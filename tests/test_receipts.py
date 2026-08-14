"""
CLIENT_CHANGES.md item 8 — the receipts ledger.

Recording money RECEIVED against an RA bill, and carrying what is still unpaid
onto the next bill of the same BOQ chain as a previous-balance memo.

Four properties everything here circles, each of which exists because of a
defect this project has already shipped or a ceiling it has already hit:

- **The snapshot is the whole feature.** The previous balance printed on a bill
  is frozen onto that bill when it is raised and is never recomputed from live
  receipts. `print_ra()` was once a loop over the live BOQ and silently rewrote
  documents already sent; a balance recomputed at print time is the same bug
  with a different source. The strongest test here renders a bill, moves the
  receipts underneath it, and asserts the page is **byte-identical**.

- **Receipts are their own collection.** Never a list on the bill, never a list
  on the BOQ — `boq.MAX_JSON_BYTES` is what that rule protects.

- **The carried balance is a MEMO, not a claim.** It is absent from
  `claim_subtotal`, from every tax figure, from `net_payable` and from
  `grand_total`, and it is invisible to the over-claim guard.
  ⚠ That last one rests on an **assumption the client has not confirmed** —
  that arrears are not re-billed as line items. See the test that pins it.

- **It follows the revision CHAIN, not the record.** A receipt against a bill
  raised on revision 0 still counts once revision 1 is live. Anything summing
  against one BOQ record resets the balance to zero on every revision, which is
  the trap `claimed_by_line()` already exists to avoid.
"""

import json

import pytest

import boq as BQ
import demo_data as DD
import ra
import receipt as RC
from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(client):
    """The real 97-line Sify BOQ, seeded through the app."""
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()


def priced(boq_id, n=None):
    lines = [li for li in STORE["boqs"][boq_id]["line_items"]
             if not li["is_header"] and li["total_qty"] > 0]
    return lines[:n] if n else lines


def big_line(boq_id, need=20.0):
    """
    A priced line with room for several claims on it.

    Not `priced(boq_id)[0]` — the real schedule's first two priced lines are
    approved at 4 and 12 units, so two 5-unit claims against them over-claim
    and the block refuses the second bill. The block is hard and has no
    override, which is correct; the fixture is what has to give.
    """
    return next(li for li in priced(boq_id)
                if li["total_qty"] >= need and li["supply_rate"] > 0)


def claim_for(li, qty, rate=None, prev=0.0):
    r = li["supply_rate"] if rate is None else rate
    return ra.build_claim(li, qty, r, prev, li["supply_rate"])


def make_bill(boq_id, ra_no, leg="supply", claims=None, boq_ref="SF/BOQ/26-27/0001",
              **over):
    """
    A bill written straight into the store, with its tax block computed the way
    `create_ra()` computes it — so `grand_total` is a real figure and the
    balance arithmetic has something honest to work against.
    """
    rid = f"r{ra_no}-{leg}"
    info = ra.compute_tax_totals(claims or [], [])
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-06", "boq_id": boq_id, "boq_ref": boq_ref,
        "boq_rev_no": 0, "ra_no": ra_no, "leg": leg, "claims": claims or [],
        "claim_subtotal": info["claim_subtotal"], "deductions": info["deductions"],
        "deduction_total": info["deduction_total"],
        "net_payable": info["net_payable"], "tax_type": info["tax_type"],
        "cgst_rate": info["cgst_rate"], "sgst_rate": info["sgst_rate"],
        "igst_rate": info["igst_rate"], "cgst_amount": info["cgst_amount"],
        "sgst_amount": info["sgst_amount"], "igst_amount": info["igst_amount"],
        "tax_amount": info["tax_amount"], "tax_slabs": info["tax_slabs"],
        "rounding_off": info["rounding_off"], "grand_total": info["grand_total"],
        "status": "draft", "certified_on": "", "notes": "",
    }
    STORE["ra_bills"][rid].update(over)
    return rid


