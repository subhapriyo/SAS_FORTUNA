"""Unit tests: the New Ticket form, on the customer portal and in Helpdesk (agents).

  1. Job Location ... not on the New Ticket form at all: set on save from the customer's Bill
                      To address (city, then state), else Kolkata; then an engineer at that
                      Job Location is assigned (test_ticket_assignment.py). The agent's ticket
                      sidebar still shows it, agents only, so it can be corrected later.
  2. Customer first . agents pick the Customer first; that narrows the Serial No choices to the
                      customer's own units
  3. Product Name ... the portal's Serial No choices name the product; agents get a read-only
                      Product Name next to Serial No (Helpdesk's searchable dropdown shows only
                      the serial), filled as soon as a unit is picked and kept on the ticket

Server side: support/portal.py (choices), support/new_ticket.py (agent form, defaults),
setup/support_desk.py (the Default ticket template). The page side is
setup/data/fortuna_new_ticket_form.js (public/js/tests/new_ticket_form.test.js).

Written test-first. ZZ-named records only; IntegrationTestCase rolls them back.

    bash apps/sas_fortuna/tools/run_unit_tests.sh test_new_ticket_form
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sas_fortuna.sas_fortuna.doctype.job_location import job_location as jl
from sas_fortuna.setup import support_desk as sd
from sas_fortuna.support import new_ticket, portal

CUSTOMER_FIELD = "custom_erpnext_customer"
SERIAL_FIELD = "custom_serial_no"
LOCATION_FIELD = "custom_job_location"


# ---------------------------------------------------------------------------
# Test records
# ---------------------------------------------------------------------------
def _location(name, cities="", states=""):
	if frappe.db.exists("Job Location", name):
		frappe.delete_doc("Job Location", name, force=True)
	return frappe.get_doc(
		{"doctype": "Job Location", "location_name": name, "cities": cities, "states": states, "is_active": 1}
	).insert(ignore_permissions=True)


def _customer(name):
	if frappe.db.exists("Customer", name):
		return frappe.get_doc("Customer", name)
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_group": frappe.get_all(
				"Customer Group", filters={"is_group": 0}, pluck="name", limit=1
			)[0],
			"territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0],
		}
	).insert(ignore_permissions=True)


# A state no branch serves (Kolkata serves West Bengal on Fortuna's sites), so only the city
# decides in these tests. India Compliance accepts only real states.
FREE_STATE = "Kerala"


def _address(customer, title, city, address_type="Billing", state=FREE_STATE):
	return frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": title,
			"address_type": address_type,
			"address_line1": "1 Zz Road",
			"city": city,
			"state": state,  # India Compliance requires one
			"country": frappe.db.get_default("country") or "India",
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	).insert(ignore_permissions=True)


def _rows(fields):
	return {f["fieldname"]: f for f in fields}


# ---------------------------------------------------------------------------
# 1. Job Location: Bill To city, else Kolkata, never shown to customers
# ---------------------------------------------------------------------------
class TestJobLocationFromBillTo(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		_location("ZZ NT Billtown", cities="Zzbill")
		_location("ZZ NT Shiptown", cities="Zzship")
		# The class shares one transaction: a customer per test keeps their addresses apart.
		self.customer = _customer(f"ZZ NT {self._testMethodName[5:40]}").name

	def test_bill_to_city_wins_over_the_primary_address(self):
		# The primary address is the shipping one; the branch still follows the Bill To address.
		ship = _address(self.customer, "ZZ NT Ship", "Zzship", address_type="Shipping")
		_address(self.customer, "ZZ NT Bill", "Zzbill")
		frappe.db.set_value("Customer", self.customer, "customer_primary_address", ship.name)
		self.assertEqual(jl.location_for_customer(self.customer), "ZZ NT Billtown")

	def test_without_a_bill_to_address_the_primary_one_is_used(self):
		ship = _address(self.customer, "ZZ NT Ship", "Zzship", address_type="Shipping")
		frappe.db.set_value("Customer", self.customer, "customer_primary_address", ship.name)
		self.assertEqual(jl.location_for_customer(self.customer), "ZZ NT Shiptown")

	def test_unknown_city_falls_back_to_the_default(self):
		_address(self.customer, "ZZ NT Far", "Zznowhere")
		self.assertIsNone(jl.location_for_customer(self.customer))
		with patch.object(jl, "DEFAULT_LOCATION", "ZZ NT Billtown"):
			self.assertEqual(new_ticket.job_location_for(self.customer), "ZZ NT Billtown")

	def test_job_location_is_not_on_the_new_ticket_form(self):
		# Nobody picks it: the customer's Bill To address decides, on save.
		sd._helpdesk_ticket_form()
		for agent in (True, False):
			with (
				patch.object(new_ticket, "is_helpdesk_agent", return_value=agent),
				patch("helpdesk.ticket_fields.is_agent", return_value=agent),
			):
				fields = _rows(new_ticket.get_template("Default")["fields"])
			self.assertNotIn(LOCATION_FIELD, fields, "agent" if agent else "customer")

	def test_ticket_sidebar_keeps_it_for_agents_only(self):
		# After creation an agent may correct it (which re-routes the ticket); customers never see it.
		row = _rows(sd.TICKET_FORM_FIELDS)[LOCATION_FIELD]
		self.assertEqual(row.get("visible_to"), "Agents")

	def test_no_row_uses_the_old_hide_from_customer_flag(self):
		# Helpdesk 16 reads Visible to; the old flag is ignored, which showed the field to customers.
		for row in sd.TICKET_FORM_FIELDS:
			self.assertNotIn("hide_from_customer", row, row["fieldname"])

	def test_setup_hides_a_job_location_row_shown_to_everyone(self):
		template = frappe.get_doc("HD Ticket Template", "Default")
		row = next((r for r in template.fields if r.fieldname == LOCATION_FIELD), None)
		if not row:
			row = template.append("fields", {"fieldname": LOCATION_FIELD})
		row.visible_to = "Everyone"
		template.save(ignore_permissions=True)
		sd._helpdesk_ticket_form()
		self.assertEqual(
			frappe.db.get_value(
				"HD Ticket Template Field", {"parent": "Default", "fieldname": LOCATION_FIELD}, "visible_to"
			),
			"Agents",
		)

	def test_customers_never_get_the_field_agents_do_in_the_sidebar(self):
		from helpdesk.ticket_fields import TicketFields

		sd._helpdesk_ticket_form()
		with patch("helpdesk.ticket_fields.is_agent", return_value=False):
			self.assertNotIn(LOCATION_FIELD, [f.fieldname for f in TicketFields("Default").get_layout()])
		with patch("helpdesk.ticket_fields.is_agent", return_value=True):
			self.assertIn(LOCATION_FIELD, [f.fieldname for f in TicketFields("Default").get_layout()])


# ---------------------------------------------------------------------------
# 2. Agents: Customer first, the rest follows
# ---------------------------------------------------------------------------
class TestCustomerFirst(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		_location("ZZ NT Billtown", cities="Zzbill")
		self.customer = _customer("ZZ NT Customer").name
		self.other = _customer("ZZ NT Other").name
		self.item = self._item()
		self.mine = self._serial("ZZNT-0001", self.customer)
		self._serial("ZZNT-0002", self.other)

	def _item(self):
		code = "ZZ-NT-MODEL"
		if not frappe.db.exists("Item", code):
			item = {
				"doctype": "Item",
				"item_code": code,
				"item_name": "ZZ Biometric Reader",
				"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
				"stock_uom": "Nos",
				"has_serial_no": 1,
				"is_stock_item": 1,
			}
			# India Compliance: every item needs an HSN/SAC code.
			if frappe.get_meta("Item").has_field("gst_hsn_code"):
				item["gst_hsn_code"] = frappe.get_all("GST HSN Code", pluck="name", limit=1)[0]
			frappe.get_doc(item).insert(ignore_permissions=True)
		return code

	def _serial(self, name, customer):
		if not frappe.db.exists("Serial No", name):
			frappe.get_doc({"doctype": "Serial No", "serial_no": name, "item_code": self.item}).insert(
				ignore_permissions=True
			)
		frappe.db.set_value("Serial No", name, "custom_sold_to", customer)
		return name

	def test_customer_is_the_first_field_and_agents_only(self):
		first = sd.TICKET_FORM_FIELDS[0]
		self.assertEqual((first["fieldname"], first.get("visible_to")), (CUSTOMER_FIELD, "Agents"))

	def test_setup_puts_the_customer_row_first_on_the_template(self):
		sd._helpdesk_ticket_form()
		rows = frappe.get_all(
			"HD Ticket Template Field", filters={"parent": "Default"}, pluck="fieldname", order_by="idx"
		)
		self.assertEqual(rows[0], CUSTOMER_FIELD)

	def test_defaults_for_a_customer(self):
		with patch.object(new_ticket, "is_helpdesk_agent", return_value=True):
			got = new_ticket.new_ticket_defaults(self.customer)
		self.assertEqual(got, {"serials": [self.mine]})  # never another customer's unit

	def test_defaults_are_for_agents_only(self):
		with patch.object(new_ticket, "is_helpdesk_agent", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				new_ticket.new_ticket_defaults(self.customer)

	def test_agents_get_customer_first_and_a_searchable_serial(self):
		# The portal's serial list knows only the portal user's own customer; agents search the
		# Serial No link instead, which the page narrows to the chosen customer.
		sd._helpdesk_ticket_form()
		with patch.object(new_ticket, "is_helpdesk_agent", return_value=True):
			fields = _rows(new_ticket.get_template("Default")["fields"])
		self.assertEqual(fields[CUSTOMER_FIELD].label, "Customer")
		self.assertFalse(fields[SERIAL_FIELD].url_method)

	def test_customers_keep_their_own_serial_list(self):
		sd._helpdesk_ticket_form()
		with (
			patch.object(new_ticket, "is_helpdesk_agent", return_value=False),
			patch("helpdesk.ticket_fields.is_agent", return_value=False),
		):
			fields = _rows(new_ticket.get_template("Default")["fields"])
		self.assertNotIn(CUSTOMER_FIELD, fields)
		self.assertEqual(fields[SERIAL_FIELD].url_method, "sas_fortuna.support.portal.customer_serials")

	def test_helpdesk_template_call_is_routed_here(self):
		self.assertEqual(
			frappe.get_hooks("override_whitelisted_methods").get(
				"helpdesk.helpdesk.doctype.hd_ticket_template.api.get_one"
			),
			["sas_fortuna.support.new_ticket.get_template"],
		)

	# -----------------------------------------------------------------------
	# 3. Product Name in the Serial No choices
	# -----------------------------------------------------------------------
	def test_portal_choices_name_the_product(self):
		with patch.object(portal, "get_portal_customer", return_value=self.customer):
			choices = portal.customer_serials()
		self.assertEqual(
			choices, [{"label": "ZZNT-0001 · ZZ Biometric Reader (ZZ-NT-MODEL)", "value": self.mine}]
		)

	def test_label_does_not_repeat_a_product_named_as_its_code(self):
		self.assertEqual(portal.serial_label("S1", "MODEL-1", "MODEL-1"), "S1 · MODEL-1")
		self.assertEqual(portal.serial_label("S1", "MODEL-1", None), "S1 · MODEL-1")
		self.assertEqual(portal.serial_label("S1", "MODEL-1", "Reader"), "S1 · Reader (MODEL-1)")

	def test_ticket_keeps_the_item_name_of_its_unit(self):
		df = frappe.get_meta("HD Ticket").get_field("custom_product_name")
		self.assertEqual(
			(df.label, df.fieldtype, df.read_only, df.fetch_from),
			("Item Name", "Data", 1, "custom_serial_no.item_name"),
		)

	def test_setup_renames_the_old_product_name_label(self):
		# Sites that got the field before the rename: migrate keeps existing labels (update=False).
		cf = frappe.db.get_value("Custom Field", {"dt": "HD Ticket", "fieldname": "custom_product_name"})
		frappe.db.set_value("Custom Field", cf, "label", "Product Name")
		sd._item_name_label()
		self.assertEqual(frappe.db.get_value("Custom Field", cf, "label"), "Item Name")

	def test_setup_keeps_a_label_an_admin_chose(self):
		cf = frappe.db.get_value("Custom Field", {"dt": "HD Ticket", "fieldname": "custom_product_name"})
		frappe.db.set_value("Custom Field", cf, "label", "Model")
		sd._item_name_label()
		self.assertEqual(frappe.db.get_value("Custom Field", cf, "label"), "Model")

	def test_product_name_sits_next_to_serial_no_for_agents(self):
		names = [f["fieldname"] for f in sd.TICKET_FORM_FIELDS]
		self.assertEqual(names.index("custom_product_name"), names.index(SERIAL_FIELD) + 1)
		self.assertEqual(_rows(sd.TICKET_FORM_FIELDS)["custom_product_name"].get("visible_to"), "Agents")

	def test_setup_puts_a_new_row_after_its_neighbour(self):
		# A site that already has the template gets Product Name next to Serial No, not at the end.
		template = frappe.get_doc("HD Ticket Template", "Default")
		for row in [r for r in template.fields if r.fieldname == "custom_product_name"]:
			template.remove(row)
		template.save(ignore_permissions=True)
		sd._helpdesk_ticket_form()
		rows = frappe.get_all(
			"HD Ticket Template Field", filters={"parent": "Default"}, pluck="fieldname", order_by="idx"
		)
		self.assertEqual(rows[rows.index(SERIAL_FIELD) + 1], "custom_product_name")

	def test_agents_see_product_name_read_only(self):
		sd._helpdesk_ticket_form()
		with patch.object(new_ticket, "is_helpdesk_agent", return_value=True):
			field = _rows(new_ticket.get_template("Default")["fields"])["custom_product_name"]
		self.assertTrue(field.disabled)  # shown, not typed in

	def test_product_of_a_unit(self):
		with patch.object(new_ticket, "is_helpdesk_agent", return_value=True):
			self.assertEqual(new_ticket.serial_product(self.mine), "ZZ Biometric Reader")
			self.assertIsNone(new_ticket.serial_product("ZZ-NO-SUCH-SERIAL"))
		with patch.object(new_ticket, "is_helpdesk_agent", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				new_ticket.serial_product(self.mine)

	def test_agent_search_shows_the_product_name(self):
		# Helpdesk's link dropdown shows a Serial No's search fields under it.
		sd._serial_no_search_fields()
		fields = (frappe.get_meta("Serial No").search_fields or "").split(",")
		fields = [f.strip() for f in fields]
		self.assertEqual(fields[:2], ["item_name", "item_code"])
		from frappe.desk.search import search_link

		found = {r["value"]: r for r in search_link("Serial No", "ZZNT-0001")}
		self.assertIn("ZZ Biometric Reader", found[self.mine].get("description", ""))
