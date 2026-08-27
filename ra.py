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
# never will be — but **not** because "an RA bill is a claim document, not a tax
# invoice". That premise is dead: the client's real as-submitted RA2 is headed
# TAX INVOICE, this module carries its own per-line tax block, and `/ra/print`
# renders the document as one (DOMAIN.md §4).
#
# The prohibition survives that inversion untouched, on its own three reasons
# (DOMAIN.md §4.9): `_tax_lines` is document-total arithmetic with no per-line
# concept, it decides no tax head, and it lives in a file that may not be
# edited. `tests/test_ra_record.py` asserts the absence at AST level.
from quotation import QUOTATION_STYLES, VIEW_DOC_STYLES, _inr, _amount_in_words

# The printed A4 sheet, shared with every other document this office issues —
# letterhead, party block, items-table shell, totals rows, bank block,
# signature. `docsheet.py` is a LEAF: it imports nothing that prints, so this
# arrow does NOT reopen the `invoice.py` prohibition above. Neither module
# imports the other; both import the leaf (ABOUT.md §2d).
import docsheet as DS
from docsheet import _meta

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

# How money arrived. Defined HERE rather than in receipt.py because
# `view_ra()` renders the mode on the bill's own receipts panel, and receipt.py
# imports ra.py — putting the list there would need the import reversed.
#
# `adjustment` is the one that is not a payment: a credit note, a debit note
# settled against the bill, or a contra entry. It is on the list because the
# client's main contractor settles retention and material recoveries that way
# and the money genuinely stops being outstanding — recording it as `cash`
# would put a bank movement in the ledger that never happened.
RECEIPT_MODES = ("neft", "rtgs", "cheque", "upi", "cash", "adjustment")

RECEIPT_MODE_LABELS = {
    "neft": "NEFT", "rtgs": "RTGS", "cheque": "Cheque",
    "upi": "UPI", "cash": "Cash", "adjustment": "Adjustment",
}

# =============================================================================
# THE LIFECYCLE — three states, and the lock that used to be certification's job
# =============================================================================
#
# Certification was doing two unrelated jobs at once: it was the main
# contractor's RULING on a claim, and it was the only thing stopping a bill that
# had already gone out from being silently edited or deleted. The client asked
# for the ruling to be removed (CLIENT_CHANGES.md item 3). The lock is not
# theirs to remove and it is not the same thing, so it is rebuilt here as an
# explicit lifecycle rather than inherited from a field that no longer exists.
#
#   draft      ours, not yet sent. Editable, deletable (subject to the receipts
#              guard), and it PRINTS WITH A DRAFT MARKER so a working copy can
#              never be mistaken for an issued document.
#   issued     it has gone to the main contractor. `edit_ra` and `delete_ra`
#              both refuse; the document prints clean; money may be receipted
#              against it. This is the state the lock exists for.
#   cancelled  withdrawn. Locked, carries its reason and date, excluded from
#              every total and from outstanding, and CANNOT BE UN-CANCELLED —
#              an un-cancel would make the withdrawal deniable.
#
# **`ra_no` is never reused.** A cancelled RA3 stays RA3 and the next bill is
# RA4, for the reason a GST serial is never reissued: the number has been quoted
# in somebody else's ledger, and a second document bearing it is indistinguish-
# able from the first. `next_ra_no()` is max+1 over EVERY bill in the chain
# including the cancelled ones, which is what makes that true by construction.
STATUSES = ("draft", "issued", "cancelled")

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
# At the line cap: 600 x 79.3 = 46 KB decoded, 75 KB on the wire.
#
# 150,000 is therefore ~3.2x the worst honest payload at today's line cap, while
# 150,000 x 1.61 = 241,500 bytes on the wire leaves ~258 KB of Flask's 500,000
# MAX_FORM_MEMORY_SIZE for the twenty other form fields. The check always fires
# before Werkzeug does.
#
# (This used to carry a second figure for the certified quantity and rate that a
# later step was going to add to each posted line. Certification is gone and
# nothing posts a second pair, so the headroom is the plain 3.2x.)
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
#   # THE LIFECYCLE — see STATUSES above for what each state permits.
#   "status": "draft" | "issued" | "cancelled",
#   "issued_on": "2026-08-12",   # "" until it is issued
#   "cancelled_on": "",          # "" unless cancelled
#   "cancel_reason": "",         # why, in the operator's own words
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
#    client already holds — exactly `proforma.prior_invoiced`'s rule.
#    The GUARD at entry uses the live figures; the DOCUMENT uses the frozen ones.
# 2. **`rate` is stored as entered and may disagree with `approved_rate`.** It
#    does on 10 cells of the client's own annexure. Rates legitimately move on
#    approved variations, so this warns and never blocks — but a rate silently
#    disagreeing with the approved BOQ is one of the two failure modes this
#    system was sold to catch, so `rate_varies` is a stored fact about the bill.
# 3. **`deductions` is bill-level and exists from day one, empty.** Retention,
#    mobilisation-advance recovery and cess all fit one shape. `amount` is
#    always stored — computed from `pct` when the basis is a percentage — so an
#    issued bill cannot change its own figures later.
# 4. **`net_payable == claim_subtotal - deduction_total`, always**, including on
#    every bill with an empty deductions list.
# 5. **`ra_no` is unique across the whole REVISION CHAIN**, not per record, and
#    is never reused — a cancelled RA3 keeps the number and RA4 is next. A
#    revision must not restart the client's sequence at RA1 either.
# 6. **`line_id` is what a claim is matched on, and `item_no` never is.** Item
#    numbers restart per section and the client's own schedule repeats one
#    inside a section, so matching on them collapsed ten lines together and
#    broke the guard in both directions at once. The id is opaque, minted by
#    `boq._new_line_id()`, and carried forward unchanged across revisions —
#    which is what lets a revision renumber freely without detaching history.


# =============================================================================
# LIFECYCLE PREDICATES — the one place a bill's state is read
# =============================================================================

def status_of(bill) -> str:
    """
    This bill's lifecycle state, normalised to one of `STATUSES`.

    **Anything unrecognised reads as `issued`, and that default is the safe
    one.** A record written before the field existed has no `status` key at all,
    and the two states this app used to write in its place — `submitted` and
    `certified` — both mean *it has gone to the main contractor*. Defaulting
    those to `draft` would silently reopen every historical bill to editing and
    deletion, which is the exact failure the lock exists to prevent; defaulting
    them to `issued` locks them, which is what they always were.

    `draft` survives the normalisation because it means the same thing it always
    did. `tools/strip_certification.py` is what rewrites the stored rows, so no
    bill relies on this default for long — but the default has to be right on
    its own, because a fixture or a hand-edited record never runs the migration.
    """
    s = str((bill or {}).get("status") or "").strip().lower()
    return s if s in STATUSES else "issued"


def is_draft(bill) -> bool:
    return status_of(bill) == "draft"


def is_issued(bill) -> bool:
    return status_of(bill) == "issued"


def is_cancelled(bill) -> bool:
    """
    Has this bill been withdrawn?

    The single predicate every total, every balance and the over-claim guard
    consult. A cancelled bill is not a bill that claims less — it is a bill that
    claims nothing, so it is excluded rather than zeroed.
    """
    return status_of(bill) == "cancelled"


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

    **DRAFT AND ISSUED BILLS BOTH COUNT; CANCELLED ONES DO NOT.** Both halves of
    that are load-bearing and neither is obvious:

    - **A draft counts.** It is not yet a document, but its quantity is
      committed the moment it is saved, and two drafts each claiming the whole
      remaining balance of a line would otherwise both pass — the guard would
      see nothing until the second was issued, by which point the first has
      already been sent. Counting drafts is what makes the second one refuse.
    - **A cancelled bill does not.** Cancelling releases its quantity back onto
      every line it claimed, which is the entire point of having a cancel: a
      claim that has been withdrawn is not competing for the approved quantity,
      and leaving it in the sum would permanently sterilise the quantity of
      every mistake anybody ever withdrew.

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
        if is_cancelled(bill):
            continue                  # withdrawn — its quantity is released
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

    ⚠ **A CANCELLED bill still counts here, unlike in `claimed_by_line()`**, and
      the difference is deliberate. That function answers *how much quantity is
      committed*, so a withdrawn claim must release it. This one answers *has
      this line ever appeared on a bill*, and a cancelled bill is still a
      document that went out naming the line — deleting the line out of the
      schedule would leave it describing something the BOQ no longer contains.
      Releasing a quantity and erasing a history are different acts.
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


# =============================================================================
# THE PARTY LOCK — which bills freeze a BOQ's customer fields
# =============================================================================
#
# ⚠ **This NARROWS a rule set on 10 August 2026, and the narrowing is the
#   point.** The lock originally counted bills of **any** status, cancelled
#   included. Because a cancelled bill can never be deleted and can never be
#   un-cancelled (ABOUT.md §3, "The lifecycle"), one of them froze that BOQ's
#   customer name **permanently, with no escape** — and a party name that
#   cannot be corrected keeps that client split across two rows of `/client/`
#   forever.
#
# A cancelled bill is excluded from every total, from `claimed_by_line()`, from
# outstanding and from the receipts guard *by design*. It should not be the one
# thing freezing master data.
#
# **What does not change:** every bill still carries its own frozen party
# snapshot, taken at save, and no printed document moves when a BOQ's live
# fields are edited. The cancelled bill goes on printing the name it was issued
# with, which is what a withdrawn document is *for*. `party_drift()` below is
# what surfaces the disagreement afterwards rather than hiding it.

