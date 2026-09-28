from sas_fortuna.overrides.portal_list import register

register(
	"Issue",
	default="creation desc",
	sort={"creation", "modified", "priority", "status", "name"},
	filters=("status", "priority"),
)
