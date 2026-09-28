import math
from urllib.parse import urlencode

import frappe
from erpnext.controllers import website_list_for_contact as wlc
from frappe.utils import cint
from frappe.utils.user import is_website_user

# doctype -> {"default": "field dir", "sort": {allowed fields}, "filters": (...), "paginate": bool}
REGISTRY = {}
PAGE_SIZES = (10, 20, 50, 100)
DEFAULT_PAGE_LEN = 10
_PARAMS = ("sort_by", "sort_dir", "sf_page", "sf_len")
_PATCHES = []


def register(doctype, default, sort, filters=("status",), paginate=False):
	REGISTRY[doctype] = {
		"default": default,
		"sort": set(sort),
		"filters": tuple(filters),
		"paginate": paginate,
	}


def add_patch(fn):
	"""Register a function that is run once, after ERPNext is importable."""
	_PATCHES.append(fn)


def _page_len():
	"""Items per page requested via ?sf_len=, restricted to PAGE_SIZES."""
	size = cint(frappe.form_dict.get("sf_len"))
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
		doc.sf = frappe._dict(info, first=(i == 0), last=(i == shown - 1))


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
		cfg = REGISTRY.get(doctype)
		if not cfg or kwargs.get("custom"):
			return original(doctype, txt, filters, limit_start, limit_page_length, order_by, **kwargs)

		# ERPNext mutates `filters` in place (docstatus, customer...) but only if it is non-empty.
		# Own a non-empty copy so we can reuse the effective filters for the total count.
		filters = frappe._dict(filters or {})
		for key in _PARAMS:  # our params are not DB fields
			filters.pop(key, None)
		filters.setdefault("docstatus", 1)  # placeholder, ERPNext overwrites it

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
			return original(
				doctype, txt, filters, limit_start, limit_page_length, order_by=order_by, **kwargs
			)

		rows = fetch()
		if not paged:
			return rows

		total = None if txt else _count(doctype, filters)
		if total and page > math.ceil(total / page_len):  # stale/hand-edited ?sf_page=
			page = math.ceil(total / page_len)
			limit_start = (page - 1) * page_len
			rows = fetch()

		if rows:
			_annotate(rows, page, page_len, total)
		return rows

	wlc.get_transaction_list = get_transaction_list

	for fn in (_patch_portal_get, *_PATCHES):
		try:
			fn()
		except Exception:
			frappe.log_error(title="sas_fortuna portal patch failed")
