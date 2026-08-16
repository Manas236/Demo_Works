"""
boqpick.py — the BOQ line picker, shared by every document raised from a schedule
================================================================================

**This is the grid, not the document.** A checkbox per BOQ line, an editable
quantity defaulting to the schedule's, select-all / clear-all, and the family
fold that carries a specification clause down with the sizes underneath it.

It was written once in `ra.py` as the claim grid, ported into `po_draft.py` as
the order picker, and the delivery challan wants it a third time. Three copies
is where `docsheet.py`'s four letterheads were when they had already drifted
apart, so it comes out here at the **second** consumer rather than the fourth.

What lives here
---------------
The **build** (`families`, `line_ids`), the **render** (`PICKER_CSS`,
`rows_html`, `grid_html`, `js`) and the **POST parsing** (`picked_lines`).

What deliberately does NOT live here
------------------------------------
Any route, any record shape, any stylesheet element of its own, and any
document-specific wording. Every string a reader sees — the section title, the
intro paragraph, the quantity column's label, the refusal message — is passed
in by the caller, because those are the parts that legitimately differ between
a purchase order and a delivery challan. The flags below (`with_pcs`,
`with_rate`) exist to preserve **observed** differences between the consumers,
not to offer a menu; that is `docsheet.letterhead()`'s `show_web` precedent.

`with_rate` is the third consumer's, added when `purchase.py` grew
`/purchase/from-boq/<id>`. A **real** purchase order is priced, so its grid
needs a rate box per line prefilled from the BOQ's `supply_base_rate` — the
draft PO's grid must never carry one (its whole point is that the supplier
fills the rates in) and the delivery challan carries no money at all. Off, this
module emits the bytes it always emitted; `tests/test_print_golden.py` pins
`/po/create` and is what proves that rather than asserts it.

⚠ **`.pk-rate`'s CSS is deliberately NOT in `PICKER_CSS`.** That constant is
spliced into `po_draft.PO_STYLES` at a fixed character position and `/po/create`
is hashed byte-for-byte, so a rule added here would move a golden for a column
that page does not render. It lives in `purchase.FROM_BOQ_STYLES`, beside the
only page that draws the column.

⚠ **`ra.py`'s claim grid is deliberately NOT folded in here.** It carries the
cumulative over-claim guard and two money columns, the guard is load-bearing,
and it re-styles on every keystroke. It is a different animal with a wider
blast radius, and it was left alone in this pass — see ABOUT.md §5 (`/ra`,
*The claim grid*) for what folding it in would have to answer first.

Import direction — this module is a LEAF
----------------------------------------
```
boqpick.py ──► boq.py       _line_id / _item_no / _num / _fmt_qty /
                            _json_for_script / MAX_LINES
boqpick.py ──► pipeline.py  esc
```

It imports **nothing** that renders a document and owns no route, so
`po_draft.py` and `challan.py` can both depend on it without depending on each
other. `boq.py` must never import it back.

Byte-for-byte
-------------
Every builder below reproduces the exact bytes `po_draft.py` used to emit,
including indentation, because `tests/test_print_golden.py` hashes
`/po/create` and was committed **before** this module existed. If you change a
builder, that file goes red and names the block.
"""

import json

import boq as BQ
import pipeline as P


