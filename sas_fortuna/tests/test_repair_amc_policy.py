"""Unit tests for Fortuna's policy answers in the repair, warranty and SIM code.

Written test-first (TDD), one class per answer:
  * Paid repairs ........ full payment before the repaired unit is shipped (not before work starts)
  * AMC repairs ......... free, except items the AMC contract excludes (sensor, battery, ...)
  * Replacement units ... keep the original warranty by default, decided per repair
  * Extended warranty ... sold as a service line on the sale bill; extends the unit's warranty
  * SIM recharge ........ yearly subscription; the customer is reminded 30 and 15 days before

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_repair_amc_policy
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate, today

from sas_fortuna.setup import support_desk as sd
from sas_fortuna.support import repair, sales, tasks
from sas_fortuna.support.utils import get_settings

SETTINGS = "Fortuna Support Settings"
OLD_START_CONDITION = "doc.payment_cleared == 1"


def _company():
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def _serial(serial_no, item_code, **values):
	"""Get-or-create a test Serial No (IntegrationTestCase rolls back per class, not per test)."""
	if not frappe.db.exists("Serial No", serial_no):
		frappe.get_doc(
			{"doctype": "Serial No", "serial_no": serial_no, "item_code": item_code, "company": _company()}
		).insert(ignore_permissions=True)
	frappe.db.set_value("Serial No", serial_no, {"custom_sim_reminders_sent": 0, **values})
	return frappe.get_doc("Serial No", serial_no)


def _start_allowed(values):
	"""Evaluate the Start Repair condition with the workflow engine itself (same safe globals)."""
	from frappe.model.workflow import is_transition_condition_satisfied

	doc = frappe.get_doc({"doctype": "Repair Order", **values})  # not saved
	return bool(is_transition_condition_satisfied(frappe._dict(condition=repair.START_REPAIR_CONDITION), doc))


def _hsn():
	"""india_compliance (on Fortuna's sites) makes HSN/SAC mandatory on Item."""
	if not frappe.get_meta("Item").has_field("gst_hsn_code"):
		return {}
	code = frappe.db.get_value("GST HSN Code", {}, "name")
	if not code:
		code = (
			frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "998719", "description": "ZZ"})
			.insert(ignore_permissions=True)
			.name
		)
	return {"gst_hsn_code": code}


def _item(code, **values):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
				**_hsn(),
				**values,
			}
		).insert(ignore_permissions=True)
	elif values:
		frappe.db.set_value("Item", code, values)
	return code


def _setting(field, value):
	"""Set one support setting for the test; put it back afterwards."""
	old = frappe.db.get_single_value(SETTINGS, field)
	frappe.db.set_single_value(SETTINGS, field, value)
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return old


class SettingsCase(IntegrationTestCase):
	def set(self, field, value):
		old = _setting(field, value)
		self.addCleanup(_setting, field, old)


