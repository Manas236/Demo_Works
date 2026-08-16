"""
purchase.py — Purchase Order Module  (THE BUY SIDE)
===================================================
Blueprint  : purchase_bp
Mounted at : /purchase  (registered in app.py)

Routes
------
  GET       /purchase/               — register of purchase orders raised
  GET,POST  /purchase/create         — raise a PO on a vendor
  POST      /purchase/<id>/update    — move it along its lifecycle
  GET       /purchase/view/<id>      — the printed purchase order

Why this is a separate pipeline and not a fourth link in the document chain
---------------------------------------------------------------------------
Every other document in this app is **sell side**:

    quotation  ->  proforma invoice  ->  tax invoice        money coming IN

A purchase order is **buy side** — money going OUT. It is not the same flow
with a different counterparty; it is the mirror image, and the two meet at the
*job*, never at the document:

* A proforma invoice **requests** money from a customer. A tax invoice
  **records a sale** and creates our output GST liability. Neither has anything
  to say about what we paid a vendor.
* A PO commits us to **spend**. The GST on it is **input** tax we pay and later
  claim, the opposite side of the ledger from a tax invoice.
* Its counterparty is a **vendor**, not a customer.

So there is deliberately **no link from a PO to a proforma or a tax invoice**,
and there never should be. Wiring one would be a category error.

The one link that does exist, and why it is optional
----------------------------------------------------
`quotation_id` is a **soft, optional** reference: "this PO is procuring for
QT-0012". It is not a parent the way a quotation is the parent of a PI — a PO
can stand entirely alone, because stock, consumables and spares get bought
without any deal behind them.

That single optional field is what buys job costing: quoted value against what
the job actually costs us to buy. `quotation.py` renders that panel by reading
`STORE["purchases"]` directly plus `url_for` — it must **not** import this
module.

The inversion you must hold in your head while editing this file
-----------------------------------------------------------------
On every other printed document **we are the seller**. On this one **we are the
buyer**, and three things flip:

  ┌────────────────┬─────────────────────────┬──────────────────────────┐
  │                │ quotation / PI / TI     │ purchase order           │
  ├────────────────┼─────────────────────────┼──────────────────────────┤
  │ letterhead     │ us (we issue it)        │ us (we issue it too)     │
  │ the "To" block │ the CUSTOMER            │ the VENDOR               │
  │ delivery block │ where we ship TO them   │ where they deliver TO US │
  │ the tax        │ OUTPUT tax we collect   │ INPUT tax we pay         │
  └────────────────┴─────────────────────────┴──────────────────────────┘

Getting the "To" block wrong here means posting our own address to a supplier
as the party to invoice. `_vendor_block()` and `_delivery_block()` are named
for the roles, not for the positions on the page, to make that hard to slip.

What is reused, and from where
------------------------------
Only the **document toolkit**, never the sell-side logic: `VIEW_DOC_STYLES`
gives the A4 frame, the repeating letterhead and the print rules, and `_inr` /
`_fmt_qty` / `_amount_in_words` / `_meta` / `_tax_lines` are the document's own
formatters. The financial-year helpers come from `pipeline.py`, which imports
nothing from the app — that is what lets both pipelines number their documents
`SF/../26-27/0001` without importing each other.

Import direction: purchase -> quotation (toolkit only), address, pipeline,
dashboard, branding, store. **Nothing here imports proforma or invoice, and
nothing there imports this.** Keep it that way; it is the whole point.
"""

import uuid
from datetime import date as _date, datetime as _datetime
from flask import Blueprint, request, redirect, url_for

import branding as B
import pipeline as P
import docsheet as DS
from dashboard import BASE_STYLES, _nav
from store import STORE

# The shared A4 document toolkit — the sheet, not the sales chain. The sheet
# itself is now `docsheet.py`, which the tax invoice renders through as well:
# neither module imports the other, both import the leaf, and the separation
# this file's docstring insists on is unaffected.
from quotation import (
    QUOTATION_STYLES,     # the register and the create form; the SHEET's copy
    _amount_in_words,     # arrives inside DS.SHEET_STYLES
    _fmt_qty,
    _inr,
    _meta,
    _tax_lines,
)

# The same term vocabularies the sell-side forms offer. Shared rather than
# re-listed: "By Road Transport" must mean the same thing whichever direction
# the goods are moving.
from quotation import _DEL_TERMS, _DISPATCH, _INCOTERMS, _PAY_TERMS, _sel_opts
from address import picker_options

purchase_bp = Blueprint("purchase", __name__, url_prefix="/purchase")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================
_REF_SERIES = "PO"

# The lifecycle of a purchase order. This is the "different procedure" that
# makes purchasing its own pipeline: a sell-side document is issued once and
# then stands, whereas a PO is a commitment that has to be chased through to
# delivery. Edit this list and the form dropdown, the register filter tabs and
# the badges all regenerate.
PO_STATUSES = [
    "Draft",               # written, not yet sent to the vendor
    "Issued",              # sent; we are committed
    "Acknowledged",        # vendor has confirmed price and delivery
    "Partially Received",  # some material in, balance pending
    "Received",            # complete
    "Cancelled",           # withdrawn before delivery
]

DEFAULT_STATUS = "Draft"

# Terminal states. Everything else is still live and counts toward committed
# spend — the buy-side equivalent of `pipeline.OPEN_STAGES`.
CLOSED_STATUSES = ("Received", "Cancelled")

# A PO that commits money but was never acknowledged by the vendor is the
# classic way a delivery date quietly slips. The register flags them.
CHASE_STATUSES = ("Issued",)

# Blank rows the line editor opens with.
DEFAULT_LINE_ROWS = 3


# =============================================================================
# HELPERS
# =============================================================================

def _today() -> str:
    return _date.today().strftime("%Y-%m-%d")


def _now() -> str:
    return _datetime.now().strftime("%Y-%m-%d %H:%M")


def _next_ref(datestr: str) -> str:
    """
    Next purchase order number — 'SF/PO/26-27/0001'.

    FY-scoped and max+1 within that year, the same shape as the tax invoice
    series (`pipeline.fy_of` / `fy_ref` are shared). A PO carries no statutory
    numbering rule — Rule 46 governs what we *issue as a supplier*, and here we
    are the customer — but a buyer's own series still has to be unique and
    non-repeating, because it is the key the vendor quotes on their invoice and
    the key we match that invoice against.

    Scanning only same-FY records is what lets the series restart each April
    without ever colliding.
    """
    fy = P.fy_of(datestr)
    highest = 0
    for po in STORE["purchases"].values():
        if po.get("fy") != fy:
            continue
        tail = str(po.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    # No 16-char cap: that is Rule 46's limit on a tax invoice, not ours.
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=64)


