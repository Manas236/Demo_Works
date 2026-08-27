"""
Phase 3B, attacked rather than demonstrated.

`tests/test_access_control.py` proves the access layer does what it was built
to do. This file tries to get past it. The difference matters: a suite written
by the same pass that wrote the feature tends to test the paths the author was
already thinking about, and the paths an author was thinking about are the ones
that work.

Eleven attacks, run against the layer shipped on 26 August 2026. **Two got
through**, and both have their own commit and their own regression case below:

* `POST /projects/view/<id>` **wrote to records under a read permission.** The
  registry is keyed per *endpoint*, and that rule takes GET and POST. See
  `test_a_read_permission_does_not_authorise_the_post_on_the_same_rule`.
* `/login` **answered an unknown username ~240x faster** than a real one with a
  wrong password, because `check_password_hash` only ran when a record was
  found. See `test_login_does_not_leak_which_usernames_exist_by_timing`.

The other nine were clean and are pinned here anyway. A clean result that
nothing asserts is a clean result that stops being true quietly — and several
of these (the tamper cases, the lockout guards) are exactly the properties a
future refactor of `auth.py` would break without noticing.

**A twelfth attack was run on 27 August 2026 and lives in its own file.**
`tests/test_privilege_escalation.py` asks what an Admin can *do* once they are
on `/users`, rather than which of those pages they can reach — §5 and §6 below
only ever tested the **roles** field. Five of its ten attacks got through, the
first being that `/users/edit/<id>` set the **Owner's password** under
`admin.users`. It is a separate file rather than a §12 here because it is a
separate pass with its own commit; read the two together.

### Reading a "clean" test in this file

Every one of them pairs the refusal with a **control** that must succeed, on
the same URL or the same mechanism. A test that only asserts "refused" passes
just as well against an application that is simply broken, and this whole file
would then be reporting that a 500 is a security guarantee.
"""

import statistics
import time

import pytest
from flask.sessions import SecureCookieSessionInterface
from werkzeug.routing import Rule

import auth
from store import STORE


# ── People ─────────────────────────────────────────────────────────────────

def _user(name: str, role_ids: list) -> dict:
    """A fresh user, replacing any left by an earlier test."""
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", role_ids,
                            created_by="adversarial-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


@pytest.fixture()
def owner(client):
    auth.ensure_builtin_roles()
    return _user("adv-owner", ["role-owner"])


@pytest.fixture()
def sales(client):
    auth.ensure_builtin_roles()
    return _user("adv-sales", ["role-sales-manager"])


@pytest.fixture()
def hr(client):
    auth.ensure_builtin_roles()
    return _user("adv-hr", ["role-hr"])


# ══ 1. A forged session cookie ═════════════════════════════════════════════

def _signed(app, payload: str) -> str:
    """A session cookie signed with the app's real key."""
    return SecureCookieSessionInterface().get_signing_serializer(app).dumps(payload)


@pytest.mark.parametrize("shape", ["ghost-user", "bad-signature", "unsigned"])
def test_a_tampered_session_cookie_is_refused(anon_client, owner, shape):
    """
    Three ways to mint a cookie, none of which may work.

    * **ghost-user** — correctly signed, naming a user id that does not exist.
      This is the one that separates "the signature verified" from "the user is
      real": a gate that trusted the id because the envelope was authentic
      would let it through.
    * **bad-signature** — a real user id, one tampered character in the MAC.
      This is what `SECRET_KEY` is for, and it is the reason ABOUT.md §7 gap 8
      had to be closed before this layer meant anything.
    * **unsigned** — raw JSON, the shape somebody tries first.

    The control below is the same cookie, correctly signed, which must reach
    the page — otherwise this test proves only that the client is broken.
    """
    import app as app_module

    if shape == "ghost-user":
        cookie = _signed(app_module.app, {auth.SESSION_KEY: "no-such-user-id"})
    elif shape == "bad-signature":
        good = _signed(app_module.app, {auth.SESSION_KEY: owner["id"]})
        cookie = good[:-6] + "AAAAAA"
    else:
        cookie = '{"uid":"%s"}' % owner["id"]

    anon_client.set_cookie("session", cookie, domain="localhost")
    response = anon_client.get("/boq/")

    assert response.status_code in (302, 303), (
        f"a {shape} cookie was not refused — it got {response.status_code}")
    assert "/login" in response.headers.get("Location", "")


