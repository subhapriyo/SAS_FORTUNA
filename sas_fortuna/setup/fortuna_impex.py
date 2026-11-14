"""after_migrate: Fortuna Impex's go-live answers (13 Nov 2026), applied as configuration.

Runs on every `bench migrate` (and so on install, see setup/install.py), right after
setup/support_desk.py and before the ticketing report. Every step only ADDS what is missing,
so edits made later in Desk are never overwritten.

Only on Fortuna Impex sites: a Company named "Fortuna Impex ..." exists, or site_config
has "sas_fortuna_fortuna_impex": 1 (0 switches it off). Other companies' sites
(Micro Systems, FaceIT) get nothing from this file.

  Step                    Answer it carries                                      Kind
  ----------------------  -----------------------------------------------------  ------------
  apply_policy_settings   payment before dispatch, AMC/SIM e-mails, reminders    once per site
  ensure_service_items    SAC codes, Rs 1800 service / Rs 200 freight, ext. warranty  add missing
  ensure_terms            AMC terms (contract text), repair terms, 100% advance  add missing
  ensure_letter_head      letter head that reads logo + address from the Company add missing
  ensure_print_formats    AMC Quotation / Pro-Forma Invoice like Fortuna's sample add missing
  ensure_sla              48-hour response per team, working days, Sunday off    add missing
  ensure_support_mailbox  amc@fortunaindia.com (off until the password is set)   add missing
  ensure_alert_cc         CC on the AMC renewal notification                     once
  sync_support_team       existing users -> agents, teams, roles (never creates)  once per person

Open points still with Fortuna are marked "TO CONFIRM" next to the value.
Data: setup/data/fortuna_support_team.json (staff sheet), fortuna_amc_terms.html,
fortuna_repair_terms.html.  Tests: sas_fortuna/tests/test_fortuna_impex_setup.py
"""

import json
import os

import frappe
from frappe.utils import add_days, add_years, getdate, today

SETTINGS = "Fortuna Support Settings"
SITE_CONFIG_KEY = "sas_fortuna_fortuna_impex"
COMPANY_PREFIX = "Fortuna Impex"
DATA = os.path.join(os.path.dirname(__file__), "data")

# Flags (frappe defaults) that make "once" steps run once per site.
SETTINGS_FLAG = "sas_fortuna_fortuna_impex_settings_v1"
ALERT_CC_FLAG = "sas_fortuna_fortuna_impex_alert_cc_v1"
STAFF_SYNCED_KEY = "sas_fortuna_fortuna_impex_staff_synced"


# ===========================================================================
# Which sites
# ===========================================================================
def applies():
	"""Site config switch first; otherwise only sites with a Fortuna Impex company."""
	switch = frappe.conf.get(SITE_CONFIG_KEY)
	if switch is not None:
		return bool(int(switch))
	return _has_fortuna_company()


def _has_fortuna_company():
	return bool(frappe.db.exists("Company", {"company_name": ["like", f"{COMPANY_PREFIX}%"]}))


def _fortuna_companies():
	return frappe.get_all("Company", filters={"company_name": ["like", f"{COMPANY_PREFIX}%"]}, pluck="name")


# ===========================================================================
# 1. Policy answers -> Fortuna Support Settings (once: later Desk edits win)
# ===========================================================================
POLICY_SETTINGS = {
	# Paid repairs: full payment before shipment of the repaired goods.
	"payment_due_before": "Dispatch",
	# AMC repairs are free; excluded items (Item > Not Covered by AMC) are charged.
	"charge_amc_repairs": 0,
	# Replacement units: case by case, normally the original warranty is kept.
	"replacement_keeps_old_warranty": 1,
	"default_warranty_days": 365,
	# Warranty-ending and renewal alerts.
	"amc_team_email": "subscription@fortunaindia.com",
	"amc_alert_cc": "info@fortunaindia.com, amc@fortunaindia.com",
	# SIM: yearly subscription; customer reminded 30 days before, in two intervals.
	"sim_billing_mode": "Subscription",
	"sim_reminder_days": "30, 15",  # TO CONFIRM: second interval (15 days) is our reading
	"sim_reminder_cc": "info@fortunaindia.com, hr@fortunaindia.com",
}


