"""Phase 5 acceptance tests: dispatch of the repaired unit (D9), replacement unit
(D7), returnable gate pass for loaners (N1, N2). Everything is rolled back.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase05.run
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, getdate, today

from sas_fortuna.support import repair
from sas_fortuna.support.test_phase01 import RESULTS, check, expect_error
from sas_fortuna.support.test_phase03 import _actions, _employee, _repair_order, _sell

LOANER = "ZZ-LOANER-1"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_hooks()
		emp = _employee()
		_return_same_unit(emp)
		_paid_dispatch_needs_invoice(emp)
		_replacement(emp)
		_gate_pass()
	finally:
		frappe.db.rollback()
		frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _s():
	return frappe.get_single("Fortuna Support Settings")


def _serial(name):
	return frappe.db.get_value(
		"Serial No",
		name,
		[
			"status",
			"warehouse",
			"custom_warranty_end",
			"custom_invoice_no",
			"custom_sold_to",
			"custom_replaces_serial",
		],
		as_dict=True,
	)


def _move(serial, source, target):
	se = frappe.new_doc("Stock Entry")
	se.company = _s().company
	se.purpose = se.stock_entry_type = "Material Transfer"
	se.append(
		"items",
		{
			"item_code": "TEST-MODEL-1",
			"qty": 1,
			"s_warehouse": source,
			"t_warehouse": target,
			"use_serial_batch_fields": 1,
			"serial_no": serial,
		},
	)
	se.insert(ignore_permissions=True)
	se.submit()


def _ready_order(serial, emp, via_workflow=True):
	ro, ticket = _repair_order(serial, emp)
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro.name)).submit()
	if via_workflow:
		ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "Start Repair")
		ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "End Repair")
	else:
		frappe.db.set_value("Repair Order", ro.name, "status", "Ready")
	return frappe.get_doc("Repair Order", ro.name), ticket


def _hooks():
	print("\n== 1. Phase 5 hook wired")
	ev = frappe.get_hooks("doc_events").get("Delivery Note", {}).get("on_submit", [])
	check("Delivery Note.on_submit -> repair", "sas_fortuna.support.repair.delivery_note_on_submit" in ev)
	check(
		"Sale stamping still runs first",
		ev.index("sas_fortuna.support.sales.delivery_note_on_submit")
		< ev.index("sas_fortuna.support.repair.delivery_note_on_submit"),
	)


def _return_same_unit(emp):
	print("\n== 2. Return the repaired unit (D9)")
	ro, ticket = _repair_order("TSN-0001", emp)
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro.name)).submit()
	expect_error("Dispatch before Ready is refused", lambda: repair.make_dispatch(ro.name), "status ready")
	ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "Start Repair")
	ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "End Repair")

	dn = frappe.get_doc("Delivery Note", repair.make_dispatch(ro.name))
	row = dn.items[0]
	check(
		"Dispatch draft: same serial, from Repair-In",
		row.serial_no == "TSN-0001" and row.warehouse == _s().repair_in_warehouse,
	)
	check("Dispatch draft is zero value", not dn.grand_total, dn.grand_total)
	check(
		"Dispatch draft linked to the repair",
		dn.custom_repair_order == ro.name and not dn.custom_replaces_serial,
	)
	dn.submit()

	ro.reload()
	check(
		"Repair Order -> Dispatched with the delivery note",
		ro.status == "Dispatched" and ro.delivery_note == dn.name,
		f"{ro.status} {ro.delivery_note}",
	)
	t = frappe.get_doc("HD Ticket", ticket)
	field = "resolution_details" if t.meta.has_field("resolution_details") else "custom_resolution_notes"
	check(
		"Ticket resolved, with a note naming the delivery note",
		t.status == "Resolved" and dn.name in (t.get(field) or ""),
		f"{t.status}",
	)
	check("Unit is back with the customer (Delivered)", _serial("TSN-0001").status == "Delivered")
	check(
		"Its sale details are untouched (not a new sale)",
		_serial("TSN-0001").custom_warranty_end
		and str(_serial("TSN-0001").custom_warranty_end) == "2027-10-15",
	)
	check("Dispatched: Close is offered", _actions(ro) == {"Close"}, str(_actions(ro)))
	ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "Close")
	check("Close -> Closed", ro.status == "Closed")


def _paid_dispatch_needs_invoice(emp):
	print("\n== 3. Paid repair: no dispatch before the invoice is paid")
	si = _sell("Sales Invoice", "TSN-0002", update_stock=1)
	frappe.db.set_value("Serial No", "TSN-0002", "custom_warranty_end", "2026-01-01")
	ro, _t = _ready_order("TSN-0002", emp, via_workflow=False)
	check("Order is Chargeable", ro.invoice_method == "Chargeable")
	expect_error(
		"Dispatch refused until the service invoice is submitted",
		lambda: repair.make_dispatch(ro.name),
		"submit the sales invoice",
	)
	frappe.db.set_value(
		"Repair Order", ro.name, "sales_invoice", si.name
	)  # stands in for the Phase 4 service invoice
	# Fortuna (13 Nov 2026): payment in full before shipment of the repaired unit.
	frappe.db.set_value("Sales Invoice", si.name, "outstanding_amount", 100)
	expect_error(
		"Dispatch refused while the invoice is not fully paid",
		lambda: repair.make_dispatch(ro.name),
		"not fully paid",
	)
	frappe.db.set_value("Sales Invoice", si.name, "outstanding_amount", 0)  # stands in for the payment
	check("Allowed once the invoice is submitted and paid", bool(repair.make_dispatch(ro.name)))


def _replacement(emp):
	print("\n== 4. Replacement unit (D7)")
	s = _s()
	_move(
		"TSN-0003",
		"Stores - FIPL" if frappe.db.exists("Warehouse", "Stores - FIPL") else s.spares_warehouse,
		s.loaner_source_warehouse,
	)
	old = _serial("TSN-0001")
	_sell("Sales Invoice", "TSN-0001", update_stock=1) if old.status != "Delivered" else None
	ro, _t = _ready_order("TSN-0001", emp, via_workflow=False)

	dn = frappe.get_doc("Delivery Note", repair.make_dispatch(ro.name, replacement_serial="TSN-0003"))
	row = dn.items[0]
	check(
		"Replacement leaves from the loaner/replacement store",
		row.serial_no == "TSN-0003" and row.warehouse == s.loaner_source_warehouse,
	)
	check("Delivery note records which unit it replaces", dn.custom_replaces_serial == "TSN-0001")
	dn.submit()

	new = _serial("TSN-0003")
	check("New unit is with the customer", new.status == "Delivered" and new.custom_sold_to == ro.customer)
	check(
		"New unit keeps the old unit's warranty end (setting on)",
		str(new.custom_warranty_end) == str(old.custom_warranty_end),
		f"{new.custom_warranty_end} vs {old.custom_warranty_end}",
	)
	check("New unit carries the original invoice no.", new.custom_invoice_no == old.custom_invoice_no)
	check("New unit points back to the unit it replaced", new.custom_replaces_serial == "TSN-0001")
	check(
		"Repair Order records the replacement serial",
		frappe.db.get_value("Repair Order", ro.name, "replacement_serial") == "TSN-0003",
	)
	check("Old unit stays with Fortuna in Repair-In", _serial("TSN-0001").warehouse == s.repair_in_warehouse)

	from sas_fortuna.support.utils import get_serial_coverage

	check(
		"Ticket on the new unit -> Warranty (old cover carried over)",
		get_serial_coverage("TSN-0003").support_type == "Warranty",
	)

	frappe.db.set_single_value("Fortuna Support Settings", "replacement_keeps_old_warranty", 0)
	frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")
	repair._carry_warranty_to_replacement(frappe.get_doc("Delivery Note", dn.name))
	check(
		"Setting off: fresh warranty from the dispatch date",
		getdate(_serial("TSN-0003").custom_warranty_end) == getdate(add_days(dn.posting_date, 365)),
	)


def _gate_pass():
	print("\n== 5. Returnable gate pass for a loaner (N1, N2)")
	s = _s()
	se = frappe.new_doc("Stock Entry")
	se.company = s.company
	se.purpose = se.stock_entry_type = "Material Receipt"
	# TEST-MODEL-1 tracks batches as well as serials: a new serial needs a batch.
	batch = frappe.db.get_value("Serial No", "TSN-0001", "batch_no")
	se.append(
		"items",
		{
			"item_code": "TEST-MODEL-1",
			"qty": 1,
			"basic_rate": 1000,
			"t_warehouse": s.loaner_source_warehouse,
			"use_serial_batch_fields": 1,
			"serial_no": LOANER,
			"batch_no": batch,
		},
	)
	se.insert(ignore_permissions=True)
	se.submit()

	def new_pass(**kw):
		d = {
			"doctype": "Returnable Gate Pass",
			"customer": "Test Company 1",
			"item_code": "TEST-MODEL-1",
			"serial_no": LOANER,
			"expected_return_date": add_days(today(), 7),
		}
		d.update(kw)
		return frappe.get_doc(d)

	expect_error(
		"Return date before issue date is refused",
		lambda: new_pass(expected_return_date=add_days(today(), -1)).insert(ignore_permissions=True),
		"cannot be before",
	)

	gp = new_pass().insert(ignore_permissions=True)
	check("New pass is Draft", gp.status == "Draft")
	gp.submit()
	gp.reload()
	check("Submitted pass is Open with its issue stock entry", gp.status == "Open" and gp.issue_stock_entry)
	check("Loaner moved to Customer Loaner", _serial(LOANER).warehouse == s.customer_loaner_warehouse)

	from frappe.desk.query_report import run as run_report

	rows = run_report("Returnable Items Outstanding").get("result") or []
	check(
		"Report 'Returnable Items Outstanding' lists the open pass",
		any(gp.name in str(r) for r in rows),
		f"{len(rows)} rows",
	)

	frappe.db.set_value("Returnable Gate Pass", gp.name, "expected_return_date", add_days(today(), -1))
	from sas_fortuna.support.tasks import mark_overdue_gate_passes

	mark_overdue_gate_passes()
	check(
		"Daily job marks a late pass Overdue",
		frappe.db.get_value("Returnable Gate Pass", gp.name, "status") == "Overdue",
	)

	from sas_fortuna.sas_fortuna.doctype.returnable_gate_pass.returnable_gate_pass import mark_returned

	mark_returned(gp.name)
	gp.reload()
	check(
		"Mark Returned -> Returned, dated today", gp.status == "Returned" and str(gp.returned_on) == today()
	)
	check("Loaner back in the loaner store", _serial(LOANER).warehouse == s.loaner_source_warehouse)
	expect_error(
		"A returned pass cannot be returned again", lambda: mark_returned(gp.name), "only open passes"
	)

	gp2 = new_pass().insert(ignore_permissions=True)
	gp2.submit()
	gp2.reload()
	gp2.cancel()
	gp2.reload()
	check(
		"Cancelling an open pass brings the loaner back",
		gp2.status == "Cancelled" and _serial(LOANER).warehouse == s.loaner_source_warehouse,
	)
