"""
specpick.py — the SPECIFICATION-LIBRARY picker for a quotation, behind the switch
==================================================================================

The picker `/quotation/create` draws while the product catalogue is hidden —
the embed, the POST rebuild, the GST guard and the page pieces — lifted out of
`quotation.py` on 12 September 2026 (CLIENT_CHANGES.md §0, twenty-eighth
block) so that file only **branches on the switch** inside its three unfrozen
functions and carries the product picker exactly as it stood at `1d7725a`.

Why a leaf, and which way the arrow runs
----------------------------------------
`quotation.py` is frozen (INTRODUCTION.md §7) with exactly three functions set
aside for this work, and the freeze test in `tests/test_nav_user_chip.py`
refuses an edit anywhere else in that file — a module-level import included.
So `quotation.py` reaches this module **inside those three functions only**,
and this module never imports `quotation.py` back: everything the picker needs
from the sell chain — the quantity formatter for the GST message — is passed
in as an argument. The arrow is one-way, at function scope, and
`tests/test_import_directions.py` pins it.

`spec.ensure_demo_specs()` is imported inside `ensure_seeded()` and nowhere
else, the arrangement `quotation.create_quotation()` always had for the seeder
it calls, so the module graph in ABOUT.md §2 gains no edge for one seeding
call. The two module-level imports are `store` and `pipeline`, both already at
the bottom of the graph.

The switch itself is NOT read here
----------------------------------
`auth.blueprint_hidden("product")` is the one accessor, and `quotation.py`
reads it. This module answers only *what a library pick is* and *what the
library page looks like*; it does not decide whether it is in use. That keeps
the decision in one place — the three functions that already branch on it —
rather than in two that could disagree.

What a pick is
--------------
`{sid, vidx, leg, qty, price, show_price}` — a spec id, a variant index, and
which leg of the work, `supply` or `install`. **Identity comes from the
library at POST**: name, code, HSN/SAC and unit are re-read from
`STORE["specs"]` and the form's copies are ignored; only the quantity, the
price and the show-price flag are the browser's. The mapping is the
twenty-seventh block's:

    name     "Supply of <title> — <variant>" / "Installation of <title> — <variant>"
    part_no  the spec code
    hsn      supply_hsn on a supply line, install_sac on an installation line
    unit     the variant's unit
    price    the variant's library rate, SUGGESTED and editable

The line-item shape is `quotation.py`'s and is untouched — a proforma and a
tax invoice copy it — so a quotation written from either library views,
prints and raises a PI and a TI identically.
"""

import pipeline as P
from store import STORE


# The two refusals `create_quotation()` states in the library's words. Named
# here so the page and the POST cannot spell one message two ways.
INVALID_ERROR = "Invalid item selection data. Please re-add your items."
EMPTY_ERROR = "Please add at least one item from the specification library."

# The library's own category order, for the <optgroup>s. A category the seed
# does not know is appended alphabetically rather than dropped.
CATEGORY_ORDER = ["Piping", "Valves", "Sprinklers", "Hydrant", "Pumps",
                  "Panels", "Civil", "Other"]


def ensure_seeded() -> None:
    """
    Seed the library if it is empty — `spec.ensure_demo_specs()`, imported in
    the function body so this leaf's module graph stays at `store` and
    `pipeline` (see the module docstring).
    """
    from spec import ensure_demo_specs
    ensure_demo_specs()


# =============================================================================
# THE EMBED
# =============================================================================

def catalog_json() -> str:
    """
    The specification library, embedded for the picker.

    One entry per spec, keyed by spec id. A variant carries the two library
    rates as numbers **or null** — null means the library has no rate for that
    leg, and the picker then opens an EMPTY price box rather than a zero, so a
    figure nobody chose cannot reach the document.

    NOT a bare `json.dumps`: `json.dumps` does not escape `<`, so a clause
    titled `…</script>…` would close the block this is embedded in and every
    byte after it would parse as HTML. ABOUT.md §7 gap 9e.
    """
    library: dict = {}
    for sid, s in STORE["specs"].items():
        library[sid] = {
            "code":             s.get("code", ""),
            "title":            s.get("title", ""),
            "category":         s.get("category", ""),
            "supply_hsn":       s.get("supply_hsn", ""),
            "install_sac":      s.get("install_sac", ""),
            "supply_gst_rate":  s.get("supply_gst_rate"),
            "install_gst_rate": s.get("install_gst_rate"),
            "variants": [{
                "label":        v.get("label", ""),
                "unit":         v.get("unit", ""),
                "supply_rate":  v.get("default_supply_base_rate"),
                "install_rate": v.get("default_install_base_rate"),
            } for v in (s.get("variants") or [])],
        }
    return P.json_for_script(library)


