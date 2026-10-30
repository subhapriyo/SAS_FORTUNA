"""Checks behind the public Supplier Registration form (/supplier-registration).

The form is the Web Form "supplier-registration" on the Supplier Onboarding DocType, filled in by
guests. On Submit its browser script (public/js/supplier_registration.js) checks formats, then
calls check_registration(), which runs validate_registration(): the same checks plus the
ones that need the database (duplicates). before_insert() below (a doc event in hooks.py) runs it
once more on save, so nothing invalid gets in even if the page is bypassed.

Each problem is {"field": <fieldname>, "message": ...}, so the page can highlight the exact field.
"""

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from sas_fortuna.api.validation import PINCODE, check_formats, check_phone

try:  # GST state codes and PIN code ranges per state, from India Compliance
	from india_compliance.gst_india.constants import STATE_NUMBERS, STATE_PINCODE_MAPPING
except ImportError:
	STATE_NUMBERS, STATE_PINCODE_MAPPING = {}, {}

REQUIRED = {
	"supplier_name": "Enter your company's name.",
	"gstin": "Enter your company's GSTIN.",
	"first_name": "Enter the contact person's first name.",
	"last_name": "Enter the contact person's last name.",
	"email": "Enter the contact person's e-mail address.",
}

# Duplicates: a value already on a Supplier, or on an APPROVED Supplier Onboarding (pending or
# rejected applications do not block applying again). Field -> Supplier fieldname, message.
DUPLICATE_CHECKS = {
	"supplier_name": ("supplier_name", "A supplier with this name is already registered with us."),
	"gstin": ("gstin", "This GSTIN is already registered with us."),
	"pan": ("pan", "This PAN is already registered with us."),
	"email": ("email_id", "This e-mail address is already registered with us."),
	"mobile": ("mobile_no", "This mobile number is already registered with us."),
}
ALREADY_REGISTERED_HINT = " If this is your company, please contact Fortuna instead of registering again."

# Supplier Onboarding approval: workflow state field and the exact state name in the
# "Supplier Onboarding Workflow". Update here if the state is renamed.
APPROVAL_FIELDNAME = "workflow_state"
APPROVED_VALUE = "Approved"


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60)
def check_registration(data):
	"""Problems with the registration form, for the page (empty list: ready to submit).

	Guest-accessible because the form is public, so it also tells anyone whether a GSTIN / PAN /
	e-mail / mobile / name is already registered: hence the rate limit per IP.
	"""
	data = frappe.parse_json(data)
	return validate_registration({k: v for k, v in data.items() if isinstance(v, str)})


def before_insert(doc, method=None):
	"""Supplier Onboarding before_insert (hooks.py): a new application gets the form's checks.

	The page already shows these problems field by field; this is the safety net if it is
	bypassed. Later Desk edits by Fortuna staff are not re-checked.
	"""
	data = doc.as_dict()
	errors = validate_registration(data)
	doc.update({field: data[field] for field in ("supplier_name", "gstin", "pan", "email", "mobile")})
	if errors:
		items = "".join(f"<li>{_(doc.meta.get_label(e['field']))}: {e['message']}</li>" for e in errors)
		frappe.throw(f"<ul>{items}</ul>", title=_("Please check your application"))


def validate_registration(data):
	"""Check a new application's `data` (a dict, tidied in place); returns the problems found."""
	errors = []

	def problem(field, message):
		if not any(e["field"] == field for e in errors):  # one message per field
			errors.append({"field": field, "message": _(message)})

	for key, value in data.items():
		if isinstance(value, str):
			data[key] = value.strip()
	if data.get("email"):
		data["email"] = data["email"].lower()

	for field, message in REQUIRED.items():
		if not data.get(field):
			problem(field, message)
	if (data.get("supplier_name") or "").lower() == "supplier":
		problem("supplier_name", "Enter your company's actual name.")

	# Indian tax details and address (the default when no country is chosen)
	if data.get("country") in (None, "", "India"):
		check_formats(data, ("gstin", "pan"), problem)
		gstin, state, pincode = data.get("gstin"), data.get("state"), data.get("pincode")
		if gstin and not data.get("pan") and not _has_error(errors, "gstin"):
			data["pan"] = gstin[2:12]  # the PAN is part of the GSTIN
		if (
			gstin
			and state
			and not _has_error(errors, "gstin")
			and STATE_NUMBERS.get(state) not in (None, gstin[:2])
		):
			gstin_state = next((s for s, code in STATE_NUMBERS.items() if code == gstin[:2]), "another state")
			problem(
				"state",
				f"This GSTIN is registered in {gstin_state}, not {state}. Check the state or the GSTIN.",
			)
		if pincode and not re.fullmatch(PINCODE, pincode):
			problem("pincode", "Enter the 6-digit PIN code.")
		elif pincode and state and not _pincode_in_state(pincode, state):
			problem("pincode", f"PIN code {pincode} is not in {state}. Check the PIN code or the state.")

	if data.get("email") and not validate_email_address(data["email"]):
		problem("email", "Enter a valid e-mail address, for example name@company.com.")
	if data.get("mobile"):
		data["mobile"], message = check_phone(data["mobile"], mobile_only=True)
		if message:
			problem("mobile", message)

	for field, (supplier_field, message) in DUPLICATE_CHECKS.items():
		value = data.get(field)
		if value and not _has_error(errors, field) and _is_registered(field, supplier_field, value):
			problem(field, message + ALREADY_REGISTERED_HINT)
	return errors


def _has_error(errors, field):
	return any(e["field"] == field for e in errors)


def _pincode_in_state(pincode, state):
	"""Does the PIN code's 3-digit prefix fall in the state's range? (unknown state: assume yes)"""
	ranges = STATE_PINCODE_MAPPING.get(state)
	if not ranges:
		return True
	if not isinstance(ranges[0], tuple):
		ranges = (ranges,)
	prefix = int(pincode[:3])
	return any(low <= prefix <= high for low, high in ranges)


def _is_registered(field, supplier_field, value):
	if field == "mobile":
		return _mobile_registered(value, supplier_field)
	if frappe.db.exists("Supplier", {supplier_field: value}):
		return True
	return bool(frappe.db.exists("Supplier Onboarding", {field: value, APPROVAL_FIELDNAME: APPROVED_VALUE}))


def _mobile_registered(number, supplier_field):
	"""Stored mobiles were typed every which way ("9830012345", "+91 98300 12345", "098300-12345"),
	so compare the last 10 digits, not the text."""
	digits = re.sub(r"\D", "", number)[-10:]

	def last_ten(column):
		return f"RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE({column}, '+', ''), '-', ''), ' ', ''), '(', ''), ')', ''), 10)"

	if frappe.db.sql(
		f"SELECT 1 FROM `tabSupplier` WHERE {last_ten(f'`{supplier_field}`')} = %s LIMIT 1", digits
	):
		return True
	return bool(
		frappe.db.sql(
			f"SELECT 1 FROM `tabSupplier Onboarding` WHERE {last_ten('`mobile`')} = %s AND `{APPROVAL_FIELDNAME}` = %s LIMIT 1",
			(digits, APPROVED_VALUE),
		)
	)
