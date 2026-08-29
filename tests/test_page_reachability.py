"""
tests/test_page_reachability.py — an island is a page nobody can find
=====================================================================

`tests/test_nav_reachability.py` already sweeps **landing pages** — classified
GET endpoints taking no path arguments — and requires each to be a nav entry, a
launcher card, a `+ New` form its own register offers, or a named exception.
That test is why the employee master got its nav entry.

It has two blind spots, and this file is both of them.

**1. It never looks at a page with a path argument.** 64 of the 109 classified
GET endpoints take one — every `/view/<id>`, `/edit/<id>`, `/print/<id>` in the
application. A register is only a way in if it actually links to the pages it
lists, and nothing asserted that it did.

**2. It cannot see an island.** Pass C found `employee.list_employees` with
**eight inbound links, every one of them inside `employee.py`** — a module that
linked to itself beautifully and that nothing outside it linked into. Counting
inbound links would have called that page well-connected. The question is not
"does anything link here", it is "can you get here **from a page you can already
reach**", and that is a graph problem rather than a grep.

So this file walks the graph. Roots are the places a user actually starts — the
nav, the launcher cards, the pre-session pages — and an edge is a `url_for()`
this codebase emits. Anything the walk does not reach is an island.

How the edges are derived, and where the approximation is
---------------------------------------------------------
There are 547 `url_for()` calls across the app modules and essentially no
literal `href="/…"` paths, so the call sites are a faithful link graph. Each
module is AST-parsed and every `url_for("endpoint")` with a **literal** first
argument is attributed to the top-level function containing it:

* the function **is** a view (its name is an endpoint) → a precise edge from
  that page to the one it links to;
* the function is a helper (`_nav()`, `_shell()`, a row renderer) → the link is
  put in a **module-wide** bucket, available from any reachable page in that
  module, because a helper's output lands on whichever page called it.

⚠ **That bucket is an over-approximation and it makes this test optimistic.** A
helper's links are credited to the whole module, so a genuinely stranded page in
an otherwise reachable module can be missed. The alternative — attributing a
helper's output to its callers — needs a call graph, and a reachability test
that reports pages falsely is a test somebody deletes. **It under-reports rather
than over-reports, deliberately.** `url_for()` calls with a computed endpoint
are counted and asserted to stay rare for the same reason.
"""

import ast
import pathlib
import re

import auth
import dashboard

REPO = pathlib.Path(__file__).resolve().parent.parent


# ═════════════════════════════════════════════════════════════════════════════
# Deliberate exceptions — a page the walk will not reach, and should not.
#
# ⚠ Adding a name here is a decision, not a formality. It says somebody looked
# at this page and concluded it genuinely has no inbound link, with the reason
# written beside it. `tests/test_nav_reachability.py`'s `UNLINKED_ON_PURPOSE` is
# the same idea one level up, and `auth.access_log` is the shape of a good
# entry: linked from `/users`, kept off the launcher on purpose because an
# in-memory `deque(maxlen=500)` diagnostic is not an audit trail.
# ═════════════════════════════════════════════════════════════════════════════
NO_INBOUND_LINK_BY_DESIGN = {
    # ── Pre-session: you arrive here, you are not sent here from a page ──
    "auth.login":
        "pre-session. `auth._standalone()` draws it with no nav at all, because "
        "every nav entry would refuse somebody with no session.",
    "auth.setup":
        "pre-session, and it closes itself once one user exists. On a fresh "
        "database every URL redirects here; after that nothing may link to it.",

    # ── The landing page ──
    "dashboard.index":
        "the nav brand IS this link, on every page in the application.",

    # ── Flask's own ──
    "static":
        "Flask registers this endpoint itself. This app has NO /static "
        "directory — CSS is Python constants and images are base64 data URIs — "
        "so nothing links to it and nothing should.",
}


# ═════════════════════════════════════════════════════════════════════════════
# The graph
# ═════════════════════════════════════════════════════════════════════════════

def _classified_get_endpoints(flask_app) -> set:
    """Every classified endpoint a user can arrive at with a GET."""
    return {r.endpoint for r in flask_app.url_map.iter_rules()
            if "GET" in (r.methods or ()) and r.endpoint in auth.ROUTE_PERMISSIONS}


def _module_path(name: str):
    p = REPO / f"{name}.py"
    return p if p.exists() else None


