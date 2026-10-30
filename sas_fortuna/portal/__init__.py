"""Customer / Supplier portal customisations layered on ERPNext's stock portal pages.

	list_engine.py    sorting, date-range filter and numbered paging for the list pages
	lists/            per-page configuration (columns, sortable fields, date field)
	detail_extras.py  extra header fields + item names for the detail pages (called by portal.js)

hooks.py runs apply_portal_overrides before every request.
"""

from sas_fortuna.portal import lists  # registers every list page
from sas_fortuna.portal.list_engine import apply as apply_portal_overrides

try:  # /repairs and /tickets lists (Support Desk, kept out of git until go-live; absent on a plain checkout)
	from sas_fortuna.support import portal_repairs, portal_tickets
except ImportError:
	pass
