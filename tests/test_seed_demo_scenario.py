"""
`tools/seed_demo_scenario.py` — the demo set, and the two rules it lives under.

Authorised by the **FIFTH override block of 30 August 2026** in
`CLIENT_CHANGES.md` §0. Not CC-2 scope; PROGRESS.md §4c.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **NOTHING IN THE APPLICATION REACHES IT.** `employees` and `attendance`
   are transactional — a seeded employee is a person who does not exist carrying
   a salary they are not paid, and a seeded marking invents a day's labour cost.
   This is a command line an operator types, not a seeder, and the ONLY thing
   that makes that true is that no module imports it. A previous pass shipped a
   defect where the app seeded demo data as a side effect of rendering; it was
   fixed, and this is what stops it coming back.
2. ⚠ **`--purge` REMOVES EXACTLY WHAT `--write` CREATED.** Not one record more,
   not one fewer. Held by a full-STORE round trip and by **two mutations** — one
   that purges too much and one that purges too little — because a round trip
   that passes against a purge doing nothing would prove nothing.
3. **`test_hardening.py` stays green**, which it does by construction: it runs
   the app's seeders and looks for rows, and this tool is not one of them.
4. **The set does not manufacture an ambiguity the live data already has** — no
   third project sharing a site.
5. **No demo record joins a closed historical set** — no `rate_model` marker.
"""

import ast
import copy
import pathlib
import sys

import pytest

from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import seed_demo_scenario as SEED  # noqa: E402


TOUCHED = SEED.MARKED_COLLECTIONS


@pytest.fixture(autouse=True)
def _clean():
    saved = {k: copy.deepcopy(STORE.get(k) or {}) for k in TOUCHED}
    for k in TOUCHED:
        STORE.setdefault(k, {}).clear()
    yield
    for k in TOUCHED:
        STORE.setdefault(k, {}).clear()
        STORE[k].update(saved[k])


def _run(*flags):
    old = sys.argv
    sys.argv = ["seed_demo_scenario.py", *flags]
    try:
        return SEED.main()
    finally:
        sys.argv = old


def _snapshot():
    return copy.deepcopy({k: dict(STORE.get(k) or {}) for k in TOUCHED})


# ═══ 1. ⚠ IT IS NOT PART OF THE APPLICATION ════════════════════════════════

def test_nothing_in_the_application_reaches_this_tool():
    """
    ⚠ **THE ONE THAT MAKES THE REST DEFENSIBLE.**

    `employees` and `attendance` are transactional in `test_hardening.py` for
    reasons that have not changed. The only thing separating "a tool an operator
    runs" from "a seeder that invents people" is that no route, no blueprint, no
    request hook and no import reaches this file.
    """
    for path in REPO.glob("*.py"):
        src = path.read_text(encoding="utf8")
        assert "seed_demo_scenario" not in src, (
            f"{path.name} names the demo seeder. It is a command-line tool; "
            f"anything in the application reaching it makes it a seeder that "
            f"invents employees and the wages against them.")


def test_a_fresh_install_is_still_empty_of_people_and_markings(client):
    """
    `test_hardening.py`'s guarantee, restated from this file's side so that
    breaking it fails here too. Run everything the app seeds from and look.
    """
    STORE.setdefault("employees", {}).clear()
    STORE.setdefault("attendance", {}).clear()
    for u in ("/", "/product/", "/address/", "/spec/", "/boq/", "/settings/"):
        client.get(u)

    assert not STORE["employees"], "something in the app seeded an employee"
    assert not STORE["attendance"], "something in the app seeded a marking"


