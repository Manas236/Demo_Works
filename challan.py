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
import branding as B
import docsheet as DS
import pipeline as P
import settings as SET
from address import picker_options, format_address_lines
from dashboard import BASE_STYLES, REGISTER_STYLES, _nav
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


def _spend_ref() -> str:
    """Take the next number and advance the counter. Call once, at save."""
    series = SET.dc_series()
    ref = SET.dc_ref_of(series)
    SET.save_dc_series(series["prefix"], int(series["next_no"] or 1) + 1)
    return ref


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
            out[lid] = out.get(lid, 0.0) + float(row.get("qty") or 0.0)
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
        total = others.get(lid, 0.0) + float(row.get("qty") or 0.0)
        # Rounded at 1e-6 for `ra.py`'s reason: 1.1 + 2.2 + 8.7 is
        # 12.000000000000002, and that is not an over-dispatch of two
        # femtometres against an approved 12.
        if total - approved[lid] > 1e-6:
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
        raw, boq, with_pcs=False, max_lines=MAX_DC_LINES,
        empty_msg=("No lines are ticked. A challan with nothing on it is not a "
                   "document — tick what is going out, or cancel."),
        cap_msg="Raise more than one challan.")


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
                dc: dict = None) -> str:
    """
    The create form: the line picker, the consignee, and the dispatch fields.

    On edit (`dc` given) the picker is not shown at all. The lines on a challan
    are what left the yard, and a challan is signed for on arrival — moving the
    lines under a signed receipt is how a dispute starts. `/po/edit` makes the
    same call, and `purchase.update_purchase()` made it first.
    """
    boq_ref = P.esc(boq.get("ref") or "")
    editing = dc is not None
    action = (url_for("challan.edit_dc", id=dc["id"]) if editing
              else url_for("challan.create_dc", boq=boq.get("id")))

    picker = ""
    if not editing:
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
            with_pcs=False)

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Edit Delivery Challan" if editing else "Delivery Challan")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{CHALLAN_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>{"Edit Delivery" if editing else "Delivery"} <span>Challan</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('challan.list_dcs')}" class="btn btn-ghost">All Challans</a>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">&#8592; {boq_ref}</a>
    </div>
  </div>

  {_alert(error)}

  <div class="set-intro" style="background:var(--surface);border:1px solid var(--border);
       border-left:3px solid var(--brand);border-radius:var(--radius);
       padding:.9rem 1.1rem;margin-bottom:1.2rem;font-size:.86rem;line-height:1.6;">
    Against <b>{boq_ref}</b> &middot; {P.esc(boq.get("project_name") or "")}
    &middot; {P.esc(boq.get("account_name") or "")}<br/>
    This challan will be numbered <b>{P.esc(next_ref()) if not editing else P.esc(dc.get("ref"))}</b>
    from the one running series at <a href="{url_for('settings.edit_settings')}">Settings</a>.
  </div>

  <form method="POST" action="{action}" onsubmit="return {"saveJSON()" if not editing else "true"};">
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
        </div>
      </div>
    </div>

    {picker}

    <div class="set-actions" style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise challan"}</button>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challan</p></footer>
