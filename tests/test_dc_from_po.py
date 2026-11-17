"""
A Delivery Challan raised FROM a purchase order
(17 November 2026, CLIENT_CHANGES.md §0 seventy-eighth block).

What this file holds:

  * a BOQ-linked order gives a BOQ challan: its `boq_id`, the BOQ lines with
    their `line_id` kept, counted by RA-from-DC exactly as a BOQ challan's;
  * an order with no BOQ gives a no-BOQ challan, every line an extra, absent
    from the RA picker; an order's extra lines are always challan extras;
  * the default quantity is what is LEFT after the challans already raised from
    the order (derived by summing), a deleted challan frees it, and going over
    warns (amber) but saves;
  * nothing ticked is refused; a Cancelled order is refused at the route;
  * the consignee is never the order's vendor, and `po_no` / `po_date` are
    never filled from the order;
  * the PO view offers the button and lists what was dispatched, its print
    block unchanged; the P&L does not move.
"""

import json

import pytest
from werkzeug.datastructures import MultiDict

import dcpo
import pnl
import ra
import settings as SET
from store import STORE

from tests.test_boq_to_po import PROJECT_ID, VENDOR_ID, _pick, _post, shop  # noqa: F401


def _dcs():
    return STORE.setdefault("delivery_challans", {})


@pytest.fixture()
def boq_po(shop, client):
    """An Issued order from the BOQ — three BOQ lines and one extra line."""
    _dcs().clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)
    picked = shop["lines"][:3]
    r = _post(client, shop["boq"], [_pick(li, qty="10", rate="100") for li in picked],
              status="Issued", delivery_to="Site store, Whitefield",
              extra_desc="Teflon tape", extra_unit="Nos", extra_qty="20",
              extra_rate="5", extra_discount="", extra_hsn="", extra_make="",
              extra_image="")
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    po = next(iter(STORE["purchases"].values()))
    assert po["extra_lines"], "fixture: the order should carry an extra line"
    yield {"po": po, "lines": picked, "boq": shop["boq"]}
    _dcs().clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)


@pytest.fixture()
def noboq_po(boq_po):
    """The same order with its BOQ link cut — an order with no BOQ."""
    po = boq_po["po"]
    po["boq_id"], po["boq_ref"] = "", ""
    return boq_po


def _form(**over):
    d = {"date": "2026-11-17", "dispatch_mode": "Transport", "dispatch_to": "",
         "consignee_name": "Samruddhi Fire", "consignee_addr": "Site store",
         "consignee_phone": "", "po_no": "", "po_date": "", "notes": "",
         "pl_present": "1", "xi_present": "1"}
    d.update(over)
    return d


def _raise(client, po, picks, extras=(), **over):
    """`picks` = {key: qty or None (unticked)}; every order line is posted."""
    md = list(_form(**over).items())
    for r in dcpo.lines_of(po):
        q = picks.get(r["key"])
        md.append(("pl_key", r["key"]))
        md.append(("pl_qty", "" if q is None else str(q)))
        if q is not None:
            md.append(("pl_on", r["key"]))
    for d, q, u in extras:
        md += [("xi_desc", d), ("xi_qty", q), ("xi_unit", u), ("line_product_id", "")]
    return client.post(f"/dc/create?po={po['id']}", data=MultiDict(md))


def _keys(po, kind):
    return [r["key"] for r in dcpo.lines_of(po) if r["kind"] == kind]


# ── Entry points ────────────────────────────────────────────────────────────

def test_the_po_view_and_the_register_offer_a_dc_from_po(boq_po, client):
    po = boq_po["po"]
    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert f'href="/dc/create?po={po["id"]}"' in view and "Create DC" in view
    reg = client.get("/dc/").get_data(as_text=True)
    assert 'href="/dc/create?frompo=1"' in reg and "DC from PO" in reg
    chooser = client.get("/dc/create?frompo=1").get_data(as_text=True)
    assert po["ref"] in chooser and f"/dc/create?po={po['id']}" in chooser


