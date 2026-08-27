"""
What an Admin can DO once they are on /users — not what they can reach.

`tests/test_access_control_adversarial.py` §5 proves a Director *reaches*
`/users/*` and is refused at `/roles/*`, and its §6 proves they cannot tick the
Owner box. All of that is about the **roles** field. This file is about
everything else on the same form, and about the same question asked of a role
the client might reasonably build with B2's checkboxes.

Run as an attack on 27 August 2026 with a **Director-only** account — not the
Owner+Director the first-run `/setup` creates, which would prove nothing. Ten
attacks. **Five got through:**

* `POST /users/edit/<owner id>` with a `password` field **set the Owner's
  password**, and that password then signed in and reached `/roles` with a 200.
  No role was changed; none had to be. This is the hole, and it is the same
  shape as `/projects/view/<id>` before it: the page was classified, one write
  path on it was not guarded.
* the same form **took the Owner role off** a spare Owner,
* `POST /users/deactivate/<owner id>` **switched a spare Owner off**, and
  `POST /users/activate/<id>` switched a dormant one back on — both of which
  walk the install down towards the single Owner whose password the first
  attack then sets,
* a **limited admin role** (`admin.users` and little else, exactly what B2
  invites an Owner to build) **conferred `charge.*` on somebody** by handing
  out the HR role — permissions its own holder does not have.

The other five were already clean and are pinned here anyway, because
`docs/ACCESS_MATRIX.md` states them to the client in prose — "they cannot grant
anybody the Owner role, or create a new Owner account" — and a claim in a
client-facing document should be held by a test rather than by a reading of the
code.

**Every attack below is paired with a control that must succeed**, on the same
route and the same field. Without one, a Director locked out of `/users`
entirely — or an app that 500s — would score as a pass on all ten.
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
                            created_by="escalation-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


@pytest.fixture()
def owner(client):
    """
    The one active Owner in the store, and the account under attack.

    Every other Owner — including the `test-owner` `conftest` signs the suite
    in as — is switched off, so `_would_strand_install()` sees exactly the
    install the client would have: one Owner, and Directors around it.
    """
    auth.ensure_builtin_roles()
    o = _user("esc-owner", ["role-owner"], "esc-owner-password")
    for user in STORE["users"].values():
        if auth.is_owner(user) and user["id"] != o["id"]:
            user["active"] = False
    assert [u["id"] for u in auth.active_owners()] == [o["id"]]
    return o


@pytest.fixture()
def director(client, owner):
    """A **Director only** — not the Owner+Director `/setup` mints."""
    d = _user("esc-director", ["role-director"])
    assert not auth.is_owner(d), "the attacker must not already be an Owner"
    assert auth.ADMIN_PERM in auth.permissions_of(d)
    _as(client, d)
    return d


@pytest.fixture()
def junior(client):
    """A subordinate for the Director to legitimately administer."""
    return _user("esc-junior", ["role-sales-manager"], "esc-junior-password")


def _signs_in(app, username: str, password: str) -> bool:
    """True when these credentials actually open a session."""
    with app.test_client() as fresh:
        response = fresh.post("/login", data={"username": username,
                                              "password": password})
        return response.status_code in (302, 303)


# ══ 1. The roles field — already clean, pinned because the client is told so ══

def test_a_director_cannot_create_an_owner_account(client, director):
    """`docs/ACCESS_MATRIX.md`: they "cannot ... create a new Owner account"."""
    client.post("/users/create",
                data={"username": "esc-minted-owner", "display_name": "m",
                      "password": "minted-owner-password",
                      "role_ids": ["role-owner"]})
    assert auth.find_user("esc-minted-owner") is None, (
        "a Director minted a new Owner account")


def test_a_director_cannot_add_the_owner_role_to_another_user(
        client, director, junior):
    """`docs/ACCESS_MATRIX.md`: they "cannot grant anybody the Owner role"."""
    client.post(f"/users/edit/{junior['id']}",
                data={"display_name": "j",
                      "role_ids": ["role-sales-manager", "role-owner"]})
    assert not auth.is_owner(junior), "a Director promoted somebody else to Owner"


def test_a_director_cannot_add_the_owner_role_to_themselves(client, director):
    """The same door, walked through by the person who opened it."""
    client.post(f"/users/edit/{director['id']}",
                data={"display_name": "d",
                      "role_ids": ["role-director", "role-owner"]})
    assert not auth.is_owner(director), "a Director promoted themselves to Owner"


def test_a_role_id_the_form_never_offered_is_still_refused(client, director):
    """
    The guard has to sit on the handler, not on which boxes are drawn.

    Two ids that no honest browser would submit: one that does not exist at
    all, and one minted by an Owner after the Director's page was rendered.
    Neither is in the HTML the Director was served; both are posted anyway.
    """
    auth.roles()["role-shadow"] = {
        "id": "role-shadow", "name": "Shadow", "builtin": False,
        "permissions": ["dashboard.view", auth.OWNER_PERM]}
    target = _user("esc-shadow-target", [])

    client.post(f"/users/edit/{target['id']}",
                data={"display_name": "t",
                      "role_ids": ["role-shadow", "role-does-not-exist"]})

    assert not auth.is_owner(target), (
        "a role id that the form never rendered still conferred admin.roles")
    assert "role-does-not-exist" not in (target.get("role_ids") or []), (
        "a role id that matches no role was stored on the user")


# ══ 2. The password field — THE HOLE ═══════════════════════════════════════

def test_a_director_cannot_set_an_owners_password(client, director, owner):
    """
    The hole, and the reason this file exists.

    `/users/edit` is classified `admin.users` and its roles field is guarded by
    `_may_grant()`. The password field beside it was guarded by nothing, so a
    Director could leave every role alone, set the Owner's password, and sign
    in as the Owner — reaching `/roles`, the one page B3 says they may never
    reach. **A password on a more-privileged account is that account.**

    The assertion is deliberately the *login*, not the hash: what makes this a
    privilege escalation is that the credential works, and a test that only
    compared hashes would still pass if the write moved somewhere else.
    """
    import app as app_module

    response = client.post(f"/users/edit/{owner['id']}",
                           data={"display_name": "esc-owner",
                                 "role_ids": owner["role_ids"],
                                 "password": "director-chose-this"})

    assert response.status_code == 403, (
        f"the write was not refused — it answered {response.status_code}")
    assert not _signs_in(app_module.app, "esc-owner", "director-chose-this"), (
        "a Director set the Owner's password and it signs in — they are now an "
        "Owner without holding admin.roles for a moment")
    assert _signs_in(app_module.app, "esc-owner", "esc-owner-password"), (
        "the Owner's own password stopped working, so this test proves nothing")


def test_the_edit_form_is_not_even_drawn_for_a_more_privileged_account(
        client, director, owner):
    """
    GET is refused too, and that is not belt-and-braces.

    A page that renders a password box and then refuses the POST teaches the
    user that the app is broken. It also leaves the field one missed guard away
    from working again. Refusing to draw it says what the rule is at the moment
    the user asks.
    """
    response = client.get(f"/users/edit/{owner['id']}")
    assert response.status_code == 403
    body = response.get_data(as_text=True)
    assert 'name="password"' not in body, (
        "the password field was rendered on an account this user may not change")
    assert "Owner account" in body, "the refusal does not say why it refused"


def test_the_refusal_reaches_the_access_log(client, director, owner):
    """
    B5's surviving diagnostic has to see this class of refusal too.

    A guard inside a view is invisible on `/access-log` unless it says so, and
    "somebody tried to change the Owner's password" is precisely the line an
    Owner should find there.
    """
    before = len(auth.REFUSAL_LOG)
    client.post(f"/users/edit/{owner['id']}",
                data={"display_name": "x", "role_ids": owner["role_ids"],
                      "password": "another-attempt"})

    assert len(auth.REFUSAL_LOG) > before, "the refusal was not logged"
    entry = auth.REFUSAL_LOG[0]
    assert entry["user"] == "esc-director"
    assert entry["endpoint"] == "auth.edit_user"
    assert "another-attempt" not in repr(entry), (
        "the attempted password was written into the refusal log")


# ══ 3. Roles and account state, taken AWAY from an Owner ═══════════════════

def test_a_director_cannot_take_the_owner_role_off_an_owner(
        client, director, owner):
    """
    `_would_strand_install()` only guards the **last** Owner. With a spare in
    the store a Director could demote one, then the other, then the last one's
    password becomes the whole install. Deciding who is an Owner is the Owner
    tier whichever direction it moves.
    """
    spare = _user("esc-owner-2", ["role-owner"], "esc-owner-2-password")
    assert len(auth.active_owners()) == 2

    response = client.post(f"/users/edit/{spare['id']}",
                           data={"display_name": "s", "role_ids": ["role-hr"]})

    assert response.status_code == 403
    assert auth.is_owner(spare), "a Director stripped the Owner role off an Owner"


def test_a_director_cannot_deactivate_an_owner(client, director, owner):
    """The same walk-down, by the route that does not touch roles at all."""
    spare = _user("esc-owner-3", ["role-owner"], "esc-owner-3-password")

    response = client.post(f"/users/deactivate/{spare['id']}")

    assert response.status_code == 403
    assert spare["active"], "a Director switched an Owner off"


def test_a_director_cannot_reactivate_a_dormant_owner(client, director, owner):
    """
    Reactivation is the same power pointed the other way: a dormant Owner
    account is a live one after a single POST, and whoever held it — a departed
    director, the person doing this — may still know its password.
    """
    spare = _user("esc-owner-4", ["role-owner"], "esc-owner-4-password")
    spare["active"] = False

    response = client.post(f"/users/activate/{spare['id']}")

    assert response.status_code == 403
    assert not spare["active"], "a Director switched a dormant Owner back on"


def test_the_last_owner_still_cannot_be_stranded(client, director, owner):
    """
    B3's stated invariant, attacked by somebody who is not the Owner.

    Already clean before this pass — `_would_strand_install()` covered it — and
    now covered twice, because `_may_administer()` refuses a Director the
    account entirely. Pinned so that a later relaxation of either guard has to
    walk past this.
    """
    assert len(auth.active_owners()) == 1
    client.post(f"/users/edit/{owner['id']}",
                data={"display_name": "o", "role_ids": ["role-hr"]})
    client.post(f"/users/deactivate/{owner['id']}")

    assert auth.is_owner(owner) and owner["active"], (
        "the last Owner was stranded by a Director — nobody can define a role "
        "in this install any more")


# ══ 4. The general rule, not the Owner special case ════════════════════════

def test_a_limited_admin_cannot_confer_a_permission_it_does_not_hold(client, owner):
    """
    B2 invites exactly this role, so the guard cannot be about Owner alone.

    "Roles are bundles of permissions, editable as data" means an Owner will
    build a *limited* admin — `admin.users` plus a little — and today's
    `role-director` is only safe from the old one-permission check by accident:
    `admin.roles` happens to be the single permission a Director lacks. Give
    somebody `admin.users` without `charge.*` and the old guard let them hand
    out the HR role, conferring four charge permissions they cannot use
    themselves.
    """
    auth.roles()["role-limited-admin"] = {
        "id": "role-limited-admin", "name": "Office Admin", "builtin": False,
        "permissions": ["dashboard.view", auth.ADMIN_PERM]}
    limited = _user("esc-limited", ["role-limited-admin"])
    fresh = _user("esc-fresh", [])
    _as(client, limited)

    assert "charge.delete" not in auth.permissions_of(limited)

    client.post(f"/users/edit/{fresh['id']}",
                data={"display_name": "f", "role_ids": ["role-hr"]})
    assert "charge.delete" not in auth.permissions_of(fresh), (
        "an admin who cannot delete a charge gave somebody else the right to")

    client.post("/users/create",
                data={"username": "esc-by-limited", "display_name": "b",
                      "password": "by-limited-password", "role_ids": ["role-hr"]})
    made = auth.find_user("esc-by-limited")
    assert made is None or "charge.delete" not in auth.permissions_of(made), (
        "the same escalation through /users/create instead of /users/edit")


def test_a_limited_admin_can_still_grant_what_it_does_hold(client, owner):
    """
    The control for the test above, and the line the rule actually draws.

    An admin handing out a role whose every permission they already hold is
    ordinary staff administration and must keep working, or the guard has
    simply broken `admin.users`.
    """
    auth.roles()["role-limited-admin"] = {
        "id": "role-limited-admin", "name": "Office Admin", "builtin": False,
        "permissions": ["dashboard.view", auth.ADMIN_PERM]}
    limited = _user("esc-limited-2", ["role-limited-admin"])
    fresh = _user("esc-fresh-2", [])
    _as(client, limited)

    client.post(f"/users/edit/{fresh['id']}",
                data={"display_name": "f", "role_ids": ["role-limited-admin"]})

    assert fresh["role_ids"] == ["role-limited-admin"], (
        "an admin could not grant a role it holds in full — admin.users is broken")


# ══ 5. The controls — a Director must still administer their own staff ═════

def test_a_director_still_administers_an_ordinary_user(client, director, junior):
    """
    B3's whole purpose: the client handles staff churn without calling us.

    Rename, re-role, **set a password** and deactivate, all on somebody who
    holds nothing the Director does not. If any of this breaks, the fix above
    has taken B3's Admin tier away instead of bounding it.
    """
    import app as app_module

    response = client.post(f"/users/edit/{junior['id']}",
                           data={"display_name": "Renamed",
                                 "role_ids": ["role-purchase-manager"],
                                 "password": "director-reset-this"})
    assert response.status_code in (302, 303), "the ordinary edit was refused"
    assert junior["display_name"] == "Renamed"
    assert junior["role_ids"] == ["role-purchase-manager"]
    assert _signs_in(app_module.app, "esc-junior", "director-reset-this"), (
        "a Director could not reset a subordinate's password — B3's stated job")

    client.post(f"/users/deactivate/{junior['id']}")
    assert not junior["active"], "a Director could not deactivate a subordinate"
    client.post(f"/users/activate/{junior['id']}")
    assert junior["active"], "a Director could not reactivate a subordinate"


def test_a_director_still_creates_users(client, director):
    """The other half of the same job."""
    client.post("/users/create",
                data={"username": "esc-hired", "display_name": "New Hire",
                      "password": "new-hire-password", "role_ids": ["role-hr"]})
    hired = auth.find_user("esc-hired")
    assert hired is not None, "a Director could not create a user at all"
    assert hired["role_ids"] == ["role-hr"]


def test_a_director_still_changes_their_own_password(client, director):
    """
    Acting on yourself is never an escalation — you already hold everything you
    hold. A guard that forgot this would lock every Owner out of `/users/edit`
    on their own row.
    """
    import app as app_module

    response = client.post(f"/users/edit/{director['id']}",
                           data={"display_name": "esc-director",
                                 "role_ids": ["role-director"],
                                 "password": "my-own-new-password"})
    assert response.status_code in (302, 303)
    assert _signs_in(app_module.app, "esc-director", "my-own-new-password")


def test_an_owner_still_administers_another_owner(client, owner):
    """
    The handover B3 exists to make safe. An Owner sets another Owner's
    password, takes the role away, and switches the account off — none of it
    blocked, because the Owner tier can grant itself anything by editing a role
    and a subset test on it would only produce a puzzling refusal.
    """
    spare = _user("esc-owner-5", ["role-owner"], "esc-owner-5-password")
    _as(client, owner)

    response = client.post(f"/users/edit/{spare['id']}",
                           data={"display_name": "Spare",
                                 "role_ids": ["role-owner"],
                                 "password": "owner-set-this"})
    assert response.status_code in (302, 303), "an Owner was refused an Owner"

    client.post(f"/users/edit/{spare['id']}",
                data={"display_name": "Spare", "role_ids": ["role-hr"]})
    assert not auth.is_owner(spare), "an Owner could not hand the tier back"