# =============================================================================
# CSS
# =============================================================================
#
# Raw CSS rather than a finished `<style>` element, exactly as
# `docsheet.BANK_CSS` is and for the same reason: there is one copy of these
# rules and two sheets need to carry it. `po_draft.PO_STYLES` splices it back
# in at the character position it has always occupied, so that page stays
# byte-for-byte what it was, and `challan.CHALLAN_STYLES` wraps it for a sheet
# that does not load `PO_STYLES` — the delivery challan, which may not import
# `po_draft.py`.
#
# It begins flush against the opening quotes (the trailing `\` suppresses the
# newline) so that splicing it in leaves the surrounding blank lines exactly as
# they were.
PICKER_CSS = """\
  /* The line picker. Ported from ra.py's claim grid rather than invented:
     the same `.is-spec` / `.is-child` classes, the same chevron and tag
     furniture, the same collapsed-on-arrival default, the same
     expand-all/collapse-all bar. An operator who has raised an RA bill already
     knows how this form works. */
  .pk-wrap { overflow-x:auto; border:1px solid var(--border);
             border-radius:10px; background:#fff; }
  .pk-table { width:100%; border-collapse:collapse; table-layout:fixed;
              font-size:.84rem; }
  .pk-table th, .pk-table td { padding:.42rem .55rem; border-bottom:1px solid var(--border);
                               vertical-align:middle; }
  .pk-table thead th { position:sticky; top:0; z-index:1; background:var(--surface);
                       font-size:.7rem; text-transform:uppercase; letter-spacing:.06em;
                       color:var(--muted); text-align:left; }
  .pk-tick { width:42px; text-align:center; }
  .pk-no   { width:74px; font-weight:600; }
  .pk-unit { width:70px; }
  .pk-avail{ width:96px; text-align:right; font-variant-numeric:tabular-nums;
             color:var(--muted); }
  .pk-in   { width:110px; }
  .pk-in input, .pk-pcs input {
    width:100%; padding:.28rem .4rem; border:1px solid var(--border);
    border-radius:6px; font:inherit; text-align:right;
  }
  .pk-pcs  { width:88px; }
  .pk-desc { min-width:220px; }
  .pk-clamp { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
              overflow:hidden; }

  .pk-head { background:var(--surface); cursor:pointer; user-select:none; }
  .pk-head td { font-weight:600; }
  .pk-chev { display:inline-block; width:1em; color:var(--muted); }
  .pk-tag  { display:inline-block; font-size:.68rem; font-weight:700;
             text-transform:uppercase; letter-spacing:.05em; color:var(--navy);
             background:#eef2ff; border-radius:99px; padding:1px 7px;
             margin-right:.5rem; }
  .pk-hdesc { color:var(--muted); font-weight:400; }
  .pk-off td { opacity:.45; }

  .pk-tools { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap;
              padding:.6rem .2rem; font-size:.82rem; color:var(--muted); }
  .pk-tools .spacer { flex:1; }
  .pk-count { font-weight:700; color:var(--navy); }

  .pk-none { display:none; margin-top:.8rem; }
"""


# =============================================================================
# BUILD — the family map and the id list, both keyed on `line_id`
# =============================================================================

def families(boq: dict) -> dict:
    """`{header line_id: [child line_id, …]}` — boq.py's fold, keyed on ids."""
    by_item = {}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            key = (str(li.get("section") or ""), BQ._item_no(li.get("item_no")))
            by_item[key] = BQ._line_id(li.get("line_id"))
    fams = {hlid: [] for hlid in by_item.values() if hlid}
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        parent = BQ._item_no(li.get("parent_item_no"))
        if not parent:
            continue
        hlid = by_item.get((str(li.get("section") or ""), parent))
        lid = BQ._line_id(li.get("line_id"))
        if hlid and lid:
            fams[hlid].append(lid)
    return fams


def line_ids(boq: dict) -> list:
    """Every pickable (non-header) line id, in schedule order."""
    return [BQ._line_id(li.get("line_id")) for li in boq.get("line_items") or []
            if not li.get("is_header") and BQ._line_id(li.get("line_id"))]


# =============================================================================
# RENDER
# =============================================================================

