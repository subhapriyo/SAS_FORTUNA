"""Shared lookups for Fortuna support, repair and AMC.

Everything in this file only READS data, so it is safe to call from
doc-event hooks, whitelisted buttons and scheduled jobs alike.
"""

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.utils import add_days, cint, getdate, today

SUPPORT_WARRANTY = "Warranty"
SUPPORT_AMC = "AMC"
SUPPORT_PAID = "Paid Service"

# Fortuna's normal warranty is 1 year.
STANDARD_WARRANTY_DAYS = 365


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def get_settings():
	"""Return the single 'Fortuna Support Settings' document (cached)."""
	return frappe.get_cached_doc("Fortuna Support Settings", "Fortuna Support Settings")


def require_setting(fieldname):
	"""Read one setting and stop with a clear message if it is blank.

	New implementers usually forget a setting; this turns a cryptic
	'NoneType' error into 'please fill X in Fortuna Support Settings'.
	"""
	value = get_settings().get(fieldname)
	if not value:
		label = frappe.get_meta("Fortuna Support Settings").get_label(fieldname)
		frappe.throw(_("Please set <b>{0}</b> in Fortuna Support Settings.").format(label))
	return value


# ---------------------------------------------------------------------------
# Serial No <-> sale lookup  (N4)
# ---------------------------------------------------------------------------
def get_serials_from_bundle(bundle):
	"""List serial numbers inside a Serial and Batch Bundle."""
	if not bundle:
		return []
	rows = frappe.get_all("Serial and Batch Entry", filters={"parent": bundle}, pluck="serial_no")
	return [s for s in rows if s]


def find_sale_for_serial(serial_no):
	"""Find which invoice sold this serial, and to whom.

	1. Fast path: the details stamped on the Serial No when the sale was
	   submitted (see sales.py).
	2. Fallback for older sales: search the latest outward Serial and Batch
	   Bundle on a Sales Invoice or Delivery Note. From v15 onwards the
	   Serial No itself no longer stores the selling document.

	Returns a dict with invoice_no, invoice_date, customer, basis
	("Sales Invoice" / "Delivery Note" / None when never sold).
	"""
	stamped = frappe.db.get_value(
		"Serial No",
		serial_no,
		["custom_invoice_no", "custom_invoice_date", "custom_sold_to"],
		as_dict=True,
	)
	if stamped and stamped.custom_invoice_date:
		return frappe._dict(
			invoice_no=stamped.custom_invoice_no,
			invoice_date=getdate(stamped.custom_invoice_date),
			customer=stamped.custom_sold_to,
			basis="Sales Invoice",
		)

	sbb = frappe.qb.DocType("Serial and Batch Bundle")
	sbe = frappe.qb.DocType("Serial and Batch Entry")
	last_out = (
		frappe.qb.from_(sbe)
		.join(sbb)
		.on(sbe.parent == sbb.name)
		.select(sbb.voucher_type, sbb.voucher_no)
		.where(
			(sbe.serial_no == serial_no)
			& (sbb.docstatus == 1)
			& (sbb.is_cancelled == 0)
			& (sbb.type_of_transaction == "Outward")
			& (sbb.voucher_type.isin(["Sales Invoice", "Delivery Note"]))
		)
		.orderby(sbb.creation, order=Order.desc)
		.limit(1)
		.run(as_dict=True)
	)
	if not last_out:
		return frappe._dict(invoice_no=None, invoice_date=None, customer=None, basis=None)

	voucher_type, voucher_no = last_out[0].voucher_type, last_out[0].voucher_no

	if voucher_type == "Sales Invoice":
		inv = frappe.db.get_value("Sales Invoice", voucher_no, ["posting_date", "customer"], as_dict=True)
		return frappe._dict(
			invoice_no=voucher_no, invoice_date=inv.posting_date, customer=inv.customer, basis="Sales Invoice"
		)

	# Sold through a Delivery Note: look for the invoice made from it.
	invoice_no = frappe.db.get_value(
		"Sales Invoice Item", {"delivery_note": voucher_no, "docstatus": 1}, "parent"
	)
	if invoice_no:
		inv = frappe.db.get_value("Sales Invoice", invoice_no, ["posting_date", "customer"], as_dict=True)
		return frappe._dict(
			invoice_no=invoice_no, invoice_date=inv.posting_date, customer=inv.customer, basis="Sales Invoice"
		)

	# Delivered but not yet invoiced: use the delivery date (flagged in 'basis').
	dn = frappe.db.get_value("Delivery Note", voucher_no, ["posting_date", "customer"], as_dict=True)
	return frappe._dict(
		invoice_no=None, invoice_date=dn.posting_date, customer=dn.customer, basis="Delivery Note"
	)


