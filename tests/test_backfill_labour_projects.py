"""
`tools/backfill_labour_projects.py` — ruling 5's bulk pass over the backlog.

CLIENT_CHANGES.md §0's **sixty-sixth** block, Manas's **ruling 5** of
5 November 2026: *"Backfill for existing data:
tools/backfill_labour_projects.py with --dry-run (default) and --write.
Assigns markings only where unambiguous (site with one project, or overhead).
Lists every ambiguous worker-month for the screen. Never changes days, rates
or slips. Backup via tools/backup_db.py first if MySQL is reachable."*

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **IT NEVER GUESSES.** A site carrying two projects leaves its markings
   alone. A wrong automatic match puts a day's labour cost against a project
   nobody chose and **looks exactly like a right one** — `po_parts.py`'s 156
   invented aliases in a third register (ABOUT.md §2h). The temptations this
   refuses are "take the oldest", "take the newest", "take the one that
   already has the most markings", and — new to this tool — "a site with no
   project is probably the office".
2. ⚠ **IT NEVER CHANGES A DAY, A RATE OR A SLIP.** Ruling 5's own words,
   asserted by fingerprinting every other field before and after, and by the
   script's own refusal to persist if one moved.
3. ⚠ **A marking that already carries a project is never touched**, not even
   to refresh the snapshotted name — the freeze contract.
4. ⚠ **Overhead is counted and left alone**, never created.
5. **The ambiguous rows are reported AS WORKER-MONTHS**, with every candidate
   named, which is the grain `/attendance/unassigned` assigns at.
6. **A dry run writes nothing**, `--dry-run` is the default said out loud, and
   a second `--write` is a no-op.
7. ⚠ **It is unreachable from the application.**

⚠ **Do not weaken 1, 2 or 3 to make a red suite green.** Each failure means
this script can silently move somebody's wages onto the wrong project, or
change what a day was assessed at.
"""

import ast
import pathlib
import sys

import pytest

import attendance as AT
import payroll as PAY
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import backfill_labour_projects as BLP  # noqa: E402

TOUCHED = ("projects", "addresses", "attendance", "payslips", "settings")


@pytest.fixture(autouse=True)
def _clean():
    saved = {k: dict(STORE.get(k) or {}) for k in TOUCHED}
    for k in TOUCHED:
        STORE.setdefault(k, {}).clear()
    yield
    for k in TOUCHED:
        STORE.setdefault(k, {}).clear()
        STORE[k].update(saved[k])


def _addr(aid, label):
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": "site", "archived": False,
        "line1": "", "city": "", "state": "", "pincode": "",
        "country": "India"}
    return aid


def _project(pid, name, aid, client="C"):
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": name, "client": client, "notes": "",
        "site_address": "", "site_address_id": aid}
    return STORE["projects"][pid]


def _marking(rid, aid, code="SF-001", name="Ramesh", date="2026-08-30",
             **over):
    rec = {"id": rid, "date": date, "employee_id": "e-" + code,
           "employee_name": name, "employee_code": code, "day_rate": 900.0,
           "site": "Somewhere", "site_address_id": aid, "site_source": "book",
           "status": "present", "ot_hours": 0.0}
    rec.update(over)
    STORE.setdefault("attendance", {})[rid] = rec
    return rec


def _run(write=False, dry=False, extra=()):
    argv = (["--write"] if write else []) + (["--dry-run"] if dry else [])
    return BLP.main(list(argv) + list(extra))


# ═══ 1. ⚠ IT NEVER GUESSES ══════════════════════════════════════════════════

def test_a_site_with_two_projects_leaves_its_markings_alone(capsys):
    """
    ⚠ **THE SAFETY PROPERTY.** The control is in the same test: a different
    marking, at a site with exactly one project, IS linked in the same run —
    without it this would pass on a script that linked nothing at all.
    """
    crowded = _addr("a-crowded", "Jamnagar")
    lone = _addr("a-lone", "Roadpali")
    _project("p-1", "Jamnagar", crowded)
    _project("p-2", "Jamnagar Shed", crowded)
    _project("p-3", "Roadpali", lone)
    _marking("m-amb", crowded)
    _marking("m-ok", lone, code="SF-002")

    assert _run(write=True) == 0
    assert STORE["attendance"]["m-amb"].get("project_id", "") == ""
    assert STORE["attendance"]["m-ok"]["project_id"] == "p-3"
    assert STORE["attendance"]["m-ok"]["project_name"] == "Roadpali"


def test_a_site_with_no_project_is_never_called_overhead(capsys):
    """
    ⚠ **The new temptation, refused.** Ruling 5 says *"or overhead"* among the
    unambiguous cases, and the only unambiguous overhead is a marking that
    ALREADY carries the mark. A site with no project may be a site whose
    project has not been filed yet; the two are told apart by a person.
    """
    bare = _addr("a-bare", "Office")
    _marking("m-bare", bare)
    assert _run(write=True) == 0
    rec = STORE["attendance"]["m-bare"]
    assert rec.get("project_id", "") == ""
    assert AT.OVERHEAD_FIELD not in rec, (
        "the script marked a no-project site as overhead — that is a guess")
    assert len(AT.markings_unassigned()) == 1, "it is still on the worklist"


