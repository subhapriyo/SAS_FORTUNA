import frappe


# Portal menu item for supplier onboarding and compliance updates.
def execute():
	doc = frappe.get_single("Portal Settings")

	# Remove stale entries before re-adding the route to avoid duplicates.
	doc.custom_menu = [row for row in doc.custom_menu if row.title != "Supplier KYC"]

	doc.append(
		"custom_menu",
		{
			"title": "Supplier KYC",
			"enabled": 1,
			"route": "/supplier-kyc",
			"role": "Supplier",
		},
	)

	doc.save(ignore_permissions=True)
	frappe.db.commit()
