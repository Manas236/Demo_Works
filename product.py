"""
product.py — Product Management Module
=======================================
Blueprint : product_bp
Mounted at : /product  (registered in app.py)

Phase 2 additions on top of Phase 1:
  - Demo product seeding (ensure_demo_products)
  - Extended product model: type + children
  - Assembly child editor with vanilla JS
  - Circular dependency protection (can_add_child — DFS)
  - Enforced delete integrity (can_delete_product now blocks if used in assembly)
  - Updated list UI: type badges + child count

Phase 2.1 additions:
  - /product/view/<id>  — recursive BOM tree inspector
  - _render_tree()      — depth-aware recursive renderer with cycle/missing guards
  - VIEW_STYLES         — tree node CSS layered on top of PRODUCT_STYLES
  - "View" button in catalog list for assembly rows

Backward compatibility:
  - All new fields (type, children) use .get() with safe defaults everywhere
  - Existing Phase 1 routes and their signatures are unchanged
"""

import uuid
from flask import Blueprint, render_template_string, request, redirect, url_for

# ── Shared imports ────────────────────────────────────────────────────────────
from dashboard import BASE_STYLES, _nav
from store import STORE

# ── Blueprint ─────────────────────────────────────────────────────────────────
product_bp = Blueprint("product", __name__, url_prefix="/product")


# =============================================================================
# DEMO SEED DATA
# =============================================================================

# Fixed UUIDs so assembly->child references are stable across the seeding call.
_S = {
    "kirloskar": "a1000001-beef-4000-8000-000000000001",
    "dbxe":      "a1000002-beef-4000-8000-000000000002",
    "motor75":   "a1000003-beef-4000-8000-000000000003",
    "db_frame":  "a1000004-beef-4000-8000-000000000004",
    "kfe":       "a1000005-beef-4000-8000-000000000005",
    "radiator":  "a1000006-beef-4000-8000-000000000006",
    "lub_oil":   "a1000007-beef-4000-8000-000000000007",
    "battery":   "a1000008-beef-4000-8000-000000000008",
    "fuel_tank": "a1000009-beef-4000-8000-000000000009",
    "jockey":    "a100000a-beef-4000-8000-00000000000a",
}


def ensure_demo_products() -> None:
    """
    Seeds STORE["products"] with 10 realistic demo products on first call.
    Subsequent calls are no-ops — guarded by STORE["_seeded"].

    Call this at the top of any route that reads from the product catalog,
    so the list is never empty on first visit without a manual add.

    Seed structure:
      Assemblies : KIRLOSKAR MAIN ELECTRIC PUMPSET, KFE ENGINE, JOCKEY PUMPSET
      Support    : DBxe 80/26-83, 75KW/100HP MOTOR, DB 80/26 FRAME
      Standalone : RADIATOR COOLANT, LUB OIL, BATTERY 180 AMP, FUEL TANK 200 LTR
    """
    if STORE["_seeded"]:
        return

    # Standalone products (leaf nodes — no children)
    _seed(_S["radiator"],  "RADIATOR COOLANT",      "RAD-001", "L",    8_500,
          "Standard coolant for diesel engines. 10L fill capacity.",
          "standalone", [])
    _seed(_S["lub_oil"],   "LUB OIL",               "OIL-002", "L",    3_200,
          "15W-40 mineral lubricant. Recommended change: 250 hrs.",
          "standalone", [])
    _seed(_S["battery"],   "BATTERY 180 AMP",        "BAT-003", "pcs", 12_500,
          "12V / 180 Ah sealed lead-acid. Maintenance-free.",
          "standalone", [])
    _seed(_S["fuel_tank"], "FUEL TANK 200 LTR",      "FT-004",  "pcs", 18_000,
          "Mild steel fuel tank, 200L capacity, coated interior.",
          "standalone", [])

    # Support items (sub-components; not sold standalone)
    _seed(_S["dbxe"],     "DBxe 80/26 - 83",         "DBX-010", "set",  125_000,
          "Horizontal multi-stage centrifugal pump. Flow: 80 m3/hr, Head: 26m.",
          "support", [])
    _seed(_S["motor75"],  "75KW/100HP MOTOR",          "MOT-011", "pcs", 210_000,
          "TEFC squirrel cage induction motor. 75kW, 4-pole, 415V/50Hz.",
          "support", [])
    _seed(_S["db_frame"], "DB 80/26 FRAME",            "FRM-012", "pcs",  45_000,
          "Fabricated MS base frame for DB 80/26 pump + motor set.",
          "support", [])

    # Assemblies (have children; leaf products must be seeded first)
    _seed(_S["kirloskar"], "KIRLOSKAR MAIN ELECTRIC PUMPSET", "KIR-100", "set", 850_000,
          "Complete Kirloskar electric pumpset. Pump, motor, and base frame. Factory tested.",
          "assembly", [
              {"product_id": _S["dbxe"],     "qty": 1},
              {"product_id": _S["motor75"],  "qty": 1},
              {"product_id": _S["db_frame"], "qty": 1},
          ])
    _seed(_S["kfe"], "KFE ENGINE", "KFE-200", "set", 380_000,
          "Diesel engine package. Kirloskar diesel, radiator-cooled, electric start.",
          "assembly", [
              {"product_id": _S["radiator"],  "qty": 1},
              {"product_id": _S["lub_oil"],   "qty": 5},
              {"product_id": _S["fuel_tank"], "qty": 1},
          ])
    _seed(_S["jockey"], "JOCKEY PUMPSET", "JOC-300", "set", 95_000,
          "Pressure-maintenance jockey pump. Auto start/stop on pressure drop.",
          "assembly", [
              {"product_id": _S["battery"], "qty": 1},
          ])

    STORE["_seeded"] = True


