"""
po_draft.py — Draft Purchase Order from a BOQ
=============================================
Blueprint  : po_draft_bp
Mounted at : /po  (registered in app.py)

CLIENT_CHANGES.md item 4. A BOQ-side document that goes to a supplier asking
them to price the material a schedule needs.

Routes
------
  GET       /po/              — register of draft POs
  GET,POST  /po/create?boq=   — pick the lines, pick the vendor, raise the draft
  GET       /po/view/<id>     — the document, with the action bar
  GET       /po/print/<id>    — the document alone, ready for Ctrl+P
  GET,POST  /po/edit/<id>     — vendor, date and notes only
  GET,POST  /po/delete/<id>   — GET confirms, POST deletes

Why this is NOT `purchase.py`
-----------------------------
Two client constraints, and both are hard:

* **ONE running PO number series** across all suppliers and all sites, so it
  can continue the numbers they already keep on paper.
* **NO GST on these POs.** Not a zero-rated block — no block at all.

`purchase.py` satisfies neither: it computes CGST/SGST/IGST on every order and
numbers through a financial-year-scoped series. It is also on `boq.py`'s
prohibited-import list. Merging the two would put the client's "no GST" rule
onto a record that legitimately needs GST — the buy-side PO records **input tax
we pay**, and that is real money against our own liability.

**Separate behaviour, shared appearance.** The document renders through
`docsheet.py`, which is the same A4 sheet `purchase.py` prints on: same
letterhead, same party block, same table shell, same signature. What differs is
only what the client asked for — no GST block, blank rates, and a `Pcs` column
beside `Qty` (DOMAIN.md §5.2).

**Rates are blank BY DESIGN**, not unfinished. The document goes to a supplier
*to be priced*. Nothing on it may read a buy rate from anywhere: not from the
catalogue, not from the BOQ's own supply rate. The BOQ rate is what we sell the
work for, and putting it in front of the person quoting us is the one thing this
document must never do.

Its OWN collection
------------------
`STORE["purchase_orders"]`, keyed by UUID, pointing at the BOQ it came from —
CLIENT_CHANGES.md §1.3. Separate from `purchases`, which is the buy-side PO.

Import direction
----------------
    po_draft.py ──► boq.py       superseded_ids, _item_no, _line_id, _fmt_qty
    po_draft.py ──► boqpick.py   the BOQ line picker — the grid, the fold,
                                 the payload parser. Shared with challan.py
    po_draft.py ──► docsheet.py  the printed A4 sheet
    po_draft.py ──► address.py   the vendor picker
    po_draft.py ──► settings.py  the number series (§ numbering below)
    po_draft.py ──► quotation.py QUOTATION_STYLES + _inr — the form widgets
    po_draft.py ──► dashboard.py BASE_STYLES / _nav
    po_draft.py ──► pipeline.py  esc / parse_money
    po_draft.py ──► store, branding

`boq.py` must **never** import this module: `/boq/view` links out with
`url_for` and reads `STORE["purchase_orders"]` directly, the same one-way trick
used five times already. It must not import `purchase.py`, `ra.py`,
`invoice.py` or `proforma.py` either — asserted in
`tests/test_import_directions.py`.
"""

import json
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import boq as BQ
import boqpick as BP
import branding as B
import docsheet as DS
import pipeline as P
import settings as SET
from address import picker_options, format_address_lines
from dashboard import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES, _inr
from store import STORE

po_draft_bp = Blueprint("po_draft", __name__, url_prefix="/po")


# =============================================================================
# BUSINESS RULES — module-level constants, never buried in a branch
# =============================================================================

# A draft PO carries no tax block of any kind. This is a named constant rather
# than an absence so that the rule is findable: the client asked for NO GST, and
# a zero-rated block would still be a block — it would print "IGST @ 0%" on a
# document that has no business mentioning tax at all.
PRINT_TAX = False

# Nor any rate. The supplier fills these in. See the module docstring.
PRINT_RATES = False

# The line cap. Derived from `boq.MAX_LINES` rather than chosen, for the same
# reason `ra.MAX_RA_LINES` is: the form renders every line of the BOQ, so a
# schedule legal at 600 lines must post a draft PO legal at 600 lines.
MAX_PO_LINES = BQ.MAX_LINES


def new_id() -> str:
    return str(uuid.uuid4())


