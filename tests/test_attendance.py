"""
Attendance and site-wise labour cost — CLIENT_CHANGES-2.md **C5**.

Built under the **third 29 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md`
§0, which gated it until then. CC-2's C5 is five bullets: daily presentee /
absentee, salary as 0 or 1 on attendance, **one employee = one site = one day**,
`OT = (salary ÷ 8) × hours`, and a presentation table of Employee — Site — OT.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **THE OT MULTIPLIER IS A SETTING, AND NO LITERAL MULTIPLIER EXISTS IN THE
   CALCULATION PATH.** CC-2 is explicit and the reason is statutory: the
   client's figure is 1× ordinary rate, the Factories Act and most state Shops
   & Establishments Acts put overtime at generally **twice**, and a hardcoded 1
   would make this software compute an **underpayment**. Asserted two ways — a
   behavioural test that changing the setting changes the money, and an **AST
   walk** that fails on a numeric constant in a multiplication inside
   `daily_wage`, `ot_amount` or `cost_of`. The second is the one that survives
   somebody "simplifying" the first.

2. ⚠ **One employee = one site = one day, enforced at WRITE TIME.** Not in the
   form, not by a dropdown that omits a name — in `conflicting_record()`, which
   both write routes call before storing anything. A second marking for one
   person on one day would bill that day's wage twice.

3. **An inactive employee cannot be marked**, checked on the record rather than
   on the picker: the dropdown lists active people only, but a posted id can
   name anybody.

4. **Delete confirms on GET and destroys only on POST** — `9d060ee`'s shape and
   ABOUT.md §7.9f's standing rule, which says in terms that the `url_map` sweep
   cannot catch a both-verbs route destroying on GET, so a new one ships its
   own test. This is that test.

5. **Every new endpoint is classified**, and **Sales, Purchase and Accountant
   are refused on every route by direct URL hit** while HR is admitted.
   ⚠ **Operation Head is refused too, and that one is OURS** — a reversible
   default, not a specification.

6. ⚠ **C5 IS NOT WIRED INTO C6 OR ANY P&L.** C6 is BLOCKED on CC-2's Open
   question 4 — whether attendance wages or the BOQ installation base rate is
   authoritative for labour cost — and subtracting both counts labour twice.
   Asserted structurally: nothing imports this module, and the labour cost
   appears on no other page.
"""

import ast
import pathlib
import re

import pytest

import attendance as AT
import auth
import settings as S
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

ATTENDANCE_ROUTES = [
    "/attendance/",
    "/attendance/mark",
    "/attendance/edit/{id}",
    "/attendance/delete/{id}",
]

# B4's wall, from the far side.
WALLED_OFF = ("sales-manager", "purchase-manager", "accountant")

DAY = "2026-08-29"


