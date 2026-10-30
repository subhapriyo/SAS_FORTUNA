"""Fortuna print formats (Phase 9: D8, F4, F9, N1, D9).

Kept as code so they can be recreated on any site with one command (also
called from create_masters):

    bench --site fortuna.localhost execute sas_fortuna.support.print_formats.create_print_formats

Each format is a Jinja print format, module SAS Fortuna, not "standard", so
it lives in the database and is never exported into the git-tracked files.
Re-running updates the HTML and CSS in place.

Shared pieces (style, company header, signature row) are joined into each
template here, so every document looks the same. When the document is
printed with a Letter Head, the built-in company header is left out.
"""

import frappe

MODULE = "SAS Fortuna"

# ---------------------------------------------------------------------------
# Shared style: quiet, professional, prints well in black and white
# ---------------------------------------------------------------------------
CSS = """
.ff { font-size: 10.5pt; color: #1d2730; line-height: 1.4; }
.ff .ff-head { display: table; width: 100%; border-bottom: 2px solid #1d3b5c; padding-bottom: 8px; margin-bottom: 14px; }
.ff .ff-head > div { display: table-cell; vertical-align: top; }
.ff .ff-co { font-size: 15pt; font-weight: 700; color: #1d3b5c; letter-spacing: .2px; }
.ff .ff-co-sub { font-size: 9pt; color: #55626e; margin-top: 2px; }
.ff .ff-title { text-align: right; }
.ff .ff-title h2 { margin: 0; font-size: 15pt; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #1d3b5c; }
.ff .ff-title .ff-no { font-size: 10pt; color: #55626e; margin-top: 2px; }
.ff .ff-tag { display: inline-block; margin-top: 4px; padding: 1px 8px; border: 1px solid #1d3b5c;
  border-radius: 10px; font-size: 8.5pt; font-weight: 600; color: #1d3b5c; }
.ff table { width: 100%; border-collapse: collapse; }
.ff .ff-grid td { padding: 3px 8px 3px 0; vertical-align: top; width: 25%; }
.ff .ff-grid .ff-k { color: #55626e; font-size: 9pt; width: 16%; }
.ff .ff-box { border: 1px solid #c9d1d8; border-radius: 4px; padding: 8px 10px; margin-bottom: 10px; }
.ff .ff-box h4 { margin: 0 0 4px; font-size: 9pt; text-transform: uppercase; letter-spacing: .6px; color: #55626e; font-weight: 600; }
/* wkhtmltopdf has no flexbox: side-by-side boxes use table layout */
.ff .ff-cols { display: table; width: 100%; table-layout: fixed; border-spacing: 8px 0; margin: 0 -8px 10px; width: calc(100% + 16px); }
.ff .ff-cols > div { display: table-cell; vertical-align: top; }
.ff .ff-cols > .ff-box { margin-bottom: 0; }
.ff .ff-box .ff-grid td { width: auto; }
.ff .ff-box .ff-grid .ff-k { width: 1%; white-space: nowrap; padding-right: 12px; }
.ff .ff-lines { min-height: 46px; }
.ff .ff-items { margin: 6px 0 10px; }
.ff .ff-items th { background: #eef2f5; color: #1d3b5c; font-size: 9pt; font-weight: 600; text-align: left;
  padding: 5px 6px; border-bottom: 1px solid #c9d1d8; }
.ff .ff-items td { padding: 5px 6px; border-bottom: 1px solid #e3e8ec; vertical-align: top; }
.ff .ff-r { text-align: right; }
.ff .ff-c { text-align: center; }
.ff .ff-muted { color: #55626e; font-size: 9pt; }
.ff .ff-totals { width: 46%; margin-left: auto; }
.ff .ff-totals td { padding: 3px 6px; }
.ff .ff-totals .ff-grand td { border-top: 1.5px solid #1d3b5c; font-weight: 700; font-size: 11.5pt; }
.ff .ff-words { margin: 6px 0 10px; font-size: 9.5pt; }
.ff .ff-note { background: #f6f8fa; border-left: 3px solid #1d3b5c; padding: 6px 10px; margin: 8px 0; font-size: 9.5pt; }
.ff .ff-big { font-size: 13pt; font-weight: 700; color: #1d3b5c; }
.ff .ff-sign { margin-top: 38px; }
.ff .ff-sign td { width: 33%; padding-top: 30px; vertical-align: bottom; }
.ff .ff-sign .ff-line { border-top: 1px solid #1d2730; padding-top: 3px; font-size: 9pt; color: #55626e; margin-right: 18px; }
.ff .ff-foot { margin-top: 14px; font-size: 8.5pt; color: #55626e; text-align: center; }
"""

