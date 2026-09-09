"""
sas_fortuna / hooks.py

Only hooks that are actually in use are enabled below. This file is kept
intentionally small — add a new hook only when a real requirement shows
up, not because it "might be useful later" (see README > Hooks).
"""

app_name = "sas_fortuna"
app_title = "SAS Fortuna"
app_publisher = "SAS Infosystem Pvt Ltd"
app_description = (
	"Custom Frappe app bundling SAS Fortuna's Client Scripts, "
	"Server Scripts, Web Forms, Portal Settings, Email Templates, "
	"and DocType customizations for version-controlled deployment."
)
app_email = "subhapriyo@gmail.com"
app_license = "mit"

# ---------------------------------------------------------------------------
# App logo
# ---------------------------------------------------------------------------
# CONFLICT WITH ORIGINAL SPEC, RESOLVED:
# The original brief asked for `app_logo_url = "/assets/sas_fortuna/images/logo.png"`
# as a hooks.py key. That is NOT a hook Frappe v16 reads automatically —
# setting it here would silently do nothing. The logo is still shipped as
# a real static asset (so the URL below is valid once the app is
# installed and `bench build` has run):
#
#     sas_fortuna/public/images/logo.png -> /assets/sas_fortuna/images/logo.png
#
# To make it appear in the UI, wire that asset path into whatever actually
# reads it on the target site — e.g. Website Settings > App Logo /
# Banner Image (Desk: Settings > Website Settings), or a custom
# `templates/pages/*.html` if this is used on a portal page. That's a
# per-site configuration step, not something an app hook can force, so
# it's documented in README > Installing on a Site rather than exported
# as a fixture.
# app_logo_url = "/assets/sas_fortuna/images/logo.png"  # NOT a real hook — see note above

# ---------------------------------------------------------------------------
# Fixtures — version-controlled customizations
# ---------------------------------------------------------------------------
# Every entry is scoped with a filter so `bench export-fixtures` can never
# sweep up unrelated site data (other apps' Custom Fields, ERPNext's own
# Property Setters, someone else's Client Script, etc.). See
# README > Fixture Management for the full rationale.
#
# BEFORE THE FIRST EXPORT, YOU MUST:
#   1. List every standard DocType you've added Custom Fields /
#      Property Setters to below, in CUSTOMIZED_DOCTYPES.
#   2. Add the EXACT name of every Client Script / Server Script /
#      Web Form / Email Template you create for this project into the
#      matching list below, the moment you create it.
#
# No naming convention (prefix, tag, etc.) is relied on — scoping is by
# explicit, hand-maintained name list instead. A record you forget to
# add here is simply skipped on export (safe default), never
# accidentally swept in. If you rename a record in the Desk UI, update
# its name here too, or the next export silently stops tracking it.
#
# Do NOT run `bench export-fixtures` until these are populated — empty
# lists mean the fixtures currently match nothing (safe default), not
# "everything". An unscoped filter would pull every Custom Field /
# Property Setter / Client Script / etc. on the site, including
# ERPNext's own, other installed apps' (e.g. fortuna_erp), and anything
# unrelated.

CUSTOMIZED_DOCTYPES = [
	# "Customer",
	# "Supplier",
	# "Sales Order",
]

CUSTOM_CLIENT_SCRIPTS = [
	# "Sales Order - Highlight Overdue",
]

CUSTOM_SERVER_SCRIPTS = [
	# "Sales Order - Before Submit - Validate Credit Limit",
]

CUSTOM_WEB_FORMS = [
	# "customer-onboarding",
]

CUSTOM_EMAIL_TEMPLATES = [
	# "Order Confirmation",
]

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["dt", "in", CUSTOMIZED_DOCTYPES]],
	},
	{
		"dt": "Property Setter",
		"filters": [["doc_type", "in", CUSTOMIZED_DOCTYPES]],
	},
	{
		"dt": "Client Script",
		"filters": [["name", "in", CUSTOM_CLIENT_SCRIPTS]],
	},
	{
		"dt": "Server Script",
		"filters": [["name", "in", CUSTOM_SERVER_SCRIPTS]],
	},
	{
		"dt": "Web Form",
		"filters": [["name", "in", CUSTOM_WEB_FORMS]],
	},
	{
		"dt": "Email Template",
		"filters": [["name", "in", CUSTOM_EMAIL_TEMPLATES]],
	},
	# Portal Settings is a single/settings doctype — one record exists per
	# site, so it can't pull in unrelated records and needs no filter.
	{"dt": "Portal Settings"},
]

# ---------------------------------------------------------------------------
# Website / Desk asset includes
# ---------------------------------------------------------------------------
# Uncomment only once sas_fortuna/public/js/sas_fortuna.js and/or
# .../css/sas_fortuna.css actually exist and contain something real.
# app_include_js = "/assets/sas_fortuna/js/sas_fortuna.js"
# app_include_css = "/assets/sas_fortuna/css/sas_fortuna.css"

# ---------------------------------------------------------------------------
# Deliberately not used (yet): doc_events, scheduler_events,
# override_whitelisted_methods, boot_session, permission_query_conditions,
# website_route_rules, etc. Add one here only when a specific, documented
# business requirement needs it — never speculatively.
# ---------------------------------------------------------------------------
