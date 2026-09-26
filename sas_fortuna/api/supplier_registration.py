# =============================================================================
# Whitelisted server method backing the client script's duplicate check.
#
# Suggested location: sas_fortuna/api/supplier_registration.py in your
# sas_fortuna custom app, matching CONFIG.duplicateCheckMethod
# ("sas_fortuna.api.supplier_registration.check_duplicate_supplier") in the
# client script. If you place it somewhere else, update that path to match.
#
# Checks TWO doctypes for a duplicate, either of which is enough to flag one:
#   1. Supplier - any existing Supplier record with this value.
#   2. Supplier Onboarding - any OTHER submission of this web form's own
#      DocType (backed by the `tabSupplier Onboarding` table) that has
#      already been approved. An onboarding submission that's still
#      pending/rejected is NOT treated as a duplicate - only an approved one
#      blocks a new submission, on the assumption that a pending or rejected
#      submission shouldn't stop someone from (re)applying.
#
# CHANGE (this revision): the response now also carries a "duplicate_in" key
# ("Supplier" or "Supplier Onboarding") whenever is_duplicate is true. It's
# omitted entirely (not sent as None) when is_duplicate is false, so the
# client can show a message that actually says where the match came
# from, instead of one generic "duplicate" message regardless of source.
# Supplier vs Supplier Onboarding are meaningfully different situations for
# the person filling the form (an already-registered Supplier vs. someone
# else's earlier approved submission), so the fieldname alone
# ("gstin"/"pan"/...) wasn't enough - "is_duplicate: true" told you WHICH
# FIELD collided, not WHERE it collided, and GSTIN is exactly the field most
# likely to legitimately show up in an approved onboarding row that isn't
# in Supplier yet (or vice versa) - the client-side message quoted "duplicate
# GSTIN" either way, which reads as "wrong"/misleading when the actual
# source differs from what the wording implies. is_duplicate is left in
# place unchanged for backward compatibility with any caller only checking
# that key.
#
# CHANGE (this revision): value comparisons for gstin/pan/email are now
# normalized server-side (gstin/pan uppercased, email lowercased) before
# the exists() lookups, rather than trusting the caller to have already
# normalized the value. The client script does normalize before calling
# this method today, but this endpoint is allow_guest=True and reachable
# directly - a case mismatch between what's sent and what's stored (e.g. a
# GSTIN saved in mixed case by some other entry path) would otherwise cause
# an inconsistent match depending on your database's column collation,
# which is one plausible source of the "sometimes wrong for gstin" reports
# if any existing rows predate consistent client-side uppercasing.
#
# Known assumptions (flagging rather than guessing silently):
#   - `allowed_fields` below uses "gstin", "pan", "email", "mobile" and
#     "supplier_name" as the fieldnames shared by BOTH the Supplier DocType
#     and the Supplier Onboarding DocType. "gstin"/"pan" are standard
#     Supplier fields (Tax Details section); "email"/"mobile"/"supplier_name"
#     are per your confirmation of the Supplier DocType's actual fieldnames.
#     I've assumed the Supplier Onboarding DocType (the web form's own
#     DocType) uses these exact same fieldnames too, since the client script
#     is built directly against them - if Supplier Onboarding's fieldnames
#     differ from Supplier's for any of these, ONBOARDING_FIELDNAME_OVERRIDES
#     below is the place to add a mapping.
#   - APPROVAL_FIELDNAME is "workflow_state", per your confirmation that
#     approval is tracked via a real Frappe Workflow. APPROVED_VALUE is
#     still a guess ("Approved") at the exact state label configured in
#     that workflow - workflow state names are free text you chose when
#     setting it up, and the check below is an exact, case-sensitive
#     compare against it, so this needs to match your actual configured
#     label (Workflow List > your Supplier Onboarding workflow > States) or
#     the check will silently never find a match.
#   - allow_guest=True is set because a public Supplier Onboarding web form
#     is typically filled out by anonymous/portal visitors with no read
#     permission on either DocType themselves; frappe.db.exists() bypasses
#     that permission check by design here, which is normally what you want
#     for this specific, narrow existence check - but it does mean this
#     endpoint answers "does a record with this value exist" for anyone who
#     can reach the URL, without further permission checks. If that's
#     broader than you want, add rate-limiting or narrow the allowed fields
#     further.
# =============================================================================

