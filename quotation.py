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

Pricing model (matches SEC/Q/25-26/6406 reference document)
------------------------------------------------------------
  depth = 0  (user-selected root items)
      assembly  → type="assembly", price = base_price, total = price × qty
      leaf      → type="item",     price = base_price, total = price × qty

  depth >= 1  (components inside an assembly — BOM breakdown)
      any type  → price = 0.00, total = 0.00

  grand_total = sum(row.total for all rows)
              = sum of depth-0 rows only (children contribute 0)

expand_product row schema
--------------------------
  {
    "type":    "assembly" | "item"
    "name":    str
    "part_no": str
    "hsn":     str     (product.get("hsn", "") — blank if field not on model)
    "qty":     float   (parent_qty × child.qty for nested rows)
    "unit":    str
    "price":   float   (0.0 when depth >= 1)
    "total":   float   (0.0 when depth >= 1)
    "depth":   int
  }
"""

import uuid
from datetime import date as _date
from flask import Blueprint, render_template_string, request, redirect, url_for

from dashboard import BASE_STYLES, _nav
from store import STORE

# ── Blueprint ─────────────────────────────────────────────────────────────────
quotation_bp = Blueprint("quotation", __name__, url_prefix="/quotation")


# =============================================================================
# COMPANY IDENTITY  — edit to match your organisation
# =============================================================================
COMPANY_NAME      = "SHANBHAG ENGINEERING COMPANY"
COMPANY_TAGLINE   = "Total Pumping Solutions"
COMPANY_ADDR      = "B/50 Nand Bhavan Industrial Estate, Mahakali Caves Rd, Andheri (E), Mumbai – 400 093"
COMPANY_PHONE     = "91 22 4036 5700 / 5711"
COMPANY_EMAIL     = "info@shanbhags.com"
COMPANY_WEB       = "www.shanbhags.com"
COMPANY_GSTIN     = "27AABFS6095A1ZA"
COMPANY_PAN       = "AABFS6095A"
COMPANY_BRANCHES  = "Pune, Surat"
COMPANY_WAREHOUSE = (
    "Building BB1, Big Depot, Opp. Sai Krupa Hotel, Village Khushivali (Shirdhon), "
    "Mumbai–Goa Highway, Taluka Panvel, District Raigad, Maharashtra – 410 221"
)
COMPANY_SIGNATORY = "Authorised Signatory"

# Standard T&C — edit as required
COMPANY_TERMS = [
    "The above prices are ex our Panvel Godown assembled unpacked condition.",
    "GST – 18% on the pumpset and Fuel Tank, 28% on Battery.",
    "Delivery – 3–4 weeks from the date of clear PO with advance.",
    "Payment – 30% advance with PO, balance against Proforma Invoice prior to Delivery. "
        "(Delivery schedule will commence from Date of receipt of Advance / Date of receipt of "
        "approved Documents / Date of Purchase Order whichever is later.)",
    "Transportation – To your a/c.",
    "KFE engine sets will need to be revalidated if commissioned beyond 3 months from the "
        "date of our invoice by authorized KBL service engineer. This will involve mandatory "
        "change of fuel, oil filters & check-up of fuel pump for freeness. If commissioned "
        "beyond 12 months from invoice date, air filter change & calibration of fuel pump will "
        "also need to be done. Costs for the same will be borne by customer. This is mandatory "
        "for engine-set warranty to be valid.",
    "Any commissioning call will be given minimum 5 working days in advance post check-list "
        "confirmation. Check list for site readiness to be carefully noted for 100% compliance.",
    "First visit for supervision of commissioning will be done on FOC basis after confirmation "
        "of site readiness. Any further visits due to site non-readiness will be charged on per "
        "man-day basis.",
    "Any short supplies from our end must be brought to our notice within 3 working days from "
        "receipt of materials. Delay in such information cannot be accepted for part replacement.",
    "For any rectifications required for bare pump, motor, monoblock pumps within warranty "
        "period which requires transport to authorized service center — the to & fro freight "
        "costs will be borne by customer.",
    "Fuel Pipe Inlet / Outlet & Rain Cap along with the Diesel Engine (for silencer) is not "
        "in KBL Scope of supply.",
    "Factory-built pump sets commissioned in absence of KBL service engineers are voided of warranty.",
    "Witness & Inspection – We can offer witnessed performance tests of Electric Motor Driven "
        "pumpsets (upto 120 hp) & Engine driven pumpsets (Except Monoblock pump, KCIL & KVM) "
        "at our Panvel Warehouse Test Facility at additional prices as required.",
    "Warranty – For pumps: 18 months from the Invoice Date or 12 months from commissioning "
        "date whichever is earlier. For boughtouts as mech seal, motors, engines, etc. warranty "
        "is limited to 12 months from invoice date only. No warranty on electronic components.",
    "For all motor-driven Pumps – As per KBL Policy, commissioning will be in customer scope "
        "& it should be as per the standard KBL Checklist.",
    "Standard Force Majeure clause is applicable.",
    "Be informed that we will raise a debit note of Rs 900.00 + GST each time your payment "
        "cheque bounces (for any reason) when presented for clearing. This will mandatorily need "
        "to be cleared before next supply can be made to you.",
    "Validity – 15 days from the date of offer submitted.",
    "Any statutory deviation in taxes & duties at time of delivery will be to customer's account.",
]


# =============================================================================
# AMOUNT IN WORDS  (Indian numeral system)
# =============================================================================

def _amount_in_words(amount: float) -> str:
    """
    Convert a rupee amount to English words (Indian system).
    1315000  → "INR Thirteen Lakh Fifteen Thousand Only"
    265000   → "INR Two Lakh Sixty Five Thousand Only"
    """
    _ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    _tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _two(n):
        if n == 0:   return ""
        if n < 20:   return _ones[n]
        t = _tens[n // 10]; o = _ones[n % 10]
        return t + (" " + o if o else "")

    def _three(n):
        if n == 0:    return ""
        if n >= 100:
            rest = _two(n % 100)
            return _ones[n // 100] + " Hundred" + (" " + rest if rest else "")
        return _two(n)

    n = int(round(amount))
    if n == 0:
        return "INR Zero Only"

    parts = []
    crore = n // 10_000_000;  n %= 10_000_000
    lakh  = n // 100_000;     n %= 100_000
    thou  = n // 1_000;       n %= 1_000
    if crore: parts.append(_three(crore) + " Crore")
    if lakh:  parts.append(_three(lakh)  + " Lakh")
    if thou:  parts.append(_three(thou)  + " Thousand")
    if n:     parts.append(_three(n))
    return "INR " + " ".join(parts) + " Only"


# =============================================================================
# CSS — list + create pages
# =============================================================================

QUOTATION_STYLES = """
<style>
  .page-top {
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:2rem; flex-wrap:wrap; gap:1rem;
  }
  .page-top h1 { font-size:1.6rem; font-weight:700; letter-spacing:-.4px; }
  .page-top h1 span { color:var(--brand); }

  .alert {
    padding:.85rem 1.2rem; border-radius:8px; font-size:.88rem;
    font-weight:500; margin-bottom:1.5rem;
    display:flex; align-items:center; gap:.5rem;
  }
  .alert-error   { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
  .alert-success { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }

  .table-wrap {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow-sm);
  }
  table { width:100%; border-collapse:collapse; font-size:.9rem; }
  thead { background:var(--bg); border-bottom:1px solid var(--border); }
  th {
    padding:.85rem 1.25rem; text-align:left; font-size:.75rem;
    font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
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

  .empty-state {
    text-align:center; padding:4rem 2rem; color:var(--muted);
    background:var(--surface); border:1px dashed var(--border); border-radius:var(--radius);
  }
  .empty-state p { margin-top:.5rem; font-size:.9rem; }

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
    box-shadow:0 0 0 3px rgba(79,70,229,.12); background:#fff;
  }
  textarea { resize:vertical; min-height:90px; }

  .picker-controls {
    display:grid; grid-template-columns:1fr 100px auto;
    gap:.65rem; align-items:end; margin-bottom:1.1rem;
  }
  .picker-controls select, .picker-controls input { margin:0; }

  .add-error {
    font-size:.82rem; color:#b91c1c; background:#fef2f2;
    border:1px solid #fecaca; border-radius:6px;
    padding:.35rem .8rem; margin-top:.5rem; display:none;
  }

  #product-list { display:flex; flex-direction:column; gap:.45rem; margin-top:.75rem; }

  .sel-row {
    display:grid; grid-template-columns:1fr 110px 36px;
    gap:.6rem; align-items:center;
    background:var(--bg); border:1px solid var(--border);
    border-radius:8px; padding:.5rem .9rem; transition:border-color .14s;
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
  .sel-qty-input:focus { border-color:var(--brand); }
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
    font-size:.88rem; border:1.5px dashed var(--border); border-radius:8px; background:var(--bg);
  }
  .form-actions { display:flex; gap:.75rem; margin-top:1.75rem; align-items:center; }

  .field-label-row {
    display:flex; align-items:center; justify-content:space-between; margin-bottom:.25rem;
  }
  .btn-tpl {
    font-family:var(--font); font-size:.73rem; font-weight:600;
    color:var(--brand); background:var(--brand-lt); border:1px solid #c7d2fe;
    border-radius:6px; padding:.28rem .65rem; cursor:pointer; transition:background .14s;
  }
  .btn-tpl:hover { background:#c7d2fe; }

  @media(max-width:700px){
    .form-grid { grid-template-columns:1fr; }
    .form-group.full { grid-column:1; }
    .picker-controls { grid-template-columns:1fr; }
    .sel-row { grid-template-columns:1fr 85px 34px; }
    th, td { padding:.7rem .85rem; }
    .col-hide { display:none; }
  }
</style>
"""


# =============================================================================
# CSS — quotation document view  (matches SEC PDF layout)
# =============================================================================

VIEW_DOC_STYLES = """
<style>
  .doc-outer { max-width:1060px; margin:0 auto; }

  /* ── Document shell ── */
  .quotation-doc {
    background:#fff;
    border:1px solid #c8c8c8;
    box-shadow:0 4px 32px rgba(0,0,0,.10);
    font-family:'Times New Roman', Times, serif;
    font-size:10.5pt; color:#111;
  }

  /* ── Letterhead ── */
  .lh-band {
    border-bottom:2px solid #111;
    padding:12px 20px 10px;
    display:flex; justify-content:space-between; align-items:flex-start;
    gap:1rem;
  }
  .lh-logo-name {
    font-family:Arial, sans-serif;
    font-size:18pt; font-weight:900;
    color:#1a1a8c; letter-spacing:.4px; line-height:1.15;
  }
  .lh-tagline {
    font-family:Arial, sans-serif;
    font-size:8.5pt; color:#555; margin-top:3px; letter-spacing:.5px;
  }
  .lh-logo-right {
    text-align:right; font-family:Arial, sans-serif;
    font-size:8pt; color:#333; line-height:1.6;
  }
  .lh-reg-addr {
    border-top:1px solid #bbb; margin:0 20px;
    padding:4px 0 5px;
    font-family:Arial, sans-serif; font-size:7.5pt; color:#555;
    text-align:center;
  }

  /* ── Title bar ── */
  .doc-title-bar {
    text-align:center;
    font-family:Arial, sans-serif; font-size:13pt; font-weight:700;
    padding:5px 0 6px; border-bottom:1px solid #111;
    letter-spacing:.6px;
  }

  /* ── Header info box ── */
  .header-box {
    display:grid; grid-template-columns:45% 55%;
    border-bottom:1px solid #111;
  }
  .hb-to {
    border-right:1px solid #111;
    padding:10px 14px 12px;
  }
  .hb-to-label {
    font-family:Arial, sans-serif; font-size:8pt;
    font-weight:700; margin-bottom:4px; display:block;
  }
  .hb-to-value {
    font-size:9.5pt; line-height:1.6; white-space:pre-wrap;
  }
  .hb-meta { padding:0; }

  /* ── Meta grid (2 columns inside right panel) ── */
  .meta-grid {
    display:grid; grid-template-columns:1fr 1fr; height:100%;
  }
  .meta-cell {
    padding:5px 10px;
    border-bottom:1px solid #ddd;
    border-right:1px solid #ddd;
    font-size:8.5pt; line-height:1.5;
  }
  .meta-cell:nth-child(even) { border-right:none; }
  /* Last two cells – no bottom border */
  .meta-cell:nth-last-child(-n+2) { border-bottom:none; }
  .meta-cell-label {
    font-family:Arial, sans-serif; font-weight:700;
    font-size:7.5pt; color:#555; display:block; margin-bottom:1px;
  }
  .meta-cell-value  { font-size:9pt; font-weight:600; color:#111; }
  .meta-cell-empty  { font-size:9pt; color:#bbb; font-weight:400; }

  /* ── Line-items table ── */
  .items-wrap { overflow-x:auto; }

  .q-table {
    width:100%; border-collapse:collapse;
    font-size:9pt;
    border-top:1px solid #111;
  }
  .q-table thead { background:#eeeeee; }
  .q-table th {
    padding:5px 7px; text-align:left;
    font-family:Arial, sans-serif; font-size:8pt; font-weight:700;
    border:1px solid #999; white-space:nowrap;
  }
  .q-table th.r { text-align:right; }
  .q-table td {
    padding:4px 7px; border:1px solid #ccc; vertical-align:top;
  }

  /* Assembly (group) rows — bold, lightly tinted */
  .row-assembly td { font-weight:700; background:#f6f6f6; }

  /* Plain item rows */
  .row-item td { background:#fff; }

  /* Column sizing */
  .c-sno    { width:3rem;   text-align:center; white-space:nowrap; }
  .c-partno { width:8.5rem; font-family:'Courier New',monospace; font-size:7.5pt; word-break:break-all; }
  .c-desc   { min-width:180px; }
  .c-hsn    { width:6rem;   text-align:center; font-size:7.5pt; }
  .c-qty    { width:3.5rem; text-align:right; }
  .c-unit   { width:3rem;   text-align:center; }
  .c-price  { width:8rem;   text-align:right; font-family:'Courier New',monospace; white-space:nowrap; }
  .c-total  { width:8.5rem; text-align:right; font-family:'Courier New',monospace; font-weight:700; white-space:nowrap; }

  /* Nested row indentation */
  .indent-1 { padding-left:1.5rem !important; }
  .indent-2 { padding-left:2.8rem !important; }
  .indent-3 { padding-left:4.0rem !important; }

  /* ── Totals row ── */
  .row-total td {
    font-family:Arial, sans-serif; font-weight:700; font-size:9.5pt;
    background:#eeeeee; border:1px solid #999; padding:5px 7px;
  }
  .row-total .c-qty   { text-align:right; }
  .row-total .c-total { text-align:right; font-family:'Courier New',monospace; }

  /* ── Amount in words ── */
  .amount-words {
    border-left:1px solid #ccc; border-right:1px solid #ccc; border-bottom:1px solid #ccc;
    padding:5px 12px; font-size:8.5pt;
    font-family:Arial, sans-serif; background:#fafafa;
  }

  /* ── T&C section ── */
  .tnc-section {
    border-top:2px solid #111;
    padding:12px 20px 16px;
    font-family:Arial, sans-serif;
    font-size:8pt; line-height:1.65;
  }
  .tnc-title {
    font-weight:700; font-size:9pt; margin-bottom:7px; text-decoration:underline;
  }
  .tnc-ol  { list-style:none; margin:0; padding:0; }
  .tnc-ol li { display:flex; gap:6px; margin-bottom:2px; }
  .tnc-num { flex-shrink:0; font-weight:700; min-width:18px; }

  /* ── Signatory block ── */
  .signatory-block {
    display:flex; justify-content:space-between; align-items:flex-end;
    padding:10px 20px 14px; border-top:1px solid #ccc;
    font-family:Arial, sans-serif; font-size:8pt;
  }
  .sig-gstin { line-height:1.9; }
  .sig-gstin b { font-weight:700; display:inline-block; min-width:55px; }
  .sig-right { text-align:right; }
  .sig-for   { font-weight:700; font-size:9pt; margin-bottom:28px; }
  .sig-name  {
    border-top:1px solid #555; padding-top:3px;
    font-size:8.5pt; text-align:center;
  }
  .sig-note {
    border-top:1px solid #ddd;
    padding:4px 20px 5px; font-family:Arial, sans-serif;
    font-size:7.5pt; color:#666; font-style:italic; text-align:center;
  }
  .page-num {
    text-align:right; font-size:7pt; color:#999;
    padding:3px 20px; border-top:1px solid #eee;
    font-family:Arial, sans-serif;
  }

  /* ── Screen chrome (hidden on print) ── */
  .screen-actions {
    display:flex; gap:.75rem; margin-bottom:1.25rem; flex-wrap:wrap;
    align-items:center; justify-content:space-between;
  }

  /* ── Print ── */
  @media print {
    nav, .page-top, .screen-actions, footer { display:none !important; }
    body { background:#fff; margin:0; }
    .doc-outer { max-width:100%; padding:0; }
    .quotation-doc { border:none; box-shadow:none; }
    .q-table th, .q-table td { font-size:8pt; }
  }

  /* ── Responsive ── */
  @media(max-width:700px){
    .header-box { grid-template-columns:1fr; }
    .hb-to      { border-right:none; border-bottom:1px solid #111; }
    .meta-grid  { grid-template-columns:1fr; }
    .meta-cell:nth-child(even) { border-right:none; }
    .c-price    { display:none; }
    .c-hsn      { display:none; }
    .lh-band    { flex-direction:column; }
  }
</style>
"""


# =============================================================================
# HELPERS
# =============================================================================

def _next_ref() -> str:
    n = len(STORE["quotations"]) + 1
    return f"QT-{n:04d}"


def _product_options_html() -> str:
    opts = '<option value="">&#8212; select a product &#8212;</option>'
    for pid, p in STORE["products"].items():
        ptype     = p.get("type", "standalone")
        tag       = ptype[:3].upper()
        label     = f'[{tag}] {p["name"]}  ({p["part_no"]})'
        safe_name = p["name"].replace('"', '&quot;')
        safe_pno  = p["part_no"].replace('"', '&quot;')
        opts += (
            f'<option value="{pid}"'
            f' data-name="{safe_name}"'
            f' data-partno="{safe_pno}">'
            f'{label}</option>'
        )
    return opts


def _fmt_qty(q: float) -> str:
    return str(int(q)) if q == int(q) else f"{q:g}"


def _mc(label: str, val: str) -> str:
    """Render one meta-cell: label line + value line."""
    v = (val or "").strip()
    val_html = (
        f'<span class="meta-cell-value">{v}</span>'
        if v else
        '<span class="meta-cell-empty">—</span>'
    )
    label_html = f'<span class="meta-cell-label">{label}</span>' if label else ""
    return f'<div class="meta-cell">{label_html}{val_html}</div>'


# =============================================================================
# EXPANSION ENGINE
# =============================================================================

def expand_product(
    product_id: str,
    qty: float,
    depth: int = 0,
    visited: frozenset = frozenset(),
) -> list[dict]:
    """
    Recursively flatten a product into ordered line-item dicts.

    Pricing rule (matches SEC reference quotation layout)
    -------------------------------------------------------
    depth = 0  → price = product.base_price  (user selected this)
    depth >= 1 → price = 0.00               (BOM breakdown; cost included in parent)

    Assembly rows (type="assembly"): bold/tinted in the view, shown with price at root.
    Item rows (type="item"): normal weight.

    Quantity propagation for children: parent_qty × child.qty
    Cycle guard: frozenset visited prevents infinite loops.
    Missing products (deleted, etc.): silently return [].
    """
    p = STORE["products"].get(product_id)
    if p is None:
        return []

    ptype    = p.get("type", "standalone")
    children = p.get("children", [])

    unit_price = p["base_price"] if depth == 0 else 0.0
    total      = unit_price * qty

    rows = [{
        "type":    "assembly" if ptype == "assembly" else "item",
        "name":    p["name"],
        "part_no": p["part_no"],
        "hsn":     p.get("hsn", ""),
        "qty":     qty,
        "unit":    p["unit"],
        "price":   unit_price,
        "total":   total,
        "depth":   depth,
    }]

    if ptype == "assembly" and product_id not in visited:
        new_visited = visited | {product_id}
        for child in children:
            rows.extend(
                expand_product(
                    child["product_id"],
                    qty * child["qty"],
                    depth + 1,
                    new_visited,
                )
            )

    return rows


# =============================================================================
# ROUTES
# =============================================================================

@quotation_bp.route("/")
def list_quotations():
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
        rows_html = ""
        for qid, q in reversed(list(quotations.items())):
            view_url   = url_for("quotation.view_quotation", id=qid)
            customer   = (q.get("to") or "").strip().splitlines()[0] or "—"
            n_priced   = sum(1 for r in q["line_items"] if r["depth"] == 0)
            rows_html += f"""
            <tr>
              <td class="td-ref">{q['ref']}</td>
              <td class="td-date">{q['date']}</td>
              <td class="td-cust">{customer}</td>
              <td class="td-items col-hide">{n_priced} priced line{"s" if n_priced != 1 else ""}</td>
              <td class="td-total">&#8377;&nbsp;{q['grand_total']:,.0f}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>
            """
        table_html = f"""
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Ref No.</th><th>Date</th><th>Customer</th>
              <th class="col-hide">Items</th><th>Grand Total</th><th></th>
            </tr></thead>
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
    <!DOCTYPE html><html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>Quotations &#8212; QMS</title>
      {BASE_STYLES}{QUOTATION_STYLES}
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
        <footer><p>QMS Platform &nbsp;&#183;&nbsp; Quotation Module &nbsp;&#183;&nbsp; In-memory store</p></footer>
      </main>
    </body></html>
    """
    return render_template_string(template)


@quotation_bp.route("/create", methods=["GET", "POST"])
def create_quotation():
    from product import ensure_demo_products
    ensure_demo_products()

    products = STORE["products"]
    error    = None
    form     = request.form

    if request.method == "POST":
        to_addr          = form.get("to",               "").strip()
        buyer_ref        = form.get("buyer_ref",        "").strip()
        other_ref        = form.get("other_ref",        "").strip()
        q_date           = form.get("date",             str(_date.today()))
        payment_terms    = form.get("payment_terms",    "").strip()
        delivery_terms   = form.get("delivery_terms",   "").strip()
        dispatch_through = form.get("dispatch_through", "").strip()
        validity         = form.get("validity",         "").strip()
        incoterms        = form.get("incoterms",        "").strip()

        raw_ids  = form.getlist("product_id")
        raw_qtys = form.getlist("product_qty")

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
                        error = f"Product '{pid[:12]}…' no longer exists in the catalog."
                        break
                    try:
                        qty = float(qty_raw)
                        if qty <= 0:
                            raise ValueError
                    except (ValueError, TypeError):
                        error = f"Invalid quantity for '{products[pid]['name']}'. Must be > 0."
                        break
                    selections.append({"product_id": pid, "qty": qty})
                if not error and not selections:
                    error = "Please add at least one product to the quotation."

        if not error:
            line_items: list[dict] = []
            for sel in selections:
                line_items.extend(expand_product(sel["product_id"], sel["qty"]))

            grand_total  = sum(r["total"] for r in line_items)
            # total_qty = sum of qty for root-level selections only
            total_qty_rt = sum(r["qty"]   for r in line_items if r["depth"] == 0)

            qid = str(uuid.uuid4())
            STORE["quotations"][qid] = {
                "id":               qid,
                "ref":              _next_ref(),
                "to":               to_addr,
                "buyer_ref":        buyer_ref,
                "other_ref":        other_ref,
                "date":             q_date,
                "payment_terms":    payment_terms,
                "delivery_terms":   delivery_terms,
                "dispatch_through": dispatch_through,
                "validity":         validity,
                "incoterms":        incoterms,
                "selections":       selections,
                "line_items":       line_items,
                "grand_total":      grand_total,
                "total_qty":        total_qty_rt,
            }
            return redirect(url_for("quotation.view_quotation", id=qid))

    # ── GET / re-render after error ──────────────────────────────────
    list_url   = url_for("quotation.list_quotations")
    error_html = f'<div class="alert alert-error">&#10007; {error}</div>' if error else ""
    today_str  = str(_date.today())
    prod_opts  = _product_options_html()

    def _fv(key, default=""):
        return form.get(key, default)

    def _sel(name, options, default):
        cur = _fv(name, default)
        inner = "".join(
            f'<option{"  selected" if o == cur else ""}>{o}</option>'
            for o in options
        )
        return f'<select id="{name}" name="{name}">{inner}</select>'

    _PAY = [
        "100% Advance",
        "100% Against Proforma Invoice",
        "30% Advance with PO, Balance Against Proforma Invoice Prior to Delivery",
        "30% Advance, Balance Before Dispatch",
        "50% Advance, Balance Before Dispatch",
        "90% Against Proforma, 10% After Installation",
        "LC at Sight", "LC 30 Days",
        "45 Days Credit", "60 Days Credit", "90 Days Credit",
        "Against Delivery (COD)",
    ]
    _DEL = [
        "Ex-Works", "Ex-Panvel Godown", "Ex-Mumbai Warehouse",
        "FOR Destination", "FOB Mumbai", "CIF Destination",
        "Door Delivery", "Ex-Factory", "Ex-Stock",
    ]
    _DIS = [
        "By Road Transport", "By Air Cargo", "By Courier", "By Hand Delivery",
        "In Clients Scope", "Self Pickup",
        "VRL Logistics", "TCI Freight", "DTDC Cargo", "Blue Dart",
    ]
    _INC = ["EXW", "FOB", "CIF", "CFR", "DAP", "DDP", "FCA", "FOR"]
    _VAL = ["7 Days", "10 Days", "15 Days", "30 Days", "45 Days", "60 Days", "90 Days"]

    restored_rows = ""
    for pid, qty_raw in zip(form.getlist("product_id"), form.getlist("product_qty")):
        pid = pid.strip()
        if not pid or pid not in products:
            continue
        p = products[pid]
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
                  onclick="this.closest('.sel-row').remove();_updateEmpty();">&#215;</button>
        </div>
        """

    empty_display = "none" if restored_rows else "block"

    template = f"""
    <!DOCTYPE html><html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>New Quotation &#8212; QMS</title>
      {BASE_STYLES}{QUOTATION_STYLES}
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
                <textarea id="to" name="to" rows="7"
                  placeholder="M/s. Company Name&#10;Address, Area&#10;City, State &#8211; PIN&#10;Phone No. :&#10;GSTIN :&#10;Kind Attn :&#10;Email Id :"
                  required>{_fv('to')}</textarea>
              </div>

              <div class="form-group">
                <label for="buyer_ref">Buyer Ref. No.</label>
                <input type="text" id="buyer_ref" name="buyer_ref"
                       value="{_fv('buyer_ref')}" placeholder="PO / SN / Enquiry No."
                       autocomplete="off"/>
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
                       placeholder="e.g. kirloskar fire pump / 2850 LPM @ 104M HEAD"
                       autocomplete="off"/>
              </div>
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-title">&#128221;&nbsp; Commercial Terms</div>
            <div class="form-grid">
              <div class="form-group">
                <label>Mode / Terms of Payment</label>
                {_sel('payment_terms', _PAY, '100% Against Proforma Invoice')}
              </div>
              <div class="form-group">
                <label>Terms of Delivery</label>
                {_sel('delivery_terms', _DEL, 'Ex-Panvel Godown')}
              </div>
              <div class="form-group">
                <label>Dispatch Through</label>
                {_sel('dispatch_through', _DIS, 'In Clients Scope')}
              </div>
              <div class="form-group">
                <label>Incoterms</label>
                {_sel('incoterms', _INC, 'FOR')}
              </div>
              <div class="form-group">
                <label>Validity</label>
                {_sel('validity', _VAL, '15 Days')}
              </div>
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-title">&#128230;&nbsp; Products / Assemblies</div>
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
                <button type="button" class="btn" onclick="_addProduct()">+ Add</button>
              </div>
            </div>
            <div id="add-error" class="add-error"></div>
            <div id="product-list">{restored_rows}</div>
            <div id="empty-notice" style="display:{empty_display};">
              No products added yet. Select a product above and click&nbsp;<strong>+ Add</strong>.
            </div>
          </div>

          <div class="form-actions">
            <button type="submit" class="btn">&#10003;&nbsp; Generate Quotation</button>
            <a href="{list_url}" class="btn btn-ghost">Cancel</a>
          </div>
        </form>

        <footer><p>QMS Platform &nbsp;&#183;&nbsp; Quotation Module &nbsp;&#183;&nbsp; In-memory store</p></footer>
      </main>

      <script>
        function fillToTemplate() {{
          const ta = document.getElementById('to');
          if (!ta.value.trim()) {{
            ta.value = [
              'M/s. ',
              'Address Line 1, Area',
              'City, State \u2013 PIN',
              'Phone No. : ',
              'GSTIN : ',
              'Kind Attn : ',
              'Email Id : ',
            ].join('\\n');
          }}
        }}

        function _addProduct() {{
          const sel   = document.getElementById('product-select');
          const qtyEl = document.getElementById('add-qty');
          const errEl = document.getElementById('add-error');
          const list  = document.getElementById('product-list');
          const empty = document.getElementById('empty-notice');

          errEl.style.display = 'none';
          const pid = sel.value;
          if (!pid) {{ errEl.textContent='Please select a product.'; errEl.style.display='block'; return; }}
          const qty = parseInt(qtyEl.value, 10);
          if (!qty || qty < 1) {{ errEl.textContent='Quantity must be at least 1.'; errEl.style.display='block'; return; }}

          const opt    = sel.options[sel.selectedIndex];
          const name   = opt.getAttribute('data-name')   || opt.text;
          const partno = opt.getAttribute('data-partno') || '';

          const row  = document.createElement('div'); row.className = 'sel-row';
          const hidId = document.createElement('input');
          hidId.type='hidden'; hidId.name='product_id'; hidId.value=pid;

          const info = document.createElement('div');
          info.innerHTML = '<div class="sel-info-name">'+name+'</div><div class="sel-info-partno">'+partno+'</div>';

          const qtyIn = document.createElement('input');
          qtyIn.type='number'; qtyIn.name='product_qty'; qtyIn.value=qty;
          qtyIn.min='1'; qtyIn.step='1'; qtyIn.className='sel-qty-input';

          const rmBtn = document.createElement('button');
          rmBtn.type='button'; rmBtn.className='btn-remove-sel'; rmBtn.textContent='\u00d7';
          rmBtn.onclick = function() {{ row.remove(); _updateEmpty(); }};

          row.appendChild(hidId); row.appendChild(info); row.appendChild(qtyIn); row.appendChild(rmBtn);
          list.appendChild(row);
          empty.style.display = 'none';
          sel.value = ''; qtyEl.value = '1';
        }}

        function _updateEmpty() {{
          const list  = document.getElementById('product-list');
          const empty = document.getElementById('empty-notice');
          empty.style.display = (list.children.length === 0) ? 'block' : 'none';
        }}

        document.getElementById('quotation-form').addEventListener('submit', function(e) {{
          if (document.getElementById('product-list').children.length === 0) {{
            e.preventDefault();
            const errEl = document.getElementById('add-error');
            errEl.textContent = 'Add at least one product before generating the quotation.';
            errEl.style.display = 'block';
            errEl.scrollIntoView({{ behavior:'smooth', block:'center' }});
          }}
        }});
      </script>
    </body></html>
    """
    return render_template_string(template)


@quotation_bp.route("/view/<id>")
def view_quotation(id: str):
    """
    GET /quotation/view/<id>

    Renders the quotation as a document matching SEC/Q/25-26/6406 layout:

    [Letterhead]
    [QUOTATION title bar]
    [Header box: To (left) | Meta grid 2×N (right)]
      Meta fields: Quotation No / Date / Buyer Ref / Other Ref /
                   Payment Terms / Dispatch Through / Delivery Terms / Validity / _ / Incoterms
    [Line items table]
      S.No | Part No | Description | HSN/SAC | Qty | Unit | Unit Price | Total Price
      Assembly rows  → bold, light-grey background, price shown (depth=0) or 0.00 (depth>0)
      Item rows      → normal weight, price shown or 0.00 per depth rule
    [Total row: label | total_qty | | grand_total]
    [Amount in words]
    [Terms and Conditions — numbered list]
    [Signatory block: GSTIN/PAN left | For Company + name right]
    [Computer-generated note]
    """
    q = STORE["quotations"].get(id)
    if not q:
        return redirect(url_for("quotation.list_quotations", msg="Quotation not found.", type="error"))

    list_url   = url_for("quotation.list_quotations")
    create_url = url_for("quotation.create_quotation")
    line_items = q["line_items"]

    # ── Line-items rows ────────────────────────────────────────────────
    sno        = 0
    total_qty  = 0.0
    table_rows = ""

    for row in line_items:
        sno += 1
        depth     = row.get("depth", 0)
        row_class = "row-assembly" if row["type"] == "assembly" else "row-item"
        indent    = f"indent-{min(depth, 3)}" if depth > 0 else ""

        if depth == 0:
            total_qty += row["qty"]

        price_str = f"{row['price']:,.2f}" if row["price"] else "0.00"
        total_str = f"{row['total']:,.2f}" if row["total"] else "0.00"
        hsn       = row.get("hsn") or ""

        table_rows += f"""
        <tr class="{row_class}">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{row['part_no']}</td>
          <td class="c-desc {indent}">{row['name']}</td>
          <td class="c-hsn">{hsn}</td>
          <td class="c-qty">{_fmt_qty(row['qty'])}</td>
          <td class="c-unit">{row['unit']}</td>
          <td class="c-price">{price_str}</td>
          <td class="c-total">{total_str}</td>
        </tr>
        """

    table_rows += f"""
    <tr class="row-total">
      <td class="c-sno" colspan="4" style="text-align:right;">Total</td>
      <td class="c-qty">{_fmt_qty(total_qty)}</td>
      <td class="c-unit"></td>
      <td class="c-price"></td>
      <td class="c-total">&#8377;&nbsp;{q['grand_total']:,.2f}</td>
    </tr>
    """

    # ── Meta grid ─────────────────────────────────────────────────────
    # 10 cells (5 rows × 2 cols), matching the PDF two-column layout
    meta_html = (
        _mc("Quotation No.",        q["ref"]) +
        _mc("Date",                 q["date"]) +
        _mc("Buyer Ref. No.",       q.get("buyer_ref")        or "") +
        _mc("Other Ref.",           q.get("other_ref")        or "") +
        _mc("Mode/Term of Payment", q.get("payment_terms")    or "") +
        _mc("Dispatch Through",     q.get("dispatch_through") or "") +
        _mc("Terms of Delivery",    q.get("delivery_terms")   or "") +
        _mc("Validity",             q.get("validity")         or "") +
        _mc("",                     "") +
        _mc("Incoterms",            q.get("incoterms")        or "")
    )

    # ── T&C ───────────────────────────────────────────────────────────
    tnc_html = "".join(
        f'<li><span class="tnc-num">{i+1}.</span>{t}</li>'
        for i, t in enumerate(COMPANY_TERMS)
    )

    # ── Amount in words ────────────────────────────────────────────────
    words = _amount_in_words(q["grand_total"])

    to_display = (q.get("to") or "").strip()

    template = f"""
    <!DOCTYPE html><html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{q['ref']} &#8212; Quotation</title>
      {BASE_STYLES}
      {VIEW_DOC_STYLES}
    </head>
    <body>
      {_nav()}
      <main>

        <div class="screen-actions">
          <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
            Quotation <span style="color:var(--brand);">{q['ref']}</span>
          </h1>
          <div style="display:flex;gap:.75rem;">
            <a href="{list_url}"   class="btn btn-ghost">&#8592; All Quotations</a>
            <a href="{create_url}" class="btn btn-ghost">+ New</a>
            <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
          </div>
        </div>

        <div class="doc-outer">
          <div class="quotation-doc">

            <!-- Letterhead -->
            <div class="lh-band">
              <div>
                <div class="lh-logo-name">{COMPANY_NAME}</div>
                <div class="lh-tagline">&#8212; {COMPANY_TAGLINE} &#8212;</div>
              </div>
              <div class="lh-logo-right">
                Phone No.: {COMPANY_PHONE}<br>
                Email: {COMPANY_EMAIL} &nbsp;|&nbsp; Web: {COMPANY_WEB}<br>
                Branches: {COMPANY_BRANCHES}
              </div>
            </div>
            <div class="lh-reg-addr">
              Registered Address: {COMPANY_ADDR}
            </div>

            <!-- Title bar -->
            <div class="doc-title-bar">QUOTATION</div>

            <!-- Header box: To (left) + meta grid (right) -->
            <div class="header-box">
              <div class="hb-to">
                <span class="hb-to-label">To</span>
                <div class="hb-to-value">{to_display}</div>
              </div>
              <div class="hb-meta">
                <div class="meta-grid">{meta_html}</div>
              </div>
            </div>

            <!-- Line items -->
            <div class="items-wrap">
              <table class="q-table">
                <thead><tr>
                  <th class="c-sno">S.No</th>
                  <th class="c-partno">Part No</th>
                  <th class="c-desc">Description of Goods</th>
                  <th class="c-hsn r">HSN/SAC</th>
                  <th class="c-qty r">Qty</th>
                  <th class="c-unit r">Unit</th>
                  <th class="c-price r">Unit Price</th>
                  <th class="c-total r">Total Price</th>
                </tr></thead>
                <tbody>{table_rows}</tbody>
              </table>
            </div>

            <!-- Amount in words -->
            <div class="amount-words">
              <strong>Amount Chargeable (in words):</strong>&nbsp;&nbsp;{words}
            </div>

            <!-- Terms and Conditions -->
            <div class="tnc-section">
              <div class="tnc-title">
                {COMPANY_NAME.split()[0]} Terms and Conditions
              </div>
              <ol class="tnc-ol">{tnc_html}</ol>
            </div>

            <!-- Signatory -->
            <div class="signatory-block">
              <div class="sig-gstin">
                GSTIN &nbsp;&nbsp;&nbsp;: <b>{COMPANY_GSTIN}</b><br>
                PAN No. : <b>{COMPANY_PAN}</b>
              </div>
              <div class="sig-right">
                <div class="sig-for">For {COMPANY_NAME}</div>
                <div class="sig-name">{COMPANY_SIGNATORY}</div>
              </div>
            </div>
            <div class="sig-note">
              This is a Computer Generated Document, no signature required
            </div>
            <div class="page-num">Page 1 of 1</div>

          </div><!-- /.quotation-doc -->
        </div><!-- /.doc-outer -->

        <footer style="margin-top:2rem;">
          <p>QMS Platform &nbsp;&#183;&nbsp; Quotation Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>
    </body></html>
    """
    return render_template_string(template)