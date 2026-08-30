#!/usr/bin/env python
"""
backfill_project_sites.py — link project site strings to the address book
==========================================================================

⚠ **THIS SCRIPT MUTATES LIVE PROJECT RECORDS AND CREATES ADDRESS RECORDS.**
Take `python tools/backup_db.py --label pre-project-sites` first.

What it does
------------
`projects.site_address` was **free text** until 30 August 2026, which is why
this database holds *"Banglore, Karnataka"* on two projects and *"Bangalore,
Karnataka"* on a third — one place, two spellings. A project's site is a **join
key**, and free text cannot join.

This walks `STORE["projects"]` and, for each distinct non-empty `site_address`
string, does one of two things:

| stored `site_address` | what happens |
|---|---|
| **matches an address label EXACTLY** | linked — `site_address_id` set to that address |
| anything else, non-blank | an address is **CREATED**, `type: "site"`, label = the string **verbatim** |
| blank | nothing. No site was recorded and none is invented. |

⚠ **"EXACTLY" MEANS EXACTLY, AND THE NARROWNESS IS THE WHOLE POINT.** The
comparison is `str.strip()` and nothing else — no casefolding, no
whitespace-collapsing, no punctuation-stripping, no prefix match. **Nothing is
fuzzy-matched.** This is the rule `tools/backfill_site_links.py` set for the
muster, and it exists because a wrong automatic match puts a project on the
wrong site and looks exactly like a right one. This repository has already paid
for that lesson once, in `po_parts.py`, where 156 invented aliases put two
placeholder rates on one physical part depending on how somebody typed it —
ABOUT.md §2h is the rule that came out of it.

⚠ **NO SPELLING IS CORRECTED.** *"Banglore, Karnataka"* becomes an address
record spelled *"Banglore, Karnataka"*. Creating it as *"Bangalore"* would be a
silent edit of the client's own record of where his work happened.

⚠ **`site_address` IS NOT REWRITTEN.** It is the label snapshot now, and on a
record this script creates an address for, it **already holds exactly the right
value** — the address was made from it. Rewriting it would be a no-op that
looked like a migration.

What is PRINTED and never applied
---------------------------------
Three reports, all advisory. **None of them changes a record.**

1. **Near misses** — a string that would have matched an existing address if you
   casefolded it or collapsed its whitespace, printed with the address it nearly
   matched. `backfill_site_links.py`'s machinery exactly.
2. **The duplicate report** — sets of **newly-created** addresses whose labels
   differ only by a small edit distance. ⚠ You **will** see *"Banglore,
   Karnataka"* and *"Bangalore, Karnataka"* here. **They are not folded.** A
   human resolves it by repointing one project onto the other address and then
   deleting the address that is left unreferenced — `address.references_of()`
   refuses the deletion until it is, and `/address/view/<id>` shows the count.
3. **The site→project ambiguity count** — for each address, how many live
   projects point at it. The client has said **one project = one site**; he has
   **NOT** said one site = one project, and this database already has more than
   one project on one string. ⚠ **No guard is built on this.** It is evidence
   for the pass that answers CC-2's Open question 4 and eventually builds C6.

**Dry-run is the default** — it prints the whole proposal and writes nothing.

**Idempotent:** a project already carrying a non-empty `site_address_id` is
skipped, so a second run neither re-links nor creates a second address for the
same string. Mapping a project by hand afterwards is not undone by re-running.

⚠ **It grants no permission and touches no identity data**, for the reason
`backfill_day_rate.py` gives.

Usage
-----
    python tools/backfill_project_sites.py            # dry-run (default)
    python tools/backfill_project_sites.py --write    # create and link
"""

import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import address as AD         # noqa: E402
import db                    # noqa: E402
import project as PJ         # noqa: E402
from store import STORE      # noqa: E402


def _exact_index() -> dict:
    """`{label: id}` for exact matching. See the docstring on what exact means."""
    return {str(a.get("label") or "").strip(): aid
            for aid, a in (STORE.get("addresses") or {}).items()
            if str(a.get("label") or "").strip()}


def _loose(s) -> str:
    """The comparison a careless implementation would have used. REPORTING ONLY."""
    return " ".join(str(s or "").split()).casefold()


def _near_misses(site: str, index: dict) -> list:
    """
    Labels that would match if somebody were less careful.

    ⚠ **Reported and NEVER applied.** The script has no opinion about whether
    `Banglore` is `Bangalore`, and inventing one is how a project lands on the
    wrong site.
    """
    want = _loose(site)
    return sorted(label for label in index
                  if _loose(label) == want and label.strip() != site.strip())


