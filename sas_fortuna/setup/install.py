"""Install hooks for SAS Fortuna.

bench install-app syncs the app's DocTypes and then saves every Single DocType
with its field defaults (frappe.installer.init_singles), validating links.
That happens before any after_migrate hook runs, so master records that a
Single's defaults point to must already exist.

install-app also never runs after_migrate, so on a fresh site the landing page
block, portal menu, custom fields, roles and permissions would be missing until
the next migrate. after_install runs those same steps once.
"""

import frappe


def before_install():
	# Fortuna Support Settings defaults repair_receipt_entry_type to the
	# "Repair Receipt" Stock Entry Type. Create it before the DocTypes sync.
	# Idempotent: does nothing if the record already exists.
	from sas_fortuna.setup.support_desk import _create_stock_entry_types

	_create_stock_entry_types()


def after_install():
	# Fortuna Impex sites: Helpdesk agents start clean (Users kept), before the steps below
	# rebuild them from the staff sheet. Install only; a migrate never does this.
	from sas_fortuna.setup.fortuna_impex import reset_helpdesk_agents

	try:
		for line in reset_helpdesk_agents():
			print(f"sas_fortuna: {line}")
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="sas_fortuna after_install: Helpdesk agent reset failed")

	# Run this app's after_migrate steps (all idempotent), in hooks.py order.
	# A failing step is logged, not raised: the next `bench migrate` runs them
	# again, and raising here would leave the app half-installed.
	from sas_fortuna import hooks

	for method in hooks.after_migrate:
		try:
			frappe.get_attr(method)()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"sas_fortuna after_install: {method} failed")
			print(f"sas_fortuna: {method} failed on install; it will run again on the next migrate.")
