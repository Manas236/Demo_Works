"""
RA edit and delete, driven end to end — CLIENT_CHANGES-2.md **A6**.

Closed under the **28 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md` §0 as
**built with a stated limitation**.

### What was ruled, and what this file is for

The client asked for "edit and delete in RA" without qualification. Two
narrowings sit between that sentence and the code:

- **Draft only** — CC-2's own narrowing. An issued bill is cancelled and
  reissued, never edited.
- **Latest bill only** — the code's, which CC-2's requirement line does not
  carry, and which PROGRESS.md §6-A had held open as a candidate for lifting.

**The second one was deliberately kept.** RA bills are cumulative: editing bill
3 while bill 5 exists corrupts every claim downstream of it. The client asked
without qualification because the chain arithmetic is not his to know.
`claim_is_frozen()` → `is_latest_bill()` is **correct behaviour, not a
shortfall**. Arbitrary mid-chain editing is new scope and is priced nowhere.

### Why this file exists beside `test_ra_routes.py`

`test_ra_routes.py` already unit-tests the gates and pins the refusals. **It
does not drive the feature end to end**, and "A6 is built" is a claim about the
product, not about `can_edit()`. So everything below goes through the real
routes with real form posts — create the bill, open the form, submit it, read
the result back — and asserts the figures actually moved.

Nothing in `ra.py`'s lifecycle logic was changed by the pass that added this
file. What changed is the two refusals, which now **explain why and name
cancelling forward as the supported route**, and that is what §3 pins.
"""

import json

import pytest

import boq as BQ
import demo_data as DD
import ra
from store import STORE
from conftest import printable


@pytest.fixture()
def seeded(client):
    """The real 97-line Sify BOQ, seeded through the app."""
    STORE["ra_bills"].clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()


def priced(boq_id, n=None):
    """
    Priced lines with room to move — `total_qty >= 20`.

    The first priced line of the demo BOQ carries a total quantity of **4**, so
    a test that raises 2 and edits it to 7 is refused by the cumulative
    over-claim block rather than by anything this file is about. Filtering here
    keeps every assertion below about edit and delete.
    """
    lines = [li for li in STORE["boqs"][boq_id]["line_items"]
             if not li["is_header"] and li["total_qty"] >= 20]
    assert len(lines) >= 3, "the demo BOQ no longer has three roomy lines"
    return lines[:n] if n else lines


def payload(rows):
    return json.dumps({"lines": [{"line_id": lid, "qty": str(q), "rate": str(r)}
                                 for lid, q, r in rows]})


def _raise(client, boq_id, line, qty, leg="supply"):
    """One bill, through `/ra/create`, and its id."""
    before = set(STORE["ra_bills"])
    r = client.post(f"/ra/create?boq={boq_id}&leg={leg}", data={
        "date": "2026-08-06", "notes": "",
        "ra_json": payload([(line["line_id"], qty, line["supply_rate"])]),
    })
    assert r.status_code == 302, "the bill was not created"
    new = set(STORE["ra_bills"]) - before
    assert len(new) == 1
    return new.pop()


# ══ 1. EDIT genuinely works on the latest bill ════════════════════════════

def test_the_latest_draft_is_created_edited_and_read_back_through_the_routes(
        client, seeded):
    """
    **The end-to-end claim, in one test.** Not `can_edit()` returning True —
    a bill raised through the create form, changed through the edit form, and
    the new figure read off the record afterwards.
    """
    line = priced(seeded, 1)[0]
    rid = _raise(client, seeded, line, 2)

    bill = STORE["ra_bills"][rid]
    assert bill["status"] == "draft"
    assert bill["claims"][0]["qty"] == 2.0
    was_subtotal = bill["claim_subtotal"]

    form = client.get(f"/ra/edit/{rid}")
    assert form.status_code == 200, "the edit form did not open on a latest draft"

    r = client.post(f"/ra/edit/{rid}", data={
        "date": "2026-08-09", "notes": "quantity re-measured on site",
        "ra_json": payload([(line["line_id"], 7, line["supply_rate"])]),
    })
    assert r.status_code == 302

    bill = STORE["ra_bills"][rid]
    assert bill["claims"][0]["qty"] == 7.0, "the edit did not land"
    assert bill["claim_subtotal"] != was_subtotal, \
        "the quantity moved but the money did not follow it"
    assert bill["date"] == "2026-08-09", "the date did not follow the edit"


