"""
What the launcher offers, per role — and the rule that it never decides anything.

Before 27 August 2026 every nav entry and all fifteen dashboard cards were shown
to everybody. Clicking one you had no permission for refused correctly, which is
the important half; it should not have been on the page in the first place,
which is this half.

### The one rule this file exists to hold

**Visibility is derived from `auth.ROUTE_PERMISSIONS` — the same dict `_gate()`
answers from — and hiding never replaces the gate.** A second, hand-maintained
list of "what to show" drifts from the list of "what to allow", and every drift
is either a dead link or, far worse, a hidden entry somebody believes is closed.
So `auth.can_reach()` reads the registry, and the first test below sweeps all
seven roles against every classified endpoint asserting that it says exactly
what the gate does.

The second half is asserted just as hard: **every hidden card is hit directly by
URL and must still be refused.** A test suite that only checked the page would
pass just as well against an application that had deleted its permission checks
and hidden the buttons instead.

### Why the expectations are written out longhand

The per-role tables below are literals, not derived from `BUILTIN_ROLES`.
Deriving them would make this file assert that the role table equals itself —
the same argument
`test_access_control_adversarial.py::test_each_role_gets_exactly_the_admin_access_it_should`
makes for its six administration URLs. If the client changes what a role means,
these tables are supposed to fail and be re-read by a person.
"""

import ast
import pathlib

import pytest

import auth
import dashboard
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

ROLES = ["owner", "director", "operation-head", "hr", "sales-manager",
         "purchase-manager", "accountant"]

# What each role's nav must offer. `Projects` and `Settings` are the only two
# entries the nav has ever had; the chip beside them is AUTHENTICATED and is
# `tests/test_nav_user_chip.py`'s business, not this file's.
EXPECTED_NAV = {
    "owner":            ["Projects", "Settings"],
    "director":         ["Projects", "Settings"],
    "operation-head":   ["Projects"],
    "hr":               [],
    "sales-manager":    ["Projects"],
    "purchase-manager": ["Projects"],
    "accountant":       ["Projects"],
}

ALL_CARDS = [
    "Quotations", "Proforma Invoices", "Tax Invoices",
    "Projects", "Bills of Quantities", "Running Account Bills",
    "Delivery Challans",
    "Purchase Orders", "Draft Purchase Orders", "Employee & Misc Charges",
    "Product Catalogue", "Spec Library", "Client Register", "Address Book",
    "Market News", "Users &amp; Access",
]

EXPECTED_CARDS = {
    "owner":    ALL_CARDS,
    "director": ALL_CARDS,
    "operation-head": [
        "Projects", "Bills of Quantities", "Running Account Bills",
        "Delivery Challans", "Purchase Orders", "Draft Purchase Orders",
        "Employee & Misc Charges", "Product Catalogue", "Spec Library",
        "Client Register", "Address Book"],
    # B4's one stated restriction, seen from the other side: HR is the narrowest
    # role in the system and its dashboard is two cards.
    "hr": ["Employee & Misc Charges", "Address Book"],
    "sales-manager": [
        "Quotations", "Proforma Invoices", "Tax Invoices", "Projects",
        "Bills of Quantities", "Running Account Bills", "Product Catalogue",
        "Spec Library", "Client Register", "Address Book"],
    "purchase-manager": [
        "Projects", "Bills of Quantities", "Delivery Challans",
        "Purchase Orders", "Draft Purchase Orders", "Product Catalogue",
        "Spec Library", "Address Book"],
    "accountant": [
        "Proforma Invoices", "Tax Invoices", "Projects",
        "Bills of Quantities", "Running Account Bills", "Purchase Orders",
        "Client Register"],
}

EXPECTED_GROUPS = {
    "owner":            ["Sell side", "Projects", "Buy side", "Library"],
    "director":         ["Sell side", "Projects", "Buy side", "Library"],
    "operation-head":   ["Projects", "Buy side", "Library"],
    "hr":               ["Buy side", "Library"],
    # No Buy side at all: a Sales Manager holds no purchase, draft-PO, challan
    # or charge permission, so the heading would stand over nothing.
    "sales-manager":    ["Sell side", "Projects", "Library"],
    "purchase-manager": ["Projects", "Buy side", "Library"],
    "accountant":       ["Sell side", "Projects", "Buy side", "Library"],
}

