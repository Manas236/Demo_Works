#!/usr/bin/env python
"""
backfill_measurement_pin.py — close the pre-measurement exception
=================================================================

⚠ **THIS SCRIPT MUTATES LIVE RECORDS.** Take
`python tools/backup_db.py --label pre-measurement-pin` first.

What it does
------------
CC-2 **C2** makes an approved measurement the source of installation quantity on
RA-Installation, and **C1** refuses to raise an installation claim without one.
Every installation bill that already exists was raised before either rule did,
with a quantity typed straight into the claim grid.

Requiring a measurement retrospectively would break live records. Allowing it
silently would pretend the rule held when it did not. So the existing set is
marked explicitly and **closed**:

    "pre_measurement": True     # this claim predates the measurement document

and the count and the moment are written to
`STORE["settings"]["measurement_migration"]`:

    {"at": "2026-08-29 23:10", "count": 4, "ids": [...]}

`tests/test_measurement_pin.py` reads it and fails if an **installation** RA bill
created after `at` claims quantity with no measurement behind it. **That test is
the point of the whole rule.** Without it "pre-measurement" stops being a closed
historical set and becomes a state any future bill can fall into, which is the
same as not having the rule at all.

What a marked bill does
-----------------------
1. it **keeps its typed quantity** — nothing is recomputed and no figure moves;
2. it renders, **on screen only**, with a marker saying the quantity was typed
   rather than measured. It never reaches a printed sheet: a note on an issued
   claim saying its figures were typed is exactly the sentence nobody wants read
   by a main contractor;
3. and the arithmetic behind it is untouched — `ra.overclaims()` keeps the BOQ
   ceiling on a project with no approved measurement, which is what stops the
   bill's own chain being stranded.

The supply leg is **not** marked. C1's supply proof is a delivery challan and no
quantity flows from it, so a supply bill has nothing to be grandfathered
against.

⚠ **It does NOT grant any permission to any role.** The previous migration
(`backfill_created_by.py`) reached into `STORE["roles"]`, and the fifth
29 August 2026 override block acknowledges that retrospectively and says the
next migration touching identity data must be authorised on its own terms.
`--grant-roles` below is that authorisation, taken by a person typing the flag
— it is **off by default** and prints exactly what it would do.

**Dry-run is the default** — it prints the proposal and writes nothing.

**Idempotent:** a bill already carrying the mark is left alone, and the migration
record is written once and not overwritten. Re-running this after a month must
not move the pinned moment, or the exception re-opens for everything written in
between.

Usage
-----
    python tools/backfill_measurement_pin.py                 # dry-run (default)
    python tools/backfill_measurement_pin.py --write         # mark the bills
    python tools/backfill_measurement_pin.py --write --grant-roles
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import approval              # noqa: E402
import auth                  # noqa: E402
import db                    # noqa: E402
import measurement as MS     # noqa: E402
from store import STORE      # noqa: E402


def _measurement_role_grants() -> dict:
    """
    `{role_id: [permission, ...]}` — the measurement permissions each builtin
    role is missing.

    ⚠ **Read only unless `--grant-roles` is passed.** `auth.ensure_builtin_roles()`
    deliberately never rewrites an existing role's permission list — once an
    Owner has edited what Director means, a restart must not undo it — so on a
    database that already has its roles, nobody holds `measurement.view` and the
    whole module is unreachable until somebody says otherwise.

    Saying otherwise is a decision about **who may do what**, which is the
    client-facing owner's, so it is a flag rather than a side effect. The
    alternative is four ticks per role at `/roles/edit/<id>`, which needs no code
    and no deployment.
    """
    out = {}
    for slug, (_name, perms) in auth.BUILTIN_ROLES.items():
        rid = f"role-{slug}"
        role = auth.roles().get(rid)
        if not role:
            continue
        wanted = {p for p in perms if p.startswith("measurement.")}
        missing = sorted(wanted - set(role.get("permissions") or []))
        if missing:
            out[rid] = missing
    return out


def main() -> int:
    # `description=__doc__` would push the docstring's "warning" marks through
    # the Windows console codec on --help, which raises. The summary line is
    # enough; the reasoning is in the docstring, read in the file.
    ap = argparse.ArgumentParser(
        description="Close the pre-measurement exception (CC-2 C1/C2). "
                    "Read the module docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually write (default is a dry run)")
    ap.add_argument("--grant-roles", action="store_true",
                    help="ALSO grant the measurement permissions to the builtin "
                         "roles that carry them in code. A second, separate live "
                         "mutation — identity data, not document data — and it "
                         "is opt-in for that reason.")
    args = ap.parse_args()

    with app.app_context():
        auth.ensure_builtin_roles()

        already = MS.migration_record()
        if already:
            print(f"! The pin has already run at {already.get('at')} "
                  f"({already.get('count')} bill(s) marked).")
            print("  The pinned moment is not moved. Only unmarked bills below "
                  "would be touched.\n")

        bills = STORE.get("ra_bills") or {}
        installation = [rid for rid, b in bills.items()
                        if str(b.get("leg") or "") == "installation"]
        todo = sorted(rid for rid, b in bills.items() if MS.needs_pin(b))

        print(f"RA bills in the database        : {len(bills)}")
        print(f"  ... on the installation leg   : {len(installation)}")
        print(f"  ... claiming quantity with no")
        print(f"      approved measurement      : {len(todo)}   <- the pinned set")
        for rid in todo:
            b = bills[rid]
            qty = sum(float(c.get("qty") or 0.0) for c in b.get("claims") or [])
            print(f"        {b.get('ref') or rid:<24} RA{b.get('ra_no')} "
                  f"{b.get('project_name') or '':<24} qty {qty:g}")

        if args.write:
            for rid in todo:
                bills[rid][MS.PRE_MEASUREMENT_FIELD] = True

        grants = _measurement_role_grants()
        print("\nMeasurement permissions missing from builtin roles:")
        if not grants:
            print("  (none — every role already holds what the code gives it)")
        for rid, perms in sorted(grants.items()):
            print(f"  {rid:>22}: {', '.join(perms)}")
        if grants and not args.grant_roles:
            print("  ! NOT granted. Pass --grant-roles to write them, or tick "
                  "them at /roles/edit/<id>.")
            print("    Until one or the other happens, /measurement/ is "
                  "unreachable on this database.")
        if args.write and args.grant_roles:
            for rid, perms in grants.items():
                role = auth.roles()[rid]
                role["permissions"] = sorted(set(role.get("permissions") or [])
                                             | set(perms))
            print("  ! GRANTED — role records were rewritten.")

        if not args.write:
            print("\nDRY RUN — nothing written. Re-run with --write.")
            return 0

        if not already:
            STORE.setdefault("settings", {})[MS.PIN_KEY] = {
                "at":    approval._now(),
                "count": len(todo),
                "ids":   todo,
            }
            print(f"\nPinned at {STORE['settings'][MS.PIN_KEY]['at']} — "
                  f"{len(todo)} bill(s) grandfathered.")
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
