"""
quotation.py — Quotation Generation Module
==========================================
Blueprint : quotation_bp
Mounted at : /quotation  (registered in app.py)

Routes
------
  GET  /quotation             — list all saved quotations
  GET  /quotation/create      — blank quotation form (header fields + product picker)
  POST /quotation/create      — validate → expand → save → redirect to view
  GET  /quotation/view/<id>   — rendered quotation document (read-only)

Core
----
  expand_product(product_id, qty, depth, visited)
    Recursively flattens a product into priced line items.
      assembly      → header row  +  children (qty × child.qty each)
      standalone    → single item row with unit price + total
      support       → same as standalone
    visited (frozenset) prevents infinite loops on corrupt data.
"""

import uuid
from datetime import date as _date
from flask import Blueprint, render_template_string, request, redirect, url_for

from dashboard import BASE_STYLES, _nav
from store import STORE

# ── Blueprint ─────────────────────────────────────────────────────────────────
quotation_bp = Blueprint("quotation", __name__, url_prefix="/quotation")


# =============================================================================
# COMPANY IDENTITY  — edit these four constants to match your organisation
# =============================================================================
COMPANY_NAME    = "HYDRO FIRE SYSTEMS PVT. LTD."
COMPANY_TAGLINE = "Fire Protection · Pump Packages · Turnkey Projects"
COMPANY_ADDR    = "Plot 14–B, MIDC Industrial Estate, Pune – 411 019, Maharashtra"
COMPANY_PHONE   = "+91-20-2712-3456  |  +91-98220-12345"
COMPANY_EMAIL   = "sales@hydrofiresy stems.in"
COMPANY_GSTIN   = "27AABCH1234A1Z5"


# =============================================================================
# CSS — list + create pages
# =============================================================================

QUOTATION_STYLES = """
<style>
  /* ── Page header ──────────────────────────────────────────────────── */
  .page-top {
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:2rem; flex-wrap:wrap; gap:1rem;
  }
  .page-top h1 { font-size:1.6rem; font-weight:700; letter-spacing:-.4px; }
  .page-top h1 span { color:var(--brand); }

  /* ── Alerts ──────────────────────────────────────────────────────── */
  .alert {
    padding:.85rem 1.2rem; border-radius:8px; font-size:.88rem;
    font-weight:500; margin-bottom:1.5rem;
    display:flex; align-items:center; gap:.5rem;
  }
  .alert-error   { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
  .alert-success { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }

  /* ── Quotation list table ─────────────────────────────────────────── */
  .table-wrap {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow-sm);
  }
  table { width:100%; border-collapse:collapse; font-size:.9rem; }
  thead { background:var(--bg); border-bottom:1px solid var(--border); }
  th {
    padding:.85rem 1.25rem; text-align:left; font-size:.75rem;
    font-weight:700; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted);
  }
  td {
    padding:.95rem 1.25rem; border-bottom:1px solid var(--border);
    color:var(--text); vertical-align:middle;
  }
  tbody tr:last-child td { border-bottom:none; }
  tbody tr { transition:background .14s; }
  tbody tr:hover { background:#f8fafc; }

  .td-ref   { font-family:'SFMono-Regular',Consolas,monospace; font-weight:700; color:var(--brand); font-size:.88rem; }
  .td-cust  { font-weight:600; }
  .td-total { font-weight:700; color:var(--brand); }
  .td-date  { font-size:.84rem; color:var(--muted); }
  .td-items { font-size:.82rem; color:var(--muted); }

  .btn-view {
    font-family:var(--font); font-size:.78rem; font-weight:600;
    color:var(--brand); background:var(--brand-lt);
    border:1px solid #c7d2fe; border-radius:6px;
    padding:.3rem .75rem; text-decoration:none; display:inline-block;
    transition:background .14s;
  }
  .btn-view:hover { background:#c7d2fe; }

  /* ── Empty state ─────────────────────────────────────────────────── */
  .empty-state {
    text-align:center; padding:4rem 2rem; color:var(--muted);
    background:var(--surface); border:1px dashed var(--border);
    border-radius:var(--radius);
  }
  .empty-state p { margin-top:.5rem; font-size:.9rem; }

  /* ── Form sections ───────────────────────────────────────────────── */
  .form-section {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:2rem 2.25rem;
    box-shadow:var(--shadow-sm); margin-bottom:1.75rem;
  }
  .form-section-title {
    font-size:.78rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.08em; color:var(--brand); margin-bottom:1.4rem;
    display:flex; align-items:center; gap:.4rem;
  }

  .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:1.1rem; }
  .form-group { display:flex; flex-direction:column; gap:.4rem; }
  .form-group.full { grid-column:1/-1; }
  .form-group.span3 { grid-column:1/-1; display:grid; grid-template-columns:1fr 1fr 1fr; gap:1.1rem; }

  label {
    font-size:.77rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.07em; color:var(--muted);
  }
  input[type="text"],
  input[type="date"],
  input[type="number"],
  textarea,
  select {
    font-family:var(--font); font-size:.92rem; color:var(--text);
    background:var(--bg); border:1.5px solid var(--border);
    border-radius:8px; padding:.6rem .9rem; width:100%;
    transition:border-color .15s, box-shadow .15s; outline:none;
  }
  input:focus, textarea:focus, select:focus {
    border-color:var(--brand);
    box-shadow:0 0 0 3px rgba(79,70,229,.12);
    background:#fff;
  }
  textarea { resize:vertical; min-height:80px; }

  /* ── Product picker row ──────────────────────────────────────────── */
  .picker-controls {
    display:grid; grid-template-columns:1fr 100px auto;
    gap:.65rem; align-items:end; margin-bottom:1.1rem;
  }
  .picker-controls select,
  .picker-controls input { margin:0; }

  .add-error {
    font-size:.82rem; color:#b91c1c; background:#fef2f2;
    border:1px solid #fecaca; border-radius:6px;
    padding:.35rem .8rem; margin-top:.5rem; display:none;
  }

  /* ── Selected products list ──────────────────────────────────────── */
  #product-list { display:flex; flex-direction:column; gap:.45rem; margin-top:.75rem; }

  .sel-row {
    display:grid; grid-template-columns:1fr 110px 36px;
    gap:.6rem; align-items:center;
    background:var(--bg); border:1px solid var(--border);
    border-radius:8px; padding:.5rem .9rem;
    transition:border-color .14s;
  }
  .sel-row:hover { border-color:#a5b4fc; }

  .sel-info-name   { font-size:.88rem; font-weight:600; color:var(--text); }
  .sel-info-partno {
    font-size:.73rem; color:var(--muted);
    font-family:'SFMono-Regular',Consolas,monospace; margin-top:.1rem;
  }

  .sel-qty-input {
    font-family:var(--font); font-size:.9rem; color:var(--text);
    background:#fff; border:1.5px solid var(--border); border-radius:6px;
    padding:.4rem .55rem; text-align:center; outline:none; width:100%;
    transition:border-color .15s;
  }
  .sel-qty-input:focus { border-color:var(--brand); box-shadow:0 0 0 2px rgba(79,70,229,.1); }

  .btn-remove-sel {
    font-family:var(--font); font-size:1rem; font-weight:700;
    color:#ef4444; background:#fef2f2; border:1px solid #fecaca;
    border-radius:6px; cursor:pointer; height:34px; width:34px;
    display:flex; align-items:center; justify-content:center;
    transition:background .14s; flex-shrink:0;
  }
  .btn-remove-sel:hover { background:#fee2e2; }

  #empty-notice {
    text-align:center; padding:1.75rem 1rem; color:var(--muted);
    font-size:.88rem; border:1.5px dashed var(--border); border-radius:8px;
    background:var(--bg);
  }

  /* ── Form actions ────────────────────────────────────────────────── */
  .form-actions { display:flex; gap:.75rem; margin-top:1.75rem; align-items:center; }

  /* ── Responsive ──────────────────────────────────────────────────── */
  @media(max-width:700px){
    .form-grid { grid-template-columns:1fr; }
    .form-group.full, .form-group.span3 { grid-column:1; display:flex; flex-direction:column; }
    .picker-controls { grid-template-columns:1fr; }
    .sel-row { grid-template-columns:1fr 85px 34px; }
    th, td { padding:.7rem .85rem; }
    .col-hide { display:none; }
  }

  /* ── Label row with inline helper button ────────────────────── */
  .field-label-row {
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:.25rem;
  }
  .btn-tpl {
    font-family:var(--font); font-size:.73rem; font-weight:600;
    color:var(--brand); background:var(--brand-lt); border:1px solid #c7d2fe;
    border-radius:6px; padding:.28rem .65rem; cursor:pointer;
    transition:background .14s;
  }
  .btn-tpl:hover { background:#c7d2fe; }
</style>
"""