# Company header; skipped when the user prints on a Letter Head.
HEADER = """
{%- set company = doc.company or frappe.db.get_single_value("Fortuna Support Settings", "company") -%}
{%- set co_addr = frappe.get_all("Dynamic Link", filters={"link_doctype": "Company", "link_name": company, "parenttype": "Address"}, pluck="parent", limit=1) -%}
{%- set addr = frappe.get_doc("Address", co_addr[0]) if co_addr else None -%}
<div class="ff-head">
  <div>
    {%- if not letter_head %}
    <div class="ff-co">{{ company }}</div>
    {%- if addr %}
    <div class="ff-co-sub">{{ addr.address_line1 or "" }}{% if addr.address_line2 %}, {{ addr.address_line2 }}{% endif %}, {{ addr.city or "" }}{% if addr.state %}, {{ addr.state }}{% endif %} {{ addr.pincode or "" }}</div>
    <div class="ff-co-sub">{% if addr.gstin %}GSTIN {{ addr.gstin }} &middot; {% endif %}{{ addr.phone or "" }}{% if addr.email_id %} &middot; {{ addr.email_id }}{% endif %}</div>
    {%- endif %}
    {%- endif %}
  </div>
  <div class="ff-title">
    <h2>{{ _(TITLE) }}</h2>
    <div class="ff-no">{{ doc.name }}</div>
    {%- if TAG %}<div class="ff-tag">{{ _(TAG) }}</div>{% endif %}
  </div>
</div>
"""

SIGN = """
<table class="ff-sign"><tr>
  {%- for label in SIGNS %}
  <td>{% if label %}<div class="ff-line">{{ _(label) }}</div>{% endif %}</td>
  {%- endfor %}
</tr></table>
"""

# Items, taxes, totals for selling documents (Quotation, Sales Order).
MONEY = """
<table class="ff-items">
  <tr><th style="width:4%">#</th><th>{{ _("Description") }}</th><th style="width:11%">{{ _("HSN/SAC") }}</th>
      <th class="ff-r" style="width:8%">{{ _("Qty") }}</th><th class="ff-r" style="width:13%">{{ _("Rate") }}</th>
      <th class="ff-r" style="width:15%">{{ _("Amount") }}</th></tr>
  {%- for row in doc.items %}
  <tr><td>{{ loop.index }}</td>
      <td><b>{{ row.item_name }}</b>{% if row.description and row.description|striptags != row.item_name %}<div class="ff-muted">{{ row.description|striptags|truncate(160) }}</div>{% endif %}</td>
      <td>{{ row.gst_hsn_code or "" }}</td>
      <td class="ff-r">{{ row.get_formatted("qty") }} {{ row.uom or "" }}</td>
      <td class="ff-r">{{ row.get_formatted("rate", doc) }}</td>
      <td class="ff-r">{{ row.get_formatted("amount", doc) }}</td></tr>
  {%- endfor %}
</table>
<table class="ff-totals">
  <tr><td>{{ _("Net Total") }}</td><td class="ff-r">{{ doc.get_formatted("net_total") }}</td></tr>
  {%- for t in doc.taxes %}{% if t.tax_amount %}
  <tr><td>{{ t.description }}</td><td class="ff-r">{{ t.get_formatted("tax_amount", doc) }}</td></tr>
  {%- endif %}{% endfor %}
  {%- if doc.discount_amount %}
  <tr><td>{{ _("Discount") }}</td><td class="ff-r">- {{ doc.get_formatted("discount_amount") }}</td></tr>
  {%- endif %}
  <tr class="ff-grand"><td>{{ _("Grand Total") }}</td><td class="ff-r">{{ doc.get_formatted("rounded_total" if doc.rounded_total else "grand_total") }}</td></tr>
</table>
<div class="ff-words"><span class="ff-muted">{{ _("In words") }}:</span> {{ doc.in_words or "" }}</div>
"""

