"""One module per portal list page: its table columns, sortable fields, paging and date field.

Importing a module registers its page with list_engine; portal/__init__.py imports them all.
To add a page: copy a module, adjust it, import it below and add the route's filter bar config
to public/js/portal.js (PAGES).
"""

from sas_fortuna.portal.lists import (
	delivery_note,
	gl_entry,  # /my-ledger
	issue,
	purchase_invoice,
	purchase_order,
	quotation,
	request_for_quotation,
	sales_invoice,
	sales_order,
	supplier_quotation,
)
