"""
C6's access rule, measured: who sees the Profit & Loss — and that NOBODY ELSE
sees a single byte of difference.

CLIENT_CHANGES.md §0, forty-seventh block (8 October 2026): margin is
commercially sensitive, and Sales Manager, Purchase Manager and Accountant all
hold `project.view`. So the P&L panel on `/projects/view/<id>` and the
"Cost not tagged to any project" line under `/projects/` render ONLY for a
holder of `project.pnl` — Owner and Director by default — and everybody else
gets the two pages exactly as they were.

### "Exactly as they were" is a measurement here, not a description

The digests in `BEFORE` were captured by running this file's
`test_a_role_without_project_pnl_gets_the_page_byte_for_byte` against the code
at `3a14375` — the commit before C6 — in a `git worktree` of that commit, with
the page-golden world (`tests/test_page_golden.py`'s `world`) and a fixed user
per role. They are literals, not computed: regenerating them from the code
under test would make this file assert that the code equals itself.

A role's page carries its own navigation (the rail is permission-filtered), so
each role has its own digest; what is pinned is that each role's page did not
move.
"""

import pytest

import auth
from store import STORE
from test_print_golden import _sha
from test_page_golden import (  # noqa: F401  (fixtures are used by pytest)
    world, GOLD_PROJECT,
    pinned_identity, golden, golden_ra, golden_dc, golden_dpo, golden_merged,
    golden_ms, golden_picker, pinned_counts,
)

PROJECT_PAGE = f"/projects/view/{GOLD_PROJECT}"
REGISTER = "/projects/"

# The four roles that hold `project.view` by default and NOT `project.pnl`.
# HR holds neither (the register refuses it), which is not this file's subject.
WITHOUT_PNL = ("operation-head", "sales-manager", "purchase-manager", "accountant")

