# SAS Fortuna

Custom Frappe app bundling SAS Fortuna's Client Scripts, Server Scripts, Web Forms, Portal Settings, Email Templates, and DocType customizations for version-controlled deployment.

## Overview

This app packages the customizations built on top of ERPNext v16 for Fortuna Impex Pvt Ltd into a single, installable, version-controlled unit. Instead of customizations living only inside the database (and being invisible to git), they're exported as fixtures and shipped as part of this app's source — so they can be reviewed, versioned, and deployed the same way to any ERPNext v16 instance.

## What's included

| Customization | How it's stored |
|---|---|
| **Custom Fields** | Customize Form additions on standard DocTypes (Customer, Supplier, etc.) — exported as fixtures |
| **Client Scripts** | Form/list-level JavaScript — `sas_fortuna/client_scripts/` (source) + exported as fixtures |
| **Server Scripts** | Backend automation and validation logic — `sas_fortuna/server_scripts/` (source) + exported as fixtures |
| **Web Forms** | Portal-facing forms — exported as fixtures |
| **Email Templates** | Notification templates — exported as fixtures |
| **Portal Settings** | Customer/supplier portal configuration — exported as fixtures |
| **Property Setters** | Field-level property overrides on standard DocTypes — exported as fixtures |
| **Custom DocTypes** | New DocTypes built directly into this app's module — shipped as controller files, not fixtures |

The full fixture list is configured in `sas_fortuna/hooks.py`.

## Installation

### On a bench with the app already present (dev)

```bash
bench --site [site-name] install-app sas_fortuna
bench --site [site-name] migrate
```

### On a new bench (client deployment)

```bash
bench get-app https://github.com/<your-org>/sas_fortuna.git
bench --site [client-site-name] install-app sas_fortuna
bench --site [client-site-name] migrate
```

`bench migrate` syncs any custom DocType schema and imports all fixtures (Custom Fields, Client/Server Scripts, Web Forms, Email Templates, Portal Settings, Property Setters).

## Syncing customizations from your site

Whenever customizations are added or changed via Customize Form, Client Script, Server Script, Web Form, Email Template, or Portal Settings in the Desk UI, re-export before committing:

```bash
bench --site [dev-site-name] export-fixtures --app sas_fortuna
```

Review the diff in `sas_fortuna/fixtures/` before committing, to catch unrelated or unexpected records pulled in from the site.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/sas_fortuna
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

## Requirements

- Frappe / ERPNext v16
- `frappe` (installed automatically as a dependency)

## License

MIT
