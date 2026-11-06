"""
ONE TAB PER SITE — CLIENT_CHANGES.md §0 **sixty-eighth** block (6 November
2026).

The client keeps one tab per site. A worker who moved during the month is on
several tabs, and their day cells on each tab are their days AT THAT SITE.

What this file holds:

* **every tab is read**; a tab's site is its SITE column where filled, else
  the tab name, and the preview says which; a several-tab workbook with a tab
  that names no site and carries no SITE is REFUSED, never guessed;
* **one worker across tabs is ONE worker-month** — one payslip, money summed —
  and the slip is exactly what a single-tab import of the same totals gives
  (pinned against figures measured on `54a63cc`, before this block);
* a day marked on **two tabs** is flagged and imported on **neither**;
* a site name that maps to an address with **two projects** (RIL Jamnagar /
  RIL Jamnagar Shed) is asked **once per site name**, and the answer is
  **saved and reused** by the next import;
* the **last-month default fills only days with no site**.
"""

import io

import pytest

import attendance as AT
import payimport as PI
import payroll as PAY
from store import STORE

openpyxl = pytest.importorskip("openpyxl")

TAIL = ["Days", "OT", "OTCD", "TOTAL DAYS", "PER DAY SALARY", "TOTAL SALARY",
        "ADV", "BALANCE", "EXTRA EXP", "LOAN", "ACTUAL SALARY", "BALANCE LOAN"]
_OWNED = ("employees", "attendance", "pay_entries", "payslips", "pay_imports",
          "projects", "addresses", "settings")

ADDR = {"jam": "JAMNAGAR REFINERY", "blr": "BANGALORE", "gov": "GOVANDI",
        "rdp": "ROADPALI"}


