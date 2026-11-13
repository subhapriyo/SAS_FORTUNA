"""AMC life cycle on Sales Order  (F3, F5, F8).

The AMC 'contract' is a normal Sales Order with:
  custom_is_amc, custom_amc_start_date, custom_amc_end_date,
  custom_amc_status, custom_covered_items (child: AMC Covered Item)
Quotation carries the same fields, so standard 'Make Sales Order' copies
the header fields (F2 -> F3); sales_order_validate copies Covered Items.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

STATUS_ACTIVE, STATUS_RENEWAL, STATUS_ENDED = "Active", "Renewal Quoted", "Ended"


# ---------------------------------------------------------------------------
# F2 -> F3  Carry Covered Items from Quotation to Sales Order
# ---------------------------------------------------------------------------
def sales_order_validate(doc, method=None):
	"""Copy the 'Covered Items' table from the source Quotation.

	The Quotation -> Sales Order mapper (ERPNext's, and fortuna_erp's override
	which calls it) copies same-named header fields, but I believe it only
	copies child tables it is told about (items, taxes, ...), so our custom
	table would be lost. This fills it once, only while the order is a draft
	and the table is still empty; harmless if the mapper already copied it.
	"""
	if doc.docstatus != 0 or not doc.get("custom_is_amc") or doc.get("custom_covered_items"):
		return
	quotation = next((row.prevdoc_docname for row in doc.items if row.prevdoc_docname), None)
	if not quotation:
		return
	for row in frappe.get_all(
		"AMC Covered Item",
		filters={"parenttype": "Quotation", "parent": quotation},
		fields=["serial_no", "item_code", "site", "software_version", "bom_ref"],
		order_by="idx",
	):
		doc.append("custom_covered_items", row)


# ---------------------------------------------------------------------------
# Rules for AMC quotations and orders (Quotation + Sales Order)
# ---------------------------------------------------------------------------
def amc_validate(doc, method=None):
	"""Period and covered units must make sense before anything is sent."""
	if not doc.get("custom_is_amc"):
		return
	# Fortuna's AMC terms and "100% against Pro-Forma" payment terms, where still blank.
	if doc.docstatus == 0:
		from sas_fortuna.support.repair import apply_quotation_terms
		from sas_fortuna.support.utils import get_settings

		apply_quotation_terms(doc, get_settings().get("amc_terms"))
	start, end = doc.get("custom_amc_start_date"), doc.get("custom_amc_end_date")
	if start and end and getdate(end) <= getdate(start):
		frappe.throw(_("AMC End Date must be after AMC Start Date."))
	seen = set()
	for row in doc.get("custom_covered_items") or []:
		if row.serial_no in seen:
			frappe.throw(_("Serial No {0} is listed twice in Covered Items.").format(row.serial_no))
		seen.add(row.serial_no)


def amc_before_submit(doc, method=None):
	"""An AMC needs covered units, and a unit cannot be under two AMCs at once."""
	if not doc.get("custom_is_amc"):
		return
	if not doc.get("custom_covered_items"):
		frappe.throw(_("Add the units this AMC covers in Covered Items."))
	if doc.doctype == "Sales Order":
		_check_no_overlapping_amc(doc)


def _check_no_overlapping_amc(so):
	serials = [row.serial_no for row in so.custom_covered_items]
	clash = frappe.db.sql(
		"""
		select ci.serial_no, so.name
		from `tabAMC Covered Item` ci
		join `tabSales Order` so on so.name = ci.parent and ci.parenttype = 'Sales Order'
		where so.docstatus = 1 and so.custom_is_amc = 1 and so.name != %(name)s
			and ifnull(so.custom_amc_status, '') != %(ended)s
			and ci.serial_no in %(serials)s
			and so.custom_amc_start_date <= %(end)s and so.custom_amc_end_date >= %(start)s
		limit 1
		""",
		{
			"name": so.name,
			"ended": STATUS_ENDED,
			"serials": serials,
			"start": so.custom_amc_start_date,
			"end": so.custom_amc_end_date,
		},
	)
	if clash:
		frappe.throw(
			_("Serial No {0} is already under AMC {1} for part of this period.").format(
				clash[0][0], clash[0][1]
			)
		)


# ---------------------------------------------------------------------------
# F5  Activate on payment
# ---------------------------------------------------------------------------
def payment_entry_on_submit(doc, method=None):
	for so in _orders_from_payment(doc):
		if frappe.db.get_value("Sales Order", so, "custom_is_amc") and _is_paid(so):
			activate_amc(so)


def _orders_from_payment(pe):
	orders = set()
	for ref in pe.references:
		if ref.reference_doctype == "Sales Order":
			orders.add(ref.reference_name)
		elif ref.reference_doctype == "Sales Invoice":
			orders.update(
				frappe.get_all(
					"Sales Invoice Item",
					filters={"parent": ref.reference_name, "sales_order": ["is", "set"]},
					pluck="sales_order",
				)
			)
	return orders


def _is_paid(so_name):
	"""Paid in full: by advance, or the order is fully billed with nothing outstanding."""
	so = frappe.db.get_value(
		"Sales Order", so_name, ["grand_total", "advance_paid", "per_billed"], as_dict=True
	)
	if flt(so.advance_paid) + 0.01 >= flt(so.grand_total):
		return True
	if flt(so.per_billed) < 100:
		return False
	invoices = set(
		frappe.get_all("Sales Invoice Item", filters={"sales_order": so_name, "docstatus": 1}, pluck="parent")
	)
	outstanding = sum(
		flt(frappe.db.get_value("Sales Invoice", inv, "outstanding_amount")) for inv in invoices
	)
	return outstanding <= 0.01


def activate_amc(sales_order):
	"""Stamp AMC start / expiry on every covered serial. Safe to run twice."""
	so = frappe.get_doc("Sales Order", sales_order)
	if so.custom_amc_status == STATUS_ACTIVE:
		return
	for row in so.custom_covered_items:
		frappe.db.set_value(
			"Serial No",
			row.serial_no,
			{
				"custom_amc_start_date": so.custom_amc_start_date,
				"amc_expiry_date": so.custom_amc_end_date,  # standard field read by C2
				"custom_amc_contract": so.name,
				"custom_amc_status": STATUS_ACTIVE,
			},
		)
	so.db_set("custom_amc_status", STATUS_ACTIVE)
	frappe.msgprint(_("AMC activated on {0} serial(s).").format(len(so.custom_covered_items)), alert=True)


# ---------------------------------------------------------------------------
# F8  Renew / End
# ---------------------------------------------------------------------------
@frappe.whitelist()
def renew_amc(sales_order):
	"""Draft a renewal Quotation for the next period with the same coverage."""
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("write")
	period_days = date_diff(so.custom_amc_end_date, so.custom_amc_start_date)
	new_start = add_days(so.custom_amc_end_date, 1)

	qtn = frappe.new_doc("Quotation")
	qtn.update(
		{
			"company": so.company,
			"quotation_to": "Customer",
			"party_name": so.customer,
			"custom_is_amc": 1,
			"custom_amc_start_date": new_start,
			"custom_amc_end_date": add_days(new_start, period_days),
			"custom_renewal_of": so.name,
		}
	)
	for item in so.items:
		qtn.append("items", {"item_code": item.item_code, "qty": item.qty})  # price list sets new rates
	for row in so.custom_covered_items:
		qtn.append("custom_covered_items", row.as_dict(no_default_fields=True))
	# Keep the dealer on the renewal: fortuna_erp assigns the quotation to the
	# dealer's user from Quotation.custom_dealer, and Dealer users only see
	# documents assigned to them.
	if so.get("sales_partner") and qtn.meta.has_field("custom_dealer"):
		qtn.custom_dealer = so.sales_partner
	qtn.insert()

	so.db_set("custom_amc_status", STATUS_RENEWAL)
	return qtn.name


@frappe.whitelist()
def end_amc(sales_order):
	"""Customer declined renewal: mark contract and serials as Ended."""
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("write")
	for row in so.custom_covered_items:
		frappe.db.set_value("Serial No", row.serial_no, "custom_amc_status", STATUS_ENDED)
	so.db_set("custom_amc_status", STATUS_ENDED)
