"""after_migrate: create what the Support Desk, Repair & AMC build needs on every site.

Runs on every `bench migrate` and only ADDS what is missing, so it is safe to
re-run and never overwrites changes made later in Customize Form or Role
Permissions Manager:

  1. Roles ............... Service Engineer, AMC Team, Support Manager
  2. Stock Entry Type .... Repair Receipt (Material Receipt)
  3. Custom Fields ....... Serial No, HD Ticket, HD Customer, Stock Entry, Material
                           Request, Quotation, Sales Order, Sales Invoice, Delivery
                           Note, Opportunity, Item (AMC exclusion, extended warranty)
  4. Permissions ......... custom roles + Helpdesk "Agent" on the new DocTypes
  5. Report roles ........ the same roles on the four Query Reports
  6. Landing page ........ LANDING_SECTIONS, shown on /desk/sas-fortuna by setup/landing_page.py
  7. Portal menu ......... Tickets + Repairs in the customer portal; Issues switched off once
  8. Helpdesk role ....... "HD Customer" for portal users (New ticket / Reply on /tickets)
  9. Ticket form ......... Default template: Ticket Type + Serial No (customer's New ticket form),
                           Job Location (agents' ticket sidebar only); Resolution Details is not
                           in the sidebar (entered through the Resolution pop-up); Resolution
                           History table on HD Ticket (Desk form, read only)
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
from sas_fortuna.support.repair import START_REPAIR_CONDITION

MODULE = "SAS Fortuna"

ROLES = ["Service Engineer", "AMC Team", "Support Manager"]

STOCK_ENTRY_TYPES = {"Repair Receipt": "Material Receipt"}


def execute():
	_create_roles()
	_create_stock_entry_types()
	_create_custom_fields()
	_item_name_label()
	_add_permissions()
	_add_report_roles()
	_relax_opportunity_for_amc()
	_portal_menu()
	_helpdesk_role_for_portal_users()
	_helpdesk_ticket_form()
	_serial_no_search_fields()
	_resolution_box()
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


# Fields added to Helpdesk's "Default" ticket template: the New Ticket form, on the customer
# portal and for agents in Helpdesk. Without them a portal ticket has no type (so no team, no
# agent) and no serial (so no warranty check). In this order, first row first.
#   url_method  where the field's choices come from (support/portal.py)
#   visible_to  "Agents" keeps a field off the customer portal. Helpdesk 16 reads only this;
#               its older hide_from_customer flag is ignored (that showed Job Location to
#               customers), so setup also corrects it on rows that already exist.
TICKET_FORM_FIELDS = [
	{
		# Agents start here: the customer decides Job Location and which units are offered
		# (support/new_ticket.py; the page side is setup/data/fortuna_new_ticket_form.js).
		# A portal customer is known from their login, so they never see it.
		"fieldname": "custom_erpnext_customer",
		"required": 0,
		"visible_to": "Agents",
		"placeholder": "Pick the customer first",
	},
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
	{
		# Agents only, read only: the Item Name of the picked unit, filled as soon as a Serial No
		# is picked. Customers see it in their Serial No choices already
		# ("SN-1 · Biometric Reader (FPM-3171)").
		"fieldname": "custom_product_name",
		"required": 0,
		"visible_to": "Agents",
		"placeholder": "Filled from the Serial No",
	},
	{
		# The agent's ticket sidebar only: it is set on save from the customer's Ship To address
		# (Kolkata when none matches), never asked for on the New Ticket form (support/new_ticket.py
		# drops it there). An agent may correct it in the sidebar, which re-routes the ticket.
		"fieldname": "custom_job_location",
		"required": 0,
		"visible_to": "Agents",
		"placeholder": "Job Location",
	},
]

# Rows this app once added and has since taken back out. resolution_details: entered only through
# the Resolution pop-up (so every resolution reaches the Resolution History) and shown read-only
# as a ticket comment; an editable sidebar box would bypass both.
REMOVED_TICKET_FORM_FIELDS = ["resolution_details"]


def _helpdesk_ticket_form():
	"""Keep the Default ticket template in step with TICKET_FORM_FIELDS.

	  - a missing row is added right after the row it follows in TICKET_FORM_FIELDS (the
	    Customer row first), so a field added later still sits where it belongs
	  - a row's visible_to is put back to ours: who may see a field is not a layout choice
	  - rows in REMOVED_TICKET_FORM_FIELDS are taken out
	An admin's other edits (required, placeholder, the order of the other rows) are kept."""
	if not frappe.db.exists("HD Ticket Template", "Default"):
		return
	template = frappe.get_doc("HD Ticket Template", "Default")
	changed = False

	# Rows taken out of the form.
	for row in [r for r in template.fields if r.fieldname in REMOVED_TICKET_FORM_FIELDS]:
		template.remove(row)
		changed = True

	# Missing rows, and who may see the ones that exist.
	rows = {r.fieldname: r for r in template.fields}
	for i, field in enumerate(TICKET_FORM_FIELDS):
		row = rows.get(field["fieldname"])
		if not row:
			row = template.append("fields", field)
			before = rows.get(TICKET_FORM_FIELDS[i - 1]["fieldname"]) if i else None
			if before:  # move it up, next to the row it follows
				template.fields.remove(row)
				template.fields.insert(template.fields.index(before) + 1, row)
			rows[field["fieldname"]] = row
			changed = True
		elif field.get("visible_to") and row.visible_to != field["visible_to"]:
			row.visible_to = field["visible_to"]
			changed = True

	# The Customer row leads: agents pick the customer before anything else.
	first = TICKET_FORM_FIELDS[0]["fieldname"]
	if template.fields and template.fields[0].fieldname != first:
		row = next(r for r in template.fields if r.fieldname == first)
		template.fields.remove(row)
		template.fields.insert(0, row)
		changed = True

	if changed:
		for idx, row in enumerate(template.fields, 1):
			row.idx = idx
		template.save(ignore_permissions=True)


