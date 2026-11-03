"""
lineedit.py — the editable line table every document's EDIT form shares
=======================================================================

31 October 2026, CLIENT_CHANGES.md §0 sixty-fourth block. The proforma, the
standalone tax invoice and the quotation gained an edit form whose lines can be
added, removed, reordered and changed — description, part no, make, HSN,
quantity, unit, rate, discount and GST. One widget rather than three, for
`docsheet.py`'s reason: three copies of a line editor are three chances for
the arithmetic to disagree.

How it works
------------
* The page draws `editor_html(rows)`: the rows are handed to a small script
  as JSON, the script draws the table and, on submit, writes every row back
  into ONE hidden field (`lines_json`) — `boqpick.py`'s arrangement.
* Each row the record already had carries `_k`, its index in the stored list.
  **The server copies the keys nobody edits on this form (`line_id`, `leg`,
  `image`, `depth`, `type`, …) from the STORED row `_k` names, never from the
  post** — so a picture, a BOQ line id or a leg cannot be forged by editing
  the JSON in a browser. A new row has no `_k` and gets none of them.
* `parse()` refuses text typed into a numeric box (naming the line), a blank
  description, and a quantity that is not above zero — every other value is
  stored as typed.
* `price()` writes each line's amount to the paisa HALF UP:
  `qty × rate × (1 − discount/100)`. `discount_pct` and `make` are written
  only when non-blank, so an edited record without either has the shape it
  always had.
* `tax_figures()` is `proforma.boq_figures()`'s per-slab rule (one tax row per
  rate slab, rounded once per slab) extended to VAT and exempt, so a quotation
  — which may not import `proforma.py` — computes the same figures.

A LEAF: imports `pipeline` and `roundoff` only.
"""

import json

import pipeline as P
import roundoff as RO

FIELD = "lines_json"
EXTRA_FIELD = "extra_json"     # a create form's imported extra lines (Part 5)
SOURCE_EXCEL = "excel"         # `source` on a line that came in from a sheet

# What the form edits. Everything else on a stored row is carried from it.
EDITED = ("name", "part_no", "make", "hsn", "qty", "unit", "price",
          "discount_pct", "gst_rate", "is_header")

COLUMNS = (("name", "Description"), ("part_no", "Part / Item No"),
           ("make", "Make"), ("hsn", "HSN/SAC"), ("qty", "Qty"),
           ("unit", "Unit"), ("price", "Rate"), ("discount_pct", "Disc %"),
           ("gst_rate", "GST %"))

NUMERIC = ("qty", "price", "discount_pct", "gst_rate")


def _num_text(v) -> str:
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:g}" if f != int(f) else str(int(f))


def uniform_gst(tax_type: str, tax_info: dict) -> float:
    """The one GST rate a quotation-shaped `tax_info` implies, or 0."""
    t = tax_info or {}
    if tax_type == "cgst_sgst":
        return float(t.get("cgst_rate") or 0) + float(t.get("sgst_rate") or 0)
    if tax_type == "igst":
        return float(t.get("igst_rate") or 0)
    if tax_type == "vat":
        return float(t.get("vat_rate") or 0)
    return 0.0


def rows_for_form(lines: list, default_gst: float) -> list:
    """The stored lines as the editor's rows, each tagged with `_k`."""
    out = []
    for k, r in enumerate(lines or []):
        gst = r.get("gst_rate")
        out.append({
            "_k": k,
            "is_header": bool(r.get("is_header")),
            "name": str(r.get("name") or ""),
            "part_no": str(r.get("part_no") or ""),
            "make": str(r.get("make") or ""),
            "hsn": str(r.get("hsn") or ""),
            "qty": _num_text(r.get("qty")),
            "unit": str(r.get("unit") or ""),
            "price": _num_text(r.get("price")),
            "discount_pct": _num_text(r.get("discount_pct")),
            "gst_rate": _num_text(gst if gst not in (None, "") else default_gst),
        })
    return out


