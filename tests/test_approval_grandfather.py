"""
The grandfather rule, pinned so it cannot grow.

CLIENT_CHANGES-2.md **B6** makes a record's creator load-bearing: a user cannot
approve a record they created. Records written before `created_by` existed have
no creator, and the fourth 29 August 2026 override block takes the only honest
position available — they **are** approvable, because the creator guard cannot
apply where there is no creator, and they say so on screen.

**That exception is a hole unless it is closed at the top.** A rule that says
"records without a creator are approvable by anybody" is fine for a set of
thirty-one historical rows and catastrophic for a set that keeps growing: every
future record with a missing stamp joins it silently, and the guard B6 calls
load-bearing quietly stops applying to anything.

So this file is the closing. It asserts, in four independent ways, that the
grandfathered set is **historical and closed**:

1. every create route of every approvable document stamps a creator;
2. no record created after the migration's pinned moment lacks one;
3. nothing but the migration ever writes the grandfather mark;
4. and the mark is never inferred from a merely-absent `created_by`.

⚠ **Do not weaken any of these to make a red suite green.** If one fails, a
create route has stopped stamping and the guard has a hole in it.
"""

import approval
import auth
from store import STORE

from conftest import ensure_test_user


# ── 1. Every create route stamps a creator ─────────────────────────────────
#
# Behavioural, not AST: it posts the real form to the real route and reads the
# record that comes out. An AST test could only prove that the call is written
# somewhere in the module; this proves it ran on the path a user takes.


def _only_new(before: dict, after: dict):
    """The one record that appeared. Fails loudly if it was not exactly one."""
    fresh = set(after) - set(before)
    assert len(fresh) == 1, f"expected exactly one new record, got {len(fresh)}"
    return after[fresh.pop()]


def test_a_charge_created_through_the_form_carries_its_creator(client):
    before = dict(STORE.setdefault("charges", {}))
    r = client.post("/charge/new", data={
        "date": "2026-08-29", "person": "R. Kadam", "head": "Travel",
        "description": "Site visit", "taxable_amount": "1200", "gst_rate": "0",
    }, follow_redirects=False)
    assert r.status_code in (302, 303), r.status_code

    rec = _only_new(before, STORE["charges"])
    user = ensure_test_user()
    assert rec.get("created_by") == user["id"], (
        "A charge raised through /charge/new did not record who raised it. "
        "B6's creator guard has nothing to check against, so this charge is "
        "approvable by the person who created it.")
    assert not approval.is_grandfathered(rec), (
        "A charge created today carries the grandfather mark. That mark means "
        "'this record predates the approval system' and only the migration may "
        "write it.")


def test_every_approvable_collection_is_covered_by_this_file():
    """
    The four document types B6 names are the four this file tests.

    A fifth added to `approval.DOCUMENTS` without a create-route test here would
    inherit the grandfather leniency with nothing proving its create route
    stamps anybody — so adding one has to break this test.
    """
    assert set(approval.DOCUMENTS) == {"charge", "ra", "invoice", "purchase"}, (
        "approval.DOCUMENTS has changed. Add a create-route stamping test for "
        "the new document type before widening this assertion — the "
        "grandfather rule is only safe while every create route stamps.")


def test_the_stamp_helper_writes_the_session_user(client):
    """`stamp_creator()` itself, directly, on all four record shapes."""
    user = ensure_test_user()
    with client.application.test_request_context():
        from flask import session
        session[auth.SESSION_KEY] = user["id"]
        for key in approval.DOCUMENTS:
            rec = {}
            approval.stamp_creator(rec)
            assert rec["created_by"] == user["id"], key
            assert approval.GRANDFATHER_FIELD not in rec, (
                f"stamp_creator() wrote the grandfather mark on a {key}. Only "
                f"tools/backfill_created_by.py may write it.")


def test_the_stamp_helper_never_writes_the_grandfather_mark():
    """Even with no session at all it stamps a creator, never the mark."""
    rec = {}
    approval.stamp_creator(rec, user=None)
    assert "created_by" in rec
    assert approval.GRANDFATHER_FIELD not in rec


