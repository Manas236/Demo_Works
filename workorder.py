"""
workorder.py — Work Orders for petty contractors (5 October 2026)
=================================================================
CLIENT_CHANGES.md §0, **forty-first** block — the 5 October 2026 call with
Samruddhi, and Manas's rulings A to J. A **work order** (WO) assigns WORK to a
petty contractor (a subcontractor). It is a document type **distinct from a
purchase order**: a PO buys MATERIAL from a supplier; a WO assigns work, and
each of its lines carries a **material rate AND a labour rate**.

What this module owns, and what it deliberately does not
--------------------------------------------------------
* **Its own collection, `work_orders`** (ruling A). Not inside `purchases`, not
  inside `purchase_orders`, and never embedded in anything — CLIENT_CHANGES.md
  §1.3. This module may not import `boq.py`, `ra.py`, `invoice.py`,
  `purchase.py` or `po_draft.py`; `tests/test_import_directions.py` holds it.
* **The printed sheet is `docsheet.py`'s** (ruling B) — the letterhead, page
  frame, party block, table shell, amount in words and signature panel the
  buy-side purchase order prints on, with the PO's own two flags: no web
  address on the letterhead and the "computer generated" signature note. No
  bank block, because the PO prints none. The differences from the PO are only
  the ones a WO needs: the title, the contractor in the vendor's place, and
  the eight columns below. ⚠ **No GST block, and no tax field anywhere** —
  whether a WO carries GST is an open question to the client (ABOUT.md §7).
* **Every amount is DERIVED, never stored** (ruling C). A line stores
  `qty`, `material_rate` and `labour_rate`; `line_amounts()` and `totals_of()`
  compute the rest at render. A record can therefore never print a total that
  contradicts its own lines.
* **DRAFT / ISSUED / CANCELLED, the RA bill's semantics** (ruling E). Edit and
  line add/delete only while DRAFT; an issued WO is cancelled and reissued,
  never edited; cancelling needs a reason and cannot be undone; a cancelled WO
  prints with the RA bill's CANCELLED overprint (`docsheet.LIFECYCLE_CSS`, the
  RA sheet's rules moved into the leaf); only a DRAFT may be deleted.
* **One global number series** at `/settings` (ruling F) — its own settings
  record, never reset, never released by a delete.
* **The contractor** is an address-book pick (type `contractor`) with a typed
  fallback, exactly as the draft PO's vendor (ruling G). **The project link**
  is optional, `project_id` with `project_name` snapshotted (ruling H).
* **The print reads the WO's own stored rows and nothing else** (ruling J):
  not the address book, not the project, not any schedule.
* **Access** (ruling I): no permission is minted. Every route carries the
  buy-side PURCHASE ORDER's own permission for the same action — see
  `auth.ROUTE_PERMISSIONS`.
* **Excel import** (ruling D) reuses `sheetimport.py` — the leaf the BOQ
  importer reads through — with this document's OWN column mapping: the two
  rate tracks are Material and Labour. A sheet with one rate column fills that
  track and leaves the other BLANK and flagged; nothing is ever guessed.
"""

import datetime
import io
import math
import re
import time
import uuid
from datetime import date as _date

from flask import Blueprint, redirect, request, url_for

import branding as B
import docsheet as DS
import importstage as IS   # the staging mechanism the BOQ importer uses (5 Oct 2026)
import pipeline as P
import settings as SET
import sheetimport as SI
from address import has_options, picker_options, format_address_lines
from chrome import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES, _fmt_qty, _inr
from store import STORE

workorder_bp = Blueprint("workorder", __name__, url_prefix="/wo")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

# The lifecycle. RA bills' three states and their meaning (ruling E).
STATUSES = ("draft", "issued", "cancelled")

# The most lines one work order may carry — the BOQ's `MAX_LINES`, restated
# rather than imported because this module may not import `boq.py`. An
# imported sheet with more is refused WHOLE, with the count named: a work
# order cut at line 600 is a work order missing its last lines.
MAX_LINES = 600

# Free text, cut where it is stored. The description cap is the reader's own
# per-cell cap, so an imported clause is never cut a second time here.
MAX_DESC_CHARS = SI.MAX_CELL_CHARS
MAX_SHORT_CHARS = 40          # item number and unit
MAX_NOTES_CHARS = 2000
MAX_REASON_CHARS = 500
MAX_SITE_CHARS = 200          # R6, 5 October 2026
MAX_TERMS_CHARS = 4000        # R7

# A figure above this is a typo, not a quantity or a rate.
MAX_FIGURE = 1_000_000_000.0

# A blank form opens with this many empty rows; an untouched row is skipped.
DEFAULT_ROWS = 3

# `line_id` — the BOQ's rule (ruling C): 12 hex characters off `uuid4`,
# minted by the server, never typed and never printed.
_LINE_ID = re.compile(r"\A[0-9a-f]{12}\Z")

# The staged Excel upload — persisted, owned, short-lived: the BOQ importer's
# own mechanism and limits (`importstage.py`; see STAGING below).
STAGE_COLLECTION = "wo_imports"
STAGE_TTL_SECONDS = IS.STAGE_TTL_SECONDS
MAX_STAGED_PER_USER = IS.MAX_STAGED_PER_USER
FORM_OVERHEAD_BYTES = 64 * 1024
PREVIEW_ROWS = 15
PREVIEW_CELL_CHARS = 80


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _uid() -> str:
    import auth
    return (auth.current_user() or {}).get("id", "")


def _can(endpoint: str) -> bool:
    """`auth.can_reach()` — through a function-body import, `boq.py`'s hatch."""
    import auth
    return auth.can_reach(endpoint)


def _wos() -> dict:
    return STORE.setdefault("work_orders", {})


def new_line_id() -> str:
    """A fresh `line_id` — `uuid4().hex[:12]`, the BOQ's shape."""
    return uuid.uuid4().hex[:12]


# =============================================================================
# THE LIFECYCLE — the one place a work order's state is read
# =============================================================================

def status_of(wo) -> str:
    """
    This work order's state, normalised to one of `STATUSES`.

    **Anything unrecognised reads as `issued`** — `ra.status_of()`'s safe
    default. A record whose status cannot be read must not silently reopen to
    editing and deletion; reading it as issued locks it, and it can still be
    cancelled.
    """
    s = str((wo or {}).get("status") or "").strip().lower()
    return s if s in STATUSES else "issued"


def is_draft(wo) -> bool:
    return status_of(wo) == "draft"


def can_edit(wo) -> tuple:
    """(allowed, reason) — edit and line add/delete are for a DRAFT only."""
    if not wo:
        return False, "That work order no longer exists."
    st = status_of(wo)
    if st == "issued":
        return False, (f"{wo.get('ref')} has been issued and cannot be edited. "
                       f"Cancel it and raise a new work order instead.")
    if st == "cancelled":
        return False, f"{wo.get('ref')} is cancelled and cannot be edited."
    return True, ""


def can_issue(wo) -> tuple:
    """(allowed, reason) — only a draft is issued."""
    if not wo:
        return False, "That work order no longer exists."
    st = status_of(wo)
    if st == "issued":
        return False, f"{wo.get('ref')} has already been issued."
    if st == "cancelled":
        return False, f"{wo.get('ref')} is cancelled and cannot be issued."
    return True, ""


def can_cancel(wo) -> tuple:
    """(allowed, reason) — a draft or an issued WO; never a second time."""
    if not wo:
        return False, "That work order no longer exists."
    if status_of(wo) == "cancelled":
        return False, (f"{wo.get('ref')} is already cancelled. A cancellation "
                       f"cannot be undone or repeated.")
    return True, ""


def can_delete(wo) -> tuple:
    """(allowed, reason) — only a DRAFT may be deleted; the rest are cancelled."""
    if not wo:
        return False, "That work order no longer exists."
    st = status_of(wo)
    if st != "draft":
        return False, (f"{wo.get('ref')} is {st} and cannot be deleted. "
                       + ("Cancel it instead — the record stays and its number "
                          "stays spent." if st == "issued" else
                          "A cancelled work order is kept as the record of what "
                          "was withdrawn."))
    return True, ""


def apply_issue(wo: dict, on: str = "") -> dict:
    """Writes `status` and `issued_on` and nothing else — no figure moves."""
    wo["status"] = "issued"
    wo["issued_on"] = str(on or "").strip()[:32] or _date.today().isoformat()
    wo["updated_at"] = _now()
    return wo


def apply_cancel(wo: dict, reason: str, on: str = "") -> dict:
    """Writes `status`, `cancelled_on` and `cancel_reason`; every line stays."""
    wo["status"] = "cancelled"
    wo["cancelled_on"] = str(on or "").strip()[:32] or _date.today().isoformat()
    wo["cancel_reason"] = str(reason or "").strip()[:MAX_REASON_CHARS]
    wo["updated_at"] = _now()
    return wo


# =============================================================================
# THE ARITHMETIC — derived, never stored (ruling C)
# =============================================================================

