"""
pricesummary.py: the one-page PRICE SUMMARY cover, and the print orientation
==========================================================================

CLIENT_CHANGES.md §0, the ninetieth block (25 November 2026). The client sent
their own RIL Jamnagar quotation workbook and asked that a quotation "look like
this: first one page summary, then the rest of the sheet". This module is what
the printed BOQ (`boq.print_boq()`) and the printed quotation
(`quotation.view_quotation()`) share so the cover looks the same on both.

## What lives here, and what does not

* **Layout only.** `summary_html()` takes rows the CALLER has already priced
  and formatted (`(sr, description, [amount strings])`) and lays them out. It
  computes no subtotal, no tax and no round off: those stay in each chain
  (`boq.section_totals()`, `quotation._tax_lines()`), the same rule
  `docsheet.py` follows for its totals rows. A summary that did its own sums
  could disagree with the detail pages; one that only prints the chain's own
  figures cannot.
* **The /settings record** (`STORE["settings"]["price_summary"]`): the title,
  the tax line and the ONE default terms list both documents copy at create.
  It is read here, not in `settings.py`, because `boq.py` may not import
  `settings.py` (`tests/test_import_directions.py`), the reason `series.py`
  exists. `settings.py` owns the page that edits the record.
* **The per-document fields**, all optional, all read through one helper each:

  | key | absent means | read by |
  |---|---|---|
  | `price_summary_on` | ON (every existing document gets the cover) | `is_on()` |
  | `summary_terms` | no terms stored yet (`tools/backfill_terms.py` fills it) | `terms_of()` |
  | `print_orientation` | the document type's own default | `orientation_of()` |

## The snapshot rule

A printed document prints ITS OWN `summary_terms`, never the live /settings
list. The list is COPIED into the record at create (`default_terms()`), and is
then the document's own to edit on its form. Editing the default at /settings
changes no document already raised: the same class of rule as `/ra/print`
reading the record and never the live BOQ.

## Imports

`store` and `pipeline` only, so `boq.py` and `quotation.py` (inside its
unfrozen functions) can both reach it, and it can reach neither.
"""

import re
import uuid

from store import STORE
import pipeline as P


RECORD = "price_summary"

DEFAULT_TITLE = "PRICE SUMMARY FOR FIRE PROTECTION SYSTEM"
DEFAULT_TAX_LINE = "TAXES WILL BE EXTRA"

# The client's own eleven terms, VERBATIM from the RIL Jamnagar summary sheet
# (25 Nov 2026). Seeded once, never over a list the client has edited.
DEFAULT_TERMS = (
    "Two layers of primer and two layers of final paint are included in our "
    "scope. Cora coating and GRIT blasting are strictly excluded and shall be "
    "managed under the Client's scope.",
    "The supply of A-type ladders is included in our scope.",
    "Our civil scope is limited to through-and-through hole making. Any core "
    "cutting, excavation, or structural breaking work is completely excluded "
    "from our scope.",
    "Transportation of all materials from the fabrication yard to the erection "
    "point shall be managed and paid for entirely by the Client.",
    "The Client must provide continuous electricity, water, and safe storage "
    "facilities at the site at no extra cost to us.",
    "NDT/Radiography testing, Holiday testing, and all arrangements for "
    "Pneumatic testing (including Nitrogen and compressors) are strictly under "
    "the Client's scope.",
    "50% advance payment upon order placement.",
    "30% advance payment before mobilization.",
    "60% payment against running bills based on work progress.",
    "10% retention payment completion of work.",
    "Goods and Services Tax (GST) is not included in the quoted rates and will "
    "be charged extra as applicable at the time of invoicing.",
)

# The TERMS LIBRARY (26 Nov 2026, §0 ninety-first block). Every term has a
# category; the client's eleven above are the first eleven, ON by default.
CATEGORIES = ("Scope", "Exclusions", "Site", "Payment", "Taxes", "Commercial",
              "Delivery", "Warranty", "Legal")
SEED_CATEGORIES = ("Scope", "Scope", "Exclusions", "Exclusions", "Site",
                   "Exclusions", "Payment", "Payment", "Payment", "Payment",
                   "Taxes")
FALLBACK_CATEGORY = "Commercial"

# Seeded OFF by default once (`extras_seeded`), never over an edit, never
# back after a delete. Available to pick; printed only when picked.
EXTRA_TERMS = (
    ("Commercial", "This offer is valid for 30 days from the date of quotation."),
    ("Commercial", "Final billing will be on actual quantities measured jointly at "
                   "site, at the unit rates quoted."),
    ("Commercial", "Any extra or additional work not covered in this quotation will "
                   "be charged separately at mutually agreed rates."),
    ("Delivery", "Material will be delivered within 2 to 3 weeks from receipt of the "
                 "confirmed order and advance payment, subject to availability."),
    ("Delivery", "Material once supplied to site will not be taken back."),
    ("Warranty", "Equipment supplied carries the manufacturer's standard warranty "
                 "against manufacturing defects."),
    ("Warranty", "Our workmanship is warranted for 12 months from the date of "
                 "commissioning. Damage due to misuse, mishandling or work by other "
                 "agencies is not covered."),
    ("Exclusions", "Statutory approvals, liaisoning and NOC from the Fire Department "
                   "are excluded unless specifically mentioned."),
    ("Exclusions", "Scaffolding, staging and lifting arrangements beyond A-type "
                   "ladders shall be provided by the Client."),
    ("Exclusions", "Power cabling up to the pump control panel and earthing are "
                   "excluded unless specifically mentioned."),
    ("Site", "Suitable accommodation for our labour at or near the site shall be "
             "provided by the Client."),
    ("Site", "Storage and safety of material at site after delivery is in the "
             "Client's scope."),
    ("Site", "Idle time of our manpower caused by reasons attributable to the Client "
             "or other agencies will be charged extra."),
    ("Site", "A clear and ready work front shall be made available by the Client "
             "before mobilization."),
    ("Payment", "Running bills shall be paid within 15 days of submission."),
    ("Legal", "We shall not be liable for delays caused by events beyond our control, "
              "including natural calamities, strikes or government restrictions."),
    ("Legal", "All disputes are subject to Navi Mumbai jurisdiction."),
)

