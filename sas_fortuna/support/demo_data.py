"""Demo data and demo steps for the client demo (and its recorded video).

Dev / demo site only. Each step COMMITS, so the records stay for the demo.

    bash apps/sas_fortuna/tools/video/step.sh prep
    bash apps/sas_fortuna/tools/video/step.sh ticket      (then: repair, receipt, ...)

State (document names) is kept in sites/fortuna.localhost/private/demo_state.json.
Logins for the presenter and the demo customer are written to
apps/sas_fortuna/tools/video/LOGINS.txt (tools/ is kept out of git).
"""

import json
import os
import secrets

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, add_months, flt, today
from frappe.utils.password import update_password

MODEL, SPARE = "DEMO-MODEL-1", "DEMO-SPARE-BOARD"
CUSTOMER = "Demo Client Pvt Ltd"
PRESENTER = "demo.presenter@fortuna.test"
CLIENT_USER = "demo.client@fortuna.test"
PRESENTER_ROLES = [
	"System Manager",
	"Agent",
	"Support Manager",
	"Sales Manager",
	"Sales User",
	"Stock Manager",
	"Stock User",
	"Accounts Manager",
	"Accounts User",
	"AMC Team",
	"Service Engineer",
	"Item Manager",
]
PRICES = {SPARE: 600, "Repair Service Charge": 300, "Freight Charges": 100, "AMC Service": 1500}


# ---------------------------------------------------------------------------
def step(name):
	frappe.flags.mute_emails = False
	state = _load()
	result = globals()[f"_{name}"](state)
	_save(state)
	frappe.db.commit()
	print(json.dumps(result or state, default=str))


def _state_path():
	return frappe.get_site_path("private", "demo_state.json")


def _load():
	p = _state_path()
	return json.load(open(p)) if os.path.exists(p) else {}


def _save(state):
	json.dump(state, open(_state_path(), "w"), indent=1, default=str)


def _settings():
	return frappe.get_single("Fortuna Support Settings")


# ---------------------------------------------------------------------------
# Preparation (P1-P10 in the demo script)
# ---------------------------------------------------------------------------
def _prep(state):
	s = _settings()
	stores = s.loaner_source_warehouse
	_logins()
	_item(MODEL, serial=True)
	_item(SPARE, serial=False)
	if not frappe.db.exists("Serial No", "DEMO-0001"):
		_stock_in(MODEL, 6, 1000, stores)
	if not frappe.db.get_value("Bin", {"item_code": SPARE, "warehouse": s.spares_warehouse}, "actual_qty"):
		_stock_in(SPARE, 10, 200, s.spares_warehouse)
	for code, rate in PRICES.items():
		if not frappe.db.exists("Item Price", {"item_code": code, "price_list": "Standard Selling"}):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": code,
					"price_list": "Standard Selling",
					"price_list_rate": rate,
				}
			).insert()
	_customer()
	if not frappe.db.get_value("Serial No", "DEMO-0001", "custom_invoice_no"):
		_sell(["DEMO-0001", "DEMO-0002", "DEMO-0003"], stores)
	frappe.db.set_value("Serial No", "DEMO-0002", "custom_warranty_end", add_months(today(), -1))
	state.update(prepared=today())
	return {
		"prepared": True,
		"serials": frappe.get_all(
			"Serial No",
			filters={"item_code": MODEL},
			fields=["name", "custom_sold_to", "custom_warranty_end"],
		),
	}


def _logins():
	path = frappe.get_app_path("sas_fortuna", "..", "tools", "video", "LOGINS.txt")
	if os.path.exists(path):
		password = open(path).read().split("password:")[1].strip()
	else:
		password = "Demo-" + secrets.token_urlsafe(9)
	frappe.flags.demo_password = password
	if frappe.db.exists("User", PRESENTER):
		return
	frappe.get_doc(
		{
			"doctype": "User",
			"email": PRESENTER,
			"first_name": "Demo",
			"last_name": "Presenter",
			"send_welcome_email": 0,
		}
	).insert()
	user = frappe.get_doc("User", PRESENTER)
	user.add_roles(*[r for r in PRESENTER_ROLES if frappe.db.exists("Role", r)])
	update_password(PRESENTER, password)
	if not frappe.db.exists("HD Agent", PRESENTER):
		frappe.get_doc(
			{"doctype": "HD Agent", "user": PRESENTER, "agent_name": "Demo Presenter", "is_active": 1}
		).insert()
	for team in ("Hardware Support", "Software Support"):
		t = frappe.get_doc("HD Team", team)
		if PRESENTER not in {r.user for r in t.users}:
			t.append("users", {"user": PRESENTER})
			t.save()
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		f.write(
			f"Demo site logins (dev only)\npresenter: {PRESENTER}\nclient:    {CLIENT_USER}\npassword:  {password}\n"
		)