def test_a_marking_with_no_site_is_reported_and_left(capsys):
    _marking("m-nosite", "", site="Banglore", site_source="unmapped")
    assert _run(write=True) == 0
    assert STORE["attendance"]["m-nosite"].get("project_id", "") == ""
    out = capsys.readouterr().out
    assert "no site linked at all" in out
    assert "Banglore" in out


def test_the_source_names_no_project_and_takes_no_first_or_newest(capsys):
    """
    ⚠ **Read from the SOURCE, not from behaviour.** A fixture can only prove
    the script did not guess on the data it was given; this proves it has no
    way to.
    """
    src = (REPO / "tools" / "backfill_labour_projects.py").read_text(
        encoding="utf8")
    tree = ast.parse(src)
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "classify"]
    assert len(fn) == 1
    body = ast.dump(fn[0])
    for banned in ("'sort'", "'sorted'", "'max'", "'min'", "'lower'"):
        assert banned not in body, (
            f"classify() reaches for {banned} — picking among candidates is "
            f"exactly what it may not do")
    assert "candidates[0]" in ast.unparse(fn[0]), (
        "the one legitimate pick is the SINGLE candidate")
    assert ast.unparse(fn[0]).count("candidates[") == 1, (
        "a second index into candidates is a guess")


# ═══ 2. ⚠ IT NEVER CHANGES A DAY, A RATE OR A SLIP ══════════════════════════