def test_the_control_a_correctly_signed_cookie_does_work(anon_client, owner):
    """
    The control for all three above.

    Without it, "every forged cookie was refused" is satisfied by an
    application that refuses every cookie, and the parametrised test would be
    green on a completely broken session layer.
    """
    import app as app_module

    anon_client.set_cookie("session",
                           _signed(app_module.app, {auth.SESSION_KEY: owner["id"]}),
                           domain="localhost")
    assert anon_client.get("/boq/").status_code == 200


# ══ 2. Deactivated mid-session ═════════════════════════════════════════════

def test_deactivation_takes_effect_on_the_very_next_request(client, owner):
    """
    B3 sells "urgent access removal when someone is dismissed". If `active` were
    read only at login, a dismissed employee would keep working for up to
    `SESSION_HOURS` — twelve hours, which is a working day, which is the whole
    of the window that matters.

    `current_user()` resolves the id against the store on every request, so the
    click after the checkbox is their last one.

    Asserted on an `AUTHENTICATED`-only route as well as a permissioned one:
    `/account` needs no permission at all, so a gate that only re-checked
    `active` on the permission branch would still serve it.
    """
    _as(client, owner)
    assert client.get("/boq/").status_code == 200
    assert client.get("/account").status_code == 200

    owner["active"] = False

    for url in ("/boq/", "/account"):
        response = client.get(url)
        assert response.status_code in (302, 303), (
            f"{url} still served a deactivated user")
        assert "/login" in response.headers.get("Location", "")


# ══ 3. A permission removed mid-session ════════════════════════════════════

def test_a_role_edit_lands_without_the_holder_signing_in_again(client, owner):
    """
    The design claim was that role edits take effect immediately *because* only
    the user id is on the session. Proved rather than assumed, and proved
    through the **real route** — an Owner posting `/roles/edit` — not by
    reaching into `STORE`, because the claim is about what the product does.

    Both directions: removing the permission refuses, putting it back allows.
    One direction on its own would pass against a gate that had simply started
    refusing everything.
    """
    victim = _user("adv-midsession", ["role-operation-head"])
    role = auth.roles()["role-operation-head"]
    original = list(role["permissions"])

    _as(client, victim)
    assert client.get("/boq/").status_code == 200

    _as(client, owner)
    client.post("/roles/edit/role-operation-head",
                data={"permissions": [p for p in original if p != "boq.view"]})

    _as(client, victim)
    assert client.get("/boq/").status_code == 403, (
        "the permission was removed from the role and the holder still had it "
        "— permissions are being cached on the session")

    _as(client, owner)
    client.post("/roles/edit/role-operation-head", data={"permissions": original})

    _as(client, victim)
    assert client.get("/boq/").status_code == 200, "granting it back did not land"


# ══ 4. Method blindness — A HOLE, FOUND AND FIXED ══════════════════════════

def _multi_method_rules():
    import app as app_module
    for rule in app_module.app.url_map.iter_rules():
        methods = rule.methods - {"HEAD", "OPTIONS"}
        if len(methods) > 1:
            yield rule, methods


