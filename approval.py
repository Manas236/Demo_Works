"""
approval.py — the approval ladder  (CLIENT_CHANGES-2.md **B6** and **B7**)
==========================================================================

Built under the **fourth 29 August 2026** override block in `CLIENT_CHANGES.md`
§0. Before that block B6 and B7 were gated and nothing here existed.

**This first half is the record shape and the grandfather rule.** The ladder
itself, the creator guard and B7's print gate follow; what is here is the field
every one of them reads — `created_by` — and the honest answer to the records
that predate it.

Which documents are approvable
------------------------------
CC-2 **B6** names four, and `DOCUMENTS` below is that list:

    - **Charges:** three-step ladder — Director → Operations Head → HR, in sequence
    - **RA / Tax Invoice / PO:** Operations Head + Director

"PO" is the **real purchase order** (`purchase.py`, `STORE["purchases"]`) — the
document this company issues to a vendor and the one A2's discount and A3's
extra lines land on. It is not the draft PO (`po_draft.py`), which is a working
sheet on the way to it and has no vendor holding it.

⚠ **The spelling is "Operation Head".** CC-2 writes "Operations Head"; the
application's role — `auth.BUILTIN_ROLES["operation-head"]` — is "Operation
Head", and the application's spelling is the one that has to match a lookup.

`created_by`
------------
Every approvable record gains `created_by`, captured **at the write site** from
the session by `stamp_creator()`. Not derived later, not inferred from an audit
log, and not optional: B6's load-bearing rule is that a user cannot approve a
record they created, and a rule about the creator needs the creator recorded at
the moment there is one.

Records that predate this module — the grandfather rule
--------------------------------------------------------
Records written before the field existed have no creator, and neither obvious
answer is acceptable: refusing approval outright strands live bills, and
allowing anyone to approve while pretending the creator rule held would be a lie
about records nobody checked.

So a record backfilled by `tools/backfill_created_by.py` carries
`created_by = None` **and** `pre_approval_system = True`, and:

1. it **is** approvable by any holder of the relevant permission whose role sits
   on the ladder — the creator guard cannot apply where there is no creator;
2. it **prints**, because B7's gate cannot fairly be applied to a document
   issued before the gate existed;
3. it renders **on screen only** with a visible marker saying so — never on any
   printed sheet;
4. and the set is **pinned**. The migration records its own timestamp and count
   in `STORE["settings"]["approval_migration"]`, and
   `tests/test_approval_grandfather.py` fails if any record created after that
   moment lacks a `created_by`. **That test is the point of the whole rule** —
   without it the exception is a permanent hole that every future record can
   fall into.

A record with neither a `created_by` nor the grandfather mark — a test fixture,
a demo seed — is treated as *creator unknown*: the guard cannot apply to it
either. It is **not** counted in the pinned set, and the pin test is what stops
that leniency reaching anything the application itself wrote.
"""

import datetime

import auth
from store import STORE


# =============================================================================
# THE APPROVABLE DOCUMENTS  (B6)
# =============================================================================
# `steps` are **role slugs** — the keys of `auth.BUILTIN_ROLES`, not display
# names and not permission ids. They are carried here from the first commit so
# the migration and the pin test have one list of what "approvable" means,
# rather than two that can drift apart.

DOCUMENTS = {
    "charge": {
        "collection": "charges",
        "label":      "charge",
        "steps":      ("director", "operation-head", "hr"),
        "sequential": True,
        "permission": "charge.approve",
        "list_endpoint": "charge.list_charges",
    },
    "ra": {
        "collection": "ra_bills",
        "label":      "RA bill",
        "steps":      ("operation-head", "director"),
        "sequential": False,
        "permission": "ra.approve",
        "list_endpoint": "ra.list_ras",
    },
    "invoice": {
        "collection": "invoices",
        "label":      "tax invoice",
        "steps":      ("operation-head", "director"),
        "sequential": False,
        "permission": "invoice.approve",
        "list_endpoint": "invoice.list_invoices",
    },
    "purchase": {
        "collection": "purchases",
        "label":      "purchase order",
        "steps":      ("operation-head", "director"),
        "sequential": False,
        "permission": "purchase.approve",
        "list_endpoint": "purchase.list_purchases",
    },
}

