"""Controller for the 'Repair Order' DocType  (D1, D3, D5, D6).

The form, fields and workflow are CONFIG (built in the DocType editor and
Workflow list). This file only does what config cannot:
  * copy details from the Helpdesk ticket / serial number,
  * default the invoice method from the support type,
  * charge AMC-excluded parts (consumables) even on a free AMC repair,
  * total the chargeable parts,
  * mirror the repair status back onto the ticket.
Buttons (receipt, spares, quotation, dispatch) live in support/repair.py.
"""

import html
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from sas_fortuna.support.utils import (
	SUPPORT_AMC,
	SUPPORT_WARRANTY,
	get_erpnext_customer,
	get_serial_coverage,
	get_settings,
)

# A repair is finished in these states; any other state counts as open.
CLOSED_STATES = ("Dispatched", "Closed", "Cancelled")
# Fixed once the customer's unit is in our Repair-In store.
LOCKED_AFTER_RECEIPT = ("customer", "product_model", "serial_no")

# Support Type -> default Invoice Method (Fortuna can still change it).
DEFAULT_INVOICE_METHOD = {
	SUPPORT_WARRANTY: "Free (Warranty)",
	SUPPORT_AMC: "AMC",
}


# End of a paragraph / line in the Helpdesk editor's HTML.
_LINE_END = re.compile(r"<br\s*/?>|</(p|div|li|h[1-6])>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def plain_text(value):
	"""Ticket description (HTML from the Helpdesk editor) -> plain text for Complaint.

	Paragraphs and line breaks become new lines; tags go, entities (&amp;) are decoded.
	"""
	if not value:
		return ""
	text = html.unescape(_TAG.sub("", _LINE_END.sub("\n", value)))
	return "\n".join(line.strip() for line in text.splitlines() if line.strip())


# Fields a new Repair Order takes from its Helpdesk ticket (see pull_from_ticket).
FROM_TICKET = ("customer", "product_model", "serial_no", "complaint")


@frappe.whitelist()
def ticket_details(ticket):
	"""What a new Repair Order copies from `ticket`, for the form to show before saving.

	Runs the same pull_from_ticket() as save, so the form and the server never disagree.
	"""
	if not ticket:
		return {}
	frappe.has_permission("HD Ticket", "read", ticket, throw=True)
	doc = frappe.new_doc("Repair Order")
	doc.helpdesk_ticket = ticket
	doc.pull_from_ticket()
	return {field: doc.get(field) for field in FROM_TICKET}


def get_list_context(context=None):
	"""Customer portal list at /repairs (see support/portal_repairs.py)."""
	from sas_fortuna.support.portal_repairs import list_context

	return list_context(context)


class RepairOrder(Document):
	def validate(self):
		self.pull_from_ticket()
		self.apply_coverage()
		if not self.invoice_method:
			self.invoice_method = DEFAULT_INVOICE_METHOD.get(self.support_type, "Chargeable")
		self.check_one_open_repair_per_serial()
		self.check_locked_after_receipt()
		self.check_delivery_address()
		self.mark_amc_excluded_parts()
		self.check_parts()
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
		# Complaint is plain text; the ticket description is HTML.
		self.complaint = self.complaint or plain_text(t.description)

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

	# -- rules --------------------------------------------------------------
	def check_one_open_repair_per_serial(self):
		"""One unit, one open repair: a second one could never receive the unit."""
		if not self.serial_no or self.status in CLOSED_STATES:
			return
		other = frappe.db.get_value(
			"Repair Order",
			{"serial_no": self.serial_no, "name": ("!=", self.name), "status": ("not in", CLOSED_STATES)},
			"name",
		)
		if other:
			frappe.throw(_("Serial No {0} already has an open repair: {1}.").format(self.serial_no, other))

	def check_locked_after_receipt(self):
		"""The receipt moved this exact serial for this customer into stock."""
		if self.is_new() or not self.repair_receipt:
			return
		for field in LOCKED_AFTER_RECEIPT:
			if self.has_value_changed(field):
				frappe.throw(
					_(
						"{0} cannot be changed after the unit is received ({1}). Cancel the receipt first."
					).format(_(self.meta.get_label(field)), self.repair_receipt)
				)

	def check_delivery_address(self):
		"""The unit goes back to this address: it must be the customer's own."""
		if not (self.delivery_address and self.customer):
			return
		if not frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": self.delivery_address,
				"link_doctype": "Customer",
				"link_name": self.customer,
			},
		):
			frappe.throw(
				_("Address {0} does not belong to {1}.").format(self.delivery_address, self.customer)
			)

	# -- AMC exclusions ---------------------------------------------------------
	def _amc_excluded_items(self):
		"""Item codes on this repair ticked 'Not Covered by AMC' on the Item."""
		codes = list({p.item_code for p in self.parts if p.item_code})
		if not codes or not frappe.get_meta("Item").has_field("custom_amc_excluded"):
			return set()
		return set(
			frappe.get_all("Item", filters={"name": ["in", codes], "custom_amc_excluded": 1}, pluck="name")
		)

	def mark_amc_excluded_parts(self):
		"""AMC covers the repair, not consumables (biometric sensor, battery): charge those.

		Only Pending parts change; a part already requested, reserved or consumed is
		tied to stock documents and stays as it is.
		"""
		if self.invoice_method != "AMC":
			return
		excluded = self._amc_excluded_items()
		for part in self.parts:
			if part.item_code in excluded and (part.status or "Pending") == "Pending":
				part.is_chargeable = 1

	def check_parts(self):
		charge_allowed = self.invoice_method == "Chargeable" or (
			self.invoice_method == "AMC" and get_settings().charge_amc_repairs
		)
		excluded = self._amc_excluded_items() if self.invoice_method == "AMC" else set()
		for part in self.parts:
			if flt(part.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be more than 0.").format(part.idx))
			if flt(part.rate) < 0:
				frappe.throw(_("Row {0}: Rate cannot be negative.").format(part.idx))
			if part.is_chargeable and not (charge_allowed or part.item_code in excluded):
				frappe.throw(
					_(
						"Row {0}: {1} is marked Chargeable, but this repair is {2}. "
						"Untick Chargeable, or set Invoice Method to Chargeable."
					).format(part.idx, part.item_code, self.invoice_method)
				)
		self._check_moved_parts_unchanged()

	def _check_moved_parts_unchanged(self):
		"""Parts already requested, reserved or consumed are tied to stock documents."""
		before = self.get_doc_before_save()
		if not before:
			return
		now = {p.name: p for p in self.parts}
		for old in before.parts:
			if old.status == "Pending":
				continue
			new = now.get(old.name)
			if not new:
				frappe.throw(
					_("Row {0} ({1}) is {2} and cannot be removed.").format(
						old.idx, old.item_code, old.status
					)
				)
			if (new.item_code, flt(new.qty), new.is_chargeable) != (
				old.item_code,
				flt(old.qty),
				old.is_chargeable,
			):
				frappe.throw(
					_("Row {0} ({1}) is {2}: item, qty and Chargeable cannot be changed.").format(
						old.idx, old.item_code, old.status
					)
				)

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

	@property
	def is_billable(self):
		"""Customer pays something: a paid repair, or chargeable (excluded) parts on an AMC repair.
		Payment in full is then needed before the unit is dispatched (repair.check_paid_before_dispatch)."""
		return self.is_chargeable or any(p.is_chargeable for p in self.parts)
