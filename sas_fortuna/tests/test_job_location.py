"""Unit tests: Job Location (where an engineer works) and ticket routing by Ticket Type + Job Location.

  Master ......... sas_fortuna/sas_fortuna/doctype/job_location (tidy lists, prefix key, no overlaps)
  Matching ....... customer address -> Job Location: city first, then state
  Routing ........ support/hd_ticket.py: location team when it has an active agent, else the
                   ticket type's own team; follows a changed type/location, keeps a hand-picked team
  Settings ....... one Team Routing row per Ticket Type + Job Location
  Seeding ........ setup/fortuna_impex.py: locations from the data file, location teams from staff

Written test-first. ZZ-named records only; IntegrationTestCase rolls them back.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_job_location
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.sas_fortuna.doctype.job_location import job_location as jl
from sas_fortuna.support import hd_ticket

ZZ_TYPE = "ZZ JL Type"
ZZ_BASE = "ZZ JL Support"


def _location(name, cities="", states="", active=1, **extra):
	if frappe.db.exists("Job Location", name):
		frappe.delete_doc("Job Location", name, force=True)
	return frappe.get_doc(
		{
			"doctype": "Job Location",
			"location_name": name,
			"cities": cities,
			"states": states,
			"is_active": active,
			**extra,
		}
	).insert(ignore_permissions=True)


def _row(ticket_type, team, job_location=None):
	return frappe._dict(ticket_type=ticket_type, team=team, job_location=job_location)


class FakeTicket(frappe._dict):
	"""Enough of an HD Ticket for route_to_team: fields listed in _changed count as changed."""

	def has_value_changed(self, fieldname):
		return fieldname in (self.get("_changed") or ())


# ---------------------------------------------------------------------------
# Master
# ---------------------------------------------------------------------------
class TestJobLocationMaster(IntegrationTestCase):
	def test_lists_are_tidied_one_per_line(self):
		loc = _location("ZZ JL Tidy", cities=" Pune ,pune\n\n Nashik", states="Goa, ")
		self.assertEqual(loc.cities, "Pune\nNashik")
		self.assertEqual(loc.states, "Goa")

	def test_prefix_key_is_tidied(self):
		self.assertEqual(_location("ZZ JL Key", invoice_prefix_key=" bbsr ").invoice_prefix_key, "BBSR")

	def test_a_location_may_carry_several_prefix_keys(self):
		# Kolkata bills as FI (1FI series) and KOLK (2FI series).
		loc = _location("ZZ JL Two Keys", invoice_prefix_key=" fi ,kolk\nFI")
		self.assertEqual(loc.invoice_prefix_key, "FI, KOLK")
		self.assertEqual(jl.prefix_keys(loc.invoice_prefix_key), ["FI", "KOLK"])

	def test_prefix_key_comes_from_the_company_when_blank(self):
		if not frappe.get_meta("Company").has_field(jl.PREFIX_FIELD):
			self.skipTest("fortuna_erp's Invoice Prefix Key is not on this site")
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", company, jl.PREFIX_FIELD, "zzk")
		self.assertEqual(_location("ZZ JL From Co", company=company).invoice_prefix_key, "ZZK")

	def test_a_city_or_state_on_two_active_locations_is_refused(self):
		_location("ZZ JL One", cities="Zzcity", states="Zzstate")
		with self.assertRaises(frappe.ValidationError):
			_location("ZZ JL Two", cities="zzcity")
		with self.assertRaises(frappe.ValidationError):
			_location("ZZ JL Three", states="ZZSTATE")
		_location("ZZ JL Off", cities="Zzcity", active=0)  # an inactive one may repeat it


# ---------------------------------------------------------------------------
# Matching an address
# ---------------------------------------------------------------------------
class TestMatching(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		_location("ZZ JL Bigcity", cities="Zzbig", states="Zzland")
		_location("ZZ JL Smalltown", cities="Zzsmall")
		_location("ZZ JL Retired", cities="Zzold", active=0)

	def test_city_wins_over_state(self):
		# Zzsmall lies in Zzland, but has a location of its own (Nagpur vs Maharashtra).
		self.assertEqual(jl.match_location(city="zzsmall", state="Zzland"), "ZZ JL Smalltown")

	def test_state_when_the_city_is_unknown(self):
		self.assertEqual(jl.match_location(city="Elsewhere", state=" zzland "), "ZZ JL Bigcity")

	def test_inactive_and_unknown_give_nothing(self):
		self.assertIsNone(jl.match_location(city="Zzold"))
		self.assertIsNone(jl.match_location(city="Nowhere", state="Noland"))
		self.assertIsNone(jl.match_location())

	def test_staff_sheet_text_names_a_location(self):
		self.assertEqual(jl.location_from_text("Fortuna ZZ JL Bigcity office"), "ZZ JL Bigcity")
		self.assertIsNone(jl.location_from_text("Somewhere else"))
		self.assertIsNone(jl.location_from_text(None))

	def test_customer_location_from_its_address(self):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "ZZ JL Customer",
				"customer_group": frappe.get_all(
					"Customer Group", filters={"is_group": 0}, pluck="name", limit=1
				)[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "ZZ JL",
				"address_type": "Billing",
				"address_line1": "1 Zz Road",
				"city": "Zzsmall",
				"state": "West Bengal",  # India Compliance requires one; the city decides here
				"country": frappe.db.get_default("country") or "India",
				"links": [{"link_doctype": "Customer", "link_name": customer.name}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(jl.location_for_customer(customer.name), "ZZ JL Smalltown")
		self.assertIsNone(jl.location_for_customer(None))


# ---------------------------------------------------------------------------
# Routing: Ticket Type + Job Location -> Team
# ---------------------------------------------------------------------------
ROUTES = [
	_row(ZZ_TYPE, ZZ_BASE),
	_row(ZZ_TYPE, f"{ZZ_BASE} - Zzbig", "ZZ JL Bigcity"),
	_row(ZZ_TYPE, f"{ZZ_BASE} - Empty", "ZZ JL Smalltown"),
]


def _staffed(team):
	return not team.endswith("Empty")


class TestRouting(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for p in (
			patch.object(hd_ticket, "has_active_agent", side_effect=_staffed),
			patch.object(hd_ticket, "get_settings", return_value=frappe._dict(team_routing=ROUTES)),
		):
			p.start()
			self.addCleanup(p.stop)

	def test_location_team_for_type_and_location(self):
		self.assertEqual(hd_ticket.team_for(ZZ_TYPE, "ZZ JL Bigcity", ROUTES), f"{ZZ_BASE} - Zzbig")

	def test_type_team_without_location_or_without_staff(self):
		self.assertEqual(hd_ticket.team_for(ZZ_TYPE, None, ROUTES), ZZ_BASE)
		self.assertEqual(hd_ticket.team_for(ZZ_TYPE, "ZZ JL Smalltown", ROUTES), ZZ_BASE)  # nobody there
		self.assertEqual(hd_ticket.team_for(ZZ_TYPE, "ZZ JL Unrouted", ROUTES), ZZ_BASE)
		self.assertIsNone(hd_ticket.team_for("ZZ JL Other Type", None, ROUTES))

	def test_new_ticket_gets_its_location_team(self):
		doc = FakeTicket(ticket_type=ZZ_TYPE, custom_job_location="ZZ JL Bigcity")
		hd_ticket.route_to_team(doc)
		self.assertEqual(doc.agent_group, f"{ZZ_BASE} - Zzbig")

	def test_team_follows_a_changed_location(self):
		doc = FakeTicket(
			ticket_type=ZZ_TYPE,
			custom_job_location="ZZ JL Bigcity",
			agent_group=ZZ_BASE,
			_changed=("custom_job_location",),
		)
		hd_ticket.route_to_team(doc)
		self.assertEqual(doc.agent_group, f"{ZZ_BASE} - Zzbig")

	def test_a_hand_picked_team_is_kept(self):
		doc = FakeTicket(
			ticket_type=ZZ_TYPE,
			custom_job_location="ZZ JL Bigcity",
			agent_group="ZZ Hand Picked",
			_changed=("custom_job_location",),
		)
		hd_ticket.route_to_team(doc)
		self.assertEqual(doc.agent_group, "ZZ Hand Picked")

	def test_nothing_changed_leaves_the_team(self):
		doc = FakeTicket(ticket_type=ZZ_TYPE, custom_job_location="ZZ JL Bigcity", agent_group=ZZ_BASE)
		hd_ticket.route_to_team(doc)
		self.assertEqual(doc.agent_group, ZZ_BASE)

	def test_location_comes_from_the_customer_when_blank(self):
		doc = FakeTicket(custom_erpnext_customer="ZZ Any")
		with patch.object(hd_ticket, "location_for_customer", return_value="ZZ JL Bigcity"):
			hd_ticket.apply_job_location(doc)
		self.assertEqual(doc.custom_job_location, "ZZ JL Bigcity")
		chosen = FakeTicket(custom_erpnext_customer="ZZ Any", custom_job_location="ZZ Chosen")
		hd_ticket.apply_job_location(chosen)
		self.assertEqual(chosen.custom_job_location, "ZZ Chosen")

	def test_unknown_address_gets_the_default_location(self):
		doc = FakeTicket(custom_erpnext_customer="ZZ Any")
		with (
			patch.object(hd_ticket, "location_for_customer", return_value=None),
			patch.object(hd_ticket, "default_location", return_value="ZZ JL Default"),
		):
			hd_ticket.apply_job_location(doc)
		self.assertEqual(doc.custom_job_location, "ZZ JL Default")

	def test_ticket_without_customer_gets_the_default_location(self):
		doc = FakeTicket()
		with patch.object(hd_ticket, "default_location", return_value="ZZ JL Default"):
			hd_ticket.apply_job_location(doc)
		self.assertEqual(doc.custom_job_location, "ZZ JL Default")

	def test_a_matched_address_wins_over_the_default(self):
		doc = FakeTicket(custom_erpnext_customer="ZZ Any")
		with (
			patch.object(hd_ticket, "location_for_customer", return_value="ZZ JL Bigcity"),
			patch.object(hd_ticket, "default_location", return_value="ZZ JL Default"),
		):
			hd_ticket.apply_job_location(doc)
		self.assertEqual(doc.custom_job_location, "ZZ JL Bigcity")


class TestDefaultLocation(IntegrationTestCase):
	"""Kolkata is the default Job Location for tickets and engineers, when it exists and is active."""

	def setUp(self):
		super().setUp()
		self.shipped_default = jl.DEFAULT_LOCATION
		p = patch.object(jl, "DEFAULT_LOCATION", "ZZ JL Home")
		p.start()
		self.addCleanup(p.stop)

	def test_default_is_kolkata(self):
		self.assertEqual(self.shipped_default, "Kolkata")

	def test_default_when_it_exists_and_is_active(self):
		if not frappe.db.exists("Job Location", "ZZ JL Home"):
			self.assertIsNone(jl.default_location())
		_location("ZZ JL Home", cities="Zzhome")
		frappe.db.set_value("Job Location", "ZZ JL Home", "is_active", 1)
		self.assertEqual(jl.default_location(), "ZZ JL Home")
		frappe.db.set_value("Job Location", "ZZ JL Home", "is_active", 0)
		self.assertIsNone(jl.default_location())

	def test_new_engineer_gets_the_default(self):
		_location("ZZ JL Home", cities="Zzhome")
		frappe.db.set_value("Job Location", "ZZ JL Home", "is_active", 1)
		agent = frappe._dict(custom_job_location=None)
		jl.fill_default_location(agent)
		self.assertEqual(agent.custom_job_location, "ZZ JL Home")

	def test_engineer_with_a_location_keeps_it(self):
		_location("ZZ JL Home", cities="Zzhome")
		agent = frappe._dict(custom_job_location="ZZ Elsewhere")
		jl.fill_default_location(agent)
		self.assertEqual(agent.custom_job_location, "ZZ Elsewhere")

	def test_hd_agent_insert_is_wired(self):
		from sas_fortuna.support import wiring

		self.assertEqual(
			wiring.doc_events["HD Agent"]["before_insert"],
			"sas_fortuna.sas_fortuna.doctype.job_location.job_location.fill_default_location",
		)


class TestHasActiveAgent(IntegrationTestCase):
	def test_team_without_members_has_no_active_agent(self):
		team = frappe.get_doc({"doctype": "HD Team", "team_name": "ZZ JL Nobody", "users": []})
		team.flags.ignore_mandatory = True
		team.insert(ignore_permissions=True)
		self.assertFalse(hd_ticket.has_active_agent("ZZ JL Nobody"))
		self.assertFalse(hd_ticket.has_active_agent("ZZ JL No Such Team"))


# ---------------------------------------------------------------------------
# Settings and the portal
# ---------------------------------------------------------------------------
class TestSettingsAndPortal(IntegrationTestCase):
	def test_one_row_per_type_and_location(self):
		from sas_fortuna.sas_fortuna.doctype.fortuna_support_settings.fortuna_support_settings import (
			FortunaSupportSettings,
		)

		check = FortunaSupportSettings._check_unique_routes
		check(frappe._dict(team_routing=[_row("A", "T"), _row("A", "T2", "L1"), _row("A", "T3", "L2")]))
		with self.assertRaises(frappe.ValidationError):
			check(frappe._dict(team_routing=[_row("A", "T", "L1"), _row("A", "T2", "L1")]))
		with self.assertRaises(frappe.ValidationError):
			check(frappe._dict(team_routing=[_row("A", "T"), _row("A", "T2")]))

	def test_portal_lists_each_ticket_type_once(self):
		from sas_fortuna.support import portal

		routes = [_row("A", "T"), _row("A", "T2", "L1"), _row("B", "T")]
		with patch("sas_fortuna.support.utils.get_settings", return_value=frappe._dict(team_routing=routes)):
			self.assertEqual(portal.customer_ticket_types(), ["A", "B"])


# ---------------------------------------------------------------------------
# Seeding on Fortuna Impex sites (setup/fortuna_impex.py)
# ---------------------------------------------------------------------------
class TestSeedLocations(IntegrationTestCase):
	def test_missing_locations_are_added_and_edits_kept(self):
		from sas_fortuna.setup import fortuna_impex as fi

		rows = [{"location_name": "ZZ JL Seeded", "cities": "Zzseed", "states": ""}]
		self.assertEqual(fi.ensure_job_locations(rows), ["Job Location ZZ JL Seeded"])
		frappe.db.set_value("Job Location", "ZZ JL Seeded", "cities", "Zzedited")
		self.assertEqual(fi.ensure_job_locations(rows), [])
		self.assertEqual(frappe.db.get_value("Job Location", "ZZ JL Seeded", "cities"), "Zzedited")

	def test_seeded_location_gets_no_default_company(self):
		# Frappe fills a blank Company link with the user's default company on insert; a seeded
		# branch must not then claim that company (or its invoice prefix key).
		from sas_fortuna.setup import fortuna_impex as fi

		fi.ensure_job_locations(
			[{"location_name": "ZZ JL No Co", "invoice_prefix_key": "", "cities": "Zznoco"}]
		)
		fi.ensure_job_locations(
			[{"location_name": "ZZ JL Own Key", "invoice_prefix_key": "ZZOWN", "cities": "Zzown"}]
		)
		self.assertEqual(
			frappe.db.get_value("Job Location", "ZZ JL No Co", ["company", "invoice_prefix_key"]),
			(None, None),
		)
		self.assertEqual(
			frappe.db.get_value("Job Location", "ZZ JL Own Key", ["company", "invoice_prefix_key"]),
			(None, "ZZOWN"),
		)

	def test_seeded_location_links_the_company_with_its_key(self):
		from sas_fortuna.setup import fortuna_impex as fi

		if not frappe.get_meta("Company").has_field(jl.PREFIX_FIELD):
			self.skipTest("fortuna_erp's Invoice Prefix Key is not on this site")
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", company, jl.PREFIX_FIELD, "ZZCO")
		fi.ensure_job_locations(
			[{"location_name": "ZZ JL With Co", "invoice_prefix_key": "zzco", "cities": "Zzwithco"}]
		)
		self.assertEqual(frappe.db.get_value("Job Location", "ZZ JL With Co", "company"), company)

	def test_several_keys_link_the_company_carrying_any_of_them(self):
		from sas_fortuna.setup import fortuna_impex as fi

		if not frappe.get_meta("Company").has_field(jl.PREFIX_FIELD):
			self.skipTest("fortuna_erp's Invoice Prefix Key is not on this site")
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", company, jl.PREFIX_FIELD, "ZZCO")
		fi.ensure_job_locations(
			[{"location_name": "ZZ JL Many", "invoice_prefix_key": "ZZNONE, zzco", "cities": "Zzmany"}]
		)
		self.assertEqual(
			frappe.db.get_value("Job Location", "ZZ JL Many", ["company", "invoice_prefix_key"]),
			(company, "ZZNONE, ZZCO"),
		)

	def test_link_by_key_sets_the_company_carrying_the_key(self):
		# An existing location (company blank) gets the Company whose Invoice Prefix Key it lists.
		from sas_fortuna.setup import fortuna_impex as fi

		if not frappe.get_meta("Company").has_field(jl.PREFIX_FIELD):
			self.skipTest("fortuna_erp's Invoice Prefix Key is not on this site")
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", company, jl.PREFIX_FIELD, "ZZCO")
		_location("ZZ JL Link", cities="Zzlink")
		frappe.db.set_value("Job Location", "ZZ JL Link", {"company": None, "invoice_prefix_key": "ZZCO"})

		self.assertEqual(
			fi.link_job_locations_by_key(["ZZ JL Link"]), ["Job Location ZZ JL Link: " + company]
		)
		self.assertEqual(frappe.db.get_value("Job Location", "ZZ JL Link", "company"), company)

	def test_link_by_key_clears_a_company_whose_key_is_not_listed(self):
		# Bhubaneswar (BBSR) was linked to Fortuna Impex (key FI): no company carries BBSR,
		# so the link goes; the location's own key stays.
		from sas_fortuna.setup import fortuna_impex as fi

		if not frappe.get_meta("Company").has_field(jl.PREFIX_FIELD):
			self.skipTest("fortuna_erp's Invoice Prefix Key is not on this site")
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", company, jl.PREFIX_FIELD, "ZZCO")
		_location("ZZ JL Unlink", cities="Zzunlink")
		frappe.db.set_value(
			"Job Location", "ZZ JL Unlink", {"company": company, "invoice_prefix_key": "ZZOTHER"}
		)

		self.assertEqual(
			fi.link_job_locations_by_key(["ZZ JL Unlink"]), ["Job Location ZZ JL Unlink: no company"]
		)
		self.assertEqual(
			frappe.db.get_value("Job Location", "ZZ JL Unlink", ["company", "invoice_prefix_key"]),
			(None, "ZZOTHER"),
		)

	def test_link_by_key_leaves_a_correct_link_alone(self):
		from sas_fortuna.setup import fortuna_impex as fi

		if not frappe.get_meta("Company").has_field(jl.PREFIX_FIELD):
			self.skipTest("fortuna_erp's Invoice Prefix Key is not on this site")
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", company, jl.PREFIX_FIELD, "ZZCO")
		_location("ZZ JL Fine", cities="Zzfine")
		frappe.db.set_value("Job Location", "ZZ JL Fine", {"company": company, "invoice_prefix_key": "ZZCO"})

		self.assertEqual(fi.link_job_locations_by_key(["ZZ JL Fine"]), [])

	def test_seeding_runs_once_per_site(self):
		# After the one run, a deleted location is not added back by later migrates.
		from sas_fortuna.setup import fortuna_impex as fi

		rows = [{"location_name": "ZZ JL Once", "cities": "Zzonce", "states": ""}]
		frappe.db.set_default(fi.JOB_LOCATIONS_FLAG, "")
		with patch.object(fi, "load_job_locations", return_value=rows):
			first = fi.seed_job_locations_once()
			self.assertIn("Job Location ZZ JL Once", first)
			frappe.delete_doc("Job Location", "ZZ JL Once", ignore_permissions=True)
			self.assertEqual(fi.seed_job_locations_once(), [])
		self.assertFalse(frappe.db.exists("Job Location", "ZZ JL Once"))

	def test_seed_step_replaces_the_every_migrate_step(self):
		from sas_fortuna.setup import fortuna_impex as fi

		self.assertIn(fi.seed_job_locations_once, fi.STEPS)
		self.assertNotIn(fi.ensure_job_locations, fi.STEPS)

	def test_kolkata_ships_with_fi_and_kolk(self):
		from sas_fortuna.setup import fortuna_impex as fi

		kolkata = next(r for r in fi.load_job_locations() if r["location_name"] == "Kolkata")
		self.assertEqual(jl.prefix_keys(kolkata["invoice_prefix_key"]), ["FI", "KOLK"])

	def test_shipped_locations_cover_the_staff_sheet(self):
		from sas_fortuna.setup import fortuna_impex as fi

		names = {row["location_name"] for row in fi.load_job_locations()}
		self.assertTrue({"Kolkata", "Mumbai", "Bhubaneswar", "Hyderabad", "Bihar", "Nagpur"} <= names)


class TestLocationTeams(IntegrationTestCase):
	USER = "zz.jl.agent@example.com"
	BASE = "ZZ JL Base Team"
	TEAM = "ZZ JL Base Team - ZZ JL Place"

	def setUp(self):
		from sas_fortuna.setup import fortuna_impex as fi
		from sas_fortuna.setup import ticketing

		super().setUp()
		self.fi = fi
		_location("ZZ JL Place", cities="Zzplace")
		if not frappe.db.exists("HD Ticket Type", ZZ_TYPE):
			frappe.get_doc({"doctype": "HD Ticket Type", "name": ZZ_TYPE}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", self.USER):
			frappe.get_doc(
				{"doctype": "User", "email": self.USER, "first_name": "ZZ JL", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("HD Agent", self.USER):
			frappe.get_doc({"doctype": "HD Agent", "user": self.USER, "agent_name": "ZZ JL"}).insert(
				ignore_permissions=True
			)
		# The class shares one transaction: create the team and its route only once.
		if not frappe.db.exists("HD Team", self.BASE):
			team = frappe.get_doc({"doctype": "HD Team", "team_name": self.BASE, "users": []})
			team.flags.ignore_mandatory = True
			team.insert(ignore_permissions=True)
		if not frappe.db.exists("Fortuna Team Route", {"ticket_type": ZZ_TYPE, "team": self.BASE}):
			ticketing._insert_route(ZZ_TYPE, self.BASE, 900)
		frappe.db.set_default(fi.STAFF_LOCATION_KEY, "")
		self.addCleanup(frappe.db.set_default, fi.STAFF_LOCATION_KEY, "")
		self.staff = fi.merge_staff(
			[
				{
					"name": "ZZ JL",
					"email": self.USER,
					"job_role": "ZZ JL ROLE",
					"location": "Fortuna ZZ JL Place",
				}
			]
		)
		roles = {**fi.JOB_ROLES, "ZZ JL ROLE": {"agent": 1, "teams": [self.BASE], "roles": []}}
		for p in (patch.object(fi, "JOB_ROLES", roles),):
			p.start()
			self.addCleanup(p.stop)

	def _agent_staff(self):
		"""The staff row merged while JOB_ROLES is patched, so it counts as an engineer."""
		return self.fi.merge_staff(
			[
				{
					"name": "ZZ JL",
					"email": self.USER,
					"job_role": "ZZ JL ROLE",
					"location": "Fortuna ZZ JL Place",
				}
			]
		)

	def _routes(self):
		return frappe.get_all(
			"Fortuna Team Route",
			filters={"parent": "Fortuna Support Settings", "ticket_type": ZZ_TYPE},
			fields=["team", "job_location"],
		)

	def test_location_team_route_member_and_agent_location(self):
		self.staff = self.fi.merge_staff(
			[
				{
					"name": "ZZ JL",
					"email": self.USER,
					"job_role": "ZZ JL ROLE",
					"location": "Fortuna ZZ JL Place",
				}
			]
		)
		with patch.object(self.fi, "load_staff", return_value=self.staff):
			self.fi.sync_job_location_teams()
		self.assertEqual(frappe.db.get_value("HD Agent", self.USER, "custom_job_location"), "ZZ JL Place")
		self.assertIn(
			self.USER, frappe.get_all("HD Team Member", filters={"parent": self.TEAM}, pluck="user")
		)
		self.assertIn(frappe._dict(team=self.TEAM, job_location="ZZ JL Place"), self._routes())

	def test_sheet_location_replaces_the_default_given_at_insert(self):
		# A new HD Agent starts on the default location (Kolkata); the staff sheet's own place wins.
		frappe.db.set_value("HD Agent", self.USER, "custom_job_location", "ZZ JL Home")
		staff = self._agent_staff()
		with (
			patch.object(jl, "DEFAULT_LOCATION", "ZZ JL Home"),
			patch.object(self.fi, "load_staff", return_value=staff),
		):
			_location("ZZ JL Home", cities="Zzhome")
			frappe.db.set_value("Job Location", "ZZ JL Home", "is_active", 1)
			self.fi.sync_job_location_teams()
		self.assertEqual(frappe.db.get_value("HD Agent", self.USER, "custom_job_location"), "ZZ JL Place")

	def test_a_location_set_by_hand_is_kept(self):
		# The class shares one transaction: put the agent back for the other tests.
		self.addCleanup(frappe.db.set_value, "HD Agent", self.USER, "custom_job_location", None)
		_location("ZZ JL Other", cities="Zzother")
		frappe.db.set_value("HD Agent", self.USER, "custom_job_location", "ZZ JL Other")
		with patch.object(self.fi, "load_staff", return_value=self._agent_staff()):
			self.fi.sync_job_location_teams()
		self.assertEqual(frappe.db.get_value("HD Agent", self.USER, "custom_job_location"), "ZZ JL Other")

	def test_done_once_per_person(self):
		with patch.object(self.fi, "load_staff", return_value=self.staff):
			self.fi.sync_job_location_teams()
			frappe.db.delete("HD Team Member", {"parent": self.TEAM, "user": self.USER})
			self.assertEqual(self.fi.sync_job_location_teams(), [])
		self.assertNotIn(
			self.USER, frappe.get_all("HD Team Member", filters={"parent": self.TEAM}, pluck="user")
		)

	def test_assignment_limited_to_the_team_once(self):
		frappe.db.set_default(self.fi.ASSIGN_WITHIN_TEAM_FLAG, "")
		self.addCleanup(frappe.db.set_default, self.fi.ASSIGN_WITHIN_TEAM_FLAG, "")
		frappe.db.set_single_value("HD Settings", "assign_within_team", 0)
		self.fi.enable_assign_within_team()
		self.assertTrue(frappe.db.get_single_value("HD Settings", "assign_within_team"))
		frappe.db.set_single_value("HD Settings", "assign_within_team", 0)  # an admin switches it off
		self.assertEqual(self.fi.enable_assign_within_team(), [])
		self.assertFalse(frappe.db.get_single_value("HD Settings", "assign_within_team"))
