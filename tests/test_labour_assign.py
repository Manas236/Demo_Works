"""
SITE → PROJECT IS DECIDED PER WORKER, AND THE BUCKET HAS A SCREEN.

CLIENT_CHANGES.md §0's **sixty-sixth** block; Manas's rulings 2 and 3 of
5 November 2026; `docs/LABOUR_PL.md` §§2–3 are the defects.

**Ruling 2.** The import used to decide the project once per sheet SITE
(`payimport.commit()`), so two live projects at one address could not be split
and the operator's only way past the refusal was to pick one for everybody.
Now:

| the site | the project |
|---|---|
| an address with **one** live project | auto-assigned |
| an address with **two or more** | a picker **per worker**, defaulting to that worker's project last month; **no default → refused before commit** |
| an address with **none** | the UNASSIGNED bucket, never dropped |
| **No project (overhead)** | on no project, and never asked about again |

Hand-entered attendance gets the same field and the same default rule.

**Ruling 3.** `/attendance/unassigned` lists the worker-months and assigns
them, under the new `labour.assign` (Owner + Director), logging who / when /
before → after on each marking.
"""

import datetime
import io

import pytest

import attendance as AT
import auth
import employee as EMP
import editlog as EL
import payimport as PI
import payroll as PAY
from store import STORE
from test_payimport import _site, _upload, workbook, PUSHKAR

SITE = "addr-roadpali"
OFFICE = "addr-office"
COLLS = ("employees", "attendance", "pay_entries", "payslips", "pay_imports",
         "projects")


@pytest.fixture(autouse=True)
def _clean():
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    yield
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    for aid in (SITE, OFFICE):
        STORE.setdefault("addresses", {}).pop(aid, None)


def _project(pid, name, aid=SITE):
    STORE["projects"][pid] = {
        "id": pid, "name": name, "norm_name": name.lower(), "client": "IOCL",
        "notes": "", "site_address_id": aid, "site_address": "",
        "created_at": "2026-09-01 09:00", "updated_at": "2026-09-01 09:00"}


def _person(eid="pk", name="PUSHKAR MISHRA", rate=833.0):
    STORE["employees"][eid] = {"id": eid, "name": name, "active": True,
                               "day_rate": rate, "code": ""}
    return STORE["employees"][eid]


def _mark(mid, eid, date, pid="", aid=SITE, status=AT.PRESENT, **over):
    rec = {"id": mid, "employee_id": eid, "employee_name": "PUSHKAR MISHRA",
           "date": date, "status": status, "ot_hours": 0.0, "day_rate": 833.0,
           "site": "ROADPALI", EMP.SITE_ADDRESS_FIELD: aid,
           EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
           "project_id": pid,
           "project_name": (STORE["projects"].get(pid) or {}).get("name", "")}
    rec.update(over)
    STORE["attendance"][mid] = rec
    return rec


# =============================================================================
# 1. THE IMPORT — the site picker no longer carries the project
# =============================================================================

