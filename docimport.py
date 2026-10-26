"""
docimport.py — Import from Excel, for every document that is typed in  (18 Oct 2026)
====================================================================================
CLIENT_CHANGES.md §0, **forty-eighth block** — authorised by Manas Gawde on
18 October 2026. ⚠ Its commercial status is NOT recorded there and is not
decided here.

What it does, for every kind below: upload a sheet in any layout, choose what
each column holds — every column has a dropdown, and **ignore** is how a
column does not go through — check what will come in, and land on the
document's OWN create form filled in. A LEGEND names the columns the document
cannot be made without, on the upload page and again beside the dropdowns,
where each line says whether a column has been chosen for it.

    GET,POST /import/<kind>                  the upload page and the legend
    GET,POST /import/<kind>/<token>          the preview: sheet, heading row, a
                                             target per column, the legend ticked
                                             off, and what will come in
    GET      /import/<kind>/<token>/apply    the document's create form, PREFILLED
    POST     /import/<kind>/<token>/apply    the three registers only: create

The kinds, and where each one lands
-----------------------------------
| kind          | the sheet becomes                         | lands on                  |
|---------------|-------------------------------------------|---------------------------|
| `purchase`    | the order's extra-part lines              | `/purchase/create`        |
| `quotation`   | spec-library picks (Supply only)          | `/quotation/create`       |
| `measurement` | the joint grid's location rows            | `/measurement/create`     |
| `challan`     | dispatch quantities against BOQ lines     | `/dc/create`              |
| `dpo`         | order quantities against BOQ lines        | `/po/create`              |
| `ra`          | claim quantities against BOQ lines        | `/ra/create` (manual path)|
| `address`     | one address per row                       | a review page, then saved |
| `spec`        | one clause per code, a size per row       | a review page, then saved |
| `employee`    | one person per row                        | a review page, then saved |

**Nothing is saved until the ordinary Save is pressed.** For the six line
documents the prefilled page IS the document's create view, reached through
its one `imported` seam (`boq.create_boq(imported=…)`'s arrangement, six
times): the same form, the same POST, the same refusals — the over-claim block,
C1, the measurement cap, the GST guard, the extra-part placeholder mark — and
this module never writes a document. For the three registers there is no form
to fill with many records, so the review page lists every row with the verdict
of that register's OWN validator (`address._validate()`, `spec._validate()`,
`employee._validate()`), and *Create* writes the rows that pass through that
register's own `create_record()`. A row that does not pass is listed and not
created.

⚠ **A BOQ line is matched on `line_id`, and a sheet carries none.** For the
challan, the draft PO and the RA bill the sheet's item number (and section, and
description, when mapped) only PROPOSES which BOQ line a row is: one exact
match is proposed, a number the schedule carries twice is never chosen for the
operator, and every proposal is a dropdown the operator can change before
anything is prefilled. What reaches the form is the `line_id` the operator
confirmed — the save is the picker's own, keyed on it, exactly as
CLIENT_CHANGES.md §0's fortieth block requires. ABOUT.md §3 property 0 is the
₹1,99,122.50 reason.

Import direction — one way, never reversed
------------------------------------------
    docimport.py ──► sheetimport.py   the reader and the schema functions
    docimport.py ──► boqimport.py     the upload reader, the import stylesheet,
                                      the legend, num_text
    docimport.py ──► purchase, quotation, measurement, challan, po_draft, ra,
                     address, spec, employee, boq, specpick — each document's
                     create seam and its own validator
    <any of them> ──► docimport.py    NEVER. Every Import button is a url_for
                                      string.

Staging — `STORE["doc_imports"]`, and layouts — `STORE["doc_import_layouts"]`
------------------------------------------------------------------------------
The BOQ importer's staging rules, held here for every kind: parsed ONCE into a
grid of cell values, never the file; owned by the uploader, and anybody else —
or an expired token, or a token for another kind — gets the same 404; purged
after 24 hours on every request; at most ten per user, across every kind. A
line document's row is NOT consumed by rendering its form, so a reload of the
prefilled form works (the purge takes it); a register's row IS consumed by *Create*, so a second
press cannot create everything twice. A confirmed mapping is remembered per
kind and heading (`sheetimport.schema_signature()`) and offered next time — on
the preview, never instead of it.
"""

import datetime
import re
import secrets
import time

from flask import Blueprint, redirect, request, url_for
from werkzeug.datastructures import MultiDict

import address as AD
import auth
import boq as BQ
import boqimport as BI
import boqpick as BP   # MAKE_MAX — the one cap on a line's make (26 Oct 2026)
import branding as B
import challan as DC
import employee as EMP
import measurement as MS
import pipeline as P
import po_draft as DPO
import purchase as PU
import quotation as Q
import ra as RA
import sheetimport as SI
import spec as SP
import specpick as SPK
from chrome import BASE_STYLES, _nav
from store import STORE

docimport_bp = Blueprint("docimport", __name__, url_prefix="/import")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

STAGE_TTL_SECONDS = 24 * 3600
# Across every kind, not per kind: one person part-way through a purchase
# order, a challan and the address book at once holds three. Each row is held
# under `sheetimport.STAGE_BUDGET_CHARS`, and `db.sync()` re-hashes every row
# on every request, so the cap is what bounds that cost.
MAX_STAGED_PER_USER = 10

# How many option elements the line-matching dropdowns may draw on one page,
# across every row. A sheet whose rows match nothing on a 600-line schedule
# would otherwise draw 600 options per row; past this, a row that matched
# nothing offers only "leave out" and says why.
MATCH_OPTIONS_CAP = 40_000

# How many notes a banner on a prefilled form lists row by row before it says
# how many more.
BANNER_NOTES = 120


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _uid() -> str:
    return (auth.current_user() or {}).get("id", "")


def _imports() -> dict:
    return STORE.setdefault("doc_imports", {})


def _layouts() -> dict:
    return STORE.setdefault("doc_import_layouts", {})


def _url(page: str, kind, **kw) -> str:
    """
    Every link this module draws to one of its own pages.

    ⚠ **The ONE computed `url_for` in this module, on purpose.** The routes are
      minted per kind (`_register_routes()` — `approval.py`'s precedent),
      because `auth.ROUTE_PERMISSIONS` maps one endpoint to one permission and
      each kind carries its document's. The three prefixes below are literals
      so `tests/test_page_reachability.py`'s prefix rule resolves them.
    """
    prefix = {"upload": "docimport.upload_", "preview": "docimport.preview_",
              "apply": "docimport.apply_"}[page]
    return url_for(prefix + kind.key, **kw)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


# =============================================================================
# THE KINDS
# =============================================================================

class Kind:
    """
    What one document needs from the shared engine. Every method has the
    plain default a kind with nothing special about it wants.
    """
    key = ""
    title = ""            # the page heading's span — "Purchase order parts"
    noun = ""             # what the legend says cannot be made without them
    endpoint = ""         # the create endpoint whose permission this carries
    needs_boq = False     # raised against a schedule (`?boq=`)
    register = False      # many records, saved from a review page
    max_rows = 300
    save_label = ""       # the create form's own button, named in the banner

    # ── context: what the upload was for (a BOQ, a leg) ────────────────────
    def context(self, args):
        """`(ctx, error, response)`. `response` short-circuits the request —
        a refusal the document's own route would give."""
        return {}, "", None

    def back_url(self, ctx) -> str:
        return url_for(self.endpoint)

    def schema(self, ctx) -> dict:
        raise NotImplementedError

    def legend(self, ctx) -> list:
        sch = self.schema(ctx)
        items = [{"label": t["label"], "keys": (t["key"],), "about": t["about"]}
                 for t in sch["targets"] if t["required"]]
        items += [{"label": g["label"], "keys": tuple(g["keys"]), "about": g["about"]}
                  for g in sch.get("any_of") or ()]
        return items

    def intro_html(self, ctx) -> str:
        return ""

    def options_html(self, rec) -> str:
        return ""

    def read_options(self, form, rec) -> None:
        return None

    def build(self, rows, rec) -> dict:
        raise NotImplementedError

    def extra_html(self, token, rec, built) -> str:
        return ""

    def read_extra(self, form, rec) -> None:
        return None

    def problems(self, rec, built) -> list:
        return []

    def apply(self, token, rec, built):
        raise NotImplementedError

    def save(self, token, rec, built):
        return redirect(_url("preview", self, token=token), code=303)


def _note(row, msg: str, level: str = "amber") -> dict:
    return {"row": row, "msg": msg, "level": level}


def _t(cells: dict, key: str, reader=SI.cell_text):
    """`(value, why)` of one mapped cell through `reader`; blank when unmapped."""
    if key not in cells:
        return ("" if reader is not SI.cell_number else None), ""
    v, k = cells[key]
    return reader(v, k)


# A sheet's Make column (26 October 2026) — the headings the BOQ importer
# already reads as a make (`sheetimport._MAKE`), as a search rather than a
# whole-cell match. A guess, as every `kw` is; the picker can change it.
_MAKE_KW = r"\bmakes?\b|\bbrand\b|manufactur|\bmfr\b"


def _make_of(cells: dict, n, notes: list) -> str:
    """A row's Make, as text, cut to what a line keeps (`BP.MAKE_MAX`)."""
    make, why = _t(cells, "make")
    if why:
        notes.append(_note(n, f"Make: {why} — left blank."))
        return ""
    if len(make) > BP.MAKE_MAX:
        notes.append(_note(n, f"The make runs past the {BP.MAKE_MAX} characters a "
                              f"line keeps; the order keeps the first {BP.MAKE_MAX}."))
    return make[:BP.MAKE_MAX]


# ── Purchase order — the extra-part repeater ─────────────────────────────────

