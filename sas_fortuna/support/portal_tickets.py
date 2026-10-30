"""Customer portal list: /tickets  (the customer's Helpdesk tickets)

Why it exists
    The portal's old "Issues" page shows ERPNext's Support-module Issue, which ERPNext says it may
    drop in v17. Our support desk runs on Helpdesk tickets (HD Ticket), so /tickets shows those, in
    the same look as /orders and /repairs. It replaces "Issues" in the portal menu
    (setup/support_desk.py: _portal_menu) and does not use the Support module at all.

How it works
    1. wiring.website_route_rules maps /tickets to the "HD Ticket" list page.
    2. HD Ticket has no portal list of its own, so _attach() gives Helpdesk's ticket module the
       get_list_context() function Frappe looks for. (We add it at runtime; Helpdesk's files are
       not edited.)
    3. paginate_list_context() (portal/list_engine.py) adds columns, sorting, date range, status
       filter and numbered pages. The filter bar's options are in public/js/portal_support.js.
    4. "New ticket" and "Reply" open Helpdesk's own customer pages (/helpdesk/my-tickets), so SLA,
       notifications and attachments keep working exactly as Helpdesk intends.

Detail page: www/ticket.py (/tickets/<name>).
Safety: see ticket_filters() - the list and the detail page use the same rule.
"""

import importlib

import frappe
from frappe import _
from markupsafe import Markup, escape

from sas_fortuna.portal.list_engine import add_patch, paginate_list_context, register, search_filters
from sas_fortuna.support.portal import get_portal_customer

HELPDESK_TICKET_MODULE = "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket"
NEW_TICKET_URL = "/helpdesk/my-tickets/new"  # Helpdesk's own "new ticket" form for customers

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

# Table columns (format: templates/includes/sf_table_row.html).
COLUMNS = [
	{"label": "Subject / Ticket", "field": "subject", "kind": "name", "sub": "name", "sub_kind": "text"},
	{
		"label": "Unit",
		"field": "custom_serial_no",
		"kind": "stack",
		"sub": "custom_support_type",
		"sub_kind": "text",
	},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Last updated", "field": "modified", "kind": "ago"},
]
FIELDS = [
	"name",
	"subject",
	"status",
	"priority",
	"opening_date",
	"creation",
	"modified",
	"custom_serial_no",
	"custom_support_type",
]
# What the Search box looks in (placeholder text: public/js/portal_support.js).
SEARCH_FIELDS = ["subject", "name", "custom_serial_no", "custom_product_model"]

# Status pill colours for Helpdesk statuses (HD Ticket Status). "Replied" = we answered and are
# waiting for the customer.
STATUS_COLORS = {
	"Open": "orange",
	"Replied": "blue",
	"Paused": "yellow",
	"Resolved": "green",
	"Closed": "gray",
}

# Sorting, date range and paging (see list_engine.register).
register(
	"HD Ticket",
	default="creation desc",  # newest first
	sort={"creation", "modified", "status", "priority", "name"},
	paginate=True,
	date_field="opening_date",
)


# ---------------------------------------------------------------------------
# Who sees which tickets (used by the list AND the detail page)
# ---------------------------------------------------------------------------
def ticket_filters(user=None):
	"""Filters that limit HD Ticket to what this portal user may see.

	- A user linked to a Customer sees every ticket of that Customer (their colleagues' too).
	  Tickets get their Customer from the serial number or from the sender (hd_ticket.py).
	- A portal (website) user without a Customer sees only the tickets they raised.
	- Desk users get None: they work in /helpdesk, and the detail page uses Desk permissions.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		return None
	customer = get_portal_customer(user)
	if customer:
		return {"custom_erpnext_customer": customer}
	if frappe.db.get_value("User", user, "user_type") == "Website User":
		return {"raised_by": user}
	return None


# ---------------------------------------------------------------------------
# Query and page settings
# ---------------------------------------------------------------------------
def get_ticket_list(doctype, txt, filters, limit_start, limit_page_length=20, order_by=None, **kwargs):
	"""Helpdesk tickets of the logged-in customer only (empty for Desk users)."""
	from frappe.www.list import get_list

	own = ticket_filters()
	if own is None:
		return []
	if filters is None:
		filters = {}
	# Change the dict in place: the list engine reuses it to count the total for the pager.
	filters.update(own)
	return get_list(
		doctype,
		None,  # the search text is handled by or_filters below
		filters,
		limit_start,
		limit_page_length,
		ignore_permissions=True,  # safe: limited by ticket_filters() just above
		fields=FIELDS,
		order_by=order_by or "creation desc",
		or_filters=search_filters(doctype, txt, SEARCH_FIELDS),
	)


def list_context(context=None):
	"""Settings for Frappe's portal list page (Frappe calls this as HD Ticket's get_list_context)."""
	new_ticket_button = Markup(
		'<p class="sf-new-ticket"><a class="btn btn-primary btn-sm" href="{}">{}</a></p>'
	).format(NEW_TICKET_URL, escape(_("New ticket")))
	return {
		"title": _("Tickets"),
		"get_list": get_ticket_list,
		"show_sidebar": True,  # portal left menu
		"show_search": True,
		"no_breadcrumbs": True,
		"introduction": new_ticket_button,  # shown above the list by frappe/www/portal.html
		"no_result_message": _("You have not raised any tickets yet."),
		"sf_status_colors": STATUS_COLORS,  # read by sf_table_row.html
	}


# ---------------------------------------------------------------------------
# Wiring (applied once per worker by list_engine.apply())
# ---------------------------------------------------------------------------
def _attach():
	"""Give Helpdesk's ticket module the get_list_context() Frappe needs to serve a portal list.
	Must run before paginate_list_context's patch below; patches run in the order they are added."""
	module = importlib.import_module(HELPDESK_TICKET_MODULE)
	if not hasattr(module, "get_list_context"):  # if a future Helpdesk ships one, leave it alone
		module.get_list_context = list_context


add_patch(_attach)
paginate_list_context(HELPDESK_TICKET_MODULE, get_list=get_ticket_list, columns=COLUMNS)
