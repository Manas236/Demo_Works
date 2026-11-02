"""
Editing an ISSUED standalone tax invoice — CLIENT_CHANGES.md §0 sixty-fourth
block, Part 2 (Manas, 31 Oct 2026: "editable, number locked").

1. every field is editable except the number, which is not even posted;
2. the date may move only within the number's financial year;
3. every change is logged (who, when, field, before → after) and the amber
   band is on screen only — the print carries none;
4. a cancelled invoice is locked, on the GET and on the POST.
"""

import json

import pytest

import editlog as EL
import lineedit as LE
from store import STORE


def _ti(**over):
    ti = {
        "id": "te1", "ref": "SF/TI/26-27/0005", "fy": "26-27", "date": "2026-10-02",
        "proforma_id": "", "proforma_ref": "PI-0001", "quotation_id": "", "quotation_ref": "",
        "account_name": "Acme", "contact_person": "Ravi", "to": "Acme Ltd\nPune",
        "bill_gstin": "27AAAAA0000A1Z5", "ship_same": "1", "ship_acct_name": "",
        "ship_addr": "", "ship_city": "", "ship_state": "", "ship_pin": "",
        "ship_phone": "", "ship_gstin": "",
        "line_items": [{"type": "item", "name": "Pump", "part_no": "P1", "hsn": "8413",
                        "qty": 2.0, "unit": "Nos", "price": 1000.0, "total": 2000.0,
                        "depth": 0}],
        "subtotal": 2000.0, "tax_type": "cgst_sgst",
        "tax_info": {"CGST": 180.0, "SGST": 180.0, "total": 360.0,
                     "cgst_rate": 9.0, "sgst_rate": 9.0},
        "grand_total": 2360.0, "round_off": 0.0, "round_off_on": True, "total_qty": 2.0,
        "place_of_supply": "Maharashtra", "pos_code": "27", "reverse_charge": False,
        "advance_received": 0.0, "net_payable": 2360.0, "po_number": "", "po_date": "",
        "dispatch_through": "", "dispatch_doc_no": "", "vehicle_no": "", "eway_bill_no": "",
        "payment_terms": "", "notes": "", "company_branch": "", "auth_signatory": "",
    }
    ti.update(over)
    STORE["invoices"][ti["id"]] = ti
    return ti


def _form(ti, rows=None, **over):
    rows = rows if rows is not None else LE.rows_for_form(ti["line_items"], 18.0)
    d = {"date": ti["date"], "place_of_supply": ti["place_of_supply"],
         "po_number": "", "po_date": "", "dispatch_through": "", "dispatch_doc_no": "",
         "vehicle_no": "", "eway_bill_no": "", "payment_terms": "", "notes": "",
         "advance_received": "0", "tax_type": ti["tax_type"],
         "account_name": ti["account_name"], "contact_person": ti["contact_person"],
         "to": ti["to"], "bill_gstin": ti["bill_gstin"], "ship_same": "1",
         "round_off_form": "1", "round_off_on": "1", LE.FIELD: json.dumps(rows)}
    d.update(over)
    return d


@pytest.fixture()
def ti(client):
    STORE["invoices"].clear()
    return _ti()


def test_the_view_offers_edit_and_the_form_has_no_number_box(client, ti):
    html = client.get("/invoice/view/te1").get_data(as_text=True)
    assert "/invoice/edit/te1" in html
    form = client.get("/invoice/edit/te1").get_data(as_text=True)
    assert 'name="doc_no_seq"' not in form and "locked" in form


def test_every_field_but_the_number_is_saved(client, ti):
    rows = LE.rows_for_form(ti["line_items"], 18.0)
    rows[0]["qty"] = "3"
    rows.append({"name": "Gasket", "qty": "4", "unit": "Nos", "price": "25",
                 "gst_rate": "18", "is_header": False})
    r = client.post("/invoice/edit/te1", data=_form(
        ti, rows, bill_gstin="27BBBBB1111B1Z5", vehicle_no="mh12ab1234",
        place_of_supply="Karnataka", date="2026-10-20", doc_no_seq="0099",
        advance_received="500"))
    assert r.status_code == 302
    t = STORE["invoices"]["te1"]
    assert t["ref"] == "SF/TI/26-27/0005"            # the number never moves
    assert t["bill_gstin"] == "27BBBBB1111B1Z5"
    assert t["vehicle_no"] == "MH12AB1234"
    assert (t["place_of_supply"], t["pos_code"]) == ("Karnataka", "29")
    assert t["subtotal"] == 3100.0 and t["tax_info"]["total"] == 558.0
    assert t["grand_total"] == 3658.0 and t["net_payable"] == 3158.0


def test_the_date_stays_inside_the_numbers_financial_year(client, ti):
    r = client.post("/invoice/edit/te1", data=_form(ti, date="2027-04-02"))
    assert r.status_code == 200 and "financial year" in r.get_data(as_text=True)
    assert STORE["invoices"]["te1"]["date"] == "2026-10-02"


def test_changes_are_logged_and_the_band_is_screen_only(client, ti):
    client.post("/invoice/edit/te1", data=_form(ti))
    assert EL.FIELD not in STORE["invoices"]["te1"]
    client.post("/invoice/edit/te1", data=_form(ti, notes="corrected PO ref"))
    entry = STORE["invoices"]["te1"][EL.FIELD][-1]
    assert (entry["field"], entry["before"], entry["after"]) == ("Note", "", "corrected PO ref")
    html = client.get("/invoice/view/te1").get_data(as_text=True)
    assert "Edited after issue on" in html
    assert html.index("Edited after issue on") < html.index('<div class="doc-outer">')


def test_a_cancelled_invoice_is_locked_on_both_verbs(client, ti):
    ti["status"] = "cancelled"
    assert client.get("/invoice/edit/te1").status_code == 302
    r = client.post("/invoice/edit/te1", data=_form(ti, notes="sneaky"))
    assert r.status_code == 302
    assert STORE["invoices"]["te1"]["notes"] == ""
    assert "/invoice/edit/te1" not in client.get("/invoice/view/te1").get_data(as_text=True)