def apply_policy_settings():
	"""Write POLICY_SETTINGS once. set_single_value, not save(): a site whose mandatory
	Company is not filled in yet must still get its answers."""
	if frappe.db.get_default(SETTINGS_FLAG):
		return []
	meta = frappe.get_meta(SETTINGS)
	for field, value in POLICY_SETTINGS.items():
		if meta.has_field(field):
			frappe.db.set_single_value(SETTINGS, field, value)
	frappe.db.set_default(SETTINGS_FLAG, "1")
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return ["Support Settings: Fortuna policy answers"]


# ===========================================================================
# 2. Service items, SAC codes and standard rates
# ===========================================================================
# Item -> SAC. 998719 is the code on Fortuna's own AMC quotation (1QTN-1906/24-25).
SERVICE_ITEMS = {
	"Repair Service Charge": "998719",
	"Freight Charges": "996511",  # TO CONFIRM with Fortuna's accountant
	"SIM Recharge": "998422",  # TO CONFIRM
	"AMC Service": "998719",
}
# Earlier placeholder SAC codes (support_desk.create_masters before 13 Nov 2026): corrected
# only while an item still carries exactly this value.
OLD_PLACEHOLDER_SAC = {"Repair Service Charge": "998713", "AMC Service": "998713"}
# Standard selling rates (Rs, before GST). AMC is 18%: TO CONFIRM whether that is the GST
# rate or the AMC price as 18% of the unit value, so no AMC rate is set here.
SERVICE_PRICES = {"Repair Service Charge": 1800, "Freight Charges": 200}  # freight: per device
# Extended warranty is a service line on the sale bill (sales.extended_warranty_months).
EXTENDED_WARRANTY_ITEM = "Extended Warranty - 1 Year"
EXTENDED_WARRANTY_MONTHS = 12
# Support Settings fields filled with these items when still blank.
SETTINGS_ITEM_FIELDS = {
	"service_charge_item": "Repair Service Charge",
	"freight_item": "Freight Charges",
	"sim_recharge_item": "SIM Recharge",
}


def selling_price_list():
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"


def ensure_service_items():
	from sas_fortuna.setup.support_desk import _ensure_hsn, ensure_service_item

	done = []
	has_sac = frappe.get_meta("Item").has_field("gst_hsn_code")  # india_compliance installed
	for code, sac in SERVICE_ITEMS.items():
		done += ensure_service_item(code, sac)
		old = OLD_PLACEHOLDER_SAC.get(code)
		if has_sac and old and frappe.db.get_value("Item", code, "gst_hsn_code") == old:
			_ensure_hsn(sac)
			frappe.db.set_value("Item", code, "gst_hsn_code", sac)
			done.append(f"Item {code}: SAC {sac}")

	done += ensure_service_item(
		EXTENDED_WARRANTY_ITEM, "998719", custom_extended_warranty_months=EXTENDED_WARRANTY_MONTHS
	)

	price_list = selling_price_list()
	if frappe.db.exists("Price List", price_list):
		for code, rate in SERVICE_PRICES.items():
			if frappe.db.exists("Item", code) and not frappe.db.exists(
				"Item Price", {"item_code": code, "price_list": price_list}
			):
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": code,
						"price_list": price_list,
						"price_list_rate": rate,
					}
				).insert(ignore_permissions=True)
				done.append(f"Price {code} = {rate}")

	for field, code in SETTINGS_ITEM_FIELDS.items():
		if frappe.db.exists("Item", code) and not frappe.db.get_single_value(SETTINGS, field):
			frappe.db.set_single_value(SETTINGS, field, code)
	return done


# ===========================================================================
# 3. Terms and payment terms
# ===========================================================================
AMC_TERMS = "Fortuna AMC Terms"
REPAIR_TERMS = "Fortuna Repair Terms"
PAYMENT_TERM = "100% Against Pro-Forma Invoice"
PAYMENT_TERMS = "100% Against Pro-Forma Invoice"
TERMS_FILES = {AMC_TERMS: "fortuna_amc_terms.html", REPAIR_TERMS: "fortuna_repair_terms.html"}
TERMS_SETTINGS = {AMC_TERMS: "amc_terms", REPAIR_TERMS: "repair_terms"}


def _read(name):
	with open(os.path.join(DATA, name)) as f:
		return f.read()


