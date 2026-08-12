"""
ra.py — Running Account Bills
=============================
The second link in the BOQ chain, and the module the client is actually paying
for:

    BOQ ──► RA bill 1 ──► RA bill 2 ──► …

A **BOQ** is the priced schedule of a project — what was approved. An **RA bill**
is a claim against it: for each line, how much of the approved quantity has been
executed this period, at what rate, and what remains unbilled. The client's own
annexure is nine of them against one 97-line schedule.

⚠ **AN RA BILL IS HEADED TAX INVOICE AND CARRIES A PER-LINE TAX BLOCK (DOMAIN.md §4).**

It carries party GSTINs, state codes, a tax invoice reference, main contractor's
PO/WO reference, per-line HSN/SAC codes, CGST/SGST (or IGST) tax amounts, a Rounding Off
adjustment, and stored monetary totals.

It must **not import `quotation._tax_lines()`** (which is document-level arithmetic)
nor `invoice.py`. `ra.py` computes its own per-line tax block. `tests/test_ra_record.py`
asserts this isolation at AST level.

What this module is built around
--------------------------------
**The over-claim block.** A cumulative claim across every RA bill must never
exceed the approved BOQ quantity for that line. Their live spreadsheet has three
lines already billed into negative balance, and catching that is what this
system was sold to do. The block is hard: there is no override anywhere in the
UI, and `OVERCLAIM_TOLERANCE` is the only dial, defaulting to zero.

**The revision chain.** Because the block is hard, the only way through it when
the approved schedule genuinely changes is a BOQ *revision* -- a new BOQ record
carrying `supersedes`. Claims therefore have to be summed across the whole
chain, or a revision would silently reset every line's claimed quantity to zero
and the block would guard nothing. `claimed_by_line()` is that sum and is the
single place anything asks the question.

Import direction
----------------
    ra.py ──► boq.py        _line_id, _item_no, _num, _opt_num — the schedule's
                            own guards, and the key a claim is matched on
    ra.py ──► dashboard.py  BASE_STYLES / _nav
    ra.py ──► pipeline.py   esc / parse_money / fy_of / fy_ref
    ra.py ──► store, branding

`boq.py` must **never** import this module — its view page links out with
`url_for` and reads `STORE["ra_bills"]` directly, the same one-way trick used
four times already. It must not import `proforma.py`, `invoice.py`,
`purchase.py` or `product.py` either.
"""

import json
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import boq as BQ
import branding as B
import pipeline as P
from dashboard import BASE_STYLES, _nav
from store import STORE

# The form's widgets and page furniture, exactly as boq.py takes them, so the
# two forms are the same form. `_tax_lines` is deliberately NOT among them and
# never will be — an RA bill is a claim document, not a tax invoice, and
# `tests/test_ra_record.py` asserts the absence at AST level.
from quotation import QUOTATION_STYLES, VIEW_DOC_STYLES, _inr, _amount_in_words

ra_bp = Blueprint("ra", __name__, url_prefix="/ra")

# =============================================================================
# BUSINESS RULES — module-level constants, never buried in a branch
# =============================================================================

# The two billing legs. One integer RA sequence per project covers both: the
# client's own run is supply on 1,2,3,5,7,9 and installation on 4,6,8, which is
# ONE series whose bills happen to alternate, not two interleaved series.
LEGS = ("supply", "installation")

# How much a CUMULATIVE claim may exceed the approved BOQ quantity, as a
# fraction of it. 0.0 is a pure hard block and is the default.
#
# Three things about this constant are the whole point:
#
#   1. At 0.0 the behaviour is EXACTLY a hard block. No epsilon, no "close
#      enough", no special case. Tested at 0.0 and at 0.01.
#   2. It applies to the CUMULATIVE claim, never per bill. A 1% per-bill
#      allowance compounds to 9% across the client's nine RA runs and becomes
#      the over-claim it exists to prevent. Cumulative is the only place it can
#      live without defeating itself.
#   3. There is NO UI for it. Not a field, not a query parameter, not a per-line
#      tick box. Changing it is a deliberate edit here, the `REQUIRE_PO_FOR_WON`
#      precedent (ABOUT.md §9).
#
# Why it exists at zero: two of the three over-claims in the client's live sheet
# are 0.06 on a quantity of 12 — 0.5%, site-measurement rounding on a pipe run —
# and the third is 11.54 on 35, which is a real over-claim. Whether the first
# two should pass is a commercial decision, so it gets a named dial rather than
# a number buried in a comparison.
OVERCLAIM_TOLERANCE = 0.0

# IEEE-754 hygiene, and deliberately NOT a commercial tolerance. Summing
# 1.1 + 2.2 + 8.7 gives 12.000000000000002, and reporting that as an over-claim
# of two femtometres against an approved 12 would be a bug. Six orders of
# magnitude below the two decimal places real quantities carry, so it cannot
# absorb anything a human would call an over-claim.
_QTY_EPSILON = 1e-6

# Rates are money at two decimal places; half a paisa apart is the same rate.
_RATE_EPSILON = 0.005

# The three states a bill moves through. `draft` is ours, `submitted` means it
# has gone to the main contractor, `certified` means he has said what he allows.
# Certification data can arrive on a bill in any of them — see CERTIFICATION.
STATUSES = ("draft", "submitted", "certified")

# The most claim lines one RA bill may post.
#
# DERIVED from boq.MAX_LINES rather than chosen, and that relationship is the
# point: the RA form renders every line of the approved BOQ, so a BOQ that is
# legal at 600 lines must produce an RA post that is legal at 600 lines. A
# smaller number here would make a valid BOQ unbillable through its own form.
MAX_RA_LINES = BQ.MAX_LINES

# The most bytes of `ra_json` one RA bill may post, measured on the DECODED
# string as `request.form` hands it back.
#
# **Measured, not copied from boq.py.** An RA line carries no specification
# text — just an opaque id, a quantity and a rate — so the byte budget is a
# different problem from the BOQ's. Against the seeded 97-line Sify schedule
# (87 priced lines), every line filled:
#
#     JSON decoded        6,896 B   ->   79.3 B/line
#     URL-encoded on wire 11,084 B  ->  127.4 B/line   (1.61x expansion)
#
# A BOQ line measures 701 B/line, so an RA line is ~8.8x smaller. The 1.61x
# expansion is *worse* than the BOQ's observed 1.36-1.51x, because an RA line
# is almost entirely punctuation and short numerals with no prose to dilute the
# percent-escaping — which is exactly why the constant is measured rather than
# scaled from boq's.
#
# At the line cap: 600 x 79.3 = 46 KB decoded, 75 KB on the wire. Step 3 adds
# certified quantity and rate to the posted line, roughly doubling it to
# ~130 B/line, so ~78 KB decoded at the cap.
#
# 150,000 is therefore ~3.2x the worst honest payload at today's line cap and
# ~1.9x it once certification posts, while 150,000 x 1.61 = 241,500 bytes on
# the wire leaves ~258 KB of Flask's 500,000 MAX_FORM_MEMORY_SIZE for the
# twenty other form fields. The check always fires before Werkzeug does.
#
# ⚠ Not a security boundary, exactly as boq.MAX_JSON_BYTES is not. It is a
#   usability boundary: it keeps an honest RA bill from ever hitting the wall
#   where the 413 handler takes the editor away.
MAX_RA_JSON_BYTES = 150_000

_REF_SERIES = "RA"

# No 16-character cap. That is Rule 46(b)'s limit on a TAX INVOICE number, and
# this document is not one. The series still has to be unique and
# non-repeating, because it is the key a payment gets filed against.
_REF_CAP = 64


# =============================================================================
# THE RECORD
# =============================================================================
#
# STORE["ra_bills"][uuid] = {
#   "id": uuid,
#   "ref": "SF/RA/26-27/0004",   # OUR document number. Not a statutory serial.
#   "fy": "26-27",
#   "date": "2026-08-05",
#
#   # Which revision this was measured against. An issued bill's basis must
#   # never move, so the id is to a SPECIFIC revision and the ref/rev are
#   # stored rather than looked up — the bill still prints correctly as a
#   # historical document if the BOQ is removed.
#   "boq_id": uuid, "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
#
#   "ra_no": 5,                  # the client's sequence within the project
#   "leg": "supply" | "installation",
#
#   # Copied from the BOQ at issue, for the same reason.
#   "project_name": str, "site_location": str,
#   "account_name": str, "contact_person": str, "to": str, "bill_gstin": str,
#
#   "claims": [ ...see below... ],
#   "claim_subtotal": float,
#   "deductions": [ {code, label, basis, pct, amount} ],
#   "deduction_total": float,
#   "net_payable": float,        # claim_subtotal - deduction_total, ALWAYS
#
#   "notes": str, "company_branch": str, "auth_signatory": str,
# }
#
# A claim row:
#
#   {"line_id": "a3f19c0b7e42",  # THE MATCH KEY — opaque, from the BOQ line
#    "item_no": "24.b",          # the DISPLAY label; not unique, never matched on
#    "section": "B",
#    "description": str, "unit": "Mtrs",
#    "approved_qty": 700.0,      # frozen: the BOQ quantity when this was issued
#    "approved_rate": 2024.0,    # frozen
#    "prev_qty": 120.0,          # cumulative claimed BEFORE this bill, frozen
#    "qty": 80.0,                # claimed in THIS bill
#    "rate": 2024.0,             # as entered — may differ from approved_rate
#    "amount": 161920.0,         # qty * rate, always computed
#    "balance_qty": 500.0,       # approved - prev - this, frozen
#    "rate_varies": False}       # rate != approved_rate at issue
#
# Five properties this shape exists to guarantee:
#
# 1. **The figures are frozen.** `approved_qty`, `approved_rate`, `prev_qty` and
#    `balance_qty` are stored, not recomputed at render. RA3 stated a balance
#    that was true on its date, and issuing RA5 must not rewrite a document the
#    client has already certified — exactly `proforma.prior_invoiced`'s rule.
#    The GUARD at entry uses the live figures; the DOCUMENT uses the frozen ones.
# 2. **`rate` is stored as entered and may disagree with `approved_rate`.** It
#    does on 10 cells of the client's own annexure. Rates legitimately move on
#    approved variations, so this warns and never blocks — but a rate silently
#    disagreeing with the approved BOQ is one of the two failure modes this
#    system was sold to catch, so `rate_varies` is a stored fact about the bill.
# 3. **`deductions` is bill-level and exists from day one, empty.** Retention,
#    mobilisation-advance recovery and cess all fit one shape. `amount` is
#    always stored — computed from `pct` when the basis is a percentage — so a
#    certified bill cannot change its own figures later.
# 4. **`net_payable == claim_subtotal - deduction_total`, always**, including on
#    every bill with an empty deductions list.
# 5. **`ra_no` is unique across the whole REVISION CHAIN**, not per record. A
#    revision must not restart the client's sequence at RA1.
# 6. **`line_id` is what a claim is matched on, and `item_no` never is.** Item
#    numbers restart per section and the client's own schedule repeats one
#    inside a section, so matching on them collapsed ten lines together and
#    broke the guard in both directions at once. The id is opaque, minted by
#    `boq._new_line_id()`, and carried forward unchanged across revisions —
#    which is what lets a revision renumber freely without detaching history.


# =============================================================================
# THE REVISION CHAIN
# =============================================================================

def revision_chain(boq_id: str) -> list:
    """
    Every BOQ id in this BOQ's revision chain, oldest first.

    A revision is a new BOQ record carrying `supersedes: <previous id>`, never
    an edit — an issued RA bill is measured against a specific revision and its
    basis must not move. So "the claims against this project" is not "the
    claims against this record", and every question this module asks has to be
    asked of the chain.

    Walks back to the root, then forward collecting descendants. Both walks
    carry a seen-set: a `supersedes` cycle is not reachable through any route
    that exists, but a hand-edited record must not be able to hang a page — the
    same judgement `product._render_tree()` makes about its BOM.

    A fork (two revisions claiming the same parent) should not happen and is
    not rejected here; the descendants are ordered by `rev_no` then id so the
    answer is at least deterministic.
    """
    boqs = STORE.get("boqs") or {}
    if boq_id not in boqs:
        return []

    seen = set()
    cur = boq_id
    while cur not in seen:
        seen.add(cur)
        prev = str((boqs.get(cur) or {}).get("supersedes") or "")
        if not prev or prev not in boqs or prev in seen:
            break
        cur = prev
    root = cur

    chain = [root]
    frontier = [root]
    collected = {root}
    while frontier:
        children = []
        for parent in frontier:
            for rid, b in boqs.items():
                if rid in collected:
                    continue
                if str(b.get("supersedes") or "") == parent:
                    collected.add(rid)
                    children.append(rid)
        children.sort(key=lambda r: (int((boqs[r] or {}).get("rev_no") or 0), r))
        chain.extend(children)
        frontier = children
    return chain


def latest_revision(boq_id: str) -> str:
    """The id of the newest revision in this BOQ's chain, or ""."""
    chain = revision_chain(boq_id)
    return chain[-1] if chain else ""


# =============================================================================
# APPROVED vs CLAIMED — the two halves of the block
# =============================================================================

def approved_by_line(boq_id: str) -> dict:
    """
    {(line_id, leg): approved_qty} from the LATEST revision in the chain.

    **Keyed on `line_id`, not `item_no`.** `item_no` is a display label and is
    not unique: it restarts per section, and the client's own section A carries
    item `17` twice on two different items priced eight times apart. Keying
    here collapsed 87 priced lines into 77 guard entries and made the block both
    too loose and too tight on the same schedule — Rs 1,99,122.50 of over-claim
    permitted and Rs 84,071.00 of legitimate claim refused. `boq._new_line_id()`
    is what fixed it; `tests/test_boq_line_ids.py` holds the arithmetic.

    The latest revision, not the one billed against: a revision exists precisely
    to change what is approved, and the block has to be measured against what is
    approved *now*. What each issued bill was measured against is frozen on its
    own claim rows.

    Both legs get the line's `total_qty`. A BOQ line carries one quantity and
    two rates (§3), and the client's annexure tracks a separate balance for
    each leg against that same quantity — 11 lines are claimed on both.
    Specification headers carry no quantity and are skipped.
    """
    latest = latest_revision(boq_id)
    if not latest:
        return {}
    boq = (STORE.get("boqs") or {}).get(latest) or {}

    out = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        lid = BQ._line_id(li.get("line_id"))
        if not lid:
            continue
        qty = float(li.get("total_qty") or 0.0)
        for leg in LEGS:
            out[(lid, leg)] = qty
    return out


def approved_rates(boq_id: str) -> dict:
    """{(line_id, leg): approved_rate} from the latest revision."""
    latest = latest_revision(boq_id)
    if not latest:
        return {}
    boq = (STORE.get("boqs") or {}).get(latest) or {}

    out = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        lid = BQ._line_id(li.get("line_id"))
        if not lid:
            continue
        out[(lid, "supply")] = float(li.get("supply_rate") or 0.0)
        out[(lid, "installation")] = float(li.get("install_rate") or 0.0)
    return out


def approved_labels(boq_id: str) -> dict:
    """
    {line_id: item_no} from the latest revision — the DISPLAY label.

    The guard keys on `line_id`; every message a human reads still says
    "Item 24.d", because that is what is written on the measurement sheet in
    their hand. Nothing outside the code ever sees a line id.
    """
    latest = latest_revision(boq_id)
    if not latest:
        return {}
    boq = (STORE.get("boqs") or {}).get(latest) or {}
    out = {}
    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            out[lid] = BQ._item_no(li.get("item_no"))
    return out


def claimed_by_line(boq_id: str, exclude_ra_id: str = None) -> dict:
    """
    {(line_id, leg): qty} summed over every RA bill in the revision chain.

    **This is the single place anything asks how much has been claimed**, and it
    is derived rather than stored on purpose. A maintained counter has to be
    updated on every create, revision and delete, and any path that misses one
    leaves the number silently wrong — and this number *is* the over-claim
    guard, so a stale one is worse than none because it is trusted.

    It costs a pass over the claim rows: ~620 of them at the client's present
    volume (9 bills × 69 claimed lines), which is microseconds. It stays cheap
    to roughly 50,000 rows, about 80× where they are.

    `exclude_ra_id` leaves one bill out, so an edit can ask "what would the
    cumulative be without my own current figures in it".

    **Keyed on `line_id`.** A claim row carrying no id matches nothing and is
    skipped rather than falling back to `item_no` — a fallback would resurrect
    exactly the collapse this key exists to end, on the lines where item numbers
    are ambiguous, and would do it silently. `boq.backfill_line_ids()` counts
    such rows so they are visible instead.
    """
    ids = set(revision_chain(boq_id))
    if not ids:
        return {}

    out = {}
    for rid, bill in (STORE.get("ra_bills") or {}).items():
        if exclude_ra_id and rid == exclude_ra_id:
            continue
        if str(bill.get("boq_id") or "") not in ids:
            continue
        leg = bill.get("leg")
        for c in bill.get("claims") or []:
            lid = BQ._line_id(c.get("line_id"))
            if not lid:
                continue
            key = (lid, leg)
            out[key] = out.get(key, 0.0) + float(c.get("qty") or 0.0)
    return out


