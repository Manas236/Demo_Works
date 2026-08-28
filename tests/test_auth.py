"""
Login, roles, and the two guards that stop one checkbox bricking the install.

`tests/test_access_control.py` owns the question "is the app closed". This file
owns the layer underneath it: does a password actually gate anything, is a
deactivated account really refused, does a union of roles union, and do B3's
lockout invariants hold when somebody tries to walk through them.

The lockout guards are the ones worth reading. Neither is a nicety: an install
whose last Owner has been deactivated, or whose Owner role has had
`admin.roles` unticked, has **no path back in** — there is no console, no
`flask shell` in this deployment, and no password-reset e-mail by agreement.
The refusals are the recovery mechanism, so they are tested as behaviour rather
than assumed from reading the code.
"""

import contextlib

import pytest

import auth
from store import STORE

from conftest import TEST_PASSWORD, TEST_USER


@pytest.fixture()
def fresh_users(client):
    """
    Just the suite's seeded Owner — every other account cleared.

    Several tests here count Owners, and a stray account left by another test
    would make `_would_strand_install()` decide there is a spare.
    """
    keep = auth.find_user(TEST_USER)
    STORE["users"].clear()
    STORE["users"][keep["id"]] = keep
    keep["active"] = True
    auth.ensure_builtin_roles()
    yield keep


# ── Signing in ─────────────────────────────────────────────────────────────

def test_a_correct_password_signs_in(anon_client, fresh_users):
    r = anon_client.post("/login", data={"username": TEST_USER,
                                         "password": TEST_PASSWORD})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")
    assert anon_client.get("/boq/").status_code == 200


def test_a_wrong_password_does_not(anon_client, fresh_users):
    r = anon_client.post("/login", data={"username": TEST_USER,
                                         "password": "not-the-password"})
    assert r.status_code == 200          # the form again, not a redirect
    assert "do not match" in r.get_data(as_text=True)
    assert anon_client.get("/boq/").status_code in (302, 303)


def test_an_unknown_user_gets_the_same_message_as_a_wrong_password(
        anon_client, fresh_users):
    """
    Deliberate. Telling a stranger that a username exists tells them which half
    of the guess to keep working on, and this app has a handful of accounts with
    predictable names.
    """
    unknown = anon_client.post("/login", data={"username": "no-such-person",
                                               "password": "whatever12"})
    wrong = anon_client.post("/login", data={"username": TEST_USER,
                                             "password": "wrong-one-12"})
    assert "do not match" in unknown.get_data(as_text=True)
    assert "do not match" in wrong.get_data(as_text=True)


def test_a_deactivated_user_cannot_sign_in(anon_client, fresh_users):
    """
    And is told why, which is the opposite call from the one above.

    A dismissed employee's own account status is not a secret from them, and
    "wrong password" would send an honest user off resetting a password that
    was never the problem. The username-enumeration argument does not apply:
    they have already proved they hold the password.
    """
    user = auth.create_user("gone", "Gone Person", "gone-password-1",
                            ["role-hr"], created_by="test")
    user["active"] = False
    r = anon_client.post("/login", data={"username": "gone",
                                         "password": "gone-password-1"})
    assert r.status_code == 200
    assert "deactivated" in r.get_data(as_text=True)


def test_the_username_is_case_insensitive_but_stored_as_entered(
        anon_client, fresh_users):
    auth.create_user("Yogesh", "Yogesh B", "yogesh-password-1",
                     ["role-director"], created_by="test")
    assert auth.find_user("yogesh")["username"] == "Yogesh"
    assert auth.find_user("YOGESH")["username"] == "Yogesh"

    r = anon_client.post("/login", data={"username": "YOGESH",
                                         "password": "yogesh-password-1"})
    assert r.status_code == 302


def test_a_duplicate_username_is_refused_whatever_its_case(fresh_users):
    auth.create_user("dup", "Dup", "dup-password-1", [], created_by="test")
    with pytest.raises(ValueError):
        auth.create_user("DUP", "Other", "other-password-1", [], created_by="test")


