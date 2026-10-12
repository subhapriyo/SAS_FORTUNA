"""Portal page /repairs  (P1 custom part). Template: www/repairs.html

Shows the logged-in customer their repair orders, loaners and dispatch
details, and lets them accept an open service quotation (N7).
Everything is filtered by the customer linked to the user's Contact, so a
customer can never see another customer's data.
"""

import frappe
from frappe import _

from sas_fortuna.support.portal import get_portal_customer

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view your repairs."), frappe.PermissionError)

	customer = get_portal_customer()
	context.no_breadcrumbs = True
	context.title = _("My Repairs")
	context.repairs = []
	if not customer:
		return context

	context.repairs = frappe.get_all(
		"Repair Order",
		filters={"customer": customer},
		fields=[
			"name",
			"serial_no",
			"product_model",
			"status",
			"support_type",
			"quotation",
			"delivery_note",
			"modified",
		],
		order_by="modified desc",
		ignore_permissions=True,  # safe: filtered by the user's own customer
	)
	for r in context.repairs:
		r.loaner = frappe.db.get_value(
			"Returnable Gate Pass",
			{"repair_order": r.name, "docstatus": 1, "status": ["in", ["Open", "Overdue"]]},
			["serial_no", "expected_return_date"],
			as_dict=True,
		)
		r.can_accept = bool(
			r.quotation
			and frappe.db.get_value("Quotation", r.quotation, ["docstatus", "status"]) == (1, "Open")
		)
	return context
