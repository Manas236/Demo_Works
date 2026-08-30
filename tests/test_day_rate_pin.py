"""
The monthly-salary exception, pinned — CC-2 **C4** / **C5**.

The employee master used to hold a **monthly salary** and `attendance.py`
divided it by a divisor we invented. The owner corrected that on 30 August 2026:
Samruddhi pays **daily or weekly**, and CC-2 had always agreed — its own note
calls `salary ÷ 8 × hours` *"1× ordinary rate"*, which is true only if
`salary ÷ 8` is an **hourly** rate, so `salary` is a **day's** wage.

Existing records carry a figure entered under the old model. Converting it
arithmetically multiplies every wage by roughly twenty-six and we do not know
which records were entered as what. So the set is **counted at migration and
closed**, and:

1. every marked record keeps its figure and **no wage is computed from it**;
2. **nothing created after the migration may join the set**;
3. an employee leaves the set by having its rate re-entered — a marking never
   does, because it is history.

⚠ **(2) IS THE POINT OF THIS FILE.** Without it "pre-day-rate" stops being a
closed historical set and becomes a state any future record can fall into, which
is the same as not having the rule at all. `tests/test_measurement_pin.py` makes
the identical argument for the pre-measurement quantity and
`tests/test_approval_grandfather.py` for `created_by`; this is that argument
applied to the rate.

⚠ **Do not weaken any of these to make a red suite green.** If (2) fails, an
employee was created carrying a rate nobody can read, and a wage will be
computed from it or silently dropped from a site total.
"""

import ast
import pathlib

import pytest

import attendance as AT
import employee as EMP
import settings as S
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

DAY = "2026-08-29"


@pytest.fixture(autouse=True)
def _clean():
    """
    `conftest._fresh_store()` clears six collections and neither `employees`
    nor `attendance` is one of them, so this file cleans up after itself — a
    leaked row reads exactly like a seeder to `test_hardening.py`, which asserts
    that nothing seeds either.
    """
    for key in ("employees", "attendance"):
        STORE.setdefault(key, {}).clear()
    STORE.setdefault("settings", {}).pop(EMP.PIN_KEY, None)
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    yield
    for key in ("employees", "attendance"):
        STORE.setdefault(key, {}).clear()
    STORE.setdefault("settings", {}).pop(EMP.PIN_KEY, None)
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)


def _old_employee(eid="old-1", **over):
    """An employee as the register wrote them BEFORE 30 August 2026."""
    rec = {"id": eid, "name": "Ramesh Patil", "code": "SF-014",
           "designation": "Fitter", "site": "Whitefield",
           "date_joined": "2026-04-01", "monthly_salary": 26000.0,
           "active": True, "notes": "",
           "created_at": "2026-08-29 10:00", "updated_at": "2026-08-29 10:00"}
    rec.update(over)
    STORE["employees"][eid] = rec
    return rec


def _old_marking(rid="am-1", **over):
    """A marking as `mark_attendance` wrote them BEFORE 30 August 2026."""
    rec = {"id": rid, "date": DAY, "employee_id": "old-1",
           "employee_name": "Ramesh Patil", "employee_code": "SF-014",
           "monthly_salary": 26000.0, "site": "Whitefield",
           "status": "present", "ot_hours": 2.0, "notes": "",
           "created_at": "2026-08-29 10:05", "updated_at": "2026-08-29 10:05"}
    rec.update(over)
    STORE["attendance"][rid] = rec
    return rec