def make_receipt(ra_id, amount, rcid=None, date="2026-08-10", **over):
    bill = STORE["ra_bills"][ra_id]
    rcid = rcid or f"rc-{ra_id}-{len(STORE['receipts'])}"
    STORE["receipts"][rcid] = {
        "id": rcid, "ref": f"SF/RCPT/26-27/{len(STORE['receipts']) + 1:04d}",
        "fy": "26-27", "date": date, "ra_id": ra_id,
        "ra_ref": bill.get("ref"), "ra_no": bill.get("ra_no"),
        "leg": bill.get("leg"), "boq_id": bill.get("boq_id"),
        "boq_ref": bill.get("boq_ref"), "project_name": "Sify",
        "account_name": "Test Contractor", "amount": float(amount),
        "mode": "neft", "instrument_ref": "UTR1", "instrument_date": date,
        "notes": "",
    }
    STORE["receipts"][rcid].update(over)
    return rcid


# ═══════════════════════════════════════════════════════════════════════════
# THE COLLECTION — its own, never embedded
# ═══════════════════════════════════════════════════════════════════════════

def test_receipts_are_their_own_persisted_collection():
    """
    CLIENT_CHANGES.md §1.3. Embedding these on the BOQ eats the headroom under
    `boq.MAX_JSON_BYTES`, which the client's real data shape already reaches at
    ~428 lines — and pushes the failure into the schedule editor, where the
    operator loses work unrelated to the thing that grew. `ra_bills` was split
    out for exactly this reason.
    """
    import db

    assert "receipts" in STORE
    assert "receipts" in db.COLLECTIONS


def test_a_receipt_is_not_stored_on_the_bill_or_the_boq(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    make_receipt(rid, 500.0)

    bill = STORE["ra_bills"][rid]
    boq = STORE["boqs"][seeded]
    assert not any("receipt" in k for k in bill), \
        "a receipt leaked onto the RA bill record"
    assert not any("receipt" in k for k in boq), \
        "a receipt leaked onto the BOQ record"
    assert len(STORE["receipts"]) == 1


def test_the_blueprint_is_registered(client):
    import app as app_module
    assert "receipt" in app_module.app.blueprints
    rules = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    for endpoint in ("receipt.list_receipts", "receipt.new_receipt",
                     "receipt.edit_receipt", "receipt.delete_receipt"):
        assert endpoint in rules


def test_ra_view_renders_when_a_receipt_exists(client, seeded):
    """
    The `/boq/view` 500 again, one link further down. `ra.view_ra()` builds
    `url_for("receipt.new_receipt")` on every bill, so an unregistered
    blueprint is a BuildError and a 500 — and it would only show up once a bill
    existed. This fails with a 500 if the blueprint is ever unregistered.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    make_receipt(rid, 500.0)

    r = client.get(f"/ra/view/{rid}")
    assert r.status_code == 200
    assert "/receipt/new" in r.get_data(as_text=True)


# ═══════════════════════════════════════════════════════════════════════════
# A PARTIAL PAYMENT LEAVES THE RIGHT BALANCE
# ═══════════════════════════════════════════════════════════════════════════

def test_a_partial_payment_leaves_the_right_balance(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    gross = STORE["ra_bills"][rid]["grand_total"]
    assert gross > 0

    make_receipt(rid, 1000.0)

    assert ra.received_against(rid) == 1000.0
    assert ra.outstanding_of(STORE["ra_bills"][rid]) == round(gross - 1000.0, 2)


def test_several_partial_payments_sum(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    gross = STORE["ra_bills"][rid]["grand_total"]

    make_receipt(rid, 1000.0)
    make_receipt(rid, 2500.50)

    assert ra.received_against(rid) == 3500.50
    assert ra.outstanding_of(STORE["ra_bills"][rid]) == round(gross - 3500.50, 2)


def test_a_bill_paid_in_full_carries_nothing_forward(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    gross = STORE["ra_bills"][rid]["grand_total"]

    make_receipt(rid, gross)

    assert ra.outstanding_of(STORE["ra_bills"][rid]) == 0.0
    balance, refs = ra.previous_balance(seeded, before_ra_no=2)
    assert balance == 0.0
    assert refs == [], "a settled bill should not be named as carrying a balance"


def test_an_overpayment_carries_forward_as_a_credit_and_is_not_clamped(client, seeded):
    """
    Signed, deliberately. Clamping a negative outstanding at zero would state
    that money we are holding is not money we are holding — the same silent
    correction DOMAIN.md §6 forbids, and the inverse of the under-reporting the
    "uncertified is not zero" rule avoids.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    gross = STORE["ra_bills"][rid]["grand_total"]

    make_receipt(rid, gross + 5000.0)

    assert ra.outstanding_of(STORE["ra_bills"][rid]) == -5000.0
    balance, _refs = ra.previous_balance(seeded, before_ra_no=2)
    assert balance == -5000.0


def test_a_bill_with_no_receipts_is_outstanding_in_full(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    assert ra.received_against(rid) == 0.0
    assert ra.outstanding_of(STORE["ra_bills"][rid]) == \
        STORE["ra_bills"][rid]["grand_total"]


# ═══════════════════════════════════════════════════════════════════════════
# THE SNAPSHOT — the reason this feature has a design at all
# ═══════════════════════════════════════════════════════════════════════════

def test_creating_a_bill_freezes_the_previous_balance(client, seeded):
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    gross1 = STORE["ra_bills"][rid1]["grand_total"]
    make_receipt(rid1, 1000.0)
    expected = round(gross1 - 1000.0, 2)

    lid = li["line_id"]
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-09-01",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "5", "rate": str(li["supply_rate"])}]}),
    })
    assert r.status_code == 302, r.get_data(as_text=True)[:2000]

    bill2 = next(b for b in STORE["ra_bills"].values() if b["ra_no"] == 2)
    assert bill2["prev_balance"] == expected
    assert bill2["prev_balance_refs"] == [STORE["ra_bills"][rid1]["ref"]]


