from sas_fortuna.overrides.portal_list import paginate_list_context, register

register(
	"Purchase Order",
	default="transaction_date desc",
	sort={"transaction_date", "schedule_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.buying.doctype.purchase_order.purchase_order")
