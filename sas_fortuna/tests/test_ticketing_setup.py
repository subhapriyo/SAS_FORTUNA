"""Unit tests for setup/ticketing.py: the prerequisites of Helpdesk ticketing.

Written test-first (TDD). Each test works on its own ZZ-named ticket type, team and status
(the module's constants are patched), and puts Team Routing and the seeded flag back as they
were. Teams are removed with plain row deletes: Helpdesk's HD Team.on_trash commits.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_ticketing_setup
"""

from unittest.mock import DEFAULT, patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.setup import ticketing as tk

SETTINGS = tk.SETTINGS
T_TYPE, T_TEAM, T_STATUS = "ZZ Test Type", "ZZ Test Team", "ZZ Paused"
FLAG = "sas_fortuna_ticketing_test_flag"


def _finding(findings, *words):
	"""The first finding whose item contains every word."""
	return next((f for f in findings if all(w in f.item for w in words)), None)


class TicketingCase(IntegrationTestCase):
	"""Empty Team Routing, unseeded flag, test-only master names; all restored afterwards."""

	patch_backfill = True

	def setUp(self):
		super().setUp()
		saved = tk._routes()
		frappe.db.delete("Fortuna Team Route", {"parent": SETTINGS})
		self.addCleanup(self._restore_routes, saved)

		patches = [
			patch.object(tk, "SEEDED_FLAG", FLAG),
			patch.object(tk, "TICKET_TYPES", {T_TYPE: "Test type"}),
			patch.object(tk, "TEAM_ROUTES", {T_TYPE: T_TEAM}),
			patch.dict(tk.PAUSED_STATUS, {"label_agent": T_STATUS}),
		]
		if self.patch_backfill:
			# Seeding tests must not create HD Customers for every customer on the site.
			patches.append(patch.object(tk, "backfill_hd_customers", return_value=[]))
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

		frappe.db.set_default(FLAG, "")
		self.addCleanup(frappe.db.set_default, FLAG, "")
		self.addCleanup(self._delete_test_masters)

	def _restore_routes(self, rows):
		frappe.db.delete("Fortuna Team Route", {"parent": SETTINGS})
		for idx, row in enumerate(rows, 1):
			tk._insert_route(row.ticket_type, row.team, idx)
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def _delete_test_masters(self):
		# The team's Assignment Rule and ALL its child rows (days, users): rows left behind
		# make the next test's rule fail with "Assignment Days have been repeated".
		rules = {frappe.db.get_value("HD Team", T_TEAM, "assignment_rule"), T_TEAM} - {None}
		frappe.db.delete("HD Team Member", {"parent": T_TEAM})
		frappe.db.delete("HD Team", {"name": T_TEAM})
		for rule in rules:
			for child in frappe.get_meta("Assignment Rule").get_table_fields():
				frappe.db.delete(child.options, {"parent": rule, "parenttype": "Assignment Rule"})
			frappe.db.delete("Assignment Rule", {"name": rule})
		frappe.db.delete("HD Ticket Type", {"name": ["in", [T_TYPE, "ZZ Other Type"]]})
		frappe.db.delete("HD Ticket Status", {"name": T_STATUS})


