"""
raboth.py — RA · Supply & Installation, raised in ONE POST
===========================================================
Blueprint  : raboth_bp
Mounted at : /raboth  (registered in app.py)

CLIENT_CHANGES.md §0's **fifty-eighth** block, item 6. The client's ask from
the 28 October 2026 Yogesh meeting: *"every document from the BoQ, and RA
especially all 3 types — Supply, Installation, and then Supply and
Installation both."* The first two were one click already; **Both** was not —
it meant raising a supply bill, issuing it, raising an installation bill,
issuing that, and only then opening `/merged/create`. Five steps and three
screens for one job.

What this does, and the order it does it in
--------------------------------------------
One form, two claim grids, one POST. On that POST:

    1. VALIDATE BOTH LEGS, before writing anything at all.
    2. write the supply leg and ISSUE it
    3. write the installation leg and ISSUE it
    4. `merged_ra.create()` over the two

⚠ **ATOMIC, AND STEP 1 IS WHAT MAKES IT SO.** *"If either leg fails the
over-claim guard, nothing is written and the refusal names the line"* is the
block's wording. Both legs are run through `ra._validate()` — the same
function, the same `overclaims()` — **before the first record exists**, which
is sound because the two legs are separate keys in `approved_by_line()` and
`claimed_by_line()` and neither can affect the other's ceiling. Steps 2 to 4
cannot then fail on the guard. If one of them fails for any other reason
(a merge refusal, a missing schedule) the records written so far are
**rolled back** — see `_rollback()`.

⚠ **THE LEGS CARRY NO TAX INVOICE NUMBER OF THEIR OWN.**
`ra.build_bill()` mints one into a blank `tax_invoice_ref`; this route passes
`ra.NO_TAX_INVOICE` so that neither leg mints anything. **Only the merged RA
carries a statutory serial**, from `merged_ra`'s own `MI` counter. Three
serials over one billing is precisely what Rule 46 exists to prevent and what
GSTR-1 would report as two phantom invoices. ⚠ A leg raised this way therefore
**cannot print as a tax invoice alone** — `ra.print_ra()` prints the document
it always printed, and that document now has no invoice number on it, which is
the truth about it.

⚠ **THE GUARD, THE `ra_no` SERIES AND THE LEG MODEL ARE UNTOUCHED.** Each leg
takes the next `ra_no` on its chain exactly as a hand-raised bill does, keeps
its own `ref`, its own status and its own claim rows, and is a perfectly
ordinary RA bill in every register and every total. CC-2 C3's invariant holds
by construction: the merged record still holds no claims of its own and its
totals are still the sum of the two legs' stored totals.

⚠ **The legs are ISSUED, and they have to be.** `merged_ra.can_merge()`
refuses a draft — *"a merge raises a tax invoice, and a draft is not a claim
that has gone anywhere"* — and that rule is not relaxed for this path. The
form says so above the button: this one action issues both bills.

Cancelling
----------
⚠ **Cancelling the merged document cancels all three**, which is this route's
own rule and not `merged_ra.py`'s. `/merged/cancel` on its own releases the
legs and leaves them standing as two independent bills — correct for a merge
somebody assembled from two bills that already existed, and wrong for three
documents raised as one. `cancel_set()` below is what the register and
`/merged/cancel` call for a set raised here; a set is recognised by
`BOTH_KEY`, stamped on all three at create.

Import direction
----------------
    raboth.py ──► ra.py          the builder, the guard, the issue
    raboth.py ──► merged_ra.py   the merge
    raboth.py ──► boq.py         the schedule and the line grid
    raboth.py ──► approval, auth, chrome, pipeline, store, branding, quotation

Nothing imports it back — `ra.py` and `merged_ra.py` must not, or the two
one-way arrows this module depends on become cycles.
"""

import json
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import approval
import auth
import boq as BQ
import branding as B
import merged_ra as MRA
import pipeline as P
import ra as RA
import roundoff as RO
from chrome import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES
from store import STORE

raboth_bp = Blueprint("raboth", __name__, url_prefix="/raboth")

