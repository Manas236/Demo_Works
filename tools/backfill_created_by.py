#!/usr/bin/env python
"""
backfill_created_by.py — the approval system's grandfather migration
=====================================================================

⚠ **THIS SCRIPT MUTATES LIVE RECORDS.** It is the first migration since the
access-control layer that rewrites existing rows rather than only adding
behaviour. Take `python tools/backup_db.py --label pre-created-by` first, and
know that the backup taken before it is the last one matching the pre-migration
shape.

What it does
------------
Every approvable document — charges, RA bills, tax invoices, purchase orders
(`approval.DOCUMENTS`) — gains `created_by`. Records written before that field
existed have no creator, so this script marks them explicitly rather than
guessing one:

    "created_by":           None      # nobody knows, and nobody is pretending to
    "pre_approval_system":  True      # this record predates the approval system

Both, together. `created_by = None` alone would be indistinguishable from a
create route that forgot to stamp; the second field is what makes the set
countable, and countable is what makes it pinnable.

**It also grants the four new approval permissions to the builtin roles the
ladder names.** `auth.ensure_builtin_roles()` deliberately never rewrites an
existing role's permission list — once an Owner has edited what Director means,
a restart must not undo it — so on a database that already has its roles,
nobody would hold `ra.approve` and no document could ever be approved. That is
a second live mutation and it is reported separately below.

The pin
-------
The count and the moment are written to `STORE["settings"]["approval_migration"]`:

    {"at": "2026-08-29 19:55", "counts": {"charge": 12, ...}, "total": 31}

`tests/test_approval_grandfather.py` reads it and fails if any record created
after `at` lacks a `created_by`. **That test is the point of the whole rule.**
Without it "grandfathered" stops being a closed historical set and becomes a
state any future record can fall into, which is the same as not having the rule.

**Dry-run is the default** — it prints the proposal and writes nothing.

**Idempotent:** a record that already carries either field is left alone, so a
second `--write` run changes nothing. The migration record itself is written
once and not overwritten, because the pinned moment must not move — re-running
this after a month would otherwise re-open the exception for everything written
in between.

Usage
-----
    python tools/backfill_created_by.py            # dry-run (default)
    python tools/backfill_created_by.py --write    # actually write
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import approval              # noqa: E402
import auth                  # noqa: E402
import db                    # noqa: E402
from store import STORE      # noqa: E402


def _needs_mark(record) -> bool:
    """A record nobody has stamped either way."""
    return ("created_by" not in record
            and approval.GRANDFATHER_FIELD not in record)


def _role_grants() -> dict:
    """
    `{role_id: [permission, ...]}` — the approval permissions each builtin role
    on a ladder is missing.

    Owner is included because it holds everything by definition; the three
    ladder roles get exactly the permissions of the documents whose ladders name
    them. No other role is touched: an approval permission on a role the ladder
    does not name would be a grant nobody asked for.
    """
    wanted = {"role-owner": set(approval.DOCUMENTS[k]["permission"]
                                for k in approval.DOCUMENTS)}
    for key, spec in approval.DOCUMENTS.items():
        for slug in spec["steps"]:
            wanted.setdefault(f"role-{slug}", set()).add(spec["permission"])

    out = {}
    for rid, perms in wanted.items():
        role = auth.roles().get(rid)
        if not role:
            continue
        missing = sorted(perms - set(role.get("permissions") or []))
        if missing:
            out[rid] = missing
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="actually write (default is a dry run)")
    args = ap.parse_args()

    with app.app_context():
        auth.ensure_builtin_roles()

        already = approval.migration_record()
        if already:
            print(f"! The migration has already run at {already.get('at')} "
                  f"({already.get('total')} records marked).")
            print("  The pinned moment is not moved. Only unmarked records "
                  "below would be touched.\n")

        counts, total = {}, 0
        for key in approval.DOCUMENTS:
            coll = approval.records(key)
            todo = [rid for rid, rec in coll.items() if _needs_mark(rec)]
            counts[key] = len(todo)
            total += len(todo)
            label = approval.DOCUMENTS[key]["label"]
            print(f"{label:>16}: {len(todo):>4} of {len(coll):>4} to mark")
            if args.write:
                for rid in todo:
                    coll[rid]["created_by"] = None
                    coll[rid][approval.GRANDFATHER_FIELD] = True

        print(f"{'TOTAL':>16}: {total:>4}")

        grants = _role_grants()
        print("\nApproval permissions missing from builtin roles:")
        if not grants:
            print("  (none — every ladder role already holds them)")
        for rid, perms in sorted(grants.items()):
            print(f"  {rid:>22}: {', '.join(perms)}")
            if args.write:
                role = auth.roles()[rid]
                role["permissions"] = sorted(set(role.get("permissions") or [])
                                             | set(perms))

        if not args.write:
            print("\nDRY RUN — nothing written. Re-run with --write.")
            return 0

        if not already:
            STORE.setdefault("settings", {})[approval.MIGRATION_KEY] = {
                "at":     approval._now(),
                "counts": counts,
                "total":  total,
            }
            print(f"\nPinned at {STORE['settings'][approval.MIGRATION_KEY]['at']} "
                  f"— {total} record(s) grandfathered.")
        else:
            print(f"\nPinned moment left at {already.get('at')} — not moved.")

        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("⚠ Database not live — STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
