#!/usr/bin/env python
"""
reconcile_role_permissions.py — the permission nobody holds
============================================================

⚠ **THIS SCRIPT MUTATES LIVE ROLE RECORDS.** Take
`python tools/backup_db.py --label pre-reconcile` first, and read the override
block dated 30 August 2026 in CLIENT_CHANGES.md before running it with
`--write`. Granting a permission is a decision about **who may do what**; that
decision is the client-facing owner's and this script will not take it silently.

The defect it closes
--------------------
`auth.ensure_builtin_roles()` never rewrites an existing role's permission list,
and that is correct: once an Owner has edited what Director means, a restart
must not undo it. The cost is that **a permission minted in a later pass never
reaches a database that already has its roles.** The permission exists in code,
it exists on a fresh database, and on the live one no role holds it — so the
page it guards is unreachable by everybody, **including the Owner**, because
`auth._gate()` has no Owner bypass.

That has now shipped three times:

    B6        the four `*.approve` permissions   repaired by a one-off in
                                                 tools/backfill_created_by.py
    C4 / C5   `employee.*`, `attendance.*`       unnoticed for a day
    C2        `measurement.*`                    repaired by a one-off in
                                                 tools/backfill_measurement_pin.py

Two of those repairs were the same twenty lines pasted into a migration written
for something else. **This is that repair written once**, so the next pass runs
a tool instead of copying one. The logic lives in `auth.role_permission_drift()`
and `auth.orphan_permissions()`; this file is only its command line.

`tests/test_permission_reachability.py` is the other half and the more important
one — it fails when a permission reaches no role, so the *next* occurrence is
caught before it is shipped rather than after.

What it grants
--------------
Exactly what `auth.BUILTIN_ROLES` already gives each role **in code**, and
nothing else. **It invents no policy and decides nothing**: every grant it makes
was already decided, with its reasoning recorded, in the pass that minted the
permission. It is **additive only** — it never removes a permission, so an
Owner's own edits at `/roles/edit/<id>` survive it exactly as they survive
`ensure_builtin_roles()`.

Roles an Owner created by hand are never rewritten; they have no definition in
code to be reconciled against. They do count as holders in the orphan report —
the question there is whether *anybody* can reach a page.

Usage
-----
    python tools/reconcile_role_permissions.py            # dry run (default)
    python tools/reconcile_role_permissions.py --write    # grant it
    python tools/reconcile_role_permissions.py --only measurement.

`--only <prefix>` narrows both the report and the write to one permission
family, for a pass that wants to reconcile what it just built and leave older
drift for a decision of its own.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app        # noqa: E402 — boots persistence, loads STORE
import auth                # noqa: E402
import db                  # noqa: E402
from store import STORE    # noqa: E402


def _report(drift, orphans, roles_map) -> None:
    """Print the proposal. Called before any write, always, on every path."""
    print("Roles in the database           :", len(roles_map))
    print("Permissions defined in code     :", len(auth.PERMISSIONS))
    print()

    print("Permissions NO role holds — the pages nobody can open:")
    if not orphans:
        print("  (none — every permission reaches at least one role)")
    for pid in orphans:
        label, group = auth.PERMISSIONS[pid]
        print(f"  {pid:<24} {group:<16} {label}")
    print()

    print("Drift — what each builtin role is missing against the code:")
    if not drift:
        print("  (none — every builtin role holds what BUILTIN_ROLES gives it)")
    for rid, perms in sorted(drift.items()):
        print(f"  {rid}")
        for pid in perms:
            mark = "  <- held by nobody" if pid in orphans else ""
            print(f"      + {pid}{mark}")
    print()


def main() -> int:
    # `description=__doc__` would push the docstring's warning marks through the
    # Windows console codec on --help, which raises. Same reason as
    # tools/backfill_measurement_pin.py.
    ap = argparse.ArgumentParser(
        description="Reconcile stored role permissions against auth.BUILTIN_ROLES. "
                    "Read the module docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually grant (default is a dry run that writes nothing)")
    ap.add_argument("--only", default="",
                    help="restrict to permissions starting with this prefix, "
                         "e.g. --only measurement.")
    args = ap.parse_args()

    with app.app_context():
        auth.ensure_builtin_roles()          # a missing builtin is its job, not ours
        roles_map = auth.roles()

        drift = auth.role_permission_drift(roles_map)
        orphans = auth.orphan_permissions(roles_map)

        if args.only:
            drift = {rid: [p for p in perms if p.startswith(args.only)]
                     for rid, perms in drift.items()}
            drift = {rid: perms for rid, perms in drift.items() if perms}
            orphans = [p for p in orphans if p.startswith(args.only)]
            print(f"(filtered to permissions starting {args.only!r})\n")

        # Reported before anything is written, on every path — the override
        # block of 30 August 2026 forbids a silent identity mutation, and a
        # write that printed only afterwards would be one.
        _report(drift, orphans, roles_map)

        if not drift:
            print("Nothing to do.")
            return 0

        if not args.write:
            total = sum(len(p) for p in drift.values())
            print(f"DRY RUN — nothing written. {total} grant(s) across "
                  f"{len(drift)} role(s) would be made.")
            print("Re-run with --write to apply, or tick them at /roles/edit/<id>.")
            return 0

        granted = auth.apply_drift(drift, roles_map)
        print(f"! GRANTED — {granted} permission(s) added. Role records were "
              f"rewritten.")

        still = auth.orphan_permissions(roles_map)
        if still:
            print(f"\n! {len(still)} permission(s) STILL reach no role: "
                  f"{', '.join(still)}")
            print("  These are held by no builtin role in code either. Grant "
                  "them at /roles/edit/<id> or leave them deliberately unheld.")

        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live — STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
