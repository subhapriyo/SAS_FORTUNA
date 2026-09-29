from sas_fortuna.overrides.portal_list import paginate_list_context, register

# Supplier portal: /purchase-invoices. Supplier Invoice No / Date are the supplier's own bill
# reference (bill_no / bill_date), shown as one two-line column right after Number / Date.
COLUMNS = [
	{"label": "Number / Date", "field": "name", "kind": "name", "sub": "posting_date", "sub_kind": "date"},
	{
		"label": "Supplier Invoice No / Date",
		"field": "bill_no",
		"kind": "stack",
		"sub": "bill_date",
		"sub_kind": "date",
	},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Due date", "field": "due_date", "kind": "date"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
	{"label": "Outstanding", "field": "outstanding_amount", "kind": "money"},
]

register(
	"Purchase Invoice",
	default="posting_date desc",
	sort={
		"posting_date",
		"bill_no",
		"bill_date",
		"due_date",
		"grand_total",
		"outstanding_amount",
		"status",
		"name",
	},
	filters=("status",),
	paginate=True,
	date_field="posting_date",
)
paginate_list_context("erpnext.accounts.doctype.purchase_invoice.purchase_invoice", columns=COLUMNS)
