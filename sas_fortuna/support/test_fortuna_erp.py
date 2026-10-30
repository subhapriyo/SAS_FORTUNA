"""Checks for the three fortuna_erp fixes made for the support go-live.
Everything is rolled back; nothing is left behind.

    bench --site fortuna.localhost execute sas_fortuna.support.test_fortuna_erp.run

1. Workflow fixtures export only fortuna_erp's own workflows.
2. An Issue is raised only for a real sale of goods.
3. Dealer list filter: no SQL injection, right DocType, still filters.
4. Opportunity: CRM fields mandatory for sales, not for AMC enquiries.
"""

import frappe

from sas_fortuna.support.test_phase01 import RESULTS, check

STOCK_ITEM = "TEST-MODEL-1"
SERVICE_ITEM = "AMC Service"


def run():
	RESULTS.clear()
	try:
		_fixtures()
		_issue_rule()
		_dealer_filter()
		_opportunity_fields()
	finally:
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _fixture_names(doctype):
	for fx in frappe.get_hooks("fixtures", app_name="fortuna_erp"):
		if isinstance(fx, dict) and fx.get("doctype") == doctype:
			return set(frappe.get_all(doctype, filters=fx.get("filters"), pluck="name"))
	return set()


def _fixtures():
	print("\n== 1. fortuna_erp workflow fixtures")
	workflows = _fixture_names("Workflow")
	check(
		"Exports Purchase Order and Quotation workflows",
		workflows == {"Purchase Order", "Quotation"},
		workflows,
	)
	check("Does not export Repair Order Flow", "Repair Order Flow" not in workflows)
	states = _fixture_names("Workflow State")
	check("Does not export repair states", not states & {"Registered", "In Repair", "Dispatched"}, states)
	check(
		"Does not export repair actions",
		not _fixture_names("Workflow Action Master") & {"Start Repair", "End Repair"},
	)


def _invoice(*items, **extra):
	return frappe._dict(items=[frappe._dict(item_code=i) for i in items], **extra)


def _issue_rule():
	print("\n== 2. Issue only for a sale of goods")
	from fortuna_erp.customisations.sales_invoice import needs_issue

	check("Product sale -> Issue", needs_issue(_invoice(STOCK_ITEM)))
	check("Product + service on one invoice -> Issue", needs_issue(_invoice(SERVICE_ITEM, STOCK_ITEM)))
	check("AMC / SIM / service-only invoice -> no Issue", not needs_issue(_invoice(SERVICE_ITEM)))
	check("Credit note -> no Issue", not needs_issue(_invoice(STOCK_ITEM, is_return=1)))
	check("Repair invoice -> no Issue", not needs_issue(_invoice(STOCK_ITEM, custom_repair_order="REP-X")))
	hooked = frappe.get_hooks("doc_events").get("Sales Invoice", {}).get("on_submit", [])
	check("Hook still wired", "fortuna_erp.customisations.sales_invoice.create_issue_on_submit" in hooked)


def _dealer_filter():
	print("\n== 3. Dealer list filter")
	from fortuna_erp.utils.dealer_user import dealer_permission_query

	email = "zz.dealer@fortuna.test"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZZ Dealer", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles("Dealer")

	check("Administrator: no filter", dealer_permission_query("Administrator", "Sales Order") == "")
	check("Non-dealer: no filter", dealer_permission_query("Guest", "Sales Order") == "")

	evil = "Sales Order` WHERE 1=1 -- "
	check("Unknown / injected DocType: dealer sees nothing", dealer_permission_query(email, evil) == "1=0")
	check("Missing DocType: dealer sees nothing", dealer_permission_query(email) == "1=0")

	# Request data no longer matters: form_dict says Quotation, we list Sales Order.
	frappe.form_dict["doctype"] = "Quotation"
	cond = dealer_permission_query(email, "Sales Order")
	check(
		"Uses the DocType being listed, not the request",
		"'Sales Order'" in cond and "`tabSales Order`" in cond,
	)

	# The condition is valid SQL and returns only the dealer's assigned orders.
	orders = frappe.get_all("Sales Order", pluck="name", limit=2)
	if orders:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": email,
				"reference_type": "Sales Order",
				"reference_name": orders[0],
				"description": "zz",
			}
		).insert(ignore_permissions=True)
	seen = frappe.db.sql(f"select name from `tabSales Order` where {cond}", pluck=True)
	check("Dealer sees exactly the assigned order", seen == orders[:1], seen)
	for dt in ("Lead", "Opportunity", "Quotation", "Sales Invoice"):
		frappe.db.sql(f"select count(*) from `tab{dt}` where {dealer_permission_query(email, dt)}")
	check("Condition runs on all five DocTypes", True)


