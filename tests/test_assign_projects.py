"""
The Owner-only bulk assign of existing unassigned attendance to projects —
`/attendance/assign-projects`, CLIENT_CHANGES.md §0 eighty-fifth block
(23 November 2026).

Rules in order: (a) October 2026 hand-entered days at RIL Jamnagar's site →
RIL Jamnagar (ruled 6 Nov, 88 days); (b) a site with exactly one project →
that project; (c) a shared site → a per-worker pick, never guessed. The GET
writes nothing; the POST applies only what was shown plus the picks, logs
who and when, and assigns nothing twice. Assigned markings and payslips are
never touched.
"""

import pytest

import attendance as AT
import auth
import employee as EMP
from store import STORE

JAM = "addr-jam"
ROAD = "addr-road"
NOPROJ = "addr-empty"
COLLS = ("employees", "attendance", "payslips", "projects")


@pytest.fixture(autouse=True)
def _clean():
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(AT.RUNS_RECORD, None)
    yield
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(AT.RUNS_RECORD, None)


def _project(pid, name, aid):
    STORE["projects"][pid] = {"id": pid, "name": name, "site_address_id": aid}


def _mark(mid, eid, date, aid, pid="", **over):
    rec = {"id": mid, "employee_id": eid, "employee_name": eid.upper(),
           "date": date, "status": AT.PRESENT, "ot_hours": 0.0,
           "day_rate": 800.0, "site": aid.upper(),
           EMP.SITE_ADDRESS_FIELD: aid, EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
           "project_id": pid, "project_name": ""}
    rec.update(over)
    STORE["attendance"][mid] = rec
    return rec


def _world(oct_days=88):
    _project("p-ril", "RIL Jamnagar", JAM)
    _project("p-shed", "RIL Jamnagar Shed", JAM)
    _project("p-road", "Roadpali", ROAD)
    for d in range(oct_days):                       # rule (a)
        _mark(f"a{d}", f"w{d % 4}", f"2026-10-{d // 4 + 1:02d}", JAM)
    _mark("imp", "w9", "2026-10-02", JAM, import_batch="batch-1")  # (c), imported
    _mark("sep", "w9", "2026-09-02", JAM)                          # (c), September
    _mark("b1", "w5", "2026-09-03", ROAD)                          # rule (b)
    _mark("b2", "w5", "2026-09-04", ROAD)
    _mark("done", "w5", "2026-09-05", ROAD, pid="p-road")          # already assigned
    _mark("oh", "w5", "2026-09-06", ROAD, **AT.overhead_fields(True))
    _mark("left", "w6", "2026-09-07", NOPROJ)                      # no project there
    _mark("nosite", "w6", "2026-09-08", "", site="SOMEWHERE")      # no address


def _form(client):
    page = client.get("/attendance/assign-projects").get_data(as_text=True)
    prop = AT.bulk_proposal()
    return page, prop, {"apply_a": "1", "apply_b": "1",
                        "sig_a": prop["a"]["sig"], "sig_b": prop["b"]["sig"]}


def test_the_get_is_a_dry_run_and_writes_nothing(client):
    _world()
    before = {k: dict(v) for k, v in STORE["attendance"].items()}
    page, prop, _ = _form(client)
    assert STORE["attendance"] == before
    assert "Nothing has been written &mdash; this is a dry" in page
    assert len(prop["a"]["rows"]) == 88
    assert {r["id"] for r in prop["b"]["rows"]} == {"b1", "b2"}
    assert {g["employee_id"] for g in prop["c"]} == {"w9"}
    assert sorted(len(g["rows"]) for g in prop["c"]) == [1, 1], \
        "one group per worker, month and site"
    assert set(prop["left"]) == {"no project filed at that site",
                                 "no address-book site on the marking"}
    assert 'name="apply_a" value="1"\n      checked' in page, "88 found: ticked"


def test_the_post_applies_a_and_b_and_leaves_c_and_assigned_alone(client):
    _world()
    _, prop, form = _form(client)
    client.post("/attendance/assign-projects", data=form)
    A = STORE["attendance"]
    assert {A[f"a{d}"]["project_id"] for d in range(88)} == {"p-ril"}
    assert A["a0"]["project_name"] == "RIL Jamnagar"
    assert A["b1"]["project_id"] == A["b2"]["project_id"] == "p-road"
    assert A["imp"]["project_id"] == "" and A["sep"]["project_id"] == ""
    assert A["left"]["project_id"] == "" and A["nosite"]["project_id"] == ""
    assert AT.is_overhead(A["oh"]) and A["oh"]["project_id"] == ""
    assert "edit_log" not in A["done"], "an assigned marking is never touched"
    log = A["a0"]["edit_log"][-1]
    assert log["after"] == "RIL Jamnagar" and log["by"]
    run = AT.bulk_runs()[-1]
    assert run["assigned"] == 90 and run["by_id"] and run["at"]


