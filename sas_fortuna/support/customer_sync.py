"""Keep one customer identity across ERPNext and Helpdesk  (C1, P1).

ERPNext 'Customer' -> Helpdesk 'HD Customer' (linked by custom field
custom_erpnext_customer). Contacts of the Customer are also linked to the
HD Customer so portal users see their company's tickets, and the Contact's
portal user gets Helpdesk's customer role, so the Helpdesk customer pages
(New ticket / Reply, linked from the portal's /tickets) open for them.

Helpdesk finds a Contact's customers through the HD Customer's Contacts table
(HD Customer Member), not through the Contact's links. So every linked Contact is
also made a member (contact_on_update, and sync_customer_members on migrate):
without it a new ticket's Customer stays empty.
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
# HD Customer members (what Helpdesk reads to fill a ticket's Customer)
# ---------------------------------------------------------------------------
def contact_on_update(doc, method=None):
	"""Make the Contact a member of every HD Customer it is linked to."""
	for link in doc.links:
		if link.link_doctype == "HD Customer":
			ensure_member(link.link_name, doc.name)


def ensure_member(hd_customer, contact):
	"""Add the Contact to the HD Customer's Contacts table once; True when added.

	The row is written directly, not through hd.save(): saving an HD Customer saves the
	contact's User, which saves the Contact again (contact_on_update) before the row is in
	the database - an endless loop. The portal role it would grant comes from
	contact_validate (grant_helpdesk_role) instead."""
	if not frappe.db.exists("HD Customer", hd_customer):
		return False
	members = {"parenttype": "HD Customer", "parentfield": "contacts", "parent": hd_customer}
	if frappe.db.exists("HD Customer Member", {**members, "contact_name": contact}):
		return False
	frappe.get_doc(
		{
			"doctype": "HD Customer Member",
			**members,
			"idx": frappe.db.count("HD Customer Member", members) + 1,
			"contact_name": contact,
		}
	).db_insert()
	frappe.clear_document_cache("HD Customer", hd_customer)
	return True


def sync_customer_members():
	"""Backfill (every migrate): Contacts linked to an HD Customer but not yet its members."""
	if not frappe.db.exists("DocType", "HD Customer Member"):
		return []
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": "HD Customer"},
		fields=["parent", "link_name"],
	)
	return [
		f"HD Customer {r.link_name}: member {r.parent}" for r in links if ensure_member(r.link_name, r.parent)
	]


def backfill_ticket_customers():
	"""Backfill (every migrate): tickets with no Helpdesk Customer get it from their ERPNext
	Customer, else from their Contact when it belongs to exactly one HD Customer. Written
	directly, so no e-mail, SLA or assignment runs again on old tickets."""
	from helpdesk.utils import get_customers

	from sas_fortuna.support.utils import get_hd_customer

	has_erp = frappe.get_meta("HD Ticket").has_field("custom_erpnext_customer")
	fields = ["name", "contact"] + (["custom_erpnext_customer"] if has_erp else [])
	done = []
	for t in frappe.get_all("HD Ticket", filters={"customer": ["is", "not set"]}, fields=fields):
		customer = get_hd_customer(t.get("custom_erpnext_customer"))
		if not customer and t.contact:
			customers = get_customers(contact=t.contact)
			customer = customers[0] if len(customers) == 1 else None
		if customer:
			frappe.db.set_value("HD Ticket", t.name, "customer", customer, update_modified=False)
			done.append(f"Ticket {t.name}: customer {customer}")
	return done


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
