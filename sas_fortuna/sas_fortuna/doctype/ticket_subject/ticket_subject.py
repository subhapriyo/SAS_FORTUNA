"""Ticket Subject: the predefined subjects on the Helpdesk New Ticket form, per Ticket Type.

The customer picks one from the Subject dropdown (HD Ticket.custom_issue_subject); "Others" is
added after them by subjects_for() and lets the customer type their own subject.
"""

import frappe
from frappe import _
from frappe.model.document import Document

OTHERS = "Others"


class TicketSubject(Document):
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


def is_offered(subject, ticket_type):
	"""True when the customer could pick this subject for this ticket type."""
	return subject == OTHERS or bool(
		frappe.db.exists("Ticket Subject", {"subject": subject, "ticket_type": ticket_type, "is_active": 1})
	)
