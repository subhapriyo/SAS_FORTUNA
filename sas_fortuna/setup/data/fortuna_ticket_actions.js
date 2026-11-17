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
// Resolution notes need nothing here: picking Resolved without notes keeps the old status and
// flags the ticket (support/hd_ticket.py); the flag shows the Resolution Details box in the
// sidebar, and Helpdesk shows the server's message saying so.
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

function setupForm({ doc, toast }) {
	if (!doc || !doc.name) return { actions: [] };

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
