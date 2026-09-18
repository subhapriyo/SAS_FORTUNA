// Copyright (c) 2026, SAS Infosystem Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier Onboarding", {
	refresh(frm) {},

	gstin(frm) {
		if (!frm.doc.gstin) return;

		const GSTIN_REGEX = /^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
		const gstin = frm.doc.gstin.trim().toUpperCase();

		if (!GSTIN_REGEX.test(gstin)) {
			frappe.msgprint(__("Please enter a valid GSTIN (e.g., 22AAAAA0000A1Z5)."));
		} else {
			frm.set_value("gstin", gstin);
		}
	},

	pan(frm) {
		if (!frm.doc.pan) return;

		const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;
		const pan = frm.doc.pan.trim().toUpperCase();

		if (!PAN_REGEX.test(pan)) {
			frappe.msgprint(__("Please enter a valid PAN (e.g., AAAAA0000A)."));
		} else {
			frm.set_value("pan", pan);
		}
	},

	validate(frm) {
		const GSTIN_REGEX = /^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
		const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;

		if (frm.doc.gstin && frm.doc.gstin.trim() !== "") {
			const gstin = frm.doc.gstin.trim().toUpperCase();
			if (!GSTIN_REGEX.test(gstin)) {
				frappe.throw(__("Please enter a valid GSTIN (e.g., 22AAAAA0000A1Z5)."));
			}
			frm.doc.gstin = gstin;
		}

		if (frm.doc.pan && frm.doc.pan.trim() !== "") {
			const pan = frm.doc.pan.trim().toUpperCase();
			if (!PAN_REGEX.test(pan)) {
				frappe.throw(__("Please enter a valid PAN (e.g., AAAAA0000A)."));
			}
			frm.doc.pan = pan;
		}
	},
});
