// HD Ticket in the DESK view (/desk/.../hd-ticket/<id>).
// The Helpdesk agent app (/helpdesk) is a separate Vue UI and does not run
// Desk scripts; agents open the Desk view for these two helpers.

frappe.ui.form.on("HD Ticket", {
	// N4: serial list follows the chosen model.
	setup(frm) {
		frm.set_query("custom_serial_no", () => ({
			filters: frm.doc.custom_product_model
				? { item_code: frm.doc.custom_product_model }
				: {},
		}));
	},

	custom_product_model(frm) {
		frm.set_value("custom_serial_no", null);
	},

	// D1: open a new Repair Order pre-linked to this ticket.
	refresh(frm) {
		if (frm.is_new() || frm.doc.custom_repair_order) return;
		frm.add_custom_button(
			__("Repair Order"),
			() => {
				frappe.new_doc("Repair Order", { helpdesk_ticket: frm.doc.name });
			},
			__("Create"),
		);
	},
});
