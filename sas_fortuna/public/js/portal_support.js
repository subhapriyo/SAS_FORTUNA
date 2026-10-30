/* Support Desk pages for the shared portal filter bar (public/js/portal.js).
 * Loaded before portal.js, only when the Support Desk files are present (see hooks.py). */
window.sf_portal_pages = Object.assign(window.sf_portal_pages || {}, {
	"/repairs": {
		search: "Search repair no., serial no., model or problem",
		status: [
			"Registered",
			"Unit Received",
			"Awaiting Payment",
			"In Repair",
			"Ready",
			"Dispatched",
			"Closed",
			"Cancelled",
		],
		sort: {
			creation: "Date",
			modified: "Last updated",
			status: "Status",
			serial_no: "Serial No",
		},
	},
	// Helpdesk tickets (HD Ticket Status). Replaces /issues.
	"/tickets": {
		search: "Search subject, ticket no., serial no. or model",
		status: ["Open", "Replied", "Paused", "Resolved", "Closed"],
		sort: {
			creation: "Created",
			modified: "Last updated",
			status: "Status",
			priority: "Priority",
		},
	},
});
