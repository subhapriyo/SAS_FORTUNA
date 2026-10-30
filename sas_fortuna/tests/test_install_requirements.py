# Copyright (c) 2026, SAS Infosystem Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import UnitTestCase


class TestInstallRequirements(UnitTestCase):
	def test_required_apps_include_doctype_dependencies(self):
		required_apps = set(frappe.get_hooks("required_apps", app_name="sas_fortuna"))

		self.assertTrue({"erpnext", "helpdesk"}.issubset(required_apps))
