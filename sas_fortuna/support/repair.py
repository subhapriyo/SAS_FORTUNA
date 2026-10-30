"""Repair Order buttons and the ERPNext hooks that move it forward.

Buttons (called from repair_order.js) only CREATE DRAFT documents and open
them: stores / accounts still review and submit, exactly as in standard
ERPNext. Hooks on submit then update the Repair Order.

    Button               Creates (draft)                Scope
    -------------------  -----------------------------  ----------
    Make Repair Receipt  Stock Entry (Material Receipt) D2
    Raise Spares Request Material Request               N6
    Reserve Spares       Stock Entry (Material Transfer) D3
    Consume Spares       Stock Entry (Material Issue)    D3, D5
    Make Quotation       Quotation                      D5, N7, N8
    Make Dispatch        Delivery Note                  D7, D9
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from sas_fortuna.support.hd_ticket import resolve_ticket
from sas_fortuna.support.utils import (
	SUPPORT_AMC,
	compute_warranty_end,
	get_serials_from_bundle,
	get_settings,
	require_setting,
)

PART_PENDING, PART_REQUESTED, PART_RESERVED, PART_CONSUMED = "Pending", "Requested", "Reserved", "Consumed"


# ===========================================================================
# Buttons
# ===========================================================================
def _get_ro(repair_order):
	ro = frappe.get_doc("Repair Order", repair_order)
	ro.check_permission("write")
	return ro


def _company():
	return require_setting("company")


@frappe.whitelist()
def make_repair_receipt(repair_order):
	"""D2: receive the customer's unit into Repair-In at ZERO value (no GL)."""
	ro = _get_ro(repair_order)
	if ro.repair_receipt:
		frappe.throw(_("Repair Receipt {0} already exists.").format(ro.repair_receipt))

	se = frappe.new_doc("Stock Entry")
	se.company = _company()
	se.stock_entry_type = require_setting("repair_receipt_entry_type")  # "Repair Receipt"
	se.purpose = "Material Receipt"
	se.custom_repair_order = ro.name
	se.append(
		"items",
		{
			"item_code": ro.product_model,
			"qty": 1,
			"t_warehouse": require_setting("repair_in_warehouse"),
			"basic_rate": 0,
			"allow_zero_valuation_rate": 1,  # customer's unit, not our stock value
			"use_serial_batch_fields": 1,
			"serial_no": ro.serial_no,
		},
	)
	se.insert()
	return se.name


@frappe.whitelist()
def raise_spares_request(repair_order):
	"""N6: request pending parts from stores into Repair WIP."""
	ro = _get_ro(repair_order)
	rows = [p for p in ro.parts if p.status == PART_PENDING]
	if not rows:
		frappe.throw(_("No pending parts to request."))

	mr = frappe.new_doc("Material Request")
	mr.company = _company()
	mr.material_request_type = "Material Transfer"
	mr.schedule_date = nowdate()
	mr.set_warehouse = require_setting("repair_wip_warehouse")
	mr.custom_repair_order = ro.name
	for p in rows:
		mr.append("items", {"item_code": p.item_code, "qty": p.qty, "schedule_date": nowdate()})
	mr.insert()

	for p in rows:
		p.db_set("status", PART_REQUESTED)
	ro.db_set("material_request", mr.name)
	return mr.name


@frappe.whitelist()
def reserve_spares(repair_order):
	"""D3: move parts from the spares store into Repair WIP (reserved)."""
	ro = _get_ro(repair_order)
	rows = [p for p in ro.parts if p.status in (PART_PENDING, PART_REQUESTED)]
	if not rows:
		frappe.throw(_("Nothing to reserve."))

	se = _new_stock_entry(ro, "Material Transfer")
	for p in rows:
		se.append(
			"items",
			{
				"item_code": p.item_code,
				"qty": p.qty,
				"s_warehouse": require_setting("spares_warehouse"),
				"t_warehouse": require_setting("repair_wip_warehouse"),
				"custom_repair_order_part": p.name,
			},
		)
	se.insert()
	return se.name


