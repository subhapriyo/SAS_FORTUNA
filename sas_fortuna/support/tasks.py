"""Daily scheduled jobs  (F1, N2, N10, SIM renewal reminders).

Wired in hooks.py -> scheduler_events["daily"]. Each job is idempotent:
a flag or link on the record stops it from repeating tomorrow.
Test one manually:
    bench --site fortuna.localhost execute sas_fortuna.support.tasks.send_amc_enquiries
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today

from sas_fortuna.support.opportunity import make_amc_opportunity
from sas_fortuna.support.utils import get_settings


# ---------------------------------------------------------------------------
# F1  Warranty ending soon -> AMC team mail (+ optional Opportunity)
# ---------------------------------------------------------------------------
def send_amc_enquiries():
	settings = get_settings()
	lead_days = cint(settings.amc_enquiry_lead_days) or 30
	serials = frappe.get_all(
		"Serial No",
		filters={
			"custom_warranty_end": ["between", [today(), add_days(today(), lead_days)]],
			"custom_amc_enquiry_sent": 0,
			"custom_amc_status": ["!=", "Active"],
		},
		fields=["name", "item_code", "custom_sold_to", "custom_warranty_end"],
	)
	if not serials:
		return

	for s in serials:
		if settings.create_amc_opportunities and s.custom_sold_to:
			try:
				# Fills fortuna_erp's CRM fields from the customer (see opportunity.py).
				make_amc_opportunity(s, settings)
			except Exception:
				# One bad record must not stop the run: log it and still flag the
				# serial below, or the AMC team would get the same unit every day.
				frappe.log_error(title=f"AMC enquiry: Opportunity for {s.name} failed")
		# The mail (and the Warranty Ending report) is the enquiry; flag it as sent.
		frappe.db.set_value("Serial No", s.name, "custom_amc_enquiry_sent", 1)

	if settings.amc_team_email:
		# Fortuna: subscription@ receives, info@ and amc@ are copied (AMC Alert CC).
		rows = "".join(
			f"<tr><td>{s.name}</td><td>{s.item_code}</td><td>{s.custom_sold_to or ''}</td>"
			f"<td>{frappe.format(s.custom_warranty_end, 'Date')}</td></tr>"
			for s in serials
		)
		frappe.sendmail(
			recipients=split_emails(settings.amc_team_email),
			cc=split_emails(settings.get("amc_alert_cc")),
			subject=_("AMC enquiries: {0} warranties ending soon").format(len(serials)),
			message=(
				"<p>Warranty ends within the next {} days for:</p>"
				"<table border='1' cellpadding='4'><tr><th>Serial</th><th>Item</th>"
				"<th>Customer</th><th>Warranty End</th></tr>{}</table>"
			).format(lead_days, rows),
		)


# ---------------------------------------------------------------------------
# N2  Flag overdue loaners (the Notification sends the reminder mail)
# ---------------------------------------------------------------------------
def mark_overdue_gate_passes():
	frappe.db.set_value(
		"Returnable Gate Pass",
		{"docstatus": 1, "status": "Open", "expected_return_date": ["<", today()]},
		"status",
		"Overdue",
	)


# ---------------------------------------------------------------------------
# N10  SIM recharge -> one draft Sales Order per customer
# ---------------------------------------------------------------------------
def create_sim_recharge_orders():
	settings = get_settings()
	if settings.sim_billing_mode != "Service Order" or not settings.sim_recharge_item:
		return  # Subscription mode: E1/E2 handles billing, nothing to do here
	lead_days = cint(settings.sim_order_lead_days) or 30
	due = frappe.get_all(
		"Serial No",
		filters={
			"custom_sim_valid_till": ["between", [today(), add_days(today(), lead_days)]],
			"custom_sim_order": ["is", "not set"],
			"custom_sold_to": ["is", "set"],
		},
		fields=["name", "custom_sold_to", "custom_sim_valid_till"],
	)

	by_customer = defaultdict(list)
	for s in due:
		by_customer[s.custom_sold_to].append(s)

	for customer, serials in by_customer.items():
		so = frappe.new_doc("Sales Order")
		so.company = settings.company
		so.customer = customer
		so.delivery_date = min(s.custom_sim_valid_till for s in serials)
		# Sales Order has no Remarks field: list the serials on the order line,
		# where they also print, and in a comment.
		serial_list = _("SIM recharge for serials: {0}").format(", ".join(s.name for s in serials))
		so.append(
			"items",
			{"item_code": settings.sim_recharge_item, "qty": len(serials), "description": serial_list},
		)
		try:
			so.insert(ignore_permissions=True)  # stays Draft for review
			so.add_comment("Comment", serial_list)
		except Exception:
			frappe.log_error(title=f"SIM recharge order for {customer} failed")
			continue
		for s in serials:
			frappe.db.set_value("Serial No", s.name, "custom_sim_order", so.name)


# ---------------------------------------------------------------------------
# SIM renewal reminders to the customer (Fortuna: yearly subscription,
# e-mail 30 and 15 days before, to the customer's default contact, CC info@ and hr@)
# ---------------------------------------------------------------------------
SIM_REMINDER_TEMPLATE = "Fortuna SIM Renewal Reminder"


def split_emails(value):
	"""'a@x.com, b@x.com' -> ['a@x.com', 'b@x.com']; blank -> []."""
	return [e.strip() for e in (value or "").split(",") if e.strip()]


def reminder_days(value):
	"""'30, 15' -> [30, 15]: whole days, largest first; anything else is ignored."""
	days = {cint(part) for part in (value or "").split(",") if part.strip().isdigit()}
	return sorted((d for d in days if d > 0), reverse=True)


def send_sim_renewal_reminders():
	"""One e-mail per customer per reminder interval, listing their SIMs that run out.

	Each Serial No counts the reminders already sent for its current validity
	(custom_sim_reminders_sent). Reminder n is due once the days left drop to the
	n-th interval, so a day the scheduler misses is caught up the next day, and a
	unit never gets the same reminder twice. A new validity date resets the count
	(sales.serial_no_validate).
	"""
	settings = get_settings()
	intervals = reminder_days(settings.get("sim_reminder_days"))
	if not intervals:
		return
	serials = frappe.get_all(
		"Serial No",
		filters={
			"custom_sim_valid_till": ["between", [today(), add_days(today(), intervals[0])]],
			"custom_sold_to": ["is", "set"],
			"custom_sim_reminders_sent": ["<", len(intervals)],
		},
		fields=[
			"name",
			"item_code",
			"custom_sold_to",
			"custom_sim_no",
			"custom_sim_valid_till",
			"custom_sim_reminders_sent",
		],
		order_by="custom_sim_valid_till asc",
	)
	by_customer = defaultdict(list)
	for s in serials:
		days_left = date_diff(s.custom_sim_valid_till, today())
		due = sum(1 for d in intervals if days_left <= d)  # reminders that should have gone out by now
		if due > cint(s.custom_sim_reminders_sent):
			s.due = due
			by_customer[s.custom_sold_to].append(s)

	cc = split_emails(settings.get("sim_reminder_cc"))
	for customer, rows in by_customer.items():
		try:
			_send_sim_reminder(customer, rows, cc)
		except Exception:
			frappe.log_error(title=f"SIM renewal reminder for {customer} failed")
			continue
		for s in rows:
			frappe.db.set_value("Serial No", s.name, "custom_sim_reminders_sent", s.due)


def _send_sim_reminder(customer, rows, cc):
	"""Mail the customer's default contact; without one, the CC list gets it flagged."""
	customer_name, email = frappe.db.get_value("Customer", customer, ["customer_name", "email_id"])
	context = {
		"customer": customer,
		"customer_name": customer_name or customer,
		"rows": rows,
		"valid_till": min(getdate(r.custom_sim_valid_till) for r in rows),
	}
	subject, message = _sim_reminder_text(context)
	recipients = [email] if email else cc
	if not recipients:
		frappe.log_error(title=f"SIM renewal reminder: no e-mail for {customer}")
		return
	if not email:
		subject = _("[No customer e-mail] {0}").format(subject)
	frappe.sendmail(
		recipients=recipients,
		cc=cc if email else [],
		subject=subject,
		message=message,
		reference_doctype="Customer",
		reference_name=customer,
	)


def _sim_reminder_text(context):
	"""Subject and body from the Email Template (editable in Desk), else a plain default."""
	if frappe.db.exists("Email Template", SIM_REMINDER_TEMPLATE):
		tpl = frappe.get_doc("Email Template", SIM_REMINDER_TEMPLATE)
		return (
			frappe.render_template(tpl.subject, context),
			frappe.render_template(tpl.response_html or tpl.response, context),
		)
	lines = "".join(
		f"<tr><td>{r.name}</td><td>{r.custom_sim_no or ''}</td>"
		f"<td>{frappe.format(r.custom_sim_valid_till, 'Date')}</td></tr>"
		for r in context["rows"]
	)
	subject = _("SIM renewal due on {0}").format(frappe.format(context["valid_till"], "Date"))
	message = _("Dear {0},").format(context["customer_name"]) + (
		"<p>The yearly SIM subscription for the devices below is due for renewal.</p>"
		"<table border='1' cellpadding='4'><tr><th>Serial No</th><th>SIM No</th><th>Valid Till</th></tr>"
		f"{lines}</table>"
	)
	return subject, message