def test_logout_needs_a_post(client, fresh_users):
    """
    The delete-route convention from commit `9d060ee`, applied to the session.

    A GET that ends a session is issued by link prefetchers, crawlers and mail
    scanners unfurling a pasted URL — every one of which would log somebody out
    in the middle of a form.
    """
    assert client.get("/boq/").status_code == 200

    confirmation = client.get("/logout")
    assert confirmation.status_code == 200
    assert client.get("/boq/").status_code == 200, "GET /logout ended the session"

    assert client.post("/logout").status_code == 302
    assert client.get("/boq/").status_code in (302, 303)


# ── Roles ──────────────────────────────────────────────────────────────────

def test_the_six_client_roles_and_the_owner_are_seeded(fresh_users):
    """B4's six by name, plus B3's Owner tier, which is not one of the six."""
    names = {r["name"] for r in auth.roles().values()}
    assert {"Director", "Operation Head", "HR", "Sales Manager",
            "Purchase Manager", "Accountant"} <= names
    assert "Owner" in names


def test_seeding_roles_twice_changes_nothing(fresh_users):
    before = {rid: dict(r) for rid, r in auth.roles().items()}
    assert auth.ensure_builtin_roles() == 0
    assert {rid: dict(r) for rid, r in auth.roles().items()} == before


def test_re_seeding_does_not_undo_an_owners_edit(fresh_users):
    """
    The point of `ensure_builtin_roles()` leaving an existing row alone.

    A restart that reset Director to its shipped permissions would quietly undo
    the client's own configuration, and it would do it at the least visible
    moment — nobody watches a restart.
    """
    with _role_restored("director") as director:
        director["permissions"] = [p for p in director["permissions"]
                                   if p != "dc.delete"]
        auth.ensure_builtin_roles()
        assert "dc.delete" not in auth.roles()["role-director"]["permissions"]

    assert "dc.delete" in auth.roles()["role-director"]["permissions"], \
        "this test leaked its role edit into the rest of the run"


def test_a_director_is_an_admin_but_not_an_owner(fresh_users):
    """
    B3's split, as data. A Director creates and deactivates users; a Director
    cannot change what a role means, because that is the right to grant
    themselves anything.
    """
    director = auth.roles()["role-director"]
    assert "admin.users" in director["permissions"]
    assert auth.OWNER_PERM not in director["permissions"]


def test_hr_information_is_kept_from_sales_purchase_and_accounts(fresh_users):
    """
    B4's one stated restriction, applied to the only employee data the app
    holds today — `charge.py`, the wages and site-expense ledger.

    C4's employee master does not exist yet. When it does, its permissions join
    this assertion rather than replacing it.
    """
    for slug in ("sales-manager", "purchase-manager", "accountant"):
        perms = auth.roles()[f"role-{slug}"]["permissions"]
        assert not [p for p in perms if p.startswith("charge.")], (
            f"{slug} carries a charge.* permission; CLIENT_CHANGES-2.md B4 keeps "
            f"HR information from Sales, Purchase and Accounts")
    assert "charge.view" in auth.roles()["role-hr"]["permissions"]


def test_a_role_cannot_be_given_a_permission_that_does_not_exist(client, fresh_users):
    """
    B2: the client bundles permissions, the client does not mint them.

    A stored typo grants nothing and is invisible on the page that stored it —
    it looks exactly like a permission that is simply not working.
    """
    with _role_restored("hr"):
        client.post("/roles/edit/role-hr",
                    data={"permissions": ["charge.view", "charge.invented",
                                          "not.real"]})
        assert auth.roles()["role-hr"]["permissions"] == ["charge.view"]

    assert "dashboard.view" in auth.roles()["role-hr"]["permissions"], \
        "this test left HR holding one permission for the rest of the run"


