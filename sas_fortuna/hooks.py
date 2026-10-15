"""
SAS Fortuna / hooks.py

Application hooks and controlled fixtures for the SAS Fortuna app.

Fixture exports are intentionally scoped to records owned by this app.
App-owned DocTypes are maintained as source files, while any additional
Custom Fields and Property Setters are exported as fixtures.
"""

app_name = "sas_fortuna"
app_title = "SAS Fortuna"
app_publisher = "SAS Infosystem Pvt Ltd"

app_description = (
	"Custom Frappe app for Fortuna Impex Pvt Ltd, covering customer and "
	"supplier onboarding, portal access, welcome emails, email logs, "
	"Client Scripts, Server Scripts, Web Forms, Workflows, and related "
	"customizations."
)

app_email = "subhapriyo@gmail.com"
app_license = "mit"


# ============================================================================
# CUSTOMIZED DOCTYPES
# ============================================================================
# Custom Field and Property Setter records are exported only for the
# DocTypes listed here.
#
# This includes:
#   - Supplier Onboarding
#   - Supplier Welcome Email Log
#   - Customer Welcome Email Log
#
# The DocTypes themselves should remain app-owned source files. Only
# additional Custom Field and Property Setter records are exported here.

CUSTOMIZED_DOCTYPES = [
	"Supplier Onboarding",
	"Supplier Welcome Email Log",
	"Customer Welcome Email Log",
]


# ============================================================================
# PORTAL & ONBOARDING FIELDS ON STANDARD DOCTYPES
# ============================================================================
# Customer and Supplier are standard ERPNext DocTypes that other apps
# (e.g. india_compliance) also customize. They are deliberately NOT added to
# CUSTOMIZED_DOCTYPES, because that would export every Custom Field and
# Property Setter on them. Only the fields listed here are exported.

PORTAL_ONBOARDING_FIELDNAMES = [
	"custom_portal__onboarding",  # Tab Break (double underscore, created from Desk)
	"custom_is_welcome_email_sent",
	"custom_welcome_email_sent_on",
	"custom_welcome_email_sent_by",
]

PORTAL_ONBOARDING_CUSTOM_FIELDS = [
	f"{doctype}-{fieldname}"
	for doctype in ("Customer", "Supplier")
	for fieldname in PORTAL_ONBOARDING_FIELDNAMES
]


# ============================================================================
# WORKFLOW STATES
# ============================================================================
# Workflow States used by SAS Fortuna workflows that are not shipped by
# Frappe. Workflow State records are named by the state itself.

CUSTOM_WORKFLOW_STATES = [
	"Pending Approval",
]


# ============================================================================
# WORKFLOWS
# ============================================================================
# Only explicitly identified SAS Fortuna workflows are exported.
#
# Add additional workflow names here when they are created and managed
# by the SAS Fortuna application.

CUSTOM_WORKFLOWS = [
	"Supplier Onboarding Workflow",
	# "Supplier Welcome Email Log Workflow",
	# "Customer Welcome Email Log Workflow",
]


# ============================================================================
# EMAIL TEMPLATES
# ============================================================================
# Only explicitly identified SAS Fortuna email templates are exported.

CUSTOM_EMAIL_TEMPLATES = [
	"Portal Welcome Email - Fortuna Impex Pvt Ltd",
	# Used by the welcome email Server Scripts; body source lives in
	# sas_fortuna/templates/emails/portal_welcome_email.html
	"Portal Welcome Email",
]


# ============================================================================
# CLIENT SCRIPTS
# ============================================================================
# Only Client Scripts required by the SAS Fortuna onboarding and portal
# processes are exported.

CUSTOM_CLIENT_SCRIPTS = [
	"Bulk Send Supplier Welcome Email",
	"Bulk Send Customer Welcome Email",
]


# ============================================================================
# SERVER SCRIPTS
# ============================================================================
# Only Server Scripts required by the SAS Fortuna onboarding, portal,
# permissions, banking, ledger, and welcome-email processes are exported.

CUSTOM_SERVER_SCRIPTS = [
	"Bulk Send Customer Welcome Email",
	"Bulk Send Supplier Welcome Email",
	"Get Portal Ledger",
	"Get Portal Party",
	"GL Entry Permission Query - Portal Party Access",
	"Party Permission Query - Portal Customer & Supplier Access",
	"Send Customer Welcome Email on First Sales Order",
	"Supplier Welcome",
]


# ============================================================================
# WEB FORMS
# ============================================================================
# These Web Forms support the SAS Fortuna customer and supplier portal
# onboarding and self-service processes.

CUSTOM_WEB_FORMS = [
	"my-ledger",
	"supplier-registration",
]


# ============================================================================
# FIXTURES
# ============================================================================
# Fixtures contain configuration/customization records that need to be
# version-controlled with the application.
#
# IMPORTANT:
# Filters are intentionally explicit to prevent unrelated records from
# the Fortuna site from being exported into the sas_fortuna application.