PARTY = """
<div class="ff-cols">
  <div class="ff-box"><h4>{{ _("Customer") }}</h4>
    <b>{{ doc.customer_name or doc.customer or doc.party_name }}</b>
    {%- if doc.address_display %}<div class="ff-muted">{{ doc.address_display }}</div>{% endif %}
    {%- if doc.contact_display %}<div class="ff-muted">{{ _("Contact") }}: {{ doc.contact_display }}{% if doc.contact_mobile %}, {{ doc.contact_mobile }}{% endif %}</div>{% endif %}
  </div>
  <div class="ff-box"><h4>{{ _("Details") }}</h4>
    <table class="ff-grid">{{ DETAILS }}</table>
  </div>
</div>
"""

TERMS = """
{%- if doc.terms %}
<div class="ff-box"><h4>{{ _("Terms and Conditions") }}</h4><div class="ff-muted">{{ doc.terms }}</div></div>
{%- endif %}
"""


def _row(label, value):
	return f'<tr><td class="ff-k">{{{{ _("{label}") }}}}</td><td>{value}</td></tr>'


def _page(title, body, tag="", signs=("Prepared by", "Authorised signatory", "Customer")):
	setup = f"{{%- set TITLE = {title!r} -%}}{{%- set TAG = {tag!r} -%}}{{%- set SIGNS = {list(signs)!r} -%}}"
	return setup + '<div class="ff">' + HEADER + body + SIGN + "</div>"


# ---------------------------------------------------------------------------
# 1. Job sheet (Repair Order)  D8
# ---------------------------------------------------------------------------
JOB_SHEET = _page(
	"Service Job Sheet",
	"""
{%- set ticket = doc.helpdesk_ticket -%}
<table class="ff-grid">
  <tr><td class="ff-k">{{ _("Date") }}</td><td>{{ frappe.format_date(doc.creation) }}</td>
      <td class="ff-k">{{ _("Ticket") }}</td><td>{{ ticket or "-" }}</td></tr>
  <tr><td class="ff-k">{{ _("Engineer") }}</td><td>{{ frappe.db.get_value("Employee", doc.responsible, "employee_name") or "-" }}</td>
      <td class="ff-k">{{ _("Status") }}</td><td>{{ _(doc.status) }}</td></tr>
</table>
<div class="ff-cols" style="margin-top:8px">
  <div class="ff-box" style="width:30%"><h4>{{ _("Customer") }}</h4>
    <b>{{ doc.customer_name or doc.customer }}</b>
    {%- if doc.delivery_address %}{% set a = frappe.get_doc("Address", doc.delivery_address) %}
    <div class="ff-muted">{{ a.address_line1 or "" }}{% if a.address_line2 %}, {{ a.address_line2 }}{% endif %}, {{ a.city or "" }} {{ a.pincode or "" }}{% if a.phone %} &middot; {{ a.phone }}{% endif %}</div>{% endif %}
    {%- if doc.contact_email %}<div class="ff-muted">{{ doc.contact_email }}</div>{% endif %}
  </div>
  <div class="ff-box" style="width:42%"><h4>{{ _("Unit") }}</h4>
    <table class="ff-grid">
      <tr><td class="ff-k">{{ _("Model") }}</td><td><b>{{ doc.product_model }}</b></td></tr>
      <tr><td class="ff-k">{{ _("Serial No") }}</td><td><b>{{ doc.serial_no }}</b></td></tr>
      <tr><td class="ff-k">{{ _("Invoice") }}</td><td>{{ doc.invoice_no or "-" }}{% if doc.invoice_date %} ({{ frappe.format_date(doc.invoice_date) }}){% endif %}</td></tr>
    </table>
  </div>
  <div class="ff-box"><h4>{{ _("Cover") }}</h4>
    <div class="ff-big">{{ _(doc.support_type or "-") }}</div>
    <div class="ff-muted">{{ _("Warranty till") }} {{ frappe.format_date(doc.warranty_end) if doc.warranty_end else "-" }}</div>
    <div class="ff-muted">{{ _("AMC till") }} {{ frappe.format_date(doc.amc_expiry) if doc.amc_expiry else "-" }}</div>
    <div class="ff-muted">{{ _("Billing") }}: {{ _(doc.invoice_method or "-") }}</div>
  </div>
</div>
<div class="ff-box"><h4>{{ _("Complaint reported") }}</h4><div class="ff-lines">{{ doc.complaint or "" }}</div></div>
<div class="ff-box"><h4>{{ _("Engineer's diagnosis") }}</h4><div class="ff-lines">{{ doc.diagnosis or "" }}</div></div>
{%- if doc.parts %}
<table class="ff-items">
  <tr><th style="width:4%">#</th><th>{{ _("Part") }}</th><th class="ff-r" style="width:10%">{{ _("Qty") }}</th><th style="width:16%">{{ _("Billing") }}</th><th style="width:16%">{{ _("Status") }}</th></tr>
  {%- for p in doc.parts %}
  <tr><td>{{ loop.index }}</td><td>{{ p.item_name or p.item_code }}</td><td class="ff-r">{{ p.get_formatted("qty") }}</td>
      <td>{{ _("Chargeable") if p.is_chargeable else _("Free (warranty)") }}</td><td>{{ _(p.status or "") }}</td></tr>
  {%- endfor %}
</table>
{%- endif %}
<div class="ff-note">{{ _("Unit received") }}: {{ doc.repair_receipt or _("not yet") }}.
  {{ _("Please quote the job sheet number") }} <b>{{ doc.name }}</b> {{ _("in all communication and when collecting the unit.") }}</div>
""",
	tag="",
	signs=("Received by (Fortuna)", "Engineer", "Customer"),
)

