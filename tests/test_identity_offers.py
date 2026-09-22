"""
What the identity pages OFFER, and to whom.

[tests/test_privilege_escalation.py](test_privilege_escalation.py) proves every
refusal on these pages holds when the POST is forged. This file is the other
half, and it is a **usability** question rather than a security one: a control
that can only ever produce a refusal should not be drawn.

The report, 22 September 2026, from the client-facing owner: signed in as a
Director, `/users/create` offered the **Owner** role on the same checkbox list
as Sales Manager — and refused the save. Three more controls on that journey
behaved the same way, all of them found by following the report:

| Offered | Refused by | Now |
|---|---|---|
| the Owner box on `/users/create` and `/users/edit` | `_may_grant()` | not drawn |
| any role carrying a permission the admin lacks | `_may_grant()` | not drawn |
| **Edit / Deactivate / Reactivate** on an Owner's row | `_may_administer()` | no links |
| the **Roles** button beside "+ New user" | the gate (`admin.roles`) | not drawn |

⚠ **Nothing here weakens a guard, and this file asserts nothing about one.**
Hiding is presentation; the gate is the gate (ABOUT.md §2g). The two are held
together by the drawing code asking the *same* predicate the handler enforces —
`_role_checkboxes()` calls `_may_grant()` one role at a time, the register calls
`_may_administer()`, the button calls `can_reach()` — so a box that disappears
and a POST that is refused cannot drift apart. The forged POST that proves it
still lives in the escalation file, which already had the case:
`test_a_role_id_the_form_never_offered_is_still_refused`.

**Every hiding test below is paired with a control**, because a page that
rendered nothing at all, or a `/users` that 500'd, would otherwise score as a
pass on all of them.
"""

import pytest

import auth
from store import STORE


# ── People ─────────────────────────────────────────────────────────────────

def _user(name: str, role_ids: list, password: str = "") -> dict:
    """A fresh user, replacing any left by an earlier test."""
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, password or f"pw-{name}-12345", role_ids,
                            created_by="offers-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


@pytest.fixture()
def owner(client):
    """The one active Owner, and the account a Director must not touch."""
    auth.ensure_builtin_roles()
    o = _user("off-owner", ["role-owner"], "off-owner-password")
    for user in STORE["users"].values():
        if auth.is_owner(user) and user["id"] != o["id"]:
            user["active"] = False
    assert [u["id"] for u in auth.active_owners()] == [o["id"]]
    return o


@pytest.fixture()
def director(client, owner):
    """A **Director only** — not the Owner+Director `/setup` mints."""
    d = _user("off-director", ["role-director"])
    assert not auth.is_owner(d), "the reader must not already be an Owner"
    assert auth.ADMIN_PERM in auth.permissions_of(d)
    _as(client, d)
    return d


@pytest.fixture()
def junior(client):
    """Somebody the Director may legitimately administer."""
    return _user("off-junior", ["role-sales-manager"], "off-junior-password")


@pytest.fixture()
def limited_admin(client, owner):
    """
    `admin.users` and almost nothing else — the role B2 invites an Owner to
    build, and the one that makes this about more than the Owner tier.
    """
    auth.roles()["role-office-admin"] = {
        "id": "role-office-admin", "name": "Office Admin", "builtin": False,
        "permissions": ["dashboard.view", auth.ADMIN_PERM]}
    user = _user("off-limited", ["role-office-admin"])
    _as(client, user)
    yield user
    auth.roles().pop("role-office-admin", None)


def _html(client, url: str) -> str:
    response = client.get(url)
    assert response.status_code == 200, f"{url} -> {response.status_code}"
    return response.get_data(as_text=True)


# ══ 1. The role picker — the box that started this ═════════════════════════

def test_a_director_is_not_offered_the_owner_role_on_the_create_form(
        client, director):
    """The report, exactly as it was made."""
    html = _html(client, "/users/create")
    assert 'value="role-owner"' not in html, (
        "a Director was offered the Owner role on /users/create — a box that "
        "can only ever produce a refusal")


def test_an_owner_is_still_offered_the_owner_role(client, owner):
    """The control. Only an Owner can create an Owner, and they must be able to."""
    _as(client, owner)
    html = _html(client, "/users/create")
    assert 'value="role-owner"' in html, (
        "an Owner cannot create another Owner — two active Owners is an "
        "operational requirement (ABOUT.md §7.21), and this is where it is done")


def test_a_director_is_still_offered_the_roles_they_can_grant(client, director):
    """
    The control that matters most: `admin.users` must still work.

    A Director offered nothing has not been made safer, they have been locked
    out of the job the role exists for.
    """
    html = _html(client, "/users/create")
    assert 'value="role-sales-manager"' in html, (
        "a Director was offered no ordinary role — admin.users is broken")


def test_a_director_is_not_offered_the_owner_role_on_the_edit_form(
        client, director, junior):
    """The same picker, the other route."""
    html = _html(client, f"/users/edit/{junior['id']}")
    assert 'value="role-owner"' not in html, (
        "the Owner role was offered on /users/edit")
    assert 'value="role-sales-manager"' in html, (
        "the role the account already holds is not even drawn")


def test_the_hidden_box_is_still_refused_when_it_is_posted_anyway(
        client, director, junior):
    """
    Drawing and deciding are two things, and this is the seam between them.

    The id is absent from the HTML the Director was served **and** refused when
    posted regardless — one assertion of each, on the same role, in one test,
    so a change that quietly moved the guard into the markup would fail here.
    """
    assert 'value="role-owner"' not in _html(client, f"/users/edit/{junior['id']}")

    client.post(f"/users/edit/{junior['id']}",
                data={"display_name": "j",
                      "role_ids": ["role-sales-manager", "role-owner"]})

    assert not auth.is_owner(junior), (
        "hiding the box was mistaken for guarding the field")


