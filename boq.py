"""
boq.py — Bill of Quantities  (SELL SIDE)
=========================================
The head of a second document chain, parallel to quotation → proforma → tax
invoice and deliberately not part of it:

    BOQ ──► RA bill 1 ──► RA bill 2 ──► …          (ra.py, Phase 3)

A **quotation** is an offer to sell goods, priced per line, invoiced once (or a
few times) against the whole. A **BOQ** is the priced schedule of a *project*:
one to two hundred lines, split into systems (sections A/B/C…), each line
carrying a quantity broken down by the area or floor it is installed on, and
each line priced twice — once to *supply* the material and once to *install*
it. It is billed progressively as the work happens, through Running Account
bills, which is why it needs its own chain rather than a render mode of the
quotation.

Three things about the shape that are easy to get wrong
-------------------------------------------------------
1. **Areas belong to the SECTION, not to the BOQ.** The client's own workbook
   declares `External` + `L0` for section A, `T1` for section B, and none at
   all for section C. A BOQ-wide area list cannot represent that, so the
   printed document renders **one table per section**, each with its own
   colgroup and column heads.
2. **`parent_item_no` is a SPECIFICATION hierarchy, not a BOM depth.** A header
   line carries ~1500 characters of specification and no quantity; the lines
   under it carry the quantities and the rates. This is not
   `line_item["depth"]` from the quotation — that means "component of an
   assembly", and the two will collide the first time a BOQ line is itself an
   assembly. They are kept as separate fields on purpose.
3. **`item_no` is a STRING, everywhere, always.** The source workbook stores
   item 4.1 as `4.0999999999999996` and 4.4 as `4.4000000000000004`. Read one
   as a float and it prints as either the wrong number or seventeen digits of
   noise on a document a customer signs.

What is reused, and from where
-------------------------------
The printed sheet is the quotation's sheet — `VIEW_DOC_STYLES` gives the A4
frame, the repeating letterhead band and every print rule, and `_inr` /
`_fmt_qty` / `_amount_in_words` / `_meta` are the document's own formatters.
`BOQ_STYLES` layers after it and introduces no new font, type size or border
weight, exactly as `PROFORMA_STYLES` and `PURCHASE_STYLES` do. It changes
exactly one thing about the page: **it prints landscape.** See the note above
`BOQ_STYLES` for why that is forced rather than chosen.

Import direction (§3.4 of the handover — one way, never reversed):

    boq.py ──► quotation.py   document toolkit only
    boq.py ──► address.py     customer picker
    boq.py ──► pipeline.py    esc / parse_money / fy_of / fy_ref
    boq.py ──► dashboard.py   BASE_STYLES / _nav
    boq.py ──► spec.py        the specification library (the picker)
    boq.py ──► demo_data.py   seed data only

`boq.py` must **not** import `ra.py` — the view page links out with `url_for`
and reads `STORE["ra_bills"]` directly, which is the same one-way trick
`quotation.py` uses for proformas. It must not import `proforma.py` or
`purchase.py` either: a BOQ has no proforma, and a project bills through RA.
"""

import json
import re
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import branding as B
import demo_data as DD
import pipeline as P
from address import INDIAN_STATES, picker_options, picker_payload
from dashboard import BASE_STYLES, _nav
from spec import ensure_demo_specs, spec_by_code, variant_of, _valid_tax_code
from store import STORE

# The document's own formatters and stylesheet — see the module docstring.
from quotation import (
    QUOTATION_STYLES,
    VIEW_DOC_STYLES,
    _amount_in_words,
    _fmt_qty,
    _inr,
    _meta,
    _DEL_TERMS,
    _PAY_TERMS,
)

boq_bp = Blueprint("boq", __name__, url_prefix="/boq")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

_REF_SERIES = "BOQ"

# No 16-character cap. That is Rule 46(b)'s limit on a *tax invoice* number;
# a BOQ is a priced schedule, not a statutory record. It still wants an
# FY-scoped, non-repeating series, because it is the key every RA bill raised
# against the project quotes back — same reasoning as the purchase order.
_REF_CAP = 64

# GST on a works contract is 18% for both the goods and the service leg unless
# the project qualifies for a concessional rate. Captured per line (supply and
# installation are different supplies and can be taxed differently), defaulted
# here so 120 lines do not have to be typed one at a time. The BOQ itself does
# NOT compute tax — see PRINT_TAX below.
DEFAULT_GST_RATE = 18.0

# The BOQ prints BASIC values only. The client's own summary sheet says "TAXES
# WILL BE EXTRA" on its face, and the liability falls due as the work is
# billed, not when the schedule is agreed. Printing a tax total here would
# state a liability that does not exist yet.
#
# ⚠ Updated per DOMAIN.md §4: An RA bill is headed TAX INVOICE and carries a
#   per-line tax block for progressive claims. The BOQ itself remains basic
#   values only (TAXES WILL BE EXTRA).
PRINT_TAX = False

# The client's remark column (column N in their workbook) holds internal
# pricing notes — "2000/nos extra for Tamper switch", "Mohali 300 mm dia and
# Banglore 450 mm dia". They are captured, and they are shown on screen and in
# the import report, but they do NOT print: the same judgement that keeps the
# deal-desk fields off the quotation. Flip this if the client wants them on the
# customer's copy.
PRINT_REMARKS = False

# A rate column that is zero on every line of the whole BOQ is a column of
# nothing, and on a landscape sheet already fighting for width the description
# needs the millimetres more than an empty column does. Same judgement as the
# PI's `.pay-box`, which breaks the figure down only when there is arithmetic
# to show.
HIDE_EMPTY_ESCALATION = True

# The most lines one BOQ may carry.
#
# This is a *persistence* limit wearing a validation hat. The whole record is
# stored as one JSON document in a single MySQL column (ABOUT.md §4), so a BOQ
# large enough to be refused by the server is a record that can never be
# written — and since a failed sync now retries on every request rather than
# giving up (§4), such a record would be re-offered and re-refused forever. The
# cap is what stops it existing in the first place.
#
# 600 against a real schedule of 97: the client's largest workbook is under 150
# lines, and a project big enough to need four times that is two projects. It
# is a deliberate limit, not a guess at a technical ceiling — the technical
# ceiling is higher and is not the reason for the number.
#
# ⚠ A line-count cap does not by itself guarantee the POST stays under Flask's
#   MAX_FORM_MEMORY_SIZE (500,000 bytes). The demo's 97 lines serialise at ~701
#   bytes each, so 600 typical lines is ~420 KB and fits; 600 lines all
#   carrying full 1500-character specification paragraphs would not. That case
#   is what the 413 handler in app.py catches, and it is the one path where the
#   backstop is doing real work rather than only catching a bypass.
MAX_LINES = 600

# The most bytes of `boq_json` one BOQ may post, measured on the DECODED string
# as `request.form` hands it back.
#
# This is the cap that actually binds, and it exists because MAX_LINES alone
# cannot keep the request under Flask's MAX_FORM_MEMORY_SIZE (500,000 bytes).
# Two facts make that so:
#
#   1. The form limit applies to the **URL-encoded body on the wire**, not to
#      the JSON. `application/x-www-form-urlencoded` percent-escapes every
#      quote, brace, comma, colon, space and newline, and JSON is made of those.
#   2. So the wire is bigger than the payload, by a factor that depends on the
#      content. Measured:
#
#        real demo BOQ (97 lines)  701 B/line JSON  ->  955 B/line encoded (1.36x)
#        terse synthetic lines     455 B/line JSON  ->  685 B/line encoded (1.51x)
#
# At 955 encoded bytes a line, a real-shaped BOQ reaches 500,000 bytes at ~523
# lines — BELOW MAX_LINES. A 524-line schedule would therefore 413 before any
# validation ran, losing the editor, which is exactly what the cap exists to
# prevent.
#
# 300,000 decoded x the worst observed 1.51 expansion = 453,000 bytes on the
# wire, leaving ~47 KB for the twenty other form fields (`notes` is a textarea
# and is the only one that can be large). The check therefore always fires
# before Werkzeug does, for any content shape this app has seen.
#
# The two caps bind on different schedules and both are needed: MAX_LINES
# catches many terse lines, this catches fewer verbose ones. For the client's
# real data shape this one binds first, at ~428 lines.
#
# ⚠ Not a security boundary. A hostile payload of nothing but escaped quotes
#   expands 3x and would still 413 — MAX_FORM_MEMORY_SIZE stays at 500,000 and
#   remains the real limit, with the 413 handler behind it. This is a
#   usability boundary: it keeps an HONEST BOQ from ever hitting that wall.
MAX_JSON_BYTES = 300_000

# Section codes offered by the create form. Free text is still accepted — a
# project can run to more sections than this — but these are what the client's
# workbooks actually use.
_SECTION_CODES = ["A", "B", "C", "D", "E", "F", "G", "H"]

_UNITS = ["Nos", "Nos.", "Mtrs", "Mtrs.", "Kgs.", "Set", "Lot", "Lump Sum",
          "Sq.Mtrs", "Ltrs", "Job"]

# What the base-rate column is called on the printed sheet. The client's own
# workbooks price against a rate schedule agreed on another project ("Mohali
# Rates") and then apply an escalation, so the label is per-BOQ data rather
# than a constant.
DEFAULT_RATE_BASIS = "Base Rate"


# =============================================================================
# HELPERS — identity and numbers
# =============================================================================

def _next_ref(datestr: str) -> str:
    """
    Next BOQ number — 'SF/BOQ/26-27/0001'.

    FY-scoped and max+1 within that year, the same shape and the same shared
    helpers as the tax invoice and the purchase order. Scanning only same-FY
    records is what lets the series restart each April without colliding, and
    max+1 (never `len()+1`) is what stops a deleted record re-issuing a number
    that has already reached a customer.
    """
    fy = P.fy_of(datestr)
    highest = 0
    for b in STORE["boqs"].values():
        if b.get("fy") != fy:
            continue
        tail = str(b.get("ref") or "").rpartition("/")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return P.fy_ref(B.COMPANY_SHORT, _REF_SERIES, fy, highest + 1, cap=_REF_CAP)


def _item_no(raw) -> str:
    """
    An item number, as a STRING — 4.1 stays "4.1" and never becomes 4.0999….

    The source workbooks store these as floats, and the two the client's Sify
    sheet holds are `4.0999999999999996` and `4.4000000000000004`. A float that
    reaches the document prints seventeen digits of binary noise next to a
    quantity somebody is going to be paid against. The form posts strings, so
    this is a guard rather than a conversion — but it is the guard that stops a
    hand-written dict or a future importer putting a float in the record.
    """
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, float):
        # %.10g is short of a double's 17 significant digits, so the dust is
        # dropped and 4.0999999999999996 formats back to "4.1".
        return f"{raw:.10g}"
    if isinstance(raw, int):
        return str(raw)
    return str(raw or "").strip()


# =============================================================================
# THE LINE IDENTIFIER
# =============================================================================
#
# `line_id` is the key an RA claim is matched on. It is OPAQUE and
# SERVER-MINTED, and both halves of that are load-bearing:
#
#   * **Opaque.** It is not derived from `item_no`, `section`, `description` or
#     any other displayed field. Those are values the client's staff edit
#     freely, and a key made of editable fields re-attributes every claim
#     against a line the moment somebody fixes a typo in it.
#   * **Not positional.** An index would re-attribute every claim below any
#     inserted line — the same defect wearing a different hat.
#
# It exists because `item_no` cannot do this job and never could. In the
# client's own 97-line Sify schedule, 87 priced lines carry only 77 distinct
# item numbers: item numbers restart per section (item `4` is in both A and B),
# and section A carries item `17` **twice**, on a flexible sprinkler drop at
# Rs 1,800 and a 150 mm butterfly valve at Rs 14,572.50. Keying the over-claim
# guard on `item_no` collapsed those ten lines together, which both waved
# Rs 1,99,122.50 of over-claim through and blocked Rs 84,071.00 of legitimate
# claim. See `tests/test_boq_line_ids.py`.
#
# Uniqueness is required WITHIN one BOQ record only. Claims are always scoped to
# a parent BOQ, so a collision across records is harmless and there is
# deliberately no global registry to keep.
#
# Nothing outside the code ever needs to read it: it is not shown on the form,
# not printed on the document, and not part of any reference the client quotes
# back. `item_no` remains the display label everywhere it already appeared.
_LINE_ID_LEN = 12
_LINE_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _new_line_id() -> str:
    """A fresh opaque line key — 12 hex characters from uuid4."""
    return uuid.uuid4().hex[:_LINE_ID_LEN]


def _line_id(raw) -> str:
    """
    A posted line id, or "" if it is absent or malformed.

    "" means *mint one*. A malformed id is never echoed back and never
    trusted — it is treated exactly as a missing one, because a browser that
    sent something this shape does not match is a browser whose id we have no
    reason to believe.
    """
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return ""
    s = str(raw).strip().lower()
    return s if _LINE_ID_RE.match(s) else ""


