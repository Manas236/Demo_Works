"""
Editing an issued proforma invoice — CLIENT_CHANGES.md §0 sixty-fourth block,
Part 1 (Manas, 31 Oct 2026).

What is held here:

1. every field is editable: party, addresses, dates, terms, the lines (add,
   remove, reorder, every column), the tax head and the round-off tick;
2. the figures are recomputed to the paisa, discount and per-line GST
   included, and the payment box follows;
3. the number moves forward only, through `docnum.validate()`, and keeping it
   is always allowed;
4. a tax invoice raised from the PI is NOT changed, and both pages draw the
   amber divergence band — which a PI never edited does not draw;
5. every change is logged (who, when, field, before → after), the band is on
   screen only, and a save that changes nothing logs nothing;
6. a forged `_k` cannot carry a stored key (an image, a line id) onto a row it
   did not come from — the keys the form does not edit come from the STORED
   row only.
"""

import json

import pytest

import docnum as DN
import editlog as EL
import lineedit as LE
from store import STORE


def _pi(**over):
    pi = {
        "id": "pe1", "ref": "PI-0007", "date": "2026-10-01",
        "quotation_id": "", "quotation_ref": "Q-1", "quotation_date": "2026-09-30",
        "account_name": "Acme", "contact_person": "Ravi", "to": "Acme Ltd\nPune",
        "bill_gstin": "27AAAAA0000A1Z5", "ship_same": "1",
        "ship_acct_name": "", "ship_addr": "", "ship_city": "", "ship_state": "",
        "ship_pin": "", "ship_phone": "", "ship_gstin": "",
        "line_items": [
            {"type": "item", "name": "Pump", "part_no": "P1", "hsn": "8413",
             "qty": 2.0, "unit": "Nos", "price": 1000.0, "total": 2000.0,
             "depth": 0, "line_id": "L-1", "image": "img-1"},
            {"type": "item", "name": "Valve", "part_no": "V1", "hsn": "8481",
             "qty": 1.0, "unit": "Nos", "price": 500.0, "total": 500.0, "depth": 0},
        ],
        "subtotal": 2500.0, "tax_type": "cgst_sgst",
        "tax_info": {"CGST": 225.0, "SGST": 225.0, "total": 450.0,
                     "cgst_rate": 9.0, "sgst_rate": 9.0},
        "grand_total": 2950.0, "round_off": 0.0, "round_off_on": True,
        "total_qty": 3.0, "po_number": "", "po_date": "", "advance_pct": 100.0,
        "amount_due": 2950.0, "project_id": "", "prior_invoiced": 0.0,
        "prior_refs": [], "balance_due": 0.0, "payment_terms": "", "delivery_terms": "",
        "delivery_date": "", "dispatch_through": "", "incoterms": "",
        "validity_days": "15", "notes": "", "company_branch": "", "auth_signatory": "",
    }
    pi.update(over)
    STORE["proformas"][pi["id"]] = pi
    return pi


def _form(pi, rows=None, **over):
    rows = rows if rows is not None else LE.rows_for_form(pi["line_items"], 18.0)
    data = {
        "doc_no_seq": DN.split_ref(pi["ref"])[1], "date": pi["date"],
        "po_number": pi.get("po_number", ""), "po_date": pi.get("po_date", ""),
        "project_id": "", "advance_pct": "100", "tax_type": pi["tax_type"],
        "payment_terms": "", "delivery_terms": "", "delivery_date": "",
        "dispatch_through": "", "incoterms": "", "validity_days": "15", "notes": "",
        "account_name": pi["account_name"], "contact_person": pi["contact_person"],
        "to": pi["to"], "bill_gstin": pi["bill_gstin"], "ship_same": "1",
        "round_off_form": "1", "round_off_on": "1",
        LE.FIELD: json.dumps(rows),
    }
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


@pytest.fixture()
def pi(client):
    STORE["proformas"].clear()
    STORE["invoices"].clear()
    return _pi()


def test_the_form_renders_every_field(client, pi):
    html = client.get("/proforma/edit/pe1").get_data(as_text=True)
    for name in ("doc_no_seq", "date", "po_number", "po_date", "advance_pct",
                 "account_name", "contact_person", 'name="to"', "bill_gstin",
                 "ship_same", "ship_gstin", "payment_terms", "incoterms",
                 "validity_days", "tax_type", LE.FIELD, "round_off_on"):
        assert name in html, name
    assert "Pump" in html and "le-add" in html


