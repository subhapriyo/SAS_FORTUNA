"""Doc-event hooks for Helpdesk 'HD Ticket'  (C1, C2, C3, F7, N4, N5).

Wired in hooks.py -> doc_events["HD Ticket"].
Kept small on purpose: routing comes from Fortuna Support Settings,
SLA and assignment stay in Helpdesk configuration.
"""

import frappe
from frappe import _

from sas_fortuna.support.utils import (
	get_erpnext_customer,
	get_serial_coverage,
	get_settings,
	is_helpdesk_agent,
)

RESOLVED_STATES = ("Resolved", "Closed")


def before_insert(doc, method=None):
	# Runs before Helpdesk resets a new ticket's status to Open: remember an imported ticket's status.
	from sas_fortuna.support.legacy_import import remember_legacy_status

	remember_legacy_status(doc)


def validate(doc, method=None):
	from sas_fortuna.support.legacy_import import validate_legacy

	route_to_team(doc)
	apply_serial_details(doc)
	apply_customer_from_sender(doc)  # after the serial: the unit's owner wins
	require_resolution_notes(doc)
	validate_legacy(doc)  # imported old tickets only: number, dates


# ---------------------------------------------------------------------------
# Portal /tickets: which Customer a ticket belongs to
# ---------------------------------------------------------------------------
def apply_customer_from_sender(doc):
	"""Fill the ticket's ERPNext Customer from the person who raised it.

	A ticket with a serial already gets its Customer from the unit (apply_serial_details). One
	without a serial (raised on the portal or by e-mail) would have none, and then it would not
	appear on the customer's /tickets page. Order of lookups:
	  1. the sender is a portal user -> that user's Customer
	  2. the sender's e-mail is on a Contact -> that Contact's Customer
	"""
	if doc.get("custom_erpnext_customer"):
		return
	customer = sender_customer(doc)
	if customer:
		doc.custom_erpnext_customer = customer


def sender_customer(doc):
	"""The ERPNext Customer of the person who raised the ticket, or None."""
	if not doc.get("raised_by"):
		return None
	from sas_fortuna.support.portal import get_portal_customer

	if frappe.db.exists("User", doc.raised_by):
		customer = get_portal_customer(doc.raised_by)
		if customer:
			return customer
	contact = frappe.db.get_value(
		"Contact Email", {"email_id": doc.raised_by, "parenttype": "Contact"}, "parent"
	)
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link", {"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"}, "link_name"
	)


def on_update(doc, method=None):
	# F7: remember when this unit was last serviced. Imported old tickets use their own closing
	# date and never move the date back (legacy_import.last_service_date).
	from sas_fortuna.support.legacy_import import (
		guard_legacy_reopen,
		keep_legacy_resolution_date,
		last_service_date,
	)

	guard_legacy_reopen(doc)  # before the rest: it may put doc.status back to a finished state
	keep_legacy_resolution_date(doc)
	if not doc.get("custom_serial_no") or doc.status not in RESOLVED_STATES:
		return
	# A normal ticket only stamps the unit the moment it becomes Resolved/Closed, not on every later
	# edit of an already-finished ticket (that would keep bumping the date forward). A legacy ticket
	# can go through more than one on_update during import (Helpdesk turns its own description into
	# an inbound "first communication", which re-saves the ticket - see legacy_import.py), so for
	# those has_value_changed() on any one save isn't reliable; last_service_date() is itself
	# idempotent and never moves the date backwards, so it is safe to (re)apply on every call.
	if not doc.get("custom_is_legacy") and not doc.has_value_changed("status"):
		return
	serviced = last_service_date(doc)
	if serviced:
		frappe.db.set_value("Serial No", doc.custom_serial_no, "custom_last_service_date", serviced)


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

	# Portal customers may only raise tickets for units sold to them. Their company comes from the
	# Helpdesk customer link or, on tickets raised from the portal form (where that link is empty),
	# from the person who raised it. No company at all: no serial either, so nobody can look up or
	# file a ticket against someone else's unit.
	if not is_helpdesk_agent():
		own = get_erpnext_customer(doc.get("customer")) or sender_customer(doc)
		if not own or (info.customer and own != info.customer):
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
