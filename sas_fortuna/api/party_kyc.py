"""Shared logic behind the Customer KYC (/customer) and Supplier KYC (/supplier) portal pages.

Both pages are the same form for two party types. Everything that differs between them lives in
a PartyConfig; customer.py and supplier.py only expose thin whitelisted wrappers, so the method
paths the pages call stay stable.

	get_party_kyc()     -> the party's KYC fields + linked addresses / contacts / default bank account
	update_party_kyc()  -> checks the form (validate_kyc), then writes the same structure back

Security model: the logged-in user can only read or change the party they are a Portal User of,
and only Address / Contact records already linked to that party. Writes use ignore_permissions
because website users have no desk permissions on these doctypes, so every write below must stay
behind those two checks.
"""

import json
import re
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import cstr, validate_email_address

from sas_fortuna.api.validation import FORMATS, PINCODE, check_formats, check_phone

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

# Party fields the portal user may edit. Fields missing on a site's DocType are skipped silently,
# so the same list works for Customer and Supplier.
KYC_FIELDS = (
	"tax_id",
	"pan",
	"gstin",
	"gst_category",
	"custom_tan_no",
	"custom_aadhaar_number",
	"custom_tds_applicability",
	"tax_withholding_category",
	"custom_tcs_applicable",
	"custom_msme",
	"custom_udyam_registration_number",
	"custom_date_of_registration",
	"custom_type_of_enterprise",
	"custom_type_of_industry",
	"custom_major_activity",
)

# Attach fields. The page uploads the file first and sends back its file_url.
ATTACHMENT_FIELDS = (
	"custom_gst_certificate",
	"custom_pan_card",
	"custom_certificate_of_incorporation__partnership_deed",
	"custom_cancelled_cheque",
	"custom_last_itr__acknowledgement",
	"custom_msme_certificate",
)

# Form input name -> DocType fieldname, where the two differ.
FORM_ALIASES = {"custom_tds_applicable": "custom_tds_applicability"}


@dataclass(frozen=True)
class PartyConfig:
	"""What differs between the Customer and Supplier KYC pages."""

	doctype: str  # "Customer" / "Supplier"
	name_field: str  # customer_name / supplier_name
	bank_account_field: str  # Link to Bank Account on the party (custom field)

	@property
	def key(self):
		return self.doctype.lower()

	@property
	def primary_address_field(self):
		return f"{self.key}_primary_address"

	@property
	def primary_contact_field(self):
		return f"{self.key}_primary_contact"


# ---------------------------------------------------------------------------
# Party lookup
# ---------------------------------------------------------------------------


def get_linked_party(cfg):
	"""Name of the Customer / Supplier the session user is a Portal User of (oldest link wins)."""
	party = None
	if frappe.session.user != "Guest":
		party = frappe.db.get_value(
			"Portal User",
			{"user": frappe.session.user, "parenttype": cfg.doctype},
			"parent",
			order_by="creation asc",
		)
	if not party:
		frappe.throw(_("{0} not linked").format(_(cfg.doctype)), frappe.PermissionError)
	return party


def _linked_names(cfg, party, link_doctype):
	"""Address / Contact names linked to the party through Dynamic Link."""
	return frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": cfg.doctype, "link_name": party, "parenttype": link_doctype},
		pluck="parent",
		order_by="parent asc",
	)


def _primary_first(names, primary):
	"""Put the party's primary record first: the form treats row 1 as primary."""
	if primary in names:
		names = [primary, *(n for n in names if n != primary)]
	return names


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_party_kyc(cfg):
	"""Everything the KYC page shows, as a flat dict keyed by form input name.

	Only the KYC fields are returned, not the whole party document.
	"""
	party = get_linked_party(cfg)
	doc = frappe.get_doc(cfg.doctype, party)

	response = {
		"name": doc.name,
		f"{cfg.key}_code": doc.name,
		cfg.name_field: doc.get(cfg.name_field) or "",
	}
	for fieldname in (*KYC_FIELDS, *ATTACHMENT_FIELDS):
		response[fieldname] = doc.get(fieldname) or ""
	for form_name, fieldname in FORM_ALIASES.items():
		response[form_name] = response.get(fieldname, "")

	response["addresses"] = _read_addresses(cfg, doc)
	response["contacts"] = _read_contacts(cfg, doc)
	response.update(_read_bank_account(cfg, doc))
	return response


