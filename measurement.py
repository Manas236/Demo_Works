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


# =============================================================================
# THE PIN — the closed set of RA bills that predate measurement
# =============================================================================
# ⚠ **This is the point of the whole grandfather arrangement, and it is the same
#   shape as `approval.MIGRATION_KEY`.** Existing RA-Installation bills carry a
#   typed quantity with no measurement behind them. Requiring one outright would
#   break live records; allowing it silently would pretend the rule held when it
#   did not. So the set is **counted at migration and closed**, and
#   `tests/test_measurement_pin.py` fails if an installation bill created after
#   that moment claims quantity with no measurement behind it.
#
#   Without that test "pre-measurement" stops being a closed historical set and
#   becomes a state any future bill can fall into, which is the same as not
#   having the rule at all.

# Where the migration writes its own record, under STORE["settings"].
PIN_KEY = "measurement_migration"

# The mark a grandfathered RA bill carries. Named once so the migration, the
# predicate, the renderer and the test cannot spell it four different ways.
PRE_MEASUREMENT_FIELD = "pre_measurement"


def migration_record() -> dict:
    """
    What the migration recorded about itself: when it ran and what it marked.

    `{}` when it has never run — the state of a fresh database, where there is
    nothing to grandfather because there is nothing older than this module.
    """
    got = STORE.get("settings", {}).get(PIN_KEY)
    return dict(got) if isinstance(got, dict) else {}


def is_pre_measurement(bill) -> bool:
    """
    Does this RA bill predate the measurement document?

    True only for the explicit mark `tools/backfill_measurement_pin.py` writes.
    ⚠ **Never inferred from a missing measurement**, which is exactly how the
    pinned set would grow: a bill written next year through a route with a bug
    in it would quietly join a set that was closed in August.
    `approval.is_grandfathered()` makes the same argument one document along.
    """
    return bool((bill or {}).get(PRE_MEASUREMENT_FIELD))


PRE_MEASUREMENT_NOTE = (
    "This claim predates the measurement document, so its installation "
    "quantity was typed rather than measured. Later claims on this project are "
    "checked against an approved measurement sheet.")

PRE_MEASUREMENT_CHIP_TITLE = (
    "Typed quantity - this claim predates the measurement document")

_CHIP = ("display:inline-block;padding:2px 9px;border-radius:12px;"
         "font-size:0.74rem;font-weight:700;letter-spacing:.02em;"
         "border:1px solid;background:#f4f1ea;color:#5b513c;"
         "border-color:#ddd5c4;")


def pre_measurement_marker(bill) -> str:
    """
    The visible "typed quantity" marker for a grandfathered RA bill.

    ⚠ **Screen only, and never on any printed sheet.** CC-2 carries no
    requirement that anything about measurement appears on paper, and a note on
    an issued claim saying its figures were typed is exactly the sentence
    nobody wants read by a main contractor. `approval.grandfather_marker()`
    makes the same argument; `tests/test_measurement_pin.py` renders every
    printed document and asserts the string is absent from all of them.
    """
    if not is_pre_measurement(bill):
        return ""
    return (
        '<div style="margin:.6rem 0;padding:.55rem .8rem;border-radius:8px;'
        'background:#f4f1ea;border:1px solid #ddd5c4;color:#5b513c;'
        'font-size:0.82rem;line-height:1.45">'
        '<b>Typed quantity.</b> ' + _esc(PRE_MEASUREMENT_NOTE) + '</div>')


def pre_measurement_chip(bill) -> str:
    """The compact form, for a register row. Screen only, like the marker."""
    if not is_pre_measurement(bill):
        return ""
    return (f'<span title="{_esc(PRE_MEASUREMENT_CHIP_TITLE)}" '
            f'style="{_CHIP}">TYPED QUANTITY</span>')


def needs_pin(bill) -> bool:
    """
    Is this an RA bill the migration would mark?

    An **installation** bill claiming a quantity, on a chain with no approved
    measurement, that nobody has marked either way. The supply leg is not here:
    C1's supply proof is a delivery challan and no quantity flows from it, so a
    supply bill has nothing to be grandfathered against.
    """
    if not isinstance(bill, dict):
        return False
    if str(bill.get("leg") or "") != "installation":
        return False
    if PRE_MEASUREMENT_FIELD in bill:
        return False
    if not any(float(c.get("qty") or 0.0) > 0 for c in bill.get("claims") or []):
        return False
    return not has_approved_measurement(str(bill.get("boq_id") or ""))


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


def sheets_on_chain(boq_id: str, chain: set = None) -> list:
    """
    `[(id, sheet)]` raised anywhere on this BOQ's revision chain, newest first.

    **Chain-scoped, not record-scoped**, for `ra.claimed_by_line()`'s reason: a
    revision is a new BOQ record, so a per-record answer would report nil
    measured the moment a schedule was revised — silently, and only on the
    projects that have been revised.

    `boq._ancestor_ids()` walks **backward**, which is
    `challan.dispatched_by_line()`'s choice and is right for its reason: a
    measurement is always raised against the tip, so backward is the whole chain
    from wherever it was raised.

    ⚠ **`chain` exists so `ra.py` can hand in ITS chain, and that is
    load-bearing rather than tidy.** `ra.claimed_by_line()` walks
    `ra.revision_chain()`, which goes **both** ways. On the tip the two answers
    are identical, but `edit_ra()` asks about a bill whose `boq_id` may be a
    superseded revision — and there a backward-only walk would miss a sheet
    raised on a later revision while the claimed sum still counted the later
    bills. The ceiling and the sum would then be measured over different sets of
    records, which is the one thing a guard must never do. `ra.overclaims()`
    passes its own chain in; everything else here defaults to the backward walk.
    """
    if chain is None:
        chain = BQ._ancestor_ids(boq_id) if boq_id else set()
    rows = [(mid, m) for mid, m in records().items()
            if str(m.get("boq_id") or "") in chain]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""),
                              str(kv[1].get("ref") or "")), reverse=True)
    return rows


