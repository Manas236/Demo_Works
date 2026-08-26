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

────────────────────────────────────────────────────────────────────────────
ESCAPING  (26 August 2026)
────────────────────────────────────────────────────────────────────────────
This module used to have **no escaping at all** and rendered every page
through `render_template_string()`. Both are closed here, and the pass was
deliberately narrow: values are escaped, `_page()` replaces the second Jinja
parse, and **nothing else was touched** — no refactor, no renaming, no new
behaviour. INTRODUCTION.md §7 freezes this file against refactor and feature
work; CLIENT_CHANGES-2.md's "Security items promoted by this phase" names this
exact defect as a narrow security fix the freeze permits, precedent `9d060ee`.

Why it stopped being cosmetic: Phase 3B put sessions in front of every page,
so a stored `<script>` in a product name runs in the reader's session, and
`{{ config['SECRET_KEY'] }}` in one printed the signing key — which is session
forgery, not defacement.

`P.esc` is `html.escape(..., quote=True)`. `pipeline.py` imports nothing of
ours, so this edge cannot cycle. What is deliberately NOT escaped: the style
constants, `_nav()`, `B.HEAD_ICON`, the markup this module builds itself
(`_badge`, the option lists, the tree nodes, the alert wrapper) and the money
format `{...:,.0f}` — see ABOUT.md §9.
"""

import uuid
from flask import Blueprint, request, redirect, url_for

# ── Shared imports ────────────────────────────────────────────────────────────
import branding as B
import pipeline as P
from dashboard import BASE_STYLES, _nav
from store import STORE

# ── Blueprint ─────────────────────────────────────────────────────────────────
product_bp = Blueprint("product", __name__, url_prefix="/product")


# =============================================================================
# DEMO SEED DATA
# =============================================================================

# Fixed UUIDs so assembly->child references are stable across the seeding call.
_S = {
    "main_pump": "a1000001-beef-4000-8000-000000000001",
    "pump_bare": "a1000002-beef-4000-8000-000000000002",
    "motor75":   "a1000003-beef-4000-8000-000000000003",
    "base_frame":"a1000004-beef-4000-8000-000000000004",
    "engine":    "a1000005-beef-4000-8000-000000000005",
    "radiator":  "a1000006-beef-4000-8000-000000000006",
    "lub_oil":   "a1000007-beef-4000-8000-000000000007",
    "battery":   "a1000008-beef-4000-8000-000000000008",
    "fuel_tank": "a1000009-beef-4000-8000-000000000009",
    "jockey":    "a100000a-beef-4000-8000-00000000000a",
    "extng_abc": "a100000b-beef-4000-8000-00000000000b",
    "hose_reel": "a100000c-beef-4000-8000-00000000000c",
}


def ensure_demo_products() -> None:
    """
    Seeds STORE["products"] with 10 realistic demo products on first call.
    Subsequent calls are no-ops — guarded by STORE["_seeded"].

    Call this at the top of any route that reads from the product catalog,
    so the list is never empty on first visit without a manual add.

    Seed structure (a typical fire pump room, plus two loose line items):
      Assemblies : MAIN FIRE PUMP SET - ELECTRIC, DIESEL ENGINE DRIVE, JOCKEY PUMP SET
      Support    : END SUCTION FIRE PUMP, 75KW/100HP MOTOR, PUMP BASE FRAME
      Standalone : RADIATOR COOLANT, LUB OIL, BATTERY 180 AMP, FUEL TANK 200 LTR,
                   ABC EXTINGUISHER 6 KG, FIRST-AID HOSE REEL

    ⚠  Demo data only — prices are placeholders, not Samruddhi Fire's rates,
       and the HSN codes are plausible chapter headings, not a classification
       Samruddhi's CA has signed off. Both must be replaced before a tax
       invoice built on these rows goes to a customer.
    """
    if STORE["_seeded"]:
        return

    # Standalone products (leaf nodes — no children)
    _seed(_S["radiator"],  "RADIATOR COOLANT",      "RAD-001", "L",    8_500,
          "Standard coolant for diesel engines. 10L fill capacity.",
          "standalone", [], hsn="38200000")
    _seed(_S["lub_oil"],   "LUB OIL",               "OIL-002", "L",    3_200,
          "15W-40 mineral lubricant. Recommended change: 250 hrs.",
          "standalone", [], hsn="27101980")
    _seed(_S["battery"],   "BATTERY 180 AMP",        "BAT-003", "pcs", 12_500,
          "12V / 180 Ah sealed lead-acid. Maintenance-free.",
          "standalone", [], hsn="85071000")
    _seed(_S["fuel_tank"], "FUEL TANK 200 LTR",      "FT-004",  "pcs", 18_000,
          "Mild steel fuel tank, 200L capacity, coated interior.",
          "standalone", [], hsn="73090090")
    _seed(_S["extng_abc"], "ABC DRY POWDER EXTINGUISHER 6 KG", "EXT-005", "pcs", 2_450,
          "IS 15683 stored-pressure ABC extinguisher with wall bracket and hose.",
          "standalone", [], hsn="84241000")
    _seed(_S["hose_reel"], "FIRST-AID HOSE REEL 30 M", "HR-006", "pcs", 9_800,
          "IS 884 swinging hose reel drum, 20 mm bore rubber hose with shut-off nozzle.",
          "standalone", [], hsn="84249000")

    # Support items (sub-components; not sold standalone)
    _seed(_S["pump_bare"],  "END SUCTION FIRE PUMP 80/26", "PMP-010", "set",  125_000,
          "Horizontal end-suction fire pump. Flow: 80 m3/hr, Head: 26m.",
          "support", [], hsn="84137010")
    _seed(_S["motor75"],    "75KW/100HP MOTOR",            "MOT-011", "pcs", 210_000,
          "TEFC squirrel cage induction motor. 75kW, 4-pole, 415V/50Hz.",
          "support", [], hsn="85015290")
    _seed(_S["base_frame"], "PUMP BASE FRAME 80/26",       "FRM-012", "pcs",  45_000,
          "Fabricated MS base frame for the 80/26 pump + motor set.",
          "support", [], hsn="73089090")

    # Assemblies (have children; leaf products must be seeded first)
    _seed(_S["main_pump"], "MAIN FIRE PUMP SET - ELECTRIC", "MFP-100", "set", 850_000,
          "Complete electric-driven main fire pump set: pump, motor and base frame, "
          "coupled and factory tested.",
          "assembly", [
              {"product_id": _S["pump_bare"],  "qty": 1},
              {"product_id": _S["motor75"],    "qty": 1},
              {"product_id": _S["base_frame"], "qty": 1},
          ], hsn="84137010")
    _seed(_S["engine"], "DIESEL ENGINE FIRE PUMP DRIVE", "DEP-200", "set", 380_000,
          "Diesel engine drive package. Radiator-cooled, electric start, "
          "with fuel tank and first fill.",
          "assembly", [
              {"product_id": _S["radiator"],  "qty": 1},
              {"product_id": _S["lub_oil"],   "qty": 5},
              {"product_id": _S["fuel_tank"], "qty": 1},
          ], hsn="84089090")
    _seed(_S["jockey"], "JOCKEY PUMP SET", "JKY-300", "set", 95_000,
          "Pressure-maintenance jockey pump. Auto start/stop on pressure drop.",
          "assembly", [
              {"product_id": _S["battery"], "qty": 1},
          ], hsn="84137010")

    STORE["_seeded"] = True


def _seed(pid, name, part_no, unit, base_price, description, ptype, children, hsn=""):
    """
    Write one demo product; skips silently if that ID already exists.

    The one exception is `hsn`, which is **backfilled onto an existing row when
    it is blank**. These rows have fixed UUIDs and were seeded before the
    catalogue captured HSN at all, so a database from an earlier run holds all
    twelve of them without one — and with no product edit route (§7.2) there is
    no way for a user to add it by hand. Without this they would put an amber
    chip on every tax invoice forever.

    It fills a gap and never overwrites: a code someone has already set, here or
    at /settings-time, is left exactly as it is.
    """
    existing = STORE["products"].get(pid)
    if existing is not None:
        if hsn and not str(existing.get("hsn") or "").strip():
            existing["hsn"] = hsn
        return

    STORE["products"][pid] = {
        "id":          pid,
        "name":        name,
        "part_no":     part_no,
        "hsn":         hsn,
        "unit":        unit,
        "base_price":  float(base_price),
        "description": description,
        "type":        ptype,
        "children":    children,
    }


def backfill_line_item_hsn(store: dict = None) -> dict:
    """
    Fill a blank `hsn` on the frozen line items of existing quotations,
    proformas and tax invoices, matching each row to the catalogue by part_no.

    **This is a one-time data migration, not app behaviour. It is deliberately
    NOT called at boot.** Read ABOUT.md §3 before running it again.

    Every document in the chain freezes a *copy* of its line items at issue, so
    that editing a product later cannot rewrite a quotation the customer has
    already seen. That freeze is load-bearing and this function drives straight
    through it — which is only defensible because of what it does and does not
    touch:

    * It fills a field that **did not exist** when those rows were written, so
      there is no agreed value being overwritten. Records created before the
      catalogue captured HSN could otherwise never acquire one, and a tax
      invoice raised from such a proforma prints an amber chip on every line.
    * It **only ever fills a blank**. A code already on a row — including one
      that differs from today's catalogue — is left exactly as it is.
    * It never touches name, qty, unit, price, total or depth. Nothing that
      carries a commercial agreement moves.

    Run it after adding HSN to the catalogue for products that older documents
    were built from. Do **not** wire it into startup: once a product's
    classification is corrected, pushing that correction onto documents already
    issued is precisely the rewriting the freeze exists to prevent.

    Returns a per-collection count of the rows changed.
    """
    store = store if store is not None else STORE

    # part_no -> hsn, from the live catalogue. Part numbers are the stable key
    # here: names get edited, and a line item does not record the product id.
    by_part = {}
    by_name = {}
    for p in store.get("products", {}).values():
        code = str(p.get("hsn") or "").strip()
        if not code:
            continue
        if p.get("part_no"):
            by_part[str(p["part_no"]).strip()] = code
        if p.get("name"):
            by_name[str(p["name"]).strip()] = code

    changed = {}
    for coll in ("quotations", "proformas", "invoices"):
        n = 0
        for rec in store.get(coll, {}).values():
            for row in rec.get("line_items", []) or []:
                if str(row.get("hsn") or "").strip():
                    continue
                code = (by_part.get(str(row.get("part_no") or "").strip())
                        or by_name.get(str(row.get("name") or "").strip()))
                if code:
                    row["hsn"] = code
                    n += 1
        changed[coll] = n
    return changed


def _valid_hsn(code: str) -> bool:
    """
    Is this a well-formed HSN (goods) or SAC (services) code?

    Digits only, and 4, 6 or 8 of them — the three lengths GST actually issues.
    How many are *required* depends on the supplier's turnover (4 up to ₹5 cr,
    6 above it), which this app does not know, so the rule here is shape-only:
    reject a typo, never dictate a length.

    It cannot tell you the code is the *right* one for the goods — that is a
    classification judgement, and getting it wrong is the customer's ITC. This
    only stops "8413-A" and "841" reaching a tax invoice.
    """
    code = (code or "").strip()
    return code.isdigit() and len(code) in (4, 6, 8)


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

  /* Sub-label under a form input. Used where the field's consequence is not
     obvious from its name — HSN looks optional until you learn it decides
     whether the customer can claim input tax credit. */
  .field-hint {
    display: block; margin-top: .35rem; font-size: .76rem;
    color: var(--muted); line-height: 1.45; font-weight: 400;
    text-transform: none; letter-spacing: 0;
  }

  /* A product with no HSN cannot go on a tax invoice, so the catalogue flags it
     in place rather than showing an empty cell. It reuses branding.field() and
     the .todo-chip from CSS_TOKENS — the app already has one visual language
     for "a statutory detail is still missing", and this is that. */

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

def _page(html: str) -> str:
    """
    A finished page. Deliberately **not** Jinja-rendered.

    Every view here used to end `return render_template_string(template)` on a
    string that was already fully interpolated. Nothing is passed as Jinja
    context, so that second parse bought nothing — but it executed any
    `{{ … }}` that had arrived from user input, and `P.esc` escapes
    `< > & " '` and deliberately not braces. A product named
    `{{ config['SECRET_KEY'] }}` printed this application's signing key on
    `/product/`. ABOUT.md §7 gap 9d; the same one-liner already fixed
    `spec.py`, `boq.py`, `proforma.py`, `invoice.py`, `purchase.py`,
    `address.py`, `settings.py` and `dashboard.py`.

    Flask returns any `str` a view returns, so this is the whole of the fix.
    """
    return html


def _esc(v) -> str:
    """The house escaper, under this module's own short name."""
    return P.esc(v)


