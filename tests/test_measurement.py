"""
CC-2 **C2** — the measurement sheet, and the two guards that are its point.

C2, **in full**, is three lines:

    Raised from the BOQ. Approved measurements become the source of
    installation quantity on RA-Installation.

⚠ **Read that again before changing anything here.** Two of the things this file
asserts are CC-2's, and everything else is **ours**:

| assertion | whose |
|---|---|
| a sheet is raised from a BOQ | CC-2 |
| an approved sheet is the source of installation quantity | CC-2 |
| a measured quantity may not exceed the BOQ quantity | ours |
| the measured quantity is cumulative across sheets | ours |
| the RA ladder governs a measurement | ours |
| the sheet prints at all | ours — and **no golden is pinned on it** |

The distinction is not pedantry: it is the difference between a delivered
requirement and unpriced work, and the fifth 29 August 2026 override block
records each of them by name.

⚠ **Every refusal here is hit at its URL.** Hiding a button is not a gate —
B5's rule — and `/measurement/create` is a typeable address.
"""

import json

import pytest

import approval
import boq as BQ
import demo_data as DD
import measurement as MS
import ra
from store import STORE

from conftest import ensure_test_user


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(client):
    """The real 97-line Sify BOQ, and nothing in front of it."""
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()


def priced(boq_id, n=None):
    lines = [li for li in STORE["boqs"][boq_id]["line_items"]
             if not li["is_header"] and li["total_qty"] > 0]
    return lines[:n] if n else lines


def payload(rows):
    """rows: [(line_id, qty)] -> the hidden field's JSON."""
    return json.dumps({"lines": [{"line_id": lid, "qty": str(q)}
                                 for lid, q in rows]})


def raise_sheet(client, boq_id, rows, date="2026-08-20", **extra):
    """POST the create form. Returns the response."""
    data = {"date": date, "location": "Block A", "measured_by": "R. Kadam",
            "witnessed_by": "", "notes": "", "ms_json": payload(rows)}
    data.update(extra)
    return client.post(f"/measurement/create?boq={boq_id}", data=data)


def only_sheet():
    return next(iter(STORE["measurements"].values()))


# ═══════════════════════════════════════════════════════════════════════════
# RAISED FROM THE BOQ — CC-2's first sentence
# ═══════════════════════════════════════════════════════════════════════════

