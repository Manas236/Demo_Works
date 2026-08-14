"""
invoice.py — GST Tax Invoice Module
===================================
Blueprint  : invoice_bp
Mounted at : /invoice  (registered in app.py)

Routes
------
  GET       /invoice/              — register of issued tax invoices
  GET,POST  /invoice/from/<pid>    — raise a tax invoice from a proforma invoice
  GET       /invoice/view/<id>     — the printed tax invoice (Rule 46 document)

Why this is a separate document again, and not a PI render mode
---------------------------------------------------------------
The quotation is an offer. The proforma is a request for money. A **tax
invoice is a statutory record of a supply** — it creates the seller's GST
liability and it is the only document in this chain against which the customer
can claim input tax credit. Rule 46 of the CGST Rules, 2017 dictates most of
what is on its face, and the PI's own document says in as many words that it is
not this one. So it gets its own record, its own numbering series, and its own
set of mandatory fields.

What Rule 46 needs that a proforma never had to carry
-----------------------------------------------------
Three things, and they are the reason this module is not thin:

1. **HSN/SAC on every line.** Captured on the product now (`product.hsn`) and
   carried down the chain by `quotation._process_selections()`. A line without
   one prints as an amber chip rather than an empty cell — see `_hsn_cell()`.
2. **Place of supply, with its State code.** Not derivable from anything the PI
   stores, so it is asked for on the form and validated against `GST_STATE_CODES`.
   It is also what decides IGST vs CGST+SGST, so `_tax_warning()` checks the
   carried-over tax head against it rather than silently recomputing.
3. **A consecutive number, unique within the financial year, ≤ 16 characters.**
   `_next_ref()` is therefore FY-scoped — unlike `proforma._next_ref()`, which
   is only max+1 — and the FY is taken from the *invoice date*, not from today.

Goods invoices also go out in triplicate (Original for Recipient / Duplicate
for Transporter / Triplicate for Supplier). There is no PDF library here (the
"export" is the browser's own Print → Save as PDF), so the copy caption is a
render parameter: `?copy=original|duplicate|triplicate|all`.

What is reused, and from where
------------------------------
The printed sheet is still the quotation's sheet — `VIEW_DOC_STYLES` gives the
A4 frame, the repeating letterhead, the items table and every print rule, and
`_inr` / `_fmt_qty` / `_amount_in_words` / `_meta` are the document's own
formatters. `INVOICE_STYLES` layers after it and introduces no new font, type
size or border weight, exactly as `PROFORMA_STYLES` does. That restraint is why
all three documents look like they came out of the same office.

Import direction: invoice -> proforma -> quotation -> dashboard. Nothing
upstream imports this module; `proforma.py` links here with
`url_for("invoice.…")` and reads `STORE["invoices"]` directly, so no cycle
exists. Keep it that way.
"""

import uuid
from datetime import date as _date
from flask import Blueprint, request, redirect, url_for

import branding as B
import pipeline as P
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

# The same vocabularies both other forms offer, and the same widget builders.
# Shared rather than re-listed: a term one document offers and another does not
# is how the three start contradicting each other.
from quotation import _DISPATCH, _PAY_TERMS, _STATES_IN
from proforma import PROFORMA_STYLES, _sel_keep

invoice_bp = Blueprint("invoice", __name__, url_prefix="/invoice")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

# The document series. Rule 46 caps the whole invoice number at 16 characters,
# and "SF/TI/26-27/0001" is exactly 16 — so a longer COMPANY_SHORT would push it
# over. `_next_ref()` falls back to a short form rather than issuing an
# over-length number; see the comment there.
_REF_SERIES = "TI"

# Rule 46(b): the serial number must be unique for the *financial year*, which
# in India runs 1 April → 31 March, and is capped at 16 characters. The FY comes
# from the invoice date (not today), so back-dating into March files under the
# right year — see `pipeline.fy_of` / `pipeline.fy_ref`, which `purchase.py`
# shares.

# Whether the supply is taxable under reverse charge. Almost never true for a
# fire-protection contractor selling goods, so it defaults to No — but Rule 46
# requires the declaration to appear either way, so it always prints.
DEFAULT_REVERSE_CHARGE = False

# Goods move under three copies (Rule 48). Services need only two, but this
# company supplies equipment, so three is the default.
COPY_LABELS = {
    "original":   "ORIGINAL FOR RECIPIENT",
    "duplicate":  "DUPLICATE FOR TRANSPORTER",
    "triplicate": "TRIPLICATE FOR SUPPLIER",
}

# GST State codes — the first two digits of every GSTIN, and half of what
# "place of supply" means on the face of the invoice (Rule 46(n) wants the name
# *and* the code). Keys match `address.INDIAN_STATES` exactly, which is what
# lets the quotation's state dropdown feed straight into this.
# 
# ⚠ This table is duplicated in `pipeline.py`. `tests/test_gst_state_codes.py`
# asserts the two match.
GST_STATE_CODES = {
    "Jammu and Kashmir": "01", "Himachal Pradesh": "02", "Punjab": "03",
    "Chandigarh": "04", "Uttarakhand": "05", "Haryana": "06", "Delhi": "07",
    "Rajasthan": "08", "Uttar Pradesh": "09", "Bihar": "10", "Sikkim": "11",
    "Arunachal Pradesh": "12", "Nagaland": "13", "Manipur": "14",
    "Mizoram": "15", "Tripura": "16", "Meghalaya": "17", "Assam": "18",
    "West Bengal": "19", "Jharkhand": "20", "Odisha": "21",
    "Chhattisgarh": "22", "Madhya Pradesh": "23", "Gujarat": "24",
    "Dadra and Nagar Haveli and Daman and Diu": "26", "Maharashtra": "27",
    "Karnataka": "29", "Goa": "30", "Lakshadweep": "31", "Kerala": "32",
    "Tamil Nadu": "33", "Puducherry": "34",
    "Andaman and Nicobar Islands": "35", "Telangana": "36",
    "Andhra Pradesh": "37", "Ladakh": "38",
}

# Reverse lookup, for reading the supplier's own State out of its GSTIN.
_CODE_TO_STATE = {v: k for k, v in GST_STATE_CODES.items()}

# Place of supply only offers real States — "Other" is in the quotation's list
# for a foreign billing address, and a foreign supply is an export, which is a
# different document (LUT / bond, no IGST) that this app does not issue.
_POS_STATES = [s for s in _STATES_IN if s in GST_STATE_CODES]


# =============================================================================
# HELPERS
# =============================================================================

def _today() -> str:
    return _date.today().strftime("%Y-%m-%d")


