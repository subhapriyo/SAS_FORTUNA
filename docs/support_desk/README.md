# Support Desk, Repair & AMC — files in sas_fortuna

Scope: Fortuna Support Desk, Repair & AMC v1.2 (C1–C4, D1–D9, E1–E2, F1–F9, P1, N1–N10).
Guide: *Fortuna_Support_Repair_AMC_Implementation_Guide* (md / pdf).
Tested with: helpdesk 1.22.2 (develop) @ 794c7b089 (2026-10-06).

## Live code (already in place)

| File | Phase | What it does |
|---|---|---|
| `sas_fortuna/support/utils.py` | 1 | Settings, serial → invoice lookup, Warranty / AMC / Paid rule |
| `sas_fortuna/support/customer_sync.py` | 1 | ERPNext Customer ↔ HD Customer, Contact links |
| `sas_fortuna/support/sales.py` | 2 | Stamp invoice / customer / warranty end on serials at sale |
| `sas_fortuna/support/hd_ticket.py` | 2 | Ticket routing, serial details, resolution notes, last service date |
| `sas_fortuna/support/repair.py` | 3–5 | Repair Order buttons + Stock / SO / SI / PE / DN hooks |
| `sas_fortuna/support/amc.py` | 6 | Covered Items copy, AMC activation, renew, end |
| `sas_fortuna/support/tasks.py` | 6 | Daily jobs: AMC enquiries, overdue loaners, SIM orders |
| `sas_fortuna/support/orders.py` | 8 | Helpdesk ticket from Sales Order |
| `sas_fortuna/support/portal.py` | 8 | Portal customer, accept quotation |
| `sas_fortuna/www/repairs.py`, `repairs.html` | 8 | `/repairs` portal page |
| `sas_fortuna/public/js/hd_ticket.js` | 3 | Desk HD Ticket: serial filter, Create → Repair Order |
| `sas_fortuna/public/js/sales_order.js` | 6, 8 | Renew / End AMC, Create → Helpdesk Ticket |

Nothing runs until it is wired in `hooks.py` — see `hooks_to_merge.py` and add each block **in its phase**.

## Staged here (copy after creating the DocType in the UI)

| From `docs/support_desk/doctype_code/` | Copy to `sas_fortuna/sas_fortuna/doctype/` after |
|---|---|
| `repair_order/repair_order.py`, `.js` | creating DocType **Repair Order** (Phase 3) — replace the generated files |
| `returnable_gate_pass/returnable_gate_pass.py`, `.js` | creating DocType **Returnable Gate Pass** (Phase 5) — replace the generated files |

```bash
cd /workspace/development/frappe-bench/apps/sas_fortuna
cp docs/support_desk/doctype_code/repair_order/* sas_fortuna/sas_fortuna/doctype/repair_order/
cp docs/support_desk/doctype_code/returnable_gate_pass/* sas_fortuna/sas_fortuna/doctype/returnable_gate_pass/
```

## Paste into the UI

| File | Where |
|---|---|
| `reports/*.sql` | Report → New → Query Report (Module: SAS Fortuna, Is Standard: Yes) |
| `print_formats/*.html` | Print Format → New → Custom Format, Jinja (Module: SAS Fortuna) |

Note: `fortuna_erp` already references a print format **"Fortuna - AMC Invoice"**. Check whether it exists before creating "Fortuna AMC Invoice" (F9); adding the annexure block to the existing one may be enough.