def test_the_site_picker_offers_each_site_once_and_overhead(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    vals = [v for v, _l, _a in PI.site_choices()]
    assert vals.count(SITE) == 1, (
        "one entry per site — the (site, project) pairs are gone, because the "
        "project is a per-worker control now")
    assert PI.OVERHEAD in vals
    assert not [v for v in vals if "|" in v], "no pair is OFFERED any more"


def test_a_multi_project_site_now_preselects_where_it_could_not_before(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    assert PI.preselect("ROADPALI", PI.site_choices()) == SITE


def test_the_overhead_entry_can_never_be_preselected_by_a_blank_site(client):
    _site()
    assert PI.preselect("", PI.site_choices()) == ""
    assert PI.preselect("   ", PI.site_choices()) == ""


def test_one_project_at_the_site_is_auto_assigned(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    r = client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": SITE, "emp_0": "pk"})
    assert r.status_code == 302
    days = AT.month_markings("pk", "2026-09")
    assert len(days) == 30
    assert {d["project_id"] for d in days} == {"p1"}
    assert {d["project_name"] for d in days} == {"Roadpali A"}


def test_no_project_at_the_site_goes_to_the_unassigned_bucket(client):
    _site()
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": SITE, "emp_0": "pk"})
    days = AT.month_markings("pk", "2026-09")
    assert len(days) == 30, "nothing is dropped"
    assert {d["project_id"] for d in days} == {""}
    assert len(AT.markings_unassigned()) == 30
    assert [g["employee_name"] for g in AT.unassigned_worker_months()] \
        == ["PUSHKAR MISHRA"]


def test_two_projects_at_the_site_refuse_the_commit_without_a_per_worker_pick(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    r = client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": SITE, "emp_0": "pk"})
    assert r.status_code == 302
    assert STORE["attendance"] == {}, "refused before anything was written"
    # ⚠ §0 sixty-eighth block (6 Nov 2026): the question is asked once per
    #   SITE NAME now, so the refusal names the site. Was:
    #       assert "choose which one for this person" in r.headers["Location"] …
    assert "choose which one this site name means" in r.headers["Location"] \
        or "choose+which+one+this+site+name+means" in r.headers["Location"]
    assert STORE["pay_imports"][sid]["status"] == PI.STAGED


def test_two_projects_at_the_site_take_the_per_worker_pick(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": SITE, "emp_0": "pk", "proj_0": "p2"})
    days = AT.month_markings("pk", "2026-09")
    assert {d["project_id"] for d in days} == {"p2"}


def test_two_workers_on_one_site_go_to_two_different_projects(client):
    """
    ⚠ **The whole of ruling 2.** Jamnagar and Jamnagar Shed share an address;
    before this pass every worker on either landed on whichever one the
    operator chose for the sheet.
    """
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person("pk", "PUSHKAR MISHRA")
    _person("nk", "NIRAJ")
    niraj = {"name": "NIRAJ", "site": "ROADPALI",
             "marks": {1: (1, None), 2: (1, None)}, "money": {"rate": 600}}
    sid = _upload(client, workbook([PUSHKAR, niraj]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": SITE,
        "emp_0": "pk", "proj_0": "p1",
        "emp_1": "nk", "proj_1": "p2"})
    assert {d["project_id"] for d in AT.month_markings("pk", "2026-09")} == {"p1"}
    assert {d["project_id"] for d in AT.month_markings("nk", "2026-09")} == {"p2"}


def test_a_per_worker_pick_of_a_project_somewhere_else_is_refused(client):
    _site()
    STORE["addresses"][OFFICE] = {"id": OFFICE, "label": "OFFICE",
                                  "type": "site", "line1": "x"}
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _project("px", "Elsewhere", OFFICE)
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    r = client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": SITE, "emp_0": "pk", "proj_0": "px"})
    assert STORE["attendance"] == {}
    assert "not+at+that+site" in r.headers["Location"] \
        or "not at that site" in r.headers["Location"]


def test_last_month_no_longer_answers_a_day_the_sheet_gives_a_site_for(client):
    """
    ⚠ **SUPERSEDED 6 November 2026 — CLIENT_CHANGES.md §0 sixty-eighth
    block.** The last-month default now fills ONLY days with no site; a site
    the sheet gives is answered once per SITE NAME (`sproj_<i>`), and the
    per-worker picker is no longer drawn. The old test, verbatim in its
    assertions:

        page = client.get(f"/payroll/import/preview/{sid}?month=2026-09")…
        assert 'name="proj_0"' in page
        assert '<option value="p2" selected>Roadpali B</option>' in page
        assert '<option value="p1" selected' not in page
    """
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    _mark("aug1", "pk", "2026-08-10", "p2")
    _mark("aug2", "pk", "2026-08-11", "p2")
    assert AT.project_last_month("pk", "2026-09")["project_id"] == "p2"
    sid = _upload(client, workbook([PUSHKAR]))
    page = client.get(f"/payroll/import/preview/{sid}?month=2026-09") \
        .get_data(as_text=True)
    assert 'name="proj_0"' not in page
    assert 'name="sproj_0"' in page
    assert '<option value="p2" selected>' not in page, \
        "August's project does not answer a site the sheet names"


def test_a_split_last_month_gives_no_default_at_all(client):
    """
    ⚠ Declared: a worker who split August across two projects has no single
    answer, and the one with more days would be an invented default.
    """
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    _mark("aug1", "pk", "2026-08-10", "p1")
    _mark("aug2", "pk", "2026-08-11", "p2")
    assert AT.project_last_month("pk", "2026-09") == {}


def test_last_month_crosses_a_year_boundary(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    _mark("dec", "pk", "2025-12-31", "p1")
    assert AT.project_last_month("pk", "2026-01")["project_id"] == "p1"


def test_an_overhead_month_is_a_real_default(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    _mark("aug", "pk", "2026-08-10", "", **AT.overhead_fields(True))
    assert AT.project_last_month("pk", "2026-09")[AT.OVERHEAD_FIELD] is True


def test_a_deleted_project_last_month_gives_no_default(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    _mark("aug", "pk", "2026-08-10", "gone", project_name="Gone")
    assert AT.project_last_month("pk", "2026-09") == {}


# =============================================================================
# 2. OVERHEAD — on no project, and never nagged about
# =============================================================================

def test_an_overhead_site_lands_on_no_project_and_is_not_unassigned(client):
    _site()
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": PI.OVERHEAD, "emp_0": "pk"})
    days = AT.month_markings("pk", "2026-09")
    assert len(days) == 30
    assert {d["project_id"] for d in days} == {""}
    assert all(AT.is_overhead(d) for d in days)
    assert AT.markings_unassigned() == [], "overhead never nags"
    assert AT.unassigned_worker_months() == []
    assert len(AT.markings_overhead()) == 30
    assert AT.off_project_labour()["markings"] == 0


def test_an_overhead_marking_keeps_the_sheets_own_site_string(client):
    """`employee.resolve_site()`'s middle row: the string is evidence."""
    _site()
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": PI.OVERHEAD, "emp_0": "pk"})
    one = AT.month_markings("pk", "2026-09")[0]
    assert one["site"] == "ROADPALI"
    assert one[EMP.SITE_ADDRESS_FIELD] == ""
    assert EMP.is_unmapped_site(one)


def test_overhead_is_still_cost_tagged_to_no_project(client):
    """
    ⚠ The amber nag stops; the register's untagged-cost line does not. An
    office day is cost, and it is on no project.
    """
    import pnl as PNL
    _site()
    _person()
    _mark("o1", "pk", "2026-09-01", "", **AT.overhead_fields(True))
    assert PNL.untagged_cost()["labour"]["markings"] == 1
    assert PNL.untagged_cost()["labour"]["total"] == 833.0


def test_a_marking_without_the_field_still_means_legacy(client):
    _site()
    _person()
    _mark("legacy", "pk", "2026-09-01", "")
    assert AT.is_overhead(STORE["attendance"]["legacy"]) is False
    assert AT.OVERHEAD_FIELD not in STORE["attendance"]["legacy"], (
        "an import or a mark writes the key only when it is True — an absent "
        "key is the legacy shape and must stay distinguishable")
    assert len(AT.markings_unassigned()) == 1


# =============================================================================
# 3. THE HAND FORM — the same field and the same default rule
# =============================================================================

def test_the_mark_form_offers_overhead_at_every_site(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    page = client.get("/attendance/mark").get_data(as_text=True)
    assert f'value="{AT.OVERHEAD_CHOICE}"' in page
    assert "No project &mdash; overhead" in page or \
        "No project — overhead" in page


def test_marking_a_day_as_overhead_stores_the_decision(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    r = client.post("/attendance/mark", data={
        "date": "2026-09-15", "employee_id": "pk", "site_id": SITE,
        "project_id": AT.OVERHEAD_CHOICE, "status": AT.PRESENT})
    assert r.status_code == 302
    rec = AT.month_markings("pk", "2026-09")[0]
    assert AT.is_overhead(rec) and rec["project_id"] == ""
    assert AT.markings_unassigned() == []


def test_editing_an_overhead_day_onto_a_project_takes_the_mark_off(client):
    _site()
    _project("p1", "Roadpali A")
    _person()
    _mark("m1", "pk", "2026-09-15", "", **AT.overhead_fields(True))
    client.post("/attendance/edit/m1", data={
        "date": "2026-09-15", "employee_id": "pk", "site_id": SITE,
        "project_id": "p1", "status": AT.PRESENT})
    rec = STORE["attendance"]["m1"]
    assert rec["project_id"] == "p1"
    assert AT.OVERHEAD_FIELD not in rec, "set or POPPED, never written False"


def test_the_mark_form_defaults_the_project_from_last_month(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    _mark("aug", "pk", "2026-08-10", "p2")
    page = client.get("/attendance/mark?date=2026-09-15").get_data(as_text=True)
    # The picker only knows the employee once one is posted back, so the
    # default is proved through _project_options() directly as well as through
    # the rejected-form path the page uses.
    assert AT._project_options(SITE, "", "pk", "2026-09").count(
        '<option value="p2" selected>') == 1
    assert 'id="project_id"' in page


def test_the_hand_forms_default_is_never_a_project_at_another_site(client):
    _site()
    STORE["addresses"][OFFICE] = {"id": OFFICE, "label": "OFFICE",
                                  "type": "site", "line1": "x"}
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _project("px", "Elsewhere", OFFICE)
    _person()
    _mark("aug", "pk", "2026-08-10", "px", aid=OFFICE)
    opts = AT._project_options(SITE, "", "pk", "2026-09")
    assert " selected>" not in opts.split("</option>", 1)[1], (
        "last month's project is at another site: nothing is preselected")


# =============================================================================
# 4. THE UNASSIGNED SCREEN — ruling 3
# =============================================================================

def test_the_screen_lists_a_worker_month_and_why_it_is_there(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    _mark("m2", "pk", "2026-09-02", "", status=AT.HALF)
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "PUSHKAR MISHRA" in page
    assert "September 2026" in page
    assert "two or more projects at that site" in page
    g = AT.unassigned_worker_months()[0]
    assert g["days"] == 1.5, "the day-count rule is share_of(), half included"
    assert g["ambiguous"] is True


def test_the_screen_says_so_when_no_project_is_filed_at_the_site(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "no project is filed at that site" in page


def test_the_screen_flags_a_worker_month_whose_slip_is_already_issued(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    slip, _ = PAY.create_draft("pk", "2026-09")
    PAY.issue(slip)
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "the slip is waiting for a project" in page


def test_assigning_writes_every_unassigned_day_of_the_month(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    for d in range(1, 5):
        _mark(f"m{d}", "pk", f"2026-09-{d:02d}", "")
    r = client.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09", "project_id": "p2"})
    assert r.status_code == 302
    assert {m["project_id"] for m in AT.month_markings("pk", "2026-09")} == {"p2"}
    assert {m["project_name"] for m in AT.month_markings("pk", "2026-09")} \
        == {"Roadpali B"}
    assert AT.unassigned_worker_months() == []


def test_assigning_to_overhead_takes_the_month_off_the_list_for_good(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    client.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09",
        "project_id": AT.OVERHEAD_CHOICE})
    assert AT.is_overhead(STORE["attendance"]["m1"])
    assert AT.unassigned_worker_months() == []


def test_assigning_never_touches_a_marking_that_already_names_a_project(client):
    _site()
    _project("p1", "Roadpali A")
    _project("p2", "Roadpali B")
    _person()
    _mark("done", "pk", "2026-09-01", "p1")
    _mark("open", "pk", "2026-09-02", "")
    client.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09", "project_id": "p2"})
    assert STORE["attendance"]["done"]["project_id"] == "p1", (
        "already assigned: /attendance/edit/<id> is where that is changed")
    assert STORE["attendance"]["open"]["project_id"] == "p2"


def test_assigning_refuses_a_project_that_is_not_at_the_markings_site(client):
    _site()
    STORE["addresses"][OFFICE] = {"id": OFFICE, "label": "OFFICE",
                                  "type": "site", "line1": "x"}
    _project("px", "Elsewhere", OFFICE)
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    done, err = AT.assign_month("pk", "2026-09", "px")
    assert done == 0 and "another site" in err
    assert STORE["attendance"]["m1"]["project_id"] == ""


def test_assigning_a_blank_is_refused(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    done, err = AT.assign_month("pk", "2026-09", "")
    assert done == 0 and "Choose a project" in err


def test_assigning_a_deleted_project_is_refused(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    done, err = AT.assign_month("pk", "2026-09", "ghost")
    assert done == 0 and "no longer exists" in err


def test_every_assignment_is_logged_who_when_before_after(client):
    """Ruling 3's *"logged (who/when/before → after)"*, on the marking."""
    _site()
    _project("p1", "Roadpali A")
    _person()
    _mark("m1", "pk", "2026-09-01", "")
    AT.assign_month("pk", "2026-09", "p1", actor_id="u-1")
    log = STORE["attendance"]["m1"][EL.FIELD]
    assert len(log) == 1
    row = log[0]
    assert row["by"] == "u-1"
    assert row["before"] == "— unassigned —"
    assert row["after"] == "Roadpali A"
    assert row["field"] == "Project — 2026-09-01"
    datetime.datetime.strptime(row["at"], "%Y-%m-%d %H:%M:%S")


def test_the_screen_is_empty_and_says_so_when_nothing_is_waiting(client):
    _site()
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "Nothing is unassigned" in page


def test_the_screen_prints_the_overhead_total_separately(client):
    _site()
    _person()
    _mark("o1", "pk", "2026-09-01", "", **AT.overhead_fields(True))
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "Overhead: 1 marking" in page
    assert "Nothing is unassigned" in page, "overhead is not on the list"


# =============================================================================
# 5. THE PERMISSION — labour.assign, Owner + Director
# =============================================================================

def test_labour_assign_is_a_permission_in_the_catalogue():
    assert "labour.assign" in auth.PERMISSIONS
    assert auth.PERMISSIONS["labour.assign"][1] == "Employee costs"


def test_both_routes_are_classified_under_it():
    assert auth.ROUTE_PERMISSIONS["attendance.unassigned_labour"] == "labour.assign"
    assert auth.ROUTE_PERMISSIONS["attendance.assign_labour"] == "labour.assign"


@pytest.mark.parametrize("slug,granted", [
    ("owner", True), ("director", True), ("hr", False),
    ("operation-head", False), ("sales-manager", False),
    ("purchase-manager", False), ("accountant", False)])
def test_the_default_grants_are_owner_and_director_only(slug, granted):
    perms = auth.BUILTIN_ROLES[slug][1]
    assert ("labour.assign" in perms) is granted, (
        f"{slug}: ruling 3 says Owner + Director by default. An Owner grants "
        f"it anywhere at /roles/edit/<id> with a tick.")


def _sign_in_as(client, slug: str) -> str:
    """One builtin role and the session on it — `test_pnl_access.py`'s helper."""
    uid = f"lab-{slug}"
    STORE.setdefault("users", {})[uid] = {
        "id": uid, "username": f"{slug}@lab", "display_name": f"Test {slug}",
        "password_hash": "not-a-hash", "role_ids": [f"role-{slug}"],
        "active": True, "created_at": "2026-08-01 09:00", "created_by": "test"}
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = uid
    return uid


def test_a_reader_without_the_permission_is_refused_both_routes(client):
    auth.ensure_builtin_roles()
    _sign_in_as(client, "hr")
    try:
        assert client.get("/attendance/unassigned").status_code == 403
        assert client.post("/attendance/assign", data={
            "employee_id": "pk", "month": "2026-09",
            "project_id": "p1"}).status_code == 403
    finally:
        STORE["users"].pop("lab-hr", None)


def test_the_muster_links_the_unassigned_screen_for_a_reader_who_may_assign(
        client):
    """
    ⚠ The link is the screen's ONLY route in (`UNLINKED_ON_PURPOSE` in
    `tests/test_nav_reachability.py` names this test as the reason it may be
    off the rail), and it is permission-filtered — so a reader without
    `labour.assign` gets `/attendance/` with no link at all. The golden for
    `/attendance/` is the Owner's render, re-baselined in the same pass; the HR
    render is the one that must be unchanged.
    """
    _site()
    auth.ensure_builtin_roles()
    try:
        # ⚠ The ANCHOR, not the URL: the `.att-assign` CSS comment names the
        #   path too, and a substring match on it would pass for both roles.
        link = '<a href="/attendance/unassigned" class="btn btn-ghost">'
        _sign_in_as(client, "owner")
        assert link in client.get("/attendance/").get_data(as_text=True)
        _sign_in_as(client, "hr")
        page = client.get("/attendance/").get_data(as_text=True)
        assert "Attendance" in page, "HR may read the muster"
        assert link not in page
    finally:
        for slug in ("owner", "hr"):
            STORE["users"].pop(f"lab-{slug}", None)


# =============================================================================
# 6. THE MONTH LABEL TWIN
# =============================================================================

def test_the_month_label_twin_agrees_with_payrolls_on_every_month():
    """
    `attendance._month_label()` exists because `payroll.py` imports
    `attendance.py`, so an import back is a cycle. The twin may not drift.
    """
    for y in (2025, 2026):
        for m in range(1, 13):
            key = f"{y}-{m:02d}"
            assert AT._month_label(key) == PAY.month_label(key)
    assert AT._month_label("") == PAY.month_label("")
    assert AT._month_label("nonsense") == PAY.month_label("nonsense")
