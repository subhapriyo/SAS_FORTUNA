"""Customer / Supplier KYC form checks (api/party_kyc.py: validate_kyc).

Every problem names its field (and row, for address / contact rows), so the page can highlight it.
"""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.api.party_kyc import validate_kyc

ZF_INDIA = "27AAACZ3052C2ZM"  # a real, publicly registered GSTIN


def form(**changes):
	data = {
		"gst_category": "Registered Regular",
		"gstin": ZF_INDIA,
		"pan": "AAACZ3052C",
		"addresses": [
			{
				"address_line1": "12 Park Street",
				"city": "Kolkata",
				"state": "West Bengal",
				"pincode": "700016",
			}
		],
		"contacts": [{"first_name": "Ravi", "email": "ravi@example.com", "mobile": "+91-98300 12345"}],
	}
	data.update(changes)
	return data


def fields(errors):
	return {(e["field"], e["row_type"], e["row"]) for e in errors}


class TestKycValidation(IntegrationTestCase):
	def test_complete_form_has_no_problems(self):
		self.assertEqual(validate_kyc(form()), [])

	def test_values_are_tidied_for_saving(self):
		data = form(gstin=" 27aaacz3052c2zm ", pan="aaacz3052c ")
		validate_kyc(data)
		self.assertEqual(
			(data["gstin"], data["pan"], data["contacts"][0]["mobile"]),
			(ZF_INDIA, "AAACZ3052C", "+91-9830012345"),
		)

	def test_gst_category_is_required(self):
		self.assertIn(("gst_category", None, None), fields(validate_kyc(form(gst_category=""))))

	def test_registered_category_needs_a_gstin(self):
		self.assertIn(("gstin", None, None), fields(validate_kyc(form(gstin="", pan=""))))

	def test_unregistered_and_overseas_need_no_gstin(self):
		for category in ("Unregistered", "Overseas"):
			self.assertEqual(validate_kyc(form(gst_category=category, gstin="", pan="")), [], category)

	def test_tds_yes_needs_a_withholding_category(self):
		errors = validate_kyc(form(custom_tds_applicable="Yes"))
		self.assertIn(("tax_withholding_category", None, None), fields(errors))

	def test_msme_yes_needs_the_udyam_number(self):
		errors = validate_kyc(form(custom_msme="Yes"))
		self.assertIn(("custom_udyam_registration_number", None, None), fields(errors))

	def test_bank_details_are_all_or_nothing(self):
		errors = validate_kyc(form(custom_bank_name="State Bank of India"))
		self.assertEqual(
			fields(errors), {("custom_account_no", None, None), ("custom_ifsc_code", None, None)}
		)

	def test_started_address_needs_city_state_and_pin(self):
		errors = validate_kyc(form(addresses=[{"address_line1": "12 Park Street"}]))
		self.assertEqual(
			fields(errors),
			{("city", "address", 1), ("state", "address", 1), ("pincode", "address", 1)},
		)

	def test_empty_address_row_is_skipped(self):
		self.assertEqual(validate_kyc(form(addresses=[{"address_line1": " ", "city": ""}])), [])

	def test_problem_in_the_second_row_names_row_two(self):
		addresses = form()["addresses"] + [
			{"address_line1": "5 Camac Street", "city": "Kolkata", "state": "West Bengal", "pincode": "70017"}
		]
		self.assertEqual(fields(validate_kyc(form(addresses=addresses))), {("pincode", "address", 2)})

	def test_contact_email_and_mobile_are_checked(self):
		contacts = [{"first_name": "Ravi", "email": "ravi@", "mobile": "+91-033 2441 1234"}]
		self.assertEqual(
			fields(validate_kyc(form(contacts=contacts))), {("email", "contact", 1), ("mobile", "contact", 1)}
		)
