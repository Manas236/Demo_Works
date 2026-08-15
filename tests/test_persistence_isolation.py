"""
sync() failure isolation — db.py

Three properties, and every one of them was absent before:

1. **Isolation.** One collection MySQL refuses must not stop the other eight.
   sync() used to wrap all nine in a single try/except, so one oversized BOQ
   took the catalogue, the quotations, the invoices and the address book down
   with it.

2. **Retry.** A failure must be retried on the next request. The old code set
   `_state["ok"] = False` on any exception, and every later sync then returned
   immediately — persistence went dark app-wide until somebody restarted the
   process, on the strength of one transient error.

3. **A visible signal.** The only notice a user got was `!! persistence lost:`
   on stdout, which nobody working in a browser will ever see. It now renders as
   a red strip under the nav on every page.

The tests run against a fake connection rather than MySQL. That is not a
compromise: forcing a *chosen* collection to fail is the entire experiment, and
provoking a real `DataError` on one table and not the others would need a
schema the app does not have. What the fake stands in for is narrow — cursor(),
executemany() and ping() — and the SQL it receives is asserted on.
"""

import json
import re

import pytest
import pymysql

import db
from store import STORE


# ── The fake connection ─────────────────────────────────────────────────────

_TABLE = re.compile(r"`(\w+)`")
_FROM  = re.compile(r"FROM `(\w+)`")


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        # `_TABLE` grabs the first backticked token, which is the table in an
        # INSERT/DELETE but is `id` in "SELECT `id`, `data` FROM `boqs`".
        table = _FROM.search(sql).group(1)
        self._result = list(self.conn.rows.get(table, {}).items())

    def fetchall(self):
        return self._result

    def executemany(self, sql, params):
        table = _TABLE.search(sql).group(1)
        self.conn.statements.append((table, sql.split()[0], len(params)))
        if table in self.conn.refuse:
            raise pymysql.err.DataError(
                1406, f"Data too long for column 'data' at row 1 ({table})")
        rows = self.conn.rows.setdefault(table, {})
        if sql.lstrip().upper().startswith("INSERT"):
            for rid, blob in params:
                rows[rid] = blob
        else:
            for (rid,) in params:
                rows.pop(rid, None)


class FakeConn:
    """cursor() / ping() — the only two things db.py asks of a connection."""

    def __init__(self, refuse=(), ping_error=None):
        self.refuse = set(refuse)
        self.ping_error = ping_error
        self.rows = {}          # table -> {id: blob}
        self.statements = []    # (table, verb, n) in the order they were issued
        self.pings = 0

    def ping(self, reconnect=True):
        self.pings += 1
        if self.ping_error:
            raise self.ping_error

    def cursor(self):
        return _FakeCursor(self)


@pytest.fixture()
def fake_db():
    """
    db.py wired to a fake connection, with all module state restored after.

    db.py holds process-global state (`_state`, `_digests`, `_failures`) and the
    suite runs with DB_ENABLED=false, so every one of those has to be put back
    or the next test inherits a half-failed persistence layer.
    """
    saved_state    = dict(db._state)
    saved_digests  = {c: dict(d) for c, d in db._digests.items()}
    saved_failures = dict(db._failures)
    saved_enabled  = db.CONFIG["enabled"]

    conn = FakeConn()
    # The suite as a whole runs with DB_ENABLED=false so it cannot reach the
    # developer's MySQL (see conftest). These tests are about an app where
    # persistence IS configured and connected, so the flag is flipped back for
    # the duration — without it, failure_note() correctly stays silent and
    # every assertion here would pass against a strip that never renders.
    db.CONFIG["enabled"] = True
    db._state["ok"] = True
    db._state["error"] = None
    db._state["conn"] = conn
    for d in db._digests.values():
        d.clear()
    db._failures.clear()

    yield conn

    db.CONFIG["enabled"] = saved_enabled
    db._state.clear()
    db._state.update(saved_state)
    for c, d in saved_digests.items():
        db._digests[c].clear()
        db._digests[c].update(d)
    db._failures.clear()
    db._failures.update(saved_failures)


def a_store():
    """One record in each of the nine persisted collections."""
    return {coll: {f"{coll}-1": {"id": f"{coll}-1", "n": 1}}
            for coll in db.COLLECTIONS}


# ── 1. Isolation ────────────────────────────────────────────────────────────