# Card title -> the endpoint it opens. Used to hit hidden cards directly.
CARD_ENDPOINT = {
    "Quotations":                 "quotation.list_quotations",
    "Proforma Invoices":          "proforma.list_proformas",
    "Tax Invoices":               "invoice.list_invoices",
    "Projects":                   "project.list_projects",
    "Bills of Quantities":        "boq.list_boqs",
    "Running Account Bills":      "ra.list_ras",
    "Delivery Challans":          "challan.list_dcs",
    "Purchase Orders":            "purchase.list_purchases",
    "Draft Purchase Orders":      "po_draft.list_pos",
    "Employee & Misc Charges": "charge.list_charges",
    "Product Catalogue":          "product.list_products",
    "Spec Library":               "spec.list_specs",
    "Client Register":            "client.list_clients",
    "Address Book":               "address.list_addresses",
    "Market News":                "extractor.index",
    "Users &amp; Access":         "auth.list_users",
}


# ── Helpers ────────────────────────────────────────────────────────────────

# ── The autouse fixture that used to live here was DELETED on 28 August 2026 ──
#
# `builtin_roles_as_shipped` reset all seven roles to `BUILTIN_ROLES` before
# every test in this file, for one reason:
# `test_auth.py::test_editing_a_role_takes_effect_without_signing_in_again`
# appended `boq.view` to HR and never took it off, and roles live in one shared
# dict that `conftest._fresh_store()` deliberately does not clear.
#
# **That was a workaround in the wrong file.** A test that pollutes global state
# is a defect regardless of what it is testing, and the leaking test now
# restores what it changed in a `finally` and asserts that it did. With the
# mutation contained at its source there is nothing here to undo, and a fixture
# that resets the roles would hide the next leak instead of surfacing it —
# every table below is written against the roles **as shipped**, so if one is
# ever edited and not put back, this file is exactly where it should fail.


def _user(slug: str) -> dict:
    name = f"vis-{slug}"
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="visibility-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


def _dashboard(client, slug: str) -> str:
    auth.ensure_builtin_roles()
    _as(client, _user(slug))
    response = client.get("/")
    assert response.status_code == 200, f"role {slug} cannot load the dashboard"
    return response.get_data(as_text=True)


def _nav_labels(html: str) -> list:
    """The text of each `.nav-link`, in the order the nav renders them."""
    import re

    block = html[html.index('<div class="nav-right">'):html.index("</nav>")]
    return re.findall(r'class="nav-link">.*?</svg>([^<]+)</a>', block, re.S)


def _card_titles(html: str) -> list:
    import re

    return re.findall(r'<div class="card-title">(.*?)</div>', html)


def _group_headings(html: str) -> list:
    """The `.mg-hd` headings only — not every `<h3>` the page happens to have."""
    import re

    return [h.split("&")[0].strip()
            for h in re.findall(r'<div class="mg-hd">.*?<h3>(.*?)</h3>', html, re.S)]


def _is_refused(response) -> bool:
    """The gate's two shapes: a 403 refusal page, or a bounce to /login."""
    if response.status_code == 403:
        return True
    if response.status_code in (301, 302, 303, 307, 308):
        return "/login" in response.headers.get("Location", "")
    return False


# ══ 1. The predicate the whole thing hangs on ══════════════════════════════

@pytest.mark.parametrize("slug", ROLES)
def test_can_reach_agrees_with_the_gate_on_every_endpoint_for_every_role(
        client, slug):
    """
    Every classified GET endpoint, requested for real, compared with what
    `auth.can_reach()` said would happen.

    This is the test that makes deriving visibility from the registry mean
    something. `can_reach()` re-states `_gate()`'s branches in a second
    function, and two functions that must agree are two functions that can
    disagree — so they are made to answer the same 80-odd questions and
    compared. A disagreement in the "shown but refused" direction is a dead
    link; in the "hidden but allowed" direction it is a page nobody can find.

    Routes taking an `<id>` are requested with a placeholder. The gate runs
    before the view, so what comes back is the gate's answer whether or not the
    record exists.
    """
    import app as app_module

    auth.ensure_builtin_roles()
    user = _user(slug)
    _as(client, user)

    disagreements = []
    for rule in app_module.app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.endpoint not in auth.ROUTE_PERMISSIONS:
            continue
        # `/setup` is PUBLIC and the gate does let it through. The **view** then
        # redirects to /login because users exist — "public conditionally", the
        # window that closes by itself. That is not the gate refusing, and a
        # sweep reading status codes cannot tell the two apart, so it is named
        # here and asserted on its own below.
        if rule.endpoint == "auth.setup":
            continue
        url = rule.rule
        for arg in rule.arguments:
            url = url.replace(f"<{arg}>", "placeholder").replace(
                f"<path:{arg}>", "placeholder")
        if "<" in url:
            continue

        predicted = auth.can_reach(rule.endpoint, user)
        refused = _is_refused(client.get(url))
        if predicted == refused:
            disagreements.append(
                f"{rule.endpoint} ({url}): can_reach={predicted}, "
                f"the gate {'refused' if refused else 'allowed'} it")

    assert not disagreements, (
        f"can_reach() and _gate() disagree for role {slug!r}:\n  "
        + "\n  ".join(disagreements))
    assert auth.can_reach("auth.setup", user), (
        "/setup is PUBLIC in the registry and can_reach must say so. What "
        "closes it once users exist is the view, not the gate.")


