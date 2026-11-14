"""Refresh Fortuna's own print formats once (14 Nov 2026).

  * The header now prints the selected Letter Head. Custom HTML formats must print it
    themselves, so once setup/fortuna_impex.py created the "Fortuna Impex" letter head,
    the prints lost their company name and address.
  * The repair quotation's payment line follows Payment Due Before (Fortuna: payment in
    full before dispatch, not before the repair starts).

Migrate only creates formats a site lacks, so existing ones are updated here. These
formats are app-owned: a Desk edit to them is replaced, as when they are re-created by hand.
"""

from sas_fortuna.support.print_formats import create_print_formats


def execute():
	create_print_formats(commit=False)
