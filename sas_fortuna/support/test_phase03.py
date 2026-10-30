"""Phase 3 acceptance tests: Repair Order, repair receipt (D2), workflow (D6), N3.
Everything is rolled back; nothing is left behind.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase03.run

D2 open point answered here: can a unit that was SOLD (serial status
Delivered) be received back into Repair-In with a zero-value Material Receipt?
"""

import frappe
from frappe.model.workflow import apply_workflow, get_transitions

from sas_fortuna.support import repair
from sas_fortuna.support.test_phase01 import RESULTS, check, expect_error


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_setup_records()
		emp = _employee()
		_warranty_repair(emp)
		_chargeable_repair(emp)
	finally:
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _employee():
	existing = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name", limit=1)
	if existing:
		return existing[0]
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "ZZ Test Engineer",
				"gender": frappe.get_all("Gender", pluck="name", limit=1)[0],
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": frappe.db.get_single_value("Fortuna Support Settings", "company"),
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _ticket(serial):
	t = frappe.get_doc(
		{
			"doctype": "HD Ticket",
			"subject": "ZZ Test repair",
			"description": "Unit does not power on.",
			"raised_by": "zz.test@example.com",
			"ticket_type": "Hardware",
			"custom_serial_no": serial,
		}
	).insert(ignore_permissions=True)
	return t.name


def _repair_order(serial, emp, customer=None):
	"""An unsold serial has no customer, so the agent picks one (as in real use)."""
	ticket = _ticket(serial)
	ro = frappe.get_doc(
		{"doctype": "Repair Order", "helpdesk_ticket": ticket, "responsible": emp, "customer": customer}
	).insert(ignore_permissions=True)
	return ro, ticket


def _sell(doctype, serial, **extra):
	from sas_fortuna.support.test_phase02 import _context
	from sas_fortuna.support.test_phase02 import _sell as sell

	ctx = _context()
	ctx.warehouse = frappe.db.get_value("Serial No", serial, "warehouse")  # sell from where it sits
	return sell(doctype, serial, ctx, **extra)


def _setup_records():
	print("\n== 1. Phase 3 configuration")
	events = frappe.get_hooks("doc_events")
	check(
		"Hook Stock Entry.on_submit",
		"sas_fortuna.support.repair.stock_entry_on_submit"
		in events.get("Stock Entry", {}).get("on_submit", []),
	)
	check(
		"Hook Stock Entry.on_cancel",
		"sas_fortuna.support.repair.stock_entry_on_cancel"
		in events.get("Stock Entry", {}).get("on_cancel", []),
	)
	check(
		"HD Ticket form script wired",
		"public/js/hd_ticket.js" in str(frappe.get_hooks("doctype_js").get("HD Ticket", [])),
	)
	wf = frappe.db.get_value(
		"Workflow", "Repair Order Flow", ["is_active", "workflow_state_field"], as_dict=True
	)
	check(
		"Workflow Repair Order Flow is active on status",
		wf and wf.is_active and wf.workflow_state_field == "status",
	)
	check(
		"Workflow has 8 states and 8 transitions",
		frappe.db.count("Workflow Document State", {"parent": "Repair Order Flow"}) == 8
		and frappe.db.count("Workflow Transition", {"parent": "Repair Order Flow"}) == 8,
	)
	check(
		"Notification Fortuna Unit Received enabled",
		frappe.db.get_value("Notification", "Fortuna Unit Received", "enabled") == 1,
	)
	check("Kanban Repair Board exists", frappe.db.exists("Kanban Board", "Repair Board"))


def _actions(doc):
	return {t.action for t in get_transitions(frappe.get_doc("Repair Order", doc.name))}


