"""
store.py — Shared In-Memory Store
===================================
Single source of truth for all runtime data across blueprints.

Each blueprint imports STORE directly from this module.
Because Python caches module imports, every import of `store.py` gets
the *same* dictionary object — changes made in product.py are immediately
visible in quotation.py, extractor.py, etc.

Structure (grows as modules are added):
  STORE = {
      "products": { "<uuid>": { ...product fields... } },
      # future keys: "assemblies", "quotations", ...
  }

Persistence
-----------
STORE is still a plain dict and every blueprint still mutates it directly —
that contract has not changed. db.py mirrors it to MySQL: app.py loads the
tables into these dicts at startup and syncs changed records back after each
request. Nothing here needs to know about that.

If MySQL is unreachable (or DB_ENABLED=false in .env) the app falls back to
this dict alone and prints a warning at startup — behaviour identical to how
it worked before, data lost on restart.
"""

STORE: dict = {
    "products":     {},   # keyed by UUID string → product dict
    "quotations":   {},   # keyed by UUID string → quotation dict
    "proformas":    {},   # keyed by UUID string → proforma invoice dict (derived from a quotation)
    "invoices":     {},   # keyed by UUID string → GST tax invoice dict (derived from a proforma)
    "purchases":    {},   # keyed by UUID string → purchase order dict (BUY side — we are the buyer)
    "purchase_orders":{}, # keyed by UUID string → Draft PO from BOQ
    "specs":        {},   # keyed by UUID string → specification library entry (clause + sized variants)
    "boqs":         {},   # keyed by UUID string → bill of quantities (head of the BOQ → RA chain)
    "ra_bills":     {},   # keyed by UUID string → Running Account bill (progressive claim against a BOQ revision, carries tax block per DOMAIN.md §4)
    "receipts":     {},   # keyed by UUID string → payment RECEIVED against one RA bill. Its OWN collection, never a list on the bill or the BOQ — CLIENT_CHANGES.md §1.3
    "delivery_challans": {},  # keyed by UUID string → goods-movement note against a BOQ. Its OWN collection for §1.3's reason — one BOQ accumulates many challans over a project's life
    "projects":     {},   # keyed by UUID string → project record (the commercial engagement BOQs are grouped under)
    "addresses":    {},   # keyed by UUID string → address dict (address book)
    "settings":     {},   # single record under the key "company" → branding overrides
    "_seeded":      False,  # flipped to True after ensure_demo_products() runs once
    "_addr_seeded": False,  # flipped to True after ensure_demo_addresses() runs once
    "_spec_seeded": False,  # flipped to True after ensure_demo_specs() runs once
    "_boq_seeded":  False,  # flipped to True after ensure_demo_boq() runs once
    "_settings_seeded": False,  # flipped to True after ensure_demo_settings() runs once
}