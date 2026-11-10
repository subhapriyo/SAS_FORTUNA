"""Legacy (old-system) ticket import into Helpdesk: support/legacy_import.py and its HD Ticket hooks.

Written before the code (TDD). Run:
    bench --site fortuna.localhost run-tests --module sas_fortuna.tests.test_legacy_import

Three groups:
  TestValidateRow ...... one spreadsheet row against the rules, with fake lookups (no database)
  TestCheckFile ........ a whole .xlsx, including the demo and invalid sample files shipped in tests/data
  TestLegacyTicketHooks  real HD Tickets: legacy fields, dates, duplicates, last service date
"""

import datetime as dt
import os
import tempfile
from typing import ClassVar

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, today

from sas_fortuna.support import legacy_import as li

DATA = os.path.join(os.path.dirname(__file__), "data")
DEMO_FILE = os.path.join(DATA, "legacy_tickets_demo.xlsx")
INVALID_FILE = os.path.join(DATA, "legacy_tickets_invalid.xlsx")
TODAY = dt.date(2026, 11, 6)


class FakeLookups:
	"""Stands in for the database in row tests."""

	masters: ClassVar = {
		"HD Ticket Status": {"Open", "Replied", "Paused", "Resolved", "Closed"},
		"HD Ticket Priority": {"Low", "Medium", "High", "Urgent"},
		"HD Ticket Type": {"Software", "Hardware", "Post-Installation"},
		"HD Team": {"Software Support", "Hardware Support"},
		"Customer": {"Demo Client Pvt Ltd", "Ganga Valley Traders (Demo)"},
		"HD Customer": {"Demo Client Pvt Ltd", "Ganga Valley Traders (Demo)"},
		"Item": {"DEMO-MODEL-1"},
		"Contact": set(),
	}
	serials: ClassVar = {"DEMO-0001": ("DEMO-MODEL-1", "Demo Client Pvt Ltd")}
	imported: ClassVar = {"OLD-2024-00001"}

	def exists(self, doctype, name):
		return name in self.masters.get(doctype, set())

	def serial(self, serial_no):
		found = self.serials.get(serial_no)
		return frappe._dict(item_code=found[0], customer=found[1]) if found else None

	def legacy_no_imported(self, legacy_no):
		return legacy_no in self.imported


def good_row(**changes):
	row = {
		"Subject": "Display goes blank after a few minutes",
		"Status": "Closed",
		"Priority": "Medium",
		"Ticket Type": "Hardware",
		"Raised By (Email)": "demo.client@fortuna.test",
		"Description": "Customer reports the display goes blank after 10 minutes.",
		"Resolution Details": "Replaced display board under warranty.",
		"Serial No": "DEMO-0001",
		"ERPNext Customer": "Demo Client Pvt Ltd",
		"Contact Mobile": "+91-9830012345",
		"Legacy Ticket No": "OLD-2025-00142",
		"Legacy Source": "Excel service register",
		"Legacy Opened On": dt.datetime(2025, 3, 14, 10, 30),
		"Legacy Closed On": dt.datetime(2025, 3, 18, 16, 0),
		"Legacy Engineer": "Suresh Bahera",
		"Is Legacy": 1,
	}
	row.update(changes)
	return row


def errors(row, seen=None):
	"""{column: message} of the ERRORS (not warnings) for one row."""
	found = li.validate_row(row, lookups=FakeLookups(), seen=seen, today=TODAY)
	return {p.column: p.message for p in found if p.level == "error"}


def warnings(row):
	found = li.validate_row(row, lookups=FakeLookups(), today=TODAY)
	return {p.column: p.message for p in found if p.level == "warning"}


