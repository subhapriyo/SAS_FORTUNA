"""after_migrate: create what the Support Desk, Repair & AMC build needs on every site.

Runs on every `bench migrate` and only ADDS what is missing, so it is safe to
re-run and never overwrites changes made later in Customize Form or Role
Permissions Manager:

  1. Roles ............... Service Engineer, AMC Team, Support Manager
  2. Stock Entry Type .... Repair Receipt (Material Receipt)
  3. Custom Fields ....... Serial No, HD Ticket, HD Customer, Stock Entry, Material
                           Request, Quotation, Sales Order, Sales Invoice, Delivery
                           Note, Opportunity
  4. Permissions ......... custom roles + Helpdesk "Agent" on the new DocTypes
  5. Report roles ........ the same roles on the four Query Reports
  6. Landing page ........ LANDING_SECTIONS, shown on /desk/sas-fortuna by setup/landing_page.py
  7. Portal menu ......... Tickets + Repairs in the customer portal; Issues switched off once
  8. Helpdesk role ....... "HD Customer" for portal users (New ticket / Reply on /tickets)
  9. New ticket form ..... Ticket Type + Serial No on Helpdesk's customer form (Default template)
 10. Ticketing ........... setup/ticketing.py ensure(): Ticket Types, Paused status, Teams,
                           Team Routing (once per site) and missing HD Customers. Runs last.

The new DocTypes themselves (Repair Order, Returnable Gate Pass, ...) are app
files under sas_fortuna/sas_fortuna/doctype and are synced by migrate before
this runs. Because this script owns these Custom Fields, do NOT also export
them as fixtures.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from sas_fortuna.setup import ticketing
from sas_fortuna.setup.ticketing import TEAM_ROUTES, TICKET_TYPES

MODULE = "SAS Fortuna"

ROLES = ["Service Engineer", "AMC Team", "Support Manager"]

STOCK_ENTRY_TYPES = {"Repair Receipt": "Material Receipt"}


def execute():
	_create_roles()
	_create_stock_entry_types()
	_create_custom_fields()
	_add_permissions()
	_add_report_roles()
	_relax_opportunity_for_amc()
	_portal_menu()
	_helpdesk_role_for_portal_users()
	_helpdesk_ticket_form()
	# Last: needs the custom fields and the New ticket form above.
	ticketing.ensure()


# ---------------------------------------------------------------------------
# 7-8. Customer portal: menu entries and Helpdesk access
# ---------------------------------------------------------------------------

# Customer portal sidebar entries (Portal Settings > Custom Menu), in this order, right under the
# standard links. A missing entry is created at its place; an existing one is fixed in place, so an
# admin's position / enabled choice is kept. When Tickets is first added, the standard "Issues" link
# (ERPNext Support module, being phased out) is switched off: Tickets replaces it. An admin can switch
# Issues back on later; this does not undo that.
PORTAL_MENU = [
	{"title": "Tickets", "route": "/tickets", "reference_doctype": "HD Ticket", "role": "Customer"},
	{"title": "Repairs", "route": "/repairs", "reference_doctype": "Repair Order", "role": "Customer"},
]


def _portal_menu():
	settings = frappe.get_single("Portal Settings")
	changed = False
	for pos, item in enumerate(PORTAL_MENU):
		row = next((r for r in settings.custom_menu if r.title == item["title"]), None)
		if not row:
			settings.append("custom_menu", {**item, "enabled": 1})
			settings.custom_menu.insert(pos, settings.custom_menu.pop())
			if item["title"] == "Tickets":
				for std in settings.menu:
					if std.route == "/issues":
						std.enabled = 0
			changed = True
		elif any(row.get(k) != v for k, v in item.items()):
			row.update(item)
			changed = True
	if changed:
		for i, r in enumerate(settings.custom_menu, 1):
			r.idx = i  # keep the row order we just set
		settings.save(ignore_permissions=True)


# Fields added to Helpdesk's "Default" ticket template, i.e. the customer's New ticket form.
# Without them a portal ticket has no type (so no team, no agent) and no serial (so no warranty
# check). url_method: where the field's choices come from (support/portal.py).
TICKET_FORM_FIELDS = [
	{
		"fieldname": "ticket_type",
		"required": 1,
		"url_method": "sas_fortuna.support.portal.customer_ticket_types",
		"placeholder": "Software, Hardware or Post-Installation",
	},
	{
		# Optional: a Helpdesk agent can add or correct it on the ticket later.
		"fieldname": "custom_serial_no",
		"required": 0,
		"url_method": "sas_fortuna.support.portal.customer_serials",
		"placeholder": "Serial No (optional)",
	},
]


def _helpdesk_ticket_form():
	"""Add TICKET_FORM_FIELDS to the Default ticket template, once. Rows are matched by fieldname;
	an admin's later edits to them (required, placeholder, order) are kept."""
	if not frappe.db.exists("HD Ticket Template", "Default"):
		return
	template = frappe.get_doc("HD Ticket Template", "Default")
	have = {row.fieldname for row in template.fields}
	missing = [f for f in TICKET_FORM_FIELDS if f["fieldname"] not in have]
	if not missing:
		return
	for field in missing:
		template.append("fields", field)
	template.save(ignore_permissions=True)


