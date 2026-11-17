"""
challan.py — Delivery Challan from a BOQ
========================================
Blueprint  : challan_bp
Mounted at : /dc  (registered in app.py)

CLIENT_CHANGES.md item 5. Built to the client's own DC54: a goods-movement note
that travels with the material.

Routes
------
  GET       /dc/              — register of delivery challans
  GET,POST  /dc/create?boq=   — pick the lines, name the consignee, raise it
  GET,POST  /dc/create?noboq=1 — a challan with NO BOQ: extra items only,
                                optional project (17 Nov 2026, §0 75th block)
  GET       /dc/view/<id>     — the document, with the action bar
  GET       /dc/print/<id>    — the document alone, ready for Ctrl+P
  GET,POST  /dc/edit/<id>     — consignee and dispatch fields only, never lines
  GET,POST  /dc/delete/<id>   — GET confirms, POST deletes

What a challan IS, and what it is not
-------------------------------------
It records **goods leaving the yard**. It carries no rate, no amount, no tax,
no bank details and no total, and that is the document rather than an
unfinished state — a challan that carries money is an invoice wearing a
different heading (CLIENT_CHANGES.md item 5).

It is **not part of the sell chain and not part of the buy chain.** It hangs
off the project chain beside the RA bill, and independently of it:

    BOQ ──► RA bill 1 ──► RA bill 2 ──► …        money claimed
        └─► challan, challan, …                  goods moved

⚠ **The two are not reconciled and this module must not import `ra.py`.** A DC
  records material dispatched; an RA bill records money claimed. They diverge
  in both directions on a real site — material dispatched and not yet billed,
  material billed and not yet dispatched — and coupling them would force one to
  answer the other's questions. That nothing compares them is a known gap
  (ABOUT.md §7 gap 19), not an oversight this module should close on its own.

⚠ **From 4 October 2026 an RA bill may be raised FROM challans** (the §0
  fortieth block), and such a bill names them in `source_dc_ids`. This module
  says *Billed in <RA ref>* on `/dc/view` and the register, and offers *Raise RA
  (Supply)* on an unbilled one — reading the answer through `dcbill.py`, the
  leaf that holds the ONE billed predicate, and never through `ra.py`. Nothing
  is written to a challan when it is billed or freed.

The consignee is the SITE, not the billed-to party
--------------------------------------------------
On the client's own DC54 the consignee is **Samruddhi Fire themselves**, at
"Sify Infinit, Bangalore": they are moving their own material to their own
store on a project, not selling it to anybody (DOMAIN.md §5.1). So the
consignee defaults to the company's own name and is **never wired to the BOQ's
`account_name`** — that is the main contractor being billed, who is exactly the
party the goods are *not* being consigned to.

Its OWN collection
------------------
`STORE["delivery_challans"]`, keyed by UUID, pointing at the BOQ it came from —
CLIENT_CHANGES.md §1.3. One BOQ accumulates many challans over a project's
life, and a BOQ record is one JSON blob against `boq.MAX_JSON_BYTES`.

Import direction
----------------
    challan.py ──► boq.py       superseded_ids, _line_id, _item_no, _fmt_qty,
                                _ancestor_ids — the revision chain
    challan.py ──► boqpick.py   the line picker, shared with po_draft.py
    challan.py ──► docsheet.py  the printed A4 sheet
    challan.py ──► address.py   the consignee picker
    challan.py ──► settings.py  the number series
    challan.py ──► quotation.py QUOTATION_STYLES + _inr — the form widgets
    challan.py ──► dashboard.py BASE_STYLES / _nav / REGISTER_STYLES
    challan.py ──► pipeline.py  esc / gstin_state_label
    challan.py ──► dcbill.py    billed_by / billing_index — the one billed
                                predicate (4 Oct 2026), a leaf
    challan.py ──► store, branding

⚠ **`REGISTER_STYLES` is loaded by `/dc/` ONLY, and that matters.** This module
owns `challan.print_dc`, which `tests/test_print_golden.py` hashes byte for
byte, and `dashboard.REGISTER_STYLES` is a **screen** sheet. Splicing it into
the wrong shell moves a pinned digest for a change that never reaches paper —
`tests/test_registers.py::test_the_pinned_challan_sheet_does_not_carry_the_register_styles`
is what stops that happening quietly.

⚠ **The REGISTER no longer borrows `.pk-table` from `boqpick.PICKER_CSS`**
(30 August 2026). It did, and that was a live coupling rather than a tidiness
point: `PICKER_CSS` is spliced into `po_draft.PO_STYLES` and `/po/create` is
hashed byte for byte, so restyling this register would have moved a golden for
a page that renders no register at all. The picker on `/dc/create` still uses
it, which is what it is for.

`boq.py` must **never** import this module: `/boq/view` links out with
`url_for` and reads `STORE["delivery_challans"]` directly, the one-way trick
used six times now. It must not import `invoice.py`, `ra.py`, `purchase.py`,
`po_draft.py`, `quotation.py`'s chain, `proforma.py` or `product.py` either —
asserted in `tests/test_import_directions.py`.
"""

import json
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import boq as BQ
import boqpick as BP
# The manual PO's Specification-library picker (31 Oct 2026), reused for a
# challan's EXTRA items (17 Nov 2026, §0 seventy-fifth block). A leaf: it reads
# the library out of STORE and never writes it.
import extraitems as EX  # extra items + project link — the leaf (17 Nov 2026)
import dcpo as DCPO      # a challan FROM a purchase order — the leaf (17 Nov 2026)
import tinum as TN       # the number set by hand, free format — the leaf (17 Nov 2026)
import units as UN     # the shared unit list — the leaf (29 Oct 2026)
import branding as B
# "Is this challan billed, and by which RA bill?" (CLIENT_CHANGES.md §0,
# fortieth block, ruling C). A LEAF that reads the bills out of STORE, so this
# module learns the answer WITHOUT importing `ra.py` — the prohibition above is
# untouched — and without a second copy of the predicate beside `ra.py`'s.
import dcbill as DCB
import docnum as DN    # the MANUAL document number, forward only (27 Oct 2026)
import editlog as EL   # the edit-after-issue log — the leaf (31 Oct 2026)
import formdraft as FD  # an unsaved form survives Back — Resume / Discard (31 Oct 2026)
import docsheet as DS
import pipeline as P
import dcqty as DQ   # Qty (Mtr) and Qty (Nos) — the leaf (17 Nov 2026)
import settings as SET
from address import picker_options, format_address_lines, CONSIGNEE_TYPES
from chrome import BASE_STYLES, _nav
from dashboard import REGISTER_STYLES
from store import STORE

# ⚠ **`QUOTATION_STYLES` is read through `docsheet`, not imported from
#   `quotation.py`.** Every form in this app is built out of that sheet's
#   `.form-section` / `.fg2` / `.form-group` widgets, and re-declaring them
#   here would be a second design system — the thing `tests/test_page_chrome.py`
#   exists to catch. But this module is on `quotation.py`'s prohibited-import
#   list, so it takes the same route `ra.py` takes to the tax invoice's
#   letterhead: **through the leaf.** `docsheet.py` imports `quotation.py`
#   deliberately (ABOUT.md §2d) and re-exports the sheet as part of the stack.
#   This is that arrangement used a second time, not a way around the rule; if
#   the shared form furniture ever moves out of `quotation.py`, this line
#   follows it.
QUOTATION_STYLES = DS.QUOTATION_STYLES

challan_bp = Blueprint("challan", __name__, url_prefix="/dc")


# =============================================================================
# BUSINESS RULES — module-level constants, never buried in a branch
# =============================================================================

# No money of any kind reaches this document. Named constants rather than an
# absence, so the rules are findable: a challan carries goods, and a rate on it
# turns a delivery note into an invoice nobody agreed to.
PRINT_RATES = False
PRINT_TAX = False
PRINT_TOTALS = False

# ⚠ **Over-dispatch WARNS and never blocks.** The RA over-claim guard is a hard
#   block because it guards money billed to a main contractor and an over-claim
#   is a false claim. This is a goods-movement note, and real sites have
#   replacements, breakages, free issue and returns. Blocking here would stop
#   lawful movements and push people to write challans outside the system,
#   which is worse than an unreconciled number.
BLOCK_OVER_DISPATCH = False

# The line cap. Derived from `boq.MAX_LINES` rather than chosen, for the reason
# `po_draft.MAX_PO_LINES` and `ra.MAX_RA_LINES` are: the form renders every
# line of the BOQ, so a schedule legal at 600 lines must post a challan legal
# at 600 lines.
MAX_DC_LINES = BQ.MAX_LINES

# Their own DC54 is dispatched by "Transport". It is free text and editable;
# this is only what the empty form opens with.
DEFAULT_DISPATCH_MODE = "Transport"

# ⚠ **The blank ruled rows on their form are deliberately NOT reproduced.**
#   DC54 carries about twenty empty ruled rows under the three used ones,
#   because it is a spreadsheet printed for a human to write more lines on by
#   hand. A generated challan lists exactly what left the yard, and blank ruled
#   rows under a signature are an invitation to add a line after the receiver
#   has signed for it. Raising a second challan is cheap and leaves a trail.
PRINT_BLANK_ROWS = False


def new_id() -> str:
    return str(uuid.uuid4())


# =============================================================================
# NUMBERING — one global series, and a number is never released
# =============================================================================

def next_ref() -> str:
    """
    The next challan number, from the series held at `/settings`.

    **Global, not per-BOQ, and that is the opposite of `ra_no`.** They run one
    paper challan series across every supplier and every site — DC54 is a bare
    `54` with no prefix and nothing about the project in it — so the next
    number depends on every challan ever raised and on nothing about the
    schedule it came from. `ra_no` is per project because it is that job's own
    RA sequence.

    **A high-water mark, never `max+1` over the surviving records.** The
    counter is stored at `/settings` and only ever advances, so deleting a
    challan **spends** its number rather than handing it back. The paper it is
    written on has already travelled with a load of material; a second document
    bearing the same number is indistinguishable from the first.
    `po_draft.next_ref()` shipped as `max+1` and was fixed; this is the fixed
    implementation, not the original.

    The shape — bare integer or padded prefix — is `settings.dc_ref_of()`,
    which owns it because `/settings` has to preview it while it is being
    typed and may not import this module.
    """
    return SET.dc_ref_of(SET.dc_series())


def _spend_ref(seq: int = 0) -> str:
    """
    Take a number and advance the counter past it. Call once, at save.

    ⚠ **`seq` is the TYPED number** (27 October 2026, CLIENT_CHANGES.md §0's
      fifty-fourth block). 0 means "whatever the series was pointing at", which
      is what every caller meant before this argument existed and is still what
      the import seam and an operator who leaves the box alone get.

    ⚠ **The counter goes to `seq + 1`, not to `next_no + 1`.** That is item A's
      point 4 and it is the whole of it: a number typed ahead of the series
      SPENDS everything it skipped, so the skipped ones are never handed out
      later. The counter has only ever gone forwards here — see this module's
      `next_ref()`, whose comment is explicit that deleting a challan spends
      its number — so this is that rule applied to a bigger step, not a new
      one.
    """
    series = SET.dc_series()
    n = int(seq) if int(seq or 0) > 0 else int(series["next_no"] or 1)
    ref = SET.dc_ref_of({"prefix": series["prefix"], "next_no": n})
    SET.save_dc_series(series["prefix"], n + 1)
    DN.note_used(DN.DC, "", n)
    return ref


# ── The challan number, FREE FORMAT (17 Nov 2026, §0 eightieth block) ──────
#
# The client sets the number to whatever they need, as on the tax invoice
# (`tinum.py`, kind "dc"): any non-blank value, trimmed, not forward-only; a
# number on another live challan is refused, naming it. ⚠ **The counter is
# STORED, not scanned**, so a typed number in the counter's own shape at or
# above it would later be minted again — `_take_free()` moves the counter past
# it. Forward only: it never moves back, and a free value of any other shape
# (`DC-77/A`) does not touch it.

def _free_may() -> bool:
    import auth as _AUTH
    return _AUTH.may_type_ti_number()


def _free_number(form, current: str = "", rec_id: str = "", required: bool = False):
    """`(value, error)` for the free-format box; ("", "") when it is blank on create."""
    return TN.validate(form.get(TN.DOC_FIELD), current=current,
                       coll="delivery_challans", rec_id=rec_id, kind="dc",
                       required=required, may=_free_may())


