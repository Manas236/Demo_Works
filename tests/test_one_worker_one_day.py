"""
ONE WORKER, ONE DAY — across every path that can write a marking.

CLIENT_CHANGES.md §0's **sixty-ninth** block, item 4 (6 November 2026). A
lock-in, not a change: CC-2's *"one employee = one site = one day"* is
`attendance.conflicting_record()`, keyed on `(employee, date)` and never on
`(employee, site, date)`. This file proves no path can put a SECOND marking
on a worker-day, whichever way round the paths are taken:

| path | how it holds |
|---|---|
| hand entry, `/attendance/mark` | `_validate()` → `conflicting_record()` refuses |
| hand correction, `/attendance/edit/<id>` | the same, with the record's own id excepted |
| the multi-tab import, `/payroll/import/commit/<id>` | a day on two tabs is imported on NEITHER (`payimport.worker_days()`); every other day goes through `attendance.import_marking()`, which refuses an existing marking and never overwrites it |
| reassignment, `/attendance/assign` (the `/attendance/unassigned` screen) | `assign_month()` only rewrites `project_id` / `project_name` / the overhead mark on markings that already exist: it creates none and moves no date or person |

**Measured on `5730b15`: no path could create a second marking; nothing was
fixed.** Every test below passed against the code as it stood.

⚠ **`_invariant()` is the assertion, and it is run after every step**, not
  only at the end — a duplicate that a later step happened to remove would
  otherwise pass.
"""

import pytest

import attendance as AT
import employee as EMP
import payimport as PI
from store import STORE
from test_payimport_tabs import book, world, _upload, _form  # noqa: F401

openpyxl = pytest.importorskip("openpyxl")

DAY = "2026-09-05"


def _invariant():
    """Every (worker, date) pair carries at most ONE marking."""
    seen = {}
    for rid, r in AT.records().items():
        key = (str(r.get("employee_id") or ""), str(r.get("date") or ""))
        seen.setdefault(key, []).append(rid)
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dup, f"a worker holds two markings on one day: {dup}"


def _on(eid, day=DAY):
    return [r for r in AT.records().values()
            if r.get("employee_id") == eid and r.get("date") == day]


def _mark(client, eid="pk", day=DAY, site="rdp", project="p-rdp", **extra):
    data = {"date": day, "employee_id": eid, "site_id": site,
            "project_id": project, "status": "present", "ot_hours": "",
            "notes": ""}
    data.update(extra)
    return client.post("/attendance/mark", data=data)


# =============================================================================
# 1. HAND ENTRY
# =============================================================================

def test_hand_entry_marks_once(world):
    r = _mark(world)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert len(_on("pk")) == 1
    _invariant()


@pytest.mark.parametrize("site,project", [
    ("rdp", "p-rdp"),        # the same site again
    ("blr", "p-blr"),        # a different site — the reading CC-2 refuses
    ("gov", ""),             # a site with no project at all
])
def test_hand_entry_refuses_a_second_marking_on_the_same_day(world, site, project):
    assert _mark(world).status_code == 302
    before = dict(_on("pk")[0])
    r = _mark(world, site=site, project=project, status="half")
    assert r.status_code == 200, "refused: the form re-renders, nothing stored"
    assert "One employee, one site, one day" in r.get_data(as_text=True)
    assert len(_on("pk")) == 1
    assert _on("pk")[0] == before, "and the first marking is untouched"
    _invariant()


def test_hand_entry_is_per_worker_not_per_site(world):
    """Two DIFFERENT people on one site on one day is two markings, and right."""
    assert _mark(world, "pk").status_code == 302
    assert _mark(world, "nk").status_code == 302
    assert len(_on("pk")) == 1 and len(_on("nk")) == 1
    _invariant()


def test_an_edit_cannot_move_a_marking_onto_a_day_already_marked(world):
    _mark(world, day=DAY)
    _mark(world, day="2026-09-06")
    moving = _on("pk", "2026-09-06")[0]
    r = world.post(f"/attendance/edit/{moving['id']}", data={
        "date": DAY, "employee_id": "pk", "site_id": "blr",
        "project_id": "p-blr", "status": "present", "ot_hours": "",
        "notes": ""})
    assert r.status_code == 200
    assert "One employee, one site, one day" in r.get_data(as_text=True)
    assert len(_on("pk", DAY)) == 1 and len(_on("pk", "2026-09-06")) == 1
    _invariant()


