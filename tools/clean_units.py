#!/usr/bin/env python
"""
clean_units.py — map the legacy free-text units onto the shared list
=====================================================================

⚠ **THIS SCRIPT MUTATES LIVE RECORDS AND HAS NOT BEEN RUN.** Take
`python tools/backup_db.py --label pre-unit-clean` first. It is a **dry run by
default** and prints the whole plan, including everything it refuses to touch,
before you ever pass `--write`.

⚠ **No backup was possible on the machine this was written on** — there is no
  MySQL there (CLIENT_CHANGES.md §0, the fifty-ninth block's *What is NOT in
  this pass*). The backup above is the first one in this sequence and must be
  real.

Authorised by the **fifty-ninth** §0 block of `CLIENT_CHANGES.md`
(29 October 2026), item **B3**, which asks for exactly this and says in terms:
**do not run it.**

What it does
------------
`units.py` is the shared list from 29 October 2026: **Nos, Mtrs, Kg, Set, Lot,
Sq Ft, Sq M**, plus whatever an Owner has added at `/settings`. Every unit
written before that date was typed into a free-text box, and the client's own
sheets carry `Nos.`, `Mtrs.`, `Kgs.`, `Lump Sum`, `Job`, `Sq.Mtrs` and `Ltrs`.
B3's rule is **existing free-text units stay as they are**, so the application
rewrites nothing — it keeps whatever a line says as an option on that line.
This script is the separate, deliberate, human-run cleanup.

For each unit string on each line of each collection below:

| the stored string | what happens |
|---|---|
| already one of the list, spelled exactly | left alone, counted as `exact` |
| one of the list, differing only by case or spacing | **normalised to the list's spelling** |
| in `ALIASES` below | **mapped** |
| anything else | ⚠ **LEFT, and printed** with its collection and line |
| blank or absent | ⚠ **LEFT** — a blank unit is a blank unit (§0 forty-fifth block, A1) |

⚠ **IT NEVER GUESSES, AND THE UNMAPPED LIST IS THE DELIVERABLE.** There is no
fuzzy match, no stemming, no "starts with". `ALIASES` is a hand-written table
of the strings this repository can actually point at — `spec.UNITS`,
`boq._UNITS` and the client's own sheets — and nothing else is touched.
`po_parts.py`'s 156 invented aliases are the lesson (ABOUT.md §2h): a wrong
automatic match changes what a document says a quantity is measured in, and
looks exactly like a right one.

⚠ **A PRINTED DOCUMENT IS NOT TOUCHED BY DEFAULT.** `--include-issued` is
needed to reach a proforma, a tax invoice, an RA bill, a merged RA, a
purchase order, a product inquiry, a delivery challan or a work order, because
each of those is a **snapshot of what was sent** (CLIENT_CHANGES.md §1.2) and
changing the unit on one changes a document somebody already has. Without the
flag it touches the two places a unit is still being *authored*: the
specification library's variants and BOQ line items.

Usage
-----
    python tools/clean_units.py                      # dry run, everything
    python tools/clean_units.py --write              # apply (BOQs + specs)
    python tools/clean_units.py --include-issued     # dry run, documents too
    python tools/clean_units.py --include-issued --write
    python tools/clean_units.py --collection boqs    # one collection

Idempotent: a second run reports every row as `exact` and writes nothing.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline as P      # noqa: E402
import units as UN        # noqa: E402

# ── The alias table. HAND-WRITTEN, and the only mapping there is. ──────────
#
# Every key is a string this repository can point at: `spec.UNITS`,
# `boq._UNITS`, `product.py`'s catalogue list, or the client's own workbooks as
# `sheetimport.py` reads them. Matched through `pipeline.norm_name()`, so case
# and internal spacing do not need their own rows.
#
# ⚠ **`Lump Sum` and `Job` map to `Lot`**, which is the one judgement in this
#   table and is flagged as such in the report: both mean "one undivided
#   amount of work", which is what the client's `Lot` is, and all three file as
#   `OTH`. If that is wrong it is wrong in a way a human reading the dry run
#   can see, which is why it is printed under its own heading.
ALIASES = {
    # → Nos
    "nos.": "Nos", "no.": "Nos", "no": "Nos", "nos": "Nos",
    "number": "Nos", "numbers": "Nos", "pcs": "Nos", "pc": "Nos",
    "piece": "Nos", "pieces": "Nos", "each": "Nos", "ea": "Nos",
    # → Mtrs
    "mtrs.": "Mtrs", "mtr": "Mtrs", "mtr.": "Mtrs", "mtrs": "Mtrs",
    "meter": "Mtrs", "meters": "Mtrs", "metre": "Mtrs", "metres": "Mtrs",
    "m": "Mtrs", "rmt": "Mtrs", "r.mt": "Mtrs", "running mtr": "Mtrs",
    # → Kg
    "kg": "Kg", "kgs": "Kg", "kgs.": "Kg", "kg.": "Kg",
    "kilogram": "Kg", "kilograms": "Kg",
    # → Set
    "set": "Set", "sets": "Set", "set.": "Set",
    # → Sq Ft
    "sqft": "Sq Ft", "sq.ft": "Sq Ft", "sq.ft.": "Sq Ft", "sq ft": "Sq Ft",
    "sft": "Sq Ft", "square feet": "Sq Ft", "square foot": "Sq Ft",
    # → Sq M
    "sqm": "Sq M", "sq.m": "Sq M", "sq.m.": "Sq M", "sq m": "Sq M",
    "sq.mtrs": "Sq M", "sq.mtr": "Sq M", "sq mtrs": "Sq M",
    "square meter": "Sq M", "square metre": "Sq M",
    # → Lot  ⚠ the one judgement — see the note above
    "lot": "Lot", "lots": "Lot", "lump sum": "Lot", "lumpsum": "Lot",
    "l.s.": "Lot", "ls": "Lot", "job": "Lot", "jobs": "Lot",
}

# The judgement rows, named so the dry run can print them apart.
JUDGEMENT = {"lump sum", "lumpsum", "l.s.", "ls", "job", "jobs"}

# ── Where a unit lives. `(collection, how to walk it)` ────────────────────
#
# Each entry names the collection, the list on the record, the key on each
# row, and whether the record is a SNAPSHOT of something already sent.
AUTHORED = (
    ("boqs",  "line_items", "unit", "ref"),
    ("specs", "variants",   "unit", "code"),
)
ISSUED = (
    ("proformas",         "line_items",  "unit", "ref"),
    ("invoices",          "line_items",  "unit", "ref"),
    ("purchases",         "line_items",  "unit", "ref"),
    ("purchases",         "extra_lines", "unit", "ref"),
    ("purchase_orders",   "items",       "unit", "ref"),
    ("ra_bills",          "claims",      "unit", "ref"),
    ("delivery_challans", "items",       "unit", "ref"),
    ("work_orders",       "lines",       "unit", "ref"),
)


def _target(value):
    """
    `(new_label, why)` for one stored unit, or `(None, why)` to leave it.

    `why` is one of `blank`, `exact`, `respell`, `alias`, `judgement`,
    `unmapped`.
    """
    raw = str(value or "")
    key = P.norm_name(raw)
    if not key:
        return None, "blank"
    for label, _uqc in UN.pairs():
        if P.norm_name(label) == key:
            return (None, "exact") if label == raw.strip() else (label, "respell")
    if key in ALIASES:
        return ALIASES[key], ("judgement" if key in JUDGEMENT else "alias")
    return None, "unmapped"


def plans(include_issued: bool = False, only=()) -> list:
    """
    Which `(collection, list, field, ref)` rows this run will walk.

    ⚠ **`AUTHORED` only, unless `include_issued`.** A proforma, a tax invoice,
      an RA bill, a purchase order, a product inquiry, a challan and a work
      order are each a SNAPSHOT of what was sent (CLIENT_CHANGES.md §1.2), and
      changing a unit on one changes a document somebody already has. Its own
      function so the rule is assertable without going through argparse —
      `tests/test_units.py` does exactly that.
    """
    out = list(AUTHORED) + (list(ISSUED) if include_issued else [])
    if only:
        keep = set(only)
        out = [row for row in out if row[0] in keep]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--write", action="store_true",
                    help="apply the plan. Without it, nothing is written.")
    ap.add_argument("--include-issued", action="store_true",
                    help="also touch documents that have been SENT. Read the "
                         "header before you do.")
    ap.add_argument("--collection", action="append", default=[],
                    help="limit to one collection. Repeatable.")
    args = ap.parse_args()

    # `app` boots persistence and loads STORE — every tool in this directory
    # does it this way (`tools/backfill_marking_projects.py`), so a tool and
    # the application cannot disagree about how the store is opened.
    os.environ.setdefault("SAMRUDDHI_DEMO_DATA", "false")
    import db                        # noqa: F401
    from app import app              # noqa: F401
    from store import STORE

    plan_rows = plans(args.include_issued, args.collection)

    counts = {k: 0 for k in ("blank", "exact", "respell", "alias",
                             "judgement", "unmapped")}
    changes, unmapped, judged = [], [], []

    for coll, listkey, field, refkey in plan_rows:
        for rid, rec in (STORE.get(coll) or {}).items():
            ref = str(rec.get(refkey) or rid)
            for n, row in enumerate(rec.get(listkey) or []):
                if not isinstance(row, dict):
                    continue
                cur = row.get(field)
                new, why = _target(cur)
                counts[why] += 1
                if why == "unmapped":
                    unmapped.append((coll, ref, n, str(cur)))
                elif new is not None:
                    changes.append((coll, rid, ref, listkey, n, field,
                                    str(cur), new, why))
                    if why == "judgement":
                        judged.append((coll, ref, n, str(cur), new))

    mode = "WRITE" if args.write else "DRY RUN"
    print(f"\nclean_units.py — {mode}"
          f"{'  (including documents already SENT)' if args.include_issued else ''}")
    print(f"collections: {', '.join(sorted({r[0] for r in plan_rows})) or '(none)'}")
    print(f"shared list: {' · '.join(UN.labels())}\n")

    empty = [c for c, _l, _f, _r in plan_rows if not (STORE.get(c) or {})]
    if empty:
        print(f"⚠ empty collection(s), nothing to read: {', '.join(sorted(set(empty)))}\n")

    print("counted:")
    for k in ("exact", "respell", "alias", "judgement", "unmapped", "blank"):
        print(f"  {k:<10} {counts[k]:>6}")

    if judged:
        print("\n⚠ JUDGEMENT ROWS — read these before --write. 'Lump Sum' and")
        print("  'Job' are being read as 'Lot'; all three file as OTH.")
        for coll, ref, n, cur, new in judged:
            print(f"    {coll:<18} {ref:<22} line {n:<4} {cur!r} -> {new!r}")

    if unmapped:
        print(f"\n⚠ LEFT ALONE — {len(unmapped)} unit(s) this table cannot point at.")
        print("  Nothing is guessed. Add a row to ALIASES, or fix the line by hand.")
        seen = {}
        for coll, ref, n, cur in unmapped:
            seen.setdefault(cur, []).append(f"{coll}/{ref}#{n}")
        for cur, where in sorted(seen.items()):
            head = ", ".join(where[:4]) + (" …" if len(where) > 4 else "")
            print(f"    {cur!r:<24} {len(where):>4}  {head}")

    print(f"\n{len(changes)} line(s) would change." if not args.write
          else f"\n{len(changes)} line(s) changing.")
    for coll, _rid, ref, _lk, n, _f, cur, new, why in changes[:40]:
        print(f"    {coll:<18} {ref:<22} line {n:<4} {cur!r} -> {new!r}  ({why})")
    if len(changes) > 40:
        print(f"    … and {len(changes) - 40} more")

    if not args.write:
        print("\nDry run — nothing was written. Re-run with --write to apply,")
        print("AFTER `python tools/backup_db.py --label pre-unit-clean`.")
        return 0

    for coll, rid, _ref, listkey, n, field, _cur, new, _why in changes:
        STORE[coll][rid][listkey][n][field] = new
    if db.is_live():
        db.sync(STORE)
    else:
        print("\n⚠ The database is NOT live (DB_ENABLED=false), so this run "
              "changed the in-memory store only and nothing was persisted.")
    print(f"\nWritten. {len(changes)} line(s) updated in "
          f"{len({c[0] for c in changes})} collection(s).")
    print("Re-run without --write: every row should now read 'exact'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
