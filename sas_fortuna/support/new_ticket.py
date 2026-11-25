"""Helpdesk's New Ticket form, server side: Customer first for agents, no Job Location.

What lives here
	get_template()          Helpdesk's template call, adjusted per viewer (hooks.py routes
	                        helpdesk...hd_ticket_template.api.get_one here)
	new_ticket_defaults()   what picking a Customer narrows: the units sold to them
	serial_product()        the Item Name shown once an agent picks a unit
	job_location_for()      a customer's branch: Ship To (else Bill To) city/state, else Kolkata

How the pieces fit
	- Job Location is nobody's choice on this form. On save it comes from the customer's Ship
	  To address, else Bill To (support/hd_ticket.py apply_job_location), and the team's
	  Assignment Rule gives the ticket to an engineer at that branch
	  (overrides/assignment_rule.py). Agents can correct it on the ticket later.
	- The customer portal uses the same template; there the customer is known from the login,
	  so the Customer row is agents-only (setup/support_desk.py TICKET_FORM_FIELDS).
	- The page side is setup/data/fortuna_new_ticket_form.js.
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
ITEM_NAME_FIELD = "custom_product_name"  # labelled "Item Name"; the fieldname predates the label

# On the template for the agent's ticket sidebar, but never asked for when creating a ticket.
NOT_ON_NEW_FORM = {"custom_job_location"}

# The most units offered for one customer; a bigger customer is searched by serial instead.
MAX_SERIALS = 500


def _agents_only(message):
	"""Stop anyone who is not a Helpdesk agent: these calls can see any customer's data."""
	if not is_helpdesk_agent():
		frappe.throw(message, frappe.PermissionError)


# ---------------------------------------------------------------------------
# 1. The form: which fields, and how they behave for agents
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_template(name):
	"""Helpdesk's template for the New Ticket page, adjusted:

	everyone  no Job Location (set on save from the Ship To address)
	agents    the Customer row reads "Customer" (its field is labelled "ERPNext Customer")
	agents    Serial No is a searchable link. The portal's choice list (url_method) knows only
	          the logged-in customer, so for an agent it would be empty; the page narrows the
	          link to the customer the agent picks instead.
	agents    Item Name is shown, never typed in: the page fills it from the picked unit."""
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
		elif field.fieldname == ITEM_NAME_FIELD:
			field.disabled = 1
	return template


# ---------------------------------------------------------------------------
# 2. Picking a Customer, then a Serial No
# ---------------------------------------------------------------------------
@frappe.whitelist()
def new_ticket_defaults(customer):
	"""Called when an agent picks the Customer. Returns {"serials": [...]}: the units sold to
	that customer (Serial No.custom_sold_to), newest first.

	No customer means no units. A blank filter would otherwise match every unit not yet sold,
	i.e. stock that belongs to nobody's ticket."""
	_agents_only(_("Only support agents can look up a customer's details."))
	if not customer:
		return {"serials": []}
	serials = frappe.get_all(
		"Serial No",
		filters={"custom_sold_to": customer},
		pluck="name",
		order_by="creation desc",
		limit=MAX_SERIALS,
	)
	return {"serials": serials}


@frappe.whitelist()
def serial_product(serial):
	"""The Item Name of a unit (its Item Code when the item has no name), None when there is no
	such unit. Agents only, like the searchable Serial No it goes with."""
	_agents_only(_("Only support agents can look up a unit."))
	if not serial:
		return None  # never let a blank name fall through to "any Serial No"
	row = frappe.db.get_value("Serial No", serial, ["item_name", "item_code"], as_dict=True)
	return (row.item_name or row.item_code) if row else None


# ---------------------------------------------------------------------------
# 3. Which branch serves the customer
# ---------------------------------------------------------------------------
def job_location_for(customer):
	"""The Job Location serving the customer's Ship To address (else Bill To): its city, else its
	state; the default location (Kolkata) when none does, or when there is no customer or address."""
	return (customer and location_for_customer(customer)) or default_location()
