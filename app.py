"""
app.py — The Orchestrator
=========================
Entry point for the Quotation Management System.
Registers all Blueprints and defines global error handling.
"""

from flask import Flask, redirect, url_for
from dashboard import dashboard_bp
from extractor import extractor_bp
from product import product_bp   # Phase 1: product management
from quotation import quotation_bp  # Phase 2: quotation generation

# ── App Initialization ────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "qms-demo-secret-2024"  # Required for session/flash; swap in prod


# ── Blueprint Registration ────────────────────────────────────────────────────
# Each Blueprint encapsulates a self-contained feature module.
# Registering here keeps app.py thin — it only wires, never implements.
app.register_blueprint(dashboard_bp)           # Mounted at /
app.register_blueprint(extractor_bp)           # Mounted at /extractor
app.register_blueprint(product_bp)            # Mounted at /product
app.register_blueprint(quotation_bp)          # Mounted at /quotation


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
    app.run(debug=True, port=5000)