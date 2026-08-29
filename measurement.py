"""
measurement.py — the measurement sheet raised from a BOQ
========================================================
Blueprint  : measurement_bp
Mounted at : /measurement  (registered in app.py)

CLIENT_CHANGES-2.md **C2**, built 29 August 2026 under the FIFTH override block
of that date. Before that block C2 was gated and nothing here existed.

⚠ WHAT CC-2 ACTUALLY SAYS — read this before changing anything below
--------------------------------------------------------------------
C2, **in full**, is three lines:

    ### C2 — measurement document

    Raised from the BOQ. Approved measurements become the source of
    installation quantity on RA-Installation.

That is the entire specification. **Almost everything in this module is
therefore OURS, and the override block lists each piece by name so nobody later
cites one as delivered CC-2 scope:**

| what | CC-2 says | who decided it |
|---|---|---|
| raised from the BOQ | yes, in those words | CC-2 |
| an approved measurement feeds RA-Installation | yes, in those words | CC-2 |
| a measured quantity may not exceed the BOQ quantity | **nothing** | ours |
| cumulative claims may not exceed the approved measured quantity | **nothing** | ours (it is how "becomes the source" is made true) |
| which ladder a measurement climbs | **nothing** — B6 names ladders for charges and for RA / Tax Invoice / PO, and names measurement on neither | ours: the RA ladder |
| that it prints at all, and what the sheet looks like | **nothing** | ours; no golden is pinned and no letterhead was invented |
| that the measured quantity is cumulative across sheets | **nothing** | ours — see `overmeasures()` |

None of that makes the work wrong. A measurement document without the two
guards is a form that records a number nobody checks. It makes the work
**unspecced**, which is a commercial fact and is recorded as one.

The chain this closes  (CC-2 **C1**)
------------------------------------
```
BoQ ──► Delivery Challan ──► RA-Supply          goods, proven by a challan
BoQ ──► Measurement      ──► RA-Installation    work, proven by a measurement
```

Before this module, installation quantity was typed straight into the claim
grid with nothing behind it — CC-2's own sentence. `ra.py` now reads the
approved measured quantity as the ceiling for the installation leg, and
`/ra/create?leg=installation` refuses a BOQ with no approved measurement on it.

Routes
------
  GET       /measurement/               — the register
  GET,POST  /measurement/create?boq=    — pick the lines, enter measured qty
  GET       /measurement/view/<id>      — the sheet, with the approval panel
  GET       /measurement/print/<id>     — the sheet alone, ready for Ctrl+P
  GET,POST  /measurement/edit/<id>      — the measured quantities, before approval
  GET,POST  /measurement/delete/<id>    — GET confirms, POST deletes

The two guards
--------------
1. **`overmeasures()`** — a measured quantity may not push the line past the
   BOQ quantity. A **hard block**, unlike `challan.over_dispatched()` which only
   warns: a challan records goods that have physically moved and blocking it
   would push people to write challans outside the system, whereas a
   measurement is the number a claim will be built from and an inflated one is
   the first half of an over-claim.

2. **`approved_qty_by_line()`** — read by `ra.overclaims()`, which lowers the
   installation leg's ceiling from the BOQ quantity to the approved measured
   quantity. The cumulative arithmetic is **not** reimplemented here;
   `ra.claimed_by_line()` stays the single place anything asks how much has been
   claimed, and this module only supplies the ceiling it is compared against.

Both guards are cumulative across the **revision chain**, exactly as
`ra.claimed_by_line()` and `challan.dispatched_by_line()` are, and for the same
reason: a revision is a new record, so a per-record sum would silently report
nil measured the moment a schedule was revised.

Its OWN collection
------------------
`STORE["measurements"]`, keyed by UUID, pointing at the BOQ revision it was
raised against — CLIENT_CHANGES.md §1.3's rule, the same one that gives
receipts and challans their own collections. One BOQ accumulates many
measurement sheets over a project's life; a list on the BOQ would make the
schedule record grow without bound and would lose them on revision.

Import direction
----------------
```
measurement.py ──► boq.py       _line_id / _item_no / _fmt_qty / MAX_LINES
measurement.py ──► boqpick.py   the shared line picker, at its FOURTH consumer
measurement.py ──► docsheet.py  the shared A4 sheet — NOTHING new was drawn
measurement.py ──► approval.py  the ladder (B6)
measurement.py ──► dashboard/pipeline/store/branding
```

⚠ **This module must never import `ra.py`.** `ra.py` imports *this* one, for
`approved_qty_by_line()` — that arrow is CC-2's own sentence ("approved
measurements become the source of installation quantity on RA-Installation")
and it runs one way. Importing back is a cycle, and it is refused at AST level
in `tests/test_import_directions.py` rather than left to this comment.

⚠ **And it must never import `challan.py`.** C1's supply leg is a separate
question answered in `ra.py` by reading `STORE["delivery_challans"]` directly —
the one-way trick. A measurement has nothing to say about goods movement.
"""

import json
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import approval
import boq as BQ
import boqpick as BP
import branding as B
import docsheet as DS
import pipeline as P
from dashboard import BASE_STYLES, _nav
from store import STORE

# ⚠ **`QUOTATION_STYLES` is read through `docsheet`, not imported from
#   `quotation.py`** — `challan.py`'s arrangement, used a third time. Every form
#   in this app is built out of that sheet's `.form-section` / `.fg2` widgets,
#   and re-declaring them here would be a second design system.
QUOTATION_STYLES = DS.QUOTATION_STYLES

