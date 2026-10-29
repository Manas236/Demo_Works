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

import ast
import pathlib
import re

import pytest

import auth
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent


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
    endpoints = {r.endpoint for r in _rules()}

    # ⚠ **A set difference against an empty left-hand side is empty**, so this
    #   test passes perfectly if `_rules()` ever stops returning anything — an
    #   import that quietly fails to register a blueprint, a filter that stops
    #   matching. The floor is what stops "every endpoint is classified" being
    #   true because there are no endpoints. Measured at 111 classified
    #   endpoints on 30 August 2026, and at **114** later the same day when the
    #   address book grew a view page and the two archive routes; 80 leaves room
    #   to delete a module without
    #   forcing an edit here, and none to delete the application.
    assert len(endpoints) > 80, (
        f"only {len(endpoints)} endpoints in the URL map — the sweep below is "
        f"asserting almost nothing. Has a blueprint failed to register?")

    unclassified = sorted(endpoints - set(auth.ROUTE_PERMISSIONS))
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


def _calls_in(src: str) -> set:
    """
    Every call in a module, as `(first string argument or None, function
    name)` — so `has_perm("x.y")` is `("x.y", "has_perm")` and
    `auth.can_see_pnl()` is `(None, "can_see_pnl")`.

    ⚠ **From the AST, deliberately.** The text equivalent of this is
    satisfied by a comment, which is not a consultation of anything.
    `auth.f()` and a bare `f()` are the same call for this purpose: what
    matters is that the function runs, not how it was imported.
    """
    out = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.attr if isinstance(fn, ast.Attribute)
                else fn.id if isinstance(fn, ast.Name) else "")
        if not name:
            continue
        first = None
        if node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            first = node.args[0].value
        out.add((first, name))
        out.add((None, name))
    return out


def _auth_predicates_for(perm: str) -> list:
    """
    Every zero-argument function in `auth.py` whose whole body is
    `return has_perm("<perm>")`.

    Read from the AST and not by regex: a docstring or a comment that mentions
    the id proves nothing, and the point of the check is that the predicate
    really wraps THIS permission and nothing else. A predicate with any other
    statement in it is not matched — a module must not be let through by a
    function that merely happens to mention the id.
    """
    tree = ast.parse((REPO / "auth.py").read_text(encoding="utf8"))
    out = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.args.args:
            continue
        body = [s for s in node.body
                if not (isinstance(s, ast.Expr)
                        and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str))]
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            continue
        call = body[0].value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "has_perm" and len(call.args) == 1
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == perm):
            out.append(node.name)
    return out