def test_a_read_permission_does_not_authorise_the_post_on_the_same_rule(
        client, sales):
    """
    **The hole this file was written to find.**

    `ROUTE_PERMISSIONS` maps an *endpoint* to a permission, and 44 rules in
    this app answer both GET and POST on one endpoint. For 43 of them that is
    right and is in fact tighter than a per-method scheme: `/ra/delete/<id>`
    renders a confirmation on GET and destroys on POST, and both should need
    `ra.delete`.

    `/projects/view/<id>` was the exception. It was classified `project.view`
    because it is a view page — and its POST branch takes
    `action=attach_boq` and writes `project_id` onto **every BOQ in a revision
    chain**. So a read permission authorised a write.

    That is not theoretical. Sales Manager, Purchase Manager and Accountant all
    carry `project.view` and none carries `project.edit`: all three are refused
    `/projects/edit/<id>` with a 403 and could then re-attach any schedule to
    any project through the page they *are* allowed to read.

    Fixed with a per-view guard on the POST branch rather than by re-keying the
    registry per method — re-keying means reclassifying all 44 rules, and the
    read/write split on several of them is the client's call, not ours. The
    general shape is recorded as ABOUT.md §7 gap 24b.
    """
    import demo_data as DD

    STORE.setdefault("projects", {})["adv-proj"] = {
        "id": "adv-proj", "name": "Victim Project", "norm_name": "victim project",
        "client": "", "site_address": "", "notes": "",
        "created_at": "2026-08-16T12:00:00Z"}
    client.get("/boq/")                      # seed the demo BOQ
    boq_id = DD.BOQ_META["id"]
    STORE["boqs"][boq_id]["project_id"] = ""

    _as(client, sales)
    assert "project.view" in auth.permissions_of(sales)
    assert "project.edit" not in auth.permissions_of(sales)

    # The read page is allowed, and the edit page is refused. That pairing is
    # the premise: the write below is reached through the one they may read.
    assert client.get("/projects/view/adv-proj").status_code == 200
    assert client.get("/projects/edit/adv-proj").status_code == 403

    response = client.post("/projects/view/adv-proj",
                           data={"action": "attach_boq", "boq_id": boq_id})

    assert STORE["boqs"][boq_id].get("project_id") != "adv-proj", (
        "a user holding only project.view attached a BOQ chain to a project by "
        "POSTing to the view page. The registry is keyed per endpoint, so the "
        "read permission authorised the write.")
    assert response.status_code == 403


def test_the_holder_of_the_write_permission_can_still_attach(client, owner):
    """
    The control for the fix above.

    A guard that refused everybody would satisfy that test perfectly while
    breaking the feature. This is the other half: `project.edit` still attaches.
    """
    import demo_data as DD

    STORE.setdefault("projects", {})["adv-proj2"] = {
        "id": "adv-proj2", "name": "Real Project", "norm_name": "real project",
        "client": "", "site_address": "", "notes": "",
        "created_at": "2026-08-16T12:00:00Z"}
    client.get("/boq/")
    boq_id = DD.BOQ_META["id"]
    STORE["boqs"][boq_id]["project_id"] = ""

    _as(client, owner)
    response = client.post("/projects/view/adv-proj2",
                           data={"action": "attach_boq", "boq_id": boq_id})

    assert response.status_code in (302, 303)
    assert STORE["boqs"][boq_id].get("project_id") == "adv-proj2", (
        "the guard refused a user who does hold project.edit — the fix broke "
        "the feature instead of protecting it")


def test_no_other_multi_method_rule_is_gated_on_a_read_permission(client):
    """
    The sweep that stops the same mistake being made again.

    `/projects/view/<id>` was found by reading 44 rules by hand. This reads
    them off `app.url_map` instead, so a route added later that answers POST
    under a `*.view` permission fails here the day it is registered.

    It deliberately does **not** try to work out whether the POST writes —
    nothing can tell that from the URL map. It asserts the weaker, checkable
    thing: a rule that accepts POST is not classified on a read verb. The one
    genuine exception is named, with its guard.
    """
    guarded = {"projectview.view_project"}   # POST branch guards project.edit itself

    suspects = []
    for rule, methods in _multi_method_rules():
        if "POST" not in methods:
            continue
        permission = auth.ROUTE_PERMISSIONS.get(rule.endpoint)
        if not isinstance(permission, str) or not permission.endswith(".view"):
            continue
        if rule.endpoint in guarded:
            continue
        suspects.append(f"{rule.endpoint} ({rule.rule}) -> {permission}")

    assert not suspects, (
        "these rules accept POST but are gated on a read permission, so a "
        "read-only user may be able to write through them. Either give the "
        "endpoint a write permission, or guard the POST branch in the view "
        "and add it to `guarded` above:\n  " + "\n  ".join(suspects))


# ══ 5. Role boundaries, hit directly by URL ════════════════════════════════

ADMIN_URLS = ["/users", "/users/create", "/roles", "/roles/create",
              "/roles/edit/role-hr", "/access-log"]