# =============================================================================
# CSS — quotation document view
# =============================================================================

VIEW_DOC_STYLES = """
<style>
  /* ── Wrapper ─────────────────────────────────────────────────────── */
  .doc-wrap { max-width:1040px; margin:0 auto; }

  .doc-actions {
    display:flex; gap:.75rem; justify-content:flex-end;
    margin-bottom:1.25rem; flex-wrap:wrap;
  }

  .quotation-doc {
    background:#fff; border:1px solid var(--border);
    border-radius:var(--radius);
    box-shadow:0 4px 28px rgba(0,0,0,.09);
    overflow:hidden;
  }

  /* ── Letterhead ──────────────────────────────────────────────────── */
  .letterhead {
    padding:1.6rem 2.25rem; border-bottom:3px solid var(--brand);
    display:flex; justify-content:space-between; align-items:flex-start;
    flex-wrap:wrap; gap:1.25rem; background:#fdfcff;
  }
  .lh-name {
    font-size:1.35rem; font-weight:800; color:var(--brand);
    letter-spacing:-.4px; line-height:1.2;
  }
  .lh-tagline { font-size:.73rem; color:var(--muted); margin-top:.25rem; letter-spacing:.03em; }
  .lh-addr    { font-size:.76rem; color:var(--muted); margin-top:.6rem; line-height:1.65; }

  .lh-right { text-align:right; }
  .lh-doc-label {
    font-size:.65rem; font-weight:800; text-transform:uppercase;
    letter-spacing:.12em; color:var(--muted); margin-bottom:.2rem;
  }
  .lh-ref {
    font-size:1.5rem; font-weight:900; color:var(--text); letter-spacing:-.4px;
    font-family:'SFMono-Regular',Consolas,monospace;
  }
  .lh-date { font-size:.8rem; color:var(--muted); margin-top:.3rem; }

  /* ── Address + Terms band ────────────────────────────────────────── */
  .addr-terms {
    display:grid; grid-template-columns:1fr 1fr;
    border-bottom:1px solid var(--border);
  }
  .addr-block {
    padding:1.25rem 2.25rem; border-right:1px solid var(--border);
  }
  .terms-block { padding:1.25rem 2.25rem; }

  .block-label {
    font-size:.65rem; font-weight:800; text-transform:uppercase;
    letter-spacing:.1em; color:var(--muted); margin-bottom:.55rem;
  }
  .block-value { font-size:.88rem; color:var(--text); white-space:pre-wrap; line-height:1.6; font-weight:500; }

  .terms-rows { display:flex; flex-direction:column; gap:.3rem; }
  .term-row   { display:flex; gap:.5rem; font-size:.83rem; }
  .term-key   { color:var(--muted); min-width:135px; flex-shrink:0; }
  .term-val   { color:var(--text); font-weight:600; }
  .term-val-empty { color:#ccc; font-weight:400; }

  /* ── Line items table ────────────────────────────────────────────── */
  .items-wrap { overflow-x:auto; }

  .q-table { width:100%; border-collapse:collapse; font-size:.86rem; }
  .q-table thead { background:#f5f7ff; }
  .q-table th {
    padding:.7rem 1rem; text-align:left; font-size:.67rem;
    font-weight:800; text-transform:uppercase; letter-spacing:.08em;
    color:var(--muted); border-bottom:1px solid var(--border);
    white-space:nowrap;
  }
  .q-table th.r { text-align:right; }
  .q-table td { padding:.7rem 1rem; border-bottom:1px solid #f0f0f6; vertical-align:middle; }

  /* Assembly header rows */
  .row-hdr         { background:#eef2ff; }
  .row-hdr td      { font-weight:700; color:#1e3a8a; border-bottom:1px solid #dbeafe; }
  .row-hdr .c-sno  { color:#93c5fd; font-weight:400; }
  .row-hdr .c-dash { color:#93c5fd; text-align:right; }

  /* Item rows */
  .row-item:last-of-type td { border-bottom:none; }

  /* Totals */
  .row-space td   { padding:.15rem 0; border-bottom:none; background:#fff; }
  .row-grandtotal { background:#eef2ff; }
  .row-grandtotal td {
    padding:.95rem 1rem; border-top:2px solid var(--brand);
    font-size:1rem; font-weight:800; color:var(--brand);
  }
  .row-grandtotal .c-total {
    font-family:'SFMono-Regular',Consolas,monospace;
    font-size:1.1rem;
  }

  /* Column widths / alignment */
  .c-sno    { width:3rem;  text-align:center; color:var(--muted); font-size:.8rem; }
  .c-partno { width:8rem;  font-family:'SFMono-Regular',Consolas,monospace; font-size:.78rem; color:var(--muted); }
  .c-desc   { min-width:220px; }
  .c-qty    { width:5rem;  text-align:right; }
  .c-unit   { width:4rem;  color:var(--muted); font-size:.8rem; }
  .c-price  { width:9rem;  text-align:right; font-family:'SFMono-Regular',Consolas,monospace; }
  .c-total  { width:9rem;  text-align:right; font-family:'SFMono-Regular',Consolas,monospace; font-weight:600; }

  /* Indent nested items via description padding */
  .indent-1 { padding-left:1.8rem !important; }
  .indent-2 { padding-left:3.2rem !important; }
  .indent-3 { padding-left:4.6rem !important; }

  /* ── Document footer / T&C ───────────────────────────────────────── */
  .doc-footer {
    padding:1.25rem 2.25rem; border-top:1px solid var(--border);
    background:#fafafa; font-size:.76rem; color:var(--muted); line-height:1.7;
  }
  .doc-footer strong { color:var(--text); font-size:.78rem; }

  /* ── Print optimisation ──────────────────────────────────────────── */
  @media print {
    nav, .page-top, .doc-actions, footer { display:none !important; }
    body  { background:#fff; }
    .doc-wrap { max-width:100%; }
    .quotation-doc { border:none; box-shadow:none; }
  }

  /* ── Responsive ──────────────────────────────────────────────────── */
  @media(max-width:700px){
    .addr-terms { grid-template-columns:1fr; }
    .addr-block { border-right:none; border-bottom:1px solid var(--border); }
    .letterhead { flex-direction:column; }
    .lh-right   { text-align:left; }
    .c-price    { display:none; }
  }
</style>
"""