@pytest.fixture()
def world(client):
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    for aid, label in ADDR.items():
        STORE["addresses"][aid] = {"id": aid, "label": label, "type": "site",
                                   "archived": False, "line1": "x"}
    for pid, name, aid in (("p-jam", "RIL Jamnagar", "jam"),
                           ("p-shed", "RIL Jamnagar Shed", "jam"),
                           ("p-blr", "Bangalore DC", "blr"),
                           ("p-rdp", "Roadpali", "rdp")):
        STORE["projects"][pid] = {
            "id": pid, "name": name, "norm_name": name.lower(), "client": "X",
            "notes": "", "site_address_id": aid, "site_address": ADDR[aid],
            "created_at": "2026-09-01 09:00", "updated_at": "2026-09-01 09:00"}
    for eid, name in (("pk", "PUSHKAR MISHRA"), ("nk", "NIRAJ KUMAR"),
                      ("gk", "GUDDU KUMAR")):
        STORE["employees"][eid] = {"id": eid, "name": name, "active": True,
                                   "day_rate": 800.0, "code": ""}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def book(tabs, days=30, title="ATTENDANCE FOR THE MONTH OF SEPTEMPER - 2026",
         site_header=True):
    """
    `tabs`: `[(tab title, rows)]` (or `(title, rows, "hidden")`); each row
    `{name, site?, marks {day: (present, ot)}, money {rate, adv, extra, loan,
    actual, bal}}`. A row's `site` is written into SITE; leave it out for a
    blank SITE cell.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for spec in tabs:
        tab, rows = spec[0], spec[1]
        ws = wb.create_sheet(tab)
        if len(spec) > 2:
            ws.sheet_state = spec[2]
        ws.cell(1, 1, title)
        heads = ["SR.NO", "NAME", "DESIGNATION"] + (["SITE"] if site_header else [])
        for c, h in enumerate(heads, start=1):
            ws.cell(2, c, h)
        d0 = len(heads) + 1
        for d in range(1, days + 1):
            ws.cell(2, d0 + 3 * (d - 1), float(d))
        tail0 = d0 + 3 * days
        col = {h: tail0 + i for i, h in enumerate(TAIL)}
        for h, c in col.items():
            ws.cell(2, c, h)
        for r, row in enumerate(rows, start=3):
            ws.cell(r, 1, float(r - 2))
            ws.cell(r, 2, row["name"])
            ws.cell(r, 3, "HELPER")
            if site_header and row.get("site"):
                ws.cell(r, 4, row["site"])
            for d, (present, ot) in row.get("marks", {}).items():
                c = d0 + 3 * (d - 1)
                ws.cell(r, c, present)
                if ot is not None:
                    ws.cell(r, c + 1, ot)
            m = row.get("money", {})
            for key, h in (("rate", "PER DAY SALARY"), ("adv", "ADV"),
                           ("extra", "EXTRA EXP"), ("loan", "LOAN"),
                           ("actual", "ACTUAL SALARY"), ("bal", "BALANCE LOAN")):
                if m.get(key) is not None:
                    ws.cell(r, col[h], m[key])
        ws.cell(3 + len(rows), 1, "TOTAL SALARY")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, data):
    r = client.post("/payroll/import/", data={
        "workbook": (io.BytesIO(data), "ATTENDANCE DATA.xlsx")},
        content_type="multipart/form-data")
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return r.headers["Location"].rsplit("/", 1)[-1]


def _form(sid, month="2026-09", **extra):
    """The commit form: each sheet site mapped by its label, every row's
    worker picked by name — what an operator accepting the preview posts."""
    rec = STORE["pay_imports"][sid]
    by_label = {v: k for k, v in ADDR.items()}
    form = {"month": month}
    for i, site in enumerate(rec["sites"]):
        aid = by_label.get(site.upper().replace("RIL JAMNAGAR SHED",
                                                "JAMNAGAR REFINERY")
                           .replace("RIL JAMNAGAR", "JAMNAGAR REFINERY"), "")
        form[f"site_{i}"] = aid
    names = {e["name"]: eid for eid, e in STORE["employees"].items()}
    workers = (PI.workers_of(rec) if hasattr(PI, "workers_of") else
               [{"name": r["name"], "rows": [i]} for i, r in enumerate(rec["rows"])])
    for w in workers:
        first = w["rows"][0]
        form[f"emp_{first}"] = names.get(w["name"], "")
    form.update(extra)
    return form


def _sites(sid):
    return STORE["pay_imports"][sid]["sites"]


def _by_day(eid, month="2026-09"):
    return {m["date"][-2:]: m for m in AT.month_markings(eid, month)}


# ── 0. which site a tab is ─────────────────────────────────────────────────

@pytest.mark.parametrize("name,want", [
    ("RIL JAMNAGAR", "RIL JAMNAGAR"), ("  Bangalore  DC ", "Bangalore DC"),
    ("Sheet1", ""), ("Sheet 2", ""), ("OCTOBER 2026", ""), ("Sept", ""),
    ("ATTENDANCE", ""), ("Salary Oct-26", ""), ("", ""),
    ("MARINE DRIVE", "MARINE DRIVE"),
])
def test_a_tab_name_is_a_site_only_when_it_names_one(name, want):
    assert PI.tab_site(name) == want


# ── 1. one worker across three tabs ────────────────────────────────────────

PUSH_MONEY = {"rate": 800, "adv": 1000, "extra": 250.5}


def _three_tab_book():
    return book([
        ("ROADPALI", [{"name": "PUSHKAR MISHRA",
                       "marks": {d: (1, 2 if d == 3 else None) for d in range(1, 11)},
                       "money": PUSH_MONEY}]),
        ("BANGALORE", [{"name": "PUSHKAR MISHRA",
                        "marks": {d: (1, None) for d in range(11, 21)},
                        "money": {"rate": 800, "adv": 500}}]),
        ("GOVANDI", [{"name": "PUSHKAR MISHRA",
                      "marks": {d: (0.5 if d == 25 else 1, None)
                                for d in range(21, 31)},
                      "money": {"rate": 800}}]),
    ])


def test_one_worker_across_three_tabs_is_one_worker_month(world):
    sid = _upload(world, _three_tab_book())
    rec = STORE["pay_imports"][sid]
    assert [t["site_from"] for t in rec["tabs"]] == ["tab", "tab", "tab"], \
        "no SITE filled: each tab's NAME is its site, and the preview says so"
    assert _sites(sid) == ["ROADPALI", "BANGALORE", "GOVANDI"]
    assert len(PI.workers_of(rec)) == 1, "three rows, one person"
    page = world.get(f"/payroll/import/preview/{sid}?month=2026-09").get_data(as_text=True)
    assert "site from the tab name" in page
    assert page.count('name="emp_') == 1, "one employee pick for the three rows"

    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    days = _by_day("pk")
    assert len(days) == 30
    assert {days[f"{d:02d}"]["project_id"] for d in range(1, 11)} == {"p-rdp"}
    assert {days[f"{d:02d}"]["project_id"] for d in range(11, 21)} == {"p-blr"}
    assert {days[f"{d:02d}"]["project_id"] for d in range(21, 31)} == {""}, \
        "GOVANDI carries no project: Unassigned, never guessed"
    assert {days[f"{d:02d}"]["site"] for d in range(21, 31)} == {"GOVANDI"}
    adv = [e for e in STORE["pay_entries"].values() if e["type"] == PAY.ADVANCE]
    assert [e["amount"] for e in adv] == [1500.0], "ADV summed into one line"


# The figures a SINGLE-TAB import of the same totals gives, measured on
# 54a63cc (the code before this block), pasted in and compared by repr.
SINGLE_TAB_SLIP = (
    "{'basic': 23600.0, 'ot': 400.0, 'travel': 250.5, 'other_allowance': 0.0, "
    "'gross': 24250.5, 'advance': 1500.0, 'loan_deduction': 0.0, "
    "'total_deduction': 1500.0, 'net_raw': 22750.5, 'round_off': 0.5, "
    "'payable': 22751, 'carry': 0.0, 'paid_days': 29.5}")
SLIP_KEYS = ("basic", "ot", "travel", "other_allowance", "gross", "advance",
             "loan_deduction", "total_deduction", "net_raw", "round_off",
             "payable", "carry", "paid_days")


def _slip_figures(eid="pk", month="2026-09"):
    slip, err = PAY.create_draft(eid, month)
    assert not err
    PAY.issue(slip)
    return repr({k: slip["snapshot"][k] for k in SLIP_KEYS})


def test_the_single_tab_slip_is_the_pinned_one(world):
    """The control: a single-tab sheet of the same totals, through the same
    import, gives the slip measured before this block."""
    STORE["settings"]["labour_cost"] = {"ot_multiplier": "2"}
    marks = {d: (0.5 if d == 25 else 1, 2 if d == 3 else None)
             for d in range(1, 31)}
    sid = _upload(world, book([("Sheet1", [{
        "name": "PUSHKAR MISHRA", "site": "ROADPALI", "marks": marks,
        "money": {"rate": 800, "adv": 1500, "extra": 250.5}}])]))
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert _slip_figures() == SINGLE_TAB_SLIP


def test_three_tabs_give_exactly_the_single_tab_slip(world):
    STORE["settings"]["labour_cost"] = {"ot_multiplier": "2"}
    sid = _upload(world, _three_tab_book())
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert _slip_figures() == SINGLE_TAB_SLIP


# ── 2. the same day on two tabs ────────────────────────────────────────────

def test_a_day_on_two_tabs_is_flagged_and_imported_on_neither(world):
    sid = _upload(world, book([
        ("ROADPALI", [{"name": "PUSHKAR MISHRA",
                       "marks": {d: (1, None) for d in range(1, 6)}}]),
        ("BANGALORE", [{"name": "PUSHKAR MISHRA",
                        "marks": {d: (1, None) for d in range(5, 11)}}]),
    ]))
    page = world.get(f"/payroll/import/preview/{sid}?month=2026-09").get_data(as_text=True)
    assert "marked on two tabs, NOT imported until resolved: day 5 " \
           "(ROADPALI / BANGALORE)" in page
    r = world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert "NOT+imported" in r.headers["Location"] or "NOT imported" in r.headers["Location"]
    days = _by_day("pk")
    assert "05" not in days, "never double-counted, never one picked"
    assert len(days) == 9
    assert STORE["pay_imports"][sid]["summary"]["clashes"] == \
        ["PUSHKAR MISHRA day 5 (ROADPALI / BANGALORE)"]
    snap = PAY.snapshot("pk", "2026-09")
    assert snap["paid_days"] == 9.0


# ── 3. a shared site, asked once per site name, saved, reused ──────────────

def _jamnagar_book(title="ATTENDANCE FOR THE MONTH OF SEPTEMPER - 2026"):
    return book([
        ("RIL JAMNAGAR", [
            {"name": "PUSHKAR MISHRA", "marks": {d: (1, None) for d in range(1, 16)}},
            {"name": "NIRAJ KUMAR", "marks": {d: (1, None) for d in range(1, 31)}}]),
        ("RIL JAMNAGAR SHED", [
            {"name": "PUSHKAR MISHRA", "marks": {d: (1, None) for d in range(16, 31)}},
            {"name": "GUDDU KUMAR", "marks": {d: (1, None) for d in range(1, 31)}}]),
    ], title=title)


def test_a_shared_site_is_asked_once_per_site_name(world):
    sid = _upload(world, _jamnagar_book())
    assert _sites(sid) == ["RIL JAMNAGAR", "RIL JAMNAGAR SHED"]
    page = world.get(f"/payroll/import/preview/{sid}?month=2026-09").get_data(as_text=True)
    assert page.count('name="sproj_') == 2, "one question per site name"
    assert 'name="proj_' not in page, "and none per worker"

    r = world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert STORE["attendance"] == {}, "unanswered: refused before any write"
    assert "RIL+JAMNAGAR" in r.headers["Location"] or "RIL JAMNAGAR" in r.headers["Location"]

    world.post(f"/payroll/import/commit/{sid}",
               data=_form(sid, sproj_0="p-jam", sproj_1="p-shed"))
    pk = _by_day("pk")
    assert {pk[f"{d:02d}"]["project_id"] for d in range(1, 16)} == {"p-jam"}
    assert {pk[f"{d:02d}"]["project_id"] for d in range(16, 31)} == {"p-shed"}
    assert {m["project_id"] for m in AT.month_markings("nk", "2026-09")} == {"p-jam"}
    assert {m["project_id"] for m in AT.month_markings("gk", "2026-09")} == {"p-shed"}
    saved = PI.saved_sites()
    assert saved["ril jamnagar"]["project"] == "p-jam"
    assert saved["ril jamnagar shed"]["project"] == "p-shed"


def test_a_saved_mapping_answers_the_next_import(world):
    sid = _upload(world, _jamnagar_book())
    world.post(f"/payroll/import/commit/{sid}",
               data=_form(sid, sproj_0="p-jam", sproj_1="p-shed"))

    oct_sid = _upload(world, _jamnagar_book(
        title="ATTENDANCE FOR THE MONTH OF OCTOBER - 2026"))
    page = world.get(f"/payroll/import/preview/{oct_sid}?month=2026-10").get_data(as_text=True)
    assert "saved from an earlier import" in page
    assert '<option value="p-jam" selected>' in page
    assert '<option value="p-shed" selected>' in page
    # The site picker is preselected from the saved mapping too: "RIL JAMNAGAR"
    # is no address label, so before it could only be picked by hand.
    assert page.count('<option value="jam" selected>') == 2

    # Posting only the site (no project answer at all): the saved one is used.
    form = {k: v for k, v in _form(oct_sid, month="2026-10").items()}
    world.post(f"/payroll/import/commit/{oct_sid}", data=form)
    pk = _by_day("pk", "2026-10")
    assert {pk[f"{d:02d}"]["project_id"] for d in range(1, 16)} == {"p-jam"}
    assert {pk[f"{d:02d}"]["project_id"] for d in range(16, 31)} == {"p-shed"}


# ── 4. the last-month default fills only days with no site ─────────────────

def _august(eid, pid):
    for d in (10, 11):
        STORE["attendance"][f"aug-{eid}-{d}"] = {
            "id": f"aug-{eid}-{d}", "employee_id": eid, "date": f"2026-08-{d}",
            "status": "present", "ot_hours": 0.0, "day_rate": 800.0,
            "site": "JAMNAGAR REFINERY", "site_address_id": "jam",
            "site_source": "book", "project_id": pid, "project_name": ""}


def test_the_last_month_default_fills_only_days_with_no_site(world):
    _august("pk", "p-shed")
    _august("nk", "p-shed")
    sid = _upload(world, book([("Sheet1", [
        {"name": "PUSHKAR MISHRA", "marks": {1: (1, None), 2: (1, None)}},
        {"name": "NIRAJ KUMAR", "site": "RIL JAMNAGAR",
         "marks": {1: (1, None), 2: (1, None)}}])]))
    rec = STORE["pay_imports"][sid]
    assert rec["tabs"][0]["site_from"] == "mixed"
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid, sproj_0="p-jam"))
    assert {m["project_id"] for m in AT.month_markings("pk", "2026-09")} == \
        {"p-shed"}, "no site at all: last month's project"
    assert {m["site"] for m in AT.month_markings("pk", "2026-09")} == {""}
    assert {m["project_id"] for m in AT.month_markings("nk", "2026-09")} == \
        {"p-jam"}, "a site the sheet gives is never overridden by last month"


# ── 5. stop rather than guess ──────────────────────────────────────────────

def test_a_tab_that_names_no_site_with_no_site_column_stops_the_parse(world):
    r = PI.parse(book([
        ("BANGALORE", [{"name": "PUSHKAR MISHRA", "marks": {1: (1, None)}}]),
        ("Sheet2", [{"name": "NIRAJ KUMAR", "marks": {1: (1, None)}}]),
    ]), "x.xlsx")
    assert r["rows"] == []
    assert any("Sheet2" in p and "cannot tell which site" in p
               for p in r["problems"])


def test_a_hidden_tab_is_listed_and_not_read(world):
    r = PI.parse(book([
        ("BANGALORE", [{"name": "PUSHKAR MISHRA", "marks": {1: (1, None)}}]),
        ("OLD COPY", [{"name": "PUSHKAR MISHRA", "marks": {1: (1, None)}}],
         "hidden"),
    ]), "x.xlsx")
    assert [(t["name"], t["site_from"]) for t in r["tabs"]] == \
        [("BANGALORE", "tab"), ("OLD COPY", "hidden")]
    assert len(r["rows"]) == 1


def test_a_differing_day_rate_between_tabs_is_not_imported(world):
    STORE["employees"]["pk"]["day_rate"] = 0.0
    sid = _upload(world, book([
        ("BANGALORE", [{"name": "PUSHKAR MISHRA", "marks": {1: (1, None)},
                        "money": {"rate": 800}}]),
        ("GOVANDI", [{"name": "PUSHKAR MISHRA", "marks": {2: (1, None)},
                      "money": {"rate": 900}}]),
    ]))
    page = world.get(f"/payroll/import/preview/{sid}?month=2026-09").get_data(as_text=True)
    assert "PER DAY SALARY differs between tabs" in page
    world.post(f"/payroll/import/commit/{sid}", data=_form(sid))
    assert STORE["employees"]["pk"]["day_rate"] == 0.0
