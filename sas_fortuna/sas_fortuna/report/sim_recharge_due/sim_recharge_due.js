// SIM Recharge Due  (Query Report, SQL in sim_recharge_due.json)
// N10: SIMs whose validity ends within the chosen number of days.

frappe.query_reports["SIM Recharge Due"] = {
	filters: [
		{
			fieldname: "days",
			label: __("Due Within (days)"),
			fieldtype: "Int",
			default: 60,
			reqd: 1,
		},
	],
};
