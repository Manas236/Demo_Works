"""
RA · SUPPLY & INSTALLATION IN ONE POST, AND THE PROOF DOCUMENT NO LONGER
REQUIRED — §0's **fifty-eighth** block, item 6.

The client's ask from the 28 October 2026 Yogesh meeting, in two halves:

**(a) Both, in one action.** *"RA especially all 3 types — Supply,
Installation, and then Supply and Installation both."* The first two were one
click already; Both meant raising a supply bill, issuing it, raising an
installation bill, issuing that, and only then opening `/merged/create` — five
steps and three screens for one job. `/raboth/create` does it in one POST.

**(b) The proof document is no longer a prerequisite.** CC-2 **C1**'s ordering
gate is switched off in code (`ra.C1_PREREQUISITE`), so a claim opens without
a delivery challan or a measurement sheet in front of it.

**The assertions that matter most:**

- `test_NOTHING_IS_WRITTEN_WHEN_EITHER_LEG_IS_OVER` — the block's own wording:
  *"if either leg fails the over-claim guard, nothing is written and the
  refusal names the line."* Both legs are validated **before the first record
  exists**.
- `test_NEITHER_LEG_CARRIES_A_TAX_INVOICE_NUMBER` — Rule 46 and GSTR-1 must
  not see three serials over one billing.
- `test_THE_MEASUREMENT_CAP_STILL_BINDS` and its partner — **only the
  prerequisite was relaxed.** With an approved sheet the installation claim is
  still capped at the MEASURED quantity; with none it is capped at the BOQ
  quantity, which is `ra.overclaims()`'s `measured == {}` path, unchanged by
  one character.
- `test_cancelling_the_merged_document_cancels_all_three` — three documents
  raised by one action are withdrawn by one action.

⚠ **`tests/test_c1_order_of_working.py` still proves the C1 gate**, under the
  `c1_prerequisite_on` fixture, for the day it is armed again. Nothing there
  was rewritten into an OFF check.
"""

import json
import re

import pytest

import approval
import boq as BQ
import demo_data as DD
import merged_ra as MRA
import ra as RA
import raboth as RB
from store import STORE


@pytest.fixture()
def sched(client):
    """The seeded schedule, with nothing in front of it and no bills."""
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()
    client.get("/boq/")
    client.get("/settings/")
    yield DD.BOQ_META["id"]
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()


def _form(client, bid) -> str:
    r = client.get(f"/raboth/create?boq={bid}")
    assert r.status_code == 200, f"the form did not open: {r.status_code}"
    return r.get_data(as_text=True)


def _boxes(html, leg):
    """`[(line_id, rate)]` for one leg's grid, in page order."""
    flat = " ".join(html.split())
    return re.findall(
        r'name="%s_qty_([0-9a-f]{12})"[^>]*?/>.*?name="%s_rate_\1" value="([^"]*)"'
        % (leg, leg), flat)


def _post(client, bid, supply=(), install=(), **over):
    html = _form(client, bid)
    data = {"boq": bid, "date": "2026-10-29"}
    for leg, want in (("supply", supply), ("installation", install)):
        rows = _boxes(html, leg)
        for i, qty in enumerate(want):
            lid, rate = rows[i]
            data[f"{leg}_qty_{lid}"] = str(qty)
            data[f"{leg}_rate_{lid}"] = rate
    data.update(over)
    return client.post(f"/raboth/create?boq={bid}", data=data,
                       follow_redirects=False)


def _bills():
    return sorted(STORE["ra_bills"].values(), key=lambda b: int(b.get("ra_no") or 0))


def _merged():
    assert len(STORE["merged_ras"]) == 1, STORE["merged_ras"]
    return next(iter(STORE["merged_ras"].values()))


def _approved(bid, leg):
    """`[(line_id, approved_qty)]` for lines priced on this leg."""
    app = RA.approved_by_line(bid)
    rates = RA.approved_rates(bid)
    return [(lid, q) for (lid, lg), q in app.items()
            if lg == leg and rates.get((lid, lg)) is not None]


# =============================================================================
# (a) ONE POST, THREE DOCUMENTS
# =============================================================================

