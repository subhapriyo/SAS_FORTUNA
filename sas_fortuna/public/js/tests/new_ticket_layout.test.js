// New Ticket page script (setup/data/fortuna_new_ticket_form.js): what it does to the PAGE, on both
// Helpdesk layouts it meets. Run with Node's own runner:
//   node --test apps/sas_fortuna/sas_fortuna/public/js/tests/*.test.js
//
// The two pages below are cut-down copies of the real markup, as measured on 25 Nov 2026:
//   OLD  Helpdesk 16.0 build (the local site): span labels, the fields in a "grid" above the Subject
//   NEW  Helpdesk 16.2.1 (Prod-Test): label elements, one flex column holding Subject, Description,
//        the field grid and Attachments, in that order
// new_ticket_form.test.js covers the form's values; this file covers the layout.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const SOURCE = fs.readFileSync(
	path.join(__dirname, "..", "..", "..", "setup", "data", "fortuna_new_ticket_form.js"),
	"utf8",
);

const OLD_PAGE = `
<div id="form">
  <div class="grid" id="grid">
    <div><span class="block">Ticket Type</span><input></div>
    <div><span class="block">Serial No</span><input></div>
    <div id="issue-wrap"><span class="block">Issue Subject</span><input></div>
  </div>
  <div id="subject-block"><span class="block">Subject </span><input maxlength="140"></div>
  <div id="desc"><div id="editor-wrap"><div class="ProseMirror"></div></div></div>
</div>`;

const NEW_PAGE = `
<div class="portal-reveal">
  <div id="column" style="display: flex; flex-direction: column">
    <div id="subject-block" class="flex w-full flex-col gap-2">
      <div class="space-y-1.5 w-full">
        <label class="block">Subject <span>*</span></label>
        <div class="relative"><input maxlength="140" placeholder="A short description"></div>
      </div>
    </div>
    <div id="desc" class="flex w-full flex-col">
      <span id="native-desc" class="mb-1.5 block">Description</span>
      <div id="editor-wrap" class="relative w-full"><div><div class="ProseMirror"></div></div></div>
    </div>
    <div id="grid" class="field-grid w-full">
      <div class="field"><div class="space-y-1.5"><label class="block">Customer</label><input></div></div>
      <div class="field"><div class="space-y-1.5"><label class="block">Ticket Type *(required)</label><input></div></div>
      <div class="field"><div class="space-y-1.5"><label class="block">Issue Subject *(required)</label><input></div></div>
    </div>
    <div id="attachments">Attachments</div>
  </div>
</div>`;

// Load the script against a page; returns the page, the form and tick() = one run of its timer.
function open(html) {
	const dom = new JSDOM(`<!doctype html><body>${html}</body>`, { url: "http://localhost/helpdesk/tickets/new" });
	const w = dom.window;
	let timer = null;
	const page = {
		document: w.document,
		location: w.location,
		setInterval: (fn) => ((timer = fn), 1),
		clearInterval: () => (timer = null),
		setTimeout: (fn) => fn(),
		getComputedStyle: w.getComputedStyle.bind(w),
		Node: w.Node,
		HTMLInputElement: w.HTMLInputElement,
		Event: w.Event,
	};
	const setupForm = new Function(...Object.keys(page), SOURCE + "\nreturn setupForm")(...Object.values(page));
	const doc = {};
	const form = setupForm({ doc, call: () => Promise.resolve({}), applyFilters: () => {} });
	const $ = (sel) => w.document.querySelector(sel);
	return { $, doc, form, tick: () => timer && timer() };
}

// Hidden by the script: this element or one around it has display none.
const hiddenUp = (el) => {
	for (; el; el = el.parentElement) if (el.style && el.style.display === "none") return true;
	return false;
};

for (const [name, html] of [["16.0", OLD_PAGE], ["16.2", NEW_PAGE]]) {
	test(`Helpdesk ${name}: its own Subject box is hidden (the Issue Subject fills it)`, () => {
		const { $, tick } = open(html);
		tick();
		assert.equal(hiddenUp($("input[maxlength='140']")), true);
	});

	test(`Helpdesk ${name}: choosing Others shows the box as "Describe your issue"`, () => {
		const { $, form, doc, tick } = open(html);
		tick();
		form.onChange.custom_issue_subject("Others");
		const label = $("#subject-block").querySelector("span.block, label.block");
		assert.match(label.textContent, /^Describe your issue/);
		assert.equal(doc.custom_issue_subject, "Others");
		assert.equal(hiddenUp($("input[maxlength='140']")), false);
	});

	test(`Helpdesk ${name}: exactly one Description label, ours with the hint`, () => {
		const { $, tick } = open(html);
		tick();
		tick(); // re-applied every few hundred ms: must not add a second heading
		const ours = $("#desc").querySelectorAll(".fortuna-description-heading");
		assert.equal(ours.length, 1);
		assert.match(ours[0].textContent, /Submit becomes active/);
		// Helpdesk's own plain "Description" label (16.2) is not shown beside ours.
		const plain = [...$("#desc").querySelectorAll("*")].filter(
			(e) => e.children.length === 0 && e.textContent.trim() === "Description" && !hiddenUp(e),
		);
		assert.deepEqual(plain, []);
	});
}

test("Helpdesk 16.2: the fields come first (Customer leads), then Describe-your-issue, then Description", () => {
	const { $, tick } = open(NEW_PAGE);
	tick();
	const order = (id) => Number($(id).style.order || 0);
	assert.ok(order("#grid") < order("#subject-block"));
	assert.ok(order("#subject-block") < order("#desc"));
	assert.ok(order("#desc") <= order("#attachments"));
});

test("Helpdesk 16.2: the page's own elements stay where Helpdesk put them (only CSS order changes)", () => {
	const { $, tick } = open(NEW_PAGE);
	tick();
	const ids = [...$("#column").children].map((c) => c.id);
	assert.deepEqual(ids, ["subject-block", "desc", "grid", "attachments"]);
});

test("Helpdesk 16.0: nothing is reordered (its fields already come first)", () => {
	const { $, tick } = open(OLD_PAGE);
	tick();
	assert.equal($("#grid").style.order, "");
	assert.equal($("#subject-block").style.order, "");
});

test("Helpdesk 16.0: Issue Subject still gets a row of its own", () => {
	const { $, tick } = open(OLD_PAGE);
	tick();
	assert.equal($("#issue-wrap").style.gridColumn, "1 / -1");
});
