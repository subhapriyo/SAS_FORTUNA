"""AMC enquiry Opportunities on a site where fortuna_erp makes ~19 CRM fields mandatory  (F1).

The problem: fortuna_erp's sales team qualifies every lead (job title, software
pitched, industry vertical, annual revenue, employees ...). An AMC enquiry made
by the daily job is not a new lead: it is an existing customer whose warranty
ends. Those answers are unknown, so every insert failed.

The fix, without changing what sales sees:
  1. setup/support_desk.py turns these fields from "always mandatory" into
     "mandatory unless the Opportunity carries a Serial No" (Property Setters,
     re-applied on every migrate). Sales opportunities have no serial, so their
     form asks for everything as before.
  2. validate() below repeats that rule on the server, because Frappe checks
     "mandatory depends on" only in the browser. Imports and API calls for
     sales opportunities still need every field. For an AMC enquiry it lifts the
     CRM fields itself (_lift_crm_fields), so the daily job keeps working even if
     someone ticks them "Mandatory" again in Customize Form (as on 27 Oct 2026).
  3. make_amc_opportunity() fills everything it can from the customer, its
     primary contact and address, and Fortuna Support Settings.
  4. Because a Serial No lifts the CRM fields, the serial must be genuine:
     the Opportunity is for a Customer, the serial was sold to that customer,
     and only one open Opportunity per serial. Otherwise anyone could skip the
     sales qualification by typing a serial.
"""

import frappe
from frappe import _
from frappe.utils import today

# CRM qualification fields an AMC enquiry cannot know. Mandatory for sales only.
QUALIFICATION_FIELDS = [
	"custom_first_name",
	"custom_last_name",
	"custom_job_title__designation",
	"custom_prospect_type",
	"custom_software_pitched",
	"custom_industry_vertical",
	"no_of_employees",
	"custom_opportunity_annual_revenue",
	"industry",
	"market_segment",
	"custom_email_id",
	"custom_mobile_no",
	"city",
	"state",
	"country",
]
SALES_ONLY = "eval:!doc.custom_serial_no"


def is_amc_enquiry(doc):
	return bool(doc.get("custom_serial_no"))


# Opportunities in these states are finished, so a new one for the same unit is fine.
CLOSED_STATUS = ("Lost", "Closed", "Converted")
CLOSED_FORTUNA_STATUS = ("Won", "Lost")


def validate(doc, method=None):
	"""Server-side rules for both kinds of Opportunity."""
	if is_amc_enquiry(doc):
		_validate_amc_enquiry(doc)
		return
	if doc.flags.ignore_mandatory:
		return
	meta = doc.meta
	missing = [
		_(meta.get_label(f))
		for f in QUALIFICATION_FIELDS
		if meta.has_field(f) and meta.get_field(f).mandatory_depends_on == SALES_ONLY and not doc.get(f)
	]
	if missing:
		frappe.throw(
			_("Please fill: {0}").format(", ".join(missing)),
			frappe.MandatoryError,
			title=_("Missing Values Required"),
		)


def _validate_amc_enquiry(doc):
	"""A serial only lifts the CRM fields when it really is this customer's unit."""
	from sas_fortuna.support.utils import find_sale_for_serial

	_lift_crm_fields(doc)

	serial = doc.custom_serial_no
	if doc.opportunity_from != "Customer":
		frappe.throw(
			_("An Opportunity with a Serial No must be for a Customer (Opportunity From = Customer).")
		)

	owner = find_sale_for_serial(serial).customer
	if not owner:
		frappe.throw(
			_("Serial No {0} has not been sold to any customer, so it cannot be used here.").format(serial)
		)
	if owner != doc.party_name:
		frappe.throw(_("Serial No {0} belongs to {1}, not {2}.").format(serial, owner, doc.party_name))

	other = frappe.db.get_value(
		"Opportunity",
		{
			"custom_serial_no": serial,
			"name": ["!=", doc.name or ""],
			"status": ["not in", CLOSED_STATUS],
			"custom_opportunity_status": ["not in", CLOSED_FORTUNA_STATUS],
		},
		"name",
	)
	if other:
		frappe.throw(_("Serial No {0} already has an open Opportunity: {1}.").format(serial, other))