@frappe.whitelist()
def consume_spares(repair_order):
	"""D3 + D5: issue reserved parts. Warranty parts hit Warranty Expense."""
	ro = _get_ro(repair_order)
	rows = [p for p in ro.parts if p.status == PART_RESERVED]
	if not rows:
		frappe.throw(_("Reserve the parts before consuming them."))

	settings = get_settings()
	se = _new_stock_entry(ro, "Material Issue")
	for p in rows:
		row = {
			"item_code": p.item_code,
			"qty": p.qty,
			"s_warehouse": require_setting("repair_wip_warehouse"),
			"custom_repair_order_part": p.name,
		}
		# Free-of-cost parts are a warranty cost; chargeable parts use the
		# optional account from settings, else ERPNext's default.
		if not p.is_chargeable:
			row["expense_account"] = require_setting("warranty_expense_account")
		elif settings.chargeable_parts_expense_account:
			row["expense_account"] = settings.chargeable_parts_expense_account
		se.append("items", row)
	se.insert()
	return se.name


@frappe.whitelist()
def make_quotation(repair_order):
	"""D5 / N7 / N8: quotation for chargeable parts + service charge."""
	ro = _get_ro(repair_order)
	settings = get_settings()
	if ro.support_type == SUPPORT_AMC and not settings.charge_amc_repairs:
		frappe.throw(_("AMC repairs are free as per Fortuna Support Settings."))
	if ro.invoice_method == "Free (Warranty)":
		frappe.throw(_("This is a free warranty repair: no quotation is needed."))
	if ro.quotation:
		frappe.throw(_("Quotation {0} already exists.").format(ro.quotation))

	qtn = frappe.new_doc("Quotation")
	qtn.company = _company()
	qtn.quotation_to = "Customer"
	qtn.party_name = ro.customer
	qtn.custom_repair_order = ro.name
	for p in ro.parts:
		if p.is_chargeable:
			# Rate left blank on purpose: the Selling Price List fills it.
			qtn.append("items", {"item_code": p.item_code, "qty": p.qty})
	qtn.append("items", {"item_code": require_setting("service_charge_item"), "qty": 1})
	if settings.freight_item:
		qtn.append("items", {"item_code": settings.freight_item, "qty": 1})
	qtn.insert()

	ro.db_set("quotation", qtn.name)
	return qtn.name


@frappe.whitelist()
def make_dispatch(repair_order, replacement_serial=None):
	"""D9 (return the repaired unit) or D7 (send a replacement unit).

	The Delivery Note is always ZERO value: the unit is the customer's.
	Paid work is billed separately on the service Sales Invoice.
	"""
	ro = _get_ro(repair_order)
	if ro.status != "Ready":
		frappe.throw(_("Repair Order must be in status Ready to dispatch."))
	if ro.is_chargeable and not _service_invoice_submitted(ro):
		frappe.throw(_("Submit the Sales Invoice for this paid repair before dispatch."))
	reserved = [p.item_code for p in ro.parts if p.status == PART_RESERVED]
	if reserved:
		# Reserved spares would sit in Repair WIP forever.
		frappe.throw(
			_("Consume or return the reserved parts before dispatch: {0}.").format(", ".join(reserved))
		)

	if replacement_serial:  # D7: new unit leaves from normal stock
		serial, warehouse = replacement_serial, require_setting("loaner_source_warehouse")
	else:  # D9: the same unit goes back from Repair-In
		serial, warehouse = ro.serial_no, require_setting("repair_in_warehouse")

	dn = frappe.new_doc("Delivery Note")
	dn.company = _company()
	dn.customer = ro.customer
	dn.shipping_address_name = ro.delivery_address
	dn.custom_repair_order = ro.name
	dn.custom_replaces_serial = ro.serial_no if replacement_serial else None
	dn.append(
		"items",
		{
			"item_code": ro.product_model,
			"qty": 1,
			"warehouse": warehouse,
			# 100% discount keeps the rate at 0 even if a price list has one.
			"discount_percentage": 100,
			"allow_zero_valuation_rate": 1,
			"use_serial_batch_fields": 1,
			"serial_no": serial,
		},
	)
	dn.insert()
	return dn.name