def claims_by_line_id(boq_id: str) -> dict:
    """
    {line_id: [ra_no, …]} — which bills have claimed against each line.

    Built for `boq.revision_blockers()`, which must refuse to delete a line that
    already carries a claim. It is passed *in* to that function rather than
    imported by it, because boq.py may never import this module (ABOUT.md §2b).
    """
    ids = set(revision_chain(boq_id))
    if not ids:
        return {}

    out = {}
    for _rid, bill in (STORE.get("ra_bills") or {}).items():
        if str(bill.get("boq_id") or "") not in ids:
            continue
        ra_no = int(bill.get("ra_no") or 0)
        for c in bill.get("claims") or []:
            lid = BQ._line_id(c.get("line_id"))
            if not lid or float(c.get("qty") or 0.0) <= 0:
                continue
            out.setdefault(lid, [])
            if ra_no not in out[lid]:
                out[lid].append(ra_no)
    return out


def bills_of(boq_id: str) -> list:
    """Every RA bill in the chain, ordered by ra_no. (id, bill) pairs."""
    ids = set(revision_chain(boq_id))
    rows = [(rid, b) for rid, b in (STORE.get("ra_bills") or {}).items()
            if str(b.get("boq_id") or "") in ids]
    rows.sort(key=lambda kv: int(kv[1].get("ra_no") or 0))
    return rows


def next_ra_no(boq_id: str) -> int:
    """
    The next RA number for this project — max+1 across the whole chain.

    Chain-scoped, so a revision cannot restart the client's sequence at RA1.
    max+1 rather than len+1 is `proforma._next_ref()`'s rule: a gap must never
    re-issue a number that has already been on a certified claim.

    The user never types this. That is what makes "RA5 before RA4" and "two
    RA6s" impossible rather than merely rejected — there is no input to reject.
    """
    highest = 0
    for _rid, b in bills_of(boq_id):
        highest = max(highest, int(b.get("ra_no") or 0))
    return highest + 1


def next_ref(datestr: str) -> str:
    """
    Next RA document number — 'SF/RA/26-27/0004'.

    FY-scoped and max+1 within the year, sharing `pipeline.fy_of` / `fy_ref`
    with the BOQ, the PO and the tax invoice. **No 16-character cap and no
    statutory meaning**: this is a claim document, not a tax invoice.
    """
    fy = P.fy_of(datestr)
    highest = 0
    for b in (STORE.get("ra_bills") or {}).values():
        if b.get("fy") != fy:
            continue
        tail = str(b.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=_REF_CAP)


# =============================================================================
# THE BLOCK
# =============================================================================

def rate_varies(rate, approved_rate) -> bool:
    """
    Does this claim rate disagree with the approved BOQ rate for the line?

    A warning, never a block — rates legitimately move on approved variations,
    and the client's own annexure carries ten cells where they do. But a rate
    that silently disagrees with the approved schedule is one of the two things
    this system exists to catch, so it is surfaced at entry and stored on the
    row rather than left to be noticed.
    """
    return abs(float(rate or 0.0) - float(approved_rate or 0.0)) > _RATE_EPSILON


def overclaims(boq_id: str, leg: str, claims: list,
               exclude_ra_id: str = None) -> list:
    """
    Every claim row that would breach the approved quantity. Empty is a pass.

    The hard block. Each entry is a dict carrying the whole arithmetic —
    approved, previously claimed, this claim, cumulative, allowed and the
    overage — because "line 24.d is over" is not something anyone can act on and
    "35 approved, 46.54 claimed, 11.54 over" is.

    Two reasons a row appears:

    - `"overclaim"` — cumulative would exceed the approved quantity.
    - `"not_in_boq"` — the line is not in the approved schedule at all, so
      there is no quantity to claim against. Reported here rather than
      elsewhere because it is the same answer: this claim is not permitted
      against the approved BOQ.

    The comparison rounds at `_QTY_EPSILON` to kill float noise. With
    `OVERCLAIM_TOLERANCE` at 0.0 this is exactly `cumulative > approved`.

    Matching is on `line_id`; `item_no` is carried into the message as the
    label the operator reads off their measurement sheet. A claim posted with
    no id, or an id absent from the approved revision, is `"not_in_boq"` — the
    same answer, because in both cases there is no approved quantity to claim
    against.
    """
    approved = approved_by_line(boq_id)
    prior = claimed_by_line(boq_id, exclude_ra_id=exclude_ra_id)
    labels = approved_labels(boq_id)

    out = []
    for c in claims or []:
        lid = BQ._line_id(c.get("line_id"))
        qty = float(c.get("qty") or 0.0)
        if qty <= 0:
            continue

        # The label the human sees: the approved revision's item number where
        # the line is known, otherwise whatever the claim carried.
        item = labels.get(lid) or BQ._item_no(c.get("item_no"))

        key = (lid, leg)
        if not lid or key not in approved:
            out.append({"item_no": item, "line_id": lid, "leg": leg,
                        "reason": "not_in_boq",
                        "approved": 0.0, "previously": prior.get(key, 0.0),
                        "this": qty, "cumulative": qty, "allowed": 0.0,
                        "over": qty})
            continue

        app = approved[key]
        previously = prior.get(key, 0.0)
        cumulative = previously + qty
        allowed = app * (1.0 + OVERCLAIM_TOLERANCE)
        if round(cumulative - allowed, 6) > _QTY_EPSILON:
            out.append({"item_no": item, "line_id": lid, "leg": leg,
                        "reason": "overclaim",
                        "approved": app, "previously": previously,
                        "this": qty, "cumulative": cumulative,
                        "allowed": allowed, "over": cumulative - allowed})
    return out


def overclaim_message(v: dict) -> str:
    """One over-claim, in words the person entering it can act on."""
    if v["reason"] == "not_in_boq":
        return (f"Item {v['item_no']} is not in the approved BOQ, so there is "
                f"nothing to claim against it.")
    q = BQ._fmt_qty
    return (f"Item {v['item_no']} ({v['leg']}): {q(v['approved'])} approved, "
            f"{q(v['previously'])} already claimed on earlier RA bills, "
            f"{q(v['this'])} claimed here — that is {q(v['cumulative'])} in "
            f"total, {q(v['over'])} over.")


# =============================================================================
# ARITHMETIC
# =============================================================================

def compute_deductions(deductions: list, claim_subtotal: float) -> tuple:
    """
    (rows, total) — every deduction with its `amount` resolved.

    A percentage deduction's amount is computed **once, here, and stored**, so
    the printed document never recomputes it and a certified bill cannot change
    its own figures when a constant moves later. Same rule as `supply_rate` on a
    BOQ line and `prior_invoiced` on a proforma.

    Empty in Phase 1 and that is expected — the shape exists so that retention,
    mobilisation-advance recovery and cess drop in without the print format or
    the balance arithmetic having to be reopened.
    """
    rows, total = [], 0.0
    for d in deductions or []:
        basis = str(d.get("basis") or "amount")
        pct = float(d.get("pct") or 0.0)
        if basis == "percent":
            amount = round(claim_subtotal * pct / 100.0, 2)
        else:
            amount = round(float(d.get("amount") or 0.0), 2)
        rows.append({"code": str(d.get("code") or "").strip(),
                     "label": str(d.get("label") or "").strip(),
                     "basis": basis, "pct": pct, "amount": amount})
        total += amount
    return rows, round(total, 2)


def bill_totals(claims: list, deductions: list) -> tuple:
    """(claim_subtotal, deduction_rows, deduction_total, net_payable)."""
    subtotal = round(sum(float(c.get("amount") or 0.0) for c in claims or []), 2)
    rows, total = compute_deductions(deductions, subtotal)
    return subtotal, rows, total, round(subtotal - total, 2)


def compute_rounding_off(unrounded_total: float) -> tuple:
    """
    (rounding_off, rounded_grand_total)

    Rounds unrounded_total to nearest whole rupee. Delta is stored as rounding_off.
    """
    grand = float(round(unrounded_total))
    rounding = round(grand - unrounded_total, 2)
    return rounding, grand


def _declared_rate(tax_type: str, cgst_rate: float, sgst_rate: float,
                   igst_rate: float) -> float:
    """
    The single GST rate the BILL declares, as the form states it.

    Only ever a **fallback** for a claim row that does not carry its own
    `gst_rate` — see `_gst_rate_of`. Under `cgst_sgst` the declared rate is the
    two halves added back together, because 9 + 9 is an 18% supply.
    """
    if str(tax_type or "").strip().lower() == "igst":
        return float(igst_rate or 0.0)
    return float(cgst_rate or 0.0) + float(sgst_rate or 0.0)


def _gst_rate_of(claim: dict, fallback: float) -> float:
    """
    The rate one claim row is taxed at — its own `gst_rate`, or the bill's.

    `build_claim()` has always snapshotted `gst_rate` off the BOQ line, so every
    row this app has ever written carries one. The fallback exists for rows that
    predate the field or were built by hand: they are taxed at the bill-level
    rate, which is **exactly what they got before this function read the field
    at all**. That is what lets per-line rates land with no migration and no
    change to a single stored bill.

    ⚠ A rate of **0.0 that is actually present is honoured as 0%**, not treated
      as missing. Nil-rated work is a real slab, and `build_claim()` cannot
      produce a stored 0.0 by accident — it folds a falsy BOQ rate to 18.0 —
      so a zero here was put there on purpose.
    """
    raw = claim.get("gst_rate")
    if raw is None or raw == "":
        return fallback
    try:
        return round(float(raw), 3)
    except (TypeError, ValueError):
        return fallback


def _head_split(tax_type: str, rate: float) -> tuple:
    """
    (cgst_rate, sgst_rate, igst_rate) for one slab — the HEAD, unchanged.

    **This function decides nothing.** Which head applies is `tax_type`, which
    comes off the bill exactly as it always has; all this does is split one
    slab's rate across it. An 18% intra-state supply is CGST 9 + SGST 9; the
    same supply inter-state is IGST 18.

    ⚠ Whether a given bill is intra- or inter-state is **still not derived
      anywhere** — see ABOUT.md §7 gap 15. `tax_type` defaults to `cgst_sgst`
      and no form offers the choice. That question is open pending the client's
      CA and is deliberately untouched here.

    Any other `tax_type` yields no tax at all, which is what the bill-level
    arithmetic did before this change and is preserved rather than tidied.
    """
    tax_type = str(tax_type or "").strip().lower()
    if tax_type == "cgst_sgst":
        half = rate / 2.0
        return half, half, 0.0
    if tax_type == "igst":
        return 0.0, 0.0, rate
    return 0.0, 0.0, 0.0


def tax_slabs(claims: list, tax_type: str = "cgst_sgst", cgst_rate: float = 9.0,
              sgst_rate: float = 9.0, igst_rate: float = 18.0) -> list:
    """
    The bill's claim rows grouped by the GST rate each one stores.

    One row per distinct rate, ascending, carrying the taxable value, the head
    split, the tax, and the distinct HSN/SAC codes that fall in it — which is
    the shape a rate-wise tax table on the document wants, and the shape a
    GSTR-1 HSN summary will want later (§7 gap 9c).

    The per-slab amounts here are rounded to the paisa **for display**. The
    document's own totals are NOT summed from them — `compute_tax_totals()`
    rounds once, from the unrounded values, so that accumulated per-slab
    rounding cannot drift the grand total against the claim subtotal.
    """
    fallback = _declared_rate(tax_type, cgst_rate, sgst_rate, igst_rate)

    buckets = {}
    for c in claims or []:
        rate = _gst_rate_of(c, fallback)
        b = buckets.setdefault(rate, {"taxable": 0.0, "hsn": set(), "lines": 0})
        b["taxable"] += float(c.get("amount") or 0.0)
        b["lines"] += 1
        code = str(c.get("hsn_sac") or "").strip()
        if code:
            b["hsn"].add(code)

    slabs = []
    for rate in sorted(buckets):
        b = buckets[rate]
        taxable = round(b["taxable"], 2)
        c_r, s_r, i_r = _head_split(tax_type, rate)
        slabs.append({
            "gst_rate":      rate,
            "taxable_value": taxable,
            "cgst_rate":     c_r,
            "sgst_rate":     s_r,
            "igst_rate":     i_r,
            "cgst_amount":   round(taxable * c_r / 100.0, 2),
            "sgst_amount":   round(taxable * s_r / 100.0, 2),
            "igst_amount":   round(taxable * i_r / 100.0, 2),
            # The slab's own total is its heads ADDED, not the rate applied
            # again. `round(x * 18/100)` and `2 x round(x * 9/100)` can differ
            # by a paisa, and if they do it is the printed slab row that stops
            # footing against the CGST and SGST totals underneath it.
            "tax_amount":    round(round(taxable * c_r / 100.0, 2)
                                   + round(taxable * s_r / 100.0, 2)
                                   + round(taxable * i_r / 100.0, 2), 2),
            "hsn_sac":       sorted(b["hsn"]),
            "line_count":    b["lines"],
        })
    return slabs


def compute_tax_totals(claims: list, deductions: list, tax_type: str = "cgst_sgst",
                       cgst_rate: float = 9.0, sgst_rate: float = 9.0,
                       igst_rate: float = 18.0) -> dict:
    """
    claim_subtotal, deductions, net_payable, tax, rounding_off and grand_total.

    **Tax is computed per RATE SLAB, off the `gst_rate` each claim row stores.**
    `build_claim()` has snapshotted that field since the record shape was
    written; until this function read it, the bill-level `cgst_rate` /
    `sgst_rate` / `igst_rate` were applied to every line regardless. That was
    right on a single-rate bill and wrong on one mixing 18% goods with 12% or
    5% work — wrong on a statutory document (ABOUT.md §7 gap 14).

    What did **not** change, and must not be changed here:

    - **The head.** `tax_type` still decides CGST+SGST versus IGST, still
      defaults to `cgst_sgst`, and is still not derived from a place of supply.
      Gap 15 is open pending the client's CA. `_head_split()` only splits a rate
      across the head it is given.
    - **Every existing key**, and what it means. `tax_slabs` is added alongside.
    - **Stored bills.** Nothing here recomputes one; `print_ra()` renders the
      frozen figures off the record, as it always has.

    ⚠ **Rounded once PER SLAB, then summed.** `cgst_amount` / `sgst_amount` /
      `igst_amount` are the sums of the rounded slab figures, so the rate-wise
      column on the printed sheet adds up to the document total exactly. That
      is a GSTR-1 requirement, not a preference: the return is filed rate-wise
      and the document is what those lines are read off. See the note at the
      arithmetic below for why this beats rounding once at document level.

      It is still exactly **one** rounding per slab. The old per-LINE rounding
      accumulated 87 of them on the seeded schedule and is what neither scheme
      may go back to.

    Identity: `grand_total == net_payable + tax_amount + rounding_off`.
    """
    subtotal, drows, dtotal, net_payable = bill_totals(claims, deductions)
    tax_type = str(tax_type or "cgst_sgst").strip().lower()

    slabs = tax_slabs(claims, tax_type, cgst_rate, sgst_rate, igst_rate)

    # ROUND PER SLAB, then sum the ROUNDED slabs — so the rate-wise column on
    # the printed sheet adds up to the document total, exactly.
    #
    # This is the reverse of what this function did when per-slab tax first
    # landed, and the reason is GSTR-1. The return is filed **rate-wise**: each
    # slab's taxable value and tax are reported as their own line, and the
    # document is the source those lines are read off. If the slab figures are
    # display roundings of numbers the total was never computed from, the
    # document's own column does not foot — and a tax invoice whose CGST column
    # does not add to its CGST total is a document that gets queried.
    #
    # The paise this gives up are the smaller cost. Rounding once at document
    # level is arithmetically tighter by up to a paisa per slab, but it is
    # tighter against a figure nobody files, and it makes the filed figures
    # inconsistent with the sheet they came from.
    #
    # ⚠ It stays exactly ONE rounding per slab. The old per-LINE rounding — 87
    #   of them accumulating on the seeded schedule — is what this must not go
    #   back to, and the pinned literals in `tests/test_ra_tax_slabs.py` are
    #   what hold it. A single-slab bill is arithmetically identical either way
    #   (one term to round), which is why every figure the client has actually
    #   been sent is untouched by this change.
    cgst_amount = round(sum(s["cgst_amount"] for s in slabs), 2)
    sgst_amount = round(sum(s["sgst_amount"] for s in slabs), 2)
    igst_amount = round(sum(s["igst_amount"] for s in slabs), 2)
    tax_amount = round(cgst_amount + sgst_amount + igst_amount, 2)

    raw_total = net_payable + tax_amount
    rounding_off, grand_total = compute_rounding_off(raw_total)

    # The document-level rates keep their existing meaning: what the tax line on
    # the sheet is labelled with. On a single-slab bill that is the slab, so a
    # 12% bill can no longer print "CGST @ 9%" over an amount charged at 6% —
    # which is what echoing the form back would now do, since the line rate is
    # the one the amount is computed from. With no slabs, or with more than one,
    # there is no single rate to state and the declared values stand; the
    # rate-wise table is what a multi-slab document prints instead.
    if len(slabs) == 1:
        out_cgst_rate = slabs[0]["cgst_rate"] or float(cgst_rate)
        out_sgst_rate = slabs[0]["sgst_rate"] or float(sgst_rate)
        out_igst_rate = slabs[0]["igst_rate"] or float(igst_rate)
    else:
        out_cgst_rate = float(cgst_rate)
        out_sgst_rate = float(sgst_rate)
        out_igst_rate = float(igst_rate)

    return {
        "claim_subtotal": subtotal,
        "deductions": drows,
        "deduction_total": dtotal,
        "net_payable": net_payable,
        "tax_type": tax_type,
        "cgst_rate": out_cgst_rate,
        "sgst_rate": out_sgst_rate,
        "igst_rate": out_igst_rate,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "tax_amount": tax_amount,
        "tax_slabs": slabs,
        "rounding_off": rounding_off,
        "grand_total": grand_total,
    }


