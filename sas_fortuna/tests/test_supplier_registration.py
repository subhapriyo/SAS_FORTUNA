"""Public Supplier Registration checks (api/supplier_registration.py)."""

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.api.supplier_registration import before_insert, check_registration, validate_registration

ZF_INDIA = "27AAACZ3052C2ZM"  # real GSTIN, registered in Maharashtra (state code 27)
NAME = "Registration Test Traders"
MOBILE = "+91-99030 00017"  # setUpClass checks that the site has none of these yet


def application(**changes):
	data = {
		"supplier_name": NAME,
		"gstin": ZF_INDIA,
		"state": "Maharashtra",
		"pincode": "411001",
		"country": "India",
		"first_name": "Ravi",
		"last_name": "Kumar",
		"email": "ravi@registration-test.example",
		"mobile": MOBILE,
	}
	data.update(changes)
	return data


def problem_fields(data):
	return {e["field"] for e in validate_registration(data)}


class TestSupplierRegistration(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# The duplicate check reads real data: the sample application must be new to this site.
		clash = validate_registration(application())
		if clash:
			raise AssertionError(f"Sample application already registered on this site, change it: {clash}")

	def test_complete_application_has_no_problems(self):
		self.assertEqual(validate_registration(application()), [])

	def test_required_fields(self):
		data = application(supplier_name="", gstin="", first_name="", last_name="", email="")
		self.assertEqual(problem_fields(data), {"supplier_name", "gstin", "first_name", "last_name", "email"})

	def test_placeholder_name_is_refused(self):
		self.assertEqual(problem_fields(application(supplier_name="supplier")), {"supplier_name"})

	def test_pan_is_filled_in_from_the_gstin(self):
		data = application(pan="")
		validate_registration(data)
		self.assertEqual(data["pan"], "AAACZ3052C")

	def test_email_is_stored_lower_case(self):
		data = application(email="Ravi@Registration-Test.Example")
		validate_registration(data)
		self.assertEqual(data["email"], "ravi@registration-test.example")

	def test_gstin_must_belong_to_the_chosen_state(self):
		errors = validate_registration(application(state="West Bengal", pincode="700016"))
		self.assertEqual([e["field"] for e in errors], ["state"])
		self.assertIn("Maharashtra", errors[0]["message"])

	def test_pin_code_must_be_in_the_chosen_state(self):
		self.assertEqual(problem_fields(application(pincode="700016")), {"pincode"})

	def test_pin_code_must_have_six_digits(self):
		self.assertEqual(problem_fields(application(pincode="41100")), {"pincode"})

	def test_mobile_must_be_a_mobile(self):
		self.assertEqual(problem_fields(application(mobile="+91-020 2612 3456")), {"mobile"})

	def test_foreign_supplier_skips_indian_tax_checks(self):
		data = application(country="United Kingdom", gstin="GB123456789", state="", pincode="SW1A 1AA")
		self.assertEqual(validate_registration(data), [])

	def test_already_registered_supplier_name_is_refused(self):
		# Rolled back to the savepoint, so the other tests never see this Supplier.
		frappe.db.savepoint("registered_supplier")
		try:
			frappe.get_doc({"doctype": "Supplier", "supplier_name": NAME}).insert(
				ignore_permissions=True, ignore_mandatory=True
			)
			errors = validate_registration(application())
		finally:
			frappe.db.rollback(save_point="registered_supplier")
		self.assertEqual([e["field"] for e in errors], ["supplier_name"])
		self.assertIn("contact Fortuna", errors[0]["message"])

	def registered_with_mobile(self, stored_as):
		"""Problem fields when an existing Supplier has this mobile, typed the way staff typed it."""
		frappe.db.savepoint("registered_mobile")
		try:
			supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": "Other Co"})
			supplier.insert(ignore_permissions=True, ignore_mandatory=True)
			frappe.db.set_value("Supplier", supplier.name, "mobile_no", stored_as)
			return [e["field"] for e in validate_registration(application())]
		finally:
			frappe.db.rollback(save_point="registered_mobile")

	def test_already_registered_mobile_is_refused(self):
		self.assertEqual(self.registered_with_mobile("+91-9903000017"), ["mobile"])

	def test_registered_mobile_is_found_however_it_was_typed(self):
		for stored_as in ("9903000017", "99030 00017", "+919903000017", "09903000017"):
			self.assertEqual(self.registered_with_mobile(stored_as), ["mobile"], stored_as)

	def test_page_check_returns_the_same_problems(self):
		frappe.set_user("Guest")
		try:
			result = check_registration(frappe.as_json(application(pincode="700016")))
		finally:
			frappe.set_user("Administrator")
		self.assertEqual([e["field"] for e in result], ["pincode"])

	def test_saving_a_bad_application_is_refused(self):
		doc = frappe.get_doc({"doctype": "Supplier Onboarding", **application(pincode="12")})
		with self.assertRaisesRegex(frappe.ValidationError, "6-digit PIN code"):
			before_insert(doc)

	def test_saving_a_good_application_stores_tidied_values(self):
		doc = frappe.get_doc(
			{"doctype": "Supplier Onboarding", **application(gstin=ZF_INDIA.lower(), pan="")}
		)
		before_insert(doc)
		self.assertEqual((doc.gstin, doc.pan, doc.mobile), (ZF_INDIA, "AAACZ3052C", "+91-9903000017"))
