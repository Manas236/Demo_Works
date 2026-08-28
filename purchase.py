"""
purchase.py — Purchase Order Module  (THE BUY SIDE)
===================================================
Blueprint  : purchase_bp
Mounted at : /purchase  (registered in app.py)

Routes
------
  GET       /purchase/               — register of purchase orders raised
  GET,POST  /purchase/create         — raise a PO on a vendor
  POST      /purchase/<id>/update    — move it along its lifecycle
  GET       /purchase/view/<id>      — the printed purchase order

Why this is a separate pipeline and not a fourth link in the document chain
---------------------------------------------------------------------------
Every other document in this app is **sell side**:

    quotation  ->  proforma invoice  ->  tax invoice        money coming IN

A purchase order is **buy side** — money going OUT. It is not the same flow
with a different counterparty; it is the mirror image, and the two meet at the
*job*, never at the document:

* A proforma invoice **requests** money from a customer. A tax invoice
  **records a sale** and creates our output GST liability. Neither has anything
  to say about what we paid a vendor.
* A PO commits us to **spend**. The GST on it is **input** tax we pay and later
  claim, the opposite side of the ledger from a tax invoice.
* Its counterparty is a **vendor**, not a customer.

So there is deliberately **no link from a PO to a proforma or a tax invoice**,
and there never should be. Wiring one would be a category error.

The one link that does exist, and why it is optional
----------------------------------------------------
`quotation_id` is a **soft, optional** reference: "this PO is procuring for
QT-0012". It is not a parent the way a quotation is the parent of a PI — a PO
can stand entirely alone, because stock, consumables and spares get bought
without any deal behind them.

That single optional field is what buys job costing: quoted value against what
the job actually costs us to buy. `quotation.py` renders that panel by reading
`STORE["purchases"]` directly plus `url_for` — it must **not** import this
module.

The inversion you must hold in your head while editing this file
-----------------------------------------------------------------
On every other printed document **we are the seller**. On this one **we are the
buyer**, and three things flip:

  ┌────────────────┬─────────────────────────┬──────────────────────────┐
  │                │ quotation / PI / TI     │ purchase order           │
  ├────────────────┼─────────────────────────┼──────────────────────────┤
  │ letterhead     │ us (we issue it)        │ us (we issue it too)     │
  │ the "To" block │ the CUSTOMER            │ the VENDOR               │
  │ delivery block │ where we ship TO them   │ where they deliver TO US │
  │ the tax        │ OUTPUT tax we collect   │ INPUT tax we pay         │
  └────────────────┴─────────────────────────┴──────────────────────────┘

Getting the "To" block wrong here means posting our own address to a supplier
as the party to invoice. `_vendor_block()` and `_delivery_block()` are named
for the roles, not for the positions on the page, to make that hard to slip.

What is reused, and from where
------------------------------
Only the **document toolkit**, never the sell-side logic: `VIEW_DOC_STYLES`
gives the A4 frame, the repeating letterhead and the print rules, and `_inr` /
`_fmt_qty` / `_amount_in_words` / `_meta` / `_tax_lines` are the document's own
formatters. The financial-year helpers come from `pipeline.py`, which imports
nothing from the app — that is what lets both pipelines number their documents
`SF/../26-27/0001` without importing each other.

Import direction: purchase -> quotation (toolkit only), address, pipeline,
dashboard, branding, store. **Nothing here imports proforma or invoice, and
nothing there imports this.** Keep it that way; it is the whole point.
"""

import uuid
from datetime import date as _date, datetime as _datetime
from flask import Blueprint, request, redirect, url_for

import branding as B
import pipeline as P
import docsheet as DS
from dashboard import BASE_STYLES, _nav
from store import STORE

# The seeded prefill list for extra (non-BOQ) purchase-order lines. A flat
# table that imports NOTHING — not store, not pipeline, not branding — so this
# arrow is one-way and `po_parts.py` sits at the bottom of the graph beside
# `demo_data.py`. ⚠ Every rate in it is an ASSUMED PLACEHOLDER; read that
# module's docstring before quoting one of its figures anywhere.
import po_parts as PP

# ── The upstream links, and why importing these two is not a cycle ───────────
#
# `boq.py` is the schedule a purchase order can now be raised against, and
# `boqpick.py` is the line picker that raising it uses. Neither imports this
# module and neither ever may — `boq.py` links out with `url_for` (the one-way
# trick this repo runs between quotation/proforma, proforma/invoice,
# quotation/purchase, boq/ra, ra/receipt and boq/challan), and `boqpick.py` is a
# leaf that renders no document at all. Both directions are asserted at AST
# level in `tests/test_import_directions.py`.
#
# ⚠ **`po_draft.py` is deliberately NOT imported**, even though
#   `/purchase/from-draft/<id>` reads a draft PO. It is a sibling document
#   module, and coupling two of those for the sake of one dict lookup is what
#   the whole `url_for` arrangement exists to avoid: this module reads
#   `STORE["purchase_orders"]` directly, and `po_draft.py` links *here* by URL.
#   The prohibition runs both ways and is tested both ways.
#
# `project.py` is permitted and is not imported either, for the same reason —
# the project is reached through `STORE["projects"]` and `url_for`.
import boq as BQ
import boqpick as BP

# The shared A4 document toolkit — the sheet, not the sales chain. The sheet
# itself is now `docsheet.py`, which the tax invoice renders through as well:
# neither module imports the other, both import the leaf, and the separation
# this file's docstring insists on is unaffected.
from quotation import (
    QUOTATION_STYLES,     # the register and the create form; the SHEET's copy
    _amount_in_words,     # arrives inside DS.SHEET_STYLES
    _fmt_qty,
    _inr,
    _meta,
    _tax_lines,
)

# The same term vocabularies the sell-side forms offer. Shared rather than
# re-listed: "By Road Transport" must mean the same thing whichever direction
# the goods are moving.
from quotation import _DEL_TERMS, _DISPATCH, _INCOTERMS, _PAY_TERMS, _sel_opts
from address import picker_options

purchase_bp = Blueprint("purchase", __name__, url_prefix="/purchase")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================
_REF_SERIES = "PO"

# The lifecycle of a purchase order. This is the "different procedure" that
# makes purchasing its own pipeline: a sell-side document is issued once and
# then stands, whereas a PO is a commitment that has to be chased through to
# delivery. Edit this list and the form dropdown, the register filter tabs and
# the badges all regenerate.
PO_STATUSES = [
    "Draft",               # written, not yet sent to the vendor
    "Issued",              # sent; we are committed
    "Acknowledged",        # vendor has confirmed price and delivery
    "Partially Received",  # some material in, balance pending
    "Received",            # complete
    "Cancelled",           # withdrawn before delivery
]

DEFAULT_STATUS = "Draft"

# Terminal states. Everything else is still live and counts toward committed
# spend — the buy-side equivalent of `pipeline.OPEN_STAGES`.
CLOSED_STATUSES = ("Received", "Cancelled")

# A PO that commits money but was never acknowledged by the vendor is the
# classic way a delivery date quietly slips. The register flags them.
CHASE_STATUSES = ("Issued",)

# Blank rows the line editor opens with.
DEFAULT_LINE_ROWS = 3

# ⚠ **A material purchase order carries the SUPPLY track and never the
# installation one.** A BOQ prices every line twice — once to supply the
# material and once to install it (ABOUT.md §2b) — and the installation amount
# is labour we perform, not goods we buy from a supplier. Putting it on an order
# placed on a vendor would commit us to paying somebody else for our own work.
#
# A named constant rather than an absence, so the rule is findable: this is
# `challan.PRINT_RATES` / `po_draft.PRINT_TAX`'s arrangement. Flipping it is not
# a one-line change — a labour order is a different document with a different
# counterparty — so read this comment before you do.
INCLUDE_INSTALL_TRACK = False

# The prefill for a rate box on `/purchase/from-boq`. `supply_base_rate` is what
# the job was **costed** at before any escalation, which is the closest thing
# this app holds to what we expect to pay for the material. `supply_rate` is the
# escalated figure we SELL it at and is emphatically not it — `po_draft.py`'s
# module docstring makes the same point about the sheet that goes out for
# pricing, and it is the same mistake in a different place.
RATE_PREFILL_FIELD = "supply_base_rate"

# The buy sheet's summary rows, one cell wider than the sell chain's because
# `DS.BUY_COLUMNS` carries the discount column. Bound here rather than passed
# literally at each of the three call sites, so a fourth one cannot quietly
# print a row that is a cell short and pull the Order Value out from under the
# Amount column.
_SUM_BLANKS   = DS.SUM_BLANKS   + ("c-disc",)
_TOTAL_BLANKS = DS.TOTAL_BLANKS + ("c-disc",)


# =============================================================================
# HELPERS
# =============================================================================

def _today() -> str:
    return _date.today().strftime("%Y-%m-%d")


def _now() -> str:
    return _datetime.now().strftime("%Y-%m-%d %H:%M")


def _next_ref(datestr: str) -> str:
    """
    Next purchase order number — 'SF/PO/26-27/0001'.

    FY-scoped and max+1 within that year, the same shape as the tax invoice
    series (`pipeline.fy_of` / `fy_ref` are shared). A PO carries no statutory
    numbering rule — Rule 46 governs what we *issue as a supplier*, and here we
    are the customer — but a buyer's own series still has to be unique and
    non-repeating, because it is the key the vendor quotes on their invoice and
    the key we match that invoice against.

    Scanning only same-FY records is what lets the series restart each April
    without ever colliding.
    """
    fy = P.fy_of(datestr)
    highest = 0
    for po in STORE["purchases"].values():
        if po.get("fy") != fy:
            continue
        tail = str(po.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    # No 16-char cap: that is Rule 46's limit on a tax invoice, not ours.
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=64)


def is_open(po: dict) -> bool:
    """Still live — committed spend that has not landed or been withdrawn."""
    return (po.get("status") or DEFAULT_STATUS) not in CLOSED_STATUSES


def _status_badge(status: str) -> str:
    status = status or DEFAULT_STATUS
    slug = status.lower().replace(" ", "-")
    return f'<span class="po-badge po-{slug}">{P.esc(status)}</span>'


def _vendor_of(po: dict) -> str:
    """The party we are buying from — for list views."""
    name = (po.get("vendor_name") or "").strip()
    if name:
        return name
    first = (po.get("to") or "").strip().splitlines()
    return first[0].strip() if first else "—"


def _addr_block(addr: dict) -> str:
    """
    An address book entry as a printable multi-line block.

    Built here rather than with `address.format_address_lines()` because a PO
    wants the vendor's GSTIN and phone in the block (we have to quote them and
    ring them), and that helper deliberately renders postal lines only.
    """
    if not addr:
        return ""
    parts = []
    if addr.get("company"):      parts.append(addr["company"])
    if addr.get("contact_name"): parts.append(f'Kind Attn: {addr["contact_name"]}')
    for k in ("line1", "line2", "landmark"):
        if addr.get(k):
            parts.append(addr[k])
    city = addr.get("city") or ""
    if addr.get("pincode"):
        city = f'{city} - {addr["pincode"]}' if city else addr["pincode"]
    if city:
        parts.append(city)
    st = ", ".join(x for x in (addr.get("state"), addr.get("country") or "India") if x)
    if st:
        parts.append(st)
    if addr.get("phone"): parts.append(f'Ph: {addr["phone"]}')
    if addr.get("gstin"): parts.append(f'GSTIN: {addr["gstin"]}')
    return "\n".join(parts)


def _purchases_for(quotation_id: str) -> list:
    """Every PO raised against one quotation, oldest number first."""
    out = [(pid, po) for pid, po in STORE["purchases"].items()
           if po.get("quotation_id") == quotation_id]
    out.sort(key=lambda kv: kv[1].get("ref", ""))
    return out


def job_cost(quotation_id: str) -> dict:
    """
    What this job has cost us to buy, against what we quoted for it.

    The whole reason the optional `quotation_id` link exists. Public because
    `quotation.py` renders it on the deal panel — it reads this via a direct
    `STORE` walk rather than importing this module (see the docstring).

    **Cancelled POs are excluded from committed spend**; a withdrawn commitment
    is not a cost. They are still counted in `count` so the panel does not
    silently lose a document somebody raised.

    ⚠ **`extra_committed` is broken out on a row of its own, and that is not
      presentation.** An extra free-text line is real cost with **no BOQ line
      behind it** (29 Aug 2026). Folded silently into `committed` it would be
      invisible; dropped, it would understate what the job has cost. So it is
      reported as its own figure **as well as** inside `committed` — which is
      the honest pair, because it genuinely is part of what we have committed to
      spend and it genuinely has no schedule line to hang on.

      Read the two together: `committed` is the whole commitment, and
      `extra_committed` is how much of it answers to nothing on any schedule.
      **Never build a coverage ratio out of these** — a numerator counting extra
      lines against a BOQ's line count is comparing two different things.
    """
    committed = 0.0
    received  = 0.0
    extra_committed = 0.0
    extra_count = 0
    rows = _purchases_for(quotation_id)
    for _pid, po in rows:
        if (po.get("status") or DEFAULT_STATUS) == "Cancelled":
            continue
        val = float(po.get("grand_total") or 0.0)
        committed += val
        xl = extra_lines_of(po)
        if xl:
            extra_committed += extra_lines_total(xl)
            extra_count += len(xl)
        if po.get("status") == "Received":
            received += val

    q = STORE["quotations"].get(quotation_id) or {}
    quoted = float(q.get("grand_total") or 0.0)
    return {
        "count":     len(rows),
        "committed": committed,
        # Its own row. Part of `committed`, and reported separately because it
        # is the part of it that no schedule line accounts for.
        "extra_committed": round(extra_committed, 2),
        "extra_count":     extra_count,
        "received":  received,
        "quoted":    quoted,
        "margin":    quoted - committed,
        # Guard the divide: a quotation can legitimately total zero (everything
        # marked "included, no separate charge"), and a ZeroDivisionError on a
        # deal panel is a 500 on a page somebody opens every day.
        "margin_pct": ((quoted - committed) / quoted * 100.0) if quoted else 0.0,
    }


def _log(po: dict, note: str, status_to: str = None) -> None:
    """Append to the PO's own audit trail. Mirrors `pipeline.log_event`."""
    po.setdefault("status_history", []).append({
        "at":     _now(),
        "status": status_to if status_to is not None else po.get("status", DEFAULT_STATUS),
        "note":   note,
    })


def _history_html(po: dict) -> str:
    """Reverse-chronological trail, newest first — same idiom as the deal panel."""
    rows = list(reversed(po.get("status_history") or []))
    if not rows:
        return '<div class="po-hist-empty">Nothing recorded yet.</div>'
    out = ""
    for e in rows:
        out += (f'<div class="po-hist-row">'
                f'<span class="ph-at">{P.esc(e.get("at"))}</span>'
                f'<span class="ph-st">{_status_badge(e.get("status"))}</span>'
                f'<span class="ph-note">{P.esc(e.get("note"))}</span></div>')
    return out


# The discount column (CLIENT_CHANGES-2.md A2) is a **percentage off the rate**,
# not a rupee figure off the amount.
#
# A percentage is the form the client's own schedules already speak: DOMAIN.md
# §2.5 derives every BOQ rate as a base rate plus an **escalation percentage**,
# and a vendor's allowance comes back the same way. It also survives a quantity
# change, which a flat amount does not — edit the qty on a line discounted by
# ₹500 and the ₹500 silently becomes a different percentage of a different
# order.
#
# ⚠ **Where it sits relative to tax is the whole of the arithmetic, and it sits
#   INSIDE the tax base.** The discounted figure is what lands in the line's
#   `total`, so it is what `_totals_of()` sums into `subtotal`, and `subtotal`
#   is the sole argument `_tax_lines()` computes tax from — there is no second
#   path. A discount allowed on the order is a reduction in what the vendor
#   supplies for, so the tax they charge us follows it down; billing us tax on
#   a price we are not paying would overstate the input credit we could claim.
MAX_DISCOUNT_PCT = 100.0


def _parse_lines(form) -> tuple:
    """
    Read the repeating line-item rows off the form.

    Returns `(line_items, error)`. Rows with no product selected are skipped
    silently — the editor opens with blank rows on purpose, and an untouched
    one is not a mistake to shout about.

    A PO is **flat**: `depth` is always 0 and an assembly's children are not
    expanded. We are buying the thing the vendor sells us; if the components
    are bought separately they are separate lines, chosen deliberately. That is
    the opposite of the quotation, where a BOM is expanded so the customer can
    see what is inside — see ABOUT.md §3.
    """
    products = STORE["products"]
    ids   = form.getlist("line_product_id")
    qtys  = form.getlist("line_qty")
    rates = form.getlist("line_rate")
    discs = form.getlist("line_discount")

    items = []
    for idx, (pid, qty_raw, rate_raw) in enumerate(zip(ids, qtys, rates)):
        pid = (pid or "").strip()
        if not pid:
            continue
        p = products.get(pid)
        if not p:
            return [], "One or more selected items no longer exist in the catalogue."
        try:
            qty = float(str(qty_raw or "").strip() or 0)
        except ValueError:
            return [], f"Quantity for '{p['name']}' must be a number."
        if qty <= 0:
            return [], f"Quantity for '{p['name']}' must be greater than zero."

        rate = P.parse_money(rate_raw)
        if rate < 0:
            return [], f"Rate for '{p['name']}' cannot be negative."

        # A short `line_discount` list is the ordinary case, not a broken form:
        # every record written before A2 existed has none, and so does a POST
        # from anything that does not render the column. Missing reads as zero.
        disc, disc_err = _parse_discount(
            discs[idx] if idx < len(discs) else "", p["name"])
        if disc_err:
            return [], disc_err

        items.append({
            "type":    "item",
            "name":    p["name"],
            "part_no": p["part_no"],
            "hsn":     p.get("hsn", ""),
            "qty":     qty,
            "unit":    p.get("unit", ""),
            "price":   rate,
            "discount_pct": disc,
            "total":   _line_total(rate, qty, disc),
            "depth":   0,
        })

    if not items:
        return [], "Add at least one item to the purchase order."
    return items, ""


def _parse_discount(raw, item_name: str) -> tuple:
    """
    `(percent, error)` for one discount box. Blank is 0, which is not a discount.

    Refused above 100 because a line cannot cost less than nothing, and refused
    below 0 because a negative discount is a price increase wearing a disguise —
    the rate box is where a higher price belongs, in the open, where the vendor
    can be shown the number we agreed.
    """
    txt = str(raw or "").strip()
    if not txt:
        return 0.0, ""
    try:
        pct = float(txt)
    except ValueError:
        return 0.0, f"Discount for '{item_name}' must be a number."
    if pct < 0:
        return 0.0, f"Discount for '{item_name}' cannot be negative."
    if pct > MAX_DISCOUNT_PCT:
        return 0.0, (f"Discount for '{item_name}' cannot be more than "
                     f"{MAX_DISCOUNT_PCT:g}%.")
    return pct, ""


# =============================================================================
# A3 — ADDITIONAL CHARGE LINES ON THE FINAL PURCHASE ORDER
# =============================================================================
#
# CLIENT_CHANGES-2.md **A3**, built under the 28 August 2026 override block in
# `CLIENT_CHANGES.md` §0. The 27 August block explicitly REFUSED this item and
# stopped it on one sentence of tax law; that sentence has now been answered and
# the answer is recorded here because it is the whole design.
#
# ⚠ **THE CHARGE IS INSIDE THE TAXABLE VALUE.** A line on a purchase order **we
#   issue to a named vendor** is part of what we are agreeing to pay *that
#   vendor*, which is consideration for that vendor's supply — s.15(2)(c) CGST
#   Act, incidental expenses charged by the supplier in respect of the supply.
#   It sits inside the taxable value and tax computes on the total including it.
#
#   The competing reading — a third-party cost we carry ourselves, our own tempo
#   and our own labour — describes a cost that **would not appear on this
#   vendor's purchase order at all**. It is a separate transaction with a
#   separate party on a separate document, and `charge.py`'s expenses ledger is
#   where it belongs. The ambiguity is real in the world and is not real on this
#   document.
#
# ⚠ **The exception is expressible anyway, and that is deliberate.** Each line
#   carries `taxable`, defaulting to **True**. The day a genuine third-party
#   freight cost has to sit on this order it can be marked outside the base
#   without another pass and without the tax-base question being reopened under
#   time pressure. A non-taxable line is added AFTER tax, never before it.
#
# **One repeater, not four fields** — CC-2's A3 note says so in as many words,
# and it is right: four hardcoded fields guarantees a fifth request. What is
# stored is a **list**, every label is free text, the first two slots are seeded
# with the client's own two heads, and the slot count below is one constant.
#
# ⚠ **What is NOT built, recorded rather than left silent:** CC-2 also asks for
#   the heads to be seeded in `/settings` and editable there. They are not.
#   Reading them would add a `purchase.py → settings.py` edge to the import
#   graph (ABOUT.md §2) for a picker whose labels are already free text. It is a
#   recorded deviation in the 28 August override block, for the client-facing
#   owner to confirm — not a thing that was forgotten.

