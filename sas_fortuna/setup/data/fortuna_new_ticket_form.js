// Fortuna Impex: Helpdesk New Ticket page (customer portal and agents).
// Kept in sas_fortuna/setup/data/fortuna_new_ticket_form.js; every migrate copies it into the
// HD Form Script "Fortuna New Ticket Form". Edit the file, not the record.
//
// Layout (field order comes from the Default ticket template, setup/support_desk.py):
//   agents     Customer, Ticket Type, Serial No, Item Name, Issue Subject, description
//   customers  Ticket Type, Serial No, Issue Subject, description
//
// 1. Subject dropdown (HD Ticket.custom_issue_subject): its choices follow the Ticket Type,
//    from the Ticket Subject list, with "Others" last.
// 2. Helpdesk's own Subject box is hidden and filled with the chosen subject; on "Others" it
//    is shown on its own row as "Describe your issue" and must be typed in.
// 3. The description box gets a border and a "Description *" heading, so customers see why
//    Submit is grey.
// 4. Agents only: picking the Customer narrows Serial No to that customer's units; picking a
//    unit shows its Item Name, read only (Helpdesk's searchable dropdown shows only the
//    serial). Server side: sas_fortuna/support/new_ticket.py. Customers see neither field:
//    their Serial No choices already name the item.
//
// Job Location is not on this form: on save the server takes it from the customer's Ship To
// address and assigns an engineer at that branch (support/hd_ticket.py,
// overrides/assignment_rule.py).
// Helpdesk has no setting for 2 and 3, so they work on the page itself. If a Helpdesk update
// changes that page, they simply stop and the form works as Helpdesk ships it; the server
// still checks the subject (sas_fortuna/support/hd_ticket.py).
//
// Two page layouts are handled (public/js/tests/new_ticket_layout.test.js has a copy of each):
//   Helpdesk 16.0  field labels are <span class="block">; the field grid already sits above the
//                  Subject box and the description
//   Helpdesk 16.2  field labels are <label class="block">; one flex column holds Subject,
//                  Description (with Helpdesk's own grey label), the field grid, Attachments.
//                  The grid is shown first with CSS order (the page's elements are never moved:
//                  Helpdesk's Vue keeps them), and Helpdesk's own "Description" label gives way
//                  to ours
function setupForm({ doc, call, applyFilters }) {
	const FIELD = "custom_issue_subject";
	const OTHERS = "Others";
	const SUBJECTS_API = "sas_fortuna.support.portal.ticket_subjects_by_type";
	const ACCENT = "#e8590c";

	const subjectInput = () => document.querySelector('input[maxlength="140"]');
	// A field's label: Helpdesk 16.0 draws a <span class="block">, 16.2 a <label class="block">.
	const FIELD_LABELS = "span.block, label.block";
	// The dropdown's label: "Issue Subject" (sites before the rename: "Subject").
	const isDropdownLabel = (label) => /^(Issue )?Subject\b/.test(label.textContent.trim());

	// The child of `ancestor` that holds `el` (null when `el` is not inside it).
	function childOf(ancestor, el) {
		while (el && el.parentElement !== ancestor) el = el.parentElement;
		return el || null;
	}

	// The Subject block: the wrapper that holds the "Subject *" label and the input.
	function subjectBlock(input) {
		let el = input && input.parentElement;
		while (el && el !== document.body) {
			const first = el.firstElementChild;
			const isLabel = first && (first.tagName === "SPAN" || first.tagName === "LABEL");
			if (isLabel && !first.contains(input)) return el;
			el = el.parentElement;
		}
		return null;
	}

	function setSubject(value) {
		const input = subjectInput();
		if (!input || input.value === value) return;
		const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
		setter.call(input, value);
		input.dispatchEvent(new Event("input", { bubbles: true }));
		input.dispatchEvent(new Event("change", { bubbles: true }));
	}

	// What the Subject box should look like for the current choice.
	function showSubjectBox() {
		const input = subjectInput();
		const block = subjectBlock(input);
		if (!block) return;
		const others = doc[FIELD] === OTHERS;
		// Before any choice the box stays as Helpdesk shows it only if it was pre-filled.
		const hide = !others && (doc[FIELD] || !input.value);
		block.style.display = hide ? "none" : "";
		const label = block.firstElementChild;
		const text = label && label.firstChild;
		if (text && text.nodeType === Node.TEXT_NODE) {
			text.textContent = others ? "Describe your issue " : "Subject ";
		}
	}

	// The Subject dropdown's label: a field label reading "Issue Subject", not the one on
	// Helpdesk's own Subject box (16.2 labels that one "Subject" too).
	function subjectDropdownLabel() {
		const input = subjectInput();
		for (const label of document.querySelectorAll(FIELD_LABELS)) {
			const own = input && label.parentElement && label.parentElement.contains(input);
			if (!own && isDropdownLabel(label)) return label;
		}
		return null;
	}

	// 16.0: the fields share grid rows; the Subject dropdown gets a row of its own.
	// (16.2 lays the fields out itself: left as it is.)
	function subjectOnItsOwnRow() {
		const label = subjectDropdownLabel();
		const wrap = label && label.parentElement;
		const grid = wrap && wrap.parentElement;
		if (grid && grid.classList.contains("grid")) wrap.style.gridColumn = "1 / -1";
	}

	// 16.2: Subject, Description, the fields and Attachments are one flex column, fields third.
	// Show the fields first (Customer leads for agents), then the "Describe your issue" box (only
	// shown for Others), then the description. CSS order only: nothing is moved.
	function fieldsFirst() {
		const root = editorRoot();
		const description = root && root.parentElement;
		const column = description && description.parentElement;
		if (!column || getComputedStyle(column).display !== "flex") return;
		const fields = childOf(column, subjectDropdownLabel());
		if (!fields || fields === description) return;
		fields.style.order = "-2";
		const subject = childOf(column, subjectInput());
		if (subject && subject !== fields && subject !== description) subject.style.order = "-1";
	}

	// The description editor: the topmost element around it that does not hold the Subject box.
	function editorRoot() {
		const editor = document.querySelector(".ProseMirror");
		const input = subjectInput();
		if (!editor || !input) return null;
		let el = editor;
		while (el.parentElement && !el.parentElement.contains(input)) el = el.parentElement;
		return el.lastElementChild && el.lastElementChild.contains(editor)
			? el.lastElementChild
			: null;
	}

	function highlightDescription() {
		const root = editorRoot();
		if (!root) return;
		if (!root.dataset.fortuna) {
			root.dataset.fortuna = "1";
			root.style.border = `1.5px solid ${ACCENT}`;
			root.style.borderRadius = "8px";
			const heading = document.createElement("div");
			heading.className = "fortuna-description-heading";
			heading.style.cssText = "margin: 4px 0 6px; font-size: 14px; font-weight: 600;";
			heading.innerHTML =
				'Description <span style="color:#e03131">*</span>' +
				'<div style="font-weight:400;font-size:12px;opacity:.7">' +
				"Tell us what is not working, since when, and any error shown. " +
				"Submit becomes active once this is filled in.</div>";
			root.parentElement.insertBefore(heading, root);
		}
		// 16.2 shows its own grey "Description" label above the editor; ours (with * and the
		// hint) takes its place.
		for (const el of root.parentElement.children) {
			const plain = el !== root && !el.classList.contains("fortuna-description-heading");
			if (plain && el.textContent.trim() === "Description") el.style.display = "none";
		}
		// Show the heading only while Helpdesk shows the editor.
		const heading = root.previousElementSibling;
		if (heading && heading.classList.contains("fortuna-description-heading")) {
			heading.style.display = getComputedStyle(root).display === "none" ? "none" : "";
		}
	}

	// Helpdesk re-renders parts of the page as the customer types, so re-apply while it is open.
	const page = location.pathname;
	const timer = setInterval(() => {
		if (location.pathname !== page) return clearInterval(timer);
		try {
			subjectOnItsOwnRow();
			showSubjectBox();
			highlightDescription();
			fieldsFirst();
		} catch (e) {
			clearInterval(timer);
			console.warn("Fortuna New Ticket Form:", e);
		}
	}, 300);

	// Small "Loading subjects..." note with a spinner next to the Subject label.
	function showLoader(on) {
		const label = subjectDropdownLabel();
		if (!label) return;
		let note = label.querySelector(".fortuna-subject-loader");
		if (!on) return note && note.remove();
		if (note) return;
		if (!document.getElementById("fortuna-spin-style")) {
			const style = document.createElement("style");
			style.id = "fortuna-spin-style";
			style.textContent = "@keyframes fortuna-spin { to { transform: rotate(360deg); } }";
			document.head.appendChild(style);
		}
		note = document.createElement("span");
		note.className = "fortuna-subject-loader";
		note.style.cssText = "margin-left:8px;font-size:12px;color:#868e96;font-weight:400;";
		note.innerHTML =
			'<span style="display:inline-block;width:10px;height:10px;margin-right:4px;' +
			"border:2px solid #ced4da;border-top-color:" +
			ACCENT +
			";border-radius:50%;" +
			'vertical-align:-1px;animation:fortuna-spin .7s linear infinite"></span>Loading subjects...';
		label.appendChild(note);
	}

	// Every ticket type's choices in one call as soon as the page opens, so they are usually
	// there before the customer has picked a ticket type.
	let allChoices = null;
	const choicesReady = call(SUBJECTS_API, {})
		.then((data) => (allChoices = data || {}))
		.catch(() => (allChoices = {}));

	let wanted = null; // the ticket type the dropdown should end up showing
	async function loadSubjects(ticketType) {
		wanted = ticketType;
		setSubject("");
		if (!ticketType) return applyFilters(FIELD, []);
		if (!allChoices) {
			showLoader(true);
			await choicesReady;
			showLoader(false);
		}
		if (wanted !== ticketType) return; // the customer changed the type again meanwhile
		applyFilters(FIELD, allChoices[ticketType] || [OTHERS]);
	}

	// --- 4. Agents: Customer first, the units follow ------------------------------------------
	const CUSTOMER = "custom_erpnext_customer";
	const SERIAL = "custom_serial_no";
	const ITEM_NAME = "custom_product_name"; // labelled "Item Name"
	const DEFAULTS_API = "sas_fortuna.support.new_ticket.new_ticket_defaults";
	const ITEM_NAME_API = "sas_fortuna.support.new_ticket.serial_product";

	// Serial No offers only these units; null switches the field off (Helpdesk does that for an
	// empty or missing list). Never leave another customer's units on offer.
	const offerUnits = (serials) => applyFilters(SERIAL, serials && serials.length ? serials : null);

	let latestCustomer = null; // answers for an older pick are ignored
	async function fillFromCustomer(customer) {
		latestCustomer = customer;
		doc[SERIAL] = ""; // a unit belongs to one customer: start the choice again
		showItemName("");
		if (!customer) return offerUnits(null);

		let defaults = null;
		try {
			defaults = await call(DEFAULTS_API, { customer });
		} catch (e) {
			// Lookup failed: offer nothing (picking the customer again retries).
		}
		if (latestCustomer !== customer) return; // the agent picked another customer meanwhile
		offerUnits(defaults && defaults.serials);
	}

	let latestSerial = null; // answers for an older pick are ignored
	async function showItemName(serial) {
		latestSerial = serial;
		doc[ITEM_NAME] = "";
		if (!serial) return;
		let itemName = "";
		try {
			itemName = (await call(ITEM_NAME_API, { serial })) || "";
		} catch (e) {
			return; // left empty here; the ticket still gets it on save (fetched from the unit)
		}
		if (latestSerial === serial) doc[ITEM_NAME] = itemName;
	}

	return {
		actions: [],
		onChange: {
			[CUSTOMER]: (value) => fillFromCustomer(value),
			[SERIAL]: (value) => showItemName(value),
			ticket_type: (value) => loadSubjects(value),
			[FIELD]: (value) => {
				doc[FIELD] = value;
				setSubject(value && value !== OTHERS ? value : "");
				showSubjectBox();
				if (value === OTHERS)
					setTimeout(() => subjectInput() && subjectInput().focus(), 50);
			},
		},
	};
}
