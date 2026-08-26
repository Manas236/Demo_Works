"""
proforma.py — Proforma Invoice Module
=====================================
Blueprint  : proforma_bp
Mounted at : /proforma  (registered in app.py)

Routes
------
  GET       /proforma/              — register of issued proforma invoices
  GET,POST  /proforma/from/<qid>    — convert a quotation into a proforma invoice
  GET       /proforma/view/<id>     — the printed proforma invoice document

Why this is its own module and not a render mode of the quotation
-----------------------------------------------------------------
A proforma invoice is a different commercial instrument from the quotation it
comes out of. It carries its own number and its own date, it is a request for
money rather than an offer to sell, and the customer's accounts department
files it against a payment. So it gets its own record and its own numbering
series (PI-0001) with a `quotation_id` back-link — which also means one
quotation can raise several PIs over its life (advance, then balance, then a
part supply) without any of them mutating.

The line items are a **snapshot**, copied at issue time. Once a PI has gone to
a customer its numbers must not move because someone edited the source later.

What is reused, and from where
------------------------------
The printed sheet is the quotation's sheet: `VIEW_DOC_STYLES` gives the A4
frame, the letterhead band, the items table and the print rules; `_inr`,
`_fmt_qty`, `_amount_in_words` and `_meta` are the document's own formatters.
Importing them here (rather than copying) is what keeps the two documents
looking like they came out of the same office.

Import direction: proforma -> quotation -> dashboard. `quotation.py` must never
import this module; it links here with `url_for("proforma.…")` and reads
`STORE["proformas"]` directly, so no cycle exists.
"""

import uuid
from datetime import date as _date
from flask import Blueprint, request, redirect, url_for

import branding as B
import pipeline as P
import docsheet as DS
from dashboard import BASE_STYLES, _nav
from store import STORE

# The document's own formatters and stylesheet — see the module docstring.
from quotation import (
    QUOTATION_STYLES,
    VIEW_DOC_STYLES,
    _amount_in_words,
    _fmt_qty,
    _inr,
    _meta,
)

# The same vocabularies the quotation form offers, and the same widget builder.
# These are shared rather than re-listed on purpose: a term the PI offers but
# the quotation does not (or vice versa) is how the two documents start
# contradicting each other. Add a payment term in quotation.py and it appears
# on both forms.
from quotation import (
    _DEL_TERMS,
    _DISPATCH,
    _INCOTERMS,
    _PAY_TERMS,
    _sel_opts,
)

proforma_bp = Blueprint("proforma", __name__, url_prefix="/proforma")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================
_REF_PREFIX = "PI"

# What share of the order value the FIRST PI on a quotation asks for. 100 = the
# whole thing, which is the safe default while nothing has been invoiced yet:
# asking for less has to be a deliberate act.
#
# Once earlier PIs exist this default is NOT used — the form opens at whatever
# is still uninvoiced (see `_remaining_pct`). 100 is the safe default for the
# first invoice and the dangerous one for the second, so it must not be reused.
DEFAULT_ADVANCE_PCT = 100.0

# Rupees of rounding dust to forgive before calling a PI set "over-invoiced".
# Three PIs at 33.34% come to 100.02% of the order and are not a mistake.
OVER_INVOICE_TOLERANCE = 1.0

# How long the PI's prices hold. Shorter than a quotation's validity on purpose
# — a payment request that has been sitting for a month should be re-issued.
DEFAULT_PI_VALIDITY = "15"

# Common splits, offered as a datalist on the convert form.
ADVANCE_PRESETS = ["100", "50", "30", "25", "10"]


# =============================================================================
# HELPERS
# =============================================================================

def _today() -> str:
    return _date.today().strftime("%Y-%m-%d")


def _ref_num(rec: dict) -> int:
    """
    Numeric tail of a PI ref (`PI-0007` -> 7), for ordering and for finding the
    highest issued number. 0 when it cannot be read, so a hand-edited record
    sorts first rather than raising.
    """
    tail = str(rec.get("ref") or "").rpartition("-")[2]
    return int(tail) if tail.isdigit() else 0


def _next_ref() -> str:
    """
    Next proforma number — PI-0007.

    Scans existing refs for the highest number and adds one, rather than
    `len(...) + 1` (what `quotation._next_ref()` does — ABOUT.md §7.5). len+1
    re-issues a number that has already been on a customer's document as soon as
    one record is removed, and a duplicated *invoice* number is a materially
    worse failure than a duplicated quotation number: it is the key the
    customer's accounts department files the payment against.

    Still not year-scoped. That needs the client's actual numbering policy
    (`SF/PI/26-27/0001` is the usual shape) before it is worth writing.
    """
    highest = max((_ref_num(pi) for pi in STORE["proformas"].values()), default=0)
    return f"{_REF_PREFIX}-{highest + 1:04d}"


def _pct(raw: str, default: float) -> float:
    """Parse an advance percentage. Lenient about '30%' and blanks."""
    txt = str(raw or "").strip().replace("%", "").replace(",", "")
    if not txt:
        return default
    try:
        return float(txt)
    except ValueError:
        return -1.0    # signals "unparseable" to the caller's validation


def _sel_keep(name: str, options: list, current: str) -> str:
    """
    A dropdown that cannot silently change the value it was given.

    `quotation._sel_opts()` marks an option selected only when it matches
    exactly, so a stored value that is not in the list renders as "nothing
    selected" — and the browser then posts the *first* option instead, quietly
    rewriting a term the customer already saw on the quotation. Here the value
    is carried over from a saved record rather than typed fresh, so anything
    unrecognised (hand-edited data, or a list that has been edited since) is
    prepended and kept selected.
    """
    cur = (current or "").strip()
    opts = list(options)
    if cur and cur not in opts:
        opts.insert(0, cur)
    return _sel_opts(name, opts, cur or (opts[0] if opts else ""), cur)


def _customer_of(rec: dict) -> str:
    """First meaningful line of the customer identity, for list views."""
    name = (rec.get("account_name") or "").strip()
    if name:
        return name
    first = (rec.get("to") or "").strip().splitlines()
    return first[0].strip() if first else "—"


def _proformas_for(quotation_id: str) -> list:
    """Every PI raised against one quotation, newest number last."""
    out = [(pid, pi) for pid, pi in STORE["proformas"].items()
           if pi.get("quotation_id") == quotation_id]
    out.sort(key=lambda kv: _ref_num(kv[1]))
    return out


def _invoiced_against(quotation_id: str) -> tuple:
    """
    How much of a quotation has already been asked for, and on which PIs.

    Returns `(total, [refs])` over every PI already raised against it. This is
    the number the convert form and the printed balance line are missing
    without: `advance_pct` is a share of the *order* value, so a second PI left
    at the default would ask for the whole order a second time, and a
    `balance_due` computed as `grand - due` alone would state a balance the
    customer has already settled.

    ⚠ Invoiced, NOT received. Nothing in this app records payment, so this is
    what has been *asked for*. It keeps the paperwork self-consistent; it is not
    a receivables position.
    """
    prior = _proformas_for(quotation_id)
    total = round(sum(float(pi.get("amount_due") or 0.0) for _pid, pi in prior), 2)
    return total, [str(pi.get("ref") or "") for _pid, pi in prior]


