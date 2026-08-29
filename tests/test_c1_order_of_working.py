"""
CC-2 **C1** — the order of working, refused BY URL.

C1, in full:

    BoQ → Delivery Challan → RA-Supply
    BoQ → Measurement     → RA-Installation

    Supply is proven by a delivery challan. Installation is proven by a
    measurement.

    Today installation quantity is typed straight into the claim grid with
    nothing behind it. C2 closes that.

⚠ **C1 states a domain model and no enforcement mechanism.** That the refusal is
**by URL** rather than by a hidden button is B5's established rule applied here,
and it is ours. `/boq/view` does hide the two RA chips when the step in front of
them is missing — that is presentation, and this file is the gate. Every test
below requests the address directly.

⚠ **The two legs are NOT symmetrical, and the asymmetry is deliberate.** The
installation leg gets an ordering guard **and** a quantity ceiling
(`ra.overclaims()`), because CC-2 says the approved measurement *is* the source
of the quantity. The supply leg gets the ordering guard **alone**: CC-2 says a
challan proves the supply and says nothing about a quantity flowing from one to
the other — and deriving one would be the wrong rule anyway, because
`challan.BLOCK_OVER_DISPATCH` is False on purpose, so dispatch figures are not
guarded tightly enough to be a ceiling on somebody's money.

⚠ **The supply leg was UNWIRED before this pass.** Nothing outside `challan.py`
read `STORE["delivery_challans"]` — not `ra.py`, not the BOQ page, nothing.
`challan → ra` was, and still is, refused at AST level. The link C1 asks for did
not exist in either direction, and this file is the whole of it.
"""

import json

import pytest

import approval
import boq as BQ
import demo_data as DD
import measurement as MS
import ra
from store import STORE

# ⚠ `conftest.chain_ready()` is deliberately NOT imported. It exists so the
#   other eleven files can raise a bill without describing the chain, and using
#   it here would test the fixture rather than the guard. Everything below builds
#   its own state, one step at a time.


@pytest.fixture()
def seeded(client):
    """The demo schedule with NOTHING in front of it — no challan, no sheet."""
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    STORE.setdefault("delivery_challans", {}).clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    STORE.setdefault("delivery_challans", {}).clear()


def _lines(boq_id, n=None):
    rows = [li for li in STORE["boqs"][boq_id]["line_items"]
            if not li["is_header"] and li["total_qty"] > 0]
    return rows[:n] if n else rows


def _where(response) -> str:
    from urllib.parse import unquote_plus
    return unquote_plus(response.headers.get("Location", ""))


def _a_challan(boq_id, cid="c1-dc"):
    STORE.setdefault("delivery_challans", {})[cid] = {
        "id": cid, "ref": "54", "date": "2026-08-01", "boq_id": boq_id,
        "boq_ref": "SF/BOQ/26-27/0001", "items": []}
    return cid


def _a_sheet(boq_id, mid="c1-ms", approved=True, qty=None):
    items = [{"line_id": li["line_id"], "item_no": li["item_no"],
              "description": li["description"], "unit": li["unit"],
              "is_header": False,
              "qty": float(li["total_qty"]) if qty is None else qty,
              "boq_qty": float(li["total_qty"])}
             for li in _lines(boq_id)]
    STORE.setdefault("measurements", {})[mid] = {
        "id": mid, "ref": "SF/MS/26-27/0001", "fy": "26-27",
        "date": "2026-08-01", "boq_id": boq_id, "items": items,
        "created_by": "somebody-else",
        "approval_status": approval.APPROVED if approved else approval.PENDING}
    return mid


def _claim(boq_id, leg, qty=1.0):
    li = _lines(boq_id, 1)[0]
    rate = li["supply_rate"] if leg == "supply" else li["install_rate"]
    return json.dumps({"lines": [{"line_id": li["line_id"], "qty": str(qty),
                                  "rate": str(rate)}]})


# ═══ 1. THE INSTALLATION LEG ═══════════════════════════════════════════════

def test_the_installation_form_is_refused_at_its_URL_with_no_measurement(
        client, seeded):
    r = client.get(f"/ra/create?boq={seeded}&leg=installation",
                   follow_redirects=False)
    assert r.status_code in (302, 303), (
        "the installation claim grid rendered with no measurement behind it — "
        "C1's whole sentence is that installation is proven by a measurement")
    assert "measurement" in _where(r).lower()
    assert f"/boq/view/{seeded}" in _where(r)


def test_the_installation_POST_is_refused_at_its_URL_too(client, seeded):
    """
    ⚠ **The half that matters.** A GET refusal with an open POST is not a gate —
    the form can be built by hand and posted. Nothing must be written.
    """
    r = client.post(f"/ra/create?boq={seeded}&leg=installation", data={
        "date": "2026-08-06", "ra_json": _claim(seeded, "installation")},
        follow_redirects=False)
    assert r.status_code in (302, 303)
    assert not STORE["ra_bills"], (
        "an installation bill was written by POSTing straight past the refused "
        "form — the guard is on the GET only, which is not a guard")


