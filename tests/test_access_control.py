"""
Default deny, proved by enumeration rather than by trust.

`tests/conftest.py`'s `client` fixture signs in, which is what lets the ~920
tests written before Phase 3B keep passing — and it means **not one of them can
tell you whether a route is reachable without a session.** Every test in this
file uses `anon_client` or mints its own user, and this file is the whole of the
evidence that the application is actually closed.

Three properties, and they fail for different reasons:

* **Every endpoint is classified.** `auth.ROUTE_PERMISSIONS` is a second thing
  to keep in step with the routes, and the honest cost of a central registry
  over a decorator is that it can fall behind. `test_every_endpoint_is_classified`
  is what stops it — a route added in a later pass fails this test the day it is
  registered. It is load-bearing. Do not weaken it, and do not "fix" a failure
  by deleting the endpoint from the sweep.

* **Absence refuses.** The reason the registry is worth its cost. A decorator
  scheme fails *open* when somebody forgets one; this fails closed, and
  `test_an_unregistered_endpoint_is_refused` is the proof rather than the claim.

* **The permission is the thing being checked** — not "is anybody logged in".
  `test_a_user_without_the_permission_is_refused` pairs a refusal and an
  allowance on the same URL, so a gate that let everybody through once they had
  any session would fail it.
"""

import re

import pytest

import auth
from store import STORE


# ── Building a concrete URL for every rule ─────────────────────────────────

def _concrete(rule) -> str:
    """
    The rule with a dummy value in every parameter.

    The ids do not need to exist. `auth._gate()` runs as a `before_request`
    hook, so it answers before the view is ever called — which is the point: a
    stranger must be refused on `/ra/print/<a real id>` without our having to
    hand them one to prove it.
    """
    path = rule.rule
    for arg in rule.arguments:
        path = re.sub(r"<[^<>]*\b" + re.escape(arg) + r">", "zz-no-such-id", path)
    return path


def _method(rule) -> str:
    """GET where the rule allows it, else POST — a POST-only rule 405s on GET,
    and a 405 is raised during routing, before any `before_request` runs."""
    return "GET" if "GET" in rule.methods else "POST"


def _rules():
    import app as app_module
    return sorted(app_module.app.url_map.iter_rules(), key=lambda r: r.rule)


# ── 1. The registry keeps up with the routes ───────────────────────────────

def test_every_endpoint_is_classified():
    """
    Every endpoint in the URL map has an entry in `ROUTE_PERMISSIONS`.

    ⚠ **This is the test that makes default-deny non-optional for future work.**
    Without it the registry silently falls behind the routes, and the first
    anyone hears of it is a page nobody can open — or, if the default were ever
    flipped, a page everybody can.

    It fails *before* the app is unreachable, not after: an unclassified route
    is refused at runtime for everybody including an Owner, so this red test is
    the cheap version of that discovery.
    """
    unclassified = sorted({r.endpoint for r in _rules()} - set(auth.ROUTE_PERMISSIONS))
    assert not unclassified, (
        f"these endpoints have no entry in auth.ROUTE_PERMISSIONS and are "
        f"therefore refused to everybody, including an Owner: {unclassified}. "
        f"Classify each one — a permission id from auth.PERMISSIONS, or "
        f"auth.PUBLIC / auth.AUTHENTICATED with a comment saying why.")


def test_the_registry_names_no_endpoint_that_no_longer_exists():
    """
    The other direction. A stale entry is not dangerous, but it is a lie about
    the access matrix, and this file's whole claim is that the matrix can be
    read in one place and believed.
    """
    stale = sorted(set(auth.ROUTE_PERMISSIONS) - {r.endpoint for r in _rules()})
    assert not stale, (
        f"auth.ROUTE_PERMISSIONS classifies endpoints that are not registered: "
        f"{stale}. A renamed or deleted route leaves its entry behind.")