@pytest.fixture(autouse=True)
def _clean():
    """
    `conftest._fresh_store()` clears six collections and neither `employees`
    nor `attendance` is one of them, so this file cleans up after itself. A
    leaked row reads exactly like a seeder to `test_hardening.py`, which
    asserts that nothing seeds either.
    """
    STORE.setdefault("employees", {}).clear()
    STORE.setdefault("attendance", {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    yield
    STORE.setdefault("employees", {}).clear()
    STORE.setdefault("attendance", {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)


def _person(client, **over):
    """Somebody on the register, added through the real employee route."""
    # ⚠ `day_rate` since 30 August 2026. It was
    #   `"monthly_salary": "26000"` and a divisor of 26 turned that into a
    #   day's ₹1,000; the day rate IS ₹1,000, so every figure this file asserts
    #   is unchanged and only the route it arrives by has moved.
    data = {
        "name": "Ramesh Patil", "code": "SF-014", "designation": "Fitter",
        "site": "Whitefield", "date_joined": "2026-04-01",
        "day_rate": "1000", "notes": "", "active": "1",
    }
    data.update(over)
    if data.get("active") is None:
        data.pop("active")
    r = client.post("/employee/new", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    return list(STORE["employees"].values())[-1]


def _mark(client, person, **over):
    """Mark a day through the real route. Returns the response."""
    data = {"date": DAY, "employee_id": person["id"], "site": "Whitefield",
            "status": "present", "ot_hours": "2", "notes": ""}
    data.update(over)
    return client.post("/attendance/mark", data=data)


def _user_with(slug: str) -> dict:
    auth.ensure_builtin_roles()
    name = f"att-test-{slug}"
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="attendance-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


# ══ 1. ⚠ The OT multiplier is a SETTING ═══════════════════════════════════

def test_no_literal_multiplier_exists_in_the_calculation_path():
    """
    ⚠ **THE TEST CC-2 ASKS FOR, AND THE ONE THAT SURVIVES A REFACTOR.**

    Walk the AST of the three functions that compute money and fail on any
    numeric constant appearing in a multiplication or a division. The OT
    multiplier and the wage divisor must both arrive as arguments, from
    `/settings`; writing either into this file is how the software would
    quietly compute a **statutory underpayment**.

    ⚠ `STANDARD_HOURS_PER_DAY` is the deliberate exception and is a NAME, not a
    literal — which is exactly why this test can be written this strictly. It
    is CC-2's own `÷ 8`: a divisor defining what an hour of a working day is,
    not a rate anybody is paid at.

    ⚠ **RETARGETED 30 August 2026, not weakened — and this test told the last
    pass to do exactly that** ("this test names functions that no longer exist —
    retarget it, do not delete it"). The old line was, verbatim:

        guarded = {"daily_wage", "ot_amount", "cost_of"}

    `daily_wage(monthly_salary, days_per_month)` divided a monthly figure by
    `settings.wage_days_per_month()`. There is no monthly figure and no divisor
    any more — the employee master carries a **day rate**, so a day's wage is
    the stored number and there is nothing to compute. The function is gone and
    `day_rate_of()` replaced it. **The teeth are unchanged**: `ot_amount()` is
    where the multiplier and the `÷ 8` live, and it is still the function a
    literal `1` or a literal `8` would turn into a statutory underpayment.
    `test_the_guard_would_catch_a_literal_multiplier` below proves this walk
    still catches one.
    """
    src = (REPO / "attendance.py").read_text(encoding="utf8")
    tree = ast.parse(src)

    guarded = {"day_rate_of", "ot_amount", "cost_of"}
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in guarded):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.BinOp) and isinstance(
                    inner.op, (ast.Mult, ast.Div)):
                for side in (inner.left, inner.right):
                    if isinstance(side, ast.Constant) and isinstance(
                            side.value, (int, float)) and not isinstance(
                            side.value, bool):
                        offenders.append(
                            f"{node.name}() line {inner.lineno}: "
                            f"{side.value!r}")

    assert not offenders, (
        "a rate is written into the calculation instead of arriving from "
        "/settings — CC-2 requires the OT multiplier to be configurable "
        f"because hardcoding it computes an underpayment: {offenders}")

    assert guarded <= {n.name for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef)}, \
        "this test names functions that no longer exist — retarget it, do not "\
        "delete it"


def test_the_guard_would_catch_a_literal_multiplier():
    """
    ⚠ **The vacuity check on the test above, and it is the point of writing
    one.** An AST walk that finds no offenders passes whether it is looking
    hard or not looking at all — and this pass narrowed the guarded set from
    three functions to three different ones, which is exactly the edit that
    could have quietly emptied it.

    So: take the real source, put a literal multiplier into the real
    `ot_amount()` the way a well-meaning simplification would, and run the same
    walk. It must go red.
    """
    src = (REPO / "attendance.py").read_text(encoding="utf8")
    poisoned = src.replace(
        "    hourly = _num(day_wage) / STANDARD_HOURS_PER_DAY",
        "    hourly = _num(day_wage) / 8.0")
    assert poisoned != src, (
        "the line this mutation targets has moved — retarget the mutation, "
        "because a mutation that changes nothing proves nothing")

    tree = ast.parse(poisoned)
    guarded = {"day_rate_of", "ot_amount", "cost_of"}
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in guarded):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.BinOp) and isinstance(
                    inner.op, (ast.Mult, ast.Div)):
                for side in (inner.left, inner.right):
                    if isinstance(side, ast.Constant) and isinstance(
                            side.value, (int, float)) and not isinstance(
                            side.value, bool):
                        offenders.append(node.name)

    assert offenders == ["ot_amount"], (
        f"the AST guard cannot see a rate written into the calculation path — "
        f"it found {offenders!r} in a source that plainly contains one, so its "
        f"passing on the real file means nothing")