def previous_bill_po_defaults(boq_id: str) -> tuple:
    """(po_ref, po_date) from the most recent bill for this BOQ, or ('', '')."""
    rows = bills_of(boq_id)
    if not rows:
        return "", ""
    prev_bill = rows[-1][1]
    return str(prev_bill.get("po_ref") or ""), str(prev_bill.get("po_date") or "")


def build_claim(boq_line: dict, qty, rate, prev_qty: float,
                approved_rate: float, leg: str = "supply",
                hsn_sac: str = None, gst_rate: float = None) -> dict:
    """
    One claim row, with every figure that has to survive on the document frozen.

    `amount` is always computed from qty × rate, so a stored amount can never
    disagree with the figures printed beside it — `boq._clean_lines()` makes the
    same call about its own amounts.

    **`item_no` and `hsn_sac` are SNAPSHOTS, taken here and never re-derived.**
    """
    q = float(BQ._num(qty, 0.0))
    r = float(BQ._num(rate, 0.0))
    approved_qty = float(boq_line.get("total_qty") or 0.0)

    if hsn_sac is None:
        hsn_sac = str(boq_line.get("install_sac" if leg == "installation" else "supply_hsn") or "").strip()
    if gst_rate is None:
        gst_rate = float(boq_line.get("install_gst_rate" if leg == "installation" else "supply_gst_rate") or 18.0)

    return {
        "line_id":       BQ._line_id(boq_line.get("line_id")),
        "item_no":       BQ._item_no(boq_line.get("item_no")),
        "section":       str(boq_line.get("section") or ""),
        "description":   str(boq_line.get("description") or ""),
        "unit":          str(boq_line.get("unit") or ""),
        "hsn_sac":       hsn_sac,
        "gst_rate":      gst_rate,
        "approved_qty":  approved_qty,
        "approved_rate": float(approved_rate or 0.0),
        "prev_qty":      float(prev_qty or 0.0),
        "qty":           q,
        "rate":          r,
        "amount":        round(q * r, 2),
        "balance_qty":   round(approved_qty - float(prev_qty or 0.0) - q, 6),
        "rate_varies":   rate_varies(r, approved_rate),
        "certified_qty":  None,
        "certified_rate": None,
    }


def new_id() -> str:
    return str(uuid.uuid4())


# =============================================================================
# THE POSTED PAYLOAD
# =============================================================================

def _parse_payload(raw: str) -> tuple:
    """(lines, error) from the editor's hidden JSON."""
    if not (raw or "").strip():
        return [], "No claim lines were posted. Please re-enter them."
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return [], "The claim data could not be read. Please re-enter the lines."
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        return [], "The claim data could not be read. Please re-enter the lines."
    return lines, ""


def clean_claims(raw_lines: list, boq: dict, leg: str, prev: dict,
                 payload_bytes: int = 0) -> tuple:
    """
    (claims, error, error_line_id) — the posted lines as stored claim rows.

    The RA counterpart of `boq._clean_lines()`, sharing its contract —
    reject-and-re-render losslessly, name the offending line so the editor can
    force it open — but not its rules. A BOQ is a schedule being authored; an
    RA bill is a claim against a fixed line set, so what is validated is
    different.

    **The caps are enforced HERE, never in the persistence layer.** `db.sync()`
    runs from `teardown_request`, after the response has been built, so a cap
    there cannot reject anything — it can only fail silently forever on a
    record that is already in memory. Same reasoning as `boq.MAX_JSON_BYTES`.

    **Sparse storage, complete display.** Every line of the BOQ is rendered on
    the form so the operator can work down a measurement sheet, but a line
    claimed at zero is DROPPED here rather than stored. It keeps `ra_bills`
    small, keeps `claimed_by_line()` cheap, and means an untouched line never
    asserts a claim of zero it never made.
    """
    if len(raw_lines) > MAX_RA_LINES:
        over = len(raw_lines) - MAX_RA_LINES
        return ([],
                f"This claim has {len(raw_lines)} lines and the limit is "
                f"{MAX_RA_LINES}. Remove {over} line{'s' if over != 1 else ''}.",
                "")

    if payload_bytes > MAX_RA_JSON_BYTES:
        return ([],
                f"This claim is too large to save — {payload_bytes // 1024} KB "
                f"of line data against a limit of {MAX_RA_JSON_BYTES // 1024} KB. "
                f"No single line is at fault; it is the claim as a whole.",
                "")

    # The approved schedule this claim is measured against, keyed by line_id.
    by_id = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            by_id[lid] = li
    rates = approved_rates(str(boq.get("id") or ""))

    out, seen = [], set()
    for li in raw_lines:
        if not isinstance(li, dict):
            continue
        lid = BQ._line_id(li.get("line_id"))

        # A line the approved schedule does not contain has no quantity to be
        # claimed against. Rejected outright rather than silently dropped: a
        # posted id that is not in the BOQ means the form and the record
        # disagree, and saving the half we understand would hide that.
        if not lid or lid not in by_id:
            return ([], "This claim refers to a line that is not in the "
                        "approved BOQ. Reload the form and enter it again.", "")
        if lid in seen:
            return ([], "The same BOQ line was claimed twice in one bill.", lid)
        seen.add(lid)

        qty = BQ._num(li.get("qty"), 0.0)
        if qty < 0:
            src = by_id[lid]
            return ([], f"Item {BQ._item_no(src.get('item_no'))} has a negative "
                        f"claim quantity.", lid)
        if qty == 0:
            continue                      # sparse storage — see the docstring

        src = by_id[lid]
        rate = BQ._num(li.get("rate"), 0.0)
        if rate < 0:
            return ([], f"Item {BQ._item_no(src.get('item_no'))} has a negative "
                        f"rate.", lid)

        hsn_sac = str(src.get("install_sac" if leg == "installation" else "supply_hsn") or "").strip()
        gst_rate = float(src.get("install_gst_rate" if leg == "installation" else "supply_gst_rate") or 18.0)

        out.append(build_claim(src, qty, rate, prev.get((lid, leg), 0.0),
                               rates.get((lid, leg), 0.0), leg=leg,
                               hsn_sac=hsn_sac, gst_rate=gst_rate))

    if not out:
        return [], "Nothing has been claimed — enter a quantity on at least one line.", ""
    return out, "", ""


# =============================================================================
# CERTIFICATION — what was CLAIMED and what is ALLOWED are different numbers
# =============================================================================
#
# Every claim row carries `certified_qty` and `certified_rate` beside its
# claimed pair, and the bill carries `status` and `certified_on`. Tracked from
# the start rather than deferred, for the reason the deductions array was:
# splitting claimed from certified after the print format exists means
# reworking every balance calculation and every document already issued.
#
# Four rules, and each one is a test:
#
# 1. **The over-claim block runs on CLAIMED quantity, never on certified.** You
#    cannot claim beyond the BOQ; what the contractor then certifies is his
#    decision, not a validation input. `overclaims()` never reads a certified
#    field — see the test that asserts it.
# 2. **Uncertified is NOT zero.** `None` means "not yet certified": excluded
#    from certified totals entirely and reported as "n of m certified".
#    Summing a blank as zero under-reports receivables, which is the exact
#    inverse of the error this system was sold to catch.
# 3. **Certified above claimed WARNS, never blocks** — the same treatment the
#    rate divergence gets, and for the same reason: it is a real fact about the
#    bill that somebody should see, not an impossibility.
# 4. **Certification stays editable ALWAYS, including on a frozen bill.**
#    Certification lags in the real world: RA3 comes back certified after RA6
#    has been raised. Freezing the certificate with the claim would make the
#    field unusable. Freeze the claim, not the certificate — two separate edit
#    permissions on one record.

def _cert_num(raw):
    """
    A certified figure, or `None` for "not yet certified".

    Deliberately NOT `_num(raw, 0.0)`. A blank certified quantity means the
    contractor has not ruled on that line, and calling that zero states that he
    allowed nothing — which under-reports what is owed and is the single most
    expensive mistake available in this module.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def is_certified(claim: dict) -> bool:
    """Has this line been ruled on? A quantity of 0.0 counts — 0 is a ruling."""
    return _cert_num(claim.get("certified_qty")) is not None


def certified_amount(claim: dict):
    """
    certified_qty x certified_rate, or `None` when the line is not certified.

    The rate falls back to the claimed rate when a quantity is certified but no
    rate is: certifying a quantity without restating the rate means the claimed
    rate stands, which is what the contractor's own annexure does.
    """
    q = _cert_num(claim.get("certified_qty"))
    if q is None:
        return None
    r = _cert_num(claim.get("certified_rate"))
    if r is None:
        r = float(claim.get("rate") or 0.0)
    return round(q * r, 2)


def certification_summary(bill: dict) -> dict:
    """
    {certified, total, amount, complete} for one bill.

    `amount` sums ONLY the certified lines. `certified`/`total` is the "n of m"
    the register reports, and it exists precisely so an uncertified line is
    visible as unanswered rather than silently contributing zero.
    """
    claims = bill.get("claims") or []
    done = [c for c in claims if is_certified(c)]
    return {"certified": len(done), "total": len(claims),
            "amount": round(sum(certified_amount(c) or 0.0 for c in done), 2),
            "complete": bool(claims) and len(done) == len(claims)}


def has_certification(bill: dict) -> bool:
    """
    Does this bill carry ANY certification data at all?

    The delete guard's question. A bill that has been certified has been out of
    the building and acknowledged by the main contractor, and deleting it
    destroys the only record of what was allowed against what was claimed.
    """
    if str(bill.get("certified_on") or "").strip():
        return True
    if str(bill.get("status") or "") == "certified":
        return True
    return any(is_certified(c) or _cert_num(c.get("certified_rate")) is not None
               for c in bill.get("claims") or [])


def certification_warnings(claims: list) -> list:
    """
    Lines certified for MORE than was claimed. A warning, never a block.

    Same treatment as the rate divergence: the contractor is free to allow more
    than was asked for — a remeasurement can go up — but a certificate above
    the claim is a fact somebody should see rather than discover in a total.
    """
    out = []
    for c in claims or []:
        q = _cert_num(c.get("certified_qty"))
        if q is None:
            continue
        claimed = float(c.get("qty") or 0.0)
        if round(q - claimed, 6) > _QTY_EPSILON:
            out.append({"item_no": c.get("item_no", ""),
                        "line_id": c.get("line_id", ""),
                        "claimed": claimed, "certified": q,
                        "over": round(q - claimed, 6)})
    return out


def certification_warning_message(v: dict) -> str:
    q = BQ._fmt_qty
    return (f"Item {v['item_no']}: {q(v['claimed'])} claimed but "
            f"{q(v['certified'])} certified — {q(v['over'])} more than was "
            f"asked for. Allowed, but worth checking.")


def bills_certified(boq_id: str) -> tuple:
    """(n, m) — how many of this project's RA bills carry a full certificate."""
    rows = bills_of(boq_id)
    done = sum(1 for _rid, b in rows if certification_summary(b)["complete"])
    return done, len(rows)


def apply_certification(bill: dict, rows: dict, status: str = None,
                        certified_on: str = None) -> dict:
    """
    Write certification onto a bill. **Works on a frozen bill by design.**

    `rows` is {line_id: {"certified_qty": ..., "certified_rate": ...}}. This is
    the second of the record's two edit permissions and it is deliberately not
    gated on `claim_is_frozen()`: RA3 is certified after RA6 exists, so gating
    it would make the field unusable exactly when it is needed.

    It touches ONLY the certified pair, the status and the date. `qty`, `rate`
    and `amount` — the claim — are never written here, which is what keeps
    "certifying a frozen bill does not reopen its claim" true by construction
    rather than by a check.
    """
    for c in bill.get("claims") or []:
        row = rows.get(c.get("line_id"))
        if row is None:
            continue
        if "certified_qty" in row:
            c["certified_qty"] = _cert_num(row.get("certified_qty"))
        if "certified_rate" in row:
            c["certified_rate"] = _cert_num(row.get("certified_rate"))

    if status in STATUSES:
        bill["status"] = status
    if certified_on is not None:
        bill["certified_on"] = str(certified_on or "").strip()
    return bill


# =============================================================================
# MUTABILITY — the claim freezes, the certificate never does
# =============================================================================

def is_latest_bill(boq_id: str, ra_id: str) -> bool:
    """Is this the highest-numbered bill in the project's chain?"""
    rows = bills_of(boq_id)
    if not rows:
        return False
    highest = max(int(b.get("ra_no") or 0) for _rid, b in rows)
    bill = (STORE.get("ra_bills") or {}).get(ra_id) or {}
    return int(bill.get("ra_no") or 0) == highest and any(
        rid == ra_id for rid, _b in rows)


def claim_is_frozen(bill: dict) -> bool:
    """
    Is this bill's CLAIM closed to edits? True once a later bill exists.

    `claimed_by_line()` sums the whole chain, so editing a mid-chain bill
    silently changes every downstream balance — including ones already printed
    and handed to the main contractor. Latest-only bounds the recompute to one
    bill and keeps printed history true.

    The certificate is NOT covered by this. See `apply_certification()`.
    """
    if not bill:
        return True
    return not is_latest_bill(str(bill.get("boq_id") or ""), str(bill.get("id") or ""))


def frozen_reason(bill: dict) -> str:
    """Why this bill's claim cannot be edited, in words, or ""."""
    if not claim_is_frozen(bill):
        return ""
    later = [int(b.get("ra_no") or 0)
             for _rid, b in bills_of(str(bill.get("boq_id") or ""))
             if int(b.get("ra_no") or 0) > int(bill.get("ra_no") or 0)]
    if not later:
        return "This bill's claim can no longer be edited."
    names = ", ".join(f"RA{n}" for n in sorted(later))
    return (f"RA{bill.get('ra_no')}'s claim is frozen because {names} "
            f"{'has' if len(later) == 1 else 'have'} been raised against this "
            f"BOQ. Every later bill's balance was calculated from this one, so "
            f"changing it now would rewrite figures already sent out. "
            f"Its certification can still be recorded.")


def can_delete(bill: dict) -> tuple:
    """
    (allowed, reason) — may this bill be deleted?

    Two conditions, both refusing with a sentence rather than hiding a button:

    - **Only the highest-numbered bill.** After a delete the next bill takes
      max+1 from what remains, so the sequence stays contiguous and a number
      the client has already seen is never reissued.
    - **Never one carrying certification data.** It has been out of the
      building and acknowledged; deleting it destroys the only record of what
      was allowed against what was claimed.
    """
    if not bill:
        return False, "That RA bill no longer exists."
    if has_certification(bill):
        return False, (
            f"RA{bill.get('ra_no')} carries certification data, so it cannot be "
            f"deleted. It has been out to the main contractor and his ruling on "
            f"it is the only record of what was allowed against what was "
            f"claimed. Correct the position in the next claim instead.")
    if claim_is_frozen(bill):
        later = [int(b.get("ra_no") or 0)
                 for _rid, b in bills_of(str(bill.get("boq_id") or ""))
                 if int(b.get("ra_no") or 0) > int(bill.get("ra_no") or 0)]
        names = ", ".join(f"RA{n}" for n in sorted(later))
        return False, (
            f"Only the latest bill can be deleted. Delete {names} first — "
            f"removing RA{bill.get('ra_no')} now would leave a gap in the "
            f"sequence and change every later bill's balance.")
    return True, ""