# =============================================================================
# NUMBERING — one global series, and a number is never released
# =============================================================================

def next_ref() -> str:
    """
    The next draft-PO number, from the series held at `/settings`.

    **Global, not per-BOQ, and that is the opposite of `ra_no`.** The client
    keeps one running purchase-order series across every supplier and every
    site (DOMAIN.md §5.2), so this depends on every draft PO ever raised and on
    nothing at all about the schedule it came from. `ra_no` is per project
    because it is that job's own RA sequence. The two are deliberately
    different and `tests/test_po_draft.py` pins the difference.

    **Not max+1 over the existing records, which is what this used to be.**
    Two things were wrong with that: it hardcoded the prefix and started at 1,
    so it would collide head-on with the numbers already in the client's book;
    and deleting the highest draft PO handed its number back to the next one.
    A purchase order number has been quoted to a supplier — reissuing it is the
    same defect that stops a GST serial being reused. The counter is stored and
    advances on every save, so a deleted PO **spends** its number.
    """
    series = SET.po_series()
    return f"{series['prefix']}/{int(series['next_no'] or 1):04d}"


def _spend_ref() -> str:
    """Take the next number and advance the counter. Call once, at save."""
    series = SET.po_series()
    ref = f"{series['prefix']}/{int(series['next_no'] or 1):04d}"
    SET.save_po_series(series["prefix"], int(series["next_no"] or 1) + 1)
    return ref


def converted_pos(po: dict) -> list:
    """
    `[(purchase_id, purchase_record)]` — the real POs raised off this draft.

    ⚠ **A LIST, and this module does not own the field.** `purchase.py` appends
    to `converted_po_ids` when `/purchase/from-draft/<id>` writes an order;
    everything here does is read it and link out with `url_for`. That is the
    one-way trick this repo already runs between quotation/proforma,
    proforma/invoice, quotation/purchase, boq/ra, ra/receipt and boq/challan —
    **`po_draft.py` must never import `purchase.py`**, and the prohibition is
    asserted at AST level in `tests/test_import_directions.py`.

    A list rather than a single `po_id` because converting the same draft twice
    is deliberately permitted: an order genuinely does get split between two
    suppliers or placed in two lots. A scalar would let the second conversion
    silently erase the first one's trail, which is the opposite of what a record
    of what was sent out for pricing is for.

    Ids whose order has since been deleted are dropped rather than rendered as a
    dead link.
    """
    purchases = STORE.get("purchases") or {}
    rows = [(pid, purchases[pid]) for pid in (po.get("converted_po_ids") or [])
            if pid in purchases]
    rows.sort(key=lambda kv: str(kv[1].get("ref") or ""))
    return rows


def draft_pos_of_boq(boq_id: str) -> list:
    """Draft POs raised against this specific BOQ revision."""
    rows = [(pid, po) for pid, po in (STORE.get("purchase_orders") or {}).items()
            if po.get("boq_id") == boq_id]
    rows.sort(key=lambda kv: str(kv[1].get("ref") or ""))
    return rows


# =============================================================================
# THE VENDOR — a picker over the shared address book, with a free-text fallback
# =============================================================================

def vendor_from(form) -> tuple:
    """
    Returns `(vendor_fields, error)` for whichever way the vendor was given.

    **The picker is the primary path** and reads the shared address book
    (`type: "vendor"`), which is better than free text: it carries the address
    and the GSTIN, and it cannot be spelled two ways on two documents.

    **The free-text box is the fallback**, for a one-off supplier not worth an
    address-book entry — a local fabricator quoting one job. The brief asked for
    free text; the address book is an improvement on it, but replacing it
    outright would have made a one-off purchase impossible without polluting the
    book, so both are offered and **whichever was used is snapshotted onto the
    record** (CLIENT_CHANGES.md §1.2).

    ⚠ This is still **not a vendor master** — ABOUT.md §7 gap B6. No payment
      terms, no lead time, no GSTIN validation at the point of purchase. An
      address-book row is carrying that whole concept.
    """
    vid = (form.get("vendor_id") or "").strip()[:64]
    typed = (form.get("vendor_name") or "").strip()[:200]

    if vid:
        addr = (STORE.get("addresses") or {}).get(vid)
        if not addr:
            return {}, "That vendor is no longer in the address book."
        lines = format_address_lines(addr)
        return {
            "vendor_id": vid,
            "vendor_name": (addr.get("company") or addr.get("contact_name") or ""),
            "vendor_source": "book",
            "to": "\n".join(lines),
            "vendor_gstin": (addr.get("gstin") or "").strip(),
        }, ""

    if typed:
        return {
            "vendor_id": "",
            "vendor_name": typed,
            "vendor_source": "typed",
            # A typed vendor may still have an address and a GSTIN; both are
            # optional, because the whole point is a supplier nobody has filed.
            "to": "\n".join(x for x in [typed,
                                        (form.get("vendor_addr") or "").strip()[:500]]
                            if x),
            "vendor_gstin": (form.get("vendor_gstin") or "").strip()[:15].upper(),
        }, ""

    return {}, ("Choose a vendor from the address book, or type a one-off "
                "supplier's name.")


