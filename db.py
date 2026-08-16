"""
db.py — MySQL Persistence Layer
================================
Gives STORE a durable home without asking any blueprint to change how it works.

The problem it solves
---------------------
store.py hands every blueprint the *same* plain dict, and the whole codebase
relies on that: `STORE["quotations"][qid]["sales_stage"] = "Closed Won"` mutates
a nested dict in place. A write-through container cannot see that — only the
outermost `__setitem__` is observable.

So instead of intercepting writes, this module **snapshots and diffs**. After
every request, sync() serialises each record and compares it to the digest it
last wrote. Anything new or changed is upserted; anything gone is deleted. In-place
nested mutation is caught exactly like a top-level assignment, and product.py,
quotation.py, pipeline.py and address.py need no changes at all.

Schema
------
One table per collection, each row a whole record as a JSON document:

    CREATE TABLE quotations (
      id         VARCHAR(64) PRIMARY KEY,
      data       JSON NOT NULL,
      updated_at TIMESTAMP ...
    )

Why JSON rather than normalised columns: quotation records are deeply nested
(line_items, selections, stage_history) and their shape is still moving. Columns
would mean a migration every time a field is added, and a rewrite of every read
in the app. This keeps the Python data model authoritative and the schema stable.
The trade-off is that MySQL cannot query inside a quotation efficiently — when
reporting needs that, promote the hot fields (ref, sales_stage, grand_total) to
generated columns; the JSON stays the source of truth.

Configuration — .env in the project root (see .env.example)
-----------------------------------------------------------
    DB_ENABLED   true | false   turn persistence off entirely
    DB_STRICT    true | false   true = refuse to start if MySQL is unreachable
    DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD

If MySQL is unreachable and DB_STRICT is false, the app still runs in memory —
but prints a loud banner, because silently losing data is exactly the confusion
this module exists to end.

When a write fails
------------------
Failure is per-collection and per-request, never global and never permanent:

    one collection refuses  ->  that collection is recorded in `_failures`
                            ->  its digests are NOT advanced
                            ->  the other eight still persist
                            ->  the next request retries it
                            ->  success clears the entry, silently

and `failure_note()` is what `dashboard._nav()` renders as a red strip under the
nav on every page, so the condition reaches the person whose work is not being
saved rather than only stdout.
"""

import hashlib
import json
import os
import threading

import pymysql
from dotenv import load_dotenv

# Read .env once, at import. Real environment variables win over the file.
load_dotenv(override=False)

# Collections in STORE that get persisted. Add a key here and it is durable —
# the table is created automatically on next start.
COLLECTIONS = ("products", "quotations", "proformas", "invoices", "purchases", "purchase_orders",
               "specs", "boqs", "ra_bills", "receipts", "delivery_challans", "projects",
               "addresses", "settings")

# Seed flags (_seeded / _addr_seeded) are deliberately NOT persisted. Both
# seeders use fixed IDs and skip existing rows, so re-running them after a
# restart is a no-op — and leaving them unpersisted means a manually emptied
# table refills itself instead of staying mysteriously blank.


# =============================================================================
# CONFIG
# =============================================================================

def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


