"""Daily scheduled jobs  (F1, N2, N10).

Wired in hooks.py -> scheduler_events["daily"]. Each job is idempotent:
a flag or link on the record stops it from repeating tomorrow.
Test one manually:
    bench --site fortuna.localhost execute sas_fortuna.support.tasks.send_amc_enquiries
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, today

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
				opp = frappe.new_doc("Opportunity")
				opp.opportunity_from = "Customer"
				opp.party_name = s.custom_sold_to
				opp.custom_serial_no = s.name
				opp.append("items", {"item_code": s.item_code, "qty": 1})
				opp.insert(ignore_permissions=True)  # other apps' Opportunity hooks run here too
			except Exception:
				# One bad record (e.g. a validation in another app) must not stop the
				# whole run: log it, still mail the AMC team, try again tomorrow.
				frappe.log_error(title=f"AMC enquiry: Opportunity for {s.name} failed")
				continue
		frappe.db.set_value("Serial No", s.name, "custom_amc_enquiry_sent", 1)

	if settings.amc_team_email:
		rows = "".join(
			f"<tr><td>{s.name}</td><td>{s.item_code}</td><td>{s.custom_sold_to or ''}</td>"
			f"<td>{frappe.format(s.custom_warranty_end, 'Date')}</td></tr>"
			for s in serials
		)
		frappe.sendmail(
			recipients=[e.strip() for e in settings.amc_team_email.split(",")],
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
		so.append("items", {"item_code": settings.sim_recharge_item, "qty": len(serials)})
		so.remarks = _("SIM recharge for serials: {0}").format(", ".join(s.name for s in serials))
		try:
			so.insert(ignore_permissions=True)  # stays Draft for review
		except Exception:
			frappe.log_error(title=f"SIM recharge order for {customer} failed")
			continue
		for s in serials:
			frappe.db.set_value("Serial No", s.name, "custom_sim_order", so.name)