# =============================================================================
# THE LINE PICKER — only the lines that were ticked
# =============================================================================

def picked_lines(raw: str, boq: dict) -> tuple:
    """
    Returns `(items, error)` — the BOQ lines that were **ticked**, snapshotted.

    ⚠ **This used to snapshot every line of the BOQ tip, unconditionally.** On
      the client's own 97-line schedule that produced a 97-line purchase order
      for a supplier who was being asked to price four of them. Most POs will
      genuinely be the whole schedule, which is why every box arrives ticked —
      but the operator has to be able to untick down to a few, and until now
      there was no box.

    The parsing itself is `boqpick.picked_lines()`, shared with the delivery
    challan. Only the two refusals are this document's — a purchase order and a
    goods-movement note are refused for the same reason and say it differently,
    and a shared component that hard-codes one of them starts lying about the
    page it is on.

    `with_pcs=True` asks for the draft PO's second count column: pieces of pipe
    against metres of it, DOMAIN.md §5.2. Nothing on a BOQ line holds one, so
    it is typed on the form and blank is normal.
    """
    return BP.picked_lines(
        raw, boq, with_pcs=True, max_lines=MAX_PO_LINES,
        empty_msg=("No lines are ticked. A purchase order with nothing on it "
                   "is not a document — tick at least one line, or cancel."),
        cap_msg="Raise more than one order.")


def _validate(form, boq: dict) -> tuple:
    """
    Returns `(data, error)`, and **always returns data** so a rejected form
    re-renders with what was typed — `address._validate()`'s contract.
    """
    data = {
        "date":         (form.get("date") or _date.today().isoformat()).strip()[:32],
        "notes":        (form.get("notes") or "").strip()[:2000],
        "delivery_to":  (form.get("delivery_to") or "").strip()[:500],
        "vendor_id":    (form.get("vendor_id") or "").strip()[:64],
        "vendor_name":  (form.get("vendor_name") or "").strip()[:200],
        "vendor_addr":  (form.get("vendor_addr") or "").strip()[:500],
        "vendor_gstin": (form.get("vendor_gstin") or "").strip()[:15],
        "po_json":      form.get("po_json") or "",
    }
    if not data["date"]:
        return data, "A draft PO needs a date."

    vendor, err = vendor_from(form)
    if err:
        return data, err
    data["vendor"] = vendor
    return data, ""


def _page(html: str) -> str:
    """A finished page. Deliberately not Jinja-rendered — ABOUT.md §7.9d."""
    return html


def _alert(msg, kind: str = "error") -> str:
    if not msg:
        return ""
    icon = "&#10003;" if kind == "success" else "&#10007;"
    return f'<div class="alert alert-{P.esc(kind)}">{icon} {P.esc(msg)}</div>'


def _flash() -> str:
    return _alert(request.args.get("msg"),
                  request.args.get("type", "success"))


# =============================================================================
# CSS
# =============================================================================

# The picker's own rules come from `boqpick.PICKER_CSS` and are spliced in at
# the character position they have always occupied, so this sheet is
# byte-for-byte what it was — `tests/test_print_golden.py` hashes it. The
# concatenation is deliberate rather than an f-string: the CSS below is full of
# literal braces, and doubling them all to gain one interpolation would be a
# larger edit than the one being made.
PO_STYLES = "\n<style>\n" + BP.PICKER_CSS + """
  /* The vendor pair. The picker is primary; the free-text box is the escape
     hatch for a one-off supplier and says so rather than sitting there
     unexplained. */
  .vn-or { text-align:center; font-size:.74rem; text-transform:uppercase;
           letter-spacing:.08em; color:var(--muted); margin:.6rem 0; }
</style>
"""