# ⚠ **The mark that makes three documents one set lives in `ra.py`**, not
#   here: it is a field on an RA bill, and `ra.py` and `merged_ra.py` both
#   read it while neither may import this module. Re-exported under the old
#   name so this file reads as it did.
BOTH_KEY = RA.RAISED_AS_BOTH

LEGS = ("supply", "installation")


def _now() -> str:
    return _date.today().isoformat()


set_of = RA.set_of
legs_of_set = RA.legs_of_set


def merged_of_set(set_id: str):
    """The merged document of one set, or None."""
    sid = str(set_id or "")
    if not sid:
        return None
    for m in (MRA.records() or {}).values():
        if set_of(m) == sid:
            return m
    return None


def cancel_set(merged: dict, reason: str) -> tuple:
    """
    `(n_cancelled, error)` — withdraw a set raised here: **the merged document
    AND both legs**, and release whatever they consumed.

    ⚠ **This is the difference between a set and an assembled merge.**
    `/merged/cancel` alone releases the two legs and leaves them standing as
    independent bills, which is right for two bills somebody merged after the
    fact and wrong for three documents raised as one action: the legs would
    go on claiming quantity against the schedule with no invoice over them,
    and the next claim would be refused for an over-claim nobody made.

    ⚠ **The merged record is cancelled FIRST.** `ra.can_cancel()` refuses a
    bill inside a **live** merged document (CC-2 C3's invariant, enforced in
    `ra.py`), so the legs cannot be withdrawn until it is no longer live. The
    order is the invariant working, not a way round it.

    ⚠ **A leg with receipts against it stops this**, and nothing is written.
    `ra.can_cancel()` refuses it — cancelling would state that nothing is owed
    on a document money was paid against — and that refusal is not overridden
    here. The caller is told which bill and why.
    """
    if not merged:
        return 0, "That merged document no longer exists."
    sid = set_of(merged)
    if not sid:
        return 0, ("That merged document was assembled from two bills that "
                   "already existed, so cancelling it releases them rather "
                   "than withdrawing them. Use the merged document's own "
                   "Cancel.")
    legs = legs_of_set(sid)

    # ⚠ Checked on EVERY leg before anything is written — the same
    #   validate-then-write shape the create path uses, for the same reason.
    for rid, b in legs:
        if RA.is_cancelled(b):
            continue
        allowed, why = RA.can_cancel(b)
        # The live merge is this one and is about to go; that refusal is
        # expected and is not a blocker.
        if not allowed and "merged document" not in why:
            return 0, (f"RA{int(b.get('ra_no') or 0)} cannot be cancelled, so "
                       f"this set cannot be withdrawn as one. {why}")

    MRA.apply_cancel(merged, reason)
    n = 1
    for rid, b in legs:
        if RA.is_cancelled(b):
            continue
        RA.apply_cancel(b, f"Raised as one Supply & Installation bill with "
                           f"{merged.get('tax_invoice_ref')}, which was "
                           f"cancelled. {reason}".strip())
        n += 1
    return n, ""


def _rollback(written_ids: list) -> None:
    """
    Undo a part-written set. ⚠ **`STORE` is one dict in one process and there
    is no transaction** — `db.py` snapshots and diffs after the request — so
    "atomic" here means *nothing half-written survives the request*, and this
    is what makes that true when a step after the first write refuses.

    ⚠ **The numbers these records spent are NOT reused.** `next_ra_no()` scans
    for the maximum and adds one, so removing the records frees the numbers
    again; a statutory serial would not be freed, which is exactly why no leg
    mints one (see the module docstring).
    """
    for rid in written_ids:
        (STORE.get("ra_bills") or {}).pop(rid, None)