def rows_html(boq: dict, chosen: set = None, qty_of: dict = None,
              with_pcs: bool = False, qty_aria: str = "Quantity",
              with_rate: bool = False, rate_of: dict = None,
              rate_aria: str = "Rate") -> str:
    """
    One row per BOQ line, every box ticked unless a rejected POST says otherwise.

    **Ticked by default**, because most documents raised from a schedule cover
    the whole schedule and a form that opens with 97 empty boxes makes the
    common case the expensive one. The operator unticks down to what they want.

    A folded row is **hidden, never removed** — exactly `ra._claim_rows()`'s
    rule and for exactly its reason: what saves must not depend on what the
    operator happened to have expanded open.

    `with_pcs` adds the draft PO's second count column (pieces of pipe against
    metres of it, DOMAIN.md §5.2). Nothing on a BOQ line holds one, so it is
    typed on the form and blank is normal. It is a flag rather than a shape
    because exactly one of the two consumers has that column.

    `qty_aria` is the quantity input's accessible name, passed in rather than
    derived from the column label: the draft PO's column reads `Order qty` and
    its input announces `Order quantity`, and preserving that is the whole
    point of extracting this without moving a byte.

    `with_rate` adds the real purchase order's rate box, **prefilled from the
    BOQ line's `supply_base_rate`** — what the job was costed at, and therefore
    the right opening figure for what we expect to pay. It is a suggestion and
    never an imposition: the box is editable and `purchase.py` stores what comes
    back, which is `purchase.fillRate()`'s own rule about a catalogue price and
    `/boq/create`'s about an escalated rate.

    ⚠ **A `None` base rate prefills BLANK, not `0.00`.** On a BOQ line `None`
      means the rate was negotiated directly rather than escalated (ABOUT.md §3
      property 6); collapsing it to zero here would open the form stating that
      the material is free.

    ⚠ **The INSTALLATION track is never read.** `install_base_rate` is labour,
      not purchased goods, and a material PO has no business carrying it — see
      `purchase.INCLUDE_INSTALL_TRACK`.
    """
    fams = families(boq)
    child_of = {kid: h for h, kids in fams.items() for kid in kids}
    # The header row's colspan covers every column after Item. Computed rather
    # than written down, so a flag cannot silently leave a row one cell short —
    # `boq.py`'s rule about spans derived from `n_supply_cols` (ABOUT.md §5).
    span = str(4 + (1 if with_pcs else 0) + (1 if with_rate else 0))
    out = []

    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if not lid:
            continue
        item = P.esc(BQ._item_no(li.get("item_no")))
        raw_desc = str(li.get("description") or "")

        if li.get("is_header"):
            kids = fams.get(lid) or []
            tag = (f'<span class="pk-tag">spec &middot; {len(kids)} '
                   f'item{"" if len(kids) == 1 else "s"}</span>') if kids else \
                  '<span class="pk-tag">spec</span>'
            click = (f' id="head_{lid}" data-open="0" '
                     f'onclick="toggleFamily(\'{lid}\')"') if kids else ""
            chev = (f'<span class="pk-chev" id="chev_{lid}">&#9656;</span>'
                    if kids else '<span class="pk-chev"></span>')
            out.append(
                f'<tr class="pk-head is-spec"{click}>'
                f'<td class="pk-tick"></td>'
                f'<td class="pk-no">{chev}{item}</td>'
                f'<td colspan="{span}">{tag}'
                f'<span class="pk-hdesc" title="{P.esc(raw_desc)}">'
                f'{P.esc(raw_desc[:110])}</span></td></tr>')
            continue

        parent = child_of.get(lid)
        hide = ' style="display:none;"' if parent else ""
        cls = " is-child" if parent else ""
        avail = float(li.get("total_qty") or 0.0)
        ticked = " checked" if (chosen is None or lid in chosen) else ""
        qty_val = (qty_of or {}).get(lid)
        qty_val = BQ._fmt_qty(avail) if qty_val is None else P.esc(qty_val)
        pcs_cell = (f"""
          <td class="pk-pcs"><input type="text" inputmode="numeric" id="p_{lid}"
              value="" aria-label="Pieces"/></td>""") if with_pcs else ""

        rate_cell = ""
        if with_rate:
            rate_val = (rate_of or {}).get(lid)
            if rate_val is None:
                base = li.get("supply_base_rate")
                # `None` is "negotiated directly", not zero — it opens blank.
                rate_val = "" if base is None else f"{float(base):.2f}"
            rate_cell = (f"""
          <td class="pk-rate"><input type="text" inputmode="decimal" id="r_{lid}"
              value="{P.esc(rate_val)}" aria-label="{P.esc(rate_aria)}"/></td>""")

        out.append(f"""
        <tr class="pk-row{cls}" id="row_{lid}"{hide}>
          <td class="pk-tick"><input type="checkbox" id="c_{lid}"{ticked}
              onchange="tick('{lid}')" aria-label="Include this line"/></td>
          <td class="pk-no">{item}</td>
          <td class="pk-desc"><span class="pk-clamp" title="{P.esc(raw_desc)}">
              {P.esc(" ".join(raw_desc.split()))}</span></td>
          <td class="pk-unit">{P.esc(li.get("unit") or "")}</td>
          <td class="pk-avail">{BQ._fmt_qty(avail)}</td>
          <td class="pk-in"><input type="text" inputmode="decimal" id="q_{lid}"
              value="{qty_val}" aria-label="{P.esc(qty_aria)}"/></td>{pcs_cell}{rate_cell}
        </tr>""")
    return "".join(out)