PO_DOC_STYLES = """
<style>
  /* Layered after the shared sheet, introducing no new font, type size or
     border weight — the same restraint PROFORMA_STYLES and PURCHASE_STYLES
     hold to. It adds exactly two things this document needs and no other
     document has: a Pcs column, and a band saying the rates are blank because
     they are meant to be. */
  .quotation-doc .doc-sub-po { text-align:center; font-size:var(--fs-sm);
      color:var(--doc-soft); padding-bottom:2mm; }
  .quotation-doc .c-pcs { width:12mm; text-align:right; }
  .quotation-doc th.c-pcs { text-align:right; }
  .quotation-doc .c-rate-blank { width:24mm; }

  .quotation-doc .po-ask {
    border:var(--rule-box); margin-top:5mm; padding:2px 6px;
    font-size:var(--fs-sm);
    print-color-adjust:exact; -webkit-print-color-adjust:exact;
  }
  .quotation-doc .po-ask b { font-weight:700; }
</style>
"""


# =============================================================================
# THE FORM
# =============================================================================

def _vendor_block_form(data: dict) -> str:
    """The picker and the free-text fallback, as one field group."""
    opts = picker_options("Select a vendor from the address book",
                          only_types=("vendor",),
                          selected=data.get("vendor_id", ""))
    return f"""
      <div class="form-group">
        <label for="vendor_id">Vendor</label>
        <select id="vendor_id" name="vendor_id">{opts}</select>
        <div class="fld-hint" style="font-size:.74rem;color:var(--muted);margin-top:.2rem;">
          Carries the address and the GSTIN with it.
        </div>
      </div>
      <div class="vn-or">&mdash; or, for a one-off supplier &mdash;</div>
      <div class="fg2">
        <div class="form-group">
          <label for="vendor_name">Supplier name</label>
          <input type="text" id="vendor_name" name="vendor_name"
                 value="{P.esc(data.get('vendor_name', ''))}"
                 placeholder="Not in the address book"/>
        </div>
        <div class="form-group">
          <label for="vendor_gstin">Their GSTIN <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <input type="text" id="vendor_gstin" name="vendor_gstin" maxlength="15"
                 style="text-transform:uppercase;"
                 value="{P.esc(data.get('vendor_gstin', ''))}"/>
        </div>
        <div class="form-group span2">
          <label for="vendor_addr">Their address <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <textarea id="vendor_addr" name="vendor_addr" rows="2">{P.esc(data.get('vendor_addr', ''))}</textarea>
        </div>
      </div>"""


