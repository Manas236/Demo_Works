"""
LABOUR INTO THE PROJECT P&L — estimate, then actual.

CLIENT_CHANGES.md §0's **sixty-sixth** block; Manas's rulings of 5 November
2026; `docs/LABOUR_PL.md` is the diagnosis the block was written from.

**Ruling 1, which is what this file holds.** A project's labour cost is the
muster's own ESTIMATE until the month is paid, and the issued payslip's own
earnings afterwards:

| the worker-month | the project's labour for it |
|---|---|
| no issued slip | `cost_of()` per marking, summed — the day rate SNAPSHOTTED on each marking times `DAY_SHARE` for its status, plus OT |
| an ISSUED slip | its share of the slip's **wages + OT + travel**, split across projects by the days each got |
| a CANCELLED slip | back to the estimate, by the same one condition |

⚠ **Advances, loans, loan recovery and the statutory heads are NEVER project
  cost** — ruling 1 in terms, and `SLIP_COST_HEADS` is the whole of what is
  read off a slip.

⚠ **The denominator of the split is the worker's WHOLE month**, every project
  and the office days too. Over the rows handed in, each project would take
  100% of one slip and the month would be billed twice.

The arithmetic is all in `attendance.py` — the one module allowed to compute a
wage (§0's forty-seventh and fifty-fifth blocks) — and `pnl.py` takes one sum
out of it, which `tests/test_attendance.py` holds.
"""

import ast
import pathlib

import pytest

import attendance as AT
import employee as EMP
import payroll as PAY
import pnl as PNL
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

SITE = "ls-site"
SITE2 = "ls-site-2"
PID = "ls-p1"
PID2 = "ls-p2"

_OWNED = ("attendance", "employees", "projects", "addresses",
          "pay_entries", "payslips", "settings")