measurement_bp = Blueprint("measurement", __name__, url_prefix="/measurement")


# =============================================================================
# BUSINESS RULES — module-level constants, never buried in a branch
# =============================================================================

# ⚠ **Over-measurement BLOCKS, and that is the opposite of the challan.**
#   `challan.BLOCK_OVER_DISPATCH` is False because a delivery challan records
#   goods that have physically left the yard, and refusing to record a real
#   movement pushes people to write challans outside the system. A measurement
#   is not a record of something that happened — it is the number the next
#   claim will be built from, so an inflated one is the first half of an
#   over-claim rather than an awkward fact about a site. `ra.overclaims()` is
#   the precedent this follows, not the challan.
#
# ⚠ **This rule is OURS.** CC-2's C2 says nothing about a ceiling of any kind.
BLOCK_OVER_MEASUREMENT = True

# No money of any kind reaches this document. Named constants rather than an
# absence, for `challan.py`'s reason: a measurement sheet is signed in the field
# by a site engineer, and a rate on it turns a measurement into a claim.
PRINT_RATES = False
PRINT_TAX = False
PRINT_TOTALS = False

# The line cap, derived from `boq.MAX_LINES` rather than chosen — the form
# renders every line of the BOQ, so a schedule legal at 600 lines must post a
# measurement legal at 600 lines. `challan.MAX_DC_LINES` and `ra.MAX_RA_LINES`
# are both derived the same way.
MAX_MS_LINES = BQ.MAX_LINES

# The document series. FY-scoped and max+1 within the year, sharing
# `pipeline.fy_of` / `fy_ref` with the BOQ, the RA bill, the PO and the tax
# invoice.
#
# ⚠ **Deliberately NOT a `/settings` series.** The delivery challan has one
#   because the client runs a single paper challan book and DC54 is a bare `54`
#   from it. Nothing we hold says a measurement sheet is numbered from a book
#   the client keeps, so inventing an editable series would be inventing a
#   business practice. If their site records turn out to carry one, this is the
#   one place it changes.
_REF_SERIES = "MS"

# No 16-character cap. That is Rule 46(b)'s limit on a TAX INVOICE number, and
# a measurement sheet is emphatically not one — it carries no money at all.
_REF_CAP = 64

# Quantity comparisons round here before they are called a breach. 1.1 + 2.2 +
# 8.7 is 12.000000000000002, and that is not an over-measurement of two
# femtometres against an approved 12. `ra._QTY_EPSILON` and
# `challan.over_dispatched()` both use the same figure.
_QTY_EPSILON = 1e-6


def new_id() -> str:
    return str(uuid.uuid4())


def _esc(v) -> str:
    return P.esc(v)


def records() -> dict:
    """The collection, created on first use."""
    return STORE.setdefault("measurements", {})


# =============================================================================
# NUMBERING
# =============================================================================

def next_ref(datestr: str = "") -> str:
    """
    Next measurement number — 'SF/MS/26-27/0004'.

    max+1 within the financial year rather than `len+1`, which is
    `proforma._next_ref()`'s rule and `ra.next_ref()`'s: a gap must never
    re-issue a number that has already been on a sheet somebody signed.
    """
    fy = P.fy_of(datestr or _date.today().isoformat())
    highest = 0
    for m in records().values():
        if m.get("fy") != fy:
            continue
        tail = str(m.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=_REF_CAP)


# =============================================================================
# READING THE CHAIN
# =============================================================================

def sheets_of_boq(boq_id: str) -> list:
    """`[(id, sheet)]` raised against this specific BOQ revision, newest first."""
    rows = [(mid, m) for mid, m in records().items()
            if str(m.get("boq_id") or "") == str(boq_id or "")]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""),
                              str(kv[1].get("ref") or "")), reverse=True)
    return rows


def sheets_on_chain(boq_id: str) -> list:
    """
    `[(id, sheet)]` raised anywhere on this BOQ's revision chain, newest first.

    **Chain-scoped, not record-scoped**, for `ra.claimed_by_line()`'s reason: a
    revision is a new BOQ record, so a per-record answer would report nil
    measured the moment a schedule was revised — silently, and only on the
    projects that have been revised.

    `boq._ancestor_ids()` walks backward from here, which is
    `challan.dispatched_by_line()`'s choice and is right for the same reason: a
    measurement is always raised against the tip, so backward is the whole
    chain from wherever it was raised.
    """
    chain = BQ._ancestor_ids(boq_id) if boq_id else set()
    rows = [(mid, m) for mid, m in records().items()
            if str(m.get("boq_id") or "") in chain]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""),
                              str(kv[1].get("ref") or "")), reverse=True)
    return rows


