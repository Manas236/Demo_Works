"""
buypick.py — the item picker for a purchase order entered from scratch
=======================================================================

`/purchase/create`'s item rows, beside the catalogue (31 October 2026,
CLIENT_CHANGES.md §0 sixtieth block). Two sources, each its own <optgroup> in
the same dropdown:

* **Specification library** — every clause × every size. Drawn only while the
  product catalogue is HIDDEN; with the catalogue on, the catalogue rows are
  drawn instead, exactly as before. `purchase.py` reads the switch and tells
  this module which; this module never reads it (specpick.py's rule — the
  decision lives in one place).
* **BOQ items** — every material line on every CURRENT BOQ (the tip of each
  revision chain), drawn whichever way the switch is set. The client asked for
  it on the 31 October call: *whatever we add to a BOQ should be in Select
  item.*

Why this exists
---------------
On 12 September 2026 the catalogue was hidden and `/purchase/create`'s rows
were emptied with it (ABOUT.md §7 gap 38): the quotation got the spec library
in its place, the purchase order got nothing, and the only way to write an
order was the extra free-text parts. The client hit the empty dropdown on
31 October 2026. Gap 38 was re-opened and closed again by this module.

What a pick is
--------------
A value in the line row's existing `line_product_id` box:

    "spec:<spec id>:<variant index>"
    "boq:<boq id>:<line id>"

A catalogue product's id is a UUID and never starts with either prefix, so the
three kinds share one field, one row, one rate box and one POST path, and the
reprice form (which re-prices stored rows by position and never reads a
product id) needs nothing.

⚠ **Identity is re-read from the source at POST** — name, HSN, unit — and the
  browser's copy is never trusted; only qty, rate, discount and make are the
  browser's. A spec or a BOQ line that has gone, or a BOQ that has since been
  REVISED, refuses the POST naming the line (specpick.process_selections()'s
  rule: a document missing a line nobody removed is worse than a form asking
  to be re-checked).

⚠ **The line is a SNAPSHOT.** Everything printed is stored on the PO line at
  create; editing, revising or deleting the spec or the BOQ afterwards moves
  nothing on an existing order. The source is kept as a reference only, under
  `src_*` keys — **deliberately NOT `line_id`**. `line_id` on a PO line means
  *ordered against that schedule line* (the from-BOQ path, `pnl.coverage_of()`
  keys on it), and a manual order that borrowed a line's text is not that: it
  must never count as PO coverage of a schedule it was not raised against.

Rates — a suggestion, and only where it is a COST
-------------------------------------------------
The rate box is prefilled, never imposed, and an empty box only
(`purchase.fillRate()`'s rule).

* spec → the variant's `default_supply_base_rate`;
* BOQ  → the line's `supply_base_rate`, from the NEWEST current BOQ that has
  one; blank when none does.

Both are the COST basis, which is the only rate that belongs on a purchase
order. Traced on 31 October 2026, every writer of the spec field: the seed
(`spec.ensure_demo_specs()` ← `demo_data.py` ← `tools/gen_demo_data.py`,
column G of the client's own BOQ, *Supply Base Rate*) and the spec form
(`spec._parse_variants()`, the box labelled *Supply Base Rate*). The BOQ form
copies it into the line's `supply_base_rate`, and `boq.lines_without_cost()`
states *the base rate is the cost basis*. Nothing writes a selling rate into
it — the Excel BOQ importer writes BOQs, not the library. ⚠ A BOQ imported
with selling rates only has a blank base rate, and the box then opens BLANK —
never the selling rate, never 0.

What is offered from a BOQ
--------------------------
* **Headers are never offered.** A specification clause is text, not a thing
  you buy.
* **A child line carries its clause.** "150mm dia ISI" alone does not say MS or
  GI, so a child of a specification header is named
  `<first line of the clause, ≤ CLAUSE_CHARS> — <its own description>`, from
  `boq.header_of()`, THE parent rule (boqpick.families() reads the same). The
  clause is cut on a word boundary; the full text stays on the BOQ.
* **Installation-only lines are not offered** — a line with a positive
  installation rate and no supply rate is labour, and a material order has no
  business carrying it (`purchase.INCLUDE_INSTALL_TRACK`'s reason). A line with
  neither rate (a BOQ saved as it is, blanks and all) IS offered: it is still a
  thing on the schedule.
* **Deduplicated on EXACT text** — the full name and the unit, compared with
  case and runs of whitespace folded, nothing else. ⚠ **No punctuation is
  stripped and nothing is fuzzy**: "1.5 mm" and "15 mm" must stay two items,
  and so must Dia and NB (150 NB pipe is 168.3 mm OD — merging them would put
  the wrong pipe on an order), MS and GI, and two wall thicknesses.
  The newest current BOQ carrying an item is the one its pick points at.

Import direction — a LEAF
-------------------------
Module level: `store` and `pipeline`. `spec` (the seeder) and `boq` (the
superseded set, the parent rule, the net rate, the make in a remark) are
imported in function bodies — `purchase.py` may not import `spec.py` at all
(`tests/test_import_directions.py`), and this module is how the buy side reads
the library without that edge. This module never imports `purchase`,
`quotation`, `product`, `auth`, `flask` or anything that prints.
"""

