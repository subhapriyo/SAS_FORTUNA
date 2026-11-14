"""Unit tests for setup/fortuna_impex.py: Fortuna Impex's go-live answers, applied on migrate.

Written test-first (TDD). Every test uses ZZ-named records or patches the module's constants,
so nothing real on the site is touched; IntegrationTestCase rolls the rest back.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_fortuna_impex_setup
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from sas_fortuna.setup import fortuna_impex as fi

ZZ_TEAM = "ZZ Impex Team"
ZZ_USER = "zz.impex.agent@example.com"


def _make_user(email, first_name="ZZ"):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	return email


# ---------------------------------------------------------------------------
# Which sites get the profile
# ---------------------------------------------------------------------------
class TestApplies(IntegrationTestCase):
	def test_site_config_switch_wins(self):
		with patch.dict(frappe.conf, {fi.SITE_CONFIG_KEY: 1}):
			self.assertTrue(fi.applies())
		with (
			patch.dict(frappe.conf, {fi.SITE_CONFIG_KEY: 0}),
			patch.object(fi, "_has_fortuna_company", return_value=True),
		):
			self.assertFalse(fi.applies())

	def test_without_switch_it_follows_the_company(self):
		conf = {k: v for k, v in frappe.conf.items() if k != fi.SITE_CONFIG_KEY}
		with patch.object(frappe, "conf", frappe._dict(conf)):
			with patch.object(fi, "_has_fortuna_company", return_value=True):
				self.assertTrue(fi.applies())
			with patch.object(fi, "_has_fortuna_company", return_value=False):
				self.assertFalse(fi.applies())

	def test_other_sites_get_nothing(self):
		with patch.object(fi, "applies", return_value=False), patch.object(fi, "STEPS", ()) as _:
			self.assertEqual(fi.execute(), [])


# ---------------------------------------------------------------------------
# Staff list (pure data)
# ---------------------------------------------------------------------------
class TestStaffList(IntegrationTestCase):
	def test_every_job_role_in_the_file_is_mapped(self):
		for person in fi.load_staff():
			self.assertIn(person.job_role, fi.JOB_ROLES, person.name)

	def test_rows_without_email_are_dropped(self):
		self.assertTrue(all(p.email for p in fi.load_staff()))

	def test_shared_email_is_one_entry_with_all_teams(self):
		# hyd.support@ is used by a software and two hardware engineers in the client sheet.
		shared = [p for p in fi.load_staff() if p.email == "hyd.support@fortunaindia.com"]
		self.assertEqual(len(shared), 1)
		self.assertEqual(set(shared[0].teams), {"Software Support", "Hardware Support"})
		self.assertTrue(shared[0].also_named)  # the other names are kept for the report

	def test_merge_unions_roles(self):
		rows = [
			{"name": "A", "email": "x@example.com", "job_role": "SW SUPPORT"},
			{"name": "B", "email": "X@example.com", "job_role": "HW SUPPORT"},
		]
		merged = fi.merge_staff(rows)
		self.assertEqual(len(merged), 1)
		self.assertIn("Service Engineer", merged[0].roles)
		self.assertTrue(merged[0].agent)
		self.assertEqual(merged[0].also_named, ["B"])


# ---------------------------------------------------------------------------
# Team sync: existing users only
# ---------------------------------------------------------------------------
class TestTeamSync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		if not frappe.db.exists("HD Team", ZZ_TEAM):
			team = frappe.get_doc({"doctype": "HD Team", "team_name": ZZ_TEAM, "users": []})
			team.flags.ignore_mandatory = True
			team.insert(ignore_permissions=True)
		self.addCleanup(self._drop_team)
		frappe.db.set_default(fi.STAFF_SYNCED_KEY, "")
		roles = dict(fi.JOB_ROLES)
		roles["ZZ HW"] = {"agent": 1, "teams": [ZZ_TEAM], "roles": ["Service Engineer"]}
		for p in (patch.object(fi, "JOB_ROLES", roles),):
			p.start()
			self.addCleanup(p.stop)

	def _drop_team(self):
		rule = frappe.db.get_value("HD Team", ZZ_TEAM, "assignment_rule")
		frappe.db.delete("HD Team Member", {"parent": ZZ_TEAM})
		frappe.db.delete("HD Team", {"name": ZZ_TEAM})
		for r in {rule, ZZ_TEAM} - {None}:
			for child in frappe.get_meta("Assignment Rule").get_table_fields():
				frappe.db.delete(child.options, {"parent": r, "parenttype": "Assignment Rule"})
			frappe.db.delete("Assignment Rule", {"name": r})

	def _staff(self, email=ZZ_USER):
		return fi.merge_staff([{"name": "ZZ Impex Agent", "email": email, "job_role": "ZZ HW"}])

	def test_existing_user_becomes_agent_team_member_with_roles(self):
		_make_user(ZZ_USER)
		with patch.object(fi, "load_staff", return_value=self._staff()):
			fi.sync_support_team()
		self.assertTrue(frappe.db.exists("HD Agent", ZZ_USER))
		self.assertIn("Service Engineer", frappe.get_roles(ZZ_USER))
		members = frappe.get_all("HD Team Member", filters={"parent": ZZ_TEAM}, pluck="user")
		self.assertIn(ZZ_USER, members)

	def test_missing_user_is_reported_not_created(self):
		email = "zz.nobody.impex@example.com"
		with patch.object(fi, "load_staff", return_value=self._staff(email)):
			done = fi.sync_support_team()
		self.assertFalse(frappe.db.exists("User", email))
		self.assertTrue(any("not found" in line and email in line for line in done))

	def test_user_found_through_employee_record(self):
		_make_user(ZZ_USER)
		with (
			patch.object(fi, "load_staff", return_value=self._staff("zz.personal@example.com")),
			patch.object(fi, "_employee_user", return_value=ZZ_USER),
		):
			fi.sync_support_team()
		self.assertTrue(frappe.db.exists("HD Agent", ZZ_USER))

	def test_admin_removal_is_respected_on_the_next_migrate(self):
		_make_user(ZZ_USER)
		with patch.object(fi, "load_staff", return_value=self._staff()):
			fi.sync_support_team()
			frappe.db.delete("HD Team Member", {"parent": ZZ_TEAM, "user": ZZ_USER})
			fi.sync_support_team()
		self.assertNotIn(ZZ_USER, frappe.get_all("HD Team Member", filters={"parent": ZZ_TEAM}, pluck="user"))


# ---------------------------------------------------------------------------
# Policy settings: once per site
# ---------------------------------------------------------------------------
class TestPolicySettings(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.db.set_default, fi.SETTINGS_FLAG, "")
		frappe.db.set_default(fi.SETTINGS_FLAG, "")

	def test_answers_are_written_to_support_settings(self):
		fi.apply_policy_settings()
		get = lambda f: frappe.db.get_single_value(fi.SETTINGS, f)  # noqa: E731
		self.assertEqual(get("payment_due_before"), "Dispatch")
		self.assertEqual(get("sim_billing_mode"), "Subscription")
		self.assertEqual(get("amc_team_email"), "subscription@fortunaindia.com")
		self.assertIn("info@fortunaindia.com", get("amc_alert_cc"))
		self.assertIn("hr@fortunaindia.com", get("sim_reminder_cc"))
		self.assertEqual(get("sim_reminder_days"), "30, 15")

	def test_later_admin_changes_are_kept(self):
		fi.apply_policy_settings()
		frappe.db.set_single_value(fi.SETTINGS, "amc_team_email", "zz@example.com")
		fi.apply_policy_settings()
		self.assertEqual(frappe.db.get_single_value(fi.SETTINGS, "amc_team_email"), "zz@example.com")


# ---------------------------------------------------------------------------
# SLA, holidays, mailbox
# ---------------------------------------------------------------------------
class TestSla(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for p in (
			patch.object(fi, "SLA_TICKET_TYPES", ("ZZ Impex Type",)),
			patch.object(fi, "SLA_NAME", "ZZ {ticket_type} SLA"),
			patch.object(fi, "HOLIDAY_LIST", "ZZ Impex Holidays"),
		):
			p.start()
			self.addCleanup(p.stop)

	def test_sla_per_ticket_type_with_response_target(self):
		fi.ensure_sla()
		sla = frappe.get_doc("HD Service Level Agreement", "ZZ ZZ Impex Type SLA")
		self.assertEqual(sla.condition, 'doc.ticket_type == "ZZ Impex Type"')
		self.assertEqual(sla.holiday_list, "ZZ Impex Holidays")
		self.assertFalse(sla.apply_sla_for_resolution)  # only the response time was given
		self.assertTrue(sla.priorities)
		self.assertTrue(all(p.response_time == fi.SLA_RESPONSE_HOURS * 3600 for p in sla.priorities))
		self.assertEqual({d.workday for d in sla.support_and_resolution}, set(fi.WORKING_DAYS))

	def test_every_priority_has_a_resolution_time(self):
		# Helpdesk computes a resolution deadline on every ticket save, even when resolution
		# is not enforced: a blank resolution time crashes ticket creation.
		fi.ensure_sla()
		sla = frappe.get_doc("HD Service Level Agreement", "ZZ ZZ Impex Type SLA")
		self.assertTrue(all(p.resolution_time == fi.SLA_RESOLUTION_HOURS * 3600 for p in sla.priorities))

	def test_a_ticket_can_be_created_under_the_sla(self):
		fi.ensure_sla()
		if not frappe.db.exists("HD Ticket Type", "ZZ Impex Type"):
			frappe.get_doc({"doctype": "HD Ticket Type", "name": "ZZ Impex Type"}).insert(
				ignore_permissions=True
			)
		ticket = frappe.get_doc(
			{
				"doctype": "HD Ticket",
				"subject": "ZZ SLA ticket",
				"description": "ZZ",
				"raised_by": "zz.sla.customer@example.com",
				"ticket_type": "ZZ Impex Type",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(ticket.sla, "ZZ ZZ Impex Type SLA")
		self.assertTrue(ticket.response_by)

	def test_existing_sla_without_resolution_time_is_repaired(self):
		fi.ensure_sla()
		frappe.db.set_value(
			"HD Service Level Priority", {"parent": "ZZ ZZ Impex Type SLA"}, "resolution_time", None
		)
		fi.ensure_sla()
		times = frappe.get_all(
			"HD Service Level Priority", filters={"parent": "ZZ ZZ Impex Type SLA"}, pluck="resolution_time"
		)
		self.assertTrue(times and all(t == fi.SLA_RESOLUTION_HOURS * 3600 for t in times))

	def test_holiday_list_has_sundays_off(self):
		fi.ensure_sla()
		holidays = frappe.get_all("HD Holiday", filters={"parent": "ZZ Impex Holidays"}, pluck="holiday_date")
		self.assertTrue(holidays)
		self.assertTrue(all(frappe.utils.getdate(d).weekday() == 6 for d in holidays))

	def test_existing_sla_is_not_overwritten(self):
		fi.ensure_sla()
		frappe.db.set_value("HD Service Level Agreement", "ZZ ZZ Impex Type SLA", "description", "edited")
		self.assertEqual(fi.ensure_sla(), [])
		self.assertEqual(
			frappe.db.get_value("HD Service Level Agreement", "ZZ ZZ Impex Type SLA", "description"), "edited"
		)


class TestMailbox(IntegrationTestCase):
	def test_mailbox_is_created_switched_off_until_the_password_is_set(self):
		with patch.dict(
			fi.MAILBOX, {"email_account_name": "ZZ Impex Mailbox", "email_id": "zz.amc@example.com"}
		):
			fi.ensure_support_mailbox()
			acc = frappe.get_doc("Email Account", "ZZ Impex Mailbox")
			self.assertEqual(acc.email_id, "zz.amc@example.com")
			self.assertFalse(acc.enable_incoming)
			self.assertEqual(fi.ensure_support_mailbox(), [])  # second run: nothing new


# ---------------------------------------------------------------------------
# Service items, prices, terms, letter head
# ---------------------------------------------------------------------------
class TestServiceItems(IntegrationTestCase):
	# Each test its own item: the class shares one transaction.
	def _run(self, code, rate=1800):
		with (
			patch.object(fi, "SERVICE_PRICES", {code: rate}),
			patch.object(fi, "SERVICE_ITEMS", {code: "998719"}),
		):
			return fi.ensure_service_items()

	def test_standard_prices(self):
		self._run("ZZ Impex Service A")
		rate = frappe.db.get_value(
			"Item Price",
			{"item_code": "ZZ Impex Service A", "price_list": fi.selling_price_list()},
			"price_list_rate",
		)
		self.assertEqual(rate, 1800)

	def test_existing_price_is_kept(self):
		with (
			patch.object(fi, "SERVICE_PRICES", {"ZZ Impex Service B": 1800}),
			patch.object(fi, "SERVICE_ITEMS", {"ZZ Impex Service B": "998719"}),
		):
			fi.ensure_service_items()
			name = frappe.db.get_value("Item Price", {"item_code": "ZZ Impex Service B"})
			frappe.db.set_value("Item Price", name, "price_list_rate", 2000)
			fi.ensure_service_items()
		self.assertEqual(frappe.db.get_value("Item Price", name, "price_list_rate"), 2000)

	def test_extended_warranty_item_carries_its_months(self):
		fi.ensure_service_items()
		self.assertEqual(
			frappe.db.get_value("Item", fi.EXTENDED_WARRANTY_ITEM, "custom_extended_warranty_months"), 12
		)


class TestTermsAndLetterHead(IntegrationTestCase):
	def test_amc_terms_come_from_the_contract(self):
		fi.ensure_terms()
		terms = frappe.db.get_value("Terms and Conditions", fi.AMC_TERMS, "terms")
		self.assertIn("48 hours", terms)
		self.assertIn("Biometric Sensor", terms)
		self.assertEqual(frappe.db.get_single_value(fi.SETTINGS, "amc_terms"), fi.AMC_TERMS)

	def test_payment_terms_template_is_full_advance(self):
		fi.ensure_terms()
		rows = frappe.get_all(
			"Payment Terms Template Detail", filters={"parent": fi.PAYMENT_TERMS}, pluck="invoice_portion"
		)
		self.assertEqual(rows, [100])

	def test_letter_head_reads_logo_and_address_from_the_company(self):
		# Nothing hard-coded: the printed document's Company supplies logo, address and contacts.
		fi.ensure_letter_head()
		html = frappe.db.get_value("Letter Head", fi.LETTER_HEAD, "content")
		self.assertIn("company_logo", html)
		self.assertNotIn("Kasba", html)

	def test_letter_head_renders_the_company_of_the_document(self):
		fi.ensure_letter_head()
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		logo = "/files/zz-impex-logo.png"
		content = frappe.db.get_value("Letter Head", fi.LETTER_HEAD, "content")
		frappe.db.set_value("Company", company, "company_logo", logo)
		html = frappe.render_template(content, {"doc": frappe._dict(company=company)})
		self.assertIn(logo, html)
		self.assertIn(company, html)


# ---------------------------------------------------------------------------
# AMC renewal alert CC
# ---------------------------------------------------------------------------
class TestAlertCc(IntegrationTestCase):
	def test_renewal_notification_gets_the_cc_row_once(self):
		name = "ZZ Impex Renewal"
		frappe.get_doc(
			{
				"doctype": "Notification",
				"name": name,
				"subject": "x",
				"document_type": "Serial No",
				"event": "Days Before",
				"date_changed": "amc_expiry_date",
				"days_in_advance": 30,
				"channel": "Email",
				"recipients": [{"receiver_by_role": "System Manager"}],
				"message": "x",
				"enabled": 0,
			}
		).insert(ignore_permissions=True)
		for field, value in (
			("amc_team_email", "subscription@fortunaindia.com"),
			("amc_alert_cc", "info@fortunaindia.com"),
		):
			old = frappe.db.get_single_value(fi.SETTINGS, field)
			frappe.db.set_single_value(fi.SETTINGS, field, value)
			self.addCleanup(frappe.db.set_single_value, fi.SETTINGS, field, old)
		with patch.object(fi, "RENEWAL_NOTIFICATION", name):
			fi.ensure_alert_cc()
			fi.ensure_alert_cc()
		cc_rows = [r.cc for r in frappe.get_doc("Notification", name).recipients if r.cc]
		self.assertEqual(len(cc_rows), 1)
		self.assertIn("subscription@fortunaindia.com", cc_rows[0])


# ---------------------------------------------------------------------------
# execute(): wiring and failure isolation
# ---------------------------------------------------------------------------
class TestExecute(IntegrationTestCase):
	def test_is_an_after_migrate_hook_between_setup_and_report(self):
		hooks = frappe.get_hooks("after_migrate")
		self.assertIn("sas_fortuna.setup.fortuna_impex.execute", hooks)
		at = hooks.index("sas_fortuna.setup.fortuna_impex.execute")
		self.assertLess(hooks.index("sas_fortuna.setup.support_desk.execute"), at)
		self.assertLess(at, hooks.index("sas_fortuna.setup.ticketing.run"))

	def test_a_failing_step_is_logged_and_the_rest_still_run(self):
		def boom():
			raise RuntimeError("boom")

		ran = []
		with (
			patch.object(fi, "applies", return_value=True),
			patch.object(fi, "STEPS", (boom, lambda: ran.append("next") or ["next done"])),
			patch("builtins.print"),
		):
			done = fi.execute()  # must not raise: a migrate is never blocked
		self.assertEqual(ran, ["next"])
		self.assertIn("next done", done)
		self.assertTrue(frappe.db.exists("Error Log", {"method": ["like", "%fortuna_impex%boom%"]}))

	def test_dates_used_by_the_holiday_list_cover_today(self):
		start, end = fi.holiday_period()
		self.assertLessEqual(start, frappe.utils.getdate(today()))
		self.assertGreater(end, frappe.utils.getdate(add_days(today(), 300)))


# ---------------------------------------------------------------------------
# Landing page (/desk/sas-fortuna): where the go-live configuration is kept
# ---------------------------------------------------------------------------
class TestLandingPage(IntegrationTestCase):
	def _links(self):
		from sas_fortuna.setup.support_desk import LANDING_SECTIONS

		return {link[2]: link for section in LANDING_SECTIONS for link in section["links"]}

	def test_configuration_is_reachable_from_the_landing_page(self):
		links = self._links()
		for target in (
			"HD Service Level Agreement",
			"HD Service Holiday List",
			"HD Team",
			"Email Account",
			"Notification",
			"Terms and Conditions",
			"Payment Terms Template",
			"Item Price",
			"Letter Head",
			"Print Format",
		):
			self.assertIn(target, links)

	def test_every_link_has_a_known_icon(self):
		from sas_fortuna.setup.landing_page import ICONS

		for label, _kind, _target, _desc, icon in self._links().values():
			self.assertIn(icon, ICONS, label)
