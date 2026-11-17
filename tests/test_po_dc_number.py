"""
The PURCHASE ORDER and DELIVERY CHALLAN numbers, free format
(17 November 2026, CLIENT_CHANGES.md §0 eightieth block).

What this file holds:

  * a PO's number is set on create and changed afterwards through a
    NUMBER-ONLY save, on a Draft and on a non-draft order alike; a Cancelled
    order is locked; nothing else on a non-draft order moves;
  * a DC's number is set on create and changed on its edit form;
  * a duplicate is refused within the SAME type only (PO vs PO, DC vs DC),
    naming the holder; trimmed and case-insensitive;
  * the automatic counters never move backwards and free values do not
    corrupt them (the PO scan, the DC stored counter);
  * every change appends {old, new, by, at}, on the view page only;
  * a DC raised from a renumbered PO keeps its snapshot and the view says so.
"""

import json

import pytest
from werkzeug.datastructures import MultiDict

import series as SER
import settings as SET
import tinum as TN
from store import STORE

from tests.test_boq_to_po import VENDOR_ID, _pick, _post, shop  # noqa: F401
from tests.test_challan import BID, _create, _payload, boq_tip  # noqa: F401


def _po(client, shop, status="Draft", **over):
    r = _post(client, shop["boq"], [_pick(li, qty="5", rate="10") for li in shop["lines"][:1]],
              status=status, **over)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return STORE["purchases"][r.location.split("/purchase/view/")[1].split("?")[0]]


def _renumber(client, po, number):
    return client.post(f"/purchase/{po['id']}/update",
                       data={"number_only": "1", TN.DOC_FIELD: number})


# ── Purchase order ──────────────────────────────────────────────────────────

def test_a_po_takes_a_free_number_on_create_and_spends_no_series_number(shop, client):
    po = _po(client, shop, **{TN.DOC_FIELD: "  SAM/PO-77 "})
    assert po["ref"] == "SAM/PO-77"
    assert SER.next_seq("PO", po["fy"]) == 1, "a free value of another shape is not counted"
    nxt = _po(client, shop)
    assert nxt["ref"] == "SF/PO/26-27/0001"


def test_a_draft_and_an_issued_po_are_renumbered_by_the_number_only_save(shop, client):
    for status in ("Draft", "Issued", "Received"):
        po = _po(client, shop, status=status)
        was, lines = po["ref"], json.dumps(po["line_items"], sort_keys=True)
        view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
        assert 'name="number_only"' in view and f'name="{TN.DOC_FIELD}"' in view
        r = _renumber(client, po, f"V-{status}")
        assert r.status_code == 302 and po["ref"] == f"V-{status}"
        assert po["status"] == status, "the status did not move"
        assert json.dumps(po["line_items"], sort_keys=True) == lines, "nothing else moved"
        [h] = po[TN.NUMBER_HISTORY_KEY]
        assert (h["old"], h["new"]) == (was, f"V-{status}") and h["by"] and h["at"]
        page = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
        screen, sheet = page.split('class="doc-outer"', 1)
        assert f"V-{status}" in sheet and was not in sheet, "the print shows the new number"
        assert "Purchase order number changes" in screen
        assert "Purchase order number changes" not in sheet, "history is never printed"


def test_a_cancelled_po_is_locked(shop, client):
    po = _po(client, shop)
    po["status"] = "Cancelled"
    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert 'name="number_only"' not in view
    was = po["ref"]
    r = _renumber(client, po, "X-1")
    assert r.status_code == 302 and po["ref"] == was
    assert TN.NUMBER_HISTORY_KEY not in po


def test_po_duplicates_are_refused_within_pos_only(shop, client):
    a = _po(client, shop, **{TN.DOC_FIELD: "SAM-1"})
    b = _po(client, shop)
    r = _renumber(client, b, " sam-1 ")
    assert "already+on+Purchase+order+SAM-1" in r.location and b["ref"] != "SAM-1"
    r = _post(client, shop["boq"], [_pick(shop["lines"][0], qty="1", rate="1")],
              **{TN.DOC_FIELD: "Sam-1"})
    assert r.status_code == 200 and "already on Purchase order SAM-1" in r.get_data(as_text=True)
    # A DC holding the same number does NOT block a PO.
    STORE.setdefault("delivery_challans", {})["dc-x"] = {"id": "dc-x", "ref": "SHARED-9"}
    assert _renumber(client, b, "SHARED-9").status_code == 302 and b["ref"] == "SHARED-9"
    # A cancelled PO's number does not block.
    a["status"] = "Cancelled"
    c = _po(client, shop)
    assert _renumber(client, c, "SAM-1").status_code == 302 and c["ref"] == "SAM-1"


def test_the_po_counter_never_moves_back(shop, client):
    first = _po(client, shop)                       # SF/PO/26-27/0001
    _renumber(client, first, "SF/PO/26-27/0050")    # typed in the series' own shape
    assert SER.next_seq("PO", first["fy"]) == 51, "counted, so it is never re-minted"
    _renumber(client, first, "PO-A")                # renamed OUT of the shape
    assert SER.next_seq("PO", first["fy"]) == 51, (
        "renaming the highest number away must not let the minter go back")
    assert SER.floor_of("PO", first["fy"]) == 51, "held by the series floor"
    nxt = _po(client, shop)
    assert nxt["ref"] == "SF/PO/26-27/0051"
    SER.save_floor("PO", first["fy"], 0)      # leave no floor behind