def measured_by_line(boq_id: str, exclude_id: str = "",
                     approved_only: bool = False) -> dict:
    """
    `{line_id: qty}` measured against this BOQ's revision chain.

    **Derived on every read and never stored**, exactly as
    `ra.claimed_by_line()` and `challan.dispatched_by_line()` are. A maintained
    counter has to be updated on every create, revision and delete, and a path
    that misses one leaves the figure silently wrong — which is worse than no
    figure, because it is trusted. This number *is* a guard, twice over.

    `approved_only` is the difference between the two guards:

    * **False** — every live sheet counts, whatever rung it stands on. This is
      what `overmeasures()` asks, and a pending sheet has to count for the same
      reason `ra.claimed_by_line()` counts a draft bill: two sheets each
      measuring the whole of a line would otherwise both pass, and the second
      would only be caught after the first was approved.
    * **True** — only fully approved sheets count. This is what
      `ra.overclaims()` asks, and it is CC-2's own word: *"**Approved**
      measurements become the source of installation quantity."*

    **A REJECTED sheet counts in neither.** It has been refused, so its figures
    are not committed against the schedule and not available to a claim. That is
    `approval.py`'s `rejected` state doing the same job `ra.is_cancelled()` does
    one document over — a withdrawn number releases the quantity it was holding.

    `exclude_id` leaves one sheet out, so an edit can ask "what would the
    cumulative be without my own current figures in it" — `ra.claimed_by_line()`
    takes the same argument for the same reason.
    """
    out = {}
    for mid, m in sheets_on_chain(boq_id):
        if exclude_id and mid == exclude_id:
            continue
        if approval.is_rejected(m):
            continue                 # refused — its quantity is released
        if approved_only and not approval.is_approved(m):
            continue
        for row in m.get("items") or []:
            if row.get("is_header"):
                continue
            lid = BQ._line_id(row.get("line_id"))
            if not lid:
                continue
            out[lid] = out.get(lid, 0.0) + float(row.get("qty") or 0.0)
    return out


def approved_qty_by_line(boq_id: str) -> dict:
    """
    `{line_id: qty}` from **approved** measurement sheets on the chain.

    ⚠ **THIS IS THE FUNCTION `ra.py` IMPORTS, and the whole of CC-2's C2
    sentence in code**: *"Approved measurements become the source of
    installation quantity on RA-Installation."* `ra.overclaims()` reads it and
    lowers the installation leg's ceiling to what it returns.

    `{}` means **no approved measurement exists on this chain at all**, and
    `ra.py` treats that as "this project predates measurement" and keeps the BOQ
    ceiling — which is what stops the pre-measurement bills being stranded. The
    exception cannot grow, because `/ra/create?leg=installation` refuses a BOQ
    with no approved measurement, so an empty answer can only describe a project
    that already existed. `tests/test_measurement_pin.py` is what pins that.
    """
    return measured_by_line(boq_id, approved_only=True)


def has_approved_measurement(boq_id: str) -> bool:
    """Is there an approved measurement anywhere on this BOQ's chain?"""
    return any(approval.is_approved(m) for _mid, m in sheets_on_chain(boq_id))


def boq_qty_by_line(boq_id: str) -> dict:
    """
    `{line_id: total_qty}` from the BOQ this sheet was raised against.

    ⚠ **The sheet's own BOQ, not the latest revision**, and that is the opposite
    of `ra.approved_by_line()`. A claim is measured against what is approved
    *now*, because a revision exists precisely to change what may be claimed. A
    measurement is a record of what was found on site against the schedule the
    engineer was holding, so the ceiling it was checked against is that
    schedule's. `challan.over_dispatched()` reads the challan's own BOQ for the
    same reason.
    """
    boq = (STORE.get("boqs") or {}).get(str(boq_id or "")) or {}
    out = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            out[lid] = float(li.get("total_qty") or 0.0)
    return out


# =============================================================================
# GUARD 1 — a measured quantity may not exceed the BOQ quantity
# =============================================================================

def overmeasures(boq_id: str, items: list, exclude_id: str = "") -> list:
    """
    Every row that would push its line past the BOQ quantity. Empty is a pass.

    ⚠ **OURS, not CC-2's.** C2 says nothing about a ceiling. It is here because
    a measurement is the number a claim is built from, so a measured quantity
    above the approved schedule is an over-claim that has not happened yet.

    ⚠ **Cumulative across the chain, and that is also ours.** The brief this was
    built from states the rule per line — *"measured quantity on a line may not
    exceed that line's BOQ quantity"* — which two sheets each measuring the whole
    of a line would both satisfy while the total came to twice the schedule.
    Real measurement happens in stages, so the sheets have to be summed or the
    guard is decorative. `ra.overclaims()` is cumulative for exactly this
    reason, one document along.

    Each entry carries the whole arithmetic, because "line 24.d is over" is not
    something anyone can act on and "35 in the schedule, 21 already measured,
    18 here, 4 over" is. `ra.overclaims()` returns the same shape and
    `overmeasure_message()` is the twin of `ra.overclaim_message()`.

    Two reasons a row appears, and they are `ra.overclaims()`'s two:

    - `"overmeasure"` — the cumulative would exceed the schedule's quantity.
    - `"not_in_boq"`  — the line is not in the schedule at all, so there is no
      quantity to measure against.
    """
    approved = boq_qty_by_line(boq_id)
    prior = measured_by_line(boq_id, exclude_id=exclude_id)
    labels = {}
    boq = (STORE.get("boqs") or {}).get(str(boq_id or "")) or {}
    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            labels[lid] = BQ._item_no(li.get("item_no"))

    out = []
    for row in items or []:
        if row.get("is_header"):
            continue
        lid = BQ._line_id(row.get("line_id"))
        qty = float(row.get("qty") or 0.0)
        if qty <= 0:
            continue

        item = labels.get(lid) or BQ._item_no(row.get("item_no"))
        if not lid or lid not in approved:
            out.append({"item_no": item, "line_id": lid,
                        "reason": "not_in_boq", "approved": 0.0,
                        "previously": prior.get(lid, 0.0), "this": qty,
                        "cumulative": qty, "over": qty})
            continue

        app_qty = approved[lid]
        previously = prior.get(lid, 0.0)
        cumulative = previously + qty
        if round(cumulative - app_qty, 6) > _QTY_EPSILON:
            out.append({"item_no": item, "line_id": lid,
                        "reason": "overmeasure", "approved": app_qty,
                        "previously": previously, "this": qty,
                        "cumulative": cumulative, "over": cumulative - app_qty})
    return out