class PurchaseKind(Kind):
    key = "purchase"
    title = "parts for a purchase order"
    noun = "purchase order"
    endpoint = "purchase.create_purchase"
    save_label = "Raise Purchase Order"
    max_rows = 300

    def schema(self, ctx):
        return {"targets": [
            SI.target("description", "Part / description", required=True,
                      about="What the vendor is being asked to supply, as you would "
                            "say it to them. A row with figures and no description "
                            "is left out — the order would refuse it.",
                      kw=r"descr|particular|\bitems?\b|\bparts?\b|material|\bname\b|specification|product",
                      avoid=r"\bsr\b|s\.?\s?no|serial|\bcode\b|hsn|\bqty|quantit|\brate|price|amount|\bunits?\b|disc|\bno\.?$"),
            # Make (26 October 2026) — the brand the vendor is asked to supply,
            # printed beside the description. Optional, free text.
            SI.target("make", "Make", kw=_MAKE_KW),
            SI.target("hsn", "HSN", kw=r"\bhsn\b|\bsac\b"),
            SI.target("unit", "Unit", kw=r"\bunits?\b|\buom\b|u\.o\.m",
                      avoid=r"rate|price|cost|amount"),
            SI.target("qty", "Quantity", required=True,
                      about="How many of the part. A word or a sum written as text "
                            "is left blank for you to fill — never turned into 0.",
                      kw=r"\bqty\b|quantit|\bqnty\b|\bnos?\b\.?$", avoid=r"rate|amount|price"),
            SI.target("rate", "Rate (₹)", kw=r"\brate\b|price|\bcost\b",
                      avoid=r"amount|total|disc"),
            SI.target("discount", "Discount %", kw=r"disc"),
        ]}

    def intro_html(self, ctx):
        return ("<p class=\"imp-note\">Each row becomes one <b>extra part</b> on a new "
                "purchase order &mdash; free text, not a catalogue. A blank rate stays "
                "blank: where the part is one we have seen before the order fills a "
                "<b>placeholder</b> rate on save and flags it, exactly as when you type "
                "the part by hand.</p>")

    def build(self, rows, rec):
        items, notes = [], []
        for r in rows:
            c, n = r["cells"], r["row"]
            desc, why = _t(c, "description")
            if why:
                notes.append(_note(n, f"Description: {why} — left out.", "red"))
                continue
            if not desc:
                notes.append(_note(n, "Figures but no description — left out: the "
                                      "order refuses a line that does not say what "
                                      "it is.", "red"))
                continue
            if len(desc) > 200:
                notes.append(_note(n, "The description runs past the 200 characters "
                                      "an extra part takes; the order keeps the first 200."))
            qty, why = _t(c, "qty", SI.cell_number)
            if why:
                notes.append(_note(n, f"Quantity: {why} — left blank for you to fill."))
            elif qty is None:
                notes.append(_note(n, "No quantity — left blank for you to fill."))
            elif qty < 0:
                notes.append(_note(n, "A negative quantity — left blank."))
                qty = None
            rate, why = _t(c, "rate", SI.cell_number)
            if why:
                notes.append(_note(n, f"Rate: {why} — left blank."))
            elif rate is not None and rate < 0:
                notes.append(_note(n, "A negative rate — left blank."))
                rate = None
            disc = None
            if "discount" in c:
                v, k = c["discount"]
                disc, why = SI.cell_number(v, k, percent=True)
                if why:
                    notes.append(_note(n, f"Discount: {why} — left blank."))
                elif disc is not None and not 0 <= disc <= PU.MAX_DISCOUNT_PCT:
                    notes.append(_note(n, "A discount outside 0–100% — left blank."))
                    disc = None
            hsn, _w = _t(c, "hsn", SI.cell_code)
            if len(hsn) > 8:
                notes.append(_note(n, f"HSN “{hsn[:20]}” is longer than the 8 "
                                      f"characters the order keeps."))
            unit, _w = _t(c, "unit")
            make = _make_of(c, n, notes)
            items.append({"row": n, "description": desc, "hsn": hsn[:8],
                          "unit": unit[:30],
                          "qty": BI.num_text(qty), "rate": BI.num_text(rate),
                          "discount": BI.num_text(disc), "make": make})
        return {"items": items, "notes": notes,
                "stats": [(len(items), "part" if len(items) == 1 else "parts")]}

    def apply(self, token, rec, built):
        md = MultiDict()
        for it in built["items"]:
            md.add("extra_desc", it["description"])
            md.add("extra_unit", it["unit"])
            md.add("extra_qty", it["qty"])
            md.add("extra_rate", it["rate"])
            md.add("extra_discount", it["discount"])
            md.add("extra_hsn", it["hsn"])
            md.add("extra_make", it.get("make", ""))
        return PU.create_purchase(imported={
            "extra": md, "banner_html": _banner(self, rec, built)})


# ── Quotation — spec-library picks ───────────────────────────────────────────

class QuotationKind(Kind):
    key = "quotation"
    title = "lines for a quotation"
    noun = "quotation"
    endpoint = "quotation.create_quotation"
    save_label = "Generate Quotation"
    max_rows = 300

    def context(self, args):
        if not auth.blueprint_hidden("product"):
            return {}, ("The quotation picker reads the product catalogue at the "
                        "moment, and a sheet carries no catalogue product. Import "
                        "works while the picker reads the specification library."), None
        SPK.ensure_seeded()
        return {}, "", None

    def schema(self, ctx):
        return {"targets": [
            SI.target("code", "Spec code", kw=r"\bcode\b|spec\.?\s*(?:no|id|code)|\bref\b"),
            SI.target("description", "Description",
                      kw=r"descr|particular|specification|\bitems?\b|\bname\b|\btitle\b",
                      avoid=r"\bcode\b|\bqty|quantit|\brate|price|amount|\bunits?\b|\bsize\b"),
            SI.target("size", "Size / variant",
                      kw=r"\bsize\b|\bdia\b|diameter|variant|\bnb\b|dimension"),
            SI.target("qty", "Quantity", required=True,
                      about="How many. A row with no quantity, or 0, is left out — "
                            "a quotation line must be greater than zero.",
                      kw=r"\bqty\b|quantit|\bqnty\b", avoid=r"rate|amount|price"),
            SI.target("price", "Rate (₹)", kw=r"\brate\b|price|\bcost\b",
                      avoid=r"amount|total"),
        ], "any_of": [{
            "keys": ("code", "description"),
            "label": "Spec code — or Description",
            "about": "Which library clause the row is. A spec code "
                     "(PIPE-MS-C-1239-AG) is matched exactly; a description only "
                     "when it is a clause's title word for word. A row that "
                     "matches no clause is listed for you to choose — nothing "
                     "is guessed. Quotations quote SUPPLY only.",
        }]}

    def intro_html(self, ctx):
        return ("<p class=\"imp-note\">Each row becomes one <b>Supply</b> line picked from "
                "the specification library. A row's rate, when the sheet gives one, is "
                "its price; otherwise the library's supply rate is suggested, and a "
                "size with no library rate opens with an empty price box.</p>")

    @staticmethod
    def _variant_text(spec, vidx) -> str:
        v = (spec.get("variants") or [{}])[vidx]
        label = (v.get("label") or "").strip()
        return f"{spec.get('code', '')} — {spec.get('title', '')}" + (f" · {label}" if label else "")

    @staticmethod
    def _match(c):
        """`(sid, vidx | None, cands, why)` — exact matches only."""
        specs = STORE.get("specs") or {}
        code, _w = _t(c, "code", SI.cell_code)
        desc, _w = _t(c, "description")
        size, _w = _t(c, "size")
        sid = None
        if code:
            hits = [k for k, s in specs.items() if _norm(s.get("code")) == _norm(code)]
            if not hits:
                return None, None, [], f"no clause in the library has the code “{code}”"
            if len(hits) > 1:
                return None, None, [(k, None) for k in hits], "several clauses share that code"
            sid = hits[0]
        elif desc:
            hits = [k for k, s in specs.items() if _norm(s.get("title")) == _norm(desc)]
            if len(hits) == 1:
                sid = hits[0]
            elif not hits:
                return None, None, [], "no clause in the library has that title"
            else:
                return None, None, [(k, None) for k in hits], "several clauses share that title"
        else:
            return None, None, [], "neither a spec code nor a description"
        spec = specs[sid]
        variants = spec.get("variants") or []
        if len(variants) == 1:
            return sid, 0, [], ""
        if size:
            want = _norm(size)
            for i, v in enumerate(variants):
                dim = str(v.get("dimension") or "").strip()
                forms = {_norm(v.get("label")), _norm(dim),
                         _norm(f"{dim} {v.get('dim_unit') or ''}"),
                         _norm(f"{dim}{v.get('dim_unit') or ''}")} - {""}
                if want in forms:
                    return sid, i, [], ""
            return sid, None, [(sid, i) for i in range(len(variants))], \
                f"no size of {spec.get('code')} is called “{size}”"
        return sid, None, [(sid, i) for i in range(len(variants))], \
            f"{spec.get('code')} comes in {len(variants)} sizes and the row names none"

    def build(self, rows, rec):
        specs = STORE.get("specs") or {}
        chosen = rec.get("matches") or {}
        picks, notes, review = [], [], []
        for r in rows:
            c, n = r["cells"], r["row"]
            qty, qwhy = _t(c, "qty", SI.cell_number)
            sid, vidx, cands, why = self._match(c)
            posted = chosen.get(str(n))
            if posted is not None:
                if posted == "":
                    sid, vidx = None, None
                    why = "left out"
                else:
                    psid, _, pv = posted.partition(":")
                    if psid in specs and pv.isdigit() and int(pv) < len(specs[psid].get("variants") or []):
                        sid, vidx, why = psid, int(pv), ""
            review.append({"row": n, "text": " · ".join(x for x in (
                _t(c, "code", SI.cell_code)[0], _t(c, "description")[0], _t(c, "size")[0]) if x),
                "sid": sid, "vidx": vidx, "cands": cands, "why": why,
                "auto": posted is None})
            if sid is None or vidx is None:
                notes.append(_note(n, f"Not imported: {why}.", "red"))
                continue
            if qwhy or qty is None or qty <= 0:
                notes.append(_note(n, f"Quantity: {qwhy or 'none, or 0'} — left out: a "
                                      f"quotation line must be greater than zero.", "red"))
                continue
            spec = specs[sid]
            v = (spec.get("variants") or [{}])[vidx]
            price, pwhy = _t(c, "price", SI.cell_number)
            if pwhy:
                notes.append(_note(n, f"Rate: {pwhy} — the library rate is used."))
                price = None
            if price is not None and price < 0:
                notes.append(_note(n, "A negative rate — the library rate is used."))
                price = None
            if price is None:
                price = v.get("default_supply_base_rate")
                if price is None:
                    notes.append(_note(n, "No rate on the sheet and none in the library "
                                          "for this size — the price box opens empty; "
                                          "type one before generating."))
            picks.append({"rid": len(picks) + 1, "sid": sid, "vidx": vidx,
                          "leg": "supply", "name": spec.get("title", ""),
                          "part_no": spec.get("code", ""), "unit": v.get("unit", ""),
                          "label": v.get("label", ""), "qty": qty,
                          "price": "" if price is None else price,
                          "show_price": True})
        return {"items": picks, "notes": notes, "review": review,
                "stats": [(len(picks), "line" if len(picks) == 1 else "lines")]}

    def read_extra(self, form, rec):
        """`BoqLineKind.read_extra()`'s rule: only a CHANGED row is a choice."""
        auto = {str(r["row"]): (f"{r['sid']}:{r['vidx']}" if r["sid"] is not None
                                and r["vidx"] is not None else "")
                for r in _built(self, dict(rec, matches={}))["review"]}
        out = dict(rec.get("matches") or {})
        for k, v in form.items():
            if k.startswith("match_") and k[6:] in auto:
                v = str(v or "")[:80]
                if v == auto[k[6:]]:
                    out.pop(k[6:], None)
                else:
                    out[k[6:]] = v
        rec["matches"] = out

    def extra_html(self, token, rec, built):
        specs = STORE.get("specs") or {}
        open_rows = [r for r in built["review"] if r["sid"] is None or r["vidx"] is None
                     or not r["auto"]]
        if not open_rows:
            return ""
        all_pairs = [(k, i) for k, s in sorted(specs.items(), key=lambda kv: kv[1].get("code", ""))
                     for i in range(len(s.get("variants") or []))]
        budget = MATCH_OPTIONS_CAP
        body = []
        for r in open_rows:
            cands = r["cands"] or (all_pairs if budget >= len(all_pairs) else [])
            budget -= len(cands)
            cur = (f"{r['sid']}:{r['vidx']}" if r["sid"] is not None and r["vidx"] is not None
                   else "")
            opts = ['<option value="">&#8212; leave this row out &#8212;</option>']
            for sid, vi in cands:
                if sid not in specs:
                    continue
                vis = range(len(specs[sid].get("variants") or [])) if vi is None else [vi]
                for i in vis:
                    val = f"{sid}:{i}"
                    sel = " selected" if val == cur else ""
                    opts.append(f'<option value="{P.esc(val)}"{sel}>'
                                f'{P.esc(self._variant_text(specs[sid], i))}</option>')
            body.append(f'<tr><td class="imp-rn">{int(r["row"])}</td>'
                        f'<td>{P.esc(r["text"])}</td>'
                        f'<td><select name="match_{int(r["row"])}">{"".join(opts)}</select>'
                        f'<div class="imp-note">{P.esc(r["why"])}</div></td></tr>')
        return f"""
    <div class="imp-card">
      <h2>Rows that need you to choose the clause</h2>
      <p class="imp-note">These rows did not name one clause and one size exactly.
      Pick each one, or leave it out. Nothing is chosen for you.</p>
      <div class="imp-wrap"><table class="imp-grid imp-match">
        <thead><tr><th>Row</th><th>On the sheet</th><th>Library clause</th></tr></thead>
        <tbody>{"".join(body)}</tbody></table></div>
    </div>"""

    def apply(self, token, rec, built):
        return Q.create_quotation(imported={
            "selections": built["items"], "banner_html": _banner(self, rec, built)})


