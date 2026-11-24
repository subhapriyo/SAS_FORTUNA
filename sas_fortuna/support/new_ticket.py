"""Helpdesk's New Ticket form, as agents see it: Customer first, the rest follows from it.

	get_template()          Helpdesk's own template call, adjusted for agents (hooks.py routes
	                        helpdesk...hd_ticket_template.api.get_one here)
	new_ticket_defaults()   what picking a Customer fills in: Job Location and their units
	job_location_for()      a customer's branch: Bill To city/state, else Kolkata

The customer portal uses the same template. There the customer is known from the login, so
it gets Helpdesk's form unchanged (Customer and Job Location rows are agents-only, see
setup/support_desk.py TICKET_FORM_FIELDS). The page side is setup/data/fortuna_new_ticket_form.js.
"""

import frappe
from frappe import _

from sas_fortuna.sas_fortuna.doctype.job_location.job_location import (
	default_location,
	location_for_customer,
)
from sas_fortuna.support.utils import is_helpdesk_agent

CUSTOMER_FIELD = "custom_erpnext_customer"
SERIAL_FIELD = "custom_serial_no"


# ---------------------------------------------------------------------------
# The form itself
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_template(name):
	"""Helpdesk's template, with two changes for agents:

	  - the Customer row reads "Customer" (its field is labelled "ERPNext Customer")
	  - Serial No becomes a searchable link: the portal's list of choices (url_method) knows only
	    the logged-in customer, so for an agent it would always be empty. The page then narrows
	    the link to the customer the agent picks.
	Customers get Helpdesk's answer as it is."""
	from helpdesk.helpdesk.doctype.hd_ticket_template.api import get_one

	template = get_one(name)
	if not is_helpdesk_agent():
		return template
	for field in template.get("fields") or []:
		if field.fieldname == CUSTOMER_FIELD:
			field.label = _("Customer")
		elif field.fieldname == SERIAL_FIELD:
			field.url_method = ""
	return template


# ---------------------------------------------------------------------------
# What a Customer fills in
# ---------------------------------------------------------------------------
@frappe.whitelist()
def new_ticket_defaults(customer):
	"""Called when an agent picks the Customer on the New Ticket form.

	Returns {job_location, serials}: the customer's branch and the names of the units sold to
	them (Serial No.custom_sold_to), newest first. Agents only: it would list any customer's
	units."""
	if not is_helpdesk_agent():
		frappe.throw(_("Only support agents can look up a customer's details."), frappe.PermissionError)
	return {
		"job_location": job_location_for(customer),
		"serials": frappe.get_all(
			"Serial No",
			filters={"custom_sold_to": customer},
			pluck="name",
			order_by="creation desc",
			limit=500,
		),
	}


def job_location_for(customer):
	"""The customer's branch: the Job Location serving their Bill To city (else state), and
	Kolkata (the default location) when none does or they have no address."""
	return (customer and location_for_customer(customer)) or default_location()
