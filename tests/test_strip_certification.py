"""
The one-shot certification migration — `tools/strip_certification.py`.

`tools/` is not imported by the app, so nothing else in this suite would notice
if this script rotted. It is tested for two properties that a migration over
somebody's real commercial records has to have and cannot be checked by reading
it: that it leaves nothing behind, and that running it twice is not a different
outcome from running it once.

The third property is the dangerous one and is asserted hardest: **no existing
bill is left as a draft.** Under the old model `status` was a
certification-tracking field with no gate attached, written as `"draft"` by
`create_ra()` and only ever moved by the certify form — so a stored `"draft"`
says nothing about whether the bill was sent, and every bill in the client's
database was raised, printed and submitted. Leaving one as a draft under the NEW
meaning would hand an already-submitted claim back to the edit and delete
routes, which is the exact lock this whole change exists to install.
"""

import importlib.util
import pathlib
import sys

import pytest

import ra
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent


def _load():
    """Import the script by path — `tools/` is not a package on sys.path."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location(
        "strip_certification", REPO / "tools" / "strip_certification.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mig():
    return _load()


def _old_bill(rid, ra_no, status, claims):
    """A bill in the shape this app wrote BEFORE the change: a legacy status,
    `certified_on`, and a certified pair on every claim row."""
    return {
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-06", "ra_no": ra_no, "leg": "supply",
        "boq_id": "b1", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "claims": claims, "claim_subtotal": 1000.0, "net_payable": 1000.0,
        "grand_total": 1180.0,
        "status": status, "certified_on": "2026-08-20", "notes": "",
    }


def _old_claim(lid, certified_qty=None, certified_rate=None):
    return {"line_id": lid, "item_no": "1", "section": "A",
            "description": "Line 1", "unit": "Mtrs",
            "approved_qty": 100.0, "approved_rate": 100.0, "prev_qty": 0.0,
            "qty": 10.0, "rate": 100.0, "amount": 1000.0,
            "balance_qty": 90.0, "rate_varies": False,
            "certified_qty": certified_qty, "certified_rate": certified_rate}


@pytest.fixture()
def legacy_store():
    """A store holding three pre-migration bills, one per old status."""
    store = {"ra_bills": {
        "r1": _old_bill("r1", 1, "draft", [_old_claim("aaa"), _old_claim("bbb")]),
        "r2": _old_bill("r2", 2, "submitted", [_old_claim("ccc", 8.0, 100.0)]),
        "r3": _old_bill("r3", 3, "certified", [_old_claim("ddd", 0.0)]),
    }}
    return store


# ═══════════════════════════════════════════════════════════════════════════
# WHAT IT REMOVES
# ═══════════════════════════════════════════════════════════════════════════

def test_it_strips_every_certified_key_from_bills_and_claim_rows(mig, legacy_store):
    result = mig.migrate(legacy_store)

    assert result["bills"] == 3
    assert result["claim_rows"] == 4          # 2 + 1 + 1
    assert result["keys"] == 11               # 3 x certified_on + 4 x 2 on rows

    for bill in legacy_store["ra_bills"].values():
        assert "certified_on" not in bill
        for c in bill["claims"]:
            assert "certified_qty" not in c
            assert "certified_rate" not in c


def test_it_touches_no_claimed_figure(mig, legacy_store):
    """It removes a ruling; it must not restate a claim. Every figure the bill
    was issued for survives byte for byte."""
    before = {rid: {c["line_id"]: {k: c[k] for k in
                                   ("qty", "rate", "amount", "approved_qty",
                                    "prev_qty", "balance_qty")}
                    for c in b["claims"]}
              for rid, b in legacy_store["ra_bills"].items()}

    mig.migrate(legacy_store)

    for rid, b in legacy_store["ra_bills"].items():
        for c in b["claims"]:
            assert {k: c[k] for k in before[rid][c["line_id"]]} == \
                before[rid][c["line_id"]]
        assert b["claim_subtotal"] == 1000.0
        assert b["grand_total"] == 1180.0


# ═══════════════════════════════════════════════════════════════════════════
# WHAT IT WRITES — and the draft rule
# ═══════════════════════════════════════════════════════════════════════════

def test_every_existing_bill_becomes_issued_including_the_drafts(mig, legacy_store):
    """
    THE rule. "Never leave an existing bill as draft" — a stored `"draft"` under
    the old model was the value `create_ra()` wrote and the certify form was the
    only thing that ever moved it, so it does not mean "not sent".
    """
    mig.migrate(legacy_store)

    for rid, bill in legacy_store["ra_bills"].items():
        assert bill["status"] == "issued", rid
        assert bill["status"] in ra.STATUSES

    assert not [b for b in legacy_store["ra_bills"].values()
                if ra.is_draft(b)]


def test_it_adds_the_new_lifecycle_fields_empty(mig, legacy_store):
    """`issued_on` is left BLANK, not stamped with today: we do not know when
    these went out, and inventing the date would be the migration asserting
    something nobody told it."""
    mig.migrate(legacy_store)

    for bill in legacy_store["ra_bills"].values():
        assert bill["issued_on"] == ""
        assert bill["cancelled_on"] == ""
        assert bill["cancel_reason"] == ""


def test_a_migrated_bill_is_locked_against_edit_and_delete(mig, legacy_store):
    """The point of the whole exercise: after this, an already-submitted claim
    is not editable and not deletable."""
    mig.migrate(legacy_store)

    for bill in legacy_store["ra_bills"].values():
        assert ra.can_edit(bill)[0] is False
        assert ra.can_delete(bill)[0] is False


# ═══════════════════════════════════════════════════════════════════════════
# IDEMPOTENCE — including the re-run hazard
# ═══════════════════════════════════════════════════════════════════════════

def test_running_it_twice_touches_nothing_the_second_time(mig, legacy_store):
    first = mig.migrate(legacy_store)
    snapshot = repr(sorted(legacy_store["ra_bills"].items()))

    second = mig.migrate(legacy_store)

    assert first["bills"] == 3
    assert second["bills"] == 0
    assert second["keys"] == 0
    assert repr(sorted(legacy_store["ra_bills"].items())) == snapshot


def test_a_draft_created_AFTER_the_migration_is_never_flipped_to_issued(mig,
                                                                       legacy_store):
    """
    THE re-run hazard, and the reason `needs_migration()` keys on a
    certification marker rather than on the status alone.

    A blanket "set every bill to issued" would be idempotent in the trivial
    sense and catastrophic in practice: a stray second run months later would
    silently issue every draft somebody had in progress, locking their claims
    and their deletes. A post-migration draft carries no certified keys and a
    status the new vocabulary recognises, so it is not a candidate at all.
    """
    mig.migrate(legacy_store)

    legacy_store["ra_bills"]["r4"] = {
        "id": "r4", "ref": "SF/RA/26-27/0004", "ra_no": 4, "leg": "supply",
        "boq_id": "b1", "claims": [{"line_id": "eee", "qty": 5.0, "rate": 10.0,
                                    "amount": 50.0}],
        "status": "draft", "issued_on": "", "cancelled_on": "",
        "cancel_reason": "",
    }

    assert mig.needs_migration(legacy_store["ra_bills"]["r4"]) is False
    result = mig.migrate(legacy_store)

    assert result["bills"] == 0
    assert legacy_store["ra_bills"]["r4"]["status"] == "draft"
    assert ra.is_draft(legacy_store["ra_bills"]["r4"]) is True


def test_a_cancelled_bill_is_not_a_migration_candidate_either(mig):
    """The other new state. Nothing about it looks pre-migration, so a re-run
    must not resurrect it as issued — which would un-cancel it."""
    store = {"ra_bills": {"r9": {
        "id": "r9", "ra_no": 9, "claims": [], "status": "cancelled",
        "cancelled_on": "2026-08-15", "cancel_reason": "withdrawn",
        "issued_on": "",
    }}}

    assert mig.needs_migration(store["ra_bills"]["r9"]) is False
    assert mig.migrate(store)["bills"] == 0
    assert store["ra_bills"]["r9"]["status"] == "cancelled"


def test_a_bill_missing_the_status_key_entirely_is_migrated(mig):
    """Records written before `status` existed at all. They are the oldest
    bills in the database and the ones most certainly already submitted."""
    store = {"ra_bills": {"r0": {
        "id": "r0", "ra_no": 1, "claims": [{"line_id": "z", "qty": 1.0}],
    }}}

    assert mig.needs_migration(store["ra_bills"]["r0"]) is True
    assert mig.migrate(store)["bills"] == 1
    assert store["ra_bills"]["r0"]["status"] == "issued"


def test_it_runs_on_an_empty_store_without_complaint(mig):
    assert mig.migrate({})["bills"] == 0
    assert mig.migrate({"ra_bills": {}})["bills"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# IT IS NOT WIRED INTO THE APP
# ═══════════════════════════════════════════════════════════════════════════

def test_no_app_module_imports_the_migration():
    """
    `product.backfill_line_item_hsn()` and `boq.backfill_line_ids()` are both
    deliberately explicit, and this is the third. A migration that runs itself
    on every boot is a migration nobody can decide not to run — and this one
    destroys data.

    Checked on the **AST**, not on the source text: `ra.py` names the script in
    a docstring, pointing the next reader at what rewrites the stored rows, and
    a grep for the string would fail on that comment while missing a real
    `import` written any other way round.
    """
    import ast

    for path in sorted(REPO.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not [n for n in names if "strip_certification" in n], \
                f"{path.name} imports the migration"

    assert STORE is not None      # the app imported cleanly without it