def _remaining_pct(grand: float, invoiced: float) -> float:
    """
    The share of the order still uninvoiced, as a percentage — what the convert
    form should open at once earlier PIs exist. 0.0 when the order is fully
    covered, which the form turns into "type it yourself" rather than a default.
    """
    if grand <= 0:
        return 0.0
    return max(0.0, round((grand - invoiced) / grand * 100.0, 2))


def _build_pi_terms(pi: dict) -> list:
    """
    Terms that print on the proforma invoice.

    Deliberately NOT `quotation._build_tnc()`. That set is written for an offer
    — validity of the offer, scope, warranty, commissioning. A PI is a payment
    instrument, so it needs the declarations that make it legally readable as
    one: that it is not a tax invoice, when title passes, what the money buys,
    and that the quotation's own terms still govern the supply.

    ⚠ Like the quotation's standing clauses, these are generic trade terms for a
    fire-protection contractor. Have them checked once against Samruddhi Fire's
    actual commercial policy before the first PI goes to a customer.
    """
    terms = [
        "This is a Proforma Invoice and NOT a Tax Invoice. It is issued for the "
        "purpose of advance payment / opening of a purchase order or letter of "
        "credit. No input tax credit can be claimed against this document.",
        "A Tax Invoice conforming to GST rules will be issued at the time of "
        "dispatch of goods, and is the only document valid for input tax credit.",
    ]

    # Everything interpolated below is user-entered on the convert form, so it
    # is escaped here rather than trusted. (quotation.py's _build_tnc does not
    # — ABOUT.md §7.7. That is the gap, not the pattern.)
    src = P.esc(pi.get("quotation_ref")).strip()
    if src:
        terms.append(
            f"This proforma invoice is raised against our Quotation {src}"
            + (f" dated {P.esc(pi['quotation_date'])}." if pi.get("quotation_date") else ".")
            + " The technical scope, exclusions and terms of that quotation "
              "continue to govern this supply in full."
        )

    pct = float(pi.get("advance_pct") or 0.0)
    if pct >= 100:
        terms.append(
            "Payment — 100% of the invoice value is payable in advance by "
            "NEFT / RTGS to the account detailed above. Please quote the "
            "proforma invoice number on the remittance."
        )
    else:
        terms.append(
            f"Payment — {pct:g}% of the invoice value is payable now by "
            "NEFT / RTGS to the account detailed above. The balance is payable "
            "before dispatch, against our intimation of readiness. Please quote "
            "the proforma invoice number on the remittance."
        )

    delivery_date = P.esc(pi.get("delivery_date")).strip()
    terms.append(
        f"Delivery — by {delivery_date}, counted from the date the advance is "
        "credited to our account, not from the date of this invoice."
        if delivery_date else
        "Delivery — 3–4 weeks from the date the advance is credited to our "
        "account, not from the date of this invoice."
    )

    dispatch = P.esc(pi.get("dispatch_through")).strip()
    if dispatch and dispatch.lower() in ("in clients scope", "self pickup"):
        terms.append("Transportation — in the customer's scope.")
    elif dispatch:
        terms.append(f"Transportation — via {dispatch}; charges extra unless "
                     f"stated as included in the prices above.")

    vdays = P.esc(pi.get("validity_days")).strip()
    terms.append(
        f"Validity — this proforma invoice is valid for {vdays} days from the "
        "date above. Beyond that a fresh proforma invoice must be requested, as "
        "material prices and taxes may have moved."
        if vdays else
        "Validity — 15 days from the date above."
    )

    terms += [
        "Goods remain the property of the seller until payment has been "
        "realised in full, notwithstanding delivery or transfer of risk.",
        "Any statutory change in taxes, duties or levies between the date of "
        "this invoice and the date of dispatch will be to the customer's account.",
        "Bank charges, if any, on the remittance are to the customer's account. "
        "Cheques are accepted subject to realisation.",
        "A debit note of Rs 900.00 + GST will be raised each time a payment "
        "cheque is returned unpaid on presentation.",
        "Standard Force Majeure clause is applicable.",
    ]
    return terms


def _alert(msg: str, msg_type: str) -> str:
    if not msg:
        return ""
    icon = "&#10003;" if msg_type == "success" else "&#10007;"
    return f'<div class="alert alert-{P.esc(msg_type)}">{icon} {P.esc(msg)}</div>'


# =============================================================================
# CSS — proforma-only additions
# =============================================================================
# Plain string, not an f-string, so the CSS braces are written once. Layered
# AFTER VIEW_DOC_STYLES and scoped inside .quotation-doc, so it inherits the
# document's type scale (--fs-*) and rule weights (--rule-*) instead of
# inventing a second set. Nothing here introduces a new font, size or border
# weight — that is the whole point of the four rules at the top of that sheet.

