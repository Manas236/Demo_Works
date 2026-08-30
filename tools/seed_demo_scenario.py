#!/usr/bin/env python
"""
seed_demo_scenario.py — a coherent demo set that actually exercises the joins
=============================================================================

⚠ **THIS WRITES INTO TWO COLLECTIONS THE SUITE CLASSIFIES AS TRANSACTIONAL**,
`employees` and `attendance`. Read the next section before running it.

Authorised by the **FIFTH override block of 30 August 2026** in
`CLIENT_CHANGES.md` §0. **Not CC-2 scope**; PROGRESS.md §4c.

    python tools/seed_demo_scenario.py            # dry run — prints the plan
    python tools/seed_demo_scenario.py --write    # create it
    python tools/seed_demo_scenario.py --purge    # remove exactly what it made

════════════════════════════════════════════════════════════════════════════
⚠ WHY THIS IS A TOOL AND NOT A SEEDER, AND WHY THAT DISTINCTION IS THE POINT
════════════════════════════════════════════════════════════════════════════

`tests/test_hardening.py::test_every_reference_collection_has_a_seeder`
classifies `employees` and `attendance` as **transactional**, and its reasons
are still exactly right:

    a seeded employee is a **person who does not exist, carrying a salary they
    are not paid**, sitting on the register HR reads

    a seeded marking says somebody was **on a site on a day** and puts a wage
    against it — inventing a day's labour cost is worse than inventing the
    person it is attributed to

**None of that is relaxed.** What this is, is a **command line an operator
types**, on a development database, deliberately. It is not part of the
application:

- **Nothing imports it.** Not `app.py`, not a blueprint, not a request hook,
  not a render path. `tests/test_seed_demo_scenario.py` walks every module in
  the repository root and fails if one so much as names it.
- **A fresh install is still empty.** `test_hardening.py`'s guarantee is about
  what the *app* does when you visit `/`, `/product/`, `/boq/` and the rest. It
  is untouched, and it stays green.
- ⚠ **The marker below exists for `--purge`, not to hide from a test.**
  `test_hardening.py` **inspects no record's fields** — it empties the
  collections, runs the app's seeders, and looks for rows. Nothing an operator
  writes from a terminal is visible to it, so there was never a shape to avoid.
  The marker's whole job is making the removal exact.

⚠ **A LAST-PASS DEFECT THAT MUST NOT COME BACK:** something in the app seeded
demo data as a side effect of rendering. It was fixed, and this file is
structured so it cannot recur — the writing lives behind `main()` and an
explicit flag, and the test named above is what keeps it there.

════════════════════════════════════════════════════════════════════════════
WHAT IT MAKES, AND WHY THAT SHAPE
════════════════════════════════════════════════════════════════════════════

**Two sites, one project on each.** Enough for `/attendance/`'s site-wise table
to have two rows and for the project page's Site Labour section to show a
site's markings under the project that shares it.

⚠ **NO THIRD PROJECT SHARING A SITE, deliberately.** The site→project ambiguity
is **already real on this database** — after the fifth-pass cleanup,
`'Bangalore, Karnataka'` carries four projects — and a demo that manufactures a
second one would make a live data problem look like a fixture. The ambiguity
note on the project page has something true to say without help from here.

**Three employees with confirmed day rates**, in a range that reads like real
Indian site labour rather than round numbers: a supervisor, a fitter and a
helper. ⚠ **None carries `rate_model: pre_day_rate`** — that marker is a
**closed historical set** (`tests/test_day_rate_pin.py` fails if a record
created after the migration carries it), and a demo row must never join it.

**Markings across three days**, so both tables have something to show, with
**one absentee** so the zero-cost path renders — a present day earns a day's
wage, an absent day earns none, which is CC-2 C5's second bullet and the one
thing a reader should be able to see working.

⚠ **`(employee_id, date)` is unique** — CC-2's *"one employee = one site = one
day"* — so the plan below has at most one row per person per day, and `--write`
refuses rather than writing a second.

Idempotence
-----------
`--write` twice creates one set: every record has a fixed id derived from the
marker, so the second run finds them present and writes nothing. `--purge`
removes exactly the marked records and nothing else, and `--purge` on a clean
database is a no-op.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app          # noqa: E402 — boots persistence, loads STORE
import db                    # noqa: E402
import employee as EMP       # noqa: E402
from store import STORE      # noqa: E402


# =============================================================================
# THE MARKER — what makes --purge exact
# =============================================================================
#
# ⚠ **Every record this tool writes carries `MARKER_FIELD`, and `--purge`
#   deletes exactly the records carrying it.** Not "records whose name starts
#   with Demo", not "records created after a timestamp", not a stored list of
#   ids that can drift from what is actually in the database. A field on the
#   row is the only test that stays true if somebody renames one, and it is the
#   `approval.pre_approval_system` / `employee.rate_model` shape a third time.
#
# ⚠ **It is a distinct key, never a value smuggled into a real field.** Putting
#   "DEMO" in a name or a note would make the marker a thing a user can type,
#   and then `--purge` would delete a record somebody wrote by hand.
MARKER_FIELD = "demo_scenario"
MARKER_VALUE = "site-labour-demo-2026-08-30"

# ⚠ Ids are FIXED and derived from the marker, which is what makes `--write`
#   idempotent without a stored manifest.
def _id(kind: str, n: int) -> str:
    return f"demo-{MARKER_VALUE}-{kind}-{n}"


MARKED_COLLECTIONS = ("addresses", "projects", "employees", "attendance")


# ── The set, written out rather than generated ──────────────────────────────
#
# ⚠ Two sites, one project each. See the docstring on why there is no third
#   project sharing a site.

SITES = [
    {"n": 1, "label": "Magarpatta Tower B — Pune",
     "city": "Pune", "state": "Maharashtra", "pincode": "411028"},
    {"n": 2, "label": "Bommasandra Industrial Shed — Bengaluru",
     "city": "Bengaluru", "state": "Karnataka", "pincode": "560099"},
]

PROJECTS = [
    {"n": 1, "site": 1, "name": "Magarpatta Tower B — Fire Protection",
     "client": "Magarpatta Township Development Co."},
    {"n": 2, "site": 2, "name": "Bommasandra Shed — Hydrant & Sprinkler",
     "client": "Kohinoor Techpark Pvt. Ltd."},
]

# ⚠ Day rates, not monthly salaries, and deliberately not round numbers —
#   a demo full of ₹1,000s teaches a reader that the figures are decoration.
#   These are ordinary Indian site-labour day rates for the three grades.
EMPLOYEES = [
    {"n": 1, "site": 1, "code": "SF-D01", "name": "Ganesh Salunkhe",
     "designation": "Site Supervisor", "day_rate": 1450.0},
    {"n": 2, "site": 1, "code": "SF-D02", "name": "Imtiaz Shaikh",
     "designation": "Pipe Fitter", "day_rate": 985.0},
    {"n": 3, "site": 2, "code": "SF-D03", "name": "Lakshmi Devi",
     "designation": "Helper", "day_rate": 640.0},
]

# (employee n, date, status, ot hours). ⚠ At most ONE row per (employee, date):
# CC-2's "one employee = one site = one day", and `--write` refuses a duplicate
# rather than quietly billing a day twice.
MARKINGS = [
    (1, "2026-08-28", "present", 0.0),
    (2, "2026-08-28", "present", 2.0),
    (3, "2026-08-28", "present", 1.5),

    (1, "2026-08-29", "present", 1.0),
    # ⚠ The absentee. A present day earns a day's wage and an absent day earns
    #   none — CC-2 C5's second bullet, and the one behaviour a reader should
    #   be able to see for themselves on the page.
    (2, "2026-08-29", "absent", 0.0),
    (3, "2026-08-29", "present", 0.0),

    (1, "2026-08-30", "present", 3.0),
    (2, "2026-08-30", "present", 0.0),
]

NOW = "2026-08-30 18:00"


def _s(v) -> str:
    return str(v or "").strip()


def marked(coll: str) -> dict:
    """Every record in `coll` this tool created. The whole of `--purge`'s reach."""
    return {rid: r for rid, r in (STORE.get(coll) or {}).items()
            if _s(r.get(MARKER_FIELD)) == MARKER_VALUE}