def create_set(boq: dict, supply_claims: list, install_claims: list,
               date_val: str, notes_val: str = "", round_on: bool = True,
               **fields) -> tuple:
    """
    `(merged, error)` — write both legs and the merged document, atomically.

    ⚠ **The caller has already validated both claim sets.** This function does
    the writing and the ordering; it does not second-guess the guard, because
    a second place deciding what an over-claim is would be a second guard.
    """
    sid = str(uuid.uuid4())
    written, bills = [], {}
    try:
        for leg, claims in (("supply", supply_claims),
                            ("installation", install_claims)):
            rid = RA.new_id()
            # ⚠ `NO_TAX_INVOICE` — neither leg mints a statutory serial. Only
            #   the merged document carries one. See the module docstring.
            # ⚠ `round_on=False` on EACH LEG (31 Oct 2026, Part A): a set is
            #   ONE billing and is rounded ONCE, on the merged tax invoice's
            #   total, never per leg. A leg raised here never prints as a tax
            #   invoice (it carries no serial), so its exact two-decimal total
            #   is the honest one, and two legs each rounded would put up to
            #   two rupees of round-off on one invoice.
            rec = RA.build_bill(rid, boq, leg, claims, date_val, notes_val,
                                tax_invoice_ref=RA.NO_TAX_INVOICE,
                                round_on=False, **fields)
            rec[BOTH_KEY] = sid
            STORE.setdefault("ra_bills", {})[rid] = rec
            approval.stamp_creator(rec)
            # Issued immediately: `merged_ra.can_merge()` refuses a draft and
            # that rule is not relaxed here. The form says so above the button.
            RA.apply_issue(rec, date_val)
            written.append(rid)
            bills[leg] = rec

        merged, err = MRA.create(
            bills["supply"], bills["installation"],
            notes="Raised as one Supply & Installation bill.")
        if err:
            _rollback(written)
            return None, err
        merged[BOTH_KEY] = sid
        # ⚠ ROUNDED ONCE, here, on the merged total (31 Oct 2026, Part A) —
        #   the set's "Round off to nearest rupee" tick. `merged_ra.create()`
        #   summed the two legs' exact totals (its rule, untouched); the one
        #   rounding is applied on top and stored as the merged document's
        #   own `rounding_off`, so `grand_total == sum of the legs' totals +
        #   rounding_off` to the paisa. A merge ASSEMBLED by hand from two
        #   bills that already existed is not touched — it carries no tick.
        legs_total = round(float(merged.get("grand_total") or 0.0), 2)
        grand, ro = RO.apply(legs_total, round_on)
        merged["grand_total"] = grand
        merged["rounding_off"] = RO.paise(float(merged.get("rounding_off") or 0.0) + ro)
        merged[RO.FIELD] = bool(round_on)
        return merged, ""
    except Exception:
        # ⚠ A refusal is returned; an unexpected failure must not leave two
        #   issued bills and no invoice over them.
        _rollback(written)
        raise


# =============================================================================
# THE PAGE
# =============================================================================