def test_the_form_is_raised_against_a_schedule_and_refuses_without_one(client):
    """`/measurement/create` with no BOQ has nothing to measure against."""
    r = client.get("/measurement/create", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/boq/" in r.headers["Location"]


def test_the_form_shows_every_boq_line(client, seeded):
    h = client.get(f"/measurement/create?boq={seeded}").get_data(as_text=True)
    for li in STORE["boqs"][seeded]["line_items"]:
        if li["is_header"]:
            continue
        assert li["line_id"] in h, f'{li["item_no"]} missing from the picker'


def test_a_superseded_revision_is_refused_at_the_route(client, seeded):
    """`/dc/create`, `/ra/create` and `/po/create` all make the same check."""
    STORE["boqs"]["rev1"] = dict(STORE["boqs"][seeded], id="rev1", rev_no=1,
                                 supersedes=seeded, ref="SF/BOQ/26-27/0002")
    r = client.get(f"/measurement/create?boq={seeded}", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "superseded" in r.headers["Location"].lower().replace("+", " ")


def test_a_sheet_snapshots_the_schedule_it_was_raised_against(client, seeded):
    """
    CLIENT_CHANGES.md §1.2 — the sheet reads as a historical record after the
    schedule is revised. `print_ra()`'s original defect is why the rule exists.
    """
    li = priced(seeded, 1)[0]
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    ms = only_sheet()

    assert ms["boq_id"] == seeded
    assert ms["boq_ref"] == STORE["boqs"][seeded]["ref"]
    row = ms["items"][0] if not ms["items"][0].get("is_header") else ms["items"][1]
    assert row["description"] == li["description"]
    assert row["unit"] == li["unit"]
    assert row["boq_qty"] == float(li["total_qty"])


def test_the_reference_is_fy_scoped_and_never_reissued(client, seeded):
    lines = priced(seeded, 2)
    raise_sheet(client, seeded, [(lines[0]["line_id"], 1)])
    first = only_sheet()["ref"]
    raise_sheet(client, seeded, [(lines[1]["line_id"], 1)])
    refs = sorted(m["ref"] for m in STORE["measurements"].values())
    assert refs[0] == first
    assert refs == ["SF/MS/26-27/0001", "SF/MS/26-27/0002"]

    # max+1, not len+1: deleting the second must not hand its number back.
    second = next(m for m in STORE["measurements"].values()
                  if m["ref"] == "SF/MS/26-27/0002")
    STORE["measurements"].pop(second["id"])
    assert MS.next_ref("2026-08-20") == "SF/MS/26-27/0002", (
        "a deleted sheet handed its number back — a second sheet bearing a "
        "number somebody has already signed is indistinguishable from the first")


# ═══════════════════════════════════════════════════════════════════════════
# GUARD 1 — measured may not exceed the BOQ quantity  (OURS)
# ═══════════════════════════════════════════════════════════════════════════

def test_a_measured_quantity_above_the_schedule_is_refused(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    r = raise_sheet(client, seeded, [(li["line_id"], li["total_qty"] + 1)])

    assert r.status_code == 200, "the form should come back, not save"
    assert not STORE["measurements"], "the sheet saved past its BOQ quantity"
    h = r.get_data(as_text=True)
    assert "Nothing was saved" in h
    assert "over" in h


def test_the_refusal_names_the_line_and_the_whole_arithmetic(client, seeded):
    """
    "Item 24.d is over" is not something anyone can act on. `35 in the
    schedule, 21 already measured, 18 here, 4 over` is.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    h = raise_sheet(client, seeded,
                    [(li["line_id"], li["total_qty"] + 5)]).get_data(as_text=True)
    assert f"Item {li['item_no']}" in h
    assert "in the schedule" in h
    assert "already measured on other sheets" in h


def test_measuring_exactly_the_schedule_is_allowed(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    r = raise_sheet(client, seeded, [(li["line_id"], li["total_qty"])])
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:400]
    assert len(STORE["measurements"]) == 1


def test_the_guard_is_CUMULATIVE_across_sheets(client, seeded):
    """
    ⚠ **OURS, and the half that makes the guard worth having.** The rule stated
    per line would let two sheets each measure the whole of a line while the
    total came to twice the schedule. Real measurement happens in stages.
    `ra.overclaims()` is cumulative for exactly this reason, one document along.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    half = li["total_qty"] / 2.0

    r1 = raise_sheet(client, seeded, [(li["line_id"], half)])
    assert r1.status_code in (302, 303)

    r2 = raise_sheet(client, seeded, [(li["line_id"], half + 1)])
    assert r2.status_code == 200, (
        "a second sheet took the line past the schedule and was accepted — "
        "the guard is per-sheet, not cumulative, and is decorative")
    assert len(STORE["measurements"]) == 1

    # The balance still measures.
    r3 = raise_sheet(client, seeded, [(li["line_id"], half)])
    assert r3.status_code in (302, 303)
    assert len(STORE["measurements"]) == 2


def test_a_REJECTED_sheet_releases_its_quantity(client, seeded):
    """
    A refused sheet is not competing for the schedule's quantity — the same
    reasoning that makes `ra.claimed_by_line()` skip a cancelled bill. Leaving
    it in the sum would permanently sterilise every quantity anybody ever got
    wrong.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], li["total_qty"])])
    only_sheet()["approval_status"] = approval.REJECTED

    r = raise_sheet(client, seeded, [(li["line_id"], li["total_qty"])])
    assert r.status_code in (302, 303), (
        "a rejected sheet is still holding the line's quantity")


def test_an_edit_is_not_compared_against_its_own_figures(client, seeded):
    """
    `exclude_id`. Without it an edit that changes nothing would refuse itself —
    `ra.overclaims()` takes the same argument for the same reason and it is the
    same bug one document over.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], li["total_qty"])])
    ms = only_sheet()

    r = client.post(f"/measurement/edit/{ms['id']}", data={
        "date": ms["date"], "location": "Block B", "measured_by": "R. Kadam",
        "witnessed_by": "", "notes": "",
        "ms_json": payload([(li["line_id"], li["total_qty"])])})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:400]
    assert STORE["measurements"][ms["id"]]["location"] == "Block B"


