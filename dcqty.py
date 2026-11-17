"""
dcqty.py — the delivery challan's TWO quantity columns, Qty (Mtr) and Qty (Nos)
==============================================================================

17 November 2026, CLIENT_CHANGES.md §0 **eighty-second** block (prod hotfix 7).

The client's own paper challan (their DC 63) reads

    Sr.No | Description | Qty (Mtr) | Qty (Nos) | Unit

A pipe line carries both (482.4 Mtr, 80 nos); a fitting or a valve carries
Nos only. Either or both may be filled on a line; at least one must be > 0.

**The data.** A challan line gains optional `qty_mtr` and `qty_nos` (a float,
or None for a blank box). Its `qty` stays, and is the **billing quantity** —
the figure in the line's OWN unit, set at save by `stamp()`:

    unit Mtr / Mtrs / m (and metre spellings)  → qty = qty_mtr
    unit Nos / No / Pcs                        → qty = qty_nos
    any other unit (Kg, Set, Lot, Sq M …)      → qty = qty_nos

**No migration.** A line saved before this block has `qty` only; it is read
by its unit (`cols()`): a Mtr line's `qty` is the Mtr column, anything else's
is the Nos column. Its billing quantity is that `qty`, as it always was.

**The Unit column names the unit of the SECOND column** — "Nos" by default,
and the line's own unit when that unit is neither Mtr nor Nos (so a Kg line
prints its kilograms in the second column with "Kg" beside them).

**Billing.** RA-from-DC, the dispatched remainder (`dcpo.py`), the
over-dispatch warning and the P&L count `billing_qty()` — the quantity in the
BOQ / PO line's own unit. The other column is information only and is never
counted: a 482.4 Mtr / 80 Nos pipe line counts 482.4 against a Mtr line.

⚠ A leaf: imports `pipeline` only. `boqpick.py`, `extraitems.py`,
`challan.py`, `dcpo.py`, `ra.py` and `pnl.py` read it.
"""

import pipeline as P

MTR_UNITS = {"mtr", "mtrs", "m", "mtr.", "mtrs.", "meter", "meters",
             "metre", "metres", "rmt", "rm"}
NOS_UNITS = {"nos", "no", "nos.", "no.", "pcs", "pc", "pcs.", "pc.",
             "number", "numbers"}

MTR_LABEL = "Qty (Mtr)"
NOS_LABEL = "Qty (Nos)"


def unit_class(unit) -> str:
    """`"mtr"`, `"nos"` or `"other"` for a unit as written."""
    u = " ".join(str(unit or "").split()).casefold()
    if u in MTR_UNITS:
        return "mtr"
    if u in NOS_UNITS:
        return "nos"
    return "other"


def has_two(row) -> bool:
    """Was this line saved with the two columns (this block or later)?"""
    return isinstance(row, dict) and ("qty_mtr" in row or "qty_nos" in row)


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def split(qty, unit) -> tuple:
    """`(mtr, nos)` for one quantity in a line's own unit — the prefill rule."""
    q = _f(qty)
    return (q, None) if unit_class(unit) == "mtr" else (None, q)


def cols(row) -> tuple:
    """
    `(mtr, nos, unit_label)` as the challan PRINTS a line: each a float or
    None (a blank cell). A line without the two keys is read by its unit.
    """
    unit = str((row or {}).get("unit") or "")
    if has_two(row):
        mtr, nos = _f(row.get("qty_mtr")), _f(row.get("qty_nos"))
    else:
        mtr, nos = split((row or {}).get("qty") or 0.0, unit)
    label = unit if unit_class(unit) == "other" and unit.strip() else "Nos"
    return mtr, nos, label


def billing_qty(row) -> float:
    """The quantity in the line's OWN unit — the one figure anything counts."""
    if not has_two(row):
        return float(_f((row or {}).get("qty")) or 0.0)
    if unit_class(row.get("unit")) == "mtr":
        return float(_f(row.get("qty_mtr")) or 0.0)
    return float(_f(row.get("qty_nos")) or 0.0)


def parse_pair(raw_mtr, raw_nos, what: str) -> tuple:
    """
    `(mtr, nos, error)` off the two boxes. Blank is None; text or a negative
    is refused; at least one must be above 0.
    """
    out = []
    for raw, lbl in ((raw_mtr, MTR_LABEL), (raw_nos, NOS_LABEL)):
        s = str(raw if raw is not None else "").strip()
        if not s:
            out.append(None)
            continue
        try:
            v = float(s)
        except ValueError:
            return None, None, f"{lbl} for '{what}' must be a number."
        if v != v or v < 0:
            return None, None, f"{lbl} for '{what}' cannot be below 0."
        out.append(v)
    mtr, nos = out
    if not ((mtr or 0) > P.QTY_EPSILON or (nos or 0) > P.QTY_EPSILON):
        return None, None, (f"'{what}' needs a quantity above 0 in "
                            f"{MTR_LABEL} or {NOS_LABEL}.")
    return mtr, nos, ""


def stamp(row: dict, mtr, nos) -> dict:
    """Write both columns and the billing `qty` onto a line."""
    row["qty_mtr"] = mtr
    row["qty_nos"] = nos
    row["qty"] = billing_qty(row)
    return row


def fmt(v) -> str:
    """A cell: "" for a blank box, else `quotation._fmt_qty()`'s own rule."""
    if v is None:
        return ""
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def replay(row) -> dict:
    """`{"mtr": str, "nos": str}` — a line's two boxes as a form shows them."""
    mtr, nos, _l = cols(row)
    return {"mtr": fmt(mtr), "nos": fmt(nos)}