# What each builtin role must get on each of the six URLs above. Written out
# rather than derived from BUILTIN_ROLES on purpose: deriving it would make the
# test agree with whatever the role table happens to say, which is the thing
# under test.
EXPECTED = {
    "owner":            {"/users": 200, "/users/create": 200, "/roles": 200,
                         "/roles/create": 200, "/roles/edit/role-hr": 200,
                         "/access-log": 200},
    # B3: a Director administers users but "cannot alter role definitions".
    "director":         {"/users": 200, "/users/create": 200, "/roles": 403,
                         "/roles/create": 403, "/roles/edit/role-hr": 403,
                         "/access-log": 200},
    "operation-head":   dict.fromkeys(ADMIN_URLS, 403),
    "hr":               dict.fromkeys(ADMIN_URLS, 403),
    "sales-manager":    dict.fromkeys(ADMIN_URLS, 403),
    "purchase-manager": dict.fromkeys(ADMIN_URLS, 403),
    "accountant":       dict.fromkeys(ADMIN_URLS, 403),
}


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_each_role_gets_exactly_the_admin_access_it_should(client, slug):
    """
    Seven roles x six administration URLs, requested directly rather than
    through a link. A page that is merely un-linked is not a page that is
    closed, and the Users & Access card on the dashboard is drawn from a
    permission check — so navigating by the UI can never find this class of
    bug.

    The Director row is the one that carries B3: user administration yes, role
    definitions no. Without it a Director could rewrite what Director means,
    which is the single thing B3 says they may not do.
    """
    auth.ensure_builtin_roles()
    user = _user(f"adv-{slug}", [f"role-{slug}"])
    _as(client, user)

    wrong = []
    for url, want in EXPECTED[slug].items():
        got = client.get(url).status_code
        if got != want:
            wrong.append(f"{url}: expected {want}, got {got}")

    assert not wrong, f"role {slug!r} has the wrong administration access:\n  " \
                      + "\n  ".join(wrong)


# ══ 6. The lockout guards, by direct POST ══════════════════════════════════

@pytest.fixture()
def sole_owner(client, owner):
    """`owner` is the only *active* Owner in the store."""
    for user in STORE["users"].values():
        if auth.is_owner(user) and user["id"] != owner["id"]:
            user["active"] = False
    assert [o["id"] for o in auth.active_owners()] == [owner["id"]]
    return owner


def test_the_last_owner_cannot_remove_their_own_role(client, sole_owner):
    """
    B3's invariant, attacked through the side door rather than the front.

    "The last Owner cannot be deleted or deactivated" is the stated rule;
    editing your own roles down to something without `admin.roles` reaches the
    same end state and is the easier one to do by accident. POSTed directly, so
    a guard that only hid the checkbox would not save it.
    """
    client_post = client.post
    _as(client, sole_owner)
    client_post(f"/users/edit/{sole_owner['id']}",
                data={"display_name": "x", "role_ids": ["role-hr"]})

    assert auth.is_owner(sole_owner), (
        "the only Owner edited their own Owner role away — nobody can define a "
        "role in this install any more")


def test_the_last_owner_cannot_be_deactivated(client, sole_owner):
    """The stated half of the same rule, by direct POST."""
    _as(client, sole_owner)
    client.post(f"/users/deactivate/{sole_owner['id']}")
    assert sole_owner["active"], "the only active Owner was deactivated"


def test_the_owner_role_cannot_lose_the_permission_that_defines_it(
        client, sole_owner):
    """
    The third door into the same room: leave the Owner *user* alone and strip
    `admin.roles` off the Owner *role*. `admin.roles` is the only permission
    that can grant `admin.roles` back, so losing it is unrecoverable.
    """
    _as(client, sole_owner)
    client.post("/roles/edit/role-owner", data={"permissions": ["dashboard.view"]})

    assert auth.OWNER_PERM in auth.roles()["role-owner"]["permissions"], (
        "the Owner role lost admin.roles — no role in this install can grant "
        "it back and no role can ever be edited again")


def test_there_is_no_route_that_deletes_a_user_at_all(client):
    """
    "Deleting the last Owner must refuse" is satisfied here by there being no
    delete route to refuse. That is deliberate (`auth.deactivate_user`'s
    docstring: `db.py` has no foreign keys and `created_by` would dangle), and
    it is asserted so that adding one later is a decision somebody takes on
    purpose — with the lockout guard written at the same time.
    """
    import app as app_module

    deleters = [r.rule for r in app_module.app.url_map.iter_rules()
                if r.rule.startswith("/users/") and "delete" in r.rule]
    assert not deleters, (
        f"a user delete route now exists: {deleters}. It needs its own "
        f"_would_strand_install() check and its own test before it ships.")