def _read_addresses(cfg, doc):
	primary = doc.get(cfg.primary_address_field)
	rows = []
	for name in _primary_first(_linked_names(cfg, doc.name, "Address"), primary):
		address = frappe.db.get_value("Address", name, ADDRESS_FIELDS, as_dict=True)
		if not address:
			continue
		rows.append(
			{
				"address_name": name,
				**{k: v or "" for k, v in address.items()},
				"is_primary": 1 if name == primary else 0,
			}
		)
	return rows


def _read_contacts(cfg, doc):
	primary = doc.get(cfg.primary_contact_field)
	rows = []
	for name in _primary_first(_linked_names(cfg, doc.name, "Contact"), primary):
		if not frappe.db.exists("Contact", name):
			continue
		contact = frappe.get_doc("Contact", name)
		row = {
			"contact_name": name,
			"first_name": contact.first_name or "",
			"designation": contact.designation or "",
			"phone": "",
			"mobile": "",
			"email": "",
			"website": contact.get("website") or "",
			"is_primary": 1 if name == primary else 0,
		}
		# First primary phone / mobile / email of each kind wins
		for phone in contact.phone_nos:
			if phone.is_primary_phone and not row["phone"]:
				row["phone"] = phone.phone
			if phone.is_primary_mobile_no and not row["mobile"]:
				row["mobile"] = phone.phone
		for email in contact.email_ids:
			if email.is_primary and not row["email"]:
				row["email"] = email.email_id
		rows.append(row)
	return rows


def _read_bank_account(cfg, doc):
	account = doc.get(cfg.bank_account_field)
	if not account:
		return {}
	values = frappe.db.get_value(
		"Bank Account", account, ["bank_account_no", "branch_code", "bank"], as_dict=True
	)
	if not values:
		return {}
	return {
		"custom_account_no": values.bank_account_no or "",
		"custom_ifsc_code": values.branch_code or "",
		"custom_bank_name": (frappe.db.get_value("Bank", values.bank, "bank_name") if values.bank else "")
		or "",
	}


# ---------------------------------------------------------------------------
# Validation (the page runs the same checks first: validate() in public/js/portal_kyc.js)
# ---------------------------------------------------------------------------

ADDRESS_FIELDS = ("address_line1", "address_line2", "city", "state", "pincode")
CONTACT_FIELDS = ("first_name", "designation", "phone", "mobile", "email", "website")

# GST categories that do not need a GSTIN
NO_GSTIN_CATEGORIES = ("Unregistered", "Overseas")

BANK_FIELDS = {
	"custom_bank_name": "Enter the bank name.",
	"custom_account_no": "Enter the account number.",
	"custom_ifsc_code": "Enter the IFSC.",
}
ADDRESS_REQUIRED = {
	"address_line1": "Enter the address.",
	"city": "Enter the city.",
	"state": "Enter the state.",
	"pincode": "Enter the PIN code.",
}


