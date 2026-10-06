"""Customer portal /quotations (Quotation): sorting, paging and a custom row template.

Uses its own row template (sf_quotation_row.html, which adds the Customer Enquiry column) instead
of the generic table.
"""

from sas_fortuna.portal.list_engine import add_patch, is_active, register

ROW_TEMPLATE = "templates/includes/sf_quotation_row.html"

register(
	"Quotation",
	default="transaction_date desc",
	sort={"transaction_date", "grand_total", "status", "name"},
	paginate=True,
	date_field="transaction_date",
)


def _use_custom_row_template():
	from erpnext.selling.doctype.quotation import quotation as quotation_module

	original = quotation_module.get_list_context

	def get_list_context(context=None):
		list_context = original(context)
		if is_active():
			# ERPNext returns a plain dict here: item assignment, not attributes
			list_context["row_template"] = ROW_TEMPLATE
		return list_context

	quotation_module.get_list_context = get_list_context


add_patch(_use_custom_row_template)