def test_renaming_the_highest_ra_serial_to_tally_never_lowers_its_series(client):
    """The same guard on hotfix 4's tax invoice numbers (RI shown)."""
    import ra
    STORE.setdefault("ra_bills", {}).clear()
    STORE["ra_bills"]["r1"] = {"id": "r1", "ref": "SF/RA/26-27/0001", "ra_no": 1,
                               "fy": "26-27", "date": "2026-08-12", "status": "issued",
                               "tax_invoice_ref": "SF/RI/26-27/0007"}
    assert SER.next_seq("RI", "26-27") == 8
    data = {k: str(STORE["ra_bills"]["r1"].get(k) or "") for k, _l in ra.TEXT_FIELDS}
    data[TN.FIELD] = "SF-7"
    assert client.post("/ra/edit-text/r1", data=data).status_code == 302
    assert STORE["ra_bills"]["r1"]["tax_invoice_ref"] == "SF-7"
    assert SER.next_seq("RI", "26-27") == 8
    STORE["ra_bills"].clear()
    SER.save_floor("RI", "26-27", 0)


def test_a_dc_from_a_renumbered_po_keeps_its_snapshot(shop, client):
    import dcpo
    po = _po(client, shop, status="Issued")
    snap = po["ref"]
    md = [("date", "2026-11-17"), ("consignee_name", "Us"), ("pl_present", "1"),
          ("xi_present", "1")]
    for row in dcpo.lines_of(po):
        md += [("pl_key", row["key"]), ("pl_qty", "1"), ("pl_on", row["key"])]
    assert client.post(f"/dc/create?po={po['id']}", data=MultiDict(md)).status_code == 302
    dc = next(d for d in STORE["delivery_challans"].values() if d.get("source_po_id") == po["id"])
    _renumber(client, po, "NEW-PO-1")
    assert dc["source_po_ref"] == snap, "the snapshot is never rewritten"
    view = client.get(f"/dc/view/{dc['id']}").get_data(as_text=True)
    assert f"PO NEW-PO-1 (raised as {snap})" in view


# ── Delivery challan ────────────────────────────────────────────────────────

def test_a_dc_takes_a_free_number_on_create_and_edit(client, boq_tip):
    lid = STORE["boqs"][BID]["line_items"][1]["line_id"]
    r = _create(client, BID, _payload((lid, 1)), **{TN.DOC_FIELD: " DC/77-A "})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    dc = next(iter(STORE["delivery_challans"].values()))
    assert dc["ref"] == "DC/77-A"
    assert int(SET.dc_series()["next_no"]) == 1, "a free value of another shape spends nothing"
    form = client.get(f"/dc/edit/{dc['id']}").get_data(as_text=True)
    assert f'name="{TN.DOC_FIELD}"' in form
    data = {"date": dc["date"], "dispatch_mode": "Transport", "consignee_name": "Us",
            "consignee_addr": "", TN.DOC_FIELD: "DC-B", "doc_no_seq": "",
            "dc_json": _payload((lid, 1))}
    r = client.post(f"/dc/edit/{dc['id']}", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert dc["ref"] == "DC-B"
    [h] = dc[TN.NUMBER_HISTORY_KEY]
    assert (h["old"], h["new"]) == ("DC/77-A", "DC-B")
    view = client.get(f"/dc/view/{dc['id']}").get_data(as_text=True)
    assert "Challan number changes" in view
    pr = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "DC-B" in pr and "Challan number changes" not in pr


def test_dc_duplicates_are_refused_within_dcs_only(client, boq_tip):
    lid = STORE["boqs"][BID]["line_items"][1]["line_id"]
    _create(client, BID, _payload((lid, 1)), **{TN.DOC_FIELD: "D-1"})
    r = _create(client, BID, _payload((lid, 1)), **{TN.DOC_FIELD: "d-1 "})
    assert r.status_code == 200 and "already on Delivery challan D-1" in r.get_data(as_text=True)
    assert len(STORE["delivery_challans"]) == 1
    # A PO holding the number does not block a DC.
    STORE["purchases"]["po-x"] = {"id": "po-x", "ref": "P-SHARED", "status": "Issued"}
    try:
        assert _create(client, BID, _payload((lid, 1)), **{TN.DOC_FIELD: "P-SHARED"}).status_code == 302
    finally:
        STORE["purchases"].pop("po-x", None)


def test_the_dc_counter_moves_past_a_typed_number_in_its_own_shape(client, boq_tip):
    lid = STORE["boqs"][BID]["line_items"][1]["line_id"]
    SET.save_dc_series("", 10)
    _create(client, BID, _payload((lid, 1)), **{TN.DOC_FIELD: "60"})
    assert int(SET.dc_series()["next_no"]) == 61, "60 is never minted again"
    _create(client, BID, _payload((lid, 1)), **{TN.DOC_FIELD: "5"})
    assert int(SET.dc_series()["next_no"]) == 61, "never backwards"
    _create(client, BID, _payload((lid, 1)))
    refs = sorted(d["ref"] for d in STORE["delivery_challans"].values())
    assert "61" in refs and refs.count("60") == 1


def test_a_login_blocked_from_docnum_override_cannot_renumber(shop, client):
    import auth
    po = _po(client, shop)
    uid = "pn-director"
    STORE["users"][uid] = {"id": uid, "username": "pn@test", "display_name": "P",
                           "password_hash": "x", "role_ids": ["role-director"],
                           "active": True, "created_at": "2026-08-01 09:00",
                           "created_by": "test", auth.PERM_DENY_FIELD: ["docnum.override"]}
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = uid
    was = po["ref"]
    _renumber(client, po, "BLOCKED-1")
    assert po["ref"] == was