def test_every_registry_permission_is_a_real_permission():
    """
    A registry entry naming a permission that is not in `PERMISSIONS` gates a
    route on a string nothing can grant — the route is unreachable, and the
    role editor cannot even show you why.
    """
    sentinels = {auth.PUBLIC, auth.AUTHENTICATED}
    bogus = sorted({p for p in auth.ROUTE_PERMISSIONS.values()
                    if p not in sentinels and p not in auth.PERMISSIONS})
    assert not bogus, f"registry entries name unknown permissions: {bogus}"


def test_every_catalogue_permission_gates_something():
    """
    And no dead permissions. A checkbox in the role editor that grants access to
    nothing is worse than no checkbox: somebody ticks it, and the access they
    were trying to give silently does not arrive.
    """
    used = {p for p in auth.ROUTE_PERMISSIONS.values()
            if p not in (auth.PUBLIC, auth.AUTHENTICATED)}
    dead = sorted(set(auth.PERMISSIONS) - used)
    assert not dead, (
        f"these permissions are in the catalogue but gate no endpoint: {dead}. "
        f"Either wire them to a route or take them off the role editor.")


# ── 2. Anonymous callers are refused everywhere that is not public ─────────

def test_no_non_public_endpoint_is_reachable_without_a_session(anon_client):
    """
    The sweep that matters. Every non-public endpoint, requested with **no
    cookie at all**, must redirect to the login page or refuse outright.

    Read off `app.url_map`, so a route added later is covered the day it is
    registered rather than the day somebody remembers this file exists.
    """
    leaked = []
    for rule in _rules():
        declared = auth.ROUTE_PERMISSIONS.get(rule.endpoint)
        if declared == auth.PUBLIC:
            continue
        url = _concrete(rule)
        r = anon_client.open(url, method=_method(rule))

        if r.status_code in (302, 303):
            target = r.headers.get("Location", "")
            if "/login" not in target and "/setup" not in target:
                leaked.append(f"{rule.endpoint} {url} -> 302 {target}")
        elif r.status_code != 403:
            leaked.append(f"{rule.endpoint} {url} -> {r.status_code}")

    assert not leaked, (
        "these endpoints answered an anonymous caller with something other than "
        "a login redirect or a 403:\n  " + "\n  ".join(leaked))


def test_the_public_endpoints_are_the_three_we_meant(anon_client):
    """
    The control for the sweep above.

    If every endpoint were quietly PUBLIC that sweep would pass by skipping
    everything. This pins the public set to exactly what it should be, so
    widening it is a deliberate edit to a named list and not a side effect.
    """
    public = sorted(e for e, p in auth.ROUTE_PERMISSIONS.items() if p == auth.PUBLIC)
    assert public == ["auth.login", "auth.setup", "static"]


def test_the_login_page_is_actually_reachable_anonymously(anon_client):
    """The other half of the control: PUBLIC must really mean reachable, or the
    sweep above is asserting that a broken app is a secure one."""
    r = anon_client.get("/login")
    assert r.status_code == 200
    assert "password" in r.get_data(as_text=True).lower()


# ── 3. It is the permission being checked, not merely the session ──────────

@pytest.fixture()
def two_users(client):
    """An HR user and an Owner. HR carries no `boq.view`; Owner carries all."""
    auth.ensure_builtin_roles()
    for name in ("acl-hr", "acl-owner"):
        existing = auth.find_user(name)
        if existing:
            del STORE["users"][existing["id"]]
    hr = auth.create_user("acl-hr", "HR Person", "acl-hr-password",
                          ["role-hr"], created_by="test")
    owner = auth.create_user("acl-owner", "Owner Person", "acl-owner-password",
                             ["role-owner"], created_by="test")
    yield {"hr": hr, "owner": owner}


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


def test_a_user_without_the_permission_is_refused_where_a_holder_is_allowed(
        client, two_users):
    """
    Both halves on one URL, deliberately.

    A refusal on its own does not show the gate is checking the *permission* —
    a gate that refused everybody, or one that had simply broken the page, would
    produce the same 403. Pairing it with a success on the same URL, differing
    only in which user is signed in, is what makes this evidence.
    """
    assert "boq.view" not in auth.permissions_of(two_users["hr"])
    assert "boq.view" in auth.permissions_of(two_users["owner"])

    _as(client, two_users["hr"])
    refused = client.get("/boq/")
    assert refused.status_code == 403, "HR holds no boq.view but reached /boq/"
    assert "boq.view" in refused.get_data(as_text=True), (
        "the refusal page must name the permission that is missing — "
        "INTRODUCTION.md §2: an error that says only 'invalid' costs somebody "
        "an afternoon")

    _as(client, two_users["owner"])
    assert client.get("/boq/").status_code == 200