def posted_rows(raw: str) -> list:
    """The editor's rows off a POST, for a redraw — never trusted for `_k` keys."""
    try:
        rows = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = {k: str(r.get(k) if r.get(k) is not None else "") for k in EDITED
               if k != "is_header"}
        row["is_header"] = bool(r.get("is_header"))
        k = r.get("_k")
        if isinstance(k, int) and not isinstance(k, bool) and k >= 0:
            row["_k"] = k
        # A row that came in from a sheet (Part 5) keeps its one mark — the
        # only value accepted is the literal, so nothing else rides along.
        if r.get("source") == SOURCE_EXCEL:
            row["source"] = SOURCE_EXCEL
        out.append(row)
    return out


def _float(text: str):
    t = str(text or "").strip().replace(",", "").replace("%", "")
    if not t:
        return None
    return float(t)


def parse(raw: str, stored: list, *, default_gst: float = 0.0,
          gst: bool = True, min_lines: int = 1) -> tuple:
    """
    `(lines, error)` — the posted rows as stored lines, priced to the paisa.
    `stored` is the record's current list; `_k` reaches into it for the keys
    this form does not edit.
    """
    rows = posted_rows(raw)
    out, items = [], 0
    for n, r in enumerate(rows, 1):
        k = r.get("_k")
        base = dict(stored[k]) if isinstance(k, int) and k < len(stored or []) else {}
        for key in EDITED:
            base.pop(key, None)
        name = r.get("name", "").strip()
        if r.get("is_header"):
            if not name:
                continue
            base.update({"is_header": True, "name": name, "part_no": r.get("part_no", "").strip(),
                         "hsn": "", "qty": 0.0, "unit": "", "price": 0.0, "total": 0.0})
            base.setdefault("type", "item")
            base.setdefault("depth", 0)
            out.append(base)
            continue
        vals = {}
        for key in NUMERIC:
            try:
                vals[key] = _float(r.get(key, ""))
            except ValueError:
                return [], (f"Line {n}: “{P.esc(r.get(key, ''))}” is not a number "
                            f"({dict(COLUMNS)[key]}).")
        if not name:
            return [], f"Line {n} has no description."
        qty = vals["qty"]
        if qty is None or qty <= 0:
            return [], f"Line {n} ({P.esc(name)}): the quantity must be greater than zero."
        price = vals["price"] if vals["price"] is not None else 0.0
        if price < 0:
            return [], f"Line {n} ({P.esc(name)}): the rate cannot be negative."
        disc = vals["discount_pct"] or 0.0
        if not (0 <= disc < 100):
            return [], f"Line {n} ({P.esc(name)}): a discount is from 0 to under 100 %."
        rate = vals["gst_rate"]
        if rate is None:
            rate = default_gst
        if rate < 0 or rate > 100:
            return [], f"Line {n} ({P.esc(name)}): GST % must be between 0 and 100."
        base.update({
            "is_header": False,
            "name": name,
            "part_no": r.get("part_no", "").strip(),
            "hsn": r.get("hsn", "").strip(),
            "qty": float(qty),
            "unit": r.get("unit", "").strip(),
            "price": float(price),
        })
        base.setdefault("type", "item")
        base.setdefault("depth", 0)
        if not isinstance(k, int) and r.get("source") == SOURCE_EXCEL:
            base["source"] = SOURCE_EXCEL
        make = r.get("make", "").strip()
        if make:
            base["make"] = make
        if disc:
            base["discount_pct"] = float(disc)
        if gst:
            base["gst_rate"] = float(rate)
        base["total"] = line_amount(base)
        out.append(base)
        items += 1
    if items < min_lines:
        return [], "A document needs at least one priced line."
    return out, ""


def line_amount(row: dict) -> float:
    """qty × rate × (1 − discount/100), to the paisa HALF UP."""
    qty = float(row.get("qty") or 0.0)
    price = float(row.get("price") or 0.0)
    disc = float(row.get("discount_pct") or 0.0)
    return RO.paise(qty * price * (1 - disc / 100.0))