class TestValidateRow(IntegrationTestCase):
	def test_a_complete_closed_row_has_no_problems(self):
		self.assertEqual(li.validate_row(good_row(), lookups=FakeLookups(), today=TODAY), [])

	# --- required columns -------------------------------------------------------------------
	def test_subject_is_required(self):
		self.assertIn("Subject", errors(good_row(Subject="  ")))

	def test_subject_longer_than_140_characters_is_refused(self):
		self.assertIn("Subject", errors(good_row(Subject="x" * 141)))

	def test_status_is_required_and_must_exist(self):
		self.assertIn("Status", errors(good_row(Status="")))
		self.assertIn("Status", errors(good_row(Status="Completed")))

	def test_legacy_ticket_number_is_required(self):
		self.assertIn("Legacy Ticket No", errors(good_row(**{"Legacy Ticket No": ""})))

	def test_is_legacy_must_be_1(self):
		self.assertIn("Is Legacy", errors(good_row(**{"Is Legacy": 0})))
		self.assertEqual(errors(good_row(**{"Is Legacy": "1"})), {})

	# --- master data ------------------------------------------------------------------------
	def test_unknown_priority_ticket_type_and_team_are_refused(self):
		found = errors(good_row(Priority="Critical", **{"Ticket Type": "Repair", "Team": "Field Team"}))
		self.assertTrue({"Priority", "Ticket Type", "Team"} <= set(found), found)

	def test_unknown_customer_is_refused(self):
		self.assertIn(
			"ERPNext Customer", errors(good_row(**{"ERPNext Customer": "Nobody Ltd", "Serial No": ""}))
		)
		self.assertIn("Customer", errors(good_row(Customer="Nobody Ltd")))

	def test_unknown_serial_points_to_legacy_serial_no(self):
		message = errors(good_row(**{"Serial No": "OLD-SN-77"}))["Serial No"]
		self.assertIn("Legacy Serial No", message)

	def test_serial_of_another_customer_is_refused(self):
		self.assertIn("Serial No", errors(good_row(**{"ERPNext Customer": "Ganga Valley Traders (Demo)"})))

	def test_product_model_must_match_the_serial(self):
		self.assertEqual(errors(good_row(**{"Product Model": "DEMO-MODEL-1"})), {})
		self.assertIn("Product Model", errors(good_row(**{"Product Model": "OTHER-MODEL"})))

	# --- formats ----------------------------------------------------------------------------
	def test_raised_by_must_be_an_email(self):
		self.assertIn("Raised By (Email)", errors(good_row(**{"Raised By (Email)": "demo.client"})))

	def test_contact_mobile_is_checked(self):
		self.assertIn("Contact Mobile", errors(good_row(**{"Contact Mobile": "12345"})))

	# --- dates ------------------------------------------------------------------------------
	def test_dates_may_be_typed_as_text(self):
		row = good_row(**{"Legacy Opened On": "2025-03-14 10:30", "Legacy Closed On": "18-03-2025"})
		self.assertEqual(errors(row), {})

	def test_unreadable_date_is_refused(self):
		self.assertIn("Legacy Opened On", errors(good_row(**{"Legacy Opened On": "14th March"})))

	def test_opened_on_is_required_and_not_in_the_future(self):
		self.assertIn("Legacy Opened On", errors(good_row(**{"Legacy Opened On": None})))
		self.assertIn("Legacy Opened On", errors(good_row(**{"Legacy Opened On": dt.datetime(2027, 1, 1)})))

	def test_closed_before_opened_is_refused(self):
		row = good_row(**{"Legacy Closed On": dt.datetime(2025, 3, 1)})
		self.assertIn("Legacy Closed On", errors(row))

	def test_finished_ticket_needs_a_closed_date(self):
		self.assertIn("Legacy Closed On", errors(good_row(**{"Legacy Closed On": None})))

	def test_open_ticket_must_not_have_a_closed_date(self):
		self.assertIn("Legacy Closed On", errors(good_row(Status="Open")))
		self.assertEqual(
			errors(good_row(Status="Open", **{"Legacy Closed On": None, "Resolution Details": ""})), {}
		)

	def test_resolved_needs_resolution_details(self):
		self.assertIn("Resolution Details", errors(good_row(Status="Resolved", **{"Resolution Details": ""})))
		self.assertEqual(errors(good_row(Status="Closed", **{"Resolution Details": ""})), {})

	# --- duplicates -------------------------------------------------------------------------
	def test_same_legacy_number_twice_in_one_file_is_refused(self):
		seen = {}
		self.assertEqual(errors(good_row(), seen=seen), {})
		self.assertIn("Legacy Ticket No", errors(good_row(), seen=seen))

	def test_legacy_number_already_imported_is_refused(self):
		self.assertIn("Legacy Ticket No", errors(good_row(**{"Legacy Ticket No": "OLD-2024-00001"})))

	# --- warnings (allowed, but worth knowing) ----------------------------------------------
	def test_ticket_nobody_can_see_on_the_portal_gets_a_warning(self):
		row = good_row(**{"Serial No": "", "ERPNext Customer": "", "Raised By (Email)": ""})
		self.assertEqual(errors(row), {})
		self.assertIn("ERPNext Customer", warnings(row))


def _workbook(rows, path):
	from openpyxl import Workbook

	wb = Workbook()
	ws = wb.active
	ws.title = li.IMPORT_SHEET
	headers = list(good_row())
	ws.append(headers)
	for row in rows:
		ws.append([row.get(h) for h in headers])
	wb.save(path)


class TestCheckFile(IntegrationTestCase):
	def test_problems_are_reported_by_spreadsheet_row(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "t.xlsx")
			_workbook([good_row(), good_row(Status="Done", **{"Legacy Ticket No": "OLD-2"})], path)
			report = li.check_file(path, lookups=FakeLookups(), today=TODAY, verbose=False)
		self.assertEqual(report.rows, 2)
		self.assertEqual([(e.row, e.column) for e in report.errors], [(3, "Status")])

	def test_blank_rows_are_skipped(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "t.xlsx")
			_workbook([good_row(), {}, {}], path)
			report = li.check_file(path, lookups=FakeLookups(), today=TODAY, verbose=False)
		self.assertEqual((report.rows, report.errors), (1, []))

	def test_unknown_column_is_reported(self):
		from openpyxl import load_workbook

		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "t.xlsx")
			_workbook([good_row()], path)
			wb = load_workbook(path)
			wb.active.cell(row=1, column=30, value="Engineer Name")
			wb.save(path)
			report = li.check_file(path, lookups=FakeLookups(), today=TODAY, verbose=False)
		self.assertIn("Engineer Name", {e.column for e in report.errors})

	def test_shipped_demo_file_is_valid_on_this_site(self):
		# Real lookups, except "already imported": the demo file may have been test-imported once.
		class SiteLookups(li.DBLookups):
			def legacy_no_imported(self, legacy_no):
				return False

		report = li.check_file(DEMO_FILE, lookups=SiteLookups(), verbose=False)
		self.assertEqual(report.errors, [], [f"row {e.row} {e.column}: {e.message}" for e in report.errors])
		self.assertGreaterEqual(report.rows, 12)

	def test_shipped_invalid_file_fails_every_row(self):
		report = li.check_file(INVALID_FILE, verbose=False)
		self.assertEqual({e.row for e in report.errors}, set(range(2, report.rows + 2)))


