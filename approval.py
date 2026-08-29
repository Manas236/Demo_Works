"""
approval.py — the approval ladder  (CLIENT_CHANGES-2.md **B6** and **B7**)
==========================================================================

Built under the **fourth 29 August 2026** override block in `CLIENT_CHANGES.md`
§0. Before that block B6 and B7 were gated and nothing here existed.

What CC-2 actually says
-----------------------
**B6**, in full:

    - **Charges:** three-step ladder — Director → Operations Head → HR, in sequence
    - **RA / Tax Invoice / PO:** Operations Head + Director
    - **Any one Director's approval is sufficient.** Confirmed by the client.

    **Load-bearing rule:** a user cannot approve a record they created. This is
    checked against the **record's creator**, not against the approver's role.

Why the ladder is ROLES and the route gate is PERMISSIONS
---------------------------------------------------------
Two different questions, answered in two different places on purpose:

* **"May you reach the approve route at all?"** — `auth.ROUTE_PERMISSIONS`,
  keyed on `charge.approve` / `ra.approve` / `invoice.approve` /
  `purchase.approve`. That is B5's default-deny registry doing its ordinary job,
  and it stays the only answer to reachability.
* **"Does your approval move this record one rung up its ladder?"** — this
  module, keyed on the **roles** B4 names, because B6 states the ladder in role
  names and a permission cannot say which rung somebody stands on.

Keeping them apart is what lets an Owner suspend somebody's approval rights with
a checkbox (drop `ra.approve`) without dismantling the ladder itself.

⚠ **THE CREATOR GUARD IS NOT EXPRESSIBLE IN `ROUTE_PERMISSIONS`.** PROGRESS.md
established that the registry cannot carry a per-record condition — it maps an
endpoint to one permission string and knows nothing about which row is being
acted on. So the guard is a per-view check, it is written **once** in
`can_approve()` below, and `tests/test_approval.py` asserts that every approval
endpoint reaches it. A rule enforced in six places is a rule that will be
enforced in five after the next change.

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

from flask import Blueprint, redirect, request, url_for

import auth
import pipeline as P
from store import STORE

approval_bp = Blueprint("approval", __name__, url_prefix="/approval")


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

# Status values a record's `approval_status` may hold. A record carrying no
# value at all reads as `pending` — see `status_of()`.
PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
STATUSES = (PENDING, APPROVED, REJECTED)


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _esc(v) -> str:
    return P.esc(str(v or ""))


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


def status_of(record) -> str:
    """
    The record's approval state, normalised to one of `STATUSES`.

    **A record carrying no `approval_status` at all reads as `pending`**, which
    is the safe answer: it is the state that grants nothing. Grandfathering is a
    separate axis and is asked separately — see `is_grandfathered()`.
    """
    s = str((record or {}).get("approval_status") or "").strip().lower()
    return s if s in STATUSES else PENDING


def is_approved(record) -> bool:
    return status_of(record) == APPROVED


def is_rejected(record) -> bool:
    return status_of(record) == REJECTED


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


# =============================================================================
# READING A LADDER
# =============================================================================

def approvals_of(record) -> list:
    """The rungs already climbed, oldest first. Always a list."""
    got = (record or {}).get("approvals")
    return list(got) if isinstance(got, list) else []


def steps_taken(record) -> set:
    """The set of role slugs whose rung has been climbed."""
    return {str(a.get("role") or "") for a in approvals_of(record)}


def approvers_of(record) -> set:
    """The set of user ids that have already taken a rung on this record."""
    return {str(a.get("user_id") or "") for a in approvals_of(record)}


def outstanding_steps(doc_key: str, record) -> list:
    """
    The rungs still to climb, in ladder order.

    For a sequential ladder the caller usually wants only the first of these;
    `can_approve()` is what knows the difference.
    """
    spec = DOCUMENTS.get(doc_key) or {}
    taken = steps_taken(record)
    return [s for s in spec.get("steps", ()) if s not in taken]


def role_slugs_of(user) -> set:
    """
    The role slugs a user holds.

    Builtin roles carry the fixed id `role-<slug>` (`auth.ensure_builtin_roles`),
    so the slug is recoverable from the id without a second lookup. A role
    created through the UI carries a `uuid4` id and matches no ladder rung —
    correct, since the ladder is stated in terms of B4's six roles and an
    invented role is not one of them.
    """
    out = set()
    for rid in (user or {}).get("role_ids") or []:
        rid = str(rid or "")
        if rid.startswith("role-"):
            out.add(rid[len("role-"):])
    return out


def role_label(slug: str) -> str:
    """The display name of a role slug — "Operation Head", not "operation-head"."""
    role = auth.roles().get(f"role-{slug}")
    if role and role.get("name"):
        return str(role["name"])
    got = auth.BUILTIN_ROLES.get(slug)
    return got[0] if got else str(slug)


def step_for(doc_key: str, record, user) -> str:
    """
    The rung `user` would climb — assumes `can_approve()` has already allowed it.

    An Owner who holds no ladder role takes the lowest outstanding rung, so a
    one-Owner installation can still move a document rather than deadlocking on
    a role nobody has been given yet.
    """
    spec = DOCUMENTS.get(doc_key) or {}
    outstanding = outstanding_steps(doc_key, record)
    if not outstanding:
        return ""
    offered = [outstanding[0]] if spec.get("sequential") else outstanding
    mine = role_slugs_of(user)
    for slug in offered:
        if slug in mine:
            return slug
    return offered[0]


# =============================================================================
# THE GUARD  (B6) — written ONCE, called from every approval site
# =============================================================================

def can_approve(doc_key: str, record, user=_UNSET) -> tuple:
    """
    `(allowed, reason)` — may `user` move this record one rung up its ladder?

    ⚠ **THIS IS THE SINGLE APPROVAL GUARD AND EVERY APPROVAL SITE CALLS IT.**
    `tests/test_approval.py::test_every_approval_endpoint_reaches_the_guard`
    fails if an approval route is added that does not. Do not inline any part of
    it at a call site: a rule enforced in six places is a rule that will be
    enforced in five after the next change, and the fifth will be the one
    somebody's money goes through.

    The checks, in the order a person can act on them:

    1. **The record has to exist**, and has to be an approvable kind.
    2. **A finished ladder takes no more approvals.**
    3. **A rejected record takes none either** — it goes back to whoever raised
       it, and correcting it returns it to `pending`.
    4. **THE CREATOR GUARD (B6's load-bearing rule).** The creator of a record
       may not approve it. Checked against the *record's creator*, never against
       the approver's role, exactly as CC-2 specifies — because CC-2's own
       reason is that union permissions defeat the ladder, and a role test
       cannot see a union.
       It **cannot** apply where there is no creator. A grandfathered record, or
       one written by a fixture, has nobody to compare against, and refusing
       every such record would strand every bill that predates this module.
    5. **One user, one rung.** A user who has already taken a rung on this
       record may not take another. This is **ours, not CC-2's**, and it follows
       CC-2's own stated reasoning to its next step: B4 lets one user hold
       several roles, so without it a user holding Director *and* HR climbs two
       thirds of the charges ladder alone — the "union permissions defeat the
       ladder" failure one move along.
    6. **The rung has to be yours.** A sequential ladder offers only its next
       rung; an unordered one offers any rung still outstanding. An Owner
       satisfies any rung (B3: "Everything") and is still bound by 4 and 5,
       which is what keeps "Everything" from meaning "alone".
    """
    spec = DOCUMENTS.get(doc_key)
    if not spec:
        return False, "That is not an approvable document."
    if not record:
        return False, "That document no longer exists."

    user = session_user() if user is _UNSET else user
    if not user:
        return False, "You are not signed in."

    if is_approved(record):
        return False, (
            f"This {spec['label']} is already fully approved. There is nothing "
            f"left to approve.")

    if is_rejected(record):
        why = str(record.get("reject_reason") or "").strip()
        tail = f" - {why}" if why else ""
        return False, (
            f"This {spec['label']} was rejected{tail}. A rejected document goes "
            f"back to whoever raised it; correcting it returns it to pending "
            f"and the ladder starts again from the bottom.")

    # -- 4. THE CREATOR GUARD ------------------------------------------------
    uid = str(user.get("id") or "")
    if creator_is_known(record) and creator_of(record) == uid:
        return False, (
            f"You raised this {spec['label']}, so you cannot approve it. "
            f"Somebody else on the ladder has to.")

    # -- 5. One user, one rung -----------------------------------------------
    if uid in approvers_of(record):
        return False, (
            f"You have already approved this {spec['label']} once. One person "
            f"cannot climb two rungs of the same ladder.")

    # -- 6. Is this rung yours? ----------------------------------------------
    outstanding = outstanding_steps(doc_key, record)
    if not outstanding:
        return False, f"This {spec['label']} has no outstanding approvals."

    if auth.is_owner(user):
        return True, ""

    offered = [outstanding[0]] if spec["sequential"] else outstanding
    if not (role_slugs_of(user) & set(offered)):
        wanted = " or ".join(role_label(s) for s in offered)
        return False, (
            f"This {spec['label']} is waiting on {wanted}, and you do not hold "
            f"that role.")
    return True, ""


# =============================================================================
# WRITING AN APPROVAL
# =============================================================================

def record_approval(doc_key: str, record, user) -> str:
    """
    Write one rung. Returns the slug climbed, or `""` if nothing was written.

    Callers must have asked `can_approve()` first; this does not re-ask, because
    a guard that runs in two places is a guard that can disagree with itself.
    """
    slug = step_for(doc_key, record, user)
    if not slug:
        return ""
    record.setdefault("approvals", []).append({
        "role":      slug,
        "role_name": role_label(slug),
        "user_id":   str(user.get("id") or ""),
        "user_name": str(user.get("display_name") or user.get("username") or ""),
        "at":        _now(),
    })
    if outstanding_steps(doc_key, record):
        record["approval_status"] = PENDING
    else:
        record["approval_status"] = APPROVED
        record["approved_at"] = _now()
    return slug


def record_rejection(doc_key: str, record, user, reason: str) -> None:
    """
    Reject a record outright, at whatever rung it had reached.

    The rungs already climbed are **kept** rather than cleared, so the record
    still says who agreed with it before somebody did not. `clear_approvals()`
    is what empties them, and it runs when the document is corrected.
    """
    record["approval_status"] = REJECTED
    record["rejected_by"] = str(user.get("id") or "")
    record["rejected_by_name"] = str(user.get("display_name")
                                     or user.get("username") or "")
    record["rejected_at"] = _now()
    record["reject_reason"] = str(reason or "").strip()


def clear_approvals(record) -> None:
    """
    Return a record to the bottom of its ladder.

    Called whenever an approvable document's figures are edited: an approval
    describes the document somebody read, so a changed document has not been
    approved. Keeping the old rungs would let an edit inherit them.
    """
    if not isinstance(record, dict):
        return
    record["approvals"] = []
    record["approval_status"] = PENDING
    for key in ("approved_at", "rejected_by", "rejected_by_name",
                "rejected_at", "reject_reason"):
        record.pop(key, None)


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


# =============================================================================
# B7 — WHAT AN UNAPPROVED DOCUMENT MAY DO
# =============================================================================
# CC-2 **B7**, in full:
#
#     Real requirement: **an unapproved document may be viewed, but not printed
#     or downloaded.**
#
#     - Gate the print and download routes on approval status
#     - The view page needs a print stylesheet that blanks it, or `Ctrl+P`
#       bypasses the gate
#
# ⚠ **B7 IS ABOUT PRINTING, NOT ABOUT EDITING.** It says nothing at all about
# who may edit an approvable document or whether an approved one may be changed.
# `can_modify()` below is **ours**, taken because an approval a later edit can
# walk underneath is not an approval, and every one of its rules is listed as a
# judgement call in ABOUT.md §2i.


def can_print(doc_key: str, record) -> tuple:
    """
    `(allowed, reason)` — B7's gate, in one place.

    A document that has not finished its ladder does not print, and the refusal
    is **by URL** rather than by hiding the button — B5's rule, and the reason
    `tests/test_approval_b7.py` requests every one of these addresses directly.

    ⚠ **A grandfathered document prints.** It was issued before this gate
    existed, and applying the gate retrospectively would make every bill the
    client already holds unprintable on the day this shipped. That is the same
    reasoning the grandfather rule rests on everywhere else in this module, and
    it is why `tools/backfill_created_by.py` had to run before B7 could.

    ⚠ **A DRAFT RA BILL NO LONGER PRINTS, and that is a real loss, taken
    deliberately.** `ra.py`'s lifecycle gives a draft a printed DRAFT marker
    precisely so a working copy exists and can never be mistaken for an issued
    document. A draft is unapproved, and B7 is unqualified, so the working copy
    goes. This is recorded as a **collision between B7 and an existing
    deliberate design**, not as a tidy consequence of it — see ABOUT.md §2i and
    the pass report.
    """
    spec = DOCUMENTS.get(doc_key)
    if not spec:
        return True, ""
    if not record:
        return False, "That document no longer exists."
    if is_grandfathered(record):
        return True, ""
    if is_approved(record):
        return True, ""
    if is_rejected(record):
        return False, (
            f"This {spec['label']} was rejected, so it cannot be printed or "
            f"downloaded. Correct it and put it back through the ladder. You "
            f"can go on viewing it on screen.")
    waiting = ", ".join(role_label(s) for s in outstanding_steps(doc_key, record))
    return False, (
        f"This {spec['label']} has not been approved, so it cannot be printed "
        f"or downloaded. It is waiting on {waiting or 'approval'}. You can go "
        f"on viewing it on screen.")


# ── B7's second bullet: the print-blanking stylesheet ──────────────────────
#
# ⚠ **This is the WHOLE gate for the tax invoice and the purchase order, and
# that is a finding rather than a choice.** Those two documents have **no
# separate print route**: `/invoice/view/<id>` and `/purchase/view/<id>` render
# the A4 sheet itself. B7's first bullet — "gate the print and download routes"
# — assumes view and print are different URLs, which is true of the RA bill
# (`/ra/view` and `/ra/print`) and false of these two. Gating their view route
# would refuse the viewing B7 explicitly permits, so the stylesheet is what
# enforces B7 there and the route stays open.
#
# ⚠ **Doubled braces.** This string is interpolated into f-string pages, so every
# literal CSS brace is `{{` / `}}` — CLAUDE.md's most common way to break a page
# here. It is written as a plain (non-f) string so the braces are single in the
# source and survive one f-string interpolation at the call site.

PRINT_BLOCK_MARKER = "approval-print-block"

PRINT_BLOCK_CSS = """
<style>
@media print {
  body > *:not(#approval-print-block) { display: none !important; }
  #approval-print-block { display: block !important; }
}
</style>
<div id="approval-print-block" style="display:none">
  <h1 style="font-size:1.5rem;margin:0 0 1rem">Not approved &mdash; not for issue</h1>
  <p style="font-size:1rem;line-height:1.6;max-width:34em">
    This document has not completed its approval ladder. It may be read on
    screen, but it is not to be printed or issued &mdash; printing it would
    produce a document nobody has approved.
  </p>
</div>
"""


def print_block(doc_key: str, record) -> str:
    """
    The print-blanking stylesheet, or `""` when the document may be printed.

    ⚠ **Emitting nothing for an approvable document is what keeps the pinned
    print goldens byte-identical.** An approved sheet is exactly the page it was
    before this module existed, which is why `tests/test_print_golden.py` did
    not move by one byte for B7 — the golden records are approved, and an
    approved document renders no blanking block.
    """
    allowed, _reason = can_print(doc_key, record)
    return "" if allowed else PRINT_BLOCK_CSS


def can_modify(doc_key: str, record, user=_UNSET) -> tuple:
    """
    `(allowed, reason)` — may this record's figures still be changed?

    ⚠ **EVERY RULE HERE IS OURS, NOT CC-2's.** B7 is about printing and
    downloading. It says nothing about editing, so the three questions the pass
    brief raised — who may edit before submission, whether an approved document
    may be edited at all, whether a rejected one returns to editable — are
    **not settled by CC-2** and are settled here. Each takes the restrictive
    reading except where the restrictive reading creates an unreachable state,
    and that exception is argued rather than assumed.

    It **layers on top of** each module's own rules and replaces none of them.
    `ra.can_edit()` still refuses an issued bill; this refuses an approved one;
    a caller asks both.

    1. **An approved document is locked.** Amend it by raising the next
       document — a corrected claim, a revised order — not by editing figures
       two people have signed off. The restrictive reading of CC-2's silence,
       and the one that makes an approval mean anything at all.
    2. **A part-climbed ladder is locked too.** Once one rung is taken, an edit
       would change what that approver approved while their name stays on it.
       Have it rejected first; that sends it back.
    3. **A rejected document returns to its creator, and only to its creator.**
       ⚠ **The one place the restrictive option was NOT taken**, because there
       it creates an unreachable state rather than a strict one: an issued RA
       bill that is rejected and cannot be edited also cannot be deleted
       (`ra.can_delete()` refuses an issued bill) and cannot be printed (B7). It
       would be stranded with no move available to anybody. Editing it calls
       `clear_approvals()` and the ladder starts from the bottom.
    4. **Before any rung is climbed, only the creator edits.** Where there is no
       creator — grandfathered, or a fixture — the guard cannot apply and the
       module's own permission is the whole gate, exactly as in
       `can_approve()`.

    An Owner is exempt from the *creator* clauses (3 and 4) under B3's
    "Everything", and is **not** exempt from 1 and 2: a locked document is
    locked because of what it is, not because of who is asking.
    """
    spec = DOCUMENTS.get(doc_key)
    if not spec:
        return True, ""
    if not record:
        return False, "That document no longer exists."

    user = session_user() if user is _UNSET else user
    uid = str((user or {}).get("id") or "")

    if is_approved(record):
        return False, (
            f"This {spec['label']} has been approved, so its figures are "
            f"locked. Raise a corrected document rather than editing one that "
            f"has been signed off.")

    if is_rejected(record):
        if creator_is_known(record) and creator_of(record) != uid \
                and not auth.is_owner(user):
            return False, (
                f"This {spec['label']} was rejected and goes back to whoever "
                f"raised it. You did not raise it.")
        return True, ""

    if approvals_of(record):
        taken = ", ".join(sorted({str(a.get("role_name") or a.get("role") or "")
                                  for a in approvals_of(record)}))
        return False, (
            f"This {spec['label']} has already been approved by {taken}, so it "
            f"cannot be edited part-way up the ladder. Have it rejected first "
            f"— that sends it back to whoever raised it.")

    if creator_is_known(record) and creator_of(record) != uid \
            and not auth.is_owner(user):
        return False, (
            f"This {spec['label']} was raised by somebody else and has not "
            f"been approved yet. Only whoever raised it can change it.")

    return True, ""


_BADGE = ("display:inline-block;padding:2px 9px;border-radius:12px;"
          "font-size:0.74rem;font-weight:700;letter-spacing:.02em;"
          "border:1px solid;")

_BADGES = {
    PENDING:  ("AWAITING APPROVAL", "#fff8e1", "#8a6100", "#f0d089"),
    APPROVED: ("APPROVED",          "#e8f6ec", "#1c6b33", "#a9d9b8"),
    REJECTED: ("REJECTED",          "#fdecec", "#a32020", "#eeb4b4"),
}


def status_badge(record) -> str:
    """The approval state as a coloured chip. Screen only."""
    label, bg, fg, border = _BADGES[status_of(record)]
    return (f'<span style="{_BADGE}background:{bg};color:{fg};'
            f'border-color:{border}">{label}</span>')


def grandfather_marker(record) -> str:
    """
    The visible "creator unknown" marker for a grandfathered record.

    ⚠ **Screen only.** CC-2 carries no requirement that anything about approval
    appears on paper, so nothing does, and this is the piece most likely to be
    pasted onto a document by accident.
    """
    if not is_grandfathered(record):
        return ""
    return (
        '<div style="margin:.6rem 0;padding:.55rem .8rem;border-radius:8px;'
        'background:#f4f1ea;border:1px solid #ddd5c4;color:#5b513c;'
        'font-size:0.82rem;line-height:1.45">'
        '<b>Creator unknown.</b> ' + _esc(GRANDFATHER_NOTE) + '</div>')


GRANDFATHER_CHIP_TITLE = (
    "Creator unknown - this record predates the approval system")


def grandfather_chip(record) -> str:
    """
    The compact form of the marker, for a table cell. Screen only.

    A list row has no space for `GRANDFATHER_NOTE`, and the alternative — leaving
    it off the list entirely — would mean the marker only appears on a page
    somebody has already decided to open. So the chip is visible in the row and
    carries the sentence in its `title`.
    """
    if not is_grandfathered(record):
        return ""
    return (f'<span title="{_esc(GRANDFATHER_CHIP_TITLE)}" '
            f'style="{_BADGE}background:#f4f1ea;color:#5b513c;'
            f'border-color:#ddd5c4">CREATOR UNKNOWN</span>')


def cell(doc_key: str, record) -> str:
    """
    The list-row form: badge, grandfather chip, and whatever actions apply.

    ⚠ **Screen only**, like everything else in this section.
    """
    if doc_key not in DOCUMENTS or not record:
        return ""
    return (f'<div style="display:flex;flex-direction:column;gap:.3rem;'
            f'align-items:flex-start">{status_badge(record)}'
            f'{grandfather_chip(record)}'
            f'<span>{actions(doc_key, record)}</span></div>')


def ladder_summary(doc_key: str, record) -> str:
    """
    The rungs climbed and the rungs outstanding, as a screen block.

    Returns `""` for a document key that has no ladder, so a caller can drop it
    into a page without asking first.
    """
    spec = DOCUMENTS.get(doc_key)
    if not spec or not record:
        return ""
    rows = []
    for a in approvals_of(record):
        who = _esc(a.get("user_name"))
        rows.append(
            f'<li><b>{_esc(a.get("role_name") or a.get("role"))}</b> &mdash; '
            f'{who or "&mdash;"} <span style="color:#8a8578">'
            f'{_esc(a.get("at"))}</span></li>')
    for slug in outstanding_steps(doc_key, record):
        rows.append(
            f'<li style="color:#8a8578"><b>{_esc(role_label(slug))}</b> '
            f'&mdash; awaiting</li>')
    if is_rejected(record):
        why = _esc(record.get("reject_reason"))
        rows.append(
            f'<li style="color:#a32020"><b>Rejected</b> by '
            f'{_esc(record.get("rejected_by_name")) or "&mdash;"} '
            f'<span style="color:#8a8578">{_esc(record.get("rejected_at"))}'
            f'</span>{" &mdash; " + why if why else ""}</li>')
    return ('<ul style="list-style:none;padding:0;margin:.4rem 0;'
            'font-size:0.84rem;line-height:1.7">' + "".join(rows) + '</ul>')


def actions(doc_key: str, record, user=_UNSET) -> str:
    """
    The Approve / Reject links for one record, or `""` when neither is offered.

    Asks the same `can_approve()` the routes ask, so a button never appears
    where the URL would refuse. ⚠ **The reverse is not a gate**: hiding a button
    is not access control (B5's rule), and every one of these routes refuses by
    URL on its own — `tests/test_approval.py` hits them directly to prove it.
    """
    user = session_user() if user is _UNSET else user
    allowed, _reason = can_approve(doc_key, record, user)
    if not allowed:
        return ""
    rid = _esc(record.get("id"))
    return (
        f'<a class="btn btn-ghost" style="padding:.25rem .6rem;font-size:.78rem"'
        f' href="{url_for("approval.approve_" + doc_key, id=rid)}">Approve</a> '
        f'<a class="btn btn-ghost" style="padding:.25rem .6rem;font-size:.78rem"'
        f' href="{url_for("approval.reject_" + doc_key, id=rid)}">Reject</a>')


def panel(doc_key: str, record) -> str:
    """
    The whole on-screen approval block: marker, badge, ladder, actions.

    ⚠ **Screen only. Never call this from a printed document.**
    `tests/test_approval_b7.py` renders every pinned printed sheet and asserts
    none of these strings reaches one.
    """
    if doc_key not in DOCUMENTS or not record:
        return ""
    return (
        '<div style="margin:.8rem 0;padding:.8rem 1rem;border-radius:10px;'
        'background:#faf9f6;border:1px solid #e6e1d6">'
        '<div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap">'
        '<b style="font-size:.8rem;letter-spacing:.04em;color:#6b6455">'
        'APPROVAL</b>' + status_badge(record) + '</div>'
        + grandfather_marker(record)
        + ladder_summary(doc_key, record)
        + '<div style="margin-top:.5rem">' + actions(doc_key, record) + '</div>'
        + '</div>')


# =============================================================================
# THE APPROVAL ROUTES
# =============================================================================
# Eight endpoints — approve and reject, once per document type — registered from
# the `DOCUMENTS` table rather than written out four times.
#
# ⚠ **Why eight endpoints and not one taking a `<doc_key>`.**
# `auth.ROUTE_PERMISSIONS` maps an endpoint to exactly ONE permission string. A
# single `/approval/approve/<doc_key>/<id>` route would have to be classified
# once for four different permissions, which the registry cannot express — so it
# would have to be gated at `AUTHENTICATED` with the real check hidden inside
# the view, and that is precisely the weakening B5 exists to prevent. Four pairs
# of endpoints keep the registry the whole answer to reachability.
#
# The bodies are generated, so the guard is still written once and there is
# nothing to copy-paste out of step.


def _decision_page(title: str, body: str) -> str:
    """
    A small page for a decision or a refusal.

    `dashboard` is imported in the function body, not at module level: every
    document module imports this one, and `dashboard.py` is imported by all of
    them — the documented escape hatch `_shell()` uses elsewhere for exactly
    this reason (ABOUT.md §2).
    """
    from dashboard import BASE_STYLES, _nav
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{_esc(title)}</title>{BASE_STYLES}</head><body>"
            f"{_nav()}<div class='wrap' style='max-width:760px'>{body}</div>"
            f"</body></html>")


def _refusal(doc_key: str, reason: str):
    """
    Refuse one approval decision, carrying the reason to the list page.

    ⚠ **A redirect, not a 403, and the difference is load-bearing in two
    directions.**

    *House style*: this is a per-record business rule, and every other one in
    this repo answers the same way — `ra.edit_ra()` and `ra.delete_ra()` bounce
    to the record with `msg=why, type="error"` rather than rendering a refusal
    page. A guard that refuses in a shape nothing else uses is a guard somebody
    will handle differently at the next call site.

    *And it must not look like the gate*: `auth._gate()` refuses with a 403 or a
    bounce to `/login`, and `tests/test_nav_visibility.py::_is_refused` reads
    exactly those two shapes to decide whether the **route** was refused. A 403
    here would make every approval endpoint look permanently unreachable to that
    sweep — `can_reach()` says a Director may approve, and it is right; what is
    being refused is this record, today, for this person.

    It is still a refusal **by URL**: nothing is written, and typing the address
    achieves exactly what not typing it achieves. B5's rule is that hiding a
    button is not a gate, and this is the gate.
    """
    spec = DOCUMENTS[doc_key]
    return redirect(url_for(spec["list_endpoint"], msg=reason, type="error"))


def _do_approve(doc_key: str, id: str):
    spec = DOCUMENTS[doc_key]
    back = url_for(spec["list_endpoint"])
    record = find(doc_key, id)
    user = session_user()

    # THE GUARD. One call, one place - see `can_approve()`.
    allowed, reason = can_approve(doc_key, record, user)
    if not allowed:
        return _refusal(doc_key, reason)

    if request.method != "POST":
        return _decision_page(
            "Approve",
            f"<div class='page-top'><h1>Approve this "
            f"<span>{_esc(spec['label'])}</span></h1></div>"
            f"{grandfather_marker(record)}"
            f"{ladder_summary(doc_key, record)}"
            f"<form method='POST' style='display:flex;gap:.7rem;margin-top:1rem'>"
            f"<button type='submit' class='btn'>Approve as "
            f"{_esc(role_label(step_for(doc_key, record, user)))}</button>"
            f"<a href='{back}' class='btn btn-ghost'>Not now</a></form>")

    slug = record_approval(doc_key, record, user)
    if outstanding_steps(doc_key, record):
        msg = f"Approved as {role_label(slug)}."
    else:
        msg = f"Approved - this {spec['label']} is now fully approved."
    return redirect(url_for(spec["list_endpoint"], msg=msg, type="success"))


def _do_reject(doc_key: str, id: str):
    spec = DOCUMENTS[doc_key]
    back = url_for(spec["list_endpoint"])
    record = find(doc_key, id)
    user = session_user()

    # THE SAME GUARD. Rejecting is an approval decision, so it answers to the
    # same rules — a creator may not reject their own record into the ground any
    # more than they may approve it out of the ladder.
    allowed, reason = can_approve(doc_key, record, user)
    if not allowed:
        return _refusal(doc_key, reason)

    if request.method != "POST":
        return _decision_page(
            "Reject",
            f"<div class='page-top'><h1>Reject this "
            f"<span>{_esc(spec['label'])}</span></h1></div>"
            f"{grandfather_marker(record)}"
            f"{ladder_summary(doc_key, record)}"
            f"<form method='POST' style='margin-top:1rem'>"
            f"<label style='display:block;margin-bottom:.4rem'>Why is it being "
            f"rejected?</label>"
            f"<input type='text' name='reason' maxlength='300' "
            f"style='width:100%;padding:.5rem;margin-bottom:.9rem'>"
            f"<div style='display:flex;gap:.7rem'>"
            f"<button type='submit' class='btn'>Reject</button>"
            f"<a href='{back}' class='btn btn-ghost'>Not now</a></div></form>")

    record_rejection(doc_key, record, user, request.form.get("reason") or "")
    return redirect(url_for(spec["list_endpoint"],
                            msg=f"{spec['label'].capitalize()} rejected.",
                            type="success"))


def _register_routes():
    """
    Mint `approve_<key>` and `reject_<key>` for every document in `DOCUMENTS`.

    Written as a loop so the two view bodies exist once. Each endpoint still has
    its own name and its own row in `auth.ROUTE_PERMISSIONS`, which is the whole
    reason the routes are separate in the first place.
    """
    for key in DOCUMENTS:
        def _approve(id, _k=key):
            return _do_approve(_k, id)

        def _reject(id, _k=key):
            return _do_reject(_k, id)

        _approve.__name__ = f"approve_{key}"
        _reject.__name__ = f"reject_{key}"
        approval_bp.add_url_rule(f"/approve/{key}/<id>",
                                 endpoint=f"approve_{key}",
                                 view_func=_approve,
                                 methods=["GET", "POST"])
        approval_bp.add_url_rule(f"/reject/{key}/<id>",
                                 endpoint=f"reject_{key}",
                                 view_func=_reject,
                                 methods=["GET", "POST"])


_register_routes()
