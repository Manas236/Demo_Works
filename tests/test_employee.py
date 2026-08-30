"""
The employee master — CLIENT_CHANGES-2.md **C4**.

Built under the **29 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md` §0,
which gated it until then. C4 reads, in full: *"Employee details and salary."*
That is the entire specification and this is the entire feature.

### What this file pins, and in what order

1. **The routes work** — register, create, view, edit, delete.
2. **Delete confirms on GET and destroys only on POST.** `9d060ee`'s shape, and
   this repo's standing rule: a browser `confirm()` is not a guard, because a
   link-prefetching browser, a crawler, a mail scanner unfurling a pasted URL
   and the back button all issue a plain GET. `test_delete_methods.py` walks the
   URL map and catches a GET-*only* delete route; it explicitly **cannot** catch
   one that accepts both and still destroys on GET, so a new delete route has to
   ship its own GET test. This is that test.
3. **A deactivated employee is excluded where active is required.**
4. **Every new endpoint is classified**, or `auth._gate()` refuses it — absence
   refuses, by design.
5. **Sales, Purchase and Accounts are refused on every employee route, by
   direct URL hit; HR is admitted.** ⚠ This is the one part of the access grid
   that is **spec-traced rather than derived**: CLIENT_CHANGES-2.md **B4**
   states exactly one per-role restriction — *"HR information is restricted
   from Sales, Purchase and Accounts"* — and a register carrying every
   employee's salary is that information.

### What C4 is NOT, asserted rather than described

No attendance, no overtime, no salary calculation, and no link to charges,
projects or a P&L. Those are C5 and C6 and both are gated. The last section of
this file asserts the absence, because "we did not build the gated item" is a
claim worth being able to check.
"""

import pytest

import auth
import employee as EM
from store import STORE


EMPLOYEE_ROUTES = [
    "/employee/",
    "/employee/new",
    "/employee/view/{id}",
    "/employee/edit/{id}",
    "/employee/delete/{id}",
]

# B4's wall, from the far side. These three roles must be refused everywhere.
WALLED_OFF = ("sales-manager", "purchase-manager", "accountant")


