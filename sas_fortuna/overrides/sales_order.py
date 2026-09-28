from sas_fortuna.overrides.portal_list import paginate_list_context, register

register(
	"Sales Order",
	default="transaction_date desc",
	sort={"transaction_date", "delivery_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.selling.doctype.sales_order.sales_order")
