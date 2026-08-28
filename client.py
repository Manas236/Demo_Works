"""
client.py — Client-wise segregation, and the minimal party edit
===============================================================
Blueprint  : client_bp
Mounted at : /client  (registered in app.py)

Routes
------
  GET       /client/                — the ledger, one panel per client
  GET,POST  /client/edit-party/<id> — the party block of one BOQ, and nothing else

CLIENT_CHANGES.md item 2. A per-client ledger grouping every BOQ by the party
it is billed to, with total schedule value, total issued, total received and
what is outstanding across all of it.

Two things it is not
--------------------
**It is not a document.** It answers *where does this client stand today*, so
every figure is computed live from `STORE` — outstanding comes from
`ra.outstanding_of()`, not from any bill's frozen `prev_balance`. That is the
one place the frozen figure is the wrong source, and it is the opposite call
from `/ra/print`, which answers *what did we state when we sent it*.

**It is not a customer master.** There is no `customer_id` anywhere in this
app: the address picker writes plain strings onto a BOQ and the grouping key is
therefore normalised text (`pipeline.norm_name`). Two spellings of one party are
two rows, which is exactly why the near-duplicate band exists — it reports the
ambiguity rather than merging it (DOMAIN.md §6).

Import direction
----------------
    client.py ──► boq.py       BOQ_STYLES, boq_identity, _to_block
    client.py ──► ra.py        bills_of / party_lock_bills / outstanding_of
    client.py ──► receipt.py   receipts_of_boq
    client.py ──► quotation.py QUOTATION_STYLES + _inr — the form widgets
    client.py ──► dashboard.py BASE_STYLES / _nav
    client.py ──► pipeline.py  esc / norm_name
    client.py ──► store

Nothing imports this module. It is the end of the chain: `boq.py`, `ra.py` and
`receipt.py` all sit upstream and none of them may import it back.
"""

import re

from flask import Blueprint, redirect, request, url_for

import branding as B
import pipeline as P
from store import STORE

from dashboard import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES, _inr
from boq import BOQ_STYLES, boq_identity, _to_block
from ra import (bills_of, is_issued, is_cancelled, is_adjustment,
                outstanding_of, party_lock_bills, PARTY_FIELDS)
from receipt import receipts_of_boq

client_bp = Blueprint("client", __name__, url_prefix="/client")


# =============================================================================
# LOGIC
# =============================================================================

def _base_name(normed: str) -> str:
    """
    A normalised name with its punctuation and spacing taken out.

    Used **only** to spot near-duplicates for the warning band. It is
    deliberately not the grouping key: collapsing `Prudent Teqtis Pvt Ltd` and
    `Prudent Teqtis Pvt. Ltd.` into one row would be this system deciding they
    are the same party, and it does not know that. DOMAIN.md §6 — surface it,
    name it, never silently correct it.
    """
    return re.sub(r"[.,\-'\s]", "", normed)


