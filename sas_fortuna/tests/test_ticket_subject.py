"""Unit tests for the Subject dropdown on the Helpdesk New Ticket form: the Ticket Subject list,
the choices it gives per ticket type, and the server check on the ticket (support/hd_ticket.py).

Written test-first. ZZ-named records only; IntegrationTestCase rolls them back.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_ticket_subject
"""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.sas_fortuna.doctype.ticket_subject.ticket_subject import (
	OTHERS,
	SUBJECT_FIELD,
	is_offered,
	subject_options,
	subjects_for,
)
from sas_fortuna.support.hd_ticket import apply_issue_subject


def _ticket_type(name):
	if not frappe.db.exists("HD Ticket Type", name):
		frappe.get_doc({"doctype": "HD Ticket Type", "name": name}).insert(ignore_permissions=True)
	return name


def _subject(subject, ticket_type, active=1, order=0):
	return frappe.get_doc(
		{
			"doctype": "Ticket Subject",
			"subject": subject,
			"ticket_type": _ticket_type(ticket_type),
			"is_active": active,
			"sort_order": order,
		}
	).insert(ignore_permissions=True)


class FakeTicket(frappe._dict):
	"""Just enough of an HD Ticket for apply_issue_subject: changed unless told otherwise."""

	def has_value_changed(self, fieldname):
		return fieldname not in (self.get("_unchanged") or ())


class TestTicketSubjectList(IntegrationTestCase):
	def test_choices_follow_the_ticket_type_in_order_with_others_last(self):
		_subject("ZZ B second", "ZZ Type A", order=2)
		_subject("ZZ A first", "ZZ Type A", order=1)
		_subject("ZZ C same order, by name", "ZZ Type A", order=2)
		_subject("ZZ switched off", "ZZ Type A", active=0)
		_subject("ZZ other type", "ZZ Type B")
		self.assertEqual(
			subjects_for("ZZ Type A"), ["ZZ A first", "ZZ B second", "ZZ C same order, by name", OTHERS]
		)

	def test_a_type_without_subjects_still_offers_others(self):
		self.assertEqual(subjects_for(_ticket_type("ZZ Type Empty")), [OTHERS])
		self.assertEqual(subjects_for(None), [OTHERS])

	def test_others_is_built_in_and_cannot_be_added(self):
		with self.assertRaises(frappe.ValidationError):
			_subject(" others ", "ZZ Type A")

	def test_the_same_subject_twice_for_one_type_is_refused(self):
		_subject("ZZ Twice", "ZZ Type C")
		with self.assertRaises(frappe.ValidationError):
			_subject("ZZ Twice", "ZZ Type C")
		_subject("ZZ Twice", "ZZ Type D")  # another type may have it

	def test_is_offered(self):
		_subject("ZZ Offered", "ZZ Type E")
		_subject("ZZ Off", "ZZ Type E", active=0)
		self.assertTrue(is_offered("ZZ Offered", "ZZ Type E"))
		self.assertFalse(is_offered("ZZ Off", "ZZ Type E"))
		self.assertFalse(is_offered("ZZ Offered", "ZZ Type F"))
		self.assertTrue(is_offered(OTHERS, "anything"))

	def test_customers_get_the_choices_from_the_portal_api(self):
		from sas_fortuna.support.portal import ticket_subjects

		_subject("ZZ Api", "ZZ Type G")
		self.assertEqual(ticket_subjects("ZZ Type G"), ["ZZ Api", OTHERS])

	def test_all_types_come_in_one_call_for_the_form(self):
		# The form loads every type's choices once when it opens, so changing the ticket type
		# needs no server round trip.
		from sas_fortuna.support.portal import ticket_subjects_by_type

		_subject("ZZ All 2", "ZZ Type L", order=2)
		_subject("ZZ All 1", "ZZ Type L", order=1)
		_subject("ZZ All off", "ZZ Type L", active=0)
		_subject("ZZ All M", "ZZ Type M")
		choices = ticket_subjects_by_type()
		self.assertEqual(choices["ZZ Type L"], ["ZZ All 1", "ZZ All 2", OTHERS])
		self.assertEqual(choices["ZZ Type M"], ["ZZ All M", OTHERS])
		for ticket_type, subjects in choices.items():
			self.assertEqual(subjects, subjects_for(ticket_type), ticket_type)


