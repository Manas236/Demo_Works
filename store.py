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
    "addresses":    {},   # keyed by UUID string → address dict (address book)
    "_seeded":      False,  # flipped to True after ensure_demo_products() runs once
    "_addr_seeded": False,  # flipped to True after ensure_demo_addresses() runs once
}