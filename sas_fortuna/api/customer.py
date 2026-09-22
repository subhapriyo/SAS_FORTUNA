import json

import frappe


def _get_customer(user):
	return frappe.db.get_value(
		"Portal User",
		{"user": user, "parenttype": "Customer"},
		"parent",
	)


@frappe.whitelist()
def get_customer_doc():
	customer = _get_customer(frappe.session.user)
	if not customer:
		frappe.throw("Customer not linked")

	customer_doc = frappe.get_doc("Customer", customer)
	response = customer_doc.as_dict()
	response["customer_code"] = customer_doc.name

	# ===== STATUTORY FIELDS =====
	# as_dict() se pan/gstin/gst_category reliably nahi aati,
	# isliye explicitly set karo
	response["pan"] = customer_doc.get("pan") or ""
	response["gstin"] = customer_doc.get("gstin") or ""
	response["gst_category"] = customer_doc.get("gst_category") or ""
	response["customer_name"] = customer_doc.customer_name or ""
	response["tax_id"] = customer_doc.get("tax_id") or ""

	# ===== MULTIPLE ADDRESSES =====
	try:
		linked_addresses = frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Customer",
				"link_name": customer,
				"parenttype": "Address",
			},
			fields=["parent"],
			order_by="parent asc",
		)

		address_names = [d["parent"] for d in linked_addresses]
		primary_address = customer_doc.customer_primary_address

		# Primary pehle aaye
		if primary_address and primary_address in address_names:
			address_names.remove(primary_address)
			address_names.insert(0, primary_address)

		addresses_list = []
		for addr_name in address_names:
			if not frappe.db.exists("Address", addr_name):
				continue
			addr = frappe.get_doc("Address", addr_name)
			addresses_list.append(
				{
					"address_name": addr_name,
					"address_line1": addr.address_line1 or "",
					"address_line2": addr.address_line2 or "",
					"city": addr.city or "",
					"state": addr.state or "",
					"pincode": addr.pincode or "",
					"is_primary": 1 if addr_name == primary_address else 0,
				}
			)

		response["addresses"] = addresses_list

		# Backward compatibility
		if addresses_list:
			p = addresses_list[0]
			response["address_line1"] = p.get("address_line1", "")
			response["address_line2"] = p.get("address_line2", "")
			response["city"] = p.get("city", "")
			response["state"] = p.get("state", "")
			response["pincode"] = p.get("pincode", "")

	except Exception:
		frappe.log_error(frappe.get_traceback(), "KYC Address Fetch Error")
		response["addresses"] = []

	# ===== MULTIPLE CONTACTS =====
	try:
		linked_contacts = frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Customer",
				"link_name": customer,
				"parenttype": "Contact",
			},
			fields=["parent"],
			order_by="parent asc",
		)

		contact_names = [d["parent"] for d in linked_contacts]
		primary_contact = customer_doc.customer_primary_contact

		if primary_contact and primary_contact in contact_names:
			contact_names.remove(primary_contact)
			contact_names.insert(0, primary_contact)

		contacts_list = []
		for contact_name in contact_names:
			if not frappe.db.exists("Contact", contact_name):
				continue
			contact = frappe.get_doc("Contact", contact_name)
			c_data = {
				"contact_name": contact_name,
				"first_name": contact.first_name or "",
				"designation": contact.designation or "",
				"phone": "",
				"mobile": "",
				"email": "",
				"website": contact.get("website") or "",
				"is_primary": 1 if contact_name == primary_contact else 0,
			}
			for p in contact.phone_nos:
				if p.is_primary_phone and not c_data["phone"]:
					c_data["phone"] = p.phone
				if p.is_primary_mobile_no and not c_data["mobile"]:
					c_data["mobile"] = p.phone
			for e in contact.email_ids:
				if e.is_primary and not c_data["email"]:
					c_data["email"] = e.email_id
			contacts_list.append(c_data)

		response["contacts"] = contacts_list

	except Exception:
		frappe.log_error(frappe.get_traceback(), "KYC Contact Fetch Error")
		response["contacts"] = []

	bank_account_name = customer_doc.get("custom_default_customer_bank_account")
	if bank_account_name and frappe.db.exists("Bank Account", bank_account_name):
		bank_account = frappe.get_doc("Bank Account", bank_account_name)
		response["custom_account_no"] = bank_account.bank_account_no or ""
		response["custom_ifsc_code"] = bank_account.branch_code or ""
		response["custom_bank_name"] = (
			frappe.db.get_value("Bank", bank_account.bank, "bank_name") if bank_account.bank else ""
		) or ""

	return response