def _service_invoice_submitted(ro):
	if ro.sales_invoice:
		return frappe.db.get_value("Sales Invoice", ro.sales_invoice, "docstatus") == 1
	if not ro.sales_order:
		return False
	return bool(frappe.db.exists("Sales Invoice Item", {"sales_order": ro.sales_order, "docstatus": 1}))


def _new_stock_entry(ro, purpose):
	se = frappe.new_doc("Stock Entry")
	se.company = _company()
	se.purpose = purpose
	se.stock_entry_type = purpose  # standard types share the purpose name
	se.custom_repair_order = ro.name
	return se


# ===========================================================================
# Hooks  (wired in hooks.py -> doc_events)
# ===========================================================================
def stock_entry_on_submit(doc, method=None):
	_stock_entry_changed(doc, cancelled=False)


def stock_entry_on_cancel(doc, method=None):
	_stock_entry_changed(doc, cancelled=True)


def set_repair_status(repair_order, status, **values):
	"""System-driven status change (receipt, dispatch).

	Written with db.set_value on purpose: these moves are triggered by
	stores/accounts users submitting ERPNext documents, and the Workflow
	only lists the HUMAN actions (Start Repair, End Repair...). The change
	is mirrored on the Helpdesk ticket so agents see it.
	"""
	frappe.db.set_value("Repair Order", repair_order, {"status": status, **values})
	ticket = frappe.db.get_value("Repair Order", repair_order, "helpdesk_ticket")
	if ticket:
		frappe.db.set_value("HD Ticket", ticket, "custom_repair_status", status)


def _stock_entry_changed(doc, cancelled):
	if not doc.get("custom_repair_order"):
		return
	ro_name = doc.custom_repair_order

	# D2: unit received -> 'Unit Received'. The N3 alert to the help desk
	# owner is a Notification on Stock Entry submit (config, Phase 3).
	if doc.stock_entry_type == get_settings().repair_receipt_entry_type:
		if cancelled:
			set_repair_status(ro_name, "Registered", repair_receipt=None)
		else:
			set_repair_status(ro_name, "Unit Received", repair_receipt=doc.name)
		return

	# D3: update part rows touched by this entry.
	if doc.purpose == "Material Transfer":
		new_status = PART_REQUESTED if cancelled else PART_RESERVED
	elif doc.purpose == "Material Issue":
		new_status = PART_RESERVED if cancelled else PART_CONSUMED
	else:
		return
	for row in doc.items:
		if row.get("custom_repair_order_part"):
			frappe.db.set_value(
				"Repair Order Part",
				row.custom_repair_order_part,
				{"status": new_status, "stock_entry": None if cancelled else doc.name},
			)


def sales_order_on_submit(doc, method=None):
	"""N7: the customer confirmed the quotation; remember the order."""
	if doc.get("custom_repair_order"):
		frappe.db.set_value("Repair Order", doc.custom_repair_order, "sales_order", doc.name)
		refresh_payment_status(doc.custom_repair_order)


def sales_order_on_cancel(doc, method=None):
	if doc.get("custom_repair_order"):
		frappe.db.set_value(
			"Repair Order", doc.custom_repair_order, {"sales_order": None, "payment_cleared": 0}
		)


def sales_invoice_on_submit(doc, method=None):
	"""Link the service invoice back to the Repair Order (D9)."""
	for so in {row.sales_order for row in doc.items if row.sales_order}:
		ro = frappe.db.get_value("Sales Order", so, "custom_repair_order")
		if ro:
			frappe.db.set_value("Repair Order", ro, "sales_invoice", doc.name)
			refresh_payment_status(ro)


def payment_entry_changed(doc, method=None):
	"""N7 payment gate: re-check after any payment against the order/invoice."""
	for ref in doc.references:
		so = None
		if ref.reference_doctype == "Sales Order":
			so = ref.reference_name
		elif ref.reference_doctype == "Sales Invoice":
			so = frappe.db.get_value(
				"Sales Invoice Item",
				{"parent": ref.reference_name, "sales_order": ["is", "set"]},
				"sales_order",
			)
		ro = so and frappe.db.get_value("Sales Order", so, "custom_repair_order")
		if ro:
			refresh_payment_status(ro)


