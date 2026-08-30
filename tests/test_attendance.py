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

   ⚠ **This entry read *"Asserted structurally: nothing imports this module,
   and the labour cost appears on no other page"* until 30 August 2026, and
   both halves stopped being true in the fifth pass of that date** — when the
   Site Labour section was authorised, `projectview.py` became an importer and
   the project page began carrying figures out of here. The **guards** were
   rewritten then and this summary was not, which is the same drift §7 of
   ABOUT.md keeps recording one field over. What is asserted today:
   `projectview.py` is the **only** importer (an allowlist of one), what
   crosses is **rendered cells** and never the arithmetic, and
   `projectview.py` still builds no margin, project total or net.

7. ⚠ **A MARKING SAYS WHICH PROJECT IT IS FOR** (30 August 2026, sixth override
   block) — **not CC-2 scope**, PROGRESS.md §4c. `charge.py`'s two keys, an id
   somebody picked and a snapshotted name, with the picker **filtered to the
   projects at the marking's own site**. One project preselects, several
   **require** a choice, none saves blank, and a project at another site is
   **dropped and never stored**. ⚠ **It does not answer Open question 4 and C6
   stays BLOCKED**: attributing a day is not costing a project. Section 7 below.
"""

import ast
import pathlib
import re

import pytest

import attendance as AT
import auth
import employee as EMP
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
    _MINTED.clear()
    yield
    STORE.setdefault("employees", {}).clear()
    STORE.setdefault("attendance", {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    # ⚠ **And the site addresses this file mints.** They go into the SHARED
    #   address book, and `tests/test_challan.py` picks `next(iter(...))` out of
    #   it to prove the consignee prefill works — so a leaked skeleton address
    #   fails a test in another file, which is exactly what happened once.
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


# Ids minted by `_site()`, so `_clean()` can take them back out of the shared
# address book. See its note.
_MINTED = set()


def _site(label="Whitefield"):
    """
    A site in the address book, and its id — which is what the picker posts.

    ⚠ Written straight into `STORE["addresses"]` rather than through
    `/address/add`, so the id is known to the caller and the fixture does not
    depend on that form's validation.
    """
    aid = f"addr-{label.lower().replace(' ', '-')}"
    _MINTED.add(aid)
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": "site",
        "contact_name": "", "company": "", "line1": "1 Site Road",
        "line2": "", "landmark": "", "city": "Bengaluru",
        "state": "Karnataka", "pincode": "560066", "country": "India",
        "phone": "", "email": "", "gstin": "",
    }
    return aid


def _person(client, **over):
    """Somebody on the register, added through the real employee route."""
    # ⚠ `day_rate` since 30 August 2026. It was
    #   `"monthly_salary": "26000"` and a divisor of 26 turned that into a
    #   day's ₹1,000; the day rate IS ₹1,000, so every figure this file asserts
    #   is unchanged and only the route it arrives by has moved.
    data = {
        "name": "Ramesh Patil", "code": "SF-014", "designation": "Fitter",
        # ⚠ `site_id` since 30 August 2026 — a picker over the address book,
        #   not free text. The old fragment was, verbatim:
        #       "site": "Whitefield", "date_joined": "2026-04-01",
        "site_id": _site("Whitefield"), "date_joined": "2026-04-01",
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
    # ⚠ The old line was, verbatim:
    #       data = {"date": DAY, "employee_id": person["id"], "site": "Whitefield",
    data = {"date": DAY, "employee_id": person["id"],
            "site_id": _site("Whitefield"),
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
    # ⚠ `site` is the address LABEL, snapshotted — the assertion is the OLD
    #   one unchanged, and the two after it are what the picker added.
    assert rec["site"] == "Whitefield"
    assert rec[EMP.SITE_ADDRESS_FIELD] == "addr-whitefield"
    assert rec[EMP.SITE_SOURCE_FIELD] == EMP.SITE_BOOK
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
    # ⚠ The old four lines were, verbatim:
    #       a = _person(client, name="A Person", code="SF-101", site="Site A")
    #       b = _person(client, name="B Person", code="SF-102", site="Site B")
    #       _mark(client, a, site="Site A", ot_hours="0")
    #       _mark(client, b, site="Site B", ot_hours="8")
    #   Both sites are address-book entries now. Every figure below is
    #   unchanged; only how the site is chosen has moved.
    a = _person(client, name="A Person", code="SF-101", site_id=_site("Site A"))
    b = _person(client, name="B Person", code="SF-102", site_id=_site("Site B"))
    _mark(client, a, site_id=_site("Site A"), ot_hours="0")
    _mark(client, b, site_id=_site("Site B"), ot_hours="8")

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

def test_only_projectview_imports_the_attendance_module():
    """
    ⚠ **The structural half of "not wired into C6" — REWRITTEN 30 August 2026,
    fifth pass. The old assertion, verbatim:**

        assert not offenders, (
            f"{offenders} import attendance.py — a labour cost figure reaching "
            f"another module is C6, which is BLOCKED")

    …with `offenders` computed over every module but `attendance.py` and
    `app.py`. It held from 29 August 2026 until the FIFTH override block of
    30 August 2026 authorised the Site Labour section on `/projects/view/<id>`,
    which needs `marking_cells()` and `markings_at_site()`.

    ⚠ **The rule is NARROWED, not dropped, and C6 is still BLOCKED.** The
    reasoning the old test carried is unchanged and still correct: C6 is blocked
    on CC-2's Open question 4 — attendance wages or the BOQ installation base
    rate — and subtracting both counts labour twice. **This pass answers that
    question in no direction.** What it authorises is a *presentation* of
    markings on a second page, and the override block says so in terms.

    So the assertion becomes an **allowlist of exactly one**, which is stricter
    than a blacklist for the reason `test_auth_imports_nothing_that_prints` is a
    whitelist: a blacklist has to be remembered when somebody adds a module, and
    a second consumer of this module is the thing that has to stay hard.
    """
    permitted = {"projectview"}          # and nothing else, ever, without a block
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
                offenders.append(path.stem)

    assert set(offenders) <= permitted, (
        f"{sorted(set(offenders) - permitted)} import attendance.py. Exactly "
        f"one module may — projectview.py, under the FIFTH override block of "
        f"30 August 2026 — and a labour figure reaching any OTHER module is C6, "
        f"which is BLOCKED on CC-2's Open question 4.")
    assert set(offenders) == permitted, (
        "projectview.py no longer imports attendance.py. If the Site Labour "
        "section was removed, narrow this allowlist back to empty and restore "
        "the original assertion quoted in the docstring above — do not leave a "
        "permission standing that nothing exercises.")


def test_the_labour_section_consumes_the_module_and_does_not_reimplement_it():
    """
    ⚠ **What the narrowed import is allowed to be, and what it is not.**

    The one permitted consumer takes *rendered answers*. It may not take the
    arithmetic: a second module able to compute a wage is a second place the OT
    multiplier could be hardcoded, which is the statutory-underpayment defect
    CC-2 names, and it is what would make this an export of C6's figure rather
    than a presentation of C5's rows.

    ⚠ **REWRITTEN 30 August 2026, sixth pass. The old assertion, verbatim:**

        assert "AT.markings_at_site(" in src and "AT.marking_cells(" in src, (
            "the section must consume attendance.py's own accessors — "
            "reimplementing either is the second copy this extraction exists "
            "to prevent")

    **Nothing about the rule changed; the accessor list grew.** The section now
    renders two groups, so it asks `markings_for_project()` and
    `unattributed_at_site()` instead of taking one list and splitting it here —
    which is the point: splitting locally would put a second definition of
    "attributed" on this page. ⚠ **The banned list below is UNCHANGED**, which
    is the half of this test that was ever load-bearing.
    """
    src = (REPO / "projectview.py").read_text(encoding="utf8")

    for accessor in ("marking_cells", "markings_for_project",
                     "unattributed_at_site"):
        assert f"AT.{accessor}(" in src, (
            f"the section must consume attendance.{accessor}() — "
            f"reimplementing it is the second copy this extraction exists to "
            f"prevent")

    # ⚠ And it must not have gone back to filtering a raw list itself: the
    #   question "is this marking attributed?" has one owner.
    assert "AT.markings_at_site(" not in src, (
        "the section takes the whole site list again — the two groups must "
        "come from the module that owns what 'attributed' means")

    for banned in ("cost_of", "ot_amount", "day_rate_of", "site_costs",
                   "STANDARD_HOURS_PER_DAY"):
        assert f"AT.{banned}" not in src, (
            f"projectview.py reaches for attendance.{banned} — the arithmetic "
            f"stays in the module that owns it, and a caller that can compute a "
            f"wage can hardcode a multiplier")


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


def test_the_project_page_builds_no_margin_total_or_net():
    """
    ⚠ **REWRITTEN 30 August 2026, fifth pass. The old assertions, verbatim:**

        src = (REPO / "projectview.py").read_text(encoding="utf8")
        assert "no cost total" in src, "the standing prohibition must be intact"
        assert "attendance" not in src.lower(), \\
            "a labour figure on the project page is C6, which is BLOCKED"

    **The first line is kept below and is unchanged.** The second is what the
    FIFTH override block of 30 August 2026 lifts, and it lifts *only* that
    clause: the Site Labour section presents markings on the project page and is
    explicitly not a P&L authority.

    ⚠ **The prohibition the old test was really guarding is NOT relaxed**, and
    this is now stated as what it always meant rather than as a proxy for it.
    `projectview.py`'s docstring reads *"Each panel shows the documents' OWN
    values and adds that one column up. What this page must never show is a
    figure that only exists by combining two panels — no revenue total, no cost
    total, no margin, no profit, no net, no balance."* The labour panel's sum is
    the **first** sentence, which five panels already exercise. The second
    sentence is what C6 would need reversed and what nothing here reverses.
    """
    src = (REPO / "projectview.py").read_text(encoding="utf8")
    assert "no cost total" in src, "the standing prohibition must be intact"

    # The panel sum goes through the SAME two helpers the other five panels use,
    # so there is one arithmetic path on this page rather than a second one that
    # could quietly start combining panels.
    assert "_sum_cell(vals)" in src, (
        "the labour panel must add its column up through _sum_cell(), the "
        "helper whose own docstring says 'a sum down a single panel, never "
        "across two'")

    # ⚠ Nothing on this page may combine two panels. These are the names a P&L
    #   would arrive under, and none of them may be computed here.
    tree = ast.parse(src)
    assigned = {t.id for n in ast.walk(tree)
                if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    for banned in ("margin", "net", "profit", "project_total", "gross_margin",
                   "cost_total", "revenue_total", "balance"):
        assert banned not in assigned, (
            f"projectview.py computes {banned!r} — that is C6, BLOCKED on "
            f"CC-2's Open question 4")


def test_the_labour_section_says_the_rows_are_not_tagged_to_the_project(client):
    """
    ⚠ **The wording is load-bearing and this is the test that says so.**

    ⚠ **REWRITTEN 30 August 2026, sixth pass. The old assertion, verbatim:**

        assert "not</b> tagged to this project" in html or \\
               "not tagged to this project" in html, (
            "the section must say these rows are NOT tagged to the project")

    **It was true of every row and is now true of only one of the two groups.**
    A marking gained a `project_id` picked off a filtered dropdown, so group 1's
    rows *are* tagged to this project by the same mechanism a charge is. Saying
    otherwise across the whole panel would now be the lie the old assertion
    existed to prevent, pointing the other way.

    **What is asserted instead is the substance the old line was protecting**:
    the *unattributed* group must say, of its own rows, that they belong to no
    project — and the charges panel's wording must still not be copied onto it.
    """
    aid = "addr-sl-1"
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": "Whitefield", "type": "site"}
    pid = "proj-sl-1"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Tower A", "client": "C",
        "site_address": "Whitefield", "site_address_id": aid}
    # An unattributed marking, so the group that carries the wording renders.
    STORE.setdefault("attendance", {})["sl-1-loose"] = {
        "id": "sl-1-loose", "date": DAY, "employee_id": "e1",
        "employee_name": "Nobody's Project", "employee_code": "SF-001",
        "day_rate": 1000.0, "site": "Whitefield", "site_address_id": aid,
        "site_source": "book", "status": "present", "ot_hours": 0.0}
    try:
        html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
        assert "Site Labour" in html
        section = html[html.index("<h2>Site Labour</h2>"):]

        assert "At this site, unattributed" in section, (
            "the unattributed rows need a heading of their own — merging them "
            "into the attributed ones is the whole defect")
        assert "attributed to no project at all" in section, (
            "the section must say these rows belong to no project")
        assert "Booked to this project" in section, (
            "and the attributed group must be labelled as what it is")
        assert "Whitefield" in html, "it must name the site"

        # The charges panel's wording must not have been copied onto it.
        assert "Expenses tagged to this project" not in section
    finally:
        STORE["projects"].pop(pid, None)
        STORE["addresses"].pop(aid, None)
        STORE["attendance"].pop("sl-1-loose", None)


def test_the_labour_section_names_every_other_project_on_the_same_site(client):
    """
    ⚠ **The ambiguity note, end to end.** Two projects on one address with an
    **unattributed** marking on it: that marking answers for both, the data
    cannot say which, and the page must not imply otherwise.

    ⚠ **REWRITTEN 30 August 2026, sixth pass. The old body created the two
    projects and NO markings, and asserted:**

        html = client.get(f"/projects/view/{ids[0]}").get_data(as_text=True)
        assert "1 other project is recorded at this same site" in html
        assert "Sify3" in html, "the note must NAME the other project"
        assert "cannot be determined from this data" in html

    **All three still hold — under the condition that now has to be true for the
    note to be honest.** The note claims the same money shows on another
    project's page, and that is only true of markings nobody has attributed. So
    the fixture gains the unattributed marking the note is about, and the test
    gains a **second control**: attribute it, and the note goes away.
    """
    aid = "addr-sl-2"
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": "Bangalore, Karnataka", "type": "site"}
    ids = ("proj-sl-a", "proj-sl-b")
    for pid, name in zip(ids, ("Sify Bangalore", "Sify3")):
        STORE.setdefault("projects", {})[pid] = {
            "id": pid, "name": name, "client": "C",
            "site_address": "Bangalore, Karnataka", "site_address_id": aid}
    loose = {"id": "sl-2-loose", "date": DAY, "employee_id": "e1",
             "employee_name": "Unattributed", "employee_code": "SF-001",
             "day_rate": 1000.0, "site": "Bangalore, Karnataka",
             "site_address_id": aid, "site_source": "book",
             "status": "present", "ot_hours": 0.0}
    STORE.setdefault("attendance", {})["sl-2-loose"] = loose
    try:
        html = client.get(f"/projects/view/{ids[0]}").get_data(as_text=True)
        assert "1 other project is recorded at this same site" in html
        assert "Sify3" in html, "the note must NAME the other project"
        assert "cannot be determined from this data" in html

        # ⚠ CONTROL 1 — attribute the marking, and the note is no longer true.
        #   The sibling project is still there; the double count is not.
        loose["project_id"] = ids[0]
        loose["project_name"] = "Sify Bangalore"
        resolved = client.get(f"/projects/view/{ids[0]}").get_data(as_text=True)
        assert "recorded at this same site" not in resolved, (
            "every marking is attributed, so the ambiguity is resolved — a "
            "page that goes on warning about it teaches people to ignore the "
            "warning")
        assert "Unattributed" in resolved, "the marking is still shown"
        loose.pop("project_id"), loose.pop("project_name")

        # CONTROL 2 — one project alone on a site raises no note either.
        STORE["projects"].pop(ids[1])
        alone = client.get(f"/projects/view/{ids[0]}").get_data(as_text=True)
        assert "recorded at this same site" not in alone, (
            "a note that appears when there is no ambiguity teaches people to "
            "ignore it")
    finally:
        for pid in ids:
            STORE["projects"].pop(pid, None)
        STORE["addresses"].pop(aid, None)
        STORE["attendance"].pop("sl-2-loose", None)


def test_the_two_groups_are_summed_separately_and_never_added_together(client):
    """
    ⚠ **The whole point of splitting the panel.** One group is attributed and
    the other is not, so a combined figure would state exactly the thing the
    page says cannot be determined.

    Two markings at one site, one booked to the project and one not, at
    deliberately different day rates so the three candidate figures — 1,000,
    250 and 1,250 — cannot be confused with each other.
    """
    aid = "addr-sl-6"
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": "Split Site", "type": "site"}
    pid = "proj-sl-6"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Split", "client": "C",
        "site_address": "Split Site", "site_address_id": aid}
    STORE.setdefault("attendance", {}).update({
        "sl6-booked": {"id": "sl6-booked", "date": DAY, "employee_id": "e1",
                       "employee_name": "Booked", "employee_code": "SF-001",
                       "day_rate": 1000.0, "site": "Split Site",
                       "site_address_id": aid, "site_source": "book",
                       "project_id": pid, "project_name": "Split",
                       "status": "present", "ot_hours": 0.0},
        "sl6-loose": {"id": "sl6-loose", "date": DAY, "employee_id": "e2",
                      "employee_name": "Loose", "employee_code": "SF-002",
                      "day_rate": 250.0, "site": "Split Site",
                      "site_address_id": aid, "site_source": "book",
                      "status": "present", "ot_hours": 0.0},
    })
    try:
        html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
        section = html[html.index("<h2>Site Labour</h2>"):]

        totals = re.findall(r'class="total-row"><td colspan="6">Total</td>'
                            r'<td style="text-align:right;">([^<]*)</td>',
                            section)
        assert len(totals) == 2, (
            f"the panel must carry exactly two group totals, got {totals!r}")
        assert totals[0].strip() == "1,000.00", (
            f"the booked group must total only what is booked: {totals!r}")
        assert totals[1].strip() == "250.00", (
            f"the unattributed group must total only what is loose: {totals!r}")

        # ⚠ THE MUTATION THAT MATTERS: the combined figure must appear nowhere.
        assert "1,250" not in section, (
            "the two groups were added together — that is a figure combining "
            "an attributed total with an unattributed one, which states the "
            "very thing this page says cannot be determined")

        # The control: each row really is in the group it belongs to.
        booked_block = section[section.index("Booked to this project"):
                               section.index("At this site, unattributed")]
        assert "Booked" in booked_block and "Loose" not in booked_block
    finally:
        STORE["projects"].pop(pid, None)
        STORE["addresses"].pop(aid, None)
        for k in ("sl6-booked", "sl6-loose"):
            STORE["attendance"].pop(k, None)


def test_a_project_with_no_site_gets_its_own_empty_state(client):
    """
    ⚠ **The trap this guards is `"" == ""`.** An unmapped marking stores
    `site_address_id: ""` and so does a project with no site linked, so a plain
    equality join would put **every unmapped marking in the database** onto
    **every unlinked project's page**.
    """
    STORE.setdefault("attendance", {})["orphan-1"] = {
        "id": "orphan-1", "date": DAY, "employee_id": "x",
        "employee_name": "Nobody", "employee_code": "SF-999",
        "day_rate": 900.0, "site": "Banglore", "site_address_id": "",
        "site_source": "unmapped", "status": "present", "ot_hours": 0.0}
    pid = "proj-sl-3"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "No Site", "client": "C",
        "site_address": "", "site_address_id": ""}
    try:
        html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
        assert "This project has no site linked" in html
        assert "Nobody" not in html, (
            "an unmapped marking was joined to an unlinked project — the two "
            "share an empty string and nothing else")
        assert "Edit Project" in html, "the empty state must offer the fix"
    finally:
        STORE["projects"].pop(pid, None)
        STORE["attendance"].pop("orphan-1", None)


def test_a_linked_site_with_no_markings_says_so_plainly(client):
    """The other empty state, and it must not be the same sentence as the first."""
    aid = "addr-sl-4"
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": "Hinjewadi Project Site", "type": "site"}
    pid = "proj-sl-4"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Quiet", "client": "C",
        "site_address": "Hinjewadi Project Site", "site_address_id": aid}
    try:
        html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
        assert "No attendance has been marked at this site" in html
        assert "This project has no site linked" not in html, (
            "a site with no markings is not a project with no site — the two "
            "need different answers and only one of them has a fix")
    finally:
        STORE["projects"].pop(pid, None)
        STORE["addresses"].pop(aid, None)


@pytest.mark.parametrize("slug", WALLED_OFF)
def test_the_labour_section_is_withheld_from_the_roles_B4_walls_off(client, slug):
    """
    ⚠ **THE ACCESS DEFECT THIS SECTION COULD EASILY HAVE SHIPPED.**

    `/projects/view/<id>` is gated on `project.view`, which Sales Manager,
    Purchase Manager and Accountant **all hold**. `attendance.*` is Owner,
    Director and HR only, and that is SPEC-TRACED to CC-2 **B4**: *"HR
    information is restricted from Sales, Purchase and Accounts."*

    So a labour panel rendered under `project.view` alone would hand those three
    roles the day rates and wages B4 exists to keep from them — through a page
    they are perfectly entitled to read, and with `/attendance/` still correctly
    refusing them. The registry cannot say "this panel needs a second
    permission" (ABOUT.md §7 gap 24), so it is a per-view check and this is what
    holds it.
    """
    aid = _site("Whitefield")
    pid = "proj-sl-wall"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Walled", "client": "C",
        "site_address": "Whitefield", "site_address_id": aid}
    STORE.setdefault("attendance", {})["w-1"] = {
        "id": "w-1", "date": DAY, "employee_id": "e1",
        "employee_name": "Ramesh Patil", "employee_code": "SF-014",
        "day_rate": 1234.0, "site": "Whitefield", "site_address_id": aid,
        "site_source": "book", "status": "present", "ot_hours": 0.0}
    try:
        _as(client, _user_with(slug))
        r = client.get(f"/projects/view/{pid}")
        assert r.status_code == 200, (
            f"{slug} holds project.view and must still be able to read the page")
        html = r.get_data(as_text=True)

        assert "1,234" not in html, (
            f"{slug} can read a day rate off the project page. B4 walls that "
            f"role off from HR information and /attendance/ refuses it — this "
            f"panel must not be the way round.")
        assert "Ramesh Patil" not in html, f"{slug} can read the muster"
        assert "attendance.view" in html, (
            "the panel must say it is withheld rather than silently vanish — a "
            "page that describes the project differently depending on who is "
            "looking, with nothing saying so, is worse than one that refuses")
    finally:
        STORE["projects"].pop(pid, None)
        STORE["attendance"].pop("w-1", None)


def test_the_withholding_guard_is_not_vacuous(client):
    """
    ⚠ **Mutation proof for the test above.** The control: an Owner holds
    `attendance.view` and must see the very figure the three roles must not, or
    the test above would pass on a panel that renders for nobody.
    """
    aid = _site("Whitefield")
    pid = "proj-sl-owner"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Open", "client": "C",
        "site_address": "Whitefield", "site_address_id": aid}
    STORE.setdefault("attendance", {})["o-1"] = {
        "id": "o-1", "date": DAY, "employee_id": "e1",
        "employee_name": "Ramesh Patil", "employee_code": "SF-014",
        "day_rate": 1234.0, "site": "Whitefield", "site_address_id": aid,
        "site_source": "book", "status": "present", "ot_hours": 0.0}
    try:
        html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
        assert "1,234" in html, (
            "the Owner cannot see the panel either — the guard above is "
            "passing because nothing renders, which proves nothing")
        assert "Ramesh Patil" in html
        assert "attendance.view" not in html
    finally:
        STORE["projects"].pop(pid, None)
        STORE["attendance"].pop("o-1", None)


def test_a_refused_marking_is_excluded_from_the_sum_and_the_page_says_so(client):
    """
    ⚠ **A total quietly short by an unknown amount looks exactly like a complete
    one.** `/attendance/` states its own shortfall for that reason; so does this.
    """
    aid = "addr-sl-5"
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": "Whitefield", "type": "site"}
    pid = "proj-sl-5"
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Mixed", "client": "C",
        "site_address": "Whitefield", "site_address_id": aid}
    STORE.setdefault("attendance", {}).update({
        "ok-1": {"id": "ok-1", "date": DAY, "employee_id": "e1",
                 "employee_name": "Paid", "employee_code": "SF-001",
                 "day_rate": 1000.0, "site": "Whitefield",
                 "site_address_id": aid, "site_source": "book",
                 "status": "present", "ot_hours": 0.0},
        "old-1": {"id": "old-1", "date": DAY, "employee_id": "e2",
                  "employee_name": "Unpriced", "employee_code": "SF-002",
                  "monthly_salary": 26000.0,
                  EMP.RATE_MODEL_FIELD: EMP.PRE_DAY_RATE,
                  "site": "Whitefield", "site_address_id": aid,
                  "site_source": "book", "status": "present", "ot_hours": 0.0},
    })
    try:
        html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
        assert "Unpriced" in html, "a refused marking stays in the head count"
        assert "day rate not confirmed" in html
        assert "1 marking is not costed above" in html
        assert "The total is short by that marking" in html
        # the sum is the ONE confirmed marking, not two and not zero
        # the LAST total row on the page is the labour panel's — anchor on the
        # attribute, not the bare word, which also appears in the stylesheet
        total = html[html.rindex('class="total-row"'):]
        total = total[:total.index("</tr>")]
        assert "1,000" in total, f"the sum took the refused marking in: {total!r}"
    finally:
        STORE["projects"].pop(pid, None)
        STORE["addresses"].pop(aid, None)
        for k in ("ok-1", "old-1"):
            STORE["attendance"].pop(k, None)


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


# ══ 7. ⚠ A MARKING SAYS WHICH PROJECT IT IS FOR ═══════════════════════════
#
# Added 30 August 2026 under the **SIXTH** override block of that date. ⚠ **Not
# CC-2 scope** — C5's five bullets name no project — and it belongs to
# PROGRESS.md §4c. C6 stays BLOCKED on Open question 4; attributing a day is not
# costing a project, and nothing below computes a margin, a total or a net.
#
# The four rules under test, all owned by `attendance.resolve_project()`:
#
#   exactly one project on the site  -> preselected, no extra decision
#   more than one                    -> A CHOICE IS REQUIRED to save
#   none                             -> blank, and it saves fine
#   a project at another site        -> DROPPED, never stored
#
# ⚠ Every guard below ships its **control** in the same test. A refusal test
#   with no control passes just as well when nothing is ever stored at all,
#   which is the way this class of test lies.

def _project(pid, name, site_id):
    """A project in the shared collection. The caller pops it — `_clean()`
    deliberately does not clear `projects`, and the try/finally shape here is
    `test_the_labour_section_names_every_other_project_on_the_same_site`'s."""
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": name, "norm_name": name.lower(),
        "client": "", "notes": "", "site_address_id": site_id,
        "site_address": "", "created_at": "", "updated_at": "",
    }
    return STORE["projects"][pid]


