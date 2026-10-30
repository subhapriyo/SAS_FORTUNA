"""Small tweaks to every portal page's context (hooks.py: update_website_context).

1. add_portal_menu: the portal left menu on our Web Form pages (e.g. /my-ledger/<entry>)
    Pages built as Web Forms are drawn without the portal left menu: a Web Form only gets a
    sidebar when it is linked to a "Website Sidebar" record, and then shows that record's links
    instead of the portal menu (Portal Settings). For the routes in WEB_FORM_ROUTES we switch the
    sidebar on and fill it with the same portal menu that /orders, /tickets, /repairs ... show.
    To give another Web Form the menu, add its route to WEB_FORM_ROUTES.

2. drop_title_prefix: no "Fortuna - " in portal and Web Form headings
    Website Settings > Title Prefix ("Fortuna") is added by Frappe to every page title, and portal
    pages print that title as their heading and in the breadcrumb ("Fortuna - Repairs"). On portal
    pages (logged-in pages with the left menu) and on Web Forms (e.g. /supplier-registration) we
    take it off again. Frappe adds the prefix just before running this hook, so the order is safe.
    Other public pages (home, login) keep it.
"""

import frappe
from frappe.website.utils import get_portal_sidebar_items

WEB_FORM_ROUTES = ("my-ledger",)  # Web Form routes that should show the portal left menu


def add_portal_menu(context):
	if frappe.session.user == "Guest":  # the menu is for logged-in portal users
		return None
	request = getattr(frappe.local, "request", None)
	path = (getattr(request, "path", "") or "").strip("/")
	if path.split("/")[0] not in WEB_FORM_ROUTES:
		return None
	return {"show_sidebar": True, "sidebar_items": get_portal_sidebar_items()}


def drop_title_prefix(context):
	prefix = context.get("title_prefix")
	title = context.get("title")
	portal_page = frappe.session.user != "Guest" and context.get("show_sidebar")
	web_form = context.get("web_form_doc")  # e.g. the public /supplier-registration
	if not (portal_page or web_form) or not prefix or not title:
		return None
	if not isinstance(title, str) or not title.startswith(f"{prefix} - "):
		return None
	return {"title": title[len(prefix) + 3 :]}
