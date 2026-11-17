"""Resolving a ticket needs a resolution (C3); every resolution is kept in a history.

Helpdesk's ticket page has no box for Resolution Details, and its Status dropdown saves straight
to the server (no hook for our code). So when an agent picks Resolved without a resolution:
  * the ticket keeps its previous status (nothing else changes) and is flagged
    custom_resolution_requested; the flag opens the Resolution pop-up on the Helpdesk ticket
    page (setup/data/fortuna_ticket_actions.js) and shows the sidebar box;
  * the pop-up saves the text (save_resolution_notes), then sets Resolved the normal way.
  * Off the Helpdesk page (Desk form, API) the server says "Please add a resolution ...".
Each resolve with a resolution adds a Resolution History row and a ticket comment; reopening
clears the current resolution (it stays in the history), so the next resolve asks again.
Customers and code (repair dispatch) resolve as before. Written test-first (TDD).

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_resolution_notes
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.setup import support_desk as sd
from sas_fortuna.support import hd_ticket

FLAG = "custom_resolution_requested"
ASKED_FOR = "custom_resolution_requested_status"  # Resolved or Closed: what the agent picked
NOTES = "resolution_details"
HISTORY = "custom_resolution_history"
NEED = "Please add a resolution message."  # the exact error text


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

	def _messages_after_resolve(self, helpdesk_page):
		t = _ticket()
		frappe.clear_messages()
		with patch.object(hd_ticket, "_from_helpdesk_page", return_value=helpdesk_page):
			_set(t, status="Resolved")
		return [str(m) for m in frappe.get_message_log()]

	def test_off_the_helpdesk_page_the_agent_is_told_to_add_a_resolution(self):
		self.assertTrue(any(NEED in m for m in self._messages_after_resolve(helpdesk_page=False)))

	def test_on_the_helpdesk_page_the_pop_up_asks_instead(self):
		self.assertFalse(any(NEED in m for m in self._messages_after_resolve(helpdesk_page=True)))

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


class TestClosedNeedsAResolutionToo(IntegrationTestCase):
	"""Closed is a finished status like Resolved: the same rule, the same pop-up."""

	def test_closing_without_a_resolution_keeps_the_status_and_asks(self):
		t = _ticket()
		t = _set(t, status="Closed")
		self.assertEqual((t.status, t.get(FLAG), t.get(ASKED_FOR)), ("Open", 1, "Closed"))
		self.assertFalse(t.resolution_date)

	def test_closing_shows_the_same_error_text(self):
		t = _ticket()
		frappe.clear_messages()
		with patch.object(hd_ticket, "_from_helpdesk_page", return_value=False):
			_set(t, status="Closed")
		self.assertIn(NEED, [frappe.parse_json(m).get("message") for m in frappe.get_message_log()])

	def test_closing_with_a_resolution_closes_and_keeps_it(self):
		t = _set(_ticket(), status="Closed", **{NOTES: "Customer confirmed it works."})
		self.assertEqual(t.status, "Closed")
		self.assertEqual([r.resolution for r in t.get(HISTORY)], ["Customer confirmed it works."])

	def test_resolved_then_closed_does_not_ask_again(self):
		t = _set(_ticket(), status="Resolved", **{NOTES: "Fixed."})
		t = _set(t, status="Closed")
		self.assertEqual((t.status, t.get(FLAG)), ("Closed", 0))
		self.assertEqual(len(t.get(HISTORY)), 1)  # still one resolution

	def test_reopening_a_closed_ticket_clears_the_resolution(self):
		t = _set(_ticket(), status="Closed", **{NOTES: "Fixed."})
		t = _set(t, status="Open")
		self.assertFalse(hd_ticket._has_notes(t))
		self.assertEqual(len(t.get(HISTORY)), 1)

	def test_helpdesk_auto_close_is_not_held_back(self):
		# Helpdesk's close_tickets_after_n_days saves with ignore_validate, as here.
		doc = frappe.get_doc("HD Ticket", _ticket().name)
		doc.status = "Closed"
		doc.flags.ignore_validate = True
		with patch.object(hd_ticket, "is_helpdesk_agent", return_value=True):
			doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("HD Ticket", doc.name, "status"), "Closed")

	def test_imported_old_tickets_are_left_to_the_importer(self):
		# legacy_import has its own checks and status guard for these; this rule stays out.
		t = _ticket()
		frappe.db.set_value("HD Ticket", t.name, "custom_is_legacy", 1)
		frappe.clear_messages()
		with patch("sas_fortuna.support.legacy_import.validate_legacy"):
			t = _set(t, status="Closed")
		self.assertFalse(t.get(FLAG))
		self.assertNotIn(NEED, " ".join(str(m) for m in frappe.get_message_log()))

	def test_the_flag_remembers_resolved_too(self):
		t = _set(_ticket(), status="Resolved")
		self.assertEqual(t.get(ASKED_FOR), "Resolved")

	def test_moving_on_clears_what_was_asked_for(self):
		t = _set(_ticket(), status="Closed")
		t = _set(t, status="Paused")
		self.assertEqual((t.get(FLAG), t.get(ASKED_FOR) or None), (0, None))


class TestResolutionHistory(IntegrationTestCase):
	def _history(self, t):
		return frappe.get_doc("HD Ticket", t.name).get(HISTORY)

	def test_a_resolve_adds_a_history_row(self):
		t = _set(_ticket(), status="Resolved", **{NOTES: "<p>Reset the device.</p>"})
		(row,) = self._history(t)
		self.assertEqual(row.resolution, "Reset the device.")
		self.assertEqual(row.resolved_by, frappe.session.user)
		self.assertTrue(row.resolved_on)

	def test_a_resolve_is_posted_as_a_ticket_comment(self):
		t = _set(_ticket(), status="Resolved", **{NOTES: "Replaced the battery."})
		comments = frappe.get_all("HD Ticket Comment", {"reference_ticket": t.name}, pluck="content")
		self.assertTrue(any("Replaced the battery." in c for c in comments), comments)

	def test_reopening_clears_the_resolution_but_keeps_the_history(self):
		t = _set(_ticket(), status="Resolved", **{NOTES: "First fix."})
		t = _set(t, status="Open")
		self.assertFalse(hd_ticket._has_notes(t))
		self.assertEqual([r.resolution for r in self._history(t)], ["First fix."])

	def test_resolving_again_asks_again_and_adds_a_second_row(self):
		t = _set(_ticket(), status="Resolved", **{NOTES: "First fix."})
		t = _set(t, status="Open")
		t = _set(t, status="Resolved")
		self.assertEqual((t.status, t.get(FLAG)), ("Open", 1))  # no resolution: asked again
		t = _set(t, status="Resolved", **{NOTES: "Second fix."})
		self.assertEqual([r.resolution for r in self._history(t)], ["First fix.", "Second fix."])

	def test_saving_without_a_status_change_adds_no_row(self):
		t = _set(_ticket(), status="Resolved", **{NOTES: "Fixed."})
		t = _set(t, priority=t.priority)  # any later save of a resolved ticket
		self.assertEqual(len(self._history(t)), 1)


class TestSaveResolutionNotes(IntegrationTestCase):
	"""The Helpdesk pop-up's Save: stores the resolution; the status is then set the normal way."""

	def test_empty_resolution_is_refused(self):
		t = _ticket()
		for empty in ("", "   ", None):
			with self.assertRaises(frappe.ValidationError) as caught:
				hd_ticket.save_resolution_notes(t.name, empty)
			self.assertEqual(str(caught.exception), NEED)

	def test_saves_the_resolution_and_leaves_the_status(self):
		t = _ticket()
		hd_ticket.save_resolution_notes(t.name, "Line one\nLine <two>")
		t = frappe.get_doc("HD Ticket", t.name)
		self.assertEqual(t.status, "Open")
		self.assertIn("Line one", t.get(NOTES))
		self.assertIn("&lt;two&gt;", t.get(NOTES))  # typed text is escaped, not run as HTML

	def test_needs_write_access_to_the_ticket(self):
		t = _ticket()
		with patch.object(hd_ticket.frappe, "has_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				hd_ticket.save_resolution_notes(t.name, "Fixed.")

	def test_then_resolved_goes_through(self):
		t = _set(_ticket(), status="Resolved")  # flagged: the pop-up opens
		hd_ticket.save_resolution_notes(t.name, "Fixed the cable.")
		t = _set(t, status="Resolved")
		self.assertEqual((t.status, t.get(FLAG)), ("Resolved", 0))


class TestPopUpOpened(IntegrationTestCase):
	"""The flag only asks for the pop-up; once it opens, it is cleared so a reload never reopens it."""

	def test_says_which_status_was_picked_once_then_nothing(self):
		# The page may show a cached copy of the ticket: the server decides whether to ask.
		t = _set(_ticket(), status="Closed")  # flagged
		self.assertEqual(hd_ticket.resolution_asked(t.name), "Closed")
		self.assertIsNone(hd_ticket.resolution_asked(t.name))  # already asked: no second pop-up
		self.assertIsNone(hd_ticket.resolution_asked(_ticket().name))  # never flagged

	def test_clears_the_flag_and_leaves_the_ticket_as_it_is(self):
		t = _set(_ticket(), status="Closed")  # flagged
		modified = frappe.db.get_value("HD Ticket", t.name, "modified")
		hd_ticket.resolution_asked(t.name)
		row = frappe.db.get_value("HD Ticket", t.name, ["status", FLAG, ASKED_FOR, "modified"], as_dict=True)
		self.assertEqual((row.status, row.get(FLAG), row.get(ASKED_FOR)), ("Open", 0, None))
		self.assertEqual(row.modified, modified)  # nothing else changed on the page

	def test_needs_write_access_to_the_ticket(self):
		t = _set(_ticket(), status="Resolved")
		with patch.object(hd_ticket.frappe, "has_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				hd_ticket.resolution_asked(t.name)

	def test_the_pop_up_save_still_goes_through_after_it(self):
		t = _set(_ticket(), status="Resolved")
		hd_ticket.resolution_asked(t.name)
		hd_ticket.save_resolution_notes(t.name, "Fixed.")
		t = _set(t, status="Resolved")
		self.assertEqual(t.status, "Resolved")


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
		asked = frappe.get_meta("HD Ticket").get_field(ASKED_FOR)
		self.assertEqual((asked.fieldtype, asked.hidden, asked.no_copy), ("Data", 1, 1))

	def test_box_shows_when_flagged_or_resolved(self):
		sd._resolution_box()
		depends_on = frappe.get_meta("HD Ticket").get_field(NOTES).depends_on
		for part in (FLAG, "'Resolved'"):
			self.assertIn(part, depends_on)

	def test_history_is_a_read_only_table_of_resolutions(self):
		df = frappe.get_meta("HD Ticket").get_field(HISTORY)
		self.assertEqual((df.fieldtype, df.options, df.read_only), ("Table", "Ticket Resolution", 1))
		child = frappe.get_meta("Ticket Resolution")
		self.assertTrue(child.istable)
		for field in ("resolution", "resolved_by", "resolved_on"):
			self.assertTrue(child.has_field(field), field)

	def test_resolution_is_not_an_editable_sidebar_field(self):
		# Entered only through the pop-up (so it reaches the history); shown read-only as a comment.
		self.assertNotIn(NOTES, [f["fieldname"] for f in sd.TICKET_FORM_FIELDS])

	def test_setup_takes_it_off_a_sidebar_that_has_it(self):
		template = frappe.get_doc("HD Ticket Template", "Default")
		if NOTES not in [r.fieldname for r in template.fields]:
			template.append("fields", {"fieldname": NOTES, "hide_from_customer": 1})
			template.save(ignore_permissions=True)
		sd._helpdesk_ticket_form()
		fields = [r.fieldname for r in frappe.get_doc("HD Ticket Template", "Default").fields]
		self.assertNotIn(NOTES, fields)
		self.assertIn("custom_job_location", fields)  # the rest stays