# The JavaScript, as a template with three substitution points.
#
# Substitution rather than an f-string because the body is full of literal
# braces — this is browser JavaScript, not CSS inside an f-string — and because
# the three points are the only things that genuinely differ between the two
# consumers: the hidden field the payload lands in, the noun the refusal
# comment uses, and whether a Pcs value is collected.
_JS_TEMPLATE = r"""
<script>
function el(id) { return document.getElementById(id); }

/* ── The fold ────────────────────────────────────────────────────────────
   Ported from ra.py, which ported it from boq.py. Open/closed state lives on
   the HEADER ROW keyed by its line_id, never in a map keyed by row index:
   two rows in one section can share an item number, so an index key desyncs
   the moment anything moves.

   A folded row is HIDDEN, not removed. Every input stays in the document, and
   saveJSON() below reads values and never visibility. */
function isFamilyOpen(h) {
  var head = el('head_' + h);
  return !!(head && head.getAttribute('data-open') === '1');
}
function setFamily(h, open) {
  var head = el('head_' + h);
  if (!head) return;
  head.setAttribute('data-open', open ? '1' : '0');
  var chev = el('chev_' + h);
  if (chev) chev.textContent = open ? '▾' : '▸';
  var kids = FAMILIES[h] || [];
  for (var i = 0; i < kids.length; i++) {
    var row = el('row_' + kids[i]);
    if (row) row.style.display = open ? '' : 'none';
  }
}
function toggleFamily(h) { setFamily(h, !isFamilyOpen(h)); }
function setAllFamilies(open) {
  for (var h in FAMILIES) {
    if (Object.prototype.hasOwnProperty.call(FAMILIES, h)) setFamily(h, open);
  }
}
function expandAll()   { setAllFamilies(true); }
function collapseAll() { setAllFamilies(false); }

/* ── The ticks ───────────────────────────────────────────────────────────
   Select-all and clear-all act on EVERY line, folded or not, for the same
   reason folding does not change the payload: what the operator can see must
   not decide what they ordered. */
function tick(lid) {
  var row = el('row_' + lid), c = el('c_' + lid);
  if (row && c) row.className = row.className.replace(/ pk-off/g, '')
                              + (c.checked ? '' : ' pk-off');
  count();
}
function setAll(on) {
  for (var i = 0; i < LINE_IDS.length; i++) {
    var c = el('c_' + LINE_IDS[i]);
    if (c) { c.checked = on; tick(LINE_IDS[i]); }
  }
}
function selectAll() { setAll(true); }
function clearAll()  { setAll(false); }

function count() {
  var n = 0;
  for (var i = 0; i < LINE_IDS.length; i++) {
    var c = el('c_' + LINE_IDS[i]);
    if (c && c.checked) n++;
  }
  el('pk-count').textContent = n + (n === 1 ? ' line' : ' lines');
  var warn = el('pk-none');
  if (warn) warn.style.display = n ? 'none' : '';
}

/* Only ticked lines are posted. The server refuses an empty selection rather
   than writing an empty __DOC_WORD__ — this is a courtesy to the wire, not the rule. */
function saveJSON() {
  var lines = [];
  for (var i = 0; i < LINE_IDS.length; i++) {
    var lid = LINE_IDS[i], c = el('c_' + lid);
    if (!c || !c.checked) continue;
    lines.push({line_id: lid,
                qty: (el('q_' + lid) || {}).value || ''__PCS_FIELD____RATE_FIELD__});
  }
  el('__PAYLOAD_ID__').value = JSON.stringify({lines: lines});
  return true;
}

count();
</script>
"""

