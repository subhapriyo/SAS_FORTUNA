"""Extra data for the portal detail pages (/orders/<name>, /invoices/<name>, ...).

ERPNext renders all of these pages with one stock template (templates/pages/order.html). It
does not expose the extra header fields we need, and it prints only the item code (no item
name). Rather than copy that template into this app (and have to keep it in sync with ERPNext),
portal.js asks this method for the data and draws it into the stock markup.

Everything returned is read server-side, after a permission check, and formatted with the
site's date format / the document currency.
"""

import frappe
from frappe import _
from frappe.utils import fmt_money, formatdate

_PO = [
	("Customer's Purchase Order", ("po_no",), "text"),
	("Customer's Purchase Order Date", ("po_date",), "date"),
]

# portal doctype -> [(label, (fieldname candidates), kind)]. The first candidate that exists on the
# doctype is used; if none exists, the doctype's fields are searched for one with the same label.
DETAIL_FIELDS = {
	"Supplier Quotation": [
		("Quotation Number", ("quotation_number",), "text"),
		("Valid Till", ("valid_till",), "date"),
	],
	"Purchase Order": [("Order Confirmation No", ("order_confirmation_no",), "text")],
	"Purchase Invoice": [
		("Supplier Invoice No", ("bill_no",), "text"),
		("Supplier Invoice Date", ("bill_date",), "date"),
	],
	# "Customer Enquiry" is a custom field: confirm its exact fieldname on your site
	"Quotation": [("Customer Enquiry", ("custom_customer_enquiry", "customer_enquiry"), "text")],
	"Sales Order": _PO,
	"Sales Invoice": _PO,
	"Delivery Note": _PO,
}


def _resolve_field(meta, candidates, label):
	for fieldname in candidates:
		if meta.has_field(fieldname):
			return fieldname
	for df in meta.fields:
		if (df.label or "").strip().lower() == label.lower():
			return df.fieldname
	return None


def _can_read(doc):
	user = frappe.session.user
	if user == "Guest":
		return False
	# same check the stock order page applies (ERPNext registers has_website_permission for all
	# of these doctypes); desk users with normal read permission are allowed too
	return bool(
		frappe.has_permission(doc.doctype, "read", doc=doc) or frappe.has_website_permission(doc, "read")
	)


@frappe.whitelist()
def get_detail_extras(doctype, name):
	"""Return {"meta": [...], "items": [...], "missing": [...]} for one portal detail page.

	meta    - [{fieldname, label, value}] header lines; empty values are left out
	items   - one entry per item row, in document order: item_code, item_name, rate, amount
	          (rate / amount carry the currency symbol)
	missing - labels whose field does not exist on the doctype (custom field still to create)
	"""
	if doctype not in DETAIL_FIELDS:
		frappe.throw(_("Not allowed"), frappe.PermissionError)

	doc = frappe.get_doc(doctype, name)
	if not _can_read(doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	meta = frappe.get_meta(doctype)
	lines, missing = [], []
	for label, candidates, kind in DETAIL_FIELDS[doctype]:
		fieldname = _resolve_field(meta, candidates, label)
		if not fieldname:
			missing.append(label)
			continue
		value = doc.get(fieldname)
		if value in (None, ""):
			continue
		value = formatdate(value) if kind == "date" else str(value).strip()
		if value:
			lines.append({"fieldname": fieldname, "label": _(label), "value": value})

	currency = doc.get("currency")
	items = [
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"rate": fmt_money(row.get("rate") or 0, currency=currency),
			"amount": fmt_money(row.get("amount") or 0, currency=currency),
		}
		for row in doc.get("items") or []
	]
	return {"meta": lines, "items": items, "missing": missing}