# ---------------------------------------------------------------------------
# 2. Returnable gate pass  N1
# ---------------------------------------------------------------------------
GATE_PASS = _page(
	"Returnable Gate Pass",
	"""
<div class="ff-cols">
  <div class="ff-box"><h4>{{ _("Issued to") }}</h4>
    <b>{{ frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer }}</b>
    {%- if doc.contact_email %}<div class="ff-muted">{{ doc.contact_email }}</div>{% endif %}
  </div>
  <div class="ff-box"><h4>{{ _("Dates") }}</h4>
    <table class="ff-grid">
      <tr><td class="ff-k">{{ _("Issued") }}</td><td>{{ frappe.format_date(doc.issue_date) }}</td></tr>
      <tr><td class="ff-k">{{ _("Return by") }}</td><td><span class="ff-big">{{ frappe.format_date(doc.expected_return_date) }}</span></td></tr>
      {%- if doc.returned_on %}<tr><td class="ff-k">{{ _("Returned") }}</td><td>{{ frappe.format_date(doc.returned_on) }}</td></tr>{% endif %}
    </table>
  </div>
</div>
<table class="ff-items">
  <tr><th style="width:4%">#</th><th>{{ _("Item") }}</th><th style="width:22%">{{ _("Serial No") }}</th><th class="ff-c" style="width:8%">{{ _("Qty") }}</th><th style="width:26%">{{ _("Against") }}</th></tr>
  <tr><td>1</td><td><b>{{ frappe.db.get_value("Item", doc.item_code, "item_name") or doc.item_code }}</b><div class="ff-muted">{{ doc.item_code }}</div></td>
      <td><b>{{ doc.serial_no }}</b></td><td class="ff-c">1</td>
      <td>{{ doc.repair_order or "" }}{% if doc.repair_order and doc.helpdesk_ticket %}<br>{% endif %}{% if doc.helpdesk_ticket %}{{ _("Ticket") }} {{ doc.helpdesk_ticket }}{% endif %}</td></tr>
</table>
<div class="ff-note">{{ _("This unit is lent by") }} {{ doc.company or frappe.db.get_single_value("Fortuna Support Settings", "company") }} {{ _("while your own unit is under repair. It remains our property. Please return it in good condition by the date above.") }}</div>
""",
	tag="Returnable",
	signs=("Issued by", "Security / gate", "Received by (customer)"),
)

