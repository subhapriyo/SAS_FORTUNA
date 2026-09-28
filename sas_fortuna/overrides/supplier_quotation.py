from sas_fortuna.overrides.portal_list import paginate_list_context, register

register(
	"Supplier Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "valid_till", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.buying.doctype.supplier_quotation.supplier_quotation")
