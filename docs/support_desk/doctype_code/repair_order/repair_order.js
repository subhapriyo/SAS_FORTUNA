// Repair Order form: buttons that create draft ERPNext documents.
// Status changes themselves come from the Workflow (config), not from here.

const RO_API = "sas_fortuna.support.repair.";

// Call a server method, then open the draft it created.
function ro_make(frm, method, doctype, args = {}) {
	frappe.call({
		method: RO_API + method,
		args: { repair_order: frm.doc.name, ...args },
		freeze: true,
		callback: (r) => r.message && frappe.set_route("Form", doctype, r.message),
	});
}

frappe.ui.form.on("Repair Order", {
	// Picking the ticket copies its details at once (the server re-checks on save).
	async helpdesk_ticket(frm) {
		if (!frm.doc.helpdesk_ticket) return;
		const { message: t } = await frappe.db.get_value("HD Ticket", frm.doc.helpdesk_ticket, [
			"custom_erpnext_customer",
			"custom_product_model",
			"custom_serial_no",
			"description",
		]);
		frm.set_value({
			customer: t.custom_erpnext_customer,
			product_model: t.custom_product_model,
			serial_no: t.custom_serial_no,
			complaint: t.description,
		});
	},

	setup(frm) {
		// Serial list limited to the chosen model.
		frm.set_query("serial_no", () => ({
			filters: frm.doc.product_model ? { item_code: frm.doc.product_model } : {},
		}));
		// Only this customer's addresses (standard ERPNext address query).
		frm.set_query("delivery_address", () => ({
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: { link_doctype: "Customer", link_name: frm.doc.customer },
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const s = frm.doc.status;
		const grp = __("Create");

		if (!frm.doc.repair_receipt && s === "Registered") {
			frm.add_custom_button(
				__("Repair Receipt"),
				() => ro_make(frm, "make_repair_receipt", "Stock Entry"),
				grp,
			);
		}
		if (["Unit Received", "Awaiting Payment", "In Repair"].includes(s)) {
			frm.add_custom_button(
				__("Spares Request"),
				() => ro_make(frm, "raise_spares_request", "Material Request"),
				grp,
			);
			frm.add_custom_button(
				__("Reserve Spares"),
				() => ro_make(frm, "reserve_spares", "Stock Entry"),
				grp,
			);
		}
		if (s === "In Repair") {
			frm.add_custom_button(
				__("Consume Spares"),
				() => ro_make(frm, "consume_spares", "Stock Entry"),
				grp,
			);
		}
		if (frm.doc.invoice_method === "Chargeable" && !frm.doc.quotation) {
			frm.add_custom_button(
				__("Quotation"),
				() => ro_make(frm, "make_quotation", "Quotation"),
				grp,
			);
		}
		if (s === "Ready") {
			frm.add_custom_button(
				__("Dispatch"),
				() => ro_make(frm, "make_dispatch", "Delivery Note"),
				grp,
			);
			frm.add_custom_button(
				__("Dispatch Replacement"),
				() => {
					frappe.prompt(
						{
							fieldname: "serial",
							label: __("Replacement Serial No"),
							fieldtype: "Link",
							options: "Serial No",
							reqd: 1,
							get_query: () => ({
								filters: { item_code: frm.doc.product_model, status: "Active" },
							}),
						},
						(v) =>
							ro_make(frm, "make_dispatch", "Delivery Note", {
								replacement_serial: v.serial,
							}),
						__("Replacement Unit"),
					);
				},
				grp,
			);
		}
		if (["Unit Received", "In Repair"].includes(s)) {
			frm.add_custom_button(
				__("Loaner Gate Pass"),
				() => {
					frappe.new_doc("Returnable Gate Pass", {
						repair_order: frm.doc.name,
						customer: frm.doc.customer,
						helpdesk_ticket: frm.doc.helpdesk_ticket,
					});
				},
				grp,
			);
		}
	},
});

// Parts table: Rate is fetched from the Item (fetch_from, config); keep totals live.
frappe.ui.form.on("Repair Order Part", {
	qty: (frm) => frm.trigger("recalc"),
	rate: (frm) => frm.trigger("recalc"),
	is_chargeable: (frm) => frm.trigger("recalc"),
});
frappe.ui.form.on("Repair Order", {
	recalc(frm) {
		let total = 0;
		(frm.doc.parts || []).forEach((p) => {
			p.amount = flt(p.qty) * flt(p.rate);
			if (p.is_chargeable) total += p.amount;
		});
		frm.set_value("parts_chargeable_total", total);
		frm.refresh_field("parts");
	},
});