# ── Measurement sheet — the joint grid ───────────────────────────────────────

class MeasurementKind(Kind):
    key = "measurement"
    title = "a measurement grid"
    noun = "measurement grid"
    endpoint = "measurement.create_ms"
    needs_boq = True
    save_label = "Raise measurement"
    max_rows = MS.MAX_GRID_ROWS

    def context(self, args):
        return _boq_context(args)

    def back_url(self, ctx):
        return url_for("measurement.create_ms", boq=ctx.get("boq_id")) if ctx.get("boq_id") \
            else url_for("measurement.list_ms")

    @staticmethod
    def _cols():
        return MS.default_columns()

    def schema(self, ctx):
        targets = [SI.target(
            "label", "Location", required=True,
            about="Where on site each row was measured — H1, B2, Hydrant… One row "
                  "per location; the columns below are what was found there.",
            kw=r"locat|\barea\b|floor|level|zone|\bplace\b|\bpoint\b|description|particular")]
        keys = []
        for col in self._cols():
            label = str(col.get("label") or col["key"])
            nums = re.findall(r"\d+", label)
            kw = re.escape(_norm(label))
            if nums:
                kw += rf"|(?<!\d){nums[0]}(?!\d)"
            key = "g_" + str(col["key"])
            keys.append(key)
            unit = str(col.get("unit") or "").strip()
            targets.append(SI.target(key, f"{label}" + (f" ({unit})" if unit else ""), kw=kw))
        targets.append(SI.target("remarks", "Remarks", kw=r"remark|\bnote|comment"))
        return {"targets": targets, "any_of": [{
            "keys": tuple(keys),
            "label": "At least one measurement column",
            "about": "A column for a size or an item the grid carries (25 NB, MSA, "
                     "PENDANT…), holding what was measured at each location. The "
                     "grid's columns come from Settings; a sheet column for "
                     "anything else is left out.",
        }]}

    def intro_html(self, ctx):
        return ("<p class=\"imp-note\">Each row becomes one <b>location</b> on the joint "
                "measurement grid. The BOQ lines measured are still ticked on the form "
                "itself, as always.</p>")

    def build(self, rows, rec):
        cols = {"g_" + str(c["key"]): str(c["key"]) for c in self._cols()}
        grid, notes = [], []
        for r in rows:
            c, n = r["cells"], r["row"]
            label, why = _t(c, "label")
            if why:
                notes.append(_note(n, f"Location: {why}."))
            remarks, _w = _t(c, "remarks")
            values = {}
            for tk, key in cols.items():
                if tk not in c:
                    continue
                v, k = c[tk]
                num, why = SI.cell_number(v, k)
                if why:
                    notes.append(_note(n, f"{key}: {why} — left blank.", "red"))
                elif num is not None and num < 0:
                    notes.append(_note(n, f"{key}: a negative measurement — left blank.", "red"))
                elif num is not None:
                    values[key] = BI.num_text(num)
            if not label and not values and not remarks:
                continue
            if not label:
                notes.append(_note(n, "Figures but no location — the row comes in "
                                      "with a blank location; name it on the form."))
            grid.append({"label": label[:120], "values": values, "remarks": remarks[:300]})
        return {"items": grid, "notes": notes,
                "stats": [(len(grid), "location" if len(grid) == 1 else "locations")]}

    def apply(self, token, rec, built):
        return MS.create_ms(imported={"boq_id": rec["ctx"]["boq_id"],
                                      "grid": built["items"],
                                      "banner_html": _banner(self, rec, built)})


# ── Challan / draft PO / RA bill — quantities against BOQ lines ─────────────

def _boq_context(args):
    """The schedule a BOQ-bound import is raised against: the TIP of its chain,
    refused exactly as the document's own create route refuses it."""
    boq_id = str(args.get("boq") or "").strip()
    if not boq_id:
        return {}, "", None
    boq = (STORE.get("boqs") or {}).get(boq_id)
    if not boq:
        return {}, "That bill of quantities no longer exists. Choose another.", None
    if boq_id in BQ.superseded_ids():
        return {}, (f"{boq.get('ref')} has been superseded. Import against the "
                    f"current revision."), None
    return {"boq_id": boq_id}, "", None


def _sec_norm(s) -> str:
    """A section as the sheet writes it — "Section A", "(A)", "A." — reduced to
    its code for an EXACT comparison with the schedule's."""
    t = re.sub(r"(?i)\b(?:section|sec|part)\b\.?", " ", str(s or ""))
    return re.sub(r"[^0-9A-Za-z-]", "", t).upper()


