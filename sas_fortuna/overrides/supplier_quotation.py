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
	{"label": "Valid till", "field": "valid_till", "kind": "date"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
]

register(
	"Supplier Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "valid_till", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.buying.doctype.supplier_quotation.supplier_quotation", columns=COLUMNS)