def _f(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def is_header(line) -> bool:
    """
    A HEADING line — the BOQ's `is_header` (5 October 2026, CLIENT_CHANGES.md
    §0 forty-second block, fix 2): an item number and a description, and no
    unit, quantity or rate. ⚠ `.get()`, always: a line written before the
    field has no key and is a priced line.
    """
    return bool((line or {}).get("is_header"))


def is_section(line) -> bool:
    """
    A SECTION heading (5 October 2026, CLIENT_CHANGES.md §0 forty-third block,
    R4): a heading line that starts a group running to the next section
    heading, closed on the print by a subtotal. `.get()` — absent is False.
    """
    return is_header(line) and bool((line or {}).get("section"))


# ── The rate tracks — a property of the WORK ORDER (R1, 5 October 2026) ──────
#
# `tracks` declares which rates this work order carries. ⚠ **It supersedes the
# per-line half of ruling D**: a work order that declares one track never asks
# for the other, and stores it ABSENT on every line — never 0. The operator
# declares it, which is why it is not a guess. ABSENT on a stored work order
# means "both", so every work order written before the field reads exactly as
# it did; an unrecognised value reads "both" too, which hides nothing.
TRACKS = ("both", "labour", "material")
TRACK_LABEL = {"both": "Material + Labour", "labour": "Labour only",
               "material": "Material only"}
TRACK_RATES = {"both": ("material_rate", "labour_rate"),
               "labour": ("labour_rate",), "material": ("material_rate",)}


def tracks_of(wo) -> str:
    t = str((wo or {}).get("tracks") or "").strip().lower()
    return t if t in TRACKS else "both"


def gst_rate_of(wo) -> float:
    """
    The work order's GST rate in % (R5). ⚠ **ABSENT means NO GST** — every work
    order written before the field, and the existing print golden, print with
    no GST row. New work orders prefill 18 on the form.
    """
    return max(0.0, min(100.0, _f((wo or {}).get("gst_rate"))))


def line_amounts(line: dict) -> tuple:
    """
    `(material_amount, labour_amount, line_total)` for one stored line.

    Each amount is `qty × rate` rounded to the paisa ONCE, and the line total is
    the sum of the two rounded amounts — so the printed columns add up to what
    is printed beside them, to the paisa. A heading line has none: (0, 0, 0).
    A track a one-track work order does not carry is ABSENT on the line and
    contributes 0.
    """
    if is_header(line):
        return 0.0, 0.0, 0.0
    qty = _f(line.get("qty"))
    mat = round(qty * _f(line.get("material_rate")), 2)
    lab = round(qty * _f(line.get("labour_rate")), 2)
    return mat, lab, round(mat + lab, 2)


def _sum_lines(lines) -> tuple:
    mat = lab = 0.0
    for line in lines:
        if is_header(line):
            continue
        m, l, _t = line_amounts(line)
        mat += m
        lab += l
    return round(mat, 2), round(lab, 2)


def totals_of(wo: dict) -> dict:
    """
    The work order's figures, every one derived and none stored:

        material, labour   the sums of the derived line amounts
        grand              material + labour — the PRE-TAX total
        gst_rate, gst      the rate (R5) and round(grand x rate / 100, 2),
                           the purchase order's rounding; 0 when no GST
        total              grand + gst — what the work order is for

    Heading lines are excluded — they carry no figure to sum.
    """
    mat, lab = _sum_lines((wo or {}).get("lines") or [])
    grand = round(mat + lab, 2)
    rate = gst_rate_of(wo)
    gst = round(grand * rate / 100.0, 2) if rate > 0 else 0.0
    return {"material": mat, "labour": lab, "grand": grand,
            "gst_rate": rate, "gst": gst, "total": round(grand + gst, 2)}


def section_groups(wo: dict) -> list:
    """
    `[{"title", "item_no", "lines", "material", "labour", "grand"}]` — the
    work order cut at its SECTION headings (R4), in order. `[]` when it has
    none, which is what keeps a work order with no section printing exactly as
    before. Priced lines above the first section heading, if any, are a group
    of their own with `title` None.
    """
    lines = (wo or {}).get("lines") or []
    if not any(is_section(l) for l in lines):
        return []
    groups, cur = [], {"title": None, "item_no": "", "lines": []}
    for line in lines:
        if is_section(line):
            groups.append(cur)
            cur = {"title": str(line.get("description") or ""),
                   "item_no": str(line.get("item_no") or ""), "lines": []}
        else:
            cur["lines"].append(line)
    groups.append(cur)
    out = []
    for g in groups:
        priced = [l for l in g["lines"] if not is_header(l)]
        if g["title"] is None and not priced:
            continue
        mat, lab = _sum_lines(g["lines"])
        g.update(material=mat, labour=lab, grand=round(mat + lab, 2))
        out.append(g)
    return out


# =============================================================================
# NUMBERING — one global series, and a number is never released (ruling F)
# =============================================================================

def next_ref() -> str:
    """The number the next work order will take — a preview, nothing spent."""
    return _free_ref(SET.wo_series())[0]


def _free_ref(series: dict) -> tuple:
    """
    `(ref, next_no)` — the series' current number, moved forward past any
    number already on a work order.

    ⚠ **Stricter than the draft PO's counter, deliberately.** `/settings` lets
    the next number be typed, and a number typed below one already issued
    would otherwise mint a second document bearing it. Skipping forward never
    reissues a number; it only ever spends more of them.
    """
    used = {str(w.get("ref") or "") for w in _wos().values()}
    raw = str(series.get("next_no") or "1").strip()
    n = int(raw) if raw.isdigit() and int(raw) >= 1 else 1
    while True:
        ref = SET.wo_ref_of({"prefix": series.get("prefix"), "next_no": n})
        if ref not in used:
            return ref, n
        n += 1


def _spend_ref() -> str:
    """Take the next number and advance the counter. Call once, at save."""
    series = SET.wo_series()
    ref, n = _free_ref(series)
    SET.save_wo_series(series["prefix"], n + 1)
    return ref


# =============================================================================
# THE CONTRACTOR — a picker over the address book, with a typed fallback
# =============================================================================

CONTRACTOR_TYPES = ("contractor",)


def contractor_from(form) -> tuple:
    """
    `(fields, error)` for whichever way the contractor was given — the draft
    PO's `vendor_from()` exactly, over the `contractor` address type (ruling G).

    **The picker is the primary path**: it carries the address and the GSTIN
    and cannot be spelled two ways on two documents. **The typed box is the
    fallback**, for a one-off contractor nobody has filed. Whichever was used
    is **snapshotted onto the record** — the print never reads the book.

    ⚠ **Both paths snapshot the same five fields** — `contractor_name`,
    `contractor_source`, `to`, `contractor_gstin` and, from 5 October 2026
    (CLIENT_CHANGES.md §0 forty-second block, fix 3), `contractor_phone`: a
    picked address gives its own phone, a typed contractor the one typed. The
    phone is a field of its own rather than a line in `to`, because a picked
    address's `to` (`address.format_address_lines()`) carries no phone either,
    and the two paths must snapshot alike.
    """
    cid = (form.get("contractor_id") or "").strip()[:64]
    typed = (form.get("contractor_name") or "").strip()[:200]

    if cid:
        addr = (STORE.get("addresses") or {}).get(cid)
        if not addr:
            return {}, "That contractor is no longer in the address book."
        if addr.get("type") not in CONTRACTOR_TYPES:
            from address import ADDRESS_TYPES
            kind = ADDRESS_TYPES.get(addr.get("type"), addr.get("type") or "another type")
            return {}, (f"That address is filed as {kind}, not as a Contractor, so "
                        f"it cannot be the contractor on a work order. Type the "
                        f"contractor's name, address, GSTIN and phone in the "
                        f"one-off boxes below instead — no address-book entry is "
                        f"needed — or add the address to the address book as type "
                        f"Contractor and pick it here.")
        return {
            "contractor_id": cid,
            "contractor_name": (addr.get("company") or addr.get("contact_name")
                                or addr.get("label") or ""),
            "contractor_source": "book",
            "to": "\n".join(format_address_lines(addr)),
            "contractor_gstin": (addr.get("gstin") or "").strip(),
            "contractor_phone": (addr.get("phone") or "").strip(),
        }, ""

    if typed:
        return {
            "contractor_id": "",
            "contractor_name": typed,
            "contractor_source": "typed",
            "to": "\n".join(x for x in [typed,
                                        (form.get("contractor_addr") or "").strip()[:500]]
                            if x),
            "contractor_gstin": (form.get("contractor_gstin") or "").strip()[:15].upper(),
            "contractor_phone": (form.get("contractor_phone") or "").strip()[:40],
        }, ""

    return {}, ("Choose a contractor from the address book, or type a one-off "
                "contractor's name.")


# =============================================================================
# THE PROJECT — optional, snapshotted (ruling H; the charges module's shape)
# =============================================================================

def project_from(form) -> tuple:
    """`(project_id, project_name, error)`. Blank is valid: a WO need not be for a project."""
    pid = (form.get("project_id") or "").strip()[:64]
    if not pid:
        return "", "", ""
    proj = (STORE.get("projects") or {}).get(pid)
    if not proj:
        return "", "", "That project no longer exists. Choose another, or none."
    return pid, str(proj.get("name") or ""), ""


def _project_options(selected: str) -> str:
    rows = sorted((STORE.get("projects") or {}).items(),
                  key=lambda kv: str(kv[1].get("name") or "").lower())
    out = '<option value="">&mdash; not for a project &mdash;</option>'
    for pid, proj in rows:
        sel = " selected" if pid == selected else ""
        out += (f'<option value="{P.esc(pid)}"{sel}>'
                f'{P.esc(proj.get("name")) or P.esc(pid[:8])}</option>')
    return out


# =============================================================================
# THE LINES — parsed from the form, validated, ids minted by the server
# =============================================================================

# The posted parallel lists, and the field each one is.
_FIELDS = (("ln_item", "item_no"), ("ln_desc", "description"),
           ("ln_unit", "unit"), ("ln_qty", "qty"),
           ("ln_mrate", "material_rate"), ("ln_lrate", "labour_rate"))

FIELD_WORDS = {"item_no": "item number", "description": "description",
               "unit": "unit", "qty": "quantity",
               "material_rate": "material rate", "labour_rate": "labour rate"}


def _figure(raw):
    """`(value, problem)` for a typed number — never guessed, never defaulted."""
    s = str(raw if raw is not None else "").strip().replace(",", "")
    if not s:
        return None, "blank"
    try:
        v = float(s)
    except ValueError:
        return None, "bad"
    if not math.isfinite(v):
        return None, "bad"
    if v < 0:
        return None, "negative"
    if v > MAX_FIGURE:
        return None, "large"
    return v, ""


def posted_rows(form) -> list:
    """
    The line rows exactly as posted — strings, for re-rendering. Blank rows
    (every box empty) are dropped: the form opens with spare ones.
    """
    cols = {f: form.getlist(name) for name, f in _FIELDS}
    ids = form.getlist("ln_id")
    notes = form.getlist("ln_note")
    hdrs = form.getlist("ln_hdr")
    secs = form.getlist("ln_sec")
    n = max([len(v) for v in cols.values()] + [len(ids)] or [0])
    rows = []
    for i in range(n):
        r = {f: str((cols[f][i] if i < len(cols[f]) else "") or "") for f in cols}
        if not any(r[f].strip() for f in cols):
            continue
        r["line_id"] = str((ids[i] if i < len(ids) else "") or "")[:64]
        r["note"] = str((notes[i] if i < len(notes) else "") or "")[:2000]
        r["is_header"] = str((hdrs[i] if i < len(hdrs) else "") or "") == "1"
        # R4 — the "Section (subtotal)" tick, meaningful on a heading only.
        r["section"] = (r["is_header"]
                        and str((secs[i] if i < len(secs) else "") or "") == "1")
        rows.append(r)
    return rows


def _lines_word(nums: list) -> str:
    shown = ", ".join(str(n) for n in nums[:12]) + (" …" if len(nums) > 12 else "")
    return (f"{len(nums)} line{'' if len(nums) == 1 else 's'} "
            f"(line{'' if len(nums) == 1 else 's'} {shown})")


def lines_from_rows(rows: list, keep_ids=frozenset(), tracks: str = "both") -> tuple:
    """
    `(lines, problems)` — the stored line dicts, or what is wrong with them.

    `problems` is `[{"row": index into rows, "field", "message"}]`, and a non-
    empty list means **nothing is saved**. Rules, each one a test:

    * a description is required;
    * a HEADING line (`is_header`) carries an item number and a description
      and nothing else: whatever was posted in its figure boxes is dropped,
      and it is exempt from every figure rule below (fix 2, 5 October 2026);
    * the quantity and BOTH rates must be typed figures, 0 or more — a blank
      rate is refused, never read as 0, because "no labour on this line" and
      "nobody typed the labour rate yet" are different facts and only a typed
      0 says the first;
    * `line_id` is the server's: kept only when it is well-formed, belongs to
      the record being edited (`keep_ids`) and is not posted twice; otherwise
      a fresh one is minted. A create keeps none.
    * ⚠ **`tracks` (R1, 5 October 2026).** Only the DECLARED tracks' rates are
      required; the other track is stored ABSENT on every line, never 0. A
      figure typed in the other track is REFUSED, naming the lines — it is
      never silently dropped.
    """
    declared = TRACK_RATES.get(tracks, TRACK_RATES["both"])
    lines, problems, used = [], [], set()
    for i, r in enumerate(rows):
        desc = r.get("description", "").strip()
        if not desc:
            problems.append({"row": i, "field": "description",
                             "message": "needs a description"})
        header = bool(r.get("is_header"))
        figs = {"qty": None}
        figs.update({f: None for f in declared})
        for f in (() if header else ("qty",) + declared):
            v, why = _figure(r.get(f))
            if why == "blank":
                msg = (f"needs a {FIELD_WORDS[f]}" if f == "qty" else
                       f"needs a {FIELD_WORDS[f]} — type 0 if there is none")
            elif why == "bad":
                msg = f"{FIELD_WORDS[f]} is not a number"
            elif why == "negative":
                msg = f"{FIELD_WORDS[f]} cannot be negative"
            elif why == "large":
                msg = f"{FIELD_WORDS[f]} is too large to be right"
            else:
                msg = ""
            if msg:
                problems.append({"row": i, "field": f, "message": msg})
            figs[f] = v
        lid = str(r.get("line_id") or "").strip()
        if not (_LINE_ID.match(lid) and lid in keep_ids and lid not in used):
            lid = new_line_id()
            while lid in used:
                lid = new_line_id()
        used.add(lid)
        line = {
            "line_id": lid,
            "is_header": header,
            "item_no": r.get("item_no", "").strip()[:MAX_SHORT_CHARS],
            "description": desc[:MAX_DESC_CHARS],
            "unit": "" if header else r.get("unit", "").strip()[:MAX_SHORT_CHARS],
            "qty": figs["qty"],
        }
        for f in ("material_rate", "labour_rate"):
            if f in declared:
                line[f] = figs[f]
        if header and r.get("section"):
            line["section"] = True
        lines.append(line)
    problems += stray_problems(rows, tracks)
    if not any(not r.get("is_header") for r in rows):
        problems.append({"row": None, "field": "",
                         "message": ("Add at least one priced line to the work "
                                     "order — a heading alone orders nothing."
                                     if rows else
                                     "Add at least one line to the work order.")})
    if len(rows) > MAX_LINES:
        problems.append({"row": None, "field": "",
                         "message": (f"{len(rows)} lines is more than one work "
                                     f"order carries ({MAX_LINES}). Split it.")})
    return lines, problems


def stray_problems(rows: list, tracks: str) -> list:
    """
    R1's refusal: a figure typed in a track this work order does NOT carry.
    One sentence per track naming the lines, plus the field on each line, so
    it is ringed. Never silently dropped — the operator clears it, or chooses
    Material + Labour.
    """
    declared = TRACK_RATES.get(tracks, TRACK_RATES["both"])
    out = []
    for f in ("material_rate", "labour_rate"):
        if f in declared:
            continue
        idx = [i for i, r in enumerate(rows)
               if not r.get("is_header") and str(r.get(f) or "").strip()]
        if not idx:
            continue
        kind = "Material" if f == "material_rate" else "Labour"
        out.append({"row": None, "field": "",
                    "message": (f"{kind} rates are typed on "
                                f"{_lines_word([k + 1 for k in idx])} but this "
                                f"work order is {TRACK_LABEL[tracks]}: clear "
                                f"them, or choose Material + Labour.")})
        for k in idx:
            out.append({"row": k, "field": f,
                        "message": (f"this work order is {TRACK_LABEL[tracks]} "
                                    f"— clear this {FIELD_WORDS[f]}")})
    return out


def rows_of(wo: dict) -> list:
    """A stored WO's lines as form rows (strings), for the edit form."""
    out = []
    for line in wo.get("lines") or []:
        out.append({
            "line_id": line.get("line_id", ""),
            "is_header": is_header(line),
            "section": is_section(line),
            "item_no": line.get("item_no", ""),
            "description": line.get("description", ""),
            "unit": line.get("unit", ""),
            "qty": num_text(line.get("qty")),
            "material_rate": num_text(line.get("material_rate")),
            "labour_rate": num_text(line.get("labour_rate")),
            "note": "",
        })
    return out


def num_text(v) -> str:
    """
    A number as the text the form holds, EXACTLY — the shortest text that
    reads back as the same float, never rounded (`boqimport.num_text()`'s
    rule, restated: this module may not import that one, which imports
    `boq.py`).
    """
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(f):
        return ""
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


# =============================================================================
# STYLES
# =============================================================================
#
# Plain strings, never f-strings, so their CSS braces are written once. Every
# rule uses the variables the shared sheets already define and introduces no
# new font, type size or border weight — the restraint PURCHASE_STYLES and
# RA_DOC_STYLES hold to.

WO_DOC_STYLES = "\n<style>\n" + """\
  .quotation-doc.wo-doc { position:relative; }
  .quotation-doc .doc-sub-wo {
    text-align:center; font-size:var(--fs-sm); color:var(--doc-soft);
    padding-bottom:2mm;
  }
  /* An imported description keeps the line breaks of the clause it came from. */
  .quotation-doc.wo-doc td.c-desc { white-space:pre-line; }
  .quotation-doc.wo-doc td.c-sno { overflow-wrap:anywhere; }
  .quotation-doc .wo-note { margin-top:4mm; font-size:var(--fs-sm); }
  .quotation-doc .wo-note b { font-weight:700; }

""" + DS.LIFECYCLE_CSS + """
  /* Screen only — the lifecycle panel above the sheet. */
  .wo-panel { background:#fff; border:1px solid var(--border);
    border-radius:var(--radius); padding:.85rem 1.1rem; margin:0 0 1.2rem;
    font-size:.86rem; line-height:1.55; }
  .wo-panel .wo-st { font-weight:700; text-transform:uppercase;
    letter-spacing:.05em; font-size:.76rem; }
  .wo-chip { display:inline-block; font-size:.78rem; font-weight:600;
    padding:.18rem .55rem; border-radius:6px; border:1px solid var(--border);
    color:var(--muted); text-decoration:none; margin-right:.35rem; }
  a.wo-chip:hover { border-color:var(--brand); color:var(--brand); }
  @media print { .wo-panel { display:none !important; } }
</style>
"""

WO_FORM_STYLES = "\n<style>\n" + """\
  .wo-or { text-align:center; font-size:.74rem; text-transform:uppercase;
           letter-spacing:.08em; color:var(--muted); margin:.6rem 0; }
  .wo-lines-wrap { overflow-x:auto; border:1px solid var(--border);
    border-radius:var(--radius); background:#fff; }
  table.wo-lines { width:100%; border-collapse:collapse; min-width:980px; }
  table.wo-lines th { text-align:left; font-size:.7rem; font-weight:700;
    color:var(--muted); text-transform:uppercase; letter-spacing:.05em;
    padding:.5rem .45rem; border-bottom:1px solid var(--border);
    white-space:nowrap; background:var(--surface); }
  table.wo-lines td { padding:.35rem .45rem; border-bottom:1px solid var(--border);
    vertical-align:top; font-size:.84rem; }
  table.wo-lines input, table.wo-lines textarea { width:100%; }
  table.wo-lines textarea { min-height:2.4rem; resize:vertical; }
  table.wo-lines .wo-pos { color:var(--muted); font-variant-numeric:tabular-nums; }
  table.wo-lines .c-item { width:72px; }
  table.wo-lines .c-unit { width:70px; }
  table.wo-lines .c-num { width:96px; }
  table.wo-lines .c-amt { width:104px; text-align:right;
    font-variant-numeric:tabular-nums; white-space:nowrap; padding-top:.65rem; }
  table.wo-lines td.wo-amt { text-align:right; font-variant-numeric:tabular-nums;
    white-space:nowrap; padding-top:.65rem; }
  table.wo-lines tfoot td { font-weight:700; background:var(--surface);
    border-bottom:none; }
  /* A field the save will refuse until it is answered. Red, and it stays red
     until a value the server would accept is typed — the BOQ import's guided
     fix, restated for this form. */
  .wo-need { border-color:#dc2626 !important;
    box-shadow:0 0 0 3px rgba(220,38,38,.18) !important; }
  .wo-flag { display:block; margin-top:.25rem; font-size:.74rem;
    color:#92400e; background:#fffbeb; border:1px solid #fde68a;
    border-radius:6px; padding:.15rem .45rem; }
  /* The tracks choice (R1) and a heading's section tick (R4). */
  .wo-tracks { display:flex; gap:.8rem; align-items:flex-end; flex-wrap:wrap; }
  .wo-tracks-hint { font-size:.78rem; color:var(--muted); max-width:420px; }
  .wo-sec { display:inline-flex; gap:.3rem; align-items:center; font-size:.76rem;
    color:var(--muted); margin:0 0 .25rem .6rem; font-weight:600; }
  /* A heading row on the form: the BOQ editor's spec line, restated. */
  table.wo-lines tr.wo-hd td { background:var(--surface); }
  table.wo-lines tr.wo-hd textarea { font-weight:700; }
  .wo-hd-tag { display:block; font-size:.7rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
    margin-bottom:.2rem; }
  .wo-del { background:none; border:1px solid var(--border); border-radius:6px;
    color:#b91c1c; cursor:pointer; padding:.25rem .5rem; font-size:.8rem; }
  .wo-tools { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap;
    margin:.7rem 0 0; }
  .wo-needbar { display:flex; gap:.7rem; align-items:center; flex-wrap:wrap;
    background:#fef2f2; border:1px solid #fecaca; color:#991b1b;
    border-radius:var(--radius); padding:.6rem .9rem; margin:0 0 1rem;
    font-size:.86rem; }
  .wo-needbar[hidden] { display:none; }
  .wo-banner { background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--brand); border-radius:var(--radius);
    padding:.8rem 1.1rem; margin-bottom:1.1rem; font-size:.85rem;
    line-height:1.6; }
  .wo-banner ul { margin:.3rem 0 0 1.1rem; }
  .imp-tabs { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:.7rem; }
  .imp-tab { font-size:.86rem; display:inline-flex; gap:.35rem; align-items:center; }
  .imp-grid { border-collapse:collapse; font-size:.78rem; }
  .imp-grid th, .imp-grid td { border:1px solid var(--border);
    padding:.3rem .45rem; vertical-align:top; max-width:260px; }
  .imp-grid th { background:var(--surface); }
  .imp-grid select { font-size:.76rem; max-width:180px; }
  .imp-grid .imp-rn { color:var(--muted); text-align:right; }
</style>
"""


# Plain string, interpolated as a value. It wires the line editor: add and
# delete rows (a new row is cloned from a server-rendered <template>, never
# built from strings here), the live amount preview, and the guided fix — a
# field marked `.wo-need` stays red until it holds what the save will accept,
# the bar counts what is left, "Next" jumps to it, and Save is refused in the
# browser while any remain. ⚠ The server refuses the same POST on its own;
# this script is a convenience and never the guard.
WO_FORM_JS = """
<script>
(function () {
  var body = document.getElementById('wo-lines-body');
  var tpl = document.getElementById('wo-row-tpl');
  var htpl = document.getElementById('wo-hd-tpl');
  if (!body || !tpl) return;
  var NUM = /^\\s*[0-9][0-9,]*(\\.[0-9]+)?\\s*$|^\\s*\\.[0-9]+\\s*$/;

  function num(v) {
    var s = String(v || '').replace(/,/g, '').trim();
    if (!s) return null;
    var f = Number(s);
    return isFinite(f) && f >= 0 ? f : null;
  }
  function inr(v) {
    var neg = v < 0, s = Math.abs(v).toFixed(2), ip = s.split('.')[0], fp = s.split('.')[1];
    if (ip.length > 3) {
      var head = ip.slice(0, -3), tail = ip.slice(-3), g = [];
      while (head.length > 2) { g.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) g.unshift(head);
      ip = g.concat([tail]).join(',');
    }
    return (neg ? '-' : '') + ip + '.' + fp;
  }
  function ok(el) {
    var n = el.name;
    if (n === 'ln_desc') return el.value.trim() !== '';
    if (n === 'ln_qty' || n === 'ln_mrate' || n === 'ln_lrate')
      return NUM.test(el.value) && num(el.value) !== null;
    return true;
  }
  function renumber() {
    var rows = body.querySelectorAll('tr.wo-ln');
    for (var i = 0; i < rows.length; i++) {
      var p = rows[i].querySelector('.wo-pos');
      if (p) p.textContent = String(i + 1);
    }
  }
  function recalc() {
    /* Heading rows carry no figure and are left out of every total. */
    var rows = body.querySelectorAll('tr.wo-ln:not(.wo-hd)'), tm = 0, tl = 0;
    /* A one-track form draws one rate per line (R1): the other box and its
       amount cell are simply not there. */
    function amt(r, name, q) {
      var el = r.querySelector('[name=' + name + ']');
      return el ? Math.round(q * (num(el.value) || 0) * 100) / 100 : 0;
    }
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var q = num(r.querySelector('[name=ln_qty]').value) || 0;
      var m = amt(r, 'ln_mrate', q), l = amt(r, 'ln_lrate', q);
      var mc = r.querySelector('[data-k=m]'), lc = r.querySelector('[data-k=l]');
      if (mc) mc.textContent = inr(m);
      if (lc) lc.textContent = inr(l);
      tm += m; tl += l;
    }
    var f = document.getElementById('wo-tot-m'), g = document.getElementById('wo-tot-l'),
        h = document.getElementById('wo-tot-g');
    if (f) f.textContent = inr(Math.round(tm * 100) / 100);
    if (g) g.textContent = inr(Math.round(tl * 100) / 100);
    if (h) h.textContent = inr(Math.round((tm + tl) * 100) / 100);
  }
  function needs() { return document.querySelectorAll('#wo-form .wo-need'); }
  function refreshBar() {
    var bar = document.getElementById('wo-needbar'), n = needs().length;
    if (!bar) return;
    bar.hidden = n === 0;
    var c = document.getElementById('wo-needcount');
    if (c) c.textContent = String(n);
  }
  window.woNext = function () {
    var list = needs();
    if (!list.length) return;
    list[0].scrollIntoView({block: 'center'});
    list[0].focus();
  };
  function addFrom(t) {
    var row = t.content.firstElementChild.cloneNode(true);
    body.appendChild(row);
    renumber(); recalc();
    var d = row.querySelector('[name=ln_desc]');
    if (d) d.focus();
  }
  window.woAdd = function () { addFrom(tpl); };
  window.woAddHeading = function () { if (htpl) addFrom(htpl); };
  body.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('.wo-del') : null;
    if (!b) return;
    var tr = b.closest('tr');
    if (tr) tr.parentNode.removeChild(tr);
    renumber(); recalc(); refreshBar();
  });
  /* R4 — the "Section (subtotal)" tick posts through the row's hidden ln_sec. */
  body.addEventListener('change', function (e) {
    var b = e.target;
    if (!b.classList || !b.classList.contains('wo-sec-box')) return;
    var h = b.closest('tr').querySelector('[name=ln_sec]');
    if (h) h.value = b.checked ? '1' : '0';
  });
  body.addEventListener('input', function (e) {
    var el = e.target;
    if (el.classList && el.classList.contains('wo-need') && ok(el)) {
      el.classList.remove('wo-need');
      refreshBar();
    }
    recalc();
  });
  var form = document.getElementById('wo-form');
  if (form) form.addEventListener('submit', function (e) {
    if (needs().length) { e.preventDefault(); refreshBar(); window.woNext(); }
  });
  renumber(); recalc(); refreshBar();
})();
</script>
"""


# =============================================================================
# SMALL PAGE HELPERS
# =============================================================================

def _page(html: str) -> str:
    """A finished page. Deliberately not Jinja-rendered — ABOUT.md §7.9d."""
    return html


def _alert(msg, kind: str = "error") -> str:
    if not msg:
        return ""
    icon = "&#10003;" if kind == "success" else "&#10007;"
    return f'<div class="alert alert-{P.esc(kind)}">{icon} {P.esc(msg)}</div>'


def _flash() -> str:
    kind = request.args.get("type", "success")
    return _alert(request.args.get("msg"),
                  kind if kind in ("success", "error") else "error")


def _shell(title: str, body: str, extra_styles: str = "") -> str:
    """A screen page in the app shell — the rail, the top bar, the shared sheets."""
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}{extra_styles}
</head>
<body>
{_nav()}
<main>
{body}
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · work orders</p></footer>
</main>
</body></html>""")


_BADGE = {
    "draft":     ("Draft",     "#fffbeb", "#b45309", "#fde68a"),
    "issued":    ("Issued",    "#f0fdf4", "#166534", "#bbf7d0"),
    "cancelled": ("Cancelled", "#fef2f2", "#b91c1c", "#fecaca"),
}


def status_badge(wo) -> str:
    label, bg, fg, border = _BADGE[status_of(wo)]
    return (f'<span style="padding:2px 8px;border-radius:12px;font-size:0.75rem;'
            f'font-weight:700;background:{bg};color:{fg};border:1px solid {border};">'
            f'{label}</span>')


# =============================================================================
# THE FORM — create and edit share it; the import prefills it
# =============================================================================

def _contractor_block(data: dict) -> str:
    """The picker and the typed fallback, as one field group (`po_draft`'s shape)."""
    opts = picker_options("Select a contractor from the address book",
                          only_types=CONTRACTOR_TYPES,
                          selected=data.get("contractor_id", ""))
    empty = ""
    if not has_options(CONTRACTOR_TYPES) and not data.get("contractor_id"):
        add = (f' <a href="{url_for("address.add_address")}">Add one to the '
               f'address book</a> as type <b>Contractor</b>, or type a name below.'
               if _can("address.add_address") else " Type a name below.")
        empty = (f'<div style="font-size:.78rem;color:var(--muted);margin-top:.25rem;">'
                 f'No contractor is filed in the address book yet.{add}</div>')
    return f"""
      <div class="form-group">
        <label for="contractor_id">Contractor</label>
        <select id="contractor_id" name="contractor_id">{opts}</select>
        <div style="font-size:.74rem;color:var(--muted);margin-top:.2rem;">
          Carries the address and the GSTIN with it.
        </div>{empty}
      </div>
      <div class="wo-or">&mdash; or, for a one-off contractor &mdash;</div>
      <div class="fg2">
        <div class="form-group">
          <label for="contractor_name">Contractor name</label>
          <input type="text" id="contractor_name" name="contractor_name"
                 value="{P.esc(data.get('contractor_name', ''))}"
                 placeholder="Not in the address book"/>
        </div>
        <div class="form-group">
          <label for="contractor_gstin">Their GSTIN <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <input type="text" id="contractor_gstin" name="contractor_gstin" maxlength="15"
                 style="text-transform:uppercase;"
                 value="{P.esc(data.get('contractor_gstin', ''))}"/>
        </div>
        <div class="form-group">
          <label for="contractor_phone">Their phone <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <input type="text" id="contractor_phone" name="contractor_phone" maxlength="40"
                 inputmode="tel" value="{P.esc(data.get('contractor_phone', ''))}"/>
        </div>
        <div class="form-group span2">
          <label for="contractor_addr">Their address <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <textarea id="contractor_addr" name="contractor_addr" rows="2">{P.esc(data.get('contractor_addr', ''))}</textarea>
        </div>
      </div>"""


def _cell(name: str, value: str, need: dict, field: str, extra: str = "",
          textarea: bool = False, aria: str = "") -> str:
    msg = need.get(field, "")
    cls = ' class="wo-need"' if msg else ""
    title = f' title="{P.esc(msg)}"' if msg else ""
    if textarea:
        return (f'<textarea name="{name}" rows="2" aria-label="{aria}"{cls}{title}>'
                f'{P.esc(value)}</textarea>')
    return (f'<input type="text" name="{name}" value="{P.esc(value)}" '
            f'aria-label="{aria}"{extra}{cls}{title}/>')


_RATE_POST = {"material_rate": "ln_mrate", "labour_rate": "ln_lrate"}
_RATE_KEY = {"material_rate": "m", "labour_rate": "l"}
_RATE_WORD = {"material_rate": "Material", "labour_rate": "Labour"}


def _row_html(r: dict, shown=("material_rate", "labour_rate")) -> str:
    """
    One editable line. `r` holds strings; `r["need"]` maps field -> sentence.

    `shown` is the rate tracks this form draws (R1, 5 October 2026): a
    one-track work order draws ONE rate and ONE amount per line and posts no
    box at all for the other — every row, headings included, posts the same
    lists, so they stay aligned row for row.
    """
    need = r.get("need") or {}
    notes = [n for n in str(r.get("note") or "").split("\n") if n.strip()]
    chips = "".join(f'<span class="wo-flag">{P.esc(n)}</span>' for n in notes)
    num = ' inputmode="decimal" autocomplete="off"'
    if r.get("is_header"):
        # A HEADING row: an item number and a description and nothing else. The
        # figure boxes are posted EMPTY as hidden inputs so the parallel lists
        # stay aligned row for row; the server drops them anyway. R4: a tick
        # makes it a SECTION heading, closed by a subtotal on the print — the
        # hidden `ln_sec` is what posts, kept in step by the form's script.
        sec = bool(r.get("section"))
        hidden_rates = "".join(
            f'\n            <input type="hidden" name="{_RATE_POST[f]}" value=""/>'
            for f in shown)
        return f"""
        <tr class="wo-ln wo-hd">
          <td><span class="wo-pos"></span>
            <input type="hidden" name="ln_id" value="{P.esc(r.get('line_id', ''))}"/>
            <input type="hidden" name="ln_note" value="{P.esc(r.get('note', ''))}"/>
            <input type="hidden" name="ln_hdr" value="1"/>
            <input type="hidden" name="ln_sec" value="{'1' if sec else '0'}"/>
            <input type="hidden" name="ln_unit" value=""/>
            <input type="hidden" name="ln_qty" value=""/>{hidden_rates}</td>
          <td class="c-item">{_cell("ln_item", r.get("item_no", ""), need, "item_no", aria="Heading item number")}</td>
          <td colspan="{3 + 2 * len(shown)}"><span class="wo-hd-tag">Heading &mdash; no quantity or rate</span><label class="wo-sec"><input type="checkbox" class="wo-sec-box"{" checked" if sec else ""}/> Section (subtotal)</label>{_cell("ln_desc", r.get("description", ""), need, "description", textarea=True, aria="Heading")}{chips}</td>
          <td><button type="button" class="wo-del" title="Delete this heading" aria-label="Delete this heading">&#10005;</button></td>
        </tr>"""
    rates = ""
    for f in shown:
        rates += (f'\n          <td class="c-num">{_cell(_RATE_POST[f], r.get(f, ""), need, f, num, aria=_RATE_WORD[f] + " rate")}</td>'
                  f'\n          <td class="wo-amt" data-k="{_RATE_KEY[f]}"></td>')
    return f"""
        <tr class="wo-ln">
          <td><span class="wo-pos"></span>
            <input type="hidden" name="ln_id" value="{P.esc(r.get('line_id', ''))}"/>
            <input type="hidden" name="ln_note" value="{P.esc(r.get('note', ''))}"/>
            <input type="hidden" name="ln_hdr" value="0"/>
            <input type="hidden" name="ln_sec" value="0"/></td>
          <td class="c-item">{_cell("ln_item", r.get("item_no", ""), need, "item_no", aria="Item number")}</td>
          <td>{_cell("ln_desc", r.get("description", ""), need, "description", textarea=True, aria="Description")}{chips}</td>
          <td class="c-unit">{_cell("ln_unit", r.get("unit", ""), need, "unit", aria="Unit")}</td>
          <td class="c-num">{_cell("ln_qty", r.get("qty", ""), need, "qty", num, aria="Quantity")}</td>{rates}
          <td><button type="button" class="wo-del" title="Delete this line" aria-label="Delete this line">&#10005;</button></td>
        </tr>"""


def _blank_row(header: bool = False) -> dict:
    return {"line_id": "", "item_no": "", "description": "", "unit": "",
            "qty": "", "material_rate": "", "labour_rate": "", "note": "",
            "is_header": header}


def shown_tracks(tracks: str, rows: list) -> tuple:
    """
    The rate columns the form draws: the DECLARED tracks — plus any other track
    in which a figure is already typed on some line, so that a refused
    one-track POST shows the operator the very figures it refused (R1: never
    silently dropped) rather than hiding them on the re-render.
    """
    declared = TRACK_RATES.get(tracks, TRACK_RATES["both"])
    out = [f for f in ("material_rate", "labour_rate")
           if f in declared or any(str(r.get(f) or "").strip()
                                   for r in rows if not r.get("is_header"))]
    return tuple(out)


def _mark(rows: list, problems: list) -> list:
    """Attach each row's problems to it as `need`, so the fields glow."""
    for r in rows:
        r.setdefault("need", {})
    for p in problems:
        if p.get("row") is not None and 0 <= p["row"] < len(rows):
            rows[p["row"]]["need"][p["field"]] = p["message"]
    return rows


def _problem_list(problems: list) -> str:
    if not problems:
        return ""
    items = ""
    for p in problems[:40]:
        where = f"Line {p['row'] + 1}: " if p.get("row") is not None else ""
        items += f"<li>{P.esc(where + p['message'])}</li>"
    more = (f"<li>…and {len(problems) - 40} more, marked in red below.</li>"
            if len(problems) > 40 else "")
    return (f'<div class="alert alert-error">&#10007; Nothing was saved. Fix the '
            f'marked fields and save again.<ul style="margin:.4rem 0 0 1.2rem;">'
            f'{items}{more}</ul></div>')


def _form_page(data: dict, rows: list, *, wo: dict = None, error: str = "",
               problems=None, banner: str = "") -> str:
    """
    The create / edit form. `rows` are string rows (`posted_rows()` shape),
    each optionally carrying `need` — the field -> sentence map the guided fix
    rings in red.
    """
    editing = wo is not None
    action = (url_for("workorder.edit_wo", id=wo["id"]) if editing
              else url_for("workorder.create_wo"))
    rows = list(rows) or [_blank_row() for _ in range(DEFAULT_ROWS)]
    tracks = data.get("tracks") if data.get("tracks") in TRACKS else "both"
    shown = shown_tracks(tracks, rows)
    body_rows = "".join(_row_html(r, shown) for r in rows)
    template_row = _row_html(_blank_row(), shown)
    template_head = _row_html(_blank_row(header=True), shown)
    n_need = sum(len(r.get("need") or {}) for r in rows)
    track_opts = "".join(
        f'<option value="{t}"{" selected" if t == tracks else ""}>{TRACK_LABEL[t]}</option>'
        for t in TRACKS)
    heads = "".join(
        f'<th class="c-num">{_RATE_WORD[f]} rate</th><th class="c-amt">{_RATE_WORD[f]} amount</th>'
        for f in shown)
    if len(shown) == 2:
        foot = """<tr>
            <td colspan="6" style="text-align:right;">Material total</td>
            <td class="wo-amt" id="wo-tot-m"></td>
            <td style="text-align:right;">Labour total</td>
            <td class="wo-amt" id="wo-tot-l"></td>
            <td></td>
          </tr><tr>
            <td colspan="8" style="text-align:right;">Grand total</td>
            <td class="wo-amt" id="wo-tot-g"></td>
            <td></td>
          </tr>"""
    else:
        k = _RATE_KEY[shown[0]] if shown else "l"
        foot = f"""<tr>
            <td colspan="6" style="text-align:right;">Total</td>
            <td class="wo-amt" id="wo-tot-{k}"></td>
            <td></td>
          </tr>"""
    rate_words = (" and ".join(f"a <b>{_RATE_WORD[f].lower()} rate</b>"
                               for f in TRACK_RATES[tracks]))
    imp = ""
    if not editing and _can("workorder.import_wo"):
        imp = (f'<a href="{url_for("workorder.import_wo")}" class="btn btn-ghost">'
               f'Import lines from Excel</a>')
    number = P.esc(wo.get("ref")) if editing else P.esc(next_ref())

    body = f"""
  <div class="page-top">
    <h1>{"Edit" if editing else "New"} <span>Work Order</span></h1>
    <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
      <a href="{url_for('workorder.list_wos')}" class="btn btn-ghost">All Work Orders</a>{imp}
    </div>
  </div>

  {_alert(error)}{_problem_list(problems or [])}
  {banner}

  <div class="wo-banner">
    Work assigned to a petty contractor &mdash; each line carries {rate_words}.
    This work order {"is" if editing else "will be"}
    numbered <b>{number}</b> from the one running series at
    {f'<a href="{url_for("settings.edit_settings")}">Settings</a>' if _can("settings.edit_settings") else "Settings"}.
    GST is added at the rate set below; 0 prints none.
  </div>

  <div class="wo-needbar" id="wo-needbar"{"" if n_need else " hidden"}>
    <span><b id="wo-needcount">{n_need}</b> field(s) need an answer before this
      can be saved &mdash; they are marked in red.</span>
    <button type="button" class="btn btn-ghost" onclick="woNext()">Go to the next one</button>
  </div>

  <form method="POST" action="{action}" id="wo-form">
    <div class="form-section">
      <div class="section-title">Rates on this work order</div>
      <div class="wo-tracks">
        <div class="form-group" style="margin:0;max-width:260px;">
          <label for="tracks">This work order carries</label>
          <select id="tracks" name="tracks">{track_opts}</select>
        </div>
        <button type="submit" name="act" value="retrack" class="btn btn-ghost">Update the rate columns</button>
        <span class="wo-tracks-hint">A work order that carries one rate never asks
          for the other, and stores none of it. Changing this redraws the lines.</span>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">Contractor</div>
      {_contractor_block(data)}
    </div>

    <div class="form-section">
      <div class="section-title">Work order details</div>
      <div class="fg2">
        <div class="form-group">
          <label for="date">Date</label>
          <input type="date" id="date" name="date" value="{P.esc(data.get('date', ''))}"/>
        </div>
        <div class="form-group">
          <label for="project_id">Project <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <select id="project_id" name="project_id">{_project_options(data.get("project_id", ""))}</select>
        </div>
        <div class="form-group">
          <label for="site">Site <span style="font-weight:500;text-transform:none;">(optional)</span></label>
          <input type="text" id="site" name="site" maxlength="{MAX_SITE_CHARS}"
                 value="{P.esc(data.get('site', ''))}" placeholder="e.g. Lucknow"/>
        </div>
        <div class="form-group">
          <label for="gst_rate">GST rate (%)</label>
          <input type="text" id="gst_rate" name="gst_rate" inputmode="decimal"
                 value="{P.esc('' if data.get('gst_rate') is None else data.get('gst_rate'))}"/>
        </div>
        <div class="form-group span2">
          <label for="notes">Notes / scope</label>
          <textarea id="notes" name="notes" rows="3">{P.esc(data.get('notes', ''))}</textarea>
        </div>
        <div class="form-group span2">
          <label for="terms">Terms &amp; Conditions <span style="font-weight:500;text-transform:none;">(one per line; printed numbered)</span></label>
          <textarea id="terms" name="terms" rows="4">{P.esc(data.get('terms', ''))}</textarea>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">Lines</div>
      <div class="wo-lines-wrap">
        <table class="wo-lines">
          <thead><tr>
            <th>#</th><th class="c-item">Item</th><th>Description</th>
            <th class="c-unit">Unit</th><th class="c-num">Qty</th>
            {heads}
            <th></th>
          </tr></thead>
          <tbody id="wo-lines-body">{body_rows}
          </tbody>
          <tfoot>{foot}</tfoot>
        </table>
      </div>
      <template id="wo-row-tpl">{template_row}</template>
      <template id="wo-hd-tpl">{template_head}</template>
      <div class="wo-tools">
        <button type="button" class="btn btn-ghost" onclick="woAdd()">+ Add a line</button>
        <button type="button" class="btn btn-ghost" onclick="woAddHeading()">+ Add a heading</button>
        <span style="font-size:.78rem;color:var(--muted);">The amounts above are a
          preview; the saved work order works them out again from each line's
          quantity and rates. A blank rate is not 0 &mdash; type 0 where there is none.</span>
      </div>
    </div>

    <div style="display:flex;gap:.75rem;margin-top:1.4rem;">
      <button type="submit" class="btn">{"Save changes" if editing else "Raise work order"}</button>
      <a href="{url_for('workorder.view_wo', id=wo['id']) if editing else url_for('workorder.list_wos')}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
{WO_FORM_JS}"""
    return _shell("Edit Work Order" if editing else "New Work Order", body,
                  WO_FORM_STYLES)


def _form_data(form) -> dict:
    """What was typed in the header fields — handed back on a refusal."""
    tracks = str(form.get("tracks") or "both").strip().lower()
    return {
        "date": (form.get("date") or "").strip()[:32],
        "project_id": (form.get("project_id") or "").strip()[:64],
        "notes": (form.get("notes") or "").strip()[:MAX_NOTES_CHARS],
        "contractor_id": (form.get("contractor_id") or "").strip()[:64],
        "contractor_name": (form.get("contractor_name") or "").strip()[:200],
        "contractor_gstin": (form.get("contractor_gstin") or "").strip()[:15],
        "contractor_phone": (form.get("contractor_phone") or "").strip()[:40],
        "contractor_addr": (form.get("contractor_addr") or "").strip()[:500],
        # 5 October 2026, the forty-third block — R1, R5, R6, R7.
        "tracks": tracks if tracks in TRACKS else "both",
        # `None` when the field was not posted at all (no form omits it; a
        # bare POST does), "" when it was posted blank — the two read
        # differently in `gst_rate_from()`.
        "gst_rate": (None if "gst_rate" not in form
                     else str(form.get("gst_rate") or "").strip()[:12]),
        "site": (form.get("site") or "").strip()[:MAX_SITE_CHARS],
        "terms": "\n".join(t.strip() for t in str(form.get("terms") or "")
                           .replace("\r\n", "\n").split("\n")
                           if t.strip())[:MAX_TERMS_CHARS],
    }


def gst_rate_from(raw) -> tuple:
    """
    `(rate, error)` for the posted GST % (R5) — a figure from 0 to 100.
    ⚠ A BLANK box is refused, never read as 0 — the blank-rate rule, applied
    to the tax: "no GST" is typed as 0. A field the POST did not carry at all
    (`None`) reads as 0, which is what a stored work order without the field
    means too.
    """
    if raw is None:
        return 0.0, ""
    s = str(raw).strip().rstrip("%").strip()
    if not s:
        return None, ("GST rate: type a figure from 0 to 100 — 0 when this work "
                      "order carries no GST.")
    try:
        v = float(s)
    except ValueError:
        return None, "GST rate: a figure from 0 to 100, please."
    if not math.isfinite(v) or v < 0 or v > 100:
        return None, "GST rate: a figure from 0 to 100, please."
    return v, ""


def _validate(form, keep_ids=frozenset()) -> tuple:
    """
    `(data, rows, lines, error, problems)` — **always returns data and rows**,
    so a refused form re-renders with what was typed (`address._validate()`'s
    contract).
    """
    data = _form_data(form)
    rows = posted_rows(form)
    lines, problems = lines_from_rows(rows, keep_ids, data["tracks"])
    rate, err = gst_rate_from(data["gst_rate"])
    if err:
        return data, rows, lines, err, problems
    data["gst_value"] = rate
    if not data["date"]:
        return data, rows, lines, "A work order needs a date.", problems
    contractor, err = contractor_from(form)
    if err:
        return data, rows, lines, err, problems
    data["contractor"] = contractor
    pid, pname, err = project_from(form)
    if err:
        return data, rows, lines, err, problems
    data["project_name"] = pname
    return data, rows, lines, "", problems


# =============================================================================
# THE DOCUMENT — the shared A4 sheet, driven by the WO's own rows (ruling J)
# =============================================================================

# The printed columns, ruling C exactly. The classes are the shared sheet's
# own (`VIEW_DOC_STYLES`): rates take the Rate column's width, amounts the
# Amount column's, so no width is invented here.
WO_COLUMNS = (("c-sno", "Sr"), ("c-desc", "Description"), ("c-unit", "Unit"),
              ("c-qty", "Qty"), ("c-price", "Material Rate"),
              ("c-total", "Material Amount"), ("c-price", "Labour Rate"),
              ("c-total", "Labour Amount"))


def _overprint(wo: dict) -> str:
    """
    The RA bill's lifecycle overprint, on a work order. **Only an ISSUED work
    order prints clean**: a draft carries DRAFT, a cancelled one CANCELLED with
    its date and reason, on screen and on paper — the entire risk is a working
    copy or a withdrawn order reaching a contractor looking like an instruction.
    """
    st = status_of(wo)
    if st == "issued":
        return ""
    if st == "cancelled":
        mark = "CANCELLED"
        band = (f"This work order was cancelled"
                f"{' on ' + P.esc(wo.get('cancelled_on')) if wo.get('cancelled_on') else ''}"
                f"{' &mdash; ' + P.esc(wo.get('cancel_reason')) if wo.get('cancel_reason') else ''}. "
                f"It is not an instruction to carry out the work. The number "
                f"{P.esc(wo.get('ref'))} is not reissued.")
    else:
        mark = "DRAFT"
        band = ("This is a DRAFT and has not been issued. Its lines and rates "
                "may still change and it is not an instruction to start work.")
    return f"""
    <div class="lc-mark lc-{st}">{mark}</div>
    <div class="lc-band lc-{st}">{band}</div>"""


def document_html(wo: dict) -> str:
    """
    The printed work order. **Every value is read off the stored record** — the
    contractor block is the snapshot taken at save, the project is the
    snapshotted name, and every figure is worked out from the stored lines.
    Nothing here reads the address book, a project or a schedule.

    5 October 2026, the forty-third block — each addition is drawn ONLY when
    the record carries it, so a work order with none of them (every one before
    the pass, and the existing print golden) prints byte-for-byte as before:

    * **one track** (R1): Sr | Description | Unit | Qty | Rate | Amount, and
      "Labour only" / "Material only" under the title;
    * **sections** (R4): "Subtotal - <section>" closing each group, then a
      SUMMARY of one row per section above the totals — their cover sheet;
    * **GST** (R5): the pre-tax total, "GST @ n%" and "Total (incl. GST)",
      the amount in words on the last;
    * **site** (R6) in the header block; **terms** (R7) as a numbered list
      after the totals, in the quotation's own Terms markup.
    """
    tracks = tracks_of(wo)
    one = TRACK_RATES[tracks][0] if tracks != "both" else None
    span = 5 if one else 7
    groups = section_groups(wo)
    gi = 0 if (groups and groups[0]["title"] is None) else -1

    def subtotal(g) -> str:
        title = P.esc(g["title"]) if g["title"] is not None else "Lines before the first section"
        if one:
            amt = g["material"] if one == "material_rate" else g["labour"]
            return f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">Subtotal - {title}</td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(amt)}</td>
        </tr>"""
        return f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">Subtotal - {title}</td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(g["material"])}</td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(g["labour"])}</td>
        </tr>"""

    rows, pos = "", 0
    for line in wo.get("lines") or []:
        if is_section(line) and groups:
            if gi >= 0:
                rows += subtotal(groups[gi])
            gi += 1
        if is_header(line):
            # A HEADING line (fix 2, 5 October 2026), drawn the way the BOQ
            # print draws a specification header: the item number in the Sr
            # column, the description spanning every figure column, and no
            # quantity, rate or amount — spanning them rather than "leaving a
            # row of blanks that reads as missing data" (`boq._section_table`).
            # `row-assembly` is the shared sheet's
            # own class for exactly that row: the purchase order and the draft
            # PO already draw a BOQ header line with it on this same sheet. It
            # takes no position number and adds nothing to any total.
            rows += f"""
        <tr class="row-assembly">
          <td class="c-sno">{P.esc(line.get("item_no"))}</td>
          <td colspan="{span}" class="c-desc">{P.esc(line.get("description"))}</td>
        </tr>"""
            continue
        pos += 1
        mat, lab, _tot = line_amounts(line)
        sr = P.esc(line.get("item_no")) or str(pos)
        if one:
            amt = mat if one == "material_rate" else lab
            figures = f"""
          <td class="c-price">{_inr(_f(line.get(one)))}</td>
          <td class="c-total">{_inr(amt)}</td>"""
        else:
            figures = f"""
          <td class="c-price">{_inr(_f(line.get("material_rate")))}</td>
          <td class="c-total">{_inr(mat)}</td>
          <td class="c-price">{_inr(_f(line.get("labour_rate")))}</td>
          <td class="c-total">{_inr(lab)}</td>"""
        rows += f"""
        <tr class="row-item">
          <td class="c-sno">{sr}</td>
          <td class="c-desc">{P.esc(line.get("description"))}</td>
          <td class="c-unit">{P.esc(line.get("unit"))}</td>
          <td class="c-qty">{_fmt_qty(_f(line.get("qty")))}</td>{figures}
        </tr>"""
    if groups and gi >= 0:
        rows += subtotal(groups[gi])

    t = totals_of(wo)
    gst = t["gst_rate"] > 0

    # ── R4: the SUMMARY — one row per section, above the totals ──────────
    if groups:
        rows += f"""
        <tr class="row-assembly">
          <td class="c-sno"></td>
          <td colspan="{span}" class="c-desc">Summary</td>
        </tr>"""
        for g in groups:
            title = (P.esc(g["title"]) if g["title"] is not None
                     else "Lines before the first section")
            blanks = ('<td class="c-price"></td>' if one else
                      '<td class="c-price"></td>\n          <td class="c-total"></td>\n'
                      '          <td class="c-price"></td>')
            rows += f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">{title}</td>
          {blanks}
          <td class="c-total">{_inr(g["grand"])}</td>
        </tr>"""

    def last_row(label: str, amount: float, total: bool) -> str:
        cls = "row-total row-sum" if total else "row-sum"
        blanks = ('<td class="c-price"></td>' if one else
                  '<td class="c-price"></td>\n          <td class="c-total"></td>\n'
                  '          <td class="c-price"></td>')
        return f"""
        <tr class="{cls}">
          <td colspan="4" class="sum-lbl">{label}</td>
          {blanks}
          <td class="c-total">{_inr(amount)}</td>
        </tr>"""

    if one:
        # One track: one Total — the pre-tax figure.
        rows += f"""
        <tr class="{"row-sum" if gst else "row-total row-sum"}">
          <td colspan="4" class="sum-lbl">Total</td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(t["grand"])}</td>
        </tr>"""
    else:
        # The two track totals sit under their own Amount columns; the grand
        # total closes the table in the last column, and the amount in words
        # restates it.
        rows += f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">Total</td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(t["material"])}</td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(t["labour"])}</td>
        </tr>
        <tr class="{"row-sum" if gst else "row-total row-sum"}">
          <td colspan="4" class="sum-lbl">Grand Total (Material + Labour)</td>
          <td class="c-price"></td>
          <td class="c-total"></td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(t["grand"])}</td>
        </tr>"""
    if gst:
        # R5 — derived, never stored: round(pre-tax x rate / 100, 2).
        rows += last_row(f"GST @ {t['gst_rate']:g}%", t["gst"], False)
        rows += last_row("Total (incl. GST)", t["total"], True)

    meta_col_1 = (
        DS._meta("Work Order No.", P.esc(wo.get("ref"))) +
        DS._meta("Your GSTIN",     P.esc(wo.get("contractor_gstin"))) +
        # 5 October 2026, fix 3 — drawn ONLY when the record carries a phone,
        # so a work order with none (every one before the field) prints
        # byte-for-byte as it did.
        (DS._meta("Your Phone", P.esc(wo.get("contractor_phone")))
         if str(wo.get("contractor_phone") or "").strip() else "") +
        DS._meta("Project",        P.esc(wo.get("project_name")))
    )
    site = str(wo.get("site") or "").strip()
    meta_col_2 = (
        DS._meta("Date",      P.esc(wo.get("date"))) +
        # R6 — only when the record carries a site.
        (DS._meta("Site", P.esc(site)) if site else "") +
        DS._meta("Our GSTIN", P.esc(B.COMPANY_GSTIN))
    )

    note_html = ""
    if wo.get("notes"):
        note_html = (f'<div class="wo-note"><b>Notes / scope:</b> '
                     f'{P.esc(wo["notes"])}</div>')

    # R7 — the quotation's own Terms markup (`tnc-title`, `ol.tnc-ol`), which
    # the shared sheet already styles: no new rule, so no stylesheet moves.
    terms = [t_ for t_ in str(wo.get("terms") or "").split("\n") if t_.strip()]
    terms_html = ""
    if terms:
        items = "".join(f'<li><span class="tnc-num">{i}.</span><span>{P.esc(t_.strip())}</span></li>'
                        for i, t_ in enumerate(terms, 1))
        terms_html = (f'\n  <div class="tnc-section">\n'
                      f'    <div class="tnc-title">Terms &amp; Conditions</div>\n'
                      f'    <ol class="tnc-ol">{items}</ol>\n  </div>')

    sub = ("Work assigned to contractor &mdash; material and labour rates"
           if not one else f"Work assigned to contractor &mdash; {TRACK_LABEL[tracks]}")
    columns = (WO_COLUMNS if not one else
               (("c-sno", "Sr"), ("c-desc", "Description"), ("c-unit", "Unit"),
                ("c-qty", "Qty"), ("c-price", "Rate"), ("c-total", "Amount")))

    return f"""
<div class="quotation-doc wo-doc">

{DS.sheet_open(show_web=False)}

  <div class="doc-box">{_overprint(wo)}
    <div class="doc-title">WORK ORDER</div>
    <div class="doc-sub-wo">{sub}</div>

{DS.party_block("To (Contractor)", DS.name_block(wo.get("to")), "",
                meta_col_1, meta_col_2)}

{DS.items_table(columns, rows)}

{DS.amount_words("Work Order Value (in words)", t["total"])}
  </div>
  {note_html}{terms_html}

{DS.sig_block("", "", computer_generated=True)}

{DS.sheet_close()}

</div>"""