# =============================================================================
# THE RA ENTRY FORM — stylesheet
# =============================================================================
#
# A plain string, not an f-string, so its CSS braces are written once. Layered
# after BASE_STYLES + QUOTATION_STYLES, which carry the page furniture and the
# form widgets, so this sheet only holds what is genuinely new: the claim grid.
#
# ⚠ There is no print sheet here. The printed RA bill is step 4, and nothing in
#   this file should grow one — a claim grid tuned for entry is not a document.
RA_STYLES = """
<style>
  .ra-meta {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:.9rem; margin-bottom:1rem;
  }
  .ra-fact { background:var(--bg); border:1px solid var(--border);
             border-radius:8px; padding:.55rem .7rem; }
  .ra-fact b { display:block; font-size:.66rem; text-transform:uppercase;
               letter-spacing:.06em; color:var(--muted); font-weight:700; }
  .ra-fact span { font-size:.86rem; font-weight:600; color:var(--navy); }

  /* The claim grid. Fixed layout: 87 rows must not reflow as the operator
     types, or the row under the cursor moves. */
  .cl-wrap { overflow-x:auto; border:1px solid var(--border); border-radius:10px; }
  table.claims { width:100%; border-collapse:collapse; font-size:.78rem;
                 table-layout:fixed; min-width:920px; }
  table.claims th {
    background:var(--bg); text-align:left; font-size:.66rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
    padding:.5rem .55rem; border-bottom:1px solid var(--border);
    position:sticky; top:0; z-index:5;
  }
  table.claims td { padding:.4rem .55rem; border-bottom:1px solid #eef2f7;
                    vertical-align:middle; }
  table.claims tr:hover td { background:#f8fafc; }
  .cl-no    { width:70px;  font-weight:700; color:var(--navy); }

  /* The description column of a CLAIM ENTRY table.
     **Deliberately not nowrap-with-ellipsis.** The operator is holding a paper
     measurement sheet and matching a row on it to a row here. Hover-to-reveal
     fails on a touch screen, and fails again when the two documents are being
     read side by side — which is the only way this form is ever used. Once the
     specification families fold, the visible rows are few enough to afford two
     lines each, so child lines wrap and only the parent header is clamped. */
  .cl-desc  { min-width:180px; max-width:280px; }
  .cl-desc .cl-clamp {
    display:-webkit-box; -webkit-box-orient:vertical;
    -webkit-line-clamp:2; line-clamp:2;
    overflow:hidden; line-height:1.35; max-height:2.7em;
  }
  /* The parent header row IS clamped to one line — it carries a specification
     paragraph of up to ~1400 characters, and a paragraph is not a table row.
     Same treatment boq.py's summary row gives it, same class name. */
  .ls-desc  { display:block; overflow:hidden; text-overflow:ellipsis;
              white-space:nowrap; }
  .cl-unit  { width:62px;  color:var(--muted); }
  .cl-num   { width:88px;  text-align:right; font-variant-numeric:tabular-nums; }
  .cl-in    { width:104px; }
  .cl-in input {
    width:100%; padding:.3rem .4rem; font-size:.78rem; text-align:right;
    border:1px solid var(--border); border-radius:6px;
    font-variant-numeric:tabular-nums;
  }
  .cl-in input:focus { outline:2px solid var(--navy); outline-offset:-1px; }
  .cl-amt { width:110px; text-align:right; font-weight:700; color:var(--navy);
            font-variant-numeric:tabular-nums; }

  /* A line with nothing left to claim. Shown, never hidden: a line that is
     exhausted is the state most likely to be mis-claimed, so hiding it hides
     exactly the fact the operator needs. */
  tr.cl-done td { background:#fafafa; color:var(--muted); }
  tr.cl-done .cl-no { color:var(--muted); }
  .cl-bal-0 { color:#b45309; font-weight:700; }

  /* A specification header — context, never claimable, and the fold point.
     ────────────────────────────────────────────────────────────────────────
     The family tree, ported from boq.py's line editor: the same `.ls-row`
     affordances (`cursor:pointer; user-select:none`), the same `is-spec` /
     `is-child` class names, the same chevron, the same `spec · N items` tag,
     and the same collapsed-on-arrival behaviour. Item 4 shut takes 4.1–4.8
     with it, because that is how the schedule reads on paper — 40 of the
     Sify BOQ's 97 rows are children of one of its 10 headers.

     ONE difference from boq.py, in MECHANISM only, and it is forced rather
     than chosen: boq.py re-renders from a browser-side model and simply does
     not emit a folded child, but this grid is server-rendered and every row
     carries the two <input>s that make up the POST body. So a folded row is
     HIDDEN, never removed. Collapsing must not be able to change what saves. */
  tr.cl-head td { background:#f1f5f9; font-weight:700; color:var(--navy); }
  tr.cl-head { cursor:pointer; user-select:none; }
  tr.cl-head:hover td { background:#e2e8f0; }
  tr.cl-head.is-spec .cl-no { border-left:3px solid var(--navy); }
  tr.cl-line.is-child .cl-no { padding-left:1.6rem; }
  .ls-chev { display:inline-block; width:12px; color:var(--muted);
             font-size:.7rem; }
  .ls-tag  { float:right; font-size:.72rem; color:var(--navy);
             font-weight:600; white-space:nowrap; padding-left:.8rem; }

  /* Expand-all / collapse-all. boq.py hangs these off its sticky jump bar;
     this grid has no sections to jump between, so they stand alone. */
  .cl-tools { display:flex; align-items:center; gap:.6rem; flex-wrap:wrap;
              margin:0 0 .5rem; font-size:.75rem; color:var(--muted); }
  .cl-tools .sp { flex:1 1 auto; }

  .cl-over input { border-color:var(--brand); background:#fef2f2; }
  .cl-warn input { border-color:var(--saffron); background:#fffbeb; }

  .ra-foot {
    display:flex; justify-content:flex-end; gap:2rem; align-items:baseline;
    padding:.8rem 1rem; background:var(--bg); border:1px solid var(--border);
    border-top:0; border-radius:0 0 10px 10px;
  }
  .ra-foot b { font-size:.7rem; text-transform:uppercase; letter-spacing:.06em;
               color:var(--muted); }
  .ra-tot { font-size:1.15rem; font-weight:800; color:var(--navy);
            font-variant-numeric:tabular-nums; }

  .ded-empty { font-size:.78rem; color:var(--muted); font-style:italic;
               padding:.6rem .8rem; background:var(--bg);
               border:1px dashed var(--border); border-radius:8px; }

  .frozen-note {
    display:flex; gap:.55rem; align-items:flex-start; background:#eff6ff;
    border:1px solid #bfdbfe; border-left:3px solid var(--navy);
    border-radius:8px; padding:.6rem .8rem; margin-bottom:1rem;
    font-size:.78rem; line-height:1.5; color:#1e3a8a;
  }
  .del-box { border:1px solid #fecaca; background:#fef2f2; border-radius:10px;
             padding:1rem 1.1rem; margin-bottom:1.2rem; }
  .del-box h2 { margin:0 0 .5rem; font-size:1rem; color:var(--brand); }
  .del-line { font-size:.82rem; line-height:1.6; }
</style>
"""


# =============================================================================
# PAGE HELPER
# =============================================================================
#
# `render_template_string` is deliberately absent. Values are pre-interpolated
# by Python and never passed as Jinja context, so a second parse would only
# execute `{{ }}` that arrived in user input — pure downside (ABOUT.md §7.9d).
# This module was written after that was settled and never had one.

def _page(html: str) -> str:
    """A finished page. Deliberately not Jinja-rendered."""
    return html


def _esc(v) -> str:
    return P.esc("" if v is None else str(v))


def _qty(v) -> str:
    return BQ._fmt_qty(v)


# =============================================================================
# THE LINE EDITOR — a smaller model than the BOQ's, on purpose
# =============================================================================
#
# `boq._BOQ_JS` is built around sections, areas, the spec picker and escalation.
# An RA form is a different animal: **the line set is FIXED**. It comes from the
# approved BOQ and the user must not be able to add to it, remove from it or
# reorder it. What they enter is one quantity and one rate per line.
#
# So this reuses the *contract* rather than the code — a JSON model posted in a
# hidden field, stripped and rebuilt server-side by named keys — and not the
# editor itself. Dragging the spec picker into a form that must refuse to pick
# anything would be the wrong kind of reuse.
#
# The model carries `line_id` and nothing else identifying: no item number, no
# description, no position. The server resolves the id against the approved BOQ
# and snapshots the item number itself, so a posted label cannot disagree with
# the schedule and cannot be spoofed.
#
# A **raw** string, unlike `boq._BOQ_JS`, because `money()` carries a regex with
# `\B` and `\d` in it. In a normal triple-quoted string Python reads those as
# invalid escapes (a SyntaxWarning today, an error later) and hands JavaScript
# something it did not write. Raw is the fix; there is nothing here that wants
# Python-level escape processing.
_RA_JS = r"""
<script>
function el(id) { return document.getElementById(id); }
function num(v) { var n = parseFloat(String(v).replace(/,/g, '')); return isNaN(n) ? 0 : n; }

function money(n) {
  var s = (Math.round(n * 100) / 100).toFixed(2), p = s.split('.');
  var x = p[0], last3 = x.slice(-3), rest = x.slice(0, -3);
  if (rest) last3 = ',' + last3;
  return rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + last3 + '.' + p[1];
}

/* Recompute one row, then the bill. Called on every keystroke, which is what
   makes the over-claim visible while it is being typed rather than on save. */
function recalc(lid) {
  var q = el('q_' + lid), r = el('r_' + lid);
  if (!q || !r) return;
  var qty = num(q.value), rate = num(r.value);

  var amt = el('a_' + lid);
  if (amt) amt.textContent = money(qty * rate);

  var row = el('row_' + lid);
  var approved = num(row.getAttribute('data-approved'));
  var prev     = num(row.getAttribute('data-prev'));
  var appRate  = num(row.getAttribute('data-rate'));

  /* The over-claim is on the CUMULATIVE quantity, never on this bill alone.
     A per-bill check would pass nine times and still end 9% over. */
  var over = (prev + qty) - approved > 1e-6;
  q.parentNode.className = 'cl-in' + (over ? ' cl-over' : '');

  /* Rate divergence WARNS and never blocks — rates legitimately move on
     approved variations, and ten cells of the client's own annexure do. */
  var varies = qty > 0 && Math.abs(rate - appRate) > 0.005;
  r.parentNode.className = 'cl-in' + (varies ? ' cl-warn' : '');

  var bal = el('b_' + lid);
  if (bal) {
    var left = approved - prev - qty;
    bal.textContent = money(left);
    bal.className = 'cl-num' + (left <= 1e-6 ? ' cl-bal-0' : '');
  }
  total();
}

function total() {
  var t = 0, n = 0, over = 0;
  for (var i = 0; i < LINE_IDS.length; i++) {
    var lid = LINE_IDS[i];
    var q = el('q_' + lid), r = el('r_' + lid);
    if (!q) continue;
    var qty = num(q.value);
    if (qty > 0) { n++; t += qty * num(r.value); }
    var row = el('row_' + lid);
    if (qty > 0 && (num(row.getAttribute('data-prev')) + qty)
                   - num(row.getAttribute('data-approved')) > 1e-6) over++;
  }
  el('ra-total').textContent = money(t);
  el('ra-count').textContent = n + (n === 1 ? ' line' : ' lines');
  var w = el('ra-over');
  if (w) {
    w.style.display = over ? '' : 'none';
    w.textContent = over + (over === 1 ? ' line is' : ' lines are')
                  + ' over the approved quantity and will be refused on save.';
  }
}

/* ── The specification family tree ──────────────────────────────────────
   Ported from boq.py: a closed header folds its family away with it, item 4
   shut takes 4.1-4.8 with it, and everything arrives shut.

   Open/closed state lives on the HEADER ROW, keyed by its line_id — never in
   a map keyed by row index. That is the desync boq.py's `_open` was moved
   onto the line to avoid, and a claim grid is exactly where it would bite,
   because two rows in one section can share an item number.

   `FAMILIES` is computed server-side for the same reason `_duplicate_items()`
   is: on this form the line set is fixed and cannot be edited.

   A folded row is HIDDEN, not removed. Every <input> stays in the document
   and therefore in the POST body, open or shut — `saveJSON()` below reads
   values and never visibility, and there is a test that fires these toggles
   against the rendered page and diffs the payload. */

function isFamilyOpen(hlid) {
  var head = el('head_' + hlid);
  return !!(head && head.getAttribute('data-open') === '1');
}

function setFamily(hlid, open) {
  var head = el('head_' + hlid);
  if (!head) return;
  head.setAttribute('data-open', open ? '1' : '0');
  var chev = el('chev_' + hlid);
  if (chev) chev.textContent = open ? '▾' : '▸';
  var kids = FAMILIES[hlid] || [];
  for (var i = 0; i < kids.length; i++) {
    var row = el('row_' + kids[i]);
    if (row) row.style.display = open ? '' : 'none';
  }
}

function toggleFamily(hlid) { setFamily(hlid, !isFamilyOpen(hlid)); }

function setAllFamilies(open) {
  for (var hlid in FAMILIES) {
    if (Object.prototype.hasOwnProperty.call(FAMILIES, hlid)) {
      setFamily(hlid, open);
    }
  }
}

function expandAll()   { setAllFamilies(true); }
function collapseAll() { setAllFamilies(false); }

/* Only lines with a quantity are posted. Sparse storage: an untouched line
   must not assert a claim of zero it never made. The server drops zeros too —
   this is a courtesy to the wire, not the rule.

   Note what this does NOT consult: whether a row is visible. A folded family
   posts exactly what an open one does. */
function saveJSON() {
  var lines = [];
  for (var i = 0; i < LINE_IDS.length; i++) {
    var lid = LINE_IDS[i];
    var q = el('q_' + lid);
    if (!q || num(q.value) <= 0) continue;
    lines.push({line_id: lid, qty: q.value, rate: (el('r_' + lid) || {}).value || ''});
  }
  el('ra_json').value = JSON.stringify({lines: lines});
  return true;
}

total();
</script>
"""


# =============================================================================
# FORM FRAGMENTS
# =============================================================================

def _duplicate_items(boq: dict) -> list:
    """
    Item numbers appearing more than once in one section of this BOQ.

    The same band the BOQ form carries, and it belongs here for the same
    reason: the operator will see two rows both labelled 17 in section A and
    needs to be told they are separate items, guarded separately, and that
    picking either one is unambiguous to the system.

    Computed server-side rather than in JS, because on this form the line set
    is fixed — it comes from the approved BOQ and cannot be edited here.
    """
    seen, dupes = {}, []
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        key = (str(li.get("section") or ""), BQ._item_no(li.get("item_no")))
        if not key[1]:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dupes.append(key)
    return dupes


def _dup_band(boq: dict) -> str:
    dupes = _duplicate_items(boq)
    if not dupes:
        return ""
    listed = ", ".join(
        f'{_esc(ino)} <span class="fh-sec">(section {_esc(sec)})</span>'
        for sec, ino in dupes)
    plural = "" if len(dupes) == 1 else "s"
    return f"""
    <div class="form-hint">
      <span class="fh-icon">&#9888;</span>
      <span><b>Repeated item number{plural}:</b> {listed}. Two lines in this
      schedule share a number, so they look alike on a measurement sheet.
      <b>They are separate items here</b> &mdash; each is tracked and guarded
      against its own approved quantity, and entering a quantity against one
      cannot touch the other.</span>
    </div>"""


def _trunc(s: str, n: int = 96) -> str:
    s = " ".join(str(s or "").split())
    return s[:n-1] + "…" if len(s) > n else s