def validate_kyc(data):
	"""Check the KYC form; returns a list of problems, empty when all is well.

	Each problem is {"field": <input name>, "message": ...}; a problem inside an address / contact
	row also has "row_type" ("address" / "contact") and "row" (1 = first row), so the page can
	highlight the exact box. Values are tidied in place on the way (trimmed, IDs upper-cased,
	phone numbers as "+91-9830012345"), so what gets saved is clean.
	"""
	errors = []

	def problem(field, message, row_type=None, row=None):
		errors.append({"field": field, "message": _(message), "row_type": row_type, "row": row})

	_trim(data)

	# Formats: GSTIN (+ check digit, + PAN match), PAN, TAN, Aadhaar, Udyam, IFSC, account number
	check_formats(data, FORMATS, problem)

	# Required, depending on other answers
	gstin, category = data.get("gstin"), data.get("gst_category")
	if not category:
		problem("gst_category", "Choose the GST category.")
	elif category not in NO_GSTIN_CATEGORIES and not gstin:
		problem("gstin", "This GST category needs a GSTIN. Enter it, or choose Unregistered.")
	if data.get("custom_tds_applicable") == "Yes" and not data.get("tax_withholding_category"):
		problem("tax_withholding_category", "Choose the tax withholding category.")
	if data.get("custom_msme") == "Yes" and not data.get("custom_udyam_registration_number"):
		problem("custom_udyam_registration_number", "Enter the Udyam registration number.")
	if any(data.get(f) for f in BANK_FIELDS):  # bank details: all or nothing
		for field, message in BANK_FIELDS.items():
			if not data.get(field):
				problem(field, message)

	# Address rows: a started row needs the full address
	for row_no, row in enumerate(data.get("addresses") or [], 1):
		_trim(row)
		if _is_blank(row, ADDRESS_FIELDS):
			continue
		for field, message in ADDRESS_REQUIRED.items():
			if not row.get(field):
				problem(field, message, "address", row_no)
		if row.get("pincode") and not re.fullmatch(PINCODE, row["pincode"]):
			problem("pincode", "Enter the 6-digit PIN code.", "address", row_no)

	# Contact rows: e-mail format and phone numbers
	for row_no, row in enumerate(data.get("contacts") or [], 1):
		_trim(row)
		if row.get("email") and not validate_email_address(row["email"]):
			problem("email", "Enter a valid e-mail address, for example name@company.com.", "contact", row_no)
		for field in ("phone", "mobile"):
			if row.get(field):
				row[field], message = check_phone(row[field], mobile_only=field == "mobile")
				if message:
					problem(field, message, "contact", row_no)
	return errors


def _trim(values):
	for key, value in values.items():
		if isinstance(value, str):
			values[key] = value.strip()


def _is_blank(row, fields):
	"""An empty address / contact row (the form always shows at least one): skipped, not saved."""
	return not any(row.get(field) for field in fields)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def update_party_kyc(cfg, data):
	"""Save the KYC form.

	Returns {"status": "success", "skipped": [labels of values not saved]}, or, when the form has
	mistakes, {"status": "invalid", "errors": [...]} (see validate_kyc) and nothing is saved.
	"""
	if isinstance(data, str):
		data = json.loads(data)

	party = get_linked_party(cfg)
	errors = validate_kyc(data)
	if errors:
		return {"status": "invalid", "errors": errors}

	doc = frappe.get_doc(cfg.doctype, party)
	before = doc.as_dict()

	skipped = _apply_fields(doc, data)
	skipped += _apply_attachments(doc, data)

	if data.get("addresses"):
		_sync_addresses(cfg, doc, data["addresses"])
	if data.get("contacts"):
		_sync_contacts(cfg, doc, data["contacts"])
	_sync_bank_account(cfg, doc, data)

	_save_as_system(_on_latest(doc, before))
	return {"status": "success", "skipped": skipped}


def _save_as_system(doc):
	"""Save the party as the system user, then hand control back to the portal user.

	ERPNext's Customer.on_update marks the primary Contact with frappe.set_value(), which checks the
	logged-in user's Desk permissions; a portal user has none, so the save failed with "Not
	permitted". Safe here: get_linked_party() already proved this is the user's own party.
	"""
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		doc.save(ignore_permissions=True)
	finally:
		frappe.set_user(user)


def _on_latest(doc, before):
	"""The party document to save: `doc`, or a fresh copy with the form's changes on it.

	Saving the addresses and contacts above runs ERPNext's own hooks, which update the party
	(primary contact, mobile, e-mail...). Our copy is then out of date and Frappe refuses to save
	it ("has been modified after you have opened it"). So, if the party changed meanwhile, reload it
	and copy over only the fields this form changed; the hooks' updates are kept.
	"""
	if frappe.db.get_value(doc.doctype, doc.name, "modified") == doc.modified:
		return doc
	latest = frappe.get_doc(doc.doctype, doc.name)
	for df in doc.meta.fields:
		if df.fieldtype in frappe.model.table_fields:
			continue
		if doc.get(df.fieldname) != before.get(df.fieldname):
			latest.set(df.fieldname, doc.get(df.fieldname))
	return latest


