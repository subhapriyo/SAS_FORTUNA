"""after_migrate: build the SAS Fortuna landing page (/desk/sas-fortuna).

The workspace file (sas_fortuna/workspace/sas_fortuna) holds a single block,
"SAS Fortuna Home". This script writes that block's HTML, CSS and JS from the
SECTIONS below, so the page is edited here, not in the browser.

Sections from other parts of the app (the Support Desk) are pulled in from
their own module, and a link is only shown when its DocType or Report exists
on the site.
"""

import html

import frappe

BLOCK = "SAS Fortuna Home"

# Each link: (label, kind, target, one-line description, icon)
# kind: "doctype" | "report" | "url"
SECTIONS = [
	{
		"title": "Customer & Supplier Onboarding",
		"intro": "Bring new partners in and keep track of who has been invited.",
		"links": [
			(
				"Supplier Onboarding",
				"doctype",
				"Supplier Onboarding",
				"Review and approve new supplier sign-ups.",
				"user-plus",
			),
			(
				"Customer Welcome Email Log",
				"doctype",
				"Customer Welcome Email Log",
				"Which customers got their welcome mail, and when.",
				"mail",
			),
			(
				"Supplier Welcome Email Log",
				"doctype",
				"Supplier Welcome Email Log",
				"The same, for suppliers.",
				"mail",
			),
		],
	},
	# "Portal Setup" section (Web Form, Portal Settings) hidden on 2026-11-12 at the
	# client's request -- not deleted, just left out of SECTIONS below.
]

ICONS = {
	"user-plus": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
	"mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
	"form": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
	"settings": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
	"wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z"/>',
	"pass": '<path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4z"/><path d="M13 5v14" stroke-dasharray="2 2"/>',
	"report": '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
	"clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
	"calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
	"users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
	"bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
	"tag": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
	"headset": '<path d="M3 14v-2a9 9 0 0 1 18 0v2"/><rect x="2" y="14" width="5" height="7" rx="2"/><rect x="17" y="14" width="5" height="7" rx="2"/>',
}

STYLE = """
:host { display: block; }
.sf { --sf-accent: var(--primary, #2563eb); color: var(--text-color); font-size: 14px; padding: 4px 0 24px; }
.sf-hero { border: 1px solid var(--border-color); border-radius: 12px; padding: 22px 24px;
  background: linear-gradient(120deg, color-mix(in srgb, var(--sf-accent) 9%, var(--card-bg)) 0%, var(--card-bg) 70%); }
.sf-hero h1 { margin: 0 0 4px; font-size: 22px; font-weight: 650; letter-spacing: -0.01em; color: var(--heading-color, var(--text-color)); }
.sf-hero p { margin: 0; color: var(--text-muted); max-width: 62ch; line-height: 1.5; }
.sf-section { margin-top: 28px; }
.sf-section h2 { margin: 0; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
.sf-section .sf-intro { margin: 4px 0 12px; color: var(--text-light, var(--text-muted)); line-height: 1.45; }
.sf-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.sf-card { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border: 1px solid var(--border-color);
  border-radius: 10px; background: var(--card-bg); color: inherit; text-decoration: none; min-width: 0;
  transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease; }
.sf-card:hover { border-color: color-mix(in srgb, var(--sf-accent) 45%, var(--border-color));
  box-shadow: 0 4px 14px rgba(0,0,0,.06); transform: translateY(-1px); text-decoration: none; }
.sf-card:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 2px; }
.sf-icon { flex: none; width: 36px; height: 36px; border-radius: 9px; display: grid; place-items: center;
  background: color-mix(in srgb, var(--sf-accent) 12%, transparent); color: var(--sf-accent); }
.sf-icon svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.sf-text { min-width: 0; }
.sf-title { display: block; font-weight: 600; color: var(--heading-color, var(--text-color)); line-height: 1.3; }
.sf-desc { display: block; margin-top: 3px; color: var(--text-muted); line-height: 1.4; font-size: 13px; }
@media (max-width: 600px) { .sf-hero { padding: 18px; } .sf-hero h1 { font-size: 19px; } .sf-grid { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .sf-card { transition: none; } .sf-card:hover { transform: none; } }
"""

# Desk routes are worked out in the browser, so they follow whatever this
# Frappe version uses (/desk/<module>/<doctype>/ on v16).
SCRIPT = """
root_element.querySelectorAll("a[data-kind]").forEach((a) => {
	const kind = a.dataset.kind, name = a.dataset.name;
	if (kind === "url") return;
	let route = null;
	try {
		route = frappe.utils.generate_route({ type: kind, name: name, is_query_report: kind === "report" });
	} catch (e) {}
	if (route) a.setAttribute("href", route);
	a.addEventListener("click", (e) => {
		if (e.ctrlKey || e.metaKey || e.shiftKey) return;
		e.preventDefault();
		kind === "report" ? frappe.set_route("query-report", name) : frappe.set_route("List", name);
	});
});
"""


def execute():
	sections = SECTIONS + _optional_sections()
	html_body = _render(sections)
	if frappe.db.exists("Custom HTML Block", BLOCK):
		frappe.db.set_value(
			"Custom HTML Block", BLOCK, {"html": html_body, "style": STYLE, "script": SCRIPT, "private": 0}
		)
	else:
		frappe.get_doc(
			{
				"doctype": "Custom HTML Block",
				"__newname": BLOCK,
				"html": html_body,
				"style": STYLE,
				"script": SCRIPT,
				"private": 0,
			}
		).insert(ignore_permissions=True)


def _optional_sections():
	try:
		from sas_fortuna.setup.support_desk import LANDING_SECTIONS
	except ImportError:
		return []
	return LANDING_SECTIONS


def _exists(kind, target):
	if kind == "doctype":
		return frappe.db.exists("DocType", target)
	if kind == "report":
		return frappe.db.exists("Report", target)
	return True


def _render(sections):
	esc = html.escape
	out = [
		'<div class="sf">',
		'<header class="sf-hero"><h1>SAS Fortuna</h1>',
		"<p>Fortuna Impex's own tools in ERPNext. Pick a tile to open it.</p></header>",
	]
	for section in sections:
		links = [link for link in section["links"] if _exists(link[1], link[2])]
		if not links:
			continue
		out.append(f'<section class="sf-section"><h2>{esc(section["title"])}</h2>')
		if section.get("intro"):
			out.append(f'<p class="sf-intro">{esc(section["intro"])}</p>')
		out.append('<div class="sf-grid">')
		for label, kind, target, desc, icon in links:
			href = target if kind == "url" else "#"
			out.append(
				f'<a class="sf-card" href="{esc(href)}" data-kind="{kind}" data-name="{esc(target)}">'
				f'<span class="sf-icon"><svg viewBox="0 0 24 24" aria-hidden="true">{ICONS.get(icon, "")}</svg></span>'
				f'<span class="sf-text"><span class="sf-title">{esc(label)}</span>'
				f'<span class="sf-desc">{esc(desc)}</span></span></a>'
			)
		out.append("</div></section>")
	out.append("</div>")
	return "\n".join(out)