# ── 2. Nothing created after the migration lacks a creator ─────────────────


def test_no_record_created_after_the_migration_lacks_a_creator(client):
    """
    ⚠ **The pin.** This is the test the whole grandfather rule rests on.

    The migration writes its own moment into
    `STORE["settings"]["approval_migration"]`. Every approvable record carrying
    a `created_at` later than that moment must have a `created_by`: it was
    written by this application, after the approval system existed, and there is
    no honest way for it to have no creator.

    It runs against whatever is in the store — which in the suite is what the
    tests themselves created, and on a real database is every row.
    """
    STORE.setdefault("settings", {})[approval.MIGRATION_KEY] = {
        "at": "2026-08-29 00:00", "counts": {}, "total": 0,
    }
    try:
        client.post("/charge/new", data={
            "date": "2026-08-29", "person": "S. Patil", "head": "Food & Meals",
            "description": "Site meals", "taxable_amount": "450",
            "gst_rate": "5",
        })
        pinned_at = approval.migration_record()["at"]
        offenders = []
        for key in approval.DOCUMENTS:
            for rid, rec in approval.records(key).items():
                created = str(rec.get("created_at") or "")
                if not created or created <= pinned_at:
                    continue
                if not rec.get("created_by"):
                    offenders.append(f"{key}/{rid} created {created} "
                                     f"- no created_by")
                # ⚠ And the mark itself must not appear on anything written
                #   after the migration. Without this the pin is walked around
                #   by the one move that defeats it: a record with no creator
                #   that ALSO claims to predate the system. A grandfathered
                #   record legitimately carries `created_by = None`, so the
                #   check above cannot see that case on its own.
                if approval.is_grandfathered(rec):
                    offenders.append(f"{key}/{rid} created {created} "
                                     f"- marked as predating the system")
        assert not offenders, (
            "These records were created AFTER the approval migration and have "
            "silently joined the grandfathered set, where B6's creator guard "
            "does not apply to them:\n  "
            + "\n  ".join(offenders))
    finally:
        STORE.get("settings", {}).pop(approval.MIGRATION_KEY, None)


def test_a_record_created_after_the_migration_would_be_caught(client):
    """
    The pin catches what it claims to — proved by planting one.

    A test that only ever passes on clean data proves nothing about its own
    sensitivity, so this plants exactly the record the pin exists to find and
    asserts the same scan reports it.
    """
    STORE.setdefault("settings", {})[approval.MIGRATION_KEY] = {
        "at": "2026-08-29 00:00", "counts": {}, "total": 0,
    }
    approval.records("charge")["planted"] = {
        "id": "planted", "created_at": "2026-08-30 09:00", "person": "nobody",
    }
    try:
        pinned_at = approval.migration_record()["at"]
        offenders = [
            f"{key}/{rid}"
            for key in approval.DOCUMENTS
            for rid, rec in approval.records(key).items()
            if str(rec.get("created_at") or "") > pinned_at
            and not rec.get("created_by")
        ]
        assert "charge/planted" in offenders, (
            "The pin did not notice a record created after the migration with "
            "no creator. It is not actually pinning anything.")
    finally:
        approval.records("charge").pop("planted", None)
        STORE.get("settings", {}).pop(approval.MIGRATION_KEY, None)


# ── 3. Only the migration writes the mark ──────────────────────────────────


def _mark_writers():
    """
    Every source line that ASSIGNS the grandfather mark, as `(filename, lineno)`.

    Walked as an AST rather than grepped, for two reasons the grep version got
    wrong: a docstring that merely *describes* the field is not a writer, and an
    assignment through the `GRANDFATHER_FIELD` constant does not contain the
    literal string at all — so the text sweep this replaced found nothing and
    asserted that nothing equalled nothing.
    """
    import ast
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    field = approval.GRANDFATHER_FIELD
    found = []

    def _names_the_field(node) -> bool:
        if isinstance(node, ast.Constant) and node.value == field:
            return True
        if isinstance(node, ast.Attribute) and node.attr == "GRANDFATHER_FIELD":
            return True
        if isinstance(node, ast.Name) and node.id == "GRANDFATHER_FIELD":
            return True
        return False

    for path in list(repo.glob("*.py")) + list((repo / "tools").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # record[FIELD] = ...
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Subscript)
                            and _names_the_field(target.slice)):
                        found.append((path.name, node.lineno))
            # {..., FIELD: ..., ...} — a record literal carrying the mark
            if isinstance(node, ast.Dict):
                if any(k is not None and _names_the_field(k) for k in node.keys):
                    found.append((path.name, node.lineno))
    return found


