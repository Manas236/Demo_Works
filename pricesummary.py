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

# Per-document keys.
FIELD_ON = "price_summary_on"
FIELD_TERMS = "summary_terms"
FIELD_ORIENT = "print_orientation"
MARK_ON = "price_summary_present"     # the form offered the tick
FIELD_TERM = "summary_term"           # one posted <input> per term, in order
MARK_TERMS = "summary_terms_present"  # the form offered the editor

# The quotation's two (it has no project name and no sections): the cover's
# subject line and its one row's System Description. Blank prints a default
# the quotation derives (`quotation._summary_cover()`).
FIELD_SUBJECT = "summary_subject"
FIELD_SYSTEM = "summary_system"

PORTRAIT, LANDSCAPE = "portrait", "landscape"
ORIENTATIONS = (PORTRAIT, LANDSCAPE)

MAX_TERMS = 60
MAX_TERM_CHARS = 1000
MAX_TEXT_CHARS = 200


# =============================================================================
# THE /settings RECORD
# =============================================================================

def ensure_seeded() -> None:
    """Seed the record with the client's defaults when it is ABSENT. A record
    that exists, however it was edited (an emptied list included), is never
    touched. A genuine default, seeded whatever SAMRUDDHI_DEMO_DATA says."""
    if RECORD not in STORE["settings"]:
        STORE["settings"][RECORD] = {"title": DEFAULT_TITLE,
                                     "tax_line": DEFAULT_TAX_LINE,
                                     "terms": list(DEFAULT_TERMS)}


def settings_of() -> dict:
    """`{"title", "tax_line", "terms"}`: the stored record, or the defaults
    when none is stored. A blank title or tax line reads as its default."""
    rec = STORE["settings"].get(RECORD)
    if not isinstance(rec, dict):
        return {"title": DEFAULT_TITLE, "tax_line": DEFAULT_TAX_LINE,
                "terms": list(DEFAULT_TERMS)}
    terms = rec.get("terms")
    return {"title": str(rec.get("title") or "").strip() or DEFAULT_TITLE,
            "tax_line": str(rec.get("tax_line") or "").strip() or DEFAULT_TAX_LINE,
            "terms": clean_terms(terms) if isinstance(terms, list) else []}


def save_settings(title: str, tax_line: str, terms: list) -> None:
    STORE["settings"][RECORD] = {"title": str(title or "").strip()[:MAX_TEXT_CHARS],
                                 "tax_line": str(tax_line or "").strip()[:MAX_TEXT_CHARS],
                                 "terms": clean_terms(terms)}


def default_terms() -> list:
    """A COPY of the current default list, for a document being created."""
    return list(settings_of()["terms"])


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


def apply_form(doc: dict, form, creating: bool) -> None:
    """Write the tick and the terms from a document's own form onto `doc`.
    On create the terms default to a copy of /settings; on edit to what the
    record holds."""
    doc[FIELD_ON] = form_on(form, legacy=is_on(doc))
    legacy = default_terms() if creating else (
        terms_of(doc) if has_terms(doc) else None)
    if legacy is None and (form is None or form.get(MARK_TERMS) is None):
        return            # an old record edited by a form without the editor
    doc[FIELD_TERMS] = form_terms(form, legacy or [])


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
  .ps-ed-btn { font-size:.75rem; padding:.3rem .5rem; border-radius:6px;
               border:1px solid var(--border, #e2e8f0); background:#fff; cursor:pointer; }
  .ps-ed-btn:hover { background:#eef2ff; }
</style>
"""

# Plain string, interpolated as a value: nothing in it needs doubling.
EDITOR_JS = """
<script>
(function () {
  if (window.psEd) return;
  function renum(box) {
    var rows = box.querySelectorAll('.ps-ed-row');
    for (var i = 0; i < rows.length; i++) {
      rows[i].querySelector('.ps-ed-no').textContent = (i + 1) + '.';
    }
  }
  window.psEd = function (btn, act) {
    var row = btn.closest('.ps-ed-row');
    var box = btn.closest('.ps-ed');
    if (act === 'add') {
      var tpl = box.querySelector('template');
      var list = box.querySelector('.ps-ed-list');
      list.appendChild(tpl.content.cloneNode(true));
      var all = list.querySelectorAll('textarea');
      if (all.length) all[all.length - 1].focus();
    } else if (act === 'del') {
      row.parentNode.removeChild(row);
    } else if (act === 'up' && row.previousElementSibling) {
      row.parentNode.insertBefore(row, row.previousElementSibling);
    } else if (act === 'down' && row.nextElementSibling) {
      row.parentNode.insertBefore(row.nextElementSibling, row);
    }
    renum(box);
  };
})();
</script>
"""


def _editor_row(i: int, text: str) -> str:
    return (f'<div class="ps-ed-row"><span class="ps-ed-no">{i}.</span>'
            f'<textarea name="{FIELD_TERM}" rows="2">{P.esc(text)}</textarea>'
            f'<button type="button" class="ps-ed-btn" title="Move up" '
            f'onclick="psEd(this,&#39;up&#39;)">&#8593;</button>'
            f'<button type="button" class="ps-ed-btn" title="Move down" '
            f'onclick="psEd(this,&#39;down&#39;)">&#8595;</button>'
            f'<button type="button" class="ps-ed-btn" title="Remove" '
            f'onclick="psEd(this,&#39;del&#39;)">&#10005;</button></div>')


def editor_html(terms: list, label: str = "Terms &amp; Conditions") -> str:
    """An ordered, editable list: add, remove, move up, move down. Posts one
    `summary_term` per row, in order, with a marker so an emptied list is told
    apart from a form that never offered the editor. No `{` or `}` in the
    markup, so it can sit in an f-string or a `.format()` page as a value."""
    rows = "".join(_editor_row(i + 1, t) for i, t in enumerate(terms or []))
    return (f'{EDITOR_CSS}<div class="form-group ps-ed">'
            f'<input type="hidden" name="{MARK_TERMS}" value="1"/>'
            f'<label>{label}</label>'
            f'<div class="ps-ed-list">{rows}</div>'
            f'<template>{_editor_row(0, "")}</template>'
            f'<button type="button" class="ps-ed-btn" onclick="psEd(this,&#39;add&#39;)">'
            f'+ Add a term</button></div>{EDITOR_JS}')


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


def form_section_html(on: bool, terms: list, extra: str = "") -> str:
    """The whole block a document form draws: the tick, any extra fields the
    caller passes (already escaped), and the terms editor."""
    return (f'<div class="form-section"><div class="section-title">'
            f'&#128209;&nbsp; Price Summary Page</div>'
            f'{checkbox_html(on)}{extra}{editor_html(terms)}</div>')


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
                 rows: list, totals: list, tax_line: str, terms: list) -> str:
    """
    The cover, as one block for the top of the page frame's <tbody>.

    `heads`  the amount column heads, e.g. ["Supply Amount", "Installation
             Amount"]; ["Supply + Installation (SITC)"]; ["Amount"].
    `rows`   `(sr, description, [amount strings])`, one per section.
    `totals` `(label, [amount strings])`, each as wide as `heads`; a cell of
             None is drawn empty.
    `tax_line` "" when the document already prints its tax (the quotation
             with GST): the tax is then one of `totals`, never this band.

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
    return (f'\n<div class="ps-cover">'
            f'<div class="ps-title">{P.esc(title)}</div>{to_html}{subj}'
            f'<table class="ps-table">{cols}<thead>{th}</thead>'
            f'<tbody>{body}</tbody></table>{band}{terms_html}</div>\n')


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