# ---------------------------------------------------------------------------
# 3. Repair quotation (Quotation)  D5, N7
# ---------------------------------------------------------------------------
_REPAIR_DETAILS = (
	_row("Date", "{{ frappe.format_date(doc.transaction_date) }}")
	+ _row("Valid till", '{{ frappe.format_date(doc.valid_till) if doc.valid_till else "-" }}')
	+ "{%- if doc.custom_repair_order %}"
	+ _row("Repair order", "{{ doc.custom_repair_order }}")
	+ _row(
		"Unit",
		'{{ frappe.db.get_value("Repair Order", doc.custom_repair_order, "product_model") }} &middot; {{ frappe.db.get_value("Repair Order", doc.custom_repair_order, "serial_no") }}',
	)
	+ "{%- endif %}"
)
REPAIR_QUOTATION = _page(
	"Service Quotation",
	PARTY.replace("{{ DETAILS }}", _REPAIR_DETAILS)
	+ MONEY
	+ """
{%- set adv = frappe.db.get_single_value("Fortuna Support Settings", "advance_percent") or 100 -%}
<div class="ff-note">
  {%- if adv|int >= 100 %}{{ _("Repair work starts once this quotation is accepted and paid in full.") }}
  {%- else %}{{ _("Repair work starts once this quotation is accepted and an advance of") }} {{ adv|int }}% {{ _("is paid.") }}{% endif %}
  {{ _("You can accept it in your customer portal under My Repairs, or reply to this e-mail.") }}
</div>
"""
	+ TERMS,
	tag="Paid repair",
	signs=("Prepared by", "Authorised signatory", "Accepted by (customer)"),
)

# ---------------------------------------------------------------------------
# 4. Proforma invoice (Sales Order)  D5
# ---------------------------------------------------------------------------
_SO_DETAILS = (
	_row("Order date", "{{ frappe.format_date(doc.transaction_date) }}")
	+ "{%- if doc.po_no %}"
	+ _row("Your ref.", "{{ doc.po_no }}")
	+ "{%- endif %}"
	+ "{%- if doc.custom_repair_order %}"
	+ _row("Repair order", "{{ doc.custom_repair_order }}")
	+ "{%- endif %}"
	+ _row(
		"Payment due",
		'{{ frappe.format_date(doc.payment_schedule[0].due_date) if doc.payment_schedule else "-" }}',
	)
)
PROFORMA = _page(
	"Proforma Invoice",
	PARTY.replace("{{ DETAILS }}", _SO_DETAILS)
	+ MONEY
	+ """
{%- set bank = frappe.get_all("Bank Account", filters={"is_company_account": 1, "company": doc.company, "is_default": 1}, fields=["bank", "bank_account_no", "branch_code"], limit=1) -%}
{%- if bank %}
<div class="ff-box"><h4>{{ _("Pay to") }}</h4>
  {{ bank[0].bank }} &middot; {{ _("A/c") }} {{ bank[0].bank_account_no or "" }} &middot; IFSC {{ bank[0].branch_code or "" }}
</div>
{%- endif %}
<div class="ff-note">{{ _("This is a proforma invoice for payment, not a tax invoice. The tax invoice follows on delivery of the service.") }}</div>
"""
	+ TERMS,
	tag="Not a tax invoice",
	signs=("Prepared by", "Authorised signatory", ""),
)