def _lift_crm_fields(doc):
	"""Skip only the CRM qualification fields' "Mandatory", whatever Customize Form says.

	The Property Setters from step 1 are site settings: a Customize Form save can tick
	"Mandatory" again (it happened on 27 Oct 2026), and every AMC enquiry then failed silently
	in the daily job. So Frappe's own mandatory check is switched off for an AMC enquiry and
	done here instead, for every required field except QUALIFICATION_FIELDS (child rows too).
	"""
	missing = []
	for row in (doc, *doc.get_all_children()):
		for df in row.meta.get("fields", {"reqd": 1}):
			if row is doc and df.fieldname in QUALIFICATION_FIELDS:
				continue
			if df.fieldtype in frappe.model.no_value_fields and df.fieldtype not in frappe.model.table_fields:
				continue
			value = row.get(df.fieldname)
			if value is None or value == "" or value == []:  # 0 is a value, as in Frappe's own check
				missing.append(df.fieldname)
	if missing:
		frappe.throw(
			_("[{0}, {1}]: {2}").format(doc.doctype, doc.name, ", ".join(missing)),
			frappe.MandatoryError,
			title=_("Missing Values Required"),
		)
	doc.flags.ignore_mandatory = True


def make_amc_opportunity(serial, settings):
	"""One Opportunity for a unit whose warranty is ending. Returns the inserted doc."""
	customer = frappe.get_cached_doc("Customer", serial.custom_sold_to)
	opp = frappe.new_doc("Opportunity")
	opp.update(
		{
			"opportunity_from": "Customer",
			"party_name": customer.name,
			"custom_serial_no": serial.name,
			"company": settings.company,
			"transaction_date": today(),
			"opportunity_owner": _owner(settings),
			"territory": customer.territory or _root("Territory"),
			"custom_company_name": customer.customer_name,
			"custom_converted_on": today(),
			"custom_opportunity_status": "Quotation Requested",
			"custom_request_type": "AMC Renewal",
			"industry": customer.get("industry"),
			"market_segment": customer.get("market_segment"),
		}
	)
	opp.update(_contact(customer))
	opp.update(_address(customer))
	# The unit whose warranty ends. Rate 0: the AMC price is set later on the quotation.
	opp.append("items", {"item_code": serial.item_code, "qty": 1, "rate": 0})
	opp.insert(ignore_permissions=True)
	return opp


def _owner(settings):
	if settings.get("amc_opportunity_owner"):
		return settings.amc_opportunity_owner
	users = frappe.get_all(
		"Has Role",
		filters={"role": "AMC Team", "parenttype": "User", "parent": ["not in", ["Administrator", "Guest"]]},
		pluck="parent",
	)
	enabled = [u for u in users if frappe.db.get_value("User", u, "enabled")]
	return sorted(enabled)[0] if enabled else "Administrator"


def _root(doctype):
	return frappe.db.get_value(
		doctype, {"is_group": 1, "parent_" + frappe.scrub(doctype): ["in", ["", None]]}, "name"
	)


def _contact(customer):
	if not customer.customer_primary_contact:
		return {}
	c = frappe.db.get_value(
		"Contact",
		customer.customer_primary_contact,
		["first_name", "last_name", "email_id", "mobile_no", "designation"],
		as_dict=True,
	)
	if not c:
		return {}
	return {
		"custom_first_name": c.first_name,
		"custom_last_name": c.last_name,
		"custom_email_id": c.email_id,
		"custom_mobile_no": c.mobile_no,
		"custom_job_title__designation": c.designation,
		"contact_person": customer.customer_primary_contact,
	}


def _address(customer):
	if not customer.customer_primary_address:
		return {}
	a = frappe.db.get_value(
		"Address", customer.customer_primary_address, ["city", "state", "country"], as_dict=True
	)
	return (
		{
			"city": a.city,
			"state": a.state,
			"country": a.country,
			"customer_address": customer.customer_primary_address,
		}
		if a
		else {}
	)
