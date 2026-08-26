"""
Shared test fixtures.

`DB_ENABLED=false` is set **before** `app` is imported, because `db.py` reads
its config into `_CFG` at import time and `load_dotenv()` does not override a
variable that is already in the environment. Without this the suite would try
to reach the developer's real MySQL and write test records into it.
"""

import os
import pathlib
import sys

os.environ["DB_ENABLED"] = "false"
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from store import STORE  # noqa: E402


# ── Authentication ─────────────────────────────────────────────────────────
#
# Phase 3B closed this application: `auth._gate()` refuses every endpoint that
# is not PUBLIC, so without a session the ~920 tests written before it would
# all redirect to /login and assert against the redirect page.
#
# `client` therefore arrives signed in. That is blunt on purpose and it hides
# gating bugs by construction — a test using this fixture can never tell you
# whether a route was reachable without a session. `tests/test_access_control.py`
# is what covers that, using `anon_client` below, and it is the reason this
# fixture is allowed to be as blunt as it is. **Do not add access-control
# assertions to tests that use `client`; they would pass for the wrong reason.**
#
# The seeded account holds the **Owner** role, not Director. CLIENT_CHANGES-2.md
# B3 splits the two — a Director administers users but "cannot alter role
# definitions" — so a Director session would 403 on `/roles/*` and the page
# sweeps in `test_page_chrome.py` and `test_entity_fallbacks.py` would fail on a
# rule working exactly as specified.
TEST_USER = "test-owner"
TEST_PASSWORD = "test-owner-password"


def ensure_test_user():
    """The seeded Owner the suite signs in as. Idempotent."""
    import auth

    auth.ensure_builtin_roles()
    user = auth.find_user(TEST_USER)
    if user is None:
        user = auth.create_user(TEST_USER, "Test Owner", TEST_PASSWORD,
                                ["role-owner"], created_by="conftest")
    user["active"] = True
    return user


def _fresh_store():
    """The per-test reset the `client` fixture has always done."""
    for key in ("boqs", "specs", "quotations", "proformas", "invoices", "purchases"):
        STORE[key].clear()
    # Seed flags are per-test too: a test that clears `specs` must be able to
    # let the seeder refill it, which is exactly the "drop the database and
    # restart" path the demo data exists to support.
    STORE["_spec_seeded"] = False
    STORE["_boq_seeded"] = False


@pytest.fixture()
def client():
    """A Flask test client, signed in as the seeded Owner, over a fresh STORE."""
    import app as app_module
    import auth

    app_module.app.config["TESTING"] = True
    _fresh_store()
    user = ensure_test_user()
    with app_module.app.test_client() as c:
        with c.session_transaction() as sess:
            sess[auth.SESSION_KEY] = user["id"]
        yield c


@pytest.fixture()
def anon_client():
    """
    A test client with **no session at all** — the anonymous caller.

    A separate client rather than a logged-out `client`, because
    `session.clear()` on a client that has already been signed in still leaves a
    cookie jar, and "refused because the cookie was cleared" is a weaker
    statement than "refused having never had one".
    """
    import app as app_module

    app_module.app.config["TESTING"] = True
    _fresh_store()
    ensure_test_user()
    with app_module.app.test_client() as c:
        yield c


REPO = pathlib.Path(__file__).resolve().parent.parent

# The client workbooks are gitignored (see fixtures/README.md). Look in both
# the fixtures/ directory and the repo root so an existing checkout, where they
# sit at the top level, keeps working.
_FIXTURE_DIRS = (REPO / "fixtures", REPO)


def find_fixture(name: str):
    """The path to a client workbook, or None when it is not installed."""
    for d in _FIXTURE_DIRS:
        p = d / name
        if p.exists():
            return p
    return None


def require_fixture(name: str):
    """
    The path to a client workbook, or an explicit skip.

    Skip, never fail: the workbooks are deliberately not in the repository, so
    a fresh clone has no way to satisfy this and a red suite would be
    misleading. The message names the file and points at the README rather than
    saying "skipped" and leaving the reader to work out why.
    """
    p = find_fixture(name)
    if p is None:
        pytest.skip(f"fixture workbook {name!r} not found in "
                    f"fixtures/ or the repo root - see fixtures/README.md "
                    f"for where to place it")
    return p


@pytest.fixture()
def sify_boq_xlsx():
    return require_fixture("sify_boq.xlsx")


@pytest.fixture()
def annexure_xlsx():
    return require_fixture("annexure.xlsx")


@pytest.fixture()
def fixtures_dir():
    return REPO
