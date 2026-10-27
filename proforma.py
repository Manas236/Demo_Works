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
  GET,POST  /proforma/pictures/<id> — a picture beside each line (21 Oct 2026)
  GET,POST  /proforma/from-boq/<id> — raise a proforma invoice from a BOQ
                                      (22 Oct 2026 — see RAISED FROM A BOQ)

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

From 22 October 2026 also proforma -> boq and proforma -> boqpick, for a PI
raised FROM a bill of quantities — `purchase.py`'s arrow (ABOUT.md §2f), for
its reason: a module owns the shape it writes, and the PI belongs in the PI
series. `boq.py` must never import this module; `/boq/view` links here with
`url_for` and reads `STORE["proformas"]` directly.
"""

import uuid
from datetime import date as _date
from flask import Blueprint, request, redirect, url_for

import boq as BQ        # the schedule a PI is raised FROM (22 Oct 2026) — §2f's arrow
import boqpick as BP    # the BOQ line picker, at its FOURTH and FIFTH consumers
import branding as B
import cascade
import lineimage as LI   # pictures beside a line — the leaf (21 Oct 2026)
import pipeline as P
import series as SER   # the document-number FLOOR and the one scan per series (25 Sep 2026)
import docnum as DN    # the MANUAL document number, forward only (27 Oct 2026)
import docsheet as DS
from chrome import BASE_STYLES, _nav
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

    ⚠ **The scan moved to `series.py` on 25 September 2026 and the rule gained
      a FLOOR** (ABOUT.md §7 gap 36) — `max(existing max + 1, floor)`,
      byte-identical with no floor set. This is the one series in the registry
      whose scope is **the whole series** rather than a financial year, exactly
      because it does not reset: its floor is filed under
      `series.GLOBAL_SCOPE` and never expires. `_ref_num()` is kept and is
      still what orders the register; the leaf's `WHOLE` mode is the same
      split on `-`.
    """
    return _ref_for(SER.next_seq("PI", ""))


def _ref_for(seq: int) -> str:
    """
    The proforma number for one ORDINAL — the shape, without the counter.

    Split out of `_next_ref()` on 27 October 2026 (CLIENT_CHANGES.md §0's
    fifty-fourth block) so a number the operator typed is spelled by exactly
    the same code as one the series minted. Two spellings of one number is how
    a typed `50` becomes `PI-50` on a document the customer files a payment
    against.
    """
    return f"{_REF_PREFIX}-{int(seq):04d}"


def _may_set_number() -> bool:
    """
    May this user type a document number? The function-body `import auth` is
    the hatch `view_proforma()` already takes for `can_reach()`.
    """
    import auth as _AUTH
    return _AUTH.has_perm("docnum.override")


def _actor_id() -> str:
    """The id of whoever is saving — never their display name (gap 41)."""
    import auth as _AUTH
    return str((_AUTH.current_user() or {}).get("id") or "")


