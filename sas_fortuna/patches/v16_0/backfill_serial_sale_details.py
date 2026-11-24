"""Once per site: fill sale details on serials sold before sas_fortuna's sale hooks.

support/sales.py stamps Invoice No, Invoice Date, Sold To and Warranty End on a
Serial No when a Sales Invoice / Delivery Note is submitted. Serials sold before
that code was deployed have none of these, so:
  - the daily AMC enquiry job (support/tasks.send_amc_enquiries) never finds them,
    because it selects on custom_warranty_end;
  - no AMC Opportunity can be made for them (needs custom_sold_to).

1. sales.backfill_serials(): stamp invoice, customer and warranty end from the sale
   found in the stock ledger (Serial and Batch Bundle). Safe to re-run.
2. Serials still without Warranty End but with ERPNext's own Warranty Expiry Date
   (set on delivery, or brought in with old data): use that date.
"""

import frappe


def execute():
	if not frappe.db.has_column("Serial No", "custom_warranty_end"):
		return  # support custom fields not on this site yet

	from sas_fortuna.support.sales import backfill_serials

	backfill_serials()

	sn = frappe.qb.DocType("Serial No")
	(
		frappe.qb.update(sn)
		.set(sn.custom_warranty_end, sn.warranty_expiry_date)
		.where(sn.custom_warranty_end.isnull() & sn.warranty_expiry_date.isnotnull())
		.run()
	)
