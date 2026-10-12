"""Stamp sale details on each Serial No when goods are sold  (N4, N5, F1).

Why: the scope's warranty rule starts from the INVOICE date, and from v15
onwards Serial No no longer remembers its selling document. Stamping it at
sale time makes every later lookup a single, fast read.
"""

import frappe

from sas_fortuna.support.utils import compute_warranty_end, find_sale_for_serial, get_serials_from_bundle


def sales_invoice_on_submit(doc, method=None):
	if doc.is_return:
		return
	for row in doc.items:
		bundle = row.serial_and_batch_bundle
		# Invoice made from a Delivery Note: the serials sit on the DN row.
		if not bundle and row.dn_detail:
			bundle = frappe.db.get_value("Delivery Note Item", row.dn_detail, "serial_and_batch_bundle")
		_stamp(get_serials_from_bundle(bundle), row.item_code, doc.name, doc.posting_date, doc.customer)


def delivery_note_on_submit(doc, method=None):
	# Repair dispatches and returns are not sales; repair.py handles those.
	if doc.is_return or doc.get("custom_repair_order"):
		return
	for row in doc.items:
		serials = get_serials_from_bundle(row.serial_and_batch_bundle)
		if row.against_sales_invoice:  # DN made after the invoice
			inv_date = frappe.db.get_value("Sales Invoice", row.against_sales_invoice, "posting_date")
			_stamp(serials, row.item_code, row.against_sales_invoice, inv_date, doc.customer)
		else:  # invoice will follow; remember the customer for now
			for serial in serials:
				frappe.db.set_value("Serial No", serial, "custom_sold_to", doc.customer)


def _stamp(serials, item_code, invoice_no, invoice_date, customer):
	warranty_end = compute_warranty_end(item_code, invoice_date)
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
	"""
	for serial in frappe.get_all(
		"Serial No", filters={"custom_invoice_date": ["is", "not set"]}, pluck="name"
	):
		sale = find_sale_for_serial(serial)
		if not sale.invoice_date:
			continue
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
