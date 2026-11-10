"""Install hooks for SAS Fortuna.

bench install-app syncs the app's DocTypes and then saves every Single DocType
with its field defaults (frappe.installer.init_singles), validating links.
That happens before any after_migrate hook runs, so master records that a
Single's defaults point to must already exist.
"""


def before_install():
	# Fortuna Support Settings defaults repair_receipt_entry_type to the
	# "Repair Receipt" Stock Entry Type. Create it before the DocTypes sync.
	# Idempotent: does nothing if the record already exists.
	from sas_fortuna.setup.support_desk import _create_stock_entry_types

	_create_stock_entry_types()