def _counter_shape_of(value: str) -> int:
    """The counter ordinal a value is in the series' own shape, else 0."""
    series = SET.dc_series()
    v = str(value or "").strip()
    prefix = str(series.get("prefix") or "")
    if not prefix:
        return int(v) if v.isdigit() else 0
    head, sep, tail = v.rpartition("/")
    return int(tail) if sep and head == prefix and tail.isdigit() else 0


def _take_free(value: str) -> str:
    """Keep the counter ahead of a typed number in its own shape. Returns it."""
    n = _counter_shape_of(value)
    series = SET.dc_series()
    if n and n >= int(series["next_no"] or 1):
        SET.save_dc_series(series["prefix"], n + 1)
        DN.note_used(DN.DC, "", n)
    return value


def _free_box(value: str = "", creating: bool = True) -> str:
    return TN.field_html(
        value, may=_free_may(), kind="dc",
        label="or type any challan number" if creating else "Challan No. (any format)",
        hint=("Optional. When typed it is this challan's number, in any format, "
              "and the box above is not used. A number already on another "
              "challan is refused." if creating else
              "Any format. A number already on another challan is refused; "
              "every change is logged on screen and never printed."))


def _may_set_number() -> bool:
    """
    May this user type a document number? The function-body `import auth` is
    the hatch `_raise_ra_btn()` already takes for `can_reach()`.
    """
    import auth as _AUTH
    return _AUTH.has_perm("docnum.override")


def _actor_id() -> str:
    """The id of whoever is saving — never their display name (gap 41)."""
    import auth as _AUTH
    return str((_AUTH.current_user() or {}).get("id") or "")


def _number_control(typed: str, may: bool) -> tuple:
    """
    `(default_seq, control_html)` for the challan's number field.

    ⚠ **A blank prefix means the whole number is typeable**, and that is
      right rather than an edge case: `settings.dc_ref_of()`'s own docstring
      records that a blank prefix gives the bare integer `54`, *"the client's
      own book and the reason the prefix defaults to blank"*. There is no
      fixed part to protect, so `docnum.split_ref()` returns none and the
      field is the number.

    ⚠ **No skip note** — that belongs to the tax invoice alone (point 6).
    """
    series = SET.dc_series()
    seq = int(series["next_no"] or 1)
    return seq, DN.number_field(DN.DC, SET.dc_ref_of(series),
                                may_override=may, typed=typed)


def challans_of_boq(boq_id: str) -> list:
    """`[(id, dc)]` raised against this specific BOQ revision, newest first."""
    rows = [(cid, dc) for cid, dc in (STORE.get("delivery_challans") or {}).items()
            if dc.get("boq_id") == boq_id]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""),
                              str(kv[1].get("ref") or "")), reverse=True)
    return rows


# =============================================================================
# CUMULATIVE DISPATCH — derived, never stored
# =============================================================================

def dispatched_by_line(boq_id: str, exclude_id: str = "") -> dict:
    """
    `{line_id: qty}` dispatched against this BOQ's revision chain.

    **Derived on every read and never stored**, exactly as
    `ra.claimed_by_line()` is. A maintained counter has to be updated on every
    create, revision and delete, and a path that misses one leaves the figure
    silently wrong — which is worse than no figure, because it is trusted.

    **Summed across the whole revision chain**, not against one BOQ record. A
    revision is a new record, so a per-record sum would report nil dispatched
    the moment a schedule was revised — silently, and only on the projects that
    have been revised. That is the mistake `claimed_by_line()` exists to avoid,
    one chain over. `boq._ancestor_ids()` supplies the chain; `ra.py` also
    walks forward, but a challan is always raised against the tip, so backward
    is the whole chain from here.

    `exclude_id` leaves one challan out, which is what the over-dispatch band
    needs: "what did everything *else* already move".
    """
    chain = BQ._ancestor_ids(boq_id) if boq_id else set()
    out = {}
    for cid, dc in (STORE.get("delivery_challans") or {}).items():
        if cid == exclude_id:
            continue
        if str(dc.get("boq_id") or "") not in chain:
            continue
        for row in dc.get("items") or []:
            if row.get("is_header"):
                continue
            lid = BQ._line_id(row.get("line_id"))
            if not lid:
                continue
            # The quantity in the line's OWN unit (17 Nov 2026, dcqty.py).
            out[lid] = out.get(lid, 0.0) + DQ.billing_qty(row)
    return out


def over_dispatched(dc: dict) -> list:
    """
    `[(item_no, description, dispatched, approved)]` for every line this
    challan pushes past its BOQ quantity — **a warning, never a refusal.**

    Read `BLOCK_OVER_DISPATCH` above for why this does not block. The approved
    figure comes from the live BOQ rather than the challan, because the
    question is "is the schedule exceeded *now*"; the printed challan is still
    driven entirely by its own rows and nothing here reaches the document.
    """
    boq = (STORE.get("boqs") or {}).get(dc.get("boq_id") or "")
    if not boq:
        return []
    approved = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            approved[lid] = float(li.get("total_qty") or 0.0)

    others = dispatched_by_line(dc.get("boq_id") or "", exclude_id=dc.get("id") or "")
    out = []
    for row in dc.get("items") or []:
        if row.get("is_header"):
            continue
        lid = BQ._line_id(row.get("line_id"))
        if not lid or lid not in approved:
            continue
        total = others.get(lid, 0.0) + DQ.billing_qty(row)
        # Rounded at `P.QTY_EPSILON` for `ra.py`'s reason: 1.1 + 2.2 + 8.7 is
        # 12.000000000000002, and that is not an over-dispatch of two
        # femtometres against an approved 12.
        #
        # ⚠ **This was the literal `1e-6` until 9 September 2026**, while
        #   `measurement.py`'s comment asserted it and `ra._QTY_EPSILON` were the
        #   same figure. They agreed by coincidence. `challan.py` may import
        #   neither `ra.py` nor `measurement.py`, so the shared figure lives in
        #   `pipeline.py` — the bottom of the graph, which this module already
        #   imports as `P`.
        if total - approved[lid] > P.QTY_EPSILON:
            out.append((str(row.get("item_no") or ""),
                        str(row.get("description") or ""),
                        total, approved[lid]))
    return out


# =============================================================================
# THE CONSIGNEE — the SITE, with a picker and a free-text fallback
# =============================================================================

def consignee_from(form) -> tuple:
    """
    Returns `(fields, error)` for whichever way the consignee was given.

    **Free text is the specified path and stays the primary one**; the
    address-book picker sits beside it as an optional prefill, exactly as
    `po_draft.vendor_from()` offers one for the vendor. Replacing the free-text
    fields with the picker outright was a rejected behaviour in the first
    draft-PO pass, and it would be wrong here for a further reason: the
    consignee is a **site**, and a site store that exists for four months is
    not worth an address-book entry.

    ⚠ **Never wired to the BOQ's `account_name`.** That is the main contractor
      being billed. On DC54 the consignee is Samruddhi themselves — the goods
      are going to their own site store (DOMAIN.md §5.1).

    Whichever path was used is snapshotted onto the record (`consignee_source`
    is `"book"` or `"typed"`), so the document does not move when the address
    book is edited underneath it.
    """
    cid = (form.get("consignee_id") or "").strip()[:64]
    name = (form.get("consignee_name") or "").strip()[:200]
    addr = (form.get("consignee_addr") or "").strip()[:500]
    phone = (form.get("consignee_phone") or "").strip()[:32]

    if cid:
        book = (STORE.get("addresses") or {}).get(cid)
        if not book:
            return {}, "That address is no longer in the address book."
        lines = format_address_lines(book)
        return {
            "consignee_id": cid,
            "consignee_source": "book",
            # The typed name still wins if one was given: the picker is a
            # prefill, and an operator who edited the box meant it.
            "consignee_name": name or (book.get("company")
                                       or book.get("contact_name") or ""),
            "consignee_addr": addr or "\n".join(lines[1:]) or "\n".join(lines),
            "consignee_phone": phone or (book.get("phone") or "").strip(),
        }, ""

    if not name:
        return {}, ("A challan needs a consignee — who the goods are going to. "
                    "It is usually us, at the site store.")
    return {
        "consignee_id": "",
        "consignee_source": "typed",
        "consignee_name": name,
        "consignee_addr": addr,
        "consignee_phone": phone,
    }, ""


# =============================================================================
# A CHALLAN WITHOUT A BOQ, AND EXTRA ITEMS ON ANY CHALLAN
# (17 November 2026, CLIENT_CHANGES.md §0 seventy-fifth block)
# =============================================================================
#
# ⚠ **An extra item is NOT a schedule line.** It is stored with
#   `line_id: None` and `extra: True`, and every reader that keys on
#   `line_id` — `dispatched_by_line()`, `over_dispatched()`,
#   `ra.dispatched_in()`, `pnl.py`'s dispatched figure — already skips a row
#   with no id. So an extra is never dispatched against a line, never capped,
#   and never billed on an RA bill.
#
# ⚠ **A no-BOQ challan has `boq_id: None`.** It takes the SAME number series,
#   it never reaches `/ra/create`'s challan picker (it is on no revision
#   chain), and it reaches a project only through its own `project_id`, with
#   the name snapshotted beside it (`charge.py`'s pattern).
#
# ⚠ **A record without these keys renders exactly as before.** Nothing is
#   migrated; `_document_html()` is untouched and prints every stored row.

# The rows the extras section opens with, the cap and the description cap
# live in `extraitems.py` with the helpers (17 Nov 2026).

# The refusal `picked_lines()` makes when nothing is ticked. A BOQ challan
# carrying extra items may tick no BOQ line, so the caller recognises it.
EMPTY_PICK_MSG = ("No lines are ticked. A challan with nothing on it is not a "
                  "document — tick what is going out, or cancel.")


# ⚠ **The helpers below LIVE IN `extraitems.py`** (17 Nov 2026, §0
#   seventy-sixth block) — lifted at their second consumer, the Product
#   Inquiry, which may not import this module. These names stay so every
#   caller and test is unchanged, and the defaults there are this module's
#   own strings, so the challan's forms render byte-for-byte as before.

def is_extra(row) -> bool:
    """A row the operator added by hand — never a BOQ line."""
    return EX.is_extra(row)


def has_boq_lines(dc) -> bool:
    """
    Does this challan carry at least one BOQ line? A challan whose only rows
    are extras has nothing an RA bill could claim, so it is never offered as
    unbilled.
    """
    return any(isinstance(r, dict) and not r.get("is_header")
               and BQ._line_id(r.get("line_id"))
               for r in (dc or {}).get("items") or [])


def project_link_from(form) -> tuple:
    """`extraitems.project_link_from()` — the optional project, snapshotted."""
    return EX.project_link_from(form)


def parse_extras(form, with_ref: bool = False, allowed_refs=None) -> tuple:
    """`(rows, error)` — the extra items, by `extraitems.parse_extras()`.

    `with_ref` (17 Nov 2026): a challan raised from a purchase order carries
    each row's order line (`po_key`) through an edit; `allowed_refs` is that
    order's own keys."""
    return EX.parse_extras(form, with_ref=with_ref, allowed_refs=allowed_refs,
                           two_qty=True)


def _extra_row_html(desc="", qty="", unit="", pick="", spec=None) -> str:
    """One extra-item row — `extraitems.extra_row_html()`."""
    return EX.extra_row_html(desc, qty, unit, pick, spec=spec)


def _extras_section_html(stored: list = None, posted=None,
                         with_ref: bool = False) -> str:
    """The *Extra items* section — `extraitems.extras_section_html()`."""
    return EX.extras_section_html(stored, posted, fmt_qty=BQ._fmt_qty,
                                  with_ref=with_ref, two_qty=True)


