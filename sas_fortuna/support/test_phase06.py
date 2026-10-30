"""Phase 6 acceptance tests: AMC life cycle (F1, F2, F3, F5, F7, F8). Rolled back.

bench --site fortuna.localhost execute sas_fortuna.support.test_phase06.run
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, date_diff, flt, getdate, today

from sas_fortuna.support import amc
from sas_fortuna.support.test_phase01 import RESULTS, check
from sas_fortuna.support.test_phase03 import _sell
from sas_fortuna.support.test_phase04 import _make_sales_order, _pay
from sas_fortuna.support.utils import get_serial_coverage

CUSTOMER = "Test Company 1"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_config()
		so = _contract()
		_activation(so)
		_renew_and_end(so)
		_enquiry_job()
	finally:
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _config():
	print("\n== 1. Phase 6 wiring")
	ev = frappe.get_hooks("doc_events")
	check(
		"Sales Order.validate -> copy Covered Items",
		"sas_fortuna.support.amc.sales_order_validate" in ev.get("Sales Order", {}).get("validate", []),
	)
	check(
		"Payment Entry.on_submit -> activate AMC",
		"sas_fortuna.support.amc.payment_entry_on_submit" in ev.get("Payment Entry", {}).get("on_submit", []),
	)
	check(
		"Payment Entry still drives the repair gate",
		"sas_fortuna.support.repair.payment_entry_changed"
		in ev.get("Payment Entry", {}).get("on_submit", []),
	)
	check(
		"Sales Order form script (Renew / End / Ticket)",
		"public/js/sales_order.js" in str(frappe.get_hooks("doctype_js").get("Sales Order", [])),
	)
	daily = frappe.get_hooks("scheduler_events").get("daily", [])
	for job in ("send_amc_enquiries", "mark_overdue_gate_passes", "create_sim_recharge_orders"):
		check(f"Daily job {job}", f"sas_fortuna.support.tasks.{job}" in daily)
	check(
		"Notification 'Fortuna AMC Renewal Due' (30 days before)",
		frappe.db.get_value("Notification", "Fortuna AMC Renewal Due", "days_in_advance") == 30,
	)


def _contract():
	print("\n== 2. AMC quotation -> contract (F2, F3)")
	_sell("Sales Invoice", "TSN-0002", update_stock=1)  # now two sold units: TSN-0001, TSN-0002
	start, end = today(), add_days(today(), 364)
	qtn = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": CUSTOMER,
			"company": frappe.db.get_single_value("Fortuna Support Settings", "company"),
			"custom_is_amc": 1,
			"custom_amc_start_date": start,
			"custom_amc_end_date": end,
			"custom_coverage": "Comprehensive",
			"custom_support_mode": "On-site",
			"items": [{"item_code": "AMC Service", "qty": 2, "rate": 5000}],
			"custom_covered_items": [
				{"serial_no": "TSN-0001", "site": "Kolkata plant"},
				{"serial_no": "TSN-0002", "site": "Howrah depot"},
			],
		}
	).insert(ignore_permissions=True)
	check(
		"Covered item fills the item code from the serial",
		all(r.item_code == "TEST-MODEL-1" for r in qtn.custom_covered_items),
		str([r.item_code for r in qtn.custom_covered_items]),
	)
	qtn = apply_workflow(frappe.get_doc("Quotation", qtn.name), "Approve")

	so = _make_sales_order(qtn.name)
	so.delivery_date = today()
	for item in so.items:
		item.delivery_date = today()
	so.insert(ignore_permissions=True)
	check(
		"Contract header copied (Is AMC, dates, coverage)",
		so.custom_is_amc
		and str(so.custom_amc_start_date) == start
		and str(so.custom_amc_end_date) == end
		and so.custom_coverage == "Comprehensive",
	)
	check(
		"Covered Items copied to the contract (2 units with sites)",
		[(r.serial_no, r.site) for r in so.custom_covered_items]
		== [("TSN-0001", "Kolkata plant"), ("TSN-0002", "Howrah depot")],
		str([(r.serial_no, r.site) for r in so.custom_covered_items]),
	)
	so.save(ignore_permissions=True)
	check(
		"Saving again does not duplicate the covered units",
		len(frappe.get_doc("Sales Order", so.name).custom_covered_items) == 2,
	)
	so = frappe.get_doc("Sales Order", so.name)
	so.submit()
	check("Submitted contract is not active before payment", not so.custom_amc_status)
	return so


def _activation(so):
	print("\n== 3. Activate on payment (F5, F7)")
	_pay(so, flt(so.grand_total) / 2)
	check("Half paid: still not active", not frappe.db.get_value("Sales Order", so.name, "custom_amc_status"))
	check(
		"Half paid: serials have no AMC yet",
		not frappe.db.get_value("Serial No", "TSN-0001", "amc_expiry_date"),
	)
	_pay(so, flt(so.grand_total) / 2)
	check(
		"Paid in full: contract Active",
		frappe.db.get_value("Sales Order", so.name, "custom_amc_status") == "Active",
	)
	for serial in ("TSN-0001", "TSN-0002"):
		s = frappe.db.get_value(
			"Serial No",
			serial,
			["amc_expiry_date", "custom_amc_start_date", "custom_amc_contract", "custom_amc_status"],
			as_dict=True,
		)
		check(
			f"{serial}: AMC dates, contract and status stamped",
			str(s.amc_expiry_date) == str(so.custom_amc_end_date)
			and str(s.custom_amc_start_date) == str(so.custom_amc_start_date)
			and s.custom_amc_contract == so.name
			and s.custom_amc_status == "Active",
			str(s),
		)
	amc.activate_amc(so.name)
	check(
		"Activating twice changes nothing",
		frappe.db.get_value("Sales Order", so.name, "custom_amc_status") == "Active",
	)

	frappe.db.set_value("Serial No", "TSN-0001", "custom_warranty_end", add_days(today(), -1))
	check(
		"Warranty over, AMC active -> ticket classified AMC (F7)",
		get_serial_coverage("TSN-0001").support_type == "AMC",
	)
	t = frappe.get_doc(
		{
			"doctype": "HD Ticket",
			"subject": "ZZ AMC breakdown",
			"description": "x",
			"raised_by": "zz@example.com",
			"ticket_type": "Hardware",
			"custom_serial_no": "TSN-0001",
		}
	).insert(ignore_permissions=True)
	check(
		"New ticket on the unit shows AMC with expiry",
		t.custom_support_type == "AMC" and str(t.custom_amc_expiry) == str(so.custom_amc_end_date),
	)


def _renew_and_end(so):
	print("\n== 4. Renew and End (F8)")
	if so.meta.has_field("sales_partner"):
		partner = frappe.get_all("Sales Partner", pluck="name", limit=1)
		if partner:
			frappe.db.set_value("Sales Order", so.name, "sales_partner", partner[0])
	so.reload()
	qname = amc.renew_amc(so.name)
	q = frappe.get_doc("Quotation", qname)
	check(
		"Renewal quotation is a draft AMC quotation",
		q.docstatus == 0 and q.custom_is_amc and q.custom_renewal_of == so.name,
	)
	check(
		"Next period starts the day after the old one ends",
		getdate(q.custom_amc_start_date) == getdate(add_days(so.custom_amc_end_date, 1)),
	)
	check(
		"Same length as the old contract",
		date_diff(q.custom_amc_end_date, q.custom_amc_start_date)
		== date_diff(so.custom_amc_end_date, so.custom_amc_start_date),
	)
	check(
		"Same covered units and sites",
		[(r.serial_no, r.site) for r in q.custom_covered_items]
		== [(r.serial_no, r.site) for r in so.custom_covered_items],
	)
	check(
		"Same service items",
		[(i.item_code, i.qty) for i in q.items] == [(i.item_code, i.qty) for i in so.items],
	)
	if so.get("sales_partner") and q.meta.has_field("custom_dealer"):
		check(
			"Dealer carried to the renewal (fortuna_erp custom_dealer)", q.custom_dealer == so.sales_partner
		)
	check(
		"Contract marked Renewal Quoted",
		frappe.db.get_value("Sales Order", so.name, "custom_amc_status") == "Renewal Quoted",
	)

	amc.end_amc(so.name)
	check(
		"End AMC: contract Ended", frappe.db.get_value("Sales Order", so.name, "custom_amc_status") == "Ended"
	)
	check(
		"End AMC: covered serials Ended",
		{frappe.db.get_value("Serial No", s, "custom_amc_status") for s in ("TSN-0001", "TSN-0002")}
		== {"Ended"},
	)


def _enquiry_job():
	print("\n== 5. Warranty ending soon -> AMC enquiry (F1)")
	from sas_fortuna.support.tasks import send_amc_enquiries

	_sell("Delivery Note", "TSN-0003")
	frappe.db.set_value(
		"Serial No",
		"TSN-0003",
		{
			"custom_warranty_end": add_days(today(), 20),
			"custom_amc_enquiry_sent": 0,
			"custom_amc_status": None,
		},
	)

	def reset():
		frappe.db.set_value("Serial No", "TSN-0003", "custom_amc_enquiry_sent", 0)

	def set_opps(on):
		frappe.db.set_single_value("Fortuna Support Settings", "create_amc_opportunities", on)
		frappe.clear_document_cache("Fortuna Support Settings", "Fortuna Support Settings")

	# Opportunities off
	set_opps(0)
	send_amc_enquiries()
	check(
		"Opportunities off: serial flagged 'AMC Enquiry Sent'",
		frappe.db.get_value("Serial No", "TSN-0003", "custom_amc_enquiry_sent") == 1,
	)
	check(
		"Opportunities off: none created",
		not frappe.db.count("Opportunity", {"custom_serial_no": "TSN-0003"}),
	)

	# Opportunities on: created despite fortuna_erp's mandatory CRM fields (opportunity.py)
	reset()
	set_opps(1)
	logged_before = frappe.db.count("Error Log", {"method": ["like", "AMC enquiry%TSN-0003%"]})
	send_amc_enquiries()
	created = frappe.db.count("Opportunity", {"custom_serial_no": "TSN-0003"})
	logged = frappe.db.count("Error Log", {"method": ["like", "AMC enquiry%TSN-0003%"]}) - logged_before
	check(
		"Opportunities on: one Opportunity created, no error",
		created == 1 and logged == 0,
		f"created={created} new errors={logged}",
	)
	if created:
		opp = frappe.get_doc("Opportunity", {"custom_serial_no": "TSN-0003"})
		check(
			"Opportunity: customer, AMC Renewal, Quotation Requested, unit as item",
			opp.opportunity_from == "Customer"
			and opp.party_name == frappe.db.get_value("Serial No", "TSN-0003", "custom_sold_to")
			and opp.get("custom_request_type", "AMC Renewal") == "AMC Renewal"
			and opp.get("custom_opportunity_status", "Quotation Requested") == "Quotation Requested"
			and [i.item_code for i in opp.items] == ["TEST-MODEL-1"],
		)
	check(
		"...and the serial is flagged either way (no daily repeat mail)",
		frappe.db.get_value("Serial No", "TSN-0003", "custom_amc_enquiry_sent") == 1,
	)
	send_amc_enquiries()
	check(
		"Running again creates nothing new",
		frappe.db.count("Opportunity", {"custom_serial_no": "TSN-0003"}) == created,
	)
	set_opps(0)

	frappe.db.set_value(
		"Serial No",
		"TSN-0002",
		{
			"custom_warranty_end": add_days(today(), 10),
			"custom_amc_status": "Active",
			"custom_amc_enquiry_sent": 0,
		},
	)
	send_amc_enquiries()
	check(
		"A unit already under active AMC is skipped",
		not frappe.db.get_value("Serial No", "TSN-0002", "custom_amc_enquiry_sent"),
	)
