"""
A search on the attendance pages — item B of the 27 October 2026 call
(CLIENT_CHANGES.md §0's **fifty-fourth** block).

The muster is a DAY at a time, because that is the unit CC-2 records in and
the unit "one employee, one site, one day" is written on. `/attendance/search`
is the other question the same records answer: what did one person, or one
site, cost over a stretch of days.

What this file holds to:

1.  **worker, site/project and a date range** each filter, one or all, and
    they compose;
2.  the three **presets** — last 10 days (inclusive of today), this calendar
    month, last calendar month — compute the range they say they do;
3.  the per-worker figures are **days present, OT hours and the wage**, and
    the wage comes from the **EXISTING** path: `cost_of()` at
    `settings.ot_multiplier()`, the same arithmetic `site_costs()` and
    `labour_cost_of()` use. ⚠ `test_the_wage_is_not_redefined_here` holds
    that structurally, so a second copy of the OT formula cannot appear
    beside this one;
4.  there is a **totals row**, and it totals what the rows show;
5.  a marking made under the **old monthly model** is counted and costed at
    nothing — `site_costs()`'s rule, not a new one;
6.  **no new permission**: `attendance.view`, the muster's own gate, and the
    three roles the HR wall refuses are refused here too;
7.  it is **screen only** and **writes nothing**.
"""

import datetime

import pytest

import attendance as A
import auth
import settings as S
from store import STORE

from test_attendance import _MINTED, _mark, _person, _site, _user_with  # noqa: F401


DAY = "2026-08-20"