# =============================================================================
# HELPERS
# =============================================================================

def _next_ref() -> str:
    """Generate QT-0001, QT-0002… based on current quotation count."""
    n = len(STORE["quotations"]) + 1
    return f"QT-{n:04d}"


def _product_options_html() -> str:
    """
    Build <option> tags for the product dropdown on the create form.
    Stores name + part_no in data-attributes so JS can display them
    in the selection list without querying the server.
    """
    opts = '<option value="">&#8212; select a product &#8212;</option>'
    for pid, p in STORE["products"].items():
        ptype = p.get("type", "standalone")
        tag   = ptype[:3].upper()
        label = f'[{tag}] {p["name"]}  ({p["part_no"]})'
        # Escape quotes in data attributes — product names shouldn't have them
        # but be safe with str.replace.
        safe_name   = p["name"].replace('"', '&quot;')
        safe_partno = p["part_no"].replace('"', '&quot;')
        opts += (
            f'<option value="{pid}"'
            f' data-name="{safe_name}"'
            f' data-partno="{safe_partno}"'
            f' data-ptype="{ptype}">'
            f'{label}</option>'
        )
    return opts


def _fmt_qty(q: float) -> str:
    """Display qty as integer when whole, else up to 4 sig figs."""
    if q == int(q):
        return str(int(q))
    return f"{q:g}"