def _run_pin():
    """What `tools/backfill_day_rate.py --write` does, in-process."""
    emp_todo = sorted(rid for rid, r in STORE["employees"].items()
                      if EMP.needs_rate_pin(r))
    att_todo = sorted(rid for rid, r in STORE["attendance"].items()
                      if EMP.needs_rate_pin(r))
    for rid in emp_todo:
        STORE["employees"][rid][EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE
    for rid in att_todo:
        STORE["attendance"][rid][EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE
    STORE.setdefault("settings", {})[EMP.PIN_KEY] = {
        "at": "2026-08-30 12:00",
        "employees":  {"count": len(emp_todo), "ids": emp_todo,
                       "monthly_salary_was": {}},
        "attendance": {"count": len(att_todo), "ids": att_todo,
                       "monthly_salary_was": {}},
    }
    return emp_todo, att_todo


# ═══ 1. WHAT THE MIGRATION MARKS, AND WHAT IT LEAVES ALONE ═════════════════

def test_a_record_written_under_the_old_model_is_in_the_set():
    assert EMP.needs_rate_pin(_old_employee()), (
        "an employee carrying a monthly salary and no day rate is exactly the "
        "record the exception exists for, and the migration would skip it")
    assert EMP.needs_rate_pin(_old_marking())


def test_a_record_carrying_a_day_rate_is_not_in_the_set():
    assert not EMP.needs_rate_pin(
        _old_employee(eid="new-1", day_rate=1000.0))


def test_a_marked_record_is_not_marked_twice():
    """Idempotence: a second run of the migration must change nothing."""
    e = _old_employee()
    e[EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE
    assert not EMP.needs_rate_pin(e)


def test_the_mark_is_never_inferred_from_a_missing_day_rate():
    """
    ⚠ **The half that keeps the set closed.** `is_pre_day_rate()` reads the
    explicit field and nothing else. Inferring it from "this record has no
    `day_rate`" — or from "it has a `monthly_salary` key" — is exactly how a
    record written next year through a route with a bug in it would quietly
    join a set that was closed in August.
    `measurement.is_pre_measurement()` makes the same argument one register
    along, and `approval.is_grandfathered()` makes it a third time.
    """
    e = _old_employee()
    assert EMP.needs_rate_pin(e), "the fixture is not in the state under test"
    assert not EMP.is_pre_day_rate(e), (
        "an unmarked record reads as grandfathered — the exception is inferred "
        "rather than recorded, and it will grow")

    e[EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE
    assert EMP.is_pre_day_rate(e)


def test_the_migration_record_is_absent_until_the_migration_runs():
    assert EMP.migration_record() == {}, (
        "a fresh database claims a day-rate migration has run, so every record "
        "written from now on would be measured against a moment that never "
        "happened")


# ═══ 2. THE PIN — nothing created after the migration joins the set ════════

def test_no_employee_created_after_the_migration_carries_the_marker():
    """
    ⚠ **THE TEST THE WHOLE EXCEPTION EXISTS FOR, and the one the brief for this
    pass names in as many words: the exception must never grow.**

    It sweeps the real store. On a fresh database the sweep is empty, which is
    the honest answer — and `test_the_sweep_can_actually_see_a_violation` below
    proves the sweep can see one, so an empty pass is not a vacuous one.
    """
    _old_employee()
    emp_ids, _ = _run_pin()
    assert emp_ids == ["old-1"]

    at = EMP.migration_record()["at"]
    offenders = [rid for rid, e in STORE["employees"].items()
                 if str(e.get("created_at") or "") > at
                 and EMP.is_pre_day_rate(e)]
    assert not offenders, (
        f"these employees were created AFTER the pin and carry the old-model "
        f"marker: {offenders}. The exception has grown, which is the same as "
        f"not having the rule.")


def test_the_sweep_can_actually_see_a_violation():
    """
    ⚠ **The vacuity check on the test above.** A sweep that passes because it
    found nothing to look at proves nothing. This plants exactly the record that
    must be caught and asserts the same walk catches it.
    """
    _old_employee()
    _run_pin()
    at = EMP.migration_record()["at"]

    planted = _old_employee(eid="new-1", created_at="2999-01-01 00:00")
    planted[EMP.RATE_MODEL_FIELD] = EMP.PRE_DAY_RATE

    offenders = [rid for rid, e in STORE["employees"].items()
                 if str(e.get("created_at") or "") > at
                 and EMP.is_pre_day_rate(e)]
    assert offenders == ["new-1"], (
        "the sweep in the test above cannot see an employee created after the "
        "pin that carries the marker, so its passing means nothing")


def test_the_create_route_cannot_produce_a_marked_record(client):
    """
    The pin above is a sweep; this is the mechanism that makes it true. The
    real route writes no `rate_model` key at all, so an employee added through
    the UI can never be in the closed set.
    """
    r = client.post("/employee/new", data={
        "name": "Fresh Hire", "code": "SF-900", "day_rate": "900",
        "active": "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]

    e = list(STORE["employees"].values())[-1]
    assert EMP.RATE_MODEL_FIELD not in e, (
        "the create route stamps the old-model marker on a brand-new record")
    assert e["day_rate"] == 900.0
    assert "monthly_salary" not in e, (
        "the create route still writes a monthly salary key")
    assert EMP.day_rate_of(e) == (900.0, True)


def test_the_pinned_moment_is_never_moved():
    """
    Re-running the migration after a month must not re-open the exception for
    everything written in between. The tool writes the record once.
    """
    _old_employee()
    _run_pin()
    first = EMP.migration_record()["at"]

    src = (REPO / "tools" / "backfill_day_rate.py").read_text(encoding="utf8")
    assert "if not already:" in src, (
        "the migration tool no longer guards the pinned moment — re-running it "
        "would move the moment and re-open the exception for every record "
        "written since")
    assert EMP.migration_record()["at"] == first


def test_the_recorded_counts_are_the_sets_that_were_marked():
    _old_employee()
    _old_employee(eid="old-2", code="SF-015")
    _old_employee(eid="fine-1", code="SF-016", day_rate=1000.0)
    _old_marking()
    emp_ids, att_ids = _run_pin()

    rec = EMP.migration_record()
    assert rec["employees"]["count"] == 2 == len(emp_ids)
    assert sorted(rec["employees"]["ids"]) == ["old-1", "old-2"]
    assert rec["attendance"]["count"] == 1 == len(att_ids)
    assert all(EMP.is_pre_day_rate(STORE["employees"][r])
               for r in rec["employees"]["ids"])
    assert not EMP.is_pre_day_rate(STORE["employees"]["fine-1"])


# ═══ 3. A MARKED RECORD KEEPS ITS FIGURE AND PRODUCES NO WAGE ══════════════

def test_a_marked_record_keeps_its_stored_figure_untouched():
    """
    ⚠ **Nothing is converted.** The migration marks; it does not divide,
    multiply, rename or delete. A snapshot on a marking is the record of what
    that day was assessed at, and recomputing it is the thing every freeze
    contract in this app exists to prevent.
    """
    e = _old_employee()
    m = _old_marking()
    _run_pin()

    assert e["monthly_salary"] == 26000.0
    assert m["monthly_salary"] == 26000.0
    assert m["ot_hours"] == 2.0
    assert "day_rate" not in e and "day_rate" not in m


def test_the_wage_calculation_refuses_rather_than_producing_a_figure():
    """
    ⚠ **The refusal is the deliverable, not the marker.** A marked record must
    produce **no number at all** — not zero, which is a figure somebody could
    have chosen, and emphatically not the monthly salary read as a day's pay,
    which is what the owner's own screenshot was showing.
    """
    m = _old_marking()
    _run_pin()

    assert EMP.day_rate_of(STORE["employees"].get("old-1") or m) == (None, False)

    c = AT.cost_of(m, S.ot_multiplier())
    assert c["refused"] is True
    assert c["day"] is None and c["ot"] is None and c["total"] is None, (
        "a refused marking returned a number — zero is a figure, and a site "
        "total would silently absorb it")
    assert c["reason"]


def test_an_unmarked_marking_still_costs_normally():
    """
    The other half. A guard that refuses everything is not a guard, and this is
    the control that proves the refusal above is selective.
    """
    m = _old_marking(rid="new-1", day_rate=1000.0)
    m.pop("monthly_salary")
    c = AT.cost_of(m, S.ot_multiplier())
    assert c["refused"] is False
    # day rate 1000, 8-hour day => 125/hour, 2 hours at the client's 1x = 250.
    assert c == {"day": 1000.0, "ot": 250.0, "total": 1250.0,
                 "refused": False, "reason": ""}


def test_a_refused_marking_is_left_out_of_the_site_total_and_is_counted():
    """
    ⚠ **Excluded from the money and INCLUDED in the head count.** Dropping the
    person from `people` would hide that they were on site; folding the old
    monthly figure into `day_cost` would overstate the site by about
    twenty-six. Both halves, so the page can say the total is short and by how
    many.
    """
    _old_marking(rid="stale-1", site="Whitefield")
    good = _old_marking(rid="ok-1", site="Whitefield", employee_id="e2",
                        employee_name="Second Person", day_rate=1000.0)
    good.pop("monthly_salary")
    _run_pin()

    sites = AT.site_costs(DAY)
    assert len(sites) == 1
    s = sites[0]
    assert s["people"] == 2, "a refused marking vanished from the head count"
    assert s["refused"] == 1
    assert s["total"] == 1250.0, (
        "the site total absorbed a marking whose rate is unconfirmed")


# ═══ 4. AN EMPLOYEE LEAVES THE SET BY RE-ENTRY; A MARKING NEVER DOES ═══════

def test_re_entering_the_rate_clears_the_marker_and_drops_the_old_figure(client):
    """
    ⚠ **The way out of the set, and the only way.** Typing a day rate is a
    deliberate act by somebody who knows what the person is paid. It clears the
    marker and takes the superseded monthly figure with it — two rate fields on
    one record with nothing saying which is live is how the next reader picks
    the wrong one.
    """
    e = _old_employee()
    _run_pin()
    assert EMP.is_pre_day_rate(e)

    r = client.post(f"/employee/edit/old-1", data={
        "name": "Ramesh Patil", "code": "SF-014", "designation": "Fitter",
        "site": "Whitefield", "date_joined": "2026-04-01",
        "day_rate": "1000", "active": "1", "notes": ""})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]

    e = STORE["employees"]["old-1"]
    assert not EMP.is_pre_day_rate(e)
    assert EMP.RATE_MODEL_FIELD not in e
    assert e["day_rate"] == 1000.0
    assert "monthly_salary" not in e, (
        "the superseded monthly figure is still on the record beside the day "
        "rate, with nothing saying which one is live")


def test_saving_a_marked_record_with_a_BLANK_rate_is_refused(client):
    """
    ⚠ **The trap this closes.** On every other record a blank rate means
    "nothing recorded" and reads as zero, which is C4's rule and stays. On a
    marked record a blank would clear the marker while recording nothing — so
    the one record whose entire problem is an unconfirmed rate would come out
    confirmed at zero because somebody pressed Save.
    """
    e = _old_employee()
    _run_pin()

    r = client.post(f"/employee/edit/old-1", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "", "active": "1"})
    assert r.status_code == 200, "a blank rate on a marked record was accepted"
    assert EMP.is_pre_day_rate(STORE["employees"]["old-1"]), (
        "the marker was cleared by a save that recorded no rate")
    assert STORE["employees"]["old-1"]["monthly_salary"] == 26000.0


def test_a_blank_rate_is_still_accepted_on_an_ORDINARY_record(client):
    """
    The control on the test above. C4 permits a zero rate — a proprietor or a
    family member drawing nothing is real — and that rule is untouched.
    """
    r = client.post("/employee/new", data={
        "name": "Unpaid Family", "code": "SF-901", "day_rate": "", "active": "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    assert list(STORE["employees"].values())[-1]["day_rate"] == 0.0


def test_marking_a_day_for_an_unconfirmed_employee_is_REFUSED(client):
    """
    ⚠ **Refused at the WRITE, which is what keeps the closed set closed.** A
    marking snapshots the rate, so recording one against an unconfirmed employee
    would mint a brand-new record that is already old-model — the exact growth
    the pin above exists to catch, arriving through the front door.
    """
    _old_employee()
    _run_pin()

    r = client.post("/attendance/mark", data={
        "date": DAY, "employee_id": "old-1", "site": "Whitefield",
        "status": "present", "ot_hours": "2", "notes": ""})
    assert r.status_code == 200, "the marking was accepted"
    assert not STORE["attendance"], "a marking was written for an unconfirmed rate"
    assert "day rate" in r.get_data(as_text=True).lower()


# ═══ 5. THE DIVISOR IS GONE AND MAY NOT COME BACK ══════════════════════════

def test_the_wage_divisor_setting_is_gone():
    """
    ⚠ **Retired, not re-tuned.** `wage_days_per_month` divided a monthly salary
    into a daily wage. There is no monthly salary any more, so there is nothing
    to divide — and a divisor reappearing would mean somebody had gone back to
    storing a monthly figure.
    """
    assert "wage_days_per_month" not in S.LABOUR_DEFAULTS
    assert not hasattr(S, "wage_days_per_month"), (
        "the accessor is back — see the header of this test")
    assert "wage_days_per_month" not in S.labour_settings()
    assert not hasattr(AT, "daily_wage"), (
        "attendance.daily_wage() divided a monthly figure by the divisor and "
        "has no meaning on a day rate")

    # ⚠ **And it is not WRITTEN BACK either, which the four assertions above
    #   cannot see.** A mutation that made `save_labour_settings()` store the
    #   key again walked straight through them: the accessor was still gone,
    #   `LABOUR_DEFAULTS` was still clean, and `labour_settings()` still could
    #   not read it — so nothing reached a calculation, and the guard stayed
    #   green while `tools/backfill_day_rate.py`'s whole cleanup was undone on
    #   the next visit to `/settings`. A dead key in a live settings row is a
    #   trap for the next reader, and this one in particular reads as a live
    #   divisor.
    S.save_labour_settings("2")
    stored = STORE.get("settings", {}).get(S.LABOUR_RECORD) or {}
    assert "wage_days_per_month" not in stored, (
        "saving /settings writes the retired divisor back into the labour "
        "record")
    assert set(stored) <= set(S.LABOUR_DEFAULTS), (
        f"the labour settings row grew keys the app does not know: "
        f"{sorted(set(stored) - set(S.LABOUR_DEFAULTS))}")


def test_no_calculation_path_reads_a_divisor():
    """
    Source-level, because the behavioural test above passes on a module that
    still carries the name in a dead branch. `_ident_names()` walks the AST
    rather than grepping, so a mention in a docstring or a comment — of which
    there are several, deliberately, explaining why it went — does not fail it.
    """
    for name in ("attendance.py", "settings.py", "employee.py"):
        tree = ast.parse((REPO / name).read_text(encoding="utf8"))
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        used |= {n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)}
        assert "wage_days_per_month" not in used, (
            f"{name} still reads or defines the wage divisor")
        assert "daily_wage" not in used, f"{name} still uses daily_wage()"


def test_the_settings_page_no_longer_offers_the_divisor(client):
    html = client.get("/settings/").get_data(as_text=True)
    assert 'name="wage_days_per_month"' not in html, (
        "the divisor is still a field somebody can set")
    assert 'name="ot_multiplier"' in html, (
        "the OT multiplier went with it — that one is CC-2's own and "
        "hardcoding it computes a statutory underpayment")


def test_a_stale_stored_divisor_cannot_reach_any_calculation():
    """
    ⚠ **The live database carries `{"wage_days_per_month": "1"}`** — which is
    why the owner's screenshot read *"1 working days a month"* and made a day's
    wage the whole monthly salary. `labour_settings()` reads off
    `LABOUR_DEFAULTS`, so a key the app no longer knows is invisible to it.
    """
    STORE.setdefault("settings", {})[S.LABOUR_RECORD] = {
        "wage_days_per_month": "1", "ot_multiplier": "2"}
    assert S.labour_settings() == {"ot_multiplier": "2"}
    assert S.ot_multiplier() == 2.0
