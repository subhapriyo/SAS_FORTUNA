import json

import frappe


def _get_supplier(user):
	return frappe.db.get_value("Portal User", {"user": user}, "parent")


@frappe.whitelist()
def get_supplier_doc():
	supplier = _get_supplier(frappe.session.user)
	if not supplier:
		frappe.throw("Supplier not linked")

	supplier_doc = frappe.get_doc("Supplier", supplier)
	response = supplier_doc.as_dict()
	response["supplier_code"] = supplier_doc.name

	# ===== STATUTORY FIELDS =====
	# as_dict() se pan/gstin/gst_category reliably nahi aati,
	# isliye explicitly set karo
	response["pan"] = supplier_doc.get("pan") or ""
	response["gstin"] = supplier_doc.get("gstin") or ""
	response["gst_category"] = supplier_doc.get("gst_category") or ""
	response["supplier_name"] = supplier_doc.supplier_name or ""

	# ===== MULTIPLE ADDRESSES =====
	try:
		linked_addresses = frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Supplier",
				"link_name": supplier,
				"parenttype": "Address",
			},
			fields=["parent"],
			order_by="parent asc",
		)

		address_names = [d["parent"] for d in linked_addresses]
		primary_address = supplier_doc.supplier_primary_address

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
				"link_doctype": "Supplier",
				"link_name": supplier,
				"parenttype": "Contact",
			},
			fields=["parent"],
			order_by="parent asc",
		)

		contact_names = [d["parent"] for d in linked_contacts]
		primary_contact = supplier_doc.supplier_primary_contact

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

	# ===== BANK =====
	try:
		bank_account_name = supplier_doc.custom_default_supplier_bank_account
		if bank_account_name and frappe.db.exists("Bank Account", bank_account_name):
			bank_account = frappe.get_doc("Bank Account", bank_account_name)
			response["custom_account_no"] = bank_account.bank_account_no or ""
			response["custom_ifsc_code"] = bank_account.branch_code or ""
			if bank_account.bank:
				response["custom_bank_name"] = (
					frappe.db.get_value("Bank", bank_account.bank, "bank_name") or ""
				)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "KYC Bank Fetch Error")

	return response