def _term_val(v: str) -> str:
    """Render a terms field value, or a greyed dash if empty."""
    stripped = v.strip() if v else ""
    if stripped:
        return f'<span class="term-val">{stripped}</span>'
    return '<span class="term-val-empty">—</span>'


def expand_product(
    product_id: str,
    qty: float,
    depth: int = 0,
    visited: frozenset = frozenset(),
) -> list[dict]:
    """
    Recursively flatten a product into ordered line-item dicts.

    Assembly  → header row (no price) + children expanded at (depth+1)
                Child quantity = parent_qty × child.qty
    Leaf      → single item row: price = base_price, total = price × qty

    Parameters
    ----------
    product_id : str
    qty        : float  — quantity of this product in the parent context
    depth      : int    — 0 for root-level selections, +1 per assembly nesting
    visited    : frozenset[str]  — IDs on current path; prevents infinite loops

    Returns
    -------
    list[dict] with keys:
        type     : "header" | "item"
        name     : str
        part_no  : str
        qty      : float
        unit     : str
        price    : float   (0.0 for headers)
        total    : float   (0.0 for headers)
        depth    : int
    """
    p = STORE["products"].get(product_id)
    if p is None:
        return []                               # deleted product — skip silently

    ptype    = p.get("type", "standalone")
    children = p.get("children", [])

    if ptype == "assembly":
        # ── Header row ──────────────────────────────────────────────
        rows: list[dict] = [{
            "type":    "header",
            "name":    p["name"],
            "part_no": p["part_no"],
            "qty":     qty,
            "unit":    p["unit"],
            "price":   0.0,
            "total":   0.0,
            "depth":   depth,
        }]

        # ── Recurse into children (cycle-safe) ──────────────────────
        if product_id not in visited:
            new_visited = visited | {product_id}
            for child in children:
                rows.extend(expand_product(
                    child["product_id"],
                    qty * child["qty"],          # quantity propagation
                    depth + 1,
                    new_visited,
                ))
        return rows

    else:
        # ── Leaf item row ────────────────────────────────────────────
        unit_price = p["base_price"]
        return [{
            "type":    "item",
            "name":    p["name"],
            "part_no": p["part_no"],
            "qty":     qty,
            "unit":    p["unit"],
            "price":   unit_price,
            "total":   unit_price * qty,
            "depth":   depth,
        }]


# =============================================================================
# ROUTES
# =============================================================================

