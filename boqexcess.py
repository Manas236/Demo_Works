"""
boqexcess.py — BILLING ABOVE THE BOQ QUANTITY, allowed and never silent
=======================================================================

17 November 2026, CLIENT_CHANGES.md §0 **eighty-first** block (prod hotfix 6).

The client's rule: billing above the BOQ quantity is normal in their trade —
site measurement exceeds the schedule. So the BOQ-quantity ceiling is no
longer a hard block. When a line's CUMULATIVE claim would pass its BOQ
quantity, the form shows an amber per-line warning (BOQ qty, already claimed,
this claim, excess) and asks for ONE reason for the bill; a blank reason is
refused. Saved, the bill carries:

    excess_lines   [{line_id, item_no, leg, boq_qty, cumulative_after, excess}]
    excess_reason  the text typed

**snapshotted at save and never recomputed**. A bill with no excess carries
NEITHER key, so every record that existed before this block — and every bill
billed within its schedule — is byte-identical, and so is its print.

⚠ **Only the BOQ-quantity ceiling softened** — `ra.overclaims()` reason
  `"overclaim"`. The installation MEASUREMENT cap (`"overmeasured"`,
  `"not_measured"`), a line not in the schedule (`"not_in_boq"`) and the
  RA-from-challans DISPATCHED cap (`ra.dc_overclaims()`) are hard blocks,
  unchanged. `ra.overclaims()` itself is unchanged: it is the detector.

⚠ **The cumulative is DERIVED by summing**, keyed on `line_id` and never on
  `item_no` (the item number is carried only as the label a person reads).

⚠ **A leaf.** It imports `store` and `pipeline` only and reads collections
  raw, because `boq.py` may not import `ra.py` and `invoice.py` may not
  either. The band is SCREEN-ONLY (`no-print`) and drawn above `.doc-outer`;
  it renders "" when there is nothing to say.
"""

import pipeline as P
from store import STORE

LINES_KEY = "excess_lines"
REASON_KEY = "excess_reason"
REASON_FIELD = "excess_reason"     # the posted box's name on every form
REASON_MAX = 500
_EPS = P.QTY_EPSILON   # the one quantity tolerance

_AMBER = ("background:#fffbeb;border:1px solid #fcd34d;color:#78350f;"
          "border-radius:8px;padding:.7rem .9rem;margin:.6rem 0 1rem;"
          "font-size:.85rem;")


def _q(x) -> str:
    """A quantity as people write it: no trailing zeros."""
    v = round(float(x or 0.0), 3)
    return f"{v:,.3f}".rstrip("0").rstrip(".")


def snapshot(rows) -> list:
    """
    The stored shape from the detector's rows. Accepts `ra.overclaims()`'s
    dicts (`approved`, `cumulative`, `over`) or this module's own.
    """
    out = []
    for r in rows or []:
        boq_qty = r.get("boq_qty", r.get("approved"))
        cum = r.get("cumulative_after", r.get("cumulative"))
        exc = r.get("excess", r.get("over"))
        out.append({
            "line_id": str(r.get("line_id") or ""),
            "item_no": str(r.get("item_no") or ""),
            "leg": str(r.get("leg") or ""),
            "boq_qty": round(float(boq_qty or 0.0), 6),
            "previously": round(float(r.get("previously") or 0.0), 6),
            "this": round(float(r.get("this") or 0.0), 6),
            "cumulative_after": round(float(cum or 0.0), 6),
            "excess": round(float(exc or 0.0), 6),
        })
    return out


def read_reason(form) -> str:
    """The typed reason, trimmed and capped; "" when blank or absent."""
    raw = (form.get(REASON_FIELD) if form is not None else "") or ""
    return " ".join(str(raw).split())[:REASON_MAX]


def refusal(rows) -> str:
    """The message for an above-BOQ bill posted with no reason."""
    n = len(rows or [])
    return (f"{n} line{'' if n == 1 else 's'} would be billed above the BOQ "
            f"quantity. That is allowed — give the reason in the amber box "
            f"(“Reason for billing above BOQ”) and save again.")


def stamp(rec: dict, rows: list, reason: str) -> None:
    """Write the snapshot onto `rec`, or remove both keys when there is none."""
    if rows:
        rec[LINES_KEY] = snapshot(rows)
        rec[REASON_KEY] = str(reason or "")
    else:
        rec.pop(LINES_KEY, None)
        rec.pop(REASON_KEY, None)


def warning_html(rows, reason: str = "") -> str:
    """
    The amber per-line warning and the ONE reason box, for the entry form.
    "" when no line is above its BOQ quantity.
    """
    rows = snapshot(rows)
    if not rows:
        return ""
    body = "".join(
        f'<tr><td>{P.esc(r["item_no"]) or "&mdash;"}</td>'
        f'<td>{P.esc(r["leg"])}</td>'
        f'<td style="text-align:right;">{_q(r["boq_qty"])}</td>'
        f'<td style="text-align:right;">{_q(r["previously"])}</td>'
        f'<td style="text-align:right;">{_q(r["this"])}</td>'
        f'<td style="text-align:right;"><b>{_q(r["excess"])}</b></td></tr>'
        for r in rows)
    return (
        f'<div class="boq-excess-warn no-print" style="{_AMBER}">'
        f'<b>&#9888; Billed above BOQ quantity</b> &mdash; allowed, and recorded '
        f'on the bill with your reason.'
        f'<table style="width:100%;margin:.5rem 0;border-collapse:collapse;'
        f'font-size:.82rem;"><thead><tr>'
        f'<th style="text-align:left;">Item</th><th style="text-align:left;">Leg</th>'
        f'<th style="text-align:right;">BOQ qty</th>'
        f'<th style="text-align:right;">Already claimed</th>'
        f'<th style="text-align:right;">This claim</th>'
        f'<th style="text-align:right;">Excess</th></tr></thead>'
        f'<tbody>{body}</tbody></table>'
        f'<label for="{REASON_FIELD}"><b>Reason for billing above BOQ</b> '
        f'(required, one for the whole bill)</label>'
        f'<textarea id="{REASON_FIELD}" name="{REASON_FIELD}" rows="2" '
        f'maxlength="{REASON_MAX}" style="width:100%;margin-top:.3rem;">'
        f'{P.esc(reason)}</textarea></div>')