def _client_groups():
    """
    Every BOQ grouped by `norm_name(account_name)`.

    Returns `(groups, duplicates)`.

    ⚠ **`total_issued` counts ISSUED bills only** — a draft has not been sent
      and a cancelled one has been withdrawn, so neither is money anybody owes.
      Cancelled bills are excluded from every total in this app by design
      (ABOUT.md §3, "The lifecycle") and this page is not the place to make an
      exception. Getting it wrong would put a withdrawn claim into a figure
      somebody is about to chase a customer for.
    """
    groups = {}
    for boq in (STORE.get("boqs") or {}).values():
        raw_name = (boq.get("account_name") or "").strip()
        if not raw_name:
            continue

        normed = P.norm_name(raw_name)
        grp = groups.setdefault(normed, {
            "display_names": set(), "boqs": [],
            "total_boq": 0.0, "total_issued": 0.0,
            "total_received": 0.0, "total_written_off": 0.0,
            "total_adjusted": 0.0, "total_outstanding": 0.0,
        })

        grp["display_names"].add(raw_name)
        grp["boqs"].append(boq)
        grp["total_boq"] += float(boq.get("subtotal") or 0.0)

        boq_id = boq.get("id")
        issued_val = sum(float(b.get("grand_total") or 0.0)
                         for _rid, b in bills_of(boq_id) if is_issued(b))
        # ── Received is BANK MOVEMENTS ONLY, from 28 August 2026 ───────
        #
        # `received_val` used to sum every receipt regardless of mode, so an
        # `adjustment`-mode receipt — the only workaround available before A5 —
        # made Outstanding right by making **Received** wrong. That was
        # PROGRESS.md §6-D's open half, and it is closed here.
        #
        # **The count came before the decision.** The live database was queried
        # on 28 August 2026: **zero** adjustment-mode receipts, one receipt in
        # total, mode `neft`. So no figure anybody has been shown moves, which
        # is what made this safe to decide rather than to keep reporting.
        #
        # ⚠ **An adjustment is excluded from Received and is NOT dropped.** It
        #   is subtracted from Outstanding under its own name below. `ra.py`'s
        #   note on `RECEIPT_MODES` is explicit that an adjustment is a credit
        #   note, a debit note or a contra settled against the bill and that
        #   *"the money genuinely stops being outstanding"* — so removing it
        #   from Outstanding as well would put a settled balance back on the
        #   books and state a debt that is not owed. Three sums, three facts,
        #   which is the same call A5 took when it made `write_off` a separate
        #   field rather than folding it into `amount`.
        received_val = sum(float(r.get("amount") or 0.0)
                           for _rid, r in receipts_of_boq(boq_id)
                           if not is_adjustment(r))
        # A5's write-off, and a **separate** sum from `received_val` on purpose.
        # Money that arrived and money the contractor allowed short are two
        # different facts: the first is a bank movement and belongs in Received,
        # the second reduces what is owed and does not.
        written_off_val = sum(float(r.get("write_off") or 0.0)
                              for _rid, r in receipts_of_boq(boq_id))
        # Settled against the bill without a bank movement. Reduces Outstanding,
        # never Received.
        adjusted_val = sum(float(r.get("amount") or 0.0)
                           for _rid, r in receipts_of_boq(boq_id)
                           if is_adjustment(r))

        grp["total_issued"] += issued_val
        grp["total_received"] += received_val
        grp["total_written_off"] += written_off_val
        grp["total_adjusted"] += adjusted_val
        # Not clamped at zero. An overpayment is ordinary — a lump sum settling
        # two bills at once — and it carries forward as a credit, exactly as
        # `ra.outstanding_of()` lets it.
        # Four terms, and the page renders every one of them that is
        # non-zero, so a reader can do this subtraction by eye. The figure is
        # **identical** to what three terms produced before 28 August 2026 —
        # `received_val` lost exactly the adjustments that `adjusted_val`
        # gained, so the total is invariant by construction, not by luck. What
        # changed is which column each rupee is shown in.
        grp["total_outstanding"] += (issued_val - received_val
                                     - written_off_val - adjusted_val)

    base_map = {}
    for normed in groups:
        base_map.setdefault(_base_name(normed), []).append(normed)
    duplicates = [(base, sorted(norms)) for base, norms in sorted(base_map.items())
                  if len(norms) > 1]

    for grp in groups.values():
        grp["boqs"].sort(key=lambda b: (str(b.get("date") or ""),
                                        str(b.get("ref") or "")), reverse=True)

    return groups, duplicates


# ⚠ **CLIENT_CHANGES-2.md A4 requires this line and names the reason.**
#
# *"Until the formal credit note exists, Total Outstanding is only as correct as
# the write-off field makes it. This limitation is stated in MG/SF/2026-02 §6
# deliberately — do not quietly present the figure as authoritative."*
#
# A5's write-off now exists, so the figure is better than it was. It is still
# not authoritative, for two reasons worth keeping apart:
#
#   1. There is **no formal credit note** (explicitly out of Phase 3A), so an
#      allowance that legally needs one is recorded here as an internal
#      write-off and nowhere else.
#   2. ~~`received_val` above still sums receipts regardless of mode.~~
#      **Closed 28 August 2026.** Received is bank movements only; an
#      `adjustment` is shown under its own heading and still reduces
#      Outstanding. PROGRESS.md §6-D is closed in both halves.
#
# Stated once, under the figures, rather than in a tooltip nobody opens.
OUTSTANDING_CAVEAT = (
    '<div class="cl-caveat">Outstanding is an <b>internal</b> figure. It is net '
    'of any write-off and of any adjustment recorded against a receipt, and '
    'there is no credit note behind a write-off &mdash; the bill still says '
    'what it says. <b>Received</b> is money that moved through a bank.</div>')


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