def _helpdesk_role_for_portal_users():
	"""Existing portal users get Helpdesk's customer role, so New ticket / Reply on /tickets work.
	New ones get it when their Contact is saved (customer_sync.contact_validate)."""
	from sas_fortuna.support.customer_sync import grant_helpdesk_role_to_portal_users

	grant_helpdesk_role_to_portal_users()


# ---------------------------------------------------------------------------
# 1-2. Master records
# ---------------------------------------------------------------------------
def _create_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def _create_stock_entry_types():
	for name, purpose in STOCK_ENTRY_TYPES.items():
		if not frappe.db.exists("Stock Entry Type", name):
			frappe.get_doc({"doctype": "Stock Entry Type", "name": name, "purpose": purpose}).insert(
				ignore_permissions=True
			)


# ---------------------------------------------------------------------------
# 3. Custom fields
# ---------------------------------------------------------------------------
def _chain(fields, after=None):
	"""Place fields one after another (first one after `after`, or at the end)."""
	for df in fields:
		if after:
			df.setdefault("insert_after", after)
		df.setdefault("module", MODULE)
		after = df["fieldname"]
	return fields


def _ro(**kw):
	return {"read_only": 1, **kw}


SERIAL_NO_FIELDS = _chain(
	[
		{"fieldname": "custom_support_tab", "fieldtype": "Tab Break", "label": "Support & AMC"},
		{"fieldname": "custom_sale_section", "fieldtype": "Section Break", "label": "Sale & Warranty"},
		_ro(fieldname="custom_invoice_no", fieldtype="Link", label="Invoice No", options="Sales Invoice"),
		_ro(fieldname="custom_invoice_date", fieldtype="Date", label="Invoice Date"),
		_ro(
			fieldname="custom_sold_to",
			fieldtype="Link",
			label="Sold To",
			options="Customer",
			in_standard_filter=1,
		),
		{"fieldname": "custom_sale_cb", "fieldtype": "Column Break"},
		_ro(
			fieldname="custom_warranty_end",
			fieldtype="Date",
			label="Warranty End (from invoice)",
			in_standard_filter=1,
		),
		_ro(
			fieldname="custom_replaces_serial", fieldtype="Link", label="Replaces Serial", options="Serial No"
		),
		{"fieldname": "custom_software_version", "fieldtype": "Data", "label": "Software Version"},
		_ro(fieldname="custom_last_service_date", fieldtype="Date", label="Last Service Date"),
		{"fieldname": "custom_amc_section", "fieldtype": "Section Break", "label": "AMC"},
		_ro(fieldname="custom_amc_start_date", fieldtype="Date", label="AMC Start Date"),
		_ro(fieldname="custom_amc_contract", fieldtype="Link", label="AMC Contract", options="Sales Order"),
		{"fieldname": "custom_amc_cb", "fieldtype": "Column Break"},
		_ro(
			fieldname="custom_amc_status",
			fieldtype="Select",
			label="AMC Status",
			options="\nActive\nRenewal Quoted\nEnded",
			in_standard_filter=1,
		),
		_ro(fieldname="custom_amc_enquiry_sent", fieldtype="Check", label="AMC Enquiry Sent"),
		{"fieldname": "custom_sim_section", "fieldtype": "Section Break", "label": "SIM"},
		{"fieldname": "custom_sim_no", "fieldtype": "Data", "label": "SIM No"},
		{"fieldname": "custom_sim_operator", "fieldtype": "Data", "label": "SIM Operator"},
		{"fieldname": "custom_sim_cb", "fieldtype": "Column Break"},
		{"fieldname": "custom_sim_activation_date", "fieldtype": "Date", "label": "SIM Activation Date"},
		{"fieldname": "custom_sim_valid_till", "fieldtype": "Date", "label": "SIM Valid Till"},
		_ro(fieldname="custom_sim_order", fieldtype="Link", label="SIM Service Order", options="Sales Order"),
	]
)