def _grid(boq: dict, leg: str, prev: dict, entered: dict) -> str:
    """
    One leg's claim grid — **this page's own, and deliberately NOT
    `ra._entry_form()`'s.**

    ⚠ **IT CARRIES NO JAVASCRIPT.** `/ra/create`'s grid is driven by
    `ra._RA_JS`, 136 lines keyed on element ids `q_<line_id>` / `r_<line_id>`
    and one hidden `ra_json`. **Two of those grids on one page collide on
    every id**, and making that script prefix-aware would rewrite a shared
    asset that `/ra/create` and `/ra/edit` both render — to add a second leg to
    a third page. So this page posts plain fields and the server reads them,
    which is what the rest of this application does anyway.

    ⚠ **WHAT IS LOST, AND WHAT IS NOT.** The live running total and the
    over-claim warning *as you type* are not here. **The guard is not
    weakened by one character**: `ra._validate()` → `ra.overclaims()` runs on
    the POST exactly as it does for a single-leg bill, and refuses before
    anything is written. What the operator loses is the preview, and what
    stands in its place is on the page: the **approved**, **claimed to date**
    and **balance** columns per line, and `ra.cap_note_html()` above the grid
    saying which ceiling applies. Raise the legs separately at `/ra/create` for
    the live grid.

    Fields are `{leg}_qty_{line_id}` and `{leg}_rate_{line_id}`, so the two
    legs cannot read each other's boxes.
    """
    approved = RA.approved_by_line(str(boq.get("id") or ""))
    rates = RA.approved_rates(str(boq.get("id") or ""))
    rows = ""
    for li in boq.get("line_items") or []:
        if not isinstance(li, dict) or li.get("is_header"):
            continue
        lid = BQ._line_id(li.get("line_id"))
        key = (lid, leg)
        if not lid or key not in approved:
            continue
        rate = rates.get(key)
        if rate is None:
            # A line with no rate on THIS leg cannot be claimed on it —
            # `clean_claims()` refuses it, so it is not offered. The other
            # leg's grid may still carry it.
            continue
        app = float(approved[key] or 0.0)
        done = float(prev.get(key, 0.0))
        bal = app - done
        was = (entered.get(lid) or {})
        rows += f"""
          <tr>
            <td>{P.esc(li.get("item_no"))}</td>
            <td>{P.esc(li.get("description"))}</td>
            <td>{P.esc(li.get("unit"))}</td>
            <td class="td-num">{BQ._fmt_qty(app)}</td>
            <td class="td-num">{BQ._fmt_qty(done)}</td>
            <td class="td-num">{BQ._fmt_qty(bal)}</td>
            <td class="td-num"><input type="text" inputmode="decimal"
                 name="{leg}_qty_{P.esc(lid)}" value="{P.esc(was.get("qty") or "")}"
                 style="width:6.5rem;text-align:right;"/></td>
            <td class="td-num"><input type="text" inputmode="decimal"
                 name="{leg}_rate_{P.esc(lid)}"
                 value="{P.esc(was.get("rate") if was.get("rate") is not None else rate)}"
                 style="width:6.5rem;text-align:right;"/></td>
          </tr>"""
    if not rows:
        return (f'<p class="form-hint">No line on this schedule carries a '
                f'{P.esc(leg)} rate, so there is nothing to claim on this '
                f'leg. The other leg can still be claimed.</p>')
    return f"""
      <div class="cl-wrap"><table class="claims">
        <thead><tr>
          <th>Item</th><th>Description</th><th>Unit</th>
          <th style="text-align:right;">Approved</th>
          <th style="text-align:right;">Claimed to date</th>
          <th style="text-align:right;">Balance</th>
          <th style="text-align:right;">This claim</th>
          <th style="text-align:right;">Rate</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table></div>"""


def _payload(form, leg: str) -> str:
    """
    The posted boxes, as the **`ra_json` string `ra._validate()` already
    takes** — so this page runs through the one validation path rather than a
    second one. A blank quantity is left out entirely; `clean_claims()` and
    then `overclaims()` judge the rest, unchanged.
    """
    lines = []
    for field, raw in form.items():
        if not field.startswith(f"{leg}_qty_"):
            continue
        lid = field[len(f"{leg}_qty_"):]
        qty = str(raw or "").strip()
        if not qty:
            continue
        lines.append({"line_id": lid, "qty": qty,
                      "rate": str(form.get(f"{leg}_rate_{lid}") or "").strip()})
    return json.dumps({"lines": lines})


