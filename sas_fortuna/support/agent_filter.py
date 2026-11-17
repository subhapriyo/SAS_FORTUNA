"""The ticket page's Assignee list: only agents of the ticket's Team at the ticket's Job Location.

Helpdesk's Assignee dropdown (helpdesk desk/src/components/ticket-agent/AssignTo.vue) lists every
active HD Agent through frappe.client.get_list and never looks at the ticket's Team. This module is
the HD Agent permission_query_conditions hook (support/wiring.py), so when that list is asked for
from a ticket page (/helpdesk/tickets/<name>, read from the request's Referer) it returns:

  - the ticket's Team members whose Job Location is the ticket's Job Location
  - nobody of the Team there (or no location on the ticket) -> the whole Team
  - no Team on the ticket, an empty Team, or not a ticket page -> no limit

Agent Managers and System Managers always see every agent, so they can override.
Only permission-checked lists are narrowed: server code (frappe.get_all) is not. Two Helpdesk
behaviours stay as they are: the signed-in agent is always offered (to assign themself), and an
agent already assigned stays listed.
"""

import re
from urllib.parse import unquote, urlparse

import frappe

TICKET_PAGE = re.compile(r"^/helpdesk/tickets/([^/?#]+)")
MANAGER_ROLES = {"Agent Manager", "System Manager"}
LOCATION_FIELD = "custom_job_location"  # HD Agent and HD Ticket (setup/support_desk.py)


def permission_query(user=None, doctype=None):
	"""SQL condition for HD Agent lists; "" (no limit) unless an agent is on a ticket page."""
	user = user or frappe.session.user
	ticket = ticket_from_request()
	if not ticket or MANAGER_ROLES & set(frappe.get_roles(user)):
		return ""
	_name, team, location = ticket
	agents = eligible_agents(team, location)
	if not agents:
		return ""
	names = ", ".join(frappe.db.escape(agent) for agent in sorted(agents))
	return f"`tabHD Agent`.`name` in ({names})"


def ticket_from_request():
	"""(ticket, team, job location) of the Helpdesk ticket page this request comes from, else None."""
	request = getattr(frappe.local, "request", None)
	referer = request.headers.get("Referer") if request is not None else None
	match = TICKET_PAGE.match(urlparse(referer or "").path)
	if not match:
		return None
	name = unquote(match.group(1))
	fields = ["name", "agent_group"]
	if frappe.get_meta("HD Ticket").has_field(LOCATION_FIELD):
		fields.append(LOCATION_FIELD)
	row = frappe.db.get_value("HD Ticket", name, fields, as_dict=True)
	if not row:
		return None
	return row.name, row.agent_group, row.get(LOCATION_FIELD)


def eligible_agents(team, location):
	"""Agents who may take a ticket of this Team at this Job Location ([] = no limit)."""
	if not team:
		return []
	members = frappe.get_all(
		"HD Team Member", filters={"parenttype": "HD Team", "parent": team}, pluck="user"
	)
	if not members:
		return []
	if location and frappe.get_meta("HD Agent").has_field(LOCATION_FIELD):
		here = frappe.get_all(
			"HD Agent",
			filters={"name": ["in", members], LOCATION_FIELD: location, "is_active": 1},
			pluck="name",
		)
		if here:
			return here
	return members