class TestEnsure(TicketingCase):
	def test_empty_site_gets_type_status_team_and_route(self):
		created = tk.ensure()
		self.assertTrue(frappe.db.exists("HD Ticket Type", T_TYPE))
		self.assertTrue(frappe.db.exists("HD Ticket Status", T_STATUS))
		self.assertTrue(frappe.db.exists("HD Team", T_TEAM))
		self.assertEqual([(r.ticket_type, r.team) for r in tk._routes()], [(T_TYPE, T_TEAM)])
		self.assertIn(f"Route {T_TYPE} -> {T_TEAM}", created)

	def test_portal_ticket_type_choices_are_filled_after_ensure(self):
		# The bug on prod: an empty Team Routing gives an empty Ticket Type dropdown.
		from sas_fortuna.support.portal import customer_ticket_types

		self.assertEqual(customer_ticket_types(), [])
		tk.ensure()
		self.assertEqual(customer_ticket_types(), [T_TYPE])

	def test_team_is_created_even_when_there_are_no_agents(self):
		# HD Team's member list is mandatory; a new site often has no HD Agent yet.
		with patch.object(tk, "_active_agents", return_value=[]):
			tk.ensure()
		self.assertTrue(frappe.db.exists("HD Team", T_TEAM))
		self.assertEqual(len(tk._routes()), 1)

	def test_team_gets_the_active_agents(self):
		agent = frappe.db.get_value("HD Agent", {"is_active": 1}, "name")
		if not agent:
			self.skipTest("no active HD Agent on this site")
		with patch.object(tk, "_active_agents", return_value=[agent]):
			tk.ensure()
		members = frappe.get_all("HD Team Member", filters={"parent": T_TEAM}, pluck="user")
		self.assertEqual(members, [agent])

	def test_second_run_creates_nothing(self):
		tk.ensure()
		self.assertEqual(tk.ensure(), [])
		self.assertEqual(len(tk._routes()), 1)

	def test_seeded_site_does_not_get_removed_masters_back(self):
		# After the first seed, an admin's removal is respected on later migrates.
		tk.ensure()
		frappe.db.delete("Fortuna Team Route", {"parent": SETTINGS})
		frappe.db.delete("HD Ticket Type", {"name": T_TYPE})
		tk.ensure()
		self.assertFalse(frappe.db.exists("HD Ticket Type", T_TYPE))
		self.assertEqual(tk._routes(), [])

	def test_existing_routing_is_kept_and_only_flagged(self):
		tk.ensure()
		frappe.db.set_default(FLAG, "")
		with patch.object(tk, "TEAM_ROUTES", {"ZZ Other Type": T_TEAM}):
			tk.ensure()
		self.assertEqual([r.ticket_type for r in tk._routes()], [T_TYPE])
		self.assertEqual(frappe.db.get_default(FLAG), "1")

	def test_routes_are_written_without_saving_settings(self):
		# Settings' Company is mandatory: a site that has not set it must still get its routes.
		settings_class = type(frappe.get_single(SETTINGS))
		with patch.object(settings_class, "save", side_effect=AssertionError("Settings saved")):
			tk.ensure()
		self.assertEqual(len(tk._routes()), 1)

	def test_a_failure_is_logged_and_undoes_only_this_step(self):
		marker = "sas_fortuna_ticketing_test_marker"
		frappe.db.set_default(marker, "kept")
		self.addCleanup(frappe.db.set_default, marker, "")
		with patch.object(tk, "_insert_route", side_effect=RuntimeError("boom")):
			tk.ensure()  # must not raise: a migrate is never blocked
		self.assertEqual(frappe.db.get_default(marker), "kept")  # earlier work survives
		self.assertFalse(frappe.db.exists("HD Ticket Type", T_TYPE))  # this step rolled back
		self.assertFalse(frappe.db.get_default(FLAG))  # so the next migrate tries again
		self.assertTrue(
			frappe.db.exists("Error Log", {"method": ["like", "%ticketing masters not created%"]})
		)

	def test_ensure_also_backfills_hd_customers(self):
		with patch.object(tk, "backfill_hd_customers", return_value=["HD Customer X"]) as backfill:
			created = tk.ensure()
		backfill.assert_called_once()
		self.assertIn("HD Customer X", created)

	def test_nothing_happens_without_helpdesk(self):
		with patch.object(tk, "helpdesk_installed", return_value=False):
			self.assertEqual(tk.ensure(), [])
		self.assertFalse(frappe.db.exists("HD Ticket Type", T_TYPE))


class TestHdCustomerBackfill(TicketingCase):
	patch_backfill = False

	def test_customer_without_hd_customer_gets_one(self):
		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "ZZ Backfill Co", "customer_type": "Company"}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True, ignore_permissions=True)
		# The Customer hook made one; remove it to stand for a customer from before the hook.
		frappe.db.delete("HD Customer", {"custom_erpnext_customer": customer.name})
		self.assertIn(customer.name, [c.name for c in tk.customers_without_hd_customer()])

		created = tk.backfill_hd_customers(only=[customer.name])
		hd = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": customer.name})
		self.addCleanup(frappe.db.delete, "HD Customer", {"name": hd})
		self.assertTrue(hd)
		self.assertEqual(created, [f"HD Customer {customer.name}"])
		self.assertNotIn(customer.name, [c.name for c in tk.customers_without_hd_customer()])