# (role slug, url) -> (sha256[:16], byte length) — measured at `3a14375`.
#
# ⚠ **The four PROJECT_PAGE rows were RE-BASELINED 28 October 2026**, and the
#   REGISTER rows were not touched. That pass (the Yogesh meeting's project-page
#   bugs) adds a *Raised from these BOQs* panel that EVERY role with
#   `project.view` sees, filtered per row kind by `auth.can_reach()`, and
#   rewords three panel captions. It adds no P&L content. Measured before these
#   literals were changed: for each of the four roles, the new page with that
#   panel cut out and the three captions put back was BYTE-IDENTICAL to the
#   page this file pinned — so what this test exists to prove (no P&L byte
#   reaches a role without `project.pnl`) still holds, and the only movement
#   is the panel: +2,200 (operation head), +1,715 (sales manager), +1,176
#   (purchase manager — it may open challans and inquiries only), +1,715
#   (accountant). The values measured at `3a14375` were:
#       operation-head   ("fb919ddfbef860ab", 71798)
#       sales-manager    ("2a423f8d5b5d3c89", 71147)
#       purchase-manager ("3a3ef2d13f8b372f", 70085)
#       accountant       ("712012bebccff293", 70955)
#
# ⚠ **ALL EIGHT rows RE-BASELINED 29 October 2026, +0 bytes**, for the SF mark
#   1.5x on screen (CLIENT_CHANGES.md §0 fifty-seventh block). Every role's
#   page renders the shell, whose rail mark went 28 -> 42 px and top-bar mark
#   26 -> 39 px. It adds no P&L content. Measured before these literals were
#   changed: for each of the eight pages, the new render with ONLY those four
#   size strings put back hashed to the value this file pinned, exactly — so
#   the claim this test makes (no P&L byte reaches a role without
#   `project.pnl`) is unchanged. The values before this re-baseline:
#       operation-head   PROJECT_PAGE ("e5cbf6b0b1d27247", 73998)
#       operation-head   REGISTER     ("dc998c9637141b9d", 46214)
#       sales-manager    PROJECT_PAGE ("4b27365a64e87f88", 72862)
#       sales-manager    REGISTER     ("e099a2f75ec7d4e4", 45563)
#       purchase-manager PROJECT_PAGE ("81af0892cbed53d8", 71261)
#       purchase-manager REGISTER     ("b87ee99b425ba029", 44501)
#       accountant       PROJECT_PAGE ("b50006d2a63f996b", 72670)
#       accountant       REGISTER     ("af54c7d7988a0bec", 45371)
BEFORE = {
    # ⚠ **RE-BASELINED 29 October 2026 — CLIENT_CHANGES.md §0's fifty-eighth
    #   block, item 3** (attach a loose document by hand). THIS ROW ONLY, out
    #   of all eight: Operation Head is the one role in `WITHOUT_PNL` that
    #   holds **`project.edit`**, and the *Attach document* panel is drawn only
    #   for a holder of it (`projtag.picker_html()`, spliced where an empty
    #   string leaves the page byte-for-byte as it was). **+2,353 bytes.**
    #
    #   Sales Manager, Purchase Manager and Accountant hold no `project.edit`,
    #   get the empty string, and their three rows below are **UNCHANGED** —
    #   which is the measurement that says the panel is gated and not merely
    #   added. Measured before the baseline was touched by reverting
    #   `projectview.py` and deleting `projtag.py`: this row came back
    #   `("62d3055badec47a3", 73998)` exactly and the other seven never moved.
    #
    #   ⚠ **This is NOT a P&L leak and the file's own rule is intact.** The
    #   panel carries no figure of any kind — it is two pickers and a
    #   paragraph. Operation Head still gets no `project.pnl` panel, which
    #   `test_only_owner_and_director_see_the_panel` below still holds.
    #   The old value:
    #       ("operation-head", PROJECT_PAGE): ("62d3055badec47a3", 73998),
    #
    #   ⚠ **AND AGAIN, same day — §0 fifty-eighth block, item 5**, for a
    #     reason that is not about the P&L at all. **+180 bytes**, still this
    #     one row of the eight. Measuring the pages in headless Chromium at
    #     390 px found that the *Attach document* panel's two `<select>`s
    #     carried `min-width:260px`, which ran the page ~56 px into a
    #     horizontal scrollbar on a phone. They now wrap and shrink
    #     (`flex`/`min-width:0`/`max-width`), which is 180 bytes of inline
    #     style — and Operation Head is the one role here that holds
    #     `project.edit` and therefore sees that panel at all. The other three
    #     rows are untouched by it, as they were by the panel itself.
    #     The value before item 5:
    #       ("operation-head", PROJECT_PAGE): ("a371184c00c7be5b", 76351),
    ("operation-head",   PROJECT_PAGE): ("06f972a3a467b58f", 76531),
    ("operation-head",   REGISTER):     ("fccc00dd8367f34e", 46214),
    ("sales-manager",    PROJECT_PAGE): ("dec7a61b388ce6c7", 72862),
    ("sales-manager",    REGISTER):     ("08984bbd0406f98a", 45563),
    ("purchase-manager", PROJECT_PAGE): ("ff159d5f83bf3ee1", 71261),
    ("purchase-manager", REGISTER):     ("58dd63e96bdac24a", 44501),
    ("accountant",       PROJECT_PAGE): ("a2e883a8f8577cc8", 72670),
    ("accountant",       REGISTER):     ("59e574c848893a81", 45371),
}


def _sign_in_as(client, slug: str) -> str:
    """A fixed user holding exactly one builtin role, and the session on it.

    Fixed id and fields, because the signed-in user's name is on the page and
    a `uuid4()` id would make the digest change from one run to the next. The
    `world` fixture snapshots `users` and puts it back afterwards."""
    uid = f"gold-{slug}"
    STORE["users"][uid] = {
        "id": uid, "username": f"{slug}@test", "display_name": f"Test {slug}",
        "password_hash": "not-a-hash", "role_ids": [f"role-{slug}"],
        "active": True, "created_at": "2026-08-01 09:00", "created_by": "conftest",
    }
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = uid
    return uid