def is_open(po: dict) -> bool:
    """Still live — committed spend that has not landed or been withdrawn."""
    return (po.get("status") or DEFAULT_STATUS) not in CLOSED_STATUSES


def _status_badge(status: str) -> str:
    status = status or DEFAULT_STATUS
    slug = status.lower().replace(" ", "-")
    return f'<span class="po-badge po-{slug}">{P.esc(status)}</span>'


def _vendor_of(po: dict) -> str:
    """The party we are buying from — for list views."""
    name = (po.get("vendor_name") or "").strip()
    if name:
        return name
    first = (po.get("to") or "").strip().splitlines()
    return first[0].strip() if first else "—"


def _addr_block(addr: dict) -> str:
    """
    An address book entry as a printable multi-line block.

    Built here rather than with `address.format_address_lines()` because a PO
    wants the vendor's GSTIN and phone in the block (we have to quote them and
    ring them), and that helper deliberately renders postal lines only.
    """
    if not addr:
        return ""
    parts = []
    if addr.get("company"):      parts.append(addr["company"])
    if addr.get("contact_name"): parts.append(f'Kind Attn: {addr["contact_name"]}')
    for k in ("line1", "line2", "landmark"):
        if addr.get(k):
            parts.append(addr[k])
    city = addr.get("city") or ""
    if addr.get("pincode"):
        city = f'{city} - {addr["pincode"]}' if city else addr["pincode"]
    if city:
        parts.append(city)
    st = ", ".join(x for x in (addr.get("state"), addr.get("country") or "India") if x)
    if st:
        parts.append(st)
    if addr.get("phone"): parts.append(f'Ph: {addr["phone"]}')
    if addr.get("gstin"): parts.append(f'GSTIN: {addr["gstin"]}')
    return "\n".join(parts)


def _purchases_for(quotation_id: str) -> list:
    """Every PO raised against one quotation, oldest number first."""
    out = [(pid, po) for pid, po in STORE["purchases"].items()
           if po.get("quotation_id") == quotation_id]
    out.sort(key=lambda kv: kv[1].get("ref", ""))
    return out


def job_cost(quotation_id: str) -> dict:
    """
    What this job has cost us to buy, against what we quoted for it.

    The whole reason the optional `quotation_id` link exists. Public because
    `quotation.py` renders it on the deal panel — it reads this via a direct
    `STORE` walk rather than importing this module (see the docstring).

    **Cancelled POs are excluded from committed spend**; a withdrawn commitment
    is not a cost. They are still counted in `count` so the panel does not
    silently lose a document somebody raised.
    """
    committed = 0.0
    received  = 0.0
    rows = _purchases_for(quotation_id)
    for _pid, po in rows:
        if (po.get("status") or DEFAULT_STATUS) == "Cancelled":
            continue
        val = float(po.get("grand_total") or 0.0)
        committed += val
        if po.get("status") == "Received":
            received += val

    q = STORE["quotations"].get(quotation_id) or {}
    quoted = float(q.get("grand_total") or 0.0)
    return {
        "count":     len(rows),
        "committed": committed,
        "received":  received,
        "quoted":    quoted,
        "margin":    quoted - committed,
        # Guard the divide: a quotation can legitimately total zero (everything
        # marked "included, no separate charge"), and a ZeroDivisionError on a
        # deal panel is a 500 on a page somebody opens every day.
        "margin_pct": ((quoted - committed) / quoted * 100.0) if quoted else 0.0,
    }


def _log(po: dict, note: str, status_to: str = None) -> None:
    """Append to the PO's own audit trail. Mirrors `pipeline.log_event`."""
    po.setdefault("status_history", []).append({
        "at":     _now(),
        "status": status_to if status_to is not None else po.get("status", DEFAULT_STATUS),
        "note":   note,
    })


def _history_html(po: dict) -> str:
    """Reverse-chronological trail, newest first — same idiom as the deal panel."""
    rows = list(reversed(po.get("status_history") or []))
    if not rows:
        return '<div class="po-hist-empty">Nothing recorded yet.</div>'
    out = ""
    for e in rows:
        out += (f'<div class="po-hist-row">'
                f'<span class="ph-at">{P.esc(e.get("at"))}</span>'
                f'<span class="ph-st">{_status_badge(e.get("status"))}</span>'
                f'<span class="ph-note">{P.esc(e.get("note"))}</span></div>')
    return out


def _parse_lines(form) -> tuple:
    """
    Read the repeating line-item rows off the form.

    Returns `(line_items, error)`. Rows with no product selected are skipped
    silently — the editor opens with blank rows on purpose, and an untouched
    one is not a mistake to shout about.

    A PO is **flat**: `depth` is always 0 and an assembly's children are not
    expanded. We are buying the thing the vendor sells us; if the components
    are bought separately they are separate lines, chosen deliberately. That is
    the opposite of the quotation, where a BOM is expanded so the customer can
    see what is inside — see ABOUT.md §3.
    """
    products = STORE["products"]
    ids   = form.getlist("line_product_id")
    qtys  = form.getlist("line_qty")
    rates = form.getlist("line_rate")

    items = []
    for pid, qty_raw, rate_raw in zip(ids, qtys, rates):
        pid = (pid or "").strip()
        if not pid:
            continue
        p = products.get(pid)
        if not p:
            return [], "One or more selected items no longer exist in the catalogue."
        try:
            qty = float(str(qty_raw or "").strip() or 0)
        except ValueError:
            return [], f"Quantity for '{p['name']}' must be a number."
        if qty <= 0:
            return [], f"Quantity for '{p['name']}' must be greater than zero."

        rate = P.parse_money(rate_raw)
        if rate < 0:
            return [], f"Rate for '{p['name']}' cannot be negative."

        items.append({
            "type":    "item",
            "name":    p["name"],
            "part_no": p["part_no"],
            "hsn":     p.get("hsn", ""),
            "qty":     qty,
            "unit":    p.get("unit", ""),
            "price":   rate,
            "total":   round(rate * qty, 2),
            "depth":   0,
        })

    if not items:
        return [], "Add at least one item to the purchase order."
    return items, ""


def _alert(msg: str, msg_type: str) -> str:
    if not msg:
        return ""
    icon = "&#10003;" if msg_type == "success" else "&#10007;"
    return f'<div class="alert alert-{msg_type}">{icon} {P.esc(msg)}</div>'


