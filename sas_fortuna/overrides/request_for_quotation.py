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
	{"label": "Company", "field": "company", "kind": "text"},
]

# RFQs are listed through the "Request for Quotation Supplier" child table, so there is no cheap
# total for the effective filters: count=False gives Previous / Next paging instead of page numbers.
register(
	"Request for Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "status", "name"},
	filters=("status",),
	paginate=True,
	count=False,
	date_field="transaction_date",
)
paginate_list_context("erpnext.buying.doctype.request_for_quotation.request_for_quotation", columns=COLUMNS)
