"""
tools/backfill_terms.py: give every existing BOQ and quotation its own terms
=============================================================================

CLIENT_CHANGES.md §0 ninetieth block (25 November 2026), R3. A BOQ or a
quotation prints the terms stored ON IT (`summary_terms`), never the live
/settings list. Documents raised before that block have none stored, so their
price summary page prints no terms until this runs. It COPIES the terms
library's ON-by-default terms, in library order (`pricesummary.default_terms()`;
the client's eleven unless the library was edited), into every BOQ and
quotation that LACKS the key, and touches nothing else. From 26 November 2026
(§0 ninety-first block) the /settings record is a LIBRARY; the copy is its
ticked terms, exactly what a new document starts with.

* **Dry run is the default.** It prints the counts and writes nothing.
* `--write` applies it and saves through `db.sync()`.
* **Idempotent.** A document that already carries `summary_terms`, an empty
  list included (somebody removed every term on purpose), is never touched, so
  a second `--write` changes nothing.

    python tools/backfill_terms.py            # dry run, the default
    python tools/backfill_terms.py --write    # apply

Take a backup first: `python tools/backup_db.py --label pre-backfill-terms`.
"""

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pricesummary as PS   # noqa: E402
from store import STORE     # noqa: E402

COLLECTIONS = (("boqs", "BOQ"), ("quotations", "quotation"))


def backfill(store: dict, write: bool = False) -> dict:
    """`{collection: {"total", "lacking", "written"}}`, plus `"terms"`, the
    number of terms each lacking document gets. Writes only when `write`."""
    terms = PS.default_terms()
    out = {"terms": len(terms)}
    for coll, _noun in COLLECTIONS:
        docs = store.get(coll) or {}
        lacking = [d for d in docs.values()
                   if isinstance(d, dict) and not PS.has_terms(d)]
        if write:
            for d in lacking:
                d[PS.FIELD_TERMS] = list(terms)
        out[coll] = {"total": len(docs), "lacking": len(lacking),
                     "written": len(lacking) if write else 0}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="apply the backfill (the default is a dry run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only (the default; kept for symmetry)")
    args = ap.parse_args()
    write = args.write and not args.dry_run

    import db
    if not db.init():
        print(f"  !! persistence is not live - {db.status()}")
        print("     Nothing to backfill. Check .env / MySQL.")
        return 1
    loaded = db.load_into(STORE)
    print(f"loaded {loaded} records from {db.CONFIG['name']}")

    res = backfill(STORE, write=write)
    print(f"{'WRITING' if write else 'DRY RUN'}: the library has "
          f"{res['terms']} term(s) on by default")
    for coll, noun in COLLECTIONS:
        r = res[coll]
        print(f"  {noun:9s}  {r['total']:5d} total, {r['lacking']:5d} without terms, "
              f"{r['written']:5d} written")
    if not write:
        print("dry run - nothing written. Re-run with --write to apply.")
        return 0
    written = db.sync(STORE)
    print(f"saved: {written['written']} written, {written['deleted']} deleted, "
          f"failed: {written['failed'] or 'none'}")
    return 0 if not written["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