# Per-document keys.
FIELD_ON = "price_summary_on"
FIELD_TERMS = "summary_terms"
FIELD_ORIENT = "print_orientation"
MARK_ON = "price_summary_present"     # the form offered the tick
FIELD_TERM = "summary_term"           # one posted <input> per term, in order
FIELD_TERM_LIB = "summary_term_lib"   # parallel: a category = "also save to library"
MARK_TERMS = "summary_terms_present"  # the form offered the editor

# The /settings library editor's parallel lists.
MARK_LIB = "summary_library_present"
LIB_ID, LIB_TEXT, LIB_CAT, LIB_ON = "lib_id", "lib_text", "lib_cat", "lib_on"

# The quotation's two (it has no project name and no sections): the cover's
# subject line and its one row's System Description. Blank prints a default
# the quotation derives (`quotation._summary_cover()`).
FIELD_SUBJECT = "summary_subject"
FIELD_SYSTEM = "summary_system"

PORTRAIT, LANDSCAPE = "portrait", "landscape"
ORIENTATIONS = (PORTRAIT, LANDSCAPE)

MAX_TERMS = 60
MAX_LIBRARY = 300
MAX_TERM_CHARS = 1000
MAX_TEXT_CHARS = 200


# =============================================================================
# THE /settings RECORD
# =============================================================================

def _entry(text: str, category: str, on: bool, eid: str = "") -> dict:
    return {"id": eid or uuid.uuid4().hex[:12], "text": text,
            "category": category if category in CATEGORIES else FALLBACK_CATEGORY,
            "on": bool(on)}


def ensure_seeded() -> None:
    """
    Seed, and migrate, the record. Idempotent: a second call changes nothing.

    * ABSENT: the client's eleven, ON by default, in `SEED_CATEGORIES`.
    * The 25 Nov shape (a flat `terms` list, no `library`): THAT list becomes
      the library as it stands, every term ON by default, each in its seed
      category when its text is a seed term exactly, else "Commercial". The
      unedited seed therefore migrates to exactly the eleven above, and an
      edited list loses nothing. The flat list is kept as `legacy_terms`.
    * The extras (`EXTRA_TERMS`) are appended OFF by default once, skipping a
      text already there; `extras_seeded` stops a deleted one coming back.

    A genuine default, seeded whatever SAMRUDDHI_DEMO_DATA says.
    """
    rec = STORE["settings"].get(RECORD)
    if not isinstance(rec, dict):
        rec = {"title": DEFAULT_TITLE, "tax_line": DEFAULT_TAX_LINE}
        STORE["settings"][RECORD] = rec
    if not isinstance(rec.get("library"), list):
        cats = dict(zip(DEFAULT_TERMS, SEED_CATEGORIES))
        old = rec.get("terms")
        texts = clean_terms(old) if isinstance(old, list) else list(DEFAULT_TERMS)
        # Stable ids for what is seeded or migrated (`term-01`...), so the
        # page renders the same bytes every time; new terms get a uuid.
        rec["library"] = [_entry(t, cats.get(t, FALLBACK_CATEGORY), True, f"term-{i + 1:02d}")
                          for i, t in enumerate(texts)]
        if isinstance(old, list):
            rec["legacy_terms"] = list(old)
            rec.pop("terms", None)
    if not rec.get("extras_seeded"):
        have = {e.get("text") for e in rec["library"] if isinstance(e, dict)}
        for i, (cat, text) in enumerate(EXTRA_TERMS):
            if text not in have:
                rec["library"].append(_entry(text, cat, False, f"extra-{i + 1:02d}"))
        rec["extras_seeded"] = True


def library() -> list:
    """The library, in order: `[{"id", "text", "category", "on"}]` (copies)."""
    ensure_seeded()
    out = []
    for e in STORE["settings"][RECORD].get("library") or []:
        if isinstance(e, dict) and str(e.get("text") or "").strip():
            out.append({"id": str(e.get("id") or ""), "text": str(e["text"]),
                        "category": e.get("category") if e.get("category") in CATEGORIES
                        else FALLBACK_CATEGORY, "on": bool(e.get("on"))})
    return out


def settings_of() -> dict:
    """`{"title", "tax_line", "terms", "library"}`. `terms` is the ON-by-default
    set, in library order. A blank title or tax line reads as its default."""
    ensure_seeded()
    rec = STORE["settings"][RECORD]
    lib = library()
    return {"title": str(rec.get("title") or "").strip() or DEFAULT_TITLE,
            "tax_line": str(rec.get("tax_line") or "").strip() or DEFAULT_TAX_LINE,
            "terms": [e["text"] for e in lib if e["on"]], "library": lib}