def test_projects_on_site_refuses_a_blank_id():
    """
    ⚠ **The guard `markings_at_site()` already carries, one function along, and
    it matters more here.** A project with no site linked stores
    `site_address_id: ""` and so does an unmapped marking. A plain `==` would
    offer **every unlinked project in the database** as a candidate for **every
    unmapped marking** — a join between two records that share only the fact
    that neither was ever filled in.
    """
    site = _site("Blank Guard Site")
    _project("blank-guard-none", "No Site At All", "")
    try:
        # The control: the guard is not passing because the collection is empty.
        _project("blank-guard-real", "Real One", site)
        assert [p["id"] for p in AT.projects_on_site(site)] == ["blank-guard-real"]

        assert AT.projects_on_site("") == []
        assert AT.projects_on_site(None) == []
        assert AT.projects_on_site("   ") == []
    finally:
        STORE["projects"].pop("blank-guard-none", None)
        STORE["projects"].pop("blank-guard-real", None)


def test_markings_for_project_refuses_a_blank_id(client):
    """
    Same guard from the other side, and here it is load-bearing twice: a legacy
    marking carries no `project_id`, so an empty id matching an empty field
    would hand **every unattributed marking in the database** to any caller that
    lost track of its own id.
    """
    site = _site("For Project Site")
    _project("mfp-1", "Attributed", site)
    try:
        person = _person(client)
        _mark(client, person, site_id=site, project_id="mfp-1")

        # The control: it does find the marking when asked properly.
        assert len(AT.markings_for_project("mfp-1")) == 1

        assert AT.markings_for_project("") == []
        assert AT.markings_for_project(None) == []
    finally:
        STORE["projects"].pop("mfp-1", None)