def test_the_edited_figure_reaches_the_printed_bill(client, seeded):
    """
    An edit that does not reach the document is not an edit.

    `/ra/print` is the thing the main contractor is handed, so it is what the
    figure has to be true on.
    """
    line = priced(seeded, 1)[0]
    rid = _raise(client, seeded, line, 2)

    assert client.post(f"/ra/edit/{rid}", data={
        "date": "2026-08-09", "notes": "",
        "ra_json": payload([(line["line_id"], 7, line["supply_rate"])]),
    }).status_code == 302

    # CC-2 B7: a bill raised through /ra/create is pending and does not print.
    # What this test is about is whether an EDIT reaches the sheet, so the bill
    # is made printable after the edit — see tests/conftest.py::printable.
    printable(STORE["ra_bills"][rid])
    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert BQ._fmt_qty(7.0) in html, "the printed bill still shows the old claim"


def test_editing_the_latest_bill_of_a_chain_of_three(client, seeded):
    """
    The restriction is about **position**, not about being the only bill.

    A chain of three with the third still a draft: the third is editable, and
    the two before it are not. Both halves in one test, because either on its
    own would pass against a gate that had simply broken.
    """
    lines = priced(seeded, 3)
    first = _raise(client, seeded, lines[0], 1)
    second = _raise(client, seeded, lines[1], 1)
    third = _raise(client, seeded, lines[2], 1)

    assert client.get(f"/ra/edit/{third}").status_code == 200, \
        "the latest bill of a chain of three could not be edited"
    assert client.get(f"/ra/edit/{first}").status_code == 302
    assert client.get(f"/ra/edit/{second}").status_code == 302

    assert client.post(f"/ra/edit/{third}", data={
        "date": "2026-08-09", "notes": "",
        "ra_json": payload([(lines[2]["line_id"], 3, lines[2]["supply_rate"])]),
    }).status_code == 302
    assert STORE["ra_bills"][third]["claims"][0]["qty"] == 3.0


# ══ 2. DELETE genuinely works on the latest bill ══════════════════════════

def test_the_latest_draft_is_deleted_through_the_route_and_is_gone(client, seeded):
    line = priced(seeded, 1)[0]
    rid = _raise(client, seeded, line, 2)

    confirm = client.get(f"/ra/delete/{rid}")
    assert confirm.status_code == 200, "the confirmation page did not open"
    assert "cannot be undone" in confirm.get_data(as_text=True)
    assert rid in STORE["ra_bills"], "GET on the delete route destroyed the bill"

    r = client.post(f"/ra/delete/{rid}")
    assert r.status_code == 302
    assert rid not in STORE["ra_bills"], "the bill is still there"


def test_deleting_the_latest_bill_frees_the_quantity_it_claimed(client, seeded):
    """
    The consequence the confirmation page promises, asserted rather than
    described: *"those quantities go back onto the balance of every line it
    claimed"*.
    """
    line = priced(seeded, 1)[0]
    rid = _raise(client, seeded, line, 5)

    claimed = ra.claimed_by_line(seeded)
    assert claimed.get((line["line_id"], "supply"), 0.0) == 5.0

    assert client.post(f"/ra/delete/{rid}").status_code == 302

    claimed = ra.claimed_by_line(seeded)
    assert claimed.get((line["line_id"], "supply"), 0.0) == 0.0, \
        "the deleted bill's quantity is still held against the line"


def test_the_number_is_reused_after_the_latest_bill_is_deleted(client, seeded):
    """
    Deliberately **not** the cancel behaviour, and the contrast is the point:
    a cancelled number stays spent, a deleted one does not. A draft was never
    seen by anybody.
    """
    lines = priced(seeded, 2)
    first = _raise(client, seeded, lines[0], 1)
    second = _raise(client, seeded, lines[1], 1)
    assert STORE["ra_bills"][second]["ra_no"] == 2

    assert client.post(f"/ra/delete/{second}").status_code == 302

    again = _raise(client, seeded, lines[1], 1)
    assert STORE["ra_bills"][again]["ra_no"] == 2, \
        "a deleted draft's number was not reused"
    assert first in STORE["ra_bills"], "deleting RA2 took RA1 with it"