def party_lock_bills(boq_id: str) -> list:
    """
    The bills that freeze a BOQ's party fields — **draft and issued only**.

    Same shape as `bills_of()`. A cancelled bill is not here, and one on its own
    therefore leaves the fields editable. Read by `client.edit_party()` on both
    the GET and the POST, so the page and the guard cannot say different things
    — `can_receipt()`'s arrangement, one rule stated once.
    """
    return [(rid, b) for rid, b in bills_of(boq_id) if not is_cancelled(b)]


# The six fields `create_ra()` copies off the BOQ at save. Named once here so
# the drift check and the snapshot cannot fall out of step.
PARTY_FIELDS = (("account_name",  "Customer"),
                ("contact_person", "Contact person"),
                ("to",             "Billing address"),
                ("bill_gstin",     "Customer GSTIN"),
                ("project_name",   "Project"),
                ("site_location",  "Site"))


def party_drift(bill: dict) -> list:
    """
    Where this bill's frozen party snapshot disagrees with the live BOQ.

    Returns `[(label, on_the_bill, on_the_boq), …]`, empty when they agree or
    when the schedule is gone.

    **Exactly `prev_balance_drift()`'s shape and exactly its reason.** A bill
    that has gone out states what it stated; editing the BOQ afterwards must
    never restate it. But a disagreement nobody can see is worse than one
    everybody can, so `/ra/view` shows both figures and says plainly that the
    document is deliberately not restated. DOMAIN.md §6: surface it, name it,
    never silently correct it.

    A field blank on the bill and blank on the BOQ is not drift. A field blank
    on **one** of them is: that is the case where somebody filled in a GSTIN
    the issued document went out without.
    """
    boq = (STORE.get("boqs") or {}).get(str(bill.get("boq_id") or ""))
    if not boq:
        return []
    out = []
    for key, label in PARTY_FIELDS:
        was = str(bill.get(key) or "").strip()
        now = str(boq.get(key) or "").strip()
        if was != now:
            out.append((label, was, now))
    return out


# =============================================================================
# RECEIPTS — money actually RECEIVED, and the balance that carries forward
# =============================================================================
#
# A receipt lives in `STORE["receipts"]`, its OWN collection, keyed to the bill
# it pays. It is never a list on the RA bill and never a list on the BOQ —
# CLIENT_CHANGES.md §1.3. The BOQ record is the one that binds against
# `boq.MAX_JSON_BYTES` at ~428 lines, and anything appended to it eats that
# headroom and pushes the failure into the schedule editor, where the operator
# loses work that has nothing to do with the thing that grew. `ra_bills` is its
# own collection for the same reason; this is that rule applied once more.
#
# The arithmetic lives HERE, in ra.py, rather than in receipt.py, for an
# import-direction reason: `create_ra()` has to snapshot the carried balance at
# the moment a bill is saved, so ra.py needs the figure. If the figure lived in
# receipt.py, ra.py would have to import it — and receipt.py already imports
# ra.py for the bill and the chain. `receipt.py ──► ra.py` and never the
# reverse; that is the same one-way arrangement `boq.py`/`ra.py` already run.

def receipts_for(ra_id: str) -> list:
    """Every receipt against one bill, oldest first. (id, receipt) pairs."""
    ra_id = str(ra_id or "")
    if not ra_id:
        return []
    rows = [(rid, r) for rid, r in (STORE.get("receipts") or {}).items()
            if str(r.get("ra_id") or "") == ra_id]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""), kv[0]))
    return rows


def received_against(ra_id: str) -> float:
    """Total received against one bill. 0.0 when nothing has been."""
    return round(sum(float(r.get("amount") or 0.0)
                     for _rid, r in receipts_for(ra_id)), 2)


def written_off_against(ra_id: str) -> float:
    """
    Total **written off** against one bill — CLIENT_CHANGES-2.md A5.

    Deliberately a second function beside `received_against()` rather than a
    figure folded into it. Money that arrived and money the contractor allowed
    short are two different facts: the first is a bank movement and belongs in
    the client register's **Received** column, the second is a reduction in what
    is owed and does not. Summing them together is precisely the defect the A5
    field exists to stop being necessary (PROGRESS.md §6-D).

    A receipt written before 27 August 2026 has no `write_off` key at all, and
    reads as 0.0 — no backfill, the same contract `proforma.prior_invoiced` and
    `tax_slabs` hold to.
    """
    return round(sum(float(r.get("write_off") or 0.0)
                     for _rid, r in receipts_for(ra_id)), 2)


def outstanding_of(bill: dict) -> float:
    """
    What is still unpaid on one bill: its own `grand_total` minus what has
    been received against it.

    **Signed, and deliberately not clamped at zero.** An overpayment produces a
    negative outstanding and carries forward as a credit. Clamping it would
    state that money we are holding is not money we are holding — the same
    class of silent correction DOMAIN.md §6 forbids everywhere else in this
    module.

    **A CANCELLED bill is outstanding 0.00**, not its grand total. It was
    withdrawn, so nothing is owed on it — carrying its value forward would state
    a debt on a document we have said is void.

    `grand_total` is read off the bill, never recomputed: it is the figure the
    bill was issued for.
    """
    if not bill:
        return 0.0
    if is_cancelled(bill):
        return 0.0
    rid = str(bill.get("id") or "")
    # **Less what was received AND less what was written off** (A5). A short
    # allowance the contractor has agreed is not money we are still owed, and
    # leaving it here is what left 10,000 sitting in outstanding forever.
    gross = float(bill.get("grand_total") or 0.0)
    return round(gross - received_against(rid) - written_off_against(rid), 2)


def previous_balance(boq_id: str, before_ra_no: int,
                     exclude_ra_id: str = None) -> tuple:
    """
    (balance, refs) — what is still unpaid on every EARLIER bill of this
    project, and which bills it came from.

    **Summed across the whole REVISION CHAIN**, not against one BOQ record, and
    that is the same requirement `claimed_by_line()` carries and for the same
    reason: a revision is a new record, so a balance summed against the record
    alone would reset to zero the moment the schedule is revised, and the figure
    carried onto the next bill would silently understate what the client owes.
    A receipt against a bill raised on revision 0 still counts once revision 1
    is the live schedule, because the money was still received.

    "Earlier" is `ra_no <`, never a date and never insertion order. `ra_no` is
    server-assigned and unique across the chain, so it is the only ordering here
    that cannot be made ambiguous by two bills sharing a date.

    **Cancelled bills carry nothing forward**, and that falls out of
    `outstanding_of()` returning 0.00 for one rather than being a second check
    here: a nil outstanding is already skipped as settled. One rule, one place.

    Returns a **live** figure. The whole point of the caller is that it freezes
    the answer onto the bill it is creating — see `create_ra()`. Nothing that
    renders an issued document may call this.
    """
    total, refs = 0.0, []
    for rid, b in bills_of(boq_id):
        if exclude_ra_id and rid == exclude_ra_id:
            continue
        if int(b.get("ra_no") or 0) >= int(before_ra_no or 0):
            continue
        out = outstanding_of(b)
        if abs(out) < 0.005:          # settled in full — nothing to carry
            continue
        total += out
        refs.append(str(b.get("ref") or ""))
    return round(total, 2), refs


def prev_balance_drift(bill: dict) -> tuple:
    """
    (stored, live, differs) — has the carried balance moved since it was frozen?

    A receipt that is corrected or removed after a later bill has already
    snapshotted its effect **does not restate that bill** — the figure is stored
    on the bill and nothing here writes to it. This function exists so the
    divergence is *visible* rather than merely harmless: the screen says the
    document stated one figure and the ledger now computes another, and leaves
    both standing.

    That is the house stance, not a compromise. `rate_varies` does exactly this
    for a claim rate that disagrees with the approved BOQ rate, and DOMAIN.md §6
    is the general rule: surface it, name it, never silently correct it.

    A bill written before the field has no `prev_balance` key. It reports no
    drift rather than a drift from zero — it never made the statement, so there
    is nothing to have moved. Same contract as `tax_slabs`.
    """
    if not bill or "prev_balance" not in bill:
        return 0.0, 0.0, False
    stored = float(bill.get("prev_balance") or 0.0)
    live, _refs = previous_balance(str(bill.get("boq_id") or ""),
                                   int(bill.get("ra_no") or 0),
                                   exclude_ra_id=str(bill.get("id") or ""))
    return stored, live, abs(stored - live) >= 0.005


def bills_snapshotting_after(boq_id: str, ra_no: int) -> list:
    """
    Later bills in the chain that already froze a carried balance — the ones a
    change to this bill's receipts can no longer reach.

    Used to name them on the receipt delete confirmation, so the operator is
    told what the correction will *not* do before confirming it.
    """
    return [b for _rid, b in bills_of(boq_id)
            if int(b.get("ra_no") or 0) > int(ra_no or 0)
            and "prev_balance" in b]


def receipts_exist_for(ra_id: str) -> int:
    """How many receipts are filed against this bill."""
    return len(receipts_for(ra_id))