def test_one_refused_collection_leaves_every_other_one_persisting(fake_db):
    """The headline property. One collection refuses, all the rest land."""
    fake_db.refuse = {"boqs"}

    result = db.sync(a_store())

    assert result["failed"] == ["boqs"]
    assert result["written"] == len(db.COLLECTIONS) - 1

    landed = {t for t, rows in fake_db.rows.items() if rows}
    assert landed == set(db.COLLECTIONS) - {"boqs"}
    assert "boqs" not in landed


def test_a_refused_collection_does_not_stop_the_ones_after_it(fake_db):
    """
    Order matters: `products` is first in COLLECTIONS and `settings` is last.
    Failing the first must not short-circuit the loop, which is exactly what the
    single try/except did.
    """
    fake_db.refuse = {"products"}

    result = db.sync(a_store())

    assert result["failed"] == ["products"]
    assert "settings" in fake_db.rows and fake_db.rows["settings"]


def test_every_collection_can_fail_alone(fake_db):
    """Isolation is not a special case for one table."""
    for coll in db.COLLECTIONS:
        for d in db._digests.values():
            d.clear()
        db._failures.clear()
        fake_db.rows.clear()
        fake_db.refuse = {coll}

        result = db.sync(a_store())

        assert result["failed"] == [coll], coll
        assert result["written"] == len(db.COLLECTIONS) - 1, coll


def test_deletes_are_isolated_too(fake_db):
    """A refused DELETE must not take the other eight collections' deletes."""
    store = a_store()
    db.sync(store)
    assert not db._failures

    fake_db.refuse = {"boqs"}
    for coll in db.COLLECTIONS:
        store[coll].clear()

    result = db.sync(store)

    assert result["failed"] == ["boqs"]
    assert result["deleted"] == len(db.COLLECTIONS) - 1
    assert fake_db.rows["boqs"]                       # still there, refused
    assert not fake_db.rows["quotations"]             # gone, as asked


# ── 2. Retry ────────────────────────────────────────────────────────────────

def test_a_failure_is_retried_on_the_next_sync(fake_db):
    """
    The record MySQL refused must land as soon as it stops refusing — which
    means its digest was never advanced past it.
    """
    store = a_store()
    fake_db.refuse = {"boqs"}
    db.sync(store)
    assert "boqs" not in fake_db.rows or not fake_db.rows["boqs"]

    fake_db.refuse = set()
    result = db.sync(store)

    assert result["failed"] == []
    assert result["written"] == 1                     # only the one that failed
    assert fake_db.rows["boqs"]["boqs-1"]
    assert db.failures() == {}


def test_a_failure_does_not_take_persistence_dark(fake_db):
    """
    The second property, stated as the bug it fixes: after a failure the app
    must still be persisting everything else, on this request and on every
    request after it — not until a restart.
    """
    store = a_store()
    fake_db.refuse = {"boqs"}
    db.sync(store)

    assert db.is_live() is True

    store["quotations"]["q-new"] = {"id": "q-new"}
    result = db.sync(store)

    assert result["written"] == 1
    assert "q-new" in fake_db.rows["quotations"]
    assert result["failed"] == ["boqs"]               # still failing, still tried


def test_a_permanently_failing_collection_keeps_being_retried(fake_db):
    """It should keep trying and keep saying so, not give up after n attempts."""
    store = a_store()
    fake_db.refuse = {"boqs"}

    for _ in range(5):
        assert db.sync(store)["failed"] == ["boqs"]

    boq_attempts = [s for s in fake_db.statements if s[0] == "boqs"]
    assert len(boq_attempts) == 5


def test_a_lost_connection_fails_everything_and_recovers_without_a_restart(fake_db):
    """
    A dropped connection is the case the old code punished hardest: one
    OperationalError and nothing persisted again until the process restarted.
    """
    fake_db.ping_error = pymysql.err.OperationalError(2006, "MySQL server has gone away")
    store = a_store()

    result = db.sync(store)
    assert result["failed"] == list(db.COLLECTIONS)
    assert result["written"] == 0
    assert db.is_live() is True

    fake_db.ping_error = None
    result = db.sync(store)

    assert result["failed"] == []
    assert result["written"] == len(db.COLLECTIONS)
    assert db.failures() == {}


def test_recovery_clears_only_the_collection_that_recovered(fake_db):
    store = a_store()
    fake_db.refuse = {"boqs", "specs"}
    db.sync(store)
    assert set(db.failures()) == {"boqs", "specs"}

    fake_db.refuse = {"boqs"}
    db.sync(store)

    assert set(db.failures()) == {"boqs"}


