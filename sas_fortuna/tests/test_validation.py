"""Shared format checks for the portal forms (api/validation.py).

GSTINs used here are real, publicly registered company GSTINs, so the check-digit tests do not
depend on our own algorithm being right: ZF India 27AAACZ3052C2ZM, Pravin Sales Division
27AABFP7386H1ZV.
"""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.api.validation import FORMATS, check_formats, check_phone, gstin_check_digit_ok

ZF_INDIA = "27AAACZ3052C2ZM"
PRAVIN = "27AABFP7386H1ZV"


def problems(data, fields=tuple(FORMATS)):
	found = {}
	check_formats(data, fields, lambda field, message: found.setdefault(field, message))
	return found


class TestGstin(IntegrationTestCase):
	def test_real_gstins_pass_the_check_digit(self):
		self.assertTrue(gstin_check_digit_ok(ZF_INDIA))
		self.assertTrue(gstin_check_digit_ok(PRAVIN))

	def test_one_wrong_character_fails_the_check_digit(self):
		self.assertFalse(gstin_check_digit_ok(ZF_INDIA[:-1] + "N"))
		self.assertFalse(gstin_check_digit_ok("27AAACZ3053C2ZM"))  # typo in the middle

	def test_valid_gstin_and_matching_pan_have_no_problems(self):
		self.assertEqual(problems({"gstin": ZF_INDIA, "pan": "AAACZ3052C"}), {})

	def test_gstin_is_upper_cased_and_spaces_removed(self):
		data = {"gstin": " 27aaacz3052c2zm ".replace("c2", "c 2")}
		self.assertEqual(problems(data), {})
		self.assertEqual(data["gstin"], ZF_INDIA)

	def test_short_gstin_is_refused(self):
		self.assertIn("gstin", problems({"gstin": "27AAACZ3052C2Z"}))

	def test_gstin_with_wrong_check_digit_is_refused(self):
		self.assertIn("last character", problems({"gstin": ZF_INDIA[:-1] + "N"})["gstin"])

	def test_pan_must_match_the_gstin(self):
		self.assertIn("pan", problems({"gstin": ZF_INDIA, "pan": "AABFP7386H"}))

	def test_pan_is_not_compared_with_a_malformed_gstin(self):
		self.assertNotIn("pan", problems({"gstin": "27AAACZ", "pan": "AABFP7386H"}))

	def test_other_formats(self):
		good = {
			"pan": "ABCDE1234F",
			"custom_tan_no": "KOLA12345B",
			"custom_aadhaar_number": "1234 5678 9012",
			"custom_udyam_registration_number": "udyam-wb-10-0012345",
			"custom_ifsc_code": "sbin0001234",
			"custom_account_no": "123456789",
		}
		self.assertEqual(problems(dict(good)), {})
		bad = {
			"pan": "ABCD1234F",
			"custom_tan_no": "KOL12345B",
			"custom_aadhaar_number": "12345678901",
			"custom_udyam_registration_number": "UDYAM-WB-10-001234",
			"custom_ifsc_code": "SBIN1001234",
			"custom_account_no": "12345678",
		}
		self.assertEqual(set(problems(dict(bad))), set(bad))

	def test_only_the_named_fields_are_checked(self):
		self.assertEqual(problems({"pan": "bad"}, fields=("gstin",)), {})


class TestPhone(IntegrationTestCase):
	"""Numbers are stored as Frappe's Phone fields want them: +<country>-<number>."""

	def test_indian_mobile_from_the_phone_control(self):
		self.assertEqual(check_phone("+91-98300 12345", mobile_only=True), ("+91-9830012345", None))

	def test_number_typed_without_country_gets_india(self):
		self.assertEqual(check_phone("09830012345")[0], "+91-9830012345")

	def test_landline_is_fine_as_phone(self):
		number, problem = check_phone("+91-033 2441 1234")
		self.assertEqual((number, problem), ("+91-3324411234", None))

	def test_landline_is_refused_as_mobile(self):
		self.assertIn("landline", check_phone("+91-033 2441 1234", mobile_only=True)[1])

	def test_foreign_mobile(self):
		self.assertEqual(check_phone("+44-7911 123456", mobile_only=True), ("+44-7911123456", None))

	def test_too_short(self):
		self.assertIn("too short", check_phone("+91-12345")[1])

	def test_unknown_country_code(self):
		self.assertIn("country code", check_phone("+999-12345678")[1])

	def test_not_a_number(self):
		self.assertIn("not a phone number", check_phone("abc")[1])

	def test_refused_number_is_returned_unchanged(self):
		self.assertEqual(check_phone("+91-12345")[0], "+91-12345")
