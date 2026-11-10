"""Importing old (legacy) tickets into Helpdesk.

Fortuna's tickets from before go-live are loaded with Desk > Data Import into HD Ticket, from the
template tools/Fortuna_Legacy_Ticket_Import.xlsx. This module holds the rules for those rows, in one
place, used twice:

  1. Before uploading, check the whole file and get every problem at once, by spreadsheet row:
       bench --site <site> execute sas_fortuna.support.legacy_import.check_file --kwargs "{'path': '/path/file.xlsx'}"
  2. During the import, validate_legacy() (HD Ticket validate hook, see hd_ticket.py) refuses a bad
     ticket even if the file was never checked, and keeps the ticket's original dates.

Imported tickets carry custom_is_legacy = 1. Tests: sas_fortuna/tests/test_legacy_import.py
"""

import datetime as dt
import re

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime

from sas_fortuna.api.validation import check_phone

IMPORT_SHEET = "HD Ticket Import"

# Custom fields on HD Ticket (created by setup/support_desk.py, HD_TICKET_FIELDS)
LEGACY_FIELDNAMES = (
	"custom_is_legacy",
	"custom_legacy_ticket_no",
	"custom_legacy_source",
	"custom_legacy_opened_on",
	"custom_legacy_closed_on",
	"custom_legacy_engineer",
	"custom_legacy_serial_no",
)

FINISHED = ("Resolved", "Closed")
SUBJECT_MAX = 140

# Spreadsheet header -> what kind of value it holds. Headers are the HD Ticket field labels,
# which is what Data Import expects.
COLUMNS = {
	"Subject": "text",
	"Status": "master:HD Ticket Status",
	"Priority": "master:HD Ticket Priority",
	"Ticket Type": "master:HD Ticket Type",
	"Team": "master:HD Team",
	"Raised By (Email)": "email",
	"Description": "text",
	"Opening Date": "date",
	"Opening Time": "time",
	"Resolution Date": "datetime",
	"Resolution Details": "text",
	"Customer": "master:HD Customer",
	"Contact": "master:Contact",
	"Serial No": "serial",
	"Product Model": "master:Item",
	"ERPNext Customer": "master:Customer",
	"Contact Mobile": "phone",
	"Remarks": "text",
	"Legacy Ticket No": "text",
	"Legacy Source": "text",
	"Legacy Opened On": "datetime",
	"Legacy Closed On": "datetime",
	"Legacy Engineer": "text",
	"Legacy Serial No": "text",
	"Is Legacy": "check",
}

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y")


class Problem(frappe._dict):
	"""One finding: level ("error" | "warning"), column, message, and row when checking a file."""


# ---------------------------------------------------------------------------
# Lookups: the database, or a fake one in tests
# ---------------------------------------------------------------------------
class DBLookups:
	def __init__(self):
		self._cache = {}

	def exists(self, doctype, name):
		key = (doctype, name)
		if key not in self._cache:
			self._cache[key] = bool(frappe.db.exists(doctype, name))
		return self._cache[key]

	def serial(self, serial_no):
		"""(item_code, customer) of a Serial No, or None when it does not exist."""
		if not frappe.db.exists("Serial No", serial_no):
			return None
		from sas_fortuna.support.utils import get_serial_coverage

		info = get_serial_coverage(serial_no)
		return frappe._dict(item_code=info.item_code, customer=info.customer)

	def legacy_no_imported(self, legacy_no):
		return bool(frappe.db.exists("HD Ticket", {"custom_legacy_ticket_no": legacy_no}))


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------
def _text(value):
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	return str(value).strip()


def parse_datetime(value):
	"""A datetime from a cell (datetime, date or text); None when blank. Raises ValueError if unreadable."""
	if value in (None, ""):
		return None
	if isinstance(value, dt.datetime):
		return value
	if isinstance(value, dt.date):
		return dt.datetime.combine(value, dt.time())
	text = _text(value)
	for fmt in DATE_FORMATS:
		try:
			return dt.datetime.strptime(text, fmt)
		except ValueError:
			pass
	raise ValueError(text)