def _mark(rec: dict) -> dict:
    rec[MARKER_FIELD] = MARKER_VALUE
    return rec


def build() -> dict:
    """
    `{collection: {id: record}}` — the whole set, as data.

    Built and returned rather than written, so the dry run prints exactly what
    `--write` would store rather than a description of it.
    """
    out = {c: {} for c in MARKED_COLLECTIONS}

    site_ids = {}
    for s in SITES:
        aid = _id("addr", s["n"])
        site_ids[s["n"]] = aid
        out["addresses"][aid] = _mark({
            "id": aid, "label": s["label"], "type": "site",
            "contact_name": "", "company": "", "line1": "", "line2": "",
            "landmark": "", "city": s["city"], "state": s["state"],
            "pincode": s["pincode"], "country": "India",
            "phone": "", "email": "", "gstin": "",
        })

    for p in PROJECTS:
        pid = _id("proj", p["n"])
        aid = site_ids[p["site"]]
        out["projects"][pid] = _mark({
            "id": pid, "name": p["name"], "norm_name": p["name"].lower(),
            "client": p["client"], "notes": "",
            # ⚠ Both keys, exactly as `/projects/create` writes them: the link
            #   and the label SNAPSHOT. A demo row that carried only one would
            #   render a drift band the moment anybody opened it.
            "site_address_id": aid,
            "site_address": out["addresses"][aid]["label"],
            "created_at": NOW, "updated_at": NOW,
        })

    emp_ids = {}
    for e in EMPLOYEES:
        eid = _id("emp", e["n"])
        emp_ids[e["n"]] = eid
        aid = site_ids[e["site"]]
        out["employees"][eid] = _mark({
            "id": eid, "name": e["name"], "code": e["code"],
            "designation": e["designation"],
            "site": out["addresses"][aid]["label"],
            EMP.SITE_ADDRESS_FIELD: aid,
            EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
            "date_joined": "2026-04-01",
            # ⚠ A CONFIRMED day rate. No `rate_model` key: that marker is a
            #   closed historical set and a record written today may never
            #   join it — tests/test_day_rate_pin.py is what says so.
            "day_rate": e["day_rate"],
            "active": True, "notes": "",
            "created_at": NOW, "updated_at": NOW,
        })

    by_n = {e["n"]: e for e in EMPLOYEES}
    for i, (en, date, status, ot) in enumerate(MARKINGS, start=1):
        rid = _id("att", i)
        e = by_n[en]
        aid = site_ids[e["site"]]
        out["attendance"][rid] = _mark({
            "id": rid, "date": date,
            "employee_id": emp_ids[en],
            # ⚠ SNAPSHOTS, exactly as `/attendance/mark` writes them: the name,
            #   the code, the DAY RATE and the site LABEL. A marking is the
            #   record of a day that has happened.
            "employee_name": e["name"], "employee_code": e["code"],
            "day_rate": e["day_rate"],
            "site": out["addresses"][aid]["label"],
            EMP.SITE_ADDRESS_FIELD: aid,
            EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
            "status": status, "ot_hours": ot, "notes": "",
            "created_at": NOW, "updated_at": NOW,
        })

    return out


