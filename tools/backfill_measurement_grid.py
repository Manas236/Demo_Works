#!/usr/bin/env python
"""
backfill_measurement_grid.py — mark the pre-joint measurement sheets
====================================================================

⚠ **THIS SCRIPT MUTATES LIVE RECORDS.** Take
`python tools/backup_db.py --label pre-measurement-grid` first.

Authorised by the **twenty-third §0 block of `CLIENT_CHANGES.md`,
6 September 2026**.

What it does
------------
The JOINT MEASUREMENT SHEET replaced the linear measurement layout with a
(location x diameter) grid. Two sheets already exist in the live database and
**neither maps onto that grid**:

    SF/MS/26-27/0001   BOQ SF/BOQ/26-27/0007, project "Banglore"
                       2 priced rows, 10.0 measured
    SF/MS/26-27/0002   BOQ SF/BOQ/26-27/0008, project "Sify Bangalore"
                       87 priced rows + 10 headers, 5,865.0 measured

⚠ **They are marked, not migrated, and the reason is that migrating them would
  mean INVENTING DATA.** The grid is keyed by (location, diameter). On these
  records `location` is a single free-text field on the **sheet** — `""` on
  0001 and `"5,7"` on 0002 — and not a property of a row; there is no diameter
  column at all. A diameter appears only inside some `description` strings
  ("150mm dia ISI"), for the pipe items and not for the rest. Deriving a grid
  from that would mean parsing prose into a measurement two parties sign.

  So each gets the explicit mark

      "grid_model": "legacy-linear"

  and goes on rendering through `measurement._legacy_document_html()`, exactly
  as it always has. **Nothing is deleted, nothing is reshaped, no quantity
  moves, and both stay in the register.** This is the treatment the day-rate
  migration gave the one old employee record.

⚠ **THE MARK IS WRITTEN, NEVER INFERRED.** `measurement.is_legacy_grid()` would
  answer correctly for these records even without it — the absence of a joint
  mark is enough. The mark is written anyway because "has no grid" and "was
  written before grids existed" are different facts, and a branch that cannot
  tell them apart will one day render a NEW sheet through the OLD template
  because somebody's grid failed to save. `pre_measurement` and
  `pre_approval_system` are the same rule, and this is its third application.

⚠ **It touches no `items` row.** Those rows carry the `line_id` quantities that
  feed `ra.overclaims()` through `measurement.approved_qty_by_line()` — the
  installation ceiling, and CC-2 C2's own sentence. Neither of these two sheets
  is approved, so neither is feeding a ceiling today; that is a fact about
  today and not a licence to touch them.

⚠ **It grants no permission and touches no user or role.** The
  `backfill_created_by.py` migration reached into `STORE["roles"]` and the
  fifth 29 August 2026 override block acknowledges that retrospectively, saying
  the next migration touching identity data must be authorised on its own
  terms. This one does not touch it at all.

Idempotent
----------
A second run reports **0 changed**. The mark is only ever written where it is
absent, and a sheet already carrying `joint-v1` is left alone — that is a sheet
raised after the redesign and it is not this script's business.

    python tools/backfill_measurement_grid.py            # dry run, the default
    python tools/backfill_measurement_grid.py --write
"""

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import db as _db  # noqa: E402
import measurement as MS  # noqa: E402
from store import STORE  # noqa: E402

# Where the run records itself, beside `measurement_migration`.
MIGRATION_KEY = "measurement_grid_migration"


def _now() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def plan(records: dict) -> tuple:
    """
    `(to_mark, already_legacy, joint)` — what this run would do.

    Pure, so `tests/test_measurement_grid_backfill.py` can exercise the
    decision without a database.
    """
    to_mark, already, joint = [], [], []
    for mid, ms in sorted(records.items(), key=lambda kv: kv[1].get("ref", "")):
        model = str(ms.get("grid_model") or "")
        if model == MS.GRID_MODEL_JOINT:
            joint.append(mid)
        elif model == MS.GRID_MODEL_LEGACY:
            already.append(mid)
        else:
            to_mark.append(mid)
    return to_mark, already, joint


def describe(ms: dict) -> str:
    """One line for the report, and the before/after values it prints."""
    items = ms.get("items") or []
    priced = [r for r in items if not r.get("is_header")]
    total = sum(float(r.get("qty") or 0.0) for r in priced)
    return (f"{ms.get('ref', '(no ref)'):<20} "
            f"boq={ms.get('boq_ref', ''):<20} "
            f"project={str(ms.get('project_name') or ''):<18} "
            f"rows={len(items):>3} (priced {len(priced):>3}) "
            f"measured={total:>10,.2f} "
            f"location={str(ms.get('location') or '')!r}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mark the pre-joint measurement sheets legacy. "
                    "Read the module docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually write the mark (default is a dry run)")
    args = ap.parse_args()

    _db.init()
    n = _db.load_into(STORE)
    print(f"loaded {n} record(s); persistence {'ON' if _db.is_live() else 'OFF'}")

    records = STORE.get("measurements") or {}
    to_mark, already, joint = plan(records)

    print(f"\nmeasurement sheets: {len(records)}")
    print(f"  already marked legacy : {len(already)}")
    print(f"  joint (untouched)     : {len(joint)}")
    print(f"  to mark               : {len(to_mark)}")

    if not to_mark:
        print("\nNothing to do. (This is what a second run looks like.)")
        return 0

    print("\nBEFORE — every value, so the report can carry them:")
    for mid in to_mark:
        print("  " + describe(records[mid]))
        print(f"      grid_model={records[mid].get('grid_model')!r}")

    if not args.write:
        print("\nDRY RUN — nothing written. Re-run with --write.")
        return 0

    for mid in to_mark:
        records[mid]["grid_model"] = MS.GRID_MODEL_LEGACY

    STORE.setdefault("settings", {})[MIGRATION_KEY] = {
        "at": _now(),
        "count": len(to_mark),
        "ids": list(to_mark),
        "refs": [records[m].get("ref", "") for m in to_mark],
        "note": ("Marked legacy-linear rather than migrated: neither sheet "
                 "carries a location or a diameter as structured data, so a "
                 "grid could only have been invented from prose."),
    }

    print("\nAFTER:")
    for mid in to_mark:
        print("  " + describe(records[mid]))
        print(f"      grid_model={records[mid].get('grid_model')!r}")

    result = _db.sync(STORE)
    print(f"\nMarked {len(to_mark)} sheet(s). sync: {result}")
    print("Every original value is untouched — only grid_model was added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