def save_settings(title: str, tax_line: str, entries: list) -> None:
    """Replace the record. `entries` are library dicts, or plain strings (each
    then a term ON by default in "Commercial")."""
    ensure_seeded()
    rec = STORE["settings"][RECORD]
    lib = []
    for e in entries or []:
        if isinstance(e, str):
            e = {"text": e, "category": FALLBACK_CATEGORY, "on": True}
        text = clean_terms([e.get("text")])
        if text:
            lib.append(_entry(text[0], e.get("category"), e.get("on"), e.get("id") or ""))
    rec.update({"title": str(title or "").strip()[:MAX_TEXT_CHARS],
                "tax_line": str(tax_line or "").strip()[:MAX_TEXT_CHARS],
                "library": lib[:MAX_LIBRARY], "extras_seeded": True})


def library_add(text: str, category: str, on: bool = False) -> bool:
    """Add a term to the library from a document's form, OFF by default, unless
    the same text is already there. True when it was added."""
    ensure_seeded()
    t = clean_terms([text])
    if not t:
        return False
    lib = STORE["settings"][RECORD]["library"]
    if any(isinstance(e, dict) and e.get("text") == t[0] for e in lib):
        return False
    if len(lib) >= MAX_LIBRARY:
        return False
    lib.append(_entry(t[0], category, on))
    return True


def form_library(form) -> list:
    """The /settings library editor as posted: four parallel lists, in order;
    a row with blank text is dropped."""
    ids, texts = form.getlist(LIB_ID), form.getlist(LIB_TEXT)
    cats, ons = form.getlist(LIB_CAT), form.getlist(LIB_ON)
    out = []
    for i, t in enumerate(texts):
        out.append({"id": ids[i] if i < len(ids) else "", "text": t,
                    "category": cats[i] if i < len(cats) else FALLBACK_CATEGORY,
                    "on": (ons[i] if i < len(ons) else "") == "1"})
    return out


def default_terms() -> list:
    """A COPY of the library's ON-by-default terms, in library order, for a
    document being created."""
    return list(settings_of()["terms"])


# =============================================================================
# THE PAYMENT WARNING (never blocks, never prints)
# =============================================================================

PAY_WORDS = ("payment", "advance", "retention", "running bill")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _payment_library_texts() -> set:
    return {e["text"] for e in library() if e["category"] == "Payment"}


def is_payment_term(text: str, pay_lib=None) -> bool:
    t = " ".join(str(text or "").split())
    pay_lib = _payment_library_texts() if pay_lib is None else pay_lib
    return t in pay_lib or any(w in t.lower() for w in PAY_WORDS)


def payment_total(terms, pay_lib=None):
    """The sum of the percentages in the payment lines, or None when no
    payment line carries one."""
    pay_lib = _payment_library_texts() if pay_lib is None else pay_lib
    total, seen = 0.0, False
    for t in terms or []:
        if is_payment_term(t, pay_lib):
            for m in _PCT.finditer(str(t)):
                total += float(m.group(1))
                seen = True
    return round(total, 2) if seen else None


def payment_warning(terms, pay_lib=None) -> str:
    """"Payment terms add up to N%." when the payment percentages are present
    and do not come to 100; "" otherwise."""
    n = payment_total(terms, pay_lib)
    if n is None or abs(n - 100.0) < 0.005:
        return ""
    return f"Payment terms add up to {n:g}%."


PAY_NOTE_STYLE = ("background:#fffbeb;border:1px solid #fcd34d;border-left:3px solid "
                  "#d97706;border-radius:6px;padding:.35rem .6rem;font-size:.8rem;"
                  "color:#78350f;")


def payment_note_html(terms) -> str:
    """The amber note for a print page's action bar: screen only, "" when the
    payment percentages come to 100 or there are none."""
    w = payment_warning(terms)
    if not w:
        return ""
    return (f'<span class="no-print ps-pay-bar" role="note" '
            f'style="{PAY_NOTE_STYLE}align-self:center;">&#9888; {P.esc(w)}</span>')


# =============================================================================
# THE PER-DOCUMENT FIELDS
# =============================================================================

def clean_terms(terms) -> list:
    out = []
    for t in terms or []:
        t = " ".join(str(t or "").replace("\r", " ").split())
        if t:
            out.append(t[:MAX_TERM_CHARS])
    return out[:MAX_TERMS]


def is_on(doc) -> bool:
    """The tick. Absent is ON: every document raised before this block gets
    the cover (R2)."""
    return (doc or {}).get(FIELD_ON) is not False


def terms_of(doc) -> list:
    v = (doc or {}).get(FIELD_TERMS)
    return clean_terms(v) if isinstance(v, list) else []


def has_terms(doc) -> bool:
    return isinstance((doc or {}).get(FIELD_TERMS), list)


def orientation_of(doc, default: str) -> str:
    v = str((doc or {}).get(FIELD_ORIENT) or "").strip().lower()
    return v if v in ORIENTATIONS else default


def orientation_value(raw) -> str:
    """A posted orientation, or "" for anything that is not one."""
    v = str(raw or "").strip().lower()
    return v if v in ORIENTATIONS else ""