def test_deleting_the_middle_of_a_chain_is_refused_through_the_route(client, seeded):
    lines = priced(seeded, 2)
    first = _raise(client, seeded, lines[0], 1)
    _raise(client, seeded, lines[1], 1)

    r = client.post(f"/ra/delete/{first}")
    assert r.status_code == 302
    assert first in STORE["ra_bills"], "a mid-chain bill was deleted"


# ══ 3. The refusals explain themselves — the part A6 changed ═════════════

def test_the_edit_refusal_says_why_and_names_the_supported_route(client, seeded):
    """
    **The whole of what the 28 August pass changed in `ra.py`.**

    The restriction stays; the refusal stopped one sentence short of useful. A
    refusal that only says no leaves the operator to guess, and the guess that
    is available — silently correcting it on the next claim — is worse than
    either supported answer.
    """
    lines = priced(seeded, 2)
    first = _raise(client, seeded, lines[0], 1)
    _raise(client, seeded, lines[1], 1)

    why = ra.frozen_reason(STORE["ra_bills"][first])

    assert "RA2" in why, "the refusal must name what froze this bill"
    assert "cumulative" in why, "and must say why that matters"
    assert "already sent out" in why, "and what the consequence would be"
    assert "Cancel" in why, "and must name the supported route"
    assert "next claim" in why, "and the alternative to cancelling forward"


def test_the_delete_refusal_says_why_and_names_the_supported_route(client, seeded):
    lines = priced(seeded, 2)
    first = _raise(client, seeded, lines[0], 1)
    _raise(client, seeded, lines[1], 1)

    allowed, why = ra.can_delete(STORE["ra_bills"][first])
    assert allowed is False

    assert "Only the latest bill can be deleted" in why
    assert "RA2" in why, "the refusal must name what is in the way"
    assert "cumulative" in why
    assert "newest first" in why, "and must name the order to work in"
    assert "becomes the latest bill again" in why, \
        "and must say what makes this bill deletable"


def test_the_refusal_reaches_the_operator_and_not_just_the_function(client, seeded):
    """
    A message nobody sees is not an explanation.

    Driven through the route, because that is where the operator meets it — the
    redirect carries the reason as the flash message.
    """
    lines = priced(seeded, 2)
    first = _raise(client, seeded, lines[0], 1)
    _raise(client, seeded, lines[1], 1)

    r = client.get(f"/ra/edit/{first}")
    assert r.status_code == 302
    location = r.headers["Location"].replace("+", " ").replace("%20", " ")
    assert "cumulative" in location or "Cancel" in location, \
        "the reason did not travel with the redirect"

    page = client.get(f"/ra/view/{first}?msg=x&type=error")
    assert page.status_code == 200


# ══ 4. The limitation, pinned as a limitation ════════════════════════════

def test_the_latest_bill_only_restriction_is_deliberate_and_still_real(
        client, seeded):
    """
    ⚠ **This asserts a LIMITATION, and it is meant to.**

    A6 closes as *built with a stated limitation*, so the limitation has to be
    something a test fails on if it is removed by accident. If somebody lifts
    the restriction deliberately, they come here, and that is the point.

    A **cancelled** later bill freezes an earlier draft too, because
    `bills_of()` keeps cancelled bills. That is reachable in ordinary use and is
    recorded in PROGRESS.md §6-A rather than left to be discovered.
    """
    lines = priced(seeded, 2)
    first = _raise(client, seeded, lines[0], 1)
    second = _raise(client, seeded, lines[1], 1)

    # Issue and cancel the later bill; the earlier draft stays frozen.
    assert client.post(f"/ra/issue/{second}").status_code == 302
    assert client.post(f"/ra/cancel/{second}",
                       data={"cancel_reason": "raised in error"}).status_code == 302
    assert ra.is_cancelled(STORE["ra_bills"][second])

    assert ra.claim_is_frozen(STORE["ra_bills"][first]) is True, \
        "a cancelled later bill stopped freezing the earlier draft"
    assert client.get(f"/ra/edit/{first}").status_code == 302