def overmeasure_message(v: dict) -> str:
    """One breach, in words the person entering it can act on."""
    if v["reason"] == "not_in_boq":
        return (f"Item {v['item_no']} is not in this schedule, so there is "
                f"nothing to measure against it.")
    q = BQ._fmt_qty
    return (f"Item {v['item_no']}: {q(v['approved'])} in the schedule, "
            f"{q(v['previously'])} already measured on other sheets, "
            f"{q(v['this'])} measured here — that is {q(v['cumulative'])} in "
            f"total, {q(v['over'])} over.")


# =============================================================================
# PAGE FURNITURE
# =============================================================================

def _page(html: str) -> str:
    """A finished page. Deliberately not Jinja-rendered — ABOUT.md §7.9d."""
    return html


def _alert(msg, kind: str = "error") -> str:
    if not msg:
        return ""
    icon = "&#10003;" if kind == "success" else "&#10007;"
    return f'<div class="alert alert-{P.esc(kind)}">{icon} {P.esc(msg)}</div>'


def _flash() -> str:
    return _alert(request.args.get("msg"), request.args.get("type", "success"))


MS_STYLES = "\n<style>\n" + BP.PICKER_CSS + """
  /* Over-measurement. RED, not the challan's amber: this one refuses, and a
     colour that says "note this" on a page that has just declined to save is a
     lie about what happened. */
  .ms-block { border:1px solid #C62828; border-left:3px solid #C62828;
              background:#FDECEC; border-radius:var(--radius);
              padding:.8rem 1rem; margin-bottom:1.2rem; font-size:.85rem;
              line-height:1.6; color:#7A1D1D; }
  .ms-block b { color:#A32020; }
  .ms-block ul { margin:.5rem 0 0 1.1rem; }
</style>
"""

MS_DOC_STYLES = "\n<style>\n" + DS.BAND_CSS + """
  /* Layered after the shared sheet, introducing no new font, type size or
     border weight — the restraint every other document module holds to. CC-2
     says nothing about what a measurement sheet looks like, so NOTHING was
     invented: this adds two column widths and a signature label, and every
     other line on the page is `docsheet.py`'s. */
  .quotation-doc .doc-header.ms-2col { grid-template-columns:50% 50%; }

  /* The site engineer and the contractor's representative both sign a
     measurement in the field, so the left of the signature panel carries a
     second rule instead of the GSTIN/PAN pair. `challan.py`'s receiver block
     is the precedent — same shape, different words. */
  .quotation-doc .ms-witness { align-self:end; }
  .quotation-doc .ms-wit-rule { border-bottom:var(--rule); width:56mm;
                                margin-bottom:2px; }
  .quotation-doc .ms-wit-lbl { font-weight:700; font-size:var(--fs-sm); }

  .quotation-doc .ms-note { margin-top:4mm; font-size:var(--fs-sm); }
</style>
"""


# =============================================================================
# THE FORM
# =============================================================================

def _validate(form) -> tuple:
    """`(data, error)` — the header fields. The lines are `picked_lines()`."""
    data = {
        "date":        (form.get("date") or "").strip(),
        "measured_by": (form.get("measured_by") or "").strip(),
        "witnessed_by": (form.get("witnessed_by") or "").strip(),
        "location":    (form.get("location") or "").strip(),
        "notes":       (form.get("notes") or "").strip(),
        "ms_json":     form.get("ms_json") or "",
    }
    if not data["date"]:
        return data, "A measurement date is required."
    return data, ""


def picked_lines(raw: str, boq: dict) -> tuple:
    """The ticked lines, snapshotted. `boqpick.py`'s parser, at its fourth consumer."""
    return BP.picked_lines(
        raw, boq,
        empty_msg=("Nothing is ticked. A measurement sheet with no lines on it "
                   "is not a document."),
        cap_msg="Raise a second sheet for the rest.",
        max_lines=MAX_MS_LINES)