def test_a_line_not_in_the_schedule_is_its_own_refusal():
    """
    `not_in_boq` rather than a zero ceiling, because the two send the reader
    somewhere different — to the schedule, or to the site.
    """
    breaches = MS.overmeasures("nope", [{"line_id": "ffffffffffff",
                                         "item_no": "9", "qty": 3.0}])
    assert len(breaches) == 1
    assert breaches[0]["reason"] == "not_in_boq"
    assert "not in this schedule" in MS.overmeasure_message(breaches[0])


# ═══════════════════════════════════════════════════════════════════════════
# GUARD 2 — the approved measurement is the installation ceiling  (CC-2's)
# ═══════════════════════════════════════════════════════════════════════════

def _approve(ms):
    """Approve a sheet directly. `conftest.printable()`'s reasoning."""
    ms["approval_status"] = approval.APPROVED
    return ms


def test_only_an_APPROVED_sheet_feeds_the_ceiling(client, seeded):
    """CC-2's own word: *"**Approved** measurements become the source."*"""
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    ms = only_sheet()

    assert MS.approved_qty_by_line(seeded) == {}, (
        "a PENDING sheet is already feeding the installation ceiling — CC-2 "
        "says approved measurements, and an unapproved one is a number "
        "somebody typed")
    assert not MS.has_approved_measurement(seeded)

    _approve(ms)
    assert MS.approved_qty_by_line(seeded)[li["line_id"]] == 2.0
    assert MS.has_approved_measurement(seeded)


def test_an_installation_claim_is_capped_at_the_measured_quantity(client, seeded):
    """
    ⚠ **CC-2's second sentence, in one assertion.** The line carries a BOQ
    quantity well above the measured one, so a claim between the two proves the
    ceiling moved from the schedule to the sheet.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    _approve(only_sheet())

    claim = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 4.0}]
    breaches = ra.overclaims(seeded, "installation", claim)
    assert breaches, (
        "4 was claimed against 3 measured and passed — the installation "
        "ceiling is still the BOQ quantity and C2's whole sentence is inert")
    assert breaches[0]["reason"] == "overmeasured"
    assert breaches[0]["approved"] == 3.0
    assert "over the measurement" in ra.overclaim_message(breaches[0])

    # And exactly the measured quantity passes.
    claim[0]["qty"] = 3.0
    assert ra.overclaims(seeded, "installation", claim) == []


def test_the_SUPPLY_leg_keeps_the_BOQ_ceiling(client, seeded):
    """
    CC-2 says a challan proves the supply and says nothing about a quantity
    flowing from one to the other. Deriving a supply ceiling from dispatch would
    be inventing a rule — and the wrong one, because
    `challan.BLOCK_OVER_DISPATCH` is False on purpose.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    _approve(only_sheet())

    claim = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 4.0}]
    assert ra.overclaims(seeded, "supply", claim) == [], (
        "the measurement lowered the SUPPLY ceiling — supply is proven by a "
        "challan and CC-2 puts no quantity on that arrow")


def test_a_line_the_sheet_did_not_measure_cannot_be_claimed(client, seeded):
    """
    Once one approved sheet exists, every line's installation ceiling comes from
    measurement — including a line nobody measured, whose ceiling is nil. That
    is the rule and not an edge case.

    It gets its **own** refusal rather than "0 approved", because the latter
    would be a lie about the BOQ and would send the operator to revise a
    schedule that is fine.
    """
    a, b = priced(seeded, 2)
    raise_sheet(client, seeded, [(a["line_id"], 1)])
    _approve(only_sheet())

    claim = [{"line_id": b["line_id"], "item_no": b["item_no"], "qty": 1.0}]
    breaches = ra.overclaims(seeded, "installation", claim)
    assert len(breaches) == 1
    assert breaches[0]["reason"] == "not_measured"
    msg = ra.overclaim_message(breaches[0])
    assert "no approved measurement behind it" in msg
    assert "Measure it" in msg, "the message does not say what to do next"
    # It must NOT wear the over-claim message's words, which quote an approved
    # quantity: "0 approved" reads as a defect in the schedule and sends the
    # operator to revise a BOQ that is fine.
    assert "approved," not in msg and "already claimed" not in msg, (
        "the missing-measurement refusal is wearing the over-claim message")


