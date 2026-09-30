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
				po_no: "Customer's PO",
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
		`<div class="portal-filter-group ${extra}"><label class="portal-filter-label" for="${id}">${T(
			title,
		)}</label>${control}</div>`;

	const bar = document.createElement("div");
	bar.className = "portal-filter-bar";
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
		`<div class="portal-filter-group portal-filter-group-range" role="group" aria-labelledby="sf-range-label">
			<span class="portal-filter-label" id="sf-range-label">${T("Filter by Date Range")}</span>
			<div class="portal-filter-range">
				<label class="portal-filter-sub" for="sf-from"><span>${T(
					"Start Date",
				)}</span><input type="date" id="sf-from" /></label>
				<label class="portal-filter-sub" for="sf-to"><span>${T(
					"End Date",
				)}</span><input type="date" id="sf-to" /></label>
				<button type="button" class="portal-filter-apply" id="sf-apply">${T("Apply")}</button>
			</div>
		</div>` +
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
		`<button type="button" class="portal-filter-clear" id="sf-clear">${T("Clear")}</button>` +
		// Items per Page must stay the LAST control in the bar.
		field(
			"sf-len",
			"Items per Page",
			`<select id="sf-len">
				${PAGE_SIZES.map((n) => `<option value="${n}">${n === "all" ? T("All items") : n}</option>`).join(
					"",
				)}
			</select>`,
			"portal-filter-group-last",
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

/* sas_fortuna portal: detail pages (/orders/<name>, /invoices/<name>, ...), all rendered by ERPNext's
 * stock order.html. Two jobs, both on top of the stock markup:
 *  1. compact items grid: tags the header / item rows so portal.css can lay them out as a grid (desktop)
 *     or stacked cards (phones); item code + name on line 1, description below, extras (serial nos,
 *     Renew AMC, ...) kept and indented.
 *  2. extra "Label: value" lines under the status badge + item names + currency-symbol money, fetched
 *     from sas_fortuna.overrides.detail_extras.get_detail_extras (permission checked server-side).
 * The layout works without the fetch; the fetch only adds the extra text. */
(() => {
	const DETAIL = {
		"supplier-quotations": "Supplier Quotation",
		"purchase-orders": "Purchase Order",
		"purchase-invoices": "Purchase Invoice",
		quotations: "Quotation",
		orders: "Sales Order",
		invoices: "Sales Invoice",
		shipments: "Delivery Note",
	};
	const parts = location.pathname.replace(/^\/+|\/+$/g, "").split("/");
	const doctype = parts.length > 1 ? DETAIL[parts[0]] : null;
	if (!doctype) return;
	document.documentElement.classList.add("sf-detail"); // scopes the detail CSS in portal.css

	frappe.ready(() => {
		const container = document.querySelector(".order-container");
		if (!container) return;
		const T = (text) => (typeof __ === "function" ? __(text) : text);
		const mk = (tag, cls, text) => {
			const el = document.createElement(tag);
			if (cls) el.className = cls;
			if (text != null) el.textContent = text;
			return el;
		};

		const head = container.querySelector(".w-100 > .order-item-header");
		const rows = [...container.querySelectorAll(".w-100 > .order-items")].filter(
			(row) => row !== head,
		);
		const LABELS = ["Item", "Qty", "Rate", "Amount"];
		const KEYS = ["item", "qty", "rate", "amt"];
		const tag = (row, labelled) =>
			[...row.children].slice(0, 4).forEach((cell, i) => {
				cell.classList.add(`sf-oi-${KEYS[i]}`);
				if (labelled && i) cell.setAttribute("data-label", T(LABELS[i]));
			});

		if (head) {
			tag(head, false);
			const qtyHead = head.querySelector(".sf-oi-qty");
			if (qtyHead) qtyHead.textContent = T("Qty"); // stock header says "Quantity"
		}

		const titles = rows.map((row) => {
			tag(row, true);
			const text = row.querySelector(".item_name_and_description > div:last-child");
			if (!text) return null;
			// line 1: item code (stock prints it as a bare text node) + item name (added after the fetch)
			const codeNode = [...text.childNodes].find(
				(n) => n.nodeType === 3 && n.textContent.trim(),
			);
			const title = mk("div", "sf-oi-title");
			title.appendChild(
				mk("span", "sf-oi-code", codeNode ? codeNode.textContent.trim() : ""),
			);
			if (codeNode) text.replaceChild(title, codeNode);
			else text.prepend(title);
			// everything that is not title / description / qty (serial nos, Renew AMC, ...) stays, indented
			[...text.childNodes].forEach((n) => {
				if (n === title) return;
				if (n.nodeType === 1) {
					if (!n.matches(".item-description, .order-qty"))
						n.classList.add("sf-oi-extra");
				} else if (n.nodeType === 3 && n.textContent.trim()) {
					const wrap = mk("div", "sf-oi-extra");
					text.replaceChild(wrap, n);
					wrap.appendChild(n);
				}
			});
			return { title, text };
		});

		frappe.call({
			method: "sas_fortuna.overrides.detail_extras.get_detail_extras",
			type: "GET",
			args: { doctype, name: decodeURIComponent(parts.slice(1).join("/")) },
			callback: ({ message }) => {
				if (!message) return;
				if (message.missing && message.missing.length) {
					console.warn("sas_fortuna: field not found on", doctype, message.missing);
				}

				// header lines under the status badge (a line with no value is never sent)
				const lines = message.meta || [];
				const badgeCol = document.querySelector(".indicator-container > div:first-child");
				if (badgeCol && lines.length) {
					const box = mk("div", "sf-meta");
					lines.forEach((line) => {
						const el = mk("div", "sf-meta-line text-muted small");
						el.appendChild(mk("span", "sf-meta-label", `${line.label}: `));
						el.appendChild(document.createTextNode(line.value));
						box.appendChild(el);
					});
					badgeCol.appendChild(box);
					// Supplier Quotation: the stock page already prints Valid Till next to the date
					if (lines.some((l) => l.fieldname === "valid_till")) {
						const stock = document.querySelector(".transaction-subheading p");
						if (stock) stock.remove();
					}
				}

				// item names + money with currency symbol, matched to the rows by position
				(message.items || []).forEach((item, i) => {
					const row = rows[i];
					if (!row) return;
					const t = titles[i];
					if (t && item.item_name && item.item_name !== item.item_code) {
						t.title.appendChild(mk("span", "sf-oi-name", item.item_name));
					}
					const desc = row.querySelector(".item-description");
					if (
						desc &&
						item.item_name &&
						desc.textContent.trim() === item.item_name.trim()
					) {
						desc.hidden = true; // description just repeats the name
					} else if (desc && !desc.textContent.trim()) {
						desc.hidden = true;
					}
					const rate = row.querySelector(".sf-oi-rate");
					const amt = row.querySelector(".sf-oi-amt");
					if (rate) rate.textContent = item.rate;
					if (amt) amt.textContent = item.amount;
				});
			},
		});
	});
})();
