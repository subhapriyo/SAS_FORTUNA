"""Serve /issues and /my-ledger as proper portal list pages (with sidebar, columns and filters).

The problem
    Both routes also belong to a Web Form (ERPNext's "issues", our "my-ledger").
    For /issues: ERPNext ships a standard Web Form called "issues" on the same route. Frappe tries Web Forms
    before list pages, so /issues redirected to Frappe's plain web-form list (/issues/list): no
    portal left menu and none of the columns / filters / paging of our other portal lists
    (portal/lists/issue.py).

The fix
    hooks.py registers PortalListPage as a page_renderer; custom renderers are tried before
    Frappe's own, so /issues is served by Frappe's normal list page. The Web Form itself is not
    touched: /issues/new and /issues/<name> still use it. Likewise /my-ledger is served as the
    GL Entry list (portal/lists/gl_entry.py) and /my-ledger/<entry> still uses the Web Form.

Note: on Fortuna the portal menu now links "Tickets" (Helpdesk) instead of "Issues"
(support/portal_tickets.py). This stays so /issues still looks right for anyone who opens it.
"""

import frappe
from frappe.website.page_renderers.list_renderer import ListPage

# route (or the doctype name it may arrive as) -> doctype whose portal list is served
LIST_ROUTES = {"issues": "Issue", "Issue": "Issue", "my-ledger": "GL Entry"}


class PortalListPage(ListPage):
	def can_render(self):
		doctype = LIST_ROUTES.get(self.path)
		# frappe.flags.sas_portal_active is set by our before_request hook, so other sites on the
		# same bench (without sas_fortuna) keep Frappe's normal behaviour.
		if not doctype or not frappe.flags.sas_portal_active:
			return False
		self.path = doctype  # ListPage expects the doctype name as the path
		return super().can_render()