# =============================================================================
# CSS
# =============================================================================
#
# `BASE_STYLES` first, then `QUOTATION_STYLES` for the form furniture
# (`.form-section`, `.section-title`, `.fg2`, `.form-group`, `.page-top`,
# `.alert`) — the same stack `settings.py` and `receipt.py` load, so these pages
# are the same pages. Only the ledger panel is new.
#
# ⚠ `BOQ_STYLES` is deliberately NOT loaded. It is the landscape print sheet and
#   it redefines `.boq-table`, which an earlier version of this file then
#   overrode with its own screen table of the same name — two stylesheets
#   fighting over one class on a page that prints nothing.

CLIENT_STYLES = """
<style>
  .cl-group { border:1px solid var(--border); border-radius:10px;
              overflow:hidden; margin-bottom:1.5rem; background:#fff; }
  .cl-head  { display:flex; justify-content:space-between; align-items:baseline;
              gap:1rem; flex-wrap:wrap; padding:.85rem 1.1rem;
              background:var(--surface); border-bottom:1px solid var(--border); }
  .cl-name  { margin:0; font-size:1.05rem; font-weight:700; color:var(--navy); }
  .cl-sub   { font-size:.78rem; color:var(--muted); }

  .cl-stats { display:flex; gap:2rem; flex-wrap:wrap; padding:.9rem 1.1rem;
              border-bottom:1px solid var(--border); }
  /* CC-2 A4's caveat. Quiet, but under the figure rather than in a tooltip. */
  .cl-caveat { padding:.5rem 1.1rem .7rem; font-size:.76rem; line-height:1.5;
               color:var(--muted); border-bottom:1px solid var(--border); }
  .cl-stat  { display:flex; flex-direction:column; gap:.2rem; }
  .cl-lbl   { font-size:.68rem; text-transform:uppercase; letter-spacing:.06em;
              color:var(--muted); font-weight:700; }
  .cl-val   { font-size:1.05rem; font-weight:700; color:var(--navy);
              font-variant-numeric:tabular-nums; }
  .cl-val.credit { color:#0CA30C; }

  .cl-table { width:100%; border-collapse:collapse; font-size:.85rem; }
  .cl-table th, .cl-table td { padding:.5rem 1.1rem; text-align:left;
              border-bottom:1px solid var(--border); }
  .cl-table th { font-size:.68rem; text-transform:uppercase; letter-spacing:.06em;
              color:var(--muted); font-weight:700; background:var(--surface); }
  .cl-table td.num, .cl-table th.num { text-align:right;
              font-variant-numeric:tabular-nums; }
  .cl-table tr:last-child td { border-bottom:none; }

  /* Amber, not red, per the app's severity rule: two spellings of one name is
     incomplete-but-working, and billing is unaffected either way. */
  .cl-dup { background:#FFF4D6; color:#8A5A00; border:1px solid #E0A93B;
            border-radius:var(--radius); padding:.85rem 1.1rem;
            margin-bottom:1.4rem; font-size:.85rem; line-height:1.6; }
  .cl-dup b { color:#7A4E00; }
  .cl-dup ul { margin:.4rem 0 0; padding-left:1.3rem; }

  /* The lock band on a frozen party form. */
  .cl-lock { background:#FFF4D6; color:#8A5A00; border:1px solid #E0A93B;
             border-radius:var(--radius); padding:.85rem 1.1rem;
             margin-bottom:1.4rem; font-size:.85rem; line-height:1.6; }
  .cl-lock b { color:#7A4E00; }
  .cl-lock .cl-bills { margin-top:.4rem; display:flex; gap:.4rem;
             flex-wrap:wrap; }
  .cl-lock .cl-bill { background:#fff; border:1px solid #E0A93B;
             border-radius:99px; padding:1px 9px; font-size:.76rem;
             font-weight:700; text-decoration:none; color:#7A4E00; }
</style>
"""


# =============================================================================
# ROUTES
# =============================================================================