def _add(client, **over):
    """Add somebody through the real route and return the stored record."""
    # ⚠ `day_rate` since 30 August 2026. The old line was, verbatim:
    #       "monthly_salary": "24000", "notes": "", "active": "1",
    #   The field carries a DAY rate now — CC-2's `salary` always was one — so
    #   the figure is a day's ₹1,200 rather than a month's ₹24,000. No
    #   arithmetic anywhere converts one to the other, deliberately.
    data = {
        "name": "Ramesh Patil", "code": "SF-014", "designation": "Fitter",
        "site": "Whitefield", "date_joined": "2026-04-01",
        "day_rate": "1200", "notes": "", "active": "1",
    }
    data.update(over)
    # A caller passing active=None means "leave the box unticked", which is what
    # a browser actually posts for an unchecked box: nothing at all.
    if data.get("active") is None:
        data.pop("active")
    r = client.post("/employee/new", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    return list(STORE["employees"].values())[-1]


def _user_with(slug: str) -> dict:
    """A fresh user holding exactly one builtin role."""
    auth.ensure_builtin_roles()
    name = f"emp-test-{slug}"
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="employee-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


@pytest.fixture(autouse=True)
def _clean():
    """
    `conftest._fresh_store()` clears six collections and `employees` is not one
    of them, so this file cleans up after itself. A leaked employee record reads
    exactly like a seeder to `test_hardening.py`.
    """
    STORE.setdefault("employees", {}).clear()
    yield
    STORE.setdefault("employees", {}).clear()


# ══ 1. The register renders ═══════════════════════════════════════════════

def test_the_register_renders_empty(client):
    r = client.get("/employee/")
    assert r.status_code == 200
    assert "Nobody on the register yet" in r.get_data(as_text=True)


def test_the_register_renders_a_person(client):
    _add(client)
    html = client.get("/employee/").get_data(as_text=True)
    assert "Ramesh Patil" in html
    assert "SF-014" in html
    assert "Fitter" in html


# ══ 2. Create round-trips ═════════════════════════════════════════════════

def test_create_round_trips(client):
    e = _add(client)
    assert e["name"] == "Ramesh Patil"
    assert e["code"] == "SF-014"
    assert e["designation"] == "Fitter"
    assert e["site"] == "Whitefield"
    assert e["date_joined"] == "2026-04-01"
    # ⚠ The old line was, verbatim:  assert e["monthly_salary"] == 24000.0
    assert e["day_rate"] == 1200.0
    assert "monthly_salary" not in e, (
        "a record written today carries a monthly figure — the create route "
        "is still on the old model, and tests/test_day_rate_pin.py says why "
        "that matters")
    assert e["active"] is True

    html = client.get(f"/employee/view/{e['id']}").get_data(as_text=True)
    assert "Ramesh Patil" in html
    assert "Whitefield" in html


def test_a_name_is_required(client):
    r = client.post("/employee/new", data={"name": "", "day_rate": "100"})
    assert r.status_code == 200, "a rejected form re-renders rather than redirecting"
    assert "name is required" in r.get_data(as_text=True).lower()
    assert not STORE["employees"], "nothing may be written on a refused POST"


def test_a_rate_of_zero_is_allowed(client):
    """
    A proprietor or a family member drawing nothing is real, and refusing it
    would force somebody to invent a figure on a wage register.

    ⚠ Renamed from `test_a_salary_of_zero_is_allowed`; its body was, verbatim:

        e = _add(client, monthly_salary="")
        assert e["monthly_salary"] == 0.0

    The rule is untouched — only the field it applies to has been renamed. The
    ONE place a blank is now refused is a record still carrying the old-model
    marker, and `tests/test_day_rate_pin.py` holds both halves of that.
    """
    e = _add(client, day_rate="")
    assert e["day_rate"] == 0.0


def test_a_negative_rate_is_refused(client):
    # ⚠ The old two lines were, verbatim:
    #       r = client.post("/employee/new", data={"name": "X", "monthly_salary": "-1"})
    #       assert "cannot be negative" in r.get_data(as_text=True)
    r = client.post("/employee/new", data={"name": "X", "day_rate": "-1"})
    assert r.status_code == 200
    assert "cannot be negative" in r.get_data(as_text=True)
    assert not STORE["employees"]


def test_a_rate_the_size_of_a_MONTHLY_salary_is_refused(client):
    """
    ⚠ **The guard moved with the unit and had to.** `MAX_MONTHLY_SALARY` was
    ₹10,00,000 — sized for a month, so on a day rate it caught almost nothing
    and a figure with two stray zeros walked through. `MAX_DAY_RATE` is
    ₹1,00,000, which still refuses nothing any site wage will ever be, and it
    catches the specific mistake this rename invites: typing the monthly salary
    into a box that now means a day.

    ⚠ **The number is OURS.** CC-2 gives no ceiling of any kind.
    """
    r = client.post("/employee/new", data={"name": "X", "day_rate": "240000"})
    assert r.status_code == 200
    assert "ONE DAY" in r.get_data(as_text=True), (
        "the refusal must say the box means one day, or the person typing a "
        "monthly figure has no idea what they got wrong")
    assert not STORE["employees"]


def test_a_duplicate_employee_code_is_refused(client):
    """
    A code is how a person is identified on a muster or a wage sheet, so two
    people holding one is the same defect as two customers sharing an invoice
    number. Compared case-insensitively: `SF-01` and `sf-01` are one code.
    """
    _add(client)
    r = client.post("/employee/new", data={
        "name": "Someone Else", "code": "sf-014", "day_rate": "1000"})
    assert r.status_code == 200
    assert "already used" in r.get_data(as_text=True)
    assert len(STORE["employees"]) == 1


def test_a_rejected_form_keeps_what_was_typed(client):
    _add(client)
    r = client.post("/employee/new", data={
        "name": "Someone Else", "code": "SF-014", "day_rate": "1000"})
    assert "Someone Else" in r.get_data(as_text=True)


# ══ 3. Edit round-trips ═══════════════════════════════════════════════════

def test_edit_round_trips(client):
    e = _add(client)
    r = client.post(f"/employee/edit/{e['id']}", data={
        "name": "Ramesh V. Patil", "code": "SF-014",
        "designation": "Site Supervisor", "site": "Hebbal",
        "date_joined": "2026-04-01", "day_rate": "1550",
        "notes": "promoted", "active": "1"})
    assert r.status_code == 302

    e = STORE["employees"][e["id"]]
    assert e["name"] == "Ramesh V. Patil"
    assert e["designation"] == "Site Supervisor"
    assert e["site"] == "Hebbal"
    # ⚠ The old line was, verbatim:  assert e["monthly_salary"] == 31000.0
    assert e["day_rate"] == 1550.0
    assert e["notes"] == "promoted"


def test_the_edit_form_is_prefilled(client):
    e = _add(client)
    html = client.get(f"/employee/edit/{e['id']}").get_data(as_text=True)
    assert 'value="Ramesh Patil"' in html
    # ⚠ The old line was, verbatim:  assert 'value="24000.00"' in html
    assert 'value="1200.00"' in html


def test_an_employee_may_keep_its_own_code_on_edit(client):
    """The uniqueness check must not refuse a record for clashing with itself."""
    e = _add(client)
    r = client.post(f"/employee/edit/{e['id']}", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "1200",
        "active": "1"})
    assert r.status_code == 302


