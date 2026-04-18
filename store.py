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

⚠  In-memory only — all data is lost on server restart.
   Swap STORE reads/writes for a DB layer when moving to production.
"""

STORE: dict = {
    "products":   {},   # keyed by UUID string → product dict
    "quotations": {},   # keyed by UUID string → quotation dict
    "_seeded":    False,  # flipped to True after ensure_demo_products() runs once
}