class TestSubjectFieldOptions(IntegrationTestCase):
	"""The agent sidebar shows the saved subject only if it is one of the field's options."""

	def _field_options(self):
		return (
			frappe.db.get_value("Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}, "options")
			or ""
		).split("\n")

	def test_options_hold_every_subject_with_others_last(self):
		_subject("ZZ Opt on", "ZZ Type N")
		_subject("ZZ Opt off", "ZZ Type N", active=0)  # old tickets may still carry it
		options = subject_options()
		self.assertIn("ZZ Opt on", options)
		self.assertIn("ZZ Opt off", options)
		self.assertEqual(options[-1], OTHERS)
		self.assertEqual(options.count(OTHERS), 1)

	def test_a_new_ticket_gets_no_subject_by_default(self):
		# Frappe defaults a Select to its first option; that must be blank, or every e-mail /
		# agent ticket would silently get the first subject (and fail the subject check).
		if not frappe.db.exists("Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}):
			self.skipTest("Subject dropdown field not on this site")
		_subject("ZZ Opt first", "ZZ Type N")
		self.assertEqual(self._field_options()[0], "")
		self.assertFalse(frappe.new_doc("HD Ticket").get(SUBJECT_FIELD))

	def test_saving_a_subject_updates_the_field(self):
		if not frappe.db.exists("Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}):
			self.skipTest("Subject dropdown field not on this site")
		doc = _subject("ZZ Opt synced", "ZZ Type N")
		self.assertIn("ZZ Opt synced", self._field_options())
		doc.delete(ignore_permissions=True)
		self.assertNotIn("ZZ Opt synced", self._field_options())


class TestTicketValidation(IntegrationTestCase):
	def test_a_predefined_subject_becomes_the_ticket_subject(self):
		_subject("ZZ Fingerprint", "ZZ Type H")
		doc = FakeTicket(custom_issue_subject="ZZ Fingerprint", ticket_type="ZZ Type H", subject="x")
		apply_issue_subject(doc)
		self.assertEqual(doc.subject, "ZZ Fingerprint")

	def test_others_keeps_the_typed_subject_and_needs_one(self):
		doc = FakeTicket(custom_issue_subject=OTHERS, ticket_type="ZZ Type H", subject="Gate not opening")
		apply_issue_subject(doc)
		self.assertEqual(doc.subject, "Gate not opening")
		for typed in ("", "  ", OTHERS):
			with self.assertRaises(frappe.ValidationError):
				apply_issue_subject(
					FakeTicket(custom_issue_subject=OTHERS, ticket_type="ZZ Type H", subject=typed)
				)

	def test_a_subject_of_another_type_or_switched_off_is_refused(self):
		_subject("ZZ Only I", "ZZ Type I")
		_subject("ZZ Retired", "ZZ Type I", active=0)
		for choice, ticket_type in (("ZZ Only I", "ZZ Type J"), ("ZZ Retired", "ZZ Type I")):
			with self.assertRaises(frappe.ValidationError):
				apply_issue_subject(
					FakeTicket(custom_issue_subject=choice, ticket_type=ticket_type, subject="x")
				)

	def test_older_tickets_are_not_checked_again(self):
		_subject("ZZ Later off", "ZZ Type K", active=0)
		doc = FakeTicket(
			custom_issue_subject="ZZ Later off",
			ticket_type="ZZ Type K",
			subject="kept",
			_unchanged=("custom_issue_subject",),
		)
		apply_issue_subject(doc)  # no error
		self.assertEqual(doc.subject, "kept")

	def test_tickets_without_a_choice_are_left_alone(self):
		doc = FakeTicket(subject="From an e-mail", ticket_type=None)
		apply_issue_subject(doc)
		self.assertEqual(doc.subject, "From an e-mail")
