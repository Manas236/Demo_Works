"""
The HSN/SAC code on a document line — ONE rule, one predicate, one page shape.
A LEAF (29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, A1).

The rule, in one line
---------------------

    any code while the document is a DRAFT; from issued onward, only a BLANK
    one may be FILLED

That is Manas's 26 October 2026 ruling, and it is **not new here**: `1fdc09e`
(28 October 2026) already built it for an issued purchase order's item lines
and wrote it down as `purchase.hsn_editable()`. This module is that one
predicate generalised, not a second one — `purchase.py` reads `editable()`
from here and its answer for a purchase order is unchanged, which is what
keeps `tests/test_po_hsn_edit.py` green with its assertions exactly as they
stand.

Why one predicate and not a check per page
------------------------------------------
Two of them is how a form that draws an editable box meets a POST that
refuses it. `editable()` is read by **both** halves at every one of the six
surfaces: the box the page draws (read-only, with the reason in its
`title`) and the refusal the POST gives (`refusal()`), so the two cannot
disagree. The server is the one that decides: a `readonly` attribute is a
courtesy, and `apply_post()` re-asks the predicate for every value it is
handed.

**Nothing is written unless everything passes.** A POST that carries one
refused code changes nothing at all, including the codes beside it that would
have been accepted. That is `purchase._reprice()`'s own staging contract and
`boq._clean_lines()`'s; a half-applied fill is worse than a refused one
because nobody can tell which half landed.

Where a blank code PRINTS as a dash
-----------------------------------
`print_cell()` is the one printed HSN/SAC cell in the application. A blank
code prints **`&mdash;`**, substituted after escaping, which is this repo's
house fallback (`tests/test_entity_fallbacks.py`).

⚠ **It replaces `branding.field()`'s amber *add HSN* chip, and that is an
  INTENDED print change.** That chip is for a statutory detail the company has
  not filled in at `/settings` — a GSTIN, a PAN, an IFSC — where the only
  answer is for somebody to go and type it. A line's missing HSN stopped being
  that on the day this module shipped: it is fillable on the document itself.
  `branding.field()` is **unchanged** and still draws the chip everywhere else
  it is used; only the HSN cell stops calling it.

**The note that says a code is missing is SCREEN ONLY** — `screen_note()`,
drawn on a view page, never inside `print_cell()` and never on a sheet. A
customer's copy of an invoice should carry the code or a dash; it has no
business carrying our own to-do list.

The trail
---------
⚠ **ONE field, `hsn_trail`, written from one place** — `_log()`. Who, when,
which line, which code, what value. Appended, never edited, never deleted;
the shape `auth.py`'s `access_history` and `projtag.py`'s `project_trail`
already use. A record with no key has never had a code filled by hand and
nothing is backfilled.

⚠ **`purchase.py` ALSO keeps its own `status_history` line**, because it has a
trail of its own and `1fdc09e` already writes to it. That is the opposite
call from `projtag.py`'s (which refused to write four shapes), and
deliberately: there is one shape here, and a purchase order's own history
panel is where somebody looking at that order will look. The two are two
records of one event and neither restates the other.

Import direction — a LEAF
-------------------------
    hsnfill.py ──► pipeline.py  esc  —  AND NOTHING ELSE AT ALL

Imports **nothing else of ours**, and no document module imports back into it
— `boq.py`, `spec.py`, `proforma.py`, `invoice.py`, `ra.py`, `merged_ra.py`,
`purchase.py` and `po_draft.py` all import this one. It is `lineimage.py`'s
position in the graph, and for the same reason: a leaf handed a record knows
nothing about the document it belongs to, so the rule cannot acquire a
per-document exception by accident. `tests/test_import_directions.py` holds
it as a whitelist.

⚠ **It may not import `branding.py`.** The whole point of `print_cell()` is
  that it does *not* reach the amber chip, and an arrow to the module that
  owns the chip is how that comes back.

⚠ **It does not import `store` either, and that is the sharper half.** It
  reads **no collection**: every record it writes to is handed to it by the
  route that owns that record. A leaf that could reach `STORE` could learn
  which document it was on, and the rule would start acquiring per-document
  exceptions. `lineimage.py` needs `STORE` for the library default and
  `series.py` needs it for the scan; this needs neither.
"""