def test_an_edit_cannot_hand_a_marking_to_a_worker_already_marked(world):
    _mark(world, "pk")
    _mark(world, "nk")
    nk = _on("nk")[0]
    r = world.post(f"/attendance/edit/{nk['id']}", data={
        "date": DAY, "employee_id": "pk", "site_id": "rdp",
        "project_id": "p-rdp", "status": "present", "ot_hours": "",
        "notes": ""})
    assert r.status_code == 200
    assert len(_on("pk")) == 1 and len(_on("nk")) == 1
    _invariant()


def test_an_edit_of_a_marking_onto_its_own_day_is_not_a_clash(world):
    """The record's own id is excepted — re-saving it is not a second one."""
    _mark(world)
    rec = _on("pk")[0]
    r = world.post(f"/attendance/edit/{rec['id']}", data={
        "date": DAY, "employee_id": "pk", "site_id": "blr",
        "project_id": "p-blr", "status": "half", "ot_hours": "",
        "notes": ""})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert [m["status"] for m in _on("pk")] == ["half"]
    _invariant()


# =============================================================================
# 2. THE MULTI-TAB IMPORT
# =============================================================================

def test_the_same_day_on_two_tabs_is_imported_on_neither(world):
    sid = _upload(world, book([
        ("ROADPALI", [{"name": "PUSHKAR MISHRA",
                       "marks": {d: (1, None) for d in range(1, 6)}}]),
        ("BANGALORE", [{"name": "PUSHKAR MISHRA",
                        "marks": {d: (1, None) for d in range(5, 11)}}]),
        ("GOVANDI", [{"name": "PUSHKAR MISHRA",
                      "marks": {5: (1, None)}}]),
    ]))
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert _on("pk") == [], "a day on three tabs: none of them is picked"
    assert len(AT.month_markings("pk", "2026-09")) == 9
    _invariant()


def test_the_import_never_overwrites_a_day_marked_by_hand(world):
    assert _mark(world, site="blr", project="p-blr").status_code == 302
    hand = dict(_on("pk")[0])
    sid = _upload(world, book([
        ("ROADPALI", [{"name": "PUSHKAR MISHRA",
                       "marks": {d: (1, 2) for d in range(1, 11)}}])]))
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert _on("pk") == [hand], "the hand marking stands, byte for byte"
    assert STORE["pay_imports"][sid]["summary"]["skipped_days"] == 1
    assert len(AT.month_markings("pk", "2026-09")) == 10
    _invariant()


def test_hand_entry_after_an_import_is_refused_on_an_imported_day(world):
    sid = _upload(world, book([
        ("ROADPALI", [{"name": "PUSHKAR MISHRA",
                       "marks": {d: (1, None) for d in range(1, 11)}}])]))
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert len(_on("pk")) == 1
    r = _mark(world, site="blr", project="p-blr")
    assert r.status_code == 200
    assert len(_on("pk")) == 1
    _invariant()


def test_one_name_twice_on_one_tab_mapped_to_one_worker_marks_each_day_once(world):
    """`group_workers()` keeps two same-tab rows apart; if the operator then
    picks the SAME employee for both, the second row's overlapping days are
    refused by `import_marking()` — skipped, never a second marking."""
    sid = _upload(world, book([
        ("ROADPALI", [
            {"name": "PUSHKAR MISHRA", "marks": {d: (1, None) for d in range(1, 8)}},
            {"name": "PUSHKAR MISHRA", "marks": {d: (1, None) for d in range(5, 11)}},
        ])]))
    rec = STORE["pay_imports"][sid]
    assert len(PI.workers_of(rec)) == 2
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert len(AT.month_markings("pk", "2026-09")) == 10
    assert rec["summary"]["skipped_days"] == 3          # days 5, 6, 7
    _invariant()


def test_two_spellings_on_two_tabs_picked_as_one_worker_mark_each_day_once(world):
    """Two names the sheet keeps apart (`norm()` differs) are two workers to
    the import; if both are picked as the same person, an overlapping day is
    written ONCE, from the first, and the second is skipped."""
    sid = _upload(world, book([
        ("ROADPALI", [{"name": "PUSHKAR MISHRA",
                       "marks": {d: (1, None) for d in range(1, 6)}}]),
        ("BANGALORE", [{"name": "PUSHKAR MISRA",
                        "marks": {d: (1, None) for d in range(5, 11)}}]),
    ]))
    rec = STORE["pay_imports"][sid]
    form = _form(sid)
    for w in PI.workers_of(rec):
        form[f"emp_{w['rows'][0]}"] = "pk"
    world.post(f"/payroll/import/commit/{sid}", data=form)
    assert len(_on("pk")) == 1
    assert len(AT.month_markings("pk", "2026-09")) == 10
    assert rec["summary"]["skipped_days"] == 1
    _invariant()