def test_a_PENDING_measurement_does_not_open_the_installation_form(client, seeded):
    """
    CC-2's own word: *"**Approved** measurements become the source."* An
    unapproved sheet is a number somebody typed, which is precisely the state C2
    exists to replace.
    """
    _a_sheet(seeded, approved=False)
    r = client.get(f"/ra/create?boq={seeded}&leg=installation",
                   follow_redirects=False)
    assert r.status_code in (302, 303)


def test_a_REJECTED_measurement_does_not_open_it_either(client, seeded):
    _a_sheet(seeded, approved=False)
    STORE["measurements"]["c1-ms"]["approval_status"] = approval.REJECTED
    r = client.get(f"/ra/create?boq={seeded}&leg=installation",
                   follow_redirects=False)
    assert r.status_code in (302, 303)


def test_an_APPROVED_measurement_opens_the_installation_form(client, seeded):
    _a_sheet(seeded, approved=True)
    r = client.get(f"/ra/create?boq={seeded}&leg=installation")
    assert r.status_code == 200, "the chain is complete and the claim is refused"


def test_a_measurement_on_an_EARLIER_revision_still_counts(client, seeded):
    """
    Chain-scoped, not record-scoped. A revision is a new BOQ record, so a
    per-record answer would report "no measurement" the moment a schedule was
    revised — silently, and only on the projects that have been revised.
    """
    _a_sheet(seeded, approved=True)
    STORE["boqs"]["rev1"] = dict(STORE["boqs"][seeded], id="rev1", rev_no=1,
                                 supersedes=seeded, ref="SF/BOQ/26-27/0002")
    r = client.get("/ra/create?boq=rev1&leg=installation")
    assert r.status_code == 200, (
        "revising the schedule threw away the measurement behind it")


# ═══ 2. THE SUPPLY LEG ═════════════════════════════════════════════════════

def test_the_supply_form_is_refused_at_its_URL_with_no_challan(client, seeded):
    r = client.get(f"/ra/create?boq={seeded}&leg=supply", follow_redirects=False)
    assert r.status_code in (302, 303), (
        "the supply claim grid rendered with no challan behind it — C1's "
        "sentence is that supply is proven by a delivery challan")
    assert "challan" in _where(r).lower()


def test_the_supply_POST_is_refused_at_its_URL_too(client, seeded):
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06", "ra_json": _claim(seeded, "supply")},
        follow_redirects=False)
    assert r.status_code in (302, 303)
    assert not STORE["ra_bills"]


def test_a_challan_opens_the_supply_form(client, seeded):
    _a_challan(seeded)
    assert client.get(f"/ra/create?boq={seeded}&leg=supply").status_code == 200


def test_a_challan_needs_no_approval_and_that_is_deliberate(client, seeded):
    """
    ⚠ **The asymmetry, asserted.** A challan is not an approvable document —
    `approval.DOCUMENTS` names four and now five, and the challan is on none of
    them. C1 says supply is *proven* by a challan; it does not say the challan is
    approved, and B6 does not put one on any ladder. Requiring an approval that
    nothing in the system can grant would make the supply leg unusable.
    """
    assert "challan" not in approval.DOCUMENTS
    _a_challan(seeded)
    assert client.get(f"/ra/create?boq={seeded}&leg=supply").status_code == 200


def test_a_challan_on_an_EARLIER_revision_still_counts(client, seeded):
    _a_challan(seeded)
    STORE["boqs"]["rev1"] = dict(STORE["boqs"][seeded], id="rev1", rev_no=1,
                                 supersedes=seeded, ref="SF/BOQ/26-27/0002")
    assert client.get("/ra/create?boq=rev1&leg=supply").status_code == 200


# ═══ 3. THE LEGS DO NOT SATISFY EACH OTHER ═════════════════════════════════

def test_a_challan_does_not_open_the_INSTALLATION_form(client, seeded):
    """
    Two chains, not one. Material dispatched proves nothing about work done —
    and this is the failure a single "has something happened on this project"
    check would produce.
    """
    _a_challan(seeded)
    r = client.get(f"/ra/create?boq={seeded}&leg=installation",
                   follow_redirects=False)
    assert r.status_code in (302, 303)


