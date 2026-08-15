"""
receipt.py — Payments RECEIVED against an RA bill
=================================================
The third link in the BOQ chain, and the first one that is about money coming
back rather than money being claimed:

    BOQ ──► RA bill 1 ──► RA bill 2 ──► …
                 │
                 └──► receipt, receipt, …          money IN

An **RA bill** is a claim: what we say we are owed. A **receipt** is a payment:
what the main contractor actually paid, when, and how. Until this module
existed, nothing in this app recorded a payment at all — ABOUT.md §3's warning
on the proforma ("Invoiced, not received. Nothing in this app records payment")
was true of the whole system. It is now true only of the quotation chain.

Its OWN collection, never a list on the bill
--------------------------------------------
`STORE["receipts"]`, keyed by uuid, each row pointing at the bill it pays.

It is deliberately **not** embedded on the RA bill and emphatically not on the
BOQ. `boq.MAX_JSON_BYTES` is 300,000 and the client's real data shape reaches it
at ~428 lines, below `MAX_LINES` — so anything appended to a BOQ record eats
that headroom and pushes the failure into the schedule editor, where the
operator loses an afternoon's work on something unrelated to what grew.
`ra_bills` was split out for that reason; this is the same rule, applied once
more (CLIENT_CHANGES.md §1.3).

The one rule this module exists to protect
------------------------------------------
**A receipt entered, corrected or deleted today must never change a bill that
was printed yesterday.**

The previous balance carried onto an RA bill is snapshotted onto that bill by
`ra.create_ra()` at the moment it is raised, and every renderer reads it off the
bill's own record. Nothing in this file writes to an RA bill, and nothing in
`ra.print_ra()` reads this collection. That is not a convention — it is the
whole reason the snapshot exists, and `tests/test_receipts.py` asserts the
printed document is byte-identical across a receipt being added, edited and
removed underneath it.

This is the same defect class that already shipped once here: `print_ra()` was
built as a loop over the live `boq["line_items"]`, so revising a schedule
silently rewrote a document the client had already been sent
(CLIENT_CHANGES.md §1.2).

Import direction
----------------
    receipt.py ──► ra.py         the bill a payment is against, the revision
                                 chain, and the balance arithmetic
    receipt.py ──► quotation.py  QUOTATION_STYLES / _inr — the same widgets, so
                                 this form IS the RA form
    receipt.py ──► dashboard.py  BASE_STYLES / _nav
    receipt.py ──► pipeline.py   esc / parse_money / fy_of / fy_ref
    receipt.py ──► store, branding

`ra.py` must **never** import this module, and neither may `boq.py`. `ra.py`
renders its receipts panel by reading `STORE["receipts"]` directly and linking
out with `url_for("receipt.…")` — the one-way trick this codebase already runs
between quotation/proforma, proforma/invoice, quotation/purchase and boq/ra.
The arithmetic itself lives in `ra.py` precisely so that this direction holds:
`create_ra()` needs the carried balance at save time, so the figure cannot live
downstream of it.

It must not import `invoice.py`, `proforma.py`, `purchase.py`, `product.py` or
`spec.py`. All of this is asserted in `tests/test_import_directions.py`.
"""

import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import boq as BQ
import branding as B
import pipeline as P
import ra as RA
from dashboard import BASE_STYLES, _nav
from store import STORE

# The form widgets, so a receipt form looks like every other form in the app
# rather than like a second design. Same stack `ra._shell()` layers.
from quotation import QUOTATION_STYLES, _inr

receipt_bp = Blueprint("receipt", __name__, url_prefix="/receipt")

# =============================================================================
# BUSINESS RULES — module-level constants, never buried in a branch
# =============================================================================

_REF_SERIES = "RCPT"

# Same FY-scoped series shape as the BOQ, the PO, the tax invoice and the RA
# bill, through the same `pipeline.fy_ref`. No 16-character cap: Rule 46(b)
# governs a tax invoice number and a receipt is not one.
_REF_CAP = 64