# =============================================================================
# THE PROJECT PAGE'S PANEL — rendered cells, never arithmetic across panels
# =============================================================================

def project_panel_html(project_id: str) -> str:
    """
    The Work Orders panel on `/projects/view/<id>` (ruling H) — **listed only**.

    Each row is one work order and its OWN value; there is no panel total and
    nothing here is combined with another panel. ⚠ A work order is COMMITTED
    cost, not paid cost, and must never be merged with purchase orders or the
    charges ledger's Labour head (ABOUT.md §7) — this panel adds nothing up.

    **The empty string when the project has none**, so a project with no work
    order renders `/projects/view` byte-for-byte as it did.
    """
    wos = sorted((w for w in _wos().values()
                  if str(w.get("project_id") or "") == str(project_id or "")
                  and project_id),
                 key=lambda w: (str(w.get("date") or ""), str(w.get("ref") or "")),
                 reverse=True)
    if not wos:
        return ""
    rows = ""
    for w in wos:
        rows += f"""
        <tr>
          <td><a href="{url_for('workorder.view_wo', id=w.get('id'))}"><b>{P.esc(w.get('ref'))}</b></a></td>
          <td>{P.esc(w.get('date'))}</td>
          <td>{P.esc(w.get('contractor_name')) or '&mdash;'}</td>
          <td>{status_badge(w)}</td>
          <td style="text-align:right;">{_inr(totals_of(w)["total"])}</td>
        </tr>"""
    return f"""
    <!-- Work Orders Panel — listed only (5 October 2026). No total, and never
         added to another panel: a work order is committed cost, not paid. -->
    <div class="panel">
      <div class="panel-head">
        <h2>Work Orders</h2>
        <span style="font-size:0.8rem;color:var(--muted);">Work assigned to contractors &mdash; listed, not totalled</span>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th>Ref</th>
            <th>Date</th>
            <th>Contractor</th>
            <th>Status</th>
            <th style="text-align:right;">WO Value (incl. GST)</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>
"""


