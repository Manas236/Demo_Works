"""
The pre-measurement exception, pinned — CC-2 **C1** / **C2**.

Existing RA-Installation bills carry a typed quantity and no measurement behind
them. Requiring one retrospectively breaks live records; allowing it silently
pretends the rule held when it did not. So the set is **counted at migration and
closed**, and:

1. every marked bill keeps its typed quantity and renders with a marker
   saying so — **on screen only**;
2. **nothing created after the migration may join the set**;
3. and the marker never reaches a printed sheet.

⚠ **(2) IS THE POINT OF THIS FILE.** Without it "pre-measurement" stops being a
closed historical set and becomes a state any future bill can fall into, which
is the same as not having the rule at all. `tests/test_approval_grandfather.py`
makes the identical argument for `created_by`, and this is that argument applied
to the quantity rather than the creator.

⚠ **Do not weaken any of these to make a red suite green.** If (2) fails, an
installation claim was raised with nothing behind it and C1 has a hole in it.
"""

import json
import pathlib
import re

import pytest

import approval
import boq as BQ
import demo_data as DD
import measurement as MS
import ra
from store import STORE

from conftest import chain_ready, printable

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def seeded(client):
    """The demo schedule with NOTHING in front of it — no challan, no sheet."""
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    STORE.setdefault("settings", {}).pop(MS.PIN_KEY, None)
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    STORE.setdefault("settings", {}).pop(MS.PIN_KEY, None)


def _a_bill(boq_id, rid="pre-1", leg="installation", qty=2.0, **over):
    """One RA bill claiming a real quantity against a real BOQ line."""
    li = next(x for x in STORE["boqs"][boq_id]["line_items"]
              if not x["is_header"] and x["total_qty"] > 0)
    rec = {"id": rid, "ref": "SF/RA/26-27/0001", "fy": "26-27", "ra_no": 1,
           "date": "2026-08-06", "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001",
           "boq_rev_no": 0, "leg": leg,
           # `ra.build_claim()` rather than a hand-written dict: a claim row
           # carries `approved_qty` and `prev_qty` and the view page renders
           # both, so a hand-rolled row 500s on a formatter rather than telling
           # this file anything about the pin.
           "claims": [ra.build_claim(li, qty, 100.0, 0.0, 100.0)],
           "claim_subtotal": qty * 100.0, "deductions": [], "deduction_total": 0.0,
           "net_payable": qty * 100.0, "grand_total": qty * 100.0,
           "status": "issued", "issued_on": "2026-08-06", "cancelled_on": "",
           "cancel_reason": "", "notes": "",
           "created_at": "2026-08-06 10:00", "created_by": "somebody-else"}
    rec.update(over)
    STORE["ra_bills"][rid] = rec
    return rec


# ═══ 1. WHAT THE MIGRATION MARKS, AND WHAT IT LEAVES ALONE ═════════════════

def test_an_installation_bill_with_no_measurement_is_in_the_set(seeded):
    bill = _a_bill(seeded)
    assert MS.needs_pin(bill), (
        "an installation claim with no measurement behind it is exactly the "
        "record the exception exists for and the migration would skip it")


def test_a_SUPPLY_bill_is_not_in_the_set(seeded):
    """
    C1's supply proof is a delivery challan and **no quantity flows from it**,
    so a supply bill has nothing to be grandfathered against. Marking it would
    put a "typed quantity" note on a claim whose quantity was never going to
    come from anywhere else.
    """
    assert not MS.needs_pin(_a_bill(seeded, rid="sup-1", leg="supply"))


def test_a_bill_claiming_nothing_is_not_in_the_set(seeded):
    bill = _a_bill(seeded, rid="empty-1")
    bill["claims"] = []
    assert not MS.needs_pin(bill)


def test_a_bill_that_DOES_have_a_measurement_behind_it_is_not_in_the_set(seeded):
    chain_ready(seeded)                      # plants an APPROVED sheet
    assert not MS.needs_pin(_a_bill(seeded, rid="fine-1"))


def test_the_mark_is_never_inferred_from_a_missing_measurement(seeded):
    """
    ⚠ **The half that keeps the set closed.** `is_pre_measurement()` reads the
    explicit mark and nothing else. Inferring it from "no measurement on this
    chain" is exactly how a bill written next year, through a route with a bug
    in it, would quietly join a set that was closed in August.
    `approval.is_grandfathered()` makes the same argument one document along.
    """
    bill = _a_bill(seeded, rid="unmarked")
    assert MS.needs_pin(bill), "the fixture is not in the state under test"
    assert not MS.is_pre_measurement(bill), (
        "a bill with no mark reads as grandfathered — the exception is inferred "
        "rather than recorded, and it will grow")

    bill[MS.PRE_MEASUREMENT_FIELD] = True
    assert MS.is_pre_measurement(bill)