def test_nothing_but_the_two_project_keys_moves(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    rec = _marking("m-ok", lone, status="half", ot_hours=3.5,
                   day_rate=777.5, notes="half shift")
    before = dict(rec)
    assert _run(write=True) == 0
    after = STORE["attendance"]["m-ok"]
    for k, was in before.items():
        if k in ("project_id", "project_name"):
            continue
        assert after[k] == was, f"{k} moved: {was!r} -> {after[k]!r}"
    assert set(after) - set(before) == {"project_id", "project_name"}


def test_a_payslip_is_never_touched(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    _marking("m-ok", lone, date="2026-09-01")
    STORE["payslips"]["s1"] = {
        "id": "s1", "employee_id": "e-SF-001", "month": "2026-09",
        "status": PAY.ISSUED,
        "snapshot": {"basic": 900.0, "ot": 0.0, "travel": 0.0}}
    frozen = dict(STORE["payslips"]["s1"]), dict(
        STORE["payslips"]["s1"]["snapshot"])
    assert _run(write=True) == 0
    assert STORE["payslips"]["s1"] == frozen[0]
    assert STORE["payslips"]["s1"]["snapshot"] == frozen[1]


def test_a_paid_worker_month_is_linked_so_the_slip_reaches_the_pnl(capsys):
    """
    ⚠ Declared: a month whose slip is issued is linked all the same. Until the
    days are on a project, the slip's money is on no project's P&L at all —
    which is the defect ruling 1 closes and this is the other half of it.
    """
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    _marking("m-ok", lone, date="2026-09-01")
    STORE["payslips"]["s1"] = {
        "id": "s1", "employee_id": "e-SF-001", "month": "2026-09",
        "status": PAY.ISSUED,
        "snapshot": {"basic": 1100.0, "ot": 0.0, "travel": 0.0}}
    assert _run(write=True) == 0
    assert STORE["attendance"]["m-ok"]["project_id"] == "p-3"
    assert AT.labour_split_of(AT.markings_for_project("p-3"))["actual"] == 1100.0


def test_the_fingerprint_covers_every_field_the_ruling_names():
    for k in ("date", "day_rate", "status", "ot_hours", AT.OVERHEAD_FIELD,
              "monthly_salary", "rate_model"):
        assert k in BLP.UNTOUCHED, (
            f"{k!r} is not in UNTOUCHED, so a change to it would not be "
            f"caught by the script's own refusal to persist")


# ═══ 3. ⚠ ALREADY ASSIGNED IS NEVER TOUCHED ═════════════════════════════════

def test_a_marking_that_already_names_a_project_keeps_its_old_name(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali RENAMED", lone)
    _marking("m-had", lone, project_id="p-3",
             project_name="Roadpali as it was called then")
    assert _run(write=True) == 0
    assert STORE["attendance"]["m-had"]["project_name"] == \
        "Roadpali as it was called then", (
        "re-snapshotting the name restates what a past day was worked for")


# ═══ 4. ⚠ OVERHEAD IS COUNTED AND LEFT ALONE ════════════════════════════════

def test_an_overhead_marking_is_counted_and_never_relinked(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    _marking("m-oh", lone, **AT.overhead_fields(True))
    assert _run(write=True) == 0
    rec = STORE["attendance"]["m-oh"]
    assert rec["project_id"] == "" and AT.is_overhead(rec)
    out = capsys.readouterr().out
    assert "marked OVERHEAD on purpose           : 1" in out


# ═══ 5. THE WORKER-MONTH REPORT ═════════════════════════════════════════════

def test_the_report_groups_by_worker_month_with_every_candidate_named(capsys):
    crowded = _addr("a-crowded", "Jamnagar")
    _project("p-1", "Jamnagar", crowded)
    _project("p-2", "Jamnagar Shed", crowded)
    for d in (1, 2, 3):
        _marking(f"m{d}", crowded, name="Ramesh Patil",
                 date=f"2026-09-0{d}")
    assert _run() == 0
    out = capsys.readouterr().out
    assert "1 worker-month(s) LEFT FOR A PERSON" in out
    assert "Ramesh Patil" in out and "2026-09" in out
    assert "3 marking(s), 3 paid day(s)" in out
    assert "'Jamnagar'" in out and "'Jamnagar Shed'" in out
    assert "/attendance/unassigned" in out


def test_the_report_names_an_issued_slip_as_the_reason_to_hurry(capsys):
    crowded = _addr("a-crowded", "Jamnagar")
    _project("p-1", "Jamnagar", crowded)
    _project("p-2", "Jamnagar Shed", crowded)
    _marking("m1", crowded, date="2026-09-01")
    STORE["payslips"]["s1"] = {
        "id": "s1", "employee_id": "e-SF-001", "month": "2026-09",
        "status": PAY.ISSUED, "snapshot": {"basic": 900.0}}
    assert _run() == 0
    assert "the payslip for this month is ISSUED" in capsys.readouterr().out


def test_a_site_with_no_project_says_what_to_do_about_it(capsys):
    _marking("m1", _addr("a-bare", "Office"))
    assert _run() == 0
    out = capsys.readouterr().out
    assert "no project is filed at that site" in out
    assert "mark the month overhead" in out


def test_the_inventory_prints_the_cost_of_the_backlog(capsys):
    crowded = _addr("a-crowded", "Jamnagar")
    _project("p-1", "Jamnagar", crowded)
    _project("p-2", "Jamnagar Shed", crowded)
    _marking("m1", crowded, day_rate=900.0)
    assert _run() == 0
    out = capsys.readouterr().out
    assert "UNASSIGNED worker-months     : 1" in out
    assert "900.00" in out


# ═══ 6. DRY RUN, DEFAULTS AND IDEMPOTENCE ═══════════════════════════════════

def test_the_default_is_a_dry_run_and_writes_nothing(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    rec = _marking("m-ok", lone)
    before = dict(rec)
    assert _run() == 0
    assert STORE["attendance"]["m-ok"] == before
    assert "DRY RUN - nothing written" in capsys.readouterr().out


def test_dry_run_said_out_loud_is_the_same_as_the_default(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    before = dict(_marking("m-ok", lone))
    assert _run(dry=True) == 0
    assert STORE["attendance"]["m-ok"] == before
    assert "DRY RUN - nothing written" in capsys.readouterr().out


def test_dry_run_and_write_together_are_refused(capsys):
    assert _run(write=True, dry=True) == 2
    assert "contradict each other" in capsys.readouterr().out


def test_a_second_write_links_nothing(capsys):
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    _marking("m-ok", lone)
    assert _run(write=True) == 0
    capsys.readouterr()
    after_first = dict(STORE["attendance"]["m-ok"])
    assert _run(write=True) == 0
    assert STORE["attendance"]["m-ok"] == after_first
    assert "0 marking(s) linked" in capsys.readouterr().out


def test_the_write_skips_the_backup_when_asked(capsys):
    """
    ⚠ `--no-backup` exists for a box whose backups are taken another way. With
    no live database there is nothing to dump, which is the suite's own case
    and is reported rather than treated as an error.
    """
    lone = _addr("a-lone", "Roadpali")
    _project("p-3", "Roadpali", lone)
    _marking("m-ok", lone)
    assert _run(write=True) == 0
    assert "no backup taken" in capsys.readouterr().out
    _marking("m-ok2", lone, code="SF-002")
    assert _run(write=True, extra=["--no-backup"]) == 0
    assert "no backup taken" not in capsys.readouterr().out


# ═══ 7. ⚠ UNREACHABLE FROM THE APPLICATION ══════════════════════════════════

def test_no_application_module_imports_this_script():
    offenders = []
    for path in REPO.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n.split(".")[0] == "backfill_labour_projects"
                   for n in names):
                offenders.append(path.name)
    assert offenders == [], (
        f"{offenders} import a migration script. It mutates wage records in "
        f"bulk and is a terminal tool, run once, under a backup.")


def test_the_script_reuses_the_apps_own_candidate_rule():
    """
    ⚠ The form, the import, the screen and this script must agree about which
    projects are at a site. Five copies is how `docsheet.py` found four
    letterheads that had already drifted.
    """
    src = (REPO / "tools" / "backfill_labour_projects.py").read_text(
        encoding="utf8")
    assert "AT.projects_on_site(" in src
    assert "site_address_id\")" in src or "SITE_ADDRESS_FIELD" in src
    assert "AT.unassigned_worker_months()" in src
    assert "AT.labour_split_of(" in src
