"""
Editing a quotation — the fifth narrow unfreeze of `quotation.py` ("Manas,
31 Oct 2026: quotation editable (28 Oct all-documents ask)", CLIENT_CHANGES.md
§0 sixty-fourth block). Every field; ONE tax per quotation; a proforma already
raised keeps its own copy; every change logged; band on screen only.
"""

import json

import pytest

import editlog as EL
import lineedit as LE
from store import STORE


def _q():
    q = {"id": "qe1", "ref": "QT-0007", "date": "2026-10-01", "validity_days": "30",
         "account_name": "Acme", "contact_person": "Ravi", "bill_addr": "Plot 4",
         "bill_city": "Pune", "bill_state": "Maharashtra", "bill_pin": "411001",
         "bill_country": "India", "bill_phone": "", "bill_gstin": "27AAAAA0000A1Z5",
         "ship_same": "1", "tax_type": "cgst_sgst", "cgst_rate": 9.0, "sgst_rate": 9.0,
         "igst_rate": 0.0, "vat_rate": 0.0,
         "line_items": [{"type": "item", "name": "Pump", "part_no": "P1", "hsn": "8413",
                         "qty": 2.0, "unit": "Nos", "price": 1000.0, "total": 2000.0,
                         "depth": 0}],
         "subtotal": 2000.0, "tax_info": {"CGST": 180.0, "SGST": 180.0, "total": 360.0,
                                          "cgst_rate": 9.0, "sgst_rate": 9.0},
         "grand_total": 2360.0, "round_off": 0.0, "round_off_on": False, "total_qty": 2.0,
         "to": "Acme\nAttn: Ravi\nPlot 4\nPune, Maharashtra – 411001\nGSTIN: 27AAAAA0000A1Z5",
         "selections": [], "payment_terms": "", "delivery_terms": "",
         "dispatch_through": "", "incoterms": ""}
    STORE["quotations"]["qe1"] = q
    import pipeline as P
    P.ensure_fields(q)
    return q


def _form(q, rows=None, **over):
    rows = rows if rows is not None else LE.rows_for_form(q["line_items"], 0.0)
    d = {k: str(q.get(k) or "") for k in (
        "date", "validity_days", "account_name", "contact_person", "bill_addr",
        "bill_city", "bill_state", "bill_pin", "bill_country", "bill_gstin")}
    d.update({"ship_same": "1", "tax_type": q["tax_type"], "cgst_rate": "9",
              "sgst_rate": "9", "round_off_form": "1", LE.FIELD: json.dumps(rows)})
    d.update(over)
    return d


@pytest.fixture()
def q(client):
    STORE["quotations"].clear()
    return _q()


def test_the_view_offers_edit(client, q):
    assert "/quotation/edit/qe1" in client.get("/quotation/view/qe1").get_data(as_text=True)


def test_lines_party_and_tax_are_saved_and_the_address_recomposed(client, q):
    rows = LE.rows_for_form(q["line_items"], 0.0)
    rows[0]["discount_pct"] = "10"
    rows[0]["make"] = "Kirloskar"
    rows.append({"name": "Gasket", "qty": "4", "unit": "Nos", "price": "25",
                 "is_header": False})
    r = client.post("/quotation/edit/qe1", data=_form(q, rows, bill_city="Mumbai",
                                                      tax_type="igst", igst_rate="18",
                                                      cgst_rate="", sgst_rate=""))
    assert r.status_code == 302
    q = STORE["quotations"]["qe1"]
    assert [l["name"] for l in q["line_items"]] == ["Pump", "Gasket"]
    assert q["line_items"][0]["total"] == 1800.0
    assert "gst_rate" not in q["line_items"][0]          # ONE tax per quotation
    assert q["subtotal"] == 1900.0 and q["tax_info"]["IGST"] == 342.0
    assert q["grand_total"] == 2242.0
    assert "Mumbai, Maharashtra" in q["to"]
    html = client.get("/quotation/view/qe1").get_data(as_text=True)
    assert "Make: Kirloskar" in html and "Discount 10%" in html
    assert "Edited after issue on" in html
    assert html.index("Edited after issue on") < html.index('<div class="doc-outer">')


def test_a_proforma_already_raised_keeps_its_copy(client, q):
    r = client.post("/proforma/from/qe1", data={"date": "2026-10-02", "advance_pct": "100"})
    assert r.status_code == 302
    pi = next(iter(STORE["proformas"].values()))
    before = json.dumps(pi, sort_keys=True)
    rows = LE.rows_for_form(q["line_items"], 0.0)
    rows[0]["qty"] = "9"
    client.post("/quotation/edit/qe1", data=_form(q, rows))
    assert STORE["quotations"]["qe1"]["line_items"][0]["qty"] == 9.0
    assert json.dumps(pi, sort_keys=True) == before


def test_an_unchanged_save_logs_nothing(client, q):
    client.post("/quotation/edit/qe1", data=_form(q))
    assert EL.FIELD not in STORE["quotations"]["qe1"]
