"""
LABOUR LANDS ON THE PROJECT BY ITSELF — §0 **fifty-eighth** block, item 2.

The client's ask from the 28 October 2026 Yogesh meeting: the project page
should say what the labour on this job cost, **per worker** and in total, and
should not quietly leave out the markings nobody attributed.

Three things are built and each has its own section below:

1. **Per worker.** `attendance.worker_costs()` computes it, day rate and
   overtime, and `projectview._worker_rollup()` renders it. ⚠ The rollup and
   the per-marking table beneath it are **the same money grouped two ways**
   and the two totals must agree — two tables that disagreed would be two wage
   formulas, and §0's fifty-fifth block allows exactly one.
2. **Nothing silently dropped.** `attendance.off_project_labour()` counts the
   markings on no live project at all and says why — a site with no project, a
   site string nothing in the book matched, a marking that predates the day
   rate. It is drawn on an **amber** line and is **never added** to anything
   on the page.
3. **An advance is not a cost.** `payroll.advances_outstanding_for()` is an
   **information** line. Manas's call, recorded in the block: the cost is the
   wage earned; the advance is cash paid ahead of it, and subtracting both
   counts the same rupee twice.

⚠ **The two-group structure is untouched.** *Booked to this project* and *At
  this site, unattributed* are still summed separately and still never added
  together; `tests/test_project.py` and `projectview.py`'s own docstring own
  that rule. This pass adds a rollup **inside** each group.
"""

import pytest

import attendance as AT
import employee as EMP
import payroll as PAY
import projectview as PV
from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

SITE = "addr-site-1"
PID = "p-lab"


# ⚠ **These six are NOT in `conftest._fresh_store()`**, so a fixture that
#   plants them has to put them back itself — the muster, the employee master,
#   the projects, the book, the wage ledger and the slips all leak between
#   tests otherwise, and a leaked advance or marking makes an assertion about
#   "none" pass for the wrong reason. Measured: without this the "absent when
#   there are none" tests in this file passed only when run alone.
#
# ⚠ **SNAPSHOT AND RESTORE, never clear-on-teardown.** `addresses` is
#   DEMO-SEEDED once per process (`SAMRUDDHI_DEMO_DATA`, §0 thirty-first
#   block) and `_fresh_store()` deliberately leaves it alone. Clearing it in
#   teardown deleted the seeded book for every later test in the session —
#   measured: 6 failures and 1 error across `test_ssti_group1.py`,
#   `test_work_orders.py` and `test_ra_from_source.py`, none of which this
#   pass touches. `test_page_golden.py::world` restores `users` the same way
#   and for the same reason.
_OWNED = ("attendance", "employees", "projects", "addresses",
          "pay_entries", "payslips")


@pytest.fixture()
def world(client):
    """One project with a linked site, and two workers marked on it."""
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["addresses"][SITE] = {
        "id": SITE, "label": "Jamnagar Refinery", "type": "site",
        "archived": False,
    }
    STORE["projects"][PID] = {
        "id": PID, "name": "Jamnagar", "norm_name": "jamnagar",
        "client": "IOCL", "notes": "",
        "site_address_id": SITE, "site_address": "Jamnagar Refinery",
        "created_at": "2026-10-01 09:00", "updated_at": "2026-10-01 09:00",
    }
    for eid, name, code in (("e1", "Ramesh Patil", "W-01"),
                            ("e2", "Suresh Jadhav", "W-02")):
        STORE["employees"][eid] = {
            "id": eid, "name": name, "code": code, "designation": "Fitter",
            "day_rate": 800.0, "active": True,
            "site": "Jamnagar Refinery", EMP.SITE_ADDRESS_FIELD: SITE,
            EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
        }
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def _mark(mid, eid, name, date, status="present", ot=0.0, pid=PID,
          site_id=SITE, **over):
    rec = {
        "id": mid, "employee_id": eid, "employee_name": name,
        "employee_code": "W-01" if eid == "e1" else "W-02",
        "date": date, "status": status, "ot_hours": ot,
        "day_rate": 800.0, "site": "Jamnagar Refinery",
        EMP.SITE_ADDRESS_FIELD: site_id, EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
        "project_id": pid, "project_name": "Jamnagar",
    }
    rec.update(over)
    STORE["attendance"][mid] = rec
    return rec