# ---------------------------------------------------------------------------
# One row
# ---------------------------------------------------------------------------
def validate_row(row, lookups=None, seen=None, today=None):
	"""Check one spreadsheet row (a dict keyed by column header). Returns a list of Problems.

	`seen` (a dict, shared across the rows of one file) catches the same Legacy Ticket No twice.
	"""
	lookups = lookups or DBLookups()
	today = getdate(today) if today else getdate()
	problems = []

	def error(column, message):
		problems.append(Problem(level="error", column=column, message=_(message)))

	def warning(column, message):
		problems.append(Problem(level="warning", column=column, message=_(message)))

	value = {key: _text(row.get(key)) for key in COLUMNS}
	status = value["Status"]

	# Required
	if not value["Subject"]:
		error("Subject", "Subject is required.")
	elif len(value["Subject"]) > SUBJECT_MAX:
		error("Subject", f"Subject is {len(value['Subject'])} characters; keep it to {SUBJECT_MAX}.")
	if not status:
		error("Status", "Status is required (Open, Replied, Paused, Resolved or Closed).")
	if cint(value["Is Legacy"] or 0) != 1:
		error("Is Legacy", "Is Legacy must be 1 for imported tickets.")

	# Master data
	for column, kind in COLUMNS.items():
		if kind.startswith("master:") and value[column]:
			doctype = kind.split(":", 1)[1]
			if not lookups.exists(doctype, value[column]):
				error(
					column,
					f"'{value[column]}' is not a {doctype} on this site. Pick one from the Lists sheet.",
				)

	# Serial: must exist, and belong to the customer and model given
	serial = None
	if value["Serial No"]:
		serial = lookups.serial(value["Serial No"])
		if not serial:
			error(
				"Serial No",
				f"Serial No '{value['Serial No']}' is not in ERPNext. Leave Serial No empty and put it in Legacy Serial No.",
			)
		else:
			if value["ERPNext Customer"] and serial.customer and serial.customer != value["ERPNext Customer"]:
				error(
					"Serial No",
					f"Serial No {value['Serial No']} was sold to {serial.customer}, not {value['ERPNext Customer']}.",
				)
			if value["Product Model"] and serial.item_code != value["Product Model"]:
				error(
					"Product Model",
					f"Serial No {value['Serial No']} is a {serial.item_code}, not {value['Product Model']}.",
				)

	# Formats
	if value["Raised By (Email)"] and not EMAIL.match(value["Raised By (Email)"]):
		error("Raised By (Email)", "Enter a valid e-mail address, for example name@company.com.")
	if value["Contact Mobile"]:
		message = check_phone(value["Contact Mobile"])[1]
		if message:
			error("Contact Mobile", message)

	# Legacy number: required and unique
	legacy_no = value["Legacy Ticket No"]
	if not legacy_no:
		error("Legacy Ticket No", "Legacy Ticket No is required: the ticket's number in the old system.")
	else:
		if seen is not None:
			if legacy_no in seen:
				error("Legacy Ticket No", f"Legacy Ticket No {legacy_no} is also on row {seen[legacy_no]}.")
			else:
				seen[legacy_no] = row.get("__row__", "?")
		if lookups.legacy_no_imported(legacy_no):
			error("Legacy Ticket No", f"Legacy Ticket No {legacy_no} has already been imported.")

	# Dates
	dates = {}
	for column in ("Legacy Opened On", "Legacy Closed On", "Resolution Date"):
		try:
			dates[column] = parse_datetime(row.get(column))
		except ValueError:
			error(column, "Not a date. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.")
	opened, closed = dates.get("Legacy Opened On"), dates.get("Legacy Closed On")
	if "Legacy Opened On" in dates:
		if not opened:
			error(
				"Legacy Opened On",
				"Legacy Opened On is required: when the ticket was raised in the old system.",
			)
		elif opened.date() > today:
			error("Legacy Opened On", "Legacy Opened On is in the future.")
	if opened and closed and closed < opened:
		error("Legacy Closed On", "Legacy Closed On is before Legacy Opened On.")
	if status in FINISHED and "Legacy Closed On" in dates and not closed:
		error("Legacy Closed On", f"A {status} ticket needs Legacy Closed On.")
	status_ok = bool(status) and lookups.exists("HD Ticket Status", status)
	if status_ok and status not in FINISHED and closed:
		error(
			"Legacy Closed On",
			f"An {status} ticket cannot have Legacy Closed On. Set Status to Closed, or clear the date.",
		)
	if status == "Resolved" and not value["Resolution Details"]:
		error("Resolution Details", "A Resolved ticket needs Resolution Details (or import it as Closed).")

	# Visible on a portal?
	if not (
		value["ERPNext Customer"]
		or (serial and serial.customer)
		or value["Raised By (Email)"]
		or value["Customer"]
	):
		warning(
			"ERPNext Customer",
			"No customer, serial or e-mail: this ticket will not show on any customer's portal.",
		)

	return problems


