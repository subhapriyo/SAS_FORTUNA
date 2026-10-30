"""Phase 8 acceptance tests: customer portal /repairs (P1) and ticket from a
Sales Order (N9). Everything is rolled back.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase08.run
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import today

from sas_fortuna.support import repair
from sas_fortuna.support.test_phase01 import RESULTS, _customer, check
from sas_fortuna.support.test_phase03 import _employee, _repair_order, _sell

CUSTOMER = "Test Company 1"
USER_A, USER_B = "zz.portal.a@example.com", "zz.portal.b@example.com"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_ticket_from_order()
		ro, other_customer = _setup_portal()
		_portal_page(ro, other_customer)
		_accept_quotation(ro)
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _ticket_from_order():
	print("\n== 1. Helpdesk ticket from a Sales Order (N9)")
	from sas_fortuna.support.orders import create_ticket_from_order

	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": CUSTOMER,
			"company": frappe.db.get_single_value("Fortuna Support Settings", "company"),
			"delivery_date": today(),
			"items": [{"item_code": "AMC Service", "qty": 1, "rate": 1000, "delivery_date": today()}],
		}
	).insert(ignore_permissions=True)
	try:
		name = create_ticket_from_order(so.name, subject="ZZ Site visit needed", ticket_type="Hardware")
	except Exception as e:
		check("Ticket created from the order", False, f"{type(e).__name__}: {str(e)[:200]}")
		frappe.clear_messages()
		return
	t = frappe.get_doc("HD Ticket", name)
	check(
		"Ticket created with the subject and type",
		t.subject == "ZZ Site visit needed" and t.ticket_type == "Hardware",
	)
	check(
		"Ticket linked to the customer (ERPNext and Helpdesk)",
		t.custom_erpnext_customer == CUSTOMER
		and frappe.db.get_value("HD Customer", t.customer, "custom_erpnext_customer") == CUSTOMER,
	)
	check(
		"Ticket linked to the Sales Order",
		t.get("custom_sales_order") == so.name,
		t.get("custom_sales_order"),
	)
	check("Ticket routed to the Hardware team", t.agent_group == "Hardware Support")


def _portal_user(email, customer):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "ZZ Portal",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)
	user.add_roles("Customer")
	frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": "ZZ Portal",
			"user": email,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	).insert(ignore_permissions=True)


def _setup_portal():
	other = _customer("ZZ Other Customer")
	_portal_user(USER_A, CUSTOMER)
	_portal_user(USER_B, other.name)
	ro, _t = _repair_order("TSN-0001", _employee())
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro.name)).submit()
	return frappe.get_doc("Repair Order", ro.name), other.name


def _list_for(user):
	"""Rows of the /repairs list as `user` sees them."""
	from sas_fortuna.support.portal_repairs import get_repair_list

	frappe.set_user(user)
	try:
		return get_repair_list("Repair Order", None, {}, 0, 100)
	finally:
		frappe.set_user("Administrator")


def _detail_for(user, name):
	"""Context of the /repairs/<name> page as `user` sees it."""
	from sas_fortuna.www import repair as page

	frappe.set_user(user)
	frappe.form_dict.name = name
	try:
		return page.get_context(frappe._dict())
	finally:
		frappe.set_user("Administrator")


def _portal_page(ro, other_customer):
	print("\n== 2. /repairs shows customers only their own repairs (P1)")
	from sas_fortuna.support.portal import get_portal_customer

	check("Portal user A maps to their customer", get_portal_customer(USER_A) == CUSTOMER)
	rows = _list_for(USER_A)
	names = [r.name for r in rows]
	check("Customer A sees their repair", ro.name in names, str(names))
	row = next((r for r in rows if r.name == ro.name), None)
	check(
		"Row shows serial, model and status",
		row and row.serial_no == "TSN-0001" and row.status == "Unit Received",
		str(row),
	)
	check("Customer B sees none of A's repairs", ro.name not in [r.name for r in _list_for(USER_B)])

	ctx = _detail_for(USER_A, ro.name)
	check(
		"Detail page shows the unit and the progress",
		ctx.doc.serial_no == "TSN-0001" and any(s["state"] == "current" for s in ctx.steps),
	)
	check("No quotation yet: nothing to accept", not ctx.get("can_accept"))
	try:
		_detail_for(USER_B, ro.name)
		check("Customer B cannot open A's repair", False)
	except frappe.PermissionError:
		check("Customer B cannot open A's repair", True)
	try:
		_detail_for("Guest", ro.name)
		check("Guests are asked to log in", False)
	except frappe.PermissionError:
		check("Guests are asked to log in", True)

	# Render both pages the way a browser request would (list + detail), as customer A.
	try:
		from frappe.website.serve import get_response
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sas_fortuna.portal import apply_portal_overrides

		frappe.set_user(USER_A)
		for path in ("repairs", f"repairs/{ro.name}"):
			frappe.local.request = Request(EnvironBuilder(path="/" + path).get_environ())
			frappe.local.form_dict = frappe._dict()
			apply_portal_overrides()
			resp = get_response(path)
			body = resp.get_data(as_text=True)
			check(
				f"Page /{path} renders for the customer",
				resp.status_code == 200 and ro.name in body,
				f"status={resp.status_code}",
			)
	except Exception as e:
		check("Page /repairs renders for the customer", False, f"{type(e).__name__}: {str(e)[:150]}")
	finally:
		frappe.set_user("Administrator")


def _accept_quotation(ro):
	print("\n== 3. Accept quotation on the portal (N7)")
	from sas_fortuna.support.portal import accept_quotation

	frappe.db.set_value("Repair Order", ro.name, "invoice_method", "Chargeable")
	ro.reload()
	qtn = frappe.get_doc("Quotation", repair.make_quotation(ro.name))
	for row in qtn.items:
		row.rate = 500
	qtn.save(ignore_permissions=True)
	qtn = apply_workflow(frappe.get_doc("Quotation", qtn.name), "Approve")

	check("Approved quotation: Accept is offered", bool(_detail_for(USER_A, ro.name).get("can_accept")))

	frappe.set_user(USER_B)
	try:
		accept_quotation(qtn.name)
		check("Customer B cannot accept A's quotation", False)
	except frappe.PermissionError:
		check("Customer B cannot accept A's quotation", True)
	finally:
		frappe.set_user("Administrator")

	frappe.set_user(USER_A)
	try:
		so_name = accept_quotation(qtn.name)
	finally:
		frappe.set_user("Administrator")
	so = frappe.get_doc("Sales Order", so_name)
	check(
		"Accepting creates a DRAFT Sales Order for Fortuna to confirm",
		so.docstatus == 0 and so.customer == CUSTOMER,
	)
	check("Draft order carries the repair link", so.custom_repair_order == ro.name)
	check(
		"Order notes that the customer accepted on the portal",
		bool(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "Sales Order",
					"reference_name": so_name,
					"content": ["like", "%portal%"],
				},
			)
		),
	)
