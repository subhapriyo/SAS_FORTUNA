/* sas_fortuna portal: filter + sort bar for list pages */
frappe.ready(() => {
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
    <button type="button" class="sf-clear" id="sf-clear">Clear</button>`;

	const anchor =
		document.querySelector(".website-list, .web-list-container, #website-list") ||
		document.querySelector(".page-content, main");
	if (!anchor) return;
	anchor.parentNode.insertBefore(bar, anchor);

	const map = { "sf-status": "status", "sf-sort": "sort_by", "sf-dir": "sort_dir" };
	Object.entries(map).forEach(([id, key]) => {
		const el = document.getElementById(id);
		if (params.get(key)) el.value = params.get(key);
		el.addEventListener("change", () => {
			const p = new URLSearchParams(location.search);
			p.delete("sf_page");
			el.value ? p.set(key, el.value) : p.delete(key);
			location.search = p.toString();
		});
	});

	document.getElementById("sf-clear").addEventListener("click", () => {
		location.search = "";
	});
});
