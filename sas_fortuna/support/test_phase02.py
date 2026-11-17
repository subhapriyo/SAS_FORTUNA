"""Phase 2 acceptance tests: ticket routing and classification, serial stamping on sale.
Everything is rolled back; nothing is left behind.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase02.run

Uses the test data from T6: item TEST-MODEL-1 (warranty 365 days), serials
TSN-0001 (sold on a Sales Invoice) and TSN-0002 / TSN-0003 (in stock).
"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, today

from sas_fortuna.support.test_phase01 import RESULTS, check, expect_error

ITEM = "TEST-MODEL-1"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	ctx = _context()
	if not ctx:
		return
	try:
		_hooks()
		_routing()
		_classification(ctx)
		_ownership(ctx)
		_resolution()
		_stamp_on_invoice(ctx)
		_stamp_on_delivery_note(ctx)
	finally:
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _context():
	for serial in ("TSN-0001", "TSN-0002", "TSN-0003"):
		if not frappe.db.exists("Serial No", serial):
			print(f"Test data missing: {serial}. Create it as in T6 first.")
			return None
	customer = frappe.db.get_value("Serial No", "TSN-0001", "custom_sold_to") or "Test Company 1"
	settings = frappe.get_single("Fortuna Support Settings")
	return frappe._dict(
		customer=customer,
		hd_customer=frappe.db.get_value("HD Customer", {"custom_erpnext_customer": customer}, "name"),
		company=settings.company,
		warehouse=frappe.db.get_value("Serial No", "TSN-0002", "warehouse"),
	)


def _ticket(**fields):
	doc = frappe.get_doc(
		{
			"doctype": "HD Ticket",
			"subject": "ZZ Test ticket",
			"description": "Phase 2 test",
			"raised_by": "zz.test@example.com",
		}
	)
	doc.update(fields)
	return doc.insert(ignore_permissions=True)


def _hooks():
	print("\n== 1. Phase 2 hooks wired")
	events = frappe.get_hooks("doc_events")
	check(
		"HD Ticket.validate",
		"sas_fortuna.support.hd_ticket.validate" in events.get("HD Ticket", {}).get("validate", []),
	)
	check(
		"HD Ticket.on_update",
		"sas_fortuna.support.hd_ticket.on_update" in events.get("HD Ticket", {}).get("on_update", []),
	)
	check(
		"Sales Invoice.on_submit",
		"sas_fortuna.support.sales.sales_invoice_on_submit"
		in events.get("Sales Invoice", {}).get("on_submit", []),
	)
	check(
		"Delivery Note.on_submit",
		"sas_fortuna.support.sales.delivery_note_on_submit"
		in events.get("Delivery Note", {}).get("on_submit", []),
	)


def _routing():
	print("\n== 2. Ticket Type -> Team (C1)")
	check(
		"Software ticket goes to Software Support",
		_ticket(ticket_type="Software").agent_group == "Software Support",
	)
	check(
		"Hardware ticket goes to Hardware Support",
		_ticket(ticket_type="Hardware").agent_group == "Hardware Support",
	)
	check(
		"Post-Installation ticket goes to Hardware Support",
		_ticket(ticket_type="Post-Installation").agent_group == "Hardware Support",
	)
	check(
		"A team chosen by hand is kept",
		_ticket(ticket_type="Software", agent_group="Hardware Support").agent_group == "Hardware Support",
	)
	t = _ticket()
	check(
		"Ticket without a type is not routed by us",
		not t.agent_group or t.ticket_type not in ("Software", "Hardware", "Post-Installation"),
		f"type={t.ticket_type} team={t.agent_group}",
	)


def _classification(ctx):
	print("\n== 3. Serial -> model, invoice, Warranty / AMC / Paid (C2, N4, N5)")
	t = _ticket(ticket_type="Hardware", custom_serial_no="TSN-0001")
	check("Model filled from the serial", t.custom_product_model == ITEM, t.custom_product_model)
	check("Invoice no. filled", bool(t.custom_invoice_no), t.custom_invoice_no)
	check(
		"Warranty end = invoice date + 365",
		t.custom_warranty_end
		and getdate(t.custom_warranty_end) == add_days(getdate(t.custom_invoice_date), 365),
	)
	check("Sold serial in warranty -> Warranty", t.custom_support_type == "Warranty", t.custom_support_type)
	check("ERPNext customer filled", t.custom_erpnext_customer == ctx.customer, t.custom_erpnext_customer)

	t2 = _ticket(ticket_type="Hardware", custom_serial_no="TSN-0002")
	check("Unsold serial -> Paid Service", t2.custom_support_type == "Paid Service", t2.custom_support_type)

	frappe.db.set_value(
		"Serial No",
		"TSN-0001",
		{"custom_warranty_end": add_days(today(), -1), "amc_expiry_date": add_days(today(), 200)},
	)
	t3 = _ticket(ticket_type="Hardware", custom_serial_no="TSN-0001")
	check("Warranty over, AMC running -> AMC", t3.custom_support_type == "AMC", t3.custom_support_type)
	frappe.db.set_value("Serial No", "TSN-0001", "amc_expiry_date", add_days(today(), -1))
	t4 = _ticket(ticket_type="Hardware", custom_serial_no="TSN-0001")
	check(
		"Warranty and AMC over -> Paid Service",
		t4.custom_support_type == "Paid Service",
		t4.custom_support_type,
	)

	other_item = frappe.get_all(
		"Item", filters={"name": ["!=", ITEM], "is_stock_item": 1}, pluck="name", limit=1
	)
	if other_item:
		expect_error(
			"Serial of another model is refused",
			lambda: _ticket(
				ticket_type="Hardware", custom_product_model=other_item[0], custom_serial_no="TSN-0002"
			),
			"belongs to",
		)

	t5 = _ticket(ticket_type="Hardware", custom_serial_no="TSN-0002")
	t5 = frappe.get_doc("HD Ticket", t5.name)  # Helpdesk touches the ticket after insert
	t5.custom_serial_no = None
	t5.save(ignore_permissions=True)
	check("Clearing the serial clears the support type", not t5.custom_support_type)

	# Normal warranty is 1 year: an Item without its own Warranty Period gets 365 days.
	from sas_fortuna.support.utils import compute_warranty_end, get_standard_warranty_days

	check("Standard warranty is 365 days", get_standard_warranty_days() == 365, get_standard_warranty_days())
	frappe.db.set_value("Item", ITEM, "warranty_period", None)
	start = getdate(today())
	check(
		"Item without Warranty Period -> 1 year",
		compute_warranty_end(ITEM, start) == getdate(add_days(start, 365)),
	)
	frappe.db.set_value("Item", ITEM, "warranty_period", 730)
	check(
		"Item's own Warranty Period wins", compute_warranty_end(ITEM, start) == getdate(add_days(start, 730))
	)
	frappe.db.set_value("Item", ITEM, "warranty_period", 365)


def _ownership(ctx):
	print("\n== 4. Portal customers only see their own units (P1)")
	other = frappe.get_all(
		"HD Customer", filters={"custom_erpnext_customer": ["not in", [ctx.customer]]}, pluck="name", limit=1
	)
	with patch("sas_fortuna.support.hd_ticket.is_helpdesk_agent", return_value=False):
		if other:
			expect_error(
				"Customer B cannot raise a ticket on customer A's serial",
				lambda: _ticket(ticket_type="Hardware", customer=other[0], custom_serial_no="TSN-0001"),
				"not registered to your account",
			)
		if ctx.hd_customer:
			t = _ticket(ticket_type="Hardware", customer=ctx.hd_customer, custom_serial_no="TSN-0001")
			check(
				"Customer A can raise a ticket on their own serial",
				t.custom_support_type in ("Warranty", "AMC", "Paid Service"),
			)
	t = _ticket(ticket_type="Hardware", customer=other[0] if other else None, custom_serial_no="TSN-0001")
	check("An agent may log a ticket for any serial", bool(t.name))


def _resolution():
	print("\n== 5. Resolve needs notes; closing stamps last service date (C3, F7)")
	t = _ticket(ticket_type="Hardware", custom_serial_no="TSN-0002")
	field = "resolution_details" if t.meta.has_field("resolution_details") else "custom_resolution_notes"

	# Without notes an agent's Resolved is held back: the ticket keeps its status and is flagged,
	# which shows the Resolution Details box (support/hd_ticket.py require_resolution_notes).
	before = frappe.db.get_value("HD Ticket", t.name, "status")
	doc = frappe.get_doc("HD Ticket", t.name)
	doc.status = "Resolved"
	with patch("sas_fortuna.support.hd_ticket.is_helpdesk_agent", return_value=True):
		doc.save(ignore_permissions=True)
	held = frappe.db.get_value("HD Ticket", t.name, ["status", "custom_resolution_requested"], as_dict=True)
	check(
		"Resolve without notes is held back (status kept, notes asked for)",
		held.status == before and held.custom_resolution_requested == 1,
	)
	doc = frappe.get_doc("HD Ticket", t.name)
	doc.status = "Resolved"
	doc.set(field, "Replaced the power board.")
	doc.save(ignore_permissions=True)
	check("Resolve with notes works", frappe.db.get_value("HD Ticket", t.name, "status") == "Resolved")
	check(
		"Serial gets Last Service Date",
		str(frappe.db.get_value("Serial No", "TSN-0002", "custom_last_service_date")) == today(),
	)


def _sell(doctype, serial, ctx, **extra):
	doc = frappe.new_doc(doctype)
	doc.update({"customer": ctx.customer, "company": ctx.company, "set_warehouse": ctx.warehouse, **extra})
	doc.append(
		"items",
		{
			"item_code": ITEM,
			"qty": 1,
			"rate": 1000,
			"warehouse": ctx.warehouse,
			"use_serial_batch_fields": 1,
			"serial_no": serial,
		},
	)
	doc.run_method("set_missing_values")
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _stamp_on_invoice(ctx):
	print("\n== 6. Sales Invoice stamps the serial (N4)")
	try:
		si = _sell("Sales Invoice", "TSN-0002", ctx, update_stock=1)
	except Exception as e:
		check("Test Sales Invoice submits", False, f"{type(e).__name__}: {str(e)[:150]}")
		frappe.clear_messages()
		return
	s = frappe.db.get_value(
		"Serial No",
		"TSN-0002",
		["custom_invoice_no", "custom_invoice_date", "custom_sold_to", "custom_warranty_end"],
		as_dict=True,
	)
	check("Invoice no. stamped", s.custom_invoice_no == si.name, s.custom_invoice_no)
	check("Invoice date stamped", getdate(s.custom_invoice_date) == getdate(si.posting_date))
	check("Sold To stamped", s.custom_sold_to == ctx.customer)
	check(
		"Warranty end stamped (+365)",
		s.custom_warranty_end and getdate(s.custom_warranty_end) == add_days(getdate(si.posting_date), 365),
	)
	from sas_fortuna.support.utils import find_sale_for_serial

	check("Lookup now uses the stamp", find_sale_for_serial("TSN-0002").invoice_no == si.name)


def _stamp_on_delivery_note(ctx):
	print("\n== 7. Delivery Note before invoice (N4)")
	try:
		_sell("Delivery Note", "TSN-0003", ctx)
	except Exception as e:
		check("Test Delivery Note submits", False, f"{type(e).__name__}: {str(e)[:150]}")
		frappe.clear_messages()
		return
	s = frappe.db.get_value("Serial No", "TSN-0003", ["custom_invoice_no", "custom_sold_to"], as_dict=True)
	check("Sold To stamped from the Delivery Note", s.custom_sold_to == ctx.customer)
	check("No invoice stamped yet", not s.custom_invoice_no)
	from sas_fortuna.support.utils import get_serial_coverage

	cov = get_serial_coverage("TSN-0003")
	check(
		"Coverage counts from the delivery date until invoiced",
		cov.sale_basis == "Delivery Note" and cov.support_type == "Warranty",
		f"{cov.sale_basis} / {cov.support_type}",
	)
