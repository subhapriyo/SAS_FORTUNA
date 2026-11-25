"""Unit tests: a new ticket goes to an engineer at the customer's branch.

  1. The ticket's Job Location comes from the customer's Ship To (else Bill To) city/state, else Kolkata
     (support/hd_ticket.py apply_job_location; test_new_ticket_form.py covers the address).
  2. The ticket's team assigns it through its Assignment Rule (Helpdesk: "<team> - Support
     Rotation"). overrides/assignment_rule.py narrows the rule's engineers to those whose
     Job Location (HD Agent.custom_job_location) is the ticket's; Helpdesk's own choice
     (Active before Away, round robin or least busy) then picks among them.
  3. No engineer of the team at that branch: the whole team stays in the pool, so a ticket
     is never left unassigned.

Written test-first.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_ticket_assignment
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.overrides import assignment_rule as ar

KOL, MUM1, MUM2 = "zz.kol@example.com", "zz.mum1@example.com", "zz.mum2@example.com"
WHERE = {KOL: "Kolkata", MUM1: "Mumbai", MUM2: "Mumbai"}


def _rule(rule="Round Robin", users=(KOL, MUM1, MUM2)):
	"""An Assignment Rule in memory: Frappe builds it with the class hooks.py names."""
	field = "weighted_users" if rule == "Weighted Distribution" else "users"
	rows = [{"user": u, "weight": 1} if field == "weighted_users" else {"user": u} for u in users]
	return frappe.get_doc(
		{
			"doctype": "Assignment Rule",
			"name": "ZZ Rule",
			"rule": rule,
			"document_type": "HD Ticket",
			field: rows,
		}
	)


def _ticket(job_location):
	return frappe._dict(doctype="HD Ticket", custom_job_location=job_location)


class TestAssignByJobLocation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.away, self.unavailable = set(), set()  # everyone Active unless a test says otherwise
		by_category = {"Away": self.away, "Unavailable": self.unavailable}
		for p in (
			patch.object(ar, "agent_locations", side_effect=lambda users: {u: WHERE.get(u) for u in users}),
			patch(
				"helpdesk.overrides.assignment_rule.get_agents_by_category",
				side_effect=lambda category: by_category.get(category, set()),
			),
		):
			p.start()
			self.addCleanup(p.stop)

	def test_engineer_at_the_ticket_branch_is_picked(self):
		self.assertEqual(_rule().get_user(_ticket("Mumbai")), MUM1)

	def test_least_busy_engineer_at_the_branch(self):
		counts = {KOL: 0, MUM1: 5, MUM2: 1}  # Kolkata is idle, but not at the branch
		with patch.object(frappe.db, "count", side_effect=lambda dt, f: counts[f["allocated_to"]]):
			self.assertEqual(_rule("Load Balancing").get_user(_ticket("Mumbai")), MUM2)

	def test_weighted_rules_pick_at_the_branch_too(self):
		self.assertIn(_rule("Weighted Distribution").get_user(_ticket("Mumbai")), (MUM1, MUM2))

	def test_unavailable_engineer_at_the_branch_is_skipped(self):
		self.unavailable.add(MUM1)
		self.assertEqual(_rule().get_user(_ticket("Mumbai")), MUM2)

	def test_branch_all_unavailable_hands_over_to_the_team(self):
		# On leave at the branch: an Active engineer elsewhere beats waiting for them.
		self.unavailable.update({MUM1, MUM2})
		self.assertEqual(_rule().get_user(_ticket("Mumbai")), KOL)

	def test_away_engineer_at_the_branch_is_still_preferred(self):
		# Away is a short break; the ticket stays with the customer's branch.
		self.away.update({MUM1, MUM2})
		self.assertIn(_rule().get_user(_ticket("Mumbai")), (MUM1, MUM2))

	def test_based_on_field_rules_are_left_alone(self):
		rule = _rule("Based on Field")
		with patch.object(ar.HelpdeskAssignmentRule, "get_user", return_value="zz.field@example.com") as base:
			self.assertEqual(rule.get_user(_ticket("Mumbai")), "zz.field@example.com")
		self.assertEqual([u.user for u in rule.users], [KOL, MUM1, MUM2])
		base.assert_called_once()

	def test_no_engineer_at_the_branch_keeps_the_whole_team(self):
		self.assertEqual(_rule().get_user(_ticket("Nagpur")), KOL)

	def test_ticket_without_a_branch_keeps_the_whole_team(self):
		self.assertEqual(_rule().get_user(_ticket(None)), KOL)

	def test_rule_keeps_its_engineers_after_choosing(self):
		rule = _rule()
		rule.get_user(_ticket("Mumbai"))
		self.assertEqual([u.user for u in rule.users], [KOL, MUM1, MUM2])

	def test_other_documents_are_assigned_as_before(self):
		other = frappe._dict(doctype="ToDo", custom_job_location="Mumbai")
		self.assertEqual(_rule().get_user(other), KOL)

	def test_assignment_rules_use_this_class(self):
		from helpdesk.overrides.assignment_rule import HelpdeskAssignmentRule

		rule = _rule()
		self.assertIsInstance(rule, ar.FortunaAssignmentRule)
		self.assertIsInstance(rule, HelpdeskAssignmentRule)  # Helpdesk's availability tiers kept


class TestAgentLocations(IntegrationTestCase):
	def test_reads_each_engineers_job_location(self):
		user = "zz.assign.agent@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "ZZ Assign", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("HD Agent", user):
			frappe.get_doc({"doctype": "HD Agent", "user": user, "agent_name": "ZZ Assign"}).insert(
				ignore_permissions=True
			)
		frappe.db.set_value("HD Agent", user, "custom_job_location", None)
		if not frappe.db.exists("Job Location", "ZZ Assign Town"):
			frappe.get_doc(
				{"doctype": "Job Location", "location_name": "ZZ Assign Town", "cities": "Zzassign"}
			).insert(ignore_permissions=True)
		frappe.db.set_value("HD Agent", user, {"custom_job_location": "ZZ Assign Town", "is_active": 1})
		self.assertEqual(ar.agent_locations([user, "zz.not.an.agent@example.com"]), {user: "ZZ Assign Town"})
		# Switched-off engineers are nobody's branch engineer.
		frappe.db.set_value("HD Agent", user, "is_active", 0)
		self.assertEqual(ar.agent_locations([user]), {})
