"""
spec.py — Specification Library
================================
The vocabulary a BOQ is written in. **This is not `product.py` and it does not
replace it.**

`product.py` serves the quotation → proforma → tax invoice chain, which is live
business. The two modules describe genuinely different things:

| | `product.py` | `spec.py` |
|---|---|---|
| an entry is | a thing we sell | a clause of work |
| priced by | one `base_price` | a supply rate **and** an installation rate |
| composed of | `children` — a bill of materials | `variants` — the same clause at several sizes |

THE VARIANT MODEL IS THE POINT
-------------------------------
The client's BOQ item 24 is one paragraph of specification, and 24.a–24.i are
that same clause at 200/150/100/80/65/50/40/32/25 mm, each with its own rate
and unit. `product.children` is a bill of materials — "this pump set contains
one motor and one base frame" — and cannot express "this clause comes in nine
sizes". So a spec carries `variants`, and picking spec + variant fills a whole
BOQ child row.

`variants` is **always a list and never null.** An unsized item — a flow
switch, a liaisoning charge — carries exactly one variant with an empty label
and no dimension, so every consumer has one code path instead of two. That is
enforced at save (`_clean_variants`), not left to the caller.

What the rates here are, and are not
-------------------------------------
`default_supply_base_rate` / `default_install_base_rate` are **defaults, and
only ever suggested**. They fill an empty box on the BOQ form and never
overwrite a typed one — `purchase.fillRate()`'s precedent, for the same reason:
the project's own rate basis is the truth and this is a starting point. The BOQ
stores what was entered (handover §4.2 rule 4).

**Escalation percentages deliberately do not live here.** An escalation belongs
to a project — it is the gap between a rate contract agreed elsewhere and what
this job is priced at — and putting it on the library would make one project's
negotiation look like a property of the material.

`spec_text` becomes the BOQ line's description and is **copied, not
referenced**: editing it on the BOQ must not write back here, and editing it
here must not reach a BOQ already issued. That is the same freeze every other
document in this app relies on, which is also why a line item carries no
`spec_id` — see `delete_spec()`.

Import direction: spec.py imports `dashboard`, `branding`, `store`, `pipeline`
and `demo_data`, none of which import anything from the app. `boq.py` imports
**this** module; this module must never import `boq.py`.
"""

import uuid

from flask import Blueprint, redirect, render_template_string, request, url_for

import branding as B
import demo_data as DD
import pipeline as P
from dashboard import BASE_STYLES, _nav
from store import STORE

spec_bp = Blueprint("spec", __name__, url_prefix="/spec")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

# Edit these and the add form, the edit form and the register filter all
# regenerate. "Other" is last and is the fallback for anything unclassified.
CATEGORIES = ["Piping", "Valves", "Sprinklers", "Hydrant", "Pumps", "Panels",
              "Civil", "Other"]

DEFAULT_CATEGORY = "Other"
DEFAULT_GST_RATE = 18.0

# Units a BOQ line is actually measured in. Shorter than the catalogue's list
# because a schedule of work measures length, count, weight and lump sums.
UNITS = ["Nos", "Nos.", "Mtrs", "Mtrs.", "Kgs.", "Set", "Lot", "Lump Sum",
         "Sq.Mtrs", "Ltrs", "Job"]

# The blank rows an empty variant editor opens with.
NEW_VARIANT_ROWS = 3

# Shown on the register and on every spec page. The seeded rates are one
# project's negotiated figures, not a price list, and a library that does not
# say so invites somebody to quote them at a different customer.
REFERENCE_NOTE = (
    "Rates in this library are <b>reference defaults</b>, not a price list. The "
    "seeded figures are the rates agreed on one project (Sify Bangalore, priced "
    "off a rate contract from another site and escalated per line). They only "
    "ever suggest a starting point into an empty box on a BOQ — the project's "
    "own rate basis is what governs."
)


# =============================================================================
# HELPERS
# =============================================================================

def _valid_code(code: str) -> bool:
    """Shape only: something typeable, no spaces, not absurdly long."""
    code = (code or "").strip()
    return bool(code) and " " not in code and len(code) <= 48


def _valid_tax_code(code: str) -> bool:
    """
    Is this a well-formed HSN (goods) or SAC (services) code?

    Digits only, and 4, 6 or 8 of them — the three lengths GST issues. How many
    are *required* depends on the supplier's turnover, which this app does not
    know, so the rule is shape-only: reject a typo, never dictate a length.

    ⚠ This duplicates `product._valid_hsn()` deliberately. `spec.py` may not
    import `product.py` (it is not in this module's import direction), and the
    shared home for a helper both need is `pipeline.py` — but moving it there
    means editing `product.py`, which is frozen while the quotation chain is
    live. Fold the two together the next time that file is open.
    """
    code = (code or "").strip()
    return code.isdigit() and len(code) in (4, 6, 8)


def _num(raw, default=0.0):
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
    """A rate that is allowed to be absent. Blank or "-" is None, not zero."""
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


def spec_by_code(code: str):
    for s in STORE["specs"].values():
        if s.get("code") == code:
            return s
    return None


