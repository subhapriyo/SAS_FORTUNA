"""Prerequisites of the Helpdesk ticketing: check them, and create what is safe to create.

	ensure()  after_migrate (and so after_install), via setup/support_desk.py execute():
	            1. Ticket Types, the Paused status, the Teams and Team Routing - ONCE per site
	            2. an HD Customer for every ERPNext Customer that has none - every migrate
	check()   read-only list of findings (OK / WARN / FAIL, each with its fix)
	run()     prints check():   bench --site <site> execute sas_fortuna.setup.ticketing.run
	seed()    first-time seeding again, by hand (commits):
	            bench --site <site> execute sas_fortuna.setup.ticketing.seed

Why: the portal's Ticket Type choices come from Team Routing (support/portal.py,
customer_ticket_types). A site where nobody created the masters shows an empty dropdown,
and its tickets get no team and no agent.

Rules:
  - Seeded once: after the first run a flag is set, so a type, team or route an admin
    removes later is never added back by a migrate. A site whose routing is already
    filled is only flagged.
  - Never blocks a migrate: a failure is rolled back to a savepoint (this step only),
    logged, and tried again on the next migrate.
  - Routing rows are written as child rows: saving the whole Settings would fail on a
    site whose mandatory Company is not set yet.
  - A Team is created even with no agent yet (Helpdesk makes its member list mandatory):
    tickets then still get a team, and check() warns until agents are added.

Tests: sas_fortuna/tests/test_ticketing_setup.py
"""

import frappe

SETTINGS = "Fortuna Support Settings"
SEEDED_FLAG = "sas_fortuna_ticketing_masters_seeded"
SAVEPOINT = "sf_ticketing_seed"

TICKET_TYPES = {
	"Software": "Software / firmware problems, settings, updates.",
	"Hardware": "Faulty units, parts and repairs.",
	"Post-Installation": "Questions and issues just after installation.",
}
# Team per ticket type. Post-Installation goes to Hardware until Fortuna decides.
TEAM_ROUTES = {
	"Software": "Software Support",
	"Hardware": "Hardware Support",
	"Post-Installation": "Hardware Support",
}
# SLA timer stops while waiting on customer, spares or payment; the customer sees "On Hold".
PAUSED_STATUS = {
	"doctype": "HD Ticket Status",
	"label_agent": "Paused",
	"label_customer": "On Hold",
	"different_view": 1,
	"category": "Paused",
	"color": "Orange",
	"order": 3,
	"enabled": 1,
}

OK, WARN, FAIL = "OK", "WARN", "FAIL"


def helpdesk_installed():
	return bool(frappe.db.exists("DocType", "HD Ticket"))


# ---------------------------------------------------------------------------
# ensure(): create
# ---------------------------------------------------------------------------
def ensure():
	"""Create what the ticketing needs; return what was created (empty when nothing)."""
	if not helpdesk_installed():
		return []
	return _seed_masters_once() + backfill_hd_customers()


def _seed_masters_once():
	if frappe.db.get_default(SEEDED_FLAG):
		return []
	frappe.db.savepoint(SAVEPOINT)
	try:
		done = []
		if not _routes():
			done += create_masters()
			for idx, (ticket_type, team) in enumerate(TEAM_ROUTES.items(), 1):
				_insert_route(ticket_type, team, idx)
				done.append(f"Route {ticket_type} -> {team}")
			frappe.clear_document_cache(SETTINGS, SETTINGS)
		frappe.db.set_default(SEEDED_FLAG, "1")
		return done
	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.log_error(title="sas_fortuna: ticketing masters not created")
		return []