class TestLegacyTicketHooks(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.flags.mute_emails = True

	def _legacy(self, **changes):
		values = {
			"doctype": "HD Ticket",
			"subject": "ZZ legacy test",
			"status": "Closed",
			"ticket_type": "Hardware",
			"raised_by": "demo.client@fortuna.test",
			"description": "ZZ legacy test",
			"custom_is_legacy": 1,
			"custom_legacy_ticket_no": frappe.generate_hash(length=10),
			"custom_legacy_opened_on": "2025-03-14 10:30:00",
			"custom_legacy_closed_on": "2025-03-18 16:00:00",
		}
		values.update(changes)
		return frappe.get_doc(values).insert(ignore_permissions=True)

	def test_legacy_fields_exist_on_hd_ticket(self):
		meta = frappe.get_meta("HD Ticket")
		for fieldname in li.LEGACY_FIELDNAMES:
			self.assertTrue(meta.has_field(fieldname), fieldname)
		self.assertTrue(meta.get_field("custom_legacy_ticket_no").unique)

	def test_imported_status_is_kept(self):
		# Helpdesk resets every new ticket to its default open status; an old Closed ticket must stay Closed.
		for status in ("Closed", "Resolved"):
			t = self._legacy(status=status, resolution_details="Fixed.")
			self.assertEqual(frappe.db.get_value("HD Ticket", t.name, "status"), status)
		t = self._legacy(status="Paused", custom_legacy_closed_on=None)
		self.assertEqual(frappe.db.get_value("HD Ticket", t.name, "status"), "Paused")

	def test_legacy_ticket_keeps_its_original_dates(self):
		t = self._legacy()
		self.assertEqual(getdate(t.opening_date), dt.date(2025, 3, 14))
		stored = frappe.db.get_value("HD Ticket", t.name, "resolution_date")
		self.assertEqual(str(stored)[:16], "2025-03-18 16:00")

	def test_duplicate_legacy_number_is_refused(self):
		t = self._legacy()
		with self.assertRaises(frappe.ValidationError):
			self._legacy(custom_legacy_ticket_no=t.custom_legacy_ticket_no)

	def test_closed_before_opened_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._legacy(custom_legacy_closed_on="2025-03-01 09:00:00")

	def test_legacy_ticket_needs_its_old_number(self):
		with self.assertRaises(frappe.ValidationError):
			self._legacy(custom_legacy_ticket_no="")

	def test_last_service_date_is_the_old_closing_date_not_today(self):
		serial = "DEMO-0001"
		if not frappe.db.exists("Serial No", serial):
			self.skipTest("demo serial DEMO-0001 not on this site")
		frappe.db.set_value("Serial No", serial, "custom_last_service_date", None)
		self._legacy(custom_serial_no=serial)
		self.assertEqual(
			getdate(frappe.db.get_value("Serial No", serial, "custom_last_service_date")),
			dt.date(2025, 3, 18),
		)

	def test_an_old_ticket_never_moves_the_last_service_date_back(self):
		serial = "DEMO-0001"
		if not frappe.db.exists("Serial No", serial):
			self.skipTest("demo serial DEMO-0001 not on this site")
		frappe.db.set_value("Serial No", serial, "custom_last_service_date", "2026-10-01")
		self._legacy(custom_serial_no=serial)
		self.assertEqual(
			getdate(frappe.db.get_value("Serial No", serial, "custom_last_service_date")),
			dt.date(2026, 10, 1),
		)

	def test_normal_tickets_still_stamp_today(self):
		serial = "DEMO-0001"
		if not frappe.db.exists("Serial No", serial):
			self.skipTest("demo serial DEMO-0001 not on this site")
		frappe.db.set_value("Serial No", serial, "custom_last_service_date", None)
		t = frappe.get_doc(
			{
				"doctype": "HD Ticket",
				"subject": "ZZ normal ticket",
				"ticket_type": "Hardware",
				"raised_by": "demo.client@fortuna.test",
				"description": "ZZ",
				"custom_serial_no": serial,
			}
		).insert(ignore_permissions=True)
		t.reload()  # Helpdesk saves the ticket again after insert (assignment)
		t.status = "Closed"
		t.save(ignore_permissions=True)
		self.assertEqual(
			getdate(frappe.db.get_value("Serial No", serial, "custom_last_service_date")), getdate(today())
		)