def variant_of(spec: dict, label: str):
    """The named variant, or the only one when a spec is unsized."""
    variants = spec.get("variants") or []
    for v in variants:
        if v.get("label") == label:
            return v
    return variants[0] if len(variants) == 1 else None


def rate_range(spec: dict) -> tuple:
    """(low, high) supply base rate across the variants — for the register."""
    rates = [v.get("default_supply_base_rate") for v in (spec.get("variants") or [])]
    rates = [r for r in rates if r]
    if not rates:
        return (None, None)
    return (min(rates), max(rates))


# =============================================================================
# SEED
# =============================================================================

def ensure_demo_specs() -> None:
    """
    Seed the library on first call; a no-op afterwards.

    Called at the top of every route that reads `STORE["specs"]`, and from
    `boq.ensure_demo_boq()`, so the picker is never empty on a fresh install.
    Guarded by `STORE["_spec_seeded"]`, which is deliberately **not persisted**
    — emptying the table refills it, which is what makes "drop the database and
    restart" a working demo reset.

    Rows carry fixed UUIDs (`demo_data.SPECS`), so re-running never duplicates
    one and an existing row is left exactly as the user edited it.

    ⚠ The rates are one project's figures, not a price list — see
      `REFERENCE_NOTE` and demo_data.py's own header. The HSN and SAC codes are
      plausible placeholders, not a classification anybody's CA has signed off.
    """
    if STORE.get("_spec_seeded"):
        return

    for row in DD.SPECS:
        sid = row["id"]
        if sid in STORE["specs"]:
            continue
        # A deep-ish copy: the variant dicts must not be shared with the module
        # constant, or editing a seeded spec would mutate demo_data in memory
        # and every later reseed would carry the edit.
        STORE["specs"][sid] = {
            **{k: v for k, v in row.items() if k != "variants"},
            "variants": [dict(v) for v in row["variants"]],
        }

    STORE["_spec_seeded"] = True


# =============================================================================
# STYLES
# =============================================================================
#
# A plain string, not an f-string, so its braces are written once. Layered
# after BASE_STYLES. This module cannot import `PRODUCT_STYLES` (product.py is
# not in its import direction), so the handful of form rules it needs are
# declared here rather than borrowed.
# =============================================================================