def test_a_missing_employee_redirects_rather_than_500ing(client):
    for url in ("/employee/view/nope", "/employee/edit/nope",
                "/employee/delete/nope"):
        r = client.get(url)
        assert r.status_code == 302, url


# ══ 4. Delete — GET confirms, POST destroys ═══════════════════════════════

def test_get_on_employee_delete_destroys_nothing(client):
    """
    ⚠ **The rule this repo holds everywhere.** A browser `confirm()` is not a
      guard: a link-prefetching browser, a crawler, a mail scanner unfurling a
      pasted URL and the back button all issue a plain GET.

    `test_delete_methods.py::test_no_registered_route_destroys_on_get` walks the
    URL map and would catch a GET-only delete route, but it says in terms that
    it **cannot** catch a route accepting both methods that still destroys on
    GET. This is the hand-written half for this route.
    """
    e = _add(client)
    before = dict(STORE["employees"])

    r = client.get(f"/employee/delete/{e['id']}")

    assert r.status_code == 200, "the GET must render a page, not redirect"
    assert STORE["employees"] == before
    assert e["id"] in STORE["employees"]

    html = r.get_data(as_text=True)
    assert "cannot be undone" in html
    assert 'method="POST"' in html


def test_post_on_employee_delete_destroys(client):
    e = _add(client)
    r = client.post(f"/employee/delete/{e['id']}")
    assert r.status_code == 302
    assert e["id"] not in STORE["employees"]


def test_the_delete_page_offers_deactivating_instead(client):
    """
    Somebody who has left is not a mistake to erase — deleting removes the
    record of what they were paid. The confirmation says so and offers the
    other door.
    """
    e = _add(client)
    html = client.get(f"/employee/delete/{e['id']}").get_data(as_text=True)
    assert "deactivate" in html.lower()


# ══ 5. Active / inactive ══════════════════════════════════════════════════

def test_a_deactivated_employee_is_excluded_where_active_is_required(client):
    """
    `active_employees()` is the one accessor anything downstream should use.
    The record stays — what somebody was paid does not stop being true when
    they leave — but they are not somebody you can assign work to.
    """
    keep = _add(client)
    gone = _add(client, name="Left Last Month", code="SF-015", active=None)

    assert gone["active"] is False
    assert gone["id"] in STORE["employees"], "the record must NOT be deleted"

    names = [e["name"] for e in EM.active_employees()]
    assert "Ramesh Patil" in names
    assert "Left Last Month" not in names
    assert len(EM.active_employees()) == 1
    assert keep["id"] in STORE["employees"]


def test_the_register_hides_inactive_by_default_and_can_show_them(client):
    _add(client)
    _add(client, name="Left Last Month", code="SF-015", active=None)

    default = client.get("/employee/").get_data(as_text=True)
    assert "Ramesh Patil" in default
    assert "Left Last Month" not in default

    every = client.get("/employee/?all=1").get_data(as_text=True)
    assert "Left Last Month" in every
    assert "Inactive" in every


