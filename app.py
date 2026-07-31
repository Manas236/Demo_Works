"""
app.py — The Orchestrator
=========================
Entry point for the Quotation Management System.
Registers all Blueprints and defines global error handling.
"""

import os

from flask import Flask, redirect, url_for
from dashboard import dashboard_bp
from extractor import extractor_bp
from product import product_bp   # Phase 1: product management
from quotation import quotation_bp  # Phase 2: quotation generation
from address import address_bp   # Standalone address book

import db                        # MySQL persistence (config from .env)
from store import STORE

# ── App Initialization ────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "qms-demo-secret-2024")


# ── Persistence ───────────────────────────────────────────────────────────────
# Connect, create the schema if absent, and hydrate STORE from MySQL. When the
# reloader is active this runs in both the watcher and the worker process;
# everything involved is idempotent, so that is harmless.
def _boot_persistence() -> None:
    live = db.init()
    if live:
        n = db.load_into(STORE)
        print(f"  * {db.status()} - {n} record(s) loaded")
    else:
        print(f"  * WARNING: {db.status()}")
        print("  *          data will be lost on restart. Check .env / MySQL.")


_boot_persistence()


@app.teardown_request
def _persist(exc):
    """
    Mirror STORE back to MySQL after every request.

    Blueprints mutate nested dicts in place, so there is no write to intercept —
    db.sync() diffs the whole store and writes only what actually changed.
    teardown_request is used (over after_request) because it runs even when a
    view raised, so a half-finished mutation is still saved rather than lost.
    """
    db.sync(STORE)


# ── Blueprint Registration ────────────────────────────────────────────────────
# Each Blueprint encapsulates a self-contained feature module.
# Registering here keeps app.py thin — it only wires, never implements.
app.register_blueprint(dashboard_bp)           # Mounted at /
app.register_blueprint(extractor_bp)           # Mounted at /extractor
app.register_blueprint(product_bp)            # Mounted at /product
app.register_blueprint(quotation_bp)          # Mounted at /quotation
app.register_blueprint(address_bp)            # Mounted at /address


# ── Global Error Handling ─────────────────────────────────────────────────────
# Catches any unmatched route and silently redirects to the dashboard.
# This ensures the demo never surfaces a raw 404 page to stakeholders.
@app.errorhandler(404)
def page_not_found(error):
    """Redirect unknown routes to the main dashboard index."""
    return redirect(url_for("dashboard.index")), 302


@app.errorhandler(500)
def internal_error(error):
    """Redirect server errors to dashboard; log in production instead."""
    return redirect(url_for("dashboard.index")), 302


# ── Dev Server ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # debug=True enables auto-reload; NEVER ship this flag to production.
    # reloader_type="stat" avoids the watchdog reloader, which recursively
    # watches every sys.path dir (incl. site-packages) and reload-storms when
    # antivirus/indexers touch file attributes there.
    app.run(debug=True, port=5000, reloader_type="stat")