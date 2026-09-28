from sas_fortuna.overrides.portal_list import paginate_list_context, register

register(
	"Delivery Note",
	default="posting_date desc",
	sort={"posting_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)
paginate_list_context("erpnext.stock.doctype.delivery_note.delivery_note")
