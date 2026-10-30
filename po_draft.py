"""
po_draft.py — Product Inquiry (the draft purchase order) from a BOQ
===================================================================
⚠ **The document is CALLED a "Product Inquiry" on screen and on paper from
  29 October 2026** (CLIENT_CHANGES.md §0 **fifty-ninth** block, B1) — the
  name it has always deserved, since it carries no rates and no GST and
  exists to be priced. **The rename is DISPLAY ONLY**: this module, the
  blueprint, `STORE["purchase_orders"]`, every `/po/` URL, every stored
  field and the `SF/DPO` series are all unchanged. See THE NAME below.
Blueprint  : po_draft_bp
Mounted at : /po  (registered in app.py)

CLIENT_CHANGES.md item 4. A BOQ-side document that goes to a supplier asking
them to price the material a schedule needs.

Routes
------
  GET       /po/              — register of product inquiries
  GET,POST  /po/create?boq=   — pick the lines, pick the vendor, raise the draft
  GET       /po/view/<id>     — the document, with the action bar
  GET       /po/print/<id>    — the document alone, ready for Ctrl+P
  GET,POST  /po/edit/<id>     — EVERY field and EVERY line, until converted
  GET,POST  /po/pictures/<id> — a picture beside each line (21 Oct 2026)
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
import cascade
import docsheet as DS
import hsnfill as HF   # the ONE HSN rule — the leaf (29 Oct 2026)
import lineimage as LI   # pictures beside a line — the leaf (21 Oct 2026)
import pipeline as P
import settings as SET
import units as UN   # the shared unit list — the leaf (29 Oct 2026)
from address import picker_options, format_address_lines
from chrome import BASE_STYLES, _nav
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
# =============================================================================
# THE NAME ON SCREEN AND ON PAPER — "Product Inquiry" (29 October 2026)
# =============================================================================
#
# CLIENT_CHANGES.md §0 **fifty-ninth** block, B1, from the 28 October 2026
# meeting with Yogesh Bankar: the Draft PO is called a **Product Inquiry**,
# which is what it has always been — a request for a supplier's prices, with
# no rates and no GST on it.
#
# ⚠ **DISPLAY ONLY, and that is the whole of the ruling.** Nothing stored and
#   nothing addressable changed:
#
#   * the module is still `po_draft.py` and the blueprint still `po_draft`;
#   * the collection is still `STORE["purchase_orders"]`;
#   * every URL is still under `/po/`, so no bookmark and no link breaks —
#     including `purchase.from_draft()`'s, which this module may not import
#     and reaches by `url_for` only;
#   * every stored field keeps its name — `converted_po_ids`, `boq_ref`,
#     `vendor_source`, `ref`;
#   * the number series is still `SF/DPO/0001` and `po_draft_series` at
#     `/settings`. **The PREFIX is a client-editable field** and renaming it
#     is their decision on their own paper book, not ours (§7 gap 15's rule).
#
#   A rename that moved any of those would be a data migration wearing a
#   label's clothes. `tests/test_product_inquiry_name.py` asserts each one.
#
# ⚠ **The PRINTED TITLE moves**, which is an intended print change and the
#   one golden this block re-baselines.
DOC_NAME = "Product Inquiry"
DOC_NAME_LOWER = "product inquiry"
DOC_NAME_PLURAL = "Product Inquiries"
DOC_NAME_PLURAL_LOWER = "product inquiries"
DOC_TITLE = "PRODUCT INQUIRY"

# What the document's own number is labelled on the sheet. The VALUE is
# untouched — still `SF/DPO/0001`.
DOC_NO_LABEL = "Inquiry No."

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


# =============================================================================
# THE LOCK — a converted draft is a historical record (29 October 2026)
# =============================================================================
#
# CLIENT_CHANGES.md §0 **fifty-ninth** block, A2: *"every field and every line
# is editable while the Draft PO is unconverted. Locked once converted to a
# real PO: refuse on POST as well as hiding the form."*
#
# ⚠ **The second half is the load-bearing one.** A form that is merely not
#   drawn is not a lock — ABOUT.md §2g's rule about controls, read the other
#   way round. `edit_po()` asks this on the GET *and* on the POST, and the
#   POST path writes nothing when it answers True.

LOCK_REASON = ("This request for quotation has already been converted into a "
               "purchase order, so its lines and its vendor are the record of "
               "what that order was raised from and cannot be changed. Raise "
               "another one instead &mdash; it is cheap and it leaves a trail.")


def is_locked(po: dict) -> bool:
    """
    Has this draft been converted into a real purchase order?

    **That is the whole of the lock, and it is deliberately not a status
    field.** `converted_po_ids` is already the record of it (written by
    `purchase.from_draft()`), and a second stored flag beside a list that
    answers the same question is how the two start disagreeing. An order
    deleted afterwards drops out of `converted_pos()` and the draft becomes
    editable again, which is correct: there is no longer an order whose
    provenance this document is.
    """
    return bool(converted_pos(po))


# ── Caps. Each is an existing one, named here rather than re-chosen. ────────
DESC_MAX = 1500          # `boq._clean_lines()`'s own cap on a description
ITEM_NO_MAX = 32         # the BOQ form's
UNIT_MAX = 30            # `purchase._parse_extra_lines()`'s
PCS_MAX = 16             # `create_po()`'s, from the picker


def parse_items(form, po: dict) -> tuple:
    """
    `(items, error)` for the full line editor — **and nothing is returned until
    every row has been read**, so a bad fourth row does not leave the first
    three half-applied. `purchase._parse_extra_lines()`'s contract.

    `items` is **`None`** when the POST carried none of the line boxes at all:
    a stale tab, which leaves the lines as they are rather than emptying the
    document. `[]` is impossible — an editor emptied by hand is refused.

    The repeater is **positional**, like the extra parts and unlike the create
    picker: this form can gain and lose rows, so there is no stable list to
    diff against and what arrives IS the new list. Every box is read by index
    off parallel `getlist()`s, so a header row in between can never shift a
    value onto the wrong line.

    `it_line_id` is carried as a hidden box and **kept only when it is the
    minted shape and already on this draft**. A row the operator added has a
    blank one and gets a freshly minted id, because `line_id` is what the
    Pictures page addresses a row by and what `purchase.from_draft()` matches
    a posted quantity on — a row with no id would be unreachable from both.

    ⚠ **A hand-added line is NOT on the BOQ, and that is allowed.** This
      document is a request for a supplier's prices, not a claim measured
      against a schedule: `from_draft()` reads `_boq_lines_by_id()` only for a
      rate prefill and tolerates a miss, and no over-claim guard looks at a
      draft PO. The BOQ link on the record stays what it was.

    ⚠ **No rate box, and that is A2's one recorded conflict with its own
      brief.** `PRINT_RATES` is False and the module docstring says nothing on
      this document may read a buy rate from anywhere; the supplier fills the
      rates in. Manas's answer, with the conflict named: no rate box, and the
      printed Rate column stays empty.
    """
    # ⚠ **A POST with no `it_rows` marker leaves every line exactly as it
    #   is**, and returns `None` rather than an empty list to say so. That is
    #   a tab opened before the editor existed, and it is
    #   `purchase._reprice()`'s own rule for a stale form, which exists
    #   precisely because the alternative is a save that silently empties a
    #   document.
    #
    #   ⚠ **It is a MARKER on the form and not "are any `it_*` boxes
    #     posted?"**, because those two questions have different answers in
    #     the one case that matters: an operator who deletes every row posts
    #     no `it_*` box at all, and that is "I emptied it" — refused below —
    #     not "I never saw the editor". A hidden box outside the repeater is
    #     the only thing that can tell them apart.
    if "it_rows" not in form:
        return None, ""

    lids = form.getlist("it_line_id")
    kinds = form.getlist("it_kind")
    item_nos = form.getlist("it_item_no")
    descs = form.getlist("it_desc")
    units = form.getlist("it_unit")
    qtys = form.getlist("it_qty")
    pcses = form.getlist("it_pcs")
    makes = form.getlist("it_make")
    hsns = form.getlist("it_hsn")
    # The row's picture id, hidden on every row — `purchase.py`'s
    # `extra_image` precedent, and for its reason: this repeater is re-read
    # whole and the lists are read by position, so a picture must ride on its
    # own row or it lands on the wrong part.
    images = form.getlist("it_image")

    n_rows = max(len(lids), len(kinds), len(item_nos), len(descs), len(units),
                 len(qtys), len(pcses), len(makes), len(hsns))

    known = {BQ._line_id(r.get("line_id")) for r in (po.get("items") or [])}
    known.discard("")
    used = set()

    def _at(seq, i):
        return str(seq[i] if i < len(seq) else "").strip()

    out = []
    for i in range(n_rows):
        desc = _at(descs, i)[:DESC_MAX]
        item_no = _at(item_nos, i)[:ITEM_NO_MAX]
        unit = _at(units, i)[:UNIT_MAX]
        qty_raw = _at(qtys, i)
        pcs = _at(pcses, i)[:PCS_MAX]
        make = _at(makes, i)[:BP.MAKE_MAX]
        hsn = HF.clean(_at(hsns, i))
        header = _at(kinds, i) == "header"

        # A row nobody typed anything into is a row that was deleted, or a
        # spare slot. Not an error, and not a line.
        if not (desc or item_no or unit or qty_raw or pcs or make or hsn):
            continue

        if not desc:
            return [], (f"Line {i + 1} has figures but no description. Say "
                        f"what the supplier is being asked to price.")

        qty = 0.0
        if not header:
            value, bad = BQ.typed_num(qty_raw)
            if bad:
                return [], (f"The quantity for '{desc[:60]}' is not a number. "
                            f"Nothing was saved.")
            if value is not None and value < 0:
                return [], f"The quantity for '{desc[:60]}' cannot be negative."
            # ⚠ A BLANK quantity is 0 here, NOT absent — this is not a BOQ.
            #   The "as it is" rule (§0 forty-fifth block) is about a schedule
            #   the client wrote; a purchase order's quantity column prints
            #   through `_fmt_qty()`, which has no absent state, and a supplier
            #   asked to price a blank quantity is being asked nothing.
            qty = float(value or 0.0)

        lid = BQ._line_id(_at(lids, i))
        if not lid or lid not in known or lid in used:
            lid = BQ._new_line_id()
        used.add(lid)

        row = {"line_id": lid, "is_header": header,
               "item_no": item_no, "description": desc,
               "unit": "" if header else unit,
               "qty": 0.0 if header else qty,
               "pcs": "" if header else pcs}
        # Absent when blank, which is the shape `picked_lines()` writes — a
        # line nobody gave a make or a code carries no empty key.
        if make and not header:
            row["make"] = make
        if hsn and not header:
            row["hsn"] = hsn
        # ⚠ **The library decides what is allowed, not the POST**
        #   (29 October 2026, §0 fifty-ninth block, B2). `apply_choice()`
        #   refuses an id that is not the minted shape, has no file on disk,
        #   or is in neither this item's library nor already on the stored
        #   line — so a crafted payload cannot attach an arbitrary stored
        #   picture. The NAME is snapshotted with it (§1.2).
        if not header:
            stored_row = next((r for r in (po.get("items") or [])
                               if BQ._line_id(r.get("line_id")) == lid), None)
            LI.apply_choice(row, _at(images, i), stored_row or row)
        out.append(row)

    if not any(not r["is_header"] for r in out):
        return [], ("There is nothing on this document to price. Add at least "
                    "one line, or cancel.")
    if len(out) > MAX_PO_LINES:
        return [], (f"{len(out)} lines; the limit is {MAX_PO_LINES}. Raise "
                    f"more than one order.")
    return out, ""


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
        raw, boq, with_pcs=True, with_make=True, with_image=True,
        max_lines=MAX_PO_LINES,
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
        return data, f"A {DOC_NAME_LOWER} needs a date."

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

# The full line editor (29 October 2026, §0 fifty-ninth block, A2). Its own
# constant rather than a block inside PO_STYLES, because `/po/create` loads
# PO_STYLES and is pinned by a golden in `tests/test_print_golden.py` — the
# picker form must stay byte-for-byte what it is.
EDIT_STYLES = """
<style>
  .ed-wrap { overflow-x:auto; }
  .ed-table { width:100%; border-collapse:collapse; font-size:.84rem; min-width:860px; }
  .ed-table th { text-align:left; font-size:.68rem; text-transform:uppercase;
                 letter-spacing:.04em; color:var(--muted); padding:.4rem .4rem;
                 border-bottom:1px solid var(--border, #e5e7eb); white-space:nowrap; }
  .ed-table td { padding:.35rem .4rem; border-bottom:1px solid var(--border, #e5e7eb);
                 vertical-align:middle; }
  .ed-table input[type=text] { width:100%; box-sizing:border-box; font-size:.84rem; }
  .ed-table textarea { width:100%; box-sizing:border-box; font-size:.84rem;
                       min-height:2.4rem; resize:vertical; }
  .ed-no    { width:4.5rem; }
  .ed-unit  { width:5rem; }
  .ed-qty   { width:5rem; text-align:right; }
  .ed-pcs   { width:4.5rem; text-align:right; }
  .ed-make  { width:8rem; }
  .ed-hsn   { width:6rem; font-family:ui-monospace,monospace; }
  .ed-act   { width:2.2rem; text-align:center; }
  .ed-row.is-head { background:#f8fafc; }
  .ed-row.is-head td { color:#334155; }
  .ed-head-tag { font-size:.64rem; text-transform:uppercase; letter-spacing:.06em;
                 color:var(--muted); }
  .ed-del { border:0; background:transparent; color:#b91c1c; cursor:pointer;
            font-size:1rem; line-height:1; padding:.1rem .3rem; }
  .ed-bar { display:flex; gap:.6rem; flex-wrap:wrap; margin:.8rem 0 0; }
  .ed-lock { border:1px solid #fecaca; background:#fef2f2; color:#7f1d1d;
             border-radius:8px; padding:.7rem .9rem; margin:0 0 1.1rem;
             font-size:.86rem; line-height:1.55; }
  @media (max-width:760px) {
    .ed-table { min-width:760px; }
  }
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


def _posted_rows(form) -> list:
    """
    The rows exactly as they were POSTED, for a refused save to re-render.

    **Unvalidated on purpose.** `parse_items()` refuses; this hands the typed
    text straight back so the operator sees their own work and the box that is
    wrong, rather than an empty form. `purchase._parse_extra_lines()`'s
    rejected-POST contract, and `address._validate()`'s before it.
    """
    lids = form.getlist("it_line_id")
    kinds = form.getlist("it_kind")
    item_nos = form.getlist("it_item_no")
    descs = form.getlist("it_desc")
    units = form.getlist("it_unit")
    qtys = form.getlist("it_qty")
    pcses = form.getlist("it_pcs")
    makes = form.getlist("it_make")
    hsns = form.getlist("it_hsn")
    images = form.getlist("it_image")
    n_rows = max(len(lids), len(kinds), len(descs))

    def _at(seq, i):
        return str(seq[i] if i < len(seq) else "")

    out = []
    for i in range(n_rows):
        header = _at(kinds, i).strip() == "header"
        row = {"line_id": _at(lids, i).strip(), "is_header": header,
               "item_no": _at(item_nos, i), "description": _at(descs, i),
               "unit": _at(units, i), "pcs": _at(pcses, i),
               "make": _at(makes, i), "hsn": _at(hsns, i)}
        # `qty` goes back as the TYPED STRING, not a float: "12x" has to come
        # back as "12x" beside the message that says it is not a number.
        row["qty"] = _at(qtys, i)
        iid = LI.valid_id(_at(images, i).strip())
        if iid:
            row[LI.KEY] = iid
        out.append(row)
    return out


def _item_row_html(row: dict = None, n: int = 0) -> str:
    """
    One row of the full line editor. `row` is None for a blank row the
    operator added, and `{"is_header": True}` for a blank specification row.

    Every box is named without an index: the repeater is read positionally off
    parallel `getlist()`s (`parse_items()`), which is the only shape that
    survives a row being deleted in the middle. The hidden `it_kind` is what
    carries "this is a specification row" through a POST — a checkbox would
    not, because an unticked checkbox posts nothing at all and the lists would
    then be of different lengths.
    """
    row = row or {}
    header = bool(row.get("is_header"))
    # ⚠ `qty` is a FLOAT off a stored row and a TYPED STRING off a refused
    #   POST (`_posted_rows()`), and both have to render. A string goes back
    #   verbatim so "12x" is handed back beside the message that says it is
    #   not a number; a float goes through `_fmt_qty()`, which drops a
    #   trailing `.0`.
    qty = row.get("qty")
    if header or qty in (None, ""):
        qty_txt = ""
    elif isinstance(qty, str):
        qty_txt = qty
    else:
        qty_txt = BQ._fmt_qty(float(qty))
    cls = "ed-row is-head" if header else "ed-row"
    # ⚠ **The picture is a SELECT over the item's library where there is one,
    #   and a hidden box otherwise** (29 October 2026, §0 fifty-ninth block,
    #   B2). `select_html()` returns "" when the item has nothing to offer and
    #   the line carries nothing, which is when the hidden box keeps the
    #   positional lists the same length. Either way the field is `it_image`
    #   and `parse_items()` reads one thing.
    pic = "" if header else LI.select_html(
        row, "it_image", "Picture", style="max-width:150px;font-size:.8rem;")
    if not pic:
        pic = f'<input type="hidden" name="it_image" value="{P.esc(LI.image_of(row))}"/>'
    hidden = (f'<input type="hidden" name="it_line_id" value="{P.esc(row.get("line_id") or "")}"/>'
              f'<input type="hidden" name="it_kind" value="{"header" if header else "item"}"/>'
              f'{pic}')
    if header:
        # A specification row carries the clause and nothing else — DOMAIN.md
        # §2.2, the same shape `boqpick.picked_lines()` writes. The four boxes
        # it has no business carrying are posted BLANK rather than omitted, so
        # every list stays the same length.
        return f"""
          <tr class="{cls}">
            <td><input type="text" name="it_item_no" value="{P.esc(row.get("item_no") or "")}"
                       maxlength="{ITEM_NO_MAX}" aria-label="Item number"/>{hidden}</td>
            <td><textarea name="it_desc" maxlength="{DESC_MAX}"
                          aria-label="Specification">{P.esc(row.get("description") or "")}</textarea>
                <div class="ed-head-tag">specification &mdash; no quantity</div></td>
            <td><input type="hidden" name="it_make" value=""/>&mdash;</td>
            <td><input type="hidden" name="it_hsn" value=""/>&mdash;</td>
            <td><input type="hidden" name="it_unit" value=""/>&mdash;</td>
            <td><input type="hidden" name="it_qty" value=""/>&mdash;</td>
            <td><input type="hidden" name="it_pcs" value=""/>&mdash;</td>
            <td class="ed-act"><button type="button" class="ed-del"
                 onclick="edDel(this)" aria-label="Remove this row">&#10007;</button></td>
          </tr>"""
    return f"""
          <tr class="{cls}">
            <td><input type="text" name="it_item_no" value="{P.esc(row.get("item_no") or "")}"
                       maxlength="{ITEM_NO_MAX}" aria-label="Item number"/>{hidden}</td>
            <td><textarea name="it_desc" maxlength="{DESC_MAX}"
                          aria-label="Description">{P.esc(row.get("description") or "")}</textarea></td>
            <td><input type="text" name="it_make" value="{P.esc(row.get("make") or "")}"
                       maxlength="{BP.MAKE_MAX}" placeholder="Make" aria-label="Make"/></td>
            <td><input type="text" name="it_hsn" value="{P.esc(row.get("hsn") or "")}"
                       maxlength="{HF.HSN_MAX}" placeholder="HSN" aria-label="HSN"/></td>
            <td>{UN.select_html("it_unit", row.get("unit") or "", blank="Unit")}</td>
            <td><input type="text" name="it_qty" value="{P.esc(qty_txt)}"
                       aria-label="Quantity" style="text-align:right;"/></td>
            <td><input type="text" name="it_pcs" value="{P.esc(row.get("pcs") or "")}"
                       maxlength="{PCS_MAX}" aria-label="Pieces" style="text-align:right;"/></td>
            <td class="ed-act"><button type="button" class="ed-del"
                 onclick="edDel(this)" aria-label="Remove this line">&#10007;</button></td>
          </tr>"""


def _item_rows_html(rows: list) -> str:
    return "".join(_item_row_html(r, n) for n, r in enumerate(rows or []))


# The two blank rows the Add buttons clone, as HTML the page already holds, so
# a row added in the browser is byte-for-byte a row the server would have
# rendered. ⚠ **Doubled braces**: this is interpolated into an f-string.
EDIT_SCRIPT = """
<script>
/* The full line editor's two buttons (29 October 2026, §0 fifty-ninth block,
   A2). Add and remove only — every box is an ordinary form field read
   positionally on the server, so a browser with JavaScript off can still
   edit, reorder nothing and save: it simply cannot add or delete a row.
   `purchase.py`'s repeaters make the same trade. */
var ED_ITEM = __ED_ITEM__;
var ED_HEAD = __ED_HEAD__;

function edAdd(header) {
  var body = document.getElementById('ed-body');
  if (!body) { return; }
  var tmp = document.createElement('tbody');
  tmp.innerHTML = header ? ED_HEAD : ED_ITEM;
  var tr = tmp.querySelector('tr');
  if (tr) {
    body.appendChild(tr);
    var first = tr.querySelector('textarea, input[type=text]');
    if (first) { first.focus(); }
  }
}

function edDel(btn) {
  var tr = btn.closest('tr');
  if (!tr) { return; }
  /* Removed outright rather than hidden: the server reads what is POSTED, and
     a hidden row still posts. That is the opposite of the claim grid's
     "a folded row is hidden, never removed" — there, folding is a view of a
     fixed list; here, the list IS what the form says it is. */
  tr.parentNode.removeChild(tr);
}
</script>
"""


def _edit_script() -> str:
    """`EDIT_SCRIPT` with the two blank rows spliced in as JSON."""
    return (EDIT_SCRIPT
            .replace("__ED_ITEM__", P.json_for_script(_item_row_html(None)))
            .replace("__ED_HEAD__", P.json_for_script(_item_row_html({"is_header": True}))))


def _entry_form(boq: dict, data: dict, error: str = "",
                po: dict = None, banner_html: str = "") -> str:
    """
    The create form: the line picker, the vendor, and the document's own fields.

    On edit (`po` given) the picker is not shown at all. The lines on an issued
    draft PO are a snapshot and changing them behind a document the supplier is
    already pricing is how a dispute starts — the same call `purchase.py` makes
    about an issued order's commercial content.

    `banner_html` (18 October 2026) is Import from Excel's note, spliced under
    the alert; "" emits the form it always emitted.
    """
    boq_ref = P.esc(boq.get("ref") or "")
    editing = po is not None
    # Import from Excel (18 October 2026). Create form only, and drawn
    # unconditionally: `docimport.upload_dpo` carries `po.create`, this form's
    # own permission — `tests/test_doc_import.py` holds the two equal.
    import_btn = ("" if editing else
                  f'\n      <a href="{url_for("docimport.upload_dpo", boq=boq.get("id"))}" '
                  f'class="btn btn-ghost">&#128229; Import from Excel</a>')
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
            with_pcs=True,
            pcs_of=data.get("_pcs"),
            with_make=True,
            make_of=data.get("_make"),
            # The item's picture, from the library (29 Oct 2026, §0
            # fifty-ninth block, B2). A select, never a file box.
            with_image=True,
            image_of=data.get("_image"))

    # ── The FULL line editor on EDIT (29 October 2026, §0 fifty-ninth block,
    #    A2). It replaced a *Make, per line* section that was the only
    #    per-line control this form had (26 October 2026, the fifty-third
    #    block, change 2) — every field on every line is editable now, and
    #    lines can be added and removed, while the draft is unconverted.
    #    ⚠ The repeater is POSITIONAL (`parse_items()` says why), so each row
    #      carries its own `line_id`, its own picture id and its own kind as
    #      hidden boxes. A header in between cannot shift a value onto the
    #      wrong line.
    items_html = ""
    if editing:
        rows_src = data.get("_items")
        if rows_src is None:
            rows_src = list(po.get("items") or [])
        items_html = f"""
    <div class="form-section">
      <div class="section-title">Lines</div>
      <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
        Every line is editable while this request has not been converted into a
        purchase order. Add a line, remove one, change a description, a
        quantity, a unit, the pieces, the brand or the HSN. <b>Rates are
        deliberately not here</b> &mdash; the supplier fills those in, which is
        what this document is for. A <b>specification</b> row carries the clause
        the sizes under it are described by and takes no quantity.
      </p>
      <input type="hidden" name="it_rows" value="1"/>
      <div class="ed-wrap">
      <table class="ed-table">
        <thead><tr>
          <th class="ed-no">Item No</th>
          <th>Description</th>
          <th class="ed-make">Make</th>
          <th class="ed-hsn">HSN</th>
          <th class="ed-unit">Unit</th>
          <th class="ed-qty">Qty</th>
          <th class="ed-pcs">Pcs</th>
          <th class="ed-act"></th>
        </tr></thead>
        <tbody id="ed-body">{_item_rows_html(rows_src)}
        </tbody>
      </table>
      </div>
      <div class="ed-bar">
        <button type="button" class="btn btn-ghost" onclick="edAdd(false)">+ Add a line</button>
        <button type="button" class="btn btn-ghost" onclick="edAdd(true)">+ Add a specification row</button>
      </div>
    </div>
    {_edit_script()}"""

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(DOC_NAME if not editing else "Edit " + DOC_NAME)}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PO_STYLES}{cascade.CASCADE_STYLES}{EDIT_STYLES if editing else ""}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>{"Edit " if editing else ""}Product <span>Inquiry</span></h1>
    <div style="display:flex;gap:.7rem;">{import_btn}
      <a href="{url_for('po_draft.list_pos')}" class="btn btn-ghost">All {DOC_NAME_PLURAL}</a>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">&#8592; {boq_ref}</a>
    </div>
  </div>

  {_alert(error)}{banner_html}

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

    {picker}{items_html}

    <div class="set-actions" style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise " + DOC_NAME_LOWER}</button>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · {DOC_NAME_LOWER}</p></footer>
</main>
</body></html>""")


# =============================================================================
# THE DOCUMENT
# =============================================================================

# The columns. Deliberately the same shape as `docsheet.SELL_COLUMNS` where the
# two agree, so the draft PO and the buy-side PO read as the same document.
# Two differences, and both are the client's ask: a **Pcs** column beside Qty,
# and a **Rate** column that is present but empty — the supplier writes in it.
# **Make** (26 October 2026) sits immediately right of the description, as on
# the purchase order — `docsheet.MAKE_CSS` keeps it narrow.
PO_COLUMNS = (("c-sno", "S.No"), ("c-partno", "Item No"),
              ("c-desc", "Description of Material"), ("c-make", "Make"),
              ("c-qty", "Qty"),
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
    # ⚠ **The Image column (21 October 2026) is drawn only when a line carries
    #   a picture that resolves**, and its stylesheet rides in with it, inside
    #   the document — this function is the whole sheet for both `/po/view` and
    #   `/po/print`. A draft PO with no picture renders byte-for-byte what it
    #   always did; `tests/test_print_golden.py` pins `/po/print`.
    pics = LI.sheet_has_images(po.get("items", []))
    rows = ""
    sno = 0
    for row in po.get("items", []):
        if row.get("is_header"):
            img_td = f"\n          {LI.EMPTY_CELL}" if pics else ""
            rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td class="c-partno">{P.esc(row.get("item_no", ""))}</td>{img_td}
          <td colspan="7" class="c-desc">{P.esc(row.get("description", ""))}</td>
        </tr>"""
            continue
        sno += 1
        img_td = f"\n          {LI.cell(row)}" if pics else ""
        rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{P.esc(row.get("item_no", ""))}</td>{img_td}
          <td class="c-desc">{P.esc(row.get("description", ""))}</td>
          <td class="c-make">{P.esc(row.get("make"))}</td>
          <td class="c-qty">{BQ._fmt_qty(row.get("qty") or 0)}</td>
          <td class="c-pcs">{P.esc(row.get("pcs", ""))}</td>
          <td class="c-unit">{P.esc(row.get("unit", ""))}</td>
          <td class="c-rate-blank"></td>
          <td class="c-total"></td>
        </tr>"""

    meta_col_1 = (
        DS._meta(DOC_NO_LABEL, P.esc(po.get("ref"))) +
        # The BOQ's ROOT number (29 Oct 2026, §0 fifty-ninth block, B4).
        DS._meta("Against BOQ",  P.esc(P.root_ref(po.get("boq_ref")))) +
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

    return f"""{LI.SHEET_CSS if pics else ""}
<div class="quotation-doc">

{DS.sheet_open(show_web=False)}

  <div class="doc-box">
    <div class="doc-title">{DOC_TITLE}</div>
    <div class="doc-sub-po">For pricing &mdash; rates to be filled in by the supplier</div>

{DS.party_block("To (Supplier)", DS.name_block(po.get("to")),
                DS.secondary_block("Deliver To", po.get("delivery_to")),
                meta_col_1, meta_col_2)}

{DS.items_table(LI.with_column(PO_COLUMNS) if pics else PO_COLUMNS, rows,
                css=DS.MAKE_CSS)}
  </div>

  <div class="po-ask">
    <b>This is a request for your rates, not a priced order.</b> Please quote
    against each line, return the priced copy, and quote our inquiry number on
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
                f'padding:2rem;">No {DOC_NAME_PLURAL_LOWER} yet. Raise one from a '
                'bill of quantities.</td></tr>')

    series = SET.po_series()
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(DOC_NAME_PLURAL)}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PO_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Product <span>Inquiries</span></h1>
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

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · {DOC_NAME_PLURAL_LOWER} ·
    series {P.esc(series['prefix'])}</p></footer>