def test_editing_a_role_takes_effect_without_signing_in_again(client, fresh_users):
    """
    Why the session holds only a user id.

    B2's rationale is that the client will change his mind about who can do
    what and that this must be a checkbox rather than a deploy. A permission set
    cached on the session at login would make it a checkbox plus a sign-out.
    """
    user = auth.create_user("changes", "Changes", "changes-password-1",
                            ["role-hr"], created_by="test")
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]
    assert client.get("/boq/").status_code == 403

    # Restored whatever happens below — see `_role_restored()`. The assertion
    # after the block is not decoration: it is what fails if the guard is ever
    # removed, in the file that caused the leak rather than in the one that
    # tripped over it.
    with _role_restored("hr"):
        auth.roles()["role-hr"]["permissions"].append("boq.view")
        assert client.get("/boq/").status_code == 200

    assert "boq.view" not in auth.roles()["role-hr"]["permissions"],         "this test leaked its role edit into the rest of the run"


@contextlib.contextmanager
def _role_restored(slug: str):
    """
    Put one builtin role's permissions back, whatever the block does to them.

    **Three tests in this file edit a builtin role to prove something true, and
    until 28 August 2026 none of them put it back.** Roles live in one shared
    dict that `conftest._fresh_store()` deliberately does not clear, and
    `ensure_builtin_roles()` deliberately never rewrites an existing row — an
    Owner's edit has to survive a restart, which is the whole point of B2. Both
    are correct, and together they mean an edit here reaches every file that
    runs afterwards.

    It did. `tests/test_nav_visibility.py` carried an autouse fixture whose only
    job was to undo the damage, and that fixture was deleted when this was
    added. **A test that pollutes global state is a defect regardless of what it
    is testing**, and the fix belongs where the mutation is.

    The worst of the three was
    `test_a_role_cannot_be_given_a_permission_that_does_not_exist`, which posts
    to `/roles/edit/role-hr` and left HR holding **one** permission — no
    `dashboard.view`, so an HR user could not load the dashboard for the rest of
    the run.
    """
    role = auth.roles()[f"role-{slug}"]
    original = list(role["permissions"])
    try:
        yield role
    finally:
        auth.roles()[f"role-{slug}"]["permissions"] = original


# ── B3's lockout guards ────────────────────────────────────────────────────

def test_the_last_owner_cannot_be_deactivated(client, fresh_users):
    owner = fresh_users
    assert len(auth.active_owners()) == 1

    r = client.post(f"/users/deactivate/{owner['id']}")
    assert owner["active"] is True, "the last Owner was deactivated"
    assert r.status_code == 302
    assert "only+active+Owner" in r.headers["Location"] or \
           "only active Owner" in r.headers["Location"].replace("%20", " ")


def test_the_last_owner_cannot_edit_their_own_owner_role_away(client, fresh_users):
    """
    The same lockout through the side door, and the easier one to do by
    accident: not "delete the Owner" but "tidy up my own roles".
    """
    owner = fresh_users
    r = client.post(f"/users/edit/{owner['id']}",
                    data={"display_name": "Test Owner", "role_ids": ["role-hr"]})
    assert r.status_code == 200, "the edit was accepted"
    assert "only active Owner" in r.get_data(as_text=True)
    assert auth.is_owner(auth.users()[owner["id"]]), "the Owner role was removed"


def test_a_second_owner_frees_the_first(client, fresh_users):
    """The guard is about the *last* Owner, not about Owners in general —
    otherwise it would stop the handover it exists to make safe."""
    auth.create_user("owner2", "Second Owner", "owner2-password-1",
                     ["role-owner"], created_by="test")
    assert len(auth.active_owners()) == 2

    owner = fresh_users
    r = client.post(f"/users/deactivate/{owner['id']}")
    assert r.status_code == 302
    assert auth.users()[owner["id"]]["active"] is False