SPEC_STYLES = """
<style>
  .page-top {
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:1.75rem; flex-wrap:wrap; gap:1rem;
  }
  .page-top h1 { font-size:1.5rem; font-weight:700; letter-spacing:-.4px; }
  .page-top h1 span { color:var(--brand); }

  .alert {
    padding:.8rem 1.1rem; border-radius:8px; font-size:.87rem;
    font-weight:500; margin-bottom:1.4rem;
    display:flex; align-items:center; gap:.5rem;
  }
  .alert-error   { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
  .alert-success { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }

  /* The standing reference-data note. Amber and always present: it is not a
     warning about a fault, it is a statement about what these numbers are. */
  .ref-note {
    background:#fffbeb; border:1px solid #fde68a; border-radius:8px;
    padding:.7rem 1rem; font-size:.8rem; color:#78350f;
    margin-bottom:1.4rem; line-height:1.5;
  }
  .ref-note b { font-weight:700; }

  .table-wrap {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow-sm);
  }
  table { width:100%; border-collapse:collapse; font-size:.88rem; }
  thead { background:var(--bg); border-bottom:1px solid var(--border); }
  th {
    padding:.8rem 1.1rem; text-align:left; font-size:.73rem;
    font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
  }
  td { padding:.9rem 1.1rem; border-bottom:1px solid var(--border); vertical-align:middle; }
  tbody tr:last-child td { border-bottom:none; }
  tbody tr:hover { background:#f8fafc; }
  .td-code  { font-family:'SFMono-Regular',Consolas,monospace; font-weight:700;
              color:var(--brand); font-size:.8rem; }
  .td-title { font-weight:600; }
  .td-muted { font-size:.82rem; color:var(--muted); }

  .cat-badge {
    display:inline-block; font-size:.68rem; font-weight:700; letter-spacing:.05em;
    text-transform:uppercase; padding:.2rem .55rem; border-radius:999px;
    background:var(--brand-lt); color:var(--navy); border:1px solid #c7d2fe;
  }
  .var-count {
    display:inline-block; font-size:.72rem; font-weight:700;
    padding:.15rem .5rem; border-radius:6px; background:#f1f5f9; color:#475569;
  }
  .var-count.unsized { background:#f8fafc; color:#94a3b8; font-weight:500; }

  .btn-view {
    font-size:.75rem; font-weight:600; color:var(--brand); background:var(--brand-lt);
    border:1px solid #c7d2fe; border-radius:6px; padding:.28rem .7rem;
    text-decoration:none; display:inline-block;
  }
  .btn-view:hover { background:#c7d2fe; }
  .btn-danger {
    font-size:.75rem; font-weight:600; color:#991b1b; background:#fef2f2;
    border:1px solid #fecaca; border-radius:6px; padding:.28rem .7rem;
    text-decoration:none; display:inline-block; cursor:pointer;
  }
  .btn-danger:hover { background:#fee2e2; }

  .empty-state {
    text-align:center; padding:3.5rem 2rem; color:var(--muted);
    background:var(--surface); border:1px dashed var(--border); border-radius:var(--radius);
  }

  .filter-bar {
    display:flex; gap:.8rem; align-items:center; flex-wrap:wrap;
    margin-bottom:1.2rem;
  }
  .filter-tab {
    font-size:.78rem; font-weight:600; padding:.4rem .85rem; border-radius:999px;
    border:1px solid var(--border); background:var(--surface); color:var(--muted);
    text-decoration:none; cursor:pointer;
  }
  .filter-tab.active { background:var(--brand); color:#fff; border-color:var(--brand); }

  /* ── Forms ────────────────────────────────────────────────────────── */
  .form-section {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.6rem 1.9rem;
    box-shadow:var(--shadow-sm); margin-bottom:1.4rem;
  }
  .section-title {
    font-size:.73rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.09em; color:var(--brand); margin-bottom:1.2rem;
    display:flex; align-items:center; gap:.4rem;
    padding-bottom:.6rem; border-bottom:1px solid var(--border);
  }
  .fg2 { display:grid; grid-template-columns:1fr 1fr;         gap:.9rem; }
  .fg3 { display:grid; grid-template-columns:1fr 1fr 1fr;     gap:.9rem; }
  .fg4 { display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:.9rem; }
  .span-all { grid-column:1/-1; }
  .form-group { display:flex; flex-direction:column; gap:.3rem; }
  label {
    font-size:.72rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.07em; color:var(--muted);
  }
  input[type="text"], input[type="number"], textarea, select {
    font-family:var(--font); font-size:.88rem; color:var(--text);
    background:var(--bg); border:1.5px solid var(--border);
    border-radius:7px; padding:.52rem .8rem; width:100%;
    transition:border-color .14s, box-shadow .14s; outline:none;
  }
  input:focus, textarea:focus, select:focus {
    border-color:var(--brand); box-shadow:0 0 0 3px rgba(79,70,229,.1); background:#fff;
  }
  textarea { resize:vertical; min-height:180px; line-height:1.55; }

  /* ── Variant editor ───────────────────────────────────────────────── */
  .var-row {
    display:grid; grid-template-columns:2.2fr .7fr .7fr 1fr 1fr 1fr 34px;
    gap:.6rem; align-items:end; margin-bottom:.6rem;
  }
  .var-head {
    display:grid; grid-template-columns:2.2fr .7fr .7fr 1fr 1fr 1fr 34px;
    gap:.6rem; margin-bottom:.4rem;
  }
  .var-head span {
    font-size:.68rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.06em; color:var(--muted);
  }
  .btn-row {
    font-size:.75rem; font-weight:600; color:var(--brand);
    background:var(--brand-lt); border:1px solid #c7d2fe; border-radius:6px;
    padding:.35rem .8rem; cursor:pointer;
  }
  .btn-row:hover { background:#c7d2fe; }
  .btn-del {
    font-size:.75rem; font-weight:700; color:#991b1b; background:#fef2f2;
    border:1px solid #fecaca; border-radius:6px; padding:.35rem .55rem; cursor:pointer;
  }
  .btn-del:hover { background:#fee2e2; }

  /* ── View page ────────────────────────────────────────────────────── */
  .spec-head {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.5rem 1.8rem;
    box-shadow:var(--shadow-sm); margin-bottom:1.4rem;
  }
  .sh-code { font-family:'SFMono-Regular',Consolas,monospace; font-size:.8rem;
             font-weight:700; color:var(--brand); }
  .sh-title { font-size:1.25rem; font-weight:700; margin:.3rem 0 .6rem; }
  .sh-meta { display:flex; gap:1.6rem; flex-wrap:wrap; margin-top:1rem;
             padding-top:1rem; border-top:1px solid var(--border); }
  .sh-cell { min-width:0; }
  .sh-lbl { font-size:.68rem; font-weight:700; text-transform:uppercase;
            letter-spacing:.06em; color:var(--muted); }
  .sh-val { font-size:.95rem; font-weight:700; margin-top:.15rem; }
  .spec-text {
    white-space:pre-wrap; line-height:1.6; font-size:.87rem;
    background:var(--bg); border:1px solid var(--border);
    border-radius:8px; padding:1rem 1.2rem;
  }
  .unsized-note { font-size:.8rem; color:var(--muted); font-style:italic; }

  @media (max-width:760px) {
    .var-row, .var-head { grid-template-columns:1fr 1fr; }
    .var-head { display:none; }
    .fg2, .fg3, .fg4 { grid-template-columns:1fr; }
  }
</style>
"""


_VARIANT_JS = """
<script>
/* The variant editor — the repeating-row pattern from product.py's BOM child
   editor, not a client-side model. A variant is six flat fields and does not
   need one. Rows post as parallel lists and blank rows are dropped on save. */
function addVariantRow() {
  var box = document.getElementById('var-rows');
  var row = document.createElement('div');
  row.className = 'var-row';
  row.innerHTML = VARIANT_ROW_HTML;
  box.appendChild(row);
}

function delVariantRow(btn) {
  var box = document.getElementById('var-rows');
  var row = btn.closest('.var-row');
  if (box.querySelectorAll('.var-row').length > 1) {
    row.remove();
  } else {
    /* Never leave the editor with nothing in it — an empty list becomes a
       single unsized variant at save anyway, so show that shape. */
    row.querySelectorAll('input').forEach(function (i) { i.value = ''; });
  }
}

function confirmDelete(url, title) {
  if (window.confirm('Delete "' + title + '" from the library?\\n\\nBOQs already '
      + 'written from it are unaffected \\u2014 they carry their own copy of the text.')) {
    window.location.href = url;
  }
  return false;
}
</script>
"""