def tax_figures(items: list, tax_type: str, round_on: bool = True) -> tuple:
    """
    `(subtotal, tax_info, grand_total, round_off, total_qty)` — per GST slab,
    rounded once per slab (`proforma.boq_figures()`'s rule), VAT likewise,
    exempt carrying no tax.
    """
    slabs, total_qty = {}, 0.0
    for r in items:
        if r.get("is_header"):
            continue
        rate = float(r.get("gst_rate") or 0.0)
        slabs[rate] = slabs.get(rate, 0.0) + float(r.get("total") or 0.0)
        if not r.get("depth"):
            total_qty += float(r.get("qty") or 0.0)
    subtotal = RO.paise(sum(slabs.values()))
    tax_info, total = {}, 0.0
    if tax_type in ("cgst_sgst", "igst", "vat") and slabs:
        one = len(slabs) == 1
        for rate in sorted(slabs):
            taxable = slabs[rate]
            if tax_type == "igst":
                amt = RO.paise(taxable * rate / 100.0)
                tax_info["IGST" if one else f"IGST @ {rate:g}%"] = amt
                total += amt
            elif tax_type == "vat":
                amt = RO.paise(taxable * rate / 100.0)
                tax_info["VAT" if one else f"VAT @ {rate:g}%"] = amt
                total += amt
            else:
                half = RO.paise(taxable * rate / 200.0)
                tax_info["CGST" if one else f"CGST @ {rate / 2:g}%"] = half
                tax_info["SGST" if one else f"SGST @ {rate / 2:g}%"] = half
                total += 2 * half
        if one:
            rate = next(iter(slabs))
            if tax_type == "igst":
                tax_info["igst_rate"] = rate
            elif tax_type == "vat":
                tax_info["vat_rate"] = rate
            else:
                tax_info["cgst_rate"] = rate / 2
                tax_info["sgst_rate"] = rate / 2
    tax_info["total"] = RO.paise(total)
    grand, ro = RO.apply(subtotal + tax_info["total"], round_on)
    return subtotal, tax_info, grand, ro, total_qty


def print_note(row: dict) -> str:
    """
    The make and the discount, under the description on a printed sheet —
    "" for a line carrying neither, so every sheet saved before this date
    prints byte-for-byte as it did.
    """
    bits = []
    if row.get("make"):
        bits.append(f"Make: {P.esc(row.get('make'))}")
    if row.get("discount_pct"):
        bits.append(f"Discount {_num_text(row.get('discount_pct'))}%")
    if not bits:
        return ""
    return (f'<br/><span style="font-size:.85em;color:#555;">'
            f'{" &middot; ".join(bits)}</span>')


EDITOR_CSS = """
<style>
  .le-wrap { overflow-x:auto; }
  .le-table { width:100%; border-collapse:collapse; font-size:.85rem; }
  .le-table th { text-align:left; font-size:.72rem; text-transform:uppercase;
                 color:var(--muted); padding:.3rem .25rem; }
  .le-table td { padding:.2rem .25rem; vertical-align:top; }
  .le-table input { width:100%; min-width:4.5rem; }
  .le-table td.le-desc input { min-width:14rem; }
  .le-table tr.le-head td { background:#f5f7fa; }
  .le-acts { white-space:nowrap; }
  .le-acts button { padding:.15rem .4rem; font-size:.8rem; }
  .le-bar { display:flex; gap:.5rem; margin-top:.6rem; flex-wrap:wrap; }
</style>
"""


def source_entry(value: str, group: str, label: str, row: dict) -> dict:
    """
    One line the editor can ADD from a source (2 Nov 2026, the full-edit
    pass): the Specification library, the parent document's own lines, a
    BOQ. `row` is the editor row it becomes — strings, no `_k` — so a pick
    lands as a NEW line the operator can still change in every column.
    """
    clean = {k: str(row.get(k) if row.get(k) is not None else "") for k in EDITED
             if k != "is_header"}
    clean["is_header"] = False
    return {"value": str(value), "group": str(group), "label": str(label), "row": clean}


def parent_sources(lines: list, group: str, default_gst: float = 0.0) -> list:
    """
    A parent document's own lines (the quotation a PI was raised from, the PI
    a TI was raised from, …) as `source_entry()`s — the create path's source
    on the EDIT form (2 Nov 2026). Headings are not offered.
    """
    out = []
    for k, r in enumerate(rows_for_form(lines or [], default_gst)):
        if r.get("is_header"):
            continue
        r.pop("_k", None)
        out.append(source_entry(f"p:{k}", group,
                                f"{r.get('part_no') or ''} {r.get('name') or ''}".strip()[:110],
                                r))
    return out