# ---------------------------------------------------------------------------
# Warranty / AMC / Paid classification  (C2, N5)
# ---------------------------------------------------------------------------
def compute_warranty_end(item_code, start_date):
	"""Invoice date + warranty days. None when there is no sale date.

	The Item's own 'Warranty Period (in days)' wins; otherwise the
	standard warranty from settings (1 year by default).
	"""
	if not start_date:
		return None
	days = cint(frappe.db.get_value("Item", item_code, "warranty_period")) or get_standard_warranty_days()
	return getdate(add_days(start_date, days))


def get_standard_warranty_days():
	"""Standard warranty from settings; 365 when the setting is blank."""
	return cint(get_settings().get("default_warranty_days")) or STANDARD_WARRANTY_DAYS


def get_serial_coverage(serial_no, on_date=None):
	"""Classify a serial as Warranty, AMC or Paid Service on a given date.

	Rule from the scope (C2 + N5), warranty wins when both are active:
	    warranty end >= date  -> Warranty
	    AMC expiry   >= date  -> AMC
	    otherwise / no sale   -> Paid Service
	"""
	on_date = getdate(on_date or today())
	serial = frappe.db.get_value(
		"Serial No", serial_no, ["item_code", "amc_expiry_date", "custom_warranty_end"], as_dict=True
	)
	if not serial:
		frappe.throw(_("Serial No {0} does not exist.").format(serial_no))

	sale = find_sale_for_serial(serial_no)
	# A stored warranty end wins: it may have been carried over from a
	# replaced unit (D7), so do not recompute it.
	warranty_end = getdate(serial.custom_warranty_end) if serial.custom_warranty_end else None
	if not warranty_end:
		warranty_end = compute_warranty_end(serial.item_code, sale.invoice_date)
	amc_expiry = getdate(serial.amc_expiry_date) if serial.amc_expiry_date else None

	if warranty_end and warranty_end >= on_date:
		support_type = SUPPORT_WARRANTY
	elif amc_expiry and amc_expiry >= on_date:
		support_type = SUPPORT_AMC
	else:
		support_type = SUPPORT_PAID

	return frappe._dict(
		serial_no=serial_no,
		item_code=serial.item_code,
		customer=sale.customer,
		invoice_no=sale.invoice_no,
		invoice_date=sale.invoice_date,
		sale_basis=sale.basis,
		warranty_end=warranty_end,
		amc_expiry=amc_expiry,
		support_type=support_type,
	)


@frappe.whitelist()
def get_serial_details(serial_no):
	"""Button/field helper for forms: returns the coverage dict as JSON."""
	frappe.has_permission("Serial No", "read", throw=True)
	return get_serial_coverage(serial_no)


# ---------------------------------------------------------------------------
# Helpdesk <-> ERPNext customer
# ---------------------------------------------------------------------------
def get_erpnext_customer(hd_customer):
	"""Map a Helpdesk 'HD Customer' to its ERPNext 'Customer' (or None)."""
	if not hd_customer:
		return None
	return frappe.db.get_value("HD Customer", hd_customer, "custom_erpnext_customer")


def get_hd_customer(customer):
	"""Reverse map: ERPNext Customer -> HD Customer name (or None)."""
	if not customer:
		return None
	return frappe.db.get_value("HD Customer", {"custom_erpnext_customer": customer}, "name")


def is_helpdesk_agent(user=None):
	"""True when the user is an active Helpdesk agent (not a portal customer)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(frappe.db.exists("HD Agent", {"user": user, "is_active": 1}))