</main>
</body></html>""")


# =============================================================================
# THE DOCUMENT
# =============================================================================

# Four columns, and nothing else — their DC54's table exactly. There is no
# Part No, no HSN, no Rate and no Amount, because none of them belongs on a
# goods-movement note. `docsheet.SELL_COLUMNS` is the eight-column set the sell
# and buy chains share; this is deliberately not it.
DC_COLUMNS = (("c-sno", "Sr.No."), ("c-desc", "Description"),
              ("c-qty", "Qty"), ("c-unit", "Unit"))


def _document_html(dc: dict) -> str:
    """
    The printed delivery challan, on the shared A4 sheet.

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
          <td colspan="3" class="c-desc">{P.esc(row.get("description", ""))}</td>
        </tr>"""
            continue
        sno += 1
        rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-desc">{P.esc(row.get("description", ""))}</td>
          <td class="c-qty">{BQ._fmt_qty(row.get("qty") or 0)}</td>
          <td class="c-unit">{P.esc(row.get("unit", ""))}</td>
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

{DS.sheet_open(title_band="DELIVERY CHALLAN")}

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


# =============================================================================
# ROUTES
# =============================================================================

@challan_bp.route("/")
def list_dcs():
    """The register — shaped like the BOQ, RA and draft-PO registers."""
    dcs = sorted((STORE.get("delivery_challans") or {}).items(),
                 key=lambda kv: (str(kv[1].get("date") or ""),
                                 str(kv[1].get("ref") or "")), reverse=True)
    rows = ""
    for cid, dc in dcs:
        n = sum(1 for r in dc.get("items", []) if not r.get("is_header"))
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
              <span class="ro-arrow">&rarr;</span></a>
          </td>
          <td>{P.esc(dc.get("date"))}</td>
          <td>{P.esc(dc.get("consignee_name")) or '&mdash;'}</td>
          <td>{P.esc(dc.get("dispatch_to")) or '&mdash;'}</td>
          <td><a class="reg-sub reg-ref" href="{url_for('boq.view_boq', id=dc.get('boq_id', ''))}">{P.esc(dc.get("boq_ref"))}</a></td>
          <td>{P.esc(dc.get("project_name")) or '&mdash;'}</td>
          <td class="num">{n}</td>
          <td class="reg-acts">
            <a class="reg-sub" href="{url_for('challan.print_dc', id=cid)}"
               title="The printed challan, on its own">&#128438;&nbsp;Print</a>
          </td>
        </tr>"""

    empty = ('<div class="reg-empty">No delivery challans yet. Raise one from '
             'a bill of quantities.</div>')

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
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">Bills of Quantities</a>
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
def create_dc():
    boq_id = request.args.get("boq") or ""
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
        return _entry_form(boq, {
            "date": _date.today().isoformat(),
            "dispatch_mode": DEFAULT_DISPATCH_MODE,
            # DC54 consigns to Samruddhi themselves. `COMPANY_LEGAL` is the
            # name `/settings` can edit; `COMPANY_NAME` is baked into the logo
            # artwork and is the fallback the rest of this app uses.
            "consignee_name": B.COMPANY_LEGAL or B.COMPANY_NAME,
        })

    data, error = _validate(request.form)
    items, line_error = ([], "") if error else picked_lines(data["dc_json"], boq)
    error = error or line_error
    if error:
        # Hand the operator back exactly what they ticked and typed.
        try:
            posted = (json.loads(data["dc_json"] or "{}").get("lines") or [])
        except (ValueError, TypeError):
            posted = []
        data["_chosen"] = {BQ._line_id(r.get("line_id")) for r in posted
                           if isinstance(r, dict)}
        data["_qty"] = {BQ._line_id(r.get("line_id")): r.get("qty")
                        for r in posted if isinstance(r, dict)}
        return _entry_form(boq, data, error)

    cid = new_id()
    STORE.setdefault("delivery_challans", {})[cid] = {
        "id": cid,
        "ref": _spend_ref(),
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
    over = over_dispatched(STORE["delivery_challans"][cid])
    msg = "Delivery challan raised."
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
    <a href="{url_for('challan.list_dcs')}" class="btn btn-ghost">All Challans</a>
    <a href="{url_for('boq.view_boq', id=dc.get('boq_id', ''))}" class="btn btn-ghost">{P.esc(dc.get('boq_ref'))}</a>
    <a href="{url_for('challan.edit_dc', id=id)}" class="btn btn-ghost">Edit</a>
    <a href="{url_for('challan.delete_dc', id=id)}" class="btn btn-ghost">Delete</a>
    <a href="{url_for('challan.print_dc', id=id)}" class="btn">&#128438;&nbsp;Print</a>
  </div>
</div>

{_flash()}
{_over_dispatch_band(dc)}

<div class="doc-outer">
{_document_html(dc)}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · delivery challan</p>
</footer>
</main>
</body></html>""")


@challan_bp.route("/print/<id>")
def print_dc(id: str):
    """The document alone behind a `.no-print` action bar — `/boq/print`'s shape."""
    dc = (STORE.get("delivery_challans") or {}).get(id)
    if not dc:
        return redirect(url_for("challan.list_dcs",
                                msg="That challan no longer exists.", type="error"))

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(dc.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{DC_DOC_STYLES}
</head>
<body>
<div class="screen-acts no-print">
  <a href="{url_for('challan.view_dc', id=id)}" class="btn btn-ghost">&#8592;&nbsp;Back</a>
  <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
</div>
<div class="doc-outer">
{_document_html(dc)}
</div>
</body></html>""")


@challan_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_dc(id: str):
    """
    Consignee and dispatch fields. **Not the lines.**

    A challan is signed for on arrival, and the lines on it are what left the
    yard. Editing them behind a signature is how a dispute starts — `/po/edit`
    makes the same call and `purchase.update_purchase()` made it first. Moving
    different material means raising another challan, which is cheap and leaves
    a trail.
    """
    dc = (STORE.get("delivery_challans") or {}).get(id)
    if not dc:
        return redirect(url_for("challan.list_dcs",
                                msg="That challan no longer exists.", type="error"))
    boq = (STORE.get("boqs") or {}).get(dc.get("boq_id", "")) or {
        "id": dc.get("boq_id", ""), "ref": dc.get("boq_ref", ""),
        "project_name": dc.get("project_name", ""),
        "account_name": dc.get("account_name", ""), "line_items": [],
    }

    if request.method == "GET":
        return _entry_form(boq, {
            "date": dc.get("date", ""),
            "dispatch_mode": dc.get("dispatch_mode", ""),
            "dispatch_to": dc.get("dispatch_to", ""),
            "po_no": dc.get("po_no", ""), "po_date": dc.get("po_date", ""),
            "notes": dc.get("notes", ""),
            "consignee_id": dc.get("consignee_id", ""),
            "consignee_name": dc.get("consignee_name", ""),
            "consignee_addr": dc.get("consignee_addr", ""),
            "consignee_phone": dc.get("consignee_phone", ""),
        }, dc=dc)

    data, error = _validate(request.form)
    if error:
        return _entry_form(boq, data, error, dc=dc)

    for key in ("date", "dispatch_mode", "dispatch_to", "po_no", "po_date",
                "notes"):
        dc[key] = data[key]
    dc.update(data["consignee"])
    # `ref` and `items` are deliberately untouched. An edit never reissues the
    # number and never moves what went out.
    return redirect(url_for("challan.view_dc", id=id,
                            msg="Delivery challan updated.", type="success"))


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
       against {P.esc(dc.get('boq_ref'))}?</p>
    <p style="font-size:.85rem;color:var(--muted);">
      This cannot be undone. <b>The number is not released</b> &mdash; the next
      challan takes the next one in the series, because {P.esc(dc.get('ref'))}
      may already have travelled with a load of material.
    </p>
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
    return redirect(url_for("boq.view_boq", id=boq_id,
                            msg=f"Challan {ref} deleted. Its number is not reissued.",
                            type="success"))
