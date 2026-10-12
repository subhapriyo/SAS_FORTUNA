// Returnable Gate Pass: loaner serial list limited to in-stock (Active)
// serials of the item, plus a "Mark Returned" button once the pass is open.

frappe.ui.form.on("Returnable Gate Pass", {
	setup(frm) {
		frm.set_query("serial_no", () => ({
			filters: { item_code: frm.doc.item_code, status: "Active" },
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && ["Open", "Overdue"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Mark Returned"), () =>
				frappe.call({
					method: "sas_fortuna.sas_fortuna.doctype.returnable_gate_pass.returnable_gate_pass.mark_returned",
					args: { gate_pass: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				}),
			);
		}
	},
});