def conflicts(plan: dict) -> list:
    """
    Reasons not to write, checked before anything is stored.

    ⚠ Two of the app's own invariants, restated here because this tool writes
    around the routes that enforce them: an employee **code** is unique
    case-insensitively, and `(employee_id, date)` is unique on a marking. A
    demo set that violated either would put the register into a state the forms
    cannot produce, which is worse than no demo set at all.
    """
    out = []
    mine = {rid for c in MARKED_COLLECTIONS for rid in plan[c]}

    codes = {_s(e.get("code")).lower(): rid
             for rid, e in (STORE.get("employees") or {}).items()
             if rid not in mine}
    for rid, e in plan["employees"].items():
        clash = codes.get(_s(e.get("code")).lower())
        if clash:
            out.append(f"employee code {e['code']!r} is already used by {clash}")

    seen = {(_s(r.get("employee_id")), _s(r.get("date")))
            for rid, r in (STORE.get("attendance") or {}).items()
            if rid not in mine}
    for rid, r in plan["attendance"].items():
        key = (_s(r.get("employee_id")), _s(r.get("date")))
        if key in seen:
            out.append(f"a marking already exists for {key[0]} on {key[1]}")
        seen.add(key)

    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create (or remove) a coherent demo scenario that "
                    "exercises the site/project/employee/attendance joins. "
                    "Read the module docstring first.")
    ap.add_argument("--write", action="store_true", help="create the set")
    ap.add_argument("--purge", action="store_true",
                    help="remove exactly the records this tool created")
    args = ap.parse_args()

    if args.write and args.purge:
        print("! --write and --purge are mutually exclusive.")
        return 2

    with app.app_context():
        present = {c: marked(c) for c in MARKED_COLLECTIONS}
        n_present = sum(len(v) for v in present.values())

        print("=" * 74)
        print(f"marker : {MARKER_FIELD} == {MARKER_VALUE!r}")
        print(f"present: {n_present} marked record(s) — " +
              ", ".join(f"{c} {len(present[c])}" for c in MARKED_COLLECTIONS))
        print("=" * 74)

        # ── --purge ─────────────────────────────────────────────────────────
        if args.purge:
            if not n_present:
                print("\nNothing marked. --purge is a no-op.")
                return 0
            total = 0
            for c in MARKED_COLLECTIONS:
                for rid, r in present[c].items():
                    # ⚠ Re-checked at the point of deletion, not trusted from
                    #   the scan above: `marked()` is the ONE definition of
                    #   what this tool owns, and a second, looser test here is
                    #   how a purge grows past what it created.
                    assert _s(r.get(MARKER_FIELD)) == MARKER_VALUE
                    del STORE[c][rid]
                    total += 1
                    print(f"  purged {c[:-1] if c != 'attendance' else 'marking'}"
                          f" {_s(r.get('label') or r.get('name') or r.get('date'))!r}")
            print(f"\nPurged {total} record(s).")
            if db.is_live():
                db.sync(STORE)
                print("Persisted.")
            else:
                print("! Database not live — STORE changed in memory only.")
            return 0

        # ── plan ────────────────────────────────────────────────────────────
        plan = build()
        print("\nTHE SET")
        for c in MARKED_COLLECTIONS:
            print(f"\n  {c.upper()} ({len(plan[c])})")
            for r in plan[c].values():
                if c == "attendance":
                    print(f"    {r['date']}  {r['employee_code']:<7} "
                          f"{r['employee_name']:<18} {r['status']:<8} "
                          f"OT {r['ot_hours']:g}  @ {r['site']}")
                elif c == "employees":
                    print(f"    {r['code']:<7} {r['name']:<18} "
                          f"{r['designation']:<16} Rs {r['day_rate']:,.0f}/day "
                          f"@ {r['site']}")
                else:
                    print(f"    {r.get('label') or r.get('name')}")

        bad = conflicts(plan)
        if bad:
            print("\n! REFUSED — the demo set collides with live data:")
            for b in bad:
                print(f"    - {b}")
            print("  Nothing written.")
            return 1

        if not args.write:
            print("\nDRY RUN — nothing written. Re-run with --write "
                  "(or --purge to remove an existing set).")
            return 0

        created = 0
        for c in MARKED_COLLECTIONS:
            for rid, rec in plan[c].items():
                if rid in (STORE.get(c) or {}):
                    continue           # idempotent: fixed ids, already there
                STORE.setdefault(c, {})[rid] = rec
                created += 1

        print(f"\nWritten. {created} record(s) created "
              f"({n_present} were already present).")
        if db.is_live():
            db.sync(STORE)
            print("Persisted.")
        else:
            print("! Database not live — STORE changed in memory only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
