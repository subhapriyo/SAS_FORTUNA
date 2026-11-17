"""Unit tests: a ticket's Helpdesk Customer (HD Ticket.customer).

Helpdesk reads a Contact's customers from the HD Customer's Contacts table (HD Customer Member),
so linked Contacts are made members (support/customer_sync.py), and the ticket's Customer follows
its ERPNext Customer (support/hd_ticket.py). ZZ-named records only; IntegrationTestCase rolls back.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_ticket_customer
"""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.support import customer_sync
from sas_fortuna.support.hd_ticket import apply_customer_from_sender

ZZ_CUSTOMER = "ZZ Ticket Customer Co"


def _leaf(doctype):
	return frappe.get_all(doctype, filters={"is_group": 0}, pluck="name", limit=1)[0]


def _hd_customer():
	"""The ZZ ERPNext Customer (created once) and its HD Customer; returns the HD Customer."""
	if not frappe.db.exists("Customer", ZZ_CUSTOMER):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": ZZ_CUSTOMER,
				"customer_type": "Company",
				"customer_group": _leaf("Customer Group"),
				"territory": _leaf("Territory"),
			}
		).insert(ignore_permissions=True)
	return customer_sync.ensure_hd_customer(ZZ_CUSTOMER, ZZ_CUSTOMER)


def _contact(email="zz.ticket.customer@example.com"):
	return frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": "ZZ Ticket",
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": ZZ_CUSTOMER}],
		}
	).insert(ignore_permissions=True)


def _members(hd_customer):
	return frappe.get_all(
		"HD Customer Member",
		filters={"parenttype": "HD Customer", "parent": hd_customer},
		pluck="contact_name",
	)


class TestCustomerMembers(IntegrationTestCase):
	def test_a_customers_contact_becomes_a_member(self):
		hd = _hd_customer()
		contact = _contact()
		self.assertIn(contact.name, _members(hd))

	def test_backfill_adds_missing_members_once(self):
		hd = _hd_customer()
		contact = _contact("zz.backfill.member@example.com")
		frappe.db.delete("HD Customer Member", {"parent": hd, "contact_name": contact.name})
		self.assertTrue(any(contact.name in line for line in customer_sync.sync_customer_members()))
		self.assertIn(contact.name, _members(hd))
		self.assertFalse(any(contact.name in line for line in customer_sync.sync_customer_members()))


class TestTicketCustomerBackfill(IntegrationTestCase):
	def test_old_ticket_gets_its_customer_from_the_erpnext_customer(self):
		hd = _hd_customer()
		ticket = frappe.get_all("HD Ticket", pluck="name", limit=1)
		if not ticket:
			self.skipTest("no ticket on this site")
		frappe.db.set_value(
			"HD Ticket",
			ticket[0],
			{"customer": None, "custom_erpnext_customer": ZZ_CUSTOMER},
			update_modified=False,
		)
		customer_sync.backfill_ticket_customers()
		self.assertEqual(frappe.db.get_value("HD Ticket", ticket[0], "customer"), hd)


class TestTicketCustomer(IntegrationTestCase):
	def test_customer_follows_the_erpnext_customer(self):
		hd = _hd_customer()
		doc = frappe._dict(custom_erpnext_customer=ZZ_CUSTOMER, customer=None, raised_by=None)
		apply_customer_from_sender(doc)
		self.assertEqual(doc.customer, hd)

	def test_a_chosen_customer_is_kept(self):
		_hd_customer()
		doc = frappe._dict(custom_erpnext_customer=ZZ_CUSTOMER, customer="Someone Else", raised_by=None)
		apply_customer_from_sender(doc)
		self.assertEqual(doc.customer, "Someone Else")