def _families(boq: dict) -> dict:
    """
    `{header_line_id: [child_line_id, ...]}` for this BOQ's specification
    families — boq.py's `childrenOf()`, computed here instead of in JS.

    Server-side for the same reason `_duplicate_items()` is: on this form the
    line set is fixed. It comes from the approved BOQ and nothing on the page
    can add to it, remove from it or reorder it, so there is no state for the
    browser to keep and nothing for it to recompute.

    The match is boq.py's, unchanged — **same section, and `parent_item_no`
    equal to the header's `item_no`.** Section is part of the key because item
    numbers restart per section (ABOUT.md §3), so item 4 in A and item 4 in B
    are different headers and 4.1 in B must not fold under A's.
    """
    heads = {}
    for li in boq.get("line_items") or []:
        if not li.get("is_header"):
            continue
        item = BQ._item_no(li.get("item_no"))
        lid = BQ._line_id(li.get("line_id"))
        if item and lid:
            heads[(str(li.get("section") or ""), item)] = lid

    out = {lid: [] for lid in heads.values()}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        parent = BQ._item_no(li.get("parent_item_no"))
        lid = BQ._line_id(li.get("line_id"))
        if not parent or not lid:
            continue
        hlid = heads.get((str(li.get("section") or ""), parent))
        if hlid:
            out[hlid].append(lid)
    return out


def _claim_rows(boq: dict, leg: str, prev: dict, entered: dict) -> str:
    """
    Every line of the approved BOQ, in BOQ order, as claim-grid rows.

    **All of them, never a shortlist.** The operator works from a site
    measurement sheet against item numbers, not from a filtered view, and
    hiding an exhausted line hides the fact that it is exhausted — which is the
    state most likely to be mis-claimed. A line with nothing left is shown
    greyed with its balance called out, not removed.

    Specification headers are rendered as context and carry no inputs: a header
    holds the clause and no quantity, so there is nothing to claim against it.
    They are also the **fold point** — see `RA_STYLES` and `_RA_JS`. A family
    arrives collapsed, and opens on arrival only when one of its children
    already carries a figure: that is boq.py's "a rejected POST forces the
    offending line open" contract, and it is also what makes `/ra/edit` show
    the lines the bill actually claimed rather than a wall of shut headers.

    **Folded is hidden, never dropped.** Every row of the approved BOQ is in
    the document whatever is open, so the POST body does not depend on what the
    operator happened to have expanded.
    """
    rates = approved_rates(str(boq.get("id") or ""))
    families = _families(boq)
    child_of = {kid: hlid for hlid, kids in families.items() for kid in kids}
    open_family = {hlid for hlid, kids in families.items()
                   if any(BQ._num((entered.get(k) or {}).get("qty"), 0.0) > 0
                          for k in kids)}
    out = []

    for li in boq.get("line_items") or []:
        item = _esc(BQ._item_no(li.get("item_no")))
        raw_desc = str(li.get("description") or "")

        if li.get("is_header"):
            # One line only: this is a specification paragraph, and the fold is
            # what makes the schedule scannable. The whole text stays in `title`.
            desc_truncated = _esc(_trunc(raw_desc, 96))
            hlid = BQ._line_id(li.get("line_id"))
            kids = families.get(hlid) or []
            is_open = hlid in open_family
            tag = (f'<span class="ls-tag">spec &middot; {len(kids)} '
                   f'item{"" if len(kids) == 1 else "s"}</span>') if kids else \
                  '<span class="ls-tag">spec</span>'
            # A header with no family is not a fold point — no chevron, no
            # click target, nothing to promise the operator that never happens.
            click = f' id="head_{hlid}" data-open="{"1" if is_open else "0"}"' \
                    f' onclick="toggleFamily(\'{hlid}\')"' if kids and hlid else ""
            chev = (f'<span class="ls-chev" id="chev_{hlid}">'
                    f'{"&#9662;" if is_open else "&#9656;"}</span>') if kids and hlid else ""
            out.append(
                f'<tr class="cl-head is-spec"{click}>'
                f'<td class="cl-no">{chev}{item}</td>'
                f'<td colspan="8">{tag}'
                f'<span class="ls-desc" title="{_esc(raw_desc)}">{desc_truncated}</span>'
                f'</td></tr>')
            continue

        lid = BQ._line_id(li.get("line_id"))
        if not lid:
            continue

        parent_lid = child_of.get(lid)
        child_cls = " is-child" if parent_lid else ""
        hide = (' style="display:none;"'
                if parent_lid and parent_lid not in open_family else "")

        approved = float(li.get("total_qty") or 0.0)
        claimed = float(prev.get((lid, leg), 0.0))
        balance = approved - claimed
        app_rate = float(rates.get((lid, leg), 0.0))

        row = entered.get(lid) or {}
        q_val = _esc(row.get("qty", ""))
        r_val = _esc(row.get("rate", "")) if "rate" in row else (
            f"{app_rate:g}" if app_rate else "")
        amt = BQ._num(row.get("qty"), 0.0) * BQ._num(r_val, 0.0)

        done = " cl-done" if balance <= 1e-6 else ""
        bal_cls = "cl-num cl-bal-0" if balance <= 1e-6 else "cl-num"

        out.append(f"""
        <tr class="cl-line{child_cls}{done}" id="row_{lid}"{hide}
            data-approved="{approved:g}" data-prev="{claimed:g}" data-rate="{app_rate:g}">
          <td class="cl-no">{item}</td>
          <td class="cl-desc"><span class="cl-clamp" title="{_esc(raw_desc)}">{_esc(" ".join(raw_desc.split()))}</span></td>
          <td class="cl-unit">{_esc(li.get("unit") or "")}</td>
          <td class="cl-num">{_qty(approved)}</td>
          <td class="cl-num">{_qty(claimed)}</td>
          <td class="{bal_cls}" id="b_{lid}">{_qty(balance)}</td>
          <td class="cl-in"><input type="text" inputmode="decimal" id="q_{lid}"
              value="{q_val}" oninput="recalc('{lid}')" aria-label="Claim quantity"/></td>
          <td class="cl-in"><input type="text" inputmode="decimal" id="r_{lid}"
              value="{r_val}" oninput="recalc('{lid}')" aria-label="Rate"/></td>
          <td class="cl-amt" id="a_{lid}">{_inr(amt)}</td>
        </tr>""")

    return "".join(out)


def _claim_ids(boq: dict) -> str:
    ids = [BQ._line_id(li.get("line_id")) for li in boq.get("line_items") or []
           if not li.get("is_header") and BQ._line_id(li.get("line_id"))]
    return json.dumps(ids)


def _family_tools(boq: dict) -> str:
    """The expand-all / collapse-all bar, or nothing when there is no family."""
    families = {h: k for h, k in _families(boq).items() if k}
    if not families:
        return ""
    n = len(families)
    rows = sum(len(k) for k in families.values())
    return f"""
      <div class="cl-tools">
        <span>{n} specification famil{"y" if n == 1 else "ies"} &middot;
        {rows} line{"" if rows == 1 else "s"} folded under {"it" if n == 1 else "them"}.
        Every line is still on the page and still saves &mdash; folding only hides it.</span>
        <span class="sp"></span>
        <button type="button" class="btn-row" onclick="expandAll()">Expand all</button>
        <button type="button" class="btn-row" onclick="collapseAll()">Collapse all</button>
      </div>"""


def _deductions_block(bill: dict = None) -> str:
    """
    The bill-level deductions list — rendered, and empty, exactly as designed.

    It exists from day one because retention, mobilisation-advance recovery and
    cess all fit one shape, and retrofitting a deduction block after the print
    format exists means every issued document was produced by a renderer with
    nowhere to put it. The entry UI is not part of this step.
    """
    rows = (bill or {}).get("deductions") or []
    if not rows:
        return ('<div class="ded-empty">No deductions on this bill. '
                'Retention, mobilisation-advance recovery and cess will be '
                'entered here.</div>')
    body = "".join(
        f'<tr><td>{_esc(d.get("label"))}</td>'
        f'<td class="cl-amt">{_inr(d.get("amount") or 0.0)}</td></tr>'
        for d in rows)
    return f'<table class="claims"><tbody>{body}</tbody></table>'


# =============================================================================
# ROUTES
# =============================================================================

