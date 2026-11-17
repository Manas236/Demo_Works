"""
dcpo.py — a DELIVERY CHALLAN raised FROM a PURCHASE ORDER: the shared reads
==========================================================================

17 November 2026, CLIENT_CHANGES.md §0 **seventy-eighth** block (prod hotfix 3).

⚠ **Why a leaf.** `challan.py` writes the challan and `purchase.py` draws the
  order's *Dispatched on DCs* list, and the two may not import each other in
  either direction (`tests/test_import_directions.py`: "a goods-movement note
  is not a purchase order" / "the buy side is a separate pipeline"). Both need
  the SAME two answers — which lines an order has, and how much of each has
  already gone out — so the arithmetic lives here once, reading `STORE`
  directly (the one-way trick `ra.py` and `pnl.py` use for this collection),
  and both modules import this file. Nothing upstream: `store` only.

## The order's lines, keyed

Every line of a purchase order gets a KEY that a challan row carries back as
`po_key`:

| key | what | becomes on the challan |
|---|---|---|
| `L:<line_id>` | a `line_items` row whose `line_id` is a line ON the order's BOQ | a BOQ line, `line_id` kept — RA-from-DC counts it exactly as a BOQ challan's line |
| `I:<n>` | any other `line_items` row (index `n`) | an extra (`line_id` None, `extra` True) |
| `X:<n>` | `extra_lines[n]` | an extra |

An order with no BOQ, or whose BOQ is no longer in the store, has no `L:` keys:
every line becomes an extra and the challan is a no-BOQ challan.

## Dispatched — DERIVED, never stored

`dispatched_by_key()` sums `qty` over the rows of every challan whose
`source_po_id` is this order, per `po_key`. A deleted challan is not in the
store, so its quantity is free again. ⚠ A challan has no cancelled state today;
one carrying `status: "cancelled"` is skipped anyway, so the day it gets one
this reads right without an edit.
"""

from store import STORE


def _lid(raw) -> str:
    """A stored line id, normalised the way `boq._line_id()` compares them."""
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return ""
    return str(raw).strip().lower()


def is_withdrawn_po(po) -> bool:
    """A purchase order withdrawn before delivery — nothing is dispatched off it."""
    return str((po or {}).get("status") or "").strip().lower() == "cancelled"


def boq_of(po):
    """The order's BOQ record, or None when it has none or it is gone."""
    bid = str((po or {}).get("boq_id") or "")
    return (STORE.get("boqs") or {}).get(bid) if bid else None


def lines_of(po) -> list:
    """
    `[{key, kind, line_id, item_no, description, unit, qty, make}]` — every
    line a challan can take off this order, in the order's own order: the
    priced lines, then the extra lines. Headers are left out (a BOQ line's
    specification header is brought back by the challan's own picker).
    """
    po = po or {}
    boq = boq_of(po)
    on_boq = ({_lid(li.get("line_id")) for li in boq.get("line_items") or []
               if isinstance(li, dict) and not li.get("is_header")} - {""}
              if boq else set())
    out = []
    for n, r in enumerate(po.get("line_items") or []):
        if not isinstance(r, dict) or r.get("is_header"):
            continue
        lid = _lid(r.get("line_id"))
        linked = bool(lid) and lid in on_boq
        out.append({
            "key": f"L:{lid}" if linked else f"I:{n}",
            "kind": "boq" if linked else "item",
            "line_id": lid if linked else None,
            "item_no": str(r.get("part_no") or ""),
            "description": str(r.get("name") or r.get("description") or ""),
            "unit": str(r.get("unit") or ""),
            "qty": float(r.get("qty") or 0.0),
            "make": str(r.get("make") or ""),
        })
    for n, r in enumerate(po.get("extra_lines") or []):
        if not isinstance(r, dict):
            continue
        out.append({
            "key": f"X:{n}", "kind": "extra", "line_id": None, "item_no": "",
            "description": str(r.get("description") or ""),
            "unit": str(r.get("unit") or ""),
            "qty": float(r.get("qty") or 0.0),
            "make": str(r.get("make") or ""),
        })
    return out


def _live(dc) -> bool:
    return str((dc or {}).get("status") or "").strip().lower() != "cancelled"


def challans_of(po_id: str) -> list:
    """`[(challan_id, challan)]` raised from this order, oldest first."""
    pid = str(po_id or "")
    if not pid:
        return []
    rows = [(cid, dc) for cid, dc in (STORE.get("delivery_challans") or {}).items()
            if str(dc.get("source_po_id") or "") == pid and _live(dc)]
    rows.sort(key=lambda kv: (str(kv[1].get("date") or ""), str(kv[1].get("ref") or "")))
    return rows


def qty_by_key(dc) -> dict:
    """`{po_key: qty}` on one challan."""
    out = {}
    for it in (dc or {}).get("items") or []:
        if not isinstance(it, dict) or it.get("is_header"):
            continue
        key = str(it.get("po_key") or "")
        if key:
            try:
                q = float(it.get("qty") or 0.0)
            except (TypeError, ValueError):
                q = 0.0
            out[key] = out.get(key, 0.0) + q
    return out


def dispatched_by_key(po_id: str, exclude: str = "") -> dict:
    """`{po_key: qty}` summed over this order's challans. `exclude` is one id."""
    out = {}
    for cid, dc in challans_of(po_id):
        if cid == exclude:
            continue
        for k, q in qty_by_key(dc).items():
            out[k] = out.get(k, 0.0) + q
    return out


def remaining_by_key(po) -> dict:
    """`{po_key: ordered − dispatched}`, never below 0."""
    sent = dispatched_by_key((po or {}).get("id"))
    return {r["key"]: max(r["qty"] - sent.get(r["key"], 0.0), 0.0)
            for r in lines_of(po)}