def measured_by_line(boq_id: str, exclude_id: str = "",
                     approved_only: bool = False, chain: set = None) -> dict:
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
    for mid, m in sheets_on_chain(boq_id, chain):
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


def approved_qty_by_line(boq_id: str, chain: set = None) -> dict:
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
    return measured_by_line(boq_id, approved_only=True, chain=chain)


def has_approved_measurement(boq_id: str, chain: set = None) -> bool:
    """Is there an approved measurement anywhere on this BOQ's chain?"""
    return any(approval.is_approved(m)
               for _mid, m in sheets_on_chain(boq_id, chain))


def installation_claims_on_chain(boq_id: str, chain: set = None) -> list:
    """
    `[ra_no, ...]` — installation RA bills claiming quantity anywhere on this
    BOQ's revision chain, lowest first.

    ⚠ **Reads `STORE["ra_bills"]` directly, and must.** `ra.py` imports THIS
    module for `approved_qty_by_line()` — CC-2's C2 sentence in code — so
    `measurement -> ra` would be a cycle at boot and is refused by
    `tests/test_import_directions.py` in terms. This is the one-way trick
    `boq.claims_against_chain()` already uses for exactly the same reason, one
    document along.

    **Installation leg only.** A supply claim is proved by a delivery challan
    (C1's other chain) and no quantity flows to it from a measurement, so a
    supply bill has nothing resting on this sheet.
    """
    if chain is None:
        chain = BQ._ancestor_ids(boq_id) if boq_id else set()
    out = []
    for bill in (STORE.get("ra_bills") or {}).values():
        if str(bill.get("boq_id") or "") not in chain:
            continue
        if str(bill.get("leg") or "") != "installation":
            continue
        claimed = sum(float(c.get("qty") or 0.0) for c in bill.get("claims") or [])
        if claimed <= 0:
            continue
        try:
            out.append(int(bill.get("ra_no") or 0))
        except (TypeError, ValueError):
            out.append(0)
    return sorted(set(out))


def has_ladder_history(ms: dict) -> bool:
    """
    Has this sheet ever been more than a draft nobody submitted?

    True once it has been approved, rejected, or had a single rung climbed. It
    is the question `can_delete()` needs and `approval.status_of()` cannot
    answer on its own: a rejected sheet reads REJECTED whether it was rejected
    at the first rung or after somebody had already approved it.
    """
    return bool(approval.is_approved(ms) or approval.is_rejected(ms)
                or approval.approvals_of(ms))


