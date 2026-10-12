"""Controller for the 'Repair Order' DocType  (D1, D3, D5, D6).

The form, fields and workflow are CONFIG (built in the DocType editor and
Workflow list). This file only does what config cannot:
  * copy details from the Helpdesk ticket / serial number,
  * default the invoice method from the support type,
  * total the chargeable parts,
  * mirror the repair status back onto the ticket.
Buttons (receipt, spares, quotation, dispatch) live in support/repair.py.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from sas_fortuna.support.utils import SUPPORT_AMC, SUPPORT_WARRANTY, get_erpnext_customer, get_serial_coverage

# Support Type -> default Invoice Method (Fortuna can still change it).
DEFAULT_INVOICE_METHOD = {
	SUPPORT_WARRANTY: "Free (Warranty)",
	SUPPORT_AMC: "AMC",
}


class RepairOrder(Document):
	def validate(self):
		self.pull_from_ticket()
		self.apply_coverage()
		if not self.invoice_method:
			self.invoice_method = DEFAULT_INVOICE_METHOD.get(self.support_type, "Chargeable")
		self.total_parts()

	def on_update(self):
		# Show repair progress on the ticket (db_set: no ticket e-mails fired).
		if self.helpdesk_ticket:
			frappe.db.set_value(
				"HD Ticket",
				self.helpdesk_ticket,
				{"custom_repair_order": self.name, "custom_repair_status": self.status},
			)

	# -- helpers ------------------------------------------------------------
	def pull_from_ticket(self):
		"""Fill blanks from the originating ticket: no re-entry for the agent."""
		if not self.helpdesk_ticket:
			return
		t = frappe.db.get_value(
			"HD Ticket",
			self.helpdesk_ticket,
			[
				"customer",
				"custom_erpnext_customer",
				"custom_product_model",
				"custom_serial_no",
				"description",
			],
			as_dict=True,
		)
		self.customer = self.customer or t.custom_erpnext_customer or get_erpnext_customer(t.customer)
		self.product_model = self.product_model or t.custom_product_model
		self.serial_no = self.serial_no or t.custom_serial_no
		self.complaint = self.complaint or t.description

	def apply_coverage(self):
		"""Same Warranty / AMC / Paid rule as the ticket (C2)."""
		if not self.serial_no or (not self.has_value_changed("serial_no") and self.support_type):
			return
		info = get_serial_coverage(self.serial_no)
		self.product_model = info.item_code
		self.customer = self.customer or info.customer
		self.invoice_no = info.invoice_no
		self.invoice_date = info.invoice_date
		self.warranty_end = info.warranty_end
		self.amc_expiry = info.amc_expiry
		self.support_type = info.support_type

	def total_parts(self):
		"""Row amount = qty x rate; only chargeable rows roll up for billing."""
		total = 0
		for part in self.parts:
			part.amount = flt(part.qty) * flt(part.rate)
			if part.is_chargeable:
				total += part.amount
		self.parts_chargeable_total = total

	@property
	def is_chargeable(self):
		return self.invoice_method == "Chargeable"
