# client_scripts/

Frappe does **not** load JavaScript from this folder automatically — Client
Script is a DocType, and the record stored in the database (exported to
`../fixtures/client_script.json` on `bench export-fixtures`) is what
actually runs on the site.

This folder exists purely so the JS is readable and diffable in Git
without opening a fixture JSON. **The fixture is the single source of
truth for what's deployed.**

Workflow:

1. Write/edit the Client Script in the Desk UI (Customize Form area
   won't do it — use the **Client Script** doctype directly), naming it
   with the `SAS Fortuna - ` prefix so it's caught by the fixture filter
   in `hooks.py`.
2. Copy the final script text into a same-named `.js` file here, e.g.
   `customer/sas_fortuna_customer_validation.js`, purely for code review
   and history.
3. Run `bench --site <site> export-fixtures --app sas_fortuna` — this is
   the step that actually updates what gets deployed.
4. Commit both the fixture change and the mirrored `.js` file together.

If the two ever disagree, the fixture wins on deploy — treat a mismatch
as a bug to fix, not an ambiguity to resolve.