class BoqLineKind(Kind):
    """The challan, the draft PO and the RA bill: a sheet row → a quantity
    against one BOQ line, proposed, confirmed, then prefilled by `line_id`."""
    needs_boq = True
    max_rows = BQ.MAX_LINES
    qty_label = "Quantity"
    qty_about = ""
    qty_prefer = ""
    extra_targets = ()

    def context(self, args):
        return _boq_context(args)

    def schema(self, ctx):
        return {"targets": [
            SI.target("item_no", "Item No.", required=True,
                      about="The BOQ item number the row is — 24.b, 3.1. It is "
                            "matched against the schedule EXACTLY. A number the "
                            "schedule carries more than once is never chosen for "
                            "you: you pick which line it is before anything is "
                            "filled in.",
                      kw=r"\bitems?\b|\bsr\b|s\.?\s?no|serial|\bsl\b",
                      avoid=r"descr|particular|\bqty|quantit|rate|amount"),
            SI.target("section", "Section", kw=r"\bsection\b|\bsec\.?\b"),
            SI.target("description", "Description",
                      kw=r"descr|particular|specification",
                      avoid=r"\bqty|quantit|rate|amount"),
            SI.target("qty", self.qty_label, required=True, about=self.qty_about,
                      kw=r"\bqty\b|quantit|\bqnty\b", avoid=r"rate|amount",
                      prefer=self.qty_prefer),
            *self.extra_targets,
        ]}

    def _boq(self, rec):
        return (STORE.get("boqs") or {}).get(rec["ctx"].get("boq_id")) or {}

    @staticmethod
    def _lines(boq):
        return [li for li in boq.get("line_items") or []
                if not li.get("is_header") and BQ._line_id(li.get("line_id"))]

    def _match(self, c, boq_lines, headers):
        """
        `(lid | None, cands, same, why)` — the one exact match, or the
        candidates to choose from. `same` is every priced line carrying the
        row's item number in ANY section, so a match can be changed to the
        neighbour a missing section column hid.
        """
        item, iwhy = _t(c, "item_no", SI.cell_item)
        if iwhy or not item:
            return None, [], [], iwhy or "no item number"
        sec, _w = _t(c, "section")
        desc, _w = _t(c, "description")
        same = [li for li in boq_lines if _norm(BQ._item_no(li.get("item_no"))) == _norm(item)]
        ids = [BQ._line_id(li["line_id"]) for li in same]
        cands = same
        if sec:
            cands = [li for li in same if _sec_norm(li.get("section")) == _sec_norm(sec)]
        if not cands:
            if _norm(item) in headers:
                return None, [], ids, (f"item {item} is a specification header — "
                                       f"nothing is entered against it")
            where = f" in section {sec}" if sec else ""
            return None, [], ids, f"no priced line on the schedule is item {item}{where}"
        if len(cands) == 1:
            return BQ._line_id(cands[0]["line_id"]), [], ids, ""
        if desc:
            hit = [li for li in cands if _norm(li.get("description")) == _norm(desc)]
            if len(hit) == 1:
                return BQ._line_id(hit[0]["line_id"]), [], ids, ""
        secs = sorted({str(li.get("section") or "") for li in cands})
        where = (f"in section {secs[0]}" if len(secs) == 1 else
                 f"in sections {', '.join(secs)}")
        return None, [BQ._line_id(li["line_id"]) for li in cands], ids, \
            f"item {item} is on the schedule {len(cands)} times, {where}"

    def _extra_values(self, c, n, notes) -> dict:
        return {}

    def build(self, rows, rec):
        boq = self._boq(rec)
        lines = self._lines(boq)
        by_id = {BQ._line_id(li["line_id"]): li for li in lines}
        headers = {_norm(BQ._item_no(li.get("item_no")))
                   for li in boq.get("line_items") or [] if li.get("is_header")}
        chosen = rec.get("matches") or {}
        items, notes, review, used = [], [], [], {}
        for r in rows:
            c, n = r["cells"], r["row"]
            lid, cands, same, why = self._match(c, lines, headers)
            posted = chosen.get(str(n))
            auto = posted is None
            if posted is not None:
                if posted == "":
                    lid, why = None, "left out"
                elif posted in by_id:
                    lid, why = posted, ""
            qty, qwhy = _t(c, "qty", SI.cell_number)
            review.append({"row": n, "item": _t(c, "item_no", SI.cell_item)[0],
                           "section": _t(c, "section")[0],
                           "desc": _t(c, "description")[0],
                           "qty": BI.num_text(qty) if qty is not None else "",
                           "lid": lid, "cands": cands, "same": same, "why": why,
                           "auto": auto})
            if lid is None:
                notes.append(_note(n, f"Not prefilled: {why}.", "red"))
                continue
            if qwhy or qty is None:
                notes.append(_note(n, f"Not prefilled: quantity {qwhy or 'is blank'}.", "red"))
                continue
            if qty <= 0:
                notes.append(_note(n, "Not prefilled: the quantity is 0 or less."))
                continue
            if lid in used:
                notes.append(_note(n, f"Not prefilled: row {used[lid]} already gives a "
                                      f"quantity for this line. Add them up on the form "
                                      f"if both are meant.", "red"))
                continue
            used[lid] = n
            items.append({"row": n, "lid": lid, "qty": BI.num_text(qty),
                          **self._extra_values(c, n, notes)})
        return {"items": items, "notes": notes, "review": review,
                "stats": [(len(items), "line matched" if len(items) == 1 else "lines matched")]}

    def read_extra(self, form, rec):
        """
        The rows whose dropdown the operator CHANGED. Every row's select is
        posted, so a value equal to the automatic proposal is not a choice and
        is not stored — it would otherwise freeze a proposal the next mapping
        change should redo. A row set back to its proposal drops its choice.
        """
        auto = {str(r["row"]): r["lid"] or ""
                for r in _built(self, dict(rec, matches={}))["review"]}
        out = dict(rec.get("matches") or {})
        for k, v in form.items():
            if k.startswith("match_") and k[6:] in auto:
                v = str(v or "")[:24]
                if v == auto[k[6:]]:
                    out.pop(k[6:], None)
                else:
                    out[k[6:]] = v
        rec["matches"] = out

    @staticmethod
    def _line_text(li) -> str:
        desc = " ".join(str(li.get("description") or "").split())
        if len(desc) > 70:
            desc = desc[:69] + "…"
        return (f"{li.get('section') or ''}·{BQ._item_no(li.get('item_no'))} — {desc}"
                + (f" ({li.get('unit')})" if li.get("unit") else ""))

    def extra_html(self, token, rec, built):
        boq = self._boq(rec)
        lines = self._lines(boq)
        by_id = {BQ._line_id(li["line_id"]): li for li in lines}
        review = built["review"]
        if not review:
            return ""
        budget = MATCH_OPTIONS_CAP
        body = []
        for r in review:
            # What a row offers: its candidates when it names several lines;
            # every line carrying its number (any section) when it matched one
            # or names a number in the wrong section; and the whole schedule —
            # while the page's budget lasts — when it matches nothing at all.
            if r["cands"]:
                offer = r["cands"]
            elif r["same"]:
                offer = r["same"]
            else:
                offer = list(by_id) if budget >= len(by_id) else []
            if r["lid"] and r["lid"] not in offer:
                offer = [r["lid"]] + offer
            budget -= len(offer)
            cur = r["lid"] or ""
            opts = ['<option value="">&#8212; leave this row out &#8212;</option>']
            for lid in offer:
                li = by_id.get(lid)
                if li is None:
                    continue
                sel = " selected" if lid == cur else ""
                opts.append(f'<option value="{P.esc(lid)}"{sel}>{P.esc(self._line_text(li))}</option>')
            if r["lid"]:
                status = ('<span class="imp-ok">&#10003; matched</span>' if r["auto"] else
                          '<span class="imp-ok">&#10003; your choice</span>')
            elif r["cands"]:
                status = '<span class="imp-bad">choose which line</span>'
            elif r["why"] == "left out":
                status = '<span class="imp-note">left out</span>'
            else:
                status = '<span class="imp-bad">no match</span>'
            if not offer and not r["cands"] and not r["lid"]:
                status += (' <span class="imp-note">(too many rows to list every line '
                           '— correct the item number on the sheet)</span>')
            body.append(
                f'<tr><td class="imp-rn">{int(r["row"])}</td>'
                f'<td>{P.esc(r["section"])}</td><td>{P.esc(r["item"])}</td>'
                f'<td>{P.esc((r["desc"] or "")[:90])}</td><td>{P.esc(r["qty"])}</td>'
                f'<td><select name="match_{int(r["row"])}">{"".join(opts)}</select>'
                f'<div class="imp-note">{status}'
                + (f' &middot; {P.esc(r["why"])}' if r["why"] and r["why"] != "left out" else "")
                + '</div></td></tr>')
        return f"""
    <div class="imp-card">
      <h2>Which BOQ line each row is</h2>
      <p class="imp-note">Against <b>{P.esc(boq.get("ref"))}</b>. A row whose item
      number (and section, and description, where you mapped them) names exactly
      one line is matched; a number the schedule carries twice is <b>never chosen
      for you</b>. Change any row, or leave it out. Press <b>Update preview</b>
      after a change, or confirm — what you choose here is what is filled in.</p>
      <div class="imp-wrap"><table class="imp-grid imp-match">
        <thead><tr><th>Row</th><th>Section</th><th>Item</th><th>Description on the
        sheet</th><th>Qty</th><th>BOQ line</th></tr></thead>
        <tbody>{"".join(body)}</tbody></table></div>
    </div>"""


class ChallanKind(BoqLineKind):
    key = "challan"
    title = "a delivery challan"
    noun = "delivery challan"
    endpoint = "challan.create_dc"
    save_label = "Raise challan"
    qty_label = "Dispatch qty"
    qty_about = ("How much of the line is going out on this load. A word or a sum "
                 "written as text is left out for you to type — never turned into 0.")
    qty_prefer = r"dispatch|despatch|this|sent|supplied"

    def back_url(self, ctx):
        return url_for("challan.create_dc", boq=ctx.get("boq_id")) if ctx.get("boq_id") \
            else url_for("challan.list_dcs")

    def apply(self, token, rec, built):
        return DC.create_dc(imported={
            "boq_id": rec["ctx"]["boq_id"],
            "chosen": {it["lid"] for it in built["items"]},
            "qty": {it["lid"]: it["qty"] for it in built["items"]},
            "banner_html": _banner(self, rec, built)})


class DraftPOKind(BoqLineKind):
    key = "dpo"
    title = "a draft purchase order"
    noun = "draft purchase order"
    endpoint = "po_draft.create_po"
    save_label = "Raise draft PO"
    qty_label = "Order qty"
    qty_about = ("How much of the line the supplier is asked to price. A word or a "
                 "sum written as text is left out for you to type.")
    qty_prefer = r"order|required|req\.?"
    extra_targets = (SI.target("pcs", "Pcs", kw=r"\bpcs\b|pieces|\bpc\b"),
                     # Make (26 October 2026) — prefills the picker's Make box.
                     SI.target("make", "Make", kw=_MAKE_KW))

    def back_url(self, ctx):
        return url_for("po_draft.create_po", boq=ctx.get("boq_id")) if ctx.get("boq_id") \
            else url_for("po_draft.list_pos")

    def _extra_values(self, c, n, notes):
        pcs, _w = _t(c, "pcs", SI.cell_code)
        return {"pcs": pcs[:16], "make": _make_of(c, n, notes)}

    def apply(self, token, rec, built):
        return DPO.create_po(imported={
            "boq_id": rec["ctx"]["boq_id"],
            "chosen": {it["lid"] for it in built["items"]},
            "qty": {it["lid"]: it["qty"] for it in built["items"]},
            "pcs": {it["lid"]: it["pcs"] for it in built["items"] if it.get("pcs")},
            "make": {it["lid"]: it["make"] for it in built["items"] if it.get("make")},
            "banner_html": _banner(self, rec, built)})


class RAKind(BoqLineKind):
    key = "ra"
    title = "claim quantities for an RA bill"
    noun = "RA bill"
    endpoint = "ra.create_ra"
    save_label = "Save RA bill"
    qty_label = "This claim qty"
    qty_about = ("The quantity claimed on THIS bill for the line — not the BOQ "
                 "quantity, and not the cumulative figure. The over-claim block "
                 "checks it on save exactly as it checks a typed claim.")
    qty_prefer = r"this|present|current|claim|now|executed"
    extra_targets = (SI.target("rate", "Rate (₹)", kw=r"\brate\b", avoid=r"amount|total"),)

    def context(self, args):
        ctx, error, resp = _boq_context(args)
        if error or not ctx:
            return ctx, error, resp
        leg = str(args.get("leg") or "supply").strip()
        if leg not in RA.LEGS:
            leg = "supply"
        ctx["leg"] = leg
        # The C1 order of working, refused HERE exactly as `/ra/create` refuses
        # it — a sheet uploaded for a claim that cannot be raised is work for
        # nothing.
        return ctx, "", RA._c1_refusal(ctx["boq_id"], leg)

    def back_url(self, ctx):
        return url_for("ra.create_ra", boq=ctx.get("boq_id"), leg=ctx.get("leg")) \
            if ctx.get("boq_id") else url_for("ra.list_ras")

    def _extra_values(self, c, n, notes):
        if "rate" not in c:
            return {}
        rate, why = _t(c, "rate", SI.cell_number)
        if why:
            notes.append(_note(n, f"Rate: {why} — the approved rate is used."))
            return {}
        if rate is None or rate < 0:
            return {}
        return {"rate": BI.num_text(rate)}

    def apply(self, token, rec, built):
        entered = {}
        for it in built["items"]:
            row = {"qty": it["qty"]}
            if it.get("rate"):
                row["rate"] = it["rate"]
            entered[it["lid"]] = row
        return RA.create_ra(imported={
            "boq_id": rec["ctx"]["boq_id"], "leg": rec["ctx"].get("leg", "supply"),
            "entered": entered, "banner_html": _banner(self, rec, built)})


# ── The three registers — reviewed, then created ─────────────────────────────

class RegisterKind(Kind):
    """Many records from one sheet: every row checked by the register's own
    validator, listed with its verdict, and created only on *Create*."""
    register = True
    max_rows = 500
    list_endpoint = ""
    plural = ""

    def row_view(self, item) -> list:
        return []

    def heads(self) -> list:
        return []

    def create(self, item) -> None:
        raise NotImplementedError

    def save(self, token, rec, built):
        ok = [it for it in built["items"] if not it["error"]]
        for it in ok:
            self.create(it)
        _imports().pop(token, None)
        bad = len(built["items"]) - len(ok)
        msg = (f"{len(ok)} {self.plural if len(ok) != 1 else self.noun} added from "
               f"{rec.get('filename')}.")
        if bad:
            msg += (f" {bad} row{'s were' if bad != 1 else ' was'} not added — fix "
                    f"{'them' if bad != 1 else 'it'} in the sheet and import "
                    f"{'those rows' if bad != 1 else 'that row'} again.")
        dest = self.list_endpoint if auth.can_reach(self.list_endpoint) else self.endpoint
        return redirect(url_for(dest, msg=msg, type="success" if ok else "error"))