# =============================================================================
# FORM — validation
# =============================================================================

def _clean_variants(form) -> list:
    """
    The posted variant rows, as §4.2's variant list.

    Blank rows are dropped silently — the editor opens with three and an
    untouched one is not a mistake (`purchase._parse_lines()` makes the same
    call about its three opening rows).

    **Rule 1 is enforced here.** An empty list becomes exactly one variant with
    an empty label and no dimension, so an unsized item — a flow switch, a
    liaisoning charge — is one code path with everything else rather than a
    special case every consumer has to remember.
    """
    labels     = form.getlist("var_label")
    dimensions = form.getlist("var_dimension")
    dim_units  = form.getlist("var_dim_unit")
    units      = form.getlist("var_unit")
    supplies   = form.getlist("var_supply")
    installs   = form.getlist("var_install")

    n = max(len(labels), len(dimensions), len(dim_units),
            len(units), len(supplies), len(installs), 0)

    def at(seq, i):
        return seq[i] if i < len(seq) else ""

    out = []
    for i in range(n):
        label = at(labels, i).strip()
        dim   = at(dimensions, i).strip()
        unit  = at(units, i).strip()
        sup   = _opt_num(at(supplies, i))
        ins   = _opt_num(at(installs, i))
        if not any([label, dim, unit, sup is not None, ins is not None]):
            continue
        out.append({
            "label":     label,
            "dimension": dim or None,
            "dim_unit":  at(dim_units, i).strip(),
            "unit":      unit,
            "default_supply_base_rate":  sup,
            "default_install_base_rate": ins,
        })

    if not out:
        # An unsized item still carries exactly ONE variant. Never null, never
        # an empty list.
        out = [{"label": "", "dimension": None, "dim_unit": "", "unit": "",
                "default_supply_base_rate": None,
                "default_install_base_rate": None}]
    return out


def _validate(form, spec_id: str = None) -> tuple:
    """
    (data, error) — and it **always returns data**, so a rejected form
    re-renders with the user's input intact rather than throwing away a
    1500-character clause because a code was mistyped. `address._validate()`
    established this contract; it is the one module in this repo that already
    does edit properly.
    """
    data = {
        "code":       (form.get("code") or "").strip(),
        "title":      (form.get("title") or "").strip(),
        "spec_text":  (form.get("spec_text") or "").strip(),
        "category":   (form.get("category") or DEFAULT_CATEGORY).strip(),
        "supply_hsn": (form.get("supply_hsn") or "").strip(),
        "install_sac": (form.get("install_sac") or "").strip(),
        "supply_gst_rate":  _num(form.get("supply_gst_rate"), DEFAULT_GST_RATE),
        "install_gst_rate": _num(form.get("install_gst_rate"), DEFAULT_GST_RATE),
        "variants":   _clean_variants(form),
    }

    # Validation, in order.
    if not data["code"]:
        return data, "A spec needs a code."
    if not _valid_code(data["code"]):
        return data, "The code must have no spaces and be 48 characters or fewer."

    clash = spec_by_code(data["code"])
    if clash and clash.get("id") != spec_id:
        return data, f"The code &quot;{P.esc(data['code'])}&quot; is already used by another spec."

    if not data["title"]:
        return data, "A spec needs a short title — it is what the BOQ picker shows."
    if not data["spec_text"]:
        return data, "A spec needs its clause text; it becomes the BOQ line description."
    if data["category"] not in CATEGORIES:
        return data, "Choose a category from the list."

    if data["supply_hsn"] and not _valid_tax_code(data["supply_hsn"]):
        return data, "HSN must be 4, 6 or 8 digits."
    if data["install_sac"] and not _valid_tax_code(data["install_sac"]):
        return data, "SAC must be 4, 6 or 8 digits."

    for v in data["variants"]:
        for key, what in (("default_supply_base_rate", "supply"),
                          ("default_install_base_rate", "installation")):
            if v[key] is not None and v[key] < 0:
                label = v["label"] or "the unsized variant"
                return data, f"A negative {what} rate on {P.esc(label)}."

    # More than one variant means they are being told apart by something, and a
    # blank label in that set cannot be picked from a dropdown.
    if len(data["variants"]) > 1:
        seen = set()
        for v in data["variants"]:
            if not v["label"]:
                return data, "With more than one variant, every variant needs a label."
            if v["label"] in seen:
                return data, f"Two variants are both labelled &quot;{P.esc(v['label'])}&quot;."
            seen.add(v["label"])

    return data, ""


# =============================================================================
# FORM — rendering
# =============================================================================

