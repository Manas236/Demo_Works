"""
roundoff.py — the one rupee round-off rule
==========================================

31 October 2026, CLIENT_CHANGES.md §0 sixty-second block. Yogesh, on the call:
the PO showed ₹11,419.80; the final amount must be a whole rupee — **.50 and
above goes up, below .50 goes down**. That is HALF UP, which is NOT Python's
`round()`: `round(2.5) == 2` (ties to even), so every money document here that
rounds goes through this module and nothing else.

A LEAF: imports nothing of the app. A document stores the rounded total as its
`grand_total` and the difference as `round_off` (signed, paise), and prints a
"Round off" row only when that key is present and non-zero — so every document
saved before this date, which has no `round_off`, prints byte-for-byte as it
did.
"""

from decimal import ROUND_HALF_UP, Decimal


def rupee(amount) -> float:
    """`amount` to the whole rupee, HALF UP. 11419.80 → 11420.0; 11419.50 →
    11420.0; 11419.49 → 11419.0; -2.5 → -3.0 (away from zero, like the paper)."""
    d = Decimal(f"{float(amount or 0.0):.6f}")
    return float(d.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def split(amount) -> tuple:
    """`(rounded, round_off)` — the whole-rupee total and the signed difference
    to the paisa. `rounded == amount + round_off` to the paisa."""
    exact = round(float(amount or 0.0), 2)
    whole = rupee(exact)
    return whole, round(whole - exact, 2)


def label(delta) -> str:
    """The printed amount of a round-off row: `+0.20`, `-0.40`."""
    return f"{float(delta or 0.0):+,.2f}"