# ---------------------------------------------------------------------------
# 5. AMC agreement (Sales Order)  F3, F4
# ---------------------------------------------------------------------------
AMC_AGREEMENT = _page(
	"Annual Maintenance Contract",
	"""
<div class="ff-cols">
  <div class="ff-box"><h4>{{ _("Customer") }}</h4>
    <b>{{ doc.customer_name }}</b>
    {%- if doc.address_display %}<div class="ff-muted">{{ doc.address_display }}</div>{% endif %}
    {%- if doc.custom_end_customer %}<div class="ff-muted">{{ _("End customer") }}: {{ doc.custom_end_customer }}</div>{% endif %}
  </div>
  <div class="ff-box"><h4>{{ _("Contract") }}</h4>
    <table class="ff-grid">
      <tr><td class="ff-k">{{ _("Period") }}</td><td><b>{{ frappe.format_date(doc.custom_amc_start_date) }} &ndash; {{ frappe.format_date(doc.custom_amc_end_date) }}</b></td></tr>
      <tr><td class="ff-k">{{ _("Coverage") }}</td><td>{{ _(doc.custom_coverage or "-") }}</td></tr>
      <tr><td class="ff-k">{{ _("Support") }}</td><td>{{ _(doc.custom_support_mode or "-") }}</td></tr>
      {%- if doc.custom_software_version %}<tr><td class="ff-k">{{ _("Software") }}</td><td>{{ doc.custom_software_version }}</td></tr>{% endif %}
      {%- if doc.custom_renewal_of %}<tr><td class="ff-k">{{ _("Renews") }}</td><td>{{ doc.custom_renewal_of }}</td></tr>{% endif %}
    </table>
  </div>
</div>
<h4 class="ff-muted" style="margin:6px 0 0;text-transform:uppercase;letter-spacing:.6px">{{ _("Units covered") }}</h4>
<table class="ff-items">
  <tr><th style="width:4%">#</th><th style="width:20%">{{ _("Serial No") }}</th><th>{{ _("Product") }}</th><th style="width:26%">{{ _("Site") }}</th><th style="width:16%">{{ _("Software") }}</th></tr>
  {%- for r in doc.custom_covered_items %}
  <tr><td>{{ loop.index }}</td><td><b>{{ r.serial_no }}</b></td>
      <td>{{ frappe.db.get_value("Item", r.item_code, "item_name") or r.item_code }}</td>
      <td>{{ r.site or "" }}</td><td>{{ r.software_version or "" }}</td></tr>
  {%- endfor %}
</table>
<h4 class="ff-muted" style="margin:6px 0 0;text-transform:uppercase;letter-spacing:.6px">{{ _("Contract value") }}</h4>
"""
	+ MONEY
	+ """
{%- if doc.terms %}
<div class="ff-box"><h4>{{ _("Terms of the contract") }}</h4><div class="ff-muted">{{ doc.terms }}</div></div>
{%- else %}
<div class="ff-note">{{ _("Terms of the contract: as per the AMC terms attached to this agreement.") }}</div>
{%- endif %}
""",
	tag="AMC",
	signs=("For the company", "Witness", "For the customer"),
)

# ---------------------------------------------------------------------------
# 6. Delivery challan (Delivery Note)  D7, D9
# ---------------------------------------------------------------------------
_DN_DETAILS = (
	_row("Date", "{{ frappe.format_date(doc.posting_date) }}")
	+ "{%- if doc.custom_repair_order %}"
	+ _row("Repair order", "{{ doc.custom_repair_order }}")
	+ "{%- endif %}"
	+ "{%- if doc.custom_replaces_serial %}"
	+ _row("Replaces unit", "<b>{{ doc.custom_replaces_serial }}</b>")
	+ "{%- endif %}"
	+ "{%- if doc.lr_no %}"
	+ _row(
		"LR / docket", "{{ doc.lr_no }}{% if doc.transporter_name %} ({{ doc.transporter_name }}){% endif %}"
	)
	+ "{%- endif %}"
)
DELIVERY_CHALLAN = _page(
	"Delivery Challan",
	PARTY.replace("{{ DETAILS }}", _DN_DETAILS)
	+ """
<table class="ff-items">
  <tr><th style="width:4%">#</th><th>{{ _("Item") }}</th><th style="width:28%">{{ _("Serial No(s)") }}</th><th class="ff-r" style="width:9%">{{ _("Qty") }}</th></tr>
  {%- for row in doc.items %}
  {%- set serials = (row.serial_no or "").split("\\n") | select | list -%}
  {%- if not serials and row.serial_and_batch_bundle %}{% set serials = frappe.get_all("Serial and Batch Entry", filters={"parent": row.serial_and_batch_bundle}, pluck="serial_no") %}{% endif %}
  <tr><td>{{ loop.index }}</td><td><b>{{ row.item_name }}</b><div class="ff-muted">{{ row.item_code }}</div></td>
      <td>{% for s in serials %}<b>{{ s }}</b>{% if not loop.last %}<br>{% endif %}{% endfor %}</td>
      <td class="ff-r">{{ row.get_formatted("qty") }} {{ row.uom or "" }}</td></tr>
  {%- endfor %}
</table>
<div class="ff-note">
  {%- if doc.custom_replaces_serial %}{{ _("Replacement unit sent against the customer's unit") }} {{ doc.custom_replaces_serial }}.
  {%- elif doc.custom_repair_order %}{{ _("Customer's own unit returned after repair.") }}
  {%- endif %}
  {{ _("Not for sale. No commercial value: any charges are billed separately.") }}
</div>
""",
	tag="Not for sale",
	signs=("Dispatched by", "Transporter", "Received by (customer)"),
)