@frappe.whitelist()
def update_customer(data):
	if isinstance(data, str):
		data = json.loads(data)

	customer = _get_customer(frappe.session.user)
	if not customer:
		frappe.throw("Customer not linked")

	doc = frappe.get_doc("Customer", customer)

	# ---------------- NORMAL CUSTOMER FIELDS ----------------
	ALLOWED_FIELDS = [
		"tax_id",
		"pan",
		"gstin",
		"gst_category",
		"custom_aadhaar_number",
		"custom_tan_no",
		"custom_tds_applicability",
		"custom_tcs_applicable",
		"custom_msme",
		"custom_udyam_registration_egistratio_number",
		"custom_date_of_registration",
		"custom_type_of_enterprise",
		"custom_type_of_industry",
		"custom_major_activity",
		"custom_gst_certificate",
		"custom_pan_card",
		"custom_certificate_of_incorporation__partnership_deed",
		"custom_cancelled_cheque",
		"custom_last_itr__acknowledgement",
		"custom_msme_certificate",
	]
	for field in ALLOWED_FIELDS:
		if field in data:
			doc.set(field, data[field])

	# ==========================================================
	# ==================== MULTIPLE ADDRESSES ==================
	# ==========================================================

	addresses_data = data.get("addresses", [])

	if addresses_data:
		existing_links = frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Customer",
				"link_name": customer,
				"parenttype": "Address",
			},
			fields=["parent"],
		)
		existing_addr_names = {d["parent"] for d in existing_links}
		saved_addr_names = []

		for idx, a_data in enumerate(addresses_data):
			# Skip completely empty rows
			if not any([a_data.get("address_line1"), a_data.get("city"), a_data.get("pincode")]):
				continue

			is_primary = idx == 0
			addr_name = a_data.get("address_name", "")

			if addr_name and frappe.db.exists("Address", addr_name):
				address = frappe.get_doc("Address", addr_name)
			else:
				address = frappe.new_doc("Address")
				address.address_title = customer
				address.address_type = "Billing"

			address.address_line1 = a_data.get("address_line1", "")
			address.address_line2 = a_data.get("address_line2", "")
			address.city = a_data.get("city", "")
			address.state = a_data.get("state", "")
			address.pincode = a_data.get("pincode", "")
			address.is_primary_address = 1 if is_primary else 0

			# Ensure customer link exists
			address.links = [
				l for l in address.links if not (l.link_doctype == "Customer" and l.link_name == customer)
			]
			address.append("links", {"link_doctype": "Customer", "link_name": customer})

			address.save(ignore_permissions=True)
			saved_addr_names.append(address.name)

			if is_primary:
				doc.customer_primary_address = address.name

		# Unlink / delete removed addresses
		for old_addr in existing_addr_names:
			if old_addr not in saved_addr_names:
				try:
					old_doc = frappe.get_doc("Address", old_addr)
					old_doc.links = [
						l
						for l in old_doc.links
						if not (l.link_doctype == "Customer" and l.link_name == customer)
					]
					if not old_doc.links:
						frappe.delete_doc("Address", old_addr, ignore_permissions=True)
					else:
						old_doc.save(ignore_permissions=True)
				except Exception:
					frappe.log_error(frappe.get_traceback(), "KYC Address Unlink Error")

	# ==========================================================
	# ==================== MULTIPLE CONTACTS ===================
	# ==========================================================

	contacts_data = data.get("contacts", [])

	if contacts_data:
		existing_links = frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Customer",
				"link_name": customer,
				"parenttype": "Contact",
			},
			fields=["parent"],
		)
		existing_contact_names = {d["parent"] for d in existing_links}
		saved_contact_names = []

		# Contact Phone has a mandatory custom_mobile_number field on this site.
		# Check once so this still works on sites where the field doesn't exist.
		contact_phone_meta = frappe.get_meta("Contact Phone")
		has_custom_mobile_field = contact_phone_meta.has_field("custom_mobile_number")

		for idx, c_data in enumerate(contacts_data):
			phone = (c_data.get("phone") or "").strip()
			mobile = (c_data.get("mobile") or "").strip()
			email = (c_data.get("email") or "").strip()
			website = c_data.get("website", "")
			raw_first_name = (c_data.get("first_name") or "").strip()
			first_name = raw_first_name or customer
			designation = c_data.get("designation", "")
			is_primary = idx == 0

			# Skip completely empty rows. Use raw_first_name (pre-fallback) so a
			# blank row isn't kept alive just because we default the name to the
			# customer name below.
			if not any([phone, mobile, email, raw_first_name]):
				continue

			contact_name = c_data.get("contact_name", "")

			if contact_name and frappe.db.exists("Contact", contact_name):
				contact = frappe.get_doc("Contact", contact_name)
				contact.phone_nos = []
				contact.email_ids = []
				contact.links = [
					l for l in contact.links if not (l.link_doctype == "Customer" and l.link_name == customer)
				]
			else:
				contact = frappe.new_doc("Contact")

			contact.first_name = first_name
			contact.designation = designation

			contact.append("links", {"link_doctype": "Customer", "link_name": customer})

			if phone:
				row = {"phone": phone, "is_primary_phone": 1}
				if has_custom_mobile_field:
					row["custom_mobile_number"] = phone
				contact.append("phone_nos", row)

			if mobile:
				row = {"phone": mobile, "is_primary_mobile_no": 1}
				if has_custom_mobile_field:
					row["custom_mobile_number"] = mobile
				contact.append("phone_nos", row)

			if email:
				contact.append("email_ids", {"email_id": email, "is_primary": 1})

			contact.website = website
			contact.is_primary_contact = 1 if is_primary else 0
			contact.save(ignore_permissions=True)
			saved_contact_names.append(contact.name)

			if is_primary:
				doc.customer_primary_contact = contact.name

		# Unlink / delete removed contacts
		for old_contact_name in existing_contact_names:
			if old_contact_name not in saved_contact_names:
				try:
					old_contact = frappe.get_doc("Contact", old_contact_name)
					old_contact.links = [
						l
						for l in old_contact.links
						if not (l.link_doctype == "Customer" and l.link_name == customer)
					]
					if not old_contact.links:
						frappe.delete_doc("Contact", old_contact_name, ignore_permissions=True)
					else:
						old_contact.save(ignore_permissions=True)
				except Exception:
					frappe.log_error(frappe.get_traceback(), "KYC Contact Unlink Error")

		bank_name = data.get("custom_bank_name")
		account_no = data.get("custom_account_no")
		ifsc = data.get("custom_ifsc_code")
		if bank_name and account_no and doc.meta.has_field("custom_default_customer_bank_account"):
			bank = get_or_create_bank(bank_name)
			bank_account = get_or_create_bank_account(customer, bank, account_no, ifsc)
			doc.custom_default_customer_bank_account = bank_account

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "success"}


def get_or_create_bank(bank_name):
	bank = frappe.db.get_value("Bank", {"bank_name": bank_name}, "name")
	if bank:
		return bank
	return frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True).name


def get_or_create_bank_account(customer, bank, account_no, ifsc=None):
	existing = frappe.db.get_value(
		"Bank Account",
		{"party_type": "Customer", "party": customer, "bank_account_no": account_no},
		"name",
	)
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": f"{customer} - {account_no[-4:]}",
				"bank": bank,
				"bank_account_no": account_no,
				"branch_code": ifsc,
				"party_type": "Customer",
				"party": customer,
				"is_default": 1,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


@frappe.whitelist()
def get_gst_category_options():
	meta = frappe.get_meta("Customer")
	field = meta.get_field("gst_category")
	if not field or not field.options:
		return []
	return [opt.strip() for opt in field.options.split("\n") if opt.strip()]


@frappe.whitelist(allow_guest=True)
def get_tax_withholding_category_options():
	options = frappe.get_all("Tax Withholding Category", fields=["name"], order_by="name asc")
	return [d["name"] for d in options]
