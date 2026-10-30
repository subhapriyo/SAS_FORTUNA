"""Post-migrate check: did the Support Desk build land on this site?

Read-only. Prints PASS / FAIL / TODO per item and a summary.
Run after `bench migrate`:
    bench --site fortuna.localhost execute sas_fortuna.support.check_setup.run
"""

import frappe

from sas_fortuna.setup.support_desk import CUSTOM_FIELDS, PERMISSIONS, REPORT_ROLES, ROLES, STOCK_ENTRY_TYPES

DOCTYPES = [
	"Fortuna Support Settings",
	"Fortuna Team Route",
	"Repair Order",
	"Repair Order Part",
	"Returnable Gate Pass",
	"AMC Covered Item",
]

# Settings the code reads with require_setting(): blank = the feature stops with a message.
REQUIRED_SETTINGS = [
	"company",
	"repair_receipt_entry_type",
	"repair_in_warehouse",
	"repair_wip_warehouse",
	"spares_warehouse",
	"loaner_source_warehouse",
	"customer_loaner_warehouse",
	"warranty_expense_account",
	"service_charge_item",
]

# Hook -> phase in which it should be wired (docs/support_desk/hooks_to_merge.py).
EXPECTED_HOOKS = {
	("Customer", "after_insert"): ("sas_fortuna.support.customer_sync.customer_after_insert", 1),
	("Contact", "validate"): ("sas_fortuna.support.customer_sync.contact_validate", 1),
	("HD Ticket", "validate"): ("sas_fortuna.support.hd_ticket.validate", 2),
	("Sales Invoice", "on_submit"): ("sas_fortuna.support.sales.sales_invoice_on_submit", 2),
	("Stock Entry", "on_submit"): ("sas_fortuna.support.repair.stock_entry_on_submit", 3),
	("Sales Order", "on_submit"): ("sas_fortuna.support.repair.sales_order_on_submit", 4),
	("Payment Entry", "on_submit"): ("sas_fortuna.support.repair.payment_entry_changed", 4),
	("Delivery Note", "on_submit"): ("sas_fortuna.support.repair.delivery_note_on_submit", 5),
	("Sales Order", "validate"): ("sas_fortuna.support.amc.sales_order_validate", 6),
}

_counts = {"PASS": 0, "FAIL": 0, "TODO": 0}


def _line(status, text):
	_counts[status] += 1
	print(f"  [{status}] {text}")


def run():
	_counts.update(PASS=0, FAIL=0, TODO=0)

	print("\n== 1. DocTypes (synced from app files)")
	for dt in DOCTYPES:
		_line("PASS" if frappe.db.exists("DocType", dt) else "FAIL", dt)

	print("\n== 2. Query Reports")
	for report in REPORT_ROLES:
		_line("PASS" if frappe.db.exists("Report", report) else "FAIL", report)

	print("\n== 3. Roles and Stock Entry Type (setup/support_desk.py)")
	for role in ROLES:
		_line("PASS" if frappe.db.exists("Role", role) else "FAIL", f"Role {role}")
	for name in STOCK_ENTRY_TYPES:
		_line("PASS" if frappe.db.exists("Stock Entry Type", name) else "FAIL", f"Stock Entry Type {name}")

	print("\n== 4. Custom fields")
	for dt, fields in CUSTOM_FIELDS.items():
		if not frappe.db.exists("DocType", dt):
			_line("TODO", f"{dt}: DocType not installed on this site (skipped)")
			continue
		missing = [
			f["fieldname"]
			for f in fields
			if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": f["fieldname"]})
		]
		if missing:
			_line("FAIL", f"{dt}: missing {', '.join(missing)}")
		else:
			_line("PASS", f"{dt}: {len(fields)} fields")

	print("\n== 5. Permissions for custom roles")
	for doctype, roles in PERMISSIONS.items():
		for role in roles:
			if not frappe.db.exists("Role", role):
				_line("TODO", f"{doctype} / {role}: role not on this site")
				continue
			found = frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role})
			_line("PASS" if found else "FAIL", f"{doctype} / {role}")

	print("\n== 6. Fortuna Support Settings (fill in at /desk/sas-fortuna/fortuna-support-settings/)")
	if frappe.db.exists("DocType", "Fortuna Support Settings"):
		settings = frappe.get_single("Fortuna Support Settings")
		for field in REQUIRED_SETTINGS:
			_line("PASS" if settings.get(field) else "TODO", field)
		_line("PASS" if settings.team_routing else "TODO", "Ticket Type -> Team routing rows")

	print("\n== 7. Hooks wired in hooks.py (add per phase from docs/support_desk/hooks_to_merge.py)")
	doc_events = frappe.get_hooks("doc_events") or {}
	for (doctype, event), (path, phase) in EXPECTED_HOOKS.items():
		wired = path in (doc_events.get(doctype, {}).get(event) or [])
		_line("PASS" if wired else "TODO", f"Phase {phase}: {doctype}.{event} -> {path}")
	jobs = (frappe.get_hooks("scheduler_events") or {}).get("daily") or []
	wired = "sas_fortuna.support.tasks.send_amc_enquiries" in jobs
	_line("PASS" if wired else "TODO", "Phase 6: daily jobs (support.tasks)")

	print("\n== 8. Masters you create in the UI (Phase 0-1)")
	for doctype, name in [
		("HD Ticket Type", "Software"),
		("HD Ticket Type", "Hardware"),
		("HD Ticket Type", "Post-Installation"),
		("HD Ticket Status", "Paused"),
		("Workflow", "Repair Order Flow"),
	]:
		if frappe.db.exists("DocType", doctype):
			_line("PASS" if frappe.db.exists(doctype, name) else "TODO", f"{doctype} {name}")

	print(f"\nSummary: {_counts['PASS']} PASS, {_counts['FAIL']} FAIL, {_counts['TODO']} TODO")
	if _counts["FAIL"]:
		print(
			"FAIL = something migrate should have created is missing: check Error Log, then re-run migrate."
		)
