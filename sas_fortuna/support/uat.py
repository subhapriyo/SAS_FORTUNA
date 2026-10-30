"""UAT logins: one test user per role, so each person at UAT sees only their own screens.

    bench --site fortuna.localhost execute sas_fortuna.support.uat.create_uat_users
    bench --site fortuna.localhost execute sas_fortuna.support.uat.check_uat_access

For the dev / UAT site only. Never run this on production: real staff get
their own users there. Safe to re-run; existing users only get missing roles.
"""

import secrets

import frappe
from frappe.utils.password import update_password

DOMAIN = "fortuna.test"


def _uat_password():
	"""Password for NEW UAT users: `uat_password` from site_config.json, else a random one.

	Never hard-coded, so no login password lives in the repository. The password used is
	returned by create_uat_users; set `uat_password` in the site config to keep it stable.
	"""
	return frappe.conf.get("uat_password") or ("Uat-" + secrets.token_urlsafe(9))


# login: (full name, roles, Helpdesk team or None). Roles follow Setup Guide step 7.
USERS = {
	"uat.agent.sw": ("UAT Software Agent", ["Agent", "Sales User"], "Software Support"),
	"uat.agent.hw": ("UAT Hardware Agent", ["Agent", "Sales User"], "Hardware Support"),
	"uat.engineer": ("UAT Service Engineer", ["Service Engineer", "Stock User"], None),
	"uat.stores": ("UAT Stores", ["Stock User"], None),
	"uat.accounts": ("UAT Accounts", ["Accounts User"], None),
	"uat.amc": ("UAT AMC Team", ["AMC Team", "Sales User"], None),
	# Manager oversees tickets and orders too, so also Agent and Sales User.
	"uat.manager": ("UAT Support Manager", ["Support Manager", "Agent", "Sales User"], None),
}


def _email(login):
	return f"{login}@{DOMAIN}"


def create_uat_users(password=None):
	password = password or _uat_password()
	done = []
	for login, (full_name, roles, team) in USERS.items():
		email = _email(login)
		if not frappe.db.exists("User", email):
			first, _, last = full_name.partition(" ")
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first,
					"last_name": last,
					"user_type": "System User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			update_password(email, password)
			done.append(f"User {email}")
		user = frappe.get_doc("User", email)
		missing = [r for r in roles if r not in {d.role for d in user.roles} and frappe.db.exists("Role", r)]
		if missing:
			user.add_roles(*missing)
			done.append(f"{email}: roles {', '.join(missing)}")

		if "Agent" in roles:
			done += _make_agent(email, full_name, team)
	frappe.db.commit()
	return {"done": done or "nothing new", "password": password}


def _make_agent(email, full_name, team):
	done = []
	if not frappe.db.exists("HD Agent", email):
		frappe.get_doc(
			{"doctype": "HD Agent", "user": email, "agent_name": full_name, "is_active": 1}
		).insert(ignore_permissions=True)
		done.append(f"HD Agent {email}")
	if team and frappe.db.exists("HD Team", team):
		doc = frappe.get_doc("HD Team", team)
		if email not in {row.user for row in doc.users}:
			doc.append("users", {"user": email})
			doc.save(ignore_permissions=True)
			done.append(f"{email} in team {team}")
	return done


# What each person must be able to do (doctype: permission types).
EXPECTED = {
	"uat.agent.sw": {
		"HD Ticket": ["read", "write"],
		"Repair Order": ["create"],
		"Quotation": ["create"],
		"Returnable Gate Pass": ["create"],
	},
	"uat.agent.hw": {
		"HD Ticket": ["read", "write"],
		"Repair Order": ["create"],
		"Quotation": ["create"],
		"Sales Order": ["create"],
	},
	"uat.engineer": {
		"Repair Order": ["read", "write"],
		"Material Request": ["create"],
		"Stock Entry": ["create"],
		"Returnable Gate Pass": ["submit"],
		"Serial No": ["read"],
	},
	"uat.stores": {
		"Stock Entry": ["create", "submit"],
		"Delivery Note": ["create", "submit"],
		"Serial No": ["read"],
	},
	"uat.accounts": {
		"Sales Invoice": ["create", "submit"],
		"Payment Entry": ["create", "submit"],
		"Subscription": ["create"],
	},
	"uat.amc": {
		"Quotation": ["create"],
		"Sales Order": ["create"],
		"Serial No": ["read"],
		"Repair Order": ["read"],
	},
	"uat.manager": {
		"Fortuna Support Settings": ["read", "write"],
		"Repair Order": ["read", "write", "delete"],
		"Returnable Gate Pass": ["cancel"],
		"HD Ticket": ["read"],
		"Serial No": ["read"],
		"Sales Order": ["read"],
		# Invoices stay with Accounts; add Accounts User if the manager must open them.
	},
}

REPORTS = {
	"uat.agent.sw": ["Serial Service History", "Returnable Items Outstanding"],
	"uat.amc": ["Warranty Ending", "Serial Service History"],
	"uat.manager": [
		"Warranty Ending",
		"Serial Service History",
		"Returnable Items Outstanding",
		"SIM Recharge Due",
	],
}


def check_uat_access():
	"""Print PASS / FAIL per user and permission, without changing anything."""
	fails = 0
	for login, needs in EXPECTED.items():
		email = _email(login)
		if not frappe.db.exists("User", email):
			print(f"MISSING  {email}: run create_uat_users first")
			fails += 1
			continue
		for doctype, ptypes in needs.items():
			for ptype in ptypes:
				ok = frappe.has_permission(doctype, ptype, user=email)
				fails += not ok
				print(f"{'PASS' if ok else 'FAIL'}  {login:14} {ptype:7} {doctype}")
		roles = set(frappe.get_roles(email))
		for report in REPORTS.get(login, []):
			allowed = {r.role for r in frappe.get_doc("Report", report).roles}
			ok = bool(roles & allowed)
			fails += not ok
			print(f"{'PASS' if ok else 'FAIL'}  {login:14} report  {report}")
	print(f"\n{fails} FAIL")
