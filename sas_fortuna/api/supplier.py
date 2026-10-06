"""Whitelisted endpoints for the Supplier KYC portal page (templates/pages/supplier.html).

Thin wrappers: the logic is shared with the Customer page in party_kyc.py. Keep these method
paths stable, the page calls them by name.
"""

import frappe

from sas_fortuna.api import party_kyc

SUPPLIER = party_kyc.PartyConfig(
	doctype="Supplier",
	name_field="supplier_name",
	bank_account_field="custom_default_supplier_bank_account",
)


@frappe.whitelist()
def get_supplier_doc():
	return party_kyc.get_party_kyc(SUPPLIER)


@frappe.whitelist(methods=["POST"])
def update_supplier(data):
	return party_kyc.update_party_kyc(SUPPLIER, data)


@frappe.whitelist()
def get_gst_category_options():
	return party_kyc.get_select_options("Supplier", "gst_category")


@frappe.whitelist()
def get_tax_withholding_category_options():
	return party_kyc.get_tax_withholding_categories()