def test_deactivating_through_the_edit_form_keeps_the_record(client):
    e = _add(client)
    r = client.post(f"/employee/edit/{e['id']}", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "1200"})
    assert r.status_code == 302
    assert STORE["employees"][e["id"]]["active"] is False
    # ⚠ The old line was, verbatim:
    #       assert STORE["employees"][e["id"]]["monthly_salary"] == 24000.0
    assert STORE["employees"][e["id"]]["day_rate"] == 1200.0


# ══ 6. Every endpoint is classified ═══════════════════════════════════════

def test_every_employee_endpoint_is_classified():
    """
    An endpoint absent from `ROUTE_PERMISSIONS` is refused to **everybody**,
    Owner included. That is the design, and it means a route added without a
    classification is unreachable rather than open.
    """
    expected = {
        "employee.list_employees":  "employee.view",
        "employee.view_employee":   "employee.view",
        "employee.new_employee":    "employee.create",
        "employee.edit_employee":   "employee.edit",
        "employee.delete_employee": "employee.delete",
    }
    for endpoint, perm in expected.items():
        assert auth.ROUTE_PERMISSIONS.get(endpoint) == perm, endpoint


def test_the_four_permissions_were_minted():
    for pid in ("employee.view", "employee.create", "employee.edit",
                "employee.delete"):
        assert pid in auth.PERMISSIONS
        assert auth.PERMISSIONS[pid][1] == "Employee costs"


# ══ 7. B4's wall — spec-traced, not derived ═══════════════════════════════

@pytest.mark.parametrize("slug", WALLED_OFF)
def test_sales_purchase_and_accounts_are_refused_on_every_employee_route(
        client, slug):
    """
    ⚠ **CLIENT_CHANGES-2.md B4, applied literally:** *"HR information is
      restricted from Sales, Purchase and Accounts."* An employee master
      carrying salary is that information in its plainest form.

    Hit by **direct URL**, not by checking that a card is hidden. Hiding is
    presentation; the gate is the gate, and a role that cannot see a link can
    still type one.
    """
    e = _add(client)                       # created as the signed-in Owner
    _as(client, _user_with(slug))

    for route in EMPLOYEE_ROUTES:
        url = route.format(id=e["id"])
        r = client.get(url)
        assert r.status_code in (302, 403), (
            f"{slug} reached {url} — B4 keeps employee information from "
            f"Sales, Purchase and Accounts")


@pytest.mark.parametrize("slug", WALLED_OFF)
def test_the_walled_off_roles_cannot_POST_either(client, slug):
    """
    The write half. A gate checked only on GET would leave the POST open to
    anybody who kept the URL.
    """
    e = _add(client)
    _as(client, _user_with(slug))

    assert client.post("/employee/new", data={"name": "X"}).status_code in (302, 403)
    assert client.post(f"/employee/edit/{e['id']}",
                       data={"name": "X"}).status_code in (302, 403)
    assert client.post(f"/employee/delete/{e['id']}").status_code in (302, 403)
    assert e["id"] in STORE["employees"], "a refused POST must destroy nothing"


def test_hr_is_admitted_everywhere(client):
    """
    The other side of the same sentence. HR is the role the employee master
    exists for; a wall that also refused HR would be a wall around nothing.
    """
    e = _add(client)
    _as(client, _user_with("hr"))

    for route in EMPLOYEE_ROUTES:
        url = route.format(id=e["id"])
        r = client.get(url)
        assert r.status_code == 200, f"HR was refused {url}"


def test_hr_can_actually_add_and_edit(client):
    _as(client, _user_with("hr"))
    r = client.post("/employee/new", data={
        "name": "Added By HR", "code": "SF-020", "day_rate": "900",
        "active": "1"})
    assert r.status_code == 302
    e = list(STORE["employees"].values())[-1]
    assert e["name"] == "Added By HR"

    r = client.post(f"/employee/edit/{e['id']}", data={
        "name": "Added By HR", "code": "SF-020", "day_rate": "950",
        "active": "1"})
    assert r.status_code == 302
    # ⚠ The old line was, verbatim:
    #       assert STORE["employees"][e["id"]]["monthly_salary"] == 19000.0
    assert STORE["employees"][e["id"]]["day_rate"] == 950.0


def test_owner_and_director_hold_all_four(client):
    for slug in ("owner", "director"):
        perms = set(auth.BUILTIN_ROLES[slug][1])
        for pid in ("employee.view", "employee.create", "employee.edit",
                    "employee.delete"):
            assert pid in perms, f"{slug} must hold {pid}"


