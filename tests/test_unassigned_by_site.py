"""
/attendance/unassigned SPLITS BY SITE — CLIENT_CHANGES.md §0's
**seventy-first** block (6 November 2026).

* One row per **worker x month x site**, the site read off each MARKING;
  never one row spanning several sites.
* A row offers only the projects filed at ITS site, plus *No project
  (overhead)*; assigning it writes only that site's unassigned days of that
  worker-month, and logs it as today.
* A site with no project says *No project at this site yet* and links to
  creating one.
* A marking with no site at all is its own *No site recorded* row, offered
  every project plus overhead.
* Overhead takes a row off the list for good, so it ASKS FIRST.
"""

import datetime
import re

import pytest

import attendance as AT
import employee as EMP
from store import STORE
from test_labour_assign import _clean, _mark, _person, _project, _site  # noqa: F401

SITE = "addr-roadpali"
OTHER = "addr-blr"


@pytest.fixture(autouse=True)
def _other_site():
    STORE.setdefault("addresses", {})[OTHER] = {
        "id": OTHER, "label": "BANGALORE", "type": "site", "line1": "x"}
    yield
    STORE["addresses"].pop(OTHER, None)


def _rows(page):
    body = page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r"<tr>.*?</tr>", body, flags=re.S)


def _options(row):
    return re.findall(r'<option value="([^"]*)">([^<]*)</option>', row)


def _hidden(row, name):
    return re.search(rf'name="{name}" value="([^"]*)"', row).group(1)


def _two_site_month():
    _site()
    _project("p-rdp", "Roadpali A")
    _project("p-rdp2", "Roadpali B")
    _project("p-blr", "Bangalore DC", aid=OTHER)
    _project("p-blr2", "Bangalore Annexe", aid=OTHER)
    _person()
    for d in range(1, 4):
        _mark(f"r{d}", "pk", f"2026-09-{d:02d}")
    for d in range(10, 15):
        _mark(f"b{d}", "pk", f"2026-09-{d:02d}", aid=OTHER, site="BANGALORE")


def test_a_worker_month_across_two_sites_is_two_rows(client):
    _two_site_month()
    groups = AT.unassigned_worker_months()
    assert sorted((g["site_label"], len(g["markings"])) for g in groups) == \
        [("BANGALORE", 5), ("ROADPALI", 3)]
    rows = _rows(client.get("/attendance/unassigned").get_data(as_text=True))
    assert len(rows) == 2


def test_each_row_offers_only_its_own_sites_projects_and_overhead(client):
    _two_site_month()
    rows = _rows(client.get("/attendance/unassigned").get_data(as_text=True))
    by_site = {("BANGALORE" if "BANGALORE" in r else "ROADPALI"): r for r in rows}
    for site, want in (("ROADPALI", {"Roadpali A", "Roadpali B"}),
                       ("BANGALORE", {"Bangalore DC", "Bangalore Annexe"})):
        opts = [n for _v, n in _options(by_site[site])]
        assert opts[0] == "— choose —"
        assert set(opts[1:-1]) == want and len(opts) == 4, (site, opts)
        assert opts[-1] == "No project (overhead)"


def test_assigning_one_site_leaves_the_other_untouched(client):
    _two_site_month()
    before = {k: dict(v) for k, v in STORE["attendance"].items()
              if k.startswith("b")}
    rows = _rows(client.get("/attendance/unassigned").get_data(as_text=True))
    rdp = next(r for r in rows if "ROADPALI" in r)
    r = client.post("/attendance/assign", data={
        "employee_id": _hidden(rdp, "employee_id"),
        "month": _hidden(rdp, "month"), "site": _hidden(rdp, "site"),
        "project_id": "p-rdp2"})
    assert r.status_code == 302 and "3+markings+assigned" in r.headers["Location"]
    assert {STORE["attendance"][f"r{d}"]["project_id"] for d in range(1, 4)} \
        == {"p-rdp2"}
    after = {k: v for k, v in STORE["attendance"].items() if k.startswith("b")}
    assert after == before, "the Bangalore days are byte-for-byte as they were"
    left = AT.unassigned_worker_months()
    assert [(g["site_label"], len(g["markings"])) for g in left] == \
        [("BANGALORE", 5)]


