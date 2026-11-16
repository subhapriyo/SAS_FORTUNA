"""Unit tests for the "we've received your ticket" e-mail.

Helpdesk keeps the template (Helpdesk > Settings > Email Notifications > Acknowledgement, i.e.
HD Settings.acknowledgement_email_content) but only sends it for tickets that came in by e-mail.
sas_fortuna sends the same template for customer-portal tickets too (support/hd_ticket.py), and
the Fortuna setup fills in Fortuna's wording once (setup/fortuna_impex.py).

Written test-first.  bash apps/sas_fortuna/tools/run_unit_tests.sh test_ticket_acknowledgement
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from sas_fortuna.setup import fortuna_impex as fi
from sas_fortuna.support import hd_ticket

HD = "HD Settings"


def _ticket(**values):
	doc = MagicMock()
	doc.get.side_effect = lambda key, default=None: values.get(key, default)
	doc.via_customer_portal = values.get("via_customer_portal", 0)
	doc.name = values.get("name", "ZZ-1")
	return doc


class TestFortunaTemplate(IntegrationTestCase):
	def _render(self, **doc):
		base = {
			"name": "0042",
			"subject": "Fingerprint or face not reading",
			"ticket_type": "Hardware",
			"creation": now_datetime(),
			"agent_group": "Hardware Support",
		}
		return frappe.render_template(fi.acknowledgement_template(), {"doc": frappe._dict(base, **doc)})

	def test_it_renders_the_ticket_details(self):
		html = self._render(custom_serial_no="DEMO-0002", response_by=now_datetime(), via_customer_portal=1)
		for text in ("#0042", "Fingerprint or face not reading", "Hardware", "DEMO-0002"):
			self.assertIn(text, html)
		self.assertNotIn("First response by", html)  # Fortuna: no response time in the mail
		self.assertIn("/helpdesk/my-tickets/0042", html)  # portal tickets get a link

	def test_company_details_come_from_the_company_record(self):
		template = fi.acknowledgement_template()
		for typed in ("Fortuna Impex", "fortunaindia.com"):
			self.assertNotIn(typed, template)  # nothing typed in; all from the Company
		company = frappe.db.get_single_value(
			"Fortuna Support Settings", "company"
		) or frappe.db.get_single_value("Global Defaults", "default_company")
		if not company:
			self.skipTest("no company on this site")
		co = frappe.get_doc("Company", company)
		html = self._render()
		self.assertIn(f"contacting {co.company_name} support", html)
		self.assertIn(f"Support Team, {co.company_name}", html)
		if co.email:
			self.assertIn(co.email, html)

	def test_optional_lines_are_left_out(self):
		html = self._render()
		self.assertNotIn("Serial No", html)
		self.assertNotIn("/helpdesk/my-tickets/", html)  # e-mail tickets: reply to the mail
		self.assertIn("reply to this e-mail", html)

	def test_setup_fills_the_wording_only_when_blank_and_switches_it_on_once(self):
		frappe.db.set_single_value(HD, {"acknowledgement_email_content": "", "send_acknowledgement_email": 0})
		frappe.db.set_default(fi.ACK_FLAG, "")
		self.assertTrue(fi.ensure_acknowledgement_email())
		self.assertEqual(
			frappe.db.get_single_value(HD, "acknowledgement_email_content"), fi.acknowledgement_template()
		)
		self.assertEqual(frappe.db.get_single_value(HD, "send_acknowledgement_email"), 1)

		# Edited and switched off in Helpdesk later: both stay as the admin left them.
		frappe.db.set_single_value(
			HD, {"acknowledgement_email_content": "<p>ours</p>", "send_acknowledgement_email": 0}
		)
		self.assertEqual(fi.ensure_acknowledgement_email(), [])
		self.assertEqual(frappe.db.get_single_value(HD, "acknowledgement_email_content"), "<p>ours</p>")
		self.assertEqual(frappe.db.get_single_value(HD, "send_acknowledgement_email"), 0)

	def test_runs_on_migrate(self):
		self.assertIn(fi.ensure_acknowledgement_email, fi.STEPS)


class TestPortalTicketsGetIt(IntegrationTestCase):
	def _send(self, doc, enabled=1):
		with patch.object(frappe.db, "get_single_value", return_value=enabled):
			hd_ticket.send_portal_acknowledgement(doc)

	def test_a_portal_ticket_is_acknowledged(self):
		doc = _ticket(via_customer_portal=1, raised_by="zz.customer@example.com")
		self._send(doc)
		doc.send_acknowledgement_email.assert_called_once()

	def test_e_mail_tickets_are_left_to_helpdesk(self):
		doc = _ticket(via_customer_portal=0, raised_by="zz.customer@example.com")
		self._send(doc)
		doc.send_acknowledgement_email.assert_not_called()

	def test_nothing_is_sent_when_switched_off(self):
		doc = _ticket(via_customer_portal=1, raised_by="zz.customer@example.com")
		self._send(doc, enabled=0)
		doc.send_acknowledgement_email.assert_not_called()

	def test_a_mail_problem_never_stops_the_ticket(self):
		doc = _ticket(via_customer_portal=1, raised_by="zz.customer@example.com")
		doc.send_acknowledgement_email.side_effect = frappe.ValidationError("SMTP down")
		self._send(doc)  # no error raised
		self.assertTrue(frappe.db.exists("Error Log", {"method": ["like", "%acknowledgement%"]}))

	def test_wired_after_insert(self):
		from sas_fortuna.support.wiring import doc_events

		self.assertIn(
			"sas_fortuna.support.hd_ticket.after_insert", str(doc_events["HD Ticket"].get("after_insert"))
		)