def _js_string(s: str) -> str:
    """
    A Python string as a single-quoted JS literal.

    Used for the blank variant row the editor clones. json.dumps would also
    work, but it emits a double-quoted literal and this HTML is full of double
    quotes — one escaping style beats two.
    """
    out = s.replace("\\", "\\\\")
    out = out.replace("'", "\\'")
    out = out.replace("\n", "\\n")
    out = out.replace("\r", "")
    return "'" + out + "'"


def _opts(name, options, current, placeholder: str = "") -> str:
    inner = f'<option value="">{placeholder}</option>' if placeholder else ""
    for o in options:
        sel = " selected" if o == current else ""
        inner += f'<option value="{P.esc(o)}"{sel}>{P.esc(o)}</option>'
    return f'<select id="{name}" name="{name}">{inner}</select>'


def _variant_row(v: dict = None) -> str:
    v = v or {}
    unit_opts = ""
    for u in UNITS:
        sel = " selected" if u == (v.get("unit") or "") else ""
        unit_opts += f'<option{sel}>{P.esc(u)}</option>'

    def val(key):
        x = v.get(key)
        return "" if x is None else P.esc(x)

    return (
        '<div class="var-row">'
        f'<input type="text" name="var_label" value="{val("label")}" placeholder="150mm dia ISI"/>'
        f'<input type="text" name="var_dimension" value="{val("dimension")}" placeholder="150"/>'
        f'<input type="text" name="var_dim_unit" value="{val("dim_unit")}" placeholder="mm"/>'
        f'<select name="var_unit"><option value=""></option>{unit_opts}</select>'
        f'<input type="text" name="var_supply" value="{val("default_supply_base_rate")}" placeholder="1760"/>'
        f'<input type="text" name="var_install" value="{val("default_install_base_rate")}" placeholder="1200"/>'
        '<button type="button" class="btn-del" onclick="delVariantRow(this)">&#10007;</button>'
        '</div>'
    )


def _render_form(data: dict, error: str, mode: str, spec_id: str = "") -> str:
    """
    One renderer for both add and edit — they differ by their action URL and
    their title, and nothing else. Forking them is how the two drift apart and
    one quietly stops validating something.
    """
    is_edit  = mode == "edit"
    action   = (url_for("spec.edit_spec", id=spec_id) if is_edit
                else url_for("spec.add_spec"))
    heading  = "Edit <span>Spec</span>" if is_edit else "Add <span>Spec</span>"

    variants = data.get("variants") or []
    if not is_edit and len(variants) <= 1 and not (variants and variants[0].get("label")):
        # A fresh form opens with room to type a size family; an unsized item
        # simply leaves the extra rows blank and they are dropped on save.
        rows = "".join(_variant_row(variants[0] if variants else None)
                       for _ in range(1)) + \
               "".join(_variant_row() for _ in range(NEW_VARIANT_ROWS - 1))
    else:
        rows = "".join(_variant_row(v) for v in variants)

    alert_html = f'<div class="alert alert-error">&#10007; {error}</div>' if error else ""

    delete_html = ""
    if is_edit:
        del_url = url_for("spec.delete_spec", id=spec_id)
        delete_html = (
            f'<a class="btn-danger" href="#" '
            f'onclick="return confirmDelete(\'{del_url}\', \'{P.esc(data.get("title"))}\')">'
            f'Delete this spec</a>'
        )

    # The blank row the JS clones is built by the same function that renders a
    # filled one, so the "+ Add variant" row can never drift from the others.
    js = _VARIANT_JS.replace("VARIANT_ROW_HTML", _js_string(_variant_row()))

    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title("Edit Spec" if is_edit else "Add Spec")}</title>{B.HEAD_ICON}
  {BASE_STYLES}{SPEC_STYLES}
