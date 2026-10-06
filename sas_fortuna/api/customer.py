"""Whitelisted endpoints for the Customer KYC portal page (templates/pages/customer.html).

Thin wrappers: the logic is shared with the Supplier page in party_kyc.py. Keep these method
paths stable, the page calls them by name.
"""

import frappe

from sas_fortuna.api import party_kyc

CUSTOMER = party_kyc.PartyConfig(
	doctype="Customer",
	name_field="customer_name",
	bank_account_field="custom_default_customer_bank_account",
)


@frappe.whitelist()
def get_customer_doc():
	return party_kyc.get_party_kyc(CUSTOMER)


@frappe.whitelist(methods=["POST"])
def update_customer(data):
	return party_kyc.update_party_kyc(CUSTOMER, data)


@frappe.whitelist()
def get_gst_category_options():
	return party_kyc.get_select_options("Customer", "gst_category")


@frappe.whitelist()
def get_tax_withholding_category_options():
	return party_kyc.get_tax_withholding_categories()
