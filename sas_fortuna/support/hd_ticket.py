"""Doc-event hooks for Helpdesk 'HD Ticket'  (C1, C2, C3, F7, N4, N5).

Wired in hooks.py -> doc_events["HD Ticket"].
Kept small on purpose: routing comes from Fortuna Support Settings,
SLA and assignment stay in Helpdesk configuration.
"""

import frappe
from frappe import _

from sas_fortuna.sas_fortuna.doctype.job_location.job_location import location_for_customer
from sas_fortuna.support.utils import (
	get_erpnext_customer,
	get_hd_customer,
	get_serial_coverage,
	get_settings,
	is_helpdesk_agent,
)

RESOLVED_STATES = ("Resolved", "Closed")


def before_insert(doc, method=None):
	# Runs before Helpdesk resets a new ticket's status to Open: remember an imported ticket's status.
	from sas_fortuna.support.legacy_import import remember_legacy_status

	remember_legacy_status(doc)


def after_insert(doc, method=None):
	send_portal_acknowledgement(doc)


# ---------------------------------------------------------------------------
# "We've received your ticket" e-mail for portal tickets
# ---------------------------------------------------------------------------
def send_portal_acknowledgement(doc):
	"""Helpdesk sends its acknowledgement e-mail (Helpdesk > Settings > Email Notifications >
	Acknowledgement) only for tickets that came in by e-mail. Send the same, editable template
	for customer-portal tickets too. A mail problem is logged and never stops the ticket."""
	if not doc.via_customer_portal or not doc.get("raised_by"):
		return
	if not frappe.db.get_single_value("HD Settings", "send_acknowledgement_email"):
		return
	try:
		doc.send_acknowledgement_email()
	except Exception:
		frappe.log_error(title=f"sas_fortuna: acknowledgement e-mail for ticket {doc.name} not sent")


def validate(doc, method=None):
	from sas_fortuna.support.legacy_import import validate_legacy

	apply_issue_subject(doc)
	apply_serial_details(doc)
	apply_customer_from_sender(doc)  # after the serial: the unit's owner wins
	apply_job_location(doc)  # needs the customer
	route_to_team(doc)  # needs the ticket type and the job location
	require_resolution_notes(doc)
	validate_legacy(doc)  # imported old tickets only: number, dates


# ---------------------------------------------------------------------------
# Subject dropdown on the New Ticket form (Ticket Subject list)
# ---------------------------------------------------------------------------
def apply_issue_subject(doc):
	"""A predefined subject becomes the ticket's subject; "Others" keeps what the customer typed,
	which then must be filled in. Checked only when the choice changes, so switching a subject
	off later never blocks saving the tickets already raised with it."""
	choice = doc.get("custom_issue_subject")
	if not choice or not doc.has_value_changed("custom_issue_subject"):
		return
	from sas_fortuna.sas_fortuna.doctype.ticket_subject.ticket_subject import OTHERS, is_offered

	if choice == OTHERS:
		typed = (doc.subject or "").strip()
		if not typed or typed == OTHERS:
			frappe.throw(_("Please describe your issue in a few words when the subject is Others."))
		return
	if not is_offered(choice, doc.ticket_type):
		frappe.throw(_("{0} is not a subject for {1} tickets.").format(choice, doc.ticket_type or _("these")))
	doc.subject = choice


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
	Helpdesk's own Customer field (doc.customer, an HD Customer) then follows it when blank,
	so agents see the customer on the ticket.
	"""
	if not doc.get("custom_erpnext_customer"):
		doc.custom_erpnext_customer = sender_customer(doc)
	if not doc.get("customer") and doc.get("custom_erpnext_customer"):
		doc.customer = get_hd_customer(doc.custom_erpnext_customer)


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
# Job Location: where the customer is, so which branch's engineers take the ticket
# ---------------------------------------------------------------------------
def apply_job_location(doc):
	"""Fill the ticket's Job Location from its customer's address (city, else state) when blank.
	An agent may change it in the ticket sidebar; route_to_team then moves the ticket."""
	if doc.get("custom_job_location") or not doc.get("custom_erpnext_customer"):
		return
	doc.custom_job_location = location_for_customer(doc.custom_erpnext_customer)


# ---------------------------------------------------------------------------
# C1  Ticket Type + Job Location -> Team
# ---------------------------------------------------------------------------
def route_to_team(doc):
	"""Set the team from Fortuna Support Settings > Team Routing.

	The team's own assignment rule (round robin) then picks the agent, and the ticket page's
	Assignee list shows that team at the ticket's Job Location (support/agent_filter.py).
	  - no team yet -> the routed team
	  - ticket type or job location changed -> the newly routed team, unless an agent had picked
	    a team that routing never gives (a hand-picked team is kept)
	"""
	if not doc.get("ticket_type"):
		return
	routes = get_settings().team_routing
	team = team_for(doc.ticket_type, doc.get("custom_job_location"), routes)
	if not team or doc.get("agent_group") == team:
		return
	if not doc.get("agent_group"):
		doc.agent_group = team
	elif _routing_changed(doc) and doc.agent_group in {row.team for row in routes}:
		doc.agent_group = team


def _routing_changed(doc):
	return doc.has_value_changed("ticket_type") or doc.has_value_changed("custom_job_location")


def team_for(ticket_type, job_location, routes):
	"""The team for this ticket type at this location: the location's row while its team has an
	active agent (so no ticket waits in an empty team), else the type's row without a location."""
	fallback = None
	for row in routes:
		if row.ticket_type != ticket_type:
			continue
		location = row.get("job_location")
		if job_location and location == job_location and has_active_agent(row.team):
			return row.team
		if not location and not fallback:
			fallback = row.team
	return fallback