class AddressKind(RegisterKind):
    key = "address"
    title = "addresses"
    noun = "address"
    plural = "addresses"
    endpoint = "address.add_address"
    list_endpoint = "address.list_addresses"

    def schema(self, ctx):
        return {"targets": [
            SI.target("label", "Label", kw=r"\blabel\b|\balias\b|short\s*name|display"),
            SI.target("type", "Type", kw=r"\btype\b|category|\bkind\b"),
            SI.target("company", "Company / firm",
                      kw=r"company|\bfirm\b|vendor|supplier|party|customer|client|\bname\b",
                      avoid=r"contact|person|attn"),
            SI.target("phone", "Phone", kw=r"phone|mobile|\bmob\b|\btel\b|contact\s*no|cell"),
            SI.target("contact_name", "Contact person", kw=r"contact|person|attn",
                      avoid=r"\bno\b|number|phone|mobile|e-?mail"),
            SI.target("line1", "Address line 1", required=True,
                      about="The building, plot or unit — the first line of the "
                            "address. The address book refuses an address without one.",
                      kw=r"line\s*1|address\s*1|building|\bplot\b|^address$|\baddress\b",
                      avoid=r"line\s*2|address\s*2|e-?mail|landmark"),
            SI.target("line2", "Address line 2",
                      kw=r"line\s*2|address\s*2|street|\broad\b|locality"),
            SI.target("landmark", "Landmark", kw=r"landmark|\bnear\b"),
            SI.target("city", "City", required=True,
                      about="The city or town.",
                      kw=r"\bcity\b|\btown\b|village"),
            SI.target("state", "State", required=True,
                      about="The State or Union Territory, spelled as the address "
                            "book lists it (Maharashtra, Karnataka…). Upper or lower "
                            "case does not matter; an abbreviation (MH) is not read.",
                      kw=r"\bstate\b"),
            SI.target("pincode", "PIN code", required=True,
                      about="Six digits, not starting with 0.",
                      kw=r"\bpin\b|pincode|pin\s*code|postal|\bzip\b"),
            SI.target("email", "E-mail", kw=r"e-?mail"),
            SI.target("gstin", "GSTIN", kw=r"\bgst"),
        ], "any_of": [{
            "keys": ("label", "company"),
            "label": "Label — or Company",
            "about": "What the address is listed as in every picker. A row with no "
                     "label is listed under its company name.",
        }]}

    def intro_html(self, ctx):
        return ("<p class=\"imp-note\">Each row becomes one address in the book, checked "
                "by exactly the rules the <b>Add Address</b> form uses — a new GSTIN "
                "must pass its check character. A row whose label is already in the "
                "book is not added twice.</p>")

    def options_html(self, rec):
        cur = (rec.get("options") or {}).get("type") or "office"
        opts = "".join(f'<option value="{P.esc(k)}"{" selected" if k == cur else ""}>'
                       f'{P.esc(v)}</option>' for k, v in AD.ADDRESS_TYPES.items())
        return f"""
    <div class="imp-card">
      <h2>Rows that do not say their type</h2>
      <div class="form-group" style="max-width:18rem;">
        <label for="opt_type">File them as</label>
        <select id="opt_type" name="opt_type">{opts}</select>
      </div>
      <p class="imp-note">A row whose Type column names one (Vendor, Project Site,
      Office&hellip;) keeps its own.</p>
    </div>"""

    def read_options(self, form, rec):
        t = form.get("opt_type")
        if t in AD.ADDRESS_TYPES:
            rec.setdefault("options", {})["type"] = t

    @staticmethod
    def _type_of(raw: str, default: str):
        if not raw:
            return default, ""
        n = _norm(raw)
        for k, v in AD.ADDRESS_TYPES.items():
            if n in (_norm(k), _norm(v)):
                return k, ""
        return "", (f"type “{raw}” is not one the address book has "
                    f"({', '.join(AD.ADDRESS_TYPES.values())})")

    def build(self, rows, rec):
        default = (rec.get("options") or {}).get("type") or "office"
        taken = {_norm(a.get("label")) for a in (STORE.get("addresses") or {}).values()}
        states = {_norm(s): s for s in AD.INDIAN_STATES}
        seen, items, notes = {}, [], []
        for r in rows:
            c, n = r["cells"], r["row"]
            vals, err = {}, ""
            for key in ("label", "company", "contact_name", "line1", "line2",
                        "landmark", "city", "email"):
                vals[key], why = _t(c, key)
                if why and not err:
                    err = f"{key}: {why}"
            for key in ("pincode", "phone"):
                vals[key], why = _t(c, key, SI.cell_code)
                if why and not err:
                    err = f"{key}: {why}"
            vals["gstin"], _w = _t(c, "gstin", SI.cell_code)
            st, _w = _t(c, "state")
            vals["state"] = states.get(_norm(st), st)
            atype, terr = self._type_of(_t(c, "type")[0], default)
            vals["type"] = atype
            err = err or terr
            if not vals["label"]:
                vals["label"] = vals["company"] or vals["contact_name"]
            data, verr = AD._validate(vals)
            err = err or verr or ""
            if not err:
                err = AD._gst_status_error(data, {}) or ""
            lab = _norm(data.get("label"))
            if not err and lab in taken:
                err = "an address with this label is already in the book"
            if not err and lab in seen:
                err = f"row {seen[lab]} already has this label"
            if not err:
                seen[lab] = n
            items.append({"row": n, "data": data, "error": err})
        good = sum(1 for it in items if not it["error"])
        return {"items": items, "notes": notes,
                "stats": [(good, "will be added"), (len(items) - good, "will not")]}

    def heads(self):
        return ["Label", "Type", "City", "State", "GSTIN"]

    def row_view(self, it):
        d = it["data"]
        return [d.get("label"), AD.ADDRESS_TYPES.get(d.get("type"), d.get("type")),
                d.get("city"), d.get("state"), d.get("gstin")]

    def create(self, it):
        AD.create_record(it["data"])


class SpecKind(RegisterKind):
    key = "spec"
    title = "specification clauses"
    noun = "clause"
    plural = "clauses"
    endpoint = "spec.add_spec"
    list_endpoint = "spec.list_specs"

    def schema(self, ctx):
        return {"targets": [
            SI.target("code", "Code", required=True,
                      about="The clause's code — no spaces, unique in the library. "
                            "Several rows with one code are one clause in several "
                            "sizes; a row with no code under a coded row is another "
                            "size of that clause.",
                      kw=r"\bcode\b|spec\.?\s*(?:no|id)"),
            SI.target("title", "Title", required=True,
                      about="The short name the BOQ picker shows.",
                      kw=r"\btitle\b|short\s*name|\bname\b", avoid=r"descr"),
            SI.target("spec_text", "Clause text", required=True,
                      about="The full clause — it becomes the BOQ line description.",
                      kw=r"descr|specification|clause|particular|\btext\b"),
            SI.target("category", "Category", kw=r"categor|\bgroup\b"),
            SI.target("supply_hsn", "HSN (supply)", kw=r"\bhsn\b"),
            SI.target("install_sac", "SAC (installation)", kw=r"\bsac\b"),
            SI.target("supply_gst_rate", "GST % (supply)",
                      kw=r"(?:supply|material|hsn).*(?:gst|tax)|(?:gst|tax).*(?:supply|material)"),
            SI.target("install_gst_rate", "GST % (installation)",
                      kw=r"(?:install|labou?r|sac).*(?:gst|tax)|(?:gst|tax).*(?:install|labou?r)"),
            SI.target("var_label", "Size / variant label",
                      kw=r"\bsize\b|variant|\bdia\b|diameter|\bnb\b"),
            SI.target("var_dimension", "Dimension", kw=r"dimension|\bdim\b",
                      avoid=r"unit"),
            SI.target("var_dim_unit", "Dimension unit", kw=r"dim\w*\s*unit"),
            SI.target("var_unit", "Unit", kw=r"\bunits?\b|\buom\b", avoid=r"rate|dim"),
            SI.target("var_supply", "Supply base rate",
                      kw=r"supply.*rate|material.*rate|rate.*supply"),
            SI.target("var_install", "Installation base rate",
                      kw=r"install.*rate|labou?r.*rate|rate.*install"),
        ]}

    def intro_html(self, ctx):
        return ("<p class=\"imp-note\">Each code becomes one clause in the library, checked "
                "by exactly the rules the <b>Add Spec</b> form uses, with one size per "
                "row. A code already in the library is not added again.</p>")

    def build(self, rows, rec):
        cats = {_norm(c): c for c in SP.CATEGORIES}
        groups, order, notes = {}, [], []
        last = None
        for r in rows:
            c, n = r["cells"], r["row"]
            code, _w = _t(c, "code", SI.cell_code)
            if not code and last is not None:
                code = last
            if not code:
                groups.setdefault(f"#row{n}", {"rows": [n], "first": c, "variants": []})
                order.append(f"#row{n}")
                continue
            last = code
            g = groups.get(_norm(code))
            if g is None:
                g = groups[_norm(code)] = {"rows": [], "first": c, "variants": [], "code": code}
                order.append(_norm(code))
            g["rows"].append(n)
            g["variants"].append(c)
        items = []
        for key in order:
            g = groups[key]
            n0 = g["rows"][0]
            if key.startswith("#row"):
                items.append({"row": n0, "data": {}, "error": "no code", "rows": g["rows"]})
                continue
            f = g["first"]
            md = MultiDict()
            md["code"] = g["code"]
            for k in ("title", "spec_text"):
                md[k] = _t(f, k)[0]
            cat = _t(f, "category")[0]
            md["category"] = cats.get(_norm(cat), cat) if cat else SP.DEFAULT_CATEGORY
            for k in ("supply_hsn", "install_sac"):
                md[k] = _t(f, k, SI.cell_code)[0]
            err = ""
            for k in ("supply_gst_rate", "install_gst_rate"):
                v, why = _t(f, k, SI.cell_number)
                if why and not err:
                    err = f"{k}: {why}"
                if v is not None:
                    md[k] = BI.num_text(v)
            for vc in g["variants"]:
                md.add("var_label", _t(vc, "var_label")[0])
                md.add("var_dimension", _t(vc, "var_dimension", SI.cell_code)[0])
                md.add("var_dim_unit", _t(vc, "var_dim_unit")[0])
                md.add("var_unit", _t(vc, "var_unit")[0])
                for k, field in (("var_supply", "supply"), ("var_install", "installation")):
                    v, why = _t(vc, k, SI.cell_number)
                    if why and not err:
                        err = f"{field} rate: {why}"
                    md.add(k, BI.num_text(v))
            data, verr = SP._validate(md)
            err = err or verr or ""
            items.append({"row": n0, "data": data, "error": _plain(err), "rows": g["rows"]})
        good = sum(1 for it in items if not it["error"])
        return {"items": items, "notes": notes,
                "stats": [(good, "will be added"), (len(items) - good, "will not")]}

    def heads(self):
        return ["Code", "Title", "Category", "Sizes", "Rows"]

    def row_view(self, it):
        d = it["data"]
        variants = d.get("variants") or []
        sizes = ", ".join(v.get("label") or "" for v in variants if v.get("label")) \
            or ("unsized" if variants else "")
        rows = it.get("rows") or [it["row"]]
        return [d.get("code"), d.get("title"), d.get("category"), sizes,
                f"{rows[0]}–{rows[-1]}" if len(rows) > 1 else str(rows[0])]

    def create(self, it):
        SP.create_record(it["data"])


