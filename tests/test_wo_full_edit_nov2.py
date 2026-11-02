"""
The work order's full edit — 2 November 2026, CLIENT_CHANGES.md §0 block of
that date, Part 2 (and Part 4, the number on edit).

Editable at every status but Cancelled; every line column, lines added (free
text, headings, Excel), removed and MOVED; the material/labour rates, the GST
%, the site and the T&C; after ISSUE every change is logged with the
screen-only band, the print carries none; a Draft edit is not logged; the
number moves forward only.
"""

import pytest

import workorder as W
from store import STORE
from test_work_orders import _clean_wo, _create, _lines  # noqa: F401


def _edit(client, wid, *rows, **over):
    wo = STORE["work_orders"][wid]
    data = {"date": wo["date"], "contractor_id": "", "contractor_name": "Ravi",
            "contractor_gstin": "", "contractor_addr": "Pune", "project_id": "",
            "notes": "", "tracks": "both", "gst_rate": "18", "site": "Tower B",
            "terms": "Pay in 30 days"}
    data.update(_lines(*rows))
    data.update(over)
    return client.post(f"/wo/edit/{wid}", data=data)


def test_an_issued_work_order_is_fully_edited_logged_and_printed(client):
    wid = _create(client)
    client.post(f"/wo/issue/{wid}", data={"issued_on": "2026-10-07"})
    wo = STORE["work_orders"][wid]
    ids = [li["line_id"] for li in wo["lines"]]
    # Reordered (second first), every column changed, the first removed and a
    # new free-text line added; the party, GST, site and T&C changed too.
    r = _edit(client, wid,
              ("2", "Moved and renamed", "Mtr", "7", "120", "45", ids[1]),
              ("3", "A new line", "Nos", "2", "500", "50"),
              contractor_name="Anil Contractor")
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    descs = [li["description"] for li in wo["lines"]]
    assert descs == ["Moved and renamed", "A new line"]
    assert wo["lines"][0]["line_id"] == ids[1] and wo["gst_rate"] == 18.0
    assert wo["site"] == "Tower B" and wo["terms"] == "Pay in 30 days"
    assert wo["contractor_name"] == "Anil Contractor"
    fields = {e["field"] for e in wo["edit_log"]}
    assert {"Contractor", "Site", "GST %", "Terms & conditions"} <= fields
    assert any(f.startswith("Line ") for f in fields)
    printed = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert "Moved and renamed" in printed and "A new line" in printed
    assert "Anil Contractor" in printed and "Edited after issue" not in printed
    view = client.get(f"/wo/view/{wid}").get_data(as_text=True)
    assert "Edited after issue" in view


def test_a_draft_edit_is_not_logged(client):
    wid = _create(client)
    r = _edit(client, wid, ("1", "Only line", "Nos", "1", "10", "1"))
    assert r.status_code == 302
    assert "edit_log" not in STORE["work_orders"][wid]


def test_a_cancelled_work_order_is_locked(client):
    wid = _create(client)
    client.post(f"/wo/cancel/{wid}", data={"cancel_reason": "wrong contractor"})
    assert STORE["work_orders"][wid]["status"] == "cancelled"
    r = _edit(client, wid, ("1", "x", "Nos", "1", "1", "1"))
    assert r.status_code == 302 and "cancelled" in r.headers["Location"]


def test_the_number_moves_forward_only_on_edit(client):
    wid = _create(client)
    wo = STORE["work_orders"][wid]
    was = wo["ref"]
    rows = [(li["item_no"], li["description"], li["unit"], str(li["qty"]),
             W.num_text(li.get("material_rate")), W.num_text(li.get("labour_rate")),
             li["line_id"]) for li in wo["lines"]]
    r = _edit(client, wid, *rows, doc_no_seq="0")
    assert r.status_code == 200 and wo["ref"] == was
    r = _edit(client, wid, *rows, doc_no_seq="0090")
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert wo["ref"].endswith("0090") and wo["number_override"]["from"] == was


def test_the_edit_form_offers_excel_and_move_buttons(client):
    wid = _create(client)
    html = client.get(f"/wo/edit/{wid}").get_data(as_text=True)
    assert f"/wo/import?wo={wid}" in html
    assert 'class="wo-mv"' in html and 'name="doc_no_seq"' in html