def _product_options(selected: str = "") -> str:
    """
    Catalogue <option> list for a line row.

    Includes **support** items prominently — a pump casing or a base frame is
    exactly the sort of thing that is bought rather than sold on its own, so
    the type that the sell-side picker treats as a sub-component is a
    first-class choice here.
    """
    opts = '<option value="">&#8212; select item &#8212;</option>'
    for pid, p in sorted(STORE["products"].items(),
                         key=lambda kv: (kv[1].get("name") or "").lower()):
        sel  = " selected" if pid == selected else ""
        kind = (p.get("type") or "standalone")[:3].upper()
        opts += (f'<option value="{P.esc(pid)}"{sel}>'
                 f'[{kind}] {P.esc(p.get("name"))} ({P.esc(p.get("part_no"))})</option>')
    return opts


# =============================================================================
# CSS — purchase-only
# =============================================================================
# Plain string, not an f-string, so the CSS braces are written once. Layered
# after BASE_STYLES / QUOTATION_STYLES. Deliberately does NOT load
# PROFORMA_STYLES or INVOICE_STYLES: this is the other pipeline, and borrowing
# a sell-side sheet is how the separation would quietly rot. Anything the buy
# side needs is declared here.

PURCHASE_STYLES = """
<style>
  /* ── Screen: form ─────────────────────────────────────────────────── */
  .field-hint {
    display:block; margin-top:.35rem; font-size:.76rem;
    color:var(--muted); line-height:1.45; font-weight:400;
    text-transform:none; letter-spacing:0;
  }

  /* The buy-side banner. A PO looks enough like the sell-side documents that
     somebody will eventually open one expecting a quotation, so the direction
     of the money is stated once, in words, at the top of the form. */
  .buy-note {
    background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--navy); border-radius:var(--radius);
    padding:.9rem 1.2rem; margin-bottom:1.4rem; font-size:.88rem;
  }
  .buy-note b { color:var(--navy); }
  .buy-note .bn-sub { color:var(--muted); font-size:.82rem; margin-top:.25rem; }

  /* Repeating line editor — same shape as product.py's BOM child rows, which
     is the established pattern in this app for "a few rows, no JS model". */
  .line-row {
    display:grid; grid-template-columns:1fr 90px 130px 120px 34px;
    gap:.55rem; align-items:center; margin-bottom:.55rem;
  }
  .line-head {
    display:grid; grid-template-columns:1fr 90px 130px 120px 34px;
    gap:.55rem; font-size:.72rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.05em; margin-bottom:.4rem;
  }
  .line-row .ln-amt {
    font-variant-numeric:tabular-nums; text-align:right;
    font-size:.86rem; color:var(--muted); padding-right:.2rem;
  }
  .btn-remove-line {
    background:none; border:1px solid var(--border); border-radius:7px;
    color:var(--muted); cursor:pointer; font-size:1rem; line-height:1;
    padding:.35rem .5rem;
  }
  .btn-remove-line:hover { border-color:var(--brand); color:var(--brand); }
  .po-total-strip {
    display:flex; justify-content:flex-end; gap:1.4rem; flex-wrap:wrap;
    margin-top:.9rem; padding-top:.9rem; border-top:1px solid var(--border);
    font-size:.9rem;
  }
  .po-total-strip b { font-size:1.05rem; color:var(--brand); }
  @media (max-width:640px){
    .line-row, .line-head { grid-template-columns:1fr 70px 110px; }
    .line-head span:nth-child(4), .line-head span:nth-child(5),
    .line-row .ln-amt { display:none; }
  }

  /* ── Screen: status badges ────────────────────────────────────────── */
  .po-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem; white-space:nowrap;
    background:#EDECF1; color:#4B4459;
  }
  .po-issued             { background:var(--navy-lt); color:var(--navy); }
  .po-acknowledged       { background:#E3ECFA; color:#1B4C8C; }
  .po-partially-received { background:#FFF4D6; color:#8A5A00; }
  .po-received           { background:#E4F3E7; color:#1E6B2E; }
  .po-cancelled          { background:#F3E4E4; color:#8C2A2A; }

  /* ── Screen: the PO panel on the view page ────────────────────────── */
  .po-panel {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.2rem 1.4rem; margin-bottom:1.5rem;
  }
  .po-panel h2 {
    font-size:.78rem; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted); margin-bottom:.9rem;
  }
  .po-panel-row { display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-end; }
  .po-hist { margin-top:1.1rem; border-top:1px solid var(--border); padding-top:.8rem; }
  .po-hist-row {
    display:flex; gap:.7rem; align-items:baseline; flex-wrap:wrap;
    font-size:.82rem; padding:.28rem 0;
  }
  .po-hist-row .ph-at { color:var(--muted); font-variant-numeric:tabular-nums; }
  .po-hist-row .ph-note { color:var(--text); }
  .po-hist-empty { font-size:.83rem; color:var(--muted); }
  @media print { .po-panel { display:none; } }

  /* ── Print: the PO document ───────────────────────────────────────── */
  /* Scoped inside .quotation-doc so it inherits that sheet's type scale
     (--fs-*) and rule weights (--rule-*). No new font, size or border weight —
     the same restraint PROFORMA_STYLES and INVOICE_STYLES hold to. */

  /* States the direction of the transaction on the face of the document. A
     supplier receiving this must not be able to mistake it for our quotation. */
  .quotation-doc .doc-sub-po {
    text-align:center; font-size:var(--fs-sm); font-weight:700;
    padding:2px 6px; border-bottom:var(--rule-box);
  }
  .quotation-doc .doc-sub-po .dp-src { font-weight:400; color:var(--doc-soft); }

  .quotation-doc .po-status-strip {
    display:flex; flex-wrap:wrap; gap:0 8mm;
    padding:2px 6px; border-bottom:var(--rule);
  }
  .quotation-doc .po-status-strip .ps-l { color:var(--doc-soft); }
  .quotation-doc .po-status-strip .ps-v { font-weight:700; }

  .quotation-doc .po-instr { border:var(--rule-box); margin-top:5mm; }
  .quotation-doc .po-instr-title {
    font-weight:700; font-size:var(--fs-md); padding:2px 6px;
    border-bottom:var(--rule);
  }
  .quotation-doc .po-instr-body { padding:4px 6px; }

  .quotation-doc .po-note { margin-top:4mm; }
  .quotation-doc .po-note .pn-lbl { font-weight:700; }

  /* .jobcost / .jc-* / .po-chip / .po-strip are defined in QUOTATION_STYLES.
     The quotation's deal panel renders the job-costing block and cannot import
     this module (purchase -> quotation, never back), so by the rule in
     ABOUT.md §2 the class belongs to the upstream sheet. Every page here loads
     QUOTATION_STYLES, so this module gets them for free. */
</style>
"""