def test_the_picker_offers_only_the_projects_at_the_chosen_site(client):
    """
    ⚠ **The filter is the feature.** A marking may not name a project somewhere
    else, so the control may not offer one — and the control and the validator
    have to agree, which is why both are exercised in this section.
    """
    here, elsewhere = _site("Picker Here"), _site("Picker Elsewhere")
    _project("pick-a", "Alpha Here", here)
    _project("pick-b", "Beta Here", here)
    _project("pick-z", "Zulu Elsewhere", elsewhere)
    try:
        person = _person(client, site_id=here)
        _mark(client, person, site_id=here, project_id="pick-a")
        rid = list(STORE["attendance"].values())[-1]["id"]

        html = client.get(f"/attendance/edit/{rid}").get_data(as_text=True)
        picker = html[html.index('<select id="project_id"'):]
        picker = picker[:picker.index("</select>")]

        assert "Alpha Here" in picker and "Beta Here" in picker
        assert "Zulu Elsewhere" not in picker, (
            "the picker offered a project from another site — the one thing "
            "the filter exists to prevent")
    finally:
        for pid in ("pick-a", "pick-b", "pick-z"):
            STORE["projects"].pop(pid, None)


def test_one_project_on_the_site_is_preselected(client):
    """
    The operator should not have to make a decision that has only one answer.
    ⚠ **The control is the several-projects case below:** preselecting is only
    defensible while it never happens where a real choice exists.
    """
    site = _site("Lone Project Site")
    _project("lone-1", "The Only One", site)
    try:
        person = _person(client, site_id=site)
        _mark(client, person, site_id=site, project_id="lone-1")
        rid = list(STORE["attendance"].values())[-1]["id"]
        html = client.get(f"/attendance/edit/{rid}").get_data(as_text=True)
        picker = html[html.index('<select id="project_id"'):]
        picker = picker[:picker.index("</select>")]

        assert '<option value="lone-1" selected>' in picker, (
            "a site carrying exactly one project must preselect it")
        assert "\u2014 none \u2014" in picker, (
            "the placeholder must say that leaving it is a real option")
    finally:
        STORE["projects"].pop("lone-1", None)