HD_TICKET_FIELDS = _chain(
	[
		{"fieldname": "custom_product_tab", "fieldtype": "Tab Break", "label": "Product & Warranty"},
		{
			"fieldname": "custom_product_model",
			"fieldtype": "Link",
			"label": "Product Model",
			"options": "Item",
			"link_filters": '[["Item","has_serial_no","=",1]]',
		},
		{"fieldname": "custom_serial_no", "fieldtype": "Link", "label": "Serial No", "options": "Serial No"},
		{
			"fieldname": "custom_contact_mobile",
			"fieldtype": "Data",
			"label": "Contact Mobile",
			"options": "Phone",
		},
		{"fieldname": "custom_remarks", "fieldtype": "Small Text", "label": "Remarks"},
		{"fieldname": "custom_product_cb", "fieldtype": "Column Break"},
		_ro(
			fieldname="custom_support_type",
			fieldtype="Select",
			label="Support Type",
			options="\nWarranty\nAMC\nPaid Service",
			in_standard_filter=1,
		),
		_ro(
			fieldname="custom_erpnext_customer",
			fieldtype="Link",
			label="ERPNext Customer",
			options="Customer",
		),
		_ro(fieldname="custom_invoice_no", fieldtype="Data", label="Invoice No"),
		_ro(fieldname="custom_invoice_date", fieldtype="Date", label="Invoice Date"),
		_ro(fieldname="custom_warranty_end", fieldtype="Date", label="Warranty End"),
		_ro(fieldname="custom_amc_expiry", fieldtype="Date", label="AMC Expiry"),
		{"fieldname": "custom_links_section", "fieldtype": "Section Break", "label": "Linked Documents"},
		_ro(fieldname="custom_sales_order", fieldtype="Link", label="Sales Order", options="Sales Order"),
		_ro(fieldname="custom_repair_order", fieldtype="Link", label="Repair Order", options="Repair Order"),
		_ro(fieldname="custom_repair_status", fieldtype="Data", label="Repair Status"),
		# Tickets imported from Fortuna's old system (support/legacy_import.py). Shown only on them.
		{
			"fieldname": "custom_legacy_section",
			"fieldtype": "Section Break",
			"label": "Legacy (Old System)",
			"collapsible": 1,
			"depends_on": "eval:doc.custom_is_legacy",
		},
		{
			"fieldname": "custom_is_legacy",
			"fieldtype": "Check",
			"label": "Is Legacy",
			"read_only": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "custom_legacy_ticket_no",
			"fieldtype": "Data",
			"label": "Legacy Ticket No",
			"unique": 1,
			"in_standard_filter": 1,
			"in_global_search": 1,
			"search_index": 1,
		},
		{"fieldname": "custom_legacy_source", "fieldtype": "Data", "label": "Legacy Source"},
		{"fieldname": "custom_legacy_engineer", "fieldtype": "Data", "label": "Legacy Engineer"},
		{"fieldname": "custom_legacy_cb", "fieldtype": "Column Break"},
		{"fieldname": "custom_legacy_opened_on", "fieldtype": "Datetime", "label": "Legacy Opened On"},
		{"fieldname": "custom_legacy_closed_on", "fieldtype": "Datetime", "label": "Legacy Closed On"},
		{
			"fieldname": "custom_legacy_serial_no",
			"fieldtype": "Data",
			"label": "Legacy Serial No",
			"in_global_search": 1,
		},
	]
)

