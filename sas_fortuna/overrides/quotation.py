from sas_fortuna.overrides.portal_list import add_patch, register

ROW_TEMPLATE = "templates/includes/sf_quotation_row.html"

register(
	"Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "grand_total", "status", "name"},
	filters=("status",),
	paginate=True,
	date_field="transaction_date",
)


def _use_custom_row_template():
	from erpnext.selling.doctype.quotation import quotation as quotation_module

	original = quotation_module.get_list_context

	def get_list_context(context=None):
		list_context = original(context)
		# ERPNext returns a plain dict here; attribute assignment raised AttributeError -> HTTP 500
		list_context["row_template"] = ROW_TEMPLATE
		return list_context

	quotation_module.get_list_context = get_list_context


add_patch(_use_custom_row_template)