def test_one_post_raises_both_legs_and_the_merged_invoice(client, sched):
    r = _post(client, sched, supply=(1,), install=(1,))
    assert r.status_code in (302, 303)
    assert "/merged/view/" in r.headers["Location"]
    bills = _bills()
    assert len(bills) == 2
    assert [b["leg"] for b in bills] == ["supply", "installation"]
    m = _merged()
    assert m["supply_ra_id"] == bills[0]["id"]
    assert m["installation_ra_id"] == bills[1]["id"]


def test_both_legs_are_ISSUED_because_a_merge_refuses_a_draft(client, sched):
    """`merged_ra.can_merge()`'s rule is not relaxed for this path — *"a merge
    raises a tax invoice, and a draft is not a claim that has gone anywhere"*.
    The form says so above the button."""
    _post(client, sched, supply=(1,), install=(1,))
    assert [b["status"] for b in _bills()] == ["issued", "issued"]
    assert "issues both" in _form(client, sched)


def test_NEITHER_LEG_CARRIES_A_TAX_INVOICE_NUMBER(client, sched):
    """
    THE ASSERTION THAT MATTERS MOST (2 of 4). Three serials over one billing
    is what Rule 46 exists to prevent, and GSTR-1 would report the two legs as
    phantom invoices. Only the merged document carries one.
    """
    _post(client, sched, supply=(1,), install=(1,))
    for b in _bills():
        assert b["tax_invoice_ref"] == "", (
            f"RA{b['ra_no']} minted {b['tax_invoice_ref']!r}")
    assert _merged()["tax_invoice_ref"].startswith("SF/MI/"), (
        "the merged document must carry the one statutory serial")


def test_a_leg_raised_this_way_cannot_print_as_a_tax_invoice_alone(client, sched):
    """It has no invoice number, so the sheet it prints carries none — which
    is the truth about it."""
    _post(client, sched, supply=(1,), install=(1,))
    b = _bills()[0]
    approval.stamp_creator(b)
    b["approval_status"] = "approved"
    html = client.get(f"/ra/print/{b['id']}").get_data(as_text=True)
    assert b["ref"] in html
    assert "SF/MI/" not in html, "a leg must not print the merged serial"


def test_the_ra_no_series_and_the_leg_model_are_untouched(client, sched):
    """Each leg takes the next `ra_no` on its chain exactly as a hand-raised
    bill does, and is an ordinary RA bill in every register and every total."""
    _post(client, sched, supply=(1,), install=(1,))
    bills = _bills()
    assert [b["ra_no"] for b in bills] == [1, 2]
    assert all(b["boq_id"] == sched for b in bills)
    assert all(b["ref"].startswith("SF/RA/") for b in bills)
    # …and a hand-raised bill afterwards carries on the same series.
    lid, q = _approved(sched, "supply")[0]
    client.post(f"/ra/create?boq={sched}&leg=supply", data={
        "date": "2026-10-30",
        "ra_json": json.dumps({"lines": [{"line_id": lid, "qty": "1",
                                          "rate": "1"}]})})
    assert sorted(int(b["ra_no"]) for b in STORE["ra_bills"].values()) == [1, 2, 3]


def test_the_merged_total_is_the_sum_of_the_two_legs_stored_totals(client, sched):
    """CC-2 C3's invariant, which this path must not break: the merged record
    holds no claims of its own."""
    _post(client, sched, supply=(1,), install=(1,))
    a, b = _bills()
    m = _merged()
    assert "claims" not in m
    assert round(m["claim_subtotal"], 2) == round(
        a["claim_subtotal"] + b["claim_subtotal"], 2)


def test_all_three_carry_the_same_set_mark(client, sched):
    _post(client, sched, supply=(1,), install=(1,))
    sids = {RA.set_of(b) for b in _bills()} | {RA.set_of(_merged())}
    assert len(sids) == 1 and "" not in sids


def test_a_bill_raised_on_its_own_carries_no_set_mark(client, sched):
    """Nothing is backfilled and the set rules never touch it."""
    lid, q = _approved(sched, "supply")[0]
    client.post(f"/ra/create?boq={sched}&leg=supply", data={
        "date": "2026-10-29",
        "ra_json": json.dumps({"lines": [{"line_id": lid, "qty": "1",
                                          "rate": "1"}]})})
    b = _bills()[0]
    assert RA.RAISED_AS_BOTH not in b
    assert RA.set_of(b) == ""


# =============================================================================
# ATOMICITY
# =============================================================================