# Same fieldnames on Quotation and Sales Order, so "Make Sales Order" copies them.
SERVICE_TAB_FIELDS = [
	{"fieldname": "custom_service_tab", "fieldtype": "Tab Break", "label": "Service / AMC"},
	_ro(fieldname="custom_repair_order", fieldtype="Link", label="Repair Order", options="Repair Order"),
	{"fieldname": "custom_is_amc", "fieldtype": "Check", "label": "Is AMC"},
	{
		"fieldname": "custom_amc_section",
		"fieldtype": "Section Break",
		"label": "AMC Details",
		"depends_on": "eval:doc.custom_is_amc",
	},
	{
		"fieldname": "custom_amc_start_date",
		"fieldtype": "Date",
		"label": "AMC Start Date",
		"mandatory_depends_on": "eval:doc.custom_is_amc",
	},
	{
		"fieldname": "custom_amc_end_date",
		"fieldtype": "Date",
		"label": "AMC End Date",
		"mandatory_depends_on": "eval:doc.custom_is_amc",
	},
	{
		"fieldname": "custom_coverage",
		"fieldtype": "Select",
		"label": "Coverage",
		"options": "\nComprehensive\nNon-Comprehensive\nLabour Only",
	},
	{
		"fieldname": "custom_support_mode",
		"fieldtype": "Select",
		"label": "Support Mode",
		"options": "\nOn-site\nRemote\nCarry-in",
	},
	{"fieldname": "custom_amc_cb", "fieldtype": "Column Break"},
	{"fieldname": "custom_software_version", "fieldtype": "Data", "label": "Software Version"},
	{"fieldname": "custom_end_customer", "fieldtype": "Data", "label": "End Customer"},
	_ro(fieldname="custom_renewal_of", fieldtype="Link", label="Renewal Of", options="Sales Order"),
	{
		"fieldname": "custom_covered_items_section",
		"fieldtype": "Section Break",
		"label": "Covered Items",
		"depends_on": "eval:doc.custom_is_amc",
	},
	{
		"fieldname": "custom_covered_items",
		"fieldtype": "Table",
		"label": "Covered Items",
		"options": "AMC Covered Item",
	},
]


def _service_tab(extra=()):
	"""Fresh copies per DocType (create_custom_fields mutates the dicts)."""
	fields = [dict(df) for df in SERVICE_TAB_FIELDS]
	for df in extra:
		pos = next(i for i, f in enumerate(fields) if f["fieldname"] == df["after"]) + 1
		fields.insert(pos, {k: v for k, v in df.items() if k != "after"})
	return _chain(fields)