def test_an_admin_cannot_grant_themselves_the_owner_role(client, fresh_users):
    """
    B3: "only an Owner can create an Owner."

    Without this the tier split is decoration — the Director who "cannot alter
    role definitions" would simply tick the Owner role on a new account and log
    in as it.
    """
    director = auth.create_user("yogesh", "Yogesh", "yogesh-password-1",
                                ["role-director"], created_by="test")
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = director["id"]

    r = client.post("/users/create", data={
        "username": "sneaky", "display_name": "Sneaky", "password": "sneaky-password-1",
        "role_ids": ["role-owner"]})
    assert r.status_code == 200, "the Director created an Owner"
    assert "Only an Owner" in r.get_data(as_text=True)
    assert auth.find_user("sneaky") is None


def test_an_admin_can_still_create_an_ordinary_user(client, fresh_users):
    """The control for the test above: the guard blocks the Owner role, not the
    user administration B3 sells the client."""
    director = auth.create_user("yogesh2", "Yogesh", "yogesh2-password-1",
                                ["role-director"], created_by="test")
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = director["id"]

    r = client.post("/users/create", data={
        "username": "newstaff", "display_name": "New Staff",
        "password": "newstaff-password-1", "role_ids": ["role-sales-manager"]})
    assert r.status_code == 302
    assert auth.find_user("newstaff") is not None


def test_the_owner_role_cannot_lose_the_permission_that_defines_it(client, fresh_users):
    """
    One unticked checkbox would otherwise leave no role able to edit any role —
    including the one that would put it back.
    """
    r = client.post("/roles/edit/role-owner",
                    data={"permissions": ["dashboard.view"]})
    assert r.status_code == 200
    assert "must keep" in r.get_data(as_text=True)
    assert auth.OWNER_PERM in auth.roles()["role-owner"]["permissions"]


def test_the_director_role_cannot_lose_user_administration(client, fresh_users):
    """B3 gives the client's Directors the staff churn. A Director who cannot
    add a user has to telephone us to hire somebody."""
    r = client.post("/roles/edit/role-director",
                    data={"permissions": ["dashboard.view"]})
    assert r.status_code == 200
    assert "must keep" in r.get_data(as_text=True)
    assert "admin.users" in auth.roles()["role-director"]["permissions"]


# ── Users are deactivated, never deleted ───────────────────────────────────

def test_there_is_no_route_that_deletes_a_user(fresh_users):
    """
    A judgement call, recorded as a test so it is not undone by accident.

    `db.py` has no foreign keys. `created_by` on a user record — and on every
    record the approvals ladder (B6) will stamp — would dangle the moment a row
    disappeared, and the name on last year's bill would stop resolving. A
    deactivated user cannot sign in, which is the whole of what removing access
    means.
    """
    import app as app_module

    user_delete = [r.rule for r in app_module.app.url_map.iter_rules()
                   if r.rule.startswith("/users/") and "delete" in r.rule]
    assert not user_delete, (
        f"a user delete route exists: {user_delete}. Users are deactivated, "
        f"never deleted — see /users/deactivate/<id>.")


def test_deactivating_and_reactivating_round_trips(client, fresh_users):
    user = auth.create_user("temp", "Temp", "temp-password-1",
                            ["role-hr"], created_by="test")
    client.post(f"/users/deactivate/{user['id']}")
    assert auth.users()[user["id"]]["active"] is False
    client.post(f"/users/activate/{user['id']}")
    assert auth.users()[user["id"]]["active"] is True


def test_a_get_to_deactivate_changes_nothing(client, fresh_users):
    """The delete-route convention again: GET confirms, POST acts."""
    user = auth.create_user("temp2", "Temp", "temp2-password-1",
                            ["role-hr"], created_by="test")
    r = client.get(f"/users/deactivate/{user['id']}")
    assert r.status_code == 200
    assert auth.users()[user["id"]]["active"] is True


# ── /setup ─────────────────────────────────────────────────────────────────

