"""
`tools/backfill_marking_projects.py` — link a marking, or refuse to guess.

Authorised by the **SIXTH override block of 30 August 2026** in
`CLIENT_CHANGES.md` §0. Not CC-2 scope; PROGRESS.md §4c.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **IT NEVER GUESSES.** A site carrying two projects leaves its markings
   alone. This is the whole safety property: a wrong automatic match puts a
   day's labour cost against a project nobody chose and **looks exactly like a
   right one** — `po_parts.py`'s 156 invented aliases in a third register
   (ABOUT.md §2h). The temptation this test exists to refuse is "take the
   oldest", "take the newest", "take the one with the most markings already".
2. ⚠ **The ambiguous rows are PRINTED IN FULL, with every candidate named.**
   The refusal is only useful if the human can act on it, and a count with no
   names is not something anybody can act on.
3. **Exactly one project on the site links**, with the name **snapshotted** —
   the tool's only write.
4. ⚠ **A marking that already carries a project is never touched**, not even to
   refresh the name. That name is what the project was called when the marking
   was attributed; re-snapshotting it is the history-rewriting every freeze
   contract in this app exists to prevent.
5. **A dry run writes nothing**, and a second `--write` is a no-op.
6. ⚠ **It is unreachable from the application.**

⚠ **Do not weaken (1) or (4) to make a red suite green.** Either failure means
this script can silently move somebody's wages onto the wrong project.
"""

import ast
import pathlib
import sys

import pytest

from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import backfill_marking_projects as BMP  # noqa: E402


TOUCHED = ("projects", "addresses", "attendance")


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
        "id": aid, "label": label, "type": "site", "contact_name": "",
        "company": "", "line1": "", "line2": "", "landmark": "", "city": "",
        "state": "", "pincode": "", "country": "India", "phone": "",
        "email": "", "gstin": "",
    }
    return aid


def _project(pid, name, aid, client="C"):
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": name, "client": client, "notes": "",
        "site_address": "", "site_address_id": aid}
    return STORE["projects"][pid]


def _marking(rid, aid, code="SF-001", name="Ramesh", **over):
    rec = {"id": rid, "date": "2026-08-30", "employee_id": "e-" + rid,
           "employee_name": name, "employee_code": code, "day_rate": 900.0,
           "site": "Somewhere", "site_address_id": aid, "site_source": "book",
           "status": "present", "ot_hours": 0.0}
    rec.update(over)
    STORE.setdefault("attendance", {})[rid] = rec
    return rec


def _run(write=False):
    argv = ["backfill_marking_projects.py"] + (["--write"] if write else [])
    old = sys.argv
    sys.argv = argv
    try:
        return BMP.main()
    finally:
        sys.argv = old


# ═══ 1. ⚠ IT NEVER GUESSES — the property this script exists for ═══════════

def test_a_site_with_two_projects_leaves_its_markings_alone(capsys):
    """
    ⚠ **THE SAFETY PROPERTY.** Two projects at one address, one marking on it.
    Neither project may be chosen, by any rule.

    The control is in the same test: a **different** marking, at a site with
    exactly one project, is linked in the same run. Without it this would pass
    on a script that linked nothing at all.
    """
    crowded = _addr("a-crowded", "Bangalore, Karnataka")
    lone = _addr("a-lone", "Magarpatta Tower B")
    _project("p-1", "Sify Bangalore", crowded)
    _project("p-2", "Sify3", crowded)
    _project("p-3", "Magarpatta Fire", lone)

    ambiguous = _marking("m-amb", crowded)
    control = _marking("m-ok", lone, code="SF-002")

    _run(write=True)

    assert ambiguous.get("project_id", "") == "", (
        "the script chose one of two candidate projects — it must never guess")
    assert ambiguous.get("project_name", "") == ""

    # THE CONTROL: the unambiguous marking in the same run WAS linked.
    assert control["project_id"] == "p-3", (
        "the control failed: nothing is ever linked, so the assertion above "
        "proves nothing")


def test_it_takes_neither_the_oldest_nor_the_newest_candidate(capsys):
    """
    ⚠ **The two rules somebody will be tempted to add**, named so that adding
    either turns this red. Insertion order and `created_at` both offer an
    obvious tie-break, and both would be a figure nobody chose.
    """
    aid = _addr("a-two", "Two Projects Here")
    first = _project("p-old", "Older", aid)
    second = _project("p-new", "Newer", aid)
    first["created_at"] = "2020-01-01 00:00"
    second["created_at"] = "2026-08-30 00:00"

    rec = _marking("m-1", aid)
    _run(write=True)

    assert rec.get("project_id", "") not in ("p-old", "p-new"), (
        "a tie-break was applied — there is no rule by which either of two "
        "projects is the right one")
    assert rec.get("project_id", "") == ""


