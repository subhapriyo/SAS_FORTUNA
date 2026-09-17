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
	"Address - Auto Link Portal Party",
	"Bank Account Permission Query - Portal Party Access",
	"Bulk Send Customer Welcome Email",
	"Bulk Send Supplier Welcome Email",
	"Get Portal Bank Accounts",
	"Get Portal Ledger",
	"Get Portal Party",
	"GL Entry Permission Query - Portal Party Access",
	"Party Permission Query - Portal Customer & Supplier Access",
	"Party Set Bank Account Owner Before Insert",
	"Send Customer Welcome Email on First Sales Order",
	"Supplier Welcome",
]


# ============================================================================
# WEB FORMS
# ============================================================================
# These Web Forms support the SAS Fortuna customer and supplier portal
# onboarding and self-service processes.

CUSTOM_WEB_FORMS = [
	"bank-accounts",
	"my-company-address",
	"my-ledger",
	"supplier-registration",
	"update-customer-details",
	"update-supplier-details",
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
	# Exports Custom Field records belonging only to the DocTypes listed in
	# CUSTOMIZED_DOCTYPES.
	{
		"dt": "Custom Field",
		"filters": [
			["dt", "in", CUSTOMIZED_DOCTYPES],
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
	# Portal Settings
	# ------------------------------------------------------------------------
	# Portal Settings is a Singleton. It is therefore exported without a
	# filter because the site contains a single Portal Settings record.
	{
		"dt": "Portal Settings",
	},
]


after_migrate = [
	"sas_fortuna.patches.supplier_portal.execute",
	"sas_fortuna.patches.customer_portal.execute",
]