def _entry_form(boq: dict, data: dict, error: str = "",
                breaches: list = None, sheet: dict = None) -> str:
    """
    The create form: the line picker and the field header.

    On edit (`sheet` given) the picker is shown again, prefilled — which is the
    opposite of `challan._entry_form()` and is deliberate. A challan is signed
    for on arrival and its lines are what left the yard, so moving them under a
    signature starts a dispute. A measurement sheet is corrected *before* it is
    approved and locked afterwards by `approval.can_modify()`, so the lines are
    exactly the thing an edit is for.
    """
    boq_ref = P.esc(boq.get("ref") or "")
    editing = sheet is not None
    action = (url_for("measurement.edit_ms", id=sheet["id"]) if editing
              else url_for("measurement.create_ms", boq=boq.get("id")))

    picker = BP.grid_html(
        boq,
        title="Lines measured",
        intro_html="""        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Untick what was not measured on this visit, and enter what was found
          on site against each line. <b>A measured quantity may not take the
          line past the schedule</b> &mdash; the sheet is refused and says which
          lines and by how much. No rates and no tax appear on a measurement.
        </p>""",
        qty_label="Measured qty",
        qty_aria="Measured quantity",
        empty_note=("Nothing is ticked. A measurement sheet with no lines on "
                    "it is not a document."),
        payload_id="ms_json",
        doc_word="measurement",
        chosen=data.get("_chosen"),
        qty_of=data.get("_qty"),
        avail_label="In BOQ",
        with_pcs=False)

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Edit Measurement" if editing else "Measurement Sheet")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{MS_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>{"Edit " if editing else ""}Measurement <span>Sheet</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('measurement.list_ms')}" class="btn btn-ghost">All Measurements</a>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">&#8592; {boq_ref}</a>
    </div>
  </div>

  {_alert(error)}
  {_breach_band(breaches)}

  <div class="set-intro" style="background:var(--surface);border:1px solid var(--border);
       border-left:3px solid var(--brand);border-radius:var(--radius);
       padding:.9rem 1.1rem;margin-bottom:1.2rem;font-size:.86rem;line-height:1.6;">
    Against <b>{boq_ref}</b> &middot; {P.esc(boq.get("project_name") or "")}
    &middot; {P.esc(boq.get("account_name") or "")}<br/>
    {"This sheet is numbered <b>" + P.esc(sheet.get("ref")) + "</b>."
     if editing else
     "This sheet will be numbered <b>" + P.esc(next_ref(data.get("date", ""))) + "</b>."}
    Once it is approved, its quantities become the ceiling for
    RA&nbsp;&middot;&nbsp;Installation on this project.
  </div>

  <form method="POST" action="{action}" onsubmit="return saveJSON();">
    <input type="hidden" name="ms_json" id="ms_json" value=""/>

    <div class="form-section">
      <div class="section-title">The visit</div>
      <div class="fg2">
        <div class="form-group">
          <label for="date">Measurement date</label>
          <input type="date" id="date" name="date" value="{P.esc(data.get('date', ''))}"/>
        </div>
        <div class="form-group">
          <label for="location">Location on site</label>
          <input type="text" id="location" name="location"
                 value="{P.esc(data.get('location', ''))}"
                 placeholder="Block, floor or area measured"/>
        </div>
        <div class="form-group">
          <label for="measured_by">Measured by</label>
          <input type="text" id="measured_by" name="measured_by"
                 value="{P.esc(data.get('measured_by', ''))}"
                 placeholder="Our site engineer"/>
        </div>
        <div class="form-group">
          <label for="witnessed_by">Witnessed by</label>
          <input type="text" id="witnessed_by" name="witnessed_by"
                 value="{P.esc(data.get('witnessed_by', ''))}"
                 placeholder="Their representative on site"/>
        </div>
        <div class="form-group span2">
          <label for="notes">Notes</label>
          <textarea id="notes" name="notes" rows="2">{P.esc(data.get('notes', ''))}</textarea>
        </div>
      </div>
    </div>

    {picker}

    <div class="set-actions" style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise measurement"}</button>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · measurement sheet</p></footer>