def form_on(form, legacy: bool = True) -> bool:
    """The tick as posted, or `legacy` from a form that did not offer it."""
    if form is None or form.get(MARK_ON) is None:
        return bool(legacy)
    return str(form.get(FIELD_ON) or "").strip().lower() in ("1", "on", "true", "yes")


def form_terms(form, legacy) -> list:
    """The terms as posted, in order, or `legacy` from a form without the
    editor. An editor posted with every row emptied is an empty list."""
    if form is None or form.get(MARK_TERMS) is None:
        return list(legacy or [])
    return clean_terms(form.getlist(FIELD_TERM))


def form_section_args(form, legacy_terms: list) -> tuple:
    """`(terms, save_cats)` for a refused POST's re-render: what was posted,
    in order, with each row's "save to library" category kept; or
    `(legacy_terms, [])` from a form without the editor."""
    if form is None or form.get(MARK_TERMS) is None:
        return list(legacy_terms or []), []
    pairs = form_term_pairs(form)
    return [t for t, _c in pairs], [c for _t, c in pairs]


def form_term_pairs(form) -> list:
    """`[(text, save_category)]` as posted, in order, blanks dropped.
    `save_category` is a category when the row was added with "Also save to
    library" ticked, else ""."""
    texts, libs = form.getlist(FIELD_TERM), form.getlist(FIELD_TERM_LIB)
    out = []
    for i, t in enumerate(texts):
        c = clean_terms([t])
        if c:
            out.append((c[0], libs[i] if i < len(libs) else ""))
    return out[:MAX_TERMS]


def apply_form(doc: dict, form, creating: bool, may_save_library: bool = False) -> None:
    """Write the tick and the terms from a document's own form onto `doc`.
    On create the terms default to a copy of the library's ON-by-default set;
    on edit to what the record holds. A term posted with a save category is
    added to the library (OFF by default) only when `may_save_library`, which
    the caller answers from the /settings permission."""
    doc[FIELD_ON] = form_on(form, legacy=is_on(doc))
    if form is not None and form.get(MARK_TERMS) is not None:
        pairs = form_term_pairs(form)
        doc[FIELD_TERMS] = [t for t, _c in pairs]
        if may_save_library:
            for t, c in pairs:
                if c in CATEGORIES:
                    library_add(t, c, on=False)
    elif creating:
        doc[FIELD_TERMS] = default_terms()


def _terms_text(doc) -> str:
    if not has_terms(doc):
        return ""
    return "\n".join(f"{i + 1}. {t}" for i, t in enumerate(terms_of(doc))) or "(no terms)"


def log_changes(before: dict, after: dict) -> list:
    """`[(label, was, now)]` for `editlog.record()`: the tick, the terms list
    (numbered, before and after) and the quotation's two summary texts."""
    out = []
    if is_on(before) != is_on(after):
        out.append(("Price summary page", "Yes" if is_on(before) else "No",
                     "Yes" if is_on(after) else "No"))
    if _terms_text(before) != _terms_text(after):
        out.append(("Summary terms", _terms_text(before), _terms_text(after)))
    for k, label in ((FIELD_SUBJECT, "Summary subject line"),
                     (FIELD_SYSTEM, "System description (summary row)")):
        was, now = str(before.get(k) or ""), str(after.get(k) or "")
        if was != now:
            out.append((label, was, now))
    return out


def orientation_change(doc: dict, new: str, default: str) -> list:
    """The one log entry the print page's switch writes, or [] for no change."""
    was = orientation_of(doc, default)
    return [] if was == new else [("Print orientation", was.capitalize(), new.capitalize())]


# =============================================================================
# THE FORM WIDGETS
# =============================================================================

EDITOR_CSS = """
<style>
  .ps-ed { margin-top:.4rem; }
  .ps-ed-row { display:flex; gap:.4rem; align-items:flex-start; margin-bottom:.35rem; }
  .ps-ed-no { min-width:1.6rem; font-weight:700; color:var(--muted, #64748b);
              padding-top:.45rem; text-align:right; font-size:.8rem; }
  .ps-ed-row textarea { flex:1 1 auto; min-height:2.4rem; resize:vertical;
                        font-size:.85rem; }
  .ps-ed-row select { flex:0 0 9rem; font-size:.8rem; }
  .ps-ed-on { flex:0 0 auto; font-size:.75rem; white-space:nowrap; padding-top:.45rem;
              display:flex; gap:.25rem; align-items:center; }
  .ps-ed-btn { font-size:.75rem; padding:.3rem .5rem; border-radius:6px;
               border:1px solid var(--border, #e2e8f0); background:#fff; cursor:pointer; }
  .ps-ed-btn:hover { background:#eef2ff; }
  .ps-ed-add { display:flex; gap:.4rem; align-items:flex-start; flex-wrap:wrap;
               margin-top:.6rem; padding-top:.6rem; border-top:1px dashed var(--border, #e2e8f0); }
  .ps-ed-add select { flex:1 1 18rem; max-width:100%; font-size:.8rem; }
  .ps-ed-add textarea { flex:1 1 18rem; min-height:2.4rem; font-size:.85rem; }
  .ps-ed-add label { font-size:.78rem; display:flex; gap:.3rem; align-items:center; }
  .ps-ed-hint { font-size:.78rem; color:var(--muted, #64748b); margin:.1rem 0 .4rem; }
  .ps-pay-note { margin:.2rem 0 .5rem; padding:.35rem .6rem; font-size:.8rem;
                 background:#fffbeb; border:1px solid #fcd34d; border-left:3px solid #d97706;
                 border-radius:6px; color:#78350f; }
  @media print { .ps-pay-note, .ps-pay-bar { display:none !important; } }
</style>
"""

