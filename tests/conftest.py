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


@pytest.fixture()
def fixtures_dir():
    return pathlib.Path(__file__).resolve().parent.parent
