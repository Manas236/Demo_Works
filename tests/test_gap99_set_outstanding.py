"""
ABOUT.md §7 gap 99, closed 31 October 2026 (§0 sixty-fourth block, Part 6):
a merged RA set's outstanding is measured against the merged tax invoice's
ROUNDED total, so a fully paid set reads 0.00.

The .50 boundary is the case that matters: legs of 1,000.25 + 500.25 =
1,500.50, rounded HALF UP to 1,501 on the merged invoice. The customer pays
1,501. Measured against the legs alone that read −0.50 (a phantom credit)
and carried onto the next bill's previous balance.
"""

import pytest

import merged_ra as MR
import ra as RA
from store import STORE


def _bill(rid, leg, no, grand, status="issued"):
    STORE["ra_bills"][rid] = {"id": rid, "boq_id": "b99", "ra_no": no, "leg": leg,
                              "ref": f"RA{no}", "status": status, "grand_total": grand}


def _receipt(rcid, ra_id, amount):
    STORE["receipts"][rcid] = {"id": rcid, "ra_id": ra_id, "boq_id": "b99",
                               "amount": amount, "date": "2026-10-31"}


@pytest.fixture()
def the_set(client):
    for c in ("ra_bills", "receipts", "merged_ras"):
        STORE.setdefault(c, {}).clear()
    _bill("s", "supply", 1, 1000.25)
    _bill("i", "installation", 2, 500.25)
    STORE["merged_ras"]["m"] = {
        "id": "m", "status": "live", "supply_ra_id": "s", "installation_ra_id": "i",
        "grand_total": 1501.0, "rounding_off": 0.5, "round_off_on": True}
    yield
    for c in ("ra_bills", "receipts", "merged_ras"):
        STORE[c].clear()


def test_a_fully_paid_set_reads_zero_at_the_half_rupee_boundary(the_set):
    _receipt("r1", "s", 1000.75)      # the rounded figure, split across the legs
    _receipt("r2", "i", 500.25)
    assert MR.balance(STORE["merged_ras"]["m"]) == 0.0
    assert RA.outstanding_of(STORE["ra_bills"]["s"]) == 0.0
    assert RA.outstanding_of(STORE["ra_bills"]["i"]) == 0.0


def test_the_next_bill_carries_no_phantom_balance(the_set):
    _receipt("r1", "s", 1000.75)
    _receipt("r2", "i", 500.25)
    bal, refs = RA.previous_balance("b99", 3)
    assert bal == 0.0 and refs == []


def test_an_unpaid_set_owes_the_rounded_invoice(the_set):
    assert MR.balance(STORE["merged_ras"]["m"]) == 1501.0


def test_a_cancelled_set_rounds_nothing(the_set):
    STORE["merged_ras"]["m"]["status"] = "cancelled"
    assert RA.set_round_off(STORE["ra_bills"]["s"]) == 0.0


def test_a_merge_without_round_off_moves_nothing(the_set):
    STORE["merged_ras"]["m"]["grand_total"] = 1500.50
    STORE["merged_ras"]["m"]["rounding_off"] = 0.0
    assert RA.outstanding_of(STORE["ra_bills"]["s"]) == 1000.25
    assert MR.balance(STORE["merged_ras"]["m"]) == 1500.50