def test_setup_disables_itself_once_a_user_exists(anon_client, fresh_users):
    """
    The public window closes by itself rather than depending on somebody
    remembering to close it — which is the only reason a public account-creating
    route is safe to ship at all.
    """
    r = anon_client.get("/setup")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_setup_creates_the_first_owner_and_signs_them_in(anon_client):
    STORE["users"].clear()
    r = anon_client.get("/setup")
    assert r.status_code == 200

    r = anon_client.post("/setup", data={
        "username": "first", "display_name": "First Owner",
        "password": "first-owner-pw", "confirm_password": "first-owner-pw"})
    assert r.status_code == 302

    user = auth.find_user("first")
    assert user is not None and auth.is_owner(user)
    assert anon_client.get("/roles").status_code == 200, "not signed in after setup"


def test_setup_is_the_only_way_in_when_there_are_no_users(anon_client):
    """
    A fresh install must not be a locked door. With no users the gate sends
    every request to `/setup` rather than to a login form nothing can satisfy.
    """
    STORE["users"].clear()
    r = anon_client.get("/boq/")
    assert r.status_code == 302
    assert "/setup" in r.headers["Location"]


def test_setup_refuses_a_short_password(anon_client):
    STORE["users"].clear()
    r = anon_client.post("/setup", data={
        "username": "shorty", "display_name": "", "password": "abc",
        "confirm_password": "abc"})
    assert r.status_code == 200
    assert "at least 8" in r.get_data(as_text=True)
    assert not STORE["users"]


# ── tools/seed_users.py ────────────────────────────────────────────────────

def test_the_seed_script_refuses_a_blank_or_placeholder_password():
    """
    No default password, ever. The account this script creates holds
    `admin.roles`, which is the right to grant itself everything — a seeded
    default is a published administrator credential on every install.
    """
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from tools.seed_users import _reject_password

    for bad in ("", "   ", "admin", "password", "changeme", "Samruddhi",
                "qms-demo-secret-2024", "short"):
        assert _reject_password(bad, "owner"), f"{bad!r} was accepted as a password"

    assert _reject_password("owner", "owner"), "the username was accepted as the password"
    assert _reject_password(" hasspace123 ", "owner"), "untrimmed password accepted"
    assert not _reject_password("a-real-chosen-password", "owner")


def test_the_seed_script_is_idempotent(fresh_users):
    """
    Roles are seeded by fixed slug, so a second run creates nothing — which is
    what makes it safe to leave in a deploy step.
    """
    before = dict(auth.roles())
    assert auth.ensure_builtin_roles() == 0
    assert dict(auth.roles()) == before


def test_the_seed_scripts_roles_are_the_builtin_ones(fresh_users):
    """The script offers slugs, not free text; an unknown one is an error rather
    than a user created with no access at all."""
    from tools.seed_users import main  # noqa: F401  (import must not explode)

    assert set(auth.BUILTIN_ROLES) == {
        "owner", "director", "operation-head", "hr",
        "sales-manager", "purchase-manager", "accountant"}
    for slug in auth.BUILTIN_ROLES:
        assert f"role-{slug}" in auth.roles()


# ── SECRET_KEY ─────────────────────────────────────────────────────────────

def test_the_demo_secret_key_is_gone_from_the_codebase():
    """
    ABOUT.md §7 gap 8, closed. With sessions live, a signing key published in a
    git history means a forged cookie is a valid login and every permission
    check in this pass is theatre.

    Asserted against the source rather than against `app.secret_key`, because
    the failure being guarded is somebody reinstating the literal as a
    convenience — which would look fine in any environment that also sets the
    variable.

    Read from the **AST**, not by string search: `app.py` still names the old
    value in a comment explaining where it went, and `tools/seed_users.py` lists
    it among the passwords it refuses. Both of those are the fix, not the defect.
    A comment is not in the AST, so this asks the only question that matters —
    is the value a live string in this module.
    """
    import ast
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted(repo.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "qms-demo-secret-2024":
                offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, (
        f"the demo secret key is a live string literal at {offenders}. It signs "
        f"session cookies and it is published in this repository's history.")


def test_an_environment_key_is_used_and_never_written(monkeypatch, tmp_path):
    """A deployment-supplied key must not cause a file to be minted beside the
    code — a second key on disk is a second thing to leak."""
    monkeypatch.setenv("SAMRUDDHI_SECRET_KEY", "a-real-deployment-key")
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "secret_key.txt")
    assert auth.resolve_secret_key() == "a-real-deployment-key"
    assert not (tmp_path / "secret_key.txt").exists()


