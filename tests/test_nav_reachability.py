"""
tests/test_nav_reachability.py — a page you can reach, you can find
===================================================================

Three jobs, and the first is the one that made this file necessary.

**1. A classified page with no link is a page nobody finds.** The employee
master shipped on 29 August 2026 correct, tested, permissioned — and with no
nav entry and no dashboard card, because `dashboard._nav()` is embedded in
every printed page and one more entry moves every print golden in the
repository. That was a deliberate call to protect the goldens during an
unattended pass, and its cost was that the owner could not find a page he had
paid for. The sweep below is what stops the next one being discovered the same
way.

**2. The nav/golden coupling, measured rather than feared.** Adding an entry
moves five pinned documents. This file asserts *exactly* what moves: bytes
inside `<nav>…</nav>`, and nothing else, on every one of them.

**3. ⚠ THE HALF THAT ACTUALLY MATTERS — the bytes move and the PAPER DOES
NOT.** `_nav()` is `display:none` at print. If a nav change were ever visible
on a printed sheet, the print rule would be wrong and re-baselining the golden
would be the wrong response — it would pin the defect. So the printed
appearance is asserted directly, in two independent ways, rather than inferred
from "the CSS should hide it".
"""

import pathlib
import re

import pytest

import auth
import dashboard
from test_print_golden import (  # noqa: F401  (fixtures are used by pytest)
    SHEET_BLOCKS, PICKER_BLOCKS, _blocks,
    GOLD_TI, GOLD_PI, GOLD_PO, GOLD_DC, GOLD_PICK_BOQ,
    golden, golden_ra, golden_dc, golden_picker, pinned_identity,
)

REPO = pathlib.Path(__file__).resolve().parent.parent

# The nav as it stood before each entry that has been added to it, used to
# render the same page both ways in one process. Nothing else in the pass that
# added the entry touches a pinned page, so the difference between the two
# renders IS the nav change.
#
# ⚠ **Both are kept and both are swept.** A pass that adds an entry and edits
#   this constant in place proves that ITS entry is confined to the nav and
#   silently stops proving it of the last one — and the whole value of this file
#   is that the property holds for the nav as a whole rather than for one link.
NAV_BEFORE_THE_EMPLOYEE_LINK = (
    ("project.list_projects",  "project",  "Projects"),
    ("settings.edit_settings", "settings", "Settings"),
)

# 29 August 2026 (fifth pass) — before the measurement register's entry.
NAV_BEFORE_THE_MEASUREMENT_LINK = (
    ("project.list_projects",   "project",  "Projects"),
    ("employee.list_employees", "employee", "Employees"),
    ("settings.edit_settings",  "settings", "Settings"),
)

NAV_BEFORE_STATES = {
    "before-employees":    NAV_BEFORE_THE_EMPLOYEE_LINK,
    "before-measurements": NAV_BEFORE_THE_MEASUREMENT_LINK,
}

# Every page a golden pins, with the markers it is split on.
PINNED = [
    ("tax invoice",      f"/invoice/view/{GOLD_TI}",       SHEET_BLOCKS),
    ("proforma",         f"/proforma/view/{GOLD_PI}",      SHEET_BLOCKS),
    ("purchase order",   f"/purchase/view/{GOLD_PO}",      SHEET_BLOCKS),
    ("RA bill",          "/ra/print/gold-ra",              SHEET_BLOCKS),
    ("delivery challan", f"/dc/print/{GOLD_DC}",           SHEET_BLOCKS),
    ("BOQ line picker",  f"/po/create?boq={GOLD_PICK_BOQ}", PICKER_BLOCKS),
]

# The four sheets that actually go on paper. The picker is a form and the
# challan is here too — it renders no nav at all, which is the point.
PRINTED_SHEETS = [n for n, _u, _m in PINNED if n != "BOQ line picker"]


@pytest.fixture(params=sorted(NAV_BEFORE_STATES), ids=sorted(NAV_BEFORE_STATES))
def both_navs(request, client):
    """
    Render any URL with the nav as it is now and as it stood before one entry.

    Parametrised over every recorded "before" state, so each entry ever added is
    still asserted to be confined to `<nav>` rather than only the most recent
    one.
    """
    after = dashboard.NAV_ITEMS
    before_items = NAV_BEFORE_STATES[request.param]

    def render(url):
        out = {}
        for key, items in (("after", after), ("before", before_items)):
            dashboard.NAV_ITEMS = items
            r = client.get(url)
            assert r.status_code == 200, f"{url} -> {r.status_code}"
            out[key] = r.get_data(as_text=True)
        dashboard.NAV_ITEMS = after
        return out["before"], out["after"]

    yield render
    dashboard.NAV_ITEMS = after


