"""
importstage.py — a staged Excel upload, held between the upload and the form
============================================================================
Moved out of `boqimport.py` on 5 October 2026 (CLIENT_CHANGES.md §0,
forty-second block, fix 1) so that the work-order importer stages a sheet
through **the SAME mechanism** the BOQ importer has used since 29 September
2026, rather than a second one of its own. The functions are `boqimport.py`'s
`purge()`, `_own()` and `_cap_per_user()` exactly, parameterised by the
collection they act on; `boqimport.py` calls them with `"boq_imports"` and its
own two limits, and every BOQ import test passes untouched.

What the mechanism is, in one place:

* **A STORE collection, persisted like every other** (`db.COLLECTIONS`): one
  row per staged upload, keyed by an unguessable token
  (`secrets.token_urlsafe(24)`), holding the read GRID — cell values, never
  the file. Because it is persisted, a staged import survives a restart of
  the process: `db.load_into()` brings it back at boot like any record.
* **Owned**: a row opens only for the user who uploaded it (`own()`).
* **Short-lived**: rows older than `STAGE_TTL_SECONDS` are purged on every
  request to an importer (`purge()`), and a row whose timestamp cannot be read
  is purged too — an import nobody can date is an import nobody should open.
* **Bounded**: the newest `MAX_STAGED_PER_USER` per user are kept
  (`cap_per_user()`).
* **Consumed** by the caller when the prefilled form renders.

⚠ **Each importer keeps its OWN collection** — `boq_imports`, `wo_imports`.
One collection shared by both would let a work-order upload evict somebody's
BOQ upload from the per-user cap, and would let a work-order token open on
`/boq/import/<token>`. The mechanism is shared; the rows are not.

A LEAF: it imports `store` and the standard library, and nothing else — a
whitelist test in `tests/test_import_directions.py` holds it. It renders
nothing, owns no route and knows neither importer.
"""

import datetime
import secrets
import time

from store import STORE

# The BOQ importer's limits, moved here with the mechanism. `boqimport.py`
# re-exports both names (its tests read them there) and passes its own.
STAGE_TTL_SECONDS = 24 * 3600
MAX_STAGED_PER_USER = 3


def now_text() -> str:
    """The `created_at` stamp a staged row carries — `boqimport._now()`'s shape."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_token() -> str:
    """An unguessable key for one staged upload."""
    return secrets.token_urlsafe(24)


def rows(collection: str) -> dict:
    """The staging collection itself."""
    return STORE.setdefault(collection, {})


def purge(collection: str, ttl: float = STAGE_TTL_SECONDS, now: float = None) -> int:
    """
    Delete every staged import older than `ttl` seconds. A row whose timestamp
    cannot be read is deleted too — an import nobody can date is an import
    nobody should be able to open. Returns how many went.
    """
    now = time.time() if now is None else now
    gone = 0
    staged = rows(collection)
    for tok, rec in list(staged.items()):
        ts = rec.get("created_ts") if isinstance(rec, dict) else None
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or now - ts > ttl:
            del staged[tok]
            gone += 1
    return gone


def own(collection: str, token: str, uid: str):
    """The staged import under `token` if user `uid` raised it, else None."""
    rec = rows(collection).get(str(token or ""))
    if not isinstance(rec, dict):
        return None
    if not uid or rec.get("user_id") != uid:
        return None
    return rec


def cap_per_user(collection: str, uid: str, limit: int = MAX_STAGED_PER_USER) -> None:
    """Keep the newest `limit` staged imports of user `uid`; delete the rest."""
    staged = rows(collection)
    mine = sorted(((rec.get("created_ts") or 0, tok) for tok, rec in staged.items()
                   if isinstance(rec, dict) and rec.get("user_id") == uid),
                  reverse=True)
    for _ts, tok in mine[limit:]:
        del staged[tok]
