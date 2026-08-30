#!/usr/bin/env python
"""
backfill_marking_projects.py — link a marking to its project, where there is one
================================================================================

⚠ **THIS SCRIPT MUTATES LIVE ATTENDANCE RECORDS.** Take
`python tools/backup_db.py --label pre-marking-projects` first. It is a **dry
run by default** and prints the whole plan, including everything it refuses to
touch, before you ever pass `--write`.

Authorised by the **SIXTH override block of 30 August 2026** in
`CLIENT_CHANGES.md` §0. ⚠ **It is not CC-2 scope**, it belongs to PROGRESS.md
§4c, and nobody may cite it as a delivered CC-2 item.

What it does
------------
An attendance marking carries a `project_id` from 30 August 2026 (ABOUT.md §3's
Attendance record, property 5). Every marking written **before** that field
existed has none — ⚠ **which means LEGACY, not "no project"** — and the form is
the only thing that writes one. This is the bulk mapping.

For each marking with a `site_address_id` and **no** `project_id`:

| projects at that site | what happens |
|---|---|
| **exactly one** | linked. `project_id` set, `project_name` **snapshotted** from it |
| **zero** | ⚠ left, and **printed**. A site with no project is legitimate |
| **two or more** | ⚠ left, and **printed with every candidate named** |

⚠ **IT NEVER GUESSES, AND THE AMBIGUOUS LIST IS THE DELIVERABLE.** It does not
take the oldest project, the newest, the one whose name looks closest, or the
one with the most markings already on it. A wrong automatic match puts a day's
labour cost against a project nobody chose and **looks exactly like a right
one** — which is `po_parts.py`'s 156 invented aliases in a third register
(ABOUT.md §2h), and `tools/backfill_site_links.py`'s rule one collection along.
The ambiguous rows are printed **in full, with their candidates**, so a human
resolves them by hand on `/attendance/edit/<id>`, where the picker offers
exactly those candidates and refuses to save without a choice.

⚠ **A marking with NO `site_address_id` is skipped and counted separately.**
Those are the unmapped ones — a free-text site string nothing in the address
book matched — and they have no site to ask the question of. Mapping the site is
`/attendance/edit/<id>`'s job or `tools/backfill_site_links.py`'s; it is not
this script's, and doing it here would be a second migration hiding inside one.

⚠ **A marking that already carries a `project_id` is never touched**, not even
to refresh the snapshotted name. That name is the record of what the project was
called on the day the marking was attributed, and re-snapshotting it would be
the history-rewriting every freeze contract in this app exists to prevent
(`proforma.prior_invoiced`, `ra.prev_balance`, and this record's own `day_rate`).

⚠ **NOTHING ELSE IS WRITTEN.** No site is remapped, no address is created, no
rate is converted, no project is renamed, no record is deleted. One field, on
one collection, under one rule.

Idempotence
-----------
A second run finds every previously-linked marking already carrying a
`project_id` and skips it, so it links nothing and writes nothing. The
ambiguous and site-less rows are reported again — they are still unresolved, and
a report that went quiet the second time would hide them.

    python tools/backfill_marking_projects.py            # dry run — the plan
    python tools/backfill_marking_projects.py --write    # apply it
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import attendance as AT      # noqa: E402 — projects_on_site(), the ONE rule
import db                    # noqa: E402
from store import STORE      # noqa: E402


# ⚠ **The candidate rule is `attendance.projects_on_site()` and is NOT copied
#   here.** The form, the validator and this script have to agree about which
#   projects are at a site; three copies is how `docsheet.py` found four
#   letterheads that had already drifted. `boq.revision_blockers()` taking the
#   claim map as an argument is the same decision — the rule lives in one place
#   and the caller comes to it.

LINK = "link"
NO_PROJECT = "no-project"
AMBIGUOUS = "ambiguous"
HAS_PROJECT = "has-project"
NO_SITE = "no-site"


def _s(v) -> str:
    return str(v or "").strip()


def _classify(marking) -> tuple:
    """
    `(action, payload)` for one marking. Reads; writes nothing.

    Separated from the writing so the dry run and the real run cannot disagree
    about what would happen — `tools/clean_site_data.py`'s two-pass shape, and
    the reason it has it.
    """
    if _s(marking.get("project_id")):
        return HAS_PROJECT, None

    aid = _s(marking.get("site_address_id"))
    if not aid:
        return NO_SITE, None

    candidates = AT.projects_on_site(aid)
    if len(candidates) == 1:
        return LINK, candidates[0]
    if not candidates:
        return NO_PROJECT, []
    return AMBIGUOUS, candidates


def _label(marking) -> str:
    return (f"{_s(marking.get('date')) or '(no date)'}  "
            f"{_s(marking.get('employee_code')) or '-':<8} "
            f"{_s(marking.get('employee_name')) or '(unnamed)':<18} "
            f"site={_s(marking.get('site')) or '(none)'!r}")


def inventory(title: str) -> None:
    """The before/after count, so a run is checkable rather than trusted."""
    markings = (STORE.get("attendance") or {}).values()
    with_project = sum(1 for r in markings if _s(r.get("project_id")))
    with_site = sum(1 for r in markings if _s(r.get("site_address_id")))
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")
    print(f"  attendance markings          : {len(list(markings))}")
    print(f"  carrying a project_id        : {with_project}")
    print(f"  carrying a site_address_id   : {with_site}")
    print(f"  projects in the register     : {len(STORE.get('projects') or {})}")


def main() -> int:
    # `description=__doc__` would push the docstring's warning marks through the
    # Windows console codec on --help, which raises.
    ap = argparse.ArgumentParser(
        description="Link an attendance marking to its project where the site "
                    "carries exactly one. Read the module docstring before "
                    "running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually link (default is a dry run)")
    args = ap.parse_args()

    with app.app_context():
        inventory("BEFORE")

        markings = STORE.get("attendance") or {}
        plan = {}
        for rid, r in sorted(markings.items(),
                             key=lambda kv: (_s(kv[1].get("date")),
                                             _s(kv[1].get("employee_code")))):
            plan[rid] = _classify(r)

        def _of(action):
            return [(rid, p) for rid, (a, p) in plan.items() if a == action]

        to_link = _of(LINK)
        ambiguous = _of(AMBIGUOUS)
        no_project = _of(NO_PROJECT)
        has_project = _of(HAS_PROJECT)
        no_site = _of(NO_SITE)

        print(f"\nPLAN over {len(plan)} marking(s)")
        print(f"  to LINK (site carries exactly one project) : {len(to_link)}")
        print(f"  left: site carries MORE THAN ONE project   : {len(ambiguous)}")
        print(f"  left: site carries NO project              : {len(no_project)}")
        print(f"  left: already carries a project            : {len(has_project)}")
        print(f"  left: no site linked at all                : {len(no_site)}")

        if to_link:
            print("\nWOULD LINK")
            for rid, proj in to_link:
                print(f"  {_label(markings[rid])}")
                print(f"      -> {_s(proj.get('name'))!r}  ({_s(proj.get('id'))})")

        # ⚠ **THE AMBIGUOUS LIST IS PRINTED IN FULL, WITH EVERY CANDIDATE
        #   NAMED.** It is the reason this script exists in the shape it does:
        #   the rows it refuses to guess at are the rows a human has to resolve,
        #   and a count with no names is not something anybody can act on. It is
        #   NOT truncated and there is deliberately no --quiet.
        if ambiguous:
            print(f"\n! {len(ambiguous)} marking(s) LEFT ALONE - the site carries "
                  f"more than one project.")
            print("  Nothing is guessed. Resolve each by hand at "
                  "/attendance/edit/<id>, where the")
            print("  picker offers exactly these candidates and refuses to save "
                  "without a choice.")
            for rid, candidates in ambiguous:
                print(f"\n  {_label(markings[rid])}")
                print(f"      id={rid}")
                print(f"      {len(candidates)} candidates:")
                for proj in candidates:
                    print(f"        - {_s(proj.get('name'))!r}  "
                          f"client={_s(proj.get('client')) or '-'!r}  "
                          f"({_s(proj.get('id'))})")

        if no_project:
            print(f"\n  {len(no_project)} marking(s) left alone - no project is "
                  f"recorded at that site.")
            print("  That is legitimate: an office or a store belongs to no "
                  "project.")
            for rid, _ in no_project:
                print(f"    {_label(markings[rid])}")

        if no_site:
            print(f"\n  {len(no_site)} marking(s) left alone - no site linked at "
                  f"all (an unmapped")
            print("  free-text string, or none recorded). There is no site to "
                  "ask the question of;")
            print("  map the site first, on /attendance/edit/<id>.")
            for rid, _ in no_site:
                print(f"    {_label(markings[rid])}")

        if not args.write:
            print("\nDRY RUN - nothing written. Re-run with --write.")
            inventory("AFTER (unchanged - dry run)")
            return 0

        for rid, proj in to_link:
            # ⚠ Two keys, `charge.py`'s shape: the id and the name SNAPSHOTTED
            #   beside it. The snapshot is taken here, once, and never refreshed
            #   afterwards — see the docstring.
            markings[rid]["project_id"] = _s(proj.get("id"))
            markings[rid]["project_name"] = _s(proj.get("name"))

        print(f"\nWritten. {len(to_link)} marking(s) linked, "
              f"{len(ambiguous) + len(no_project) + len(no_site)} left alone.")
        inventory("AFTER")

        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live - STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