def _edit_distance(a: str, b: str) -> int:
    """Plain Levenshtein. Used for the duplicate REPORT and for nothing else."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _duplicate_pairs(labels: list, limit: int = 3) -> list:
    """
    `[(a, b, distance), …]` — labels close enough to be one place typed twice.

    ⚠ **Printed, never folded.** Two addresses one letter apart are two records
    until a person says otherwise; folding them silently picks a spelling for
    the client.
    """
    out = []
    labels = sorted(set(labels))
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if abs(len(a) - len(b)) > limit:
                continue
            d = _edit_distance(a, b)
            if 0 < d <= limit:
                out.append((a, b, d))
    return sorted(out, key=lambda r: (r[2], r[0]))


def _classify(proj, index) -> tuple:
    """`(action, payload)` — `"skip"`, `"link"` with an id, or `"create"`."""
    if str(proj.get(PJ.SITE_ADDRESS_ID_FIELD) or "").strip():
        return "skip", "already linked"
    site = str(proj.get("site_address") or "").strip()
    if not site:
        return "skip", "no site recorded"
    aid = index.get(site)
    if aid:
        return "link", aid
    return "create", site


def main() -> int:
    # `description=__doc__` would push the docstring's warning marks through the
    # Windows console codec on --help, which raises.
    ap = argparse.ArgumentParser(
        description="Link project site strings to the address book. Read the "
                    "module docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually create and link (default is a dry run)")
    args = ap.parse_args()

    with app.app_context():
        index = _exact_index()
        print(f"Addresses in the book : {len(index)}")
        for label, aid in sorted(index.items()):
            atype = (STORE["addresses"][aid].get("type") or "")
            mark = "  <- offerable as a site" if atype in AD.SITE_TYPES else ""
            print(f"    {label!r:<40} {atype:<10}{mark}")

        projects = STORE.get("projects") or {}
        plan = {}
        to_create = {}          # {site string: [project ids]}
        for pid, proj in sorted(projects.items()):
            action, payload = _classify(proj, index)
            plan[pid] = (action, payload)
            if action == "create":
                to_create.setdefault(payload, []).append(pid)

        linked = sum(1 for a, _ in plan.values() if a == "link")
        creating = sum(1 for a, _ in plan.values() if a == "create")
        skipped = sum(1 for a, _ in plan.values() if a == "skip")

        print(f"\nprojects     : {len(plan)} record(s)")
        print(f"  linked to an EXISTING address : {linked}")
        print(f"  address to be CREATED         : {creating}"
              f"  ({len(to_create)} distinct string(s))")
        print(f"  skipped                       : {skipped}")
        for pid, (action, payload) in plan.items():
            site = str(projects[pid].get("site_address") or "")
            name = str(projects[pid].get("name") or "")
            print(f"      {action:<7} {name[:22]!r:<24} {site!r:<28} {payload}")

        # ── Near misses ───────────────────────────────────────────────────
        print("\n" + "=" * 68)
        print("NEAR MISSES - printed, NEVER applied")
        print("=" * 68)
        any_near = False
        for site in sorted(to_create):
            near = _near_misses(site, index)
            for label in near:
                any_near = True
                print(f"  {site!r:<32} ~ nearly matches address {label!r}")
        if not any_near:
            print("  (none)")
        print("\n  ! Nothing above was matched automatically. A wrong match")
        print("    puts a project on the wrong site and looks exactly like a")
        print("    right one.")

        # ── The duplicate report ──────────────────────────────────────────
        print("\n" + "=" * 68)
        print("DUPLICATE REPORT - newly-created labels a letter or two apart")
        print("=" * 68)
        pairs = _duplicate_pairs(list(to_create))
        if not pairs:
            print("  (none)")
        for a, b, d in pairs:
            print(f"  {a!r}")
            print(f"  {b!r}      (edit distance {d})")
            print(f"      -> NOT folded. One place spelled two ways is still two")
            print(f"         records until a person says otherwise. Resolve it by")
            print(f"         repointing one project onto the other address, then")
            print(f"         deleting the address that is left unreferenced.")

        # ── Site -> project ambiguity ─────────────────────────────────────
        print("\n" + "=" * 68)
        print("SITE -> PROJECT AMBIGUITY - evidence for a later pass (C6)")
        print("=" * 68)
        counts = {}
        for pid, (action, payload) in plan.items():
            key = payload if action in ("link", "create") else None
            if key is None:
                key = str(projects[pid].get(PJ.SITE_ADDRESS_ID_FIELD) or "") or None
            if key:
                counts[key] = counts.get(key, 0) + 1
        multi = 0
        for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0]))):
            label = (STORE.get("addresses") or {}).get(key, {}).get("label") or key
            flag = "  <- MORE THAN ONE PROJECT ON ONE SITE" if n > 1 else ""
            if n > 1:
                multi += 1
            print(f"  {str(label)!r:<40} {n} project(s){flag}")
        if not counts:
            print("  (no project names a site)")
        print(f"\n  ! {multi} address(es) carry more than one project. The client")
        print("    has said one project = one site; he has NOT said one site =")
        print("    one project. NO GUARD IS BUILT ON THIS - it is evidence for")
        print("    the pass that answers CC-2 Open question 4 and builds C6.")

        if not args.write:
            print("\nDRY RUN - nothing written. Re-run with --write.")
            return 0

        created_ids = {}
        for site, pids in sorted(to_create.items()):
            new_id = str(uuid.uuid4())
            # ⚠ The label is the string VERBATIM. No spelling is corrected.
            STORE["addresses"][new_id] = {
                "id": new_id, "label": site, "type": "site",
                "contact_name": "", "company": "",
                "line1": "", "line2": "", "landmark": "",
                "city": "", "state": "", "pincode": "", "country": "India",
                "phone": "", "email": "", "gstin": "",
            }
            created_ids[site] = new_id
            print(f"  created address {new_id}  {site!r}")

        for pid, (action, payload) in plan.items():
            if action == "link":
                STORE["projects"][pid][PJ.SITE_ADDRESS_ID_FIELD] = payload
            elif action == "create":
                STORE["projects"][pid][PJ.SITE_ADDRESS_ID_FIELD] = created_ids[payload]
            # ⚠ `site_address` is NOT rewritten. It is the label snapshot and it
            #   already holds exactly the right value — the address was made
            #   from it, or matched against it exactly.

        print(f"\nWritten. {len(created_ids)} address(es) created, "
              f"{linked + creating} project(s) linked.")
        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live - STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