# =============================================================================
# RENDERING — why these views do not call render_template_string()
# =============================================================================
#
# Every page in this module is a fully interpolated HTML string by the time the
# view returns it. Nothing is passed as Jinja context — ABOUT.md §1 says so
# explicitly — so handing the finished string back to Jinja parses it a second
# time for no benefit and one large cost: any `{{ … }}` or `{% … %}` that
# reached the output from USER INPUT is then executed as a template.
#
# That is not theoretical. `pipeline.esc()` escapes `< > & " '` and deliberately
# not braces, so a PO whose `notes` reads `{{ config }}` prints the Flask config
# — including SECRET_KEY — onto a document that goes out to a supplier, and one
# reading `{% for x in y %}` raises a TemplateSyntaxError that 500s the page.
# Both are stored, and `update_purchase()` changes status only (ABOUT.md §5), so
# neither can be edited off the record.
#
# Returning the string directly is what Flask does with any `str` a view
# returns. It removes the second parse, and with it the injection. HTML
# escaping still does its own job — this changes nothing about XSS.
#
# ⚠ Still open in `quotation.py` and `product.py`, and this one-liner does not
#   reach either: quotation.py builds its pages with `.format()` and has
#   attribute, <script> and option-text sinks besides; product.py does not
#   escape at all. Each wants its own pass — ABOUT.md §7.9d.
# =============================================================================

def _page(html: str) -> str:
    """A finished page. See the note above — deliberately not Jinja-rendered."""
    return html


# =============================================================================
# ROUTES
# =============================================================================

