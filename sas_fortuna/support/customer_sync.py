"""Keep one customer identity across ERPNext and Helpdesk  (C1, P1).

ERPNext 'Customer' -> Helpdesk 'HD Customer' (linked by custom field
custom_erpnext_customer). Contacts of the Customer are also linked to the
HD Customer so portal users see their company's tickets, and the Contact's
portal user gets Helpdesk's customer role, so the Helpdesk customer pages
(New ticket / Reply, linked from the portal's /tickets) open for them.
"""

import frappe

from sas_fortuna.support.utils import get_hd_customer


def customer_after_insert(doc, method=None):
	ensure_hd_customer(doc.name, doc.customer_name)


def ensure_hd_customer(customer, customer_name=None):
	"""Create the matching HD Customer once; return its name."""
	existing = get_hd_customer(customer)
	if existing:
		return existing
	name = customer_name or customer
	# An HD Customer with the same name may already exist (created in
	# Helpdesk before this sync): link it instead of creating a duplicate.
	if frappe.db.exists("HD Customer", name):
		frappe.db.set_value("HD Customer", name, "custom_erpnext_customer", customer)
		return name
	hd = frappe.get_doc(
		{"doctype": "HD Customer", "customer_name": name, "custom_erpnext_customer": customer}
	)
	hd.insert(ignore_permissions=True)
	return hd.name


def contact_validate(doc, method=None):
	"""If a Contact belongs to a Customer, also link it to the HD Customer, and give its portal
	user the Helpdesk customer role."""
	linked = {(link.link_doctype, link.link_name) for link in doc.links}
	for link_doctype, link_name in list(linked):
		if link_doctype != "Customer":
			continue
		hd_customer = get_hd_customer(link_name)
		if hd_customer and ("HD Customer", hd_customer) not in linked:
			doc.append("links", {"link_doctype": "HD Customer", "link_name": hd_customer})
		if doc.user:
			grant_helpdesk_role(doc.user)


# ---------------------------------------------------------------------------
# Helpdesk role for portal users
# ---------------------------------------------------------------------------
# Helpdesk's customer pages (/helpdesk/my-tickets: list, new ticket, reply) need this role.
# ERPNext portal users only get "Customer", so without it those pages show
# "Insufficient Permission" and stay empty.
HELPDESK_CUSTOMER_ROLE = "HD Customer"


def grant_helpdesk_role(user):
	"""Give a customer's portal user the Helpdesk customer role (website users only; staff use Agent)."""
	if not frappe.db.exists("Role", HELPDESK_CUSTOMER_ROLE):
		return
	if frappe.db.get_value("User", user, "user_type") != "Website User":
		return
	if HELPDESK_CUSTOMER_ROLE not in frappe.get_roles(user):
		frappe.get_doc("User", user).add_roles(HELPDESK_CUSTOMER_ROLE)


def grant_helpdesk_role_to_portal_users():
	"""Backfill (after_migrate): every portal user linked to a Customer gets the Helpdesk role."""
	users = frappe.db.sql(
		"""select distinct c.user from `tabContact` c
		join `tabDynamic Link` l on l.parent = c.name and l.parenttype = 'Contact' and l.link_doctype = 'Customer'
		where ifnull(c.user, '') != ''""",
		pluck=True,
	)
	users += frappe.get_all("Portal User", filters={"parenttype": "Customer"}, pluck="user")
	for user in {u for u in users if u}:
		grant_helpdesk_role(user)


def sync_all_customers():
	"""One-time backfill. Run:  bench --site fortuna.localhost execute
	sas_fortuna.support.customer_sync.sync_all_customers
	"""
	for c in frappe.get_all("Customer", filters={"disabled": 0}, fields=["name", "customer_name"]):
		ensure_hd_customer(c.name, c.customer_name)
	frappe.db.commit()  # needed because bench execute does not auto-commit