def _shell(title: str, body: str) -> str:
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{BQ.BOQ_STYLES}{RA_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
</main>
</body></html>""")


def _alert(msg: str, kind: str = "error") -> str:
    """
    A banner. **Escapes its own message — every caller passes plain text.**

    Escaping here rather than at each call site is deliberate: the messages
    this renders are built from BOQ data. `overclaim_message()` interpolates an
    item number, and an item number is a free-text field somebody types on the
    BOQ form — so `<script>` in a line's item number reaches this banner. It
    did, until this escaped.

    That makes this the one choke point, and it is why no caller may pass HTML
    through it. `_flash()` passes the raw query parameter for the same reason.
    """
    return f'<div class="alert {kind}">{_esc(msg)}</div>' if msg else ""


def _flash() -> str:
    """A redirect's ?msg=&type= banner. Raw — `_alert()` does the escaping."""
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "success" if request.args.get("type") == "success" else "error"
    return _alert(msg, kind)


def _boq_facts(boq: dict, leg: str, ra_no) -> str:
    """
    The five facts above the claim grid.

    `ra_no` is **the integer**, and this function owns the `RA` prefix. It used
    to be handed the caller's page heading — an already-formatted `"RA3"` from
    `_entry_form` and a bare `3` from everywhere else — and printed `RARA3`.
    That was patched by sniffing for a leading `"RA"`, which left one parameter
    with two contracts and the next caller free to pick the wrong one. The
    caller passes the number; there is nothing left to sniff.
    """
    n, m = bills_certified(str(boq.get("id") or ""))
    label = f"RA{int(ra_no or 0)}"       # int() by intent: a pre-formatted
                                         # string is now a loud TypeError here
                                         # rather than a quiet "RARA3" on screen
    return f"""
    <div class="ra-meta">
      <div class="ra-fact"><b>Project</b><span>{_esc(boq.get("project_name"))}</span></div>
      <div class="ra-fact"><b>BOQ</b><span>{_esc(boq.get("ref"))} &middot; rev {_esc(boq.get("rev_no") or 0)}</span></div>
      <div class="ra-fact"><b>Customer</b><span>{_esc(boq.get("account_name"))}</span></div>
      <div class="ra-fact"><b>This bill</b><span>{_esc(label)} &middot; {_esc(leg)}</span></div>
      <div class="ra-fact"><b>Certified so far</b><span>{n} of {m} bills</span></div>
    </div>"""


def _entry_form(boq: dict, leg: str, prev: dict, entered: dict, error: str,
                action: str, ra_no: int, back_url: str, date_val: str,
                notes_val: str, submit_label: str, frozen_note: str = "") -> str:
    """
    The claim grid, shared by create and edit — one form, two entry points.

    `ra_no` is **the integer**. The page heading is derived from it here; it is
    not a second parameter that could disagree with it, and it is not what gets
    handed to `_boq_facts()`.
    """
    heading = f"RA{int(ra_no or 0)}"
    return _shell(heading, f"""
  <div class="page-top">
    <h1>{heading}</h1>
    <a href="{back_url}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {_alert(error)}
  {frozen_note}
  {_boq_facts(boq, leg, ra_no)}
  {_dup_band(boq)}
  <form method="POST" action="{action}" onsubmit="return saveJSON()">
    <input type="hidden" name="ra_json" id="ra_json"/>
    <div class="form-section">
      <div class="fg2">
        <div class="form-group"><label for="date">Date</label>
          <input type="date" id="date" name="date" value="{_esc(date_val)}"/></div>
        <div class="form-group"><label for="leg_shown">Leg</label>
          <input type="text" id="leg_shown" value="{_esc(leg)}" disabled
                 title="A bill covers one leg. Start a separate bill for the other."/></div>
      </div>
    </div>
    <div class="form-section">
      <div class="section-title">&#128200; Claim</div>
      <p id="ra-over" class="alert error" style="display:none;"></p>
      {_family_tools(boq)}
      <div class="cl-wrap">
        <table class="claims">
          <thead><tr>
            <th>Item</th><th>Description</th><th>Unit</th>
            <th style="text-align:right;">Approved</th>
            <th style="text-align:right;">Claimed to date</th>
            <th style="text-align:right;">Balance</th>
            <th style="text-align:right;">This claim</th>
            <th style="text-align:right;">Rate</th>
            <th style="text-align:right;">Amount</th>
          </tr></thead>
          <tbody>{_claim_rows(boq, leg, prev, entered)}</tbody>
        </table>
      </div>
      <div class="ra-foot">
        <span><b>Lines claimed</b> <span id="ra-count">0 lines</span></span>
        <span><b>Claim total</b> <span class="ra-tot" id="ra-total">0.00</span></span>
      </div>
    </div>
    <div class="form-section">
      <div class="section-title">&#9986; Deductions</div>
      {_deductions_block()}
    </div>
    <div class="form-section">
      <div class="form-group"><label for="notes">Notes</label>
        <textarea id="notes" name="notes" rows="2">{_esc(notes_val)}</textarea></div>
    </div>
    <button type="submit" class="btn">{submit_label}</button>
  </form>
  <script>var LINE_IDS = {_claim_ids(boq)};
var FAMILIES = {json.dumps(_families(boq))};</script>
  {_RA_JS}""")


def _posted(raw_lines: list) -> dict:
    """Posted rows keyed by line_id, so a rejected save re-renders losslessly."""
    out = {}
    for r in raw_lines or []:
        if not isinstance(r, dict):
            continue
        lid = BQ._line_id(r.get("line_id"))
        if lid:
            out[lid] = r
    return out


def _validate(raw: str, boq: dict, leg: str, prev: dict,
              exclude_ra_id: str = None) -> tuple:
    """
    (claims, error) — parse, clean and run the block. One path for create and edit.

    The order is deliberate: shape, then per-line rules, then the cumulative
    block last, because the block is the expensive one and the only one that
    needs the whole claim set at once.
    """
    raw_lines, error = _parse_payload(raw)
    if error:
        return [], raw_lines, error

    claims, error, _bad = clean_claims(raw_lines, boq, leg, prev,
                                       payload_bytes=len(raw))
    if error:
        return [], raw_lines, error

    # THE BLOCK. Cumulative across the whole revision chain, hard, and with no
    # override anywhere in this file. The message carries the full arithmetic
    # because "line 24.d is over" is not something anybody can act on.
    breaches = overclaims(str(boq.get("id") or ""), leg, claims,
                          exclude_ra_id=exclude_ra_id)
    if breaches:
        msg = " ".join(overclaim_message(v) for v in breaches[:4])
        if len(breaches) > 4:
            msg += f" ({len(breaches) - 4} more not shown.)"
        return [], raw_lines, msg

    return claims, raw_lines, ""


def certification_status_badge(bill: dict) -> str:
    summary = certification_summary(bill)
    c, t = summary["certified"], summary["total"]
    if c == 0:
        return '<span class="status-badge cert-none" style="background:#f1f5f9;color:#64748b;border:1px solid #cbd5e1;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">None</span>'
    elif summary["complete"]:
        return '<span class="status-badge cert-full" style="background:#ecfdf5;color:#047857;border:1px solid #a7f3d0;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">Full</span>'
    else:
        return f'<span class="status-badge cert-partial" style="background:#fffbeb;color:#b45309;border:1px solid #fde68a;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">Partial ({c}/{t})</span>'


@ra_bp.route("/")
def list_ras():
    """
    The Running Account Bills register.

    Mirrors the BOQ register's structure, styling, and nav placement.
    Lists all RA bills grouped/sorted by BOQ and ra_no.
    """
    BQ.ensure_demo_boq()
    bills = STORE.get("ra_bills") or {}
    dash_url = url_for("dashboard.index")
    create_url = url_for("ra.create_ra")

    msg = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    alert_html = _alert(msg, msg_type) if msg else ""

    query = (request.args.get("q") or "").strip().lower()
    rows = []
    for rid, b in bills.items():
        if query:
            hay = " ".join(str(b.get(k) or "") for k in
                           ("ref", "project_name", "account_name", "site_location", "boq_ref")).lower()
            if query not in hay:
                continue
        rows.append((rid, b))

    # Sort so bills for the same BOQ read in ra_no order
    rows.sort(key=lambda kv: (str(kv[1].get("boq_id") or ""), int(kv[1].get("ra_no") or 0)))

    total_claimed = sum(float(b.get("net_payable") or 0.0) for _rid, b in bills.items())
    total_certified = sum(certification_summary(b)["amount"] for _rid, b in bills.items())

    tiles_html = f"""
    <div class="pipe-tiles">
      <div class="pipe-tile t-open">
        <div class="pt-lbl">Total Claimed Net Payable</div>
        <div class="pt-val">&#8377;&nbsp;{total_claimed:,.0f}</div>
        <div class="pt-sub">{len(bills)} running account bill{"s" if len(bills) != 1 else ""}</div>
      </div>
      <div class="pipe-tile">
        <div class="pt-lbl">Total Certified Amount</div>
        <div class="pt-val">&#8377;&nbsp;{total_certified:,.0f}</div>
        <div class="pt-sub">certified across all bills</div>
      </div>
    </div>"""

    if rows:
        table_rows_html = ""
        for rid, b in rows:
            boq_id = str(b.get("boq_id") or "")
            is_latest = is_latest_bill(boq_id, rid)
            latest_badge = '<span style="background:#e0e7ff;color:#3730a3;border:1px solid #c7d2fe;padding:2px 6px;border-radius:10px;font-size:0.7rem;font-weight:600;">Latest</span>' if is_latest else ""
            summary = certification_summary(b)
            cert_badge = certification_status_badge(b)
            view_url = url_for("ra.view_ra", id=rid)
            cert_url = url_for("ra.certify_ra", id=rid)
            print_url = url_for("ra.print_ra", id=rid)
            boq_link = url_for("boq.view_boq", id=boq_id) if boq_id in STORE.get("boqs", {}) else "#"

            table_rows_html += f"""
            <tr>
              <td class="td-ref"><a href="{view_url}">RA{_esc(b.get('ra_no'))}</a> <span style="font-size:0.75rem;color:var(--muted);">({_esc(b.get('ref'))})</span></td>
              <td><span class="fh-sec">{_esc(b.get('leg'))}</span></td>
              <td class="td-muted">{_esc(b.get('date'))}</td>
              <td><a href="{boq_link}">{_esc(b.get('boq_ref'))}</a></td>
              <td class="td-num" style="font-weight:600;">&#8377;&nbsp;{float(b.get('net_payable') or 0.0):,.2f}</td>
              <td class="td-num">&#8377;&nbsp;{summary['amount']:,.2f}</td>
              <td>{cert_badge}</td>
              <td>{latest_badge}</td>
              <td>
                <a href="{view_url}" class="btn-view">&#128269; View</a>
                <a href="{cert_url}" class="btn-view" style="margin-left:0.3rem;">&#9998; Certify</a>
                <a href="{print_url}" class="btn-view" style="margin-left:0.3rem;">&#128438; Print</a>
              </td>
            </tr>"""

        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>RA Bill</th><th>Leg</th><th>Date</th><th>BOQ Ref</th>
            <th style="text-align:right;">Claimed Net</th><th style="text-align:right;">Certified Amount</th>
            <th>Certification</th><th>Latest?</th><th></th>
          </tr></thead>
          <tbody>{table_rows_html}</tbody>
        </table></div>"""
    elif bills:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128269;</div><br>
          <strong>No RA bills match that search</strong>
          <a href="{url_for('ra.list_ras')}" class="btn"
             style="display:inline-block;margin-top:1.1rem;">Show all</a>
        </div>"""
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128203;</div><br>
          <strong>No Running Account bills yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            An RA bill is a progressive claim for work executed against an approved BOQ schedule.
          </p>
          <a href="{create_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">+ Create RA Bill</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Running Account Bills")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{BQ.BOQ_STYLES}{RA_STYLES}</head>
    <body>{_nav()}
    <main>
      {alert_html}
      <div class="page-top">
        <h1>RA <span>Register</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            showing {len(rows)} of {len(bills)}
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{create_url}" class="btn">+ Create RA Bill</a>
        </div>
      </div>
      {tiles_html}
      <div class="filter-bar">
        <form method="GET" action="{url_for('ra.list_ras')}">
          <input type="search" name="q" value="{_esc(query)}"
                 placeholder="RA no., project, customer or site"/>
          <button type="submit" class="filter-tab">Search</button>
        </form>
      </div>
      {table_html}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · RA register</p></footer>
    </main></body></html>"""
    return BQ._page(template)


@ra_bp.route("/certify/<id>", methods=["GET", "POST"])
def certify_ra(id: str):
    """
    Record certification data from the main contractor.

    Editable ALWAYS, including on bills that are not the latest (the contractor
    certifies late).
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.list_ras", msg="That RA bill no longer exists.", type="error"))

    boq_id = str(bill.get("boq_id") or "")
    claims = bill.get("claims") or []
    status_val = bill.get("status") or "draft"
    cert_on_val = bill.get("certified_on") or ""

    if request.method == "POST":
        status_val = (request.form.get("status") or status_val).strip()
        cert_on_val = (request.form.get("certified_on") or "").strip()

        rows = {}
        for c in claims:
            lid = c.get("line_id", "")
            if not lid:
                continue
            raw_cq = request.form.get(f"cert_qty_{lid}")
            raw_cr = request.form.get(f"cert_rate_{lid}")
            rows[lid] = {
                "certified_qty": _cert_num(raw_cq),
                "certified_rate": _cert_num(raw_cr)
            }

        apply_certification(bill, rows, status=status_val, certified_on=cert_on_val)

        # Check for warnings (certified > claimed)
        warns = certification_warnings(bill.get("claims") or [])
        msg = f"Certification saved for RA{bill.get('ra_no')}."
        msg_type = "success"
        if warns:
            warn_txt = " ".join(certification_warning_message(w) for w in warns[:3])
            msg += f" Note: {warn_txt}"

        return redirect(url_for("ra.view_ra", id=id, msg=msg, type=msg_type))

    # GET form
    rows_html = ""
    for c in claims:
        lid = c.get("line_id", "")
        snap = BQ._item_no(c.get("item_no"))
        cq = c.get("certified_qty")
        cr = c.get("certified_rate")
        cq_str = "" if cq is None else f"{float(cq):g}"
        cr_str = "" if cr is None else f"{float(cr):g}"
        claimed_q = float(c.get("qty") or 0.0)
        claimed_r = float(c.get("rate") or 0.0)

        # Variance calculation if certified_qty is present
        diff_str = "&mdash;"
        if cq is not None:
            diff = float(cq) - claimed_q
            diff_str = f"{diff:+.2f}" if abs(diff) > 1e-6 else "="

        rows_html += f"""
        <tr>
          <td class="cl-no">{_esc(snap)}</td>
          <td class="cl-desc">{_esc(c.get("description"))[:140]}</td>
          <td class="cl-unit">{_esc(c.get("unit"))}</td>
          <td class="cl-num">{BQ._fmt_qty(claimed_q)}</td>
          <td class="cl-num">{_inr(claimed_r)}</td>
          <td class="cl-amt">{_inr(c.get("amount") or 0.0)}</td>
          <td><input type="text" name="cert_qty_{_esc(lid)}" value="{_esc(cq_str)}" placeholder="blank = uncertified" style="width:110px;padding:3px 6px;font-size:0.85rem;"/></td>
          <td><input type="text" name="cert_rate_{_esc(lid)}" value="{_esc(cr_str)}" placeholder="blank = claimed rate" style="width:110px;padding:3px 6px;font-size:0.85rem;"/></td>
          <td class="cl-num" style="font-weight:600;">{diff_str}</td>
        </tr>"""

    st_opts = "".join(f'<option value="{st}"{" selected" if st == status_val else ""}>{st.title()}</option>' for st in STATUSES)

    return _shell(f"Certify RA{bill.get('ra_no')}", f"""
  <div class="page-top">
    <h1>Certify <span>RA{_esc(bill.get('ra_no'))}</span></h1>
    <div><a href="{url_for('ra.view_ra', id=id)}" class="btn btn-ghost">&#8592; View Bill</a></div>
  </div>
  <form method="POST" action="{url_for('ra.certify_ra', id=id)}">
    <div class="ra-meta">
      <div class="ra-fact"><b>Ref</b><span>{_esc(bill.get('ref'))}</span></div>
      <div class="ra-fact"><b>BOQ</b><span>{_esc(bill.get('boq_ref'))}</span></div>
      <div class="ra-fact"><b>Project</b><span>{_esc(bill.get('project_name'))}</span></div>
      <div class="ra-fact"><b>Status</b>
        <span><select name="status" style="padding:2px 6px;font-size:0.85rem;">{st_opts}</select></span>
      </div>
      <div class="ra-fact"><b>Certified Date</b>
        <span><input type="date" name="certified_on" value="{_esc(cert_on_val)}" style="padding:2px 6px;font-size:0.85rem;"/></span>
      </div>
    </div>
    <div class="form-section" style="margin-top:1rem;">
      <div class="section-title">&#9998; Certified Quantities &amp; Rates</div>
      <p style="font-size:0.8rem;color:var(--muted);margin-bottom:0.8rem;">
        Blank certified quantity means <em>not yet ruled on</em>. A typed <code>0</code> means <em>certified at zero</em>.
      </p>
      <div class="cl-wrap"><table class="claims">
        <thead><tr>
          <th>Item</th><th>Description</th><th>Unit</th>
          <th style="text-align:right;">Claimed Qty</th>
          <th style="text-align:right;">Claimed Rate</th>
          <th style="text-align:right;">Claimed Amount</th>
          <th>Certified Qty</th>
          <th>Certified Rate</th>
          <th style="text-align:right;">Variance</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table></div>
      <div style="margin-top:1.2rem;display:flex;gap:0.8rem;">
        <button type="submit" class="btn">Save Certification</button>
        <a href="{url_for('ra.view_ra', id=id)}" class="btn btn-ghost">Cancel</a>
      </div>
    </div>
  </form>""")


@ra_bp.route("/create", methods=["GET", "POST"])
def create_ra():
    """
    Raise a new RA bill against a BOQ.

    `ra_no` is assigned HERE, on save, and never typed. That is what makes
    "RA5 before RA4" and "two RA6s" impossible rather than merely rejected —
    there is no input to reject.

    **One leg per bill, by construction.** The leg is a property of the bill,
    chosen once before any quantity is entered; a claim row carries a quantity
    and a rate and has no leg of its own. There is no shape in which a
    mixed-leg bill can be expressed, which is a stronger guarantee than a UI
    that merely discourages one.
    """
    BQ.ensure_demo_boq()
    boqs = STORE["boqs"]

    boq_id = (request.values.get("boq") or "").strip()
    leg = (request.values.get("leg") or "supply").strip()
    if leg not in LEGS:
        leg = "supply"

    # No BOQ chosen yet — pick one. Only the LATEST revision of each chain is
    # offered: a claim is measured against what is approved now, and raising a
    # bill against a superseded revision would measure it against a schedule
    # that has already been replaced.
    if boq_id not in boqs:
        latest_ids = {latest_revision(bid) for bid in boqs}
        rows = "".join(
            f'<tr><td class="cl-no">{_esc(b.get("ref"))}</td>'
            f'<td class="cl-desc">{_esc(b.get("project_name"))}</td>'
            f'<td class="cl-num">{_esc(b.get("rev_no") or 0)}</td>'
            f'<td class="cl-num">{len(bills_of(bid))}</td>'
            f'<td class="cl-amt">{_inr(b.get("subtotal") or 0.0)}</td>'
            f'<td><a class="btn btn-ghost" href="{url_for("ra.create_ra", boq=bid, leg="supply")}">Supply</a>'
            f' <a class="btn btn-ghost" href="{url_for("ra.create_ra", boq=bid, leg="installation")}">Installation</a></td></tr>'
            for bid, b in sorted(boqs.items(), key=lambda kv: kv[1].get("ref", ""))
            if bid in latest_ids)
        empty = '<tr><td colspan="6">No BOQs yet.</td></tr>'
        return _shell("New RA bill", f"""
  <div class="page-top">
    <h1>New <span>RA bill</span></h1>
    <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">&#8592; All BOQs</a>
  </div>
  {_flash()}
  <div class="form-section">
    <div class="section-title">&#128203; Which schedule is this a claim against?</div>
    <p style="font-size:.8rem;color:var(--muted);margin:.2rem 0 1rem;">
      Pick the BOQ, then the leg. <b>A bill covers one leg</b> &mdash; supply or
      installation, never both. The RA number is assigned when you save.
    </p>
    <div class="cl-wrap"><table class="claims">
      <thead><tr><th>BOQ</th><th>Project</th><th>Rev</th><th>RA bills</th>
      <th style="text-align:right;">Value</th><th>Raise a claim</th></tr></thead>
      <tbody>{rows or empty}</tbody>
    </table></div>
  </div>""")

    boq = boqs[boq_id]
    prev = claimed_by_line(boq_id)
    today = _date.today().isoformat()
    error, entered = "", {}
    date_val = today
    notes_val = ""

    if request.method == "POST":
        date_val = (request.form.get("date") or today).strip()
        notes_val = (request.form.get("notes") or "").strip()
        claims, raw_lines, error = _validate(
            request.form.get("ra_json", ""), boq, leg, prev)
        entered = _posted(raw_lines)

        tax_invoice_ref = (request.form.get("tax_invoice_ref") or "").strip()
        def_po_ref, def_po_date = previous_bill_po_defaults(boq_id)
        po_ref = (request.form.get("po_ref") if request.form.get("po_ref") is not None else def_po_ref).strip()
        po_date = (request.form.get("po_date") if request.form.get("po_date") is not None else def_po_date).strip()
        tax_type = (request.form.get("tax_type") or "cgst_sgst").strip()
        cgst_rate = float(BQ._num(request.form.get("cgst_rate"), 9.0))
        sgst_rate = float(BQ._num(request.form.get("sgst_rate"), 9.0))
        igst_rate = float(BQ._num(request.form.get("igst_rate"), 18.0))

        if not error:
            rid = new_id()
            tax_info = compute_tax_totals(claims, [], tax_type=tax_type,
                                          cgst_rate=cgst_rate, sgst_rate=sgst_rate,
                                          igst_rate=igst_rate)
            STORE["ra_bills"][rid] = {
                "id": rid,
                "ref": next_ref(date_val),
                "fy": P.fy_of(date_val),
                "date": date_val,
                "tax_invoice_ref": tax_invoice_ref,
                "tax_invoice_date": date_val,
                "po_ref": po_ref,
                "po_date": po_date,
                "boq_id": boq_id,
                "boq_ref": boq.get("ref", ""),
                "boq_rev_no": int(boq.get("rev_no") or 0),
                "ra_no": next_ra_no(boq_id),
                "leg": leg,
                "project_name": boq.get("project_name", ""),
                "site_location": boq.get("site_location", ""),
                "account_name": boq.get("account_name", ""),
                "contact_person": boq.get("contact_person", ""),
                "to": boq.get("to", ""),
                "bill_gstin": boq.get("bill_gstin", ""),
                "claims": claims,
                "claim_subtotal": tax_info["claim_subtotal"],
                "deductions": tax_info["deductions"],
                "deduction_total": tax_info["deduction_total"],
                "net_payable": tax_info["net_payable"],
                "tax_type": tax_info["tax_type"],
                "cgst_rate": tax_info["cgst_rate"],
                "sgst_rate": tax_info["sgst_rate"],
                "igst_rate": tax_info["igst_rate"],
                "cgst_amount": tax_info["cgst_amount"],
                "sgst_amount": tax_info["sgst_amount"],
                "igst_amount": tax_info["igst_amount"],
                "tax_amount": tax_info["tax_amount"],
                # The rate-wise breakdown, frozen with the rest of the bill.
                # Stored rather than re-derived at print time for the same
                # reason `cgst_amount` is: the document must not depend on the
                # BOQ's GST rates never being edited. A bill written before this
                # field simply has no key, renders exactly as it always did, and
                # is never backfilled — see ABOUT.md §7 gap 14.
                "tax_slabs": tax_info["tax_slabs"],
                "rounding_off": tax_info["rounding_off"],
                "grand_total": tax_info["grand_total"],
                "status": "draft", "certified_on": "",
                "notes": notes_val,
                "company_branch": "", "auth_signatory": "",
            }
            return redirect(url_for("ra.view_ra", id=rid,
                                    msg="RA bill saved.", type="success"))

    ra_no = next_ra_no(boq_id)
    return _entry_form(
        boq, leg, prev, entered, error,
        action=url_for("ra.create_ra", boq=boq_id, leg=leg),
        ra_no=ra_no,
        back_url=url_for("boq.view_boq", id=boq_id),
        date_val=date_val, notes_val=notes_val,
        submit_label="Save RA bill")


@ra_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_ra(id: str):
    """
    Edit a bill's CLAIM — allowed only while it is the latest bill for its BOQ.

    `claimed_by_line()` sums the whole chain, so editing a mid-chain bill
    silently changes every downstream balance, including ones already printed
    and handed to the main contractor. Latest-only bounds the recompute to one
    bill and keeps printed history true.

    The certificate is a separate permission and is NOT gated here — see
    `apply_certification()`. Its entry UI is step 3.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.create_ra",
                                msg="That RA bill no longer exists.", type="error"))

    if claim_is_frozen(bill):
        return redirect(url_for("ra.view_ra", id=id,
                                msg=frozen_reason(bill), type="error"))

    boq_id = str(bill.get("boq_id") or "")
    boq = STORE["boqs"].get(boq_id)
    if not boq:
        return redirect(url_for("ra.view_ra", id=id,
                                msg="The BOQ this bill was raised against is gone.",
                                type="error"))

    leg = bill.get("leg", "supply")
    # This bill's own figures are excluded, so the cumulative shown is "what
    # everyone else has claimed" and editing it does not block against itself.
    prev = claimed_by_line(boq_id, exclude_ra_id=id)

    error = ""
    entered = {c["line_id"]: {"qty": BQ._fmt_qty(c.get("qty")),
                              "rate": f'{float(c.get("rate") or 0.0):g}'}
               for c in bill.get("claims") or [] if c.get("line_id")}
    date_val = bill.get("date", "")
    notes_val = bill.get("notes", "")

    if request.method == "POST":
        date_val = (request.form.get("date") or date_val).strip()
        notes_val = (request.form.get("notes") or "").strip()
        claims, raw_lines, error = _validate(
            request.form.get("ra_json", ""), boq, leg, prev, exclude_ra_id=id)
        entered = _posted(raw_lines)

        if not error:
            tax_invoice_ref = (request.form.get("tax_invoice_ref") or bill.get("tax_invoice_ref") or "").strip()
            po_ref = (request.form.get("po_ref") if request.form.get("po_ref") is not None else bill.get("po_ref", "")).strip()
            po_date = (request.form.get("po_date") if request.form.get("po_date") is not None else bill.get("po_date", "")).strip()
            tax_type = (request.form.get("tax_type") or bill.get("tax_type") or "cgst_sgst").strip()
            cgst_rate = float(BQ._num(request.form.get("cgst_rate"), bill.get("cgst_rate", 9.0)))
            sgst_rate = float(BQ._num(request.form.get("sgst_rate"), bill.get("sgst_rate", 9.0)))
            igst_rate = float(BQ._num(request.form.get("igst_rate"), bill.get("igst_rate", 18.0)))

            tax_info = compute_tax_totals(claims, bill.get("deductions") or [],
                                          tax_type=tax_type, cgst_rate=cgst_rate,
                                          sgst_rate=sgst_rate, igst_rate=igst_rate)
            bill["claims"] = claims
            bill["claim_subtotal"] = tax_info["claim_subtotal"]
            bill["deductions"] = tax_info["deductions"]
            bill["deduction_total"] = tax_info["deduction_total"]
            bill["net_payable"] = tax_info["net_payable"]
            bill["tax_type"] = tax_info["tax_type"]
            bill["cgst_rate"] = tax_info["cgst_rate"]
            bill["sgst_rate"] = tax_info["sgst_rate"]
            bill["igst_rate"] = tax_info["igst_rate"]
            bill["cgst_amount"] = tax_info["cgst_amount"]
            bill["sgst_amount"] = tax_info["sgst_amount"]
            bill["igst_amount"] = tax_info["igst_amount"]
            bill["tax_amount"] = tax_info["tax_amount"]
            bill["tax_slabs"] = tax_info["tax_slabs"]
            bill["rounding_off"] = tax_info["rounding_off"]
            bill["grand_total"] = tax_info["grand_total"]
            bill["tax_invoice_ref"] = tax_invoice_ref
            bill["po_ref"] = po_ref
            bill["po_date"] = po_date
            bill["date"] = date_val
            bill["notes"] = notes_val
            return redirect(url_for("ra.view_ra", id=id,
                                    msg="RA bill updated.", type="success"))

    return _entry_form(
        boq, leg, prev, entered, error,
        action=url_for("ra.edit_ra", id=id),
        ra_no=bill.get("ra_no"),
        back_url=url_for("ra.view_ra", id=id),
        date_val=date_val, notes_val=notes_val,
        submit_label="Save changes")


@ra_bp.route("/view/<id>")
def view_ra(id: str):
    """
    One RA bill on screen.

    **Not the printed document** — that is step 4, and this deliberately is not
    it: no A4 sheet, no letterhead, no `VIEW_DOC_STYLES`. This is the page you
    land on after saving, and the one `boq.view_boq()`'s RA chips point at.

    Item numbers here are the ones SNAPSHOT on each claim row, not the BOQ's
    current numbers. A revision may renumber freely, and this page is a record
    of what was claimed — so it shows what the bill said when it was made, and
    flags any line whose number has since moved rather than silently adopting
    the new one.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.create_ra",
                                msg="That RA bill no longer exists.", type="error"))

    boq_id = str(bill.get("boq_id") or "")
    live = approved_labels(boq_id)
    frozen = claim_is_frozen(bill)
    cert = certification_summary(bill)

    rows = []
    for c in bill.get("claims") or []:
        lid = c.get("line_id", "")
        snap = BQ._item_no(c.get("item_no"))
        now = live.get(lid, "")
        # The snapshot is what prints. A divergence is shown beside it rather
        # than replacing it — the document said 17 and must go on saying 17.
        moved = (f' <span class="fh-sec" title="Renumbered by a later BOQ '
                 f'revision">(now {_esc(now)})</span>') if now and now != snap else ""
        warn = ' &#9888;' if c.get("rate_varies") else ""
        cq = _cert_num(c.get("certified_qty"))
        rows.append(
            f'<tr><td class="cl-no">{_esc(snap)}{moved}</td>'
            f'<td class="cl-desc">{_esc(c.get("description"))[:160]}</td>'
            f'<td class="cl-unit">{_esc(c.get("unit"))}</td>'
            f'<td class="cl-num">{_qty(c.get("approved_qty"))}</td>'
            f'<td class="cl-num">{_qty(c.get("prev_qty"))}</td>'
            f'<td class="cl-num">{_qty(c.get("qty"))}</td>'
            f'<td class="cl-num">{_inr(c.get("rate") or 0.0)}{warn}</td>'
            f'<td class="cl-num">{_qty(c.get("balance_qty"))}</td>'
            f'<td class="cl-num">{"&mdash;" if cq is None else _qty(cq)}</td>'
            f'<td class="cl-amt">{_inr(c.get("amount") or 0.0)}</td></tr>')

    varies = sum(1 for c in bill.get("claims") or [] if c.get("rate_varies"))
    rate_note = ""
    if varies:
        rate_note = (
            f'<div class="form-hint"><span class="fh-icon">&#9888;</span>'
            f'<span><b>{varies} line{"" if varies == 1 else "s"} claimed at a '
            f'rate that differs from the approved BOQ.</b> That is allowed &mdash; '
            f'rates legitimately move on approved variations &mdash; and is '
            f'recorded on the bill rather than blocked.</span></div>')

    frozen_html = (f'<div class="frozen-note"><span>&#128274;</span>'
                   f'<span>{_esc(frozen_reason(bill))}</span></div>') if frozen else ""

    allowed, why = can_delete(bill)
    del_btn = (f'<a class="btn btn-ghost" href="{url_for("ra.delete_ra", id=id)}">'
               f'Delete</a>') if allowed else (
        f'<span class="btn btn-ghost" style="opacity:.55;cursor:not-allowed;" '
        f'title="{_esc(why)}">Delete</span>')
    edit_btn = ("" if frozen else
                f'<a class="btn btn-ghost" href="{url_for("ra.edit_ra", id=id)}">Edit claim</a>')
    cert_btn = f'<a class="btn btn-ghost" href="{url_for("ra.certify_ra", id=id)}">&#9998; Certify</a>'
    print_btn = f'<a class="btn" href="{url_for("ra.print_ra", id=id)}" style="background:#0284c7;color:#fff;border:none;">&#128438; Print / Tax Invoice</a>'

    return _shell(f"RA{bill.get('ra_no')}", f"""
  <div class="page-top">
    <h1>RA{_esc(bill.get('ra_no'))} <span>&middot; {_esc(bill.get('leg'))}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.view_boq', id=boq_id)}" class="btn btn-ghost">&#8592; BOQ</a>
      {edit_btn}{cert_btn}{print_btn}{del_btn}
    </div>
  </div>
  {_flash()}
  {frozen_html}
  {rate_note}
  <div class="ra-meta">
    <div class="ra-fact"><b>Our reference</b><span>{_esc(bill.get('ref'))}</span></div>
    <div class="ra-fact"><b>Date</b><span>{_esc(bill.get('date'))}</span></div>
    <div class="ra-fact"><b>Against</b><span>{_esc(bill.get('boq_ref'))} &middot; rev {_esc(bill.get('boq_rev_no'))}</span></div>
    <div class="ra-fact"><b>Project</b><span>{_esc(bill.get('project_name'))}</span></div>
    <div class="ra-fact"><b>Status</b><span>{_esc(bill.get('status') or 'draft')}</span></div>
    <div class="ra-fact"><b>Certified</b><span>{cert['certified']} of {cert['total']} lines</span></div>
  </div>
  <div class="form-section">
    <div class="section-title">&#128200; Claim</div>
    <div class="cl-wrap"><table class="claims">
      <thead><tr>
        <th>Item</th><th>Description</th><th>Unit</th>
        <th style="text-align:right;">Approved</th>
        <th style="text-align:right;">Previous</th>
        <th style="text-align:right;">This claim</th>
        <th style="text-align:right;">Rate</th>
        <th style="text-align:right;">Balance</th>
        <th style="text-align:right;">Certified</th>
        <th style="text-align:right;">Amount</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table></div>
    <div class="ra-foot">
      <span><b>Claim total</b> <span class="ra-tot">{_inr(bill.get('claim_subtotal') or 0.0)}</span></span>
      <span><b>Deductions</b> <span class="ra-tot">{_inr(bill.get('deduction_total') or 0.0)}</span></span>
      <span><b>Net payable</b> <span class="ra-tot">{_inr(bill.get('net_payable') or 0.0)}</span></span>
    </div>
  </div>
  <div class="form-section">
    <div class="section-title">&#9986; Deductions</div>
    {_deductions_block(bill)}
  </div>
  <p style="font-size:.75rem;color:var(--muted);">
    This is a working view. <a href="{url_for('ra.print_ra', id=id)}">Click here to view/print the Tax Invoice</a>.
  </p>""")


