"""
boqimport.py — Import a BOQ from the client's own Excel file  (29 Sep 2026)
==========================================================================
CLIENT_CHANGES.md §0, **thirty-fourth block** — new chargeable scope outside
MG/SF/2026-06, authorised by Manas Gawde on 29 September 2026.

    GET,POST /boq/import                the upload form
    GET,POST /boq/import/<token>        the preview: sheet, column mapping,
                                        flags, totals check, confirm
    GET      /boq/import/<token>/form   /boq/create, PREFILLED — nothing saved

**Nothing is saved until the operator presses Create BOQ on the ordinary form.**
The prefilled page IS `boq.create_boq()`, reached through its one `imported`
seam: the same editor, the same Save, the same duplicate/revision/size checks
and every line minted its `line_id` by `boq._clean_lines()` exactly as a typed
line is. This module never writes to `STORE["boqs"]`.

Import direction — one way, never reversed
------------------------------------------
    boqimport.py ──► sheetimport.py   the reader: bytes in, plain dicts out
    boqimport.py ──► boq.py           create_boq(imported=…), MAX_LINES,
                                      MAX_JSON_BYTES, BOQ_STYLES
    boq.py       ──► boqimport.py     NEVER. /boq/create links here with
                                      url_for("boqimport.upload"), a string.

Both halves are asserted at AST level in `tests/test_import_directions.py`.

The staging collection — `STORE["boq_imports"]`
-----------------------------------------------
The upload is parsed ONCE into a grid of cell values and staged under an
unguessable token (`secrets.token_urlsafe`), because the preview and the
confirm are separate requests and the file itself is never kept:

    {id, token, user_id, created_at, created_ts, filename, sheets, grid,
     sheet_index, mapping, layout, known, confirmed,
     rate_mode, markup}            # 1 October 2026 — "" until posted

* **Owned.** Only the user who uploaded it may open it. Anybody else — and a
  token that has expired or was already used — gets the same 404 page, so the
  answer does not say whether a token exists.
* **Short-lived.** Rows older than 24 hours are purged on EVERY request to this
  module. A user keeps at most three; an upload past that drops their oldest.
* **Consumed.** A confirmed import's row is deleted the moment the prefilled
  form is rendered. ⚠ A **known layout** (below) keeps its row until the purge,
  because the form it goes straight to carries a *Change mapping* link back to
  the preview, and a deleted row has no preview to go back to.
* **The token only ever travels in a PATH.** Never a query string, never a
  hidden field that echoes back into one.

The layout memory — `STORE["import_layouts"]`
---------------------------------------------
    {id = signature, signature, mapping, rate_mode, created_by, created_at,
     use_count}

`sheetimport.signature()` hashes the header texts and their columns. Confirming
a mapping upserts it; an upload whose sheet matches a stored signature skips the
preview and opens the prefilled form directly — ⚠ **unless the sheet reads as
our cost** (1 October 2026): its markup is typed on the preview every time and
never remembered, so a cost layout always stops there.

Selling rates or our cost (1 October 2026)
------------------------------------------
The preview asks what the sheet's rates ARE. **Selling** is v1, unchanged.
**Our cost** needs a Markup % (≥ 0): each sheet rate becomes the BASE rate on
its own track, the markup the ESCALATION %, and the form works out the unit
rate (`editor_model()`). Every footing check still runs on the sheet's own
figures, before the markup. Pre-selected — never decided — by the operator's
own choice, then the layout's last confirmed mode, then the heading's words
(`sheetimport.cost_words()`).

The column picker (6 October 2026)
----------------------------------
CLIENT_CHANGES.md §0, forty-fourth block, R1–R6. The preview lists EVERY
column of each ticked tab with three samples, an Import tick, a target and one
line of advice (`sheetimport.advise()`); the tick and the target arrive set to
the advice (`stage()` stores `sheetimport.advised_mapping()`), and an unticked
column is mapped to "" and ignored completely. Several tabs build into one BOQ,
one section per tab (`build_tabs()`); the names above the heading come through
as editable suggestions, the account matched to the address book
(`detected_names()`, `prefill_of()`). The staged row keeps `sheet_index` and
`mapping` for the primary tab and adds `ticked`, `tab_maps` and `names`. A POST
without the page's `picker` marker reads as v1 did.

The upload never touches disk
-----------------------------
Werkzeug spools any file part over 500 KB to a temporary FILE while it parses
the body — `attachment.py` records that as unavoidable for a form the whole
application shares. It is avoidable for ONE route: form parsing is lazy, the
gate (`auth._gate`) never reads the body, so `_read_upload()` swaps this one
request's stream factory for an in-memory buffer before `request.files` is
first touched. The Content-Length is checked against the cap first, so the
buffer is bounded before a byte is read.
"""

import datetime
import io
import json
import math
import re
import time

from flask import Blueprint, redirect, request, url_for

import auth
import boq as BQ
import branding as B
import importstage as IS   # the staging mechanism, shared with workorder.py (5 Oct 2026)
import pipeline as P
import sheetimport as SI
from address import is_active   # 6 Oct 2026 — the account name matched to the book (R4)
from chrome import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES
from store import STORE

boqimport_bp = Blueprint("boqimport", __name__, url_prefix="/boq/import")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

# Moved into the leaf `importstage.py` with the mechanism (5 October 2026) and
# re-exported here under the same names, which this module passes to it and
# `tests/test_boq_import.py` reads.
STAGE_TTL_SECONDS = IS.STAGE_TTL_SECONDS
MAX_STAGED_PER_USER = IS.MAX_STAGED_PER_USER

# Multipart overhead on top of the file itself: boundaries, part headers and
# the filename. Anything past cap + this is refused from the Content-Length
# header, before the body is read at all.
FORM_OVERHEAD_BYTES = 64 * 1024

# How much of a long cell the preview grid shows. DISPLAY ONLY — the staged
# grid keeps the whole text (up to sheetimport.MAX_CELL_CHARS).
PREVIEW_CELL_CHARS = 140

# The banner lists flags row by row up to this many, then says how many more.
BANNER_FLAG_ROWS = 200

# What the rates on a sheet ARE (1 October 2026, CLIENT_CHANGES.md §0,
# thirty-ninth block). "selling" is v1's reading and the default: one rate per
# track is the selling rate and the base rate stays blank. "cost" is a sheet
# priced at OUR cost (the Iron Mountain sheet, "OWN COST (INR)"): each rate
# goes into the BASE rate on its own track, the markup becomes the escalation
# %, and the BOQ form works the unit rate out from the two.
RATE_MODES = ("selling", "cost")

# The targets a cost sheet may not map: its one rate per track IS the base,
# and its markup IS the escalation.
COST_REFUSED_TARGETS = ("supply_base_rate", "escalation_pct",
                        "install_base_rate", "install_escalation_pct")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _uid() -> str:
    return (auth.current_user() or {}).get("id", "")


def _imports() -> dict:
    return IS.rows("boq_imports")


def _layouts() -> dict:
    return STORE.setdefault("import_layouts", {})


# =============================================================================
# STAGING — purge, own, cap
# =============================================================================
#
# ⚠ The bodies moved into the leaf `importstage.py` on 5 October 2026, verbatim
#   and parameterised by collection, so the work-order importer stages through
#   this SAME mechanism (CLIENT_CHANGES.md §0, forty-second block). These three
#   stay, under their old names, as this module's own calls into it.

def purge(now: float = None) -> int:
    """
    Delete every staged import older than 24 hours. Runs on every request to
    this module. A row whose timestamp cannot be read is deleted too — an
    import nobody can date is an import nobody should be able to open.
    """
    return IS.purge("boq_imports", STAGE_TTL_SECONDS, now)


def _own(token: str):
    """The staged import under `token` if the signed-in user raised it."""
    return IS.own("boq_imports", token, _uid())


def _cap_per_user(uid: str) -> None:
    IS.cap_per_user("boq_imports", uid, MAX_STAGED_PER_USER)


def _grid(rec: dict):
    try:
        return rec["grid"][int(rec.get("sheet_index") or 0)]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _sheet(rec: dict) -> dict:
    try:
        return rec["sheets"][int(rec.get("sheet_index") or 0)]
    except (IndexError, KeyError, TypeError, ValueError):
        return {}


# =============================================================================
# SEVERAL TABS, ONE BOQ (6 October 2026, CLIENT_CHANGES.md §0 forty-fourth
# block, R5) — the work order's pass-3 mechanism, on the BOQ's staged row
# =============================================================================
#
# ⚠ **`sheet_index` and `mapping` keep their meaning**, so every caller and
#   every test that reads them is unchanged: `sheet_index` is the PRIMARY tab
#   (the first ticked, in workbook order) and `mapping` is its mapping.
#   `ticked` lists every tab to build and `tab_maps` holds the others'. A row
#   staged before this pass has neither and reads as its one sheet.

def _tab_grid(rec: dict, i: int):
    try:
        return rec["grid"][int(i)]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _tab_name(rec: dict, i: int) -> str:
    try:
        return str((rec.get("sheets") or [])[int(i)].get("name") or f"Sheet {int(i) + 1}")
    except (IndexError, AttributeError, TypeError, ValueError):
        return f"Sheet {i}"


def _ticked(rec: dict) -> list:
    """The tabs to build, in workbook order, each one staged."""
    raw = rec.get("ticked")
    if not raw:
        raw = [rec.get("sheet_index") or 0]
    out = []
    for i in raw:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if _tab_grid(rec, i) is not None and i not in out:
            out.append(i)
    return sorted(out)


def _default_mapping(rec: dict, i: int) -> dict:
    """
    A freshly ticked tab's mapping: its own confirmed layout when it has one;
    else **the first ticked tab's picks when the headers match** (R5 — the
    same template on every tab, chosen once); else the advice for this tab.
    """
    grid = _tab_grid(rec, i)
    known, _lay = _known_mapping(grid)
    if known is not None:
        return known
    sig = SI.signature(grid)
    for j in _ticked(rec):
        if j != i and sig and SI.signature(_tab_grid(rec, j)) == sig:
            return dict(_mapping_of(rec, j))
    return SI.advised_mapping(grid)


def _mapping_of(rec: dict, i: int) -> dict:
    """Tab `i`'s mapping — `mapping` for the primary tab, `tab_maps` for the
    rest, the default for a tab nobody has mapped yet."""
    if int(i) == int(rec.get("sheet_index") or 0):
        return rec.get("mapping") or {}
    m = (rec.get("tab_maps") or {}).get(str(i))
    return dict(m) if isinstance(m, dict) else _default_mapping(rec, i)


def _tab_problems(rec: dict) -> list:
    """`mapping_problems()` for every ticked tab — named by tab when there
    are several, exactly as before when there is one."""
    tabs = _ticked(rec)
    if not tabs:
        return ["Tick at least one tab to import."]
    probs = []
    for i in tabs:
        grid = _tab_grid(rec, i)
        for p in SI.mapping_problems(grid, SI.clean_mapping(grid, _mapping_of(rec, i))):
            probs.append(f"{_tab_name(rec, i)}: {p}" if len(tabs) > 1 else p)
    return probs