def _item(code, serial):
	if frappe.db.exists("Item", code):
		return
	hsn = frappe.get_all("GST HSN Code", filters={"name": ["like", "8471%"]}, pluck="name", limit=1) or [
		"847150"
	]
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code.replace("-", " ").title(),
			"item_group": "Products" if serial else "Raw Material",
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"gst_hsn_code": hsn[0],
			"has_serial_no": 1 if serial else 0,
			"serial_no_series": "DEMO-.####" if serial else None,
			"valuation_rate": 1000 if serial else 200,
			"custom_status": "Approved",
		}
	).insert()


def _stock_in(code, qty, rate, warehouse):
	se = frappe.new_doc("Stock Entry")
	se.company = _settings().company
	se.purpose = se.stock_entry_type = "Material Receipt"
	se.append("items", {"item_code": code, "qty": qty, "basic_rate": rate, "t_warehouse": warehouse})
	se.insert()
	se.submit()


def _customer():
	if not frappe.db.exists("Customer", CUSTOMER):
		leaf = lambda dt: frappe.get_all(dt, filters={"is_group": 0}, pluck="name", limit=1)[0]  # noqa: E731
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": CUSTOMER,
				"customer_type": "Company",
				"customer_group": leaf("Customer Group"),
				"territory": leaf("Territory"),
			}
		).insert()
	if not frappe.db.get_value("Customer", CUSTOMER, "customer_primary_address"):
		addr = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": CUSTOMER,
				"address_type": "Billing",
				"address_line1": "12 Park Street",
				"city": "Kolkata",
				"state": "West Bengal",
				"pincode": "700016",
				"country": "India",
				"gst_category": "Unregistered",
				"is_primary_address": 1,
				"is_shipping_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": CUSTOMER}],
			}
		).insert()
		frappe.db.set_value("Customer", CUSTOMER, "customer_primary_address", addr.name)
	if not frappe.db.exists("User", CLIENT_USER):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": CLIENT_USER,
				"first_name": "Ravi",
				"last_name": "Mehta",
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [{"role": "Customer"}],
			}
		).insert()
		if getattr(frappe.flags, "demo_password", None):
			update_password(CLIENT_USER, frappe.flags.demo_password)
	if not frappe.db.get_value("Customer", CUSTOMER, "customer_primary_contact"):
		c = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Ravi",
				"last_name": "Mehta",
				"designation": "Service Head",
				"user": CLIENT_USER,
				"email_ids": [{"email_id": CLIENT_USER, "is_primary": 1}],
				"phone_nos": [
					{
						"phone": "9830012345",
						"custom_mobile_number": "+91-9830012345",
						"is_primary_mobile_no": 1,
					}
				],
				"links": [{"link_doctype": "Customer", "link_name": CUSTOMER}],
			}
		).insert()
		frappe.db.set_value(
			"Customer",
			CUSTOMER,
			{"customer_primary_contact": c.name, "mobile_no": "9830012345", "email_id": CLIENT_USER},
		)


def _sell(serials, warehouse):
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{"customer": CUSTOMER, "company": _settings().company, "update_stock": 1, "set_warehouse": warehouse}
	)
	si.append(
		"items",
		{
			"item_code": MODEL,
			"qty": len(serials),
			"rate": 45000,
			"warehouse": warehouse,
			"use_serial_batch_fields": 1,
			"serial_no": "\n".join(serials),
		},
	)
	si.run_method("set_missing_values")
	si.insert()
	si.submit()
	return si.name


# ---------------------------------------------------------------------------
# Scene steps
# ---------------------------------------------------------------------------
def _new_ticket(serial, subject, key, state):
	t = frappe.get_doc(
		{
			"doctype": "HD Ticket",
			"subject": subject,
			"description": "Customer reports: " + subject.lower() + ".",
			"raised_by": CLIENT_USER,
			"ticket_type": "Hardware",
			"custom_serial_no": serial,
		}
	).insert()
	state[key] = t.name
	return t


def _ticket(state):
	_new_ticket("DEMO-0001", "Unit does not power on", "ticket", state)


def _paid_ticket(state):
	_new_ticket("DEMO-0002", "Display flickering", "paid_ticket", state)


def _employee():
	from sas_fortuna.support.test_phase03 import _employee as emp

	return emp()


def _new_repair(ticket, key, state):
	ro = frappe.get_doc(
		{
			"doctype": "Repair Order",
			"helpdesk_ticket": ticket,
			"responsible": _employee(),
			"help_desk_owner": PRESENTER,
		}
	).insert()
	state[key] = ro.name


def _repair(state):
	_new_repair(state["ticket"], "repair", state)


def _paid_repair(state):
	_new_repair(state["paid_ticket"], "paid_repair", state)


def _do_receipt(ro):
	from sas_fortuna.support.repair import make_repair_receipt

	frappe.get_doc("Stock Entry", make_repair_receipt(ro)).submit()


def _receipt(state):
	_do_receipt(state["repair"])


def _paid_receipt(state):
	_do_receipt(state["paid_repair"])


def _add_part(ro_name, chargeable):
	ro = frappe.get_doc("Repair Order", ro_name)
	ro.append("parts", {"item_code": SPARE, "qty": 1, "is_chargeable": chargeable})
	ro.diagnosis = (
		"Power board failed. Replace board." if not chargeable else "Display board damaged. Replace board."
	)
	ro.save()