def ensure_terms():
	done = []
	for title, filename in TERMS_FILES.items():
		if not frappe.db.exists("Terms and Conditions", title):
			frappe.get_doc(
				{
					"doctype": "Terms and Conditions",
					"title": title,
					"terms": _read(filename),
					"selling": 1,
					"buying": 0,
				}
			).insert(ignore_permissions=True)
			done.append(f"Terms {title}")
		if not frappe.db.get_single_value(SETTINGS, TERMS_SETTINGS[title]):
			frappe.db.set_single_value(SETTINGS, TERMS_SETTINGS[title], title)

	if not frappe.db.exists("Payment Term", PAYMENT_TERM):
		frappe.get_doc(
			{
				"doctype": "Payment Term",
				"payment_term_name": PAYMENT_TERM,
				"invoice_portion": 100,
				"due_date_based_on": "Day(s) after invoice date",
				"credit_days": 0,
			}
		).insert(ignore_permissions=True)
		done.append(f"Payment Term {PAYMENT_TERM}")
	if not frappe.db.exists("Payment Terms Template", PAYMENT_TERMS):
		frappe.get_doc(
			{
				"doctype": "Payment Terms Template",
				"template_name": PAYMENT_TERMS,
				"terms": [
					{
						"payment_term": PAYMENT_TERM,
						"invoice_portion": 100,
						"due_date_based_on": "Day(s) after invoice date",
						"credit_days": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		done.append(f"Payment Terms Template {PAYMENT_TERMS}")
	if not frappe.db.get_single_value(SETTINGS, "payment_terms_template"):
		frappe.db.set_single_value(SETTINGS, "payment_terms_template", PAYMENT_TERMS)
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return done


# ===========================================================================
# 4. Letter head: logo and address come from the printed document's Company
# ===========================================================================
LETTER_HEAD = "Fortuna Impex"

# Rendered by Frappe with {"doc": <printed document>}. Nothing is hard-coded: change the
# logo (Company > Company Logo) or the address (Company's Address) and every print follows.
LETTER_HEAD_HTML = """\
{%- set company = doc.company or frappe.db.get_single_value("Global Defaults", "default_company") -%}
{%- set co = frappe.get_doc("Company", company) if company else None -%}
{%- set links = frappe.get_all("Dynamic Link", filters={"link_doctype": "Company", "link_name": company, "parenttype": "Address"}, pluck="parent", limit=1) if company else [] -%}
{%- set addr = frappe.get_doc("Address", links[0]) if links else None -%}
<table style="width:100%; border-bottom:2px solid #1d3b5c; margin-bottom:6px"><tr>
  <td style="width:40%; vertical-align:middle">
    {%- if co and co.company_logo %}<img src="{{ co.company_logo }}" style="max-height:85px; max-width:240px">{% endif %}
  </td>
  <td style="text-align:right; vertical-align:middle; font-size:9.5pt; color:#1d2730">
    {%- if co %}<div style="font-size:13pt; font-weight:700; color:#1d3b5c">{{ co.company_name }}</div>{% endif %}
    {%- if addr %}
    <div>{{ addr.address_line1 or "" }}{% if addr.address_line2 %}, {{ addr.address_line2 }}{% endif %}</div>
    <div>{{ addr.city or "" }}{% if addr.pincode %} - {{ addr.pincode }}{% endif %}{% if addr.state %}, {{ addr.state }}{% endif %}{% if addr.country %}, {{ addr.country }}{% endif %}</div>
    {%- endif %}
    {%- set email = (addr and addr.email_id) or (co and co.email) -%}
    {%- set phone = (addr and addr.phone) or (co and co.phone_no) -%}
    <div>{{ email or "" }}{% if email and phone %}, {% endif %}{{ phone or "" }}</div>
    {%- if addr and addr.get("gstin") %}<div>GSTIN: {{ addr.gstin }}</div>{% endif %}
  </td>
</tr></table>
"""


def ensure_letter_head():
	done = []
	if not frappe.db.exists("Letter Head", LETTER_HEAD):
		frappe.get_doc(
			{
				"doctype": "Letter Head",
				"letter_head_name": LETTER_HEAD,
				"source": "HTML",
				"content": LETTER_HEAD_HTML,
				"is_default": 0 if frappe.db.exists("Letter Head", {"is_default": 1}) else 1,
			}
		).insert(ignore_permissions=True)
		done.append(f"Letter Head {LETTER_HEAD}")
	# Fortuna's company prints on it unless someone already chose another letter head.
	for company in _fortuna_companies():
		if not frappe.db.get_value("Company", company, "default_letter_head"):
			frappe.db.set_value("Company", company, "default_letter_head", LETTER_HEAD)
			done.append(f"Company {company}: letter head")
	return done


# ===========================================================================
# 5. Print formats like Fortuna's sample (AMC quotation, pro-forma)
# ===========================================================================
def ensure_print_formats():
	from sas_fortuna.support.print_formats import create_print_formats

	return create_print_formats(only_missing=True)


# ===========================================================================
# 6. Helpdesk SLA per team
# ===========================================================================
# AMC contract: "FORTUNA would attend the call within 48 hours of call logging".
# Helpdesk counts SLA time in WORKING hours, so 48 clock hours is read as two working days
# of 8 hours. TO CONFIRM with Fortuna, together with working hours and holidays.
SLA_RESPONSE_HOURS = 16
# No resolution time was given, so resolution is not enforced (apply_sla_for_resolution = 0).
# Helpdesk still computes a "resolve by" date on every ticket save and fails on a blank
# value, so each priority carries this nominal target: 5 working days. TO CONFIRM.
SLA_RESOLUTION_HOURS = 40
SLA_TICKET_TYPES = ("Software", "Hardware", "Post-Installation")
SLA_NAME = "Fortuna {ticket_type} SLA"
WORKING_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
WORKING_HOURS = ("10:00:00", "18:00:00")  # TO CONFIRM
HOLIDAY_LIST = "Fortuna Support Holidays"
WEEKLY_OFF = "Sunday"


def holiday_period():
	"""From 1 Jan this year to 31 Dec next year; public holidays are added in Helpdesk."""
	start = getdate(today()).replace(month=1, day=1)
	return start, getdate(add_days(add_years(start, 2), -1))


def ensure_sla():
	if not frappe.db.exists("DocType", "HD Service Level Agreement"):
		return []
	done = []
	if not frappe.db.exists("HD Service Holiday List", HOLIDAY_LIST):
		start, end = holiday_period()
		holidays = frappe.get_doc(
			{
				"doctype": "HD Service Holiday List",
				"holiday_list_name": HOLIDAY_LIST,
				"from_date": start,
				"to_date": end,
				"weekly_off": WEEKLY_OFF,
				"description": "Fortuna support: Sundays off. Add public holidays here.",
			}
		)
		holidays.get_weekly_off_dates()
		holidays.insert(ignore_permissions=True)
		done.append(f"Holiday List {HOLIDAY_LIST}")

	priorities = frappe.get_all("HD Ticket Priority", filters={"disabled": 0}, pluck="name")
	for rank, ticket_type in enumerate(SLA_TICKET_TYPES, 1):
		name = SLA_NAME.format(ticket_type=ticket_type)
		if frappe.db.exists("HD Service Level Agreement", name):
			done += _fill_blank_resolution_time(name)
			continue
		frappe.get_doc(
			{
				"doctype": "HD Service Level Agreement",
				"service_level": name,
				"description": f"{ticket_type} tickets: attend within 48 hours (AMC terms).",
				"condition": f'doc.ticket_type == "{ticket_type}"',
				"rank": rank,
				"enabled": 1,
				"default_sla": 0,
				"holiday_list": HOLIDAY_LIST,
				# Only a response time was given; resolution is not measured until Fortuna sets one.
				"apply_sla_for_resolution": 0,
				"priorities": [
					{
						"priority": p,
						"response_time": SLA_RESPONSE_HOURS * 3600,
						"resolution_time": SLA_RESOLUTION_HOURS * 3600,
						"default_priority": int(p == "Medium"),
					}
					for p in priorities
				],
				"support_and_resolution": [
					{"workday": day, "start_time": WORKING_HOURS[0], "end_time": WORKING_HOURS[1]}
					for day in WORKING_DAYS
				],
			}
		).insert(ignore_permissions=True)
		done.append(f"SLA {name}")
	return done


def _fill_blank_resolution_time(sla):
	"""Repair SLAs created before 14 Nov 2026 without a resolution time (ticket saves failed).
	Only blank rows are filled; a time someone set in Helpdesk is kept."""
	rows = frappe.get_all(
		"HD Service Level Priority",
		filters={"parent": sla, "parenttype": "HD Service Level Agreement"},
		fields=["name", "resolution_time"],
	)
	blank = [r.name for r in rows if not r.resolution_time]
	for row in blank:
		frappe.db.set_value("HD Service Level Priority", row, "resolution_time", SLA_RESOLUTION_HOURS * 3600)
	return [f"SLA {sla}: resolution time on {len(blank)} priorities"] if blank else []


# ===========================================================================
# 7. Support mailbox (amc@fortunaindia.com)
# ===========================================================================
# Login details were not supplied, so the account is created switched off. To go live:
# Email Account > Fortuna AMC Support: password, mail server, then Enable Incoming.
MAILBOX = {
	"email_account_name": "Fortuna AMC Support",
	"email_id": "amc@fortunaindia.com",
	"append_to": "HD Ticket",
}


def ensure_support_mailbox():
	if frappe.db.exists("Email Account", MAILBOX["email_account_name"]) or frappe.db.exists(
		"Email Account", {"email_id": MAILBOX["email_id"]}
	):
		return []
	account = frappe.get_doc(
		{
			"doctype": "Email Account",
			**MAILBOX,
			"enable_incoming": 0,
			"enable_outgoing": 0,
			"awaiting_password": 1,
			"create_contact": 1,
		}
	)
	if not frappe.db.exists("DocType", MAILBOX["append_to"]):
		account.append_to = None
	account.insert(ignore_permissions=True)
	return [f"Email Account {MAILBOX['email_id']} (switched off until the password is set)"]


# ===========================================================================
# 8. CC on the AMC renewal notification
# ===========================================================================
RENEWAL_NOTIFICATION = "Fortuna AMC Renewal Due"


def ensure_alert_cc():
	"""Add one recipient row copying the AMC team e-mails (subscription@, info@, amc@)."""
	if not frappe.db.exists("Notification", RENEWAL_NOTIFICATION):
		return []  # created by support_desk.create_masters; checked again next migrate
	doc = frappe.get_doc("Notification", RENEWAL_NOTIFICATION)
	if any(row.cc for row in doc.recipients):
		return []
	cc = ", ".join(
		e
		for e in (
			frappe.db.get_single_value(SETTINGS, "amc_team_email"),
			frappe.db.get_single_value(SETTINGS, "amc_alert_cc"),
		)
		if e
	)
	if not cc:
		return []
	doc.append("recipients", {"cc": cc})
	doc.save(ignore_permissions=True)
	return [f"Notification {RENEWAL_NOTIFICATION}: CC {cc}"]


# ===========================================================================
# 9. Support team: existing users -> Helpdesk agents, teams and roles
# ===========================================================================
# Job Role (client sheet) -> what that person gets. Users are NEVER created: the staff
# already exist on Fortuna's sites. Anyone not found is reported and tried again next migrate.
JOB_ROLES = {
	"SW SUPPORT": {"agent": 1, "teams": ["Software Support"], "roles": []},
	"HW SUPPORT": {"agent": 1, "teams": ["Hardware Support"], "roles": ["Service Engineer"]},
	# TO CONFIRM: coordinator and AMC executive get the AMC Team role; no ticket team.
	"SUPPORT COORDINATOR": {"agent": 1, "teams": [], "roles": ["AMC Team"]},
	"AMC & CREDIT CONTROL EXECUTIVE": {"agent": 0, "teams": [], "roles": ["AMC Team"]},
	"SUPPORT MANAGER": {"agent": 1, "teams": [], "roles": ["Support Manager"]},
	# Supplier Onboarding Workflow: Approve / Reject is allowed to Purchase Manager.
	"SUPPLIER APPROVER": {"agent": 0, "teams": [], "roles": ["Purchase Manager"]},
}


def load_staff():
	with open(os.path.join(DATA, "fortuna_support_team.json")) as f:
		return merge_staff(json.load(f)["staff"])


def merge_staff(rows):
	"""One entry per e-mail (case-insensitive), first name wins. A shared mailbox used by
	several people gets every team and role of all of them; the other names are kept
	in also_named for the migrate report. Rows without e-mail are dropped."""
	merged = {}
	for row in rows:
		email = (row.get("email") or "").strip().lower()
		if not email:
			continue
		job = JOB_ROLES.get(row.get("job_role"), {})
		person = merged.get(email)
		if not person:
			person = merged[email] = frappe._dict(
				name=row.get("name"),
				email=email,
				job_role=row.get("job_role"),
				agent=0,
				teams=[],
				roles=[],
				also_named=[],
			)
		elif row.get("name") != person.name and row.get("name") not in person.also_named:
			person.also_named.append(row.get("name"))
		person.agent = person.agent or job.get("agent", 0)
		person.teams += [t for t in job.get("teams", []) if t not in person.teams]
		person.roles += [r for r in job.get("roles", []) if r not in person.roles]
	return list(merged.values())


def _employee_user(email):
	"""User linked to an Employee whose company or personal e-mail is this address."""
	if not frappe.db.exists("DocType", "Employee"):
		return None
	for field in ("company_email", "personal_email", "prefered_email"):
		if frappe.get_meta("Employee").has_field(field):
			user = frappe.db.get_value("Employee", {field: email, "user_id": ["is", "set"]}, "user_id")
			if user:
				return user
	return None


def find_user(email):
	if frappe.db.exists("User", email):
		return email
	return _employee_user(email)


def sync_support_team():
	"""Give each listed person what their job role needs, once. A person done once is not
	touched again, so removing someone from a team in Helpdesk stays removed."""
	synced = set(json.loads(frappe.db.get_default(STAFF_SYNCED_KEY) or "[]"))
	done = []
	for person in load_staff():
		if person.email in synced:
			continue
		user = find_user(person.email)
		if not user:
			done.append(f"Staff not found (no User / Employee): {person.name} <{person.email}>")
			continue
		if not frappe.db.get_value("User", user, "enabled"):
			done.append(f"Staff user disabled, skipped: {user}")
			continue
		if person.also_named:
			done.append(
				f"{user} is shared by {person.name}, {', '.join(person.also_named)}: give each their own e-mail"
			)
		done += _grant(user, person)
		synced.add(person.email)
	frappe.db.set_default(STAFF_SYNCED_KEY, json.dumps(sorted(synced)))
	return done


def _grant(user, person):
	done = []
	missing = [r for r in person.roles if frappe.db.exists("Role", r) and r not in frappe.get_roles(user)]
	if missing:
		frappe.get_doc("User", user).add_roles(*missing)
		done.append(f"{user}: roles {', '.join(missing)}")
	if person.agent and frappe.db.exists("DocType", "HD Agent") and not frappe.db.exists("HD Agent", user):
		frappe.get_doc(
			{"doctype": "HD Agent", "user": user, "agent_name": person.name, "is_active": 1}
		).insert(ignore_permissions=True)
		done.append(f"{user}: Helpdesk agent")
	for team in person.teams:
		if not frappe.db.exists("HD Team", team):
			done.append(f"{user}: team {team} missing")
			continue
		doc = frappe.get_doc("HD Team", team)
		if user not in {m.user for m in doc.users}:
			doc.append("users", {"user": user})
			doc.save(ignore_permissions=True)
			done.append(f"{user}: team {team}")
	return done


# ===========================================================================
# execute(): after_migrate entry point
# ===========================================================================
STEPS = (
	apply_policy_settings,
	ensure_service_items,
	ensure_terms,
	ensure_letter_head,
	ensure_print_formats,
	ensure_sla,
	ensure_support_mailbox,
	ensure_alert_cc,
	sync_support_team,
)


def execute():
	"""Run every step; one failing step is rolled back to its savepoint and logged, the
	rest still run, and the migrate is never blocked. Prints what changed."""
	if not applies():
		return []
	done = []
	for step in STEPS:
		name = getattr(step, "__name__", "step")
		frappe.db.savepoint("sf_fortuna_impex")
		try:
			done += step() or []
		except Exception:
			frappe.db.rollback(save_point="sf_fortuna_impex")
			frappe.log_error(title=f"sas_fortuna fortuna_impex: {name} failed")
	if done:
		print("\nsas_fortuna Fortuna Impex setup")
		for line in done:
			print(f"  {line}")
	return done