# How many charge slots the form offers. The client asked for four — loading &
# unloading, transportation, and "2 extra charges". Raising this is a one-line
# change and nothing below counts on it being 4.
PO_CHARGE_SLOTS = 4

# The two the client named, in the two slots he named them for. The rest are
# blank; every one of them is an editable text box, so this is a prefill and not
# a vocabulary.
DEFAULT_PO_CHARGE_LABELS = ("Loading & Unloading", "Transportation", "", "")

# A charge bigger than this is a typo, not a charge — the same class of guard as
# `MAX_DISCOUNT_PCT`. Ten crore on a loading line is somebody's stray zero.
MAX_CHARGE_AMOUNT = 100000000.0


def _parse_charges(form) -> tuple:
    """
    `(charges, error)` — the additional-charge repeater off a submitted form.

    Read **by index** rather than by three parallel `getlist()` calls, because
    an unchecked checkbox posts **nothing at all**: `charge_taxable` as a list
    would arrive shorter than the labels and silently pair the wrong flag with
    the wrong line. `charge_taxable_<n>` cannot misalign.

    Row rules, and each of them is a refusal to guess:

    - **Both blank** — skipped. Empty slots are the normal case and are not an
      error; a form offering four slots for two charges must not demand four.
    - **An amount that is not a number, or is negative** — refused. A negative
      charge is a discount wearing a disguise, and A2's discount column is where
      a reduction belongs, in the open.
    - **An amount with no label** — refused. A figure on a purchase order that
      does not say what it is for is exactly what a vendor queries.
    - **A label with a zero amount** — skipped. Nothing is being charged.

    Nothing is returned until every row has been read, so a bad fourth row does
    not leave the first three half-applied.
    """
    labels = form.getlist("charge_label")
    amounts = form.getlist("charge_amount")
    rows = max(len(labels), len(amounts))

    out = []
    for n in range(rows):
        label = str(labels[n] if n < len(labels) else "").strip()[:120]
        raw = str(amounts[n] if n < len(amounts) else "").strip()

        if not label and not raw:
            continue
        if raw:
            try:
                amount = float(raw)
            except ValueError:
                return [], (f"Charge amount for "
                            f"'{label or 'line ' + str(n + 1)}' must be a number.")
        else:
            amount = 0.0
        if amount < 0:
            return [], (f"Charge amount for '{label or 'line ' + str(n + 1)}' "
                        f"cannot be negative. A reduction belongs in the "
                        f"discount column.")
        if amount > MAX_CHARGE_AMOUNT:
            return [], (f"Charge amount for '{label or 'line ' + str(n + 1)}' "
                        f"is larger than this document allows.")
        if amount and not label:
            return [], (f"Charge line {n + 1} has an amount but no label. Say "
                        f"what the vendor is being asked to charge for.")
        if not amount:
            continue

        out.append({
            "label": label,
            "amount": round(amount, 2),
            # Absent checkbox means unticked means NOT taxable. The form ships
            # every box ticked, so the default a blank form produces is the
            # taxable one — the flag defaults to true where it is created, not
            # where it is read.
            "taxable": bool(form.get(f"charge_taxable_{n}")),
        })
    return out, ""


def charges_of(po: dict) -> list:
    """
    The charge lines on an order, or `[]`.

    A purchase order raised before 28 August 2026 has no `charges` key at all
    and reads as empty — no backfill, the same contract `written_off_against()`
    and `proforma.prior_invoiced` hold to.
    """
    return list((po or {}).get("charges") or [])


def charge_totals(charges: list) -> tuple:
    """
    `(taxable, exempt)` — the charge money that goes inside the tax base and the
    charge money that goes after it.

    Two figures rather than one, because they enter the arithmetic at different
    points and folding them together is the mistake this whole item was stopped
    on for a day.
    """
    taxable = round(sum(float(c.get("amount") or 0.0)
                        for c in (charges or []) if c.get("taxable")), 2)
    exempt = round(sum(float(c.get("amount") or 0.0)
                       for c in (charges or []) if not c.get("taxable")), 2)
    return taxable, exempt


def _line_total(rate: float, qty: float, disc_pct: float) -> float:
    """
    One line's amount, net of its discount, rounded once at the end.

    Rounded **once**, on the discounted product, rather than discounting an
    already-rounded amount: two roundings on 87 lines is how a purchase order
    ends up a rupee away from the vendor's invoice for no reason anybody can
    find. `discount_pct == 0` reproduces `round(rate * qty, 2)` exactly, which
    is what every line written before A2 carries.
    """
    return round(rate * qty * (1.0 - (disc_pct or 0.0) / 100.0), 2)


# =============================================================================
# EXTRA (NON-BOQ) PURCHASE-ORDER LINES
# =============================================================================
#
# ⚠ **THIS IS NOT ONE OF CLIENT_CHANGES-2.md's TWENTY PHASE 3 ITEMS.** It is a
#   client request made *after* the 19 August 2026 meeting that produced that
#   list, it carries no 3A/3B/3C tag, and it is priced in neither quotation.
#   Built under the **29 August 2026** override block in `CLIENT_CHANGES.md`
#   §0, which says in terms that no agent may record it as a Phase 3 item or
#   count it toward the board. PROGRESS.md carries it outside the bars.
#
# The requirement, in the client's words: BOQ items are not enough. When raising
# a purchase order he needs to ask the vendor for additional parts that appear
# nowhere on the BOQ. He sent a list of those parts with **no prices and no
# units**.
#
# ── THREE SEPARATE CONCEPTS LIVE ON THIS RECORD AND MUST NOT BE CONFLATED ────
#
#   There are THREE, not two, and each enters the arithmetic at its own point:
#
#   ┌───────────────┬────────────────────────────┬─────────────────────────────┐
#   │ `line_items`  │ BOQ-derived or catalogue    │ into `subtotal`             │
#   │               │ lines; carry a `line_id`    │                             │
#   │               │ when raised from a schedule │                             │
#   ├───────────────┼────────────────────────────┼─────────────────────────────┤
#   │ `extra_lines` │ **new** — free-text parts;  │ into `subtotal`, exactly    │
#   │               │ carry **NO** `line_id`      │ as a `line_items` row does  │
#   ├───────────────┼────────────────────────────┼─────────────────────────────┤
#   │ `charges`     │ A3's 4-slot labelled        │ AFTER `subtotal`, into      │
#   │               │ repeater (loading, freight) │ `taxable_value`             │
#   └───────────────┴────────────────────────────┴─────────────────────────────┘
#
# ⚠ **An extra line is a LINE, not a charge.** It is goods this company is
#   buying from this vendor, so it sits inside `subtotal` exactly as a
#   `line_items` row does. It does **not** go through `_parse_charges()` or
#   `charge_totals()`, and the fact that both are "money that was not on the
#   schedule" is not a reason to merge them: a charge is what the vendor bills
#   us *beyond* the goods, and an extra line *is* goods.
#
# ⚠ **An extra line carries NO `line_id` and must never be given one.**
#   `line_id` is a BOQ identity — the key `/purchase/from-boq` matches a row
#   back to a schedule by (§2f, and the ₹1,99,122.50 that matching on `item_no`
#   once cost). An extra line has no BOQ ancestor, so it has no such identity,
#   and minting one would make a part that is on no schedule claim to be on one.
#   `tests/test_po_extra_lines.py` asserts the key is absent.
#
# ⚠ **NOT capped at four.** `PO_CHARGE_SLOTS = 4` is A3's *fixed* repeater for
#   labelled charges. Extra lines are open-ended — the client's own list runs to
#   about 74 distinct parts — so rows are added and removed like the create
#   form's item rows, and there is no slot count here at all. There is also no
#   maximum, deliberately: `_parse_lines()` has none either, and inventing one
#   for this repeater alone would refuse an order the item editor beside it
#   would accept.
#
# ⚠ **Free text, and there is no parts master.** The owner chose this
#   explicitly. `po_parts.py` is a **typeahead prefill and nothing else** — not
#   a collection, not a document, not editable through the UI, not a vocabulary.
#   A description that matches a seeded name prefills unit and rate; anything
#   else is accepted exactly as typed, with a blank rate.


def _extra_assumed(description: str, rate: float) -> bool:
    """
    Whether this line's rate is still the seeded ASSUMED placeholder.

    Derived on the **server**, from the description and the rate themselves,
    rather than trusted from a hidden field the form posts. A hidden flag would
    be client-controlled, and the direction that matters is the dangerous one:
    a tampered or stale form could clear the mark and quietly present an
    invented figure as a real price.

    So the rule is arithmetic, not memory: **the rate is assumed if and only if
    the description matches a seeded part AND the submitted rate is still that
    part's seeded figure.** Prefill the box and it is true; edit the rate to
    anything else and it is false on the very next save, which is exactly
    "clears the moment the rate is edited".

    ⚠ **It can say "assumed" about a rate nobody prefilled** — type
    `Butane gas` and `130` by hand and the line is marked, because the figure
    on it *is* the placeholder figure whatever route it took to get there. That
    false positive is the safe one: it over-warns on screen and the mark never
    prints. The opposite error would let an invented rate travel unmarked.
    """
    hit = PP.lookup(description)
    if not hit:
        return False
    _canonical, _unit, seeded = hit
    return round(float(rate or 0.0), 2) == round(seeded, 2)


def _parse_extra_lines(form) -> tuple:
    """
    `(extra_lines, error)` — the free-text extra-line repeater off a form.

    Row rules, and each is a refusal to guess:

    - **Every field blank** — dropped silently. The editor opens with blank
      rows on purpose and an untouched one is not a mistake, which is
      `_parse_lines()`'s own contract.
    - **A description and no rate** — **kept**, with rate 0, and shown as
      incomplete. This is the client's actual case: he sent a list of parts
      with no prices, and refusing the row would make the feature useless on
      the day it is most needed. The vendor is being asked to price it.
    - **A quantity, rate or discount with no description** — refused. A figure
      on a purchase order that does not say what it is for is exactly what a
      vendor queries, and it is the same refusal `_parse_charges()` makes.
    - **A negative quantity or rate** — refused, in the words `_parse_lines()`
      uses.

    Nothing is returned until every row has been read, so a bad fourth row does
    not leave the first three half-applied.
    """
    descs  = form.getlist("extra_desc")
    units  = form.getlist("extra_unit")
    qtys   = form.getlist("extra_qty")
    rates  = form.getlist("extra_rate")
    discs  = form.getlist("extra_discount")
    rows = max(len(descs), len(units), len(qtys), len(rates), len(discs))

    def _at(seq, n):
        return str(seq[n] if n < len(seq) else "").strip()

    out = []
    for n in range(rows):
        desc = _at(descs, n)[:200]
        unit = _at(units, n)[:30]
        qty_raw, rate_raw, disc_raw = _at(qtys, n), _at(rates, n), _at(discs, n)

        if not (desc or unit or qty_raw or rate_raw or disc_raw):
            continue

        if not desc:
            return [], (f"Extra line {n + 1} has figures but no description. "
                        f"Say what the vendor is being asked to supply.")

        try:
            qty = float(qty_raw or 0)
        except ValueError:
            return [], f"Quantity for '{desc}' must be a number."
        if qty < 0:
            return [], f"Quantity for '{desc}' cannot be negative."

        rate = P.parse_money(rate_raw)
        if rate < 0:
            return [], f"Rate for '{desc}' cannot be negative."

        disc, disc_err = _parse_discount(disc_raw, desc)
        if disc_err:
            return [], disc_err

        out.append({
            "type": "extra",
            "description": desc,
            "unit": unit,
            "qty": qty,
            "rate": rate,
            "discount_pct": disc,
            # Reuses `_line_total()` — the SAME arithmetic A2 put on the item
            # rows, not a second copy of it. A2's discount is inside the tax
            # base and that has to remain true of an extra line, which it does
            # because `total` is already net and `subtotal` is what
            # `_tax_lines()` sees.
            "total": _line_total(rate, qty, disc),
            "rate_is_assumed": _extra_assumed(desc, rate),
            # ⚠ NO `line_id`. Deliberate, load-bearing, and asserted by a test.
            #   An extra line has no BOQ ancestor and must never claim one.
        })
    return out, ""


def extra_lines_of(po: dict) -> list:
    """
    The extra lines on an order, or `[]`.

    A purchase order raised before 29 August 2026 has no `extra_lines` key at
    all and reads as empty — no backfill, the same contract `charges_of()` and
    `proforma.prior_invoiced` hold to, and what keeps every order already in
    the database printing byte-for-byte what it always printed.
    """
    return list((po or {}).get("extra_lines") or [])


def extra_lines_total(extra_lines: list) -> float:
    """
    What the extra lines add to `subtotal`, net of their own discounts.

    Its own function because it is also the figure the job-costing summary
    needs to show on a **row of its own**: extra-line spend is real cost with
    no BOQ line behind it, and folding it into a schedule-derived figure would
    make it invisible.
    """
    return round(sum(float(r.get("total") or 0.0)
                     for r in (extra_lines or [])), 2)


def _charge_rows_html(charges: list, posted_labels=None, posted_amounts=None,
                      posted_taxable=None) -> str:
    """
    The A3 repeater, `PO_CHARGE_SLOTS` rows of label + amount + taxable.

    Filled from three sources in falling priority, which is the same contract
    `edit_purchase_rates()`'s rate boxes hold to:

    1. **What the user just posted**, so a form rejected on its fourth row comes
       back with the first three still typed in rather than emptied.
    2. **What is stored on the order**, when there is an order.
    3. **`DEFAULT_PO_CHARGE_LABELS`**, which is a prefill and not a vocabulary —
       every one of these is an editable text box.

    `posted_taxable` is the **form itself**, not a list, because an unchecked
    box posts nothing: it is asked `charge_taxable_<n>` per row. `None` means
    this is not a re-render of a POST, and the box follows the stored flag.

    **The box ships ticked on a blank row.** That is where "taxable defaults to
    true" actually lives — a charge on a purchase order we issue is inside the
    taxable value (see the section note), and the operator has to take an action
    to say otherwise.
    """
    out = ""
    for n in range(PO_CHARGE_SLOTS):
        stored = charges[n] if n < len(charges) else {}

        if posted_labels is not None and n < len(posted_labels):
            label = str(posted_labels[n])
        else:
            label = str(stored.get("label") or "")
            if not label and not stored and n < len(DEFAULT_PO_CHARGE_LABELS):
                label = DEFAULT_PO_CHARGE_LABELS[n]

        if posted_amounts is not None and n < len(posted_amounts):
            amount = str(posted_amounts[n])
        elif stored.get("amount"):
            amount = f"{float(stored['amount']):.2f}"
        else:
            amount = ""

        if posted_taxable is not None:
            taxable = bool(posted_taxable.get(f"charge_taxable_{n}"))
        elif stored:
            taxable = bool(stored.get("taxable"))
        else:
            taxable = True

        out += f"""
        <div class="chg-row">
          <input type="text" name="charge_label" value="{P.esc(label)}"
                 placeholder="what the charge is for" maxlength="120"/>
          <input type="number" name="charge_amount" value="{P.esc(amount)}"
                 min="0" step="0.01" placeholder="0.00" oninput="recalc()"/>
          <label class="chg-tax">
            <input type="checkbox" name="charge_taxable_{n}" value="1"
                   {"checked" if taxable else ""} onchange="recalc()"/>
            <span>Taxable</span>
          </label>
        </div>"""
    return out


def _charge_section_html(charges: list, posted_labels=None, posted_amounts=None,
                         posted_taxable=None) -> str:
    """
    The whole `form-section` the repeater lives in, so the create form and the
    reprice form cannot describe the same field two different ways.
    """
    rows = _charge_rows_html(charges, posted_labels, posted_amounts, posted_taxable)
    return f"""
        <div class="form-section">
          <div class="section-title">Additional charges</div>
          <div class="chg-head">
            <span>Charge</span><span>Amount (&#8377;)</span><span></span>
          </div>
          {rows}
          <small class="field-hint">Loading, transportation and anything else
            this vendor is billing us for beyond the line items. <b>Taxable</b>
            puts the charge inside the value the vendor computes GST on, which
            is what an incidental expense on their own supply is
            &mdash; s.15(2)(c). Untick it only for a cost somebody other than
            this vendor is charging us. Leave a row blank and it is not used.</small>
        </div>"""


# How many blank extra-line rows the form opens with. A floor, not a cap — the
# "+ Add part" button adds as many more as anybody wants, and `_parse_extra_lines()`
# drops every row left untouched.
DEFAULT_EXTRA_ROWS = 3


def _extra_row_html(desc="", unit="", qty="", rate="", disc="") -> str:
    """
    One row of the extra-line repeater. Also the `<template>` a new row clones.

    Six cells to `.line-row`'s six, but a different set of them — a free-text
    description and unit where the item editor has a catalogue `<select>` — so
    it gets its own `.xl-row` grid rather than borrowing one that does not fit.
    That is the same call A3's `.chg-row` made for the same reason.
    """
    return f"""
        <div class="xl-row">
          <input type="text" name="extra_desc" value="{P.esc(desc)}"
                 list="xl-parts" maxlength="200" placeholder="part, as you would say it to the vendor"
                 oninput="xlFill(this)"/>
          <input type="text" name="extra_unit" value="{P.esc(unit)}"
                 maxlength="30" placeholder="Unit"/>
          <input type="number" name="extra_qty" value="{P.esc(qty)}"
                 min="0" step="any" placeholder="Qty" oninput="recalc()"/>
          <input type="number" name="extra_rate" value="{P.esc(rate)}"
                 min="0" step="0.01" placeholder="Rate" oninput="recalc()"/>
          <input type="number" name="extra_discount" value="{P.esc(disc)}"
                 min="0" max="100" step="any" placeholder="0" oninput="recalc()"/>
          <span class="ln-amt">&#8212;</span>
          <button type="button" class="btn-remove-line"
                  onclick="this.closest('.xl-row').remove(); recalc();">&#215;</button>
        </div>"""


