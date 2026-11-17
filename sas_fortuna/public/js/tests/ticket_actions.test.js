// Helpdesk ticket page buttons (setup/data/fortuna_ticket_actions.js), run with Node's own runner:
//   node --test apps/sas_fortuna/sas_fortuna/public/js/tests/*.test.js
// Loaded the way Helpdesk loads an HD Form Script: new Function(script + "return setupForm").
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
	path.join(__dirname, "..", "..", "..", "setup", "data", "fortuna_ticket_actions.js"),
	"utf8",
);

function run(doc, window = { open: () => {} }) {
	const opened = [];
	const warnings = [];
	window.open = (url, target) => opened.push([url, target]);
	const setupForm = new Function("window", SOURCE + "\nreturn setupForm")(window);
	const form = setupForm({ doc, toast: { warning: (m) => warnings.push(m) } });
	return { actions: form.actions, opened, warnings };
}

const button = (actions, start) => actions.find((a) => !a.group && a.label.startsWith(start));
const coverage = (actions) => actions.filter((a) => a.group === "Coverage");

test("no Repair Order yet: Create Repair Order opens a new one linked to the ticket", () => {
	const { actions, opened } = run({ name: "0011", custom_serial_no: "SN-1" });
	button(actions, "Create Repair Order").onClick();
	assert.deepEqual(opened, [["/desk/repair-order/new?helpdesk_ticket=0011", "_blank"]]);
});

test("no serial on the ticket: still opens, with a hint to fill it in", () => {
	const { actions, opened, warnings } = run({ name: "0011" });
	button(actions, "Create Repair Order").onClick();
	assert.equal(opened.length, 1);
	assert.equal(warnings.length, 1);
});

test("with a Repair Order: the button opens it, showing its status", () => {
	const { actions, opened } = run({
		name: "0011",
		custom_repair_order: "RO-0007",
		custom_repair_status: "In Repair",
	});
	assert.equal(button(actions, "Create"), undefined);
	const open = button(actions, "Repair Order");
	assert.match(open.label, /RO-0007.*In Repair/);
	open.onClick();
	assert.deepEqual(opened, [["/desk/repair-order/RO-0007", "_blank"]]);
});

test("coverage dropdown: read-only lines under the support type", () => {
	const { actions } = run({
		name: "0011",
		custom_support_type: "AMC",
		custom_warranty_end: "2026-03-31",
		custom_amc_expiry: "2027-03-31",
		custom_repair_status: "In Repair",
		custom_repair_order: "RO-0007",
	});
	const lines = coverage(actions);
	assert.ok(lines.every((a) => a.buttonLabel === "Coverage: AMC"));
	const text = lines.map((a) => a.label).join(" | ");
	for (const part of [
		"Support Type: AMC",
		"Warranty End:",
		"AMC Expiry:",
		"Repair Status: In Repair",
	]) {
		assert.ok(text.includes(part), part);
	}
	assert.ok(text.includes("2027"), "dates are shown");
});

test("nothing known yet: coverage says so, no blanks", () => {
	const lines = coverage(run({ name: "0011" }).actions);
	assert.equal(lines[0].buttonLabel, "Coverage: not checked");
	assert.ok(lines.every((a) => !a.label.endsWith(": ")));
});

test("Create Repair Order shows while the ticket is being worked (Open, Replied, Paused)", () => {
	for (const [status, status_category] of [
		["Open", "Open"],
		["Replied", "Paused"],
		["Paused", "Paused"],
	]) {
		const { actions } = run({ name: "0011", status, status_category });
		assert.ok(button(actions, "Create Repair Order"), status);
	}
});

test("no Create Repair Order once the ticket is Resolved or Closed", () => {
	for (const status of ["Resolved", "Closed"]) {
		const { actions } = run({ name: "0011", status, status_category: "Resolved" });
		assert.equal(button(actions, "Create"), undefined, status);
		assert.equal(coverage(actions).length, 4, `${status}: coverage still shown`);
	}
});

test("a resolved ticket still links to its Repair Order", () => {
	const { actions } = run({
		name: "0011",
		status: "Closed",
		status_category: "Resolved",
		custom_repair_order: "RO-0007",
		custom_repair_status: "Dispatched",
	});
	assert.match(button(actions, "Repair Order").label, /RO-0007/);
});

test("a status Fortuna adds later follows its category", () => {
	const open = run({ name: "0011", status: "Awaiting Unit", status_category: "Paused" });
	assert.ok(button(open.actions, "Create Repair Order"));
	const done = run({ name: "0011", status: "Cancelled", status_category: "Resolved" });
	assert.equal(button(done.actions, "Create"), undefined);
});

test("no category on the doc (older Helpdesk): known resolved names still hide it", () => {
	assert.equal(button(run({ name: "0011", status: "Resolved" }).actions, "Create"), undefined);
	assert.equal(button(run({ name: "0011", status: "Closed" }).actions, "Create"), undefined);
	assert.ok(button(run({ name: "0011", status: "Open" }).actions, "Create Repair Order"));
});

test("buttons carry no `icon`: Helpdesk would draw it twice and hide the label", () => {
	for (const doc of [{ name: "0011" }, { name: "0011", custom_repair_order: "RO-0007" }]) {
		for (const action of run(doc).actions) {
			assert.equal(action.icon, undefined, action.label);
		}
	}
});

// Resolved picked without notes: the server keeps the status, flags the ticket and says so
// itself (Helpdesk shows the server's message as a toast; seen in the browser). A second toast
// from this script would only repeat it.
test("flagged ticket: no toast of our own (the server's message is shown)", () => {
	const flagged = { name: "0011", status: "Open", custom_resolution_requested: 1 };
	assert.equal(run(flagged, {}).warnings.length, 0);
});

test("new or unsaved ticket: no buttons", () => {
	assert.deepEqual(run({}).actions, []);
	assert.deepEqual(run(undefined).actions, []);
});
