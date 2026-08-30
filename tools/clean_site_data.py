#!/usr/bin/env python
"""
clean_site_data.py — fold one duplicate address, map two strings, purge test rows
==================================================================================

⚠ **THIS SCRIPT DELETES LIVE RECORDS.** Take
`python tools/backup_db.py --label pre-clean-site-data` first. It is a **dry run
by default** and prints everything it would touch, including everything it would
cascade to, before you ever pass `--write`.

Authorised by the **FIFTH override block of 30 August 2026** in
`CLIENT_CHANGES.md` §0. **It is not CC-2 scope**, it belongs to PROGRESS.md §4c,
and nobody may cite it as a delivered CC-2 item.

What it does — three things and no fourth
------------------------------------------

**5a. Folds ONE duplicate address.** *"Banglore, Karnataka"* and *"Bangalore,
Karnataka"* are one place recorded twice, which is what
`tools/backfill_project_sites.py` created when it linked the free-text strings
**verbatim** and then printed the pair as a duplicate it deliberately did not
fold. The correctly-spelled record is canonical. Every reference is repointed
off the misspelled one using `address.references_of()` — which matches on the
**id and the snapshot string**, so a legacy record is not missed — and the
record, now unreferenced, is deleted.

⚠ **THIS IS A ONE-OFF REPOINT OF ONE NAMED PAIR AND IT IS NOT A MERGE ENGINE.**
The two labels are constants at the top of this file. There is no
`--merge A B`, no similarity threshold, and nothing here generalises. A reusable
address-merge operation is a different thing with a different blast radius, it
was explicitly not authorised, and building one "while we are here" is how a
tool that folded one known pair becomes a tool that folds pairs nobody checked.

⚠ **If `references_of()` still returns rows after the repoint, this STOPS** and
does not delete. It does not force, and it does not fall back to a blind
`del`. A refusal there means something points at that address by a route this
script does not know about, and guessing is exactly the wrong move.

**5b. Repoints the unmapped `Banglore` strings.** A record whose `site` is the
bare string `Banglore` with no id — `site_source == "unmapped"` — is pointed at
the canonical address. ⚠ **A record the purge below removes is SKIPPED and
said so**, because repointing a row on its way to deletion is work that reports
a number nobody can check afterwards.

⚠ **`Banglore` (the bare string) and `Banglore, Karnataka` (the address label)
are different strings and are handled by different steps.** 5a folds the
address; 5b maps the string. Neither is fuzzy-matched onto anything: both are
named here as constants, and the only reason it is safe to point `Banglore` at
`Bangalore, Karnataka` is that a human wrote that instruction down in the
override block.

**5c. Purges five named test records**, by exact `(name, client)` or
`(name, code)`, plus:

- every attendance marking belonging to a purged employee;
- every BOQ, purchase order and charge carrying a purged project's `project_id`.

⚠ **A PURGE THAT WOULD ORPHAN A DOCUMENT SOMEBODY MIGHT WANT STOPS AND REPORTS.**
The cascade is computed **transitively** — a project's BOQ is checked for the RA
bills, delivery challans, measurement sheets and draft POs hanging off it — and
if any exist, that purge target is **refused** and left exactly as it stands.
The rest of the run continues, and the refusal is printed at the top of the
summary where it cannot be missed. **This is not a warning that is then
overridden**: there is no `--force`, and there is deliberately no flag to add
one.

⚠ **`Sify Bangalore`, `Sify 2` and `Sify3` are NOT purge targets**, nor are
their clients or their BOQs. ⚠ **`Sify3` IS repointed by 5a**, because it sits
on the misspelled address and that address cannot be deleted while anything
points at it. A repoint onto the correct spelling of **the same physical place**
changes no fact about the project: its name, client, BOQs, charges and documents
are untouched, and the site it names is the site it always named. The override
block authorises that distinction in writing so that nobody later has to guess
whether two instructions collided.

⚠ **`Hinjewadi Project Site` is a real address and is never touched.**

**5d** reports what still carries an old-model rate marker or an unconfirmed day
rate once the purge has run.

Idempotence
-----------
Every step is a no-op on a second run: 5a finds no misspelled address, 5b finds
no unmapped string, 5c finds no target by name. The second run prints zeroes and
writes nothing — which is asserted by `tests/test_clean_site_data.py` rather
than promised here.

    python tools/clean_site_data.py            # dry run — prints the whole plan
    python tools/clean_site_data.py --write    # apply it
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import address as AD         # noqa: E402
import db                    # noqa: E402
import employee as EMP       # noqa: E402
from store import STORE      # noqa: E402


# =============================================================================
# THE NAMED CONSTANTS — everything this script acts on is written down here
# =============================================================================
#
# ⚠ Nothing below is discovered, inferred, matched by similarity or derived from
#   a threshold. If a label is not in this file it is not touched, and that is
#   the property that makes a destructive script reviewable.

CANONICAL_LABEL = "Bangalore, Karnataka"     # 5a — the correct spelling, kept
DUPLICATE_LABEL = "Banglore, Karnataka"      # 5a — the misspelling, folded away
UNMAPPED_STRING = "Banglore"                 # 5b — the bare free-text string

# 5c — deleted, and only these. `(name, client)` for a project;
#      `(name, code)` for an employee. Compared exactly, after strip().
PURGE_PROJECTS = [("Banglore", "Manas"), ("Test Supplier2", "Manas2")]
PURGE_EMPLOYEES = [("Test", "SF-100"), ("Test2", "SF-101"), ("Test3", "SF-102")]

# ⚠ Collections whose records hang off a BOQ. A purge that would strand one of
#   these is refused — see `_orphans_under_boq()`. `purchases` is on the list
#   even though a real PO is cascaded when it carries the project id directly:
#   one raised from a BOQ on a DIFFERENT project would be stranded silently.
BOQ_DEPENDANTS = ("ra_bills", "delivery_challans", "measurements",
                  "purchase_orders", "purchases")

DOC_LABEL = {
    "ra_bills": "RA bill", "delivery_challans": "delivery challan",
    "measurements": "measurement sheet", "purchase_orders": "draft PO",
    "purchases": "purchase order", "boqs": "BOQ", "charges": "charge",
}


def _s(v) -> str:
    return str(v or "").strip()


def _addr_by_label(label: str):
    """The address record with this exact label, or None. Exact after strip()."""
    for a in (STORE.get("addresses") or {}).values():
        if _s(a.get("label")) == label:
            return a
    return None


# =============================================================================
# THE INVENTORY — printed before and after, so the run is checkable
# =============================================================================

def inventory(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")

    print(f"\nPROJECTS ({len(STORE.get('projects', {}))})")
    for p in sorted(STORE.get("projects", {}).values(),
                    key=lambda r: _s(r.get("name")).lower()):
        print(f"  {_s(p.get('name')):<18} client={_s(p.get('client')):<38} "
              f"site={_s(p.get('site_address'))!r:<24} "
              f"id={_s(p.get('site_address_id')) or '-'}")

    print(f"\nADDRESSES ({len(STORE.get('addresses', {}))})")
    for a in sorted(STORE.get("addresses", {}).values(),
                    key=lambda r: _s(r.get("label")).lower()):
        n = len(AD.references_of(a.get("id")))
        print(f"  {_s(a.get('label')):<32} type={_s(a.get('type')):<9} "
              f"active={AD.is_active(a)!s:<5} refs={n}")

    print(f"\nEMPLOYEES ({len(STORE.get('employees', {}))})")
    for e in sorted(STORE.get("employees", {}).values(),
                    key=lambda r: _s(r.get("code"))):
        rate, ok = EMP.day_rate_of(e)
        print(f"  {_s(e.get('code')):<8} {_s(e.get('name')):<16} "
              f"site={_s(e.get('site'))!r:<26} "
              f"src={_s(e.get(EMP.SITE_SOURCE_FIELD)) or '-':<9} "
              f"rate={'not confirmed' if not ok else rate}")

    print(f"\nATTENDANCE ({len(STORE.get('attendance', {}))})")
    for r in sorted(STORE.get("attendance", {}).values(),
                    key=lambda x: (_s(x.get("date")), _s(x.get("employee_code")))):
        print(f"  {_s(r.get('date'))}  {_s(r.get('employee_code')):<8} "
              f"{_s(r.get('employee_name')):<16} "
              f"site={_s(r.get('site'))!r:<26} "
              f"src={_s(r.get(EMP.SITE_SOURCE_FIELD)) or '-':<9} "
              f"model={_s(r.get(EMP.RATE_MODEL_FIELD)) or '-'}")


# =============================================================================
# 5c — WHAT A PURGE WOULD REACH, and what makes it refuse
# =============================================================================

def _orphans_under_boq(boq_id: str) -> list:
    """
    Records that hang off this BOQ and would be stranded by deleting it.

    ⚠ **This is the STOP condition, and it is checked before anything is
    written.** A delivery challan is the record that goods physically left the
    yard; a measurement sheet is the ceiling an installation claim is checked
    against; an RA bill is a claim somebody gets paid on. None of them is a
    thing to delete because a project it hangs off is named like a test record.
    """
    out = []
    for coll in BOQ_DEPENDANTS:
        for r in (STORE.get(coll) or {}).values():
            if _s(r.get("boq_id")) == _s(boq_id):
                out.append((coll, r))
    return out


def plan_project_purge(proj) -> tuple:
    """
    `(cascade, blockers)` for one project.

    `cascade` is what would be deleted with it; `blockers` is what would be
    orphaned, and a non-empty `blockers` refuses the purge outright.
    """
    pid = proj.get("id")
    cascade = []

    # ⚠ **The WHOLE cascade is computed before any of it is tested for
    #   orphans.** A record that is itself being deleted cannot also be
    #   stranded by the deletion, and computing the two in one pass reported a
    #   purchase order as both — it carries the project id directly *and* hangs
    #   off the project's BOQ, and whichever loop ran first won. Two passes, so
    #   the answer does not depend on the order of a tuple at the top of a for.
    for coll in ("boqs", "purchases", "charges"):
        for r in (STORE.get(coll) or {}).values():
            if _s(r.get("project_id")) == _s(pid):
                cascade.append((coll, r))

    doomed = {(coll, r.get("id")) for coll, r in cascade}
    blockers, seen = [], set()
    for coll, r in cascade:
        if coll != "boqs":
            continue
        for dcoll, d in _orphans_under_boq(r.get("id")):
            key = (dcoll, d.get("id"))
            if key in doomed or key in seen:
                continue
            seen.add(key)
            blockers.append((dcoll, d, r))
    return cascade, blockers


def _describe(coll: str, rec) -> str:
    # ⚠ Collapsed to one line. A charge's `description` is free text somebody
    #   typed and this database has one holding a newline — which turned the
    #   cascade report, the thing a human reads before authorising a deletion,
    #   into ragged output that hides a row.
    ref = " ".join((_s(rec.get("ref")) or _s(rec.get("description"))
                    or _s(rec.get("id"))).split())
    extra = ""
    if coll == "charges":
        extra = f" ({_s(rec.get('date'))} · {_s(rec.get('person'))})"
    elif rec.get("status"):
        extra = f" (status {_s(rec.get('status'))})"
    return f"{DOC_LABEL.get(coll, coll)} {ref}{extra}"


# `attendance`[:-1] is `attendanc`. Spelled out rather than sliced.
SINGULAR = {"employees": "employee", "attendance": "attendance marking",
            "projects": "project", "boqs": "BOQ", "charges": "charge",
            "purchases": "purchase order"}


# =============================================================================
# THE RUN
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fold one duplicate address, map the unmapped site strings, "
                    "and purge five named test records. Read the module "
                    "docstring before running with --write.")
    ap.add_argument("--write", action="store_true",
                    help="actually apply the plan (default is a dry run)")
    args = ap.parse_args()

    with app.app_context():
        inventory("BEFORE")

        stopped = []            # refusals, printed loudly at the end
        counts = {"repointed": 0, "addr_deleted": 0, "mapped": 0,
                  "projects": 0, "employees": 0, "attendance": 0,
                  "boqs": 0, "purchases": 0, "charges": 0, "skipped": 0}

        # ── Work out which records the purge will remove, FIRST ─────────────
        #
        # ⚠ 5b has to know this before it repoints anything: a record on its way
        #   to deletion must be skipped, not mapped. So the purge is PLANNED
        #   before 5a and 5b run, and applied after them.
        purge_projects, purge_emp = [], []
        for name, client in PURGE_PROJECTS:
            for p in (STORE.get("projects") or {}).values():
                if _s(p.get("name")) == name and _s(p.get("client")) == client:
                    purge_projects.append(p)
        for name, code in PURGE_EMPLOYEES:
            for e in (STORE.get("employees") or {}).values():
                if _s(e.get("name")) == name and _s(e.get("code")) == code:
                    purge_emp.append(e)

        project_plans, refused_projects = {}, set()
        for p in purge_projects:
            cascade, blockers = plan_project_purge(p)
            project_plans[p["id"]] = (p, cascade, blockers)
            if blockers:
                refused_projects.add(p["id"])

        doomed_emp_ids = {e["id"] for e in purge_emp}
        doomed_att = [r for r in (STORE.get("attendance") or {}).values()
                      if _s(r.get("employee_id")) in doomed_emp_ids]
        doomed_att_ids = {r["id"] for r in doomed_att}

        # ── 5a. Fold the duplicate address ──────────────────────────────────
        print(f"\n{'=' * 74}\n5a. FOLD THE DUPLICATE ADDRESS\n{'=' * 74}")
        dup = _addr_by_label(DUPLICATE_LABEL)
        canon = _addr_by_label(CANONICAL_LABEL)
        repoint = []
        if dup is None:
            print(f"  {DUPLICATE_LABEL!r} is not in the book — nothing to fold.")
        elif canon is None:
            stopped.append(
                f"5a: the canonical address {CANONICAL_LABEL!r} does not exist. "
                f"Refusing to fold {DUPLICATE_LABEL!r} into nothing.")
            print(f"  ! STOP — {CANONICAL_LABEL!r} is not in the book.")
        else:
            refs = AD.references_of(dup["id"])
            print(f"  canonical : {CANONICAL_LABEL!r}  {canon['id']}")
            print(f"  duplicate : {DUPLICATE_LABEL!r}  {dup['id']}  "
                  f"({len(refs)} reference(s))")
            for ref in refs:
                rec = (STORE.get(ref["collection"]) or {}).get(ref["id"])
                if rec is None:
                    stopped.append(
                        f"5a: {ref['collection']}/{ref['id']} is referenced but "
                        f"not readable. Refusing to fold.")
                    continue
                repoint.append((ref, rec))
                note = ""
                if ref["collection"] == "projects" and ref["id"] in refused_projects:
                    note = "  (its purge is REFUSED below; the repoint still applies)"
                print(f"    repoint {ref['kind']} {ref['label']!r}"
                      f"  [{ref['how']}]{note}")
            if not refs:
                print("    (nothing points at it — it can simply be deleted)")

        # ── 5b. Map the unmapped site strings ───────────────────────────────
        print(f"\n{'=' * 74}\n5b. MAP THE UNMAPPED {UNMAPPED_STRING!r} STRINGS"
              f"\n{'=' * 74}")
        to_map = []
        for coll in ("employees", "attendance"):
            for rid, r in (STORE.get(coll) or {}).items():
                if not EMP.is_unmapped_site(r):
                    continue
                if _s(r.get("site")) != UNMAPPED_STRING:
                    continue
                doomed = (rid in doomed_emp_ids) or (rid in doomed_att_ids)
                who = (f"{_s(r.get('code')) or _s(r.get('employee_code'))} "
                       f"{_s(r.get('name')) or _s(r.get('employee_name'))}")
                if doomed:
                    counts["skipped"] += 1
                    print(f"  SKIP  {SINGULAR[coll]} {who.strip()} — it is on the "
                          f"5c purge list and will be deleted; repointing a row "
                          f"on its way out reports a number nobody can check.")
                else:
                    to_map.append((coll, rid, r))
                    print(f"  map   {SINGULAR[coll]} {who.strip()} "
                          f"-> {CANONICAL_LABEL!r}")
        if not to_map and not counts["skipped"]:
            print(f"  no record carries the bare string {UNMAPPED_STRING!r}.")

        # ── 5c. The purge, and what it reaches ──────────────────────────────
        print(f"\n{'=' * 74}\n5c. PURGE THE NAMED TEST RECORDS\n{'=' * 74}")
        if not purge_projects and not purge_emp:
            print("  none of the named records exists — nothing to purge.")

        for pid, (p, cascade, blockers) in project_plans.items():
            print(f"\n  PROJECT {_s(p.get('name'))!r} "
                  f"(client {_s(p.get('client'))!r})")
            if cascade:
                print("    would also delete:")
                for coll, r in cascade:
                    print(f"      - {_describe(coll, r)}")
            else:
                print("    nothing hangs off it.")
            if blockers:
                print("    ! REFUSED — deleting it would ORPHAN:")
                for dcoll, d, boq in blockers:
                    print(f"      - {_describe(dcoll, d)}  "
                          f"(hangs off {_s(boq.get('ref'))})")
                stopped.append(
                    f"5c: project {_s(p.get('name'))!r} NOT purged — deleting "
                    f"it would strand {len(blockers)} document(s) under "
                    f"{_s(cascade[0][1].get('ref')) if cascade else 'its BOQ'}. "
                    f"A human decides whether those are disposable, not this "
                    f"script.")

        for e in purge_emp:
            mine = [r for r in doomed_att if _s(r.get("employee_id")) == e["id"]]
            print(f"\n  EMPLOYEE {_s(e.get('code'))} {_s(e.get('name'))!r}")
            print(f"    would also delete {len(mine)} attendance marking(s):")
            for r in mine:
                print(f"      - {_s(r.get('date'))} at {_s(r.get('site'))!r}")

        if not args.write:
            print(f"\n{'=' * 74}")
            if stopped:
                print("REFUSALS — these are NOT applied even with --write:")
                for s in stopped:
                    print(f"  ! {s}")
                print()
            print("DRY RUN — nothing written. Re-run with --write.")
            print("=" * 74)
            return 0

        # ── APPLY ───────────────────────────────────────────────────────────
        print(f"\n{'=' * 74}\nAPPLYING\n{'=' * 74}")

        # 5a
        if dup is not None and canon is not None:
            for ref, rec in repoint:
                if ref["collection"] == "projects":
                    rec["site_address_id"] = canon["id"]
                    # ⚠ The label snapshot is rewritten HERE and only here,
                    #   because the address it points at has genuinely changed.
                    #   That is the same act as re-saving the project through
                    #   the form, and leaving it would raise `site_drift()`'s
                    #   amber band on a project this script just corrected.
                    rec["site_address"] = CANONICAL_LABEL
                else:
                    rec[EMP.SITE_ADDRESS_FIELD] = canon["id"]
                    rec["site"] = CANONICAL_LABEL
                    rec[EMP.SITE_SOURCE_FIELD] = EMP.SITE_BOOK
                counts["repointed"] += 1
                print(f"  repointed {ref['kind']} {ref['label']!r}")

            left = AD.references_of(dup["id"])
            if left:
                # ⚠ NOT forced. See the docstring.
                stopped.append(
                    f"5a: {DUPLICATE_LABEL!r} still has {len(left)} reference(s) "
                    f"after the repoint and was NOT deleted: "
                    f"{[r['label'] for r in left]}")
                print(f"  ! STOP — {len(left)} reference(s) remain; "
                      f"the address is NOT deleted.")
            else:
                del STORE["addresses"][dup["id"]]
                counts["addr_deleted"] = 1
                print(f"  deleted address {DUPLICATE_LABEL!r}")

        # 5b
        for coll, rid, r in to_map:
            r[EMP.SITE_ADDRESS_FIELD] = canon["id"]
            r["site"] = CANONICAL_LABEL
            r[EMP.SITE_SOURCE_FIELD] = EMP.SITE_BOOK
            counts["mapped"] += 1
            print(f"  mapped {SINGULAR[coll]} {rid}")

        # 5c
        for pid, (p, cascade, blockers) in project_plans.items():
            if blockers:
                print(f"  REFUSED project {_s(p.get('name'))!r} — left as it is")
                continue
            for coll, r in cascade:
                (STORE.get(coll) or {}).pop(r["id"], None)
                counts[coll] = counts.get(coll, 0) + 1
                print(f"  deleted {_describe(coll, r)}")
            STORE["projects"].pop(pid, None)
            counts["projects"] += 1
            print(f"  deleted project {_s(p.get('name'))!r}")

        for r in doomed_att:
            STORE["attendance"].pop(r["id"], None)
            counts["attendance"] += 1
        for e in purge_emp:
            STORE["employees"].pop(e["id"], None)
            counts["employees"] += 1
            print(f"  deleted employee {_s(e.get('code'))} {_s(e.get('name'))!r}")
        if counts["attendance"]:
            print(f"  deleted {counts['attendance']} attendance marking(s)")

        inventory("AFTER")

        # ── 5d ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 74}\n5d. WHAT STILL CARRIES AN OLD-MODEL RATE"
              f"\n{'=' * 74}")
        flagged = 0
        for coll in ("employees", "attendance"):
            for r in (STORE.get(coll) or {}).values():
                rate, ok = EMP.day_rate_of(r)
                marked = EMP.is_pre_day_rate(r)
                if marked or not ok:
                    flagged += 1
                    print(f"  {SINGULAR[coll]} "
                          f"{_s(r.get('code')) or _s(r.get('employee_code'))} "
                          f"{_s(r.get('name')) or _s(r.get('employee_name'))!r}"
                          f" — {'old-model marker' if marked else 'no confirmed rate'}")
        if not flagged:
            print("  nothing. Every remaining record carries a confirmed day rate.")

        print(f"\n{'=' * 74}\nSUMMARY\n{'=' * 74}")
        for k, v in counts.items():
            print(f"  {k:<14} {v}")
        if stopped:
            print("\n  ! REFUSALS — a human has to decide these:")
            for s in stopped:
                print(f"    - {s}")

        if db.is_live():
            db.sync(STORE)
            print("\nPersisted.")
        else:
            print("\n! Database not live — STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
