from sas_fortuna.overrides.portal_list import paginate_list_context, register

COLUMNS = [
	{
		"label": "Number / Date",
		"field": "name",
		"kind": "name",
		"sub": "transaction_date",
		"sub_kind": "date",
	},
	{
		"label": "Customer's Purchase Order / Date",
		"field": "po_no",
		"kind": "stack",
		"sub": "po_date",
		"sub_kind": "date",
	},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Item", "field": "items_preview", "kind": "items"},
	{"label": "Delivery", "field": "delivery_date", "kind": "date"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
]

register(
	"Sales Order",
	default="transaction_date desc",
	sort={"transaction_date", "po_no", "po_date", "delivery_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
	date_field="transaction_date",
)
paginate_list_context("erpnext.selling.doctype.sales_order.sales_order", columns=COLUMNS)
