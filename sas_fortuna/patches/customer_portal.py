import frappe

CUSTOMER_FIELDS = [
	{"fieldname": "custom_tan_no", "fieldtype": "Data", "label": "TAN No."},
	{
		"fieldname": "custom_tds_applicability",
		"fieldtype": "Select",
		"label": "TDS Applicability",
		"options": "Yes\nNo",
	},
	{
		"fieldname": "custom_tcs_applicable",
		"fieldtype": "Select",
		"label": "TCS Applicable",
		"options": "Yes\nNo",
	},
	{
		"fieldname": "custom_msme",
		"fieldtype": "Select",
		"label": "MSME",
		"options": "Yes\nNo",
	},
	{
		"fieldname": "custom_udyam_registration_number",
		"fieldtype": "Data",
		"label": "Udyam Registration Number",
	},
	{
		"fieldname": "custom_date_of_registration",
		"fieldtype": "Date",
		"label": "Date of Registration",
	},
	{
		"fieldname": "custom_type_of_enterprise",
		"fieldtype": "Select",
		"label": "Type of Enterprise",
		"options": "Micro\nSmall\nMedium",
	},
	{
		"fieldname": "custom_type_of_industry",
		"fieldtype": "Data",
		"label": "Type of Industry",
	},
	{
		"fieldname": "custom_major_activity",
		"fieldtype": "Select",
		"label": "Major Activity",
		"options": "Manufacturer\nTraders\nService Provider",
	},
	{"fieldname": "custom_bank_details", "fieldtype": "Section Break", "label": "Bank Details"},
	{
		"fieldname": "custom_default_customer_bank_account",
		"fieldtype": "Link",
		"label": "Default Customer Bank Account",
		"options": "Bank Account",
	},
	{"fieldname": "custom_gst_certificate", "fieldtype": "Attach", "label": "GST Certificate"},
	{"fieldname": "custom_pan_card", "fieldtype": "Attach", "label": "PAN Card"},
	{
		"fieldname": "custom_certificate_of_incorporation__partnership_deed",
		"fieldtype": "Attach",
		"label": "Certificate of Incorporation / Partnership deed",
	},
	{"fieldname": "custom_cancelled_cheque", "fieldtype": "Attach", "label": "Cancelled Cheque"},
	{
		"fieldname": "custom_last_itr__acknowledgement",
		"fieldtype": "Attach",
		"label": "Last ITR - Acknowledgement",
	},
	{"fieldname": "custom_msme_certificate", "fieldtype": "Attach", "label": "MSME Certificate"},
]


def ensure_customer_fields():
	for field in CUSTOMER_FIELDS:
		if frappe.db.exists("Custom Field", {"dt": "Customer", "fieldname": field["fieldname"]}):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Customer",
				"fieldname": field["fieldname"],
				"fieldtype": field["fieldtype"],
				"label": field["label"],
				"options": field.get("options"),
			}
		).insert(ignore_permissions=True)


def execute():
	ensure_customer_fields()
	doc = frappe.get_single("Portal Settings")

	# Remove if already exists (avoid duplicates)
	doc.custom_menu = [row for row in doc.custom_menu if row.title != "Customer KYC"]

	doc.append(
		"custom_menu", {"title": "Customer KYC", "enabled": 1, "route": "/customer-kyc", "role": "Customer"}
	)

	doc.save(ignore_permissions=True)
	frappe.db.commit()