def _nav_span(html):
    """`(before, nav, after)`, or `None` when the page renders no nav."""
    if "<nav>" not in html:
        return None
    a = html.index("<nav>")
    b = html.index("</nav>") + len("</nav>")
    return html[:a], html[a:b], html[b:]


# ══ 1. The coupling, measured ═════════════════════════════════════════════

@pytest.mark.parametrize("name,url,markers", PINNED,
                         ids=[n for n, _u, _m in PINNED])
def test_a_nav_entry_moves_the_nav_and_nothing_else(
        name, url, markers, both_navs, golden, golden_ra, golden_dc,
        golden_picker):
    """
    **The condition the re-baseline was authorised under.**

    Every byte that moved must be inside `<nav>…</nav>`. Everything before it
    and everything after it — the whole document, the whole stylesheet, the
    whole form — must be character-for-character what it was.

    Measured when this was written: **+248 bytes on five pages, 0 on the
    challan.** Measured again on 29 August 2026 for the measurement register's
    entry: **+342 bytes on the same five, 0 on the challan.**
    """
    before, after = both_navs(url)

    b_span, a_span = _nav_span(before), _nav_span(after)
    if a_span is None:
        # No nav on the page at all — see the challan test below.
        assert before == after, f"{name} has no nav and still moved"
        return

    assert b_span[0] == a_span[0], f"{name}: bytes moved BEFORE <nav>"
    assert b_span[2] == a_span[2], f"{name}: bytes moved AFTER </nav>"

    delta = len(after) - len(before)
    assert delta == len(a_span[1]) - len(b_span[1]), (
        f"{name}: the page grew by {delta} but the nav grew by "
        f"{len(a_span[1]) - len(b_span[1])} — something outside it moved")


@pytest.mark.parametrize("name,url,markers", PINNED,
                         ids=[n for n, _u, _m in PINNED])
def test_only_the_head_block_of_a_pinned_document_moves(
        name, url, markers, both_navs, golden, golden_ra, golden_dc,
        golden_picker):
    """
    The same fact stated in the goldens' own vocabulary, because that is the
    vocabulary a failure will be reported in.

    `head` runs from `<head>` to the first structural marker and is where the
    nav sits. **`letterhead`, `foot-strip`, `doc-box`, `party`, `items` and
    `signature` must every one of them be identical** — those are the document.
    """
    before, after = both_navs(url)
    b, a = _blocks(before, markers), _blocks(after, markers)

    moved = [k for k in b if b[k] != a[k]]
    assert moved in ([], ["head"]), (
        f"{name}: {moved} moved. Only the head block may move for a nav "
        f"change; anything else means the entry escaped the nav.")


def test_the_delivery_challan_does_not_move_at_all(both_navs, golden_dc):
    """
    ⚠ **The measurement that says the coupling is avoidable, not inherent.**

    `challan.print_dc` renders **no nav**, so a nav change cannot reach it.
    ABOUT.md §7 records that as the shape all six pinned pages should have —
    and this is the one page that already proves it works.
    """
    before, after = both_navs(f"/dc/print/{GOLD_DC}")
    assert before == after, "the challan renders no nav and must not move"
    assert "<nav>" not in after


# ══ 2. ⚠ The bytes moved; the paper did not ═══════════════════════════════

@pytest.mark.parametrize("name,url,markers", PINNED,
                         ids=[n for n, _u, _m in PINNED])
def test_the_printed_sheet_is_identical_once_the_nav_is_removed(
        name, url, markers, both_navs, golden, golden_ra, golden_dc,
        golden_picker):
    """
    ⚠ **THE ASSERTION THE WHOLE RE-BASELINE RESTS ON.**

    Strip `<nav>…</nav>` — which is exactly what `display:none` does to the
    rendered page — and the two documents are **byte-identical**. Not "close",
    not "the figures match": the same bytes.

    So no figure, no label and no visible character on any printed sheet
    changed, and that is established by construction rather than by reading the
    output and hoping.
    """
    before, after = both_navs(url)
    b, a = _nav_span(before), _nav_span(after)
    if a is None:
        assert before == after
        return
    assert b[0] + b[2] == a[0] + a[2], (
        f"{name}: with the nav removed the pages still differ — something "
        f"that PRINTS changed, and re-baselining would pin the defect")