def _warranty_repair(emp):
	print("\n== 2. Repair Order from a ticket (D1)")
	ro, ticket = _repair_order("TSN-0001", emp)
	check(
		"Customer, model and serial copied from the ticket",
		ro.customer and ro.product_model == "TEST-MODEL-1" and ro.serial_no == "TSN-0001",
	)
	check("Support type Warranty", ro.support_type == "Warranty", ro.support_type)
	check(
		"Invoice method defaults to Free (Warranty)",
		ro.invoice_method == "Free (Warranty)",
		ro.invoice_method,
	)
	check("Starts as Registered", ro.status == "Registered", ro.status)
	t = frappe.db.get_value(
		"HD Ticket", ticket, ["custom_repair_order", "custom_repair_status"], as_dict=True
	)
	check(
		"Ticket shows the repair order and its status",
		t.custom_repair_order == ro.name and t.custom_repair_status == "Registered",
		str(t),
	)
	check("Registered: only Cancel is offered", _actions(ro) == {"Cancel"}, str(_actions(ro)))

	print("\n== 3. Repair receipt of a SOLD unit (D2 open point)")
	serial_before = frappe.db.get_value("Serial No", "TSN-0001", ["status", "warehouse"], as_dict=True)
	print(f"  TSN-0001 before: status={serial_before.status}, warehouse={serial_before.warehouse}")
	se_name = repair.make_repair_receipt(ro.name)
	se = frappe.get_doc("Stock Entry", se_name)
	item = se.items[0]
	check(
		"Receipt draft: type Repair Receipt into Repair-In",
		se.stock_entry_type == "Repair Receipt"
		and item.t_warehouse == frappe.db.get_single_value("Fortuna Support Settings", "repair_in_warehouse"),
	)
	check(
		"Receipt draft: zero value, serial set",
		not item.basic_rate and item.allow_zero_valuation_rate and item.serial_no == "TSN-0001",
	)
	try:
		se.submit()
		ok = True
	except Exception as e:
		ok = False
		print(f"  D2 BLOCKED: {type(e).__name__}: {str(e)[:300]}")
		frappe.clear_messages()
	check("D2: a sold (Delivered) unit can be received back", ok)
	if not ok:
		return
	serial_after = frappe.db.get_value("Serial No", "TSN-0001", ["status", "warehouse"], as_dict=True)
	print(f"  TSN-0001 after:  status={serial_after.status}, warehouse={serial_after.warehouse}")
	check("Unit now sits in Repair-In", serial_after.warehouse == item.t_warehouse)
	gl = frappe.db.count("GL Entry", {"voucher_no": se.name, "is_cancelled": 0})
	check(
		"No accounting value posted (zero-value receipt)",
		not frappe.db.sql(
			"select sum(debit) from `tabGL Entry` where voucher_no=%s and is_cancelled=0", se.name
		)[0][0],
		f"{gl} GL rows",
	)
	ro.reload()
	check(
		"Repair Order -> Unit Received with receipt linked",
		ro.status == "Unit Received" and ro.repair_receipt == se.name,
		f"{ro.status} {ro.repair_receipt}",
	)
	check(
		"Ticket shows Unit Received",
		frappe.db.get_value("HD Ticket", ticket, "custom_repair_status") == "Unit Received",
	)
	expect_error("A second receipt is refused", lambda: repair.make_repair_receipt(ro.name), "already exists")
	check(
		"Warranty job: Start Repair offered, Send Quotation not",
		_actions(ro) == {"Start Repair", "Cancel"},
		str(_actions(ro)),
	)

	print("\n== 4. Workflow (D6)")
	ro = frappe.get_doc("Repair Order", ro.name)
	ro = apply_workflow(ro, "Start Repair")
	check("Start Repair -> In Repair", ro.status == "In Repair", ro.status)
	ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "End Repair")
	check("End Repair -> Ready", ro.status == "Ready", ro.status)
	check(
		"Ticket follows to Ready", frappe.db.get_value("HD Ticket", ticket, "custom_repair_status") == "Ready"
	)
	check("Ready: no human action (dispatch is by Delivery Note)", not _actions(ro), str(_actions(ro)))

	print("\n== 5. Units still in our stock; cancelling a receipt")
	expect_error(
		"Unsold serial without a customer is refused", lambda: _repair_order("TSN-0003", emp), "customer"
	)
	ro_own, _t = _repair_order("TSN-0003", emp, customer="Test Company 1")
	se_own = frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro_own.name))
	expect_error(
		"A unit still in our own store cannot be 'received' from a customer", se_own.submit, "already present"
	)
	frappe.db.set_value("Repair Order", ro_own.name, "status", "Cancelled")  # one open repair per unit

	_sell("Delivery Note", "TSN-0003")  # now it is with the customer
	ro2, _t = _repair_order("TSN-0003", emp)
	se2 = frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro2.name))
	se2.submit()
	se2.reload()
	se2.cancel()
	ro2.reload()
	check(
		"Receipt cancelled -> Registered, link cleared",
		ro2.status == "Registered" and not ro2.repair_receipt,
		f"{ro2.status} {ro2.repair_receipt}",
	)


def _chargeable_repair(emp):
	print("\n== 6. Paid repair: payment gate (N7)")
	_sell("Sales Invoice", "TSN-0002", update_stock=1)
	frappe.db.set_value("Serial No", "TSN-0002", "custom_warranty_end", "2026-01-01")  # warranty over
	ro, _t = _repair_order("TSN-0002", emp)
	check(
		"Out-of-warranty unit -> Paid Service, Chargeable",
		ro.support_type == "Paid Service" and ro.invoice_method == "Chargeable",
		f"{ro.support_type} {ro.invoice_method}",
	)
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro.name)).submit()
	ro.reload()
	check("Chargeable, no quotation yet: only Cancel", _actions(ro) == {"Cancel"}, str(_actions(ro)))
	frappe.db.set_value(
		"Repair Order", ro.name, "quotation", "QTN-TEST"
	)  # stands in for the Phase 4 quotation
	check("With a quotation: Send Quotation offered", "Send Quotation" in _actions(ro), str(_actions(ro)))
	frappe.db.set_value("Repair Order", ro.name, "status", "Awaiting Payment")
	check(
		"Awaiting Payment, unpaid: Start Repair NOT offered",
		"Start Repair" not in _actions(ro),
		str(_actions(ro)),
	)
	frappe.db.set_value("Repair Order", ro.name, "payment_cleared", 1)
	check("Awaiting Payment, paid: Start Repair offered", "Start Repair" in _actions(ro), str(_actions(ro)))