# The financial-year helpers live in pipeline.py, not here: `purchase.py`
# numbers its POs the same way and the two pipelines must not import each
# other. See `pipeline.fy_of` for why that module is the safe home.
_fy_of = P.fy_of


def _next_ref(datestr: str) -> str:
    """
    Next tax invoice number — 'SF/TI/26-27/0001'.

    Two things this does that `proforma._next_ref()` does not, both because a
    tax invoice number is a statutory identifier rather than a convenience:

    * **It is scoped to the financial year.** Rule 46(b) requires the serial to
      be unique for the FY, and the series restarts at 0001 each April. Scanning
      only invoices in the same FY is what makes that true.
    * **It is max+1 within that FY**, so deleting a record never re-issues a
      number that has already been on a customer's document and in their GSTR-2B.

    Rule 46(b) also caps the whole thing at 16 characters. The standard form is
    exactly 16 with a two-letter COMPANY_SHORT; if the short name is longer the
    prefix is dropped rather than issuing an over-length number, because an
    invoice number the portal will reject is worse than an unbranded one.
    """
    fy = _fy_of(datestr)
    highest = 0
    for ti in STORE["invoices"].values():
        if ti.get("fy") != fy:
            continue
        tail = str(ti.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))

    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=16)


def _money(raw: str, default: float = 0.0) -> float:
    """Parse a rupee figure. Returns -1.0 to signal 'unparseable' to the caller."""
    txt = str(raw or "").strip().replace(",", "").replace("₹", "")
    if not txt:
        return default
    try:
        return float(txt)
    except ValueError:
        return -1.0


def _supplier_state() -> str:
    """
    The State we supply from, read out of the company GSTIN's first two digits.

    Derived rather than stored as a settings field: the GSTIN already carries it
    by construction, and two fields that must agree are two fields that can
    disagree. Returns '' when the GSTIN is blank or is the specimen template,
    in which case `_tax_warning()` simply stays quiet.
    """
    gstin = (B.COMPANY_GSTIN or "").strip()
    return _CODE_TO_STATE.get(gstin[:2], "") if len(gstin) >= 2 else ""


def _tax_warning(place_of_supply: str, tax_type: str) -> str:
    """
    Does the tax head carried over from the quotation match the place of supply?

    Intra-state supply attracts CGST+SGST; inter-state attracts IGST. The head
    was chosen by hand on the quotation, long before anyone stated a place of
    supply, so the two can genuinely disagree.

    This **warns and does not correct**. Silently switching the head would move
    the customer's total after they have already agreed a figure and, if the
    rates differ, change what they owe — that is a commercial decision, not a
    rounding fix. Returns '' when everything agrees or when there is nothing to
    compare against.
    """
    ours = _supplier_state()
    if not ours or not place_of_supply or tax_type not in ("cgst_sgst", "igst"):
        return ""

    intra = (place_of_supply == ours)
    if intra and tax_type == "igst":
        return (f"Place of supply is {place_of_supply}, the same State we supply "
                f"from, but the quotation charged IGST. An intra-State supply "
                f"attracts CGST + SGST.")
    if not intra and tax_type == "cgst_sgst":
        return (f"Place of supply is {place_of_supply} and we supply from "
                f"{ours}, so this is an inter-State supply — but the quotation "
                f"charged CGST + SGST. An inter-State supply attracts IGST.")
    return ""


def _customer_of(rec: dict) -> str:
    """First meaningful line of the customer identity, for list views."""
    name = (rec.get("account_name") or "").strip()
    if name:
        return name
    first = (rec.get("to") or "").strip().splitlines()
    return first[0].strip() if first else "—"


def _invoices_for(proforma_id: str) -> list:
    """Every tax invoice raised against one proforma, oldest number first."""
    out = [(iid, ti) for iid, ti in STORE["invoices"].items()
           if ti.get("proforma_id") == proforma_id]
    out.sort(key=lambda kv: kv[1].get("ref", ""))
    return out


def _missing_hsn(line_items: list) -> list:
    """
    Names of the lines that have no HSN/SAC, de-duplicated, order preserved.

    Rule 46(g) makes HSN mandatory, and a line without one costs the customer
    the input tax credit on it. This is deliberately **not** a blocking
    validation: there is no product edit route (ABOUT.md §7.2), so a user
    holding a legacy catalogue row could not clear the block even if they
    wanted to. The gap is surfaced instead — on the form as a warning naming
    the exact products, and on the printed sheet as an amber chip in the cell,
    which is this app's existing contract for a missing statutory detail.
    """
    seen, out = set(), []
    for r in line_items or []:
        if not str(r.get("hsn") or "").strip():
            nm = str(r.get("name") or "").strip() or "(unnamed line)"
            if nm not in seen:
                seen.add(nm)
                out.append(nm)
    return out


def _hsn_cell(code: str) -> str:
    """An HSN cell on the printed sheet — amber 'add HSN' chip when blank."""
    return B.field(str(code or "").strip(), "HSN")


def _build_ti_terms(ti: dict) -> list:
    """
    Terms and declarations that print on the tax invoice.

    Deliberately neither `quotation._build_tnc()` (written for an offer) nor
    `proforma._build_pi_terms()` (written for a payment request). What a tax
    invoice has to carry is different again: the statutory declarations, what
    the goods were supplied against, and the recourse if the customer disputes
    it. The reverse-charge declaration is not in this list — Rule 46(m) wants
    it on the face of the invoice, so it prints in the header grid.

    ⚠ Generic trade terms, **not checked against Samruddhi Fire's actual
    commercial policy** — the same caveat as the other two documents.
    """
    terms = []

    src = P.esc(ti.get("proforma_ref")).strip()
    if src:
        terms.append(
            f"Supplied against our Proforma Invoice {src}"
            + (f" dated {P.esc(ti['proforma_date'])}" if ti.get("proforma_date") else "")
            + (f", raised on Quotation {P.esc(ti['quotation_ref'])}"
               if ti.get("quotation_ref") else "")
            + ". The technical scope, exclusions and terms of that quotation "
              "continue to govern this supply in full."
        )

    po = P.esc(ti.get("po_number")).strip()
    if po:
        terms.append(
            f"Supplied against your Purchase Order {po}"
            + (f" dated {P.esc(ti['po_date'])}." if ti.get("po_date") else ".")
        )

    adv = float(ti.get("advance_received") or 0.0)
    if adv > 0:
        terms.append(
            "The advance shown above has already been received and is adjusted "
            "against this invoice. Only the net amount payable is now due."
        )

    terms += [
        "Goods once despatched will not be taken back or exchanged except "
        "against a written short-supply or damage claim raised within 7 days "
        "of receipt, supported by the transporter's remarks on the LR.",
        "Goods remain the property of the seller until payment has been "
        "realised in full, notwithstanding delivery or transfer of risk.",
        "Interest at 18% per annum is chargeable on any amount outstanding "
        "beyond the agreed credit period.",
        "A debit note of Rs 900.00 + GST will be raised each time a payment "
        "cheque is returned unpaid on presentation.",
        "Any statutory change in taxes, duties or levies applicable to this "
        "supply will be to the customer's account.",
        "Warranty, where applicable, runs from the date of this invoice and is "
        "limited to repair or replacement of the defective part. It does not "
        "cover consumables, wear parts, or damage from misuse or incorrect "
        "installation.",
        "Standard Force Majeure clause is applicable.",
        "Subject to Mumbai jurisdiction.",
    ]
    return terms