CONFIG = {
    "enabled":  _flag("DB_ENABLED", True),
    "strict":   _flag("DB_STRICT", False),
    "host":     os.getenv("DB_HOST", "127.0.0.1"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "name":     os.getenv("DB_NAME", "samruddhi_qms"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Runtime state. `ok` means "persistence was initialised and the connection is
# ours to use" — it is set by init() and NOT cleared by a failing write. A write
# that fails is a per-collection, per-request condition (see `_failures`), not a
# reason to stop trying for the lifetime of the process.
_state = {"ok": False, "error": None, "conn": None}
_lock = threading.Lock()

# Collections whose last sync attempt failed: {collection: "ErrorType: message"}.
#
# This is the runtime health signal, and it is deliberately transient. A record
# MySQL refuses leaves its collection listed here and its digest un-advanced, so
# the NEXT request retries exactly the rows that did not land. An entry clears
# itself the moment that retry succeeds. Nothing here survives a restart and
# nothing here needs to — the digests are rebuilt from the database at boot.
#
# `failure_note()` turns this into the line the nav strip prints, which is how a
# user finds out their work is not being saved without reading stdout.
_failures: dict = {}

# digest[collection][id] = the sha256 of the JSON most recently written for that
# row. A 64-character hex string, whatever the record's size.
#
# It held the FULL JSON string until this was changed, which meant the process
# carried a second complete copy of the entire database purely to answer "did
# this change?" — a question a hash answers exactly as well, because the only
# operation ever performed on the cached value is `!=` against the current one.
#
# Measured on a store of 200 BOQs (~15 MB of JSON): 30.2 MB held as strings
# against 0.5 MB as digests. It also makes the retry loop cheap — a permanently
# failing collection is re-diffed on every single request (§4), and comparing
# 64 bytes is not comparing 70 KB.
#
# sha256 rather than a faster non-cryptographic hash: a collision here silently
# skips a write, which is indistinguishable from data loss and would be found
# months later. The hashing is not the bottleneck — the JSON serialisation that
# precedes it is, and that was always happening.
_digests: dict = {c: {} for c in COLLECTIONS}


class PersistenceError(RuntimeError):
    """Raised only when DB_STRICT is on and MySQL cannot be reached."""


# =============================================================================
# CONNECTION
# =============================================================================

def _connect(with_db: bool = True):
    return pymysql.connect(
        host=CONFIG["host"], port=CONFIG["port"],
        user=CONFIG["user"], password=CONFIG["password"],
        database=CONFIG["name"] if with_db else None,
        charset="utf8mb4", autocommit=True,
        cursorclass=pymysql.cursors.Cursor,
    )


def _conn():
    """Live connection, reconnecting if the server dropped an idle session."""
    c = _state["conn"]
    if c is None:
        raise PersistenceError("not initialised")
    c.ping(reconnect=True)
    return c


def _ensure_schema() -> None:
    """Create the database and one table per collection. Safe to re-run."""
    boot = _connect(with_db=False)
    try:
        with boot.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{CONFIG['name']}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        boot.close()

    conn = _connect()
    with conn.cursor() as cur:
        for coll in COLLECTIONS:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS `{coll}` (
                  `id`         VARCHAR(64)  NOT NULL,
                  `data`       JSON         NOT NULL,
                  `updated_at` TIMESTAMP    NOT NULL
                               DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    _state["conn"] = conn


# =============================================================================
# PUBLIC API
# =============================================================================

def init() -> bool:
    """
    Connect, create schema if needed, and mark persistence live.

    Returns True when MySQL is in play. Returns False when it is switched off
    or unreachable and DB_STRICT is false. Raises PersistenceError when
    unreachable and DB_STRICT is true.
    """
    if not CONFIG["enabled"]:
        _state["error"] = "disabled via DB_ENABLED=false"
        return False
    try:
        _ensure_schema()
        _state["ok"] = True
        _state["error"] = None
        _failures.clear()
        return True
    except Exception as exc:                      # pymysql raises many shapes
        _state["ok"] = False
        _state["error"] = f"{type(exc).__name__}: {exc}"
        if CONFIG["strict"]:
            raise PersistenceError(
                f"MySQL unreachable and DB_STRICT=true — {_state['error']}"
            ) from exc
        return False


def is_live() -> bool:
    return bool(_state["ok"])


def failures() -> dict:
    """
    A copy of {collection: error} for every collection whose last sync failed.

    Empty is the healthy answer. A copy rather than the dict itself, because a
    caller iterating this while a request thread syncs would otherwise be
    walking a dict that is being mutated under it.
    """
    return dict(_failures)


# What a collection is called when a human is being told about it. A strip that
# says "boqs" is telling the user the name of a MySQL table; one that says
# "bills of quantities" is telling them which of their work is at risk.
LABELS = {
    "products":   "products",
    "quotations": "quotations",
    "proformas":  "proforma invoices",
    "invoices":   "tax invoices",
    "purchases":  "purchase orders",
    "specs":      "specifications",
    "boqs":       "bills of quantities",
    "ra_bills":   "RA bills",
    "addresses":  "addresses",
    "settings":   "company settings",
}


def _join(items: list) -> str:
    """'a', 'a and b', 'a, b and c'."""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _failed_names() -> list:
    """Failed collections in COLLECTIONS order, so the wording is stable."""
    return [c for c in COLLECTIONS if c in _failures]


def failure_note() -> str:
    """
    A plain sentence saying what is not being saved, or "" when all is well.

    **No exception text.** This is the sentence the nav strip shows a user, and
    the person reading it is a fire-contractor's office staff, not a DBA — a
    MySQL column error in the page furniture is noise they cannot act on. The
    raw error is still one hover away in `failure_detail()`, which is what the
    strip hangs off its `title=`, so a screenshot still carries it.

    Two conditions produce a note, and the distinction is the whole reason this
    is not just `not is_live()`:

    - **MySQL was unreachable at boot** with DB_STRICT off. The app is running
      in memory by fallback, not by choice. `sync()` returns early so no
      collection ever fails, which means `_failures` stays empty and would say
      everything is fine — the worst available answer.
    - **A write failed** after a successful boot. Then the collections are
      named — in words, via `LABELS` — because "your bills of quantities are
      not being saved" is actionable and "something went wrong" is not.

    `DB_ENABLED=false` deliberately produces **no note**. That is a chosen
    configuration with a startup banner of its own, and painting every dev run
    and every test red is how a warning stops being read.
    """
    if not CONFIG["enabled"]:
        return ""
    if not _state["ok"]:
        return "Nothing is being saved - the database is not connected."
    names = _failed_names()
    if not names:
        return ""
    what = _join([LABELS.get(c, c) for c in names])
    # Always "are": every label is a plural noun phrase, so the verb follows the
    # words and not the number of collections. "Bills of quantities is" is one
    # collection and still wrong.
    rest = ("" if len(names) == len(COLLECTIONS)
            else " Everything else is saving normally.")
    return f"{what.capitalize()} are not being saved.{rest}"


def failure_detail() -> str:
    """
    The raw error text behind `failure_note()`, or "" when there is none.

    This is the half a developer needs and a user does not: the strip carries it
    in `title=` rather than in the visible text, so it survives a screenshot
    without putting a `DataError` in front of somebody quoting a fire system.
    One line per failed collection, keyed by the MySQL table name rather than
    the friendly label, because that is what matches the server's own logs.
    """
    if not CONFIG["enabled"]:
        return ""
    if not _state["ok"]:
        return _state["error"] or "not initialised"
    return "\n".join(f"{c}: {_failures[c]}" for c in _failed_names())


def status() -> str:
    """One-line human summary, used for the startup banner."""
    # ASCII only: the Windows console is cp1252 and turns em-dashes into mojibake.
    if _state["ok"]:
        base = (f"MySQL {CONFIG['user']}@{CONFIG['host']}:{CONFIG['port']}"
                f"/{CONFIG['name']} - persistence ON")
        # The console gets the raw errors, not the friendly sentence: this line
        # is read by whoever is looking after the server.
        if _failures:
            return f"{base} - FAILING: {'; '.join(failure_detail().splitlines())}"
        return base
    return f"in-memory only - {_state['error'] or 'not initialised'}"


def _blob(record) -> str:
    """Canonical JSON for a record. sort_keys makes the digest stable."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


def _digest(blob: str) -> str:
    """
    The sha256 of a record's canonical JSON, as hex.

    Takes the blob rather than the record because sync() needs the JSON anyway —
    it is what gets written — and serialising twice would cost more than the
    hashing does. `_blob`'s sort_keys is what makes this stable across runs;
    without it a dict reordering would look like an edit.
    """
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_into(store: dict) -> int:
    """
    Fill STORE from MySQL at startup.

    Mutates the existing dicts in place rather than replacing them, because
    every blueprint already holds a reference to those exact objects.
    """
    if not _state["ok"]:
        return 0

    loaded = 0
    conn = _conn()
    for coll in COLLECTIONS:
        target = store.setdefault(coll, {})
        target.clear()
        _digests[coll].clear()
        with conn.cursor() as cur:
            cur.execute(f"SELECT `id`, `data` FROM `{coll}`")
            for rid, raw in cur.fetchall():
                record = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                target[rid] = record
                # Prime the digest so an untouched record is not rewritten on
                # the very first sync.
                _digests[coll][rid] = _digest(_blob(record))
                loaded += 1
    return loaded


def _sync_collection(conn, store: dict, coll: str) -> tuple:
    """
    Write one collection's changes. Returns (written, deleted). May raise.

    The digest cache is advanced **only after** the statement that wrote those
    rows returned. A batch that raises therefore leaves every row in it looking
    changed, which is precisely what makes the next request retry them. Upserts
    and deletes are both idempotent, so re-running a batch that half-landed is
    safe.
    """
    current = store.get(coll) or {}
    cache   = _digests[coll]
    written = deleted = 0

    # (id, json, digest). The JSON goes to MySQL, the digest goes in the cache —
    # the blob is not retained past this function, which is the whole saving.
    pending = []
    for rid, record in current.items():
        blob = _blob(record)
        dig  = _digest(blob)
        if cache.get(rid) != dig:
            pending.append((rid, blob, dig))

    gone = [rid for rid in cache if rid not in current]

    if pending:
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO `{coll}` (`id`, `data`) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE `data` = VALUES(`data`)",
                [(rid, blob) for rid, blob, _ in pending],
            )
        for rid, _blob_, dig in pending:
            cache[rid] = dig
        written = len(pending)

    if gone:
        with conn.cursor() as cur:
            cur.executemany(
                f"DELETE FROM `{coll}` WHERE `id` = %s",
                [(rid,) for rid in gone],
            )
        for rid in gone:
            cache.pop(rid, None)
        deleted = len(gone)

    return written, deleted


def _note_failure(coll: str, exc: Exception) -> str:
    """Record a collection's failure, printing only when the message changes."""
    note = f"{type(exc).__name__}: {exc}"
    if _failures.get(coll) != note:
        # Only on change: teardown_request runs on EVERY request, and a
        # permanently oversized record would otherwise print this line a
        # hundred times a minute and bury the one that mattered.
        print(f"  !! persistence failed on '{coll}' - {note}")
    _failures[coll] = note
    return note


def _note_recovery(coll: str) -> None:
    if _failures.pop(coll, None) is not None:
        print(f"  * persistence recovered on '{coll}'")


def sync(store: dict) -> dict:
    """
    Persist everything that changed since the last sync.

    Returns {"written": n, "deleted": n, "failed": [collection, ...]} — handy
    in tests and logs. Never raises: a persistence hiccup must not turn a
    working page into a 500.

    Two properties this function exists to guarantee, both of which it did NOT
    have before and both of which cost real data:

    1. **A failing collection is isolated.** Each of the nine is written inside
       its own try/except, so one record MySQL refuses — a `data` blob past
       `max_allowed_packet`, a constraint, a truncation — stops that collection
       and only that one. It used to wrap all nine in a single try, so a single
       bad BOQ took products, quotations, invoices and addresses down with it.

    2. **A failure is retried, not fatal.** The old code set `_state["ok"] =
       False` on any exception, which made every later sync return immediately:
       persistence went dark app-wide, until somebody restarted the process, on
       the strength of one transient error. Now the failure is recorded against
       its collection and the next request tries again. A dropped connection
       heals itself on the next `_conn()` ping; an oversized record keeps
       failing and keeps saying so.

    The user-visible half of this lives in `failure_note()`, which the nav strip
    renders. A `print` to stdout is not a signal anybody working in a browser
    will ever see.
    """
    result = {"written": 0, "deleted": 0, "failed": []}
    if not _state["ok"]:
        return result

    with _lock:
        # One ping per request, not one per collection. If the connection
        # itself is gone then nothing can be written, so every collection is
        # marked failed — and the next request's ping(reconnect=True) is what
        # brings them all back without a restart.
        try:
            conn = _conn()
        except Exception as exc:
            for coll in COLLECTIONS:
                _note_failure(coll, exc)
            result["failed"] = list(COLLECTIONS)
            return result

        for coll in COLLECTIONS:
            try:
                written, deleted = _sync_collection(conn, store, coll)
            except Exception as exc:      # pymysql raises many shapes
                _note_failure(coll, exc)
                result["failed"].append(coll)
            else:
                result["written"] += written
                result["deleted"] += deleted
                _note_recovery(coll)

    return result


def reset(store: dict = None) -> None:
    """Drop every row in every collection. Used by tests; never by the app."""
    if not _state["ok"]:
        return
    _failures.clear()
    conn = _conn()
    with conn.cursor() as cur:
        for coll in COLLECTIONS:
            cur.execute(f"DELETE FROM `{coll}`")
            _digests[coll].clear()
    if store is not None:
        for coll in COLLECTIONS:
            store.get(coll, {}).clear()