def test_the_ot_figure_reads_the_setting_and_moves_when_it_moves(client):
    """
    The behavioural half. **Change the setting and the money changes** — which
    is the whole of what "configurable" means and the only thing a user can
    check.

    On a ₹1,000 day rate an hour is ₹125, so two hours of overtime is ₹250 at
    1× and ₹500 at 2×.

    ⚠ **Rewritten 30 August 2026 and every figure is the same.** The two old
    lines were, verbatim:

        wage = AT.daily_wage(26000.0, 26.0)
        assert wage == 1000.0

    A ₹26,000 month over 26 days was a ₹1,000 day, and ₹1,000 is now the stored
    day rate — so the arithmetic below is untouched and only the way the day's
    wage is arrived at has changed. `daily_wage()` is gone because the division
    it performed was the defect.
    """
    assert S.ot_multiplier() == 1.0, "the client's own figure is the default"

    wage, ok = AT.day_rate_of({"day_rate": 1000.0})
    assert (wage, ok) == (1000.0, True)

    assert AT.ot_amount(wage, 2, S.ot_multiplier()) == 250.0

    S.save_labour_settings("2")
    assert S.ot_multiplier() == 2.0
    assert AT.ot_amount(wage, 2, S.ot_multiplier()) == 500.0, \
        "the statutory rate must double the figure, not be ignored"


def test_changing_the_setting_changes_what_the_page_shows(client):
    """
    End to end, because a function returning the right number is not the same
    as a page showing it. Nothing stored is rewritten — the markings are
    untouched and the page recomputes.
    """
    person = _person(client)
    assert _mark(client, person).status_code == 302

    before = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert "1,250" in before, "1,000 day + 250 overtime at the client's 1x"

    # ⚠ `save_labour_settings` lost its second argument with the divisor. The
    #   old line was, verbatim:  S.save_labour_settings("2", "26")
    S.save_labour_settings("2")
    after = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert "1,500" in after, "1,000 day + 500 overtime at 2x"
    assert "1,250" not in after

    stored = list(STORE["attendance"].values())[0]
    assert stored["ot_hours"] == 2.0, "the marking itself must not be rewritten"


def test_the_settings_page_carries_the_field_and_says_what_it_is_for(client):
    """
    A setting nobody can find is a constant with extra steps. It must be on
    `/settings`, and the page must say plainly why 1× may not be enough — the
    reader is the person who would otherwise leave it alone.
    """
    html = client.get("/settings/").get_data(as_text=True)
    assert 'name="ot_multiplier"' in html
    # ⚠ The divisor's field is GONE. The old line was, verbatim:
    #       assert 'name="wage_days_per_month"' in html
    # `tests/test_day_rate_pin.py::test_the_settings_page_no_longer_offers_the_divisor`
    # is the assertion that replaces it, and it asserts the opposite fact.
    assert "Factories Act" in html, \
        "the page must say why the client's 1x may understate what is owed"