@pytest.fixture(autouse=True)
def _clean():
    """`test_attendance.py`'s own cleanup — neither collection is in
    `conftest._fresh_store()`, and a leaked row reads as a seeder to
    `tests/test_hardening.py`."""
    for name in ("employees", "attendance"):
        STORE.setdefault(name, {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    _MINTED.clear()
    yield
    for name in ("employees", "attendance"):
        STORE.setdefault(name, {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


def _marking(rid, *, date, name="Ramesh Patil", eid="e1", site="Whitefield",
             project_id="", status=A.PRESENT, ot="0", rate=1000.0, **extra):
    """A marking written straight into the store, so a test can place one on
    any date without climbing the one-per-day constraint."""
    rec = {"id": rid, "date": date, "employee_id": eid, "employee_name": name,
           "employee_code": "", "day_rate": rate, "site": site,
           "project_id": project_id, "project_name": "Tower A" if project_id else "",
           "status": status, "ot_hours": ot, "notes": ""}
    rec.update(extra)
    STORE.setdefault("attendance", {})[rid] = rec
    return rec


# ═══ 1. THE PRESETS ════════════════════════════════════════════════════════

def test_last_10_days_includes_today_and_is_ten_days_long():
    lo, hi = A.preset_range(A.PRESET_LAST_10, "2026-10-27")
    assert (lo, hi) == ("2026-10-18", "2026-10-27")
    span = (datetime.date.fromisoformat(hi)
            - datetime.date.fromisoformat(lo)).days + 1
    assert span == 10, "ten days of markings, not eleven"


def test_this_month_runs_from_the_first_to_today():
    assert A.preset_range(A.PRESET_THIS_MONTH, "2026-10-27") == ("2026-10-01",
                                                                 "2026-10-27")


@pytest.mark.parametrize("today,want", [
    ("2026-10-27", ("2026-09-01", "2026-09-30")),   # 30-day month
    ("2026-03-15", ("2026-02-01", "2026-02-28")),   # February
    ("2026-01-15", ("2025-12-01", "2025-12-31")),   # across the year boundary
    ("2024-03-15", ("2024-02-01", "2024-02-29")),   # a leap February
])
def test_last_month_is_the_previous_CALENDAR_month(today, want):
    """Not the last thirty days: a wages question is asked by the month
    somebody is being paid for."""
    assert A.preset_range(A.PRESET_LAST_MONTH, today) == want


def test_an_unknown_preset_filters_nothing_rather_than_raising():
    assert A.preset_range("whatever", "2026-10-27") == ("", "")


# ═══ 2. THE FILTERS ════════════════════════════════════════════════════════

def test_the_date_range_is_inclusive_on_both_ends(client):
    for n, day in enumerate(("2026-08-19", "2026-08-20", "2026-08-21",
                             "2026-08-22"), start=1):
        _marking(f"m{n}", date=day)
    got = {r["date"] for r in A.search_markings("2026-08-20", "2026-08-21")}
    assert got == {"2026-08-20", "2026-08-21"}


def test_a_blank_filter_matches_everything(client):
    _marking("m1", date=DAY, eid="e1")
    _marking("m2", date=DAY, eid="e2", name="Suresh")
    assert len(A.search_markings()) == 2
    assert len(A.search_markings(employee_id="e1")) == 1


def test_the_worker_site_and_project_filters_compose(client):
    _marking("m1", date=DAY, eid="e1", site="Whitefield", project_id="p1")
    _marking("m2", date=DAY, eid="e1", site="Rabale", project_id="p2")
    _marking("m3", date=DAY, eid="e2", name="Suresh", site="Whitefield",
             project_id="p1")

    assert len(A.search_markings(employee_id="e1")) == 2
    assert len(A.search_markings(site="Whitefield")) == 2
    assert len(A.search_markings(project_id="p1")) == 2
    assert len(A.search_markings(employee_id="e1", site="Whitefield")) == 1
    assert len(A.search_markings(employee_id="e1", site="Whitefield",
                                 project_id="p2")) == 0


def test_the_site_filter_matches_the_SNAPSHOTTED_label(client):
    """
    ⚠ An address renamed next March must not restate which site somebody
    worked on last August, so the label ON THE RECORD is the answer. That
    also means an **unmapped** site string — one the address book does not
    hold — is searchable rather than invisible.
    """
    _marking("m1", date=DAY, site="A String Nobody Mapped")
    assert len(A.search_markings(site="A String Nobody Mapped")) == 1


def test_a_malformed_date_filters_nothing_rather_than_raising(client):
    _marking("m1", date=DAY)
    assert len(A.search_markings("not-a-date", "also-not")) == 1


# ═══ 3. THE PER-WORKER FIGURES ═════════════════════════════════════════════

def test_days_present_ot_hours_and_the_wage_per_worker(client):
    _marking("m1", date="2026-08-19", eid="e1", ot="2")
    _marking("m2", date="2026-08-20", eid="e1", ot="0")
    _marking("m3", date="2026-08-21", eid="e1", status=A.ABSENT, ot="3")
    _marking("m4", date="2026-08-20", eid="e2", name="Suresh", ot="0")

    rows = A.worker_costs(A.search_markings())
    assert [r["employee"] for r in rows] == ["Ramesh Patil", "Suresh"]

    ramesh = rows[0]
    assert ramesh["days_marked"] == 3
    assert ramesh["days_present"] == 2, "the absent day is marked, not present"
    assert ramesh["ot_hours"] == 2.0, "overtime on an ABSENT day is nil"
    # Two present days at a ₹1,000 day rate, plus 2 h at (1000 ÷ 8) × 1.
    assert ramesh["day_cost"] == 2000.0
    assert ramesh["ot_cost"] == 250.0
    assert ramesh["total"] == 2250.0


def test_the_overtime_multiplier_is_read_from_settings_and_not_hardcoded(client):
    """
    ⚠ CC-2's own warning: *"the statutory rate is generally twice, and a `1`
    written into this function would compute an underpayment that nobody could
    see."* This page must move with the setting.
    """
    _marking("m1", date=DAY, ot="8")
    assert A.worker_costs(A.search_markings())[0]["ot_cost"] == 1000.0
    S.save_labour_settings("2")
    assert A.worker_costs(A.search_markings())[0]["ot_cost"] == 2000.0


def test_an_old_monthly_model_marking_is_counted_and_costed_at_NOTHING(client):
    """
    `site_costs()`'s rule, not a new one. A monthly figure read as a day's pay
    is about twenty-six times too big, so no wage is computed from it at all —
    and the person is still shown, because dropping them would hide that
    somebody worked.
    """
    _marking("m1", date=DAY, eid="e1")
    rec = _marking("m2", date="2026-08-21", eid="e2", name="Suresh")
    rec.pop("day_rate")
    rec["monthly_salary"] = 26000.0
    rec["rate_model"] = "pre_day_rate"

    rows = {r["employee"]: r for r in A.worker_costs(A.search_markings())}
    assert set(rows) == {"Ramesh Patil", "Suresh"}
    assert rows["Suresh"]["refused"] == 1
    assert rows["Suresh"]["total"] == 0.0, (
        "a refused marking contributes NOTHING — never its monthly figure")
    assert rows["Suresh"]["days_present"] == 1, "the day still happened"


def test_the_wage_is_not_redefined_here():
    """
    ⚠ **Structural, and the one that matters.** A second place able to compute
    a wage is a second place the OT multiplier could be hardcoded — the defect
    `labour_cost_of()`'s docstring names. `worker_costs()` must price each
    marking through `cost_of()` and read the multiplier through the one
    accessor, exactly as `site_costs()` does.
    """
    import inspect

    src = inspect.getsource(A.worker_costs)
    assert "cost_of(r, multiplier)" in src
    assert "S.ot_multiplier()" in src
    for forbidden in ("STANDARD_HOURS_PER_DAY", "/ 8", "* 1.5", "ot_amount("):
        assert forbidden not in src, (
            f"worker_costs() computes {forbidden!r} itself instead of going "
            f"through cost_of()")


# ═══ 4. THE PAGE ═══════════════════════════════════════════════════════════

def test_the_page_renders_the_rows_and_a_totals_row(client):
    _marking("m1", date=DAY, eid="e1", ot="2")
    _marking("m2", date=DAY, eid="e2", name="Suresh", ot="0")
    html = client.get(f"/attendance/search?from={DAY}&to={DAY}").get_data(as_text=True)

    assert "Ramesh Patil" in html and "Suresh" in html
    assert "All workers" in html, "the totals row"
    # 1,000 + 250 for Ramesh, 1,000 for Suresh.
    assert "2,250" in html and "1,000" in html


def test_the_totals_row_totals_what_the_rows_show(client):
    _marking("m1", date=DAY, eid="e1", ot="2")
    _marking("m2", date=DAY, eid="e2", name="Suresh", ot="8")
    rows = A.worker_costs(A.search_markings())
    total = round(sum(r["total"] for r in rows), 2)
    assert total == 1250.0 + 2000.0
    html = client.get(f"/attendance/search?from={DAY}&to={DAY}").get_data(as_text=True)
    assert f"{total:,.0f}" in html


def test_the_preset_links_are_on_the_page_and_keep_the_other_filters(client):
    _marking("m1", date=DAY, eid="e1")
    html = client.get("/attendance/search?employee_id=e1").get_data(as_text=True)
    for _name, label in A.PRESETS:
        assert label in html
    assert "employee_id=e1" in html, (
        "a preset link that dropped the worker filter would reset the search")


def test_the_default_view_is_the_last_ten_days(client):
    today = datetime.date.today()
    _marking("m1", date=today.isoformat())
    _marking("m2", date=(today - datetime.timedelta(days=40)).isoformat(),
             eid="e2", name="Suresh")
    html = client.get("/attendance/search").get_data(as_text=True)
    # ⚠ The worker DROPDOWN lists everybody ever marked, deliberately — see
    #   `_search_filter_options()`. So this looks at the result table, which
    #   is what the range actually filters.
    table = html.split('<table class="reg-table">')[-1]
    assert "Ramesh Patil" in table
    assert "Suresh" not in table, "40 days ago is outside the default range"


def test_an_empty_result_says_so_rather_than_rendering_a_blank_table(client):
    html = client.get(f"/attendance/search?from={DAY}&to={DAY}").get_data(as_text=True)
    assert "No markings match" in html


def test_the_filter_options_come_from_the_MARKINGS(client):
    """
    ⚠ Not from the address book and the project register. A site nobody has
    ever been marked on would be an option that always returns nothing, and an
    **unmapped** site string would be missing altogether — which is exactly
    the attribution the muster's unmapped band exists to surface.
    """
    _marking("m1", date=DAY, site="A String Nobody Mapped", project_id="p1")
    _site("Never Used")
    html = client.get(f"/attendance/search?from={DAY}&to={DAY}").get_data(as_text=True)
    assert "A String Nobody Mapped" in html
    assert "Never Used" not in html


@pytest.mark.parametrize("field", ["site", "employee_name", "employee_code"])
def test_user_text_reaching_this_page_is_escaped(client, field):
    """
    ABOUT.md §9 — user text is escaped at every site where it reaches HTML.
    Three fields, because each is interpolated at its own place: the site into
    the filter list, the name into the row, the code into the sub-line.
    """
    nasty = 'Ram & Co <script>alert(1)</script>'
    # `_marking`'s own keyword for the name is `name`; the other two are the
    # record's keys and reach it through `**extra`.
    _marking("m1", date=DAY,
             **({"name": nasty} if field == "employee_name" else {field: nasty}))
    html = client.get(f"/attendance/search?from={DAY}&to={DAY}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "Ram &amp; Co" in html


# ═══ 5. ACCESS, AND WHAT IT DOES NOT DO ════════════════════════════════════

def test_it_is_classified_under_the_MUSTERS_OWN_permission_and_mints_none():
    assert auth.ROUTE_PERMISSIONS["attendance.search_attendance"] == "attendance.view"
    assert auth.ROUTE_PERMISSIONS["attendance.list_attendance"] == "attendance.view"
    assert not [p for p in auth.PERMISSIONS if p.startswith("attendance.")
                and p not in ("attendance.view", "attendance.create",
                              "attendance.edit", "attendance.delete")], (
        "item B mints no permission")


@pytest.mark.parametrize("slug", ["sales-manager", "purchase-manager",
                                  "accountant", "operation-head"])
def test_the_roles_refused_the_muster_are_refused_the_search(client, slug):
    """
    The HR wall (B4) and our own Operation Head derivation, holding on the new
    page because it is the same permission rather than because somebody
    remembered to repeat the rule.
    """
    user = _user_with(slug)
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]
    r = client.get("/attendance/search", follow_redirects=False)
    assert r.status_code in (302, 303, 403), (
        f"{slug} reached the search page")


def test_hr_is_admitted(client):
    user = _user_with("hr")
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]
    assert client.get("/attendance/search").status_code == 200


def test_the_page_writes_nothing(client):
    _marking("m1", date=DAY, eid="e1", ot="2")
    before = {k: dict(v) for k, v in STORE["attendance"].items()}
    settings_before = dict(STORE.get("settings") or {})
    client.get(f"/attendance/search?from={DAY}&to={DAY}")
    client.get("/attendance/search?preset=last-month")
    assert STORE["attendance"] == before
    assert dict(STORE.get("settings") or {}) == settings_before


def test_it_is_GET_only_and_has_no_print_route():
    import app as app_module

    rules = [r for r in app_module.app.url_map.iter_rules()
             if r.endpoint == "attendance.search_attendance"]
    assert len(rules) == 1
    assert set(rules[0].methods) - {"HEAD", "OPTIONS"} == {"GET"}
    assert not [r for r in app_module.app.url_map.iter_rules()
                if str(r.rule).startswith("/attendance/") and "print" in str(r.rule)], (
        "item B is screen only")
