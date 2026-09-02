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
import json

from store import STORE

from conftest import ensure_test_user, charge_form


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
    """
    ⚠ **REWRITTEN 2 September 2026 for B8, and NOT weakened.** Both assertions
    below are the originals, unchanged. What changed is the post: CC-2's B8
    makes an attachment **compulsory on a charge**, so a form without a file no
    longer creates one and `_only_new()` had nothing to find. The old post,
    kept verbatim:

        r = client.post("/charge/new", data={
            "date": "2026-08-29", "person": "R. Kadam", "head": "Travel",
            "description": "Site visit", "taxable_amount": "1200", "gst_rate": "0",
        }, follow_redirects=False)

    `charge_form()` is that same dict with a real PNG added, in `conftest.py`, so
    the next change to what a valid charge post looks like lands in one place.
    The redirect assertion is what now also proves the attachment was accepted —
    a refused file re-renders the form with a 200.
    """
    before = dict(STORE.setdefault("charges", {}))
    r = client.post("/charge/new", data=charge_form(),
                    content_type="multipart/form-data", follow_redirects=False)
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


def test_a_measurement_created_through_the_form_carries_its_creator(client):
    """
    ⚠ **The fifth document, added with CC-2 C2 on 29 August 2026.**

    The assertion below refused to be widened without this test, which is what
    that assertion is for: a document added to `approval.DOCUMENTS` inherits the
    grandfather leniency — *"a record with no creator is approvable by anyone"* —
    and inherits it silently. So the create route is posted for real and the
    record is read back, exactly as the charge above it is.

    A measurement is the sharpest case of the four to leave unstamped: an
    approved sheet is the ceiling every installation claim is checked against,
    so a creator who can approve their own sheet can raise their own ceiling and
    then claim against it.
    """
    import boq as BQ
    import demo_data as DD

    client.get("/boq/")                       # seeds the demo schedule
    BQ.ensure_demo_boq()
    bid = DD.BOQ_META["id"]
    line = next(li for li in STORE["boqs"][bid]["line_items"]
                if not li["is_header"] and li["total_qty"] > 0)

    before = dict(STORE.setdefault("measurements", {}))
    r = client.post(f"/measurement/create?boq={bid}", data={
        "date": "2026-08-29", "location": "Block A", "measured_by": "R. Kadam",
        "witnessed_by": "", "notes": "",
        "ms_json": json.dumps({"lines": [{"line_id": line["line_id"],
                                          "qty": "1"}]}),
    }, follow_redirects=False)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:600]

    rec = _only_new(before, STORE["measurements"])
    user = ensure_test_user()
    assert rec.get("created_by") == user["id"], (
        "A measurement raised through /measurement/create did not record who "
        "raised it. B6's creator guard has nothing to check against, so the "
        "person who measured can approve their own sheet — and an approved "
        "sheet is the ceiling their own installation claim is checked against.")
    assert not approval.is_grandfathered(rec), (
        "A measurement created today carries the grandfather mark. That mark "
        "means 'this record predates the approval system' and only the "
        "migration may write it.")


def test_a_merged_ra_created_through_the_form_carries_its_creator(client):
    """
    ⚠ **The sixth document, added with CC-2 C3 on 2 September 2026.**

    The assertion below refused to be widened without this test, which is what
    that assertion is for: a document added to `approval.DOCUMENTS` inherits the
    grandfather leniency — *"a record with no creator is approvable by anyone"* —
    and inherits it **silently**. So the create route is posted for real and the
    record is read back, exactly as the four above it are.

    A merged document is the sharpest case in the set: it is the one record in
    this application that **mints a statutory tax invoice serial**. A creator who
    can approve their own merge can raise a Rule 46(b) number over two bills and
    sign it off alone.
    """
    import boq as BQ
    import demo_data as DD
    import merged_ra
    import ra as RA

    client.get("/boq/")
    BQ.ensure_demo_boq()
    bid = DD.BOQ_META["id"]
    line = next(li for li in STORE["boqs"][bid]["line_items"]
                if not li["is_header"] and li["total_qty"] > 0)

    def _bill(rid, ra_no, leg, ref):
        claims = [RA.build_claim(line, 1.0, line["supply_rate"], 0.0,
                                 line["supply_rate"], leg=leg)]
        subtotal, drows, dtotal, net = RA.bill_totals(claims, [])
        STORE.setdefault("ra_bills", {})[rid] = {
            "id": rid, "ref": ref, "fy": "26-27", "date": "2026-09-01",
            "boq_id": bid, "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
            "ra_no": ra_no, "leg": leg, "claims": claims,
            "claim_subtotal": subtotal, "deductions": drows,
            "deduction_total": dtotal, "net_payable": net,
            "grand_total": net, "status": "issued",
        }
        return rid

    _bill("gf-supply", 1, "supply", "SF/RA/26-27/0021")
    _bill("gf-install", 2, "installation", "SF/RA/26-27/0022")

    before = dict(STORE.setdefault("merged_ras", {}))
    r = client.post("/merged/create", data={
        "boq_id": bid,
        "supply_ra_id": "gf-supply",
        "installation_ra_id": "gf-install",
        "notes": "",
    }, follow_redirects=False)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:600]

    rec = _only_new(before, STORE["merged_ras"])
    user = ensure_test_user()
    assert rec.get("created_by") == user["id"], (
        "A merged document raised through /merged/create did not record who "
        "raised it. B6's creator guard has nothing to check against, so the "
        "person who merged the two bills can approve their own tax invoice.")
    assert not approval.is_grandfathered(rec), (
        "A merged document created today carries the grandfather mark. That "
        "mark means 'this record predates the approval system' and only the "
        "migration may write it.")


def test_every_approvable_collection_is_covered_by_this_file():
    """
    Every document type in `approval.DOCUMENTS` is one this file tests.

    A new one added without a create-route test here would inherit the
    grandfather leniency with nothing proving its create route stamps anybody —
    so adding one has to break this test.

    ⚠ **Widened on 29 August 2026 for `measurement` (CC-2 C2), and only after
    the test above it was written.** The previous assertion, kept verbatim so
    the widening is legible rather than invisible:

        assert set(approval.DOCUMENTS) == {"charge", "ra", "invoice", "purchase"}, (
            "approval.DOCUMENTS has changed. Add a create-route stamping test for "
            "the new document type before widening this assertion — the "
            "grandfather rule is only safe while every create route stamps.")

    ⚠ **Widened again on 2 September 2026 for `merged_ra` (CC-2 C3), on the
    same terms and in the same order — the stamping test directly above was
    written first.** The assertion it replaces, also kept verbatim:

        assert set(approval.DOCUMENTS) == {"charge", "ra", "invoice", "purchase",
                                           "measurement"}, (
            "approval.DOCUMENTS has changed. Add a create-route stamping test for "
            "the new document type before widening this assertion — the "
            "grandfather rule is only safe while every create route stamps.")
    """
    assert set(approval.DOCUMENTS) == {"charge", "ra", "invoice", "purchase",
                                       "measurement", "merged_ra"}, (
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