def test_editing_an_earlier_receipt_does_not_move_a_later_bills_snapshot(client, seeded):
    """
    **The requirement, stated as a test.** RA2 said what it said on the day it
    was raised. Correcting a receipt against RA1 in October must not rewrite a
    figure printed on a document the main contractor already holds.
    """
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    gross1 = STORE["ra_bills"][rid1]["grand_total"]
    rcid = make_receipt(rid1, 1000.0)

    lid = li["line_id"]
    client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-09-01",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "5", "rate": str(li["supply_rate"])}]}),
    })
    bill2 = next(b for b in STORE["ra_bills"].values() if b["ra_no"] == 2)
    frozen = bill2["prev_balance"]
    assert frozen == round(gross1 - 1000.0, 2)

    # The receipt is corrected — a transposed figure, caught a month later.
    r = client.post(f"/receipt/edit/{rcid}", data={
        "date": "2026-08-10", "amount": "9000", "mode": "neft",
        "instrument_ref": "UTR1", "instrument_date": "2026-08-10", "notes": ""})
    assert r.status_code == 302
    assert STORE["receipts"][rcid]["amount"] == 9000.0

    assert bill2["prev_balance"] == frozen, \
        "correcting a receipt rewrote a figure already printed on RA2"

    # And the divergence is surfaced rather than hidden.
    stored, live, drifted = ra.prev_balance_drift(bill2)
    assert stored == frozen
    assert live == round(gross1 - 9000.0, 2)
    assert drifted is True