def test_several_projects_on_the_site_require_a_choice(client):
    """
    ⚠ **THE POINT OF THE WHOLE CHANGE.** `'Bangalore, Karnataka'` carries four
    live projects. Defaulting the pick — to the first, the newest, or the one
    that looks right — would put a day's wage against a project **nobody
    chose**, silently, on the only figure this module produces.

    The control is in the same test: choosing one saves. Without it this would
    pass just as well on a route that refused everything.
    """
    site = _site("Crowded Site")
    _project("crowd-a", "Alpha", site)
    _project("crowd-b", "Bravo", site)
    try:
        person = _person(client, site_id=site)

        refused = _mark(client, person, site_id=site, project_id="")
        assert refused.status_code == 200, "a blank pick must not save"
        body = refused.get_data(as_text=True)
        assert "2 projects are recorded at this site" in body
        assert "Alpha" in body and "Bravo" in body, \
            "the refusal must NAME the candidates, not just count them"
        assert not STORE["attendance"], "nothing may be stored on a refusal"

        # ⚠ Nothing is preselected either — not the first, not the newest.
        picker = body[body.index('<select id="project_id"'):]
        picker = picker[:picker.index("</select>")]
        assert '<option value="crowd-a" selected>' not in picker
        assert '<option value="crowd-b" selected>' not in picker

        # THE CONTROL: the same post with a choice goes through.
        ok = _mark(client, person, site_id=site, project_id="crowd-b")
        assert ok.status_code == 302
        stored = list(STORE["attendance"].values())[-1]
        assert stored["project_id"] == "crowd-b"
        assert stored["project_name"] == "Bravo"
    finally:
        for pid in ("crowd-a", "crowd-b"):
            STORE["projects"].pop(pid, None)


