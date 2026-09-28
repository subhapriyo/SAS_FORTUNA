from sas_fortuna.overrides.portal_list import register

register(
	"Delivery Note",
	default="posting_date desc",
	sort={"posting_date", "grand_total", "status", "name"},
	filters=("status",),
)
