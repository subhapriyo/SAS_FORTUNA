"""Assignment Rule: a ticket goes to an engineer at the customer's branch.

How a new ticket finds its engineer:
  1. On save the ticket gets its Job Location from the customer's Bill To city, else state,
     else Kolkata (support/hd_ticket.py apply_job_location), and its team from Ticket Type +
     Job Location (route_to_team).
  2. Helpdesk gives every team an Assignment Rule ("<team> - Support Rotation") whose
     engineers are the team's members. That rule picks the engineer.
  3. This class narrows the rule's engineers to those whose Job Location
     (HD Agent.custom_job_location) is the ticket's, then lets Helpdesk choose among them as
     it always does: Active before Away, then round robin, least busy or by weight.
  4. No engineer of the team at that branch, or a ticket without one: the whole team, so a
     ticket is never left unassigned.

hooks.py: override_doctype_class["Assignment Rule"]. It builds on Helpdesk's own class
(helpdesk/overrides/assignment_rule.py), so Helpdesk's availability rules stay as they are.
"""

import frappe
from helpdesk.overrides.assignment_rule import HelpdeskAssignmentRule

TICKET = "HD Ticket"
JOB_LOCATION = "custom_job_location"


class FortunaAssignmentRule(HelpdeskAssignmentRule):
	def get_user(self, doc):
		"""The next engineer for this document, from those at its Job Location when there are any."""
		pool_field = _pool_field(self.rule)
		branch = doc.get(JOB_LOCATION) if doc.get("doctype") == TICKET else None
		if not pool_field or not branch:
			return super().get_user(doc)

		pool = getattr(self, pool_field)
		where = agent_locations([row.user for row in pool])
		at_branch = [row for row in pool if where.get(row.user) == branch]
		if not at_branch:
			return super().get_user(doc)  # nobody at that branch: anyone in the team

		# Narrow for this one choice, then put the rule's engineers back as they were.
		setattr(self, pool_field, at_branch)
		try:
			return super().get_user(doc)
		finally:
			setattr(self, pool_field, pool)


def _pool_field(rule):
	"""Where a rule keeps its engineers. "Based on Field" names one in the document: left alone."""
	if rule == "Weighted Distribution":
		return "weighted_users"
	if rule in ("Round Robin", "Load Balancing"):
		return "users"
	return None


def agent_locations(users):
	"""{user: Job Location} for the engineers among these users (HD Agent is keyed by user)."""
	if not users:
		return {}
	return dict(
		frappe.get_all(
			"HD Agent",
			filters={"name": ["in", list(users)]},
			fields=["name", JOB_LOCATION],
			as_list=True,
		)
	)
