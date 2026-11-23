"""
Add lines from Excel on "New PI (no BOQ)" — `/proforma/new`, CLIENT_CHANGES.md
§0 eighty-ninth block, item 6a (23 November 2026). The existing proforma
import kind (`/import/proforma`) gains a `?new=1` context that renders the
standalone form's line editor with the sheet's rows; nothing is saved until
that form's own Save.
"""

import json

from store import STORE
from test_doc_import import applied, staged

ROWS = [["Description", "Qty", "Unit", "Rate", "GST %"],
        ["Flange 150 NB", 4, "Nos", 1350, 18],
        ["Gasket", 10, "Nos", "", ""]]


def test_the_new_form_offers_the_import_button(client):
    html = client.get("/proforma/new").get_data(as_text=True)
    assert 'href="/import/proforma?new=1"' in html
    assert client.get("/import/proforma?new=1").status_code == 200


def test_the_rows_land_in_the_new_forms_editor_and_nothing_is_saved(client):
    before = set(STORE["proformas"])
    tok = staged("proforma", ROWS, {"new": "1"})
    page = applied(client, "proforma", tok).get_data(as_text=True)
    assert "New <span>Proforma Invoice</span>" in page
    assert set(STORE["proformas"]) == before, "nothing saved by the import"
    rows = json.loads(page.split("var ROWS = ", 1)[1].split(";\n", 1)[0])
    assert [r["name"] for r in rows] == ["Flange 150 NB", "Gasket"]
    assert rows[0]["qty"] == "4" and rows[0]["price"] == "1350"
    assert rows[1]["price"] == "", "a blank rate stays blank"
    assert all(r.get("source") == "excel" for r in rows)


def test_the_other_contexts_are_unchanged(client):
    import docimport as DI
    k = DI.KINDS["proforma"]
    assert k.context({})[0] == {}
    assert k.context({"new": "0"})[0] == {}
