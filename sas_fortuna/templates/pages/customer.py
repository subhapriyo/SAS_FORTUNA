"""Customer KYC portal page (/customer). Markup: customer.html; behaviour: public/js/portal_kyc.js; data: api/customer.py."""

import frappe
from frappe import _


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to access this page."), frappe.PermissionError)
	context.no_cache = 1
	context.show_sidebar = True
	context.title = _("Customer KYC")
