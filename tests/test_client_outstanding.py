"""
Total Outstanding on the client register — CLIENT_CHANGES-2.md **A4**.

**A4 was already BUILT before this pass and no part of it was rebuilt.** This
file exists to *verify* that, and to close the one thing PROGRESS.md §6-D held
against it. It is a verification file, not a build.

### What was already there and is re-asserted here

`client._client_groups()` computed Outstanding as issued-less-received and
`/client/` rendered it, covered by `test_outstanding_counts_issued_bills_only`
and `test_receipts_reduce_outstanding_and_an_overpayment_shows_as_credit` in
`tests/test_client_segregation.py`. Those tests are untouched. The assertions
below re-state the same guarantees from a second angle so that A4's arithmetic
is pinned independently of the file that happened to build it.

### What changed under A4 on 27 August 2026, and what did not

The figure now also nets off A5's write-off, because that is what A5 is *for* —
CC-2 A5: *"This field lets that ₹10,000 be written off so outstanding is
correct internally."* That is A5's work landing on A4's figure, not a rebuild
of A4.

And the page now carries the caveat CC-2's A4 note asks for in as many words:
*"do not quietly present the figure as authoritative"*. It did not before
(PROGRESS.md §6-D), and A5 existing is exactly the moment the caveat starts
mattering rather than stopping mattering.
"""

import pytest

import client as CL
from store import STORE


@pytest.fixture()
def register(client):
    """One customer, one schedule, two bills — one issued, one still a draft."""
    STORE["receipts"].clear()
    STORE["ra_bills"].clear()
    STORE["boqs"]["boq-out"] = {
        "id": "boq-out", "ref": "BOQ-OUT", "date": "2026-07-01",
        "account_name": "Prestige Estates", "project_name": "Whitefield tower",
        "site_location": "Whitefield", "subtotal": 500000.0,
    }
    for rid, no, status, total in (("ra-out-1", 1, "issued", 100000.0),
                                   ("ra-out-2", 2, "draft", 250000.0)):
        STORE["ra_bills"][rid] = {
            "id": rid, "ra_no": no, "ref": f"SF/RA/26-27/000{no}",
            "leg": "supply", "boq_id": "boq-out", "boq_ref": "BOQ-OUT",
            "project_name": "Whitefield tower",
            "account_name": "Prestige Estates",
            "date": "2026-08-01", "status": status, "grand_total": total,
        }
    yield
    STORE["boqs"].pop("boq-out", None)


def _grp():
    groups, _dupes = CL._client_groups()
    assert len(groups) == 1, "the fixture is one customer"
    return list(groups.values())[0]


def _receipt(rid, ra_id, amount, write_off=0.0):
    STORE["receipts"][rid] = {
        "id": rid, "ref": rid, "date": "2026-08-20", "ra_id": ra_id,
        "ra_no": 1, "boq_id": "boq-out", "amount": amount,
        "write_off": write_off, "mode": "neft",
    }


# ── The arithmetic that was already built ──────────────────────────────────

def test_only_issued_bills_count_toward_outstanding(register):
    """
    A draft has not been sent, so nothing is owed on it. RA2 is ₹2,50,000 and
    contributes nothing.
    """
    grp = _grp()
    assert grp["total_issued"] == 100000.0
    assert grp["total_outstanding"] == 100000.0


def test_a_receipt_reduces_outstanding(register):
    _receipt("rc-1", "ra-out-1", 60000.0)
    grp = _grp()
    assert grp["total_received"] == 60000.0
    assert grp["total_outstanding"] == 40000.0


def test_an_overpayment_carries_forward_as_a_credit_and_is_not_clamped(register):
    """
    Signed, deliberately. Clamping at zero would state that money we are
    holding is not money we are holding.
    """
    _receipt("rc-1", "ra-out-1", 130000.0)
    grp = _grp()
    assert grp["total_outstanding"] == -30000.0


def test_the_schedule_value_is_not_the_outstanding(register):
    """
    ₹5,00,000 of schedule is not ₹5,00,000 owed. Only what has been billed and
    issued is owed, which is the distinction the register exists to draw.
    """
    grp = _grp()
    assert grp["total_boq"] == 500000.0
    assert grp["total_outstanding"] == 100000.0


# ── What A5 added to it ────────────────────────────────────────────────────

def test_a_write_off_comes_off_outstanding_but_not_off_received(register):
    _receipt("rc-1", "ra-out-1", 90000.0, write_off=10000.0)
    grp = _grp()
    assert grp["total_received"] == 90000.0
    assert grp["total_written_off"] == 10000.0
    assert grp["total_outstanding"] == 0.0


def test_the_three_figures_still_reconcile(register):
    """issued − received − written_off = outstanding, on every path."""
    _receipt("rc-1", "ra-out-1", 40000.0, write_off=5000.0)
    _receipt("rc-2", "ra-out-1", 20000.0)
    grp = _grp()
    assert (grp["total_issued"] - grp["total_received"]
            - grp["total_written_off"]) == grp["total_outstanding"]
    assert grp["total_outstanding"] == 35000.0


# ── The page ───────────────────────────────────────────────────────────────

def test_the_register_renders_the_outstanding_figure(register, client):
    _receipt("rc-1", "ra-out-1", 60000.0)
    html = client.get("/client/").get_data(as_text=True)
    assert "Outstanding" in html
    assert "40,000.00" in html


def test_an_overpaid_client_is_labelled_in_credit_rather_than_shown_negative(
        register, client):
    _receipt("rc-1", "ra-out-1", 130000.0)
    html = client.get("/client/").get_data(as_text=True)
    assert "in credit" in html
    assert "-30,000.00" not in html, "the sign is carried by the word, not a minus"
    assert "30,000.00" in html


def test_the_page_no_longer_presents_outstanding_without_a_caveat(register, client):
    """
    CC-2's A4 note: *"do not quietly present the figure as authoritative"*.
    PROGRESS.md §6-D recorded that the page did exactly that. This is the
    assertion that stops it happening again.
    """
    html = client.get("/client/").get_data(as_text=True)
    assert "internal" in html.lower()
    assert "no credit note" in html.lower()
    assert "cl-caveat" in html


def test_the_caveat_is_there_even_when_nothing_has_been_written_off(register, client):
    """
    It is a statement about what the figure *is*, not a footnote on one
    client's arithmetic. A caveat that appears only once something has gone
    unusual is a caveat nobody reads at the moment it matters.
    """
    html = client.get("/client/").get_data(as_text=True)
    assert "cl-caveat" in html
    assert "Written off" not in html, "no write-off here, so no stat"
