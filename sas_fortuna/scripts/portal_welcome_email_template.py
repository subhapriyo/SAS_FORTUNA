"""
sas_fortuna/scripts/portal_welcome_email_template.py

Ensures the "Portal Welcome Email" Email Template exists. Used by:
  - Send Customer Welcome Email on First Sales Order
  - Supplier Welcome (Supplier Onboarding)
  - Bulk Send Customer / Supplier Welcome Email

The body is kept in the app at
    sas_fortuna/templates/emails/portal_welcome_email.html
so it is version-controlled alongside the scripts that render it.

    bench --site <site> execute sas_fortuna.scripts.portal_welcome_email_template.execute
    bench --site <site> execute sas_fortuna.scripts.portal_welcome_email_template.verify

execute() only CREATES the template when it is missing. An existing template
is never overwritten; execute() reports whether its subject/body differ from
the app's copy so you can decide what to do.
"""

import frappe

TEMPLATE_NAME = "Portal Welcome Email"
SUBJECT = 'Welcome to {{ company or "Company" }}!'
BODY_PATH = ("templates", "emails", "portal_welcome_email.html")


def _app_body():
	path = frappe.get_app_path("sas_fortuna", *BODY_PATH)
	with open(path, encoding="utf-8") as f:
		return f.read()


def _normalise(text):
	# Ignore line endings and trailing whitespace per line (the repo's
	# pre-commit hooks strip it from the app copy).
	lines = (text or "").replace("\r\n", "\n").split("\n")
	return "\n".join(line.rstrip() for line in lines).strip()


def _compare(template):
	"""Return a list of differences between the site's template and the app's copy."""
	diffs = []
	if (template.subject or "") != SUBJECT:
		diffs.append(f"subject is {template.subject!r}, app copy is {SUBJECT!r}")
	if not template.get("use_html"):
		diffs.append("use_html is off")
	if _normalise(template.get("response_html")) != _normalise(_app_body()):
		diffs.append("response_html differs from templates/emails/portal_welcome_email.html")
	return diffs


def execute():
	if frappe.db.exists("Email Template", TEMPLATE_NAME):
		template = frappe.get_doc("Email Template", TEMPLATE_NAME)
		diffs = _compare(template)
		print(f"Email Template '{TEMPLATE_NAME}' already exists - left unchanged.")
		for d in diffs:
			print(f"  note: {d}")
		if not diffs:
			print("  matches the app copy.")
		return

	frappe.get_doc(
		{
			"doctype": "Email Template",
			"name": TEMPLATE_NAME,
			"subject": SUBJECT,
			"use_html": 1,
			"response_html": _app_body(),
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Created Email Template '{TEMPLATE_NAME}'.")


def verify():
	if not frappe.db.exists("Email Template", TEMPLATE_NAME):
		print(f"MISSING  Email Template '{TEMPLATE_NAME}'")
		return
	diffs = _compare(frappe.get_doc("Email Template", TEMPLATE_NAME))
	if diffs:
		for d in diffs:
			print(f"DIFF     {d}")
	else:
		print(f"OK       Email Template '{TEMPLATE_NAME}' matches the app copy")
