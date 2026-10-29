"""
Staff access — a login's own ALLOW and BLOCK lists (CLIENT_CHANGES.md §0
fifty-sixth block, 29 October 2026, Manas's choice B).

What this file holds:

* the resolver: roles, plus allowed, minus blocked — block wins — and an
  `admin.*` permission is never added or removed by a person's list; an
  Owner's lists are ignored altogether;
* the gate follows the resolver — an allowed page opens, a blocked one refuses;
* `/access/` never lists an Owner, a Director or the viewer, and refuses to
  edit one by URL;
* nobody allows what they do not hold — proved with a limited admin role,
  because a Director holds every non-admin permission;
* allowing a delete does not get past `auth.OWNER_ONLY`;
* every save appends to the login's own history; a switched-off permission's
  stored choice survives a save.
"""

import pytest

import auth
from store import STORE


@pytest.fixture()
def made():
    """
    Logins on the BUILT-IN role definitions. Roles live in the shared STORE
    and other files edit them, so each builtin role's permissions are put back
    to `auth.BUILTIN_ROLES` for the test and restored after it.
    """
    import copy
    auth.ensure_builtin_roles()
    saved = copy.deepcopy(STORE["roles"])
    for slug, (_name, perms) in auth.BUILTIN_ROLES.items():
        STORE["roles"][f"role-{slug}"]["permissions"] = list(perms)
    out = []

    def make(slug_or_roles, name=None):
        role_ids = ([f"role-{slug_or_roles}"] if isinstance(slug_or_roles, str)
                    else list(slug_or_roles))
        name = name or f"sa-{'-'.join(role_ids)}"
        old = auth.find_user(name)
        if old:
            del STORE["users"][old["id"]]
        u = auth.create_user(name, name, f"pw-{name}-12345", role_ids,
                             created_by="staff-access-test")
        out.append(u["id"])
        return u
    yield make
    for uid in out:
        STORE["users"].pop(uid, None)
    STORE["roles"].clear()
    STORE["roles"].update(saved)


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


# ── 1. the resolver ──────────────────────────────────────────────────────────

def test_allow_adds_block_removes_and_block_wins(made):
    u = made("sales-manager")
    base = auth.permissions_of(u)
    assert "purchase.view" not in base and "quotation.view" in base
    u[auth.PERM_ALLOW_FIELD] = ["purchase.view", "dc.view"]
    u[auth.PERM_DENY_FIELD] = ["quotation.view", "dc.view"]
    got = auth.permissions_of(u)
    assert "purchase.view" in got
    assert "quotation.view" not in got
    assert "dc.view" not in got, "block wins over allow"


def test_an_admin_permission_is_never_moved_by_a_persons_list(made):
    u = made("sales-manager")
    u[auth.PERM_ALLOW_FIELD] = ["admin.roles", "admin.users"]
    assert not {"admin.roles", "admin.users"} & auth.permissions_of(u)
    d = made("director")
    d[auth.PERM_DENY_FIELD] = ["admin.users"]
    assert "admin.users" in auth.permissions_of(d)


def test_an_owners_lists_are_ignored(made):
    o = made("owner")
    o[auth.PERM_DENY_FIELD] = ["ra.view", "boq.view"]
    assert {"ra.view", "boq.view"} <= auth.permissions_of(o)


def test_role_permissions_of_is_the_roles_alone(made):
    u = made("hr")
    u[auth.PERM_ALLOW_FIELD] = ["ra.view"]
    assert "ra.view" not in auth.role_permissions_of(u)
    assert "ra.view" in auth.permissions_of(u)


# ── 2. the gate follows ──────────────────────────────────────────────────────

def test_an_allowed_page_opens_and_a_blocked_one_refuses(client, made):
    u = made("hr")
    _as(client, u)
    assert client.get("/ra/").status_code == 403
    assert client.get("/attendance/").status_code == 200
    u[auth.PERM_ALLOW_FIELD] = ["ra.view"]
    u[auth.PERM_DENY_FIELD] = ["attendance.view"]
    assert client.get("/ra/").status_code == 200
    assert client.get("/attendance/").status_code == 403


def test_allowing_a_delete_does_not_pass_the_owner_gate(client, made):
    u = made("hr")
    u[auth.PERM_ALLOW_FIELD] = ["ra.delete"]
    _as(client, u)
    assert "ra.delete_ra" in auth.OWNER_ONLY
    assert client.get("/ra/delete/nope").status_code == 403