def _seed(pid, name, part_no, unit, base_price, description, ptype, children):
    """Write one demo product; skips silently if that ID already exists."""
    if pid not in STORE["products"]:
        STORE["products"][pid] = {
            "id":          pid,
            "name":        name,
            "part_no":     part_no,
            "unit":        unit,
            "base_price":  float(base_price),
            "description": description,
            "type":        ptype,
            "children":    children,
        }


# =============================================================================
# GRAPH / INTEGRITY HELPERS
# =============================================================================

def can_add_child(parent_id: str, child_id: str) -> tuple[bool, str | None]:
    """
    Returns (True, None) if adding child_id as a child of parent_id is safe.
    Returns (False, reason) if self-reference or a cycle would result.

    Algorithm: DFS from child_id through the existing product graph.
    If parent_id is reachable from child_id, the proposed edge creates a cycle.
    """
    if parent_id == child_id:
        return False, "A product cannot reference itself as a component."

    visited: set[str] = set()
    stack:   list[str] = [child_id]

    while stack:
        node = stack.pop()
        if node == parent_id:
            return False, "Adding this component would create a circular dependency."
        if node in visited:
            continue
        visited.add(node)
        p = STORE["products"].get(node)
        if p:
            for c in p.get("children", []):
                stack.append(c["product_id"])

    return True, None


def can_delete_product(product_id: str) -> tuple[bool, str | None]:
    """
    Blocks deletion if the product appears as a child in any assembly.
    Returns (True, None) if safe.
    Returns (False, reason) with the blocking assembly name.
    """
    for pid, p in STORE["products"].items():
        if pid == product_id:
            continue
        for child in p.get("children", []):
            if child["product_id"] == product_id:
                return False, f"Cannot delete: product is used in assembly '{p['name']}'"

    return True, None


# =============================================================================
# CSS — product-module-specific (layered on top of BASE_STYLES)
# =============================================================================

