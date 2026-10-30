"""Checks for the validation rules added on 23 Oct. Everything is rolled back.

bench --site fortuna.localhost execute sas_fortuna.support.test_rules.run
"""

import frappe
from frappe.utils import add_days, today

from sas_fortuna.support.test_phase01 import RESULTS, check, expect_error

SERIAL = "TSN-0001"  # sold unit from the T6 test data
ITEM = "TEST-MODEL-1"
PART = "AMC Service"  # any item works for part-row rules


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_repair_order()
		_amc()
		_settings()
		_sim()
	finally:
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _employee():
	from sas_fortuna.support.test_phase03 import _employee as make_employee

	return make_employee()


def _ro(**extra):
	doc = frappe.get_doc(
		{
			"doctype": "Repair Order",
			"serial_no": SERIAL,
			"product_model": ITEM,
			"responsible": _employee(),
			**extra,
		}
	)
	customer = frappe.db.get_value("Serial No", SERIAL, "custom_sold_to")
	doc.customer = doc.customer or customer
	return doc


def _repair_order():
	print("\n== 1. Repair Order rules")
	frappe.db.set_value(
		"Repair Order", {"serial_no": SERIAL}, "status", "Closed"
	)  # clear earlier test repairs
	ro = _ro().insert(ignore_permissions=True)
	check("First repair for the unit saves", bool(ro.name))
	expect_error(
		"Second open repair for the same unit refused",
		lambda: _ro().insert(ignore_permissions=True),
		"already has an open repair",
	)

	def save_with(**part):
		"""Fresh copy (the save hooks touch the record), one part row, save."""
		doc = frappe.get_doc("Repair Order", ro.name)
		doc.invoice_method = "Free (Warranty)"
		doc.parts = []
		doc.append("parts", {"item_code": PART, "qty": 1, "rate": 0, **part})
		return lambda: doc.save(ignore_permissions=True)

	expect_error("Part qty 0 refused", save_with(qty=0), "Qty must be more than 0")
	expect_error("Negative rate refused", save_with(rate=-5), "cannot be negative")
	expect_error(
		"Chargeable part on a free warranty repair refused", save_with(is_chargeable=1), "marked Chargeable"
	)
	save_with()()
	check("Free part on a warranty repair saves", True)
	ro = frappe.get_doc("Repair Order", ro.name)

	from sas_fortuna.support.repair import make_quotation

	expect_error(
		"No quotation for a free warranty repair", lambda: make_quotation(ro.name), "no quotation is needed"
	)

	# A part already reserved is tied to a stock entry.
	frappe.db.set_value("Repair Order Part", ro.parts[0].name, "status", "Reserved")
	ro.reload()
	ro.parts[0].qty = 2
	expect_error(
		"Reserved part: qty cannot change", lambda: ro.save(ignore_permissions=True), "cannot be changed"
	)
	ro.reload()
	ro.parts = []
	expect_error(
		"Reserved part: row cannot be removed", lambda: ro.save(ignore_permissions=True), "cannot be removed"
	)

	from sas_fortuna.support.repair import make_dispatch

	frappe.db.set_value("Repair Order", ro.name, "status", "Ready")
	expect_error("No dispatch while parts are reserved", lambda: make_dispatch(ro.name), "reserved parts")

	ro.reload()
	foreign = frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Address", "link_doctype": "Customer", "link_name": ("!=", ro.customer)},
		"parent",
	)
	if foreign:
		ro.delivery_address = foreign
		expect_error(
			"Another customer's address refused",
			lambda: ro.save(ignore_permissions=True),
			"does not belong to",
		)

	# After receipt the unit and customer are fixed (any existing entry stands in for the receipt).
	receipt = frappe.get_all("Stock Entry", pluck="name", limit=1)[0]
	frappe.db.set_value("Repair Order", ro.name, {"repair_receipt": receipt, "status": "Unit Received"})
	ro = frappe.get_doc("Repair Order", ro.name)
	ro.customer = frappe.db.get_value("Customer", {"name": ("!=", ro.customer)}, "name")
	expect_error(
		"Customer locked after receipt",
		lambda: ro.save(ignore_permissions=True),
		"cannot be changed after the unit is received",
	)


def _amc_quotation(**extra):
	customer = frappe.db.get_value("Serial No", SERIAL, "custom_sold_to")
	q = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": customer,
			"company": frappe.db.get_single_value("Fortuna Support Settings", "company"),
			"custom_is_amc": 1,
			"custom_amc_start_date": today(),
			"custom_amc_end_date": add_days(today(), 364),
			"items": [{"item_code": "AMC Service", "qty": 1, "rate": 1000}],
			**extra,
		}
	)
	return q


def _amc():
	print("\n== 2. AMC rules")
	q = _amc_quotation(custom_amc_end_date=add_days(today(), -1))
	expect_error("End date before start refused", lambda: q.insert(ignore_permissions=True), "must be after")
	q = _amc_quotation(custom_covered_items=[{"serial_no": SERIAL}, {"serial_no": SERIAL}])
	expect_error("Same unit twice refused", lambda: q.insert(ignore_permissions=True), "listed twice")
	q = _amc_quotation().insert(ignore_permissions=True)
	check("AMC quotation without units can be saved as a draft", bool(q.name))
	expect_error("...but not submitted", lambda: q.submit(), "Covered Items")

	# Overlap: an active AMC order on the unit already covers this period.
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": q.party_name,
			"company": q.company,
			"delivery_date": today(),
			"custom_is_amc": 1,
			"custom_amc_start_date": today(),
			"custom_amc_end_date": add_days(today(), 364),
			"custom_covered_items": [{"serial_no": SERIAL}],
			"items": [{"item_code": "AMC Service", "qty": 1, "rate": 1000, "delivery_date": today()}],
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()
	check("First AMC order for the unit submits", so.docstatus == 1)
	so2 = frappe.copy_doc(so)
	so2.custom_amc_start_date = add_days(today(), 100)
	so2.custom_amc_end_date = add_days(today(), 400)
	so2.insert(ignore_permissions=True)
	expect_error("Overlapping AMC on the same unit refused", lambda: so2.submit(), "already under AMC")
	so3 = frappe.copy_doc(so)
	so3.custom_amc_start_date = add_days(today(), 365)
	so3.custom_amc_end_date = add_days(today(), 729)
	so3.insert(ignore_permissions=True)
	so3.submit()
	check("Next-period (renewal) AMC submits", so3.docstatus == 1)


def _settings():
	print("\n== 3. Settings rules")
	s = frappe.get_single("Fortuna Support Settings")
	s.amc_enquiry_lead_days = -1
	expect_error("Negative lead days refused", lambda: s.save(), "cannot be negative")
	s.reload()
	s.amc_team_email = "amc@fortuna.test, not-an-email"
	expect_error("Invalid AMC team e-mail refused", lambda: s.save(), "")
	s.reload()
	s.amc_team_email = "amc@fortuna.test, service@fortuna.test"
	s.save()
	check("Two valid e-mails save", True)


def _sim():
	print("\n== 4. SIM dates")
	sn = frappe.get_doc("Serial No", SERIAL)
	sn.custom_sim_activation_date = today()
	sn.custom_sim_valid_till = add_days(today(), -1)
	expect_error(
		"SIM Valid Till before activation refused",
		lambda: sn.save(ignore_permissions=True),
		"cannot be before",
	)