def _link_edges():
    """
    `(precise, module_wide, computed)`.

    `precise[endpoint]`      -> endpoints that page's own view function links to
    `module_wide[module]`    -> endpoints a helper in that module links to
    `computed`               -> `url_for(<not a literal>)` sites still unresolved

    ⚠ **A literal first argument is not the only way this codebase names an
    endpoint, and assuming it was made the first draft of this file report 16
    pages as islands when every one of them was linked.** Two idioms put the
    name somewhere else:

        ra.py       `_gated("Delete", "ra.delete_ra", ...)` — a helper takes the
                    endpoint as a parameter and the NAME is a literal at the
                    call site, in the same function.
        approval.py `url_for("approval.approve_" + doc_key, ...)` — one handler
                    per document type, addressed by a built-up prefix.

    So the walk collects, per function, every string literal that **is** a known
    endpoint and every literal that is a **strict prefix** of one or more known
    endpoints. Both are conservative in the direction that matters: they can only
    add edges, and a literal that names an endpoint in a page-rendering function
    is a link in every case in this codebase.

    The module-level `ROUTE_PERMISSIONS` and `NAV_ITEMS` tables are full of
    endpoint names and are **not** functions, so this walk never sees them —
    which is the only reason the rule above is safe.
    """
    known = set(auth.ROUTE_PERMISSIONS)
    precise, module_wide = {}, {}
    computed = 0

    modules = {ep.split(".", 1)[0] for ep in auth.ROUTE_PERMISSIONS}
    for mod in sorted(modules):
        path = _module_path(mod)
        if path is None:                       # e.g. Flask's own `static`
            continue
        tree = ast.parse(path.read_text(encoding="utf8"))

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            targets, mentions_url_for = set(), False
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "url_for"):
                    mentions_url_for = True
                    first = sub.args[0] if sub.args else None
                    if not (isinstance(first, ast.Constant)
                            and isinstance(first.value, str)):
                        computed += 1
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    text = sub.value
                    if text in known:
                        targets.add(text)
                    elif "." in text and not text.endswith("."):
                        targets |= {ep for ep in known if ep.startswith(text)}

            # A function that never mentions `url_for` is not drawing links —
            # it is prose, a permission check or a lookup table.
            if not mentions_url_for:
                continue

            endpoint = f"{mod}.{node.name}"
            if endpoint in auth.ROUTE_PERMISSIONS:
                precise.setdefault(endpoint, set()).update(targets)
            else:
                module_wide.setdefault(mod, set()).update(targets)

    return precise, module_wide, computed


def _helper_audience():
    """
    `{module: {modules whose pages a helper in it can draw on}}`.

    A helper's output lands on whichever page called it, and several of them are
    called across module lines — `approval.py` draws the Approve / Reject pair
    onto the RA, tax invoice, purchase order, charge and measurement view pages,
    and its links belong to those pages rather than to `approval.py`, which has
    no register of its own to start from.

    Scoping a helper's links to its own module made the first draft of this file
    report all ten `approval.approve_*` / `reject_*` handlers as islands when
    every one of them is a button on a page somebody uses daily.

    The audience is derived statically: module B is in module A's audience when
    B's source calls `A.<something>(`. That is an approximation, and like the
    rest of this file it errs towards **reaching more**, so it under-reports.
    """
    modules = {ep.split(".", 1)[0] for ep in auth.ROUTE_PERMISSIONS}
    audience = {m: {m} for m in modules}
    for caller in modules:
        path = _module_path(caller)
        if path is None:
            continue
        src = path.read_text(encoding="utf8")
        for callee in modules:
            if callee != caller and re.search(rf"\b{callee}\.[a-zA-Z_]+\s*\(", src):
                audience[callee].add(caller)
    return audience


def _roots() -> set:
    """Where a user actually starts: the nav, the launcher, the named exceptions."""
    src = (REPO / "dashboard.py").read_text(encoding="utf8")
    roots = {ep for ep, _icon, _label in dashboard.NAV_ITEMS}
    roots |= set(re.findall(r'_card\(\s*"([a-z_]+\.[a-z_]+)"', src))
    roots.add("auth.list_users")          # `_access_card()`, built by hand
    roots |= set(NO_INBOUND_LINK_BY_DESIGN)
    return roots


def _walk(nodes: set, roots=None):
    """Everything reachable from the roots by following `url_for()` edges."""
    precise, module_wide, _computed = _link_edges()
    audience = _helper_audience()

    # A page in module X sees its own view's links, plus the links of any
    # helper whose audience includes X.
    from_helpers = {}
    for owner, targets in module_wide.items():
        for seen_by in audience.get(owner, {owner}):
            from_helpers.setdefault(seen_by, set()).update(targets)

    reached = {ep for ep in (roots if roots is not None else _roots())
               if ep in nodes}
    changed = True
    while changed:
        changed = False
        for ep in sorted(reached):
            outgoing = set(precise.get(ep, ()))
            outgoing |= from_helpers.get(ep.split(".", 1)[0], set())
            for target in outgoing:
                if target in nodes and target not in reached:
                    reached.add(target)
                    changed = True
    return reached


