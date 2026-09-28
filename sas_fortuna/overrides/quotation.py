from sas_fortuna.overrides.portal_list import add_patch, register

ROW_TEMPLATE = "templates/includes/sf_quotation_row.html"

register(
	"Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
)


def _use_custom_row_template():
	from erpnext.selling.doctype.quotation import quotation as quotation_module

	original = quotation_module.get_list_context

	def get_list_context(context=None):
		list_context = original(context)
		list_context.row_template = ROW_TEMPLATE
		return list_context

	quotation_module.get_list_context = get_list_context


add_patch(_use_custom_row_template)
