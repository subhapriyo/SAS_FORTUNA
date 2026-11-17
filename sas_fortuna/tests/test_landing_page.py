"""Unit tests: the SAS Fortuna landing page (/desk/sas-fortuna) and its sidebar.

  Landing page ... setup/landing_page.py renders SECTIONS + support_desk.LANDING_SECTIONS
  Sidebar ........ sas_fortuna/sidebar/sas_fortuna/sas_fortuna.json, a standard Sidebar that
                   bench migrate imports (Frappe 16: an app ships a Sidebar; without one the
                   desk computes a list of the module's own DocTypes and reports)

Written test-first.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_landing_page
"""

import json
import os

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.setup import landing_page

SIDEBAR_FILE = ("sas_fortuna", "sidebar", "sas_fortuna", "sas_fortuna.json")


def _sidebar():
	with open(frappe.get_app_path("sas_fortuna", *SIDEBAR_FILE)) as f:
		return json.load(f)


def _links(sidebar):
	return {
		(i.get("link_type"), i.get("link_to") or i.get("url"))
		for i in sidebar["items"]
		if i["type"] == "Link"
	}


class TestLandingPage(IntegrationTestCase):
	def _all_links(self):
		return [
			link for s in landing_page.SECTIONS + landing_page._optional_sections() for link in s["links"]
		]

	def test_tickets_and_engineers_tiles(self):
		targets = {(kind, target) for _label, kind, target, _desc, _icon in self._all_links()}
		self.assertIn(("doctype", "HD Ticket"), targets)
		self.assertIn(("doctype", "HD Agent"), targets)

	def test_every_tile_has_a_known_icon(self):
		for label, _kind, _target, _desc, icon in self._all_links():
			self.assertIn(icon, landing_page.ICONS, label)

	def test_rendered_page_shows_the_new_tiles(self):
		page = landing_page._render(landing_page.SECTIONS + landing_page._optional_sections())
		self.assertIn("Support Engineers", page)
		self.assertIn('data-name="HD Ticket"', page)


class TestSidebar(IntegrationTestCase):
	def test_is_a_standard_sidebar_of_the_module(self):
		sb = _sidebar()
		self.assertEqual(
			(sb["doctype"], sb["name"], sb["title"], sb["module"], sb["app"], sb["standard"]),
			("Sidebar", "SAS Fortuna", "SAS Fortuna", "SAS Fortuna", "sas_fortuna", 1),
		)

	def test_home_opens_the_landing_page(self):
		first = _sidebar()["items"][0]
		self.assertEqual(
			(first["label"], first["link_type"], first["link_to"]), ("Home", "Workspace", "SAS Fortuna")
		)

	def test_new_support_links(self):
		links = _links(_sidebar())
		self.assertIn(("DocType", "HD Ticket"), links)
		self.assertIn(("DocType", "HD Agent"), links)
		self.assertIn(("DocType", "Job Location"), links)
		self.assertIn(("URL", "/helpdesk"), links)

	def test_keeps_every_doctype_and_report_of_the_module(self):
		# What the computed sidebar showed before must not disappear: every list DocType and
		# report of the module (child tables have no list of their own).
		links = _links(_sidebar())
		for name in frappe.get_all("DocType", filters={"module": "SAS Fortuna", "istable": 0}, pluck="name"):
			self.assertIn(("DocType", name), links, name)
		for name in frappe.get_all("Report", filters={"module": "SAS Fortuna"}, pluck="name"):
			self.assertIn(("Report", name), links, name)

	def test_links_under_a_section_are_its_children(self):
		in_section = False
		for item in _sidebar()["items"]:
			if item["type"] == "Section Break":
				in_section = True
				continue
			if in_section:
				self.assertEqual(item.get("child"), 1, item["label"])

	def test_every_link_target_exists(self):
		for item in _sidebar()["items"]:
			kind, target = item.get("link_type"), item.get("link_to")
			if item["type"] != "Link" or kind == "URL":
				continue
			self.assertTrue(frappe.db.exists(kind, target), f"{kind} {target}")

	def test_file_sits_where_migrate_imports_it(self):
		self.assertTrue(os.path.exists(frappe.get_app_path("sas_fortuna", *SIDEBAR_FILE)))