@pytest.mark.parametrize("slug", WITHOUT_PNL)
@pytest.mark.parametrize("url", (PROJECT_PAGE, REGISTER))
def test_a_role_without_project_pnl_gets_the_page_byte_for_byte(world, client, slug, url):
    """
    ⚠ **The access rule's other half, and the one a leak would break.** A
    panel that rendered for one byte too many readers is the defect; a page
    that moved by one byte for a reader who may not see the P&L means the
    panel, its stylesheet or the line under the register reached them.
    """
    _sign_in_as(client, slug)
    r = client.get(url)
    assert r.status_code == 200, f"{slug} could not open {url}"
    html = r.get_data(as_text=True)
    got = (_sha(html), len(html))
    assert got == BEFORE[(slug, url)], (
        f"{slug} on {url}: the page moved — {BEFORE[(slug, url)]} -> {got}. "
        f"A role without project.pnl must get the page exactly as it was at "
        f"3a14375.")


# ── Who DOES see it ─────────────────────────────────────────────────────────

PANEL_MARK = '<div class="panel pnl" id="pnl">'
LINE_MARK = '<p class="proj-untagged"'


def test_project_pnl_is_owner_and_director_by_default():
    """CLIENT_CHANGES.md §0 forty-seventh block: Owner and Director only. The
    Owner holds every permission by construction; Director is granted it by
    name; no other builtin role is."""
    holders = sorted(slug for slug, (_n, perms) in auth.BUILTIN_ROLES.items()
                     if "project.pnl" in perms)
    assert holders == ["director", "owner"]


@pytest.mark.parametrize("slug", ("owner", "director"))
def test_owner_and_director_see_the_panel_and_the_line(world, client, slug):
    _sign_in_as(client, slug)
    page = client.get(PROJECT_PAGE).get_data(as_text=True)
    register = client.get(REGISTER).get_data(as_text=True)
    assert page.count(PANEL_MARK) == 1, f"{slug} should see the Profit & Loss"
    assert register.count(LINE_MARK) == 1, f"{slug} should see the untagged line"
    # Both hold attendance.view, so the labour row is shown, not withheld.
    assert "withheld: it needs the View attendance" not in page


@pytest.mark.parametrize("slug", WITHOUT_PNL)
def test_without_the_permission_there_is_no_panel_and_no_line(world, client, slug):
    """The marker-level statement of what the digests above pin byte-for-byte —
    kept so a failure there names the cause in words."""
    _sign_in_as(client, slug)
    assert PANEL_MARK not in client.get(PROJECT_PAGE).get_data(as_text=True)
    assert LINE_MARK not in client.get(REGISTER).get_data(as_text=True)


def test_ticking_project_pnl_on_a_role_is_all_it_takes(world, client):
    """
    ⚠ **The proof the checkbox grants something** — the property
    `test_every_catalogue_permission_gates_something` exists to protect, here
    for a permission that gates a panel rather than a page. An Owner ticks
    `project.pnl` on Accountant at /roles; the panel and the line arrive with
    no code change and no re-login. Accountant holds no `attendance.view`, so
    the labour row says it is withheld (CC-2 B4).
    """
    _sign_in_as(client, "accountant")
    assert PANEL_MARK not in client.get(PROJECT_PAGE).get_data(as_text=True)
    role = STORE["roles"]["role-accountant"]
    role["permissions"] = sorted(set(role["permissions"]) | {"project.pnl"})
    page = client.get(PROJECT_PAGE).get_data(as_text=True)
    register = client.get(REGISTER).get_data(as_text=True)
    assert page.count(PANEL_MARK) == 1 and register.count(LINE_MARK) == 1
    assert "withheld: it needs the View attendance" in page
    assert "site labour not shown" in register


def test_the_panel_carries_its_own_stylesheet_so_nobody_else_receives_it(world, client):
    """The panel's CSS travels inside the panel. A rule added to the page's
    `<head>` instead would reach every reader of the page — and move the four
    pinned digests above."""
    import projectview
    _sign_in_as(client, "owner")
    page = client.get(PROJECT_PAGE).get_data(as_text=True)
    head = page[:page.index("<body")]
    assert ".pnl-figure" not in head and "table.pnl-rows" not in head
    panel = page[page.index(PANEL_MARK):]
    assert projectview.PNL_CSS.strip() in panel