@ra_bp.route("/print/<id>")
def print_ra(id: str):
    """
    The printed RA bill tax invoice document.

    Modeled directly on RA2.pdf (DOMAIN.md §4).
    Carries TAX INVOICE header, seller & buyer GSTINs, PO/WO references,
    per-line HSN/SAC codes, CGST/SGST/IGST breakdown, Rounding Off,
    Grand Total, Amount in Words, and Bank details.

    **Every value on this page comes from the bill's own record.** That is the
    whole point of the snapshot: an issued tax invoice must render identically
    after the BOQ it was measured against is revised. The only thing read from
    the live BOQ is the specification-header *relation* — see the line table
    below — and `test_ra_print_immutability.py` asserts the property end to end.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.list_ras", msg="That RA bill no longer exists.", type="error"))

    boq_id = str(bill.get("boq_id") or "")
    boq = STORE["boqs"].get(boq_id) or {}
    claims = bill.get("claims") or []

    # Tax & monetary details (from stored record)
    tax_type = bill.get("tax_type", "cgst_sgst")
    cgst_rate = float(bill.get("cgst_rate") or 9.0)
    sgst_rate = float(bill.get("sgst_rate") or 9.0)
    igst_rate = float(bill.get("igst_rate") or 18.0)

    cgst_amount = float(bill.get("cgst_amount") or 0.0)
    sgst_amount = float(bill.get("sgst_amount") or 0.0)
    igst_amount = float(bill.get("igst_amount") or 0.0)
    tax_amount = float(bill.get("tax_amount") or (cgst_amount + sgst_amount + igst_amount))

    claim_subtotal = float(bill.get("claim_subtotal") or 0.0)
    deductions = bill.get("deductions") or []
    deduction_total = float(bill.get("deduction_total") or 0.0)
    net_payable = float(bill.get("net_payable") or (claim_subtotal - deduction_total))
    rounding_off = float(bill.get("rounding_off") or 0.0)
    grand_total = float(bill.get("grand_total") or (net_payable + tax_amount + rounding_off))

    # `quotation._amount_in_words()` already returns its own "INR " prefix —
    # the document printed "INR INR Nine Lakh …" until this stopped adding one.
    words = _amount_in_words(grand_total)

    # References
    tax_inv_ref = bill.get("tax_invoice_ref") or bill.get("ref") or f"SF/RA/{bill.get('fy') or '26-27'}/{int(bill.get('ra_no') or 1):04d}"
    tax_inv_date = bill.get("tax_invoice_date") or bill.get("date") or ""
    # (`po_ref` / `po_date` are rendered below as `po_ref_disp` / `po_date_disp`,
    # which escape as well as defaulting. There is deliberately no second,
    # unescaped pair of the same name sitting here waiting to be picked up.)

    # Company & Customer details.
    #
    # No `or boq.get(...)` fallback on any of these. `create_ra()` copies all six
    # onto the bill at issue precisely so the document does not depend on the
    # schedule still saying the same thing; reading the live BOQ when the copy is
    # blank reintroduces exactly that dependency, and it does it silently on the
    # only bills where it can matter. A blank copy prints an em dash and says so.
    #
    # The seller half is read from `branding`, which is where `/settings` puts
    # the company identity — the same module and the same render-time read the
    # bank block below already uses. It carried a hardcoded GSTIN and a
    # hardcoded State until this, and printed both on the face of a tax invoice
    # — a document saying the company supplies from somewhere it has never
    # traded. `tests/test_ra_seller_identity.py` fails if either comes back,
    # which is why neither is named here even in a comment.
    # There is no fallback behind these on purpose: a fallback is how a literal
    # survives, and an identity this document cannot read is a thing the
    # operator must see and go fix at /settings.
    #
    # The State is DERIVED from the GSTIN rather than stored beside it — the
    # first two digits are the State of registration by construction, so there
    # is no second field to disagree with the first. `invoice._supplier_state()`
    # reaches the same answer the same way on the sell side; the table itself
    # lives in `pipeline.py` because neither chain may import the other.
    seller_gstin_disp = _esc(B.COMPANY_GSTIN or "") or "&mdash;"
    seller_state_disp = _esc(P.gstin_state_label(B.COMPANY_GSTIN)) or "&mdash;"
    seller_addr_disp = _esc(B.COMPANY_ADDR or "") or "&mdash;"
    buyer_name_disp = _esc(bill.get("account_name") or "") or "&mdash;"
    buyer_gstin_disp = _esc(bill.get("bill_gstin") or "") or "&mdash;"
    project_name_disp = _esc(bill.get("project_name") or "") or "&mdash;"
    site_location_disp = _esc(bill.get("site_location") or "") or "&mdash;"
    contact_person_disp = _esc(bill.get("contact_person") or "") or "&mdash;"
    to_address_disp = _esc(bill.get("to") or "") or "&mdash;"
    po_ref_disp = _esc(bill.get("po_ref") or "") or "&mdash;"
    po_date_disp = _esc(bill.get("po_date") or "") or "&mdash;"

    # ── The line table ─────────────────────────────────────────────────────
    #
    # **Driven by `bill["claims"]`, never by the BOQ's live `line_items`.** This
    # is an issued tax invoice, and every figure, unit, description, item number
    # and HSN/SAC on it is the snapshot taken at save (ABOUT.md §3) — the same
    # rule `/ra/view` already follows. Iterating the BOQ instead made the
    # document a view of the *current* schedule three ways at once: it printed
    # the live item number over the snapshot, it reordered with the BOQ, and a
    # line dropped from the BOQ vanished from the table while its amount stayed
    # inside the Claim Subtotal — an invoice whose rows did not add up to its
    # own total.
    #
    # The BOQ is consulted for exactly ONE thing: **which specification header a
    # claimed line sits under.** That is a relation (`parent_item_no`), not a
    # value, and no claim row carries it. Nothing else is read from there.
    live_lines = boq.get("line_items") or []
    live_by_lid, headers_by_key = {}, {}
    for li in live_lines:
        if li.get("is_header"):
            headers_by_key[(str(li.get("section") or ""),
                            BQ._item_no(li.get("item_no")))] = li
            continue
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            live_by_lid[lid] = li

    table_rows_html = ""
    last_header_key = None
    for idx, c in enumerate(claims, 1):
        # The header lookup. Only the relation crosses over — the claim's own
        # id resolves to its BOQ line, whose `parent_item_no` names the header.
        src = live_by_lid.get(BQ._line_id(c.get("line_id"))) or {}
        parent = BQ._item_no(src.get("parent_item_no"))
        header_key = (str(src.get("section") or ""), parent) if parent else None
        hdr = headers_by_key.get(header_key) if header_key else None

        if hdr is not None and header_key != last_header_key:
            # Printed in full, never truncated — `boq.view_boq()` prints the
            # same paragraph in full, and an ellipsis in the middle of a
            # specification clause on a tax invoice is a document that says
            # something other than what was agreed.
            table_rows_html += f"""
                <tr style="background:#f8fafc;font-weight:700;">
                  <td style="text-align:center;"></td>
                  <td style="font-weight:700;color:var(--navy);">{_esc(BQ._item_no(hdr.get("item_no")))}</td>
                  <td colspan="6" style="font-weight:700;color:var(--navy);">{_esc((hdr.get("description") or "").strip())}</td>
                </tr>"""
        last_header_key = header_key

        hsn_sac = (c.get("hsn_sac") or "").strip()
        hsn_display = _esc(hsn_sac) if hsn_sac else '<span class="status-badge" style="background:#fffbeb;color:#b45309;border:1px solid #fde68a;padding:1px 5px;border-radius:4px;font-size:0.7rem;">Blank HSN/SAC</span>'
        qty = float(c.get("qty") or 0.0)
        rate = float(c.get("rate") or 0.0)
        amt = float(c.get("amount") or (qty * rate))

        table_rows_html += f"""
            <tr>
              <td style="text-align:center;">{idx}</td>
              <td style="font-weight:600;">{_esc(BQ._item_no(c.get('item_no')))}</td>
              <td>{_esc(c.get('description'))}</td>
              <td style="text-align:center;">{hsn_display}</td>
              <td style="text-align:center;">{_esc(c.get('unit'))}</td>
              <td style="text-align:right;">{BQ._fmt_qty(qty)}</td>
              <td style="text-align:right;">&#8377;&nbsp;{rate:,.2f}</td>
              <td style="text-align:right;font-weight:600;">&#8377;&nbsp;{amt:,.2f}</td>
            </tr>"""

    # Deductions block rows
    deductions_rows_html = ""
    for d in deductions:
        lbl = d.get("label") or d.get("code") or "Deduction"
        damt = float(d.get("amount") or 0.0)
        deductions_rows_html += f"""
        <tr>
          <td colspan="7" style="text-align:right;color:var(--muted);">{_esc(lbl)}:</td>
          <td style="text-align:right;color:#dc2626;">- &#8377;&nbsp;{damt:,.2f}</td>
        </tr>"""

    # Tax block rows
    #
    # A bill at ONE rate — which is every bill the client has actually sent us —
    # prints exactly the markup it always has: `CGST @ 9%` over its amount. That
    # is the format they recognise and it is deliberately not modernised.
    #
    # A bill mixing rates cannot state a single one, so it gains a rate-wise
    # breakdown above the totals and the total lines drop their rate label. The
    # slabs are read off the RECORD (`tax_slabs`, frozen at save) and never
    # recomputed here — the same rule as every other figure on this sheet. A
    # bill written before that field has no key, so `slabs` is empty, `multi` is
    # False, and it renders byte-for-byte as it did the day it was issued.
    slabs = bill.get("tax_slabs") or []
    multi = len(slabs) > 1

    igst_label = "Total IGST" if multi else f"IGST @ {igst_rate:g}%"
    cgst_label = "Total CGST" if multi else f"CGST @ {cgst_rate:g}%"
    sgst_label = "Total SGST" if multi else f"SGST @ {sgst_rate:g}%"

    if tax_type == "igst":
        tax_rows_html = f"""
        <tr>
          <td colspan="7" style="text-align:right;font-weight:500;">{igst_label}:</td>
          <td style="text-align:right;font-weight:600;">&#8377;&nbsp;{igst_amount:,.2f}</td>
        </tr>"""
    else:
        tax_rows_html = f"""
        <tr>
          <td colspan="7" style="text-align:right;font-weight:500;">{cgst_label}:</td>
          <td style="text-align:right;font-weight:600;">&#8377;&nbsp;{cgst_amount:,.2f}</td>
        </tr>
        <tr>
          <td colspan="7" style="text-align:right;font-weight:500;">{sgst_label}:</td>
          <td style="text-align:right;font-weight:600;">&#8377;&nbsp;{sgst_amount:,.2f}</td>
        </tr>"""

    if multi:
        slab_rows_html = ""
        for s in slabs:
            codes = ", ".join(s.get("hsn_sac") or [])
            hsn_note = f" &middot; {_esc(codes)}" if codes else ""
            rate_pct = float(s.get("gst_rate") or 0.0)
            if tax_type == "igst":
                heads = f"IGST {float(s.get('igst_rate') or 0.0):g}%"
                head_amt = float(s.get("igst_amount") or 0.0)
            else:
                heads = (f"CGST {float(s.get('cgst_rate') or 0.0):g}% + "
                         f"SGST {float(s.get('sgst_rate') or 0.0):g}%")
                head_amt = float(s.get("tax_amount") or 0.0)
            slab_rows_html += f"""
        <tr>
          <td colspan="5" style="text-align:right;color:var(--muted);">
            Taxable @ {rate_pct:g}% ({heads}){hsn_note}:
          </td>
          <td colspan="2" style="text-align:right;">&#8377;&nbsp;{float(s.get('taxable_value') or 0.0):,.2f}</td>
          <td style="text-align:right;font-weight:600;">&#8377;&nbsp;{head_amt:,.2f}</td>
        </tr>"""
        tax_rows_html = slab_rows_html + tax_rows_html

    rounding_html = ""
    if abs(rounding_off) > 1e-4:
        rounding_html = f"""
        <tr>
          <td colspan="7" style="text-align:right;color:var(--muted);">Rounding Off:</td>
          <td style="text-align:right;font-weight:500;">&#8377;&nbsp;{rounding_off:+.2f}</td>
        </tr>"""

    # Document html
    html = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title(f"TAX INVOICE — RA{bill.get('ra_no')}")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}
    <style>
      @media print {{
        .no-print {{ display: none !important; }}
        body {{ background: #fff !important; padding: 0 !important; }}
        .doc-paper {{ box-shadow: none !important; margin: 0 !important; width: 100% !important; max-width: 100% !important; border: none !important; }}
      }}
      .doc-paper {{ background: #fff; max-width: 900px; margin: 1.5rem auto; padding: 2.5rem; border: 1px solid #cbd5e1; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); font-family: Inter, system-ui, sans-serif; color: #1e293b; }}
      .doc-header {{ text-align: center; border-bottom: 2px solid #0f172a; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
      .doc-header h1 {{ font-size: 1.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #0f172a; margin: 0; }}
      .doc-header p {{ font-size: 0.85rem; color: #475569; margin-top: 0.2rem; }}
      .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }}
      .box-card {{ border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; background: #f8fafc; font-size: 0.85rem; line-height: 1.5; }}
      .box-card b {{ color: #0f172a; display: inline-block; min-width: 110px; }}
      table.doc-table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.85rem; }}
      table.doc-table th, table.doc-table td {{ border: 1px solid #cbd5e1; padding: 8px 10px; }}
      table.doc-table th {{ background: #f1f5f9; color: #0f172a; font-weight: 700; text-align: left; }}
      .doc-summary {{ margin-top: 1.5rem; display: flex; justify-content: space-between; align-items: flex-start; gap: 2rem; font-size: 0.85rem; }}
      .bank-card {{ border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; background: #f8fafc; flex: 1; }}
      .sig-card {{ text-align: center; width: 220px; border-top: 1px dashed #94a3b8; padding-top: 3.5rem; font-weight: 600; color: #475569; font-size: 0.8rem; }}
    </style>
    </head>
    <body>
      <div class="no-print" style="max-width:900px;margin:1rem auto 0;display:flex;justify-content:space-between;align-items:center;">
        <div>
          <a href="{url_for('ra.view_ra', id=id)}" class="btn btn-ghost">&#8592; Back to RA View</a>
          <a href="{url_for('ra.list_ras')}" class="btn btn-ghost" style="margin-left:0.4rem;">RA Register</a>
        </div>
        <button onclick="window.print()" class="btn" style="background:#0284c7;color:#fff;border:none;">&#128438; Print / Save PDF</button>
      </div>

      <div class="doc-paper">
        <div class="doc-header">
          <h1>TAX INVOICE</h1>
          <p>{B.COMPANY_NAME} &middot; {B.COMPANY_TAGLINE}</p>
        </div>

        <div class="grid-2">
          <div class="box-card">
            <div style="font-weight:700;font-size:0.95rem;color:#0f172a;margin-bottom:0.4rem;border-bottom:1px solid #e2e8f0;padding-bottom:0.3rem;">Billed By (Supplier)</div>
            <b>Name:</b> {_esc(B.COMPANY_LEGAL or B.COMPANY_NAME)}<br/>
            <b>GSTIN:</b> {seller_gstin_disp}<br/>
            <b>State:</b> {seller_state_disp}<br/>
            <b>Address:</b> {seller_addr_disp}
          </div>
          <div class="box-card">
            <div style="font-weight:700;font-size:0.95rem;color:#0f172a;margin-bottom:0.4rem;border-bottom:1px solid #e2e8f0;padding-bottom:0.3rem;">Invoice &amp; Bill Details</div>
            <b>Tax Invoice Ref:</b> {_esc(tax_inv_ref)}<br/>
            <b>Invoice Date:</b> {_esc(tax_inv_date)}<br/>
            <b>RA Bill No:</b> RA{_esc(bill.get('ra_no'))} ({_esc(bill.get('leg'))})<br/>
            <b>PO/WO No &amp; Date:</b> {po_ref_disp} ({po_date_disp})
          </div>
        </div>

        <div class="grid-2">
          <div class="box-card">
            <div style="font-weight:700;font-size:0.95rem;color:#0f172a;margin-bottom:0.4rem;border-bottom:1px solid #e2e8f0;padding-bottom:0.3rem;">Billed To (Customer)</div>
            <b>Customer:</b> {buyer_name_disp}<br/>
            <b>GSTIN:</b> {buyer_gstin_disp}<br/>
            <b>Contact:</b> {contact_person_disp}<br/>
            <b>Address:</b> {to_address_disp}
          </div>
          <div class="box-card">
            <div style="font-weight:700;font-size:0.95rem;color:#0f172a;margin-bottom:0.4rem;border-bottom:1px solid #e2e8f0;padding-bottom:0.3rem;">Project &amp; Site Details</div>
            <b>Project Name:</b> {project_name_disp}<br/>
            <b>Site Location:</b> {site_location_disp}<br/>
            <b>BOQ Ref:</b> {_esc(bill.get('boq_ref'))} (Rev {_esc(bill.get('boq_rev_no'))})
          </div>
        </div>

        <table class="doc-table">
          <thead>
            <tr>
              <th style="width:40px;text-align:center;">#</th>
              <th style="width:70px;">Item No</th>
              <th>Description of Goods / Work Executed</th>
              <th style="width:100px;text-align:center;">HSN / SAC</th>
              <th style="width:60px;text-align:center;">Unit</th>
              <th style="width:90px;text-align:right;">Claim Qty</th>
              <th style="width:100px;text-align:right;">Rate</th>
              <th style="width:120px;text-align:right;">Amount</th>
            </tr>
          </thead>
          <tbody>
            {table_rows_html}
            <tr>
              <td colspan="7" style="text-align:right;font-weight:600;">Claim Subtotal:</td>
              <td style="text-align:right;font-weight:600;">&#8377;&nbsp;{claim_subtotal:,.2f}</td>
            </tr>
            {deductions_rows_html}
            <tr>
              <td colspan="7" style="text-align:right;font-weight:700;background:#f8fafc;">Taxable Net Payable Value:</td>
              <td style="text-align:right;font-weight:700;background:#f8fafc;">&#8377;&nbsp;{net_payable:,.2f}</td>
            </tr>
            {tax_rows_html}
            {rounding_html}
            <tr style="font-size:0.95rem;background:#f1f5f9;">
              <td colspan="7" style="text-align:right;font-weight:800;color:#0f172a;">Grand Total (Inclusive of Taxes):</td>
              <td style="text-align:right;font-weight:800;color:#0f172a;">&#8377;&nbsp;{grand_total:,.2f}</td>
            </tr>
          </tbody>
        </table>

        <div style="margin-top:1rem;padding:0.8rem;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;font-size:0.85rem;">
          <b>Amount in Words:</b> {_esc(words)}
        </div>

        <div class="doc-summary">
          <div class="bank-card">
            <div style="font-weight:700;color:#0f172a;margin-bottom:0.3rem;">Bank Details for Remittance</div>
            <b>Bank Name:</b> {_esc(B.BANK_NAME)}<br/>
            <b>A/C No:</b> {_esc(B.BANK_ACCOUNT_NO)}<br/>
            <b>IFSC Code:</b> {_esc(B.BANK_IFSC)}<br/>
            <b>Branch:</b> {_esc(B.BANK_BRANCH)}
          </div>
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;">
            <p style="font-size:0.75rem;color:var(--muted);margin-bottom:2.5rem;">For {_esc(B.COMPANY_NAME)}</p>
            <div class="sig-card">Authorised Signatory</div>
          </div>
        </div>
      </div>
    </body></html>"""
    return html


