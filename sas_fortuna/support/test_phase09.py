"""Phase 9 acceptance tests: every Fortuna print format renders on a real
document. Documents are rolled back; preview PDFs are kept for review in
docs/support_desk/print_previews/.

    bench --site fortuna.localhost execute sas_fortuna.support.test_phase09.run
"""

import os

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, today

from sas_fortuna.support import repair
from sas_fortuna.support.print_formats import FORMATS
from sas_fortuna.support.test_phase01 import RESULTS, check
from sas_fortuna.support.test_phase03 import _employee, _repair_order, _sell
from sas_fortuna.support.test_phase04 import SPARE, _make_sales_order, _make_spare

OUT = frappe.get_app_path("sas_fortuna", "..", "docs", "support_desk", "print_previews")


def run():
	RESULTS.clear()
	frappe.flags.mute_emails = True
	os.makedirs(OUT, exist_ok=True)
	try:
		_formats_exist()
		docs = _build_documents()
		for fmt, (doctype, name, must_show) in docs.items():
			_render(fmt, doctype, name, must_show)
	finally:
		frappe.db.rollback()
	passed = sum(ok for _, ok in RESULTS)
	print(f"\nPreviews in: {os.path.realpath(OUT)}")
	print(f"Summary: {passed} PASS, {len(RESULTS) - passed} FAIL")


def _formats_exist():
	print("\n== 1. Print formats installed")
	for name, (doctype, _html) in FORMATS.items():
		pf = frappe.db.get_value(
			"Print Format", name, ["doc_type", "print_format_type", "disabled", "standard"], as_dict=True
		)
		check(
			f"{name} on {doctype}",
			pf
			and pf.doc_type == doctype
			and pf.print_format_type == "Jinja"
			and not pf.disabled
			and pf.standard == "No",
		)
	check(
		"Job Sheet is the default for Repair Order",
		frappe.get_meta("Repair Order").default_print_format == "Fortuna Job Sheet",
	)
	check(
		"Gate Pass is the default for Returnable Gate Pass",
		frappe.get_meta("Returnable Gate Pass").default_print_format == "Fortuna Gate Pass",
	)