def test_every_catalogue_permission_gates_something():
    """
    And no dead permissions. A checkbox in the role editor that grants access to
    nothing is worse than no checkbox: somebody ticks it, and the access they
    were trying to give silently does not arrive.

    ⚠ **REWRITTEN 8 October 2026 — CC-2 C6, CLIENT_CHANGES.md §0 forty-seventh
    block.** The old assertion, verbatim:

        used = {p for p in auth.ROUTE_PERMISSIONS.values()
                if p not in (auth.PUBLIC, auth.AUTHENTICATED)}
        dead = sorted(set(auth.PERMISSIONS) - used)
        assert not dead, (
            f"these permissions are in the catalogue but gate no endpoint: {dead}. "
            f"Either wire them to a route or take them off the role editor.")

    `project.pnl` gates a PANEL — the Profit & Loss on `/projects/view/<id>`
    and one line under `/projects/` — and no endpoint: both pages stay on
    `project.view`, and inventing a route to satisfy this test would have been
    a page nobody asked for. So the rule now counts a permission as live when
    it gates an endpoint **or** is a DECLARED panel permission — and the
    declaration is held harder than a route entry is: an allowlist of exactly
    one, every page it names a classified, non-public endpoint, and the module
    serving each page consulting it by name. The checkbox's real effect is
    proved in `tests/test_pnl_access.py`, by granting it to a role and seeing
    the panel arrive. A permission that is neither is still refused.
    """
    used = {p for p in auth.ROUTE_PERMISSIONS.values()
            if p not in (auth.PUBLIC, auth.AUTHENTICATED)}
    dead = sorted(set(auth.PERMISSIONS) - used - set(auth.PANEL_PERMISSIONS))
    assert not dead, (
        f"these permissions are in the catalogue but gate no endpoint: {dead}. "
        f"Either wire them to a route or take them off the role editor.")

    # ⚠ The panel permissions. This line is where a new one becomes visible,
    #   and it has now fired once: a second was authorised on 27 October 2026.
    #
    # ⚠ **AMENDED 27 October 2026 — CLIENT_CHANGES.md §0's fifty-fourth
    #   block, item A.** The old assertion, kept verbatim rather than deleted,
    #   because an allowlist that is widened silently is an allowlist nobody
    #   can audit:
    #
    #     assert set(auth.PANEL_PERMISSIONS) == {"project.pnl"}, (
    #         f"auth.PANEL_PERMISSIONS is {sorted(auth.PANEL_PERMISSIONS)}; exactly "
    #         f"one panel permission was authorised (the forty-seventh §0 block)")
    #
    #   `docnum.override` joins it for the same structural reason `project.pnl`
    #   is here: it opens no page. It unlocks a FIELD on eight create forms
    #   that are all gated by their own document permission already, and the
    #   server half of the gate refuses a changed number on the POST. Each of
    #   the two is still held to every other assertion below — named pages,
    #   classified endpoints, and the serving module consulting it by name.
    assert set(auth.PANEL_PERMISSIONS) == {"project.pnl", "docnum.override"}, (
        f"auth.PANEL_PERMISSIONS is {sorted(auth.PANEL_PERMISSIONS)}; exactly "
        f"two panel permissions were authorised (the forty-seventh and "
        f"fifty-fourth §0 blocks)")
    for perm, endpoints in auth.PANEL_PERMISSIONS.items():
        assert perm in auth.PERMISSIONS, f"{perm} is declared but not in the catalogue"
        assert perm not in used, (
            f"{perm} gates an endpoint, so it is not a panel permission — take "
            f"it out of PANEL_PERMISSIONS")
        assert endpoints, f"{perm} names no page to render a panel on"
        for endpoint in endpoints:
            gate = auth.ROUTE_PERMISSIONS.get(endpoint)
            assert gate and gate not in (auth.PUBLIC, auth.AUTHENTICATED), (
                f"{perm} names {endpoint}, which is not a classified, "
                f"permission-gated endpoint")
            module = endpoint.split(".", 1)[0]
            src = (REPO / f"{module}.py").read_text(encoding="utf8")
            # ⚠ **REWRITTEN 29 October 2026 (§0 fifty-eighth block, item 4),
            #   and the old assertion is kept verbatim below.** It required
            #   the literal `has_perm("<perm>")` in the serving module, and
            #   `dashboard.py` cannot carry it:
            #   `test_nav_visibility.py::test_the_dashboard_names_no_permission
            #   _id_anywhere_in_its_code` **forbids** a permission id written
            #   as a string anywhere in that file, because a card that names
            #   one is a second list beside `ROUTE_PERMISSIONS`. The two
            #   assertions became mutually exclusive the moment the P&L
            #   reached the dashboard.
            #
            #   What this assertion is FOR is unchanged and is still proved:
            #   *the serving module really consults this permission, so the
            #   checkbox is not a lie.* A module may now do it through a
            #   **named predicate in `auth.py`** instead — and the predicate
            #   is read and proved to wrap THIS permission, so the chain is
            #   verified end to end rather than assumed. Nothing is excused by
            #   name: a module that consults neither still fails.
            #
            #   The old assertion, verbatim:
            #       assert f'has_perm("{perm}")' in src, (
            #           f"{module}.py serves {endpoint} and never consults {perm} by "
            #           f"name — the checkbox would grant nothing there")
            # ⚠ **BOTH halves read the module's AST, not its text.** A
            #   substring check is satisfied by a COMMENT — measured: with
            #   `can_pnl = True` in `dashboard.py` and a comment above it
            #   naming `auth.can_see_pnl()`, the text version of this
            #   assertion passed. A comment is not a consultation.
            calls = _calls_in(src)
            direct = (perm, "has_perm") in calls
            via = [fn for fn in _auth_predicates_for(perm)
                   if (None, fn) in calls]
            assert direct or via, (
                f"{module}.py serves {endpoint} and never consults {perm} — "
                f"not as has_perm('{perm}') and not through a predicate in "
                f"auth.py that returns has_perm('{perm}'). The checkbox "
                f"would grant nothing there")


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