def _number_control(typed: str, may: bool) -> tuple:
    """
    `(default_seq, control_html)` for the proforma's number field.

    ⚠ **No skip note.** That is the tax invoice's, and only the tax invoice's
    — a gap in the PI series is nobody's business but ours, while a gap in a
    tax invoice series shows in the *documents issued* table of a GSTR-1.
    §0's fifty-fourth block, item A point 6.
    """
    seq = SER.next_seq("PI", "")
    return seq, DN.number_field(DN.PI, _ref_for(seq), may_override=may,
                                typed=typed)


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

    ⚠ **Every option is escaped HERE** (22 October 2026), because
      `quotation._sel_opts()` interpolates option text raw and `quotation.py`
      is frozen. The prepended value is a stored record's text — a BOQ's
      free-text payment terms reach the PI and TI raised from it this way —
      so it is user input on its way into HTML. No value in the five shared
      vocabularies changes under `P.esc` (checked when this was written), so
      every form that only ever offered those renders byte for byte as before;
      the browser posts the decoded text, so the value round-trips unchanged.
    """
    cur = (current or "").strip()
    opts = list(options)
    if cur and cur not in opts:
        opts.insert(0, cur)
    opts = [P.esc(o) for o in opts]
    cur = P.esc(cur)
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
    boq_src = P.esc(pi.get("boq_ref")).strip()
    if src:
        terms.append(
            f"This proforma invoice is raised against our Quotation {src}"
            + (f" dated {P.esc(pi['quotation_date'])}." if pi.get("quotation_date") else ".")
            + " The technical scope, exclusions and terms of that quotation "
              "continue to govern this supply in full."
        )
    elif boq_src:
        # Raised from a schedule (22 October 2026). Only such a PI says this.
        terms.append(
            f"This proforma invoice is raised against our Bill of Quantities "
            f"{boq_src}. The specifications, quantities and terms of that "
            f"schedule continue to govern this work in full; quantities are "
            f"provisional and billed as executed."
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
# RAISED FROM A BOQ — 22 October 2026
# =============================================================================
# CLIENT_CHANGES.md §0, fifty-first block. The client wants every document
# raised from the schedule, "even TI". The proforma invoice and the tax invoice
# raised from a BOQ are the ORDINARY documents — the same collection, the same
# PI-nnnn / SF/TI/yy-yy/nnnn series, the same printed sheet — so they are
# written here and in `invoice.py`, which own those shapes, and not in a third
# module that would need a third number series. `purchase.from_boq()` set the
# precedent (ABOUT.md §2f); `invoice.py` imports what follows from here, the
# arrow it already had.
#
# What a BOQ gives a sell-side line that a quotation never did:
#
#   * **Two tracks.** Every BOQ line is priced to SUPPLY and to INSTALL, each
#     with its own code (supply HSN, installation SAC) and its own GST rate.
#     The operator chooses Supply, Installation, or both — the RA bill's three
#     types. "Both" STACKS the two, supply rows first, each leg under its own
#     band row — the merged RA's arrangement, and the reason a line is never
#     collapsed to one combined rate: one row would carry one code, and goods
#     and the service that installs them are taxed under two.
#   * **Specification headers.** A size line ("150mm dia") means nothing
#     without the clause above it, so the clause comes across as a heading row
#     carrying no money — the purchase order's rule (`_po_lines_from_picked()`).
#   * **Per-line GST rates**, so the tax is computed per RATE SLAB and rounded
#     once per slab — `ra.compute_tax_totals()`'s rule — and a document with
#     two slabs prints one tax row per slab rather than one wrong rate.
#
# ⚠ **The rate is the schedule's SELLING rate** (`supply_rate` /
#   `install_rate`) and is not editable — the document states what was agreed,
#   exactly as a PI from a quotation states what was quoted. The QUANTITY is
#   the operator's, defaulting to the schedule's: a PI may ask for a lot.
# ⚠ **The tax head is CHOSEN on the form, never derived** (CLIENT_CHANGES.md
#   §1.5): CGST + SGST by default, the RA bill's default. The tax invoice's own
#   form warns when it disagrees with the place of supply, as it always has.

BOQ_LEGS = (("supply", "Supply"),
            ("installation", "Installation"),
            ("both", "Supply &amp; Installation"))

BOQ_TAX_HEADS = (("cgst_sgst", "CGST + SGST (intra-State)"),
                 ("igst", "IGST (inter-State)"))

# leg -> (rate field, code field, GST-rate field, band label)
_LEG_FIELDS = {
    "supply":       ("supply_rate",  "supply_hsn",  "supply_gst_rate",  "SUPPLY"),
    "installation": ("install_rate", "install_sac", "install_gst_rate", "INSTALLATION"),
}

# A BOQ line with no GST rate is taxed at this — `ra.build_claim()`'s fold of a
# falsy BOQ rate, for its reason: a blank on the schedule is "not stated",
# never "nil-rated".
_BOQ_DEFAULT_GST = 18.0


def boq_leg(raw) -> str:
    """The leg off a form or a query string; anything unknown is Supply."""
    raw = str(raw or "").strip().lower()
    return raw if raw in dict(BOQ_LEGS) else "supply"


def boq_tax_head(raw) -> str:
    """The tax head off a form; anything unknown is CGST + SGST."""
    raw = str(raw or "").strip().lower()
    return raw if raw in dict(BOQ_TAX_HEADS) else "cgst_sgst"


def boq_leg_label(leg: str) -> str:
    """'Supply', 'Installation' or 'Supply &amp; Installation' — markup-safe."""
    return dict(BOQ_LEGS).get(leg, "")


def _heading_item(name: str, part_no: str = "", line_id: str = "",
                  band: str = "") -> dict:
    """A row that carries words and no money — a spec clause or a leg band."""
    row = {"type": "item", "is_header": True, "line_id": line_id,
           "name": name, "part_no": part_no, "hsn": "",
           "qty": 0.0, "unit": "", "price": 0.0, "total": 0.0, "depth": 0}
    if band:
        row["leg_band"] = band
    return row


def boq_line_items(picked: list, boq: dict, leg: str) -> tuple:
    """
    `(line_items, error)` — `boqpick.picked_lines()` rows in the sell chain's
    line shape, for one leg or both.

    Snapshotted here and now, as every document raised from a schedule is: the
    printed PI or TI never re-reads the BOQ (CLIENT_CHANGES.md §1.2).

    A ticked line that is **not priced on a leg** is left off that leg — an
    installation-only line has no supply row, and a 0.00 row on an invoice says
    the thing was free. A clause heading prints only above a line that made it
    onto the leg. Matching is on `line_id` alone (§1.4).
    """
    lines = boq.get("line_items") or []
    by_lid, head_lid = {}, {}
    heads = BQ.header_of(lines)
    for i, li in enumerate(lines):
        lid = BQ._line_id(li.get("line_id"))
        if not lid:
            continue
        by_lid[lid] = li
        if i in heads:
            head_lid[lid] = BQ._line_id(lines[heads[i]].get("line_id"))

    parts = ("supply", "installation") if leg == "both" else (leg,)
    out, priced = [], 0
    for part in parts:
        rate_f, code_f, gst_f, band = _LEG_FIELDS[part]
        rows, last_head = [], None
        for row in picked:
            if row.get("is_header"):
                continue
            lid = str(row.get("line_id") or "")
            src = by_lid.get(lid) or {}
            # ⚠ Merge of 23 October 2026: the line is billed at its NET rate —
            #   `boq.net_rate()`, the one price of a line on the office line's
            #   forty-fourth block (R3) — never the unit rate before discount.
            #   An undiscounted line's net rate IS its unit rate, untouched; a
            #   blank rate (an as-is BOQ, A4) is `None` and the line is left off
            #   this leg, as an unpriced line always was here. `rate_f` stays the
            #   field that says which leg a line is priced on.
            net = BQ.net_rate(src, part)
            rate = 0.0 if net is None else float(net)
            if rate <= 0:
                continue
            qty = float(row.get("qty") or 0.0)
            if qty <= 0:
                return [], (f"Quantity for item {row.get('item_no') or '(unnumbered)'} "
                            f"must be greater than zero.")
            hid = head_lid.get(lid)
            if hid and hid != last_head and hid in by_lid:
                h = by_lid[hid]
                rows.append(_heading_item(str(h.get("description") or ""),
                                          BQ._item_no(h.get("item_no")), hid))
                last_head = hid
            rows.append({
                "type": "item", "is_header": False,
                "line_id": lid,      # THE key back to the schedule line
                "leg": part,
                "name": str(row.get("description") or ""),
                "part_no": str(row.get("item_no") or ""),
                "hsn": str(src.get(code_f) or ""),
                "gst_rate": float(src.get(gst_f) or _BOQ_DEFAULT_GST),
                "qty": qty,
                "unit": str(row.get("unit") or ""),
                "price": rate,
                "total": round(qty * rate, 2),
                "depth": 0,
            })
            priced += 1
        if rows:
            out.append(_heading_item(band, band=part))
            out.extend(rows)

    if not priced:
        return [], (f"None of the ticked lines carries a "
                    f"{boq_leg_label(leg).replace('&amp;', '&').lower()} rate on "
                    f"this schedule, so there is nothing to invoice. Choose "
                    f"another leg, or tick priced lines.")
    return out, ""


def boq_figures(items: list, tax_type: str) -> tuple:
    """
    `(subtotal, tax_info, grand_total, total_qty)` for BOQ-raised lines.

    Taxed **per rate slab**, rounded once per slab and then summed —
    `ra.compute_tax_totals()`'s rule 2, so every printed tax row foots. The
    `tax_info` dict is the sell chain's own shape, which the PI and TI sheets
    print row by row: one slab gives `CGST` / `SGST` (or `IGST`) with their
    rates, exactly what a quotation stores; two or more give one key per head
    per slab — `CGST @ 9%` — because a single "CGST @ 9%" over a 6% line is a
    tax invoice stating a rate it did not charge.
    """
    slabs = {}
    total_qty = 0.0
    for r in items:
        if r.get("is_header"):
            continue
        rate = float(r.get("gst_rate") or 0.0)
        slabs[rate] = slabs.get(rate, 0.0) + float(r.get("total") or 0.0)
        total_qty += float(r.get("qty") or 0.0)
    subtotal = round(sum(slabs.values()), 2)

    tax_info, total = {}, 0.0
    one = len(slabs) == 1
    for rate in sorted(slabs):
        taxable = slabs[rate]
        if tax_type == "igst":
            amt = round(taxable * rate / 100.0, 2)
            tax_info["IGST" if one else f"IGST @ {rate:g}%"] = amt
            total += amt
        else:
            half = round(taxable * rate / 200.0, 2)
            tax_info["CGST" if one else f"CGST @ {rate / 2:g}%"] = half
            tax_info["SGST" if one else f"SGST @ {rate / 2:g}%"] = half
            total += 2 * half
    if one:
        rate = next(iter(slabs))
        if tax_type == "igst":
            tax_info["igst_rate"] = rate
        else:
            tax_info["cgst_rate"] = rate / 2
            tax_info["sgst_rate"] = rate / 2
    tax_info["total"] = round(total, 2)
    grand = round(subtotal + tax_info["total"], 2)
    return subtotal, tax_info, grand, total_qty


def boq_customer(boq: dict) -> dict:
    """The schedule's customer block, copied — the fields a PI and a TI carry."""
    keys = ("account_name", "contact_person", "to", "bill_gstin", "ship_same",
            "ship_acct_name", "ship_addr", "ship_city", "ship_state", "ship_pin",
            "ship_phone", "ship_gstin")
    return {k: boq.get(k, "") for k in keys}


