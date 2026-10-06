"""Hooks that run automatically on `bench migrate` (see hooks.py after_migrate).

These are not Frappe patches: they run on every migrate, so each one must be idempotent.
One-off tools run by hand live in sas_fortuna/scripts/ instead.
"""