def editor_html(rows: list, *, gst: bool = True, field: str = FIELD,
                form_selector: str = "form", sources: list = None) -> str:
    """
    The table, its buttons, and the script that posts it as one field.

    `sources` (2 Nov 2026) — `source_entry()` dicts — adds a searchable
    dropdown and an *Add picked line* button above *+ Add line*. None (every
    caller before that date) draws exactly what it drew.
    """
    cols = [c for c in COLUMNS if gst or c[0] != "gst_rate"]
    head = "".join(f"<th>{lbl}</th>" for _k, lbl in cols)
    sel = form_selector.replace("\\", "\\\\").replace("'", "\\'")
    script = """<script>
(function () {
  var ROWS = %(rows)s;
  var COLS = %(cols)s;
  var NUM = {qty:1, price:1, discount_pct:1, gst_rate:1};
  var body = document.getElementById('le-body');
  var out = document.getElementById(%(field_js)s);
  function cell(tr, row, key) {
    var td = document.createElement('td');
    if (key === 'name') td.className = 'le-desc';
    if (row.is_header && key !== 'name' && key !== 'part_no') { tr.appendChild(td); return; }
    var i = document.createElement('input');
    i.type = 'text'; i.value = row[key] || '';
    if (NUM[key]) { i.inputMode = 'decimal'; i.style.textAlign = 'right'; }
    i.setAttribute('aria-label', key);
    i.addEventListener('input', function () { row[key] = i.value; });
    td.appendChild(i); tr.appendChild(td);
  }
  function btn(txt, title, fn) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'btn btn-ghost'; b.textContent = txt; b.title = title;
    b.addEventListener('click', fn); return b;
  }
  function draw() {
    body.innerHTML = '';
    ROWS.forEach(function (row, idx) {
      var tr = document.createElement('tr');
      if (row.is_header) tr.className = 'le-head';
      COLS.forEach(function (c) { cell(tr, row, c); });
      var td = document.createElement('td'); td.className = 'le-acts';
      td.appendChild(btn('\\u2191', 'Move up', function () {
        if (idx > 0) { var t = ROWS[idx - 1]; ROWS[idx - 1] = row; ROWS[idx] = t; draw(); } }));
      td.appendChild(btn('\\u2193', 'Move down', function () {
        if (idx < ROWS.length - 1) { var t = ROWS[idx + 1]; ROWS[idx + 1] = row; ROWS[idx] = t; draw(); } }));
      td.appendChild(btn('\\u2715', 'Remove this line', function () { ROWS.splice(idx, 1); draw(); }));
      tr.appendChild(td);
      body.appendChild(tr);
    });
    out.value = JSON.stringify(ROWS);
  }
  document.getElementById('le-add').addEventListener('click', function () {
    var last = ROWS.length ? ROWS[ROWS.length - 1] : {};
    ROWS.push({name:'', part_no:'', make:'', hsn:'', qty:'', unit:'', price:'',
               discount_pct:'', gst_rate: last.gst_rate || '', is_header:false});
    draw();
  });
  document.getElementById('le-add-head').addEventListener('click', function () {
    ROWS.push({name:'', part_no:'', is_header:true}); draw();
  });
  var pick = document.getElementById('le-src');
  var SRC = %(src)s;
  if (pick) {
    document.getElementById('le-add-src').addEventListener('click', function () {
      var e = SRC[pick.value];
      if (!e) return;
      var r = {}; for (var k in e.row) { r[k] = e.row[k]; }
      ROWS.push(r); pick.value = ''; draw();
    });
    var find = document.getElementById('le-find');
    if (find) find.addEventListener('input', function () {
      var w = find.value.toLowerCase().split(/\\s+/).filter(function (x) { return x; });
      Array.prototype.forEach.call(pick.querySelectorAll('option'), function (o) {
        if (!o.value) return;
        var t = o.textContent.toLowerCase();
        o.hidden = !w.every(function (x) { return t.indexOf(x) !== -1; });
      });
    });
  }
  var form = document.querySelector('%(sel)s');
  if (form) form.addEventListener('submit', function () { out.value = JSON.stringify(ROWS); });
  draw();
})();
</script>""" % {"rows": P.json_for_script(rows), "cols": P.json_for_script([k for k, _ in cols]),
                "field_js": P.json_for_script(field), "sel": sel,
                "src": P.json_for_script({e["value"]: e for e in (sources or [])})}
    src_bar = ""
    if sources:
        groups: dict = {}
        for e in sources:
            groups.setdefault(e["group"], []).append(e)
        opts = '<option value="">&#8212; pick a line to add &#8212;</option>' + "".join(
            f'<optgroup label="{P.esc(g)}">' + "".join(
                f'<option value="{P.esc(e["value"])}">{P.esc(e["label"])}</option>'
                for e in es) + "</optgroup>" for g, es in groups.items())
        src_bar = (f'<div class="le-bar"><input type="search" id="le-find" '
                   f'placeholder="Search, e.g. GI 50" aria-label="Search lines to add" '
                   f'autocomplete="off"/><select id="le-src" aria-label="Line to add" '
                   f'style="max-width:32rem;">{opts}</select>'
                   f'<button type="button" class="btn btn-ghost" id="le-add-src">'
                   f'+ Add picked line</button></div>')
    return f"""{EDITOR_CSS}
<div class="le-wrap"><table class="le-table">
  <thead><tr>{head}<th></th></tr></thead>
  <tbody id="le-body"></tbody>
</table></div>
<input type="hidden" id="{P.esc(field)}" name="{P.esc(field)}" value="{P.esc(json.dumps(rows))}"/>
{src_bar}<div class="le-bar">
  <button type="button" class="btn btn-ghost" id="le-add">+ Add line</button>
  <button type="button" class="btn btn-ghost" id="le-add-head">+ Add heading</button>
</div>
{script}"""