</main>
</body></html>""")


def _breach_band(breaches: list) -> str:
    """The refusal, naming every line. Red, because the sheet was not saved."""
    if not breaches:
        return ""
    items = "".join(f"<li>{P.esc(overmeasure_message(v))}</li>" for v in breaches)
    n = len(breaches)
    return f"""
  <div class="ms-block">
    <b>Nothing was saved.</b> {n} line{'' if n == 1 else 's'} would go past the
    schedule. A measurement is what the next claim is built from, so a quantity
    above the approved schedule is refused here rather than at the claim.
    <ul>{items}</ul>
  </div>"""


# =============================================================================
# THE DOCUMENT
# =============================================================================

# Five columns. `docsheet.SELL_COLUMNS` is the eight-column set the sell and buy
# chains share and this is deliberately not it — there is no Part No, no HSN, no
# Rate and no Amount on a measurement, because none of them belongs on a sheet
# that records what was found on site.
#
# ⚠ **CC-2 says nothing about what this document looks like, so nothing was
#   invented.** Every element below is `docsheet.py`'s existing furniture: the
#   page frame, the letterhead, the foot strip, the party block, the items-table
#   shell, the signature panel and the print CSS. The only additions are two
#   column widths and one signature label, which is what `challan.py` added.
MS_COLUMNS = (("c-sno", "Sr.No."), ("c-desc", "Description"),
              ("c-qty", "Measured"), ("c-unit", "Unit"),
              ("c-avail", "In BOQ"))


def _document_html(ms: dict) -> str:
    """
    The printed measurement sheet, on the shared A4 sheet.

    **Driven by the sheet's own stored rows**, never re-read from the live BOQ —
    CLIENT_CHANGES.md §1.2, and `print_ra()`'s original defect is the reason the
    rule exists: it was built as a loop over `boq["line_items"]`, and a deleted
    BOQ line silently vanished from a printed document while its figure stayed
    inside the total. Every description, unit and quantity here comes off `ms`.

    ⚠ **No golden is pinned on this page and that is deliberate.** CC-2 is
    silent on whether a measurement prints at all, so the route exists (a sheet
    signed in the field has to reach paper) but nothing about its layout is
    asserted byte-for-byte. Pinning a golden would freeze a design nobody
    specified and make the client's first sight of it a re-baselining exercise.

    ⚠ **Nothing about approval reaches this page.** `approval.panel()`,
    `status_badge()` and `grandfather_marker()` are screen-only, and
    `tests/test_approval_b7.py` renders every printed sheet and asserts the
    strings are absent. This one is included in that sweep.
    """
    rows = ""
    sno = 0
    for row in ms.get("items", []):
        if row.get("is_header"):
            rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td colspan="4" class="c-desc">{P.esc(row.get("description", ""))}</td>
        </tr>"""
            continue
        sno += 1
        rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-desc">{P.esc(row.get("description", ""))}</td>
          <td class="c-qty">{BQ._fmt_qty(row.get("qty") or 0)}</td>
          <td class="c-unit">{P.esc(row.get("unit", ""))}</td>
          <td class="c-avail">{BQ._fmt_qty(row.get("boq_qty") or 0)}</td>
        </tr>"""

    # ── Our own identity, read at render time and never written into this file
    # `tests/test_measurement.py` greps this module and fails if a State name or
    # a GSTIN-shaped string appears anywhere in it, including in a comment —
    # `tests/test_ra_seller_identity.py`'s rule, applied to the third document
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

    site_body = DS.name_block(
        "\n".join(x for x in [ms.get("account_name") or "",
                              ms.get("site_location") or ""] if x.strip()))
    site_cell = (
        '<span class="dh-lbl">Project &amp; Site</span>'
        f'<div class="dh-body">{site_body}</div>'
        + DS._meta("Project", P.esc(ms.get("project_name"))))

    sheet_cell = (
        DS._meta("Measurement No.", P.esc(ms.get("ref")))
        + DS._meta("Date", P.esc(ms.get("date")))
        + DS._meta("Against BOQ", P.esc(ms.get("boq_ref"))))
    people_cell = (
        DS._meta("Location", P.esc(ms.get("location")))
        + DS._meta("Measured by", P.esc(ms.get("measured_by")))
        + DS._meta("Witnessed by", P.esc(ms.get("witnessed_by"))))

    note_html = ""
    if ms.get("notes"):
        note_html = (f'\n  <div class="ms-note"><b>Notes:</b> '
                     f'{P.esc(ms["notes"])}</div>')

    # Both parties sign a measurement in the field, so the contractor's
    # representative signs on the left where every other document prints GSTIN
    # and PAN. `challan.py`'s receiver block is the precedent.
    witness_html = ('<div class="ms-witness">'
                    '<div class="ms-wit-rule"></div>'
                    '<div class="ms-wit-lbl">Name &amp; Signature of Witness'
                    '</div></div>')

    return f"""
<div class="quotation-doc">

{DS.sheet_open(title_band="MEASUREMENT SHEET")}

  <div class="doc-box">
    <div class="doc-header ms-2col">
      <div class="dh-cell">{office_cell}</div>
      <div class="dh-cell">{site_cell}</div>
    </div>
    <div class="doc-header ms-2col">
      <div class="dh-cell">{sheet_cell}</div>
      <div class="dh-cell">{people_cell}</div>
    </div>

    <div class="doc-title">MEASUREMENT OF WORK DONE</div>

{DS.items_table(MS_COLUMNS, rows)}
  </div>{note_html}

{DS.sig_block(P.esc(ms.get("company_branch")), P.esc(ms.get("auth_signatory")),
              left_html=witness_html)}

{DS.sheet_close()}

</div>"""


# =============================================================================
# ROUTES
# =============================================================================

@measurement_bp.route("/")
def list_ms():
    """The register — every measurement sheet, newest first."""
    rows = sorted(records().items(),
                  key=lambda kv: (str(kv[1].get("date") or ""),
                                  str(kv[1].get("ref") or "")), reverse=True)

    body = ""
    for mid, m in rows:
        n = sum(1 for r in (m.get("items") or []) if not r.get("is_header"))
        body += f"""
      <tr>
        <td><a href="{url_for('measurement.view_ms', id=mid)}"><b>{P.esc(m.get('ref'))}</b></a></td>
        <td>{P.esc(m.get('date'))}</td>
        <td>{P.esc(m.get('project_name'))}<div style="color:var(--muted);font-size:.8rem;">{P.esc(m.get('site_location'))}</div></td>
        <td><a href="{url_for('boq.view_boq', id=m.get('boq_id', ''))}">{P.esc(m.get('boq_ref'))}</a></td>
        <td style="text-align:right;">{n}</td>
        <td>{approval.cell("measurement", m)}</td>
      </tr>"""

    if not body:
        body = ('<tr><td colspan="6" style="text-align:center;color:var(--muted);'
                'padding:2rem;">No measurement sheets yet. Raise one from a '
                'schedule.</td></tr>')

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Measurement Sheets")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Measurement <span>Sheets</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">Bills of Quantities</a>
    </div>
  </div>

  {_flash()}

  <div class="set-intro" style="background:var(--surface);border:1px solid var(--border);
       border-left:3px solid var(--brand);border-radius:var(--radius);
       padding:.9rem 1.1rem;margin-bottom:1.2rem;font-size:.86rem;line-height:1.6;">
    A measurement is raised from a schedule and records what was found on site.
    <b>Once it is approved its quantities are the ceiling for
    RA&nbsp;&middot;&nbsp;Installation</b> on that project &mdash; which is why
    an installation claim cannot be raised until one exists.
  </div>

  <table class="tbl">
    <thead><tr>
      <th>Ref</th><th>Date</th><th>Project</th><th>BOQ</th>
      <th style="text-align:right;">Lines</th><th>Approval</th>
    </tr></thead>
    <tbody>{body}</tbody>
  </table>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · measurement sheets</p></footer>
</main>
</body></html>""")