def test_the_wage_divisor_is_gone_and_the_rate_is_a_day_rate(client):
    """
    ⚠ **REPLACES `test_the_wage_divisor_is_a_setting_too_and_is_ours`, which
    asserted a fact that has stopped being true.** Its body was, verbatim:

        assert S.wage_days_per_month() == 26.0
        assert AT.daily_wage(30000.0, 30.0) == 1000.0
        assert AT.daily_wage(30000.0, 26.0) != AT.daily_wage(30000.0, 30.0)

        # A nonsense value must not crash a page somebody opens daily.
        S.save_labour_settings("1", "0")
        assert S.wage_days_per_month() == 26.0, "a zero divisor falls back"

    and its docstring recorded the divisor as **ours, not CC-2's**. That was
    right, and the correct response to "we invented this" turned out to be
    removing it rather than defending it: CC-2's `salary` was a **day rate** all
    along, so there was never anything to divide. The divisor is retired, and
    with it the whole question of 26 versus 30 that this test existed to keep
    open. `tests/test_day_rate_pin.py` holds the rest of the property.
    """
    assert not hasattr(S, "wage_days_per_month")
    assert not hasattr(AT, "daily_wage")
    assert "wage_days_per_month" not in S.LABOUR_DEFAULTS

    # A day's wage is the stored rate and nothing else — no arithmetic between
    # the record and the figure, which is what makes a divisor impossible.
    assert AT.day_rate_of({"day_rate": 1000.0}) == (1000.0, True)

    # The multiplier survives, and a nonsense value still falls back rather than
    # crashing a page somebody opens daily.
    S.save_labour_settings("not a number")
    assert S.ot_multiplier() == 1.0, "a nonsense multiplier falls back"


# ══ 2. ⚠ One employee = one site = one day ════════════════════════════════

def test_a_second_marking_for_the_same_person_and_day_is_refused(client):
    """
    ⚠ **CC-2's third bullet, and the reason the constraint is on
    `(employee, date)` rather than on `(employee, site, date)`.**

    The second reading would let one person be marked present on three sites on
    one day and bill a full day's wage three times, silently, on the only
    figure this module produces. So a **different site on the same day is
    refused too** — that is the case the wrong key would wave through.
    """
    person = _person(client)
    assert _mark(client, person).status_code == 302
    assert len(STORE["attendance"]) == 1

    r = _mark(client, person, site="Some Other Site")
    assert r.status_code == 200, "the refusal re-renders the form"
    assert len(STORE["attendance"]) == 1, "nothing was written"

    body = r.get_data(as_text=True)
    assert "already marked" in body
    assert "Whitefield" in body, "the existing record is named, not just refused"


def test_the_refusal_is_at_write_time_and_not_only_in_the_form(client):
    """
    Asserted against `conflicting_record()` directly, because the form is a
    convenience and the rule is the rule. A future pass that changes the picker
    must not be able to change the constraint by accident.
    """
    person = _person(client)
    _mark(client, person)

    assert AT.conflicting_record(person["id"], DAY), "the clash is visible"
    assert not AT.conflicting_record(person["id"], "2026-08-30"), \
        "a different day is not a clash"

    other = _person(client, name="Second Person", code="SF-015")
    assert not AT.conflicting_record(other["id"], DAY), \
        "a different person on the same day is not a clash"


def test_editing_a_record_does_not_clash_with_itself(client):
    """
    The way this constraint is usually got wrong: saving a record unchanged
    finds itself and refuses. `except_id` is what stops it, and an edit that
    could never be saved would make the whole feature unusable.
    """
    person = _person(client)
    _mark(client, person)
    rid = list(STORE["attendance"])[0]

    r = client.post(f"/attendance/edit/{rid}",
                    data={"date": DAY, "employee_id": person["id"],
                          "site": "Whitefield", "status": "present",
                          "ot_hours": "3", "notes": ""})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert STORE["attendance"][rid]["ot_hours"] == 3.0


# ══ 3. The register, and the round trip ═══════════════════════════════════

def test_the_register_renders_empty(client):
    r = client.get("/attendance/")
    assert r.status_code == 200
    assert "Nobody is marked for this day yet" in r.get_data(as_text=True)