def test_an_admin_cannot_promote_themselves_to_owner(client):
    """
    B3's tier split, attacked from the Admin side.

    A Director holds `admin.users` and may assign roles. Without `_may_grant()`
    they would simply tick "Owner" on the same checkbox list that assigns Sales
    Manager, and the tier that "cannot alter role definitions" would grant
    itself the role that can. Both doors: promoting themselves, and minting a
    fresh Owner account they then use.
    """
    auth.ensure_builtin_roles()
    director = _user("adv-director-2", ["role-director"])
    _as(client, director)

    client.post(f"/users/edit/{director['id']}",
                data={"display_name": "d",
                      "role_ids": ["role-director", "role-owner"]})
    assert not auth.is_owner(director), "a Director granted themselves Owner"

    client.post("/users/create",
                data={"username": "adv-sneak", "display_name": "s",
                      "password": "sneaky-password", "role_ids": ["role-owner"]})
    assert auth.find_user("adv-sneak") is None, (
        "a Director minted a new Owner account — the tier split is decoration")


# ══ 7. /setup after seeding ════════════════════════════════════════════════

def test_setup_refuses_a_direct_post_once_a_user_exists(anon_client):
    """
    `/setup` is PUBLIC, and the only thing keeping it safe is that it refuses
    once `users` is non-empty. A GET redirect proves nothing on its own: an
    attacker posts the form, they do not browse to it.

    The assertion that matters is the last one — no account was created.
    """
    assert STORE["users"], "precondition: a user exists"

    assert anon_client.get("/setup").status_code in (302, 303)

    response = anon_client.post("/setup", data={
        "username": "adv-pwn-owner", "display_name": "Pwn",
        "password": "pwned-password-1", "confirm_password": "pwned-password-1"})

    assert response.status_code in (302, 303)
    assert auth.find_user("adv-pwn-owner") is None, (
        "an anonymous POST to /setup minted an Owner account on a seeded "
        "install — the whole application is open to anybody who knows the URL")


# ══ 8. Error and edge endpoints ════════════════════════════════════════════

def test_the_404_handler_renders_nothing_to_a_stranger(anon_client):
    """
    `app.errorhandler(404)` redirects to the dashboard, which is itself gated —
    so an anonymous caller lands on `/login`, not on anything useful. The
    assertion is that the redirect body carries no page: a handler that
    *rendered* the dashboard before redirecting would leak it.
    """
    response = anon_client.get("/no/such/page/at/all")
    assert response.status_code in (301, 302)

    body = response.get_data(as_text=True)
    assert "<nav" not in body, "the 404 handler rendered chrome to a stranger"

    onward = anon_client.get(response.headers["Location"])
    assert "/login" in onward.headers.get("Location", ""), (
        "an anonymous 404 did not end at the login page")


def test_the_413_page_is_gated_like_any_other(anon_client, client, hr, owner):
    """
    The 413 handler is the one error page in this app that renders real content
    — `dashboard.too_large_page()`, with the nav on it. So the question is
    whether it can be reached *before* the gate.

    It cannot, and the ordering is visible in the three results: an anonymous
    oversize POST is redirected to login, a signed-in user without the route's
    permission gets **403**, and only a user who would have been allowed
    through sees the 413 page itself. `before_request` runs before the view,
    and the body is not parsed until the view touches `request.form`.
    """
    payload = {"x": "A" * 600_000}

    anonymous = anon_client.post("/boq/create", data=payload)
    assert anonymous.status_code in (302, 303)
    assert "<nav" not in anonymous.get_data(as_text=True), (
        "the too-large page rendered for a caller with no session")

    _as(client, hr)
    assert "boq.create" not in auth.permissions_of(hr)
    assert client.post("/boq/create", data=payload).status_code == 403, (
        "a user without boq.create reached the 413 handler — the gate is "
        "running after the body is parsed")

    _as(client, owner)
    allowed = client.post("/boq/create", data=payload)
    assert allowed.status_code == 413, (
        "the control failed: a permitted user should see the real 413 page")
    assert "<nav" in allowed.get_data(as_text=True)


