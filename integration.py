"""
=============================================================================
INTEGRATION GUIDE — wiring quotation.py into the existing app
=============================================================================

1. store.py
-----------
No changes needed if your STORE already has the "quotations" key:

    STORE = {
        "products":   {},
        "quotations": {},      # ← must exist
        "_seeded":    False,
    }

If "quotations" is missing, add it now.


2. app.py — two lines to add
-----------------------------
Find the block where you register product_bp, e.g.:

    from product import product_bp
    app.register_blueprint(product_bp)

Add the quotation blueprint immediately after:

    from quotation import quotation_bp          # ← ADD
    app.register_blueprint(quotation_bp)        # ← ADD

Full example app.py (minimal):

    from flask import Flask
    from dashboard import dashboard_bp
    from product   import product_bp
    from quotation import quotation_bp          # ← NEW

    app = Flask(__name__)

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(quotation_bp)        # ← NEW

    if __name__ == "__main__":
        app.run(debug=True)


3. dashboard.py — optional nav link
-------------------------------------
If _nav() builds the top navigation bar, add a link to /quotation
alongside the existing /product link so users can reach it directly.

Example (inside _nav()):

    <a href="/quotation">Quotations</a>


4. URL map after integration
-----------------------------
  GET  /                        → dashboard
  GET  /product                 → product catalog
  GET  /product/add             → add product form
  POST /product/add             → save product
  GET  /product/view/<id>       → assembly BOM inspector
  GET  /product/delete/<id>     → delete product

  GET  /quotation               → quotation register (list)
  GET  /quotation/create        → new quotation form
  POST /quotation/create        → validate + expand + save → redirect to view
  GET  /quotation/view/<id>     → rendered quotation document


=============================================================================
DATA FLOW
=============================================================================

CREATE FORM (GET)
  ↓  User fills header fields + adds products via JS picker
  ↓
POST /quotation/create
  ├─ Validate: "to" field, ≥1 product, valid qty for each
  ├─ For each selected product:
  │     expand_product(pid, qty)
  │       assembly  → header row + recurse into children (qty × child.qty)
  │       leaf      → item row (price = base_price, total = price × qty)
  ├─ Compute grand_total = sum(item.total for item in line_items)
  ├─ Save to STORE["quotations"][uuid]
  └─ Redirect → GET /quotation/view/<id>

VIEW (GET /quotation/view/<id>)
  ├─ Read from STORE["quotations"][id]
  ├─ Render letterhead (static COMPANY_* constants)
  ├─ Render address + terms grid from saved fields
  ├─ Render line_items table
  │     header rows → blue tint, no S.No, no price, qty shown as annotation
  │     item rows   → S.No (increments only on items), price, total
  │     indent_cls  → "indent-1/2/3" on Description td, driven by row.depth
  └─ Render grand total + T&C footer


=============================================================================
EXPANSION ENGINE: expand_product()
=============================================================================

Signature:
  expand_product(product_id, qty, depth=0, visited=frozenset()) → list[dict]

Row dict schema:
  {
    "type":    "header" | "item",
    "name":    str,
    "part_no": str,
    "qty":     float,   # actual quantity at this level
    "unit":    str,
    "price":   float,   # 0.0 for headers
    "total":   float,   # 0.0 for headers
    "depth":   int,     # 0 = root, +1 per nesting level
  }

Example: KIRLOSKAR MAIN ELECTRIC PUMPSET × 2
  [header] KIRLOSKAR MAIN ELECTRIC PUMPSET  qty=2
  [item  ] DBxe 80/26 - 83                  qty=2×1=2   price=125000  total=250000
  [item  ] 75KW/100HP MOTOR                 qty=2×1=2   price=210000  total=420000
  [item  ] DB 80/26 FRAME                   qty=2×1=1*  total= 90000
  (* child qty=1 in seed; 2×1=2 → total=45000×2=90000)

  grand_total = 250000 + 420000 + 90000 = 760000

Cycle protection: visited frozenset prevents loops on corrupt data.
Missing products: silently skipped (expand_product returns []).
"""