# ---------------------------------------------------------------------------
# 7. AMC annexure (Sales Invoice)  F9
# ---------------------------------------------------------------------------
AMC_ANNEXURE = _page(
	"AMC Annexure",
	"""
{%- set so_names = doc.items | selectattr("sales_order") | map(attribute="sales_order") | unique | list -%}
{%- set amc = so_names | select("in", frappe.get_all("Sales Order", filters={"name": ["in", so_names or [""]], "custom_is_amc": 1}, pluck="name")) | list -%}
<table class="ff-grid">
  <tr><td class="ff-k">{{ _("Invoice") }}</td><td><b>{{ doc.name }}</b> ({{ frappe.format_date(doc.posting_date) }})</td>
      <td class="ff-k">{{ _("Customer") }}</td><td>{{ doc.customer_name }}</td></tr>
</table>
{%- for so_name in amc %}
{%- set so = frappe.get_doc("Sales Order", so_name) %}
<div class="ff-box" style="margin-top:8px"><h4>{{ _("Contract") }} {{ so.name }}</h4>
  {{ _("Period") }} <b>{{ frappe.format_date(so.custom_amc_start_date) }} &ndash; {{ frappe.format_date(so.custom_amc_end_date) }}</b>
  &middot; {{ _(so.custom_coverage or "") }} &middot; {{ _(so.custom_support_mode or "") }}
  {%- if so.custom_software_version %} &middot; {{ _("Software") }} {{ so.custom_software_version }}{% endif %}
</div>
<table class="ff-items">
  <tr><th style="width:4%">#</th><th style="width:22%">{{ _("Serial No") }}</th><th>{{ _("Product") }}</th><th style="width:30%">{{ _("Site") }}</th></tr>
  {%- for r in so.custom_covered_items %}
  <tr><td>{{ loop.index }}</td><td><b>{{ r.serial_no }}</b></td><td>{{ frappe.db.get_value("Item", r.item_code, "item_name") or r.item_code }}</td><td>{{ r.site or "" }}</td></tr>
  {%- endfor %}
</table>
{%- else %}
<div class="ff-note">{{ _("This invoice is not linked to an AMC contract.") }}</div>
{%- endfor %}
""",
	tag="Annexure to tax invoice",
	signs=("", "Authorised signatory", ""),
)

FORMATS = {
	"Fortuna Job Sheet": ("Repair Order", JOB_SHEET),
	"Fortuna Gate Pass": ("Returnable Gate Pass", GATE_PASS),
	"Fortuna Repair Quotation": ("Quotation", REPAIR_QUOTATION),
	"Fortuna Proforma Invoice": ("Sales Order", PROFORMA),
	"Fortuna AMC Agreement": ("Sales Order", AMC_AGREEMENT),
	"Fortuna Delivery Challan": ("Delivery Note", DELIVERY_CHALLAN),
	"Fortuna AMC Annexure": ("Sales Invoice", AMC_ANNEXURE),
}
# Made the default print format of their DocType (only our own DocTypes).
DEFAULT_FOR = {"Repair Order": "Fortuna Job Sheet", "Returnable Gate Pass": "Fortuna Gate Pass"}


def create_print_formats():
	"""Create or update every Fortuna print format. Safe to re-run."""
	done = []
	for name, (doctype, html) in FORMATS.items():
		values = {
			"doc_type": doctype,
			"module": MODULE,
			"standard": "No",
			"custom_format": 1,
			"print_format_type": "Jinja",
			"html": html,
			"css": CSS,
			"disabled": 0,
		}
		if frappe.db.exists("Print Format", name):
			doc = frappe.get_doc("Print Format", name)
			if all(doc.get(k) == v for k, v in values.items()):
				continue  # already up to date
			doc.update(values)
			doc.save(ignore_permissions=True)
			done.append(f"updated {name}")
		else:
			frappe.get_doc({"doctype": "Print Format", "name": name, **values}).insert(
				ignore_permissions=True
			)
			done.append(f"created {name}")
	for doctype, fmt in DEFAULT_FOR.items():
		if frappe.get_meta(doctype).default_print_format == fmt:
			continue
		frappe.make_property_setter(
			{
				"doctype": doctype,
				"doctype_or_field": "DocType",
				"property": "default_print_format",
				"value": fmt,
			},
			validate_fields_for_doctype=False,
		)
	frappe.db.commit()
	return done