import re

import pipeline as P
from store import STORE


SPEC_PREFIX = "spec:"
BOQ_PREFIX = "boq:"

SPEC_GROUP = "Specification library"
BOQ_GROUP = "BOQ items"

# How much of a specification clause a child line's name carries.
CLAUSE_CHARS = 160
# How much an <option> SHOWS (31 Oct 2026, after the first screen): the size
# first, then a short cut of the clause, never more than OPTION_CHARS before
# the unit. A native dropdown sizes its popup to the longest option, and at
# 150 characters Chrome pushed it off the left edge of the window, cutting off
# exactly the part that says what the item is. The FULL name is the option's
# tooltip and what the search box matches; the stored name is never cut.
OPTION_CHARS = 70
OPTION_CLAUSE_CHARS = 40

# The library's own category order — specpick.CATEGORY_ORDER, restated rather
# than imported so this leaf does not depend on the quotation's picker.
CATEGORY_ORDER = ["Piping", "Valves", "Sprinklers", "Hydrant", "Pumps",
                  "Panels", "Civil", "Other"]


def _BQ():
    """`boq`, imported in the function body (see the module docstring)."""
    import boq
    return boq


def ensure_seeded() -> None:
    """Seed the spec library if it is empty — specpick.ensure_seeded()'s way."""
    from spec import ensure_demo_specs
    ensure_demo_specs()


def is_pick(value) -> bool:
    """Is this `line_product_id` a library or BOQ pick rather than a product?"""
    v = str(value or "")
    return v.startswith(SPEC_PREFIX) or v.startswith(BOQ_PREFIX)


def _fold(text) -> str:
    """The dedupe key's fold: case and runs of whitespace. Nothing else."""
    return " ".join(str(text or "").split()).lower()