# ---------------------------------------------------------------------------
# A whole file
# ---------------------------------------------------------------------------
def read_rows(path):
	"""(headers, [(spreadsheet row number, {header: value}), ...]) from the import sheet."""
	from openpyxl import load_workbook

	wb = load_workbook(path, data_only=True, read_only=True)
	ws = wb[IMPORT_SHEET] if IMPORT_SHEET in wb.sheetnames else wb.worksheets[0]
	rows = ws.iter_rows(values_only=True)
	headers = [_text(h) for h in next(rows, [])]
	out = []
	for number, cells in enumerate(rows, start=2):
		record = {h: v for h, v in zip(headers, cells, strict=False) if h}
		if any(_text(v) for v in record.values()):
			record["__row__"] = number
			out.append((number, record))
	wb.close()
	return headers, out


def check_file(path, lookups=None, today=None, verbose=True):
	"""Check a filled-in import file before uploading it. Prints and returns a report."""
	lookups = lookups or DBLookups()
	headers, rows = read_rows(path)
	report = frappe._dict(rows=len(rows), errors=[], warnings=[])

	for header in headers:
		if header and header not in COLUMNS:
			report.errors.append(
				Problem(
					level="error",
					row=1,
					column=header,
					message=_("Unknown column: Data Import will not know where to put it."),
				)
			)
	missing = [
		c
		for c in ("Subject", "Status", "Legacy Ticket No", "Legacy Opened On", "Is Legacy")
		if c not in headers
	]
	for column in missing:
		report.errors.append(
			Problem(level="error", row=1, column=column, message=_("Required column is missing."))
		)

	seen = {}
	for number, record in rows:
		for p in validate_row(record, lookups=lookups, seen=seen, today=today):
			p.row = number
			(report.errors if p.level == "error" else report.warnings).append(p)

	if verbose:
		print(f"{len(rows)} rows, {len(report.errors)} errors, {len(report.warnings)} warnings")
		for p in report.errors + report.warnings:
			print(f"  row {p.row:>4}  {p.level.upper():7}  {p.column}: {p.message}")
		print("Ready to import." if not report.errors else "Fix the errors above, then check again.")
	return report


# ---------------------------------------------------------------------------
# HD Ticket hooks (called from hd_ticket.py)
# ---------------------------------------------------------------------------
# Helpdesk changes four things on every new ticket that are wrong for an old one:
#   before_validate  status -> the default open status (an old Closed ticket would arrive Open)
#   before_save      resolution_date -> now
#   after_insert     a ticket with a Description gets an inbound "Communication" created from it
#                    (create_communication_via_contact), which reopens a Closed/Resolved ticket a
#                    moment after it was created
#   (the sas_fortuna on_update hook) the unit's Last Service Date -> today
# remember_legacy_status (before_insert, runs first), validate_legacy (validate) and
# keep_legacy_resolution_date / guard_legacy_reopen / last_service_date (on_update) put the old
# values back.


def remember_legacy_status(doc):
	"""HD Ticket before_insert: keep the status the import asked for."""
	if doc.get("custom_is_legacy") and doc.get("status"):
		doc.flags.legacy_status = doc.status