</head>
<body>{_nav()}
<main>
  {alert_html}
  <div class="page-top">
    <h1>{heading}</h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('spec.list_specs')}" class="btn btn-ghost">&#8592; Library</a>
    </div>
  </div>

  <div class="ref-note">{REFERENCE_NOTE}</div>

  <form method="POST" action="{action}">
    <div class="form-section">
      <div class="section-title">&#128209; Identity</div>
      <div class="fg3">
        <div class="form-group">
          <label for="code">Code</label>
          <input type="text" id="code" name="code" value="{P.esc(data.get('code'))}"
                 placeholder="PIPE-MS-C-1239" required
                 style="font-family:'SFMono-Regular',Consolas,monospace;"/>
        </div>
        <div class="form-group">
          <label for="category">Category</label>
          {_opts("category", CATEGORIES, data.get("category"))}
        </div>
        <div class="form-group">
          <label for="title">Short Title <span style="text-transform:none;font-weight:500;">(what the BOQ picker shows)</span></label>
          <input type="text" id="title" name="title" value="{P.esc(data.get('title'))}"
                 placeholder="MS 'C' class pipe, IS 1239, roll-grooved" required/>
        </div>
      </div>
      <div class="fg2" style="margin-top:.9rem;">
        <div class="form-group span-all">
          <label for="spec_text">Clause Text <span style="text-transform:none;font-weight:500;">(becomes the BOQ line description)</span></label>
          <textarea id="spec_text" name="spec_text" required
                    placeholder="Supply, Fabrication, Installation, Testing of ...">{P.esc(data.get('spec_text'))}</textarea>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">&#129534; Tax Classification</div>
      <div class="fg4">
        <div class="form-group">
          <label for="supply_hsn">HSN <span style="text-transform:none;font-weight:500;">(goods)</span></label>
          <input type="text" id="supply_hsn" name="supply_hsn"
                 value="{P.esc(data.get('supply_hsn'))}" placeholder="73063090"/>
        </div>
        <div class="form-group">
          <label for="supply_gst_rate">Supply GST %</label>
          <input type="text" id="supply_gst_rate" name="supply_gst_rate"
                 value="{data.get('supply_gst_rate', DEFAULT_GST_RATE):g}"/>
        </div>
        <div class="form-group">
          <label for="install_sac">SAC <span style="text-transform:none;font-weight:500;">(services)</span></label>
          <input type="text" id="install_sac" name="install_sac"
                 value="{P.esc(data.get('install_sac'))}" placeholder="995462"/>
        </div>
        <div class="form-group">
          <label for="install_gst_rate">Installation GST %</label>
          <input type="text" id="install_gst_rate" name="install_gst_rate"
                 value="{data.get('install_gst_rate', DEFAULT_GST_RATE):g}"/>
        </div>
      </div>
      <p style="margin-top:.7rem;font-size:.78rem;color:var(--muted);">
        Supply carries an <b>HSN</b> and installation a <b>SAC</b> — they are
        different supplies and are taxed separately. Both are optional here and
        both are wanted on the tax invoice the RA bill becomes.
      </p>
    </div>

    <div class="form-section">
      <div class="section-title">&#128207; Variants</div>
      <p style="margin-bottom:1rem;font-size:.82rem;color:var(--muted);">
        One row per size. Leave every row blank for an <b>unsized</b> item — it is
        stored as a single variant with no label, so there is one shape rather
        than two. Rates here are <b>suggestions</b> that fill an empty box on a
        BOQ and never overwrite a typed one.
      </p>
      <div class="var-head">
        <span>Label</span><span>Dim.</span><span>Unit</span><span>Measured In</span>
        <span>Supply Base</span><span>Install Base</span><span></span>
      </div>
      <div id="var-rows">{rows}</div>
      <button type="button" class="btn-row" style="margin-top:.5rem;" onclick="addVariantRow()">
        + Add variant
      </button>
    </div>

    <div style="display:flex;gap:.8rem;justify-content:space-between;margin-bottom:2rem;">
      <div>{delete_html}</div>
      <div style="display:flex;gap:.8rem;">
        <a href="{url_for('spec.list_specs')}" class="btn btn-ghost">Cancel</a>
        <button type="submit" class="btn">{"Save Changes" if is_edit else "Add Spec"}</button>
      </div>
    </div>
  </form>

  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · specification library</p></footer>
