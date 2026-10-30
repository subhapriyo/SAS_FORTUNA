"""Customer portal: one repair at /repairs/<name>.  Template: www/repair.html

How the page is reached
    wiring.website_route_rules maps "/repairs/<name>" to this page and puts <name> in
    frappe.form_dict.name. The list it comes from is /repairs (support/portal_repairs.py).

Who may open it
    A customer: only repairs of their own Customer.
    A Desk user: any repair they can read in Desk (handy for support staff checking what a
    customer sees). Everyone else gets "not allowed"; guests are asked to log in.

What it shows
    Status + a plain-words hint, a progress tracker, the unit, the problem / diagnosis, parts,
    any loaner unit, and links to the quotation / order / invoice / dispatch. When the quotation
    is open, the customer can accept it here (support/portal.py: accept_quotation).
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate

from sas_fortuna.support.portal import get_portal_customer
from sas_fortuna.support.portal_repairs import STATUS_COLORS

no_cache = 1  # always fresh: the status changes while the customer watches

# The journey shown in the progress tracker. "Awaiting Payment" only applies to paid repairs.
STEPS = ["Registered", "Unit Received", "Awaiting Payment", "In Repair", "Ready", "Dispatched", "Closed"]

# What each status means for the customer. Plain strings here, translated when the page renders.
STATUS_HINT = {
	"Registered": "We have registered your repair. Please send the unit to us.",
	"Unit Received": "We have received your unit and will inspect it.",
	"Awaiting Payment": "Please accept the quotation and make the payment, so we can start the repair.",
	"In Repair": "Our engineers are repairing your unit.",
	"Ready": "Your unit is repaired and will be dispatched shortly.",
	"Dispatched": "Your unit is on its way back to you.",
	"Closed": "This repair is complete.",
	"Cancelled": "This repair was cancelled.",
}
PAID_HINT = "Payment received, thank you. Our engineer will start the repair shortly."


def get_context(context):
	doc, customer = _load_repair()

	context.no_cache = 1
	context.show_sidebar = True  # the portal left menu
	context.doc = doc
	context.title = doc.name
	context.parents = [{"label": _("Repairs"), "route": "repairs"}]  # breadcrumb back to the list

	# Header: status pill, hint, progress
	context.status_color = STATUS_COLORS.get(doc.status, "gray")
	context.status_hint = _status_hint(doc)
	context.created_on = formatdate(doc.creation)
	context.cancelled = doc.status == "Cancelled"
	context.steps = _progress(doc)

	# Cards
	context.unit = _unit_rows(doc)
	context.parts = _parts(doc)
	context.loaner = _loaner(doc)
	context.links, context.quotation, context.can_accept = _documents(doc, customer)
	return context


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------
def _load_repair():
	"""Return (Repair Order, the viewer's Customer or None), or stop with the right error."""
	name = frappe.form_dict.name
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view your repairs."), frappe.PermissionError)
	if not name or not frappe.db.exists("Repair Order", name):
		raise frappe.DoesNotExistError(_("Repair Order {0} not found").format(name))

	doc = frappe.get_doc("Repair Order", name)
	customer = get_portal_customer()
	allowed = doc.customer == customer if customer else frappe.has_permission("Repair Order", "read", doc=doc)
	if not allowed:
		frappe.throw(_("You are not allowed to view this repair."), frappe.PermissionError)
	return doc, customer


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def _status_hint(doc):
	if doc.status == "Awaiting Payment" and doc.payment_cleared:
		return _(PAID_HINT)  # paid, but the engineer has not pressed Start Repair yet
	return _(STATUS_HINT[doc.status]) if doc.status in STATUS_HINT else ""


def _progress(doc):
	"""Steps for the tracker, each marked done / current / todo."""
	steps = [s for s in STEPS if s != "Awaiting Payment" or doc.invoice_method == "Chargeable"]
	current = steps.index(doc.status) if doc.status in steps else -1  # Cancelled: nothing current
	return [
		{"label": _(step), "state": "done" if i < current else "current" if i == current else "todo"}
		for i, step in enumerate(steps)
	]


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
def _unit_rows(doc):
	"""(label, value) rows for "Your unit"; empty values are left out."""
	rows = [
		(_("Model"), doc.product_model),
		(_("Serial No"), doc.serial_no),
		(_("Cover"), doc.support_type),
		(_("Warranty until"), formatdate(doc.warranty_end) if doc.warranty_end else None),
		(_("AMC until"), formatdate(doc.amc_expiry) if doc.amc_expiry else None),
		(_("Replacement unit"), doc.replacement_serial),
	]
	return [(label, value) for label, value in rows if value]


def _parts(doc):
	"""Parts table. The price is shown only for parts the customer pays for."""
	currency = frappe.db.get_default("currency")
	return [
		{
			"item": p.item_name or frappe.db.get_value("Item", p.item_code, "item_name") or p.item_code,
			"qty": int(p.qty) if flt(p.qty).is_integer() else flt(p.qty),  # "1", not "1.0"
			"billing": _("Chargeable") if p.is_chargeable else _("Free"),
			"amount": fmt_money(p.amount, currency=currency) if p.is_chargeable else "",
		}
		for p in doc.parts
	]


def _loaner(doc):
	"""The latest submitted loaner gate pass for this repair, if any."""
	loaner = frappe.db.get_value(
		"Returnable Gate Pass",
		{"repair_order": doc.name, "docstatus": 1},
		["serial_no", "item_code", "expected_return_date", "status", "returned_on"],
		as_dict=True,
		order_by="creation desc",
	)
	if loaner:
		loaner.return_by = formatdate(loaner.expected_return_date)
	return loaner


def _documents(doc, customer):
	"""Links to the related portal pages, and whether the customer can accept the quotation.
	Returns (links, quotation name, can_accept)."""
	links, quotation, can_accept = [], None, False

	if doc.quotation:
		q = frappe.db.get_value(
			"Quotation", doc.quotation, ["docstatus", "status", "grand_total", "currency"], as_dict=True
		)
		if q and q.docstatus == 1:  # drafts are internal, never shown
			quotation = doc.quotation
			can_accept = q.status == "Open" and bool(customer)  # only the customer accepts
			links.append(
				_link(
					_("Quotation"), doc.quotation, "quotations", fmt_money(q.grand_total, currency=q.currency)
				)
			)
	if doc.sales_order:
		links.append(
			_link(
				_("Order"),
				doc.sales_order,
				"orders",
				_("Paid") if doc.payment_cleared else _("Payment pending"),
			)
		)
	if doc.sales_invoice:
		links.append(_link(_("Invoice"), doc.sales_invoice, "invoices"))
	if doc.delivery_note:
		links.append(_link(_("Dispatch"), doc.delivery_note, "shipments"))
	return links, quotation, can_accept


def _link(label, name, route, note=""):
	return {"label": label, "name": name, "route": f"/{route}/{name}", "note": note}