# =============================================================================
# ROUTES — the register, create, view, print, edit
# =============================================================================

def _get(id: str):
    return _wos().get(str(id or ""))


def _gone():
    return redirect(url_for("workorder.list_wos",
                            msg="That work order no longer exists.", type="error"))


@workorder_bp.route("/")
def list_wos():
    """
    The register — the quotation register's table (`QUOTATION_STYLES`'
    `.table-wrap`), which every page here already loads. ⚠ Deliberately NOT
    the dashboard's newer register stylesheet: `tests/test_registers.py` pins
    the two pages the owner has seen in that pattern, and a third is his call.
    """
    wos = sorted(_wos().items(),
                 key=lambda kv: (str(kv[1].get("date") or ""),
                                 str(kv[1].get("ref") or "")), reverse=True)
    rows = ""
    for wid, w in wos:
        n = sum(1 for l in w.get("lines") or [] if not is_header(l))
        project = P.esc(w.get("project_name")) or "&mdash;"
        rows += f"""
        <tr>
          <td class="td-ref">{P.esc(w.get("ref"))}</td>
          <td>{P.esc(w.get("date"))}</td>
          <td class="td-cust">{P.esc(w.get("contractor_name")) or "&mdash;"}</td>
          <td>{project}</td>
          <td>{status_badge(w)}</td>
          <td style="text-align:right;">{n}</td>
          <td class="td-total" style="text-align:right;">{_inr(totals_of(w)["total"])}</td>
          <td><a class="btn-view" href="{url_for('workorder.view_wo', id=wid)}">Open</a></td>
        </tr>"""

    acts = ""
    if _can("workorder.create_wo"):
        acts += (f'<a href="{url_for("workorder.create_wo")}" class="btn">'
                 f'+ New work order</a>')
    if _can("workorder.import_wo"):
        acts += (f'<a href="{url_for("workorder.import_wo")}" class="btn btn-ghost">'
                 f'Import from Excel</a>')

    table = (f"""
  <div class="table-wrap"><table>
    <thead><tr>
      <th>WO No.</th><th>Date</th><th>Contractor</th><th>Project</th>
      <th>Status</th><th style="text-align:right;">Lines</th>
      <th style="text-align:right;">Value (incl. GST)</th><th></th>
    </tr></thead>
    <tbody>{rows}
    </tbody>
  </table></div>""" if rows else """
  <div class="empty-state">No work orders yet.</div>""")

    body = f"""
  <div class="page-top">
    <h1>Work <span>Orders</span></h1>
    <div style="display:flex;gap:.7rem;flex-wrap:wrap;">{acts}</div>
  </div>

  {_flash()}

  <p style="font-size:.85rem;color:var(--muted);margin-bottom:1rem;">
    Work assigned to petty contractors &mdash; a different document from a
    purchase order, which buys material. Each line carries a material rate and
    a labour rate. One running series; the next is <b>{P.esc(next_ref())}</b>.
    No GST is stated on a work order.
  </p>
{table}"""
    return _shell("Work Orders", body)


