"""Phase 7 acceptance tests: SIM recharge (N10) and standard Subscriptions (E1, E2).
Everything is rolled back.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase07.run
"""

import frappe
from frappe.utils import add_days, today

from sas_fortuna.support.test_phase01 import RESULTS, check
from sas_fortuna.support.test_phase03 import _sell

CUSTOMER = "Test Company 1"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_sim_fields_and_report()
		_sim_orders()
		_subscription()
	finally:
		frappe.db.rollback()
		frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _settings(**values):
	for k, v in values.items():
		frappe.db.set_single_value("Fortuna Support Settings", k, v)
	frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")


def _sim(serial, days, sim_no):
	frappe.db.set_value(
		"Serial No",
		serial,
		{
			"custom_sim_no": sim_no,
			"custom_sim_operator": "Airtel",
			"custom_sim_activation_date": add_days(today(), days - 365),
			"custom_sim_valid_till": add_days(today(), days),
			"custom_sim_order": None,
		},
	)


def _sim_fields_and_report():
	print("\n== 1. SIM details on the serial and the report (N10)")
	meta = frappe.get_meta("Serial No")
	for f in (
		"custom_sim_no",
		"custom_sim_operator",
		"custom_sim_activation_date",
		"custom_sim_valid_till",
		"custom_sim_order",
	):
		check(f"Serial No field {f}", meta.has_field(f))
	_sell("Sales Invoice", "TSN-0002", update_stock=1)
	_sell("Delivery Note", "TSN-0003")
	_sim("TSN-0001", 10, "SIM-ZZ-1")
	_sim("TSN-0002", 20, "SIM-ZZ-2")
	_sim("TSN-0003", 90, "SIM-ZZ-3")

	from frappe.desk.query_report import run as run_report

	rows = run_report("SIM Recharge Due", filters={"days": 60}).get("result") or []
	text = str(rows)
	check(
		"Report lists SIMs due within 60 days", "TSN-0001" in text and "TSN-0002" in text, f"{len(rows)} rows"
	)
	check("Report leaves out a SIM due in 90 days", "TSN-0003" not in text)


def _sim_orders():
	print("\n== 2. SIM recharge orders (Service Order mode)")
	from sas_fortuna.support.tasks import create_sim_recharge_orders

	_settings(sim_billing_mode="Subscription")
	create_sim_recharge_orders()
	check(
		"Subscription mode: the job creates nothing",
		not frappe.db.get_value("Serial No", "TSN-0001", "custom_sim_order"),
	)

	_settings(sim_billing_mode="Service Order", sim_order_lead_days=30)
	create_sim_recharge_orders()
	so_name = frappe.db.get_value("Serial No", "TSN-0001", "custom_sim_order")
	errors = frappe.get_all("Error Log", filters={"method": ["like", "SIM recharge order%"]}, pluck="method")
	check("One draft Sales Order raised for the customer", bool(so_name), f"errors={errors}")
	if not so_name:
		return
	so = frappe.get_doc("Sales Order", so_name)
	check("Order is a draft for review", so.docstatus == 0)
	check(
		"Order: SIM Recharge x 2 for both due SIMs",
		so.customer == CUSTOMER and [(i.item_code, i.qty) for i in so.items] == [("SIM Recharge", 2)],
		str([(i.item_code, i.qty) for i in so.items]),
	)
	desc = so.items[0].description or ""
	check(
		"Both serials linked to the order",
		frappe.db.get_value("Serial No", "TSN-0002", "custom_sim_order") == so_name,
	)
	check(
		"Serials listed on the order line (prints on the order)",
		"TSN-0001" in desc and "TSN-0002" in desc,
		desc[:120],
	)
	check(
		"SIM due in 90 days is not ordered yet",
		not frappe.db.get_value("Serial No", "TSN-0003", "custom_sim_order"),
	)
	count = frappe.db.count("Sales Order", {"customer": CUSTOMER, "docstatus": 0})
	create_sim_recharge_orders()
	check(
		"Running again raises no second order",
		frappe.db.count("Sales Order", {"customer": CUSTOMER, "docstatus": 0}) == count,
	)


def _subscription():
	print("\n== 3. Standard Subscription billing (E1, E2)")
	try:
		plan = frappe.get_doc(
			{
				"doctype": "Subscription Plan",
				"plan_name": "ZZ SIM Plan",
				"item": "SIM Recharge",
				"price_determination": "Fixed Rate",
				"cost": 500,
				"billing_interval": "Year",
				"billing_interval_count": 1,
				"currency": frappe.db.get_value(
					"Company",
					frappe.db.get_single_value("Fortuna Support Settings", "company"),
					"default_currency",
				),
			}
		).insert(ignore_permissions=True)
		sub = frappe.get_doc(
			{
				"doctype": "Subscription",
				"party_type": "Customer",
				"party": CUSTOMER,
				"company": frappe.db.get_single_value("Fortuna Support Settings", "company"),
				"start_date": today(),
				"generate_invoice_at": "Beginning of the current subscription period",
				"submit_invoice": 0,  # start with drafts until Fortuna trusts the numbers
				"plans": [{"plan": plan.name, "qty": 2}],
			}
		).insert(ignore_permissions=True)
		sub.process(posting_date=today())
	except Exception as e:
		check("Subscription set up and processed", False, f"{type(e).__name__}: {str(e)[:200]}")
		frappe.clear_messages()
		return
	invoices = frappe.get_all(
		"Sales Invoice", filters={"subscription": sub.name}, fields=["name", "docstatus", "grand_total"]
	)
	check("Subscription raised its first invoice", len(invoices) == 1, str(invoices))
	if invoices:
		check(
			"With 'Submit Invoice' off the invoice stays draft for review",
			invoices[0].docstatus == 0,
			f"docstatus={invoices[0].docstatus}",
		)
		check(
			"Invoice amount = 2 x 500 before tax",
			frappe.db.get_value("Sales Invoice", invoices[0].name, "net_total") == 1000,
		)
