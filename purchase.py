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

# ── The upstream links, and why importing these two is not a cycle ───────────
#
# `boq.py` is the schedule a purchase order can now be raised against, and
# `boqpick.py` is the line picker that raising it uses. Neither imports this
# module and neither ever may — `boq.py` links out with `url_for` (the one-way
# trick this repo runs between quotation/proforma, proforma/invoice,
# quotation/purchase, boq/ra, ra/receipt and boq/challan), and `boqpick.py` is a
# leaf that renders no document at all. Both directions are asserted at AST
# level in `tests/test_import_directions.py`.
#
# ⚠ **`po_draft.py` is deliberately NOT imported**, even though
#   `/purchase/from-draft/<id>` reads a draft PO. It is a sibling document
#   module, and coupling two of those for the sake of one dict lookup is what
#   the whole `url_for` arrangement exists to avoid: this module reads
#   `STORE["purchase_orders"]` directly, and `po_draft.py` links *here* by URL.
#   The prohibition runs both ways and is tested both ways.
#
# `project.py` is permitted and is not imported either, for the same reason —
# the project is reached through `STORE["projects"]` and `url_for`.
import boq as BQ
import boqpick as BP

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

# ⚠ **A material purchase order carries the SUPPLY track and never the
# installation one.** A BOQ prices every line twice — once to supply the
# material and once to install it (ABOUT.md §2b) — and the installation amount
# is labour we perform, not goods we buy from a supplier. Putting it on an order
# placed on a vendor would commit us to paying somebody else for our own work.
#
# A named constant rather than an absence, so the rule is findable: this is
# `challan.PRINT_RATES` / `po_draft.PRINT_TAX`'s arrangement. Flipping it is not
# a one-line change — a labour order is a different document with a different
# counterparty — so read this comment before you do.
INCLUDE_INSTALL_TRACK = False

# The prefill for a rate box on `/purchase/from-boq`. `supply_base_rate` is what
# the job was **costed** at before any escalation, which is the closest thing
# this app holds to what we expect to pay for the material. `supply_rate` is the
# escalated figure we SELL it at and is emphatically not it — `po_draft.py`'s
# module docstring makes the same point about the sheet that goes out for
# pricing, and it is the same mistake in a different place.
RATE_PREFILL_FIELD = "supply_base_rate"


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


# =============================================================================
# THE VENDOR — one block, three create paths
# =============================================================================
#
# `/purchase/create`, `/purchase/from-boq` and `/purchase/from-draft` all have
# to answer "who are we buying from", and they must answer it identically: the
# same picker over the same address book, the same two refusals in the same
# order, and the same five fields snapshotted onto the record. Three copies of
# that is three chances for one of them to accept a vendor the others refuse.
#
# So it is extracted here rather than written twice more, and `create_purchase()`
# was changed to call it — the extraction is the point, and a helper only the new
# routes used would be the second copy it exists to prevent. The refusal wording
# and the ordering are unchanged, deliberately, because they are what the
# existing tests read.

def _vendor_from(form) -> tuple:
    """
    Returns `(fields, error)` — the vendor block a PO record carries, or why not.

    **The address book is the only path**, unlike `po_draft.vendor_from()` which
    also takes a typed one-off supplier. That difference is real and is kept: a
    draft PO is a request for a quotation and may go to a fabricator nobody has
    filed, whereas this document commits money and quotes the vendor's GSTIN
    back at them on a record we claim input tax credit against.

    ⚠ **Still not a vendor master** — ABOUT.md §7 gap B6, which now has a third
      consumer rather than two.
    """
    vendor_id = (form.get("vendor_id") or "").strip()
    vendor = STORE["addresses"].get(vendor_id)
    if not vendor_id:
        return {}, "Choose the vendor this order goes to."
    if not vendor:
        return {}, "That vendor is no longer in the address book."
    return {
        "vendor_id":    vendor_id,
        "vendor_name":  vendor.get("company") or vendor.get("label") or "",
        "vendor_gstin": vendor.get("gstin", ""),
        "to":           _addr_block(vendor),
        "vendor_ref":   (form.get("vendor_ref") or "").strip(),
    }, ""


def _vendor_field(selected: str) -> str:
    """The vendor form group — one widget, so three forms cannot offer three."""
    return f"""<div class="form-group">
              <label for="vendor_id">Vendor *</label>
              <select id="vendor_id" name="vendor_id" required>
                {picker_options("— choose vendor —", only_types=("vendor",), selected=selected)}
              </select>
              <small class="field-hint">From the address book, vendors only.
                Add one at <a href="{url_for("address.add_address")}">Address Book</a>
                if the supplier is not listed.</small>
            </div>"""


# =============================================================================
# THE UPSTREAM LINKS — boq_id, project_id, and line_id on every line
# =============================================================================
#
# All three are **optional**, all three default to `""` / absent, and a purchase
# order carrying none of them is the normal case rather than an incomplete one.
# That is the same contract `proforma.prior_invoiced` and `ra.tax_slabs` hold
# to: a new field defaults cleanly, nothing is backfilled, and every record
# written before it existed renders exactly as it did.
#
# ⚠ **`line_id` is the key and `item_no` is a label.** Item numbers restart per
#   section and the client's own section A carries item 17 twice — a flexible
#   sprinkler drop at ₹1,800 and a 150 mm butterfly valve at ₹14,572.50. Keying
#   on it collapsed 87 priced lines into 77 and waved ₹1,99,122.50 of over-claim
#   through on their real schedule (ABOUT.md §3 property 0). Nothing here ever
#   matches on `item_no`; it is carried for the person reading the document.

