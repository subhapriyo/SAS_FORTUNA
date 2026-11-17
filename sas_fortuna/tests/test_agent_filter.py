"""Unit tests: the ticket page's Assignee list (support/agent_filter.py).

Helpdesk's Assignee dropdown lists every active agent; the HD Agent permission rule narrows it,
on a ticket page only, to the ticket's Team at the ticket's Job Location (whole Team when nobody
is there). Managers see everyone. Written test-first; ZZ records, rolled back.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_agent_filter
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.support import agent_filter as af

TEAM = "ZZ AF Software"
HERE = "zz.af.kolkata@example.com"
AWAY = "zz.af.mumbai@example.com"
OUTSIDER = "zz.af.outsider@example.com"


def _location(name):
	if not frappe.db.exists("Job Location", name):
		frappe.get_doc({"doctype": "Job Location", "location_name": name}).insert(ignore_permissions=True)
	return name


def _agent(email, location=None):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("HD Agent", email):
		frappe.get_doc({"doctype": "HD Agent", "user": email, "agent_name": email}).insert(
			ignore_permissions=True
		)
	frappe.db.set_value("HD Agent", email, "custom_job_location", location)
	return email


class TestAgentFilter(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		_agent(HERE, _location("ZZ AF Kolkata"))
		_agent(AWAY, _location("ZZ AF Mumbai"))
		_agent(OUTSIDER, "ZZ AF Kolkata")  # right place, other team
		_location("ZZ AF Bihar")
		if not frappe.db.exists("HD Team", TEAM):
			frappe.get_doc(
				{"doctype": "HD Team", "team_name": TEAM, "users": [{"user": HERE}, {"user": AWAY}]}
			).insert(ignore_permissions=True)

	# --- who may take a ticket --------------------------------------------
	def test_team_members_at_the_location(self):
		self.assertEqual(af.eligible_agents(TEAM, "ZZ AF Kolkata"), [HERE])

	def test_whole_team_when_nobody_is_at_the_location(self):
		self.assertEqual(sorted(af.eligible_agents(TEAM, "ZZ AF Bihar")), sorted([HERE, AWAY]))
		self.assertEqual(sorted(af.eligible_agents(TEAM, None)), sorted([HERE, AWAY]))

	def test_no_team_means_no_limit(self):
		self.assertEqual(af.eligible_agents(None, "ZZ AF Kolkata"), [])
		self.assertEqual(af.eligible_agents("ZZ AF No Such Team", None), [])

	# --- the permission rule ----------------------------------------------
	def _rule(self, user, ticket=("ZZ T", TEAM, "ZZ AF Kolkata")):
		with patch.object(af, "ticket_from_request", return_value=ticket):
			return af.permission_query(user)

	def test_agents_get_only_eligible_agents(self):
		rule = self._rule(HERE)
		self.assertIn(frappe.db.escape(HERE), rule)
		self.assertNotIn(frappe.db.escape(AWAY), rule)

	def test_managers_and_other_pages_get_everyone(self):
		with patch.object(af.frappe, "get_roles", return_value=["Agent", "Agent Manager"]):
			self.assertEqual(self._rule(HERE), "")
		self.assertEqual(self._rule(HERE, ticket=None), "")

	def test_the_list_itself_is_narrowed(self):
		# End to end through Helpdesk's call: frappe.client.get_list("HD Agent") as an agent.
		frappe.set_user(HERE)
		self.addCleanup(frappe.set_user, "Administrator")
		with patch.object(af, "ticket_from_request", return_value=("ZZ T", TEAM, "ZZ AF Kolkata")):
			names = frappe.get_list("HD Agent", filters={"is_active": 1}, pluck="name")
		self.assertIn(HERE, names)
		self.assertNotIn(AWAY, names)
		self.assertNotIn(OUTSIDER, names)

	def test_server_side_queries_are_never_narrowed(self):
		with patch.object(af, "ticket_from_request", return_value=("ZZ T", TEAM, "ZZ AF Kolkata")):
			self.assertIn(AWAY, frappe.get_all("HD Agent", pluck="name"))

	# --- reading the ticket from the page ----------------------------------
	def test_ticket_page_is_read_from_the_referer(self):
		ticket = frappe.get_all("HD Ticket", pluck="name", limit=1)
		if not ticket:
			self.skipTest("no ticket on this site")
		for url, expected in (
			(f"http://site:8000/helpdesk/tickets/{ticket[0]}", ticket[0]),
			(f"http://site:8000/helpdesk/tickets/{ticket[0]}?tab=activity", ticket[0]),
			("http://site:8000/helpdesk/tickets", None),
			("http://site:8000/helpdesk/teams/ZZ", None),
			(None, None),
		):
			request = SimpleNamespace(headers={"Referer": url} if url else {})
			with patch.object(af.frappe.local, "request", request, create=True):
				found = af.ticket_from_request()
			self.assertEqual(found[0] if found else None, expected, url)
