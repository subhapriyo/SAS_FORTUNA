"""Phase 0-1 acceptance tests. Everything is rolled back; nothing is left behind.

bench --site fortuna.localhost execute sas_fortuna.support.test_phase01.run
"""

import frappe

RESULTS = []


def check(name, ok, detail=""):
	RESULTS.append((name, bool(ok)))
	print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def expect_error(name, fn, must_contain=""):
	try:
		fn()
	except frappe.ValidationError as e:
		msg = str(e)
		check(name, must_contain.lower() in msg.lower(), f"message: {msg[:120]}")
		return
	finally:
		frappe.clear_messages()
	check(name, False, "no error raised")


def _leaf(doctype):
	return frappe.get_all(doctype, filters={"is_group": 0}, pluck="name", limit=1)[0]


def _customer(name):
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": _leaf("Customer Group"),
			"territory": _leaf("Territory"),
		}
	).insert(ignore_permissions=True)


def run():
	frappe.flags.mute_emails = True
	try:
		_masters()
		_settings_validation()
		_customer_sync()
		_coverage()
		_landing_page()
	finally:
		frappe.db.rollback()
	_idempotent()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _masters():
	print("\n== 1. Phase 0-1 masters")
	s = frappe.get_single("Fortuna Support Settings")
	acc = frappe.db.get_value(
		"Account", s.warranty_expense_account, ["is_group", "parent_account", "root_type"], as_dict=True
	)
	check(
		"Warranty Expense is a ledger under Indirect Expenses",
		acc and not acc.is_group and "Indirect Expenses" in acc.parent_account,
	)
	for field in ("service_charge_item", "freight_item", "sim_recharge_item"):
		item = frappe.db.get_value("Item", s.get(field), ["is_stock_item", "gst_hsn_code"], as_dict=True)
		check(
			f"{field}: non-stock with SAC",
			item and not item.is_stock_item and (item.gst_hsn_code or "").startswith("99"),
		)
	for t in ("Software", "Hardware", "Post-Installation"):
		check(f"Ticket type {t}", frappe.db.exists("HD Ticket Type", t))
	check(
		"Paused status pauses the SLA",
		frappe.db.get_value("HD Ticket Status", "Paused", "category") == "Paused",
	)
	for team in ("Software Support", "Hardware Support"):
		rule = frappe.db.get_value("HD Team", team, "assignment_rule")
		check(f"Team {team} has an assignment rule", rule and frappe.db.exists("Assignment Rule", rule))
	routes = {r.ticket_type: r.team for r in s.team_routing}
	check("Routing: Software -> Software Support", routes.get("Software") == "Software Support")
	check("Routing: Hardware -> Hardware Support", routes.get("Hardware") == "Hardware Support")
	check(
		"Routing covers every Fortuna ticket type",
		set(routes) >= {"Software", "Hardware", "Post-Installation"},
	)
	events = frappe.get_hooks("doc_events")
	check(
		"Hook Customer.after_insert wired",
		"sas_fortuna.support.customer_sync.customer_after_insert"
		in events.get("Customer", {}).get("after_insert", []),
	)
	check(
		"Hook Contact.validate wired",
		"sas_fortuna.support.customer_sync.contact_validate" in events.get("Contact", {}).get("validate", []),
	)


def _settings_validation():
	print("\n== 2. Settings refuse bad values")

	def with_change(**changes):
		doc = frappe.get_doc("Fortuna Support Settings")
		doc.update(changes)
		return doc

	expect_error(
		"Advance 0% refused",
		lambda: with_change(advance_percent=0).run_method("validate"),
		"between 1 and 100",
	)
	expect_error(
		"Advance 150% refused",
		lambda: with_change(advance_percent=150).run_method("validate"),
		"between 1 and 100",
	)
	s = frappe.get_single("Fortuna Support Settings")
	expect_error(
		"Repair-In = Repair WIP refused",
		lambda: with_change(repair_wip_warehouse=s.repair_in_warehouse).run_method("validate"),
		"cannot both be",
	)
	expect_error(
		"Customer Loaner = Stores refused",
		lambda: with_change(customer_loaner_warehouse=s.spares_warehouse).run_method("validate"),
		"cannot both be",
	)

	def dup_route():
		doc = frappe.get_doc("Fortuna Support Settings")
		doc.append("team_routing", {"ticket_type": "Software", "team": "Hardware Support"})
		doc.run_method("validate")

	expect_error("Same ticket type routed twice refused", dup_route, "routed twice")
	other = frappe.get_all(
		"Warehouse", filters={"company": ["!=", s.company], "is_group": 0}, pluck="name", limit=1
	)
	if other:
		expect_error(
			"Warehouse of another company refused",
			lambda: with_change(spares_warehouse=other[0]).run_method("validate"),
			"does not belong",
		)
	try:
		frappe.get_doc("Fortuna Support Settings").run_method("validate")
		check("Current settings are valid", True)
	except frappe.ValidationError as e:
		check("Current settings are valid", False, str(e)[:120])