def band_html(recs, title: str = "Billed above BOQ") -> str:
    """
    The screen-only amber band for a VIEW page. `recs` is one record or a
    list of `(label, record)` pairs (a merged document's two legs, a BOQ's
    bills). Reads the STORED snapshot only. "" when nothing carries one.
    """
    if isinstance(recs, dict):
        recs = [("", recs)]
    parts = []
    for label, rec in recs or []:
        rows = (rec or {}).get(LINES_KEY) or []
        if not rows:
            continue
        items = "".join(
            f'<li>Item {P.esc(r.get("item_no")) or "&mdash;"} ({P.esc(r.get("leg"))}): '
            f'BOQ {_q(r.get("boq_qty"))}, billed to {_q(r.get("cumulative_after"))} '
            f'&mdash; <b>{_q(r.get("excess"))} above</b></li>'
            for r in rows)
        head = f'<div style="margin-top:.4rem;"><b>{label}</b></div>' if label else ""
        parts.append(
            f'{head}<ul style="margin:.3rem 0 0 1.1rem;">{items}</ul>'
            f'<div style="margin-top:.3rem;">Reason: '
            f'{P.esc((rec or {}).get(REASON_KEY)) or "&mdash;"}</div>')
    if not parts:
        return ""
    return (f'<div class="boq-excess-band no-print" style="{_AMBER}">'
            f'<b>&#9888; {P.esc(title)}</b> (screen only, never printed)'
            + "".join(parts) + "</div>")


# ── The tax invoice raised from a BOQ ───────────────────────────────────────

def _is_live(rec) -> bool:
    return str((rec or {}).get("status") or "").strip().lower() != "cancelled"


def ti_prior_by_line(chain: set, exclude_id: str = "") -> dict:
    """
    `{(line_id, leg): qty}` on every LIVE tax invoice raised from a BOQ of this
    chain — DERIVED by summing, keyed on `line_id`. RA bills are NOT counted
    here (ABOUT.md §7 gap 78 is unchanged: a BOQ tax invoice and the RA bills
    are two routes the form names, never sums).
    """
    out = {}
    for iid, ti in (STORE.get("invoices") or {}).items():
        if iid == exclude_id or not _is_live(ti):
            continue
        if str(ti.get("boq_id") or "") not in chain or ti.get("proforma_id"):
            continue
        for it in ti.get("line_items") or []:
            if it.get("type") != "item" or it.get("is_header"):
                continue
            lid = str(it.get("line_id") or "")
            if not lid:
                continue
            key = (lid, str(it.get("leg") or ""))
            out[key] = out.get(key, 0.0) + float(it.get("qty") or 0.0)
    return out


def ti_excess(boq: dict, chain: set, items: list, exclude_id: str = "") -> list:
    """
    The rows of a BOQ tax invoice's `items` above the schedule's quantity.
    `exclude_id` names the invoice being edited, so it is not counted twice.
    """
    qty_of, label = {}, {}
    for li in (boq or {}).get("line_items") or []:
        lid = str(li.get("line_id") or "")
        if lid and not li.get("is_header"):
            qty_of[lid] = float(li.get("total_qty") or 0.0)
            label[lid] = str(li.get("item_no") or "")
    prior = ti_prior_by_line(chain, exclude_id=exclude_id)
    mine = {}
    for it in items or []:
        if it.get("type") != "item" or it.get("is_header"):
            continue
        lid = str(it.get("line_id") or "")
        if lid not in qty_of:
            continue
        key = (lid, str(it.get("leg") or ""))
        mine[key] = mine.get(key, 0.0) + float(it.get("qty") or 0.0)
    out = []
    for (lid, leg), this in mine.items():
        before = prior.get((lid, leg), 0.0)
        cum = before + this
        if round(cum - qty_of[lid], 6) > _EPS:
            out.append({"line_id": lid, "item_no": label.get(lid, ""), "leg": leg,
                        "approved": qty_of[lid], "previously": before,
                        "this": this, "cumulative": cum,
                        "over": cum - qty_of[lid]})
    return out


# ── The BOQ's own view ──────────────────────────────────────────────────────

def boq_band_html(chain: set) -> str:
    """Every live RA bill and BOQ tax invoice on this chain that billed above it."""
    pairs = []
    for r in sorted((STORE.get("ra_bills") or {}).values(),
                    key=lambda b: int(b.get("ra_no") or 0)):
        if str(r.get("boq_id") or "") in chain and _is_live(r) and r.get(LINES_KEY):
            pairs.append((f"RA{int(r.get('ra_no') or 0)} {P.esc(r.get('leg'))}", r))
    for t in sorted((STORE.get("invoices") or {}).values(),
                    key=lambda t: str(t.get("ref") or "")):
        if str(t.get("boq_id") or "") in chain and _is_live(t) and t.get(LINES_KEY):
            pairs.append((f"Tax invoice {P.esc(t.get('ref'))}", t))
    return band_html(pairs)
