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
  sync_support_team       staff sheet -> agents, teams, roles (Users: opt-in)   once per person
  grant_agent_manager     Helpdesk Agent Manager role for SUPPORT MANAGER rows   once per site
  seed_job_locations_once Kolkata, Mumbai, Bhubaneswar ... and what they serve;  once per site
                          each linked to the Company carrying its invoice key
  sync_job_location_teams staff location -> agent's Job Location, location team  once per person
  fill_blank_job_locations  engineers / tickets with no Job Location -> Kolkata    once per site
                          (a ticket: its customer's address first)
  enable_assign_within_team  Helpdesk's "assign within team" setting on           once per site
  ensure_kb_articles      FAQ articles customers see while raising a ticket      add missing
  ensure_ticket_subject_form  Subject dropdown + form script on New Ticket       add missing; script follows its file
  ensure_ticket_subjects  starter subjects per ticket type (Ticket Subject list) types without any
  sync_subject_options    Subject dropdown's choices = the Ticket Subject list   every migrate
  ensure_ticket_actions_script  Repair Order + Coverage buttons on the ticket page  script follows its file
  ensure_acknowledgement_email  "we've received your ticket" e-mail text + on      text if blank; on once

Open points still with Fortuna are marked "TO CONFIRM" next to the value.
Data: setup/data/fortuna_amc_terms.html,
fortuna_repair_terms.html, fortuna_kb_articles.json (FAQ articles), fortuna_ticket_subjects.json
(starter subjects), fortuna_new_ticket_form.js (New Ticket form script), fortuna_ticket_actions.js
(ticket page buttons), fortuna_ticket_acknowledgement.html (new-ticket e-mail), fortuna_job_locations.json (branches).
Tests: sas_fortuna/tests/test_fortuna_impex_setup.py, test_ticket_subject.py,
test_ticket_acknowledgement.py, test_install_agents.py, test_job_location.py
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
AGENT_MANAGER_FLAG = "sas_fortuna_fortuna_impex_agent_manager_v1"
STAFF_LOCATION_KEY = "sas_fortuna_fortuna_impex_staff_location_synced"
ASSIGN_WITHIN_TEAM_FLAG = "sas_fortuna_fortuna_impex_assign_within_team_v1"
JOB_LOCATIONS_FLAG = "sas_fortuna_fortuna_impex_job_locations_v1"
JOB_LOCATION_BACKFILL_FLAG = "sas_fortuna_fortuna_impex_job_location_backfill_v1"
# site_config switch: 1 lets sync_support_team create missing staff Users (off by default).
CREATE_USERS_KEY = "sas_fortuna_create_staff_users"
# Set once per Fortuna site by patches/v16_0/fortuna_staff_and_job_locations: user creation on.
# An explicit site_config value (0 or 1) still wins.
CREATE_USERS_FLAG = "sas_fortuna_fortuna_impex_create_staff_users_v1"


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
# 9. Support team: staff sheet -> Users, Helpdesk agents, teams and roles
# ===========================================================================
# Fortuna (16 Nov 2026): SW SUPPORT -> Software Support, HW SUPPORT -> Hardware Support, the
# teams setup/ticketing.py seeds and routes the Software / Hardware ticket types to.
SOFTWARE_TEAM = "Software Support"
HARDWARE_TEAM = "Hardware Support"

# Job Role (client sheet) -> what that person gets. A staff member with no User yet is only
# reported, unless site_config CREATE_USERS_KEY is 1: then they get a User (no welcome
# e-mail, no password: they use Forgot Password).
JOB_ROLES = {
	"SW SUPPORT": {"agent": 1, "teams": [SOFTWARE_TEAM], "roles": []},
	"HW SUPPORT": {"agent": 1, "teams": [HARDWARE_TEAM], "roles": ["Service Engineer"]},
	# TO CONFIRM: coordinator and AMC executive get the AMC Team role; no ticket team.
	"SUPPORT COORDINATOR": {"agent": 1, "teams": [], "roles": ["AMC Team"]},
	"AMC & CREDIT CONTROL EXECUTIVE": {"agent": 0, "teams": [], "roles": ["AMC Team"]},
	# Agent Manager: Helpdesk's manager role (agent and team admin, settings, dashboards).
	# Not a team member, so the round robin does not hand them tickets. Note: with Helpdesk
	# Settings > "Restrict tickets by Team" on, the role does not lift the restriction.
	"SUPPORT MANAGER": {"agent": 1, "teams": [], "roles": ["Support Manager", "Agent Manager"]},
	# Supplier Onboarding Workflow: Approve / Reject is allowed to Purchase Manager.
	"SUPPLIER APPROVER": {"agent": 0, "teams": [], "roles": ["Purchase Manager"]},
}


# The staff sheet holds personal data (names, mobiles, private e-mails), so it is not kept
# in git. Put Fortuna's sheet on each site at  sites/<site>/private/sas_fortuna/
# fortuna_support_team.json  (same format as before); without it the staff step does nothing.
STAFF_FILE = "fortuna_support_team.json"


def staff_file():
	return frappe.get_site_path("private", "sas_fortuna", STAFF_FILE)


def load_staff():
	path = staff_file()
	if not os.path.exists(path):
		return []
	with open(path) as f:
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
				location=row.get("location"),  # sheet's "Job Location" text, e.g. Fortuna Kolkata
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


def create_users_enabled():
	"""site_config CREATE_USERS_KEY when set (0 or 1), else on once the staff patch has run.
	A staff member who already has a User (same e-mail, or via Employee) is never duplicated."""
	switch = frappe.conf.get(CREATE_USERS_KEY)
	if switch is not None:
		return bool(int(switch))
	return bool(_flag_set(CREATE_USERS_FLAG))


def create_staff_user(person):
	"""Desk (System) User for a staff member: no welcome e-mail and no password, so nothing
	reaches the person until an admin sends a password reset (or they use Forgot Password)."""
	first, _, last = (person.name or person.email).title().partition(" ")
	frappe.get_doc(
		{
			"doctype": "User",
			"email": person.email,
			"first_name": first,
			"last_name": last,
			"user_type": "System User",
			"send_welcome_email": 0,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return person.email


def sync_support_team():
	"""Give each listed person what their job role needs, once. A person done once is not
	touched again, so removing someone from a team in Helpdesk stays removed."""
	staff = load_staff()
	if not staff:
		return [f"Staff sheet not on this site (private/sas_fortuna/{STAFF_FILE}): staff not linked"]
	synced = set(json.loads(frappe.db.get_default(STAFF_SYNCED_KEY) or "[]"))
	done = []
	for person in staff:
		if person.email in synced:
			continue
		user = find_user(person.email)
		if not user and create_users_enabled():
			user = create_staff_user(person)
			done.append(f"{user}: User created ({person.name}, no welcome e-mail)")
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


def grant_agent_manager():
	"""Once per site: Agent Manager for SUPPORT MANAGER people already synced before that role
	was in JOB_ROLES (sync_support_team does each person only once). Existing Users only."""
	if frappe.db.get_default(AGENT_MANAGER_FLAG) or not frappe.db.exists("Role", "Agent Manager"):
		return []
	done = []
	for person in load_staff():
		if "Agent Manager" not in person.roles:
			continue
		user = find_user(person.email)
		if user and "Agent Manager" not in frappe.get_roles(user):
			frappe.get_doc("User", user).add_roles("Agent Manager")
			done.append(f"{user}: role Agent Manager")
	frappe.db.set_default(AGENT_MANAGER_FLAG, "1")
	return done


# ===========================================================================
# 9b. Job Locations and location teams (Ticket Type + Job Location -> team -> assignee)
# ===========================================================================
JOB_LOCATIONS_FILE = "fortuna_job_locations.json"


def load_job_locations():
	with open(os.path.join(DATA, JOB_LOCATIONS_FILE)) as f:
		return json.load(f)["locations"]


def ensure_job_locations(rows=None):
	"""Add each shipped Job Location that is missing; one that exists (edited or not) is left alone.
	A location whose Invoice Prefix Key belongs to a Company on this site is linked to it."""
	if not frappe.db.exists("DocType", "Job Location"):
		return []
	from sas_fortuna.sas_fortuna.doctype.job_location.job_location import PREFIX_FIELD, prefix_keys

	has_key = frappe.get_meta("Company").has_field(PREFIX_FIELD)
	done = []
	for row in load_job_locations() if rows is None else rows:
		if frappe.db.exists("Job Location", row["location_name"]):
			continue
		keys = prefix_keys(row.get("invoice_prefix_key"))
		key = ", ".join(keys) or None
		# Only a Company that really carries one of these keys on this site ("on if exists").
		company = frappe.db.get_value("Company", {PREFIX_FIELD: ["in", keys]}) if has_key and keys else None
		doc = frappe.get_doc({"doctype": "Job Location", **row, "company": company})
		doc.insert(ignore_permissions=True)
		if doc.company != company:
			# Frappe filled the blank link with the user's default company (and validate took its
			# key): a branch is not that company, so put back what the data says.
			doc.db_set({"company": company, "invoice_prefix_key": key})
		done.append(f"Job Location {row['location_name']}")
	return done


def link_job_locations_by_key(names):
	"""Each named Job Location -> the Company carrying one of its Invoice Prefix Keys, or no
	Company when none does (Bhubaneswar's BBSR is not Fortuna Impex's FI). Keys are kept."""
	from sas_fortuna.sas_fortuna.doctype.job_location.job_location import PREFIX_FIELD, prefix_keys

	if not frappe.get_meta("Company").has_field(PREFIX_FIELD):
		return []
	done = []
	for name in names:
		row = frappe.db.get_value("Job Location", name, ["company", "invoice_prefix_key"], as_dict=True)
		if not row:
			continue
		keys = prefix_keys(row.invoice_prefix_key)
		company = frappe.db.get_value("Company", {PREFIX_FIELD: ["in", keys]}) if keys else None
		if (row.company or None) != company:
			frappe.db.set_value("Job Location", name, "company", company)
			done.append(f"Job Location {name}: {company or 'no company'}")
	return done


def seed_job_locations_once():
	"""Once per site: add the shipped Job Locations that are missing, then link each shipped one to
	its Company by invoice key. Later migrates leave them alone (edit or delete them in Desk)."""
	# The flag is read from the table, not the defaults cache, so a second call sees the first.
	if not frappe.db.exists("DocType", "Job Location") or _flag_set(JOB_LOCATIONS_FLAG):
		return []
	rows = load_job_locations()
	done = ensure_job_locations(rows)
	done += link_job_locations_by_key([row["location_name"] for row in rows])
	frappe.db.set_default(JOB_LOCATIONS_FLAG, "1")
	return done


def _flag_set(key):
	"""A once-per-site flag, read from the table rather than the defaults cache."""
	return frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": key}, "defvalue")


def _blank_location_rows(doctype):
	fields = ["name", "custom_job_location"]
	if doctype == "HD Ticket":
		fields.append("custom_erpnext_customer")
	return frappe.get_all(doctype, filters={"custom_job_location": ["is", "not set"]}, fields=fields)


def _location_for_ticket(ticket):
	from sas_fortuna.sas_fortuna.doctype.job_location.job_location import (
		default_location,
		location_for_customer,
	)

	customer = ticket.get("custom_erpnext_customer")
	return (customer and location_for_customer(customer)) or default_location()


def _save_location(doctype, name, location):
	# Field only: no save hooks, so a ticket's team and assignee stay as they are.
	frappe.db.set_value(doctype, name, "custom_job_location", location, update_modified=False)


def fill_blank_job_locations():
	"""Once per site: engineers and tickets made before Job Locations (or before the Kolkata
	default) get one: an engineer the default, a ticket its customer's address, else the default.
	Runs after the staff sheet has placed its people. Waits while the default location is absent."""
	from sas_fortuna.sas_fortuna.doctype.job_location.job_location import default_location

	if not frappe.db.exists("DocType", "Job Location") or _flag_set(JOB_LOCATION_BACKFILL_FLAG):
		return []
	default = default_location()
	if not default:
		return []
	done = []
	for agent in _blank_location_rows("HD Agent"):
		if not agent.custom_job_location:
			_save_location("HD Agent", agent.name, default)
			done.append(f"{agent.name}: Job Location {default}")
	for ticket in _blank_location_rows("HD Ticket"):
		location = None if ticket.custom_job_location else _location_for_ticket(ticket)
		if location:
			_save_location("HD Ticket", ticket.name, location)
			done.append(f"Ticket {ticket.name}: Job Location {location}")
	frappe.db.set_default(JOB_LOCATION_BACKFILL_FLAG, "1")
	return done


def location_team(base_team, job_location):
	return f"{base_team} - {job_location}"


def sync_job_location_teams():
	"""Once per person: their Job Location (from the sheet's location) on the HD Agent, and
	membership of the location team of each of their teams, e.g. Hardware Support - Mumbai.
	The team and its Team Routing rows (same ticket types as the base team) are created when
	missing. Someone without a User / agent yet is tried again next migrate."""
	if not frappe.db.exists("DocType", "Job Location"):
		return []
	from sas_fortuna.sas_fortuna.doctype.job_location.job_location import (
		default_location,
		location_from_text,
	)

	synced = set(json.loads(frappe.db.get_default(STAFF_LOCATION_KEY) or "[]"))
	done = []
	for person in load_staff():
		if person.email in synced or not person.agent:
			continue
		location = location_from_text(person.location)
		user = find_user(person.email)
		if not location or not user or not frappe.db.exists("HD Agent", user):
			continue  # nothing to place, or not an agent yet: next migrate
		# Blank, or the default a new HD Agent gets on insert: the sheet's place wins (once).
		current = frappe.db.get_value("HD Agent", user, "custom_job_location")
		if current != location and (not current or current == default_location()):
			frappe.db.set_value("HD Agent", user, "custom_job_location", location)
			done.append(f"{user}: Job Location {location}")
		for base in person.teams:
			done += _join_location_team(user, base, location)
		synced.add(person.email)
	frappe.db.set_default(STAFF_LOCATION_KEY, json.dumps(sorted(synced)))
	return done


def _join_location_team(user, base, location):
	"""User into '<base> - <location>' (created when missing), plus its routing rows."""
	from sas_fortuna.setup import ticketing

	done = []
	name = location_team(base, location)
	if frappe.db.exists("HD Team", name):
		team = frappe.get_doc("HD Team", name)
		if user not in {m.user for m in team.users}:
			team.append("users", {"user": user})
			team.save(ignore_permissions=True)
			done.append(f"{user}: team {name}")
	else:
		# Helpdesk adds the team's round-robin Assignment Rule on insert.
		frappe.get_doc({"doctype": "HD Team", "team_name": name, "users": [{"user": user}]}).insert(
			ignore_permissions=True
		)
		done.append(f"Team {name} ({user})")
	routes = ticketing._routes()
	for ticket_type in [r.ticket_type for r in routes if r.team == base and not r.job_location]:
		if not any(r.ticket_type == ticket_type and r.job_location == location for r in routes):
			ticketing._insert_route(ticket_type, name, len(routes) + 1, job_location=location)
			routes = ticketing._routes()
			done.append(f"Route {ticket_type} at {location} -> {name}")
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return done


def enable_assign_within_team():
	"""Once per site: Helpdesk > Settings > "Restrict agent assignment to selected team" on.
	Note: the Helpdesk version in use (Nov 2026) shows this setting but its Assignee dropdown does
	not read it; the list is narrowed by support/agent_filter.py. Kept on for when Helpdesk does.
	An admin may switch it off again; it is not switched back on."""
	if frappe.db.get_default(ASSIGN_WITHIN_TEAM_FLAG) or not frappe.get_meta("HD Settings").has_field(
		"assign_within_team"
	):
		return []
	frappe.db.set_single_value("HD Settings", "assign_within_team", 1)
	frappe.db.set_default(ASSIGN_WITHIN_TEAM_FLAG, "1")
	return ["Helpdesk: agent assignment limited to the ticket's team"]


AGENT_ROLES = ("Agent", "Agent Manager")


def reset_helpdesk_agents():
	"""Install only (setup/install.py): start Helpdesk's agents from a clean slate, so agents a
	restored or copied database brings along do not carry over. Removes every HD Agent, every
	team membership and the Agent / Agent Manager roles; the User logins stay. The staff sheet
	then rebuilds them (sync_support_team runs again for everyone)."""
	if not applies() or not frappe.db.exists("DocType", "HD Agent"):
		return []
	agents = frappe.get_all("HD Agent", pluck="name")
	for team in frappe.get_all("HD Team", fields=["name", "assignment_rule"]):
		# Helpdesk will not save a team without members, so clear the rows directly: the
		# team's members and the users of its assignment rule (round robin). The staff sheet
		# adds members back with a normal save.
		frappe.db.delete("HD Team Member", {"parenttype": "HD Team", "parent": team.name})
		if team.assignment_rule:
			for field in ("users", "weighted_users"):
				df = frappe.get_meta("Assignment Rule").get_field(field)
				if df and df.options:
					frappe.db.delete(
						df.options, {"parenttype": "Assignment Rule", "parent": team.assignment_rule}
					)
	for agent in agents:
		frappe.delete_doc("HD Agent", agent, ignore_permissions=True, force=True)
	for user in agents:
		if user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
			continue
		roles = [r for r in AGENT_ROLES if r in frappe.get_roles(user)]
		if roles:
			frappe.get_doc("User", user).remove_roles(*roles)
	frappe.db.set_default(STAFF_SYNCED_KEY, "[]")
	return [f"Helpdesk agents reset: {len(agents)} removed, Users kept"]


# ===========================================================================
# 10. FAQ articles for the customer portal (add missing)
# ===========================================================================
# While a customer types a ticket subject, Helpdesk suggests published Knowledge Base
# articles. Without any, the panel only ever says "No answers found".
KB_FILE = "fortuna_kb_articles.json"


def load_kb():
	with open(os.path.join(DATA, KB_FILE)) as f:
		return json.load(f)["categories"]


def ensure_kb_articles(categories=None):
	"""Publish each FAQ article whose title is not on the site yet. An existing article (any
	status) is left alone, so wording changed or archived in Helpdesk stays that way."""
	if not frappe.db.exists("DocType", "HD Article"):
		return []
	done = []
	for cat in load_kb() if categories is None else categories:
		category = None
		for article in cat["articles"]:
			if frappe.db.exists("HD Article", {"title": article["title"]}):
				continue
			category = category or _kb_category(cat)
			frappe.get_doc(
				{
					"doctype": "HD Article",
					"title": article["title"],
					"category": category,
					"content": article["content"],
					"status": "Published",
				}
			).insert(ignore_permissions=True)
			done.append(f"Knowledge Base: {article['title']}")
	if done:
		_rebuild_kb_index()
	return done


def _kb_category(cat):
	name = frappe.db.get_value("HD Article Category", {"category_name": cat["name"]})
	if name:
		return name
	doc = frappe.get_doc(
		{
			"doctype": "HD Article Category",
			"category_name": cat["name"],
			"description": cat.get("description"),
		}
	)
	return doc.insert(ignore_permissions=True).name


def _rebuild_kb_index():
	"""Customers search a Redis index that Helpdesk refreshes only on its own schedule, so
	rebuild it now. Not fatal: a site whose Redis lacks the search module still migrates."""
	try:
		from helpdesk.search import HelpdeskSearch

		HelpdeskSearch().build_index()
	except Exception:
		frappe.log_error(title="sas_fortuna fortuna_impex: Knowledge Base search index not rebuilt")


# ===========================================================================
# 11. Subject dropdown on the New Ticket form (Ticket Subject list)
# ===========================================================================
# The customer picks a subject from a list kept per Ticket Type (Desk > Ticket Subject), or
# "Others" and types their own. Helpdesk's Subject box is a plain text box, so a Select field
# carries the choice and a Helpdesk Form Script (setup/data/fortuna_new_ticket_form.js) fills
# its choices, fills/hides the text box and highlights the description.
SUBJECT_FIELD = "custom_issue_subject"
SUBJECT_LABEL = "Issue Subject"
FORM_SCRIPT = "Fortuna New Ticket Form"
FORM_SCRIPT_FILE = "fortuna_new_ticket_form.js"
TICKET_SUBJECTS_FILE = "fortuna_ticket_subjects.json"
SUBJECT_CUSTOM_FIELD = {
	"fieldname": SUBJECT_FIELD,
	# Not "Subject": HD Ticket's own subject field has that label, and Data Import maps file
	# columns by label, so two "Subject" fields sent legacy ticket titles into this dropdown.
	"label": SUBJECT_LABEL,
	"fieldtype": "Select",
	"insert_after": "custom_serial_no",
	# No options here on purpose: they change with the ticket type (Ticket Subject list).
	"description": "Picked on the New Ticket form; Others means the customer typed the subject.",
}
SUBJECT_TEMPLATE_ROW = {
	"fieldname": SUBJECT_FIELD,
	"required": 1,
	"placeholder": "Choose the closest subject",
}


def form_script_source():
	return _read(FORM_SCRIPT_FILE)


def ensure_ticket_subject_form():
	"""Field, its place on the Default ticket template, the form script, and the Subjects
	section on each Ticket Type. The script is code: it follows the file on every migrate."""
	if not frappe.db.exists("DocType", "HD Ticket"):
		return []
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	done = []
	if not frappe.db.exists("Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}):
		create_custom_fields({"HD Ticket": [SUBJECT_CUSTOM_FIELD]}, update=False)
		done.append("HD Ticket: Subject dropdown field")
	elif (
		frappe.db.get_value("Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}, "label")
		== "Subject"
	):
		# Sites made before the rename: only the old default label is changed, never an admin's own.
		frappe.db.set_value(
			"Custom Field", {"dt": "HD Ticket", "fieldname": SUBJECT_FIELD}, "label", SUBJECT_LABEL
		)
		frappe.clear_cache(doctype="HD Ticket")
		done.append(f"HD Ticket: Subject dropdown relabelled {SUBJECT_LABEL}")
	done += _subject_on_ticket_template()
	done += _subject_form_script()
	if not frappe.db.exists(
		"DocType Link", {"parent": "HD Ticket Type", "link_doctype": "Ticket Subject", "custom": 1}
	):
		frappe.get_doc(
			{
				"doctype": "DocType Link",
				"parent": "HD Ticket Type",
				"parenttype": "DocType",
				"parentfield": "links",
				"link_doctype": "Ticket Subject",
				"link_fieldname": "ticket_type",
				"group": "Subjects",
				"custom": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="HD Ticket Type")
		done.append("Ticket Type: Subjects section")
	return done


# Fortuna's order on the New Ticket form: Ticket Type, Serial No, Subject, then the description.
SUBJECT_AFTER = ("custom_serial_no", "ticket_type")


def _subject_on_ticket_template():
	"""Add the dropdown after Serial No (or Ticket Type) on the Default template, once (the
	admin may move or change it later)."""
	if not frappe.db.exists("HD Ticket Template", "Default"):
		return []
	template = frappe.get_doc("HD Ticket Template", "Default")
	if any(row.fieldname == SUBJECT_FIELD for row in template.fields):
		return []
	row = template.append("fields", SUBJECT_TEMPLATE_ROW)
	have = [r.fieldname for r in template.fields]
	anchor = next((f for f in SUBJECT_AFTER if f in have), None)
	after = have.index(anchor) if anchor else None
	if after is not None:
		template.fields.remove(row)
		template.fields.insert(after + 1, row)
		for i, r in enumerate(template.fields, 1):
			r.idx = i
	template.save(ignore_permissions=True)
	return ["New Ticket form: Subject dropdown"]


def _subject_form_script():
	# New Ticket page; Helpdesk loads new-page scripts for agents and customers alike from
	# apply_to_customer_portal being 0.
	return _sync_form_script(FORM_SCRIPT, form_script_source(), apply_on_new_page=1)


def _sync_form_script(name, source, apply_on_new_page):
	"""Create or update an HD Ticket Helpdesk Form Script so it matches its file in the app.
	The script is code, kept in git: it follows the file on every migrate."""
	wanted = {
		"dt": "HD Ticket",
		"apply_to": "Form",
		"enabled": 1,
		"apply_on_new_page": apply_on_new_page,
		"apply_to_customer_portal": 0,
		"script": source,
	}
	if not frappe.db.exists("HD Form Script", name):
		frappe.get_doc({"doctype": "HD Form Script", "name": name, **wanted}).insert(ignore_permissions=True)
		return ["Helpdesk Form Script: " + name]
	doc = frappe.get_doc("HD Form Script", name)
	if all(doc.get(k) == v for k, v in wanted.items()):
		return []
	doc.update(wanted)
	doc.save(ignore_permissions=True)
	return ["Helpdesk Form Script: " + name + " updated"]


# Agent's ticket page (/helpdesk/tickets/<id>): "Create Repair Order" / "Repair Order ..." and a
# read-only Coverage dropdown (Support Type, Warranty End, AMC Expiry, Repair Status). Kept off
# the sidebar because Helpdesk's sidebar ignores read-only and would let agents edit them.
TICKET_ACTIONS_SCRIPT = "Fortuna Ticket Actions"
TICKET_ACTIONS_FILE = "fortuna_ticket_actions.js"


def ticket_actions_source():
	return _read(TICKET_ACTIONS_FILE)


def ensure_ticket_actions_script():
	if not frappe.db.exists("DocType", "HD Form Script"):
		return []
	return _sync_form_script(TICKET_ACTIONS_SCRIPT, ticket_actions_source(), apply_on_new_page=0)


def load_ticket_subjects():
	with open(os.path.join(DATA, TICKET_SUBJECTS_FILE)) as f:
		return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def ensure_ticket_subjects():
	"""Starter subjects, only for a ticket type that has none yet: after that the Ticket Subject
	list is the master, and a subject removed there stays removed."""
	done = []
	for ticket_type, subjects in load_ticket_subjects().items():
		if not frappe.db.exists("HD Ticket Type", ticket_type):
			continue
		if frappe.db.exists("Ticket Subject", {"ticket_type": ticket_type}):
			continue
		for order, subject in enumerate(subjects, 1):
			frappe.get_doc(
				{
					"doctype": "Ticket Subject",
					"subject": subject,
					"ticket_type": ticket_type,
					"is_active": 1,
					"sort_order": order * 10,
				}
			).insert(ignore_permissions=True)
		done.append(f"Ticket Subjects: {len(subjects)} for {ticket_type}")
	return done


def sync_subject_options():
	"""Subject dropdown's choices = the Ticket Subject list (kept in step on every Ticket Subject
	save too), so the agent's ticket sidebar can show the chosen subject."""
	from sas_fortuna.sas_fortuna.doctype.ticket_subject.ticket_subject import sync_subject_options as sync

	return sync()


# ===========================================================================
# 12. "We've received your ticket" e-mail (Helpdesk's Acknowledgement setting)
# ===========================================================================
# The text is kept in Helpdesk (Settings > Email Notifications > Acknowledgement), where Fortuna
# can edit it; support/hd_ticket.py sends it for portal tickets as well as e-mailed ones.
ACK_FILE = "fortuna_ticket_acknowledgement.html"
ACK_FLAG = "sas_fortuna_fortuna_impex_ack_email_v1"


def acknowledgement_template():
	return _read(ACK_FILE)


def ensure_acknowledgement_email():
	"""Fortuna's wording when the Helpdesk text is still blank, and the e-mail switched on once;
	a later edit or switch-off in Helpdesk is kept."""
	if not frappe.db.exists("DocType", "HD Settings"):
		return []
	done = []
	if not (frappe.db.get_single_value("HD Settings", "acknowledgement_email_content") or "").strip():
		frappe.db.set_single_value("HD Settings", "acknowledgement_email_content", acknowledgement_template())
		done.append("Helpdesk: new-ticket acknowledgement e-mail text")
	if not frappe.db.get_default(ACK_FLAG):
		frappe.db.set_single_value("HD Settings", "send_acknowledgement_email", 1)
		frappe.db.set_default(ACK_FLAG, "1")
		done.append("Helpdesk: new-ticket acknowledgement e-mail switched on")
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
	grant_agent_manager,
	seed_job_locations_once,
	sync_job_location_teams,  # after the agents exist
	fill_blank_job_locations,  # after the staff sheet has placed its people
	enable_assign_within_team,
	ensure_kb_articles,
	ensure_ticket_subject_form,
	ensure_ticket_subjects,
	sync_subject_options,
	ensure_ticket_actions_script,
	ensure_acknowledgement_email,
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