def test_the_ambiguous_list_is_printed_in_full_with_every_candidate(capsys):
    """
    ⚠ **The refusal is only useful if a human can act on it.** A count with no
    names sends somebody to the database to find out what the script would not
    say.
    """
    aid = _addr("a-many", "Bangalore, Karnataka")
    for pid, name in (("p-a", "Banglore"), ("p-b", "Sify Bangalore"),
                      ("p-c", "Sify3"), ("p-d", "Test Supplier")):
        _project(pid, name, aid)
    _marking("m-1", aid, name="Ganesh Salunkhe")

    _run()
    out = capsys.readouterr().out

    assert "1 marking(s) LEFT ALONE" in out
    assert "4 candidates" in out
    for name in ("Banglore", "Sify Bangalore", "Sify3", "Test Supplier"):
        assert repr(name) in out or name in out, (
            f"the candidate {name!r} was not named in the ambiguous report")
    assert "Ganesh Salunkhe" in out, "the marking itself must be identifiable"
    assert "/attendance/edit/" in out, "it must say where to resolve them"


# ═══ 2. What it DOES link ══════════════════════════════════════════════════

def test_exactly_one_project_on_the_site_links_and_snapshots_the_name(capsys):
    aid = _addr("a-one", "Magarpatta Tower B")
    _project("p-1", "Magarpatta Fire Protection", aid)
    rec = _marking("m-1", aid)

    _run(write=True)

    assert rec["project_id"] == "p-1"
    assert rec["project_name"] == "Magarpatta Fire Protection", (
        "the name must be snapshotted onto the marking, not left to a lookup")


def test_a_site_with_no_project_is_left_and_reported(capsys):
    """A site with no project is legitimate — an office, a store."""
    aid = _addr("a-none", "Head Office")
    rec = _marking("m-1", aid)

    _run(write=True)
    out = capsys.readouterr().out

    assert rec.get("project_id", "") == ""
    assert "no project is recorded at that site" in out
    assert "an office or a store belongs to no project" in out


def test_a_marking_with_no_site_is_skipped_and_counted_separately(capsys):
    """
    ⚠ **An unmapped marking has no site to ask the question of**, and mapping it
    here would be a second migration hiding inside this one.
    """
    rec = _marking("m-1", "", site="Banglore", site_source="unmapped")

    _run(write=True)
    out = capsys.readouterr().out

    assert rec.get("project_id", "") == ""
    assert "no site linked at all" in out
    assert rec["site"] == "Banglore", "the unmapped string must be left alone"
    assert rec["site_address_id"] == "", "no site may be invented"


# ═══ 3. ⚠ What it must NOT touch ═══════════════════════════════════════════

def test_a_marking_that_already_carries_a_project_is_never_re_snapshotted():
    """
    ⚠ **THE FREEZE CONTRACT.** `project_name` is what the project was called
    when the marking was attributed. Refreshing it would restate history — the
    defect `proforma.prior_invoiced`, `ra.prev_balance` and this record's own
    `day_rate` all exist to prevent.
    """
    aid = _addr("a-one", "Site")
    proj = _project("p-1", "Renamed Since", aid)
    rec = _marking("m-1", aid, project_id="p-1",
                   project_name="Called This At The Time")

    _run(write=True)

    assert rec["project_name"] == "Called This At The Time", (
        "the tool re-snapshotted a name that was already recorded — that is a "
        "rewrite of history, not a backfill")
    assert proj["name"] == "Renamed Since", "and the project is untouched"


def test_it_writes_one_field_and_nothing_else(capsys):
    """
    ⚠ **No site is remapped, no address created, no project renamed, nothing
    deleted.** One field, on one collection, under one rule.
    """
    aid = _addr("a-one", "Site")
    proj = _project("p-1", "The Project", aid)
    rec = _marking("m-1", aid)

    before_addr = dict(STORE["addresses"][aid])
    before_proj = dict(proj)
    before_rest = {k: v for k, v in rec.items()
                   if k not in ("project_id", "project_name")}

    _run(write=True)

    assert STORE["addresses"][aid] == before_addr, "an address was modified"
    assert dict(proj) == before_proj, "a project was modified"
    assert len(STORE["addresses"]) == 1, "an address was created or deleted"
    assert len(STORE["projects"]) == 1, "a project was created or deleted"
    assert len(STORE["attendance"]) == 1, "a marking was created or deleted"
    for k, v in before_rest.items():
        assert rec[k] == v, f"the tool changed {k!r} on the marking"


# ═══ 4. Dry run and idempotence ════════════════════════════════════════════

def test_a_dry_run_writes_nothing(capsys):
    aid = _addr("a-one", "Site")
    _project("p-1", "The Project", aid)
    rec = _marking("m-1", aid)

    _run()
    out = capsys.readouterr().out

    assert "WOULD LINK" in out and "DRY RUN - nothing written" in out
    assert rec.get("project_id", "") == "", "a dry run wrote to the record"


