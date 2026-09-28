import frappe
from erpnext.controllers import website_list_for_contact as wlc

# doctype -> {"default": "field dir", "sort": {allowed fields}, "filters": (...)}
REGISTRY = {}
_PARAMS = ("sort_by", "sort_dir")


def register(doctype, default, sort, filters=("status",)):
	REGISTRY[doctype] = {"default": default, "sort": set(sort), "filters": tuple(filters)}


def apply():
	"""Idempotent: safe to call on every request (hooked via before_request)."""
	if getattr(wlc, "_sas_patched", False):
		return
	original = wlc.get_transaction_list

	def get_transaction_list(
		doctype, txt=None, filters=None, limit_start=0, limit_page_length=20, order_by="modified desc"
	):
		cfg = REGISTRY.get(doctype)
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
		return original(doctype, txt, filters, limit_start, limit_page_length, order_by=order_by)

	wlc.get_transaction_list = get_transaction_list
	wlc._sas_patched = True
