"""Ticket Subject: the predefined subjects on the Helpdesk New Ticket form, per Ticket Type.

The customer picks one from the Subject dropdown (HD Ticket.custom_issue_subject); "Others" is
added after them by subjects_for() and lets the customer type their own subject.
"""

import frappe
from frappe import _
from frappe.model.document import Document

OTHERS = "Others"
SUBJECT_FIELD = "custom_issue_subject"


class TicketSubject(Document):
	# Any add, edit or delete changes the dropdown's choices on HD Ticket.
	def on_update(self):
		sync_subject_options()

	def after_delete(self):
		sync_subject_options()

	def validate(self):
		self.subject = (self.subject or "").strip()
		if self.subject.lower() == OTHERS.lower():
			frappe.throw(_('"{0}" is always offered last; it need not be added.').format(OTHERS))
		duplicate = frappe.db.exists(
			"Ticket Subject",
			{"subject": self.subject, "ticket_type": self.ticket_type, "name": ["!=", self.name]},
		)
		if duplicate:
			frappe.throw(_("{0} already has the subject {1}.").format(self.ticket_type, self.subject))


def subjects_for(ticket_type):
	"""Active subjects of a ticket type, in dropdown order, with Others last."""
	rows = []
	if ticket_type:
		rows = frappe.get_all(
			"Ticket Subject",
			filters={"ticket_type": ticket_type, "is_active": 1},
			pluck="subject",
			order_by="sort_order asc, subject asc",
		)
	return [*rows, OTHERS]


def subjects_by_type():
	"""Every ticket type's active subjects in one query, each list with Others last."""
	choices = {}
	for row in frappe.get_all(
		"Ticket Subject",
		filters={"is_active": 1},
		fields=["ticket_type", "subject"],
		order_by="ticket_type asc, sort_order asc, subject asc",
	):
		choices.setdefault(row.ticket_type, []).append(row.subject)
	return {ticket_type: [*subjects, OTHERS] for ticket_type, subjects in choices.items()}


def subject_options():
	"""Every value the Subject dropdown may hold: all Ticket Subjects (active or not), any value
	already on a ticket (so a removed subject never breaks saving those tickets), Others last."""
	values = set(frappe.get_all("Ticket Subject", pluck="subject"))
	if frappe.get_meta("HD Ticket").has_field(SUBJECT_FIELD):
		values |= set(
			frappe.get_all(
				"HD Ticket", filters={SUBJECT_FIELD: ["is", "set"]}, pluck=SUBJECT_FIELD, distinct=True
			)
		)
	values.discard(OTHERS)
	return [*sorted(v for v in values if v), OTHERS]


def sync_subject_options():
	"""Copy subject_options() onto the HD Ticket Select field.

	The New Ticket form narrows the choices per ticket type in the browser (form script), but
	the agent's ticket sidebar shows a Select only through the field's own options: with none,
	a saved subject reads as the empty "Choose the closest subject"."""
	cf = frappe.db.get_value(
		"Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}, ["name", "options"], as_dict=True
	)
	if not cf:
		return []  # field not on this site (created by setup/fortuna_impex.py)
	choices = subject_options()
	options = "\n".join(choices)
	if (cf.options or "") == options:
		return []  # already in step: no write, no cache clear
	# Select options need no column change, so a direct write plus a cache clear is enough.
	frappe.db.set_value("Custom Field", cf.name, "options", options, update_modified=False)
	frappe.clear_cache(doctype="HD Ticket")
	return [f"HD Ticket Subject dropdown: {len(choices)} choices"]


def is_offered(subject, ticket_type):
	"""True when the customer could pick this subject for this ticket type."""
	return subject == OTHERS or bool(
		frappe.db.exists("Ticket Subject", {"subject": subject, "ticket_type": ticket_type, "is_active": 1})
	)
