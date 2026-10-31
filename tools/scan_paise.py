"""
scan_paise.py — list saved documents carrying a money figure beyond two decimals
================================================================================

CLIENT_CHANGES.md §0 sixty-third block, Part B (31 October 2026). The client's
customer portal rejected a bill with THREE decimals in an amount. From this
date every money figure is rounded to the paisa when it is computed (the leaf
`roundoff.paise()`); **records saved before are NOT rewritten** — snapshot
immutability, a printed document is driven by its own stored rows.

This tool is how the owner finds those older records: it walks every money
collection and prints each document, **by type and number**, that stores any
money value with more than two decimals, and the fields that do.

⚠ **READ-ONLY. THERE IS NO WRITE MODE, AND THERE WILL NOT BE ONE.** It never
  calls `db.sync()`, never assigns into `STORE`, and refuses `--write` in
  words rather than ignoring it. A record it names is fixed — if it is fixed
  at all — by a person deciding to raise a fresh document, never by this.

What it counts as money: the keys in `MONEY_KEYS` and the per-slab tax heads
(`CGST @ 9%` …), anywhere in a record, nested lists and dicts included. Rates
that are percentages and quantities are not money and are not scanned. A work
order stores no amount (its figures are derived), so its DERIVED totals are
scanned through `workorder.totals_of()` — what it would print.

Usage
-----
    python tools/scan_paise.py          # the report (the only mode)
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MONEY_KEYS = frozenset({
    "total", "amount", "subtotal", "grand_total", "taxable_value", "round_off",
    "rounding_off", "claim_subtotal", "net_payable", "tax_amount",
    "cgst_amount", "sgst_amount", "igst_amount", "deduction_total",
    "amount_due", "balance_due", "supply_amount", "install_amount",
    "supply_subtotal", "install_subtotal", "payable", "net_raw", "gross",
    "CGST", "SGST", "IGST", "VAT", "taxable", "taxable_amount",
    "advance_received", "prior_invoiced", "price", "written_off",
    "material", "labour", "gst", "carry", "basic", "ot", "prev_balance",
})

# (collection, the label printed, the field that is its number)
COLLECTIONS = (
    ("quotations",  "Quotation",        "ref"),
    ("boqs",        "BOQ",              "ref"),
    ("proformas",   "Proforma Invoice", "ref"),
    ("invoices",    "Tax Invoice",      "ref"),
    ("purchases",   "Purchase Order",   "ref"),
    ("work_orders", "Work Order",       "ref"),
    ("ra_bills",    "RA Bill",          "ref"),
    ("merged_ras",  "Merged RA (TI)",   "tax_invoice_ref"),
    ("receipts",    "Receipt",          "ref"),
    ("charges",     "Charge",           "ref"),
    ("payslips",    "Payslip",          "id"),
)


def too_fine(v) -> bool:
    """A number with more than two decimals — `repr`, so 0.1 + 0.2 is caught."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return Decimal(repr(float(v))).as_tuple().exponent < -2
    except Exception:          # pragma: no cover — inf / nan
        return False


def offenders(rec, path: str = "") -> list:
    """`[(field path, value)]` — every money value in `rec` beyond two decimals."""
    out = []
    if isinstance(rec, dict):
        for k, v in rec.items():
            here = f"{path}.{k}" if path else str(k)
            if (k in MONEY_KEYS or str(k).startswith(("CGST @", "SGST @", "IGST @"))) \
                    and too_fine(v):
                out.append((here, v))
            out += offenders(v, here)
    elif isinstance(rec, list):
        for i, v in enumerate(rec):
            out += offenders(v, f"{path}[{i}]")
    return out


def scan(store: dict, wo_totals=None) -> list:
    """
    `[(label, number, [(field, value), …]), …]` — read-only, in collection
    order then by number. `wo_totals` is `workorder.totals_of` (passed in so
    this function stays pure and importable without the app).
    """
    found = []
    for coll, label, key in COLLECTIONS:
        rows = []
        for rid, rec in (store.get(coll) or {}).items():
            if not isinstance(rec, dict):
                continue
            bad = offenders(rec)
            if coll == "work_orders" and wo_totals is not None:
                try:
                    bad += [(f"(derived) {p}", v)
                            for p, v in offenders(wo_totals(rec))]
                except Exception:      # pragma: no cover — a malformed order
                    pass
            if bad:
                number = str(rec.get(key) or rec.get("ref") or rid)
                if coll == "payslips":
                    snap = rec.get("snapshot") or {}
                    number = (f"{snap.get('employee_name') or rec.get('employee_id')}"
                              f" {rec.get('month') or ''}").strip()
                rows.append((label, number, bad))
        found += sorted(rows, key=lambda r: r[1])
    return found


def report(found: list) -> str:
    if not found:
        return "No saved document carries a money figure beyond two decimals."
    lines = [f"{len(found)} saved document(s) carry a money figure beyond two "
             f"decimals. NOTHING HAS BEEN CHANGED — this tool cannot write.", ""]
    for label, number, bad in found:
        lines.append(f"{label}  {number}")
        for field, value in bad[:12]:
            lines.append(f"    {field} = {value!r}")
        if len(bad) > 12:
            lines.append(f"    … and {len(bad) - 12} more field(s)")
    return "\n".join(lines)


def main(argv) -> int:
    if any(a.startswith("--write") or a in ("-w", "--fix", "--apply") for a in argv):
        print("scan_paise.py is READ-ONLY and has no write mode. Saved documents "
              "are never rewritten (snapshot immutability); nothing was done.")
        return 2
    from app import app        # noqa: F401 — boots persistence, loads STORE
    import workorder as WO
    from store import STORE
    print(report(scan(STORE, wo_totals=WO.totals_of)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
