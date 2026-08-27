"""
The signed-in user chip — and the golden coupling it had to be built around.

Until 27 August 2026 this application had **no way to sign out from the
interface**. `/logout` existed and worked; nothing linked to it. The chip in
`dashboard._user_chip()` is that link, plus who you are and a way to `/account`.

### Why it is not simply four lines in `_nav()`

Five print goldens hash the **whole response bytes** of pages that render
`_nav()`, so any nav change moves them — the long-standing coupling recorded in
ABOUT.md §7 as "Global Nav vs Print Goldens". Measured for this pass rather than
assumed: replacing `_nav()` with a sentinel moved **five** of the eleven golden
assertions (tax invoice, proforma, purchase order, RA bill, BOQ line picker) and
left the delivery challan alone, because `challan.print_dc` renders no nav at
all.

So the chip carries its own style constant, emitted in the body beside itself,
and `BASE_STYLES` — the block those goldens hash — is untouched. The remaining
problem is the chip's own *markup*, which is bytes wherever it appears, so it is
suppressed on exactly the endpoints a golden pins. `PINNED_PAGES` is that set,
and the first test below is what stops it drifting away from the goldens it
claims to track.

**This file does not assert the goldens are unmoved** — `tests/test_print_golden.py`
does that, unchanged, and it is the real evidence. This file asserts the chip is
where it should be, absent where it must be, and escaped.
"""

import ast
import pathlib

import pytest

import auth
import dashboard

REPO = pathlib.Path(__file__).resolve().parent.parent


# ── The tie between PINNED_PAGES and the goldens ───────────────────────────

