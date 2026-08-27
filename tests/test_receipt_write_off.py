"""
The write-off / adjustment field on a payment — CLIENT_CHANGES-2.md **A5**.

Built under the **27 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md` §0.

### The problem A5 solves, in the client's own figures

The main contractor allows a bill short: we bill ₹1,00,000, he allows ₹90,000.
The bill still says ₹1,00,000 and the receipts say ₹90,000, so ₹10,000 sits in
Outstanding forever. The write-off is what clears it.

### Why it is a SECOND figure and not part of the amount

This is the load-bearing design decision and most of this file exists to pin
it. Before A5 the only way to clear a short allowance was a second receipt with
`mode="adjustment"` — which does reduce Outstanding, but `client.received_val`
sums receipt **amounts** without inspecting mode, so the register's *Received*
column was inflated by every write-off (PROGRESS.md §6-D). Money that arrived
and money the contractor allowed short are two different facts, and they are
now two figures:

    outstanding = billed − received − written_off
    received    = sum(amount)          ← unchanged, and now correct

**The old defect is NOT fixed by A5 and is asserted here as still present.**
`received_val` still sums every receipt regardless of mode, so an
adjustment-mode receipt already in the database still inflates Received. What
happens to those records is a question about live data, not about code, and it
stays open. `test_an_adjustment_mode_receipt_still_inflates_received` is
deliberately written to **pass on the defective behaviour** — it is a tripwire,
so that whoever fixes it has to come here and say so.

### What A5 is not

Not a GST credit note. No document, no number series, nothing that leaves the
office. CC-2 A5 says so explicitly and the formal credit note is quoted
separately.
"""

import pytest

import client as CL
import ra as RA
from store import STORE


# ── Fixtures: one issued bill of ₹1,00,000 ─────────────────────────────────

@pytest.fixture()
def bill(client):
    """One issued RA bill worth exactly ₹1,00,000, and nothing paid on it."""
    STORE["receipts"].clear()
    STORE["ra_bills"].clear()
    b = {
        "id": "ra-writeoff-1", "ra_no": 1, "ref": "SF/RA/26-27/0001",
        "leg": "supply", "boq_id": "boq-wo", "boq_ref": "BOQ-WO",
        "project_name": "Whitefield tower", "account_name": "Prestige Estates",
        "date": "2026-08-01", "status": "issued",
        "grand_total": 100000.0,
    }
    STORE["ra_bills"]["ra-writeoff-1"] = b
    return b


def _record(client, *, amount, write_off="", ra="ra-writeoff-1"):
    return client.post(f"/receipt/new?ra={ra}", data={
        "date": "2026-08-20", "amount": amount, "mode": "neft",
        "instrument_ref": "UTR90001", "instrument_date": "2026-08-20",
        "notes": "", "write_off": write_off,
    })


def _only_receipt():
    assert len(STORE["receipts"]) == 1
    return list(STORE["receipts"].values())[0]


# ── The arithmetic ─────────────────────────────────────────────────────────

def test_the_clients_own_example_end_to_end(client, bill):
    """
    Billed ₹1,00,000, allowed ₹90,000, ₹10,000 written off.

    Outstanding goes to zero. Received stays at ₹90,000 — the ₹10,000 is not
    money that arrived and must never be counted as though it were.
    """
    assert _record(client, amount="90000", write_off="10000").status_code == 302

    assert RA.received_against("ra-writeoff-1") == 90000.0
    assert RA.written_off_against("ra-writeoff-1") == 10000.0
    assert RA.outstanding_of(bill) == 0.0


def test_without_the_write_off_the_ten_thousand_sits_there_forever(client, bill):
    """The state of the world before A5, stated so the fix has something to be a fix of."""
    assert _record(client, amount="90000").status_code == 302
    assert RA.received_against("ra-writeoff-1") == 90000.0
    assert RA.written_off_against("ra-writeoff-1") == 0.0
    assert RA.outstanding_of(bill) == 10000.0


def test_a_receipt_written_before_a5_existed_reads_as_no_write_off(client, bill):
    """
    No backfill. A record with no `write_off` key at all is not a broken record
    — it is every receipt in the database on 26 August 2026.
    """
    STORE["receipts"]["old-1"] = {
        "id": "old-1", "ref": "SF/RC/26-27/0001", "date": "2026-08-02",
        "ra_id": "ra-writeoff-1", "ra_no": 1, "boq_id": "boq-wo",
        "amount": 90000.0, "mode": "neft",
    }
    assert "write_off" not in STORE["receipts"]["old-1"]
    assert RA.written_off_against("ra-writeoff-1") == 0.0
    assert RA.outstanding_of(bill) == 10000.0