def test_an_unchanged_record_is_still_not_rewritten(fake_db):
    """The diff still works — isolation did not turn sync into a full rewrite."""
    store = a_store()
    assert db.sync(store)["written"] == len(db.COLLECTIONS)
    assert db.sync(store)["written"] == 0


# ── _digests holds a hash, and the diff is unchanged by that ────────────────
#
# The cache used to hold every record's full JSON, so the process carried a
# second complete copy of the database to answer "did this change?" — a question
# a hash answers exactly as well, because `!=` is the only thing ever done to
# the cached value. These tests pin the diff semantics that must NOT have moved.

def test_the_cache_holds_a_digest_and_not_the_record(fake_db):
    store = a_store()
    store["boqs"]["boqs-1"]["project_name"] = "Sify Bangalore"
    db.sync(store)

    cached = db._digests["boqs"]["boqs-1"]
    assert len(cached) == 64
    assert all(c in "0123456789abcdef" for c in cached)
    assert "Sify Bangalore" not in cached


def test_a_changed_record_still_syncs(fake_db):
    """Half the contract: an edit must still reach MySQL."""
    store = a_store()
    db.sync(store)

    store["boqs"]["boqs-1"]["project_name"] = "Sify Bangalore"
    result = db.sync(store)

    assert result["written"] == 1
    assert "Sify Bangalore" in fake_db.rows["boqs"]["boqs-1"]


def test_a_nested_in_place_mutation_is_still_caught(fake_db):
    """
    The reason this module snapshots and diffs at all: blueprints mutate nested
    dicts in place, and only the outermost __setitem__ would be observable to a
    write-through wrapper. Hashing must not weaken that.
    """
    store = a_store()
    store["boqs"]["boqs-1"]["line_items"] = [{"item_no": "4.1", "total_qty": 700.0}]
    db.sync(store)

    store["boqs"]["boqs-1"]["line_items"][0]["total_qty"] = 701.0
    result = db.sync(store)

    assert result["written"] == 1
    assert "701" in fake_db.rows["boqs"]["boqs-1"]


def test_an_unchanged_record_still_does_not_sync(fake_db):
    """The other half: no edit, no write, however many requests go by."""
    store = a_store()
    db.sync(store)

    for _ in range(5):
        assert db.sync(store)["written"] == 0

    assert [s for s in fake_db.statements if s[0] == "boqs"] == [("boqs", "INSERT", 1)]


def test_rebuilding_a_record_with_the_same_content_is_not_a_change(fake_db):
    """
    `_blob`'s sort_keys is what makes the digest stable. Without it a dict built
    in a different key order would hash differently and every request would
    rewrite the whole database.
    """
    store = a_store()
    store["boqs"]["boqs-1"] = {"id": "boqs-1", "ref": "SF/BOQ/26-27/0001", "rev_no": 0}
    db.sync(store)

    # Same content, different insertion order.
    store["boqs"]["boqs-1"] = {"rev_no": 0, "id": "boqs-1", "ref": "SF/BOQ/26-27/0001"}

    assert db.sync(store)["written"] == 0


def test_reverting_an_edit_within_one_request_is_not_a_change(fake_db):
    """A digest is content-addressed, so an edit and its undo cancel out."""
    store = a_store()
    db.sync(store)

    store["boqs"]["boqs-1"]["project_name"] = "typo"
    del store["boqs"]["boqs-1"]["project_name"]

    assert db.sync(store)["written"] == 0


def test_what_reaches_mysql_is_the_json_not_the_digest(fake_db):
    """The obvious way to get this change wrong."""
    store = a_store()
    db.sync(store)

    written = fake_db.rows["boqs"]["boqs-1"]
    assert json.loads(written) == {"id": "boqs-1", "n": 1}


def test_load_into_primes_digests_that_sync_agrees_with(fake_db):
    """
    The one path the rest of this file cannot reach, and the expensive way to
    get the digest change wrong.

    load_into() primes the cache at boot so an untouched record is not rewritten
    on the very first sync. If its priming disagreed with what sync() computes —
    one hashing the record and the other the blob, say — then every record would
    look changed and the first request after every restart would rewrite the
    whole database, silently and forever.
    """
    fake_db.rows["boqs"] = {
        "b-1": json.dumps({"id": "b-1", "ref": "SF/BOQ/26-27/0001", "rev_no": 0}),
    }
    store = {c: {} for c in db.COLLECTIONS}

    assert db.load_into(store) == 1
    assert store["boqs"]["b-1"]["ref"] == "SF/BOQ/26-27/0001"

    # Nothing touched the record, so nothing should be written.
    assert db.sync(store)["written"] == 0

    # And an edit after a load is still caught.
    store["boqs"]["b-1"]["rev_no"] = 1
    assert db.sync(store)["written"] == 1


