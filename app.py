"""
app.py — The Orchestrator
=========================
Entry point for the Quotation Management System.
Registers all Blueprints and defines global error handling.
"""

import os

from flask import Flask, redirect, url_for
import dashboard                  # too_large_page() for the 413 handler
from dashboard import dashboard_bp
from extractor import extractor_bp
from product import product_bp   # Phase 1: product management
from quotation import quotation_bp  # Phase 2: quotation generation
from proforma import proforma_bp  # Phase 3: proforma invoice (derived from a quotation)
from invoice import invoice_bp   # Phase 4: GST tax invoice (derived from a proforma)
from purchase import purchase_bp  # Buy side: purchase orders. A SEPARATE pipeline —
                                  # it never links to a proforma or a tax invoice.
from spec import spec_bp         # Specification library: the vocabulary a BOQ is
                                 # written in. Clauses with SIZED VARIANTS — not a
                                 # replacement for product.py, which serves the
                                 # quotation chain and is untouched.
from boq import boq_bp           # BOQ: the priced schedule for a project. Head of a
                                 # SECOND sell-side chain — BOQ -> RA bills — parallel
                                 # to quotation -> proforma -> tax invoice, not part of it.
from ra import ra_bp             # RA bills: progressive claims against a BOQ
                                  # revision. Headed TAX INVOICE per DOMAIN.md §4.
from receipt import receipt_bp   # Receipts: money RECEIVED against an RA bill.
                                 # Its own collection, never a list on the bill
                                 # or the BOQ. It imports ra.py; ra.py links
                                 # back with url_for only.
from client import client_bp     # Client-wise segregation and party edits
from po_draft import po_draft_bp # Draft PO from BOQ
from address import address_bp   # Standalone address book
from settings import settings_bp, ensure_demo_settings, load_saved  # Company identity & bank details

import branding as B             # Runtime overrides are pushed onto this module
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

    # The specimen company identity. Seeded here rather than from a route
    # because the letterhead is rendered by the FIRST request and there is no
    # route guaranteed to run before it. Only ever fills a gap — an identity
    # just loaded out of MySQL is left alone.
    ensure_demo_settings()

    # Company identity and bank details saved on /settings override the defaults
    # in branding.py. This must run AFTER load_into and after the seeder, and
    # before the first request renders a letterhead. Idempotent, so the reloader
    # running it in both processes is harmless.
    B.apply_settings(load_saved())


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
app.register_blueprint(proforma_bp)           # Mounted at /proforma
app.register_blueprint(invoice_bp)            # Mounted at /invoice
app.register_blueprint(purchase_bp)           # Mounted at /purchase  (buy side)
app.register_blueprint(spec_bp)               # Mounted at /spec
app.register_blueprint(boq_bp)                # Mounted at /boq
app.register_blueprint(ra_bp)                 # Mounted at /ra   — REQUIRED by
                                              # /boq/view, which builds
                                              # url_for("ra.view_ra") for every
                                              # RA bill against the BOQ and
                                              # 500s without this.
app.register_blueprint(receipt_bp)            # Mounted at /receipt — REQUIRED by
                                              # /ra/view, which builds
                                              # url_for("receipt.new_receipt")
                                              # on every bill and 500s without it.
app.register_blueprint(po_draft_bp)           # Mounted at /po (Draft PO from BOQ)
app.register_blueprint(client_bp)             # Mounted at /client
app.register_blueprint(address_bp)            # Mounted at /address
app.register_blueprint(settings_bp)           # Mounted at /settings


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


@app.errorhandler(413)
def payload_too_large(error):
    """
    A POST past MAX_FORM_MEMORY_SIZE (500,000 bytes, Flask's default).

    Deliberately NOT a redirect like the two above. A 404 is a mistyped URL and
    nobody's work; a 413 is a form somebody spent an afternoon filling in, and
    bouncing them to the dashboard would look exactly like the app discarding it
    without comment. Werkzeug rejects the body before the form is parsed, so
    there is genuinely nothing left to re-render — the page says so, and points
    at the Back button, which may still hold it.

    This is a **backstop**, not the defence. The line cap in
    `boq._clean_lines()` is what keeps a real BOQ from ever reaching it; this
    catches the paths that bypass the form, and the case of 600 legal lines that
    happen to serialise past the limit.

    The status stays 413 — a 302 would tell the browser and the logs that the
    request succeeded.
    """
    return dashboard.too_large_page(), 413


# ── Dev Server ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # debug=True enables auto-reload; NEVER ship this flag to production.
    # reloader_type="stat" avoids the watchdog reloader, which recursively
    # watches every sys.path dir (incl. site-packages) and reload-storms when
    # antivirus/indexers touch file attributes there.
    app.run(debug=True, port=5000, reloader_type="stat")