PRODUCT_STYLES = """
<style>
  /* ── Page header ───────────────────────────────────────────────────── */
  .page-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2rem;
    flex-wrap: wrap;
    gap: 1rem;
  }
  .page-top h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -.4px; }
  .page-top h1 span { color: var(--brand); }

  /* ── Empty state ───────────────────────────────────────────────────── */
  .empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--muted);
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
  }
  .empty-state p { margin-top: .5rem; font-size: .92rem; }

  /* ── Table ─────────────────────────────────────────────────────────── */
  .table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
  }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  thead { background: var(--bg); border-bottom: 1px solid var(--border); }
  th {
    padding: .85rem 1.25rem;
    text-align: left;
    font-size: .75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--muted);
  }
  td {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    vertical-align: middle;
  }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr { transition: background .15s; }
  tbody tr:hover { background: #f8fafc; }

  .td-name   { font-weight: 600; }
  .td-partno { font-family: 'SFMono-Regular', Consolas, monospace; font-size: .82rem; color: var(--muted); }
  .td-price  { font-weight: 600; color: var(--brand); }
  .td-unit   { color: var(--muted); font-size: .85rem; }

  /* ── Type badges ───────────────────────────────────────────────────── */
  .badge {
    display: inline-block;
    font-size: .68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    padding: .2rem .55rem;
    border-radius: 20px;
    white-space: nowrap;
  }
  .badge-assembly   { background: #dbeafe; color: #1d4ed8; }
  .badge-support    { background: #fef3c7; color: #92400e; }
  .badge-standalone { background: #f0fdf4; color: #166534; }

  .children-count { font-size: .78rem; color: var(--muted); margin-top: .2rem; }

  /* ── Action buttons ────────────────────────────────────────────────── */
  .btn-delete {
    font-family: var(--font);
    font-size: .78rem;
    font-weight: 600;
    color: #ef4444;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 6px;
    padding: .3rem .75rem;
    cursor: pointer;
    transition: background .15s, border-color .15s;
    text-decoration: none;
    display: inline-block;
  }
  .btn-delete:hover { background: #fee2e2; border-color: #ef4444; }

  /* ── Form card ─────────────────────────────────────────────────────── */
  .form-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem 2.25rem;
    box-shadow: var(--shadow-sm);
    max-width: 680px;
  }
  .form-card h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 1.75rem; letter-spacing: -.3px; }

  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.1rem; }
  .form-group { display: flex; flex-direction: column; gap: .4rem; }
  .form-group.full { grid-column: 1 / -1; }

  label {
    font-size: .78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--muted);
  }
  input[type="text"],
  input[type="number"],
  textarea,
  select {
    font-family: var(--font);
    font-size: .92rem;
    color: var(--text);
    background: var(--bg);
    border: 1.5px solid var(--border);
    border-radius: 8px;
    padding: .6rem .9rem;
    width: 100%;
    transition: border-color .15s, box-shadow .15s;
    outline: none;
  }
  input:focus, textarea:focus, select:focus {
    border-color: var(--brand);
    box-shadow: 0 0 0 3px rgba(79,70,229,.12);
    background: #fff;
  }
  textarea { resize: vertical; min-height: 90px; }
  .form-actions { display: flex; gap: .75rem; margin-top: 1.75rem; align-items: center; }

  /* ── Assembly / BOM section ────────────────────────────────────────── */
  .assembly-section {
    grid-column: 1 / -1;
    border: 1.5px solid var(--brand-lt);
    border-radius: 10px;
    padding: 1.25rem 1.4rem;
    background: #f5f3ff;
    margin-top: .25rem;
  }
  .assembly-section-title {
    font-size: .8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--brand);
    margin-bottom: 1rem;
  }
  #children-container { display: flex; flex-direction: column; gap: .6rem; }

  .child-row {
    display: grid;
    grid-template-columns: 1fr 90px 36px;
    gap: .5rem;
    align-items: center;
  }
  .child-row select,
  .child-row input[type="number"] { margin: 0; font-size: .88rem; padding: .5rem .75rem; }

  .btn-remove-child {
    font-family: var(--font);
    font-size: 1rem;
    font-weight: 700;
    color: #ef4444;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 6px;
    cursor: pointer;
    height: 36px;
    width: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background .15s;
    flex-shrink: 0;
  }
  .btn-remove-child:hover { background: #fee2e2; }

  .btn-add-child {
    font-family: var(--font);
    font-size: .8rem;
    font-weight: 600;
    color: var(--brand);
    background: var(--brand-lt);
    border: 1px dashed var(--brand);
    border-radius: 6px;
    padding: .45rem 1rem;
    cursor: pointer;
    margin-top: .75rem;
    transition: background .15s;
  }
  .btn-add-child:hover { background: #c7d2fe; }

  .no-products-hint { font-size: .85rem; color: var(--muted); font-style: italic; }

  /* ── Alert ─────────────────────────────────────────────────────────── */
  .alert {
    padding: .85rem 1.2rem;
    border-radius: 8px;
    font-size: .88rem;
    font-weight: 500;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: .5rem;
  }
  .alert-success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
  .alert-error   { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

  /* ── Responsive ────────────────────────────────────────────────────── */
  @media (max-width: 700px) {
    .form-grid { grid-template-columns: 1fr; }
    .form-group.full, .assembly-section { grid-column: 1; }
    th, td { padding: .75rem .9rem; }
    .col-desc, .col-children { display: none; }
    .child-row { grid-template-columns: 1fr 70px 32px; }
  }
</style>
"""


# =============================================================================
# CSS — view page (BOM tree inspector), layered on top of PRODUCT_STYLES
# =============================================================================