# =============================================================================
# A CHALLAN FROM A PURCHASE ORDER (17 November 2026, §0 seventy-eighth block)
# =============================================================================
#
# ⚠ **This module may not import `purchase.py`, and `purchase.py` may not
#   import this one** (`tests/test_import_directions.py`). The order's lines
#   and what has already gone out against them are `dcpo.py`'s — a leaf that
#   reads `STORE` directly and that both modules import. The route lives HERE
#   because it writes a challan; the order's view links to it by `url_for`.
#
# ⚠ **What the challan carries.** `source_po_id` / `source_po_ref`, and on
#   every row taken off the order a `po_key` (`dcpo.lines_of()`'s key), which is
#   what the remainder is summed on — DERIVED, never stored. An order with a
#   BOQ gives a BOQ challan (its `boq_id`, the BOQ lines through the ordinary
#   picker so they are exactly a BOQ challan's lines, `line_id` kept); every
#   other line, and every order line on an order with no BOQ, is an extra.
#
# ⚠ **Never the vendor as consignee.** The goods go to our site; the
#   consignee opens at the order's own delivery address, else blank.
#
# ⚠ **`po_no` / `po_date` are NOT filled from the order.** They print on the
#   challan and the client is still confirming which PO number belongs there,
#   so they stay typed by hand exactly as on every other challan.

PO_NOTHING_TICKED = ("No lines are ticked. A challan with nothing on it is not "
                     "a document — tick what is going out, or cancel.")


def _po_for_dc(po_id: str):
    """`(po, error)` — the order, refused when it is gone or Cancelled."""
    po = (STORE.get("purchases") or {}).get(str(po_id or "")[:64])
    if not po:
        return None, "That purchase order no longer exists."
    if DCPO.is_withdrawn_po(po):
        return None, (f"Purchase order {po.get('ref') or ''} is Cancelled, so "
                      f"nothing is dispatched against it.")
    return po, ""


_PO_PICK_JS = """<script>
/* Amber, never blocking: a quantity above what is left on the order. */
function dcPoWarn(box) {
  var row = box.closest('tr'), w = row ? row.querySelector('.po-over') : null;
  var left = parseFloat(box.getAttribute('data-left')), n = parseFloat(box.value);
  if (w) w.style.display = (!isNaN(n) && !isNaN(left) && n > left) ? 'inline' : 'none';
}
document.querySelectorAll('input[data-left]').forEach(function (b) { dcPoWarn(b); });
</script>"""


def _po_picker_html(po: dict, data: dict) -> str:
    """Every line of the order, ticked, at what is left of it. Rate-less."""
    rows_src = DCPO.lines_of(po)
    sent = DCPO.dispatched_by_key(po.get("id"))
    on = data.get("_po_on")
    qty_of = data.get("_po_qty") or {}
    body = ""
    for r in rows_src:
        k = r["key"]
        left = max(r["qty"] - sent.get(k, 0.0), 0.0)
        qty = qty_of.get(k)
        if qty is None:
            mtr_txt, nos_txt = (DQ.fmt(v) if v is not None else ""
                                for v in DQ.split(left, r["unit"]))
        else:
            mtr_txt, nos_txt = str(qty.get("mtr") or ""), str(qty.get("nos") or "")
        own_mtr = DQ.unit_class(r["unit"]) == "mtr"
        checked = " checked" if (on is None or k in on) else ""
        tag = ("BOQ line" if r["kind"] == "boq" else
               "extra line" if r["kind"] == "extra" else "order line")
        body += f"""
          <tr>
            <td style="width:2rem;"><input type="checkbox" name="pl_on" value="{P.esc(k)}"{checked}
                 aria-label="Dispatch this line"/><input type="hidden" name="pl_key" value="{P.esc(k)}"/></td>
            <td>{P.esc(r["item_no"]) or "&mdash;"}</td>
            <td>{P.esc(" ".join(r["description"].split())[:160])}
              <div style="font-size:.7rem;color:var(--muted);">{tag}</div></td>
            <td>{P.esc(r["unit"])}</td>
            <td style="text-align:right;">{BQ._fmt_qty(r["qty"])}</td>
            <td style="text-align:right;">{BQ._fmt_qty(sent.get(k, 0.0))}</td>
            <td style="text-align:right;"><input type="text" name="pl_qty_mtr" value="{P.esc(mtr_txt)}"
                 inputmode="decimal"{f' data-left="{left:g}" oninput="dcPoWarn(this)"' if own_mtr else ""}
                 aria-label="Quantity in metres" style="width:6rem;text-align:right;"/></td>
            <td style="text-align:right;"><input type="text" name="pl_qty_nos" value="{P.esc(nos_txt)}"
                 inputmode="decimal"{"" if own_mtr else f' data-left="{left:g}" oninput="dcPoWarn(this)"'}
                 aria-label="Quantity in numbers" style="width:6rem;text-align:right;"/>
              <span class="po-over" style="display:none;color:#9a6700;font-size:.75rem;">
                above the {BQ._fmt_qty(left)} {P.esc(r["unit"])} left &mdash; saved anyway</span></td>
          </tr>"""
    if not body:
        body = ('<tr><td colspan="8" style="color:var(--muted);">This purchase '
                'order has no lines.</td></tr>')
    return f"""
    <div class="form-section">
      <div class="section-title">Lines going out &mdash; from {P.esc(po.get("ref"))}</div>
      <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
        Every line of the order is ticked, at what is <b>left</b> of it after the
        challans already raised from this order. Untick what is not on this load.
        A quantity above what is left is warned about and saved anyway.
        <b>No rates</b> &mdash; a challan carries no money.
      </p>
      <input type="hidden" name="pl_present" value="1"/>
      <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:.84rem;">
        <thead><tr style="text-align:left;font-size:.7rem;text-transform:uppercase;color:var(--muted);">
          <th></th><th>Item</th><th>Description</th><th>Unit</th>
          <th style="text-align:right;">Ordered</th><th style="text-align:right;">Sent</th>
          <th style="text-align:right;">Qty (Mtr)</th>
          <th style="text-align:right;">Qty (Nos)</th></tr></thead>
        <tbody>{body}
        </tbody>
      </table>
      </div>
    </div>
    """ + _PO_PICK_JS


def _po_picks(form, po: dict) -> tuple:
    """
    `(boq_payload_json, other_rows, posted_on, posted_qty, error)` off the
    order picker. A ticked BOQ line goes back through the ordinary picker (so
    it is exactly a BOQ challan's line); every other ticked line is an extra.
    """
    keys = form.getlist("pl_key")
    qtys = form.getlist("pl_qty")
    on = set(form.getlist("pl_on"))
    # The two columns (17 Nov 2026, §0 eighty-second block, dcqty.py). A POST
    # carrying only `pl_qty` (an older page) is placed by each line's unit.
    mtrs, noses = form.getlist("pl_qty_mtr"), form.getlist("pl_qty_nos")
    two = bool(mtrs or noses)
    by_key = {r["key"]: r for r in DCPO.lines_of(po)}
    if two:
        posted_qty = {k: {"mtr": mtrs[i] if i < len(mtrs) else "",
                          "nos": noses[i] if i < len(noses) else ""}
                      for i, k in enumerate(keys)}
    else:
        posted_qty = {}
        for i, k in enumerate(keys):
            raw = qtys[i] if i < len(qtys) else ""
            unit = (by_key.get(k) or {}).get("unit")
            posted_qty[k] = ({"mtr": raw, "nos": ""} if DQ.unit_class(unit) == "mtr"
                             else {"mtr": "", "nos": raw})
    boq_lines, others = [], []
    for k in keys:
        if k not in on or k not in by_key:
            continue
        r = by_key[k]
        pair = posted_qty.get(k) or {}
        mtr, nos, err = DQ.parse_pair(pair.get("mtr"), pair.get("nos"),
                                      r["description"][:60])
        if err:
            return "", [], on, posted_qty, err
        if r["kind"] == "boq":
            boq_lines.append({"line_id": r["line_id"],
                              "qty_mtr": "" if mtr is None else f"{mtr:g}",
                              "qty_nos": "" if nos is None else f"{nos:g}"})
        else:
            row = {"line_id": None, "extra": True, "is_header": False,
                   "item_no": r["item_no"], "description": r["description"][:500],
                   "unit": r["unit"][:30], "qty": 0.0, "source": "po", "po_key": k}
            others.append(DQ.stamp(row, mtr, nos))
    if not boq_lines and not others:
        return "", [], on, posted_qty, PO_NOTHING_TICKED
    return json.dumps({"lines": boq_lines}), others, on, posted_qty, ""


def over_po_remainder(dc: dict) -> list:
    """
    `[(description, sent_total, ordered)]` — the order's lines this challan
    took past what was ordered, counting every challan raised from it.
    Derived on every read; a warning, never a refusal.
    """
    pid = str((dc or {}).get("source_po_id") or "")
    po = (STORE.get("purchases") or {}).get(pid)
    if not po:
        return []
    mine = DCPO.qty_by_key(dc)
    sent = DCPO.dispatched_by_key(pid)
    return [(r["description"], sent.get(r["key"], 0.0), r["qty"])
            for r in DCPO.lines_of(po)
            if r["key"] in mine and sent.get(r["key"], 0.0) > r["qty"] + 1e-9]


def _over_po_band(dc: dict) -> str:
    """The amber band on `/dc/view` — screen only (the print never calls it)."""
    rows = over_po_remainder(dc)
    if not rows:
        return ""
    items = "".join(
        f"<li>{P.esc(' '.join(d.split())[:90])}: {BQ._fmt_qty(t)} dispatched "
        f"against {BQ._fmt_qty(o)} ordered</li>" for d, t, o in rows)
    return f"""
  <div class="dc-warn">
    <b>More has gone out than purchase order {P.esc(dc.get("source_po_ref"))}
    carries</b>, on {len(rows)} line{"" if len(rows) == 1 else "s"}. The
    challan stands &mdash; this is a warning, not a refusal.
    <ul>{items}</ul>
  </div>"""


def _keep_po_keys(items: list, before: list) -> list:
    """An edit rebuilds BOQ rows from the schedule; put each `po_key` back."""
    keys = {BQ._line_id(r.get("line_id")): r.get("po_key")
            for r in before or [] if r.get("po_key") and BQ._line_id(r.get("line_id"))}
    for r in items or []:
        lid = BQ._line_id(r.get("line_id"))
        if lid and lid in keys and not r.get("is_header"):
            r["po_key"] = keys[lid]
    return items


def _project_select_html(selected: str = "") -> str:
    """A no-BOQ challan's optional project — `extraitems.project_select_html()`."""
    return EX.project_select_html(selected)


# =============================================================================
# THE LINE PICKER — only the lines that were ticked
# =============================================================================

def picked_lines(raw: str, boq: dict) -> tuple:
    """
    Returns `(items, error)` — the BOQ lines that were **ticked**, snapshotted.

    The parsing is `boqpick.picked_lines()`, shared with the draft PO. Only the
    two refusals are this document's. No `Pcs` column: that is one variant of
    their purchase order (DOMAIN.md §5.2) and nothing on their challan.
    """
    return BP.picked_lines(
        raw, boq, with_pcs=False, max_lines=MAX_DC_LINES, two_qty=True,
        empty_msg=EMPTY_PICK_MSG,
        cap_msg="Raise more than one challan.")


def _posted_qty(posted: list) -> dict:
    """
    A rejected POST's boxes, handed back as typed: `{lid: {"mtr", "nos"}}` for
    a row that posted the two columns, else its one `qty` (placed by unit).
    """
    out = {}
    for r in posted or []:
        if not isinstance(r, dict):
            continue
        lid = BQ._line_id(r.get("line_id"))
        if "qty_mtr" in r or "qty_nos" in r:
            out[lid] = {"mtr": str(r.get("qty_mtr") or ""),
                        "nos": str(r.get("qty_nos") or "")}
        else:
            out[lid] = r.get("qty")
    return out


def _with_extras(boq_items, boq_err: str, extras: list) -> tuple:
    """
    BOQ lines first, then the extras — the order they print in. Ticking no BOQ
    line is allowed when there is an extra item: the challan still has a line.
    """
    if boq_err == EMPTY_PICK_MSG and extras:
        return list(extras), ""
    if boq_err:
        return [], boq_err
    return list(boq_items or []) + list(extras), ""


