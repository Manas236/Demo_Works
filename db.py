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
"""

import json
import os
import threading

import pymysql
from dotenv import load_dotenv

# Read .env once, at import. Real environment variables win over the file.
load_dotenv(override=False)

# Collections in STORE that get persisted. Add a key here and it is durable —
# the table is created automatically on next start.
COLLECTIONS = ("products", "quotations", "proformas", "invoices", "purchases",
               "specs", "boqs", "addresses", "settings")

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

# Runtime state. `ok` is the single flag the rest of the app checks.
_state = {"ok": False, "error": None, "conn": None}
_lock = threading.Lock()

# digest[collection][id] = the JSON string most recently written for that row.
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


def status() -> str:
    """One-line human summary, used for the startup banner."""
    # ASCII only: the Windows console is cp1252 and turns em-dashes into mojibake.
    if _state["ok"]:
        return (f"MySQL {CONFIG['user']}@{CONFIG['host']}:{CONFIG['port']}"
                f"/{CONFIG['name']} - persistence ON")
    return f"in-memory only - {_state['error'] or 'not initialised'}"


def _blob(record) -> str:
    """Canonical JSON for a record. sort_keys makes the digest stable."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


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
                _digests[coll][rid] = _blob(record)
                loaded += 1
    return loaded


def sync(store: dict) -> dict:
    """
    Persist everything that changed since the last sync.

    Returns {"written": n, "deleted": n} — handy in tests and logs.
    Never raises: a persistence hiccup must not turn a working page into a 500.
    """
    result = {"written": 0, "deleted": 0}
    if not _state["ok"]:
        return result

    with _lock:
        try:
            conn = _conn()
            for coll in COLLECTIONS:
                current = store.get(coll) or {}
                cache   = _digests[coll]

                upserts = []
                for rid, record in current.items():
                    blob = _blob(record)
                    if cache.get(rid) != blob:
                        upserts.append((rid, blob))

                gone = [rid for rid in cache if rid not in current]

                if upserts:
                    with conn.cursor() as cur:
                        cur.executemany(
                            f"INSERT INTO `{coll}` (`id`, `data`) VALUES (%s, %s) "
                            "ON DUPLICATE KEY UPDATE `data` = VALUES(`data`)",
                            upserts,
                        )
                    for rid, blob in upserts:
                        cache[rid] = blob
                    result["written"] += len(upserts)

                if gone:
                    with conn.cursor() as cur:
                        cur.executemany(
                            f"DELETE FROM `{coll}` WHERE `id` = %s",
                            [(rid,) for rid in gone],
                        )
                    for rid in gone:
                        cache.pop(rid, None)
                    result["deleted"] += len(gone)
        except Exception as exc:
            # Degrade to in-memory rather than break the request. The banner
            # already told the user persistence was on, so say it broke.
            _state["ok"] = False
            _state["error"] = f"sync failed — {type(exc).__name__}: {exc}"
            print(f"  !! persistence lost: {_state['error']}")

    return result


def reset(store: dict = None) -> None:
    """Drop every row in every collection. Used by tests; never by the app."""
    if not _state["ok"]:
        return
    conn = _conn()
    with conn.cursor() as cur:
        for coll in COLLECTIONS:
            cur.execute(f"DELETE FROM `{coll}`")
            _digests[coll].clear()
    if store is not None:
        for coll in COLLECTIONS:
            store.get(coll, {}).clear()