VIEW_STYLES = """
<style>
  /* ── Product detail header card ─────────────────────────────────────── */
  .detail-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem 2.25rem;
    box-shadow: var(--shadow-sm);
    margin-bottom: 2rem;
  }
  .detail-card h2 {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -.3px;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: .75rem;
    flex-wrap: wrap;
  }
  .detail-meta {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 1rem 2rem;
    font-size: .88rem;
    color: var(--muted);
  }
  .detail-meta-item strong {
    display: block;
    font-size: .72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--muted);
    margin-bottom: .25rem;
  }
  .detail-meta-item span { color: var(--text); font-weight: 500; }
  .detail-meta-item span.price { color: var(--brand); font-weight: 700; }
  .detail-desc {
    margin-top: 1.25rem;
    padding-top: 1.25rem;
    border-top: 1px solid var(--border);
    font-size: .9rem;
    color: var(--muted);
    line-height: 1.65;
    white-space: pre-wrap;
  }

  /* ── BOM section wrapper ────────────────────────────────────────────── */
  .bom-header {
    font-size: .8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--brand);
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: .5rem;
  }
  .bom-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.75rem 2rem;
    box-shadow: var(--shadow-sm);
  }

  /* ── Tree nodes ─────────────────────────────────────────────────────── */
  .tree-root { display: flex; flex-direction: column; gap: 0; }

  .tree-node {
    display: flex;
    align-items: center;
    gap: .6rem;
    padding: .6rem .75rem;
    border-radius: 7px;
    border-left: 3px solid transparent;
    transition: background .13s;
    font-size: .9rem;
    flex-wrap: wrap;
  }
  .tree-node:hover { background: #f4f4f8; }

  /* Depth levels — left border colour signals nesting depth */
  .tree-depth-0 { border-left-color: var(--brand); background: #f5f3ff; font-weight: 600; }
  .tree-depth-1 { border-left-color: #a5b4fc; margin-left: 1.5rem; }
  .tree-depth-2 { border-left-color: #c7d2fe; margin-left: 3rem; }
  .tree-depth-3 { border-left-color: #e0e7ff; margin-left: 4.5rem; }
  .tree-depth-deep { border-left-color: #e0e7ff; margin-left: 6rem; }

  .tree-connector {
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: .82rem;
    color: #a5b4fc;
    flex-shrink: 0;
    min-width: 1.2rem;
  }
  .tree-name { font-weight: 600; color: var(--text); flex: 1; min-width: 140px; }
  .tree-partno {
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: .78rem;
    color: var(--muted);
    flex-shrink: 0;
  }
  .tree-qty {
    font-size: .8rem;
    font-weight: 700;
    color: #4f46e5;
    background: #ede9fe;
    border-radius: 4px;
    padding: .12rem .4rem;
    flex-shrink: 0;
  }
  .tree-price {
    font-size: .82rem;
    color: var(--brand);
    font-weight: 600;
    flex-shrink: 0;
    margin-left: auto;
  }

  .tree-divider { height: 1px; background: var(--border); margin: .2rem 0; }

  /* Warning nodes (missing product, cycle detected) */
  .tree-warning {
    background: #fef9c3 !important;
    border-left-color: #ca8a04 !important;
    color: #854d0e;
    font-size: .85rem;
  }

  /* Non-assembly info box */
  .no-bom-box {
    text-align: center;
    padding: 2.5rem 1.5rem;
    color: var(--muted);
    font-size: .92rem;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    background: var(--bg);
  }
  .no-bom-box p { margin-top: .4rem; font-size: .85rem; }

  /* ── Responsive ─────────────────────────────────────────────────────── */
  @media (max-width: 640px) {
    .detail-meta { grid-template-columns: 1fr 1fr; }
    .tree-depth-1 { margin-left: .75rem; }
    .tree-depth-2 { margin-left: 1.5rem; }
    .tree-depth-3, .tree-depth-deep { margin-left: 2.25rem; }
    .tree-price { margin-left: 0; }
  }
</style>
"""


# =============================================================================
# HELPERS
# =============================================================================

def _badge(ptype: str) -> str:
    labels = {"assembly": "Assembly", "support": "Support", "standalone": "Standalone"}
    return f'<span class="badge badge-{ptype}">{labels.get(ptype, ptype)}</span>'


def _build_child_select_options(exclude_id: str | None = None) -> str:
    """
    Build <option> HTML for child product dropdowns.
    exclude_id: omit this product ID from the list (used to hide self on edit).
    """
    opts = '<option value="">— select component —</option>'
    for pid, p in STORE["products"].items():
        if pid == exclude_id:
            continue
        ptype = p.get("type", "standalone")
        label = f'[{ptype[:3].upper()}] {p["name"]} ({p["part_no"]})'
        opts += f'<option value="{pid}">{label}</option>'
    return opts