def _entry_form(boq: dict, data: dict, error: str = "",
                po: dict = None) -> str:
    """
    The create form: the line picker, the vendor, and the document's own fields.

    On edit (`po` given) the picker is not shown at all. The lines on an issued
    draft PO are a snapshot and changing them behind a document the supplier is
    already pricing is how a dispute starts — the same call `purchase.py` makes
    about an issued order's commercial content.
    """
    boq_ref = P.esc(boq.get("ref") or "")
    editing = po is not None
    action = (url_for("po_draft.edit_po", id=po["id"]) if editing
              else url_for("po_draft.create_po", boq=boq.get("id")))

    picker = ""
    if not editing:
        picker = BP.grid_html(
            boq,
            title="Lines to order",
            intro_html="""        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line is ticked to start with, because most orders are the whole
          schedule. Untick what this supplier is not being asked to price, and
          change a quantity where you want less than the schedule shows.
          <b>Rates are deliberately not here</b> — the supplier fills those in.
        </p>""",
            qty_label="Order qty",
            qty_aria="Order quantity",
            empty_note=("Nothing is ticked. A purchase order with no lines on "
                        "it is not a document."),
            payload_id="po_json",
            doc_word="PO",
            chosen=data.get("_chosen"),
            qty_of=data.get("_qty"),
            with_pcs=True)

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Draft PO" if not editing else "Edit Draft PO")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PO_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>{"Edit Draft" if editing else "Draft"} <span>Purchase Order</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('po_draft.list_pos')}" class="btn btn-ghost">All Draft POs</a>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">&#8592; {boq_ref}</a>
    </div>
  </div>

  {_alert(error)}

  <div class="set-intro" style="background:var(--surface);border:1px solid var(--border);
       border-left:3px solid var(--brand);border-radius:var(--radius);
       padding:.9rem 1.1rem;margin-bottom:1.2rem;font-size:.86rem;line-height:1.6;">
    Against <b>{boq_ref}</b> &middot; {P.esc(boq.get("project_name") or "")}
    &middot; {P.esc(boq.get("account_name") or "")}<br/>
    This order will be numbered <b>{P.esc(next_ref()) if not editing else P.esc(po.get("ref"))}</b>
    from the one running series at <a href="{url_for('settings.edit_settings')}">Settings</a>.
  </div>

  <form method="POST" action="{action}" onsubmit="return {"saveJSON()" if not editing else "true"};">
    <input type="hidden" name="po_json" id="po_json" value=""/>

    <div class="form-section">
      <div class="section-title">Supplier</div>
      {_vendor_block_form(data)}
    </div>

    <div class="form-section">
      <div class="section-title">Order details</div>
      <div class="fg2">
        <div class="form-group">
          <label for="date">Date</label>
          <input type="date" id="date" name="date" value="{P.esc(data.get('date', ''))}"/>
        </div>
        <div class="form-group">
          <label for="delivery_to">Deliver to</label>
          <input type="text" id="delivery_to" name="delivery_to"
                 value="{P.esc(data.get('delivery_to', ''))}"
                 placeholder="Site store, or our office"/>
        </div>
        <div class="form-group span2">
          <label for="notes">Notes / terms</label>
          <textarea id="notes" name="notes" rows="3">{P.esc(data.get('notes', ''))}</textarea>
        </div>
      </div>
    </div>

    {picker}

    <div class="set-actions" style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise draft PO"}</button>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · draft purchase order</p></footer>
</main>
</body></html>""")


# =============================================================================
# THE DOCUMENT
# =============================================================================

# The columns. Deliberately the same shape as `docsheet.SELL_COLUMNS` where the
# two agree, so the draft PO and the buy-side PO read as the same document.
# Two differences, and both are the client's ask: a **Pcs** column beside Qty,
# and a **Rate** column that is present but empty — the supplier writes in it.
PO_COLUMNS = (("c-sno", "S.No"), ("c-partno", "Item No"),
              ("c-desc", "Description of Material"), ("c-qty", "Qty"),
              ("c-pcs", "Pcs"), ("c-unit", "Unit"),
              ("c-rate-blank", "Rate"), ("c-total", "Amount"))


def _document_html(po: dict) -> str:
    """
    The printed draft PO, on the shared A4 sheet.

    **Driven by the PO's own stored rows**, never re-read from the live BOQ —
    CLIENT_CHANGES.md §1.2. The vendor, the project, the party and every line
    were snapshotted at save.

    There is **no tax block and no total**, and neither is an oversight. The
    client asked for no GST (`PRINT_TAX`), and a document whose rates are blank
    by design has no value to total — printing "Order Value 0.00" under a column
    of empty rate cells would state that the material is free.
    """
    rows = ""
    sno = 0
    for row in po.get("items", []):
        if row.get("is_header"):
            rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td class="c-partno">{P.esc(row.get("item_no", ""))}</td>
          <td colspan="6" class="c-desc">{P.esc(row.get("description", ""))}</td>
        </tr>"""
            continue
        sno += 1
        rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{P.esc(row.get("item_no", ""))}</td>
          <td class="c-desc">{P.esc(row.get("description", ""))}</td>
          <td class="c-qty">{BQ._fmt_qty(row.get("qty") or 0)}</td>
          <td class="c-pcs">{P.esc(row.get("pcs", ""))}</td>
          <td class="c-unit">{P.esc(row.get("unit", ""))}</td>
          <td class="c-rate-blank"></td>
          <td class="c-total"></td>
        </tr>"""

    meta_col_1 = (
        DS._meta("Draft PO No.", P.esc(po.get("ref"))) +
        DS._meta("Against BOQ",  P.esc(po.get("boq_ref"))) +
        DS._meta("Project",      P.esc(po.get("project_name"))) +
        DS._meta("Your GSTIN",   P.esc(po.get("vendor_gstin")))
    )
    meta_col_2 = (
        DS._meta("Date",       P.esc(po.get("date"))) +
        DS._meta("Site",       P.esc(po.get("site_location"))) +
        DS._meta("For",        P.esc(po.get("account_name"))) +
        DS._meta("Our GSTIN",  P.esc(B.COMPANY_GSTIN))
    )

    note_html = ""
    if po.get("notes"):
        note_html = (f'<div class="po-note" style="margin-top:4mm;">'
                     f'<b>Notes:</b> {P.esc(po["notes"])}</div>')

    return f"""
