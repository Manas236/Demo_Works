"""
Two more day statuses on the muster — HALF DAY and PAID LEAVE.

CLIENT_CHANGES.md §0's **fifty-fifth** block (29 October 2026). ⚠ **Beyond
CC-2**, whose C5 says "0 or 1": the client's own monthly sheet marks a half day
0.5 and records paid leave as a comment on a 1, and the payslip pays both.

What this file holds:

1. A half day earns half the snapshotted day rate; paid leave earns a whole
   day; overtime is paid on a present or a half day only.
2. The share is a TABLE (`DAY_SHARE`), never a literal in `cost_of()` — the
   existing AST guard in `tests/test_attendance.py` still walks it, and the
   mutation below proves a literal `0.5` would be caught.
3. Present and Absent behave byte-for-byte as before.
4. The month reader the payslip uses (`month_figures()`) prices through
   `cost_of()` and counts each status.
5. `import_marking()` enforces the form's rules, above all one employee = one
   day: an existing marking is never overwritten.
"""

import ast
import pathlib

import pytest

import attendance as AT
import employee as EMP
import settings as S
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean():
    STORE.setdefault("employees", {}).clear()
    STORE.setdefault("attendance", {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    yield
    STORE.setdefault("employees", {}).clear()
    STORE.setdefault("attendance", {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)


def _marking(status, rate=800.0, ot=2.0, date="2026-09-03", eid="e1"):
    return {"id": f"m-{date}-{status}", "date": date, "employee_id": eid,
            "employee_name": "Amit", "employee_code": "", "day_rate": rate,
            "site": "", "status": status, "ot_hours": ot}


def _person(**over):
    p = {"id": "e1", "name": "Amit Kumar Yadav", "code": "", "active": True,
         "day_rate": 550.0, "designation": "Helper"}
    p.update(over)
    STORE.setdefault("employees", {})[p["id"]] = p
    return p


# ── 1. the money ─────────────────────────────────────────────────────────────

def test_a_half_day_earns_half_and_keeps_its_overtime():
    c = AT.cost_of(_marking(AT.HALF, rate=800.0, ot=2.0), 1.0)
    assert c["day"] == 400.0
    assert c["ot"] == 200.0          # 800 / 8 × 2 × 1
    assert c["total"] == 600.0


def test_paid_leave_earns_the_day_and_no_overtime():
    c = AT.cost_of(_marking(AT.PAID_LEAVE, rate=800.0, ot=3.0), 1.0)
    assert c["day"] == 800.0
    assert c["ot"] == 0.0, "overtime needs a day somebody WORKED"
    assert c["total"] == 800.0


def test_present_and_absent_are_unchanged():
    assert AT.cost_of(_marking(AT.PRESENT, 800.0, 2.0), 1.0)["total"] == 1000.0
    assert AT.cost_of(_marking(AT.ABSENT, 800.0, 2.0), 1.0)["total"] == 0.0


def test_the_multiplier_still_rides_on_a_half_days_overtime():
    c = AT.cost_of(_marking(AT.HALF, rate=800.0, ot=2.0), 2.0)
    assert c["ot"] == 400.0


def test_an_unknown_status_earns_nothing():
    assert AT.share_of("holiday") == 0.0
    assert AT.cost_of(_marking("holiday"), 1.0)["total"] == 0.0


# ── 2. the share is data, not a literal ──────────────────────────────────────

def _literals_in_cost_path(src: str) -> list:
    tree = ast.parse(src)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {
                "day_rate_of", "ot_amount", "cost_of"}:
            for inner in ast.walk(node):
                if isinstance(inner, ast.BinOp) and isinstance(
                        inner.op, (ast.Mult, ast.Div)):
                    for side in (inner.left, inner.right):
                        if isinstance(side, ast.Constant) and isinstance(
                                side.value, (int, float)):
                            found.append(side.value)
    return found


def test_the_half_share_is_not_a_literal_in_cost_of():
    src = (REPO / "attendance.py").read_text(encoding="utf8")
    assert _literals_in_cost_path(src) == []


def test_the_guard_would_catch_a_literal_half():
    """Mutation: write the half as a literal in cost_of() and the walk finds it."""
    src = (REPO / "attendance.py").read_text(encoding="utf8")
    old = "day = round(wage * share_of(status), 2)"
    assert old in src
    mutated = src.replace(old, "day = round(wage * 0.5, 2)")
    assert _literals_in_cost_path(mutated) == [0.5]


# ── 3. the pages ─────────────────────────────────────────────────────────────

def test_the_form_offers_all_four_statuses(client):
    html = client.get("/attendance/mark").get_data(as_text=True)
    for value in ("present", "half", "paid_leave", "absent"):
        assert f'value="{value}"' in html


def test_a_half_day_can_be_marked_through_the_form(client):
    aid = "addr-half-site"
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": "Half Site", "type": "site", "line1": "x",
        "city": "Pune", "state": "Maharashtra", "pincode": "411001",
        "country": "India"}
    try:
        p = _person()
        r = client.post("/attendance/mark", data={
            "date": "2026-09-04", "employee_id": p["id"], "site_id": aid,
            "status": "half", "ot_hours": "1", "notes": ""})
        assert r.status_code == 302, r.get_data(as_text=True)[:400]
        rec = list(STORE["attendance"].values())[0]
        assert rec["status"] == AT.HALF
        assert "import_batch" not in rec, "the form writes no batch id"
    finally:
        STORE["addresses"].pop(aid, None)


def test_the_badge_names_the_new_statuses():
    cells = AT.marking_cells(_marking(AT.HALF), 1.0)
    assert "Half day" in cells["status"] and cells["row_class"] == ""
    cells = AT.marking_cells(_marking(AT.PAID_LEAVE, ot=2.0), 1.0)
    assert "Paid leave" in cells["status"]
    assert "not paid — paid leave" in cells["ot"]


def test_worker_costs_counts_a_half_day_as_half():
    rows = [_marking(AT.PRESENT, date="2026-09-01"),
            _marking(AT.HALF, date="2026-09-02"),
            _marking(AT.PAID_LEAVE, date="2026-09-03"),
            _marking(AT.ABSENT, date="2026-09-04")]
    w = AT.worker_costs(rows)[0]
    assert w["days_present"] == 2.5
    assert w["days_marked"] == 4
    assert w["ot_hours"] == 4.0, "present + half carry overtime; leave does not"


# ── 4. the month the payslip reads ───────────────────────────────────────────

def test_month_figures_prices_through_cost_of():
    for m in (_marking(AT.PRESENT, 550.0, 2.0, "2026-09-01"),
              _marking(AT.HALF, 550.0, 0.0, "2026-09-02"),
              _marking(AT.PAID_LEAVE, 550.0, 0.0, "2026-09-03"),
              _marking(AT.ABSENT, 550.0, 0.0, "2026-09-04"),
              _marking(AT.PRESENT, 550.0, 0.0, "2026-10-01")):   # other month
        STORE["attendance"][m["id"]] = m
    f = AT.month_figures("e1", "2026-09")
    assert f["markings"] == 4
    assert (f["present_days"], f["half_days"], f["paid_leave_days"],
            f["absent_days"]) == (1, 1, 1, 1)
    assert f["paid_days"] == 2.5
    assert f["basic"] == 1375.0       # 550 × 2.5
    assert f["ot"] == 137.5           # 550 / 8 × 2
    assert f["rates"] == [550.0]


def test_month_figures_reads_each_days_snapshot_rate():
    STORE["attendance"]["a"] = _marking(AT.PRESENT, 500.0, 0.0, "2026-09-01")
    STORE["attendance"]["b"] = _marking(AT.PRESENT, 600.0, 0.0, "2026-09-02")
    f = AT.month_figures("e1", "2026-09")
    assert f["basic"] == 1100.0 and f["rates"] == [500.0, 600.0]


# ── 5. the import's write ────────────────────────────────────────────────────

SITE = {"site": "Roadpali", EMP.SITE_ADDRESS_FIELD: "", EMP.SITE_SOURCE_FIELD: ""}
NOPROJ = {"project_id": "", "project_name": ""}


def test_import_marking_writes_the_forms_record_plus_a_batch():
    p = _person()
    rid, err = AT.import_marking(p, "2026-09-05", AT.HALF, 2, SITE, NOPROJ, "b1")
    assert not err
    rec = STORE["attendance"][rid]
    assert rec["import_batch"] == "b1" and rec["day_rate"] == 550.0
    assert rec["status"] == AT.HALF and rec["ot_hours"] == 2.0


def test_import_marking_never_overwrites_a_day_already_marked():
    p = _person()
    STORE["attendance"]["hand"] = dict(_marking(AT.ABSENT, date="2026-09-05"),
                                       id="hand")
    rid, err = AT.import_marking(p, "2026-09-05", AT.PRESENT, 0, SITE, NOPROJ, "b1")
    assert rid == "" and err
    assert STORE["attendance"]["hand"]["status"] == AT.ABSENT
    assert len(STORE["attendance"]) == 1


def test_import_marking_refuses_what_the_form_refuses():
    p = _person(active=False)
    assert AT.import_marking(p, "2026-09-05", AT.PRESENT, 0, SITE, NOPROJ, "b")[1]
    p = _person(active=True, **{EMP.RATE_MODEL_FIELD: EMP.PRE_DAY_RATE})
    assert AT.import_marking(p, "2026-09-05", AT.PRESENT, 0, SITE, NOPROJ, "b")[1]
    p = _person(**{EMP.RATE_MODEL_FIELD: None})
    p.pop(EMP.RATE_MODEL_FIELD)
    assert AT.import_marking(p, "2026-09-05", "late", 0, SITE, NOPROJ, "b")[1]
    assert AT.import_marking(p, "2026-09-05", AT.PRESENT, 99, SITE, NOPROJ, "b")[1]
    assert AT.import_marking(p, "05/09/2026", AT.PRESENT, 0, SITE, NOPROJ, "b")[1]
    assert STORE["attendance"] == {}


def test_remove_batch_removes_that_batch_and_nothing_else():
    p = _person()
    AT.import_marking(p, "2026-09-05", AT.PRESENT, 0, SITE, NOPROJ, "b1")
    AT.import_marking(p, "2026-09-06", AT.PRESENT, 0, SITE, NOPROJ, "b2")
    STORE["attendance"]["hand"] = dict(_marking(AT.PRESENT, date="2026-09-07"),
                                       id="hand")
    assert AT.remove_batch("b1") == 1
    assert AT.remove_batch("") == 0, "a blank batch matches nothing"
    assert {r.get("import_batch") for r in STORE["attendance"].values()} == {
        "b2", None}
