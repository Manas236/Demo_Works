#!/usr/bin/env python
"""
backfill_site_links.py — link existing site strings to the address book
=======================================================================

⚠ **THIS SCRIPT MUTATES LIVE EMPLOYEE AND ATTENDANCE RECORDS.** Take
`python tools/backup_db.py --label pre-site-links` first.

What it does
------------
`site` on the employee master and on an attendance marking was **free text**
until 30 August 2026, which is why one place is spelled more than one way across
this database. The owner corrected that: sites come from the **address book**.

This walks both collections and decides one of two things per record:

| stored `site` | what happens |
|---|---|
| **matches an address label EXACTLY** | linked — `site_address_id` set, `site_source` = `"book"` |
| anything else, non-blank | ⚠ **left exactly as it stands**, `site_source` = `"unmapped"`, and reported |
| blank | nothing — no site was recorded and none is invented |

⚠ **"EXACTLY" MEANS EXACTLY, AND THE NARROWNESS IS THE WHOLE POINT.** The
comparison is `str.strip()` and nothing else — no casefolding, no
whitespace-collapsing, no punctuation-stripping, no prefix match. **Nothing is
fuzzy-matched**, because a wrong automatic match moves labour cost to the wrong
site and looks exactly like a right one. This repository has already paid for
that lesson once, in `po_parts.py`, where 156 invented aliases put two
placeholder rates on one physical part depending on how somebody typed it —
ABOUT.md §2h is the rule that came out of it.

**Near misses are REPORTED, never applied.** A string that would match if you
casefolded it, or collapsed its whitespace, is printed under the unmapped list
with the address it nearly matches, so a person can look at the pair and decide.
The script will not decide for them.

What an unmapped record does
----------------------------
1. it **keeps its string.** `Banglore` stays `Banglore` — it is the evidence of
   where somebody worked, and deleting it would be the silent drop this rule
   exists to prevent;
2. it carries `site_source == "unmapped"`, shows a chip on its row, and appears
   in a band on **both** registers listing every unmapped string and how many
   records carry it;
3. it is mapped by a **person**, on the edit form, by choosing the right
   address. Leaving the picker alone keeps the string exactly as it is —
   `employee.resolve_site()` is where that is guaranteed.

⚠ **It grants no permission and touches no identity data**, for the reason
`backfill_day_rate.py` gives.

**Dry-run is the default** — it prints the proposal and writes nothing.

**Idempotent:** a record already carrying `site_source` is left alone, so a
second run neither re-links nor re-marks. Mapping a record by hand afterwards is
not undone by re-running this.

Usage
-----
    python tools/backfill_site_links.py            # dry-run (default)
    python tools/backfill_site_links.py --write    # link and mark
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import db                    # noqa: E402
import employee as EMP       # noqa: E402
from store import STORE      # noqa: E402

COLLECTIONS = ("employees", "attendance")


def _exact_index() -> dict:
    """`{label: id}` for exact matching. See the docstring on what exact means."""
    return {str(a.get("label") or "").strip(): aid
            for aid, a in (STORE.get("addresses") or {}).items()
            if str(a.get("label") or "").strip()}


def _near_misses(site: str, index: dict) -> list:
    """
    Labels that would match if somebody were less careful.

    ⚠ **Reported and NEVER applied.** This is the list a human looks at; the
    script has no opinion about whether `Banglore` is `Bangalore`, and inventing
    one is how labour cost lands on the wrong site.
    """
    def loose(s):
        return " ".join(str(s or "").split()).casefold()

    want = loose(site)
    return sorted(label for label in index if loose(label) == want)


def _classify(record, index) -> tuple:
    """`(action, payload)` — `"skip"`, `"link"` with an id, or `"unmapped"`."""
    if EMP.SITE_SOURCE_FIELD in record:
        return "skip", "already classified"
    site = str(record.get("site") or "").strip()
    if not site:
        return "skip", "no site recorded"
    aid = index.get(site)
    if aid:
        return "link", aid
    return "unmapped", site


def main() -> int:
    # `description=__doc__` would push the docstring's warning marks through the
    # Windows console codec on --help, which raises.
    ap = argparse.ArgumentParser(
        description="Link existing site strings to the address book. Read the "
                    "module docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually write (default is a dry run)")
    args = ap.parse_args()

    with app.app_context():
        index = _exact_index()
        print(f"Addresses in the book : {len(index)}")
        for label, aid in sorted(index.items()):
            atype = (STORE["addresses"][aid].get("type") or "")
            mark = "  <- offerable as a site" if atype in EMP.SITE_TYPES else ""
            print(f"    {label!r:<40} {atype:<10}{mark}")

        plans = {c: {} for c in COLLECTIONS}
        unmapped = {}
        for coll in COLLECTIONS:
            for rid, r in sorted((STORE.get(coll) or {}).items()):
                action, payload = _classify(r, index)
                plans[coll][rid] = (action, payload)
                if action == "unmapped":
                    unmapped.setdefault(payload, {c: 0 for c in COLLECTIONS})
                    unmapped[payload][coll] += 1

        for coll in COLLECTIONS:
            rows = plans[coll]
            linked = sum(1 for a, _ in rows.values() if a == "link")
            unmapped_n = sum(1 for a, _ in rows.values() if a == "unmapped")
            skipped = sum(1 for a, _ in rows.values() if a == "skip")
            print(f"\n{coll:<12} : {len(rows)} record(s)")
            print(f"  linked exactly       : {linked}")
            print(f"  left UNMAPPED        : {unmapped_n}")
            print(f"  skipped              : {skipped}")
            for rid, (action, payload) in rows.items():
                if action == "skip":
                    continue
                site = str((STORE[coll][rid]).get("site") or "")
                print(f"      {action:<9} {site!r:<28} {payload}")

        print("\n" + "=" * 68)
        print("UNMAPPED SITE STRINGS — the full list, for a human to map")
        print("=" * 68)
        if not unmapped:
            print("  (none)")
        for site, counts in sorted(unmapped.items()):
            per = ", ".join(f"{n} in {c}" for c, n in counts.items() if n)
            print(f"  {site!r:<32} {per}")
            near = _near_misses(site, index)
            for label in near:
                print(f"      ~ near miss, NOT applied: address {label!r}")
            if not near:
                print("      ~ nothing in the book is even close")
        # ⚠ Plain ASCII in every print(): a warning mark here goes through the
        #   Windows console codec and raises, which is the same trap
        #   `backfill_measurement_pin.py` records against `--help`.
        print("\n  ! Nothing above was matched automatically. A wrong match "
              "moves labour")
        print("    cost to the wrong site and looks exactly like a right one.")

        if not args.write:
            print("\nDRY RUN — nothing written. Re-run with --write.")
            return 0

        for coll in COLLECTIONS:
            for rid, (action, payload) in plans[coll].items():
                r = STORE[coll][rid]
                if action == "link":
                    r[EMP.SITE_ADDRESS_FIELD] = payload
                    r[EMP.SITE_SOURCE_FIELD] = EMP.SITE_BOOK
                    # `site` is already the label by construction — it matched
                    # exactly — so it is not rewritten.
                elif action == "unmapped":
                    r[EMP.SITE_ADDRESS_FIELD] = ""
                    r[EMP.SITE_SOURCE_FIELD] = EMP.SITE_UNMAPPED

        print("\nWritten.")
        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live — STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