CUSTOM_FIELDS = {
	"Serial No": SERIAL_NO_FIELDS,
	"HD Ticket": HD_TICKET_FIELDS,
	"HD Customer": _chain(
		[
			{
				"fieldname": "custom_erpnext_customer",
				"fieldtype": "Link",
				"label": "ERPNext Customer",
				"options": "Customer",
				"unique": 1,
			}
		]
	),
	"Stock Entry": _chain(
		[
			_ro(
				fieldname="custom_repair_order",
				fieldtype="Link",
				label="Repair Order",
				options="Repair Order",
			),
			_ro(
				fieldname="custom_help_desk_owner",
				fieldtype="Link",
				label="Help Desk Owner",
				options="User",
				fetch_from="custom_repair_order.help_desk_owner",
				hidden=1,
			),
		],
		after="stock_entry_type",
	),
	"Stock Entry Detail": _chain(
		[_ro(fieldname="custom_repair_order_part", fieldtype="Data", label="Repair Order Part", hidden=1)]
	),
	"Material Request": _chain(
		[
			_ro(
				fieldname="custom_repair_order",
				fieldtype="Link",
				label="Repair Order",
				options="Repair Order",
			)
		],
		after="material_request_type",
	),
	"Sales Invoice": _chain(
		[_ro(fieldname="custom_repair_order", fieldtype="Link", label="Repair Order", options="Repair Order")]
	),
	"Delivery Note": _chain(
		[
			_ro(
				fieldname="custom_repair_order",
				fieldtype="Link",
				label="Repair Order",
				options="Repair Order",
			),
			_ro(
				fieldname="custom_replaces_serial",
				fieldtype="Link",
				label="Replaces Serial",
				options="Serial No",
			),
		]
	),
	"Opportunity": _chain(
		[{"fieldname": "custom_serial_no", "fieldtype": "Link", "label": "Serial No", "options": "Serial No"}]
	),
	"Quotation": _service_tab(),
	"Sales Order": _service_tab(
		extra=[
			_ro(
				after="custom_renewal_of",
				fieldname="custom_amc_status",
				fieldtype="Select",
				label="AMC Status",
				options="\nActive\nRenewal Quoted\nEnded",
				allow_on_submit=1,
				in_standard_filter=1,
			)
		]
	),
}


def _create_custom_fields():
	# Skip DocTypes of apps that are not installed (e.g. Helpdesk on a test site).
	present = {dt: fields for dt, fields in CUSTOM_FIELDS.items() if frappe.db.exists("DocType", dt)}
	# update=False: only missing fields are created; edits made later are kept.
	create_custom_fields(present, update=False)


# ---------------------------------------------------------------------------
# 4. Permissions for roles that are not standard ERPNext roles
# ---------------------------------------------------------------------------
# DocType JSON only lists standard ERPNext roles (they always exist when the
# DocTypes sync). The roles below are added here as Custom DocPerms, once.
PERMISSIONS = {
	"Fortuna Support Settings": {"Support Manager": ["read", "write"]},
	"Repair Order": {
		"Agent": ["read", "write", "create", "print", "email", "report"],
		"Service Engineer": ["read", "write", "print", "report"],
		"Support Manager": ["read", "write", "create", "delete", "print", "email", "report", "export"],
		"AMC Team": ["read", "report"],
	},
	# AMC team and managers look units up (warranty, AMC dates) without needing Stock User.
	"Serial No": {
		"AMC Team": ["read", "report", "print"],
		"Support Manager": ["read", "report", "print", "export"],
	},
	"Returnable Gate Pass": {
		"Agent": ["read", "write", "create", "print"],
		"Service Engineer": ["read", "write", "create", "submit", "print"],
		"Support Manager": ["read", "write", "create", "submit", "cancel", "amend", "print", "report"],
	},
}


def _add_permissions():
	from frappe.permissions import add_permission, update_permission_property

	for doctype, roles in PERMISSIONS.items():
		for role, ptypes in roles.items():
			if not frappe.db.exists("Role", role):
				continue  # e.g. "Agent" when Helpdesk is not installed
			if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				continue  # already set (or changed by hand): leave it alone
			try:
				add_permission(doctype, role, 0)
				for ptype in ptypes:
					update_permission_property(doctype, role, 0, ptype, 1)
			except Exception:
				# Never block a migrate over a permission row; set it by hand instead.
				frappe.log_error(title=f"sas_fortuna: permission {doctype} / {role} not set")