def _project_name_of(project_id: str) -> str:
    """
    The project's own name, or `""`.

    Stored on the record rather than looked up at render, so the PO still reads
    as a historical document if the project is removed — `proforma.quotation_ref`
    and `ra.boq_ref` make the same call for the same reason.
    """
    proj = (STORE.get("projects") or {}).get(str(project_id or "")) or {}
    return str(proj.get("name") or "")


def _project_of_boq(boq: dict) -> tuple:
    """
    `(project_id, project_name)` a PO inherits from the BOQ it is raised against.

    **Inherited at create and then STORED, never derived.** A PO entered from
    scratch can be tagged to a project with no BOQ behind it at all, so the link
    cannot be a lookup through `boq_id` — there would be nothing to look through.

    ⚠ A BOQ with no `project_id` gives the PO **no project**, and specifically
      does not fall back to the BOQ's free-text `project_name`. That field is a
      display label; `project_id` is the grouping key (project.py's docstring
      says so in as many words), and inventing an id-less project name here
      would put a row on no project's page while looking as though it had one.
    """
    pid = str(boq.get("project_id") or "")
    name = _project_name_of(pid)
    return (pid, name) if name else ("", "")


def _boq_lines_by_id(boq: dict) -> dict:
    """`{line_id: line}` for the BOQ, so a picked row can find its HSN and rate."""
    out = {}
    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            out[lid] = li
    return out


def _po_lines_from_picked(picked: list, boq: dict) -> tuple:
    """
    Returns `(line_items, error)` — `boqpick` rows in this module's line shape.

    The rows are **snapshotted into the PO record here and now**. Nothing on the
    printed order is ever re-read from the live BOQ afterwards, which is not a
    stylistic preference: `print_ra()` looped `boq["line_items"]` instead of the
    bill's own claims, so a line deleted from the schedule vanished from the
    printed table while its amount stayed inside the printed subtotal — an
    invoice whose rows did not add up to its own total, green the whole time
    because every print test rendered against data nobody then touched
    (ABOUT.md §5, `/ra/print` reads the RECORD).

    A **specification header** comes across carrying its clause and no money, so
    the supplier can read what they are being asked to supply (DOMAIN.md §2.2).
    It has no quantity, no rate and no amount, and is excluded from both totals.
    """
    by_lid = _boq_lines_by_id(boq)
    items = []
    for row in picked:
        lid = str(row.get("line_id") or "")
        src = by_lid.get(lid) or {}
        if row.get("is_header"):
            items.append({
                "type":      "item",
                "is_header": True,
                "line_id":   lid,
                "name":      str(row.get("description") or ""),
                "part_no":   str(row.get("item_no") or ""),
                "hsn":       "",
                "qty":       0.0,
                "unit":      "",
                "price":     0.0,
                "total":     0.0,
                "depth":     0,
            })
            continue

        qty = float(row.get("qty") or 0.0)
        if qty <= 0:
            return [], (f"Quantity for item {row.get('item_no') or '(unnumbered)'} "
                        f"must be greater than zero.")
        rate = float(row.get("rate") or 0.0)
        if rate < 0:
            return [], (f"Rate for item {row.get('item_no') or '(unnumbered)'} "
                        f"cannot be negative.")

        items.append({
            "type":      "item",
            "is_header": False,
            # THE key. Carried so this row can be traced back to the schedule
            # line it was ordered against however the item numbers are later
            # renumbered by a revision.
            "line_id":   lid,
            "name":      str(row.get("description") or ""),
            "part_no":   str(row.get("item_no") or ""),
            # The BOQ line carries a supply HSN and an installation SAC. Only
            # the supply code belongs on a material order — INCLUDE_INSTALL_TRACK.
            "hsn":       str(src.get("supply_hsn") or ""),
            "qty":       qty,
            "unit":      str(row.get("unit") or ""),
            "price":     rate,
            "total":     round(rate * qty, 2),
            "depth":     0,
        })

    if not any(not r["is_header"] for r in items):
        return [], "Add at least one item to the purchase order."
    return items, ""


