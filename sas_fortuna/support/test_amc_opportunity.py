"""AMC enquiry Opportunities must not depend on how the Opportunity form is customised (opportunity.py).

On 27 Oct 2026 someone re-ticked "Mandatory" on fortuna_erp's CRM fields (Customize Form), and the
daily AMC job stopped creating Opportunities without anyone noticing. These tests set the fields
mandatory again and check the job still works, while sales Opportunities stay fully checked.

	env/bin/python apps/fortuna_erp/tools/quick_test.py sas_fortuna.support.test_amc_opportunity
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.tests import IntegrationTestCase

from sas_fortuna.support.opportunity import QUALIFICATION_FIELDS, make_amc_opportunity
from sas_fortuna.support.utils import find_sale_for_serial, get_settings


def make_crm_fields_always_mandatory():
	"""What the 27 Oct Customize Form save did."""
	meta = frappe.get_meta("Opportunity")
	for field in QUALIFICATION_FIELDS:
		if meta.has_field(field):
			make_property_setter(
				"Opportunity", field, "reqd", "1", "Check", validate_fields_for_doctype=False
			)
	frappe.clear_cache(doctype="Opportunity")


class TestAmcOpportunity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Meta is cached outside the database: drop it after the class rolls back.
		cls.addClassCleanup(frappe.clear_cache, doctype="Opportunity")
		cls.serial = cls.sold_serial()
		make_crm_fields_always_mandatory()

	@staticmethod
	def sold_serial():
		for s in frappe.get_all(
			"Serial No",
			filters={"custom_sold_to": ["is", "set"]},
			fields=["name", "item_code", "custom_sold_to", "custom_warranty_end"],
		):
			if find_sale_for_serial(s.name).customer == s.custom_sold_to:
				# No open enquiry yet for this unit (rolled back with the class).
				frappe.db.delete("Opportunity", {"custom_serial_no": s.name})
				return s
		raise AssertionError("No sold serial on this site to test with")

	def test_amc_enquiry_is_created_even_when_crm_fields_are_mandatory(self):
		# Savepoint: the other tests need this unit without an open enquiry.
		frappe.db.savepoint("amc_enquiry")
		try:
			opp = make_amc_opportunity(self.serial, get_settings())
			created = frappe.db.exists("Opportunity", opp.name)
		finally:
			frappe.db.rollback(save_point="amc_enquiry")
		self.assertTrue(created)

	def test_amc_enquiry_still_needs_the_other_required_fields(self):
		opp = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Customer",
				"party_name": self.serial.custom_sold_to,
				"custom_serial_no": self.serial.name,
				"company": get_settings().company,
				# custom_request_type (required, no default) left out
			}
		)
		with self.assertRaises(frappe.MandatoryError) as raised:
			opp.insert(ignore_permissions=True)
		self.assertIn("custom_request_type", str(raised.exception))
		self.assertNotIn("industry", str(raised.exception))  # the CRM fields are not asked for

	def test_sales_opportunity_still_needs_the_crm_fields(self):
		opp = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Customer",
				"party_name": self.serial.custom_sold_to,
				"company": get_settings().company,
			}
		)
		with self.assertRaises(frappe.MandatoryError) as raised:
			opp.insert(ignore_permissions=True)
		self.assertIn("industry", str(raised.exception).lower())
