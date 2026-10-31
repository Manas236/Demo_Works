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


# =============================================================================
# THE PAISA — every money value to two decimals, HALF UP (31 Oct 2026, later)
# =============================================================================
#
# The client's customer portal rejected a bill carrying an amount with THREE
# decimals. The rule from this pass: a line amount (qty × rate, less its
# discount) is rounded to the paisa WHEN IT IS COMPUTED, before it is summed,
# so a subtotal is the sum of the stored line amounts and a printed total is
# the sum of the printed lines, to the paisa. `round(x, 2)` is not this — it
# rounds the BINARY float half to even (round(2.675, 2) == 2.67).

def paise(amount) -> float:
    """`amount` to the paisa, HALF UP. 1235.36415 → 1235.36; 2.675 → 2.68;
    -2.675 → -2.68 (away from zero). `None` and "" read as 0."""
    d = Decimal(f"{float(amount or 0.0):.6f}")
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# =============================================================================
# THE TICK — "Round off to nearest rupee", per document (31 Oct 2026, later)
# =============================================================================
#
# Manas, 31 October 2026: round-off on all documents, nothing left behind — and
# the operator decides per document. Every money document's create and edit
# form carries the tick, TICKED BY DEFAULT, and the record stores the choice as
# `round_off_on` (bool).
#
#   ticked    the whole rupee, HALF UP; `round_off` stored; a "Round off" row
#             printed when it is non-zero — the behaviour from §0 sixty-second
#   unticked  the exact two-decimal figure; `round_off` stored as 0; no row
#
# ⚠ **A record WITHOUT `round_off_on` is a legacy record and behaves exactly
#   as it did** — `is_on(rec, legacy)` answers with the caller's `legacy`,
#   which is what that document did before the tick existed (True for the PO,
#   PI, TI, RA and payslip, which rounded; False for the quotation, BOQ and a
#   work order without `rounds_to_rupee`, which did not).
#
# ⚠ **An unchecked checkbox posts NOTHING**, so the form also posts the hidden
#   marker `MARK`. A POST without the marker did not come from a form that
#   offered the tick — an older client, a test, an import — and is read as the
#   document's legacy behaviour, never as "unticked".

FIELD = "round_off_on"
MARK = "round_off_form"


def form_choice(form, legacy: bool = True) -> bool:
    """The tick as posted: the box when the form offered it, else `legacy`."""
    if form is None or form.get(MARK) is None:
        return bool(legacy)
    return str(form.get(FIELD) or "").strip().lower() in ("1", "on", "true", "yes")


def is_on(rec, legacy: bool = True) -> bool:
    """The stored choice — or, on a record that predates the tick, `legacy`."""
    rec = rec or {}
    if FIELD in rec:
        return bool(rec.get(FIELD))
    return bool(legacy)


def apply(exact, on: bool) -> tuple:
    """`(grand, round_off)` — ticked: the whole rupee and the signed difference;
    unticked: the exact figure to the paisa and 0.0."""
    exact = paise(exact)
    if not on:
        return exact, 0.0
    whole = rupee(exact)
    return whole, paise(whole - exact)


def checkbox_html(on: bool, hint: str = "") -> str:
    """The tick, with its marker. Drawn inside the form it belongs to.

    ⚠ The markup holds no `{` or `}`, so it can be interpolated into an
    f-string page as it is."""
    checked = " checked" if on else ""
    tip = (f'<small class="field-hint" style="display:block;">{hint}</small>'
           if hint else "")
    return (f'<div class="form-group roundoff-tick">'
            f'<input type="hidden" name="{MARK}" value="1"/>'
            f'<label style="display:flex;gap:.45rem;align-items:center;'
            f'font-weight:600;"><input type="checkbox" name="{FIELD}" '
            f'value="1"{checked}/> Round off to nearest rupee</label>{tip}</div>')


def paise_tax(tax_info) -> dict:
    """A tax block with every HEAD to the paisa and `total` their sum.

    Rates (`cgst_rate`, `igst_rate`, … — any key ending `_rate`) are not money
    and are left as they are. A head that is not a number is left alone too.
    The rule is the house one: each printed tax row is a two-decimal figure and
    the tax total is the sum of the printed rows."""
    out = dict(tax_info or {})
    total, heads = 0.0, 0
    for k, v in list(out.items()):
        if k == "total" or str(k).endswith("_rate"):
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        out[k] = paise(v)
        total += out[k]
        heads += 1
    out["total"] = paise(total) if heads else paise(out.get("total"))
    return out