def _totals_of(items: list, tax_type: str, cgst: float, igst: float) -> tuple:
    """
    `(subtotal, tax_info, grand_total, total_qty)` for a set of PO lines.

    The same `quotation._tax_lines()` every purchase order has always used, with
    SGST forced equal to CGST exactly as the create form forces it. The tax is
    **input** tax we pay — the opposite side of the ledger from a tax invoice —
    and none of that arithmetic is shared with the sell chain, only the
    furniture it prints inside.
    """
    subtotal = round(sum(float(r.get("total") or 0.0) for r in items), 2)
    tax_info = _tax_lines(subtotal, tax_type,
                          cgst_rate=cgst, sgst_rate=cgst, igst_rate=igst)
    grand = round(subtotal + float(tax_info.get("total") or 0.0), 2)
    total_qty = round(sum(float(r.get("qty") or 0.0) for r in items), 3)
    return subtotal, tax_info, grand, total_qty


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
# CSS — the two BOQ-side create forms ONLY
# =============================================================================
#
# ⚠ **This is deliberately a SEPARATE constant from `PURCHASE_STYLES`, and the
#   reason is measurable.** `PURCHASE_STYLES` is loaded by `/purchase/view`,
#   which `tests/test_print_golden.py` hashes byte-for-byte — so a rule added
#   there for a form moves the digest of a printed document that did not change.
#   The two pages below are the only ones that draw a picker or a rate column,
#   so their rules load only on them.
#
# `BP.PICKER_CSS` is spliced in at the top exactly as `po_draft.PO_STYLES`
# splices it, because `challan.CHALLAN_STYLES` established that a second
# consumer wraps the same raw CSS afresh rather than importing the first
# consumer's sheet. `.pk-rate` is added *here* rather than to `PICKER_CSS` for
# the same golden reason — `/po/create` renders no rate column and must not
# carry a rule for one.
FROM_BOQ_STYLES = "\n<style>\n" + BP.PICKER_CSS + """
  .pk-rate { width:112px; }
  .pk-rate input {
    width:100%; padding:.28rem .4rem; border:1px solid var(--border);
    border-radius:6px; font:inherit; text-align:right;
  }

  /* The amber band. Same shape and same severity as ra.py's over-claim and
     party-drift bands, and the same rule behind it (DOMAIN.md §6): surface it,
     name it, never silently correct it. Amber, not red — nothing is broken,
     but nothing here may go out unread. */
  .up-warn {
    background:#FFF8E6; border:1px solid #E8C86A; border-left:3px solid #C79200;
    border-radius:var(--radius); padding:.85rem 1.1rem; margin-bottom:1.2rem;
    font-size:.86rem; line-height:1.6;
  }
  .up-warn b { color:#7A5A00; }
  .up-warn .uw-chips { margin-top:.45rem; display:flex; gap:.4rem; flex-wrap:wrap; }

  /* The from-draft line table. product.py's repeating-row pattern, which this
     module's own line editor already uses — there is nothing to PICK when
     converting a draft, because the draft IS the selection. */
  .dl-head, .dl-row {
    display:grid; grid-template-columns:74px 1fr 70px 96px 112px;
    gap:.55rem; align-items:center;
  }
  .dl-head {
    font-size:.7rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.06em; margin-bottom:.4rem;
  }
  .dl-row { padding:.35rem 0; border-bottom:1px solid var(--border); }
  .dl-row input {
    width:100%; padding:.28rem .4rem; border:1px solid var(--border);
    border-radius:6px; font:inherit; text-align:right;
  }
  .dl-no { font-weight:600; font-size:.84rem; }
  .dl-desc { font-size:.84rem; }
  .dl-unit { font-size:.84rem; color:var(--muted); }
  .dl-avail { font-size:.84rem; color:var(--muted); text-align:right;
              font-variant-numeric:tabular-nums; }
  .dl-spec { grid-column:1 / -1; font-size:.82rem; color:var(--muted);
             font-weight:600; padding:.4rem 0 .1rem; }
  @media (max-width:640px){
    .dl-head, .dl-row { grid-template-columns:60px 1fr 90px 100px; }
    .dl-head span:nth-child(4), .dl-row .dl-avail { display:none; }
  }
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
        qid       = (f.get("quotation_id") or "").strip()
        status    = (f.get("status") or DEFAULT_STATUS).strip()

        # One vendor block, shared with the two BOQ-side create paths. The two
        # refusals and their order are exactly what they always were.
        vendor_fields, vendor_err = _vendor_from(f)

        tax_type  = (f.get("tax_type") or "exempt").strip()
        cgst = P.parse_money(f.get("cgst_rate"))
        igst = P.parse_money(f.get("igst_rate"))

        items, line_err = _parse_lines(f)

        if not po_date:
            error = "Purchase order date is required."
        elif vendor_err:
            error = vendor_err
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
                **vendor_fields,

                # ── Optional soft links upstream. NEVER hard parents. ─────
                # Every one of these may be "" and that is the normal case for
                # an order entered from scratch — stock and consumables get
                # bought with no deal, no schedule and no project behind them.
                # Any code walking purchases must assume nothing.
                "quotation_id":  qid,
                "quotation_ref": q.get("ref", ""),
                "project_id":    (f.get("project_id") or "").strip(),
                "project_name":  _project_name_of((f.get("project_id") or "").strip()),
                "boq_id":        "",
                "boq_ref":       "",
                "boq_rev_no":    0,
                "draft_id":      "",
                "draft_ref":     "",

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


# =============================================================================
# RAISING A REAL PO FROM THE BOQ CHAIN
# =============================================================================
#
# Until this existed, work raised from a bill of quantities dead-ended at a
# **draft** PO (`SF/DPO/nnnn`) — a rate-less sheet sent to a supplier to be
# priced, with no way back. The priced copy came in on paper and was re-keyed
# into `/purchase/create` from scratch, with no link between the two documents
# and, more expensively, **no link from the money we actually spent to the
# project we spent it on** (ABOUT.md §7, the largest open gap in that list).
#
# Two routes close it, and both land in the ordinary register with the ordinary
# `SF/PO/26-27/nnnn` series:
#
#   /purchase/from-boq/<boq_id>       tick the lines, price them, order them
#   /purchase/from-draft/<draft_id>   the draft comes back priced; make it real
#
# Neither introduces a draft state, an approval step or a status of its own. The
# record they write is the same record `/purchase/create` writes, with three
# optional fields filled in — which is why a PO that has none of them is
# completely unaffected and renders byte-for-byte what it always did.

def _form_values(f, is_post: bool, **defaults) -> dict:
    """
    The order's own fields — the user's input on a rejected POST, else defaults.

    `create_purchase()`'s `_v()` contract, which is `address._validate()`'s:
    **a rejected form re-renders with what was typed** and nothing is written.
    """
    def v(name, fallback=""):
        if is_post:
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    return {
        "date":             v("date", defaults.get("date") or _today()),
        "vendor_id":        v("vendor_id", defaults.get("vendor_id", "")),
        "status":           v("status", DEFAULT_STATUS),
        "vendor_ref":       v("vendor_ref", defaults.get("vendor_ref", "")),
        "delivery_date":    v("delivery_date"),
        "delivery_to":      v("delivery_to",
                              defaults.get("delivery_to") or B.COMPANY_ADDR),
        "tax_type":         v("tax_type", "cgst_sgst"),
        "cgst_rate":        v("cgst_rate", "9"),
        "igst_rate":        v("igst_rate", "18"),
        "payment_terms":    v("payment_terms"),
        "delivery_terms":   v("delivery_terms"),
        "dispatch_through": v("dispatch_through"),
        "incoterms":        v("incoterms"),
        "notes":            v("notes", defaults.get("notes", "")),
    }


def _upstream_form(*, title: str, action: str, back_html: str, intro_html: str,
                   banner_html: str, lines_section: str, data: dict,
                   error: str, onsubmit: str = "true") -> str:
    """
    One form, two routes.

    The order's own fields — date, vendor, status, tax, terms — are identical
    whichever upstream document the lines came from, so they are written once.
    Only the **lines** differ: `/from-boq` renders `boqpick`'s grid, `/from-draft`
    renders the draft's own rows, because there is nothing left to pick once a
    draft has been raised.

    Every widget is the shared one: `_vendor_field()` for the supplier, and
    `_sel_opts` over `_PAY_TERMS` / `_DEL_TERMS` / `_DISPATCH` / `_INCOTERMS` for
    the terms — "By Road Transport" must mean the same thing whichever way the
    goods move, and whichever form asked.
    """
    status_opts = "".join(
        f'<option{" selected" if s == data["status"] else ""}>{s}</option>'
        for s in PO_STATUSES if s != "Cancelled"
    )
    return _page(f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title(title)}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}{FROM_BOQ_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>{title}</h1>
        <div style="display:flex;gap:.7rem;flex-wrap:wrap;">{back_html}</div>
      </div>

      {_alert(error, "error")}
      {banner_html}

      <div class="buy-note">
        This is the <b>buy side</b> &mdash; a <b>real purchase order we place on a
        vendor</b>, in the ordinary register and the ordinary series.
        <div class="bn-sub">{intro_html}
          The next number is {P.esc(_next_ref(data["date"]))}.</div>
      </div>

      <form method="POST" action="{action}" onsubmit="return {onsubmit};">
        <input type="hidden" name="po_json" id="po_json" value=""/>

        <div class="form-section">
          <div class="section-title">Order</div>
          <div class="fg3">
            <div class="form-group">
              <label for="date">PO Date *</label>
              <input type="date" id="date" name="date" value="{P.esc(data['date'])}" required/>
            </div>
            {_vendor_field(data["vendor_id"])}
            <div class="form-group">
              <label for="status">Status</label>
              <select id="status" name="status">{status_opts}</select>
              <small class="field-hint">The ordinary lifecycle &mdash; Draft while
                you are still pricing it, Issued once it has gone to the vendor.
                There is no extra approval step on this path.</small>
            </div>
            <div class="form-group">
              <label for="vendor_ref">Vendor's Offer / Quote Ref</label>
              <input type="text" id="vendor_ref" name="vendor_ref"
                     value="{P.esc(data['vendor_ref'])}"
                     placeholder="their quotation no., if any"/>
            </div>
            <div class="form-group">
              <label for="delivery_date">Wanted By</label>
              <input type="date" id="delivery_date" name="delivery_date"
                     value="{P.esc(data['delivery_date'])}"/>
            </div>
          </div>
        </div>

        {lines_section}

        <div class="form-section">
          <div class="section-title">Tax the vendor will charge us</div>
          <div class="fg3">
            <div class="form-group">
              <label for="tax_type">Tax Type</label>
              <select id="tax_type" name="tax_type">
                <option value="cgst_sgst"{" selected" if data["tax_type"] == "cgst_sgst" else ""}>CGST + SGST (intra-state)</option>
                <option value="igst"{" selected" if data["tax_type"] == "igst" else ""}>IGST (inter-state)</option>
                <option value="exempt"{" selected" if data["tax_type"] == "exempt" else ""}>Exempt / Nil</option>
              </select>
            </div>
            <div class="form-group">
              <label for="cgst_rate">CGST % <span style="font-weight:500;text-transform:none;">(SGST matches)</span></label>
              <input type="number" id="cgst_rate" name="cgst_rate"
                     value="{P.esc(data['cgst_rate'])}" min="0" step="any"/>
            </div>
            <div class="form-group">
              <label for="igst_rate">IGST %</label>
              <input type="number" id="igst_rate" name="igst_rate"
                     value="{P.esc(data['igst_rate'])}" min="0" step="any"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Terms &amp; delivery</div>
          <div class="fg2">
            <div class="form-group">
              <label for="payment_terms">Payment Terms</label>
              {_sel_opts("payment_terms", _PAY_TERMS, _PAY_TERMS[0], data["payment_terms"])}
            </div>
            <div class="form-group">
              <label for="delivery_terms">Terms of Delivery</label>
              {_sel_opts("delivery_terms", _DEL_TERMS, _DEL_TERMS[0], data["delivery_terms"])}
            </div>
            <div class="form-group">
              <label for="dispatch_through">Dispatch Through</label>
              {_sel_opts("dispatch_through", _DISPATCH, _DISPATCH[0], data["dispatch_through"])}
            </div>
            <div class="form-group">
              <label for="incoterms">Incoterms</label>
              {_sel_opts("incoterms", _INCOTERMS, _INCOTERMS[0], data["incoterms"])}
            </div>
            <div class="form-group span2">
              <label for="delivery_to">Deliver To</label>
              <textarea id="delivery_to" name="delivery_to" rows="3"
                placeholder="our stores, or the project site">{P.esc(data['delivery_to'])}</textarea>
            </div>
            <div class="form-group span2">
              <label for="notes">Note on the order <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <input type="text" id="notes" name="notes" value="{P.esc(data['notes'])}"
                     placeholder="e.g. Urgent — required at site by month end"/>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn">Raise Purchase Order</button>
          {back_html}
        </div>
      </form>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order</p></footer>
    </main></body></html>""")


