// Browser-side format checks (public/js/sf_validation.js), run with Node's own test runner:
//   node --test apps/sas_fortuna/sas_fortuna/public/js/tests/
// The file is loaded as the browser would load it (it sets window.sfValidation).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const sandbox = { window: {} };
vm.runInNewContext(
	fs.readFileSync(path.join(__dirname, "..", "sf_validation.js"), "utf8"),
	sandbox,
);
const check = sandbox.window.sfValidation;

const ZF_INDIA = "27AAACZ3052C2ZM"; // a real, publicly registered GSTIN

function problems(data, fields = Object.keys(check.FORMATS)) {
	const found = {};
	check.checkFormats(data, fields, (field, message) => (found[field] = found[field] || message));
	return found;
}

test("valid GSTIN with matching PAN passes", () => {
	assert.deepEqual(problems({ gstin: ZF_INDIA, pan: "AAACZ3052C" }), {});
});

test("GSTIN is upper-cased and spaces removed, and shown back on screen", () => {
	const shown = {};
	const data = { gstin: "27aaacz3052c 2zm" };
	check.checkFormats(
		data,
		["gstin"],
		() => {},
		(field, value) => (shown[field] = value),
	);
	assert.equal(data.gstin, ZF_INDIA);
	assert.equal(shown.gstin, ZF_INDIA);
});

test("GSTIN with a wrong last character is refused", () => {
	assert.match(problems({ gstin: ZF_INDIA.slice(0, -1) + "N" }).gstin, /last character/);
});

test("PAN must match the GSTIN", () => {
	assert.ok(problems({ gstin: ZF_INDIA, pan: "AABFP7386H" }).pan);
});

test("other formats: good values pass, bad ones are caught", () => {
	assert.deepEqual(
		problems({ custom_ifsc_code: "sbin0001234", custom_account_no: "123456789" }),
		{},
	);
	assert.deepEqual(
		Object.keys(
			problems({ custom_ifsc_code: "SBIN1001234", custom_account_no: "12345678" }),
		).sort(),
		["custom_account_no", "custom_ifsc_code"],
	);
});

test("PIN code pattern", () => {
	assert.ok(check.PINCODE.test("700016"));
	assert.ok(!check.PINCODE.test("070016"));
	assert.ok(!check.PINCODE.test("70016"));
});

test("phone: Indian numbers", () => {
	assert.equal(check.phoneProblem("+91-98300 12345", true), "");
	assert.equal(check.phoneProblem("+91-098300 12345", true), ""); // leading 0 allowed
	assert.match(check.phoneProblem("+91-12345", false), /10 digits/);
	assert.match(check.phoneProblem("+91-03324411234", true), /landline/);
	assert.equal(check.phoneProblem("+91-03324411234", false), ""); // fine as a phone
});

test("phone: country must be chosen, digits only, sensible length", () => {
	assert.match(check.phoneProblem("9830012345", true), /country/);
	assert.match(check.phoneProblem("+91-98300abcde", true), /digits only/);
	assert.equal(check.phoneProblem("+44-7911 123456", true), "");
	assert.equal(check.phoneProblem("+44 7911 123456", true), ""); // typed with its own code
	assert.match(check.phoneProblem("+44-123", true), /too short/);
	assert.match(check.phoneProblem("+44-1234567890123456", true), /too long/);
});

test("phoneValue joins the chosen country and the typed number", () => {
	const control = (typed, isd) => ({ $input: { val: () => typed }, $isd: { text: () => isd } });
	assert.equal(check.phoneValue(control("98300 12345", "+91")), "+91-98300 12345");
	assert.equal(check.phoneValue(control("+44 7911 123456", "+91")), "+44 7911 123456");
	assert.equal(check.phoneValue(control("  ", "+91")), "");
});