@purchase_bp.route("/")
def list_purchases():
    """Register of purchase orders raised, newest number first."""
    purchases = STORE["purchases"]

    status_f = (request.args.get("status") or "").strip()
    rows = sorted(purchases.items(), key=lambda kv: kv[1].get("ref", ""), reverse=True)
    if status_f:
        rows = [(k, v) for k, v in rows
                if (v.get("status") or DEFAULT_STATUS) == status_f]

    dash_url   = url_for("dashboard.index")
    create_url = url_for("purchase.create_purchase")

    committed = sum(float(p.get("grand_total") or 0.0)
                    for p in purchases.values() if is_open(p))
    landed    = sum(float(p.get("grand_total") or 0.0)
                    for p in purchases.values() if p.get("status") == "Received")
    chasing   = sum(1 for p in purchases.values()
                    if (p.get("status") or DEFAULT_STATUS) in CHASE_STATUSES)

    tiles_html = ""
    if purchases:
        tiles_html = f"""
        <div class="pipe-tiles">
          <div class="pipe-tile t-open">
            <div class="pt-lbl">Committed Spend</div>
            <div class="pt-val">&#8377;&nbsp;{committed:,.0f}</div>
            <div class="pt-sub">on {sum(1 for p in purchases.values() if is_open(p))} open order(s)</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Material Received</div>
            <div class="pt-val">&#8377;&nbsp;{landed:,.0f}</div>
            <div class="pt-sub">orders marked complete</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Awaiting Acknowledgement</div>
            <div class="pt-val">{chasing}</div>
            <div class="pt-sub">issued, vendor has not confirmed</div>
          </div>
        </div>"""

    # Filter tabs reuse .filter-bar / .filter-tab from P.PIPELINE_STYLES — the
    # same widget the quotation register uses, so the two registers behave
    # identically even though they belong to opposite pipelines.
    tabs = (f'<a href="{url_for("purchase.list_purchases")}" '
            f'class="filter-tab{"" if status_f else " active"}">All '
            f'({len(purchases)})</a>')
    for s in PO_STATUSES:
        n = sum(1 for p in purchases.values()
                if (p.get("status") or DEFAULT_STATUS) == s)
        if not n:
            continue
        on = " active" if status_f == s else ""
        tabs += (f'<a href="{url_for("purchase.list_purchases", status=s)}" '
                 f'class="filter-tab{on}">{P.esc(s)} ({n})</a>')
    tabs_html = (f'<div class="filter-bar"><div class="filter-tabs">{tabs}</div></div>'
                 if purchases else "")

    if rows:
        rows_html = ""
        for pid, po in rows:
            view_url = url_for("purchase.view_purchase", id=pid)
            job = ""
            if po.get("quotation_id") in STORE["quotations"]:
                job = (f'<a class="btn-view" href="'
                       f'{url_for("quotation.view_quotation", id=po["quotation_id"])}">'
                       f'{P.esc(po.get("quotation_ref"))}</a>')
            elif po.get("quotation_ref"):
                job = P.esc(po.get("quotation_ref"))
            else:
                job = '<span class="td-muted">stock</span>'
            rows_html += f"""
            <tr>
              <td class="td-ref">{P.esc(po.get('ref'))}</td>
              <td class="td-muted">{P.esc(po.get('date'))}</td>
              <td class="td-cust">{P.esc(_vendor_of(po))}</td>
              <td class="col-h">{job}</td>
              <td class="col-h">{P.esc(po.get('delivery_date'))}</td>
              <td>{_status_badge(po.get('status'))}</td>
              <td class="td-total">&#8377;&nbsp;{float(po.get('grand_total') or 0):,.0f}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>"""
        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>PO No.</th><th>Date</th><th>Vendor</th>
            <th class="col-h">For Job</th><th class="col-h">Wanted By</th>
            <th>Status</th><th>Order Value</th><th></th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    elif purchases:
        table_html = ('<div class="empty-state"><strong>No purchase orders '
                      f'with status &ldquo;{P.esc(status_f)}&rdquo;</strong></div>')
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128230;</div><br>
          <strong>No purchase orders yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            This is the <b>buy side</b> &mdash; what we order from our vendors,
            separate from the quotation &rarr; proforma &rarr; tax invoice chain.
            Link a PO to a quotation and the deal shows what the job is costing.</p>
          <a href="{create_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">
            Raise the first purchase order</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Purchase Orders")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}</head>
    <body>{_nav()}
    <main>
      {_alert(request.args.get("msg"), request.args.get("type", "success"))}
      <div class="page-top">
        <h1>Purchase <span>Orders</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            {len(purchases)} raised &middot; buy side
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{create_url}" class="btn">+ New purchase order</a>
        </div>
      </div>
      {tiles_html}
      {tabs_html}
      {table_html}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order register</p></footer>
    </main></body></html>"""
    return _page(template)


@purchase_bp.route("/create", methods=["GET", "POST"])
def create_purchase():
    """
    Raise a purchase order on a vendor.

    Unlike the sell-side documents this is **entered from scratch, not derived**
    — there is no upstream record to freeze a copy of, because the decision to
    buy is ours. The optional `quotation_id` says which job it is for, and is
    genuinely optional: stock and consumables are bought with no deal behind
    them.
    """
    from product import ensure_demo_products
    ensure_demo_products()

    f     = request.form
    error = ""

    if request.method == "POST":
        po_date   = (f.get("date") or "").strip()
        vendor_id = (f.get("vendor_id") or "").strip()
        vendor    = STORE["addresses"].get(vendor_id)
        qid       = (f.get("quotation_id") or "").strip()
        status    = (f.get("status") or DEFAULT_STATUS).strip()

        tax_type  = (f.get("tax_type") or "exempt").strip()
        cgst = P.parse_money(f.get("cgst_rate"))
        igst = P.parse_money(f.get("igst_rate"))

        items, line_err = _parse_lines(f)

        if not po_date:
            error = "Purchase order date is required."
        elif not vendor_id:
            error = "Choose the vendor this order goes to."
        elif not vendor:
            error = "That vendor is no longer in the address book."
        elif status not in PO_STATUSES:
            error = "Invalid status."
        elif qid and qid not in STORE["quotations"]:
            error = "That quotation no longer exists. Leave the job blank to raise a stock order."
        elif line_err:
            error = line_err

        if not error:
            subtotal = round(sum(r["total"] for r in items), 2)
            # SGST always mirrors CGST, exactly as the quotation form forces it.
            tax_info = _tax_lines(subtotal, tax_type,
                                  cgst_rate=cgst, sgst_rate=cgst, igst_rate=igst)
            grand = round(subtotal + float(tax_info.get("total") or 0.0), 2)

            q   = STORE["quotations"].get(qid) or {}
            pid = str(uuid.uuid4())
            po = {
                "id":   pid,
                "ref":  _next_ref(po_date),
                "fy":   P.fy_of(po_date),
                "date": po_date,

                # ── Who we are buying FROM. Not a customer. ───────────────
                "vendor_id":    vendor_id,
                "vendor_name":  vendor.get("company") or vendor.get("label") or "",
                "vendor_gstin": vendor.get("gstin", ""),
                "to":           _addr_block(vendor),
                "vendor_ref":   (f.get("vendor_ref") or "").strip(),

                # ── Optional soft link to the job. Never a hard parent. ───
                "quotation_id":  qid,
                "quotation_ref": q.get("ref", ""),
                "project_id":    (f.get("project_id") or "").strip(),

                # ── What we are buying ────────────────────────────────────
                "line_items": items,
                "subtotal":   subtotal,
                "tax_type":   tax_type,
                "tax_info":   tax_info,
                "grand_total": grand,
                "total_qty":  round(sum(r["qty"] for r in items), 3),

                # ── Where and when we want it ─────────────────────────────
                "delivery_date":    (f.get("delivery_date") or "").strip(),
                "delivery_to":      (f.get("delivery_to") or "").strip(),
                "payment_terms":    (f.get("payment_terms") or "").strip(),
                "delivery_terms":   (f.get("delivery_terms") or "").strip(),
                "dispatch_through": (f.get("dispatch_through") or "").strip(),
                "incoterms":        (f.get("incoterms") or "").strip(),

                "status":         status,
                "status_history": [],
                "notes":          (f.get("notes") or "").strip(),
                "company_branch": (f.get("company_branch") or "").strip(),
                "auth_signatory": (f.get("auth_signatory") or "").strip(),
            }
            _log(po, f"Purchase order {po['ref']} raised on "
                     f"{po['vendor_name'] or 'vendor'} for &#8377;{grand:,.0f}.",
                 status_to=status)
            STORE["purchases"][pid] = po

            # Buying material for a job is a real event in that deal's life, so
            # it goes on the quotation's audit trail — the one place the two
            # pipelines touch. It does not change the sales stage.
            if q:
                P.log_event(q, f"Purchase order {po['ref']} raised on "
                               f"{P.esc(po['vendor_name'])} for &#8377;{grand:,.0f}.")

            return redirect(url_for("purchase.view_purchase", id=pid,
                                    msg=f"Purchase order {po['ref']} created.",
                                    type="success"))

    # ── Field values: the user's own input on a failed POST, else default ──
    def _v(name: str, fallback: str = "") -> str:
        if request.method == "POST":
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    v_date   = _v("date", _today())
    v_vendor = _v("vendor_id")
    # ?quotation_id=… lets the quotation's "Raise PO" button pre-select the job.
    # Only honoured on GET; on POST the form field is authoritative.
    v_qid    = _v("quotation_id", request.args.get("quotation_id", ""))
    q        = STORE["quotations"].get(v_qid) or {}
    v_pid    = _v("project_id", q.get("project_id", ""))
    v_vref   = _v("vendor_ref")
    v_del_d  = _v("delivery_date")
    v_del_to = _v("delivery_to", B.COMPANY_ADDR)
    v_notes  = _v("notes")
    v_tax    = _v("tax_type", "cgst_sgst")
    v_cgst   = _v("cgst_rate", "9")
    v_igst   = _v("igst_rate", "18")

    # Rebuild the line rows the user had, then pad to DEFAULT_LINE_ROWS.
    prior_ids   = f.getlist("line_product_id") if request.method == "POST" else []
    prior_qtys  = f.getlist("line_qty")        if request.method == "POST" else []
    prior_rates = f.getlist("line_rate")       if request.method == "POST" else []
    rows_data = [(i, q, r) for i, q, r in zip(prior_ids, prior_qtys, prior_rates)]
    while len(rows_data) < DEFAULT_LINE_ROWS:
        rows_data.append(("", "", ""))

    lines_html = ""
    for sel, qty, rate in rows_data:
        lines_html += f"""
        <div class="line-row">
          <select name="line_product_id" onchange="fillRate(this)">{_product_options(sel)}</select>
          <input type="number" name="line_qty" value="{P.esc(qty)}" min="0" step="any" placeholder="Qty"/>
          <input type="number" name="line_rate" value="{P.esc(rate)}" min="0" step="0.01" placeholder="Rate"/>
          <span class="ln-amt">&#8212;</span>
          <button type="button" class="btn-remove-line"
                  onclick="this.closest('.line-row').remove(); recalc();">&#215;</button>
        </div>"""

    # Rates the vendor charges us are NOT the catalogue's base_price (that is a
    # sell price), so the picker only suggests it — the field stays editable and
    # is never overwritten once the user has typed something.
    catalog_rates = "{" + ",".join(
        f'"{pid}":{float(p.get("base_price") or 0):.2f}'
        for pid, p in STORE["products"].items()
    ) + "}"

    q_opts = '<option value="">&#8212; none / stock purchase &#8212;</option>'
    for qid_, q_ in sorted(STORE["quotations"].items(),
                           key=lambda kv: kv[1].get("ref", ""), reverse=True):
        sel = " selected" if qid_ == v_qid else ""
        q_opts += (f'<option value="{P.esc(qid_)}"{sel}>{P.esc(q_.get("ref"))} '
                   f'&middot; {P.esc(q_.get("account_name") or "unnamed")}</option>')

    p_opts = '<option value="">&#8212; none &#8212;</option>'
    for proj_id, proj in sorted(STORE["projects"].items(),
                                key=lambda kv: kv[1].get("name", "").lower()):
        sel = " selected" if proj_id == v_pid else ""
        p_opts += f'<option value="{P.esc(proj_id)}"{sel}>{P.esc(proj.get("name"))}</option>'

    status_opts = "".join(
        f'<option{" selected" if s == _v("status", DEFAULT_STATUS) else ""}>{s}</option>'
        for s in PO_STATUSES if s != "Cancelled"
    )

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("New Purchase Order")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>New <span>Purchase Order</span></h1>
        <a href="{url_for("purchase.list_purchases")}" class="btn btn-ghost">&#8592; All Purchase Orders</a>
      </div>

      {_alert(error, "error")}

      <div class="buy-note">
        This is the <b>buy side</b> &mdash; an order <b>we place on a vendor</b>,
        not a document for a customer.
        <div class="bn-sub">The GST here is <b>input tax we pay</b>, the opposite
          side of the ledger from a tax invoice. Nothing on this page touches a
          proforma or a tax invoice. The next number is {P.esc(_next_ref(v_date))}.</div>
      </div>

      <form method="POST" action="{url_for("purchase.create_purchase")}">

        <div class="form-section">
          <div class="section-title">Order</div>
          <div class="fg3">
            <div class="form-group">
              <label for="date">PO Date *</label>
              <input type="date" id="date" name="date" value="{P.esc(v_date)}" required/>
            </div>
            <div class="form-group">
              <label for="vendor_id">Vendor *</label>
              <select id="vendor_id" name="vendor_id" required>
                {picker_options("— choose vendor —", only_types=("vendor",), selected=v_vendor)}
              </select>
              <small class="field-hint">From the address book, vendors only.
                Add one at <a href="{url_for("address.add_address")}">Address Book</a>
                if the supplier is not listed.</small>
            </div>
            <div class="form-group">
              <label for="status">Status</label>
              <select id="status" name="status">{status_opts}</select>
              <small class="field-hint">Start as Draft while you are still
                pricing it; Issued once it has gone to the vendor.</small>
            </div>
            <div class="form-group">
              <label for="quotation_id">For Job <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <select id="quotation_id" name="quotation_id">{q_opts}</select>
              <small class="field-hint">Link it to the quotation this material is
                for and the deal shows quoted value against what it costs us.
                Leave blank for stock.</small>
            </div>
            <div class="form-group">
              <label for="project_id">Project <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <select id="project_id" name="project_id">{p_opts}</select>
            </div>
            <div class="form-group">
              <label for="vendor_ref">Vendor's Offer / Quote Ref</label>
              <input type="text" id="vendor_ref" name="vendor_ref" value="{P.esc(v_vref)}"
                     placeholder="their quotation no., if any"/>
            </div>
            <div class="form-group">
              <label for="delivery_date">Wanted By</label>
              <input type="date" id="delivery_date" name="delivery_date" value="{P.esc(v_del_d)}"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Items ordered</div>
          <div class="line-head">
            <span>Item</span><span>Qty</span><span>Rate (&#8377;)</span>
            <span style="text-align:right;">Amount</span><span></span>
          </div>
          <div id="lines">{lines_html}</div>
          <button type="button" class="btn btn-ghost" onclick="addLine()"
                  style="margin-top:.3rem;">+ Add item</button>
          <div class="po-total-strip">
            <span>Subtotal <b id="po-sub">&#8377; 0</b></span>
            <span>Tax <b id="po-tax">&#8377; 0</b></span>
            <span>Order Value <b id="po-grand">&#8377; 0</b></span>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Tax the vendor will charge us</div>
          <div class="fg3">
            <div class="form-group">
              <label for="tax_type">Tax Type</label>
              <select id="tax_type" name="tax_type" onchange="recalc()">
                <option value="cgst_sgst"{" selected" if v_tax == "cgst_sgst" else ""}>CGST + SGST (intra-state)</option>
                <option value="igst"{" selected" if v_tax == "igst" else ""}>IGST (inter-state)</option>
                <option value="exempt"{" selected" if v_tax == "exempt" else ""}>Exempt / Nil</option>
              </select>
            </div>
            <div class="form-group">
              <label for="cgst_rate">CGST % <span style="font-weight:500;text-transform:none;">(SGST matches)</span></label>
              <input type="number" id="cgst_rate" name="cgst_rate" value="{P.esc(v_cgst)}"
                     min="0" step="any" oninput="recalc()"/>
            </div>
            <div class="form-group">
              <label for="igst_rate">IGST %</label>
              <input type="number" id="igst_rate" name="igst_rate" value="{P.esc(v_igst)}"
                     min="0" step="any" oninput="recalc()"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Terms &amp; delivery</div>
          <div class="fg2">
            <div class="form-group">
              <label for="payment_terms">Payment Terms</label>
              {_sel_opts("payment_terms", _PAY_TERMS, _PAY_TERMS[0], _v("payment_terms"))}
            </div>
            <div class="form-group">
              <label for="delivery_terms">Terms of Delivery</label>
              {_sel_opts("delivery_terms", _DEL_TERMS, _DEL_TERMS[0], _v("delivery_terms"))}
            </div>
            <div class="form-group">
              <label for="dispatch_through">Dispatch Through</label>
              {_sel_opts("dispatch_through", _DISPATCH, _DISPATCH[0], _v("dispatch_through"))}
            </div>
            <div class="form-group">
              <label for="incoterms">Incoterms</label>
              {_sel_opts("incoterms", _INCOTERMS, _INCOTERMS[0], _v("incoterms"))}
            </div>
            <div class="form-group span2">
              <label for="delivery_to">Deliver To</label>
              <textarea id="delivery_to" name="delivery_to" rows="3"
                placeholder="our stores, or the project site">{P.esc(v_del_to)}</textarea>
              <small class="field-hint">Where the vendor sends the material.
                Defaults to our registered address.</small>
            </div>
            <div class="form-group span2">
              <label for="notes">Note on the order <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <input type="text" id="notes" name="notes" value="{P.esc(v_notes)}"
                     placeholder="e.g. Urgent — required at site by month end"/>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn">Raise Purchase Order</button>
          <a href="{url_for("purchase.list_purchases")}" class="btn btn-ghost">Cancel</a>
        </div>
      </form>

      <template id="line-tpl">
        <div class="line-row">
          <select name="line_product_id" onchange="fillRate(this)">{_product_options()}</select>
          <input type="number" name="line_qty" min="0" step="any" placeholder="Qty"/>
          <input type="number" name="line_rate" min="0" step="0.01" placeholder="Rate"/>
          <span class="ln-amt">&#8212;</span>
          <button type="button" class="btn-remove-line"
                  onclick="this.closest('.line-row').remove(); recalc();">&#215;</button>
        </div>
      </template>

      <script>
        var RATES = {catalog_rates};

        function addLine() {{
          var tpl = document.getElementById('line-tpl');
          document.getElementById('lines').appendChild(tpl.content.cloneNode(true));
          bind();
        }}

        /* Suggest the catalogue price, never impose it: base_price is what we
           SELL at, and what a vendor charges us is a different number. Only an
           empty rate box is filled, so a typed figure is never overwritten. */
        function fillRate(sel) {{
          var row = sel.closest('.line-row');
          var rate = row.querySelector('input[name="line_rate"]');
          if (rate && !rate.value && RATES[sel.value] !== undefined) {{
            rate.value = RATES[sel.value].toFixed(2);
          }}
          recalc();
        }}

        function recalc() {{
          var sub = 0;
          document.querySelectorAll('#lines .line-row').forEach(function (row) {{
            var q = parseFloat(row.querySelector('input[name="line_qty"]').value) || 0;
            var r = parseFloat(row.querySelector('input[name="line_rate"]').value) || 0;
            var amt = q * r;
            sub += amt;
            var cell = row.querySelector('.ln-amt');
            if (cell) cell.textContent = amt ? amt.toLocaleString('en-IN',
              {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) : '\\u2014';
          }});

          var type = document.getElementById('tax_type').value;
          var tax = 0;
          if (type === 'cgst_sgst') {{
            tax = sub * (parseFloat(document.getElementById('cgst_rate').value) || 0) / 100 * 2;
          }} else if (type === 'igst') {{
            tax = sub * (parseFloat(document.getElementById('igst_rate').value) || 0) / 100;
          }}

          var f = function (v) {{ return '\\u20B9 ' + v.toLocaleString('en-IN',
            {{maximumFractionDigits: 0}}); }};
          document.getElementById('po-sub').textContent   = f(sub);
          document.getElementById('po-tax').textContent   = f(tax);
          document.getElementById('po-grand').textContent = f(sub + tax);
        }}

        function bind() {{
          document.querySelectorAll('#lines input').forEach(function (el) {{
            el.oninput = recalc;
          }});
        }}

        bind();
        recalc();
      </script>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order</p></footer>
    </main></body></html>"""
    return _page(template)


