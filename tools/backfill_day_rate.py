#!/usr/bin/env python
"""
backfill_day_rate.py — close the monthly-salary exception
==========================================================

⚠ **THIS SCRIPT MUTATES LIVE EMPLOYEE AND ATTENDANCE RECORDS.** Take
`python tools/backup_db.py --label pre-day-rate` first.

What it does
------------
The employee master used to hold a **monthly salary** and `attendance.py`
divided it by `settings.wage_days_per_month` to get a daily wage. The owner
corrected that on 30 August 2026: **Samruddhi pays daily or weekly, never
monthly**, and CC-2 had always agreed — its own note calls
`salary ÷ 8 × hours` *"1× ordinary rate"*, which is true only if `salary ÷ 8` is
an **hourly** rate, so `salary` is a **day's** wage.

⚠ **NOTHING IS CONVERTED.** Rereading a stored monthly figure as a day rate
multiplies every wage by roughly twenty-six, and **we do not know which records
were entered as what** — the divisor on this database was set to `1`, so the
pages have been showing a day's wage equal to a whole monthly salary. Dividing
by 26 would replace one guess with another. So the existing set is **marked
explicitly and closed**:

    "rate_model": "pre_day_rate"    # on employees AND on attendance markings

and the count, the moment and the figures are written to
`STORE["settings"]["day_rate_migration"]`:

    {"at": "2026-08-30 12:00", "employees": {...}, "attendance": {...}}

`tests/test_day_rate_pin.py` reads it and fails if an **employee created after
`at`** carries the mark. **That test is the point of the whole rule.** Without
it "pre-day-rate" stops being a closed historical set and becomes a state any
future record can fall into, which is the same as not having the rule at all.
`tools/backfill_measurement_pin.py` makes the identical argument one register
along, and this is that argument applied to the rate rather than the quantity.

What a marked record does
-------------------------
1. **it keeps its figure.** Nothing is recomputed, converted or deleted;
2. **no wage is computed from it, anywhere.** `employee.day_rate_of()` refuses
   to answer and `attendance.cost_of()` returns `refused` rather than a number.
   A refused marking is excluded from every site total and the page says by how
   many;
3. an **employee** shows an amber band saying the rate needs re-entering, and
   typing one clears the mark. An **attendance marking** never clears: it is
   history, and the record of what that day was assessed at does not improve by
   being rewritten;
4. `/attendance/mark` **refuses** an employee whose rate is unconfirmed, so a
   NEW marking can never join the closed set.

It also strips the dead `wage_days_per_month` key
--------------------------------------------------
`settings.labour_settings()` reads off `LABOUR_DEFAULTS` and cannot see a key
that is no longer in it, so the stored value is already inert. It is removed
anyway: a dead key sitting in a live settings row is a trap for the next reader,
and this one in particular reads as a live divisor.

⚠ **It grants no permission to any role and touches no identity data.**
`backfill_created_by.py` reached into `STORE["roles"]` and the fifth 29 August
2026 override block says the next migration touching identity data must be
authorised on its own terms. This one has no reason to, so it has no flag for
it.

**Dry-run is the default** — it prints the proposal and writes nothing.

**Idempotent:** a record already carrying the mark is left alone, and the
migration record is written once and not overwritten. Re-running this after a
month must not move the pinned moment, or the exception re-opens for everything
written in between.

Usage
-----
    python tools/backfill_day_rate.py            # dry-run (default)
    python tools/backfill_day_rate.py --write    # mark the records
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import db                    # noqa: E402
import employee as EMP       # noqa: E402
import settings as S         # noqa: E402
from store import STORE      # noqa: E402

DEAD_SETTING = "wage_days_per_month"


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _todo(collection: str) -> list:
    """Ids of the records the migration would mark, sorted."""
    return sorted(rid for rid, r in (STORE.get(collection) or {}).items()
                  if EMP.needs_rate_pin(r))


def main() -> int:
    # `description=__doc__` would push the docstring's warning marks through the
    # Windows console codec on --help, which raises. The summary is enough; the
    # reasoning is in the docstring, read in the file.
    ap = argparse.ArgumentParser(
        description="Close the monthly-salary exception. Read the module "
                    "docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually write (default is a dry run)")
    args = ap.parse_args()

    with app.app_context():
        already = EMP.migration_record()
        if already:
            print(f"! The pin has already run at {already.get('at')}.")
            print("  The pinned moment is not moved. Only unmarked records "
                  "below would be touched.\n")

        emps = STORE.get("employees") or {}
        atts = STORE.get("attendance") or {}
        emp_todo = _todo("employees")
        att_todo = _todo("attendance")

        print(f"Employees in the database        : {len(emps)}")
        print(f"  ... carrying an old-model rate : {len(emp_todo)}"
              f"   <- the pinned set")
        for rid in emp_todo:
            e = emps[rid]
            print(f"        {str(e.get('code') or '-'):<10} "
                  f"{str(e.get('name') or '')[:26]:<28} "
                  f"monthly_salary={e.get('monthly_salary')!r:<12} "
                  f"site={str(e.get('site') or '')!r}")

        print(f"\nAttendance markings              : {len(atts)}")
        print(f"  ... costed under the old model : {len(att_todo)}"
              f"   <- the pinned set")
        for rid in att_todo:
            a = atts[rid]
            print(f"        {str(a.get('date') or ''):<12} "
                  f"{str(a.get('employee_name') or '')[:26]:<28} "
                  f"monthly_salary={a.get('monthly_salary')!r:<12} "
                  f"site={str(a.get('site') or '')!r}")

        stale = (STORE.get("settings", {}).get(S.LABOUR_RECORD) or {})
        has_dead = DEAD_SETTING in stale
        shown = repr(stale.get(DEAD_SETTING)) if has_dead else "absent"
        print(f"\nDead `{DEAD_SETTING}` in the labour settings row : {shown}")
        if has_dead:
            print("  It is already inert — `labour_settings()` reads off "
                  "LABOUR_DEFAULTS — and is removed so it cannot mislead.")

        if not args.write:
            print("\nDRY RUN — nothing written. Re-run with --write.")
            return 0

        # ⚠ The figures are recorded BEFORE the mark goes on, so the migration
        #   record is the account of what was there. `employee.edit_employee()`
        #   drops `monthly_salary` when a day rate is confirmed, and this is
        #   where that figure survives outside the pre-migration dump.
        emp_had = {rid: emps[rid].get("monthly_salary") for rid in emp_todo}
        att_had = {rid: atts[rid].get("monthly_salary") for rid in att_todo}

        for rid in emp_todo:
            emps[rid][EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE
        for rid in att_todo:
            atts[rid][EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE

        if has_dead:
            stale.pop(DEAD_SETTING, None)
            if stale:
                STORE["settings"][S.LABOUR_RECORD] = stale
            else:
                STORE["settings"].pop(S.LABOUR_RECORD, None)
            print(f"\nRemoved the dead `{DEAD_SETTING}` key.")

        if not already:
            STORE.setdefault("settings", {})[EMP.PIN_KEY] = {
                "at": _now(),
                "employees":  {"count": len(emp_todo), "ids": emp_todo,
                               "monthly_salary_was": emp_had},
                "attendance": {"count": len(att_todo), "ids": att_todo,
                               "monthly_salary_was": att_had},
            }
            print(f"\nPinned at {STORE['settings'][EMP.PIN_KEY]['at']} — "
                  f"{len(emp_todo)} employee(s) and {len(att_todo)} "
                  f"marking(s) marked as old-model.")
        else:
            print(f"\nPinned moment left at {already.get('at')} — not moved.")

        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live — STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
