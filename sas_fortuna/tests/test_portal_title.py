"""No "Fortuna - " in portal and Web Form headings (portal/sidebar.py: drop_title_prefix)."""

import frappe
from frappe.tests import UnitTestCase

from sas_fortuna.portal.sidebar import drop_title_prefix


def context(title="Fortuna - Repairs", **extra):
	return frappe._dict(title_prefix="Fortuna", title=title, **extra)


class TestPortalTitle(UnitTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user):
		frappe.set_user(user)

	def test_logged_in_portal_page_loses_the_prefix(self):
		self.as_user("Administrator")
		self.assertEqual(drop_title_prefix(context(show_sidebar=True)), {"title": "Repairs"})

	def test_public_web_form_loses_the_prefix(self):
		self.as_user("Guest")
		result = drop_title_prefix(context("Fortuna - Supplier Registration", web_form_doc={"name": "x"}))
		self.assertEqual(result, {"title": "Supplier Registration"})

	def test_other_public_pages_keep_it(self):
		self.as_user("Guest")
		self.assertIsNone(drop_title_prefix(context("Fortuna - Login", show_sidebar=True)))

	def test_page_without_sidebar_keeps_it(self):
		self.as_user("Administrator")
		self.assertIsNone(drop_title_prefix(context()))

	def test_title_without_the_prefix_is_left_alone(self):
		self.as_user("Administrator")
		self.assertIsNone(drop_title_prefix(context("Repairs", show_sidebar=True)))