# A receipt records money that arrived. Zero is not a payment and negative is a
# refund — a different document with different accounting, and deliberately out
# of scope here rather than smuggled in as a negative receipt. Recorded as an
# open item in CLIENT_CHANGES.md item 8.
_MIN_AMOUNT = 0.005

# Free-text caps. Not a security boundary — `_esc()` is — but a receipt whose
# note is a pasted email thread bloats a collection that `db.sync()` diffs on
# every request.
_MAX_TEXT = 200
_MAX_NOTES = 1000


# =============================================================================
# THE RECORD
# =============================================================================
#
# STORE["receipts"][uuid] = {
#   "id": uuid,
#   "ref": "SF/RCPT/26-27/0001",   # our own series, FY-scoped
#   "fy": "26-27",
#   "date": "2026-08-14",          # the date the money was RECEIVED, which is
#                                  # not the instrument's own date
#
#   # The bill this pays. `ra_id` is the key; every other field here is a
#   # SNAPSHOT taken at save, for the reason every back-reference in this app is
#   # stored rather than looked up — the ledger still reads correctly as a
#   # historical record if the bill is removed, and it names what it paid.
#   "ra_id": uuid, "ra_ref": "SF/RA/26-27/0004", "ra_no": 4, "leg": "supply",
#
#   # The project, snapshotted for the same reason. `boq_id` is what the ledger
#   # groups on, and it is the bill's BOQ — a SPECIFIC revision.
#   "boq_id": uuid, "boq_ref": "SF/BOQ/26-27/0001",
#   "project_name": str, "account_name": str,
#
#   "amount": 250000.0,            # what arrived. Always > 0.
#   "mode": "neft",                # one of ra.RECEIPT_MODES
#   "instrument_ref": "UTR12345",  # cheque number, UTR, transaction id
#   "instrument_date": "2026-08-13",
#   "notes": str,
# }
#
# Four properties this shape exists to guarantee:
#
# 1. **The resulting balance is NOT a field here.** It is computed —
#    `ra.outstanding_of()` for one bill, `ra.previous_balance()` for the chain.
#    Storing it would be a third representation of a number already derivable
#    from two others, and the moment an earlier receipt is corrected the stored
#    one disagrees with both. "Two fields that must agree are two fields that
#    can disagree" is the argument `ra.print_ra()` already makes for deriving
#    the seller's State from the GSTIN instead of storing it beside one.
#
#    The one place a balance IS frozen is on the RA BILL, by `ra.create_ra()`,
#    because that is a figure printed on a document that has left the building.
#    A ledger row is a current-state screen; a bill is a record of what was
#    sent. The two get opposite treatment on purpose.
#
# 2. **It is keyed to a BILL, not to a BOQ.** Money is received against a claim,
#    and which project that rolls up to is the bill's business. `boq_id` is
#    carried for grouping only and is never the match key.
#
# 3. **A receipt survives its BOQ being superseded.** The bill it pays was
#    raised against one specific revision, and `ra.previous_balance()` walks the
#    whole revision chain — so a payment against a bill raised on revision 0
#    still counts once revision 1 is live. Anything that summed against a single
#    BOQ record would silently reset the carried balance to zero on every
#    revision, which is the same trap `ra.claimed_by_line()` exists to avoid.
#
# 4. **Deleting a receipt never rewrites a bill.** See the module docstring.


def new_id() -> str:
    return str(uuid.uuid4())


def next_ref(datestr: str) -> str:
    """
    Next receipt number — 'SF/RCPT/26-27/0001'.

    FY-scoped and max+1 within the year, not len+1: a gap left by a deleted
    receipt must never re-issue a number that has already been quoted on a
    remittance advice. `proforma._next_ref()`'s rule, shared by every series in
    this app.
    """
    fy = P.fy_of(datestr)
    highest = 0
    for r in (STORE.get("receipts") or {}).values():
        if r.get("fy") != fy:
            continue
        tail = str(r.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=_REF_CAP)