def test_deleting_a_receipt_does_not_move_a_later_bills_snapshot(client, seeded):
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    gross1 = STORE["ra_bills"][rid1]["grand_total"]
    rcid = make_receipt(rid1, 1000.0)

    rid2 = make_bill(seeded, 2, claims=[claim_for(li, 5.0, prev=5.0)],
                     prev_balance=round(gross1 - 1000.0, 2),
                     prev_balance_refs=["SF/RA/26-27/0001"])
    frozen = STORE["ra_bills"][rid2]["prev_balance"]

    r = client.post(f"/receipt/delete/{rcid}")
    assert r.status_code == 302
    assert rcid not in STORE["receipts"]

    assert STORE["ra_bills"][rid2]["prev_balance"] == frozen
    stored, live, drifted = ra.prev_balance_drift(STORE["ra_bills"][rid2])
    assert stored == frozen
    assert live == gross1, "the whole bill is outstanding again once the receipt is gone"
    assert drifted is True


def test_the_printed_bill_is_byte_identical_across_receipt_changes(client, seeded):
    """
    **The strongest form of the rule.** Not "the number is still stored" but
    "the rendered document has not changed by a single byte" — the same shape
    `test_ra_print_immutability.py` uses for a revised BOQ, applied to the
    thing this feature adds. If any renderer ever reaches for
    `STORE["receipts"]`, this fails.
    """
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    gross1 = STORE["ra_bills"][rid1]["grand_total"]
    rcid = make_receipt(rid1, 1000.0)

    rid2 = make_bill(seeded, 2, claims=[claim_for(li, 5.0, prev=5.0)],
                     prev_balance=round(gross1 - 1000.0, 2),
                     prev_balance_refs=["SF/RA/26-27/0001"])

    before = client.get(f"/ra/print/{rid2}").get_data(as_text=True)
    assert "Previous Balance Outstanding" in before, \
        "the memo did not render at all — this test would prove nothing"

    make_receipt(rid1, 250.0)                        # a payment arrives
    STORE["receipts"][rcid]["amount"] = 4321.0       # an earlier one is corrected
    after_change = client.get(f"/ra/print/{rid2}").get_data(as_text=True)
    assert after_change == before

    STORE["receipts"].pop(rcid)                      # and one is removed
    after_delete = client.get(f"/ra/print/{rid2}").get_data(as_text=True)
    assert after_delete == before


def test_editing_a_bills_claim_does_not_recompute_its_carried_balance(client, seeded):
    """
    `edit_ra()` rewrites the claim and the whole tax block. It must not touch
    `prev_balance`: that is a statement about OTHER bills, and this bill may
    already have been printed.
    """
    li = big_line(seeded)
    make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    rid2 = make_bill(seeded, 2, claims=[claim_for(li, 5.0, prev=5.0)],
                     prev_balance=777.0, prev_balance_refs=["SF/RA/26-27/0001"])

    r = client.post(f"/ra/edit/{rid2}", data={
        "date": "2026-09-02",
        "ra_json": json.dumps({"lines": [
            {"line_id": li["line_id"], "qty": "7", "rate": str(li["supply_rate"])}]}),
    })
    assert r.status_code == 302, r.get_data(as_text=True)[:2000]

    bill2 = STORE["ra_bills"][rid2]
    assert bill2["prev_balance"] == 777.0
    assert bill2["claims"][0]["qty"] == 7.0, "the claim edit itself did not apply"