fixtures = [
	# ------------------------------------------------------------------------
	# Custom Fields
	# ------------------------------------------------------------------------
	# Exports Custom Field records belonging to the DocTypes listed in
	# CUSTOMIZED_DOCTYPES, OR the explicitly named Portal & Onboarding fields
	# on Customer and Supplier.
	#
	# Keep this as a SINGLE "Custom Field" entry: export-fixtures writes one
	# file per DocType (fixtures/custom_field.json), so a second entry would
	# overwrite this one's output.
	{
		"dt": "Custom Field",
		"or_filters": [
			["dt", "in", CUSTOMIZED_DOCTYPES],
			["name", "in", PORTAL_ONBOARDING_CUSTOM_FIELDS],
		],
	},
	# ------------------------------------------------------------------------
	# Property Setters
	# ------------------------------------------------------------------------
	# Exports Property Setter records belonging only to the customized
	# DocTypes listed above.
	{
		"dt": "Property Setter",
		"filters": [
			["doc_type", "in", CUSTOMIZED_DOCTYPES],
		],
	},
	# ------------------------------------------------------------------------
	# Client Scripts
	# ------------------------------------------------------------------------
	# Exports only the explicitly listed SAS Fortuna Client Scripts.
	{
		"dt": "Client Script",
		"filters": [
			["name", "in", CUSTOM_CLIENT_SCRIPTS],
		],
	},
	# ------------------------------------------------------------------------
	# Server Scripts
	# ------------------------------------------------------------------------
	# Exports only the explicitly listed SAS Fortuna Server Scripts.
	{
		"dt": "Server Script",
		"filters": [
			["name", "in", CUSTOM_SERVER_SCRIPTS],
		],
	},
	# ------------------------------------------------------------------------
	# Web Forms
	# ------------------------------------------------------------------------
	# Exports only the explicitly listed SAS Fortuna Web Forms.
	{
		"dt": "Web Form",
		"filters": [
			["name", "in", CUSTOM_WEB_FORMS],
		],
	},
	# ------------------------------------------------------------------------
	# Email Templates
	# ------------------------------------------------------------------------
	# Exports only the explicitly listed SAS Fortuna Email Templates.
	{
		"dt": "Email Template",
		"filters": [
			["name", "in", CUSTOM_EMAIL_TEMPLATES],
		],
	},
	# ------------------------------------------------------------------------
	# Workflows
	# ------------------------------------------------------------------------
	# Exports only the explicitly listed SAS Fortuna Workflows.
	{
		"dt": "Workflow",
		"filters": [
			["name", "in", CUSTOM_WORKFLOWS],
		],
	},
	# ------------------------------------------------------------------------
	# Workflow States
	# ------------------------------------------------------------------------
	# Exports only the explicitly listed SAS Fortuna Workflow States.
	{
		"dt": "Workflow State",
		"filters": [
			["name", "in", CUSTOM_WORKFLOW_STATES],
		],
	},
	# ------------------------------------------------------------------------
	# Portal Settings
	# ------------------------------------------------------------------------
	# Portal Settings is a Singleton. It is therefore exported without a
	# filter because the site contains a single Portal Settings record.
	{
		"dt": "Portal Settings",
	},
]


# ============================================================================
# PORTAL LIST PAGES (filters, sorting, design)
# ============================================================================
# Adds column headers, sorting, filtering (status, date range), and items-per-page
# to the Customer and Supplier portal list pages (Quotations, Orders, Invoices,
# Shipments, Issues, RFQ, Supplier Quotations, Purchase Orders, Purchase Invoices).
# The patch is applied lazily on each request to avoid importing ERPNext while
# this app is loading. Engine: sas_fortuna/portal/list_engine.py; per-page
# config: sas_fortuna/portal/lists/<doctype>.py; filter bar: public/js/portal.js.

before_request = ["sas_fortuna.portal.apply_portal_overrides"]

web_include_css = "/assets/sas_fortuna/css/portal.css"
web_include_js = "/assets/sas_fortuna/js/portal.js"


# ============================================================================
# MIGRATE HOOKS
# ============================================================================
# Run on every `bench migrate` (idempotent): KYC entries in the portal sidebar
# and the Customer KYC custom fields. See sas_fortuna/setup/.

after_migrate = [
	"sas_fortuna.setup.portal_menu.execute",
	"sas_fortuna.setup.customer_fields.execute",
]

# Support Desk / Repair / AMC is kept OUT of git (see .gitignore). Wire its
# setup only where its files exist, so a checkout without them still migrates.
import os as _os

if _os.path.exists(_os.path.join(_os.path.dirname(__file__), "setup", "support_desk.py")):
	after_migrate.append("sas_fortuna.setup.support_desk.execute")