def test_a_site_with_no_project_saves_blank(client):
    """
    An office or a store is a legitimate place to be marked and belongs to no
    project. Refusing it would make the register unusable for exactly the sites
    that never carry one.
    """
    site = _site("Head Office Store")
    person = _person(client, site_id=site)
    r = _mark(client, person, site_id=site, project_id="")
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    stored = list(STORE["attendance"].values())[-1]
    assert stored["project_id"] == ""
    assert stored["project_name"] == ""


def test_a_marking_may_not_carry_a_project_whose_site_is_not_its_own(client):
    """
    ⚠ **THE INVARIANT, PROVED BY MUTATION.** The posted `project_id` names a
    real project that sits at a **different** address. It must not reach the
    record.

    It is **dropped rather than refused**, and that is deliberate: the server
    cannot tell a re-picked site from a hand-made POST — both arrive as a
    project that is not at this address — and dropping is safe under both
    readings. What is asserted here is the property that holds either way:
    **the stored record never carries a project whose site is not its own.**

    The control is the second half: the identical post, with the project that
    *is* at that site, does store it. Without that, this test would pass on a
    route that stored no project ever.
    """
    here, elsewhere = _site("Mutation Here"), _site("Mutation Elsewhere")
    _project("mut-here", "Belongs Here", here)
    _project("mut-away", "Belongs Elsewhere", elsewhere)
    try:
        person = _person(client, site_id=here)

        # THE MUTATION: a real project id, at the wrong site.
        r = _mark(client, person, site_id=here, project_id="mut-away")
        assert r.status_code == 302
        stored = list(STORE["attendance"].values())[-1]
        assert stored["site_address_id"] == here
        assert stored["project_id"] == "", (
            "a project at another site reached the record — the invariant this "
            "field exists under is broken")
        assert stored["project_name"] == ""

        # THE CONTROL: the right project at the same site does land.
        STORE["attendance"].clear()
        r = _mark(client, person, site_id=here, project_id="mut-here")
        assert r.status_code == 302
        stored = list(STORE["attendance"].values())[-1]
        assert stored["project_id"] == "mut-here", (
            "the control failed: nothing is ever stored, so the assertion "
            "above proves nothing")
    finally:
        for pid in ("mut-here", "mut-away"):
            STORE["projects"].pop(pid, None)