def receipts_of_boq(boq_id: str) -> list:
    """
    Every receipt against every bill in one project's REVISION CHAIN.

    Chain-scoped, not record-scoped, for property 3 above.
    """
    ids = set(RA.revision_chain(boq_id))
    if not ids:
        return []
    rows = [(rid, r) for rid, r in (STORE.get("receipts") or {}).items()
            if str(r.get("boq_id") or "") in ids]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""), kv[0]))
    return rows


def _validate(form, bill: dict) -> tuple:
    """
    (data, error) — and **always returns data**, so a rejected form re-renders
    with what the operator typed still in it. `address._validate()`'s contract.
    """
    today = _date.today().isoformat()
    data = {
        "date": (form.get("date") or today).strip()[:_MAX_TEXT],
        "amount_raw": (form.get("amount") or "").strip()[:_MAX_TEXT],
        "mode": (form.get("mode") or "neft").strip().lower()[:_MAX_TEXT],
        "instrument_ref": (form.get("instrument_ref") or "").strip()[:_MAX_TEXT],
        "instrument_date": (form.get("instrument_date") or "").strip()[:_MAX_TEXT],
        "notes": (form.get("notes") or "").strip()[:_MAX_NOTES],
    }

    # **A receipt may only be recorded against an ISSUED bill**, and this is
    # checked before anything the operator typed, because it is a fact about the
    # bill rather than about the form — no correction to the amount or the date
    # can make a draft receiptable.
    #
    # The rule and its wording both live in `ra.can_receipt()`: `/ra/view`
    # disables its own "Record a payment" control from the same function, and a
    # guard stated in two places is a guard that ends up meaning two things.
    # `receipt.py ──► ra.py`, never the reverse (ABOUT.md §2c).
    allowed, why = RA.can_receipt(bill)
    if not allowed:
        return data, why

    if data["mode"] not in RA.RECEIPT_MODES:
        return data, "Pick how the money arrived."
    if not data["date"]:
        return data, "A receipt needs the date the money was received."

    amount = float(P.parse_money(data["amount_raw"]) or 0.0)
    if amount < _MIN_AMOUNT:
        return data, ("Enter the amount received. A receipt records money that "
                      "arrived, so it has to be more than zero — a refund is a "
                      "different document and is not recorded here.")
    data["amount"] = round(amount, 2)
    return data, ""


def _overpay_note(bill: dict, amount: float, exclude_id: str = None) -> str:
    """
    A WARNING when this receipt takes the bill past what it claimed. Never a
    block.

    The house rule, and the same treatment a claim rate that diverges from the
    approved BOQ gets: surface it, name the arithmetic, and let the operator
    decide (DOMAIN.md §6). A lump sum settling two
    bills at once is a real thing the client's main contractor does, and a hard
    block would make the ledger unable to record what actually happened
    (DOMAIN.md §6).
    """
    if not bill:
        return ""
    already = RA.received_against(str(bill.get("id") or ""))
    if exclude_id:
        prior = (STORE.get("receipts") or {}).get(exclude_id) or {}
        already = round(already - float(prior.get("amount") or 0.0), 2)
    gross = float(bill.get("grand_total") or 0.0)
    total = round(already + float(amount or 0.0), 2)
    if total - gross < _MIN_AMOUNT:
        return ""
    return (f"This takes total receipts against RA{bill.get('ra_no')} to "
            f"{_inr(total)} against a bill of {_inr(gross)} — "
            f"{_inr(total - gross)} more than was claimed. Recorded as entered; "
            f"the excess carries forward as a credit on the next bill.")


# =============================================================================
# PAGE FURNITURE
# =============================================================================
#
# No `render_template_string` anywhere in this module, and none is to be added.
# A fully-interpolated string parsed a second time by Jinja executes any
# `{{ }}` that arrived in user input, and nothing here is passed as Jinja
# context — so the second parse is pure downside (ABOUT.md §7.9d).

def _page(html: str) -> str:
    """A finished page. Deliberately not Jinja-rendered."""
    return html


def _esc(v) -> str:
    return P.esc("" if v is None else str(v))