def _num(raw, default: float = 0.0) -> float:
    """A number off the form. Blank or unparseable falls back, never raises."""
    if raw is None:
        return default
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    s = str(raw).strip().replace(",", "")
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _opt_num(raw):
    """
    A number that is allowed to be absent.

    Returns `None` for a blank cell **and for a literal "-"**. In the client's
    workbooks a "-" in a base-rate cell does not mean zero and is not an error:
    it means the rate was negotiated directly rather than escalated off the
    base schedule. Collapsing that to 0.0 would state that the material is
    free.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    s = str(raw).strip().replace(",", "")
    if not s or s in ("-", "--", "—", "–"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _derived_rate(base, pct: float):
    """
    base × (1 + pct/100) — the rate the escalation implies.

    Only ever a *suggestion*. The stored `supply_rate` is whatever was entered,
    because the client's own sheets carry a dozen lines where the two disagree
    for a documented reason (a tamper switch at ₹2000/nos, a larger diameter at
    the Bangalore site). Recomputing the rate from the escalation would quietly
    rewrite a price that was agreed — the importer's job is to *report* that
    disagreement, never to resolve it.
    """
    if base is None:
        return None
    return float(base) * (1.0 + float(pct or 0.0) / 100.0)


# =============================================================================
# HELPERS — the record
# =============================================================================

def _json_for_script(obj) -> str:
    """
    JSON safe to embed in a <script> block.

    `json.dumps` does not escape `<`, and a spec clause containing the seven
    characters `</script>` therefore CLOSES the script element early — every
    byte after it is parsed as HTML, which is script injection through a field
    a user is invited to paste a specification into. This page embeds 56
    clauses, the whole address book and the entire editor model, so it happens
    three times over.

    `<` and friends are ordinary JSON string escapes: the browser decodes
    them back to the original characters, so nothing about the data changes —
    only its spelling on the wire. `ensure_ascii` (on by default) has already
    escaped U+2028/U+2029, the other pair that terminates a JS line.

    ⚠ The same pattern is used by `quotation._product_catalog_json()` and by
      every `json.dumps(picker_payload())` in the app. They are untouched here
      because the quotation chain is live — recorded in ABOUT.md §7.
    """
    # NOTE the doubled backslashes. The replacement must be the SIX characters
    # backslash-u-0-0-3-c, not the character U+003C. A single backslash here
    # compiles to "<" and the replace becomes a silent no-op — which is exactly
    # what it was on the first attempt at this fix.
    return (json.dumps(obj)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def _sel_keep(name: str, options, default: str, current=None) -> str:
    """
    A dropdown that never silently rewrites a value it does not recognise.

    `quotation._sel_opts()` marks an option selected only on an exact match, so
    a stored value absent from the list renders as "nothing selected" and the
    browser then posts the FIRST option. On this form that is not theoretical:
    the Sify schedule's payment terms are "Material Payment 50% Advance & 50%
    After Delivery Or as per OEM Conditions." — the client's own wording, and
    not one of `quotation._PAY_TERMS`. Loading the demo through `_sel_opts`
    would quietly change it to "100% Against Proforma Invoice".

    So an unrecognised value is prepended and kept selected, exactly as
    `proforma._sel_keep()` does for the same reason one document further along.

    ⚠ This duplicates that function. `boq.py` may not import `proforma.py`
    (§3.4), and the shared home is `quotation.py`, which both may import — move
    it there the next time that file is open, and delete both copies.
    """
    cur = current if current is not None else default
    opts = list(options)
    if cur and cur not in opts:
        opts = [cur] + opts
    inner = "".join(
        f'<option{" selected" if o == cur else ""}>{P.esc(o)}</option>'
        for o in opts
    )
    return f'<select id="{name}" name="{name}">{inner}</select>'


def _sections_of(boq: dict) -> list:
    return boq.get("sections") or []


def _areas_of(boq: dict, code: str) -> list:
    for s in _sections_of(boq):
        if s.get("code") == code:
            return list(s.get("areas") or [])
    return []


def _lines_of(boq: dict, code: str) -> list:
    return [li for li in boq.get("line_items", []) if li.get("section") == code]


def section_totals(boq: dict, code: str) -> tuple:
    """
    (supply, installation) for one section — COMPUTED, never stored.

    A stored section subtotal is a second copy of a figure that is already
    implied by the lines, and the two disagree the first time a line is edited.
    The record stores only the BOQ-level trio (§4.3), and even those are
    recomputed here for the document so the printed sheet cannot contradict its
    own lines.
    """
    supply = install = 0.0
    for li in _lines_of(boq, code):
        if li.get("is_header"):
            continue
        supply  += float(li.get("supply_amount") or 0.0)
        install += float(li.get("install_amount") or 0.0)
    return supply, install


def boq_totals(boq: dict) -> tuple:
    """(supply, installation, subtotal) across every section."""
    supply = install = 0.0
    for s in _sections_of(boq):
        sup, ins = section_totals(boq, s.get("code"))
        supply  += sup
        install += ins
    return supply, install, supply + install


def _any_escalation(boq: dict, key: str) -> bool:
    """Does any line in this BOQ actually carry an escalation on this track?"""
    return any(float(li.get(key) or 0.0) != 0.0
               for li in boq.get("line_items", []))


# =============================================================================
# SEED
# =============================================================================

def _seed_line(row: dict, sections_by_code: dict) -> dict:
    """
    One `demo_data.BOQ_LINES` entry as a §4.2 line item.

    The seed table names a spec and, for a size family, a variant — so the
    demo BOQ is built along the same path a user takes through the picker
    rather than by a private back door. The description comes from the library
    (`spec_text` for a header or an unsized line, the variant label for a
    child) and is **copied**, which is what a real line does too.

    The rates come off the seed table, not off the spec, and that is
    deliberate: twelve lines in this schedule differ from
    base x (1 + escalation) for a documented commercial reason. Re-deriving
    them from the library defaults would quietly erase those decisions and the
    subtotals would stop matching the client's sheet.
    """
    spec = spec_by_code(row["spec"])
    code = row["section"]

    if row.get("header"):
        return {
            # Deterministic, from the generator — see demo_data's line_id note.
            # A regenerated seed must produce the same ids or a re-seed would
            # orphan every claim raised against the demo BOQ.
            "line_id":        _line_id(row.get("line_id")) or _new_line_id(),
            "item_no":        _item_no(row["item_no"]),
            "parent_item_no": "",
            "section":        code,
            "is_header":      True,
            "description":    spec["spec_text"] if spec else "",
            "remark":         "",
            "unit":           "",
            "area_qty":       {},
            "total_qty":      0.0,
            "supply_base_rate": None, "supply_escalation_pct": 0.0,
            "supply_rate": 0.0, "supply_amount": 0.0,
            "supply_hsn": "", "supply_gst_rate": 0.0,
            "install_base_rate": None, "install_escalation_pct": 0.0,
            "install_rate": 0.0, "install_amount": 0.0,
            "install_sac": "", "install_gst_rate": 0.0,
        }

    variant = variant_of(spec, row["variant"]) if spec else None
    # A child of a size family is described by its variant label; a standalone
    # line by the clause itself. That is exactly what the picker does.
    description = (row["variant"] or "").strip()
    if not description:
        description = spec["spec_text"] if spec else ""

    qty = float(row.get("total_qty") or 0.0)
    s_rate = float(row.get("s_rate") or 0.0)
    i_rate = float(row.get("i_rate") or 0.0)

    return {
        "line_id":        _line_id(row.get("line_id")) or _new_line_id(),
        "item_no":        _item_no(row["item_no"]),
        "parent_item_no": _item_no(row.get("parent") or ""),
        "section":        code,
        "is_header":      False,
        "description":    description,
        "remark":         row.get("remark") or "",
        "unit":           (variant or {}).get("unit", ""),
        # Only areas the section actually declares, and only where the sheet
        # carried a figure — a blank cell means the item is not on that floor.
        "area_qty":       {k: float(v) for k, v in (row.get("areas") or {}).items()
                           if k in sections_by_code.get(code, [])},
        "total_qty":      qty,

        "supply_base_rate":      row.get("s_base"),
        "supply_escalation_pct": float(row.get("s_pct") or 0.0),
        "supply_rate":           s_rate,
        "supply_amount":         s_rate * qty,
        "supply_hsn":            (spec or {}).get("supply_hsn", ""),
        "supply_gst_rate":       float((spec or {}).get("supply_gst_rate") or DEFAULT_GST_RATE),

        "install_base_rate":      row.get("i_base"),
        "install_escalation_pct": float(row.get("i_pct") or 0.0),
        "install_rate":           i_rate,
        "install_amount":         i_rate * qty,
        "install_sac":            (spec or {}).get("install_sac", ""),
        "install_gst_rate":       float((spec or {}).get("install_gst_rate") or DEFAULT_GST_RATE),
    }


def ensure_demo_boq() -> None:
    """
    Seed one complete BOQ on first call; a no-op afterwards.

    This is the Sify Bangalore schedule — three sections, 97 lines, the area
    breakdown each section actually declares — generated from the client's own
    workbook. It exists so the system can be shown working without anybody
    typing 120 lines first, and so every downstream phase has something real to
    run against.

    Guarded by `STORE["_boq_seeded"]`, which is deliberately **not persisted**:
    dropping the database and restarting refills it. The record carries a fixed
    UUID, so re-running never produces a second copy and a BOQ the user has
    since edited is left alone.

    It depends on the library, so `ensure_demo_specs()` runs first — the lines
    are built from specs by code, the same path the picker takes.
    """
    if STORE.get("_boq_seeded"):
        return
    ensure_demo_specs()

    bid = DD.BOQ_META["id"]
    if bid in STORE["boqs"]:
        STORE["_boq_seeded"] = True
        return

    sections = [dict(s, areas=list(s["areas"])) for s in DD.BOQ_SECTIONS]
    areas_by_code = {s["code"]: s["areas"] for s in sections}

    boq = {
        **DD.BOQ_META,
        "to": "\n".join(x for x in [
            DD.BOQ_META.get("account_name"),
            ", ".join(y for y in [DD.BOQ_META.get("bill_city"),
                                  DD.BOQ_META.get("bill_state")] if y),
        ] if x),
        "ship_same": False,
        "ship_acct_name": DD.BOQ_META.get("project_name", ""),
        "ship_addr": DD.BOQ_META.get("site_location", ""),
        "ship_city": DD.BOQ_META.get("bill_city", ""),
        "ship_state": DD.BOQ_META.get("bill_state", ""),
        "ship_pin": "",
        "sections":   sections,
        "line_items": [_seed_line(r, areas_by_code) for r in DD.BOQ_LINES],
        "supply_subtotal": 0.0, "install_subtotal": 0.0, "subtotal": 0.0,
        "company_branch": "", "auth_signatory": "",
    }

    # Computed from the lines by the same helper the document uses, so the
    # stored trio cannot disagree with what prints.
    sup, ins, tot = boq_totals(boq)
    boq["supply_subtotal"], boq["install_subtotal"], boq["subtotal"] = sup, ins, tot

    STORE["boqs"][bid] = boq
    STORE["_boq_seeded"] = True


def backfill_line_ids(store: dict = None) -> dict:
    """
    Mint `line_id` on every BOQ line that predates the field. One-time, explicit.

    Returns `{"boqs", "lines", "claims_without_ids"}` — records touched, lines
    filled, and RA claim rows that carry no `line_id` and therefore match
    nothing.

    **Explicit and idempotent, not lazy-on-read.** A lazy mint would hand out a
    different id every time a record was loaded without being saved, which is
    the one behaviour that would be worse than no id at all. Run this once;
    running it again fills nothing and reports zero.

    It only ever fills a **blank**. An id already on a line is never replaced —
    that id may already have claims matched against it, and reissuing it is
    exactly the orphaning this whole change exists to prevent. Uniqueness is
    enforced within each record, so a record that somehow carries the same id
    twice gets the duplicate re-minted.

    ⚠ **It cannot repair RA claims that predate the field**, and deliberately
    does not try. Matching an existing claim back to a line would have to go
    through `item_no` — and `item_no` is ambiguous on exactly the lines that
    matter (the client's section A carries item `17` twice), so a guess would
    silently attach a claim to the wrong item at the wrong rate. Those rows are
    counted and reported instead. At the time this migration was written there
    were **zero** RA bills in existence — there is no route that creates one
    yet — so the count is expected to be 0 and a non-zero answer means someone
    needs to look before trusting the guard.
    """
    store = store if store is not None else STORE
    touched_boqs = 0
    filled = 0

    for boq in (store.get("boqs") or {}).values():
        seen = set()
        touched_here = False
        for li in boq.get("line_items") or []:
            if not isinstance(li, dict):
                continue
            lid = _line_id(li.get("line_id"))
            if not lid or lid in seen:
                lid = _new_line_id()
                while lid in seen:
                    lid = _new_line_id()
                li["line_id"] = lid
                filled += 1
                touched_here = True
            seen.add(lid)
        if touched_here:
            touched_boqs += 1

    orphan_claims = 0
    for bill in (store.get("ra_bills") or {}).values():
        for c in bill.get("claims") or []:
            if not _line_id(c.get("line_id")):
                orphan_claims += 1

    return {"boqs": touched_boqs, "lines": filled,
            "claims_without_ids": orphan_claims}


# =============================================================================
# REVISIONS — carrying ids forward, and what a revision may not remove
# =============================================================================

def revision_blockers(prev_lines: list, new_lines: list,
                      claims_by_line_id: dict) -> list:
    """
    Lines a revision would delete that already carry RA claims. Empty is a pass.

    A revision creates a **new BOQ record** and posts the previous revision's
    lines with their ids, so a surviving line keeps its id by the ordinary
    `_clean_lines()` round trip and a genuinely new line mints one. That is the
    whole point of the identifier: an RA bill raised against revision 1 still
    matches its lines after revision 2, even if every item number moved.

    What needs a guard is **deletion**. Dropping a line that has been claimed
    against leaves a claim with no approved quantity behind it — the balance
    arithmetic has nothing to hold, and a bill already submitted to the main
    contractor becomes unbacked. If the work genuinely is not happening, the
    correction belongs in a claim, not in the schedule the claim was measured
    against. Deleting an **unclaimed** line stays free.

    Pure by design, and that is an import-direction decision rather than a
    stylistic one: `claims_by_line_id` is passed in ({line_id: [ra_no, …]},
    which `ra.claims_by_line_id()` builds) because **boq.py must never import
    ra.py** (ABOUT.md §2b). The revision route, when it is built, reads
    `STORE["ra_bills"]` directly — the same one-way trick `view_boq()` already
    uses for the RA chips.
    """
    surviving = {_line_id(li.get("line_id")) for li in new_lines or []}
    surviving.discard("")

    out = []
    for li in prev_lines or []:
        lid = _line_id(li.get("line_id"))
        if not lid or lid in surviving:
            continue
        ra_nos = claims_by_line_id.get(lid) or []
        if not ra_nos:
            continue                       # unclaimed: deleting it is free
        out.append({"line_id": lid,
                    "item_no": _item_no(li.get("item_no")),
                    "section": str(li.get("section") or ""),
                    "description": str(li.get("description") or ""),
                    "ra_nos": sorted(ra_nos)})
    return out


def revision_blocker_message(v: dict) -> str:
    """One blocked deletion, in words the person revising it can act on."""
    bills = ", ".join(f"RA{n}" for n in v["ra_nos"])
    plural = "bills" if len(v["ra_nos"]) != 1 else "bill"
    return (f"Item {v['item_no']} (section {v['section']}) cannot be removed — "
            f"it has already been claimed on {plural} {bills}. Reduce its "
            f"quantity instead, or correct the position in the next claim.")


# =============================================================================
# THE PRINTED BOQ — stylesheet
# =============================================================================
#
# A plain string, not an f-string, so its CSS braces are written once. Only the
# HTML below needs doubling. `DASH_STYLES` established this and it is worth
# copying for any block this size.
#
# ── WHY THIS SHEET PRINTS LANDSCAPE ──────────────────────────────────────────
# The fixed columns — Sr, Total Qty, Unit, base rate, escalation, supply rate,
# supply amount, install base, install rate, install amount — come to ~167mm
# before a single area column or a single character of description. A4 portrait
# gives 192mm of printable width against the app's 9mm side margins. Two area
# columns take it to 195mm, which is already over, and the description column
# is the one that has to hold ~1500 characters of specification.
#
# The alternative was dropping the area breakdown to fit portrait. That is
# worse: the area columns are the only place `total_qty` is substantiated, and
# `sum(area_qty) == total_qty` is the reconciliation the importer exists to
# run. A sheet that cannot be checked against the workbook it came from is not
# a document, it is a summary. Landscape also scales — the column count is a
# property of the *section*, and a project with five floors would break any
# portrait layout tuned for two.
#
# Everything here is an override layered after VIEW_DOC_STYLES, never an edit
# to it: the quotation, PI, TI and PO sheets are untouched and still portrait.
# =============================================================================

BOQ_STYLES = """
<style>
  /* ── Landscape ─────────────────────────────────────────────────────────
     Later @page rule of equal specificity wins, so this replaces the
     `size:A4 portrait` in VIEW_DOC_STYLES for this page only. */
  @media print {
    @page { size:A4 landscape; margin:9mm 8mm 8mm; }
  }
  .boq-outer { max-width:297mm; }

  /* ── Screen furniture ──────────────────────────────────────────────── */
  .boq-panel {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.3rem 1.5rem;
    box-shadow:var(--shadow-sm); margin-bottom:1.4rem;
  }
  .bp-head {
    display:flex; align-items:flex-start; justify-content:space-between;
    gap:1rem; flex-wrap:wrap; margin-bottom:1rem;
    padding-bottom:.8rem; border-bottom:1px solid var(--border);
  }
  .bp-title { font-size:.73rem; font-weight:700; text-transform:uppercase;
              letter-spacing:.09em; color:var(--brand); }
  .bp-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1rem; }
  .bp-cell { min-width:0; }
  .bp-lbl  { font-size:.7rem; font-weight:700; text-transform:uppercase;
             letter-spacing:.06em; color:var(--muted); }
  .bp-val  { font-size:1.15rem; font-weight:700; margin-top:.2rem; }
  .bp-sub  { font-size:.75rem; color:var(--muted); margin-top:.15rem; }

  /* Running Account bills raised against this BOQ. Mirrors .pi-strip on the
     quotation deal panel — same shape, same purpose, one chain over. */
  .ra-block { margin-top:1.1rem; padding-top:.9rem; border-top:1px dashed var(--border); }
  .ra-lbl   { font-size:.7rem; font-weight:700; text-transform:uppercase;
              letter-spacing:.06em; color:var(--muted); }
  .ra-strip { display:flex; flex-wrap:wrap; gap:.45rem; margin-top:.5rem; }
  .ra-chip  {
    font-size:.75rem; font-weight:600; color:var(--navy); background:#eef2ff;
    border:1px solid #c7d2fe; border-radius:999px; padding:.25rem .7rem;
    text-decoration:none;
  }
  .ra-chip:hover { background:#e0e7ff; }

  /* ── The document ──────────────────────────────────────────────────── */
  .boq-doc .doc-sub-boq {
    text-align:center; font-size:var(--fs-sm); color:var(--doc-soft);
    padding:2px 0 3px; border-bottom:var(--rule-box);
  }

  /* One table per section. Each carries its own column heads because the area
     columns are a property of the section, not of the BOQ — a single table
     whose column count changes halfway down is not a table. */
  .sec-block { margin-top:4mm; }
  .sec-block:first-of-type { margin-top:0; }

  .sec-head {
    border:var(--rule-box); border-bottom:none;
    padding:3px 5px; font-weight:700; font-size:var(--fs-md);
  }
  .sec-code { display:inline-block; min-width:7mm; }

  .boq-table {
    width:100%; border-collapse:collapse; table-layout:fixed;
    font-size:var(--fs-xs);
  }
  /* Every property the document cares about is declared, never inherited:
     BASE_STYLES and QUOTATION_STYLES both ship bare `th`/`td` rules and load
     either side of this sheet. Omitting one is how the heads silently come out
     uppercase and grey. */
  .boq-table th {
    background:#c9c9c9; border:var(--rule); padding:2px 3px;
    font-weight:700; text-align:center;
    font-family:inherit; font-size:var(--fs-xs); color:var(--doc-ink);
    text-transform:none; letter-spacing:normal; white-space:normal;
    vertical-align:middle;
  }
  .boq-table td {
    border:var(--rule); padding:2px 3px; vertical-align:top;
    font-family:inherit; font-size:var(--fs-xs); color:var(--doc-ink);
    text-transform:none; letter-spacing:normal;
  }

  .b-sno   { width:12mm; text-align:center; }
  .b-desc  { text-align:left; overflow-wrap:break-word; }
  .b-area  { width:14mm; text-align:right; font-variant-numeric:tabular-nums; }
  .b-qty   { width:15mm; text-align:right; font-variant-numeric:tabular-nums; }
  .b-unit  { width:13mm; text-align:center; }
  .b-base  { width:16mm; text-align:right; font-variant-numeric:tabular-nums; }
  .b-esc   { width:11mm; text-align:center; }
  .b-rate  { width:18mm; text-align:right; font-variant-numeric:tabular-nums; }
  .b-amt   { width:24mm; text-align:right; font-variant-numeric:tabular-nums; }

  /* Hierarchy by weight and indent, never by fill — it has to survive a
     printer with background graphics switched off. */
  .row-spec .b-desc { font-weight:700; }
  .b-child          { padding-left:8px; }

  .row-secsum td {
    font-weight:700; font-size:var(--fs-sm);
    border-top:var(--rule-box); border-bottom:var(--rule-box);
  }
  .secsum-lbl { text-align:right; }

  .boq-grand { margin-top:4mm; border:var(--rule-box); }
  .boq-grand table { width:100%; border-collapse:collapse; }
  .boq-grand td {
    border:none; padding:3px 5px; font-weight:700; font-size:var(--fs-md);
    font-family:inherit; color:var(--doc-ink); text-transform:none;
  }
  .bg-lbl { text-align:right; }
  .bg-amt { width:24mm; text-align:right; font-variant-numeric:tabular-nums; }
  .bg-tag { width:26mm; text-align:center; font-size:var(--fs-sm); font-weight:400; }

  .boq-words { border-top:var(--rule); padding:3px 5px; font-weight:700;
               font-size:var(--fs-sm); }
  .boq-taxnote { padding:3px 5px; font-size:var(--fs-sm); font-weight:700; }

  @media print {
    /* Repeat the column heads of every section table on page 2+. Without this
       a 120-line BOQ has three pages of unlabelled numbers. */
    .boq-table > thead { display:table-header-group; }
    .boq-table th { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
    .boq-table tr, .sec-head, .boq-grand { break-inside:avoid; page-break-inside:avoid; }
    .sec-head { break-after:avoid; page-break-after:avoid; }
    .boq-outer { max-width:none; }
  }

  /* MUST stay scoped to `screen`. A4 landscape at 96dpi is ~1123px, so an
     unscoped max-width breakpoint would fire on paper and print the phone
     layout — see the same note in VIEW_DOC_STYLES. */
  @media screen and (max-width:760px) {
    .boq-outer { max-width:100%; }
    .boq-table { table-layout:auto; min-width:900px; }
    .sec-wrap  { overflow-x:auto; }
  }

  /* ── The line editor ───────────────────────────────────────────────── */
  .sec-editor { display:flex; flex-direction:column; gap:.6rem; }
  .sec-row {
    display:grid; grid-template-columns:80px 1fr 1.2fr 34px; gap:.6rem;
    align-items:end;
  }
  .line-card {
    border:1px solid var(--border); border-radius:10px;
    padding:.9rem 1rem; margin-bottom:.8rem; background:var(--bg);
  }
  .line-card.is-spec { border-left:3px solid var(--navy); background:#f8fafc; }
  .lc-head {
    display:flex; align-items:center; justify-content:space-between;
    gap:.6rem; margin-bottom:.7rem;
  }
  .lc-no { font-size:.72rem; font-weight:700; text-transform:uppercase;
           letter-spacing:.07em; color:var(--muted); }
  .lc-track {
    font-size:.68rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.06em; color:var(--muted); margin:.6rem 0 .35rem;
  }
  .lc-areas {
    display:flex; flex-wrap:wrap; gap:.6rem; align-items:end;
    padding:.5rem .6rem; border:1px dashed var(--border); border-radius:8px;
    background:var(--surface);
  }
  .lc-area { width:96px; }
  .lc-none { font-size:.78rem; color:var(--muted); font-style:italic; }
  .btn-row {
    font-size:.75rem; font-weight:600; color:var(--brand);
    background:var(--brand-lt); border:1px solid #c7d2fe; border-radius:6px;
    padding:.3rem .75rem; cursor:pointer;
  }
  .btn-row:hover { background:#c7d2fe; }
  /* The demo-load banner. Blue, not amber: nothing is wrong, but the user has
     to know that a form which just filled itself has saved nothing. */
  .demo-banner {
    background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;
    padding:.75rem 1rem; font-size:.82rem; color:#1e3a8a;
    margin-bottom:1.4rem; line-height:1.5;
  }

  /* ── Navigating a long schedule ────────────────────────────────────
     97 lines as stacked panels is unusable. A line shows a one-line
     summary; the panel opens only for the line being worked on. */
  .jump-bar {
    position:sticky; top:60px; z-index:20;
    display:flex; align-items:center; gap:.4rem; flex-wrap:wrap;
    background:var(--surface); border:1px solid var(--border);
    border-radius:10px; padding:.5rem .7rem; margin-bottom:1rem;
    box-shadow:var(--shadow-sm);
  }
  .jb-lbl { font-size:.68rem; font-weight:700; text-transform:uppercase;
            letter-spacing:.06em; color:var(--muted); margin-right:.2rem; }
  .jb-btn {
    font-size:.75rem; font-weight:700; color:var(--navy); background:var(--bg);
    border:1px solid var(--border); border-radius:6px; padding:.25rem .6rem;
    cursor:pointer; min-width:28px;
  }
  .jb-btn:hover { background:var(--brand-lt); border-color:#c7d2fe; }
  .jb-sp { flex:1 1 auto; }

  /* Form-only advisory bands. Amber, not red: amber in this app means
     "incomplete but working" (ABOUT.md §5), which is exactly what both of
     these are. A repeated item number is an ambiguity on the printed sheet,
     not a billing fault — claims key on the line's own id, so two lines
     sharing a number stay separate. A priced line at quantity 0 is a line
     awaiting measurement, which is a legitimate state.

     Neither ever reaches the printed sheet. The print is the client-facing
     document and a band on it would assert a defect in his schedule where
     there is none. */
  .form-hint {
    display:flex; gap:.55rem; align-items:flex-start;
    background:#fffbeb; border:1px solid #fcd34d; border-left:3px solid var(--saffron);
    border-radius:8px; padding:.6rem .8rem; margin-bottom:1rem;
    font-size:.78rem; line-height:1.5; color:#78350f;
  }
  .fh-icon { color:var(--saffron); font-size:.95rem; line-height:1.3; }
  .fh-sec { color:#92400e; font-weight:600; }

  .sec-group { margin-bottom:.9rem; border:1px solid var(--border);
               border-radius:10px; overflow:hidden; }
  .sec-bar {
    display:flex; align-items:center; gap:.6rem; cursor:pointer;
    padding:.6rem .8rem; background:var(--bg); user-select:none;
  }
  .sec-bar:hover { background:#eef2ff; }
  .sec-bar-warn { background:#fef2f2; cursor:default; }
  .sec-bar-warn:hover { background:#fef2f2; }
  .sb-code {
    font-weight:700; font-size:.8rem; min-width:22px; text-align:center;
    background:var(--navy); color:#fff; border-radius:5px; padding:.05rem .35rem;
  }
  .sec-bar-warn .sb-code { background:#991b1b; }
  .sb-title { font-weight:600; font-size:.86rem; flex:1 1 auto; min-width:0;
              overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sb-count { font-size:.74rem; color:var(--muted); white-space:nowrap; }
  .sec-lines { padding:.5rem; background:var(--surface); }

  /* The summary row — the actual deliverable. Scannable at a glance. */
  .ls-row {
    display:flex; align-items:center; gap:.6rem; cursor:pointer;
    padding:.4rem .55rem; border-radius:6px; user-select:none;
    font-size:.82rem; line-height:1.35;
  }
  .ls-row:hover { background:#f1f5f9; }
  .ls-chev { width:12px; flex:0 0 12px; color:var(--muted); font-size:.7rem; }
  .ls-no {
    font-family:'SFMono-Regular',Consolas,monospace; font-weight:700;
    font-size:.76rem; color:var(--brand); flex:0 0 54px;
  }
  .ls-desc { flex:1 1 auto; min-width:0; overflow:hidden;
             text-overflow:ellipsis; white-space:nowrap; }
  .ls-qty  { flex:0 0 82px; text-align:right; color:var(--muted);
             font-variant-numeric:tabular-nums; white-space:nowrap; }
  .ls-rate { flex:0 0 88px; text-align:right;
             font-variant-numeric:tabular-nums; white-space:nowrap; }
  .ls-tag  { flex:0 0 178px; text-align:right; font-size:.72rem;
             color:var(--navy); font-weight:600; }

  .line-card { padding:0; margin-bottom:.15rem; background:transparent;
               border:1px solid transparent; border-radius:8px; }
  .line-card.is-open { border-color:var(--border); background:var(--bg);
                       margin-bottom:.7rem; }
  .line-card.is-spec > .ls-row { font-weight:700; }
  .line-card.is-spec.is-open { border-left:3px solid var(--navy); }
  .line-card.is-child > .ls-row { padding-left:1.6rem; }
  .lc-body { padding:.8rem 1rem 1rem; border-top:1px solid var(--border); }

  /* Bulk insert — a spec expanded into a header row plus one child per size. */
  .bulk-bar {
    display:flex; gap:.7rem; align-items:end; flex-wrap:wrap;
    padding:.9rem 1rem; border:1px dashed var(--border); border-radius:10px;
    background:var(--bg);
  }
  .btn-del {
    font-size:.75rem; font-weight:700; color:#991b1b; background:#fef2f2;
    border:1px solid #fecaca; border-radius:6px; padding:.3rem .6rem;
    cursor:pointer;
  }
  .btn-del:hover { background:#fee2e2; }
  .derived {
    font-size:.68rem; color:var(--muted); margin-top:.15rem; min-height:1em;
  }
  .derived b { color:var(--navy); }
</style>
"""


# =============================================================================
# THE PRINTED BOQ — rendering
# =============================================================================

def _rate_cell(rate) -> str:
    """
    A rate, or a blank cell when the track is not priced on this line.

    Blank, not `0.00`: a line that is installation-only has no supply rate at
    all, and printing 0.00 there says the material is free. The *amount*
    column still prints 0.00, because that is a real figure that sums into the
    subtotal — which is exactly how the client's own workbook renders it.
    """
    return _inr(rate) if rate else ""


def _base_cell(base) -> str:
    """
    A base rate, or "-" when the rate was entered directly.

    "-" is the client's own convention and it carries meaning: this line was
    negotiated rather than escalated off the base schedule. It is not zero and
    it is not missing data, so it prints as itself.
    """
    return "-" if base is None else _inr(base)


def _esc_cell(pct) -> str:
    pct = float(pct or 0.0)
    return f"{pct:g}%" if pct else ""


def _section_table(boq: dict, sec: dict, show_s_esc: bool, show_i_esc: bool,
                   show_rate_breakup: bool = False) -> str:
    """
    One section: its title band, its own column heads, its lines, its subtotal.

    `show_rate_breakup` decides whether HOW a rate was arrived at is shown
    beside the rate itself — the base rate columns and the escalation columns.
    It is **display only**: `supply_rate` / `install_rate` and every amount are
    printed exactly as stored either way, so the two variants of this table can
    never disagree about money.

    It defaults to **False** because the issued document is the common case
    (§5, the BOQ print) — the client does not want the negotiation basis on the
    sheet that leaves the building. `/boq/view` passes True, which is what keeps
    those figures on screen for whoever is pricing the job.

    ⚠ Every colspan below is derived from `n_supply_cols` / `n_install_cols`
      rather than written as a number, because dropping three columns silently
      breaks any span that was counted by hand. `test_boq_print_columns.py`
      asserts every row of every section sums to the header width.
    """
    code   = sec.get("code") or ""
    areas  = list(sec.get("areas") or [])
    lines  = _lines_of(boq, code)
    basis  = boq.get("rate_basis_label") or DEFAULT_RATE_BASIS

    # The base rate columns and the escalation columns stand or fall together —
    # an escalation percentage with nothing to apply it to is not a column, it
    # is a riddle. So the breakup flag gates both, and HIDE_EMPTY_ESCALATION
    # still narrows further within it.
    show_base  = show_rate_breakup
    show_s_esc = show_s_esc and show_rate_breakup
    show_i_esc = show_i_esc and show_rate_breakup

    # [base] [, esc] , rate — the rate column is the only one always present.
    n_supply_cols  = 1 + (1 if show_base else 0) + (1 if show_s_esc else 0)
    n_install_cols = 1 + (1 if show_base else 0) + (1 if show_i_esc else 0)

    # ── Column widths ──────────────────────────────────────────────────
    # An explicit <colgroup>, per section, because the column COUNT is a
    # property of the section.
    #
    # This is not decoration. Under `table-layout:fixed` the browser takes its
    # widths from `<col>` elements if they exist and otherwise from the cells
    # of the FIRST row — and the first row here spans the area columns with a
    # single `colspan` "Area / Floor" head. Without a colgroup, `.b-area`'s
    # 14mm is divided across however many areas the section declares, so a
    # two-area section prints its quantity columns at 7mm each. It renders,
    # it just renders wrong, which is the kind of fault that is only ever
    # noticed on paper.
    cols = ['<col style="width:12mm"/>', "<col/>"]                  # Sr., Description
    cols += ['<col style="width:14mm"/>'] * len(areas)              # one per area
    cols += ['<col style="width:15mm"/>', '<col style="width:13mm"/>']   # Total Qty, Unit
    if show_base:
        cols += ['<col style="width:16mm"/>']                       # supply base
    if show_s_esc:
        cols += ['<col style="width:11mm"/>']
    cols += ['<col style="width:18mm"/>', '<col style="width:24mm"/>']   # supply rate, amount
    if show_base:
        cols += ['<col style="width:16mm"/>']                       # install base
    if show_i_esc:
        cols += ['<col style="width:11mm"/>']
    cols += ['<col style="width:18mm"/>', '<col style="width:24mm"/>']   # install rate, amount
    colgroup = "<colgroup>" + "".join(cols) + "</colgroup>"

    # ── Column heads ───────────────────────────────────────────────────
    area_ths = "".join(f'<th class="b-area">{P.esc(a)}</th>' for a in areas)

    s_esc_th = '<th class="b-esc">Esc. %</th>' if show_s_esc else ""
    i_esc_th = '<th class="b-esc">Esc. %</th>' if show_i_esc else ""

    # A section with no area breakdown gets no area columns at all — nothing to
    # show and nothing to reconcile against.
    area_group_th = (f'<th class="b-area" colspan="{len(areas)}">Area / Floor</th>'
                     if areas else "")

    # Two header SHAPES, and which one is used follows from what is left to
    # group. With the breakup shown, "Supply" and "Installation" each span two
    # or three sub-columns and the second row names them. With it hidden each
    # side is a single U/ Rate column, and a group head spanning one column is
    # furniture that says nothing — so the grouping collapses into the column
    # itself, which is where the track name has to go instead.
    #
    # The second row then survives only to carry the area names, and a section
    # declaring no areas (the client's own section C) has nothing left to put in
    # it. An empty <tr> in a thead is not harmless: `.boq-table th` is filled
    # grey, so it prints as a blank band under the heads on every page.
    grouped   = n_supply_cols > 1 or n_install_cols > 1
    need_row2 = grouped or bool(areas)
    rs        = ' rowspan="2"' if need_row2 else ""

    if grouped:
        supply_th  = f'<th colspan="{n_supply_cols}">Supply</th>'
        install_th = f'<th colspan="{n_install_cols}">Installation</th>'
        rate_ths   = (f'<th class="b-base">{P.esc(basis)}</th>{s_esc_th}'
                      f'<th class="b-rate">U/ Rate</th>'
                      f'<th class="b-base">{P.esc(basis)}</th>{i_esc_th}'
                      f'<th class="b-rate">U/ Rate</th>')
    else:
        supply_th  = f'<th class="b-rate"{rs}>Supply<br/>U/ Rate</th>'
        install_th = f'<th class="b-rate"{rs}>Installation<br/>U/ Rate</th>'
        rate_ths   = ""

    row2_html = f"<tr>{area_ths}{rate_ths}</tr>" if need_row2 else ""

    head_html = f"""
      <thead>
        <tr>
          <th class="b-sno"{rs}>Sr.</th>
          <th class="b-desc"{rs}>Description</th>
          {area_group_th}
          <th class="b-qty"{rs}>Total Qty</th>
          <th class="b-unit"{rs}>Unit</th>
          {supply_th}
          <th class="b-amt"{rs}>Supply Amount</th>
          {install_th}
          <th class="b-amt"{rs}>Installation Amount</th>
        </tr>
        {row2_html}
      </thead>"""

    # ── Lines ──────────────────────────────────────────────────────────
    body = ""
    for li in lines:
        is_header = bool(li.get("is_header"))
        row_cls   = "row-spec" if is_header else "row-line"
        # A specification hierarchy, NOT a BOM depth — see the module docstring.
        child_cls = " b-child" if (li.get("parent_item_no") or "").strip() else ""

        desc = P.esc(li.get("description"))
        if PRINT_REMARKS and li.get("remark"):
            desc += f'<br><i>{P.esc(li.get("remark"))}</i>'

        if is_header:
            # A specification header carries the paragraph and nothing else:
            # no quantity, no rate, no amount. Spanning the numeric columns is
            # what makes that visible rather than leaving a row of blanks that
            # reads as missing data.
            #   description itself + areas + qty + unit
            #   + supply([base][,esc],rate) + supply amount
            #   + install([base][,esc],rate) + install amount
            span = 1 + len(areas) + 2 + n_supply_cols + 1 + n_install_cols + 1
            body += f"""
            <tr class="{row_cls}">
              <td class="b-sno">{P.esc(_item_no(li.get("item_no")))}</td>
              <td class="b-desc{child_cls}" colspan="{span}">{desc}</td>
            </tr>"""
            continue

        area_qty = li.get("area_qty") or {}
        area_tds = ""
        for a in areas:
            v = area_qty.get(a)
            # A blank cell means the item does not appear on that floor. It is
            # not a zero, and printing 0 would put an item everywhere.
            area_tds += f'<td class="b-area">{_fmt_qty(v) if v else ""}</td>'

        s_base_td = (f'<td class="b-base">{_base_cell(li.get("supply_base_rate"))}</td>'
                     if show_base else "")
        i_base_td = (f'<td class="b-base">{_base_cell(li.get("install_base_rate"))}</td>'
                     if show_base else "")
        s_esc_td = (f'<td class="b-esc">{_esc_cell(li.get("supply_escalation_pct"))}</td>'
                    if show_s_esc else "")
        i_esc_td = (f'<td class="b-esc">{_esc_cell(li.get("install_escalation_pct"))}</td>'
                    if show_i_esc else "")

        body += f"""
        <tr class="{row_cls}">
          <td class="b-sno">{P.esc(_item_no(li.get("item_no")))}</td>
          <td class="b-desc{child_cls}">{desc}</td>
          {area_tds}
          <td class="b-qty">{_fmt_qty(float(li.get("total_qty") or 0.0))}</td>
          <td class="b-unit">{P.esc(li.get("unit"))}</td>
          {s_base_td}
          {s_esc_td}
          <td class="b-rate">{_rate_cell(li.get("supply_rate"))}</td>
          <td class="b-amt">{_inr(li.get("supply_amount"))}</td>
          {i_base_td}
          {i_esc_td}
          <td class="b-rate">{_rate_cell(li.get("install_rate"))}</td>
          <td class="b-amt">{_inr(li.get("install_amount"))}</td>
        </tr>"""

    # ── Section subtotal — COMPUTED, never stored ──────────────────────
    sup, ins = section_totals(boq, code)
    # Label spans everything up to the supply amount, exactly as the client's
    # own sheet merges A:I for its "BASIC VALUE SUBTOTAL (A)" row.
    sum_span = 2 + len(areas) + 2 + n_supply_cols
    body += f"""
    <tr class="row-secsum">
      <td class="secsum-lbl" colspan="{sum_span}">BASIC VALUE SUBTOTAL ({P.esc(code)}) &gt;&gt;&gt;&gt;</td>
      <td class="b-amt">{_inr(sup)}</td>
      <td colspan="{n_install_cols}"></td>
      <td class="b-amt">{_inr(ins)}</td>
    </tr>"""

    return f"""
    <div class="sec-block">
      <div class="sec-head">
        <span class="sec-code">{P.esc(code)}</span>{P.esc(sec.get("title"))}
      </div>
      <div class="sec-wrap">
        <table class="boq-table">{colgroup}{head_html}<tbody>{body}</tbody></table>
      </div>
    </div>"""


# =============================================================================
# FORM — parsing and validation
# =============================================================================

def _parse_payload(raw: str) -> tuple:
    """
    Read the editor's hidden JSON into (sections, lines, error).

    The line editor is a browser-side model serialised on submit, the same
    shape of thing as the quotation's `selections_json`. A BOQ line carries
    seventeen fields and a variable number of area quantities, so parallel
    form-field lists (purchase.py's pattern) would not survive the area columns
    changing when the section changes.
    """
    if not (raw or "").strip():
        return [], [], "Add at least one section and one line item."
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return [], [], "The line item data could not be read. Please re-enter the lines."

    sections = data.get("sections") or []
    lines    = data.get("lines") or []
    if not isinstance(sections, list) or not isinstance(lines, list):
        return [], [], "The line item data could not be read. Please re-enter the lines."
    return sections, lines, ""


def _clean_sections(raw_sections: list) -> tuple:
    """(sections, error) — codes present, unique, and areas de-duplicated in order."""
    out, seen = [], set()
    for s in raw_sections:
        if not isinstance(s, dict):
            continue
        code = str(s.get("code") or "").strip()
        if not code:
            return [], "Every section needs a code (A, B, C …)."
        if code in seen:
            return [], f"Section code &quot;{P.esc(code)}&quot; is used twice."
        seen.add(code)

        # Ordered and de-duplicated: the order drives the column order on the
        # printed sheet, and a repeated area name would render two columns that
        # can never be told apart.
        areas, seen_a = [], set()
        for a in (s.get("areas") or []):
            a = str(a or "").strip()
            if a and a not in seen_a:
                seen_a.add(a)
                areas.append(a)

        out.append({"code": code,
                    "title": str(s.get("title") or "").strip(),
                    "areas": areas})

    if not out:
        return [], "Add at least one section."
    return out, ""


def _clean_lines(raw_lines: list, sections: list, payload_bytes: int = 0) -> tuple:
    """
    (line_items, error, error_index) — one §4.2 line item per editor row.

    `error_index` is the 0-based position of the offending row, or -1. The
    editor collapses every line by default, so a rejected POST that only said
    "line 47 needs a description" would hide the very row it is complaining
    about. The index is what lets the re-render force that one open.

    Rates are stored **as entered**, never recomputed from the escalation:
    see `_derived_rate`. Amounts *are* computed, always, so a stored amount can
    never disagree with the rate and quantity printed beside it.
    """
    # The line cap is checked FIRST, before any per-line work. Every other rule
    # here describes one row; this one describes the schedule, and validating
    # 5000 rows to then reject the lot for being 5000 rows is work nobody asked
    # for. It reports the first line past the limit as the offender, so the
    # re-render opens the row where the BOQ stopped being acceptable rather
    # than the last one the user happened to add.
    if len(raw_lines) > MAX_LINES:
        over = len(raw_lines) - MAX_LINES
        return ([],
                f"This BOQ has {len(raw_lines)} lines and the limit is "
                f"{MAX_LINES}. Line {MAX_LINES + 1} is the first one over it — "
                f"remove {over} line{'s' if over != 1 else ''}, or split the "
                f"schedule into a second BOQ.",
                MAX_LINES)

    # …and the size cap, which binds on a schedule of few but very long lines
    # where the line count never does. `err_idx` is -1 deliberately: no single
    # line is at fault, so forcing one open would point the user at a row that
    # is not the problem. See MAX_JSON_BYTES for why the limit is where it is.
    if payload_bytes > MAX_JSON_BYTES:
        return ([],
                f"This schedule is too large to save — {payload_bytes // 1024} KB "
                f"of line data against a limit of {MAX_JSON_BYTES // 1024} KB. "
                f"No single line is at fault; it is the schedule as a whole. "
                f"Shorten the longest descriptions, or split it into a second BOQ.",
                -1)

    by_code = {s["code"]: s for s in sections}
    out = []

    # THE LINE-ID ROUND TRIP — the one thing in this function that, if it
    # breaks, breaks silently and destroys claim history.
    #
    # This function builds a fresh dict out of named keys by construction, which
    # is what keeps the editor's `_open` / `_spec` UI state out of the record.
    # The same property means an id that is not explicitly carried across is an
    # id that is DROPPED — and a dropped id is re-minted on the next save, which
    # orphans every RA claim against that BOQ with no error anywhere. So the id
    # is read off the posted line and preserved verbatim.
    #
    # `used` enforces uniqueness within this one record. A duplicate is NOT a
    # rejection: it is what a copy-pasted row in the editor looks like, which is
    # a legitimate action producing a genuinely new line. First occurrence keeps
    # the id, the rest are minted fresh.
    used = set()
    for idx, li in enumerate(raw_lines, start=1):
        if not isinstance(li, dict):
            continue

        code = str(li.get("section") or "").strip()
        if code not in by_code:
            return [], f"Line {idx} is in section &quot;{P.esc(code)}&quot;, which is not defined above.", idx - 1

        item_no = _item_no(li.get("item_no"))
        if not item_no:
            return [], f"Line {idx} needs an item number.", idx - 1

        description = str(li.get("description") or "").strip()
        if not description:
            return [], f"Line {item_no} needs a description.", idx - 1

        # Keep a well-formed, not-yet-used id verbatim; mint in every other
        # case. Headers get one too: they carry no quantity and nothing claims
        # against them, but a revision has to carry every surviving line
        # forward and a uniform rule is one fewer thing to get wrong.
        lid = _line_id(li.get("line_id"))
        if not lid or lid in used:
            lid = _new_line_id()
            while lid in used:                    # uuid4 collision; never seen
                lid = _new_line_id()
        used.add(lid)

        is_header = bool(li.get("is_header"))

        # A specification header carries the paragraph and nothing else. Zeroing
        # here rather than hiding it in the renderer means the record itself is
        # honest — nothing downstream has to remember to skip these rows.
        if is_header:
            out.append({
                "line_id":        lid,
                "item_no":        item_no,
                "parent_item_no": _item_no(li.get("parent_item_no")),
                "section":        code,
                "is_header":      True,
                "description":    description,
                "remark":         str(li.get("remark") or "").strip(),
                "unit":           "",
                "area_qty":       {},
                "total_qty":      0.0,
                "supply_base_rate": None, "supply_escalation_pct": 0.0,
                "supply_rate": 0.0, "supply_amount": 0.0,
                "supply_hsn": "", "supply_gst_rate": 0.0,
                "install_base_rate": None, "install_escalation_pct": 0.0,
                "install_rate": 0.0, "install_amount": 0.0,
                "install_sac": "", "install_gst_rate": 0.0,
            })
            continue

        # ── Quantities ────────────────────────────────────────────────
        areas = by_code[code]["areas"]
        raw_aq = li.get("area_qty") or {}
        area_qty = {}
        for a in areas:
            v = _opt_num(raw_aq.get(a))
            # Only what was actually entered. A blank means "not on this floor",
            # which is different from "none of them here".
            if v is not None:
                area_qty[a] = v

        if areas:
            # With an area breakdown the total IS the breakdown. Letting the two
            # be typed independently on a *create* form invites a contradiction
            # at the moment of entry; a client's workbook that already contains
            # one is the importer's problem to report (Phase 2), not this
            # form's to reproduce.
            total_qty = sum(area_qty.values())
        else:
            total_qty = _num(li.get("total_qty"))

        if total_qty < 0:
            return [], f"Line {item_no} has a negative quantity.", idx - 1

        # ── Rates ─────────────────────────────────────────────────────
        s_base = _opt_num(li.get("supply_base_rate"))
        s_pct  = _num(li.get("supply_escalation_pct"))
        s_rate = _opt_num(li.get("supply_rate"))
        if s_rate is None:
            s_rate = _derived_rate(s_base, s_pct) or 0.0

        i_base = _opt_num(li.get("install_base_rate"))
        i_pct  = _num(li.get("install_escalation_pct"))
        i_rate = _opt_num(li.get("install_rate"))
        if i_rate is None:
            i_rate = _derived_rate(i_base, i_pct) or 0.0

        if s_rate < 0 or i_rate < 0:
            return [], f"Line {item_no} has a negative rate.", idx - 1

        hsn = str(li.get("supply_hsn") or "").strip()
        sac = str(li.get("install_sac") or "").strip()
        # Shape-only, and only when filled — exactly as the catalogue validates
        # it. A blank is allowed here and flagged downstream, because the BOQ is
        # priced long before anybody classifies the goods.
        if hsn and not _valid_tax_code(hsn):
            return [], f"Line {item_no}: HSN must be 4, 6 or 8 digits.", idx - 1
        if sac and not _valid_tax_code(sac):
            return [], f"Line {item_no}: SAC must be 4, 6 or 8 digits.", idx - 1

        out.append({
            "line_id":        lid,
            "item_no":        item_no,
            "parent_item_no": _item_no(li.get("parent_item_no")),
            "section":        code,
            "is_header":      False,
            "description":    description,
            "remark":         str(li.get("remark") or "").strip(),
            "unit":           str(li.get("unit") or "").strip(),
            "area_qty":       area_qty,
            "total_qty":      float(total_qty),

            "supply_base_rate":      s_base,
            "supply_escalation_pct": s_pct,
            "supply_rate":           float(s_rate),
            "supply_amount":         float(s_rate) * float(total_qty),
            "supply_hsn":            hsn,
            "supply_gst_rate":       _num(li.get("supply_gst_rate"), DEFAULT_GST_RATE),

            "install_base_rate":      i_base,
            "install_escalation_pct": i_pct,
            "install_rate":           float(i_rate),
            "install_amount":         float(i_rate) * float(total_qty),
            "install_sac":            sac,
            "install_gst_rate":       _num(li.get("install_gst_rate"), DEFAULT_GST_RATE),
        })

    if not out:
        return [], "Add at least one line item.", -1
    return out, "", -1


def _to_block(form) -> str:
    """The printable customer address block, same construction as a quotation."""
    parts = []
    for key in ("account_name", "bill_addr"):
        v = (form.get(key) or "").strip()
        if v:
            parts.append(v)
    city  = ", ".join(x for x in [(form.get("bill_city") or "").strip(),
                                  (form.get("bill_state") or "").strip()] if x)
    pin   = (form.get("bill_pin") or "").strip()
    if city or pin:
        parts.append(f"{city} - {pin}".strip(" -"))
    if (form.get("bill_phone") or "").strip():
        parts.append(f"Ph: {form['bill_phone'].strip()}")
    if (form.get("bill_gstin") or "").strip():
        parts.append(f"GSTIN: {form['bill_gstin'].strip()}")
    return "\n".join(parts)


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
# That is not theoretical here. `pipeline.esc()` escapes `< > & " '` and
# deliberately not braces, so a spec clause reading `{{ config }}` renders the
# Flask config — including SECRET_KEY — and a clause reading `{% for x in y %}`
# raises a TemplateSyntaxError that 500s every page carrying that text. The BOQ
# create form embeds all 56 clauses in its picker payload, so one malformed
# clause takes the whole form down for everybody.
#
# Returning the string directly is what Flask does with any `str` a view
# returns. It removes the second parse, and with it the injection. HTML
# escaping still does its own job — this changes nothing about XSS.
#
# ⚠ Six more modules — proforma, invoice, purchase, address, settings, dashboard
#   — took this same one-line fix in a later pass. It is still OPEN in
#   `quotation.py` and `product.py`, and the one-liner does not reach either:
#   quotation.py builds its pages with `.format()` and has attribute, <script>
#   and option-text sinks besides; product.py does not escape at all. Each wants
#   its own pass — ABOUT.md §7.9d.
# =============================================================================

def _page(html: str) -> str:
    """A finished page. See the note above — deliberately not Jinja-rendered."""
    return html


# =============================================================================
# ROUTES
# =============================================================================

@boq_bp.route("/")
def list_boqs():
    ensure_demo_boq()
    boqs     = STORE["boqs"]
    dash_url = url_for("dashboard.index")
    new_url  = url_for("boq.create_boq")

    msg      = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {P.esc(msg)}</div>'

    query = (request.args.get("q") or "").strip().lower()
    rows  = []
    for bid, b in boqs.items():
        if query:
            hay = " ".join(str(b.get(k) or "") for k in
                           ("ref", "project_name", "account_name", "site_location")).lower()
            if query not in hay:
                continue
        rows.append((bid, b))
    rows.sort(key=lambda kv: kv[1].get("ref", ""), reverse=True)

    total_supply = total_install = 0.0
    for _bid, b in boqs.items():
        s, i, _t = boq_totals(b)
        total_supply  += s
        total_install += i

    tiles_html = f"""
    <div class="pipe-tiles">
      <div class="pipe-tile t-open">
        <div class="pt-lbl">Total BOQ Value</div>
        <div class="pt-val">&#8377;&nbsp;{total_supply + total_install:,.0f}</div>
        <div class="pt-sub">{len(boqs)} bill{"s" if len(boqs) != 1 else ""} of quantities · basic value, taxes extra</div>
      </div>
      <div class="pipe-tile">
        <div class="pt-lbl">Supply</div>
        <div class="pt-val">&#8377;&nbsp;{total_supply:,.0f}</div>
        <div class="pt-sub">material</div>
      </div>
      <div class="pipe-tile">
        <div class="pt-lbl">Installation</div>
        <div class="pt-val">&#8377;&nbsp;{total_install:,.0f}</div>
        <div class="pt-sub">labour &amp; erection</div>
      </div>
    </div>"""

    if rows:
        rows_html = ""
        for bid, b in rows:
            sup, ins, tot = boq_totals(b)
            n_lines = sum(1 for li in b.get("line_items", []) if not li.get("is_header"))
            n_secs  = len(_sections_of(b))
            rows_html += f"""
            <tr>
              <td class="td-ref">{P.esc(b.get('ref'))}</td>
              <td class="td-muted">{P.esc(b.get('date'))}</td>
              <td class="td-cust">{P.esc(b.get('project_name'))}</td>
              <td>{P.esc(b.get('account_name'))}</td>
              <td class="td-muted col-h">{n_secs} section{"s" if n_secs != 1 else ""} · {n_lines} line{"s" if n_lines != 1 else ""}</td>
              <td class="td-muted col-h">&#8377;&nbsp;{sup:,.0f}</td>
              <td class="td-muted col-h">&#8377;&nbsp;{ins:,.0f}</td>
              <td style="font-weight:700;color:var(--brand);">&#8377;&nbsp;{tot:,.0f}</td>
              <td><a href="{url_for('boq.view_boq', id=bid)}" class="btn-view">&#128269; View</a></td>
            </tr>"""
        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>BOQ No.</th><th>Date</th><th>Project</th><th>Customer</th>
            <th class="col-h">Size</th><th class="col-h">Supply</th>
            <th class="col-h">Installation</th><th>Total</th><th></th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    elif boqs:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128269;</div><br>
          <strong>No BOQs match that search</strong>
          <a href="{url_for('boq.list_boqs')}" class="btn"
             style="display:inline-block;margin-top:1.1rem;">Show all</a>
        </div>"""
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128203;</div><br>
          <strong>No bills of quantities yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            A BOQ is the priced schedule for a project — sections, areas, and a
            supply and installation rate per line. It bills through RA bills.
          </p>
          <a href="{new_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">+ Create BOQ</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Bills of Quantities")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{BOQ_STYLES}</head>
    <body>{_nav()}
    <main>
      {alert_html}
      <div class="page-top">
        <h1>BOQ <span>Register</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            showing {len(rows)} of {len(boqs)}
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{new_url}" class="btn">+ Create BOQ</a>
        </div>
      </div>
      {tiles_html}
      <div class="filter-bar">
        <form method="GET" action="{url_for('boq.list_boqs')}">
          <input type="search" name="q" value="{P.esc(query)}"
                 placeholder="BOQ no., project, customer or site"/>
          <button type="submit" class="filter-tab">Search</button>
        </form>
      </div>
      {table_html}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · BOQ register</p></footer>
    </main></body></html>"""
    return _page(template)


def _document_html(boq: dict, show_rate_breakup: bool = False) -> str:
    """
    The A4 sheet — letterhead, header block, section tables, totals, signature.

    Shared by `/boq/view` and `/boq/print` so the two can never drift apart.
    They differ in exactly one thing, and it is this argument: the view shows
    the rate breakup because whoever is pricing the job needs it, and the print
    does not because it is the copy that goes to the client (§5).

    Everything else — the totals, the amount in words, the letterhead, the
    signature block — is built once, here. `boq_totals()` recomputes from the
    lines rather than reading the stored trio, so a printed sheet can never
    contradict its own lines (§3, property 7).
    """
    sup, ins, total = boq_totals(boq)

    # Escalation columns only earn their millimetres when something is actually
    # escalated — see HIDE_EMPTY_ESCALATION. `_section_table` ANDs this with
    # `show_rate_breakup`, so the two narrowings compose rather than fight.
    show_s_esc = (not HIDE_EMPTY_ESCALATION) or _any_escalation(boq, "supply_escalation_pct")
    show_i_esc = (not HIDE_EMPTY_ESCALATION) or _any_escalation(boq, "install_escalation_pct")

    sections_html = "".join(
        _section_table(boq, s, show_s_esc, show_i_esc, show_rate_breakup)
        for s in _sections_of(boq)
    )

    codes    = " + ".join(P.esc(s.get("code")) for s in _sections_of(boq))
    grand_lbl = f"TOTAL ({codes}) &gt;&gt;&gt;&gt;" if codes else "TOTAL &gt;&gt;&gt;&gt;"

    tax_note = ""
    if not PRINT_TAX:
        tax_note = ('<div class="boq-taxnote">GST EXTRA AS APPLICABLE. '
                    'Taxes fall due on the Running Account bill raised against this schedule.</div>')

    grand_html = f"""
    <div class="boq-grand">
      <table>
        <tr>
          <td class="bg-lbl">{grand_lbl}</td>
          <td class="bg-tag">Supply</td><td class="bg-amt">{_inr(sup)}</td>
          <td class="bg-tag">Installation</td><td class="bg-amt">{_inr(ins)}</td>
        </tr>
        <tr>
          <td class="bg-lbl">TOTAL BASIC VALUE</td>
          <td class="bg-tag"></td><td class="bg-amt"></td>
          <td class="bg-tag"></td><td class="bg-amt">{_inr(total)}</td>
        </tr>
      </table>
      <div class="boq-words">{_amount_in_words(total)}</div>
      {tax_note}
    </div>"""

    # ── Header meta, two columns ───────────────────────────────────────
    meta_col_1 = (
        # `quotation._meta()` does NOT escape — it belongs to a module that
        # largely does not (ABOUT.md §7.7), and importing a helper does not
        # import its discipline. Every value handed to it here is user input
        # heading for a printed document, so it is escaped at the call site.
        _meta("BOQ No.",       P.esc(boq.get("ref"))) +
        _meta("Project",       P.esc(boq.get("project_name"))) +
        _meta("Site",          P.esc(boq.get("site_location"))) +
        _meta("Payment Terms", P.esc(boq.get("payment_terms")))
    )
    meta_col_2 = (
        _meta("Date",              P.esc(boq.get("date"))) +
        _meta("Revision",          str(int(_num(boq.get("rev_no"), 0)))) +
        _meta("Rate Basis",        P.esc(boq.get("rate_basis_label"))) +
        _meta("Terms of Delivery", P.esc(boq.get("delivery_terms")))
    )

    to_lines   = [ln for ln in (boq.get("to") or "").strip().split("\n")]
    to_display = ""
    if to_lines and to_lines[0].strip():
        rest = "\n".join(to_lines[1:]).strip()
        to_display = f'<span class="dh-name">{P.esc(to_lines[0])}</span>'
        if rest:
            to_display += f"\n{P.esc(rest)}"

    ship_parts = []
    if not boq.get("ship_same"):
        sname = boq.get("ship_acct_name") or boq.get("account_name") or ""
        if sname:
            ship_parts.append(sname)
        if boq.get("ship_addr"):
            ship_parts.append(boq["ship_addr"])
        scity = ", ".join(x for x in [boq.get("ship_city", ""), boq.get("ship_state", "")] if x)
        if scity or boq.get("ship_pin"):
            ship_parts.append(f"{scity} - {boq.get('ship_pin','')}".strip(" -"))
    ship_html = ""
    if ship_parts:
        ship_html = ('<div class="dh-ship"><span class="dh-lbl">Site / Ship To</span>'
                     f'<div class="dh-body">{P.esc(chr(10).join(ship_parts))}</div></div>')

    notes_html = ""
    if (boq.get("notes") or "").strip():
        notes_html = (f'<div class="tnc-section"><div class="tnc-title">Notes</div>'
                      f'<div style="white-space:pre-wrap;">{P.esc(boq.get("notes"))}</div></div>')

    comp_br   = boq.get("company_branch") or B.COMPANY_NAME
    signatory = boq.get("auth_signatory") or B.COMPANY_SIGNATORY

    return f"""
<div class="doc-outer boq-outer">
<div class="quotation-doc boq-doc">

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
      </div>
    </td></tr></thead>

    <tfoot><tr><td>
      <div class="lh-foot">
        {B.COMPANY_LEGAL or B.COMPANY_NAME} &middot; BOQ {P.esc(boq.get('ref'))}
        &middot; basic value, taxes extra
      </div>
    </td></tr></tfoot>

    <tbody><tr><td>

      <div class="doc-box">
        <div class="doc-title">BILL OF QUANTITIES</div>
        <div class="doc-sub-boq">
          Priced schedule of work &middot; billed progressively through Running Account bills
        </div>

        <div class="doc-header">
          <div class="dh-cell">
            <span class="dh-lbl">To</span>
            <div class="dh-body">{to_display}</div>
            {ship_html}
          </div>
          <div class="dh-cell">{meta_col_1}</div>
          <div class="dh-cell">{meta_col_2}</div>
        </div>
      </div>

      {sections_html}
      {grand_html}
      {notes_html}

      <div class="sig-block">
        <div>
          <div class="sig-kv"><b>For</b><span>{P.esc(comp_br)}</span></div>
        </div>
        <div>
          <div class="sig-for">For {P.esc(comp_br)}</div>
          <div class="sig-name">{P.esc(signatory)}</div>
        </div>
      </div>
      <div class="sig-note">
        Quantities are provisional and billed as executed. Rates are firm for the
        duration of the project unless varied in writing.
      </div>

    </td></tr></tbody>
  </table>

</div>
</div>"""


@boq_bp.route("/view/<id>")
def view_boq(id: str):
    """
    The BOQ on screen — the operations panel, the RA chips, and the sheet.

    This is the INTERNAL view, so it passes `show_rate_breakup=True`: the base
    rate and the escalation percentage stay visible to whoever is pricing or
    revising the job. `/boq/print` is the copy that leaves the building and
    passes False. See §5.
    """
    ensure_demo_boq()
    boq = STORE["boqs"].get(id)
    if not boq:
        return redirect(url_for("boq.list_boqs", msg="BOQ not found.", type="error"))

    sup, ins, total = boq_totals(boq)

    # ── Running Account bills raised against this BOQ (screen only) ─────
    # STORE["ra_bills"] is read directly and the link is built with url_for —
    # `ra.py` imports THIS module, so importing it back would be a cycle. Same
    # one-way trick quotation.py uses for proformas. The collection does not
    # exist until Phase 3, hence the defensive .get().
    ra_rows = sorted(
        ((rid, r) for rid, r in (STORE.get("ra_bills") or {}).items()
         if r.get("boq_id") == id),
        key=lambda kv: int(kv[1].get("ra_no") or 0),
    )
    ra_html = ""
    if ra_rows:
        chips = "".join(
            f'<a class="ra-chip" href="{url_for("ra.view_ra", id=rid)}">'
            f'RA{P.esc(r.get("ra_no"))} &middot; {P.esc(r.get("ref"))} &middot; '
            f'&#8377;&nbsp;{float(r.get("grand_total") or 0):,.0f}</a>'
            for rid, r in ra_rows
        )
        ra_html = f"""
        <div class="ra-block">
          <span class="ra-lbl">Running Account bills raised</span>
          <div class="ra-strip">{chips}</div>
        </div>"""

    msg      = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {P.esc(msg)}</div>'

    n_lines = sum(1 for li in boq.get("line_items", []) if not li.get("is_header"))
    panel_html = f"""
    <div class="boq-panel">
      <div class="bp-head">
        <div>
          <div class="bp-title">Project Schedule</div>
          <div style="margin-top:.35rem;font-weight:700;">{P.esc(boq.get('project_name'))}</div>
          <div class="bp-sub">{P.esc(boq.get('site_location'))}</div>
        </div>
      </div>
      <div class="bp-grid">
        <div class="bp-cell">
          <div class="bp-lbl">Supply</div>
          <div class="bp-val">&#8377;&nbsp;{sup:,.0f}</div>
        </div>
        <div class="bp-cell">
          <div class="bp-lbl">Installation</div>
          <div class="bp-val">&#8377;&nbsp;{ins:,.0f}</div>
        </div>
        <div class="bp-cell">
          <div class="bp-lbl">Total Basic Value</div>
          <div class="bp-val" style="color:var(--brand);">&#8377;&nbsp;{total:,.0f}</div>
          <div class="bp-sub">taxes extra</div>
        </div>
        <div class="bp-cell">
          <div class="bp-lbl">Size</div>
          <div class="bp-val">{n_lines}</div>
          <div class="bp-sub">priced lines in {len(_sections_of(boq))} section(s)</div>
        </div>
      </div>
      {ra_html}
    </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(P.esc(boq.get('ref')) + " BOQ")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{BOQ_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    BOQ <span style="color:var(--brand);">{P.esc(boq.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">&#8592; All BOQs</a>
    <a href="{url_for('boq.create_boq')}" class="btn btn-ghost">+ New</a>
    <a href="{url_for('boq.print_boq', id=id)}" class="btn">&#128438;&nbsp;Print (landscape)</a>
  </div>
</div>

{alert_html}
{panel_html}

{_document_html(boq, show_rate_breakup=True)}

<footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE}</p></footer>
</main></body></html>"""
    return _page(template)


@boq_bp.route("/print/<id>")
def print_boq(id: str):
    """
    The issued BOQ — the sheet that goes to the client, and nothing else.

    It renders the same `_document_html()` as `/boq/view` with one difference:
    `show_rate_breakup=False`, so the base rate columns and the escalation
    columns are not emitted at all. That is a decision the client made on
    10 Aug 2026 — the escalated U/ Rate is what was agreed and what they are
    billed against; how it was arrived at is our side of the negotiation. See
    ABOUT.md §5.

    **Nothing about the record changes.** `supply_base_rate`,
    `install_base_rate` and both escalation percentages stay on every line, stay
    in the database, and stay on `/boq/view`. This route omits three columns
    from one table; it does not compute anything differently, and
    `test_boq_print_columns.py` pins the subtotals to prove it.

    No `_nav()` and no operations panel — the `.no-print` bar is the only screen
    furniture, exactly as `ra.print_ra()` does it one chain over.
    """
    ensure_demo_boq()
    boq = STORE["boqs"].get(id)
    if not boq:
        return redirect(url_for("boq.list_boqs", msg="BOQ not found.", type="error"))

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(P.esc(boq.get('ref')) + " BOQ")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{BOQ_STYLES}
  <style>
    @media print {{ .no-print {{ display:none !important; }} }}
  </style>
</head>
<body>
<main>

<div class="screen-acts no-print">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    BOQ <span style="color:var(--brand);">{P.esc(boq.get('ref'))}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{url_for('boq.view_boq', id=id)}" class="btn btn-ghost">&#8592; Back to BOQ</a>
    <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">All BOQs</a>
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print (landscape)</button>
  </div>
</div>

{_document_html(boq, show_rate_breakup=False)}

</main></body></html>"""
    return _page(template)


# =============================================================================
# CREATE — the line editor
# =============================================================================
#
# The editor is a browser-side model serialised into one hidden field on
# submit, the same shape of thing as the quotation's `selections_json` and for
# the same reason: the area quantity boxes on a line depend on which section
# the line is in, so the field set is not fixed and parallel form-field lists
# (purchase.py's simpler pattern) cannot express it.
#
# `_BOQ_JS` is a PLAIN string, not an f-string, so its braces are written once
# — the DASH_STYLES precedent. It is interpolated into the page as a value, so
# nothing in here needs doubling. It also no longer has to dodge `{{` and `{%`:
# this module returns finished HTML rather than re-rendering it through Jinja
# (see "why these views do not call render_template_string" below). The
# spaced-out object literals are left as they are — they read better anyway.
# =============================================================================

def _spec_catalog_json() -> str:
    """
    The specification library, shaped for the picker.

    Sent whole rather than fetched per keystroke — 56 clauses is a few hundred
    KB and the app has no API layer; the address book is embedded the same way
    (`address.picker_payload()`). `variants` comes across in full because the
    variant dropdown has to repopulate when the spec changes, with no round
    trip.

    Note what is NOT sent: nothing that would let the browser write back. The
    picker copies values onto a line and the line owns them from then on.
    """
    ensure_demo_specs()
    return _json_for_script({
        sid: {
            "code":       s.get("code") or "",
            "title":      s.get("title") or "",
            "category":   s.get("category") or "Other",
            "spec_text":  s.get("spec_text") or "",
            "supply_hsn": s.get("supply_hsn") or "",
            "install_sac": s.get("install_sac") or "",
            "supply_gst_rate":  s.get("supply_gst_rate") or "",
            "install_gst_rate": s.get("install_gst_rate") or "",
            "variants": [{
                "label":  v.get("label") or "",
                "unit":   v.get("unit") or "",
                "s_base": v.get("default_supply_base_rate"),
                "i_base": v.get("default_install_base_rate"),
            } for v in (s.get("variants") or [])],
        }
        for sid, s in STORE["specs"].items()
    })


def _demo_form_payload() -> tuple:
    """
    The seeded BOQ, shaped for the create form's editor.

    Returns `(boot, prefill)` — the editor's JSON model, and the plain form
    fields (project, customer, terms) that sit outside it.

    It reads the seeded *record* rather than `demo_data` directly, so what the
    form loads is exactly what `/boq/view` shows: one source, no second copy of
    the schedule to drift. The record's line items are converted back into the
    editor's shape, which is a lossless round trip because the editor's fields
    are a superset of what a line stores — the one asymmetry is `total_qty`,
    which the editor derives from the area boxes whenever the section declares
    areas, so it is only carried across for sections that declare none.

    Nothing is written to STORE. This fills the form; the user still presses
    Create, and can edit anything first.
    """
    ensure_demo_boq()
    src = STORE["boqs"].get(DD.BOQ_META["id"])
    if not src:
        return {"sections": [{"code": "A", "title": "", "areas": []}], "lines": []}, {}

    areas_by_code = {s["code"]: (s.get("areas") or []) for s in src["sections"]}

    def _s(v):
        """A stored number as the string the editor holds. None stays blank."""
        if v is None:
            return ""
        return f"{v:g}" if isinstance(v, float) else str(v)

    lines = []
    for li in src["line_items"]:
        row = {
            # Carried so the editor posts it back and `_clean_lines()` keeps it.
            # Without this the prefilled form re-mints every id on save and
            # every claim against the demo BOQ is orphaned.
            "line_id":        li.get("line_id", ""),
            "item_no":        li["item_no"],
            "parent_item_no": li["parent_item_no"],
            "section":        li["section"],
            "is_header":      bool(li["is_header"]),
            "description":    li["description"],
            "remark":         li.get("remark", ""),
            "unit":           li.get("unit", ""),
            "area_qty":       {k: _s(v) for k, v in (li.get("area_qty") or {}).items()},
            # Derived from the area boxes when the section has any, so sending
            # it would be sending a figure the editor is about to recompute.
            "total_qty":      "" if areas_by_code.get(li["section"]) else _s(li["total_qty"]),
            "supply_base_rate":      _s(li["supply_base_rate"]),
            "supply_escalation_pct": _s(li["supply_escalation_pct"]),
            "supply_rate":           _s(li["supply_rate"]),
            "supply_hsn":            li.get("supply_hsn", ""),
            "supply_gst_rate":       _s(li["supply_gst_rate"]),
            "install_base_rate":      _s(li["install_base_rate"]),
            "install_escalation_pct": _s(li["install_escalation_pct"]),
            "install_rate":           _s(li["install_rate"]),
            "install_sac":            li.get("install_sac", ""),
            "install_gst_rate":       _s(li["install_gst_rate"]),
        }
        if row["is_header"]:
            # A header carries the clause and nothing else; blanking the rest
            # keeps the editor's own rule ("a header has no numbers") true of
            # what it is handed, not just of what it saves.
            for k in ("unit", "total_qty", "supply_base_rate", "supply_escalation_pct",
                      "supply_rate", "supply_hsn", "supply_gst_rate",
                      "install_base_rate", "install_escalation_pct",
                      "install_rate", "install_sac", "install_gst_rate"):
                row[k] = ""
            row["area_qty"] = {}
        lines.append(row)

    boot = {
        "sections": [{"code": s["code"], "title": s.get("title", ""),
                      "areas": list(s.get("areas") or [])} for s in src["sections"]],
        "lines": lines,
    }

    prefill = {
        "project_name":     src.get("project_name", ""),
        "site_location":    src.get("site_location", ""),
        "rate_basis_label": src.get("rate_basis_label", ""),
        "account_name":     src.get("account_name", ""),
        "contact_person":   src.get("contact_person", ""),
        "bill_city":        src.get("bill_city", ""),
        "bill_state":       src.get("bill_state", ""),
        "bill_gstin":       src.get("bill_gstin", ""),
        "payment_terms":    src.get("payment_terms", ""),
        "delivery_terms":   src.get("delivery_terms", ""),
        "notes":            src.get("notes", ""),
    }
    return boot, prefill


_BOQ_JS = """
<script>
/* ═══ THE BOQ EDITOR ════════════════════════════════════════════════════
   MODEL is the single source of truth. Every input writes into it and the
   affected block re-renders from it; nothing is ever read back out of the
   DOM. On submit the whole thing is serialised into #boq_json.

   Re-rendering the whole editor on every keystroke would lose the caret, so
   only the changes that alter the SHAPE of a row (its section, or whether it
   is a specification header) trigger a re-render. Plain value edits write
   into MODEL and stop there. */

var MODEL = BOQ_BOOT;
var SPECS = BOQ_SPECS;
var ADDR_BOOK = BOQ_ADDR;

function el(id) { return document.getElementById(id); }

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function secByCode(code) {
  for (var i = 0; i < MODEL.sections.length; i++) {
    if (MODEL.sections[i].code === code) return MODEL.sections[i];
  }
  return null;
}

function num(v) { var n = parseFloat(String(v).replace(/,/g, '')); return isNaN(n) ? 0 : n; }

/* ── Sections ─────────────────────────────────────────────────────────
   Areas are typed as a comma-separated list because they are short labels
   ("External", "L0", "T1") and a repeating-row editor for two of them is
   more furniture than the job needs. */
function renderSections() {
  var h = '';
  for (var i = 0; i < MODEL.sections.length; i++) {
    var s = MODEL.sections[i];
    h += '<div class="sec-row">'
      +   '<div class="form-group"><label>Code</label>'
      +     '<input type="text" value="' + esc(s.code) + '" placeholder="A"'
      +      ' oninput="setSec(' + i + ',&quot;code&quot;,this.value)"/></div>'
      +   '<div class="form-group"><label>Section Title</label>'
      +     '<input type="text" value="' + esc(s.title) + '"'
      +      ' placeholder="WET SPRINKLER SYSTEM, As per Technical Specifications Part-A"'
      +      ' oninput="setSec(' + i + ',&quot;title&quot;,this.value)"/></div>'
      +   '<div class="form-group"><label>Areas / Floors (comma separated)</label>'
      +     '<input type="text" value="' + esc((s.areas || []).join(', ')) + '"'
      +      ' placeholder="External, L0   &#8212; leave blank for none"'
      +      ' onchange="setAreas(' + i + ',this.value)"/></div>'
      +   '<button type="button" class="btn-del" onclick="delSec(' + i + ')">&#10007;</button>'
      + '</div>';
  }
  el('sec-editor').innerHTML = h;
  renderPickers();
}

/* Both bulk-insert dropdowns are built here rather than server-side: the
   section list is edited in the browser, so a select rendered once on the
   server goes stale the moment a section is added or renamed. */
function renderPickers() {
  var spec = el('bulk-spec'), sec = el('bulk-section');
  if (spec && !spec.innerHTML) spec.innerHTML = specOptions('');
  if (sec) {
    var keep = sec.value;
    sec.innerHTML = secOptions(keep);
    if (keep) sec.value = keep;
  }
}

function setSec(i, key, val) {
  var old = MODEL.sections[i].code;
  MODEL.sections[i][key] = val.trim();
  if (key === 'code') {
    /* Re-point every line that was in the old section, so renaming a section
       does not orphan the lines that live in it. */
    for (var j = 0; j < MODEL.lines.length; j++) {
      if (MODEL.lines[j].section === old) MODEL.lines[j].section = val.trim();
    }
    renderLines();
  }
}

function setAreas(i, val) {
  var parts = val.split(','), out = [], seen = {};
  for (var k = 0; k < parts.length; k++) {
    var a = parts[k].trim();
    if (a && !seen[a]) { seen[a] = 1; out.push(a); }
  }
  MODEL.sections[i].areas = out;
  renderLines();   /* the area boxes on every line in this section change */
}

function addSec() {
  MODEL.sections.push({code: '', title: '', areas: []});
  renderSections();
}

function delSec(i) {
  MODEL.sections.splice(i, 1);
  renderSections();
  renderLines();
}

/* ── Lines ────────────────────────────────────────────────────────── */
function blankLine() {
  var first = MODEL.sections[0];
  return {
    /* A line the user just added is the one they are about to fill in. */
    _open: true,
    _spec: '', _variant: null, _auto: {},
    /* Blank means "the server mints one". The browser never invents a line id:
       the server is the only authority on it, so a new line, a copied row and
       a hand-edited payload all take the same path. Lines loaded into the
       editor from an existing BOQ arrive carrying theirs, and it rides back
       untouched inside MODEL on submit — that round trip is what keeps RA
       claims attached across an edit. */
    line_id: '',
    item_no: '', parent_item_no: '', section: (first ? first.code : ''),
    is_header: false, description: '', remark: '', unit: '',
    area_qty: {}, total_qty: '',
    supply_base_rate: '', supply_escalation_pct: '', supply_rate: '',
    supply_hsn: '', supply_gst_rate: '',
    install_base_rate: '', install_escalation_pct: '', install_rate: '',
    install_sac: '', install_gst_rate: ''
  };
}

function secOptions(cur) {
  var h = '';
  for (var i = 0; i < MODEL.sections.length; i++) {
    var c = MODEL.sections[i].code;
    h += '<option value="' + esc(c) + '"' + (c === cur ? ' selected' : '') + '>'
      +  esc(c || '(unnamed)') + '</option>';
  }
  return h;
}

/* ── The spec picker ───────────────────────────────────────────────────

   WHAT A PICK DOES TO A ROW — the rule, stated once.

   Every field on a line is in exactly one of three states:

     empty   nothing in it
     auto    what is in it was put there by the picker
     typed   the user edited it by hand

   and the picker obeys one sentence: **a pick overwrites empty and auto, and
   never overwrites typed.**

   From which:

     1. Choosing a SPEC fills description, HSN, SAC and both GST rates.
     2. Choosing a spec also RESETS the variant: unit and the two base rates
        belonged to a variant of the *previous* spec, so any of them still
        marked auto is cleared. Anything typed survives.
     3. Choosing a VARIANT fills unit, both base rates, and sets the
        description to the variant's label.
     4. An UNSIZED spec (one blank-labelled variant) applies its variant
        immediately — there is no size left to choose.
     5. Typing in a field marks it typed for good. Later picks leave it alone.

   Before this was specified, every fill was "only if the box is empty", which
   is right for a blank row and wrong for a re-selection: once a row had been
   populated once, changing the spec did nothing and choosing a variant did
   nothing, so a row could sit there showing one spec in the picker and another
   spec's description and unit. The `_auto` map is what tells a value the
   picker put there from a value a human chose.

   `_spec`, `_variant` and `_auto` live ON the line — not in a lookup keyed by
   row index, which is what they used to be. An index-keyed map silently
   desyncs the moment a line is deleted: every row below it inherits the
   previous row's spec. They are stripped in saveJSON(), so none of it reaches
   the record — a BOQ line still carries no spec_id (see spec.delete_spec). */

function autoMap(L) {
  if (!L._auto) L._auto = {};
  return L._auto;
}

/* Write a value AND remember the picker was the one that wrote it. */
function setAuto(L, key, value) {
  L[key] = value;
  autoMap(L)[key] = true;
}

/* May a pick write here? Empty or previously auto-filled: yes. Typed: no. */
function canFill(L, key) {
  var v = L[key];
  return v === '' || v === null || v === undefined || !!autoMap(L)[key];
}

/* Undo the picker's own fills for these fields, leaving typed values alone. */
function clearAuto(L, keys) {
  var a = autoMap(L);
  for (var k = 0; k < keys.length; k++) {
    if (a[keys[k]]) {
      L[keys[k]] = '';
      delete a[keys[k]];
    }
  }
}

/* Fields a VARIANT owns — cleared when the spec changes under them. */
var VARIANT_FIELDS = ['unit', 'supply_base_rate', 'install_base_rate'];

function specOptions(cur) {
  var h = '<option value="">&#8212; fill from spec library &#8212;</option>';
  var cats = {}, order = [];
  for (var sid in SPECS) {
    var c = SPECS[sid].category || 'Other';
    if (!cats[c]) { cats[c] = []; order.push(c); }
    cats[c].push(sid);
  }
  order.sort();
  for (var k = 0; k < order.length; k++) {
    h += '<optgroup label="' + esc(order[k]) + '">';
    var ids = cats[order[k]];
    for (var j = 0; j < ids.length; j++) {
      h += '<option value="' + esc(ids[j]) + '"'
        +  (ids[j] === cur ? ' selected' : '') + '>'
        +  esc(SPECS[ids[j]].title) + '</option>';
    }
    h += '</optgroup>';
  }
  return h;
}

/* Options carry the variant's INDEX, not its label. Five of the seeded labels
   are multi-line pump specifications; matching those back by string through an
   HTML attribute is fragile for no benefit, and an index cannot be mangled by
   escaping, whitespace or newline normalisation. */
function variantOptions(sid, chosen) {
  var sp = SPECS[sid];
  if (!sp) return '<option value="">&#8212;</option>';
  var h = '<option value="">&#8212; choose a size &#8212;</option>';
  for (var v = 0; v < sp.variants.length; v++) {
    var lab = sp.variants[v].label;
    /* A label may be several lines long; the dropdown wants one. */
    var shown = String(lab || '(unsized)').replace(/\\s+/g, ' ');
    if (shown.length > 70) shown = shown.slice(0, 68) + '\\u2026';
    h += '<option value="' + v + '"' + (v === chosen ? ' selected' : '') + '>'
      +  esc(shown) + '</option>';
  }
  return h;
}

function isUnsized(sp) {
  return sp && sp.variants.length === 1 && !sp.variants[0].label;
}

function fld(i, key, label, val, ph, cls) {
  return '<div class="form-group ' + (cls || '') + '"><label>' + label + '</label>'
    + '<input type="text" value="' + esc(val) + '" placeholder="' + esc(ph || '') + '"'
    + ' oninput="setLine(' + i + ',&quot;' + key + '&quot;,this.value)"/></div>';
}

/* ── Navigating 97 lines ───────────────────────────────────────────────

   A BOQ is long. Rendered as stacked full-height blocks it is less usable
   than the spreadsheet it replaces, so the editor renders a **one-line
   summary** per line — item no, description, quantity, rate — and opens the
   full panel only for the line being worked on.

   The summary is the point. Collapsing is just what makes it readable.

   Open/closed state lives ON the line (`_open`) and ON the section
   (`_open`), never in a map keyed by row index: an index-keyed map desyncs
   the moment a line is deleted, which is exactly the bug the spec picker
   had. Absent means closed, so a freshly loaded BOQ opens fully collapsed
   and `_demo_form_payload()` needs to say nothing about it.

   A header row's toggle folds the whole family: item 24 closed takes
   24.a-24.i with it, because that is how the schedule reads on paper. */

function isOpen(x) { return !!(x && x._open); }

/* The lines belonging to a section, with their MODEL.lines indexes intact —
   handlers address a line by its real index, not its position in a group. */
function linesOf(code) {
  var out = [];
  for (var i = 0; i < MODEL.lines.length; i++) {
    if (MODEL.lines[i].section === code) out.push(i);
  }
  return out;
}

/* Children of a header, by index: same section, parent_item_no matches. */
function childrenOf(i) {
  var P = MODEL.lines[i], out = [];
  if (!P.is_header || !P.item_no) return out;
  for (var j = 0; j < MODEL.lines.length; j++) {
    var C = MODEL.lines[j];
    if (j !== i && C.section === P.section && C.parent_item_no === P.item_no) {
      out.push(j);
    }
  }
  return out;
}

function money(v) {
  var n = num(v);
  if (!n) return '';
  return n.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function trunc(s, n) {
  /* \\s, doubled: _BOQ_JS is a normal Python string, so a single backslash
     here would be an invalid Python escape and would not survive. */
  s = String(s || '').replace(/\\s+/g, ' ').trim();
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

/* The one-line summary — enough to scan a schedule and spot a wrong line. */
function lineSummary(i, L) {
  var kids = L.is_header ? childrenOf(i) : [];
  var qty = L.is_header ? '' : (L.total_qty === '' || L.total_qty == null
        ? totalOf(L, (secByCode(L.section) || {}).areas || [])
        : String(L.total_qty));
  var chev = isOpen(L) ? '▾' : '▸';

  return '<div class="ls-row" onclick="toggleLine(' + i + ')">'
    +   '<span class="ls-chev">' + chev + '</span>'
    +   '<span class="ls-no">' + esc(L.item_no || '—') + '</span>'
    +   '<span class="ls-desc">' + esc(trunc(L.description, 96)) + '</span>'
    +   (L.is_header
        ? '<span class="ls-tag">spec' + (kids.length ? ' · ' + kids.length + ' items' : '') + '</span>'
        : '<span class="ls-qty">' + esc(qty) + (qty ? ' ' + esc(L.unit || '') : '') + '</span>'
          + '<span class="ls-rate">' + money(L.supply_rate) + '</span>'
          + '<span class="ls-rate">' + money(L.install_rate) + '</span>')
    + '</div>';
}

function lineBody(i, L) {
  var sec = secByCode(L.section);
  var areas = (sec && sec.areas) || [];
  var h = '<div class="lc-body">';

  h += '<div class="lc-head">'
    +   '<span class="lc-no">Line ' + (i + 1)
    +     (L.item_no ? ' &middot; ' + esc(L.item_no) : '') + '</span>'
    +   '<button type="button" class="btn-del" onclick="delLine(' + i + ')">Remove</button>'
    + '</div>'
    + '<div class="fg4">'
    +   '<div class="form-group"><label>Section</label>'
    +     '<select onchange="setSection(' + i + ',this.value)">'
    +       secOptions(L.section) + '</select></div>'
    +   fld(i, 'item_no', 'Item No.', L.item_no, '4.1')
    +   fld(i, 'parent_item_no', 'Under Item', L.parent_item_no, '4')
    +   '<div class="form-group"><label>Row Type</label><div class="check-row">'
    +     '<input type="checkbox" id="hdr' + i + '"' + (L.is_header ? ' checked' : '')
    +      ' onchange="setHeader(' + i + ',this.checked)"/>'
    +     '<label for="hdr' + i + '">Specification header</label></div></div>'
    + '</div>';

  h += '<div class="fg2" style="margin-top:.7rem;">'
    +   '<div class="form-group span-all"><label>Description / Specification</label>'
    +     '<textarea placeholder="Supply, Fabrication, Installation, Testing of ..."'
    +      ' oninput="setLine(' + i + ',&quot;description&quot;,this.value)">'
    +      esc(L.description) + '</textarea></div>'
    + '</div>';

  var picked = L._spec || '';
  var sp = SPECS[picked];
  h += '<div class="fg4" style="margin-top:.7rem;">'
    +   '<div class="form-group"><label>Fill from spec library</label>'
    +     '<select onchange="fillFromSpec(' + i + ',this.value)">'
    +       specOptions(picked) + '</select></div>'
    +   '<div class="form-group"><label>Variant</label>'
    +     (sp && !isUnsized(sp)
        ? '<select onchange="fillFromVariant(' + i + ',this.value)">'
          + variantOptions(picked, L._variant) + '</select>'
        : '<select disabled><option>' + (sp ? '(unsized)' : '&#8212;') + '</option></select>')
    +   '</div>'
    +   fld(i, 'remark', 'Remark (internal &#8212; does not print)', L.remark,
            '2000/nos extra for tamper switch')
    +   fld(i, 'unit', 'Unit', L.unit, 'Mtrs')
    + '</div>';

  if (!L.is_header) {
    /* Quantities. With an area breakdown the total IS the breakdown, so it
       is shown derived rather than typed — two independently typed figures
       that must agree are two figures that can disagree. */
    h += '<div class="lc-track">Quantity</div><div class="lc-areas">';
    if (areas.length) {
      for (var a = 0; a < areas.length; a++) {
        var an = areas[a];
        h += '<div class="form-group lc-area"><label>' + esc(an) + '</label>'
          +  '<input type="text" value="'
          +   esc(L.area_qty[an] == null ? '' : L.area_qty[an]) + '"'
          +  ' oninput="setArea(' + i + ',' + JSON.stringify(an).replace(/"/g, '&quot;')
          +  ',this.value)"/></div>';
      }
      h += '<div class="form-group lc-area"><label>Total Qty</label>'
        +  '<div class="readonly-field" id="tq' + i + '">'
        +   esc(totalOf(L, areas)) + '</div></div>';
    } else {
      h += '<div class="form-group lc-area"><label>Total Qty</label>'
        +  '<input type="text" value="' + esc(L.total_qty) + '"'
        +  ' oninput="setLine(' + i + ',&quot;total_qty&quot;,this.value)"/></div>'
        +  '<span class="lc-none">This section declares no areas '
        +  '&#8212; the total stands alone.</span>';
    }
    h += '</div>';

    h += '<div class="lc-track">Supply</div><div class="fg5">'
      +   fld(i, 'supply_base_rate', 'Base Rate', L.supply_base_rate, '1760  or  -')
      +   fld(i, 'supply_escalation_pct', 'Escalation %', L.supply_escalation_pct, '15')
      +   '<div class="form-group"><label>Unit Rate</label>'
      +     '<input type="text" value="' + esc(L.supply_rate) + '" placeholder="2024"'
      +      ' oninput="setLine(' + i + ',&quot;supply_rate&quot;,this.value)"/>'
      +     '<div class="derived" id="sd' + i + '"></div></div>'
      +   fld(i, 'supply_hsn', 'HSN', L.supply_hsn, '73090090')
      +   fld(i, 'supply_gst_rate', 'GST %', L.supply_gst_rate, '18')
      + '</div>';

    h += '<div class="lc-track">Installation</div><div class="fg5">'
      +   fld(i, 'install_base_rate', 'Base Rate', L.install_base_rate, '1200  or  -')
      +   fld(i, 'install_escalation_pct', 'Escalation %', L.install_escalation_pct, '0')
      +   '<div class="form-group"><label>Unit Rate</label>'
      +     '<input type="text" value="' + esc(L.install_rate) + '" placeholder="1200"'
      +      ' oninput="setLine(' + i + ',&quot;install_rate&quot;,this.value)"/>'
      +     '<div class="derived" id="id' + i + '"></div></div>'
      +   fld(i, 'install_sac', 'SAC', L.install_sac, '995461')
      +   fld(i, 'install_gst_rate', 'GST %', L.install_gst_rate, '18')
      + '</div>';
  }

  return h + '</div>';
}

function lineCard(i, L, extraClass) {
  return '<div class="line-card' + (L.is_header ? ' is-spec' : '')
    + (isOpen(L) ? ' is-open' : '') + (extraClass || '') + '" data-line="' + i + '">'
    + lineSummary(i, L)
    + (isOpen(L) ? lineBody(i, L) : '')
    + '</div>';
}

function sectionTotals(code) {
  var s = 0, ins = 0;
  var idx = linesOf(code);
  for (var k = 0; k < idx.length; k++) {
    var L = MODEL.lines[idx[k]];
    if (L.is_header) continue;
    var q = num(L.total_qty === '' || L.total_qty == null
      ? totalOf(L, (secByCode(code) || {}).areas || []) : L.total_qty);
    s += num(L.supply_rate) * q;
    ins += num(L.install_rate) * q;
  }
  return [s, ins];
}

function renderLines() {
  var h = '';
  var placed = {};

  for (var si = 0; si < MODEL.sections.length; si++) {
    var S = MODEL.sections[si];
    var idx = linesOf(S.code);
    for (var k = 0; k < idx.length; k++) placed[idx[k]] = true;
    var tot = sectionTotals(S.code);

    h += '<div class="sec-group" id="secgrp-' + si + '">'
      +   '<div class="sec-bar" onclick="toggleSection(' + si + ')">'
      +     '<span class="ls-chev">' + (isOpen(S) ? '▾' : '▸') + '</span>'
      +     '<span class="sb-code">' + esc(S.code || '?') + '</span>'
      +     '<span class="sb-title">' + esc(trunc(S.title, 74) || '(untitled section)') + '</span>'
      +     '<span class="sb-count">' + idx.length + ' line' + (idx.length === 1 ? '' : 's') + '</span>'
      +     '<span class="ls-rate">' + money(tot[0]) + '</span>'
      +     '<span class="ls-rate">' + money(tot[1]) + '</span>'
      +   '</div>';

    if (isOpen(S)) {
      h += '<div class="sec-lines">';
      if (!idx.length) {
        h += '<div class="lc-none" style="padding:.6rem .8rem;">No lines in this section yet.</div>';
      }
      var hidden = {};
      for (var k2 = 0; k2 < idx.length; k2++) {
        var i = idx[k2], L = MODEL.lines[i];
        /* A closed header folds its children away with it. */
        if (L.is_header && !isOpen(L)) {
          var kids = childrenOf(i);
          for (var c = 0; c < kids.length; c++) hidden[kids[c]] = true;
        }
      }
      for (var k3 = 0; k3 < idx.length; k3++) {
        var i2 = idx[k3], L2 = MODEL.lines[i2];
        if (hidden[i2]) continue;
        var cls = L2.parent_item_no ? ' is-child' : '';
        h += lineCard(i2, L2, cls);
      }
      h += '</div>';
    }
    h += '</div>';
  }

  /* Lines whose section no longer exists would otherwise be invisible — and
     an invisible line still posts and still counts. Show them. */
  var orphans = [];
  for (var o = 0; o < MODEL.lines.length; o++) if (!placed[o]) orphans.push(o);
  if (orphans.length) {
    h += '<div class="sec-group orphan-group">'
      +  '<div class="sec-bar sec-bar-warn">'
      +    '<span class="sb-code">!</span>'
      +    '<span class="sb-title">' + orphans.length + ' line(s) in a section that no longer exists'
      +    ' &mdash; give them a section or remove them</span></div>'
      +  '<div class="sec-lines">';
    for (var o2 = 0; o2 < orphans.length; o2++) {
      h += lineCard(orphans[o2], MODEL.lines[orphans[o2]], '');
    }
    h += '</div></div>';
  }

  el('line-editor').innerHTML = h;
  renderJump();
  renderDupWarn();
  renderZeroQty();
  for (var k4 = 0; k4 < MODEL.lines.length; k4++) {
    if (isOpen(MODEL.lines[k4])) hint(k4);
  }
}

/* ── Open / close ─────────────────────────────────────────────────────── */

function toggleLine(i) {
  var L = MODEL.lines[i];
  L._open = !isOpen(L);
  renderLines();
}

function toggleSection(si) {
  var S = MODEL.sections[si];
  S._open = !isOpen(S);
  renderLines();
}

function setAllOpen(open) {
  for (var s = 0; s < MODEL.sections.length; s++) MODEL.sections[s]._open = open;
  for (var i = 0; i < MODEL.lines.length; i++) MODEL.lines[i]._open = open;
  renderLines();
}

function expandAll() { setAllOpen(true); }
function collapseAll() { setAllOpen(false); }

/* Jump to a section: open it, render, then scroll to it. */
function jumpTo(si) {
  if (si === '' || si === null) return;
  si = parseInt(si, 10);
  var S = MODEL.sections[si];
  if (!S) return;
  S._open = true;
  renderLines();
  var node = el('secgrp-' + si);
  if (node && node.scrollIntoView) node.scrollIntoView({block: 'start'});
}

/* ── Duplicate item numbers — a WARNING, never a block ──────────────────

   The client's own Sify schedule has one: section A carries item 17 twice, on
   a flexible sprinkler drop and a 150 mm butterfly valve. It is in THEIR
   source workbook, not something this app introduced, and it is theirs to
   decide about — so this surfaces the ambiguity and refuses to act on it.

   It cannot break anything, because a claim is matched on the line's opaque
   `line_id` and never on the item number. That is exactly why this is a
   warning: before the identifier existed, two lines sharing an item number
   silently collapsed into one in the over-claim guard. Now they do not, and
   the only remaining cost is that two rows on the printed sheet read alike —
   which is a thing to tell somebody, not a thing to refuse to save. */
function renderDupWarn() {
  var box = el('dup-warn');
  if (!box) return;

  var seen = {}, dupes = [];
  for (var i = 0; i < MODEL.lines.length; i++) {
    var L = MODEL.lines[i];
    var ino = String(L.item_no || '').trim();
    if (!ino) continue;
    var k = String(L.section || '') + '\\u0000' + ino;
    if (seen[k]) {
      if (seen[k] === 1) { dupes.push({sec: L.section, ino: ino}); seen[k] = 2; }
    } else {
      seen[k] = 1;
    }
  }

  if (!dupes.length) { box.innerHTML = ''; return; }

  var list = '';
  for (var d = 0; d < dupes.length; d++) {
    list += (d ? ', ' : '') + esc(dupes[d].ino)
         +  ' <span class="fh-sec">(section ' + esc(dupes[d].sec || '?') + ')</span>';
  }
  box.innerHTML =
    '<div class="form-hint">'
  +   '<span class="fh-icon">&#9888;</span>'
  +   '<span><b>Repeated item number' + (dupes.length === 1 ? '' : 's') + ':</b> ' + list
  +   '. Two lines in the same section share a number, so they will print alike '
  +   'and be hard to tell apart on a measurement sheet. '
  +   '<b>This does not affect billing</b> &mdash; each line is tracked separately '
  +   'and claims cannot run together. Saving is not blocked.</span>'
  + '</div>';
}

/* ── Priced lines carrying no quantity — a HINT, never an error ─────────

   A line with a base rate, an escalation and a unit rate but Total Qty 0
   contributes 0.00 to the amount and 0.00 to the subtotal. A schedule made
   only of those shows a full set of rates against a grand total of zero, and
   nothing on the page says why — which reads as a broken form rather than as
   what it is.

   It is a hint and not an error because quantity 0 is a LEGITIMATE state: BOQ
   quantities are provisional and billed as executed (the printed footer
   already says so), so a line awaiting site measurement is correct, not
   incomplete.

   HEADERS ARE NOT COUNTED. A specification header carries the clause and no
   quantity by design (§4.2), so flagging it would be pure noise and would
   train the user to ignore the band.

   The RA consequence is the part worth knowing at entry time rather than
   later: `ra.approved_by_line()` reads `total_qty`, so a line approved at 0
   has nothing to claim against and EVERY RA claim on it is refused by the
   over-claim block. Better learned here than when the first RA bill will not
   save. */
function renderZeroQty() {
  var box = el('zeroqty-hint');
  if (!box) return;

  var n = 0, priced = 0;
  for (var i = 0; i < MODEL.lines.length; i++) {
    var L = MODEL.lines[i];
    if (L.is_header) continue;
    priced++;
    /* The same resolution `lineSummary()` and `sectionTotals()` use: with an
       area breakdown the total IS the breakdown, so read it from the boxes. */
    var qty = (L.total_qty === '' || L.total_qty == null)
      ? totalOf(L, (secByCode(L.section) || {}).areas || [])
      : L.total_qty;
    if (num(qty) === 0) n++;
  }

  if (!n || !priced) { box.innerHTML = ''; return; }

  var isAll = (n === priced);
  box.innerHTML =
    '<div class="form-hint">'
  +   '<span class="fh-icon">&#9888;</span>'
  +   '<span><b>' + (isAll ? 'Every priced line has' : n + ' priced line'
        + (n === 1 ? ' has' : 's have')) + ' a quantity of 0.</b> '
  +   'They carry rates but contribute <b>nothing</b> to the total'
  +   (isAll ? ', which is why it reads 0.00' : '') + '. '
  +   'That is a valid state for work awaiting site measurement &mdash; '
  +   'quantities are provisional and billed as executed. '
  +   'Note that an RA bill cannot claim against a line approved at 0.'
  +   '</span>'
  + '</div>';
}

function renderJump() {
  var box = el('jump-bar');
  if (!box) return;
  var h = '<span class="jb-lbl">Jump to</span>';
  for (var s = 0; s < MODEL.sections.length; s++) {
    var S = MODEL.sections[s];
    h += '<button type="button" class="jb-btn" onclick="jumpTo(' + s + ')">'
      +  esc(S.code || '?') + '</button>';
  }
  h += '<span class="jb-sp"></span>'
    +  '<button type="button" class="jb-btn" onclick="expandAll()">Expand all</button>'
    +  '<button type="button" class="jb-btn" onclick="collapseAll()">Collapse all</button>';
  box.innerHTML = h;
}

function totalOf(L, areas) {
  var t = 0, any = false;
  for (var a = 0; a < areas.length; a++) {
    var v = L.area_qty[areas[a]];
    if (v !== '' && v != null) { t += num(v); any = true; }
  }
  return any ? String(Math.round(t * 1000) / 1000) : '';
}

/* The escalated rate is a SUGGESTION, never imposed — purchase.py's fillRate()
   makes the same call about a catalogue price. The client's own sheets carry a
   dozen lines where the agreed rate deliberately differs from
   base x (1 + escalation), so overwriting the box would destroy real data. The
   hint says so rather than correcting it. */
function hint(i) {
  var L = MODEL.lines[i];
  if (!L || L.is_header) return;
  var pairs = [['sd', 'supply_base_rate', 'supply_escalation_pct', 'supply_rate'],
               ['id', 'install_base_rate', 'install_escalation_pct', 'install_rate']];
  for (var p = 0; p < pairs.length; p++) {
    var box = el(pairs[p][0] + i);
    if (!box) continue;
    var base = L[pairs[p][1]], pct = L[pairs[p][2]], rate = L[pairs[p][3]];
    var txt = '';
    if (base !== '' && base != null && String(base).trim() !== '-') {
      var d = Math.round(num(base) * (1 + num(pct) / 100) * 100) / 100;
      if (rate === '' || rate == null) {
        txt = 'suggests <b>' + d + '</b> &#8212; <a href="#" onclick="useRate('
            + i + ',&quot;' + pairs[p][3] + '&quot;,' + d + ');return false;">use</a>';
      } else if (Math.abs(num(rate) - d) > 0.005) {
        txt = 'escalation implies ' + d + ' &#8212; rate differs, kept as entered';
      }
    }
    box.innerHTML = txt;
  }
}

function useRate(i, key, v) {
  MODEL.lines[i][key] = String(v);
  renderLines();
}

function setLine(i, key, val) {
  var L = MODEL.lines[i];
  L[key] = val;
  /* The user has now had their say about this field. Rule 5: a later pick
     leaves it alone. Deleting the flag rather than setting a "typed" one keeps
     the map small and makes `canFill` a single lookup. */
  delete autoMap(L)[key];
  if (key === 'supply_base_rate' || key === 'supply_escalation_pct'
   || key === 'supply_rate' || key === 'install_base_rate'
   || key === 'install_escalation_pct' || key === 'install_rate') {
    hint(i);
  }
}

function setArea(i, area, val) {
  MODEL.lines[i].area_qty[area] = val;
  var sec = secByCode(MODEL.lines[i].section);
  var box = el('tq' + i);
  if (box && sec) box.textContent = totalOf(MODEL.lines[i], sec.areas || []);
}

function setSection(i, code) {
  MODEL.lines[i].section = code;
  /* An area quantity keyed to a name the new section does not declare would be
     dropped silently on save, so it is dropped here, where the user can see
     it happen. */
  var sec = secByCode(code), keep = {};
  var areas = (sec && sec.areas) || [];
  for (var a = 0; a < areas.length; a++) {
    var n = areas[a];
    if (MODEL.lines[i].area_qty[n] != null) keep[n] = MODEL.lines[i].area_qty[n];
  }
  MODEL.lines[i].area_qty = keep;
  renderLines();
}

function setHeader(i, on) {
  MODEL.lines[i].is_header = on;
  renderLines();
}

/* Choosing a SPEC. See "WHAT A PICK DOES TO A ROW" above.

   A rate in the library is a reference default from another project, not what
   was agreed on this one — purchase.py's fillRate() makes the same call about
   a vendor's price, and handover §4.2 rule 4 says the BOQ stores what was
   entered. "Never overwrites typed" is that rule; "overwrites auto" is what
   makes changing your mind work. */
function fillFromSpec(i, sid) {
  var L = MODEL.lines[i];
  L._spec = sid;
  L._variant = null;

  var sp = SPECS[sid];
  if (!sp) { renderLines(); return; }

  /* Whatever a variant of the PREVIOUS spec left behind is no longer true of
     this row. Typed values are the user's and stay. */
  clearAuto(L, VARIANT_FIELDS);

  if (canFill(L, 'description'))      setAuto(L, 'description', sp.spec_text);
  if (canFill(L, 'supply_hsn'))       setAuto(L, 'supply_hsn', sp.supply_hsn);
  if (canFill(L, 'install_sac'))      setAuto(L, 'install_sac', sp.install_sac);
  if (canFill(L, 'supply_gst_rate'))  setAuto(L, 'supply_gst_rate', String(sp.supply_gst_rate));
  if (canFill(L, 'install_gst_rate')) setAuto(L, 'install_gst_rate', String(sp.install_gst_rate));

  /* Nothing left to choose, so apply it now. */
  if (isUnsized(sp)) { applyVariant(i, 0); }

  renderLines();
}

/* Choosing a VARIANT, by index. */
function fillFromVariant(i, idx) {
  if (idx === '' || idx === null || idx === undefined) return;
  applyVariant(i, parseInt(idx, 10));
  renderLines();
}

function applyVariant(i, idx) {
  var L = MODEL.lines[i];
  var sp = SPECS[L._spec];
  if (!sp) return;
  var v = sp.variants[idx];
  if (!v) return;

  L._variant = idx;
  if (canFill(L, 'unit')) setAuto(L, 'unit', v.unit);
  if (canFill(L, 'supply_base_rate') && v.s_base !== null && v.s_base !== '') {
    setAuto(L, 'supply_base_rate', String(v.s_base));
  }
  if (canFill(L, 'install_base_rate') && v.i_base !== null && v.i_base !== '') {
    setAuto(L, 'install_base_rate', String(v.i_base));
  }
  /* On the printed sheet the child row of a size family says the variant
     label, and the header above it carries the clause. An unsized spec has no
     label, so its description stays the clause itself. */
  if (v.label && canFill(L, 'description')) {
    setAuto(L, 'description', v.label);
  }
}

/* ── Insert a whole size family ────────────────────────────────────────
   One click turns a spec into the shape their sheet actually uses: a header
   row carrying the clause, then one child row per size, numbered N, N.a,
   N.b … An unsized spec has nothing to expand, so it inserts one plain line.
   Building item 24 by hand is otherwise ten rows of typing. */
function insertFamily() {
  var sid = el('bulk-spec').value;
  var code = el('bulk-section').value;
  var sp = SPECS[sid];
  if (!sp) return;

  var next = nextItemNo(code);
  /* Land the family somewhere visible: open its section, and open the header
     so its children show as summaries. The children themselves stay closed —
     ten expanded panels is the problem this is here to avoid. */
  var S = secByCode(code);
  if (S) S._open = true;

  if (isUnsized(sp)) {
    var one = blankLine();
    one._open = false;
    one.section = code;
    one.item_no = String(next);
    setAuto(one, 'description', sp.spec_text);
    applySpecFields(one, sp, sid);
    applyVariantFields(one, sp.variants[0], 0);
    MODEL.lines.push(one);
  } else {
    var head = blankLine();
    head.section = code;
    head.item_no = String(next);
    head.is_header = true;
    head._open = true;
    head._spec = sid;
    setAuto(head, 'description', sp.spec_text);
    MODEL.lines.push(head);

    var letters = 'abcdefghijklmnopqrstuvwxyz';
    for (var v = 0; v < sp.variants.length; v++) {
      var kid = blankLine();
      kid._open = false;
      kid.section = code;
      kid.item_no = String(next) + '.' + letters.charAt(v);
      kid.parent_item_no = String(next);
      setAuto(kid, 'description', sp.variants[v].label);
      applySpecFields(kid, sp, sid);
      applyVariantFields(kid, sp.variants[v], v);
      MODEL.lines.push(kid);
    }
  }
  el('bulk-spec').value = '';
  renderLines();
  window.scrollTo(0, document.body.scrollHeight);
}

function applySpecFields(L, sp, sid) {
  L._spec = sid;
  setAuto(L, 'supply_hsn', sp.supply_hsn);
  setAuto(L, 'install_sac', sp.install_sac);
  setAuto(L, 'supply_gst_rate', String(sp.supply_gst_rate));
  setAuto(L, 'install_gst_rate', String(sp.install_gst_rate));
}

function applyVariantFields(L, v, idx) {
  L._variant = idx;
  setAuto(L, 'unit', v.unit);
  if (v.s_base !== null && v.s_base !== '') setAuto(L, 'supply_base_rate', String(v.s_base));
  if (v.i_base !== null && v.i_base !== '') setAuto(L, 'install_base_rate', String(v.i_base));
}

/* The next whole number free in this section — 24 when 1..23 are taken. */
function nextItemNo(code) {
  var top = 0;
  for (var i = 0; i < MODEL.lines.length; i++) {
    if (MODEL.lines[i].section !== code) continue;
    var m = /^(\\d+)/.exec(String(MODEL.lines[i].item_no || ''));
    if (m) top = Math.max(top, parseInt(m[1], 10));
  }
  return top + 1;
}

function addLine() {
  var L = blankLine();
  MODEL.lines.push(L);
  /* Adding a line to a section the user has collapsed would put it somewhere
     they cannot see. */
  var S = secByCode(L.section);
  if (S) S._open = true;
  renderLines();
  window.scrollTo(0, document.body.scrollHeight);
}

function delLine(i) {
  MODEL.lines.splice(i, 1);
  renderLines();
}

/* The editor's own bookkeeping — `_spec`, `_variant`, `_auto`, `_open` — is UI
   state and must never reach the record: a BOQ line carries no spec_id
   (handover §4.2) and certainly no scroll position.

   It IS posted, though, and deliberately. The record is kept clean on the
   SERVER, by construction: `_clean_lines()` and `_clean_sections()` build a
   fresh dict out of named keys, so an underscore key cannot get in whatever
   the browser sends, and `test_no_ui_state_reaches_the_record` asserts it.
   Stripping here as well would throw the state away on a rejected POST — the
   user would get their input back with every line slammed shut and the
   picker's typed/auto memory wiped, which is the opposite of the
   always-return-the-user's-input contract this form is held to. */
function saveJSON() {
  el('boq_json').value = JSON.stringify(MODEL);
  return true;
}

function toggleShipSame(same) {
  var box = el('ship-fields');
  if (box) box.style.display = same ? 'none' : '';
}

/* ── Address book picker — same behaviour as the quotation form ────── */
function setSelectValue(e, value) {
  if (!e || !value) return;
  var found = Array.prototype.some.call(e.options, function (o) { return o.value === value; });
  if (!found) {
    var opt = document.createElement('option');
    opt.value = value; opt.textContent = value;
    e.appendChild(opt);
  }
  e.value = value;
}

function applyAddr(kind, sel) {
  var a = ADDR_BOOK[sel.value];
  if (!a) return;
  var set = function (id, v) { var e = el(id); if (e && v) e.value = v; };
  var street = [a.line1, a.line2, a.landmark].filter(Boolean).join('\\n');
  var addrEl = el(kind + '_addr');
  if (addrEl) addrEl.value = street;
  set(kind + '_city', a.city);
  set(kind + '_pin', a.pincode);
  set(kind + '_phone', a.phone);
  set(kind + '_gstin', a.gstin);
  setSelectValue(el(kind + '_state'), a.state);
  if (kind === 'bill') {
    set('account_name', a.company);
    set('contact_person', a.contact_name);
  } else {
    set('ship_acct_name', a.company);
    var same = el('ship_same_chk');
    if (same && same.checked) { same.checked = false; toggleShipSame(false); }
  }
}

renderSections();
renderLines();
</script>
"""


@boq_bp.route("/create", methods=["GET", "POST"])
def create_boq():
    ensure_demo_specs()

    error = ""
    sections: list = []
    lines: list = []

    if request.method == "POST":
        form = request.form

        # Validation, in order — nothing is written to STORE until every one
        # of these passes, so a rejected POST leaves no half-built record.
        err_idx = -1
        raw_json = form.get("boq_json", "")
        raw_sections, raw_lines, error = _parse_payload(raw_json)

        if not error and not (form.get("date") or "").strip():
            error = "The BOQ needs a date."
        if not error and not (form.get("project_name") or "").strip():
            error = "The BOQ needs a project name."
        if not error and not (form.get("account_name") or "").strip():
            error = "The BOQ needs a customer account name."

        if not error:
            sections, error = _clean_sections(raw_sections)
        if not error:
            # The byte length of what was POSTed, not of a re-serialisation of
            # it: whitespace and key order in the browser's own JSON are part of
            # what has to fit on the wire, and re-dumping it here would measure
            # a string nobody sent.
            lines, error, err_idx = _clean_lines(
                raw_lines, sections, len(raw_json.encode("utf-8")))

        if not error:
            datestr = (form.get("date") or "").strip()
            bid     = str(uuid.uuid4())

            boq = {
                "id":   bid,
                "ref":  _next_ref(datestr),
                "fy":   P.fy_of(datestr),
                "date": datestr,
                "rev_no": int(_num(form.get("rev_no"), 0)),

                # The previous BOQ id this one supersedes, or "" for an
                # original. A revision is a NEW record rather than an edit,
                # because RA bills are measured against a specific revision and
                # an issued claim's basis must never move under it. `ra.py`
                # walks this field to sum a line's claims across the whole
                # chain — without that, a revision would reset every line's
                # claimed quantity to zero and defeat the over-claim block.
                # Nothing writes a non-empty value yet; the revision route is
                # not built. See PHASE4_RA_DESIGN.md §4.
                "supersedes": (form.get("supersedes") or "").strip(),

                "project_name":  (form.get("project_name") or "").strip(),
                "site_location": (form.get("site_location") or "").strip(),

                "account_name":   (form.get("account_name") or "").strip(),
                "contact_person": (form.get("contact_person") or "").strip(),
                "to":             _to_block(form),
                "bill_gstin":     (form.get("bill_gstin") or "").strip(),
                "ship_same":      bool(form.get("ship_same")),
                "ship_acct_name": (form.get("ship_acct_name") or "").strip(),
                "ship_addr":      (form.get("ship_addr") or "").strip(),
                "ship_city":      (form.get("ship_city") or "").strip(),
                "ship_state":     (form.get("ship_state") or "").strip(),
                "ship_pin":       (form.get("ship_pin") or "").strip(),

                "rate_basis_label": (form.get("rate_basis_label") or "").strip() or DEFAULT_RATE_BASIS,
                "sections":   sections,
                "line_items": lines,

                # Stored per §4.3 for the register and the dashboard. The
                # document recomputes them from the lines every render, so a
                # stored figure can never contradict the sheet it sits on.
                "supply_subtotal":  0.0,
                "install_subtotal": 0.0,
                "subtotal":         0.0,

                "payment_terms":   (form.get("payment_terms") or "").strip(),
                "delivery_terms":  (form.get("delivery_terms") or "").strip(),
                "notes":           (form.get("notes") or "").strip(),
                "company_branch":  (form.get("company_branch") or "").strip(),
                "auth_signatory":  (form.get("auth_signatory") or "").strip(),
            }
            sup, ins, tot = boq_totals(boq)
            boq["supply_subtotal"]  = sup
            boq["install_subtotal"] = ins
            boq["subtotal"]         = tot

            STORE["boqs"][bid] = boq
            return redirect(url_for("boq.view_boq", id=bid,
                                    msg=f"BOQ {boq['ref']} created.", type="success"))

        # Rejected: re-render with what the user actually typed, exactly as the
        # quotation form does. The editor boots from the posted JSON, so no
        # work is lost — including which rows were open.
        sections = raw_sections if isinstance(raw_sections, list) else []
        lines    = raw_lines if isinstance(raw_lines, list) else []

        # …and force the offending row open. Every line is collapsed by
        # default, so a complaint about line 47 that leaves line 47 shut is
        # worse than no validation at all.
        if 0 <= err_idx < len(lines) and isinstance(lines[err_idx], dict):
            lines[err_idx]["_open"] = True
            bad_section = lines[err_idx].get("section")
            for sec in sections:
                if isinstance(sec, dict) and sec.get("code") == bad_section:
                    sec["_open"] = True

    # Filled by ?demo=1 below. Bound here so `_v` closes over something real
    # whichever branch runs.
    prefill: dict = {}

    def _v(key: str, default: str = "") -> str:
        """
        A form field's value: the user's own input first, then the demo
        prefill, then the module default. Same precedence idea as
        `proforma._v()` — what the user typed always wins.
        """
        if request.method == "POST":
            return P.esc(request.form.get(key, ""))
        if key in prefill:
            return P.esc(prefill[key])
        return P.esc(default)

    def _sel(name, options, default):
        """A dropdown that survives a rejected POST and a demo prefill alike."""
        cur = None
        if request.method == "POST":
            cur = request.form.get(name)
        elif name in prefill and prefill[name]:
            cur = prefill[name]
        return _sel_keep(name, options, default, cur)

    alert_html = ""
    if error:
        alert_html = f'<div class="alert alert-error">&#10007; {error}</div>'


    # A fresh form opens with the shape of a real BOQ already in place — one
    # section and one line — because an empty editor gives no clue what a
    # section or an area even is here.
    boot = {"sections": sections, "lines": lines}
    if not sections and not lines:
        boot = {"sections": [{"code": "A", "title": "", "areas": []}], "lines": []}

    # ?demo=1 loads the whole seeded Sify schedule into the editor — 3 sections,
    # 97 lines, every rate and area quantity. Nobody can hand-build a BOQ of
    # that size to try the form out, and a form that cannot be exercised cannot
    # be reviewed. It fills the EDITOR, not the database: the user still has to
    # press Create, and can change anything first.
    prefill = {}
    if request.method == "GET" and request.args.get("demo"):
        boot, prefill = _demo_form_payload()

    # Loading the demo has to be visibly a *demo*, and it has to say that
    # nothing is saved yet — otherwise the obvious reading of a form that just
    # filled itself with 97 lines is that a BOQ now exists.
    demo_banner = ""
    if request.method == "GET" and request.args.get("demo"):
        n_lines = len(boot.get("lines", []))
        n_secs  = len(boot.get("sections", []))
        demo_banner = (
            '<div class="demo-banner">'
            f'&#128203; Loaded the <b>Sify Bangalore</b> demo schedule &mdash; '
            f'{n_secs} sections, {n_lines} lines, with the rates and area '
            'quantities from the client&rsquo;s own workbook. '
            '<b>Nothing has been saved.</b> Edit anything you like, then press '
            'Create BOQ &mdash; or just leave the page.'
            '</div>')

    js = (_BOQ_JS
          .replace("BOQ_BOOT", _json_for_script(boot))
          .replace("BOQ_SPECS", _spec_catalog_json())
          .replace("BOQ_ADDR", _json_for_script(picker_payload())))

    today = _date.today().isoformat()

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Create BOQ")}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{BOQ_STYLES}
</head>
<body>
{_nav()}
<main>
  {alert_html}
  <div class="page-top">
    <h1>Create <span>BOQ</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">&#8592; All BOQs</a>
      <a href="{url_for('boq.create_boq', demo=1)}" class="btn btn-ghost">
        &#128203;&nbsp;Use demo data
      </a>
    </div>
  </div>
  {demo_banner}

  <form method="POST" onsubmit="return saveJSON()">
    <input type="hidden" id="boq_json" name="boq_json"/>

    <div class="form-section">
      <div class="section-title">&#128203; BOQ Details</div>
      <div class="fg4">
        <div class="form-group">
          <label for="date">Date</label>
          <input type="date" id="date" name="date" value="{_v('date', today)}" required/>
        </div>
        <div class="form-group">
          <label for="rev_no">Revision No.</label>
          <input type="text" id="rev_no" name="rev_no" value="{_v('rev_no', '0')}" placeholder="0"/>
        </div>
        <div class="form-group span2">
          <label for="project_name">Project Name</label>
          <input type="text" id="project_name" name="project_name"
                 value="{_v('project_name')}" placeholder="Sify Bangalore" required/>
        </div>
        <div class="form-group span2">
          <label for="site_location">Site Location</label>
          <input type="text" id="site_location" name="site_location"
                 value="{_v('site_location')}" placeholder="Bangalore, Karnataka"/>
        </div>
        <div class="form-group span2">
          <label for="rate_basis_label">Rate Basis Label</label>
          <input type="text" id="rate_basis_label" name="rate_basis_label"
                 value="{_v('rate_basis_label', DEFAULT_RATE_BASIS)}" placeholder="Mohali Rates"/>
        </div>
      </div>
      <p style="margin-top:.7rem;font-size:.78rem;color:var(--muted);">
        The rate basis is what the base-rate column is headed on the printed sheet.
        These schedules are commonly priced off a rate contract agreed on another
        project and then escalated.
      </p>
    </div>

    <div class="form-section">
      <div class="section-title">&#127970; Customer</div>
      <div class="addr-pick">
        <select id="bill_pick" onchange="applyAddr('bill', this)">{picker_options("— fill from address book —")}</select>
        <a href="{url_for('address.list_addresses')}" target="_blank" rel="noopener" class="addr-pick-link">
          &#128214; manage address book
        </a>
      </div>
      <div class="fg2">
        <div class="form-group">
          <label for="account_name">Account Name</label>
          <input type="text" id="account_name" name="account_name"
                 value="{_v('account_name')}" placeholder="Prudent Teqtis Pvt Ltd" required/>
        </div>
        <div class="form-group">
          <label for="contact_person">Contact Person</label>
          <input type="text" id="contact_person" name="contact_person"
                 value="{_v('contact_person')}" placeholder="Mr. Name, Designation"/>
        </div>
        <div class="form-group span-all">
          <label for="bill_addr">Address</label>
          <textarea id="bill_addr" name="bill_addr"
                    placeholder="Plot/Door No., Street, Area">{_v('bill_addr')}</textarea>
        </div>
      </div>
      <div class="fg4" style="margin-top:.7rem;">
        <div class="form-group">
          <label for="bill_state">State</label>
          {_sel("bill_state", list(INDIAN_STATES), "Maharashtra")}
        </div>
        <div class="form-group">
          <label for="bill_city">City</label>
          <input type="text" id="bill_city" name="bill_city" value="{_v('bill_city')}" placeholder="Mumbai"/>
        </div>
        <div class="form-group">
          <label for="bill_pin">Pincode</label>
          <input type="text" id="bill_pin" name="bill_pin" value="{_v('bill_pin')}" placeholder="400001"/>
        </div>
        <div class="form-group">
          <label for="bill_gstin">GSTIN</label>
          <input type="text" id="bill_gstin" name="bill_gstin" value="{_v('bill_gstin')}"
                 placeholder="27AABCX1234A1ZX"
                 style="font-family:'SFMono-Regular',Consolas,monospace;letter-spacing:.04em;"/>
        </div>
      </div>
      <div class="check-row" style="margin-top:.8rem;">
        <input type="checkbox" name="ship_same" value="1" id="ship_same_chk"
               onchange="toggleShipSame(this.checked)"/>
        <label for="ship_same_chk">Site address same as billing</label>
      </div>
      <div id="ship-fields">
        <div class="addr-pick" style="margin-top:.7rem;">
          <select id="ship_pick" onchange="applyAddr('ship', this)">{picker_options("— fill site address from book —")}</select>
        </div>
        <div class="fg4">
          <div class="form-group span2">
            <label for="ship_acct_name">Site / Consignee</label>
            <input type="text" id="ship_acct_name" name="ship_acct_name" value="{_v('ship_acct_name')}"/>
          </div>
          <div class="form-group span2">
            <label for="ship_addr">Site Address</label>
            <input type="text" id="ship_addr" name="ship_addr" value="{_v('ship_addr')}"/>
          </div>
          <div class="form-group">
            <label for="ship_state">State</label>
            {_sel("ship_state", list(INDIAN_STATES), "Maharashtra")}
          </div>
          <div class="form-group">
            <label for="ship_city">City</label>
            <input type="text" id="ship_city" name="ship_city" value="{_v('ship_city')}"/>
          </div>
          <div class="form-group">
            <label for="ship_pin">Pincode</label>
            <input type="text" id="ship_pin" name="ship_pin" value="{_v('ship_pin')}"/>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">&#128209; Sections &amp; Areas</div>
      <p style="margin-bottom:1rem;font-size:.82rem;color:var(--muted);">
        A section is a system (A &mdash; sprinklers, B &mdash; hydrants, C &mdash; pumps).
        <b>Areas belong to the section, not to the BOQ</b> &mdash; one section may break its
        quantities down by floor while another does not break them down at all.
        Leave the area list blank for a section that carries only a total quantity.
      </p>
      <div class="sec-editor" id="sec-editor"></div>
      <button type="button" class="btn-row" style="margin-top:.8rem;" onclick="addSec()">
        + Add section
      </button>
    </div>

    <div class="form-section">
      <div class="section-title">&#128221; Line Items</div>
      <p style="margin-bottom:1rem;font-size:.82rem;color:var(--muted);">
        Tick <b>Specification header</b> for a row that carries the specification
        paragraph and no quantity; put its item number in <b>Under Item</b> on the
        rows beneath it. A base rate of <b>-</b> means the rate was agreed directly
        rather than escalated.
      </p>
      <div class="bulk-bar">
        <div class="form-group" style="flex:2 1 320px;">
          <label for="bulk-spec">Insert a spec as a whole family</label>
          <select id="bulk-spec"></select>
        </div>
        <div class="form-group" style="flex:0 0 90px;">
          <label for="bulk-section">Into</label>
          <select id="bulk-section"></select>
        </div>
        <button type="button" class="btn-row" onclick="insertFamily()">
          + Insert header &amp; variants
        </button>
      </div>
      <p style="margin:.5rem 0 1.1rem;font-size:.78rem;color:var(--muted);">
        A sized spec inserts one <b>header row</b> carrying the clause plus one child
        row per size, numbered <b>24</b>, <b>24.a</b>, <b>24.b</b>&hellip; &mdash; the
        shape a BOQ is actually written in. An unsized spec inserts a single line.
      </p>

      <div class="jump-bar" id="jump-bar"></div>
      <div id="dup-warn"></div>
      <div id="zeroqty-hint"></div>
      <div id="line-editor"></div>
      <button type="button" class="btn-row" style="margin-top:.4rem;" onclick="addLine()">
        + Add line
      </button>
    </div>

    <div class="form-section">
      <div class="section-title">&#128196; Terms</div>
      <div class="fg2">
        <div class="form-group">
          <label for="payment_terms">Payment Terms</label>
          {_sel("payment_terms", _PAY_TERMS, _PAY_TERMS[0])}
        </div>
        <div class="form-group">
          <label for="delivery_terms">Terms of Delivery</label>
          {_sel("delivery_terms", _DEL_TERMS, "FOR Site")}
        </div>
        <div class="form-group span-all">
          <label for="notes">Notes</label>
          <textarea id="notes" name="notes"
                    placeholder="Anything that belongs on the schedule itself">{_v('notes')}</textarea>
        </div>
        <div class="form-group">
          <label for="company_branch">Company Branch</label>
          <input type="text" id="company_branch" name="company_branch" value="{_v('company_branch')}"/>
        </div>
        <div class="form-group">
          <label for="auth_signatory">Authorised Signatory</label>
          <input type="text" id="auth_signatory" name="auth_signatory" value="{_v('auth_signatory')}"
                 placeholder="{B.COMPANY_SIGNATORY}"/>
        </div>
      </div>
    </div>

    <div style="display:flex;gap:.8rem;justify-content:flex-end;margin-bottom:2rem;">
      <a href="{url_for('boq.list_boqs')}" class="btn btn-ghost">Cancel</a>
      <button type="submit" class="btn">Create BOQ</button>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE}</p></footer>
</main>
{js}
</body></html>"""
    return _page(template)