def has_active_agent(team):
	"""True when at least one member of the Helpdesk team is an active agent."""
	members = frappe.get_all(
		"HD Team Member", filters={"parenttype": "HD Team", "parent": team}, pluck="user"
	)
	return bool(members) and bool(frappe.db.exists("HD Agent", {"name": ["in", members], "is_active": 1}))


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
# Helpdesk's ticket page has no box for the notes and its Status dropdown saves at once, so a
# refusal (throw) would leave the agent stuck. Instead the ticket keeps its status and is
# flagged; the flag shows the Resolution Details box in the sidebar (setup/support_desk.py
# _resolution_box). With notes typed, picking Resolved again goes through.
RESOLUTION_FLAG = "custom_resolution_requested"
# What a Resolved pick changes before this check runs (Helpdesk's before_validate). The
# resolution date and SLA are worked out later (before_save), from the status put back here.
RESOLVE_CHANGES = ("status", "status_category", "first_responded_on")


def _resolution_field(doc):
	"""Helpdesk releases differ: use their field if present, else ours."""
	return "resolution_details" if doc.meta.has_field("resolution_details") else "custom_resolution_notes"


def _has_notes(doc):
	"""The notes field is HTML (editor): "<p> </p>" is empty."""
	text = frappe.utils.strip_html(doc.get(_resolution_field(doc)) or "")
	return bool(text.replace("&nbsp;", " ").strip())


def _set_flag(doc, value):
	if doc.meta.has_field(RESOLUTION_FLAG):
		doc.set(RESOLUTION_FLAG, value)


def require_resolution_notes(doc):
	if not doc.has_value_changed("status"):
		return  # e.g. the notes being typed: the box stays until the ticket is resolved
	if doc.status != "Resolved" or not is_helpdesk_agent() or _has_notes(doc):
		_set_flag(doc, 0)  # resolved, moved to another status, or not an agent: no box needed
		return
	before = doc.get_doc_before_save()
	if not before:  # a new ticket has no status to keep
		frappe.throw(_("Please add resolution notes before marking the ticket Resolved."))
	for field in RESOLVE_CHANGES:
		doc.set(field, before.get(field))
	_set_flag(doc, 1)
	# Shown as a toast by Helpdesk (checked in the browser) and on the Desk form.
	frappe.msgprint(
		_(
			"Add Resolution Details (ticket sidebar, More Details), then set the ticket to Resolved "
			"again. It stays {0} until then."
		).format(_(before.status)),
		alert=True,
		indicator="orange",
	)


def resolve_ticket(ticket, note):
	"""Resolve a ticket from code (used when a repair is dispatched)."""
	doc = frappe.get_doc("HD Ticket", ticket)
	if doc.status in RESOLVED_STATES:
		return
	doc.set(_resolution_field(doc), note)
	doc.status = "Resolved"
	doc.save(ignore_permissions=True)  # system action, triggers Helpdesk e-mails