def test_a_month_cannot_be_imported_twice(world):
    data = book([("ROADPALI", [{"name": "PUSHKAR MISHRA",
                                "marks": {d: (1, None) for d in range(1, 11)}}])])
    sid = _upload(world, data)
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    sid2 = _upload(world, data)
    world.post(f"/payroll/import/commit/{sid2}", data=_form(sid2))
    assert len(AT.month_markings("pk", "2026-09")) == 10
    _invariant()


def test_import_marking_itself_refuses_a_second_marking(world):
    person = STORE["employees"]["pk"]
    rid, err = AT.import_marking(person, DAY, AT.PRESENT, 0, {}, {}, "b1")
    assert rid and not err
    rid2, err2 = AT.import_marking(person, DAY, AT.HALF, 0, {}, {}, "b2")
    assert rid2 == "" and err2 == "already marked for that day"
    _invariant()


# =============================================================================
# 3. REASSIGNMENT — /attendance/unassigned
# =============================================================================

def _unassigned_month(client):
    sid = _upload(client, book([
        ("GOVANDI", [{"name": "PUSHKAR MISHRA",
                      "marks": {d: (1, None) for d in range(1, 11)}}])]))
    client.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    rows = AT.month_markings("pk", "2026-09")
    assert len(rows) == 10 and {r["project_id"] for r in rows} == {""}
    return rows


def test_reassignment_creates_no_marking_and_moves_no_day(world):
    rows = _unassigned_month(world)
    # filed at the site AFTER the import, so the month sat unassigned
    STORE["projects"]["p-gov"] = dict(STORE["projects"]["p-rdp"], id="p-gov",
                                      name="Govandi", norm_name="govandi",
                                      site_address_id="gov")
    before = {r["id"]: (r["employee_id"], r["date"]) for r in rows}
    page = world.get("/attendance/unassigned").get_data(as_text=True)
    assert "PUSHKAR MISHRA" in page
    r = world.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09", "project_id": "p-gov"})
    assert r.status_code == 302
    after = {r["id"]: (r["employee_id"], r["date"])
             for r in AT.month_markings("pk", "2026-09")}
    assert after == before, "same records, same people, same days"
    assert {r["project_id"] for r in AT.month_markings("pk", "2026-09")} == {"p-gov"}
    _invariant()


def test_reassignment_to_overhead_creates_no_marking(world):
    rows = _unassigned_month(world)
    ids = {r["id"] for r in rows}
    world.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09",
        "project_id": AT.OVERHEAD_CHOICE})
    assert {r["id"] for r in AT.month_markings("pk", "2026-09")} == ids
    _invariant()


def test_a_day_freed_by_a_clash_can_be_marked_by_hand_exactly_once(world):
    """The import's own advice — *mark by hand once resolved* — taken: the
    clash day is free, the first hand marking lands, the second is refused,
    and reassigning the month afterwards adds nothing."""
    sid = _upload(world, book([
        ("GOVANDI", [{"name": "PUSHKAR MISHRA",
                      "marks": {d: (1, None) for d in range(1, 6)}}]),
        ("BANGALORE", [{"name": "PUSHKAR MISHRA",
                        "marks": {5: (1, None)}}]),
    ]))
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert _on("pk") == []
    assert _mark(world, site="gov", project="").status_code == 302
    _invariant()
    assert _mark(world, site="blr", project="p-blr").status_code == 200
    _invariant()
    world.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09",
        "project_id": AT.OVERHEAD_CHOICE})
    assert len(_on("pk")) == 1
    assert len(AT.month_markings("pk", "2026-09")) == 5
    _invariant()


def test_conflicting_record_is_keyed_on_worker_and_day_and_not_on_site():
    """The rule itself, stated directly: the site is not part of the key."""
    import inspect
    src = inspect.getsource(AT.conflicting_record)
    assert '"employee_id"' in src and '"date"' in src
    assert "site" not in src.split('"""', 2)[2], (
        "conflicting_record() must not read the site — keyed on "
        "(employee, date), CC-2's one-employee-one-day")
