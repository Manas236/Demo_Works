"""
The delivery challan's full edit — 2 November 2026, CLIENT_CHANGES.md §0
block of that date, Part 2 (lock 3) and Part 4 (the number on edit).

An UNBILLED challan is fully editable, lines included, on the create form's
picker (and from Excel); a challan billed on a live RA bill keeps its lines
locked — hidden on the form AND refused on the POST — while every other
field stays editable. The number moves forward only. Every change is logged
with the screen-only band; the print carries none and keeps its copy labels.
"""

import json

import pytest

import dcbill as DCB
from store import STORE
from test_challan import BID, _create, _only_dc, _payload, boq_tip  # noqa: F401


def _edit_form(**over):
    data = {"date": "2026-08-02", "dispatch_mode": "Transport", "dispatch_to": "Site",
            "consignee_name": "New Consignee", "consignee_addr": "Gate 2",
            "consignee_phone": "", "po_no": "PO-9", "po_date": "", "notes": "edited"}
    data.update(over)
    return data


def _bill_it(cid):
    STORE.setdefault("ra_bills", {})["rb1"] = {
        "id": "rb1", "ra_no": 3, "status": "issued", "boq_id": BID,
        DCB.SOURCE_KEY: [cid]}


@pytest.fixture()
def dc(client, boq_tip):
    STORE.setdefault("ra_bills", {}).clear()
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    yield _only_dc()
    STORE["ra_bills"].clear()


def test_an_unbilled_challans_lines_party_and_fields_change_and_print(client, dc):
    r = client.post(f"/dc/edit/{dc['id']}", data=_edit_form(
        dc_json=_payload(("bbbbbbbbbbbb", 4), ("dddddddddddd", 2))))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    items = [i for i in dc["items"] if not i.get("is_header")]
    assert [(i["line_id"], i["qty"]) for i in items] == [
        ("bbbbbbbbbbbb", 4.0), ("dddddddddddd", 2.0)]
    assert dc["consignee_name"] == "New Consignee" and dc["po_no"] == "PO-9"
    html = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "New Consignee" in html and "PO-9" in html
    assert "Butterfly valve" in html and "Flexible sprinkler drop" not in html
    for label in ("Original", "Duplicate", "Triplicate"):
        assert label in html, f"copy label {label} survives"
    assert "Edited after issue" not in html, "no band on paper"
    view = client.get(f"/dc/view/{dc['id']}").get_data(as_text=True)
    assert "Edited after issue" in view


def test_a_billed_challans_lines_are_locked_and_the_rest_is_not(client, dc):
    _bill_it(dc["id"])
    before = [dict(r) for r in dc["items"]]
    html = client.get(f"/dc/edit/{dc['id']}").get_data(as_text=True)
    assert 'id="c_bbbbbbbbbbbb"' not in html and "lock 3" in html
    r = client.post(f"/dc/edit/{dc['id']}", data=_edit_form(
        dc_json=_payload(("bbbbbbbbbbbb", 99))))
    assert r.status_code == 302
    assert dc["items"] == before, "a billed challan's lines moved"
    assert dc["consignee_name"] == "New Consignee", "the other fields still edit"


def test_the_number_moves_forward_only_and_is_never_reissued(client, dc):
    was = dc["ref"]
    r = client.post(f"/dc/edit/{dc['id']}", data=_edit_form(doc_no_seq="0"))
    assert r.status_code == 200 and dc["ref"] == was
    r = client.post(f"/dc/edit/{dc['id']}", data=_edit_form(doc_no_seq="70"))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert dc["ref"] != was and dc["ref"].endswith("70")
    assert any(e["field"] == "Challan No." for e in dc["edit_log"])
    import settings as SET
    assert int(SET.dc_series()["next_no"]) == 71


def test_a_stale_form_with_no_picker_leaves_the_lines_alone(client, dc):
    before = [dict(r) for r in dc["items"]]
    r = client.post(f"/dc/edit/{dc['id']}", data=_edit_form())
    assert r.status_code == 302 and dc["items"] == before
