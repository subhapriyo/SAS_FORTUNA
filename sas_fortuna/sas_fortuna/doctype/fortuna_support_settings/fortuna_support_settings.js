// Fortuna Support Settings: only offer leaf warehouses / ledgers of the chosen company.

frappe.ui.form.on("Fortuna Support Settings", {
	setup(frm) {
		const warehouse = () => ({ filters: { company: frm.doc.company, is_group: 0 } });
		[
			"repair_in_warehouse",
			"repair_wip_warehouse",
			"spares_warehouse",
			"loaner_source_warehouse",
			"customer_loaner_warehouse",
		].forEach((f) => frm.set_query(f, warehouse));

		const expense = () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: "Expense" },
		});
		frm.set_query("warranty_expense_account", expense);
		frm.set_query("chargeable_parts_expense_account", expense);

		frm.set_query("service_charge_item", () => ({
			filters: { is_stock_item: 0, disabled: 0 },
		}));
		frm.set_query("freight_item", () => ({ filters: { is_stock_item: 0, disabled: 0 } }));
		frm.set_query("sim_recharge_item", () => ({ filters: { is_stock_item: 0, disabled: 0 } }));
		frm.set_query("repair_receipt_entry_type", () => ({
			filters: { purpose: "Material Receipt" },
		}));
	},
});