# ---------------------------------------------------------------------------
# Paid repairs: full payment before shipment
# ---------------------------------------------------------------------------
class TestPaymentBeforeDispatch(SettingsCase):
	def test_blank_setting_means_dispatch(self):
		self.set("payment_due_before", "")
		self.assertEqual(repair.payment_due_before(), "Dispatch")

	def test_start_repair_waits_only_for_the_confirmed_order(self):
		self.set("payment_due_before", "Dispatch")
		self.assertTrue(_start_allowed(frappe._dict(sales_order="SO-1", payment_cleared=0)))
		self.assertFalse(_start_allowed(frappe._dict(sales_order=None, payment_cleared=0)))

	def test_old_mode_still_needs_the_advance(self):
		self.set("payment_due_before", "Repair Start")
		self.assertFalse(_start_allowed(frappe._dict(sales_order="SO-1", payment_cleared=0)))
		self.assertTrue(_start_allowed(frappe._dict(sales_order="SO-1", payment_cleared=1)))

	def test_new_sites_get_the_new_condition(self):
		row = next(
			t for t in sd.WORKFLOW_TRANSITIONS if t[0] == "Awaiting Payment" and t[1] == "Start Repair"
		)
		self.assertEqual(row[4], repair.START_REPAIR_CONDITION)

	def test_patch_updates_an_existing_workflow_once(self):
		from sas_fortuna.patches.v16_0 import start_repair_after_order_confirmed as p

		# Only the transition row matters: the patch looks rows up by their parent workflow name.
		with patch.object(p, "WORKFLOW", "ZZ Repair Flow"):
			frappe.get_doc(
				{
					"doctype": "Workflow Transition",
					"parent": "ZZ Repair Flow",
					"parenttype": "Workflow",
					"parentfield": "transitions",
					"state": "Awaiting Payment",
					"action": "Start Repair",
					"next_state": "In Repair",
					"allowed": "System Manager",
					"condition": OLD_START_CONDITION,
				}
			).db_insert()
			p.execute()
			p.execute()  # idempotent
			cond = frappe.db.get_value(
				"Workflow Transition", {"parent": "ZZ Repair Flow", "action": "Start Repair"}, "condition"
			)
		self.assertEqual(cond, repair.START_REPAIR_CONDITION)

	def test_unpaid_billable_repair_cannot_ship(self):
		ro = frappe._dict(name="RO-ZZ", is_billable=True, sales_order="SO-ZZ", sales_invoice=None)
		with (
			patch.object(repair, "_service_invoice_submitted", return_value=True),
			patch.object(repair, "is_fully_paid", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, repair.check_paid_before_dispatch, ro)

	def test_paid_repair_ships(self):
		ro = frappe._dict(name="RO-ZZ", is_billable=True, sales_order="SO-ZZ", sales_invoice=None)
		with (
			patch.object(repair, "_service_invoice_submitted", return_value=True),
			patch.object(repair, "is_fully_paid", return_value=True),
		):
			repair.check_paid_before_dispatch(ro)  # no error

	def test_free_repair_ships_without_payment(self):
		repair.check_paid_before_dispatch(frappe._dict(name="RO-ZZ", is_billable=False))

	def test_delivery_note_for_a_repair_runs_the_same_check(self):
		dn = frappe._dict(custom_repair_order="RO-ZZ", is_return=0)
		with (
			patch.object(frappe, "get_doc", return_value=frappe._dict(name="RO-ZZ")),
			patch.object(repair, "check_paid_before_dispatch") as check,
		):
			repair.delivery_note_before_submit(dn)
		check.assert_called_once()

	def test_delivery_note_hook_is_wired(self):
		hooks = frappe.get_hooks("doc_events")["Delivery Note"]["before_submit"]
		self.assertIn("sas_fortuna.support.repair.delivery_note_before_submit", hooks)

	def test_advance_percent_is_only_checked_in_repair_start_mode(self):
		settings = frappe.get_single(SETTINGS)
		settings.payment_due_before = "Dispatch"
		settings.advance_percent = 0
		settings.validate()  # 0 % is fine when payment is due before dispatch
		settings.payment_due_before = "Repair Start"
		self.assertRaises(frappe.ValidationError, settings.validate)


# ---------------------------------------------------------------------------
# AMC repairs: free, except excluded items
# ---------------------------------------------------------------------------
class TestAmcExclusions(SettingsCase):
	def setUp(self):
		super().setUp()
		self.set("charge_amc_repairs", 0)
		self.sensor = _item("ZZ Biometric Sensor", custom_amc_excluded=1)
		self.board = _item("ZZ Main Board", custom_amc_excluded=0)

	def _ro(self, method="AMC", *parts):
		ro = frappe.new_doc("Repair Order")
		ro.invoice_method = method
		for code in parts:
			ro.append("parts", {"item_code": code, "qty": 1, "status": "Pending"})
		return ro

	def test_item_field_exists(self):
		self.assertTrue(frappe.get_meta("Item").has_field("custom_amc_excluded"))

	def test_excluded_part_becomes_chargeable_on_an_amc_repair(self):
		ro = self._ro("AMC", self.sensor, self.board)
		ro.mark_amc_excluded_parts()
		self.assertEqual([bool(p.is_chargeable) for p in ro.parts], [True, False])
		ro.check_parts()  # an excluded part may be chargeable on an AMC repair
		self.assertTrue(ro.is_billable)

	def test_covered_part_still_cannot_be_charged(self):
		ro = self._ro("AMC", self.board)
		ro.parts[0].is_chargeable = 1
		self.assertRaises(frappe.ValidationError, ro.check_parts)

	def test_free_amc_repair_is_not_billable(self):
		ro = self._ro("AMC", self.board)
		ro.mark_amc_excluded_parts()
		self.assertFalse(ro.is_billable)

	def test_amc_quotation_lists_only_the_excluded_parts(self):
		ro = self._ro("AMC", self.sensor, self.board)
		ro.mark_amc_excluded_parts()
		lines = repair.quotation_lines(ro, get_settings())
		self.assertEqual([line["item_code"] for line in lines], [self.sensor])

	def test_chargeable_repair_quotation_adds_service_and_freight(self):
		self.set("service_charge_item", _item("ZZ Service Charge"))
		self.set("freight_item", _item("ZZ Freight"))
		ro = self._ro("Chargeable", self.board)
		ro.parts[0].is_chargeable = 1
		codes = [line["item_code"] for line in repair.quotation_lines(ro, get_settings())]
		self.assertEqual(codes, [self.board, "ZZ Service Charge", "ZZ Freight"])

	def test_nothing_to_quote_on_a_free_amc_repair(self):
		ro = self._ro("AMC", self.board)
		self.assertRaises(frappe.ValidationError, repair.quotation_lines, ro, get_settings())


# ---------------------------------------------------------------------------
# Replacement units: per-repair choice, setting as default
# ---------------------------------------------------------------------------
class TestReplacementWarranty(SettingsCase):
	def test_blank_choice_follows_the_setting(self):
		self.set("replacement_keeps_old_warranty", 1)
		self.assertTrue(repair.keeps_old_warranty(""))
		self.set("replacement_keeps_old_warranty", 0)
		self.assertFalse(repair.keeps_old_warranty(""))

	def test_repair_choice_wins(self):
		self.set("replacement_keeps_old_warranty", 1)
		self.assertFalse(repair.keeps_old_warranty("New Warranty"))
		self.assertTrue(repair.keeps_old_warranty("Keep Original Warranty"))

	def test_field_on_repair_order(self):
		self.assertTrue(frappe.get_meta("Repair Order").has_field("replacement_warranty"))


# ---------------------------------------------------------------------------
# Extended warranty sold on the bill
# ---------------------------------------------------------------------------
class TestExtendedWarranty(IntegrationTestCase):
	def test_months_come_from_the_service_line(self):
		ew = _item("ZZ Extended Warranty 2Y", custom_extended_warranty_months=24)
		plain = _item("ZZ Plain Device")
		self.assertEqual(sales.extended_warranty_months([plain, ew]), 24)
		self.assertEqual(sales.extended_warranty_months([plain]), 0)

	def test_stamp_adds_the_months(self):
		device = _item("ZZ EW Device", has_serial_no=1, is_stock_item=1)
		serial = _serial("ZZ-EW-0001", device)
		sold = getdate("2026-01-10")
		sales._stamp([serial.name], device, None, sold, None, extra_months=12)
		base = sales.compute_warranty_end(device, sold)
		self.assertEqual(
			getdate(frappe.db.get_value("Serial No", serial.name, "custom_warranty_end")),
			getdate(add_months(base, 12)),
		)


# ---------------------------------------------------------------------------
# SIM recharge reminders to the customer
# ---------------------------------------------------------------------------
class TestSimReminders(SettingsCase):
	def setUp(self):
		super().setUp()
		self.set("sim_reminder_days", "30, 15")
		self.set("sim_reminder_cc", "info@example.com")
		self.customer = self._customer()
		device = _item("ZZ SIM Device", has_serial_no=1, is_stock_item=1)
		self.serial = _serial(
			"ZZ-SIM-0001",
			device,
			custom_sold_to=self.customer,
			custom_sim_no="8991000000",
			custom_sim_valid_till=None,
		)

	def _customer(self):
		name = frappe.db.get_value("Customer", {"customer_name": "ZZ SIM Customer"})
		if name:
			return name
		return (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "ZZ SIM Customer",
					"customer_type": "Company",
					"email_id": "",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _valid_till(self, days):
		frappe.db.set_value("Serial No", self.serial.name, "custom_sim_valid_till", add_days(today(), days))

	def _run(self):
		with patch.object(frappe, "sendmail") as sendmail:
			tasks.send_sim_renewal_reminders()
		return sendmail

	def test_reminder_days_are_parsed(self):
		self.assertEqual(tasks.reminder_days("30, 15"), [30, 15])
		self.assertEqual(tasks.reminder_days("15,30,x,"), [30, 15])
		self.assertEqual(tasks.reminder_days(""), [])

	def test_first_reminder_inside_30_days_then_none_until_15(self):
		self._valid_till(25)
		self.assertEqual(self._run().call_count, 1)
		self.assertEqual(frappe.db.get_value("Serial No", self.serial.name, "custom_sim_reminders_sent"), 1)
		self.assertEqual(self._run().call_count, 0)  # next day: nothing new
		self._valid_till(12)
		self.assertEqual(self._run().call_count, 1)  # second interval
		self.assertEqual(frappe.db.get_value("Serial No", self.serial.name, "custom_sim_reminders_sent"), 2)

	def test_customer_gets_it_with_the_cc_copied(self):
		frappe.db.set_value("Customer", self.customer, "email_id", "zz.sim.customer@example.com")
		self._valid_till(10)
		kwargs = self._run().call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["zz.sim.customer@example.com"])
		self.assertIn("info@example.com", kwargs["cc"])
		self.assertEqual(kwargs["reference_name"], self.customer)
		self.assertIn(self.serial.name, kwargs["message"])

	def test_without_customer_email_the_team_is_told(self):
		frappe.db.set_value("Customer", self.customer, "email_id", "")
		self._valid_till(10)
		kwargs = self._run().call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["info@example.com"])
		self.assertIn("No customer e-mail", kwargs["subject"])

	def test_far_away_validity_sends_nothing(self):
		self._valid_till(60)
		self.assertEqual(self._run().call_count, 0)

	def test_new_validity_resets_the_reminders(self):
		self._valid_till(10)
		self._run()
		doc = frappe.get_doc("Serial No", self.serial.name)
		doc.custom_sim_valid_till = add_days(today(), 365)
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.custom_sim_reminders_sent, 0)

	def test_daily_job_is_wired(self):
		self.assertIn(
			"sas_fortuna.support.tasks.send_sim_renewal_reminders",
			frappe.get_hooks("scheduler_events")["daily"],
		)