_PCS_FIELD = """,
                pcs: (el('p_' + lid) || {}).value || ''"""

_RATE_FIELD = """,
                rate: (el('r_' + lid) || {}).value || ''"""


def js(payload_id: str, doc_word: str, with_pcs: bool = False,
       with_rate: bool = False) -> str:
    """The fold, the ticks and the payload builder, wired to one form."""
    return (_JS_TEMPLATE
            .replace("__DOC_WORD__", doc_word)
            .replace("__PCS_FIELD__", _PCS_FIELD if with_pcs else "")
            .replace("__RATE_FIELD__", _RATE_FIELD if with_rate else "")
            .replace("__PAYLOAD_ID__", payload_id))


def grid_html(boq: dict, *, title: str, intro_html: str, qty_label: str,
              qty_aria: str, empty_note: str, payload_id: str, doc_word: str,
              chosen: set = None, qty_of: dict = None,
              with_pcs: bool = False, avail_label: str = "In BOQ",
              with_rate: bool = False, rate_of: dict = None,
              rate_label: str = "Rate", rate_aria: str = "Rate") -> str:
    """
    The whole grid as one form section — tools bar, table, refusal band, and
    the script that drives them.

    Everything a reader sees is passed in. `title`, `intro_html`, `qty_label`
    and `empty_note` are the document's own words; a purchase order and a
    delivery challan say different things about the same grid, and hard-coding
    either one here is how a shared component starts lying about the page it is
    on.
    """
    pcs_head = ('\n              <th class="pk-pcs">Pcs</th>') if with_pcs else ""
    rate_head = (f'\n              <th class="pk-rate">{rate_label}</th>'
                 if with_rate else "")
    return f"""
      <div class="form-section">
        <div class="section-title">{title}</div>
{intro_html}
        <div class="pk-tools">
          <button type="button" class="btn btn-ghost" onclick="selectAll()">Select all</button>
          <button type="button" class="btn btn-ghost" onclick="clearAll()">Clear all</button>
          <button type="button" class="btn btn-ghost" onclick="expandAll()">Expand all</button>
          <button type="button" class="btn btn-ghost" onclick="collapseAll()">Collapse all</button>
          <span class="spacer"></span>
          <span><span class="pk-count" id="pk-count">0 lines</span> selected</span>
        </div>
        <div class="pk-wrap">
          <table class="pk-table">
            <thead><tr>
              <th class="pk-tick"></th>
              <th class="pk-no">Item</th>
              <th class="pk-desc">Description</th>
              <th class="pk-unit">Unit</th>
              <th class="pk-avail">{avail_label}</th>
              <th class="pk-in">{qty_label}</th>{pcs_head}{rate_head}
            </tr></thead>
            <tbody>{rows_html(boq, chosen, qty_of, with_pcs, qty_aria,
                              with_rate, rate_of, rate_aria)}</tbody>
          </table>
        </div>
        <div class="alert alert-error pk-none" id="pk-none">
          {empty_note}
        </div>
      </div>
      <script>
        var LINE_IDS = {BQ._json_for_script(line_ids(boq))};
        var FAMILIES = {BQ._json_for_script(families(boq))};
      </script>
      {js(payload_id, doc_word, with_pcs, with_rate)}"""


# =============================================================================
# POST PARSING — only the lines that were ticked
# =============================================================================

