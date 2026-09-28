import importlib
import math
from urllib.parse import urlencode

import frappe
from erpnext.controllers import website_list_for_contact as wlc
from frappe.utils import cint
from frappe.utils.user import is_website_user

# doctype -> {"default": "field dir", "sort": {allowed fields}, "filters": (...), "paginate": bool, "count": bool}
REGISTRY = {}
PAGE_SIZES = (10, 25, 50, 100)
MAX_ALL = 500  # ?sf_len=all (All items) is capped: every row is loaded as a full document
DEFAULT_PAGE_LEN = 10
_PARAMS = ("sort_by", "sort_dir", "sf_page", "sf_len")
_PATCHES = []
PAGED_ROW_TEMPLATE = "templates/includes/sf_paged_row.html"
TABLE_ROW_TEMPLATE = "templates/includes/sf_table_row.html"

# ERPNext's transaction list and our Issue list mutate `filters` in place (docstatus, customer,
# raised_by...) but only when it is non-empty, so we seed a harmless key to keep our copy in sync
# for the total count. ERPNext overwrites docstatus; Issue is not submittable, so it gets a no-op.
_TRANSACTION_SEED = {"docstatus": 1}
_GENERIC_SEED = {"name": ["!=", ""]}


def register(doctype, default, sort, filters=("status",), paginate=False, count=True):
	REGISTRY[doctype] = {
		"default": default,
		"sort": set(sort),
		"filters": tuple(filters),
		"paginate": paginate,
		"count": count,  # False: no cheap total, so Previous / Next paging instead of page numbers
	}


def add_patch(fn):
	"""Register a function that is run once, after ERPNext is importable."""
	_PATCHES.append(fn)


def paginate_list_context(module_path, get_list=None, columns=None):
	"""Turn on numbered paging for the portal list of the doctype module at `module_path`.

	Wraps the module's get_list_context() so the list uses sf_paged_row.html (the doctype's own row
	template + the pager footer). If `get_list` is given it replaces ERPNext's list query, and is
	paginated the same way as the stock transaction list. If `columns` is given, rows are drawn by
	sf_table_row.html: a table with a header row (see that template for the column format).
	"""

	def _patch():
		module = importlib.import_module(module_path)
		original = module.get_list_context

		def get_list_context(context=None):
			list_context = original(context)
			base = list_context.get("row_template")
			if columns:
				list_context["sf_columns"] = columns
				list_context["row_template"] = TABLE_ROW_TEMPLATE
			elif base and base != PAGED_ROW_TEMPLATE:
				# plain dict in ERPNext: use item assignment, not attributes
				list_context["sf_base_row"] = base
				list_context["row_template"] = PAGED_ROW_TEMPLATE
			if get_list:
				list_context["get_list"] = _wrap_get_list(get_list)
			return list_context

		module.get_list_context = get_list_context

	add_patch(_patch)


def _page_len():
	"""Items per page requested via ?sf_len= (a PAGE_SIZES value or "all")."""
	raw = frappe.form_dict.get("sf_len")
	if raw == "all":
		return MAX_ALL
	size = cint(raw)
	return size if size in PAGE_SIZES else DEFAULT_PAGE_LEN


def _page_url(page):
	request = getattr(frappe.local, "request", None)
	if not request:
		return ""
	args = request.args.to_dict()
	if page > 1:
		args["sf_page"] = page
	else:
		args.pop("sf_page", None)
	query = urlencode(args)
	return f"{request.path}?{query}" if query else request.path


def _page_links(page, pages, span=2):
	"""1 ... 4 5 [6] 7 8 ... 20  ->  list of {n, url, current} and {gap} entries."""
	wanted = sorted({1, pages, *range(max(1, page - span), min(pages, page + span) + 1)})
	links, last = [], 0
	for n in wanted:
		if n - last > 1:
			links.append(frappe._dict(gap=True))
		links.append(frappe._dict(n=n, url=_page_url(n), current=(n == page)))
		last = n
	return links


def _count(doctype, filters):
	"""Total rows matching the *effective* filters (docstatus / customer already applied by ERPNext)."""
	try:
		ignore = frappe.session.user != "Guest" and is_website_user()
		names = frappe.get_list(
			doctype,
			filters=dict(filters),
			pluck="name",
			limit_page_length=0,
			ignore_permissions=ignore,
		)
		return len(names)
	except Exception:
		frappe.log_error(title="sas_fortuna portal count failed")
		return None


