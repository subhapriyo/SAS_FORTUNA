"""Supplier KYC portal page (/supplier). Markup: supplier.html; behaviour: public/js/portal_kyc.js; data: api/supplier.py."""

import frappe
from frappe import _


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to access this page."), frappe.PermissionError)
	context.no_cache = 1
	context.show_sidebar = True
	context.title = _("Supplier KYC")