def test_can_reach_refuses_an_endpoint_that_is_not_in_the_registry(client):
    """
    Absence is False here for the same reason absence is a refusal in the gate.
    A launcher that offered an unclassified route would draw a card nobody —
    including an Owner — can open.
    """
    auth.ensure_builtin_roles()
    owner = _user("owner")
    assert not auth.can_reach("some.route_added_later", owner)
    assert auth.can_reach("dashboard.index", owner)


def test_can_reach_is_false_for_a_stranger():
    """No session, nothing offered — the nav is never drawn for one anyway."""
    import app as app_module

    with app_module.app.test_request_context("/"):
        assert not auth.can_reach("boq.list_boqs")
        assert auth.can_reach("auth.login"), "PUBLIC must stay reachable"


# ══ 2. What each role actually sees ════════════════════════════════════════

@pytest.mark.parametrize("slug", ROLES)
def test_the_nav_offers_exactly_what_the_role_may_reach(client, slug):
    """Two entries, seven roles, written out rather than derived."""
    labels = _nav_labels(_dashboard(client, slug))
    assert labels == EXPECTED_NAV[slug], (
        f"role {slug!r} nav is {labels}, expected {EXPECTED_NAV[slug]}")


@pytest.mark.parametrize("slug", ROLES)
def test_the_launcher_offers_exactly_what_the_role_may_reach(client, slug):
    """
    Sixteen cards, seven roles. HR sees two of them, which is what B4's one
    stated restriction looks like from the dashboard.
    """
    titles = _card_titles(_dashboard(client, slug))
    assert titles == EXPECTED_CARDS[slug], (
        f"role {slug!r} sees {titles}\n  expected {EXPECTED_CARDS[slug]}\n"
        f"  extra:   {[t for t in titles if t not in EXPECTED_CARDS[slug]]}\n"
        f"  missing: {[t for t in EXPECTED_CARDS[slug] if t not in titles]}")


@pytest.mark.parametrize("slug", ROLES)
def test_a_group_whose_cards_are_all_hidden_takes_its_heading_with_it(
        client, slug):
    """
    "Buy side — money out" over an empty box tells a Sales Manager there is
    something they are missing. The heading goes with its last card.
    """
    headings = _group_headings(_dashboard(client, slug))
    assert headings == EXPECTED_GROUPS[slug], (
        f"role {slug!r} sees group headings {headings}, "
        f"expected {EXPECTED_GROUPS[slug]}")


def test_a_role_that_reaches_no_register_gets_no_modules_zone(client):
    """
    The whole zone goes when its last group does — and says so, rather than
    leaving a title over an empty page that reads as a page that failed to
    load.
    """
    auth.ensure_builtin_roles()
    auth.roles()["role-bare"] = {
        "id": "role-bare", "name": "Bare", "builtin": False,
        "permissions": ["dashboard.view"]}
    bare = auth.create_user("vis-bare", "Bare", "vis-bare-password-1",
                            ["role-bare"], created_by="visibility-test")
    _as(client, bare)

    html = client.get("/").get_data(as_text=True)
    assert '<h2>Modules</h2>' not in html, "an empty Modules zone was rendered"
    assert '<div class="mods">' not in html
    assert "Nothing to show here yet" in html, (
        "a user who reaches nothing got a bare page rather than an explanation")
    assert 'class="dash-actions"' not in html, (
        "an empty action bar was rendered")


