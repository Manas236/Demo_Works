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
    "merged_ras":   {},   # keyed by UUID string → merged RA document (CC-2 C3): ONE issued supply bill + ONE issued installation bill from the same revision chain, stacked onto one sheet under ONE minted tax invoice number. Its OWN collection — a separate document type, the same relationship as Draft PO → PO. ⚠ It holds NO claims of its own: copying claim rows in would make ra.claimed_by_line() count the same quantity twice, and every over-claim guard downstream would then be wrong in the direction that lets money through
    "measurements": {},   # keyed by UUID string → measurement sheet raised against a BOQ revision (CC-2 C2). Its OWN collection for §1.3's reason — one BOQ accumulates many sheets over a project's life, and an approved sheet's quantity is the ceiling for RA-Installation
    "delivery_challans": {},  # keyed by UUID string → goods-movement note against a BOQ. Its OWN collection for §1.3's reason — one BOQ accumulates many challans over a project's life
    "projects":     {},   # keyed by UUID string → project record (the commercial engagement BOQs are grouped under)
    "charges":      {},   # keyed by UUID string → employee/misc expense record (travel, wages, consumables — not in any BOQ)
    "employees":    {},   # keyed by UUID string → employee master record: details and salary (CC-2 C4). Its OWN collection — a person is not a charge, and the charges ledger has never had an employee record behind it
    "attendance":   {},   # keyed by UUID string → one employee, one site, one day (CC-2 C5). Its OWN collection, never a list on the employee — one person accumulates a record per working day for as long as they are employed, which is CLIENT_CHANGES.md §1.3's rule exactly
    "attachments":  {},   # keyed by UUID string → attachment METADATA (CC-2 B8). ⚠ The BYTES ARE NOT HERE and must never be — db._blob() writes them through json.dumps(default=str), which reloads a repr STRING with no exception raised. The file is on disk under attachment.root(); this row holds its relative path, size, sniffed mime type and the record it belongs to. Its OWN collection per CLIENT_CHANGES.md §1.3 — one charge accumulates several files
    "addresses":    {},   # keyed by UUID string → address dict (address book)
    "users":        {},   # keyed by UUID string → user account (auth.py). Its OWN collection — never a list on a role, per CLIENT_CHANGES.md §1.3
    "roles":        {},   # keyed by UUID string → role: a named bundle of permission strings. Separate from users for the same §1.3 reason: one role is held by many users
    "settings":     {},   # single record under the key "company" → branding overrides
    "_seeded":      False,  # flipped to True after ensure_demo_products() runs once
    "_addr_seeded": False,  # flipped to True after ensure_demo_addresses() runs once
    "_spec_seeded": False,  # flipped to True after ensure_demo_specs() runs once
    "_boq_seeded":  False,  # flipped to True after ensure_demo_boq() runs once
    "_settings_seeded": False,  # flipped to True after ensure_demo_settings() runs once
}