def _item_name_label():
	"""HD Ticket's custom_product_name was first labelled "Product Name"; it is now "Item Name",
	the name ERPNext uses. _create_custom_fields keeps existing labels, so older sites are renamed
	here. Only the old default is replaced: a label an admin picked stays."""
	name = frappe.db.get_value(
		"Custom Field", {"dt": "HD Ticket", "fieldname": "custom_product_name", "label": "Product Name"}
	)
	if name:
		frappe.db.set_value("Custom Field", name, "label", "Item Name")
		frappe.clear_cache(doctype="HD Ticket")


# Serial No search (Helpdesk's link dropdown, and Desk's): show the item under each serial.
# Helpdesk lists a record's search fields as the grey line under it, so the Item Name leads.
SERIAL_SEARCH_FIELDS = ["item_name", "item_code"]


def _serial_no_search_fields():
	"""Put item_name and item_code first in Serial No's search fields; any others an admin added
	stay after them."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	current = [f.strip() for f in (frappe.get_meta("Serial No").search_fields or "").split(",") if f.strip()]
	wanted = SERIAL_SEARCH_FIELDS + [f for f in current if f not in SERIAL_SEARCH_FIELDS]
	if current == wanted:
		return
	make_property_setter(
		"Serial No",
		None,
		"search_fields",
		",".join(wanted),
		"Data",
		for_doctype=True,
		validate_fields_for_doctype=False,
	)
	frappe.clear_cache(doctype="Serial No")


# Desk form: Resolution Details shows when the agent asked to resolve without one (flag set by
# support/hd_ticket.py), while Resolved is picked, and on resolved tickets. Set once; a later
# Customize Form change is kept. (It is not in the Helpdesk sidebar: see TICKET_FORM_FIELDS.)
RESOLUTION_DEPENDS_ON = (
	"eval:doc.custom_resolution_requested || doc.status == 'Resolved' || doc.status_category == 'Resolved'"
)


def _resolution_box():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	if not frappe.get_meta("HD Ticket").has_field("resolution_details"):
		return  # older Helpdesk: notes go in custom_resolution_notes, always shown
	if frappe.db.exists(
		"Property Setter",
		{"doc_type": "HD Ticket", "field_name": "resolution_details", "property": "depends_on"},
	):
		return
	make_property_setter(
		"HD Ticket",
		"resolution_details",
		"depends_on",
		RESOLUTION_DEPENDS_ON,
		"Code",
		validate_fields_for_doctype=False,
	)


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
		# Renewal reminders already e-mailed for this validity (support/tasks.py); reset on a new date.
		_ro(fieldname="custom_sim_reminders_sent", fieldtype="Int", label="SIM Reminders Sent"),
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
		# The unit's Item Name, kept with the ticket; shown next to Serial No on the agent's New
		# Ticket form, whose searchable Serial No dropdown shows only the serial.
		_ro(
			fieldname="custom_product_name",
			fieldtype="Data",
			label="Item Name",
			fetch_from="custom_serial_no.item_name",
		),
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
		{
			# From the customer's address (support/hd_ticket.py); with the Ticket Type it picks the team.
			"fieldname": "custom_job_location",
			"fieldtype": "Link",
			"label": "Job Location",
			"options": "Job Location",
			"in_standard_filter": 1,
		},
		_ro(fieldname="custom_invoice_no", fieldtype="Data", label="Invoice No"),
		_ro(fieldname="custom_invoice_date", fieldtype="Date", label="Invoice Date"),
		_ro(fieldname="custom_warranty_end", fieldtype="Date", label="Warranty End"),
		_ro(fieldname="custom_amc_expiry", fieldtype="Date", label="AMC Expiry"),
		{"fieldname": "custom_links_section", "fieldtype": "Section Break", "label": "Linked Documents"},
		_ro(fieldname="custom_sales_order", fieldtype="Link", label="Sales Order", options="Sales Order"),
		_ro(fieldname="custom_repair_order", fieldtype="Link", label="Repair Order", options="Repair Order"),
		_ro(fieldname="custom_repair_status", fieldtype="Data", label="Repair Status"),
		# Set when an agent picks Resolved without notes: shows the Resolution Details box
		# (support/hd_ticket.py require_resolution_notes). Cleared once resolved.
		{
			"fieldname": "custom_resolution_requested",
			"fieldtype": "Check",
			"label": "Resolution Notes Requested",
			"hidden": 1,
			"no_copy": 1,
		},
		{
			# Which finished status the agent picked (Resolved / Closed): the pop-up saves with it.
			"fieldname": "custom_resolution_requested_status",
			"fieldtype": "Data",
			"label": "Resolution Requested For",
			"hidden": 1,
			"no_copy": 1,
		},
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


# Item: what Fortuna's answers need on the product master.
ITEM_FIELDS = _chain(
	[
		{
			# AMC contract exclusions: consumables are charged even on an AMC repair.
			"fieldname": "custom_amc_excluded",
			"fieldtype": "Check",
			"label": "Not Covered by AMC",
			"description": "Consumable (e.g. biometric sensor, maintenance-free battery): "
			"charged on AMC repairs as per the AMC contract.",
		},
		{
			# Extended warranty is a service line on the sale bill (Fortuna's answer).
			"fieldname": "custom_extended_warranty_months",
			"fieldtype": "Int",
			"label": "Extended Warranty (Months)",
			"description": "For an extended-warranty service item: months added to the warranty "
			"of the units sold on the same Sales Invoice.",
			"non_negative": 1,
		},
	],
	after="warranty_period",
)

# Every resolution given on the ticket (child: Ticket Resolution), kept when it is reopened.
# Filled by support/hd_ticket.py; shown on the Desk form right under Resolution Details.
RESOLUTION_HISTORY_FIELDS = [
	{
		"fieldname": "custom_resolution_history",
		"fieldtype": "Table",
		"label": "Resolution History",
		"options": "Ticket Resolution",
		"insert_after": "resolution_details",
		"read_only": 1,
		"no_copy": 1,
		"module": MODULE,
	},
]

CUSTOM_FIELDS = {
	"Serial No": SERIAL_NO_FIELDS,
	"Item": ITEM_FIELDS,
	"HD Ticket": HD_TICKET_FIELDS + RESOLUTION_HISTORY_FIELDS,
	# Where the engineer works; location teams (Hardware Support - Kolkata) are built from it.
	"HD Agent": _chain(
		[
			{
				"fieldname": "custom_job_location",
				"fieldtype": "Link",
				"label": "Job Location",
				"options": "Job Location",
				"in_list_view": 1,
				"in_standard_filter": 1,
			}
		],
		after="agent_name",
	),
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
	# Agents and engineers make and work Repair Orders, which link to the unit, its model and
	# the customer: without read on these the form stops with "Insufficient Permission for
	# Serial No". Fortuna's SW/HW staff have no other ERPNext role. Read only.
	"Serial No": {
		"AMC Team": ["read", "report", "print"],
		"Support Manager": ["read", "report", "print", "export"],
		"Agent": ["read", "select", "report"],
		"Service Engineer": ["read", "select", "report"],
	},
	"Item": {
		"Agent": ["read", "select"],
		"Service Engineer": ["read", "select"],
	},
	"Customer": {
		"Agent": ["read", "select"],
		"Service Engineer": ["read", "select"],
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
				"Payment policy, AMC and SIM alerts, terms, warehouses and accounts.",
				"settings",
			),
			("Helpdesk", "url", "/helpdesk", "Where agents pick up and answer tickets.", "headset"),
			(
				"Tickets",
				"doctype",
				"HD Ticket",
				"Every ticket with its branch, team and status; filter by Job Location.",
				"tag",
			),
			(
				"Support Engineers",
				"doctype",
				"HD Agent",
				"Each engineer with their branch (Job Location).",
				"users",
			),
		],
	},
	# Go-live configuration from Fortuna's answers (setup/fortuna_impex.py creates the records;
	# these links are where they are kept up to date).
	{
		"title": "Helpdesk & Alerts Setup",
		"intro": "Response targets, working days, teams and the mails that go out.",
		"links": [
			(
				"SLA Policies",
				"doctype",
				"HD Service Level Agreement",
				"Response target per team: attend within 48 hours.",
				"clock",
			),
			(
				"Support Holidays",
				"doctype",
				"HD Service Holiday List",
				"Weekly off and public holidays the SLA clock skips.",
				"calendar",
			),
			(
				"Helpdesk Teams",
				"doctype",
				"HD Team",
				"Software, Hardware and Post-Installation agents.",
				"users",
			),
			(
				"Job Locations",
				"doctype",
				"Job Location",
				"Branches, the cities/states they serve and their invoice prefix key.",
				"pass",
			),
			(
				"Support Mailbox",
				"doctype",
				"Email Account",
				"amc@fortunaindia.com: add the password to turn e-mail tickets on.",
				"mail",
			),
			(
				"Alerts",
				"doctype",
				"Notification",
				"AMC renewal, unit received and other automatic e-mails.",
				"bell",
			),
			(
				"Ticket Subjects",
				"doctype",
				"Ticket Subject",
				"Subject dropdown on the New Ticket form, per ticket type; untick Active to hide one.",
				"tag",
			),
			(
				"Knowledge Base",
				"url",
				"/helpdesk/kb",
				"FAQ articles customers are shown while raising a ticket.",
				"form",
			),
		],
	},
	{
		"title": "Quotations, Terms & Rates",
		"intro": "What AMC and repair quotations print and charge.",
		"links": [
			(
				"Terms and Conditions",
				"doctype",
				"Terms and Conditions",
				"AMC contract terms and repair terms.",
				"form",
			),
			(
				"Payment Terms",
				"doctype",
				"Payment Terms Template",
				"100% against Pro-Forma Invoice.",
				"form",
			),
			(
				"Standard Rates",
				"doctype",
				"Item Price",
				"Repair service Rs 1800, freight Rs 200 per device.",
				"tag",
			),
			("Letter Head", "doctype", "Letter Head", "Logo and address, taken from the Company.", "pass"),
			(
				"Print Formats",
				"doctype",
				"Print Format",
				"AMC Quotation, Pro-Forma, Job Sheet and more.",
				"report",
			),
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
	# settings field: (item code, SAC). 998719 = maintenance and repair services, as on
	# Fortuna's own AMC quotation (1QTN-1906/24-25); freight and SIM codes still to be confirmed.
	"service_charge_item": ("Repair Service Charge", "998719"),
	"freight_item": ("Freight Charges", "996511"),
	"sim_recharge_item": ("SIM Recharge", "998422"),
	None: ("AMC Service", "998719"),  # used on AMC quotations, not in settings
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
		done += ensure_service_item(code, sac)
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


def ensure_service_item(code, sac, **values):
	"""Create one non-stock service item if missing; return what was done.

	fortuna_erp keeps every Item disabled until its Status is "Approved"
	(customisations/item.py), and a disabled item cannot go on a quotation,
	so ours are approved. On production Fortuna's approver may do this instead.
	"""
	done = []
	if not frappe.db.exists("Item", code):
		_ensure_hsn(sac)
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": _services_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"gst_hsn_code": sac,
				**values,
			}
		).insert(ignore_permissions=True)
		done.append(f"Item {code}")
	item = frappe.get_doc("Item", code)
	if item.meta.has_field("custom_status") and item.custom_status != "Approved":
		item.custom_status = "Approved"
		item.save(ignore_permissions=True)
		done.append(f"Approved item {code}")
	return done


def _services_group():
	"""ERPNext's 'Services' item group, or the root group on a site without it."""
	return "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"


def _ensure_hsn(code):
	"""india_compliance links Item.gst_hsn_code to a GST HSN Code master: create the code if missing."""
	if code and frappe.db.exists("DocType", "GST HSN Code") and not frappe.db.exists("GST HSN Code", code):
		frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": code, "description": code}).insert(
			ignore_permissions=True
		)


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
	# Fortuna: work starts once the quotation is confirmed; payment in full before dispatch.
	("Awaiting Payment", "Start Repair", "In Repair", "Service Engineer", START_REPAIR_CONDITION),
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
