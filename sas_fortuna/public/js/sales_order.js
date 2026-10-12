// Sales Order extras: AMC Renew / End (F8) and Create Ticket (N9).
// Loaded through hooks.py -> doctype_js = {"Sales Order": "public/js/sales_order.js"}

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		// N9: raise a Helpdesk ticket against this service order.
		frm.add_custom_button(
			__("Helpdesk Ticket"),
			() => {
				frappe.prompt(
					[
						{ fieldname: "subject", label: __("Subject"), fieldtype: "Data", reqd: 1 },
						{
							fieldname: "ticket_type",
							label: __("Ticket Type"),
							fieldtype: "Link",
							options: "HD Ticket Type",
						},
					],
					(v) =>
						frappe.call({
							method: "sas_fortuna.support.orders.create_ticket_from_order",
							args: { sales_order: frm.doc.name, ...v },
							callback: (r) => frappe.set_route("Form", "HD Ticket", r.message),
						}),
					__("New Ticket"),
				);
			},
			__("Create"),
		);

		// F8: AMC contract actions, only on AMC orders.
		if (!frm.doc.custom_is_amc) return;
		const call = (method, msg) =>
			frappe.confirm(msg, () =>
				frappe.call({
					method: "sas_fortuna.support.amc." + method,
					args: { sales_order: frm.doc.name },
					callback: (r) =>
						r.message
							? frappe.set_route("Form", "Quotation", r.message)
							: frm.reload_doc(),
				}),
			);

		if (["Active", ""].includes(frm.doc.custom_amc_status || "")) {
			frm.add_custom_button(
				__("Renew AMC"),
				() => call("renew_amc", __("Create a renewal quotation?")),
				__("AMC"),
			);
		}
		if (frm.doc.custom_amc_status !== "Ended") {
			frm.add_custom_button(
				__("End AMC"),
				() => call("end_amc", __("Mark this AMC as ended?")),
				__("AMC"),
			);
		}
	},
});
