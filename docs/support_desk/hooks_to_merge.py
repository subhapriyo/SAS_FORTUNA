# =============================================================================
# SUPPORT DESK, REPAIR & AMC  —  additions for sas_fortuna/hooks.py
# =============================================================================
# NOT imported by Frappe. Copy each block into hooks.py WHEN ITS PHASE STARTS:
# the hooks call DocTypes / fields / settings that must exist first, otherwise
# every HD Ticket, Sales Invoice or Delivery Note save will fail.
#
#   Block A (lists + fixtures) ........ any time (only affects export-fixtures)
#   Block B (doc_events, doctype_js) .. add each line in the phase noted
#   Block C (scheduler_events) ........ Phase 6, after Fortuna Support Settings
#                                       is filled and the custom fields exist
# =============================================================================


# -----------------------------------------------------------------------------
# Block A1 — extend the existing lists at the top of hooks.py
# -----------------------------------------------------------------------------
# CUSTOM_WORKFLOWS: add
# "Repair Order Flow",
#
# CUSTOM_WORKFLOW_STATES: add
# "Registered", "Unit Received", "Awaiting Payment", "In Repair",
# "Ready", "Dispatched", "Closed", "Cancelled",

# New lists (paste below CUSTOM_WEB_FORMS):

SUPPORT_DESK_MODULE = "SAS Fortuna"

SUPPORT_DESK_WORKFLOW_ACTIONS = [
	"Send Quotation",
	"Start Repair",
	"End Repair",
	"Close",
	"Cancel",
]

SUPPORT_DESK_NOTIFICATIONS = [
	"Fortuna Unit Received",
	"Fortuna Receipt Confirmed",
	"Fortuna Repair Quotation",
	"Fortuna Repair Dispatched",
	"Fortuna Loaner Overdue",
	"Fortuna AMC Renewal Due",
]

# Explicit names, not "Fortuna%": fortuna_erp already has print formats such as
# "Fortuna - AMC Invoice" that must stay owned by fortuna_erp.
SUPPORT_DESK_PRINT_FORMATS = [
	"Fortuna Job Sheet",
	"Fortuna Repair Quotation",
	"Fortuna Proforma Invoice",
	"Fortuna Installation Certificate",
	"Fortuna Warranty Terms",
	"Fortuna Installed Items",
	"Fortuna AMC Agreement",
	"Fortuna AMC Invoice",
	"Fortuna Gate Pass",
	"Fortuna Delivery Challan",
]

SUPPORT_DESK_ROLES = ["Service Engineer", "AMC Team", "Support Manager"]
SUPPORT_DESK_TICKET_TYPES = ["Software", "Hardware", "Post-Installation"]
SUPPORT_DESK_STOCK_ENTRY_TYPES = ["Repair Receipt"]


# -----------------------------------------------------------------------------
# Block A2 — fixtures
# -----------------------------------------------------------------------------
# 1) In the EXISTING "Custom Field" entry, add ONE line to or_filters
#    (keep a single Custom Field entry, as the comment in hooks.py says):
#
# {
# "dt": "Custom Field",
# "or_filters": [
# ["dt", "in", CUSTOMIZED_DOCTYPES],
# ["name", "in", PORTAL_ONBOARDING_CUSTOM_FIELDS],
# ["module", "=", SUPPORT_DESK_MODULE],        # <-- add
# ],
# },
#
# 2) Change the EXISTING "Property Setter" entry to:
#
# {
# "dt": "Property Setter",
# "or_filters": [
# ["doc_type", "in", CUSTOMIZED_DOCTYPES],
# ["module", "=", SUPPORT_DESK_MODULE],        # <-- add
# ],
# },
#
# 3) Append these NEW entries at the end of the fixtures list:

SUPPORT_DESK_FIXTURES = [
	{"dt": "Workflow Action Master", "filters": [["name", "in", SUPPORT_DESK_WORKFLOW_ACTIONS]]},
	{"dt": "Notification", "filters": [["name", "in", SUPPORT_DESK_NOTIFICATIONS]]},
	{"dt": "Print Format", "filters": [["name", "in", SUPPORT_DESK_PRINT_FORMATS]]},
	{"dt": "Role", "filters": [["name", "in", SUPPORT_DESK_ROLES]]},
	{"dt": "HD Ticket Type", "filters": [["name", "in", SUPPORT_DESK_TICKET_TYPES]]},
	{"dt": "Stock Entry Type", "filters": [["name", "in", SUPPORT_DESK_STOCK_ENTRY_TYPES]]},
]
# e.g.  fixtures = [ ...existing entries..., *SUPPORT_DESK_FIXTURES ]


# -----------------------------------------------------------------------------
# Block B — form scripts and document events (add per phase)
# -----------------------------------------------------------------------------
doctype_js = {
	"HD Ticket": "public/js/hd_ticket.js",  # Phase 3 (needs Repair Order)
	"Sales Order": "public/js/sales_order.js",  # Phase 6
}

doc_events = {
	# Phase 1 — after the custom field HD Customer.custom_erpnext_customer exists
	"Customer": {
		"after_insert": "sas_fortuna.support.customer_sync.customer_after_insert",
	},
	"Contact": {
		"validate": "sas_fortuna.support.customer_sync.contact_validate",
	},
	# Phase 2 — after Fortuna Support Settings + Serial No / HD Ticket custom fields
	"HD Ticket": {
		"validate": "sas_fortuna.support.hd_ticket.validate",
		"on_update": "sas_fortuna.support.hd_ticket.on_update",
	},
	"Sales Invoice": {
		"on_submit": [
			"sas_fortuna.support.sales.sales_invoice_on_submit",  # Phase 2: stamp serials
			"sas_fortuna.support.repair.sales_invoice_on_submit",  # Phase 4: link repair bill
		],
	},
	"Delivery Note": {
		"on_submit": [
			"sas_fortuna.support.sales.delivery_note_on_submit",  # Phase 2
			"sas_fortuna.support.repair.delivery_note_on_submit",  # Phase 5
		],
	},
	# Phase 3 — after the Repair Order DocType + Stock Entry custom fields
	"Stock Entry": {
		"on_submit": "sas_fortuna.support.repair.stock_entry_on_submit",
		"on_cancel": "sas_fortuna.support.repair.stock_entry_on_cancel",
	},
	# Phase 4 / 6
	"Sales Order": {
		"validate": "sas_fortuna.support.amc.sales_order_validate",  # Phase 6
		"on_submit": "sas_fortuna.support.repair.sales_order_on_submit",  # Phase 4
		"on_cancel": "sas_fortuna.support.repair.sales_order_on_cancel",  # Phase 4
	},
	"Payment Entry": {
		"on_submit": [
			"sas_fortuna.support.repair.payment_entry_changed",  # Phase 4: N7 gate
			"sas_fortuna.support.amc.payment_entry_on_submit",  # Phase 6: F5
		],
		"on_cancel": "sas_fortuna.support.repair.payment_entry_changed",  # Phase 4
	},
}


# -----------------------------------------------------------------------------
# Block C — daily jobs (Phase 6)
# -----------------------------------------------------------------------------
scheduler_events = {
	"daily": [
		"sas_fortuna.support.tasks.send_amc_enquiries",  # F1
		"sas_fortuna.support.tasks.mark_overdue_gate_passes",  # N2
		"sas_fortuna.support.tasks.create_sim_recharge_orders",  # N10
	],
}