PROFORMA_STYLES = """
<style>
  /* ── The "not a tax invoice" declaration ──────────────────────────────
     Sits directly under the title, inside the frame. It is the single most
     important sentence on the page: it is what stops the document being
     mistaken for a tax invoice, so it prints at body weight in the frame
     rather than being buried at clause 1 of the terms. */
  .quotation-doc .doc-sub {
    text-align:center; font-size:var(--fs-sm); font-weight:700;
    padding:2px 6px; border-bottom:var(--rule-box);
  }
  .quotation-doc .doc-sub .ds-src { font-weight:400; color:var(--doc-soft); }

  /* ── Payment box ──────────────────────────────────────────────────────
     Always present, but it only breaks the figure down when there is
     arithmetic to show — a part payment, or earlier PIs already raised
     against the same order. The figure the customer actually has to pay is
     the one number on this document that must not be hunted for, so it gets
     the heavy rule and the --fs-md step — the same emphasis the closing total
     gets in the items table, and no more. Weight and rule, never fill. */
  .quotation-doc .pay-box { border-top:var(--rule-box); }
  .quotation-doc .pay-row {
    display:flex; justify-content:space-between; gap:6mm;
    padding:2px 6px; border-bottom:var(--rule-hair);
  }
  .quotation-doc .pay-row:last-child { border-bottom:none; }
  .quotation-doc .pay-amt {
    font-variant-numeric:tabular-nums; white-space:nowrap;
  }
  .quotation-doc .pay-due {
    font-weight:700; font-size:var(--fs-md);
    border-top:var(--rule); border-bottom:var(--rule);
  }
  .quotation-doc .pay-words {
    padding:2px 6px; font-weight:700; border-top:var(--rule-hair);
  }

""" + DS.BANK_CSS + """
  .quotation-doc .pi-note { margin-top:4mm; }
  .quotation-doc .pi-note .pn-lbl { font-weight:700; }

""" + DS.BANK_CSS_NARROW + """
  /* ── Screen-only: the convert form and the register ───────────────── */
  .src-note {
    background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--brand); border-radius:var(--radius);
    padding:.9rem 1.2rem; margin-bottom:1.4rem; font-size:.88rem;
  }
  .src-note b { color:var(--brand); }
  .src-note .sn-sub { color:var(--muted); font-size:.82rem; margin-top:.25rem; }

  .frozen-wrap {
    border:1px solid var(--border); border-radius:10px; overflow:hidden;
    background:var(--bg);
  }
  .frozen-wrap table { font-size:.82rem; }
  .frozen-wrap td, .frozen-wrap th { padding:.45rem .7rem; }
  .frozen-wrap .fz-comp td:first-child { padding-left:1.6rem; color:var(--muted); }
  .frozen-wrap .fz-num { text-align:right; font-variant-numeric:tabular-nums; }
  .frozen-wrap tfoot td {
    font-weight:700; background:var(--bg); border-top:1px solid var(--border);
  }
  .frozen-hint {
    font-size:.8rem; color:var(--muted); margin-top:.6rem; line-height:1.5;
  }

  /* ── Running position on the convert form ─────────────────────────────
     One quotation can carry several PIs (advance, then balance, then a part
     supply), so the form has to state the arithmetic — quoted, invoiced,
     what is left — rather than list the earlier PIs as chips and leave the
     user to add them up against a field pre-filled with 100%.
     Colours reuse the amber already used by .todo-chip and .pi-badge.part;
     "fully invoiced" takes --navy rather than introducing a green. */
  .pi-ledger { margin-top:.75rem; max-width:26rem; }
  .pi-ledger .pl-row {
    display:flex; justify-content:space-between; gap:1.2rem;
    padding:.3rem 0; font-size:.85rem; color:var(--muted);
  }
  .pi-ledger .pl-row b {
    color:var(--text); font-variant-numeric:tabular-nums; white-space:nowrap;
  }
  .pi-ledger .pl-rem {
    border-top:1px solid var(--border); font-weight:700; color:var(--text);
  }
  .pi-ledger .pl-rem b { color:var(--brand); }
  .pi-ledger .pl-done, .pi-ledger .pl-done b { color:var(--navy); }
  .pi-ledger .pl-over, .pi-ledger .pl-over b { color:#8A5A00; }

  .adv-row { display:flex; align-items:flex-end; gap:1rem; flex-wrap:wrap; }
  .adv-out {
    font-size:.88rem; color:var(--muted); padding-bottom:.55rem; line-height:1.5;
  }
  .adv-out b { color:var(--brand); font-size:1rem; }

  /* Over-invoicing is confirmed, never blocked — a PI set that exceeds the
     quoted value is occasionally right and usually a slip, so it costs one
     deliberate tick. See OVER_INVOICE_TOLERANCE. */
  .over-confirm {
    display:flex; gap:.65rem; align-items:flex-start; margin-top:.9rem;
    padding:.75rem .9rem; font-size:.85rem; line-height:1.5;
    background:#FFF4D6; color:#8A5A00;
    border:1px solid #E0A93B; border-radius:var(--radius);
  }
  .over-confirm input { margin-top:.2rem; flex:none; }

  .pi-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem;
    background:var(--navy-lt); color:var(--navy);
  }
  .pi-badge.part { background:#FFF4D6; color:#8A5A00; }

  /* .pi-strip / .pi-chip are defined in QUOTATION_STYLES — both this module
     and the quotation's deal panel render them, and every page here already
     loads that sheet. */

  /* ── Tax-invoice chips ────────────────────────────────────────────────
     One step further down the same chain: these list the tax invoices raised
     against a proforma. They live here, not in INVOICE_STYLES, because this
     module's view page renders them and it must not import invoice.py — the
     link is url_for + a direct read of STORE["invoices"], which is what keeps
     the proforma -> invoice arrow one-way. invoice.py loads this sheet on
     every page, so it gets them for free. */
  .ti-strip { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.6rem; }
  .ti-chip {
    font-size:.76rem; font-weight:600; text-decoration:none;
    padding:.22rem .55rem; border-radius:7px;
    border:1px solid var(--border); background:var(--bg); color:var(--navy);
  }
  .ti-chip:hover { border-color:var(--brand); color:var(--brand); }
  @media print { .ti-strip { display:none; } }
</style>
"""


# =============================================================================
# RENDERING — why these views do not call render_template_string()
# =============================================================================
#
# Every page in this module is a fully interpolated HTML string by the time the
# view returns it. Nothing is passed as Jinja context — ABOUT.md §1 says so
# explicitly — so handing the finished string back to Jinja parses it a second
# time for no benefit and one large cost: any `{{ … }}` or `{% … %}` that
# reached the output from USER INPUT is then executed as a template.
#
# That is not theoretical. `pipeline.esc()` escapes `< > & " '` and deliberately
# not braces, so a PI whose `notes` reads `{{ config }}` prints the Flask config
# — including SECRET_KEY — onto the document, and one reading `{% for x in y %}`
# raises a TemplateSyntaxError that 500s the page. Both are stored on the
# record, so both persist until somebody raises a fresh PI.
#
# Returning the string directly is what Flask does with any `str` a view
# returns. It removes the second parse, and with it the injection. HTML
# escaping still does its own job — this changes nothing about XSS.
#
# ⚠ Still open in `quotation.py` and `product.py`, and this one-liner does not
#   reach either: quotation.py builds its pages with `.format()` and has
#   attribute, <script> and option-text sinks besides; product.py does not
#   escape at all. Each wants its own pass — ABOUT.md §7.9d.
# =============================================================================

def _page(html: str) -> str:
    """A finished page. See the note above — deliberately not Jinja-rendered."""
    return html


# =============================================================================
# ROUTES
# =============================================================================