def _extra_section_html(extra_lines: list, posted=None) -> str:
    """
    The whole `form-section` the extra-line repeater lives in.

    Shared by `/purchase/create` and `/purchase/edit/<id>` so the two cannot
    describe the same field two different ways — `_charge_section_html()`'s
    contract, one repeater further down the form.

    Filled from three sources in falling priority, which is that same contract:

    1. **What the user just posted** (`posted` is the form), so a rejected POST
       comes back with every row still typed in rather than emptied.
    2. **What is stored on the order**, when there is an order.
    3. **Blank rows**, padded to `DEFAULT_EXTRA_ROWS`.

    ⚠ **This section is drawn on `/purchase/create` and `/purchase/edit/<id>`
      ONLY.** It is deliberately absent from `/purchase/from-boq/<boq_id>` and
      `/purchase/from-draft/<draft_id>` — see the note on those routes.
    """
    rows_data = []
    if posted is not None:
        descs = posted.getlist("extra_desc")
        units = posted.getlist("extra_unit")
        qtys  = posted.getlist("extra_qty")
        rates = posted.getlist("extra_rate")
        discs = posted.getlist("extra_discount")
        n_rows = max(len(descs), len(units), len(qtys), len(rates), len(discs))
        for n in range(n_rows):
            rows_data.append((
                descs[n] if n < len(descs) else "",
                units[n] if n < len(units) else "",
                qtys[n]  if n < len(qtys)  else "",
                rates[n] if n < len(rates) else "",
                discs[n] if n < len(discs) else "",
            ))
    else:
        for r in extra_lines or []:
            rows_data.append((
                str(r.get("description") or ""),
                str(r.get("unit") or ""),
                _fmt_qty(float(r.get("qty") or 0.0)) if r.get("qty") else "",
                f"{float(r.get('rate') or 0.0):.2f}" if r.get("rate") else "",
                f"{float(r.get('discount_pct') or 0.0):g}" if r.get("discount_pct") else "",
            ))
    while len(rows_data) < DEFAULT_EXTRA_ROWS:
        rows_data.append(("", "", "", "", ""))

    rows = "".join(_extra_row_html(*r) for r in rows_data)
    options = "".join(f'<option value="{P.esc(n)}"></option>'
                      for n in PP.suggestions())
    return f"""
        <div class="form-section">
          <div class="section-title">Extra parts &mdash; not on the schedule</div>
          <div class="xl-head">
            <span>Part</span><span>Unit</span><span>Qty</span>
            <span>Rate (&#8377;)</span><span>Disc %</span>
            <span style="text-align:right;">Amount</span><span></span>
          </div>
          <div id="xlines">{rows}</div>
          <datalist id="xl-parts">{options}</datalist>
          <button type="button" class="btn btn-ghost" onclick="addExtra()"
                  style="margin-top:.3rem;">+ Add part</button>
          <small class="field-hint">Anything you need from this vendor that is
            not a BOQ item. <b>Type the part however you say it</b> &mdash; this
            is free text, not a catalogue, and nothing here has to exist
            anywhere else first. These are <b>goods</b>, so they sit in the
            order's sub&nbsp;total beside the items above, not in the additional
            charges below.
            <br/><b>Rates are suggested, never quoted.</b> A part we have seen
            before fills in a unit and a placeholder rate so an order can go out
            today; that figure is <b>an assumption nobody has verified</b>, it
            is flagged on screen until you replace it, and it is never printed
            on the order the vendor receives. Leave the rate blank if you want
            the vendor to price it. Leave a whole row blank and it is not
            used.</small>
        </div>"""


def _alert(msg: str, msg_type: str) -> str:
    if not msg:
        return ""
    icon = "&#10003;" if msg_type == "success" else "&#10007;"
    return f'<div class="alert alert-{P.esc(msg_type)}">{icon} {P.esc(msg)}</div>'


# =============================================================================
# THE VENDOR — one block, three create paths
# =============================================================================
#
# `/purchase/create`, `/purchase/from-boq` and `/purchase/from-draft` all have
# to answer "who are we buying from", and they must answer it identically: the
# same picker over the same address book, the same two refusals in the same
# order, and the same five fields snapshotted onto the record. Three copies of
# that is three chances for one of them to accept a vendor the others refuse.
#
# So it is extracted here rather than written twice more, and `create_purchase()`
# was changed to call it — the extraction is the point, and a helper only the new
# routes used would be the second copy it exists to prevent. The refusal wording
# and the ordering are unchanged, deliberately, because they are what the
# existing tests read.

def _vendor_from(form) -> tuple:
    """
    Returns `(fields, error)` — the vendor block a PO record carries, or why not.

    **The address book is the only path**, unlike `po_draft.vendor_from()` which
    also takes a typed one-off supplier. That difference is real and is kept: a
    draft PO is a request for a quotation and may go to a fabricator nobody has
    filed, whereas this document commits money and quotes the vendor's GSTIN
    back at them on a record we claim input tax credit against.

    ⚠ **Still not a vendor master** — ABOUT.md §7 gap B6, which now has a third
      consumer rather than two.
    """
    vendor_id = (form.get("vendor_id") or "").strip()
    vendor = STORE["addresses"].get(vendor_id)
    if not vendor_id:
        return {}, "Choose the vendor this order goes to."
    if not vendor:
        return {}, "That vendor is no longer in the address book."
    return {
        "vendor_id":    vendor_id,
        "vendor_name":  vendor.get("company") or vendor.get("label") or "",
        "vendor_gstin": vendor.get("gstin", ""),
        "to":           _addr_block(vendor),
        "vendor_ref":   (form.get("vendor_ref") or "").strip(),
    }, ""


def _vendor_field(selected: str) -> str:
    """The vendor form group — one widget, so three forms cannot offer three."""
    return f"""<div class="form-group">
              <label for="vendor_id">Vendor *</label>
              <select id="vendor_id" name="vendor_id" required>
                {picker_options("— choose vendor —", only_types=("vendor",), selected=selected)}
              </select>
              <small class="field-hint">From the address book, vendors only.
                Add one at <a href="{url_for("address.add_address")}">Address Book</a>
                if the supplier is not listed.</small>
            </div>"""


# =============================================================================
# THE UPSTREAM LINKS — boq_id, project_id, and line_id on every line
# =============================================================================
#
# All three are **optional**, all three default to `""` / absent, and a purchase
# order carrying none of them is the normal case rather than an incomplete one.
# That is the same contract `proforma.prior_invoiced` and `ra.tax_slabs` hold
# to: a new field defaults cleanly, nothing is backfilled, and every record
# written before it existed renders exactly as it did.
#
# ⚠ **`line_id` is the key and `item_no` is a label.** Item numbers restart per
#   section and the client's own section A carries item 17 twice — a flexible
#   sprinkler drop at ₹1,800 and a 150 mm butterfly valve at ₹14,572.50. Keying
#   on it collapsed 87 priced lines into 77 and waved ₹1,99,122.50 of over-claim
#   through on their real schedule (ABOUT.md §3 property 0). Nothing here ever
#   matches on `item_no`; it is carried for the person reading the document.

def _project_name_of(project_id: str) -> str:
    """
    The project's own name, or `""`.

    Stored on the record rather than looked up at render, so the PO still reads
    as a historical document if the project is removed — `proforma.quotation_ref`
    and `ra.boq_ref` make the same call for the same reason.
    """
    proj = (STORE.get("projects") or {}).get(str(project_id or "")) or {}
    return str(proj.get("name") or "")


def _project_of_boq(boq: dict) -> tuple:
    """
    `(project_id, project_name)` a PO inherits from the BOQ it is raised against.

    **Inherited at create and then STORED, never derived.** A PO entered from
    scratch can be tagged to a project with no BOQ behind it at all, so the link
    cannot be a lookup through `boq_id` — there would be nothing to look through.

    ⚠ A BOQ with no `project_id` gives the PO **no project**, and specifically
      does not fall back to the BOQ's free-text `project_name`. That field is a
      display label; `project_id` is the grouping key (project.py's docstring
      says so in as many words), and inventing an id-less project name here
      would put a row on no project's page while looking as though it had one.
    """
    pid = str(boq.get("project_id") or "")
    name = _project_name_of(pid)
    return (pid, name) if name else ("", "")


def _boq_lines_by_id(boq: dict) -> dict:
    """`{line_id: line}` for the BOQ, so a picked row can find its HSN and rate."""
    out = {}
    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            out[lid] = li
    return out


def _po_lines_from_picked(picked: list, boq: dict) -> tuple:
    """
    Returns `(line_items, error)` — `boqpick` rows in this module's line shape.

    The rows are **snapshotted into the PO record here and now**. Nothing on the
    printed order is ever re-read from the live BOQ afterwards, which is not a
    stylistic preference: `print_ra()` looped `boq["line_items"]` instead of the
    bill's own claims, so a line deleted from the schedule vanished from the
    printed table while its amount stayed inside the printed subtotal — an
    invoice whose rows did not add up to its own total, green the whole time
    because every print test rendered against data nobody then touched
    (ABOUT.md §5, `/ra/print` reads the RECORD).

    A **specification header** comes across carrying its clause and no money, so
    the supplier can read what they are being asked to supply (DOMAIN.md §2.2).
    It has no quantity, no rate and no amount, and is excluded from both totals.
    """
    by_lid = _boq_lines_by_id(boq)
    items = []
    for row in picked:
        lid = str(row.get("line_id") or "")
        src = by_lid.get(lid) or {}
        if row.get("is_header"):
            items.append({
                "type":      "item",
                "is_header": True,
                "line_id":   lid,
                "name":      str(row.get("description") or ""),
                "part_no":   str(row.get("item_no") or ""),
                "hsn":       "",
                "qty":       0.0,
                "unit":      "",
                "price":     0.0,
                "total":     0.0,
                "depth":     0,
            })
            continue

        qty = float(row.get("qty") or 0.0)
        if qty <= 0:
            return [], (f"Quantity for item {row.get('item_no') or '(unnumbered)'} "
                        f"must be greater than zero.")
        rate = float(row.get("rate") or 0.0)
        if rate < 0:
            return [], (f"Rate for item {row.get('item_no') or '(unnumbered)'} "
                        f"cannot be negative.")

        items.append({
            "type":      "item",
            "is_header": False,
            # THE key. Carried so this row can be traced back to the schedule
            # line it was ordered against however the item numbers are later
            # renumbered by a revision.
            "line_id":   lid,
            "name":      str(row.get("description") or ""),
            "part_no":   str(row.get("item_no") or ""),
            # The BOQ line carries a supply HSN and an installation SAC. Only
            # the supply code belongs on a material order — INCLUDE_INSTALL_TRACK.
            "hsn":       str(src.get("supply_hsn") or ""),
            "qty":       qty,
            "unit":      str(row.get("unit") or ""),
            "price":     rate,
            "total":     round(rate * qty, 2),
            "depth":     0,
        })

    if not any(not r["is_header"] for r in items):
        return [], "Add at least one item to the purchase order."
    return items, ""


def _totals_of(items: list, tax_type: str, cgst: float, igst: float,
               charges: list = None, extra_lines: list = None) -> tuple:
    """
    `(subtotal, taxable_value, tax_info, grand_total, total_qty)` for a set of
    PO lines, their extra free-text lines and their A3 charge lines.

    The same `quotation._tax_lines()` every purchase order has always used, with
    SGST forced equal to CGST exactly as the create form forces it. The tax is
    **input** tax we pay — the opposite side of the ledger from a tax invoice —
    and none of that arithmetic is shared with the sell chain, only the
    furniture it prints inside.

    ⚠ **WHERE EACH OF THE THREE ENTERS, which is the whole of the arithmetic:**

        subtotal      = sum(line totals) + sum(extra line totals)
                                                      ← extra lines enter HERE,
                                                        as LINES, beside items
        taxable_value = subtotal + taxable charges    ← A3 enters HERE instead
        tax           = _tax_lines(taxable_value)     ← so tax follows both up
        grand_total   = taxable_value + tax + exempt charges

    **Three concepts, two entry points, and the difference is not cosmetic.**
    An extra line is *goods we are buying from this vendor*, so it belongs in
    `subtotal` exactly where a `line_items` row belongs. A charge is what the
    vendor bills us *beyond* the goods, so it joins one step later. Putting an
    extra line through `charge_totals()` would give the right grand total by the
    wrong route and print it in the wrong place on the sheet.

    `subtotal` therefore still means what it always meant — **the sum of the
    line amounts** — with the free-text lines counted as the lines they are. An
    order with no extra lines and no charges has `taxable_value == subtotal`, so
    **every stored total on every order raised before this pass is reproduced to
    the rupee**, and the printed "Taxable Value" row prints the same number it
    always did.

    A **non-taxable** charge is added after the tax and is not in the base,
    which is the one line of code the `taxable` flag buys.
    """
    subtotal = round(sum(float(r.get("total") or 0.0) for r in items)
                     + extra_lines_total(extra_lines), 2)
    ch_taxable, ch_exempt = charge_totals(charges)
    taxable_value = round(subtotal + ch_taxable, 2)
    tax_info = _tax_lines(taxable_value, tax_type,
                          cgst_rate=cgst, sgst_rate=cgst, igst_rate=igst)
    grand = round(taxable_value + float(tax_info.get("total") or 0.0)
                  + ch_exempt, 2)
    # Extra lines are quantities of goods, so they count toward the order's
    # total quantity for the same reason they count toward its value.
    total_qty = round(sum(float(r.get("qty") or 0.0) for r in items)
                      + sum(float(r.get("qty") or 0.0)
                            for r in (extra_lines or [])), 3)
    return subtotal, taxable_value, tax_info, grand, total_qty


def _product_options(selected: str = "") -> str:
    """
    Catalogue <option> list for a line row.

    Includes **support** items prominently — a pump casing or a base frame is
    exactly the sort of thing that is bought rather than sold on its own, so
    the type that the sell-side picker treats as a sub-component is a
    first-class choice here.
    """
    opts = '<option value="">&#8212; select item &#8212;</option>'
    for pid, p in sorted(STORE["products"].items(),
                         key=lambda kv: (kv[1].get("name") or "").lower()):
        sel  = " selected" if pid == selected else ""
        kind = (p.get("type") or "standalone")[:3].upper()
        opts += (f'<option value="{P.esc(pid)}"{sel}>'
                 f'[{kind}] {P.esc(p.get("name"))} ({P.esc(p.get("part_no"))})</option>')
    return opts


# =============================================================================
# CSS — purchase-only
# =============================================================================
# Plain string, not an f-string, so the CSS braces are written once. Layered
# after BASE_STYLES / QUOTATION_STYLES. Deliberately does NOT load
# PROFORMA_STYLES or INVOICE_STYLES: this is the other pipeline, and borrowing
# a sell-side sheet is how the separation would quietly rot. Anything the buy
# side needs is declared here.

PURCHASE_STYLES = """
<style>
  /* ── Print: the discount column ───────────────────────────────────────
     `.c-disc` is declared HERE and not in `QUOTATION_STYLES` beside its eight
     siblings, and that is the whole point of this constant. The sell chain's
     column widths are shared by the quotation, the proforma and the tax
     invoice, all three of which are pinned byte-for-byte; a rule added there
     moves three digests for a column only the buy sheet draws. Narrow, because
     "12.5%" is the widest thing it will ever hold. */
  .c-disc { width:14mm; text-align:right; font-variant-numeric:tabular-nums;
            font-size:var(--fs-xs); }

  /* ── Screen: form ─────────────────────────────────────────────────── */
  .field-hint {
    display:block; margin-top:.35rem; font-size:.76rem;
    color:var(--muted); line-height:1.45; font-weight:400;
    text-transform:none; letter-spacing:0;
  }

  /* The buy-side banner. A PO looks enough like the sell-side documents that
     somebody will eventually open one expecting a quotation, so the direction
     of the money is stated once, in words, at the top of the form. */
  .buy-note {
    background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--navy); border-radius:var(--radius);
    padding:.9rem 1.2rem; margin-bottom:1.4rem; font-size:.88rem;
  }
  .buy-note b { color:var(--navy); }
  .buy-note .bn-sub { color:var(--muted); font-size:.82rem; margin-top:.25rem; }

  /* Repeating line editor — same shape as product.py's BOM child rows, which
     is the established pattern in this app for "a few rows, no JS model". */
  .line-row {
    display:grid; grid-template-columns:1fr 90px 130px 80px 120px 34px;
    gap:.55rem; align-items:center; margin-bottom:.55rem;
  }
  .line-head {
    display:grid; grid-template-columns:1fr 90px 130px 80px 120px 34px;
    gap:.55rem; font-size:.72rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.05em; margin-bottom:.4rem;
  }
  .line-row .ln-amt {
    font-variant-numeric:tabular-nums; text-align:right;
    font-size:.86rem; color:var(--muted); padding-right:.2rem;
  }
  .btn-remove-line {
    background:none; border:1px solid var(--border); border-radius:7px;
    color:var(--muted); cursor:pointer; font-size:1rem; line-height:1;
    padding:.35rem .5rem;
  }
  .btn-remove-line:hover { border-color:var(--brand); color:var(--brand); }
  .po-total-strip {
    display:flex; justify-content:flex-end; gap:1.4rem; flex-wrap:wrap;
    margin-top:.9rem; padding-top:.9rem; border-top:1px solid var(--border);
    font-size:.9rem;
  }
  .po-total-strip b { font-size:1.05rem; color:var(--brand); }
  @media (max-width:640px){
    .line-row, .line-head { grid-template-columns:1fr 70px 110px; }
    .line-head span:nth-child(4), .line-head span:nth-child(5),
    .line-head span:nth-child(6),
    .line-row input[name="line_discount"],
    .line-row .ln-amt { display:none; }
  }

  /* ── Screen: status badges ────────────────────────────────────────── */
  .po-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem; white-space:nowrap;
    background:#EDECF1; color:#4B4459;
  }
  .po-issued             { background:var(--navy-lt); color:var(--navy); }
  .po-acknowledged       { background:#E3ECFA; color:#1B4C8C; }
  .po-partially-received { background:#FFF4D6; color:#8A5A00; }
  .po-received           { background:#E4F3E7; color:#1E6B2E; }
  .po-cancelled          { background:#F3E4E4; color:#8C2A2A; }

  /* ── Screen: the PO panel on the view page ────────────────────────── */
  .po-panel {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.2rem 1.4rem; margin-bottom:1.5rem;
  }
  .po-panel h2 {
    font-size:.78rem; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted); margin-bottom:.9rem;
  }
  .po-panel-row { display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-end; }
  /* A3's charge repeater (28 Aug 2026). Three cells against `.line-row`'s six,
     so it gets its own grid rather than borrowing one that does not fit. Screen
     only — the printed charge lines are ordinary `row-sum` rows and carry no
     rule of their own, which is why nothing here is inside the print block. */
  .chg-head, .chg-row {
    display:grid; grid-template-columns:1fr 150px 120px; gap:.6rem;
    align-items:center;
  }
  .chg-head {
    font-size:.72rem; text-transform:uppercase; letter-spacing:.05em;
    color:var(--muted); padding:0 0 .35rem;
  }
  .chg-row { padding:.22rem 0; }
  .chg-row input[type="text"], .chg-row input[type="number"] { margin:0; }
  .chg-tax {
    display:flex; gap:.4rem; align-items:center;
    font-size:.82rem; color:var(--muted); margin:0;
  }
  .chg-tax input { margin:0; }
  @media (max-width:640px) {
    .chg-head { display:none; }
    .chg-row { grid-template-columns:1fr; }
  }
  /* The extra free-text line repeater (29 Aug 2026). Seven cells against
     `.line-row`'s six and a different set of them — a typed description and a
     typed unit where the item editor has a catalogue <select> — so it gets its
     own grid rather than stretching one that does not fit. Screen only. */
  .xl-head, .xl-row {
    display:grid; grid-template-columns:1fr 80px 80px 110px 70px 110px 34px;
    gap:.55rem; align-items:center;
  }
  .xl-head {
    font-size:.72rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.05em; margin-bottom:.4rem;
  }
  .xl-row { margin-bottom:.55rem; }
  .xl-row input { margin:0; }
  @media (max-width:640px){
    .xl-head { display:none; }
    .xl-row { grid-template-columns:1fr 70px 90px; }
    .xl-row input[name="extra_unit"], .xl-row input[name="extra_discount"],
    .xl-row .ln-amt { display:none; }
  }

  /* ⚠ THE ASSUMED-RATE MARKER IS SCREEN ONLY, AND THE PRINT RULE BELOW IS THE
     WHOLE POINT OF IT. It says "the figure beside me was seeded from
     po_parts.py and nobody has replaced it yet" — which is a note to ourselves
     about our own guess. The vendor receives the ORDER, not our record of
     having invented the price, so it is `display:none` at print exactly as
     `.po-panel` is. Same amber and same shape as the blank-identity
     `.todo-chip` it is modelled on, because the app already has one visual
     language for "this still needs real data". */
  .xl-assumed {
    display:inline-block; margin-left:.4em;
    background:#FFF4D6; color:#8A5A00; border:1px dashed #E0A93B;
    border-radius:5px; padding:0 .38em;
    font-size:.82em; font-weight:600; font-style:normal;
    letter-spacing:0; white-space:nowrap;
  }
  @media print { .xl-assumed { display:none !important; } }

  .po-hist { margin-top:1.1rem; border-top:1px solid var(--border); padding-top:.8rem; }
  .po-hist-row {
    display:flex; gap:.7rem; align-items:baseline; flex-wrap:wrap;
    font-size:.82rem; padding:.28rem 0;
  }
  .po-hist-row .ph-at { color:var(--muted); font-variant-numeric:tabular-nums; }
  .po-hist-row .ph-note { color:var(--text); }
  .po-hist-empty { font-size:.83rem; color:var(--muted); }

  /* A1's reprice trail (28 Aug 2026). Inside .po-panel deliberately, so the
     rule below hides it from the printed sheet along with everything else on
     the panel: what the vendor holds is the order, not our record of having
     changed it. */
  .po-reprice { margin-top:1.1rem; border-top:1px solid var(--border); padding-top:.8rem; }
  .po-reprice-t {
    font-size:.72rem; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted); margin-bottom:.5rem;
  }
  .rp-entry { padding:.35rem 0; }
  .rp-when { font-size:.78rem; color:var(--muted); font-variant-numeric:tabular-nums; }
  .rp-line {
    display:flex; gap:.7rem; align-items:baseline; flex-wrap:wrap;
    font-size:.82rem; padding:.15rem 0 .15rem .9rem;
  }
  .rp-line .rp-item { color:var(--text); }
  .rp-line .rp-move { font-variant-numeric:tabular-nums; font-weight:600; }
  .rp-line .rp-disc { color:var(--muted); font-variant-numeric:tabular-nums; }
  @media print { .po-panel { display:none; } }

  /* ── Print: the PO document ───────────────────────────────────────── */
  /* Scoped inside .quotation-doc so it inherits that sheet's type scale
     (--fs-*) and rule weights (--rule-*). No new font, size or border weight —
     the same restraint PROFORMA_STYLES and INVOICE_STYLES hold to. */

  /* States the direction of the transaction on the face of the document. A
     supplier receiving this must not be able to mistake it for our quotation. */
  .quotation-doc .doc-sub-po {
    text-align:center; font-size:var(--fs-sm); font-weight:700;
    padding:2px 6px; border-bottom:var(--rule-box);
  }
  .quotation-doc .doc-sub-po .dp-src { font-weight:400; color:var(--doc-soft); }

  .quotation-doc .po-status-strip {
    display:flex; flex-wrap:wrap; gap:0 8mm;
    padding:2px 6px; border-bottom:var(--rule);
  }
  .quotation-doc .po-status-strip .ps-l { color:var(--doc-soft); }
  .quotation-doc .po-status-strip .ps-v { font-weight:700; }

  .quotation-doc .po-instr { border:var(--rule-box); margin-top:5mm; }
  .quotation-doc .po-instr-title {
    font-weight:700; font-size:var(--fs-md); padding:2px 6px;
    border-bottom:var(--rule);
  }
  .quotation-doc .po-instr-body { padding:4px 6px; }

  .quotation-doc .po-note { margin-top:4mm; }
  .quotation-doc .po-note .pn-lbl { font-weight:700; }

  /* .jobcost / .jc-* / .po-chip / .po-strip are defined in QUOTATION_STYLES.
     The quotation's deal panel renders the job-costing block and cannot import
     this module (purchase -> quotation, never back), so by the rule in
     ABOUT.md §2 the class belongs to the upstream sheet. Every page here loads
     QUOTATION_STYLES, so this module gets them for free. */
</style>
"""