def test_a_marking_round_trips_through_the_routes(client):
    """Created through the form, read back off the record, shown on the page."""
    person = _person(client)
    assert _mark(client, person, notes="half day rain").status_code == 302

    rec = list(STORE["attendance"].values())[0]
    assert rec["date"] == DAY
    assert rec["employee_id"] == person["id"]
    assert rec["site"] == "Whitefield"
    assert rec["status"] == "present"
    assert rec["ot_hours"] == 2.0
    assert rec["notes"] == "half day rain"

    # ⚠ Snapshotted, not looked up — the freeze contract every record in this
    # app holds to. A wage for a day already worked must not move when the
    # salary is revised.
    assert rec["employee_name"] == "Ramesh Patil"
    assert rec["employee_code"] == "SF-014"
    # ⚠ A DAY rate since 30 August 2026. The old line was, verbatim:
    #       assert rec["monthly_salary"] == 26000.0
    # A ₹26,000 month over the old divisor of 26 was a ₹1,000 day, so the money
    # the page shows is unchanged; what moved is that the day rate is now the
    # thing stored rather than a figure derived from a monthly one.
    assert rec["day_rate"] == 1000.0
    assert "monthly_salary" not in rec, (
        "a marking written today carries a monthly figure — the write route "
        "is still on the old model")

    html = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert "Ramesh Patil" in html and "Whitefield" in html


def test_a_salary_revision_does_not_move_a_day_already_recorded(client):
    """
    The point of the snapshot, stated as behaviour. `ra.prev_balance` and
    `proforma.prior_invoiced` make the same argument one chain over.
    """
    person = _person(client)
    _mark(client, person)
    before = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)

    # ⚠ The old line was, verbatim:  person["monthly_salary"] = 52000.0
    #   The field it revises has been renamed; the property is identical.
    person["day_rate"] = 2000.0
    after = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert before == after, \
        "a wage already recorded must not move when the master changes"


def test_an_absent_day_costs_nothing_and_its_overtime_is_not_paid(client):
    """
    **"Salary as 0 or 1 based on attendance"** — CC-2's second bullet.

    ⚠ Overtime hours on an absent day are **stored and shown, and not paid**.
    CC-2 does not rule on it; paying for hours on a day the register says
    nobody worked would be the more expensive mistake to make silently, and the
    hours stay visible so the contradiction is not swallowed.
    """
    person = _person(client)
    assert _mark(client, person, status="absent", ot_hours="3").status_code == 302

    rec = list(STORE["attendance"].values())[0]
    assert rec["ot_hours"] == 3.0, "the hours are recorded"

    # ⚠ `cost_of` lost its divisor argument and gained a refusal. The old two
    #   lines were, verbatim:
    #       c = AT.cost_of(rec, 26.0, 1.0)
    #       assert c == {"day": 0.0, "ot": 0.0, "total": 0.0}
    #   The three money figures are identical; `refused` is False because this
    #   marking carries a day rate, and it is asserted so that a refusal can
    #   never be mistaken for an absent day — both would once have read 0.0.
    c = AT.cost_of(rec, 1.0)
    assert c == {"day": 0.0, "ot": 0.0, "total": 0.0,
                 "refused": False, "reason": ""}

    html = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert "not paid" in html, "the contradiction must be visible on the page"


def test_the_site_wise_labour_cost_is_the_presentation_table(client):
    """
    CC-2's fifth bullet — Employee, Site, OT time — plus the cost the item is
    named for. Two people on two sites must not be summed into one figure.
    """
    a = _person(client, name="A Person", code="SF-101", site="Site A")
    b = _person(client, name="B Person", code="SF-102", site="Site B")
    _mark(client, a, site="Site A", ot_hours="0")
    _mark(client, b, site="Site B", ot_hours="8")

    rows = AT.site_costs(DAY)
    assert [r["site"] for r in rows] == ["Site A", "Site B"]
    assert rows[0]["total"] == 1000.0, "one day, no overtime"
    assert rows[1]["total"] == 2000.0, "one day plus eight hours at 1x"

    html = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert "Site-wise labour cost" in html
    assert "Site A" in html and "Site B" in html


def test_the_cost_is_derived_and_never_stored(client):
    """
    A maintained total is a number one code path can forget to update, and this
    repo has paid for that twice. Nothing on the record holds a cost.
    """
    person = _person(client)
    _mark(client, person)
    rec = list(STORE["attendance"].values())[0]
    for banned in ("cost", "total", "day_wage", "wage", "amount", "ot_amount"):
        assert banned not in rec, \
            f"{banned!r} is stored — the labour cost must be derived"


