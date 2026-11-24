"""Unit tests: the Helpdesk ticket list (/helpdesk/tickets) shows Customer as the 2nd column.

Helpdesk builds the default columns in HD Ticket.default_list_data(); overrides/hd_ticket.py
moves Customer right after ID, before Subject. Everything else stays as Helpdesk ships it.
A person's own saved view (HD View) keeps the columns they chose.

Written test-first.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_ticket_list
"""

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase

from sas_fortuna.overrides import hd_ticket as ticket_override


def _keys(columns):
	return [c["key"] for c in columns]


class TestCustomerColumn(IntegrationTestCase):
	def test_customer_is_the_second_column(self):
		keys = _keys(get_controller("HD Ticket").default_list_data()["columns"])
		self.assertEqual(keys[:3], ["name", "customer", "subject"])

	def test_no_column_is_added_or_lost(self):
		from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket

		helpdesk = _keys(HDTicket.default_list_data()["columns"])
		ours = _keys(get_controller("HD Ticket").default_list_data()["columns"])
		self.assertEqual(sorted(ours), sorted(helpdesk))

	def test_customer_portal_list_is_left_alone(self):
		# Customers see only their own tickets: Helpdesk shows them no Customer column.
		from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket

		self.assertEqual(
			get_controller("HD Ticket").default_list_data(True)["columns"],
			HDTicket.default_list_data(True)["columns"],
		)

	def test_rows_are_unchanged(self):
		from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket

		self.assertEqual(
			get_controller("HD Ticket").default_list_data()["rows"], HDTicket.default_list_data()["rows"]
		)

	def test_moving_tolerates_a_missing_column(self):
		cols = [{"key": "name"}, {"key": "subject"}]
		self.assertEqual(_keys(ticket_override.customer_after_id(cols)), ["name", "subject"])
		cols = [{"key": "subject"}, {"key": "customer"}]  # no ID column: Customer leads
		self.assertEqual(_keys(ticket_override.customer_after_id(cols)), ["customer", "subject"])

	def test_moving_does_not_change_the_list_it_was_given(self):
		cols = [{"key": "name"}, {"key": "subject"}, {"key": "customer"}]
		ticket_override.customer_after_id(cols)
		self.assertEqual(_keys(cols), ["name", "subject", "customer"])

	def test_hd_ticket_uses_this_class(self):
		from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket

		self.assertEqual(
			frappe.get_hooks("override_doctype_class").get("HD Ticket"),
			["sas_fortuna.overrides.hd_ticket.FortunaHDTicket"],
		)
		self.assertTrue(issubclass(get_controller("HD Ticket"), HDTicket))  # Helpdesk's ticket logic kept
