"""Unit tests for support/print_formats.py: what every Fortuna print shows at the top, and the
payment line on the repair quotation.

Written test-first (TDD) after the demo prints of 14 Nov 2026 showed no letter head and a
payment line that contradicted Fortuna's rule (payment in full before dispatch).

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_print_formats
"""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.support import print_formats as pf

SETTINGS = "Fortuna Support Settings"


def _render(template, **context):
	context.setdefault("doc", frappe._dict(company=frappe.db.get_value("Company", {}), name="ZZ-0001"))
	return frappe.render_template(template, {"_": frappe._, **context})


class TestHeader(IntegrationTestCase):
	def test_selected_letter_head_is_printed(self):
		# Custom HTML formats must print the letter head themselves: Frappe does not add it.
		html = _render(pf._page("ZZ Title", ""), letter_head="<div>ZZ-LETTER-HEAD</div>")
		self.assertIn("ZZ-LETTER-HEAD", html)
		self.assertIn("ZZ Title", html)

	def test_without_letter_head_the_company_is_named(self):
		company = frappe.db.get_value("Company", {})
		html = _render(pf._page("ZZ Title", ""), letter_head="")
		self.assertIn(company, html)


class TestRepairPaymentNote(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for field in ("payment_due_before", "advance_percent"):
			old = frappe.db.get_single_value(SETTINGS, field)
			self.addCleanup(frappe.db.set_single_value, SETTINGS, field, old)

	def _note(self, due, advance=100):
		frappe.db.set_single_value(SETTINGS, {"payment_due_before": due, "advance_percent": advance})
		return _render(pf.REPAIR_PAYMENT_NOTE)

	def test_payment_before_dispatch(self):
		note = self._note("Dispatch")
		self.assertIn("before the repaired unit is dispatched", note)
		self.assertNotIn("accepted and paid in full", note)

	def test_blank_setting_means_dispatch(self):
		self.assertIn("before the repaired unit is dispatched", self._note(""))

	def test_advance_before_repair_start(self):
		self.assertIn("advance of 50%", self._note("Repair Start", 50))
		self.assertIn("accepted and paid in full", self._note("Repair Start", 100))

	def test_repair_quotation_uses_the_note(self):
		self.assertIn(pf.REPAIR_PAYMENT_NOTE, pf.REPAIR_QUOTATION)


class TestRefreshPatch(IntegrationTestCase):
	def test_existing_formats_get_the_fixed_html(self):
		from sas_fortuna.patches.v16_0 import refresh_fortuna_print_formats as patch

		pf.create_print_formats(commit=False)
		frappe.db.set_value("Print Format", "Fortuna Repair Quotation", "html", "<p>old</p>")
		patch.execute()
		self.assertEqual(
			frappe.db.get_value("Print Format", "Fortuna Repair Quotation", "html"), pf.REPAIR_QUOTATION
		)
