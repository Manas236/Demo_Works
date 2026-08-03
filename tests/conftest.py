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


@pytest.fixture()
def client():
    """A Flask test client over a STORE emptied of everything the tests write."""
    import app as app_module

    app_module.app.config["TESTING"] = True
    for key in ("boqs", "specs", "quotations", "proformas", "invoices", "purchases"):
        STORE[key].clear()
    # Seed flags are per-test too: a test that clears `specs` must be able to
    # let the seeder refill it, which is exactly the "drop the database and
    # restart" path the demo data exists to support.
    STORE["_spec_seeded"] = False
    STORE["_boq_seeded"] = False
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
