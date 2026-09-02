"""
merged_ra.py — the merged RA bill  (CC-2 **C3**)
================================================

Built 2 September 2026 under the **first override block of that date** in
`CLIENT_CHANGES.md` §0 — the block that unblocked C3 by answering **BQ2** and
then **BQ1**, in that order, ahead of any code. C3 had been **BLOCKED** since
30 August 2026 on exactly those two answers.

What it is
----------

RA-Supply and RA-Installation are raised **separately** and go on being raised
separately, each keeping its own `ra_no`, its own `ref` and its own status.
The merge produces **one further document** carrying both legs' line rows
**stacked**, with one combined total, raising **one tax invoice number**. CC-2's
own example:

    RA-Supply       : Item 1 (qty 1)  ₹500
    RA-Installation : Item 1 (qty 1)  ₹700
    Merged          : Item 1 (qty 1) + Item 1 (qty 1) = ₹1,200

⚠ **Plain concatenation, NOT a line-by-line merge.** The two rows above stay two
rows. Adding them into one would need the two legs to agree on a unit, a rate
and an HSN/SAC, and they agree on none of the three — supply is goods at one
rate, installation is a service at another.

CC-2's six invariants, and where each one lives
-----------------------------------------------

| invariant | enforced by |
|---|---|
| the merged record holds **no claims of its own** | there is no `claims` key; `stacked_rows()` reads the two sources at render |
| totals are the **sum of the two stored totals**, never recomputed from the live BOQ | `_sum_totals()`, and `test_the_total_is_the_sum_of_the_stored_totals` |
| a bill appears in **at most one live** merged document | `live_merge_of()`, checked in `create()` |
| a source bill in a live merged document **cannot be cancelled** | `ra.can_cancel()` — in `ra.py`, reading `STORE` directly |
| **receipts stay on the source bills** | nothing here writes a receipt, and `balance()` sums the legs |
| the merge action is **on the RA register from day one** | `ra.list_ras()` renders the button |

⚠ **The totals rule is the same defect class as the `print_ra` bug already fixed
once.** A merged sheet that recomputed from the live BOQ would restate a
document the client already holds the moment a schedule was revised. The figures
are summed **at creation** from what the two bills stored, and frozen here.

BQ1 and BQ2, as the override block answers them
------------------------------------------------

**BQ2 first**, because BQ1 is not stable without it. The repo said both things:
`PHASE4_RA_DESIGN.md` §2 said `ref` inherits Rule 46(b)'s 16-character cap,
§5 of the same file said it does not. **The ruling splits the question rather
than picking a side:**

- an RA bill's **`ref` is our document number** and keeps `ra._REF_CAP = 64`.
  Not touched by this module. §5 was right about `ref`.
- the **statutory serial is `tax_invoice_ref`**, a different field, and it **is**
  subject to Rule 46(b)'s 16 characters. §2 was right about the tax invoice
  number. The two documents were never arguing about the same field.

**BQ1 then dissolves.** It asked which of *three* serials is the statutory one
when a merged document mints one over two bills that "each already carry one".
The answer is that the two legs **never spent a statutory serial** — their
`ref`s are document numbers — so there is no third. This document mints **its
own**, from **its own counter**, derived from **neither** leg.

⚠ **Derivation was refused for a measured reason, not a stylistic one.**
`SF/RA/26-27/0004` is **exactly 16 characters**. There is no room inside Rule
46(b)'s budget to decorate a leg's number into a unique merged variant, and a
scheme that must truncate to fit is a scheme that will collide.

⚠ **THE SERIES MUST NOT COLLIDE WITH `invoice.py`'s.** That module already mints
`SF/TI/26-27/0001` at `cap=16` for the sell-side tax invoice. A second counter
emitting a `TI` number would put **one statutory serial on two different
documents**, which is precisely what Rule 46(b) exists to prevent and would be
strictly worse than the ambiguity being resolved. So this series is `MI`, and
`ra.py`'s standing prohibition on importing `invoice.py` is **not** relaxed to
share a counter. Multiple invoice series are permitted provided each is
consecutive and unique within the financial year, which a separate counter under
a distinct series gives by construction.

⚠ **WHAT THIS DOES NOT DO.** It mints a series for the **merged** document only.
A single-leg RA bill's `tax_invoice_ref` stays what DOMAIN.md §4.2 records — a
typed field with no counter behind it, falling back to `ref` when left blank.
**That gap is not closed here**, it is not in C3's scope, and §4.2's STATUS
paragraph stands unchanged.

Import direction
----------------

`merged_ra.py ──► ra.py`, and **never the reverse.** `ra.py` renders the merge
button with `url_for` and reads `STORE["merged_ras"]` directly to answer "is
this bill inside a live merge?" — the same one-way trick `ra.py`/`receipt.py`
and `boq.py`/`ra.py` already run, and `tests/test_import_directions.py` holds it.
"""

import datetime
import uuid

from flask import Blueprint, redirect, request, url_for

import approval
import boq as BQ
import branding as B
import docsheet as DS
import pipeline as P
import ra as RA
from dashboard import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES, _inr, _meta
from store import STORE

merged_bp = Blueprint("merged_ra", __name__, url_prefix="/merged")


# =============================================================================
# THE SERIES — BQ1's answer, in code
# =============================================================================

# ⚠ **`MI`, and NOT `TI`.** See the module docstring: `invoice.py` owns `TI` and
#   a second counter under the same series would put one statutory serial on two
#   documents. `test_the_merged_series_does_not_collide_with_the_tax_invoice_series`
#   is what stops a later pass "tidying" the two together.
_REF_SERIES = "MI"

