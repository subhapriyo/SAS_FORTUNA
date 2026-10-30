"""Acceptance tests: customer portal /tickets (Helpdesk tickets, replaces /issues). Rolled back.

bench --site fortuna.localhost execute sas_fortuna.support.test_portal_tickets.run
"""

import frappe

from sas_fortuna.support.test_phase01 import RESULTS, _customer, check

CUSTOMER = "Test Company 1"
USER_A, USER_B = "zz.tickets.a@example.com", "zz.tickets.b@example.com"


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	try:
		_tests()
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nSummary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _portal_user(email, customer):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "ZZ Tickets",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)
	user.add_roles("Customer")
	frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": "ZZ Tickets",
			"user": email,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	).insert(ignore_permissions=True)


def _ticket(user, subject, **extra):
	"""Raise a ticket as `user`, like the portal's New ticket form does."""
	frappe.set_user(user)
	try:
		t = frappe.get_doc(
			dict(
				{
					"doctype": "HD Ticket",
					"subject": subject,
					"description": "ZZ test",
					"raised_by": user,
					"ticket_type": "Software",
				},
				**extra,
			)
		)
		t.insert(ignore_permissions=True)
		return t
	finally:
		frappe.set_user("Administrator")


def _list_for(user, **filters):
	from sas_fortuna.support.portal_tickets import get_ticket_list

	frappe.set_user(user)
	try:
		return [r.name for r in get_ticket_list("HD Ticket", None, dict(filters), 0, 100)]
	finally:
		frappe.set_user("Administrator")


def _detail_for(user, name):
	from sas_fortuna.www import ticket as page

	frappe.set_user(user)
	frappe.form_dict.name = name
	try:
		return page.get_context(frappe._dict())
	finally:
		frappe.set_user("Administrator")


def _tests():
	print("\n== 1. Portal users get Helpdesk's customer role (New ticket / Reply work)")
	other = _customer("ZZ Tickets Other")
	_portal_user(USER_A, CUSTOMER)
	_portal_user(USER_B, other.name)
	check("Customer A's portal user has the HD Customer role", "HD Customer" in frappe.get_roles(USER_A))

	print("\n== 2. /tickets lists only the customer's own tickets")
	ta = _ticket(USER_A, "ZZ A printer jams")
	tb = _ticket(USER_B, "ZZ B screen dark")
	check(
		"Ticket raised by A is stamped with A's customer",
		ta.custom_erpnext_customer == CUSTOMER,
		str(ta.custom_erpnext_customer),
	)
	names_a = _list_for(USER_A)
	check("A sees their ticket", ta.name in names_a)
	check("A does not see B's ticket", tb.name not in names_a)
	check("Status filter works", ta.name not in _list_for(USER_A, status="Closed"))
	check("Desk user without a customer gets an empty portal list", _list_for("Administrator") == [])

	print("\n== 3. /tickets/<name> detail page")
	ctx = _detail_for(USER_A, ta.name)
	check("A opens their ticket", ctx.doc.name == ta.name and ctx.status_color)
	check("Reply in Helpdesk is offered to the person who raised it", ctx.reply_url.endswith(ta.name))
	for who, label in ((USER_B, "B cannot open A's ticket"), ("Guest", "Guests are asked to log in")):
		try:
			_detail_for(who, ta.name)
			check(label, False)
		except frappe.PermissionError:
			check(label, True)

	print("\n== 4. New ticket form: type and serial")
	from sas_fortuna.support.portal import customer_serials, customer_ticket_types
	from sas_fortuna.support.test_phase01 import expect_error
	from sas_fortuna.support.utils import get_serial_coverage

	# A unit of customer A: one already sold to Test Company 1 by the earlier test phases.
	own_serial = next(
		(
			s
			for s in frappe.get_all("Serial No", filters={"custom_sold_to": CUSTOMER}, pluck="name")
			if get_serial_coverage(s).customer == CUSTOMER
		),
		None,
	)
	if not own_serial:
		check("A unit sold to customer A exists (run phases 01-03 first)", False)
		return
	frappe.set_user(USER_A)
	try:
		types, serials = customer_ticket_types(), [s["value"] for s in customer_serials()]
	finally:
		frappe.set_user("Administrator")
	check(
		"Ticket types offered are the routed ones",
		set(types) == {"Software", "Hardware", "Post-Installation"},
		str(types),
	)
	check("Serial choices: A's own unit", own_serial in serials, str(serials[:5]))
	check("Serial choices: never another customer's unit", "DEMO-0001" not in serials)
	t = _ticket(USER_A, "ZZ A unit fault", ticket_type="Hardware", custom_serial_no=own_serial)
	check(
		"Ticket with A's own serial: routed to Hardware Support",
		t.agent_group == "Hardware Support",
		str(t.agent_group),
	)
	check(
		"...and checked for warranty", bool(t.custom_support_type) and t.custom_erpnext_customer == CUSTOMER
	)
	expect_error(
		"Ticket with another customer's serial is refused",
		lambda: _ticket(USER_A, "ZZ not my unit", ticket_type="Hardware", custom_serial_no="DEMO-0001"),
		"not registered to your account",
	)
	t2 = _ticket(USER_A, "ZZ no serial", ticket_type="Hardware")
	check("Serial is optional", bool(t2.name) and not t2.custom_serial_no)
	t2.reload()
	t2.custom_serial_no = own_serial
	t2.save(ignore_permissions=True)  # as Administrator, i.e. a Helpdesk agent in the backend
	check(
		"An agent can add the serial later",
		t2.custom_serial_no == own_serial and bool(t2.custom_support_type),
	)

	print("\n== 5. Portal menu: Tickets replaces Issues")
	s = frappe.get_single("Portal Settings")
	check("Tickets entry in the portal menu", any(r.route == "/tickets" and r.enabled for r in s.custom_menu))
	check("Standard Issues link switched off", not any(r.route == "/issues" and r.enabled for r in s.menu))