def _render_tree(product_id: str, qty: int, depth: int, visited: frozenset) -> str:
    """
    Recursively renders a product node and all its children as indented HTML.

    Parameters
    ----------
    product_id : str        — ID of the product to render at this level
    qty        : int        — quantity of this product in the parent assembly
    depth      : int        — current nesting depth (0 = direct child of root assembly)
    visited    : frozenset  — product IDs already on this branch (cycle guard)

    Design notes
    ------------
    * Uses frozenset (immutable) so sibling branches get independent snapshots.
    * Depths > 3 collapse to a single CSS class to keep indentation sane.
    * Missing products and cycles render as yellow warning nodes; they never crash.
    """
    depth_cls = f"tree-depth-{depth}" if depth <= 3 else "tree-depth-deep"

    # ── Cycle guard ──────────────────────────────────────────────────────
    if product_id in visited:
        return (
            f'<div class="tree-node {depth_cls} tree-warning">'
            f'  <span class="tree-connector">&#8627;</span>'
            f'  &#9888;&nbsp;Circular reference detected'
            f'  &nbsp;<code style="font-size:.78rem;">{product_id[:8]}…</code>'
            f'</div>'
        )

    # ── Missing product guard ────────────────────────────────────────────
    p = STORE["products"].get(product_id)
    if p is None:
        return (
            f'<div class="tree-node {depth_cls} tree-warning">'
            f'  <span class="tree-connector">&#8627;</span>'
            f'  &#9888;&nbsp;Missing product'
            f'  &nbsp;<code style="font-size:.78rem;">{product_id[:8]}…</code>'
            f'</div>'
        )

    # ── Render this node ─────────────────────────────────────────────────
    ptype     = p.get("type", "standalone")
    children  = p.get("children", [])
    connector = "&#8627;" if depth > 0 else "&#9862;"   # ↳  or  ⚦ (gear-like)

    qty_html = f'<span class="tree-qty">&#215;&nbsp;{qty}</span>' if qty > 0 else ""

    node_html = (
        f'<div class="tree-node {depth_cls}">'
        f'  <span class="tree-connector">{connector}</span>'
        f'  <span class="tree-name">{p["name"]}</span>'
        f'  <span class="tree-partno">{p["part_no"]}</span>'
        f'  {_badge(ptype)}'
        f'  {qty_html}'
        f'  <span class="tree-price">&#8377;&nbsp;{p["base_price"]:,.0f}</span>'
        f'</div>'
    )

    # ── Recurse into children ────────────────────────────────────────────
    new_visited = visited | {product_id}
    for child in children:
        node_html += _render_tree(
            child["product_id"],
            child["qty"],
            depth + 1,
            new_visited,
        )

    return node_html


# =============================================================================
# ROUTES
# =============================================================================