def _urls_the_goldens_request() -> set:
    """
    Every URL `tests/test_print_golden.py` hands to `client.get`, read from its
    **AST** rather than by importing it.

    Importing would run its fixtures; a text search would match the URLs in its
    prose. The AST sees exactly the calls, including the f-strings, whose
    interpolations are replaced by a placeholder id — every rule involved takes
    a single opaque `<id>`, so the placeholder matches the same rule the real
    id would.
    """
    source = (REPO / "tests" / "test_print_golden.py").read_text(encoding="utf8")
    urls = set()

    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "client"
                and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            urls.add(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            built = ""
            for part in arg.values:
                if isinstance(part, ast.Constant):
                    built += str(part.value)
                else:
                    built += "golden-placeholder-id"
            urls.add(built)
    return urls


def test_the_suppression_set_is_exactly_what_the_goldens_pin():
    """
    `PINNED_PAGES` is hand-written, and this is the only reason that is allowed.

    A second list of routes is exactly the drift Part C's navigation filtering
    refuses to accept, so this one is checked against the thing it describes:
    the URLs the golden file actually requests, resolved to endpoints through
    the live `url_map`. Add a golden and forget the endpoint, or delete a golden
    and leave a stale entry, and this fails.
    """
    import app as app_module

    adapter = app_module.app.url_map.bind("localhost")
    hashed = set()
    for url in _urls_the_goldens_request():
        path = url.split("?", 1)[0]
        endpoint, _ = adapter.match(path)
        hashed.add(endpoint)

    assert hashed, "no golden URLs were found — the AST walk has stopped working"
    assert dashboard.PINNED_PAGES == hashed, (
        f"dashboard.PINNED_PAGES and the print goldens disagree.\n"
        f"  pinned but not hashed: {sorted(dashboard.PINNED_PAGES - hashed)}\n"
        f"  hashed but not pinned: {sorted(hashed - dashboard.PINNED_PAGES)}\n"
        f"An endpoint that is hashed and not pinned will have its golden moved "
        f"by the next nav change; one that is pinned and not hashed is a page "
        f"needlessly missing its sign-out control.")


# ── The chip itself ────────────────────────────────────────────────────────

def test_the_nav_carries_the_signed_in_users_name_account_and_a_way_out(client):
    """All three things the chip exists to show, on an ordinary page."""
    html = client.get("/").get_data(as_text=True)

    assert '<div class="nav-user">' in html, "the chip is not on the dashboard"
    assert "Test Owner" in html, "the chip does not name the signed-in user"
    assert 'href="/account"' in html, "no link to /account"
    assert 'href="/logout"' in html, "no way to sign out"


@pytest.mark.parametrize("url", ["/", "/boq/", "/spec/", "/users", "/account",
                                 "/settings/", "/projects/", "/receipt/"])
def test_the_chip_is_on_every_ordinary_page_not_just_the_dashboard(client, url):
    """
    The point of putting it in `_nav()` rather than at call sites: a user who
    has been inside `/boq/create` for an hour can still sign out. Includes
    `/product/` and `/quotation/` by construction — neither file was touched.
    """
    html = client.get(url).get_data(as_text=True)
    assert "<nav>" in html, f"{url} does not render the shared nav at all"
    assert 'class="nav-user"' in html, f"{url} has a nav but no sign-out control"


def test_the_frozen_modules_get_the_chip_without_being_edited(client):
    """
    `product.py` and `quotation.py` are frozen (INTRODUCTION.md §7) and neither
    is modified by this pass. They carry the chip because `_nav()` grew it,
    which is the whole argument for putting it there instead of at 39 call
    sites.
    """
    import subprocess

    for url in ("/product/", "/quotation/"):
        assert 'class="nav-user"' in client.get(url).get_data(as_text=True), (
            f"{url} lost its sign-out control")

    try:
        changed = subprocess.run(["git", "diff", "--name-only",
                                  "eff0034", "--", "product.py", "quotation.py"],
                                 cwd=REPO, capture_output=True, text=True,
                                 timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available here; the assertion above still holds")
    if changed.returncode != 0:
        pytest.skip("this checkout does not reach eff0034 — the pass's baseline")
    assert not changed.stdout.strip(), (
        f"a frozen module was edited: {changed.stdout.strip()}. The chip is in "
        f"_nav() precisely so these two never have to be.")


def test_the_display_name_is_escaped(client):
    """
    The chip interpolates a value a user administrator typed. `P.esc` at the
    interpolation site, per the 27 August 2026 rule in CLAUDE.md — not a
    response filter, and not left to the browser.
    """
    user = auth.find_user("test-owner")
    original = user["display_name"]
    user["display_name"] = '<script>alert(1)</script>Bob & Co'
    try:
        html = client.get("/").get_data(as_text=True)
        assert "<script>alert(1)</script>Bob" not in html, (
            "a display name reached the nav unescaped")
        assert "&lt;script&gt;" in html and "Bob &amp; Co" in html
    finally:
        user["display_name"] = original


def test_the_initials_come_from_the_display_name(client):
    """Two words, two initials — and never an empty circle."""
    user = auth.find_user("test-owner")
    original = user["display_name"]
    try:
        user["display_name"] = "Yogesh Ramesh Patil"
        assert '<span class="nu-avatar">YR</span>' in \
            client.get("/").get_data(as_text=True)
        user["display_name"] = ""
        html = client.get("/").get_data(as_text=True)
        assert '<span class="nu-avatar">' in html, "the avatar vanished"
    finally:
        user["display_name"] = original


# ── Where it must NOT appear ───────────────────────────────────────────────

@pytest.mark.parametrize("url", ["/invoice/view/any-id", "/proforma/view/any-id",
                                 "/purchase/view/any-id", "/ra/print/any-id",
                                 "/dc/print/any-id", "/po/create"])
def test_no_chip_on_a_page_a_golden_hashes(url):
    """
    Asserted against `_user_chip()` in a request context for that URL rather
    than by rendering the page, because rendering needs the golden records and
    those live in `tests/test_print_golden.py` — which already proves the real
    thing, that the bytes did not move.
    """
    import app as app_module

    with app_module.app.test_request_context(url):
        assert dashboard._user_chip() == "", (
            f"{url} is hashed by a golden and would have gained nav markup")


def test_the_chip_is_empty_with_no_session():
    """
    The 404 and 413 handlers render `_nav()` and can be reached before anybody
    has signed in. A chip with nobody in it is worse than no chip.
    """
    import app as app_module

    with app_module.app.test_request_context("/"):
        assert dashboard._user_chip() == ""


def test_the_chip_styles_are_not_in_the_block_the_goldens_hash():
    """
    The constant separation is the mechanism, so it is asserted rather than
    trusted. Fold these rules into `BASE_STYLES` and five goldens move for a
    control `@media print` hides anyway.
    """
    assert ".nav-user" not in dashboard.BASE_STYLES, (
        "the chip's styles have been folded into BASE_STYLES — the block five "
        "print goldens hash")
    assert ".nav-user" in dashboard.USER_CHIP_STYLES
    assert dashboard.USER_CHIP_STYLES.lstrip().startswith("<style>")


# ── The route behind the link ──────────────────────────────────────────────

def test_the_link_goes_to_the_confirmation_and_the_post_is_what_signs_out(client):
    """
    `POST /logout` stays the real route. The nav links to `GET /logout`, which
    confirms — the delete-route convention from `9d060ee`, and the reason a
    prefetcher or a mail scanner unfurling a pasted URL cannot end a session.
    """
    html = client.get("/").get_data(as_text=True)
    assert 'href="/logout"' in html
    assert 'action="/logout"' not in html, (
        "a POST form was put in the nav, bypassing the GET confirmation")

    confirm = client.get("/logout")
    assert confirm.status_code == 200
    assert "Sign out" in confirm.get_data(as_text=True)
    with client.session_transaction() as session:
        assert auth.SESSION_KEY in session, "GET /logout ended the session"

    out = client.post("/logout")
    assert out.status_code in (302, 303)
    with client.session_transaction() as session:
        assert auth.SESSION_KEY not in session, "POST /logout did not sign out"


def test_signing_out_actually_closes_the_app_again(client):
    """
    The control that makes the test above mean something: after the POST the
    session is gone and a gated page redirects to `/login`, rather than the
    cookie merely being rewritten.
    """
    assert client.get("/boq/").status_code == 200
    client.post("/logout")

    response = client.get("/boq/")
    assert response.status_code in (302, 303)
    assert "/login" in response.headers.get("Location", "")
