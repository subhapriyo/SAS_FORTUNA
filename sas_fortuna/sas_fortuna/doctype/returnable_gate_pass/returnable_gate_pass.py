"""Controller for 'Returnable Gate Pass'  (N1, N2).

A loaner unit leaves Fortuna on this pass and must come back by the
expected return date. Submitting the pass moves the unit from stores to
the 'Customer Loaner' warehouse; 'Mark Returned' moves it back.
Stock always follows the paper: no pass, no movement.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from sas_fortuna.support.utils import require_setting


class ReturnableGatePass(Document):
	def validate(self):
		if getdate(self.expected_return_date) < getdate(self.issue_date):
			frappe.throw(_("Expected Return Date cannot be before Issue Date."))
		if self.docstatus == 0:
			self.status = "Draft"

	def on_submit(self):
		# Loaner goes out: Stores -> Customer Loaner.
		se = self._transfer(
			require_setting("loaner_source_warehouse"), require_setting("customer_loaner_warehouse")
		)
		self.db_set({"issue_stock_entry": se, "status": "Open"})

	def on_cancel(self):
		for field in ("return_stock_entry", "issue_stock_entry"):
			name = self.get(field)
			if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
				frappe.get_doc("Stock Entry", name).cancel()
		self.db_set("status", "Cancelled")

	def _transfer(self, source, target):
		"""Create AND submit a one-line transfer (fails cleanly if no stock)."""
		se = frappe.new_doc("Stock Entry")
		se.company = require_setting("company")
		se.purpose = se.stock_entry_type = "Material Transfer"
		se.custom_repair_order = self.repair_order
		se.remarks = _("Returnable Gate Pass {0}").format(self.name)
		se.append(
			"items",
			{
				"item_code": self.item_code,
				"qty": 1,
				"s_warehouse": source,
				"t_warehouse": target,
				"use_serial_batch_fields": 1,
				"serial_no": self.serial_no,
				# Items that track batches too need the serial's batch on every move.
				"batch_no": frappe.db.get_value("Serial No", self.serial_no, "batch_no"),
			},
		)
		# System move: the user may submit gate passes without Stock Entry rights.
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		return se.name


@frappe.whitelist()
def mark_returned(gate_pass):
	"""Button: loaner is back -> Customer Loaner -> Stores, close the pass."""
	gp = frappe.get_doc("Returnable Gate Pass", gate_pass)
	gp.check_permission("write")
	if gp.status not in ("Open", "Overdue"):
		frappe.throw(_("Only open passes can be marked returned."))
	se = gp._transfer(
		require_setting("customer_loaner_warehouse"), require_setting("loaner_source_warehouse")
	)
	gp.db_set({"return_stock_entry": se, "returned_on": today(), "status": "Returned"})
	return se