# The collection a document key writes to. `db.py` persists every one of these
# already — no new table and no new collection, because an approval is a fact
# ABOUT a document and lives on it.
COLLECTIONS = {k: v["collection"] for k, v in DOCUMENTS.items()}

# Where the migration writes its own record, under STORE["settings"]. Read by
# `tests/test_approval_grandfather.py`, which is what pins the exception.
MIGRATION_KEY = "approval_migration"

# The mark a grandfathered record carries. Named once so the migration, the
# predicate and the test cannot spell it three different ways.
GRANDFATHER_FIELD = "pre_approval_system"


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# =============================================================================
# READING A RECORD
# =============================================================================

def records(doc_key: str) -> dict:
    """The collection behind a document key, created on first use."""
    coll = COLLECTIONS.get(doc_key)
    if not coll:
        return {}
    return STORE.setdefault(coll, {})


def find(doc_key: str, record_id: str):
    """One record, or None. Never raises on an unknown document key."""
    return records(doc_key).get(str(record_id or "")) or None


def is_grandfathered(record) -> bool:
    """
    Did this record exist before the approval system did?

    True only for the explicit mark `tools/backfill_created_by.py` writes. It is
    never inferred from a missing `created_by`, because inferring it is exactly
    how the pinned set would grow — a record written next year with a bug in its
    create route would quietly join a set that was closed in August.
    """
    return bool((record or {}).get(GRANDFATHER_FIELD))


def creator_of(record) -> str:
    """The user id that wrote this record, or `""` when nobody knows."""
    return str((record or {}).get("created_by") or "")


def creator_is_known(record) -> bool:
    return bool(creator_of(record))


# =============================================================================
# WRITING THE CREATOR
# =============================================================================

# A distinct "argument not given" marker, because `None` is a meaningful value
# here: `stamp_creator(rec, user=None)` means "explicitly nobody", which is what
# a migration or a fixture passes, and it must not fall back to the session.
_UNSET = object()


def session_user():
    """
    The signed-in user, or None — **safe outside a request context.**

    `auth.current_user()` reaches for `flask.session` and raises when there is no
    request. This module is imported by `tools/backfill_created_by.py` and called
    from fixtures, so the answer outside a request is "nobody", not an exception.
    """
    from flask import has_request_context

    if not has_request_context():
        return None
    return auth.current_user()


def stamp_creator(record, user=_UNSET) -> None:
    """
    Capture `created_by` at the write site.

    Called from every create route of every approvable document. Writes the
    session's user id, or `""` when there is no session — which only happens in
    a fixture, since B5 refuses every one of those routes anonymously.

    Pass `user=None` to mean **explicitly nobody**; omit the argument to mean
    "whoever is signed in". The two are different questions and `_UNSET` is what
    keeps them apart.

    ⚠ It never writes `pre_approval_system`. That mark belongs to the migration
    alone, and `tests/test_approval_grandfather.py` fails if anything else sets
    it.
    """
    if not isinstance(record, dict):
        return
    user = session_user() if user is _UNSET else user
    record["created_by"] = str((user or {}).get("id") or "")


def migration_record() -> dict:
    """
    What the migration recorded about itself: when it ran and what it marked.

    `{}` when it has never run — which is the state of a fresh database, where
    there is nothing to grandfather because there is nothing older than this
    module.
    """
    got = STORE.get("settings", {}).get(MIGRATION_KEY)
    return dict(got) if isinstance(got, dict) else {}


def grandfathered_ids(doc_key: str) -> list:
    """Every record of one type carrying the grandfather mark, sorted."""
    return sorted(rid for rid, rec in records(doc_key).items()
                  if is_grandfathered(rec))


# =============================================================================
# THE ON-SCREEN MARKER — screen only, NEVER on a printed sheet
# =============================================================================
# ⚠ **This must not be called from a printed document.** CC-2 carries no
# requirement that anything about approval appears on paper, so nothing does,
# and this marker is the piece most likely to be pasted onto a sheet by
# accident. `tests/test_approval_b7.py` renders every pinned printed document
# and asserts the string is absent from all of them.

GRANDFATHER_NOTE = (
    "This record predates the approval system, so who raised it is not known. "
    "It can be approved by anyone on its ladder — the rule that a person "
    "cannot approve their own record has nobody to check against here.")