# ══ 9. Fail-closed, proved by adding a route rather than removing an entry ══

def test_a_route_added_to_the_live_url_map_is_refused(client, owner):
    """
    `test_access_control.py` proves fail-closed by **removing** an endpoint from
    the registry. That is the right shape for a routine test — it leaks nothing
    into the URL map that later sweeps walk — but it proves the converse of
    what actually happens in practice.

    What happens in practice is that somebody **adds a route** and forgets the
    registry. So this does that: a real rule, a real view function, no entry.
    An Owner holding every permission in the catalogue must still be refused,
    because absence is the answer and not a lookup miss to be forgiven.

    The rule is removed in a `finally`, and the last assertion proves it — a
    leaked rule would make `test_every_endpoint_is_classified` fail in every
    later run of the session, which is a confusing way to find out.
    """
    import app as app_module

    rule = Rule("/adv-runtime-leak", endpoint="adv_runtime_leak", methods=["GET"])
    assert "adv_runtime_leak" not in auth.ROUTE_PERMISSIONS

    app_module.app.url_map.add(rule)
    app_module.app.view_functions["adv_runtime_leak"] = lambda: "TOP SECRET LEAKED"
    try:
        _as(client, owner)
        response = client.get("/adv-runtime-leak")
        body = response.get_data(as_text=True)

        assert response.status_code == 403, (
            "an unclassified route served an Owner. Default-deny is not in "
            "force and every route added from here on ships open.")
        assert "TOP SECRET LEAKED" not in body
        assert "no permission declared" in body, (
            "the refusal must say why — INTRODUCTION.md §2: an error that says "
            "only 'invalid' costs somebody an afternoon")
    finally:
        app_module.app.url_map._rules.remove(rule)
        app_module.app.url_map._rules_by_endpoint.pop("adv_runtime_leak", None)
        app_module.app.url_map._remap = True
        app_module.app.view_functions.pop("adv_runtime_leak", None)

    live = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    assert "adv_runtime_leak" not in live, "the throwaway rule leaked"


# ══ 10. The refusal log records the refusal and NOT the credentials ════════

# The eight fields a refusal is allowed to carry. Written as an exact set: a
# ninth added later has to be considered here, which is the point — the log is
# read by an administrator on a screen, and anything in it is disclosed.
LOG_KEYS = {"at", "user", "user_id", "endpoint", "path", "method",
            "permission", "reason"}


def test_the_refusal_log_records_who_what_and_which_permission(client, hr):
    """
    The condition attached to enforcing without B5's audit stage was **block and
    log**. The enumeration test proves no endpoint is *unclassified*; only this
    shows one classified too *tight* — a real user blocked doing their job.
    Without user, endpoint and permission on the record, "it says I cannot" is
    unactionable.
    """
    auth.REFUSAL_LOG.clear()
    _as(client, hr)
    client.get("/boq/")

    assert auth.REFUSAL_LOG, "a refusal was not recorded at all"
    entry = auth.REFUSAL_LOG[0]
    assert entry["user"] == "adv-hr"
    assert entry["endpoint"] == "boq.list_boqs"
    assert entry["permission"] == "boq.view"
    assert entry["reason"] == "permission not held"


def test_the_refusal_log_does_not_capture_credentials(client, hr):
    """
    **A log that captures credentials is a new hole, not a mitigation.**

    `/access-log` is a screen an administrator reads, and the same lines go to
    `app.logger`, which is written to disk and survives a restart. A refused
    POST carries the form body — and a refused POST to a login-ish or
    password-changing route would carry a password in it.

    So this posts a refused request stuffed with things that must not be kept,
    and asserts the entry holds exactly the eight fields it is meant to and
    nothing more. The rendered `/access-log` page is checked too: the log
    structure being clean is no comfort if the page reads something else.
    """
    auth.REFUSAL_LOG.clear()
    _as(client, hr)
    client.post("/boq/create", data={
        "project_name": "X",
        "password": "hunter2-SUPERSECRET",
        "new_password": "another-SECRET-value",
        "session": "eyJ1aWQiOiJzdG9sZW4ifQ.FAKE.SIGNATURE",
        "notes": "A" * 500,
    })

    assert auth.REFUSAL_LOG
    entry = auth.REFUSAL_LOG[0]

    assert set(entry) == LOG_KEYS, (
        f"the refusal log's shape changed: {sorted(set(entry) ^ LOG_KEYS)}. "
        f"Anything added here is disclosed on /access-log and written to the "
        f"server log — check it cannot carry a credential before allowing it.")

    blob = repr(list(auth.REFUSAL_LOG))
    for secret in ("hunter2-SUPERSECRET", "another-SECRET-value",
                   "eyJ1aWQiOiJzdG9sZW4ifQ"):
        assert secret not in blob, (
            f"the refusal log captured {secret!r} out of the form body")

    owner = _user("adv-log-owner", ["role-owner"])
    _as(client, owner)
    page = client.get("/access-log").get_data(as_text=True)
    for secret in ("hunter2", "another-SECRET", "eyJ1aWQi"):
        assert secret not in page, f"/access-log rendered {secret!r}"