def test_a_deleted_record_still_deletes(fake_db):
    store = a_store()
    db.sync(store)

    del store["boqs"]["boqs-1"]
    result = db.sync(store)

    assert result["deleted"] == 1
    assert "boqs-1" not in fake_db.rows["boqs"]
    assert "boqs-1" not in db._digests["boqs"]


# ── failure_note() ──────────────────────────────────────────────────────────

def test_failure_note_is_empty_when_healthy(fake_db):
    db.sync(a_store())
    assert db.failure_note() == ""


def test_failure_note_names_the_work_in_words_and_carries_no_exception(fake_db):
    """
    The split. The sentence a user reads names their work; the exception is not
    in it. Office staff pricing a fire system cannot act on a MySQL column
    error, and putting one in the page furniture only teaches people to ignore
    the strip.
    """
    fake_db.refuse = {"boqs"}
    db.sync(a_store())

    note = db.failure_note()
    assert note == ("Bills of quantities are not being saved. "
                    "Everything else is saving normally.")
    assert "DataError" not in note
    assert "Data too long" not in note
    assert "boqs" not in note          # the table name is not a user-facing word


def test_failure_detail_carries_the_exception_the_note_dropped(fake_db):
    """The half a developer needs, keyed by table name to match server logs."""
    fake_db.refuse = {"boqs"}
    db.sync(a_store())

    detail = db.failure_detail()
    assert detail.startswith("boqs: ")
    assert "Data too long" in detail


def test_detail_has_one_line_per_failed_collection(fake_db):
    fake_db.refuse = {"boqs", "specs"}
    db.sync(a_store())

    lines = db.failure_detail().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("specs: ")     # COLLECTIONS order, not set order
    assert lines[1].startswith("boqs: ")


def test_note_drops_the_reassurance_when_nothing_is_saving(fake_db):
    """
    "Everything else is saving normally" is true and worth saying — right up
    until nothing else is, when it would be a lie.
    """
    fake_db.refuse = set(db.COLLECTIONS)
    db.sync(a_store())

    note = db.failure_note()
    assert "Everything else" not in note


def test_failure_note_reports_mysql_unreachable_at_boot(fake_db):
    """
    The condition `_failures` alone cannot see.

    MySQL down at boot with DB_STRICT off leaves `_state["ok"]` False, so
    sync() returns early and no collection ever fails. An empty `_failures`
    would then say everything is fine, which is the worst available answer —
    the app is running entirely in memory.
    """
    db._state["ok"] = False
    db._state["error"] = "OperationalError: (2003, 'Cannot connect to MySQL')"

    assert db.failure_note() == "Nothing is being saved - the database is not connected."
    assert "2003" in db.failure_detail()     # the exception, on the other side of the split


def test_db_enabled_false_is_silent(fake_db):
    """
    A chosen configuration, not a failure. It has a startup banner of its own,
    and painting every dev run and every test red is how a warning stops being
    read.
    """
    db._state["ok"] = False
    db._state["error"] = "disabled via DB_ENABLED=false"
    db.CONFIG["enabled"] = False
    try:
        assert db.failure_note() == ""
        assert db.failure_detail() == ""
    finally:
        db.CONFIG["enabled"] = True


def test_the_strip_tells_a_boot_failure_to_restart_and_a_write_failure_to_wait(
        client, fake_db):
    """
    The advice has to differ. A failed write is retried every request, so the
    user should keep working and watch the strip clear. An unreachable server
    is never retried — sync() returns early — so only a restart fixes it, and
    telling that user to wait would be a lie.
    """
    fake_db.refuse = {"boqs"}
    client.get("/boq/")
    html = client.get("/").get_data(as_text=True)
    assert "Every request retries." in html
    assert "Restart the app" not in html

    db._failures.clear()
    db._state["ok"] = False
    db._state["error"] = "OperationalError: (2003, 'Cannot connect')"

    html = client.get("/").get_data(as_text=True)
    assert 'class="db-down"' in html
    assert "Restart the app once MySQL is reachable." in html
    assert "Every request retries." not in html