def _alert(msg: str, msg_type: str) -> str:
    if not msg:
        return ""
    icon = "&#10003;" if msg_type == "success" else "&#10007;"
    return f'<div class="alert alert-{msg_type}">{icon} {P.esc(msg)}</div>'


# =============================================================================
# CSS — tax-invoice-only additions
# =============================================================================
# Plain string, not an f-string, so the CSS braces are written once. Layered
# AFTER VIEW_DOC_STYLES and PROFORMA_STYLES and scoped inside .quotation-doc, so
# it inherits the document's type scale (--fs-*) and rule weights (--rule-*).
# Nothing here introduces a new font, size or border weight.

INVOICE_STYLES = """
<style>
  /* ── Copy caption ─────────────────────────────────────────────────────
     Goods move under three copies (Rule 48) and the recipient's copy has to be
     distinguishable from the transporter's at a glance, without reading it. It
     sits in the top-right of the frame, at the smallest step, because it
     labels the sheet rather than saying anything about the supply. */
  .quotation-doc .copy-mark {
    text-align:right; font-size:var(--fs-xs); font-weight:700;
    letter-spacing:.06em; padding:2px 6px; border-bottom:var(--rule-hair);
  }

  /* Each copy is a complete sheet of its own, so a fresh page starts at each
     one. `page-break-before` (not `break-before`) — Chrome's print path still
     honours the legacy property most reliably. */
  .quotation-doc + .quotation-doc { page-break-before:always; }

  /* ── The statutory declaration strip ──────────────────────────────────
     Rule 46(m) wants the reverse-charge status on the face of the invoice, and
     46(n) the place of supply with its State code. Both are read by the
     customer's accounts team before anything else on the page, so they get
     their own band under the header grid rather than being mixed into it. */
  .quotation-doc .gst-strip {
    display:flex; flex-wrap:wrap; gap:0 8mm;
    padding:2px 6px; border-bottom:var(--rule);
  }
  .quotation-doc .gst-strip .gs-l { color:var(--doc-soft); }
  .quotation-doc .gst-strip .gs-v { font-weight:700; }

  /* ── Payment settlement box ───────────────────────────────────────────
     Only rendered when an advance has actually been adjusted. When nothing was
     received the closing row of the items table is already the amount due, and
     printing the same figure twice invites the reader to hunt for a difference
     — the same reasoning as the PI's .pay-box. */
  .quotation-doc .set-box { border-top:var(--rule-box); }
  .quotation-doc .set-row {
    display:flex; justify-content:space-between; gap:6mm;
    padding:2px 6px; border-bottom:var(--rule-hair);
  }
  .quotation-doc .set-row:last-child { border-bottom:none; }
  .quotation-doc .set-amt { font-variant-numeric:tabular-nums; white-space:nowrap; }
  .quotation-doc .set-net {
    font-weight:700; font-size:var(--fs-md);
    border-top:var(--rule); border-bottom:var(--rule);
  }
  .quotation-doc .set-words {
    padding:2px 6px; font-weight:700; border-top:var(--rule-hair);
  }

  /* ── Despatch details ─────────────────────────────────────────────────
     Vehicle number and e-way bill belong to the movement of the goods, not to
     the money, so they sit apart from the header meta columns. */
  .quotation-doc .desp-box { border:var(--rule-box); margin-top:5mm; }
  .quotation-doc .desp-title {
    font-weight:700; font-size:var(--fs-md); padding:2px 6px;
    border-bottom:var(--rule);
  }
  .quotation-doc .desp-kv {
    display:grid; grid-template-columns:auto 1fr auto 1fr;
    gap:2px 6px; padding:4px 6px;
  }
  .quotation-doc .desp-kv .dk-l { color:var(--doc-soft); }
  .quotation-doc .desp-kv .dk-v { font-weight:700; overflow-wrap:anywhere; }

  /* The certification Rule 46 expects above the signature. */
  .quotation-doc .certify { padding:2px 6px; margin-top:4mm; }

  .quotation-doc .ti-note { margin-top:4mm; }
  .quotation-doc .ti-note .tn-lbl { font-weight:700; }

  @media screen and (max-width:760px){
    .quotation-doc .desp-kv { grid-template-columns:auto 1fr; }
  }

  /* ── Screen-only: the convert form, the register, the copy switcher ─── */

  /* Sub-label under a form input, for a field whose consequence is not obvious
     from its name. Restated here rather than imported because PRODUCT_STYLES,
     where the catalogue's copy of this rule lives, is not loaded on these
     pages — and neither sheet is the app's shared stylesheet (that is
     dashboard.BASE_STYLES, which every page already carries too much of). */
  .field-hint {
    display:block; margin-top:.35rem; font-size:.76rem;
    color:var(--muted); line-height:1.45; font-weight:400;
    text-transform:none; letter-spacing:0;
  }

  /* Segmented control for choosing which copy to print. Three sheets is a
     print-time concern, so it is a screen affordance and never prints. */
  .copy-switch { display:flex; gap:.4rem; flex-wrap:wrap; align-items:center; }
  .copy-switch .cs-lbl {
    font-size:.76rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:.05em; font-weight:600;
  }
  .copy-switch a {
    font-size:.76rem; font-weight:600; text-decoration:none;
    padding:.28rem .6rem; border-radius:7px;
    border:1px solid var(--border); color:var(--muted); background:var(--bg);
  }
  .copy-switch a.on { border-color:var(--brand); color:var(--brand); }
  @media print { .copy-switch { display:none; } }

  /* Warning panel — a compliance gap the user can see but this app cannot fix
     for them (a missing HSN, a tax head that disagrees with the place of
     supply). Amber, never red: nothing here is broken, but it must not go out
     unread. */
  .gst-warn {
    background:#FFF9EC; border:1px solid #F0DCA8; border-left:3px solid #C98A00;
    border-radius:var(--radius); padding:.9rem 1.2rem; margin-bottom:1.4rem;
    font-size:.86rem; line-height:1.55;
  }
  .gst-warn b { color:#8A5A00; }
  .gst-warn ul { margin:.45rem 0 0 1.1rem; }
  .gst-warn li { margin:.15rem 0; }

  .ti-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem;
    background:var(--navy-lt); color:var(--navy);
  }
  .ti-badge.paid { background:#E4F3E7; color:#1E6B2E; }
  .ti-badge.due  { background:#FFF4D6; color:#8A5A00; }

  /* .ti-strip / .ti-chip are defined in PROFORMA_STYLES — both this module and
     the proforma's view page render them, and every page here already loads
     that sheet. Same reasoning that puts .pi-chip in QUOTATION_STYLES one step
     upstream: the chip belongs to the sheet of the document it hangs off. */
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
# not braces, so an invoice whose `notes` reads `{{ config }}` prints the Flask
# config — including SECRET_KEY — onto a statutory document, and one reading
# `{% for x in y %}` raises a TemplateSyntaxError that 500s the page. Both are
# stored on the record, and a tax invoice has no edit route (ABOUT.md §7.3), so
# neither can be typed away afterwards.
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

@invoice_bp.route("/")
def list_invoices():
    """Register of every tax invoice issued, newest number first."""
    invoices = STORE["invoices"]
    rows = sorted(invoices.items(), key=lambda kv: kv[1].get("ref", ""), reverse=True)

    dash_url = url_for("dashboard.index")
    pi_url   = url_for("proforma.list_proformas")

    total_value = sum(float(ti.get("grand_total") or 0.0) for ti in invoices.values())
    total_tax   = sum(float((ti.get("tax_info") or {}).get("total") or 0.0)
                      for ti in invoices.values())
    total_net   = sum(float(ti.get("net_payable") or 0.0) for ti in invoices.values())

    tiles_html = ""
    if invoices:
        tiles_html = f"""
        <div class="pipe-tiles">
          <div class="pipe-tile t-open">
            <div class="pt-lbl">Invoiced Value</div>
            <div class="pt-val">&#8377;&nbsp;{total_value:,.0f}</div>
            <div class="pt-sub">{len(invoices)} tax invoice{"s" if len(invoices) != 1 else ""}</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Tax Charged</div>
            <div class="pt-val">&#8377;&nbsp;{total_tax:,.0f}</div>
            <div class="pt-sub">output GST on these invoices</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Outstanding</div>
            <div class="pt-val">&#8377;&nbsp;{total_net:,.0f}</div>
            <div class="pt-sub">net of advances adjusted</div>
          </div>
        </div>"""

    if rows:
        rows_html = ""
        for iid, ti in rows:
            view_url = url_for("invoice.view_invoice", id=iid)
            net      = float(ti.get("net_payable") or 0.0)
            badge    = ('<span class="ti-badge paid">settled</span>' if net <= 0
                        else f'<span class="ti-badge due">&#8377;&nbsp;{net:,.0f} due</span>')
            src_url  = url_for("proforma.view_proforma", id=ti.get("proforma_id", ""))
            rows_html += f"""
            <tr>
              <td class="td-ref">{P.esc(ti.get('ref'))}</td>
              <td class="td-muted">{P.esc(ti.get('date'))}</td>
              <td class="td-cust">{P.esc(_customer_of(ti))}</td>
              <td class="col-h"><a href="{src_url}" class="btn-view">{P.esc(ti.get('proforma_ref'))}</a></td>
              <td class="col-h">{P.esc(ti.get('place_of_supply'))}
                  <span class="td-muted">({P.esc(ti.get('pos_code'))})</span></td>
              <td class="td-muted">&#8377;&nbsp;{float(ti.get('grand_total') or 0):,.0f}</td>
              <td class="td-total">{badge}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>"""
        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Invoice No.</th><th>Date</th><th>Customer</th>
            <th class="col-h">From PI</th><th class="col-h">Place of Supply</th>
            <th>Invoice Value</th><th>Status</th><th></th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#129534;</div><br>
          <strong>No tax invoices yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            A tax invoice is raised from a proforma invoice at the time the goods
            are despatched &mdash; open the PI the customer has paid against and
            use <b>Raise Tax Invoice</b>.</p>
          <a href="{pi_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">
            Go to Proforma Register</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Tax Invoices")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{INVOICE_STYLES}</head>
    <body>{_nav()}
    <main>
      {_alert(request.args.get("msg"), request.args.get("type", "success"))}
      <div class="page-top">
        <h1>Tax <span>Invoices</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            {len(invoices)} issued
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{pi_url}"   class="btn btn-ghost">Proformas</a>
        </div>
      </div>
      {tiles_html}
      {table_html}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · tax invoice register</p></footer>
    </main></body></html>"""
    return _page(template)