# ---------------------------------------------------------------------------
# 5. Report access for the same non-standard roles
# ---------------------------------------------------------------------------
REPORT_ROLES = {
	"Returnable Items Outstanding": ["Agent", "Support Manager"],
	"Serial Service History": ["Agent", "Support Manager", "AMC Team"],
	"SIM Recharge Due": ["Support Manager"],
	"Warranty Ending": ["AMC Team", "Support Manager"],
}


def _add_report_roles():
	for report, roles in REPORT_ROLES.items():
		if not frappe.db.exists("Report", report):
			continue
		doc = frappe.get_doc("Report", report)
		have = {row.role for row in doc.roles}
		missing = [r for r in roles if r not in have and frappe.db.exists("Role", r)]
		if not missing:
			continue
		for role in missing:
			doc.append("roles", {"role": role})
		# Standard reports can only be saved in developer mode, so insert just the new rows.
		for row in doc.roles:
			if row.role in missing:
				row.db_insert()


# ---------------------------------------------------------------------------
# 5b. Opportunity: fortuna_erp's CRM fields stay mandatory for sales, not for
#     AMC enquiries made by the daily job (see support/opportunity.py).
# ---------------------------------------------------------------------------
def _relax_opportunity_for_amc():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	from sas_fortuna.support.opportunity import QUALIFICATION_FIELDS, SALES_ONLY

	if not frappe.db.exists("DocType", "Opportunity"):
		return
	meta = frappe.get_meta("Opportunity")
	if not meta.has_field("custom_serial_no"):
		return
	for field in QUALIFICATION_FIELDS:
		if not meta.has_field(field):
			continue  # fortuna_erp field not on this site
		make_property_setter("Opportunity", field, "reqd", "0", "Check", validate_fields_for_doctype=False)
		make_property_setter(
			"Opportunity",
			field,
			"mandatory_depends_on",
			SALES_ONLY,
			"Code",
			validate_fields_for_doctype=False,
		)
	frappe.clear_cache(doctype="Opportunity")


# ---------------------------------------------------------------------------
# 6. Landing page sections
# ---------------------------------------------------------------------------
# Read by setup/landing_page.py, which builds /desk/sas-fortuna. Kept here,
# next to the rest of the support setup, so support links change in one place.
# Each link: (label, kind, target, one-line description, icon)
LANDING_SECTIONS = [
	{
		"title": "Support Desk, Repair & AMC",
		"intro": "Repairs, loaners and the settings behind them.",
		"links": [
			("Repair Order", "doctype", "Repair Order", "Track a unit from receipt to dispatch.", "wrench"),
			(
				"Returnable Gate Pass",
				"doctype",
				"Returnable Gate Pass",
				"Loaners out with customers, and their return.",
				"pass",
			),
			(
				"Fortuna Support Settings",
				"doctype",
				"Fortuna Support Settings",
				"Warehouses, accounts and switches for repairs.",
				"settings",
			),
			("Helpdesk", "url", "/helpdesk", "Where agents pick up and answer tickets.", "headset"),
		],
	},
	{
		"title": "Support Reports",
		"intro": "Quick answers for follow-ups and audits.",
		"links": [
			(
				"Warranty Ending",
				"report",
				"Warranty Ending",
				"Warranties ending soon, for AMC follow-up.",
				"report",
			),
			(
				"Serial Service History",
				"report",
				"Serial Service History",
				"Every ticket and repair for one serial.",
				"report",
			),
			(
				"Returnable Items Outstanding",
				"report",
				"Returnable Items Outstanding",
				"Loaners that are not back yet.",
				"report",
			),
			("SIM Recharge Due", "report", "SIM Recharge Due", "SIMs that need a recharge soon.", "report"),
		],
	},
]


