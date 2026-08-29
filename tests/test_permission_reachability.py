"""
A permission no role holds gates a page nobody can open.

The defect this exists to stop
------------------------------
`auth.ensure_builtin_roles()` never rewrites an existing role's permission list,
and that is correct — once an Owner has edited what Director means, a restart
must not undo it. The cost is that **a permission minted in a later pass never
reaches a database that already has its roles.** It exists in code, it exists on
a fresh database, and on the live one nobody holds it. `auth._gate()` has no
Owner bypass, so the page is unreachable by *everybody*.

It has shipped three times: the four `*.approve` permissions (B6), `employee.*`
and `attendance.*` (C4 / C5), and `measurement.*` (C2). The first and third were
repaired by near-identical one-offs pasted into migration scripts written for
something else; the second went unnoticed for a day, with C4 and C5 standing on
the board as BUILT while nobody could open either page.

⚠ WHY THE OBVIOUS TEST WOULD BE A LIE
--------------------------------------
The obvious test is "every id in `auth.PERMISSIONS` is held by at least one role
in `auth.BUILTIN_ROLES`". **That assertion cannot fail, ever.** The Owner role is
literally `list(_ALL_PERMS)` — every permission, by construction — so the set
difference is empty for any possible edit to `PERMISSIONS`. Committing it alone
would add a green test that asserts nothing, which is the exact shape this pass
was commissioned to sweep out of the suite.

It is kept below anyway, for one reason and with its weakness asserted rather
than merely described: `test_owner_holds_every_permission_by_construction` pins
the property that makes it vacuous. The day somebody narrows the Owner role that
test goes red, and `test_no_permission_is_orphaned_on_a_fresh_database` stops
being decoration and starts being a guard. That is a comment that cannot rot.

The tests that can actually fail today are:

* `test_every_permission_reaches_a_role_other_than_the_owner` — a permission
  wired to no working role. The fresh-database half of the defect.
* `test_role_permission_drift_is_detected_on_a_database_seeded_before_the_permission_existed`
  — the live-database half, and the one that models what actually happened three
  times: roles stored first, permission minted afterwards.
"""

import auth


# ─────────────────────────────────────────────────────────────────────────────
# Deliberate exceptions — a permission that reaches only the Owner ON PURPOSE.
#
# Each entry is a decision somebody wrote down, not a page nobody noticed. Add
# to this only with the reason in the string; an unexplained entry is how a real
# orphan gets parked here and forgotten.
# ─────────────────────────────────────────────────────────────────────────────
OWNER_ONLY_BY_DESIGN = {
    "admin.roles":
        "CLIENT_CHANGES-2.md B3 splits Owner from Admin on exactly this "
        "permission: a Director administers users but cannot alter role "
        "definitions. Granting it to a second builtin role would collapse the "
        "tier the specification draws. `auth.OWNER_PERM` is this id.",
}


def _seeded_roles() -> dict:
    """A store's worth of roles, exactly as `ensure_builtin_roles()` makes them."""
    return {
        f"role-{slug}": {
            "id": f"role-{slug}", "name": name,
            "permissions": sorted(set(perms)), "builtin": True,
        }
        for slug, (name, perms) in auth.BUILTIN_ROLES.items()
    }


# ── The property that makes the naive test vacuous ───────────────────────────

def test_owner_holds_every_permission_by_construction():
    """
    Pins WHY `test_no_permission_is_orphaned_on_a_fresh_database` cannot fail.

    If this goes red the Owner role has been narrowed, and that test has just
    become load-bearing — read it before changing anything else.
    """
    owner = set(auth.BUILTIN_ROLES["owner"][1])
    assert owner == set(auth.PERMISSIONS), (
        "The Owner role is no longer every permission. The orphan test below is "
        "no longer vacuous — it is now a real guard, and so is this one."
    )