def _validate(form) -> tuple:
    """
    Returns `(data, error)`, and **always returns data** so a rejected form
    re-renders with what was typed — `address._validate()`'s contract.
    """
    data = {
        "date":             (form.get("date") or _date.today().isoformat()).strip()[:32],
        "dispatch_mode":    (form.get("dispatch_mode") or "").strip()[:120],
        "dispatch_to":      (form.get("dispatch_to") or "").strip()[:200],
        "po_no":            (form.get("po_no") or "").strip()[:64],
        "po_date":          (form.get("po_date") or "").strip()[:32],
        "consignee_id":     (form.get("consignee_id") or "").strip()[:64],
        "consignee_name":   (form.get("consignee_name") or "").strip()[:200],
        "consignee_addr":   (form.get("consignee_addr") or "").strip()[:500],
        "consignee_phone":  (form.get("consignee_phone") or "").strip()[:32],
        "notes":            (form.get("notes") or "").strip()[:2000],
        "dc_json":          form.get("dc_json") or "",
        # The typed document number, carried back like every other field
        # (27 October 2026). It is VALIDATED in `create_dc()`, not here: this
        # function serves the edit route too, and an edit never reissues the
        # number.
        "doc_no_seq":       (form.get("doc_no_seq") or "").strip()[:12],
    }
    if not data["date"]:
        return data, "A challan needs a date."

    consignee, err = consignee_from(form)
    if err:
        return data, err
    data["consignee"] = consignee
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
#
# ⚠ **This module has its OWN stylesheet and does not load `BOQ_STYLES`.**
#   `client.py` shipped loading the landscape BOQ print sheet and redefining
#   over it, which left two stylesheets fighting on one page. The picker's
#   rules are spliced in from `boqpick.PICKER_CSS` — one copy, shared with the
#   draft PO — and everything below is this module's own.

CHALLAN_STYLES = "\n<style>\n" + BP.PICKER_CSS + """
  /* The hint under a field. `settings.py` defines the same class in its own
     sheet; this page used it without one, so the hint rendered as body
     text. Same figures as there. */
  .fld-hint { font-size:.72rem; color:var(--muted); margin-top:.15rem; }
  /* The consignee pair. The free-text fields are the specified path and the
     picker is a prefill beside them, so the box says which is which rather
     than leaving the operator to guess. */
  .cn-or { text-align:center; font-size:.74rem; text-transform:uppercase;
           letter-spacing:.08em; color:var(--muted); margin:.6rem 0; }

  /* Over-dispatch. Amber, never red: this is a fact about the schedule, not a
     refusal, and the movement is allowed through. */
  .dc-warn { border:1px solid #E5B400; border-left:3px solid #E5B400;
             background:#FFFBEB; border-radius:var(--radius);
             padding:.8rem 1rem; margin-bottom:1.2rem; font-size:.85rem;
             line-height:1.6; color:#6B4E00; }
  .dc-warn b { color:#8A5A00; }
  .dc-warn ul { margin:.5rem 0 0 1.1rem; }
</style>
"""

DC_DOC_STYLES = "\n<style>\n" + DS.BAND_CSS + """
  /* Layered after the shared sheet, introducing no new font, type size or
     border weight — the restraint PROFORMA_STYLES, PURCHASE_STYLES and
     PO_DOC_STYLES all hold to. It adds only what this document has and no
     other does. */

  /* Their DC54 sets both header blocks as two equal columns rather than the
     42/29/29 of the shared party block: office against consignee, then challan
     meta against dispatch meta. */
  .quotation-doc .doc-header.dc-2col { grid-template-columns:50% 50%; }

  /* ⚠ HOTFIX 16 Nov 2026: the title band's own clear space. Since the 14 Nov
     logo move (option A) `branding.letterhead_top()` draws the banner with a
     margin-top of -11.21875px (the 44 px the mark rose), and its white canvas
     painted over the lower half of DELIVERY CHALLAN. The band keeps its 3px
     and gains exactly that rise, so the banner's top edge lands where the
     band ends. DC only: BAND_CSS (shared with the merged RA and the joint
     sheet) and the banner are untouched. One class more specific than
     BAND_CSS; the print-edge rule sets padding-TOP only. */
  .quotation-doc .page-frame > caption.sheet-band {
    padding-bottom:calc(3px + 11.21875px);
  }

  /* The receiver signs for the goods on arrival, so this sits on the LEFT of
     the signature panel where every other document prints GSTIN and PAN. No
     other document in this app is signed by the person receiving it. */
  .quotation-doc .dc-receiver { align-self:end; }
  .quotation-doc .dc-rec-rule {
    border-bottom:var(--rule); width:56mm; margin-bottom:2px;
  }
  .quotation-doc .dc-rec-lbl { font-weight:700; font-size:var(--fs-sm); }

  /* A note under the table, if one was typed. */
  .quotation-doc .dc-note { margin-top:4mm; font-size:var(--fs-sm); }
</style>
"""


# =============================================================================
# THE FORM
# =============================================================================

def _consignee_block_form(data: dict) -> str:
    """The free-text fields, with the address-book picker as a prefill."""
    opts = picker_options("Prefill from the address book",
                          only_types=CONSIGNEE_TYPES,  # None: the whole book
                          selected=data.get("consignee_id", ""))
    return f"""
      <div class="fg2">
        <div class="form-group">
          <label for="consignee_name">Consignee name</label>
          <input type="text" id="consignee_name" name="consignee_name"
                 value="{P.esc(data.get('consignee_name', ''))}"/>
          <div class="fld-hint">Usually us &mdash; the goods are going to our own
            site store, not to the party being billed.</div>
        </div>
        <div class="form-group">
          <label for="consignee_phone">Phone No.</label>
          <input type="text" id="consignee_phone" name="consignee_phone"
                 value="{P.esc(data.get('consignee_phone', ''))}"/>
        </div>
        <div class="form-group span2">
          <label for="consignee_addr">Consignee address</label>
          <textarea id="consignee_addr" name="consignee_addr" rows="3">{P.esc(data.get('consignee_addr', ''))}</textarea>
        </div>
      </div>
      <div class="cn-or">&mdash; or prefill from the address book &mdash;</div>
      <div class="form-group">
        <label for="consignee_id">Address book</label>
        <select id="consignee_id" name="consignee_id">{opts}</select>
        <div class="fld-hint">Optional. Fills anything you have left blank above,
          and is snapshotted onto the challan either way.</div>
      </div>"""