def _cut(text, limit: int) -> str:
    """`text` cut to `limit` characters on a word boundary, with an ellipsis."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    head = t[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (head or t[:limit]) + "…"


# The scope-of-work words a BOQ clause opens with — "Supply, Fabrication,
# Installtion, Testing & comissioning of …" — spelling slips included, because
# the client's own sheets carry them. Stripped from the dropdown's LABEL only
# (they are the same on every line and push the item off the end); the stored
# name, the tooltip and the search text keep every word.
_LEAD_IN = re.compile(
    r"^(?:(?:supply(?:ing)?|providing|fabrication|fabricating|err?ection|"
    r"install(?:ation|tion|ing)?|testing|test|"
    r"co?m+is+ion(?:ing)?|commissioning|fixing|laying|and|of|the)"
    r"[\s,&/.]*)+", re.I)


def _strip_lead_in(text: str) -> str:
    """`text` without the scope-of-work lead-in, unless that would leave nothing."""
    m = _LEAD_IN.match(text or "")
    if not m or len(m.group(0).split()) < 2:
        return text
    rest = text[m.end():].strip()
    return (rest[:1].upper() + rest[1:]) if rest else text


def _option_label(own: str, context: str = "", unit: str = "") -> str:
    """
    What the dropdown shows: `<own text> · <context, cut short> (<unit>)` —
    the distinguishing part (a size, a variant) FIRST, so a list of sizes of
    one clause reads down its left edge.
    """
    own = _strip_lead_in(" ".join(str(own or "").split()))
    context = _strip_lead_in(" ".join(str(context or "").split()))
    if own and context:
        text = f"{own} · {_cut(context, OPTION_CLAUSE_CHARS)}"
    else:
        text = own or context
    text = _cut(text, OPTION_CHARS)
    return text + (f" ({unit})" if unit else "")


def _num_or_none(v):
    """A stored rate as a float, or None for a blank. A 0 stays 0."""
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# =============================================================================
# THE SPECIFICATION LIBRARY
# =============================================================================

def _spec_name(spec: dict, variant: dict) -> str:
    title = " ".join(str(spec.get("title") or "").split())
    label = " ".join(str(variant.get("label") or "").split())
    return f"{title} — {label}" if label else title


def spec_entries() -> list:
    """
    `[{value, label, name, rate, make, group}]` — one per spec variant, in the
    library's category order then by code.
    """
    by_cat: dict = {}
    for sid, s in (STORE.get("specs") or {}).items():
        by_cat.setdefault(s.get("category") or "Other", []).append((sid, s))
    cats = ([c for c in CATEGORY_ORDER if c in by_cat]
            + sorted(c for c in by_cat if c not in CATEGORY_ORDER))
    out = []
    for cat in cats:
        for sid, s in sorted(by_cat[cat],
                             key=lambda kv: (kv[1].get("code") or "").lower()):
            for vidx, v in enumerate(s.get("variants") or []):
                name = _spec_name(s, v)
                unit = str(v.get("unit") or "")
                code = str(s.get("code") or "")
                title = str(s.get("title") or "")
                vlabel = str(v.get("label") or "")
                label = (_option_label(vlabel, title, unit) if vlabel.strip()
                         else _option_label(title, "", unit))
                out.append({
                    "value": f"{SPEC_PREFIX}{sid}:{vidx}",
                    "label": label,
                    "name":  name,
                    "find":  " ".join(x for x in (name, code, unit) if x),
                    "rate":  _num_or_none(v.get("default_supply_base_rate")),
                    "make":  "",
                })
    return out


# =============================================================================
# BOQ ITEMS
# =============================================================================

def current_boqs() -> list:
    """
    Every BOQ at the TIP of its revision chain, newest first (date, then ref).
    A superseded revision is never offered: its lines would appear twice.
    """
    BQ = _BQ()
    gone = BQ.superseded_ids()
    tips = [b for bid, b in (STORE.get("boqs") or {}).items()
            if isinstance(b, dict) and str(bid) not in gone]
    return sorted(tips, key=lambda b: (str(b.get("date") or ""),
                                       str(b.get("ref") or "")), reverse=True)


def _make_of(BQ, li: dict) -> str:
    """
    The make the BOQ importer wrote into a line's remark, or `""` —
    `boq.make_from_remark()`, THE parse (29 Oct 2026, §7 gap 81). Looked up
    rather than called by name so this leaf also runs on a checkout that
    predates it (the 31 October hotfix branch does), where it is `""`.
    """
    parse = getattr(BQ, "make_from_remark", None)
    return parse(li.get("remark")) if parse else ""


def _is_install_only(BQ, li: dict) -> bool:
    sup = BQ.net_rate(li, "supply")
    ins = BQ.net_rate(li, "install")
    return (sup is None or sup <= 0) and (ins is not None and ins > 0)


def _line_parts(lines: list, idx: int, header_of: dict = None) -> tuple:
    """`(clause, own)` — the parent clause's first line (cut) and the line's own text."""
    BQ = _BQ()
    li = lines[idx]
    own = " ".join(str(li.get("description") or "").split())
    parents = header_of if header_of is not None else BQ.header_of(lines)
    h = parents.get(idx)
    if h is None:
        return "", own
    clause = str(lines[h].get("description") or "").strip().split("\n", 1)[0]
    return _cut(clause, CLAUSE_CHARS), own


def boq_line_name(lines: list, idx: int, header_of: dict = None) -> str:
    """
    The name a BOQ line carries on a purchase order: its own description, and
    — for a child of a specification header — the clause's first line first.
    """
    clause, own = _line_parts(lines, idx, header_of)
    if not clause:
        return own
    return f"{clause} — {own}" if own else clause


def boq_entries() -> list:
    """
    `[{value, label, name, rate, make, unit, boq_ref}]` — one per distinct
    material item across the current BOQs (see the module docstring for what
    is offered, what is not, and the exact-text dedupe).
    """
    BQ = _BQ()
    seen: dict = {}
    order = []
    for boq in current_boqs():
        bid = str(boq.get("id") or "")
        lines = boq.get("line_items") or []
        parents = BQ.header_of(lines)
        for i, li in enumerate(lines):
            if not isinstance(li, dict) or li.get("is_header"):
                continue
            lid = BQ._line_id(li.get("line_id"))
            if not lid or _is_install_only(BQ, li):
                continue
            name = boq_line_name(lines, i, parents)
            if not name:
                continue
            unit = " ".join(str(li.get("unit") or "").split())
            key = (_fold(name), _fold(unit))
            rate = _num_or_none(li.get("supply_base_rate"))
            make = _make_of(BQ, li)
            if key in seen:
                e = seen[key]
                # The newest BOQ owns the pick; an older one only fills what
                # the newer left blank.
                if e["rate"] is None and rate is not None:
                    e["rate"] = rate
                if not e["make"] and make:
                    e["make"] = make
                continue
            clause, own = _line_parts(lines, i, parents)
            label = (_option_label(own, clause, unit) if clause and own
                     else _option_label(name, "", unit))
            e = {
                "value":   f"{BOQ_PREFIX}{bid}:{lid}",
                "label":   label,
                "name":    name,
                "find":    " ".join(x for x in (name, unit) if x),
                "rate":    rate,
                "make":    make,
                "unit":    unit,
                "boq_ref": str(boq.get("ref") or ""),
            }
            seen[key] = e
            order.append(e)
    return sorted(order, key=lambda e: _fold(e["name"]))


# =============================================================================
# RENDER
# =============================================================================

def _group_html(label: str, entries: list, selected: str) -> str:
    if not entries:
        return ""
    out = f'<optgroup label="{P.esc(label)}">'
    for e in entries:
        sel = " selected" if e["value"] == selected else ""
        # `title` is the full name, shown on hover; `data-s` is what the
        # search box matches, so a word cut off the label is still found.
        full = e.get("name") or e["label"]
        find = (e.get("find") or full).lower()
        out += (f'<option value="{P.esc(e["value"])}"{sel} title="{P.esc(full)}" '
                f'data-s="{P.esc(find)}">{P.esc(e["label"])}</option>')
    return out + "</optgroup>"


def groups_html(selected: str = "", *, with_spec: bool,
                spec: list = None, boq: list = None) -> str:
    """
    The two <optgroup>s, in order: the library (only when `with_spec`), then
    the BOQ items. Pass already-built entry lists to render many rows from
    one build.
    """
    out = ""
    if with_spec:
        out += _group_html(SPEC_GROUP, spec if spec is not None else spec_entries(),
                           selected)
    out += _group_html(BOQ_GROUP, boq if boq is not None else boq_entries(), selected)
    return out


def prefill_maps(*, with_spec: bool, spec: list = None, boq: list = None) -> tuple:
    """
    `({value: rate}, {value: make})` for the picks that have one. A blank rate
    or make is ABSENT, so the page fills nothing for it.
    """
    entries = list(boq if boq is not None else boq_entries())
    if with_spec:
        entries = list(spec if spec is not None else spec_entries()) + entries
    rates = {e["value"]: round(e["rate"], 2) for e in entries if e["rate"] is not None}
    makes = {e["value"]: e["make"] for e in entries if e["make"]}
    return rates, makes


# The search box above each item dropdown. Plain text with SINGLE braces: it
# is substituted into the page as a value, never re-parsed as an f-string.
FIND_PLACEHOLDER = "Search items, e.g. GI 50"

FIND_JS = """<script>
/* Filter one row's item dropdown as you type. Every word must appear
   (case-insensitive, anywhere in the option's text), so "gi 50" finds a
   50 mm GI pipe. A matched option is never auto-selected. */