def test_failure_note_names_every_failed_collection(fake_db):
    fake_db.refuse = {"boqs", "specs", "invoices"}
    db.sync(a_store())

    note = db.failure_note()
    assert note == ("Tax invoices, specifications and bills of quantities "
                    "are not being saved. Everything else is saving normally.")


# ── 3. The visible signal, on a rendered page ───────────────────────────────

def test_the_strip_is_absent_while_persistence_is_healthy(client, fake_db):
    html = client.get("/").get_data(as_text=True)
    # The ELEMENT, not the class name — `.db-down` is in BASE_STYLES on every
    # page whether or not the strip renders, so a bare substring check passes
    # against a broken build.
    assert 'class="db-down"' not in html
    assert "Not saving" not in html


def test_the_strip_appears_on_a_rendered_page(client, fake_db):
    """
    End to end: a real request's teardown_request drives db.sync(), the write is
    refused, and the next page a user loads says so.

    Two requests, deliberately. sync() runs from teardown_request — *after* the
    response has been built — so the request that provokes the failure cannot
    carry the notice. The one after it must.
    """
    fake_db.refuse = {"boqs"}

    client.get("/boq/")                               # provokes the failure
    assert db.failures(), "the fixture did not actually reach db.sync()"

    html = client.get("/").get_data(as_text=True)

    assert 'class="db-down"' in html
    assert "Not saving" in html
    assert "Bills of quantities are not being saved." in html
    assert "will be lost on restart" in html


def test_the_strip_keeps_the_exception_out_of_sight_but_in_the_page(client, fake_db):
    """
    The split, on the rendered page: a user reads a sentence about their work,
    a developer hovers (or screenshots) and gets the MySQL error.
    """
    fake_db.refuse = {"boqs"}
    client.get("/boq/")
    html = client.get("/").get_data(as_text=True)

    strip = html[html.index('class="db-down"'):]
    strip = strip[:strip.index("</div>")]

    visible = strip[strip.index("<span>"):]
    assert "Data too long" not in visible
    assert "DataError" not in visible

    assert 'title="boqs: ' in strip
    assert "Data too long" in strip


def test_the_strip_is_chrome_and_appears_away_from_the_dashboard(client, fake_db):
    """
    The whole reason it lives in `_nav()`: a user can work for an hour inside
    the BOQ editor without ever loading `/`.
    """
    fake_db.refuse = {"boqs"}
    client.get("/boq/")          # seeds the demo BOQ, so there is a write to refuse
    assert db.failures()

    for path in ("/boq/", "/spec/", "/address/", "/quotation/",
                 # The two newest modules. A page that renders its own chrome
                 # instead of calling `_nav()` looks right and silently drops
                 # this strip — which is the one warning that means *nothing
                 # you type is being saved*.
                 "/client/", "/po/"):
        html = client.get(path).get_data(as_text=True)
        assert 'class="db-down"' in html, path


def test_the_strip_clears_itself_when_the_write_lands(client, fake_db):
    fake_db.refuse = {"boqs"}
    client.get("/boq/")                               # seeds a BOQ, which is refused
    assert 'class="db-down"' in client.get("/").get_data(as_text=True)

    fake_db.refuse = set()
    client.get("/")                                   # this sync succeeds

    html = client.get("/").get_data(as_text=True)
    assert 'class="db-down"' not in html
    assert db.failures() == {}


def test_the_strip_escapes_the_error_text(client, fake_db):
    """
    MySQL quotes the offending value back in a truncation or duplicate-key
    message, so user input can reach this string — and it now lands in an
    ATTRIBUTE, where a bare `"` is the thing that breaks out, not a `<`.
    """
    db._failures["boqs"] = (
        'DataError: Duplicate entry \'<script>alert(1)</script>\' '
        'and a " quote')

    html = client.get("/").get_data(as_text=True)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    # The quote that would otherwise close title=" and let the rest of the
    # message become markup.
    assert 'and a &quot; quote' in html


def test_the_strip_never_prints(client, fake_db):
    """
    It is app chrome. The rule that hides `nav` on paper lives in quotation.py's
    VIEW_DOC_STYLES, so this strip ships its own — a page that does not load
    that sheet must still not print it.
    """
    from dashboard import BASE_STYLES

    assert "@media print { .db-down { display: none !important; } }" in BASE_STYLES