def test_a_marked_bill_is_not_marked_twice(seeded):
    """Idempotence: a second run of the migration must change nothing."""
    bill = _a_bill(seeded, rid="twice")
    bill[MS.PRE_MEASUREMENT_FIELD] = True
    assert not MS.needs_pin(bill)


# ═══ 2. THE PIN ITSELF — nothing created after the migration joins the set ══

def _run_pin():
    """What `tools/backfill_measurement_pin.py --write` does, in-process."""
    todo = sorted(rid for rid, b in (STORE.get("ra_bills") or {}).items()
                  if MS.needs_pin(b))
    for rid in todo:
        STORE["ra_bills"][rid][MS.PRE_MEASUREMENT_FIELD] = True
    STORE.setdefault("settings", {})[MS.PIN_KEY] = {
        "at": approval._now(), "count": len(todo), "ids": todo}
    return todo


def test_the_migration_record_is_absent_until_the_migration_runs(seeded):
    assert MS.migration_record() == {}, (
        "a fresh database claims a pre-measurement migration has run, so every "
        "bill written from now on would be measured against a moment that "
        "never happened")


def test_no_installation_bill_created_after_the_migration_lacks_a_measurement(
        seeded):
    """
    ⚠ **THE TEST THE WHOLE EXCEPTION EXISTS FOR.**

    It sweeps the real store. On a fresh database the sweep is empty, which is
    the honest answer — and the two tests below prove the sweep can actually
    see a violation, so an empty pass is not a vacuous one.
    """
    _a_bill(seeded, rid="old-1")
    pinned = _run_pin()
    assert pinned == ["old-1"]

    at = MS.migration_record()["at"]
    offenders = []
    for rid, b in (STORE.get("ra_bills") or {}).items():
        if str(b.get("leg") or "") != "installation":
            continue
        if str(b.get("created_at") or "") <= at:
            continue
        if MS.is_pre_measurement(b):
            offenders.append((rid, "carries the grandfather mark"))
        elif not MS.has_approved_measurement(str(b.get("boq_id") or "")):
            offenders.append((rid, "no approved measurement on its chain"))
    assert not offenders, (
        f"these installation bills were created AFTER the pin and have no "
        f"measurement behind them: {offenders}. The exception has grown, which "
        f"is the same as not having the rule.")


def test_the_sweep_can_actually_see_a_violation(seeded):
    """
    ⚠ **The vacuity check on the test above.** A sweep that passes because it
    found nothing to look at is a sweep that proves nothing. This plants exactly
    the record that must be caught and asserts the same walk catches it.
    """
    _a_bill(seeded, rid="old-1")
    _run_pin()
    at = MS.migration_record()["at"]

    _a_bill(seeded, rid="new-1", created_at="2999-01-01 00:00")

    offenders = [rid for rid, b in STORE["ra_bills"].items()
                 if str(b.get("leg") or "") == "installation"
                 and str(b.get("created_at") or "") > at
                 and not MS.has_approved_measurement(str(b.get("boq_id") or ""))]
    assert offenders == ["new-1"], (
        "the sweep in the test above cannot see a bill raised after the pin "
        "with nothing behind it, so its passing means nothing")


def test_the_pinned_moment_is_never_moved(seeded):
    """
    Re-running the migration after a month must not re-open the exception for
    everything written in between. The tool writes the record once.
    """
    _a_bill(seeded, rid="old-1")
    _run_pin()
    first = MS.migration_record()

    # What the tool does on a second run: it sees `already` and leaves it.
    already = MS.migration_record()
    assert already, "the record vanished"
    if not already:                                   # pragma: no cover
        STORE["settings"][MS.PIN_KEY] = {"at": "2999-01-01 00:00"}
    assert MS.migration_record()["at"] == first["at"]

    src = (REPO / "tools" / "backfill_measurement_pin.py").read_text(encoding="utf8")
    assert "if not already:" in src, (
        "the migration tool no longer guards the pinned moment — re-running it "
        "would move the moment and re-open the exception for every bill "
        "written since")


def test_the_recorded_count_is_the_set_that_was_marked(seeded):
    _a_bill(seeded, rid="old-1")
    _a_bill(seeded, rid="old-2", ref="SF/RA/26-27/0002")
    _a_bill(seeded, rid="sup-1", leg="supply")
    pinned = _run_pin()

    rec = MS.migration_record()
    assert rec["count"] == 2 == len(pinned)
    assert sorted(rec["ids"]) == ["old-1", "old-2"]
    assert all(MS.is_pre_measurement(STORE["ra_bills"][r]) for r in rec["ids"])
    assert not MS.is_pre_measurement(STORE["ra_bills"]["sup-1"])


# ═══ 3. A MARKED BILL KEEPS ITS FIGURES AND SAYS SO — ON SCREEN ════════════

