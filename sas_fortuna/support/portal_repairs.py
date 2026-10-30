"""Customer portal list: /repairs  (the customer's Repair Orders)

How it works
    1. wiring.website_route_rules maps /repairs to the "Repair Order" list page.
    2. Frappe's list page calls get_list_context() in repair_order.py, which returns
       list_context() below (title, our query, colours).
    3. paginate_list_context() (portal/list_engine.py) adds the table columns, sorting,
       date range, status filter and numbered pages - the same engine as /orders, /invoices.
    4. The filter bar above the table is drawn by public/js/portal.js, with this page's
       status list / sort fields from public/js/portal_support.js.

Detail page: www/repair.py (/repairs/<name>).
Safety: a customer only ever sees repairs of their own Customer (see get_repair_list).
"""

import frappe
from frappe import _

from sas_fortuna.portal.list_engine import paginate_list_context, register, search_filters
from sas_fortuna.support.portal import get_portal_customer

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

# Table columns (format: templates/includes/sf_table_row.html). Cover, complaint etc. are on
# the detail page, so the table stays readable on a laptop.
COLUMNS = [
	{"label": "Repair No / Date", "field": "name", "kind": "name", "sub": "creation", "sub_kind": "date"},
	{
		"label": "Unit / Serial No",
		"field": "product_model",
		"kind": "stack",
		"sub": "serial_no",
		"sub_kind": "text",
	},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Last updated", "field": "modified", "kind": "ago"},
]
FIELDS = ["name", "creation", "modified", "product_model", "serial_no", "status"]  # what the columns need
# What the Search box looks in (placeholder text: public/js/portal_support.js).
SEARCH_FIELDS = ["name", "serial_no", "product_model", "complaint"]

# Status pill colours, shared with the detail page (www/repair.py) and the ticket page.
STATUS_COLORS = {
	"Registered": "gray",
	"Unit Received": "blue",
	"Awaiting Payment": "orange",
	"In Repair": "blue",
	"Ready": "green",
	"Dispatched": "green",
	"Closed": "gray",
	"Cancelled": "red",
}

# Sorting, date range and paging (see list_engine.register for what each argument means).
register(
	"Repair Order",
	default="creation desc",  # newest first
	sort={"creation", "modified", "status", "name", "serial_no"},
	paginate=True,
	date_field="creation",  # "Filter by Date Range" applies to the date the repair was opened
)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------
def get_repair_list(doctype, txt, filters, limit_start, limit_page_length=20, order_by=None, **kwargs):
	"""Repair orders of the logged-in customer only (empty for anyone without a Customer)."""
	from frappe.www.list import get_list

	customer = get_portal_customer()
	if not customer:
		return []
	if filters is None:
		filters = {}
	# Change the dict in place: the list engine reuses it to count the total for the pager.
	filters["customer"] = customer
	return get_list(
		doctype,
		None,  # the search text is handled by or_filters below
		filters,
		limit_start,
		limit_page_length,
		ignore_permissions=True,  # safe: limited to the user's own Customer just above
		fields=FIELDS,
		order_by=order_by or "creation desc",
		or_filters=search_filters(doctype, txt, SEARCH_FIELDS),
	)


def list_context(context=None):
	"""Settings for Frappe's portal list page (called through repair_order.get_list_context)."""
	return {
		"title": _("Repairs"),
		"get_list": get_repair_list,
		"show_sidebar": True,  # portal left menu
		"show_search": True,
		"no_breadcrumbs": True,
		"sf_status_colors": STATUS_COLORS,  # read by sf_table_row.html
	}


# Columns + paging around get_list_context(); applied once per worker by list_engine.apply().
paginate_list_context(
	"sas_fortuna.sas_fortuna.doctype.repair_order.repair_order", get_list=get_repair_list, columns=COLUMNS
)
