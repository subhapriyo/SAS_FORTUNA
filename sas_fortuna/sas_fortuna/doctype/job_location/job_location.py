"""Job Location: where support engineers work, and which customers' tickets each place serves.

	match_location()        a city / state -> Job Location (city first, then state; active only)
	location_for_customer() an ERPNext Customer's address -> Job Location
	location_from_text()    staff-sheet text such as "Fortuna Kolkata" -> Job Location

A ticket's Job Location (HD Ticket.custom_job_location) comes from location_for_customer; with the
Ticket Type it picks the team, and so the assignee (support/hd_ticket.py route_to_team).
The Invoice Prefix Key mirrors Fortuna ERP's Company > Invoice Prefix Key, when that field exists.
A branch may bill under several keys (Kolkata: FI, KOLK), kept as "FI, KOLK"; left blank, it is
taken from the Company.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document

# fortuna_erp's custom field on Company (absent on sites without fortuna_erp)
PREFIX_FIELD = "custom_invoice_prefix_key"


class JobLocation(Document):
	def validate(self):
		self.location_name = (self.location_name or "").strip()
		self.cities = _tidy(self.cities)
		self.states = _tidy(self.states)
		self._fill_prefix_key()
		self._check_no_overlap()

	def _fill_prefix_key(self):
		"""Blank -> the Company's own key; keys -> upper case (as fortuna_erp reads them), "FI, KOLK"."""
		if (
			not self.invoice_prefix_key
			and self.company
			and frappe.get_meta("Company").has_field(PREFIX_FIELD)
		):
			self.invoice_prefix_key = frappe.db.get_value("Company", self.company, PREFIX_FIELD)
		self.invoice_prefix_key = ", ".join(prefix_keys(self.invoice_prefix_key)) or None

	def _check_no_overlap(self):
		"""A city or state on two active locations would make a ticket's location a coin toss."""
		if not self.is_active:
			return
		for other in _active_locations(exclude=self.name):
			for label, mine, theirs in (
				(_("City"), self.cities, other.cities),
				(_("State"), self.states, other.states),
			):
				shared = _keys(mine) & _keys(theirs)
				if shared:
					frappe.throw(
						_("{0} {1} is already served by Job Location {2}.").format(
							label, ", ".join(sorted(shared)), other.name
						)
					)


# ---------------------------------------------------------------------------
# Lists: "one per line" text <-> comparable keys
# ---------------------------------------------------------------------------
def _split(text):
	return [part.strip() for part in re.split(r"[\n,]", text or "") if part.strip()]


def _tidy(text):
	"""One entry per line, first spelling kept, repeats (any case) dropped."""
	seen, kept = set(), []
	for part in _split(text):
		if part.lower() not in seen:
			seen.add(part.lower())
			kept.append(part)
	return "\n".join(kept)


def _keys(text):
	return {part.lower() for part in _split(text)}


def prefix_keys(text):
	"""Invoice prefix keys as a list: upper case, in order, each once ("fi, kolk, FI" -> FI, KOLK)."""
	return list(dict.fromkeys(part.upper() for part in _split(text)))


def _active_locations(exclude=None):
	filters = {"is_active": 1}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.get_all("Job Location", filters=filters, fields=["name", "cities", "states"])


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def match_location(city=None, state=None):
	"""Active Job Location serving this city, else this state; None when neither is listed."""
	city, state = (city or "").strip().lower(), (state or "").strip().lower()
	locations = _active_locations()
	for key, field in ((city, "cities"), (state, "states")):
		if not key:
			continue
		for loc in locations:
			if key in _keys(loc.get(field)):
				return loc.name
	return None


def customer_address(customer):
	"""The Customer's primary address, else its first linked address (billing first)."""
	if not customer:
		return None
	name = frappe.db.get_value("Customer", customer, "customer_primary_address")
	if not name:
		linked = frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": customer},
			pluck="parent",
		)
		rows = frappe.get_all(
			"Address",
			filters={"name": ["in", linked or [""]], "disabled": 0},
			fields=["name", "address_type"],
			order_by="is_primary_address desc, creation asc",
		)
		billing = [r.name for r in rows if r.address_type == "Billing"]
		name = (billing or [r.name for r in rows] or [None])[0]
	return frappe.db.get_value("Address", name, ["city", "state"], as_dict=True) if name else None


def location_for_customer(customer):
	"""Job Location for a customer's tickets, from the customer's address; None when unknown."""
	address = customer_address(customer)
	return match_location(address.city, address.state) if address else None


def location_from_text(text):
	"""Job Location whose name appears in free text ("Fortuna Kolkata" -> Kolkata); longest name first."""
	text = (text or "").lower()
	if not text:
		return None
	names = frappe.get_all("Job Location", filters={"is_active": 1}, pluck="name")
	for name in sorted(names, key=len, reverse=True):
		if name.lower() in text:
			return name
	return None
