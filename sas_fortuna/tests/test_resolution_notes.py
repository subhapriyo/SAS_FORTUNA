"""Resolving a ticket needs resolution notes (C3), and the agent is shown where to type them.

Helpdesk's ticket page has no box for Resolution Details, and its Status dropdown saves straight
to the server (no hook for our code). So when an agent picks Resolved without notes:
  * the ticket keeps its previous status (nothing else changes) and is flagged
    custom_resolution_requested;
  * the flag shows the Resolution Details box in the ticket sidebar (the field's Depends On);
  * with the notes typed, picking Resolved again resolves it and clears the flag.
Customers and code (repair dispatch) resolve as before. Written test-first (TDD).

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_resolution_notes
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.setup import support_desk as sd
from sas_fortuna.support import hd_ticket

FLAG = "custom_resolution_requested"
NOTES = "resolution_details"


def _ticket(**values):
	return frappe.get_doc(
		{
			"doctype": "HD Ticket",
			"subject": "ZZ resolution notes",
			"raised_by": "zz.resolution@example.com",
			"description": "<p>Device not reading thumbs</p>",
			**values,
		}
	).insert(ignore_permissions=True)


def _set(ticket, agent=True, **values):
	"""Save `values` on the ticket the way Helpdesk does (one field at a time, as an agent)."""
	doc = frappe.get_doc("HD Ticket", ticket.name)
	doc.update(values)
	with patch.object(hd_ticket, "is_helpdesk_agent", return_value=agent):
		doc.save(ignore_permissions=True)
	return frappe.get_doc("HD Ticket", ticket.name)


class TestResolveWithoutNotes(IntegrationTestCase):
	def test_ticket_keeps_its_status_and_is_flagged(self):
		t = _ticket()
		before = (t.status, t.status_category)
		t = _set(t, status="Resolved")
		self.assertEqual((t.status, t.status_category), before)
		self.assertEqual(t.get(FLAG), 1)

	def test_nothing_of_a_resolve_is_kept(self):
		t = _ticket()
		t = _set(t, status="Resolved")
		self.assertFalse(t.resolution_date)
		self.assertFalse(t.first_responded_on)  # Helpdesk stamps it when Open -> Resolved

	def test_the_agent_is_told_where_to_type_them(self):
		t = _ticket()
		frappe.clear_messages()
		_set(t, status="Resolved")
		self.assertTrue(any("Resolution Details" in str(m) for m in frappe.get_message_log()))

	def test_blank_notes_count_as_none(self):
		t = _ticket()
		t = _set(t, status="Resolved", **{NOTES: "<p> </p>"})
		self.assertNotEqual(t.status, "Resolved")
		self.assertEqual(t.get(FLAG), 1)


class TestResolveWithNotes(IntegrationTestCase):
	def test_notes_then_resolved_resolves_and_clears_the_flag(self):
		t = _ticket()
		t = _set(t, status="Resolved")
		t = _set(t, **{NOTES: "Replaced the sensor."})
		self.assertEqual(t.get(FLAG), 1)  # box stays until resolved
		t = _set(t, status="Resolved")
		self.assertEqual(t.status, "Resolved")
		self.assertEqual(t.get(FLAG), 0)
		self.assertTrue(t.resolution_date)

	def test_notes_first_resolves_at_once(self):
		t = _ticket()
		t = _set(t, status="Resolved", **{NOTES: "Reset the device."})
		self.assertEqual(t.status, "Resolved")
		self.assertFalse(t.get(FLAG))

	def test_moving_to_another_status_clears_the_flag(self):
		t = _ticket()
		t = _set(t, status="Resolved")
		t = _set(t, status="Paused")
		self.assertEqual(t.status, "Paused")
		self.assertEqual(t.get(FLAG), 0)


class TestOthersResolveAsBefore(IntegrationTestCase):
	def test_customer_may_resolve_without_notes(self):
		t = _ticket()
		t = _set(t, agent=False, status="Resolved")
		self.assertEqual(t.status, "Resolved")
		self.assertFalse(t.get(FLAG))

	def test_code_resolves_with_its_own_note(self):
		t = _ticket()
		with patch.object(hd_ticket, "is_helpdesk_agent", return_value=True):
			hd_ticket.resolve_ticket(t.name, "Unit dispatched.")
		self.assertEqual(frappe.db.get_value("HD Ticket", t.name, "status"), "Resolved")


class TestResolutionBoxSetup(IntegrationTestCase):
	def test_flag_is_a_hidden_check_on_the_ticket(self):
		df = frappe.get_meta("HD Ticket").get_field(FLAG)
		self.assertEqual((df.fieldtype, df.hidden, df.no_copy), ("Check", 1, 1))

	def test_box_shows_when_flagged_or_resolved(self):
		sd._resolution_box()
		depends_on = frappe.get_meta("HD Ticket").get_field(NOTES).depends_on
		for part in (FLAG, "'Resolved'"):
			self.assertIn(part, depends_on)

	def test_box_is_in_the_agent_sidebar_not_the_customer_form(self):
		row = next(f for f in sd.TICKET_FORM_FIELDS if f["fieldname"] == NOTES)
		self.assertEqual((row["hide_from_customer"], row["required"]), (1, 0))