def test_a_cancelled_po_is_refused_and_offers_no_button(boq_po, client):
    po = boq_po["po"]
    po["status"] = "Cancelled"
    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert f"/dc/create?po={po['id']}" not in view
    assert po["ref"] not in client.get("/dc/create?frompo=1").get_data(as_text=True)
    r = client.get(f"/dc/create?po={po['id']}")
    assert r.status_code == 302 and "Cancelled" in r.location
    r = _raise(client, po, {k: 1 for k in _keys(po, "boq")})
    assert r.status_code == 302 and not _dcs()


# ── The form ────────────────────────────────────────────────────────────────

def test_the_form_never_prefills_the_vendor_and_never_fills_po_no(boq_po, client):
    po = boq_po["po"]
    html = client.get(f"/dc/create?po={po['id']}").get_data(as_text=True)
    assert 'name="consignee_name"\n                 value=""' in html
    assert "Site store, Whitefield" in html, "the order's delivery address prefills"
    assert po["vendor_name"] not in html.split('name="consignee_name"')[1][:300]
    assert 'id="po_no" name="po_no"' in html and po["ref"] not in html.split('name="po_no"')[1][:120]
    # Every order line is a ticked row; no rate anywhere in the picker.
    assert html.count('name="pl_on"') == len(dcpo.lines_of(po))
    boxes = html.split('name="pl_on"')[1:]
    assert all('"checked' in b[:80] or ' checked' in b[:80] for b in boxes), "every row arrives ticked"
    picker = html.split("Lines going out")[1].split("</table>")[0]
    assert "Rate" not in picker and "100.00" not in picker


def test_nothing_ticked_is_refused(boq_po, client):
    r = _raise(client, boq_po["po"], {})
    assert r.status_code == 200 and "No lines are ticked" in r.get_data(as_text=True)
    assert not _dcs()


# ── Linkage ─────────────────────────────────────────────────────────────────

def test_a_boq_po_gives_a_boq_challan_counted_by_ra_from_dc(boq_po, client):
    po, lines = boq_po["po"], boq_po["lines"]
    keys = _keys(po, "boq")
    r = _raise(client, po, {keys[0]: 4, keys[1]: 6, _keys(po, "extra")[0]: 5})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    dc = next(iter(_dcs().values()))
    assert dc["boq_id"] == boq_po["boq"]
    assert (dc["source_po_id"], dc["source_po_ref"]) == (po["id"], po["ref"])
    assert dc["po_no"] == "" and dc["po_date"] == "", "never filled from the order"
    rows = [x for x in dc["items"] if not x.get("is_header")]
    assert [x["line_id"] for x in rows[:2]] == [lines[0]["line_id"], lines[1]["line_id"]]
    assert [x["qty"] for x in rows[:2]] == [4.0, 6.0]
    assert rows[2]["extra"] and rows[2]["line_id"] is None and rows[2]["description"] == "Teflon tape"
    # RA-from-DC sees it exactly as a BOQ challan.
    on_chain = [cid for cid, _ in ra.challans_on_chain(boq_po["boq"])]
    assert dc["id"] in on_chain
    assert ra.dispatched_in([dc]) == {lines[0]["line_id"]: 4.0, lines[1]["line_id"]: 6.0}
    # The print is the challan's own rows, and carries no rate.
    pr = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "Teflon tape" in pr and "100.00" not in pr


def test_a_no_boq_po_gives_a_no_boq_challan_of_extras(noboq_po, client):
    po = noboq_po["po"]
    assert not _keys(po, "boq"), "no BOQ, so no BOQ-linked keys"
    keys = [r["key"] for r in dcpo.lines_of(po)]
    r = _raise(client, po, {k: 1 for k in keys}, project_id=PROJECT_ID)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    dc = next(iter(_dcs().values()))
    assert dc["boq_id"] is None
    assert all(x["extra"] and x["line_id"] is None for x in dc["items"])
    assert dc["project_id"] == PROJECT_ID
    assert dc["id"] not in [cid for cid, _ in ra.challans_on_chain(noboq_po["boq"])]
    page = client.get(f"/projects/view/{PROJECT_ID}").get_data(as_text=True)
    assert f"/dc/view/{dc['id']}" in page