# Plain string, interpolated as a value: nothing in it needs doubling. ONE
# <script> for the document editor (psEd), the library editor (psLib) and the
# live payment note (psPay).
EDITOR_JS = """
<script>
(function () {
  if (window.psEd) return;
  var WORDS = ['payment', 'advance', 'retention', 'running bill'];
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function renum(box) {
    var rows = box.querySelectorAll('.ps-ed-list > .ps-ed-row');
    for (var i = 0; i < rows.length; i++) {
      rows[i].querySelector('.ps-ed-no').textContent = (i + 1) + '.';
    }
    psPay(box);
  }
  function payLib(box) {
    var t = box.querySelector('template.ps-pay-lib');
    if (!t) return [];
    return Array.prototype.map.call(t.content.querySelectorAll('i'),
                                    function (e) { return e.textContent; });
  }
  window.psPay = function (box) {
    var note = box.querySelector('.ps-pay-note');
    if (!note) return;
    var lib = payLib(box), total = 0, seen = false;
    each(box.querySelectorAll('.ps-ed-list > .ps-ed-row'), function (row) {
      var ta = row.querySelector('textarea');
      var t = ta.value.replace(/\\s+/g, ' ').trim();
      if (!t) return;
      var cat = row.querySelector('select.ps-lib-cat');
      var on = row.querySelector('input.ps-lib-on');
      if (on && on.value !== '1') return;
      var low = t.toLowerCase();
      var pay = (cat ? cat.value === 'Payment' : lib.indexOf(t) >= 0) ||
                WORDS.some(function (w) { return low.indexOf(w) >= 0; });
      if (!pay) return;
      var m, re = /(\\d+(?:\\.\\d+)?)\\s*%/g;
      while ((m = re.exec(t))) { total += parseFloat(m[1]); seen = true; }
    });
    total = Math.round(total * 100) / 100;
    if (seen && total !== 100) {
      note.textContent = '\\u26A0 Payment terms add up to ' + total + '%.';
      note.hidden = false;
    } else {
      note.hidden = true;
    }
  };
  function addRow(box, text, cat) {
    var tpl = box.querySelector('template.ps-row-tpl');
    var frag = tpl.content.cloneNode(true);
    frag.querySelector('textarea').value = text;
    var flag = frag.querySelector('input.ps-lib-flag');
    if (flag) flag.value = cat || '';
    box.querySelector('.ps-ed-list').appendChild(frag);
  }
  function move(btn, act) {
    var row = btn.closest('.ps-ed-row');
    if (act === 'del') {
      row.parentNode.removeChild(row);
    } else if (act === 'up' && row.previousElementSibling) {
      row.parentNode.insertBefore(row, row.previousElementSibling);
    } else if (act === 'down' && row.nextElementSibling) {
      row.parentNode.insertBefore(row.nextElementSibling, row);
    }
  }
  window.psEd = function (btn, act) {
    var box = btn.closest('.ps-ed');
    if (act === 'lib') {
      var sel = box.querySelector('select.ps-lib-pick');
      var o = sel.options[sel.selectedIndex];
      if (!o || !o.value) return;
      addRow(box, o.value, '');
      o.parentNode.removeChild(o);
      sel.selectedIndex = 0;
    } else if (act === 'own') {
      var ta = box.querySelector('textarea.ps-own-text');
      var t = ta.value.trim();
      if (!t) return;
      var sv = box.querySelector('input.ps-own-save');
      var cs = box.querySelector('select.ps-own-cat');
      addRow(box, t, (sv && sv.checked && cs) ? cs.value : '');
      ta.value = '';
      if (sv) sv.checked = false;
    } else if (act === 'new') {
      addRow(box, '', '');
    } else {
      move(btn, act);
    }
    renum(box);
  };
  window.psLibOn = function (cb) {
    cb.parentNode.querySelector('input.ps-lib-on').value = cb.checked ? '1' : '0';
    psPay(cb.closest('.ps-ed'));
  };
  document.addEventListener('input', function (e) {
    var b = e.target.closest && e.target.closest('.ps-ed');
    if (b) psPay(b);
  });
  document.addEventListener('change', function (e) {
    var b = e.target.closest && e.target.closest('.ps-ed');
    if (b) psPay(b);
  });
})();
</script>
"""


def _btns() -> str:
    return (f'<button type="button" class="ps-ed-btn" title="Move up" '
            f'onclick="psEd(this,&#39;up&#39;)">&#8593;</button>'
            f'<button type="button" class="ps-ed-btn" title="Move down" '
            f'onclick="psEd(this,&#39;down&#39;)">&#8595;</button>'
            f'<button type="button" class="ps-ed-btn" title="Remove" '
            f'onclick="psEd(this,&#39;del&#39;)">&#10005;</button>')


def _editor_row(i: int, text: str, save_cat: str = "") -> str:
    return (f'<div class="ps-ed-row"><span class="ps-ed-no">{i}.</span>'
            f'<textarea name="{FIELD_TERM}" rows="2">{P.esc(text)}</textarea>'
            f'<input type="hidden" class="ps-lib-flag" name="{FIELD_TERM_LIB}" '
            f'value="{P.esc(save_cat)}"/>{_btns()}</div>')


