"""Helpdesk's New Ticket form (portal and agents): Customer first for agents, no Job Location.

	get_template()          Helpdesk's own template call, adjusted (hooks.py routes
	                        helpdesk...hd_ticket_template.api.get_one here)
	new_ticket_defaults()   what picking a Customer narrows: the units sold to them
	job_location_for()      a customer's branch: Bill To city/state, else Kolkata

Job Location is nobody's choice on this form: on save it comes from the customer's Bill To
address (support/hd_ticket.py apply_job_location) and the team's Assignment Rule gives the
ticket to an engineer at that branch (overrides/assignment_rule.py). It stays on the agent's
ticket sidebar, so it can be corrected later. The customer portal uses the same template;
there the customer is known from the login (the Customer row is agents-only, see
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
# On the template for the ticket sidebar (agents), but not asked for when creating a ticket.
NOT_ON_NEW_FORM = {"custom_job_location"}


# ---------------------------------------------------------------------------
# The form itself
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_template(name):
	"""Helpdesk's template for the New Ticket page, adjusted:

	- everyone: no Job Location (set on save from the Bill To address, see the module note)
	- agents: the Customer row reads "Customer" (its field is labelled "ERPNext Customer")
	- agents: Serial No becomes a searchable link. The portal's list of choices (url_method)
	  knows only the logged-in customer, so for an agent it would always be empty; the page
	  narrows the link to the customer the agent picks."""
	from helpdesk.helpdesk.doctype.hd_ticket_template.api import get_one

	template = get_one(name)
	template["fields"] = [f for f in template.get("fields") or [] if f.fieldname not in NOT_ON_NEW_FORM]
	if not is_helpdesk_agent():
		return template
	for field in template["fields"]:
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

	Returns {serials}: the names of the units sold to them (Serial No.custom_sold_to), newest
	first. Agents only: it would list any customer's units."""
	if not is_helpdesk_agent():
		frappe.throw(_("Only support agents can look up a customer's details."), frappe.PermissionError)
	return {
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