# ---------------------------------------------------------------------------
# 7. Phase 0-1 masters: run ONCE per site, by hand (not on every migrate)
#    bench --site <site> execute sas_fortuna.setup.support_desk.create_masters
# ---------------------------------------------------------------------------
# Site data, not app config: an account, service items, Helpdesk ticket types,
# the Paused status and two teams. Each is created only if missing and then
# linked in Fortuna Support Settings, so re-running changes nothing.
# SAC codes are placeholders until Fortuna's accountant confirms them.
SERVICE_ITEMS = {
	# settings field: (item code, SAC)
	"service_charge_item": ("Repair Service Charge", "998713"),
	"freight_item": ("Freight Charges", "996511"),
	"sim_recharge_item": ("SIM Recharge", "998422"),
	None: ("AMC Service", "998713"),  # used on AMC quotations, not in settings
}
# TICKET_TYPES and TEAM_ROUTES: see setup/ticketing.py


def create_masters():
	settings = frappe.get_single("Fortuna Support Settings")
	company = settings.company
	if not company:
		frappe.throw("Set Company in Fortuna Support Settings first.")
	done = []

	# Account: Warranty Expense under Indirect Expenses
	abbr = frappe.db.get_value("Company", company, "abbr")
	account = f"Warranty Expense - {abbr}"
	if not frappe.db.exists("Account", account):
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Warranty Expense",
				"parent_account": f"Indirect Expenses - {abbr}",
				"company": company,
				"is_group": 0,
			}
		).insert()
		done.append(account)
	settings.warranty_expense_account = settings.warranty_expense_account or account

	# Non-stock service items
	for field, (code, sac) in SERVICE_ITEMS.items():
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": "Services",
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"gst_hsn_code": sac,
				}
			).insert()
			done.append(f"Item {code}")
		# fortuna_erp keeps every Item disabled until its Status is "Approved"
		# (customisations/item.py). Disabled items cannot go on a quotation,
		# so approve ours. On production Fortuna's approver may do this instead.
		item = frappe.get_doc("Item", code)
		if item.meta.has_field("custom_status") and item.custom_status != "Approved":
			item.custom_status = "Approved"
			item.save()
			done.append(f"Approved item {code}")
		if field and not settings.get(field):
			settings.set(field, code)

	# Helpdesk ticket types, Paused status, teams (shared with migrate)
	done += ticketing.create_masters()

	# Routing rows in settings
	have = {row.ticket_type for row in settings.team_routing}
	for ticket_type, team in TEAM_ROUTES.items():
		if ticket_type not in have:
			settings.append("team_routing", {"ticket_type": ticket_type, "team": team})

	settings.save()
	done += _create_repair_workflow()
	done += _create_receipt_notification()
	done += _create_repair_board()
	done += _create_renewal_notification()
	# Phase 9: print formats (updates them in place when re-run)
	from sas_fortuna.support.print_formats import create_print_formats

	done += create_print_formats()
	frappe.db.commit()
	return {"created": done or "nothing new"}


# Phase 3 (D6): Repair Order status flow. Only HUMAN actions are transitions;
# Registered -> Unit Received and Ready -> Dispatched are set by the system
# when the Repair Receipt / Delivery Note is submitted (repair.set_repair_status).
WORKFLOW = "Repair Order Flow"
WORKFLOW_STATES = [
	# (state, role allowed to edit in this state, style)
	("Registered", "Agent", "Primary"),
	("Unit Received", "Agent", "Info"),
	("Awaiting Payment", "Agent", "Warning"),
	("In Repair", "Service Engineer", "Primary"),
	("Ready", "Service Engineer", "Success"),
	("Dispatched", "Stock User", "Success"),
	("Closed", "Support Manager", "Inverse"),
	("Cancelled", "Support Manager", "Danger"),
]
WORKFLOW_TRANSITIONS = [
	# (from, action, to, role, condition)
	(
		"Unit Received",
		"Send Quotation",
		"Awaiting Payment",
		"Agent",
		'doc.invoice_method == "Chargeable" and doc.quotation',
	),
	("Unit Received", "Start Repair", "In Repair", "Service Engineer", 'doc.invoice_method != "Chargeable"'),
	("Awaiting Payment", "Start Repair", "In Repair", "Service Engineer", "doc.payment_cleared == 1"),
	("In Repair", "End Repair", "Ready", "Service Engineer", ""),
	("Dispatched", "Close", "Closed", "Agent", ""),
	("Registered", "Cancel", "Cancelled", "Support Manager", ""),
	("Unit Received", "Cancel", "Cancelled", "Support Manager", ""),
	("Awaiting Payment", "Cancel", "Cancelled", "Support Manager", ""),
]