@ra_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_ra(id: str):
    """
    Delete an RA bill — the highest-numbered one only, and never a certified one.

    **POST-only for the deletion itself.** The GET is a confirmation page that
    names the bill and shows the claimed total being removed, because a link
    that deletes is a link a crawler, a prefetch or a back button can fire.

    ⚠ **This docstring used to claim "there is no GET path in this app that
      destroys anything". That was false when it was written** — `/address/
      delete`, `/product/delete` and `/spec/delete` all destroyed on GET,
      guarded only by a browser `confirm()`, which none of those three actors
      ever sees. All three now follow this route's pattern, so **the claim is
      true of the four delete routes that exist today.**

      Be precise about what holds it true, because this docstring used to lean
      on the sweep for more than the sweep proves.
      `test_no_registered_route_destroys_on_get` walks every registered rule
      whose path contains "delete" and asserts it **accepts POST**. That catches
      a GET-only delete route — the failure mode that existed — but it cannot
      catch a route that accepts both methods and still destroys on GET.

      What actually holds the property, per route, is four hand-written tests
      that issue a real GET and assert the store is unchanged:
      `test_get_on_address_delete_destroys_nothing`,
      `test_get_on_spec_delete_destroys_nothing` and
      `test_get_on_product_delete_destroys_nothing` in
      `tests/test_delete_methods.py`, and `test_a_get_never_deletes_anything`
      in `tests/test_ra_routes.py` for this route. **They do not generalise to a
      fifth route** — a new delete route has to bring its own. See ABOUT.md §7.9f
      for the standing rule.

    After a delete the next bill takes max(ra_no)+1 from what remains, so the
    sequence stays contiguous and a number the client has already seen on a
    claim is never reissued.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.create_ra",
                                msg="That RA bill no longer exists.", type="error"))

    allowed, why = can_delete(bill)
    boq_id = str(bill.get("boq_id") or "")

    if not allowed:
        # Refused with the reason, and the button is never hidden — a control
        # that vanishes teaches nothing about why.
        return redirect(url_for("ra.view_ra", id=id, msg=why, type="error"))

    if request.method == "POST":
        STORE["ra_bills"].pop(id, None)
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg=f"RA{bill.get('ra_no')} deleted.",
                                type="success"))

    n_lines = len(bill.get("claims") or [])
    return _shell(f"Delete RA{bill.get('ra_no')}", f"""
  <div class="page-top"><h1>Delete <span>RA{_esc(bill.get('ra_no'))}</span></h1></div>
  <div class="del-box">
    <h2>&#9888; This cannot be undone</h2>
    <div class="del-line">
      You are about to delete <b>RA{_esc(bill.get('ra_no'))}</b>
      ({_esc(bill.get('ref'))}, {_esc(bill.get('leg'))}), raised on
      {_esc(bill.get('date'))} against {_esc(bill.get('boq_ref'))}.<br/>
      It claims <b>{n_lines} line{"" if n_lines == 1 else "s"}</b> totalling
      <b>{_inr(bill.get('claim_subtotal') or 0.0)}</b>.<br/><br/>
      Those quantities go back onto the balance of every line it claimed, and
      the next bill raised will take the number <b>RA{_esc(bill.get('ra_no'))}</b>
      again.
    </div>
  </div>
  <form method="POST" action="{url_for('ra.delete_ra', id=id)}"
        style="display:flex;gap:.7rem;">
    <button type="submit" class="btn">Delete RA{_esc(bill.get('ra_no'))}</button>
    <a href="{url_for('ra.view_ra', id=id)}" class="btn btn-ghost">Keep it</a>
  </form>""")