import hashlib
from datetime import datetime

import pipeline as P


# =============================================================================
# THE RULE
# =============================================================================

# The longest code GST knows is an 8-digit HSN; a SAC is 6. One cap, the one
# `purchase._parse_extra_lines()` has always used for its `extra_hsn` box.
HSN_MAX = 8


def clean(typed) -> str:
    """A posted code as it would be stored — stripped and capped, never validated.

    ⚠ **Deliberately NOT validated against a tariff.** No code path in this
      application ever has: the catalogue did not, `spec._valid_tax_code()`
      only checks the SHAPE, and a line whose code is refused is a line that
      cannot be billed at all. The cap and the escaping are the guard.
    """
    return str(typed if typed is not None else "").strip()[:HSN_MAX]


def stored(line: dict, field: str) -> str:
    """The code a line carries under `field`, stripped. "" means blank."""
    return str((line or {}).get(field) or "").strip()


def editable(is_draft: bool, current) -> bool:
    """
    May this code be changed?  **The one predicate.**

    `True` while the document is a draft — nothing has gone to a customer or a
    vendor, so the code is ours. `True` on a blank code whatever the state —
    that is the *fill*, and it is the whole feature. `False` on a code that is
    already printed on an issued document, which is never overwritten.
    """
    return bool(is_draft) or not str(current or "").strip()


def refusal(label: str, current: str, noun: str = "document") -> str:
    """The sentence a refused change gets. `purchase._reprice()`'s wording."""
    return (f"The code for {label} is already printed as {current} and this "
            f"{noun} is no longer a draft, so it cannot be changed. Only a "
            f"blank code can be filled in.")


# =============================================================================
# THE PRINTED CELL
# =============================================================================

def print_cell(code) -> str:
    """
    One printed HSN/SAC cell's contents — the code, or an em-dash.

    `esc(x) or '&mdash;'` and never `esc(x or '&mdash;')`: the second escapes
    the entity into visible text, which is the mistake
    `tests/test_entity_fallbacks.py` exists to catch.
    """
    return P.esc(str(code or "").strip()) or "&mdash;"


# =============================================================================
# THE LINE
# =============================================================================
#
# A line is addressed by its POSITION plus a FINGERPRINT of what it says —
# `lineimage.py`'s key, used again for the same reason. A page opened before
# the document changed underneath it then refuses rather than writing a code
# onto whichever line has since moved into that slot.

def fingerprint(text) -> str:
    """A short hash of a line's description, posted beside its position."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def entry(key: str, sno, label: str, description: str, line: dict,
          field: str = "hsn", code_label: str = "HSN") -> dict:
    """
    One fillable code: where it is, what it says, and which key holds it.

    `field` is the document's own key — `hsn` on a proforma, a tax invoice and
    a purchase order line, `hsn_sac` on an RA claim, and `supply_hsn` /
    `install_sac` on a BOQ line, which is the one record that carries **two**
    codes and therefore two entries per line.
    """
    return {"key": key, "sno": sno, "label": str(label or ""),
            "description": str(description or ""), "line": line,
            "field": field, "code_label": code_label}


def value_of(e: dict) -> str:
    return stored(e["line"], e["field"])


def missing(entries: list) -> list:
    """The labels of the entries with no code, de-duplicated, order kept."""
    seen, out = set(), []
    for e in entries:
        if value_of(e):
            continue
        name = e["label"] or e["description"][:60] or f"line {e['sno']}"
        tag = f"{name} ({e['code_label']})" if e["code_label"] != "HSN" else name
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


# =============================================================================
# THE TRAIL
# =============================================================================

TRAIL_FIELD = "hsn_trail"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _log(rec: dict, e: dict, value: str, who: str) -> dict:
    """
    Append one entry to this record's HSN trail — who, when, line, code, value.

    ⚠ **Appended and never edited.** The line's own label and description are
      snapshotted beside the position for the reason every snapshot in this
      app exists: the trail has to still read correctly after a reprice has
      reordered the lines, and a position alone would then say nothing.
    """
    entry_row = {
        "at":    _now(),
        "by":    str(who or "").strip() or "unknown",
        "line":  str(e.get("sno") or ""),
        "label": e["label"] or e["description"][:80],
        "field": e["field"],
        "code":  e["code_label"],
        "value": value,
    }
    rec.setdefault(TRAIL_FIELD, []).append(entry_row)
    return entry_row


def trail_of(rec: dict) -> list:
    """This record's HSN trail, newest first. `[]` on a record never filled."""
    return list(reversed((rec or {}).get(TRAIL_FIELD) or []))


