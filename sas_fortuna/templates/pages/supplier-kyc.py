import frappe


# Supplier view metadata used by the portal page.
def get_context(context):
	context.no_cache = 1
	context.show_sidebar = True
	context.title = "Supplier KYC"
