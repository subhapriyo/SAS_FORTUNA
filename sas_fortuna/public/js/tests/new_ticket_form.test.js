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

// answers: customer -> what new_ticket_defaults returns (or a function returning a promise)
function open(answers = {}) {
	const doc = {};
	const filters = [];
	const calls = [];
	const call = (method, args) => {
		calls.push([method, args]);
		if (method !== DEFAULTS_API) return Promise.resolve({});
		const answer = answers[args.customer];
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
	return { doc, filters, calls, pick };
}

test("picking a customer fills its Job Location", async () => {
	const { doc, pick } = open({ ACME: { job_location: "Hyderabad", serials: ["SN-1"] } });
	await pick("ACME");
	assert.equal(doc[LOCATION], "Hyderabad");
});

test("picking a customer narrows Serial No to that customer's units", async () => {
	const { filters, pick } = open({
		ACME: { job_location: "Kolkata", serials: ["SN-1", "SN-2"] },
	});
	await pick("ACME");
	assert.deepEqual(filters.at(-1), [SERIAL, ["SN-1", "SN-2"]]);
});

test("a customer with no units: Serial No is switched off rather than offering others' units", async () => {
	const { doc, filters, pick } = open({ ACME: { job_location: "Kolkata", serials: [] } });
	doc[SERIAL] = "SN-OLD";
	await pick("ACME");
	assert.deepEqual(filters.at(-1), [SERIAL, null]);
	assert.equal(doc[SERIAL], "");
});

test("clearing the customer clears what it filled", async () => {
	const { doc, filters, pick } = open({ ACME: { job_location: "Mumbai", serials: ["SN-1"] } });
	await pick("ACME");
	await pick("");
	assert.equal(doc[LOCATION], "");
	assert.equal(doc[SERIAL], "");
	assert.deepEqual(filters.at(-1), [SERIAL, null]);
});

test("only the latest customer's answer is used", async () => {
	let releaseSlow;
	const slow = () => new Promise((resolve) => (releaseSlow = resolve));
	const { doc, pick } = open({ SLOW: slow, FAST: { job_location: "Nagpur", serials: [] } });
	const first = pick("SLOW");
	await pick("FAST");
	releaseSlow({ job_location: "Bihar", serials: ["SN-X"] });
	await first;
	assert.equal(doc[LOCATION], "Nagpur");
});

test("if the lookup fails the form still works: the server fills Job Location on save", async () => {
	const { doc, pick } = open({ ACME: () => Promise.reject(new Error("offline")) });
	await pick("ACME");
	assert.equal(doc[LOCATION] || "", "");
});

test("the agent's choice of Job Location is kept until the customer changes", async () => {
	const { doc, calls, pick } = open({ ACME: { job_location: "Kolkata", serials: [] } });
	await pick("ACME");
	doc[LOCATION] = "Mumbai"; // agent corrects it by hand
	assert.equal(calls.filter(([m]) => m === DEFAULTS_API).length, 1);
	assert.equal(doc[LOCATION], "Mumbai");
});