def _all_mappings(rec: dict) -> dict:
    """Every ticked tab's targets in one dict — what the cost-mode refusal
    reads (a base or escalation column on ANY tab is refused in cost mode)."""
    out = {}
    for i in _ticked(rec):
        for c, t in _mapping_of(rec, i).items():
            out[f"{i}:{c}"] = t
    return out


def build_tabs(rec: dict) -> dict:
    """
    `sheetimport.build()` over every ticked tab, MERGED into one result in
    workbook order (R5).

    **One tab is exactly v1's result** — the merge is not run, so a single-tab
    import is byte-for-byte what it was. Several tabs:

    * **each tab is a SECTION** — the sheet's own sections stay sections; a
      section with no title of its own takes the TAB's name;
    * **codes**: the code the sheet writes is kept; a code the reader assigned
      is re-lettered A, B, C … in tab order, skipping every code a sheet wrote;
      a code two tabs both wrote is renamed "A-2" and noted (v1's rule);
    * every line, flag, need and check carries its `tab`, so "Row 12" says
      which tab's row 12;
    * `tab_totals` — each tab's own totals check, against its own total row —
      and `totals`, the COMBINED figure: the sums of the tabs' computed and
      sheet figures, judged within the same rupee.
    """
    tabs = _ticked(rec)
    built = []
    for i in tabs:
        grid = _tab_grid(rec, i)
        res = SI.build(grid, SI.clean_mapping(grid, _mapping_of(rec, i)))
        built.append((i, res))
    if len(built) == 1:
        res = built[0][1]
        res["tab_totals"] = []
        return res

    explicit = set()
    for _i, res in built:
        src = res.get("section_src") or []
        for k, s in enumerate(res["sections"]):
            if k < len(src) and src[k] == "sheet":
                explicit.add(s["code"])
    letters = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    used, sections, lines, flags, needs, checks = set(), [], [], [], [], []
    counts, tab_totals, renames = {}, [], []

    def next_free():
        for l in letters:
            if l not in used and l not in explicit:
                return l
        n = 1
        while f"S{n}" in used:
            n += 1
        return f"S{n}"

    for i, res in built:
        name = _tab_name(rec, i)
        src = res.get("section_src") or []
        remap = {}
        for k, s in enumerate(res["sections"]):
            code = s["code"] if (k < len(src) and src[k] == "sheet") else next_free()
            if code in used:
                base, n = code, 2
                while f"{base}-{n}" in used:
                    n += 1
                renames.append({"row": 0, "col": "", "field": "Tab", "raw": base,
                                "kind": "dup_section", "severity": "amber", "tab": name,
                                "message": SI._FLAG_TEXT["dup_section"].format(
                                    raw=base, new=f"{base}-{n}")})
                code = f"{base}-{n}"
            used.add(code)
            remap[s["code"]] = code
            sections.append({"code": code, "title": s["title"] or name})
        for l in res["lines"]:
            l = dict(l, section=remap.get(l["section"], l["section"]), tab=name)
            lines.append(l)
        flags += [dict(f, tab=name) for f in res["flags"]]
        needs += [dict(n, tab=name) for n in res["needs"]]
        checks += [dict(c, tab=name) for c in res["checks"]]
        for k, v in (res.get("counts") or {}).items():
            counts[k] = counts.get(k, 0) + v
        tab_totals.append((name, res["totals"]))
    flags += renames

    # The combined figure: every tab's computed sum against every tab's sheet
    # total, per track. Judged only where EVERY tab gave a figure for that
    # track — a total missing on one tab is not a match on the rest.
    combined = {}
    for _n, t in tab_totals:
        for c in t.get("checks") or []:
            cur = combined.setdefault(c["track"], {"track": c["track"], "computed": 0.0,
                                                   "sheet": 0.0, "column": c.get("column"),
                                                   "all": True})
            cur["computed"] = round(cur["computed"] + float(c.get("computed") or 0.0), 2)
            if c.get("sheet") is None:
                cur["all"] = False
            else:
                cur["sheet"] = round(cur["sheet"] + float(c["sheet"]), 2)
    out_checks, judged = [], []
    for c in combined.values():
        ok = c.pop("all")
        if not ok:
            c.update(sheet=None, status="no_figure")
        else:
            c["difference"] = round(c["computed"] - c["sheet"], 2)
            c["status"] = ("match" if abs(c["difference"]) <= SI.TOTALS_TOLERANCE
                           else "mismatch")
            judged.append(c["status"])
        out_checks.append(c)
    status = ("no_total" if not judged and all(t.get("status") == "no_total"
                                                for _n, t in tab_totals)
              else "mismatch" if "mismatch" in judged else "match" if judged else "no_figure")
    totals = {"status": status, "row": None, "label": "", "checks": out_checks,
              "total_rows": sum(int(t.get("total_rows") or 0) for _n, t in tab_totals),
              "combined": True}
    return {"sections": sections, "lines": lines, "flags": flags, "needs": needs,
            "checks": checks, "counts": counts, "totals": totals,
            "tab_totals": tab_totals}


# =============================================================================
# NAMES FROM THE SHEET (6 October 2026, R4) — suggestions, confirmed on the
# preview, never saved by themselves
# =============================================================================

def detected_names(rec: dict) -> dict:
    """
    `{"project_name": (text, source), "account_name": (text, source)}` — what
    the sheet suggests, each with the plain-words place it came from ("tab
    “BOQ”, row 2"), from the first ticked tab that has one. Project falls back
    to the PRIMARY tab's name, said as such. ("", "") where there is nothing.
    """
    out = {"project_name": ("", ""), "account_name": ("", "")}
    for i in _ticked(rec):
        names = SI.detect_names(_tab_grid(rec, i))
        where = f"tab “{_tab_name(rec, i)}”"
        if not out["project_name"][0] and names.get("project"):
            p = names["project"]
            out["project_name"] = (p["text"], f"{where}, row {int(p['row'])}")
        if not out["account_name"][0] and names.get("client"):
            c = names["client"]
            out["account_name"] = (c["text"], f"{where}, row {int(c['row'])}")
    if not out["project_name"][0]:
        primary = int(rec.get("sheet_index") or 0)
        out["project_name"] = (_tab_name(rec, primary),
                               f"the name of tab “{_tab_name(rec, primary)}” — "
                               f"nothing above its heading names the project")
    return out


def names_of(rec: dict) -> dict:
    """The names the preview shows in its boxes: what the user typed there
    once they have posted, otherwise the sheet's suggestion."""
    typed = rec.get("names") or {}
    found = detected_names(rec)
    return {k: (typed[k] if k in typed else found[k][0]) for k in found}


_MS = re.compile(r"^\s*m\s*/\s*s\.?\s*", re.I)


def address_match(name: str):
    """
    `(address id, address)` of the ACTIVE address-book entry whose company
    or label is this name — compared by `pipeline.norm_name()` (case and
    spacing), with a leading "M/s" ignored on either side — else `(None,
    None)`. The first by label when several match. Read straight out of
    `STORE["addresses"]`, the one-way read every other reader of the book
    uses; "active" is `address.is_active()`, the book's own predicate.
    """
    want = {P.norm_name(name), P.norm_name(_MS.sub("", name or ""))} - {""}
    if not want:
        return None, None
    book = STORE.get("addresses") or {}
    for aid, a in sorted(book.items(), key=lambda kv: (str(kv[1].get("label") or "").lower(),
                                                       kv[0])):
        if not isinstance(a, dict) or not is_active(a):
            continue
        for f in ("company", "label"):
            v = str(a.get(f) or "")
            if want & ({P.norm_name(v), P.norm_name(_MS.sub("", v))} - {""}):
                return aid, a
    return None, None


def prefill_of(rec: dict) -> dict:
    """
    The plain form fields the prefilled `/boq/create` opens with (R4): the
    project name, and the account — **from the address book when the name
    matches an entry** (the picker pre-selected, its address, GSTIN and
    contact filled exactly as choosing it by hand would), else the sheet's
    name as free text. Nothing is saved: the form is the confirmation.
    """
    names = names_of(rec)
    out = {}
    if names["project_name"]:
        out["project_name"] = names["project_name"]
    acct = names["account_name"]
    if acct:
        out["account_name"] = acct
        aid, a = address_match(acct)
        if aid:
            street = "\n".join(x for x in (a.get("line1"), a.get("line2"), a.get("landmark")) if x)
            out.update({"bill_pick": aid,
                        "account_name": a.get("company") or acct,
                        "contact_person": a.get("contact_name") or "",
                        "bill_addr": street, "bill_city": a.get("city") or "",
                        "bill_state": a.get("state") or "", "bill_pin": a.get("pincode") or "",
                        "bill_gstin": a.get("gstin") or ""})
    return out


def _known_mapping(grid: dict):
    """(mapping, layout record) when this sheet's layout has been confirmed
    before and its stored mapping still applies cleanly; (None, None) else."""
    sig = SI.signature(grid)
    lay = _layouts().get(sig) if sig else None
    if not isinstance(lay, dict):
        return None, None
    mapping = SI.clean_mapping(grid, lay.get("mapping") or {})
    if SI.mapping_problems(grid, mapping):
        return None, None
    return mapping, lay


def stage(wb: dict, filename: str, uid: str) -> tuple:
    """
    Stage a read workbook for `uid` and return `(token, known)`.

    `known` is True when the pre-selected sheet's layout has been confirmed
    before and its mapping still applies: the caller then goes straight to the
    prefilled form. The per-user cap runs here, after the new row is in.

    ⚠ **Never for a cost sheet** (1 October 2026). A sheet whose rates are our
      cost needs a markup, which is the operator's to type every time — it is
      a decision about one job, never remembered — so a known layout that
      reads as cost stops at the preview with its mapping applied.
    """
    token = IS.new_token()
    sel = wb["selected"]
    grid = wb["grid"][sel]
    mapping, layout = _known_mapping(grid)
    known = mapping is not None and _auto_mode(grid)[0] == "selling"
    if mapping is None:
        # ⚠ The ADVICE, not the bare guess (6 October 2026, R1): the tick and
        #   the target arrive set to what `sheetimport.advise()` suggests, a
        #   lone rate column as the selling rate among them.
        mapping = SI.advised_mapping(grid)
    _imports()[token] = {
        "id": token, "token": token, "user_id": uid,
        "created_at": _now(), "created_ts": time.time(),
        "filename": filename, "format": wb["format"],
        "sheets": wb["sheets"], "grid": wb["grid"],
        "sheet_index": sel, "mapping": mapping,
        "layout": SI.signature(grid), "known": known, "confirmed": False,
        # "" until the operator posts a choice; `rate_mode()` reads it.
        "rate_mode": "", "markup": "",
        # 6 October 2026 (R4/R5). `ticked` — the tabs to build, the reader's
        # own pick by default; `tab_maps` — the mapping of every ticked tab
        # OTHER than `sheet_index`, whose mapping stays in `mapping` as it
        # always was; `names` — the project and account names as the user
        # typed them on the preview, empty until they post.
        "ticked": [sel], "tab_maps": {}, "names": {},
    }
    _cap_per_user(uid)
    if known:
        layout["use_count"] = int(layout.get("use_count") or 0) + 1
    return token, known