def _entry_form(boq: dict, data: dict, error: str = "",
                dc: dict = None, banner_html: str = "", held=None,
                po: dict = None) -> str:
    """
    The create form: the line picker, the consignee, and the dispatch fields.

    On edit (`dc` given) the picker is not shown at all. The lines on a challan
    are what left the yard, and a challan is signed for on arrival — moving the
    lines under a signed receipt is how a dispute starts. `/po/edit` makes the
    same call, and `purchase.update_purchase()` made it first.

    `banner_html` (18 October 2026) is Import from Excel's note — what was read
    and which sheet rows matched no line. It is the importer's own escaped
    markup, spliced under the alert; "" emits the form it always emitted.
    """
    # A no-BOQ challan (17 Nov 2026) has `boq` None: no picker, no import, a
    # project picker instead, and the extras section is its only lines.
    standalone = not boq
    boq = boq or {}
    boq_ref = P.esc(boq.get("ref") or "")
    editing = dc is not None
    # Import from Excel (18 October 2026). Drawn on the create form only, and
    # unconditionally: `docimport.upload_challan` carries `dc.create`, the
    # very permission this form is classified under, so whoever sees the form
    # can follow the button — `tests/test_doc_import.py` holds the two equal.
    # ⚠ **LINES ON EDIT from 2 November 2026** (CLIENT_CHANGES.md §0 block of
    #   that date, Part 2): the edit form is the create form — the picker
    #   prefilled with what the challan carries — UNLESS the challan is
    #   already billed on an RA bill (`held`), which is lock 3: its lines are
    #   the billed record. Excel imports onto the edit form too.
    lines_locked = editing and bool(held)
    # `po` (17 Nov 2026, §0 seventy-eighth block): raised FROM a purchase
    # order — the order's own lines replace the BOQ grid.
    from_po = po is not None
    import_btn = ("" if lines_locked or standalone or from_po else
                  f'\n      <a href="{url_for("docimport.upload_challan", boq=boq.get("id"), **({"dc": dc["id"]} if editing else {}))}" '
                  f'class="btn btn-ghost">&#128229; Import from Excel</a>')
    action = (url_for("challan.edit_dc", id=dc["id"]) if editing
              else url_for("challan.create_dc", po=po.get("id")) if from_po
              else url_for("challan.create_dc", noboq=1) if standalone
              else url_for("challan.create_dc", boq=boq.get("id")))
    back_url = (url_for("purchase.view_purchase", id=po.get("id")) if from_po
                else url_for("challan.list_dcs") if standalone
                else url_for("boq.view_boq", id=boq.get("id")))

    # ⚠ **The number is typeable on CREATE and nowhere else.** `edit_dc()`
    #   says in terms that `ref` is "deliberately untouched — an edit never
    #   reissues the number", and that rule is older than this field and is
    #   not being reopened: a challan is signed for on arrival and the paper
    #   carrying the number has already travelled with a load of material.
    #   §0's fifty-fourth block, item A point 2 — a challan has no unissued
    #   state to be editable in.
    if editing:
        # The number on EDIT (2 Nov 2026, Part 4): forward only — the challan
        # keeps its own number unless a higher one is typed; a number is never
        # reissued (the counter moves past it).
        dc_number_html = (
            f'<label for="doc_no_seq" style="display:block;font-size:.78rem;'
            f'text-transform:uppercase;letter-spacing:.04em;color:var(--muted);'
            f'margin-bottom:.3rem;">Challan No.</label>'
            + DN.number_field(DN.DC, str(dc.get("ref") or ""),
                              may_override=_may_set_number(),
                              typed=data.get("doc_no_seq", ""))
            + '<div class="dnum-note">Forward only &mdash; a number already '
              'used is never issued again.</div>'
            # Free format (17 Nov 2026, §0 eightieth block): wins when changed.
            + _free_box((request.form.get(TN.DOC_FIELD) if request.method == "POST"
                         else None) or str(dc.get("ref") or ""), creating=False))
    else:
        _default_seq, control = _number_control(data.get("doc_no_seq", ""),
                                                _may_set_number())
        dc_number_html = (
            f'<label for="doc_no_seq" style="display:block;font-size:.78rem;'
            f'text-transform:uppercase;letter-spacing:.04em;color:var(--muted);'
            f'margin-bottom:.3rem;">Challan No.</label>{control}'
            f'<div class="dnum-note">One running series, from '
            f'<a href="{url_for("settings.edit_settings")}">Settings</a>.</div>'
            + _free_box(request.form.get(TN.DOC_FIELD) or "" if request.method == "POST" else ""))

    picker = ""
    if lines_locked:
        bill = held[1] if isinstance(held, tuple) and len(held) > 1 else {}
        picker = (f'<div class="form-section"><div class="section-title">Lines</div>'
                  f'<p class="field-hint">These lines are <b>locked</b>: this challan is '
                  f'billed on RA{P.esc(bill.get("ra_no") or "")} and its lines are the '
                  f'billed record (lock 3). Every other field stays editable.</p></div>')
    elif from_po:
        picker = _po_picker_html(po, data)
    elif not standalone:
        picker = BP.grid_html(
            boq,
            title="Lines going out",
            intro_html="""        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line is ticked to start with. Untick what is not on this load,
          and change a quantity where less than the schedule is going.
          <b>No rates and no tax appear on a challan</b> &mdash; it is a record
          of goods moving, not a demand for money.
        </p>""",
            qty_label="Dispatch qty",
            qty_aria="Dispatch quantity",
            empty_note=("Nothing is ticked. A challan with no lines on it is "
                        "not a document."),
            payload_id="dc_json",
            doc_word="challan",
            chosen=data.get("_chosen"),
            qty_of=data.get("_qty"),
            with_pcs=False,
            two_qty=True)

    # Extra items — every challan, create and edit. Not drawn while the lines
    # are locked (billed): the stored extras then stay exactly as they are.
    extras_html = "" if lines_locked else _extras_section_html(
        [r for r in (dc or {}).get("items") or [] if is_extra(r)],
        data.get("_xposted"),
        # A challan raised from an order keeps each row's order line through
        # an edit (17 Nov 2026); every other challan renders as it always did.
        with_ref=bool((dc or {}).get("source_po_id")))
    if standalone:
        intro_html = ("<b>No BOQ</b> &middot; a standalone challan. Its lines are "
                      "the items below; it is never billed on an RA bill.")
        project_html = _project_select_html(data.get("project_id", ""))
    else:
        intro_html = (f'Against <b>{boq_ref}</b> &middot; {P.esc(boq.get("project_name") or "")}\n'
                      f'    &middot; {P.esc(boq.get("account_name") or "")}')
        project_html = ""
    if from_po:
        intro_html = (f'From purchase order <b>{P.esc(po.get("ref"))}</b> &middot; '
                      + (f'against <b>{boq_ref}</b> &middot; {P.esc(boq.get("project_name") or "")}'
                         if not standalone else
                         '<b>no BOQ</b> &middot; its lines are extra items and it is '
                         'never billed on an RA bill'))
    back_html = (f'\n      <a href="{back_url}" class="btn btn-ghost">&#8592; {P.esc(po.get("ref"))}</a>'
                 if from_po else "" if standalone else
                 f'\n      <a href="{back_url}" class="btn btn-ghost">&#8592; {boq_ref}</a>')

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Edit Delivery Challan" if editing else "Delivery Challan")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{CHALLAN_STYLES}{DN.NUMBER_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>{"Edit Delivery" if editing else "Delivery"} <span>Challan</span></h1>
    <div style="display:flex;gap:.7rem;">{import_btn}
      <a href="{url_for('challan.list_dcs')}" class="btn btn-ghost">All Challans</a>{back_html}
    </div>
  </div>

  {_alert(error)}{banner_html}

  <div class="set-intro" style="background:var(--surface);border:1px solid var(--border);
       border-left:3px solid var(--brand);border-radius:var(--radius);
       padding:.9rem 1.1rem;margin-bottom:1.2rem;font-size:.86rem;line-height:1.6;">
    {intro_html}<br/>
    {dc_number_html}
  </div>

  <form method="POST" action="{action}" onsubmit="return {"saveJSON()" if not (lines_locked or standalone or from_po) else "true"};">
    <input type="hidden" name="dc_json" id="dc_json" value=""/>

    <div class="form-section">
      <div class="section-title">Consignee &mdash; where the goods are going</div>
      {_consignee_block_form(data)}
    </div>

    <div class="form-section">
      <div class="section-title">Dispatch</div>
      <div class="fg2">
        <div class="form-group">
          <label for="date">Challan date</label>
          <input type="date" id="date" name="date" value="{P.esc(data.get('date', ''))}"/>
        </div>
        <div class="form-group">
          <label for="dispatch_mode">Dispatch mode</label>
          <input type="text" id="dispatch_mode" name="dispatch_mode"
                 value="{P.esc(data.get('dispatch_mode', ''))}"
                 placeholder="{DEFAULT_DISPATCH_MODE}"/>
        </div>
        <div class="form-group">
          <label for="dispatch_to">Dispatch to</label>
          <input type="text" id="dispatch_to" name="dispatch_to"
                 value="{P.esc(data.get('dispatch_to', ''))}"
                 placeholder="Where the transporter is taking it"/>
        </div>
        <div class="form-group">
          <label for="po_no">PO No.</label>
          <input type="text" id="po_no" name="po_no"
                 value="{P.esc(data.get('po_no', ''))}"/>
        </div>
        <div class="form-group">
          <label for="po_date">PO date</label>
          <input type="text" id="po_date" name="po_date"
                 value="{P.esc(data.get('po_date', ''))}"
                 placeholder="as written on their order"/>
        </div>
        <div class="form-group span2">
          <label for="notes">Notes</label>
          <textarea id="notes" name="notes" rows="2">{P.esc(data.get('notes', ''))}</textarea>
        </div>{project_html}
      </div>
    </div>

    {picker}
{extras_html}
    <div class="set-actions" style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise challan"}</button>
      <a href="{back_url}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
  {"" if editing else FD.script('form[action*="/dc/create"]', "delivery challan", resumed=request.method == "POST" and FD.is_resume(request.form))}

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challan</p></footer>
</main>
</body></html>""")


# =============================================================================
# THE DOCUMENT
# =============================================================================

# Five columns (four until 17 Nov 2026, their DC54) and nothing else. There is no
# Part No, no HSN, no Rate and no Amount, because none of them belongs on a
# goods-movement note. `docsheet.SELL_COLUMNS` is the eight-column set the sell
# and buy chains share; this is deliberately not it.
#
# ⚠ FIVE from 17 November 2026 (§0 eighty-second block, `dcqty.py`): their
#   paper DC 63 reads Sr.No | Description | Qty (Mtr) | Qty (Nos) | Unit. Both
#   quantity columns wear the sheet's own `c-qty` class, so they carry the old
#   Qty column's font, alignment and borders. The Unit column names the unit
#   of the SECOND column — "Nos" unless the line's unit is neither Mtr nor Nos.
DC_COLUMNS = (("c-sno", "Sr.No."), ("c-desc", "Description"),
              ("c-qty", DQ.MTR_LABEL), ("c-qty", DQ.NOS_LABEL), ("c-unit", "Unit"))


def _document_html(dc: dict, copy_label: str = None, screen: bool = False) -> str:
    """
    The printed delivery challan, on the shared A4 sheet.

    `copy_label` is one of `docsheet.COPIES_DC`, set by `/dc/print` once per
    copy and printed right-aligned in the title band (CGST Rule 55). `/dc/view`
    passes none and draws the sheet once, unlabelled. Presentation only: the
    label is never written to the challan.

    **Driven by the challan's own stored rows**, never re-read from the live
    BOQ — CLIENT_CHANGES.md §1.2. Every description, unit, quantity and
    consignee field on this page comes off `dc`. `print_ra()` was built as a
    loop over `boq["line_items"]` and a deleted BOQ line silently vanished from
    a printed document while its figure stayed inside the total; nothing here
    reads the BOQ at all, not even for a specification clause, because the
    clause text is snapshotted onto the challan at save.

    What it takes from the shared sheet: the page frame, the letterhead, the
    foot strip, the items-table shell, the signature panel and the print CSS.
    What it does not have, and none of these is an oversight:

    * **no GST block** and no tax of any kind (`PRINT_TAX`);
    * **no rate or amount column** (`PRINT_RATES`) — DOMAIN.md §5.1;
    * **no total and no amount in words** (`PRINT_TOTALS`) — there is nothing
      to total, and a zero would state that the material is free, which is the
      argument `/boq` makes for a missing base rate printing as `-`;
    * **no bank block.** `docsheet.bank_block()` is for the documents that ask
      for money. This one asks for a signature.

    The **seller identity is read from `branding`** at render time — the same
    module and the same read `print_ra()` uses, and the State is derived from
    the GSTIN rather than stored beside it. Two fields that must agree are two
    fields that can disagree. There is no fallback behind any of them: a blank
    prints an em dash, because a missing identity is a thing the operator must
    see and go fix at `/settings`.
    """
    rows = ""
    sno = 0
    for row in dc.get("items", []):
        if row.get("is_header"):
            rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td colspan="4" class="c-desc">{P.esc(row.get("description", ""))}</td>
        </tr>"""
            continue
        sno += 1
        # `/dc/view` ONLY (`screen`, 17 Nov 2026): a chip on an extra item.
        # `/dc/print` never passes it, so the printed sheet is byte-identical.
        chip = (' <span class="no-print" style="display:inline-block;font-size:.7rem;'
                'padding:0 .4rem;border:1px solid #E5B400;border-radius:999px;'
                'background:#FFFBEB;color:#6B4E00;white-space:nowrap;">'
                'Extra item, not billed</span>') if screen and is_extra(row) else ""
        # Blank cells where a column is empty; a line saved before 17 Nov
        # 2026 is read by its unit (`dcqty.cols()`).
        q_mtr, q_nos, unit_lbl = DQ.cols(row)
        rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-desc">{P.esc(row.get("description", ""))}{chip}</td>
          <td class="c-qty">{DQ.fmt(q_mtr)}</td>
          <td class="c-qty">{DQ.fmt(q_nos)}</td>
          <td class="c-unit">{P.esc(unit_lbl)}</td>
        </tr>"""

    # ── Our own identity, read and never written into this file ────────────
    # `tests/test_challan.py` greps this module and fails if a State name or a
    # GSTIN-shaped string reappears anywhere in it, including in a comment —
    # `tests/test_ra_seller_identity.py`'s rule, applied to the second document
    # that prints who we are.
    our_gstin = P.esc(B.COMPANY_GSTIN or "") or "&mdash;"
    our_state = P.esc(P.gstin_state_label(B.COMPANY_GSTIN)) or "&mdash;"
    our_addr = P.esc(B.COMPANY_ADDR or "") or "&mdash;"
    our_phone = P.esc(B.COMPANY_PHONE or "") or "&mdash;"

    office_cell = (
        '<span class="dh-lbl">Office Address</span>'
        f'<div class="dh-body">{our_addr}</div>'
        + DS._meta("Contact No.", our_phone)
        + DS._meta("GSTIN", our_gstin)
        + DS._meta("State", our_state))

    consignee_body = DS.name_block(
        "\n".join(x for x in [dc.get("consignee_name") or "",
                              dc.get("consignee_addr") or ""] if x.strip()))
    consignee_cell = (
        '<span class="dh-lbl">Consignee Details</span>'
        f'<div class="dh-body">{consignee_body}</div>'
        + DS._meta("Phone No.", P.esc(dc.get("consignee_phone"))))

    challan_cell = (
        DS._meta("Challan No.",   P.esc(dc.get("ref")))
        + DS._meta("Challan Date", P.esc(dc.get("date")))
        + DS._meta("Dispatch Mode", P.esc(dc.get("dispatch_mode"))))
    dispatch_cell = (
        DS._meta("PO No.",       P.esc(dc.get("po_no")))
        + DS._meta("PO Date",      P.esc(dc.get("po_date")))
        + DS._meta("Dispatch to",  P.esc(dc.get("dispatch_to"))))

    note_html = ""
    if dc.get("notes"):
        note_html = (f'\n  <div class="dc-note"><b>Notes:</b> '
                     f'{P.esc(dc["notes"])}</div>')

    # The receiver signs for the goods, so their line replaces the GSTIN/PAN
    # pair on the left of the signature panel. No other document here is signed
    # by the person receiving it.
    receiver_html = ('<div class="dc-receiver">'
                     '<div class="dc-rec-rule"></div>'
                     '<div class="dc-rec-lbl">Name &amp; Signature of Receiver</div>'
                     '</div>')

    return f"""
<div class="quotation-doc">

{DS.sheet_open(title_band="DELIVERY CHALLAN", copy_label=copy_label)}

  <div class="doc-box">
    <div class="doc-header dc-2col">
      <div class="dh-cell">{office_cell}</div>
      <div class="dh-cell">{consignee_cell}</div>
    </div>
    <div class="doc-header dc-2col">
      <div class="dh-cell">{challan_cell}</div>
      <div class="dh-cell">{dispatch_cell}</div>
    </div>

    <div class="doc-title">DESCRIPTION OF GOODS</div>

{DS.items_table(DC_COLUMNS, rows)}
  </div>{note_html}

{DS.sig_block(P.esc(dc.get("company_branch")), P.esc(dc.get("auth_signatory")),
              left_html=receiver_html)}

{DS.sheet_close()}

