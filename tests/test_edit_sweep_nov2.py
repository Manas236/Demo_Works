"""
The parity sweep — 2 November 2026, CLIENT_CHANGES.md §0 block of that date,
Part 2 (sweep) and Part 4 (the number on every edit route).

* Product inquiry: editable once converted (logged, band), rows MOVE, a line
  can be added FROM the BOQ, and the number moves forward only.
* Receipt: the number on edit, forward only.
* Proforma / tax invoice: their parent's lines are offered on the edit form.
"""

import json

from store import STORE
from test_po_full_edit import _a_draft, _convert, _rows, shop  # noqa: F401
from test_proforma_edit import _pi, pi  # noqa: F401
from test_receipts import make_bill, make_receipt, seeded  # noqa: F401


# ── Product inquiry ────────────────────────────────────────────────────────

def test_the_inquiry_edit_form_moves_rows_adds_from_the_boq_and_numbers(client, shop):
    d = _a_draft(client, shop)
    html = client.get(f"/po/edit/{d['id']}").get_data(as_text=True)
    assert "edMove(this,-1)" in html and 'id="ed-boq"' in html
    assert "+ Add from the BOQ" in html and 'name="doc_no_seq"' in html


def test_the_inquiry_saves_rows_in_posted_order(client, shop):
    d = _a_draft(client, shop)
    items = [i for i, r in enumerate(d["items"]) if not r.get("is_header")]
    body = _rows(d)
    for key in [k for k in body if k.startswith("it_") and isinstance(body[k], list)]:
        vals = body[key]
        vals[items[0]], vals[items[1]] = vals[items[1]], vals[items[0]]
    first_desc = d["items"][items[1]]["description"]
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    assert [r for r in d["items"] if not r.get("is_header")][0]["description"] == first_desc


def test_the_inquiry_number_moves_forward_only(client, shop):
    d = _a_draft(client, shop)
    was = d["ref"]
    r = client.post(f"/po/edit/{d['id']}", data=dict(_rows(d), doc_no_seq="0"))
    assert r.status_code == 200 and d["ref"] == was
    r = client.post(f"/po/edit/{d['id']}", data=dict(_rows(d), doc_no_seq="0050"))
    assert r.status_code == 302 and d["ref"].endswith("0050")


def test_a_converted_inquiry_edit_is_banded_on_screen(client, shop):
    d = _a_draft(client, shop)
    _convert(client, shop, d)
    r = client.post(f"/po/edit/{d['id']}", data=dict(_rows(d), notes="after conversion"))
    assert r.status_code == 302 and d["edit_log"]
    assert "Edited after issue" in client.get(f"/po/view/{d['id']}").get_data(as_text=True)
    assert "Edited after issue" not in client.get(f"/po/print/{d['id']}").get_data(as_text=True)


# ── Receipt ────────────────────────────────────────────────────────────────

def test_the_receipt_number_moves_forward_only_on_edit(client, seeded):
    rid = make_bill(seeded, 1)
    rc = make_receipt(rid, 100)
    rec = STORE["receipts"][rc]
    html = client.get(f"/receipt/edit/{rc}").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html
    form = {"date": rec["date"], "amount": "100", "mode": "neft",
            "instrument_ref": "UTR1", "instrument_date": rec["date"], "notes": ""}
    r = client.post(f"/receipt/edit/{rc}", data=dict(form, doc_no_seq="0040"))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert rec["ref"].endswith("/0040") and rec["number_override"]["to"] == rec["ref"]


# ── Proforma / tax invoice sources ─────────────────────────────────────────

def test_the_proforma_edit_offers_its_quotations_lines(client, pi):
    STORE["quotations"]["qsrc"] = {"id": "qsrc", "ref": "QT-0099", "line_items": [
        {"type": "item", "name": "Gate valve 80 NB", "part_no": "GV80", "hsn": "8481",
         "qty": 4.0, "unit": "Nos", "price": 900.0, "total": 3600.0, "depth": 0}]}
    pi["quotation_id"] = "qsrc"
    html = client.get(f"/proforma/edit/{pi['id']}").get_data(as_text=True)
    assert "Quotation QT-0099" in html and "Gate valve 80 NB" in html
    assert "+ Add picked line" in html
    STORE["quotations"].pop("qsrc", None)
