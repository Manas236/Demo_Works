"""
Importer fixes, 23 November 2026.

a. A ticked sheet with NO quantity column (a "Summary" tab) no longer blocks
   the import: it is skipped, and the preview says so in one line. Only when
   NO ticked sheet has one is the import refused, saying exactly that. The
   BOQ importer and the Work Order importer share the rule
   (`sheetimport.split_qty_tabs()`).
b. The prefilled form's banner says "Preview ready. ..." instead of the bold
   "Nothing has been saved", which read like a failure. Still nothing is saved
   until the document's own Save.
c. The title picker never takes a date line ("DATE: 21.02.2024") as the
   project — it falls through to the next candidate.

Every workbook is built in memory; no binary is committed.
"""

import io

import pytest

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")

import boqimport                 # noqa: E402
import conftest                  # noqa: E402
import sheetimport as SI         # noqa: E402
import workorder as W            # noqa: E402
from store import STORE          # noqa: E402

from test_boq_import_picker import confirm, model_of, open_form, rendered_form, stage  # noqa: E402


ITEMS = [["Sr", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount"],
         ["1", "Pipe", 10, "Mtr", 100, 1000],
         ["2", "Valve", 2, "Nos", 50, 100],
         [None, "Total", None, None, None, 1100]]
SUMMARY = [["Sr", "Description", "Amount"],
           ["A", "Sprinkler system", 1100],
           [None, "Grand Total", 1100]]


def grid_of(rows, name="BOQ"):
    return SI.from_rows([(name, "visible", rows)])["grid"][0]


# ═══ a. The shared rule ═════════════════════════════════════════════════════

def test_split_qty_tabs_keeps_order_and_names_the_rest():
    maps = {0: {"0": "description", "1": "amount"}, 1: {"0": "description", "1": "qty"},
            2: {"0": "qty"}}
    assert SI.split_qty_tabs([0, 1, 2], maps.get) == ([1, 2], [0])
    assert SI.skipped_sheet_text("Summary") == "Skipped sheet 'Summary': no quantity column found."


# ═══ a. BOQ import ══════════════════════════════════════════════════════════

def test_a_summary_tab_is_skipped_and_said_so(client):
    tok, _k = stage([("Summary", SUMMARY), ("Sprinkler", ITEMS)])
    html, r = confirm(client, tok, action="update", tab=["0", "1"])
    page = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "Skipped sheet &#x27;Summary&#x27;: no quantity column found." in page
    assert "Before this can open as a BOQ" not in page, "a skipped tab blocks nothing"
    form_html = open_form(client, tok)
    model = model_of(form_html)
    assert [l["description"] for l in model["lines"]] == ["Pipe", "Valve"]
    assert "Skipped sheet &#x27;Summary&#x27;: no quantity column found." in form_html


def test_a_skipped_tab_still_shows_its_column_picker(client):
    """The operator can still map a quantity on it and bring it back."""
    tok, _k = stage([("Summary", SUMMARY), ("Sprinkler", ITEMS)])
    confirm(client, tok, action="update", tab=["0", "1"])
    page = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert 'name="map_0_2"' in page


def test_no_tab_with_a_quantity_column_is_still_refused(client):
    tok, _k = stage([("Summary", SUMMARY)])
    _html, r = confirm(client, tok)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert SI.NO_QTY_ANYWHERE in body
    assert STORE["boq_imports"][tok]["confirmed"] is False


def test_one_tab_with_a_quantity_is_byte_for_byte_as_before():
    g = grid_of(ITEMS)
    rec = {"grid": [g], "sheets": [{"name": "BOQ", "staged": True}], "sheet_index": 0,
           "mapping": SI.advised_mapping(g), "ticked": [0]}
    plain = SI.build(g, SI.clean_mapping(g, SI.advised_mapping(g)))
    plain["tab_totals"] = []
    assert boqimport.build_tabs(rec) == plain


# ═══ a. Work order import ═══════════════════════════════════════════════════

WO_ITEMS = [["Sr. No.", "Description", "Qty", "Unit", "Material Rate", "Labour Rate"],
            ["1", "Pipe laying", 10, "Mtr", 80, 20]]


def test_work_order_skips_a_summary_tab(client):
    wb = SI.from_rows([("Summary", "visible", SUMMARY), ("WO", "visible", WO_ITEMS)])
    tok = W.stage(wb, "wo.xlsx", conftest.ensure_test_user()["id"])
    html = client.get(f"/wo/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    form.update(tab=["0", "1"], act="update")
    page = client.post(f"/wo/import/{tok}", data=form).get_data(as_text=True)
    assert "Skipped sheet &#x27;Summary&#x27;: no quantity column found." in page
    form = rendered_form(page)
    form.update(tab=["0", "1"], act="confirm")
    page = client.post(f"/wo/import/{tok}", data=form).get_data(as_text=True)
    assert "Not yet:" not in page
    assert "Pipe laying" in page
    assert "Skipped sheet &#x27;Summary&#x27;: no quantity column found." in page


def test_work_order_with_no_quantity_anywhere_is_refused(client):
    wb = SI.from_rows([("Summary", "visible", SUMMARY)])
    tok = W.stage(wb, "wo.xlsx", conftest.ensure_test_user()["id"])
    html = client.get(f"/wo/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    form.update(tab=["0"], act="confirm")
    page = client.post(f"/wo/import/{tok}", data=form).get_data(as_text=True)
    assert SI.NO_QTY_ANYWHERE in page


# ═══ b. The banner wording ══════════════════════════════════════════════════

def test_boq_banner_says_preview_ready(client):
    tok, _k = stage([("BOQ", ITEMS)])
    html = open_form(client, tok)
    assert "<b>Preview ready.</b> Fill in the project and customer, then press Create BOQ." in html
    assert "Nothing has been saved" not in html


# ═══ c. A date line is never the title ══════════════════════════════════════

@pytest.mark.parametrize("line", [
    "DATE: 21.02.2024", "Date - 21/02/2024", "Dt. 21-02-2024", "Dated 21.02.24",
    "21.02.2024", "21 February 2024", "DATE:"])
def test_a_date_line_is_never_the_title(line):
    g = grid_of([[line], ["Fire Fighting Works at Pune"], HEAD_ROW, ["1", "Pipe", 1, "Mtr", 10]])
    p = SI.detect_names(g)["project"]
    assert p["text"] == "Fire Fighting Works at Pune"


def test_a_date_line_alone_leaves_no_title():
    g = grid_of([["DATE: 21.02.2024"], HEAD_ROW, ["1", "Pipe", 1, "Mtr", 10]])
    assert SI.detect_names(g)["project"] is None


@pytest.mark.parametrize("title", [
    "Data Centre Fire Fighting", "Dattatray Nagar Hospital", "Update of Hydrant System 2024"])
def test_a_title_that_merely_starts_like_date_is_kept(title):
    g = grid_of([[title], HEAD_ROW, ["1", "Pipe", 1, "Mtr", 10]])
    assert SI.detect_names(g)["project"]["text"] == title


HEAD_ROW = ["Sr", "Description", "Qty", "Unit", "Supply Rate"]