</main>
</body></html>""")


@po_draft_bp.route("/create", methods=["GET", "POST"])
def create_po(imported: dict = None):
    """
    `imported` (18 October 2026) is the one seam Import from Excel renders this
    form through, on a GET — the schedule, the matched lines, their quantities
    and pieces. Flask never passes it; the POST path never reads it.
    """
    boq_id = (imported or {}).get("boq_id") or request.args.get("boq") or ""
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
        if imported:
            return _entry_form(boq, {"date": _date.today().isoformat(),
                                     "_chosen": set(imported.get("chosen") or ()),
                                     "_qty": dict(imported.get("qty") or {}),
                                     "_pcs": dict(imported.get("pcs") or {}),
                                     "_make": dict(imported.get("make") or {})},
                               banner_html=imported.get("banner_html") or "")
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
        # The typed Pcs too (18 October 2026) — it was dropped on a refused
        # save until the picker learned to prefill it.
        data["_pcs"] = {BQ._line_id(r.get("line_id")): str(r.get("pcs") or "")[:16]
                        for r in posted if isinstance(r, dict)}
        # And the typed Make (26 Oct 2026), for the same reason.
        data["_make"] = {BQ._line_id(r.get("line_id")): str(r.get("make") or "")[:BP.MAKE_MAX]
                         for r in posted if isinstance(r, dict)}
        # And the chosen picture (29 Oct 2026, B2), for the same reason.
        data["_image"] = {BQ._line_id(r.get("line_id")): str(r.get("image") or "")
                          for r in posted if isinstance(r, dict)}
        return _entry_form(boq, data, error)

    # Carry the typed Pcs across. It is not on the BOQ and never will be.
    try:
        pcs_of = {BQ._line_id(r.get("line_id")): str(r.get("pcs") or "").strip()[:16]
                  for r in (json.loads(data["po_json"]).get("lines") or [])
                  if isinstance(r, dict)}
    except (ValueError, TypeError):
        pcs_of = {}
    # ⚠ **And the schedule's own HSN** (29 October 2026, §0 fifty-ninth block,
    #   A2/A1). Snapshotted at create like every other field, so the code the
    #   supplier is asked about is the one the schedule carried that day and
    #   `purchase.from_draft()` can take it from here rather than re-reading a
    #   BOQ that may have moved or gone. Absent when the BOQ line has none, so
    #   a row carries no empty key — `picked_lines()`'s shape.
    #   It prints nowhere on this document: a request for quotation carries no
    #   tax block at all (`PRINT_TAX`), and an HSN is a tax code.
    hsn_of = {BQ._line_id(li.get("line_id")): str(li.get("supply_hsn") or "").strip()
              for li in (boq.get("line_items") or [])}
    for row in items:
        if not row.get("is_header"):
            row["pcs"] = pcs_of.get(row["line_id"], "")
            code = hsn_of.get(row["line_id"], "")
            if code:
                row["hsn"] = code

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
                            msg=f"{DOC_NAME} raised.", type="success"))


@po_draft_bp.route("/view/<id>")
def view_po(id: str):
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg=f"That {DOC_NAME_LOWER} no longer exists.", type="error"))

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

    # Pictures (21 October 2026) — drawn only for a role the gate lets
    # through. The newline lives inside the string.
    import auth as _AUTH
    # Edit (29 October 2026, §0 fifty-ninth block, A2) — present with its
    # refusal printed on it rather than hidden, which is `ra.py`'s `_gated()`
    # rule: a control that vanishes teaches nothing about why it went. The
    # route refuses a typed URL on its own, on both methods; this is
    # presentation.
    if is_locked(po):
        edit_btn = ('<span class="btn btn-ghost" style="opacity:.55;'
                    'cursor:not-allowed;" title="Already converted into a '
                    'purchase order, so its lines and vendor are fixed.">'
                    'Edit</span>')
    else:
        edit_btn = (f'<a href="{url_for("po_draft.edit_po", id=id)}" '
                    f'class="btn btn-ghost">Edit</a>')
    pics_btn = ""
    if _AUTH.can_reach("po_draft.pictures"):
        pics_btn = (f'\n    <a href="{url_for("po_draft.pictures", id=id)}" '
                    f'class="btn btn-ghost">&#128247;&nbsp;Pictures</a>')

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(po.get('ref')) + " " + DOC_NAME)}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{PO_DOC_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    {DOC_NAME} <span style="color:var(--brand);">{P.esc(po.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('po_draft.list_pos')}" class="btn btn-ghost">All {DOC_NAME_PLURAL}</a>
    <a href="{url_for('boq.view_boq', id=po.get('boq_id', ''))}" class="btn btn-ghost">{P.esc(po.get('boq_ref'))}</a>
    {convert_html}
    {edit_btn}{pics_btn}
    <a href="{url_for('po_draft.delete_po', id=id)}" class="btn btn-ghost">Delete</a>
    <a href="{url_for('po_draft.print_po', id=id)}" class="btn">&#128438;&nbsp;Print</a>
  </div>
</div>

{_flash()}
{converted_strip}

<div class="doc-outer">
{_document_html(po)}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · {DOC_NAME_LOWER}</p>
</footer>
</main>
</body></html>""")