def test_the_walled_off_roles_hold_none_of_the_four():
    for slug in WALLED_OFF:
        perms = set(auth.BUILTIN_ROLES[slug][1])
        for pid in ("employee.view", "employee.create", "employee.edit",
                    "employee.delete"):
            assert pid not in perms, f"{slug} must not hold {pid} — B4"


# ══ 8. The nav link and the dashboard card — ARRIVED ══════════════════════
#
# ⚠ **A test stood here and it told this pass to delete it. It has been
#   deleted, exactly as instructed and in the commit that adds the link**, and
#   it is recorded here rather than removed without trace. It read:
#
#       def test_there_is_no_nav_link_and_no_dashboard_card(client):
#           """
#           ⚠ **DELIBERATE, and this test is what stops it being "fixed" by
#           accident.**
#
#           `dashboard._nav()` is embedded in **every printed page** and hidden
#           by CSS, so one more nav entry moves **every print golden in the
#           repo**. That has bitten this repo twice. `charge.py` shipped with no
#           nav link for exactly this reason and is the precedent.
#
#           The page is reachable at `/employee/`, which the tests above prove.
#           Adding the link is queued work and belongs in a pass that expects to
#           re-baseline the goldens and does nothing else — **at which point
#           delete this test in the same commit**, rather than weakening it.
#           """
#           html = client.get("/").get_data(as_text=True)
#           assert "/employee/" not in html, (
#               "an employee link appeared on the dashboard. _nav() is on every "
#               "printed page, so this moves every print golden — see the "
#               "docstring.")
#
#   The pass it named arrived on 29 August 2026 (third pass), authorised to
#   re-baseline. Five goldens moved by +248 bytes each, all of it inside
#   `<nav>`, and **nothing on any printed sheet changed** —
#   `tests/test_nav_reachability.py` holds both halves, and the per-role
#   visibility of the link is `tests/test_nav_visibility.py`'s.


def test_the_register_is_reachable_from_the_nav_and_the_launcher(client):
    """
    The replacement for the test above, asserting the opposite fact for the
    same reason: **the owner could not find a page he had paid for.**

    Both surfaces, because they fail differently — the launcher is only on `/`,
    and the nav is on every page but is the one that costs a golden.
    """
    html = client.get("/").get_data(as_text=True)
    assert html.count('href="/employee/"') >= 2, (
        "the employee master must be reachable from BOTH the nav and the "
        "dashboard launcher, not one of them")
    assert 'class="nav-link">' in html


# ══ 9. What C4 is NOT ═════════════════════════════════════════════════════

def test_c4_built_no_attendance_no_overtime_and_no_wage_calculation():
    """
    C5 and C6 are gated, and "we did not build the gated item" is a claim worth
    being able to check rather than merely assert in a comment.

    Read against the module source: a field, a route or a constant for any of
    these would be C5 started under C4's authorisation.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "employee.py").read_text(encoding="utf8")

    body = "\n".join(line for line in src.splitlines()
                     if not line.lstrip().startswith("#"))
    for gated in ("attendance", "presentee", "absentee", "overtime",
                  "ot_multiplier", "ot_hours"):
        assert f'"{gated}"' not in body and f"'{gated}'" not in body, (
            f"{gated!r} is C5, which is gated. C4 is employee details and "
            f"salary, and nothing else.")


def test_the_employee_record_is_not_linked_to_charges_or_projects(client):
    """
    C5 consumes this module later; it has not. `charge.py`'s `person` stays
    free text and is **not** a foreign key to an employee.
    """
    e = _add(client)
    assert "project_id" not in e
    assert "charge_ids" not in e

    import charge  # noqa: F401
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "charge.py").read_text(encoding="utf8")
    assert "employee" not in src.split('"""', 2)[2], (
        "charge.py reached for the employee master. Linking the two is C5, "
        "which is gated.")


def test_the_employees_collection_is_registered_for_persistence():
    """
    A collection missing from `db.COLLECTIONS` is lost on restart, silently —
    the failure mode is a register that empties itself overnight.
    """
    import db
    assert "employees" in db.COLLECTIONS
    assert "employees" in STORE