def _cat_options(current: str) -> str:
    return "".join(f'<option value="{c}"{" selected" if c == current else ""}>{c}</option>'
                   for c in CATEGORIES)


def _pay_note(warning: str) -> str:
    hidden = "" if warning else " hidden"
    return (f'<div class="ps-pay-note" role="note"{hidden}>'
            f'{"&#9888; " + P.esc(warning) if warning else ""}</div>')


def _pay_lib_template(lib: list) -> str:
    return ('<template class="ps-pay-lib">'
            + "".join(f"<i>{P.esc(e['text'])}</i>" for e in lib if e["category"] == "Payment")
            + "</template>")


def editor_html(terms: list, label: str = "Terms &amp; Conditions",
                may_save_library: bool = False, hint: str = "",
                save_cats: list = None) -> str:
    """
    A document's OWN terms (26 Nov 2026, §0 ninety-first block): the stored
    list (edit, remove, move up, move down), then **Add from library** (a
    picker of library terms not already on the document, grouped by
    category) and **Add your own term** (free text; "Also save to library"
    only when `may_save_library`). The amber payment note is screen only.
    Posts one `summary_term` (and a parallel `summary_term_lib`) per row, in
    order, with a marker so an emptied list is told apart from a form that
    never offered the editor. No `{` or `}` in the markup.
    """
    lib = library()
    terms = list(terms or [])
    on_doc = set(terms)
    save_cats = list(save_cats or [])
    rows = "".join(_editor_row(i + 1, t, (save_cats[i] if i < len(save_cats) else "")
                               if may_save_library else "")
                   for i, t in enumerate(terms))
    groups = ""
    for c in CATEGORIES:
        opts = "".join(
            f'<option value="{P.esc(e["text"])}">'
            f'{P.esc(e["text"] if len(e["text"]) <= 110 else e["text"][:107] + "...")}</option>'
            for e in lib if e["category"] == c and e["text"] not in on_doc)
        if opts:
            groups += f'<optgroup label="{c}">{opts}</optgroup>'
    save = ""
    if may_save_library:
        save = (f'<label><input type="checkbox" class="ps-own-save"/> Also save to library</label>'
                f'<select class="ps-own-cat" aria-label="Library category">'
                f'{_cat_options(FALLBACK_CATEGORY)}</select>')
    hint_html = f'<div class="ps-ed-hint">{hint}</div>' if hint else ""
    return (f'{EDITOR_CSS}<div class="form-group ps-ed">'
            f'<input type="hidden" name="{MARK_TERMS}" value="1"/>'
            f'<label>{label}</label>{hint_html}'
            f'{_pay_note(payment_warning(terms))}'
            f'<div class="ps-ed-list">{rows}</div>'
            f'<template class="ps-row-tpl">{_editor_row(0, "")}</template>'
            f'{_pay_lib_template(lib)}'
            f'<div class="ps-ed-add">'
            f'<select class="ps-lib-pick" aria-label="Add from library">'
            f'<option value="">Add from library...</option>{groups}</select>'
            f'<button type="button" class="ps-ed-btn" onclick="psEd(this,&#39;lib&#39;)">'
            f'+ Add</button></div>'
            f'<div class="ps-ed-add">'
            f'<textarea class="ps-own-text" rows="2" placeholder="Add your own term"></textarea>'
            f'{save}<button type="button" class="ps-ed-btn" onclick="psEd(this,&#39;own&#39;)">'
            f'+ Add your own term</button></div>'
            f'</div>{EDITOR_JS}')


def _library_row(i: int, e: dict) -> str:
    checked = " checked" if e.get("on") else ""
    return (f'<div class="ps-ed-row"><span class="ps-ed-no">{i}.</span>'
            f'<input type="hidden" name="{LIB_ID}" value="{P.esc(e.get("id", ""))}"/>'
            f'<textarea name="{LIB_TEXT}" rows="2">{P.esc(e.get("text", ""))}</textarea>'
            f'<select name="{LIB_CAT}" class="ps-lib-cat" aria-label="Category">'
            f'{_cat_options(e.get("category") or FALLBACK_CATEGORY)}</select>'
            f'<label class="ps-ed-on"><input type="checkbox" onchange="psLibOn(this)"{checked}/>'
            f'<input type="hidden" class="ps-lib-on" name="{LIB_ON}" '
            f'value="{"1" if e.get("on") else "0"}"/> On by default</label>{_btns()}</div>')


def library_editor_html(entries: list) -> str:
    """The /settings TERMS LIBRARY: every term's text, category and "on by
    default" tick, in order; add, edit, delete, reorder, recategorise. The
    amber note is for the ON-by-default set (screen only)."""
    entries = list(entries or [])
    pay = {e["text"] for e in entries if e.get("category") == "Payment"}
    warning = payment_warning([e["text"] for e in entries if e.get("on")], pay)
    rows = "".join(_library_row(i + 1, e) for i, e in enumerate(entries))
    blank = {"id": "", "text": "", "category": FALLBACK_CATEGORY, "on": False}
    return (f'{EDITOR_CSS}<div class="form-group ps-ed ps-lib">'
            f'<input type="hidden" name="{MARK_LIB}" value="1"/>'
            f'<label>Terms library</label>'
            f'<div class="ps-ed-hint">Ticked terms are where every new BOQ and '
            f'quotation starts; the rest are offered under Add from library on the '
            f'document. Editing or deleting a term here never changes a document '
            f'already raised.</div>'
            f'{_pay_note(warning)}'
            f'<div class="ps-ed-list">{rows}</div>'
            f'<template class="ps-row-tpl">{_library_row(0, blank)}</template>'
            f'<button type="button" class="ps-ed-btn" onclick="psEd(this,&#39;new&#39;)">'
            f'+ Add a library term</button></div>{EDITOR_JS}')