</main>
{js}
</body></html>"""


def _js_string(s: str) -> str:
    """A Python string as a single-quoted JS literal."""
    return "'" + (s.replace("\\", "\\\\").replace("'", "\\'")
                   .replace("\n", "\\n").replace("\r", "")) + "'"


# =============================================================================
# ROUTES
# =============================================================================

@spec_bp.route("/")
def list_specs():
    ensure_demo_specs()

    msg      = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {P.esc(msg)}</div>'

    cur_cat = (request.args.get("cat") or "").strip()
    query   = (request.args.get("q") or "").strip().lower()

    rows = []
    for sid, s in STORE["specs"].items():
        if cur_cat and s.get("category") != cur_cat:
            continue
        if query:
            hay = " ".join([str(s.get("code") or ""), str(s.get("title") or ""),
                            str(s.get("spec_text") or "")]).lower()
            if query not in hay:
                continue
        rows.append((sid, s))
    rows.sort(key=lambda kv: (kv[1].get("category", ""), kv[1].get("code", "")))

    counts = {}
    for s in STORE["specs"].values():
        counts[s.get("category", DEFAULT_CATEGORY)] = counts.get(s.get("category", DEFAULT_CATEGORY), 0) + 1

    tabs = f'<a href="{url_for("spec.list_specs")}" class="filter-tab{"" if cur_cat else " active"}">All ({len(STORE["specs"])})</a>'
    for c in CATEGORIES:
        n = counts.get(c, 0)
        if not n:
            continue
        active = " active" if c == cur_cat else ""
        tabs += (f'<a href="{url_for("spec.list_specs", cat=c)}" '
                 f'class="filter-tab{active}">{P.esc(c)} ({n})</a>')

    if rows:
        body = ""
        for sid, s in rows:
            variants = s.get("variants") or []
            unsized  = len(variants) == 1 and not variants[0].get("label")
            vcount   = ('<span class="var-count unsized">unsized</span>' if unsized
                        else f'<span class="var-count">{len(variants)} sizes</span>')
            lo, hi = rate_range(s)
            if lo is None:
                rate_txt = "&mdash;"
            elif lo == hi:
                rate_txt = f"&#8377;&nbsp;{lo:,.0f}"
            else:
                rate_txt = f"&#8377;&nbsp;{lo:,.0f} &ndash; {hi:,.0f}"
            body += f"""
            <tr>
              <td class="td-code">{P.esc(s.get('code'))}</td>
              <td class="td-title">{P.esc(s.get('title'))}</td>
              <td><span class="cat-badge">{P.esc(s.get('category'))}</span></td>
              <td>{vcount}</td>
              <td class="td-muted">{rate_txt}</td>
              <td class="td-muted">{P.esc(s.get('supply_hsn') or '&mdash;')} / {P.esc(s.get('install_sac') or '&mdash;')}</td>
              <td style="display:flex;gap:.4rem;">
                <a href="{url_for('spec.view_spec', id=sid)}" class="btn-view">&#128269; View</a>
                <a href="{url_for('spec.edit_spec', id=sid)}" class="btn-view">&#9998; Edit</a>
              </td>
            </tr>"""
        table = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Code</th><th>Title</th><th>Category</th><th>Variants</th>
            <th>Supply Base Rate</th><th>HSN / SAC</th><th></th>
          </tr></thead>
          <tbody>{body}</tbody>
        </table></div>"""
    elif STORE["specs"]:
        table = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128269;</div><br>
          <strong>No specs match that filter</strong>
          <a href="{url_for('spec.list_specs')}" class="btn"
             style="display:inline-block;margin-top:1.1rem;">Show all</a>
        </div>"""
    else:
        table = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128209;</div><br>
          <strong>The library is empty</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">
            A spec is a clause of work with its sized variants. It is what a BOQ
            line is written from.
          </p>
          <a href="{url_for('spec.add_spec')}" class="btn"
             style="display:inline-block;margin-top:1.1rem;">+ Add Spec</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Specification Library")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{SPEC_STYLES}</head>
    <body>{_nav()}
    <main>
      {alert_html}
      <div class="page-top">
        <h1>Specification <span>Library</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            showing {len(rows)} of {len(STORE["specs"])}
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{url_for('dashboard.index')}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{url_for('spec.add_spec')}" class="btn">+ Add Spec</a>
        </div>
      </div>
      <div class="ref-note">{REFERENCE_NOTE}</div>
      <div class="filter-bar">
        {tabs}
        <form method="GET" action="{url_for('spec.list_specs')}" style="display:flex;gap:.5rem;margin-left:auto;">
          {f'<input type="hidden" name="cat" value="{P.esc(cur_cat)}"/>' if cur_cat else ''}
          <input type="search" name="q" value="{P.esc(query)}" placeholder="code, title or clause text"/>
          <button type="submit" class="filter-tab">Search</button>
        </form>
      </div>
      {table}
      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · specification library</p></footer>
    </main></body></html>"""
    return render_template_string(template)


@spec_bp.route("/view/<id>")
def view_spec(id: str):
    ensure_demo_specs()
    s = STORE["specs"].get(id)
    if not s:
        return redirect(url_for("spec.list_specs", msg="Spec not found.", type="error"))

    variants = s.get("variants") or []
    unsized  = len(variants) == 1 and not variants[0].get("label")

    if unsized:
        v = variants[0]
        sup = v.get("default_supply_base_rate")
        ins = v.get("default_install_base_rate")
        var_html = f"""
        <p class="unsized-note">This is an unsized item — one variant, no dimension.</p>
        <div class="table-wrap" style="margin-top:.6rem;"><table>
          <thead><tr><th>Measured In</th><th>Supply Base Rate</th><th>Installation Base Rate</th></tr></thead>
          <tbody><tr>
            <td>{P.esc(v.get('unit') or '&mdash;')}</td>
            <td>{'&#8377;&nbsp;' + format(sup, ',.2f') if sup is not None else '&mdash;'}</td>
            <td>{'&#8377;&nbsp;' + format(ins, ',.2f') if ins is not None else '&mdash;'}</td>
          </tr></tbody>
        </table></div>"""
    else:
        body = ""
        for v in variants:
            sup = v.get("default_supply_base_rate")
            ins = v.get("default_install_base_rate")
            dim = v.get("dimension")
            body += f"""
            <tr>
              <td class="td-title">{P.esc(v.get('label'))}</td>
              <td class="td-muted">{P.esc(dim) + ' ' + P.esc(v.get('dim_unit') or '') if dim else '&mdash;'}</td>
              <td>{P.esc(v.get('unit') or '&mdash;')}</td>
              <td>{'&#8377;&nbsp;' + format(sup, ',.2f') if sup is not None else '&mdash;'}</td>
              <td>{'&#8377;&nbsp;' + format(ins, ',.2f') if ins is not None else '&mdash;'}</td>
            </tr>"""
        var_html = f"""
        <div class="table-wrap"><table>
          <thead><tr><th>Variant</th><th>Dimension</th><th>Measured In</th>
                     <th>Supply Base Rate</th><th>Installation Base Rate</th></tr></thead>
          <tbody>{body}</tbody>
        </table></div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title(P.esc(s.get('code')))}</title>{B.HEAD_ICON}
    {BASE_STYLES}{SPEC_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Spec <span>{P.esc(s.get('code'))}</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{url_for('spec.list_specs')}" class="btn btn-ghost">&#8592; Library</a>
          <a href="{url_for('spec.edit_spec', id=id)}" class="btn">&#9998;&nbsp;Edit</a>
        </div>
      </div>

      <div class="spec-head">
        <div class="sh-code">{P.esc(s.get('code'))}</div>
        <div class="sh-title">{P.esc(s.get('title'))}</div>
        <span class="cat-badge">{P.esc(s.get('category'))}</span>
        <div class="sh-meta">
          <div class="sh-cell"><div class="sh-lbl">HSN (supply)</div>
            <div class="sh-val">{P.esc(s.get('supply_hsn')) or '&mdash;'}</div></div>
          <div class="sh-cell"><div class="sh-lbl">SAC (installation)</div>
            <div class="sh-val">{P.esc(s.get('install_sac')) or '&mdash;'}</div></div>
          <div class="sh-cell"><div class="sh-lbl">Supply GST</div>
            <div class="sh-val">{float(s.get('supply_gst_rate') or 0):g}%</div></div>
          <div class="sh-cell"><div class="sh-lbl">Installation GST</div>
            <div class="sh-val">{float(s.get('install_gst_rate') or 0):g}%</div></div>
          <div class="sh-cell"><div class="sh-lbl">Variants</div>
            <div class="sh-val">{len(variants)}</div></div>
        </div>
      </div>

      <div class="ref-note">{REFERENCE_NOTE}</div>

      <div class="form-section">
        <div class="section-title">&#128221; Clause Text</div>
        <div class="spec-text">{P.esc(s.get('spec_text'))}</div>
        <p style="margin-top:.7rem;font-size:.78rem;color:var(--muted);">
          This text is <b>copied</b> onto a BOQ line, never referenced. Editing it
          here does not reach a BOQ already written, and editing it there does not
          write back — the same freeze every issued document in this app relies on.
        </p>
      </div>

      <div class="form-section">
        <div class="section-title">&#128207; Variants</div>
        {var_html}
      </div>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · specification library</p></footer>
    </main></body></html>"""
    return render_template_string(template)