@proforma_bp.route("/")
def list_proformas():
    """Register of every proforma invoice raised, newest number first."""
    proformas = STORE["proformas"]
    rows = sorted(proformas.items(), key=lambda kv: kv[1].get("ref", ""), reverse=True)

    dash_url = url_for("dashboard.index")
    qtn_url  = url_for("quotation.list_quotations")

    total_value = sum(float(pi.get("grand_total") or 0.0) for pi in proformas.values())
    total_due   = sum(float(pi.get("amount_due")  or 0.0) for pi in proformas.values())

    tiles_html = ""
    if proformas:
        part = sum(1 for pi in proformas.values() if float(pi.get("advance_pct") or 100) < 100)
        tiles_html = f"""
        <div class="pipe-tiles">
          <div class="pipe-tile t-open">
            <div class="pt-lbl">Invoiced Value</div>
            <div class="pt-val">&#8377;&nbsp;{total_value:,.0f}</div>
            <div class="pt-sub">{len(proformas)} proforma invoice{"s" if len(proformas) != 1 else ""}</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Requested Now</div>
            <div class="pt-val">&#8377;&nbsp;{total_due:,.0f}</div>
            <div class="pt-sub">{part} part-payment{"s" if part != 1 else ""}
                &middot; {len(proformas) - part} in full</div>
          </div>
        </div>"""

    if rows:
        rows_html = ""
        for pid, pi in rows:
            view_url = url_for("proforma.view_proforma", id=pid)
            pct      = float(pi.get("advance_pct") or 100.0)
            badge    = (f'<span class="pi-badge part">{pct:g}% advance</span>'
                        if pct < 100 else '<span class="pi-badge">full value</span>')
            src_url  = url_for("quotation.view_quotation", id=pi.get("quotation_id", ""))
            rows_html += f"""
            <tr>
              <td class="td-ref">{P.esc(pi.get('ref'))}</td>
              <td class="td-muted">{P.esc(pi.get('date'))}</td>
              <td class="td-cust">{P.esc(_customer_of(pi))}</td>
              <td class="col-h"><a href="{src_url}" class="btn-view">{P.esc(pi.get('quotation_ref'))}</a></td>
              <td class="col-h">{badge}</td>
              <td class="td-muted">&#8377;&nbsp;{float(pi.get('grand_total') or 0):,.0f}</td>
              <td class="td-total">&#8377;&nbsp;{float(pi.get('amount_due') or 0):,.0f}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>"""
        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>PI No.</th><th>Date</th><th>Customer</th>
            <th class="col-h">From Quotation</th><th class="col-h">Ask</th>
            <th>Invoice Value</th><th>Payable Now</th><th></th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#129534;</div><br>
          <strong>No proforma invoices yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            A proforma invoice is raised from a quotation — open the quotation the
            customer has agreed to and use <b>Raise Proforma</b>.</p>
          <a href="{qtn_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">
            Go to Quotation Register</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Proforma Invoices")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}</head>
    <body>{_nav()}
    <main>
      {_alert(request.args.get("msg"), request.args.get("type", "success"))}
      <div class="page-top">
        <h1>Proforma <span>Invoices</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            {len(proformas)} issued
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{qtn_url}"  class="btn btn-ghost">Quotations</a>
        </div>
      </div>
      {tiles_html}
      {table_html}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · proforma invoice register</p></footer>
    </main></body></html>"""
    return _page(template)


@proforma_bp.route("/from/<qid>", methods=["GET", "POST"])
def create_proforma(qid: str):
    """
    Raise a proforma invoice from a quotation.

    The line items, prices, taxes and addresses are copied verbatim and are not
    editable here — the PI states what was quoted. Only the fields that belong
    to the *invoice* are collected: its date, the customer's PO reference, how
    much of the value is being asked for now, and the payment/delivery terms
    that apply to this particular payment.
    """
    q = STORE["quotations"].get(qid)
    if not q:
        return redirect(url_for("quotation.list_quotations",
                                msg="Quotation not found.", type="error"))

    f     = request.form
    error = ""

    # ── What this quotation has already been invoiced for ──────────────────
    # Read once, before either branch: the POST path needs it to compute a
    # truthful balance and to catch over-invoicing, and the GET path needs it
    # to open the form at the uninvoiced remainder instead of at 100%.
    grand              = float(q.get("grand_total") or 0.0)
    invoiced, pri_refs = _invoiced_against(qid)
    remaining          = round(grand - invoiced, 2)
    rem_pct            = _remaining_pct(grand, invoiced)
    needs_confirm      = False

    if request.method == "POST":
        pi_date  = (f.get("date") or "").strip()
        pct      = _pct(f.get("advance_pct"), DEFAULT_ADVANCE_PCT)
        validity = (f.get("validity_days") or "").strip()
        due      = round(grand * pct / 100.0, 2)

        if not pi_date:
            error = "Invoice date is required."
        elif pct < 0:
            error = "Advance % must be a number, e.g. 30."
        elif not (0 < pct <= 100):
            error = "Advance % must be greater than 0 and no more than 100."
        elif validity and not validity.isdigit():
            error = "Validity must be a whole number of days."

        # ── Over-invoicing: confirm, never block ───────────────────────────
        # Asking for more than the order value is occasionally right (scope
        # grew, prices moved) and usually a slip, so it takes a deliberate
        # second act rather than a refusal. Only reachable when earlier PIs
        # exist — on the first PI, `pct <= 100` already covers it.
        over = round(invoiced + due - grand, 2)
        if not error and over > OVER_INVOICE_TOLERANCE and not f.get("confirm_over"):
            needs_confirm = True
            error = (f"This would invoice &#8377;&nbsp;{invoiced + due:,.0f} against a "
                     f"quoted value of &#8377;&nbsp;{grand:,.0f} — "
                     f"&#8377;&nbsp;{over:,.0f} more than the order. "
                     f"{len(pri_refs)} proforma invoice"
                     f"{'s' if len(pri_refs) != 1 else ''} "
                     f"({', '.join(pri_refs)}) already account for "
                     f"&#8377;&nbsp;{invoiced:,.0f}. "
                     f"Tick the box below to raise it anyway.")

        if not error:
            pid = str(uuid.uuid4())
            pi = {
                "id":  pid,
                "ref": _next_ref(),
                "date": pi_date,

                # ── Back-link to the source. quotation_ref is stored, not
                #    looked up, so the PI still prints correctly as a historical
                #    document if the quotation is ever removed.
                "quotation_id":   qid,
                "quotation_ref":  q.get("ref", ""),
                "quotation_date": q.get("date", ""),

                # ── Customer identity, copied ─────────────────────────────
                "account_name":   q.get("account_name", ""),
                "contact_person": q.get("contact_person", ""),
                "to":             q.get("to", ""),
                "bill_gstin":     q.get("bill_gstin", ""),
                "ship_same":      q.get("ship_same", ""),
                "ship_acct_name": q.get("ship_acct_name", ""),
                "ship_addr":      q.get("ship_addr", ""),
                "ship_city":      q.get("ship_city", ""),
                "ship_state":     q.get("ship_state", ""),
                "ship_pin":       q.get("ship_pin", ""),
                "ship_phone":     q.get("ship_phone", ""),
                "ship_gstin":     q.get("ship_gstin", ""),

                # ── Frozen commercial content ─────────────────────────────
                # dict(row) per line: a shallow copy is enough because every
                # value in a line_item is a scalar, and it guarantees a later
                # edit to the quotation cannot reach an issued invoice.
                "line_items": [dict(r) for r in q.get("line_items", [])],
                "subtotal":   float(q.get("subtotal") or q.get("grand_total") or 0.0),
                "tax_type":   q.get("tax_type", "exempt"),
                "tax_info":   dict(q.get("tax_info") or {"total": 0.0}),
                "grand_total": grand,
                "total_qty":   q.get("total_qty", 0),

                # ── The invoice's own fields ──────────────────────────────
                "po_number":     (f.get("po_number") or "").strip(),
                "po_date":       (f.get("po_date") or "").strip(),
                "advance_pct":   pct,
                "amount_due":    due,
                "project_id":    (f.get("project_id") or "").strip(),

                # ── The running position, frozen at issue ─────────────────
                # What earlier PIs on this quotation had already asked for.
                # Frozen like every other figure here: PI-0001 stated a
                # balance that was true on its date, and issuing PI-0002 must
                # not rewrite the document already sitting in the customer's
                # ledger. So the balance is `order - invoiced before this one
                # - this one`, and a later PI cannot reach back into it.
                "prior_invoiced": invoiced,
                "prior_refs":     list(pri_refs),
                "balance_due":    round(grand - invoiced - due, 2),
                "payment_terms": (f.get("payment_terms") or "").strip(),
                "delivery_terms": (f.get("delivery_terms") or "").strip(),
                "delivery_date": (f.get("delivery_date") or "").strip(),
                "dispatch_through": (f.get("dispatch_through") or "").strip(),
                "incoterms":     (f.get("incoterms") or "").strip(),
                "validity_days": validity,
                "notes":         (f.get("notes") or "").strip(),

                "company_branch": q.get("company_branch", ""),
                "auth_signatory": q.get("auth_signatory", ""),
            }
            STORE["proformas"][pid] = pi

            # The PI is a real event in the deal's life, so it belongs on the
            # quotation's audit trail. log_event does not change the stage.
            # The audit trail carries the running position, not just this
            # invoice — "raised for 7,00,000" alone doesn't tell you whether
            # the deal is now fully invoiced or double-invoiced.
            msg = (f"Proforma invoice {pi['ref']} raised for &#8377;{due:,.0f}"
                   + (f" ({pct:g}% of quoted value)" if pct < 100 else ""))
            if invoiced:
                bal = pi["balance_due"]
                msg += (f". Invoiced to date &#8377;{invoiced + due:,.0f} of "
                        f"&#8377;{grand:,.0f}"
                        + (f", &#8377;{bal:,.0f} uninvoiced." if bal > 0 else
                           " — fully invoiced." if bal == 0 else
                           f" — &#8377;{-bal:,.0f} OVER the quoted value."))
            else:
                msg += "."
            P.log_event(q, msg)

            return redirect(url_for("proforma.view_proforma", id=pid,
                                    msg=f"Proforma invoice {pi['ref']} created.",
                                    type="success"))

    # ── Field values: the user's own input on a failed POST, else the
    #    quotation's, else the module default. ───────────────────────────────
    def _v(name: str, fallback: str = "") -> str:
        if request.method == "POST":
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    v_date     = _v("date", _today())
    v_po_no    = _v("po_number", q.get("po_number", ""))
    v_po_date  = _v("po_date", q.get("po_date", ""))
    v_pid      = _v("project_id", q.get("project_id", ""))
    # The advance defaults to whatever is still uninvoiced, not to 100. On the
    # first PI those are the same number; on the second they are the whole
    # difference between "ask for the balance" and "bill the order twice".
    # Fully invoiced already ⇒ open blank, so a further PI has to be typed.
    if not pri_refs:
        _pct_default = f"{DEFAULT_ADVANCE_PCT:g}"
    elif rem_pct > 0:
        _pct_default = f"{rem_pct:g}"
    else:
        _pct_default = ""
    v_pct      = _v("advance_pct", _pct_default)
    v_pay      = _v("payment_terms", q.get("payment_terms", ""))
    v_del_t    = _v("delivery_terms", q.get("delivery_terms", ""))
    v_del_d    = _v("delivery_date", q.get("delivery_date", ""))
    v_dispatch = _v("dispatch_through", q.get("dispatch_through", ""))
    v_inco     = _v("incoterms", q.get("incoterms", ""))
    v_valid    = _v("validity_days", DEFAULT_PI_VALIDITY)
    v_notes    = _v("notes")

    # ── Frozen line-item preview ───────────────────────────────────────────
    rows_html = ""
    for r in q.get("line_items", []):
        comp = " fz-comp" if r.get("depth", 0) == 1 else ""
        rows_html += f"""
        <tr class="{comp.strip()}">
          <td>{P.esc(r.get('name'))}</td>
          <td class="td-muted">{P.esc(r.get('part_no'))}</td>
          <td class="fz-num">{_fmt_qty(float(r.get('qty') or 0))} {P.esc(r.get('unit'))}</td>
          <td class="fz-num">{_inr(r.get('price') or 0)}</td>
          <td class="fz-num">{_inr(r.get('total') or 0)}</td>
        </tr>"""

    tax_total = float((q.get("tax_info") or {}).get("total") or 0.0)
    frozen_html = f"""
    <div class="frozen-wrap"><table>
      <thead><tr>
        <th>Description</th><th>Part No</th>
        <th class="fz-num">Qty</th><th class="fz-num">Rate</th><th class="fz-num">Amount</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr><td colspan="4" class="fz-num">Subtotal</td>
            <td class="fz-num">{_inr(q.get('subtotal') or grand)}</td></tr>
        <tr><td colspan="4" class="fz-num">Tax</td>
            <td class="fz-num">{_inr(tax_total)}</td></tr>
        <tr><td colspan="4" class="fz-num">Invoice Value</td>
            <td class="fz-num">{_inr(grand)}</td></tr>
      </tfoot>
    </table></div>
    <p class="frozen-hint">
      These lines are copied onto the invoice exactly as quoted and are frozen at
      issue. To invoice different quantities or prices, raise a new quotation first.
    </p>"""

    # ── The running position ───────────────────────────────────────────────
    # Listing the earlier PIs was never enough: the user still had to add them
    # up in their head against a form pre-filled with 100%. So state the
    # arithmetic — quoted, invoiced, what is left — and let the field default
    # to the last line.
    existing = _proformas_for(qid)
    existing_html = ""
    if existing:
        chips = "".join(
            f'<a class="pi-chip" href="{url_for("proforma.view_proforma", id=p_id)}">'
            f'{P.esc(p.get("ref"))} &middot; &#8377;&nbsp;{float(p.get("amount_due") or 0):,.0f}</a>'
            for p_id, p in existing
        )
        if remaining > OVER_INVOICE_TOLERANCE:
            rem_cls, rem_lbl = "", "Still uninvoiced"
        elif remaining >= -OVER_INVOICE_TOLERANCE:
            rem_cls, rem_lbl = " pl-done", "Fully invoiced — nothing left to bill"
        else:
            rem_cls, rem_lbl = " pl-over", "Over-invoiced against the quoted value"

        existing_html = f"""
        <div class="pi-strip">{chips}</div>
        <div class="pi-ledger">
          <div class="pl-row"><span>Quoted value</span>
               <b>&#8377;&nbsp;{grand:,.0f}</b></div>
          <div class="pl-row"><span>Already invoiced on
               {len(existing)} proforma{"s" if len(existing) != 1 else ""}</span>
               <b>&#8722;&nbsp;&#8377;&nbsp;{invoiced:,.0f}</b></div>
          <div class="pl-row pl-rem{rem_cls}"><span>{rem_lbl}</span>
               <b>&#8377;&nbsp;{abs(remaining):,.0f}</b></div>
        </div>
        <div class="sn-sub">Invoiced, not received &mdash; this app records what
          has been asked for, not what has been paid.</div>"""

    # ── Advance field: presets, help text, over-invoice confirmation ───────
    # The percentage stays a share of the QUOTED value, not of the balance —
    # that is what "30% advance" means in the trade and what prints on the
    # document. Only the default and the guidance know about the balance.
    presets = list(ADVANCE_PRESETS)
    if pri_refs and rem_pct > 0 and f"{rem_pct:g}" not in presets:
        presets.insert(0, f"{rem_pct:g}")
    presets_html = "".join(f'<option value="{p}"></option>' for p in presets)

    if not pri_refs:
        adv_help = ("100 asks for the whole invoice value; 30 asks for a 30% advance "
                    "and shows the balance as payable before dispatch.<br>"
                    f"Invoice value <b>&#8377;&nbsp;{grand:,.0f}</b>")
    elif rem_pct > 0:
        adv_help = (f"Pre-filled with <b>{rem_pct:g}%</b> &mdash; the part of this order "
                    f"not yet invoiced (&#8377;&nbsp;{remaining:,.0f}).<br>"
                    f"The percentage is of the quoted value "
                    f"(&#8377;&nbsp;{grand:,.0f}), not of the balance.")
    else:
        adv_help = ("This quotation is <b>already fully invoiced</b>, so the field is "
                    "blank rather than pre-filled.<br>Enter a percentage only if you "
                    "mean to invoice beyond the order value.")

    p_opts = '<option value="">&#8212; none &#8212;</option>'
    for proj_id, proj in sorted(STORE["projects"].items(),
                                key=lambda kv: kv[1].get("name", "").lower()):
        sel = " selected" if proj_id == v_pid else ""
        p_opts += f'<option value="{P.esc(proj_id)}"{sel}>{P.esc(proj.get("name"))}</option>'

    confirm_html = ""
    if needs_confirm:
        confirm_html = """
          <label class="over-confirm">
            <input type="checkbox" name="confirm_over" value="1"/>
            <span>Yes &mdash; raise this invoice even though it takes the total
              past the quoted value. The scope or price of this order has
              changed since it was quoted.</span>
          </label>"""

    q_view = url_for("quotation.view_quotation", id=qid)

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Raise Proforma Invoice")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Raise <span>Proforma Invoice</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{q_view}" class="btn btn-ghost">&#8592; Back to Quotation</a>
          <a href="{url_for("proforma.list_proformas")}" class="btn btn-ghost">All Proformas</a>
        </div>
      </div>

      {_alert(error, "error")}

      <div class="src-note">
        From quotation <b>{P.esc(q.get('ref'))}</b> dated {P.esc(q.get('date'))}
        &middot; {P.esc(_customer_of(q))}
        &middot; quoted value <b>&#8377;&nbsp;{grand:,.0f}</b>
        <div class="sn-sub">The invoice will be numbered {_next_ref()}.</div>
        {existing_html}
      </div>

      <form method="POST" action="{url_for("proforma.create_proforma", qid=qid)}">

        <div class="form-section">
          <div class="section-title">Invoice</div>
          <div class="fg3">
            <div class="form-group">
              <label for="date">Invoice Date *</label>
              <input type="date" id="date" name="date" value="{P.esc(v_date)}" required/>
            </div>
            <div class="form-group">
              <label for="po_number">Customer PO No.</label>
              <input type="text" id="po_number" name="po_number" value="{P.esc(v_po_no)}"
                     placeholder="their PO number, if received"/>
            </div>
            <div class="form-group">
              <label for="po_date">Customer PO Date</label>
              <input type="date" id="po_date" name="po_date" value="{P.esc(v_po_date)}"/>
            </div>
            <div class="form-group">
              <label for="project_id">Project <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <select id="project_id" name="project_id">{p_opts}</select>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Amount Requested</div>
          <div class="adv-row">
            <div class="form-group" style="max-width:170px;">
              <label for="advance_pct">Advance % *</label>
              <input type="number" id="advance_pct" name="advance_pct" list="adv-presets"
                     value="{P.esc(v_pct)}" min="0.01" max="100" step="any" required/>
              <datalist id="adv-presets">
                {presets_html}
              </datalist>
            </div>
            <div class="adv-out">{adv_help}</div>
          </div>
          {confirm_html}
        </div>

        <div class="form-section">
          <div class="section-title">Terms carried onto this invoice</div>
          <div class="fg2">
            <div class="form-group">
              <label for="payment_terms">Payment Terms</label>
              {_sel_keep("payment_terms", _PAY_TERMS, v_pay)}
            </div>
            <div class="form-group">
              <label for="delivery_terms">Terms of Delivery</label>
              {_sel_keep("delivery_terms", _DEL_TERMS, v_del_t)}
            </div>
            <div class="form-group">
              <label for="delivery_date">Delivery Date</label>
              <input type="date" id="delivery_date" name="delivery_date" value="{P.esc(v_del_d)}"/>
            </div>
            <div class="form-group">
              <label for="dispatch_through">Dispatch Through</label>
              {_sel_keep("dispatch_through", _DISPATCH, v_dispatch)}
            </div>
            <div class="form-group">
              <label for="incoterms">Incoterms</label>
              {_sel_keep("incoterms", _INCOTERMS, v_inco)}
            </div>
            <div class="form-group">
              <label for="validity_days">PI Validity (days)</label>
              <input type="number" id="validity_days" name="validity_days"
                     value="{P.esc(v_valid)}" min="0" step="1"/>
            </div>
            <div class="form-group span2">
              <label for="notes">Note on the invoice <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <input type="text" id="notes" name="notes" value="{P.esc(v_notes)}"
                     placeholder="e.g. Against your enquiry dated 12.07.2026 — part supply, first lot"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Items being invoiced &mdash; frozen at issue</div>
          {frozen_html}
        </div>

        <div class="form-actions">
          <button type="submit" class="btn">Raise Proforma Invoice</button>
          <a href="{q_view}" class="btn btn-ghost">Cancel</a>
        </div>
      </form>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · proforma invoice</p></footer>
    </main></body></html>"""
    return _page(template)


