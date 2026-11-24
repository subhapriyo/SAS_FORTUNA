"""Doc-event hooks for Helpdesk 'HD Ticket'  (C1, C2, C3, F7, N4, N5).

Wired in hooks.py -> doc_events["HD Ticket"].
Kept small on purpose: routing comes from Fortuna Support Settings,
SLA and assignment stay in Helpdesk configuration.
"""

import frappe
from frappe import _

from sas_fortuna.support.new_ticket import job_location_for
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
	post_resolution_comment(doc)  # C3: a resolve just recorded in Resolution History
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
	"""Fill a ticket's Job Location when blank: the branch serving its customer's Bill To city
	(else state), Kolkata when none does or there is no customer. Nobody picks it on the New
	Ticket form; the team's Assignment Rule then gives the ticket to an engineer at that branch
	(overrides/assignment_rule.py). An agent may correct it later in the ticket sidebar;
	route_to_team then moves the ticket."""
	if doc.get("custom_job_location"):
		return
	doc.custom_job_location = job_location_for(doc.get("custom_erpnext_customer"))


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
# C3  No resolve without a resolution (agents only; customers may close freely)
# ---------------------------------------------------------------------------
# Applies to the finished statuses (category "Resolved": Resolved, Closed) when an agent moves
# a ticket into one from an open status. Helpdesk's auto-close saves with ignore_validate, so
# it is never held back; Resolved -> Closed asks nothing more.
# Helpdesk has no resolution prompt of its own, and its Status dropdown saves at once, so a
# refusal (throw) would leave the agent stuck. Instead the ticket keeps its status and is
# flagged, with the status asked for. On the Helpdesk ticket page the flag opens the
# Resolution pop-up (setup/data/fortuna_ticket_actions.js), which saves the text with
# save_resolution_notes and then sets that status the normal way; the Desk form asks before
# saving (public/js/hd_ticket.js). Tickets imported from the old system keep their status.
# Every resolve with a resolution is kept in Resolution History (Desk form, read only) and
# posted as a ticket comment, which is where agents read it on the Helpdesk page (it is not an
# editable sidebar field). Reopening clears the current resolution, so the next resolve asks
# again.
RESOLUTION_FLAG = "custom_resolution_requested"
ASKED_FOR = "custom_resolution_requested_status"  # the finished status the agent picked
RESOLUTION_HISTORY = "custom_resolution_history"
NEED_RESOLUTION = "Please add a resolution message."  # Fortuna's wording, Resolved and Closed
# What a Resolved pick changes before this check runs (Helpdesk's before_validate). The
# resolution date and SLA are worked out later (before_save), from the status put back here.
RESOLVE_CHANGES = ("status", "status_category", "first_responded_on")


def _resolution_field(doc):
	"""Helpdesk releases differ: use their field if present, else ours."""
	return "resolution_details" if doc.meta.has_field("resolution_details") else "custom_resolution_notes"


def _plain(html):
	"""Editor HTML -> plain text ("<p> </p>" -> "")."""
	return frappe.utils.strip_html(html or "").replace("&nbsp;", " ").strip()


def _has_notes(doc):
	return bool(_plain(doc.get(_resolution_field(doc))))


def _from_helpdesk_page():
	"""True when the request comes from a Helpdesk ticket page, where the pop-up asks."""
	from sas_fortuna.support.agent_filter import ticket_from_request

	return bool(ticket_from_request())


def _is_resolved(status):
	return frappe.get_cached_value("HD Ticket Status", status, "category") == "Resolved" if status else False


def _set_flag(doc, asked_for=None):
	"""Flag the ticket as waiting for a resolution for `asked_for` (None clears it)."""
	if doc.meta.has_field(RESOLUTION_FLAG):
		doc.set(RESOLUTION_FLAG, 1 if asked_for else 0)
	if doc.meta.has_field(ASKED_FOR):
		doc.set(ASKED_FOR, asked_for)


def need_resolution():
	"""The error shown when Resolved or Closed is picked without a resolution."""
	return _(NEED_RESOLUTION)