def test_a_project_with_no_measurement_keeps_the_BOQ_CEILING(client, seeded):
    """
    ⚠ **The grandfather rule at the arithmetic level.** Requiring a measurement
    here would break every installation bill raised before this module existed.
    `tests/test_measurement_pin.py` is what stops the exception growing.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    assert MS.approved_qty_by_line(seeded) == {}
    claim = [{"line_id": li["line_id"], "item_no": li["item_no"],
              "qty": li["total_qty"]}]
    assert ra.overclaims(seeded, "installation", claim) == []


# ═══════════════════════════════════════════════════════════════════════════
# APPROVAL — the ladder, which is OURS
# ═══════════════════════════════════════════════════════════════════════════

def test_the_measurement_ladder_is_the_RA_LADDER_and_that_is_our_choice():
    """
    ⚠ **B6 names charges and RA / Tax Invoice / PO. It does not name a
    measurement.** The RA ladder was chosen because a measurement exists to feed
    an RA-Installation bill and the two claim against the same schedule; the
    charges ladder ends at HR, who has nothing to say about what was measured on
    a site.

    If this ever fails, somebody changed the ladder — which is one word in
    `approval.DOCUMENTS` and a decision for the client-facing owner, not a
    refactor.
    """
    spec = approval.DOCUMENTS["measurement"]
    assert spec["steps"] == approval.DOCUMENTS["ra"]["steps"] == (
        "operation-head", "director")
    assert spec["sequential"] is False
    assert spec["sequential"] == approval.DOCUMENTS["ra"]["sequential"]


def test_editing_a_sheet_sends_it_back_to_the_bottom_of_the_ladder(client, seeded):
    """
    An approval describes the document somebody read, so a changed document has
    not been approved. `ra.edit_ra()` calls `clear_approvals()` for the reason.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    ms = only_sheet()
    ms["approvals"] = [{"role": "operation-head", "role_name": "Operation Head",
                        "user_id": "someone-else", "user_name": "X",
                        "at": "2026-08-29 10:00"}]

    # A part-climbed ladder is LOCKED (approval.can_modify), so the edit is
    # refused rather than silently clearing the rung.
    r = client.post(f"/measurement/edit/{ms['id']}", data={
        "date": ms["date"], "location": "B", "measured_by": "", "witnessed_by": "",
        "notes": "", "ms_json": payload([(li["line_id"], 2)])},
        follow_redirects=False)
    assert r.status_code in (302, 303)
    assert approval.approvals_of(ms), "the rung was cleared by a refused edit"

    # With no rung climbed, the edit goes through and clears nothing that was
    # there — but it does return the record to pending explicitly.
    ms["approvals"] = []
    ms["approval_status"] = approval.APPROVED
    ms["approval_status"] = approval.PENDING     # approved is locked; see below
    r = client.post(f"/measurement/edit/{ms['id']}", data={
        "date": ms["date"], "location": "B", "measured_by": "", "witnessed_by": "",
        "notes": "", "ms_json": payload([(li["line_id"], 2)])})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:400]
    assert approval.status_of(ms) == approval.PENDING


def test_an_approved_sheet_is_locked_at_its_edit_and_delete_URLs(client, seeded):
    """
    `approval.can_modify()` — ours, not CC-2's. An approved sheet is the ceiling
    a claim was checked against; editing it behind the claim moves the ceiling
    under a bill that has already been raised.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    ms = _approve(only_sheet())

    for url in (f"/measurement/edit/{ms['id']}",
                f"/measurement/delete/{ms['id']}"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code in (302, 303), f"{url} rendered on an approved sheet"
    assert client.post(f"/measurement/delete/{ms['id']}").status_code in (302, 303)
    assert ms["id"] in STORE["measurements"], "an approved sheet was deleted"


def test_a_measurement_records_who_raised_it(client, seeded):
    """B6's load-bearing rule needs a creator recorded at the write site."""
    li = priced(seeded, 1)[0]
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    assert only_sheet()["created_by"] == ensure_test_user()["id"]