<div class="quotation-doc">

{DS.sheet_open(show_web=False)}

  <div class="doc-box">
    <div class="doc-title">DRAFT PURCHASE ORDER</div>
    <div class="doc-sub-po">For pricing &mdash; rates to be filled in by the supplier</div>

{DS.party_block("To (Supplier)", DS.name_block(po.get("to")),
                DS.secondary_block("Deliver To", po.get("delivery_to")),
                meta_col_1, meta_col_2)}

{DS.items_table(PO_COLUMNS, rows)}
  </div>

  <div class="po-ask">
    <b>This is a request for your rates, not a priced order.</b> Please quote
    against each line, return the priced copy, and quote our draft PO number on
    your quotation. No taxes are stated on this document; show them separately
    on your offer.
  </div>
  {note_html}

{DS.sig_block(P.esc(po.get("company_branch")), P.esc(po.get("auth_signatory")),
              computer_generated=True)}

{DS.sheet_close()}

</div>"""


# =============================================================================
# ROUTES
# =============================================================================

@po_draft_bp.route("/")
def list_pos():
    """The register — shaped like the BOQ and RA registers, not a new layout."""
    pos = sorted((STORE.get("purchase_orders") or {}).items(),
                 key=lambda kv: str(kv[1].get("ref") or ""), reverse=True)
    rows = ""
    for pid, po in pos:
        n = sum(1 for r in po.get("items", []) if not r.get("is_header"))
        # Where the draft ended up. Blank is the normal state — most drafts are
        # still out with a supplier being priced — so it falls back to the house
        # em-dash, substituted AFTER escaping (tests/test_entity_fallbacks.py).
        converted = ", ".join(
            f'<a href="{url_for("purchase.view_purchase", id=rid)}">'
            f'{P.esc(rec.get("ref"))}</a>'
            for rid, rec in converted_pos(po)) or '&mdash;'
        rows += f"""
        <tr>
          <td><a href="{url_for('po_draft.view_po', id=pid)}"><b>{P.esc(po.get("ref"))}</b></a></td>
          <td>{P.esc(po.get("date"))}</td>
          <td>{P.esc(po.get("vendor_name")) or '&mdash;'}</td>
          <td><a href="{url_for('boq.view_boq', id=po.get('boq_id', ''))}">{P.esc(po.get("boq_ref"))}</a></td>
          <td>{P.esc(po.get("project_name")) or '&mdash;'}</td>
          <td style="text-align:right;">{n}</td>
          <td>{converted}</td>
        </tr>"""

    if not rows:
        rows = ('<tr><td colspan="7" style="text-align:center;color:var(--muted);'
                'padding:2rem;">No draft purchase orders yet. Raise one from a '
                'bill of quantities.</td></tr>')

    series = SET.po_series()
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Draft Purchase Orders")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PO_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Draft <span>Purchase Orders</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">Bills of Quantities</a>
    </div>
  </div>

  {_flash()}

  <p style="font-size:.85rem;color:var(--muted);margin-bottom:1rem;">
    Sent to a supplier to be priced &mdash; description and quantity only, no
    rates and no GST. One running series across all suppliers and all sites;
    the next is <b>{P.esc(next_ref())}</b>, editable at
    <a href="{url_for('settings.edit_settings')}">Settings</a>.
  </p>

  <div class="pk-wrap">
    <table class="pk-table">
      <thead><tr>
        <th>PO No.</th><th>Date</th><th>Supplier</th>
        <th>Against BOQ</th><th>Project</th>
        <th style="text-align:right;">Lines</th>
        <th>Converted &rarr;</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · draft purchase orders ·
    series {P.esc(series['prefix'])}</p></footer>
</main>
</body></html>""")


