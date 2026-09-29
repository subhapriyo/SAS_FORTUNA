/* sas_fortuna portal: shared filter bar for list pages.
 * Order (same on every page): Filter by Status | Filter by Date Range | Sort by | Sort order | Clear | Items per Page.
 * Items per Page is always the last control. All values go to the server as URL params
 * (status, sf_from, sf_to, sort_by, sort_dir, sf_len); see sas_fortuna/overrides/portal_list.py.
 * The bar is only shown when the list has rows (or a filter is active, so it can still be cleared). */
frappe.ready(() => {
	const PAGE_SIZES = ["10", "25", "50", "100", "all"];
	const DEFAULT_PAGE_SIZE = "10";

	const PAGES = {
		// Supplier role
		"/rfq": {
			status: ["Draft", "Submitted", "Cancelled"],
			sort: { transaction_date: "Date", name: "Number" },
		},
		"/supplier-quotations": {
			status: ["Draft", "Submitted", "Cancelled"],
			sort: { transaction_date: "Date", valid_till: "Valid till", grand_total: "Amount" },
		},
		"/purchase-orders": {
			status: ["To Receive and Bill", "To Bill", "To Receive", "Completed", "Cancelled"],
			sort: {
				transaction_date: "Date",
				schedule_date: "Required by",
				grand_total: "Amount",
			},
		},
		"/purchase-invoices": {
			status: [
				"Draft",
				"Submitted",
				"Paid",
				"Unpaid",
				"Overdue",
				"Partly Paid",
				"Return",
				"Debit Note Issued",
			],
			sort: {
				posting_date: "Date",
				name: "Number",
				bill_no: "Supplier Invoice No",
				bill_date: "Supplier Invoice Date",
				due_date: "Due date",
				grand_total: "Amount",
				outstanding_amount: "Outstanding",
			},
		},
		// Customer role
		"/quotations": {
			status: ["Draft", "Open", "Ordered", "Partially Ordered", "Expired", "Lost"],
			sort: { transaction_date: "Date", grand_total: "Amount", name: "Number" },
		},
		"/orders": {
			status: ["To Deliver and Bill", "To Bill", "To Deliver", "Completed", "Cancelled"],
			sort: {
				transaction_date: "Date",
				po_no: "Customer's PO",
				po_date: "Customer's PO Date",
				delivery_date: "Delivery",
				grand_total: "Amount",
			},
		},
		"/invoices": {
			status: ["Paid", "Unpaid", "Overdue", "Partly Paid", "Return", "Credit Note Issued"],
			sort: {
				posting_date: "Date",
				po_date: "Customer's PO Date",
				due_date: "Due date",
				grand_total: "Amount",
				outstanding_amount: "Outstanding",
			},
		},
		"/shipments": {
			status: ["To Bill", "Completed", "Return Issued", "Cancelled"],
			sort: {
				posting_date: "Date",
				po_date: "Customer's PO Date",
				grand_total: "Amount",
				name: "Number",
			},
		},
		"/issues": {
			status: ["Open", "Replied", "On Hold", "Resolved", "Closed"],
			sort: { creation: "Created", modified: "Last updated", priority: "Priority" },
		},
	};

	const cfg = PAGES[location.pathname.replace(/\/+$/, "")];
	if (!cfg) return;

	const params = new URLSearchParams(location.search);
	const T = (text) => (typeof __ === "function" ? __(text) : text); // translate when available
	const esc = (text) =>
		String(text).replace(
			/[&<>"']/g,
			(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
		);
	const opts = (obj) =>
		Object.entries(obj)
			.map(([v, l]) => `<option value="${esc(v)}">${esc(T(l))}</option>`)
			.join("");

	// One labelled control. Every control gets a visible title so no filter is ever unlabelled.
	const field = (id, title, control, extra = "") =>
		`<div class="sf-field ${extra}"><label class="sf-label" for="${id}">${T(
			title,
		)}</label>${control}</div>`;

	const bar = document.createElement("div");
	bar.className = "sf-filter-bar";
	bar.setAttribute("role", "search");
	bar.innerHTML =
		field(
			"sf-status",
			"Filter by Status",
			`<select id="sf-status">
				<option value="">${T("All statuses")}</option>
				${cfg.status.map((s) => `<option value="${esc(s)}">${esc(T(s))}</option>`).join("")}
			</select>`,
		) +
		// Date range: native date inputs open the browser calendar; filtering happens server-side.
		`<fieldset class="sf-field sf-field-range">
			<legend class="sf-label">${T("Filter by Date Range")}</legend>
			<div class="sf-range">
				<label class="sf-sub" for="sf-from"><span>${T(
					"Start Date",
				)}</span><input type="date" id="sf-from" /></label>
				<label class="sf-sub" for="sf-to"><span>${T(
					"End Date",
				)}</span><input type="date" id="sf-to" /></label>
				<button type="button" class="sf-apply" id="sf-apply">${T("Apply")}</button>
			</div>
		</fieldset>` +
		field(
			"sf-sort",
			"Sort by",
			`<select id="sf-sort"><option value="">${T("Default")}</option>${opts(
				cfg.sort,
			)}</select>`,
		) +
		field(
			"sf-dir",
			"Sort Order",
			`<select id="sf-dir">
				<option value="desc">${T("Newest / High first")}</option>
				<option value="asc">${T("Oldest / Low first")}</option>
			</select>`,
		) +
		`<button type="button" class="sf-clear" id="sf-clear">${T("Clear")}</button>` +
		// Items per Page must stay the LAST control in the bar.
		field(
			"sf-len",
			"Items per Page",
			`<select id="sf-len">
				${PAGE_SIZES.map((n) => `<option value="${n}">${n === "all" ? T("All items") : n}</option>`).join(
					"",
				)}
			</select>`,
			"sf-field-last",
		);

	const anchor =
		document.querySelector(".website-list, .web-list-container, #website-list") ||
		document.querySelector(".page-content, main");
	if (!anchor) return;
	anchor.parentNode.insertBefore(bar, anchor);

	// Show the bar only when the list has rows. If a status/date filter is active the bar stays
	// visible even for 0 results, otherwise the user could not clear the filter. Rows can be
	// (re)drawn after load (e.g. the ajax "More" call), so re-check on DOM changes.
	const ROWS =
		".sf-table tbody tr, .sf-qrow, .website-list .list-item-container, .website-list .web-list-item";
	const filtersActive = ["status", "sf_from", "sf_to"].some((key) => params.get(key));
	const syncVisibility = () => {
		const hidden = !(filtersActive || document.querySelector(ROWS));
		if (bar.hidden !== hidden) bar.hidden = hidden;
	};
	syncVisibility();
	new MutationObserver(syncVisibility).observe(anchor.parentNode, {
		childList: true,
		subtree: true,
	});

	// Reload with the given params changed. Any filter/sort/size change goes back to page 1.
	const reload = (changes) => {
		const p = new URLSearchParams(location.search);
		p.delete("sf_page");
		Object.entries(changes).forEach(([key, value]) =>
			value ? p.set(key, value) : p.delete(key),
		);
		location.search = p.toString();
	};

	// Simple selects: apply immediately on change.
	const map = {
		"sf-status": "status",
		"sf-sort": "sort_by",
		"sf-dir": "sort_dir",
		"sf-len": "sf_len",
	};
	Object.entries(map).forEach(([id, key]) => {
		const el = document.getElementById(id);
		if (params.get(key)) el.value = params.get(key);
		else if (id === "sf-len") el.value = DEFAULT_PAGE_SIZE;
		el.addEventListener("change", () => reload({ [key]: el.value }));
	});

	// Date range: applied with the Apply button (or Enter) so a range can be entered in two steps.
	const from = document.getElementById("sf-from");
	const to = document.getElementById("sf-to");
	const ISO = /^\d{4}-\d{2}-\d{2}$/;
	from.value = ISO.test(params.get("sf_from") || "") ? params.get("sf_from") : "";
	to.value = ISO.test(params.get("sf_to") || "") ? params.get("sf_to") : "";
	const syncBounds = () => {
		to.min = from.value || "";
		from.max = to.value || "";
	};
	syncBounds();
	[from, to].forEach((el) => {
		el.addEventListener("change", syncBounds);
		el.addEventListener("keydown", (e) => e.key === "Enter" && applyRange());
	});
	const applyRange = () => reload({ sf_from: from.value, sf_to: to.value });
	document.getElementById("sf-apply").addEventListener("click", applyRange);

	document.getElementById("sf-clear").addEventListener("click", () => {
		// reset filters/sort/date range/page, but keep the chosen items-per-page
		const keep = new URLSearchParams();
		if (params.get("sf_len")) keep.set("sf_len", params.get("sf_len"));
		location.search = keep.toString();
	});
});
