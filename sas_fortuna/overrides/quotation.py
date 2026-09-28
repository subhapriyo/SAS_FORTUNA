from sas_fortuna.overrides.portal_list import register

register(
	"Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "grand_total", "status", "name"},
	filters=("status",),
)