def refresh_payment_status(repair_order):
	"""Set Repair Order.payment_cleared.

	Cleared when money received >= (order total x 'Advance Required %').
	'Money received' = the larger of advances against the order and amount
	paid on its invoices (an advance later allocated to the invoice would
	otherwise be counted twice). The workflow transition 'Start Repair' only
	allows the move when payment_cleared = 1  (pure config condition).
	"""
	so_name = frappe.db.get_value("Repair Order", repair_order, "sales_order")
	cleared = 0
	if so_name:
		so = frappe.db.get_value(
			"Sales Order", so_name, ["docstatus", "grand_total", "advance_paid"], as_dict=True
		)
		if so.docstatus == 1:
			percent = flt(get_settings().advance_percent) or 100
			required = flt(so.grand_total) * percent / 100
			invoiced_paid = sum(
				flt(r.grand_total) - flt(r.outstanding_amount)
				for r in frappe.get_all(
					"Sales Invoice",
					filters={"docstatus": 1, "name": ["in", _invoices_for_order(so_name)]},
					fields=["grand_total", "outstanding_amount"],
				)
			)
			received = max(flt(so.advance_paid), invoiced_paid)
			cleared = 1 if received + 0.01 >= required else 0
	frappe.db.set_value("Repair Order", repair_order, "payment_cleared", cleared)


def _invoices_for_order(so_name):
	return list(
		set(
			frappe.get_all(
				"Sales Invoice Item", filters={"sales_order": so_name, "docstatus": 1}, pluck="parent"
			)
		)
	) or [""]


def delivery_note_on_submit(doc, method=None):
	"""D7 / D9: dispatched -> Repair Order 'Dispatched', ticket 'Resolved'.
	The dispatch e-mail with PDF is a Notification on Delivery Note (config).
	"""
	if not doc.get("custom_repair_order"):
		return
	set_repair_status(doc.custom_repair_order, "Dispatched", delivery_note=doc.name)

	if doc.get("custom_replaces_serial"):
		_carry_warranty_to_replacement(doc)

	ticket = frappe.db.get_value("Repair Order", doc.custom_repair_order, "helpdesk_ticket")
	if ticket:
		resolve_ticket(ticket, _("Unit dispatched to customer on Delivery Note {0}.").format(doc.name))


def _row_serials(row):
	"""Serials on a stock row, whether typed in serial_no or held in a bundle."""
	typed = [s.strip() for s in (row.get("serial_no") or "").split("\n") if s.strip()]
	return typed or get_serials_from_bundle(row.get("serial_and_batch_bundle"))


def _carry_warranty_to_replacement(dn):
	"""D7: the new serial inherits the old unit's sale details and, by
	setting, its remaining warranty (else a fresh warranty from dispatch)."""
	old = frappe.db.get_value(
		"Serial No",
		dn.custom_replaces_serial,
		["custom_invoice_no", "custom_invoice_date", "custom_warranty_end"],
		as_dict=True,
	)
	keep_old_warranty = get_settings().replacement_keeps_old_warranty
	new_serials = []
	for row in dn.items:
		warranty_end = (
			old.custom_warranty_end
			if keep_old_warranty
			else compute_warranty_end(row.item_code, dn.posting_date)
		)
		for serial in _row_serials(row):
			new_serials.append(serial)
			frappe.db.set_value(
				"Serial No",
				serial,
				{
					"custom_replaces_serial": dn.custom_replaces_serial,
					"custom_sold_to": dn.customer,
					"custom_invoice_no": old.custom_invoice_no,
					"custom_invoice_date": old.custom_invoice_date,
					"custom_warranty_end": warranty_end,
				},
			)
	if new_serials:
		frappe.db.set_value("Repair Order", dn.custom_repair_order, "replacement_serial", new_serials[0])
