"""HD Ticket: Helpdesk's ticket, with Customer as the 2nd column of the agents' ticket list.

Helpdesk builds the default columns of /helpdesk/tickets in HD Ticket.default_list_data().
Fortuna's agents look for the customer first, so Customer moves to right after ID (before
Subject). Nothing else changes: same columns, same widths, and all of Helpdesk's ticket logic
comes from the parent class. A person's own saved view keeps the columns they chose; the
customer portal's list has no Customer column and is left as it is.

hooks.py: override_doctype_class["HD Ticket"] (via support/wiring.py).
"""

from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket

CUSTOMER = "customer"
ID = "name"


class FortunaHDTicket(HDTicket):
	@staticmethod
	def default_list_data(show_customer_portal_fields=False):
		"""Helpdesk's default list, with Customer moved next to ID."""
		data = HDTicket.default_list_data(show_customer_portal_fields)
		data["columns"] = customer_after_id(data["columns"])
		return data


def customer_after_id(columns):
	"""A copy of the columns with Customer right after ID (first when there is no ID column).
	Unchanged when there is no Customer column."""
	customer = next((c for c in columns if c.get("key") == CUSTOMER), None)
	if not customer:
		return list(columns)
	rest = [c for c in columns if c is not customer]
	at = next((i + 1 for i, c in enumerate(rest) if c.get("key") == ID), 0)
	return rest[:at] + [customer] + rest[at:]