def next_ra_no(boq_id: str) -> int:
    """
    The next RA number for this project — max+1 across the whole chain.

    Chain-scoped, so a revision cannot restart the client's sequence at RA1.
    max+1 rather than len+1 is `proforma._next_ref()`'s rule: a gap must never
    re-issue a number that has already been on a claim the client holds.

    **Cancelled bills are counted here, on purpose.** They are the whole reason
    max+1 is stated rather than assumed: cancelling RA3 must leave RA3 spent, so
    the next bill is RA4. `bills_of()` returns every bill in the chain and this
    reads all of them, which is what makes the number un-reusable by
    construction rather than by a rule somebody has to remember.

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
    the printed document never recomputes it and an issued bill cannot change
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
# MUTABILITY — two independent gates on one record
# =============================================================================
#
# A bill's claim is closed to edits by EITHER of two unrelated facts, and it is
# worth keeping them apart in your head because they answer different questions
# and neither implies the other:
#
#   `claim_is_frozen()`  POSITION IN THE CHAIN. A mid-chain bill cannot be
#                        edited even as a draft, because `claimed_by_line()`
#                        sums the whole chain and moving a figure here silently
#                        restates every downstream balance.
#   `status_of()`        WHETHER IT HAS LEFT THE BUILDING. An issued bill cannot
#                        be edited even when it is the latest, because it is a
#                        document somebody else is holding.
#
# The status gate is reported FIRST wherever both apply, because "you already
# sent this" is the fact the operator can act on and "a later bill exists" is
# not the reason they are being stopped.

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

    **This is only half the question.** It says nothing about whether the bill
    has been issued — `can_edit()` is what asks both.
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
            f"changing it now would rewrite figures already sent out.")


def _receipts_refusal(bill: dict, done: str, doing: str) -> str:
    """
    The one sentence that refuses an action because money is filed against the
    bill. Shared by `can_delete()` and `can_cancel()` so the two cannot drift
    into describing the same fact two different ways.

    `done` / `doing` are the past participle and the gerund — "deleted" /
    "deleting it" — passed in rather than derived, because a sentence built by
    string-surgery on a verb is a sentence nobody can read in the source.
    """
    n = receipts_exist_for(str(bill.get("id") or ""))
    return (
        f"RA{bill.get('ra_no')} has {n} receipt{'' if n == 1 else 's'} recorded "
        f"against it totalling {_inr(received_against(str(bill.get('id') or '')))}, "
        f"so it cannot be {done}. Money has been received against this claim, and "
        f"{doing} would leave that payment filed against a document that no "
        f"longer stands. Remove the receipts first if they were entered in error.")


def can_edit(bill: dict) -> tuple:
    """
    (allowed, reason) — may this bill's CLAIM be edited?

    Both gates, in the order a person can act on:

    1. **Cancelled is final.** A withdrawn bill is locked, and there is no
       un-cancel anywhere in this module.
    2. **Issued is closed.** The main contractor is holding it. This is the lock
       certification used to provide as a side effect of being a status; it is
       now the status's actual job.
    3. **Mid-chain is closed** — `claim_is_frozen()`, for the separate reason
       that editing here restates every later bill's balance.
    """
    if not bill:
        return False, "That RA bill no longer exists."
    if is_cancelled(bill):
        return False, cancelled_reason(bill)
    if is_issued(bill):
        return False, (
            f"RA{bill.get('ra_no')} has been issued, so its claim can no longer "
            f"be edited. The main contractor is holding this document and its "
            f"figures must go on saying what they said when it was sent. "
            f"Correct the position in the next claim, or cancel this bill and "
            f"raise a fresh one.")
    if claim_is_frozen(bill):
        return False, frozen_reason(bill)
    return True, ""


def cancelled_reason(bill: dict) -> str:
    """Why a cancelled bill is locked, naming when and why it was withdrawn."""
    when = str(bill.get("cancelled_on") or "").strip()
    why = str(bill.get("cancel_reason") or "").strip()
    return (f"RA{bill.get('ra_no')} was cancelled"
            f"{' on ' + when if when else ''}"
            f"{' — ' + why if why else ''}. A cancelled bill is locked and "
            f"cannot be un-cancelled: the withdrawal is a fact somebody else "
            f"has been told about. Raise a new bill instead; it will take the "
            f"next number, not this one.")


def can_delete(bill: dict) -> tuple:
    """
    (allowed, reason) — may this bill be deleted?

    Four conditions, each refusing with a sentence rather than hiding a button:

    - **Never one with money receipted against it.** A receipt is keyed to the
      bill it pays, so deleting the bill orphans the payment: the money stays
      in the ledger pointing at a document that no longer exists, and it
      silently stops being counted in the balance carried onto the next bill.
      Checked first because it is the most specific fact and the one with an
      obvious remedy. It is *mostly* unreachable now that a receipt can only be
      recorded against an issued bill and an issued bill refuses deletion
      anyway — kept because a guard that depends on another guard for its
      correctness is one refactor away from being wrong.
    - **Never a cancelled one.** Cancelling is how a bill is withdrawn without
      destroying it; deleting it afterwards would throw away the record of the
      withdrawal and free the number.
    - **Never an issued one.** It has left the building. Cancel it instead —
      that is what cancel is for, and it keeps `ra_no` spent.
    - **Only the highest-numbered bill**, so removing one cannot leave a gap in
      the sequence or restate a later bill's balance.
    """
    if not bill:
        return False, "That RA bill no longer exists."
    if receipts_exist_for(str(bill.get("id") or "")):
        return False, _receipts_refusal(bill, "deleted", "deleting it")
    if is_cancelled(bill):
        return False, (
            f"RA{bill.get('ra_no')} was cancelled, so it cannot be deleted. The "
            f"cancellation is the record of what was withdrawn and why, and "
            f"RA{bill.get('ra_no')} stays spent either way — deleting it would "
            f"destroy the first and free the second.")
    if is_issued(bill):
        return False, (
            f"RA{bill.get('ra_no')} has been issued, so it cannot be deleted. "
            f"The main contractor is holding it, and a document that has gone "
            f"out is withdrawn by cancelling it — which keeps the number spent "
            f"and records why — not by removing it from our own books.")
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


def can_issue(bill: dict) -> tuple:
    """(allowed, reason) — may this draft be issued to the main contractor?"""
    if not bill:
        return False, "That RA bill no longer exists."
    if is_cancelled(bill):
        return False, cancelled_reason(bill)
    if is_issued(bill):
        return False, (
            f"RA{bill.get('ra_no')} has already been issued"
            f"{' on ' + str(bill.get('issued_on')) if bill.get('issued_on') else ''}"
            f". Issuing it a second time would restate its date without changing "
            f"anything the main contractor holds.")
    return True, ""


def can_cancel(bill: dict) -> tuple:
    """
    (allowed, reason) — may this bill be cancelled?

    A draft or an issued bill may both be cancelled. A **cancelled** one may
    not: there is no un-cancel and no re-cancel, because either would make the
    withdrawal something that could be quietly taken back.

    **A bill with receipts against it is refused**, in the same shape and for
    the same reason `can_delete()` refuses one: cancelling it would state that
    nothing is owed on a document money has already been paid against, and
    `outstanding_of()` would drop that payment's bill out of the ledger's
    arithmetic. Reverse the receipts first, deliberately.
    """
    if not bill:
        return False, "That RA bill no longer exists."
    if is_cancelled(bill):
        return False, cancelled_reason(bill)
    if receipts_exist_for(str(bill.get("id") or "")):
        return False, _receipts_refusal(bill, "cancelled", "cancelling it")
    return True, ""


def can_receipt(bill: dict) -> tuple:
    """
    (allowed, reason) — may money be recorded against this bill?

    **Only against an ISSUED one.** A draft has not been sent to anybody, so
    there is nothing it could have been paid against; recording money against
    one would be filing a real payment under a document that does not yet
    exist, and the payment would then block the draft's own deletion. A
    cancelled bill has been withdrawn and owes nothing.

    It lives HERE rather than in `receipt.py` for the same import-direction
    reason `RECEIPT_MODES` does: `receipt.py ──► ra.py` and never the reverse,
    and `/ra/view` renders the control that states this rule beside the button
    it disables. One rule, one place, both sides of the arrow.
    """
    if not bill:
        return False, "That RA bill no longer exists."
    if is_cancelled(bill):
        return False, (
            f"RA{bill.get('ra_no')} was cancelled, so no payment can be "
            f"recorded against it. A withdrawn claim is owed nothing. If money "
            f"did arrive, it belongs against whichever bill replaced this one.")
    if not is_issued(bill):
        return False, (
            f"RA{bill.get('ra_no')} is still a draft, so no payment can be "
            f"recorded against it — it has not been sent to the main "
            f"contractor, so there is nothing for him to have paid. Issue it "
            f"first, then record the receipt.")
    return True, ""


def apply_issue(bill: dict, on: str = "") -> dict:
    """
    Mark a bill issued. Writes `status` and `issued_on` and **nothing else** —
    no figure on the bill moves, which is what makes "issuing does not restate a
    claim" true by construction rather than by a check.
    """
    bill["status"] = "issued"
    bill["issued_on"] = str(on or "").strip() or _date.today().isoformat()
    return bill


def apply_cancel(bill: dict, reason: str, on: str = "") -> dict:
    """
    Withdraw a bill. Writes `status`, `cancelled_on` and `cancel_reason`, and
    **nothing else** — every claimed figure stays exactly as issued.

    The bill is not emptied and its quantities are not zeroed. A cancelled bill
    still prints, carrying its CANCELLED overprint, because it is the record of
    what was withdrawn; what changes is that `claimed_by_line()` stops counting
    it and `outstanding_of()` reports nil against it.
    """
    bill["status"] = "cancelled"
    bill["cancelled_on"] = str(on or "").strip() or _date.today().isoformat()
    bill["cancel_reason"] = str(reason or "").strip()
    return bill


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
# THE PRINTED BILL — the sheet's own layer
# =============================================================================
#
# `/ra/print` renders on the shared A4 sheet (`docsheet.py`), so this stylesheet
# layers *after* it and introduces **no new font, no new type size and no new
# border weight** — it uses only the `--fs-*` and `--rule-*` `VIEW_DOC_STYLES`
# already defines. That is the same restraint `PROFORMA_STYLES`,
# `INVOICE_STYLES` and `PURCHASE_STYLES` hold to, and it is the reason the four
# documents read as one office's paperwork.
#
# It replaced a page that broke every one of those rules: a `.doc-paper` card in
# Inter over a slate palette, its own border weights, its own table, and a
# `.doc-header` rule that silently overrode `VIEW_DOC_STYLES`' class of the same
# name.

# The columns. Deliberately the SAME EIGHT-COLUMN GEOMETRY as the tax invoice
# and the purchase order, so `docsheet.sum_row()` and `total_row()` line up
# against it and the three sheets have the same rhythm. Only two labels differ,
# and both differ because this document says something the others do not:
# "Item No" is the BOQ's display label (never a key — DOMAIN.md §2.2), and the
# quantity is *this bill's* claim rather than a quantity supplied.
RA_COLUMNS = (("c-sno", "S.No"), ("c-partno", "Item No"),
              ("c-desc", "Description of Work Executed"), ("c-hsn", "HSN/SAC"),
              ("c-qty", "Claim Qty"), ("c-unit", "Unit"),
              ("c-price", "Rate"), ("c-total", "Amount"))

RA_DOC_STYLES = """
<style>
  .quotation-doc.ra-doc { position:relative; }
  .quotation-doc .doc-sub-ra {
    text-align:center; font-size:var(--fs-sm); color:var(--doc-soft);
    padding-bottom:2mm;
  }

  /* The lifecycle overprint. A draft or a cancelled bill must never be
     mistakable for a live tax invoice, on screen OR on paper, so neither rule
     sits behind a `@media screen`, and the band forces its background through
     with print-color-adjust. The watermark is a bordered, coloured word rather
     than a filled block, so it still reads when a browser is printing with
     backgrounds off. */
  .quotation-doc .lc-mark {
    position:absolute; top:45%; left:50%;
    transform:translate(-50%,-50%) rotate(-24deg);
    font-size:5.5rem; font-weight:800; letter-spacing:.35rem;
    border:6px solid currentColor; border-radius:12px;
    padding:.35rem 2rem; opacity:.18; pointer-events:none;
    white-space:nowrap; z-index:2;
  }
  .quotation-doc .lc-band {
    margin:0 0 3mm; padding:2mm 3mm;
    font-size:var(--fs-sm); font-weight:700; text-align:center;
    border:1px solid currentColor;
    print-color-adjust:exact; -webkit-print-color-adjust:exact;
  }
  .quotation-doc .lc-draft { color:#b45309; }
  .quotation-doc .lc-band.lc-draft { background:#fffbeb; }
  .quotation-doc .lc-cancelled { color:#b91c1c; }
  .quotation-doc .lc-band.lc-cancelled { background:#fef2f2; }

  /* The carried-balance memo. Framed OUTSIDE `.doc-box`, deliberately: it is a
     statement about earlier bills, not a charge on this one, and it must not
     read as part of the tax computation it sits under. */
  .quotation-doc .memo-box {
    border:var(--rule-box); margin-top:5mm;
    print-color-adjust:exact; -webkit-print-color-adjust:exact;
  }
  .quotation-doc .memo-row {
    display:flex; justify-content:space-between; gap:6mm;
    padding:2px 6px; border-bottom:var(--rule-hair);
  }
  .quotation-doc .memo-row.memo-due { font-weight:700; border-bottom:none; }
  .quotation-doc .memo-amt { font-variant-numeric:tabular-nums; font-weight:700; }
  .quotation-doc .memo-note {
    padding:2px 6px; border-top:var(--rule); color:var(--doc-soft);
    font-size:var(--fs-xs);
  }
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
    return f'<div class="alert {_esc(kind)}">{_esc(msg)}</div>' if msg else ""


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
    rows = bills_of(str(boq.get("id") or ""))
    live = sum(1 for _rid, b in rows if not is_cancelled(b))
    void = len(rows) - live
    run = (f"{live} raised" + (f", {void} cancelled" if void else "")) if rows \
        else "none yet"
    label = f"RA{int(ra_no or 0)}"       # int() by intent: a pre-formatted
                                         # string is now a loud TypeError here
                                         # rather than a quiet "RARA3" on screen
    return f"""
    <div class="ra-meta">
      <div class="ra-fact"><b>Project</b><span>{_esc(boq.get("project_name"))}</span></div>
      <div class="ra-fact"><b>BOQ</b><span>{_esc(boq.get("ref"))} &middot; rev {_esc(boq.get("rev_no") or 0)}</span></div>
      <div class="ra-fact"><b>Customer</b><span>{_esc(boq.get("account_name"))}</span></div>
      <div class="ra-fact"><b>This bill</b><span>{_esc(label)} &middot; {_esc(leg)}</span></div>
      <div class="ra-fact"><b>Bills on this project</b><span>{_esc(run)}</span></div>
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


_STATUS_BADGE_STYLE = ("padding:2px 8px;border-radius:12px;font-size:0.75rem;"
                       "font-weight:600;")

# Amber for draft, green for issued, red for cancelled — the house severity
# scale (ABOUT.md §5): amber means *incomplete but working*, red means *this is
# not a live document*. A draft is amber rather than grey because it is a state
# somebody has to act on, not a neutral one.
_STATUS_BADGES = {
    "draft":     ("Draft",     "#fffbeb", "#b45309", "#fde68a"),
    "issued":    ("Issued",    "#ecfdf5", "#047857", "#a7f3d0"),
    "cancelled": ("Cancelled", "#fef2f2", "#b91c1c", "#fecaca"),
}


def status_badge(bill: dict) -> str:
    """The bill's lifecycle state as a chip. One renderer, used everywhere."""
    label, bg, fg, border = _STATUS_BADGES[status_of(bill)]
    return (f'<span class="status-badge st-{status_of(bill)}" '
            f'style="background:{bg};color:{fg};border:1px solid {border};'
            f'{_STATUS_BADGE_STYLE}">{label}</span>')


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

    # **Cancelled bills are excluded from both tiles.** A withdrawn claim is not
    # a smaller claim, so it contributes nothing rather than contributing its
    # figures — the same rule `claimed_by_line()` and `outstanding_of()` follow.
    # The count of them is still shown, because a total that silently drops
    # records is a total nobody can reconcile against the table beneath it.
    live = [b for _rid, b in bills.items() if not is_cancelled(b)]
    n_void = len(bills) - len(live)
    total_claimed = sum(float(b.get("net_payable") or 0.0) for b in live)
    total_outstanding = sum(outstanding_of(b) for b in live)

    tiles_html = f"""
    <div class="pipe-tiles">
      <div class="pipe-tile t-open">
        <div class="pt-lbl">Total Claimed Net Payable</div>
        <div class="pt-val">&#8377;&nbsp;{total_claimed:,.0f}</div>
        <div class="pt-sub">{len(live)} live running account bill{"s" if len(live) != 1 else ""}{f" &middot; {n_void} cancelled, excluded" if n_void else ""}</div>
      </div>
      <div class="pipe-tile">
        <div class="pt-lbl">Total Outstanding</div>
        <div class="pt-val">&#8377;&nbsp;{total_outstanding:,.0f}</div>
        <div class="pt-sub">still unpaid across the live bills</div>
      </div>
    </div>"""

    if rows:
        table_rows_html = ""
        for rid, b in rows:
            boq_id = str(b.get("boq_id") or "")
            is_latest = is_latest_bill(boq_id, rid)
            latest_badge = '<span style="background:#e0e7ff;color:#3730a3;border:1px solid #c7d2fe;padding:2px 6px;border-radius:10px;font-size:0.7rem;font-weight:600;">Latest</span>' if is_latest else ""
            view_url = url_for("ra.view_ra", id=rid)
            print_url = url_for("ra.print_ra", id=rid)
            boq_link = url_for("boq.view_boq", id=boq_id) if boq_id in STORE.get("boqs", {}) else "#"

            # A cancelled bill's money reads as a dash, not as a figure. Printing
            # its net payable in the same column as the live ones invites the
            # reader to add the column up and get a number the tile above does
            # not agree with.
            void = is_cancelled(b)
            net_cell = "&mdash;" if void else \
                f"&#8377;&nbsp;{float(b.get('net_payable') or 0.0):,.2f}"
            out_cell = "&mdash;" if void else f"&#8377;&nbsp;{outstanding_of(b):,.2f}"

            table_rows_html += f"""
            <tr{' style="opacity:.6;"' if void else ''}>
              <td class="td-ref"><a href="{view_url}">RA{_esc(b.get('ra_no'))}</a> <span style="font-size:0.75rem;color:var(--muted);">({_esc(b.get('ref'))})</span></td>
              <td><span class="fh-sec">{_esc(b.get('leg'))}</span></td>
              <td class="td-muted">{_esc(b.get('date'))}</td>
              <td><a href="{boq_link}">{_esc(b.get('boq_ref'))}</a></td>
              <td class="td-num" style="font-weight:600;">{net_cell}</td>
              <td class="td-num">{out_cell}</td>
              <td>{status_badge(b)}</td>
              <td>{latest_badge}</td>
              <td>
                <a href="{view_url}" class="btn-view">&#128269; View</a>
                <a href="{print_url}" class="btn-view" style="margin-left:0.3rem;">&#128438; Print</a>
              </td>
            </tr>"""

        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>RA Bill</th><th>Leg</th><th>Date</th><th>BOQ Ref</th>
            <th style="text-align:right;">Claimed Net</th><th style="text-align:right;">Outstanding</th>
            <th>Status</th><th>Latest?</th><th></th>
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


# =============================================================================
# THE LIFECYCLE ROUTES
# =============================================================================
#
# Both follow `delete_ra()`'s shape exactly, which is the shape `9d060ee` set
# for every state-changing route in this app: **the GET renders a confirmation
# page and mutates nothing; the change happens only inside the POST branch.**
#
# ⚠ There is deliberately **no `onclick="return confirm(...)"` anywhere here.**
#   A browser confirm() is not a guard — it never runs for a link-prefetching
#   browser, a crawler, a chat client unfurling a pasted URL, or the back
#   button, and each of those issues a plain GET. That is exactly what
#   `9d060ee` removed from three delete routes, and re-introducing it on a
#   route that issues or voids a tax invoice would be worse than where it was.
#
# ABOUT.md §7.9f's standing rule is written for delete routes and the `url_map`
# sweep only walks rules whose path contains "delete", so **neither of these is
# covered by it**. Each therefore ships its own hand-written test asserting a
# GET leaves the bill's status unchanged — `test_a_get_on_issue_changes_nothing`
# and `test_a_get_on_cancel_changes_nothing`.

def _confirm_page(title: str, heading: str, body: str, action: str,
                  submit_label: str, back_url: str, extra: str = "") -> str:
    """The confirmation page both lifecycle routes render on a GET."""
    return _shell(title, f"""
  <div class="page-top"><h1>{heading}</h1></div>
  <div class="del-box">
    <div class="del-line">{body}</div>
  </div>
  <form method="POST" action="{action}" style="display:flex;gap:.7rem;align-items:flex-end;flex-wrap:wrap;">
    {extra}
    <button type="submit" class="btn">{submit_label}</button>
    <a href="{back_url}" class="btn btn-ghost">Go back</a>
  </form>""")


@ra_bp.route("/issue/<id>", methods=["GET", "POST"])
def issue_ra(id: str):
    """
    Issue a draft bill to the main contractor — the point the lock comes down.

    After this the claim cannot be edited and the bill cannot be deleted; the
    only way back is a cancellation, which keeps `ra_no` spent. That is the
    whole reason this is a deliberate act with its own confirmation rather than
    a status dropdown: it is the moment the document stops being ours.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.list_ras",
                                msg="That RA bill no longer exists.", type="error"))

    allowed, why = can_issue(bill)
    if not allowed:
        return redirect(url_for("ra.view_ra", id=id, msg=why, type="error"))

    if request.method == "POST":
        apply_issue(bill, on=(request.form.get("issued_on") or "").strip())
        return redirect(url_for("ra.view_ra", id=id,
                                msg=f"RA{bill.get('ra_no')} issued.",
                                type="success"))

    n_lines = len(bill.get("claims") or [])
    today = _date.today().isoformat()
    return _confirm_page(
        title=f"Issue RA{bill.get('ra_no')}",
        heading=f"Issue <span>RA{_esc(bill.get('ra_no'))}</span>",
        body=f"""
      You are about to issue <b>RA{_esc(bill.get('ra_no'))}</b>
      ({_esc(bill.get('ref'))}, {_esc(bill.get('leg'))}) against
      {_esc(bill.get('boq_ref'))}. It claims
      <b>{n_lines} line{"" if n_lines == 1 else "s"}</b> totalling
      <b>{_inr(bill.get('grand_total') or 0.0)}</b>.<br/><br/>
      Once issued, <b>its claim can no longer be edited and it cannot be
      deleted</b>. Its printed document drops the DRAFT marker, and money may be
      recorded against it. To withdraw it afterwards you cancel it, which keeps
      the number <b>RA{_esc(bill.get('ra_no'))}</b> spent &mdash; the next bill
      will be RA{int(bill.get('ra_no') or 0) + 1} either way.""",
        action=url_for("ra.issue_ra", id=id),
        submit_label=f"Issue RA{_esc(bill.get('ra_no'))}",
        back_url=url_for("ra.view_ra", id=id),
        extra=f"""
    <div class="form-group" style="margin:0;"><label for="issued_on">Issued on</label>
      <input type="date" id="issued_on" name="issued_on" value="{_esc(today)}"/></div>""")


@ra_bp.route("/cancel/<id>", methods=["GET", "POST"])
def cancel_ra(id: str):
    """
    Withdraw a bill. **There is no route back**, and that is the point.

    Cancelling is not deleting. The record stays, its figures stay exactly as
    issued, the document still prints (over a CANCELLED overprint), and
    `ra_no` stays spent — cancelled RA3 is still RA3 and the next bill is RA4,
    the same reasoning that stops a GST serial being reissued.

    What changes is arithmetic: `claimed_by_line()` stops counting it, so the
    quantity it claimed goes back onto every line's balance, and
    `outstanding_of()` reports nil against it so it leaves the ledger's totals.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.list_ras",
                                msg="That RA bill no longer exists.", type="error"))

    allowed, why = can_cancel(bill)
    if not allowed:
        return redirect(url_for("ra.view_ra", id=id, msg=why, type="error"))

    error = ""
    if request.method == "POST":
        reason = (request.form.get("cancel_reason") or "").strip()
        if not reason:
            # A cancellation with no reason is a hole in the record six months
            # later, when the only remaining question is why the number is
            # missing from the run. Required, and refused in words.
            error = ("Say why this bill is being cancelled. A cancelled RA "
                     "number stays spent forever, so the reason is the only "
                     "thing that will explain the gap later.")
        else:
            apply_cancel(bill, reason,
                         on=(request.form.get("cancelled_on") or "").strip())
            return redirect(url_for("ra.view_ra", id=id,
                                    msg=f"RA{bill.get('ra_no')} cancelled.",
                                    type="success"))

    n_lines = len(bill.get("claims") or [])
    today = _date.today().isoformat()
    state = "issued" if is_issued(bill) else "a draft"
    return _shell(f"Cancel RA{bill.get('ra_no')}", f"""
  <div class="page-top"><h1>Cancel <span>RA{_esc(bill.get('ra_no'))}</span></h1></div>
  {_alert(error)}
  <div class="del-box">
    <h2>&#9888; This cannot be undone</h2>
    <div class="del-line">
      You are about to cancel <b>RA{_esc(bill.get('ra_no'))}</b>
      ({_esc(bill.get('ref'))}, {_esc(bill.get('leg'))}), currently {state},
      raised on {_esc(bill.get('date'))} against {_esc(bill.get('boq_ref'))}.
      It claims <b>{n_lines} line{"" if n_lines == 1 else "s"}</b> totalling
      <b>{_inr(bill.get('grand_total') or 0.0)}</b>.<br/><br/>
      The bill is <b>not deleted</b>. It keeps its figures, still prints as a
      record with a CANCELLED overprint, and <b>keeps the number
      RA{_esc(bill.get('ra_no'))}</b> &mdash; the next bill will be
      RA{int(bill.get('ra_no') or 0) + 1}, exactly as if this one still stood.
      <br/><br/>
      What changes: the quantities it claimed go <b>back onto the balance</b> of
      every line, and it drops out of every total and out of outstanding.
      <b>There is no un-cancel.</b>
    </div>
  </div>
  <form method="POST" action="{url_for('ra.cancel_ra', id=id)}">
    <div class="form-section">
      <div class="fg2">
        <div class="form-group"><label for="cancel_reason">Why is it being cancelled?</label>
          <input type="text" id="cancel_reason" name="cancel_reason"
                 value="{_esc(request.form.get('cancel_reason') or '')}"
                 placeholder="e.g. quantities remeasured, superseded by RA4"/></div>
        <div class="form-group"><label for="cancelled_on">Cancelled on</label>
          <input type="date" id="cancelled_on" name="cancelled_on" value="{_esc(today)}"/></div>
      </div>
    </div>
    <div style="display:flex;gap:.7rem;">
      <button type="submit" class="btn">Cancel RA{_esc(bill.get('ra_no'))}</button>
      <a href="{url_for('ra.view_ra', id=id)}" class="btn btn-ghost">Keep it</a>
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
    if boq_id in boqs and boq_id in BQ.superseded_ids():
        msg = f"BOQ {boqs[boq_id].get('ref')} is superseded. Claims must be raised against the latest revision."
        return redirect(url_for("ra.create_ra", msg=msg, type="error"))

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

            # THE SNAPSHOT. What earlier bills of this project still owe is
            # frozen onto this bill HERE, at the moment it is created, and is
            # never recomputed afterwards — not on edit, and above all not at
            # print time.
            #
            # This is the exact defect class that already shipped once in this
            # module: `print_ra()` was a loop over the live `boq["line_items"]`,
            # so revising the schedule silently rewrote a document the client
            # had already been sent. A previous-balance recomputed from live
            # receipts is the same bug with a different source — entering a
            # receipt against RA1 in October would rewrite the balance printed
            # on RA2 in August. A printed document is driven by its own stored
            # rows, full stop (CLIENT_CHANGES.md §1.2).
            this_ra_no = next_ra_no(boq_id)
            prev_balance, prev_balance_refs = previous_balance(boq_id, this_ra_no)

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
                "ra_no": this_ra_no,
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
                # The carried balance, frozen above. It is a MEMO on this
                # document and nothing more: it is deliberately absent from
                # `claim_subtotal`, from every tax figure, from `net_payable`
                # and from `grand_total`, and it is invisible to the over-claim
                # guard because it is not a quantity on a line.
                #
                # ⚠ ASSUMPTION, NOT CONFIRMED BY THE CLIENT: an unpaid amount is
                #   NOT re-billed as a claim row on the next RA bill. It is
                #   stated on the face of the bill and left there. If they come
                #   back and say the arrears should be re-claimed, this is the
                #   field that changes and the change is not cosmetic — a
                #   re-billed arrear would enter `claim_subtotal`, be taxed a
                #   second time on a value already taxed once, and inflate the
                #   cumulative claim against the approved schedule until the
                #   over-claim block refused a bill for the wrong reason.
                #   CLIENT_CHANGES.md item 8 and §3 carry the open question.
                "prev_balance": prev_balance,
                "prev_balance_refs": prev_balance_refs,
                # A new bill is a DRAFT. It is editable, deletable and prints
                # with a DRAFT marker until somebody deliberately issues it at
                # `/ra/issue/<id>` — the lock comes down there, not here.
                "status": "draft",
                "issued_on": "", "cancelled_on": "", "cancel_reason": "",
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
    Edit a bill's CLAIM — allowed only while it is a DRAFT and the latest bill
    for its BOQ.

    Two independent gates, both in `can_edit()`:

    - **Status.** An issued bill is a document the main contractor is holding
      and a cancelled one is withdrawn; neither may have its figures moved.
      This is the lock that used to fall out of certification being a status,
      rebuilt as its own thing.
    - **Position.** `claimed_by_line()` sums the whole chain, so editing a
      mid-chain bill silently changes every downstream balance, including ones
      already printed and handed over. Latest-only bounds the recompute to one
      bill and keeps printed history true.
    """
    bill = STORE["ra_bills"].get(id)
    if not bill:
        return redirect(url_for("ra.create_ra",
                                msg="That RA bill no longer exists.", type="error"))

    allowed, why = can_edit(bill)
    if not allowed:
        return redirect(url_for("ra.view_ra", id=id, msg=why, type="error"))

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
            # `prev_balance` / `prev_balance_refs` are deliberately NOT in this
            # list and must not be added to it. They were frozen by
            # `create_ra()` and they are a statement about OTHER bills, so
            # editing this bill's own claim has no business moving them — and
            # this bill may already have been printed and sent. Recomputing
            # here would make "the snapshot never moves" true only until
            # somebody opened the edit form. `prev_balance_drift()` is how a
            # stale figure is surfaced instead.
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
        rows.append(
            f'<tr><td class="cl-no">{_esc(snap)}{moved}</td>'
            f'<td class="cl-desc">{_esc(c.get("description"))[:160]}</td>'
            f'<td class="cl-unit">{_esc(c.get("unit"))}</td>'
            f'<td class="cl-num">{_qty(c.get("approved_qty"))}</td>'
            f'<td class="cl-num">{_qty(c.get("prev_qty"))}</td>'
            f'<td class="cl-num">{_qty(c.get("qty"))}</td>'
            f'<td class="cl-num">{_inr(c.get("rate") or 0.0)}{warn}</td>'
            f'<td class="cl-num">{_qty(c.get("balance_qty"))}</td>'
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

    # The lock notice. Whichever gate is shut, the reason is stated in words at
    # the top of the page rather than being left to a greyed-out button — a
    # control that vanishes teaches nothing about why.
    can_ed, edit_why = can_edit(bill)
    lock_html = (f'<div class="frozen-note"><span>&#128274;</span>'
                 f'<span>{_esc(edit_why)}</span></div>') if not can_ed else ""

    def _gated(label: str, endpoint: str, allowed: bool, why: str) -> str:
        """
        A control that is **always present**, and carries its refusal when it is
        not available. The house rule: refuse with the reason on the control
        rather than hiding it, because a button that vanishes teaches nothing
        about why it went.
        """
        if allowed:
            return f'<a class="btn btn-ghost" href="{url_for(endpoint, id=id)}">{label}</a>'
        return (f'<span class="btn btn-ghost" style="opacity:.55;cursor:not-allowed;" '
                f'title="{_esc(why)}">{label}</span>')

    del_allowed, del_why = can_delete(bill)
    iss_allowed, iss_why = can_issue(bill)
    can_allowed, can_why = can_cancel(bill)

    del_btn = _gated("Delete", "ra.delete_ra", del_allowed, del_why)
    edit_btn = _gated("Edit claim", "ra.edit_ra", can_ed, edit_why)
    issue_btn = _gated("&#10003; Issue", "ra.issue_ra", iss_allowed, iss_why)
    cancel_btn = _gated("&#10007; Cancel", "ra.cancel_ra", can_allowed, can_why)
    print_btn = f'<a class="btn" href="{url_for("ra.print_ra", id=id)}" style="background:#0284c7;color:#fff;border:none;">&#128438; Print / Tax Invoice</a>'

    # The cancellation band. Loud, at the top, and it names the reason — a
    # cancelled bill that looks like a live one on screen is how somebody sends
    # a withdrawn claim a second time.
    cancelled_html = ""
    if is_cancelled(bill):
        cancelled_html = (
            f'<div class="alert error"><b>RA{_esc(bill.get("ra_no"))} is '
            f'cancelled.</b> Withdrawn on '
            f'{_esc(bill.get("cancelled_on") or "an unrecorded date")}'
            f'{" &mdash; " + _esc(bill.get("cancel_reason")) if bill.get("cancel_reason") else ""}. '
            f'Its quantities have been released back onto the BOQ balances and '
            f'it is excluded from every total. The number RA{_esc(bill.get("ra_no"))} '
            f'stays spent and is never reissued.</div>')

    # ── Receipts against this bill ──────────────────────────────────────────
    #
    # A CURRENT-STATE screen, so unlike the printed document it is computed
    # live. That split is the whole design: `/ra/print` prints what the bill
    # said, this page shows where the money actually stands today, and
    # `prev_balance_drift()` below is what makes it visible when the two have
    # come apart. `url_for("receipt.…")` and a direct read of the receipts
    # collection keep the arrow one-way — ra.py does not import receipt.py.
    rc_rows = receipts_for(id)
    rc_received = received_against(id)
    rc_outstanding = outstanding_of(bill)
    rc_body = "".join(
        f'<tr><td class="cl-no">{_esc(r.get("ref"))}</td>'
        f'<td class="cl-desc">{_esc(r.get("date"))}</td>'
        f'<td class="cl-unit">{_esc(RECEIPT_MODE_LABELS.get(str(r.get("mode") or ""), r.get("mode") or ""))}</td>'
        f'<td class="cl-desc">{_esc(r.get("instrument_ref")) or "&mdash;"}</td>'
        f'<td class="cl-amt">{_inr(r.get("amount") or 0.0)}</td>'
        # A5. An em dash where there is none, so an ordinary ledger looks
        # exactly as it did and a write-off cannot hide inside one.
        f'<td class="cl-amt">{_inr(r.get("write_off")) if r.get("write_off") else "&mdash;"}</td>'
        f'<td><a class="btn btn-ghost" href="{url_for("receipt.edit_receipt", id=rid)}">Edit</a> '
        f'<a class="btn btn-ghost" href="{url_for("receipt.delete_receipt", id=rid)}">Delete</a></td></tr>'
        for rid, r in rc_rows)
    rc_empty = ('<tr><td colspan="7" style="color:var(--muted);">'
                'Nothing received against this bill yet.</td></tr>')

    # **Money is only ever received against an ISSUED bill.** A draft has not
    # been sent, so nothing can have been paid against it; a cancelled one has
    # been withdrawn. `receipt.new_receipt()` refuses both at the route — this
    # is the same rule stated on the control, so the operator is told before
    # clicking rather than after. The button is disabled, never hidden.
    if is_issued(bill):
        rc_add_btn = (f'<a class="btn" href="{url_for("receipt.new_receipt", ra=id)}">'
                      f'&#43; Record a payment</a>')
    else:
        rc_add_btn = (
            f'<span class="btn" style="opacity:.55;cursor:not-allowed;" '
            f'title="{_esc(can_receipt(bill)[1])}">&#43; Record a payment</span>')

    # The drift notice. A receipt corrected after a later bill froze its effect
    # does not restate that bill — this says so rather than letting the two
    # figures disagree in silence. DOMAIN.md §6: surface it, never correct it.
    stored_pb, live_pb, pb_drifted = prev_balance_drift(bill)
    drift_note = ""
    if pb_drifted:
        drift_note = (
            f'<div class="form-hint"><span class="fh-icon">&#9888;</span>'
            f'<span><b>This bill was issued stating a previous balance of '
            f'{_esc(_inr(stored_pb))}; the ledger now computes '
            f'{_esc(_inr(live_pb))}.</b> A receipt has been corrected or removed '
            f'since. The figure printed on the bill is deliberately left as '
            f'issued &mdash; a document already sent is not restated. Correct '
            f'the position on the next bill.</span></div>')

    # The SAME band, one field over. A BOQ's party fields can now be corrected
    # while a cancelled bill stands against it (`party_lock_bills()`), so this
    # is the surface that stops the correction being silent. Deliberately the
    # receipts band's shape and wording rather than a second design: an
    # operator who has met one has met both.
    party_rows = party_drift(bill)
    if party_rows:
        pairs = "; ".join(
            f'{_esc(label)} &mdash; on this bill '
            f'<b>{_esc(was) or "(blank)"}</b>, on the schedule now '
            f'<b>{_esc(now) or "(blank)"}</b>'
            for label, was, now in party_rows)
        drift_note += (
            f'<div class="form-hint"><span class="fh-icon">&#9888;</span>'
            f'<span><b>The schedule\'s customer details have been edited since '
            f'this bill was issued.</b> {pairs}. The bill carries its own copy, '
            f'frozen at save, and is deliberately <b>not</b> restated &mdash; a '
            f'document already sent says what it said. The current details are '
            f'what a new bill would carry.</span></div>')

    pb_html = ""
    if "prev_balance" in bill:
        refs = [str(r) for r in (bill.get("prev_balance_refs") or []) if str(r or "").strip()]
        pb_html = (
            f'<span><b>Previous balance carried onto this bill</b> '
            f'<span class="ra-tot">{_inr(stored_pb)}</span></span>'
            f'<span style="color:var(--muted);font-size:.72rem;">'
            f'{_esc(", ".join(refs)) if refs else "nothing outstanding when this bill was raised"}'
            f'</span>')

    return _shell(f"RA{bill.get('ra_no')}", f"""
  <div class="page-top">
    <h1>RA{_esc(bill.get('ra_no'))} <span>&middot; {_esc(bill.get('leg'))}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.view_boq', id=boq_id)}" class="btn btn-ghost">&#8592; BOQ</a>
      {edit_btn}{issue_btn}{cancel_btn}{print_btn}{del_btn}
    </div>
  </div>
  {_flash()}
  {cancelled_html}
  {lock_html}
  {rate_note}
  {drift_note}
  <div class="ra-meta">
    <div class="ra-fact"><b>Our reference</b><span>{_esc(bill.get('ref'))}</span></div>
    <div class="ra-fact"><b>Date</b><span>{_esc(bill.get('date'))}</span></div>
    <div class="ra-fact"><b>Against</b><span>{_esc(bill.get('boq_ref'))} &middot; rev {_esc(bill.get('boq_rev_no'))}</span></div>
    <div class="ra-fact"><b>Project</b><span>{_esc(bill.get('project_name'))}</span></div>
    <div class="ra-fact"><b>Status</b><span>{status_badge(bill)}</span></div>
    <div class="ra-fact"><b>{"Cancelled on" if is_cancelled(bill) else "Issued on"}</b><span>{_esc((bill.get('cancelled_on') if is_cancelled(bill) else bill.get('issued_on')) or '') or "&mdash;"}</span></div>
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
  <div class="form-section">
    <div class="section-title">&#128176; Receipts against this bill</div>
    <div class="cl-wrap"><table class="claims">
      <thead><tr>
        <th>Receipt</th><th>Received on</th><th>Mode</th><th>Instrument</th>
        <th style="text-align:right;">Amount</th>
        <th style="text-align:right;">Written off</th><th></th>
      </tr></thead>
      <tbody>{rc_body or rc_empty}</tbody>
    </table></div>
    <div class="ra-foot">
      <span><b>Bill grand total</b> <span class="ra-tot">{_inr(bill.get('grand_total') or 0.0)}</span></span>
      <span><b>Received</b> <span class="ra-tot">{_inr(rc_received)}</span></span>
      <span><b>Outstanding on this bill</b> <span class="ra-tot">{_inr(rc_outstanding)}</span></span>
      {pb_html}
    </div>
    <div style="margin-top:.8rem;">
      {rc_add_btn}
      <a class="btn btn-ghost" href="{url_for('receipt.list_receipts', boq=boq_id)}">Project ledger</a>
    </div>
    <p style="font-size:.75rem;color:var(--muted);margin-top:.6rem;">
      Outstanding is computed live from the receipts ledger. The
      <b>previous balance printed on a bill</b> is not &mdash; that is frozen on
      the bill when it is raised, and a receipt entered afterwards never
      rewrites a document already sent.
    </p>
  </div>
  <p style="font-size:.75rem;color:var(--muted);">
    This is a working view. <a href="{url_for('ra.print_ra', id=id)}">Click here to view/print the Tax Invoice</a>.
  </p>""")


@ra_bp.route("/print/<id>")
def print_ra(id: str):
    """
    The printed RA bill tax invoice document.

    Modeled on the client's as-submitted RA2.pdf (DOMAIN.md §4), and rendered
    **on the same A4 sheet as every other document this office issues** —
    `docsheet.py` supplies the letterhead, the party block, the items-table
    shell, the totals rows, the amount in words, the bank block and the
    signature panel. It used to carry a layout entirely of its own (a
    `.doc-paper` card in Inter over a slate palette) which matched nothing else
    the client receives; the sheet is the fix, and the change is measured by
    `tests/test_print_golden.py`.

    What is **not** shared, and stays here because it is this chain's:

    - the two independent series — a Tax Invoice No. and an RA Bill No. on one
      page, counting separately (DOMAIN.md §4.2);
    - **per-line HSN/SAC**, snapshotted onto each claim row, and the per-slab
      CGST/SGST/IGST block computed off the rate each row stores. That is the
      difference the `invoice.py` prohibition rests on, and folding it into the
      shared layer would have smuggled the coupling back in (ABOUT.md §2d);
    - the sparse table — **only claimed lines**, with a parent specification
      line printed above its sub-items carrying no quantity and no rate
      (DOMAIN.md §4.6);
    - the previous-balance memo, below the Grand Total and outside the tax
      computation;
    - the DRAFT / CANCELLED overprint.

    **Every value on this page comes from the bill's own record.** That is the
    whole point of the snapshot: an issued tax invoice must render identically
    after the BOQ it was measured against is revised. The only thing read from
    the live BOQ is the specification-header *relation* — see the line table
    below — and `test_ra_print_immutability.py` asserts the property end to end.

    ⚠ **Place of supply is still absent and is not to be added here.** It is a
    Rule 46 field and its absence is real, but it decides CGST+SGST against
    IGST and that determination is pending the client's CA — ABOUT.md §7 gap
    15, CLIENT_CHANGES.md §3.1. Rendering this document on the statutory sheet
    does not make the question answered.
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

    # The carried balance — read off THIS BILL'S OWN RECORD, never recomputed
    # from `STORE["receipts"]`. That is the whole contract: entering, editing or
    # deleting a receipt after this bill was issued must leave the printed page
    # byte-identical, and `tests/test_receipts.py` asserts exactly that against
    # the rendered document.
    #
    # A bill written before the field has no key and prints no memo block at
    # all — not a zero. It never made the statement, and printing "Previous
    # Balance: 0.00" on it would be this document asserting a position it was
    # never issued with. Same contract as `tax_slabs` above.
    has_prev_balance = "prev_balance" in bill
    prev_balance = float(bill.get("prev_balance") or 0.0)
    total_with_prev = round(grand_total + prev_balance, 2)

    # `quotation._amount_in_words()` already returns its own "INR " prefix —
    # the document printed "INR INR Nine Lakh …" until this stopped adding one.
    words = _amount_in_words(grand_total)

    # ── The lifecycle overprint ────────────────────────────────────────────
    #
    # **Only an ISSUED bill prints clean.** The other two states each get a
    # diagonal watermark and a band under the title, and both are `@media print`
    # -visible on purpose: the entire risk here is a working copy or a withdrawn
    # claim reaching the main contractor's desk looking like a live tax invoice.
    #
    # `print-color-adjust:exact` on the band, because a browser with backgrounds
    # switched off would otherwise print the paper's most important sentence as
    # black text on white — indistinguishable from the document body. The
    # watermark is drawn with a border and a colour rather than a fill so it
    # survives that setting regardless.
    status = status_of(bill)
    overprint_html = ""
    if status != "issued":
        if status == "cancelled":
            mark = "CANCELLED"
            band = (f"This bill was cancelled"
                    f"{' on ' + _esc(bill.get('cancelled_on')) if bill.get('cancelled_on') else ''}"
                    f"{' &mdash; ' + _esc(bill.get('cancel_reason')) if bill.get('cancel_reason') else ''}. "
                    f"It is not a demand for payment. The number "
                    f"RA{_esc(bill.get('ra_no'))} is not reissued.")
        else:
            mark = "DRAFT"
            band = ("This is a DRAFT and has not been issued. Its figures may "
                    "still change and it is not a demand for payment.")
        overprint_html = f"""
        <div class="lc-mark lc-{status}">{mark}</div>
        <div class="lc-band lc-{status}">{band}</div>"""

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
            #
            # `.row-assembly` is the sheet's own class for a row that heads a
            # group, so a specification clause looks here exactly like an
            # assembly does on a tax invoice. It carries **no quantity and no
            # rate** (DOMAIN.md §2.2): it is a heading with legal weight, not a
            # billable line, and the six numeric columns are spanned rather
            # than left as a row of blanks that reads as missing data.
            table_rows_html += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td class="c-partno">{_esc(BQ._item_no(hdr.get("item_no")))}</td>
          <td colspan="6" class="c-desc">{_esc((hdr.get("description") or "").strip())}</td>
        </tr>"""
        last_header_key = header_key

        hsn_sac = (c.get("hsn_sac") or "").strip()
        # A blank code prints as the house amber chip, exactly as it does on the
        # tax invoice and in the catalogue — never as an empty cell. Rule 46(g):
        # a line without one costs the customer the input tax credit on it.
        hsn_display = _esc(hsn_sac) if hsn_sac else B.field("", "HSN/SAC code")
        qty = float(c.get("qty") or 0.0)
        rate = float(c.get("rate") or 0.0)
        amt = float(c.get("amount") or (qty * rate))

        table_rows_html += f"""
        <tr class="row-item">
          <td class="c-sno">{idx}</td>
          <td class="c-partno">{_esc(BQ._item_no(c.get('item_no')))}</td>
          <td class="c-desc">{_esc(c.get('description'))}</td>
          <td class="c-hsn">{hsn_display}</td>
          <td class="c-qty">{BQ._fmt_qty(qty)}</td>
          <td class="c-unit">{_esc(c.get('unit'))}</td>
          <td class="c-price">{_inr(rate)}</td>
          <td class="c-total">{_inr(amt)}</td>
        </tr>"""

    # Deductions block rows
    deductions_rows_html = ""
    for d in deductions:
        lbl = d.get("label") or d.get("code") or "Deduction"
        damt = float(d.get("amount") or 0.0)
        deductions_rows_html += DS.sum_row(f"Less: {_esc(lbl)}", f"&#8722;&nbsp;{_inr(damt)}")

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
        tax_rows_html = DS.sum_row(igst_label, _inr(igst_amount))
    else:
        tax_rows_html = (DS.sum_row(cgst_label, _inr(cgst_amount)) +
                         DS.sum_row(sgst_label, _inr(sgst_amount)))

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
            # The slab's taxable value and its tax, on one row. GSTR-1 is filed
            # rate-wise off exactly these figures, so each is the *stored* one
            # and the column adds to the total beneath it.
            slab_rows_html += DS.sum_row(
                f"Taxable @ {rate_pct:g}% ({heads}){hsn_note} &mdash; "
                f"{_inr(float(s.get('taxable_value') or 0.0))}",
                _inr(head_amt))
        tax_rows_html = slab_rows_html + tax_rows_html

    # The previous-balance memo. Rendered BELOW the Grand Total and visually
    # outside the tax computation, because that is what it is: a statement of
    # what is still outstanding on earlier bills, not a charge on this one.
    #
    # It is not added into any taxable figure, and the "Total Due" beneath it is
    # arithmetic over two figures both stored on this record — it is not a new
    # taxable value and carries no tax of its own. The arrears were taxed on the
    # bill that first claimed them; taxing them again here would charge GST
    # twice on one supply.
    #
    # Nothing prints when the stored balance is nil, and nothing prints at all
    # on a bill written before the field: silence is the correct rendering of
    # "this document made no such statement".
    prev_balance_html = ""
    if has_prev_balance and abs(prev_balance) >= 0.005:
        refs = [str(r) for r in (bill.get("prev_balance_refs") or []) if str(r or "").strip()]
        refs_note = (" &middot; " + _esc(", ".join(refs))) if refs else ""
        prev_balance_html = f"""
  <div class="memo-box">
    <div class="memo-row">
      <span><b>Previous Balance Outstanding</b>{refs_note}</span>
      <span class="memo-amt">{_inr(prev_balance)}</span>
    </div>
    <div class="memo-row memo-due">
      <span><b>Total Due (this bill + previous balance)</b></span>
      <span class="memo-amt">{_inr(total_with_prev)}</span>
    </div>
    <div class="memo-note">Memorandum only. The previous balance is carried forward for information and is <b>not</b> re-claimed as a line item on this bill. It was claimed and taxed on the bill that raised it, so no GST is charged on it here.</div>
  </div>"""

    rounding_html = ""
    if abs(rounding_off) > 1e-4:
        rounding_html = DS.sum_row("Rounding Off", f"{rounding_off:+,.2f}")

    # ── The header meta ────────────────────────────────────────────────────
    #
    # **The two series sit side by side and count independently** (DOMAIN.md
    # §4.2). The Tax Invoice No. is the seller's statutory serial across all
    # work; `ra_no` is this claim's position in this project's run. One is not
    # derived from the other and they must not be printed as if they were.
    meta_col_1 = (
        _meta("Tax Invoice No.",     _esc(tax_inv_ref)) +
        _meta("RA Bill No.",         f"RA{_esc(bill.get('ra_no'))} "
                                     f"({_esc(bill.get('leg'))})") +
        _meta("Against BOQ",         f"{_esc(bill.get('boq_ref'))} "
                                     f"(Rev {_esc(bill.get('boq_rev_no'))})") +
        _meta("Buyer's PO / WO No.", po_ref_disp) +
        _meta("Buyer's GSTIN",       buyer_gstin_disp)
    )
    meta_col_2 = (
        _meta("Date",                 _esc(tax_inv_date)) +
        _meta("Contact Person",       contact_person_disp) +
        _meta("Buyer's PO / WO Date", po_date_disp) +
        _meta("Our GSTIN",            seller_gstin_disp) +
        _meta("Our State",            seller_state_disp)
    )

    # The project and the site, under the buyer. A site is a first-class field
    # in this business, not a label — they run several concurrently (DOMAIN.md
    # §1) — and the client's own bill names it on the face.
    site_html = DS.secondary_block(
        "Project / Site",
        "\n".join(x for x in [bill.get("project_name") or "",
                              bill.get("site_location") or ""] if x.strip()))

    # ── Totals ─────────────────────────────────────────────────────────────
    totals_html = (
        DS.sum_row("Claim Subtotal", _inr(claim_subtotal)) +
        deductions_rows_html +
        DS.sum_row("Taxable Value (net payable)", _inr(net_payable)) +
        tax_rows_html +
        rounding_html +
        DS.total_row("Grand Total (inclusive of taxes)",
                     BQ._fmt_qty(sum(float(c.get("qty") or 0.0) for c in claims)),
                     _inr(grand_total))
    )

    html = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(f"TAX INVOICE — RA{bill.get('ra_no')}")}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{DS.DOCSHEET_STYLES}{RA_DOC_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Tax Invoice <span style="color:var(--brand);">{_esc(tax_inv_ref)}</span>
    {status_badge(bill)}
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('ra.view_ra', id=id)}" class="btn btn-ghost">&#8592;&nbsp;Back to RA{_esc(bill.get('ra_no'))}</a>
    <a href="{url_for('ra.list_ras')}" class="btn btn-ghost">RA Register</a>
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>

<div class="doc-outer">
<div class="quotation-doc ra-doc">

{DS.sheet_open()}

  <div class="doc-box">
    {overprint_html}
    <div class="doc-title">TAX INVOICE</div>
    <div class="doc-sub-ra">Running Account bill &middot; claim for work executed</div>

{DS.party_block("To", DS.name_block(bill.get("to")) or buyer_name_disp,
                site_html, meta_col_1, meta_col_2)}

{DS.items_table(RA_COLUMNS, table_rows_html + totals_html)}

{DS.amount_words("Grand Total (in words)", grand_total)}
  </div>
{prev_balance_html}
{DS.bank_block(f"Please quote tax invoice no. <b>{_esc(tax_inv_ref)}</b> "
               f"and RA{_esc(bill.get('ra_no'))} on the remittance advice.")}

{DS.sig_block(_esc(bill.get("company_branch")), _esc(bill.get("auth_signatory")))}

{DS.sheet_close()}

</div>
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · RA bill tax invoice</p>
</footer>
</main>
</body></html>"""
    return _page(html)


@ra_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_ra(id: str):
    """
    Delete an RA bill — a DRAFT, the highest-numbered one only.

    `can_delete()` holds the four refusals: receipts against it, cancelled,
    issued, or not the latest. An issued bill is withdrawn by **cancelling**
    it — which keeps `ra_no` spent and records why — never by deleting it.

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
