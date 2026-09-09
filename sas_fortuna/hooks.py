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
#   2. Name every Client Script / Server Script / Web Form / Email
#      Template you create for this project with the FIXTURE_NAME_PREFIX
#      below, so the name-based filters catch exactly (and only) your
#      records.
#
# Do NOT run `bench export-fixtures` until both are done — an empty
# CUSTOMIZED_DOCTYPES list means the Custom Field / Property Setter
# fixtures currently match nothing (safe default), not "everything".

CUSTOMIZED_DOCTYPES = [
	# "Customer",
	# "Supplier",
	# "Sales Order",
]

FIXTURE_NAME_PREFIX = "SAS Fortuna - "

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
		"filters": [["name", "like", f"{FIXTURE_NAME_PREFIX}%"]],
	},
	{
		"dt": "Server Script",
		"filters": [["name", "like", f"{FIXTURE_NAME_PREFIX}%"]],
	},
	{
		"dt": "Web Form",
		"filters": [["name", "like", f"{FIXTURE_NAME_PREFIX}%"]],
	},
	{
		"dt": "Email Template",
		"filters": [["name", "like", f"{FIXTURE_NAME_PREFIX}%"]],
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