def _part(state):
	_add_part(state["repair"], 0)


def _start(state):
	apply_workflow(frappe.get_doc("Repair Order", state["repair"]), "Start Repair")


def _spares(state):
	from sas_fortuna.support.repair import consume_spares, raise_spares_request, reserve_spares

	ro = state["repair"]
	state["spares_request"] = raise_spares_request(ro)
	se = frappe.get_doc("Stock Entry", reserve_spares(ro))
	se.submit()
	state["reserve"] = se.name
	se = frappe.get_doc("Stock Entry", consume_spares(ro))
	se.submit()
	state["consume"] = se.name


def _end(state):
	apply_workflow(frappe.get_doc("Repair Order", state["repair"]), "End Repair")


def _dispatch(state):
	from sas_fortuna.support.repair import make_dispatch

	dn = frappe.get_doc("Delivery Note", make_dispatch(state["repair"]))
	dn.submit()
	state["dispatch"] = dn.name


def _close(state):
	apply_workflow(frappe.get_doc("Repair Order", state["repair"]), "Close")


def _paid_part(state):
	_add_part(state["paid_repair"], 1)


def _quote(state):
	from sas_fortuna.support.repair import make_quotation

	q = make_quotation(state["paid_repair"])
	state["quotation"] = q
	apply_workflow(frappe.get_doc("Quotation", q), "Approve")


def _send_quote(state):
	apply_workflow(frappe.get_doc("Repair Order", state["paid_repair"]), "Send Quotation")


def _order(qtn):
	from sas_fortuna.support.test_phase04 import _make_sales_order

	so = _make_sales_order(qtn)
	so.delivery_date = today()
	for item in so.items:
		item.delivery_date = today()
	so.insert()
	so.submit()
	return so


def _pay_order(so_name):
	from sas_fortuna.support.test_phase04 import _pay

	so = frappe.get_doc("Sales Order", so_name)
	return _pay(so, flt(so.grand_total)).name


def _paid_order(state):
	state["sales_order"] = _order(state["quotation"]).name


def _paid_payment(state):
	state["payment"] = _pay_order(state["sales_order"])


def _amc_quote(state):
	q = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": CUSTOMER,
			"company": _settings().company,
			"custom_is_amc": 1,
			"custom_amc_start_date": today(),
			"custom_amc_end_date": add_days(today(), 364),
			"custom_coverage": "Comprehensive",
			"custom_support_mode": "On-site",
			"items": [{"item_code": "AMC Service", "qty": 2}],
			"custom_covered_items": [
				{"serial_no": "DEMO-0002", "site": "Kolkata head office"},
				{"serial_no": "DEMO-0003", "site": "Howrah warehouse"},
			],
		}
	).insert()
	state["amc_quotation"] = q.name


def _amc_approve(state):
	apply_workflow(frappe.get_doc("Quotation", state["amc_quotation"]), "Approve")
	state["amc_order"] = _order(state["amc_quotation"]).name


def _amc_pay(state):
	state["amc_payment"] = _pay_order(state["amc_order"])


def _amc_ticket(state):
	_new_ticket("DEMO-0003", "Unit making noise", "amc_ticket", state)


def _ending_soon(state):
	"""Two units sold about 11 months ago, so the Warranty Ending report has something to show."""
	if not frappe.db.get_value("Serial No", "DEMO-0004", "custom_invoice_no"):
		_sell(["DEMO-0004", "DEMO-0005"], _settings().loaner_source_warehouse)
	for serial, days in (("DEMO-0004", 12), ("DEMO-0005", 26)):
		frappe.db.set_value(
			"Serial No",
			serial,
			{
				"custom_invoice_date": add_days(today(), days - 365),
				"custom_warranty_end": add_days(today(), days),
				"custom_amc_enquiry_sent": 0,
			},
		)


def _client_login(state):
	"""Make sure the demo customer can log in to the portal with the password in LOGINS.txt."""
	_logins()
	user = frappe.get_doc("User", CLIENT_USER)
	user.enabled = 1
	if "Customer" not in {r.role for r in user.roles}:
		user.append("roles", {"role": "Customer"})
	user.save()
	update_password(CLIENT_USER, frappe.flags.demo_password)
	# ERPNext's portal lists (/quotations, /orders, /invoices) find the customer through the
	# Customer's "Portal Users" table, not through the Contact.
	customer = frappe.get_doc("Customer", CUSTOMER)
	if CLIENT_USER not in {r.user for r in customer.get("portal_users", [])}:
		customer.append("portal_users", {"user": CLIENT_USER})
		customer.save()
	return {
		"user": user.name,
		"type": user.user_type,
		"enabled": user.enabled,
		"roles": [r.role for r in user.roles],
	}


def _amc_ticket2(state):
	# DEMO-0002: warranty over, AMC now active -> the ticket shows Support Type AMC.
	_new_ticket("DEMO-0002", "Fan error on start-up", "amc_ticket2", state)