# ── 3. the page ──────────────────────────────────────────────────────────────

def test_the_page_lists_staff_only(client, made):
    me = made("director", "sa-me")
    other_dir = made("director", "sa-other-director")
    owner = made("owner", "sa-an-owner")
    hr = made("hr", "sa-hr-person")
    _as(client, me)
    page = client.get("/access/").get_data(as_text=True)
    html = page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]   # the list, not the nav chip
    assert "sa-hr-person" in html
    for hidden in ("sa-me", "sa-other-director", "sa-an-owner"):
        assert hidden not in html, hidden
    for target in (me, other_dir, owner):
        client.post(f"/access/{target['id']}", data={"p:ra.view": "block"})
        assert not target.get(auth.PERM_DENY_FIELD), "refused by URL too"
    assert hr


def test_a_director_saves_a_persons_list_and_it_is_recorded(client, made):
    d = made("director")
    s = made("sales-manager", "sa-sales")
    _as(client, d)
    r = client.post(f"/access/{s['id']}", data={
        "p:purchase.view": "allow", "p:quotation.edit": "block",
        "p:quotation.view": "role"})
    assert r.status_code == 302
    assert s[auth.PERM_ALLOW_FIELD] == ["purchase.view"]
    assert s[auth.PERM_DENY_FIELD] == ["quotation.edit"]
    hist = s[auth.ACCESS_HISTORY_FIELD]
    assert len(hist) == 1 and hist[0]["by"] == d["username"]
    client.post(f"/access/{s['id']}", data={})
    assert s[auth.PERM_ALLOW_FIELD] == [] and len(s[auth.ACCESS_HISTORY_FIELD]) == 2


def test_nobody_allows_what_they_do_not_hold(client, made):
    STORE["roles"]["role-limited-admin"] = {
        "id": "role-limited-admin", "name": "Limited admin", "builtin": False,
        "permissions": ["admin.users", "dashboard.view", "quotation.view"]}
    a = made(["role-limited-admin"], "sa-limited")
    s = made("sales-manager", "sa-sales-2")
    _as(client, a)
    # A sales manager holds more than the limited admin, so administering it
    # is refused outright — `_may_administer()` still guards this page.
    # A BLOCK needs nothing held, so only that guard can refuse this one.
    client.post(f"/access/{s['id']}", data={"p:ra.view": "block"})
    assert not s.get(auth.PERM_DENY_FIELD)
    STORE["roles"]["role-limited-admin"]["permissions"] += [
        p for p in auth.role_permissions_of(s)]
    client.post(f"/access/{s['id']}", data={"p:charge.view": "allow"})
    assert not s.get(auth.PERM_ALLOW_FIELD), "charge.view is not the actor's"
    client.post(f"/access/{s['id']}", data={"p:quotation.view": "allow"})
    assert s[auth.PERM_ALLOW_FIELD] == ["quotation.view"]


def test_a_forged_admin_allow_is_dropped(client, made):
    d = made("director")
    s = made("sales-manager", "sa-sales-3")
    _as(client, d)
    client.post(f"/access/{s['id']}", data={"p:admin.users": "allow",
                                            "p:admin.roles": "allow"})
    assert s[auth.PERM_ALLOW_FIELD] == []


def test_a_switched_off_permissions_choice_survives_a_save(client, made):
    d = made("director")
    s = made("sales-manager", "sa-sales-4")
    frozen = sorted(auth.frozen_permissions() - {
        p for p in auth.PERMISSIONS if p.startswith("admin.")})
    assert frozen, "the product module is hidden, so something is frozen"
    s[auth.PERM_DENY_FIELD] = [frozen[0]]
    _as(client, d)
    client.post(f"/access/{s['id']}", data={f"p:{frozen[0]}": "role"})
    assert s[auth.PERM_DENY_FIELD] == [frozen[0]]


def test_who_may_open_the_page(client, made):
    _as(client, made("sales-manager", "sa-sales-5"))
    assert client.get("/access/").status_code == 403
    _as(client, made("hr", "sa-hr-2"))
    assert client.get("/access/").status_code == 403
    _as(client, made("director", "sa-dir-2"))
    assert client.get("/access/").status_code == 200
