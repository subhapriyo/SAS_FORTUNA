// Fortuna Impex: buttons on the Helpdesk agent's ticket page (/helpdesk/tickets/<id>).
// Kept in sas_fortuna/setup/data/fortuna_ticket_actions.js; every migrate copies it into the
// HD Form Script "Fortuna Ticket Actions". Edit the file, not the record.
// Tests: sas_fortuna/public/js/tests/ticket_actions.test.js
//
// 1. Repair Order: "Create Repair Order" opens a new Repair Order (Desk form) linked to this
//    ticket; the Repair Order copies the ticket's customer, model and serial when it is saved.
//    Offered only while the ticket is being worked (Open, Replied, Paused), not once it is
//    Resolved or Closed. Once one exists, the button opens it and shows its status, in any
//    status. Helpdesk re-runs this script when the ticket changes, so it follows the status.
// 2. Coverage: a read-only dropdown with Support Type, Warranty End, AMC Expiry and Repair
//    Status. They are shown here, not in the sidebar, because Helpdesk's sidebar would let
//    agents edit them (it ignores read-only); they come from the serial number on save.
// 3. Resolution pop-up: Helpdesk has no resolution prompt and no hook on its Status dropdown,
//    so picking Resolved or Closed without a resolution keeps the old status and flags the
//    ticket with the status picked (support/hd_ticket.py). Helpdesk then re-runs this script.
//    The page may show a cached copy of the ticket, so on the flag the script asks the server
//    (resolution_asked), which answers with the status picked and clears the flag (or nothing):
//    the pop-up opens once, on that answer, never again on a reload. It is Helpdesk's own
//    $dialog with a required Resolution box:
//      Save & Resolve / Save & Close -> stores the text (save_resolution_notes), then sets the
//                        picked status through Helpdesk's normal status change; an empty box
//                        shows the error.
//      Cancel         -> "Please add a resolution message."; the status stays.
//    Each resolution is kept in the ticket's Resolution History (server side).
//
// No `icon` on the buttons: Helpdesk passes it to frappe-ui's Button, which then becomes an
// icon-only button (label hidden), and the header adds the same icon again as a prefix.

// Ticket statuses whose category is "Resolved" (Helpdesk's own: Resolved, Closed). The doc
// carries status_category; the names are a fallback for a doc loaded without it.
const RESOLVED_CATEGORY = "Resolved";
const RESOLVED_STATUSES = ["Resolved", "Closed"];

function isResolved(doc) {
	if (doc.status_category) return doc.status_category === RESOLVED_CATEGORY;
	return RESOLVED_STATUSES.includes(doc.status);
}

// --- 3. Resolution pop-up ------------------------------------------------------
const NEED_RESOLUTION = "Please add a resolution message."; // same text as the server's
const SAVE_RESOLUTION = "sas_fortuna.support.hd_ticket.save_resolution_notes";
const RESOLUTION_ASKED = "sas_fortuna.support.hd_ticket.resolution_asked";
const RESOLUTION_BOX = "fortuna-resolution-text";
const hasText = (html) => Boolean((html || "").replace(/<[^>]*>|&nbsp;/g, "").trim());

async function askResolution({ doc, toast, $dialog, call, updateField }) {
	if (!doc.custom_resolution_requested || hasText(doc.resolution_details) || !$dialog || !call) {
		return;
	}
	// Helpdesk re-runs this script on every change: ask once per Resolved pick (the ticket's
	// save time changes with each pick), not on every re-run.
	const attempt = `${doc.name}@${doc.modified}`;
	if (window.__fortunaResolutionAsked === attempt) return;
	window.__fortunaResolutionAsked = attempt;

	// The server decides (the page's copy may be cached) and clears the one-time flag.
	let target;
	try {
		target = await call(RESOLUTION_ASKED, { ticket: doc.name }); // "Resolved" / "Closed" / null
	} catch (e) {
		return;
	}
	if (!target) return;
	const verb = target === "Closed" ? "Close" : "Resolve";
	const error = (message) => toast && toast.error && toast.error(message);
	const closer = (arg) => (typeof arg === "function" ? arg : (arg && arg.close) || (() => {}));
	// Helpdesk says "Ticket updated successfully." after every save, this one too, although the
	// status did not change. Clear it (now and once more after Helpdesk's own toast) so the
	// pop-up is the only answer the agent sees.
	const clearToasts = () => toast && toast.dismiss && toast.dismiss();
	clearToasts();
	window.setTimeout(clearToasts, 300);
	$dialog({
		title: `${verb} ticket`,
		html:
			`<label for="${RESOLUTION_BOX}" class="mb-1.5 block text-sm text-ink-gray-7">` +
			`Resolution <span class="text-ink-red-4">*</span></label>` +
			// Minimum height: the box can be dragged taller, never shorter than about 5 lines.
			`<textarea id="${RESOLUTION_BOX}" rows="5" class="form-textarea w-full rounded text-base" ` +
			`style="min-height: 8rem; resize: vertical" ` +
			`placeholder="What was done for this ticket"></textarea>`,
		actions: [
			{
				label: `Save & ${verb}`,
				variant: "solid",
				onClick: async (arg) => {
					const box = window.document.getElementById(RESOLUTION_BOX);
					const notes = ((box && box.value) || "").trim();
					if (!notes) return error(NEED_RESOLUTION); // pop-up stays open
					try {
						await call(SAVE_RESOLUTION, { ticket: doc.name, notes });
					} catch (e) {
						return error((e && e.message) || NEED_RESOLUTION);
					}
					closer(arg)();
					updateField("status", target); // Helpdesk's own status change
				},
			},
			{
				label: "Cancel",
				onClick: (arg) => {
					error(NEED_RESOLUTION);
					closer(arg)();
				},
			},
		],
	});
}

function setupForm({ doc, toast, $dialog, call, updateField }) {
	if (!doc || !doc.name) return { actions: [] };
	askResolution({ doc, toast, $dialog, call, updateField });

	const openDesk = (path) => window.open(`/desk/${path}`, "_blank");
	const actions = [];

	// --- 1. Repair Order ---------------------------------------------------
	if (doc.custom_repair_order) {
		const status = doc.custom_repair_status ? ` (${doc.custom_repair_status})` : "";
		actions.push({
			label: `Repair Order ${doc.custom_repair_order}${status}`,
			onClick: () => openDesk(`repair-order/${encodeURIComponent(doc.custom_repair_order)}`),
		});
	} else if (!isResolved(doc)) {
		actions.push({
			label: "Create Repair Order",
			onClick: () => {
				if (!doc.custom_serial_no && toast && toast.warning) {
					toast.warning(
						"No Serial No on this ticket: pick the unit on the Repair Order.",
					);
				}
				openDesk(`repair-order/new?helpdesk_ticket=${encodeURIComponent(doc.name)}`);
			},
		});
	}

	// --- 2. Coverage (read-only) ---------------------------------------------
	const date = (value) =>
		value
			? new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", {
					day: "2-digit",
					month: "short",
					year: "numeric",
			  })
			: "";
	const lines = [
		["Support Type", doc.custom_support_type],
		["Warranty End", date(doc.custom_warranty_end)],
		["AMC Expiry", date(doc.custom_amc_expiry)],
		["Repair Status", doc.custom_repair_status],
	];
	const buttonLabel = `Coverage: ${doc.custom_support_type || "not checked"}`;
	for (const [label, value] of lines) {
		actions.push({
			group: "Coverage",
			buttonLabel,
			label: `${label}: ${value || "not known"}`,
			onClick: () => {},
		});
	}
	return { actions };
}