# ══ 4. An inactive employee cannot be marked ══════════════════════════════

def test_an_inactive_employee_cannot_be_marked(client):
    """
    Checked on the **record**, not on the dropdown. The picker lists active
    people only, but a posted id can name anybody — and somebody who has left
    cannot be on site.
    """
    person = _person(client, active=None)
    assert person["active"] is False

    r = _mark(client, person)
    assert r.status_code == 200
    assert not STORE["attendance"], "nothing was written"
    assert "no longer employed" in r.get_data(as_text=True)


def test_the_picker_offers_active_people_only(client):
    """The form half of the same rule — a convenience, not the guard."""
    _person(client, name="Still Here", code="SF-201")
    _person(client, name="Has Left", code="SF-202", active=None)

    html = client.get("/attendance/mark").get_data(as_text=True)
    assert "Still Here" in html
    assert "Has Left" not in html


def test_an_employee_who_is_gone_altogether_is_refused(client):
    """A posted id naming nobody must not write a marking against nobody."""
    person = _person(client)
    STORE["employees"].clear()
    r = _mark(client, person)
    assert r.status_code == 200
    assert not STORE["attendance"]


# ══ 5. Delete confirms on GET ═════════════════════════════════════════════

def test_a_get_on_delete_destroys_nothing(client):
    """
    ⚠ **ABOUT.md §7.9f point 2, which is not optional.** The `url_map` sweep in
    `test_delete_methods.py` catches a GET-only delete route and says in terms
    that it **cannot** catch one accepting both verbs that still destroys on
    GET. So every new delete route ships this test, by hand.
    """
    person = _person(client)
    _mark(client, person)
    rid = list(STORE["attendance"])[0]

    r = client.get(f"/attendance/delete/{rid}")
    assert r.status_code == 200
    assert rid in STORE["attendance"], "a GET must only confirm"

    r = client.post(f"/attendance/delete/{rid}")
    assert r.status_code == 302
    assert rid not in STORE["attendance"]


# ══ 6. Access control ═════════════════════════════════════════════════════

def test_every_attendance_endpoint_is_classified():
    """
    An endpoint absent from `ROUTE_PERMISSIONS` is refused to everybody,
    including an Owner — absence fails closed, which is the design. This is the
    per-module form of `test_every_endpoint_is_classified`.
    """
    import app as app_module
    found = [r.endpoint for r in app_module.app.url_map.iter_rules()
             if r.endpoint.startswith("attendance.")]

    # ⚠ Without this the loop below is green when the blueprint is not
    #   registered at all: nothing matches the prefix, nothing is asserted, and
    #   "every attendance endpoint is classified" is true of the empty set.
    #   Four routes on 30 August 2026 — list, mark, edit and delete. The
    #   site-wise labour cost is a panel on the list page, not a route.
    assert len(found) >= 4, (
        f"only {len(found)} attendance endpoints are registered; the sweep "
        f"below would assert nothing")

    for endpoint in found:
        assert endpoint in auth.ROUTE_PERMISSIONS, \
            f"{endpoint} is unclassified and therefore unreachable"


@pytest.mark.parametrize("slug", WALLED_OFF)
def test_sales_purchase_and_accounts_are_refused_on_every_route(client, slug):
    """
    ⚠ **B4's one stated restriction, applied to a third surface.** *"HR
    information is restricted from Sales, Purchase and Accounts"* — and a
    muster carrying a salary snapshot and producing a wage is that information.
    Hit **every** route by direct URL; hiding a card is presentation.
    """
    person = _person(client)
    _mark(client, person)
    rid = list(STORE["attendance"])[0]

    _as(client, _user_with(slug))
    for route in ATTENDANCE_ROUTES:
        url = route.format(id=rid)
        assert client.get(url).status_code == 403, f"{slug} reached {url}"


def test_hr_is_admitted_everywhere(client):
    """The other side of the wall: HR keeps the muster, as it keeps the master."""
    person = _person(client)
    _mark(client, person)
    rid = list(STORE["attendance"])[0]

    _as(client, _user_with("hr"))
    for route in ATTENDANCE_ROUTES:
        url = route.format(id=rid)
        assert client.get(url).status_code == 200, f"HR was refused {url}"