def _write_upstream_po(*, data: dict, vendor_fields: dict, items: list,
                       boq: dict = None, project_id: str = "",
                       project_name: str = "", draft: dict = None,
                       origin: str = "") -> dict:
    """
    Write the purchase order. **One record shape, whichever route got here.**

    It is the same record `create_purchase()` writes — same collection, same
    `SF/PO/26-27/nnnn` series, same lifecycle, same audit trail. The only
    difference is that three optional fields are filled in. There is no draft
    flag, no approval gate and no status this app would have to teach anybody to
    clear; a purchase order raised from a schedule is a purchase order.
    """
    boq = boq or {}
    tax_type = data["tax_type"]
    cgst = P.parse_money(data["cgst_rate"])
    igst = P.parse_money(data["igst_rate"])
    subtotal, tax_info, grand, total_qty = _totals_of(items, tax_type, cgst, igst)

    pid = str(uuid.uuid4())
    po = {
        "id":   pid,
        "ref":  _next_ref(data["date"]),
        "fy":   P.fy_of(data["date"]),
        "date": data["date"],

        **vendor_fields,

        # ── The upstream links. All optional; all STORED, never derived. ──
        "quotation_id":  "",
        "quotation_ref": "",
        "boq_id":        str(boq.get("id") or ""),
        "boq_ref":       str(boq.get("ref") or ""),
        "boq_rev_no":    int(boq.get("rev_no") or 0),
        "project_id":    project_id,
        "project_name":  project_name,
        "draft_id":      str((draft or {}).get("id") or ""),
        "draft_ref":     str((draft or {}).get("ref") or ""),

        "line_items":  items,
        "subtotal":    subtotal,
        "tax_type":    tax_type,
        "tax_info":    tax_info,
        "grand_total": grand,
        "total_qty":   total_qty,

        "delivery_date":    data["delivery_date"],
        "delivery_to":      data["delivery_to"],
        "payment_terms":    data["payment_terms"],
        "delivery_terms":   data["delivery_terms"],
        "dispatch_through": data["dispatch_through"],
        "incoterms":        data["incoterms"],

        "status":         data["status"],
        "status_history": [],
        "notes":          data["notes"],
        "company_branch": "",
        "auth_signatory": "",
    }
    _log(po, f"Purchase order {po['ref']} raised on "
             f"{po.get('vendor_name') or 'vendor'} for &#8377;{grand:,.0f}"
             f"{origin}.",
         status_to=data["status"])
    STORE["purchases"][pid] = po
    return po