def test_the_second_write_is_a_no_op(capsys):
    aid = _addr("a-one", "Site")
    _project("p-1", "The Project", aid)
    rec = _marking("m-1", aid)

    _run(write=True)
    capsys.readouterr()
    after_first = dict(rec)

    _run(write=True)
    out = capsys.readouterr().out

    assert "to LINK (site carries exactly one project) : 0" in out
    assert "already carries a project            : 1" in out
    assert dict(rec) == after_first, "the second run changed the record"


def test_the_report_does_not_go_quiet_on_a_second_run(capsys):
    """
    ⚠ An unresolved row is still unresolved. A report that only fires the first
    time hides exactly the rows a human has not got to yet.
    """
    aid = _addr("a-two", "Crowded")
    _project("p-a", "Alpha", aid)
    _project("p-b", "Bravo", aid)
    _marking("m-1", aid)

    _run(write=True)
    capsys.readouterr()
    _run(write=True)
    out = capsys.readouterr().out

    assert "1 marking(s) LEFT ALONE" in out
    assert "Alpha" in out and "Bravo" in out


def test_the_inventory_is_printed_before_and_after(capsys):
    aid = _addr("a-one", "Site")
    _project("p-1", "The Project", aid)
    _marking("m-1", aid)

    _run(write=True)
    out = capsys.readouterr().out

    assert "BEFORE" in out and "AFTER" in out
    assert out.index("BEFORE") < out.index("AFTER")
    assert "carrying a project_id        : 0" in out
    assert "carrying a project_id        : 1" in out


# ═══ 5. ⚠ Structure ═══════════════════════════════════════════════════════

def test_the_candidate_rule_is_not_a_second_copy():
    """
    ⚠ **The form, the validator and this script must agree about which projects
    are at a site.** Three copies is how `docsheet.py` found four letterheads
    that had already drifted, so the script calls
    `attendance.projects_on_site()` rather than walking the collection itself.
    """
    src = (REPO / "tools" / "backfill_marking_projects.py").read_text(
        encoding="utf8")
    assert "AT.projects_on_site(" in src, (
        "the tool must ask attendance.py which projects are at a site")
    assert 'STORE.get("projects")' not in src.replace(
        'len(STORE.get(\'projects\') or {})', ""), (
        "the tool is walking the projects collection itself — that is the "
        "second copy of the rule this test exists to prevent")


def test_there_is_no_force_and_no_similarity_matching():
    """
    ⚠ **The refusal must not be overridable and must not be a threshold.** A
    `--force` turns "never guesses" into "guesses when somebody is in a hurry",
    and a similarity score is a guess with a number on it.
    """
    src = (REPO / "tools" / "backfill_marking_projects.py").read_text(
        encoding="utf8")
    tree = ast.parse(src)

    flags = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and \
                getattr(getattr(node, "func", None), "attr", "") == "add_argument":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value)
    assert flags == {"--write"}, (
        f"the only flag may be --write; found {sorted(flags)}")

    # ⚠ `"ratio"` is deliberately NOT on this list: it is a substring of
    #   "migration", which this file says several times, and a banned token that
    #   fires on an ordinary English word gets deleted by the next person rather
    #   than obeyed. `.ratio(` is the call that would matter.
    for banned in ("difflib", "SequenceMatcher", "get_close_matches",
                   "levenshtein", ".ratio(", "threshold", "fuzz"):
        assert banned.lower() not in src.lower(), (
            f"{banned!r} appears — nothing here may match by similarity")


def test_it_is_not_reachable_from_the_application():
    """
    ⚠ A script that mutates live records and that a request can reach is a
    request that mutates live records.

    ⚠ **The rule here is IMPORT reachability, not a mention**, and that is a
    deliberate difference from `tests/test_seed_demo_scenario.py`, which fails
    if an application module so much as names its tool. The seeder's rule is
    stricter for its own reason: `employees` and `attendance` are transactional
    collections and a name in the app is the first step to seeding one. A
    backfill is the opposite case — **every other backfill in this repo is named
    in the module it migrates** (`boq.py` and `ra.py` name
    `backfill_line_ids`, `employee.py` names `backfill_day_rate`, `project.py`
    names `backfill_project_sites`, `approval.py` names `backfill_created_by`),
    because the module carrying the field is where a reader asks how the old
    records got one. Banning the pointer would delete the documentation and
    leave the actual risk — an import — untested.
    """
    for path in REPO.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                names = [a.name for a in getattr(node, "names", [])]
                for candidate in [mod] + names:
                    assert "backfill_marking_projects" not in candidate, (
                        f"{path.name} imports the backfill — it is a "
                        f"command-line tool and nothing in the application may "
                        f"reach it")

    # And `tools/` is not on the application's import path, so even the name
    # would not resolve from a request. The control: it IS importable from here,
    # because this file put `tools/` on the path itself.
    assert BMP.__file__.replace("\\", "/").endswith(
        "tools/backfill_marking_projects.py")
