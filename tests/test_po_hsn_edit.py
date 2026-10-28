"""
HSN on an existing purchase order's ITEM lines, on the reprice form
(28 October 2026).

The rule is the 26 October 2026 ruling for documents already created —
"fill blanks only, an HSN already printed is never overwritten" — read with
the line `/purchase/edit` already draws for the document number: a **Draft**
order has not gone to a vendor, so any HSN on it is ours to change; from
**Issued** onward only a BLANK HSN may be filled.

⚠ No assertion here passes against a blank page: each names an HSN that only
  appears when the feature worked, or a refusal sentence.
"""

import pytest

from store import STORE
from test_po_make import (  # noqa: F401 — fixtures and helpers reused as-is
    ORDER, _po_from_boq, _reprice_form, shop)


def _set_status(po, status):
    po["status"] = status


def test_the_reprice_form_draws_an_hsn_box_per_item_line(client, shop):
    po, rows = _po_from_boq(client, shop)
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert page.count('<input type="text" name="line_hsn"') == len(rows) == 2
    assert "<span>Item</span><span>Make</span><span>HSN</span><span>Qty</span>" in page
    assert 'class="form-section rp-hsn"' in page


def test_a_draft_order_takes_any_hsn_and_the_change_prints(client, shop):
    po, rows = _po_from_boq(client, shop)
    rows[0]["hsn"] = "84818030"
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_hsn=["73072900", "84813000"]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert "HSN+updated+on+2+lines" in r.headers["Location"]
    assert rows[0]["hsn"] == "73072900" and rows[1]["hsn"] == "84813000"
    assert any("HSN updated" in str(h.get("note", ""))
               for h in po.get("status_history") or [])
    assert not po.get("reprice_log"), "an HSN is not a rate"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "73072900" in html and "84813000" in html


def test_an_issued_order_fills_a_blank_hsn(client, shop):
    po, rows = _po_from_boq(client, shop)
    rows[0]["hsn"] = ""
    rows[1]["hsn"] = "84818030"
    _set_status(po, "Issued")
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    # The printed one is read-only, the blank one is not.
    assert page.count("readonly title=\"Already printed") == 1
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_hsn=["73072900", "84818030"]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert rows[0]["hsn"] == "73072900" and rows[1]["hsn"] == "84818030"


def test_an_issued_order_refuses_to_overwrite_a_printed_hsn(client, shop):
    po, rows = _po_from_boq(client, shop)
    rows[0]["hsn"] = "84818030"
    _set_status(po, "Issued")
    before = [r.get("price") for r in rows]
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_rate=["999.00", "999.00"], line_hsn=["11111111", ""]))
    assert r.status_code == 200
    assert "already printed as 84818030" in r.get_data(as_text=True)
    assert rows[0]["hsn"] == "84818030"
    assert [r.get("price") for r in rows] == before, "nothing written on a refusal"


def test_a_stale_form_without_hsn_boxes_keeps_every_hsn(client, shop):
    po, rows = _po_from_boq(client, shop)
    rows[0]["hsn"] = "84818030"
    client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(rows))
    assert rows[0]["hsn"] == "84818030"


def test_an_hsn_list_of_the_wrong_length_is_refused(client, shop):
    po, rows = _po_from_boq(client, shop)
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_hsn=["73072900"]))
    assert r.status_code == 200
    assert "That order has changed since this form was opened" in r.get_data(as_text=True)


def test_hsn_is_capped_and_escaped(client, shop):
    po, rows = _po_from_boq(client, shop)
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_hsn=["<b>12345678999", ""]))
    assert r.status_code == 302
    assert rows[0]["hsn"] == "<b>12345"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "<b>12345" not in html and "&lt;b&gt;12345" in html
