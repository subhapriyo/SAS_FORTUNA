"""Guide section 0 checks: does this site have the fields the support code uses?

Read-only. Run:
    bench --site fortuna.localhost execute sas_fortuna.support.check_env.run
"""

import frappe

CHECKS = {
	"HD Ticket": [
		"ticket_type",
		"agent_group",
		"customer",
		"priority",
		"status",
		"description",
		"resolution_details",
		"raised_by",
	],
	"HD Customer": ["customer_name"],
	"HD Agent": ["user", "is_active"],
	"Stock Entry Detail": ["use_serial_batch_fields", "serial_no", "allow_zero_valuation_rate"],
	"Delivery Note Item": ["use_serial_batch_fields", "serial_no", "against_sales_invoice"],
	"Serial and Batch Bundle": ["voucher_type", "voucher_no", "type_of_transaction", "is_cancelled"],
	"Item": ["warranty_period"],
	"Serial No": ["amc_expiry_date", "item_code", "status"],
	"Customer": ["mobile_no", "email_id"],
	"Delivery Note": ["contact_email"],
	"Sales Invoice": ["subscription"],
}

# DocTypes our custom fields will be added to (clash check).
TOUCHED = [
	"Serial No",
	"HD Ticket",
	"HD Customer",
	"Stock Entry",
	"Stock Entry Detail",
	"Material Request",
	"Quotation",
	"Sales Order",
	"Sales Invoice",
	"Delivery Note",
	"Opportunity",
]


def run():
	print("\n== Fields the code relies on")
	for dt, fields in CHECKS.items():
		if not frappe.db.exists("DocType", dt):
			print(f"  {dt:26} DOCTYPE MISSING")
			continue
		meta = frappe.get_meta(dt)
		missing = [f for f in fields if not meta.has_field(f)]
		print(f"  {dt:26} {'OK' if not missing else 'MISSING: ' + ', '.join(missing)}")

	print("\n== HD Ticket status")
	st = frappe.get_meta("HD Ticket").get_field("status")
	print(f"  type={st.fieldtype}  options={st.options!r}")
	if frappe.db.exists("DocType", "HD Ticket Status"):
		print("  HD Ticket Status records:", frappe.get_all("HD Ticket Status", pluck="name"))

	print("\n== HD Service Level Agreement fields")
	skip = ("Section Break", "Column Break", "Tab Break")
	print(
		"  ",
		[
			f.fieldname
			for f in frappe.get_meta("HD Service Level Agreement").fields
			if f.fieldtype not in skip
		],
	)

	print(
		"\n== Stock Settings: use_serial_batch_fields =",
		frappe.db.get_single_value("Stock Settings", "use_serial_batch_fields"),
	)

	print("\n== Existing custom fields on DocTypes we touch")
	for cf in frappe.get_all(
		"Custom Field",
		filters={"dt": ["in", TOUCHED]},
		fields=["dt", "fieldname", "fieldtype", "module"],
		order_by="dt, fieldname",
	):
		print(f"  {cf.dt:20} {cf.fieldname:34} {cf.fieldtype:12} {cf.module or ''}")