@purchase_bp.route("/<id>/update", methods=["POST"])
def update_purchase(id: str):
    """
    Move a purchase order along its lifecycle.

    Status only. The commercial content of an issued PO is not editable here —
    a vendor has already been told a price and a quantity, and changing them
    behind the document is how a dispute starts. An amendment means a fresh PO.
    """
    po = STORE["purchases"].get(id)
    if not po:
        return redirect(url_for("purchase.list_purchases",
                                msg="Purchase order not found.", type="error"))

    new_status = (request.form.get("status") or "").strip()
    note       = (request.form.get("note") or "").strip()

    if new_status not in PO_STATUSES:
        return redirect(url_for("purchase.view_purchase", id=id,
                                msg="Invalid status.", type="error"))

    old = po.get("status") or DEFAULT_STATUS
    po["status"] = new_status
    if new_status != old:
        _log(po, note or f"Status changed from {old} to {new_status}.",
             status_to=new_status)
    elif note:
        _log(po, note, status_to=new_status)

    return redirect(url_for("purchase.view_purchase", id=id,
                            msg="Purchase order updated.", type="success"))


@purchase_bp.route("/view/<id>")
def view_purchase(id: str):
    """
    The printed purchase order.

    Same A4 sheet as the sell-side documents (`VIEW_DOC_STYLES`) so everything
    that leaves this office looks like it came from the same place — but read
    the module docstring first: the **"To" block is the vendor**, and the
    delivery block is where they send material **to us**.
    """
    po = STORE["purchases"].get(id)
    if not po:
        return redirect(url_for("purchase.list_purchases",
                                msg="Purchase order not found.", type="error"))

    # ── Line rows ─────────────────────────────────────────────────────────
    sno, total_qty, table_rows = 0, 0.0, ""
    for row in po.get("line_items", []):
        sno += 1
        total_qty += float(row.get("qty") or 0)
        table_rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>
          <td class="c-desc">{P.esc(row.get('name'))}</td>
          <td class="c-hsn">{B.field(row.get('hsn'), "HSN")}</td>
          <td class="c-qty">{_fmt_qty(float(row.get('qty') or 0))}</td>
          <td class="c-unit">{P.esc(row.get('unit'))}</td>
          <td class="c-price">{_inr(row.get('price') or 0)}</td>
          <td class="c-total">{_inr(row.get('total') or 0)}</td>
        </tr>"""

    subtotal = float(po.get("subtotal") or 0.0)
    tax_info = po.get("tax_info") or {"total": 0.0}
    tax_type = po.get("tax_type", "exempt")
    grand    = float(po.get("grand_total") or 0.0)
    has_tax  = tax_type != "exempt" and float(tax_info.get("total") or 0) > 0

    # The rows come from `docsheet`; what goes in them stays here. The tax on
    # this document is **input** tax we pay, the opposite side of the ledger
    # from a tax invoice, and nothing about that arithmetic is shared with the
    # sell chain — only the furniture it prints inside.
    if has_tax:
        table_rows += DS.sum_row("Taxable Value", _inr(subtotal))
        rate_keys = {"CGST": "cgst_rate", "SGST": "sgst_rate",
                     "IGST": "igst_rate", "VAT": "vat_rate"}
        skip = {"total", *rate_keys.values()}
        for tname, tamt in tax_info.items():
            if tname in skip:
                continue
            r = tax_info.get(rate_keys.get(tname, ""), 0)
            lbl = f" @ {r:g}%" if r else ""
            table_rows += DS.sum_row(f"{tname}{lbl}", _inr(tamt), indent=12)

    table_rows += DS.total_row("Order Value", _fmt_qty(total_qty), _inr(grand))

    # ── Header meta ───────────────────────────────────────────────────────
    meta_col_1 = (
        _meta("Purchase Order No.",  P.esc(po.get("ref"))) +
        _meta("Your Offer Ref",      P.esc(po.get("vendor_ref"))) +
        _meta("Your GSTIN",          P.esc(po.get("vendor_gstin"))) +
        _meta("Mode/Term of Payment", P.esc(po.get("payment_terms"))) +
        _meta("Terms of Delivery",   P.esc(po.get("delivery_terms")))
    )
    meta_col_2 = (
        _meta("Date",             P.esc(po.get("date"))) +
        _meta("Required By",      P.esc(po.get("delivery_date"))) +
        _meta("Dispatch Through", P.esc(po.get("dispatch_through"))) +
        _meta("Incoterms",        P.esc(po.get("incoterms"))) +
        _meta("Our GSTIN",        B.COMPANY_GSTIN)
    )

    # ── The vendor block. This is the "To" on a PO — NOT a customer. ───────
    # `DS.name_block` builds the same shape the tax invoice puts a *customer*
    # into. The shape is shared; the role is not, which is why these two locals
    # are named for the role rather than for the position on the page.
    vendor_block = DS.name_block(po.get("to"))
    delivery_block = DS.secondary_block("Deliver To", po.get("delivery_to"))

    job_line = ""
    if po.get("quotation_ref"):
        job_line = (f'<span class="dp-src"> &middot; for our job '
                    f'{P.esc(po["quotation_ref"])}</span>')

    status_strip = f"""
    <div class="po-status-strip">
      <span><span class="ps-l">Status:</span>
            <span class="ps-v">{P.esc(po.get("status") or DEFAULT_STATUS)}</span></span>
      <span><span class="ps-l">Required By:</span>
            <span class="ps-v">{P.esc(po.get("delivery_date")) or "&#8212;"}</span></span>
      <span><span class="ps-l">This order is placed by us as buyer.</span></span>
    </div>"""

    instr_html = """
  <div class="po-instr">
    <div class="po-instr-title">Instructions to Supplier</div>
    <div class="po-instr-body">
      <ol class="tnc-ol">
        <li><span class="tnc-num">1.</span><span>Quote our purchase order number
          on your invoice, delivery challan, packing list and all correspondence.
          An invoice without it may be returned unpaid.</span></li>
        <li><span class="tnc-num">2.</span><span>Your tax invoice must comply with
          Rule 46 of the CGST Rules — GSTIN, HSN/SAC per line, place of supply and
          the tax split shown separately. We cannot claim input tax credit
          against a deficient invoice, and any credit lost will be recovered
          from your payment.</span></li>
        <li><span class="tnc-num">3.</span><span>Deliver to the address shown
          above within the required-by date. Material delivered elsewhere, or
          without prior intimation, is at your risk.</span></li>
        <li><span class="tnc-num">4.</span><span>Goods are accepted subject to
          inspection. Anything short-supplied, damaged or not to specification
          will be rejected and is to be collected at your cost.</span></li>
        <li><span class="tnc-num">5.</span><span>Prices are firm for the duration
          of this order. No escalation is admissible unless agreed in writing
          before dispatch.</span></li>
        <li><span class="tnc-num">6.</span><span>Any change to price, quantity or
          delivery date must be agreed in writing. We will not accept an
          amendment made on your invoice alone.</span></li>
        <li><span class="tnc-num">7.</span><span>This order may be cancelled
          without liability if material is not delivered by the required-by
          date.</span></li>
      </ol>
    </div>
  </div>"""

    note_html = ""
    if po.get("notes"):
        note_html = (f'<div class="po-note"><span class="pn-lbl">Note:</span> '
                     f'{P.esc(po["notes"])}</div>')

    comp_br   = P.esc(po.get("company_branch")) or B.COMPANY_NAME
    signatory = P.esc(po.get("auth_signatory")) or B.COMPANY_SIGNATORY

    # ── Screen-only panel: lifecycle + audit trail ────────────────────────
    status_sel = "".join(
        f'<option{" selected" if s == (po.get("status") or DEFAULT_STATUS) else ""}>{s}</option>'
        for s in PO_STATUSES
    )
    job_link = ""
    if po.get("quotation_id") in STORE["quotations"]:
        jc = job_cost(po["quotation_id"])
        job_link = (f'<a class="po-chip" href="'
                    f'{url_for("quotation.view_quotation", id=po["quotation_id"])}">'
                    f'{P.esc(po.get("quotation_ref"))} &middot; job costing</a>'
                    f'<span class="jc-sub" style="margin-left:.5rem;">'
                    f'quoted &#8377;&nbsp;{jc["quoted"]:,.0f} &middot; '
                    f'committed &#8377;&nbsp;{jc["committed"]:,.0f}</span>')

    panel = f"""
