// HD Ticket in the DESK view (/desk/.../hd-ticket/<id>).
// The Helpdesk agent app (/helpdesk) is a separate Vue UI and does not run Desk scripts: its
// buttons and Resolution pop-up come from setup/data/fortuna_ticket_actions.js.
// Tests: public/js/tests/hd_ticket_form.test.js
// Wrapped in its own scope: Desk loads form scripts into one page, so names here must not clash.
(() => {
	// The finished statuses (category "Resolved" in Helpdesk): both need a resolution.
	const FINISHED = ["Resolved", "Closed"];
	const NEED_RESOLUTION = __("Please add a resolution message."); // same text as the server's
	const hasText = (html) => Boolean((html || "").replace(/<[^>]*>|&nbsp;/g, "").trim());

	// C3: picking Resolved or Closed (from an open status) without a resolution opens a pop-up
	// with a required Resolution box. Save fills Resolution Details and saves the ticket with the
	// picked status (the server then adds it to the Resolution History). An empty box, or closing
	// the pop-up, shows the error and puts the status back. The server enforces the same rule.
	function askResolution(frm) {
		const before = frm._fortuna_saved_status; // the status the ticket was saved with
		const target = frm.doc.status; // Resolved or Closed
		const verb = target === "Closed" ? __("Close") : __("Resolve");
		let resolved = false;
		const dialog = new frappe.ui.Dialog({
			title: __("{0} ticket", [verb]),
			fields: [
				{
					fieldname: "resolution",
					fieldtype: "Small Text",
					label: __("Resolution"),
					description: __("Required: what was done for this ticket."),
				},
			],
			primary_action_label: __("Save & {0}", [verb]),
			primary_action() {
				const text = (dialog.get_value("resolution") || "").trim();
				if (!text) {
					frappe.show_alert({ message: NEED_RESOLUTION, indicator: "red" });
					return; // the pop-up stays open
				}
				const html = text
					.split("\n")
					.map((line) => `<p>${frappe.utils.escape_html(line)}</p>`)
					.join("");
				frm.doc.resolution_details = html;
				frm.set_value("resolution_details", html);
				frm.doc.status = target;
				resolved = true;
				dialog.hide();
				frm.save();
			},
			onhide() {
				if (resolved) return;
				frappe.show_alert({ message: NEED_RESOLUTION, indicator: "red" });
				frm.set_value("status", before);
			},
		});
		dialog.show();
	}

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

		refresh(frm) {
			frm._fortuna_saved_status = frm.doc.status; // for the Resolution pop-up's Cancel
			// D1: open a new Repair Order pre-linked to this ticket.
			if (frm.is_new() || frm.doc.custom_repair_order) return;
			frm.add_custom_button(
				__("Repair Order"),
				() => {
					frappe.new_doc("Repair Order", { helpdesk_ticket: frm.doc.name });
				},
				__("Create"),
			);
		},

		status(frm) {
			// Only into a finished status from an open one: Resolved -> Closed asks nothing.
			const finishing =
				FINISHED.includes(frm.doc.status) && !FINISHED.includes(frm._fortuna_saved_status);
			if (finishing && !hasText(frm.doc.resolution_details)) askResolution(frm);
		},
	});
})();