@invoice_bp.route("/from/<pid>", methods=["GET", "POST"])
def create_invoice(pid: str):
    """
    Raise a GST tax invoice from a proforma invoice.

    Line items, prices and taxes are copied verbatim and are not editable here —
    the tax invoice states what was supplied against what was quoted, and a
    number that moves between the PI and the invoice is a number the customer's
    accounts department has to reconcile by hand.

    What is collected is what only the *supply* knows: when it happened, where
    it was supplied to (place of supply — the field that decides IGST vs
    CGST+SGST), how the goods moved, and how much of the value has already been
    received against the proforma.
    """
    pi = STORE["proformas"].get(pid)
    if not pi:
        return redirect(url_for("proforma.list_proformas",
                                msg="Proforma invoice not found.", type="error"))

    f     = request.form
    error = ""
    grand = float(pi.get("grand_total") or 0.0)

    if request.method == "POST":
        ti_date = (f.get("date") or "").strip()
        pos     = (f.get("place_of_supply") or "").strip()
        adv     = _money(f.get("advance_received"), 0.0)

        if not ti_date:
            error = "Invoice date is required."
        elif not pos:
            error = "Place of supply is required — it decides whether this supply attracts IGST or CGST + SGST."
        elif pos not in GST_STATE_CODES:
            error = f"'{pos}' is not a GST State. Pick one from the list."
        elif adv < 0:
            error = "Advance received must be a number, e.g. 125000."
        elif adv > grand:
            error = (f"Advance received (₹{adv:,.2f}) is more than the invoice "
                     f"value (₹{grand:,.2f}).")

        if not error:
            iid = str(uuid.uuid4())
            ti = {
                "id":  iid,
                "ref": _next_ref(ti_date),
                "fy":  _fy_of(ti_date),
                "date": ti_date,

                # ── Back-links. Both refs are stored, not looked up, so the
                #    invoice still prints correctly as a historical document if
                #    the PI or the quotation is ever removed.
                "proforma_id":    pid,
                "proforma_ref":   pi.get("ref", ""),
                "proforma_date":  pi.get("date", ""),
                "quotation_id":   pi.get("quotation_id", ""),
                "quotation_ref":  pi.get("quotation_ref", ""),

                # ── Customer identity, copied from the PI ─────────────────
                "account_name":   pi.get("account_name", ""),
                "contact_person": pi.get("contact_person", ""),
                "to":             pi.get("to", ""),
                "bill_gstin":     pi.get("bill_gstin", ""),
                "ship_same":      pi.get("ship_same", ""),
                "ship_acct_name": pi.get("ship_acct_name", ""),
                "ship_addr":      pi.get("ship_addr", ""),
                "ship_city":      pi.get("ship_city", ""),
                "ship_state":     pi.get("ship_state", ""),
                "ship_pin":       pi.get("ship_pin", ""),
                "ship_phone":     pi.get("ship_phone", ""),
                "ship_gstin":     pi.get("ship_gstin", ""),

                # ── Frozen commercial content ────────────────────────────
                # dict(row) per line, same as the PI: a shallow copy is enough
                # because every value in a line_item is a scalar, and it means a
                # later edit upstream cannot reach an issued tax invoice.
                "line_items":  [dict(r) for r in pi.get("line_items", [])],
                "subtotal":    float(pi.get("subtotal") or grand),
                "tax_type":    pi.get("tax_type", "exempt"),
                "tax_info":    dict(pi.get("tax_info") or {"total": 0.0}),
                "grand_total": grand,
                "total_qty":   pi.get("total_qty", 0),

                # ── Statutory fields this document is the first to carry ──
                "place_of_supply": pos,
                "pos_code":        GST_STATE_CODES[pos],
                "reverse_charge":  f.get("reverse_charge") == "1",

                # ── Settlement ────────────────────────────────────────────
                "advance_received": adv,
                "net_payable":      round(grand - adv, 2),

                # ── Movement of the goods ─────────────────────────────────
                "po_number":        (f.get("po_number") or "").strip(),
                "po_date":          (f.get("po_date") or "").strip(),
                "dispatch_through": (f.get("dispatch_through") or "").strip(),
                "dispatch_doc_no":  (f.get("dispatch_doc_no") or "").strip(),
                "vehicle_no":       (f.get("vehicle_no") or "").strip().upper(),
                "eway_bill_no":     (f.get("eway_bill_no") or "").strip(),
                "payment_terms":    (f.get("payment_terms") or "").strip(),
                "notes":            (f.get("notes") or "").strip(),

                "company_branch": pi.get("company_branch", ""),
                "auth_signatory": pi.get("auth_signatory", ""),
            }
            STORE["invoices"][iid] = ti

            # Invoicing the supply is the last real event in the deal's life, so
            # it belongs on the quotation's audit trail alongside the PI. Like
            # log_event elsewhere, it does not change the sales stage.
            q = STORE["quotations"].get(ti["quotation_id"])
            if q:
                P.log_event(q, f"Tax invoice {ti['ref']} raised for "
                               f"&#8377;{grand:,.0f} against {ti['proforma_ref']}.")

            return redirect(url_for("invoice.view_invoice", id=iid,
                                    msg=f"Tax invoice {ti['ref']} created.",
                                    type="success"))

    # ── Field values: the user's own input on a failed POST, else the PI's,
    #    else the module default. Same contract as proforma._v(). ────────────
    def _v(name: str, fallback: str = "") -> str:
        if request.method == "POST":
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    # Place of supply defaults to where the goods are actually going: the ship-to
    # State when it differs from billing, otherwise the source quotation's
    # billing State. The PI does not carry bill_state (it only keeps the
    # pre-joined `to` block), so the quotation is consulted for the fallback —
    # a convenience on the *form* only. Once posted, the answer is stored on the
    # invoice, so the document never depends on the quotation still existing.
    q_src = STORE["quotations"].get(pi.get("quotation_id", "")) or {}
    pos_default = ""
    if not pi.get("ship_same") and pi.get("ship_state"):
        pos_default = pi.get("ship_state", "")
    if pos_default not in GST_STATE_CODES:
        pos_default = q_src.get("bill_state", "")
    if pos_default not in GST_STATE_CODES:
        pos_default = ""

    v_date     = _v("date", _today())
    v_pos      = _v("place_of_supply", pos_default)
    v_po_no    = _v("po_number", pi.get("po_number", ""))
    v_po_date  = _v("po_date", pi.get("po_date", ""))
    v_adv      = _v("advance_received", f"{float(pi.get('amount_due') or 0.0):.2f}")
    v_dispatch = _v("dispatch_through", pi.get("dispatch_through", ""))
    v_doc_no   = _v("dispatch_doc_no")
    v_vehicle  = _v("vehicle_no")
    v_eway     = _v("eway_bill_no")
    v_pay      = _v("payment_terms", pi.get("payment_terms", ""))
    v_notes    = _v("notes")

    rc_checked = ("checked" if (f.get("reverse_charge") == "1"
                                if request.method == "POST"
                                else DEFAULT_REVERSE_CHARGE) else "")

    # ── Compliance warnings: things the user must see but this app will not
    #    silently "fix" on their behalf. ─────────────────────────────────────
    warn_bits = []

    gaps = _missing_hsn(pi.get("line_items", []))
    if gaps:
        items = "".join(f"<li>{P.esc(n)}</li>" for n in gaps)
        warn_bits.append(
            "<b>Missing HSN/SAC.</b> Rule 46 makes it mandatory on a tax invoice, "
            "and the customer cannot claim input tax credit on a line without it. "
            f"These lines have none:<ul>{items}</ul>"
            "Add the code on the product in the catalogue, then raise the "
            "quotation again — this invoice will print an amber chip in the "
            "cell rather than a blank."
        )

    tax_msg = _tax_warning(v_pos, pi.get("tax_type", "exempt"))
    if tax_msg:
        warn_bits.append(
            f"<b>Tax head may not match the place of supply.</b> {P.esc(tax_msg)} "
            "This is not corrected automatically, because changing the head "
            "changes what the customer owes after they have already agreed a "
            "figure. Raise a fresh quotation if the head is wrong."
        )

    warn_html = ""
    if warn_bits:
        warn_html = ('<div class="gst-warn">'
                     + "".join(f"<p>{b}</p>" for b in warn_bits)
                     + "</div>")

    # ── Frozen line-item preview ───────────────────────────────────────────
    rows_html = ""
    for r in pi.get("line_items", []):
        comp = " fz-comp" if r.get("depth", 0) == 1 else ""
        rows_html += f"""
        <tr class="{comp.strip()}">
          <td>{P.esc(r.get('name'))}</td>
          <td class="td-muted">{P.esc(r.get('part_no'))}</td>
          <td class="td-muted">{_hsn_cell(r.get('hsn'))}</td>
          <td class="fz-num">{_fmt_qty(float(r.get('qty') or 0))} {P.esc(r.get('unit'))}</td>
          <td class="fz-num">{_inr(r.get('price') or 0)}</td>
          <td class="fz-num">{_inr(r.get('total') or 0)}</td>
        </tr>"""

    tax_total = float((pi.get("tax_info") or {}).get("total") or 0.0)
    frozen_html = f"""
    <div class="frozen-wrap"><table>
      <thead><tr>
        <th>Description</th><th>Part No</th><th>HSN/SAC</th>
        <th class="fz-num">Qty</th><th class="fz-num">Rate</th><th class="fz-num">Amount</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr><td colspan="5" class="fz-num">Taxable Value</td>
            <td class="fz-num">{_inr(pi.get('subtotal') or grand)}</td></tr>
        <tr><td colspan="5" class="fz-num">Tax</td>
            <td class="fz-num">{_inr(tax_total)}</td></tr>
        <tr><td colspan="5" class="fz-num">Invoice Value</td>
            <td class="fz-num">{_inr(grand)}</td></tr>
      </tfoot>
    </table></div>
    <p class="frozen-hint">
      These lines are copied onto the tax invoice exactly as they were invoiced
      on the proforma, and are frozen at issue. To invoice different quantities
      or prices, raise a fresh quotation and proforma first.
    </p>"""

    existing = _invoices_for(pid)
    existing_html = ""
    if existing:
        chips = "".join(
            f'<a class="ti-chip" href="{url_for("invoice.view_invoice", id=i_id)}">'
            f'{P.esc(t.get("ref"))} &middot; &#8377;&nbsp;{float(t.get("grand_total") or 0):,.0f}</a>'
            for i_id, t in existing
        )
        existing_html = (f'<div class="ti-strip">{chips}</div>'
                         f'<div class="sn-sub">Already raised against this proforma — '
                         f'a second tax invoice for the same supply is a duplicate. '
                         f'Check before issuing another.</div>')

    pi_view = url_for("proforma.view_proforma", id=pid)

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Raise Tax Invoice")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{INVOICE_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Raise <span>Tax Invoice</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{pi_view}" class="btn btn-ghost">&#8592; Back to Proforma</a>
          <a href="{url_for("invoice.list_invoices")}" class="btn btn-ghost">All Tax Invoices</a>
        </div>
      </div>

      {_alert(error, "error")}

      <div class="src-note">
        From proforma <b>{P.esc(pi.get('ref'))}</b> dated {P.esc(pi.get('date'))}
        &middot; {P.esc(_customer_of(pi))}
        &middot; invoice value <b>&#8377;&nbsp;{grand:,.0f}</b>
        <div class="sn-sub">The invoice will be numbered {P.esc(_next_ref(v_date))}
          &mdash; consecutive within FY {P.esc(_fy_of(v_date))}, as Rule 46 requires.</div>
        {existing_html}
      </div>

      {warn_html}

      <form method="POST" action="{url_for("invoice.create_invoice", pid=pid)}">

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
                     placeholder="their PO number"/>
            </div>
            <div class="form-group">
              <label for="po_date">Customer PO Date</label>
              <input type="date" id="po_date" name="po_date" value="{P.esc(v_po_date)}"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">GST particulars</div>
          <div class="fg2">
            <div class="form-group">
              <label for="place_of_supply">Place of Supply *</label>
              {_sel_keep("place_of_supply", _POS_STATES, v_pos)}
              <small class="field-hint">The State where the goods are delivered.
                It decides IGST (inter-State) against CGST + SGST (intra-State),
                and prints with its GST State code.</small>
            </div>
            <div class="form-group">
              <label for="reverse_charge">Reverse Charge</label>
              <label style="display:flex;align-items:center;gap:.5rem;font-weight:500;
                            text-transform:none;letter-spacing:0;">
                <input type="checkbox" id="reverse_charge" name="reverse_charge"
                       value="1" {rc_checked} style="width:auto;"/>
                Tax is payable on reverse charge basis
              </label>
              <small class="field-hint">Rarely true on a sale of goods. The
                declaration prints either way — Rule 46 requires the status to
                appear on the face of the invoice.</small>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Settlement</div>
          <div class="adv-row">
            <div class="form-group" style="max-width:220px;">
              <label for="advance_received">Advance Already Received (&#8377;)</label>
              <input type="number" id="advance_received" name="advance_received"
                     value="{P.esc(v_adv)}" min="0" max="{grand:.2f}" step="0.01"/>
            </div>
            <div class="adv-out">
              Pre-filled with what {P.esc(pi.get('ref'))} asked for. Set it to 0 if
              nothing has actually been received — the invoice then shows the
              whole value as due.<br>
              Invoice value <b>&#8377;&nbsp;{grand:,.0f}</b>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Despatch</div>
          <div class="fg2">
            <div class="form-group">
              <label for="dispatch_through">Dispatch Through</label>
              {_sel_keep("dispatch_through", _DISPATCH, v_dispatch)}
            </div>
            <div class="form-group">
              <label for="dispatch_doc_no">LR / Docket No.</label>
              <input type="text" id="dispatch_doc_no" name="dispatch_doc_no"
                     value="{P.esc(v_doc_no)}" placeholder="transporter's consignment note"/>
            </div>
            <div class="form-group">
              <label for="vehicle_no">Vehicle No.</label>
              <input type="text" id="vehicle_no" name="vehicle_no"
                     value="{P.esc(v_vehicle)}" placeholder="e.g. MH 04 AB 1234"/>
            </div>
            <div class="form-group">
              <label for="eway_bill_no">E-Way Bill No.</label>
              <input type="text" id="eway_bill_no" name="eway_bill_no"
                     value="{P.esc(v_eway)}" placeholder="12 digits, where applicable"/>
            </div>
            <div class="form-group">
              <label for="payment_terms">Payment Terms</label>
              {_sel_keep("payment_terms", _PAY_TERMS, v_pay)}
            </div>
            <div class="form-group">
              <label for="notes">Note on the invoice <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <input type="text" id="notes" name="notes" value="{P.esc(v_notes)}"
                     placeholder="e.g. Part supply, first lot of two"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Items being invoiced &mdash; frozen at issue</div>
          {frozen_html}
        </div>

        <div class="form-actions">
          <button type="submit" class="btn">Raise Tax Invoice</button>
          <a href="{pi_view}" class="btn btn-ghost">Cancel</a>
        </div>
      </form>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · tax invoice</p></footer>
    </main></body></html>"""
    return _page(template)


@invoice_bp.route("/view/<id>")
def view_invoice(id: str):
    """
    The printed GST tax invoice.

    Same A4 sheet as the quotation and the proforma (VIEW_DOC_STYLES) — same
    letterhead band, same items table, same print rules. What differs is what
    Rule 46 requires and the other two never carried: the copy caption, the
    place of supply with its State code, the reverse-charge declaration, the
    per-line HSN, the despatch details and the certification above the
    signature.

    ``?copy=`` selects which of the three copies to render — ``original``
    (default), ``duplicate``, ``triplicate``, or ``all`` for one print run that
    produces the full set on three pages.
    """
    ti = STORE["invoices"].get(id)
    if not ti:
        return redirect(url_for("invoice.list_invoices",
                                msg="Tax invoice not found.", type="error"))

    copy_arg = (request.args.get("copy") or "original").lower()
    if copy_arg not in COPY_LABELS and copy_arg != "all":
        copy_arg = "original"
    copies = list(COPY_LABELS) if copy_arg == "all" else [copy_arg]

    # ── Line-item rows — same treatment as the other two documents, plus the
    #    HSN cell, which is the one column a tax invoice cannot leave blank.
    sno, total_qty, table_rows = 0, 0.0, ""
    for row in ti.get("line_items", []):
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
          <td class="c-hsn">{_hsn_cell(row.get('hsn'))}</td>
          <td class="c-qty">{_fmt_qty(float(row.get('qty') or 0))}</td>
          <td class="c-unit">{P.esc(row.get('unit'))}</td>
          <td class="c-price">{_inr(row.get('price') or 0)}</td>
          <td class="c-total">{_inr(row.get('total') or 0)}</td>
        </tr>"""

    subtotal = float(ti.get("subtotal") or ti.get("grand_total") or 0.0)
    tax_info = ti.get("tax_info") or {"total": 0.0}
    tax_type = ti.get("tax_type", "exempt")
    grand    = float(ti.get("grand_total") or 0.0)
    has_tax  = tax_type != "exempt" and float(tax_info.get("total") or 0) > 0

    # "Taxable Value", not "Subtotal": on a tax invoice this figure is the base
    # the tax was computed on, and that is the term the customer's accounts
    # team and the GST return both use for it.
    if has_tax:
        table_rows += f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">Taxable Value</td>
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
    meta_col_1 = (
        _meta("Tax Invoice No.",      P.esc(ti.get("ref"))) +
        _meta("Against Proforma",     P.esc(ti.get("proforma_ref"))) +
        _meta("Buyer's PO No.",       P.esc(ti.get("po_number"))) +
        _meta("Buyer's GSTIN",        P.esc(ti.get("bill_gstin"))) +
        _meta("Mode/Term of Payment", P.esc(ti.get("payment_terms")))
    )
    meta_col_2 = (
        _meta("Date",             P.esc(ti.get("date"))) +
        _meta("Proforma Date",    P.esc(ti.get("proforma_date"))) +
        _meta("Buyer's PO Date",  P.esc(ti.get("po_date"))) +
        _meta("Against Quotation", P.esc(ti.get("quotation_ref"))) +
        _meta("Dispatch Through", P.esc(ti.get("dispatch_through")))
    )

    # ── To / Ship To ──────────────────────────────────────────────────────
    to_lines   = (ti.get("to") or "").strip().split("\n")
    to_display = ""
    if to_lines and to_lines[0].strip():
        rest = "\n".join(to_lines[1:]).strip()
        to_display = f'<span class="dh-name">{P.esc(to_lines[0])}</span>'
        if rest:
            to_display += f"\n{P.esc(rest)}"

    ship_parts = []
    if not ti.get("ship_same"):
        sname = ti.get("ship_acct_name") or ti.get("account_name") or ""
        if sname:                 ship_parts.append(sname)
        if ti.get("ship_addr"):   ship_parts.append(ti["ship_addr"])
        scity = ", ".join(filter(None, [ti.get("ship_city", ""), ti.get("ship_state", "")]))
        if scity or ti.get("ship_pin"):
            ship_parts.append(f"{scity} – {ti.get('ship_pin', '')}".strip(" –"))
        if ti.get("ship_phone"):  ship_parts.append(f"Ph: {ti['ship_phone']}")
        if ti.get("ship_gstin"):  ship_parts.append(f"GSTIN: {ti['ship_gstin']}")

    ship_html = ""
    if ship_parts:
        ship_html = ('<div class="dh-ship"><span class="dh-lbl">Ship To</span>'
                     f'<div class="dh-body">{P.esc(chr(10).join(ship_parts))}</div></div>')

    # ── The statutory strip: Rule 46(m) and 46(n), on the face of the sheet ──
    pos      = P.esc(ti.get("place_of_supply"))
    pos_code = P.esc(ti.get("pos_code"))
    rc_txt   = "Yes" if ti.get("reverse_charge") else "No"
    gst_strip = f"""
    <div class="gst-strip">
      <span><span class="gs-l">Place of Supply:</span>
            <span class="gs-v">{pos or "&#8212;"}</span></span>
      <span><span class="gs-l">State Code:</span>
            <span class="gs-v">{pos_code or "&#8212;"}</span></span>
      <span><span class="gs-l">Tax payable on reverse charge basis:</span>
            <span class="gs-v">{rc_txt}</span></span>
    </div>"""

    # ── Settlement box ────────────────────────────────────────────────────
    # Only earns its space when an advance was actually adjusted. With nothing
    # received the closing row of the table already is the amount due.
    adv = float(ti.get("advance_received") or 0.0)
    net = float(ti.get("net_payable") or grand)

    if adv > 0:
        set_box = f"""
      <div class="set-box">
        <div class="set-row"><span>Total Invoice Value</span>
             <span class="set-amt">{_inr(grand)}</span></div>
        <div class="set-row"><span>Less: advance received against
             {P.esc(ti.get('proforma_ref')) or "proforma invoice"}</span>
             <span class="set-amt">{_inr(adv)}</span></div>
        <div class="set-row set-net"><span>Net Amount Payable</span>
             <span class="set-amt">{_inr(net)}</span></div>
        <div class="set-words">Net Amount Payable (in words) : {_amount_in_words(net)}</div>
      </div>"""
    else:
        set_box = ""

    # ── Despatch block ────────────────────────────────────────────────────
    # Rendered only when at least one detail was captured — an empty grid of
    # labels reads as an unfinished document, the same reason _meta() leaves a
    # blank value blank rather than printing an em-dash.
    desp_fields = [
        ("Dispatch Through", ti.get("dispatch_through")),
        ("LR / Docket No.",  ti.get("dispatch_doc_no")),
        ("Vehicle No.",      ti.get("vehicle_no")),
        ("E-Way Bill No.",   ti.get("eway_bill_no")),
    ]
    desp_html = ""
    if any(str(v or "").strip() for _l, v in desp_fields):
        kv = "".join(
            f'<span class="dk-l">{lbl}</span><span class="dk-v">{P.esc(val) or "&#8212;"}</span>'
            for lbl, val in desp_fields
        )
        desp_html = f"""
      <div class="desp-box">
        <div class="desp-title">Despatch Details</div>
        <div class="desp-kv">{kv}</div>
      </div>"""

    note_html = ""
    if ti.get("notes"):
        note_html = (f'<div class="ti-note"><span class="tn-lbl">Note:</span> '
                     f'{P.esc(ti["notes"])}</div>')

    tnc_html = "".join(
        f'<li><span class="tnc-num">{i + 1}.</span><span>{t}</span></li>'
        for i, t in enumerate(_build_ti_terms(ti))
    )

    comp_br   = P.esc(ti.get("company_branch")) or B.COMPANY_NAME
    signatory = P.esc(ti.get("auth_signatory")) or B.COMPANY_SIGNATORY

    # ── One complete sheet per copy ───────────────────────────────────────
    def _sheet(copy_key: str) -> str:
        """The whole A4 document, captioned for one of the three copies."""
        return f"""
<div class="quotation-doc">

  <table class="page-frame">
  <thead><tr><td>
    <div class="lh">
      <div>
        <div class="lh-name">{B.name_html("lh-name-fire")}</div>
        <div class="lh-tag">&#8212; {B.COMPANY_TAGLINE} &#8212;</div>
        {f'<div class="lh-legal">{B.COMPANY_LEGAL}</div>' if B.COMPANY_LEGAL else ''}
      </div>
      <div class="lh-mark">{B.logo_img(56, doc=True)}</div>
    </div>
    <div class="lh-rule"></div>
    <div class="lh-addr">Registered Address: {B.field(B.COMPANY_ADDR, "registered address")}</div>
    <div class="lh-contact">
      Phone: {B.field(B.COMPANY_PHONE, "phone")}<span class="sep">|</span>
      Email: {B.field(B.COMPANY_EMAIL, "e-mail")}
      {f'<span class="sep">|</span>Web: {B.COMPANY_WEB}' if B.COMPANY_WEB else ''}
      {f'<span class="sep">|</span>GSTIN: {B.COMPANY_GSTIN}' if B.COMPANY_GSTIN else ''}
    </div>
  </td></tr></thead>

  <tfoot><tr><td>
    <div class="lh-foot">{B.COMPANY_LEGAL or B.COMPANY_NAME} &middot; {B.COMPANY_TAGLINE}</div>
  </td></tr></tfoot>

  <tbody><tr><td>

  <div class="doc-box">
    <div class="copy-mark">{COPY_LABELS[copy_key]}</div>
    <div class="doc-title">TAX INVOICE</div>

    <div class="doc-header">
      <div class="dh-cell">
        <span class="dh-lbl">To</span>
        <div class="dh-body">{to_display}</div>
        {ship_html}
      </div>
      <div class="dh-cell">{meta_col_1}</div>
      <div class="dh-cell">{meta_col_2}</div>
    </div>

    {gst_strip}

    <div class="items-wrap">
      <table class="q-table">
        <thead><tr>
          <th class="c-sno">S.No</th>
          <th class="c-partno">Part No</th>
          <th class="c-desc">Description of Goods</th>
          <th class="c-hsn">HSN/SAC</th>
          <th class="c-qty">Qty</th>
          <th class="c-unit">Unit</th>
          <th class="c-price">Rate</th>
          <th class="c-total">Amount</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>

    <div class="amount-words">Invoice Value (in words) : {_amount_in_words(grand)}</div>
    {set_box}
  </div>

  {desp_html}
  {note_html}

  <div class="tnc-section">
    <div class="tnc-title">Terms and Conditions</div>
    <ol class="tnc-ol">{tnc_html}</ol>
  </div>

  <div class="certify">Certified that the particulars given above are true and
    correct, and that the amount indicated represents the price actually charged
    and that there is no flow of additional consideration directly or indirectly
    from the buyer.</div>

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

  </td></tr></tbody>
  </table>

</div>"""

    sheets_html = "".join(_sheet(c) for c in copies)

    # ── Screen chrome ─────────────────────────────────────────────────────
    def _copy_link(key: str, label: str) -> str:
        on = "on" if copy_arg == key else ""
        return (f'<a class="{on}" '
                f'href="{url_for("invoice.view_invoice", id=id, copy=key)}">{label}</a>')

    copy_switch = (
        '<div class="copy-switch"><span class="cs-lbl">Copy</span>'
        + _copy_link("original", "Original")
        + _copy_link("duplicate", "Duplicate")
        + _copy_link("triplicate", "Triplicate")
        + _copy_link("all", "All 3")
        + "</div>"
    )

    pi_view = (url_for("proforma.view_proforma", id=ti["proforma_id"])
               if ti.get("proforma_id") in STORE["proformas"] else "")
    back_pi = (f'<a href="{pi_view}" class="btn btn-ghost">&#8592; Proforma '
               f'{P.esc(ti.get("proforma_ref"))}</a>' if pi_view else "")

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(ti.get('ref')) + " Tax Invoice")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{INVOICE_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Tax Invoice <span style="color:var(--brand);">{P.esc(ti.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;align-items:center;">
    {copy_switch}
    {back_pi}
    <a href="{url_for("invoice.list_invoices")}" class="btn btn-ghost">All Tax Invoices</a>
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>

{_alert(request.args.get("msg"), request.args.get("type", "success"))}

<div class="doc-outer">
{sheets_html}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · tax invoice</p>
</footer>
</main>
</body></html>"""
    return _page(template)
