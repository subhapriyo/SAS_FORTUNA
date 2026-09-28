/* sas_fortuna portal: filter + sort + items-per-page bar for list pages */
frappe.ready(() => {
	const PAGE_SIZES = [10, 20, 50, 100];
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
		// Customer role
		"/quotations": {
			paginate: true, // server renders numbered pager (see quotation.py)
			status: ["Open", "Ordered", "Partially Ordered", "Expired", "Lost"],
			sort: { transaction_date: "Date", grand_total: "Amount", name: "Number" },
		},
		"/orders": {
			status: ["To Deliver and Bill", "To Bill", "To Deliver", "Completed", "Cancelled"],
			sort: { transaction_date: "Date", delivery_date: "Delivery", grand_total: "Amount" },
		},
		"/invoices": {
			status: ["Paid", "Unpaid", "Overdue", "Partly Paid", "Return", "Credit Note Issued"],
			sort: {
				posting_date: "Date",
				due_date: "Due date",
				grand_total: "Amount",
				outstanding_amount: "Outstanding",
			},
		},
		"/shipments": {
			status: ["To Bill", "Completed", "Return Issued", "Cancelled"],
			sort: { posting_date: "Date", grand_total: "Amount", name: "Number" },
		},
		"/issues": {
			status: ["Open", "Replied", "On Hold", "Resolved", "Closed"],
			sort: { creation: "Created", modified: "Last updated", priority: "Priority" },
		},
	};

	const cfg = PAGES[location.pathname.replace(/\/+$/, "")];
	if (!cfg) return;

	const params = new URLSearchParams(location.search);
	const opts = (obj) =>
		Object.entries(obj)
			.map(([v, l]) => `<option value="${v}">${l}</option>`)
			.join("");

	const bar = document.createElement("div");
	bar.className = "sf-filter-bar";
	bar.innerHTML = `
    <select id="sf-status">
      <option value="">All statuses</option>
      ${cfg.status.map((s) => `<option value="${s}">${s}</option>`).join("")}
    </select>
    <select id="sf-sort">
      <option value="">Sort by</option>
      ${opts(cfg.sort)}
    </select>
    <select id="sf-dir">
      <option value="desc">Newest / High first</option>
      <option value="asc">Oldest / Low first</option>
    </select>
    ${
		cfg.paginate
			? `<select id="sf-len" title="Items per page">
      ${PAGE_SIZES.map((n) => `<option value="${n}">${n} per page</option>`).join("")}
    </select>`
			: ""
	}
    <button type="button" class="sf-clear" id="sf-clear">Clear</button>`;

	const anchor =
		document.querySelector(".website-list, .web-list-container, #website-list") ||
		document.querySelector(".page-content, main");
	if (!anchor) return;
	anchor.parentNode.insertBefore(bar, anchor);

	const map = {
		"sf-status": "status",
		"sf-sort": "sort_by",
		"sf-dir": "sort_dir",
		"sf-len": "sf_len",
	};
	Object.entries(map).forEach(([id, key]) => {
		const el = document.getElementById(id);
		if (!el) return; // sf-len only exists on paginated pages
		if (params.get(key)) el.value = params.get(key);
		else if (id === "sf-len") el.value = DEFAULT_PAGE_SIZE;
		el.addEventListener("change", () => {
			const p = new URLSearchParams(location.search);
			p.delete("sf_page"); // any filter/sort/size change goes back to page 1
			el.value ? p.set(key, el.value) : p.delete(key);
			location.search = p.toString();
		});
	});

	document.getElementById("sf-clear").addEventListener("click", () => {
		// reset filters/sort/page, but keep the chosen items-per-page
		const keep = new URLSearchParams();
		if (params.get("sf_len")) keep.set("sf_len", params.get("sf_len"));
		location.search = keep.toString();
	});
});
