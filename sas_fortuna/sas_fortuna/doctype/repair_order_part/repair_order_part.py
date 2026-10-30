# Copyright (c) 2026, SAS Infosystem Pvt Ltd and contributors
# For license information, please see license.txt

"""Child row of Repair Order: one spare part. Status is set by stock hooks (support/repair.py)."""

from frappe.model.document import Document


class RepairOrderPart(Document):
	pass