# =============================================================================
# CSS — the two BOQ-side create forms ONLY
# =============================================================================
#
# ⚠ **This is deliberately a SEPARATE constant from `PURCHASE_STYLES`, and the
#   reason is measurable.** `PURCHASE_STYLES` is loaded by `/purchase/view`,
#   which `tests/test_print_golden.py` hashes byte-for-byte — so a rule added
#   there for a form moves the digest of a printed document that did not change.
#   The two pages below are the only ones that draw a picker or a rate column,
#   so their rules load only on them.
#
# `BP.PICKER_CSS` is spliced in at the top exactly as `po_draft.PO_STYLES`
# splices it, because `challan.CHALLAN_STYLES` established that a second
# consumer wraps the same raw CSS afresh rather than importing the first
# consumer's sheet. `.pk-rate` is added *here* rather than to `PICKER_CSS` for
# the same golden reason — `/po/create` renders no rate column and must not
# carry a rule for one.
FROM_BOQ_STYLES = "\n<style>\n" + BP.PICKER_CSS + """
  .pk-rate { width:112px; }
  .pk-rate input {
    width:100%; padding:.28rem .4rem; border:1px solid var(--border);
    border-radius:6px; font:inherit; text-align:right;
  }

  /* The amber band. Same shape and same severity as ra.py's over-claim and
     party-drift bands, and the same rule behind it (DOMAIN.md §6): surface it,
     name it, never silently correct it. Amber, not red — nothing is broken,
     but nothing here may go out unread. */
  .up-warn {
    background:#FFF8E6; border:1px solid #E8C86A; border-left:3px solid #C79200;
    border-radius:var(--radius); padding:.85rem 1.1rem; margin-bottom:1.2rem;
    font-size:.86rem; line-height:1.6;
  }
  .up-warn b { color:#7A5A00; }
  .up-warn .uw-chips { margin-top:.45rem; display:flex; gap:.4rem; flex-wrap:wrap; }

  /* The from-draft line table. product.py's repeating-row pattern, which this
     module's own line editor already uses — there is nothing to PICK when
     converting a draft, because the draft IS the selection. */
  .dl-head, .dl-row {
    display:grid; grid-template-columns:74px 1fr 70px 96px 112px;
    gap:.55rem; align-items:center;
  }
  .dl-head {
    font-size:.7rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.06em; margin-bottom:.4rem;
  }
  .dl-row { padding:.35rem 0; border-bottom:1px solid var(--border); }
  .dl-row input {
    width:100%; padding:.28rem .4rem; border:1px solid var(--border);
    border-radius:6px; font:inherit; text-align:right;
  }
  .dl-no { font-weight:600; font-size:.84rem; }
  .dl-desc { font-size:.84rem; }
  .dl-unit { font-size:.84rem; color:var(--muted); }
  .dl-avail { font-size:.84rem; color:var(--muted); text-align:right;
              font-variant-numeric:tabular-nums; }
  .dl-spec { grid-column:1 / -1; font-size:.82rem; color:var(--muted);
             font-weight:600; padding:.4rem 0 .1rem; }
  @media (max-width:640px){
    .dl-head, .dl-row { grid-template-columns:60px 1fr 90px 100px; }
    .dl-head span:nth-child(4), .dl-row .dl-avail { display:none; }
  }
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
# not braces, so a PO whose `notes` reads `{{ config }}` prints the Flask config
# — including SECRET_KEY — onto a document that goes out to a supplier, and one
# reading `{% for x in y %}` raises a TemplateSyntaxError that 500s the page.
# Both are stored, and `update_purchase()` changes status only (ABOUT.md §5), so
# neither can be edited off the record.
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

@purchase_bp.route("/")
def list_purchases():
    """Register of purchase orders raised, newest number first."""
    purchases = STORE["purchases"]

    status_f = (request.args.get("status") or "").strip()
    rows = sorted(purchases.items(), key=lambda kv: kv[1].get("ref", ""), reverse=True)
    if status_f:
        rows = [(k, v) for k, v in rows
                if (v.get("status") or DEFAULT_STATUS) == status_f]

    dash_url   = url_for("dashboard.index")
    create_url = url_for("purchase.create_purchase")

    committed = sum(float(p.get("grand_total") or 0.0)
                    for p in purchases.values() if is_open(p))
    landed    = sum(float(p.get("grand_total") or 0.0)
                    for p in purchases.values() if p.get("status") == "Received")
    chasing   = sum(1 for p in purchases.values()
                    if (p.get("status") or DEFAULT_STATUS) in CHASE_STATUSES)

    tiles_html = ""
    if purchases:
        tiles_html = f"""
        <div class="pipe-tiles">
          <div class="pipe-tile t-open">
            <div class="pt-lbl">Committed Spend</div>
            <div class="pt-val">&#8377;&nbsp;{committed:,.0f}</div>
            <div class="pt-sub">on {sum(1 for p in purchases.values() if is_open(p))} open order(s)</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Material Received</div>
            <div class="pt-val">&#8377;&nbsp;{landed:,.0f}</div>
            <div class="pt-sub">orders marked complete</div>
          </div>
          <div class="pipe-tile">
            <div class="pt-lbl">Awaiting Acknowledgement</div>
            <div class="pt-val">{chasing}</div>
            <div class="pt-sub">issued, vendor has not confirmed</div>
          </div>
        </div>"""

    # Filter tabs reuse .filter-bar / .filter-tab from P.PIPELINE_STYLES — the
    # same widget the quotation register uses, so the two registers behave
    # identically even though they belong to opposite pipelines.
    tabs = (f'<a href="{url_for("purchase.list_purchases")}" '
            f'class="filter-tab{"" if status_f else " active"}">All '
            f'({len(purchases)})</a>')
    for s in PO_STATUSES:
        n = sum(1 for p in purchases.values()
                if (p.get("status") or DEFAULT_STATUS) == s)
        if not n:
            continue
        on = " active" if status_f == s else ""
        tabs += (f'<a href="{url_for("purchase.list_purchases", status=s)}" '
                 f'class="filter-tab{on}">{P.esc(s)} ({n})</a>')
    tabs_html = (f'<div class="filter-bar"><div class="filter-tabs">{tabs}</div></div>'
                 if purchases else "")

    if rows:
        rows_html = ""
        for pid, po in rows:
            view_url = url_for("purchase.view_purchase", id=pid)
            job = ""
            if po.get("quotation_id") in STORE["quotations"]:
                job = (f'<a class="btn-view" href="'
                       f'{url_for("quotation.view_quotation", id=po["quotation_id"])}">'
                       f'{P.esc(po.get("quotation_ref"))}</a>')
            elif po.get("quotation_ref"):
                job = P.esc(po.get("quotation_ref"))
            else:
                job = '<span class="td-muted">stock</span>'
            rows_html += f"""
            <tr>
              <td class="td-ref">{P.esc(po.get('ref'))}</td>
              <td class="td-muted">{P.esc(po.get('date'))}</td>
              <td class="td-cust">{P.esc(_vendor_of(po))}</td>
              <td class="col-h">{job}</td>
              <td class="col-h">{P.esc(po.get('delivery_date'))}</td>
              <td>{_status_badge(po.get('status'))}</td>
              <td class="td-total">&#8377;&nbsp;{float(po.get('grand_total') or 0):,.0f}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>"""
        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>PO No.</th><th>Date</th><th>Vendor</th>
            <th class="col-h">For Job</th><th class="col-h">Wanted By</th>
            <th>Status</th><th>Order Value</th><th></th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    elif purchases:
        table_html = ('<div class="empty-state"><strong>No purchase orders '
                      f'with status &ldquo;{P.esc(status_f)}&rdquo;</strong></div>')
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128230;</div><br>
          <strong>No purchase orders yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            This is the <b>buy side</b> &mdash; what we order from our vendors,
            separate from the quotation &rarr; proforma &rarr; tax invoice chain.
            Link a PO to a quotation and the deal shows what the job is costing.</p>
          <a href="{create_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">
            Raise the first purchase order</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Purchase Orders")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}</head>
    <body>{_nav()}
    <main>
      {_alert(request.args.get("msg"), request.args.get("type", "success"))}
      <div class="page-top">
        <h1>Purchase <span>Orders</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            {len(purchases)} raised &middot; buy side
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{create_url}" class="btn">+ New purchase order</a>
        </div>
      </div>
      {tiles_html}
      {tabs_html}
      {table_html}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order register</p></footer>
    </main></body></html>"""
    return _page(template)


@purchase_bp.route("/create", methods=["GET", "POST"])
def create_purchase():
    """
    Raise a purchase order on a vendor.

    Unlike the sell-side documents this is **entered from scratch, not derived**
    — there is no upstream record to freeze a copy of, because the decision to
    buy is ours. The optional `quotation_id` says which job it is for, and is
    genuinely optional: stock and consumables are bought with no deal behind
    them.
    """
    from product import ensure_demo_products
    ensure_demo_products()

    f     = request.form
    error = ""

    if request.method == "POST":
        po_date   = (f.get("date") or "").strip()
        qid       = (f.get("quotation_id") or "").strip()
        status    = (f.get("status") or DEFAULT_STATUS).strip()

        # One vendor block, shared with the two BOQ-side create paths. The two
        # refusals and their order are exactly what they always were.
        vendor_fields, vendor_err = _vendor_from(f)

        tax_type  = (f.get("tax_type") or "exempt").strip()
        cgst = P.parse_money(f.get("cgst_rate"))
        igst = P.parse_money(f.get("igst_rate"))

        items, line_err = _parse_lines(f)
        charges, charge_err = _parse_charges(f)
        extra_lines, extra_err = _parse_extra_lines(f)

        if not po_date:
            error = "Purchase order date is required."
        elif vendor_err:
            error = vendor_err
        elif status not in PO_STATUSES:
            error = "Invalid status."
        elif qid and qid not in STORE["quotations"]:
            error = "That quotation no longer exists. Leave the job blank to raise a stock order."
        elif line_err:
            error = line_err
        elif extra_err:
            error = extra_err
        elif charge_err:
            error = charge_err

        if not error:
            # Through `_totals_of()` rather than repeating its three lines here.
            # They were a verbatim copy of it before 28 August 2026, and A3 has
            # to enter the arithmetic in **one** place or the create form and
            # the reprice form compute a different tax base from the same order.
            # The extra free-text lines enter through the same single door, and
            # this route deliberately keeps no private copy of that sum either.
            # SGST always mirrors CGST, exactly as the quotation form forces it.
            (subtotal, taxable_value, tax_info,
             grand, total_qty) = _totals_of(items, tax_type, cgst, igst,
                                            charges, extra_lines)

            q   = STORE["quotations"].get(qid) or {}
            pid = str(uuid.uuid4())
            po = {
                "id":   pid,
                "ref":  _next_ref(po_date),
                "fy":   P.fy_of(po_date),
                "date": po_date,

                # ── Who we are buying FROM. Not a customer. ───────────────
                **vendor_fields,

                # ── Optional soft links upstream. NEVER hard parents. ─────
                # Every one of these may be "" and that is the normal case for
                # an order entered from scratch — stock and consumables get
                # bought with no deal, no schedule and no project behind them.
                # Any code walking purchases must assume nothing.
                "quotation_id":  qid,
                "quotation_ref": q.get("ref", ""),
                "project_id":    (f.get("project_id") or "").strip(),
                "project_name":  _project_name_of((f.get("project_id") or "").strip()),
                "boq_id":        "",
                "boq_ref":       "",
                "boq_rev_no":    0,
                "draft_id":      "",
                "draft_ref":     "",

                # ── What we are buying ────────────────────────────────────
                "line_items": items,
                # Free-text parts that are on no schedule (29 Aug 2026). LINES,
                # not charges: they are inside `subtotal` beside `line_items`,
                # and not one of them carries a `line_id`.
                "extra_lines": extra_lines,
                "subtotal":   subtotal,
                # A3. `subtotal` is the lines — both kinds; `taxable_value` is
                # those plus the taxable charges, and is what the tax was
                # computed on.
                "charges":       charges,
                "taxable_value": taxable_value,
                "tax_type":   tax_type,
                "tax_info":   tax_info,
                "grand_total": grand,
                "total_qty":  total_qty,

                # ── Where and when we want it ─────────────────────────────
                "delivery_date":    (f.get("delivery_date") or "").strip(),
                "delivery_to":      (f.get("delivery_to") or "").strip(),
                "payment_terms":    (f.get("payment_terms") or "").strip(),
                "delivery_terms":   (f.get("delivery_terms") or "").strip(),
                "dispatch_through": (f.get("dispatch_through") or "").strip(),
                "incoterms":        (f.get("incoterms") or "").strip(),

                "status":         status,
                "status_history": [],
                "notes":          (f.get("notes") or "").strip(),
                "company_branch": (f.get("company_branch") or "").strip(),
                "auth_signatory": (f.get("auth_signatory") or "").strip(),
            }
            _log(po, f"Purchase order {po['ref']} raised on "
                     f"{po['vendor_name'] or 'vendor'} for &#8377;{grand:,.0f}.",
                 status_to=status)
            STORE["purchases"][pid] = po

            # Buying material for a job is a real event in that deal's life, so
            # it goes on the quotation's audit trail — the one place the two
            # pipelines touch. It does not change the sales stage.
            if q:
                P.log_event(q, f"Purchase order {po['ref']} raised on "
                               f"{P.esc(po['vendor_name'])} for &#8377;{grand:,.0f}.")

            return redirect(url_for("purchase.view_purchase", id=pid,
                                    msg=f"Purchase order {po['ref']} created.",
                                    type="success"))

    # A3's repeater. On a rejected POST it comes back carrying what was typed;
    # on a fresh GET it comes back carrying `DEFAULT_PO_CHARGE_LABELS` and no
    # amounts, which is a prefill nobody has to use.
    if request.method == "POST":
        charge_section = _charge_section_html(
            [], f.getlist("charge_label"), f.getlist("charge_amount"), f)
        extra_section = _extra_section_html([], posted=f)
    else:
        charge_section = _charge_section_html([])
        extra_section = _extra_section_html([])

    # ── Field values: the user's own input on a failed POST, else default ──
    def _v(name: str, fallback: str = "") -> str:
        if request.method == "POST":
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    v_date   = _v("date", _today())
    v_vendor = _v("vendor_id")
    # ?quotation_id=… lets the quotation's "Raise PO" button pre-select the job.
    # Only honoured on GET; on POST the form field is authoritative.
    v_qid    = _v("quotation_id", request.args.get("quotation_id", ""))
    q        = STORE["quotations"].get(v_qid) or {}
    v_pid    = _v("project_id", q.get("project_id", ""))
    v_vref   = _v("vendor_ref")
    v_del_d  = _v("delivery_date")
    v_del_to = _v("delivery_to", B.COMPANY_ADDR)
    v_notes  = _v("notes")
    v_tax    = _v("tax_type", "cgst_sgst")
    v_cgst   = _v("cgst_rate", "9")
    v_igst   = _v("igst_rate", "18")

    # Rebuild the line rows the user had, then pad to DEFAULT_LINE_ROWS.
    prior_ids   = f.getlist("line_product_id") if request.method == "POST" else []
    prior_qtys  = f.getlist("line_qty")        if request.method == "POST" else []
    prior_rates = f.getlist("line_rate")       if request.method == "POST" else []
    prior_discs = f.getlist("line_discount")   if request.method == "POST" else []
    # `zip` on four lists would silently drop every row if the discount list
    # came in short, so it is indexed separately and a missing one reads blank.
    rows_data = [(i, q, r, prior_discs[n] if n < len(prior_discs) else "")
                 for n, (i, q, r) in enumerate(zip(prior_ids, prior_qtys, prior_rates))]
    while len(rows_data) < DEFAULT_LINE_ROWS:
        rows_data.append(("", "", "", ""))

    lines_html = ""
    for sel, qty, rate, disc in rows_data:
        lines_html += f"""
        <div class="line-row">
          <select name="line_product_id" onchange="fillRate(this)">{_product_options(sel)}</select>
          <input type="number" name="line_qty" value="{P.esc(qty)}" min="0" step="any" placeholder="Qty"/>
          <input type="number" name="line_rate" value="{P.esc(rate)}" min="0" step="0.01" placeholder="Rate"/>
          <input type="number" name="line_discount" value="{P.esc(disc)}" min="0" max="100" step="any" placeholder="0"/>
          <span class="ln-amt">&#8212;</span>
          <button type="button" class="btn-remove-line"
                  onclick="this.closest('.line-row').remove(); recalc();">&#215;</button>
        </div>"""

    # Rates the vendor charges us are NOT the catalogue's base_price (that is a
    # sell price), so the picker only suggests it — the field stays editable and
    # is never overwritten once the user has typed something.
    catalog_rates = "{" + ",".join(
        f'"{pid}":{float(p.get("base_price") or 0):.2f}'
        for pid, p in STORE["products"].items()
    ) + "}"

    # The seeded prefill table for the extra-line typeahead, keyed by the SAME
    # normalisation `po_parts._norm()` applies — the browser and the server have
    # to agree on what "matches", because the server decides from the same table
    # whether a rate is still the assumed one.
    # ⚠ Through `P.json_for_script()`, not `json.dumps` (ABOUT.md §7.9e).
    seed_json = P.json_for_script({
        PP._norm(name): {"u": row["unit"], "r": float(row["assumed_rate"])}
        for name, row in PP.PARTS.items()
    })

    q_opts = '<option value="">&#8212; none / stock purchase &#8212;</option>'
    for qid_, q_ in sorted(STORE["quotations"].items(),
                           key=lambda kv: kv[1].get("ref", ""), reverse=True):
        sel = " selected" if qid_ == v_qid else ""
        q_opts += (f'<option value="{P.esc(qid_)}"{sel}>{P.esc(q_.get("ref"))} '
                   f'&middot; {P.esc(q_.get("account_name") or "unnamed")}</option>')

    p_opts = '<option value="">&#8212; none &#8212;</option>'
    for proj_id, proj in sorted(STORE["projects"].items(),
                                key=lambda kv: kv[1].get("name", "").lower()):
        sel = " selected" if proj_id == v_pid else ""
        p_opts += f'<option value="{P.esc(proj_id)}"{sel}>{P.esc(proj.get("name"))}</option>'

    status_opts = "".join(
        f'<option{" selected" if s == _v("status", DEFAULT_STATUS) else ""}>{s}</option>'
        for s in PO_STATUSES if s != "Cancelled"
    )

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("New Purchase Order")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>New <span>Purchase Order</span></h1>
        <a href="{url_for("purchase.list_purchases")}" class="btn btn-ghost">&#8592; All Purchase Orders</a>
      </div>

      {_alert(error, "error")}

      <div class="buy-note">
        This is the <b>buy side</b> &mdash; an order <b>we place on a vendor</b>,
        not a document for a customer.
        <div class="bn-sub">The GST here is <b>input tax we pay</b>, the opposite
          side of the ledger from a tax invoice. Nothing on this page touches a
          proforma or a tax invoice. The next number is {P.esc(_next_ref(v_date))}.</div>
      </div>

      <form method="POST" action="{url_for("purchase.create_purchase")}">

        <div class="form-section">
          <div class="section-title">Order</div>
          <div class="fg3">
            <div class="form-group">
              <label for="date">PO Date *</label>
              <input type="date" id="date" name="date" value="{P.esc(v_date)}" required/>
            </div>
            <div class="form-group">
              <label for="vendor_id">Vendor *</label>
              <select id="vendor_id" name="vendor_id" required>
                {picker_options("— choose vendor —", only_types=("vendor",), selected=v_vendor)}
              </select>
              <small class="field-hint">From the address book, vendors only.
                Add one at <a href="{url_for("address.add_address")}">Address Book</a>
                if the supplier is not listed.</small>
            </div>
            <div class="form-group">
              <label for="status">Status</label>
              <select id="status" name="status">{status_opts}</select>
              <small class="field-hint">Start as Draft while you are still
                pricing it; Issued once it has gone to the vendor.</small>
            </div>
            <div class="form-group">
              <label for="quotation_id">For Job <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <select id="quotation_id" name="quotation_id">{q_opts}</select>
              <small class="field-hint">Link it to the quotation this material is
                for and the deal shows quoted value against what it costs us.
                Leave blank for stock.</small>
            </div>
            <div class="form-group">
              <label for="project_id">Project <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <select id="project_id" name="project_id">{p_opts}</select>
            </div>
            <div class="form-group">
              <label for="vendor_ref">Vendor's Offer / Quote Ref</label>
              <input type="text" id="vendor_ref" name="vendor_ref" value="{P.esc(v_vref)}"
                     placeholder="their quotation no., if any"/>
            </div>
            <div class="form-group">
              <label for="delivery_date">Wanted By</label>
              <input type="date" id="delivery_date" name="delivery_date" value="{P.esc(v_del_d)}"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Items ordered</div>
          <div class="line-head">
            <span>Item</span><span>Qty</span><span>Rate (&#8377;)</span>
            <span>Disc %</span>
            <span style="text-align:right;">Amount</span><span></span>
          </div>
          <div id="lines">{lines_html}</div>
          <button type="button" class="btn btn-ghost" onclick="addLine()"
                  style="margin-top:.3rem;">+ Add item</button>
          <div class="po-total-strip">
            <span>Taxable Value <b id="po-sub">&#8377; 0</b></span>
            <span>Tax <b id="po-tax">&#8377; 0</b></span>
            <span>Order Value <b id="po-grand">&#8377; 0</b></span>
          </div>
        </div>

        {extra_section}

        {charge_section}

        <div class="form-section">
          <div class="section-title">Tax the vendor will charge us</div>
          <div class="fg3">
            <div class="form-group">
              <label for="tax_type">Tax Type</label>
              <select id="tax_type" name="tax_type" onchange="recalc()">
                <option value="cgst_sgst"{" selected" if v_tax == "cgst_sgst" else ""}>CGST + SGST (intra-state)</option>
                <option value="igst"{" selected" if v_tax == "igst" else ""}>IGST (inter-state)</option>
                <option value="exempt"{" selected" if v_tax == "exempt" else ""}>Exempt / Nil</option>
              </select>
            </div>
            <div class="form-group">
              <label for="cgst_rate">CGST % <span style="font-weight:500;text-transform:none;">(SGST matches)</span></label>
              <input type="number" id="cgst_rate" name="cgst_rate" value="{P.esc(v_cgst)}"
                     min="0" step="any" oninput="recalc()"/>
            </div>
            <div class="form-group">
              <label for="igst_rate">IGST %</label>
              <input type="number" id="igst_rate" name="igst_rate" value="{P.esc(v_igst)}"
                     min="0" step="any" oninput="recalc()"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Terms &amp; delivery</div>
          <div class="fg2">
            <div class="form-group">
              <label for="payment_terms">Payment Terms</label>
              {_sel_opts("payment_terms", _PAY_TERMS, _PAY_TERMS[0], _v("payment_terms"))}
            </div>
            <div class="form-group">
              <label for="delivery_terms">Terms of Delivery</label>
              {_sel_opts("delivery_terms", _DEL_TERMS, _DEL_TERMS[0], _v("delivery_terms"))}
            </div>
            <div class="form-group">
              <label for="dispatch_through">Dispatch Through</label>
              {_sel_opts("dispatch_through", _DISPATCH, _DISPATCH[0], _v("dispatch_through"))}
            </div>
            <div class="form-group">
              <label for="incoterms">Incoterms</label>
              {_sel_opts("incoterms", _INCOTERMS, _INCOTERMS[0], _v("incoterms"))}
            </div>
            <div class="form-group span2">
              <label for="delivery_to">Deliver To</label>
              <textarea id="delivery_to" name="delivery_to" rows="3"
                placeholder="our stores, or the project site">{P.esc(v_del_to)}</textarea>
              <small class="field-hint">Where the vendor sends the material.
                Defaults to our registered address.</small>
            </div>
            <div class="form-group span2">
              <label for="notes">Note on the order <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <input type="text" id="notes" name="notes" value="{P.esc(v_notes)}"
                     placeholder="e.g. Urgent — required at site by month end"/>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn">Raise Purchase Order</button>
          <a href="{url_for("purchase.list_purchases")}" class="btn btn-ghost">Cancel</a>
        </div>
      </form>

      <template id="line-tpl">
        <div class="line-row">
          <select name="line_product_id" onchange="fillRate(this)">{_product_options()}</select>
          <input type="number" name="line_qty" min="0" step="any" placeholder="Qty"/>
          <input type="number" name="line_rate" min="0" step="0.01" placeholder="Rate"/>
          <input type="number" name="line_discount" min="0" max="100" step="any" placeholder="0"/>
          <span class="ln-amt">&#8212;</span>
          <button type="button" class="btn-remove-line"
                  onclick="this.closest('.line-row').remove(); recalc();">&#215;</button>
        </div>
      </template>

      <template id="xline-tpl">{_extra_row_html()}</template>

      <script>
        var RATES = {catalog_rates};

        /* The seeded prefill list, normalised name -> {{u: unit, r: rate}}.
           ⚠ Every `r` here is an ASSUMED PLACEHOLDER, not a quoted price — see
           po_parts.py. It is offered into an empty box and flagged on screen
           until somebody replaces it. Through json_for_script(), never
           json.dumps: this is JSON going into a <script> block (ABOUT.md
           §7.9e). */
        var XSEED = {seed_json};

        function addLine() {{
          var tpl = document.getElementById('line-tpl');
          document.getElementById('lines').appendChild(tpl.content.cloneNode(true));
          bind();
        }}

        function addExtra() {{
          var tpl = document.getElementById('xline-tpl');
          document.getElementById('xlines').appendChild(tpl.content.cloneNode(true));
          recalc();
        }}

        /* The same normalisation po_parts._norm() does: lowercase, and every
           run of whitespace collapsed to one. The two have to agree, because
           the server decides whether a rate is still the assumed one by looking
           the description up in the same table. */
        function xlNorm(s) {{
          return String(s || '').toLowerCase().split(/\\s+/).filter(Boolean).join(' ');
        }}

        /* Suggest the seeded unit and rate, never impose them: an empty box is
           filled, a typed one is left alone. That is fillRate()'s contract
           above, and it is what makes "the assumed mark clears the moment the
           rate is edited" true — the operator's own figure is never
           overwritten. */
        function xlFill(input) {{
          var hit = XSEED[xlNorm(input.value)];
          if (!hit) {{ recalc(); return; }}
          var row = input.closest('.xl-row');
          var unit = row.querySelector('input[name="extra_unit"]');
          var rate = row.querySelector('input[name="extra_rate"]');
          if (unit && !unit.value) {{ unit.value = hit.u; }}
          if (rate && !rate.value) {{ rate.value = hit.r.toFixed(2); }}
          recalc();
        }}

        /* Suggest the catalogue price, never impose it: base_price is what we
           SELL at, and what a vendor charges us is a different number. Only an
           empty rate box is filled, so a typed figure is never overwritten. */
        function fillRate(sel) {{
          var row = sel.closest('.line-row');
          var rate = row.querySelector('input[name="line_rate"]');
          if (rate && !rate.value && RATES[sel.value] !== undefined) {{
            rate.value = RATES[sel.value].toFixed(2);
          }}
          recalc();
        }}

        function recalc() {{
          var sub = 0;
          document.querySelectorAll('#lines .line-row').forEach(function (row) {{
            var q = parseFloat(row.querySelector('input[name="line_qty"]').value) || 0;
            var r = parseFloat(row.querySelector('input[name="line_rate"]').value) || 0;
            var dEl = row.querySelector('input[name="line_discount"]');
            var d = dEl ? (parseFloat(dEl.value) || 0) : 0;
            if (d < 0) d = 0;
            if (d > 100) d = 100;
            /* The same shape as _line_total(): discount the product, then round
               once. The server is the authority and recomputes it on POST --
               this strip only has to agree with what will be stored. */
            var amt = Math.round(q * r * (1 - d / 100) * 100) / 100;
            sub += amt;
            var cell = row.querySelector('.ln-amt');
            if (cell) cell.textContent = amt ? amt.toLocaleString('en-IN',
              {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) : '\\u2014';
          }});

          /* Extra free-text lines are LINES: they join `sub`, the same figure
             the item rows above join, and NOT the charge split below. Same
             _line_total() shape again — discount the product, then round once. */
          document.querySelectorAll('#xlines .xl-row').forEach(function (row) {{
            var q = parseFloat(row.querySelector('input[name="extra_qty"]').value) || 0;
            var r = parseFloat(row.querySelector('input[name="extra_rate"]').value) || 0;
            var dEl = row.querySelector('input[name="extra_discount"]');
            var d = dEl ? (parseFloat(dEl.value) || 0) : 0;
            if (d < 0) d = 0;
            if (d > 100) d = 100;
            var amt = Math.round(q * r * (1 - d / 100) * 100) / 100;
            sub += amt;
            var cell = row.querySelector('.ln-amt');
            if (cell) cell.textContent = amt ? amt.toLocaleString('en-IN',
              {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) : '\\u2014';
          }});

          /* A3: the same split the server does in _totals_of(). A taxable
             charge joins the base BEFORE tax; an untaxed one is added after it.
             The strip is a preview and the server is the authority, but a
             preview that ignored the charges would disagree with the document
             it is previewing. */
          var chTax = 0, chEx = 0;
          document.querySelectorAll('.chg-row').forEach(function (row) {{
            var a = parseFloat(row.querySelector('input[name="charge_amount"]').value) || 0;
            if (a <= 0) return;
            var box = row.querySelector('input[type="checkbox"]');
            if (box && box.checked) {{ chTax += a; }} else {{ chEx += a; }}
          }});
          var base = Math.round((sub + chTax) * 100) / 100;

          var type = document.getElementById('tax_type').value;
          var tax = 0;
          if (type === 'cgst_sgst') {{
            tax = base * (parseFloat(document.getElementById('cgst_rate').value) || 0) / 100 * 2;
          }} else if (type === 'igst') {{
            tax = base * (parseFloat(document.getElementById('igst_rate').value) || 0) / 100;
          }}

          var f = function (v) {{ return '\\u20B9 ' + v.toLocaleString('en-IN',
            {{maximumFractionDigits: 0}}); }};
          document.getElementById('po-sub').textContent   = f(base);
          document.getElementById('po-tax').textContent   = f(tax);
          document.getElementById('po-grand').textContent = f(base + tax + chEx);
        }}

        /* Only the item rows need this: every extra-line input carries its own
           inline oninput (recalc, or xlFill on the description), so a row added
           by cloning the template is live the moment it lands. */
        function bind() {{
          document.querySelectorAll('#lines input').forEach(function (el) {{
            el.oninput = recalc;
          }});
        }}

        bind();
        recalc();
      </script>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order</p></footer>
    </main></body></html>"""
    return _page(template)