def test_operation_head_is_refused_and_it_is_our_derivation(client):
    """
    ⚠ **Refused, and the refusal is OURS rather than CC-2's.**

    B4 names Operations Head as one of its six roles, so "CC-2 is silent on the
    role" is not the reason. The reason is narrower: B4's one sentence about
    employee data does not name Operations Head **in either direction**. It is
    a **reversible default** — an Owner grants it at `/roles/edit/<id>` with a
    checkbox, no code change and no re-login — and the access matrix marks it
    `–` (withheld by our derivation) rather than `§`.
    """
    person = _person(client)
    _mark(client, person)
    rid = list(STORE["attendance"])[0]

    _as(client, _user_with("operation-head"))
    for route in ATTENDANCE_ROUTES:
        url = route.format(id=rid)
        assert client.get(url).status_code == 403, \
            f"Operation Head reached {url}"


def test_the_matrix_marks_operation_head_as_our_derivation_not_the_spec():
    """
    The claim the grid makes about those four cells, asserted against the
    generated document. `§` would assert a backing that does not exist.
    """
    doc = (REPO / "docs" / "ACCESS_MATRIX.md").read_text(encoding="utf8")
    for perm in ("attendance.view", "attendance.create", "attendance.edit",
                 "attendance.delete"):
        row = next(l for l in doc.splitlines() if f"`{perm}`" in l and "|" in l)
        # A leading "|" makes cells[0] empty and cells[1] the label, so the
        # seven role columns are cells[2..8] in the order the grid heads them:
        # Owner, Director, Operation Head, HR, Sales, Purchase, Accountant.
        cells = [c.strip() for c in row.split("|")]
        owner, director, ops, hr = cells[2], cells[3], cells[4], cells[5]
        assert owner == "·" and director == "·" and hr == "·", \
            f"{perm}: Owner, Director and HR hold it, as our derivation"
        assert ops == "–", (
            f"{perm}: Operation Head must carry the '–' mark — withheld by OUR "
            f"derivation, reversible at /roles/edit/<id>. Got {ops!r}.")
        assert ops != "§", \
            f"{perm}: a § would claim a backing CC-2 does not give"
        assert cells[6] == cells[7] == cells[8] == "§", \
            f"{perm}: Sales, Purchase and Accounts ARE B4's own sentence"


def test_operation_head_can_be_granted_it_without_a_code_change(client):
    """
    ⚠ **The claim "reversible default" makes, checked rather than asserted.**
    A permission that needs a deployment to grant is a policy, not a default.
    """
    auth.ensure_builtin_roles()
    role = auth.roles()["role-operation-head"]
    before = list(role["permissions"])
    try:
        role["permissions"] = before + ["attendance.view"]
        _as(client, _user_with("operation-head"))
        assert client.get("/attendance/").status_code == 200, \
            "one checkbox must be all it takes"
    finally:
        role["permissions"] = before


# ══ 7. ⚠ What C5 is NOT — C6 is BLOCKED and stays blocked ═════════════════

def test_nothing_imports_the_attendance_module():
    """
    ⚠ **The structural half of "not wired into C6".**

    C6 is BLOCKED on CC-2's Open question 4 — attendance wages or the BOQ
    installation base rate — and subtracting both counts labour twice. C5 can
    be built without the answer; wiring it into C6 cannot. So nothing consumes
    this module, and that is checked at AST level rather than promised.
    """
    offenders = []
    for path in REPO.glob("*.py"):
        if path.name in ("attendance.py", "app.py"):
            continue                      # app.py registers the blueprint
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n.split(".")[0] == "attendance" for n in names):
                offenders.append(path.name)
    assert not offenders, (
        f"{offenders} import attendance.py — a labour cost figure reaching "
        f"another module is C6, which is BLOCKED")