def trail_html(rec: dict) -> str:
    """The trail as the view page draws it. "" when nothing has been filled."""
    rows = trail_of(rec)
    if not rows:
        return ""
    out = ""
    for r in rows:
        out += (f'<div class="hf-trail-row">'
                f'<span class="hf-at">{P.esc(r.get("at"))}</span>'
                f'<span class="hf-by">{P.esc(r.get("by"))}</span>'
                f'<span class="hf-note">{P.esc(r.get("code"))} '
                f'<b>{P.esc(r.get("value")) or "(cleared)"}</b> on '
                f'{P.esc(r.get("label"))}</span></div>')
    return ('<div class="hf-trail"><div class="hf-trail-t">Codes filled on '
            f'this document</div>{out}</div>')


# =============================================================================
# THE SCREEN NOTE — never printed
# =============================================================================

NOTE_CSS = """<style>
  /* hsnfill.py — the screen-only "a code is missing" note and the fill page.
     ⚠ Never loaded by a print route and never inside the sheet's own styles:
        this note does not go to a customer. */
  .hf-note { border:1px solid #f59e0b; background:#fffbeb; color:#78350f;
             border-radius:8px; padding:.6rem .8rem; margin:0 0 1rem;
             font-size:.84rem; line-height:1.55; }
  .hf-note b { font-weight:700; }
  .hf-note a { color:#78350f; font-weight:600; }
  .hf-note ul { margin:.35rem 0 0; padding-left:1.1rem; }
  .hf-table { width:100%; border-collapse:collapse; font-size:.86rem; }
  .hf-table th { text-align:left; font-size:.72rem; text-transform:uppercase;
                 letter-spacing:.04em; color:var(--muted); padding:.5rem .6rem;
                 border-bottom:1px solid var(--border, #e5e7eb); }
  .hf-table td { padding:.55rem .6rem; border-bottom:1px solid var(--border, #e5e7eb);
                 vertical-align:middle; }
  .hf-table input[type=text] { width:9rem; font-family:ui-monospace,monospace; }
  .hf-table input[readonly] { background:#f3f4f6; color:var(--muted); }
  .hf-desc { max-width:520px; overflow-wrap:anywhere; }
  .hf-lbl { color:var(--muted); font-size:.76rem; }
  .hf-ro { font-size:.72rem; color:var(--muted); }
  .hf-trail { margin-top:1.4rem; font-size:.82rem; }
  .hf-trail-t { font-size:.72rem; text-transform:uppercase; letter-spacing:.04em;
                color:var(--muted); margin-bottom:.4rem; }
  .hf-trail-row { display:grid; grid-template-columns:9.5rem 8rem 1fr; gap:.5rem;
                  padding:.3rem 0; border-top:1px solid var(--border, #e5e7eb); }
  .hf-at, .hf-by { color:var(--muted); font-size:.78rem; }
  @media (max-width:620px) {
    .hf-table thead { display:none; }
    .hf-table tr { display:block; border-bottom:1px solid var(--border, #e5e7eb); }
    .hf-table td { display:block; border:0; padding:.3rem .2rem; }
    .hf-trail-row { grid-template-columns:1fr; }
  }
</style>"""


def screen_note(entries: list, fill_url: str = "", noun: str = "document") -> str:
    """
    The note naming the lines with no code. **Screen only, never printed.**

    "" when every line has one, which is what keeps it off a document that
    needs nothing — and off every page golden captured against a complete one.
    """
    gaps = missing(entries)
    if not gaps:
        return ""
    items = "".join(f"<li>{P.esc(g)}</li>" for g in gaps)
    n = len(gaps)
    link = (f' <a href="{fill_url}">Fill them in</a>.' if fill_url else "")
    return (f'<div class="hf-note"><b>HSN/SAC is missing on '
            f'{n} line{"" if n == 1 else "s"}.</b> Rule 46 makes it mandatory '
            f'on a tax invoice, and the customer cannot claim input tax credit '
            f'on a line without one. It prints as a dash.{link}'
            f'<ul>{items}</ul>'
            f'<span class="hf-ro">This note is on screen only &mdash; it is '
            f'never printed on the {P.esc(noun)}.</span></div>')