def boq_project_id(boq: dict) -> str:
    """
    The project the document inherits from its BOQ — **stored, never
    derived**, `purchase._project_of_boq()`'s rule: a BOQ with no live project
    gives none, and never falls back to its free-text `project_name`.
    """
    pid = str(boq.get("project_id") or "")
    return pid if pid in (STORE.get("projects") or {}) else ""


def boq_chain(boq_id: str) -> set:
    """The BOQ and every revision it supersedes — "same project" here."""
    return BQ._ancestor_ids(boq_id) | {boq_id}


def boq_replay(raw: str) -> tuple:
    """`(chosen, qty_of)` off a rejected POST, so no tick or quantity is lost."""
    import json
    try:
        rows = (json.loads(raw or "{}").get("lines") or [])
    except (ValueError, TypeError, AttributeError):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    return ({BQ._line_id(r.get("line_id")) for r in rows},
            {BQ._line_id(r.get("line_id")): r.get("qty") for r in rows})


def boq_choice_html(leg: str, tax_type: str) -> str:
    """The leg and the tax head, as two rows of radio pills."""
    legs = "".join(
        f'<label><input type="radio" name="leg" value="{k}"'
        f'{" checked" if k == leg else ""}/> {lbl}</label>'
        for k, lbl in BOQ_LEGS)
    heads = "".join(
        f'<label><input type="radio" name="tax_type" value="{k}"'
        f'{" checked" if k == tax_type else ""}/> {lbl}</label>'
        for k, lbl in BOQ_TAX_HEADS)
    return f"""
          <div class="form-group">
            <label>What is being invoiced *</label>
            <div class="leg-pick">{legs}</div>
            <small class="field-hint">Supply and Installation are each priced on
              the schedule with their own HSN / SAC and GST rate. Both prints the
              two stacked &mdash; supply first, then installation &mdash; as the
              merged RA does. A ticked line not priced for a leg is left off it.</small>
          </div>
          <div class="form-group">
            <label>Tax head *</label>
            <div class="leg-pick">{heads}</div>
          </div>"""


def boq_grid(boq: dict, chosen, qty_of, payload_id: str, doc_word: str) -> str:
    """`boqpick`'s grid, in this document's words."""
    return BP.grid_html(
        boq,
        title="Lines to invoice",
        intro_html=f"""        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line is ticked to start with. Untick what this {doc_word} does not
          cover, and lower a quantity to invoice part of a line. The rate is the
          schedule&rsquo;s own and is not edited here.
        </p>""",
        qty_label="Invoice qty",
        qty_aria="Invoice quantity",
        empty_note=(f"Nothing is ticked. A {doc_word} with no lines on it is "
                    f"not a document."),
        payload_id=payload_id,
        doc_word=doc_word,
        chosen=chosen,
        qty_of=qty_of)