@measurement_bp.route("/create", methods=["GET", "POST"])
def create_ms():
    boq_id = request.args.get("boq") or ""
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="Choose a bill of quantities to measure against.",
                                type="error"))
    # A superseded revision is not what anybody is building from, so it is not
    # what anybody should be measuring against. Refused at the route and not
    # only in the link — `/dc/create`, `/ra/create` and `/po/create` all make
    # the same check on the same predicate, because a link is not a guard.
    if boq_id in BQ.superseded_ids():
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg="That schedule has been superseded. Measure "
                                    "against the current revision.",
                                type="error"))

    if request.method == "GET":
        return _entry_form(boq, {"date": _date.today().isoformat()})

    data, error = _validate(request.form)
    items, line_error = ([], "") if error else picked_lines(data["ms_json"], boq)
    error = error or line_error

    breaches = []
    if not error:
        # GUARD 1. A hard block — `BLOCK_OVER_MEASUREMENT`.
        breaches = overmeasures(boq_id, items)
        if breaches:
            error = ""      # the band says it in full; a second line would repeat

    if error or breaches:
        # Hand the operator back exactly what they ticked and typed.
        try:
            posted = (json.loads(data["ms_json"] or "{}").get("lines") or [])
        except (ValueError, TypeError):
            posted = []
        data["_chosen"] = {BQ._line_id(r.get("line_id")) for r in posted
                           if isinstance(r, dict)}
        data["_qty"] = {BQ._line_id(r.get("line_id")): r.get("qty")
                        for r in posted if isinstance(r, dict)}
        return _entry_form(boq, data, error, breaches)

    mid = new_id()
    record = {
        "id": mid,
        "ref": next_ref(data["date"]),
        "fy": P.fy_of(data["date"]),
        "date": data["date"],
        # The BOQ this came from — a specific revision, exactly as an RA bill,
        # a challan and a draft PO name one. Both refs are STORED, not looked
        # up, so the sheet still reads as a historical record if the schedule
        # is gone.
        "boq_id": boq_id,
        "boq_ref": boq.get("ref", ""),
        "boq_rev_no": boq.get("rev_no", 0),
        "project_name": boq.get("project_name", ""),
        "site_location": boq.get("site_location", ""),
        "account_name": boq.get("account_name", ""),
        "location": data["location"],
        "measured_by": data["measured_by"],
        "witnessed_by": data["witnessed_by"],
        "notes": data["notes"],
        "items": _with_boq_qty(items, boq_id),
        "company_branch": "", "auth_signatory": "",
        "created_at": approval._now(),
    }
    # B6 — the creator, captured at the write site. See approval.py.
    approval.stamp_creator(record)
    records()[mid] = record
    return redirect(url_for("measurement.view_ms", id=mid,
                            msg="Measurement raised. It has to be approved "
                                "before an installation claim can use it.",
                            type="success"))


def _with_boq_qty(items: list, boq_id: str) -> list:
    """
    Snapshot the schedule's quantity onto each row, for the printed `In BOQ`
    column.

    Stored rather than looked up at render time, for CLIENT_CHANGES.md §1.2's
    reason: the sheet has to read as the record of what the engineer was holding
    even after the schedule is revised.
    """
    approved = boq_qty_by_line(boq_id)
    out = []
    for row in items or []:
        row = dict(row)
        if not row.get("is_header"):
            lid = BQ._line_id(row.get("line_id"))
            row["boq_qty"] = approved.get(lid, 0.0)
        out.append(row)
    return out


@measurement_bp.route("/view/<id>")
def view_ms(id: str):
    ms = records().get(id)
    if not ms:
        return redirect(url_for("measurement.list_ms",
                                msg="That measurement sheet no longer exists.",
                                type="error"))

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Measurement " + str(ms.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{MS_DOC_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Measurement <span style="color:var(--brand);">{P.esc(ms.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('measurement.list_ms')}" class="btn btn-ghost">All Measurements</a>
    <a href="{url_for('boq.view_boq', id=ms.get('boq_id', ''))}" class="btn btn-ghost">{P.esc(ms.get('boq_ref'))}</a>
    <a href="{url_for('measurement.edit_ms', id=id)}" class="btn btn-ghost">Edit</a>
    <a href="{url_for('measurement.delete_ms', id=id)}" class="btn btn-ghost">Delete</a>
    <a href="{url_for('measurement.print_ms', id=id)}" class="btn">&#128438;&nbsp;Print</a>
  </div>
</div>

{_flash()}
{approval.panel("measurement", ms)}

<div class="doc-outer">
{_document_html(ms)}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · measurement sheet</p>
</footer>
</main>
</body></html>""")


@measurement_bp.route("/print/<id>")
def print_ms(id: str):
    """
    The sheet alone behind a `.no-print` action bar — `/dc/print`'s shape.

    ⚠ **B7 applies here like everywhere else.** An unapproved measurement does
    not print, refused by URL. There is no draft/cancelled exemption on this
    document: the RA bill has one because it has a lifecycle that predates the
    ladder, and a measurement's only state is where it stands on its ladder.
    """
    ms = records().get(id)
    if not ms:
        return redirect(url_for("measurement.list_ms",
                                msg="That measurement sheet no longer exists.",
                                type="error"))

    may_print, why_not = approval.can_print("measurement", ms)
    if not may_print:
        return redirect(url_for("measurement.view_ms", id=id, msg=why_not,
                                type="error"))

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(ms.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{MS_DOC_STYLES}
</head>
<body>
<div class="screen-acts no-print">
  <a href="{url_for('measurement.view_ms', id=id)}" class="btn btn-ghost">&#8592;&nbsp;Back</a>
  <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
</div>
<div class="doc-outer">
{_document_html(ms)}
</div>
</body></html>""")


