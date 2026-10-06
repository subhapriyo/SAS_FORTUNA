"""
sas_fortuna/scripts/portal_onboarding.py

Idempotent setup for the "Portal & Onboarding" customization on Customer and
Supplier, plus the "Pending Approval" Workflow State. Run on the DEV site only;
production receives these records through fixtures on `bench migrate`.

    bench --site <site> execute sas_fortuna.scripts.portal_onboarding.execute
    bench --site <site> execute sas_fortuna.scripts.portal_onboarding.verify

Safe to re-run: existing Custom Fields are never re-positioned or duplicated,
and an existing Workflow State is left untouched.
"""

import frappe

APP = "sas_fortuna"
TARGET_DOCTYPES = ("Customer", "Supplier")
WORKFLOW_STATE = "Pending Approval"

# Matches the tab already created from Desk on Customer (note the double
# underscore), so Customer is not given a second "Portal & Onboarding" tab.
TAB_FIELDNAME = "custom_portal__onboarding"

# Order matters: each field is inserted after the previous one.
FIELDS = [
	{
		"fieldname": TAB_FIELDNAME,
		"label": "Portal & Onboarding",
		"fieldtype": "Tab Break",
	},
	{
		"fieldname": "custom_is_welcome_email_sent",
		"label": "Is Welcome Email Sent",
		"fieldtype": "Check",
		"default": "0",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "custom_welcome_email_sent_on",
		"label": "Welcome Email Sent On",
		"fieldtype": "Datetime",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "custom_welcome_email_sent_by",
		"label": "Welcome Email Sent By",
		"fieldtype": "Link",
		"options": "User",  # the DocType is "User", not "Users"
		"read_only": 1,
		"no_copy": 1,
	},
]

# Properties enforced on fields that already exist (position is NOT touched).
ENFORCED_PROPS = ("label", "fieldtype", "options", "read_only", "no_copy")


def _app_module():
	"""Module Def belonging to sas_fortuna, so a module-filtered fixture picks the fields up."""
	modules = frappe.get_all("Module Def", filters={"app_name": APP}, pluck="name")
	return modules[0] if modules else None


def _anchor_fieldname(doctype):
	"""
	Last field of the 'Portal Users' tab, so the new tab lands immediately after it.
	Falls back to the last field of the DocType when no such tab exists.
	"""
	fields = frappe.get_meta(doctype).fields
	start = next(
		(
			i
			for i, df in enumerate(fields)
			if df.fieldtype == "Tab Break" and (df.label or "").strip().lower() == "portal users"
		),
		None,
	)
	if start is None:
		return fields[-1].fieldname, "end of DocType (no 'Portal Users' tab found)"

	end = start
	for j in range(start + 1, len(fields)):
		if fields[j].fieldtype == "Tab Break":
			break
		end = j
	return fields[end].fieldname, f"after '{fields[end].fieldname}' (end of Portal Users tab)"


def _ensure_fields(doctype, module):
	log = []
	meta = frappe.get_meta(doctype)
	tab_exists = frappe.db.exists("Custom Field", f"{doctype}-{TAB_FIELDNAME}")

	if not tab_exists:
		insert_after, where = _anchor_fieldname(doctype)
		log.append(f"  anchor: {where}")
	else:
		insert_after = None  # positions already set; only enforce properties

	for spec in FIELDS:
		name = f"{doctype}-{spec['fieldname']}"

		if frappe.db.exists("Custom Field", name):
			cf = frappe.get_doc("Custom Field", name)
			changed = [p for p in ENFORCED_PROPS if p in spec and cf.get(p) != spec[p]]
			for p in changed:
				cf.set(p, spec[p])
			if module and not cf.get("module"):
				cf.module = module
				changed.append("module")
			if changed:
				cf.save()
				log.append(f"  updated {name}: {', '.join(changed)}")
			else:
				log.append(f"  ok      {name}")
			insert_after = spec["fieldname"]
			continue

		# Guard against a standard field already using this fieldname.
		if meta.get_field(spec["fieldname"]):
			frappe.throw(f"{doctype} already has a field named {spec['fieldname']}")

		cf = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": doctype,
				"insert_after": insert_after,
				**({"module": module} if module else {}),
				**spec,
			}
		)
		cf.insert()
		log.append(f"  created {name} (after {insert_after})")
		insert_after = spec["fieldname"]

	frappe.clear_cache(doctype=doctype)
	return log


def _ensure_workflow_state():
	if frappe.db.exists("Workflow State", WORKFLOW_STATE):
		return f"  ok      Workflow State '{WORKFLOW_STATE}' already exists"
	frappe.get_doc(
		{
			"doctype": "Workflow State",
			"workflow_state_name": WORKFLOW_STATE,
			"style": "Warning",
		}
	).insert()
	return f"  created Workflow State '{WORKFLOW_STATE}'"


def execute():
	module = _app_module()
	print(f"Module for Custom Fields: {module or '(none found - module left blank)'}")

	for dt in TARGET_DOCTYPES:
		print(f"\n{dt}")
		for line in _ensure_fields(dt, module):
			print(line)

	print("\nWorkflow State")
	print(_ensure_workflow_state())

	frappe.db.commit()
	print("\nDone. Next: bench --site <site> export-fixtures --app sas_fortuna")


def verify():
	ok = True
	for dt in TARGET_DOCTYPES:
		meta = frappe.get_meta(dt)
		for spec in FIELDS:
			df = meta.get_field(spec["fieldname"])
			if not df:
				print(f"MISSING  {dt}.{spec['fieldname']}")
				ok = False
				continue
			bad = [p for p in ENFORCED_PROPS if p in spec and df.get(p) != spec[p]]
			print(
				f"{'BAD     ' if bad else 'OK      '}{dt}.{spec['fieldname']}"
				+ (f"  mismatch: {', '.join(bad)}" if bad else "")
			)
			ok = ok and not bad

	count = frappe.db.count("Workflow State", {"name": WORKFLOW_STATE})
	print(f"{'OK      ' if count == 1 else 'BAD     '}Workflow State '{WORKFLOW_STATE}' x{count}")
	ok = ok and count == 1

	print("\nALL GOOD" if ok else "\nISSUES FOUND")