# ── Imported extra lines (31 Oct 2026, §0 sixty-fourth block, Part 5) ────────

def imported_rows(rows) -> list:
    """Rows a sheet produced, as editor rows: strings, no `_k`, marked excel."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        row = {k: str(r.get(k) if r.get(k) is not None else "") for k in EDITED
               if k != "is_header"}
        row["is_header"] = False
        row["source"] = SOURCE_EXCEL
        out.append(row)
    return out


def extras_html(rows: list, import_url: str = "") -> str:
    """
    A create form's extra lines: a read-only list and the hidden field that
    carries them to the save. "" when there are none and no import link —
    so a create form nobody imported onto renders exactly as it did.
    """
    link = (f'<a class="btn btn-ghost" href="{P.esc(import_url)}">&#128229; Add lines '
            f'from Excel</a>' if import_url else "")
    if not rows:
        return (f'<div class="le-bar" style="margin:.4rem 0 1rem;">{link}</div>'
                if link else "")
    body = "".join(
        f'<tr><td>{P.esc(r.get("name"))}</td><td>{P.esc(r.get("make"))}</td>'
        f'<td>{P.esc(r.get("hsn"))}</td><td style="text-align:right;">{P.esc(r.get("qty"))}</td>'
        f'<td>{P.esc(r.get("unit"))}</td><td style="text-align:right;">{P.esc(r.get("price"))}</td>'
        f'<td style="text-align:right;">{P.esc(r.get("discount_pct"))}</td>'
        f'<td style="text-align:right;">{P.esc(r.get("gst_rate"))}</td></tr>' for r in rows)
    return f"""{EDITOR_CSS}
<div class="form-section">
  <div class="section-title">Extra lines from Excel &mdash; added after the copied lines</div>
  <div class="le-wrap"><table class="le-table">
    <thead><tr><th>Description</th><th>Make</th><th>HSN</th><th>Qty</th><th>Unit</th>
      <th>Rate</th><th>Disc %</th><th>GST %</th></tr></thead>
    <tbody>{body}</tbody></table></div>
  <p class="frozen-hint">These come in as extra lines; the lines copied above are not
    changed. A blank GST % is taxed at the document's rate. To change one, raise the
    proforma and use <b>Edit</b>.</p>
  <input type="hidden" name="{EXTRA_FIELD}" value="{P.esc(json.dumps(rows))}"/>
  <div class="le-bar">{link}</div>
</div>"""
