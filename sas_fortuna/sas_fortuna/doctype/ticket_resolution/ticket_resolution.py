# Copyright (c) 2026, SAS Infosystem Pvt Ltd and contributors
# For license information, please see license.txt

"""Child row of HD Ticket > Resolution History: one resolution, who gave it and when.

Rows are added by support/hd_ticket.py each time the ticket is resolved, so a reopened ticket
keeps every earlier resolution. Read only."""

from frappe.model.document import Document


class TicketResolution(Document):
	pass