@product_bp.route("/")
def list_products():
    """
    GET /product
    Lists all products with type badge, child-component count, and — for
    assembly rows — a View button linking to the BOM inspector.
    """
    ensure_demo_products()

    products = STORE["products"]
    msg      = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    add_url  = url_for("product.add_product")
    dash_url = url_for("dashboard.index")

    # ── Build table rows ──────────────────────────────────────────────
    if products:
        rows = ""
        for pid, p in products.items():
            ptype      = p.get("type", "standalone")
            children   = p.get("children", [])
            delete_url = url_for("product.delete_product", id=pid)
            view_url   = url_for("product.view_product",   id=pid)

            # "View" button only makes sense for assemblies
            view_btn = (
                f'<a href="{view_url}" '
                f'   class="btn btn-ghost" '
                f'   style="font-size:.78rem;padding:.28rem .7rem;" '
                f'   title="Inspect BOM tree">'
                f'  &#128269; View'
                f'</a>'
            ) if ptype == "assembly" else ""

            child_info = ""
            if ptype == "assembly":
                n = len(children)
                child_info = f'<div class="children-count">&#8627; {n} component{"s" if n != 1 else ""}</div>'

            desc_preview = (p.get("description") or "—").splitlines()[0]

            rows += f"""
            <tr>
              <td class="td-name">
                {p['name']}
                {child_info}
              </td>
              <td class="td-partno">{p['part_no']}</td>
              <td>{_badge(ptype)}</td>
              <td class="td-unit">{p['unit']}</td>
              <td class="td-price">&#8377; {p['base_price']:,.0f}</td>
              <td class="col-desc" style="color:var(--muted);font-size:.85rem;max-width:200px;
                          overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                {desc_preview}
              </td>
              <td style="white-space:nowrap;">
                <div style="display:flex;gap:.4rem;align-items:center;">
                  {view_btn}
                  <a href="{delete_url}"
                     class="btn-delete"
                     onclick="return confirm('Delete {p['name']}? This cannot be undone.')">
                    Delete
                  </a>
                </div>
              </td>
            </tr>
            """

        table_html = f"""
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Part No.</th>
                <th>Type</th>
                <th>Unit</th>
                <th>Base Price</th>
                <th class="col-desc">Description</th>
                <th></th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        """
    else:
        table_html = """
        <div class="empty-state">
          <div style="font-size:2rem;">&#128230;</div>
          <p>No products yet. Add your first product to get started.</p>
        </div>
        """

    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {msg}</div>'

    type_counts: dict[str, int] = {}
    for p in products.values():
        t = p.get("type", "standalone")
        type_counts[t] = type_counts.get(t, 0) + 1
    subtitle = " &nbsp;&#183;&nbsp; ".join(f'{v} {k}' for k, v in sorted(type_counts.items()))

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>Products &#8212; QMS</title>
      {BASE_STYLES}
      {PRODUCT_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        {alert_html}
        <div class="page-top">
          <h1>Product <span>Catalog</span>
            <span style="font-size:.75rem;font-weight:500;color:var(--muted);margin-left:.6rem;">
              {len(products)} total &nbsp;&#183;&nbsp; {subtitle}
            </span>
          </h1>
          <div style="display:flex;gap:.75rem;">
            <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
            <a href="{add_url}" class="btn">+ Add Product</a>
          </div>
        </div>
        {table_html}
        <footer>
          <p>QMS Platform &nbsp;&#183;&nbsp; Product Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return render_template_string(template)


@product_bp.route("/view/<id>")
def view_product(id: str):
    """
    GET /product/view/<id>

    Full-detail view for any product. For assemblies, renders a recursive
    indented BOM tree showing every child (and their children) down to leaf
    nodes. Non-assemblies show a polite "no components" message.

    Edge cases handled:
      - Unknown product ID  → redirect to catalog with error
      - Assembly with no children → "empty assembly" notice
      - Missing child reference  → yellow ⚠ warning node in tree
      - Circular reference (shouldn't exist due to can_add_child guard,
        but _render_tree handles it defensively via visited frozenset)
    """
    ensure_demo_products()

    product = STORE["products"].get(id)
    if not product:
        return redirect(url_for(
            "product.list_products",
            msg="Product not found.",
            type="error",
        ))

    list_url = url_for("product.list_products")
    ptype    = product.get("type", "standalone")
    children = product.get("children", [])

    # ── Build BOM / tree section ──────────────────────────────────────
    if ptype == "assembly" and children:
        tree_nodes = ""
        divider    = '<div class="tree-divider"></div>'
        for i, child in enumerate(children):
            tree_nodes += _render_tree(
                child["product_id"],
                child["qty"],
                depth=0,
                # Seed visited with the root so it cannot appear as its own child
                visited=frozenset([id]),
            )
            if i < len(children) - 1:
                tree_nodes += divider

        n = len(children)
        bom_html = f"""
        <div class="bom-section">
          <div class="bom-header">
            &#9881;&nbsp; Bill of Materials
            <span style="font-weight:500;color:var(--muted);font-size:.78rem;margin-left:.25rem;">
              &mdash; {n} direct component{"s" if n != 1 else ""}
            </span>
          </div>
          <div class="tree-root">
            {tree_nodes}
          </div>
        </div>
        """

    elif ptype == "assembly" and not children:
        bom_html = """
        <div class="no-bom-box">
          <div style="font-size:1.8rem;">&#128230;</div>
          <strong>Empty Assembly</strong>
          <p>This assembly has no child components defined yet.</p>
        </div>
        """
    else:
        type_label = ptype.capitalize()
        bom_html = f"""
        <div class="no-bom-box">
          <div style="font-size:1.8rem;">&#128269;</div>
          <strong>{type_label} product &mdash; no sub-components</strong>
          <p>Only <em>Assembly</em> products have a Bill of Materials.
             This is a leaf node that can be used as a component inside assemblies.</p>
        </div>
        """

    # ── Description block (only if non-empty) ────────────────────────
    desc = (product.get("description") or "").strip()
    desc_html = f'<div class="detail-desc">{desc}</div>' if desc else ""

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{product['name']} &#8212; QMS</title>
      {BASE_STYLES}
      {PRODUCT_STYLES}
      {VIEW_STYLES}
    </head>
    <body>
      {_nav()}
      <main>

        <!-- Page header -->
        <div class="page-top">
          <h1>Product <span>Detail</span></h1>
          <a href="{list_url}" class="btn btn-ghost">&#8592; Back to Catalog</a>
        </div>

        <!-- Product header card -->
        <div class="detail-card">
          <h2>
            {product['name']}
            {_badge(ptype)}
          </h2>
          <div class="detail-meta">
            <div class="detail-meta-item">
              <strong>Part No.</strong>
              <span style="font-family:'SFMono-Regular',Consolas,monospace;font-size:.88rem;">
                {product['part_no']}
              </span>
            </div>
            <div class="detail-meta-item">
              <strong>Unit</strong>
              <span>{product['unit']}</span>
            </div>
            <div class="detail-meta-item">
              <strong>Base Price</strong>
              <span class="price">&#8377; {product['base_price']:,.0f}</span>
            </div>
            <div class="detail-meta-item">
              <strong>Type</strong>
              <span>{ptype.capitalize()}</span>
            </div>
          </div>
          {desc_html}
        </div>

        <!-- BOM tree or informational placeholder -->
        {bom_html}

        <footer style="margin-top:2.5rem;">
          <p>QMS Platform &nbsp;&#183;&nbsp; Product Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return render_template_string(template)


@product_bp.route("/add", methods=["GET", "POST"])
def add_product():
    """
    GET  /product/add  — render form with type selector + assembly BOM editor.
    POST /product/add  — validate, run cycle check on children, write to STORE.
    """
    ensure_demo_products()

    error    = None
    products = STORE["products"]

    if request.method == "POST":
        name        = request.form.get("name",        "").strip()
        part_no     = request.form.get("part_no",     "").strip()
        unit        = request.form.get("unit",        "").strip()
        base_price  = request.form.get("base_price",  "").strip()
        description = request.form.get("description", "").strip()
        ptype       = request.form.get("type",        "standalone")

        raw_child_ids  = request.form.getlist("child_product_id")
        raw_child_qtys = request.form.getlist("child_qty")

        if not name or not part_no or not unit or not base_price:
            error = "Name, Part No., Unit, and Base Price are required."
        elif ptype not in ("standalone", "assembly", "support"):
            error = "Invalid product type."
        else:
            try:
                price_val = float(base_price)
                if price_val < 0:
                    raise ValueError
            except ValueError:
                error = "Base Price must be a valid positive number."

        children: list[dict] = []
        new_id = str(uuid.uuid4())

        if not error and ptype == "assembly":
            seen: set[str] = set()
            for cid, cqty_raw in zip(raw_child_ids, raw_child_qtys):
                cid = cid.strip()
                if not cid:
                    continue
                if cid not in products:
                    error = "One or more selected components no longer exist in the catalog."
                    break
                if cid in seen:
                    error = f"Duplicate component: '{products[cid]['name']}'. Each component can appear only once."
                    break
                try:
                    qty = int(cqty_raw)
                    if qty < 1:
                        raise ValueError
                except (ValueError, TypeError):
                    error = f"Invalid quantity for '{products[cid]['name']}'. Must be a whole number >= 1."
                    break

                ok, reason = can_add_child(new_id, cid)
                if not ok:
                    error = reason
                    break

                seen.add(cid)
                children.append({"product_id": cid, "qty": qty})

        if not error:
            STORE["products"][new_id] = {
                "id":          new_id,
                "name":        name,
                "part_no":     part_no,
                "unit":        unit,
                "base_price":  price_val,
                "description": description,
                "type":        ptype,
                "children":    children,
            }
            return redirect(url_for(
                "product.list_products",
                msg=f"'{name}' added successfully.",
                type="success",
            ))

    list_url   = url_for("product.list_products")
    error_html = f'<div class="alert alert-error">&#10007; {error}</div>' if error else ""

    unit_options   = ["", "pcs", "set", "kg", "m", "L", "box", "pair", "roll"]
    unit_opts_html = "".join(
        f'<option value="{u}" {"selected" if request.form.get("unit") == u else ""}>'
        f'{u if u else "&#8212; Select unit &#8212;"}</option>'
        for u in unit_options
    )

    type_opts_html = "".join(
        f'<option value="{t}" {"selected" if request.form.get("type", "standalone") == t else ""}>'
        f'{t.capitalize()}</option>'
        for t in ("standalone", "assembly", "support")
    )

    child_select_options = _build_child_select_options(exclude_id=None)

    prior_ids  = request.form.getlist("child_product_id")
    prior_qtys = request.form.getlist("child_qty")
    restored   = ""
    for cid, cqty in zip(prior_ids, prior_qtys):
        if not cid:
            continue
        opts = '<option value="">&#8212; select component &#8212;</option>'
        for pid, p in products.items():
            sel    = "selected" if pid == cid else ""
            plabel = p.get("type", "standalone")
            opts  += f'<option value="{pid}" {sel}>[{plabel[:3].upper()}] {p["name"]} ({p["part_no"]})</option>'
        restored += f"""
        <div class="child-row">
          <select name="child_product_id">{opts}</select>
          <input type="number" name="child_qty" value="{cqty}" min="1" step="1"/>
          <button type="button" class="btn-remove-child"
                  onclick="this.closest('.child-row').remove()">&#215;</button>
        </div>
        """

    current_type     = request.form.get("type", "standalone")
    assembly_display = "block" if current_type == "assembly" else "none"
    no_products_hint = (
        '<p class="no-products-hint">No other products in catalog yet. '
        'Add standalone or support products first.</p>'
        if not products else ""
    )

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>Add Product &#8212; QMS</title>
      {BASE_STYLES}
      {PRODUCT_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        <div class="page-top">
          <h1>Add <span>Product</span></h1>
          <a href="{list_url}" class="btn btn-ghost">&#8592; Back to Catalog</a>
        </div>

        {error_html}

        <template id="child-opt-tpl">{child_select_options}</template>

        <div class="form-card">
          <h2>New Product</h2>
          <form method="POST" action="">
            <div class="form-grid">

              <div class="form-group">
                <label for="name">Product Name *</label>
                <input type="text" id="name" name="name"
                       value="{request.form.get('name', '')}"
                       placeholder="e.g. Steel Bracket" required autocomplete="off"/>
              </div>

              <div class="form-group">
                <label for="part_no">Part No. *</label>
                <input type="text" id="part_no" name="part_no"
                       value="{request.form.get('part_no', '')}"
                       placeholder="e.g. SB-1042" required autocomplete="off"/>
              </div>

              <div class="form-group">
                <label for="unit">Unit *</label>
                <select id="unit" name="unit" required>{unit_opts_html}</select>
              </div>

              <div class="form-group">
                <label for="base_price">Base Price (&#8377;) *</label>
                <input type="number" id="base_price" name="base_price"
                       value="{request.form.get('base_price', '')}"
                       placeholder="0.00" step="0.01" min="0" required/>
              </div>

              <div class="form-group full">
                <label for="type-select">Product Type *</label>
                <select id="type-select" name="type"
                        onchange="toggleAssemblySection()">{type_opts_html}</select>
              </div>

              <div class="form-group full">
                <label for="description">Description</label>
                <textarea id="description" name="description"
                  placeholder="Dimensions, material, spec notes&#8230;">{request.form.get('description', '')}</textarea>
              </div>

              <div class="assembly-section full" id="assembly-section"
                   style="display:{assembly_display};">
                <div class="assembly-section-title">&#9881; Components / Bill of Materials</div>
                {no_products_hint}
                <div id="children-container">{restored}</div>
                <button type="button" class="btn-add-child" onclick="addChildRow()">
                  + Add Component
                </button>
              </div>

            </div>

            <div class="form-actions">
              <button type="submit" class="btn">Save Product</button>
              <a href="{list_url}" class="btn btn-ghost">Cancel</a>
            </div>
          </form>
        </div>

        <footer>
          <p>QMS Platform &nbsp;&#183;&nbsp; Product Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>

      <script>
        function toggleAssemblySection() {{
          const val     = document.getElementById('type-select').value;
          const section = document.getElementById('assembly-section');
          section.style.display = (val === 'assembly') ? 'block' : 'none';
        }}

        function addChildRow() {{
          const container = document.getElementById('children-container');
          const optHtml   = document.getElementById('child-opt-tpl').innerHTML;

          const row = document.createElement('div');
          row.className = 'child-row';

          const sel = document.createElement('select');
          sel.name  = 'child_product_id';
          sel.innerHTML = optHtml;

          const qty = document.createElement('input');
          qty.type  = 'number';
          qty.name  = 'child_qty';
          qty.value = '1';
          qty.min   = '1';
          qty.step  = '1';

          const btn = document.createElement('button');
          btn.type        = 'button';
          btn.className   = 'btn-remove-child';
          btn.textContent = '\u00d7';
          btn.onclick = function() {{ this.closest('.child-row').remove(); }};

          row.appendChild(sel);
          row.appendChild(qty);
          row.appendChild(btn);
          container.appendChild(row);
        }}
      </script>
    </body>
    </html>
    """
    return render_template_string(template)


@product_bp.route("/delete/<id>")
def delete_product(id: str):
    """
    GET /product/delete/<id>
    Enforces assembly integrity: blocks if the product is used as a child
    in any other product. Route signature unchanged from Phase 1.
    """
    product = STORE["products"].get(id)

    if not product:
        return redirect(url_for(
            "product.list_products",
            msg="Product not found — it may have already been deleted.",
            type="error",
        ))

    allowed, reason = can_delete_product(id)
    if not allowed:
        return redirect(url_for(
            "product.list_products",
            msg=reason,
            type="error",
        ))

    name = product["name"]
    del STORE["products"][id]

    return redirect(url_for(
        "product.list_products",
        msg=f"'{name}' deleted.",
        type="success",
    ))