def _apply_fields(doc, data):
	"""Copy the editable KYC fields from the form onto the party document."""
	data = dict(data)
	for form_name, fieldname in FORM_ALIASES.items():
		if form_name in data:
			data[fieldname] = data.pop(form_name)

	skipped = []
	for fieldname in KYC_FIELDS:
		if fieldname not in data or not doc.meta.has_field(fieldname):
			continue
		value = data[fieldname]
		if not _is_valid_select(doc.meta.get_field(fieldname), value):
			# Saving would raise and lose the whole form; keep the stored value instead.
			skipped.append(doc.meta.get_label(fieldname))
			continue
		doc.set(fieldname, value)

	# TDS "No" means no withholding category; the page keeps the hidden select's old value.
	if data.get("custom_tds_applicability") == "No" and doc.meta.has_field("tax_withholding_category"):
		doc.set("tax_withholding_category", None)
	return skipped


def _is_valid_select(df, value):
	"""Mirror of Frappe's select validation (value is stripped, options are not)."""
	if df.fieldtype != "Select" or not value or not df.options:
		return True
	return cstr(value).strip() in df.options.split("\n")


def _apply_attachments(doc, data):
	"""Set uploaded attachment URLs and attach each File to the party.

	Only files the session user uploaded themselves are accepted. Attaching the File to the party
	matters: an unattached private file can be opened by nobody but its uploader.
	"""
	skipped = []
	for fieldname in ATTACHMENT_FIELDS:
		file_url = data.get(fieldname)
		if not file_url or file_url == doc.get(fieldname) or not doc.meta.has_field(fieldname):
			continue
		file_name = frappe.db.get_value("File", {"file_url": file_url, "owner": frappe.session.user}, "name")
		if not file_name:
			skipped.append(doc.meta.get_label(fieldname))
			continue
		frappe.db.set_value(
			"File",
			file_name,
			{
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
				"attached_to_field": fieldname,
			},
		)
		doc.set(fieldname, file_url)
	return skipped


def _relink(record, cfg, party):
	"""Make `party` the record's only link of this party type (Address / Contact links table)."""
	record.links = [
		link for link in record.links if not (link.link_doctype == cfg.doctype and link.link_name == party)
	]
	record.append("links", {"link_doctype": cfg.doctype, "link_name": party})


def _unlink_removed(cfg, party, link_doctype, existing, kept):
	"""Rows the user removed from the form: drop the party link, delete the record if now orphaned."""
	for name in existing - set(kept):
		try:
			record = frappe.get_doc(link_doctype, name)
			record.links = [
				link
				for link in record.links
				if not (link.link_doctype == cfg.doctype and link.link_name == party)
			]
			if record.links:
				record.save(ignore_permissions=True)
			else:
				frappe.delete_doc(link_doctype, name, ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"KYC {link_doctype} Unlink Error")


def _sync_addresses(cfg, doc, rows):
	existing = set(_linked_names(cfg, doc.name, "Address"))
	kept = []

	for idx, row in enumerate(rows):
		if _is_blank(row, ADDRESS_FIELDS):
			continue

		# Only reuse an Address that is already linked to this party, never one named by the client
		name = row.get("address_name")
		if name in existing:
			address = frappe.get_doc("Address", name)
		else:
			address = frappe.new_doc("Address")
			address.address_title = doc.name
			address.address_type = "Billing"
			# Country is mandatory on Address and the form has no country box: use the site's country
			address.country = frappe.db.get_single_value("System Settings", "country") or "India"

		is_primary = idx == 0
		for fieldname in ADDRESS_FIELDS:
			address.set(fieldname, row.get(fieldname) or "")
		address.is_primary_address = 1 if is_primary else 0
		_relink(address, cfg, doc.name)
		address.save(ignore_permissions=True)
		kept.append(address.name)

		if is_primary:
			doc.set(cfg.primary_address_field, address.name)

	_unlink_removed(cfg, doc.name, "Address", existing, kept)


