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
    ra.py ──► boq.py        _item_no, _num, _opt_num — the schedule's own guards
    ra.py ──► dashboard.py  BASE_STYLES / _nav
    ra.py ──► pipeline.py   esc / parse_money / fy_of / fy_ref
    ra.py ──► store, branding

`boq.py` must **never** import this module — its view page links out with
`url_for` and reads `STORE["ra_bills"]` directly, the same one-way trick used
four times already. It must not import `proforma.py`, `invoice.py`,
`purchase.py` or `product.py` either.
"""

import uuid

import boq as BQ
import branding as B
import pipeline as P
from store import STORE

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
#   {"item_no": "24.b", "section": "B",
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
    {(item_no, leg): approved_qty} from the LATEST revision in the chain.

    The latest, not the one billed against: a revision exists precisely to
    change what is approved, and the block has to be measured against what is
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
        item = BQ._item_no(li.get("item_no"))
        if not item:
            continue
        qty = float(li.get("total_qty") or 0.0)
        for leg in LEGS:
            out[(item, leg)] = qty
    return out


def approved_rates(boq_id: str) -> dict:
    """{(item_no, leg): approved_rate} from the latest revision."""
    latest = latest_revision(boq_id)
    if not latest:
        return {}
    boq = (STORE.get("boqs") or {}).get(latest) or {}

    out = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        item = BQ._item_no(li.get("item_no"))
        if not item:
            continue
        out[(item, "supply")] = float(li.get("supply_rate") or 0.0)
        out[(item, "installation")] = float(li.get("install_rate") or 0.0)
    return out


def claimed_by_line(boq_id: str, exclude_ra_id: str = None) -> dict:
    """
    {(item_no, leg): qty} summed over every RA bill in the revision chain.

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
            key = (BQ._item_no(c.get("item_no")), leg)
            out[key] = out.get(key, 0.0) + float(c.get("qty") or 0.0)
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
    """
    approved = approved_by_line(boq_id)
    prior = claimed_by_line(boq_id, exclude_ra_id=exclude_ra_id)

    out = []
    for c in claims or []:
        item = BQ._item_no(c.get("item_no"))
        qty = float(c.get("qty") or 0.0)
        if not item or qty <= 0:
            continue

        key = (item, leg)
        if key not in approved:
            out.append({"item_no": item, "leg": leg, "reason": "not_in_boq",
                        "approved": 0.0, "previously": prior.get(key, 0.0),
                        "this": qty, "cumulative": qty, "allowed": 0.0,
                        "over": qty})
            continue

        app = approved[key]
        previously = prior.get(key, 0.0)
        cumulative = previously + qty
        allowed = app * (1.0 + OVERCLAIM_TOLERANCE)
        if round(cumulative - allowed, 6) > _QTY_EPSILON:
            out.append({"item_no": item, "leg": leg, "reason": "overclaim",
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
    """
    q = float(BQ._num(qty, 0.0))
    r = float(BQ._num(rate, 0.0))
    approved_qty = float(boq_line.get("total_qty") or 0.0)
    return {
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
    }


def new_id() -> str:
    return str(uuid.uuid4())