def checkbox_html(on: bool) -> str:
    checked = " checked" if on else ""
    return (f'<div class="form-group ps-tick">'
            f'<input type="hidden" name="{MARK_ON}" value="1"/>'
            f'<label style="display:flex;gap:.45rem;align-items:center;font-weight:600;">'
            f'<input type="checkbox" name="{FIELD_ON}" value="1"{checked}/> '
            f'Include price summary page</label>'
            f'<small class="field-hint" style="display:block;">Prints a one-page '
            f'price summary before the detailed sheet, with the terms below.</small>'
            f'</div>')


def text_fields_html(subject: str, system: str, subject_hint: str,
                     system_hint: str) -> str:
    """The quotation's subject and System Description boxes (blank = the
    default shown as the placeholder)."""
    def box(name, label, val, hint):
        return (f'<div class="form-group"><label for="{name}">{label}</label>'
                f'<input type="text" id="{name}" name="{name}" maxlength="{MAX_TEXT_CHARS}" '
                f'value="{P.esc(val)}" placeholder="{P.esc(hint)}"/></div>')
    return ('<div class="fg2">'
            + box(FIELD_SUBJECT, "Summary subject line", subject, subject_hint)
            + box(FIELD_SYSTEM, "System description (summary row)", system, system_hint)
            + '</div>')


def quote_defaults(q: dict) -> tuple:
    """`(subject, system)` a quotation's cover prints when its own two boxes
    are blank: "<Ship To name, else Customer> Quotation", and its Lead
    Sub-type, else "Fire Protection System". Words only, no money."""
    q = q or {}
    name = ""
    if not q.get("ship_same"):
        name = str(q.get("ship_acct_name") or "").strip()
    name = name or str(q.get("account_name") or "").strip()
    subject = f"{name} Quotation" if name else "Quotation"
    system = str(q.get("lead_subtype") or "").strip() or "Fire Protection System"
    return subject, system


def form_text(form, name: str, legacy: str = "") -> str:
    if form is None or form.get(name) is None:
        return str(legacy or "")
    return " ".join(str(form.get(name) or "").split())[:MAX_TEXT_CHARS]


QUOTE_TERMS_HINT = "With the price summary page on, these are the only terms printed."


def form_section_html(on: bool, terms: list, extra: str = "",
                      may_save_library: bool = False, hint: str = "",
                      save_cats: list = None) -> str:
    """The whole block a document form draws: the tick, any extra fields the
    caller passes (already escaped), and the terms editor."""
    return (f'<div class="form-section"><div class="section-title">'
            f'&#128209;&nbsp; Price Summary Page</div>'
            f'{checkbox_html(on)}{extra}'
            f'{editor_html(terms, may_save_library=may_save_library, hint=hint, save_cats=save_cats)}</div>')


# =============================================================================
# THE PRINTED COVER
# =============================================================================

# Shares VIEW_DOC_STYLES' tokens (--rule-box, --rule, --fs-*), so it adds no
# typeface, size or border weight. `break-after:page` ends the cover's page;
# the letterhead above it is the page frame's repeating <thead>.
SUMMARY_CSS = """
<style>
  .ps-cover { break-after:page; page-break-after:always; }
  .ps-title { border:var(--rule-box); padding:4px 6px; text-align:center;
              font-weight:700; font-size:var(--fs-lg); letter-spacing:.02em;
              -webkit-print-color-adjust:exact; print-color-adjust:exact;
              background:#c9c9c9; }
  .ps-to { margin:4mm 0 2mm; font-size:var(--fs-md); white-space:pre-line; }
  .ps-to b { font-weight:700; }
  .ps-subject { text-align:center; font-weight:700; font-size:var(--fs-md);
                margin:2mm 0 3mm; text-decoration:underline; }
  .ps-table { width:100%; border-collapse:collapse; table-layout:fixed;
              font-size:var(--fs-sm); }
  .ps-table th, .ps-table td { border:var(--rule); padding:3px 5px;
              font-family:inherit; font-size:var(--fs-sm); color:var(--doc-ink);
              text-transform:none; letter-spacing:normal; vertical-align:top; }
  .ps-table th { background:#c9c9c9; font-weight:700; text-align:center;
                 -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  .ps-table col.ps-c-sr  { width:16mm; }
  .ps-table col.ps-c-amt { width:38mm; }
  .ps-table .ps-sr  { text-align:center; }
  .ps-table .ps-amt { text-align:right; white-space:nowrap;
                      font-variant-numeric:tabular-nums; }
  .ps-table tr.ps-tot td { font-weight:700; border-top:var(--rule-box); }
  /* QUOTATION_STYLES' bare `tbody tr:last-child td { border-bottom:none }`
     would leave the last total open at the foot; restated, one class higher. */
  .ps-table tbody tr:last-child td { border-bottom:var(--rule); }
  .ps-table .ps-lbl { text-align:right; }
  .ps-band { margin-top:3mm; border:var(--rule-box); padding:3px 6px;
             text-align:center; font-weight:700; font-size:var(--fs-md); }
  .ps-terms { margin-top:4mm; font-size:var(--fs-sm); }
  .ps-terms-h { font-weight:700; text-decoration:underline; margin-bottom:1.5mm; }
  .ps-terms ol { margin:0; padding-left:6mm; }
  .ps-terms li { margin:0 0 1mm; text-align:justify; }
  @media print { .ps-table tr { break-inside:avoid; page-break-inside:avoid; } }
</style>
"""


