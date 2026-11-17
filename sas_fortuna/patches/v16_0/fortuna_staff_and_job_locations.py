"""Fortuna Impex sites, once: staff Users and engineers, and Job Locations everywhere.

  - Staff on the sheet (sites/<site>/private/sas_fortuna/fortuna_support_team.json) without a
    User get one (no welcome e-mail, no password), then their Helpdesk agent, teams, roles
    and Job Location. Someone who already has a User (same e-mail, or via Employee) keeps it.
    site_config "sas_fortuna_create_staff_users": 0 keeps user creation off on a site.
  - Job Locations: missing ones added and linked to their Company by invoice key; engineers
    and tickets without one get theirs (a ticket: its customer's address, else Kolkata).

All of it is setup/fortuna_impex.execute(), which after_migrate also runs; this patch makes
sure it runs on each site with user creation switched on. Other companies' sites: nothing.
"""

from sas_fortuna.setup import fortuna_impex as fi


def execute():
	import frappe

	if not fi.applies():
		return
	frappe.db.set_default(fi.CREATE_USERS_FLAG, "1")
	fi.execute()