def require_resolution_notes(doc):
	if not doc.has_value_changed("status"):
		return  # e.g. the resolution being typed: nothing to decide until the status moves
	if doc.get("custom_is_legacy"):
		return  # imported old tickets: legacy_import checks their resolution and status
	before = doc.get_doc_before_save()
	was_finished = bool(before) and _is_resolved(before.status)
	if was_finished and not _is_resolved(doc.status):
		# Reopened: the old resolution is in the history; the next resolve needs a new one.
		doc.set(_resolution_field(doc), None)
	finishing = _is_resolved(doc.status) and not was_finished  # Resolved -> Closed is not
	if not finishing or not is_helpdesk_agent() or _has_notes(doc):
		_set_flag(doc)  # moved on, not an agent, or a resolution is given
		if finishing and _has_notes(doc):
			_record_resolution(doc)
		return
	asked_for = doc.status
	if not before:  # a new ticket has no status to keep
		frappe.throw(need_resolution())
	for field in RESOLVE_CHANGES:
		doc.set(field, before.get(field))
	_set_flag(doc, asked_for)
	if not _from_helpdesk_page():  # there the pop-up asks; elsewhere say it
		frappe.msgprint(need_resolution(), alert=True, indicator="red")


def _record_resolution(doc):
	"""Keep this resolution in Resolution History; on_update posts it as a ticket comment."""
	if not doc.meta.has_field(RESOLUTION_HISTORY):
		return
	from sas_fortuna.sas_fortuna.doctype.repair_order.repair_order import plain_text

	text = plain_text(doc.get(_resolution_field(doc)))  # keeps the lines, drops the tags
	doc.append(
		RESOLUTION_HISTORY,
		{"resolution": text, "resolved_by": frappe.session.user, "resolved_on": frappe.utils.now_datetime()},
	)
	doc.flags.new_resolution = text


def post_resolution_comment(doc):
	"""Show the resolution in the ticket's Comments on the Helpdesk page (agents only)."""
	text = doc.flags.pop("new_resolution", None)
	if not text or not frappe.db.exists("DocType", "HD Ticket Comment"):
		return
	body = frappe.utils.escape_html(text).replace("\n", "<br>")
	frappe.get_doc(
		{
			"doctype": "HD Ticket Comment",
			"reference_ticket": doc.name,
			"commented_by": frappe.session.user,
			"content": f"<p><b>{_('Resolution')}</b></p><p>{body}</p>",
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def resolution_asked(ticket):
	"""The Helpdesk page saw the flag: is this ticket really waiting for a resolution?

	Returns the status the agent picked (Resolved / Closed) and clears the flag, so the pop-up
	opens once and a reload never reopens it; None when there is nothing to ask. The server
	decides because the page may be showing a cached copy of the ticket. Nothing else on the
	ticket changes (not even its modified time)."""
	frappe.has_permission("HD Ticket", "write", ticket, throw=True)
	row = frappe.db.get_value("HD Ticket", ticket, [RESOLUTION_FLAG, ASKED_FOR], as_dict=True)
	if not row or not row.get(RESOLUTION_FLAG):
		return None
	frappe.db.set_value("HD Ticket", ticket, {RESOLUTION_FLAG: 0, ASKED_FOR: None}, update_modified=False)
	return row.get(ASKED_FOR) or "Resolved"


@frappe.whitelist()
def save_resolution_notes(ticket, notes):
	"""The Helpdesk pop-up's Save: store the resolution. The page then sets Resolved itself."""
	if not (notes or "").strip():
		frappe.throw(need_resolution())
	frappe.has_permission("HD Ticket", "write", ticket, throw=True)
	doc = frappe.get_doc("HD Ticket", ticket)
	lines = frappe.utils.escape_html(notes.strip()).splitlines()
	doc.set(_resolution_field(doc), "".join(f"<p>{line}</p>" for line in lines))
	doc.save()
	return doc.name


def resolve_ticket(ticket, note):
	"""Resolve a ticket from code (used when a repair is dispatched)."""
	doc = frappe.get_doc("HD Ticket", ticket)
	if doc.status in RESOLVED_STATES:
		return
	doc.set(_resolution_field(doc), note)
	doc.status = "Resolved"
	doc.save(ignore_permissions=True)  # system action, triggers Helpdesk e-mails
