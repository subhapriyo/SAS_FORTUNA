"""Portal helpers shared by /repairs and its buttons  (P1, N7)."""

import frappe
from frappe import _


def get_portal_customer(user=None):
	"""Customer linked to the user's Contact (standard ERPNext portal link)."""
	contact = frappe.db.get_value("Contact", {"user": user or frappe.session.user}, "name")
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name",
	)


@frappe.whitelist()
def accept_quotation(quotation):
	"""Customer accepts: create a DRAFT Sales Order for Fortuna to confirm."""
	customer = get_portal_customer()
	qtn = frappe.db.get_value("Quotation", quotation, ["party_name", "docstatus", "status"], as_dict=True)
	if not qtn or qtn.party_name != customer or qtn.docstatus != 1 or qtn.status != "Open":
		frappe.throw(_("This quotation cannot be accepted."), frappe.PermissionError)

	so = _make_sales_order()(quotation)
	so.delivery_date = frappe.utils.add_days(frappe.utils.today(), 7)
	so.insert(ignore_permissions=True)
	so.add_comment("Comment", _("Accepted by customer on the portal."))
	return so.name


def _make_sales_order():
	"""ERPNext's Quotation -> Sales Order mapper, or the override another app
	registered for it (fortuna_erp overrides it), so portal orders follow the
	same rules as orders made in Desk."""
	path = "erpnext.selling.doctype.quotation.quotation.make_sales_order"
	overrides = frappe.get_hooks("override_whitelisted_methods") or {}
	return frappe.get_attr((overrides.get(path) or [path])[-1])