# ═════════════════════════════════════════════════════════════════════════════
# The sweep
# ═════════════════════════════════════════════════════════════════════════════

def test_every_classified_page_has_an_inbound_route_from_a_page_you_can_reach():
    """
    ⚠ **The test a hand sweep cannot replace.**

    Pass C swept for unreachable pages by hand and linked the three it found;
    pass E added a fourth. A hand sweep is right on the day it is done and says
    nothing about the pass after it. This walks `app.url_map`, so a page added
    later is covered the day it is registered.

    A page that fails here is not broken — it is *unfindable*, which is the
    defect the owner reported in his own words: he could not reach most of what
    had been built without editing links himself.
    """
    import app as app_module

    nodes = _classified_get_endpoints(app_module.app)
    islands = sorted(nodes - _walk(nodes))

    assert not islands, (
        f"{len(islands)} classified page(s) have no inbound link from anywhere "
        f"a user can already be. Add a link from the register or page they "
        f"belong to, or name each in NO_INBOUND_LINK_BY_DESIGN with the "
        f"reason: {islands}")


def test_the_exception_list_names_no_page_that_does_not_exist():
    """
    An exception for a renamed route protects nothing and silently lets its
    replacement through the sweep. Same failure `test_nav_reachability.py`
    guards against one level up.
    """
    import app as app_module

    known = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    stale = sorted(set(NO_INBOUND_LINK_BY_DESIGN) - known)
    assert not stale, (
        f"NO_INBOUND_LINK_BY_DESIGN names endpoints that are gone: {stale}")


def test_every_exception_carries_a_reason():
    """
    A reason is what makes an exception a decision rather than a place to park
    a page nobody wants to link. An empty string is not a reason.
    """
    for endpoint, reason in NO_INBOUND_LINK_BY_DESIGN.items():
        assert reason and reason.strip(), f"{endpoint} is excepted with no reason"
        assert len(reason.strip()) > 20, (
            f"{endpoint}'s reason is too short to be one: {reason!r}")


def test_no_exception_is_actually_reachable():
    """
    An exception that has since been linked is a stale excuse, and it hides the
    page from the sweep for no reason. If something now links to it, the entry
    must go.

    ⚠ Excludes the pre-session and Flask-owned entries: those are unreachable by
    design and always will be, so they are not evidence of anything.
    """
    import app as app_module

    permanent = {"auth.login", "auth.setup", "dashboard.index", "static"}
    nodes = _classified_get_endpoints(app_module.app)

    # Walk with the excusable entries removed from the roots, and see which of
    # them the graph reaches anyway.
    excusable = set(NO_INBOUND_LINK_BY_DESIGN) - permanent
    reached = _walk(nodes, roots=_roots() - excusable)

    stale = sorted(excusable & reached)
    assert not stale, (
        f"these are listed as having no inbound link, but the walk reaches "
        f"them: {stale}. Remove them from NO_INBOUND_LINK_BY_DESIGN.")


def test_the_link_graph_is_built_from_literal_endpoints_almost_everywhere():
    """
    The whole file rests on `url_for("literal")` being how this codebase links.
    A computed endpoint — `url_for(ep)` — is invisible to the AST walk, and
    enough of them would quietly turn the sweep above into a test of nothing.

    This is the tripwire on that assumption rather than a rule against the
    idiom. If it fires, raise the bound deliberately and say why.
    """
    precise, module_wide, computed = _link_edges()
    literal = sum(len(v) for v in precise.values())
    literal += sum(len(v) for v in module_wide.values())

    assert literal > 100, (
        f"only {literal} literal url_for targets found — the AST walk has "
        f"stopped seeing this codebase's links and the sweep is not testing "
        f"what it claims to")

    # Measured on 30 August 2026: ten sites, and every one of them names its
    # endpoint as a literal somewhere the walk does see —
    #   approval.py  x2   `url_for("approval.approve_" + doc_key, ...)`, resolved
    #                     by the prefix rule in `_link_edges()`
    #   ra.py        x1   `_gated(label, endpoint, ...)`, resolved by the
    #                     literal "ra.delete_ra" etc. at the call site
    #   dashboard.py x2   the nav and card renderers, whose endpoints ARE the
    #                     roots of this walk
    #   the rest          the same two idioms elsewhere
    # An eleventh is not forbidden; it just has to be checked, because a
    # computed endpoint whose name appears as a literal nowhere is a link this
    # file cannot see.
    assert computed <= 10, (
        f"{computed} url_for() call sites use a computed endpoint, up from the "
        f"10 measured on 30 August 2026. The sweep can only see one if its "
        f"endpoint name appears as a literal too. Check the new one, then raise "
        f"this bound deliberately.")