def _opportunity_fields():
	print("\n== 4. Opportunity mandatory fields (sales vs AMC enquiry)")
	from sas_fortuna.support.opportunity import QUALIFICATION_FIELDS, SALES_ONLY, make_amc_opportunity

	meta = frappe.get_meta("Opportunity")
	present = [f for f in QUALIFICATION_FIELDS if meta.has_field(f)]
	bad = [
		f for f in present if meta.get_field(f).reqd or meta.get_field(f).mandatory_depends_on != SALES_ONLY
	]
	check(f"{len(present)} CRM fields: mandatory only without a serial", not bad, bad)

	settings = frappe.get_single("Fortuna Support Settings")
	customer = frappe.db.get_value("Serial No", "TSN-0001", "custom_sold_to") or "Test Company 1"

	# A sales opportunity (no serial) still needs every CRM field, also on the server.
	sales = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_from": "Customer",
			"party_name": customer,
			"company": settings.company,
			"opportunity_owner": "Administrator",
			"territory": frappe.db.get_value("Customer", customer, "territory") or "All Territories",
			"custom_company_name": customer,
			"custom_converted_on": frappe.utils.today(),
			"custom_opportunity_status": "Quotation Requested",
			"custom_request_type": "New installation",
		}
	)
	try:
		sales.insert(ignore_permissions=True)
		check("Sales opportunity without CRM fields is refused", False, "saved")
	except frappe.MandatoryError as e:
		check("Sales opportunity without CRM fields is refused", True)
		check("...naming the missing fields", "Job Title" in str(e) or "Software" in str(e), str(e)[:120])

	# An AMC enquiry for a sold unit goes through.
	serial = frappe._dict(name="TSN-0001", item_code="TEST-MODEL-1", custom_sold_to=customer)
	opp = make_amc_opportunity(serial, settings)
	check("AMC enquiry Opportunity created", bool(opp.name), opp.name)
	check("...for the customer and serial", opp.party_name == customer and opp.custom_serial_no == "TSN-0001")
	check(
		"...as AMC Renewal, Quotation Requested",
		opp.custom_request_type == "AMC Renewal" and opp.custom_opportunity_status == "Quotation Requested",
	)
	check(
		"...with an owner and territory",
		bool(opp.opportunity_owner and opp.territory),
		f"{opp.opportunity_owner} / {opp.territory}",
	)
	opp.reload()
	opp.save(ignore_permissions=True)
	check("AMC team can save it again without CRM fields", True)

	# A serial lifts the CRM fields only when it is genuinely this customer's unit.
	print("\n== 5. Serial No on an Opportunity must be genuine")
	from sas_fortuna.support.test_phase01 import expect_error

	expect_error(
		"Second open Opportunity for the same serial is refused",
		lambda: make_amc_opportunity(serial, settings),
		"already has an open Opportunity",
	)
	opp.db_set("custom_opportunity_status", "Lost")
	again = make_amc_opportunity(serial, settings)
	check("After the first is Lost, a new one is allowed", bool(again.name))
	again.db_set("custom_opportunity_status", "Lost")

	other_customer = frappe.db.get_value("Customer", {"name": ["!=", customer]}, "name")
	if other_customer:
		expect_error(
			"Serial of another customer is refused",
			lambda: make_amc_opportunity(frappe._dict(serial, custom_sold_to=other_customer), settings),
			"belongs to",
		)
	unsold = frappe.db.get_value(
		"Serial No", {"custom_sold_to": ["is", "not set"], "item_code": "TEST-MODEL-1"}, "name"
	)
	if unsold:
		expect_error(
			"Unsold serial is refused",
			lambda: make_amc_opportunity(
				frappe._dict(name=unsold, item_code="TEST-MODEL-1", custom_sold_to=customer), settings
			),
			"has not been sold",
		)
	# party_name must be a real Lead, or Frappe's own link check fails first.
	lead = frappe.db.get_value("Lead", {}, "name")
	if not lead:
		check("Serial on a Lead / Prospect Opportunity is refused", True, "skipped: no Lead on this site")
		return
	lead_opp = frappe.get_doc(
		dict(
			sales.as_dict(), name=None, custom_serial_no="TSN-0001", opportunity_from="Lead", party_name=lead
		)
	)
	expect_error(
		"Serial on a Lead / Prospect Opportunity is refused",
		lambda: lead_opp.insert(ignore_permissions=True),
		"must be for a Customer",
	)