def boq_heading_row(row: dict, img_td: str = "") -> str:
    """
    A clause or a leg band on the printed sheet: words, no S.No and no figures.

    Only a document raised from a BOQ carries one, so every other PI and TI
    renders exactly the rows it always did.
    """
    name = P.esc(row.get("name"))
    if row.get("leg_band"):
        name = f"<b>{name}</b>"
    return f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>{img_td}
          <td class="c-desc">{name}</td>
          <td class="c-hsn"></td>
          <td class="c-qty"></td>
          <td class="c-unit"></td>
          <td class="c-price"></td>
          <td class="c-total"></td>
        </tr>"""


# The picker's stylesheet, wrapped for the two from-BOQ forms, plus the pills.
# A separate constant and never part of PROFORMA_STYLES, which the printed PI
# and both registers load and the goldens hash.
FROM_BOQ_FORM_STYLES = "\n<style>\n" + BP.PICKER_CSS + """
  .leg-pick { display:flex; flex-wrap:wrap; gap:.5rem; }
  .leg-pick label {
    display:flex; align-items:center; gap:.4rem; margin:0;
    padding:.45rem .8rem; border:1px solid var(--border); border-radius:8px;
    cursor:pointer; font-weight:600; text-transform:none; letter-spacing:0;
  }
  .leg-pick input { width:auto; margin:0; }
  .boq-dup {
    background:#FFF8E6; border:1px solid #E8C86A; border-left:3px solid #C79200;
    border-radius:8px; padding:.7rem .9rem; margin:0 0 1rem; font-size:.84rem;
  }