def test_the_writing_is_behind_an_explicit_flag():
    """
    ⚠ No write happens at import, and none happens without a flag. Asserted on
    the AST rather than by running it, because "it did not write this time" is
    not the same claim as "it cannot write without being told to".
    """
    tree = ast.parse((REPO / "tools" / "seed_demo_scenario.py")
                     .read_text(encoding="utf8"))

    # ⚠ Only statements that RUN at import. A `def` body does not run when the
    #   module is imported, and neither does the `if __name__ == "__main__"`
    #   guard — walking those would flag `main()` calling `build()`, which is
    #   the tool working correctly rather than a defect.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.If)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                assert inner.func.id not in ("build", "main"), (
                    "the tool does work at import time — importing it would "
                    "then be enough to seed")

    # And the one `if` at module level is the __main__ guard, not a condition
    # under which an import writes.
    guards = [n for n in tree.body if isinstance(n, ast.If)]
    assert len(guards) == 1, "an unexpected module-level branch"
    assert ast.dump(guards[0].test).count("__name__") == 1

    flags = {a.value for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "add_argument"
             for a in n.args
             if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    assert flags == {"--write", "--purge"}


# ═══ 2. ⚠ --purge IS EXACT ═════════════════════════════════════════════════

def test_write_then_purge_returns_the_store_to_where_it_was():
    """The round trip. Every collection, field for field."""
    STORE["addresses"]["keep-1"] = {"id": "keep-1", "label": "Real Site",
                                    "type": "site"}
    STORE["employees"]["keep-2"] = {"id": "keep-2", "name": "Real Person",
                                    "code": "SF-900", "day_rate": 1000.0,
                                    "active": True}
    before = _snapshot()

    _run("--write")
    assert STORE["employees"] != before["employees"], "nothing was written"

    _run("--purge")
    assert _snapshot() == before, "--purge did not return the store to where it was"


def test_purge_leaves_an_unmarked_record_alone_even_when_it_looks_the_same():
    """
    ⚠ **The marker is a FIELD, not a name pattern.** A record somebody wrote by
    hand that happens to share a demo employee's name and code must survive —
    which is the whole reason `--purge` tests a key rather than a string.
    """
    _run("--write")
    twin_id = "hand-written"
    demo = next(iter(SEED.marked("employees").values()))
    STORE["employees"][twin_id] = {k: v for k, v in demo.items()
                                   if k != SEED.MARKER_FIELD}
    STORE["employees"][twin_id]["id"] = twin_id

    _run("--purge")

    assert twin_id in STORE["employees"], (
        "a hand-written record with the same name and code as a demo row was "
        "purged — the marker is being read as a name pattern")
    assert not SEED.marked("employees")


def test_the_purge_exactness_guard_catches_purging_ONE_RECORD_TOO_MANY(monkeypatch):
    """
    ⚠ **Mutation 1 of 2.** Widen `marked()` by one record — the shape of a purge
    that starts matching on something looser than the marker — and the round
    trip must go red.
    """
    STORE["employees"]["keep-2"] = {"id": "keep-2", "name": "Real Person",
                                    "code": "SF-900", "day_rate": 1000.0,
                                    "active": True}
    before = _snapshot()
    _run("--write")

    real = SEED.marked

    def too_greedy(coll):
        out = dict(real(coll))
        if coll == "employees":
            out["keep-2"] = STORE["employees"]["keep-2"]
        return out

    monkeypatch.setattr(SEED, "marked", too_greedy)
    # The tool re-checks the marker at the point of deletion, so a greedy
    # `marked()` trips its own assertion rather than deleting — which IS the
    # guard. Either outcome is a catch; silently succeeding is not.
    caught = False
    try:
        _run("--purge")
    except AssertionError:
        caught = True
    monkeypatch.undo()

    if not caught:
        assert _snapshot() != before, (
            "a purge that took one record too many was not caught — the round "
            "trip cannot see the difference and is not a guard")
    else:
        assert "keep-2" in STORE["employees"], (
            "the re-check fired but the extra record had already gone")

    for c in TOUCHED:                       # leave the store clean either way
        for rid in list(SEED.marked(c)):
            del STORE[c][rid]


def test_the_purge_exactness_guard_catches_purging_ONE_RECORD_TOO_FEW(monkeypatch):
    """
    ⚠ **Mutation 2 of 2, and the one a round trip is likeliest to miss.** Drop
    one record from `marked()` — the shape of a purge that forgets a collection
    — and the round trip must still go red.
    """
    before = _snapshot()
    _run("--write")

    real = SEED.marked

    def too_shy(coll):
        out = dict(real(coll))
        if coll == "attendance" and out:
            out.pop(sorted(out)[0])
        return out

    monkeypatch.setattr(SEED, "marked", too_shy)
    _run("--purge")
    monkeypatch.undo()

    assert _snapshot() != before, (
        "a purge that left one record behind was not caught — the round trip "
        "is not comparing what it claims to")
    assert len(SEED.marked("attendance")) == 1, "the mutation did not take"

    for c in TOUCHED:
        for rid in list(SEED.marked(c)):
            del STORE[c][rid]


def test_purge_on_a_clean_database_is_a_no_op():
    before = _snapshot()
    _run("--purge")
    assert _snapshot() == before


def test_write_twice_creates_one_set():
    _run("--write")
    once = _snapshot()
    _run("--write")
    assert _snapshot() == once, "the second --write created a second set"


# ═══ 3. THE SET ITSELF ═════════════════════════════════════════════════════

def test_two_sites_one_project_each_and_no_shared_site():
    """
    ⚠ **The ambiguity is REAL on the live database and the demo must not
    manufacture a second one.** After the fifth-pass cleanup
    `'Bangalore, Karnataka'` carries four projects. A fixture that invented
    another would make a live data problem look like a demo artefact.
    """
    _run("--write")
    sites = SEED.marked("addresses")
    projects = SEED.marked("projects")

    assert len(sites) == 2
    assert len(projects) == 2

    per_site = {}
    for p in projects.values():
        per_site.setdefault(p["site_address_id"], []).append(p["name"])
    assert all(len(v) == 1 for v in per_site.values()), (
        f"the demo put more than one project on a site: {per_site}")
    assert set(per_site) == set(sites), "a project is on a site it did not create"


def test_no_demo_record_joins_the_closed_old_model_set():
    """
    ⚠ `rate_model: pre_day_rate` marks a set somebody counted and closed at the
    migration. `tests/test_day_rate_pin.py` fails if a record created after that
    moment carries it, and a demo row is created after that moment.
    """
    _run("--write")
    import employee as EMP

    for coll in ("employees", "attendance"):
        for r in SEED.marked(coll).values():
            assert EMP.RATE_MODEL_FIELD not in r, f"{coll} row carries the marker"
            assert "monthly_salary" not in r, f"{coll} row carries a MONTHLY figure"
            assert not EMP.is_pre_day_rate(r)

    for e in SEED.marked("employees").values():
        rate, ok = EMP.day_rate_of(e)
        assert ok and rate > 0, "a demo employee has no confirmed day rate"


def test_one_employee_is_marked_absent_so_the_zero_cost_path_renders():
    """CC-2 C5's second bullet — salary as 0 or 1 on attendance — made visible."""
    _run("--write")
    import attendance as AT
    import settings as S

    rows = list(SEED.marked("attendance").values())
    absent = [r for r in rows if r["status"] == "absent"]
    assert len(absent) >= 1, "nothing is marked absent — the zero path never renders"

    c = AT.cost_of(absent[0], S.ot_multiplier())
    assert c["day"] == 0.0 and c["total"] == 0.0 and not c["refused"], (
        "an absent day must cost nil, and it must be nil rather than refused")


def test_one_employee_one_site_one_day_holds_across_the_set():
    """
    ⚠ CC-2's uniqueness constraint. A demo set that broke it would put the
    register into a state the forms cannot produce, and would bill one day's
    wage twice on the only figure the module produces.
    """
    _run("--write")
    import attendance as AT

    seen = set()
    for r in SEED.marked("attendance").values():
        key = (r["employee_id"], r["date"])
        assert key not in seen, f"two markings for {key}"
        seen.add(key)
        assert not AT.conflicting_record(r["employee_id"], r["date"],
                                         except_id=r["id"])


def test_the_markings_land_on_the_project_page_of_the_site_they_share(client):
    """
    End to end, and the reason the set exists: open a demo project and the
    labour booked at its site is there.
    """
    _run("--write")
    proj = sorted(SEED.marked("projects").values(), key=lambda p: p["name"])[0]

    html = client.get(f"/projects/view/{proj['id']}").get_data(as_text=True)
    assert "Site Labour" in html
    assert proj["site_address"] in html, "the section must name the site"

    aid = proj["site_address_id"]
    expected = [r for r in SEED.marked("attendance").values()
                if r["site_address_id"] == aid]
    assert expected, "the fixture put no markings on this project's site"
    for r in expected:
        assert r["employee_name"] in html

    # ⚠ and NOT the other site's markings
    for r in SEED.marked("attendance").values():
        if r["site_address_id"] != aid:
            assert r["employee_name"] not in html, (
                "a marking from a different site appeared on this project")


def test_the_demo_projects_raise_no_ambiguity_note(client):
    """
    The other half of `test_two_sites_one_project_each_and_no_shared_site`,
    seen from the page: one project per site means no note, which is what makes
    the note meaningful where it does appear.
    """
    _run("--write")
    proj = next(iter(SEED.marked("projects").values()))
    html = client.get(f"/projects/view/{proj['id']}").get_data(as_text=True)
    assert "recorded at this same site" not in html


def test_the_day_rates_look_like_site_labour_and_are_not_round():
    """
    ⚠ Not decoration. A demo full of round ₹1,000s teaches whoever opens it that
    the figures are placeholders, and this app has already paid once for
    placeholder rates being read as real (`po_parts.py`, ABOUT.md §2h).
    """
    _run("--write")
    rates = sorted(e["day_rate"] for e in SEED.marked("employees").values())
    assert all(300 <= r <= 3000 for r in rates), (
        f"{rates} is not a plausible Indian site-labour day rate range")
    assert any(r % 100 for r in rates), "every rate is a round hundred"
