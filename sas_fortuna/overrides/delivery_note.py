from sas_fortuna.overrides.portal_list import paginate_list_context, register

COLUMNS = [
	{"label": "Number / Date", "field": "name", "kind": "name", "sub": "posting_date", "sub_kind": "date"},
	{"label": "Customer's Purchase Order", "field": "po_no", "kind": "text"},
	{"label": "Customer's Purchase Order Date", "field": "po_date", "kind": "date"},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Item", "field": "items_preview", "kind": "items"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
]

register(
	"Delivery Note",
	default="posting_date desc",
	sort={"posting_date", "po_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
	date_field="posting_date",
)
paginate_list_context("erpnext.stock.doctype.delivery_note.delivery_note", columns=COLUMNS)
