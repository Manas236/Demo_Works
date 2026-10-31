#!/usr/bin/env python
"""
backfill_spec_from_boqs.py — add every current BOQ's items to the Spec library
==============================================================================

CLIENT_CHANGES.md §0 sixty-first block (31 October 2026). From that date every
BOQ SAVED through `/boq/create` adds its items to the Specification library
(`boq.learn_into_library()`). This is the one-time pass for the BOQs that were
already on the box before then.

It runs the SAME code the save does — `boq.library_payload()` into
`spec.learn_from_clauses()` — over the TIP of every revision chain (a
superseded revision's lines would only add a second copy of a size it later
corrected). Add-only: a clause already in the library is reused, a size it lacks
is appended, and a rate fills only where the library has none. Nothing already
in the library is changed.

**Dry-run is the default** and writes nothing. `--write` writes and prints the
same report. **Idempotent:** a second `--write` adds nothing.

⚠ **ON PRODUCTION, STOP THE SERVICE FIRST.** The app keeps the whole store in
  ONE process's memory (`--workers 1`). Written while it runs, the new clauses
  would be invisible to it until a restart, and an edit to an existing clause
  in the app afterwards would write that clause back WITHOUT the sizes added
  here. So: back up, stop, `--write`, start.

Usage
-----
    python tools/backfill_spec_from_boqs.py            # dry run (default)
    python tools/backfill_spec_from_boqs.py --write    # actually write
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app          # noqa: E402,F401 — boots persistence, loads STORE
import boq as BQ             # noqa: E402
import spec as SP            # noqa: E402
from store import STORE      # noqa: E402


def current_boqs() -> list:
    gone = BQ.superseded_ids()
    tips = [b for bid, b in (STORE.get("boqs") or {}).items()
            if isinstance(b, dict) and str(bid) not in gone]
    return sorted(tips, key=lambda b: (str(b.get("date") or ""), str(b.get("ref") or "")))


def backfill(write: bool = False) -> dict:
    total = {"new_specs": 0, "new_variants": 0, "rates_filled": 0, "unchanged": 0}
    SP.ensure_demo_specs()
    tips = current_boqs()
    mode = "WRITE" if write else "DRY RUN — nothing is written"
    print(f"Spec library backfill from BOQs · {mode}")
    print(f"Library before: {len(STORE.get('specs') or {})} clauses · "
          f"{len(tips)} current BOQ(s)\n")
    # ⚠ The dry run runs the REAL write against a copy of the library and then
    #   puts the original back, so its counts are exactly what --write will do —
    #   including a clause new in one BOQ and reused by the next.
    import copy
    saved = None if write else copy.deepcopy(STORE["specs"])
    for boq in tips:
        rep = SP.learn_from_clauses(BQ.library_payload(boq),
                                    boq_ref=str(boq.get("ref") or ""), write=True)
        for k in total:
            total[k] += rep.get(k, 0)
        print(f"{boq.get('ref') or boq.get('id')}  "
              f"({boq.get('project_name') or 'no project name'}): "
              f"+{rep['new_specs']} clauses, +{rep['new_variants']} sizes, "
              f"{rep['rates_filled']} rates filled, {rep['unchanged']} unchanged")
        for code, title, label in rep["added"]:
            print(f"    {code:<12} {title[:60]}{(' — ' + label) if label else ''}")
    print(f"\nTotal: +{total['new_specs']} clauses, +{total['new_variants']} sizes, "
          f"{total['rates_filled']} rates filled.")
    if saved is not None:
        STORE["specs"].clear()
        STORE["specs"].update(saved)
    print(f"Library after: {len(STORE.get('specs') or {})} clauses"
          + ("" if write else " (unchanged — dry run)"))
    if write:
        import db
        if db.is_live():
            res = db.sync(STORE)
            if res.get("failed"):
                print(f"⚠ PERSISTENCE FAILED on {res['failed']} — nothing in those "
                      f"collections was written. Restore from the backup and stop.")
            else:
                print(f"Written ({res.get('written', 0)} record(s)).")
        else:
            print("⚠ The database is NOT live (DB_ENABLED=false), so this run "
                  "changed the in-memory store only and nothing was persisted.")
    return total


if __name__ == "__main__":
    backfill(write="--write" in sys.argv[1:])