@frappe.whitelist()
def update_supplier(data):
	if isinstance(data, str):
		data = json.loads(data)

	supplier = _get_supplier(frappe.session.user)
	if not supplier:
		frappe.throw("Supplier not linked")

	doc = frappe.get_doc("Supplier", supplier)

	# ---------------- NORMAL SUPPLIER FIELDS ----------------
	ALLOWED_FIELDS = [
		"pan",
		"gstin",
		"gst_category",
		"custom_tan_no",
		"custom_aadhaar_number",
		"custom_tds_applicable",
		"custom_msme",
		"custom_udyam_registration_number",
		"custom_type_of_industry",
		"custom_type_of_enterprise",
		"custom_major_activity",
		"tax_withholding_category",
		"custom_tcs_applicable",
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
				"link_doctype": "Supplier",
				"link_name": supplier,
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
				address.address_title = supplier
				address.address_type = "Billing"

			address.address_line1 = a_data.get("address_line1", "")
			address.address_line2 = a_data.get("address_line2", "")
			address.city = a_data.get("city", "")
			address.state = a_data.get("state", "")
			address.pincode = a_data.get("pincode", "")
			address.is_primary_address = 1 if is_primary else 0

			# Ensure supplier link exists
			address.links = [
				l for l in address.links if not (l.link_doctype == "Supplier" and l.link_name == supplier)
			]
			address.append("links", {"link_doctype": "Supplier", "link_name": supplier})

			address.save(ignore_permissions=True)
			saved_addr_names.append(address.name)

			if is_primary:
				doc.supplier_primary_address = address.name

		# Unlink / delete removed addresses
		for old_addr in existing_addr_names:
			if old_addr not in saved_addr_names:
				try:
					old_doc = frappe.get_doc("Address", old_addr)
					old_doc.links = [
						l
						for l in old_doc.links
						if not (l.link_doctype == "Supplier" and l.link_name == supplier)
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
				"link_doctype": "Supplier",
				"link_name": supplier,
				"parenttype": "Contact",
			},
			fields=["parent"],
		)
		existing_contact_names = {d["parent"] for d in existing_links}
		saved_contact_names = []

		for idx, c_data in enumerate(contacts_data):
			phone = c_data.get("phone", "")
			mobile = c_data.get("mobile", "")
			email = c_data.get("email", "")
			website = c_data.get("website", "")
			first_name = c_data.get("first_name", "") or supplier
			designation = c_data.get("designation", "")
			is_primary = idx == 0

			if not any([phone, mobile, email, first_name]):
				continue

			contact_name = c_data.get("contact_name", "")

			if contact_name and frappe.db.exists("Contact", contact_name):
				contact = frappe.get_doc("Contact", contact_name)
				contact.phone_nos = []
				contact.email_ids = []
				contact.links = [
					l for l in contact.links if not (l.link_doctype == "Supplier" and l.link_name == supplier)
				]
			else:
				contact = frappe.new_doc("Contact")

			contact.first_name = first_name
			contact.designation = designation

			contact.append("links", {"link_doctype": "Supplier", "link_name": supplier})

			if phone:
				contact.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
			if mobile:
				contact.append("phone_nos", {"phone": mobile, "is_primary_mobile_no": 1})
			if email:
				contact.append("email_ids", {"email_id": email, "is_primary": 1})

			contact.website = website
			contact.is_primary_contact = 1 if is_primary else 0
			contact.save(ignore_permissions=True)
			saved_contact_names.append(contact.name)

			if is_primary:
				doc.supplier_primary_contact = contact.name

		# Unlink / delete removed contacts
		for old_contact_name in existing_contact_names:
			if old_contact_name not in saved_contact_names:
				try:
					old_contact = frappe.get_doc("Contact", old_contact_name)
					old_contact.links = [
						l
						for l in old_contact.links
						if not (l.link_doctype == "Supplier" and l.link_name == supplier)
					]
					if not old_contact.links:
						frappe.delete_doc("Contact", old_contact_name, ignore_permissions=True)
					else:
						old_contact.save(ignore_permissions=True)
				except Exception:
					frappe.log_error(frappe.get_traceback(), "KYC Contact Unlink Error")

	# ==========================================================
	# ======================== BANK ============================
	# ==========================================================

	bank_name = data.get("custom_bank_name")
	account_no = data.get("custom_account_no")
	ifsc = data.get("custom_ifsc_code")
	account_holder = data.get("custom_account_holder_name")

	if bank_name and account_no:
		bank = get_or_create_bank(bank_name)
		bank_account = get_or_create_bank_account(
			supplier=supplier,
			bank=bank,
			account_no=account_no,
			ifsc=ifsc,
			account_holder=account_holder,
		)
		doc.custom_default_supplier_bank_account = bank_account

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "success"}


# ---------------- HELPERS ----------------


def get_or_create_bank(bank_name):
	bank = frappe.db.get_value("Bank", {"bank_name": bank_name}, "name")
	if bank:
		return bank
	bank_doc = frappe.get_doc({"doctype": "Bank", "bank_name": bank_name})
	bank_doc.insert(ignore_permissions=True)
	return bank_doc.name


def get_or_create_bank_account(supplier, bank, account_no, ifsc=None, account_holder=None):
	existing = frappe.db.get_value(
		"Bank Account",
		{"party_type": "Supplier", "party": supplier, "bank_account_no": account_no},
		"name",
	)
	if existing:
		return existing

	bank_account = frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": f"{supplier} - {account_no[-4:]}",
			"bank": bank,
			"bank_account_no": account_no,
			"ifsc": ifsc,
			"party_type": "Supplier",
			"party": supplier,
			"account_holder_name": account_holder,
			"is_default": 1,
		}
	)
	bank_account.insert(ignore_permissions=True)
	return bank_account.name


@frappe.whitelist()
def get_gst_category_options():
	meta = frappe.get_meta("Supplier")
	field = meta.get_field("gst_category")
	if not field or not field.options:
		return []
	return [opt.strip() for opt in field.options.split("\n") if opt.strip()]


@frappe.whitelist(allow_guest=True)
def get_tax_withholding_category_options():
	options = frappe.get_all("Tax Withholding Category", fields=["name"], order_by="name asc")
	return [d["name"] for d in options]
