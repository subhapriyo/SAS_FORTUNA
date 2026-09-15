import frappe


def execute():
	doc = frappe.get_single("Portal Settings")

	# Remove if already exists (avoid duplicates)
	doc.custom_menu = [row for row in doc.custom_menu if row.title != "Vendor KYC"]

	doc.append(
		"custom_menu", {"title": "Vendor KYC", "enabled": 1, "route": "/vendor-kyc", "role": "Supplier"}
	)

	doc.save(ignore_permissions=True)
	frappe.db.commit()