def create_masters():
	"""Ticket Types, the Paused status and the Teams, each only if missing.
	Also used by setup.support_desk.create_masters."""
	done = []
	for name, description in TICKET_TYPES.items():
		if not frappe.db.exists("HD Ticket Type", name):
			doc = frappe.new_doc("HD Ticket Type")
			doc.name = name
			doc.description = description
			doc.insert(set_name=name, ignore_permissions=True)
			done.append(f"Ticket Type {name}")

	if frappe.db.exists("DocType", "HD Ticket Status") and not frappe.db.exists(
		"HD Ticket Status", PAUSED_STATUS["label_agent"]
	):
		frappe.get_doc(dict(PAUSED_STATUS)).insert(ignore_permissions=True)
		done.append(f"Ticket Status {PAUSED_STATUS['label_agent']}")

	# Helpdesk adds a round-robin Assignment Rule to each new team.
	agents = _active_agents()
	for team in sorted(set(TEAM_ROUTES.values())):
		if frappe.db.exists("HD Team", team):
			continue
		doc = frappe.get_doc(
			{"doctype": "HD Team", "team_name": team, "users": [{"user": a} for a in agents]}
		)
		doc.flags.ignore_mandatory = True  # members are mandatory; a new site may have no agent yet
		doc.insert(ignore_permissions=True)
		done.append(f"Team {team}")
	return done


def _active_agents():
	return frappe.get_all("HD Agent", filters={"is_active": 1}, pluck="name")


def _routes():
	return frappe.get_all(
		"Fortuna Team Route",
		filters={"parent": SETTINGS, "parenttype": SETTINGS, "parentfield": "team_routing"},
		fields=["ticket_type", "team"],
		order_by="idx asc",
	)


def _insert_route(ticket_type, team, idx):
	frappe.get_doc(
		{
			"doctype": "Fortuna Team Route",
			"parent": SETTINGS,
			"parenttype": SETTINGS,
			"parentfield": "team_routing",
			"idx": idx,
			"ticket_type": ticket_type,
			"team": team,
		}
	).db_insert()


def customers_without_hd_customer():
	"""Enabled ERPNext Customers with no linked HD Customer: their tickets would not reach
	the customer's portal."""
	if not frappe.get_meta("HD Customer").has_field("custom_erpnext_customer"):
		return []
	return frappe.db.sql(
		"""select c.name, c.customer_name from `tabCustomer` c
		left join `tabHD Customer` h on h.custom_erpnext_customer = c.name
		where c.disabled = 0 and h.name is null""",
		as_dict=True,
	)


def backfill_hd_customers(only=None):
	"""Create the missing HD Customers (all of them, or only the Customers named in `only`)."""
	from sas_fortuna.support.customer_sync import ensure_hd_customer

	done = []
	frappe.db.savepoint("sf_hd_customer_backfill")
	try:
		for c in customers_without_hd_customer():
			if only is not None and c.name not in only:
				continue
			ensure_hd_customer(c.name, c.customer_name)
			done.append(f"HD Customer {c.name}")
	except Exception:
		frappe.db.rollback(save_point="sf_hd_customer_backfill")
		frappe.log_error(title="sas_fortuna: HD Customer backfill failed")
		return []
	return done


def seed():
	"""Run the first-time seeding again (clears the flag), then commit.
	bench execute does not commit by itself."""
	frappe.db.set_default(SEEDED_FLAG, "")
	done = ensure()
	frappe.db.commit()
	print("\n".join(done) or "nothing new")