def _annotate(rows, page, page_len, total):
	"""Attach paging info to each row (as `doc.sf`) so the row template can draw header/footer."""
	shown = min(len(rows), page_len)
	if total is None:  # e.g. text search: no cheap total, fall back to "is there one more row?"
		pages = None
		has_next = len(rows) > page_len
	else:
		pages = max(math.ceil(total / page_len), 1)
		has_next = page < pages

	info = {
		"page": page,
		"page_size": page_len,
		"sizes": PAGE_SIZES,
		"start": (page - 1) * page_len,
		"shown": shown,
		"total": total,
		"pages": pages,
		"has_next": has_next,
		"prev_url": _page_url(page - 1) if page > 1 else "",
		"next_url": _page_url(page + 1) if has_next else "",
		"links": _page_links(page, pages) if pages and pages > 1 else [],
	}
	for i, doc in enumerate(rows):
		# plain attribute, not doc.update(): a list value would be treated as child rows
		doc.sf = frappe._dict(info, first=(i == 0), last=(i == shown - 1), n=info["start"] + i + 1)


def _patch_portal_get():
	"""frappe.www.portal.get() asks for `limit + 1` rows and drops the last one itself.
	Feeding it our page size as `limit` lets it do that trimming natively."""
	from frappe.www import portal

	original = portal.get

	def get(doctype, **kwargs):
		cfg = REGISTRY.get(doctype)
		if cfg and cfg["paginate"]:
			kwargs["limit"] = _page_len()
		return original(doctype, **kwargs)

	portal.get = get


def _paginate(doctype, original, txt, filters, limit_start, limit_page_length, seed, **kwargs):
	"""Sorting + numbered paging around `original(doctype, txt, filters, start, len, order_by=..)`."""
	cfg = REGISTRY[doctype]

	# Own a non-empty copy so we can reuse the effective filters for the total count.
	filters = frappe._dict(filters or {})
	for key in _PARAMS:  # our params are not DB fields
		filters.pop(key, None)
	for key, value in seed.items():
		filters.setdefault(key, value)

	order_by = cfg["default"]
	field = frappe.form_dict.get("sort_by")
	if field in cfg["sort"]:
		direction = "asc" if frappe.form_dict.get("sort_dir") == "asc" else "desc"
		order_by = f"{field} {direction}"

	# numbered paging for full page loads (the "More" ajax call carries a cmd)
	paged = cfg["paginate"] and not frappe.form_dict.get("cmd")
	page = 1
	page_len = DEFAULT_PAGE_LEN
	if paged:
		page_len = max(cint(limit_page_length) - 1, 1)  # portal.get asks for page_len + 1
		page = max(cint(frappe.form_dict.get("sf_page")), 1)
		limit_start = (page - 1) * page_len

	def fetch():
		return original(doctype, txt, filters, limit_start, limit_page_length, order_by=order_by, **kwargs)

	rows = fetch()
	if not paged:
		return rows

	total = None if (txt or not cfg["count"]) else _count(doctype, filters)
	if total and page > math.ceil(total / page_len):  # stale/hand-edited ?sf_page=
		page = math.ceil(total / page_len)
		limit_start = (page - 1) * page_len
		rows = fetch()

	if rows:
		_annotate(rows, page, page_len, total)
	return rows


def _wrap_get_list(original):
	"""For doctypes with their own get_list (e.g. Issue), set through paginate_list_context(get_list=)."""

	def get_list(
		doctype, txt=None, filters=None, limit_start=0, limit_page_length=20, order_by=None, **kwargs
	):
		if doctype not in REGISTRY:
			return original(
				doctype, txt, filters, limit_start, limit_page_length, order_by=order_by, **kwargs
			)
		return _paginate(
			doctype, original, txt, filters, limit_start, limit_page_length, _GENERIC_SEED, **kwargs
		)

	return get_list


def apply():
	"""Idempotent: safe to call on every request (hooked via before_request)."""
	if getattr(wlc, "_sas_patched", False):
		return
	wlc._sas_patched = True
	original = wlc.get_transaction_list

	def get_transaction_list(
		doctype,
		txt=None,
		filters=None,
		limit_start=0,
		limit_page_length=20,
		order_by="creation desc",
		**kwargs,  # ERPNext also calls this with custom=True (web-form link filtering)
	):
		if doctype not in REGISTRY or kwargs.get("custom"):
			return original(doctype, txt, filters, limit_start, limit_page_length, order_by, **kwargs)
		return _paginate(
			doctype, original, txt, filters, limit_start, limit_page_length, _TRANSACTION_SEED, **kwargs
		)

	wlc.get_transaction_list = get_transaction_list

	for fn in (_patch_portal_get, *_PATCHES):
		try:
			fn()
		except Exception:
			frappe.log_error(title="sas_fortuna portal patch failed")