def test_a_key_is_minted_and_reused_when_the_environment_is_silent(
        monkeypatch, tmp_path):
    monkeypatch.delenv("SAMRUDDHI_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "secret_key.txt")

    first = auth.resolve_secret_key()
    assert len(first) >= 32
    assert (tmp_path / "secret_key.txt").read_text(encoding="utf8").strip() == first
    assert auth.resolve_secret_key() == first, "a new key on every boot logs everybody out"


# ── tools/set_password.py ──────────────────────────────────────────────────
#
# The break-glass CLI that closed ABOUT.md §7 gap 21. Its behaviour needs a live
# MySQL and cannot run here — `main()` refuses outright when `db.init()` is
# false, which is the point of it. What these four tests hold is the half that
# CAN rot silently: the three things it deliberately does not own a copy of, and
# the one thing it must never do. Each is a real drift, not a style rule.

def _set_password_source():
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent
            / "tools" / "set_password.py").read_text(encoding="utf8")


def test_the_break_glass_tool_shares_the_seed_scripts_password_policy():
    """
    One password policy with one home.

    Two copies drift, and the copy that drifts *low* is the one somebody reaches
    for in an emergency — which is exactly when a placeholder password gets set
    on the account that can grant itself everything.
    """
    from tools import seed_users, set_password

    assert set_password._reject_password is seed_users._reject_password


def test_the_break_glass_tool_takes_its_hashing_from_auth():
    """
    The writer and the reader must not be able to drift apart.

    `/login` verifies with `auth`'s `check_password_hash`. A tool that reached
    for `werkzeug.security` itself could be pinned differently, or follow a
    parameter change `auth` had not taken, and mint a hash that verifies
    nowhere — locking the account harder than the forgotten password did.
    Read from the AST so a mention in the docstring is not a false positive.
    """
    import ast

    import auth as auth_mod
    from tools import set_password

    tree = ast.parse(_set_password_source())
    direct = [n for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.module == "werkzeug.security"]
    assert not direct, (
        "tools/set_password.py imports werkzeug.security directly; it must come "
        "through auth, which is where /login gets it")

    assert set_password.auth.generate_password_hash is auth_mod.generate_password_hash
    assert set_password.auth.check_password_hash is auth_mod.check_password_hash


def test_the_break_glass_tool_never_creates_a_user():
    """
    It sets passwords; it does not mint accounts.

    A typo'd username that created an account would be worse than one that
    failed: a seeded-by-accident login is `test_no_seeder_invents_a_user`'s
    whole subject, and this tool runs with the operator's full attention
    elsewhere. Asserted against the AST rather than the text because the
    docstring says the words "does not create users" in prose.
    """
    import ast

    called = set()
    for node in ast.walk(ast.parse(_set_password_source())):
        if isinstance(node, ast.Call):
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute)
                    else fn.id if isinstance(fn, ast.Name) else "")
            called.add(name)

    assert "create_user" not in called
    assert "ensure_builtin_roles" not in called, (
        "seeding roles is tools/seed_users.py's job; this tool touches an "
        "account that already exists")


def test_the_break_glass_tool_never_prints_the_hash():
    """
    A recovery tool is run in somebody's terminal, and terminals keep scrollback.

    The username, roles and Owner tier are what the operator needs to know it
    worked. The hash is the one thing on that screen worth stealing.
    """
    import ast

    for node in ast.walk(ast.parse(_set_password_source())):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "print"):
            continue
        printed = ast.dump(ast.Module(body=[ast.Expr(node)], type_ignores=[]))
        for banned in ("new_hash", "password_hash"):
            assert banned not in printed, f"a print() carries {banned}"