@purchase_bp.route("/from-boq/<boq_id>", methods=["GET", "POST"])
def from_boq(boq_id: str):
    """
    Raise a **real** purchase order against a bill of quantities.

    The grid is `boqpick.py`'s — the same one `/po/create` and `/dc/create`
    render, imported rather than copied a third time, which is the entire reason
    that leaf exists. What this route adds to it is a **rate box per line**,
    prefilled from the schedule's `supply_base_rate` and editable.

    Three rules worth knowing before editing:

    * **The installation track is excluded** (`INCLUDE_INSTALL_TRACK`). A BOQ
      line is priced to supply and to install; only the first is goods we buy.
    * **Matching is on `line_id`.** `item_no` is a display label and is not
      unique even within a section — the seeded Sify schedule has 87 priced
      lines and 77 distinct item numbers.
    * **A superseded revision is refused at the route**, exactly as `/ra/create`
      and `/dc/create` refuse one. `/boq/view` also hides the link, but a link
      is not a guard.
    """
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="Choose a bill of quantities to order against.",
                                type="error"))
    if boq_id in BQ.superseded_ids():
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg="That schedule has been superseded. Raise the "
                                    "purchase order against the current revision.",
                                type="error"))

    project_id, project_name = _project_of_boq(boq)
    is_post = request.method == "POST"
    f = request.form
    data = _form_values(f, is_post)
    error = ""
    chosen = qty_of = rate_of = None

    if is_post:
        vendor_fields, error = _vendor_from(f)
        if not data["date"]:
            error = "Purchase order date is required."
        elif data["status"] not in PO_STATUSES:
            error = error or "Invalid status."

        picked, line_err = ([], "") if error else BP.picked_lines(
            f.get("po_json") or "", boq, with_pcs=False, with_rate=True,
            max_lines=BQ.MAX_LINES,
            empty_msg=("No lines are ticked. A purchase order with nothing on "
                       "it is not a document — tick at least one line, or cancel."),
            cap_msg="Raise more than one order.")
        error = error or line_err

        items, shape_err = ([], "") if error else _po_lines_from_picked(picked, boq)
        error = error or shape_err

        if not error:
            po = _write_upstream_po(
                data=data, vendor_fields=vendor_fields, items=items, boq=boq,
                project_id=project_id, project_name=project_name,
                origin=f", against {boq.get('ref') or 'a schedule'}")
            return redirect(url_for("purchase.view_purchase", id=po["id"],
                                    msg=f"Purchase order {po['ref']} created "
                                        f"against {boq.get('ref') or 'the schedule'}.",
                                    type="success"))

        # Hand the operator back exactly what they ticked and typed.
        chosen, qty_of, rate_of = _replay_picked(f.get("po_json") or "")

    boq_ref = P.esc(boq.get("ref") or "")
    proj_bit = (f' &middot; project <b>{P.esc(project_name)}</b>'
                if project_name else
                ' &middot; <span style="color:var(--muted);">this schedule is not '
                'attached to a project, so the order will carry none</span>')

    lines_section = BP.grid_html(
        boq,
        title="Lines to order",
        intro_html=f"""        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line is ticked to start with, because most orders are the whole
          schedule. Untick what this supplier is not supplying, and change a
          quantity where you want less than the schedule shows.
          <b>Rates open at the schedule's supply base rate</b> &mdash; what the job
          was costed at — and are yours to edit; what you leave in the box is what
          is stored. The <b>installation</b> rates are labour and are deliberately
          not offered here.
        </p>""",
        qty_label="Order qty",
        qty_aria="Order quantity",
        empty_note=("Nothing is ticked. A purchase order with no lines on it "
                    "is not a document."),
        payload_id="po_json",
        doc_word="purchase order",
        chosen=chosen,
        qty_of=qty_of,
        with_rate=True,
        rate_of=rate_of,
        rate_label="Rate (&#8377;)",
        rate_aria="Rate")

    back_html = (f'<a href="{url_for("boq.view_boq", id=boq_id)}" '
                 f'class="btn btn-ghost">&#8592; {boq_ref}</a>')
    return _upstream_form(
        title="Purchase Order from BOQ",
        action=url_for("purchase.from_boq", boq_id=boq_id),
        back_html=back_html,
        intro_html=(f'Against <b>{boq_ref}</b> &middot; '
                    f'{P.esc(boq.get("project_name") or "")}{proj_bit}.'),
        banner_html="",
        lines_section=lines_section,
        data=data,
        error=error,
        onsubmit="saveJSON()")


