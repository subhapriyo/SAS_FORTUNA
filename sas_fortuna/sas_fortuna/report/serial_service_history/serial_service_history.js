// Serial Service History  (Query Report, SQL in serial_service_history.json)
// F7: one timeline per unit (tickets, repairs, AMC contracts).

frappe.query_reports["Serial Service History"] = {
	filters: [
		{
			fieldname: "serial_no",
			label: __("Serial No"),
			fieldtype: "Link",
			options: "Serial No",
			reqd: 1,
		},
	],
};