def test_rerunning_assigns_nothing_twice(client):
    _world()
    _, _, form = _form(client)
    client.post("/attendance/assign-projects", data=form)
    logs = sum(len(r.get("edit_log") or []) for r in STORE["attendance"].values())
    _, prop, form2 = _form(client)
    assert prop["a"]["rows"] == [] and prop["b"]["rows"] == []
    client.post("/attendance/assign-projects", data=form2)
    assert sum(len(r.get("edit_log") or [])
               for r in STORE["attendance"].values()) == logs


def test_a_changed_proposal_writes_nothing(client):
    _world()
    _, _, form = _form(client)
    _mark("late", "w5", "2026-09-10", ROAD)          # appears after the GET
    r = client.post("/attendance/assign-projects", data=form)
    assert "changed" in r.headers["Location"]
    assert all(not m["project_id"] for k, m in STORE["attendance"].items()
               if k != "done")


def test_the_shared_site_pick_is_per_worker_and_a_blank_writes_nothing(client):
    _world()
    _, prop, _ = _form(client)
    g = next(g for g in prop["c"] if g["month"] == "2026-09")
    other = next(x for x in prop["c"] if x is not g)
    client.post("/attendance/assign-projects", data={
        f"pick_{g['key']}": "p-shed", f"gsig_{g['key']}": g["sig"],
        f"pick_{other['key']}": "", f"gsig_{other['key']}": other["sig"]})
    A = STORE["attendance"]
    assert A["sep"]["project_id"] == "p-shed"
    assert A["imp"]["project_id"] == "", "a blank pick writes nothing"
    assert A["a0"]["project_id"] == "", "rule (a) unticked: not applied"


def test_a_pick_of_a_project_at_another_site_is_refused(client):
    _world()
    _, prop, _ = _form(client)
    g = prop["c"][0]
    r = client.post("/attendance/assign-projects", data={
        f"pick_{g['key']}": "p-road", f"gsig_{g['key']}": g["sig"]})
    assert "not+at" in r.headers["Location"] or "not at" in r.headers["Location"]
    assert all(m["project_id"] in ("", "p-road") for m in STORE["attendance"].values())
    assert STORE["attendance"]["sep"]["project_id"] == ""


def test_rule_a_is_unticked_when_the_count_is_not_the_ruled_88(client):
    _world(oct_days=90)
    page, prop, _ = _form(client)
    assert len(prop["a"]["rows"]) == 90
    assert "the ruling named" in page
    assert 'name="apply_a" value="1"\n      />' in page


def test_payslips_are_never_altered(client):
    _world()
    STORE["payslips"]["s1"] = {"id": "s1", "employee_id": "w5",
                               "month": "2026-09", "status": "Issued",
                               "snapshot": {"basic": 1600.0}}
    before = dict(STORE["payslips"]["s1"])
    _, _, form = _form(client)
    client.post("/attendance/assign-projects", data=form)
    assert STORE["payslips"]["s1"] == before


def _director(client):
    auth.ensure_builtin_roles()
    old = auth.find_user("assign-director")
    if old:
        del STORE["users"][old["id"]]
    user = auth.create_user("assign-director", "Director", "assign-director-pw",
                            ["role-director"], created_by="test")
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]
    return user


def test_a_director_holding_labour_assign_is_refused_and_not_linked(client):
    _world()
    _director(client)
    assert "labour.assign" in auth.permissions_of(auth.find_user("assign-director"))
    assert client.get("/attendance/assign-projects").status_code == 403
    r = client.post("/attendance/assign-projects", data={"apply_b": "1"})
    assert r.status_code == 403
    assert STORE["attendance"]["b1"]["project_id"] == ""
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "/attendance/assign-projects" not in page


def test_the_owner_sees_the_button_on_the_unassigned_screen(client):
    _world()
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert 'href="/attendance/assign-projects">Assign in bulk</a>' in page