# =============================================================================
# RAISING A REAL PO FROM THE BOQ CHAIN
# =============================================================================
#
# Until this existed, work raised from a bill of quantities dead-ended at a
# **draft** PO (`SF/DPO/nnnn`) — a rate-less sheet sent to a supplier to be
# priced, with no way back. The priced copy came in on paper and was re-keyed
# into `/purchase/create` from scratch, with no link between the two documents
# and, more expensively, **no link from the money we actually spent to the
# project we spent it on** (ABOUT.md §7, the largest open gap in that list).
#
# Two routes close it, and both land in the ordinary register with the ordinary
# `SF/PO/26-27/nnnn` series:
#
#   /purchase/from-boq/<boq_id>       tick the lines, price them, order them
#   /purchase/from-draft/<draft_id>   the draft comes back priced; make it real
#
# Neither introduces a draft state, an approval step or a status of its own. The
# record they write is the same record `/purchase/create` writes, with three
# optional fields filled in — which is why a PO that has none of them is
# completely unaffected and renders byte-for-byte what it always did.

def _form_values(f, is_post: bool, **defaults) -> dict:
    """
    The order's own fields — the user's input on a rejected POST, else defaults.

    `create_purchase()`'s `_v()` contract, which is `address._validate()`'s:
    **a rejected form re-renders with what was typed** and nothing is written.
    """
    def v(name, fallback=""):
        if is_post:
            return (f.get(name) or "").strip()
        return str(fallback or "").strip()

    return {
        "date":             v("date", defaults.get("date") or _today()),
        "vendor_id":        v("vendor_id", defaults.get("vendor_id", "")),
        "status":           v("status", DEFAULT_STATUS),
        "vendor_ref":       v("vendor_ref", defaults.get("vendor_ref", "")),
        "delivery_date":    v("delivery_date"),
        "delivery_to":      v("delivery_to",
                              defaults.get("delivery_to") or B.COMPANY_ADDR),
        "tax_type":         v("tax_type", "cgst_sgst"),
        "cgst_rate":        v("cgst_rate", "9"),
        "igst_rate":        v("igst_rate", "18"),
        "payment_terms":    v("payment_terms"),
        "delivery_terms":   v("delivery_terms"),
        "dispatch_through": v("dispatch_through"),
        "incoterms":        v("incoterms"),
        "notes":            v("notes", defaults.get("notes", "")),
    }