@pytest.fixture()
def world(client):
    """
    Two sites, a project on each, one worker on 800 a day.

    ⚠ Snapshot-and-restore, never clear-on-teardown —
    `tests/test_project_labour_oct28.py::world`'s rule, for its reason:
    `addresses` is demo-seeded once per process and clearing it breaks later
    files.
    """
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    for aid, label in ((SITE, "Jamnagar Refinery"), (SITE2, "Roadpali")):
        STORE["addresses"][aid] = {"id": aid, "label": label, "type": "site",
                                   "archived": False}
    for pid, name, aid in ((PID, "Jamnagar", SITE), (PID2, "Roadpali", SITE2)):
        STORE["projects"][pid] = {
            "id": pid, "name": name, "norm_name": name.lower(),
            "client": "IOCL", "notes": "",
            "site_address_id": aid, "site_address": "",
            "created_at": "2026-10-01 09:00", "updated_at": "2026-10-01 09:00"}
    STORE["employees"]["e1"] = {
        "id": "e1", "name": "Ramesh Patil", "code": "W-01",
        "designation": "Fitter", "day_rate": 800.0, "active": True,
        "site": "Jamnagar Refinery", EMP.SITE_ADDRESS_FIELD: SITE,
        EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def _mark(mid, date, status="present", ot=0.0, pid=PID, site_id=SITE,
          eid="e1", rate=800.0, **over):
    rec = {"id": mid, "employee_id": eid, "employee_name": "Ramesh Patil",
           "employee_code": "W-01", "date": date, "status": status,
           "ot_hours": ot, "day_rate": rate, "site": "Jamnagar Refinery",
           EMP.SITE_ADDRESS_FIELD: site_id,
           EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
           "project_id": pid,
           "project_name": (STORE["projects"].get(pid) or {}).get("name", "")}
    rec.update(over)
    STORE["attendance"][mid] = rec
    return rec


def _slip(sid, month, status=PAY.ISSUED, basic=0.0, ot=0.0, travel=0.0,
          advance=0.0, loan=0.0, eid="e1", **snap):
    s = {"id": sid, "employee_id": eid, "month": month, "status": status,
         "snapshot": dict({"employee_name": "Ramesh Patil", "basic": basic,
                           "ot": ot, "travel": travel, "advance": advance,
                           "loan_deduction": loan,
                           "payable": basic + ot + travel - advance - loan},
                          **snap)}
    STORE["payslips"][sid] = s
    return s


# =============================================================================
# 1. THE ESTIMATE — the payroll module's own day-count rule, reused
# =============================================================================

def test_the_estimate_is_the_day_rate_times_the_day_share(world):
    """
    Present 1, half 0.5, paid leave 1, absent 0 — `DAY_SHARE`, and the figure
    is `cost_of()`'s, not a second rule beside it.
    """
    _mark("m1", "2026-10-01", "present")      # 800
    _mark("m2", "2026-10-02", "half")         # 400
    _mark("m3", "2026-10-03", "paid_leave")   # 800
    _mark("m4", "2026-10-04", "absent")       # 0
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert got["estimate"] == 2000.0
    assert got["actual"] == 0.0
    assert got["total"] == 2000.0
    assert (got["markings"], got["costed"], got["refused"]) == (4, 4, 0)
    assert got["estimate_markings"] == 4
    assert got["slips"] == 0


def test_the_estimate_carries_overtime_at_the_setting(world):
    """1,000 + (1,000 ÷ 8) × 2h × 2 = 1,500 — `test_pnl.py`'s own figure."""
    STORE["settings"]["labour_cost"] = {"ot_multiplier": "2"}
    _mark("m1", "2026-10-01", ot=2, rate=1000.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["estimate"] == 1500.0


def test_overtime_on_a_half_day_is_paid_and_on_an_absent_day_is_not(world):
    """`OT_STATUSES` — the estimate inherits `cost_of()`'s rule, not a copy."""
    _mark("m1", "2026-10-01", "half", ot=8)       # 400 + 800
    _mark("m2", "2026-10-02", "absent", ot=8)     # 0, and no OT
    assert AT.labour_split_of(AT.markings_for_project(PID))["estimate"] == 1200.0


def test_the_day_count_rule_is_share_of_and_not_a_second_table(world):
    """
    ⚠ **No numeric constant may appear in a multiplication in the split.**
    `tests/test_attendance.py` walks `cost_of()`'s AST for the same reason: a
    literal day share here would be a second day-count rule, and ruling 1 says
    *"the payroll module's OWN day-count rule (reuse it, never a second
    rule)"*.
    """
    tree = ast.parse((REPO / "attendance.py").read_text(encoding="utf8"))
    wanted = {"labour_split_of", "paid_share", "slip_earnings"}
    seen = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in wanted):
            continue
        seen.add(node.name)
        for sub in ast.walk(node):
            if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mult):
                for side in (sub.left, sub.right):
                    assert not isinstance(side, ast.Constant), (
                        f"{node.name}() multiplies by the literal "
                        f"{side.value!r} — the day share is DAY_SHARE and the "
                        f"OT multiplier is a setting")
    assert seen == wanted, f"not found in attendance.py: {sorted(wanted - seen)}"


# =============================================================================
# 2. THE ACTUAL — an issued slip replaces the estimate
# =============================================================================

def test_an_issued_slip_replaces_the_estimate_for_that_worker_month(world):
    """
    Two present days estimate at 1,600. The slip was paid at 1,700 plus 300
    travel: the project's labour is 2,000, and the estimate is gone — not
    added to.
    """
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-10-02")
    _slip("s1", "2026-10", basic=1700.0, travel=300.0)
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert got["actual"] == 2000.0
    assert got["estimate"] == 0.0
    assert got["total"] == 2000.0
    assert got["actual_markings"] == 2
    assert got["estimate_markings"] == 0
    assert got["slips"] == 1


def test_the_slips_wages_overtime_and_travel_are_all_three_project_cost(world):
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-10", basic=800.0, ot=200.0, travel=120.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 1120.0
    assert AT.SLIP_COST_HEADS == ("basic", "ot", "travel")


def test_a_draft_slip_leaves_the_month_on_the_estimate(world):
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-10", status=PAY.DRAFT, basic=5000.0)
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert (got["estimate"], got["actual"], got["slips"]) == (800.0, 0.0, 0)