import frappe
from frappe import _

# Fieldname on the Supplier Onboarding DocType that tracks approval state,
# and the value that means "approved". See "Known assumptions" above -
# adjust both if your workflow uses a Frappe Workflow ("workflow_state")
# instead of a plain status field.
APPROVAL_FIELDNAME = "workflow_state"

# The exact label for the "approved" workflow state, as configured in your
# Workflow doctype (Workflow List > your Supplier Onboarding workflow >
# States table). This is free text you (or whoever set up the workflow)
# chose - I can't know it without you confirming it, and the match below is
# an exact, case-sensitive string compare against that label. If this
# doesn't match your workflow's actual state name, this check will never
# find a match and duplicates won't be caught.
APPROVED_VALUE = "Approved"

# Only needed if a field is named differently on Supplier Onboarding than on
# Supplier - e.g. ONBOARDING_FIELDNAME_OVERRIDES = {"supplier_name": "company_name"}.
# Empty by default since both DocTypes are assumed to share fieldnames.
ONBOARDING_FIELDNAME_OVERRIDES = {}

# Fields normalized server-side before comparison, and how. Only fields with
# a fixed canonical casing are listed - mobile/supplier_name are left as-is
# since they don't have one.
FIELD_NORMALIZERS = {
	"gstin": lambda v: v.strip().upper(),
	"pan": lambda v: v.strip().upper(),
	"email": lambda v: v.strip().lower(),
}


@frappe.whitelist(allow_guest=True)
def check_duplicate_supplier(fieldname, value, exclude_name=None):
	"""
	Returns whether the given fieldname/value pair already exists as either
	(a) a Supplier record, or (b) an APPROVED Supplier Onboarding submission
	other than the one being edited - and, if so, which of the two it was
	found in.

	Args:
		fieldname (str): One of "gstin", "pan", "email", "mobile",
			"supplier_name".
		value (str): The value to check for.
		exclude_name (str, optional): A `name` to exclude from both checks -
			relevant if this form is ever used to edit an existing Supplier
			or an existing Supplier Onboarding submission, so a record
			doesn't flag itself as a duplicate of itself.

	Returns:
		dict: {
			"is_duplicate": bool,
			"duplicate_in": "Supplier" | "Supplier Onboarding" | None
		}
	"""
	if not fieldname or not value:
		return {"is_duplicate": False}

	allowed_fields = {"gstin", "pan", "email", "mobile", "supplier_name"}
	if fieldname not in allowed_fields:
		frappe.throw(_("Invalid field for duplicate check: {0}").format(fieldname))

	normalizer = FIELD_NORMALIZERS.get(fieldname)
	normalized_value = normalizer(value) if normalizer else value.strip()

	# 1. Existing Supplier record
	supplier_filters = {fieldname: normalized_value}
	if exclude_name:
		supplier_filters["name"] = ["!=", exclude_name]

	if frappe.db.exists("Supplier", supplier_filters):
		return {"is_duplicate": True, "duplicate_in": "Supplier"}

	# 2. Another APPROVED Supplier Onboarding submission
	onboarding_fieldname = ONBOARDING_FIELDNAME_OVERRIDES.get(fieldname, fieldname)
	onboarding_filters = {onboarding_fieldname: normalized_value, APPROVAL_FIELDNAME: APPROVED_VALUE}
	if exclude_name:
		onboarding_filters["name"] = ["!=", exclude_name]

	if frappe.db.exists("Supplier Onboarding", onboarding_filters):
		return {"is_duplicate": True, "duplicate_in": "Supplier Onboarding"}

	return {"is_duplicate": False}
