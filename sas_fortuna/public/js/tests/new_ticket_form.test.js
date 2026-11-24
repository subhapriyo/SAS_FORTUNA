// New Ticket page script (setup/data/fortuna_new_ticket_form.js), run with Node's own runner:
//   node --test apps/sas_fortuna/sas_fortuna/public/js/tests/*.test.js
// Loaded the way Helpdesk loads an HD Form Script: new Function(script + "return setupForm").
// The page itself (DOM) is stubbed out: these tests cover what happens to the form's values.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
	path.join(__dirname, "..", "..", "..", "setup", "data", "fortuna_new_ticket_form.js"),
	"utf8",
);

const DEFAULTS_API = "sas_fortuna.support.new_ticket.new_ticket_defaults";
const PRODUCT_API = "sas_fortuna.support.new_ticket.serial_product";
const PRODUCT = "custom_product_name";
const CUSTOMER = "custom_erpnext_customer";
const SERIAL = "custom_serial_no";
const LOCATION = "custom_job_location";

// A page with nothing on it: the layout helpers find no elements and do nothing.
const PAGE = {
	document: {
		querySelector: () => null,
		querySelectorAll: () => [],
		getElementById: () => null,
	},
	location: { pathname: "/helpdesk/tickets/new" },
	setInterval: () => 0,
	clearInterval: () => {},
};

// answers: customer -> what new_ticket_defaults returns, serial -> its product name
// (either may be a function returning a promise)
function open(answers = {}) {
	const doc = {};
	const filters = [];
	const calls = [];
	const call = (method, args) => {
		calls.push([method, args]);
		if (method !== DEFAULTS_API && method !== PRODUCT_API) return Promise.resolve({});
		const answer = answers[method === DEFAULTS_API ? args.customer : args.serial];
		return typeof answer === "function" ? answer() : Promise.resolve(answer);
	};
	const applyFilters = (field, list) => filters.push([field, list]);
	const setupForm = new Function(...Object.keys(PAGE), SOURCE + "\nreturn setupForm")(
		...Object.values(PAGE),
	);
	const form = setupForm({ doc, call, applyFilters });
	const pick = async (value) => {
		doc[CUSTOMER] = value;
		await form.onChange[CUSTOMER](value);
	};
	const pickUnit = async (value) => {
		doc[SERIAL] = value;
		await form.onChange[SERIAL](value);
	};
	return { doc, filters, calls, pick, pickUnit };
}

test("Job Location is not the form's business: the server sets it from the Bill To address", async () => {
	const { doc, pick } = open({ ACME: { serials: ["SN-1"] } });
	await pick("ACME");
	assert.equal(LOCATION in doc, false);
	await pick("");
	assert.equal(LOCATION in doc, false);
});

test("picking a customer narrows Serial No to that customer's units", async () => {
	const { filters, pick } = open({ ACME: { serials: ["SN-1", "SN-2"] } });
	await pick("ACME");
	assert.deepEqual(filters.at(-1), [SERIAL, ["SN-1", "SN-2"]]);
});

test("a customer with no units: Serial No is switched off rather than offering others' units", async () => {
	const { doc, filters, pick } = open({ ACME: { serials: [] } });
	doc[SERIAL] = "SN-OLD";
	await pick("ACME");
	assert.deepEqual(filters.at(-1), [SERIAL, null]);
	assert.equal(doc[SERIAL], "");
});

test("clearing the customer clears the chosen unit", async () => {
	const { doc, filters, pick } = open({ ACME: { serials: ["SN-1"] } });
	await pick("ACME");
	doc[SERIAL] = "SN-1";
	await pick("");
	assert.equal(doc[SERIAL], "");
	assert.deepEqual(filters.at(-1), [SERIAL, null]);
});

test("only the latest customer's answer is used", async () => {
	let releaseSlow;
	const slow = () => new Promise((resolve) => (releaseSlow = resolve));
	const { filters, pick } = open({ SLOW: slow, FAST: { serials: ["SN-F"] } });
	const first = pick("SLOW");
	await pick("FAST");
	releaseSlow({ serials: ["SN-S"] });
	await first;
	assert.deepEqual(filters.at(-1), [SERIAL, ["SN-F"]]);
});

test("picking a unit shows its product name", async () => {
	const { doc, pickUnit } = open({ "SN-1": "Biometric Reader" });
	await pickUnit("SN-1");
	assert.equal(doc[PRODUCT], "Biometric Reader");
});

test("clearing the unit, or changing the customer, clears the product name", async () => {
	const { doc, pick, pickUnit } = open({ ACME: { serials: ["SN-1"] }, "SN-1": "Reader" });
	await pickUnit("SN-1");
	await pickUnit("");
	assert.equal(doc[PRODUCT], "");
	await pickUnit("SN-1");
	await pick("ACME");
	assert.equal(doc[PRODUCT], "");
});

test("only the latest unit's product name is shown", async () => {
	let releaseSlow;
	const slow = () => new Promise((resolve) => (releaseSlow = resolve));
	const { doc, pickUnit } = open({ "SN-SLOW": slow, "SN-FAST": "Fast Reader" });
	const first = pickUnit("SN-SLOW");
	await pickUnit("SN-FAST");
	releaseSlow("Slow Reader");
	await first;
	assert.equal(doc[PRODUCT], "Fast Reader");
});

test("if the lookup fails the form still works: the unit can be picked later", async () => {
	const { filters, pick } = open({ ACME: () => Promise.reject(new Error("offline")) });
	await pick("ACME");
	assert.deepEqual(filters, []);
});
