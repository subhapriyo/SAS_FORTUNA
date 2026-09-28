from sas_fortuna.overrides.portal_list import register

register(
	"Supplier Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "valid_till", "grand_total", "status", "name"},
	filters=("status",),
)
