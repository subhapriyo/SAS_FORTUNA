"""after_migrate: keep the KYC pages in the portal sidebar (Portal Settings > Custom Menu).

The Portal Settings fixture already carries these entries; this makes sure they exist and point at
the right page on any site. Entries are matched by title and fixed in place, so their position and
enabled flag (an admin may switch one off) are kept. Duplicates by title are removed.
"""

import frappe

# route = the page in templates/pages/ (customer.html -> /customer)
KYC_MENU_ITEMS = (
	{"title": "Customer KYC", "route": "/customer", "role": "Customer"},
	{"title": "Supplier KYC", "route": "/supplier", "role": "Supplier"},
)


def execute():
	settings = frappe.get_single("Portal Settings")
	changed = False

	for item in KYC_MENU_ITEMS:
		rows = [row for row in settings.custom_menu if row.title == item["title"]]
		if not rows:
			settings.append("custom_menu", {**item, "enabled": 1})
			changed = True
			continue

		row, duplicates = rows[0], rows[1:]
		for key in ("route", "role"):
			if row.get(key) != item[key]:
				row.set(key, item[key])
				changed = True
		if duplicates:
			settings.custom_menu = [r for r in settings.custom_menu if r not in duplicates]
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