def test_extras_can_be_added_on_top(boq_po, client):
    po = boq_po["po"]
    r = _raise(client, po, {_keys(po, "boq")[0]: 1}, extras=[("Spare gasket", "2", "Nos")])
    assert r.status_code == 302
    dc = next(iter(_dcs().values()))
    assert dc["items"][-1]["description"] == "Spare gasket"
    assert "po_key" not in dc["items"][-1], "a hand-added extra is on no order line"


# ── The remainder ───────────────────────────────────────────────────────────

def test_partial_dispatch_leaves_the_remainder_across_two_challans(boq_po, client):
    po = boq_po["po"]
    k = _keys(po, "boq")[0]
    assert _raise(client, po, {k: 4}).status_code == 302
    assert dcpo.remaining_by_key(po)[k] == 6.0
    html = client.get(f"/dc/create?po={po['id']}").get_data(as_text=True)
    row = html.split(f'value="{k}"')[2]
    assert 'name="pl_qty" value="6"' in row, "the default is what is left"
    assert _raise(client, po, {k: 6}).status_code == 302
    assert dcpo.remaining_by_key(po)[k] == 0.0
    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Dispatched on DCs" in view
    for dc in _dcs().values():
        assert f"/dc/view/{dc['id']}" in view


def test_a_deleted_challan_frees_its_quantity(boq_po, client):
    po = boq_po["po"]
    k = _keys(po, "boq")[0]
    _raise(client, po, {k: 7})
    cid = next(iter(_dcs()))
    assert dcpo.remaining_by_key(po)[k] == 3.0
    assert client.post(f"/dc/delete/{cid}").status_code in (302, 303)
    assert dcpo.remaining_by_key(po)[k] == 10.0
    # And a challan marked cancelled (no such state today) is skipped too.
    _raise(client, po, {k: 7})
    next(iter(_dcs().values()))["status"] = "cancelled"
    assert dcpo.remaining_by_key(po)[k] == 10.0


def test_going_over_the_remainder_warns_and_saves(boq_po, client):
    po = boq_po["po"]
    k = _keys(po, "boq")[0]
    r = _raise(client, po, {k: 15})
    assert r.status_code == 302 and "exceeds+the+order" in r.location
    dc = next(iter(_dcs().values()))
    assert dc["items"][-1]["qty"] == 15.0 or any(x.get("qty") == 15.0 for x in dc["items"])
    view = client.get(f"/dc/view/{dc['id']}").get_data(as_text=True)
    assert "More has gone out than purchase order" in view
    pr = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "More has gone out than purchase order" not in pr, "screen only"


def test_an_edit_keeps_each_rows_order_line(boq_po, client):
    po = boq_po["po"]
    kb, kx = _keys(po, "boq")[0], _keys(po, "extra")[0]
    _raise(client, po, {kb: 2, kx: 3})
    dc = next(iter(_dcs().values()))
    edit = client.get(f"/dc/edit/{dc['id']}").get_data(as_text=True)
    assert f'name="xi_ref" value="{kx}"' in edit
    lid = boq_po["lines"][0]["line_id"]
    md = list(_form(doc_no_seq=dc["ref"],
                    dc_json=json.dumps({"lines": [{"line_id": lid, "qty": "5"}]})).items())
    md += [("xi_desc", "Teflon tape"), ("xi_qty", "4"), ("xi_unit", "Nos"),
           ("line_product_id", ""), ("xi_ref", kx)]
    r = client.post(f"/dc/edit/{dc['id']}", data=MultiDict(md))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    sent = dcpo.dispatched_by_key(po["id"])
    assert sent == {kb: 5.0, kx: 4.0}
    # A crafted ref naming no line of this order is dropped.
    md[-1] = ("xi_ref", "X:999")
    client.post(f"/dc/edit/{dc['id']}", data=MultiDict(md))
    assert kx not in dcpo.dispatched_by_key(po["id"])


# ── The P&L ─────────────────────────────────────────────────────────────────

def test_the_pnl_does_not_move(boq_po, client):
    po = boq_po["po"]
    before = pnl.project_pnl(PROJECT_ID)
    _raise(client, po, {k: 1 for k in [r["key"] for r in dcpo.lines_of(po)]})
    assert _dcs()
    assert pnl.project_pnl(PROJECT_ID) == before, "a challan carries no money"