def test_changing_the_site_clears_a_project_that_no_longer_belongs(client):
    """
    The edit path, which is where this actually bites: a marking booked to a
    project at site A is corrected to site B. The project cannot come with it.

    ⚠ Site B here carries **one** project, so the picker's own rule does not
    turn the correction into a refusal — the stale link simply goes.
    """
    a, b = _site("Move From"), _site("Move To")
    _project("move-a", "At A", a)
    _project("move-b", "At B", b)
    try:
        person = _person(client, site_id=a)
        _mark(client, person, site_id=a, project_id="move-a")
        rec = list(STORE["attendance"].values())[-1]
        assert rec["project_id"] == "move-a"          # the precondition

        # The browser posts the project it was showing; the site has moved.
        r = client.post(f"/attendance/edit/{rec['id']}", data={
            "date": DAY, "employee_id": person["id"], "site_id": b,
            "project_id": "move-a", "status": "present", "ot_hours": "2",
            "notes": ""})
        assert r.status_code == 302, r.get_data(as_text=True)[:600]

        assert rec["site_address_id"] == b
        assert rec["project_id"] == "", (
            "the marking kept a project belonging to the site it just left")
        assert rec["project_name"] == ""
    finally:
        for pid in ("move-a", "move-b"):
            STORE["projects"].pop(pid, None)


