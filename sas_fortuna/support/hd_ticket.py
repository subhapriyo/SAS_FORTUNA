"""Doc-event hooks for Helpdesk 'HD Ticket'  (C1, C2, C3, F7, N4, N5).

Wired in hooks.py -> doc_events["HD Ticket"].
Kept small on purpose: routing comes from Fortuna Support Settings,
SLA and assignment stay in Helpdesk configuration.
"""

import frappe
from frappe import _
from frappe.utils import today

from sas_fortuna.support.utils import (
	get_erpnext_customer,
	get_serial_coverage,
	get_settings,
	is_helpdesk_agent,
)

RESOLVED_STATES = ("Resolved", "Closed")


def validate(doc, method=None):
	route_to_team(doc)
	apply_serial_details(doc)
	require_resolution_notes(doc)


def on_update(doc, method=None):
	# F7: remember when this unit was last serviced.
	if doc.has_value_changed("status") and doc.status in RESOLVED_STATES and doc.get("custom_serial_no"):
		frappe.db.set_value("Serial No", doc.custom_serial_no, "custom_last_service_date", today())


# ---------------------------------------------------------------------------
# C1  Ticket Type -> Team
# ---------------------------------------------------------------------------
def route_to_team(doc):
	"""Pick the team from the routing table, only when none is chosen yet.

	The Team's own assignment rule (round robin) then picks the agent.
	"""
	if doc.get("agent_group") or not doc.get("ticket_type"):
		return
	for row in get_settings().team_routing:
		if row.ticket_type == doc.ticket_type:
			doc.agent_group = row.team
			return


# ---------------------------------------------------------------------------
# C2 / N4 / N5  Serial -> model, customer, invoice, support type
# ---------------------------------------------------------------------------
def apply_serial_details(doc):
	serial_no = doc.get("custom_serial_no")
	if not serial_no:
		doc.custom_support_type = None
		return
	# Re-evaluate only when the serial changes (or the ticket is new).
	if not doc.has_value_changed("custom_serial_no") and doc.get("custom_support_type"):
		return

	info = get_serial_coverage(serial_no)

	# Serial must belong to the chosen model.
	if doc.get("custom_product_model") and doc.custom_product_model != info.item_code:
		frappe.throw(
			_("Serial No {0} belongs to {1}, not {2}.").format(
				serial_no, info.item_code, doc.custom_product_model
			)
		)

	# Portal customers may only raise tickets for units sold to them.
	ticket_customer = get_erpnext_customer(doc.get("customer"))
	if not is_helpdesk_agent() and ticket_customer and info.customer and ticket_customer != info.customer:
		frappe.throw(_("This serial number is not registered to your account."))

	doc.custom_product_model = info.item_code
	doc.custom_invoice_no = info.invoice_no
	doc.custom_invoice_date = info.invoice_date
	doc.custom_warranty_end = info.warranty_end
	doc.custom_amc_expiry = info.amc_expiry
	doc.custom_support_type = info.support_type
	doc.custom_erpnext_customer = doc.get("custom_erpnext_customer") or info.customer
	# Primary contact's mobile from the Customer master (C1 acceptance).
	if not doc.get("custom_contact_mobile") and doc.custom_erpnext_customer:
		doc.custom_contact_mobile = frappe.db.get_value("Customer", doc.custom_erpnext_customer, "mobile_no")


# ---------------------------------------------------------------------------
# C3  No resolve without notes (agents only; customers may close freely)
# ---------------------------------------------------------------------------
def _resolution_field(doc):
	"""Helpdesk releases differ: use their field if present, else ours."""
	return "resolution_details" if doc.meta.has_field("resolution_details") else "custom_resolution_notes"


def require_resolution_notes(doc):
	if doc.status != "Resolved" or not doc.has_value_changed("status"):
		return
	if not is_helpdesk_agent():
		return
	if not (doc.get(_resolution_field(doc)) or "").strip():
		frappe.throw(_("Please add resolution notes before marking the ticket Resolved."))


def resolve_ticket(ticket, note):
	"""Resolve a ticket from code (used when a repair is dispatched)."""
	doc = frappe.get_doc("HD Ticket", ticket)
	if doc.status in RESOLVED_STATES:
		return
	doc.set(_resolution_field(doc), note)
	doc.status = "Resolved"
	doc.save(ignore_permissions=True)  # system action, triggers Helpdesk e-mails
