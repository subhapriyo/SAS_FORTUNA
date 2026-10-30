"""Customer / Supplier portal /my-ledger: the party's ledger (GL Entry) as a portal list.

Why
    /my-ledger used to be Frappe's plain Web Form list: no filters, no paging, a cut-off Remarks
    column and no totals. It is now drawn like /orders and /invoices, with a summary at the end.

How it works
    1. portal/renderers.py serves the route "my-ledger" as the GL Entry list page (it would
       otherwise go to the "my-ledger" Web Form, which still shows one entry: /my-ledger/<entry>).
    2. GL Entry has no portal list of its own, so _attach() gives ERPNext's GL Entry module the
       get_list_context() function Frappe looks for (added at runtime; ERPNext is not edited).
    3. paginate_list_context() adds columns, sorting, date range, voucher-type filter and paging.
       The filter bar settings are in public/js/portal.js ("/my-ledger").
    4. list_context() adds the summary under the table: opening balance, total debit, total
       credit and closing balance for the selected period (all matching entries, not one page).

Safety
    Every query is limited to the portal user's own party (get_portal_party). Cancelled entries
    are never shown.
"""

import importlib

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate
from markupsafe import Markup, escape

from sas_fortuna.portal.list_engine import add_patch, paginate_list_context, register, search_filters

GL_ENTRY_MODULE = "erpnext.accounts.doctype.gl_entry.gl_entry"

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

# Table columns (format: templates/includes/sf_table_row.html). The voucher links to
# /my-ledger/<entry>, the existing "my-ledger" Web Form page that shows one entry in full.
COLUMNS = [
	{"label": "Date", "field": "posting_date", "kind": "date"},
	{"label": "Voucher", "field": "voucher_no", "kind": "name", "sub": "voucher_type", "sub_kind": "text"},
	{"label": "Debit", "field": "debit", "kind": "money"},
	{"label": "Credit", "field": "credit", "kind": "money"},
	{"label": "Remarks", "field": "remarks", "kind": "text"},
]
FIELDS = ["name", "posting_date", "voucher_type", "voucher_no", "debit", "credit", "remarks", "creation"]
# What the Search box looks in (placeholder text: public/js/portal.js, "/my-ledger").
SEARCH_FIELDS = ["voucher_no", "against_voucher", "remarks"]

register(
	"GL Entry",
	default="posting_date desc, creation desc",  # newest first, stable within a day
	sort={"posting_date", "debit", "credit", "voucher_type", "voucher_no"},
	paginate=True,
	date_field="posting_date",
)