def test_no_permission_is_orphaned_on_a_fresh_database():
    """
    Every permission reaches at least one role on a freshly seeded database.

    ⚠ Vacuous while the test above is green — see this module's docstring. It is
    here so the assertion already exists the moment the Owner stops being a
    catch-all.
    """
    orphans = auth.orphan_permissions(_seeded_roles())
    assert orphans == [], (
        f"{len(orphans)} permission(s) reach no role at all on a fresh "
        f"database: {', '.join(orphans)}"
    )


# ── The guards that can fail today ───────────────────────────────────────────

def test_every_permission_reaches_a_role_other_than_the_owner():
    """
    A permission only the Owner holds gates a page no working role can open.

    This is the fresh-database half of the defect, and it catches a permission
    minted and wired to nothing: `_ALL_PERMS` sweeps it into the Owner
    automatically, so the orphan check above stays green while the feature is
    unusable by the people whose job it is.

    An intended exception goes in `OWNER_ONLY_BY_DESIGN` **with its reason**.
    """
    holders = {}
    for slug, (_name, perms) in auth.BUILTIN_ROLES.items():
        if slug == "owner":
            continue
        for pid in perms:
            holders.setdefault(pid, []).append(slug)

    unreachable = sorted(set(auth.PERMISSIONS)
                         - set(holders)
                         - set(OWNER_ONLY_BY_DESIGN))
    assert unreachable == [], (
        f"{len(unreachable)} permission(s) reach no role but the Owner: "
        f"{', '.join(unreachable)}. Either grant one to the role whose job it "
        f"is, or add it to OWNER_ONLY_BY_DESIGN with the reason."
    )


def test_owner_only_exceptions_are_real_permissions_and_still_owner_only():
    """
    An exception that has stopped being true is a stale excuse. If a permission
    listed here has since been granted to a working role the entry must go —
    otherwise the list slowly becomes the place orphans hide.
    """
    for pid, reason in OWNER_ONLY_BY_DESIGN.items():
        assert pid in auth.PERMISSIONS, f"{pid} is not a permission any more"
        assert reason.strip(), f"{pid} is excepted with no reason given"
        others = [slug for slug, (_n, perms) in auth.BUILTIN_ROLES.items()
                  if slug != "owner" and pid in perms]
        assert others == [], (
            f"{pid} is listed as Owner-only by design but {others} now hold it. "
            f"Remove it from OWNER_ONLY_BY_DESIGN."
        )


def test_role_permission_drift_is_detected_on_a_database_seeded_before_the_permission_existed():
    """
    **The one that models what actually happened, three times.**

    Reconstruct the real conditions: a database whose roles were stored before a
    permission existed. `ensure_builtin_roles()` will not repair it — asserted
    below — so `role_permission_drift()` has to see it, or nothing does.
    """
    stored = _seeded_roles()
    # The state the live database was in on 30 August 2026: roles seeded before
    # C2 minted `measurement.*`, so not one of them carried any.
    for role in stored.values():
        role["permissions"] = [p for p in role["permissions"]
                               if not p.startswith("measurement.")]

    expected_orphans = sorted(p for p in auth.PERMISSIONS
                              if p.startswith("measurement."))
    assert expected_orphans, "C2's permissions have gone — rewrite this test"
    assert auth.orphan_permissions(stored) == expected_orphans, (
        "a permission stripped from every stored role must read as orphaned")

    drift = auth.role_permission_drift(stored)
    assert drift, "drift went undetected on a database missing measurement.*"
    for slug, (_name, perms) in auth.BUILTIN_ROLES.items():
        wanted = sorted(p for p in perms if p.startswith("measurement."))
        if wanted:
            assert drift.get(f"role-{slug}") == wanted, (
                f"role-{slug} should be reported as missing {wanted}")

    granted = auth.apply_drift(drift, stored)
    assert granted == sum(len(v) for v in drift.values())
    assert auth.orphan_permissions(stored) == []
    assert auth.role_permission_drift(stored) == {}