def test_a_limited_admin_is_offered_no_role_carrying_what_it_lacks(
        client, limited_admin):
    """
    The rule is "nobody confers what they do not hold", not "no Owner box".

    An Office Admin holding `admin.users` and `dashboard.view` holds no part of
    the HR role, so that role cannot be granted — and is therefore not drawn.
    Their own role still is: its permissions are exactly theirs, which is the
    line the rule draws and the control this test carries with it.
    """
    html = _html(client, "/users/create")
    assert 'value="role-hr"' not in html, (
        "an admin was offered a role carrying permissions it does not hold")
    assert 'value="role-office-admin"' in html, (
        "an admin could not hand on the very role they hold in full")


def test_an_empty_picker_says_why_rather_than_leaving_a_gap(client):
    """
    A second floor, and unreachable for a pleasant reason.

    Whoever can open this page holds a role, and a role's own permissions are
    by definition a subset of its holder's — so their own role is always
    grantable and the picker always has at least one box. The empty branch is
    what stops a future role arrangement from rendering a caption above blank
    space, which reads as a page that failed to load rather than as a boundary.
    """
    nobody = _user("off-roleless", [])
    assert "no role you can assign" in auth._role_checkboxes([], nobody), (
        "an empty picker said nothing about why it was empty")


def test_a_held_role_the_editor_cannot_grant_is_carried_through_the_save(client):
    """
    The floor under `_may_administer()`, asserted directly on the renderer.

    Unreachable through the pages today: `/users/edit` is refused outright when
    the target holds anything its editor does not, so a drawn-but-ungrantable
    role cannot arise. It is pinned anyway because the failure mode is silent —
    a role simply omitted from the form is a role the next save **strips**, and
    nobody would see it happen. Kept for the day object-level guards (ABOUT.md
    §7 gap 24) put an editor on a form they cannot fully grant.
    """
    auth.ensure_builtin_roles()
    editor = _user("off-editor", ["role-sales-manager"])

    drawn = auth._role_checkboxes(["role-hr"], editor, held=["role-hr"])

    assert 'type="hidden" name="role_ids" value="role-hr"' in drawn, (
        "a role the account holds was dropped from the form — the next save "
        "would silently take it away")
    assert "disabled" in drawn, "it was drawn as an editable choice"


# ══ 2. The register — the same rule on a row ═══════════════════════════════

def test_a_director_is_offered_no_action_on_an_owners_row(client, director, owner):
    """
    `_may_administer()` refuses all three of these, so none of them is drawn.

    The row itself stays — who the Owners are is not a secret from an admin,
    and the Roles column already names the tier. What goes is the invitation.
    """
    html = _html(client, "/users")

    assert f'/users/edit/{owner["id"]}' not in html, (
        "an Edit link on an Owner's row — the password field on that page is "
        "what ABOUT.md §7 gap 26 was about")
    assert f'/users/deactivate/{owner["id"]}' not in html, (
        "a Deactivate link on the only Owner's row")
    assert owner["username"] in html, "the Owner's row vanished from the register"


def test_a_director_still_acts_on_an_ordinary_account(client, director, junior):
    """The control. Administering staff is the whole of `admin.users`."""
    html = _html(client, "/users")
    assert f'/users/edit/{junior["id"]}' in html, "a Director cannot edit their staff"
    assert f'/users/deactivate/{junior["id"]}' in html, (
        "a Director cannot deactivate their staff — the one control B3 calls "
        "urgent access removal")


def test_a_director_still_acts_on_their_own_row(client, director):
    """Acting on yourself gains you nothing you did not already hold."""
    html = _html(client, "/users")
    assert f'/users/edit/{director["id"]}' in html, (
        "a Director cannot even edit their own row")


def test_a_dormant_owner_offers_a_director_no_way_back(client, director, owner):
    """
    Reactivation is the mirror door and needs hiding for the mirror reason: a
    dormant Owner account is a live one after one POST, and whoever held it may
    still know its password.
    """
    owner["active"] = False
    html = _html(client, "/users")
    assert f'/users/activate/{owner["id"]}' not in html, (
        "a Director was offered a Reactivate link on an Owner account")


def test_an_owner_is_offered_every_action_on_every_row(client, owner, junior):
    """
    The control for the whole register, and the state the `/users` page golden
    hashes — it renders as an Owner, so `main` must not move.
    """
    _as(client, owner)
    html = _html(client, "/users")
    for user in (owner, junior):
        assert f'/users/edit/{user["id"]}' in html, (
            f"an Owner lost the Edit link on {user['username']}")


# ══ 3. The Roles button ════════════════════════════════════════════════════

def test_a_director_is_not_offered_the_roles_button(client, director):
    """
    `/roles` is Owner-only — `admin.roles` is the single permission a Director
    lacks — and this button sat beside "+ New user" on the page a Director uses
    most.
    """
    assert not auth.can_reach("auth.list_roles", director), (
        "the premise is wrong: a Director can reach /roles")
    assert "/roles" not in _html(client, "/users"), (
        "a Director was offered a button that 403s")


def test_an_owner_is_still_offered_the_roles_button(client, owner):
    """The control. B2's whole point is that an Owner edits role definitions."""
    _as(client, owner)
    assert "/roles" in _html(client, "/users"), (
        "an Owner lost the only link to the roles editor")