# ---------------------------------------------------------------------------
# Whose ledger
# ---------------------------------------------------------------------------
def get_portal_party(user=None):
	"""(party_type, party) of the logged-in portal user, or (None, None).

	Same order as the "Get Portal Ledger" server script: the Customer / Supplier "Portal Users"
	table first (Customer before Supplier), then the user's Contact links.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		return None, None
	for party_type in ("Customer", "Supplier"):
		party = frappe.db.get_value("Portal User", {"parenttype": party_type, "user": user}, "parent")
		if party:
			return party_type, party
	contact = frappe.db.get_value("Contact", {"user": user}, "name")
	if contact:
		for party_type in ("Customer", "Supplier"):
			party = frappe.db.get_value(
				"Dynamic Link",
				{"parenttype": "Contact", "parent": contact, "link_doctype": party_type},
				"link_name",
			)
			if party:
				return party_type, party
	return None, None


def _party_filters():
	party_type, party = get_portal_party()
	if not party:
		return None
	return {"party_type": party_type, "party": party, "is_cancelled": 0}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------
def get_ledger_list(doctype, txt, filters, limit_start, limit_page_length=20, order_by=None, **kwargs):
	"""Ledger entries of the logged-in party only (empty for anyone without a party)."""
	from frappe.www.list import get_list

	own = _party_filters()
	if own is None:
		return []
	if filters is None:
		filters = {}
	# Change the dict in place: the list engine reuses it to count the total for the pager.
	filters.update(own)
	rows = get_list(
		doctype,
		None,  # the search text is handled by or_filters below
		filters,
		limit_start,
		limit_page_length,
		ignore_permissions=True,  # safe: limited to the user's own party just above
		fields=FIELDS,
		order_by=order_by or "posting_date desc, creation desc",
		or_filters=search_filters(doctype, txt, SEARCH_FIELDS),
	)
	currency = _currency()
	for row in rows:
		row["currency"] = currency  # used by the money columns
		for field in ("debit", "credit"):
			if not flt(row.get(field)):
				row[field] = None  # show a dash, not 0.00, in the empty column
	return rows


def _currency():
	company = frappe.db.get_default("company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	return (
		company and frappe.get_cached_value("Company", company, "default_currency")
	) or frappe.db.get_default("currency")


# ---------------------------------------------------------------------------
# Summary under the table
# ---------------------------------------------------------------------------
def _summary():
	"""Totals for the selected period and voucher type (all pages), as HTML for the list footer."""
	own = _party_filters()
	if own is None:
		return ""

	start = _date_param("sf_from")
	end = _date_param("sf_to")
	if start and end and start > end:
		start, end = end, start
	voucher_type = frappe.form_dict.get("voucher_type")
	txt = (frappe.form_dict.get("txt") or "").strip()

	where = ["party_type = %(party_type)s", "party = %(party)s", "is_cancelled = 0"]
	values = dict(own, start=start, end=end, voucher_type=voucher_type, txt=f"%{txt}%")
	period = list(where)
	if start:
		period.append("posting_date >= %(start)s")
	if end:
		period.append("posting_date <= %(end)s")
	if voucher_type:
		period.append("voucher_type = %(voucher_type)s")
	if txt:  # same fields as the Search box (SEARCH_FIELDS)
		period.append("(" + " or ".join(f"{f} like %(txt)s" for f in SEARCH_FIELDS) + ")")

	debit, credit = frappe.db.sql(
		f"select ifnull(sum(debit), 0), ifnull(sum(credit), 0) from `tabGL Entry` where {' and '.join(period)}",
		values,
	)[0]

	# Opening / closing balance only make sense for the whole ledger, not for one voucher type or
	# a search result.
	opening = None
	if not voucher_type and not txt:
		opening = 0
		if start:
			opening = frappe.db.sql(
				f"select ifnull(sum(debit - credit), 0) from `tabGL Entry` where {' and '.join(where)} and posting_date < %(start)s",
				values,
			)[0][0]

	currency = _currency()
	money = lambda v: escape(fmt_money(abs(flt(v)), currency=currency))  # noqa: E731
	rows = []
	if opening is not None and start:  # no start date: the ledger starts at zero
		rows.append((_("Opening balance"), money(opening) + _drcr(opening, own["party_type"])))
	rows.append((_("Total debit"), money(debit)))
	rows.append((_("Total credit"), money(credit)))
	if opening is not None:
		closing = flt(opening) + flt(debit) - flt(credit)
		rows.append((_("Closing balance"), money(closing) + _drcr(closing, own["party_type"]), True))

	title = _("Summary")
	if start or end:
		title = _("Summary for {0} to {1}").format(
			frappe.utils.formatdate(start) if start else _("the start"),
			frappe.utils.formatdate(end) if end else _("today"),
		)
	if voucher_type:
		title += " · " + _(voucher_type)  # plain text: escaped once, by Markup.format below
	if txt:
		title += " · " + _('matching "{0}"').format(txt)

	# Markup("").join keeps the rows as HTML (a plain "".join would make them text again).
	body = Markup("").join(
		Markup('<div class="sf-ledger-row{}"><span>{}</span><span>{}</span></div>').format(
			" sf-ledger-total" if len(r) > 2 else "", r[0], r[1]
		)
		for r in rows
	)
	return Markup('<div class="sf-ledger-summary"><h5>{}</h5>{}</div>').format(title, body)


def _drcr(amount, party_type):
	"""Plain words after a balance, from the party's point of view."""
	amount = flt(amount)
	if not amount:
		return ""
	if party_type == "Customer":
		hint = _("payable by you") if amount > 0 else _("in your favour")
	else:
		hint = _("payable to you") if amount < 0 else _("in our favour")
	return Markup(' <span class="sf-muted">{} ({})</span>').format("Dr" if amount > 0 else "Cr", hint)


def _date_param(key):
	try:
		return getdate(frappe.form_dict.get(key)) if frappe.form_dict.get(key) else None
	except Exception:
		return None


def list_context(context=None):
	"""Settings for Frappe's portal list page (Frappe calls this as GL Entry's get_list_context)."""
	return {
		"title": _("My Ledger"),
		"get_list": get_ledger_list,
		"show_sidebar": True,  # portal left menu
		"show_search": True,  # voucher no / remarks (SEARCH_FIELDS)
		"no_breadcrumbs": True,
		"list_footer": _summary(),  # drawn under the table by frappe/www/portal.html
		"no_result_message": _("No ledger entries for this selection."),
	}


# ---------------------------------------------------------------------------
# Wiring (applied once per worker by list_engine.apply())
# ---------------------------------------------------------------------------
def _attach():
	"""Give ERPNext's GL Entry module the get_list_context() Frappe needs to serve a portal list.
	Must run before paginate_list_context's patch below; patches run in the order they are added."""
	module = importlib.import_module(GL_ENTRY_MODULE)
	if not hasattr(module, "get_list_context"):
		module.get_list_context = list_context


add_patch(_attach)
paginate_list_context(GL_ENTRY_MODULE, get_list=get_ledger_list, columns=COLUMNS)
