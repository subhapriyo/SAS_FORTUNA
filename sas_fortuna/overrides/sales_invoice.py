from sas_fortuna.overrides.portal_list import register

register(
	"Sales Invoice",
	default="posting_date desc",
	sort={"posting_date", "due_date", "grand_total", "outstanding_amount", "status", "name"},
	filters=("status",),
)