@raboth_bp.route("/create", methods=["GET", "POST"])
def create_both():
    """
    *RA · Supply & Installation* — both legs and the merged tax invoice, in one
    POST. See the module docstring for every rule.
    """
    BQ.ensure_demo_boq()
    boq_id = (request.args.get("boq") or request.form.get("boq") or "").strip()
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="That schedule no longer exists.",
                                type="error"))

    # ⚠ The tip only, which is `/boq/view`'s own rule for the whole raise bar:
    #   a claim is measured against a specific revision and a superseded one
    #   is not the approved schedule any more.
    tip = RA.latest_revision(boq_id) or boq_id
    if tip != boq_id:
        return redirect(url_for("boq.view_boq", id=boq_id, type="error",
                                msg=("That schedule has been superseded. Raise "
                                     "the claim on its latest revision.")))

    today = _date.today().isoformat()
    error, entered = "", {"supply": {}, "installation": {}}
    date_val, notes_val = today, ""

    if request.method == "POST":
        date_val = (request.form.get("date") or today).strip()
        notes_val = (request.form.get("notes") or "").strip()

        # ── STEP 1: VALIDATE BOTH LEGS BEFORE WRITING ANYTHING ─────────────
        claims = {}
        for leg in LEGS:
            prev = RA.claimed_by_line(boq_id)
            got, raw_lines, err = RA._validate(
                _payload(request.form, leg), boq, leg, prev)
            entered[leg] = RA._posted(raw_lines)
            if err and not error:
                # ⚠ **BOTH LEGS MUST CLAIM SOMETHING, and that falls out of
                #   `clean_claims()` rather than being a rule invented here**:
                #   an RA bill with no claim rows is refused on every path in
                #   this application. A merged document over an empty leg
                #   would be a bill claiming nothing on one side, and CC-2
                #   C3's model is two bills STACKED.
                #
                # ⚠ **So the message names the right document rather than
                #   just saying no.** The client asked for three RA types;
                #   this is the third, not a replacement for the first two,
                #   and a claim on one side only is what those are for.
                error = (f"{leg.title()} leg: {err} Nothing has been saved "
                         f"— this one action raises both bills or neither. "
                         f"To claim on one side only, use RA &middot; Supply "
                         f"or RA &middot; Installation on the schedule "
                         f"instead.")
            claims[leg] = got

        if not error:
            merged, err = create_set(
                boq, claims["supply"], claims["installation"],
                date_val, notes_val,
                round_on=RO.form_choice(request.form, legacy=True),
                po_ref=(request.form.get("po_ref") or "").strip(),
                po_date=(request.form.get("po_date") or "").strip(),
                tax_type=(request.form.get("tax_type") or "cgst_sgst").strip(),
                cgst_rate=float(BQ._num(request.form.get("cgst_rate"), 9.0)),
                sgst_rate=float(BQ._num(request.form.get("sgst_rate"), 9.0)),
                igst_rate=float(BQ._num(request.form.get("igst_rate"), 18.0)))
            if err:
                error = err
            else:
                return redirect(url_for(
                    "merged_ra.view_merged", id=merged["id"], type="success",
                    msg=(f"Supply and installation raised and merged onto tax "
                         f"invoice {merged.get('tax_invoice_ref')}. Both bills "
                         f"are issued; neither carries an invoice number of "
                         f"its own.")))

    prev = RA.claimed_by_line(boq_id)
    return _form(boq, prev, entered, error, date_val, notes_val)


def _form(boq, prev, entered, error, date_val, notes_val) -> str:
    boq_id = str(boq.get("id") or "")
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("RA · Supply & Installation")}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{BQ.BOQ_STYLES}{RA.RA_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>RA &middot; <span>Supply &amp; Installation</span></h1>
    <a href="{url_for('boq.view_boq', id=boq_id)}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {RA._alert(error)}
  <div class="form-hint" style="margin:.6rem 0;">
    &#9432;&nbsp;<b>One action, three documents.</b> This raises the supply
    bill and the installation bill, <b>issues both</b>, and puts one tax
    invoice over them. ⚠ <b>Neither bill carries a tax invoice number of its
    own</b> &mdash; only the merged document does, so one billing spends one
    statutory serial. If either leg breaks the over-claim guard,
    <b>nothing is saved</b>.
  </div>
  {RA.cap_note_html(boq_id, "supply")}
  {RA.cap_note_html(boq_id, "installation")}
  <form method="POST" action="{url_for('raboth.create_both', boq=boq_id)}">
    <input type="hidden" name="boq" value="{P.esc(boq_id)}"/>
    <div class="form-section">
      <div class="section-title">&#128197; Bill</div>
      <div class="form-grid">
        <div class="form-group"><label for="date">Date</label>
          <input type="date" id="date" name="date" value="{P.esc(date_val)}"/></div>
        <div class="form-group span2"><label for="notes">Notes</label>
          <input type="text" id="notes" name="notes" value="{P.esc(notes_val)}"/></div>
      </div>
      {RO.checkbox_html(RO.form_choice(request.form, legacy=True) if request.method == "POST" else True,
                        "Once, on the merged tax invoice's total &mdash; never on each leg.")}
    </div>
    <div class="form-section">
      <div class="section-title">&#128230; Supply</div>
      {_grid(boq, "supply", prev, entered.get("supply") or {})}
    </div>
    <div class="form-section">
      <div class="section-title">&#128295; Installation</div>
      {_grid(boq, "installation", prev, entered.get("installation") or {})}
    </div>
    <div class="form-actions">
      <button type="submit" class="btn">Raise both and merge</button>
      <a href="{url_for('boq.view_boq', id=boq_id)}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
</main>
</body></html>"""