def test_the_project_name_is_a_snapshot_and_a_rename_does_not_restate_it(client):
    """
    Same freeze contract as `employee_name`, `employee_code`, `day_rate` and the
    site label beside it. Renaming a project next March must not restate which
    project a day in August was worked for.
    """
    site = _site("Snapshot Site")
    proj = _project("snap-1", "Original Name", site)
    try:
        person = _person(client, site_id=site)
        _mark(client, person, site_id=site, project_id="snap-1")
        stored = list(STORE["attendance"].values())[-1]
        assert stored["project_name"] == "Original Name"

        proj["name"] = "Renamed Afterwards"
        assert stored["project_name"] == "Original Name", (
            "the marking restated itself when the project was renamed")
        assert stored["project_id"] == "snap-1", "the join still resolves"
    finally:
        STORE["projects"].pop("snap-1", None)


def test_an_absent_project_id_is_legacy_and_nothing_in_the_app_backfills_it(client):
    """
    ⚠ **Absent means LEGACY, not "no project", and no third state marker is
    invented** — `project.is_legacy_site()` reading the shape rather than a mark
    is the precedent. The bulk mapping is a tool an operator runs deliberately
    (`tools/backfill_marking_projects.py`), and **nothing on a render path may
    write one**.
    """
    site = _site("Legacy Site")
    _project("legacy-1", "The Only Project", site)
    try:
        person = _person(client, site_id=site)
        _mark(client, person, site_id=site, project_id="")
        rec = list(STORE["attendance"].values())[-1]
        rec.pop("project_id", None)           # a marking written before the field
        rec.pop("project_name", None)

        # Every page that reads a marking, hit in turn. None may write one.
        client.get("/attendance/")
        client.get(f"/attendance/edit/{rec['id']}")
        client.get("/")
        assert "project_id" not in rec, (
            "a render path backfilled project_id — that is a migration, and a "
            "migration is a tool somebody runs on purpose")

        assert rec in AT.unattributed_at_site(site)
        assert AT.markings_for_project("legacy-1") == []
    finally:
        STORE["projects"].pop("legacy-1", None)