class EmployeeKind(RegisterKind):
    key = "employee"
    title = "employees"
    noun = "employee"
    plural = "employees"
    endpoint = "employee.new_employee"
    list_endpoint = "employee.list_employees"

    def schema(self, ctx):
        return {"targets": [
            SI.target("name", "Name", required=True,
                      about="The person's name — the only thing the register needs.",
                      kw=r"\bname\b|employee|\bstaff\b|worker",
                      avoid=r"\bcode\b|\bid\b|\bno\.?$|number|site|designat"),
            SI.target("code", "Employee code",
                      kw=r"\bcode\b|emp\.?\s*(?:no|id)|employee\s*(?:no|id|code)|\bid\b|staff\s*no"),
            SI.target("designation", "Designation",
                      kw=r"designat|position|\brole\b|\bpost\b|\btrade\b"),
            SI.target("site", "Site", kw=r"\bsite\b|location|posted|project"),
            SI.target("date_joined", "Date joined", kw=r"join|\bdoj\b|\bdate\b"),
            SI.target("day_rate", "Day rate (₹)",
                      kw=r"day\s*rate|daily|\bwage|salary|per\s*day|\brate\b"),
            SI.target("active", "Active", kw=r"\bactive\b|\bstatus\b"),
            SI.target("notes", "Notes", kw=r"\bnote|remark"),
        ]}

    def intro_html(self, ctx):
        return ("<p class=\"imp-note\">Each row becomes one person on the register, checked "
                "by exactly the rules the <b>New Employee</b> form uses. ⚠ The rate is "
                "a <b>DAY</b> rate. A site is matched to the address book "
                "<b>exactly</b> by its label and never guessed.</p>")

    @staticmethod
    def _sites() -> dict:
        out = {}
        for aid, a in (STORE.get("addresses") or {}).items():
            if a.get("type") in EMP.SITE_TYPES and AD.is_active(a):
                lab = str(a.get("label") or "").strip()
                if lab:
                    out.setdefault(lab, aid)
        return out

    def build(self, rows, rec):
        sites = self._sites()
        names = {_norm(e.get("name")) for e in (STORE.get("employees") or {}).values()}
        codes, items, notes = {}, [], []
        for r in rows:
            c, n = r["cells"], r["row"]
            err = ""
            form = {}
            for k in ("name", "designation", "notes"):
                form[k], why = _t(c, k)
                if why and not err:
                    err = f"{k}: {why}"
            form["code"], _w = _t(c, "code", SI.cell_code)
            d, why = _t(c, "date_joined", SI.cell_date)
            form["date_joined"] = d
            err = err or (f"date joined: {why}" if why else "")
            rate, why = _t(c, "day_rate", SI.cell_number)
            form["day_rate"] = BI.num_text(rate)
            err = err or (f"day rate: {why}" if why else "")
            act, _w = _t(c, "active")
            a = _norm(act)
            if a in ("", "yes", "y", "true", "active", "1", "working"):
                form["active"] = "1"
            elif a in ("no", "n", "false", "inactive", "left", "0"):
                form["active"] = ""
            else:
                err = err or f"active: “{act}” is neither yes nor no"
            site, _w = _t(c, "site")
            form["site_id"] = ""
            if site:
                aid = sites.get(site.strip())
                if aid is None:
                    err = err or (f"no site called “{site}” in the address book — add "
                                  f"it there first, or clear the cell")
                else:
                    form["site_id"] = aid
            data, verr = EMP._validate(form)
            err = err or verr or ""
            code = _norm(data.get("code"))
            if not err and code and code in codes:
                err = f"row {codes[code]} already has the code {data.get('code')}"
            if not err and code:
                codes[code] = n
            if not err and _norm(data.get("name")) in names:
                notes.append(_note(n, f"{data.get('name')} is already on the register "
                                      f"under this name — this row adds another person."))
            items.append({"row": n, "data": data, "error": err})
        good = sum(1 for it in items if not it["error"])
        return {"items": items, "notes": notes,
                "stats": [(good, "will be added"), (len(items) - good, "will not")]}

    def heads(self):
        return ["Name", "Code", "Designation", "Site", "Day rate"]

    def row_view(self, it):
        d = it["data"]
        rate = d.get("day_rate")
        return [d.get("name"), d.get("code"), d.get("designation"), d.get("site"),
                "" if rate in (None, "") else f"₹ {float(rate):,.2f}"]

    def create(self, it):
        EMP.create_record(it["data"])


def _plain(msg: str) -> str:
    """A validator's sentence as plain text. `spec._validate()` writes its
    quotes as `&quot;` because its form interpolates the message raw; here every
    message is escaped at the interpolation site, so the entity is undone first
    rather than escaped a second time."""
    return str(msg or "").replace("&quot;", "\"")


KINDS = {k.key: k for k in (PurchaseKind(), QuotationKind(), MeasurementKind(),
                            ChallanKind(), DraftPOKind(), RAKind(),
                            AddressKind(), SpecKind(), EmployeeKind())}


# =============================================================================
# STAGING — purge, own, cap
# =============================================================================

def purge(now: float = None) -> int:
    """`boqimport.purge()`'s rule: older than 24 hours, or undatable, goes."""
    now = time.time() if now is None else now
    gone = 0
    for tok, rec in list(_imports().items()):
        ts = rec.get("created_ts") if isinstance(rec, dict) else None
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or now - ts > STAGE_TTL_SECONDS:
            del _imports()[tok]
            gone += 1
    return gone


def _own(token: str, kind):
    """The staged import under `token` if the signed-in user raised it, FOR
    THIS KIND — a purchase-order token is not a way into the address book."""
    rec = _imports().get(str(token or ""))
    if not isinstance(rec, dict) or rec.get("kind") != kind.key:
        return None
    uid = _uid()
    if not uid or rec.get("user_id") != uid:
        return None
    try:
        if rec["grid"][int(rec.get("sheet_index") or 0)] is None:
            return None
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    return rec


def _cap_per_user(uid: str) -> None:
    mine = sorted(((rec.get("created_ts") or 0, tok) for tok, rec in _imports().items()
                   if isinstance(rec, dict) and rec.get("user_id") == uid),
                  reverse=True)
    for _ts, tok in mine[MAX_STAGED_PER_USER:]:
        del _imports()[tok]


def _grid(rec):
    return rec["grid"][int(rec.get("sheet_index") or 0)]


def _effective(kind, rec):
    """`(grid, schema, hdr, mapping)` for the staged import as it stands."""
    grid = _grid(rec)
    schema = kind.schema(rec.get("ctx") or {})
    hdr = SI.schema_header(grid, schema, rec.get("header_row"))
    mapping = SI.schema_clean(grid, rec.get("mapping") or {}, schema)
    return grid, schema, hdr, mapping


def _first_mapping(kind, rec) -> None:
    """The mapping a sheet opens with: the layout last confirmed for this kind
    and heading, else the guess. Either way the preview shows it first."""
    grid = _grid(rec)
    schema = kind.schema(rec.get("ctx") or {})
    hdr = SI.schema_header(grid, schema, rec.get("header_row"))
    sig = SI.schema_signature(grid, hdr, kind.key)
    lay = _layouts().get(sig) if sig else None
    if isinstance(lay, dict):
        rec["mapping"] = SI.schema_clean(grid, lay.get("mapping") or {}, schema)
        rec["known"] = True
    else:
        rec["mapping"] = SI.schema_guess(grid, schema, hdr)
        rec["known"] = False
    rec["layout"] = sig


def stage(kind, wb: dict, filename: str, uid: str, ctx: dict) -> str:
    """Stage a read workbook for `uid` under a fresh token and return it."""
    token = secrets.token_urlsafe(24)
    sel = SI.schema_pick(wb, kind.schema(ctx))
    rec = {
        "id": token, "token": token, "kind": kind.key, "user_id": uid,
        "created_at": _now(), "created_ts": time.time(),
        "filename": filename, "format": wb["format"],
        "sheets": wb["sheets"], "grid": wb["grid"], "sheet_index": sel,
        "header_row": None, "mapping": {}, "ctx": dict(ctx or {}),
        "options": {}, "matches": {}, "confirmed": False,
        "layout": "", "known": False,
    }
    _first_mapping(kind, rec)
    _imports()[token] = rec
    _cap_per_user(uid)
    return token


def _upsert_layout(kind, rec) -> None:
    grid, _schema, hdr, mapping = _effective(kind, rec)
    sig = SI.schema_signature(grid, hdr, kind.key)
    if not sig:
        return
    lay = _layouts().get(sig)
    if isinstance(lay, dict):
        lay["mapping"] = dict(mapping)
        lay["use_count"] = int(lay.get("use_count") or 0) + 1
    else:
        _layouts()[sig] = {"id": sig, "signature": sig, "kind": kind.key,
                           "mapping": dict(mapping), "created_by": _uid(),
                           "created_at": _now(), "use_count": 1}


def _built(kind, rec) -> dict:
    """The rows as the kind reads them — rebuilt from the staged grid on every
    request, so what is shown and what is filled in cannot drift apart."""
    grid, _schema, hdr, mapping = _effective(kind, rec)
    rows, repeats = SI.schema_rows(grid, mapping, hdr)
    built = kind.build(rows, rec)
    built["rows"] = len(rows)
    built["repeats"] = repeats
    return built


def _problems(kind, rec, built) -> list:
    grid, schema, hdr, mapping = _effective(kind, rec)
    probs = []
    if not hdr:
        probs.append("No heading row was found on this sheet. Type the row the "
                     "headings are on, then choose what each column holds.")
    probs += SI.schema_problems(grid, mapping, schema)
    if built["rows"] > kind.max_rows:
        probs.append(f"This sheet has {built['rows']} rows and one {kind.noun} takes "
                     f"at most {kind.max_rows}. Split it — nothing is cut off.")
    if not probs and not built["items"]:
        probs.append(f"Nothing on this sheet can be imported into the {kind.noun} — "
                     f"see the notes below.")
    probs += kind.problems(rec, built)
    return probs


# =============================================================================
# RENDERING
# =============================================================================

