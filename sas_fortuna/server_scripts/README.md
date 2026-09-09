# server_scripts/

Same relationship as `../client_scripts/README.md`: the **Server Script**
DocType record (exported to `../fixtures/server_script.json`) is what
actually executes. Files here are a readable mirror for code review, not
an alternate loading mechanism.

## Before adding a new Server Script, ask: should this really be one?

Prefer a real Python module inside this app instead (e.g.
`sas_fortuna/sas_fortuna/utils/*.py`, wired up via a proper hook like
`doc_events`) when the logic:

- is more than a few lines,
- needs unit tests,
- is reused in more than one place, or
- implements non-trivial business rules.

Reach for a Frappe **Server Script** only for small, self-contained,
low-risk automation that genuinely benefits from being editable by an
admin without a deployment — and even then, add its exact name to
`CUSTOM_SERVER_SCRIPTS` in `hooks.py` the moment you create it, or it
will be silently skipped on export.

Never put secrets, API keys, or credentials in a Server Script — they end
up in the fixture JSON and therefore in Git history.
