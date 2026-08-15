"""
tools/strip_certification.py — remove certification from stored RA bills, and
give every one of them a lifecycle status.

A one-shot migration for CLIENT_CHANGES.md item 3. Certification is gone from
the code entirely — the route, the fields, the arithmetic and the columns — so
the keys it left on `STORE["ra_bills"]` are dead weight that would otherwise sit
in the JSON blob forever, and every bill written before the change carries a
`status` from the OLD vocabulary (`draft` / `submitted` / `certified`) that the
new one does not recognise.

    python tools/strip_certification.py --dry-run     # report, change nothing
    python tools/strip_certification.py               # strip, restatus and save

**Take a backup first** — `python tools/backup_db.py --label pre-decertify` —
per INTRODUCTION.md §5.3. This script refuses to write without one on disk
unless `--force` is given, exactly as `tools/backfill_line_ids.py` does.

**It is deliberately NOT wired into app startup**, and must not be. It rewrites
stored records, and a migration that runs itself on every boot is a migration
nobody can decide not to run — `product.backfill_line_item_hsn()` and
`boq.backfill_line_ids()` are both explicit for the same reason (ABOUT.md §3).

What it does to each bill
-------------------------
1. **Deletes `certified_on`** from the bill and **`certified_qty` /
   `certified_rate`** from every claim row on it. Nothing reads them any more.
2. **Sets `status` to `"issued"`**, and adds the empty `issued_on`,
   `cancelled_on` and `cancel_reason` the new shape carries.

⚠ **EVERY existing bill becomes `issued`, including the ones stored as
  `draft`.** That is the point rather than a rounding of it. Before this change
  `status` was a certification-tracking field with no gate attached to it: it
  was written as `"draft"` by `create_ra()` and only ever moved by the certify
  form, so a bill sitting at `"draft"` says nothing about whether it was sent —
  every bill in this database was raised, printed and submitted. Leaving one as
  a draft under the NEW meaning would make an already-submitted claim editable
  and deletable, which is precisely the lock this migration exists to install.

⚠ **What is lost, stated plainly.** Any certified quantity or rate the main
  contractor had ruled and somebody had keyed in is **destroyed** by this
  script and is not recoverable from the record afterwards. That is what
  "remove it entirely, not hide it behind a flag" means, and it is why the
  backup is not optional. The dated dump in `backups/` is the only copy.

Idempotence
-----------
Running it twice touches nothing the second time, and — more importantly — a
bill created *after* the migration is never touched at all, so a legitimate new
draft is not flipped to issued by a stray re-run.

That works because a bill is only migrated when it still carries a
**certification marker**: a `certified_on` key, a `certified_qty` /
`certified_rate` key on any claim row, or a `status` outside the new vocabulary.
Every bill this app has ever written has all three — `create_ra()` always wrote
`certified_on`, and `build_claim()` always wrote the certified pair — so the
marker identifies a pre-migration record exactly. A post-migration draft has
none of them and is skipped.
"""

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import db                 # noqa: E402
import ra as RA           # noqa: E402
from store import STORE   # noqa: E402

# The keys this migration removes. Named here rather than inline so the script
# says on its face exactly what it destroys.
_BILL_KEYS = ("certified_on",)
_CLAIM_KEYS = ("certified_qty", "certified_rate")

# The lifecycle fields it adds, with the values a migrated (already submitted)
# bill gets. `issued_on` is left BLANK rather than invented: we do not know the
# date these went out, and stamping today's date onto a bill issued in June
# would be this script asserting something nobody told it.
_NEW_FIELDS = {"issued_on": "", "cancelled_on": "", "cancel_reason": ""}


def needs_migration(bill: dict) -> bool:
    """
    Does this bill still carry a certification marker?

    The idempotence test. See the module docstring — this is what stops a
    re-run from flipping a legitimately new draft to issued.
    """
    if any(k in bill for k in _BILL_KEYS):
        return True
    if str(bill.get("status") or "") not in RA.STATUSES:
        return True
    return any(k in c for c in (bill.get("claims") or []) for k in _CLAIM_KEYS)


def migrate(store: dict) -> dict:
    """
    Strip and restatus every pre-migration bill in `store`. Returns counts.

    Pure over the store it is handed, so the tests can drive it without a
    database — the same shape `boq.backfill_line_ids()` has.
    """
    bills = store.get("ra_bills") or {}
    touched, claim_rows, keys, was = 0, 0, 0, {}

    for bill in bills.values():
        if not needs_migration(bill):
            continue
        touched += 1
        old = str(bill.get("status") or "(none)")
        was[old] = was.get(old, 0) + 1

        for k in _BILL_KEYS:
            if k in bill:
                del bill[k]
                keys += 1

        for c in bill.get("claims") or []:
            hit = False
            for k in _CLAIM_KEYS:
                if k in c:
                    del c[k]
                    keys += 1
                    hit = True
            if hit:
                claim_rows += 1

        # Never left as a draft — see the docstring's second warning.
        bill["status"] = "issued"
        for k, v in _NEW_FIELDS.items():
            bill.setdefault(k, v)

    return {"bills": touched, "claim_rows": claim_rows, "keys": keys,
            "was": was, "total": len(bills)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change and write nothing")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if no backup file is present")
    args = ap.parse_args()

    if not db.init():
        print(f"  !! persistence is not live - {db.status()}")
        print("     Nothing to migrate. Check .env / MySQL.")
        return 1

    backups = list((REPO / "backups").glob("*.sql"))
    if not backups and not (args.dry_run or args.force):
        print("  !! no backup found in backups/")
        print("     Run: python tools/backup_db.py --label pre-decertify")
        print("     This migration DESTROYS certified quantities and rates.")
        return 1

    loaded = db.load_into(STORE)
    print(f"loaded {loaded} records from {db.CONFIG['name']}")

    bills = STORE.get("ra_bills") or {}
    pending = [b for b in bills.values() if needs_migration(b)]
    print(f"  {len(bills)} RA bill(s), {len(pending)} still carrying "
          f"certification")

    if not pending:
        print("  nothing to do - already migrated")
        return 0

    if args.dry_run:
        for b in sorted(pending, key=lambda x: int(x.get("ra_no") or 0)):
            n = sum(1 for c in (b.get("claims") or [])
                    if any(k in c for k in _CLAIM_KEYS))
            ruled = sum(1 for c in (b.get("claims") or [])
                        if c.get("certified_qty") is not None)
            print(f"    RA{b.get('ra_no')} {b.get('ref', '')}: "
                  f"status {b.get('status') or '(none)'!r} -> 'issued', "
                  f"{n} claim row(s) stripped"
                  + (f", {ruled} CARRY A RULING THAT WILL BE LOST" if ruled else ""))
        print("dry run - nothing written")
        return 0

    result = migrate(STORE)
    print(f"  migrated {result['bills']} of {result['total']} bill(s)")
    print(f"  stripped {result['keys']} certification key(s) across "
          f"{result['claim_rows']} claim row(s)")
    for old, n in sorted(result["was"].items()):
        print(f"    {n} bill(s) were {old!r} -> now 'issued'")

    written = db.sync(STORE)
    print(f"saved: {written['written']} written, {written['deleted']} deleted, "
          f"failed: {written['failed'] or 'none'}")
    return 0 if not written["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
