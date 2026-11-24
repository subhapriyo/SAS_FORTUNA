"""Assignment Rule: a ticket goes to an engineer at the customer's branch.

How a new ticket finds its engineer
  1. On save the ticket gets its Job Location from the customer's Bill To city, else state,
     else Kolkata (support/hd_ticket.py apply_job_location), and its team from Ticket Type +
     Job Location (route_to_team).
  2. Helpdesk gives every team an Assignment Rule ("<team> - Support Rotation") whose
     engineers are the team's members. That rule picks the engineer.
  3. This class narrows the rule's engineers to the ticket's branch: engineers whose Job
     Location (HD Agent.custom_job_location) is the ticket's, who are switched on (HD Agent
     "Is Active") and not Unavailable (on leave). Away still counts: it is a short break.
  4. Helpdesk then chooses among them as it always does: Active before Away, then round
     robin, least busy or by weight.
  5. Nobody usable at that branch, or a ticket without one: the whole team, so a ticket is
     never left unassigned.

hooks.py: override_doctype_class["Assignment Rule"]. It builds on Helpdesk's own class
(helpdesk/overrides/assignment_rule.py), so Helpdesk's availability rules stay as they are.
"""

import frappe
from helpdesk.overrides import assignment_rule as helpdesk_rule
from helpdesk.overrides.assignment_rule import HelpdeskAssignmentRule

TICKET = "HD Ticket"
JOB_LOCATION = "custom_job_location"

# Where each rule type keeps its engineers. "Based on Field" takes the engineer from a field
# of the document, so there is no pool to narrow and it is left alone.
POOL_FIELDS = {
	"Round Robin": "users",
	"Load Balancing": "users",
	"Weighted Distribution": "weighted_users",
}


class FortunaAssignmentRule(HelpdeskAssignmentRule):
	def get_user(self, doc):
		"""The next engineer for this document: one at its branch when there is one to use,
		else anyone in the rule (Helpdesk's own choice)."""
		pool_field = POOL_FIELDS.get(self.rule)
		branch = doc.get(JOB_LOCATION) if doc.get("doctype") == TICKET else None
		if not pool_field or not branch:
			return super().get_user(doc)

		pool = getattr(self, pool_field)
		at_branch = branch_engineers(pool, branch)
		if not at_branch:
			return super().get_user(doc)  # nobody usable at that branch: the whole team

		# Narrow for this one choice, then put the rule's engineers back as they were (the rule
		# document can be cached and reused for the next ticket).
		setattr(self, pool_field, at_branch)
		try:
			return super().get_user(doc)
		finally:
			setattr(self, pool_field, pool)


def branch_engineers(pool, branch):
	"""The rule's rows (engineers) who work at this branch and can take a ticket now."""
	where = agent_locations([row.user for row in pool])
	on_leave = helpdesk_rule.get_agents_by_category("Unavailable")
	return [row for row in pool if where.get(row.user) == branch and row.user not in on_leave]


def agent_locations(users):
	"""{user: Job Location} for the switched-on engineers among these users (HD Agent is keyed
	by user). Inactive engineers and users who are not engineers are left out."""
	if not users:
		return {}
	return dict(
		frappe.get_all(
			"HD Agent",
			filters={"name": ["in", list(users)], "is_active": 1},
			fields=["name", JOB_LOCATION],
			as_list=True,
		)
	)