# =============================================================================
# THE FILL PAGE — what every document's page shares
# =============================================================================
#
# Each document owns its route, its permission and its page shell; this owns
# the rows and the POST. `lineimage.py`'s arrangement exactly.

def rows_html(entries: list, action: str, is_draft: bool,
              may_edit: bool = True) -> str:
    """
    The fill page's table — one row per fillable code, in one form.

    A code the predicate refuses is drawn **read-only with the reason in its
    `title`**, never as an editable box that produces a refusal: a control
    that can only fail is not drawn (the owner's 22 September rule).

    `may_edit` False draws the codes and no form at all — for a document whose
    own lifecycle refuses the whole page (a cancelled one).
    """
    body = ""
    for e in entries:
        cur = value_of(e)
        ro = not editable(is_draft, cur)
        fp = fingerprint(e["description"])
        box = (f'<input type="hidden" name="k" value="{P.esc(e["key"])}"/>'
               f'<input type="hidden" name="fp_{P.esc(e["key"])}" value="{fp}"/>'
               f'<input type="text" name="v_{P.esc(e["key"])}" '
               f'value="{P.esc(cur)}" maxlength="{HSN_MAX}" '
               f'placeholder="{P.esc(e["code_label"])}" '
               f'aria-label="{P.esc(e["code_label"])} for line {P.esc(e["sno"])}"'
               + (' readonly title="Already printed on a document that is no '
                  'longer a draft, so it stays as it is."' if ro else "")
               + "/>") if may_edit else f'<b>{print_cell(cur)}</b>'
        lbl = (f'<div class="hf-lbl">{P.esc(e["label"])}</div>'
               if e["label"] else "")
        body += f"""
        <tr>
          <td>{P.esc(e["sno"])}</td>
          <td class="hf-desc">{lbl}{P.esc(e["description"])}</td>
          <td>{P.esc(e["code_label"])}</td>
          <td>{box}{'<div class="hf-ro">printed &mdash; read-only</div>' if ro and may_edit else ''}</td>
        </tr>"""
    if not body:
        body = ('\n        <tr><td colspan="4" class="hf-ro">This document has '
                'no line that can carry an HSN/SAC code.</td></tr>')
    return f"""
    <table class="hf-table">
      <thead><tr><th>S.No</th><th>Line</th><th>Code</th><th>HSN / SAC</th></tr></thead>
      <tbody>{body}
      </tbody>
    </table>"""


def apply_post(form, entries: list, is_draft: bool, rec: dict,
               who: str = "", noun: str = "document") -> tuple:
    """
    `(message, error)` for one fill POST. Exactly one of the two is "".

    **Staged.** Every posted code is read and checked first; only when all of
    them pass is anything written. A refused value leaves the document exactly
    as it was, codes and all.

    A key the form did not carry is **left as it is** — a tab opened before a
    box existed, and `purchase._reprice()`'s own rule for a stale form.
    """
    by_key = {e["key"]: e for e in entries}
    staged = []
    for key in form.getlist("k"):
        e = by_key.get(str(key))
        if e is None:
            return "", "That line is not on this document. Nothing was changed."
        if str(form.get(f"fp_{key}") or "") != fingerprint(e["description"]):
            return "", ("This document changed after the page was opened, so "
                        "nothing was saved. The page below is current — try "
                        "again.")
        typed = clean(form.get(f"v_{key}"))
        cur = value_of(e)
        if typed == cur:
            continue
        if not editable(is_draft, cur):
            label = e["label"] or e["description"][:60] or f"line {e['sno']}"
            return "", refusal(f"{label} ({e['code_label']})", cur, noun)
        staged.append((e, typed))

    if not staged:
        return "Nothing changed, so nothing was recorded.", ""

    for e, typed in staged:
        e["line"][e["field"]] = typed
        _log(rec, e, typed, who)
    n = len(staged)
    return (f"HSN/SAC updated on {n} line{'' if n == 1 else 's'}."), ""