def test_write_offs_across_several_receipts_add_up(client, bill):
    assert _record(client, amount="50000", write_off="2000").status_code == 302
    assert _record(client, amount="40000", write_off="8000").status_code == 302
    assert RA.received_against("ra-writeoff-1") == 90000.0
    assert RA.written_off_against("ra-writeoff-1") == 10000.0
    assert RA.outstanding_of(bill) == 0.0


def test_a_cancelled_bill_is_still_outstanding_nothing(client, bill):
    """
    The existing rule wins over the new arithmetic: a withdrawn bill owes
    nothing, so nothing is owed on it whatever was written off.
    """
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    bill["status"] = "cancelled"
    assert RA.outstanding_of(bill) == 0.0


# ── Validation ─────────────────────────────────────────────────────────────

def test_a_blank_write_off_is_zero_and_is_the_ordinary_case(client, bill):
    assert _record(client, amount="90000", write_off="").status_code == 302
    assert _only_receipt()["write_off"] == 0.0


def test_a_negative_write_off_is_refused_and_nothing_is_written(client, bill):
    r = _record(client, amount="90000", write_off="-500")
    assert r.status_code == 200, "a rejected form re-renders"
    assert "cannot be negative" in r.get_data(as_text=True)
    assert STORE["receipts"] == {}


def test_the_amount_still_has_to_be_money_that_arrived(client, bill):
    """
    A5 is a field **on a payment**, which is how CC-2 words it. It does not
    relax the existing rule that a receipt records money that arrived, and this
    pins that no part of the write-off work weakened it.
    """
    r = _record(client, amount="0", write_off="10000")
    assert r.status_code == 200
    assert "has to be more than zero" in r.get_data(as_text=True)
    assert STORE["receipts"] == {}


def test_a_write_off_past_the_balance_warns_and_is_still_recorded(client, bill):
    """
    Warn, never block — DOMAIN.md §6, and the same treatment `_overpay_note()`
    already gives an overpayment. The ledger has to be able to record what
    actually happened.
    """
    r = _record(client, amount="90000", write_off="30000")
    assert r.status_code == 302
    assert "receipts and write-offs" in r.headers["Location"].replace("+", " ") \
        or "more than was claimed" in r.headers["Location"].replace("+", " ")
    assert _only_receipt()["write_off"] == 30000.0
    assert RA.outstanding_of(bill) == -20000.0, "not clamped, exactly as an overpayment is not"


# ── Editing ────────────────────────────────────────────────────────────────

def test_a_write_off_can_be_added_to_a_payment_recorded_earlier(client, bill):
    """
    The ordinary sequence: the ₹90,000 came in last month, the short allowance
    is agreed today. The receipt is edited rather than a second one invented.
    """
    assert _record(client, amount="90000").status_code == 302
    rid = list(STORE["receipts"])[0]
    assert RA.outstanding_of(bill) == 10000.0

    r = client.post(f"/receipt/edit/{rid}", data={
        "date": "2026-08-20", "amount": "90000", "mode": "neft",
        "instrument_ref": "UTR90001", "instrument_date": "2026-08-20",
        "notes": "allowed short, agreed with Mr Bankar", "write_off": "10000",
    })
    assert r.status_code == 302
    assert STORE["receipts"][rid]["write_off"] == 10000.0
    assert RA.outstanding_of(bill) == 0.0


def test_a_write_off_can_be_taken_back_off(client, bill):
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    rid = list(STORE["receipts"])[0]
    r = client.post(f"/receipt/edit/{rid}", data={
        "date": "2026-08-20", "amount": "90000", "mode": "neft",
        "instrument_ref": "", "instrument_date": "", "notes": "",
        "write_off": "",
    })
    assert r.status_code == 302
    assert STORE["receipts"][rid]["write_off"] == 0.0
    assert RA.outstanding_of(bill) == 10000.0


def test_the_edit_form_shows_the_stored_write_off(client, bill):
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    rid = list(STORE["receipts"])[0]
    html = client.get(f"/receipt/edit/{rid}").get_data(as_text=True)
    assert 'name="write_off"' in html
    assert 'value="10000"' in html


# ── Where it shows ─────────────────────────────────────────────────────────

