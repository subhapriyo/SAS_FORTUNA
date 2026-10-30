"""Small Sales Order helpers  (N9).

'Create Ticket' button on Sales Order: help desk raises a Helpdesk ticket
against a service order, already linked to the right customer.
"""

import frappe
from frappe import _

from sas_fortuna.support.customer_sync import ensure_hd_customer


@frappe.whitelist()
def create_ticket_from_order(sales_order, subject=None, ticket_type=None):
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	ticket = frappe.get_doc(
		{
			"doctype": "HD Ticket",
			"subject": subject or _("Service request for {0}").format(so.name),
			"description": _("Raised from Sales Order {0}.").format(so.name),
			"raised_by": so.contact_email or frappe.session.user,
			"ticket_type": ticket_type,
			"customer": ensure_hd_customer(so.customer, so.customer_name),
			"custom_erpnext_customer": so.customer,
			"custom_sales_order": so.name,
		}
	)
	ticket.insert()
	return ticket.name
