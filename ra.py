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

⚠ **AN RA BILL IS A CLAIM DOCUMENT, NOT A TAX INVOICE.**

That is a deliberate, commercially scoped decision (PHASE4_RA_DESIGN.md §5), and
it is the first thing to know before editing this file. This module must not
grow Rule 46 fields, a place of supply, a reverse-charge declaration, an
FY-unique statutory serial, e-invoicing — and it must **not import
`quotation._tax_lines()`**. The project tax-invoice chain is a separate module
later. `tests/test_ra_record.py` asserts the absence, because the pull towards
"it has amounts on it, so it should have tax on it" is strong and wrong.

What this module is built around
--------------------------------
**The over-claim block.** A cumulative claim across every RA bill must never
exceed the approved BOQ quantity for that line. Their live spreadsheet has three
lines already billed into negative balance, and catching that is what this
system was sold to do. The block is hard: there is no override anywhere in the
UI, and `OVERCLAIM_TOLERANCE` is the only dial, defaulting to zero.

**The revision chain.** Because the block is hard, the only way through it when
the approved schedule genuinely changes is a BOQ *revision* — a new BOQ record
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
from quotation import QUOTATION_STYLES, _inr

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


def build_claim(boq_line: dict, qty, rate, prev_qty: float,
                approved_rate: float) -> dict:
    """
    One claim row, with every figure that has to survive on the document frozen.

    `amount` is always computed from qty × rate, so a stored amount can never
    disagree with the figures printed beside it — `boq._clean_lines()` makes the
    same call about its own amounts.

    **`item_no` is a SNAPSHOT, taken here and never re-derived.** A revision may
    now renumber freely (PHASE4_RA_DESIGN.md §4 rule 1, withdrawn at step 1.5),
    so a bill printed last month against item 17 would silently re-render as
    item 18 after a revision — quietly changing a document already submitted to
    the main contractor. The claim stores the number as it stood when the claim
    was made and prints that; matching is always on `line_id`. Where a
    *current-state* screen shows a number it uses the live one and says so.
    """
    q = float(BQ._num(qty, 0.0))
    r = float(BQ._num(rate, 0.0))
    approved_qty = float(boq_line.get("total_qty") or 0.0)
    return {
        # The match key, copied off the BOQ line it was raised against. Stored
        # on the claim so the sum survives the line's item number being edited
        # or renumbered by a later revision.
        "line_id":       BQ._line_id(boq_line.get("line_id")),
        "item_no":       BQ._item_no(boq_line.get("item_no")),
        "section":       str(boq_line.get("section") or ""),
        "description":   str(boq_line.get("description") or ""),
        "unit":          str(boq_line.get("unit") or ""),
        "approved_qty":  approved_qty,
        "approved_rate": float(approved_rate or 0.0),
        "prev_qty":      float(prev_qty or 0.0),
        "qty":           q,
        "rate":          r,
        "amount":        round(q * r, 2),
        "balance_qty":   round(approved_qty - float(prev_qty or 0.0) - q, 6),
        "rate_varies":   rate_varies(r, approved_rate),
        # None, NOT 0.0 — "not yet certified" is not "certified at nothing".
        # The entry UI for these is step 3; the shape and the arithmetic are
        # here from the start so the print format never has to be reopened.
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

        out.append(build_claim(src, qty, rate, prev.get((lid, leg), 0.0),
                               rates.get((lid, leg), 0.0)))

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
  .cl-desc  { min-width:220px; }
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

  /* A specification header — context, never claimable. */
  tr.cl-head td { background:#f1f5f9; font-weight:700; color:var(--navy); }

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

/* Only lines with a quantity are posted. Sparse storage: an untouched line
   must not assert a claim of zero it never made. The server drops zeros too —
   this is a courtesy to the wire, not the rule. */
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
    """
    rates = approved_rates(str(boq.get("id") or ""))
    out = []

    for li in boq.get("line_items") or []:
        item = _esc(BQ._item_no(li.get("item_no")))
        desc = _esc(li.get("description") or "")

        if li.get("is_header"):
            out.append(
                f'<tr class="cl-head"><td class="cl-no">{item}</td>'
                f'<td colspan="7">{desc[:300]}</td></tr>')
            continue

        lid = BQ._line_id(li.get("line_id"))
        if not lid:
            continue

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
        <tr class="cl-line{done}" id="row_{lid}"
            data-approved="{approved:g}" data-prev="{claimed:g}" data-rate="{app_rate:g}">
          <td class="cl-no">{item}</td>
          <td class="cl-desc">{desc[:160]}</td>
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
    n, m = bills_certified(str(boq.get("id") or ""))
    return f"""
    <div class="ra-meta">
      <div class="ra-fact"><b>Project</b><span>{_esc(boq.get("project_name"))}</span></div>
      <div class="ra-fact"><b>BOQ</b><span>{_esc(boq.get("ref"))} &middot; rev {_esc(boq.get("rev_no") or 0)}</span></div>
      <div class="ra-fact"><b>Customer</b><span>{_esc(boq.get("account_name"))}</span></div>
      <div class="ra-fact"><b>This bill</b><span>RA{_esc(ra_no)} &middot; {_esc(leg)}</span></div>
      <div class="ra-fact"><b>Certified so far</b><span>{n} of {m} bills</span></div>
    </div>"""


def _entry_form(boq: dict, leg: str, prev: dict, entered: dict, error: str,
                action: str, heading: str, back_url: str, date_val: str,
                notes_val: str, submit_label: str, frozen_note: str = "") -> str:
    """The claim grid, shared by create and edit — one form, two entry points."""
    return _shell(heading, f"""
  <div class="page-top">
    <h1>{heading}</h1>
    <a href="{back_url}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {_alert(error)}
  {frozen_note}
  {_boq_facts(boq, leg, heading)}
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
  <script>var LINE_IDS = {_claim_ids(boq)};</script>
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

        if not error:
            rid = new_id()
            subtotal, drows, dtotal, net = bill_totals(claims, [])
            STORE["ra_bills"][rid] = {
                "id": rid,
                "ref": next_ref(date_val),
                "fy": P.fy_of(date_val),
                "date": date_val,
                # The bill is measured against a SPECIFIC revision, and the ref
                # and rev are stored rather than looked up, so it still reads
                # correctly as a historical document if the BOQ is removed.
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
                "claim_subtotal": subtotal,
                "deductions": drows, "deduction_total": dtotal,
                "net_payable": net,
                # Certification starts empty, and empty is NOT zero. The entry
                # UI is step 3; the shape and arithmetic are here from day one.
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
        heading=f"RA{ra_no}",
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
            subtotal, drows, dtotal, net = bill_totals(
                claims, bill.get("deductions") or [])
            # The claim is rewritten; the CERTIFICATE is not touched here.
            bill["claims"] = claims
            bill["claim_subtotal"] = subtotal
            bill["deductions"] = drows
            bill["deduction_total"] = dtotal
            bill["net_payable"] = net
            bill["date"] = date_val
            bill["notes"] = notes_val
            return redirect(url_for("ra.view_ra", id=id,
                                    msg="RA bill updated.", type="success"))

    return _entry_form(
        boq, leg, prev, entered, error,
        action=url_for("ra.edit_ra", id=id),
        heading=f"RA{bill.get('ra_no')}",
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

    return _shell(f"RA{bill.get('ra_no')}", f"""
  <div class="page-top">
    <h1>RA{_esc(bill.get('ra_no'))} <span>&middot; {_esc(bill.get('leg'))}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.view_boq', id=boq_id)}" class="btn btn-ghost">&#8592; BOQ</a>
      {edit_btn}{del_btn}
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
    This is a working view. The printed RA bill is a later step.
  </p>""")


@ra_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_ra(id: str):
    """
    Delete an RA bill — the highest-numbered one only, and never a certified one.

    **POST-only for the deletion itself.** The GET is a confirmation page that
    names the bill and shows the claimed total being removed; there is no
    GET path in this app that destroys anything, because a link that deletes
    is a link a crawler, a prefetch or a back button can fire.

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
