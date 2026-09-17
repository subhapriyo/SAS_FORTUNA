import frappe


# Customer KYC page metadata for the portal view.
def get_context(context):
	context.no_cache = 1
	context.show_sidebar = True
	context.title = "Customer KYC"