# ═══════════════════════════════════════════════════════════════════════════
# THE PRINTED SHEET — ours, and deliberately not pinned
# ═══════════════════════════════════════════════════════════════════════════

def test_an_unapproved_sheet_does_not_print_and_the_refusal_is_at_the_URL(
        client, seeded):
    """B7, on the fifth document. There is no draft/cancelled exemption here."""
    li = priced(seeded, 1)[0]
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    ms = only_sheet()

    r = client.get(f"/measurement/print/{ms['id']}", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert client.get(f"/measurement/view/{ms['id']}").status_code == 200, (
        "B7 permits the viewing and refuses only the printing")

    _approve(ms)
    assert client.get(f"/measurement/print/{ms['id']}").status_code == 200


def test_the_printed_sheet_reuses_the_shared_document_furniture(client, seeded):
    """
    ⚠ **CC-2 is silent on whether a measurement prints, so NOTHING was
    invented.** No golden is pinned on this page. What is asserted is that the
    page is built out of `docsheet.py`'s existing chrome rather than a
    letterhead somebody drew — which is the whole of what the silence permits.
    """
    li = priced(seeded, 1)[0]
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)

    # The shared sheet's own structural markers, the ones test_print_golden.py
    # splits every A4 document on.
    for marker in ('<table class="page-frame">', '<div class="doc-box">',
                   '<div class="doc-header', '<div class="items-wrap">',
                   '<div class="sig-block">'):
        assert marker in h, f"the printed sheet does not carry {marker}"
    assert "MEASUREMENT SHEET" in h


def test_no_money_reaches_the_printed_sheet(client, seeded):
    """
    A measurement is signed in the field by a site engineer. A rate on it turns
    a measurement into a claim — `challan.py`'s rule, one document along.
    """
    li = next(x for x in priced(seeded) if float(x["install_rate"] or 0) > 0)
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)

    assert MS.PRINT_RATES is False and MS.PRINT_TAX is False
    assert MS.PRINT_TOTALS is False
    assert "&#8377;" not in h and "Amount" not in h
    assert f"{float(li['install_rate']):,.2f}" not in h


def test_nothing_about_approval_reaches_the_printed_sheet(client, seeded):
    """
    CC-2 carries no requirement that anything about approval appears on paper.
    `tests/test_approval_b7.py` sweeps every pinned sheet; this covers the one
    that is not pinned.
    """
    li = priced(seeded, 1)[0]
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)

    for s in ("APPROVED", "AWAITING APPROVAL", "CREATOR UNKNOWN",
              approval.GRANDFATHER_NOTE, "Approve", "Reject"):
        assert s not in h, f"the printed measurement carries {s!r}"


def test_this_module_never_writes_our_own_identity_into_its_source():
    """
    `tests/test_ra_seller_identity.py`'s rule, applied to the third document
    that prints who we are: a State name or a GSTIN-shaped literal in this file
    is an identity that survives a `/settings` change.
    """
    import pathlib
    import re

    src = (pathlib.Path(__file__).resolve().parent.parent
           / "measurement.py").read_text(encoding="utf8")
    assert not re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z]\d\b", src), (
        "a GSTIN-shaped literal is in measurement.py")
    for state in ("Maharashtra", "Karnataka", "Gujarat", "Delhi"):
        assert state not in src, f"the State name {state!r} is in measurement.py"


# ═══════════════════════════════════════════════════════════════════════════
# THE REGISTER
# ═══════════════════════════════════════════════════════════════════════════

def test_the_register_lists_a_sheet_with_its_approval_state(client, seeded):
    li = priced(seeded, 1)[0]
    raise_sheet(client, seeded, [(li["line_id"], 1)])
    h = client.get("/measurement/").get_data(as_text=True)
    assert "SF/MS/26-27/0001" in h
    assert "AWAITING APPROVAL" in h

    _approve(only_sheet())
    assert "APPROVED" in client.get("/measurement/").get_data(as_text=True)


def test_the_boq_page_offers_the_measurement_chip_on_the_tip(client, seeded):
    h = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert f"/measurement/create?boq={seeded}" in h
