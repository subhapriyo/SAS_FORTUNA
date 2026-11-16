"""Hooks for the Support Desk, Repair & AMC build, switched on phase by phase.

hooks.py reads doc_events / doctype_js / scheduler_events from here, so all
support hooks sit in one file, grouped by phase. Plain Python only: hooks.py
imports this module, so no frappe import at this level.

To switch a phase on: uncomment its lines, then
    bench --site fortuna.localhost clear-cache
and check with
    bench --site fortuna.localhost execute sas_fortuna.support.check_setup.run
"""

S = "sas_fortuna.support."

doctype_js = {
	"HD Ticket": "public/js/hd_ticket.js",  # Phase 3
	"Sales Order": "public/js/sales_order.js",  # Phase 6
}

doc_events = {
	# Phase 1: one customer identity in ERPNext and Helpdesk
	"Customer": {"after_insert": S + "customer_sync.customer_after_insert"},
	"Contact": {"validate": S + "customer_sync.contact_validate"},
	# Phase 2: ticket classification and routing; stamp serials on sale
	"HD Ticket": {
		"before_insert": S + "hd_ticket.before_insert",
		# Fortuna: "we've received your ticket" e-mail for portal tickets too
		"after_insert": S + "hd_ticket.after_insert",
		"validate": S + "hd_ticket.validate",
		"on_update": S + "hd_ticket.on_update",
	},
	"Sales Invoice": {
		"on_submit": [S + "sales.sales_invoice_on_submit", S + "repair.sales_invoice_on_submit"]
	},
	"Delivery Note": {
		# Fortuna: a paid repair ships only when paid in full
		"before_submit": [S + "repair.delivery_note_before_submit"],
		"on_submit": [S + "sales.delivery_note_on_submit", S + "repair.delivery_note_on_submit"],
	},
	# Phase 3: repair receipt
	"Stock Entry": {
		"on_submit": S + "repair.stock_entry_on_submit",
		"on_cancel": S + "repair.stock_entry_on_cancel",
	},
	# Phase 4: paid repair (Phase 6 adds amc.sales_order_validate and amc.payment_entry_on_submit)
	"Sales Order": {
		# Phase 6: copy Covered Items from the quotation, then check the AMC period and units
		"validate": [S + "amc.sales_order_validate", S + "amc.amc_validate"],
		"before_submit": S + "amc.amc_before_submit",
		"on_submit": S + "repair.sales_order_on_submit",
		"on_cancel": S + "repair.sales_order_on_cancel",
	},
	"Payment Entry": {
		"on_submit": [
			S + "repair.payment_entry_changed",
			S + "amc.payment_entry_on_submit",
		],  # Phase 6: activate AMC
		"on_cancel": S + "repair.payment_entry_changed",
	},
	# Phase 6: sales opportunities keep fortuna_erp's mandatory CRM fields; AMC enquiries don't
	"Opportunity": {"validate": S + "opportunity.validate"},
	# Phase 6: AMC quotation period and covered units
	"Quotation": {"validate": S + "amc.amc_validate", "before_submit": S + "amc.amc_before_submit"},
	# SIM dates on the unit
	"Serial No": {"validate": S + "sales.serial_no_validate"},
}

# Customer portal: /repairs is the Repair Order portal list (support/portal_repairs.py),
# /repairs/<name> the detail page (www/repair.py). /tickets the same for Helpdesk tickets
# (support/portal_tickets.py, www/ticket.py); it replaces the Support module's /issues.
website_route_rules = [
	{"from_route": "/tickets", "to_route": "HD Ticket"},
	{
		"from_route": "/tickets/<path:name>",
		"to_route": "ticket",
		"defaults": {"doctype": "HD Ticket", "parents": [{"label": "Tickets", "route": "tickets"}]},
	},
	{"from_route": "/repairs", "to_route": "Repair Order"},
	{
		"from_route": "/repairs/<path:name>",
		"to_route": "repair",
		"defaults": {"doctype": "Repair Order", "parents": [{"label": "Repairs", "route": "repairs"}]},
	},
]

scheduler_events = {
	# Phase 6: daily jobs
	"daily": [
		S + "tasks.send_amc_enquiries",
		S + "tasks.mark_overdue_gate_passes",
		S + "tasks.create_sim_recharge_orders",
		S + "tasks.send_sim_renewal_reminders",  # Fortuna: customer e-mail 30 / 15 days before
	],
}