def _page(client, pid=PID):
    r = client.get(f"/projects/view/{pid}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _labour(html: str) -> str:
    """Just the Site Labour panel, so a match cannot come from another one."""
    assert "<h2>Site Labour</h2>" in html, "no Site Labour panel on the page"
    return html.split("<h2>Site Labour</h2>", 1)[1]


# =============================================================================
# 1. PER WORKER — and the same money as the rows below it
# =============================================================================

def test_the_panel_shows_a_row_per_worker_with_day_rate_and_overtime(world):
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01", ot=2)
    _mark("m2", "e1", "Ramesh Patil", "2026-10-02")
    _mark("m3", "e2", "Suresh Jadhav", "2026-10-01")
    seg = _labour(_page(world))
    assert "What each worker on this project cost" in seg
    assert "Ramesh Patil" in seg and "Suresh Jadhav" in seg
    assert "2 workers" in seg
    # Ramesh: 2 days x 800 = 1,600 day + 2h OT at 800/8 x 1 = 200 -> 1,800
    assert "1,800.00" in seg, "Ramesh's own total is not on the page"
    assert "Every marking, day by day" in seg, (
        "the per-marking table lost its heading, so the rollup reads as the "
        "whole panel")


def test_THE_ROLLUP_AND_THE_MARKINGS_ARE_THE_SAME_MONEY(world):
    """
    THE ASSERTION THAT MATTERS MOST. Both tables are `cost_of()` over the same
    rows, so their totals are equal **by construction** — and if they ever are
    not, there are two wage formulas in this application and §0's fifty-fifth
    block allows one.
    """
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01", ot=2)
    _mark("m2", "e2", "Suresh Jadhav", "2026-10-01", status="half")
    rows = AT.markings_for_project(PID)
    per_worker = round(sum(b["total"] for b in AT.worker_costs(rows)), 2)
    per_marking = AT.labour_cost_of(rows)["total"]
    assert per_worker == per_marking == 1400.0, (
        f"rollup {per_worker} vs markings {per_marking} — these must be the "
        f"same number computed one way")


def test_a_half_day_and_paid_leave_follow_DAY_SHARE_in_the_rollup(world):
    """The two statuses from §0's fifty-fifth block, not re-implemented here."""
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01", status="half")
    _mark("m2", "e1", "Ramesh Patil", "2026-10-02", status="paid_leave")
    _mark("m3", "e1", "Ramesh Patil", "2026-10-03", status="absent")
    b = AT.worker_costs(AT.markings_for_project(PID))[0]
    assert b["days_present"] == 1.5, "0.5 + 1.0 + 0.0 paid days"
    assert b["days_marked"] == 3
    assert b["total"] == 1200.0, "400 (half) + 800 (paid leave) + 0 (absent)"


def test_a_refused_marking_is_counted_per_worker_and_not_costed(world):
    """
    `labour_cost_of()`'s and `site_costs()`'s rule, held per worker too: a
    record on the old monthly model contributes nothing and is reported. A
    monthly figure read as a day rate is about twenty-six times too large.
    """
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    _mark("m2", "e1", "Ramesh Patil", "2026-10-02",
          monthly_salary=21000.0, rate_model="pre_day_rate", day_rate=None)
    b = AT.worker_costs(AT.markings_for_project(PID))[0]
    assert b["refused"] == 1
    assert b["days_marked"] == 2
    assert b["total"] == 800.0, "the refused day added nothing"
    seg = _labour(_page(world))
    assert "1 not costed" in seg, "the shortfall is not stated per worker"


def test_the_rollup_is_withheld_without_attendance_view(world, monkeypatch):
    """
    B4's wall is the panel's, and the rollup is inside it. A reader who may not
    see wages gets the withheld message and not one figure.
    """
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "attendance.view" else real(p))
    seg = _labour(_page(world))
    assert "View attendance</b> permission" in seg
    assert "What each worker on this project cost" not in seg
    assert "Ramesh Patil" not in seg


def test_the_rollup_stylesheet_never_reaches_a_reader_without_wages(world, monkeypatch):
    """
    `PNL_CSS`'s arrangement, and here it is what keeps
    `tests/test_pnl_access.py`'s byte-for-byte pin green: the sheet travels
    INSIDE the panel, so a reader without `attendance.view` receives none of it.
    """
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    assert ".sl-roll-head {" in PV.ROLLUP_CSS
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "attendance.view" else real(p))
    assert ".sl-roll-head {" not in _page(world)