def test_permissions_are_the_union_of_several_roles(client, two_users):
    """
    B4: "One user may hold several roles — the client explicitly wants Sales and
    Purchase linkable." The effective set is the union, so a user holding both
    reaches both registers.
    """
    user = auth.create_user("acl-both", "Both", "acl-both-password",
                            ["role-sales-manager", "role-purchase-manager"],
                            created_by="test")
    perms = auth.permissions_of(user)
    assert "quotation.create" in perms   # from Sales Manager
    assert "purchase.create" in perms    # from Purchase Manager

    _as(client, user)
    assert client.get("/quotation/").status_code == 200
    assert client.get("/purchase/").status_code == 200
    # And still not everything: neither role carries the wages ledger, which is
    # B4's one stated restriction.
    assert client.get("/charge/").status_code == 403


def test_a_deactivated_user_is_refused_mid_session(client, two_users):
    """
    B3 sells the client "urgent access removal when someone is dismissed".
    That has to mean *now*, not at their next sign-in — the session is resolved
    against the store on every request, so the next click is the last one.
    """
    _as(client, two_users["owner"])
    assert client.get("/boq/").status_code == 200

    two_users["owner"]["active"] = False
    r = client.get("/boq/")
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("Location", "")


# ── 4. Fail-closed, proved rather than claimed ─────────────────────────────

def test_an_unregistered_endpoint_is_refused(client, two_users):
    """
    **The property the whole design rests on.**

    An endpoint absent from `ROUTE_PERMISSIONS` is refused — to everybody,
    including an Owner who holds every permission there is. That is what makes
    a route added in a later pass fail closed instead of shipping open, and it
    is the one thing a decorator scheme cannot give you, because a forgotten
    decorator is indistinguishable from a route that was meant to be open.

    Proved by removing a real endpoint from the registry rather than by adding
    a route to the live URL map, which would leak into every sweep that walks
    it afterwards.
    """
    _as(client, two_users["owner"])
    assert client.get("/boq/").status_code == 200, "precondition: the Owner can reach /boq/"

    saved = auth.ROUTE_PERMISSIONS.pop("boq.list_boqs")
    try:
        r = client.get("/boq/")
        assert r.status_code == 403, (
            "an endpoint with no registry entry was served. Default-deny is not "
            "in force, and every route added from here on ships open.")
        assert "no permission declared" in r.get_data(as_text=True)
    finally:
        auth.ROUTE_PERMISSIONS["boq.list_boqs"] = saved

    assert client.get("/boq/").status_code == 200, "the registry was not restored"


def test_the_refusal_was_logged(client, two_users):
    """
    The condition attached to enforcing without B5's audit stage: block **and
    log**. The enumeration tests above prove no endpoint is unclassified; only
    the log shows one classified too *tight* — a permission scoped so narrowly
    that a real user is blocked doing their job. Without user, endpoint and
    permission on the record, "it says I cannot" is unactionable.
    """
    auth.REFUSAL_LOG.clear()
    _as(client, two_users["hr"])
    client.get("/boq/")

    assert auth.REFUSAL_LOG, "a refusal was not recorded"
    entry = auth.REFUSAL_LOG[0]
    assert entry["user"] == "acl-hr"
    assert entry["endpoint"] == "boq.list_boqs"
    assert entry["permission"] == "boq.view"
    assert entry["path"] == "/boq/"


def test_the_access_log_page_is_owner_gated(client, two_users):
    """The log names who tried to reach what, so it is not for everybody."""
    _as(client, two_users["hr"])
    assert client.get("/access-log").status_code == 403

    _as(client, two_users["owner"])
    assert client.get("/access-log").status_code == 200
