from sas_fortuna.overrides.portal_list import register

register(
	"Purchase Order",
	default="transaction_date desc",
	sort={"transaction_date", "schedule_date", "grand_total", "status", "name"},
	filters=("status",),
)