def _shell(title: str, body: str) -> str:
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{BQ.BOQ_STYLES}{RA.RA_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
</main>
</body></html>""")


def _alert(msg: str, kind: str = "error") -> str:
    """A banner. **Escapes its own message** — every caller passes plain text."""
    return f'<div class="alert {kind}">{_esc(msg)}</div>' if msg else ""


def _flash() -> str:
    """A redirect's ?msg=&type= banner. Raw — `_alert()` does the escaping."""
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "success" if request.args.get("type") == "success" else "error"
    return _alert(msg, kind)


def _mode_options(selected: str) -> str:
    """
    The mode picker, as a `<select>` over `ra.RECEIPT_MODES`.

    A select over the shared list rather than a free-text box: the ledger groups
    on this value, and a typed "NEFT " with a trailing space is a second mode
    nobody can see. The option list lives in `ra.py` so this form and the bill's
    own receipts panel can never label the same value differently.
    """
    sel = str(selected or "").lower()
    return "".join(
        f'<option value="{_esc(m)}"{" selected" if m == sel else ""}>'
        f'{_esc(RA.RECEIPT_MODE_LABELS.get(m, m))}</option>'
        for m in RA.RECEIPT_MODES)


def _bill_facts(bill: dict, exclude_id: str = None) -> str:
    """The five facts above the form — where this money is going."""
    rid = str(bill.get("id") or "")
    received = RA.received_against(rid)
    if exclude_id:
        prior = (STORE.get("receipts") or {}).get(exclude_id) or {}
        received = round(received - float(prior.get("amount") or 0.0), 2)
    gross = float(bill.get("grand_total") or 0.0)
    return f"""
    <div class="ra-meta">
      <div class="ra-fact"><b>Bill</b><span>RA{_esc(bill.get("ra_no"))} &middot; {_esc(bill.get("leg"))}</span></div>
      <div class="ra-fact"><b>Reference</b><span>{_esc(bill.get("ref"))}</span></div>
      <div class="ra-fact"><b>Project</b><span>{_esc(bill.get("project_name"))}</span></div>
      <div class="ra-fact"><b>Bill total</b><span>{_inr(gross)}</span></div>
      <div class="ra-fact"><b>Received so far</b><span>{_inr(received)}</span></div>
    </div>"""


def _form(bill: dict, data: dict, error: str, action: str, back_url: str,
          submit_label: str, exclude_id: str = None, extra_note: str = "") -> str:
    """The receipt form, shared by add and edit — one form, two entry points."""
    heading = f"Payment against RA{int(bill.get('ra_no') or 0)}"
    return _shell(heading, f"""
  <div class="page-top">
    <h1>Record a <span>payment</span></h1>
    <a href="{back_url}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {_alert(error)}
  {extra_note}
  {_bill_facts(bill, exclude_id)}
  <form method="POST" action="{action}">
    <div class="form-section">
      <div class="section-title">&#128176; What arrived</div>
      <div class="fg2">
        <div class="form-group"><label for="date">Date received</label>
          <input type="date" id="date" name="date" value="{_esc(data.get("date"))}"/></div>
        <div class="form-group"><label for="amount">Amount received</label>
          <input type="text" id="amount" name="amount" inputmode="decimal"
                 placeholder="0.00" value="{_esc(data.get("amount_raw"))}"/></div>
      </div>
      <div class="fg2">
        <div class="form-group"><label for="mode">Mode</label>
          <select id="mode" name="mode">{_mode_options(data.get("mode"))}</select></div>
        <div class="form-group"><label for="instrument_ref">Cheque no. / UTR / txn id</label>
          <input type="text" id="instrument_ref" name="instrument_ref"
                 value="{_esc(data.get("instrument_ref"))}"/></div>
      </div>
      <div class="fg2">
        <div class="form-group"><label for="instrument_date">Instrument date</label>
          <input type="date" id="instrument_date" name="instrument_date"
                 value="{_esc(data.get("instrument_date"))}"/></div>
        <div class="form-group"><label for="notes">Notes</label>
          <input type="text" id="notes" name="notes" value="{_esc(data.get("notes"))}"/></div>
      </div>
      <div class="form-hint"><span class="fh-icon">&#8505;</span>
        <span>The balance left on this bill is worked out from the ledger and is
        not typed. What gets <b>printed</b> on the next bill is frozen onto that
        bill when it is raised &mdash; entering a payment here never changes a
        bill that has already gone out.</span></div>
    </div>
    <div style="display:flex;gap:.7rem;">
      <button type="submit" class="btn">{_esc(submit_label)}</button>
      <a href="{back_url}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>""")


# =============================================================================
# ROUTES
# =============================================================================

@receipt_bp.route("/")
def list_receipts():
    """
    The receipts ledger. `?boq=<id>` narrows it to one project's chain.

    A **current-state screen**, so every balance on it is computed live from the
    collection rather than read off a stored field. That is the opposite of what
    `/ra/print` does, and deliberately so: this page answers "where does the
    money stand today", and the document answers "what did we state when we sent
    it".
    """
    boq_id = (request.values.get("boq") or "").strip()
    boqs = STORE.get("boqs") or {}

    if boq_id and boq_id in boqs:
        rows = receipts_of_boq(boq_id)
        scope = f'{boqs[boq_id].get("ref") or ""} &middot; {_esc(boqs[boq_id].get("project_name"))}'
        bills = RA.bills_of(boq_id)
    else:
        rows = sorted((STORE.get("receipts") or {}).items(),
                      key=lambda kv: (str(kv[1].get("date") or ""), kv[0]))
        scope = "All projects"
        bills = []

    body = "".join(
        f'<tr><td class="cl-no">{_esc(r.get("ref"))}</td>'
        f'<td class="cl-desc">{_esc(r.get("date"))}</td>'
        f'<td class="cl-desc">{_esc(r.get("project_name"))}</td>'
        f'<td class="cl-no">RA{_esc(r.get("ra_no"))}</td>'
        f'<td class="cl-unit">{_esc(RA.RECEIPT_MODE_LABELS.get(str(r.get("mode") or ""), r.get("mode") or ""))}</td>'
        f'<td class="cl-desc">{_esc(r.get("instrument_ref")) or "&mdash;"}</td>'
        f'<td class="cl-amt">{_inr(r.get("amount") or 0.0)}</td>'
        f'<td><a class="btn btn-ghost" href="{url_for("receipt.edit_receipt", id=rid)}">Edit</a> '
        f'<a class="btn btn-ghost" href="{url_for("receipt.delete_receipt", id=rid)}">Delete</a></td></tr>'
        for rid, r in rows)
    empty = '<tr><td colspan="8" style="color:var(--muted);">No receipts recorded.</td></tr>'
    total = round(sum(float(r.get("amount") or 0.0) for _rid, r in rows), 2)

    # The per-bill position, only when the ledger is scoped to one project —
    # across all projects the column would be summing unrelated schedules.
    pos_html = ""
    if bills:
        billed = round(sum(float(b.get("grand_total") or 0.0) for _rid, b in bills), 2)
        outstanding = round(sum(RA.outstanding_of(b) for _rid, b in bills), 2)
        pos_rows = "".join(
            f'<tr><td class="cl-no">RA{_esc(b.get("ra_no"))}</td>'
            f'<td class="cl-unit">{_esc(b.get("leg"))}</td>'
            f'<td class="cl-desc">{_esc(b.get("date"))}</td>'
            f'<td class="cl-amt">{_inr(b.get("grand_total") or 0.0)}</td>'
            f'<td class="cl-amt">{_inr(RA.received_against(rid))}</td>'
            f'<td class="cl-amt">{_inr(RA.outstanding_of(b))}</td>'
            f'<td><a class="btn btn-ghost" href="{url_for("receipt.new_receipt", ra=rid)}">'
            f'&#43; Payment</a></td></tr>'
            for rid, b in bills)
        pos_html = f"""
  <div class="form-section">
    <div class="section-title">&#128202; Position by bill</div>
    <div class="cl-wrap"><table class="claims">
      <thead><tr><th>Bill</th><th>Leg</th><th>Date</th>
        <th style="text-align:right;">Billed</th>
        <th style="text-align:right;">Received</th>
        <th style="text-align:right;">Outstanding</th><th></th></tr></thead>
      <tbody>{pos_rows}</tbody>
    </table></div>
    <div class="ra-foot">
      <span><b>Billed</b> <span class="ra-tot">{_inr(billed)}</span></span>
      <span><b>Received</b> <span class="ra-tot">{_inr(total)}</span></span>
      <span><b>Outstanding</b> <span class="ra-tot">{_inr(outstanding)}</span></span>
    </div>
    <p style="font-size:.75rem;color:var(--muted);margin-top:.6rem;">
      Live figures, across the whole revision chain. What a bill
      <b>printed</b> as its previous balance is frozen on that bill and is not
      restated here.
    </p>
  </div>"""

    return _shell("Receipts", f"""
  <div class="page-top">
    <h1>Receipts <span>&middot; {scope}</span></h1>
    <a href="{url_for('ra.list_ras')}" class="btn btn-ghost">&#8592; RA bills</a>
  </div>
  {_flash()}
  {pos_html}
  <div class="form-section">
    <div class="section-title">&#128179; Payments received</div>
    <div class="cl-wrap"><table class="claims">
      <thead><tr><th>Receipt</th><th>Date</th><th>Project</th><th>Bill</th>
        <th>Mode</th><th>Instrument</th>
        <th style="text-align:right;">Amount</th><th></th></tr></thead>
      <tbody>{body or empty}</tbody>
    </table></div>
    <div class="ra-foot">
      <span><b>Total received</b> <span class="ra-tot">{_inr(total)}</span></span>
    </div>
  </div>""")


@receipt_bp.route("/new", methods=["GET", "POST"])
def new_receipt():
    """Record a payment against one RA bill. `?ra=<id>` names the bill."""
    ra_id = (request.values.get("ra") or "").strip()
    bill = (STORE.get("ra_bills") or {}).get(ra_id)

    if not bill:
        # No bill chosen — pick one, exactly as `ra.create_ra()` renders a BOQ
        # picker rather than a blank form. There is no such thing as a receipt
        # against nothing.
        # Every bill is LISTED, and only the issued ones offer a Record link —
        # the refusal rides on the disabled control rather than the row being
        # dropped. A draft that has silently vanished from this picker is
        # indistinguishable from one that does not exist.
        def _pick(rid: str, b: dict) -> str:
            allowed, why = RA.can_receipt(b)
            if allowed:
                return (f'<a class="btn btn-ghost" '
                        f'href="{url_for("receipt.new_receipt", ra=rid)}">Record</a>')
            return (f'<span class="btn btn-ghost" style="opacity:.55;'
                    f'cursor:not-allowed;" title="{_esc(why)}">Record</span>')

        rows = "".join(
            f'<tr><td class="cl-no">RA{_esc(b.get("ra_no"))}</td>'
            f'<td class="cl-desc">{_esc(b.get("ref"))}</td>'
            f'<td class="cl-desc">{_esc(b.get("project_name"))}</td>'
            f'<td class="cl-amt">{_inr(b.get("grand_total") or 0.0)}</td>'
            f'<td class="cl-amt">{_inr(RA.outstanding_of(b))}</td>'
            f'<td>{_pick(rid, b)}</td></tr>'
            for rid, b in sorted((STORE.get("ra_bills") or {}).items(),
                                 key=lambda kv: str(kv[1].get("ref") or "")))
        empty = '<tr><td colspan="6">No RA bills yet.</td></tr>'
        return _shell("Record a payment", f"""
  <div class="page-top">
    <h1>Record a <span>payment</span></h1>
    <a href="{url_for('receipt.list_receipts')}" class="btn btn-ghost">&#8592; Receipts</a>
  </div>
  {_flash()}
  <div class="form-section">
    <div class="section-title">&#128203; Which bill was this paid against?</div>
    <div class="cl-wrap"><table class="claims">
      <thead><tr><th>Bill</th><th>Reference</th><th>Project</th>
        <th style="text-align:right;">Billed</th>
        <th style="text-align:right;">Outstanding</th><th></th></tr></thead>
      <tbody>{rows or empty}</tbody>
    </table></div>
  </div>""")

    today = _date.today().isoformat()
    data = {"date": today, "amount_raw": "", "mode": "neft",
            "instrument_ref": "", "instrument_date": "", "notes": ""}
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form, bill)
        if not error:
            rid = new_id()
            STORE["receipts"][rid] = {
                "id": rid,
                "ref": next_ref(data["date"]),
                "fy": P.fy_of(data["date"]),
                "date": data["date"],
                # Every one of these is a SNAPSHOT, stored rather than looked
                # up, so the ledger still reads as a historical record if the
                # bill is removed. `ra_id` is the only one that is a key.
                "ra_id": ra_id,
                "ra_ref": str(bill.get("ref") or ""),
                "ra_no": int(bill.get("ra_no") or 0),
                "leg": str(bill.get("leg") or ""),
                "boq_id": str(bill.get("boq_id") or ""),
                "boq_ref": str(bill.get("boq_ref") or ""),
                "project_name": str(bill.get("project_name") or ""),
                "account_name": str(bill.get("account_name") or ""),
                "amount": data["amount"],
                "mode": data["mode"],
                "instrument_ref": data["instrument_ref"],
                "instrument_date": data["instrument_date"],
                "notes": data["notes"],
            }
            # NOTHING is written to the RA bill here. Not its `prev_balance`,
            # not any later bill's. That is the contract this module exists to
            # keep — see the module docstring.
            note = _overpay_note(bill, data["amount"], exclude_id=rid)
            return redirect(url_for("ra.view_ra", id=ra_id,
                                    msg=note or "Payment recorded.",
                                    type="error" if note else "success"))

    return _form(bill, data, error,
                 action=url_for("receipt.new_receipt", ra=ra_id),
                 back_url=url_for("ra.view_ra", id=ra_id),
                 submit_label="Record payment")