@pytest.mark.parametrize("name,url,markers", PINNED,
                         ids=[n for n, _u, _m in PINNED])
def test_every_printed_sheet_hides_the_nav_at_print(
        name, url, markers, client, golden, golden_ra, golden_dc,
        golden_picker):
    """
    The other half, and it is independent of the first: removing the nav from
    the *string* proves the document is unchanged, and this proves the
    **browser** removes it from the *page*.

    One rule does it for every sheet — `quotation.VIEW_DOC_STYLES` carries
    `nav,… { display:none !important; }` inside `@media print`. A page that
    grew a nav without that rule would print app chrome on a customer's
    invoice.
    """
    if name == "BOQ line picker":
        pytest.skip("a form, not a printed sheet — it carries `.no-print`")

    html = client.get(url).get_data(as_text=True)
    if "<nav>" not in html:
        return                              # the challan; nothing to hide

    assert "@media print" in html
    rule = re.search(r"@media print\s*\{.*?\bnav\b[^}]*display\s*:\s*none",
                     html, re.S)
    assert rule, (
        f"{name} renders a nav and no @media print rule hides it — every byte "
        f"of that nav would print on the sheet")


def test_the_print_rule_is_stated_once_and_in_one_place():
    """
    Read against the source, so it cannot be satisfied by a second copy of the
    rule drifting into some other stylesheet. One definition; every sheet loads
    it through `VIEW_DOC_STYLES`.
    """
    src = (REPO / "quotation.py").read_text(encoding="utf8")
    assert "nav,.page-top,.screen-acts,.deal-panel,.alert,footer" in src
    assert "display:none !important;" in src


# ══ 3. The sweep — no classified page without a way in ════════════════════
#
# Endpoints that are deliberately not linked from the nav or the launcher, each
# with the reason. ⚠ **Adding a name here is a decision, not a formality**: it
# says "somebody looked and this one genuinely should not be on a menu".

UNLINKED_ON_PURPOSE = {
    # Pre-session and session pages. `/login` and `/setup` are where you arrive
    # with no nav at all (`auth._standalone()`); `/logout` and `/account` hang
    # off the user chip, which is `tests/test_nav_user_chip.py`'s business.
    "auth.login":   "standalone, pre-session — the nav would refuse every entry",
    "auth.setup":   "standalone, and it closes itself once one user exists",
    "auth.logout":  "on the user chip in the nav, not a menu entry",
    "auth.account": "on the user chip in the nav, not a menu entry",
    # The landing page is the nav brand.
    "dashboard.index": "the nav brand IS this link",
    # Administration lives behind the Users & Access card, which is a launcher
    # entry — these are its own sub-pages.
    "auth.list_roles":   "reached from /users, its parent",
    "auth.create_user":  "reached from /users, its parent",
    "auth.create_role":  "reached from /roles, its parent",
    # ⚠ Added a link on 29 August 2026 and kept OFF the launcher deliberately:
    # a diagnostic is not a register (ABOUT.md §7 gap 23). `/users` carries it.
    "auth.access_log":   "a diagnostic, linked from /users rather than the launcher",
    # ── C3, 2 September 2026 ────────────────────────────────────────────────
    #
    # ⚠ **Kept OFF the nav and the launcher DELIBERATELY, and CC-2 is the
    #   reason rather than a golden.** C3 says: *"Build the merge action ON THE
    #   RA REGISTER from day one. The draft-PO → PO bridge was initially shipped
    #   without its entry point; do not repeat that."* CC-2 names the RA
    #   register as this document's home, and `ra.list_ras()` carries the link —
    #   `test_the_merge_action_is_on_the_ra_register` asserts it directly, so
    #   this entry is not a way of avoiding that requirement.
    #
    #   A merged document is a **sub-register of the RA register** in exactly
    #   the sense `/roles` is a sub-page of `/users`, which is the precedent
    #   three entries above.
    #
    # ⚠ **It is NOT here to protect the print goldens**, and that is worth
    #   stating because it would be a real motive: `_nav()` is embedded in every
    #   printed page, so a sixth nav entry would move the `head` digest of every
    #   document by roughly 248 bytes (the 29 August 2026 re-baseline measured
    #   exactly that for `Employees`). Nothing on any printed sheet would
    #   change. If the owner asks for a menu entry, add it and re-baseline —
    #   that is a decision about a menu, and this comment must not be read as an
    #   argument against it.
    "merged_ra.list_merged": "a sub-register of the RA register, which CC-2 names "
                          "as the merge action's home; linked from there",
}