def test_the_quotation_surfaces_go_together(client):
    """
    The action buttons and the whole pipeline band read the quotation register.
    Showing an Operation Head "New quotation", "Register" and a panel of links
    into it would be a dozen refusals in a row on the landing page.
    """
    ops = _dashboard(client, "operation-head")
    assert "New quotation" not in ops and ">Register<" not in ops
    assert 'href="/quotation' not in ops, (
        "the landing page still links into the quotation register for a role "
        "holding no quotation.view — the pipeline band was not suppressed")

    sales = _dashboard(client, "sales-manager")
    assert "New quotation" in sales, "the control for a role that holds it went too"
    assert 'href="/quotation' in sales, (
        "the band went for a role that does hold quotation.view")


# ══ 3. Hiding is presentation. The gate is the gate. ═══════════════════════

@pytest.mark.parametrize("slug", ROLES)
def test_every_hidden_card_is_still_refused_when_hit_directly(client, slug):
    """
    **The half that matters.** A suite that only read the page would pass
    against an application that had deleted its permission checks and hidden
    the buttons instead.

    Every card this role does not see, requested by URL. Paired with the
    control below, which requires the visible ones to open.
    """
    from flask import url_for

    import app as app_module

    hidden = [t for t in ALL_CARDS if t not in EXPECTED_CARDS[slug]]
    auth.ensure_builtin_roles()
    _as(client, _user(slug))

    still_open = []
    with app_module.app.test_request_context():
        urls = {t: url_for(CARD_ENDPOINT[t]) for t in hidden}
    for title, url in urls.items():
        if not _is_refused(client.get(url)):
            still_open.append(f"{title} ({url})")

    assert not still_open, (
        f"role {slug!r} cannot see these cards but can still open them — "
        f"hiding has been mistaken for a permission check: {still_open}")


@pytest.mark.parametrize("slug", ROLES)
def test_every_visible_card_actually_opens(client, slug):
    """
    The control. Without it, a role locked out of everything would score a
    clean pass on the test above.
    """
    from flask import url_for

    import app as app_module

    auth.ensure_builtin_roles()
    _as(client, _user(slug))

    with app_module.app.test_request_context():
        urls = {t: url_for(CARD_ENDPOINT[t]) for t in EXPECTED_CARDS[slug]}
    refused = [f"{t} ({u})" for t, u in urls.items()
               if _is_refused(client.get(u))]

    assert not refused, (
        f"role {slug!r} is offered cards it cannot open: {refused}")


def test_the_gate_still_runs_on_a_route_the_nav_no_longer_offers(client):
    """
    Named separately from the sweep because it is the sentence, not a sample:
    `/settings/` is off an Operation Head's nav, and `/settings/` still refuses
    an Operation Head.
    """
    auth.ensure_builtin_roles()
    _as(client, _user("operation-head"))

    assert "Settings" not in _nav_labels(client.get("/").get_data(as_text=True))
    assert client.get("/settings/").status_code == 403


# ══ 4. No second list ══════════════════════════════════════════════════════

def test_the_dashboard_names_no_permission_id_anywhere_in_its_code():
    """
    The mechanism, asserted rather than trusted.

    Every card and nav entry names an **endpoint** and asks `can_reach()`. The
    moment one of them names a permission id instead, there are two lists — the
    registry and this file — and they can disagree without anything failing.
    Read from the AST, so the docstring that mentions `admin.users` in prose
    does not trip it.
    """
    tree = ast.parse((REPO / "dashboard.py").read_text(encoding="utf8"))

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))

    offenders = sorted({
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value in auth.PERMISSIONS and id(node) not in docstrings})

    assert not offenders, (
        f"dashboard.py names these permission ids in code: {offenders}. "
        f"Navigation must ask can_reach(<endpoint>) so there is one list, not "
        f"two — see auth.can_reach().")


def test_every_endpoint_the_launcher_names_is_classified():
    """
    A card pointing at an unclassified endpoint would be invisible to everybody
    (absence is a refusal), which is a silent way to delete a module from the
    application.
    """
    named = set(CARD_ENDPOINT.values()) | {e for e, _, _ in dashboard.NAV_ITEMS}
    unclassified = sorted(e for e in named if e not in auth.ROUTE_PERMISSIONS)
    assert not unclassified, (
        f"the launcher offers unclassified endpoints: {unclassified}")