@receipt_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_receipt(id: str):
    """
    Correct a receipt.

    **Allowed even after a later bill has snapshotted its effect**, and that is
    a decision rather than an oversight. A payment gets mis-keyed — a
    transposed figure, the wrong bill — and a ledger that cannot be corrected is
    a ledger that is wrong forever. What must not happen is the correction
    silently reaching back into a document that has already been sent, and it
    cannot: the carried balance is stored on each bill and nothing here writes
    to one.

    Where the two then disagree, `ra.prev_balance_drift()` says so on the bill's
    own page. Surface it, never correct it (DOMAIN.md §6).
    """
    rec = (STORE.get("receipts") or {}).get(id)
    if not rec:
        return redirect(url_for("receipt.list_receipts",
                                msg="That receipt no longer exists.", type="error"))

    ra_id = str(rec.get("ra_id") or "")
    bill = (STORE.get("ra_bills") or {}).get(ra_id) or {}
    data = {
        "date": str(rec.get("date") or ""),
        "amount_raw": f'{float(rec.get("amount") or 0.0):g}',
        "mode": str(rec.get("mode") or "neft"),
        "instrument_ref": str(rec.get("instrument_ref") or ""),
        "instrument_date": str(rec.get("instrument_date") or ""),
        "notes": str(rec.get("notes") or ""),
    }
    error = ""

    later = RA.bills_snapshotting_after(str(rec.get("boq_id") or ""),
                                        int(rec.get("ra_no") or 0))
    note = ""
    if later:
        names = ", ".join(f"RA{int(b.get('ra_no') or 0)}" for b in later)
        note = (f'<div class="form-hint"><span class="fh-icon">&#9888;</span>'
                f'<span><b>{_esc(names)}</b> already stated a previous balance '
                f'that was computed while this receipt stood as it is. '
                f'Correcting it here will <b>not</b> change what those bills '
                f'printed &mdash; a document already sent is not restated. The '
                f'difference will be flagged on each of them.</span></div>')

    if request.method == "POST":
        data, error = _validate(request.form, bill)
        if not error:
            rec["date"] = data["date"]
            rec["fy"] = P.fy_of(data["date"])
            rec["amount"] = data["amount"]
            rec["mode"] = data["mode"]
            rec["instrument_ref"] = data["instrument_ref"]
            rec["instrument_date"] = data["instrument_date"]
            rec["notes"] = data["notes"]
            # `ref` is NOT reissued on an edit. It may already be on a
            # remittance advice, and a number that moves is a number nobody can
            # quote back. Same reason `ra_no` is never reassigned.
            over = _overpay_note(bill, data["amount"], exclude_id=id)
            return redirect(url_for("ra.view_ra", id=ra_id,
                                    msg=over or "Receipt updated.",
                                    type="error" if over else "success"))

    if not bill:
        return redirect(url_for("receipt.list_receipts",
                                msg="The bill this receipt was filed against is gone.",
                                type="error"))

    return _form(bill, data, error,
                 action=url_for("receipt.edit_receipt", id=id),
                 back_url=url_for("ra.view_ra", id=ra_id),
                 submit_label="Save receipt", exclude_id=id, extra_note=note)


