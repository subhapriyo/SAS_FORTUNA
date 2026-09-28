from urllib.parse import urlencode

import frappe
from erpnext.controllers import website_list_for_contact as wlc
from frappe.utils import cint

# doctype -> {"default": "field dir", "sort": {allowed fields}, "filters": (...), "paginate": bool}
REGISTRY = {}
PAGE_LEN = 20
_PARAMS = ("sort_by", "sort_dir", "sf_page")
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


def _page_url(page):
	request = getattr(frappe.local, "request", None)
	if not request:
		return ""
	args = request.args.to_dict()
	args["sf_page"] = page
	return f"{request.path}?{urlencode(args)}"


def _annotate(rows, page):
	"""Attach paging info to the rows so the row template can draw the footer."""
	shown = min(len(rows), PAGE_LEN)
	has_next = len(rows) > PAGE_LEN
	info = {
		"sf_page": page,
		"sf_start": (page - 1) * PAGE_LEN,
		"sf_shown": shown,
		"sf_has_next": has_next,
		"sf_prev_url": _page_url(page - 1) if page > 1 else "",
		"sf_next_url": _page_url(page + 1) if has_next else "",
	}
	for i, doc in enumerate(rows):
		doc.update({**info, "sf_first": i == 0, "sf_last": i == shown - 1})


def apply():
	"""Idempotent: safe to call on every request (hooked via before_request)."""
	if getattr(wlc, "_sas_patched", False):
		return
	wlc._sas_patched = True
	original = wlc.get_transaction_list

	def get_transaction_list(
		doctype, txt=None, filters=None, limit_start=0, limit_page_length=20, order_by="modified desc"
	):
		cfg = REGISTRY.get(doctype)
		page = 1
		paged = False
		if cfg:
			# keep our params out of the DB filters, otherwise Frappe treats them as fields
			if isinstance(filters, dict):
				for key in _PARAMS:
					filters.pop(key, None)
			order_by = cfg["default"]
			field = frappe.form_dict.get("sort_by")
			if field in cfg["sort"]:
				direction = "asc" if frappe.form_dict.get("sort_dir") == "asc" else "desc"
				order_by = f"{field} {direction}"

			# numbered paging for full page loads (the "More" ajax call carries a cmd)
			paged = cfg["paginate"] and not frappe.form_dict.get("cmd")
			if paged:
				page = max(cint(frappe.form_dict.get("sf_page")), 1)
				limit_start = (page - 1) * PAGE_LEN
				limit_page_length = PAGE_LEN + 1  # one extra row tells us if a next page exists

		rows = original(doctype, txt, filters, limit_start, limit_page_length, order_by=order_by)
		if paged and rows:
			_annotate(rows, page)
		return rows

	wlc.get_transaction_list = get_transaction_list

	for fn in _PATCHES:
		try:
			fn()
		except Exception:
			frappe.log_error(title="sas_fortuna portal patch failed")
