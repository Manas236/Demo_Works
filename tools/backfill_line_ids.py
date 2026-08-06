"""
tools/backfill_line_ids.py — mint `line_id` on BOQ lines that predate the field.

A one-time migration for Phase 4 step 1.5. Every BOQ line now carries an opaque
server-minted `line_id`, which is the key an RA claim is matched on; records
written before the field exists have none, and nothing can be claimed against
them until they do.

    python tools/backfill_line_ids.py --dry-run     # report, change nothing
    python tools/backfill_line_ids.py               # fill and save

**Take a backup first** — `python tools/backup_db.py --label pre-line-ids` —
per the standing rule. This script refuses to write without one on disk unless
`--force` is given.

It is idempotent: it only ever fills a **blank**. An id already on a line is
never replaced, because that id may already have claims matched against it and
reissuing it is precisely the orphaning the identifier exists to prevent.

⚠ It cannot repair RA claims written before the field existed, and does not
  try. Matching one back to a line would have to go through `item_no`, which is
  ambiguous on exactly the lines that matter — the client's section A carries
  item 17 twice — so a guess would silently attach a claim to the wrong item at
  the wrong rate. Such rows are counted and reported instead.
"""

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import boq as BQ      # noqa: E402
import db             # noqa: E402
from store import STORE  # noqa: E402


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
        print("     Run: python tools/backup_db.py --label pre-line-ids")
        return 1

    loaded = db.load_into(STORE)
    print(f"loaded {loaded} records from {db.CONFIG['name']}")

    boqs = STORE.get("boqs") or {}
    before = sum(1 for b in boqs.values()
                 for li in (b.get("line_items") or [])
                 if not BQ._line_id(li.get("line_id")))
    print(f"  {len(boqs)} BOQ record(s), {before} line(s) without an id")

    if args.dry_run:
        for bid, b in boqs.items():
            missing = sum(1 for li in (b.get("line_items") or [])
                          if not BQ._line_id(li.get("line_id")))
            if missing:
                print(f"    would fill {missing:4d} of "
                      f"{len(b.get('line_items') or []):4d} on {b.get('ref', bid)}")
        print("dry run - nothing written")
        return 0

    result = BQ.backfill_line_ids(STORE)
    print(f"  filled {result['lines']} line(s) across "
          f"{result['boqs']} BOQ record(s)")

    if result["claims_without_ids"]:
        # Loud, because the over-claim guard cannot see these rows at all.
        print(f"  !! {result['claims_without_ids']} RA claim row(s) carry no "
              f"line_id and match nothing.")
        print("     They were written before the field existed. They are NOT "
              "repaired automatically -")
        print("     matching them back would have to guess through item_no, "
              "which is ambiguous.")
    else:
        print("  0 RA claim rows without an id (expected: no RA bills exist yet)")

    written = db.sync(STORE)
    print(f"saved: {written['written']} written, {written['deleted']} deleted, "
          f"failed: {written['failed'] or 'none'}")
    return 0 if not written["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