def test_NOTHING_IS_WRITTEN_WHEN_EITHER_LEG_IS_OVER(client, sched):
    """
    THE ASSERTION THAT MATTERS MOST (1 of 4), and the block's own wording.
    Both legs are validated BEFORE the first record exists.
    """
    _lid, approved_qty = _approved(sched, "installation")[0]
    r = _post(client, sched, supply=(1,), install=(approved_qty + 1,))
    assert r.status_code == 200, "an over-claim must not redirect"
    assert STORE["ra_bills"] == {}, "a leg was written despite the refusal"
    assert STORE["merged_ras"] == {}
    body = r.get_data(as_text=True)
    assert "Installation leg:" in body, "the refusal must name which leg"
    assert "Nothing has been saved" in body


def test_the_refusal_names_the_line_and_the_arithmetic(client, sched):
    _lid, approved_qty = _approved(sched, "supply")[0]
    r = _post(client, sched, supply=(approved_qty + 5,), install=(1,))
    body = r.get_data(as_text=True)
    assert "Supply leg:" in body
    assert "over" in body.lower()
    assert STORE["ra_bills"] == {}


def test_a_supply_over_claim_does_not_write_the_installation_leg_either(
        client, sched):
    """The supply leg is validated first, so this is the direction that would
    break if validation and writing were interleaved."""
    _lid, approved_qty = _approved(sched, "supply")[0]
    _post(client, sched, supply=(approved_qty + 1,), install=(1,))
    assert STORE["ra_bills"] == {}


def test_an_empty_post_is_refused_rather_than_raising_three_empty_documents(
        client, sched):
    r = _post(client, sched)
    assert r.status_code == 200
    assert "Nothing has been claimed" in r.get_data(as_text=True)
    assert STORE["ra_bills"] == {} and STORE["merged_ras"] == {}


def test_BOTH_legs_must_claim_something_and_the_message_names_the_remedy(
        client, sched):
    """
    ⚠ **A ONE-SIDED "Both" IS REFUSED, and it should be.** The rule is not
    invented in `raboth.py` — `ra.clean_claims()` refuses an RA bill with no
    claim rows on every path in this application, and a merged document over
    an empty leg would be a bill claiming nothing on one side. CC-2 C3's model
    is two bills **stacked**.

    ⚠ **So the refusal names the right document rather than just saying no.**
    The client asked for three RA types; this is the third, not a replacement
    for the first two, and a claim on one side only is what those are for.
    """
    r = _post(client, sched, supply=(1,))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Installation leg:" in body
    assert "Nothing has been claimed" in body
    assert "RA &amp;middot; Supply or RA &amp;middot; Installation" in body or \
           "RA &middot; Supply or RA &middot; Installation" in body
    assert STORE["ra_bills"] == {} and STORE["merged_ras"] == {}


