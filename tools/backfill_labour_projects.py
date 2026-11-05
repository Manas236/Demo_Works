#!/usr/bin/env python
"""
backfill_labour_projects.py — put existing labour on its project, where it is certain
====================================================================================

⚠ **THIS SCRIPT MUTATES LIVE ATTENDANCE RECORDS.** It takes a backup itself
when MySQL is reachable (`tools/backup_db.py --label pre-labour-projects`,
Manas's ruling 5), and it is a **dry run by default** — it prints the whole
plan, including every row it refuses to touch, before you ever pass `--write`.

Authorised by **CLIENT_CHANGES.md §0's sixty-sixth block**, Manas's **ruling
5** of 5 November 2026: *"Backfill for existing data:
tools/backfill_labour_projects.py with --dry-run (default) and --write.
Assigns markings only where unambiguous (site with one project, or overhead).
Lists every ambiguous worker-month for the screen. Never changes days, rates
or slips. Backup via tools/backup_db.py first if MySQL is reachable."*

    python tools/backfill_labour_projects.py              # dry run — the plan
    python tools/backfill_labour_projects.py --dry-run    # the same thing, said
    python tools/backfill_labour_projects.py --write      # apply it

What it does
------------
`docs/LABOUR_PL.md` is the diagnosis. The short version: the project P&L joins
on a marking's `project_id`, and almost nothing in a real database carries one
— every marking written before 30 August 2026, and everything the old
per-SITE import put in. This is the bulk pass over that backlog.

For each marking with **no** `project_id` and **not** marked overhead:

| projects at its site | what happens |
|---|---|
| **exactly one** | linked. `project_id` set, `project_name` **snapshotted** from it |
| **two or more** | ⚠ left, and reported **as a worker-month** for `/attendance/unassigned` |
| **zero** | ⚠ left, and reported. Nothing to assign to until a project is filed there |
| no site at all | ⚠ left, and reported separately. There is no site to ask the question of |

⚠ **IT NEVER GUESSES, AND THE AMBIGUOUS LIST IS THE DELIVERABLE.** It does not
take the oldest project, the newest, the closest name, or the one with the most
markings on it already. A wrong automatic match puts a day's labour cost against
a project nobody chose and **looks exactly like a right one** — `po_parts.py`'s
156 invented aliases in a third register (ABOUT.md §2h), and
`tools/backfill_site_links.py`'s rule one collection along.

⚠ **IT NEVER MARKS ANYTHING OVERHEAD.** Ruling 5 says *"or overhead"* among
the unambiguous cases, and the only unambiguous overhead is a marking that
**already carries** `attendance.OVERHEAD_FIELD` — which this script then counts
and leaves alone. Deciding that a site with no project is "probably the office"
is exactly the guess the paragraph above refuses: a site with no project may be
a site whose project has not been filed yet, and the two are told apart by a
person, on `/attendance/unassigned`, with one click.

⚠ **IT NEVER CHANGES A DAY, A RATE OR A SLIP** — ruling 5's own words. One
field on one collection: `project_id`, and the `project_name` snapshotted
beside it. No status, no `ot_hours`, no `day_rate`, no site, no employee, no
payslip, nothing deleted. `tests/test_backfill_labour_projects.py` asserts a
digest of every other field before and after.

⚠ **A marking that already carries a `project_id` is never touched**, not even
to refresh the snapshotted name. That name is the record of what the project
was called on the day the marking was attributed, and re-snapshotting it is the
history-rewriting every freeze contract in this app exists to prevent
(`proforma.prior_invoiced`, `ra.prev_balance`, and this record's own
`day_rate`).

⚠ **A worker-month whose payslip is already ISSUED is linked all the same, and
that is the point.** The slip is what the project's labour cost becomes
(ruling 1) — until the days are on a project, the slip's money is on no
project's P&L at all. The slip itself is not touched.

Idempotence
-----------
A second run finds every previously-linked marking already carrying a
`project_id` and skips it, so it links nothing and writes nothing. The
ambiguous, no-project and site-less rows are reported again — they are still
unresolved, and a report that went quiet the second time would hide them.

Relationship to `tools/backfill_marking_projects.py`
----------------------------------------------------
That script (30 August 2026, the §0 sixth override block) does the same
one-project-at-the-site link and is **kept, working, and tested**. This one is
the ruling-5 tool and supersedes it for this pass, because it differs in four
ways that matter now and did not exist then:

1. it **reports by worker-month**, which is the grain `/attendance/unassigned`
   assigns at — the old one printed markings, and a month of one worker is 26
   of them;
2. it knows about **overhead** (`OVERHEAD_FIELD`), counts it, and excludes it
   from the backlog, so the figure it prints matches the screen's;
3. it **takes the backup itself** rather than telling you to;
4. it prints the **cost** of what is waiting, through
   `attendance.labour_split_of()`, so the size of the backlog is a figure
   somebody can act on rather than a row count.

Neither writes anything the other would undo. Running both is harmless.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app          # noqa: E402 — boots persistence, loads STORE
import attendance as AT      # noqa: E402 — projects_on_site(), the ONE rule
import db                    # noqa: E402
import employee as EMP       # noqa: E402 — SITE_ADDRESS_FIELD, the one spelling
from store import STORE      # noqa: E402


# ⚠ **The candidate rule is `attendance.projects_on_site()` and is NOT copied
#   here.** The form, the validator, the import, the screen and this script
#   have to agree about which projects are at a site; five copies is how
#   `docsheet.py` found four letterheads that had already drifted.

LINK = "link"
NO_PROJECT = "no-project"
AMBIGUOUS = "ambiguous"
HAS_PROJECT = "has-project"
OVERHEAD = "overhead"
NO_SITE = "no-site"

# The fields this script is not allowed to touch, checked rather than trusted —
# ruling 5's *"Never changes days, rates or slips."*
UNTOUCHED = ("date", "employee_id", "employee_name", "employee_code",
             "day_rate", "status", "ot_hours", "site", "site_address_id",
             "site_source", "notes", "import_batch", "monthly_salary",
             "rate_model", AT.OVERHEAD_FIELD)


def _s(v) -> str:
    return str(v or "").strip()


def classify(marking) -> tuple:
    """
    `(action, payload)` for one marking. Reads; writes nothing.

    Separated from the writing so the dry run and the real run cannot disagree
    about what would happen — `tools/clean_site_data.py`'s two-pass shape, and
    the reason it has it.
    """
    if _s(marking.get("project_id")):
        return HAS_PROJECT, None
    if AT.is_overhead(marking):
        return OVERHEAD, None

    aid = _s(marking.get(EMP.SITE_ADDRESS_FIELD))
    if not aid:
        return NO_SITE, None

    candidates = AT.projects_on_site(aid)
    if len(candidates) == 1:
        return LINK, candidates[0]
    if not candidates:
        return NO_PROJECT, []
    return AMBIGUOUS, candidates


def fingerprint(marking) -> tuple:
    """Every field this script may not change, so "may not" can be CHECKED."""
    return tuple(repr(marking.get(k)) for k in UNTOUCHED)


def _label(marking) -> str:
    return (f"{_s(marking.get('date')) or '(no date)'}  "
            f"{_s(marking.get('employee_code')) or '-':<8} "
            f"{_s(marking.get('employee_name')) or '(unnamed)':<18} "
            f"site={_s(marking.get('site')) or '(none)'!r}")


def _rs(v) -> str:
    return "-" if v is None else f"{v:,.2f}"


def inventory(title: str) -> None:
    """The before/after count, so a run is checkable rather than trusted."""
    markings = list((STORE.get("attendance") or {}).values())
    with_project = sum(1 for r in markings if _s(r.get("project_id")))
    with_site = sum(1 for r in markings
                    if _s(r.get(EMP.SITE_ADDRESS_FIELD)))
    overhead = sum(1 for r in markings if AT.is_overhead(r))
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")
    print(f"  attendance markings          : {len(markings)}")
    print(f"  carrying a project_id        : {with_project}")
    print(f"  marked overhead              : {overhead}")
    print(f"  carrying a site_address_id   : {with_site}")
    print(f"  projects in the register     : {len(STORE.get('projects') or {})}")
    waiting = AT.unassigned_worker_months()
    cost = AT.labour_split_of(AT.markings_unassigned())
    print(f"  UNASSIGNED worker-months     : {len(waiting)}"
          f"  ({cost['markings']} marking(s), {_rs(cost['total'])})")


def main(argv=None) -> int:
    # `description=__doc__` would push the docstring's warning marks through
    # the Windows console codec on --help, which raises.
    ap = argparse.ArgumentParser(
        description="Put existing labour on its project where the site "
                    "carries exactly one. Read the module docstring before "
                    "running with --write.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and write nothing (the default)")
    ap.add_argument("--write", action="store_true",
                    help="actually link (default is a dry run)")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the automatic backup with --write. Only for a "
                         "box whose backups are taken another way.")
    args = ap.parse_args(argv)

    if args.dry_run and args.write:
        print("! --dry-run and --write contradict each other. Pick one.")
        return 2

    with app.app_context():
        inventory("BEFORE")

        markings = STORE.get("attendance") or {}
        before = {rid: fingerprint(r) for rid, r in markings.items()}
        was_project = {rid: _s(r.get("project_id"))
                       for rid, r in markings.items()}
        plan = {}
        for rid, r in sorted(markings.items(),
                             key=lambda kv: (_s(kv[1].get("date")),
                                             _s(kv[1].get("employee_code")))):
            plan[rid] = classify(r)

        def _of(action):
            return [(rid, p) for rid, (a, p) in plan.items() if a == action]

        to_link = _of(LINK)
        ambiguous = _of(AMBIGUOUS)
        no_project = _of(NO_PROJECT)
        has_project = _of(HAS_PROJECT)
        overhead = _of(OVERHEAD)
        no_site = _of(NO_SITE)

        print(f"\nPLAN over {len(plan)} marking(s)")
        print(f"  to LINK (site carries exactly one project) : {len(to_link)}")
        print(f"  left: site carries MORE THAN ONE project   : {len(ambiguous)}")
        print(f"  left: site carries NO project              : {len(no_project)}")
        print(f"  left: already carries a project            : {len(has_project)}")
        print(f"  left: marked OVERHEAD on purpose           : {len(overhead)}")
        print(f"  left: no site linked at all                : {len(no_site)}")

        if to_link:
            print("\nWOULD LINK")
            for rid, proj in to_link:
                print(f"  {_label(markings[rid])}")
                print(f"      -> {_s(proj.get('name'))!r}  ({_s(proj.get('id'))})")

        # ⚠ **THE WORKER-MONTH LIST IS THE DELIVERABLE**, printed in full with
        #   every candidate named. Ruling 5: *"Lists every ambiguous
        #   worker-month for the screen."* A count with no names is not
        #   something anybody can act on; it is NOT truncated and there is
        #   deliberately no --quiet.
        waiting = AT.unassigned_worker_months()
        if waiting:
            print(f"\n! {len(waiting)} worker-month(s) LEFT FOR A PERSON. "
                  f"Nothing is guessed.")
            print("  Resolve them at /attendance/unassigned — one choice per "
                  "worker-month, logged,")
            print("  and it offers exactly the candidates named below, plus "
                  "'No project (overhead)'.")
            for g in waiting:
                print(f"\n  {g['employee_name'] or '(unnamed)':<20} "
                      f"{g['month'] or '(no month)'}   "
                      f"{len(g['markings'])} marking(s), "
                      f"{g['days']:g} paid day(s), "
                      f"{_rs(g['cost']['total'])}")
                sites = ", ".join(lbl or "(none)" for _a, lbl in g["sites"])
                print(f"      site(s): {sites or '(no site on the marking)'}")
                if g["paid"]:
                    print("      ⚠ the payslip for this month is ISSUED — its "
                          "wages are on no project's P&L")
                if g["candidates"]:
                    seen = set()
                    print("      candidates:")
                    for pid, name, _aid in g["candidates"]:
                        if pid in seen:
                            continue
                        seen.add(pid)
                        print(f"        - {name!r}  ({pid})")
                else:
                    print("      no project is filed at that site — file one, "
                          "or mark the month overhead")

        if no_site:
            print(f"\n  {len(no_site)} marking(s) left alone - no site linked "
                  f"at all (an unmapped")
            print("  free-text string, or none recorded). There is no site to "
                  "ask the question of;")
            print("  map the site first, on /attendance/edit/<id> or with "
                  "tools/backfill_site_links.py.")
            for rid, _ in no_site:
                print(f"    {_label(markings[rid])}")

        if not args.write:
            print("\nDRY RUN - nothing written. Re-run with --write.")
            inventory("AFTER (unchanged - dry run)")
            # ⚠ **The dry run proves it wrote nothing rather than asserting
            #   it.** Every field, including `project_id` and `project_name`,
            #   compared against the snapshot taken before the plan was built.
            changed = [rid for rid, r in markings.items()
                       if fingerprint(r) != before[rid]
                       or _s(r.get("project_id")) != was_project[rid]]
            if changed:
                raise SystemExit(
                    f"A DRY RUN CHANGED {len(changed)} marking(s) — "
                    f"{changed[:5]}. That is a defect in this script, not in "
                    f"the data.")
            return 0

        # ⚠ **The backup, before the first write and not after it** — ruling 5:
        #   *"Backup via tools/backup_db.py first if MySQL is reachable."* A
        #   box with no live database has nothing to dump and is not an error;
        #   a box WITH one that cannot be dumped is, and `backup()` raises
        #   rather than warning.
        if not args.no_backup:
            if db.is_live():
                import backup_db
                backup_db.backup("pre-labour-projects")
            else:
                print("! Database not live - no backup taken (nothing to "
                      "dump; STORE changes in memory only).")

        for rid, proj in to_link:
            # ⚠ Two keys, `charge.py`'s shape: the id and the name SNAPSHOTTED
            #   beside it. The snapshot is taken here, once, and never
            #   refreshed afterwards — see the docstring.
            markings[rid]["project_id"] = _s(proj.get("id"))
            markings[rid]["project_name"] = _s(proj.get("name"))

        # ⚠ **Ruling 5's "never changes days, rates or slips", CHECKED.** A
        #   migration that merely intends to touch one field is a migration
        #   nobody can prove anything about.
        drifted = [rid for rid, was in before.items()
                   if fingerprint(markings[rid]) != was]
        if drifted:
            raise SystemExit(
                f"REFUSING TO PERSIST: {len(drifted)} marking(s) had a field "
                f"other than project_id/project_name change — {drifted[:5]}")

        print(f"\nWritten. {len(to_link)} marking(s) linked, "
              f"{len(ambiguous) + len(no_project) + len(no_site)} left for a "
              f"person, {len(overhead)} overhead left alone.")
        inventory("AFTER")

        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live - STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