<div class="po-panel">
  <h2>Order status</h2>
  <form method="POST" action="{url_for("purchase.update_purchase", id=id)}">
    <div class="po-panel-row">
      <div class="form-group" style="max-width:230px;margin:0;">
        <label for="status">Status</label>
        <select id="status" name="status">{status_sel}</select>
      </div>
      <div class="form-group" style="flex:1;min-width:220px;margin:0;">
        <label for="note">Note <span style="font-weight:500;text-transform:none;">(optional)</span></label>
        <input type="text" id="note" name="note"
               placeholder="e.g. 6 of 10 received, balance next week"/>
      </div>
      <button type="submit" class="btn">Update</button>
    </div>
  </form>
  {f'<div class="po-strip">{job_link}</div>' if job_link else ''}
  <div class="po-hist">{_history_html(po)}</div>
</div>"""

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(po.get('ref')) + " Purchase Order")}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{PURCHASE_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Purchase Order <span style="color:var(--brand);">{P.esc(po.get('ref'))}</span>
    {_status_badge(po.get('status'))}
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for("purchase.list_purchases")}" class="btn btn-ghost">All Purchase Orders</a>
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>

{_alert(request.args.get("msg"), request.args.get("type", "success"))}
{panel}

<div class="doc-outer">
<div class="quotation-doc">

{DS.sheet_open(show_web=False)}

  <div class="doc-box">
    <div class="doc-title">PURCHASE ORDER</div>
    <div class="doc-sub-po">Order placed on supplier{job_line}</div>

{DS.party_block("To (Supplier)", vendor_block, delivery_block, meta_col_1, meta_col_2)}

    {status_strip}

{DS.items_table(DS.SELL_COLUMNS, table_rows)}

{DS.amount_words("Order Value (in words)", grand)}
  </div>

  {instr_html}
  {note_html}

{DS.sig_block(comp_br, signatory, computer_generated=True)}

{DS.sheet_close()}

</div>
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order</p>
</footer>
</main>
</body></html>"""
    return _page(template)
