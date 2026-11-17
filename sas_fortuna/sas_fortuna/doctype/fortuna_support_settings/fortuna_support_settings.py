# Copyright (c) 2026, SAS Infosystem Pvt Ltd and contributors
# For license information, please see license.txt

"""Fortuna Support Settings: every value the support code would otherwise hard-code.

Fortuna's open points (advance %, AMC repair charges, replacement warranty,
SIM billing) are settings here, so their answers need no code change.
Read in code through sas_fortuna.support.utils.get_settings / require_setting.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, validate_email_address


class FortunaSupportSettings(Document):
	def validate(self):
		# The advance only matters when payment is due before the repair starts;
		# Fortuna's default (Dispatch) always needs 100% before the unit ships.
		if self.payment_due_before == "Repair Start" and not 0 < flt(self.advance_percent) <= 100:
			frappe.throw(_("Advance Required % must be between 1 and 100."))
		for field in ("default_warranty_days", "amc_enquiry_lead_days", "sim_order_lead_days"):
			if cint(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))
		# Mail lists: throws on any address that is not a valid e-mail.
		for field in ("amc_team_email", "amc_alert_cc", "sim_reminder_cc"):
			if self.get(field):
				validate_email_address(self.get(field), throw=True)
		self._check_reminder_days()
		self._check_warehouses_belong_to_company()
		self._check_dedicated_warehouses()
		self._check_unique_routes()

	def _check_warehouses_belong_to_company(self):
		for field in (
			"repair_in_warehouse",
			"repair_wip_warehouse",
			"spares_warehouse",
			"loaner_source_warehouse",
			"customer_loaner_warehouse",
		):
			warehouse = self.get(field)
			if warehouse and frappe.db.get_value("Warehouse", warehouse, "company") != self.company:
				frappe.throw(_("{0} does not belong to {1}.").format(warehouse, self.company))

	def _check_dedicated_warehouses(self):
		"""Repair-In, Repair WIP and Customer Loaner must each be a warehouse of
		their own: customer units (zero value), reserved spares and loaners out
		with customers would otherwise mix, and stock reports go wrong.
		Spares and Loaner Source may share one store (e.g. Stores)."""
		dedicated = ("repair_in_warehouse", "repair_wip_warehouse", "customer_loaner_warehouse")
		others = ("spares_warehouse", "loaner_source_warehouse")
		for field in dedicated:
			warehouse = self.get(field)
			if not warehouse:
				continue
			for other in dedicated + others:
				if other != field and self.get(other) == warehouse:
					frappe.throw(
						_("{0} and {1} cannot both be {2}. Use a separate warehouse for {0}.").format(
							self.meta.get_label(field), self.meta.get_label(other), warehouse
						)
					)

	def _check_reminder_days(self):
		"""'30, 15' style list of whole days; anything else is a typo worth stopping on."""
		for part in (self.sim_reminder_days or "").split(","):
			if part.strip() and not part.strip().isdigit():
				frappe.throw(_("Customer Reminder Days: use whole days separated by commas, e.g. 30, 15."))

	def _check_unique_routes(self):
		"""One row per Ticket Type + Job Location (blank location = the type's fallback team)."""
		seen = set()
		for row in self.team_routing:
			key = (row.ticket_type, row.get("job_location") or None)
			if key in seen:
				where = row.get("job_location") or _("all locations")
				frappe.throw(_("Ticket Type {0} is routed twice for {1}.").format(row.ticket_type, where))
			seen.add(key)