def _build_documents():
	s = frappe.get_single("Fortuna Support Settings")
	emp = _employee()
	_make_spare()

	# Repair under warranty, with parts
	ro, _t = _repair_order("TSN-0001", emp)
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro.name)).submit()
	ro = frappe.get_doc("Repair Order", ro.name)
	ro.diagnosis = "Power board failed; replaced under warranty."
	ro.append("parts", {"item_code": SPARE, "qty": 1, "is_chargeable": 0, "rate": 200})
	ro.save(ignore_permissions=True)

	# Loaner on a gate pass
	batch = frappe.db.get_value("Serial No", "TSN-0001", "batch_no")
	se = frappe.new_doc("Stock Entry")
	se.company = s.company
	se.purpose = se.stock_entry_type = "Material Receipt"
	se.append(
		"items",
		{
			"item_code": "TEST-MODEL-1",
			"qty": 1,
			"basic_rate": 1000,
			"t_warehouse": s.loaner_source_warehouse,
			"use_serial_batch_fields": 1,
			"serial_no": "ZZ-LOANER-9",
			"batch_no": batch,
		},
	)
	se.insert(ignore_permissions=True)
	se.submit()
	gp = frappe.get_doc(
		{
			"doctype": "Returnable Gate Pass",
			"customer": ro.customer,
			"item_code": "TEST-MODEL-1",
			"serial_no": "ZZ-LOANER-9",
			"repair_order": ro.name,
			"helpdesk_ticket": ro.helpdesk_ticket,
			"expected_return_date": add_days(today(), 10),
		}
	).insert(ignore_permissions=True)
	gp.submit()

	# Paid repair: quotation, then proforma from the accepted quotation
	_sell("Sales Invoice", "TSN-0002", update_stock=1)
	frappe.db.set_value("Serial No", "TSN-0002", "custom_warranty_end", "2026-01-01")
	ro2, _t = _repair_order("TSN-0002", emp)
	frappe.get_doc("Stock Entry", repair.make_repair_receipt(ro2.name)).submit()
	ro2 = frappe.get_doc("Repair Order", ro2.name)
	ro2.append("parts", {"item_code": SPARE, "qty": 1, "is_chargeable": 1, "rate": 200})
	ro2.save(ignore_permissions=True)
	qtn = frappe.get_doc("Quotation", repair.make_quotation(ro2.name))
	for row in qtn.items:
		row.rate = {SPARE: 650, s.service_charge_item: 400}.get(row.item_code, 150)
	qtn.save(ignore_permissions=True)
	qtn = apply_workflow(frappe.get_doc("Quotation", qtn.name), "Approve")
	so = _make_sales_order(qtn.name)
	so.delivery_date = today()
	for item in so.items:
		item.delivery_date = today()
	so.insert(ignore_permissions=True)

	# AMC contract, submitted, and its invoice
	amc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": ro.customer,
			"company": s.company,
			"delivery_date": today(),
			"custom_is_amc": 1,
			"custom_amc_start_date": today(),
			"custom_amc_end_date": add_days(today(), 364),
			"custom_coverage": "Comprehensive",
			"custom_support_mode": "On-site",
			"custom_software_version": "v4.2",
			"items": [{"item_code": "AMC Service", "qty": 2, "rate": 6000, "delivery_date": today()}],
			"custom_covered_items": [
				{"serial_no": "TSN-0001", "site": "Kolkata plant, Line 2"},
				{"serial_no": "TSN-0003", "site": "Howrah depot"},
			],
		}
	).insert(ignore_permissions=True)
	amc.submit()
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	si = make_sales_invoice(amc.name)
	si.insert(ignore_permissions=True)

	# Dispatch of the repaired unit
	frappe.db.set_value("Repair Order", ro.name, "status", "Ready")
	dn = frappe.get_doc("Delivery Note", repair.make_dispatch(ro.name))

	return {
		"Fortuna Job Sheet": (
			"Repair Order",
			ro.name,
			["Service Job Sheet", "TSN-0001", "Power board failed", "Free (warranty)", ro.name],
		),
		"Fortuna Gate Pass": (
			"Returnable Gate Pass",
			gp.name,
			["Returnable Gate Pass", "ZZ-LOANER-9", "Return by", ro.name],
		),
		"Fortuna Repair Quotation": (
			"Quotation",
			qtn.name,
			["Service Quotation", ro2.name, "TSN-0002", "Grand Total", "paid in full"],
		),
		"Fortuna Proforma Invoice": (
			"Sales Order",
			so.name,
			["Proforma Invoice", "not a tax invoice", "Grand Total"],
		),
		"Fortuna AMC Agreement": (
			"Sales Order",
			amc.name,
			["Annual Maintenance Contract", "Kolkata plant, Line 2", "TSN-0003", "Comprehensive", "v4.2"],
		),
		"Fortuna AMC Annexure": ("Sales Invoice", si.name, ["AMC Annexure", amc.name, "Howrah depot"]),
		"Fortuna Delivery Challan": (
			"Delivery Note",
			dn.name,
			["Delivery Challan", "TSN-0001", "returned after repair", "Not for sale"],
		),
	}


def _render(fmt, doctype, name, must_show):
	print(f"\n== {fmt}")
	try:
		html = frappe.get_print(doctype, name, print_format=fmt, no_letterhead=1)
	except Exception as e:
		check(f"{fmt}: renders", False, f"{type(e).__name__}: {str(e)[:200]}")
		frappe.clear_messages()
		return
	check(f"{fmt}: renders", bool(html) and "Traceback" not in html and "Error" not in html[:400])
	missing = [m for m in must_show if m not in html]
	check(f"{fmt}: shows {', '.join(str(m) for m in must_show)}", not missing, f"missing: {missing}")
	check(
		f"{fmt}: company header printed",
		frappe.db.get_single_value("Fortuna Support Settings", "company") in html,
	)
	slug = fmt.lower().replace(" ", "_")
	try:
		pdf = frappe.get_print(doctype, name, print_format=fmt, no_letterhead=1, as_pdf=True)
		with open(os.path.join(OUT, f"{slug}.pdf"), "wb") as f:
			f.write(pdf)
	except Exception as e:
		print(f"  (PDF preview not made: {type(e).__name__}; HTML saved instead)")
		with open(os.path.join(OUT, f"{slug}.html"), "w") as f:
			f.write(html)