def _customer_sync():
	print("\n== 3. Customer -> Helpdesk customer")
	c = _customer("ZZ Test Customer Phase1")
	hd = frappe.db.get_value("HD Customer", {"custom_erpnext_customer": c.name}, "name")
	check("New Customer creates a linked HD Customer", hd)

	frappe.get_doc({"doctype": "HD Customer", "customer_name": "ZZ Test Pre Existing"}).insert(
		ignore_permissions=True
	)
	c2 = _customer("ZZ Test Pre Existing")
	linked = frappe.get_all(
		"HD Customer",
		filters={"customer_name": "ZZ Test Pre Existing"},
		fields=["name", "custom_erpnext_customer"],
	)
	check(
		"Existing HD Customer of same name is linked, not duplicated",
		len(linked) == 1 and linked[0].custom_erpnext_customer == c2.name,
		str(linked),
	)

	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": "ZZ Test",
			"links": [{"link_doctype": "Customer", "link_name": c.name}],
		}
	).insert(ignore_permissions=True)
	links = {(lk.link_doctype, lk.link_name) for lk in contact.links}
	check("Contact of the Customer is linked to its HD Customer", ("HD Customer", hd) in links, str(links))

	contact.save(ignore_permissions=True)
	count = sum(1 for lk in contact.links if lk.link_doctype == "HD Customer")
	check("Saving the Contact again adds no duplicate link", count == 1, f"{count} links")

	lone = frappe.get_doc({"doctype": "Contact", "first_name": "ZZ Lone"}).insert(ignore_permissions=True)
	check(
		"Contact without a Customer gets no HD link",
		not any(lk.link_doctype == "HD Customer" for lk in lone.links),
	)


def _coverage():
	print("\n== 4. Warranty / AMC / Paid rule (regression)")
	from sas_fortuna.support.utils import get_serial_coverage

	if not frappe.db.exists("Serial No", "TSN-0001"):
		print("  [SKIP] test serial TSN-0001 not found")
		return
	check("TSN-0001 today -> Warranty", get_serial_coverage("TSN-0001")["support_type"] == "Warranty")
	check(
		"TSN-0001 in 2028 -> Paid Service",
		get_serial_coverage("TSN-0001", "2028-01-01")["support_type"] == "Paid Service",
	)
	frappe.db.set_value("Serial No", "TSN-0001", "amc_expiry_date", "2028-06-30")
	check(
		"TSN-0001 in 2028 with AMC -> AMC",
		get_serial_coverage("TSN-0001", "2028-01-01")["support_type"] == "AMC",
	)
	check("Warranty beats AMC today", get_serial_coverage("TSN-0001")["support_type"] == "Warranty")


def _landing_page():
	print("\n== 5. Landing page")
	block = frappe.db.get_value("Custom HTML Block", "SAS Fortuna Home", ["html", "private"], as_dict=True)
	check("Block exists and is public", block and not block.private)
	html = block.html if block else ""
	for title in (
		"Customer &amp; Supplier Onboarding",
		"Portal Setup",
		"Support Desk, Repair &amp; AMC",
		"Support Reports",
	):
		check(f"Section shown: {title.replace('&amp;', '&')}", title in html)
	check("Portal pages section removed", "Portal pages" not in html and "/supplier-registration" not in html)
	check(
		"Workspace uses the block",
		"SAS Fortuna Home" in (frappe.db.get_value("Workspace", "SAS Fortuna", "content") or ""),
	)


def _idempotent():
	print("\n== 6. Re-running create_masters changes nothing")
	from sas_fortuna.setup.support_desk import create_masters

	out = create_masters()
	check("create_masters is safe to re-run", out.get("created") == "nothing new", str(out))