@proforma_bp.route("/view/<id>")
def view_proforma(id: str):
    """
    The printed proforma invoice.

    Same A4 sheet as the quotation (VIEW_DOC_STYLES) — same letterhead band,
    same items table, same print rules. What differs is what a PI has to say
    that a quotation does not: the not-a-tax-invoice declaration, the amount
    actually payable now, and the bank account to pay it into.
    """
    pi = STORE["proformas"].get(id)
    if not pi:
        return redirect(url_for("proforma.list_proformas",
                                msg="Proforma invoice not found.", type="error"))

    # ── Line-item rows — identical treatment to the quotation document ─────
    sno, total_qty, table_rows = 0, 0.0, ""
    for row in pi.get("line_items", []):
        sno += 1
        depth   = row.get("depth", 0)
        row_cls = "row-assembly" if row.get("type") == "assembly" else "row-item"
        indent  = "indent-1" if depth == 1 else ("indent-2" if depth >= 2 else "")
        if depth == 0:
            total_qty += float(row.get("qty") or 0)

        table_rows += f"""
        <tr class="{row_cls}">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>
          <td class="c-desc {indent}">{P.esc(row.get('name'))}</td>
          <td class="c-hsn">{P.esc(row.get('hsn'))}</td>
          <td class="c-qty">{_fmt_qty(float(row.get('qty') or 0))}</td>
          <td class="c-unit">{P.esc(row.get('unit'))}</td>
          <td class="c-price">{_inr(row.get('price') or 0)}</td>
          <td class="c-total">{_inr(row.get('total') or 0)}</td>
        </tr>"""

    subtotal = float(pi.get("subtotal") or pi.get("grand_total") or 0.0)
    tax_info = pi.get("tax_info") or {"total": 0.0}
    tax_type = pi.get("tax_type", "exempt")
    grand    = float(pi.get("grand_total") or 0.0)
    has_tax  = tax_type != "exempt" and float(tax_info.get("total") or 0) > 0

    if has_tax:
        table_rows += f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">Subtotal</td>
          <td class="c-qty"></td><td class="c-unit"></td><td class="c-price"></td>
          <td class="c-total">{_inr(subtotal)}</td>
        </tr>"""

        rate_keys = {"CGST": "cgst_rate", "SGST": "sgst_rate",
                     "IGST": "igst_rate", "VAT":  "vat_rate"}
        skip_keys = {"total", *rate_keys.values()}
        for tname, tamt in tax_info.items():
            if tname in skip_keys:
                continue
            r = tax_info.get(rate_keys.get(tname, ""), 0)
            rate_label = f" @ {r:g}%" if r else ""
            table_rows += f"""
            <tr class="row-sum">
              <td colspan="4" class="sum-lbl">{tname}{rate_label}</td>
              <td class="c-qty"></td><td class="c-unit"></td><td class="c-price"></td>
              <td class="c-total">{_inr(tamt)}</td>
            </tr>"""

    table_rows += f"""
    <tr class="row-total row-sum">
      <td colspan="4" class="sum-lbl">{"Invoice Value" if has_tax else "Total"}</td>
      <td class="c-qty">{_fmt_qty(total_qty)}</td>
      <td class="c-unit"></td><td class="c-price"></td>
      <td class="c-total">{_inr(grand)}</td>
    </tr>"""

    # ── Header meta ───────────────────────────────────────────────────────
    validity = P.esc(pi.get("validity_days")).strip()
    meta_col_1 = (
        _meta("Proforma Invoice No.",  P.esc(pi.get("ref"))) +
        _meta("Against Quotation",     P.esc(pi.get("quotation_ref"))) +
        _meta("Buyer's PO No.",        P.esc(pi.get("po_number"))) +
        _meta("Mode/Term of Payment",  P.esc(pi.get("payment_terms"))) +
        _meta("Terms of Delivery",     P.esc(pi.get("delivery_terms")))
    )
    meta_col_2 = (
        _meta("Date",             P.esc(pi.get("date"))) +
        _meta("Quotation Date",   P.esc(pi.get("quotation_date"))) +
        _meta("Buyer's PO Date",  P.esc(pi.get("po_date"))) +
        _meta("Dispatch Through", P.esc(pi.get("dispatch_through"))) +
        _meta("Validity",         f"{validity} days" if validity else "") +
        _meta("Incoterms",        P.esc(pi.get("incoterms")))
    )

    # ── To / Ship To ──────────────────────────────────────────────────────
    to_lines   = (pi.get("to") or "").strip().split("\n")
    to_display = ""
    if to_lines and to_lines[0].strip():
        rest = "\n".join(to_lines[1:]).strip()
        to_display = f'<span class="dh-name">{P.esc(to_lines[0])}</span>'
        if rest:
            to_display += f"\n{P.esc(rest)}"

    ship_parts = []
    if not pi.get("ship_same"):
        sname = pi.get("ship_acct_name") or pi.get("account_name") or ""
        if sname:                 ship_parts.append(sname)
        if pi.get("ship_addr"):   ship_parts.append(pi["ship_addr"])
        scity = ", ".join(filter(None, [pi.get("ship_city", ""), pi.get("ship_state", "")]))
        if scity or pi.get("ship_pin"):
            ship_parts.append(f"{scity} – {pi.get('ship_pin', '')}".strip(" –"))
        if pi.get("ship_phone"):  ship_parts.append(f"Ph: {pi['ship_phone']}")
        if pi.get("ship_gstin"):  ship_parts.append(f"GSTIN: {pi['ship_gstin']}")

    ship_html = ""
    if ship_parts:
        ship_html = ('<div class="dh-ship"><span class="dh-lbl">Ship To</span>'
                     f'<div class="dh-body">{P.esc(chr(10).join(ship_parts))}</div></div>')

    # ── Payment box ───────────────────────────────────────────────────────
    # The full breakdown only earns its space when there is arithmetic to show
    # — a part payment, or an order with earlier PIs against it. A PI that is
    # the only one and asks for the whole value gets the compact form: the
    # closing row of the table already states that figure, and repeating it
    # invites the reader to look for a difference.
    #
    # `prior_invoiced` is read off the record, never recomputed. It is what had
    # been invoiced when THIS document was issued; a PI raised later must not
    # change what a document already with the customer says.
    pct    = float(pi.get("advance_pct") or 100.0)
    due    = float(pi.get("amount_due") or grand)
    bal    = float(pi.get("balance_due") or 0.0)
    prior  = float(pi.get("prior_invoiced") or 0.0)
    p_refs = [r for r in (pi.get("prior_refs") or []) if r]

    if prior > 0 or pct < 100:
        # With earlier PIs in play, `grand` is the value of the whole order,
        # not of this demand — so it is labelled as such.
        head_lbl = "Total Order Value" if prior > 0 else "Total Invoice Value"
        due_lbl  = (f"Amount Payable Now ({pct:g}% of order value)" if prior > 0
                    else f"Amount Payable Now (advance @ {pct:g}%)")

        prior_row = ""
        if prior > 0:
            on = f" on {', '.join(P.esc(r) for r in p_refs)}" if p_refs else ""
            prior_row = (f'<div class="pay-row"><span>Less: already invoiced{on}</span>'
                         f'<span class="pay-amt">{_inr(prior)}</span></div>')

        # A negative balance means this PI was deliberately raised past the
        # order value. Printing "Balance 0.00" there would be a false comfort
        # and printing a negative is not a figure the customer can act on, so
        # the row is simply omitted and the totals above carry the story.
        bal_row = ""
        if bal > 0:
            bal_row = ('<div class="pay-row"><span>Balance, payable before dispatch</span>'
                       f'<span class="pay-amt">{_inr(bal)}</span></div>')
        elif prior > 0 and bal == 0:
            bal_row = ('<div class="pay-row"><span>Balance on this order after '
                       'this payment</span>'
                       f'<span class="pay-amt">{_inr(0)}</span></div>')

        pay_box = f"""
      <div class="pay-box">
        <div class="pay-row"><span>{head_lbl}</span>
             <span class="pay-amt">{_inr(grand)}</span></div>
        {prior_row}
        <div class="pay-row pay-due"><span>{due_lbl}</span>
             <span class="pay-amt">{_inr(due)}</span></div>
        {bal_row}
        <div class="pay-words">Amount Payable Now (in words) : {_amount_in_words(due)}</div>
      </div>"""
    else:
        pay_box = f"""
      <div class="pay-box">
        <div class="pay-row pay-due"><span>Amount Payable Now (100% advance)</span>
             <span class="pay-amt">{_inr(due)}</span></div>
        <div class="pay-words">Amount Payable Now (in words) : {_amount_in_words(due)}</div>
      </div>"""

    # ── Bank block ────────────────────────────────────────────────────────
    # Shared with the RA bill through `docsheet.py`. Neither module imports the
    # other; both import the leaf. Only the note under it is this document's.
    bank_html = DS.bank_block(
        f"Please quote proforma invoice no.\n      "
        f"<b>{P.esc(pi.get('ref'))}</b> on the remittance advice.")

    note_html = ""
    if pi.get("notes"):
        note_html = (f'<div class="pi-note"><span class="pn-lbl">Note:</span> '
                     f'{P.esc(pi["notes"])}</div>')

    tnc_html = "".join(
        f'<li><span class="tnc-num">{i + 1}.</span><span>{t}</span></li>'
        for i, t in enumerate(_build_pi_terms(pi))
    )

    src_line = ""
    if pi.get("quotation_ref"):
        src_line = (f'<span class="ds-src"> &middot; against Quotation '
                    f'{P.esc(pi["quotation_ref"])}</span>')

    comp_br   = P.esc(pi.get("company_branch")) or B.COMPANY_NAME
    signatory = P.esc(pi.get("auth_signatory")) or P.esc(B.COMPANY_SIGNATORY)

    q_view = (url_for("quotation.view_quotation", id=pi["quotation_id"])
              if pi.get("quotation_id") in STORE["quotations"] else "")
    back_q = (f'<a href="{q_view}" class="btn btn-ghost">&#8592; Quotation '
              f'{P.esc(pi.get("quotation_ref"))}</a>' if q_view else "")

    # ── Onward to the tax invoice ─────────────────────────────────────────
    # Built from url_for plus a direct read of STORE["invoices"]. This module
    # must NOT import invoice.py — invoice.py imports this one (for the shared
    # stylesheet and _sel_keep), and a url_for string needs no import, which is
    # what keeps that arrow one-way. Same trick quotation.py uses to reach here.
    raised = sorted(
        ((iid, t) for iid, t in STORE["invoices"].items()
         if t.get("proforma_id") == id),
        key=lambda kv: kv[1].get("ref", ""),
    )
    ti_chips = "".join(
        f'<a class="ti-chip" href="{url_for("invoice.view_invoice", id=i_id)}">'
        f'{P.esc(t.get("ref"))}</a>'
        for i_id, t in raised
    )
    ti_strip = f'<div class="ti-strip">{ti_chips}</div>' if ti_chips else ""

    # The button stays available after the first invoice: a part supply is
    # invoiced in lots, so a second tax invoice against one PI is legitimate.
    # The convert form lists what already exists so the decision is informed —
    # the same contract the quotation's "Raise Proforma" button has.
    raise_ti = (f'<a href="{url_for("invoice.create_invoice", pid=id)}" class="btn">'
                f'&#129534;&nbsp;{"Raise Another Tax Invoice" if raised else "Raise Tax Invoice"}</a>')

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(pi.get('ref')) + " Proforma Invoice")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Proforma Invoice <span style="color:var(--brand);">{P.esc(pi.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;align-items:center;">
    {back_q}
    <a href="{url_for("proforma.list_proformas")}" class="btn btn-ghost">All Proformas</a>
    {raise_ti}
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>
{ti_strip}

{_alert(request.args.get("msg"), request.args.get("type", "success"))}

<div class="doc-outer">
<div class="quotation-doc">

{DS.sheet_open(show_gstin=False, show_branches=True)}

  <div class="doc-box">
    <div class="doc-title">PROFORMA INVOICE</div>
    <div class="doc-sub">This is not a Tax Invoice{src_line}</div>

    <div class="doc-header">
      <div class="dh-cell">
        <span class="dh-lbl">To</span>
        <div class="dh-body">{to_display}</div>
        {ship_html}
      </div>
      <div class="dh-cell">{meta_col_1}</div>
      <div class="dh-cell">{meta_col_2}</div>
    </div>

    <div class="items-wrap">
      <table class="q-table">
        <thead><tr>
          <th class="c-sno">S.No</th>
          <th class="c-partno">Part No</th>
          <th class="c-desc">Description of Goods</th>
          <th class="c-hsn">HSN/SAC</th>
          <th class="c-qty">Qty</th>
          <th class="c-unit">Unit</th>
          <th class="c-price">Unit Price</th>
          <th class="c-total">Total Price</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>

    <div class="amount-words">Invoice Value (in words) : {_amount_in_words(grand)}</div>
    {pay_box}
  </div>

  {bank_html}
  {note_html}

  <div class="tnc-section">
    <div class="tnc-title">Terms and Conditions</div>
    <ol class="tnc-ol">{tnc_html}</ol>
  </div>

  <div class="sig-block">
    <div class="sig-kv">
      <span>GSTIN</span><span>: <b>{B.field(B.COMPANY_GSTIN, "GSTIN")}</b></span>
      <span>PAN No.</span><span>: <b>{B.field(B.COMPANY_PAN, "PAN")}</b></span>
    </div>
    <div class="sig-right">
      <div class="sig-for">For {comp_br}</div>
      <div class="sig-name">{signatory}</div>
    </div>
  </div>
  <div class="sig-note">This is a Computer Generated Document, no signature required</div>

  </td></tr></tbody>
  </table>

</div>
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · proforma invoice</p>
</footer>
</main>
</body></html>"""
    return _page(template)