# ⚠ **16, and this is BQ2's answer.** Rule 46(b) caps a TAX INVOICE number at 16
#   characters, and `tax_invoice_ref` is a tax invoice number — unlike
#   `ra._REF_CAP = 64`, which governs the RA bill's own document number and is
#   deliberately NOT changed by this module.
#
#   `SF/MI/26-27/0001` is exactly 16 and stays exactly 16 through `9999`. If a
#   company short name ever pushes it over, `P.fy_ref()` drops the prefix rather
#   than issuing an over-length number — a number the GST portal will reject is
#   worse than an unbranded one.
_REF_CAP = 16

STATUSES = ("live", "cancelled")


def next_tax_invoice_ref(datestr: str) -> str:
    """
    The next merged tax invoice number — `SF/MI/26-27/0001`.

    FY-scoped and **max+1 within the year, not len+1**: a gap left by a
    cancelled document must never re-issue a number that has already been quoted
    in somebody else's ledger. Every series in this application follows that
    rule and this one is a **statutory** serial, where it is not a preference.

    ⚠ **A cancelled merged document keeps its number**, exactly as a cancelled
    RA bill keeps its `ra_no`. The count therefore includes cancelled rows.
    """
    fy = P.fy_of(datestr)
    highest = 0
    for m in (STORE.get("merged_ras") or {}).values():
        if m.get("fy") != fy:
            continue
        tail = str(m.get("tax_invoice_ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=_REF_CAP)


# =============================================================================
# THE RECORD
# =============================================================================
#
# STORE["merged_ras"][uuid] = {
#   "id": uuid,
#   "tax_invoice_ref": "SF/MI/26-27/0001",  # THE statutory serial. Minted here.
#   "fy": "26-27",
#   "date": "2026-09-02",
#
#   # The two legs. These ids are the ONLY thing that makes this document mean
#   # anything, and everything beside them is a snapshot for the historical
#   # record — the same contract every back-reference in this app keeps.
#   "supply_ra_id": uuid,        "installation_ra_id": uuid,
#   "supply_ref": str,           "installation_ref": str,
#   "supply_ra_no": int,         "installation_ra_no": int,
#
#   "boq_id": uuid, "boq_ref": str,
#   "project_name": str, "site_location": str, "account_name": str,
#   "contact_person": str, "to": str, "bill_gstin": str,
#
#   # SUMMED AT CREATION from what the two bills STORED. Never recomputed.
#   "claim_subtotal": float, "deduction_total": float, "net_payable": float,
#   "tax_amount": float, "rounding_off": float, "grand_total": float,
#
#   "status": "live" | "cancelled",
#   "cancelled_on": "", "cancel_reason": "",
#   "notes": str,
# }
#
# ⚠ **THERE IS NO `claims` KEY AND THERE MUST NEVER BE ONE.** CC-2: *"The
#   merged record never holds claims of its own. It references the two source
#   bills. Copying claim rows into it would make the over-claim guard count the
#   same quantity twice."* `ra.claimed_by_line()` walks `STORE["ra_bills"]` and
#   sums `claims` — a merged record carrying copies would be counted as a third
#   claim against the same schedule, and every over-claim check downstream would
#   be wrong in the direction that lets money through.
#
#   `test_the_merged_record_holds_no_claims_of_its_own` fails if one appears,
#   and `test_merging_does_not_move_the_overclaim_guard` proves the consequence
#   rather than only the shape.


def _now_date() -> str:
    return datetime.date.today().isoformat()


def records() -> dict:
    return STORE.setdefault("merged_ras", {})


def status_of(doc) -> str:
    """
    Normalised lifecycle state.

    Anything unrecognised reads as `live`, which is the **safe** default here
    for the mirror image of `ra.status_of()`'s reason: a record whose status
    cannot be read must not silently release its two legs for a second merge.
    """
    s = str((doc or {}).get("status") or "").strip().lower()
    return s if s in STATUSES else "live"


def is_cancelled(doc) -> bool:
    return status_of(doc) == "cancelled"


def is_live(doc) -> bool:
    return status_of(doc) == "live"


# =============================================================================
# THE "AT MOST ONE LIVE MERGE" INVARIANT
# =============================================================================

def live_merge_of(ra_id: str):
    """
    The **live** merged document holding this bill, or `None`.

    ⚠ **Live only, and that is the whole of CC-2's rule.** *"A bill may appear
    in at most one LIVE merged document. Otherwise the same money is invoiced
    twice."* A cancelled merged document releases both its legs — that is what
    cancelling it is **for** — so a cancelled row must not go on blocking them.
    """
    ra_id = str(ra_id or "")
    if not ra_id:
        return None
    for m in records().values():
        if not is_live(m):
            continue
        if ra_id in (str(m.get("supply_ra_id") or ""),
                     str(m.get("installation_ra_id") or "")):
            return m
    return None


def merges_of(ra_id: str) -> list:
    """Every merged document this bill has been in, live or cancelled."""
    ra_id = str(ra_id or "")
    return [m for m in records().values()
            if ra_id in (str(m.get("supply_ra_id") or ""),
                         str(m.get("installation_ra_id") or ""))]


def legs_of(doc) -> tuple:
    """`(supply_bill, installation_bill)` — either may be None if deleted."""
    bills = STORE.get("ra_bills") or {}
    return (bills.get(str((doc or {}).get("supply_ra_id") or "")),
            bills.get(str((doc or {}).get("installation_ra_id") or "")))


# =============================================================================
# WHAT MAY BE MERGED
# =============================================================================

def candidates(boq_id: str) -> tuple:
    """
    `(supply_bills, installation_bills)` eligible for a new merge on one chain.

    ⚠ **`ra.py`'s existing status rules, not a looser set invented here.** A
    bill qualifies only when `ra.is_issued()` says so — which means a **draft**
    is refused (it is not a claim that has gone anywhere yet) and a **cancelled**
    one is refused (`ra.is_cancelled()`, the same predicate every total and the
    over-claim guard already consult). `ra.status_of()` is the one place a
    bill's state is read and this defers to it rather than testing the raw
    field.

    ⚠ **Chain-scoped, not record-scoped.** `ra.revision_chain()` is what "same
    project" means in this application — a BOQ revision does not start a new
    project, and `receipt.receipts_of_boq()` groups the same way for the same
    reason.
    """
    ids = set(RA.revision_chain(boq_id))
    supply, install = [], []
    for rid, b in (STORE.get("ra_bills") or {}).items():
        if str(b.get("boq_id") or "") not in ids:
            continue
        if not RA.is_issued(b):
            continue
        if live_merge_of(rid) is not None:
            continue
        (supply if str(b.get("leg") or "") == "supply" else install).append((rid, b))
    supply.sort(key=lambda kv: int(kv[1].get("ra_no") or 0))
    install.sort(key=lambda kv: int(kv[1].get("ra_no") or 0))
    return supply, install


def can_merge(supply_bill, install_bill) -> tuple:
    """
    `(allowed, reason)` for one proposed pair. The whole gate, in one place.

    Every refusal here names what is wrong with **this pair** rather than
    returning a generic no, because the operator is choosing from two lists and
    needs to know which half to change.
    """
    if not supply_bill or not install_bill:
        return False, "Choose one supply bill and one installation bill."

    s_id = str(supply_bill.get("id") or "")
    i_id = str(install_bill.get("id") or "")
    if s_id == i_id:
        return False, "A bill cannot be merged with itself."

    if str(supply_bill.get("leg") or "") != "supply":
        return False, "The first bill must be an RA-Supply bill."
    if str(install_bill.get("leg") or "") != "installation":
        return False, "The second bill must be an RA-Installation bill."

    # ⚠ ra.py's own rules, consulted rather than restated.
    for b, what in ((supply_bill, "supply"), (install_bill, "installation")):
        if RA.is_draft(b):
            return False, (f"RA{int(b.get('ra_no') or 0)} ({what}) is still a "
                           f"draft. Issue it before merging it — a merge raises "
                           f"a tax invoice, and a draft is not a claim that has "
                           f"gone anywhere.")
        if RA.is_cancelled(b):
            return False, (f"RA{int(b.get('ra_no') or 0)} ({what}) is cancelled "
                           f"and claims nothing, so there is nothing of it to "
                           f"invoice.")
        if not RA.is_issued(b):
            return False, f"RA{int(b.get('ra_no') or 0)} ({what}) is not issued."

    # ⚠ Same project, read as the revision CHAIN. A revision does not start a
    #   new project, so two bills raised against revisions 0 and 1 of one
    #   schedule are the same project and may be merged.
    s_chain = set(RA.revision_chain(str(supply_bill.get("boq_id") or "")))
    if str(install_bill.get("boq_id") or "") not in s_chain:
        return False, ("Those two bills are against different projects. A merged "
                       "document covers one project's supply and installation.")

    for b, what in ((supply_bill, "supply"), (install_bill, "installation")):
        held = live_merge_of(str(b.get("id") or ""))
        if held is not None:
            return False, (
                f"RA{int(b.get('ra_no') or 0)} ({what}) is already inside merged "
                f"document {held.get('tax_invoice_ref')}. A bill may be in at "
                f"most one live merged document, or the same money is invoiced "
                f"twice. Cancel that document first to release it.")

    return True, ""


# =============================================================================
# THE FIGURES — summed from what the legs STORED
# =============================================================================

_SUMMED = ("claim_subtotal", "deduction_total", "net_payable",
           "tax_amount", "rounding_off", "grand_total")


def _sum_totals(supply_bill, install_bill) -> dict:
    """
    Each money field, as the **sum of the two bills' own stored values**.

    ⚠ **Nothing here reads the BOQ.** CC-2: *"Totals are the sum of the two
    bills' own stored totals, never recomputed from the live BOQ. Same defect
    class as the `print_ra` bug already fixed once."* A schedule revised after
    these bills were issued must not move a document the client already holds.

    ⚠ **`grand_total` is summed, not re-derived** from the summed parts. The two
    bills each rounded once per tax slab, and re-deriving would round the sum a
    second time — the merged sheet would then disagree with its own two legs by
    a rupee, which is exactly the kind of difference that costs an afternoon.
    """
    out = {}
    for key in _SUMMED:
        out[key] = round(float(supply_bill.get(key) or 0.0)
                         + float(install_bill.get(key) or 0.0), 2)
    return out


def balance(doc) -> float:
    """
    What is still unpaid across both legs.

    ⚠ **Derived by summing the legs, never by repointing receipts.** CC-2:
    *"Receipts stay attached to the source bills. The merged document derives
    its balance by summing them. Do not repoint receipts — it would churn
    `previous_balance()` and the memo line for no gain."* `ra.outstanding_of()`
    is the one definition of that figure and this consumes it.
    """
    supply_bill, install_bill = legs_of(doc)
    total = 0.0
    for b in (supply_bill, install_bill):
        if b:
            total += RA.outstanding_of(b)
    return round(total, 2)


def stacked_rows(doc) -> list:
    """
    Both legs' claim rows, **stacked** — supply first, then installation.

    Read from the source bills at render time, because the merged record holds
    no claims of its own. Each row is tagged with the leg it came from so the
    sheet can band them, and **nothing is combined**: CC-2's own example keeps
    Item 1 (supply) and Item 1 (installation) as two rows.
    """
    supply_bill, install_bill = legs_of(doc)
    rows = []
    for bill, leg in ((supply_bill, "supply"), (install_bill, "installation")):
        if not bill:
            continue
        for c in bill.get("claims") or []:
            row = dict(c)
            row["_leg"] = leg
            row["_ra_no"] = int(bill.get("ra_no") or 0)
            row["_ref"] = str(bill.get("ref") or "")
            rows.append(row)
    return rows


def tax_slabs(doc) -> list:
    """
    The stacked tax block, per rate slab, across both legs.

    ⚠ **This is the one figure that is recomputed rather than summed, and the
    reason is that a slab is not a total.** Supply at 18% and installation at
    18% are **one** 18% slab on the merged sheet, not two rows saying 18%
    twice — and CC-2 notes the per-line HSN/SAC already carries the rates, so
    the block foots with no new arithmetic. It is computed from the **frozen**
    claim rows of the two bills, never from the live BOQ, so it is as frozen as
    the sums beside it.

    ⚠ **It is NOT what `grand_total` is built from.** That is summed from the
    two stored totals — see `_sum_totals()`. If the two ever disagree, the
    stored sum wins and the difference is a bug in this function, not a
    correction to the document.
    """
    supply_bill, _install = legs_of(doc)
    tax_type = str((supply_bill or {}).get("tax_type") or "cgst_sgst")
    return RA.tax_slabs(stacked_rows(doc), tax_type)


# =============================================================================
# CREATE / CANCEL
# =============================================================================

def create(supply_bill, install_bill, notes: str = "") -> tuple:
    """`(doc, error)` — mint the merged document, or refuse and say why."""
    allowed, why = can_merge(supply_bill, install_bill)
    if not allowed:
        return None, why

    mid = str(uuid.uuid4())
    date = _now_date()
    doc = {
        "id": mid,
        "tax_invoice_ref": next_tax_invoice_ref(date),
        "fy": P.fy_of(date),
        "date": date,

        "supply_ra_id": str(supply_bill.get("id") or ""),
        "installation_ra_id": str(install_bill.get("id") or ""),
        "supply_ref": str(supply_bill.get("ref") or ""),
        "installation_ref": str(install_bill.get("ref") or ""),
        "supply_ra_no": int(supply_bill.get("ra_no") or 0),
        "installation_ra_no": int(install_bill.get("ra_no") or 0),

        # Snapshotted at creation, for the reason every back-reference in this
        # application is: the document still reads correctly as a historical
        # record if a source bill is removed, and it names what it covered.
        "boq_id": str(supply_bill.get("boq_id") or ""),
        "boq_ref": str(supply_bill.get("boq_ref") or ""),
        "project_name": str(supply_bill.get("project_name") or ""),
        "site_location": str(supply_bill.get("site_location") or ""),
        "account_name": str(supply_bill.get("account_name") or ""),
        "contact_person": str(supply_bill.get("contact_person") or ""),
        "to": str(supply_bill.get("to") or ""),
        "bill_gstin": str(supply_bill.get("bill_gstin") or ""),

        "status": "live",
        "cancelled_on": "",
        "cancel_reason": "",
        "notes": str(notes or ""),
    }
    doc.update(_sum_totals(supply_bill, install_bill))
    records()[mid] = doc
    # B6 — the creator, captured at the write site, because the rule that a
    # person may not approve their own record needs it recorded at the one
    # moment there is one.
    approval.stamp_creator(doc)
    return doc, ""


def can_cancel(doc) -> tuple:
    """
    `(allowed, reason)` — may this merged document be withdrawn?

    ⚠ **A merged document with receipts against EITHER leg is still
    cancellable, and that is deliberate.** The receipts belong to the source
    bills and are untouched by this — cancelling the merge withdraws the
    *invoice*, not the claims, and the legs go back to standing on their own
    with their payments intact. `ra.can_cancel()` refuses a bill with receipts
    for a different reason: cancelling *that* would state nothing is owed on a
    document money was paid against.
    """
    if not doc:
        return False, "That merged document no longer exists."
    if is_cancelled(doc):
        return False, (f"Merged document {doc.get('tax_invoice_ref')} is already "
                       f"cancelled. There is no un-cancel — it would make the "
                       f"withdrawal deniable.")
    return True, ""


def apply_cancel(doc, reason: str, on: str = "") -> dict:
    """
    Withdraw the merged document, which **releases both legs**.

    Nothing is written to either source bill. Release is not a field — it is
    what `live_merge_of()` starts answering once this row is no longer live,
    which is the same "derive it, do not store it" rule the receipts arithmetic
    follows.

    ⚠ **The tax invoice number is NOT reused.** It has been quoted in somebody
    else's ledger and a second document bearing it is indistinguishable from the
    first — the reason a GST serial is never reissued.
    """
    doc["status"] = "cancelled"
    doc["cancelled_on"] = on or _now_date()
    doc["cancel_reason"] = str(reason or "")
    return doc


# =============================================================================
# PAGES
# =============================================================================

def _esc(v) -> str:
    return P.esc(str(v or ""))


def _alert(msg: str, kind: str = "error") -> str:
    return f'<div class="alert alert-{_esc(kind)}">{_esc(msg)}</div>' if msg else ""


def _flash() -> str:
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "success" if request.args.get("type") == "success" else "error"
    return _alert(msg, kind)


MERGED_STYLES = """
<style>
.mg-legband td {
  background: var(--surface); font-weight: 600; font-size: .82rem;
  text-transform: uppercase; letter-spacing: .04em;
}
.mg-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.mg-note { color: var(--muted); font-size: .82rem; margin-top: .35rem; }
@media (max-width: 760px) { .mg-pair { grid-template-columns: 1fr; } }
</style>
"""


def _shell(title: str, body: str) -> str:
    return BQ._page(f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{B.page_title(title)}</title>{B.HEAD_ICON}
{BASE_STYLES}{QUOTATION_STYLES}{BQ.BOQ_STYLES}{RA.RA_STYLES}{MERGED_STYLES}</head>
<body>{_nav()}
<main>{body}</main>
</body></html>""")


def status_badge(doc) -> str:
    if is_cancelled(doc):
        return ('<span class="pill" style="background:#fee2e2;color:#991b1b;'
                'border:1px solid #fecaca;">Cancelled</span>')
    return ('<span class="pill" style="background:#dcfce7;color:#166534;'
            'border:1px solid #bbf7d0;">Live</span>')


@merged_bp.route("/")
def list_merged():
    """The merged-RA register."""
    docs = records()
    rows = sorted(docs.values(),
                  key=lambda m: (str(m.get("date") or ""),
                                 str(m.get("tax_invoice_ref") or "")),
                  reverse=True)

    live = [m for m in rows if is_live(m)]
    n_void = len(rows) - len(live)
    total = sum(float(m.get("grand_total") or 0.0) for m in live)

    body_rows = ""
    for m in rows:
        void = is_cancelled(m)
        gt = ("&mdash;" if void
              else f"&#8377;&nbsp;{float(m.get('grand_total') or 0.0):,.2f}")
        out = "&mdash;" if void else f"&#8377;&nbsp;{balance(m):,.2f}"
        body_rows += f"""
        <tr{' style="opacity:.6;"' if void else ''}>
          <td class="td-ref"><a href="{url_for('merged_ra.view_merged', id=m.get('id'))}">
              {_esc(m.get('tax_invoice_ref'))}</a></td>
          <td class="td-muted">{_esc(m.get('date'))}</td>
          <td>{_esc(m.get('project_name')) or '&mdash;'}</td>
          <td class="td-muted">RA{_esc(m.get('supply_ra_no'))} + RA{_esc(m.get('installation_ra_no'))}</td>
          <td class="td-num" style="font-weight:600;">{gt}</td>
          <td class="td-num">{out}</td>
          <td>{status_badge(m)}</td>
          <td>{approval.cell("merged_ra", m)}</td>
          <td>
            <a href="{url_for('merged_ra.view_merged', id=m.get('id'))}" class="btn-view">&#128269; View</a>
            <a href="{url_for('merged_ra.print_merged', id=m.get('id'))}" class="btn-view"
               style="margin-left:.3rem;">&#128438; Print</a>
          </td>
        </tr>"""

    if rows:
        table = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Tax Invoice No.</th><th>Date</th><th>Project</th><th>Legs</th>
            <th style="text-align:right;">Grand Total</th>
            <th style="text-align:right;">Outstanding</th>
            <th>Status</th><th>Approval</th><th></th>
          </tr></thead>
          <tbody>{body_rows}</tbody>
        </table></div>"""
    else:
        table = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#129527;</div><br>
          <strong>No merged documents yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            A merged document stacks one issued RA-Supply bill and one issued
            RA-Installation bill from the same project onto a single sheet, and
            raises <b>one</b> tax invoice number over the pair. The two bills go
            on standing on their own.
          </p>
          <a href="{url_for('merged_ra.create_merged')}" class="btn"
             style="display:inline-block;margin-top:1.1rem;">+ Merge two bills</a>
        </div>"""

    return _shell("Merged RA Bills", f"""
      {_flash()}
      <div class="page-top">
        <h1>Merged <span>RA Register</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{url_for('ra.list_ras')}" class="btn btn-ghost">&#8592; RA Register</a>
          <a href="{url_for('merged_ra.create_merged')}" class="btn">+ Merge two bills</a>
        </div>
      </div>
      <div class="pipe-tiles">
        <div class="pipe-tile t-open">
          <div class="pt-lbl">Merged &amp; Invoiced</div>
          <div class="pt-val">&#8377;&nbsp;{total:,.0f}</div>
          <div class="pt-sub">{len(live)} live document{"s" if len(live) != 1 else ""}{f" &middot; {n_void} cancelled, excluded" if n_void else ""}</div>
        </div>
      </div>
      {table}""")


def _bill_options(pairs, name: str, selected: str) -> str:
    opts = '<option value="">&mdash; choose &mdash;</option>'
    for rid, b in pairs:
        sel = " selected" if rid == selected else ""
        opts += (f'<option value="{_esc(rid)}"{sel}>'
                 f'RA{_esc(b.get("ra_no"))} &middot; {_esc(b.get("ref"))} &middot; '
                 f'{_inr(float(b.get("grand_total") or 0.0))}</option>')
    return f'<select name="{name}">{opts}</select>'


@merged_bp.route("/create", methods=["GET", "POST"])
def create_merged():
    """
    Choose one issued supply bill and one issued installation bill.

    ⚠ **The BOQ is chosen first and the two lists are filtered to its revision
    chain**, so a pair from two different projects is not offerable. The
    same-project rule is still checked in `can_merge()` on the POST — an
    offerable list is presentation, and the gate is the gate.
    """
    boqs = STORE.get("boqs") or {}
    boq_id = (request.form.get("boq_id") if request.method == "POST"
              else request.args.get("boq")) or ""
    error = ""

    if request.method == "POST":
        bills = STORE.get("ra_bills") or {}
        s = bills.get((request.form.get("supply_ra_id") or "").strip())
        i = bills.get((request.form.get("installation_ra_id") or "").strip())
        doc, error = create(s, i, notes=(request.form.get("notes") or "").strip())
        if doc:
            return redirect(url_for("merged_ra.view_merged", id=doc["id"],
                                    msg=f"Merged document {doc['tax_invoice_ref']} raised.",
                                    type="success"))

    boq_opts = '<option value="">&mdash; choose a project &mdash;</option>'
    for bid, bq in sorted(boqs.items(), key=lambda kv: str(kv[1].get("ref") or "")):
        sel = " selected" if bid == boq_id else ""
        boq_opts += (f'<option value="{_esc(bid)}"{sel}>{_esc(bq.get("ref"))} '
                     f'&middot; {_esc(bq.get("project_name"))}</option>')

    picker = ""
    if boq_id:
        supply, install = candidates(boq_id)
        if not supply or not install:
            missing = []
            if not supply:
                missing.append("an issued RA-Supply bill")
            if not install:
                missing.append("an issued RA-Installation bill")
            picker = (f'<div class="mg-note">This project has no {" and no ".join(missing)} '
                      f'available to merge. A bill must be <b>issued</b> — a draft is not a '
                      f'claim that has gone anywhere, and a cancelled bill claims nothing — '
                      f'and it must not already be inside a live merged document.</div>')
        else:
            picker = f"""
            <div class="mg-pair">
              <div class="form-group"><label>RA-Supply bill</label>
                {_bill_options(supply, "supply_ra_id", request.form.get("supply_ra_id", ""))}</div>
              <div class="form-group"><label>RA-Installation bill</label>
                {_bill_options(install, "installation_ra_id", request.form.get("installation_ra_id", ""))}</div>
            </div>
            <div class="form-group"><label>Notes</label>
              <input type="text" name="notes" value="{_esc(request.form.get('notes'))}"/></div>
            <button type="submit" class="btn">Raise merged document</button>"""

    return _shell("Merge two RA bills", f"""
      <div class="page-top">
        <h1>Merge <span>two RA bills</span></h1>
        <a href="{url_for('merged_ra.list_merged')}" class="btn btn-ghost">&#8592; Merged register</a>
      </div>
      {_alert(error)}
      <form method="POST" action="{url_for('merged_ra.create_merged')}">
        <div class="form-section">
          <div class="section-title">&#128203; Which project?</div>
          <div class="form-group"><label>BOQ</label>
            <select name="boq_id" onchange="this.form.submit()">{boq_opts}</select></div>
          {picker}
        </div>
      </form>
      <div class="form-hint"><span class="fh-icon">&#8505;</span>
        <span>The two bills go on standing on their own &mdash; each keeps its
        own RA number, its own status and its own receipts. This document stacks
        their rows onto one sheet, adds the two stored totals, and raises
        <b>one</b> tax invoice number over the pair. It never holds claims of its
        own.</span></div>""")


@merged_bp.route("/view/<id>")
def view_merged(id: str):
    doc = records().get(id)
    if not doc:
        return redirect(url_for("merged_ra.list_merged",
                                msg="That merged document no longer exists.",
                                type="error"))
    supply_bill, install_bill = legs_of(doc)

    rows = ""
    last_leg = None
    for r in stacked_rows(doc):
        if r["_leg"] != last_leg:
            last_leg = r["_leg"]
            rows += (f'<tr class="mg-legband"><td colspan="6">'
                     f'RA{r["_ra_no"]} &mdash; {_esc(last_leg)} '
                     f'({_esc(r["_ref"])})</td></tr>')
        rows += (f'<tr><td>{_esc(r.get("item_no"))}</td>'
                 f'<td>{_esc(r.get("description"))}</td>'
                 f'<td>{_esc(r.get("unit"))}</td>'
                 f'<td class="td-num">{_esc(RA._qty(r.get("qty")))}</td>'
                 f'<td class="td-num">{_inr(float(r.get("rate") or 0.0))}</td>'
                 f'<td class="td-num">{_inr(float(r.get("amount") or 0.0))}</td></tr>')

    def _leg_line(bill, leg):
        if not bill:
            return (f'<div class="mg-note">The {leg} bill has been removed. This '
                    f'document still states what it covered.</div>')
        return (f'<div><a href="{url_for("ra.view_ra", id=bill.get("id"))}">'
                f'RA{_esc(bill.get("ra_no"))} &middot; {_esc(bill.get("ref"))}</a> '
                f'&mdash; {_inr(float(bill.get("grand_total") or 0.0))}</div>')

    cancel_bit = ""
    if is_live(doc):
        cancel_bit = (f'<a href="{url_for("merged_ra.cancel_merged", id=id)}" '
                      f'class="btn btn-ghost">Cancel document</a>')

    return _shell(f"Merged {doc.get('tax_invoice_ref')}", f"""
      {_flash()}
      <div class="page-top">
        <h1>{_esc(doc.get('tax_invoice_ref'))}
          <span style="font-size:.8rem;font-weight:500;">{status_badge(doc)}</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{url_for('merged_ra.list_merged')}" class="btn btn-ghost">&#8592; Register</a>
          <a href="{url_for('merged_ra.print_merged', id=id)}" class="btn">&#128438; Print</a>
          {cancel_bit}
        </div>
      </div>
      {approval.panel("merged_ra", doc)}
      <div class="form-section">
        <div class="section-title">&#128279; The two bills this covers</div>
        {_leg_line(supply_bill, "supply")}
        {_leg_line(install_bill, "installation")}
        <div class="mg-note">Each keeps its own number, its own status and its
          own receipts. Cancelling this document releases both of them.</div>
      </div>
      <div class="form-section">
        <div class="section-title">&#128209; Stacked rows &mdash; both legs</div>
        <div class="cl-wrap"><table class="claims">
          <thead><tr><th>Item</th><th>Description</th><th>Unit</th>
            <th style="text-align:right;">Qty</th>
            <th style="text-align:right;">Rate</th>
            <th style="text-align:right;">Amount</th></tr></thead>
          <tbody>{rows}</tbody>
        </table></div>
      </div>
      <div class="form-section">
        <div class="section-title">&#128176; Totals &mdash; the two bills' own stored figures, added</div>
        <table class="claims">
          <tr><td>Claim subtotal</td><td class="td-num">{_inr(float(doc.get('claim_subtotal') or 0.0))}</td></tr>
          <tr><td>Deductions</td><td class="td-num">{_inr(float(doc.get('deduction_total') or 0.0))}</td></tr>
          <tr><td>Net payable</td><td class="td-num">{_inr(float(doc.get('net_payable') or 0.0))}</td></tr>
          <tr><td>Tax</td><td class="td-num">{_inr(float(doc.get('tax_amount') or 0.0))}</td></tr>
          <tr><td><b>Grand total</b></td><td class="td-num"><b>{_inr(float(doc.get('grand_total') or 0.0))}</b></td></tr>
          <tr><td>Outstanding across both legs</td><td class="td-num">{_inr(balance(doc))}</td></tr>
        </table>
        <div class="mg-note">Nothing here is recomputed from the schedule. Each
          figure is the sum of what the two bills stored when they were issued,
          so a later revision of the BOQ cannot move a document that has been
          sent.</div>
      </div>""")


@merged_bp.route("/print/<id>")
def print_merged(id: str):
    """
    The A4 sheet, through `docsheet.py` like every other printed document.

    ⚠ **Gated by B7 exactly as `/ra/print/<id>` is.** A merged document that has
    not finished its ladder does not print, and the refusal is **by URL**.
    """
    doc = records().get(id)
    if not doc:
        return redirect(url_for("merged_ra.list_merged",
                                msg="That merged document no longer exists.",
                                type="error"))

    allowed, why = approval.can_print("merged_ra", doc)
    if not allowed:
        return redirect(url_for("merged_ra.view_merged", id=id, msg=why, type="error"))

    rows = ""
    n = 0
    last_leg = None
    for r in stacked_rows(doc):
        if r["_leg"] != last_leg:
            last_leg = r["_leg"]
            rows += (f'<tr class="sec-row"><td colspan="7">'
                     f'RA{r["_ra_no"]} &mdash; {_esc(last_leg).upper()} '
                     f'&mdash; {_esc(r["_ref"])}</td></tr>')
        n += 1
        rows += (f'<tr><td class="c-sno">{n}</td>'
                 f'<td class="c-desc">{_esc(r.get("description"))}</td>'
                 f'<td class="c-hsn">{_esc(r.get("hsn_sac"))}</td>'
                 f'<td class="c-qty">{_esc(RA._qty(r.get("qty")))}</td>'
                 f'<td class="c-unit">{_esc(r.get("unit"))}</td>'
                 f'<td class="c-rate">{DS._inr(float(r.get("rate") or 0.0))}</td>'
                 f'<td class="c-amt">{DS._inr(float(r.get("amount") or 0.0))}</td></tr>')

    columns = (("c-sno", "S.No"), ("c-desc", "Description"), ("c-hsn", "HSN/SAC"),
               ("c-qty", "Qty"), ("c-unit", "Unit"), ("c-rate", "Rate"),
               ("c-amt", "Amount"))

    tax_rows = ""
    for slab in tax_slabs(doc):
        for head, amt in slab.get("heads", []):
            tax_rows += DS.sum_row(f"{_esc(head)}", DS._inr(float(amt or 0.0)))

    # ⚠ `_meta()` takes PRE-ESCAPED values by contract (ABOUT.md §9), so every
    #   argument here is escaped at the call site and none of them is escaped
    #   twice. The seller half is read from `branding` at render, exactly as
    #   `ra.print_ra()` does — a hardcoded GSTIN on the face of a tax invoice
    #   is what `tests/test_ra_seller_identity.py` exists to refuse.
    meta_col_1 = (
        _meta("Tax Invoice No.", _esc(doc.get("tax_invoice_ref"))) +
        _meta("Covers", f"RA{_esc(doc.get('supply_ra_no'))} (supply) + "
                        f"RA{_esc(doc.get('installation_ra_no'))} (installation)") +
        _meta("Against BOQ", _esc(doc.get("boq_ref")) or "&mdash;") +
        _meta("Project", _esc(doc.get("project_name")) or "&mdash;") +
        _meta("Buyer's GSTIN", _esc(doc.get("bill_gstin")) or "&mdash;")
    )
    meta_col_2 = (
        _meta("Date", _esc(doc.get("date"))) +
        _meta("Supply bill", _esc(doc.get("supply_ref")) or "&mdash;") +
        _meta("Installation bill", _esc(doc.get("installation_ref")) or "&mdash;") +
        _meta("Our GSTIN", _esc(B.COMPANY_GSTIN) or "&mdash;") +
        _meta("Contact Person", _esc(doc.get("contact_person")) or "&mdash;")
    )

    # ⚠ **`name_block()` and `secondary_block()` escape their own argument and
    #   return "" when it is empty**, so the RAW value goes in and the fallback
    #   stays OUTSIDE the call. `esc(x) or "&mdash;"` here would hand the entity
    #   to the escaper and print a literal `&amp;mdash;` on a tax invoice —
    #   ABOUT.md §9's "do not escape twice", and `tests/test_entity_fallbacks.py`
    #   caught exactly that on this page before it was written this way.
    #   `ra.print_ra()` puts the `or` outside for the same reason.
    party = DS.party_block(
        "To",
        DS.name_block(doc.get("to")) or '<span class="dh-name">&mdash;</span>',
        DS.secondary_block("Site", doc.get("site_location")),
        meta_col_1, meta_col_2)
    meta = ""

    void_band = ""
    if is_cancelled(doc):
        void_band = ('<div class="draft-mark">CANCELLED &mdash; '
                     'this document has been withdrawn and is not a demand for payment</div>')

    sheet = (DS.sheet_open(title_band="MERGED TAX INVOICE")
             + party + meta + void_band
             + DS.items_table(columns, rows)
             + DS.sum_row("Claim subtotal", DS._inr(float(doc.get("claim_subtotal") or 0.0)))
             + DS.sum_row("Less deductions", DS._inr(float(doc.get("deduction_total") or 0.0)))
             + DS.sum_row("Net payable", DS._inr(float(doc.get("net_payable") or 0.0)))
             + tax_rows
             + DS.sum_row("Rounding off", DS._inr(float(doc.get("rounding_off") or 0.0)))
             + DS.total_row("Grand Total", "", DS._inr(float(doc.get("grand_total") or 0.0)))
             + DS.amount_words("Amount in words", float(doc.get("grand_total") or 0.0))
             + DS.bank_block()
             + DS.sig_block(computer_generated=True)
             + DS.sheet_close())

    return BQ._page(f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{B.page_title(str(doc.get('tax_invoice_ref') or 'Merged'))}</title>{B.HEAD_ICON}
{DS.SHEET_STYLES}{DS.DOCSHEET_STYLES}{RA.RA_DOC_STYLES}
{approval.print_block("merged_ra", doc)}</head>
<body>
{_nav()}
<main>
<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Merged Tax Invoice <span style="color:var(--brand);">{_esc(doc.get('tax_invoice_ref'))}</span>
  </h1>
  <div style="display:flex;gap:.6rem;">
    <a href="{url_for('merged_ra.view_merged', id=id)}" class="btn btn-ghost">&#8592; Back</a>
    <button class="btn" onclick="window.print()">&#128438; Print</button>
  </div>
</div>
{sheet}
</main>
</body></html>""")


@merged_bp.route("/cancel/<id>", methods=["GET", "POST"])
def cancel_merged(id: str):
    """
    Withdraw a merged document, releasing both legs.

    ⚠ **The GET renders a confirmation and mutates nothing**; the change happens
    only inside the POST branch. `ra.issue_ra()` and `ra.cancel_ra()` set that
    shape and it is the standing rule for every state-changing route here — a
    browser `confirm()` is not a guard, because a prefetch, a crawler and the
    back button all issue a plain GET and none of them sees one.
    """
    doc = records().get(id)
    if not doc:
        return redirect(url_for("merged_ra.list_merged",
                                msg="That merged document no longer exists.",
                                type="error"))

    allowed, why = can_cancel(doc)
    if not allowed:
        return redirect(url_for("merged_ra.view_merged", id=id, msg=why, type="error"))

    if request.method == "POST":
        apply_cancel(doc, (request.form.get("reason") or "").strip())
        return redirect(url_for("merged_ra.view_merged", id=id,
                                msg=(f"{doc.get('tax_invoice_ref')} cancelled. "
                                     f"Both bills are released."),
                                type="success"))

    return _shell("Cancel merged document", f"""
      <div class="page-top"><h1>Cancel <span>{_esc(doc.get('tax_invoice_ref'))}</span></h1></div>
      <div class="del-box">
        <h2>&#9888; The number is not reused</h2>
        <div class="del-line">
          This withdraws the merged tax invoice. <b>{_esc(doc.get('tax_invoice_ref'))}</b>
          stays spent &mdash; it has been quoted in somebody else's ledger, and a
          second document bearing it would be indistinguishable from the first.
          <br/><br/>
          RA{_esc(doc.get('supply_ra_no'))} and RA{_esc(doc.get('installation_ra_no'))}
          are <b>released</b> and may be merged again. Neither bill is otherwise
          touched: their receipts, their status and their own numbers are
          unchanged.
        </div>
      </div>
      <form method="POST" action="{url_for('merged_ra.cancel_merged', id=id)}">
        <div class="form-group"><label>Why is it being withdrawn?</label>
          <input type="text" name="reason" /></div>
        <div style="display:flex;gap:.7rem;">
          <button type="submit" class="btn">Cancel the document</button>
          <a href="{url_for('merged_ra.view_merged', id=id)}" class="btn btn-ghost">Keep it</a>
        </div>
      </form>""")