</div>"""


def _over_dispatch_band(dc: dict) -> str:
    """The amber band, naming the lines. A warning, and the movement stands."""
    rows = over_dispatched(dc)
    if not rows:
        return ""
    items = "".join(
        f"<li><b>{P.esc(item) or '&mdash;'}</b> &mdash; "
        f"{P.esc(' '.join(desc.split())[:90])}: "
        f"{BQ._fmt_qty(total)} dispatched against {BQ._fmt_qty(approved)} "
        f"in the schedule</li>"
        for item, desc, total, approved in rows)
    return f"""
  <div class="dc-warn">
    <b>More has now gone out than the schedule carries</b>, on
    {len(rows)} line{"" if len(rows) == 1 else "s"}. The challan stands &mdash;
    replacements, breakages, free issue and returns are ordinary on a site, and
    refusing the movement here would only push it onto paper this system never
    sees. Reconcile it against the schedule, or revise the BOQ.
    <ul>{items}</ul>
  </div>"""


# ── Billed — CLIENT_CHANGES.md §0, fortieth block, ruling C (4 Oct 2026) ─────
#
# ⚠ **Every rule below is drawn inline or from styles this page already
#   loads.** `CHALLAN_STYLES` is in the `<head>` of the pinned `/dc/` register
#   and `DC_DOC_STYLES` in the pinned `/dc/print`; a rule added to either would
#   move a page golden for a band neither pinned page draws.

def _billed_html(held) -> str:
    """
    `/dc/view`'s *Billed in <RA ref>* band, or nothing. `held` is
    `dcbill.billed_by()`'s answer — the one predicate — computed once by the
    caller. Screen only: `/dc/print` never draws it, and the challan record
    carries no mark of it.
    """
    if not held:
        return ""
    rid, bill = held
    return (
        '<div style="border:1px solid #bbf7d0;border-left:3px solid #15803d;'
        'background:#f0fdf4;border-radius:var(--radius);padding:.7rem 1rem;'
        'margin-bottom:1rem;font-size:.86rem;line-height:1.6;color:#14532d;">'
        f'&#10003; <b>Billed in <a href="{url_for("ra.view_ra", id=rid)}">'
        f'{P.esc(bill.get("ref")) or "&mdash;"}</a></b> '
        f'(RA{P.esc(bill.get("ra_no"))}). A challan is billed once, so it is not '
        f'offered for another RA bill while that one stands; cancelling the bill '
        f'frees it.</div>')


def _raise_ra_btn(dc_id: str, dc: dict, held) -> str:
    """
    *Raise RA (Supply)* — ruling A's way in, or nothing.

    Drawn only where it can lead somewhere: the challan is not billed, its
    schedule still exists, and the user holds what `/ra/create` requires —
    asked of `auth.can_reach()`, the dict the gate answers from, through a
    function-body import (`boq.view_boq()`'s hatch). ⚠ **Presentation, not the
    gate**: `/ra/create` classifies itself, and refuses a billed challan on the
    POST whatever this page drew.
    """
    if held or str(dc.get("boq_id") or "") not in (STORE.get("boqs") or {}):
        return ""
    # Extras only (17 Nov 2026): nothing on it an RA bill could claim.
    if not has_boq_lines(dc):
        return ""
    import auth as _AUTH
    if not _AUTH.can_reach("ra.create_ra"):
        return ""
    return (f'\n    <a href="{url_for("ra.create_ra", leg="supply", dc=dc_id)}" '
            f'class="btn btn-ghost">&#43;&nbsp;Raise RA (Supply)</a>')


def _billed_delete_note(dc_id: str) -> str:
    """
    The delete confirmation names the bill a billed challan is on. A WARNING,
    not a refusal — deleting a challan was never guarded and ruling C asks for
    no guard here — so the operator decides knowing that the bill will go on
    naming a challan that no longer exists. Its own figures do not move: every
    claim row is a snapshot.
    """
    held = DCB.billed_by(dc_id)
    if not held:
        return ""
    rid, bill = held
    return (f'\n    <p style="font-size:.85rem;color:#92400e;">&#9888; This challan '
            f'is billed in <a href="{url_for("ra.view_ra", id=rid)}">'
            f'{P.esc(bill.get("ref")) or "&mdash;"}</a> '
            f'(RA{P.esc(bill.get("ra_no"))}). Deleting it leaves that bill naming '
            f'a challan that no longer exists; the bill\'s own figures do not '
            f'change.</p>')


# =============================================================================
# ROUTES
# =============================================================================

@challan_bp.route("/")
def list_dcs():
    """The register — shaped like the BOQ, RA and draft-PO registers."""
    dcs = sorted((STORE.get("delivery_challans") or {}).items(),
                 key=lambda kv: (str(kv[1].get("date") or ""),
                                 str(kv[1].get("ref") or "")), reverse=True)
    # Ruling C (4 Oct 2026) — the one walk `dcbill.billed_by()` also reads,
    # taken once for the whole register. A challan nobody billed renders the
    # row it always rendered, byte for byte: this register is page-golden
    # pinned, and the mark is spliced in only where there is something to say.
    billed = DCB.billing_index()
    rows = ""
    for cid, dc in dcs:
        held = billed.get(cid)
        mark = (f'<div style="margin-top:.3rem;font-size:.74rem;">'
                f'<a class="reg-sub" href="{url_for("ra.view_ra", id=held[0])}" '
                f'title="A billed challan is not offered for another RA bill">'
                f'Billed in {P.esc(held[1].get("ref")) or "&mdash;"}</a></div>'
                ) if held else ""
        n = sum(1 for r in dc.get("items", []) if not r.get("is_header"))
        # A no-BOQ challan (17 Nov 2026) links to no schedule.
        boq_cell = (f'<a class="reg-sub reg-ref" href="{url_for("boq.view_boq", id=dc.get("boq_id"))}">'
                    f'{P.esc(dc.get("boq_ref"))}</a>' if dc.get("boq_id")
                    else '<span style="color:var(--muted);">No BOQ</span>')
        # ⚠ **THE PRIMARY ACTION, and it is the actual defect the owner
        #   reported: he could not tell what to click.** Their series has no
        #   prefix (ABOUT.md §5 `/dc`), so challan 54 rendered as the two
        #   characters `54` — a bare number, which reads as a reference rather
        #   than an action and is the smallest target this application offers.
        #   It carries a word and a border now, and `AGAINST BOQ` beside it is
        #   marked secondary so there is exactly one primary action per row.
        rows += f"""
        <tr>
          <td>
            <a class="reg-open" href="{url_for('challan.view_dc', id=cid)}"
               title="Open delivery challan {P.esc(dc.get("ref"))}">Open
              <span class="reg-ref">{P.esc(dc.get("ref"))}</span>
              <span class="ro-arrow">&rarr;</span></a>{mark}
          </td>
          <td>{P.esc(dc.get("date"))}</td>
          <td>{P.esc(dc.get("consignee_name")) or '&mdash;'}</td>
          <td>{P.esc(dc.get("dispatch_to")) or '&mdash;'}</td>
          <td>{boq_cell}</td>
          <td>{P.esc(dc.get("project_name")) or '&mdash;'}</td>
          <td class="num">{n}</td>
          <td class="reg-acts">
            <a class="reg-sub" href="{url_for('challan.print_dc', id=cid)}"
               title="The printed challan, on its own">&#128438;&nbsp;Print</a>
          </td>
        </tr>"""

    empty = ('<div class="reg-empty">No delivery challans yet. Raise one from '
             'a bill of quantities.</div>')

    # "New DC (no BOQ)" (17 Nov 2026, §0 seventy-fifth block) — beside the
    # BOQ entry, drawn only for a user `/dc/create` would admit.
    import auth as _AUTH
    new_btn = (f'\n      <a href="{url_for("challan.create_dc", noboq=1)}" '
               f'class="btn">&#43;&nbsp;New DC (no BOQ)</a>'
               # "DC from PO" (17 Nov 2026, §0 seventy-eighth block) — to the
               # purchase-order chooser, under the same permission.
               f'\n      <a href="{url_for("challan.create_dc", frompo=1)}" '
               f'class="btn">&#43;&nbsp;DC from PO</a>'
               if _AUTH.can_reach("challan.create_dc") else "")

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delivery Challans")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{REGISTER_STYLES}{CHALLAN_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Delivery <span>Challans</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">Bills of Quantities</a>{new_btn}
    </div>
  </div>

  {_flash()}

  <p style="font-size:.85rem;color:var(--muted);margin-bottom:1rem;">
    Goods leaving the yard &mdash; description, quantity and unit only, no
    rates and no tax. One running series across all sites; the next is
    <b>{P.esc(next_ref())}</b>, editable at
    <a href="{url_for('settings.edit_settings')}">Settings</a>.
  </p>

  <div class="reg-card">
    <div class="reg-head">
      <span class="reg-title">Delivery challans</span>
      <span class="reg-note">Newest first. Open one to see the note, its
        dispatch details and the over-dispatch band.</span>
    </div>
    {f'''<div class="reg-scroll">
    <table class="reg-table">
      <thead><tr>
        <th>Challan</th><th>Date</th><th>Consignee</th><th>Dispatch to</th>
        <th>Against BOQ</th><th>Project</th>
        <th class="num">Lines</th><th class="reg-acts">Actions</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>''' if rows else empty}
  </div>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challans</p></footer>
</main>
</body></html>""")


@challan_bp.route("/create", methods=["GET", "POST"])
def create_dc(imported: dict = None):
    """
    `imported` (18 October 2026) is the one seam Import from Excel renders this
    form through — `docimport.py` calls it on a GET with the schedule, the
    lines the sheet matched and their quantities. Flask never passes it, and
    the POST path never reads it: the save is the ordinary one, matched on
    `line_id` by `picked_lines()` exactly as a ticked line is.
    """
    boq_id = (imported or {}).get("boq_id") or request.args.get("boq") or ""
    # A challan with NO BOQ (17 Nov 2026, §0 seventy-fifth block): asked for
    # explicitly, so a stale or missing `?boq=` still refuses as it always did.
    if not boq_id and not imported and request.args.get("noboq"):
        return _create_standalone()
    # A challan FROM a purchase order (17 Nov 2026, §0 seventy-eighth block):
    # `?po=<id>` raises it, `?frompo=1` chooses the order. Same endpoint and
    # permission (`dc.create`), so no route and no grant moved.
    if not boq_id and not imported and request.args.get("po"):
        return _create_from_po(request.args.get("po"))
    if not boq_id and not imported and request.args.get("frompo"):
        return _po_chooser()
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="Choose a bill of quantities to despatch against.",
                                type="error"))
    # A superseded revision is not what anybody is building from, so it is not
    # what anybody should be despatching against. Refused at the route and not
    # only in the link, because a link is not a guard — `/ra/create` and
    # `/po/create` both make the same check on the same predicate.
    if boq_id in BQ.superseded_ids():
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg="That schedule has been superseded. Raise the "
                                    "challan against the current revision.",
                                type="error"))

    if request.method == "GET":
        data = {
            "date": _date.today().isoformat(),
            "dispatch_mode": DEFAULT_DISPATCH_MODE,
            # DC54 consigns to Samruddhi themselves. `COMPANY_LEGAL` is the
            # name `/settings` can edit; `COMPANY_NAME` is baked into the logo
            # artwork and is the fallback the rest of this app uses.
            "consignee_name": B.COMPANY_LEGAL or B.COMPANY_NAME,
        }
        if imported:
            # Only the lines the sheet matched arrive ticked, at the sheet's
            # quantity; everything else on the schedule is unticked.
            data["_chosen"] = set(imported.get("chosen") or ())
            data["_qty"] = dict(imported.get("qty") or {})
            return _entry_form(boq, data,
                               banner_html=imported.get("banner_html") or "")
        return _entry_form(boq, data)

    data, error = _validate(request.form)
    extras, x_error = parse_extras(request.form)
    items, line_error = ([], "") if error else _with_extras(
        *picked_lines(data["dc_json"], boq), extras)
    error = error or x_error or line_error

    # ⚠ **In the SAVE path, never on a GET** — §0's fifty-fourth block,
    #   item A point 9. `_spend_ref()` below is what moves the counter, and it
    #   is reached only past every refusal.
    may_number = _may_set_number()
    default_seq = int(SET.dc_series()["next_no"] or 1)
    # The free-format box (17 Nov 2026): when typed it IS the number and the
    # series box is not consulted.
    free, num_err = _free_number(request.form)
    seq_used = default_seq
    if not free and not num_err:
        seq_used, num_err = DN.validate(DN.DC, "", data["doc_no_seq"],
                                        default_seq, may_number)
    error = error or num_err
    # A Resume of an unsaved draft (formdraft.py, §0 sixty-fourth block, Part
    # 4) REDRAWS from what was typed: nothing above is enforced, nothing below
    # is saved, and no number is spent (`_spend_ref()` is past this return).
    resuming = FD.is_resume(request.form)

    if error or resuming:
        # Hand the operator back exactly what they ticked and typed.
        try:
            posted = (json.loads(data["dc_json"] or "{}").get("lines") or [])
        except (ValueError, TypeError):
            posted = []
        data["_chosen"] = {BQ._line_id(r.get("line_id")) for r in posted
                           if isinstance(r, dict)}
        data["_qty"] = _posted_qty(posted)
        data["_xposted"] = request.form
        return _entry_form(boq, data, "" if resuming else error)

    cid = new_id()
    default_ref = SET.dc_ref_of(SET.dc_series())
    STORE.setdefault("delivery_challans", {})[cid] = {
        "id": cid,
        "ref": _take_free(free) if free else _spend_ref(seq_used),
        "date": data["date"],
        # The BOQ this came from — a specific revision, exactly as an RA bill
        # and a draft PO name one. Both refs are STORED, not looked up, so the
        # document still reads as a historical record if the schedule is gone.
        "boq_id": boq_id,
        "boq_ref": boq.get("ref", ""),
        "boq_rev_no": boq.get("rev_no", 0),
        "project_name": boq.get("project_name", ""),
        "site_location": boq.get("site_location", ""),
        # Carried for the register only. It is the party being BILLED and is
        # never the consignee — see `consignee_from()`.
        "account_name": boq.get("account_name", ""),
        **data["consignee"],
        "dispatch_mode": data["dispatch_mode"],
        "dispatch_to": data["dispatch_to"],
        "po_no": data["po_no"],
        "po_date": data["po_date"],
        "notes": data["notes"],
        "items": items,
        "company_branch": "", "auth_signatory": "",
    }
    DN.record_override(STORE["delivery_challans"][cid], default_ref,
                       STORE["delivery_challans"][cid]["ref"], _actor_id())
    over = over_dispatched(STORE["delivery_challans"][cid])
    msg = "Delivery challan raised."
    if over:
        msg += (f" {len(over)} line{'' if len(over) == 1 else 's'} now exceed"
                f"{'s' if len(over) == 1 else ''} the schedule — see the note "
                f"on the challan.")
    return redirect(url_for("challan.view_dc", id=cid, msg=msg, type="success"))


