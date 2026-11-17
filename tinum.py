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
FIELD = "tax_invoice_ref"      # the posted box's name on every TI form
MAX_LEN = 64                   # a cap on what is stored, not a GST rule

# Every place a tax invoice number is stored: (collection, field, what it is).
SOURCES = (
    ("invoices",   "ref",             "Tax invoice"),
    ("ra_bills",   "tax_invoice_ref", "RA bill"),
    ("merged_ras", "tax_invoice_ref", "Merged RA"),
)

# ── The KINDS (17 Nov 2026, §0 eightieth block) ─────────────────────────────
# The same free-format rule for the purchase order and the delivery challan.
# A duplicate is refused within the SAME kind only (PO vs PO, DC vs DC). The
# `ti` entry is hotfix 4's behaviour exactly, and every default below is it.
DOC_FIELD = "doc_number"
NUMBER_HISTORY_KEY = "number_history"
KINDS = {
    "ti": {"sources": SOURCES, "noun": "tax invoice number", "field": FIELD,
           "history": HISTORY_KEY, "title": "Tax invoice number changes",
           "blank": "type the number Tally gave."},
    "po": {"sources": (("purchases", "ref", "Purchase order"),),
           "noun": "purchase order number", "field": DOC_FIELD,
           "history": NUMBER_HISTORY_KEY, "title": "Purchase order number changes",
           "blank": "type the number you want."},
    "dc": {"sources": (("delivery_challans", "ref", "Delivery challan"),),
           "noun": "challan number", "field": DOC_FIELD,
           "history": NUMBER_HISTORY_KEY, "title": "Challan number changes",
           "blank": "type the number you want."},
}


def norm(value) -> str:
    """Trimmed, case-insensitive — the comparison the duplicate rule uses."""
    return str(value or "").strip().casefold()


def is_cancelled(rec) -> bool:
    """The modules' own test, read raw (this leaf may import none of them)."""
    return str((rec or {}).get("status") or "").strip().lower() == "cancelled"


def _label(coll: str, rec: dict, what: str) -> str:
    if coll == "ra_bills":
        return f"{what} RA{rec.get('ra_no') or ''} ({rec.get('ref') or ''})"
    return f"{what} {rec.get('tax_invoice_ref') or rec.get('ref') or ''}".strip()


def holder_of(value, *, coll: str = "", rec_id: str = "", kind: str = "ti"):
    """
    The label of the OTHER live document of this kind already carrying this
    number, or "". `coll` / `rec_id` name the document being saved, which
    never collides with itself.
    """
    want = norm(value)
    if not want:
        return ""
    for c, field, what in KINDS[kind]["sources"]:
        for rid, rec in (STORE.get(c) or {}).items():
            if c == coll and rid == rec_id:
                continue
            if is_cancelled(rec) or norm(rec.get(field)) != want:
                continue
            return _label(c, rec, what)
    return ""


def validate(raw, *, current: str = "", coll: str, rec_id: str = "",
             may: bool = True, required: bool = True, kind: str = "ti") -> tuple:
    """
    `(value, error)` for a typed document number of this `kind`.

    * blank — refused when `required` (an edit), else `("", "")`: the caller
      mints its automatic number as it always did (a create);
    * unchanged from `current` (compared trimmed, case-insensitively) —
      accepted as it stands, with no duplicate check, so a record carrying a
      legacy collision is never locked out of its other edits;
    * changed without `may` — refused (a login whose BLOCK list names
      `docnum.override`);
    * longer than `MAX_LEN` — refused;
    * on another live document of the same kind — refused, naming it.
    """
    k = KINDS[kind]
    noun = k["noun"]
    value = str(raw if raw is not None else "").strip()
    if not value:
        return "", (f"The {noun} cannot be blank — {k['blank']}" if required else "")
    if any(ord(ch) < 32 for ch in value):
        return str(current or ""), f"The {noun} has a character it may not carry."
    if norm(value) == norm(current):
        return str(current or "").strip() or value, ""
    if not may:
        return str(current or ""), (f"You may not set a {noun} by hand, so it "
                                    f"stays as it is.")
    if len(value) > MAX_LEN:
        return value, (f"A {noun} of {len(value)} characters is too long; the "
                       f"limit here is {MAX_LEN}.")
    held = holder_of(value, coll=coll, rec_id=rec_id, kind=kind)
    if held:
        return value, (f"{noun[0].upper() + noun[1:]} {value} is already on {held}. "
                       f"A number may be used once; correct one of the two.")
    return value, ""


def record_change(rec: dict, old, new, actor_id: str, kind: str = "ti") -> bool:
    """Append `{old, new, by, at}` — only when the number actually moved."""
    old_s, new_s = str(old or ""), str(new or "")
    if old_s == new_s:
        return False
    rec.setdefault(KINDS[kind]["history"], []).append({
        "old": old_s, "new": new_s, "by": str(actor_id or ""),
        "at": datetime.datetime.now().replace(microsecond=0).isoformat(" "),
    })
    return True


def field_html(value: str = "", *, may: bool = True, label: str = "Tax Invoice No.",
               hint: str = "", kind: str = "ti") -> str:
    """The free-text box. Styled on the element: the sheets around it are pinned."""
    name = KINDS[kind]["field"]
    ro = "" if may else " readonly"
    note = hint or ("The number Tally Prime gave, exactly as Tally prints it. "
                    "It may be corrected later; a number already on another "
                    "live tax invoice is refused.")
    return (f'<div class="form-group" style="max-width:22rem;margin:.6rem 0;">'
            f'<label for="{name}">{label}</label>'
            f'<input type="text" id="{name}" name="{name}" value="{P.esc(value)}" '
            f'maxlength="{MAX_LEN}" autocomplete="off"{ro}/>'
            f'<div style="font-size:.78rem;color:var(--muted);margin-top:.25rem;">'
            f'{note}</div></div>')


def history_html(rec: dict, kind: str = "ti") -> str:
    """The changes, for the VIEW page only. "" when there are none."""
    k = KINDS[kind]
    rows = (rec or {}).get(k["history"]) or []
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
            f'<b>{k["title"]}</b> (screen only, never printed)'
            f'<ul style="margin:.3rem 0 0 1.1rem;">{items}</ul></div>')


def keep_counter(series_key: str, fy: str, change) -> None:
    """
    Apply `change()` — a rename — without letting the automatic series move
    BACK (17 Nov 2026, §0 eightieth block).

    The scanned series (`series.py`) count a stored number; renaming the
    highest one to a free-format value would drop the scan and let the minter
    issue that number again. So the next number is read before and after, and
    when it fell, the series FLOOR for that year is set to what it was — the
    existing mechanism, shown at /settings. Never lowers anything.
    """
    import series as SER   # a leaf, like this one
    before = SER.next_seq(series_key, fy)
    change()
    if SER.next_seq(series_key, fy) < before:
        SER.save_floor(series_key, SER.BY_KEY[series_key].scope_for(fy), before)