def _badge(ptype: str) -> str:
    labels = {"assembly": "Assembly", "support": "Support", "standalone": "Standalone"}
    return (f'<span class="badge badge-{_esc(ptype)}">'
            f'{_esc(labels.get(ptype, ptype))}</span>')


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
        opts += f'<option value="{_esc(pid)}">{_esc(label)}</option>'
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
            f'  &nbsp;<code style="font-size:.78rem;">{_esc(product_id[:8])}…</code>'
            f'</div>'
        )

    # ── Missing product guard ────────────────────────────────────────────
    p = STORE["products"].get(product_id)
    if p is None:
        return (
            f'<div class="tree-node {depth_cls} tree-warning">'
            f'  <span class="tree-connector">&#8627;</span>'
            f'  &#9888;&nbsp;Missing product'
            f'  &nbsp;<code style="font-size:.78rem;">{_esc(product_id[:8])}…</code>'
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
        f'  <span class="tree-name">{_esc(p["name"])}</span>'
        f'  <span class="tree-partno">{_esc(p["part_no"])}</span>'
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
                {_esc(p['name'])}
                {child_info}
              </td>
              <td class="td-partno">{_esc(p['part_no'])}</td>
              <td class="td-partno">{B.field(p.get('hsn'), 'HSN')}</td>
              <td>{_badge(ptype)}</td>
              <td class="td-unit">{_esc(p['unit'])}</td>
              <td class="td-price">&#8377; {p['base_price']:,.0f}</td>
              <td class="col-desc" style="color:var(--muted);font-size:.85rem;max-width:200px;
                          overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                {_esc(desc_preview)}
              </td>
              <td style="white-space:nowrap;">
                <div style="display:flex;gap:.4rem;align-items:center;">
                  {view_btn}
                  <a href="{delete_url}" class="btn-delete">
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
                <th>HSN/SAC</th>
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
        alert_html = f'<div class="alert alert-{_esc(msg_type)}">{icon} {_esc(msg)}</div>'

    type_counts: dict[str, int] = {}
    for p in products.values():
        t = p.get("type", "standalone")
        type_counts[t] = type_counts.get(t, 0) + 1
    subtitle = " &nbsp;&#183;&nbsp; ".join(f'{v} {_esc(k)}' for k, v in sorted(type_counts.items()))

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Products")}</title>
      {B.HEAD_ICON}
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
          <p>{B.COMPANY_NAME} &nbsp;&#183;&nbsp; {B.APP_SUBTITLE} &nbsp;&#183;&nbsp; product catalogue</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return _page(template)          # NOT render_template_string — see _page()


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
          <strong>{_esc(type_label)} product &mdash; no sub-components</strong>
          <p>Only <em>Assembly</em> products have a Bill of Materials.
             This is a leaf node that can be used as a component inside assemblies.</p>
        </div>
        """

    # ── Description block (only if non-empty) ────────────────────────
    desc = (product.get("description") or "").strip()
    desc_html = f'<div class="detail-desc">{_esc(desc)}</div>' if desc else ""

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title(product['name'])}</title>
      {B.HEAD_ICON}
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
            {_esc(product['name'])}
            {_badge(ptype)}
          </h2>
          <div class="detail-meta">
            <div class="detail-meta-item">
              <strong>Part No.</strong>
              <span style="font-family:'SFMono-Regular',Consolas,monospace;font-size:.88rem;">
                {_esc(product['part_no'])}
              </span>
            </div>
            <div class="detail-meta-item">
              <strong>HSN/SAC</strong>
              <span style="font-family:'SFMono-Regular',Consolas,monospace;font-size:.88rem;">
                {B.field(product.get('hsn'), 'HSN')}
              </span>
            </div>
            <div class="detail-meta-item">
              <strong>Unit</strong>
              <span>{_esc(product['unit'])}</span>
            </div>
            <div class="detail-meta-item">
              <strong>Base Price</strong>
              <span class="price">&#8377; {product['base_price']:,.0f}</span>
            </div>
            <div class="detail-meta-item">
              <strong>Type</strong>
              <span>{_esc(ptype.capitalize())}</span>
            </div>
          </div>
          {desc_html}
        </div>

        <!-- BOM tree or informational placeholder -->
        {bom_html}

        <footer style="margin-top:2.5rem;">
          <p>{B.COMPANY_NAME} &nbsp;&#183;&nbsp; {B.APP_SUBTITLE} &nbsp;&#183;&nbsp; product catalogue</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return _page(template)          # NOT render_template_string — see _page()


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
        hsn         = request.form.get("hsn",         "").strip()
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
        elif hsn and not _valid_hsn(hsn):
            error = "HSN/SAC must be 4, 6 or 8 digits — e.g. 8413, 841370 or 84137010."
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
                "hsn":         hsn,
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
    error_html = f'<div class="alert alert-error">&#10007; {_esc(error)}</div>' if error else ""

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
            opts  += (f'<option value="{_esc(pid)}" {sel}>'
                      f'{_esc(f"[{plabel[:3].upper()}] " + p["name"] + " (" + p["part_no"] + ")")}</option>')
        restored += f"""
        <div class="child-row">
          <select name="child_product_id">{opts}</select>
          <input type="number" name="child_qty" value="{_esc(cqty)}" min="1" step="1"/>
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
      <title>{B.page_title("Add Product")}</title>
      {B.HEAD_ICON}
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
                       value="{_esc(request.form.get('name', ''))}"
                       placeholder="e.g. Steel Bracket" required autocomplete="off"/>
              </div>

              <div class="form-group">
                <label for="part_no">Part No. *</label>
                <input type="text" id="part_no" name="part_no"
                       value="{_esc(request.form.get('part_no', ''))}"
                       placeholder="e.g. SB-1042" required autocomplete="off"/>
              </div>

              <div class="form-group">
                <label for="hsn">HSN / SAC Code</label>
                <input type="text" id="hsn" name="hsn"
                       value="{_esc(request.form.get('hsn', ''))}"
                       placeholder="e.g. 84137010" inputmode="numeric"
                       pattern="[0-9]{{4}}|[0-9]{{6}}|[0-9]{{8}}" maxlength="8"
                       autocomplete="off"/>
                <small class="field-hint">4, 6 or 8 digits. Carried onto the
                  quotation, the proforma and the tax invoice — a tax invoice
                  without it is not valid for the customer's input tax credit.</small>
              </div>

              <div class="form-group">
                <label for="unit">Unit *</label>
                <select id="unit" name="unit" required>{unit_opts_html}</select>
              </div>

              <div class="form-group">
                <label for="base_price">Base Price (&#8377;) *</label>
                <input type="number" id="base_price" name="base_price"
                       value="{_esc(request.form.get('base_price', ''))}"
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
                  placeholder="Dimensions, material, spec notes&#8230;">{_esc(request.form.get('description', ''))}</textarea>
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
          <p>{B.COMPANY_NAME} &nbsp;&#183;&nbsp; {B.APP_SUBTITLE} &nbsp;&#183;&nbsp; product catalogue</p>
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
    return _page(template)          # NOT render_template_string — see _page()


@product_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_product(id: str):
    """
    Delete a product — **POST destroys, GET confirms.**

    Previously a GET destroy behind a browser `confirm()`, which never runs for
    a prefetching browser, a crawler, a link unfurler or a back button. Matches
    `ra.delete_ra()` exactly; see ABOUT.md §7's delete audit.

    The assembly-integrity refusal is unchanged — `can_delete_product()` still
    blocks anything used as a child in another product's BOM, and still reports
    the reason rather than hiding the control.

    ⚠ **This module is otherwise off-limits** (INTRODUCTION.md §7, STATE.md
      §3.5) because it has no output escaping across ~1,400 lines and still
      renders through `render_template_string`. This change is deliberately
      confined to closing the GET destroy and adds **no** new exposure:

      - the confirmation page below is **returned directly**, not passed through
        `render_template_string`, so nothing on it is parsed as a Jinja template
        and a product name containing `{{ … }}` cannot execute;
      - every interpolated value is escaped with `markupsafe.escape`, imported
        locally rather than as a module-wide convention this file does not have.

      Nothing else here was tidied, refactored or "fixed".
    """
    from markupsafe import escape as _esc     # local: this module has no escaper

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

    if request.method == "POST":
        name = product["name"]
        del STORE["products"][id]
        return redirect(url_for(
            "product.list_products",
            msg=f"'{name}' deleted.",
            type="success",
        ))

    name = _esc(product.get("name") or "this product")
    part_no = _esc(product.get("part_no") or "")
    kind = _esc(product.get("type") or "standalone")
    n_children = len(product.get("children") or [])

    # Returned directly. NOT render_template_string — see the docstring.
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delete Product")}</title>{B.HEAD_ICON}
  {BASE_STYLES}{PRODUCT_STYLES}
</head>
<body>{_nav()}
<main>
  <div class="page-top"><h1>Delete <span>{name}</span></h1></div>
  <div style="border:1px solid #fecaca;background:#fef2f2;border-radius:10px;
              padding:1rem 1.1rem;margin-bottom:1.2rem;">
    <h2 style="margin:0 0 .5rem;font-size:1rem;color:var(--brand);">
      &#9888; This cannot be undone
    </h2>
    <div style="font-size:.82rem;line-height:1.6;">
      You are about to delete <b>{name}</b>{f" ({part_no})" if part_no else ""},
      a <b>{kind}</b> product{f" with {n_children} component(s)" if n_children else ""}.<br/><br/>
      Quotations, proforma invoices and tax invoices already issued keep the
      copy of the line they froze, so no document already sent changes. It only
      leaves the catalogue &mdash; and there is no edit route, so re-adding it
      means entering it again.
    </div>
  </div>
  <form method="POST" action="{url_for('product.delete_product', id=id)}"
        style="display:flex;gap:.7rem;">
    <button type="submit" class="btn">Delete {name}</button>
    <a href="{url_for('product.list_products')}" class="btn btn-ghost">Keep it</a>
  </form>
</main>
</body></html>"""