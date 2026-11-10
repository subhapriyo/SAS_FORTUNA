"""Unit tests for support/customer_sync.py — keeping one customer identity across
ERPNext (Customer) and Helpdesk (HD Customer), and giving portal users the Helpdesk role.

Written test-first (TDD): these exercise every public function in customer_sync.py.
    bench --site fortuna.localhost run-tests --app sas_fortuna --module sas_fortuna.tests.test_customer_sync
"""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.support import customer_sync as cs

CUSTOMER_ROLE = cs.HELPDESK_CUSTOMER_ROLE


class TestEnsureHdCustomer(IntegrationTestCase):
	def _customer(self, **changes):
		values = {"doctype": "Customer", "customer_name": "ZZ Sync Co", "customer_type": "Company"}
		values.update(changes)
		doc = frappe.get_doc(values).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Customer", doc.name, force=True, ignore_permissions=True))
		return doc

	def test_new_customer_gets_a_matching_hd_customer(self):
		customer = self._customer()
		hd_name = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": customer.name}, "name")
		self.assertTrue(hd_name)
		self.addCleanup(
			lambda: frappe.delete_doc("HD Customer", hd_name, force=True, ignore_permissions=True)
		)

	def test_ensure_hd_customer_is_idempotent(self):
		customer = self._customer()
		first = cs.ensure_hd_customer(customer.name, customer.customer_name)
		second = cs.ensure_hd_customer(customer.name, customer.customer_name)
		self.assertEqual(first, second)
		self.addCleanup(lambda: frappe.delete_doc("HD Customer", first, force=True, ignore_permissions=True))

	def test_ensure_hd_customer_links_an_existing_hd_customer_instead_of_duplicating(self):
		name = "ZZ Pre-existing HD Customer"
		frappe.delete_doc("HD Customer", name, force=True, ignore_permissions=True)
		pre = frappe.get_doc({"doctype": "HD Customer", "customer_name": name}).insert(
			ignore_permissions=True
		)
		self.addCleanup(lambda: frappe.delete_doc("HD Customer", name, force=True, ignore_permissions=True))

		customer = self._customer(customer_name=name)
		linked = cs.ensure_hd_customer(customer.name, name)
		self.assertEqual(linked, pre.name)
		self.assertEqual(
			frappe.db.get_value("HD Customer", pre.name, "custom_erpnext_customer"), customer.name
		)
		# still exactly one HD Customer with that name, not a duplicate
		self.assertEqual(frappe.db.count("HD Customer", {"customer_name": name}), 1)


class TestContactValidate(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.delete_doc("Role", CUSTOMER_ROLE, force=True, ignore_permissions=True) if False else None

	def _customer_with_hd(self, name="ZZ Contact Sync Co"):
		frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": name, "customer_type": "Company"}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Customer", name, force=True, ignore_permissions=True))
		hd_name = cs.ensure_hd_customer(customer.name, name)
		self.addCleanup(
			lambda: frappe.delete_doc("HD Customer", hd_name, force=True, ignore_permissions=True)
		)
		return customer, hd_name

	def test_contact_linked_to_customer_is_also_linked_to_its_hd_customer(self):
		customer, hd_name = self._customer_with_hd()
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "ZZ Sync Contact",
				"links": [{"link_doctype": "Customer", "link_name": customer.name}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Contact", contact.name, force=True, ignore_permissions=True)
		)
		link_pairs = {(row.link_doctype, row.link_name) for row in contact.links}
		self.assertIn(("HD Customer", hd_name), link_pairs)

	def test_contact_validate_does_not_duplicate_an_existing_hd_customer_link(self):
		customer, hd_name = self._customer_with_hd()
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "ZZ Sync Contact 2",
				"links": [
					{"link_doctype": "Customer", "link_name": customer.name},
					{"link_doctype": "HD Customer", "link_name": hd_name},
				],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Contact", contact.name, force=True, ignore_permissions=True)
		)
		pairs = [(row.link_doctype, row.link_name) for row in contact.links]
		self.assertEqual(pairs.count(("HD Customer", hd_name)), 1)

	def test_contact_with_no_customer_link_is_untouched(self):
		contact = frappe.get_doc({"doctype": "Contact", "first_name": "ZZ No Customer Link"}).insert(
			ignore_permissions=True
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Contact", contact.name, force=True, ignore_permissions=True)
		)
		self.assertEqual(len(contact.links), 0)