@po_draft_bp.route("/create", methods=["GET", "POST"])
def create_po():
    boq_id = request.args.get("boq") or ""
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="Choose a bill of quantities to order against.",
                                type="error"))
    # A superseded revision is not what anybody is building from, so it is not
    # what anybody should be buying for. Same predicate `/boq/view` branches its
    # own action bar on.
    if boq_id in BQ.superseded_ids():
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg="That schedule has been superseded. Raise the "
                                    "order against the current revision.",
                                type="error"))

    if request.method == "GET":
        return _entry_form(boq, {"date": _date.today().isoformat()})

    data, error = _validate(request.form, boq)
    items, line_error = ([], "") if error else picked_lines(data["po_json"], boq)
    error = error or line_error
    if error:
        # Hand the operator back exactly what they ticked and typed.
        try:
            posted = (json.loads(data["po_json"] or "{}").get("lines") or [])
        except (ValueError, TypeError):
            posted = []
        data["_chosen"] = {BQ._line_id(r.get("line_id")) for r in posted
                           if isinstance(r, dict)}
        data["_qty"] = {BQ._line_id(r.get("line_id")): r.get("qty")
                        for r in posted if isinstance(r, dict)}
        return _entry_form(boq, data, error)

    # Carry the typed Pcs across. It is not on the BOQ and never will be.
    try:
        pcs_of = {BQ._line_id(r.get("line_id")): str(r.get("pcs") or "").strip()[:16]
                  for r in (json.loads(data["po_json"]).get("lines") or [])
                  if isinstance(r, dict)}
    except (ValueError, TypeError):
        pcs_of = {}
    for row in items:
        if not row.get("is_header"):
            row["pcs"] = pcs_of.get(row["line_id"], "")

    pid = new_id()
    STORE.setdefault("purchase_orders", {})[pid] = {
        "id": pid,
        "ref": _spend_ref(),
        "date": data["date"],
        # The BOQ this came from — a specific revision, exactly as an RA bill
        # names one. Both refs are STORED, not looked up, so the document still
        # reads as a historical record if the schedule is removed.
        "boq_id": boq_id,
        "boq_ref": boq.get("ref", ""),
        "boq_rev_no": boq.get("rev_no", 0),
        "project_name": boq.get("project_name", ""),
        "site_location": boq.get("site_location", ""),
        "account_name": boq.get("account_name", ""),
        # Whichever vendor path was used, snapshotted.
        **data["vendor"],
        "delivery_to": data["delivery_to"],
        "notes": data["notes"],
        "items": items,
        "company_branch": "", "auth_signatory": "",
    }
    return redirect(url_for("po_draft.view_po", id=pid,
                            msg="Draft purchase order raised.", type="success"))