DOC_IMPORT_STYLES = """
<style>
.imp-hrow{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-top:.6rem;}
.imp-hrow input[type=number]{width:6rem;}
.imp-boqs{width:100%;border-collapse:collapse;font-size:.85rem;}
.imp-boqs th,.imp-boqs td{border-top:1px solid var(--border,#e2e8f0);padding:.45rem .5rem;text-align:left;}
.imp-rev td.st-ok{color:#15803d;font-weight:600;}
.imp-rev td.st-bad{color:#b91c1c;}
/* The matching tables scroll sideways inside .imp-wrap on a phone rather than
   squeezing the BOQ line's dropdown to a few characters. */
.imp-grid.imp-match{min-width:46rem;}
.imp-grid.imp-match select{max-width:none;width:100%;min-width:16rem;}
</style>
"""


def _page(title: str, body: str) -> str:
    """A finished page. Never Jinja-rendered (ABOUT.md §1)."""
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{Q.QUOTATION_STYLES}{BI.IMPORT_STYLES}{DOC_IMPORT_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE}</p></footer>
</main>
</body></html>"""


def _not_found(kind):
    """The one answer for a token that is not yours, has expired, was used, or
    belongs to another kind. Returned DIRECTLY with 404 — the app-wide 404
    handler redirects to the dashboard (`boqimport._not_found()`'s reason)."""
    body = f"""
  <div class="page-top"><h1>Import <span>not found</span></h1></div>
  <div class="imp-card">
    <p>This import is not available. It may have expired (an upload is kept for
    24 hours), it may already have been used, or it belongs to someone else.</p>
    <p class="imp-note">Nothing was saved. Upload the file again to start over.</p>
    <div class="imp-actions">
      <a class="btn" href="{_url("upload", kind)}">Upload a sheet</a>
    </div>
  </div>"""
    return _page("Import not found", body), 404


def _ctx_args(ctx: dict) -> dict:
    """A staged context as the query string the upload page reads it from."""
    out = {}
    if (ctx or {}).get("boq_id"):
        out["boq"] = ctx["boq_id"]
    if (ctx or {}).get("leg"):
        out["leg"] = ctx["leg"]
    return out


def _boq_chooser(kind) -> str:
    """For a schedule-bound import opened with no schedule: which one."""
    sup = BQ.superseded_ids()
    rows = []
    for bid, b in sorted((STORE.get("boqs") or {}).items(),
                         key=lambda kv: str(kv[1].get("ref") or ""), reverse=True):
        if bid in sup:
            continue
        if kind.key == "ra":
            go = (f'<a class="btn btn-ghost" href="{_url("upload", kind, boq=bid, leg="supply")}">Supply</a> '
                  f'<a class="btn btn-ghost" href="{_url("upload", kind, boq=bid, leg="installation")}">Installation</a>')
        else:
            go = f'<a class="btn btn-ghost" href="{_url("upload", kind, boq=bid)}">Import against this</a>'
        rows.append(f"<tr><td><b>{P.esc(b.get('ref'))}</b></td>"
                    f"<td>{P.esc(b.get('project_name'))}</td>"
                    f"<td>{P.esc(b.get('account_name'))}</td><td>{go}</td></tr>")
    table = (f'<table class="imp-boqs"><thead><tr><th>BOQ</th><th>Project</th>'
             f'<th>Party</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
             if rows else '<p class="imp-note">There is no bill of quantities yet.</p>')
    return f"""
  <div class="imp-card">
    <h2>Which schedule is this {P.esc(kind.noun)} raised against?</h2>
    <p class="imp-note">Only the current revision of each schedule is listed.</p>
    {table}
  </div>"""


def _upload_page(kind, ctx: dict, error: str = "", blocked: bool = False) -> str:
    """
    The upload form and the legend. `blocked` — the document cannot take an
    import right now (the quotation picker reading the catalogue) — draws the
    reason and no form: a form that can only produce that refusal again is a
    control that must not be drawn.
    """
    avail = SI.available()
    alert = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>' if error else ""
    missing = [k for k, ok in avail.items() if not ok]
    if missing:
        alert += (f'<div class="alert alert-error">&#10007; {P.esc(SI.UNAVAILABLE)} '
                  f'(missing: {P.esc(", ".join(missing))})</div>')
    back = kind.back_url(ctx)
    if blocked:
        chooser = form = ""
    elif kind.needs_boq and not ctx.get("boq_id"):
        chooser = _boq_chooser(kind)
        form = ""
    else:
        chooser = ""
        against = ""
        if ctx.get("boq_id"):
            boq = (STORE.get("boqs") or {}).get(ctx["boq_id"]) or {}
            against = (f'<p class="imp-note">Against <b>{P.esc(boq.get("ref"))}</b> &middot; '
                       f'{P.esc(boq.get("project_name"))}'
                       + (f' &middot; <b>{P.esc(ctx["leg"])}</b> leg' if ctx.get("leg") else "")
                       + "</p>")
        lands = ("the rows are listed for you to check, and nothing is added until you "
                 "press <b>Create</b>" if kind.register else
                 f"the ordinary form opens filled in, and <b>nothing is saved until you "
                 f"press {P.esc(kind.save_label)}</b>")
        form = f"""
  <div class="imp-card">
    <h2>Your own sheet, any layout</h2>
    {against}
    <form method="POST" enctype="multipart/form-data" class="imp-file"
          action="{_url("upload", kind, **_ctx_args(ctx))}">
      <input type="file" name="workbook" accept=".xlsx,.xls" required/>
      <button class="btn" type="submit">Upload</button>
    </form>
    <p class="imp-note">An <b>.xlsx</b> or <b>.xls</b> file up to
    {SI.MAX_UPLOAD_BYTES // 1048576} MB. A workbook with macros (.xlsm) is refused
    &mdash; save it as .xlsx first. The file is read once and not kept.</p>
    <p class="imp-note">Next you see the sheet with a guess under every column; choose
    what each one holds, or <i>ignore</i> it. Then {lands}.</p>
    {kind.intro_html(ctx)}
  </div>
  {BI.legend_html(kind.legend(ctx), kind.noun)}"""
    body = f"""
  {alert}
  <div class="page-top">
    <h1>Import <span>{P.esc(kind.title)}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{back}" class="btn btn-ghost">&#8592; Back</a>
    </div>
  </div>
  {chooser}{form}"""
    return _page(f"Import {kind.title}", body)


def _target_select(col: int, current: str, schema: dict) -> str:
    opts = ['<option value="">&#8212; ignore &#8212;</option>']
    for t in schema["targets"]:
        sel = " selected" if t["key"] == current else ""
        star = " *" if t["required"] else ""
        opts.append(f'<option value="{P.esc(t["key"])}"{sel}>{P.esc(t["label"])}{star}</option>')
    return (f'<select name="map_{int(col)}" aria-label="Column {SI.col_letter(col)}">'
            f'{"".join(opts)}</select>')


def _notes_html(notes: list, limit: int = BANNER_NOTES) -> str:
    items = []
    for nt in notes[:limit]:
        cls = ' class="is-red"' if nt["level"] == "red" else ""
        items.append(f"<li{cls}>Row {int(nt['row'])}: {P.esc(nt['msg'])}</li>")
    if len(notes) > limit:
        items.append(f"<li>&hellip; and {len(notes) - limit} more.</li>")
    return f'<ul class="imp-flags">{"".join(items)}</ul>' if items else ""


def _stats_html(built: dict) -> str:
    parts = [f'<span><b>{int(built["rows"])}</b> row{"s" if built["rows"] != 1 else ""} read</span>']
    parts += [f"<span><b>{int(n)}</b> {P.esc(w)}</span>" for n, w in built.get("stats") or []]
    if built.get("repeats"):
        parts.append(f'<span><b>{int(built["repeats"])}</b> repeated heading rows skipped</span>')
    return f'<div class="imp-stats">{"".join(parts)}</div>'


def _review_html(kind, built) -> str:
    """The three registers: every row, and the validator's verdict on it."""
    heads = "".join(f"<th>{P.esc(h)}</th>" for h in kind.heads())
    body = []
    for it in built["items"]:
        cells = "".join(f"<td>{P.esc(v if v is not None else '')}</td>"
                        for v in kind.row_view(it))
        st = ('<td class="st-ok">&#10003; will be added</td>' if not it["error"] else
              f'<td class="st-bad">&#10007; {P.esc(it["error"])}</td>')
        body.append(f'<tr><td class="imp-rn">{int(it["row"])}</td>{cells}{st}</tr>')
    return (f'<div class="imp-wrap"><table class="imp-grid imp-rev"><thead><tr><th>Row</th>'
            f'{heads}<th>Status</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _preview_page(kind, token: str, rec: dict, problems=None, error: str = "") -> str:
    grid, schema, hdr, mapping = _effective(kind, rec)
    built = _built(kind, rec)
    if problems is None:
        # Said on the plain GET as well — `boqimport`'s preview does the same —
        # so the operator sees what confirm will refuse before pressing it.
        problems = _problems(kind, rec, built)
    alert = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>' if error else ""
    if problems:
        alert += ('<div class="alert alert-error" style="display:block;">'
                  '<div style="font-weight:700;margin-bottom:.3rem;">&#10007; '
                  f'Before this can open as a {P.esc(kind.noun)}:</div>'
                  '<ul style="margin:0 0 0 1.1rem;">'
                  + "".join(f"<li>{P.esc(p)}</li>" for p in problems) + "</ul></div>")

    opts = []
    for i, s in enumerate(rec.get("sheets") or []):
        tag = "" if s.get("visibility") == "visible" else " (hidden)"
        dis = "" if s.get("staged") else " disabled"
        sel = " selected" if i == rec.get("sheet_index") else ""
        opts.append(f'<option value="{i}"{sel}{dis}>{P.esc(s.get("name"))}{tag} '
                    f'&middot; {int(s.get("rows") or 0)} rows</option>')
    hdr_row = grid["rows"][hdr[0]][0] if hdr else ""

    cols = grid["cols"]
    head_cells = "".join(f"<th>{SI.col_letter(c)}</th>" for c in cols)
    map_cells = "".join(f"<th>{_target_select(c, mapping.get(str(c), ''), schema)}</th>"
                        for c in cols)
    start = hdr[1] + 1 if hdr else 0
    shown = ([hdr[0]] if hdr else []) + list(range(start, min(len(grid["rows"]),
                                                              start + SI.PREVIEW_ROWS)))
    body_rows = []
    for ri in shown:
        rnum, vals = grid["rows"][ri]
        tds = "".join(f"<td>{P.esc(BI._cell_text(vals[ci] if ci < len(vals) else None))}</td>"
                      for ci in range(len(cols)))
        rcls = ' class="imp-hdr"' if hdr and ri == hdr[0] else ""
        body_rows.append(f'<tr{rcls}><td class="imp-rn">{int(rnum)}</td>{tds}</tr>')
    more = len(grid["rows"]) - (start + SI.PREVIEW_ROWS)
    more_note = (f'<p class="imp-note">&hellip; and {more} more rows on the sheet, all of '
                 f'which are read.</p>' if more > 0 else "")
    known = (f'<p class="imp-note">This layout has been confirmed before; its column '
             f'choices are applied. Confirming again saves any change.</p>'
             if rec.get("known") else "")

    if kind.register:
        what = _review_html(kind, built) + (_notes_html(built["notes"]) if built["notes"] else "")
        confirm = f"Confirm &amp; review the {P.esc(kind.plural)}"
    else:
        what = (_notes_html(built["notes"]) or
                '<p class="imp-note">Every row read cleanly.</p>')
        confirm = f"Confirm &amp; open the {P.esc(kind.noun)} form"

    act = _url("preview", kind, token=token)
    body = f"""
  {alert}
  <div class="page-top">
    <h1>Import <span>check the columns</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{_url("upload", kind, **_ctx_args(rec.get("ctx") or {}))}" class="btn btn-ghost">&#8592; Upload a different file</a>
    </div>
  </div>
  <form method="POST" action="{act}">
    <div class="imp-card">
      <h2>{P.esc(rec.get("filename"))}</h2>
      <div class="imp-file">
        <label for="sheet" style="font-weight:600;font-size:.85rem;">Sheet</label>
        <select id="sheet" name="sheet">{"".join(opts)}</select>
        <button class="btn btn-ghost" type="submit" name="action" value="update">Show this sheet</button>
      </div>
      <div class="imp-hrow">
        <label for="header_row" style="font-weight:600;font-size:.85rem;">The headings are on row</label>
        <input type="number" min="1" id="header_row" name="header_row" value="{P.esc(hdr_row)}"/>
        <button class="btn btn-ghost" type="submit" name="action" value="update">Use this row</button>
        <span class="imp-note">Blank finds it for you. Rows above it are left out.</span>
      </div>
      <p class="imp-note">A hidden sheet is listed and never chosen for you. Each
      import reads one sheet.</p>
      {known}
    </div>
    {kind.options_html(rec)}
    {BI.legend_html(kind.legend(rec.get("ctx") or {}), kind.noun, mapping)}

    <div class="imp-card">
      <h2>What each column holds</h2>
      <p class="imp-note">Choose a target under every column the {P.esc(kind.noun)}
      should take, and leave the rest as <i>ignore</i> &mdash; an ignored column does
      not go through. Targets marked * are the ones the legend lists.</p>
      <div class="imp-wrap">
        <table class="imp-grid">
          <thead><tr><th>Row</th>{head_cells}</tr><tr><th></th>{map_cells}</tr></thead>
          <tbody>{"".join(body_rows)}</tbody>
        </table>
      </div>
      {more_note}
      <div class="imp-actions">
        <button class="btn btn-ghost" type="submit" name="action" value="update">Update preview</button>
      </div>
    </div>
    {kind.extra_html(token, rec, built)}

    <div class="imp-card">
      <h2>What will come in</h2>
      {_stats_html(built)}
      {what}
      <div class="imp-actions">
        <button class="btn" type="submit" name="action" value="confirm">{confirm}</button>
      </div>
    </div>
  </form>"""
    return _page(f"Import {kind.title}", body)


def _banner(kind, rec, built) -> str:
    """The note on top of a prefilled form — escaped here, in the import's own
    styles, which the document's page does not load."""
    sheet = (rec.get("sheets") or [{}])[int(rec.get("sheet_index") or 0)]
    reds = [n for n in built["notes"] if n["level"] == "red"]
    notes = _notes_html(built["notes"])
    fold = (f'<details{" open" if reds else ""}><summary>{len(built["notes"])} note'
            f'{"s" if len(built["notes"]) != 1 else ""} from the import</summary>{notes}</details>'
            if notes else "")
    stats = ", ".join(f"{int(n)} {w}" for n, w in built.get("stats") or [])
    cls = "imp-banner has-red" if reds else "imp-banner"
    return (BI.IMPORT_STYLES +
            f'<div class="{cls}">&#128229; Imported from <b>{P.esc(rec.get("filename"))}</b>, '
            f'sheet “{P.esc(sheet.get("name"))}” &mdash; {int(built["rows"])} row'
            f'{"s" if built["rows"] != 1 else ""} read, {P.esc(stats)}. '
            f'<b>Nothing has been saved.</b> Check the form, then press '
            f'<b>{P.esc(kind.save_label)}</b> &mdash; or just leave the page. '
            f'<a href="{_url("preview", kind, token=rec["token"])}">Change the columns</a>'
            f'{fold}</div>')


def _review_page(kind, token: str, rec: dict, built: dict) -> str:
    """The three registers' apply page: every row, its verdict, and Create."""
    ok = sum(1 for it in built["items"] if not it["error"])
    bad = len(built["items"]) - ok
    button = (f'<button class="btn" type="submit">Create {ok} '
              f'{P.esc(kind.plural if ok != 1 else kind.noun)}</button>' if ok else
              '<p class="imp-note imp-bad">No row can be added as it stands.</p>')
    body = f"""
  <div class="page-top">
    <h1>Import <span>{P.esc(kind.title)}</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{_url("preview", kind, token=token)}" class="btn btn-ghost">&#8592; Change the columns</a>
    </div>
  </div>
  <div class="imp-card">
    <h2>{P.esc(rec.get("filename"))}</h2>
    <p class="imp-note"><b>{ok}</b> row{"s" if ok != 1 else ""} will be added and
    <b>{bad}</b> will not. Each row was checked by the rules the
    {P.esc(kind.noun)} form uses; a row that fails is listed with the reason and is
    not created. <b>Nothing has been added yet.</b></p>
    {_review_html(kind, built)}
    {_notes_html(built["notes"])}
    <form method="POST" action="{_url("apply", kind, token=token)}" class="imp-actions">
      {button}
    </form>
  </div>"""
    return _page(f"Import {kind.title}", body)


# =============================================================================
# ROUTES — minted per kind
# =============================================================================

def _do_upload(kind):
    purge()
    ctx, error, resp = kind.context(request.args)
    if resp is not None:
        return resp
    if error and not kind.needs_boq:
        return _upload_page(kind, ctx, error, blocked=True)
    if request.method == "GET" or error or (kind.needs_boq and not ctx.get("boq_id")):
        return _upload_page(kind, ctx, error)
    try:
        data, filename = BI._read_upload()
        wb = SI.read(data, filename)
        token = stage(kind, wb, filename, _uid(), ctx)
    except SI.Refused as refused:
        return _upload_page(kind, ctx, refused.message)
    return redirect(_url("preview", kind, token=token), code=303)


def _do_preview(kind, token: str):
    purge()
    rec = _own(token, kind)
    if rec is None:
        return _not_found(kind)
    if request.method == "GET":
        return _preview_page(kind, token, rec)

    form = request.form
    # A different sheet: a fresh start for it. Everything posted with it
    # belonged to the old sheet.
    try:
        wanted = int(form.get("sheet", rec.get("sheet_index") or 0))
    except (TypeError, ValueError):
        wanted = rec.get("sheet_index") or 0
    sheets = rec.get("sheets") or []
    if (wanted != rec.get("sheet_index") and 0 <= wanted < len(sheets)
            and sheets[wanted].get("staged") and rec["grid"][wanted] is not None):
        rec["sheet_index"] = wanted
        rec["header_row"], rec["matches"], rec["confirmed"] = None, {}, False
        _first_mapping(kind, rec)
        return redirect(_url("preview", kind, token=token), code=303)

    # A different heading row: the posted mapping belonged to the old one.
    grid, schema, hdr, _m = _effective(kind, rec)
    current = grid["rows"][hdr[0]][0] if hdr else None
    raw = str(form.get("header_row", "") or "").strip()
    want = int(raw) if raw.isdigit() else None
    if "header_row" in form and want != current:
        rec["header_row"], rec["matches"], rec["confirmed"] = want, {}, False
        _first_mapping(kind, rec)
        return redirect(_url("preview", kind, token=token), code=303)

    posted = {k[4:]: v for k, v in form.items() if k.startswith("map_")}
    before = SI.schema_clean(grid, rec.get("mapping") or {}, schema)
    if posted:
        rec["mapping"] = SI.schema_clean(grid, posted, schema)
    kind.read_options(form, rec)
    # The row choices posted with this form were drawn for the mapping it was
    # drawn with. A changed mapping — a Section column chosen, the item column
    # moved — proposes afresh, and a choice made against the old one would
    # silently override the new proposal, so they go with it.
    if SI.schema_clean(grid, rec.get("mapping") or {}, schema) != before:
        rec["matches"] = {}
    else:
        kind.read_extra(form, rec)
    rec["confirmed"] = False
    if (form.get("action") or "") != "confirm":
        return redirect(_url("preview", kind, token=token), code=303)
    built = _built(kind, rec)
    problems = _problems(kind, rec, built)
    if problems:
        return _preview_page(kind, token, rec, problems=problems)
    _upsert_layout(kind, rec)
    rec["confirmed"] = True
    return redirect(_url("apply", kind, token=token), code=303)


def _do_apply(kind, token: str):
    purge()
    rec = _own(token, kind)
    if rec is None:
        return _not_found(kind)
    if not rec.get("confirmed"):
        return redirect(_url("preview", kind, token=token), code=303)
    # The context is re-checked: a schedule superseded, or a C1 step undone,
    # since the upload refuses here as the document's own route would.
    ctx, error, resp = kind.context(_ctx_args(rec.get("ctx") or {}))
    if resp is not None:
        return resp
    if error:
        rec["confirmed"] = False
        return _preview_page(kind, token, rec, error=error)
    built = _built(kind, rec)
    problems = _problems(kind, rec, built)
    if problems:
        rec["confirmed"] = False
        return _preview_page(kind, token, rec, problems=problems)
    if kind.register:
        if request.method == "POST":
            return kind.save(token, rec, built)
        return _review_page(kind, token, rec, built)
    return kind.apply(token, rec, built)


def _register_routes():
    """
    Mint `upload_<kind>`, `preview_<kind>` and `apply_<kind>` for every kind —
    `approval._register_routes()`'s arrangement, because each kind carries its
    own document's permission and the registry maps one endpoint to one. The
    three bodies are written once.
    """
    for key, kind in KINDS.items():
        def _upload(_k=kind):
            return _do_upload(_k)

        def _preview(token, _k=kind):
            return _do_preview(_k, token)

        def _apply(token, _k=kind):
            return _do_apply(_k, token)

        _upload.__name__ = f"upload_{key}"
        _preview.__name__ = f"preview_{key}"
        _apply.__name__ = f"apply_{key}"
        docimport_bp.add_url_rule(f"/{key}", endpoint=f"upload_{key}",
                                  view_func=_upload, methods=["GET", "POST"])
        docimport_bp.add_url_rule(f"/{key}/<token>", endpoint=f"preview_{key}",
                                  view_func=_preview, methods=["GET", "POST"])
        docimport_bp.add_url_rule(f"/{key}/<token>/apply", endpoint=f"apply_{key}",
                                  view_func=_apply,
                                  methods=["GET", "POST"] if kind.register else ["GET"])


_register_routes()
