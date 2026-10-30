"""after_migrate: put the SAS Fortuna tile into every saved desktop layout.

Why
    In the Desktop Icons grid (Frappe v16), a user who has ever saved a desktop layout
    sees only the icons stored in that layout: the client rebuilds the grid from the saved
    `Desktop Layout` (frappe.desktop_utils.arrange_layout) and never adds icons that were
    created on the site afterwards. So the SAS Fortuna App icon (desktop_icon/sas_fortuna.json)
    reaches the browser but is not drawn for those users.

What it does
    Appends the SAS Fortuna icon to the end of each saved layout that does not contain it yet
    (anywhere, including inside folders). The user's existing order, folders and hidden flags
    are left alone, and a layout that already has the icon -- even hidden by the user -- is not
    touched. Idempotent.
"""

import json

import frappe

ICON = "SAS Fortuna"
FIELDS = [
	"app",
	"bg_color",
	"hidden",
	"icon",
	"icon_image",
	"icon_type",
	"idx",
	"label",
	"link",
	"link_to",
	"link_type",
	"logo_url",
	"name",
	"parent_icon",
	"restrict_removal",
	"standard",
]


def _labels(entries):
	for entry in entries or []:
		if isinstance(entry, dict):
			yield entry.get("label")
			yield from _labels(entry.get("child_icons"))


def execute():
	if not frappe.db.exists("DocType", "Desktop Layout") or not frappe.db.exists("Desktop Icon", ICON):
		return

	icon = frappe.db.get_value("Desktop Icon", ICON, FIELDS, as_dict=True)
	entry = {**icon, "child_icons": []}

	changed = False
	for name in frappe.get_all("Desktop Layout", pluck="name"):
		raw = frappe.db.get_value("Desktop Layout", name, "layout")
		try:
			layout = json.loads(raw or "[]")
		except ValueError:
			continue
		# an empty layout falls back to the server's icons on the client, so it needs nothing
		if not isinstance(layout, list) or not layout or ICON in set(_labels(layout)):
			continue
		layout.append(entry)
		frappe.db.set_value("Desktop Layout", name, "layout", json.dumps(layout), update_modified=False)
		changed = True

	if changed:
		from frappe.desk.doctype.desktop_icon.desktop_icon import clear_every_users_desktop_icons

		clear_every_users_desktop_icons()