def _upsert_layout(grid: dict, mapping: dict, mode: str = "selling") -> None:
    """Remember a confirmed mapping — and, from 1 October 2026, whether the
    sheet was confirmed as selling rates or our cost. Never the markup."""
    sig = SI.signature(grid)
    if not sig:
        return
    lay = _layouts().get(sig)
    if isinstance(lay, dict):
        lay["mapping"] = dict(mapping)
        lay["rate_mode"] = mode
        lay["use_count"] = int(lay.get("use_count") or 0) + 1
    else:
        _layouts()[sig] = {"id": sig, "signature": sig, "mapping": dict(mapping),
                           "rate_mode": mode,
                           "created_by": _uid(), "created_at": _now(), "use_count": 1}


# =============================================================================
# SELLING RATES OR OUR COST (1 October 2026)
# =============================================================================

def _auto_mode(grid: dict) -> tuple:
    """
    `(mode, why)` with no choice posted yet: what this sheet's layout was last
    confirmed as, else "cost" when the heading says so
    (`sheetimport.cost_words()`), else "selling". `why` is the plain sentence
    the preview shows beside a pre-selection — "" for the default.
    """
    lay = _layouts().get(SI.signature(grid) or "")
    if isinstance(lay, dict) and lay.get("rate_mode") in RATE_MODES:
        name = "our cost" if lay["rate_mode"] == "cost" else "selling rates"
        return lay["rate_mode"], f"this layout was last confirmed as {name}"
    words = SI.cost_words(grid)
    if words:
        return "cost", "the heading says " + ", ".join(
            f"“{w}” (in “{cell}”)" for w, cell in words)
    return "selling", ""


def rate_mode(rec: dict, grid: dict) -> tuple:
    """`(mode, why)` for a staged import: the operator's own choice once they
    have posted one (`why` is then ""), otherwise `_auto_mode()`."""
    chosen = rec.get("rate_mode")
    if chosen in RATE_MODES:
        return chosen, ""
    return _auto_mode(grid)


def parse_markup(raw):
    """The markup % as a float — a number, 0 or more; a trailing "%" and
    thousands commas are allowed — or None when it is not one."""
    s = str(raw if raw is not None else "").strip()
    s = s[:-1].strip() if s.endswith("%") else s
    s = s.replace(",", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v) or v < 0:
        return None
    return v


def mode_problems(mode: str, markup_raw, mapping: dict) -> list:
    """Why a COST import cannot be confirmed yet — [] when it can, and always
    [] in selling mode, which confirms exactly as it did before."""
    if mode != "cost":
        return []
    probs = []
    if parse_markup(markup_raw) is None:
        probs.append("Type the markup % for this cost sheet — a number, 0 or more — "
                     "or choose Selling rates.")
    taken = [SI.TARGET_LABEL[t] for t in COST_REFUSED_TARGETS if t in mapping.values()]
    if taken:
        probs.append(f"On a cost sheet each track's one rate becomes its base rate and "
                     f"the markup becomes its escalation, so no column can be "
                     f"{' or '.join(taken)}: set it to Ignore, or choose Selling rates.")
    return probs


# =============================================================================
# THE UPLOAD — in memory, bounded, and read once
# =============================================================================

def _memory_stream(*_args, **_kwargs):
    """The stream factory for this one request: a BytesIO, never a temp file."""
    return io.BytesIO()


def _read_upload():
    """
    `(bytes, filename)` of the uploaded workbook, or `SI.Refused`.

    ⚠ **Order is the guarantee.** The Content-Length is checked BEFORE
      `request.files` is touched, because touching it is what makes Werkzeug
      read the body; the stream factory is swapped before it too, so the part
      lands in memory and never in a temporary file.
    """
    limit = SI.MAX_UPLOAD_BYTES + FORM_OVERHEAD_BYTES
    length = request.content_length
    if length is None:
        raise SI.Refused("The upload arrived without a length and was not read. "
                         "Try again from the form.")
    if length > limit:
        raise SI.Refused(f"That upload is {length / 1048576:.1f} MB and the limit "
                         f"is {SI.MAX_UPLOAD_BYTES // 1048576} MB. Save the BOQ "
                         f"sheet on its own as a new workbook and upload that.")
    request.max_content_length = limit
    request._get_file_stream = _memory_stream
    fs = request.files.get("workbook")
    if fs is None or not (fs.filename or "").strip():
        raise SI.Refused("Choose the Excel file to import.")
    data = fs.stream.read(SI.MAX_UPLOAD_BYTES + 1)
    return data, str(fs.filename or "").strip()


# =============================================================================
# LINES — the staged grid shaped for the BOQ editor
# =============================================================================

def _with_notes(remark: str, notes) -> str:
    """The words of every cell the sheet wrote as TEXT in a numeric column —
    "Qty: Included", "Supply rate: #VALUE! in sheet" — appended to a line's
    remark (6 October 2026, CLIENT_CHANGES.md §0, forty-fifth block, A1), so
    nothing the sheet said is lost. After the sheet's own remark and Make."""
    for n in notes or []:
        remark = _with_note(remark, n)
    return remark


def num_text(v) -> str:
    """
    A number as the text the editor holds, EXACTLY.

    The shortest text that reads back as the same float — so 2024.0 is "2024"
    and 7.000000000000001 stays itself. It is never rounded: the client's
    sheets carry figures a formula left with float dust, and rounding here
    would change an agreed rate by a paisa before anybody had looked at it.
    `boq._form_payload_from()` uses `:g`, which keeps six digits; that is its
    business and is not reused here for exactly this reason.
    """
    if v is None:
        return ""
    f = float(v)
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


def _with_make(remark: str, make: str) -> str:
    """The sheet's Make column, kept in the line's remark — "Make: Jindal"."""
    make = (make or "").strip()
    if not make:
        return remark
    bit = f"Make: {make}"
    return f"{remark}; {bit}" if remark else bit


def _with_note(remark: str, note: str) -> str:
    """The sheet's own Remark column (6 October 2026, R1), word for word,
    added to a line's remark — before any "Make: …"."""
    note = (note or "").strip()
    if not note:
        return remark
    return f"{remark}; {note}" if remark else note


def _rowref(l: dict) -> str:
    """Where a line came from, for its flag sentences: "Row 12" — or, when
    several tabs are one BOQ (R5), "Sprinkler · row 12", since every tab has
    a row 12."""
    return f"{l['tab']} · row {l['row']}" if l.get("tab") else f"Row {l['row']}"


def editor_model(result: dict, markup: float = None) -> dict:
    """
    `sheetimport.build()`'s result as the editor's boot model — the shape
    `boq._form_payload_from()` produces, plus UI keys the editor draws and
    `boq._clean_lines()` never reads:

        _flags     the row's notes — an amber chip on the row, never a block
        _row       the source row number, for the chip
        _item_src  "auto" (worked out from the sheet's structure — an "auto"
                   chip) or "sheet"; the item-number source lives HERE only
        _ls        a lump sum — an "LS · review" chip
        _ro        a rate-only line ("RO" in the quantity) — a grey "rate
                   only" chip; quantity 0, its remark says so (1 Oct 2026)
        _cost      the tracks whose base rate came from a COST sheet — the
                   form fills their blank unit rate from its own base +
                   escalation suggestion on load, then drops the key

    ⚠ **6 October 2026** (the §0 forty-fourth block): each row also carries
      `supply_disc_pct` / `install_disc_pct` — the sheet's discount %, blank
      when it gave none (R3) — and the sheet's own Remark column, word for
      word, ahead of any "Make: …" (R1). On a merged several-tab result a
      flag reads "<tab> · row N" (`_rowref()`).

    ⚠ **`markup` is the cost mode (1 October 2026).** None — selling rates —
      is v1's model exactly. A number: on every track where the sheet gave a
      rate (a ₹0 is none), the sheet rate is the BASE rate, the markup is the
      ESCALATION %, and the unit rate is left BLANK with the track in `_cost`,
      so it is worked out by the form's existing base + escalation
      computation (`_BOQ_JS` `suggestRate()`) — this module writes no second
      formula. A track with no rate stays exactly as it was, flags and all.

    ⚠ **A group label is not sent and not folded** (1 October 2026): its words
      are already in front of each of its children's descriptions
      (`sheetimport._group_labels()`); a Make on it goes to the parent's remark,
      as spec text's does.

    ⚠ **Spec text and sub-headings are FOLDED, not sent as lines** (30 Sep
      2026). `build()` derives them as the brief states — a header with no
      item number — but the save refuses every line without one
      (`_clean_lines()`: "Line N needs an item number"), and what the save
      accepts is not this pass's to change. So a spec-text row's words are
      appended to its parent's description, where a BOQ header carries its
      clause anyway, and a sub-heading's to its section's title. A Make on
      either goes into the parent's remark. Nothing on the sheet is dropped.

    ⚠ **As it is (6 October 2026, CLIENT_CHANGES.md §0, forty-fifth block).**
      `_block` (a red quantity the form would not save without) and `_need`
      (the boxes the guided fix rang and the save stopped on) are NO LONGER
      WRITTEN: a blank is what the sheet said, and it saves blank (A3). Every
      cell the sheet wrote as text in a numeric column comes into the line's
      remark as `<Field>: <text>`, after the sheet's own remark and Make (A1,
      `build()`'s `as_remark`) — on a folded spec-text row, into its parent's.

    Every line goes in with a blank `line_id`, so each is minted on save.
    """
    sections = [{"code": s["code"], "title": s["title"], "areas": []}
                for s in result["sections"]]
    sec_at = {s["code"]: k for k, s in enumerate(sections)}
    lines, last = [], {}
    for l in result["lines"]:
        header = bool(l["is_header"])
        if l.get("kind") == "group_label":
            tgt = last.get((l["section"], l["parent_item_no"])) if l["parent_item_no"] else None
            if tgt is not None:
                lines[tgt]["remark"] = _with_notes(_with_make(_with_note(
                    lines[tgt]["remark"], l.get("remark")), l.get("make")), l.get("as_remark"))
            continue
        if header and not l["item_no"] and l.get("kind") in ("spec_text", "subheading"):
            text = (l["description"] or "").strip()
            tgt = last.get((l["section"], l["parent_item_no"])) if l["parent_item_no"] else None
            if tgt is not None:
                row = lines[tgt]
                if text:
                    base = row["description"].rstrip()
                    row["description"] = f"{base}\n{text}" if base else text
                row["remark"] = _with_notes(_with_make(_with_note(row["remark"], l.get("remark")),
                                                       l.get("make")), l.get("as_remark"))
            elif l["section"] in sec_at:
                sec = sections[sec_at[l["section"]]]
                bits = [b for b in (text, f"Make: {l['make']}" if l.get("make") else "") if b]
                if bits:
                    sec["title"] = " — ".join(([sec["title"]] if sec["title"] else []) + bits)
            continue
        row = {
            "line_id": "",
            "item_no": l["item_no"],
            "parent_item_no": l["parent_item_no"],
            "section": l["section"],
            "is_header": header,
            "description": l["description"],
            "remark": _with_notes(_with_make(_with_note("", l.get("remark")), l.get("make")),
                                  l.get("as_remark")),
            "unit": "" if header else l["unit"],
            "area_qty": {},
            "total_qty": "" if header else num_text(l["qty"]),
            "supply_base_rate": "" if header else num_text(l["supply_base_rate"]),
            "supply_escalation_pct": "" if header else num_text(l["escalation_pct"]),
            "supply_rate": "" if header else num_text(l["supply_rate"]),
            "supply_hsn": "", "supply_gst_rate": "",
            "install_base_rate": "" if header else num_text(l["install_base_rate"]),
            "install_escalation_pct": "" if header else num_text(l["install_escalation_pct"]),
            "install_rate": "" if header else num_text(l["install_rate"]),
            "install_sac": "", "install_gst_rate": "",
            # The discount per track (6 October 2026, R3) — blank unless the
            # sheet gave one, and never a 0 the sheet did not write.
            "supply_disc_pct": "" if header else num_text(l.get("supply_disc_pct")),
            "install_disc_pct": "" if header else num_text(l.get("install_disc_pct")),
            "_row": l["row"],
        }
        ref = _rowref(l)
        if l["flags"]:
            row["_flags"] = [f"{ref}: {m}" for m in l["flags"]]
        if l.get("item_src"):
            row["_item_src"] = l["item_src"]
        if l.get("lump_sum"):
            row["_ls"] = True
        if l.get("rate_only") and not header:
            row["remark"] = _with_notes(_with_make(_with_note(SI.RATE_ONLY_REMARK,
                                                              l.get("remark")),
                                                   l.get("make")), l.get("as_remark"))
            row["_ro"] = True
        if markup is not None and not header:
            cost = []
            for t in ("supply", "install"):
                r = l[f"{t}_rate"]
                if r is None or abs(r) < 0.005:
                    continue                          # no rate: as it was
                row[f"{t}_base_rate"] = num_text(r)
                row[f"{t}_escalation_pct"] = num_text(markup)
                row[f"{t}_rate"] = ""
                cost.append(t)
            if cost:
                row["_cost"] = cost
        lines.append(row)
        if l["item_no"]:
            last[(l["section"], l["item_no"])] = len(lines) - 1
    return {"sections": sections, "lines": lines}