# ---------------------------------------------------------------------------
# check(): read-only
# ---------------------------------------------------------------------------
def check():
	"""Every prerequisite as frappe._dict(status, item, fix)."""
	findings = []

	def add(status, item, fix=""):
		findings.append(frappe._dict(status=status, item=item, fix=fix))

	if not helpdesk_installed():
		add(FAIL, "Helpdesk app installed", "Install the helpdesk app on this site, then bench migrate")
		return findings

	seed_fix = "Fortuna Support Settings > Team Routing, or: bench --site <site> execute sas_fortuna.setup.ticketing.seed"
	routes = _routes()
	if routes:
		add(OK, f"Team Routing has {len(routes)} rows")
	else:
		add(FAIL, "Team Routing has rows (portal Ticket Type list is empty without them)", seed_fix)

	teams = set()
	for r in routes:
		problems = []
		if not frappe.db.exists("HD Ticket Type", r.ticket_type):
			problems.append(f"Ticket Type {r.ticket_type} missing")
		if frappe.db.exists("HD Team", r.team):
			teams.add(r.team)
		else:
			problems.append(f"Team {r.team} missing")
		item = f"Route {r.ticket_type} -> {r.team}"
		if problems:
			add(
				FAIL,
				f"{item}: {', '.join(problems)}",
				"Create it in Helpdesk, or fix the row in Team Routing",
			)
		else:
			add(OK, item)

	active = set(_active_agents())
	has_rule = frappe.get_meta("HD Team").has_field("assignment_rule")
	for team in sorted(teams):
		members = set(frappe.get_all("HD Team Member", filters={"parent": team}, pluck="user"))
		if members & active:
			add(OK, f"Team {team} has an active agent")
		else:
			add(
				WARN,
				f"Team {team} has no active agent: its tickets stay unassigned",
				f"Helpdesk > Teams > {team}: add agents",
			)
		if has_rule:
			rule = frappe.db.get_value("HD Team", team, "assignment_rule")
			if rule and not frappe.db.get_value("Assignment Rule", rule, "disabled"):
				add(OK, f"Team {team} assignment rule {rule} enabled")
			else:
				add(
					WARN,
					f"Team {team} has no enabled assignment rule",
					f"Open Helpdesk > Teams > {team} and save it",
				)

	status = PAUSED_STATUS["label_agent"]
	if frappe.db.exists("HD Ticket Status", status):
		add(OK, f"Ticket Status {status}")
	else:
		add(WARN, f"Ticket Status {status} missing (SLA cannot pause)", seed_fix)

	_check_ticket_form(add)

	if frappe.db.exists("Custom Field", {"dt": "HD Ticket", "fieldname": "custom_serial_no"}):
		add(OK, "HD Ticket custom fields (Product & Warranty)")
	else:
		add(FAIL, "HD Ticket custom fields (Product & Warranty) missing", "bench migrate")

	if frappe.db.exists("Role", "HD Customer"):
		add(OK, "Role HD Customer (portal users can raise and reply)")
	else:
		add(FAIL, "Role HD Customer missing", "Helpdesk not fully installed: bench migrate")

	menu = frappe.get_all(
		"Portal Menu Item",
		filters={"parent": "Portal Settings", "route": "/tickets", "enabled": 1},
		pluck="name",
	)
	if menu:
		add(OK, "Portal menu Tickets enabled")
	else:
		add(WARN, "Portal menu Tickets not enabled", "Portal Settings > Custom Menu: enable Tickets")

	missing = customers_without_hd_customer()
	if missing:
		add(WARN, f"{len(missing)} Customers have no HD Customer", "bench migrate (backfills them)")
	else:
		add(OK, "Every Customer has an HD Customer")

	if frappe.db.exists("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}):
		add(OK, "Default outgoing Email Account (replies reach customers)")
	else:
		add(
			WARN,
			"No default outgoing Email Account: replies are not e-mailed",
			"Email Account: set one as Default Outgoing",
		)
	if frappe.db.exists("Email Account", {"enable_incoming": 1, "default_incoming": 1}):
		add(OK, "Incoming support mailbox (e-mail becomes a ticket)")
	else:
		add(
			WARN,
			"No incoming support mailbox: customers cannot raise tickets by e-mail",
			"Email Account: enable incoming for the support address",
		)
	return findings


def _check_ticket_form(add):
	"""Ticket Type + Serial No on Helpdesk's Default template, i.e. the portal's New ticket form."""
	from sas_fortuna.setup.support_desk import TICKET_FORM_FIELDS

	if not frappe.db.exists("HD Ticket Template", "Default"):
		add(FAIL, "HD Ticket Template Default missing", "Helpdesk not fully installed: bench migrate")
		return
	have = {
		r.fieldname: r.url_method
		for r in frappe.get_all(
			"HD Ticket Template Field", filters={"parent": "Default"}, fields=["fieldname", "url_method"]
		)
	}
	for field in TICKET_FORM_FIELDS:
		name = field["fieldname"]
		if have.get(name) == field["url_method"]:
			add(OK, f"New ticket form field {name}")
		else:
			add(FAIL, f"New ticket form field {name} missing or without its choices", "bench migrate")


def run():
	"""Print check(). Read-only."""
	findings = check()
	for f in findings:
		print(f"[{f.status:4}] {f.item}" + (f"\n         fix: {f.fix}" if f.fix else ""))
	counts = {s: sum(f.status == s for f in findings) for s in (OK, WARN, FAIL)}
	print(f"\n{counts[OK]} OK, {counts[WARN]} WARN, {counts[FAIL]} FAIL")