def _create_repair_workflow():
	if frappe.db.exists("Workflow", WORKFLOW):
		return []
	for state, _role, style in WORKFLOW_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert()
	for action in {t[1] for t in WORKFLOW_TRANSITIONS}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert()
	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW,
			"document_type": "Repair Order",
			"workflow_state_field": "status",
			"is_active": 1,
			"send_email_alert": 0,
			"states": [
				{"state": s, "doc_status": "0", "allow_edit": role} for s, role, _style in WORKFLOW_STATES
			],
			"transitions": [
				{
					"state": f,
					"action": a,
					"next_state": t,
					"allowed": role,
					"condition": cond,
					"allow_self_approval": 1,
				}
				for f, a, t, role, cond in WORKFLOW_TRANSITIONS
			],
		}
	).insert()
	return [f"Workflow {WORKFLOW}"]


# Phase 3 (N3): tell the help desk owner when the customer's unit arrives.
def _create_receipt_notification():
	name = "Fortuna Unit Received"
	if frappe.db.exists("Notification", name):
		return []
	frappe.get_doc(
		{
			"doctype": "Notification",
			"name": name,
			"subject": "Unit received for {{ doc.custom_repair_order }}",
			"document_type": "Stock Entry",
			"event": "Submit",
			"channel": "Email",
			"condition": 'doc.stock_entry_type == "Repair Receipt" and doc.custom_repair_order',
			"recipients": [{"receiver_by_document_field": "custom_help_desk_owner"}],
			"message": (
				"<p>The unit for repair order <b>{{ doc.custom_repair_order }}</b> has been received "
				"into stores ({{ doc.name }}, {{ frappe.format_date(doc.posting_date) }}).</p>"
				"<p>Please confirm receipt to the customer and move the repair forward.</p>"
			),
			"enabled": 1,
		}
	).insert()
	return [f"Notification {name}"]


# Phase 6 (F8): remind the AMC team 30 days before an active AMC expires.
def _create_renewal_notification():
	name = "Fortuna AMC Renewal Due"
	if frappe.db.exists("Notification", name):
		return []
	frappe.get_doc(
		{
			"doctype": "Notification",
			"name": name,
			"subject": "AMC renewal due: {{ doc.name }}",
			"document_type": "Serial No",
			"event": "Days Before",
			"date_changed": "amc_expiry_date",
			"days_in_advance": 30,
			"channel": "Email",
			"condition": 'doc.custom_amc_status == "Active"',
			"recipients": [{"receiver_by_role": "AMC Team"}],
			"message": (
				"<p>The AMC for <b>{{ doc.name }}</b> ({{ doc.item_code }}), contract "
				"{{ doc.custom_amc_contract }}, ends on {{ frappe.format_date(doc.amc_expiry_date) }}.</p>"
				"<p>Open the contract and use AMC &gt; Renew AMC to send the renewal quotation.</p>"
			),
			"enabled": 1,
		}
	).insert()
	return [f"Notification {name}"]


# Phase 3 (D6): Kanban board on Repair Order status.
def _create_repair_board():
	name = "Repair Board"
	if frappe.db.exists("Kanban Board", name):
		return []
	from frappe.desk.doctype.kanban_board.kanban_board import quick_kanban_board

	quick_kanban_board("Repair Order", name, "status")
	return [f"Kanban {name}"]
