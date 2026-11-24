// Fortuna Impex: Helpdesk New Ticket page (customer portal and agents).
// Kept in sas_fortuna/setup/data/fortuna_new_ticket_form.js; every migrate copies it into the
// HD Form Script "Fortuna New Ticket Form". Edit the file, not the record.
//
// Layout: Ticket Type and Serial No on one row, the Subject dropdown on the next, then (only
// for "Others") the box to type the subject, then the description.
// 1. Subject dropdown (HD Ticket.custom_issue_subject): its choices follow the Ticket Type,
//    from the Ticket Subject list, with "Others" last.
// 2. Helpdesk's own Subject box is hidden and filled with the chosen subject; on "Others" it
//    is shown on its own row as "Describe your issue" and must be typed in.
// 3. The description box gets a border and a "Description *" heading, so customers see why
//    Submit is grey.
// 4. Agents only: Customer is the first field. Picking one fills Job Location (the customer's
//    Bill To address, else Kolkata) and narrows Serial No to that customer's units
//    (sas_fortuna/support/new_ticket.py). Customers never see these two fields.
// Helpdesk has no setting for 2 and 3, so they work on the page itself. If a Helpdesk update
// changes that page, they simply stop and the form works as Helpdesk ships it; the server
// still checks the subject (sas_fortuna/support/hd_ticket.py).
function setupForm({ doc, call, applyFilters }) {
	const FIELD = "custom_issue_subject";
	const OTHERS = "Others";
	const SUBJECTS_API = "sas_fortuna.support.portal.ticket_subjects_by_type";
	const ACCENT = "#e8590c";

	const subjectInput = () => document.querySelector('input[maxlength="140"]');
	// The dropdown's label: "Issue Subject" (sites before the rename: "Subject").
	const isDropdownLabel = (label) => /^(Issue )?Subject\b/.test(label.textContent.trim());

	// The Subject block: the wrapper that holds the "Subject *" label and the input.
	function subjectBlock(input) {
		let el = input && input.parentElement;
		while (el && el !== document.body) {
			const first = el.firstElementChild;
			if (first && first.tagName === "SPAN" && !first.contains(input)) return el;
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

	// Ticket Type and Serial No share the first row; the Subject dropdown gets a row of its own.
	function subjectOnItsOwnRow() {
		for (const label of document.querySelectorAll("span.block")) {
			const wrap = label.parentElement;
			const grid = wrap && wrap.parentElement;
			if (!grid || !grid.classList.contains("grid")) continue;
			if (isDropdownLabel(label)) {
				wrap.style.gridColumn = "1 / -1";
				return;
			}
		}
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

	function subjectDropdownLabel() {
		for (const label of document.querySelectorAll("span.block")) {
			const grid = label.parentElement && label.parentElement.parentElement;
			if (
				grid &&
				grid.classList.contains("grid") &&
				isDropdownLabel(label)
			) {
				return label;
			}
		}
		return null;
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

	// --- 4. Agents: Customer first, the rest follows ------------------------------------------
	const CUSTOMER = "custom_erpnext_customer";
	const SERIAL = "custom_serial_no";
	const LOCATION = "custom_job_location";
	const DEFAULTS_API = "sas_fortuna.support.new_ticket.new_ticket_defaults";

	let latestCustomer = null; // only the last picked customer's answer is used
	async function fillFromCustomer(customer) {
		latestCustomer = customer;
		doc[SERIAL] = ""; // a unit belongs to one customer: start the choice again
		if (!customer) {
			doc[LOCATION] = "";
			applyFilters(SERIAL, null); // no customer, no units to offer
			return;
		}
		let defaults;
		try {
			defaults = await call(DEFAULTS_API, { customer });
		} catch (e) {
			return; // the server still fills Job Location when the ticket is saved
		}
		if (latestCustomer !== customer || !defaults) return; // picked another one meanwhile
		doc[LOCATION] = defaults.job_location || "";
		// Only this customer's units; none sold to them switches the field off.
		const serials = defaults.serials || [];
		applyFilters(SERIAL, serials.length ? serials : null);
	}

	return {
		actions: [],
		onChange: {
			[CUSTOMER]: (value) => fillFromCustomer(value),
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
