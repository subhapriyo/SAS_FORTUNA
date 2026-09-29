import frappe
from frappe.utils.user import is_website_user

from sas_fortuna.overrides.portal_list import paginate_list_context, register

COLUMNS = [
	{"label": "Subject / Number", "field": "subject", "kind": "name", "sub": "name", "sub_kind": "text"},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Priority", "field": "priority", "kind": "text"},
	{"label": "Last updated", "field": "modified", "kind": "ago"},
]

register(
	"Issue",
	default="creation desc",
	sort={"creation", "modified", "priority", "status", "name"},
	filters=("status", "priority"),
	paginate=True,
	date_field="opening_date",
)


def _issue_list(doctype, txt, filters, limit_start, limit_page_length=20, order_by=None):
	"""ERPNext's get_issue_list, but passing order_by through (the original drops it, so sorting
	and stable paging on /issues were impossible). Keep in sync with
	erpnext.support.doctype.issue.issue.get_issue_list."""
	from frappe.www.list import get_list

	user = frappe.session.user
	contact = frappe.db.get_value("Contact", {"user": user}, "name")
	customer = None

	if contact:
		contact_doc = frappe.get_doc("Contact", contact)
		customer = contact_doc.get_link_for("Customer")

	ignore_permissions = False
	if is_website_user() and user != "Guest":
		if not filters:
			filters = {}

		if customer:
			filters["customer"] = customer
		else:
			filters["raised_by"] = user

		ignore_permissions = True

	return get_list(
		doctype,
		txt,
		filters,
		limit_start,
		limit_page_length,
		ignore_permissions=ignore_permissions,
		order_by=order_by,
	)


paginate_list_context("erpnext.support.doctype.issue.issue", get_list=_issue_list, columns=COLUMNS)
