"""Duplicate check behind the public Supplier Registration web form (/supplier-registration).

Called by the web form's client script (fixtures/web_form.json) as the user leaves a field. A value
counts as a duplicate when it already exists on:
	1. a Supplier, or
	2. an APPROVED Supplier Onboarding submission (pending / rejected ones do not block re-applying).

The response says where the match was found ("duplicate_in"), so the form can say "already a
registered supplier" vs "already approved in another application".

Guest-accessible on purpose (the form is public), so it answers "does this value exist" for anyone:
that is why only five fields can be checked and the endpoint is rate limited per IP.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

# Supplier Onboarding approval: Workflow state field and the exact (case-sensitive) state name
# configured in the "Supplier Onboarding Workflow". If the state is renamed, update it here.
APPROVAL_FIELDNAME = "workflow_state"
APPROVED_VALUE = "Approved"

# Fields that may be checked, named as on Supplier Onboarding (the web form's DocType).
ALLOWED_FIELDS = {"gstin", "pan", "email", "mobile", "supplier_name"}

# Where Supplier names a field differently. Without this the Supplier lookup on "email" / "mobile"
# matched nothing (no such columns), so only approved onboarding rows were ever caught.
SUPPLIER_FIELDNAMES = {"email": "email_id", "mobile": "mobile_no"}

# Canonical casing applied before comparing, so stored and typed values match whatever the
# database collation. Fields without a canonical form are only stripped.
FIELD_NORMALIZERS = {
	"gstin": lambda v: v.strip().upper(),
	"pan": lambda v: v.strip().upper(),
	"email": lambda v: v.strip().lower(),
}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60 * 60)
def check_duplicate_supplier(fieldname, value, exclude_name=None):
	"""Return {"is_duplicate": bool, "duplicate_in": "Supplier" | "Supplier Onboarding"}.

	fieldname: one of ALLOWED_FIELDS. exclude_name: a record name to ignore, so a record being
	edited does not match itself. "duplicate_in" is omitted when there is no duplicate.
	"""
	if not fieldname or not value:
		return {"is_duplicate": False}

	if fieldname not in ALLOWED_FIELDS:
		frappe.throw(_("Invalid field for duplicate check: {0}").format(fieldname))

	normalizer = FIELD_NORMALIZERS.get(fieldname)
	normalized_value = normalizer(value) if normalizer else value.strip()

	# 1. Existing Supplier record
	supplier_filters = {SUPPLIER_FIELDNAMES.get(fieldname, fieldname): normalized_value}
	if exclude_name:
		supplier_filters["name"] = ["!=", exclude_name]

	if frappe.db.exists("Supplier", supplier_filters):
		return {"is_duplicate": True, "duplicate_in": "Supplier"}

	# 2. Another APPROVED Supplier Onboarding submission
	onboarding_filters = {fieldname: normalized_value, APPROVAL_FIELDNAME: APPROVED_VALUE}
	if exclude_name:
		onboarding_filters["name"] = ["!=", exclude_name]

	if frappe.db.exists("Supplier Onboarding", onboarding_filters):
		return {"is_duplicate": True, "duplicate_in": "Supplier Onboarding"}

	return {"is_duplicate": False}