class TestGrantHelpdeskRole(IntegrationTestCase):
	def _website_user(self, email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ Portal",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", email, force=True, ignore_permissions=True))
		return user

	def test_grant_helpdesk_role_adds_role_to_website_user(self):
		email = "zz.sync.portal@example.com"
		self._website_user(email)
		cs.grant_helpdesk_role(email)
		self.assertIn(CUSTOMER_ROLE, frappe.get_roles(email))

	def test_grant_helpdesk_role_is_idempotent(self):
		email = "zz.sync.portal2@example.com"
		self._website_user(email)
		cs.grant_helpdesk_role(email)
		cs.grant_helpdesk_role(email)  # second call must not error or duplicate
		self.assertEqual(frappe.get_roles(email).count(CUSTOMER_ROLE), 1)

	def test_grant_helpdesk_role_skips_a_system_user(self):
		# Staff (System Users) get Helpdesk access through Agent, never through this portal role.
		# ERPNext only keeps user_type = 'System User' once a desk role is assigned (a bare insert
		# with no roles is coerced back to Website User by erpnext.portal.utils.set_default_role),
		# so give this one a desk role to make it a genuine staff account.
		email = "zz.sync.staff@example.com"
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ Staff",
				"send_welcome_email": 0,
				"roles": [{"role": "Sales User"}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", email, force=True, ignore_permissions=True))
		self.assertEqual(frappe.db.get_value("User", email, "user_type"), "System User")
		cs.grant_helpdesk_role(email)
		self.assertNotIn(CUSTOMER_ROLE, frappe.get_roles(email))


class TestSyncAllCustomers(IntegrationTestCase):
	def test_sync_all_customers_backfills_enabled_customers_only(self):
		# customer_after_insert already syncs every new Customer regardless of 'disabled', so to test
		# sync_all_customers() itself (the backfill job) in isolation, undo that first-sync here and
		# then check what the backfill does on its own. Unique names (hash suffix) avoid colliding
		# with a same-named Customer left over from an earlier run.
		tag = frappe.generate_hash(length=6)
		enabled = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"ZZ Backfill Enabled {tag}",
				"customer_type": "Company",
				"disabled": 0,
			}
		).insert(ignore_permissions=True)
		disabled = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"ZZ Backfill Disabled {tag}",
				"customer_type": "Company",
				"disabled": 1,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", enabled.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", disabled.name, force=True, ignore_permissions=True)
		)
		for c in (enabled, disabled):
			hd = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": c.name}, "name")
			if hd:
				frappe.delete_doc("HD Customer", hd, force=True, ignore_permissions=True)

		cs.sync_all_customers()

		enabled_hd = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": enabled.name}, "name")
		disabled_hd = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": disabled.name}, "name")
		self.assertTrue(enabled_hd)
		self.assertFalse(disabled_hd)
		if enabled_hd:
			frappe.delete_doc("HD Customer", enabled_hd, force=True, ignore_permissions=True)

	def test_new_disabled_customer_still_gets_synced_immediately_on_insert(self):
		# Documents the actual behaviour: customer_after_insert does not check 'disabled', so a
		# disabled Customer still gets an HD Customer the moment it is created. Only the backfill
		# (sync_all_customers) is selective. If this ever changes, it should change on purpose.
		disabled = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "ZZ Disabled On Insert",
				"customer_type": "Company",
				"disabled": 1,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", disabled.name, force=True, ignore_permissions=True)
		)
		hd = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": disabled.name}, "name")
		self.assertTrue(hd)
		if hd:
			frappe.delete_doc("HD Customer", hd, force=True, ignore_permissions=True)
