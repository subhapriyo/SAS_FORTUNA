// HD Ticket Desk form (public/js/hd_ticket.js): the Resolution pop-up on picking Resolved.
//   node --test apps/sas_fortuna/sas_fortuna/public/js/tests/*.test.js
// Frappe's form API is stood in for: frappe.ui.form.on collects the handlers, frappe.ui.Dialog
// records the pop-up, frm.set_value / frm.save are recorded.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hd_ticket.js"), "utf8");
const NEED = /^Please add a resolution message\.$/; // the exact error text

function form(doc) {
	const handlers = {};
	const seen = { dialogs: [], values: [], saved: 0, alerts: [] };
	class Dialog {
		constructor(options) {
			this.options = options;
			this.value = "";
			seen.dialogs.push(this);
		}
		show() {}
		hide() {
			if (this.options.onhide) this.options.onhide();
		}
		get_value() {
			return this.value;
		}
	}
	const frappe = {
		ui: { form: { on: (_dt, h) => Object.assign(handlers, h) }, Dialog },
		show_alert: (a) => seen.alerts.push(typeof a === "string" ? a : a.message),
		utils: { escape_html: (s) => s.replace(/</g, "&lt;").replace(/>/g, "&gt;") },
	};
	// __() like Frappe's: no translation here, but {0}, {1} filled from the list.
	const __ = (s, args = []) => s.replace(/\{(\d+)\}/g, (_m, i) => args[i]);
	new Function("frappe", "__", SOURCE)(frappe, __);
	const frm = {
		doc: { name: "0011", status: "Open", ...doc },
		is_new: () => false,
		set_query: () => {},
		add_custom_button: () => {},
		set_value(field, value) {
			seen.values.push([field, value]);
			this.doc[field] = value;
			return Promise.resolve();
		},
		save() {
			seen.saved += 1;
			return Promise.resolve();
		},
	};
	handlers.refresh(frm); // remembers the saved status
	const pick = (status) => {
		frm.doc.status = status;
		handlers.status(frm);
		return seen.dialogs[seen.dialogs.length - 1];
	};
	return { frm, seen, pick };
}

test("picking Resolved without a resolution opens the pop-up", () => {
	const { seen, pick } = form();
	pick("Resolved");
	assert.equal(seen.dialogs.length, 1);
	const field = seen.dialogs[0].options.fields[0];
	assert.equal(field.fieldname, "resolution");
	assert.match(field.label, /Resolution/);
});

test("no pop-up for other statuses, or with a resolution already typed", () => {
	const { seen, pick } = form({ resolution_details: "<p>Reset the device</p>" });
	pick("Paused");
	pick("Resolved");
	assert.equal(seen.dialogs.length, 0);
});

test("Save with an empty box: error, pop-up stays, nothing saved", () => {
	const { seen, pick } = form();
	const dialog = pick("Resolved");
	dialog.value = "  ";
	dialog.options.primary_action();
	assert.match(seen.alerts[0], NEED);
	assert.equal(seen.saved, 0);
});

test("Save with a resolution: fills Resolution Details and saves as Resolved", () => {
	const { frm, seen, pick } = form();
	const dialog = pick("Resolved");
	dialog.value = "Replaced the <sensor>";
	dialog.options.primary_action();
	assert.match(frm.doc.resolution_details, /Replaced the &lt;sensor&gt;/);
	assert.equal(frm.doc.status, "Resolved");
	assert.equal(seen.saved, 1);
});

test("picking Closed without a resolution opens the pop-up too", () => {
	const { frm, seen, pick } = form();
	const dialog = pick("Closed");
	assert.equal(seen.dialogs.length, 1);
	dialog.value = "Customer confirmed.";
	dialog.options.primary_action();
	assert.equal(frm.doc.status, "Closed");
	assert.equal(seen.saved, 1);
});

test("Resolved -> Closed asks nothing (the ticket already has its resolution)", () => {
	const { seen, pick } = form({ status: "Resolved" });
	pick("Closed");
	assert.equal(seen.dialogs.length, 0);
});

test("Closed shows the same error text", () => {
	const { seen, pick } = form();
	pick("Closed").hide();
	assert.match(seen.alerts[0], NEED);
});

test("closing the pop-up without a resolution: error, status goes back", () => {
	const { frm, seen, pick } = form();
	pick("Resolved").hide();
	assert.equal(frm.doc.status, "Open");
	assert.match(seen.alerts[0], NEED);
});