def test_a_superseded_schedule_is_refused(client, sched):
    STORE["boqs"]["rev1"] = dict(STORE["boqs"][sched], id="rev1",
                                 ref="SF/BOQ/26-27/0099", supersedes=sched,
                                 rev_no=1)
    r = client.get(f"/raboth/create?boq={sched}", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "superseded" in r.headers["Location"]


# =============================================================================
# CANCELLING A SET
# =============================================================================

def test_cancelling_the_merged_document_cancels_all_three(client, sched):
    """
    THE ASSERTION THAT MATTERS MOST (4 of 4). Three documents raised by one
    action are withdrawn by one action, and everything they claimed is free
    again.
    """
    _post(client, sched, supply=(1,), install=(1,))
    m = _merged()
    client.post(f"/merged/cancel/{m['id']}", data={"reason": "wrong figures"})
    assert MRA.is_cancelled(m)
    assert all(RA.is_cancelled(b) for b in _bills()), (
        "a leg was left standing with no invoice over it, still claiming "
        "quantity against the schedule")


def test_the_cancelled_set_frees_what_it_claimed(client, sched):
    lid, approved_qty = _approved(sched, "supply")[0]
    _post(client, sched, supply=(approved_qty,), install=(1,))
    assert RA.claimed_by_line(sched).get((lid, "supply")) == approved_qty
    client.post(f"/merged/cancel/{_merged()['id']}", data={"reason": "x"})
    assert RA.claimed_by_line(sched).get((lid, "supply"), 0.0) == 0.0


def test_an_ASSEMBLED_merge_still_only_RELEASES_its_legs(client, sched):
    """
    ⚠ The difference, and it must not erode. CC-2 C3's own wording for a merge
    built from two bills that already existed: cancelling it releases them,
    and they go on standing with their receipts and numbers intact.
    """
    from conftest import chain_ready
    chain_ready(sched)
    for rid, leg in (("s1", "supply"), ("i1", "installation")):
        lid, _q = _approved(sched, leg)[0]
        STORE["ra_bills"][rid] = {
            "id": rid, "ref": f"SF/RA/26-27/{rid}", "ra_no": 9 if rid == "s1" else 10,
            "date": "2026-10-01", "boq_id": sched, "leg": leg, "status": "issued",
            "claim_subtotal": 100.0, "grand_total": 118.0, "deduction_total": 0.0,
            "net_payable": 100.0, "tax_amount": 18.0, "rounding_off": 0.0,
            "claims": [], "tax_invoice_ref": ""}
    m, err = MRA.create(STORE["ra_bills"]["s1"], STORE["ra_bills"]["i1"])
    assert not err, err
    assert RA.set_of(m) == "", "an assembled merge carries no set mark"
    client.post(f"/merged/cancel/{m['id']}", data={"reason": "x"})
    assert MRA.is_cancelled(m)
    assert not RA.is_cancelled(STORE["ra_bills"]["s1"]), "released, not cancelled"
    assert not RA.is_cancelled(STORE["ra_bills"]["i1"])


def test_a_leg_with_receipts_stops_the_set_cancel_and_writes_nothing(client, sched):
    """`ra.can_cancel()` refuses a bill money was paid against, and that
    refusal is not overridden here."""
    _post(client, sched, supply=(1,), install=(1,))
    leg = _bills()[0]
    STORE.setdefault("receipts", {})["rc1"] = {
        "id": "rc1", "ra_id": leg["id"], "date": "2026-10-30", "amount": 10.0,
        "mode": "NEFT", "ref": "x", "written_off": 0.0}
    m = _merged()
    r = client.post(f"/merged/cancel/{m['id']}", data={"reason": "x"},
                    follow_redirects=False)
    STORE["receipts"].pop("rc1", None)
    assert "type=error" in r.headers["Location"]
    assert not MRA.is_cancelled(m), "the merged document was withdrawn anyway"
    assert not any(RA.is_cancelled(b) for b in _bills())


def test_the_confirmation_page_says_which_of_the_two_it_will_do(client, sched):
    _post(client, sched, supply=(1,), install=(1,))
    html = client.get(f"/merged/cancel/{_merged()['id']}").get_data(as_text=True)
    assert "cancelled with it" in html
    assert "three documents withdrawn together" in html


# =============================================================================
# THE REGISTER
# =============================================================================

def test_the_register_collapses_a_set_under_its_invoice(client, sched):
    _post(client, sched, supply=(1,), install=(1,))
    html = client.get("/ra/").get_data(as_text=True)
    m = _merged()
    assert m["tax_invoice_ref"] in html
    assert "raised as one" in html
    assert "carry no invoice number of their own" in html
    # ⚠ Both legs are still their own rows — nothing is hidden, or the two
    #   tiles above could not be reconciled against the table.
    for b in _bills():
        assert f'>RA{b["ra_no"]}</a>' in html


def test_a_bill_raised_on_its_own_gets_no_header_row(client, sched):
    lid, _q = _approved(sched, "supply")[0]
    client.post(f"/ra/create?boq={sched}&leg=supply", data={
        "date": "2026-10-29",
        "ra_json": json.dumps({"lines": [{"line_id": lid, "qty": "1",
                                          "rate": "1"}]})})
    assert "raised as one" not in client.get("/ra/").get_data(as_text=True)


# =============================================================================
# (b) THE PREREQUISITE IS OFF — AND THE CAP IS NOT
# =============================================================================

def test_the_prerequisite_is_off_on_the_shipped_configuration():
    assert RA.C1_PREREQUISITE is False
    assert RA.c1_prerequisite_on() is False


@pytest.mark.parametrize("leg", ["supply", "installation"])
def test_a_claim_opens_with_no_challan_and_no_sheet(client, sched, leg):
    r = client.get(f"/ra/create?boq={sched}&leg={leg}")
    assert r.status_code == 200, "the C1 prerequisite still refuses"


def test_the_form_says_which_cap_applies(client, sched):
    html = client.get(f"/ra/create?boq={sched}&leg=installation").get_data(as_text=True)
    assert "capped at the BOQ quantity" in html
    assert "No approved measurement sheet exists on this schedule yet" in html


def test_THE_MEASUREMENT_CAP_STILL_BINDS(client, sched):
    """
    THE ASSERTION THAT MATTERS MOST (3 of 4). ⚠ **Only the PREREQUISITE was
    relaxed.** With an approved sheet on the chain, `ra.overclaims()` caps the
    installation claim at the MEASURED quantity exactly as it did before, and
    a line the sheet did not measure cannot be claimed at all.
    """
    lid, approved_qty = _approved(sched, "installation")[0]
    measured = 2.0
    assert approved_qty > measured
    STORE["measurements"]["ms1"] = {
        "id": "ms1", "ref": "SF/MS/26-27/0001", "date": "2026-10-02",
        "boq_id": sched, "approval_status": approval.APPROVED,
        "created_by": "somebody-else",
        "items": [{"line_id": lid, "qty": measured, "is_header": False}]}

    # The form says the cap moved…
    html = client.get(f"/ra/create?boq={sched}&leg=installation").get_data(as_text=True)
    assert "capped at the MEASURED quantity" in html

    # …and the guard enforces it: measured + 1 is refused, though it is well
    # under the BOQ quantity.
    over = RA.overclaims(sched, "installation",
                         [{"line_id": lid, "qty": measured + 1}])
    assert over and over[0]["reason"] == "overmeasured"
    assert RA.overclaims(sched, "installation",
                         [{"line_id": lid, "qty": measured}]) == []


def test_with_no_sheet_the_cap_is_the_BOQ_quantity(client, sched):
    """`overclaims()`'s `measured == {}` path — **unchanged by one
    character**; what changed is that it is now reachable on a new project."""
    lid, approved_qty = _approved(sched, "installation")[0]
    assert RA.overclaims(sched, "installation",
                         [{"line_id": lid, "qty": approved_qty}]) == []
    over = RA.overclaims(sched, "installation",
                         [{"line_id": lid, "qty": approved_qty + 1}])
    assert over and over[0]["reason"] == "overclaim"


def test_a_line_the_sheet_did_not_measure_cannot_be_claimed(client, sched):
    """Once ONE approved sheet exists, every line's ceiling comes from it —
    including a line it did not measure, whose ceiling is nil."""
    lines = _approved(sched, "installation")
    (lid, _q), (other, _o) = lines[0], lines[1]
    STORE["measurements"]["ms1"] = {
        "id": "ms1", "ref": "SF/MS/26-27/0001", "date": "2026-10-02",
        "boq_id": sched, "approval_status": approval.APPROVED,
        "created_by": "somebody-else",
        "items": [{"line_id": lid, "qty": 2.0, "is_header": False}]}
    over = RA.overclaims(sched, "installation", [{"line_id": other, "qty": 1}])
    assert over and over[0]["reason"] == "not_measured"


def test_the_supply_leg_gets_no_ceiling_from_a_challan(client, sched):
    """C1's asymmetry is untouched: a challan proves the supply and no
    quantity flows from it. `challan.BLOCK_OVER_DISPATCH` is False on purpose."""
    lid, approved_qty = _approved(sched, "supply")[0]
    STORE["delivery_challans"]["dc1"] = {
        "id": "dc1", "ref": "DC/1", "date": "2026-10-01", "boq_id": sched,
        "items": [{"line_id": lid, "qty": 1}]}
    assert RA.overclaims(sched, "supply",
                         [{"line_id": lid, "qty": approved_qty}]) == []


def test_the_boq_bar_advises_instead_of_greying(client, sched):
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert 'class="btn btn-ghost rb-off"' not in html
    assert "no delivery challan on this schedule yet" in html
    assert "capped at the BOQ quantity" in html


def test_the_gate_still_works_when_it_is_armed(client, sched, monkeypatch):
    """The switch is a switch. `tests/test_c1_order_of_working.py` proves the
    whole rule under the `c1_prerequisite_on` fixture; this is the one-line
    statement of it beside the OFF behaviour."""
    monkeypatch.setattr(RA, "C1_PREREQUISITE", True)
    r = client.get(f"/ra/create?boq={sched}&leg=supply", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "delivery challan" in r.headers["Location"].lower().replace("+", " ")