# =============================================================================
# THE POST — picks become lines, or the whole form is refused
# =============================================================================

def process_selections(data: list) -> tuple:
    """
    The browser's picks → quotation `line_items`, or a refusal.

    Returns `(line_items, error, gst_rates)`. `error` is a plain sentence
    (escaped by the caller at the interpolation site) and the other two are
    empty when it is set. `gst_rates` is one `(line name, library GST rate)`
    per line, for `gst_guard()` — the line-item shape itself is untouched,
    because a proforma and a tax invoice copy it.

    A spec that no longer exists, or a variant index the spec no longer has,
    refuses the whole POST rather than dropping the line silently — a
    quotation missing a line nobody removed is worse than a form asking to be
    re-checked.

    ⚠ **A shown line with no price is REFUSED.** A leg the library has no rate
    for opens with an empty box; leaving it empty is not choosing zero, and a
    `0.00` printed against work somebody forgot to price is the figure this
    refusal exists to stop. A deliberately typed `0` is a price and is kept —
    the same "included, no separate charge" convention `show_price` off gives.

    ⚠ Two depths exist in the record shape and only depth 0 is written here:
    a clause has no bill of materials, so there is nothing to indent. Every
    existing quotation keeps whatever depth-1 rows it has.
    """
    line_items = []
    gst_rates = []
    for n, item in enumerate(data, start=1):
        sid = str(item.get("sid") or "")
        spec = STORE["specs"].get(sid)
        if not spec:
            return [], (f"Line {n}: that specification no longer exists in the "
                        f"library. Remove it and pick again."), []
        variants = spec.get("variants") or []
        try:
            vidx = int(item.get("vidx", 0))
            variant = variants[vidx]
        except (TypeError, ValueError, IndexError):
            return [], (f"Line {n}: the size chosen for '{spec.get('title', '')}' "
                        f"is no longer in the library. Remove it and pick again."), []
        leg = str(item.get("leg") or "")
        if leg not in ("supply", "install"):
            return [], f"Line {n}: choose Supply or Installation.", []

        label = (variant.get("label") or "").strip()
        title = (spec.get("title") or "").strip()
        name = ("Supply of " if leg == "supply" else "Installation of ") + title
        if label:
            name += " — " + label

        try:
            qty = float(item.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            return [], f"Line {n} ({name}): quantity must be greater than zero.", []

        show_price = bool(item.get("show_price", True))
        raw_price = item.get("price")
        if raw_price is None or str(raw_price).strip() == "":
            if show_price:
                return [], (f"Line {n} ({name}): no price. The library has no "
                            f"rate for this leg — type one, or untick Show "
                            f"Price to include it at no separate charge."), []
            price = 0.0
        else:
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                return [], f"Line {n} ({name}): the price is not a number.", []
            if price < 0:
                return [], f"Line {n} ({name}): the price cannot be negative.", []
        eff_price = price if show_price else 0.0

        line_items.append({
            "type":    "item",
            "name":    name,
            "part_no": spec.get("code", ""),
            "hsn":     spec.get("supply_hsn", "") if leg == "supply"
                       else spec.get("install_sac", ""),
            "qty":     qty,
            "unit":    variant.get("unit", ""),
            "price":   eff_price,
            "total":   eff_price * qty,
            "depth":   0,
        })
        rate = spec.get("supply_gst_rate") if leg == "supply" else spec.get("install_gst_rate")
        gst_rates.append((name, rate))

    return line_items, "", gst_rates


def gst_guard(gst_rates: list, tax_type: str, cgst_rate: float, sgst_rate: float,
              igst_rate: float, fmt) -> str:
    """
    ONE tax per quotation, and nothing is auto-applied. The refusal, or `""`.

    The library stores a GST rate per leg of every clause; a quotation carries
    one document-level tax (`quotation._tax_lines()`). The two are reconciled
    here and NEVER by changing either: the POST is refused, naming the lines
    and the rates, when the picked lines' library rates disagree with each
    other or with the Tax section's effective rate. Exempt and VAT are outside
    the GST heads and are not compared. A clause whose library rate is blank
    makes no claim and is skipped. Per-line tax on the sell chain is not built
    — CLIENT_CHANGES.md §0, 11 September 2026.

    `fmt` is the caller's quantity formatter (`quotation._fmt_qty`), passed in
    so this leaf never imports the module that imports it.
    """
    effective = None
    if tax_type == "cgst_sgst":
        effective = cgst_rate + sgst_rate
    elif tax_type == "igst":
        effective = igst_rate
    if effective is None:
        return ""
    claimed = [(n, float(r)) for n, r in gst_rates if r is not None]
    distinct = sorted({r for _, r in claimed})
    if len(distinct) > 1 or (distinct and abs(distinct[0] - effective) > 1e-9):
        head = (f"CGST {fmt(cgst_rate)}% + SGST {fmt(sgst_rate)}%"
                if tax_type == "cgst_sgst" else f"IGST {fmt(igst_rate)}%")
        named = "; ".join(f"'{n}' at {fmt(r)}%" for n, r in claimed)
        return (f"GST rates do not agree. A quotation carries one tax, "
                f"and the Tax section says {fmt(effective)}% ({head}), "
                f"but the library rates the picked lines at: {named}. "
                f"Change the Tax section to match, or pick lines that "
                f"share one rate — nothing is applied for you.")
    return ""


# =============================================================================
# THE PAGE — the eight seams the shared template leaves open
# =============================================================================
# `quotation.create_quotation()` holds ONE page template — the one that stood
# at `1d7725a` — with eight placeholders where the two pickers differ. In the
# product mode those are filled with the `1d7725a` text, held inside that
# function; in the library mode they are filled from here. Everything that is
# not picker-specific — the form, the address book, the tax panel, the shared
# JavaScript — exists once, in the template, and neither mode can drift from
# the other in it.
#
# ⚠ **The JavaScript here is PLAIN text with SINGLE braces.** The template is
#   a `str.format` string whose own JS doubles every brace; a value substituted
#   by `.format()` is inserted verbatim and never re-parsed, so a fill must
#   carry the braces the browser is meant to see. Doubling one here would
#   put `{{` on the wire.

def spec_options_html(specs: dict) -> str:
    """
    The spec <select>'s options: one <optgroup> per category, in the library's
    own category order, each option carrying the spec id. Every value is
    escaped at the interpolation site — option TEXT included, which is the half
    the old product picker's `.replace('"', '&quot;')` missed (ABOUT.md §7.7).
    """
    by_cat: dict = {}
    for sid, s in specs.items():
        by_cat.setdefault((s.get("category") or "Other"), []).append((sid, s))
    cats = ([c for c in CATEGORY_ORDER if c in by_cat]
            + sorted(c for c in by_cat if c not in CATEGORY_ORDER))
    out = '<option value="">— select a specification —</option>'
    for cat in cats:
        rows = sorted(by_cat[cat], key=lambda kv: (kv[1].get("code") or "").lower())
        out += f'<optgroup label="{P.esc(cat)}">'
        for sid, s in rows:
            out += (f'<option value="{P.esc(sid)}">'
                    f'{P.esc(s.get("code", ""))} · {P.esc(s.get("title", ""))}</option>')
        out += '</optgroup>'
    return out


SECTION_HTML = """<!-- ════════ SECTION 3: ITEMS — from the specification library ════════ -->
<div class="form-section">
  <div class="section-title">&#128230;&nbsp; Item Details</div>
  <p style="font-size:.8rem;color:var(--muted);margin:-.4rem 0 .8rem;">
    Items are written from the <strong>specification library</strong> — the same
    clauses a BOQ is written from. Pick a clause, its size where it has one, and
    whether you are quoting the <em>supply</em>, the <em>installation</em>, or
    both; each leg becomes its own line with its own HSN/SAC. Library rates are
    suggestions and every price box stays editable.
  </p>

  <div class="picker-bar" style="grid-template-columns:minmax(0,2fr) minmax(0,1fr) 170px 90px auto;">
    <div class="form-group" style="margin:0;">
      <label for="picker-spec">Specification</label>
      <select id="picker-spec" onchange="onSpecPicked()">{spec_opts}</select>
    </div>
    <div class="form-group" style="margin:0;">
      <label for="picker-variant">Size / variant</label>
      <select id="picker-variant" disabled><option value="">&#8212;</option></select>
    </div>
    <div class="form-group" style="margin:0;">
      <label for="picker-leg">Quote</label>
      <select id="picker-leg">
        <option value="both" selected>Supply + Installation</option>
        <option value="supply">Supply only</option>
        <option value="install">Installation only</option>
      </select>
    </div>
    <div class="form-group" style="margin:0;">
      <label for="picker-qty">Qty</label>
      <input type="number" id="picker-qty" value="1" min="0.001" step="any"/>
    </div>
    <div class="form-group" style="margin:0;">
      <label style="visibility:hidden;">Add</label>
      <button type="button" class="btn" onclick="addProduct()">+ Add</button>
    </div>
  </div>
  <div id="add-error" class="add-error"></div>
  <div id="sel-container"></div>
  <div id="empty-notice">
    No items added yet. Pick a specification above and click <strong>+ Add</strong>.
  </div>
</div>"""

CATALOG_LOAD_ERROR = "The specification library failed to load — please refresh."
SUBMIT_EMPTY_MESSAGE = "Add at least one item before generating the quotation."

# A library pick has no components, so the restore loop has nothing to renumber
# beneath a row. The product picker's four lines go here in the other mode.
RESTORE_COMPONENT_RIDS_JS = ""

PICKER_ADD_JS = """/* ═══ THE LIBRARY PICKER ════════════════════════════════════
   CATALOG holds the SPECIFICATION LIBRARY (see _product_catalog_json).
   A pick is a spec, a variant (size) and a leg — supply or installation —
   and each leg becomes its own row with its own HSN/SAC on the server.
   Rows carry only what the browser owns: qty, price, show_price. Identity
   is re-read from the library at POST.
═══════════════════════════════════════════════════════════ */
function legLabel(leg) { return leg === 'supply' ? 'Supply' : 'Installation'; }

function rateOf(spec, vidx, leg) {
  var v = (spec.variants || [])[vidx];
  if (!v) return null;
  var r = (leg === 'supply') ? v.supply_rate : v.install_rate;
  return (r === null || r === undefined || r === '') ? null : r;
}

/* The size control follows the spec: one option per variant, or a single
   dash for an unsized clause (the library always carries exactly one
   variant then — spec._clean_variants() guarantees it). */
function onSpecPicked() {
  var specEl = document.getElementById('picker-spec');
  var varEl  = document.getElementById('picker-variant');
  var spec   = CATALOG[specEl ? specEl.value : ''];
  varEl.innerHTML = '';
  if (!spec) {
    varEl.disabled = true;
    varEl.innerHTML = '<option value="">&#8212;</option>';
    return;
  }
  var vs = spec.variants || [];
  var sized = vs.length > 1 || (vs.length === 1 && vs[0].label);
  if (!sized) {
    varEl.disabled = true;
    varEl.innerHTML = '<option value="0">' + (vs.length ? escHtml(vs[0].unit || '') : '') + '</option>';
    return;
  }
  varEl.disabled = false;
  vs.forEach(function(v, i) {
    var opt = document.createElement('option');
    opt.value = String(i);
    opt.textContent = (v.label || ('variant ' + (i + 1))) + (v.unit ? '  (' + v.unit + ')' : '');
    varEl.appendChild(opt);
  });
}

function addProduct() {
  var errEl  = document.getElementById('add-error');
  errEl.style.display = 'none';

  var specEl = document.getElementById('picker-spec');
  var varEl  = document.getElementById('picker-variant');
  var legEl  = document.getElementById('picker-leg');
  var qtyEl  = document.getElementById('picker-qty');
  var sid    = specEl ? specEl.value : '';

  if (!sid) {
    errEl.textContent = 'Please pick a specification.';
    errEl.style.display = 'block'; return;
  }
  var spec = CATALOG[sid];
  if (!spec) {
    errEl.textContent = 'Specification not found in the library — try refreshing the page.';
    errEl.style.display = 'block'; return;
  }
  var qty = parseFloat(qtyEl ? qtyEl.value : '1');
  if (!qty || qty <= 0) {
    errEl.textContent = 'Quantity must be greater than zero.';
    errEl.style.display = 'block'; return;
  }
  var vidx = parseInt(varEl && varEl.value !== '' ? varEl.value : '0', 10) || 0;
  if (!(spec.variants || [])[vidx]) {
    errEl.textContent = 'Pick a size.';
    errEl.style.display = 'block'; return;
  }
  var want = legEl ? legEl.value : 'both';
  var legs = (want === 'both') ? ['supply', 'install'] : [want];

  /* "Supply + Installation" adds one row per leg the library has a rate
     for. A leg with no library rate is added only when asked for by name,
     and then its price box opens EMPTY — never 0 — so a figure nobody
     chose cannot reach the document. The server refuses an empty price on
     a shown line. */
  var added = 0;
  legs.forEach(function(leg) {
    var rate = rateOf(spec, vidx, leg);
    if (want === 'both' && rate === null) return;
    SEL.push({
      rid:        ++_rid,
      sid:        sid,
      vidx:       vidx,
      leg:        leg,
      name:       spec.title,
      part_no:    spec.code,
      unit:       (spec.variants[vidx].unit || ''),
      label:      (spec.variants[vidx].label || ''),
      qty:        qty,
      price:      (rate === null ? '' : rate),
      show_price: true
    });
    added++;
  });
  if (!added) {
    errEl.textContent = 'The library has no supply or installation rate for that size. '
      + 'Choose "Supply only" or "Installation only" and type a price.';
    errEl.style.display = 'block'; return;
  }

  specEl.value = '';
  onSpecPicked();
  qtyEl.value = '1';
  render();
}"""

PICKER_RENDER_JS = """function renderRoot(item, idx) {
  /* The leg badge reuses `.badge-asm` — the one badge style QUOTATION_STYLES
     carries — because that sheet is frozen and this page may not add CSS. */
  var badge = '<span class="badge-asm">' + legLabel(item.leg) + '</span>';
  var spec  = CATALOG[item.sid] || {};
  var code  = spec.code || item.part_no || '';
  var hsn   = (item.leg === 'supply') ? (spec.supply_hsn || '') : (spec.install_sac || '');
  var codeLine = escHtml(code)
    + (item.unit ? ' &nbsp;|&nbsp; ' + escHtml(item.unit) : '')
    + (hsn ? ' &nbsp;|&nbsp; ' + (item.leg === 'supply' ? 'HSN ' : 'SAC ') + escHtml(hsn) : '');
  var priceVal = (item.price === null || item.price === undefined) ? '' : item.price;
  var priceHint = (priceVal === '') ? ' placeholder="no library rate"' : '';

  /* Use data-* attributes for field names — avoids all quote-escaping issues */
  return '<div class="sel-root" id="root-' + item.rid + '">'
    + '<div class="sel-root-head">'
    +   '<div class="sel-root-info">'
    +     '<div class="sel-name">' + escHtml(item.name)
    +       (item.label ? ' &mdash; ' + escHtml(item.label) : '') + badge + '</div>'
    +     '<div class="sel-pno">'  + codeLine + '</div>'
    +   '</div>'
    +   '<div class="sel-root-ctrl">'
    +     ctrlBlock('Qty',
          '<input type="number" class="ctrl-input w-qty"'
          + ' data-sel="' + idx + '" data-field="qty"'
          + ' value="' + item.qty + '" min="0.001" step="any"'
          + ' onchange="onRootFieldChange(this)"/>')
    +     ctrlBlock('Price (&#8377;)',
          '<input type="number" class="ctrl-input w-price"'
          + ' data-sel="' + idx + '" data-field="price"'
          + ' value="' + priceVal + '" min="0" step="any"' + priceHint
          + ' onchange="onRootFieldChange(this)"/>')
    +     ctrlBlock('Show Price',
          '<input type="checkbox" class="ctrl-check"'
          + ' data-sel="' + idx + '" data-field="show_price"'
          + (item.show_price ? ' checked' : '')
          + ' onchange="onRootFieldChange(this)"/>')
    +     '<button type="button" class="btn-rm" onclick="removeRoot(' + idx + ')">&#215;</button>'
    +   '</div>'
    + '</div>'
    + '</div>';
}"""

PICKER_MUTATION_JS = """/* ═══ FIELD-CHANGE DISPATCHER (reads data-* — no string quoting needed) ═ */
function onRootFieldChange(el) {
  var idx   = parseInt(el.dataset.sel, 10);
  var field = el.dataset.field;
  var val   = (el.type === 'checkbox') ? el.checked : el.value;
  onRootChange(idx, field, val);
}

/* ═══ MUTATIONS ═════════════════════════════════════════════ */
function onRootChange(idx, field, val) {
  if (field === 'qty')        SEL[idx].qty        = parseFloat(val) || 1;
  /* An emptied price box stays EMPTY — it is not zero. A typed 0 is kept
     as 0: that is a price somebody chose. */
  else if (field === 'price') SEL[idx].price      = (String(val).trim() === '') ? '' : (parseFloat(val) || 0);
  else if (field === 'show_price') SEL[idx].show_price = val;
  saveJSON();
}

function removeRoot(idx) { SEL.splice(idx, 1); render(); }"""

DEMO_PICK_JS = """  /* One clause from the library, both legs — the first spec whose first
     variant carries a supply AND an installation rate, so the demo shows a
     priced row of each kind. Nothing is invented: if the library has no
     such clause, nothing is added and the picker says so. */
  var demoSid = null;
  var keys = Object.keys(CATALOG);
  for (var i = 0; i < keys.length; i++) {
    if (rateOf(CATALOG[keys[i]], 0, 'supply') !== null
        && rateOf(CATALOG[keys[i]], 0, 'install') !== null) { demoSid = keys[i]; break; }
  }

  if (demoSid) {
    /* Don't add duplicate */
    var already = SEL.some(function(s) { return s.sid === demoSid; });
    if (!already) {
      var spec = CATALOG[demoSid];
      ['supply', 'install'].forEach(function(leg) {
        SEL.push({
          rid:        ++_rid,
          sid:        demoSid,
          vidx:       0,
          leg:        leg,
          name:       spec.title,
          part_no:    spec.code,
          unit:       (spec.variants[0].unit || ''),
          label:      (spec.variants[0].label || ''),
          qty:        2,
          price:      rateOf(spec, 0, leg),
          show_price: true
        });
      });
      render();
    }
  } else {
    var ae = document.getElementById('add-error');
    ae.textContent = 'The specification library has no clause with both rates — add one at /spec first.';
    ae.style.display = 'block';
  }"""

# The eight seams, by name. `quotation.create_quotation()` fills the same
# eight in the product mode from the `1d7725a` text it holds; a key added
# here without a placeholder in the template is a silent no-op, and a
# placeholder added there without a key here is a KeyError at render — so
# `tests/test_quotation_switch.py` asserts the two sets are equal.
SEAMS = ("picker_section", "catalog_load_error", "restore_component_rids",
         "picker_add_js", "picker_render_js", "picker_mutation_js",
         "demo_pick_js", "submit_empty_message")


def page_pieces(specs: dict) -> dict:
    """The eight fills for the library mode, ready for `page.format(**pieces)`."""
    return {
        "picker_section":         SECTION_HTML.replace("{spec_opts}", spec_options_html(specs)),
        "catalog_load_error":     CATALOG_LOAD_ERROR,
        "restore_component_rids": RESTORE_COMPONENT_RIDS_JS,
        "picker_add_js":          PICKER_ADD_JS,
        "picker_render_js":       PICKER_RENDER_JS,
        "picker_mutation_js":     PICKER_MUTATION_JS,
        "demo_pick_js":           DEMO_PICK_JS,
        "submit_empty_message":   SUBMIT_EMPTY_MESSAGE,
    }