@po_draft_bp.route("/view/<id>")
def view_po(id: str):
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg="That draft PO no longer exists.", type="error"))

    # ── Where the priced copy goes next ───────────────────────────────────
    #
    # The return leg ABOUT.md §7 gap B7 named as missing: the supplier prices
    # this sheet, and until now the priced copy came back on paper and was
    # re-keyed into `/purchase/create` from scratch, with nothing linking the two
    # documents. This is a **link**, built with `url_for` — the route lives in
    # `purchase.py`, which owns the `purchases` record shape, and this module
    # must never import it.
    #
    # The draft is not consumed by following it. It stays exactly as it is,
    # because it is the record of what was sent out to be priced.
    already = converted_pos(po)
    convert_html = (
        f'<a href="{url_for("purchase.from_draft", draft_id=id)}" class="btn">'
        f'{"Convert again" if already else "Convert to Purchase Order"}</a>')
    converted_strip = ""
    if already:
        chips = "".join(
            f'<a class="po-chip" href="{url_for("purchase.view_purchase", id=rid)}">'
            f'{P.esc(rec.get("ref"))}</a>' for rid, rec in already)
        converted_strip = (
            f'<div class="po-strip" style="margin:0 0 1rem;">'
            f'<span style="font-size:.82rem;color:var(--muted);margin-right:.5rem;">'
            f'Converted to</span>{chips}</div>')

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(po.get('ref')) + " Draft PO")}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{PO_DOC_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Draft PO <span style="color:var(--brand);">{P.esc(po.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('po_draft.list_pos')}" class="btn btn-ghost">All Draft POs</a>
    <a href="{url_for('boq.view_boq', id=po.get('boq_id', ''))}" class="btn btn-ghost">{P.esc(po.get('boq_ref'))}</a>
    {convert_html}
    <a href="{url_for('po_draft.edit_po', id=id)}" class="btn btn-ghost">Edit</a>
    <a href="{url_for('po_draft.delete_po', id=id)}" class="btn btn-ghost">Delete</a>
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>

{_flash()}
{converted_strip}

<div class="doc-outer">
{_document_html(po)}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · draft purchase order</p>
</footer>
</main>
</body></html>""")


@po_draft_bp.route("/print/<id>")
def print_po(id: str):
    """The document alone behind a `.no-print` action bar — `/boq/print`'s shape."""
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg="That draft PO no longer exists.", type="error"))

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(po.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{PO_DOC_STYLES}
</head>
<body>
<div class="screen-acts no-print">
  <a href="{url_for('po_draft.view_po', id=id)}" class="btn btn-ghost">&#8592;&nbsp;Back</a>
  <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
</div>
<div class="doc-outer">
{_document_html(po)}
</div>
</body></html>""")


@po_draft_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_po(id: str):
    """
    Vendor, date, delivery address and notes. **Not the lines.**

    An issued draft PO is a document a supplier is pricing, and moving the lines
    under it is how a dispute starts — `purchase.update_purchase()` makes the
    same call about an issued order's commercial content. Ordering different
    lines means raising another draft PO, which is cheap and leaves a trail.
    """
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg="That draft PO no longer exists.", type="error"))
    boq = (STORE.get("boqs") or {}).get(po.get("boq_id", "")) or {
        "id": po.get("boq_id", ""), "ref": po.get("boq_ref", ""),
        "project_name": po.get("project_name", ""),
        "account_name": po.get("account_name", ""), "line_items": [],
    }

    if request.method == "GET":
        return _entry_form(boq, {
            "date": po.get("date", ""), "notes": po.get("notes", ""),
            "delivery_to": po.get("delivery_to", ""),
            "vendor_id": po.get("vendor_id", ""),
            "vendor_name": po.get("vendor_name", "") if not po.get("vendor_id") else "",
            "vendor_gstin": po.get("vendor_gstin", "") if not po.get("vendor_id") else "",
            "vendor_addr": "",
        }, po=po)

    data, error = _validate(request.form, boq)
    if error:
        return _entry_form(boq, data, error, po=po)

    po["date"] = data["date"]
    po["notes"] = data["notes"]
    po["delivery_to"] = data["delivery_to"]
    po.update(data["vendor"])
    # `ref` is deliberately untouched. An edit never reissues the number.
    return redirect(url_for("po_draft.view_po", id=id,
                            msg="Draft purchase order updated.", type="success"))


@po_draft_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_po(id: str):
    """
    GET renders the confirmation, POST destroys — ABOUT.md §7.9f's standing rule
    for any new delete route, and `tests/test_po_draft.py` ships the per-route
    GET test that rule also requires.

    **Deleting does not release the number.** The series counter lives at
    `/settings` and only ever advances, so the next draft PO takes the next
    number and this one's is spent. It has been quoted to a supplier; a second
    document bearing it is indistinguishable from the first.
    """
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg="That draft PO no longer exists.", type="error"))

    if request.method == "GET":
        return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delete Draft PO")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PO_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top"><h1>Delete <span>{P.esc(po.get('ref'))}</span></h1></div>
  <div class="card" style="border:1px solid var(--border);border-radius:10px;padding:1.2rem;">
    <p>Delete draft purchase order <b>{P.esc(po.get('ref'))}</b> to
       <b>{P.esc(po.get('vendor_name')) or 'an unnamed supplier'}</b>, raised
       against {P.esc(po.get('boq_ref'))}?</p>
    <p style="font-size:.85rem;color:var(--muted);">
      This cannot be undone. <b>The number is not released</b> — the next draft
      PO takes the next one in the series, because {P.esc(po.get('ref'))} may
      already have been quoted to a supplier.
    </p>
    <form method="POST" style="display:flex;gap:.75rem;margin-top:1rem;">
      <button type="submit" class="btn">Delete it</button>
      <a href="{url_for('po_draft.view_po', id=id)}" class="btn btn-ghost">Cancel</a>
    </form>
  </div>
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · draft purchase order</p></footer>
</main>
</body></html>""")

    boq_id = po.get("boq_id", "")
    ref = po.get("ref", "")
    STORE["purchase_orders"].pop(id, None)
    return redirect(url_for("boq.view_boq", id=boq_id,
                            msg=f"Draft PO {ref} deleted. Its number is not reissued.",
                            type="success"))