@quotation_bp.route("/")
def list_quotations():
    """
    GET /quotation
    Displays all saved quotations in a summary table (newest first).
    """
    quotations = STORE["quotations"]
    create_url = url_for("quotation.create_quotation")
    dash_url   = url_for("dashboard.index")
    msg        = request.args.get("msg")
    msg_type   = request.args.get("type", "success")

    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {msg}</div>'

    if quotations:
        # Sort newest first (insertion order in Python 3.7+ dicts reflects
        # creation order, so reversed() gives newest first)
        rows_html = ""
        for qid, q in reversed(list(quotations.items())):
            view_url = url_for("quotation.view_quotation", id=qid)
            # First line of "To" as customer display
            customer = (q.get("to") or "").strip().splitlines()[0] or "—"
            item_count = sum(1 for r in q["line_items"] if r["type"] == "item")
            rows_html += f"""
            <tr>
              <td class="td-ref">{q['ref']}</td>
              <td class="td-date">{q['date']}</td>
              <td class="td-cust">{customer}</td>
              <td class="td-items col-hide">{item_count} line item{"s" if item_count != 1 else ""}</td>
              <td class="td-total">&#8377;&nbsp;{q['grand_total']:,.0f}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>
            """

        table_html = f"""
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ref No.</th>
                <th>Date</th>
                <th>Customer</th>
                <th class="col-hide">Items</th>
                <th>Grand Total</th>
                <th></th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2.2rem;">&#128196;</div>
          <strong>No quotations yet</strong>
          <p>Create your first quotation to get started.</p>
          <a href="{create_url}" class="btn" style="display:inline-block;margin-top:1.25rem;">
            + Create Quotation
          </a>
        </div>
        """

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>Quotations &#8212; QMS</title>
      {BASE_STYLES}
      {QUOTATION_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        {alert_html}
        <div class="page-top">
          <h1>Quotation <span>Register</span>
            <span style="font-size:.75rem;font-weight:500;color:var(--muted);margin-left:.6rem;">
              {len(quotations)} total
            </span>
          </h1>
          <div style="display:flex;gap:.75rem;">
            <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
            <a href="{create_url}" class="btn">+ Create Quotation</a>
          </div>
        </div>
        {table_html}
        <footer>
          <p>QMS Platform &nbsp;&#183;&nbsp; Quotation Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return render_template_string(template)


@quotation_bp.route("/create", methods=["GET", "POST"])
def create_quotation():
    """
    GET  /quotation/create  — render the creation form.
    POST /quotation/create  — validate, expand products, save, redirect to view.

    Product selection is driven by vanilla JS:
      User picks product from <select> + enters qty → "Add" button appends a row.
      Each row carries:
        <input type="hidden" name="product_id" …>
        <input type="number" name="product_qty" …>

    Flask reads parallel lists via request.form.getlist().
    """
    from product import ensure_demo_products
    ensure_demo_products()

    products  = STORE["products"]
    error     = None
    form      = request.form  # shorthand for re-render after error

    # ──────────────────────────────────────────────────────────────────
    # POST — process submission
    # ──────────────────────────────────────────────────────────────────
    if request.method == "POST":
        # ── Header fields ─────────────────────────────────────────────
        to_addr          = form.get("to",               "").strip()
        buyer_ref        = form.get("buyer_ref",        "").strip()
        other_ref        = form.get("other_ref",        "").strip()
        q_date           = form.get("date",             str(_date.today()))
        payment_terms    = form.get("payment_terms",    "").strip()
        delivery_terms   = form.get("delivery_terms",   "").strip()
        dispatch_through = form.get("dispatch_through", "").strip()
        validity         = form.get("validity",         "").strip()
        incoterms        = form.get("incoterms",        "").strip()

        # ── Product selections ────────────────────────────────────────
        raw_ids  = form.getlist("product_id")
        raw_qtys = form.getlist("product_qty")

        # ── Validation ────────────────────────────────────────────────
        if not to_addr:
            error = "Please fill in the 'To' (customer) field."

        selections: list[dict] = []
        if not error:
            if not raw_ids or all(pid.strip() == "" for pid in raw_ids):
                error = "Please add at least one product to the quotation."
            else:
                for pid, qty_raw in zip(raw_ids, raw_qtys):
                    pid = pid.strip()
                    if not pid:
                        continue
                    if pid not in products:
                        error = f"Product ID '{pid[:16]}…' no longer exists in the catalog."
                        break
                    try:
                        qty = float(qty_raw)
                        if qty <= 0:
                            raise ValueError
                    except (ValueError, TypeError):
                        name = products[pid]["name"]
                        error = f"Invalid quantity for '{name}'. Must be a positive number."
                        break
                    selections.append({"product_id": pid, "qty": qty})

                if not error and not selections:
                    error = "Please add at least one product to the quotation."

        # ── Expand + save ──────────────────────────────────────────────
        if not error:
            line_items: list[dict] = []
            for sel in selections:
                line_items.extend(
                    expand_product(sel["product_id"], sel["qty"])
                )

            grand_total = sum(r["total"] for r in line_items if r["type"] == "item")

            qid = str(uuid.uuid4())
            STORE["quotations"][qid] = {
                "id":              qid,
                "ref":             _next_ref(),
                "to":              to_addr,
                "buyer_ref":       buyer_ref,
                "other_ref":       other_ref,
                "date":            q_date,
                "payment_terms":   payment_terms,
                "delivery_terms":  delivery_terms,
                "dispatch_through":dispatch_through,
                "validity":        validity,
                "incoterms":       incoterms,
                "selections":      selections,
                "line_items":      line_items,
                "grand_total":     grand_total,
            }
            return redirect(url_for("quotation.view_quotation", id=qid))

    # ──────────────────────────────────────────────────────────────────
    # GET (or POST with error) — render form
    # ──────────────────────────────────────────────────────────────────
    list_url    = url_for("quotation.list_quotations")
    error_html  = (
        f'<div class="alert alert-error">&#10007; {error}</div>'
        if error else ""
    )
    today_str   = str(_date.today())
    prod_opts   = _product_options_html()

    # Restore selected product rows after a validation error.
    # We render them server-side; JS will handle future interactions.
    restored_rows = ""
    raw_ids  = form.getlist("product_id")  # empty on GET
    raw_qtys = form.getlist("product_qty")
    for pid, qty_raw in zip(raw_ids, raw_qtys):
        pid = pid.strip()
        if not pid or pid not in products:
            continue
        p    = products[pid]
        name = p["name"].replace('"', '&quot;')
        restored_rows += f"""
        <div class="sel-row">
          <input type="hidden" name="product_id" value="{pid}"/>
          <div>
            <div class="sel-info-name">{p['name']}</div>
            <div class="sel-info-partno">{p['part_no']}</div>
          </div>
          <input type="number" name="product_qty" class="sel-qty-input"
                 value="{qty_raw}" min="1" step="1"/>
          <button type="button" class="btn-remove-sel"
                  onclick="this.closest('.sel-row').remove(); _updateEmpty();">
            &#215;
          </button>
        </div>
        """

    empty_display = "none" if restored_rows else "block"

    # Restore scalar form fields
    def _fv(key, default=""):
        return form.get(key, default)

    # Build a <select> with the correct option pre-selected
    def _sel(name, options, default):
        cur = _fv(name, default)
        inner = "".join(
            f'<option{"  selected" if o == cur else ""}>{o}</option>'
            for o in options
        )
        return f'<select id="{name}" name="{name}">{inner}</select>'

    _PAY_OPTS = [
        "100% Advance", "100% Against Proforma Invoice",
        "30% Advance, Balance Before Dispatch", "30% Advance, 70% Against Delivery",
        "50% Advance, Balance Before Dispatch",
        "90% Against Proforma, 10% After Installation",
        "LC at Sight", "LC 30 Days",
        "45 Days Credit", "60 Days Credit", "90 Days Credit",
        "Against Delivery (COD)", "Part Advance + Balance Against Dispatch",
    ]
    _DEL_OPTS = [
        "Ex-Works", "Ex-Panvel Godown", "Ex-Mumbai Warehouse",
        "FOR Destination", "FOB Mumbai", "CIF Destination",
        "Door Delivery", "Ex-Factory", "Ex-Stock",
    ]
    _DIS_OPTS = [
        "By Road Transport", "By Air Cargo", "By Courier", "By Hand Delivery",
        "Through Client Transporter", "In Client Scope", "Self Pickup",
        "Transporter \u2013 VRL Logistics", "Transporter \u2013 TCI Freight",
        "Transporter \u2013 DTDC Cargo", "Transporter \u2013 Blue Dart",
    ]
    _INC_OPTS = ["EXW", "FOB", "CIF", "CFR", "DAP", "DDP", "FCA", "FOR"]
    _VAL_OPTS = [
        "7 Days", "10 Days", "15 Days", "30 Days",
        "45 Days", "60 Days", "90 Days", "Until Stock Lasts",
    ]

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>New Quotation &#8212; QMS</title>
      {BASE_STYLES}
      {QUOTATION_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        <div class="page-top">
          <h1>Create <span>Quotation</span></h1>
          <a href="{list_url}" class="btn btn-ghost">&#8592; Back</a>
        </div>

        {error_html}

        <form method="POST" action="" id="quotation-form">

          <!-- ── Section 1: Buyer Information ────────────────────── -->
          <div class="form-section">
            <div class="form-section-title">&#128203;&nbsp; Buyer Information</div>
            <div class="form-grid">

              <div class="form-group full">
                <div class="field-label-row">
                  <label for="to">To (Customer Name &amp; Address) *</label>
                  <button type="button" class="btn-tpl" onclick="fillToTemplate()">
                    &#128196; Use Template
                  </button>
                </div>
                <textarea id="to" name="to" rows="6"
                  placeholder="M/s. ABC Industries Pvt. Ltd.&#10;Address Line 1, Address Line 2&#10;City, State &#8211; PIN&#10;GSTIN:&#10;Contact Person:&#10;Phone:"
                  required>{_fv('to')}</textarea>
              </div>

              <div class="form-group">
                <label for="buyer_ref">Buyer Ref. No.</label>
                <input type="text" id="buyer_ref" name="buyer_ref"
                       value="{_fv('buyer_ref')}"
                       placeholder="PO-2024-0789" autocomplete="off"/>
              </div>

              <div class="form-group">
                <label for="date">Date *</label>
                <input type="date" id="date" name="date"
                       value="{_fv('date', today_str)}" required/>
              </div>

              <div class="form-group full">
                <label for="other_ref">Other Reference</label>
                <input type="text" id="other_ref" name="other_ref"
                       value="{_fv('other_ref')}"
                       placeholder="As per your enquiry / Against your RFQ…" autocomplete="off"/>
              </div>

            </div><!-- /.form-grid -->
          </div>

          <!-- ── Section 2: Commercial Terms ──────────────────────── -->
          <div class="form-section">
            <div class="form-section-title">&#128221;&nbsp; Commercial Terms</div>
            <div class="form-grid">

              <div class="form-group">
                <label for="payment_terms">Mode / Terms of Payment</label>
                {_sel('payment_terms', _PAY_OPTS, '100% Against Proforma Invoice')}
              </div>

              <div class="form-group">
                <label for="delivery_terms">Terms of Delivery</label>
                {_sel('delivery_terms', _DEL_OPTS, 'Ex-Works')}
              </div>

              <div class="form-group">
                <label for="dispatch_through">Dispatch Through</label>
                {_sel('dispatch_through', _DIS_OPTS, 'By Road Transport')}
              </div>

              <div class="form-group">
                <label for="incoterms">Incoterms</label>
                {_sel('incoterms', _INC_OPTS, 'EXW')}
              </div>

              <div class="form-group">
                <label for="validity">Validity</label>
                {_sel('validity', _VAL_OPTS, '15 Days')}
              </div>

            </div><!-- /.form-grid -->
          </div>

          <!-- ── Section 3: Products / Assemblies ─────────────────── -->
          <div class="form-section">
            <div class="form-section-title">&#128230;&nbsp; Products / Assemblies</div>

            <!-- Picker row: dropdown + qty + Add button -->
            <div class="picker-controls">
              <div class="form-group" style="margin:0;">
                <label for="product-select">Product</label>
                <select id="product-select">{prod_opts}</select>
              </div>
              <div class="form-group" style="margin:0;">
                <label for="add-qty">Qty</label>
                <input type="number" id="add-qty" value="1" min="1" step="1"/>
              </div>
              <div class="form-group" style="margin:0;">
                <label style="visibility:hidden;">Add</label>
                <button type="button" class="btn" onclick="_addProduct()">
                  + Add
                </button>
              </div>
            </div>
            <div id="add-error" class="add-error"></div>

            <!-- Selected product rows (hidden inputs submitted with form) -->
            <div id="product-list">
              {restored_rows}
            </div>
            <div id="empty-notice" style="display:{empty_display};">
              No products added yet. Select a product above and click&nbsp;<strong>+ Add</strong>.
            </div>

          </div><!-- /.form-section -->

          <div class="form-actions">
            <button type="submit" class="btn">&#10003;&nbsp; Generate Quotation</button>
            <a href="{list_url}" class="btn btn-ghost">Cancel</a>
          </div>

        </form>

        <footer>
          <p>QMS Platform &nbsp;&#183;&nbsp; Quotation Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>

      <script>
        /* ── Fill "To" address with a blank template ─────────────── */
        function fillToTemplate() {{
          const ta = document.getElementById('to');
          if (!ta.value.trim()) {{
            ta.value = 'Company Name\\nAddress Line 1\\nAddress Line 2\\nCity, State \u2013 PIN\\nGSTIN: \\nContact Person: \\nPhone: \\nEmail: ';
          }}
        }}

        /* ── Vanilla JS product picker ────────────────────────────── */

        function _addProduct() {{
          const sel    = document.getElementById('product-select');
          const qtyEl  = document.getElementById('add-qty');
          const errEl  = document.getElementById('add-error');
          const list   = document.getElementById('product-list');
          const empty  = document.getElementById('empty-notice');

          errEl.style.display = 'none';

          const pid = sel.value;
          if (!pid) {{
            errEl.textContent = 'Please select a product.';
            errEl.style.display = 'block';
            return;
          }}

          const qty = parseInt(qtyEl.value, 10);
          if (!qty || qty < 1) {{
            errEl.textContent = 'Quantity must be at least 1.';
            errEl.style.display = 'block';
            return;
          }}

          const opt    = sel.options[sel.selectedIndex];
          const name   = opt.getAttribute('data-name')   || opt.text;
          const partno = opt.getAttribute('data-partno') || '';

          // ── Build row DOM ──────────────────────────────────────────
          const row = document.createElement('div');
          row.className = 'sel-row';

          // Hidden product_id
          const hidId   = document.createElement('input');
          hidId.type    = 'hidden';
          hidId.name    = 'product_id';
          hidId.value   = pid;

          // Product info display
          const info = document.createElement('div');
          info.innerHTML = (
            '<div class="sel-info-name">' + name   + '</div>' +
            '<div class="sel-info-partno">' + partno + '</div>'
          );

          // Qty input (editable after adding)
          const qtyIn   = document.createElement('input');
          qtyIn.type    = 'number';
          qtyIn.name    = 'product_qty';
          qtyIn.value   = qty;
          qtyIn.min     = '1';
          qtyIn.step    = '1';
          qtyIn.className = 'sel-qty-input';

          // Remove button
          const rmBtn   = document.createElement('button');
          rmBtn.type    = 'button';
          rmBtn.className = 'btn-remove-sel';
          rmBtn.textContent = '\u00d7';
          rmBtn.onclick = function() {{
            row.remove();
            _updateEmpty();
          }};

          row.appendChild(hidId);
          row.appendChild(info);
          row.appendChild(qtyIn);
          row.appendChild(rmBtn);
          list.appendChild(row);

          empty.style.display = 'none';

          // Reset controls
          sel.value      = '';
          qtyEl.value    = '1';
        }}

        function _updateEmpty() {{
          const list  = document.getElementById('product-list');
          const empty = document.getElementById('empty-notice');
          empty.style.display = (list.children.length === 0) ? 'block' : 'none';
        }}

        /* ── Guard empty submission ──────────────────────────────── */
        document.getElementById('quotation-form').addEventListener('submit', function(e) {{
          const list = document.getElementById('product-list');
          if (list.children.length === 0) {{
            e.preventDefault();
            const errEl = document.getElementById('add-error');
            errEl.textContent = 'Add at least one product before generating the quotation.';
            errEl.style.display = 'block';
            errEl.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          }}
        }});
      </script>

    </body>
    </html>
    """
    return render_template_string(template)


@quotation_bp.route("/view/<id>")
def view_quotation(id: str):
    """
    GET /quotation/view/<id>

    Renders the saved quotation as a formatted document:
      - Letterhead (static company info + ref number)
      - Customer address + terms grid
      - Expanded line-items table (assembly headers + priced items)
      - Grand total
      - Standard T&C footer

    Assembly header rows are rendered with a blue tint, no price.
    Item rows carry S.No (counted independently of headers), unit price, total.
    Depth-based indentation in the Description column shows nesting visually.
    """
    q = STORE["quotations"].get(id)
    if not q:
        return redirect(url_for(
            "quotation.list_quotations",
            msg="Quotation not found.",
            type="error",
        ))

    list_url   = url_for("quotation.list_quotations")
    create_url = url_for("quotation.create_quotation")
    line_items = q["line_items"]

    # ── Build table rows ──────────────────────────────────────────────
    sno        = 0
    table_rows = ""

    for row in line_items:
        depth      = row.get("depth", 0)
        indent_cls = f"indent-{min(depth, 3)}" if depth > 0 else ""

        if row["type"] == "header":
            # Assembly grouping header — no serial number, no price
            depth_label = (
                f'<span style="font-size:.72rem;color:#6b7280;margin-left:.4rem;'
                f'font-weight:400;">({_fmt_qty(row["qty"])} {row["unit"]})</span>'
            )
            table_rows += f"""
            <tr class="row-hdr">
              <td class="c-sno">&#9644;</td>
              <td class="c-partno">{row['part_no']}</td>
              <td class="c-desc {indent_cls}">
                {row['name']}{depth_label}
              </td>
              <td class="c-qty c-dash">—</td>
              <td class="c-unit"></td>
              <td class="c-price c-dash">—</td>
              <td class="c-total c-dash">—</td>
            </tr>
            """
        else:
            sno += 1
            table_rows += f"""
            <tr class="row-item">
              <td class="c-sno">{sno}</td>
              <td class="c-partno">{row['part_no']}</td>
              <td class="c-desc {indent_cls}">{row['name']}</td>
              <td class="c-qty">{_fmt_qty(row['qty'])}</td>
              <td class="c-unit">{row['unit']}</td>
              <td class="c-price">&#8377;&nbsp;{row['price']:,.0f}</td>
              <td class="c-total">&#8377;&nbsp;{row['total']:,.0f}</td>
            </tr>
            """

    # ── Grand total row ───────────────────────────────────────────────
    table_rows += f"""
    <tr class="row-space"><td colspan="7"></td></tr>
    <tr class="row-grandtotal">
      <td colspan="4"></td>
      <td colspan="2" style="text-align:right;letter-spacing:.04em;font-size:.82rem;
                             font-weight:700;text-transform:uppercase;">
        Grand Total
      </td>
      <td class="c-total">&#8377;&nbsp;{q['grand_total']:,.0f}</td>
    </tr>
    """

    # ── Terms values (show — if empty) ────────────────────────────────
    def tv(key):
        return _term_val(q.get(key, ""))

    # Customer display — preserve line breaks
    to_display = (q.get("to") or "").strip()

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{q['ref']} &#8212; QMS Quotation</title>
      {BASE_STYLES}
      {VIEW_DOC_STYLES}
    </head>
    <body>
      {_nav()}
      <main>

        <div class="page-top">
          <h1>Quotation <span>{q['ref']}</span></h1>
          <div style="display:flex;gap:.75rem;">
            <a href="{list_url}" class="btn btn-ghost">&#8592; All Quotations</a>
            <a href="{create_url}" class="btn btn-ghost">+ New</a>
            <button class="btn" onclick="window.print()">&#128438; Print</button>
          </div>
        </div>

        <div class="doc-wrap">
          <div class="quotation-doc">

            <!-- ── Letterhead ─────────────────────────────────────── -->
            <div class="letterhead">
              <div>
                <div class="lh-name">{COMPANY_NAME}</div>
                <div class="lh-tagline">{COMPANY_TAGLINE}</div>
                <div class="lh-addr">
                  {COMPANY_ADDR}<br>
                  {COMPANY_PHONE}<br>
                  {COMPANY_EMAIL} &nbsp;&#183;&nbsp; GSTIN: {COMPANY_GSTIN}
                </div>
              </div>
              <div class="lh-right">
                <div class="lh-doc-label">Quotation</div>
                <div class="lh-ref">{q['ref']}</div>
                <div class="lh-date">{q['date']}</div>
                {"" if not q.get('buyer_ref') else f'<div class="lh-date" style="margin-top:.25rem;">Buyer Ref: {q["buyer_ref"]}</div>'}
              </div>
            </div>

            <!-- ── Address + Terms ────────────────────────────────── -->
            <div class="addr-terms">
              <div class="addr-block">
                <div class="block-label">To</div>
                <div class="block-value">{to_display}</div>
              </div>
              <div class="terms-block">
                <div class="block-label">Terms &amp; Conditions</div>
                <div class="terms-rows">
                  {"" if not q.get('other_ref') else f'<div class="term-row"><span class="term-key">Reference</span><span class="term-val">{q["other_ref"]}</span></div>'}
                  <div class="term-row">
                    <span class="term-key">Payment Terms</span>
                    {tv('payment_terms')}
                  </div>
                  <div class="term-row">
                    <span class="term-key">Delivery Terms</span>
                    {tv('delivery_terms')}
                  </div>
                  <div class="term-row">
                    <span class="term-key">Dispatch Through</span>
                    {tv('dispatch_through')}
                  </div>
                  <div class="term-row">
                    <span class="term-key">Validity</span>
                    {tv('validity')}
                  </div>
                  <div class="term-row">
                    <span class="term-key">Incoterms</span>
                    {tv('incoterms')}
                  </div>
                </div>
              </div>
            </div>

            <!-- ── Line Items ─────────────────────────────────────── -->
            <div class="items-wrap">
              <table class="q-table">
                <thead>
                  <tr>
                    <th class="c-sno">S.No</th>
                    <th class="c-partno">Part No.</th>
                    <th class="c-desc">Description</th>
                    <th class="c-qty r">Qty</th>
                    <th class="c-unit">Unit</th>
                    <th class="c-price r">Unit Price</th>
                    <th class="c-total r">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {table_rows}
                </tbody>
              </table>
            </div>

            <!-- ── Document Footer / T&C ──────────────────────────── -->
            <div class="doc-footer">
              <strong>Notes &amp; Standard Terms:</strong><br>
              1.&nbsp; All prices are in Indian Rupees (&#8377;) and exclusive of GST unless stated.<br>
              2.&nbsp; Goods remain the property of {COMPANY_NAME} until payment is received in full.<br>
              3.&nbsp; This quotation is subject to availability of materials at time of order.<br>
              4.&nbsp; Any disputes are subject to the jurisdiction of courts in Pune, Maharashtra.<br>
              5.&nbsp; For queries regarding this quotation, contact {COMPANY_EMAIL}.
            </div>

          </div><!-- /.quotation-doc -->
        </div><!-- /.doc-wrap -->

        <footer style="margin-top:2.5rem;">
          <p>QMS Platform &nbsp;&#183;&nbsp; Quotation Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return render_template_string(template)