def new_wo_defaults() -> dict:
    """
    A NEW work order's header, hand-made or imported: today's date, both rate
    tracks (R1), GST at 18 % (R5 — prefilled, editable) and the default terms
    from the work order's own settings record (R7).
    """
    return {"date": _date.today().isoformat(), "tracks": "both",
            "gst_rate": "18", "terms": SET.wo_default_terms()}


def _retrack(data: dict, rows: list, wo: dict = None) -> str:
    """
    "Update the rate columns" (R1): the form redrawn for the tracks now
    chosen, nothing saved. A figure already typed in a track the work order no
    longer carries stays ON THE PAGE, ringed and named — never dropped.
    """
    stray = stray_problems(rows, data["tracks"])
    banner = ("" if stray else
              f'<div class="alert alert-success">&#10003; The lines now carry '
              f'{P.esc(TRACK_LABEL[data["tracks"]])}. Nothing is saved until '
              f'you press {"Save changes" if wo else "Raise work order"}.</div>')
    return _form_page(data, _mark(rows, stray), wo=wo, problems=stray,
                      banner=banner)


@workorder_bp.route("/create", methods=["GET", "POST"])
def create_wo():
    if request.method == "GET":
        return _form_page(new_wo_defaults(), [])

    if request.form.get("act") == "retrack":
        return _retrack(_form_data(request.form), posted_rows(request.form))

    data, rows, lines, error, problems = _validate(request.form)
    if error or problems:
        return _form_page(data, _mark(rows, problems), error=error,
                          problems=problems)

    wid = str(uuid.uuid4())
    now = _now()
    _wos()[wid] = {
        "id": wid,
        "ref": _spend_ref(),
        "date": data["date"],
        "status": "draft",
        # Whichever contractor path was used, snapshotted (ruling G).
        **data["contractor"],
        # Optional, and snapshotted (ruling H).
        "project_id": data["project_id"],
        "project_name": data["project_name"],
        "notes": data["notes"],
        # 5 October 2026, the forty-third block: R1, R5, R6, R7.
        "tracks": data["tracks"],
        "gst_rate": data["gst_value"],
        "site": data["site"],
        "terms": data["terms"],
        "lines": lines,
        "created_at": now,
        "created_by": _uid(),
        "updated_at": now,
    }
    return redirect(url_for("workorder.view_wo", id=wid,
                            msg="Work order raised as a draft.", type="success"))


@workorder_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_wo(id: str):
    """Header fields AND lines — add, change, delete — while DRAFT only."""
    wo = _get(id)
    if not wo:
        return _gone()
    allowed, why = can_edit(wo)
    if not allowed:
        return redirect(url_for("workorder.view_wo", id=id, msg=why, type="error"))

    if request.method == "GET":
        typed = wo.get("contractor_source") == "typed"
        to_lines = str(wo.get("to") or "").split("\n")
        return _form_page({
            "date": wo.get("date", ""), "project_id": wo.get("project_id", ""),
            "notes": wo.get("notes", ""),
            "contractor_id": wo.get("contractor_id", "") if not typed else "",
            "contractor_name": wo.get("contractor_name", "") if typed else "",
            "contractor_gstin": wo.get("contractor_gstin", "") if typed else "",
            "contractor_phone": wo.get("contractor_phone", "") if typed else "",
            "contractor_addr": "\n".join(to_lines[1:]) if typed else "",
            "tracks": tracks_of(wo),
            # A stored work order with no `gst_rate` carries NO GST, so its
            # box opens at 0 and a resave keeps it that way.
            "gst_rate": num_text(wo.get("gst_rate")) or "0",
            "site": wo.get("site", ""), "terms": wo.get("terms", ""),
        }, rows_of(wo), wo=wo)

    if request.form.get("act") == "retrack":
        return _retrack(_form_data(request.form), posted_rows(request.form), wo)

    keep = frozenset(str(l.get("line_id") or "") for l in wo.get("lines") or [])
    data, rows, lines, error, problems = _validate(request.form, keep)
    if error or problems:
        return _form_page(data, _mark(rows, problems), wo=wo, error=error,
                          problems=problems)

    wo["date"] = data["date"]
    wo.update(data["contractor"])
    wo["project_id"] = data["project_id"]
    wo["project_name"] = data["project_name"]
    wo["notes"] = data["notes"]
    wo["tracks"] = data["tracks"]
    wo["gst_rate"] = data["gst_value"]
    wo["site"] = data["site"]
    wo["terms"] = data["terms"]
    wo["lines"] = lines
    wo["updated_at"] = _now()
    # `ref` is deliberately untouched. An edit never reissues the number.
    return redirect(url_for("workorder.view_wo", id=id,
                            msg="Work order updated.", type="success"))