@measurement_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_ms(id: str):
    """
    Correct a sheet — header fields **and** the measured quantities.

    ⚠ Gated by `approval.can_modify()`, which is B7-adjacent and **ours**: an
    approved sheet is locked, a part-climbed one is locked, a rejected one goes
    back to whoever raised it. Those rules are written once in `approval.py` and
    this calls them rather than restating any part of them.
    """
    ms = records().get(id)
    if not ms:
        return redirect(url_for("measurement.list_ms",
                                msg="That measurement sheet no longer exists.",
                                type="error"))

    may, why_not = approval.can_modify("measurement", ms)
    if not may:
        return redirect(url_for("measurement.view_ms", id=id, msg=why_not,
                                type="error"))

    boq_id = str(ms.get("boq_id") or "")
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("measurement.view_ms", id=id,
                                msg="The schedule this sheet was raised against "
                                    "is gone, so its lines cannot be re-picked.",
                                type="error"))

    if request.method == "GET":
        data = {k: ms.get(k, "") for k in
                ("date", "location", "measured_by", "witnessed_by", "notes")}
        data["_chosen"] = {BQ._line_id(r.get("line_id"))
                           for r in ms.get("items") or []
                           if not r.get("is_header")}
        data["_qty"] = {BQ._line_id(r.get("line_id")): r.get("qty")
                        for r in ms.get("items") or []
                        if not r.get("is_header")}
        return _entry_form(boq, data, sheet=ms)

    data, error = _validate(request.form)
    items, line_error = ([], "") if error else picked_lines(data["ms_json"], boq)
    error = error or line_error

    breaches = []
    if not error:
        # GUARD 1, with THIS sheet left out of the prior sum — otherwise an edit
        # that changes nothing would be compared against its own figures and
        # refuse itself. `ra.overclaims()` takes `exclude_ra_id` for the same
        # reason and it is the same bug one document over.
        breaches = overmeasures(boq_id, items, exclude_id=id)

    if error or breaches:
        try:
            posted = (json.loads(data["ms_json"] or "{}").get("lines") or [])
        except (ValueError, TypeError):
            posted = []
        data["_chosen"] = {BQ._line_id(r.get("line_id")) for r in posted
                           if isinstance(r, dict)}
        data["_qty"] = {BQ._line_id(r.get("line_id")): r.get("qty")
                        for r in posted if isinstance(r, dict)}
        return _entry_form(boq, data, error, breaches, sheet=ms)

    ms.update({
        "date": data["date"],
        "location": data["location"],
        "measured_by": data["measured_by"],
        "witnessed_by": data["witnessed_by"],
        "notes": data["notes"],
        "items": _with_boq_qty(items, boq_id),
    })
    # An approval describes the document somebody read, so a changed document
    # has not been approved. `approval.clear_approvals()` is the one place that
    # rule lives; `ra.edit_ra()` calls it for the same reason.
    approval.clear_approvals(ms)
    return redirect(url_for("measurement.view_ms", id=id,
                            msg="Measurement updated. It is back at the bottom "
                                "of its approval ladder.",
                            type="success"))


@measurement_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_ms(id: str):
    """
    GET confirms, POST deletes. Gated by the same `can_modify()` as the edit.

    ⚠ **A sheet an installation claim has already been built on is still
    deletable, and that is a known limitation rather than a decision.** Deleting
    it lowers the ceiling `ra.overclaims()` reads, so a bill that was legal
    becomes one that could not be raised today — the figures on the issued bill
    do not change, because every claim row is a snapshot, but the project's
    remaining balance does. Nothing in CC-2 covers it and no receipt-style guard
    was invented here; it is carried into the pass report as an open question.
    """
    ms = records().get(id)
    if not ms:
        return redirect(url_for("measurement.list_ms",
                                msg="That measurement sheet no longer exists.",
                                type="error"))

    may, why_not = approval.can_modify("measurement", ms)
    if not may:
        return redirect(url_for("measurement.view_ms", id=id, msg=why_not,
                                type="error"))

    if request.method != "POST":
        return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delete Measurement")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top"><h1>Delete <span>{P.esc(ms.get('ref'))}</span></h1></div>
  <div class="alert alert-error">
    This measurement sheet and its {sum(1 for r in (ms.get('items') or [])
                                       if not r.get('is_header'))} measured
    line(s) will be removed. If an installation claim has already been raised
    against this project, deleting the sheet lowers the ceiling every later
    claim is checked against.
  </div>
  <form method="POST" style="display:flex;gap:.75rem;">
    <button type="submit" class="btn">Delete it</button>
    <a href="{url_for('measurement.view_ms', id=id)}" class="btn btn-ghost">Cancel</a>
  </form>
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · measurement sheet</p></footer>
</main>
</body></html>""")

    records().pop(id, None)
    return redirect(url_for("measurement.list_ms",
                            msg="Measurement sheet deleted.", type="success"))
