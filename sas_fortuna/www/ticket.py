"""Customer portal: one Helpdesk ticket at /tickets/<name>.  Template: www/ticket.html

How the page is reached
    wiring.website_route_rules maps "/tickets/<name>" to this page and puts <name> in
    frappe.form_dict.name. The list it comes from is /tickets (support/portal_tickets.py).

Who may open it
    A customer: exactly the tickets their /tickets list shows (same filter, ticket_filters()).
    A Desk user: any ticket they can read in Desk. Guests are asked to log in.

What it shows (read-only)
    Status + hint, details, the unit, the linked repair, the resolution and the e-mail
    conversation. Agents' internal comments (HD Ticket Comment) are never shown.
    Replying and raising a new ticket happen in Helpdesk's own customer pages
    (/helpdesk/my-tickets), so Helpdesk keeps its SLA clock, notifications and attachments.
"""

import frappe
from frappe import _
from frappe.utils import format_datetime, formatdate, sanitize_html

from sas_fortuna.support.portal_repairs import STATUS_COLORS as REPAIR_COLORS
from sas_fortuna.support.portal_tickets import NEW_TICKET_URL, STATUS_COLORS, ticket_filters

no_cache = 1  # always fresh: replies arrive while the customer watches

# What each Helpdesk status means for the customer. Translated when the page renders.
STATUS_HINT = {
	"Open": "We have your ticket and will get back to you soon.",
	"Replied": "We have replied. Please answer so we can continue.",
	"Paused": "This ticket is on hold for now.",
	"Resolved": "We have resolved this ticket. Reply if the problem is still there.",
	"Closed": "This ticket is closed.",
}
RESOLVED = ("Resolved", "Closed")


def get_context(context):
	doc = _load_ticket()

	context.no_cache = 1
	context.show_sidebar = True  # the portal left menu
	context.doc = doc
	context.title = doc.subject or doc.name
	context.parents = [{"label": _("Tickets"), "route": "tickets"}]  # breadcrumb back to the list

	# Header
	context.status_color = STATUS_COLORS.get(doc.status, "gray")
	context.status_hint = _(STATUS_HINT[doc.status]) if doc.status in STATUS_HINT else ""
	context.created_on = formatdate(doc.opening_date or doc.creation)
	context.new_ticket_url = NEW_TICKET_URL
	context.reply_url = _reply_url(doc)

	# Cards
	context.details = _rows(
		(_("Ticket"), doc.name),
		(_("Type"), doc.ticket_type),
		(_("Priority"), doc.priority),
		(_("Raised by"), doc.raised_by),
	)
	context.unit = _rows(
		(_("Model"), doc.get("custom_product_model")),
		(_("Serial No"), doc.get("custom_serial_no")),
		(_("Cover"), doc.get("custom_support_type")),
		(_("Warranty until"), _date(doc.get("custom_warranty_end"))),
		(_("AMC until"), _date(doc.get("custom_amc_expiry"))),
	)
	context.repair = _repair(doc)
	context.resolution = sanitize_html(doc.resolution_details or "") if doc.status in RESOLVED else ""

	# Conversation (falls back to the description when there are no e-mails yet)
	context.messages = _conversation(doc)
	context.description = sanitize_html(doc.description or "")
	return context


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------
def _load_ticket():
	"""Return the HD Ticket, or stop with the right error."""
	name = frappe.form_dict.name
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view your tickets."), frappe.PermissionError)
	if not name or not frappe.db.exists("HD Ticket", name):
		raise frappe.DoesNotExistError(_("Ticket {0} not found").format(name))

	doc = frappe.get_doc("HD Ticket", name)
	own = ticket_filters()  # the same rule as the /tickets list
	if own is not None:
		allowed = all(doc.get(field) == value for field, value in own.items())
	else:
		allowed = frappe.has_permission("HD Ticket", "read", doc=doc)  # Desk users
	if not allowed:
		frappe.throw(_("You are not allowed to view this ticket."), frappe.PermissionError)
	return doc


def _reply_url(doc):
	"""Link to the ticket in Helpdesk's customer pages, if Helpdesk will let this user open it.

	Helpdesk lets only the person who raised it (or a manager of that customer) open it, so we ask
	Helpdesk's own rule instead of guessing; a colleague of the same company gets no button.
	"""
	from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import has_permission as helpdesk_can_open

	return f"/helpdesk/my-tickets/{doc.name}" if helpdesk_can_open(doc) else ""


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
def _rows(*rows):
	"""Keep only the (label, value) rows that have a value."""
	return [(label, value) for label, value in rows if value]


def _date(value):
	return formatdate(value) if value else None


def _repair(doc):
	"""The repair opened from this ticket, with its status, for a link to /repairs/<name>."""
	name = doc.get("custom_repair_order")
	if not name:
		return None
	status = frappe.db.get_value("Repair Order", name, "status")
	return {"name": name, "status": status, "color": REPAIR_COLORS.get(status, "gray")}


def _conversation(doc):
	"""E-mails on the ticket, oldest first. Messages from agents are labelled "Fortuna Support".
	HTML is sanitised: e-mail bodies come from outside."""
	staff = set(frappe.get_all("HD Agent", pluck="user"))
	messages = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "HD Ticket",
			"reference_name": doc.name,
			"communication_type": "Communication",
		},
		fields=["sender", "sender_full_name", "content", "creation"],
		order_by="creation asc",
	)
	return [
		{
			"from_us": m.sender in staff,
			"who": _("Fortuna Support") if m.sender in staff else (m.sender_full_name or m.sender),
			"when": format_datetime(m.creation, "dd-MM-yyyy HH:mm"),
			"content": sanitize_html(m.content or ""),
		}
		for m in messages
	]