def _replay_picked(raw: str) -> tuple:
    """
    `(chosen, qty_of, rate_of)` off a rejected POST, so nothing typed is lost.

    `po_draft.create_po()`'s arrangement, with the rate column added. A form
    that throws the operator's ticks away on a validation failure is worse than
    no validation on a 97-line schedule.
    """
    import json
    try:
        rows = (json.loads(raw or "{}").get("lines") or [])
    except (ValueError, TypeError):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    return ({BQ._line_id(r.get("line_id")) for r in rows},
            {BQ._line_id(r.get("line_id")): r.get("qty") for r in rows},
            {BQ._line_id(r.get("line_id")): r.get("rate") for r in rows})


@purchase_bp.route("/from-draft/<draft_id>", methods=["GET", "POST"])
def from_draft(draft_id: str):
    """
    Turn a priced draft PO into a real one.

    ⚠ **This route lives here and not in `po_draft.py`, deliberately.** It
    writes a `purchases` record, so it belongs to the module that owns that
    shape; putting it there would force `po_draft.py` to import this module and
    couple two document modules for no reason at all. `po_draft.py` links here
    by URL — the one-way trick, used a seventh time.

    **The draft is kept, never deleted.** It is the record of what was sent out
    for pricing, and destroying it the moment it succeeds would throw away the
    only evidence of what was asked and of whom.

    **Converting twice is allowed and warned about.** Two purchase orders off one
    request for quotation is an ordinary thing when an order is split between
    suppliers or placed in two lots, so this warns in an amber band naming the
    orders already raised — `ra.prev_balance_drift()`'s and `ra.party_drift()`'s
    shape — and lets it through. DOMAIN.md §6: surface it, name it, never
    silently refuse it.
    """
    drafts = STORE.get("purchase_orders") or {}
    draft = drafts.get(draft_id)
    if not draft:
        return redirect(url_for("po_draft.list_pos",
                                msg="That draft PO no longer exists.", type="error"))

    # The BOQ may legitimately be gone; the draft is a snapshot and still
    # converts. Its rates then have no base to fall back on, which is stated on
    # the form rather than silently producing zeros.
    boq = (STORE.get("boqs") or {}).get(str(draft.get("boq_id") or "")) or {}
    base_of = {}
    for lid, li in _boq_lines_by_id(boq).items():
        base = li.get(RATE_PREFILL_FIELD)
        base_of[lid] = None if base is None else float(base)

    project_id, project_name = _project_of_boq(boq)

    # Only rows with something to buy. A draft carries its specification headers
    # for the supplier to read, and those come across unchanged.
    rows = list(draft.get("items") or [])

    is_post = request.method == "POST"
    f = request.form
    # The draft's own vendor prefills the picker ONLY when it came from the
    # address book. A typed one-off supplier has no id to select, and this
    # document may not carry one — see `_vendor_from()`.
    data = _form_values(f, is_post,
                        vendor_id=(draft.get("vendor_id") or ""),
                        delivery_to=draft.get("delivery_to") or "",
                        notes=draft.get("notes") or "")
    error = ""
    posted_qty, posted_rate = {}, {}

    if is_post:
        posted_qty = dict(zip(f.getlist("dl_line_id"), f.getlist("dl_qty")))
        posted_rate = dict(zip(f.getlist("dl_line_id"), f.getlist("dl_rate")))

        vendor_fields, error = _vendor_from(f)
        if not data["date"]:
            error = "Purchase order date is required."
        elif data["status"] not in PO_STATUSES:
            error = error or "Invalid status."

        items = []
        if not error:
            for row in rows:
                lid = str(row.get("line_id") or "")
                if row.get("is_header"):
                    items.append({
                        "type": "item", "is_header": True, "line_id": lid,
                        "name": str(row.get("description") or ""),
                        "part_no": str(row.get("item_no") or ""),
                        "hsn": "", "qty": 0.0, "unit": "", "price": 0.0,
                        "total": 0.0, "depth": 0,
                    })
                    continue
                qty = BQ._num(posted_qty.get(lid), None)
                if qty is None or qty < 0:
                    qty = float(row.get("qty") or 0.0)
                if qty <= 0:
                    error = (f"Quantity for item {row.get('item_no') or '(unnumbered)'} "
                             f"must be greater than zero.")
                    break
                rate = BQ._num(posted_rate.get(lid), None)
                if rate is None or rate < 0:
                    rate = _draft_rate_of(row, base_of)
                src = _boq_lines_by_id(boq).get(lid) or {}
                items.append({
                    "type": "item", "is_header": False, "line_id": lid,
                    "name": str(row.get("description") or ""),
                    "part_no": str(row.get("item_no") or ""),
                    "hsn": str(src.get("supply_hsn") or ""),
                    "qty": float(qty), "unit": str(row.get("unit") or ""),
                    "price": float(rate),
                    "total": round(float(rate) * float(qty), 2),
                    "depth": 0,
                })
            if not error and not any(not r["is_header"] for r in items):
                error = "This draft PO has no lines to order."

        if not error:
            po = _write_upstream_po(
                data=data, vendor_fields=vendor_fields, items=items, boq=boq,
                project_id=project_id, project_name=project_name, draft=draft,
                origin=f", converted from draft {draft.get('ref') or ''}".rstrip())
            # The link back, on the draft. A LIST, not a scalar: converting twice
            # is permitted, and a single field would let the second conversion
            # quietly erase the first one's trail.
            draft.setdefault("converted_po_ids", []).append(po["id"])
            return redirect(url_for("purchase.view_purchase", id=po["id"],
                                    msg=f"Purchase order {po['ref']} created from "
                                        f"draft {draft.get('ref') or 'PO'}.",
                                    type="success"))

    # ── The lines. Not the picker: a draft IS the selection. ──────────────
    lines_html = ""
    for row in rows:
        lid = P.esc(str(row.get("line_id") or ""))
        if row.get("is_header"):
            lines_html += (f'<div class="dl-row"><div class="dl-spec">'
                           f'{P.esc(row.get("item_no") or "")} &middot; '
                           f'{P.esc(str(row.get("description") or "")[:160])}</div></div>')
            continue
        raw_lid = str(row.get("line_id") or "")
        qty_v = posted_qty.get(raw_lid)
        if qty_v is None:
            qty_v = BQ._fmt_qty(float(row.get("qty") or 0.0))
        rate_v = posted_rate.get(raw_lid)
        if rate_v is None:
            r = _draft_rate_of(row, base_of, blank_when_unknown=True)
            rate_v = "" if r is None else f"{float(r):.2f}"
        lines_html += f"""
        <div class="dl-row">
          <span class="dl-no">{P.esc(row.get("item_no") or "")}</span>
          <span class="dl-desc">{P.esc(" ".join(str(row.get("description") or "").split())[:180])}</span>
          <span class="dl-unit">{P.esc(row.get("unit") or "")}</span>
          <input type="hidden" name="dl_line_id" value="{lid}"/>
          <input type="text" inputmode="decimal" name="dl_qty" value="{P.esc(qty_v)}"
                 aria-label="Order quantity"/>
          <input type="text" inputmode="decimal" name="dl_rate" value="{P.esc(rate_v)}"
                 aria-label="Rate"/>
        </div>"""

    rate_note = ("Rates open at the schedule's supply base rate and are yours to "
                 "edit." if boq else
                 "The bill of quantities behind this draft is no longer in the "
                 "system, so there is no base rate to open with — every rate has "
                 "to be typed.")
    lines_section = f"""
      <div class="form-section">
        <div class="section-title">Lines carried from the draft</div>
        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line on the draft comes across with its BOQ line id, so this order
          stays traceable to the schedule it was measured from. {rate_note}
          The draft itself is <b>kept</b> — it is the record of what was sent out
          to be priced.
        </p>
        <div class="dl-head">
          <span>Item</span><span>Description</span><span>Unit</span>
          <span style="text-align:right;">Qty</span>
          <span style="text-align:right;">Rate (&#8377;)</span>
        </div>
        {lines_html or '<p style="font-size:.85rem;color:var(--muted);">This draft PO carries no lines.</p>'}
      </div>"""

    # ── The amber band, on a second conversion ────────────────────────────
    banner_html = ""
    already = [pid_ for pid_ in (draft.get("converted_po_ids") or [])
               if pid_ in STORE["purchases"]]
    if already:
        chips = "".join(
            f'<a class="po-chip" href="{url_for("purchase.view_purchase", id=pid_)}">'
            f'{P.esc(STORE["purchases"][pid_].get("ref"))}</a>'
            for pid_ in already)
        banner_html = (
            f'<div class="up-warn">'
            f'<b>Draft {P.esc(draft.get("ref"))} has already been converted.</b> '
            f'{len(already)} purchase order{"" if len(already) == 1 else "s"} '
            f'already exist{"s" if len(already) == 1 else ""} against it, so '
            f'converting again will order this material a second time.'
            f'<br/>That is not blocked, because splitting one request for '
            f'quotation across two orders is an ordinary thing — but check the '
            f'quantities below before you raise it.'
            f'<div class="uw-chips">{chips}</div></div>')

    typed_note = ""
    if not draft.get("vendor_id") and draft.get("vendor_name"):
        typed_note = (f' The draft went to <b>{P.esc(draft.get("vendor_name"))}</b>, '
                      f'who is not in the address book — a real order has to name a '
                      f'vendor from it, so add them first or pick whoever is '
                      f'actually supplying.')

    back_html = (f'<a href="{url_for("po_draft.view_po", id=draft_id)}" '
                 f'class="btn btn-ghost">&#8592; {P.esc(draft.get("ref"))}</a>')
    return _upstream_form(
        title="Purchase Order from Draft",
        action=url_for("purchase.from_draft", draft_id=draft_id),
        back_html=back_html,
        intro_html=(f'Converted from draft <b>{P.esc(draft.get("ref"))}</b>'
                    f'{" &middot; " + P.esc(boq.get("ref")) if boq.get("ref") else ""}'
                    f'{" &middot; project <b>" + P.esc(project_name) + "</b>" if project_name else ""}.'
                    f'{typed_note}'),
        banner_html=banner_html,
        lines_section=lines_section,
        data=data,
        error=error)