def test_a_measurement_does_not_open_the_SUPPLY_form(client, seeded):
    _a_sheet(seeded, approved=True)
    r = client.get(f"/ra/create?boq={seeded}&leg=supply", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_both_steps_open_both_legs(client, seeded):
    _a_challan(seeded)
    _a_sheet(seeded, approved=True)
    for leg in ("supply", "installation"):
        assert client.get(f"/ra/create?boq={seeded}&leg={leg}").status_code == 200


# ═══ 4. HIDING THE CHIP IS NOT THE GATE ════════════════════════════════════

def test_the_boq_page_hides_a_chip_whose_step_is_missing(client, seeded):
    """
    Presentation. It stops somebody clicking into a refusal they could have been
    spared; it is **not** what refuses them, and the tests above are.
    """
    h = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "/ra/create?boq=" not in h
    assert f"/measurement/create?boq={seeded}" in h, (
        "the way to satisfy the chain is not offered on the page that refuses "
        "it, so the refusal is a dead end")
    assert f"/dc/create?boq={seeded}" in h


def test_each_chip_appears_as_its_own_step_lands(client, seeded):
    _a_challan(seeded)
    h = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "leg=supply" in h and "leg=installation" not in h

    _a_sheet(seeded, approved=True)
    h = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "leg=supply" in h and "leg=installation" in h


def test_a_hidden_chip_is_still_a_typeable_address(client, seeded):
    """
    ⚠ **B5's rule, stated once here so it cannot be forgotten.** The chip being
    absent from the page above proves nothing about access. The address is
    refused because `ra._c1_refusal()` refuses it, and if that function were
    deleted every test in section 1 and 2 of this file would pass on a hidden
    button.
    """
    h = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "leg=installation" not in h
    r = client.get(f"/ra/create?boq={seeded}&leg=installation",
                   follow_redirects=False)
    assert r.status_code in (302, 303), (
        "the chip is hidden and the URL is open — that is the exact shape B5 "
        "exists to prevent")


# ═══ 5. WHAT THE GUARD DOES **NOT** DO ═════════════════════════════════════

def test_an_existing_bill_is_not_retrospectively_broken(client, seeded):
    """
    ⚠ **The guard is on raising a NEW claim.** A bill that already exists keeps
    its typed quantity and goes on rendering — that is the whole of the
    pre-measurement exception, and widening this to an existing record is how it
    would strand live bills. `tests/test_measurement_pin.py` closes the other
    end.
    """
    li = _lines(seeded, 1)[0]
    STORE["ra_bills"]["old-1"] = {
        "id": "old-1", "ref": "SF/RA/26-27/0001", "fy": "26-27", "ra_no": 1,
        "date": "2026-08-06", "boq_id": seeded, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "leg": "installation",
        "claims": [ra.build_claim(li, 1.0, 100.0, 0.0, 100.0)],
        "claim_subtotal": 100.0, "deductions": [], "deduction_total": 0.0,
        "net_payable": 100.0, "grand_total": 100.0,
        "status": "issued", "issued_on": "2026-08-06", "cancelled_on": "",
        "cancel_reason": "", "notes": "", "created_at": "2026-08-06 10:00",
        "created_by": "somebody-else", "approval_status": approval.APPROVED,
        MS.PRE_MEASUREMENT_FIELD: True}

    assert client.get("/ra/view/old-1").status_code == 200
    assert client.get("/ra/print/old-1").status_code == 200
    assert client.get("/ra/").status_code == 200


def test_the_register_and_the_picker_are_not_gated(client, seeded):
    """
    C1 gates raising a claim, not reading one. `/ra/` and the BOQ picker at
    `/ra/create` with no `boq` are both open — refusing them would hide the
    register from somebody whose projects happen to be incomplete.
    """
    assert client.get("/ra/").status_code == 200
    assert client.get("/ra/create").status_code == 200


def test_the_supply_leg_gets_NO_quantity_ceiling_from_the_challan(client, seeded):
    """
    The asymmetry again, this time in the arithmetic. A challan that dispatched
    one unit must not cap a supply claim, because `challan.BLOCK_OVER_DISPATCH`
    is False and over-dispatch is a warning — so dispatch figures are not
    guarded tightly enough to be a ceiling on somebody's money.
    """
    li = next(x for x in _lines(seeded) if x["total_qty"] >= 4)
    STORE.setdefault("delivery_challans", {})["c1-dc"] = {
        "id": "c1-dc", "ref": "54", "date": "2026-08-01", "boq_id": seeded,
        "items": [{"line_id": li["line_id"], "is_header": False, "qty": 1.0}]}

    claim = [{"line_id": li["line_id"], "item_no": li["item_no"],
              "qty": float(li["total_qty"])}]
    assert ra.overclaims(seeded, "supply", claim) == [], (
        "the challan capped a supply claim — CC-2 puts no quantity on that "
        "arrow and the dispatch figure is a warning, not a guard")


def test_challan_exists_is_the_only_thing_ra_asks_of_a_challan():
    """
    ⚠ **`ra.py` does not import `challan.py`, and C1 did not change that.** The
    supply guard asks one question and answers it with a dict lookup — the
    one-way trick used between boq/ra, boq/challan and ra/receipt.
    `tests/test_import_directions.py` refuses the edge at AST level in both
    directions; this asserts the shape of what replaced it.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "ra.py").read_text(encoding="utf8")
    assert "import challan" not in src
    assert 'STORE.get("delivery_challans")' in src