def test_a_project_from_another_site_is_refused_on_a_sited_row(client):
    _two_site_month()
    key = AT.SITE_BOOK + SITE
    done, err = AT.assign_month("pk", "2026-09", "p-blr", site=key)
    assert done == 0 and err
    assert all(not STORE["attendance"][f"r{d}"]["project_id"] for d in range(1, 4))


def test_the_assignment_is_logged_as_today(client):
    _two_site_month()
    AT.assign_month("pk", "2026-09", "p-rdp", actor_id="u-1",
                    site=AT.SITE_BOOK + SITE)
    import editlog as EL
    log = STORE["attendance"]["r1"][EL.FIELD]
    assert log[-1]["at"][:10] == datetime.date.today().isoformat()
    assert log[-1]["after"] == "Roadpali A" and log[-1]["by"] == "u-1"


# ── a site with no project ─────────────────────────────────────────────────

def test_a_site_with_no_project_says_so_and_links_to_creating_one(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01")
    rows = _rows(client.get("/attendance/unassigned").get_data(as_text=True))
    assert len(rows) == 1
    assert "No project at this site yet" in rows[0]
    assert 'href="/projects/create"' in rows[0]
    assert [n for _v, n in _options(rows[0])][1:] == ["No project (overhead)"]


def test_overhead_asks_for_confirmation_before_it_writes(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01")
    rows = _rows(client.get("/attendance/unassigned").get_data(as_text=True))
    form = {"employee_id": _hidden(rows[0], "employee_id"),
            "month": _hidden(rows[0], "month"),
            "site": _hidden(rows[0], "site"),
            "project_id": AT.OVERHEAD_CHOICE}
    r = client.post("/attendance/assign", data=form)
    assert r.status_code == 302
    assert not AT.is_overhead(STORE["attendance"]["m1"]), "nothing written yet"
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert 'id="confirm-overhead"' in page
    assert "for good" in page and "Yes, mark it overhead" in page
    assert len(AT.unassigned_worker_months()) == 1, "the row is still listed"
    r = client.post("/attendance/assign", data=dict(form, confirm="1"))
    assert AT.is_overhead(STORE["attendance"]["m1"])
    assert AT.unassigned_worker_months() == []


def test_no_confirmation_panel_without_an_overhead_request(client):
    _site()
    _person()
    _mark("m1", "pk", "2026-09-01")
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert 'id="confirm-overhead"' not in page


# ── a marking with no site at all ──────────────────────────────────────────

def test_a_marking_with_no_site_is_its_own_row_offered_every_project(client):
    _two_site_month()
    _mark("n1", "pk", "2026-09-20", aid="", site="",
          **{EMP.SITE_SOURCE_FIELD: ""})
    rows = _rows(client.get("/attendance/unassigned").get_data(as_text=True))
    assert len(rows) == 3
    none = next(r for r in rows if "No site recorded" in r)
    names = sorted(n for _v, n in _options(none)[1:-1])
    assert names == ["Bangalore Annexe", "Bangalore DC", "Roadpali A",
                     "Roadpali B"]
    assert _options(none)[-1][1] == "No project (overhead)"
    r = client.post("/attendance/assign", data={
        "employee_id": "pk", "month": "2026-09",
        "site": _hidden(none, "site"), "project_id": "p-blr"})
    assert r.status_code == 302
    assert STORE["attendance"]["n1"]["project_id"] == "p-blr"
    assert all(not STORE["attendance"][k]["project_id"]
               for k in STORE["attendance"] if k != "n1"), \
        "only the no-site day moved"


def test_a_legacy_site_string_is_its_own_row_and_never_matched(client):
    _two_site_month()
    _mark("t1", "pk", "2026-09-21", aid="", site="JAMNAGAR OLD")
    groups = {g["site_kind"]: g for g in AT.unassigned_worker_months()}
    assert groups["text"]["site_label"] == "JAMNAGAR OLD"
    page = client.get("/attendance/unassigned").get_data(as_text=True)
    assert "not in the address book" in page
