"""Customer portal /invoices (Sales Invoice): table columns, sorting, paging.

COLUMNS format: see templates/includes/sf_table_row.html. register(): see list_engine.register.
"""

from sas_fortuna.portal.list_engine import paginate_list_context, register

COLUMNS = [
	{"label": "Number / Date", "field": "name", "kind": "name", "sub": "posting_date", "sub_kind": "date"},
	{
		"label": "Customer's Purchase Order / Date",
		"field": "po_no",
		"kind": "stack",
		"sub": "po_date",
		"sub_kind": "date",
	},
	{"label": "Status", "field": "status", "kind": "status"},
	{"label": "Due date", "field": "due_date", "kind": "date"},
	{"label": "Amount", "field": "grand_total", "kind": "money"},
	{"label": "Outstanding", "field": "outstanding_amount", "kind": "money"},
]

register(
	"Sales Invoice",
	default="posting_date desc",
	sort={
		"posting_date",
		"po_no",
		"po_date",
		"due_date",
		"grand_total",
		"outstanding_amount",
		"status",
		"name",
	},
	paginate=True,
	date_field="posting_date",
)
paginate_list_context("erpnext.accounts.doctype.sales_invoice.sales_invoice", columns=COLUMNS)