def can_delete(ms: dict) -> tuple:
    """
    `(allowed, reason)` — may this measurement sheet be destroyed?

    ⚠ **Refuses a sheet an installation claim rests on.** Pass E shipped the
    delete route with this left open and said so: deleting the sheet lowers the
    ceiling `ra.overclaims()` reads, so a bill that was legal becomes one that
    could not be raised today. The issued figures do not move — every claim row
    is a snapshot — but **the project's remaining balance does**, and the
    document the claim was measured from stops existing.

    It **layers on top of `approval.can_modify()` and replaces none of it**,
    which is `ra.can_edit()`'s arrangement with the same function. That matters
    for what this actually adds, and the honest account is:

    * an **approved** sheet was already undeletable — `can_modify()` rule 1
      locks it, an Owner included — and an approved sheet is the only kind that
      feeds the ceiling. So the common case was closed before this existed.
    * a sheet that was approved and has since been **rejected** was NOT. It is
      editable and deletable by its creator, and deleting it destroys the basis
      document for a claim already raised. That is the hole this closes.

    ⚠ **A draft nobody ever submitted stays deletable, deliberately.** Refusing
    on "a claim exists anywhere on the chain" alone would strand a sheet raised
    by mistake on a live project with no way to remove it ever, which is a trap
    rather than a guard. A sheet that never entered the ladder was never the
    basis of anything, so `has_ladder_history()` is the second condition.

    Refuses **by URL**, in the route, and not by hiding the button — B5's
    established rule and `ra.can_delete()`'s shape.
    """
    if not ms:
        return False, "That measurement sheet no longer exists."

    if not has_ladder_history(ms):
        return True, ""

    claims = installation_claims_on_chain(str(ms.get("boq_id") or ""))
    if claims:
        bills = ", ".join(f"RA{n}" for n in claims)
        plural = "bills" if len(claims) != 1 else "bill"
        return False, (
            f"{ms.get('ref') or 'This sheet'} cannot be deleted — installation "
            f"{plural} {bills} were raised against this project while it stood. "
            f"Deleting it would lower the measured ceiling under a claim that "
            f"has already been made, and destroy the document that claim was "
            f"measured from. Correct the quantities on the next sheet instead.")

    return True, ""


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

  /* ── The joint grid, on screen ──────────────────────────────────────
     Introduces no new colour or border weight; every token is the house
     one the picker beside it already uses. */
  table.jg-table { width:100%; border-collapse:collapse; font-size:.8rem; }
  table.jg-table th, table.jg-table td { border:1px solid var(--border);
        padding:2px 3px; }
  table.jg-table th { background:#f3f4f6; font-weight:700; text-align:center;
        white-space:nowrap; }
  table.jg-table th.jg-loc { text-align:left; min-width:110px; }
  table.jg-table th.jg-rem { text-align:left; min-width:180px; }
  .jg-unit { display:block; font-weight:400; font-size:.85em; color:#555; }
  .jg-in, .jg-loc-in, .jg-rem-in { width:100%; border:0; background:transparent;
        padding:3px 2px; font:inherit; color:inherit; }
  .jg-in { text-align:right; min-width:52px; }
  .jg-in:focus, .jg-loc-in:focus, .jg-rem-in:focus { outline:2px solid var(--brand);
        outline-offset:-2px; background:#fff; }
  .jg-del { padding:0 .45rem; line-height:1.6; }
</style>
"""

# =============================================================================
# THE JOINT MEASUREMENT SHEET — the client's own workbook layout
# =============================================================================
#
# Authorised by the **twenty-third §0 block of CLIENT_CHANGES.md, 6 September
# 2026**. Transcribed from the client's own workbook; they are not re-sending
# the file, so that block and this section are the whole specification.
#
# ⚠ **CC-2 SAYS NOTHING ABOUT THIS.** C2 is two sentences and neither of them
#   mentions printing, a layout, a location, a diameter or a countersignature.
#   Every ruling below is **ours or Manas's, unspecced and unpriced**, and the
#   §0 block lists each one so Yogesh can disagree with any of them
#   individually. Nobody may later cite one as delivered CC-2 scope.
#
# ⚠⚠ **THE `items` ROWS ARE NOT TOUCHED BY ANY OF THIS, AND THAT IS THE WHOLE
#     POINT.** The brief for this pass instructed that the measurement stop
#     capping the installation claim and that no per-line `line_id` link exist
#     — describing both as things not to *add*. Both already existed and ship:
#     `ra.overclaims()` replaces the BOQ ceiling with `approved_qty_by_line()`,
#     which reads `items[].line_id`. A (location, dia) grid carries no
#     `line_id`, so building it *instead of* `items` would have deleted two live
#     guards silently — and through `approved_qty_by_line()` returning `{}`,
#     which `ra.py` reads as *"this project predates measurement"*. It would
#     also have contradicted C2's own sentence, the only one CC-2 specifies.
#
#     **Manas ruled on 6 September 2026 that the cap stays.** So a joint sheet
#     carries BOTH: the `items` rows that feed the ceiling, unchanged, and the
#     grid, which is what prints. `ra.py` is not modified by this pass.

GRID_MODEL_JOINT = "joint-v1"

# ⚠ **The legacy mark is WRITTEN, never inferred from a missing field.** This is
#   `pre_measurement`'s rule and `pre_approval_system`'s, applied a third time
#   and for their reason: "no grid" and "created before grids existed" are
#   different facts, and a branch that cannot tell them apart will one day
#   render a new sheet through the old template because somebody's grid failed
#   to save. `tools/backfill_measurement_grid.py` writes the mark.
GRID_MODEL_LEGACY = "legacy-linear"

# The seventeen rows the client's paper form carries, in their order.
# ⚠ Rows are per sheet and editable; only the SEED is fixed here. Their form
#   then carries about ten blank ruled fillers, which this app does NOT print —
#   see `_joint_document_html()`.
DEFAULT_LOCATION_ROWS = (
    "H1", "SH 1", "B1", "B2", "B3", "B4", "B5", "B6", "B7",
    "Hosereel", "Hose Box", "Hydrant", "Air Release", "Air Vessel",
    "RRL Hose", "Branch Pipe", "4 Way",
)

# The four free-text header fields. SITE is NOT among them: it is inherited from
# the project's address-book entry — see `site_of()`.
GRID_HEADER_FIELDS = ("system", "material", "dia_meter", "area")

MAX_GRID_ROWS = 200


def is_joint(ms) -> bool:
    """Is this sheet the joint (location x diameter) model?"""
    return str((ms or {}).get("grid_model") or "") == GRID_MODEL_JOINT


def is_legacy_grid(ms) -> bool:
    """
    Is this sheet the linear pre-6-September model?

    True for the explicit mark **and** for a record carrying no mark at all —
    every measurement written before this pass. The mark is what
    `tools/backfill_measurement_grid.py` adds so the state is recorded rather
    than deduced; until it runs, the absence is what describes them, and both
    render through the same branch either way.
    """
    return not is_joint(ms)


def default_columns() -> list:
    """The column set a NEW sheet is created with, read from `/settings`."""
    import settings as ST
    return [dict(c) for c in ST.measurement_columns()]


def grid_columns_of(ms) -> list:
    """
    The columns THIS sheet was created with.

    ⚠ **Read off the record, never out of `/settings`.** A settings edit must
      not restate a sheet somebody has already signed — the same invariant as
      the RA bill's snapshotted claim rows, and it has already shipped as a
      defect once in this repo. A sheet with no snapshot at all is a legacy
      record and has no grid to draw.
    """
    return list((ms or {}).get("grid_columns") or [])


def grid_rows_of(ms) -> list:
    return list((ms or {}).get("grid_rows") or [])


def _cell(row: dict, key: str) -> float:
    try:
        return float((row.get("values") or {}).get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def grid_totals(ms) -> dict:
    """
    `{column key: total}` — **every** numeric column, over **every** row.

    ⚠ **A DELIBERATE DEPARTURE FROM THE CLIENT'S OWN PAPER, recorded in the §0
      block so nobody later "fixes" it back.** Their workbook's TOTAL row is
      wrong in three separate ways:

        * `25 NB` has **no total at all**;
        * an **unlabelled** column immediately left of `25 NB` does have one,
          and it sums a **different row range** to every other column — rows
          9-35 against 9-25;
        * `SUPPORTS (MSA kgs)` has no total either.

      We total every column over every row and we do not carry the unlabelled
      column at all. Reproducing a spreadsheet's arithmetic bugs is not
      fidelity to the client's process; it is copying a mistake onto a document
      two parties sign.
    """
    cols = grid_columns_of(ms)
    rows = grid_rows_of(ms)
    return {c["key"]: sum(_cell(r, c["key"]) for r in rows) for c in cols}


def columns_in_use(ms) -> list:
    """The column labels that actually carry a value on this sheet."""
    totals = grid_totals(ms)
    return [c["label"] for c in grid_columns_of(ms)
            if abs(totals.get(c["key"], 0.0)) > _QTY_EPSILON]


def dia_hint(ms) -> str:
    """
    The derived hint shown beside the DIA METER box.

    ⚠ **A HINT, and never an auto-fill.** The client's own sample reads
      *"25 mm To 150 mm"* while their grid carries a **200 NB** column — so the
      field is a stated scope for the system, not a summary of what was
      measured, and filling it from the grid would overwrite a statement of
      scope with a description of data. Ruled 6 September 2026.
    """
    used = columns_in_use(ms)
    if not used:
        return ""
    return "This sheet carries values in: " + ", ".join(used)


def site_of(ms, boq=None) -> tuple:
    """
    `(label, source)` — the SITE band's value and where it came from.

    ⚠ **SITE IS INHERITED, NEVER TYPED.** It comes from the BOQ's project's
      `site_address_id`, with the label snapshotted onto the sheet at save —
      exactly the pattern `project.site_address` already uses. Three spellings
      of one city are already live in this database because site was free text
      in three places, and the 30 August cleanup is what that cost. A fourth
      free-text site field would be the same mistake a fourth time.

      Where the BOQ has no project, or the project has no site, this falls back
      to whatever the BOQ itself carries and the caller shows the amber band —
      `project.site_drift()`'s shape, not a second design.
    """
    ms = ms or {}
    if ms.get("site_label"):
        return str(ms["site_label"]), str(ms.get("site_source") or "snapshot")
    boq = boq or (STORE.get("boqs") or {}).get(str(ms.get("boq_id") or ""))
    return _site_from_boq(boq)


def _site_from_boq(boq) -> tuple:
    """`(label, source)` for a BOQ, resolved through its project."""
    boq = boq or {}
    pid = str(boq.get("project_id") or "")
    proj = (STORE.get("projects") or {}).get(pid) if pid else None
    if proj:
        label = str(proj.get("site_address") or "").strip()
        if label:
            return label, "project"
    fallback = str(boq.get("site_location") or "").strip()
    return fallback, ("boq" if fallback else "none")


def parse_grid(raw: str, columns: list) -> tuple:
    """
    `(rows, error)` — the posted grid, cleaned against `columns`.

    A cell whose column is not in the snapshot is **dropped**, never stored:
    the snapshot is what the sheet prints and a value with no column to sit in
    would be invisible money. A row with no label and no values at all is
    dropped too, which is what an untouched filler row looks like.
    """
    try:
        payload = json.loads(raw or "{}")
        raw_rows = payload.get("rows") or []
    except (ValueError, TypeError):
        return [], "The measurement grid did not survive the round trip. Nothing was saved."
    if not isinstance(raw_rows, list):
        return [], "The measurement grid did not survive the round trip. Nothing was saved."
    if len(raw_rows) > MAX_GRID_ROWS:
        return [], (f"This sheet has {len(raw_rows)} location rows and the "
                    f"limit is {MAX_GRID_ROWS}. Raise a second sheet.")

    keys = [c["key"] for c in columns]
    out = []
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        label = str(r.get("label") or "").strip()[:120]
        remarks = str(r.get("remarks") or "").strip()[:300]
        values, raw_vals = {}, (r.get("values") or {})
        if isinstance(raw_vals, dict):
            for k in keys:
                v = raw_vals.get(k)
                if v in (None, ""):
                    continue
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    return [], (f"Row &quot;{P.esc(label) or '(unnamed)'}&quot; "
                                f"has a value that is not a number.")
                if f < 0:
                    return [], (f"Row &quot;{P.esc(label) or '(unnamed)'}&quot; "
                                f"has a negative measurement.")
                values[k] = f
        if not label and not values and not remarks:
            continue
        out.append({"label": label, "values": values, "remarks": remarks})
    return out, ""


def seed_grid_rows(columns: list) -> list:
    """The seventeen seeded location rows, empty."""
    return [{"label": name, "values": {}, "remarks": ""}
            for name in DEFAULT_LOCATION_ROWS]


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

# ── The joint sheet's own styles ────────────────────────────────────────────
#
# Layered AFTER the shared sheet and never an edit to it, exactly as
# `boq.BOQ_STYLES` is: the quotation, PI, TI, PO and RA sheets are untouched
# and still portrait. Nothing here introduces a font, a type size or a border
# weight the house sheet does not already use.
MS_JOINT_STYLES = """
<style>
  /* ── Landscape. The grid is 13 columns wide before REMARKS. ───────────
     A later @page rule of equal specificity wins, so this replaces
     `size:A4 portrait` for this page only — boq.py's precedent. */
  @media print {
    @page { size:A4 landscape; margin:9mm 8mm 8mm; }
  }
  .ms-joint-outer { max-width:297mm; }

  /* The five-row header field block, down the left under the title. */
  .quotation-doc .jm-fields { display:grid;
        grid-template-columns:auto 1fr; gap:1px 8mm;
        font-size:var(--fs-sm); margin:3mm 0 4mm; max-width:120mm; }
  .quotation-doc .jm-f-lbl { font-weight:700; letter-spacing:.04em; }
  .quotation-doc .jm-f-val { border-bottom:var(--rule); min-height:1.35em; }
  .quotation-doc .jm-hint { grid-column:1 / -1; font-size:var(--fs-xs, .68rem);
        color:#555; padding-top:1px; }

  /* The amber inherited-site band. `project.site_drift()`'s shape in this
     sheet's own metrics, deliberately rather than a second design. */
  .quotation-doc .jm-drift { display:flex; gap:.5rem; align-items:flex-start;
        border:1px solid #fde68a; background:#fffbeb; border-radius:4px;
        padding:.45rem .7rem; margin:0 0 3mm; font-size:var(--fs-xs, .68rem);
        line-height:1.5; }

  /* ── The grid ─────────────────────────────────────────────────────── */
  .quotation-doc table.jm-grid { width:100%; border-collapse:collapse;
        font-size:var(--fs-xs, .68rem); table-layout:fixed; }
  .quotation-doc table.jm-grid th,
  .quotation-doc table.jm-grid td { border:var(--rule); padding:1.4mm 1mm;
        vertical-align:middle; }
  .quotation-doc table.jm-grid th { text-align:center; font-weight:700;
        background:#f3f4f6; }
  .quotation-doc .jm-loc { width:34mm; text-align:left; }
  .quotation-doc .jm-num { width:13mm; text-align:right; }
  /* Widest column on the sheet, about four times a dia column. */
  .quotation-doc .jm-rem { width:52mm; text-align:left; }
  .quotation-doc .jm-unit { display:block; font-weight:400;
        font-size:.85em; color:#444; }
  .quotation-doc tr.jm-total td { font-weight:700; background:#f3f4f6; }

  /* ── The two-party sign-off ───────────────────────────────────────── */
  .quotation-doc .jm-sign { display:grid; grid-template-columns:1fr 1fr;
        gap:0 12mm; margin-top:8mm; }
  .quotation-doc .jm-party { border:var(--rule); }
  .quotation-doc .jm-band { border-bottom:var(--rule); padding:1.6mm 2mm;
        font-weight:700; text-align:center; background:#f3f4f6;
        min-height:1.4em; }
  .quotation-doc .jm-srow { display:grid; grid-template-columns:26mm 1fr;
        border-bottom:var(--rule); }
  .quotation-doc .jm-srow:last-child { border-bottom:0; }
  .quotation-doc .jm-slbl { padding:2.2mm 2mm; font-weight:700;
        border-right:var(--rule); }
  .quotation-doc .jm-sval { padding:2.2mm 2mm; min-height:1.5em; }
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
        # The joint sheet's own heading. SITE is NOT here: it is inherited
        # from the project's address-book entry and never typed — see
        # `site_of()` for why a fourth free-text site field is refused.
        "system":      (form.get("system") or "").strip()[:120],
        "material":    (form.get("material") or "").strip()[:120],
        "dia_meter":   (form.get("dia_meter") or "").strip()[:120],
        "area":        (form.get("area") or "").strip()[:120],
        "grid_json":   form.get("grid_json") or "",
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

  <form method="POST" action="{action}" onsubmit="return saveJSON() &amp;&amp; collectGrid();">
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

    {_joint_fields_html(boq, data, sheet)}

    {_joint_grid_form(boq, data, sheet)}

    {picker}

    <div class="set-actions" style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise measurement"}</button>
      <a href="{url_for('boq.view_boq', id=boq.get('id'))}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · measurement sheet</p></footer>
</main>
</body></html>""")


def _joint_fields_html(boq: dict, data: dict, sheet: dict = None) -> str:
    """
    The five header rows: SITE (inherited, read-only) and four free-text.

    ⚠ **SITE HAS NO INPUT AT ALL, and that is the ruling rather than an
      oversight.** It is inherited from the BOQ's project's address-book entry
      and snapshotted at save. Three spellings of one city are already live in
      this database because site was free text in three places; the 30 August
      cleanup is what that cost, and a fourth free-text site box would be the
      same mistake a fourth time. `project.site_address` is the pattern.
    """
    label, source = (site_of(sheet, boq) if sheet else _site_from_boq(boq))
    note = {
        "project": "Inherited from this project's address-book site.",
        "snapshot": "Snapshotted onto this sheet when it was saved.",
        "boq": ("&#9888; The project has no address-book site, so this is the "
                "schedule's own free-text string. Nothing has been guessed at."),
        "none": ("&#9888; Neither the project nor the schedule records a site."),
    }[source]

    def _fld(key, label_text, placeholder):
        return f"""
        <div class="form-group">
          <label for="{key}">{label_text}</label>
          <input type="text" id="{key}" name="{key}"
                 value="{P.esc(data.get(key, ''))}" placeholder="{placeholder}"/>
        </div>"""

    hint = dia_hint(sheet) if sheet else ""
    hint_html = (f'<p class="fld-hint" style="margin:.3rem 0 0;">{P.esc(hint)}'
                 f'</p>' if hint else "")

    return f"""
    <div class="form-section">
      <div class="section-title">The sheet's own heading</div>
      <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
        These five rows print down the left of the joint sheet, under the title.
      </p>
      <div class="fg2">
        <div class="form-group span2">
          <label>Site</label>
          <input type="text" value="{P.esc(label)}" disabled
                 style="background:#f3f4f6;"/>
          <p class="fld-hint" style="margin:.3rem 0 0;">{note}</p>
        </div>
        {_fld("system", "System", "Hydrant &amp; Sprinkler Line")}
        {_fld("material", "Material", "MS Pipe")}
        {_fld("dia_meter", "Dia meter", "25 mm To 150 mm")}
        {_fld("area", "Area", "All Area")}
        <div class="form-group span2">{hint_html}</div>
      </div>
    </div>"""


def _joint_grid_form(boq: dict, data: dict, sheet: dict = None) -> str:
    """
    The location x diameter entry grid.

    Rows are editable, addable and removable per sheet; the columns come from
    the sheet's own snapshot when editing, and from `/settings` when creating.
    """
    cols = (grid_columns_of(sheet) if sheet and is_joint(sheet)
            else default_columns())
    rows = data.get("_grid")
    if rows is None:
        rows = (grid_rows_of(sheet) if sheet and is_joint(sheet)
                else seed_grid_rows(cols))

    def _head(c):
        # Hoisted out of the f-string on purpose: a nested same-quoted
        # subscript inside an f-string expression is a SyntaxError before
        # Python 3.12, and this repo runs 3.10.
        unit = str(c.get("unit") or "").strip()
        tail = (f'<span class="jg-unit">({P.esc(unit)})</span>' if unit else "")
        return f'<th class="jg-num">{P.esc(c["label"])}{tail}</th>'

    heads = "".join(_head(c) for c in cols)

    body = ""
    for i, r in enumerate(rows):
        cells = "".join(
            f'<td><input type="number" step="any" min="0" class="jg-in" '
            f'data-key="{P.esc(c["key"])}" '
            f'value="{P.esc(str((r.get("values") or {}).get(c["key"], "")))}"/></td>'
            for c in cols)
        body += (
            f'\n        <tr>'
            f'<td><input type="text" class="jg-loc-in" '
            f'value="{P.esc(r.get("label") or "")}"/></td>'
            f'{cells}'
            f'<td><input type="text" class="jg-rem-in" '
            f'value="{P.esc(r.get("remarks") or "")}"/></td>'
            f'<td><button type="button" class="btn btn-ghost jg-del" '
            f'title="Remove this row">&times;</button></td></tr>')

    ncols = len(cols)
    return f"""
    <div class="form-section">
      <div class="section-title">Joint measurement grid</div>
      <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
        The seventeen locations from the client's own form are seeded below.
        Add, rename or remove rows as the site needs. <b>Blank rows are not
        printed</b> &mdash; a ruled blank underneath a countersignature is an
        invitation to write on the document after it is signed.
        The columns come from <a href="{url_for('settings.edit_settings')}">Settings</a>
        and are <b>frozen onto this sheet when it is saved</b>.
      </p>
      <input type="hidden" name="grid_json" id="grid_json" value=""/>
      <div style="overflow-x:auto;">
        <table class="jg-table" id="jg-table">
          <thead><tr><th class="jg-loc">Location</th>{heads}
            <th class="jg-rem">Remarks</th><th></th></tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>
      <button type="button" class="btn btn-ghost" id="jg-add"
              style="margin-top:.7rem;">+ Add a location</button>
    </div>
    <script>
    (function () {{
      var NCOLS = {ncols};
      var KEYS = {P.json_for_script([c["key"] for c in cols])};
      var tbl = document.getElementById('jg-table');

      function rowHTML() {{
        var cells = '';
        for (var i = 0; i < NCOLS; i++) {{
          cells += '<td><input type="number" step="any" min="0" class="jg-in" '
                 + 'data-key="' + KEYS[i] + '"/></td>';
        }}
        return '<td><input type="text" class="jg-loc-in"/></td>' + cells
             + '<td><input type="text" class="jg-rem-in"/></td>'
             + '<td><button type="button" class="btn btn-ghost jg-del">&times;</button></td>';
      }}

      document.getElementById('jg-add').addEventListener('click', function () {{
        var tr = document.createElement('tr');
        tr.innerHTML = rowHTML();
        tbl.tBodies[0].appendChild(tr);
      }});

      tbl.addEventListener('click', function (e) {{
        if (e.target && e.target.classList.contains('jg-del')) {{
          var tr = e.target.closest('tr');
          if (tr) tr.parentNode.removeChild(tr);
        }}
      }});

      // Collected on submit, beside the picker's own payload. `saveJSON()` is
      // the picker's; this adds the grid without touching it.
      window.collectGrid = function () {{
        var out = [];
        var trs = tbl.tBodies[0].rows;
        for (var i = 0; i < trs.length; i++) {{
          var tr = trs[i];
          var loc = tr.querySelector('.jg-loc-in');
          var rem = tr.querySelector('.jg-rem-in');
          var vals = {{}};
          var ins = tr.querySelectorAll('.jg-in');
          for (var j = 0; j < ins.length; j++) {{
            var v = ins[j].value;
            if (v !== '' && v !== null) vals[ins[j].dataset.key] = v;
          }}
          out.push({{label: loc ? loc.value : '',
                     values: vals,
                     remarks: rem ? rem.value : ''}});
        }}
        document.getElementById('grid_json').value =
          JSON.stringify({{rows: out}});
        return true;
      }};
    }})();
    </script>"""


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


def _fmt_cell(v: float) -> str:
    """A grid cell. Zero prints blank — a nil measurement is not a nought."""
    return BQ._fmt_qty(v) if abs(v) > _QTY_EPSILON else ""


def _joint_grid_html(ms: dict) -> str:
    """The two-row table head, the location rows, and the TOTAL row."""
    cols = grid_columns_of(ms)
    rows = grid_rows_of(ms)
    totals = grid_totals(ms)

    # ── The two-row head. A column with no group spans both rows; a group
    #    draws a spanning cell above its members. Walked in column order so
    #    the group cell's colspan is whatever the settings list actually
    #    carries, rather than a number hardcoded from the client's sample.
    top, bottom, i = [], [], 0
    while i < len(cols):
        c = cols[i]
        group = str(c.get("group") or "")
        if not group:
            top.append(f'<th class="jm-num" rowspan="2">{P.esc(c["label"])}'
                       f'{_unit_html(c)}</th>')
            i += 1
            continue
        span = i
        while span < len(cols) and str(cols[span].get("group") or "") == group:
            span += 1
        top.append(f'<th colspan="{span - i}">{P.esc(group)}</th>')
        for c2 in cols[i:span]:
            bottom.append(f'<th class="jm-num">{P.esc(c2["label"])}'
                          f'{_unit_html(c2)}</th>')
        i = span

    body = ""
    for r in rows:
        cells = "".join(f'<td class="jm-num">{_fmt_cell(_cell(r, c["key"]))}</td>'
                        for c in cols)
        body += (f'\n        <tr><td class="jm-loc">{P.esc(r.get("label") or "")}</td>'
                 f'{cells}'
                 f'<td class="jm-rem">{P.esc(r.get("remarks") or "")}</td></tr>')

    total_cells = "".join(
        f'<td class="jm-num">{_fmt_cell(totals.get(c["key"], 0.0))}</td>'
        for c in cols)

    return f"""
    <table class="jm-grid">
      <thead>
        <tr>
          <th class="jm-loc" rowspan="2">Location</th>
          {''.join(top)}
          <th class="jm-rem" rowspan="2">REMARKS</th>
        </tr>
        <tr>{''.join(bottom)}</tr>
      </thead>
      <tbody>{body}
        <tr class="jm-total"><td class="jm-loc">TOTAL</td>{total_cells}
          <td class="jm-rem"></td></tr>
      </tbody>
    </table>"""


def _unit_html(col: dict) -> str:
    unit = str(col.get("unit") or "").strip()
    return f'<span class="jm-unit">({P.esc(unit)})</span>' if unit else ""


def _joint_document_html(ms: dict) -> str:
    """
    The JOINT MEASUREMENT SHEET — the client's own workbook layout.

    ⚠ **THE LETTERHEAD IS THE SHARED ONE AND NOTHING IS HAND-WRITTEN.**
      `DS.sheet_open()` is what the tax invoice, the PO, the proforma, the RA
      bill and the delivery challan all print, and the standing architectural
      rule is that a new document derived from an existing chain reuses the
      printed layout that already exists: separate behaviour, shared
      appearance. `tests/test_print_golden.py` asserts the DC's letterhead
      block hashes identically to the tax invoice's, and this sheet joins that
      set. The address comes from `/settings` through `B.COMPANY_ADDR`, read at
      render time — **never from a constant in this file**.

    ⚠ **NO BLANK FILLER ROWS.** The client's paper carries about ten ruled
      blanks between the last location and the TOTAL row. They are not printed.
      The delivery challan pass already took this decision on the argument that
      blank ruled rows underneath a signature invite post-signature insertion,
      and **this document is countersigned by the customer**, so the argument
      is stronger here than it was there. Flagged in the §0 block as still
      needing Yogesh's confirmation, exactly as the DC one does.

    ⚠ **Driven by the sheet's own stored rows and its own stored columns**,
      never re-read from `/settings` or from the live BOQ — CLIENT_CHANGES.md
      §1.2, and `print_ra()`'s original defect is why the rule exists.

    ⚠ **Nothing about approval reaches this page.** `approval.panel()`,
      `status_badge()` and `grandfather_marker()` are screen-only and
      `tests/test_approval_b7.py` renders every printed sheet and asserts the
      strings are absent.
    """
    site_label, site_source = site_of(ms)

    # The amber band, when the site is not the address book's own answer.
    # `project.site_drift()`'s shape — deliberately not a second design.
    drift = ""
    if site_source == "boq":
        drift = ('<div class="jm-drift"><span>&#9888;</span><span>'
                 '<b>This site is the free-text string on the schedule.</b> '
                 'The project it belongs to has no address-book site, so '
                 'nothing has been guessed at and it does not join to '
                 'anything.</span></div>')
    elif site_source == "none":
        drift = ('<div class="jm-drift"><span>&#9888;</span><span>'
                 '<b>No site is recorded against this sheet.</b> Its project '
                 'has no address-book site and the schedule carries no site '
                 'either.</span></div>')

    fields = [("SITE", site_label),
              ("SYSTEM", ms.get("system") or ""),
              ("MATERIAL", ms.get("material") or ""),
              ("DIA METER", ms.get("dia_meter") or ""),
              ("AREA", ms.get("area") or "")]
    field_html = "".join(
        f'<div class="jm-f-lbl">{P.esc(lbl)}</div>'
        f'<div class="jm-f-val">{P.esc(val)}</div>'
        for lbl, val in fields)

    sheet_cell = (
        DS._meta("Measurement No.", P.esc(ms.get("ref")))
        + DS._meta("Date", P.esc(ms.get("date")))
        + DS._meta("Against BOQ", P.esc(ms.get("boq_ref")))
        + DS._meta("Project", P.esc(ms.get("project_name"))))

    # ── The two-party sign-off. THE REASON THE DOCUMENT IS CALLED *JOINT*.
    #    It is countersigned by the main contractor's site engineer, and that
    #    structure is load-bearing: a measurement one party signed alone is not
    #    a joint measurement. The four label rows on each side stay blank for a
    #    wet signature.
    #
    # ⚠ The right-hand band takes the party from the BOQ's bill-to snapshot,
    #   and where the BOQ carries none it prints EMPTY rather than inventing a
    #   placeholder. A placeholder on a countersignature block is a name
    #   somebody might sign under.
    def _party(band_html, labels):
        rows = "".join(f'<div class="jm-srow"><div class="jm-slbl">{l}</div>'
                       f'<div class="jm-sval"></div></div>' for l in labels)
        return (f'<div class="jm-party"><div class="jm-band">{band_html}</div>'
                f'{rows}</div>')

    ours = _party(f'{B.name_html("lh-name-fire")}',
                  ("NAME", "DESIGNATION", "SIGNATURE", "DATE"))
    theirs = _party(P.esc(ms.get("account_name") or ""),
                    ("NAME", "DESIGN.", "SIGN.", "DATE"))

    note_html = ""
    if ms.get("notes"):
        note_html = (f'\n  <div class="ms-note"><b>Notes:</b> '
                     f'{P.esc(ms["notes"])}</div>')

    return f"""
<div class="quotation-doc ms-joint-outer">

{DS.sheet_open(title_band="JOINT MEASUREMENT SHEET")}

  <div class="doc-box">
    <div class="doc-header ms-2col">
      <div class="dh-cell">
        <div class="jm-fields">{field_html}</div>
      </div>
      <div class="dh-cell">{sheet_cell}</div>
    </div>
    {drift}
{_joint_grid_html(ms)}
  </div>{note_html}

  <div class="jm-sign">{ours}{theirs}</div>

{DS.sheet_close()}

</div>"""


def _document_html(ms: dict) -> str:
    """
    The printed measurement sheet — joint grid, or the legacy linear sheet.

    ⚠ **THE LEGACY BRANCH IS NOT DEAD CODE AND MUST NOT BE DELETED.** Two live
      sheets predate the joint model — `SF/MS/26-27/0001` (BOQ 0007, project
      *Banglore*) and `SF/MS/26-27/0002` (BOQ 0008, *Sify Bangalore*, 87 priced
      rows). Neither carries a location or a diameter as structured data:
      `location` is one free-text field on the record, not a property of a row.
      Neither maps onto the grid and migrating them would mean **inventing
      data**, so both are marked old-model and rendered here — the same
      treatment the day-rate migration gave the one old employee record.
      Nothing is deleted, nothing is reshaped, and both stay in the register.
    """
    return (_joint_document_html(ms) if is_joint(ms)
            else _legacy_document_html(ms))


def _legacy_document_html(ms: dict) -> str:
    """
    The linear measurement sheet, as it printed before 6 September 2026.

    Unchanged except for its name. Every sheet raised before the joint model
    renders through this and goes on looking exactly as it did.

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

    # ── The joint grid ─────────────────────────────────────────────────────
    #
    # ⚠ **THE COLUMN SET IS SNAPSHOTTED HERE, at create, and never re-read.**
    #   A later `/settings` edit must not restate a sheet somebody has already
    #   signed — the RA bill's own claim-row invariant, which has already
    #   shipped as a defect once in this repo.
    columns = default_columns()
    grid_rows, grid_error = parse_grid(data["grid_json"], columns)
    if grid_error:
        data["_chosen"] = None
        return _entry_form(boq, data, grid_error)

    site_label, site_source = _site_from_boq(boq)

    mid = new_id()
    record = {
        "id": mid,
        "ref": next_ref(data["date"]),
        "fy": P.fy_of(data["date"]),
        "date": data["date"],
        # ── The joint model, marked EXPLICITLY. `is_legacy_grid()` reads the
        #    absence of this as "written before the grid existed", and the mark
        #    is what keeps "no grid" and "predates grids" apart.
        "grid_model": GRID_MODEL_JOINT,
        "grid_columns": columns,
        "grid_rows": grid_rows,
        "system": data["system"],
        "material": data["material"],
        "dia_meter": data["dia_meter"],
        "area": data["area"],
        # SITE, inherited and snapshotted — `project.site_address`'s pattern.
        "site_label": site_label,
        "site_source": site_source,
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
  {DS.SHEET_STYLES}{MS_DOC_STYLES}{MS_JOINT_STYLES if is_joint(ms) else ''}
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
  {DS.SHEET_STYLES}{MS_DOC_STYLES}{MS_JOINT_STYLES if is_joint(ms) else ''}
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
                ("date", "location", "measured_by", "witnessed_by", "notes",
                 "system", "material", "dia_meter", "area")}
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

    # ⚠ **The columns are the sheet's OWN snapshot on an edit, never
    #   `/settings` again.** Re-reading settings here is exactly the defect the
    #   snapshot exists to prevent: it would restate an existing sheet's columns
    #   from whatever the list happens to say today. A legacy sheet being edited
    #   gains the joint model with the CURRENT settings columns, because it has
    #   no snapshot of its own to keep.
    columns = (grid_columns_of(ms) if is_joint(ms) else default_columns())
    grid_rows, grid_error = parse_grid(data["grid_json"], columns)
    if grid_error:
        return _entry_form(boq, data, grid_error, sheet=ms)

    ms.update({
        "date": data["date"],
        "location": data["location"],
        "measured_by": data["measured_by"],
        "witnessed_by": data["witnessed_by"],
        "notes": data["notes"],
        "items": _with_boq_qty(items, boq_id),
        "grid_model": GRID_MODEL_JOINT,
        "grid_columns": columns,
        "grid_rows": grid_rows,
        "system": data["system"],
        "material": data["material"],
        "dia_meter": data["dia_meter"],
        "area": data["area"],
    })
    # SITE is re-inherited on save, exactly as it is on create — the label is a
    # snapshot of the address book at the moment somebody saved, and re-saving
    # is the documented way to take a new one (`project.site_drift()`'s band
    # says so in those words).
    _lbl, _src = _site_from_boq(boq)
    ms["site_label"], ms["site_source"] = _lbl, _src
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
    GET confirms, POST deletes. Gated by `can_modify()` **and** `can_delete()`.

    ⚠ **The limitation this docstring used to record is now closed.** It said a
    sheet an installation claim had been built on was still deletable, and
    carried that into the pass report as an open question. `can_delete()` above
    is the answer, and it refuses **on both verbs** — a guard on POST alone
    would let the confirm page render an offer the app will not honour, which
    is ABOUT.md §7.9f's standing complaint about both-verb routes.
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

    # Layered on top of `can_modify()`, not folded into it: that function
    # answers "has this been signed off", this one answers "does anything
    # downstream rest on it". `ra.can_edit()` and `can_modify()` are paired the
    # same way.
    may_delete, why_not_delete = can_delete(ms)
    if not may_delete:
        return redirect(url_for("measurement.view_ms", id=id,
                                msg=why_not_delete, type="error"))

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