def test_party_dates_terms_and_lines_are_all_saved(client, pi):
    rows = LE.rows_for_form(pi["line_items"], 18.0)
    rows.reverse()                               # reorder
    rows[0]["qty"] = "3"                         # Valve: 3 × 500, less 10 %
    rows[0]["discount_pct"] = "10"
    rows[0]["make"] = "Kirloskar"
    rows[0]["gst_rate"] = "12"                   # a second slab
    rows.append({"name": "Gasket", "part_no": "", "make": "", "hsn": "4016",
                 "qty": "4", "unit": "Nos", "price": "25", "discount_pct": "",
                 "gst_rate": "18", "is_header": False})
    r = client.post("/proforma/edit/pe1", data=_form(
        pi, rows, account_name="Acme Fire Pvt Ltd", bill_gstin="27BBBBB1111B1Z5",
        date="2026-10-05", po_number="PO/77", po_date="2026-10-02",
        payment_terms="30 days", notes="corrected", advance_pct="50"))
    assert r.status_code == 302
    pi = STORE["proformas"]["pe1"]
    assert pi["account_name"] == "Acme Fire Pvt Ltd"
    assert pi["bill_gstin"] == "27BBBBB1111B1Z5"
    assert (pi["date"], pi["po_number"], pi["po_date"]) == ("2026-10-05", "PO/77", "2026-10-02")
    assert pi["notes"] == "corrected" and pi["payment_terms"] == "30 days"
    names = [l["name"] for l in pi["line_items"]]
    assert names == ["Valve", "Pump", "Gasket"]
    valve = pi["line_items"][0]
    assert valve["total"] == 1350.0 and valve["discount_pct"] == 10.0
    assert valve["make"] == "Kirloskar"
    assert pi["subtotal"] == 1350.0 + 2000.0 + 100.0
    # Two slabs: 12 % on 1350, 18 % on 2100.
    assert pi["tax_info"]["CGST @ 6%"] == 81.0
    assert pi["tax_info"]["CGST @ 9%"] == 189.0
    assert pi["tax_info"]["total"] == 2 * 81.0 + 2 * 189.0
    assert pi["grand_total"] == round(3450 + 540)
    assert pi["advance_pct"] == 50.0 and pi["amount_due"] == 1995.0
    assert pi["balance_due"] == 1995.0


def test_the_print_shows_make_and_discount_only_when_present(client, pi):
    html = client.get("/proforma/view/pe1").get_data(as_text=True)
    assert "Make:" not in html and "Discount " not in html
    rows = LE.rows_for_form(pi["line_items"], 18.0)
    rows[0]["make"] = "Kirloskar"
    client.post("/proforma/edit/pe1", data=_form(pi, rows))
    html = client.get("/proforma/view/pe1").get_data(as_text=True)
    assert "Make: Kirloskar" in html


def test_keys_the_form_does_not_edit_come_from_the_stored_row(client, pi):
    rows = LE.rows_for_form(pi["line_items"], 18.0)
    # A forged new row claiming to be row 0 by carrying no _k gets nothing.
    rows.append({"name": "Forged", "qty": "1", "price": "1", "gst_rate": "18",
                 "image": "img-1", "line_id": "L-1"})
    client.post("/proforma/edit/pe1", data=_form(pi, rows))
    lines = STORE["proformas"]["pe1"]["line_items"]
    assert lines[0]["image"] == "img-1" and lines[0]["line_id"] == "L-1"
    assert "image" not in lines[2] and "line_id" not in lines[2]


def test_text_in_a_numeric_box_is_refused_and_nothing_is_saved(client, pi):
    rows = LE.rows_for_form(pi["line_items"], 18.0)
    rows[0]["qty"] = "two"
    r = client.post("/proforma/edit/pe1", data=_form(pi, rows))
    assert r.status_code == 200 and "not a number" in r.get_data(as_text=True)
    assert STORE["proformas"]["pe1"]["line_items"][0]["qty"] == 2.0
    assert EL.FIELD not in STORE["proformas"]["pe1"]