# =============================================================================
# 2. NOTHING SILENTLY DROPPED — the amber line
# =============================================================================

def test_a_marking_on_no_project_is_counted_and_named(world):
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    _mark("m9", "e2", "Suresh Jadhav", "2026-10-01", pid="", site_id="addr-other")
    STORE["addresses"]["addr-other"] = {
        "id": "addr-other", "label": "Loose Yard", "type": "site",
        "archived": False}
    seg = _labour(_page(world))
    assert "booked to no project at all" in seg
    # ⚠ The amount is pinned INSIDE the sentence, not merely "somewhere on the
    #   page": 800.00 is also this project's own labour cost, so a loose
    #   `in seg` passed even when `off_project_labour()` reported nil. Measured
    #   — that mutation survived until this assertion was written this way.
    assert "booked to no project at all</b>, costing 800.00." in seg, (
        "the amber line does not carry the off-project amount")
    assert "This figure is not added to anything on this page" in seg, (
        "the line must say it is not part of the page's arithmetic")


def test_a_site_with_no_project_is_named_as_the_reason(world):
    """
    `payimport.py` maps SITE -> address -> project. Where the address carries
    no project there is nothing to map to, and tagging the muster cannot fix
    it — so the line says so rather than telling somebody to go and tag.
    """
    STORE["addresses"]["addr-other"] = {
        "id": "addr-other", "label": "Loose Yard", "type": "site",
        "archived": False}
    _mark("m9", "e2", "Suresh Jadhav", "2026-10-01", pid="", site_id="addr-other")
    off = AT.off_project_labour()
    assert off["markings"] == 1 and off["no_project_site"] == 1
    assert "carries no project" in _labour(_page(world))


def test_an_unmapped_site_string_is_named_and_never_guessed(world):
    _mark("m9", "e2", "Suresh Jadhav", "2026-10-01", pid="", site_id="",
          site="Banglore", **{EMP.SITE_SOURCE_FIELD: EMP.SITE_UNMAPPED})
    off = AT.off_project_labour()
    assert off["unmapped_site"] == 1
    assert off["sites"] == ["Banglore"]
    seg = _labour(_page(world))
    assert "nothing in the address book matched" in seg
    assert "Banglore" in seg
    assert "Nothing has been guessed at" in seg


def test_a_marking_naming_a_DELETED_project_is_on_no_project(world):
    """`markings_on_no_project()`'s rule, read from this side: a dangling
    `project_id` is on no project's page either."""
    _mark("m9", "e2", "Suresh Jadhav", "2026-10-01", pid="p-gone")
    assert AT.off_project_labour()["markings"] == 1


def test_the_line_is_absent_when_every_marking_is_on_a_project(world):
    """A page that goes on warning about a resolved problem teaches its reader
    to ignore the warning — `_labour_note()`'s own rule."""
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    seg = _labour(_page(world))
    assert "booked to no project at all" not in seg


def test_the_line_is_drawn_even_when_this_project_has_no_markings(world):
    """
    The empty state says *"Nobody has been recorded as working here"*, which is
    the strongest possible invitation to read the wage bill as nil. It is
    exactly the state in which off-project markings matter most.
    """
    _mark("m9", "e2", "Suresh Jadhav", "2026-10-01", pid="", site_id="")
    seg = _labour(_page(world))
    assert "Nobody has been recorded as working here" in seg
    assert "booked to no project at all" in seg


def test_the_counts_overlap_and_are_never_summed(world):
    """One marking can be both reasons at once; the two counts describe it
    twice and a sum of them would describe nothing."""
    _mark("m9", "e2", "Suresh Jadhav", "2026-10-01", pid="", site_id="",
          site="Banglore", **{EMP.SITE_SOURCE_FIELD: EMP.SITE_UNMAPPED})
    off = AT.off_project_labour()
    assert off["markings"] == 1
    assert off["no_project_site"] == 1 and off["unmapped_site"] == 1


# =============================================================================
# 3. AN ADVANCE IS NOT A COST
# =============================================================================

