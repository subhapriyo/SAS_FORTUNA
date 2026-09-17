import frappe

from sas_fortuna.portal import set_portal_sidebar


# Supplier KYC page metadata for the portal view.
def get_context(context):
	context.no_cache = 1
	set_portal_sidebar(context, "Portal")
	context.title = "Supplier KYC"
