"""Stamp sale details on each Serial No when goods are sold  (N4, N5, F1).

Why: the scope's warranty rule starts from the INVOICE date, and from v15
onwards Serial No no longer remembers its selling document. Stamping it at
sale time makes every later lookup a single, fast read.

Extended warranty (Fortuna): sold as a service line on the same sale bill. The
line's Item carries "Extended Warranty (Months)"; those months are added to the
warranty of every unit on that invoice.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, getdate

from sas_fortuna.support.utils import compute_warranty_end, find_sale_for_serial, get_serials_from_bundle


def sales_invoice_on_submit(doc, method=None):
	if doc.is_return:
		return
	extra_months = extended_warranty_months([row.item_code for row in doc.items])
	for row in doc.items:
		bundle = row.serial_and_batch_bundle
		# Invoice made from a Delivery Note: the serials sit on the DN row.
		if not bundle and row.dn_detail:
			bundle = frappe.db.get_value("Delivery Note Item", row.dn_detail, "serial_and_batch_bundle")
		_stamp(
			get_serials_from_bundle(bundle),
			row.item_code,
			doc.name,
			doc.posting_date,
			doc.customer,
			extra_months=extra_months,
		)


def delivery_note_on_submit(doc, method=None):
	# Repair dispatches and returns are not sales; repair.py handles those.
	if doc.is_return or doc.get("custom_repair_order"):
		return
	for row in doc.items:
		serials = get_serials_from_bundle(row.serial_and_batch_bundle)
		if row.against_sales_invoice:  # DN made after the invoice
			inv_date = frappe.db.get_value("Sales Invoice", row.against_sales_invoice, "posting_date")
			invoice_items = frappe.get_all(
				"Sales Invoice Item", filters={"parent": row.against_sales_invoice}, pluck="item_code"
			)
			_stamp(
				serials,
				row.item_code,
				row.against_sales_invoice,
				inv_date,
				doc.customer,
				extra_months=extended_warranty_months(invoice_items),
			)
		else:  # invoice will follow; remember the customer for now
			for serial in serials:
				frappe.db.set_value("Serial No", serial, "custom_sold_to", doc.customer)


def serial_no_validate(doc, method=None):
	"""SIM validity cannot end before the SIM was activated. A new validity (the yearly
	recharge) starts the customer reminders afresh (tasks.send_sim_renewal_reminders)."""
	start, end = doc.get("custom_sim_activation_date"), doc.get("custom_sim_valid_till")
	if start and end and getdate(end) < getdate(start):
		frappe.throw(_("SIM Valid Till cannot be before SIM Activation Date."))
	if not doc.is_new() and doc.has_value_changed("custom_sim_valid_till"):
		doc.custom_sim_reminders_sent = 0


def extended_warranty_months(item_codes):
	"""Largest 'Extended Warranty (Months)' among the items on one bill; 0 when none.
	Largest, not the sum: two extended-warranty lines for two units extend each unit once."""
	codes = list({c for c in item_codes if c})
	if not codes or not frappe.get_meta("Item").has_field("custom_extended_warranty_months"):
		return 0
	months = frappe.get_all("Item", filters={"name": ["in", codes]}, pluck="custom_extended_warranty_months")
	return max((cint(m) for m in months), default=0)


def _stamp(serials, item_code, invoice_no, invoice_date, customer, extra_months=0):
	warranty_end = compute_warranty_end(item_code, invoice_date)
	if warranty_end and extra_months:
		warranty_end = getdate(add_months(warranty_end, extra_months))
	for serial in serials:
		frappe.db.set_value(
			"Serial No",
			serial,
			{
				"custom_invoice_no": invoice_no,
				"custom_invoice_date": invoice_date,
				"custom_sold_to": customer,
				"custom_warranty_end": warranty_end,
			},
		)


def backfill_serials():
	"""One-time: stamp serials sold before this app was installed.
	bench --site fortuna.localhost execute sas_fortuna.support.sales.backfill_serials
	Safe to re-run: only serials without an invoice date are looked at.
	Returns a count, which bench prints, e.g. {"checked": 3, "stamped": 1}.
	"""
	serials = frappe.get_all("Serial No", filters={"custom_invoice_date": ["is", "not set"]}, pluck="name")
	stamped = 0
	for serial in serials:
		sale = find_sale_for_serial(serial)
		if not sale.invoice_date:
			continue  # never sold (or sold on a DN not yet invoiced)
		stamped += 1
		item_code = frappe.db.get_value("Serial No", serial, "item_code")
		frappe.db.set_value(
			"Serial No",
			serial,
			{
				"custom_invoice_no": sale.invoice_no,
				"custom_invoice_date": sale.invoice_date if sale.invoice_no else None,
				"custom_sold_to": sale.customer,
				"custom_warranty_end": compute_warranty_end(item_code, sale.invoice_date),
			},
		)
	frappe.db.commit()
	return {"checked": len(serials), "stamped": stamped}