def test_the_forms_project_json_cannot_close_the_script_block(client):
    """
    ABOUT.md §7.9e: `json.dumps` does not escape `<`, so a project named with
    the seven characters that close a script element would end the block and
    every byte after it would be parsed as HTML. A project name is free text
    somebody typed, which is exactly the input that rule exists for.
    """
    site = _site("Injection Site")
    payload = "Tower </" + "script><img src=x onerror=alert(1)>"
    _project("inj-1", payload, site)
    try:
        _person(client, site_id=site)
        html = client.get("/attendance/mark").get_data(as_text=True)
        script = html[html.index("var BY_SITE ="):]
        script = script[:script.index("</" + "script>")]
        assert "</" + "script>" not in script
        assert "\\u003c/script\\u003e" in script, (
            "the payload must arrive escaped, not stripped — stripping would "
            "change the data as well as its spelling")
    finally:
        STORE["projects"].pop("inj-1", None)


def test_the_project_link_is_read_without_importing_the_project_module():
    """
    ⚠ **`charge.py`'s arrangement, copied rather than re-invented.** That ledger
    stores `project_id` beside a snapshotted `project_name` and reaches
    `STORE["projects"]` directly; `test_import_directions.py` refuses
    `charge -> project` with the reason *"a charge reads STORE['projects']
    directly"* and refuses this module's arrow on the same terms.

    Importing the module would buy one name lookup and would pull `address.py` —
    and through it `product.py`'s stylesheet — into the import graph of the
    muster.
    """
    tree = ast.parse((REPO / "attendance.py").read_text(encoding="utf8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            assert "project" not in [mod] + names, (
                "attendance.py imports project.py — read STORE['projects'] "
                "directly, the way charge.py does")

    # The control: it really does reach the collection, so the assertion above
    # is not passing because the link was never built.
    src = (REPO / "attendance.py").read_text(encoding="utf8")
    assert '"projects"' in src


def test_the_project_field_is_charge_pys_shape_and_not_a_second_one():
    """
    Two keys, named the same two things, meaning the same two things. A second
    spelling of one pattern is how `docsheet.py`'s four letterheads drifted.
    """
    site = _site("Shape Site")
    _project("shape-1", "Shapely", site)
    try:
        fields, err = AT.resolve_project({"project_id": "shape-1"}, site)
        assert not err
        assert set(fields) == {"project_id", "project_name"}, (
            "the marking's project keys must be exactly charge.py's two")
        assert fields == {"project_id": "shape-1", "project_name": "Shapely"}
    finally:
        STORE["projects"].pop("shape-1", None)