@po_draft_bp.route("/print/<id>")
def print_po(id: str):
    """The document alone behind a `.no-print` action bar — `/boq/print`'s shape."""
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg=f"That {DOC_NAME_LOWER} no longer exists.", type="error"))

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
    **Every field and every line, while this draft is UNCONVERTED**
    (29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, A2).

    Vendor, date, delivery address, notes and terms; and per line the
    description, item number, unit, quantity, pieces, make and HSN, with lines
    added and removed freely. A specification row can be added too, carrying
    the clause and no quantity.

    ⚠ **LOCKED once it has been converted into a purchase order, and refused
      on the POST as well as hidden on the GET.** `is_locked()` is asked twice
      and the POST path writes nothing when it answers True — a form that is
      merely not drawn is not a lock. A document a real order was raised from
      is the record of what that order was raised from.

    ⚠ **No rate box.** `PRINT_RATES` is False and nothing on this document may
      read a buy rate from anywhere (the module docstring); the supplier fills
      the rates in. A2's brief named "rate" among the editable fields and
      Manas's answer, with the conflict put to him, was: no rate box, and the
      printed Rate column stays empty. Recorded in the §0 block.

    ⚠ **`ref` is deliberately untouched** and an edit never reissues the
      number — the fifty-fourth block's carve-out stands, and so does the
      global counter's "a number is never released".

    **What this replaced**, so the narrowing it reverses is findable: until
    this pass the route edited the vendor, the date, the delivery address and
    the notes, plus each line's *make* (26 October 2026, the fifty-third
    block, change 2) — and nothing else, because *"an issued draft PO is a
    document a supplier is pricing, and moving the lines under it is how a
    dispute starts"*. That reasoning was right about a **converted** draft and
    too strong about an unconverted one, which has gone to nobody yet. The
    lock above is where it now lives.
    """
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg=f"That {DOC_NAME_LOWER} no longer exists.", type="error"))

    # ⚠ **BOTH methods, and the POST writes nothing.** The GET redirects so a
    #   bookmarked form cannot be filled in and submitted; the POST refuses
    #   before `_validate()` is even called, so no value is read off a form
    #   that may not change this document.
    if is_locked(po):
        return redirect(url_for("po_draft.view_po", id=id,
                                msg=P.esc(LOCK_REASON).replace("&mdash;", "—"),
                                type="error"))

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
    items, line_error = (None, "") if error else parse_items(request.form, po)
    error = error or line_error
    if error:
        # Hand the operator back exactly what they typed, rows and all — a
        # browser cannot refill a form and a refused save must not lose work.
        data["_items"] = _posted_rows(request.form)
        return _entry_form(boq, data, error, po=po)

    po["date"] = data["date"]
    po["notes"] = data["notes"]
    po["delivery_to"] = data["delivery_to"]
    # `None` is a stale tab (`parse_items()`), and leaves the lines alone.
    if items is not None:
        po["items"] = items
    po.update(data["vendor"])
    # `ref` is deliberately untouched. An edit never reissues the number.
    return redirect(url_for("po_draft.view_po", id=id,
                            msg=f"{DOC_NAME} updated.", type="success"))


def _picture_entries(po: dict) -> list:
    """Every line that can carry a picture, numbered as the sheet numbers them."""
    out, sno = [], 0
    for n, r in enumerate(po.get("items") or []):
        if r.get("is_header"):
            continue
        sno += 1
        out.append(LI.entry(f"it:{n}", sno, r.get("item_no"), r.get("description"), r))
    return out


@po_draft_bp.route("/pictures/<id>", methods=["GET", "POST"])
def pictures(id: str):
    """
    The picture beside each line of a draft PO (21 October 2026).

    The draft is what a supplier prices from, so this is where a picture does
    the most work: they quote for the part they can see. `po.edit` — the edit
    route's permission, and like that route it never moves a line; the
    picture is the only thing written. A converted order takes each line's
    picture with it (`purchase.from_draft()`); one already converted keeps
    the copy it took. One upload per request (`lineimage.py` says why).
    """
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg=f"That {DOC_NAME_LOWER} no longer exists.", type="error"))

    here = url_for("po_draft.pictures", id=id)
    if request.method == "POST":
        msg, err = LI.apply_post(request.form, request.files, _picture_entries(po))
        return redirect(url_for("po_draft.pictures", id=id, msg=msg or err,
                                type="error" if err else "success"))

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(po.get('ref')) + " Pictures")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{LI.PAGE_CSS}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Pictures &middot; <span>{P.esc(po.get('ref'))}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('po_draft.view_po', id=id)}" class="btn btn-ghost">&#8592; Back to the {DOC_NAME_LOWER}</a>
    </div>
  </div>

  {_flash()}

  <div class="form-section">
    <div class="section-title">A picture beside each line</div>
    <p class="field-hint" style="margin:0 0 1rem;">
      A picture prints in an <b>Image</b> column beside the description, so the
      supplier prices the part they can see. A line with none prints an empty
      cell; a draft with no picture at all prints no Image column. JPEG, PNG or
      WebP up to 5&nbsp;MB, one line at a time &mdash; it is shrunk to
      {LI.MAX_SIDE}&nbsp;px and stored once. Nothing else on the draft changes here.
    </p>
    {LI.rows_html(_picture_entries(po), here, editable=True)}
  </div>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · {DOC_NAME_LOWER}</p></footer>
</main>
</body></html>""")


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

    ⚠ **A draft that has been CONVERTED cascades into the real order it
      produced** (23 September 2026), and the confirmation page names it before
      the button. Until then this route popped the draft alone and left
      `purchases.draft_id` pointing at a record that no longer existed — the
      dangling-reference gap ABOUT.md §7 recorded against this module. It is
      closed by destroying the pair rather than by clearing the field, because
      a real order raised from a draft nobody can now produce is not a record
      anybody can answer questions about.

      **It is not a silent cascade.** `cascade.impact_of()` counts the closure
      and `cascade.impact_html()` prints it on the GET, so an Owner deleting a
      converted draft is told a Purchase Order goes with it and confirms that
      specifically. A route that destroys something the page did not name is a
      defect (ABOUT.md §5 `/po`).
    """
    po = (STORE.get("purchase_orders") or {}).get(id)
    if not po:
        return redirect(url_for("po_draft.list_pos",
                                msg=f"That {DOC_NAME_LOWER} no longer exists.", type="error"))

    report = cascade.impact_of("purchase_orders", id)

    if request.method == "GET":
        return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delete " + DOC_NAME)}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PO_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top"><h1>Delete <span>{P.esc(po.get('ref'))}</span></h1></div>
  <div class="card" style="border:1px solid var(--border);border-radius:10px;padding:1.2rem;">
    <p>Delete {DOC_NAME_LOWER} <b>{P.esc(po.get('ref'))}</b> to
       <b>{P.esc(po.get('vendor_name')) or 'an unnamed supplier'}</b>, raised
       against {P.esc(po.get('boq_ref'))}?</p>
    <p style="font-size:.85rem;color:var(--muted);">
      This cannot be undone. <b>The number is not released</b> — the next draft
      PO takes the next one in the series, because {P.esc(po.get('ref'))} may
      already have been quoted to a supplier.
    </p>
  </div>
{cascade.impact_html(report)}
  <div class="card" style="border:1px solid var(--border);border-radius:10px;padding:1.2rem;">
    <form method="POST" style="display:flex;gap:.75rem;">
      <button type="submit" class="btn">Delete it</button>
      <a href="{url_for('po_draft.view_po', id=id)}" class="btn btn-ghost">Cancel</a>
    </form>
  </div>
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · {DOC_NAME_LOWER}</p></footer>
</main>
</body></html>""")

    boq_id = po.get("boq_id", "")
    ref = po.get("ref", "")
    destroyed = cascade.delete_cascade("purchase_orders", id)
    extra = (f" {len(destroyed)} converted order"
             f"{'' if len(destroyed) == 1 else 's'} went with it."
             if destroyed else "")
    return redirect(url_for("boq.view_boq", id=boq_id,
                            msg=(f"{DOC_NAME} {ref} deleted.{extra} "
                                 f"Its number is not reissued."),
                            type="success"))
