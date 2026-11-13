"""Phase 4 acceptance tests: spares (D3, N6), warranty cost (D5), repair quotation
(D5, N8) and the payment gate (N7). Everything is rolled back.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase04.run
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import flt, today

from sas_fortuna.support import repair
from sas_fortuna.support.test_phase01 import RESULTS, check, expect_error
from sas_fortuna.support.test_phase03 import _actions, _employee, _repair_order, _sell

SPARE = "ZZ Test Spare Board"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_hooks()
		emp = _employee()
		_make_spare()
		_spares(emp)
		_quotation_and_payment(emp)
	finally:
		frappe.db.rollback()
		frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _settings():
	return frappe.get_single("Fortuna Support Settings")


def _set_setting(field, value):
	frappe.db.set_single_value("Fortuna Support Settings", field, value)
	frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")


def _hooks():
	print("\n== 1. Phase 4 hooks wired")
	ev = frappe.get_hooks("doc_events")
	check(
		"Sales Order.on_submit",
		"sas_fortuna.support.repair.sales_order_on_submit" in ev.get("Sales Order", {}).get("on_submit", []),
	)
	check(
		"Sales Order.on_cancel",
		"sas_fortuna.support.repair.sales_order_on_cancel" in ev.get("Sales Order", {}).get("on_cancel", []),
	)
	check(
		"Payment Entry.on_submit / on_cancel",
		"sas_fortuna.support.repair.payment_entry_changed"
		in ev.get("Payment Entry", {}).get("on_cancel", []),
	)
	check(
		"Sales Invoice links back to the repair",
		"sas_fortuna.support.repair.sales_invoice_on_submit"
		in ev.get("Sales Invoice", {}).get("on_submit", []),
	)


def _make_spare():
	hsn = frappe.get_all("GST HSN Code", filters={"name": ["like", "8473%"]}, pluck="name", limit=1) or [
		"847330"
	]
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": SPARE,
			"item_name": SPARE,
			"item_group": "Raw Material",
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"gst_hsn_code": hsn[0],
			"valuation_rate": 200,
			"custom_status": "Approved",  # fortuna_erp disables items until approved
		}
	).insert(ignore_permissions=True)
	se = frappe.new_doc("Stock Entry")
	se.company = _settings().company
	se.purpose = se.stock_entry_type = "Material Receipt"
	se.append(
		"items",
		{"item_code": SPARE, "qty": 5, "basic_rate": 200, "t_warehouse": _settings().spares_warehouse},
	)
	se.insert(ignore_permissions=True)
	se.submit()


def _received_order(serial, emp, parts, invoice_method=None):
	ro, _ticket = _repair_order(serial, emp)
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro.name)).submit()
	ro = frappe.get_doc("Repair Order", ro.name)
	if invoice_method:
		ro.invoice_method = invoice_method
	for code, chargeable in parts:
		ro.append("parts", {"item_code": code, "qty": 1, "is_chargeable": chargeable, "rate": 200})
	ro.save(ignore_permissions=True)
	return ro


def _parts(ro):
	return {p.is_chargeable: p for p in frappe.get_doc("Repair Order", ro.name).parts}


def _bin(warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": SPARE, "warehouse": warehouse}, "actual_qty"))


def _spares(emp):
	print("\n== 2. Spares: request, reserve, consume (D3, N6)")
	s = _settings()
	# One free, one chargeable part: a chargeable part needs a Chargeable repair.
	ro = _received_order("TSN-0001", emp, [(SPARE, 0), (SPARE, 1)], invoice_method="Chargeable")
	check(
		"Chargeable parts total counts only the chargeable part",
		flt(ro.parts_chargeable_total) == 200,
		ro.parts_chargeable_total,
	)

	mr = frappe.get_doc("Material Request", repair.raise_spares_request(ro.name))
	check(
		"Spares request: Material Transfer into Repair WIP",
		mr.material_request_type == "Material Transfer" and mr.set_warehouse == s.repair_wip_warehouse,
	)
	check(
		"Spares request lists both parts, linked to the repair",
		len(mr.items) == 2 and mr.custom_repair_order == ro.name,
	)
	check("Parts marked Requested", {p.status for p in _parts(ro).values()} == {"Requested"})
	expect_error("Nothing left to request", lambda: repair.raise_spares_request(ro.name), "no pending parts")
	expect_error(
		"Consume before reserve is refused", lambda: repair.consume_spares(ro.name), "reserve the parts"
	)

	before_store, before_wip = _bin(s.spares_warehouse), _bin(s.repair_wip_warehouse)
	reserve = frappe.get_doc("Stock Entry", repair.reserve_spares(ro.name))
	reserve.submit()
	check(
		"Reserve moves 2 from the spares store to Repair WIP",
		_bin(s.spares_warehouse) == before_store - 2 and _bin(s.repair_wip_warehouse) == before_wip + 2,
	)
	parts = _parts(ro)
	check(
		"Parts marked Reserved with the stock entry",
		all(p.status == "Reserved" and p.stock_entry == reserve.name for p in parts.values()),
	)

	issue = frappe.get_doc("Stock Entry", repair.consume_spares(ro.name))
	free_row = next(r for r in issue.items if r.custom_repair_order_part == parts[0].name)
	check(
		"Free part is charged to Warranty Expense (D5)",
		free_row.expense_account == s.warranty_expense_account,
		free_row.expense_account,
	)
	issue.submit()
	check("Parts marked Consumed", {p.status for p in _parts(ro).values()} == {"Consumed"})
	check("Repair WIP back to where it was", _bin(s.repair_wip_warehouse) == before_wip)
	debit = frappe.db.sql(
		"select sum(debit) from `tabGL Entry` where voucher_no=%s and account=%s and is_cancelled=0",
		(issue.name, s.warranty_expense_account),
	)[0][0]
	check("Warranty Expense debited with the free part's cost (200)", flt(debit) == 200, debit)

	issue.reload()
	issue.cancel()
	check(
		"Cancelling the issue puts parts back to Reserved",
		{p.status for p in _parts(ro).values()} == {"Reserved"},
	)


def _quotation_and_payment(emp):
	print("\n== 3. Repair quotation (D5, N8)")
	for code in (_settings().service_charge_item, _settings().freight_item):
		check(f"{code} is approved and active", frappe.db.get_value("Item", code, "disabled") == 0)
	_sell("Sales Invoice", "TSN-0002", update_stock=1)
	frappe.db.set_value("Serial No", "TSN-0002", "custom_warranty_end", "2026-01-01")
	ro = _received_order("TSN-0002", emp, [(SPARE, 1)])
	check("Out-of-warranty repair is Chargeable", ro.invoice_method == "Chargeable")

	qtn = frappe.get_doc("Quotation", repair.make_quotation(ro.name))
	codes = [i.item_code for i in qtn.items]
	s = _settings()
	check(
		"Quotation has the chargeable part, service charge and freight",
		codes == [SPARE, s.service_charge_item, s.freight_item],
		str(codes),
	)
	check(
		"Quotation is linked to the repair",
		qtn.custom_repair_order == ro.name
		and frappe.db.get_value("Repair Order", ro.name, "quotation") == qtn.name,
	)
	expect_error("A second quotation is refused", lambda: repair.make_quotation(ro.name), "already exists")

	_sell("Delivery Note", "TSN-0003")
	amc_ro = _received_order("TSN-0003", emp, [])
	frappe.db.set_value("Repair Order", amc_ro.name, {"support_type": "AMC", "invoice_method": "AMC"})
	expect_error(
		"AMC repair quotation refused while 'Charge AMC Repairs' is off (N8)",
		lambda: repair.make_quotation(amc_ro.name),
		"amc repairs are free",
	)
	_set_setting("charge_amc_repairs", 1)
	check("...and allowed once it is switched on", bool(repair.make_quotation(amc_ro.name)))
	_set_setting("charge_amc_repairs", 0)

	print("\n== 4. Payment gate (N7)")
	for row in qtn.items:
		row.rate = {SPARE: 600, s.service_charge_item: 300, s.freight_item: 100}[row.item_code]
	qtn.save(ignore_permissions=True)
	# fortuna_erp's Quotation workflow: Draft -> Approve -> Approved (= submitted)
	qtn = apply_workflow(frappe.get_doc("Quotation", qtn.name), "Approve")
	check(
		"Quotation approved and submitted via fortuna_erp's workflow", qtn.docstatus == 1, qtn.workflow_state
	)
	ro = frappe.get_doc("Repair Order", ro.name)
	ro = apply_workflow(ro, "Send Quotation")
	check("Send Quotation -> Awaiting Payment", ro.status == "Awaiting Payment", ro.status)

	so = _make_sales_order(qtn.name)
	check("Sales Order carries the repair link from the quotation", so.custom_repair_order == ro.name)
	so.delivery_date = today()
	for item in so.items:
		item.delivery_date = today()
	so.insert(ignore_permissions=True)
	so.submit()
	ro.reload()
	check("Order confirmed: repair knows its Sales Order", ro.sales_order == so.name)

	# Fortuna (13 Nov 2026): payment in full is due before DISPATCH, so work starts on confirmation.
	_set_setting("payment_due_before", "Dispatch")
	check(
		"Payment due before dispatch: Start Repair offered once the order is confirmed",
		not ro.payment_cleared and "Start Repair" in _actions(ro),
	)
	# The rest of this section is the other policy: an advance before work starts.
	_set_setting("payment_due_before", "Repair Start")
	repair.refresh_payment_status(ro.name)
	ro.reload()
	check(
		"Payment due before repair start, not paid yet: no Start Repair",
		not ro.payment_cleared and "Start Repair" not in _actions(ro),
	)

	half = _pay(so, flt(so.grand_total) / 2)
	ro.reload()
	check("50% paid with 100% required: still blocked", not ro.payment_cleared)
	_set_setting("advance_percent", 50)
	repair.refresh_payment_status(ro.name)
	ro.reload()
	check(
		"50% paid with 50% required: cleared, Start Repair offered",
		ro.payment_cleared and "Start Repair" in _actions(ro),
	)
	_set_setting("advance_percent", 100)

	half.reload()
	half.cancel()
	ro.reload()
	check("Payment cancelled: gate closes again", not ro.payment_cleared)

	_pay(so, flt(so.grand_total))
	ro.reload()
	check("Paid in full: cleared", ro.payment_cleared == 1)
	ro = apply_workflow(frappe.get_doc("Repair Order", ro.name), "Start Repair")
	check("Start Repair -> In Repair", ro.status == "In Repair")
	_set_setting("payment_due_before", "Dispatch")

	print("\n== 5. Service invoice links back (D9)")
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	si = make_sales_invoice(so.name)
	si.allocate_advances_automatically = 1
	si.insert(ignore_permissions=True)
	si.submit()
	ro.reload()
	check("Repair knows its Sales Invoice", ro.sales_invoice == si.name)
	check("Still cleared after invoicing (advance not counted twice)", ro.payment_cleared == 1)


def _make_sales_order(quotation):
	"""Use fortuna_erp's override when present, as the Desk button does."""
	path = "erpnext.selling.doctype.quotation.quotation.make_sales_order"
	method = (frappe.get_hooks("override_whitelisted_methods") or {}).get(path, [path])[-1]
	return frappe.get_attr(method)(quotation)


def _pay(so, amount):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pe = get_payment_entry("Sales Order", so.name, party_amount=amount)
	pe.reference_no = "ZZ-TEST"
	pe.reference_date = today()
	pe.insert(ignore_permissions=True)
	pe.submit()
	return pe