function findItem(inp) {
  var row = inp.closest('.line-row');
  var sel = row ? row.querySelector('select[name="line_product_id"]') : null;
  if (!sel) return;
  var words = inp.value.toLowerCase().split(/\\s+/).filter(function (w) { return w; });
  var opts = sel.querySelectorAll('option');
  for (var i = 0; i < opts.length; i++) {
    var o = opts[i];
    if (!o.value) { o.hidden = false; continue; }
    var t = (o.getAttribute('data-s') || o.textContent).toLowerCase();
    var ok = words.every(function (w) { return t.indexOf(w) !== -1; });
    o.hidden = !ok;
  }
  var groups = sel.querySelectorAll('optgroup');
  for (var g = 0; g < groups.length; g++) {
    groups[g].hidden = !groups[g].querySelector('option:not([hidden])');
  }
}
</script>"""


# =============================================================================
# THE POST — a pick becomes a line's identity, or the form is refused
# =============================================================================

def resolve(value) -> tuple:
    """
    `(identity, error)` for one pick. `identity` is the PO line's own fields —
    `name`, `part_no`, `hsn`, `unit` — plus the `src_*` reference keys, all
    re-read from the source now. `error` is a plain sentence.

    Never reads the catalogue switch: whether a pick is VALID does not depend
    on what the page happened to draw that day (gap 38's rule, kept).
    """
    v = str(value or "")
    if v.startswith(SPEC_PREFIX):
        rest = v[len(SPEC_PREFIX):]
        sid, _, raw_vidx = rest.rpartition(":")
        spec = (STORE.get("specs") or {}).get(sid)
        if not spec:
            return None, ("One of the picked library items is no longer in the "
                          "specification library. Remove it and pick again.")
        try:
            vidx = int(raw_vidx)
            if vidx < 0:
                raise IndexError
            variant = (spec.get("variants") or [])[vidx]
        except (TypeError, ValueError, IndexError):
            return None, (f"The size picked for '{spec.get('title', '')}' is no "
                          f"longer in the library. Remove it and pick again.")
        return {
            "name":        _spec_name(spec, variant),
            "part_no":     str(spec.get("code") or ""),
            "hsn":         str(spec.get("supply_hsn") or ""),
            "unit":        str(variant.get("unit") or ""),
            "source":      "spec",
            "src_spec_id": sid,
            "src_vidx":    vidx,
        }, ""

    if v.startswith(BOQ_PREFIX):
        BQ = _BQ()
        rest = v[len(BOQ_PREFIX):]
        bid, _, lid = rest.rpartition(":")
        boq = (STORE.get("boqs") or {}).get(bid)
        if not boq:
            return None, ("One of the picked BOQ items belongs to a BOQ that no "
                          "longer exists. Remove it and pick again.")
        if bid in BQ.superseded_ids():
            return None, (f"BOQ {boq.get('ref') or ''} has been revised since this "
                          f"page was opened. Pick the item again from the "
                          f"current revision.")
        lines = boq.get("line_items") or []
        idx = next((i for i, li in enumerate(lines)
                    if isinstance(li, dict) and BQ._line_id(li.get("line_id")) == lid),
                   None)
        if idx is None or lines[idx].get("is_header") or _is_install_only(BQ, lines[idx]):
            return None, (f"One of the picked items is no longer a material line "
                          f"on BOQ {boq.get('ref') or ''}. Remove it and pick again.")
        li = lines[idx]
        return {
            "name":        boq_line_name(lines, idx),
            # ⚠ The BOQ's item number is NOT carried as a part number: it is a
            #   label inside THAT schedule, and this order is not raised
            #   against it. "4.1" on an unrelated vendor's order is noise.
            "part_no":     "",
            "hsn":         str(li.get("supply_hsn") or ""),
            "unit":        str(li.get("unit") or ""),
            "source":      "boq",
            "src_boq_id":  bid,
            "src_boq_ref": str(boq.get("ref") or ""),
            "src_line_id": lid,
        }, ""

    return None, "That is not a library or BOQ item."