def _create_standalone():
    """
    `/dc/create?noboq=1` — a challan with NO BOQ (17 Nov 2026, §0
    seventy-fifth block). The same form, the same consignee, dispatch and
    number rules, and the SAME series; its lines are extra items only, and it
    may name a project. `boq_id` is None, so no revision chain, no
    over-dispatch band and no RA bill ever reaches it.
    """
    if request.method == "GET":
        return _entry_form(None, {
            "date": _date.today().isoformat(),
            "dispatch_mode": DEFAULT_DISPATCH_MODE,
            "consignee_name": B.COMPANY_LEGAL or B.COMPANY_NAME,
        })

    data, error = _validate(request.form)
    link, link_error = project_link_from(request.form)
    extras, x_error = parse_extras(request.form)
    error = error or link_error or x_error
    if not error and not extras:
        error = ("A challan with nothing on it is not a document — add at "
                 "least one item that is going out.")
    may_number = _may_set_number()
    default_seq = int(SET.dc_series()["next_no"] or 1)
    # The free-format box (17 Nov 2026): when typed it IS the number and the
    # series box is not consulted.
    free, num_err = _free_number(request.form)
    seq_used = default_seq
    if not free and not num_err:
        seq_used, num_err = DN.validate(DN.DC, "", data["doc_no_seq"],
                                        default_seq, may_number)
    error = error or num_err
    resuming = FD.is_resume(request.form)
    if error or resuming:
        data["project_id"] = (request.form.get("project_id") or "").strip()[:64]
        data["_xposted"] = request.form
        return _entry_form(None, data, "" if resuming else error)

    cid = new_id()
    default_ref = SET.dc_ref_of(SET.dc_series())
    STORE.setdefault("delivery_challans", {})[cid] = {
        "id": cid,
        "ref": _take_free(free) if free else _spend_ref(seq_used),
        "date": data["date"],
        "boq_id": None,
        "boq_ref": "",
        **link,
        "site_location": "",
        "account_name": "",
        **data["consignee"],
        "dispatch_mode": data["dispatch_mode"],
        "dispatch_to": data["dispatch_to"],
        "po_no": data["po_no"],
        "po_date": data["po_date"],
        "notes": data["notes"],
        "items": extras,
        "company_branch": "", "auth_signatory": "",
    }
    DN.record_override(STORE["delivery_challans"][cid], default_ref,
                       STORE["delivery_challans"][cid]["ref"], _actor_id())
    return redirect(url_for("challan.view_dc", id=cid,
                            msg="Delivery challan raised.", type="success"))


def _po_chooser():
    """`/dc/create?frompo=1` — the purchase orders a challan can be raised from."""
    rows = ""
    pos = sorted((STORE.get("purchases") or {}).items(),
                 key=lambda kv: str(kv[1].get("ref") or ""), reverse=True)
    for pid, po in pos:
        if DCPO.is_withdrawn_po(po):
            continue
        lines = DCPO.lines_of(po)
        left = DCPO.remaining_by_key(po)
        open_n = sum(1 for r in lines if left.get(r["key"], 0.0) > 0)
        rows += f"""
        <tr>
          <td><b>{P.esc(po.get("ref"))}</b></td>
          <td>{P.esc(po.get("date"))}</td>
          <td>{P.esc(po.get("vendor_name")) or "&mdash;"}</td>
          <td>{P.esc(po.get("boq_ref")) or "No BOQ"}</td>
          <td>{P.esc(po.get("status"))}</td>
          <td style="text-align:right;">{open_n} of {len(lines)}</td>
          <td><a class="btn btn-ghost" href="{url_for('challan.create_dc', po=pid)}">Create DC</a></td>
        </tr>"""
    if not rows:
        rows = ('<tr><td colspan="7" style="text-align:center;color:var(--muted);'
                'padding:2rem;">No purchase order to despatch from.</td></tr>')
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("DC from PO")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{CHALLAN_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Challan from a <span>Purchase Order</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('challan.list_dcs')}" class="btn btn-ghost">All Challans</a>
    </div>
  </div>
  {_flash()}
  <p style="font-size:.85rem;color:var(--muted);margin-bottom:1rem;">
    Choose the order the goods are going out against. Cancelled orders are not
    listed. <i>Lines open</i> counts the order lines with quantity still to send.
  </p>
  <div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-size:.86rem;">
    <thead><tr style="text-align:left;font-size:.72rem;text-transform:uppercase;color:var(--muted);">
      <th>PO No.</th><th>Date</th><th>Supplier</th><th>BOQ</th><th>Status</th>
      <th style="text-align:right;">Lines open</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challan</p></footer>
</main>
</body></html>""")


def _create_from_po(po_id: str):
    """
    `/dc/create?po=<id>` — a challan raised FROM a purchase order (17 Nov 2026,
    §0 seventy-eighth block). The ordinary form, number, consignee, extras and
    series; its lines are the order's, at what is left of each.
    """
    po, err = _po_for_dc(po_id)
    if err:
        return redirect(url_for("challan.list_dcs", msg=err, type="error"))
    boq = DCPO.boq_of(po)
    standalone = not boq

    if request.method == "GET":
        return _entry_form(boq, {
            "date": _date.today().isoformat(),
            "dispatch_mode": DEFAULT_DISPATCH_MODE,
            # ⚠ NEVER the order's vendor: the goods go to our own site. The
            #   order's delivery address when it has one, else blank.
            "consignee_name": "",
            "consignee_addr": str(po.get("delivery_to") or "")[:500],
            "project_id": str(po.get("project_id") or "") if standalone else "",
        }, po=po)

    data, error = _validate(request.form)
    payload, others, on, posted_qty, pick_err = _po_picks(request.form, po)
    extras, x_error = parse_extras(request.form)
    link = {}
    if standalone:
        link, link_error = project_link_from(request.form)
        error = error or link_error
    error = error or pick_err or x_error
    items = []
    if not error:
        boq_items = []
        if boq and json.loads(payload).get("lines"):
            # The ordinary picker, so a BOQ line is exactly a BOQ challan's
            # line (its specification header comes with it).
            boq_items, error = picked_lines(payload, boq)
            for r in boq_items:
                if not r.get("is_header"):
                    r["po_key"] = f"L:{BQ._line_id(r.get('line_id'))}"
        items = list(boq_items) + list(others) + list(extras)
    may_number = _may_set_number()
    default_seq = int(SET.dc_series()["next_no"] or 1)
    # The free-format box (17 Nov 2026): when typed it IS the number and the
    # series box is not consulted.
    free, num_err = _free_number(request.form)
    seq_used = default_seq
    if not free and not num_err:
        seq_used, num_err = DN.validate(DN.DC, "", data["doc_no_seq"],
                                        default_seq, may_number)
    error = error or num_err
    resuming = FD.is_resume(request.form)
    if error or resuming:
        data["_po_on"] = on
        data["_po_qty"] = posted_qty
        data["_xposted"] = request.form
        data["project_id"] = (request.form.get("project_id") or "").strip()[:64]
        return _entry_form(boq, data, "" if resuming else error, po=po)

    cid = new_id()
    default_ref = SET.dc_ref_of(SET.dc_series())
    rec = {
        "id": cid,
        "ref": _take_free(free) if free else _spend_ref(seq_used),
        "date": data["date"],
        "boq_id": boq.get("id") if boq else None,
        "boq_ref": boq.get("ref", "") if boq else "",
        **({"boq_rev_no": boq.get("rev_no", 0),
            "project_name": boq.get("project_name", "")} if boq else link),
        "site_location": boq.get("site_location", "") if boq else "",
        "account_name": boq.get("account_name", "") if boq else "",
        # Where it came from. Stored, never looked up, like `boq_ref`.
        "source_po_id": po.get("id"),
        "source_po_ref": str(po.get("ref") or ""),
        **data["consignee"],
        "dispatch_mode": data["dispatch_mode"],
        "dispatch_to": data["dispatch_to"],
        "po_no": data["po_no"],
        "po_date": data["po_date"],
        "notes": data["notes"],
        "items": items,
        "company_branch": "", "auth_signatory": "",
    }
    STORE.setdefault("delivery_challans", {})[cid] = rec
    DN.record_override(rec, default_ref, rec["ref"], _actor_id())
    msg = f"Delivery challan raised from {rec['source_po_ref']}."
    over_po = over_po_remainder(rec)
    if over_po:
        msg += (f" {len(over_po)} line{'' if len(over_po) == 1 else 's'} now "
                f"exceed{'s' if len(over_po) == 1 else ''} the order — see the "
                f"note on the challan.")
    over = over_dispatched(rec) if boq else []
    if over:
        msg += (f" {len(over)} line{'' if len(over) == 1 else 's'} now exceed"
                f"{'s' if len(over) == 1 else ''} the schedule — see the note "
                f"on the challan.")
    return redirect(url_for("challan.view_dc", id=cid, msg=msg, type="success"))


@challan_bp.route("/view/<id>")
def view_dc(id: str):
    dc = (STORE.get("delivery_challans") or {}).get(id)
    if not dc:
        return redirect(url_for("challan.list_dcs",
                                msg="That challan no longer exists.", type="error"))

    # Read ONCE, and both the band and the button branch on it — so this page
    # cannot say "billed" and offer to bill it in the same breath.
    held = DCB.billed_by(id)
    boq_btn = (f'\n    <a href="{url_for("boq.view_boq", id=dc.get("boq_id"))}" '
               f'class="btn btn-ghost">{P.esc(dc.get("boq_ref"))}</a>'
               if dc.get("boq_id") else "")
    # The order it was raised from (17 Nov 2026) — screen only, and only when
    # that order is still there.
    if dc.get("source_po_id") in (STORE.get("purchases") or {}):
        # ⚠ The stored `source_po_ref` is a SNAPSHOT and is never rewritten.
        #   When the order has since been renumbered (17 Nov 2026), the button
        #   names its CURRENT number and the one this challan was raised against.
        now_ref = str(STORE["purchases"][dc["source_po_id"]].get("ref") or "")
        snap = str(dc.get("source_po_ref") or "")
        po_label = (f"PO {P.esc(now_ref)}" if now_ref == snap else
                    f"PO {P.esc(now_ref)} (raised as {P.esc(snap)})")
        boq_btn += (f'\n    <a href="{url_for("purchase.view_purchase", id=dc.get("source_po_id"))}" '
                    f'class="btn btn-ghost">{po_label}</a>')

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Challan " + str(dc.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{CHALLAN_STYLES}{DC_DOC_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Challan <span style="color:var(--brand);">{P.esc(dc.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('challan.list_dcs')}" class="btn btn-ghost">All Challans</a>{boq_btn}{_raise_ra_btn(id, dc, held)}
    <a href="{url_for('challan.edit_dc', id=id)}" class="btn btn-ghost">Edit</a>
    <a href="{url_for('challan.delete_dc', id=id)}" class="btn btn-ghost">Delete</a>
    <a href="{url_for('challan.print_dc', id=id)}" class="btn">&#128438;&nbsp;Print</a>
  </div>
</div>

{_flash()}{_billed_html(held)}
{_over_dispatch_band(dc)}{_over_po_band(dc)}{EL.band(dc, "delivery challan")}{TN.history_html(dc, "dc")}

<div class="doc-outer">
{_document_html(dc, screen=True)}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challan</p>
</footer>
</main>
</body></html>""")


