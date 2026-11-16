"""Unit tests for the install-time Helpdesk agent reset (fortuna_impex.reset_helpdesk_agents,
called from setup/install.after_install).

Written test-first. The reset is pointed at ZZ test records only (frappe.get_all is narrowed),
so the site's real agents and teams are never touched; IntegrationTestCase rolls back the rest.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_install_agents
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.setup import fortuna_impex as fi
from sas_fortuna.setup import install

ZZ_USER = "zz.reset.agent@example.com"
ZZ_TEAM = "ZZ Reset Team"
_real_get_all = frappe.get_all


def _only_zz(doctype, *args, **kwargs):
	"""frappe.get_all, but HD Agent / HD Team lists hold only this test's records."""
	rows = _real_get_all(doctype, *args, **kwargs)
	if doctype in ("HD Agent", "HD Team"):
		return [r for r in rows if str(r if isinstance(r, str) else r.get("name")).lower().startswith("zz")]
	return rows


class TestResetHelpdeskAgents(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("User", ZZ_USER):
			frappe.get_doc(
				{"doctype": "User", "email": ZZ_USER, "first_name": "ZZ", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.get_doc("User", ZZ_USER).add_roles("Agent", "Agent Manager")
		if not frappe.db.exists("HD Agent", ZZ_USER):
			frappe.get_doc({"doctype": "HD Agent", "user": ZZ_USER, "agent_name": "ZZ Reset"}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("HD Team", ZZ_TEAM):
			frappe.get_doc({"doctype": "HD Team", "team_name": ZZ_TEAM, "users": [{"user": ZZ_USER}]}).insert(
				ignore_permissions=True
			)
		team = frappe.get_doc("HD Team", ZZ_TEAM)
		if ZZ_USER not in {m.user for m in team.users}:
			team.append("users", {"user": ZZ_USER})
			team.save(ignore_permissions=True)
		frappe.db.set_default(fi.STAFF_SYNCED_KEY, f'["{ZZ_USER}"]')

	def _reset(self, applies=True):
		with patch.object(fi, "applies", return_value=applies), patch.object(fi.frappe, "get_all", _only_zz):
			return fi.reset_helpdesk_agents()

	def test_agents_teams_and_roles_are_cleared_but_the_user_stays(self):
		done = self._reset()
		self.assertEqual(done, ["Helpdesk agents reset: 1 removed, Users kept"])
		self.assertFalse(frappe.db.exists("HD Agent", ZZ_USER))
		self.assertEqual(frappe.get_doc("HD Team", ZZ_TEAM).users, [])
		rule = frappe.db.get_value("HD Team", ZZ_TEAM, "assignment_rule")
		if rule:  # the round robin no longer hands tickets to the removed agent
			self.assertNotIn(ZZ_USER, [u.user for u in frappe.get_doc("Assignment Rule", rule).users])
		self.assertTrue(frappe.db.exists("User", ZZ_USER))
		roles = frappe.get_roles(ZZ_USER)
		self.assertNotIn("Agent", roles)
		self.assertNotIn("Agent Manager", roles)

	def test_the_staff_sheet_rebuilds_everyone_afterwards(self):
		self._reset()
		self.assertEqual(frappe.db.get_default(fi.STAFF_SYNCED_KEY), "[]")

	def test_other_companies_sites_are_left_alone(self):
		self.assertEqual(self._reset(applies=False), [])
		self.assertTrue(frappe.db.exists("HD Agent", ZZ_USER))

	def test_install_resets_before_the_setup_steps_run(self):
		calls = []
		with (
			patch.object(fi, "reset_helpdesk_agents", side_effect=lambda: calls.append("reset") or []),
			patch("sas_fortuna.hooks.after_migrate", ["frappe.utils.now"]),
			patch.object(install.frappe, "get_attr", side_effect=lambda m: lambda: calls.append(m)),
			patch.object(install.frappe.db, "commit"),  # keep the test's records out of the database
		):
			install.after_install()
		self.assertEqual(calls, ["reset", "frappe.utils.now"])

	def test_a_failing_reset_never_stops_the_install(self):
		with (
			patch.object(fi, "reset_helpdesk_agents", side_effect=RuntimeError("boom")),
			patch("sas_fortuna.hooks.after_migrate", []),
			patch.object(install.frappe.db, "commit"),
			patch.object(install.frappe.db, "rollback"),
		):
			install.after_install()  # no error raised