def test_a_bill_written_before_the_field_prints_no_memo_and_reports_no_drift(client, seeded):
    """
    The `tax_slabs` contract, applied again: a new field defaults cleanly rather
    than forcing a migration. A bill with no `prev_balance` key never made the
    statement, so it prints nothing — not a zero — and has nothing that could
    have drifted.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    STORE["ra_bills"][rid].pop("prev_balance", None)
    STORE["ra_bills"][rid].pop("prev_balance_refs", None)

    body = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "Previous Balance Outstanding" not in body
    assert "Total Due" not in body

    assert ra.prev_balance_drift(STORE["ra_bills"][rid]) == (0.0, 0.0, False)


def test_a_nil_carried_balance_prints_no_memo(client, seeded):
    """RA1 has no earlier bill. A memo saying "Previous Balance: 0.00" on it is
    noise, not information."""
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)],
                    prev_balance=0.0, prev_balance_refs=[])
    body = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "Previous Balance Outstanding" not in body


# ═══════════════════════════════════════════════════════════════════════════
# THE CARRIED BALANCE IS A MEMO, NOT A CLAIM
# ═══════════════════════════════════════════════════════════════════════════

def test_the_carried_balance_is_not_billed_taxed_or_claimed(client, seeded):
    """
    ⚠ **This pins an ASSUMPTION, not a confirmed requirement.** The client has
    not confirmed that unpaid amounts are carried as a memo rather than
    re-billed as line items on the next RA — CLIENT_CHANGES.md item 8 and §3
    carry the open question, and this test is where the answer would land.

    What the assumption buys: an arrear that entered `claim_subtotal` would be
    taxed a second time on a value already taxed once, and would inflate the
    cumulative claim against the approved schedule until the over-claim block
    refused a bill for the wrong reason.
    """
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    make_receipt(rid1, 1.0)                        # a token payment, big arrear

    lid = li["line_id"]
    client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-09-01",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "5", "rate": str(li["supply_rate"])}]}),
    })
    bill2 = next(b for b in STORE["ra_bills"].values() if b["ra_no"] == 2)

    assert bill2["prev_balance"] > 0, "the fixture did not produce an arrear"

    # A bill claiming the same lines with no arrear behind it must total the
    # same. The memo touches nothing that is billed.
    control = ra.compute_tax_totals(bill2["claims"], [])
    assert bill2["claim_subtotal"] == control["claim_subtotal"]
    assert bill2["net_payable"] == control["net_payable"]
    assert bill2["tax_amount"] == control["tax_amount"]
    assert bill2["grand_total"] == control["grand_total"]

    # And no claim row was invented for it.
    assert len(bill2["claims"]) == 1
    assert all(c["line_id"] == lid for c in bill2["claims"])


def test_the_carried_balance_is_invisible_to_the_overclaim_guard(client, seeded):
    """
    The guard is on QUANTITY. An arrear is money, carries no line and no
    quantity, and must not be able to trip it — which is only true while it
    stays out of `claims`.
    """
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, li["total_qty"])])
    make_receipt(rid1, 1.0)

    before = ra.claimed_by_line(seeded)
    make_receipt(rid1, 5.0)
    assert ra.claimed_by_line(seeded) == before, \
        "a receipt changed the claimed-quantity map"


def test_the_memo_states_it_is_not_re_claimed(client, seeded):
    """The document has to say so on its face — INTRODUCTION.md §2: a rule this
    system enforces states its reason on the page, in words."""
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)],
                    prev_balance=12345.0, prev_balance_refs=["SF/RA/26-27/0001"])
    body = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "Previous Balance Outstanding" in body
    assert "re-claimed as a line item on this bill" in body
    assert "no GST is charged on it here" in body


# ═══════════════════════════════════════════════════════════════════════════
# THE REVISION CHAIN — a receipt survives its BOQ being superseded
# ═══════════════════════════════════════════════════════════════════════════

def _revise(boq_id: str, new_id: str = "boq-rev1") -> str:
    """A revision: a NEW record carrying `supersedes`, never an edit."""
    original = STORE["boqs"][boq_id]
    rev = dict(original)
    rev["id"] = new_id
    rev["ref"] = "SF/BOQ/26-27/0001"
    rev["rev_no"] = 1
    rev["supersedes"] = boq_id
    rev["line_items"] = [dict(li) for li in original["line_items"]]
    STORE["boqs"][new_id] = rev
    return new_id


def test_a_receipt_against_a_superseded_revision_still_counts(client, seeded):
    """
    **The decision, pinned.** A receipt is keyed to a BILL, and a bill is keyed
    to a specific BOQ revision. Superseding that revision changes what is
    approved; it changes nothing about money that has already been received.

    So `previous_balance()` walks the whole chain, exactly as
    `claimed_by_line()` does. Summing against a single BOQ record instead would
    reset the carried balance to zero on every revision and understate what the
    client owes — silently, and only on projects that have been revised.
    """
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    gross1 = STORE["ra_bills"][rid1]["grand_total"]
    make_receipt(rid1, 1000.0)

    rev = _revise(seeded)
    assert ra.latest_revision(seeded) == rev

    # RA2 is raised against the REVISION; RA1 lives on the superseded record.
    balance, refs = ra.previous_balance(rev, before_ra_no=2)
    assert balance == round(gross1 - 1000.0, 2), \
        "the revision reset the carried balance to zero"
    assert refs == [STORE["ra_bills"][rid1]["ref"]]


def test_the_ledger_for_a_project_spans_the_whole_chain(client, seeded):
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    make_receipt(rid1, 1000.0)

    rev = _revise(seeded)
    rid2 = make_bill(rev, 2, claims=[claim_for(li, 5.0, prev=5.0)])
    make_receipt(rid2, 2000.0)

    rows = RC.receipts_of_boq(rev)
    assert len(rows) == 2
    assert round(sum(float(r["amount"]) for _rid, r in rows), 2) == 3000.0

    # And from the old record too — the chain is walked from either end.
    assert len(RC.receipts_of_boq(seeded)) == 2


def test_a_bill_raised_on_a_revision_snapshots_the_chains_balance(client, seeded):
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    gross1 = STORE["ra_bills"][rid1]["grand_total"]
    make_receipt(rid1, 1000.0)

    rev = _revise(seeded)
    lid = li["line_id"]
    r = client.post(f"/ra/create?boq={rev}&leg=supply", data={
        "date": "2026-09-01",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "5", "rate": str(li["supply_rate"])}]}),
    })
    assert r.status_code == 302, r.get_data(as_text=True)[:2000]

    bill2 = next(b for b in STORE["ra_bills"].values() if b["ra_no"] == 2)
    assert bill2["boq_id"] == rev
    assert bill2["prev_balance"] == round(gross1 - 1000.0, 2)


# ═══════════════════════════════════════════════════════════════════════════
# DESTRUCTION — POST only, and its own GET test
# ═══════════════════════════════════════════════════════════════════════════

def test_get_on_receipt_delete_destroys_nothing(client, seeded):
    """
    ABOUT.md §7.9f's standing rule, and this route's own copy of it.

    `test_no_registered_route_destroys_on_get` walks the url_map and asserts a
    delete route **accepts POST**. That catches a GET-only delete route, but it
    cannot catch one that accepts both and still destroys on GET — so every
    delete route brings a hand-written test that issues a real GET and asserts
    the store is unchanged. This is that test for `/receipt/delete`.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    rcid = make_receipt(rid, 1000.0)
    before = dict(STORE["receipts"])

    r = client.get(f"/receipt/delete/{rcid}")

    assert r.status_code == 200, "the GET should render a confirmation page"
    assert STORE["receipts"] == before, "a GET destroyed a receipt"
    assert rcid in STORE["receipts"]
    assert "cannot be undone" in r.get_data(as_text=True)


