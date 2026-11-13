"""Fortuna's answer (13 Nov 2026): paid repairs are paid in full before the repaired unit
is shipped, not before work starts.

Sites that already have the "Repair Order Flow" workflow (created once by
support_desk.create_masters) still carry the old condition on "Awaiting Payment ->
Start Repair". This patch swaps it for repair.START_REPAIR_CONDITION, which reads the
Payment Due Before setting. A condition someone changed by hand is left alone.
"""

import frappe

from sas_fortuna.support.repair import START_REPAIR_CONDITION

WORKFLOW = "Repair Order Flow"
OLD_CONDITION = "doc.payment_cleared == 1"


def execute():
	frappe.db.set_value(
		"Workflow Transition",
		{
			"parent": WORKFLOW,
			"state": "Awaiting Payment",
			"action": "Start Repair",
			"condition": OLD_CONDITION,
		},
		"condition",
		START_REPAIR_CONDITION,
	)
	frappe.clear_cache(doctype="Repair Order")
