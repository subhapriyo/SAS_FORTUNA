"""Supplier portal /purchase-orders (Purchase Order): table columns, sorting, paging.

COLUMNS format: see templates/includes/sf_table_row.html. register(): see list_engine.register.
"""

from sas_fortuna.portal.list_engine import paginate_list_context, register

COLUMNS = [
	{
		"label": "Number / Date",
		"field": "name",
		"kind": "name",
		"sub": "transaction_date",
		"sub_kind": "date",
	},
	{"label": "Order Confirmation No", "field": "order_confirmation_no", "kind": "text"},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Item", "field": "items_preview", "kind": "items"},
	{"label": "Required by", "field": "schedule_date", "kind": "date"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
]

register(
	"Purchase Order",
	default="transaction_date desc",
	sort={"transaction_date", "schedule_date", "grand_total", "status", "name"},
	paginate=True,
	date_field="transaction_date",
)
paginate_list_context("erpnext.buying.doctype.purchase_order.purchase_order", columns=COLUMNS)