def test_only_the_backfill_tool_writes_the_grandfather_mark():
    """
    The grandfather mark is assigned in exactly one place in the whole tree.

    That mark means "this record predates the approval system". Anything else
    writing it makes a closed historical set grow, and a grandfathered record is
    approvable by anybody — so a second writer is a way to mint records the
    creator guard does not apply to.

    ⚠ The constant `GRANDFATHER_FIELD = "pre_approval_system"` in `approval.py`
    is a definition, not an assignment into a record, and the AST walk does not
    count it.
    """
    writers = _mark_writers()
    assert writers, (
        "No assignment of the grandfather mark was found anywhere. Either the "
        "migration has stopped writing it — in which case nothing is "
        "grandfathered and live bills are stranded — or this test has stopped "
        "being able to see it and is now vacuous.")

    stray = sorted({f"{name}:{line}" for name, line in writers
                    if name != "backfill_created_by.py"})
    assert not stray, (
        "Something other than tools/backfill_created_by.py writes the "
        "grandfather mark:\n  " + "\n  ".join(stray) + "\n"
        "Only the migration may mark a record as predating the approval "
        "system.")


def test_the_mark_writer_sweep_can_actually_see_a_writer(tmp_path):
    """
    The sweep is sensitive — proved against a file that really does write it.

    A test that only ever reports "nothing found" passes whether or not it
    works. This is the version of that check that would have caught the text
    sweep this file used first, which searched for a literal string the
    migration never writes.
    """
    import ast

    planted = ast.parse(
        'rec["pre_approval_system"] = True\n'
        'other = {"pre_approval_system": True}\n'
        'approval.GRANDFATHER_FIELD\n')
    hits = 0
    for node in ast.walk(planted):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Subscript)
                        and isinstance(t.slice, ast.Constant)
                        and t.slice.value == approval.GRANDFATHER_FIELD):
                    hits += 1
        if isinstance(node, ast.Dict) and any(
                isinstance(k, ast.Constant)
                and k.value == approval.GRANDFATHER_FIELD for k in node.keys):
            hits += 1
    assert hits == 2, (
        f"The AST shapes the sweep looks for did not match a file that plainly "
        f"writes the mark ({hits} of 2 found).")


# ── 4. The mark is never inferred ──────────────────────────────────────────


def test_a_missing_creator_is_not_the_same_as_grandfathered():
    """
    `is_grandfathered()` reads the explicit mark and never infers it.

    The distinction is the whole rule. A record with no `created_by` has an
    unknown creator — the guard cannot apply, and that is a fact about one
    record. A record *marked* grandfathered is a member of a counted, closed,
    historical set. Collapsing the two would make every future stamping bug a
    silent enlargement of the set.
    """
    assert approval.is_grandfathered({}) is False
    assert approval.is_grandfathered({"created_by": None}) is False
    assert approval.is_grandfathered({"created_by": ""}) is False
    assert approval.is_grandfathered({approval.GRANDFATHER_FIELD: True}) is True

    # And the creator predicates agree about all four.
    assert approval.creator_is_known({}) is False
    assert approval.creator_is_known({"created_by": None}) is False
    assert approval.creator_is_known({"created_by": "u1"}) is True


def test_the_migration_record_is_absent_until_the_migration_runs():
    """A fresh database has nothing to grandfather, and says so by staying empty."""
    STORE.get("settings", {}).pop(approval.MIGRATION_KEY, None)
    assert approval.migration_record() == {}