def picked_lines(raw: str, boq: dict, *, empty_msg: str, cap_msg: str,
                 max_lines: int = None, with_pcs: bool = False,
                 with_rate: bool = False) -> tuple:
    """
    Returns `(items, error)` — the BOQ lines that were **ticked**, snapshotted.

    Matching is on **`line_id`** and never on `item_no` (CLIENT_CHANGES.md
    §1.4): item numbers restart per section and the client's own section A
    carries item 17 twice. A posted row whose id is not on this BOQ is dropped
    rather than guessed at.

    Specification headers come across with their family, carrying **no
    quantity** — they are the clause the sizes under them are described by, and
    the person reading the document needs it (DOMAIN.md §2.2). They are not
    themselves pickable, so they are never ticked and never counted toward the
    line total.

    ⚠ **The keys read off a BOQ line are `description` and `is_header`.** They
      are not `desc` and not `type`. `po_draft` read the wrong two and
      snapshotted every row with an empty description; two of its three tests
      passed against that, because they asserted `"" in html`.

    `with_rate` carries the rate box back off the form as a float on each
    non-header row. A **blank or unparseable** box falls back to the BOQ's
    `supply_base_rate`, and a missing base rate falls back to `0.0` — exactly
    the quantity's rule one field over, and for its reason: the prefill is what
    the operator saw, so an empty box means "as offered", never "free".
    """
    if max_lines is None:
        max_lines = BQ.MAX_LINES
    try:
        payload = json.loads(raw or "{}")
        rows = payload.get("lines") or []
    except (ValueError, TypeError):
        return [], "The line selection did not survive the round trip. Nothing was saved."

    if not isinstance(rows, list):
        return [], "The line selection did not survive the round trip. Nothing was saved."

    by_lid = {}
    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if lid:
            by_lid[lid] = li

    # Which ids the operator actually ticked.
    picked, qty_of, rate_of = [], {}, {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        lid = BQ._line_id(row.get("line_id"))
        if not lid or lid not in by_lid:
            continue
        picked.append(lid)
        qty_of[lid] = row.get("qty")
        rate_of[lid] = row.get("rate")

    if not picked:
        return [], empty_msg
    if len(picked) > max_lines:
        return [], (f"{len(picked)} lines selected; the limit is "
                    f"{max_lines}. {cap_msg}")

    chosen = set(picked)

    # Walk the BOQ in ORDER rather than the posted list, so the document reads
    # in schedule order however the browser happened to serialise it. A header
    # is carried whenever one of its children was ticked.
    wanted_headers = set()
    for li in boq.get("line_items") or []:
        if li.get("is_header"):
            continue
        if BQ._line_id(li.get("line_id")) in chosen:
            parent = BQ._item_no(li.get("parent_item_no"))
            if parent:
                wanted_headers.add((str(li.get("section") or ""), parent))

    extra = {"pcs": ""} if with_pcs else {}
    if with_rate:
        # A specification header carries the clause and no money — the same
        # reason it carries no quantity. Present and zero rather than absent, so
        # every row this function returns has one shape.
        extra = {**extra, "rate": 0.0}
    items = []
    for li in boq.get("line_items") or []:
        lid = BQ._line_id(li.get("line_id"))
        if li.get("is_header"):
            key = (str(li.get("section") or ""), BQ._item_no(li.get("item_no")))
            if key in wanted_headers:
                items.append({
                    "line_id": lid,
                    "is_header": True,
                    "item_no": BQ._item_no(li.get("item_no")),
                    "description": str(li.get("description") or ""),
                    "unit": "", "qty": 0.0, **extra,
                })
            continue
        if lid not in chosen:
            continue
        # The quantity is editable on the form and defaults to the BOQ's. A
        # blank or unparseable box falls back to the schedule's figure rather
        # than to zero: zero would be a silent instruction to move nothing.
        qty = BQ._num(qty_of.get(lid), None)
        if qty is None or qty < 0:
            qty = float(li.get("total_qty") or 0.0)
        row = {
            "line_id": lid,
            "is_header": False,
            "item_no": BQ._item_no(li.get("item_no")),
            "description": str(li.get("description") or ""),
            "unit": str(li.get("unit") or ""),
            "qty": float(qty),
            **extra,
        }
        if with_rate:
            # The prefill is the SUPPLY base rate. The installation track is
            # labour and is never read here — purchase.INCLUDE_INSTALL_TRACK.
            rate = BQ._num(rate_of.get(lid), None)
            if rate is None or rate < 0:
                base = li.get("supply_base_rate")
                rate = 0.0 if base is None else float(base)
            row["rate"] = float(rate)
        items.append(row)
    return items, ""
