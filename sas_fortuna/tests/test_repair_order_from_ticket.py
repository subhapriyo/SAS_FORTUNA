"""Agents making a Repair Order from a Helpdesk ticket (Helpdesk "Create Repair Order").

Written test-first (TDD):
  * Lookups ...... an Agent or Service Engineer (Fortuna's SW/HW staff have no ERPNext role
                   besides these) can read the Serial No, Item and Customer a Repair Order links
                   to, or the form stops with "Insufficient Permission for Serial No".
  * Complaint .... the ticket's description is HTML (Helpdesk editor); the Repair Order's
                   Complaint is plain text, so it is copied without the tags.
  * Form ......... the form fills itself from ticket_details(), the same code the server runs
                   on save, so both copy the same values (one place to change).

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_repair_order_from_ticket
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.sas_fortuna.doctype.repair_order import repair_order as ro_module
from sas_fortuna.setup import support_desk as sd

LOOKUPS = ("Serial No", "Item", "Customer")
REPAIR_ROLES = ("Agent", "Service Engineer")
ZZ_USER = "zz.ro.agent@fortuna.test"


class TestRepairLookupsForAgents(IntegrationTestCase):
	def test_agents_and_engineers_can_read_what_a_repair_order_links_to(self):
		for doctype in LOOKUPS:
			for role in REPAIR_ROLES:
				self.assertIn("read", sd.PERMISSIONS.get(doctype, {}).get(role, []), f"{doctype} / {role}")

	def test_lookups_stay_read_only(self):
		for doctype in LOOKUPS:
			for role in REPAIR_ROLES:
				extra = set(sd.PERMISSIONS[doctype][role]) - {"read", "select", "report", "print"}
				self.assertFalse(extra, f"{doctype} / {role}: {extra}")

	def test_an_agent_with_no_other_role_can_read_a_serial_no(self):
		sd._add_permissions()
		if not frappe.db.exists("User", ZZ_USER):
			frappe.get_doc(
				{"doctype": "User", "email": ZZ_USER, "first_name": "ZZ RO Agent", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", ZZ_USER)
		user.remove_roles(*[r.role for r in user.roles])
		user.add_roles("Agent")
		frappe.clear_cache(user=ZZ_USER)
		for doctype in LOOKUPS:
			self.assertTrue(frappe.has_permission(doctype, "read", user=ZZ_USER), doctype)
		self.assertFalse(frappe.has_permission("Serial No", "write", user=ZZ_USER))


class TestComplaintFromTicket(IntegrationTestCase):
	def _pull(self, description, complaint=None):
		ticket = frappe._dict(
			customer=None,
			custom_erpnext_customer="ZZ Customer",
			custom_product_model=None,
			custom_serial_no=None,
			description=description,
		)
		doc = frappe.new_doc("Repair Order")
		doc.helpdesk_ticket = "ZZ-TICKET"
		doc.complaint = complaint
		with patch.object(ro_module.frappe.db, "get_value", return_value=ticket):
			doc.pull_from_ticket()
		return doc.complaint

	def test_html_tags_are_dropped(self):
		self.assertEqual(self._pull("<p>asfsafssvsavsavv</p>"), "asfsafssvsavsavv")

	def test_paragraphs_and_breaks_become_lines(self):
		self.assertEqual(
			self._pull("<p>No display</p><p>Since Monday<br>Kolkata office &amp; branch</p>"),
			"No display\nSince Monday\nKolkata office & branch",
		)

	def test_plain_text_is_kept(self):
		self.assertEqual(self._pull("Device not reading thumbs"), "Device not reading thumbs")

	def test_a_complaint_typed_by_the_agent_is_kept(self):
		self.assertEqual(self._pull("<p>from ticket</p>", complaint="typed"), "typed")

	def test_empty_description_stays_empty(self):
		self.assertFalse(self._pull(None))
		self.assertFalse(self._pull("<p></p>"))


class TestTicketDetailsForTheForm(IntegrationTestCase):
	TICKET = frappe._dict(
		customer="ZZ HD Customer",
		custom_erpnext_customer=None,
		custom_product_model="ZZ-MODEL",
		custom_serial_no="ZZ-SN-1",
		description="<p>No display</p>",
	)

	def _details(self, allowed=True):
		# Fake only the ticket read; Frappe's own lookups (DocType meta) go to the database.
		real_get_value = frappe.db.get_value

		def get_value(doctype, *args, **kwargs):
			return self.TICKET if doctype == "HD Ticket" else real_get_value(doctype, *args, **kwargs)

		with (
			patch.object(ro_module.frappe.db, "get_value", side_effect=get_value),
			patch.object(ro_module, "get_erpnext_customer", return_value="ZZ ERP Customer"),
			patch.object(ro_module.frappe, "has_permission", return_value=allowed) as perm,
		):
			return ro_module.ticket_details("ZZ-TICKET"), perm

	def test_same_values_the_server_copies_on_save(self):
		details, _perm = self._details()
		self.assertEqual(
			details,
			{
				"customer": "ZZ ERP Customer",  # from the Helpdesk customer when the link is blank
				"product_model": "ZZ-MODEL",
				"serial_no": "ZZ-SN-1",
				"complaint": "No display",
			},
		)

	def test_checks_the_user_may_read_the_ticket(self):
		_details, perm = self._details()
		perm.assert_called_once_with("HD Ticket", "read", "ZZ-TICKET", throw=True)

	def test_no_ticket_no_details(self):
		self.assertEqual(ro_module.ticket_details(""), {})
