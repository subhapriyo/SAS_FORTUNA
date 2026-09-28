from sas_fortuna.overrides.portal_list import paginate_list_context, register

register(
	"Sales Invoice",
	default="posting_date desc",
	sort={"posting_date", "due_date", "grand_total", "outstanding_amount", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.accounts.doctype.sales_invoice.sales_invoice")