def summary_html(*, title: str, to_name: str, subject: str, heads: list,
                 rows: list, totals: list, tax_line: str, terms: list,
                 notes: list = None) -> str:
    """
    The cover, as one block for the top of the page frame's <tbody>.

    `heads`  the amount column heads, e.g. ["Supply Amount", "Installation
             Amount"]; ["Supply + Installation (SITC)"]; ["Amount"].
    `rows`   `(sr, description, [amount strings])`, one per section.
    `totals` `(label, [amount strings])`, each as wide as `heads`; a cell of
             None is drawn empty.
    `tax_line` "" when the document already prints its tax (the quotation
             with GST): the tax is then one of `totals`, never this band.
    `notes`  `(label, value)` lines under the numbered terms, only the filled
             ones (the quotation's own delivery / dispatch / validity, 26 Nov
             2026). Styled on the element, so no stylesheet moves.

    Every text argument is RAW and escaped here; every amount is already
    formatted by the chain and contains only digits, commas, a point and a
    sign, so it is printed as it is.
    """
    n = len(heads)
    cols = ('<colgroup><col class="ps-c-sr"/><col/>'
            + '<col class="ps-c-amt"/>' * n + '</colgroup>')
    th = ('<tr><th>Sr. No.</th><th>System Description</th>'
          + "".join(f"<th>{P.esc(h)}</th>" for h in heads) + "</tr>")
    body = ""
    for sr, desc, amts in rows:
        body += (f'<tr><td class="ps-sr">{P.esc(sr)}</td><td>{P.esc(desc)}</td>'
                 + "".join(f'<td class="ps-amt">{a if a is not None else ""}</td>'
                           for a in amts) + "</tr>")
    for label, amts in totals:
        body += (f'<tr class="ps-tot"><td class="ps-lbl" colspan="2">{P.esc(label)}</td>'
                 + "".join(f'<td class="ps-amt">{a if a is not None else ""}</td>'
                           for a in amts) + "</tr>")
    to_html = (f'<div class="ps-to"><b>To,</b>\n{P.esc(to_name)}</div>'
               if (to_name or "").strip() else '<div class="ps-to"><b>To,</b></div>')
    subj = (f'<div class="ps-subject">{P.esc(subject)}</div>'
            if (subject or "").strip() else "")
    band = f'<div class="ps-band">{P.esc(tax_line)}</div>' if (tax_line or "").strip() else ""
    terms_html = ""
    if terms:
        items = "".join(f"<li>{P.esc(t)}</li>" for t in terms)
        terms_html = (f'<div class="ps-terms"><div class="ps-terms-h">'
                      f'Terms &amp; Condition :-</div><ol>{items}</ol></div>')
    notes_html = ""
    filled = [(lb, v) for lb, v in (notes or []) if str(v or "").strip()]
    if filled:
        notes_html = ('<div class="ps-notes" style="margin-top:2mm;font-size:var(--fs-sm);">'
                      + "".join(f'<div><b>{P.esc(lb)}:</b> {P.esc(v)}</div>'
                                for lb, v in filled) + "</div>")
    return (f'\n<div class="ps-cover">'
            f'<div class="ps-title">{P.esc(title)}</div>{to_html}{subj}'
            f'<table class="ps-table">{cols}<thead>{th}</thead>'
            f'<tbody>{body}</tbody></table>{band}{terms_html}{notes_html}</div>\n')


def section_letter(i: int) -> str:
    """A, B, ... Z, AA, AB: the summary's Sr. No. when a section has no code."""
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# =============================================================================
# THE ORIENTATION SWITCH (screen only)
# =============================================================================

def orientation_toolbar(action_url: str, current: str, may_change: bool) -> str:
    """Portrait / Landscape, as two buttons in one POST form, in the page's
    `.no-print` action bar. Without the permission it is a plain label."""
    if not may_change:
        return (f'<span class="no-print" style="font-size:.8rem;color:var(--muted);'
                f'align-self:center;">Prints {P.esc(current)}</span>')

    def btn(v, lbl):
        on = v == current
        style = ("background:var(--brand);color:#fff;border-color:var(--brand);"
                 if on else "")
        pressed = ' aria-pressed="true"' if on else ""
        return (f'<button type="submit" name="{FIELD_ORIENT}" value="{v}" '
                f'class="btn btn-ghost" style="{style}"{pressed}>{lbl}</button>')
    return (f'<form method="POST" action="{P.esc(action_url)}" class="no-print" '
            f'style="display:flex;gap:.3rem;margin:0;" '
            f'title="The orientation the whole print follows, saved on this document">'
            f'{btn(PORTRAIT, "Portrait")}{btn(LANDSCAPE, "Landscape")}</form>')