@challan_bp.route("/print/<id>")
def print_dc(id: str):
    """
    The document alone behind a `.no-print` action bar — `/boq/print`'s shape.

    **Every copy by default** — `docsheet.COPIES_DC`, each on its own page, so
    one Ctrl+P prints the set Rule 55 asks for. `?copy=original|duplicate|
    triplicate` reprints one lost copy; anything else prints the set. Every
    copy is rendered from the same stored challan.
    """
    dc = (STORE.get("delivery_challans") or {}).get(id)
    if not dc:
        return redirect(url_for("challan.list_dcs",
                                msg="That challan no longer exists.", type="error"))

    choice = DS.copy_choice(request.args.get("copy"), DS.COPIES_DC)
    switch = DS.copy_toolbar(
        lambda k: url_for("challan.print_dc", id=id, copy=k), DS.COPIES_DC, choice)
    sheets = DS.copies(lambda label: _document_html(dc, copy_label=label),
                       DS.COPIES_DC, choice)

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(dc.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{DC_DOC_STYLES}{DS.COPY_STYLES}
</head>
<body>
<div class="screen-acts no-print">
  <a href="{url_for('challan.view_dc', id=id)}" class="btn btn-ghost">&#8592;&nbsp;Back</a>
  {switch}
  <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
</div>
<div class="doc-outer">
{sheets}
</div>
</body></html>""")


# The fields `edit_dc()` writes, as the edit log names them (31 Oct 2026).
DC_EDIT_FIELDS = (("date", "Challan date"), ("dispatch_mode", "Dispatch mode"),
                  ("dispatch_to", "Dispatch to"), ("po_no", "PO No."),
                  ("po_date", "PO date"), ("notes", "Note"),
                  ("consignee_name", "Consignee"), ("consignee_addr", "Consignee address"),
                  ("consignee_phone", "Consignee phone"), ("consignee_id", "Consignee (address book)"),
                  ("project_name", "Project"))


@challan_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_dc(id: str, imported: dict = None):
    """
    Every field — and, from 2 November 2026, the LINES and the NUMBER.

    ⚠ **Lines (CLIENT_CHANGES.md §0 block of 2 Nov 2026, Part 2, lock 3).** An
      UNBILLED challan's lines are edited on the same picker the create form
      draws — tick, untick, change a quantity — and Excel lands on it too
      (`imported`, the create seam's shape; Flask never passes it). A challan
      already billed on a live RA bill (`dcbill.billed_by()`, the ONE billed
      predicate) has its lines LOCKED, refused on the POST as well as hidden:
      they are what the bill claimed. *Until this date the lines were never
      editable: "a challan is signed for on arrival … moving the lines under a
      signed receipt is how a dispute starts."* Manas's ruling replaces that
      with lock 3; every change after issue is on the edit log.
    ⚠ **The number, forward only** (Part 4): its own number always passes; a
      higher one typed spends the series up to it (`_spend_ref()`), so no
      number is ever issued twice.
    """
    dc = (STORE.get("delivery_challans") or {}).get(id)
    if not dc:
        return redirect(url_for("challan.list_dcs",
                                msg="That challan no longer exists.", type="error"))
    # A no-BOQ challan (17 Nov 2026) edits with `boq` None — no picker.
    standalone = not dc.get("boq_id")
    boq = None if standalone else (STORE.get("boqs") or {}).get(dc.get("boq_id", "")) or {
        "id": dc.get("boq_id", ""), "ref": dc.get("boq_ref", ""),
        "project_name": dc.get("project_name", ""),
        "account_name": dc.get("account_name", ""), "line_items": [],
    }
    held = DCB.billed_by(id)

    def _current():
        return {
            "date": dc.get("date", ""),
            "dispatch_mode": dc.get("dispatch_mode", ""),
            "dispatch_to": dc.get("dispatch_to", ""),
            "po_no": dc.get("po_no", ""), "po_date": dc.get("po_date", ""),
            "notes": dc.get("notes", ""),
            "consignee_id": dc.get("consignee_id", ""),
            "consignee_name": dc.get("consignee_name", ""),
            "consignee_addr": dc.get("consignee_addr", ""),
            "consignee_phone": dc.get("consignee_phone", ""),
            "project_id": dc.get("project_id", ""),
            "_chosen": {BQ._line_id(r.get("line_id")) for r in dc.get("items") or []
                        if not r.get("is_header") and not is_extra(r)},
            # Both columns, as saved; a line from before 17 Nov 2026 by its unit.
            "_qty": {BQ._line_id(r.get("line_id")): DQ.replay(r)
                     for r in dc.get("items") or []
                     if not r.get("is_header") and not is_extra(r)},
        }

    if request.method == "GET":
        data = _current()
        if imported:
            data["_chosen"] = set(imported.get("chosen") or ())
            data["_qty"] = dict(imported.get("qty") or {})
        return _entry_form(boq, data, dc=dc, held=held,
                           banner_html=(imported or {}).get("banner_html") or "")

    data, error = _validate(request.form)
    items = None
    # Extra items (17 Nov 2026). Read only when the form drew the section
    # (`xi_present`) and the lines are not locked; otherwise the stored
    # extras are carried over untouched.
    stored_extras = [r for r in dc.get("items") or [] if is_extra(r)]
    stored_boq = [r for r in dc.get("items") or [] if not is_extra(r)]
    read_extras = not held and bool(request.form.get("xi_present"))
    # Raised from an order (17 Nov 2026): each row keeps its order line.
    po_keys = ({r["key"] for r in DCPO.lines_of(
                   (STORE.get("purchases") or {}).get(dc.get("source_po_id")) or {})}
               | {str(r.get("po_key")) for r in stored_extras if r.get("po_key")}
               if dc.get("source_po_id") else None)
    extras, x_error = (parse_extras(request.form, with_ref=po_keys is not None,
                                    allowed_refs=po_keys) if read_extras
                       else (stored_extras, ""))
    error = error or x_error
    link = {}
    if standalone and not error:
        link, error = project_link_from(request.form)
    if not error and not held:
        if standalone:
            items = list(extras) if read_extras else None
        elif data["dc_json"]:
            items, error = _with_extras(*picked_lines(data["dc_json"], boq), extras)
        elif read_extras:
            items = stored_boq + list(extras)
        if items is not None and not items:
            error = ("A challan with nothing on it is not a document — tick a "
                     "BOQ line or add an extra item.")
    own_seq = DN.ordinal_of(dc.get("ref"))
    seq_now = own_seq
    # The free-format box (17 Nov 2026): when it differs from the challan's
    # own number it wins, and the forward-only box is not consulted.
    ref_was = str(dc.get("ref") or "")
    free_now = ref_was
    if not error and TN.DOC_FIELD in request.form:
        free_now, error = _free_number(request.form, current=ref_was, rec_id=id,
                                       required=True)
    if not error and free_now == ref_was:
        seq_now, error = DN.validate(DN.DC, "", data["doc_no_seq"], own_seq,
                                     _may_set_number())
    if error:
        try:
            posted = (json.loads(data["dc_json"] or "{}").get("lines") or [])
        except (ValueError, TypeError):
            posted = []
        if posted:
            data["_chosen"] = {BQ._line_id(r.get("line_id")) for r in posted
                               if isinstance(r, dict)}
            data["_qty"] = _posted_qty(posted)
        else:
            data.update({k: v for k, v in _current().items() if k.startswith("_")})
        if read_extras:
            data["_xposted"] = request.form
        data["project_id"] = (request.form.get("project_id") or "").strip()[:64]
        return _entry_form(boq, data, error, dc=dc, held=held)

    # 31 Oct 2026, §0 sixty-fourth block, Part 2 — a challan is a SENT
    # document: every change is logged on it (`editlog`, who / when / field /
    # before → after) and `/dc/view` draws the screen-only band. `/dc/print`
    # carries none.
    import auth as _AUTH
    before = dict(dc)
    before_items = [dict(r) for r in dc.get("items") or []]
    for key in ("date", "dispatch_mode", "dispatch_to", "po_no", "po_date",
                "notes"):
        dc[key] = data[key]
    dc.update(data["consignee"])
    if standalone:
        dc.update(link)
    changes = EL.diff(before, dc, DC_EDIT_FIELDS)
    if items is not None:
        if dc.get("source_po_id"):
            _keep_po_keys(items, before_items)
        dc["items"] = items
        changes += EL.line_diff([dict(r, name=r.get("description"), price="")
                                 for r in before_items],
                                [dict(r, name=r.get("description"), price="")
                                 for r in items])
    if free_now != ref_was:
        dc["ref"] = _take_free(free_now)
        TN.record_change(dc, ref_was, free_now, _actor_id(), kind="dc")
        changes.append(("Challan No.", ref_was, dc["ref"]))
    elif seq_now != own_seq:
        dc["ref"] = _spend_ref(seq_now)
        DN.record_override(dc, ref_was, dc["ref"], _actor_id())
        TN.record_change(dc, ref_was, dc["ref"], _actor_id(), kind="dc")
        changes.append(("Challan No.", ref_was, dc["ref"]))
    EL.record(dc, changes, str((_AUTH.current_user() or {}).get("id") or ""))
    msg = "Delivery challan updated."
    over = over_dispatched(dc) if items is not None else []
    if over:
        msg += (f" {len(over)} line{'' if len(over) == 1 else 's'} now exceed"
                f"{'s' if len(over) == 1 else ''} the schedule — see the note "
                f"on the challan.")
    return redirect(url_for("challan.view_dc", id=id, msg=msg, type="success"))


@challan_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_dc(id: str):
    """
    GET renders the confirmation, POST destroys — ABOUT.md §7.9f's standing
    rule for any new delete route, and `tests/test_challan.py` ships the
    per-route GET test that rule also requires. The `url_map` sweep proves only
    that the rule accepts POST; it cannot catch a route that accepts both and
    destroys on GET.

    **Deleting does not release the number.** The series counter lives at
    `/settings` and only ever advances, so the next challan takes the next
    number and this one's is spent. It has travelled with a load of material.
    """
    dc = (STORE.get("delivery_challans") or {}).get(id)
    if not dc:
        return redirect(url_for("challan.list_dcs",
                                msg="That challan no longer exists.", type="error"))

    if request.method == "GET":
        return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delete Delivery Challan")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{CHALLAN_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top"><h1>Delete <span>{P.esc(dc.get('ref'))}</span></h1></div>
  <div class="card" style="border:1px solid var(--border);border-radius:10px;padding:1.2rem;">
    <p>Delete delivery challan <b>{P.esc(dc.get('ref'))}</b> consigned to
       <b>{P.esc(dc.get('consignee_name')) or 'an unnamed consignee'}</b>, raised
       {('against ' + P.esc(dc.get('boq_ref'))) if dc.get('boq_id') else 'without a BOQ'}?</p>
    <p style="font-size:.85rem;color:var(--muted);">
      This cannot be undone. <b>The number is not released</b> &mdash; the next
      challan takes the next one in the series, because {P.esc(dc.get('ref'))}
      may already have travelled with a load of material.
    </p>{_billed_delete_note(id)}
    <form method="POST" style="display:flex;gap:.75rem;margin-top:1rem;">
      <button type="submit" class="btn">Delete it</button>
      <a href="{url_for('challan.view_dc', id=id)}" class="btn btn-ghost">Cancel</a>
    </form>
  </div>
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challan</p></footer>
</main>
</body></html>""")

    boq_id = dc.get("boq_id", "")
    ref = dc.get("ref", "")
    STORE["delivery_challans"].pop(id, None)
    if not boq_id:   # a no-BOQ challan (17 Nov 2026) goes back to the register
        return redirect(url_for("challan.list_dcs",
                                msg=f"Challan {ref} deleted. Its number is not reissued.",
                                type="success"))
    return redirect(url_for("boq.view_boq", id=boq_id,
                            msg=f"Challan {ref} deleted. Its number is not reissued.",
                            type="success"))