</style>
"""


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
            src_txt  = P.esc(pi.get('quotation_ref'))
            # Raised from a schedule (22 October 2026): the cell names the BOQ
            # and links to it. Every other row renders exactly as before.
            if pi.get("boq_id") and not pi.get("quotation_id"):
                src_url = url_for("boq.view_boq", id=pi.get("boq_id"))
                src_txt = f"BOQ {P.esc(pi.get('boq_ref'))}"
            rows_html += f"""
            <tr>
              <td class="td-ref">{P.esc(pi.get('ref'))}</td>
              <td class="td-muted">{P.esc(pi.get('date'))}</td>
              <td class="td-cust">{P.esc(_customer_of(pi))}</td>
              <td class="col-h"><a href="{src_url}" class="btn-view">{src_txt}</a></td>
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
            customer has agreed to and use <b>Raise Proforma</b> — or from a bill
            of quantities, with <b>+ Proforma Invoice</b> on the BOQ.</p>
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
    may_number = _may_set_number()
    seq_used = default_seq = 0

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

        # ⚠ **In the SAVE path, never on a GET** — §0's fifty-fourth block,
        #   item A point 9.
        if not error:
            default_seq = SER.next_seq("PI", "")
            seq_used, num_err = DN.validate(DN.PI, "", f.get("doc_no_seq"),
                                            default_seq, may_number)
            error = error or num_err

        if not error:
            pid = str(uuid.uuid4())
            pi = {
                "id":  pid,
                "ref": _ref_for(seq_used),
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
            # ── Pictures: the library's, by default (21 October 2026) ──────
            # A line written from a spec-library clause carries the clause's
            # code as its part_no; where that clause has a picture, the line
            # gets it — onto the PI's own COPY of the line, never the
            # quotation's. Only a blank is filled. Changing or removing one
            # is the PI's Pictures page; the figures above are untouched.
            LI.fill_from_library(pi["line_items"])
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

            DN.note_used(DN.PI, "", seq_used)
            DN.record_override(pi, _ref_for(default_seq), pi["ref"],
                               _actor_id())

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
    # The picture each line will carry, drawn as a first column ONLY when at
    # least one line will carry one — the library's for its code, the rule
    # `create_proforma()` applies on POST (21 October 2026).
    pic_of = [LI.image_of(r) or LI.library_image_for(r.get("part_no"))
              for r in q.get("line_items", [])]
    with_pics = any(LI.src_of(i) for i in pic_of)
    rows_html = ""
    for r, pic in zip(q.get("line_items", []), pic_of):
        comp = " fz-comp" if r.get("depth", 0) == 1 else ""
        pic_cell = ""
        if with_pics:
            src = LI.src_of(pic)
            pic_cell = ('<td style="width:56px;">'
                        + (f'<img src="{src}" alt="" style="max-width:48px;'
                           f'max-height:48px;object-fit:contain;display:block;"/>'
                           if src else "") + '</td>')
        rows_html += f"""
        <tr class="{comp.strip()}">{pic_cell}
          <td>{P.esc(r.get('name'))}</td>
          <td class="td-muted">{P.esc(r.get('part_no'))}</td>
          <td class="fz-num">{_fmt_qty(float(r.get('qty') or 0))} {P.esc(r.get('unit'))}</td>
          <td class="fz-num">{_inr(r.get('price') or 0)}</td>
          <td class="fz-num">{_inr(r.get('total') or 0)}</td>
        </tr>"""

    tax_total = float((q.get("tax_info") or {}).get("total") or 0.0)
    pic_th = "<th>Picture</th>" if with_pics else ""
    span = 5 if with_pics else 4
    pic_hint = ""
    if with_pics:
        n_pics = sum(1 for i in pic_of if LI.src_of(i))
        pic_hint = (f" {n_pics} line{'' if n_pics == 1 else 's'} will carry the "
                    f"specification library&rsquo;s picture. Change or remove any "
                    f"picture on the invoice&rsquo;s <b>Pictures</b> page once it "
                    f"is raised.")
    frozen_html = f"""
    <div class="frozen-wrap"><table>
      <thead><tr>{pic_th}
        <th>Description</th><th>Part No</th>
        <th class="fz-num">Qty</th><th class="fz-num">Rate</th><th class="fz-num">Amount</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr><td colspan="{span}" class="fz-num">Subtotal</td>
            <td class="fz-num">{_inr(q.get('subtotal') or grand)}</td></tr>
        <tr><td colspan="{span}" class="fz-num">Tax</td>
            <td class="fz-num">{_inr(tax_total)}</td></tr>
        <tr><td colspan="{span}" class="fz-num">Invoice Value</td>
            <td class="fz-num">{_inr(grand)}</td></tr>
      </tfoot>
    </table></div>
    <p class="frozen-hint">
      These lines are copied onto the invoice exactly as quoted and are frozen at
      issue. To invoice different quantities or prices, raise a new quotation first.{pic_hint}
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

    _default_seq, pi_number_html = _number_control(
        f.get("doc_no_seq") if request.method == "POST" else "", may_number)

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Raise Proforma Invoice")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{DN.NUMBER_STYLES}</head>
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
        <div class="sn-sub">A running series, not reset by the financial
          year.</div>
        {existing_html}
      </div>

      <form method="POST" action="{url_for("proforma.create_proforma", qid=qid)}">

        <div class="form-section">
          <div class="section-title">Invoice</div>
          <div class="fg3">
            <div class="form-group">
              <label for="doc_no_seq">Proforma No.</label>
              {pi_number_html}
            </div>
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


@proforma_bp.route("/from-boq/<boq_id>", methods=["GET", "POST"])
def from_boq(boq_id: str):
    """
    Raise a proforma invoice FROM a bill of quantities (22 October 2026).

    The ordinary PI — `PI-nnnn`, `STORE["proformas"]`, the same printed sheet
    and the same onward *Raise Tax Invoice* — written from the schedule rather
    than from a quotation. See *RAISED FROM A BOQ* above for the leg, the
    headings, the rate and the tax.

    What differs from `create_proforma()`, and why:

    * **The lines are ticked, and the leg is chosen** — Supply, Installation,
      or both. The rate is the schedule's and is not edited.
    * **No running position across PIs.** A quotation's PIs are shares of one
      quoted value; a BOQ's PIs each carry their own lines (supply this month,
      labour next), so there is no one "order value" to measure a share of.
      `prior_invoiced` is 0 and the advance % is a share of THIS document. The
      form lists the PIs already raised from the schedule, so a second one is
      a decision, not an accident.
    * **The project is inherited from the BOQ** and stored.

    A **superseded** revision is refused at the route — `/purchase/from-boq`'s
    rule; `/boq/view` draws the link on the tip only, and a link is not a
    guard.
    """
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="Choose a bill of quantities to invoice against.",
                                type="error"))
    if boq_id in BQ.superseded_ids():
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg="That schedule has been superseded. Raise the "
                                    "proforma invoice against the current revision.",
                                type="error"))

    f = request.form
    is_post = request.method == "POST"
    leg = boq_leg(f.get("leg") if is_post else request.args.get("leg"))
    head = boq_tax_head(f.get("tax_type") if is_post else "")
    error = ""
    chosen = qty_of = None
    may_number = _may_set_number()
    seq_used = default_seq = 0

    if is_post:
        pi_date  = (f.get("date") or "").strip()
        pct      = _pct(f.get("advance_pct"), DEFAULT_ADVANCE_PCT)
        validity = (f.get("validity_days") or "").strip()

        if not pi_date:
            error = "Invoice date is required."
        elif pct < 0:
            error = "Advance % must be a number, e.g. 30."
        elif not (0 < pct <= 100):
            error = "Advance % must be greater than 0 and no more than 100."
        elif validity and not validity.isdigit():
            error = "Validity must be a whole number of days."

        picked, line_err = ([], "") if error else BP.picked_lines(
            f.get("pi_json") or "", boq, max_lines=BQ.MAX_LINES,
            empty_msg=("No lines are ticked. A proforma invoice with nothing on "
                       "it is not a document — tick at least one line, or cancel."),
            cap_msg="Raise more than one proforma invoice.")
        error = error or line_err
        items, item_err = ([], "") if error else boq_line_items(picked, boq, leg)
        error = error or item_err

        if not error:
            default_seq = SER.next_seq("PI", "")
            seq_used, num_err = DN.validate(DN.PI, "", f.get("doc_no_seq"),
                                            default_seq, may_number)
            error = error or num_err

        if not error:
            subtotal, tax_info, grand, total_qty = boq_figures(items, head)
            due = round(grand * pct / 100.0, 2)
            pid = str(uuid.uuid4())
            pi = {
                "id":  pid,
                "ref": _ref_for(seq_used),
                "date": pi_date,

                # ── No quotation behind it. The keys are present and empty, so
                #    every reader of a PI finds the shape it always found.
                "quotation_id":   "",
                "quotation_ref":  "",
                "quotation_date": "",

                # ── The schedule it was raised from. `boq_ref` is stored, not
                #    looked up, so the PI prints if the BOQ is ever removed.
                "boq_id":     boq_id,
                "boq_ref":    boq.get("ref", ""),
                "boq_rev_no": int(boq.get("rev_no") or 0),
                "boq_leg":    leg,

                **boq_customer(boq),

                "line_items":  items,
                "subtotal":    subtotal,
                "tax_type":    head,
                "tax_info":    tax_info,
                "grand_total": grand,
                "total_qty":   total_qty,

                "po_number":     (f.get("po_number") or "").strip(),
                "po_date":       (f.get("po_date") or "").strip(),
                "advance_pct":   pct,
                "amount_due":    due,
                "project_id":    boq_project_id(boq),

                "prior_invoiced": 0.0,
                "prior_refs":     [],
                "balance_due":    round(grand - due, 2),
                "payment_terms": (f.get("payment_terms") or "").strip(),
                "delivery_terms": (f.get("delivery_terms") or "").strip(),
                "delivery_date": (f.get("delivery_date") or "").strip(),
                "dispatch_through": (f.get("dispatch_through") or "").strip(),
                "incoterms":     (f.get("incoterms") or "").strip(),
                "validity_days": validity,
                "notes":         (f.get("notes") or "").strip(),

                "company_branch": boq.get("company_branch", ""),
                "auth_signatory": boq.get("auth_signatory", ""),
            }
            STORE["proformas"][pid] = pi
            DN.note_used(DN.PI, "", seq_used)
            DN.record_override(pi, _ref_for(default_seq), pi["ref"],
                               _actor_id())
            return redirect(url_for("proforma.view_proforma", id=pid,
                                    msg=f"Proforma invoice {pi['ref']} created "
                                        f"against {boq.get('ref') or 'the schedule'}.",
                                    type="success"))

        chosen, qty_of = boq_replay(f.get("pi_json") or "")

    def _v(name: str, fallback: str = "") -> str:
        if is_post:
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    v_date     = _v("date", _today())
    v_po_no    = _v("po_number")
    v_po_date  = _v("po_date")
    v_pct      = _v("advance_pct", f"{DEFAULT_ADVANCE_PCT:g}")
    v_pay      = _v("payment_terms", boq.get("payment_terms", ""))
    v_del_t    = _v("delivery_terms", boq.get("delivery_terms", ""))
    v_del_d    = _v("delivery_date")
    v_dispatch = _v("dispatch_through")
    v_inco     = _v("incoterms")
    v_valid    = _v("validity_days", DEFAULT_PI_VALIDITY)
    v_notes    = _v("notes")

    chain = boq_chain(boq_id)
    earlier = sorted(((p_id, p) for p_id, p in STORE["proformas"].items()
                      if str(p.get("boq_id") or "") in chain),
                     key=lambda kv: _ref_num(kv[1]))
    earlier_html = ""
    if earlier:
        chips = "".join(
            f'<a class="pi-chip" href="{url_for("proforma.view_proforma", id=p_id)}">'
            f'{P.esc(p.get("ref"))} &middot; {boq_leg_label(p.get("boq_leg"))} &middot; '
            f'&#8377;&nbsp;{float(p.get("amount_due") or 0):,.0f}</a>'
            for p_id, p in earlier)
        earlier_html = (f'<div class="pi-strip">{chips}</div>'
                        f'<div class="sn-sub">Already raised from this schedule. '
                        f'Each carries its own lines &mdash; check that this one '
                        f'does not ask for the same work twice.</div>')

    proj = (STORE.get("projects") or {}).get(boq_project_id(boq)) or {}
    proj_bit = (f' &middot; project <b>{P.esc(proj.get("name"))}</b>' if proj else "")
    back = url_for("boq.view_boq", id=boq_id)

    _default_seq, pi_number_html = _number_control(
        f.get("doc_no_seq") if is_post else "", may_number)

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Proforma Invoice from BOQ")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{FROM_BOQ_FORM_STYLES}{DN.NUMBER_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Proforma Invoice <span>from BOQ</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{back}" class="btn btn-ghost">&#8592; {P.esc(boq.get('ref'))}</a>
          <a href="{url_for("proforma.list_proformas")}" class="btn btn-ghost">All Proformas</a>
        </div>
      </div>

      {_alert(error, "error")}

      <div class="src-note">
        From bill of quantities <b>{P.esc(boq.get('ref'))}</b>
        &middot; {P.esc(boq.get('project_name'))} &middot; {P.esc(_customer_of(boq))}{proj_bit}
        <div class="sn-sub">A running series, not reset by the financial
          year.</div>
        {earlier_html}
      </div>

      <form method="POST" action="{url_for("proforma.from_boq", boq_id=boq_id)}"
            onsubmit="return saveJSON();">
        <input type="hidden" name="pi_json" id="pi_json" value=""/>

        <div class="form-section">
          <div class="section-title">Invoice</div>
          <div class="fg3">
            <div class="form-group">
              <label for="doc_no_seq">Proforma No.</label>
              {pi_number_html}
            </div>
            <div class="form-group">
              <label for="date">Invoice Date *</label>
              <input type="date" id="date" name="date" value="{P.esc(v_date)}" required/>
            </div>
            <div class="form-group">
              <label for="po_number">Customer PO / Work Order No.</label>
              <input type="text" id="po_number" name="po_number" value="{P.esc(v_po_no)}"
                     placeholder="their order number, if received"/>
            </div>
            <div class="form-group">
              <label for="po_date">Customer PO Date</label>
              <input type="date" id="po_date" name="po_date" value="{P.esc(v_po_date)}"/>
            </div>
          </div>
          <div class="fg2" style="margin-top:.9rem;">{boq_choice_html(leg, head)}
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
                {"".join(f'<option value="{p}"></option>' for p in ADVANCE_PRESETS)}
              </datalist>
            </div>
            <div class="adv-out">100 asks for the whole value of the lines ticked
              below; 30 asks for a 30% advance on them and shows the balance as
              payable before dispatch.</div>
          </div>
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
                     placeholder="e.g. Advance against material for Basement 1"/>
            </div>
          </div>
        </div>
{boq_grid(boq, chosen, qty_of, "pi_json", "proforma invoice")}
        <div class="form-actions">
          <button type="submit" class="btn">Raise Proforma Invoice</button>
          <a href="{back}" class="btn btn-ghost">Cancel</a>
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
    #
    # ⚠ **The Image column (21 October 2026) is drawn only when a line carries
    #   a picture that resolves** — `LI.sheet_has_images()`. A PI with none,
    #   which is every PI raised before pictures existed, renders byte-for-byte
    #   what it always rendered; `tests/test_print_golden.py` holds that.
    pics = LI.sheet_has_images(pi.get("line_items", []))
    sno, total_qty, table_rows = 0, 0.0, ""
    for row in pi.get("line_items", []):
        # A clause or leg band on a PI raised from a BOQ (22 October 2026):
        # words only, and not numbered. No other PI carries one.
        if row.get("is_header"):
            table_rows += boq_heading_row(
                row, f"\n          {LI.cell(row)}" if pics else "")
            continue
        sno += 1
        depth   = row.get("depth", 0)
        row_cls = "row-assembly" if row.get("type") == "assembly" else "row-item"
        indent  = "indent-1" if depth == 1 else ("indent-2" if depth >= 2 else "")
        if depth == 0:
            total_qty += float(row.get("qty") or 0)
        img_td = f"\n          {LI.cell(row)}" if pics else ""

        table_rows += f"""
        <tr class="{row_cls}">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>{img_td}
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

    # The label spans S.No / Part No / (Image) / Description / HSN.
    span = 5 if pics else 4
    if has_tax:
        table_rows += f"""
        <tr class="row-sum">
          <td colspan="{span}" class="sum-lbl">Subtotal</td>
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
              <td colspan="{span}" class="sum-lbl">{tname}{rate_label}</td>
              <td class="c-qty"></td><td class="c-unit"></td><td class="c-price"></td>
              <td class="c-total">{_inr(tamt)}</td>
            </tr>"""

    table_rows += f"""
    <tr class="row-total row-sum">
      <td colspan="{span}" class="sum-lbl">{"Invoice Value" if has_tax else "Total"}</td>
      <td class="c-qty">{_fmt_qty(total_qty)}</td>
      <td class="c-unit"></td><td class="c-price"></td>
      <td class="c-total">{_inr(grand)}</td>
    </tr>"""

    # ── Header meta ───────────────────────────────────────────────────────
    validity = P.esc(pi.get("validity_days")).strip()
    # A PI raised from a BOQ (22 October 2026) names its schedule in place of
    # a quotation it never had; every other PI's head is exactly as it was.
    from_boq = bool(pi.get("boq_ref")) and not pi.get("quotation_ref")
    meta_col_1 = (
        _meta("Proforma Invoice No.",  P.esc(pi.get("ref"))) +
        (_meta("Against BOQ",          P.esc(pi.get("boq_ref"))) if from_boq else
         _meta("Against Quotation",    P.esc(pi.get("quotation_ref")))) +
        _meta("Buyer's PO No.",        P.esc(pi.get("po_number"))) +
        _meta("Mode/Term of Payment",  P.esc(pi.get("payment_terms"))) +
        _meta("Terms of Delivery",     P.esc(pi.get("delivery_terms")))
    )
    meta_col_2 = (
        _meta("Date",             P.esc(pi.get("date"))) +
        ("" if from_boq else
         _meta("Quotation Date",  P.esc(pi.get("quotation_date")))) +
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
    elif pi.get("boq_ref"):
        src_line = (f'<span class="ds-src"> &middot; against Bill of Quantities '
                    f'{P.esc(pi["boq_ref"])}</span>')

    comp_br   = P.esc(pi.get("company_branch")) or B.COMPANY_NAME
    signatory = P.esc(pi.get("auth_signatory")) or P.esc(B.COMPANY_SIGNATORY)

    q_view = (url_for("quotation.view_quotation", id=pi["quotation_id"])
              if pi.get("quotation_id") in STORE["quotations"] else "")
    back_q = (f'<a href="{q_view}" class="btn btn-ghost">&#8592; Quotation '
              f'{P.esc(pi.get("quotation_ref"))}</a>' if q_view else "")
    if not back_q and pi.get("boq_id") in (STORE.get("boqs") or {}):
        back_q = (f'<a href="{url_for("boq.view_boq", id=pi["boq_id"])}" '
                  f'class="btn btn-ghost">&#8592; BOQ {P.esc(pi.get("boq_ref"))}</a>')

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

    # ── Delete ───────────────────────────────────────────────────────────
    # Drawn only for somebody the gate would let through (`auth.can_reach()`),
    # and NOT drawn at all once a tax invoice has been raised from this PI —
    # `delete_proforma()` refuses that case outright, so offering the control
    # would be offering a refusal. ⚠ Presentation, not the gate: the route is
    # in ROUTE_PERMISSIONS and refuses a typed URL itself. ⚠ It left
    # `auth.OWNER_ONLY` on 21 October 2026 (§0 fifty-second block), so
    # `proforma.delete` alone now decides and a Director sees this control.
    # The newline and indent live INSIDE the string, so a proforma nobody may
    # delete renders the action bar byte-for-byte as it always did.
    import auth as _AUTH
    del_pi = ""
    if not raised and _AUTH.can_reach("proforma.delete_proforma"):
        del_pi = (f'\n    <a href="{url_for("proforma.delete_proforma", id=id)}" '
                  f'class="btn btn-ghost" '
                  f'style="color:#b91c1c;border-color:#fecaca;">'
                  f'&#128465;&nbsp;Delete</a>')

    # ── Pictures (21 October 2026) — drawn for whoever the gate lets through,
    # and only them. The newline lives inside the string.
    pics_btn = ""
    if _AUTH.can_reach("proforma.pictures"):
        pics_btn = (f'\n    <a href="{url_for("proforma.pictures", id=id)}" '
                    f'class="btn btn-ghost">&#128247;&nbsp;Pictures</a>')
    img_th = f'\n          <th class="{LI.COLUMN[0]}">{LI.COLUMN[1]}</th>' if pics else ""

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(pi.get('ref')) + " Proforma Invoice")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{LI.SHEET_CSS if pics else ""}{DS.PRINT_EDGE_STYLES}
</head>
<body>
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Proforma Invoice <span style="color:var(--brand);">{P.esc(pi.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;align-items:center;">
    {back_q}
    <a href="{url_for("proforma.list_proformas")}" class="btn btn-ghost">All Proformas</a>
    {raise_ti}{del_pi}{pics_btn}
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
          <th class="c-partno">Part No</th>{img_th}
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

{DS.sig_block(comp_br, signatory, computer_generated=True)}

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


def _picture_entries(pi: dict) -> list:
    """
    Every line of the PI, numbered as the printed sheet numbers them.

    A heading row on a PI raised from a BOQ is not a line and is not numbered
    on the sheet, so it is not offered here either; the key keeps the row's
    own index, so it is stable whatever is skipped. With no heading rows —
    every PI raised from a quotation — this is exactly the list it always was.
    """
    out, sno = [], 0
    for n, r in enumerate(pi.get("line_items", [])):
        if r.get("is_header"):
            continue
        sno += 1
        out.append(LI.entry(f"li:{n}", sno, r.get("part_no"), r.get("name"), r))
    return out


@proforma_bp.route("/pictures/<id>", methods=["GET", "POST"])
def pictures(id: str):
    """
    The picture beside each line of a proforma invoice (21 October 2026).

    **The figures are not reachable from here.** A picture is the only thing
    this page writes, onto the PI's own copy of the line — the quotation's line
    is a different dict (`create_proforma()` copied it). One upload per request
    (`lineimage.py` says why), then back to this page with a message.

    `proforma.create` — choosing what the invoice shows is part of raising it.
    The PI has no lifecycle to gate on: it is never cancelled, and a tax
    invoice already raised from it keeps its own copy of the lines.
    """
    pi = STORE["proformas"].get(id)
    if not pi:
        return redirect(url_for("proforma.list_proformas",
                                msg="Proforma invoice not found.", type="error"))
    lines = pi.get("line_items", [])
    here = url_for("proforma.pictures", id=id)

    if request.method == "POST":
        if request.form.get("action") == "library":
            n = LI.fill_from_library(lines)
            msg = (f"The library's picture was put on {n} line{'' if n == 1 else 's'}."
                   if n else "No line without a picture has one in the library.")
            return redirect(url_for("proforma.pictures", id=id, msg=msg,
                                    type="success"))
        msg, err = LI.apply_post(request.form, request.files, _picture_entries(pi))
        return redirect(url_for("proforma.pictures", id=id, msg=msg or err,
                                type="error" if err else "success"))

    # The library button is drawn only when it would fill something.
    lib_n = sum(1 for r in lines
                if not LI.image_of(r) and LI.library_image_for(r.get("part_no")))
    lib_html = ""
    if lib_n:
        lib_html = (f'<form method="POST" action="{here}" class="pic-lib">'
                    f'<input type="hidden" name="action" value="library"/>'
                    f'<button type="submit" class="btn">Use the library&rsquo;s picture '
                    f'on {lib_n} line{"" if lib_n == 1 else "s"} with none</button></form>')

    return _page(f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title(str(pi.get('ref')) + " Pictures")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{LI.PAGE_CSS}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Pictures &middot; <span>{P.esc(pi.get('ref'))}</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{url_for('proforma.view_proforma', id=id)}" class="btn btn-ghost">&#8592; Back to the invoice</a>
        </div>
      </div>

      {_alert(request.args.get("msg"), request.args.get("type", "success"))}

      <div class="form-section">
        <div class="section-title">A picture beside each line</div>
        <p class="frozen-hint" style="margin:0 0 1rem;">
          A picture prints in an <b>Image</b> column beside the description. A
          line with none prints an empty cell; an invoice with no picture at all
          prints no Image column. JPEG, PNG or WebP up to 5&nbsp;MB, one line at
          a time &mdash; it is shrunk to {LI.MAX_SIDE}&nbsp;px and stored once.
          Nothing else on the invoice changes here.
        </p>
        {lib_html}
        {LI.rows_html(_picture_entries(pi), here, editable=True)}
      </div>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · proforma invoice</p></footer>
    </main></body></html>""")


@proforma_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_proforma(id: str):
    """
    Delete a proforma invoice.

    ⚠ **A PI that has been converted to a tax invoice cannot be deleted**, and
    that is the whole reason this route exists rather than a plain STORE pop.
    `cascade.impact_of("proformas", id)` reaches `invoices` through the
    `proforma_id` edge and returns a hard stop — a GST number has to stay
    consecutive, so removing the document the invoice was raised from is
    refused outright. Withdraw the tax invoice with `/invoice/cancel/<id>`
    instead; the number stays spent and the sheet prints marked CANCELLED.

    **The number is not released.** The PI series only ever advances, the same
    rule the delivery challan follows: the document may already have been sent
    to a customer to pay against.

    GET renders the confirmation and destroys nothing; POST destroys. Per
    ABOUT.md §7.9f this route ships its own GET-does-not-mutate test.
    """
    pi = STORE["proformas"].get(id)
    if not pi:
        return redirect(url_for("proforma.list_proformas",
                                msg="That proforma invoice no longer exists.",
                                type="error"))

    report = cascade.impact_of("proformas", id)

    if request.method == "POST":
        if report["blocked"] is not None:
            return redirect(url_for(
                "proforma.view_proforma", id=id, type="error",
                msg=("A tax invoice has been raised from this proforma — "
                     "cancel that instead. A GST number cannot leave a gap.")))
        ref = str(pi.get("ref") or "")
        cascade.delete_cascade("proformas", id)
        return redirect(url_for(
            "proforma.list_proformas", type="success",
            msg=f"Proforma {ref} deleted. Its number is not reissued."))

    blocked = report["blocked"] is not None
    acts = f"""
  <form method="POST" action="{url_for('proforma.delete_proforma', id=id)}"
        style="display:flex;gap:.7rem;">
    <button type="submit" class="btn">Delete {P.esc(pi.get('ref'))}</button>
    <a href="{url_for('proforma.view_proforma', id=id)}" class="btn btn-ghost">Keep it</a>
  </form>""" if not blocked else f"""
  <div style="display:flex;gap:.7rem;">
    <a href="{url_for('proforma.view_proforma', id=id)}" class="btn btn-ghost">&#8592; Back to the proforma</a>
  </div>"""

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Delete " + str(pi.get('ref') or ''))}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PROFORMA_STYLES}{cascade.CASCADE_STYLES}
</head>
<body>
{_nav()}
<main>
  <div class="page-top">
    <h1>Delete <span style="color:var(--brand);">{P.esc(pi.get('ref'))}</span></h1>
  </div>

  <div class="cas-box">
    <h2>&#9888; This cannot be undone</h2>
    <div class="cas-line">
      You are about to delete proforma invoice <b>{P.esc(pi.get('ref'))}</b>,
      raised {P.esc(pi.get('date'))} for
      <b>{P.esc(pi.get('customer_name')) or 'an unnamed customer'}</b>.<br/>
      <b>The number is not released</b> &mdash; the next proforma takes the
      next one in the series, because {P.esc(pi.get('ref'))} may already have
      gone to the customer to pay against.
    </div>
  </div>
{cascade.impact_html(report)}
{acts}

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · proforma invoice</p></footer>
</main>
</body></html>""")