def test_the_number_moves_forward_only(client, pi):
    _pi(id="pe2", ref="PI-0009")
    r = client.post("/proforma/edit/pe1", data=_form(pi, doc_no_seq="0008"))
    assert r.status_code == 200
    assert "highest already used in this series is 0009" in r.get_data(as_text=True)
    assert STORE["proformas"]["pe1"]["ref"] == "PI-0007"
    r = client.post("/proforma/edit/pe1", data=_form(pi, doc_no_seq="0012"))
    assert r.status_code == 302
    assert STORE["proformas"]["pe1"]["ref"] == "PI-0012"
    assert STORE["proformas"]["pe1"]["number_override"]["from"] == "PI-0007"
    assert DN.highest_used(DN.PI, "") == 12


def test_keeping_the_number_is_always_allowed(client, pi):
    _pi(id="pe2", ref="PI-0009")
    r = client.post("/proforma/edit/pe1", data=_form(pi, notes="x"))
    assert r.status_code == 302
    assert STORE["proformas"]["pe1"]["ref"] == "PI-0007"
    assert "number_override" not in STORE["proformas"]["pe1"]


def test_every_change_is_logged_and_an_unchanged_save_logs_nothing(client, pi):
    client.post("/proforma/edit/pe1", data=_form(pi))
    assert EL.FIELD not in STORE["proformas"]["pe1"]
    client.post("/proforma/edit/pe1", data=_form(pi, bill_gstin="27CCCCC2222C1Z5"))
    log = STORE["proformas"]["pe1"][EL.FIELD]
    entry = [e for e in log if e["field"] == "Customer GSTIN"][0]
    assert entry["before"] == "27AAAAA0000A1Z5" and entry["after"] == "27CCCCC2222C1Z5"
    assert entry["by"] and entry["at"]
    html = client.get("/proforma/view/pe1").get_data(as_text=True)
    assert "Edited after issue on" in html
    # Screen only: drawn above the sheet, and hidden in print.
    assert html.index("Edited after issue on") < html.index('<div class="doc-outer">')
    assert "@media print { .el-band { display:none !important; } }" in html


def test_a_tax_invoice_raised_from_it_is_not_changed_and_both_pages_say_so(client, pi):
    STORE["invoices"]["ti1"] = {
        "id": "ti1", "ref": "SF/TI/26-27/0001", "fy": "26-27", "date": "2026-10-02",
        "proforma_id": "pe1", "proforma_ref": "PI-0007",
        **{k: pi[k] for k in ("account_name", "contact_person", "to", "bill_gstin",
                              "ship_same", "ship_acct_name", "ship_addr", "ship_city",
                              "ship_state", "ship_pin", "ship_phone", "ship_gstin")},
        "line_items": [dict(r) for r in pi["line_items"]], "subtotal": 2500.0,
        "tax_type": "cgst_sgst", "tax_info": dict(pi["tax_info"]), "grand_total": 2950.0,
        "round_off": 0.0, "place_of_supply": "Maharashtra", "pos_code": "27",
    }
    before = json.dumps(STORE["invoices"]["ti1"], sort_keys=True)
    # Never edited: no band on either page.
    assert "was edited after tax invoice" not in client.get("/proforma/view/pe1").get_data(as_text=True)
    assert "was edited after tax invoice" not in client.get("/invoice/view/ti1").get_data(as_text=True)
    form = client.get("/proforma/edit/pe1").get_data(as_text=True)
    assert "does <b>not</b> change it" in form
    client.post("/proforma/edit/pe1", data=_form(pi, account_name="Renamed Ltd"))
    assert json.dumps(STORE["invoices"]["ti1"], sort_keys=True) == before
    for url in ("/proforma/view/pe1", "/invoice/view/ti1"):
        html = client.get(url).get_data(as_text=True)
        assert "The proforma was edited after tax invoice SF/TI/26-27/0001" in html, url
        assert "Renamed Ltd" in html


def test_the_route_is_classified_and_the_number_permission_covers_it():
    import auth
    assert auth.ROUTE_PERMISSIONS["proforma.edit_proforma"] == "proforma.create"
    assert "proforma.edit_proforma" in auth.PANEL_PERMISSIONS["docnum.override"]
