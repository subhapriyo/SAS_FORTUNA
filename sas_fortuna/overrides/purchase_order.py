from sas_fortuna.overrides.portal_list import paginate_list_context, register

COLUMNS = [
	{
		"label": "Number / Date",
		"field": "name",
		"kind": "name",
		"sub": "transaction_date",
		"sub_kind": "date",
	},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Item", "field": "items_preview", "kind": "items"},
	{"label": "Required by", "field": "schedule_date", "kind": "date"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
]

register(
	"Purchase Order",
	default="transaction_date desc",
	sort={"transaction_date", "schedule_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.buying.doctype.purchase_order.purchase_order", columns=COLUMNS)