def test_post_on_receipt_delete_removes_it(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    rcid = make_receipt(rid, 1000.0)

    r = client.post(f"/receipt/delete/{rcid}")
    assert r.status_code == 302
    assert rcid not in STORE["receipts"]


def test_the_delete_confirmation_names_the_bills_it_will_not_restate(client, seeded):
    """The consequence is stated before the operator confirms, not discovered
    afterwards — "reason shown, not the button hidden"."""
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    rcid = make_receipt(rid1, 1000.0)
    make_bill(seeded, 2, claims=[claim_for(li, 5.0, prev=5.0)],
              prev_balance=500.0, prev_balance_refs=["SF/RA/26-27/0001"])

    body = client.get(f"/receipt/delete/{rcid}").get_data(as_text=True)
    assert "RA2" in body
    assert "will" in body and "not" in body


def test_a_bill_with_receipts_cannot_be_deleted(client, seeded):
    """
    Deleting the bill would orphan the payment: the money stays in the ledger
    pointing at a document that no longer exists, and silently stops counting
    toward the balance carried onto the next bill.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    make_receipt(rid, 1000.0)

    allowed, why = ra.can_delete(STORE["ra_bills"][rid])
    assert allowed is False
    assert "receipt" in why.lower()

    r = client.post(f"/ra/delete/{rid}")
    assert r.status_code == 302
    assert rid in STORE["ra_bills"], "a bill with money against it was deleted"


def test_a_bill_becomes_deletable_once_its_receipts_are_gone(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    rcid = make_receipt(rid, 1000.0)

    client.post(f"/receipt/delete/{rcid}")
    allowed, _why = ra.can_delete(STORE["ra_bills"][rid])
    assert allowed is True


# ═══════════════════════════════════════════════════════════════════════════
# THE FORM
# ═══════════════════════════════════════════════════════════════════════════

def test_recording_a_payment_through_the_form(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    gross = STORE["ra_bills"][rid]["grand_total"]

    r = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-20", "amount": "1,500.50", "mode": "cheque",
        "instrument_ref": "000123", "instrument_date": "2026-08-19",
        "notes": "part payment"})
    assert r.status_code == 302, r.get_data(as_text=True)[:2000]

    assert len(STORE["receipts"]) == 1
    rec = next(iter(STORE["receipts"].values()))
    assert rec["amount"] == 1500.50, "the Indian-format amount did not parse"
    assert rec["mode"] == "cheque"
    assert rec["ra_id"] == rid
    assert rec["ra_ref"] == STORE["ra_bills"][rid]["ref"]
    assert rec["boq_id"] == seeded
    assert rec["ref"].startswith("SF/RCPT/")
    assert ra.outstanding_of(STORE["ra_bills"][rid]) == round(gross - 1500.50, 2)


@pytest.mark.parametrize("amount", ["", "0", "-500", "abc"])
def test_a_receipt_of_nothing_is_refused(client, seeded, amount):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])

    r = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-20", "amount": amount, "mode": "neft",
        "instrument_ref": "", "instrument_date": "", "notes": ""})
    assert r.status_code == 200, "a rejected form should re-render, not redirect"
    assert STORE["receipts"] == {}
    assert "amount received" in r.get_data(as_text=True).lower()


def test_a_rejected_form_keeps_what_was_typed(client, seeded):
    """`address._validate()`'s contract — always return data, so the operator
    does not retype the form."""
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])

    body = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-20", "amount": "0", "mode": "cheque",
        "instrument_ref": "CHQ-9911", "instrument_date": "",
        "notes": "keep me"}).get_data(as_text=True)
    assert "CHQ-9911" in body
    assert "keep me" in body
    assert 'value="cheque" selected' in body


def test_an_unknown_mode_is_refused(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])

    r = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-20", "amount": "100", "mode": "barter",
        "instrument_ref": "", "instrument_date": "", "notes": ""})
    assert r.status_code == 200
    assert STORE["receipts"] == {}


def test_the_mode_picker_is_a_select_over_the_shared_list(client, seeded):
    """
    A select, not a free-text box — the ledger groups on this value and a typed
    "NEFT " with a trailing space is a second mode nobody can see. The list
    lives in `ra.py` so the form and the bill's own panel cannot disagree.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])

    body = client.get(f"/receipt/new?ra={rid}").get_data(as_text=True)
    assert '<select id="mode" name="mode">' in body
    for mode in ra.RECEIPT_MODES:
        assert f'value="{mode}"' in body


def test_an_overpayment_warns_and_is_still_recorded(client, seeded):
    """
    Warns, never blocks — a lump sum settling two bills at once is a real thing
    the client's main contractor does. Same treatment as a claim rate that
    diverges from the approved BOQ, and as a certification above what was
    claimed (DOMAIN.md §6).
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    gross = STORE["ra_bills"][rid]["grand_total"]

    r = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-20", "amount": str(gross + 1000), "mode": "neft",
        "instrument_ref": "", "instrument_date": "", "notes": ""})
    assert r.status_code == 302
    assert len(STORE["receipts"]) == 1, "the overpayment was blocked, not warned"
    assert "more than was claimed" in r.headers["Location"].replace("+", " ")


def test_new_receipt_without_a_bill_renders_a_picker(client, seeded):
    li = big_line(seeded)
    make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    body = client.get("/receipt/new").get_data(as_text=True)
    assert "Which bill was this paid against?" in body
    assert "RA1" in body


def test_the_receipt_number_is_max_plus_one_within_the_year(client, seeded):
    """
    Not len+1. A gap left by a deleted receipt must never re-issue a number
    already quoted on a remittance advice — `proforma._next_ref()`'s rule.
    """
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    make_receipt(rid, 100.0, rcid="a", date="2026-08-01")
    STORE["receipts"]["a"]["ref"] = "SF/RCPT/26-27/0007"

    assert RC.next_ref("2026-08-20").endswith("/0008")

    STORE["receipts"].pop("a")
    assert RC.next_ref("2026-08-20").endswith("/0001")


def test_editing_a_receipt_does_not_reissue_its_number(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    rcid = make_receipt(rid, 100.0)
    ref = STORE["receipts"][rcid]["ref"]

    client.post(f"/receipt/edit/{rcid}", data={
        "date": "2026-09-09", "amount": "250", "mode": "upi",
        "instrument_ref": "", "instrument_date": "", "notes": ""})

    assert STORE["receipts"][rcid]["ref"] == ref
    assert STORE["receipts"][rcid]["amount"] == 250.0
    assert STORE["receipts"][rcid]["fy"] == "26-27"


# ═══════════════════════════════════════════════════════════════════════════
# THE LEDGER PAGE
# ═══════════════════════════════════════════════════════════════════════════

def test_the_ledger_lists_receipts_and_totals_them(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    make_receipt(rid, 1000.0)
    make_receipt(rid, 250.0)

    body = client.get("/receipt/").get_data(as_text=True)
    assert body.count("SF/RCPT/") >= 2
    assert "1,250.00" in body


def test_the_project_ledger_shows_the_position_by_bill(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    make_receipt(rid, 1000.0)

    body = client.get(f"/receipt/?boq={seeded}").get_data(as_text=True)
    assert "Position by bill" in body
    assert "Outstanding" in body
    assert "RA1" in body


def test_the_bill_page_shows_receipts_and_the_live_outstanding(client, seeded):
    li = big_line(seeded)
    rid = make_bill(seeded, 1, claims=[claim_for(li, 10.0)])
    make_receipt(rid, 1000.0)

    body = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "Receipts against this bill" in body
    assert "Outstanding on this bill" in body
    assert "SF/RCPT/" in body


def test_the_bill_page_flags_a_drifted_snapshot(client, seeded):
    li = big_line(seeded)
    rid1 = make_bill(seeded, 1, claims=[claim_for(li, 5.0)])
    make_receipt(rid1, 1000.0)
    rid2 = make_bill(seeded, 2, claims=[claim_for(li, 5.0, prev=5.0)],
                     prev_balance=999999.0, prev_balance_refs=["SF/RA/26-27/0001"])

    body = client.get(f"/ra/view/{rid2}").get_data(as_text=True)
    assert "was issued stating a previous balance" in body
    assert "not restated" in body or "is not restated" in body


def test_no_page_here_reintroduces_render_template_string():
    """
    ABOUT.md §7.9d. A fully-interpolated string parsed a second time by Jinja
    executes any `{{ }}` that arrived in user input, and nothing in this module
    is passed as Jinja context — so the second parse is pure downside.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "receipt.py").read_text(
        encoding="utf8")
    # The CALL, not the word — the module's own comment explains why it is
    # absent, and a check that could not tell prose from a call site would
    # forbid documenting the rule.
    assert "render_template_string(" not in src
    assert "import render_template_string" not in src