def too_large(model: dict) -> str:
    """
    The refusal for a schedule the form could never save, or "".

    Measured the way `boq.create_boq()` measures the POST: the line count
    against `MAX_LINES`, then the UTF-8 bytes of the JSON the editor will post
    against `MAX_JSON_BYTES`. ⚠ **Never truncated**: a BOQ that silently lost
    its last forty lines would print, bill and total as if it were whole.
    """
    n = len(model["lines"])
    size = len(json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if n <= BQ.MAX_LINES and size <= BQ.MAX_JSON_BYTES:
        return ""
    about = BQ.MAX_LINES if size <= BQ.MAX_JSON_BYTES else int(BQ.MAX_JSON_BYTES * n / max(size, 1))
    about = max(1, min(about, BQ.MAX_LINES))
    return (f"This sheet has {n} lines; the BOQ limit is about {about}. Split it — "
            f"save each part as its own sheet and import them as separate BOQs. "
            f"Nothing was cut off: the import stops here rather than drop lines.")


# =============================================================================
# RENDERING
# =============================================================================

IMPORT_STYLES = """
<style>
.imp-card{background:var(--card,#fff);border:1px solid var(--border,#e2e8f0);border-radius:12px;padding:1.1rem 1.2rem;margin-bottom:1rem;}
.imp-card h2{font-size:1rem;margin:0 0 .6rem;}
.imp-note{font-size:.82rem;color:var(--muted,#64748b);margin:.4rem 0 0;}
.imp-file{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;}
.imp-file input[type=file]{flex:1 1 260px;min-width:0;}
.imp-wrap{overflow-x:auto;border:1px solid var(--border,#e2e8f0);border-radius:10px;}
.imp-grid{border-collapse:collapse;font-size:.78rem;min-width:100%;}
.imp-grid th,.imp-grid td{border-bottom:1px solid var(--border,#e2e8f0);padding:.3rem .45rem;vertical-align:top;text-align:left;white-space:pre-wrap;max-width:22rem;}
.imp-grid thead th{background:#f8fafc;position:sticky;top:0;}
.imp-grid .imp-rn{color:var(--muted,#64748b);font-variant-numeric:tabular-nums;white-space:nowrap;}
.imp-grid tr.imp-hdr td{background:#eef2ff;font-weight:600;}
.imp-grid td.is-flag{background:#fef3c7;}
.imp-grid td.is-red{background:#fee2e2;}
.imp-grid select{font-size:.76rem;max-width:12rem;}
.imp-grid select.is-undecided{border-color:#dc2626;background:#fef2f2;}
.imp-flags{margin:.3rem 0 0 1.1rem;padding:0;font-size:.8rem;}
.imp-flags li{margin:.15rem 0;}
.imp-flags li.is-red{color:#b91c1c;}
.imp-stats{display:flex;gap:1.2rem;flex-wrap:wrap;font-size:.85rem;}
.imp-stats b{font-size:1.05rem;}
.imp-ok{color:#15803d;font-weight:600;}
.imp-bad{color:#b91c1c;font-weight:600;}
.imp-banner{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:.8rem 1rem;margin-bottom:1rem;font-size:.86rem;}
.imp-banner.has-red{border-color:#fca5a5;background:#fff7f7;}
.imp-banner details{margin-top:.5rem;}
.imp-banner summary{cursor:pointer;font-weight:600;}
.imp-actions{display:flex;gap:.7rem;flex-wrap:wrap;justify-content:flex-end;margin-top:1rem;}
.imp-summary{display:grid;gap:.6rem;margin-top:.7rem;}
.imp-group{border:1px solid var(--border,#e2e8f0);border-radius:10px;padding:.6rem .8rem;background:#fff;}
.imp-group.is-red{border-color:#fca5a5;background:#fff7f7;}
.imp-group h3{font-size:.9rem;margin:0;font-weight:600;}
.imp-group h3 b{font-size:1rem;}
.imp-group.is-red h3 b{color:#b91c1c;}
.imp-group summary{cursor:pointer;font-size:.88rem;}
.imp-tag{display:inline-block;margin-left:.3rem;padding:0 .4rem;border-radius:999px;font-size:.68rem;font-weight:700;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe;vertical-align:middle;}
.imp-need-link{color:#b91c1c;font-weight:600;}
.imp-linkish{background:none;border:0;padding:0;font:inherit;cursor:pointer;text-decoration:underline;}
.imp-mode .form-group{max-width:14rem;margin-top:.7rem;}
.imp-warn{color:#b45309;font-weight:600;}
.imp-tabs{display:flex;gap:.4rem 1.2rem;flex-wrap:wrap;font-size:.86rem;}
.imp-tab{display:inline-flex;gap:.35rem;align-items:center;}
.imp-pick td{vertical-align:middle;}
.imp-pick .imp-samp{color:var(--muted,#64748b);max-width:18rem;}
.imp-pick .imp-adv{font-size:.76rem;max-width:20rem;}
.imp-pick .imp-use{text-align:center;}
.imp-pick tr.imp-off td{color:var(--muted,#64748b);background:#f8fafc;}
.imp-names .fg2{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:.8rem 1.2rem;}
.imp-names .imp-note{margin-top:.25rem;}
</style>
"""

# The preview's "Rates on this sheet are" card (1 October 2026): shows the
# Markup % box while "Our cost" is chosen, makes it required then, and warns
# live at 0. A plain string, not an f-string, so its braces are written once.
# The server is the authority: `mode_problems()` refuses a missing markup.
_MODE_JS = """
<script>
function impMode() {
  var cost = document.getElementById('rm-cost');
  var on = !!(cost && cost.checked);
  var box = document.getElementById('imp-markup');
  var inp = document.getElementById('markup');
  var zero = document.getElementById('imp-zero');
  var note = document.getElementById('imp-costcheck');
  if (box) box.style.display = on ? '' : 'none';
  if (inp) inp.required = on;
  var v = inp ? String(inp.value).trim() : '';
  if (zero) zero.style.display = (on && v !== '' && Number(v) === 0) ? '' : 'none';
  if (note) note.style.display = on ? '' : 'none';
}
</script>
"""


def _page(title: str, body: str) -> str:
    """A finished page. Never Jinja-rendered (ABOUT.md §1)."""
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{BQ.BOQ_STYLES}{IMPORT_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE}</p></footer>
</main>
</body></html>"""


def _not_found():
    """
    The one answer for a token that is not yours, has expired, or was used.

    Returned with status 404 DIRECTLY rather than through `abort(404)`: the
    app-wide 404 handler redirects to the dashboard, which would tell the
    client this request succeeded and would lose the sentence below.
    """
    body = f"""
  <div class="page-top"><h1>Import <span>not found</span></h1></div>
  <div class="imp-card">
    <p>This import is not available. It may have expired (an upload is kept for
    24 hours), it may already have been opened into the BOQ form, or it belongs
    to someone else.</p>
    <p class="imp-note">Nothing was saved. Upload the file again to start over.</p>
    <div class="imp-actions">
      <a class="btn" href="{url_for('boqimport.upload')}">Upload an Excel BOQ</a>
    </div>
  </div>"""
    return _page("Import not found", body), 404


def _upload_page(error: str = "") -> str:
    avail = SI.available()
    alert = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>' if error else ""
    missing = [k for k, ok in avail.items() if not ok]
    unavailable = ""
    if missing:
        unavailable = (f'<div class="alert alert-error">&#10007; '
                       f'{P.esc(SI.UNAVAILABLE)} (missing: {P.esc(", ".join(missing))})</div>')
    body = f"""
  {alert}{unavailable}
  <div class="page-top">
    <h1>Import <span>BOQ from Excel</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.create_boq')}" class="btn btn-ghost">&#8592; Back to Create BOQ</a>
    </div>
  </div>
  <div class="imp-card">
    <h2>Your own BOQ workbook, any layout</h2>
    <form method="POST" enctype="multipart/form-data" class="imp-file">
      <input type="file" name="workbook" accept=".xlsx,.xls" required/>
      <button class="btn" type="submit">Upload</button>
    </form>
    <p class="imp-note">An <b>.xlsx</b> or <b>.xls</b> file up to
    {SI.MAX_UPLOAD_BYTES // 1048576} MB. A workbook with macros (.xlsm) is refused
    &mdash; save it as .xlsx first. The file is read once and not kept.</p>
    <p class="imp-note">You will see every column of the sheet with three sample
    values and a suggestion of what to take &mdash; already ticked &mdash; and you
    choose which columns to import; several tabs can go into one BOQ, one
    section each. Then the ordinary <b>Create BOQ</b> form opens with every line
    filled in. <b>Nothing is saved until you press Create BOQ.</b></p>
    <p class="imp-note">Only the <b>total</b> quantity is read; floor or area
    columns are left out. Where the sheet gives one rate per line, that rate is
    taken as the <b>selling</b> rate and the base rate is left blank for you to
    fill in later &mdash; unless you mark the sheet&rsquo;s rates as <b>our
    cost</b> on the next page, with a markup.</p>
  </div>"""
    return _page("Import BOQ", body)


def _cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return num_text(v)
    s = str(v)
    if len(s) > PREVIEW_CELL_CHARS:
        s = s[:PREVIEW_CELL_CHARS - 1] + "…"
    return s


def _target_select(col: int, current: str, tab: int = None) -> str:
    """One column's target dropdown. Named `map_<tab>_<column>` on the column
    picker (6 October 2026, R1/R5) — one per column per ticked tab; ticking
    it on is `use_<tab>_<column>`. A target chosen ticks its box (`impTick`)."""
    opts = []
    if current == SI.UNDECIDED:
        opts.append(f'<option value="{SI.UNDECIDED}" selected>'
                    f'&#8212; choose: Supply or Installation &#8212;</option>')
    for key, label in SI.TARGETS:
        sel = " selected" if key == current else ""
        opts.append(f'<option value="{P.esc(key)}"{sel}>{P.esc(label)}</option>')
    cls = ' class="is-undecided"' if current == SI.UNDECIDED else ""
    name = f"map_{int(col)}" if tab is None else f"map_{int(tab)}_{int(col)}"
    hook = "" if tab is None else f' onchange="impTick(this,&#39;use_{int(tab)}_{int(col)}&#39;)"'
    return (f'<select name="{name}"{cls}{hook} aria-label="Column '
            f'{SI.col_letter(col)}">{"".join(opts)}</select>')


def _money(v) -> str:
    return "&mdash;" if v is None else f"&#8377;&nbsp;{float(v):,.2f}"


def totals_block(result: dict) -> str:
    """
    The totals check as the preview and the form's banner show it. One tab:
    v1's one line, exactly. Several tabs (R5): the COMBINED figure first, then
    each tab's own check against its own total row.
    """
    tabs = result.get("tab_totals") or []
    if not tabs:
        return _totals_html(result["totals"])
    each = "".join(f"<li>{P.esc(name)} &mdash; {_totals_html(t)}</li>" for name, t in tabs)
    return (f"{_totals_html(result['totals'])}"
            f'<ul class="imp-flags">{each}</ul>')


def _totals_html(totals: dict) -> str:
    status = totals.get("status")
    if totals.get("combined"):
        # Several tabs: the sums of every tab's figures (R5).
        if status == "no_total":
            return "Combined totals check: <b>no grand total found</b> on any tab."
        parts = []
        track_name = {"supply": "Supply", "install": "Installation",
                      "both": "Supply + Installation"}
        for c in totals.get("checks") or []:
            name = track_name.get(c.get("track"), "")
            if c.get("status") == "no_figure":
                parts.append(f"{name}: computed {_money(c.get('computed'))}, not every "
                             f"tab gives a total to compare")
            elif c.get("status") == "match":
                parts.append(f'{name}: <span class="imp-ok">matches</span> '
                             f"{_money(c.get('sheet'))}")
            else:
                parts.append(f'{name}: <span class="imp-bad">does not match</span> &mdash; '
                             f"the tabs' totals {_money(c.get('sheet'))}, quantity &times; rate "
                             f"{_money(c.get('computed'))} (difference "
                             f"{_money(c.get('difference'))})")
        return "Combined totals check, every ticked tab: " + ("; ".join(parts) or "no rate mapped") + "."
    if status == "no_total":
        n = totals.get("total_rows") or 0
        why = (f" ({n} total row{'s' if n != 1 else ''} on the sheet, none marked "
               f"Grand Total)" if n else "")
        return f"Totals check: <b>no grand total found</b> on the sheet{why}."
    parts = []
    track_name = {"supply": "Supply", "install": "Installation", "both": "Supply + Installation"}
    for c in totals.get("checks") or []:
        name = track_name.get(c.get("track"), "")
        if c.get("status") == "no_figure":
            parts.append(f"{name}: computed {_money(c.get('computed'))}, "
                         f"no figure on the total row")
        elif c.get("status") == "match":
            parts.append(f'{name}: <span class="imp-ok">matches</span> '
                         f"{_money(c.get('sheet'))}")
        else:
            parts.append(f'{name}: <span class="imp-bad">does not match</span> &mdash; '
                         f"sheet {_money(c.get('sheet'))}, quantity &times; rate "
                         f"{_money(c.get('computed'))} (difference "
                         f"{_money(c.get('difference'))})")
    where = f" (row {int(totals['row'])}, “{P.esc(totals.get('label'))}”)" if totals.get("row") else ""
    if not parts:
        return f"Totals check: a grand total row was found{where} but no rate is mapped to check it against."
    return f"Totals check{where}: " + "; ".join(parts) + "."


def _flag_list(flags: list, limit: int = BANNER_FLAG_ROWS) -> str:
    items = []
    for f in flags[:limit]:
        where = f"Row {int(f['row'])}" + (f", column {P.esc(f['col'])}" if f.get("col") else "")
        if f.get("tab"):
            # Several tabs, one BOQ (R5): every tab has a row 12.
            where = (f"{P.esc(f['tab'])}" + (f" &middot; row {int(f['row'])}" if f.get("row") else "")
                     + (f", column {P.esc(f['col'])}" if f.get("col") else ""))
        raw = f" (“{P.esc(f['raw'])}”)" if f.get("raw") and f.get("kind") in ("text", "na", "error") else ""
        cls = ' class="is-red"' if f.get("severity") == "red" else ""
        items.append(f"<li{cls}>{where} &middot; {P.esc(f['field'])}: "
                     f"{P.esc(f['message'])}{raw}</li>")
    more = len(flags) - limit
    if more > 0:
        items.append(f"<li>&hellip; and {more} more.</li>")
    return f'<ul class="imp-flags">{"".join(items)}</ul>' if items else ""


def _where(f: dict) -> str:
    """"Row 12" — or "Sprinkler · row 12" when several tabs are one BOQ."""
    row = f"row {int(f['row'])}" if f.get("row") else ""
    if f.get("tab"):
        return P.esc(f["tab"]) + (f" &middot; {row}" if row else "")
    return row[:1].upper() + row[1:]


FIELD_NAME = {"total_qty": "Quantity", "supply_rate": "Supply rate",
              "install_rate": "Installation rate", "rate": "Rate",
              "item_no": "Item No.", "description": "Description"}
COL_NAME = {"supply_amount": "supply", "install_amount": "installation", "amount": "amount"}

# The grouped summary lists at most this many entries per group, then counts.
SUMMARY_ROWS = 60

# What the preview posts to confirm AND land on one field: "confirm@<line>.<field>".
_GOTO = re.compile(r"^\d{1,4}\.[a-z_]{1,20}$")


def summary_html(result: dict, model: dict, on_form: bool,
                 unit_mapped: bool = True) -> str:
    """
    The import, GROUPED (30 September 2026) — what used to be one line per
    flagged cell. The groups, each counted:

      Nothing blocks the save      6 October 2026 (the forty-fifth block, A3):
                                   a QUIET count of the lines with no rate and
                                   no quantity — it replaced "N fields need
                                   you", every blank the import asked about
      N lines where the sheet's    the sheet's amount (or net rate) against what
        figure is not the BOQ's    the BOQ computes, both figures — the rate
                                   kept as the sheet has it (A2)
      N cells of text …            text where a number belongs, kept in the
                                   line's remark (A1)
      N item numbers filled in     from the sheet's structure — "auto" chips
      N lump sums                  an amount alone, taken as 1 LS — review
      N subtotals checked          every total row, footed; which do not add up

    and, folded, any other note the reader left (a rate cell it could not
    read, a cut cell, a renamed section, a row below the grand total, a number
    in the Make column) so nothing it said is hidden.

    From 1 October 2026, a fifth group — *N rate-only lines* — drawn only
    when the sheet has one, so a sheet without "RO" reads as it did.

    `unit_mapped` False — no column is mapped to Unit — adds one line (30
    September 2026): *This sheet has no Unit column: N lines have no unit
    (fill on the form)*. A note, not a flag: a blank unit never blocks the
    save, and nothing is inferred from a description. The default leaves the
    summary exactly as it was.

    `on_form` is kept for its callers; nothing in the summary links to a
    field any more — there is no field to send anybody to.
    """
    lines = model["lines"]
    flags = result.get("flags") or []

    # ── As it is (6 October 2026, CLIENT_CHANGES.md §0, forty-fifth block) ──
    # What used to be "N fields need you" — every blank the import asked
    # somebody to fill, each a link the form then stopped on — is a QUIET
    # count now: a blank comes in blank, and nothing stops the save (A3).
    body = [ln for ln in lines if not ln.get("is_header")]

    def _blank(ln, key):
        return not str(ln.get(key) if ln.get(key) is not None else "").strip()

    n_rate = sum(1 for ln in body
                 if all(_blank(ln, f"{t}_rate") and t not in (ln.get("_cost") or [])
                        for t in ("supply", "install")))
    n_qty = sum(1 for ln in body if _blank(ln, "total_qty"))
    quiet = BQ.blank_summary(n_rate, n_qty)
    n_formula = int((result.get("counts") or {}).get("formula_blank") or 0)
    formula = (f' {n_formula} formula cell{"s" if n_formula != 1 else ""} had no saved '
               f'value and came in blank &mdash; if the sheet shows figures there, open '
               f'it in Excel, save it, and import again.' if n_formula else "")
    parts = [
        f'<div class="imp-group" id="imp-blanks"><h3>Nothing blocks the save.</h3>'
        f'<p class="imp-note">Every cell comes in as the sheet has it: a blank stays '
        f'blank and a 0 stays 0.'
        + (f" {P.esc(quiet)}." if quiet else "") + formula + "</p></div>"]

    # The sheet's own figures against what the BOQ will compute (A2) — amber,
    # never a block, the rate kept as the sheet has it.
    sums = [f for f in flags if f.get("kind") in ("as_mismatch", "as_no_rate_amt",
                                                  "as_net", "mismatch_both")]
    if sums:
        items = "".join(f"<li>{_where(f)}: {P.esc(f['message'])}</li>"
                        for f in sums[:SUMMARY_ROWS])
        if len(sums) > SUMMARY_ROWS:
            items += f"<li>&hellip; and {len(sums) - SUMMARY_ROWS} more.</li>"
        parts.append(
            f'<div class="imp-group" id="imp-sums"><h3><b>{len(sums)}</b> line'
            f'{"s" if len(sums) != 1 else ""} where the sheet&rsquo;s figure is not what '
            f'the BOQ computes <span class="imp-tag">review</span></h3>'
            f'<p class="imp-note">Nothing was changed: the rate stays as the sheet has '
            f'it, and the BOQ&rsquo;s amount is quantity &times; rate, which is what an RA '
            f'bill bills.</p><ul class="imp-flags">{items}</ul></div>')

    # Text where a number belongs (A1): kept in the line's remark, word for word.
    texts = [f for f in flags if f.get("kind") == "as_remark"]
    if texts:
        items = "".join(f"<li>{_where(f)} &middot; {P.esc(f['field'])}: "
                        f"&ldquo;{P.esc(f['raw'])}&rdquo;</li>" for f in texts[:SUMMARY_ROWS])
        if len(texts) > SUMMARY_ROWS:
            items += f"<li>&hellip; and {len(texts) - SUMMARY_ROWS} more.</li>"
        parts.append(
            f'<details class="imp-group" id="imp-texts"><summary><b>{len(texts)}</b> '
            f'cell{"s" if len(texts) != 1 else ""} of text where a number belongs, kept '
            f'in the line&rsquo;s remark</summary><p class="imp-note">The figure is left '
            f'blank and the words go into the remark as <i>Qty: Included</i> &mdash; '
            f'nothing the sheet said is lost.</p><ul class="imp-flags">{items}</ul></details>')

    auto = [(i, ln) for i, ln in enumerate(lines) if ln.get("_item_src") == "auto"]
    sheet_n = (result.get("counts") or {}).get("sheet_items", 0)
    eg = ", ".join(P.esc(ln["item_no"]) for _i, ln in auto[:12]) + ("&hellip;" if len(auto) > 12 else "")
    parts.append(
        f'<div class="imp-group"><h3><b>{len(auto)}</b> item number'
        f'{"s" if len(auto) != 1 else ""} filled in from the sheet&rsquo;s structure '
        f'<span class="imp-tag">review</span></h3>'
        + (f'<p class="imp-note">A priced row with no number of its own under a numbered '
           f'line becomes its sub-item &mdash; {eg}. Each is marked <b>auto</b> on the form.'
           + (f' {sheet_n} more took the sub-label the sheet wrote.' if sheet_n else "")
           + "</p>" if auto else
           (f'<p class="imp-note">{sheet_n} sub-item number{"s" if sheet_n != 1 else ""} '
            f'came from the sheet as written.</p>' if sheet_n else "")) + "</div>")

    ls = [(i, ln) for i, ln in enumerate(lines) if ln.get("_ls")]
    ls_items = "".join(
        f"<li>Row {int(ln.get('_row') or 0)} &middot; item {P.esc(ln['item_no']) or '&mdash;'}: "
        f"{P.esc((ln.get('_flags') or [''])[-1])}</li>" for _i, ln in ls[:SUMMARY_ROWS])
    parts.append(
        f'<div class="imp-group"><h3><b>{len(ls)}</b> lump sum{"s" if len(ls) != 1 else ""} '
        f'<span class="imp-tag">review</span></h3>'
        + (f'<ul class="imp-flags">{ls_items}</ul>' if ls else "") + "</div>")

    # Rate-only lines (1 October 2026) — drawn only when there are some, so a
    # sheet without "RO" in it reads exactly as it did.
    ro = [ln for ln in lines if ln.get("_ro")]
    if ro:
        # As it is (A3): a rate-only line with no rate is a line with no rate —
        # said, not asked about.
        ro_none = sum(1 for ln in ro if _blank(ln, "supply_rate") and _blank(ln, "install_rate")
                      and not ln.get("_cost"))
        eg = ", ".join(P.esc(ln["item_no"]) for ln in ro[:12]) + ("&hellip;" if len(ro) > 12 else "")
        parts.append(
            f'<div class="imp-group" id="imp-ro"><h3><b>{len(ro)}</b> rate-only line'
            f'{"s" if len(ro) != 1 else ""}</h3><p class="imp-note">&ldquo;RO&rdquo; in the '
            f'quantity &mdash; {eg}. Each comes in at quantity 0 with its rates kept, marked '
            f'<b>rate only</b>, and says so in its remark.'
            + (f' {ro_none} of them ha{"ve" if ro_none != 1 else "s"} no rate on either track '
               f'and come{"" if ro_none != 1 else "s"} in with the rate blank.' if ro_none else "")
            + '</p></div>')

    if not unit_mapped:
        nu = sum(1 for ln in lines
                 if not ln.get("is_header") and not str(ln.get("unit") or "").strip())
        if nu:
            parts.append(
                f'<div class="imp-group" id="imp-units"><h3>This sheet has no Unit column: '
                f'<b>{nu}</b> line{"s have" if nu != 1 else " has"} no unit '
                f'(fill on the form)</h3></div>')

    checks = result.get("checks") or []
    bad = [c for c in checks if c.get("status") != "match"]
    if not checks:
        chk = '<p class="imp-note">No subtotal or total rows with a figure were found.</p>'
    elif not bad:
        chk = '<p class="imp-note"><span class="imp-ok">All of them add up.</span> ' + ", ".join(
            f"row {int(c['row'])} ({P.esc(c['kind'])})" for c in checks[:SUMMARY_ROWS]) + "</p>"
    else:
        rows = []
        for c in bad[:SUMMARY_ROWS]:
            figs = "; ".join(f"{COL_NAME.get(f['col'], P.esc(f['col']))}: sheet {_money(f['sheet'])}, "
                             f"the lines above {_money(f['lines'])}" for f in c["figures"])
            tab = f"{P.esc(c['tab'])} &middot; " if c.get("tab") else ""
            rows.append(f'<li class="is-red">{tab}Row {int(c["row"])} &ldquo;{P.esc(c.get("label"))}&rdquo; '
                        f'does not add up &mdash; {figs}</li>')
        chk = (f'<p class="imp-note"><span class="imp-bad">{len(bad)} do not add up</span>; '
               f'{len(checks) - len(bad)} do.</p><ul class="imp-flags">{"".join(rows)}</ul>')
    parts.append(f'<div class="imp-group"><h3><b>{len(checks)}</b> subtotal'
                 f'{"s" if len(checks) != 1 else ""} checked</h3>{chk}</div>')

    covered = {"no_qty", "no_rate_amt", "no_rate", "mismatch", "no_item", "no_desc",
               "lump_sum", "total_bad", "ro_no_rate",
               # 6 October 2026 (R3): the discount's two blocking checks.
               "mismatch_net", "net_mismatch",
               # …and the as-is notes (the forty-fifth block), grouped above.
               "as_remark", "as_mismatch", "as_no_rate_amt", "as_net", "mismatch_both"}
    notes = [f for f in result.get("flags") or [] if f.get("kind") not in covered]
    if notes:
        parts.append(f'<details class="imp-group"><summary><b>{len(notes)}</b> other note'
                     f'{"s" if len(notes) != 1 else ""} from the reader</summary>'
                     f'{_flag_list(notes)}</details>')
    return f'<div class="imp-summary">{"".join(parts)}</div>'


def _mode_card(mode: str, why: str, markup_raw: str) -> str:
    """The "Rates on this sheet are" card (1 October 2026) — the
    quotation form's own radio row (`.tax-options`) and `.form-group`."""
    cost = mode == "cost"
    mk = parse_markup(markup_raw)
    reason = (f'<p class="imp-note">Pre-selected: {P.esc(why)}. Change it either way.</p>'
              if why else "")
    return f"""
    <div class="imp-card imp-mode">
      <h2>Rates on this sheet are</h2>
      <div class="tax-options" style="margin-bottom:.2rem;">
        <label class="tax-opt">
          <input type="radio" name="rate_mode" value="selling" id="rm-selling"
                 {"" if cost else "checked"} onchange="impMode()"/> Selling rates
        </label>
        <label class="tax-opt">
          <input type="radio" name="rate_mode" value="cost" id="rm-cost"
                 {"checked" if cost else ""} onchange="impMode()"/> Our cost
        </label>
      </div>
      {reason}
      <div id="imp-markup" class="form-group"{"" if cost else ' style="display:none;"'}>
        <label for="markup">Markup %</label>
        <input type="number" id="markup" name="markup" min="0" step="any"
               value="{P.esc(markup_raw)}"{" required" if cost else ""} oninput="impMode()"/>
      </div>
      <p id="imp-zero" class="imp-note imp-warn"{"" if (cost and mk == 0) else ' style="display:none;"'}>
        &#9888; At 0% the sale price will equal cost.</p>
      <p class="imp-note"><b>Our cost</b>: each rate goes into the <b>base rate</b> on its
      own track, the markup becomes the <b>escalation %</b> on every priced line, and the
      BOQ form works the unit rate out from the two &mdash; editable per line. The printed
      BOQ never shows the base rate or the escalation. <b>Selling rates</b>: each rate is
      the unit rate and the base rate stays blank, as before.</p>
    </div>{_MODE_JS}"""


def _trunc(s: str, n: int) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1] + "…"


# A target chosen in a dropdown ticks that column's Import box: choosing what a
# column is IS choosing to take it. Unticking is left to the user. A plain
# string, so its braces are written once.
_PICK_JS = """
<script>
function impTick(sel, name) {
  var box = document.getElementsByName(name)[0];
  if (box && sel.value !== '') box.checked = true;
}
</script>
"""


def _picker_html(rec: dict, i: int, several: bool) -> str:
    """
    One tab's COLUMN PICKER (6 October 2026, CLIENT_CHANGES.md §0 forty-fourth
    block, R1): every non-empty column — its letter, its heading, three sample
    values, an **Import** tick, the target and one line of advice.

    The tick and the target arrive set to the ADVICE (`stage()` stores it);
    after a POST they are what the user chose. An unticked column shows what
    the advice would take, so ticking it back takes that. ⚠ The advice and the
    headings are escaped here, and the advice never quotes a cell.
    """
    grid = _tab_grid(rec, i)
    mapping = SI.clean_mapping(grid, _mapping_of(rec, i))
    advice = SI.advise_mapping(grid)
    labels = SI.header_labels(grid)
    rows = []
    for ci, c in enumerate(grid["cols"]):
        cur = mapping.get(str(c), "")
        adv_t, adv_r = advice.get(str(c), ("", ""))
        on = cur != ""
        shown = cur if on else adv_t
        samples = " &middot; ".join(P.esc(_trunc(s, 40))
                                    for s in SI.column_samples(grid, ci)) or "&mdash;"
        rows.append(
            f'<tr class="{"" if on else "imp-off"}">'
            f'<td class="imp-rn">{SI.col_letter(c)}</td>'
            f'<td class="imp-head">{P.esc(_trunc(labels.get(ci, ""), 60)) or "&mdash;"}</td>'
            f'<td class="imp-samp">{samples}</td>'
            f'<td class="imp-use"><input type="checkbox" name="use_{int(i)}_{int(c)}" value="1"'
            f'{" checked" if on else ""} aria-label="Import column {SI.col_letter(c)}"/></td>'
            f'<td>{_target_select(c, shown, tab=i)}</td>'
            f'<td class="imp-adv">{P.esc(adv_r)}</td></tr>')
    no_header = ("" if grid.get("header") else
                 '<p class="imp-note">No heading row was recognised on this tab, so every '
                 'column starts unticked and the lines start at the top. Tick and choose '
                 'what each column holds.</p>')
    title = f" &mdash; {P.esc(_tab_name(rec, i))}" if several else ""
    return f"""
    <div class="imp-card">
      <h2>What each column holds{title}</h2>
      {no_header}
      <div class="imp-wrap">
        <table class="imp-grid imp-pick">
          <thead><tr><th>Col</th><th>Heading</th><th>On the sheet</th><th>Import</th>
          <th>Take it as</th><th>Advice</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
      <p class="imp-note">Only a <b>ticked</b> column is read &mdash; an unticked one is
      ignored completely: never imported, never asked about. The advice is already ticked
      and chosen; change either. A lone rate column is suggested as your <b>selling</b>
      rate, and the base rate then stays blank &mdash; unless the rates are <b>Our cost</b>,
      above.</p>
    </div>"""


def _names_html(rec: dict) -> str:
    """The project and account names from the sheet (R4) — editable boxes,
    each saying where its suggestion came from, and whether the account
    matches an address-book entry (it is then selected on the form)."""
    found = detected_names(rec)
    shown = names_of(rec)
    typed = rec.get("names") or {}

    def source(key):
        text, where = found[key]
        if key in typed and typed[key] != text:
            return "As you typed it."
        if not text:
            return "Nothing above the heading names one &mdash; type it here or on the form."
        return f"From the sheet: {P.esc(where)}."

    match = ""
    if shown["account_name"]:
        aid, a = address_match(shown["account_name"])
        if aid:
            match = (f' Matches the address-book entry &ldquo;{P.esc(a.get("label"))}&rdquo;'
                     f' &mdash; it will be selected on the form, its address filled.')
    return f"""
    <div class="imp-card imp-names">
      <h2>Names from the sheet</h2>
      <div class="fg2">
        <div class="form-group">
          <label for="project_name">Project name</label>
          <input type="text" id="project_name" name="project_name" maxlength="200"
                 value="{P.esc(shown["project_name"])}"/>
          <p class="imp-note">{source("project_name")}</p>
        </div>
        <div class="form-group">
          <label for="account_name">Account / bill-to name</label>
          <input type="text" id="account_name" name="account_name" maxlength="200"
                 value="{P.esc(shown["account_name"])}"/>
          <p class="imp-note">{source("account_name")}{match}</p>
        </div>
      </div>
      <p class="imp-note">Suggestions only &mdash; they fill the Create BOQ form, where you
      can still change them. Nothing is saved until you press Create BOQ.</p>
    </div>"""


def _preview_page(token: str, rec: dict, error: str = "", problems=None) -> str:
    grid = _grid(rec)
    tabs = _ticked(rec)
    several = len(tabs) > 1
    result = build_tabs(rec)
    mode, why = rate_mode(rec, grid)
    if problems is None:
        problems = (_tab_problems(rec)
                    + mode_problems(mode, rec.get("markup"), _all_mappings(rec)))

    alert = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>' if error else ""
    if problems:
        alert += ('<div class="alert alert-error" style="display:block;">'
                  '<div style="font-weight:700;margin-bottom:.3rem;">&#10007; '
                  'Before this can open as a BOQ:</div><ul style="margin:0 0 0 1.1rem;">'
                  + "".join(f"<li>{P.esc(p)}</li>" for p in problems) + "</ul></div>")

    # The tabs (R5): every staged one with a tick; the reader's pick ticked.
    tick_html = []
    for i, s in enumerate(rec.get("sheets") or []):
        if not s.get("staged") or _tab_grid(rec, i) is None:
            continue
        tag = "" if s.get("visibility") == "visible" else " (hidden)"
        tick_html.append(
            f'<label class="imp-tab"><input type="checkbox" name="tab" value="{i}"'
            f'{" checked" if i in tabs else ""}/> {P.esc(s.get("name"))}{tag} '
            f'&middot; {int(s.get("rows") or 0)} rows</label>')
    unread = [s for s in rec.get("sheets") or [] if not s.get("staged")]
    unread_html = ""
    if unread:
        unread_html = ('<ul class="imp-flags">' + "".join(
            f"<li>{P.esc(s.get('name'))}: {P.esc(s.get('refusal') or 'not read')}</li>"
            for s in unread) + "</ul>")

    # The primary tab's grid as read, the cells a flag came from shaded. The
    # targets are chosen in the picker above it now, not in this grid.
    cols = grid["cols"]
    primary = int(rec.get("sheet_index") or 0)
    flagged = {}
    for f in result["flags"]:
        if several and f.get("tab") != _tab_name(rec, primary):
            continue
        key = (f["row"], f["col"])
        if flagged.get(key) != "is-red":
            flagged[key] = "is-red" if f.get("severity") == "red" else "is-flag"
    head_cells = "".join(f"<th>{SI.col_letter(c)}</th>" for c in cols)
    body_rows = []
    hdr = grid.get("header") or []
    shown = list(range(hdr[0], hdr[1] + 1)) if hdr else []
    start = SI.data_start(grid)
    shown += list(range(start, min(len(grid["rows"]), start + SI.PREVIEW_ROWS)))
    for ri in shown:
        rnum, vals = grid["rows"][ri]
        tds = []
        for ci, c in enumerate(cols):
            v = vals[ci] if ci < len(vals) else None
            cls = flagged.get((rnum, SI.col_letter(c)), "")
            cls_attr = f' class="{cls}"' if cls else ""
            tds.append(f"<td{cls_attr}>{P.esc(_cell_text(v))}</td>")
        rcls = ' class="imp-hdr"' if hdr and hdr[0] <= ri <= hdr[1] else ""
        body_rows.append(f'<tr{rcls}><td class="imp-rn">{int(rnum)}</td>{"".join(tds)}</tr>')
    more_rows = len(grid["rows"]) - (start + SI.PREVIEW_ROWS)
    more_note = (f'<p class="imp-note">&hellip; and {more_rows} more rows on the sheet, '
                 f'all of which are read.</p>' if more_rows > 0 else "")

    c = result["counts"]
    model = editor_model(result)
    heads = sum(1 for l in model["lines"] if l["is_header"])
    stats = (f'<div class="imp-stats"><span><b>{c["lines"]}</b> lines</span>'
             f'<span><b>{heads}</b> spec headers</span>'
             f'<span><b>{len(result["sections"])}</b> sections</span>'
             f'<span><b>{c["totals_dropped"]}</b> total rows checked, not imported</span>'
             + (f'<span><b>{len(tabs)}</b> tabs, one section each</span>' if several else "")
             + (f'<span><b>{c["repeats"]}</b> repeated heading rows skipped</span>'
                if c.get("repeats") else "")
             + (f'<span><b>{c["group_labels"]}</b> group labels put in front of their '
                f'sizes</span>' if c.get("group_labels") else "")
             + (f'<span><b>{c["below_grand"]}</b> rows below the grand total left out'
                f'</span>' if c.get("below_grand") else "") + '</div>')

    known = ""
    if rec.get("layout") and rec["layout"] in _layouts():
        lay = _layouts()[rec["layout"]]
        known = (f'<p class="imp-note">This layout has been confirmed '
                 f'{int(lay.get("use_count") or 0)} time(s) before; its saved column '
                 f'choices are applied. Confirming again saves any change.</p>')

    pickers = "".join(_picker_html(rec, i, several) for i in tabs)
    unit_mapped = any("unit" in _mapping_of(rec, i).values() for i in tabs)
    act = url_for("boqimport.preview", token=token)
    body = f"""
  {alert}
  <div class="page-top">
    <h1>Import <span>check the columns</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boqimport.upload')}" class="btn btn-ghost">&#8592; Upload a different file</a>
    </div>
  </div>
  <form method="POST" action="{act}">
    <input type="hidden" name="picker" value="1"/>
    <div class="imp-card">
      <h2>{P.esc(rec.get("filename"))}</h2>
      <div class="imp-tabs">{"".join(tick_html)}</div>
      <div class="imp-actions" style="justify-content:flex-start;margin-top:.6rem;">
        <button class="btn btn-ghost" type="submit" name="action" value="update">Show the ticked tabs</button>
      </div>
      <p class="imp-note">Tick every tab that belongs in this BOQ: each becomes a
      <b>section</b>, titled as the tab is &mdash; its own section title if it has one,
      else the tab&rsquo;s name. A hidden tab is listed and never ticked for you.</p>
      {unread_html}
      {known}
    </div>
    {_mode_card(mode, why, str(rec.get("markup") or ""))}
    {_names_html(rec)}
    {pickers}

    <div class="imp-card">
      <h2>The sheet as read{f" &mdash; {P.esc(_tab_name(rec, primary))}" if several else ""}</h2>
      <div class="imp-wrap">
        <table class="imp-grid">
          <thead><tr><th>Row</th>{head_cells}</tr></thead>
          <tbody>{"".join(body_rows)}</tbody>
        </table>
      </div>
      {more_note}
      <div class="imp-actions">
        <button class="btn btn-ghost" type="submit" name="action" value="update">Update preview</button>
      </div>
    </div>

    <div class="imp-card">
      <h2>What will be imported</h2>
      {stats}
      <p id="imp-costcheck" class="imp-note"{"" if mode == "cost" else ' style="display:none;"'}>
      <b>Checked against the sheet&rsquo;s cost figures</b> &mdash; every quantity &times;
      rate, subtotal, section total and the grand total below is the sheet&rsquo;s own
      arithmetic on its base rates, before the markup.</p>
      <div style="margin:.6rem 0 0;font-size:.85rem;">{totals_block(result)}</div>
      {summary_html(result, model, on_form=False, unit_mapped=unit_mapped)}
      <p class="imp-note">The BOQ opens <b>as the sheet is</b>: a blank cell stays
      blank, a 0 stays 0, nothing is worked out or turned into 0, and nothing stops the
      save. Only the columns you ticked are imported.</p>
      <div class="imp-actions">
        <button class="btn" type="submit" name="action" value="confirm">Confirm &amp; open the BOQ form</button>
      </div>
    </div>
  </form>{_PICK_JS}"""
    return _page("Import BOQ", body)


def _banner(token: str, rec: dict, result: dict, model: dict,
            unit_mapped: bool = True, markup: float = None, prefill: dict = None) -> str:
    """The summary that sits on top of the prefilled form. Escaped here; the
    form's own `demo_banner` sits beside it. `markup` set: a cost sheet, and
    the banner says so in the brief's own words (1 October 2026). From 6
    October 2026 it names every ticked tab (R5) and says which names the
    sheet filled in (R4)."""
    c = result["counts"]
    tabs = _ticked(rec)
    cost = ""
    if markup is not None:
        cost = (f'<p style="margin:.4rem 0 0;"><b>Imported from a cost sheet:</b> base rate = '
                f'sheet rate, escalation = {P.esc(num_text(markup))}% on every line, editable '
                f'per line.</p>')
    known = ""
    if rec.get("known"):
        lay = _layouts().get(rec.get("layout") or "") or {}
        known = (f'<p style="margin:.4rem 0 0;">Recognised a layout confirmed '
                 f'{int(lay.get("use_count") or 0)} time(s) before, and applied its '
                 f'column choices. <a href="{url_for("boqimport.preview", token=token)}">'
                 f'Change mapping</a></p>')
    names = ""
    pf = prefill or {}
    filled = [w for k, w in (("project_name", "the project name"),
                             ("account_name", "the account name")) if pf.get(k)]
    if filled:
        book = (" &mdash; the account matches an address-book entry, which is selected "
                "and its address filled" if pf.get("bill_pick") else "")
        names = (f'<p style="margin:.4rem 0 0;">Filled in from the sheet: '
                 f'{" and ".join(filled)}{book}. Check them.</p>')
    flags = summary_html(result, model, on_form=True, unit_mapped=unit_mapped)
    cls = "imp-banner"
    if len(tabs) > 1:
        where = ("tabs " + ", ".join(f"“{P.esc(_tab_name(rec, i))}”" for i in tabs)
                 + " (one section each)")
    else:
        where = f"sheet “{P.esc(_sheet(rec).get('name'))}”"
    return (f'<div class="{cls}">&#128229; Imported from <b>{P.esc(rec.get("filename"))}</b>, '
            f'{where} &mdash; {c["lines"]} lines, '
            f'{sum(1 for l in model["lines"] if l["is_header"])} spec headers, '
            f'{len(result["sections"])} section'
            f'{"s" if len(result["sections"]) != 1 else ""}; {c["totals_dropped"]} total '
            f'row{"s" if c["totals_dropped"] != 1 else ""} checked and left out. '
            f'<b>Nothing has been saved.</b> Check the lines, fill in the project and '
            f'customer, then press Create BOQ &mdash; or just leave the page.'
            f'<div style="margin:.4rem 0 0;">{totals_block(result)}</div>'
            f'{cost}{known}{names}{flags}</div>')


# =============================================================================
# ROUTES
# =============================================================================

@boqimport_bp.route("", methods=["GET", "POST"])
def upload():
    purge()
    if request.method == "GET":
        return _upload_page()

    try:
        data, filename = _read_upload()
        wb = SI.read(data, filename)
    except SI.Refused as refused:
        return _upload_page(refused.message)

    token, known = stage(wb, filename, _uid())
    if known:
        return redirect(url_for("boqimport.form", token=token), code=303)
    return redirect(url_for("boqimport.preview", token=token), code=303)


def _take_picker_post(rec: dict, form) -> list:
    """
    The column picker's POST (6 October 2026, R1/R4/R5): the ticked tabs, each
    tab's targets — a column is taken only when its Import box is ticked —
    and the two names as typed. Returns problems ([] when it was taken).

    A tab ticked for the first time posts no targets of its own: it gets its
    default (its known layout, the first tab's picks when the headers match,
    else the advice) AFTER the posted tabs are stored, so a match copies what
    was just chosen rather than what was chosen before.
    """
    sheets = rec.get("sheets") or []
    tabs = []
    for x in form.getlist("tab"):
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if (0 <= i < len(sheets) and sheets[i].get("staged")
                and _tab_grid(rec, i) is not None and i not in tabs):
            tabs.append(i)
    tabs.sort()
    rec["names"] = {k: str(form.get(k) or "").strip()[:200]
                    for k in ("project_name", "account_name")}
    if not tabs:
        return ["Tick at least one tab to import."]

    posted = {}
    for i in tabs:
        grid = _tab_grid(rec, i)
        if not any(k.startswith(f"map_{i}_") for k in form):
            continue
        picks = {}
        for c in grid["cols"]:
            picks[str(c)] = (str(form.get(f"map_{i}_{c}") or "")
                             if form.get(f"use_{i}_{c}") else "")
        posted[i] = SI.clean_mapping(grid, picks)

    primary = tabs[0]
    old_maps = {i: _mapping_of(rec, i) for i in tabs if i not in posted
                and (i == rec.get("sheet_index") or str(i) in (rec.get("tab_maps") or {}))}
    if primary != rec.get("sheet_index"):
        rec["sheet_index"] = primary
        rec["layout"] = SI.signature(_tab_grid(rec, primary))
        rec["known"] = False
    rec["ticked"] = tabs
    maps = {**old_maps, **posted}
    rec["mapping"] = maps.get(primary) or {}
    rec["tab_maps"] = {str(i): m for i, m in maps.items() if i != primary}
    for i in tabs:
        if i not in maps:
            m = _default_mapping(rec, i)
            if i == primary:
                rec["mapping"] = m
            else:
                rec["tab_maps"][str(i)] = m
    return []


@boqimport_bp.route("/<token>", methods=["GET", "POST"])
def preview(token: str):
    purge()
    rec = _own(token)
    if rec is None or _grid(rec) is None:
        return _not_found()
    if request.method == "GET":
        return _preview_page(token, rec)

    if request.form.get("picker"):
        # The column picker (6 October 2026) — every tab's ticks and targets.
        problems = _take_picker_post(rec, request.form)
        if problems:
            return _preview_page(token, rec, problems=problems)
    else:
        # ⚠ The v1 shape, still honoured: a `sheet` to switch to, and one flat
        #   `map_<column>` per column for that sheet — every column taken,
        #   the dropdown alone deciding. A request that is not the picker's
        #   (an old page, a script) reads exactly as it always did.
        try:
            wanted = int(request.form.get("sheet", rec.get("sheet_index") or 0))
        except (TypeError, ValueError):
            wanted = rec.get("sheet_index") or 0
        sheets = rec.get("sheets") or []
        if (wanted != rec.get("sheet_index") and 0 <= wanted < len(sheets)
                and sheets[wanted].get("staged") and rec["grid"][wanted] is not None):
            rec["sheet_index"] = wanted
            grid = rec["grid"][wanted]
            known_map, _lay = _known_mapping(grid)
            rec["mapping"] = known_map if known_map is not None else SI.advised_mapping(grid)
            rec["layout"] = SI.signature(grid)
            rec["known"] = False
            rec["ticked"], rec["tab_maps"] = [wanted], {}
            # The selling / cost choice belonged to the old sheet: back to this
            # sheet's own pre-selection.
            rec["rate_mode"], rec["markup"] = "", ""
            return redirect(url_for("boqimport.preview", token=token), code=303)

        grid = _grid(rec)
        posted = {k[4:]: v for k, v in request.form.items() if k.startswith("map_")}
        rec["mapping"] = SI.clean_mapping(grid, posted)

    grid = _grid(rec)
    # Selling rates or our cost (1 October 2026). Kept on every POST — an
    # "Update preview" as much as a confirm — so the choice survives a re-read.
    if request.form.get("rate_mode") in RATE_MODES:
        rec["rate_mode"] = request.form["rate_mode"]
    if "markup" in request.form:
        rec["markup"] = str(request.form.get("markup") or "").strip()[:20]

    # "confirm@<line>.<field>" was a link in the grouped summary: confirm, and
    # land on that field. Nothing emits it from 6 October 2026 (A3 — no field
    # needs anybody); an old page that posts it still confirms. Anything that
    # is not exactly that shape is ignored.
    action = request.form.get("action") or ""
    goto = ""
    if action.startswith("confirm@"):
        goto = action[len("confirm@"):]
        action = "confirm"
        if not _GOTO.match(goto):
            goto = ""
    if action != "confirm":
        return redirect(url_for("boqimport.preview", token=token), code=303)

    mode, _why = rate_mode(rec, grid)
    problems = _tab_problems(rec) + mode_problems(mode, rec.get("markup"), _all_mappings(rec))
    if problems:
        return _preview_page(token, rec, problems=problems)
    markup = parse_markup(rec.get("markup")) if mode == "cost" else None
    # Every ticked tab, merged — and measured WHOLE against the BOQ's limits
    # (R5): refused with its line count, never truncated.
    refusal = too_large(editor_model(build_tabs(rec), markup=markup))
    if refusal:
        return _preview_page(token, rec, error=refusal)
    for i in _ticked(rec):
        # Each tab's picks are remembered under its own header signature.
        _upsert_layout(_tab_grid(rec, i), _mapping_of(rec, i), mode)
    rec["layout"] = SI.signature(grid)
    rec["confirmed"], rec["known"] = True, False
    dest = url_for("boqimport.form", token=token)
    if goto:
        line_i, field = goto.split(".", 1)
        dest += f"#need-{int(line_i)}-{field}"
    return redirect(dest, code=303)


@boqimport_bp.route("/<token>/form")
def form(token: str):
    purge()
    rec = _own(token)
    if rec is None or _grid(rec) is None:
        return _not_found()
    if not (rec.get("confirmed") or rec.get("known")):
        return redirect(url_for("boqimport.preview", token=token), code=303)

    grid = _grid(rec)
    mode, _why = rate_mode(rec, grid)
    problems = _tab_problems(rec) + mode_problems(mode, rec.get("markup"), _all_mappings(rec))
    if problems:
        rec["known"] = False
        return _preview_page(token, rec, problems=problems)
    markup = parse_markup(rec.get("markup")) if mode == "cost" else None
    result = build_tabs(rec)
    model = editor_model(result, markup=markup)
    refusal = too_large(model)
    if refusal:
        rec["known"], rec["confirmed"] = False, False
        return _preview_page(token, rec, error=refusal)

    # The names the sheet gave (R4) — suggestions, now on the ordinary form,
    # where they are edited like anything else; nothing is saved here.
    prefill = prefill_of(rec)
    unit_mapped = any("unit" in _mapping_of(rec, i).values() for i in _ticked(rec))
    # IMPORT_STYLES rides with the banner: /boq/create does not load it, so the
    # banner's own classes were unstyled there until 30 September 2026.
    html = BQ.create_boq(imported={"boot": model, "prefill": prefill,
                                   "banner_html": IMPORT_STYLES + _banner(
                                       token, rec, result, model,
                                       unit_mapped=unit_mapped,
                                       markup=markup, prefill=prefill)})
    # Consumed. A known layout keeps its row for the Change-mapping link; the
    # 24-hour purge takes it.
    if rec.get("confirmed"):
        _imports().pop(token, None)
    return html