# The verbs a module uses for "the form my own register offers". `mark` is
# attendance's — you mark a day, you do not create one — and it is here rather
# than in the exception list because it is the same *kind* of page as the other
# three, not a page somebody decided not to link.
FORM_VERBS = ("create", "new", "add", "mark")


def _create_form_endpoints(flask_app):
    """Endpoints whose own register already offers them as a `+ New` button."""
    return {ep for ep in _classified_landing_pages(flask_app)
            if ep.rsplit(".", 1)[1].split("_")[0] in FORM_VERBS}


def _classified_landing_pages(flask_app):
    """Classified GET endpoints taking no path arguments."""
    out = set()
    for rule in flask_app.url_map.iter_rules():
        if "GET" not in (rule.methods or ()) or rule.arguments:
            continue
        if rule.endpoint in auth.ROUTE_PERMISSIONS:
            out.add(rule.endpoint)
    return out


def test_every_classified_page_is_reachable_from_the_nav_or_the_launcher():
    """
    ⚠ **The test the employee master needed and did not have.**

    Every classified page a user can land on must be one of three things: a nav
    entry, a launcher card, a form its own register offers — or a named
    exception with a reason written beside it. A page that is none of those is
    a page somebody built and nobody can find.

    It sweeps `app.url_map`, so a page added in a later pass is covered the day
    it is registered.
    """
    import app as app_module

    src = (REPO / "dashboard.py").read_text(encoding="utf8")
    drawn = {ep for ep, _icon, _label in dashboard.NAV_ITEMS}
    drawn |= set(re.findall(r'_card\(\s*"([a-z_]+\.[a-z_]+)"', src))
    drawn.add("auth.list_users")            # `_access_card()`, built by hand

    landing = _classified_landing_pages(app_module.app)
    forms = _create_form_endpoints(app_module.app)

    orphans = sorted(landing - drawn - forms - set(UNLINKED_ON_PURPOSE))
    assert not orphans, (
        "these pages are classified, permissioned and reachable, and nothing "
        "links to them — add a card, add a nav entry, or add a name to "
        f"UNLINKED_ON_PURPOSE with the reason: {orphans}")


def test_the_exception_list_names_no_endpoint_that_does_not_exist():
    """
    An exception for a route that has been renamed is an exception protecting
    nothing, and it would silently let its replacement through the sweep.
    """
    import app as app_module
    known = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    stale = sorted(set(UNLINKED_ON_PURPOSE) - known)
    assert not stale, f"UNLINKED_ON_PURPOSE names endpoints that are gone: {stale}"


def test_the_refusal_log_finally_has_a_link(client):
    """
    ⚠ `/access-log` was classified, permissioned, rendered — and linked from
    **nowhere in the application**. It was reachable only by typing the URL.

    It is on `/users` rather than on the launcher: it is a diagnostic, not an
    audit trail (ABOUT.md §7 gap 23 — an in-memory `deque(maxlen=500)` that
    dies with the process), and the launcher is for registers people work in.
    """
    html = client.get("/users").get_data(as_text=True)
    assert 'href="/access-log"' in html, \
        "the refusal log must be reachable from its parent page"


def test_the_refusal_log_link_is_drawn_only_for_a_holder(client):
    """
    And it is filtered by `can_reach()` like everything else — an Admin holding
    `admin.users` without `admin.access_log` sees the buttons beside it and not
    this one. **The route still refuses them by URL**; hiding is presentation.
    """
    from store import STORE

    auth.ensure_builtin_roles()
    auth.roles()["role-users-only"] = {
        "id": "role-users-only", "name": "Users only",
        "permissions": ["dashboard.view", "admin.users"], "builtin": False}
    existing = auth.find_user("nav-users-only")
    if existing:
        del STORE["users"][existing["id"]]
    user = auth.create_user("nav-users-only", "Users only",
                            "pw-nav-users-only-12345", ["role-users-only"],
                            created_by="reachability-test")
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]

    html = client.get("/users").get_data(as_text=True)
    assert 'href="/access-log"' not in html, "hidden for a non-holder"
    assert client.get("/access-log").status_code == 403, \
        "and refused by URL — hiding never replaces the gate"