def test_the_employee_master_links_out_without_importing_back():
    """
    `attendance.py` imports `employee.py`; the register links the other way
    with `url_for` and imports nothing. The one-way trick, used again.
    """
    src = (REPO / "employee.py").read_text(encoding="utf8")
    assert "url_for('attendance.list_attendance')" in src or \
           'url_for("attendance.list_attendance")' in src, \
        "the employee register must offer a way through to the muster"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            assert "attendance" not in [mod] + names, \
                "employee.py must not import attendance.py — that is a cycle"


def test_the_charge_ledger_is_still_forbidden_in_both_directions():
    """
    ⚠ **That prohibition did NOT expire when C5 was authorised.** Joining the
    wages ledger to the people data is a profit-and-loss question, and C6 is
    blocked. `test_import_directions.py` holds `employee ↔ charge`; this holds
    the same edge for the new module.
    """
    for a, b in (("attendance", "charge"), ("charge", "attendance")):
        tree = ast.parse((REPO / f"{a}.py").read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                names = [a_.name for a_ in getattr(node, "names", [])]
                assert b not in [mod] + names, f"{a}.py imports {b}.py"


def test_the_project_page_still_shows_no_labour_cost(client):
    """
    `projectview.py` carries a standing prohibition — *"no revenue total, no
    cost total, no margin, no profit, no net, no balance"* — that C6 requires be
    reversed and this pass leaves alone. Asserted on the source, because that
    docstring is the guard.
    """
    src = (REPO / "projectview.py").read_text(encoding="utf8")
    assert "no cost total" in src, "the standing prohibition must be intact"
    assert "attendance" not in src.lower(), \
        "a labour figure on the project page is C6, which is BLOCKED"


def test_the_dashboard_card_carries_counts_and_no_money(client):
    """
    ⚠ The launcher card shows how many markings exist, never what they cost.
    A labour-cost total there would be the first half of the P&L C6 is blocked
    on, and it would put payroll-derived money in front of every holder of
    `dashboard.view` — ABOUT.md §7 gap 27's trap.
    """
    person = _person(client)
    _mark(client, person)

    html = client.get("/").get_data(as_text=True)
    card = html[html.index(">Attendance<"):]
    card = card[:card.index("</a>")]
    assert "marked" in card and "today" in card
    assert "8377" not in card, "no rupee figure belongs on this card"


def test_the_pages_say_this_is_not_payroll(client):
    """
    The one sentence that has to be on every page of this module. Somebody will
    read a figure here as somebody's pay; the page has to say it is not.
    """
    person = _person(client)
    _mark(client, person)
    for url in ("/attendance/", "/attendance/mark"):
        html = client.get(url).get_data(as_text=True)
        assert "not payroll" in html, f"{url} must say what this is not"
        assert "PF" in html and "ESIC" in html


def test_only_this_module_and_the_launcher_touch_the_collection():
    """
    One writer, so a labour figure cannot appear from somewhere that never
    thought about the uniqueness constraint.

    ⚠ **`dashboard.py` is the one exception and it is a READER**, exactly as it
    reads every other collection for a card count. It is exempted here and
    held to the narrower rule by
    `test_the_dashboard_card_carries_counts_and_no_money`: it may count
    markings and it may not price them.
    """
    reach = re.compile(r'STORE\s*(\.\s*(get|setdefault)\s*\(\s*)?\[?\s*["\']attendance["\']')
    offenders = []
    for path in REPO.glob("*.py"):
        if path.name in ("attendance.py", "store.py", "db.py", "dashboard.py"):
            continue
        if reach.search(path.read_text(encoding="utf8")):
            offenders.append(path.name)
    assert not offenders, f"{offenders} reach into STORE['attendance']"

    # And the exemption is a count, not an arithmetic: no wage, no multiplier
    # and no divisor anywhere near it.
    dash = (REPO / "dashboard.py").read_text(encoding="utf8")
    window = dash[dash.index('"att_total"'):]
    window = window[:600]

    for banned in ("ot_multiplier", "wage_days_per_month", "daily_wage",
                   "cost_of", "site_costs"):
        assert banned not in window, \
            f"the launcher is computing labour cost ({banned}) — that is C6"
