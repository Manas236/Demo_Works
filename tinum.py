"""
tinum.py — the TAX INVOICE NUMBER as Tally Prime issued it
==========================================================

17 November 2026, CLIENT_CHANGES.md §0 **seventy-ninth** block (prod hotfix 4).

The client's GST invoice series is issued by **Tally Prime**. The number this
system prints on a tax invoice must be whatever Tally gave, in Tally's format
(`SF-3`, `125/26-27`, …), and correctable after the fact. Tally is the master,
so for THIS field:

  * any non-blank value is accepted, trimmed — **not forward-only**;
  * it is settable on create, on a draft's edit and on an ISSUED document's
    edit; a CANCELLED document stays locked (its callers refuse it);
  * a value already carried by ANOTHER live document that holds a tax invoice
    number is **refused**, naming that document. Compared trimmed and
    case-insensitively, across all three places a TI number lives:

        invoices.ref · ra_bills.tax_invoice_ref · merged_ras.tax_invoice_ref

  * every change appends `{old, new, by, at}` to the record's
    `ti_number_history`, drawn on the VIEW page and never printed.

⚠ **A leaf**, for `docnum.py`'s reason: `ra.py` may never import `invoice.py`,
  and a cross-collection check written in either would couple them through the
  basement. This file imports `store` and `pipeline` and reads the three
  collections directly. It asks no permission question: callers pass `may`.

⚠ **The automatic series are untouched.** A record with no typed number gets
  exactly the number it always did. A Tally value is skipped by the
  RA (`/RI/<fy>/`) scan, and by the TI and merged scans unless its last `/`
  segment is all digits, in which case it can only move the next AUTOMATIC
  number forward — never back, never onto a number already used.
"""

import datetime

import pipeline as P
from store import STORE

HISTORY_KEY = "ti_number_history"
FIELD = "tax_invoice_ref"      # the posted box's name on every form
MAX_LEN = 64                   # a cap on what is stored, not a GST rule

# Every place a tax invoice number is stored: (collection, field, what it is).
SOURCES = (
    ("invoices",   "ref",             "Tax invoice"),
    ("ra_bills",   "tax_invoice_ref", "RA bill"),
    ("merged_ras", "tax_invoice_ref", "Merged RA"),
)


def norm(value) -> str:
    """Trimmed, case-insensitive — the comparison the duplicate rule uses."""
    return str(value or "").strip().casefold()


def is_cancelled(rec) -> bool:
    """The three modules' own test, read raw (this leaf may import none of them)."""
    return str((rec or {}).get("status") or "").strip().lower() == "cancelled"


def _label(coll: str, rec: dict, what: str) -> str:
    if coll == "ra_bills":
        return f"{what} RA{rec.get('ra_no') or ''} ({rec.get('ref') or ''})"
    return f"{what} {rec.get('tax_invoice_ref') or rec.get('ref') or ''}".strip()


def holder_of(value, *, coll: str = "", rec_id: str = ""):
    """
    The label of the OTHER live document already carrying this number, or "".
    `coll` / `rec_id` name the document being saved, which never collides
    with itself.
    """
    want = norm(value)
    if not want:
        return ""
    for c, field, what in SOURCES:
        for rid, rec in (STORE.get(c) or {}).items():
            if c == coll and rid == rec_id:
                continue
            if is_cancelled(rec) or norm(rec.get(field)) != want:
                continue
            return _label(c, rec, what)
    return ""


def validate(raw, *, current: str = "", coll: str, rec_id: str = "",
             may: bool = True, required: bool = True) -> tuple:
    """
    `(value, error)` for a typed tax invoice number.

    * blank — refused when `required` (an edit), else `("", "")`: the caller
      mints its automatic number as it always did (a create);
    * unchanged from `current` (compared trimmed, case-insensitively) —
      accepted as it stands, with no duplicate check, so a record carrying a
      legacy collision is never locked out of its other edits;
    * changed without `may` — refused (a login whose BLOCK list names
      `docnum.override`);
    * longer than `MAX_LEN` — refused;
    * on another live document — refused, naming it.
    """
    value = str(raw if raw is not None else "").strip()
    if not value:
        return "", ("The tax invoice number cannot be blank — type the "
                    "number Tally gave." if required else "")
    if any(ord(ch) < 32 for ch in value):
        return str(current or ""), "The tax invoice number has a character it may not carry."
    if norm(value) == norm(current):
        return str(current or "").strip() or value, ""
    if not may:
        return str(current or ""), ("You may not set a tax invoice number by "
                                    "hand, so it stays as it is.")
    if len(value) > MAX_LEN:
        return value, (f"A tax invoice number of {len(value)} characters is too "
                       f"long; the limit here is {MAX_LEN}.")
    held = holder_of(value, coll=coll, rec_id=rec_id)
    if held:
        return value, (f"Tax invoice number {value} is already on {held}. A "
                       f"number may be used once; correct one of the two.")
    return value, ""


def record_change(rec: dict, old, new, actor_id: str) -> bool:
    """Append `{old, new, by, at}` — only when the number actually moved."""
    old_s, new_s = str(old or ""), str(new or "")
    if old_s == new_s:
        return False
    rec.setdefault(HISTORY_KEY, []).append({
        "old": old_s, "new": new_s, "by": str(actor_id or ""),
        "at": datetime.datetime.now().replace(microsecond=0).isoformat(" "),
    })
    return True


def field_html(value: str = "", *, may: bool = True, label: str = "Tax Invoice No.",
               hint: str = "") -> str:
    """The free-text box. Styled on the element: the sheets around it are pinned."""
    ro = "" if may else " readonly"
    note = hint or ("The number Tally Prime gave, exactly as Tally prints it. "
                    "It may be corrected later; a number already on another "
                    "live tax invoice is refused.")
    return (f'<div class="form-group" style="max-width:22rem;margin:.6rem 0;">'
            f'<label for="{FIELD}">{label}</label>'
            f'<input type="text" id="{FIELD}" name="{FIELD}" value="{P.esc(value)}" '
            f'maxlength="{MAX_LEN}" autocomplete="off"{ro}/>'
            f'<div style="font-size:.78rem;color:var(--muted);margin-top:.25rem;">'
            f'{note}</div></div>')


def history_html(rec: dict) -> str:
    """The changes, for the VIEW page only. "" when there are none."""
    rows = (rec or {}).get(HISTORY_KEY) or []
    if not rows:
        return ""
    users = STORE.get("users") or {}
    items = "".join(
        f'<li>{P.esc(r.get("at"))} &mdash; <b>{P.esc(r.get("old") or "(none)")}</b> '
        f'&rarr; <b>{P.esc(r.get("new"))}</b> by '
        f'{P.esc((users.get(r.get("by")) or {}).get("display_name") or r.get("by") or "?")}</li>'
        for r in rows)
    return (f'<div class="no-print" style="border:1px solid #e5e7eb;border-radius:8px;'
            f'padding:.6rem .9rem;margin:0 0 1rem;font-size:.82rem;">'
            f'<b>Tax invoice number changes</b> (screen only, never printed)'
            f'<ul style="margin:.3rem 0 0 1.1rem;">{items}</ul></div>')
