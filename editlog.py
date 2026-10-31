"""
editlog.py — every edit after issue, logged on the record
=========================================================

31 October 2026, CLIENT_CHANGES.md §0 sixty-fourth block (Manas's ruling on
the 28 October "edit every document" ask): an issued tax invoice, a merged
tax invoice, an issued purchase order, an issued work order, a delivery
challan and a proforma invoice may be corrected after they have gone out —
and every such correction is written on the record:

    rec["edit_log"] = [
        {"at": "2026-10-31 14:05:11", "by": "<user id>",
         "field": "Customer GSTIN", "before": "27AAA…", "after": "27AAB…"},
        …
    ]

* **The user's ID, never the display name** — ABOUT.md §7 gap 41. The band
  resolves the name when it is drawn.
* **One entry per field that actually changed.** A save that changes nothing
  writes nothing, so a record that was never edited carries no key at all and
  reads exactly as every record written before this date.
* **The band is SCREEN ONLY.** It is drawn above `.doc-outer`, which
  `docsheet.PRINT_EDGE_CSS` withholds from paper, and it carries its own
  `@media print { display:none }` as well. The printed document never says it
  was edited — the customer's copy is the document, the log is ours.

A LEAF: imports `store` and `pipeline` only.
"""

import datetime

import pipeline as P
from store import STORE

FIELD = "edit_log"


def _now() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat(" ")


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:g}" if v != int(v) else f"{int(v)}"
    return str(v).strip()


def diff(before: dict, after: dict, fields) -> list:
    """`[(label, was, now), …]` for every `(key, label)` whose text changed."""
    out = []
    for key, label in fields:
        was, now = _text(before.get(key)), _text(after.get(key))
        if was != now:
            out.append((label, was, now))
    return out


def line_text(row: dict) -> str:
    """One line, as the log states it — words, quantity, rate, amount."""
    if row.get("is_header"):
        return f"[heading] {_text(row.get('name'))}"
    bits = [_text(row.get("name"))]
    if row.get("make"):
        bits.append(f"make {_text(row.get('make'))}")
    if row.get("hsn"):
        bits.append(f"HSN {_text(row.get('hsn'))}")
    qty = _text(row.get("qty"))
    unit = _text(row.get("unit"))
    bits.append(f"{qty} {unit}".strip())
    bits.append(f"@ {_text(row.get('price'))}")
    if row.get("discount_pct"):
        bits.append(f"less {_text(row.get('discount_pct'))}%")
    if row.get("gst_rate") not in (None, ""):
        bits.append(f"GST {_text(row.get('gst_rate'))}%")
    bits.append(f"= {_text(row.get('total'))}")
    return " · ".join(b for b in bits if b)


def line_diff(before: list, after: list, default_gst=None) -> list:
    """
    Per-position line changes, added and removed lines included.

    `default_gst` is the rate a stored line WITHOUT its own `gst_rate` was
    taxed at (a quotation-shaped document taxes every line at one rate): the
    edit form writes that rate onto each line, and that alone is not a change
    anybody made.
    """
    if default_gst is not None:
        before = [dict(r, gst_rate=default_gst)
                  if not r.get("is_header") and r.get("gst_rate") in (None, "") else r
                  for r in before or []]
    out = []
    for i in range(max(len(before or []), len(after or []))):
        was = line_text(before[i]) if i < len(before or []) else ""
        now = line_text(after[i]) if i < len(after or []) else ""
        if was != now:
            out.append((f"Line {i + 1}", was, now))
    return out


def record(rec: dict, changes: list, actor_id: str) -> int:
    """Append one entry per change. Returns how many were written."""
    if not changes:
        return 0
    at = _now()
    log = rec.setdefault(FIELD, [])
    for label, was, now in changes:
        log.append({"at": at, "by": str(actor_id or ""), "field": str(label),
                    "before": str(was), "after": str(now)})
    return len(changes)


def _who(uid: str) -> str:
    user = (STORE.get("users") or {}).get(str(uid or "")) or {}
    return (str(user.get("name") or user.get("username") or "").strip()
            or (f"user {uid}" if uid else "an unknown user"))


BAND_CSS = """
<style>
  .el-band { margin:0 0 1rem; padding:.75rem 1rem; border:1px solid #f2d994;
             border-left:4px solid #d97706; border-radius:6px; background:#fff8e5;
             color:#7a4b00; font-size:.88rem; }
  .el-band summary { cursor:pointer; font-weight:600; }
  .el-band table { margin-top:.6rem; border-collapse:collapse; width:100%;
                   font-size:.8rem; background:#fff; }
  .el-band th, .el-band td { border:1px solid #f2d994; padding:.3rem .45rem;
                             text-align:left; vertical-align:top; }
  @media print { .el-band { display:none !important; } }
</style>
"""


def band(rec: dict, word: str = "document") -> str:
    """
    The amber screen-only band, or "" for a record never edited after issue.
    The newest entry names the date and the user; the whole log sits behind
    a <details>.
    """
    log = [e for e in (rec.get(FIELD) or []) if isinstance(e, dict)]
    if not log:
        return ""
    last = log[-1]
    rows = "".join(
        f"<tr><td>{P.esc(e.get('at'))}</td><td>{P.esc(_who(e.get('by')))}</td>"
        f"<td>{P.esc(e.get('field'))}</td><td>{P.esc(e.get('before')) or '(blank)'}</td>"
        f"<td>{P.esc(e.get('after')) or '(blank)'}</td></tr>"
        for e in reversed(log))
    return (f'{BAND_CSS}<div class="el-band" role="note"><details>'
            f'<summary>&#9888; Edited after issue on {P.esc(str(last.get("at") or "")[:10])} '
            f'by {P.esc(_who(last.get("by")))} &mdash; {len(log)} change'
            f'{"" if len(log) == 1 else "s"} logged</summary>'
            f'<div style="margin-top:.4rem;">This {P.esc(word)} has been changed since it '
            f'was issued. The log below is on screen only; the printed copy carries '
            f'no band.</div>'
            f'<table><thead><tr><th>When</th><th>Who</th><th>Field</th><th>Before</th>'
            f'<th>After</th></tr></thead><tbody>{rows}</tbody></table>'
            f'</details></div>')
