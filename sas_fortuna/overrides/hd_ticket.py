"""HD Ticket class: Helpdesk's ticket, with Customer as the 2nd column of the agents' ticket list.

What it changes
	/helpdesk/tickets builds its default columns from HD Ticket.default_list_data(). Fortuna's
	agents look for the customer first, so Customer moves to right after ID, before Subject.
	Same columns and widths otherwise; every bit of Helpdesk's ticket logic comes from the
	parent class unchanged.

What it leaves alone
	- the customer portal's ticket list (it has no Customer column)
	- a person's own saved view (HD View with its own columns) and the standard Public Views
	  (Pending Tickets, SLA Alerts, ...), which store their own column lists

Good to know
	- Not to be confused with support/hd_ticket.py: that file holds the ticket's doc events
	  (routing, Job Location, resolution notes); this one is the ticket's class.
	- Helpdesk's own tests/api/test_doc_list.py compares the list API with Helpdesk's original
	  column order, so on a site with sas_fortuna those three checks report the new order.
	- tests/test_ticket_list.py covers this file, end to end through the list API.

hooks.py: override_doctype_class["HD Ticket"] (via support/wiring.py).
"""

from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket

CUSTOMER = "customer"  # HD Ticket.customer: the Helpdesk customer shown in the list
ID = "name"


class FortunaHDTicket(HDTicket):
	@staticmethod
	def default_list_data(show_customer_portal_fields=False):
		"""Helpdesk's default list (columns + rows), with Customer moved next to ID."""
		data = HDTicket.default_list_data(show_customer_portal_fields)
		data["columns"] = customer_after_id(data["columns"])
		return data


def customer_after_id(columns):
	"""A copy of the columns with Customer right after ID (first when there is no ID column).

	Returns the columns unchanged (as a new list) when there is no Customer column, e.g. the
	customer portal's list. The list passed in is never modified."""
	customer = next((c for c in columns if c.get("key") == CUSTOMER), None)
	if not customer:
		return list(columns)
	rest = [c for c in columns if c is not customer]
	after_id = next((i + 1 for i, c in enumerate(rest) if c.get("key") == ID), 0)
	return rest[:after_id] + [customer] + rest[after_id:]