class TestCheck(TicketingCase):
	def test_empty_routing_is_a_failure(self):
		finding = _finding(tk.check(), "Team Routing")
		self.assertEqual(finding.status, tk.FAIL)
		self.assertTrue(finding.fix)

	def test_seeded_site_passes_routing(self):
		tk.ensure()
		findings = tk.check()
		self.assertEqual(_finding(findings, "Team Routing").status, tk.OK)
		self.assertEqual(_finding(findings, "Route", T_TYPE).status, tk.OK)
		self.assertEqual(_finding(findings, "Ticket Status", T_STATUS).status, tk.OK)

	def test_route_to_a_missing_team_is_a_failure(self):
		tk.ensure()
		tk._insert_route(T_TYPE, "ZZ Ghost Team", 2)
		self.assertEqual(_finding(tk.check(), "Route", "ZZ Ghost Team").status, tk.FAIL)

	def test_team_without_active_agent_is_a_warning(self):
		with patch.object(tk, "_active_agents", return_value=[]):
			tk.ensure()
		self.assertEqual(_finding(tk.check(), T_TEAM, "agent").status, tk.WARN)

	def test_missing_helpdesk_is_a_failure(self):
		with patch.object(tk, "helpdesk_installed", return_value=False):
			findings = tk.check()
		self.assertEqual([f.status for f in findings], [tk.FAIL])

	def test_every_finding_has_status_item_and_fix(self):
		for f in tk.check():
			self.assertIn(f.status, (tk.OK, tk.WARN, tk.FAIL))
			self.assertTrue(f.item)
			if f.status != tk.OK:
				self.assertTrue(f.fix, f.item)


class TestWiring(IntegrationTestCase):
	"""ensure() runs on every migrate, and so on install (after_install runs the after_migrate list)."""

	STEPS = (
		"_create_roles",
		"_create_stock_entry_types",
		"_create_custom_fields",
		"_add_permissions",
		"_add_report_roles",
		"_relax_opportunity_for_amc",
		"_portal_menu",
		"_helpdesk_role_for_portal_users",
		"_helpdesk_ticket_form",
	)

	def test_support_desk_setup_is_an_after_migrate_hook(self):
		self.assertIn("sas_fortuna.setup.support_desk.execute", frappe.get_hooks("after_migrate"))
		self.assertIn("sas_fortuna.setup.install.after_install", frappe.get_hooks("after_install"))

	def test_support_desk_setup_runs_ensure_last(self):
		from sas_fortuna.setup import support_desk as sd

		calls = []
		mocks = {name: DEFAULT for name in self.STEPS}
		with (
			patch.multiple(sd, **mocks) as steps,
			patch.object(tk, "ensure", side_effect=lambda: calls.append("ensure")) as ensure,
		):
			steps["_helpdesk_ticket_form"].side_effect = lambda: calls.append("ticket_form")
			sd.execute()
		ensure.assert_called_once()
		# after the custom fields and the New ticket form exist
		self.assertEqual(calls, ["ticket_form", "ensure"])

	def test_report_is_an_after_migrate_hook_right_after_the_setup(self):
		# hooks.py: the report runs after setup.support_desk.execute, so it shows the result.
		# after_install runs the same after_migrate list, so a fresh install prints it too.
		hooks = frappe.get_hooks("after_migrate")
		self.assertIn("sas_fortuna.setup.ticketing.run", hooks)
		self.assertLess(
			hooks.index("sas_fortuna.setup.support_desk.execute"),
			hooks.index("sas_fortuna.setup.ticketing.run"),
		)


class TestReport(IntegrationTestCase):
	"""run(): the check() report printed in the migrate / install log (Frappe Cloud shows it, no SSH)."""

	def _findings(self, *statuses):
		return [frappe._dict(status=s, item=f"ZZ item {i}", fix="ZZ fix") for i, s in enumerate(statuses)]

	def _report_logs(self):
		return frappe.db.count("Error Log", {"method": ["like", "%ticketing prerequisites%"]})

	def test_prints_every_finding_and_a_summary(self):
		with (
			patch.object(tk, "check", return_value=self._findings(tk.OK, tk.WARN)),
			patch("builtins.print") as printed,
		):
			tk.run()
		text = "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)
		self.assertIn("ZZ item 0", text)
		self.assertIn("ZZ item 1", text)
		self.assertIn("1 OK, 1 WARN, 0 FAIL", text)

	def test_a_failure_goes_to_the_error_log(self):
		before = self._report_logs()
		with patch.object(tk, "check", return_value=self._findings(tk.OK, tk.FAIL)), patch("builtins.print"):
			tk.run()
		self.assertEqual(self._report_logs(), before + 1)

	def test_no_error_log_without_failures(self):
		before = self._report_logs()
		with patch.object(tk, "check", return_value=self._findings(tk.OK, tk.WARN)), patch("builtins.print"):
			tk.run()
		self.assertEqual(self._report_logs(), before)

	def test_never_blocks_a_migrate(self):
		with patch.object(tk, "check", side_effect=RuntimeError("boom")), patch("builtins.print"):
			tk.run()  # must not raise