@client_bp.route("/")
def list_clients():
    groups, duplicates = _client_groups()

    dup_html = ""
    if duplicates:
        items = ""
        for _base, norms in duplicates:
            names = sorted({n for norm in norms
                            for n in groups[norm]["display_names"]})
            items += f'<li>{" &nbsp;/&nbsp; ".join(P.esc(n) for n in names)}</li>'
        dup_html = f"""
      <div class="cl-dup">
        <b>These names may be the same party, typed differently.</b>
        They are listed as separate clients below and their totals are not
        added together. Nothing is merged automatically &mdash; a name is the
        only key this app has, and deciding two of them are one party is a
        judgement it cannot make. Correct the spelling on the schedule itself
        if they should be one, using <b>Edit party</b> on the row.
        <ul>{items}</ul>
      </div>"""

    body = ""
    for normed in sorted(groups):
        grp = groups[normed]
        names = " &nbsp;/&nbsp; ".join(P.esc(n) for n in sorted(grp["display_names"]))
        out = grp["total_outstanding"]
        out_cls = " credit" if out < 0 else ""
        out_note = " in credit" if out < 0 else ""

        # Shown only where there is one. Outstanding now drops by every A5
        # write-off, and a register reading Issued 1,00,000 / Received 90,000 /
        # Outstanding 0 with nothing between them explains nothing — it looks
        # like an arithmetic error rather than an allowance somebody agreed to.
        # A client with no write-offs sees the three figures it always did.
        written_off_stat = ""
        if grp["total_written_off"]:
            written_off_stat = (
                f"""
          <div class="cl-stat"><span class="cl-lbl">Written off</span>
            <span class="cl-val">{_inr(grp['total_written_off'])}</span></div>""")

        # Same rule, same reason: shown only where there is one. A client whose
        # money all arrived through a bank sees exactly the three figures it saw
        # before 28 August 2026, and the byte-for-byte identical page.
        adjusted_stat = ""
        if grp["total_adjusted"]:
            adjusted_stat = (
                f"""
          <div class="cl-stat"><span class="cl-lbl">Adjusted</span>
            <span class="cl-val">{_inr(grp['total_adjusted'])}</span></div>""")

        rows = ""
        for boq in grp["boqs"]:
            bid = boq.get("id")
            locked = bool(party_lock_bills(bid))
            edit = (f'<a class="btn btn-ghost" '
                    f'href="{url_for("client.edit_party", id=bid)}">'
                    f'{"View party" if locked else "Edit party"}</a>')
            rows += f"""
            <tr>
              <td><a href="{url_for('boq.view_boq', id=bid)}"><b>{P.esc(boq.get('ref'))}</b></a></td>
              <td>{P.esc(boq.get('date'))}</td>
              <td>{P.esc(boq.get('project_name')) or '&mdash;'}</td>
              <td>{P.esc(boq.get('site_location')) or '&mdash;'}</td>
              <td class="num">{_inr(boq.get('subtotal') or 0.0)}</td>
              <td style="text-align:right;">{edit}</td>
            </tr>"""

        n = len(grp["boqs"])
        body += f"""
      <div class="cl-group">
        <div class="cl-head">
          <h2 class="cl-name">{names}</h2>
          <span class="cl-sub">{n} schedule{"" if n == 1 else "s"}</span>
        </div>
        <div class="cl-stats">
          <div class="cl-stat"><span class="cl-lbl">Schedule value</span>
            <span class="cl-val">{_inr(grp['total_boq'])}</span></div>
          <div class="cl-stat"><span class="cl-lbl">Issued (RA)</span>
            <span class="cl-val">{_inr(grp['total_issued'])}</span></div>
          <div class="cl-stat"><span class="cl-lbl">Received</span>
            <span class="cl-val">{_inr(grp['total_received'])}</span></div>{adjusted_stat}{written_off_stat}
          <div class="cl-stat"><span class="cl-lbl">Outstanding{out_note}</span>
            <span class="cl-val{out_cls}">{_inr(abs(out))}</span></div>
        </div>
        {OUTSTANDING_CAVEAT}
        <table class="cl-table">
          <thead><tr>
            <th>BOQ</th><th>Date</th><th>Project</th><th>Site</th>
            <th class="num">Schedule value</th><th></th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>"""

    if not groups:
        body = ('<div class="cl-group"><div class="cl-stats" '
                'style="color:var(--muted);border:none;">No bills of quantities '
                'carry a customer name yet.</div></div>')

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Client Register")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{CLIENT_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Client <span>Register</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">Bills of Quantities</a>
      <a href="{url_for('receipt.list_receipts')}" class="btn btn-ghost">Receipts</a>
    </div>
  </div>

  {_flash()}

  <p style="font-size:.85rem;color:var(--muted);margin-bottom:1.2rem;">
    Every schedule grouped by the party it is billed to. <b>Issued</b> counts
    RA bills that have actually gone out &mdash; a draft has not been sent and a
    cancelled one has been withdrawn, so neither is here. Every figure is
    computed now rather than read off a document: this page answers where the
    client stands today.
  </p>

  {dup_html}
  {body}

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · client register</p></footer>
</main>
</body></html>""")


@client_bp.route("/edit-party/<id>", methods=["GET", "POST"])
def edit_party(id):
    """
    The minimal BOQ edit route — **party fields only**, and it must not become
    the general BOQ edit (CLIENT_CHANGES.md item 2). It touches the customer
    block and nothing else: no line item, no rate, no quantity, no project
    name, no section, no reference. There is a test for those absences.

    #### The lock, and what a GET does about it

    An RA bill snapshots the party block at save, so editing the schedule
    afterwards produces a register disagreeing with documents already issued.
    **Draft and issued bills freeze these fields** — `ra.party_lock_bills()`,
    which is where the rule is stated, so this page and the guard cannot say
    different things (`can_receipt()`'s arrangement).

    ⚠ **A GET renders the form READ-ONLY. It does not bounce.** It used to
      redirect on both methods, so a locked BOQ's customer details could not
      even be *looked at* — the operator was sent back to the schedule with an
      error for opening a page. Refusing a change and refusing to show what
      would change are different acts, and only the first is the rule. Every
      control renders `disabled`, the blocking bills are named and linked, and
      the POST is what refuses.

    ⚠ **A CANCELLED bill alone does not lock.** That narrows a rule set on
      10 August 2026 — see `ra.party_lock_bills()` for why, and for what did
      not change: every bill keeps its own frozen snapshot, and `/ra/view`
      raises an amber band where the two have come apart.
    """
    boq = (STORE.get("boqs") or {}).get(id)
    if not boq:
        return redirect(url_for("client.list_clients",
                                msg="That schedule no longer exists.",
                                type="error"))

    locking = party_lock_bills(id)
    locked = bool(locking)
    error = ""

    if request.method == "POST":
        if locked:
            refs = ", ".join(str(b.get("ref") or "") for _rid, b in locking)
            return redirect(url_for(
                "boq.view_boq", id=id, type="error",
                msg=(f"Party fields cannot be edited because RA bills already "
                     f"exist against this schedule: {refs}")))

        form = request.form
        if not (form.get("account_name") or "").strip():
            error = "The BOQ needs a customer account name."

        if not error:
            # ONLY these keys are written. Line items, rates, quantities,
            # sections, the project name, the reference and the revision number
            # are all untouched by construction — there is no path here that
            # could reach them.
            for key in ("account_name", "contact_person", "bill_addr",
                        "bill_city", "bill_state", "bill_pin", "bill_phone",
                        "bill_gstin", "ship_acct_name", "ship_addr",
                        "ship_city", "ship_state", "ship_pin"):
                boq[key] = (form.get(key) or "").strip()
            boq["ship_same"] = bool(form.get("ship_same"))
            boq["to"] = _to_block(form)
            return redirect(url_for("boq.view_boq", id=id,
                                    msg="Party details updated.", type="success"))

    def _v(key: str) -> str:
        if request.method == "POST" and not locked:
            return P.esc(request.form.get(key, ""))
        return P.esc(boq.get(key, ""))

    ship_same = (request.form.get("ship_same") if request.method == "POST"
                 and not locked else boq.get("ship_same"))
    dis = " disabled" if locked else ""

    lock_html = ""
    if locked:
        chips = "".join(
            f'<a class="cl-bill" href="{url_for("ra.view_ra", id=rid)}">'
            f'RA{P.esc(b.get("ra_no"))} &middot; {P.esc(b.get("ref"))}</a>'
            for rid, b in locking)
        n = len(locking)
        cancelled = sum(1 for _rid, b in bills_of(id) if is_cancelled(b))
        cancel_note = ""
        if cancelled:
            cancel_note = (f" {cancelled} cancelled bill"
                           f"{'' if cancelled == 1 else 's'} against this "
                           f"schedule {'is' if cancelled == 1 else 'are'} "
                           f"deliberately not counted here &mdash; a withdrawn "
                           f"claim is excluded from every other total too, and "
                           f"it should not be the thing freezing a customer's "
                           f"name for good.")
        lock_html = f"""
      <div class="cl-lock">
        <b>These details are locked and shown read-only.</b>
        {n} RA bill{"" if n == 1 else "s"}
        {"has" if n == 1 else "have"} already been raised against this schedule
        and each carries its own copy of the customer block, frozen when it was
        saved. Editing the schedule now would leave the register disagreeing
        with documents that have gone out.{cancel_note}
        <div class="cl-bills">{chips}</div>
      </div>"""

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(("Party details " if locked else "Edit party ") + str(boq.get('ref')))}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{CLIENT_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>{"Party details" if locked else "Edit party"}
        <span>{P.esc(boq.get('ref'))}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('client.list_clients')}" class="btn btn-ghost">Client register</a>
      <a href="{url_for('boq.view_boq', id=id)}" class="btn btn-ghost">&#8592; Schedule</a>
    </div>
  </div>

  {_alert(error)}
  {lock_html}

  <form method="POST" action="{url_for('client.edit_party', id=id)}">
    <div class="form-section">
      <div class="section-title">Bill To</div>
      <div class="fg2">
        <div class="form-group">
          <label for="account_name">Account name</label>
          <input type="text" id="account_name" name="account_name"
                 value="{_v('account_name')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="contact_person">Contact person</label>
          <input type="text" id="contact_person" name="contact_person"
                 value="{_v('contact_person')}"{dis}/>
        </div>
        <div class="form-group span2">
          <label for="bill_addr">Address</label>
          <textarea id="bill_addr" name="bill_addr" rows="2"{dis}>{_v('bill_addr')}</textarea>
        </div>
        <div class="form-group">
          <label for="bill_city">City</label>
          <input type="text" id="bill_city" name="bill_city" value="{_v('bill_city')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="bill_state">State</label>
          <input type="text" id="bill_state" name="bill_state" value="{_v('bill_state')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="bill_pin">PIN</label>
          <input type="text" id="bill_pin" name="bill_pin" value="{_v('bill_pin')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="bill_phone">Phone</label>
          <input type="text" id="bill_phone" name="bill_phone" value="{_v('bill_phone')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="bill_gstin">GSTIN</label>
          <input type="text" id="bill_gstin" name="bill_gstin" maxlength="15"
                 style="text-transform:uppercase;" value="{_v('bill_gstin')}"{dis}/>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">Ship To</div>
      <div class="fg2">
        <div class="form-group span2">
          <label for="ship_same">
            <input type="checkbox" id="ship_same" name="ship_same" value="1"
                   {"checked" if ship_same else ""}{dis}/>
            Same as billing
          </label>
        </div>
        <div class="form-group">
          <label for="ship_acct_name">Site name / care of</label>
          <input type="text" id="ship_acct_name" name="ship_acct_name"
                 value="{_v('ship_acct_name')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="ship_pin">PIN</label>
          <input type="text" id="ship_pin" name="ship_pin" value="{_v('ship_pin')}"{dis}/>
        </div>
        <div class="form-group span2">
          <label for="ship_addr">Delivery address</label>
          <textarea id="ship_addr" name="ship_addr" rows="2"{dis}>{_v('ship_addr')}</textarea>
        </div>
        <div class="form-group">
          <label for="ship_city">City</label>
          <input type="text" id="ship_city" name="ship_city" value="{_v('ship_city')}"{dis}/>
        </div>
        <div class="form-group">
          <label for="ship_state">State</label>
          <input type="text" id="ship_state" name="ship_state" value="{_v('ship_state')}"{dis}/>
        </div>
      </div>
    </div>

    <div style="display:flex;gap:.75rem;align-items:center;margin-top:1.4rem;">
      {'' if locked else '<button type="submit" class="btn">Save party details</button>'}
      <a href="{url_for('boq.view_boq', id=id)}" class="btn btn-ghost">
        {"Back to the schedule" if locked else "Cancel"}</a>
      <span style="font-size:.8rem;color:var(--muted);">
        This form touches the customer block and nothing else &mdash; no line,
        no rate, no quantity.</span>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · party details</p></footer>
</main>
</body></html>""")