def test_ensure_builtin_roles_does_not_repair_drift_and_that_is_why_the_tool_exists():
    """
    Pins the limitation the whole reconciliation is built around.

    If this ever goes red because somebody made `ensure_builtin_roles()` rewrite
    existing rows, an Owner's edits at `/roles/edit/<id>` are being silently
    undone on every restart — a worse bug than the one it would be fixing.
    """
    from store import STORE

    saved = STORE.get("roles")
    STORE["roles"] = _seeded_roles()
    try:
        STORE["roles"]["role-director"]["permissions"] = ["dashboard.view"]
        made = auth.ensure_builtin_roles()
        assert made == 0, "every builtin already exists; none should be minted"
        assert STORE["roles"]["role-director"]["permissions"] == ["dashboard.view"], (
            "ensure_builtin_roles() rewrote an existing role — an Owner's own "
            "edits would now be undone on every restart"
        )
        assert "role-director" in auth.role_permission_drift(STORE["roles"])
    finally:
        if saved is None:
            STORE.pop("roles", None)
        else:
            STORE["roles"] = saved


def test_apply_drift_never_removes_a_permission_an_owner_granted():
    """
    Reconciliation is additive. An Owner who granted a role something by hand
    must still have it afterwards — otherwise the tool is a policy reset wearing
    a repair's name.

    ⚠ The role used here has to be one that **actually drifts**, and picking one
    that does not is how this test lies. An earlier draft hand-granted to
    Purchase Manager, which `BUILTIN_ROLES` gives no `measurement.*` at all — so
    it never appeared in the drift dict, `apply_drift()` never touched it, and
    the assertion passed under a deliberate mutation that replaced permission
    lists wholesale. Sales Manager is missing two permissions in the fixture
    below, so the write path is genuinely exercised.
    """
    stored = _seeded_roles()
    # Drift to repair: seeded before C2, so the two it should hold are absent.
    stored["role-sales-manager"]["permissions"] = [
        p for p in stored["role-sales-manager"]["permissions"]
        if not p.startswith("measurement.")]
    # ...and one an Owner granted by hand that the code does not give it.
    stored["role-sales-manager"]["permissions"].append("dc.view")
    stored["role-sales-manager"]["permissions"].sort()

    drift = auth.role_permission_drift(stored)
    assert drift.get("role-sales-manager"), (
        "fixture is wrong: this role must have drift or the write path below "
        "is never entered and the assertion proves nothing")

    auth.apply_drift(drift, stored)

    after = stored["role-sales-manager"]["permissions"]
    assert "dc.view" in after, (
        "reconciliation removed a permission the code does not grant — it must "
        "only ever add")
    assert "measurement.view" in after, "the drift itself was not repaired"


def test_apply_drift_refuses_a_permission_that_is_not_in_the_registry():
    """A reconciliation that can invent a permission is a privilege escalation."""
    stored = _seeded_roles()
    granted = auth.apply_drift({"role-hr": ["not.a.real.permission"]}, stored)
    assert granted == 0
    assert "not.a.real.permission" not in stored["role-hr"]["permissions"]


def test_every_permission_gates_at_least_one_route():
    """
    The mirror image: a permission that guards nothing is dead weight in the
    role editor, and a role editor full of meaningless ticks is how a real grant
    gets made by accident.
    """
    used = set(auth.ROUTE_PERMISSIONS.values()) - {auth.PUBLIC, auth.AUTHENTICATED}
    unused = sorted(set(auth.PERMISSIONS) - used)
    assert unused == [], (
        f"{len(unused)} permission(s) gate no route: {', '.join(unused)}")
    invented = sorted(used - set(auth.PERMISSIONS))
    assert invented == [], (
        f"ROUTE_PERMISSIONS names {len(invented)} permission(s) that do not "
        f"exist: {', '.join(invented)}")