def _sync_contacts(cfg, doc, rows):
	existing = set(_linked_names(cfg, doc.name, "Contact"))
	kept = []

	# Some sites make Contact Phone.custom_mobile_number mandatory; fill it when the field exists.
	# It is a Phone field, so Frappe only accepts it with a country code (see check_phone).
	has_custom_mobile = frappe.get_meta("Contact Phone").has_field("custom_mobile_number")

	for idx, row in enumerate(rows):
		if _is_blank(row, CONTACT_FIELDS):
			continue
		# Values were trimmed and phone numbers normalised by validate_kyc
		phone, mobile, email = row.get("phone"), row.get("mobile"), row.get("email")
		first_name = row.get("first_name")

		# Only reuse a Contact that is already linked to this party, never one named by the client
		name = row.get("contact_name")
		if name in existing:
			contact = frappe.get_doc("Contact", name)
			contact.phone_nos = []
			contact.email_ids = []
		else:
			contact = frappe.new_doc("Contact")

		is_primary = idx == 0
		contact.first_name = first_name or doc.name
		contact.designation = row.get("designation") or ""
		contact.website = row.get("website") or ""
		contact.is_primary_contact = 1 if is_primary else 0
		_relink(contact, cfg, doc.name)

		for number, flag in ((phone, "is_primary_phone"), (mobile, "is_primary_mobile_no")):
			if number:
				phone_row = {"phone": number, flag: 1}
				if has_custom_mobile:
					phone_row["custom_mobile_number"] = number
				contact.append("phone_nos", phone_row)
		if email:
			contact.append("email_ids", {"email_id": email, "is_primary": 1})

		contact.save(ignore_permissions=True)
		kept.append(contact.name)

		if is_primary:
			doc.set(cfg.primary_contact_field, contact.name)

	_unlink_removed(cfg, doc.name, "Contact", existing, kept)


def _sync_bank_account(cfg, doc, data):
	"""Point the party's default bank account at the entered account (created on first use)."""
	bank_name = (data.get("custom_bank_name") or "").strip()
	account_no = (data.get("custom_account_no") or "").strip()
	ifsc = (data.get("custom_ifsc_code") or "").strip()
	if not (bank_name and account_no) or not doc.meta.has_field(cfg.bank_account_field):
		return

	bank = frappe.db.get_value("Bank", {"bank_name": bank_name}, "name")
	if not bank:
		bank = (
			frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True).name
		)

	account = frappe.db.get_value(
		"Bank Account",
		{"party_type": cfg.doctype, "party": doc.name, "bank_account_no": account_no},
		["name", "branch_code"],
		as_dict=True,
	)
	if account:
		if ifsc and ifsc != account.branch_code:
			frappe.db.set_value("Bank Account", account.name, "branch_code", ifsc)
		name = account.name
	else:
		name = (
			frappe.get_doc(
				{
					"doctype": "Bank Account",
					"account_name": f"{doc.name} - {account_no[-4:]}",
					"bank": bank,
					"bank_account_no": account_no,
					"branch_code": ifsc,  # Bank Account has no "ifsc" field: IFSC lives in branch_code
					"party_type": cfg.doctype,
					"party": doc.name,
					"is_default": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	doc.set(cfg.bank_account_field, name)


# ---------------------------------------------------------------------------
# Dropdown options
# ---------------------------------------------------------------------------


def get_select_options(doctype, fieldname):
	"""Non-empty options of a Select field (e.g. gst_category, which india_compliance defines)."""
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or not field.options:
		return []
	return [opt.strip() for opt in field.options.split("\n") if opt.strip()]


def get_tax_withholding_categories():
	return frappe.get_all("Tax Withholding Category", pluck="name", order_by="name asc")
