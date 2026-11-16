"""Portal helpers shared by /repairs, /tickets and their detail pages  (P1, N7).

	get_portal_customer()    which Customer the logged-in portal user belongs to
	accept_quotation()       the "Accept quotation" button on /repairs/<name>
	customer_ticket_types()  choices for "Ticket Type" on Helpdesk's New ticket form
	customer_serials()       choices for "Serial No" on that form: the customer's own units only

The last two are set as the fields' url_method on Helpdesk's "Default" ticket template
(setup/support_desk.py: _helpdesk_ticket_form).
"""

import frappe
from frappe import _


def get_portal_customer(user=None):
	"""The portal user's Customer: the Customer's Portal Users table (what ERPNext's own portal
	pages use), else the Customer linked to the user's Contact."""
	user = user or frappe.session.user
	customer = frappe.db.get_value("Portal User", {"parenttype": "Customer", "user": user}, "parent")
	if customer:
		return customer
	contact = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name",
	)


@frappe.whitelist()
def customer_ticket_types():
	"""Ticket types a customer can pick: those routed to a team (Fortuna Support Settings > Team
	Routing), so every portal ticket reaches the right team and gets an agent."""
	from sas_fortuna.support.utils import get_settings

	return [row.ticket_type for row in get_settings().team_routing if row.ticket_type]


@frappe.whitelist()
def ticket_subjects(ticket_type=None):
	"""Subject dropdown on the New Ticket form: active subjects of this ticket type, Others last."""
	from sas_fortuna.sas_fortuna.doctype.ticket_subject.ticket_subject import subjects_for

	return subjects_for(ticket_type)


@frappe.whitelist()
def ticket_subjects_by_type():
	"""All ticket types' Subject choices at once ({type: [..., "Others"]}); the New Ticket form
	loads them when it opens, so picking a ticket type fills the dropdown without waiting."""
	from sas_fortuna.sas_fortuna.doctype.ticket_subject.ticket_subject import subjects_by_type

	return subjects_by_type()


@frappe.whitelist()
def customer_serials():
	"""The logged-in customer's units, as "serial · model" choices. Never another customer's."""
	customer = get_portal_customer()
	if not customer:
		return []
	rows = frappe.get_all(
		"Serial No",
		filters={"custom_sold_to": customer},
		fields=["name", "item_code"],
		order_by="name asc",
		limit=500,
		ignore_permissions=True,  # safe: only this customer's own units
	)
	return [{"label": f"{r.name} · {r.item_code}", "value": r.name} for r in rows]


@frappe.whitelist()
def accept_quotation(quotation):
	"""Customer accepts: create a DRAFT Sales Order for Fortuna to confirm."""
	customer = get_portal_customer()
	qtn = frappe.db.get_value("Quotation", quotation, ["party_name", "docstatus", "status"], as_dict=True)
	if not qtn or qtn.party_name != customer or qtn.docstatus != 1 or qtn.status != "Open":
		frappe.throw(_("This quotation cannot be accepted."), frappe.PermissionError)

	# Ownership is checked above. Building the order also reads Items, price
	# lists and taxes, which a portal customer may not read (v16 checks Item
	# permission while filling item details). Rather than open those to all
	# customers, build the order as the system, then hand control back.
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		so = _make_sales_order(quotation)
		so.delivery_date = frappe.utils.add_days(frappe.utils.today(), 7)
		for item in so.items:
			item.delivery_date = item.delivery_date or so.delivery_date
		so.insert(ignore_permissions=True)
		so.add_comment(
			"Comment", _("Accepted by customer on the portal ({0}).").format(user), comment_email=user
		)
	finally:
		frappe.set_user(user)
	return so.name


def _make_sales_order(quotation):
	"""Map the quotation to a Sales Order on the customer's behalf.

	The Desk mapper (and fortuna_erp's override of it) checks that the
	logged-in user may create Sales Orders, which a portal customer may not.
	The ownership check is done above, so use ERPNext's mapper with
	ignore_permissions, as ERPNext's own portal does, and repeat the two
	rules the Desk path adds: expired quotations are refused, and fortuna_erp
	copies the dealer (Quotation.custom_dealer) into Sales Partner.
	"""
	from erpnext.selling.doctype.quotation.quotation import _make_sales_order as map_quotation

	valid_till = frappe.db.get_value("Quotation", quotation, "valid_till")
	allow_expired = frappe.db.get_single_value(
		"Selling Settings", "allow_sales_order_creation_for_expired_quotation"
	)
	if valid_till and not allow_expired and frappe.utils.getdate(valid_till) < frappe.utils.getdate():
		frappe.throw(_("This quotation has expired. Please ask Fortuna for a new one."))

	so = map_quotation(quotation, ignore_permissions=True)
	dealer = (
		frappe.db.get_value("Quotation", quotation, "custom_dealer")
		if frappe.get_meta("Quotation").has_field("custom_dealer")
		else None
	)
	if dealer and not so.get("sales_partner"):
		so.sales_partner = dealer
	return so