@workorder_bp.route("/view/<id>")
def view_wo(id: str):
    """The document with its action bar — the screen page."""
    wo = _get(id)
    if not wo:
        return _gone()
    st = status_of(wo)

    acts = [f'<a href="{url_for("workorder.list_wos")}" class="btn btn-ghost">All Work Orders</a>']
    if can_edit(wo)[0] and _can("workorder.edit_wo"):
        acts.append(f'<a href="{url_for("workorder.edit_wo", id=id)}" class="btn btn-ghost">Edit</a>')
    if can_issue(wo)[0] and _can("workorder.issue_wo"):
        acts.append(f'<a href="{url_for("workorder.issue_wo", id=id)}" class="btn btn-ghost">Issue</a>')
    if can_cancel(wo)[0] and _can("workorder.cancel_wo"):
        acts.append(f'<a href="{url_for("workorder.cancel_wo", id=id)}" class="btn btn-ghost">Cancel</a>')
    if can_delete(wo)[0] and _can("workorder.delete_wo"):
        acts.append(f'<a href="{url_for("workorder.delete_wo", id=id)}" class="btn btn-ghost" '
                    f'style="color:#b91c1c;border-color:#fecaca;">&#128465;&nbsp;Delete</a>')
    if _can("workorder.print_wo"):
        acts.append(f'<a href="{url_for("workorder.print_wo", id=id)}" class="btn">&#128438;&nbsp;Print</a>')

    if st == "draft":
        state = ("A draft: its lines may still change. Issue it to send it to "
                 "the contractor; after that it can only be cancelled.")
    elif st == "issued":
        state = (f"Issued{' on ' + P.esc(wo.get('issued_on')) if wo.get('issued_on') else ''}. "
                 f"It cannot be edited &mdash; to change it, cancel it and raise "
                 f"a new work order.")
    else:
        state = (f"Cancelled{' on ' + P.esc(wo.get('cancelled_on')) if wo.get('cancelled_on') else ''}"
                 f"{' &mdash; ' + P.esc(wo.get('cancel_reason')) if wo.get('cancel_reason') else ''}. "
                 f"The number is not reissued.")
    project = ""
    if wo.get("project_id") or wo.get("project_name"):
        label = P.esc(wo.get("project_name")) or "project"
        if wo.get("project_id") in (STORE.get("projects") or {}) \
                and _can("projectview.view_project"):
            project = (f'<a class="wo-chip" href="'
                       f'{url_for("projectview.view_project", id=wo["project_id"])}">'
                       f'{label} &middot; project</a>')
        else:
            project = f'<span class="wo-chip">{label} &middot; project</span>'

    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(wo.get('ref')) + " Work Order")}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{WO_DOC_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Work Order <span style="color:var(--brand);">{P.esc(wo.get('ref'))}</span>
    {status_badge(wo)}
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    {"".join(acts)}
  </div>
</div>

{_flash()}
<div class="wo-panel"><span class="wo-st">{_BADGE[st][0]}</span> &middot; {state}
  {f'<div style="margin-top:.4rem;">{project}</div>' if project else ''}</div>

<div class="doc-outer">
{document_html(wo)}
</div>

<footer style="margin-top:1.75rem;">
  <p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · work order</p>
</footer>
</main>
</body></html>""")


@workorder_bp.route("/print/<id>")
def print_wo(id: str):
    """The document alone behind a `.no-print` action bar — `/po/print`'s shape."""
    wo = _get(id)
    if not wo:
        return _gone()
    return _page(f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(str(wo.get('ref')))}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{WO_DOC_STYLES}
</head>
<body>
<div class="screen-acts no-print">
  <a href="{url_for('workorder.view_wo', id=id)}" class="btn btn-ghost">&#8592;&nbsp;Back</a>
  <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
</div>
<div class="doc-outer">
{document_html(wo)}
</div>
</body></html>""")


# =============================================================================
# THE LIFECYCLE ROUTES — GET confirms, POST acts (`ra.py`'s shape, `9d060ee`)
# =============================================================================
#
# No `confirm()` anywhere: a browser dialog is not a guard — a prefetching
# browser, a crawler or a pasted link issues a plain GET. Each route mutates
# only inside its POST branch, and each ships its own GET-changes-nothing test
# (ABOUT.md §7.9f: the url_map sweep reads only paths containing "delete").

def _summary(wo: dict) -> str:
    n = sum(1 for l in wo.get("lines") or [] if not is_header(l))
    return (f"<b>{P.esc(wo.get('ref'))}</b> to "
            f"<b>{P.esc(wo.get('contractor_name')) or 'an unnamed contractor'}</b>, "
            f"dated {P.esc(wo.get('date'))}, with <b>{n} line{'' if n == 1 else 's'}</b> "
            f"worth <b>{_inr(totals_of(wo)['total'])}</b>")


@workorder_bp.route("/issue/<id>", methods=["GET", "POST"])
def issue_wo(id: str):
    """Issue a draft — the point it stops being editable."""
    wo = _get(id)
    if not wo:
        return _gone()
    allowed, why = can_issue(wo)
    if not allowed:
        return redirect(url_for("workorder.view_wo", id=id, msg=why, type="error"))

    if request.method == "POST":
        apply_issue(wo, on=(request.form.get("issued_on") or ""))
        return redirect(url_for("workorder.view_wo", id=id,
                                msg=f"{wo.get('ref')} issued.", type="success"))

    body = f"""
  <div class="page-top"><h1>Issue <span>{P.esc(wo.get('ref'))}</span></h1></div>
  <div class="wo-banner">
    You are about to issue {_summary(wo)}.<br/><br/>
    Once issued it <b>can no longer be edited and cannot be deleted</b>. Its
    printed sheet drops the DRAFT marker. To withdraw it afterwards you cancel
    it, which keeps the number <b>{P.esc(wo.get('ref'))}</b> spent.
  </div>
  <form method="POST" action="{url_for('workorder.issue_wo', id=id)}"
        style="display:flex;gap:.7rem;align-items:flex-end;flex-wrap:wrap;">
    <div class="form-group" style="margin:0;"><label for="issued_on">Issued on</label>
      <input type="date" id="issued_on" name="issued_on" value="{P.esc(_date.today().isoformat())}"/></div>
    <button type="submit" class="btn">Issue {P.esc(wo.get('ref'))}</button>
    <a href="{url_for('workorder.view_wo', id=id)}" class="btn btn-ghost">Go back</a>
  </form>"""
    return _shell(f"Issue {wo.get('ref')}", body, WO_FORM_STYLES)


@workorder_bp.route("/cancel/<id>", methods=["GET", "POST"])
def cancel_wo(id: str):
    """Withdraw a work order. **There is no route back**, and a reason is required."""
    wo = _get(id)
    if not wo:
        return _gone()
    allowed, why = can_cancel(wo)
    if not allowed:
        return redirect(url_for("workorder.view_wo", id=id, msg=why, type="error"))

    error = ""
    if request.method == "POST":
        reason = (request.form.get("cancel_reason") or "").strip()
        if not reason:
            error = ("Say why this work order is being cancelled. Its number "
                     "stays spent forever, so the reason is the only thing that "
                     "will explain the gap later.")
        else:
            apply_cancel(wo, reason, on=(request.form.get("cancelled_on") or ""))
            return redirect(url_for("workorder.view_wo", id=id,
                                    msg=f"{wo.get('ref')} cancelled.",
                                    type="success"))

    state = "issued" if status_of(wo) == "issued" else "a draft"
    body = f"""
  <div class="page-top"><h1>Cancel <span>{P.esc(wo.get('ref'))}</span></h1></div>
  {_alert(error)}
  <div class="wo-banner">
    <b>&#9888; This cannot be undone.</b> You are about to cancel {_summary(wo)},
    currently {state}.<br/><br/>
    The work order is <b>not deleted</b>. It keeps every line and figure, still
    prints as a record with a CANCELLED overprint, and keeps the number
    <b>{P.esc(wo.get('ref'))}</b>. To change the work, raise a new work order.
  </div>
  <form method="POST" action="{url_for('workorder.cancel_wo', id=id)}">
    <div class="form-section">
      <div class="fg2">
        <div class="form-group"><label for="cancel_reason">Why is it being cancelled?</label>
          <input type="text" id="cancel_reason" name="cancel_reason" maxlength="{MAX_REASON_CHARS}"
                 value="{P.esc(request.form.get('cancel_reason') or '')}"
                 placeholder="e.g. scope changed, reissued as a new work order"/></div>
        <div class="form-group"><label for="cancelled_on">Cancelled on</label>
          <input type="date" id="cancelled_on" name="cancelled_on" value="{P.esc(_date.today().isoformat())}"/></div>
      </div>
    </div>
    <div style="display:flex;gap:.7rem;">
      <button type="submit" class="btn">Cancel {P.esc(wo.get('ref'))}</button>
      <a href="{url_for('workorder.view_wo', id=id)}" class="btn btn-ghost">Keep it</a>
    </div>
  </form>"""
    return _shell(f"Cancel {wo.get('ref')}", body, WO_FORM_STYLES)


@workorder_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_wo(id: str):
    """
    Delete a DRAFT. GET confirms, POST destroys. Owner-only (`auth.OWNER_ONLY`),
    as the PO's delete is.

    **The number is not released.** The counter at `/settings` only advances,
    so the next work order takes the next number and this one's is spent.
    An issued or cancelled work order is refused: it is cancelled, not deleted.
    """
    wo = _get(id)
    if not wo:
        return _gone()
    allowed, why = can_delete(wo)
    if not allowed:
        return redirect(url_for("workorder.view_wo", id=id, msg=why, type="error"))

    if request.method == "POST":
        ref = str(wo.get("ref") or "")
        _wos().pop(id, None)
        return redirect(url_for("workorder.list_wos", type="success",
                                msg=f"Work order {ref} deleted. Its number is "
                                    f"not reissued."))

    body = f"""
  <div class="page-top"><h1>Delete <span>{P.esc(wo.get('ref'))}</span></h1></div>
  <div class="wo-banner">
    <b>&#9888; This cannot be undone.</b> You are about to delete the draft
    {_summary(wo)}.<br/>
    <b>The number is not released</b> &mdash; the next work order takes the
    next number in the series.
  </div>
  <form method="POST" action="{url_for('workorder.delete_wo', id=id)}" style="display:flex;gap:.7rem;">
    <button type="submit" class="btn">Delete {P.esc(wo.get('ref'))}</button>
    <a href="{url_for('workorder.view_wo', id=id)}" class="btn btn-ghost">Keep it</a>
  </form>"""
    return _shell(f"Delete {wo.get('ref')}", body, WO_FORM_STYLES)


# =============================================================================
# EXCEL IMPORT — sheetimport.py, with this document's own mapping (ruling D)
# =============================================================================
#
# STAGING (5 October 2026, CLIENT_CHANGES.md §0 forty-second block, fix 1).
# The read workbook — cell values, never the file — waits between the upload
# and the mapping in the persisted STORE collection `wo_imports`, through
# `importstage.py`: the BOQ importer's own mechanism, moved into that leaf so
# both use one copy. Keyed by an unguessable token, owned by the uploader, 24
# hours, three per user, consumed when the prefilled form renders — and,
# because it is a persisted collection, it survives a restart of the process.
# ⚠ Its OWN collection, not `boq_imports`: a work-order upload must never evict
#   a BOQ upload from the per-user cap, nor open on `/boq/import/<token>`.
# (Until this fix it was a dict in this module's RAM — ABOUT.md §7 gap 58,
# closed.)

# This document's mapping targets — its OWN vocabulary (ruling D). The two rate
# tracks are Material and Labour; amounts are read only to CHECK the sheet's
# arithmetic, never imported.
TARGETS = (
    ("",                "— ignore —"),
    ("item_no",         "Item No."),
    ("description",     "Description"),
    ("qty",             "Quantity"),
    ("unit",            "Unit"),
    ("material_rate",   "Material rate"),
    ("labour_rate",     "Labour rate"),
    ("material_amount", "Material amount (check only)"),
    ("labour_amount",   "Labour amount (check only)"),
    ("amount",          "Amount (check only)"),
)
TARGET_KEYS = tuple(k for k, _l in TARGETS)
TARGET_LABEL = dict(TARGETS)

# The reader speaks in the BOQ's two tracks; a work order's are material and
# labour. One table each way, so the reader is reused exactly as written.
_TO_SI = {"item_no": "item_no", "description": "description", "qty": "qty",
          "unit": "unit", "material_rate": "supply_rate",
          "labour_rate": "install_rate", "material_amount": "supply_amount",
          "labour_amount": "install_amount", "amount": "amount"}
_FROM_SI = {v: k for k, v in _TO_SI.items()}


def staged() -> dict:
    """The `wo_imports` collection."""
    return IS.rows(STAGE_COLLECTION)


def _purge(now: float = None) -> int:
    return IS.purge(STAGE_COLLECTION, STAGE_TTL_SECONDS, now)


def _own(token: str):
    return IS.own(STAGE_COLLECTION, token, _uid())


def _grid(rec: dict):
    """The staged grid of the selected sheet, or None."""
    try:
        return rec["grid"][int(rec.get("sheet_index") or 0)]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def stage(wb: dict, filename: str, uid: str) -> str:
    """
    Stage a read workbook for `uid` and return its token — the row shape of
    `boqimport.stage()`, less the BOQ's own layout memory and rate mode, which
    a work order has neither of. The per-user cap runs after the row is in.
    """
    token = IS.new_token()
    sel = int(wb["selected"])
    staged()[token] = {
        "id": token, "token": token, "user_id": uid,
        "created_at": IS.now_text(), "created_ts": time.time(),
        "filename": filename, "format": wb["format"],
        "sheets": wb["sheets"], "grid": wb["grid"],
        "sheet_index": sel,
        # R4 (5 October 2026): several tabs into one work order. `ticked` is
        # the tabs to build, by default only the reader's own pick; `mapping`
        # holds ONE column mapping PER TAB, keyed by the tab's index — the
        # columns differ from tab to tab.
        "ticked": [sel],
        "mapping": {str(sel): guess_mapping(wb["grid"][sel])},
    }
    IS.cap_per_user(STAGE_COLLECTION, uid, MAX_STAGED_PER_USER)
    return token


def _tab_grid(rec: dict, i: int):
    try:
        return rec["grid"][int(i)]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _ticked(rec: dict) -> list:
    """The ticked tabs, in workbook order, each one staged."""
    out = []
    ticked = rec.get("ticked")
    if ticked is None:                       # a row staged before R4
        ticked = [rec.get("sheet_index") or 0]
    for i in ticked:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if _tab_grid(rec, i) is not None and i not in out:
            out.append(i)
    return sorted(out)


def _mapping_of(rec: dict, i: int) -> dict:
    """
    Tab `i`'s column mapping — the one confirmed or posted, else the reader's
    guess for that tab. A row staged before R4 holds ONE flat mapping for its
    `sheet_index`; it is read as that tab's.
    """
    m = rec.get("mapping") or {}
    if m and all(isinstance(v, str) for v in m.values()):
        m = {str(rec.get("sheet_index") or 0): m}
    tab = m.get(str(i))
    return dict(tab) if isinstance(tab, dict) else guess_mapping(_tab_grid(rec, i))


def guess_mapping(grid: dict) -> dict:
    """
    `{column: target}` — the reader's own guess, said in this document's words.

    `sheetimport` already reads "Material" as one track and "Labour" /
    "Installation" / "Erection" as the other, so its guess is translated, not
    re-made. A rate it could not place stays "?" for the operator to choose;
    a base rate or an escalation % has no place on a work order and is left
    ignored.
    """
    out = {}
    for col, t in SI.guess_mapping(grid).items():
        out[col] = SI.UNDECIDED if t == SI.UNDECIDED else _FROM_SI.get(t, "")
    return out


def clean_mapping(grid: dict, posted, prefix: str = "map_") -> dict:
    """A posted mapping for one tab, reduced to known targets. Each tab's boxes
    are named `map_<tab>_<column>` on the multi-tab preview (R4)."""
    out = {}
    for c in grid["cols"]:
        t = str(posted.get(f"{prefix}{c}", "") or "")
        out[str(c)] = t if (t in TARGET_KEYS or t == SI.UNDECIDED) else ""
    return out


def import_tracks(mappings: list) -> str:
    """
    R1's default for an IMPORT: "labour" or "material" when exactly one rate
    track is mapped across the ticked tabs, else "both". It is a default —
    shown at the top of the form, and the operator may change it.
    """
    mapped = {t for m in mappings for t in m.values()
              if t in ("material_rate", "labour_rate")}
    if mapped == {"labour_rate"}:
        return "labour"
    if mapped == {"material_rate"}:
        return "material"
    return "both"


def mapping_problems(grid: dict, mapping: dict) -> list:
    """Why this mapping cannot be used yet — [] when it can."""
    probs = []
    for c in grid["cols"]:
        if mapping.get(str(c)) == SI.UNDECIDED:
            probs.append(f"Column {SI.col_letter(c)} looks like a rate but does "
                         f"not say which: choose Material rate or Labour rate "
                         f"for it, or ignore it.")
    seen = {}
    for c in grid["cols"]:
        t = mapping.get(str(c), "")
        if t and t != SI.UNDECIDED:
            seen.setdefault(t, []).append(SI.col_letter(c))
    for t, letters in seen.items():
        if len(letters) > 1:
            probs.append(f"{TARGET_LABEL[t]} is chosen for {len(letters)} columns "
                         f"({', '.join(letters)}). Keep one.")
    if "description" not in seen:
        probs.append("Choose the column that holds the Description.")
    if "qty" not in seen:
        probs.append("Choose the column that holds the Quantity.")
    return probs


# The reader's sentences name the BOQ's tracks; on this page they are material
# and labour.
_WORDS = ((re.compile(r"supply \+ installation", re.I), "material + labour"),
          (re.compile(r"\bSupply\b"), "Material"),
          (re.compile(r"\bsupply\b"), "material"),
          (re.compile(r"\bInstallation\b"), "Labour"),
          (re.compile(r"\binstallation\b"), "labour"))


def _wo_words(text: str) -> str:
    for rx, rep in _WORDS:
        text = rx.sub(rep, text)
    return text


def item_column_values(grid: dict, mapping: dict) -> set:
    """
    Every text written in the column mapped to Item No. — so a section heading
    takes its code as its item number only when the SHEET wrote that code, and
    never a letter the reader assigned itself.
    """
    col = next((c for c, t in mapping.items() if t == "item_no"), None)
    if col is None:
        return set()
    try:
        ci = [str(c) for c in grid["cols"]].index(str(col))
    except ValueError:
        return set()
    out = set()
    for _rnum, vals in grid.get("rows") or []:
        v = vals[ci] if ci < len(vals) else None
        if v is not None and str(v).strip():
            out.add(str(v).strip())
    return out


def rows_from_build(result: dict, mapping: dict, sheet_codes=frozenset(),
                    tracks: str = None, tab_name: str = "", left_out=None) -> list:
    """
    ⚠ **5 October 2026, the forty-third block** — what changed, read first:

    * `tracks` (R1): only the DECLARED tracks are filled and asked for; the
      other is left blank and never ringed. `None` keeps the pre-R1 reading —
      the tracks this tab maps (`import_tracks([mapping])`).
    * SECTIONS (R4): each titled sheet section comes in as a SECTION heading
      (`section` True), and a tab with no section title opens with its TAB
      NAME as one, so a work order built from several tabs keeps each tab as
      a group with its own subtotal.
    * QTY-0 LINES (R3, a work-order import only): a priced line with quantity
      0 and NO non-zero rate on any declared track is LEFT OUT — a BOQ row this
      contractor is not doing. Quantity 0 WITH a rate is kept as a rate-only
      line. A heading whose every child was left out goes too, and so does a
      section left with nothing in it; nothing is left orphaned. Each sheet
      row left out is appended to `left_out` as `(tab_name, row)`.
    """
    rows = _rows_from_build(result, mapping, sheet_codes, tracks, tab_name)
    return _drop_qty0(rows, tracks or import_tracks([mapping]), tab_name, left_out)


def _rows_from_build(result: dict, mapping: dict, sheet_codes=frozenset(),
                     tracks: str = None, tab_name: str = "") -> list:
    """
    `sheetimport.build()`'s lines as this form's rows (a list), each
    carrying `need` (the fields the save will refuse until answered) and `note`
    (what the reader said about the row).

    * A **group label** is dropped: its words are already in front of each of
      its children's descriptions (`sheetimport._group_labels()`).
    * **Specification text** with no item number is FOLDED into its parent's
      description — the BOQ importer's rule (`boqimport.editor_model()`).
    * ⚠ **A heading row is a HEADING LINE** (5 October 2026, CLIENT_CHANGES.md
      §0 forty-second block, fix 2) — the BOQ importer's rule: a line the
      reader marks `is_header` comes in `is_header`, with its item number and
      its description and NO unit, quantity or rate, and nothing ringed. So
      does specification text with no parent above it to fold into, and so
      does each titled SECTION of the sheet ("A  CIVIL WORKS"), placed before
      its first line — a work order has no sections of its own, and dropping
      the sheet's section titles would lose the sheet's own structure. A
      section's code becomes the heading's item number only when the sheet
      itself wrote it (`sheet_codes`); a letter the reader assigned is not
      printed. Until this fix a heading row came in as a PRICED line with its
      figures blank and ringed, which made every heading a thing to delete.
    * **One rate column on the sheet** (ruling D): that track fills; the other
      is left BLANK and marked on every PRICED line, saying the sheet has no
      such column. A blank rate is never read as 0.
    * The reader's own blocking flags mark the same fields here.
    """
    has_mat = "material_rate" in mapping.values()
    has_lab = "labour_rate" in mapping.values()
    declared = TRACK_RATES[tracks or import_tracks([mapping])]
    titles = {s.get("code"): (s.get("title") or "").strip()
              for s in result.get("sections") or []}
    rows, last, seen_sections = [], {}, set()

    def heading(item_no: str, text: str, notes=(), section: bool = False,
                row=None, parent: str = "", sec_code=None) -> dict:
        h = {"line_id": "", "is_header": True, "item_no": item_no, "_row": row,
             "_parent": parent, "_sec": sec_code,
             "description": text, "unit": "", "qty": "",
             "material_rate": "", "labour_rate": "",
             "note": "\n".join(notes)[:2000], "need": {}}
        if section:
            h["section"] = True
        return h

    # R4 — a tab with no section title of its own is one section, its name.
    if tab_name and not any(t for t in titles.values()):
        rows.append(heading("", tab_name, section=True))

    for l in result["lines"]:
        kind = l.get("kind")
        sec = l.get("section")
        if sec not in seen_sections:
            seen_sections.add(sec)
            if titles.get(sec):
                code = str(sec or "")
                rows.append(heading(code if code in sheet_codes else "", titles[sec],
                                    section=True))
        if kind == "group_label":
            continue
        header = bool(l.get("is_header"))
        src = f"Row {l.get('row')}"
        flag_notes = [f"{src}: {_wo_words(m)}" for m in (l.get("flags") or [])]
        if header and not l.get("item_no") and kind in ("spec_text", "subheading"):
            text = (l.get("description") or "").strip()
            tgt = (last.get((sec, l.get("parent_item_no")))
                   if l.get("parent_item_no") else None)
            if tgt is not None:
                if text:
                    base = rows[tgt]["description"].rstrip()
                    rows[tgt]["description"] = f"{base}\n{text}" if base else text
                continue
            if text:
                rows.append(heading("", text, flag_notes, row=l.get("row"),
                                    parent=l.get("parent_item_no") or "", sec_code=sec))
            continue
        if header:
            rows.append(heading(l.get("item_no") or "", l.get("description") or "",
                                flag_notes, row=l.get("row"),
                                parent=l.get("parent_item_no") or "", sec_code=sec))
            if l.get("item_no"):
                last[(sec, l.get("item_no"))] = len(rows) - 1
            continue
        # A PRICED line.
        need, notes = {}, list(flag_notes)
        row = {"line_id": "", "is_header": False, "item_no": l.get("item_no") or "",
               "description": l.get("description") or "",
               "unit": l.get("unit") or "",
               "qty": num_text(l.get("qty")),
               "material_rate": (num_text(l.get("supply_rate"))
                                 if has_mat and "material_rate" in declared else ""),
               "labour_rate": (num_text(l.get("install_rate"))
                               if has_lab and "labour_rate" in declared else ""),
               "_row": l.get("row"), "_parent": l.get("parent_item_no") or "",
               "_sec": sec}
        for n in l.get("needs") or []:
            f = {"total_qty": "qty", "description": "description",
                 "supply_rate": "material_rate",
                 "install_rate": "labour_rate"}.get(n.get("field"))
            msg = f"{src}: {_wo_words(n.get('message') or '')}"
            if n.get("field") == "rate":
                for g in ("material_rate", "labour_rate"):
                    if not row[g] and g in declared:
                        need[g] = msg
            elif f and (f not in ("material_rate", "labour_rate") or f in declared):
                need[f] = msg
        if not row["qty"]:
            need.setdefault("qty", f"{src}: no quantity on the sheet — type it")
        for f, present, word in (("material_rate", has_mat, "material"),
                                 ("labour_rate", has_lab, "labour")):
            if row[f] or f not in declared:
                continue
            if present:
                need.setdefault(f, f"{src}: no {word} rate on this row — type "
                                   f"it, or 0 if there is none")
            else:
                need.setdefault(f, f"The sheet has no {word} rate column — type "
                                   f"the {word} rate, or 0 if there is none")
        if l.get("rate_only"):
            notes.append(f"{src}: rate only (RO) on the sheet — quantity 0")
        row["note"] = "\n".join(notes)[:2000]
        row["need"] = need
        rows.append(row)
        if l.get("item_no"):
            last[(sec, l.get("item_no"))] = len(rows) - 1
    return rows


def _is_zero(text) -> bool:
    v, why = _figure(text)
    return why == "" and v == 0


def _drop_qty0(rows: list, tracks: str, tab_name: str = "", left_out=None) -> list:
    """
    R3 (5 October 2026), on a work-order import ONLY — `boqimport.py` never
    calls this. The client's sheets are their whole BOQ, and a row with
    quantity 0 is a row this contractor is not doing.

    * quantity 0 AND no non-zero rate on any DECLARED track → left out;
    * quantity 0 WITH a rate → kept, a rate-only line, with a note saying so;
    * a heading whose every child was left out → left out (no orphan);
    * a section whose every line was left out → left out with all it holds.

    A quantity left BLANK by the reader is not 0, and is never dropped: it is
    still ringed for somebody to type. `left_out` collects `(tab, sheet row)`
    for every row with a sheet row number that was left out.
    """
    declared = TRACK_RATES.get(tracks, TRACK_RATES["both"])
    drop = set()
    for i, r in enumerate(rows):
        if r.get("is_header") or not _is_zero(r.get("qty")):
            continue
        rated = any((_figure(r.get(f))[0] or 0) > 0 for f in declared)
        if not rated:
            drop.add(i)
        elif "rate only" not in str(r.get("note") or "").lower():
            note = f"Row {r.get('_row')}: rate only — quantity 0 on the sheet"
            r["note"] = (f"{r['note']}\n{note}" if r.get("note") else note)[:2000]
    heads = [i for i, r in enumerate(rows) if r.get("is_header")]
    # A heading's CHILDREN are the rows the sheet itself puts under it — the
    # reader's `parent_item_no` within the same section — never merely the
    # rows that follow it: item 3 after heading 2 is heading 2's sibling.
    # Deepest first, so a sub-heading left empty empties its parent in turn.
    #
    # ⚠ **A heading with NOTHING under it is an orphan too, and goes** — "no
    #   orphan headings". With no child by the sheet's parent relation, its
    #   children are the rows that follow it up to the next heading; none at
    #   all and it is left out (and listed). Found on the client's own sheet:
    #   their "TOTAL OF SPRINKLER" row has its amount in a column with no
    #   heading, so the reader cannot confirm it as the grand total by its
    #   sums, and the contractor's OWN quote notes and terms under it came
    #   in as heading lines. R7 forbids
    #   carrying the contractor's terms onto our work order; this keeps them
    #   off it without touching the shared reader's grand-total rule. A child
    #   comes AFTER its heading and before the next heading carrying the same
    #   number: those terms are numbered 1–5 again, and the real items 1, 2,
    #   4 and 5 above them must not count as theirs.
    for h in reversed(heads):
        if rows[h].get("section"):
            continue
        kids = []
        no, sec = rows[h].get("item_no"), rows[h].get("_sec")
        if no:
            end = next((j for j in heads if j > h and rows[j].get("item_no") == no
                        and rows[j].get("_sec") == sec), len(rows))
            kids = [j for j in range(h + 1, end)
                    if rows[j].get("_parent") == no and rows[j].get("_sec") == sec]
        if not kids:
            nxt = next((j for j in heads if j > h), len(rows))
            kids = list(range(h + 1, nxt))
            # An UNNUMBERED heading may introduce numbered ones: the heading
            # after it is its child (already decided, deepest first), unless
            # that is a section heading. A numbered one directly followed by
            # another heading is followed by its sibling, not its child.
            if not no and nxt < len(rows) and not rows[nxt].get("section"):
                kids.append(nxt)
        if not any(j not in drop for j in kids):
            drop.add(h)
    secs = [i for i in heads if rows[i].get("section")]
    for k, h in enumerate(secs):
        nxt = secs[k + 1] if k + 1 < len(secs) else len(rows)
        members = [j for j in range(h + 1, nxt) if not rows[j].get("is_header")]
        if not any(j not in drop for j in members):
            drop.update(range(h, nxt))
    if left_out is not None:
        for i in sorted(drop):
            if rows[i].get("_row") is not None:
                left_out.append((tab_name, rows[i]["_row"]))
    return [r for i, r in enumerate(rows) if i not in drop]


def _left_out_html(left_out: list) -> str:
    """How many sheet rows were left out, and which — on the preview and the form."""
    if not left_out:
        return ""
    by_tab = {}
    for tab, row in left_out:
        by_tab.setdefault(tab, []).append(row)
    bits = "; ".join(f"{P.esc(tab) + ' ' if tab else ''}row{'s' if len(rs) > 1 else ''} "
                     f"{', '.join(str(x) for x in rs)}" for tab, rs in by_tab.items())
    n = len(left_out)
    return (f"<li><b>{n} row{'' if n == 1 else 's'} left out</b> &mdash; quantity 0 "
            f"and no rate on the sheet, or a heading left with nothing under it: "
            f"{bits}.</li>")


def _totals_banner(totals: dict) -> str:
    """The reader's own sum check, said in this document's words."""
    checks = totals.get("checks") or []
    if not checks:
        return ""
    names = {"supply": "Material", "install": "Labour", "both": "Material + labour"}
    bits = []
    for c in checks:
        name = names.get(c.get("track"), c.get("track"))
        if c.get("status") == "match":
            bits.append(f"{name}: {_inr(c['computed'])} &mdash; agrees with the sheet's total")
        elif c.get("status") == "mismatch":
            bits.append(f"{name}: lines add up to {_inr(c['computed'])}, the sheet "
                        f"says {_inr(c.get('sheet') or 0)} &mdash; check before saving")
        else:
            bits.append(f"{name}: lines add up to {_inr(c['computed'])} (no total "
                        f"on the sheet to compare)")
    return "<li>" + "</li><li>".join(bits) + "</li>"


def _memory_stream(*_args, **_kwargs):
    """The stream factory for this one request: a BytesIO, never a temp file."""
    return io.BytesIO()


def _read_upload():
    """
    `(bytes, filename)` of the uploaded workbook, or `SI.Refused` — the BOQ
    importer's order, restated: the Content-Length is checked before the body
    is touched, and the part lands in memory and never in a temporary file.
    """
    limit = SI.MAX_UPLOAD_BYTES + FORM_OVERHEAD_BYTES
    length = request.content_length
    if length is None:
        raise SI.Refused("The upload arrived without a length and was not read. "
                         "Try again from the form.")
    if length > limit:
        raise SI.Refused(f"That upload is {length / 1048576:.1f} MB and the limit "
                         f"is {SI.MAX_UPLOAD_BYTES // 1048576} MB.")
    request.max_content_length = limit
    request._get_file_stream = _memory_stream
    fs = request.files.get("workbook")
    if fs is None or not (fs.filename or "").strip():
        raise SI.Refused("Choose the Excel file to import.")
    data = fs.stream.read(SI.MAX_UPLOAD_BYTES + 1)
    return data, str(fs.filename or "").strip()


def _upload_page(error: str = "") -> str:
    avail = SI.available()
    unavailable = ""
    if not (avail.get("xlsx") or avail.get("xls")):
        unavailable = f'<div class="alert alert-error">&#10007; {P.esc(SI.UNAVAILABLE)}</div>'
    body = f"""
  <div class="page-top">
    <h1>Import <span>Work Order Lines</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('workorder.list_wos')}" class="btn btn-ghost">All Work Orders</a>
      <a href="{url_for('workorder.create_wo')}" class="btn btn-ghost">New work order by hand</a>
    </div>
  </div>
  {_alert(error)}{unavailable}
  <div class="wo-banner">
    Upload the contractor's sheet (.xlsx or .xls). You will see each column
    with a guess at what it holds &mdash; <b>Material rate</b>, <b>Labour
    rate</b>, Quantity and so on &mdash; and confirm it. Then the ordinary New
    Work Order form opens with every line filled in, for you to check, change,
    add to or delete from. <b>Nothing is saved until you press Raise work
    order.</b><br/>
    A sheet with only one rate column fills that rate and leaves the other
    blank and marked: a blank rate is never taken as 0.
  </div>
  <form method="POST" action="{url_for('workorder.import_wo')}" enctype="multipart/form-data">
    <div class="form-section">
      <div class="form-group">
        <label for="workbook">Excel file</label>
        <input type="file" id="workbook" name="workbook" accept=".xlsx,.xls"/>
      </div>
    </div>
    <button type="submit" class="btn">Read the sheet</button>
  </form>"""
    return _shell("Import Work Order Lines", body, WO_FORM_STYLES)


def _tab_name(rec: dict, i: int) -> str:
    try:
        return str((rec.get("sheets") or [])[i].get("name") or f"Sheet {i + 1}")
    except (IndexError, AttributeError):
        return f"Sheet {i + 1}"


def _tab_problems(rec: dict) -> list:
    """`mapping_problems()` per ticked tab (R4), each naming its tab."""
    probs = []
    tabs = _ticked(rec)
    if not tabs:
        probs.append("Tick at least one tab to import.")
    for i in tabs:
        for p in mapping_problems(_tab_grid(rec, i), _mapping_of(rec, i)):
            probs.append(f"{_tab_name(rec, i)}: {p}")
    return probs


def build_import(rec: dict) -> tuple:
    """
    `(rows, tracks, left_out, totals_html)` — every ticked tab built in
    workbook order into ONE list of form rows (R4). The tracks are
    `import_tracks()` over the ticked tabs' mappings (R1), and every tab is
    built for those same tracks.
    """
    tabs = _ticked(rec)
    maps = {i: _mapping_of(rec, i) for i in tabs}
    tracks = import_tracks(list(maps.values()))
    rows, left_out, totals = [], [], ""
    for i in tabs:
        grid, mapping = _tab_grid(rec, i), maps[i]
        si_map = {c: (_TO_SI.get(t, "") if t != SI.UNDECIDED else "")
                  for c, t in mapping.items()}
        result = SI.build(grid, si_map)
        rows += rows_from_build(result, mapping, item_column_values(grid, mapping),
                                tracks=tracks, tab_name=_tab_name(rec, i),
                                left_out=left_out)
        tb = _totals_banner(result.get("totals") or {})
        if tb:
            totals += tb.replace("<li>", f"<li>{P.esc(_tab_name(rec, i))} &mdash; ", 1) \
                if len(tabs) > 1 else tb
    return rows, tracks, left_out, totals


def _preview_page(token: str, rec: dict, problems=None, error: str = "") -> str:
    tabs = _ticked(rec)
    tick_html = ""
    for i, s in enumerate(rec.get("sheets") or []):
        if not s.get("staged") or _tab_grid(rec, i) is None:
            continue
        hidden = " (hidden)" if s.get("visibility") != "visible" else ""
        tick_html += (f'<label class="imp-tab"><input type="checkbox" name="tab" '
                      f'value="{i}"{" checked" if i in tabs else ""}/> '
                      f'{P.esc(s.get("name"))}{hidden}</label>')

    tables = ""
    for i in tabs:
        grid = _tab_grid(rec, i)
        mapping = _mapping_of(rec, i)
        labels = SI.header_labels(grid)
        cols = grid["cols"]
        heads = ""
        for ci, c in enumerate(cols):
            cur = mapping.get(str(c), "")
            opts = "".join(
                f'<option value="{P.esc(k)}"{" selected" if k == cur else ""}>{P.esc(lbl)}</option>'
                for k, lbl in TARGETS)
            if cur == SI.UNDECIDED:
                opts = ('<option value="?" selected>— choose: material or labour? —</option>'
                        + opts)
            heads += (f'<th>{SI.col_letter(c)}<br/><span style="font-weight:400;">'
                      f'{P.esc(labels.get(ci, ""))}</span><br/>'
                      f'<select name="map_{i}_{c}" aria-label="{P.esc(_tab_name(rec, i))} '
                      f'column {SI.col_letter(c)}">{opts}</select></th>')
        start = SI.data_start(grid)
        body_rows = ""
        for rnum, vals in grid["rows"][start:start + PREVIEW_ROWS]:
            cells = ""
            for ci in range(len(cols)):
                v = vals[ci] if ci < len(vals) else None
                text = "" if v is None else str(v)
                if len(text) > PREVIEW_CELL_CHARS:
                    text = text[:PREVIEW_CELL_CHARS] + "…"
                cells += f"<td>{P.esc(text)}</td>"
            body_rows += f'<tr><td class="imp-rn">{int(rnum)}</td>{cells}</tr>'
        no_header = ("" if grid.get("header") else
                     '<div class="alert alert-error">&#10007; No heading row was found '
                     'in the first rows of this tab, so no column could be guessed. '
                     'Choose each column by hand.</div>')
        # R3: what this tab's mapping would leave out, said BEFORE the confirm.
        left = ""
        if not mapping_problems(grid, mapping):
            lo = []
            si_map = {c: (_TO_SI.get(t, "") if t != SI.UNDECIDED else "")
                      for c, t in mapping.items()}
            rows_from_build(SI.build(grid, si_map), mapping,
                            item_column_values(grid, mapping),
                            tracks=import_tracks([_mapping_of(rec, j) for j in tabs]),
                            tab_name=_tab_name(rec, i), left_out=lo)
            left = (f'<ul style="margin:.4rem 0 0 1.1rem;font-size:.82rem;">'
                    f'{_left_out_html(lo)}</ul>' if lo else "")
        tables += f"""
    <div class="form-section" style="overflow-x:auto;">
      <div class="section-title">{P.esc(_tab_name(rec, i))}</div>
      {no_header}{left}
      <table class="imp-grid">
        <thead><tr><th>Row</th>{heads}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>"""

    probs = ""
    if problems:
        probs = ('<div class="alert alert-error">&#10007; Not yet:<ul style="margin:.4rem 0 0 1.2rem;">'
                 + "".join(f"<li>{P.esc(p)}</li>" for p in problems) + "</ul></div>")

    body = f"""
  <div class="page-top">
    <h1>Import <span>Work Order Lines</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('workorder.import_wo')}" class="btn btn-ghost">Upload another file</a>
    </div>
  </div>
  {_alert(error)}{probs}
  <div class="wo-banner">
    <b>{P.esc(rec.get("filename"))}</b> &mdash; tick the tabs this work order is
    built from, and check what each column holds. Only <b>Material rate</b> and
    <b>Labour rate</b> become rates; an amount column is read to check the
    sheet's arithmetic and is never imported. Rows with quantity 0 and no rate
    are left out. The first {PREVIEW_ROWS} rows under each heading are shown.
  </div>
  <form method="POST" action="{url_for('workorder.import_preview', token=token)}">
    <div class="form-section">
      <div class="section-title">Tabs</div>
      <div class="imp-tabs">{tick_html}</div>
      <button type="submit" name="act" value="tabs" class="btn btn-ghost">Show the ticked tabs</button>
    </div>
{tables}
    <button type="submit" name="act" value="confirm" class="btn">Use these columns &rarr;</button>
  </form>"""
    return _shell("Import Work Order Lines", body, WO_FORM_STYLES)


@workorder_bp.route("/import", methods=["GET", "POST"])
def import_wo():
    """Upload a sheet (GET shows the form, POST reads and stages it)."""
    _purge()
    if request.method == "GET":
        return _upload_page()
    try:
        data, filename = _read_upload()
        wb = SI.read(data, filename)
    except SI.Refused as exc:
        return _upload_page(exc.message)
    token = stage(wb, filename, _uid())
    return redirect(url_for("workorder.import_preview", token=token))


@workorder_bp.route("/import/<token>", methods=["GET", "POST"])
def import_preview(token: str):
    """
    The mapping, then the prefilled form. GET shows the columns; a POST with
    `act=sheet` switches the sheet; `act=confirm` checks the mapping and, when
    it is complete, renders the ordinary New Work Order form with every line
    filled in — **nothing is saved here** — and drops the staged upload.
    """
    _purge()
    rec = _own(token)
    if rec is None or _grid(rec) is None:
        return redirect(url_for("workorder.import_wo",
                                msg="That import has expired or is not yours. "
                                    "Upload the file again.", type="error"))
    if request.method == "GET":
        return _preview_page(token, rec)

    # R4: the ticked tabs and one mapping per tab, kept on the staged row on
    # every POST so a re-shown preview keeps what was chosen.
    posted_tabs = []
    for x in request.form.getlist("tab"):
        try:
            i = int(x)
        except ValueError:
            continue
        if _tab_grid(rec, i) is not None and (rec.get("sheets") or [{}] * (i + 1))[i].get("staged"):
            posted_tabs.append(i)
    maps = {}
    for i in sorted(set(posted_tabs)):
        grid = _tab_grid(rec, i)
        if any(k.startswith(f"map_{i}_") for k in request.form):
            maps[str(i)] = clean_mapping(grid, request.form, prefix=f"map_{i}_")
        else:
            maps[str(i)] = _mapping_of(rec, i)       # freshly ticked: its guess
    old = rec.get("mapping") or {}
    if old and all(isinstance(v, str) for v in old.values()):
        old = {str(rec.get("sheet_index") or 0): old}
    rec["mapping"] = {**old, **maps}
    rec["ticked"] = sorted(set(posted_tabs))
    act = request.form.get("act") or ""
    if act != "confirm":
        return _preview_page(token, rec)

    problems = _tab_problems(rec)
    if problems:
        return _preview_page(token, rec, problems)
    rows, tracks, left_out, totals_html = build_import(rec)
    if not [r for r in rows if not r.get("is_header")]:
        return _preview_page(token, rec, ["No priced line could be read under the "
                                          "heading with these columns."])
    if len(rows) > MAX_LINES:
        return _preview_page(token, rec, [
            f"The ticked tabs give {len(rows)} lines and one work order carries "
            f"{MAX_LINES}. Tick fewer tabs, or split the sheet."])

    # Consumed — `boqimport.form()`'s rule: the row goes when the form renders.
    staged().pop(token, None)
    mapped = {t for i in _ticked(rec) for t in _mapping_of(rec, i).values()}
    one = ""
    if tracks != "both":
        one = (f"<li><b>The ticked tabs carry one rate &mdash; this work order "
               f"is {TRACK_LABEL[tracks]}.</b> The other rate is not asked for; "
               f"change it at the top of the form if that is wrong.</li>")
    elif not ({"material_rate", "labour_rate"} & mapped):
        one = ("<li><b>No rate column was chosen.</b> Both rates are blank and "
               "marked on every line.</li>")
    n_need = sum(len(r["need"]) for r in rows)
    n_head = sum(1 for r in rows if r.get("is_header"))
    n_line = len(rows) - n_head
    heads = (f" and {n_head} heading{'' if n_head == 1 else 's'}" if n_head else "")
    tabs_word = ", ".join(P.esc(_tab_name(rec, i)) for i in _ticked(rec))
    banner = f"""
  <div class="wo-banner">
    <b>Imported from {P.esc(rec.get("filename"))}</b> ({tabs_word}) &mdash; {n_line} line{"" if n_line == 1 else "s"}{heads},
    nothing saved yet. Check every line, then press <b>Raise work order</b>.
    <ul>{one}{_left_out_html(left_out)}{totals_html}
      <li>{n_need} field{"" if n_need == 1 else "s"} marked in red must be answered before the save.</li>
    </ul>
  </div>"""
    return _form_page(dict(new_wo_defaults(), tracks=tracks), rows, banner=banner)