def _draft_rate_of(row: dict, base_of: dict, blank_when_unknown: bool = False):
    """
    A converted line's opening rate — **the draft first, the BOQ second**.

    A draft PO carries no rates today (`po_draft.PRINT_RATES` is False and the
    whole document exists so the supplier fills them in), so in practice this
    always falls through to the schedule's supply base rate. It reads the draft
    first anyway, because ABOUT.md §7 gap B7 names capturing the supplier's
    quoted rates against a draft as the natural next piece of work — and when
    that lands, a rate the supplier actually quoted must beat what we costed the
    job at rather than being silently ignored.
    """
    quoted = row.get("rate")
    if quoted is not None:
        parsed = BQ._num(quoted, None)
        if parsed is not None and parsed >= 0:
            return float(parsed)
    base = base_of.get(str(row.get("line_id") or ""))
    if base is None:
        return None if blank_when_unknown else 0.0
    return float(base)


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
        # A specification header, carried down from a BOQ line's parent clause
        # so the supplier can read what they are being asked to supply
        # (DOMAIN.md §2.2). It carries no quantity, no rate and no amount, takes
        # no serial number, and contributes nothing to either total.
        #
        # Orders entered from scratch have no such row — `_parse_lines()` cannot
        # produce one — so this branch is never taken on a PO raised at
        # `/purchase/create`, and that document is byte-for-byte what it was.
        if row.get("is_header"):
            table_rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>
          <td colspan="6" class="c-desc">{P.esc(row.get('name'))}</td>
        </tr>"""
            continue
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
    # ── Where this order came from, when it came from anywhere ────────────
    #
    # ⚠ **Every one of these is conditional and the whole strip collapses to the
    #   empty string when the order has no upstream link.** That is what makes
    #   an order entered from scratch render byte-for-byte what it always did,
    #   which `tests/test_print_golden.py` measures rather than trusts. Note
    #   there is no literal whitespace around `{upstream_html}` at its insertion
    #   point below, for exactly that reason.
    #
    # The refs are read off the RECORD; the id is only used to build the link
    # and to check the target still exists. A BOQ or a project that has been
    # removed leaves the order still naming what it was raised against, in
    # plain text — `proforma.quotation_ref`'s contract.
    up_chips = ""
    if po.get("boq_ref") or po.get("boq_id"):
        label = P.esc(po.get("boq_ref")) or "the schedule"
        if po.get("boq_id") in (STORE.get("boqs") or {}):
            up_chips += (f'<a class="po-chip" href="'
                         f'{url_for("boq.view_boq", id=po["boq_id"])}">'
                         f'{label} &middot; schedule</a>')
        else:
            up_chips += f'<span class="po-chip">{label} &middot; schedule</span>'
    if po.get("draft_ref") or po.get("draft_id"):
        label = P.esc(po.get("draft_ref")) or "draft PO"
        if po.get("draft_id") in (STORE.get("purchase_orders") or {}):
            up_chips += (f'<a class="po-chip" href="'
                         f'{url_for("po_draft.view_po", id=po["draft_id"])}">'
                         f'{label} &middot; draft</a>')
        else:
            up_chips += f'<span class="po-chip">{label} &middot; draft</span>'
    if po.get("project_id") or po.get("project_name"):
        label = P.esc(po.get("project_name")) or "project"
        if po.get("project_id") in (STORE.get("projects") or {}):
            up_chips += (f'<a class="po-chip" href="'
                         f'{url_for("projectview.view_project", id=po["project_id"])}">'
                         f'{label} &middot; project</a>')
        else:
            up_chips += f'<span class="po-chip">{label} &middot; project</span>'
    upstream_html = (f'<div class="po-strip">{up_chips}</div>' if up_chips else "")

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
  {f'<div class="po-strip">{job_link}</div>' if job_link else ''}{upstream_html}
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