def keep_legacy_resolution_date(doc):
	"""HD Ticket on_update: a finished legacy ticket's Resolution Date is its old closing date."""
	if not (doc.get("custom_is_legacy") and doc.get("custom_legacy_closed_on") and doc.status in FINISHED):
		return
	closed = get_datetime(doc.custom_legacy_closed_on)
	if not doc.resolution_date or get_datetime(doc.resolution_date) != closed:
		doc.db_set("resolution_date", closed, update_modified=False)


def validate_legacy(doc):
	"""HD Ticket validate, legacy tickets only: required number, unique, sensible dates; keep old dates."""
	if not doc.get("custom_is_legacy"):
		return
	# Put back the imported status that Helpdesk replaced with the default open status.
	if doc.flags.get("legacy_status") and doc.status != doc.flags.legacy_status:
		doc.status = doc.flags.legacy_status
		doc.status_category = frappe.db.get_value("HD Ticket Status", doc.status, "category")
	legacy_no = (doc.get("custom_legacy_ticket_no") or "").strip()
	if not legacy_no:
		frappe.throw(_("Legacy Ticket No is required on an imported (legacy) ticket."))
	doc.custom_legacy_ticket_no = legacy_no
	other = frappe.db.get_value(
		"HD Ticket", {"custom_legacy_ticket_no": legacy_no, "name": ["!=", doc.name or ""]}
	)
	if other:
		frappe.throw(
			_("Legacy Ticket No {0} has already been imported as ticket {1}.").format(legacy_no, other)
		)

	opened = get_datetime(doc.custom_legacy_opened_on) if doc.get("custom_legacy_opened_on") else None
	closed = get_datetime(doc.custom_legacy_closed_on) if doc.get("custom_legacy_closed_on") else None
	if opened and opened > now_datetime():
		frappe.throw(_("Legacy Opened On is in the future."))
	if opened and closed and closed < opened:
		frappe.throw(_("Legacy Closed On is before Legacy Opened On."))

	# Keep the ticket's original dates (Helpdesk would use the import date).
	if opened:
		doc.opening_date = opened.date()
		doc.opening_time = opened.time()


# A legacy ticket's import description is turned into an inbound Communication (new_ticket=True), and
# whatever Helpdesk hook watches Communication creation reopens the ticket a moment later, inside its
# own save, on a freshly loaded HD Ticket object (no before_insert flags survive onto it). This window
# keeps the fix scoped to that one moment, so a real reopen by a person afterwards is never touched.
REOPEN_GUARD_WINDOW_SECONDS = 120


def guard_legacy_reopen(doc):
	"""HD Ticket on_update: undo the import's own 'first communication' reopening an imported ticket.

	Applies to any imported status (Paused and Replied too, not only Resolved/Closed): whatever the
	sheet asked for, Helpdesk's synthetic reopen must not win.
	"""
	if not doc.get("custom_is_legacy") or not doc.has_value_changed("status"):
		return
	before = doc.get_doc_before_save()
	if not before or before.status == doc.status:
		return  # nothing to undo
	age = (now_datetime() - get_datetime(doc.creation)).total_seconds()
	if age > REOPEN_GUARD_WINDOW_SECONDS:
		return  # too long after import to be the synthetic reopen: a person changed it, leave it
	doc.db_set(
		{"status": before.status, "status_category": before.status_category},
		update_modified=False,
		commit=False,
	)


def last_service_date(doc):
	"""The date to stamp on the unit when this ticket is resolved, or None to leave it alone.

	Normal tickets: today. Legacy tickets: their old closing date, and never earlier than the date
	already on the unit (an old ticket must not make a recently serviced unit look neglected).
	"""
	if not doc.get("custom_is_legacy"):
		return getdate()
	if not doc.get("custom_legacy_closed_on"):
		return None
	closed = getdate(doc.custom_legacy_closed_on)
	current = frappe.db.get_value("Serial No", doc.custom_serial_no, "custom_last_service_date")
	if current and getdate(current) >= closed:
		return None
	return closed