@receipt_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_receipt(id: str):
    """
    Remove a receipt entered in error.

    **POST-only for the deletion itself.** The GET is a confirmation page, and
    that is not decoration: a link that destroys is a link a crawler, a prefetch
    or a back button will eventually fire, and none of those three ever sees a
    browser `confirm()`. ABOUT.md §7.9f is the standing rule, and it is explicit
    that the `url_map` sweep does **not** prove this — it only checks that a
    delete route accepts POST, which a route that also destroys on GET would
    pass. This route brings its own test:
    `test_get_on_receipt_delete_destroys_nothing`.

    The confirmation names every later bill that already froze a balance while
    this receipt stood, because those bills will **not** move — the operator
    should know that before confirming, not discover it afterwards.
    """
    rec = (STORE.get("receipts") or {}).get(id)
    if not rec:
        return redirect(url_for("receipt.list_receipts",
                                msg="That receipt no longer exists.", type="error"))

    ra_id = str(rec.get("ra_id") or "")

    if request.method == "POST":
        STORE["receipts"].pop(id, None)
        # Again: no RA bill is touched. A bill that stated a balance including
        # this money goes on stating it.
        back = (url_for("ra.view_ra", id=ra_id) if ra_id in (STORE.get("ra_bills") or {})
                else url_for("receipt.list_receipts"))
        sep = "&" if "?" in back else "?"
        return redirect(f"{back}{sep}msg=Receipt+{rec.get('ref')}+deleted.&type=success")

    later = RA.bills_snapshotting_after(str(rec.get("boq_id") or ""),
                                        int(rec.get("ra_no") or 0))
    later_html = ""
    if later:
        names = ", ".join(f"RA{int(b.get('ra_no') or 0)}" for b in later)
        later_html = (
            f'<br/><br/><b>{_esc(names)}</b> already printed a previous balance '
            f'worked out while this receipt stood. Those documents will '
            f'<b>not</b> change &mdash; they have been sent, and this app does '
            f'not restate a document after the fact. Each will show the '
            f'difference on its own page instead.')

    return _shell("Delete receipt", f"""
  <div class="page-top"><h1>Delete <span>{_esc(rec.get('ref'))}</span></h1></div>
  <div class="del-box">
    <h2>&#9888; This cannot be undone</h2>
    <div class="del-line">
      You are about to delete receipt <b>{_esc(rec.get('ref'))}</b> &mdash;
      <b>{_inr(rec.get('amount') or 0.0)}</b> received on
      {_esc(rec.get('date'))} against <b>RA{_esc(rec.get('ra_no'))}</b>
      ({_esc(rec.get('ra_ref'))}).<br/><br/>
      That amount goes back onto the outstanding balance of RA{_esc(rec.get('ra_no'))}.
      {later_html}
    </div>
  </div>
  <form method="POST" action="{url_for('receipt.delete_receipt', id=id)}"
        style="display:flex;gap:.7rem;">
    <button type="submit" class="btn">Delete receipt</button>
    <a href="{url_for('ra.view_ra', id=ra_id)}" class="btn btn-ghost">Keep it</a>
  </form>""")
