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

// --- Resolution pop-up -------------------------------------------------------------------
// Resolved / Closed picked without a resolution: the server keeps the status and flags the
// ticket. The page may show a cached copy of the ticket, so the flag only makes the script ask
// the server (resolution_asked), which answers with the status picked (and clears the flag), or
// nothing. The pop-up opens on that answer. Save stores the text, then sets the status.
const NEED = /^Please add a resolution message\.$/; // the exact error text
const METHOD = "sas_fortuna.support.hd_ticket.save_resolution_notes";
const ASKED = "sas_fortuna.support.hd_ticket.resolution_asked";
const flagged = {
	name: "0011",
	status: "Open",
	modified: "2026-11-17 21:00:00",
	custom_resolution_requested: 1,
};
const settle = () => new Promise((resolve) => setImmediate(resolve)); // let the server answer

// The page around the script: Helpdesk's $dialog, call, updateField and toast, and the textarea.
// `asked`: the server's answer to resolution_asked (default: what the page's copy says).
async function page(doc, { typed = "", window = {}, asked } = {}) {
	const seen = { dialogs: [], calls: [], updates: [], errors: [], closed: 0, dismissed: 0 };
	const answer =
		asked !== undefined
			? asked
			: doc.custom_resolution_requested
			? doc.custom_resolution_requested_status || "Resolved"
			: null;
	window.document = { getElementById: () => ({ value: typed }) };
	window.open = () => {};
	window.setTimeout = (fn) => fn(); // run "later" at once
	const setupForm = new Function("window", SOURCE + "\nreturn setupForm")(window);
	setupForm({
		doc,
		toast: {
			warning: () => {},
			error: (m) => seen.errors.push(m),
			dismiss: () => (seen.dismissed += 1),
		},
		$dialog: (options) => seen.dialogs.push(options),
		call: async (method, args) => {
			seen.calls.push([method, args]);
			return method === ASKED ? answer : undefined;
		},
		updateField: (field, value) => seen.updates.push([field, value]),
	});
	await settle();
	const action = (label) => seen.dialogs[0].actions.find((a) => a.label.startsWith(label));
	const click = async (label) => action(label).onClick({ close: () => (seen.closed += 1) });
	seen.saves = () => seen.calls.filter(([method]) => method === METHOD);
	return { seen, click };
}

test("flagged ticket: the Resolution pop-up opens with a required text box", async () => {
	const { seen } = await page(flagged);
	assert.equal(seen.dialogs.length, 1);
	assert.match(seen.dialogs[0].title, /Resol/);
	assert.match(seen.dialogs[0].html, /<textarea/);
	assert.match(seen.dialogs[0].html, /\*/); // marked mandatory
});

test("the server decides: a cached 'flagged' copy opens nothing once it was asked", async () => {
	const { seen } = await page(flagged, { asked: null });
	assert.deepEqual(seen.calls, [[ASKED, { ticket: "0011" }]]);
	assert.equal(seen.dialogs.length, 0);
	assert.equal(seen.dismissed, 0);
});

test("the status to set comes from the server's answer", async () => {
	const { seen, click } = await page(flagged, { asked: "Closed", typed: "Done." });
	assert.match(seen.dialogs[0].title, /Close/);
	await click("Save");
	assert.deepEqual(seen.updates, [["status", "Closed"]]);
});

test("no flag on the page: the server is not asked", async () => {
	const { seen } = await page({ ...flagged, custom_resolution_requested: 0 });
	assert.deepEqual([seen.calls, seen.dialogs], [[], []]);
});

test("opening the pop-up clears Helpdesk's 'Ticket updated successfully.' (the status did not change)", async () => {
	assert.ok((await page(flagged)).seen.dismissed >= 1);
});

test("the Resolution box keeps a minimum height (can grow, not shrink below it)", async () => {
	const { seen } = await page(flagged);
	assert.match(seen.dialogs[0].html, /min-height:\s*8rem/);
	assert.match(seen.dialogs[0].html, /resize:\s*vertical/);
});

test("the server is asked once per Resolved pick, not on every re-run of the script", async () => {
	const window = {};
	await page(flagged, { window });
	assert.equal((await page(flagged, { window })).seen.calls.length, 0);
	const again = { ...flagged, modified: "2026-11-17 21:05:00" }; // picked Resolved again
	assert.equal((await page(again, { window })).seen.dialogs.length, 1);
});

test("no pop-up once a resolution is there", async () => {
	assert.equal(
		(await page({ ...flagged, resolution_details: "<p>Reset</p>" })).seen.dialogs.length,
		0,
	);
	assert.equal(
		(await page({ ...flagged, resolution_details: "<p> </p>" })).seen.dialogs.length,
		1,
	);
});

test("Save with an empty box: error, nothing saved, status stays", async () => {
	const { seen, click } = await page(flagged, { typed: "   " });
	await click("Save");
	assert.match(seen.errors[0], NEED);
	assert.deepEqual([seen.saves(), seen.updates, seen.closed], [[], [], 0]);
});

test("Save with a resolution: stores it, then sets Resolved the normal way", async () => {
	const { seen, click } = await page(flagged, { typed: "  Replaced the sensor.  " });
	await click("Save");
	assert.deepEqual(seen.saves(), [[METHOD, { ticket: "0011", notes: "Replaced the sensor." }]]);
	assert.deepEqual(seen.updates, [["status", "Resolved"]]);
	assert.equal(seen.closed, 1);
});

test("Closed picked: the same pop-up, and Save closes the ticket", async () => {
	const closing = { ...flagged, custom_resolution_requested_status: "Closed" };
	const { seen, click } = await page(closing, { typed: "Customer confirmed." });
	assert.match(seen.dialogs[0].title, /Close/);
	await click("Save");
	assert.deepEqual(seen.updates, [["status", "Closed"]]);
});

test("Closed shows the same error text", async () => {
	const closing = { ...flagged, custom_resolution_requested_status: "Closed" };
	const { seen, click } = await page(closing);
	await click("Cancel");
	assert.match(seen.errors[0], NEED);
});

test("Cancel: error message, status stays", async () => {
	const { seen, click } = await page(flagged, { typed: "half typed" });
	await click("Cancel");
	assert.match(seen.errors[0], NEED);
	assert.deepEqual([seen.saves(), seen.updates, seen.closed], [[], [], 1]);
});

test("flagged ticket: no extra warning toast of our own", () => {
	assert.equal(run(flagged, {}).warnings.length, 0);
});

test("new or unsaved ticket: no buttons", () => {
	assert.deepEqual(run({}).actions, []);
	assert.deepEqual(run(undefined).actions, []);
});