def test_the_form_says_in_words_that_this_is_not_a_credit_note(client, bill):
    """
    CC-2 A5 is explicit that this is not a GST credit note, and the person
    typing into the box is the person who needs to know.
    """
    html = client.get("/receipt/new?ra=ra-writeoff-1").get_data(as_text=True)
    assert 'name="write_off"' in html
    assert "not a credit note" in html.lower()
    assert "Outstanding" in html and "Received" in html


def test_the_bill_page_shows_the_write_off_beside_the_receipt(client, bill):
    """
    A figure that moves Outstanding and appears nowhere is worse than no figure
    at all — the balance drops and nothing on the page says why.
    """
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    html = client.get("/ra/view/ra-writeoff-1").get_data(as_text=True)
    assert "Written off" in html
    assert "10,000.00" in html


def test_the_receipts_ledger_carries_a_written_off_column(client, bill):
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    html = client.get("/receipt/").get_data(as_text=True)
    assert "Written off" in html
    assert "10,000.00" in html


def test_an_ordinary_receipt_shows_a_dash_not_a_zero(client, bill):
    assert _record(client, amount="90000").status_code == 302
    html = client.get("/receipt/").get_data(as_text=True)
    assert "Written off" in html, "the column is always there"
    assert ">0.00<" not in html.split("Written off", 1)[1][:600]


# ── The client register — A4's Total Outstanding ───────────────────────────

def _register_group(client, bill):
    STORE["boqs"]["boq-wo"] = {
        "id": "boq-wo", "ref": "BOQ-WO", "date": "2026-07-01",
        "account_name": "Prestige Estates", "project_name": "Whitefield tower",
        "site_location": "Whitefield", "subtotal": 100000.0,
    }
    groups, _dupes = CL._client_groups()
    assert len(groups) == 1
    return list(groups.values())[0]


def test_the_register_takes_the_write_off_off_outstanding(client, bill):
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    grp = _register_group(client, bill)
    assert grp["total_issued"] == 100000.0
    assert grp["total_received"] == 90000.0
    assert grp["total_written_off"] == 10000.0
    assert grp["total_outstanding"] == 0.0


def test_the_register_keeps_the_write_off_out_of_received(client, bill):
    """
    **The whole reason A5 is a separate field.** If this figure were 1,00,000
    the register would be claiming the contractor paid in full.
    """
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    grp = _register_group(client, bill)
    assert grp["total_received"] == 90000.0
    assert grp["total_received"] != 100000.0


def test_the_register_shows_the_written_off_figure_when_there_is_one(client, bill):
    assert _record(client, amount="90000", write_off="10000").status_code == 302
    _register_group(client, bill)
    html = client.get("/client/").get_data(as_text=True)
    assert "Written off" in html
    assert "10,000.00" in html


def test_a_client_with_no_write_offs_sees_the_three_figures_it_always_did(client, bill):
    assert _record(client, amount="90000").status_code == 302
    _register_group(client, bill)
    html = client.get("/client/").get_data(as_text=True)
    assert "Written off" not in html
    assert "Outstanding" in html


# ── The defect A5 does NOT fix ─────────────────────────────────────────────

def test_an_adjustment_mode_receipt_still_inflates_received(client, bill):
    """
    ⚠ **A TRIPWIRE, not an endorsement.** This asserts the *defective* current
    behaviour on purpose.

    `client.received_val` sums every receipt regardless of mode, so the
    pre-A5 workaround — a second receipt with `mode="adjustment"` — still makes
    Outstanding right by making Received wrong. A5 makes that workaround
    unnecessary for **new** entries; it does nothing about records already in
    the database, and what to do with those is a question about live data
    rather than about code (PROGRESS.md §6-D).

    When somebody fixes it, this test fails, and they have to come here and
    record the decision rather than discovering the change downstream.
    """
    assert _record(client, amount="90000").status_code == 302
    r = client.post("/receipt/new?ra=ra-writeoff-1", data={
        "date": "2026-08-21", "amount": "10000", "mode": "adjustment",
        "instrument_ref": "", "instrument_date": "", "notes": "short allowed",
        "write_off": "",
    })
    assert r.status_code == 302

    grp = _register_group(client, bill)
    assert grp["total_outstanding"] == 0.0, "Outstanding is right..."
    assert grp["total_received"] == 100000.0, \
        "...and Received is wrong, by the whole adjustment. Still open."
    assert grp["total_written_off"] == 0.0, \
        "an adjustment-mode receipt is not a write-off and is not counted as one"
