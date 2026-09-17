import frappe


def get_portal_sidebar_items():
	settings = frappe.get_single("Portal Settings")
	user_roles = set(frappe.get_roles())
	items = []

	for item in list(getattr(settings, "menu", []) or []) + list(getattr(settings, "custom_menu", []) or []):
		if isinstance(item, dict):
			enabled = item.get("enabled", 0)
			role = item.get("role")
			route = item.get("route")
			title = item.get("title")
		else:
			enabled = getattr(item, "enabled", 0)
			role = getattr(item, "role", None)
			route = getattr(item, "route", None)
			title = getattr(item, "title", None)

		if not enabled or not route:
			continue
		if role and role not in user_roles:
			continue
		items.append({"title": title, "route": route})

	return items


def set_portal_sidebar(context, title="Portal"):
	context.show_sidebar = True
	context.sidebar_title = title
	context.sidebar_items = get_portal_sidebar_items()
	return context