def test_a_cancelled_slip_puts_the_month_back_on_the_estimate(world):
    """Ruling 1's last line, and it falls out of one condition."""
    _mark("m1", "2026-10-01")
    s = _slip("s1", "2026-10", basic=5000.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 5000.0
    s["status"] = PAY.CANCELLED
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert (got["estimate"], got["actual"], got["slips"]) == (800.0, 0.0, 0)


def test_another_months_slip_does_not_touch_this_month(world):
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-09", basic=9999.0)
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert (got["estimate"], got["actual"]) == (800.0, 0.0)


def test_another_workers_slip_does_not_touch_this_worker(world):
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-10", basic=9999.0, eid="e2")
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert (got["estimate"], got["actual"]) == (800.0, 0.0)


def test_the_slip_status_strings_still_match_payrolls_own(world):
    """
    `attendance.py` reads the status as TEXT because importing `payroll.py`
    would be a cycle (it imports this module). The two must not drift.
    """
    assert AT.SLIP_ISSUED == PAY.ISSUED
    assert AT.SLIP_CANCELLED == PAY.CANCELLED


# =============================================================================
# 3. DEDUCTIONS ARE NOT PROJECT COST — ruling 1
# =============================================================================

def test_an_advance_never_reaches_a_project(world):
    """
    The same 2,000 of wages, once with a 1,500 advance recovered and once
    without. The project's labour is identical: an advance is the same money
    paid earlier.
    """
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-10-02")
    _slip("s1", "2026-10", basic=1600.0, travel=400.0, advance=1500.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 2000.0
    STORE["payslips"]["s1"]["snapshot"]["advance"] = 0.0
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 2000.0


def test_a_loan_recovery_never_reaches_a_project(world):
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-10", basic=800.0, loan=500.0,
          loan_opening=5000.0, loan_balance=4500.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 800.0


def test_the_statutory_heads_and_the_round_off_never_reach_a_project(world):
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-10", basic=800.0, pf=96.0, esic=18.0, pt=200.0,
          mlwf=12.0, round_off=0.4, payable=474.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 800.0


def test_other_allowance_typed_on_the_draft_is_not_project_cost(world):
    """
    ⚠ **A judgement call, declared.** `other_allowance` is typed on the draft
    and the slip does not say what it was for. Ruling 1 names three heads —
    *"wages + OT + travel"* — and a fourth read in silently would put a bonus
    or an ex-gratia on one project's margin. It is on the slip, it is paid, and
    it is not attributed here.
    """
    _mark("m1", "2026-10-01")
    _slip("s1", "2026-10", basic=800.0, other_allowance=5000.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 800.0


# =============================================================================
# 4. THE SPLIT — by days, across projects
# =============================================================================

def test_a_slip_splits_across_two_projects_by_days(world):
    """
    13 days on Jamnagar and 13 on Roadpali, one slip of 26,000: 13,000 each.
    """
    for d in range(1, 14):
        _mark(f"a{d}", f"2026-10-{d:02d}")
        _mark(f"b{d}", f"2026-10-{d + 13:02d}", pid=PID2, site_id=SITE2)
    _slip("s1", "2026-10", basic=26000.0)
    one = AT.labour_split_of(AT.markings_for_project(PID))
    two = AT.labour_split_of(AT.markings_for_project(PID2))
    assert one["actual"] == 13000.0
    assert two["actual"] == 13000.0
    assert round(one["actual"] + two["actual"], 2) == 26000.0


def test_a_half_day_takes_half_a_days_share_of_the_slip(world):
    """One full day and one half day: 2/3 and 1/3 of the slip, not half each."""
    _mark("m1", "2026-10-01", "present")
    _mark("m2", "2026-10-02", "half", pid=PID2, site_id=SITE2)
    _slip("s1", "2026-10", basic=900.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 600.0
    assert AT.labour_split_of(AT.markings_for_project(PID2))["actual"] == 300.0


def test_office_days_keep_their_share_off_the_project(world):
    """
    20 project days and 6 overhead days out of a 26,000 slip: the project
    carries 20,000 and the other 6,000 is on no project — never redistributed
    onto the one project that happens to have markings.
    """
    for d in range(1, 21):
        _mark(f"a{d}", f"2026-10-{d:02d}")
    for d in range(21, 27):
        _mark(f"o{d}", f"2026-10-{d:02d}", pid="",
              **AT.overhead_fields(True))
    _slip("s1", "2026-10", basic=26000.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 20000.0


def test_an_absent_day_takes_no_share_of_the_slip(world):
    _mark("m1", "2026-10-01", "present")
    _mark("m2", "2026-10-02", "absent")
    _slip("s1", "2026-10", basic=800.0)
    assert AT.labour_split_of(AT.markings_for_project(PID))["actual"] == 800.0


def test_a_slip_with_no_paid_day_anywhere_contributes_nothing(world):
    """
    ⚠ Declared: the denominator is zero, so there is no share to take. The
    money is on the slip and on no project. Dividing it equally, or falling
    back on the estimate, would put a figure nobody can trace on a margin.
    """
    _mark("m1", "2026-10-01", "absent")
    _slip("s1", "2026-10", basic=500.0)
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert (got["estimate"], got["actual"], got["total"]) == (0.0, 0.0, 0.0)
    assert got["slips"] == 1


def test_the_denominator_is_the_whole_month_and_not_the_rows_handed_in(world):
    """
    ⚠ **The regression this guards.** Were the denominator computed over the
    argument, each of two projects would take the WHOLE slip and the month
    would be billed twice. Measured here: the two shares sum to the slip.
    """
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-10-02", pid=PID2, site_id=SITE2)
    _slip("s1", "2026-10", basic=1000.0)
    one = AT.labour_split_of(AT.markings_for_project(PID))["actual"]
    two = AT.labour_split_of(AT.markings_for_project(PID2))["actual"]
    assert (one, two) == (500.0, 500.0)
    assert one + two == 1000.0


# =============================================================================
# 5. THE CLOSED PRE-DAY-RATE SET
# =============================================================================

def test_a_pre_day_rate_marking_is_refused_in_the_estimate(world):
    _mark("m1", "2026-10-01", rate=0.0, monthly_salary=20000.0,
          **{EMP.RATE_MODEL_FIELD: EMP.PRE_DAY_RATE})
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert (got["refused"], got["costed"], got["estimate"]) == (1, 0, 0.0)


def test_a_pre_day_rate_month_that_was_PAID_reaches_the_pnl_by_the_slip(world):
    """
    ⚠ **Declared.** `share_of()` reads the STATUS, not the rate, so a slip can
    be split across a worker on the closed historical set. The slip is the one
    figure about that month which is not twenty-six times wrong, so it is used
    and the marking is not refused.
    """
    _mark("m1", "2026-10-01", rate=0.0, monthly_salary=20000.0,
          **{EMP.RATE_MODEL_FIELD: EMP.PRE_DAY_RATE})
    _slip("s1", "2026-10", basic=769.0)
    got = AT.labour_split_of(AT.markings_for_project(PID))
    assert got["actual"] == 769.0
    assert (got["refused"], got["costed"]) == (0, 1)


# =============================================================================
# 6. THE P&L TAKES IT
# =============================================================================

def test_the_project_pnl_shows_the_split_and_totals_on_estimate_plus_actual(world):
    _mark("m1", "2026-10-01")                       # estimate 800
    _mark("m2", "2026-09-01")                       # paid month
    _slip("s1", "2026-09", basic=1200.0)
    lab = PNL.project_pnl(PID)["to_date"]["labour"]
    assert lab["estimate"] == 800.0
    assert lab["actual"] == 1200.0
    assert lab["total"] == 2000.0
    assert PNL.project_pnl(PID)["to_date"]["actual"] == 2000.0


def test_a_reader_without_attendance_view_still_gets_every_key(world):
    """
    The withheld dict carries the five new keys too, so a caller can read
    `labour["estimate"]` without asking whether it was withheld first.
    """
    lab = PNL.project_pnl(PID, include_labour=False)["to_date"]["labour"]
    assert lab["withheld"] is True
    for k in ("total", "estimate", "actual"):
        assert lab[k] is None
    for k in ("markings", "costed", "refused", "estimate_markings",
              "actual_markings", "slips"):
        assert lab[k] == 0