def _advance(aid, eid, amount, date="2026-10-05"):
    STORE["pay_entries"][aid] = {
        "id": aid, "employee_id": eid, "employee_name": "Ramesh Patil",
        "date": date, "type": PAY.ADVANCE, "amount": amount, "note": "",
        "source": PAY.SOURCE_MANUAL, "created_at": "2026-10-05 10:00",
        "created_by": "test", "updated_at": "2026-10-05 10:00",
    }


def test_an_advance_shows_as_information_and_is_not_subtracted(world):
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    _advance("a1", "e1", 500.0)
    seg = _labour(_page(world))
    assert "Advances outstanding: 500.00" in seg
    assert "An advance is cash paid ahead of the wages, not a cost of its own" in seg
    assert "not</b> subtracted anywhere" in seg
    # …and the labour figure itself is untouched by it.
    assert AT.labour_cost_of(AT.markings_for_project(PID))["total"] == 800.0


def test_PNL_DOES_NOT_SUBTRACT_AN_ADVANCE(world):
    """
    THE ASSERTION THAT MATTERS MOST for this section. The P&L's labour cost is
    wages EARNED and an advance changes it by nothing. Getting this the other
    way round overstates the cost of every project that pays in advance.
    """
    import pnl as PNL
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    before = PNL.project_pnl(PID)["to_date"]["labour"]["total"]
    _advance("a1", "e1", 5000.0)
    after = PNL.project_pnl(PID)["to_date"]["labour"]["total"]
    assert before == after == 800.0, (
        f"an advance moved the P&L's labour cost from {before} to {after}")


def test_an_advance_settled_by_an_ISSUED_slip_is_no_longer_outstanding(world):
    _advance("a1", "e1", 500.0)
    STORE["payslips"]["s1"] = {
        "id": "s1", "employee_id": "e1", "month": "2026-10",
        "status": PAY.ISSUED, "snapshot": {"entry_ids": ["a1"]},
    }
    assert PAY.advances_outstanding_for(["e1"]) == {
        "total": 0.0, "entries": 0, "people": 0}


def test_a_DRAFT_slip_settles_nothing(world):
    """A draft can still be refreshed or cancelled, so it has set nothing
    against anything — `live_slip()`'s own distinction from this side."""
    _advance("a1", "e1", 500.0)
    STORE["payslips"]["s1"] = {
        "id": "s1", "employee_id": "e1", "month": "2026-10",
        "status": PAY.DRAFT, "snapshot": {"entry_ids": ["a1"]},
    }
    assert PAY.advances_outstanding_for(["e1"])["total"] == 500.0


def test_a_CANCELLED_slip_settles_nothing(world):
    _advance("a1", "e1", 500.0)
    STORE["payslips"]["s1"] = {
        "id": "s1", "employee_id": "e1", "month": "2026-10",
        "status": PAY.CANCELLED, "snapshot": {"entry_ids": ["a1"]},
    }
    assert PAY.advances_outstanding_for(["e1"])["total"] == 500.0


def test_only_the_workers_on_this_project_are_counted(world):
    """A blank id list matches nobody, which is `markings_for_project()`'s
    guard in another register: `""` matching `""` would hand over the lot."""
    _advance("a1", "e1", 500.0)
    _advance("a2", "e2", 900.0)
    assert PAY.advances_outstanding_for(["e1"])["total"] == 500.0
    assert PAY.advances_outstanding_for([])["total"] == 0.0
    assert PAY.advances_outstanding_for(["", None])["total"] == 0.0


def test_a_travel_or_loan_entry_is_not_an_advance(world):
    """Only `ADVANCE`. A travel allowance is pay and a loan has its own
    derived balance (`loan_balance()`)."""
    STORE["pay_entries"]["t1"] = {
        "id": "t1", "employee_id": "e1", "date": "2026-10-05",
        "type": PAY.TRAVEL, "amount": 300.0}
    STORE["pay_entries"]["l1"] = {
        "id": "l1", "employee_id": "e1", "date": "2026-10-05",
        "type": PAY.LOAN_GIVEN, "amount": 4000.0}
    assert PAY.advances_outstanding_for(["e1"])["entries"] == 0


def test_the_advances_line_is_absent_when_there_are_none(world):
    _mark("m1", "e1", "Ramesh Patil", "2026-10-01")
    assert "Advances outstanding" not in _labour(_page(world))
