"""Format checks shared by the portal forms: Customer / Supplier KYC (party_kyc.py) and the public
Supplier Registration (supplier_registration.py). Browser twin: public/js/sf_validation.js.

Messages are written for the person filling in the form: what is wrong and what to type instead.
"""

import re

import frappe
from frappe import _

# Field -> (format, message). Values are checked after upper-casing and removing spaces.
FORMATS = {
	"gstin": (
		r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]",
		"Enter the 15-character GSTIN, for example 19AABCF1234A1ZB.",
	),
	"pan": (r"[A-Z]{5}[0-9]{4}[A-Z]", "Enter the 10-character PAN, for example ABCDE1234F."),
	"custom_tan_no": (r"[A-Z]{4}[0-9]{5}[A-Z]", "Enter the 10-character TAN, for example KOLA12345B."),
	"custom_aadhaar_number": (r"[0-9]{12}", "Enter the 12-digit Aadhaar number."),
	"custom_udyam_registration_number": (
		r"UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}",
		"Enter the Udyam number as printed on the certificate, for example UDYAM-WB-10-0012345.",
	),
	"custom_ifsc_code": (r"[A-Z]{4}0[A-Z0-9]{6}", "Enter the 11-character IFSC, for example SBIN0001234."),
	"custom_account_no": (r"[0-9]{9,18}", "Enter the account number (9 to 18 digits)."),
}
PINCODE = r"[1-9][0-9]{5}"


def check_formats(data, fields, problem):
	"""Tidy and check `fields` of `data` (a dict) against FORMATS; calls problem(field, message)."""
	for field in fields:
		if data.get(field):
			data[field] = data[field].upper().replace(" ", "")
			pattern, message = FORMATS[field]
			if not re.fullmatch(pattern, data[field]):
				problem(field, message)
	gstin, pan = data.get("gstin"), data.get("pan")
	gstin_ok = gstin and re.fullmatch(FORMATS["gstin"][0], gstin)
	if gstin_ok and not gstin_check_digit_ok(gstin):
		problem("gstin", "This GSTIN is not valid: its last character does not match. Please check it.")
	if gstin_ok and pan and gstin[2:12] != pan:
		problem("pan", "This PAN does not match the GSTIN (characters 3 to 12 of a GSTIN are the PAN).")


def gstin_check_digit_ok(gstin):
	"""GSTIN's last character is a mod-36 checksum of the first 14."""
	chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	total = 0
	for i, char in enumerate(gstin[:14]):
		value = chars.index(char) * (2 if i % 2 else 1)
		total += value // 36 + value % 36
	return gstin[14] == chars[(36 - total % 36) % 36]


def check_phone(number, mobile_only=False):
	"""(number as Frappe's Phone fields store it, e.g. "+91-9830012345", problem or None).

	Forms send what Frappe's Phone control shows, "+91-98300 12345"; older callers may send just
	"09830012345", which gets the site's country (System Settings > Country; India if not set).
	Checked with Google's phone-number rules (the `phonenumbers` package Frappe already uses): the
	number must exist in that country, and a Mobile must be a mobile number.
	"""
	import phonenumbers
	from phonenumbers import NumberParseException, PhoneNumberType, ValidationResult

	try:
		parsed = phonenumbers.parse(number, _default_phone_region())
	except NumberParseException as e:
		if e.error_type == NumberParseException.INVALID_COUNTRY_CODE:
			return number, _("This country code is not valid.")
		return number, _("This is not a phone number. Use digits only.")

	if not phonenumbers.is_valid_number(parsed):
		reason = phonenumbers.is_possible_number_with_reason(parsed)
		if reason == ValidationResult.TOO_SHORT:
			return number, _("This number is too short for the chosen country.")
		if reason == ValidationResult.TOO_LONG:
			return number, _("This number is too long for the chosen country.")
		return number, _(
			"This number does not exist in the chosen country. Check the country and the digits."
		)
	if mobile_only and phonenumbers.number_type(parsed) not in (
		PhoneNumberType.MOBILE,
		PhoneNumberType.FIXED_LINE_OR_MOBILE,
	):
		return number, _("This looks like a landline number. Please enter a mobile number.")
	return f"+{parsed.country_code}-{parsed.national_number}", None


def _default_phone_region():
	"""Two-letter country code used for numbers typed without one ("IN" for India)."""
	country = frappe.db.get_single_value("System Settings", "country")
	code = country and frappe.db.get_value("Country", country, "code")
	return (code or "in").upper()