# ══ 11. Login response shape — A HOLE, FOUND AND FIXED ═════════════════════

def test_login_says_the_same_thing_however_it_failed(anon_client):
    """
    The body half, which was already correct.

    One message for both failures, one status. Distinguishing "no such user"
    from "wrong password" tells an attacker which half to keep working on, and
    with no rate limiting (ABOUT.md §7 gap 22) that is the difference between
    guessing usernames and guessing passwords for usernames you know are real.
    """
    _user("adv-real-user", ["role-hr"])

    wrong = anon_client.post("/login", data={"username": "adv-real-user",
                                             "password": "not-the-password"})
    unknown = anon_client.post("/login", data={"username": "adv-no-such-person",
                                               "password": "not-the-password"})

    assert wrong.status_code == unknown.status_code == 200

    message = "That username and password do not match."
    assert message in wrong.get_data(as_text=True)
    assert message in unknown.get_data(as_text=True)

    # The only difference between the two bodies is the username echoed back
    # into the form — which is the caller's own input and tells them nothing.
    normalised_wrong = wrong.get_data(as_text=True).replace("adv-real-user", "X")
    normalised_unknown = unknown.get_data(as_text=True).replace("adv-no-such-person", "X")
    assert normalised_wrong == normalised_unknown


def test_login_does_not_leak_which_usernames_exist_by_timing(anon_client):
    """
    **The second hole this file found.** The bodies matched; the clock did not.

    `check_password_hash` is scrypt and costs ~70 ms on this box. It only ran
    when `find_user()` returned a record, so an unknown username was answered
    in ~0.3 ms and a real one in ~70 ms — measured at **239x**. That is not a
    subtle side channel that needs statistics to see; it is visible in a
    browser's network tab, over the internet, on the first try. Pair it with
    gap 22 (no rate limiting, no lockout) and an attacker enumerates every
    valid username in seconds, then brute-forces only those.

    Fixed by hashing against a fixed dummy on the not-found path, so both
    branches pay the same cost. The two must now be within one order of
    magnitude of each other.

    ⚠ **This is a timing test and timing tests flake.** It is deliberately
    written with a very loose bound — 8x, against a defect that measured 239x —
    and takes a median of several runs. It is here to catch the branch being
    removed, not to certify constant-time behaviour, which Python cannot give.
    """
    _user("adv-timed-user", ["role-hr"])

    def elapsed(username: str) -> float:
        start = time.perf_counter()
        anon_client.post("/login", data={"username": username,
                                         "password": "not-the-password"})
        return time.perf_counter() - start

    # One of each first, to pay any import or first-request cost outside the
    # measurement.
    elapsed("adv-timed-user")
    elapsed("adv-no-such-person")

    real = statistics.median(elapsed("adv-timed-user") for _ in range(7))
    ghost = statistics.median(elapsed("adv-no-such-person") for _ in range(7))

    ratio = max(real, ghost) / max(min(real, ghost), 1e-9)
    assert ratio < 8.0, (
        f"/login answers a real username and an unknown one at very different "
        f"speeds ({real * 1000:.1f} ms vs {ghost * 1000:.1f} ms, {ratio:.0f}x). "
        f"That enumerates every valid username in this install regardless of "
        f"what the page says. Hash against a dummy on the not-found path.")
