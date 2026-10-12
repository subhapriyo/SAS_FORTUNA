"""Keep one customer identity across ERPNext and Helpdesk  (C1, P1).

ERPNext 'Customer' -> Helpdesk 'HD Customer' (linked by custom field
custom_erpnext_customer). Contacts of the Customer are also linked to the
HD Customer so portal users see their company's tickets.
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
	"""If a Contact belongs to a Customer, also link it to the HD Customer."""
	linked = {(link.link_doctype, link.link_name) for link in doc.links}
	for link_doctype, link_name in list(linked):
		if link_doctype != "Customer":
			continue
		hd_customer = get_hd_customer(link_name)
		if hd_customer and ("HD Customer", hd_customer) not in linked:
			doc.append("links", {"link_doctype": "HD Customer", "link_name": hd_customer})


def sync_all_customers():
	"""One-time backfill. Run:  bench --site fortuna.localhost execute
	sas_fortuna.support.customer_sync.sync_all_customers
	"""
	for c in frappe.get_all("Customer", filters={"disabled": 0}, fields=["name", "customer_name"]):
		ensure_hd_customer(c.name, c.customer_name)
	frappe.db.commit()  # needed because bench execute does not auto-commit