@spec_bp.route("/add", methods=["GET", "POST"])
def add_spec():
    ensure_demo_specs()

    if request.method == "POST":
        data, error = _validate(request.form)
        if error:
            return _render_form(data, error, "add")

        sid = str(uuid.uuid4())
        STORE["specs"][sid] = {"id": sid, **data}
        return redirect(url_for("spec.view_spec", id=sid,
                                msg=f"Spec {data['code']} added.", type="success"))

    return _render_form({
        "code": "", "title": "", "spec_text": "", "category": DEFAULT_CATEGORY,
        "supply_hsn": "", "install_sac": "",
        "supply_gst_rate": DEFAULT_GST_RATE, "install_gst_rate": DEFAULT_GST_RATE,
        "variants": [],
    }, "", "add")


@spec_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_spec(id: str):
    """
    The edit route this module has from day one.

    ABOUT.md §7.2 calls `product.py`'s missing edit route the highest-value gap
    in the repo — it is why a blank HSN cannot be blocked at the tax invoice and
    why the seeder has to backfill. A library of 56 clauses, several of them
    1300 characters, cannot be maintained by delete-and-re-add. It shares
    `_render_form()` and `_validate()` with `add_spec`, so the two cannot drift.
    """
    ensure_demo_specs()
    s = STORE["specs"].get(id)
    if not s:
        return redirect(url_for("spec.list_specs", msg="Spec not found.", type="error"))

    if request.method == "POST":
        data, error = _validate(request.form, spec_id=id)
        if error:
            return _render_form(data, error, "edit", id)

        # Mutate in place: STORE is one shared dict and db.py diffs it, so
        # replacing the object would work too — but every other module edits in
        # place and consistency is worth more than the micro-difference.
        s.update(data)
        return redirect(url_for("spec.view_spec", id=id,
                                msg=f"Spec {data['code']} updated.", type="success"))

    return _render_form(dict(s), "", "edit", id)


@spec_bp.route("/delete/<id>")
def delete_spec(id: str):
    """
    Delete, with **no dependency guard — deliberately.**

    `product.can_delete_product()` refuses to remove anything used as a child in
    an assembly, because a BOM holds a live `product_id` and deleting the target
    would break the parent. Nothing equivalent exists here: a BOQ line item
    carries **no `spec_id`** (handover §4.2). `spec_text`, the rates, the unit
    and the tax codes are all *copied* onto the line at the moment it is
    written, and edited there.

    So a spec has no dependents by construction, and removing one cannot reach a
    BOQ — issued or draft. The absence of a guard here is the design, not an
    oversight.

    The trade-off is real and worth stating: there is no traceability from a BOQ
    line back to the library entry it came from. Adding one would mean adding a
    field to a contracted shape, and it would have to survive the line being
    edited away from the spec, at which point the link is a lie. Not worth it
    yet.
    """
    ensure_demo_specs()
    s = STORE["specs"].pop(id, None)
    if not s:
        return redirect(url_for("spec.list_specs", msg="Spec not found.", type="error"))
    return redirect(url_for("spec.list_specs",
                            msg=f"Spec {s.get('code')} deleted. BOQs written from it are unaffected.",
                            type="success"))
