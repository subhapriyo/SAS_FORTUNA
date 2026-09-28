from sas_fortuna.overrides.portal_list import register

register(
	"Request for Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "status", "name"},
	filters=("status",),
)