def _upstream_form(*, title: str, action: str, back_html: str, intro_html: str,
                   banner_html: str, lines_section: str, data: dict,
                   error: str, onsubmit: str = "true") -> str:
    """
    One form, two routes.

    The order's own fields — date, vendor, status, tax, terms — are identical
    whichever upstream document the lines came from, so they are written once.
    Only the **lines** differ: `/from-boq` renders `boqpick`'s grid, `/from-draft`
    renders the draft's own rows, because there is nothing left to pick once a
    draft has been raised.

    Every widget is the shared one: `_vendor_field()` for the supplier, and
    `_sel_opts` over `_PAY_TERMS` / `_DEL_TERMS` / `_DISPATCH` / `_INCOTERMS` for
    the terms — "By Road Transport" must mean the same thing whichever way the
    goods move, and whichever form asked.
    """
    status_opts = "".join(
        f'<option{" selected" if s == data["status"] else ""}>{s}</option>'
        for s in PO_STATUSES if s != "Cancelled"
    )
    return _page(f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title(title)}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}{FROM_BOQ_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>{title}</h1>
        <div style="display:flex;gap:.7rem;flex-wrap:wrap;">{back_html}</div>
      </div>

      {_alert(error, "error")}
      {banner_html}

      <div class="buy-note">
        This is the <b>buy side</b> &mdash; a <b>real purchase order we place on a
        vendor</b>, in the ordinary register and the ordinary series.
        <div class="bn-sub">{intro_html}
          The next number is {P.esc(_next_ref(data["date"]))}.</div>
      </div>

      <form method="POST" action="{action}" onsubmit="return {onsubmit};">
        <input type="hidden" name="po_json" id="po_json" value=""/>

        <div class="form-section">
          <div class="section-title">Order</div>
          <div class="fg3">
            <div class="form-group">
              <label for="date">PO Date *</label>
              <input type="date" id="date" name="date" value="{P.esc(data['date'])}" required/>
            </div>
            {_vendor_field(data["vendor_id"])}
            <div class="form-group">
              <label for="status">Status</label>
              <select id="status" name="status">{status_opts}</select>
              <small class="field-hint">The ordinary lifecycle &mdash; Draft while
                you are still pricing it, Issued once it has gone to the vendor.
                There is no extra approval step on this path.</small>
            </div>
            <div class="form-group">
              <label for="vendor_ref">Vendor's Offer / Quote Ref</label>
              <input type="text" id="vendor_ref" name="vendor_ref"
                     value="{P.esc(data['vendor_ref'])}"
                     placeholder="their quotation no., if any"/>
            </div>
            <div class="form-group">
              <label for="delivery_date">Wanted By</label>
              <input type="date" id="delivery_date" name="delivery_date"
                     value="{P.esc(data['delivery_date'])}"/>
            </div>
          </div>
        </div>

        {lines_section}

        <div class="form-section">
          <div class="section-title">Tax the vendor will charge us</div>
          <div class="fg3">
            <div class="form-group">
              <label for="tax_type">Tax Type</label>
              <select id="tax_type" name="tax_type">
                <option value="cgst_sgst"{" selected" if data["tax_type"] == "cgst_sgst" else ""}>CGST + SGST (intra-state)</option>
                <option value="igst"{" selected" if data["tax_type"] == "igst" else ""}>IGST (inter-state)</option>
                <option value="exempt"{" selected" if data["tax_type"] == "exempt" else ""}>Exempt / Nil</option>
              </select>
            </div>
            <div class="form-group">
              <label for="cgst_rate">CGST % <span style="font-weight:500;text-transform:none;">(SGST matches)</span></label>
              <input type="number" id="cgst_rate" name="cgst_rate"
                     value="{P.esc(data['cgst_rate'])}" min="0" step="any"/>
            </div>
            <div class="form-group">
              <label for="igst_rate">IGST %</label>
              <input type="number" id="igst_rate" name="igst_rate"
                     value="{P.esc(data['igst_rate'])}" min="0" step="any"/>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title">Terms &amp; delivery</div>
          <div class="fg2">
            <div class="form-group">
              <label for="payment_terms">Payment Terms</label>
              {_sel_opts("payment_terms", _PAY_TERMS, _PAY_TERMS[0], data["payment_terms"])}
            </div>
            <div class="form-group">
              <label for="delivery_terms">Terms of Delivery</label>
              {_sel_opts("delivery_terms", _DEL_TERMS, _DEL_TERMS[0], data["delivery_terms"])}
            </div>
            <div class="form-group">
              <label for="dispatch_through">Dispatch Through</label>
              {_sel_opts("dispatch_through", _DISPATCH, _DISPATCH[0], data["dispatch_through"])}
            </div>
            <div class="form-group">
              <label for="incoterms">Incoterms</label>
              {_sel_opts("incoterms", _INCOTERMS, _INCOTERMS[0], data["incoterms"])}
            </div>
            <div class="form-group span2">
              <label for="delivery_to">Deliver To</label>
              <textarea id="delivery_to" name="delivery_to" rows="3"
                placeholder="our stores, or the project site">{P.esc(data['delivery_to'])}</textarea>
            </div>
            <div class="form-group span2">
              <label for="notes">Note on the order <span style="font-weight:500;text-transform:none;">(optional)</span></label>
              <input type="text" id="notes" name="notes" value="{P.esc(data['notes'])}"
                     placeholder="e.g. Urgent — required at site by month end"/>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn">Raise Purchase Order</button>
          {back_html}
        </div>
      </form>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order</p></footer>
    </main></body></html>""")


def _write_upstream_po(*, data: dict, vendor_fields: dict, items: list,
                       boq: dict = None, project_id: str = "",
                       project_name: str = "", draft: dict = None,
                       origin: str = "") -> dict:
    """
    Write the purchase order. **One record shape, whichever route got here.**

    It is the same record `create_purchase()` writes — same collection, same
    `SF/PO/26-27/nnnn` series, same lifecycle, same audit trail. The only
    difference is that three optional fields are filled in. There is no draft
    flag, no approval gate and no status this app would have to teach anybody to
    clear; a purchase order raised from a schedule is a purchase order.
    """
    boq = boq or {}
    tax_type = data["tax_type"]
    cgst = P.parse_money(data["cgst_rate"])
    igst = P.parse_money(data["igst_rate"])
    # No charge repeater on the two upstream forms: they are derived documents
    # whose job is to carry a schedule's lines across without re-entry, and a
    # charge is added afterwards on `/purchase/edit/<id>` like any other money
    # that was not on the schedule. `charges` is still written, as `[]`, so the
    # key exists on every order this module creates.
    charges = []
    # ⚠ **No extra-line repeater here either, and it is the same call, made
    #   again deliberately.** `/purchase/from-boq` and `/purchase/from-draft`
    #   are picker flows over a schedule: their whole job is to carry ticked
    #   lines across without re-entry. Bolting a free-text surface onto a picker
    #   is a second design — two ways of adding a line on one form, one of which
    #   traces to the schedule and one of which cannot — and it is not what
    #   either page is for. A part that is on no schedule is added afterwards on
    #   `/purchase/edit/<id>`, exactly as a charge is. `extra_lines` is still
    #   written, as `[]`, so the key exists on every order this module creates.
    #   **A recorded deviation, matching the call A3 made, not an omission.**
    extra_lines = []
    (subtotal, taxable_value, tax_info,
     grand, total_qty) = _totals_of(items, tax_type, cgst, igst,
                                    charges, extra_lines)

    pid = str(uuid.uuid4())
    po = {
        "id":   pid,
        "ref":  _next_ref(data["date"]),
        "fy":   P.fy_of(data["date"]),
        "date": data["date"],

        **vendor_fields,

        # ── The upstream links. All optional; all STORED, never derived. ──
        "quotation_id":  "",
        "quotation_ref": "",
        "boq_id":        str(boq.get("id") or ""),
        "boq_ref":       str(boq.get("ref") or ""),
        "boq_rev_no":    int(boq.get("rev_no") or 0),
        "project_id":    project_id,
        "project_name":  project_name,
        "draft_id":      str((draft or {}).get("id") or ""),
        "draft_ref":     str((draft or {}).get("ref") or ""),

        "line_items":  items,
        "extra_lines": extra_lines,
        "subtotal":    subtotal,
        "charges":       charges,
        "taxable_value": taxable_value,
        "tax_type":    tax_type,
        "tax_info":    tax_info,
        "grand_total": grand,
        "total_qty":   total_qty,

        "delivery_date":    data["delivery_date"],
        "delivery_to":      data["delivery_to"],
        "payment_terms":    data["payment_terms"],
        "delivery_terms":   data["delivery_terms"],
        "dispatch_through": data["dispatch_through"],
        "incoterms":        data["incoterms"],

        "status":         data["status"],
        "status_history": [],
        "notes":          data["notes"],
        "company_branch": "",
        "auth_signatory": "",
    }
    _log(po, f"Purchase order {po['ref']} raised on "
             f"{po.get('vendor_name') or 'vendor'} for &#8377;{grand:,.0f}"
             f"{origin}.",
         status_to=data["status"])
    STORE["purchases"][pid] = po
    return po


@purchase_bp.route("/from-boq/<boq_id>", methods=["GET", "POST"])
def from_boq(boq_id: str):
    """
    Raise a **real** purchase order against a bill of quantities.

    The grid is `boqpick.py`'s — the same one `/po/create` and `/dc/create`
    render, imported rather than copied a third time, which is the entire reason
    that leaf exists. What this route adds to it is a **rate box per line**,
    prefilled from the schedule's `supply_base_rate` and editable.

    Three rules worth knowing before editing:

    * **The installation track is excluded** (`INCLUDE_INSTALL_TRACK`). A BOQ
      line is priced to supply and to install; only the first is goods we buy.
    * **Matching is on `line_id`.** `item_no` is a display label and is not
      unique even within a section — the seeded Sify schedule has 87 priced
      lines and 77 distinct item numbers.
    * **A superseded revision is refused at the route**, exactly as `/ra/create`
      and `/dc/create` refuse one. `/boq/view` also hides the link, but a link
      is not a guard.
    """
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return redirect(url_for("boq.list_boqs",
                                msg="Choose a bill of quantities to order against.",
                                type="error"))
    if boq_id in BQ.superseded_ids():
        return redirect(url_for("boq.view_boq", id=boq_id,
                                msg="That schedule has been superseded. Raise the "
                                    "purchase order against the current revision.",
                                type="error"))

    project_id, project_name = _project_of_boq(boq)
    is_post = request.method == "POST"
    f = request.form
    data = _form_values(f, is_post)
    error = ""
    chosen = qty_of = rate_of = None

    if is_post:
        vendor_fields, error = _vendor_from(f)
        if not data["date"]:
            error = "Purchase order date is required."
        elif data["status"] not in PO_STATUSES:
            error = error or "Invalid status."

        picked, line_err = ([], "") if error else BP.picked_lines(
            f.get("po_json") or "", boq, with_pcs=False, with_rate=True,
            max_lines=BQ.MAX_LINES,
            empty_msg=("No lines are ticked. A purchase order with nothing on "
                       "it is not a document — tick at least one line, or cancel."),
            cap_msg="Raise more than one order.")
        error = error or line_err

        items, shape_err = ([], "") if error else _po_lines_from_picked(picked, boq)
        error = error or shape_err

        if not error:
            po = _write_upstream_po(
                data=data, vendor_fields=vendor_fields, items=items, boq=boq,
                project_id=project_id, project_name=project_name,
                origin=f", against {boq.get('ref') or 'a schedule'}")
            return redirect(url_for("purchase.view_purchase", id=po["id"],
                                    msg=f"Purchase order {po['ref']} created "
                                        f"against {boq.get('ref') or 'the schedule'}.",
                                    type="success"))

        # Hand the operator back exactly what they ticked and typed.
        chosen, qty_of, rate_of = _replay_picked(f.get("po_json") or "")

    boq_ref = P.esc(boq.get("ref") or "")
    proj_bit = (f' &middot; project <b>{P.esc(project_name)}</b>'
                if project_name else
                ' &middot; <span style="color:var(--muted);">this schedule is not '
                'attached to a project, so the order will carry none</span>')

    lines_section = BP.grid_html(
        boq,
        title="Lines to order",
        intro_html=f"""        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line is ticked to start with, because most orders are the whole
          schedule. Untick what this supplier is not supplying, and change a
          quantity where you want less than the schedule shows.
          <b>Rates open at the schedule's supply base rate</b> &mdash; what the job
          was costed at — and are yours to edit; what you leave in the box is what
          is stored. The <b>installation</b> rates are labour and are deliberately
          not offered here.
        </p>""",
        qty_label="Order qty",
        qty_aria="Order quantity",
        empty_note=("Nothing is ticked. A purchase order with no lines on it "
                    "is not a document."),
        payload_id="po_json",
        doc_word="purchase order",
        chosen=chosen,
        qty_of=qty_of,
        with_rate=True,
        rate_of=rate_of,
        rate_label="Rate (&#8377;)",
        rate_aria="Rate")

    back_html = (f'<a href="{url_for("boq.view_boq", id=boq_id)}" '
                 f'class="btn btn-ghost">&#8592; {boq_ref}</a>')
    return _upstream_form(
        title="Purchase Order from BOQ",
        action=url_for("purchase.from_boq", boq_id=boq_id),
        back_html=back_html,
        intro_html=(f'Against <b>{boq_ref}</b> &middot; '
                    f'{P.esc(boq.get("project_name") or "")}{proj_bit}.'),
        banner_html="",
        lines_section=lines_section,
        data=data,
        error=error,
        onsubmit="saveJSON()")


def _replay_picked(raw: str) -> tuple:
    """
    `(chosen, qty_of, rate_of)` off a rejected POST, so nothing typed is lost.

    `po_draft.create_po()`'s arrangement, with the rate column added. A form
    that throws the operator's ticks away on a validation failure is worse than
    no validation on a 97-line schedule.
    """
    import json
    try:
        rows = (json.loads(raw or "{}").get("lines") or [])
    except (ValueError, TypeError):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    return ({BQ._line_id(r.get("line_id")) for r in rows},
            {BQ._line_id(r.get("line_id")): r.get("qty") for r in rows},
            {BQ._line_id(r.get("line_id")): r.get("rate") for r in rows})


@purchase_bp.route("/from-draft/<draft_id>", methods=["GET", "POST"])
def from_draft(draft_id: str):
    """
    Turn a priced draft PO into a real one.

    ⚠ **This route lives here and not in `po_draft.py`, deliberately.** It
    writes a `purchases` record, so it belongs to the module that owns that
    shape; putting it there would force `po_draft.py` to import this module and
    couple two document modules for no reason at all. `po_draft.py` links here
    by URL — the one-way trick, used a seventh time.

    **The draft is kept, never deleted.** It is the record of what was sent out
    for pricing, and destroying it the moment it succeeds would throw away the
    only evidence of what was asked and of whom.

    **Converting twice is allowed and warned about.** Two purchase orders off one
    request for quotation is an ordinary thing when an order is split between
    suppliers or placed in two lots, so this warns in an amber band naming the
    orders already raised — `ra.prev_balance_drift()`'s and `ra.party_drift()`'s
    shape — and lets it through. DOMAIN.md §6: surface it, name it, never
    silently refuse it.
    """
    drafts = STORE.get("purchase_orders") or {}
    draft = drafts.get(draft_id)
    if not draft:
        return redirect(url_for("po_draft.list_pos",
                                msg="That draft PO no longer exists.", type="error"))

    # The BOQ may legitimately be gone; the draft is a snapshot and still
    # converts. Its rates then have no base to fall back on, which is stated on
    # the form rather than silently producing zeros.
    boq = (STORE.get("boqs") or {}).get(str(draft.get("boq_id") or "")) or {}
    base_of = {}
    for lid, li in _boq_lines_by_id(boq).items():
        base = li.get(RATE_PREFILL_FIELD)
        base_of[lid] = None if base is None else float(base)

    project_id, project_name = _project_of_boq(boq)

    # Only rows with something to buy. A draft carries its specification headers
    # for the supplier to read, and those come across unchanged.
    rows = list(draft.get("items") or [])

    is_post = request.method == "POST"
    f = request.form
    # The draft's own vendor prefills the picker ONLY when it came from the
    # address book. A typed one-off supplier has no id to select, and this
    # document may not carry one — see `_vendor_from()`.
    data = _form_values(f, is_post,
                        vendor_id=(draft.get("vendor_id") or ""),
                        delivery_to=draft.get("delivery_to") or "",
                        notes=draft.get("notes") or "")
    error = ""
    posted_qty, posted_rate = {}, {}

    if is_post:
        posted_qty = dict(zip(f.getlist("dl_line_id"), f.getlist("dl_qty")))
        posted_rate = dict(zip(f.getlist("dl_line_id"), f.getlist("dl_rate")))

        vendor_fields, error = _vendor_from(f)
        if not data["date"]:
            error = "Purchase order date is required."
        elif data["status"] not in PO_STATUSES:
            error = error or "Invalid status."

        items = []
        if not error:
            for row in rows:
                lid = str(row.get("line_id") or "")
                if row.get("is_header"):
                    items.append({
                        "type": "item", "is_header": True, "line_id": lid,
                        "name": str(row.get("description") or ""),
                        "part_no": str(row.get("item_no") or ""),
                        "hsn": "", "qty": 0.0, "unit": "", "price": 0.0,
                        "total": 0.0, "depth": 0,
                    })
                    continue
                qty = BQ._num(posted_qty.get(lid), None)
                if qty is None or qty < 0:
                    qty = float(row.get("qty") or 0.0)
                if qty <= 0:
                    error = (f"Quantity for item {row.get('item_no') or '(unnumbered)'} "
                             f"must be greater than zero.")
                    break
                rate = BQ._num(posted_rate.get(lid), None)
                if rate is None or rate < 0:
                    rate = _draft_rate_of(row, base_of)
                src = _boq_lines_by_id(boq).get(lid) or {}
                items.append({
                    "type": "item", "is_header": False, "line_id": lid,
                    "name": str(row.get("description") or ""),
                    "part_no": str(row.get("item_no") or ""),
                    "hsn": str(src.get("supply_hsn") or ""),
                    "qty": float(qty), "unit": str(row.get("unit") or ""),
                    "price": float(rate),
                    "total": round(float(rate) * float(qty), 2),
                    "depth": 0,
                })
            if not error and not any(not r["is_header"] for r in items):
                error = "This draft PO has no lines to order."

        if not error:
            po = _write_upstream_po(
                data=data, vendor_fields=vendor_fields, items=items, boq=boq,
                project_id=project_id, project_name=project_name, draft=draft,
                origin=f", converted from draft {draft.get('ref') or ''}".rstrip())
            # The link back, on the draft. A LIST, not a scalar: converting twice
            # is permitted, and a single field would let the second conversion
            # quietly erase the first one's trail.
            draft.setdefault("converted_po_ids", []).append(po["id"])
            return redirect(url_for("purchase.view_purchase", id=po["id"],
                                    msg=f"Purchase order {po['ref']} created from "
                                        f"draft {draft.get('ref') or 'PO'}.",
                                    type="success"))

    # ── The lines. Not the picker: a draft IS the selection. ──────────────
    lines_html = ""
    for row in rows:
        lid = P.esc(str(row.get("line_id") or ""))
        if row.get("is_header"):
            lines_html += (f'<div class="dl-row"><div class="dl-spec">'
                           f'{P.esc(row.get("item_no") or "")} &middot; '
                           f'{P.esc(str(row.get("description") or "")[:160])}</div></div>')
            continue
        raw_lid = str(row.get("line_id") or "")
        qty_v = posted_qty.get(raw_lid)
        if qty_v is None:
            qty_v = BQ._fmt_qty(float(row.get("qty") or 0.0))
        rate_v = posted_rate.get(raw_lid)
        if rate_v is None:
            r = _draft_rate_of(row, base_of, blank_when_unknown=True)
            rate_v = "" if r is None else f"{float(r):.2f}"
        lines_html += f"""
        <div class="dl-row">
          <span class="dl-no">{P.esc(row.get("item_no") or "")}</span>
          <span class="dl-desc">{P.esc(" ".join(str(row.get("description") or "").split())[:180])}</span>
          <span class="dl-unit">{P.esc(row.get("unit") or "")}</span>
          <input type="hidden" name="dl_line_id" value="{lid}"/>
          <input type="text" inputmode="decimal" name="dl_qty" value="{P.esc(qty_v)}"
                 aria-label="Order quantity"/>
          <input type="text" inputmode="decimal" name="dl_rate" value="{P.esc(rate_v)}"
                 aria-label="Rate"/>
        </div>"""

    rate_note = ("Rates open at the schedule's supply base rate and are yours to "
                 "edit." if boq else
                 "The bill of quantities behind this draft is no longer in the "
                 "system, so there is no base rate to open with — every rate has "
                 "to be typed.")
    lines_section = f"""
      <div class="form-section">
        <div class="section-title">Lines carried from the draft</div>
        <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">
          Every line on the draft comes across with its BOQ line id, so this order
          stays traceable to the schedule it was measured from. {rate_note}
          The draft itself is <b>kept</b> — it is the record of what was sent out
          to be priced.
        </p>
        <div class="dl-head">
          <span>Item</span><span>Description</span><span>Unit</span>
          <span style="text-align:right;">Qty</span>
          <span style="text-align:right;">Rate (&#8377;)</span>
        </div>
        {lines_html or '<p style="font-size:.85rem;color:var(--muted);">This draft PO carries no lines.</p>'}
      </div>"""

    # ── The amber band, on a second conversion ────────────────────────────
    banner_html = ""
    already = [pid_ for pid_ in (draft.get("converted_po_ids") or [])
               if pid_ in STORE["purchases"]]
    if already:
        chips = "".join(
            f'<a class="po-chip" href="{url_for("purchase.view_purchase", id=pid_)}">'
            f'{P.esc(STORE["purchases"][pid_].get("ref"))}</a>'
            for pid_ in already)
        banner_html = (
            f'<div class="up-warn">'
            f'<b>Draft {P.esc(draft.get("ref"))} has already been converted.</b> '
            f'{len(already)} purchase order{"" if len(already) == 1 else "s"} '
            f'already exist{"s" if len(already) == 1 else ""} against it, so '
            f'converting again will order this material a second time.'
            f'<br/>That is not blocked, because splitting one request for '
            f'quotation across two orders is an ordinary thing — but check the '
            f'quantities below before you raise it.'
            f'<div class="uw-chips">{chips}</div></div>')

    typed_note = ""
    if not draft.get("vendor_id") and draft.get("vendor_name"):
        typed_note = (f' The draft went to <b>{P.esc(draft.get("vendor_name"))}</b>, '
                      f'who is not in the address book — a real order has to name a '
                      f'vendor from it, so add them first or pick whoever is '
                      f'actually supplying.')

    back_html = (f'<a href="{url_for("po_draft.view_po", id=draft_id)}" '
                 f'class="btn btn-ghost">&#8592; {P.esc(draft.get("ref"))}</a>')
    return _upstream_form(
        title="Purchase Order from Draft",
        action=url_for("purchase.from_draft", draft_id=draft_id),
        back_html=back_html,
        intro_html=(f'Converted from draft <b>{P.esc(draft.get("ref"))}</b>'
                    f'{" &middot; " + P.esc(boq.get("ref")) if boq.get("ref") else ""}'
                    f'{" &middot; project <b>" + P.esc(project_name) + "</b>" if project_name else ""}.'
                    f'{typed_note}'),
        banner_html=banner_html,
        lines_section=lines_section,
        data=data,
        error=error)


def _draft_rate_of(row: dict, base_of: dict, blank_when_unknown: bool = False):
    """
    A converted line's opening rate — **the draft first, the BOQ second**.

    A draft PO carries no rates today (`po_draft.PRINT_RATES` is False and the
    whole document exists so the supplier fills them in), so in practice this
    always falls through to the schedule's supply base rate. It reads the draft
    first anyway, because ABOUT.md §7 gap B7 names capturing the supplier's
    quoted rates against a draft as the natural next piece of work — and when
    that lands, a rate the supplier actually quoted must beat what we costed the
    job at rather than being silently ignored.
    """
    quoted = row.get("rate")
    if quoted is not None:
        parsed = BQ._num(quoted, None)
        if parsed is not None and parsed >= 0:
            return float(parsed)
    base = base_of.get(str(row.get("line_id") or ""))
    if base is None:
        return None if blank_when_unknown else 0.0
    return float(base)


@purchase_bp.route("/<id>/update", methods=["POST"])
def update_purchase(id: str):
    """
    Move a purchase order along its lifecycle.

    Status only. The commercial content of an issued PO is not editable here —
    a vendor has already been told a price and a quantity, and changing them
    behind the document is how a dispute starts. An amendment means a fresh PO.
    """
    po = STORE["purchases"].get(id)
    if not po:
        return redirect(url_for("purchase.list_purchases",
                                msg="Purchase order not found.", type="error"))

    new_status = (request.form.get("status") or "").strip()
    note       = (request.form.get("note") or "").strip()

    if new_status not in PO_STATUSES:
        return redirect(url_for("purchase.view_purchase", id=id,
                                msg="Invalid status.", type="error"))

    old = po.get("status") or DEFAULT_STATUS
    po["status"] = new_status
    if new_status != old:
        _log(po, note or f"Status changed from {old} to {new_status}.",
             status_to=new_status)
    elif note:
        _log(po, note, status_to=new_status)

    return redirect(url_for("purchase.view_purchase", id=id,
                            msg="Purchase order updated.", type="success"))


# =============================================================================
# A1 — THE RATE ON AN ORDER THAT ALREADY EXISTS
# =============================================================================
#
# CLIENT_CHANGES-2.md **A1**, built under the 27 August 2026 override block in
# `CLIENT_CHANGES.md` §0. The rate was already editable **at creation** — the
# box is on `/purchase/create`, on `/purchase/from-boq` and on
# `/purchase/from-draft`, and `RATE_PREFILL_FIELD` only ever suggested a
# figure. What was missing, and what this is, is editing it **afterwards**.
#
# ⚠ **The DRAFT-ONLY narrowing was LIFTED on 28 August 2026**, under the
#   override block of that date in `CLIENT_CHANGES.md` §0. From 27 August this
#   route refused every status but `Draft`, and the commercial question that
#   narrowing left open — *"whether A1-as-sold covers editing the rate on an
#   issued PO"* — was put and answered.
#
#   **The answer, and the reasoning, because it overturns a decision this file
#   used to argue for:** the reason anybody wants an editable base rate is that
#   a wrong rate has **already gone out**. A restriction to Drafts leaves
#   exactly that case unsolved, which removes the feature's purpose — a Draft
#   rate was never locked in the first place, it is simply a form you have not
#   submitted. The objection the narrowing protected — `update_purchase()`'s
#   *"a vendor has already been told a price and a quantity, and changing them
#   behind the document is how a dispute starts"* — is answered by **recording**
#   the change rather than forbidding it. The dispute starts when the change is
#   invisible, not when it is made.
#
#   **So nothing is overwritten silently.** Every reprice that moves a figure
#   writes a `reprice_log` entry — who, when, and old rate → new rate on each
#   line that actually moved — and `/purchase/view` renders it under the order.
#   See `_record_reprice()` below.
#
# ⚠ **One status is still refused: `Cancelled`.** A withdrawn order is not a
#   live purchase order, and repricing one would restate a document we have
#   said is void. That is the same rule `ra.cancelled_reason()` states for a
#   cancelled bill, for the same reason, and it is the only status this route
#   turns away.
#
# **Rates and discounts, and nothing else.** Not the quantity, not the vendor,
# not the lines. "Base rate editable" is a field unlock, and a form that also
# re-derived the line list would have to answer what happens to the `line_id`
# on a BOQ-derived order — which is the key the whole `/purchase/from-boq`
# arrangement turns on (see `_po_lines_from_picked`). Lines stay exactly as
# they were ordered; only what we agreed to pay for them moves.


def can_edit_rates(po: dict) -> tuple:
    """
    `(allowed, reason)` for editing the commercial content of an order.

    Returns the refusal in words rather than a bare False, because it is shown
    to the operator. Same contract as `ra.can_edit()`.

    **One refusal, and it is not about the vendor having been told.** A live
    order in any status may be repriced, because the case the feature exists for
    is precisely a rate that has already gone out (see the section note above).
    A **Cancelled** order is refused: it is not a live order, it is a document
    withdrawn on the record, and repricing it would restate something we have
    told somebody is void.
    """
    status = (po or {}).get("status") or DEFAULT_STATUS
    if status == "Cancelled":
        return False, (f"{po.get('ref') or 'This order'} was cancelled, so it "
                       f"cannot be repriced. The withdrawal is a fact the "
                       f"vendor has been told; raise a fresh purchase order "
                       f"instead of restating a void one.")
    return True, ""


def _repricer() -> str:
    """
    Who is repricing, for the record. Falls back to a name, never to silence.

    `auth.py` is a bottom-of-graph module and imports nothing that prints, so
    this arrow is one-way and safe — `dashboard.py` already pulls it in, which
    makes it transitively present here either way. Imported inside the function
    rather than at module level for the same reason `dashboard.index()` imports
    the seeders that way: a module-level arrow here would be a new edge on the
    graph in ABOUT.md §2 for one string.
    """
    import auth
    user = auth.current_user() or {}
    return str(user.get("display_name") or user.get("username") or "unknown")


def _record_reprice(po: dict, before: list, note: str) -> list:
    """
    Append one `reprice_log` entry naming every line whose money moved.

    `before` is `[(name, part_no, rate, discount_pct), ...]` captured **before**
    `_reprice()` wrote anything, in `_priced_rows()` order — the same order the
    form was generated from, so the two zip without a key.

    **Only lines that actually moved are recorded**, and an entry is written
    only when at least one did. A submit that changes nothing is not a reprice
    and a log full of "no change" rows is a log nobody reads. Returns the list
    of moved rows so the caller can say how many there were.

    Rounded to 2dp before comparison: `128000.0` and `128000.004` are the same
    rate and a float that came back off a form should not be able to invent a
    history entry.
    """
    moved = []
    for (name, part_no, old_rate, old_disc), (_i, row) in zip(before, _priced_rows(po)):
        new_rate = round(float(row.get("price") or 0.0), 2)
        new_disc = round(float(row.get("discount_pct") or 0.0), 4)
        if (round(old_rate, 2), round(old_disc, 4)) == (new_rate, new_disc):
            continue
        moved.append({
            "name": name, "part_no": part_no,
            "rate_from": round(old_rate, 2), "rate_to": new_rate,
            "disc_from": round(old_disc, 4), "disc_to": new_disc,
        })
    if not moved:
        return []
    po.setdefault("reprice_log", []).append({
        "at":     _now(),
        "by":     _repricer(),
        "status": po.get("status") or DEFAULT_STATUS,
        "note":   note,
        "lines":  moved,
    })
    return moved


def _reprice_html(po: dict) -> str:
    """
    The reprice history, newest first, or "" when there is none.

    Returns the **empty string** on an order that has never been repriced, so
    an order that predates 28 August 2026 renders exactly the bytes it always
    did — which is what keeps `/purchase/view`'s golden still.

    Rendered as one row per changed line under a header naming who and when,
    because "who changed it" and "what it changed from" are the two questions
    anybody looking at a repriced order is asking and splitting them across two
    panels answers neither.
    """
    log = po.get("reprice_log") or []
    if not log:
        return ""
    out = ""
    for e in reversed(log):
        lines = ""
        for ln in e.get("lines") or []:
            disc_bit = ""
            if float(ln.get("disc_from") or 0) or float(ln.get("disc_to") or 0):
                disc_bit = (f'<span class="rp-disc">disc '
                            f'{float(ln.get("disc_from") or 0):g}%'
                            f' &#8594; {float(ln.get("disc_to") or 0):g}%</span>')
            lines += (f'<div class="rp-line">'
                      f'<span class="rp-item">{P.esc(ln.get("name"))}</span>'
                      f'<span class="rp-move">{_inr(ln.get("rate_from") or 0)}'
                      f' &#8594; {_inr(ln.get("rate_to") or 0)}</span>'
                      f'{disc_bit}</div>')
        note = (f' &middot; {P.esc(e.get("note"))}') if e.get("note") else ""
        out += (f'<div class="rp-entry">'
                f'<div class="rp-when">{P.esc(e.get("at"))} &middot; '
                f'{P.esc(e.get("by"))} &middot; order was '
                f'{P.esc(e.get("status"))}{note}</div>{lines}</div>')
    return out


def _priced_rows(po: dict) -> list:
    """
    `(index, row)` for every line that carries money.

    Specification headers carried down from a BOQ clause are skipped: they have
    no quantity, no rate and no amount, and a rate box against one would write a
    figure into a row that contributes nothing to either total.
    """
    return [(i, r) for i, r in enumerate(po.get("line_items") or [])
            if not r.get("is_header")]


def _reprice(po: dict, form) -> str:
    """
    Apply the posted rates and discounts to `po` in place. Returns "" or an error.

    **Positional**, against `_priced_rows()` in order, and the count must match
    exactly. The form is generated from this same list and cannot add or remove
    a line, so a short or long post is a tampered one or a stale tab — and
    silently zipping it against whatever arrived would reprice the wrong line.
    Nothing is written until every row has been read and validated.
    """
    rows  = _priced_rows(po)
    rates = form.getlist("line_rate")
    discs = form.getlist("line_discount")

    if len(rates) != len(rows):
        return ("That order has changed since this form was opened. "
                "Reopen it and try again.")

    # A3's charge lines are re-read whole rather than diffed: the repeater posts
    # every slot every time, so what arrives IS the new list. Validated before
    # any row is written, for the same reason the rates are.
    charges, charge_err = _parse_charges(form)
    if charge_err:
        return charge_err

    # The extra free-text lines the same way, and for a second reason: unlike
    # the item rows they are **not** positional. This repeater can gain and lose
    # rows on the edit form, so there is no stable list to diff against and what
    # arrives IS the new list. That is also why a description and a quantity are
    # editable here while a `line_items` row's are not — an item row is a
    # snapshot of something upstream, and an extra line has no upstream at all.
    extra_lines, extra_err = _parse_extra_lines(form)
    if extra_err:
        return extra_err

    staged = []
    for n, (_idx, row) in enumerate(rows):
        name = str(row.get("name") or "this line")
        rate = P.parse_money(rates[n])
        if rate < 0:
            return f"Rate for '{name}' cannot be negative."
        disc, err = _parse_discount(discs[n] if n < len(discs) else "", name)
        if err:
            return err
        staged.append((row, rate, disc))

    for row, rate, disc in staged:
        row["price"] = rate
        row["discount_pct"] = disc
        row["total"] = _line_total(rate, float(row.get("qty") or 0.0), disc)

    # The same three figures the create form writes, from the same helper, using
    # the rates already stored on the order. The tax TYPE is not editable here:
    # whether a vendor charges CGST+SGST or IGST is a fact about where they are,
    # not a price we negotiated, and it was settled when the order was raised.
    po["charges"] = charges
    po["extra_lines"] = extra_lines

    tax_info = po.get("tax_info") or {}
    (subtotal, taxable_value, new_tax,
     grand, total_qty) = _totals_of(
        po.get("line_items") or [],
        po.get("tax_type", "exempt"),
        float(tax_info.get("cgst_rate") or 0.0),
        float(tax_info.get("igst_rate") or 0.0),
        charges, extra_lines)
    po["subtotal"]      = subtotal
    po["taxable_value"] = taxable_value
    po["tax_info"]      = new_tax
    po["grand_total"]   = grand
    po["total_qty"]     = total_qty
    return ""


@purchase_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_purchase_rates(id: str):
    """
    Reprice a live purchase order — CLIENT_CHANGES-2.md A1.

    Gated by `can_edit_rates()` on both verbs. Checking only on POST would leave
    a form that renders happily and refuses on submit; checking only on GET
    would leave the POST open to anyone who kept the URL.

    **Any status but `Cancelled`**, from 28 August 2026 — see the section note
    above for why the Draft-only narrowing was lifted rather than kept. Every
    reprice that moves a figure is recorded by `_record_reprice()` before the
    redirect, and the record is what makes the unlock safe rather than the
    restriction that used to stand in its place.
    """
    po = STORE["purchases"].get(id)
    if not po:
        return redirect(url_for("purchase.list_purchases",
                                msg="Purchase order not found.", type="error"))

    allowed, why = can_edit_rates(po)
    if not allowed:
        return redirect(url_for("purchase.view_purchase", id=id,
                                msg=why, type="error"))

    error = ""
    if request.method == "POST":
        before = float(po.get("grand_total") or 0.0)
        # Captured BEFORE `_reprice()` writes, because it mutates the rows in
        # place and there is no second copy to diff against afterwards.
        was = [(str(r.get("name") or ""), str(r.get("part_no") or ""),
                float(r.get("price") or 0.0), float(r.get("discount_pct") or 0.0))
               for _i, r in _priced_rows(po)]
        # The extra lines are compared whole rather than per-line, because they
        # are not positional: a row can be added or removed here, so "which one
        # moved" is not a question with an answer. What matters for the message
        # is only whether the list is the one that went in.
        extra_was = extra_lines_of(po)
        error = _reprice(po, request.form)
        if not error:
            after = float(po.get("grand_total") or 0.0)
            note  = (request.form.get("note") or "").strip()
            moved = _record_reprice(po, was, note)
            extra_moved = extra_lines_of(po) != extra_was
            # The order's own trail gets one line; the per-line detail lives in
            # `reprice_log` and prints under the document. Two records of one
            # event, and neither restates the other.
            if moved:
                n = len(moved)
                _log(po, note or (f"Repriced {n} line{'' if n == 1 else 's'}: "
                                  f"order value &#8377;{before:,.0f} "
                                  f"&#8594; &#8377;{after:,.0f}."))
                msg = f"Rates updated on {n} line{'' if n == 1 else 's'}."
                if extra_moved:
                    msg += " Extra parts updated."
            elif extra_moved:
                # `reprice_log` records rate movements on ITEM lines and is
                # rendered as such, so an extra-line edit does not fake an entry
                # in it. It still goes on the order's own status trail, because
                # "nothing changed" would be a lie about a save that happened.
                _log(po, note or (f"Extra parts updated: order value "
                                  f"&#8377;{before:,.0f} "
                                  f"&#8594; &#8377;{after:,.0f}."))
                msg = "Extra parts updated."
            else:
                msg = "Nothing changed, so nothing was recorded."
            return redirect(url_for("purchase.view_purchase", id=id,
                                    msg=msg, type="success"))

    # ── The rows ──────────────────────────────────────────────────────────
    #
    # Six cells, which is exactly what `.line-row` already lays out for the
    # create form: item, qty, rate, discount, amount, spacer. Reusing that grid
    # rather than declaring a new one is not tidiness — `PURCHASE_STYLES` is
    # loaded by `/purchase/view`, whose bytes are pinned, so a rule added for
    # this page would move a printed document that did not change.
    posted_rates = request.form.getlist("line_rate")    if request.method == "POST" else []
    posted_discs = request.form.getlist("line_discount") if request.method == "POST" else []

    # The same widget the create form draws, so the two cannot describe one
    # field two ways. A rejected POST comes back with what was typed.
    if request.method == "POST":
        charge_section = _charge_section_html(
            charges_of(po), request.form.getlist("charge_label"),
            request.form.getlist("charge_amount"), request.form)
        extra_section = _extra_section_html(extra_lines_of(po),
                                            posted=request.form)
    else:
        charge_section = _charge_section_html(charges_of(po))
        extra_section = _extra_section_html(extra_lines_of(po))

    rows_html = ""
    for n, (_idx, row) in enumerate(_priced_rows(po)):
        rate = posted_rates[n] if n < len(posted_rates) else f"{float(row.get('price') or 0.0):.2f}"
        disc = posted_discs[n] if n < len(posted_discs) else (
            f"{float(row.get('discount_pct') or 0.0):g}" if row.get("discount_pct") else "")
        rows_html += f"""
        <div class="line-row">
          <span>{P.esc(row.get('name'))}
            <span class="bn-sub">{P.esc(row.get('part_no'))}</span></span>
          <span>{_fmt_qty(float(row.get('qty') or 0.0))} {P.esc(row.get('unit'))}</span>
          <input type="number" name="line_rate" value="{P.esc(rate)}"
                 min="0" step="0.01" placeholder="Rate"/>
          <input type="number" name="line_discount" value="{P.esc(disc)}"
                 min="0" max="100" step="any" placeholder="0"/>
          <span class="ln-amt">{_inr(row.get('total') or 0)}</span>
          <span></span>
        </div>"""

    # A Draft has not gone anywhere; an Issued order has. The same form serves
    # both from 28 August 2026, and it says which one this is rather than
    # asserting the Draft case at an operator who is looking at an Issued order.
    status_now = po.get("status") or DEFAULT_STATUS
    if status_now == "Draft":
        sent_note = (f"This order is a <b>Draft</b> &mdash; it has not been "
                     f"sent to {P.esc(_vendor_of(po))} yet, so what we agree "
                     f"to pay is still ours to change.")
    else:
        sent_note = (f"This order is <b>{P.esc(status_now)}</b> and "
                     f"{P.esc(_vendor_of(po))} has been sent it. Repricing it "
                     f"is allowed and is how a rate that went out wrong gets "
                     f"corrected &mdash; but the vendor is holding the figures "
                     f"you are about to change, so tell them.")

    # The same seeded prefill table the create form hands its typeahead, keyed
    # by the same `po_parts._norm()` normalisation the server matches on.
    seed_json = P.json_for_script({
        PP._norm(name): {"u": row["unit"], "r": float(row["assumed_rate"])}
        for name, row in PP.PARTS.items()
    })

    tax_info = po.get("tax_info") or {}
    tax_note = "no tax on this order"
    if po.get("tax_type") == "cgst_sgst":
        tax_note = (f"CGST {float(tax_info.get('cgst_rate') or 0):g}% + "
                    f"SGST {float(tax_info.get('sgst_rate') or 0):g}%")
    elif po.get("tax_type") == "igst":
        tax_note = f"IGST {float(tax_info.get('igst_rate') or 0):g}%"

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Reprice " + str(po.get('ref')))}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{PURCHASE_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Reprice <span>{P.esc(po.get('ref'))}</span></h1>
        <a href="{url_for("purchase.view_purchase", id=id)}" class="btn btn-ghost">&#8592; Back to the order</a>
      </div>

      {_alert(error, "error")}

      <div class="buy-note">
        {sent_note}
        <div class="bn-sub">Rates and discounts on the <b>items</b> &mdash;
          their quantities, the lines themselves and the vendor are not editable
          here, and the tax stays as raised ({P.esc(tax_note)}).
          <b>Every change is recorded</b> &mdash; who, when, and the old rate
          against the new one on each item line that moves &mdash; and it prints
          under the order.
          <br/><b>Extra parts below are fully editable</b>, descriptions and
          quantities included: an item row is a snapshot of something upstream,
          and an extra part has no upstream to disagree with. Changing one goes
          on the order's history rather than into the rate-change table, which
          lists movements on item lines.</div>
      </div>

      <template id="xline-tpl">{_extra_row_html()}</template>

      <script>
        /* The charge widget is shared with `/purchase/create`, whose live total
           strip calls recalc() on every keystroke. This page has no such strip
           — the Order Value it shows is the stored one, "as it stands" — so the
           hook is defined and does nothing rather than throwing a ReferenceError
           into the console on every character typed. The extra-line widget is
           shared the same way and calls it from the same places. */
        function recalc() {{}}

        /* The extra-line repeater is shared with `/purchase/create` too, so the
           two behaviours it needs come with it: add a row, and prefill from the
           seeded list. Both are the create form's own, and the seed table below
           is the same one, through json_for_script() (ABOUT.md §7.9e).
           ⚠ Every rate in it is an ASSUMED PLACEHOLDER — see po_parts.py. */
        var XSEED = {seed_json};

        function addExtra() {{
          var tpl = document.getElementById('xline-tpl');
          document.getElementById('xlines').appendChild(tpl.content.cloneNode(true));
        }}

        function xlNorm(s) {{
          return String(s || '').toLowerCase().split(/\\s+/).filter(Boolean).join(' ');
        }}

        function xlFill(input) {{
          var hit = XSEED[xlNorm(input.value)];
          if (!hit) {{ return; }}
          var row = input.closest('.xl-row');
          var unit = row.querySelector('input[name="extra_unit"]');
          var rate = row.querySelector('input[name="extra_rate"]');
          if (unit && !unit.value) {{ unit.value = hit.u; }}
          if (rate && !rate.value) {{ rate.value = hit.r.toFixed(2); }}
        }}
      </script>

      <form method="POST" action="{url_for("purchase.edit_purchase_rates", id=id)}">
        <div class="form-section">
          <div class="section-title">What we pay</div>
          <div class="line-head">
            <span>Item</span><span>Qty</span><span>Rate (&#8377;)</span>
            <span>Disc %</span>
            <span style="text-align:right;">Amount</span><span></span>
          </div>
          {rows_html}
          <div class="po-total-strip">
            <span>Order Value as it stands
              <b>&#8377; {float(po.get('grand_total') or 0.0):,.0f}</b></span>
          </div>
        </div>

        {extra_section}

        {charge_section}

        <div class="form-section">
          <div class="section-title">Why</div>
          <div class="form-group">
            <label for="note">Note <span style="font-weight:500;text-transform:none;">(optional)</span></label>
            <input type="text" id="note" name="note"
                   placeholder="e.g. revised after Sanghvi's second quote"/>
            <span class="field-hint">Goes on the order's history. Left blank, the
              history records the old and new order value.</span>
          </div>
        </div>

        <div style="display:flex;gap:.7rem;flex-wrap:wrap;margin-top:1.2rem;">
          <button type="submit" class="btn">Save rates</button>
          <a href="{url_for("purchase.view_purchase", id=id)}" class="btn btn-ghost">Cancel</a>
        </div>
      </form>

      <footer><p>{B.COMPANY_NAME} &middot; {B.APP_SUBTITLE} &middot; purchase order</p></footer>
    </main></body></html>"""
    return _page(template)


@purchase_bp.route("/view/<id>")
def view_purchase(id: str):
    """
    The printed purchase order.

    Same A4 sheet as the sell-side documents (`VIEW_DOC_STYLES`) so everything
    that leaves this office looks like it came from the same place — but read
    the module docstring first: the **"To" block is the vendor**, and the
    delivery block is where they send material **to us**.
    """
    po = STORE["purchases"].get(id)
    if not po:
        return redirect(url_for("purchase.list_purchases",
                                msg="Purchase order not found.", type="error"))

    # ── Line rows ─────────────────────────────────────────────────────────
    sno, total_qty, table_rows = 0, 0.0, ""
    for row in po.get("line_items", []):
        # A specification header, carried down from a BOQ line's parent clause
        # so the supplier can read what they are being asked to supply
        # (DOMAIN.md §2.2). It carries no quantity, no rate and no amount, takes
        # no serial number, and contributes nothing to either total.
        #
        # Orders entered from scratch have no such row — `_parse_lines()` cannot
        # produce one — so this branch is never taken on a PO raised at
        # `/purchase/create`, and that document is byte-for-byte what it was.
        if row.get("is_header"):
            table_rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>
          <td colspan="7" class="c-desc">{P.esc(row.get('name'))}</td>
        </tr>"""
            continue
        sno += 1
        total_qty += float(row.get("qty") or 0)
        # A line written before A2 has no `discount_pct` at all, and one saved
        # with the box left blank has 0.0. Both print an em dash rather than
        # "0 %", because a discount of nothing is not a discount and a column of
        # zeroes reads like a negotiation that failed.
        disc_pct = float(row.get("discount_pct") or 0.0)
        disc_cell = f"{disc_pct:g}%" if disc_pct else "&#8212;"
        table_rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{P.esc(row.get('part_no'))}</td>
          <td class="c-desc">{P.esc(row.get('name'))}</td>
          <td class="c-hsn">{B.field(row.get('hsn'), "HSN")}</td>
          <td class="c-qty">{_fmt_qty(float(row.get('qty') or 0))}</td>
          <td class="c-unit">{P.esc(row.get('unit'))}</td>
          <td class="c-price">{_inr(row.get('price') or 0)}</td>
          <td class="c-disc">{disc_cell}</td>
          <td class="c-total">{_inr(row.get('total') or 0)}</td>
        </tr>"""

    # ── Extra free-text lines (29 Aug 2026) ───────────────────────────────
    #
    # Rendered as ordinary `row-item` rows in the SAME table, continuing the
    # same serial numbering and the same quantity total, because that is what
    # they are: goods on this order. They are not a second table, not a block
    # under the totals, and emphatically not charge rows — a charge is what the
    # vendor bills us beyond the goods, and these ARE goods.
    #
    # An order with no extra lines draws nothing here and prints byte-for-byte
    # what it always printed, which is what keeps the pinned golden still.
    #
    # ⚠ Two cells differ from an item row and both are honest blanks rather than
    #   invented content: there is **no part number** (nothing upstream minted
    #   one) and **no HSN** (these come from no catalogue). The HSN cell goes
    #   through `B.field()` exactly as an item row's does, so a missing HSN is
    #   flagged in the house style rather than left looking deliberate.
    for row in extra_lines_of(po):
        sno += 1
        qty = float(row.get("qty") or 0.0)
        total_qty += qty
        disc_pct = float(row.get("discount_pct") or 0.0)
        disc_cell = f"{disc_pct:g}%" if disc_pct else "&#8212;"
        rate = float(row.get("rate") or 0.0)
        if rate:
            # ⚠ **SCREEN ONLY.** `.xl-assumed` is `display:none` at print — see
            #   PURCHASE_STYLES. The vendor receives the order; the vendor does
            #   not receive our note that we invented the price.
            chip = ('<span class="xl-assumed">assumed</span>'
                    if row.get("rate_is_assumed") else "")
            rate_cell = f"{_inr(rate)}{chip}"
        else:
            # A part typed with no rate: kept deliberately, and shown as
            # incomplete in the same amber the blank-HSN guard uses. This one
            # DOES print — a vendor being asked to price a line has to be able
            # to see which line, and that is the client's actual use for it.
            #
            # ⚠ It cannot tell a line nobody has priced from a line genuinely
            #   supplied free of charge, because both store rate 0. A
            #   free-of-cost line is rare enough on a purchase order that
            #   flagging it is the better error; if one ever needs to be
            #   expressed, it needs a field, not a zero.
            rate_cell = B.field("", "rate")
        table_rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sno}</td>
          <td class="c-partno"></td>
          <td class="c-desc">{P.esc(row.get('description'))}</td>
          <td class="c-hsn">{B.field("", "HSN")}</td>
          <td class="c-qty">{_fmt_qty(qty)}</td>
          <td class="c-unit">{P.esc(row.get('unit'))}</td>
          <td class="c-price">{rate_cell}</td>
          <td class="c-disc">{disc_cell}</td>
          <td class="c-total">{_inr(row.get('total') or 0)}</td>
        </tr>"""

    subtotal = float(po.get("subtotal") or 0.0)
    tax_info = po.get("tax_info") or {"total": 0.0}
    tax_type = po.get("tax_type", "exempt")
    grand    = float(po.get("grand_total") or 0.0)
    has_tax  = tax_type != "exempt" and float(tax_info.get("total") or 0) > 0

    # ── A3's charge lines ─────────────────────────────────────────────────
    #
    # `taxable_value` falls back to `subtotal` for an order raised before
    # 28 August 2026, which is exactly right: with no charges the two are the
    # same figure, and the Taxable Value row below prints what it always did.
    charges = charges_of(po)
    ch_taxable, ch_exempt = charge_totals(charges)
    taxable_value = float(po.get("taxable_value") or subtotal)

    # The rows come from `docsheet`; what goes in them stays here. The tax on
    # this document is **input** tax we pay, the opposite side of the ledger
    # from a tax invoice, and nothing about that arithmetic is shared with the
    # sell chain — only the furniture it prints inside.
    # ⚠ The summary rows carry one more blank cell than the sell chain's,
    # because the buy sheet has one more column. `DS.SUM_BLANKS` /
    # `DS.TOTAL_BLANKS` stay the default everywhere else, so the tax invoice and
    # the proforma are untouched by this — see docsheet.py's note.
    # ⚠ **The order of these rows IS the arithmetic**, so read it as one thing:
    #
    #     Sub Total          the lines            ← only printed when charges
    #                                               exist; otherwise Taxable
    #                                               Value is the lines and one
    #                                               row said so, as before
    #     <taxable charges>  each on its own row  ← INSIDE the base
    #     Taxable Value      lines + those        ← what tax is computed on
    #     CGST / SGST / IGST                      ← follows them up
    #     <exempt charges>   each on its own row  ← AFTER tax, outside the base
    #     Order Value        the lot
    #
    # An order with no charges renders byte-for-byte what it rendered before
    # A3 — no Sub Total row, no charge rows — which is what keeps the printed
    # document still for every order already in the database.
    if charges and has_tax:
        table_rows += DS.sum_row("Sub Total", _inr(subtotal),
                                 blanks=_SUM_BLANKS)
    for c in charges:
        if not c.get("taxable"):
            continue
        # `P.esc` at the interpolation site — `DS.sum_row()` interpolates its
        # label raw and the label here is free text somebody typed (ABOUT.md §9).
        table_rows += DS.sum_row(P.esc(c.get("label")),
                                 _inr(c.get("amount") or 0),
                                 indent=12, blanks=_SUM_BLANKS)

    if has_tax:
        table_rows += DS.sum_row("Taxable Value", _inr(taxable_value),
                                 blanks=_SUM_BLANKS)
        rate_keys = {"CGST": "cgst_rate", "SGST": "sgst_rate",
                     "IGST": "igst_rate", "VAT": "vat_rate"}
        skip = {"total", *rate_keys.values()}
        for tname, tamt in tax_info.items():
            if tname in skip:
                continue
            r = tax_info.get(rate_keys.get(tname, ""), 0)
            lbl = f" @ {r:g}%" if r else ""
            table_rows += DS.sum_row(f"{tname}{lbl}", _inr(tamt), indent=12,
                                     blanks=_SUM_BLANKS)
    else:
        # An exempt order has no Taxable Value row to hang the charges under, so
        # a taxable charge on one still needs its own row above — printed by the
        # loop above — and the charges simply add into the Order Value. Nothing
        # further to draw here.
        pass

    # Outside the base, so after the tax and never before it. Labelled so the
    # vendor can see it was excluded rather than left out.
    for c in charges:
        if c.get("taxable"):
            continue
        table_rows += DS.sum_row(f"{P.esc(c.get('label'))} (no tax)",
                                 _inr(c.get("amount") or 0),
                                 indent=12, blanks=_SUM_BLANKS)

    table_rows += DS.total_row("Order Value", _fmt_qty(total_qty), _inr(grand),
                               blanks=_TOTAL_BLANKS)

    # ── Header meta ───────────────────────────────────────────────────────
    meta_col_1 = (
        _meta("Purchase Order No.",  P.esc(po.get("ref"))) +
        _meta("Your Offer Ref",      P.esc(po.get("vendor_ref"))) +
        _meta("Your GSTIN",          P.esc(po.get("vendor_gstin"))) +
        _meta("Mode/Term of Payment", P.esc(po.get("payment_terms"))) +
        _meta("Terms of Delivery",   P.esc(po.get("delivery_terms")))
    )
    meta_col_2 = (
        _meta("Date",             P.esc(po.get("date"))) +
        _meta("Required By",      P.esc(po.get("delivery_date"))) +
        _meta("Dispatch Through", P.esc(po.get("dispatch_through"))) +
        _meta("Incoterms",        P.esc(po.get("incoterms"))) +
        _meta("Our GSTIN",        P.esc(B.COMPANY_GSTIN))
    )

    # ── The vendor block. This is the "To" on a PO — NOT a customer. ───────
    # `DS.name_block` builds the same shape the tax invoice puts a *customer*
    # into. The shape is shared; the role is not, which is why these two locals
    # are named for the role rather than for the position on the page.
    vendor_block = DS.name_block(po.get("to"))
    delivery_block = DS.secondary_block("Deliver To", po.get("delivery_to"))

    job_line = ""
    if po.get("quotation_ref"):
        job_line = (f'<span class="dp-src"> &middot; for our job '
                    f'{P.esc(po["quotation_ref"])}</span>')

    status_strip = f"""
    <div class="po-status-strip">
      <span><span class="ps-l">Status:</span>
            <span class="ps-v">{P.esc(po.get("status") or DEFAULT_STATUS)}</span></span>
      <span><span class="ps-l">Required By:</span>
            <span class="ps-v">{P.esc(po.get("delivery_date")) or "&#8212;"}</span></span>
      <span><span class="ps-l">This order is placed by us as buyer.</span></span>
    </div>"""

    instr_html = """
  <div class="po-instr">
    <div class="po-instr-title">Instructions to Supplier</div>
    <div class="po-instr-body">
      <ol class="tnc-ol">
        <li><span class="tnc-num">1.</span><span>Quote our purchase order number
          on your invoice, delivery challan, packing list and all correspondence.
          An invoice without it may be returned unpaid.</span></li>
        <li><span class="tnc-num">2.</span><span>Your tax invoice must comply with
          Rule 46 of the CGST Rules — GSTIN, HSN/SAC per line, place of supply and
          the tax split shown separately. We cannot claim input tax credit
          against a deficient invoice, and any credit lost will be recovered
          from your payment.</span></li>
        <li><span class="tnc-num">3.</span><span>Deliver to the address shown
          above within the required-by date. Material delivered elsewhere, or
          without prior intimation, is at your risk.</span></li>
        <li><span class="tnc-num">4.</span><span>Goods are accepted subject to
          inspection. Anything short-supplied, damaged or not to specification
          will be rejected and is to be collected at your cost.</span></li>
        <li><span class="tnc-num">5.</span><span>Prices are firm for the duration
          of this order. No escalation is admissible unless agreed in writing
          before dispatch.</span></li>
        <li><span class="tnc-num">6.</span><span>Any change to price, quantity or
          delivery date must be agreed in writing. We will not accept an
          amendment made on your invoice alone.</span></li>
        <li><span class="tnc-num">7.</span><span>This order may be cancelled
          without liability if material is not delivered by the required-by
          date.</span></li>
      </ol>
    </div>
  </div>"""

    note_html = ""
    if po.get("notes"):
        note_html = (f'<div class="po-note"><span class="pn-lbl">Note:</span> '
                     f'{P.esc(po["notes"])}</div>')

    comp_br   = P.esc(po.get("company_branch")) or B.COMPANY_NAME
    signatory = P.esc(po.get("auth_signatory")) or P.esc(B.COMPANY_SIGNATORY)

    # ── Screen-only panel: lifecycle + audit trail ────────────────────────
    status_sel = "".join(
        f'<option{" selected" if s == (po.get("status") or DEFAULT_STATUS) else ""}>{s}</option>'
        for s in PO_STATUSES
    )
    # ── Where this order came from, when it came from anywhere ────────────
    #
    # ⚠ **Every one of these is conditional and the whole strip collapses to the
    #   empty string when the order has no upstream link.** That is what makes
    #   an order entered from scratch render byte-for-byte what it always did,
    #   which `tests/test_print_golden.py` measures rather than trusts. Note
    #   there is no literal whitespace around `{upstream_html}` at its insertion
    #   point below, for exactly that reason.
    #
    # The refs are read off the RECORD; the id is only used to build the link
    # and to check the target still exists. A BOQ or a project that has been
    # removed leaves the order still naming what it was raised against, in
    # plain text — `proforma.quotation_ref`'s contract.
    up_chips = ""
    if po.get("boq_ref") or po.get("boq_id"):
        label = P.esc(po.get("boq_ref")) or "the schedule"
        if po.get("boq_id") in (STORE.get("boqs") or {}):
            up_chips += (f'<a class="po-chip" href="'
                         f'{url_for("boq.view_boq", id=po["boq_id"])}">'
                         f'{label} &middot; schedule</a>')
        else:
            up_chips += f'<span class="po-chip">{label} &middot; schedule</span>'
    if po.get("draft_ref") or po.get("draft_id"):
        label = P.esc(po.get("draft_ref")) or "draft PO"
        if po.get("draft_id") in (STORE.get("purchase_orders") or {}):
            up_chips += (f'<a class="po-chip" href="'
                         f'{url_for("po_draft.view_po", id=po["draft_id"])}">'
                         f'{label} &middot; draft</a>')
        else:
            up_chips += f'<span class="po-chip">{label} &middot; draft</span>'
    if po.get("project_id") or po.get("project_name"):
        label = P.esc(po.get("project_name")) or "project"
        if po.get("project_id") in (STORE.get("projects") or {}):
            up_chips += (f'<a class="po-chip" href="'
                         f'{url_for("projectview.view_project", id=po["project_id"])}">'
                         f'{label} &middot; project</a>')
        else:
            up_chips += f'<span class="po-chip">{label} &middot; project</span>'
    upstream_html = (f'<div class="po-strip">{up_chips}</div>' if up_chips else "")

    job_link = ""
    if po.get("quotation_id") in STORE["quotations"]:
        jc = job_cost(po["quotation_id"])
        # Extra-line spend gets named here rather than disappearing into
        # `committed`: it is cost with no schedule line behind it, and a job
        # summary that hides that is the whole trap `job_cost()`'s docstring
        # describes. Rendered ONLY when there is some — an order with no extra
        # lines draws the identical string it always drew, which is what keeps
        # `/purchase/view`'s pinned bytes still. Same contract as
        # `reprice_btn` and `upstream_html` above.
        extra_bit = ""
        if jc["extra_committed"]:
            n = jc["extra_count"]
            extra_bit = (f' &middot; of which extra parts '
                         f'&#8377;&nbsp;{jc["extra_committed"]:,.0f} '
                         f'({n} line{"" if n == 1 else "s"} on no schedule)')
        job_link = (f'<a class="po-chip" href="'
                    f'{url_for("quotation.view_quotation", id=po["quotation_id"])}">'
                    f'{P.esc(po.get("quotation_ref"))} &middot; job costing</a>'
                    f'<span class="jc-sub" style="margin-left:.5rem;">'
                    f'quoted &#8377;&nbsp;{jc["quoted"]:,.0f} &middot; '
                    f'committed &#8377;&nbsp;{jc["committed"]:,.0f}'
                    f'{extra_bit}</span>')

    # Offered only where `can_edit_rates()` would allow it, which from
    # 28 August 2026 means **every order except a Cancelled one**. A button that
    # redirects to a refusal is a worse answer than no button.
    #
    # ⚠ This is one of the two reasons `/purchase/view`'s golden moved in this
    #   pass: the pinned order is **Issued**, and until the narrowing was lifted
    #   an Issued order carried no Reprice button. It carries one now, and that
    #   is the feature rather than a regression.
    reprice_btn = ""
    if can_edit_rates(po)[0]:
        # The newline and indent live INSIDE the string, so a Cancelled order
        # renders the action bar byte-for-byte as it always did.
        reprice_btn = (f'\n    <a href="{url_for("purchase.edit_purchase_rates", id=id)}" '
                       f'class="btn btn-ghost">Reprice</a>')

    # Empty string on an order that has never been repriced, so the panel of an
    # order raised before 28 August 2026 renders byte-for-byte as it did.
    rp = _reprice_html(po)
    reprice_hist = (f'\n  <div class="po-reprice">'
                    f'<div class="po-reprice-t">Rate changes</div>{rp}</div>') if rp else ""

    panel = f"""
<div class="po-panel">
  <h2>Order status</h2>
  <form method="POST" action="{url_for("purchase.update_purchase", id=id)}">
    <div class="po-panel-row">
      <div class="form-group" style="max-width:230px;margin:0;">
        <label for="status">Status</label>
        <select id="status" name="status">{status_sel}</select>
      </div>
      <div class="form-group" style="flex:1;min-width:220px;margin:0;">
        <label for="note">Note <span style="font-weight:500;text-transform:none;">(optional)</span></label>
        <input type="text" id="note" name="note"
               placeholder="e.g. 6 of 10 received, balance next week"/>
      </div>
      <button type="submit" class="btn">Update</button>
    </div>
  </form>
  {f'<div class="po-strip">{job_link}</div>' if job_link else ''}{upstream_html}
  <div class="po-hist">{_history_html(po)}</div>{reprice_hist}
</div>"""

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(po.get('ref')) + " Purchase Order")}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{PURCHASE_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Purchase Order <span style="color:var(--brand);">{P.esc(po.get('ref'))}</span>
    {_status_badge(po.get('status'))}
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for("purchase.list_purchases")}" class="btn btn-ghost">All Purchase Orders</a>{reprice_btn}
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>

{_alert(request.args.get("msg"), request.args.get("type", "success"))}
{panel}

<div class="doc-outer">
<div class="quotation-doc">

{DS.sheet_open(show_web=False)}

  <div class="doc-box">
    <div class="doc-title">PURCHASE ORDER</div>
    <div class="doc-sub-po">Order placed on supplier{job_line}</div>

{DS.party_block("To (Supplier)", vendor_block, delivery_block, meta_col_1, meta_col_2)}

    {status_strip}

{DS.items_table(DS.BUY_COLUMNS, table_rows)}

{DS.amount_words("Order Value (in words)", grand)}
  </div>

  {instr_html}
  {note_html}

{DS.sig_block(comp_br, signatory, computer_generated=True)}

{DS.sheet_close()}

</div>
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · purchase order</p>
</footer>
</main>
</body></html>"""
    return _page(template)
