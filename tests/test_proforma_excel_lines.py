"""
Add lines from Excel on the PROFORMA — CLIENT_CHANGES.md §0 sixty-fourth block,
Part 5 (31 Oct 2026; narrows the earlier "a PI is copied, never typed"
exclusion, per Manas's 28 October agreement with the client).

Not a standalone PI: the sheet lands on a PI's edit form or on one of its two
create forms. The imported rows are EXTRA lines appended after the copied
ones, which are untouched; nothing is saved until the form's own Save.
"""

import json

import docimport as DI
import lineedit as LE
from store import STORE
from tests.test_doc_import import SIFY, applied, sify, staged
from tests.test_proforma_edit import _form as _edit_form, _pi

ROWS = [["Description", "Make", "HSN", "Qty", "Unit", "Rate", "GST %"],
        ["Flange 50 NB", "Kirloskar", "7307", 4, "Nos", 120, 18],
        ["Gasket 50 NB", "", "4016", 4, "Nos", 25, 12]]


def test_the_kind_carries_the_proformas_create_permission():
    import auth
    assert auth.ROUTE_PERMISSIONS["docimport.upload_proforma"] == "proforma.create"
    assert DI.KINDS["proforma"].endpoint == "proforma.edit_proforma"


def test_onto_the_edit_form_the_rows_are_appended_and_nothing_is_saved(client):
    STORE["proformas"].clear()
    pi = _pi()
    before = json.dumps(pi, sort_keys=True)
    tok = staged("proforma", ROWS, ctx={"pi": "pe1"})
    page = applied(client, "proforma", tok).get_data(as_text=True)
    assert "Nothing has been saved" in page and "Flange 50 NB" in page
    assert json.dumps(STORE["proformas"]["pe1"], sort_keys=True) == before
    # The editor's rows: the two stored lines first, then the two imported.
    rows = LE.rows_for_form(pi["line_items"], 18.0) + LE.imported_rows(
        DI._built(DI.KINDS["proforma"], STORE["doc_imports"][tok])["items"])
    r = client.post("/proforma/edit/pe1", data=_edit_form(pi, rows))
    assert r.status_code == 302
    lines = STORE["proformas"]["pe1"]["line_items"]
    assert [l["name"] for l in lines] == ["Pump", "Valve", "Flange 50 NB", "Gasket 50 NB"]
    assert [l.get("source") for l in lines] == [None, None, "excel", "excel"]
    assert lines[2]["make"] == "Kirloskar" and lines[3]["gst_rate"] == 12.0


def _quotation():
    STORE["quotations"]["qx"] = {
        "id": "qx", "ref": "QT-0001", "date": "2026-08-01", "account_name": "A Customer",
        "to": "A Customer\nPune",
        "line_items": [{"type": "item", "name": "Pipe", "qty": 2.0, "price": 100.0,
                        "total": 200.0, "unit": "Nos", "hsn": "7306", "depth": 0}],
        "subtotal": 200.0, "grand_total": 236.0, "total_qty": 2.0,
        "tax_type": "cgst_sgst",
        "tax_info": {"CGST": 18.0, "SGST": 18.0, "total": 36.0,
                     "cgst_rate": 9.0, "sgst_rate": 9.0}}


def test_onto_the_quotation_path_create_form_the_copied_lines_are_untouched(client):
    STORE["proformas"].clear()
    _quotation()
    tok = staged("proforma", ROWS, ctx={"qid": "qx"})
    page = applied(client, "proforma", tok).get_data(as_text=True)
    assert "Extra lines from Excel" in page and not STORE["proformas"]
    extra = LE.imported_rows(DI._built(DI.KINDS["proforma"], STORE["doc_imports"][tok])["items"])
    r = client.post("/proforma/from/qx", data={"date": "2026-08-04", "advance_pct": "100",
                                              LE.EXTRA_FIELD: json.dumps(extra)})
    assert r.status_code == 302
    pi = next(iter(STORE["proformas"].values()))
    copied, *added = pi["line_items"]
    assert {k: copied[k] for k in ("name", "qty", "price", "total")} == \
        {"name": "Pipe", "qty": 2.0, "price": 100.0, "total": 200.0}
    assert [a["name"] for a in added] == ["Flange 50 NB", "Gasket 50 NB"]
    # 200 + 480 at 18 % and 100 at 12 %.
    assert pi["subtotal"] == 780.0
    assert pi["tax_info"]["total"] == round(680 * 0.18 + 100 * 0.12, 2)


def test_a_quotation_path_pi_without_an_import_is_unchanged(client):
    STORE["proformas"].clear()
    _quotation()
    client.post("/proforma/from/qx", data={"date": "2026-08-04", "advance_pct": "100"})
    pi = next(iter(STORE["proformas"].values()))
    assert len(pi["line_items"]) == 1 and "gst_rate" not in pi["line_items"][0]
    assert pi["tax_info"]["CGST"] == 18.0


def test_onto_the_boq_path_create_form(client):
    sify(client)
    tok = staged("proforma", ROWS, ctx={"boq": SIFY})
    page = applied(client, "proforma", tok).get_data(as_text=True)
    assert "Extra lines from Excel" in page and "Flange 50 NB" in page


def test_text_in_a_numeric_cell_never_becomes_zero(client):
    STORE["proformas"].clear()
    _quotation()
    tok = staged("proforma", [["Description", "Qty", "Rate"], ["Elbow", "four", 10]],
                 ctx={"qid": "qx"})
    built = DI._built(DI.KINDS["proforma"], STORE["doc_imports"][tok])
    assert built["items"][0]["qty"] == ""