def test_a_marked_bill_keeps_its_typed_quantity(client, seeded):
    """Nothing is recomputed and no figure moves."""
    bill = _a_bill(seeded, rid="old-1", qty=7.0)
    before = json.dumps(bill["claims"], sort_keys=True)
    _run_pin()
    assert json.dumps(bill["claims"], sort_keys=True) == before
    assert bill["net_payable"] == 700.0


def test_the_marker_is_on_the_bills_own_page(client, seeded):
    bill = _a_bill(seeded, rid="old-1")
    _run_pin()
    h = client.get(f"/ra/view/old-1").get_data(as_text=True)
    assert "Typed quantity" in h
    assert MS.PRE_MEASUREMENT_NOTE.split(",")[0] in h


def test_the_chip_is_in_the_register_row(client, seeded):
    _a_bill(seeded, rid="old-1")
    _run_pin()
    h = client.get("/ra/").get_data(as_text=True)
    assert "TYPED QUANTITY" in h


def test_an_UNMARKED_bill_carries_neither(client, seeded):
    """The other half: the marker appears only where the mark is."""
    _a_bill(seeded, rid="fresh-1")
    assert "Typed quantity" not in client.get("/ra/view/fresh-1").get_data(as_text=True)
    assert "TYPED QUANTITY" not in client.get("/ra/").get_data(as_text=True)


def test_the_marker_NEVER_reaches_a_printed_sheet(client, seeded):
    """
    ⚠ **On screen only.** A note on an issued claim saying its figures were
    typed rather than measured is exactly the sentence nobody wants read by a
    main contractor. CC-2 carries no requirement that anything about
    measurement appears on paper, so nothing does.
    """
    bill = _a_bill(seeded, rid="old-1")
    _run_pin()
    printable(bill)                      # B7 — an approved bill prints
    h = client.get("/ra/print/old-1").get_data(as_text=True)
    assert h, "the printed sheet did not render"

    for s in ("Typed quantity", "TYPED QUANTITY", MS.PRE_MEASUREMENT_NOTE,
              MS.PRE_MEASUREMENT_CHIP_TITLE):
        assert s not in h, f"the printed RA bill carries {s!r}"


def test_the_marker_is_written_in_exactly_one_place():
    """
    The note and the chip are one string each, in `measurement.py`. A second
    spelling in `ra.py` is a marker that will say something different after the
    next edit — `approval.GRANDFATHER_NOTE` is named once for the same reason.
    """
    ra_src = (REPO / "ra.py").read_text(encoding="utf8")
    assert "Typed quantity" not in ra_src, (
        "the marker's text is spelled out in ra.py as well as measurement.py")
    assert re.search(r"MS\.pre_measurement_marker\(", ra_src)
    assert re.search(r"MS\.pre_measurement_chip\(", ra_src)


# ═══ 4. THE ARITHMETIC A MARKED BILL SITS ON IS UNTOUCHED ══════════════════

def test_a_pre_measurement_project_can_still_be_claimed_against(seeded):
    """
    The grandfather rule at the arithmetic level: with no approved measurement
    on the chain, `ra.overclaims()` keeps the BOQ ceiling — so the bill's own
    project is not stranded by the module that arrived after it.
    """
    _a_bill(seeded, rid="old-1", qty=2.0)
    _run_pin()

    li = next(x for x in STORE["boqs"][seeded]["line_items"]
              if not x["is_header"] and x["total_qty"] >= 4)
    claim = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 1.0}]
    assert ra.overclaims(seeded, "installation", claim) == []


def test_once_a_measurement_EXISTS_the_ceiling_moves_even_for_that_project(seeded):
    """
    And the exception does not become a permanent exemption for the project. The
    moment an approved sheet lands on the chain, the ceiling is the measured
    quantity — including for a schedule that carries grandfathered bills.
    """
    _a_bill(seeded, rid="old-1", qty=2.0)
    _run_pin()

    li = next(x for x in STORE["boqs"][seeded]["line_items"]
              if not x["is_header"] and x["total_qty"] >= 4)
    STORE.setdefault("measurements", {})["ms-x"] = {
        "id": "ms-x", "ref": "SF/MS/26-27/0001", "fy": "26-27",
        "date": "2026-08-20", "boq_id": seeded, "created_by": "someone",
        "approval_status": approval.APPROVED,
        "items": [{"line_id": li["line_id"], "is_header": False,
                   "item_no": li["item_no"], "qty": 1.0}]}

    claim = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 2.0}]
    breaches = ra.overclaims(seeded, "installation", claim)
    assert breaches, (
        "a project carrying a grandfathered bill kept the BOQ ceiling after an "
        "approved measurement arrived — the exception became permanent")
    assert breaches[0]["reason"] == "overmeasured"
