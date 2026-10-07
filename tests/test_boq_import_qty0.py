"""
The BOQ import leaves out a row with QUANTITY 0 AND NO RATE (7 October 2026,
CLIENT_CHANGES.md §0, forty-sixth block — Manas's ruling, no charge).

Every workbook here is BUILT IN MEMORY (`sheetimport.from_rows()`); no binary
is committed and no text from a client's real sheet appears in this file. The
client's own sheets are read by `tests/test_boq_import_qty0_client_sheets.py`,
which skips where they are absent.

The rule, and where each half is held below:

* a line is LEFT OUT when (a) its quantity cell is the NUMBER 0, (b) no ticked
  rate carries a non-zero number and (c) no ticked amount does — a blank
  quantity is not 0; quantity 0 WITH a rate is kept untouched; quantity 0 with
  only an amount is kept and listed;
* a parent whose every child went goes too, and a section left with no lines;
  a parent that keeps a child, or is itself priced, stays;
* the preview lists every row left out, per tab, by row and description; the
  form carries the one-line count; screen only;
* selling and cost mode alike, every ticked tab; the IMPORT only — a 0 typed
  on /boq/create saves as it always did;
* ONE row predicate, `sheetimport.qty0_unpriced()`, called by the BOQ import
  and the work order alike — and the work order's rows did not move.
"""

import copy
import json
import re

import pytest

import boq
import boqimport
import conftest
import sheetimport as SI
import workorder as W
from store import STORE


# ═══ Helpers ═════════════════════════════════════════════════════════════════

HEAD = ["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount",
        "Installation Rate", "Installation Amount"]
MAP = {"0": "item_no", "1": "description", "2": "qty", "3": "unit",
       "4": "supply_rate", "5": "supply_amount", "6": "install_rate",
       "7": "install_amount"}


def grid_of(rows, name="BOQ"):
    return SI.from_rows([(name, "visible", rows)])["grid"][0]


def built(rows, mapping=None):
    """`sheetimport.build()` over HEAD + rows, as the BOQ import reads it."""
    return SI.build(grid_of([HEAD] + rows), dict(mapping or MAP))


def dropped(rows, mapping=None, tab="BOQ"):
    return boqimport.drop_qty0(built(rows, mapping), tab)


def rows_of(res):
    return [l["row"] for l in res["lines"]]


def stage(rows_by_tab, name="sheet.xlsx"):
    """Stage synthetic tabs for the suite's signed-in Owner. Call AFTER `client`."""
    wb = SI.from_rows([(t, "visible", rows) for t, rows in rows_by_tab])
    return boqimport.stage(wb, name, conftest.ensure_test_user()["id"])


def rendered_form(html: str) -> dict:
    """The preview's controls as rendered — what a browser posts untouched."""
    form = {"picker": "1", "action": "confirm"}
    for name, opts in re.findall(r'<select name="(map_\d+_\d+)"[^>]*>(.*?)</select>', html, re.S):
        m = re.search(r'<option value="([^"]*)" selected>', opts)
        form[name] = m.group(1) if m else ""
    for name in re.findall(r'<input type="checkbox" name="(use_\d+_\d+)" value="1" checked', html):
        form[name] = "1"
    form["tab"] = re.findall(r'<input type="checkbox" name="tab" value="(\d+)" checked', html)
    return form


def preview_and_form(client, tok, **changes):
    """GET the preview, confirm it as rendered (plus `changes`), follow to the
    prefilled form. Returns (preview html, form html)."""
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    form.update(changes)
    r = client.post(f"/boq/import/{tok}", data=form)
    assert r.status_code == 303, r.get_data(as_text=True)[:3000]
    page = client.get(r.headers["Location"])
    assert page.status_code == 200
    return html, page.get_data(as_text=True)


def model_of(html: str) -> dict:
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", html, re.S)
    assert m, "the page carries no editor model"
    return json.loads(m.group(1))


def save_model(client, model, **form):
    data = {"date": "2026-10-07", "project_name": "P", "account_name": "A",
            "boq_json": json.dumps(model)}
    data.update(form)
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data=data)
    new = set(STORE["boqs"]) - before
    if r.status_code == 302 and new:
        return STORE["boqs"][new.pop()]
    return r.get_data(as_text=True)


def visible(html: str) -> str:
    """The page with scripts and styles taken out — what is RENDERED."""
    return re.sub(r"<(script|style)>.*?</\1>", "", html, flags=re.S)


# ═══ 1. The predicate — ONE function, pure ═══════════════════════════════════

@pytest.mark.parametrize("qty,figures,want", [
    (0, [], True),
    (0.0, [None, 0, 0.0], True),
    (-0.0, [None], True),                       # a negative zero is the number 0
    (0, [None, "Included", float("nan")], True),  # text and NaN are no price
    (0, [5], False),
    (0, [None, 0, 1500.0], False),              # (c): an amount is a price
    (0, [-250.0], False),                       # a credit is a non-zero number
    (None, [], False),                          # a BLANK quantity is not 0
    ("0", [], False),                           # the reader gives numbers, not text
    (True, [], False), (False, [], False),      # a bool is no quantity
    (float("nan"), [], False),
    (3, [], False), (0.001, [], False),
])
def test_the_predicate_is_the_number_0_and_no_other_figure(qty, figures, want):
    assert SI.qty0_unpriced(qty, figures) is want


def test_the_predicate_reads_any_iterable_and_never_mutates_it():
    figs = {"supply_rate": 0.0, "supply_amount": None}
    assert SI.qty0_unpriced(0.0, figs.values()) is True
    assert figs == {"supply_rate": 0.0, "supply_amount": None}
    assert SI.qty0_unpriced(0.0, iter([0, 0])) is True


def test_the_price_fields_are_every_rate_and_amount_and_no_percentage():
    assert set(SI.QTY0_RATE_FIELDS) == {"supply_base_rate", "supply_rate", "supply_net_rate",
                                        "install_base_rate", "install_rate", "install_net_rate"}
    assert set(SI.QTY0_PRICE_FIELDS) == set(SI.QTY0_RATE_FIELDS) | set(SI.AMOUNT_FIELDS)
    for pct in SI.PCT_FIELDS:
        assert pct not in SI.QTY0_PRICE_FIELDS, f"{pct} moves a rate; it is not one"


# ═══ 2. The reader records the row's prices as the sheet wrote them ══════════

def test_price_figures_are_the_ticked_rates_and_amounts_as_the_sheet_wrote_them():
    res = built([["1", "Pipe", 0, "Mtr", 0, 0, None, 12],
                 ["2", "Valve", 4, "Nos", 25, 100, None, None]])
    one, two = res["lines"]
    assert one["price_figures"] == {"supply_rate": 0.0, "supply_amount": 0.0,
                                    "install_amount": 12.0}
    assert two["price_figures"] == {"supply_rate": 25.0, "supply_amount": 100.0}
    assert one["supply_rate"] == 0.0, "the line itself is unchanged: 0 stays 0"


def test_an_unticked_column_is_never_in_the_price_figures():
    rows = [["1", "Pipe", 0, "Mtr", 75, None, None, None]]
    unticked = {k: v for k, v in MAP.items() if v != "supply_rate"}
    li = built(rows, unticked)["lines"][0]
    assert "supply_rate" not in li["price_figures"] and li["supply_rate"] is None


def test_the_reader_still_returns_every_line_quantity_0_or_not():
    """The rule is the IMPORTER's: `build()` leaves nothing out."""
    res = built([["1", "Pipe", 0, "Mtr", None, None, None, None],
                 ["2", "Valve", 4, "Nos", 25, None, None, None]])
    assert rows_of(res) == [2, 3]


# ═══ 3. Which lines go, and which stay — `boqimport.drop_qty0()` ═════════════

def test_quantity_0_with_blank_rates_is_left_out():
    res = dropped([["1", "Pipe", 0, "Mtr", None, None, None, None],
                   ["2", "Valve", 4, "Nos", 25, None, None, None]])
    assert rows_of(res) == [3]
    assert res["left_out"] == [{"tab": "BOQ", "row": 2, "item_no": "1", "text": "Pipe"}]


def test_quantity_0_with_0_rates_and_0_amounts_is_left_out():
    res = dropped([["1", "Pipe", 0, "Mtr", 0, 0, 0, 0],
                   ["2", "Valve", 4, "Nos", 25, None, None, None]])
    assert rows_of(res) == [3] and [e["row"] for e in res["left_out"]] == [2]


def test_quantity_0_that_reads_as_0_is_the_number_0():
    """Text "0" and a negative zero are the number 0 on the sheet."""
    res = dropped([["1", "Pipe", "0", "Mtr", None, None, None, None],
                   ["2", "Bend", -0.0, "Nos", 0, None, None, None],
                   ["3", "Valve", 4, "Nos", 25, None, None, None]])
    assert rows_of(res) == [4]


def test_quantity_0_with_a_rate_is_kept_untouched_as_a_rate_only_line():
    rows = [["1", "Pipe", 0, "Mtr", 1080, 0, None, None],
            ["2", "Bend", 0, "Nos", None, None, 45, None]]
    plain = built(rows)
    res = boqimport.drop_qty0(copy.deepcopy(plain), "BOQ")
    assert res == plain, "nothing to leave out and nothing to note: not a byte moved"
    model = boqimport.editor_model(res)
    one, two = model["lines"]
    assert (one["total_qty"], one["supply_rate"]) == ("0", "1080")
    assert (two["total_qty"], two["install_rate"]) == ("0", "45")
    assert "_ro" not in one, "no chip is added: RO marks the cell, not a 0"


def test_a_negative_rate_is_a_rate():
    res = dropped([["1", "Credit", 0, "LS", -500, None, None, None]])
    assert rows_of(res) == [2] and "left_out" not in res


def test_rate_only_RO_lines_survive_with_or_without_a_rate():
    """ "RO" in the quantity is not the number 0 — even with no rate at all."""
    rows = [["1", "Pipe", "RO", "Mtr", 900, None, None, None],
            ["2", "Bend", "RO", "Nos", None, None, None, None],
            ["3", "Valve", 0, "Nos", None, None, None, None]]
    res = dropped(rows)
    kept = [l for l in res["lines"] if l["rate_only"]]
    assert [l["row"] for l in kept] == [2, 3], "every rate-only line survived"
    assert [e["row"] for e in res["left_out"]] == [4]


def test_quantity_0_no_rate_but_an_amount_is_kept_and_noted():
    rows = [["1", "Hangers", 0, "Nos", None, 1800, None, None],
            ["2", "Clamps", 0, "Nos", 0, None, None, 75]]
    plain = built(rows)
    res = dropped(rows)
    assert res["lines"] == plain["lines"], "kept exactly as the reader keeps it"
    assert "left_out" not in res
    assert [(e["row"], e["amounts"]) for e in res["qty0_kept"]] == [
        (2, {"supply_amount": 1800.0}), (3, {"install_amount": 75.0})]


def test_a_blank_quantity_with_a_blank_rate_is_kept_as_it_is():
    rows = [["1", "Pipe", None, "Mtr", None, None, None, None],
            ["2", "Bend", None, "Nos", 30, None, None, None],
            ["3", "Valve", 4, "Nos", 25, None, None, None]]
    plain = built(rows)
    res = boqimport.drop_qty0(copy.deepcopy(plain), "BOQ")
    assert res == plain
    model = boqimport.editor_model(res)
    assert [l["total_qty"] for l in model["lines"] if not l["is_header"]] == ["", "4"]


SPEC = [
    ["1", "MS pipe, heavy class", None, None, None, None, None, None],
    [None, "to IS 1239, painted", None, None, None, None, None, None],   # spec text
    [None, "a) 150 mm", 0, "Mtr", None, None, None, None],
    [None, "b) 100 mm", 0, "Mtr", 0, 0, None, None],
    ["2", "Butterfly valve", None, None, None, None, None, None],
    [None, "a) 150 mm", 2, "Nos", 900, None, None, None],
    [None, "b) 100 mm", 0, "Nos", None, None, None, None],
]


def test_a_parent_whose_children_all_drop_goes_with_its_words():
    res = dropped(SPEC)
    model = boqimport.editor_model(res)
    descs = [l["description"] for l in model["lines"]]
    assert "MS pipe, heavy class" not in " ".join(descs)
    assert [e["row"] for e in res["left_out"]] == [2, 3, 4, 5, 8]
    assert res["left_out"][1]["text"] == "to IS 1239, painted", "its spec text went with it"
    assert all("IS 1239" not in s["title"] for s in model["sections"]), \
        "a parent's words never land in a section title"


def test_a_parent_with_one_surviving_child_stays():
    model = boqimport.editor_model(dropped(SPEC))
    assert [(l["item_no"], l["is_header"]) for l in model["lines"]] == [
        ("2", True), ("2.a", False)]


def test_a_parent_that_is_itself_priced_stays_when_its_children_go():
    rows = [["1", "Pump set", 1, "Set", 250000, None, None, None],
            [None, "a) spare seal", 0, "Nos", None, None, None, None],
            [None, "b) spare impeller", 0, "Nos", 0, None, None, None]]
    res = dropped(rows)
    assert rows_of(res) == [2] and [e["row"] for e in res["left_out"]] == [3, 4]


def test_an_unpriced_quantity_0_parent_that_keeps_a_child_stays():
    rows = [["1", "Pipe", 0, "Mtr", None, None, None, None],
            [None, "a) 150 mm", 6, "Mtr", 900, None, None, None]]
    res = dropped(rows)
    assert rows_of(res) == [2, 3] and "left_out" not in res


def test_an_emptied_sub_header_empties_its_header():
    rows = [["1", "Sprinkler pipework", None, None, None, None, None, None],
            ["1.1", "Above ground", None, None, None, None, None, None],
            ["1.1.1", "150 mm", 0, "Mtr", None, None, None, None],
            ["2", "Valves", 3, "Nos", 600, None, None, None]]
    res = dropped(rows)
    assert rows_of(res) == [5] and [e["row"] for e in res["left_out"]] == [2, 3, 4]


def test_a_heading_with_nothing_under_it_to_begin_with_is_not_touched():
    """The ruling: headings are never left out directly (the work order, by
    contrast, drops one — its R3, the contractor's own terms)."""
    rows = [["1", "General notes", None, None, None, None, None, None],
            ["2", "Valve", 0, "Nos", None, None, None, None],
            ["3", "Pipe", 4, "Mtr", 100, None, None, None]]
    res = dropped(rows)
    assert rows_of(res) == [2, 4] and [e["row"] for e in res["left_out"]] == [3]


def test_a_section_left_with_no_lines_goes_and_a_heading_only_section_stays():
    rows = [["A", "SPRINKLER SYSTEM", None, None, None, None, None, None],
            ["1", "Pipe", 4, "Mtr", 100, None, None, None],
            ["B", "SPRAY SYSTEM", None, None, None, None, None, None],
            ["1", "Nozzles", None, None, None, None, None, None],
            [None, "a) 15 mm", 0, "Nos", None, None, None, None],
            ["C", "GENERAL", None, None, None, None, None, None],
            ["1", "Notes on testing", None, None, None, None, None, None]]
    res = dropped(rows)
    assert [s["code"] for s in res["sections"]] == ["A", "C"]
    assert res["section_src"] == ["sheet", "sheet"]
    assert res["left_out_sections"] == [{"tab": "BOQ", "code": "B", "title": "SPRAY SYSTEM"}]
    assert [e["row"] for e in res["left_out"]] == [5, 6]
    assert boqimport.editor_model(res)["sections"][1]["title"] == "GENERAL"


def test_a_sheet_whose_every_line_goes_still_opens(client):
    tok, _k = stage([("BOQ", [HEAD, ["1", "Pipe", 0, "Mtr", None, None, None, None],
                              ["2", "Bend", 0, "Nos", 0, 0, None, None]])])
    html, page = preview_and_form(client, tok)
    assert "<b>2</b> rows left out" in html and "<b>2</b> rows left out" in page
    assert model_of(page) == {"sections": [], "lines": []}


def test_the_counts_and_the_notes_move_with_the_lines():
    rows = [["1", "Pipe", 0, "Mtr", "Included", None, None, None],   # text: no price
            ["2", "Valve", 4, "Nos", 25, None, None, None]]
    plain = built(rows)
    res = dropped(rows)
    assert plain["counts"]["lines"] == 2 and res["counts"]["lines"] == 1
    assert plain["counts"]["as_remark"] == 1 and res["counts"]["as_remark"] == 0
    assert any(f["row"] == 2 for f in plain["flags"])
    assert not any(f["row"] == 2 for f in res["flags"]), "no note on a row the BOQ does not hold"


# ═══ 4. Through the import — preview, form, save; screen only ════════════════

SHEET = [HEAD,
         ["1", "Pipe 150 mm", 10, "Mtr", 100, 1000, 20, 200],
         ["2", "Pipe 80 mm", 0, "Mtr", None, None, None, None],      # left out
         ["3", "Bend", 0, "Nos", 0, 0, 0, 0],                        # left out
         ["4", "Valve", 0, "Nos", 900, 0, None, None],               # rate only: kept
         ["5", "Hanger", 0, "Nos", None, 1800, None, None],          # amount: kept, noted
         ["6", "Clamp", None, "Nos", None, None, 15, None],          # blank qty: kept
         ["7", "Tee", 2, "Nos", 50, 100, None, None]]


def test_the_preview_lists_every_row_left_out_by_row_and_description(client):
    tok, _k = stage([("Fire PR", SHEET)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    left = re.search(r'<details class="imp-group" id="imp-left" open>(.*?)</details>', html, re.S)
    assert left, "the list is OPEN on the preview"
    assert ("<b>2</b> rows left out &mdash; quantity 0 and no rate on the sheet, or a "
            "heading left with nothing under it") in left.group(1)
    assert ("Fire PR &mdash; row 3 &ldquo;Pipe 80 mm&rdquo;, row 4 &ldquo;Bend&rdquo;"
            in left.group(1))
    assert 'id="imp-qty0-kept" open' in html and "row 6 &ldquo;Hanger&rdquo;" in html
    assert "<b>2</b> rows left out &mdash; quantity 0, no rate</span>" in html, "the stats line"
    assert "<b>5</b> lines" in html, "the line count is what will be imported"


def test_the_form_carries_the_one_line_count_and_the_lines_that_stay(client):
    tok, _k = stage([("Fire PR", SHEET)])
    _html, page = preview_and_form(client, tok)
    assert re.search(r'<details class="imp-group" id="imp-left"><summary><b>2</b> rows left out', page), \
        "on the form the list is FOLDED: its summary is the one-line count"
    model = model_of(page)
    assert [l["item_no"] for l in model["lines"]] == ["1", "4", "5", "6", "7"]
    by = {l["item_no"]: l for l in model["lines"]}
    assert (by["4"]["total_qty"], by["4"]["supply_rate"]) == ("0", "900")
    assert (by["5"]["total_qty"], by["5"]["supply_rate"]) == ("0", "")
    assert by["6"]["total_qty"] == "" and by["6"]["install_rate"] == "15"


def test_the_saved_boq_holds_what_stayed_and_no_trace_of_the_report(client):
    tok, _k = stage([("Fire PR", SHEET)])
    _html, page = preview_and_form(client, tok)
    rec = save_model(client, model_of(page))
    assert isinstance(rec, dict), rec[:2000]
    assert [l["item_no"] for l in rec["line_items"]] == ["1", "4", "5", "6", "7"]
    assert "left out" not in json.dumps(rec) and "left_out" not in json.dumps(rec)
    # Nothing left out carried an amount: the subtotals are the sheet's own.
    assert rec["supply_subtotal"] == pytest.approx(1000.0 + 0.0 + 100.0)
    assert rec["install_subtotal"] == pytest.approx(200.0)
    printed = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
    assert "left out" not in printed and "Pipe 80 mm" not in printed and "Bend" not in printed


def test_the_totals_check_and_the_sums_do_not_move(client):
    # SHEET without its row 5 (an amount and no rate, kept by rule (c)): the
    # grand-total check is quantity x rate, which that row is outside of by the
    # reader's own rule, so it is left out of a sheet that has to foot.
    sheet = [r for r in SHEET if r[0] != "5"] + [[None, "TOTAL", None, None, None, 1100, None, 200]]
    rec = {"grid": [grid_of(sheet)], "sheets": [{"name": "BOQ", "staged": True}],
           "sheet_index": 0, "ticked": [0], "mapping": SI.advised_mapping(grid_of(sheet))}
    merged = boqimport.build_tabs(rec)
    plain = SI.build(rec["grid"][0], SI.clean_mapping(rec["grid"][0], rec["mapping"]))
    assert merged["totals"] == plain["totals"] and merged["checks"] == plain["checks"]
    assert merged["totals"]["status"] == "match" and merged["left_out"]

    def sums(model):
        out = {"supply": 0.0, "install": 0.0}
        for l in model["lines"]:
            for t in out:
                if l["total_qty"] not in ("", None) and l[f"{t}_rate"] not in ("", None):
                    out[t] += float(l["total_qty"]) * float(l[f"{t}_rate"])
        return out
    assert sums(boqimport.editor_model(merged)) == sums(boqimport.editor_model(plain))


def test_a_sheet_the_rule_does_not_touch_imports_byte_for_byte_as_before(client):
    rows = [HEAD, ["1", "Pipe", 10, "Mtr", 100, 1000, None, None],
            ["2", "Valve", 0, "Nos", 900, 0, None, None]]
    rec = {"grid": [grid_of(rows)], "sheets": [{"name": "BOQ", "staged": True}],
           "sheet_index": 0, "ticked": [0], "mapping": SI.advised_mapping(grid_of(rows))}
    merged = boqimport.build_tabs(rec)
    plain = SI.build(rec["grid"][0], SI.clean_mapping(rec["grid"][0], rec["mapping"]))
    plain["tab_totals"] = []
    assert merged == plain
    assert not any(k in merged for k in boqimport.QTY0_REPORT_KEYS)
    tok, _k = stage([("BOQ", rows)])
    html, page = preview_and_form(client, tok)
    assert 'id="imp-left"' not in html and 'id="imp-left"' not in page
    assert 'id="imp-qty0-kept"' not in html


def test_two_tabs_are_counted_and_listed_per_tab(client):
    one = [HEAD, ["1", "Pipe", 4, "Mtr", 100, None, None, None],
           ["2", "Bend", 0, "Nos", None, None, None, None]]
    two = [HEAD, ["1", "Nozzle", 0, "Nos", 0, None, None, None],
           ["2", "Hose", 0, "Nos", None, None, None, None],
           ["3", "Coupling", 3, "Nos", 40, None, None, None]]
    tok, _k = stage([("Sprinkler", one), ("Spray", two)])
    first = rendered_form(client.get(f"/boq/import/{tok}").get_data(as_text=True))
    client.post(f"/boq/import/{tok}", data=dict(first, tab=["0", "1"], action="update"))
    html, page = preview_and_form(client, tok)
    assert "<b>3</b> rows left out" in html and "<b>3</b> rows left out" in page
    assert "Sprinkler &mdash; row 3 &ldquo;Bend&rdquo;</li>" in html
    assert "Spray &mdash; row 2 &ldquo;Nozzle&rdquo;, row 3 &ldquo;Hose&rdquo;</li>" in html
    model = model_of(page)
    assert [(s["code"], s["title"]) for s in model["sections"]] == [("A", "Sprinkler"),
                                                                     ("B", "Spray")]
    assert [l["description"] for l in model["lines"]] == ["Pipe", "Coupling"]


def test_a_tab_the_rule_empties_takes_no_letter():
    """Each tab is dropped BEFORE the merge, so an emptied tab never takes a
    section code the next tab would have had."""
    one = [HEAD, ["1", "Bend", 0, "Nos", None, None, None, None]]
    two = [HEAD, ["1", "Coupling", 3, "Nos", 40, None, None, None]]
    grids = [grid_of(one, "Gone"), grid_of(two, "Kept")]
    rec = {"grid": grids, "sheet_index": 0, "ticked": [0, 1],
           "sheets": [{"name": "Gone", "staged": True}, {"name": "Kept", "staged": True}],
           "mapping": SI.advised_mapping(grids[0]),
           "tab_maps": {"1": SI.advised_mapping(grids[1])}}
    merged = boqimport.build_tabs(rec)
    assert merged["sections"] == [{"code": "A", "title": "Kept"}]
    assert [e["tab"] for e in merged["left_out"]] == ["Gone"]
    assert merged["left_out_sections"][0]["tab"] == "Gone"


def test_cost_mode_leaves_out_the_same_rows(client):
    tok, _k = stage([("Fire PR", SHEET)])
    html, page = preview_and_form(client, tok, rate_mode="cost", markup="10")
    assert "<b>2</b> rows left out" in html and "<b>2</b> rows left out" in page
    model = model_of(page)
    assert [l["item_no"] for l in model["lines"]] == ["1", "4", "5", "6", "7"]
    by = {l["item_no"]: l for l in model["lines"]}
    assert (by["4"]["supply_base_rate"], by["4"]["supply_escalation_pct"]) == ("900", "10")


def test_an_unticked_rate_column_holding_a_number_does_not_save_the_row(client):
    rows = [HEAD, ["1", "Pipe", 4, "Mtr", 100, None, None, None],
            ["2", "Bend", 0, "Nos", None, None, 55, None]]
    tok, _k = stage([("BOQ", rows)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    assert form.pop("use_0_6") == "1"                 # untick the installation rate
    form.pop("use_0_7", None)
    r = client.post(f"/boq/import/{tok}", data=form)
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert [l["description"] for l in model_of(page)["lines"]] == ["Pipe"]
    assert "<b>1</b> row left out" in page
    # …and ticked, the same 55 keeps it. (The layout now remembers column G as
    # unticked, so it is ticked back by hand, as the user would.)
    tok2, _k = stage([("BOQ", rows)])
    _h, page2 = preview_and_form(client, tok2, use_0_6="1", map_0_6="install_rate")
    assert [l["description"] for l in model_of(page2)["lines"]] == ["Pipe", "Bend"]


def test_a_known_layout_goes_straight_to_the_form_and_still_leaves_out(client):
    tok, _k = stage([("Fire PR", SHEET)])
    preview_and_form(client, tok)                       # confirmed: the layout is known
    tok2, known = stage([("Fire PR", SHEET)])
    assert known is True
    page = client.get(f"/boq/import/{tok2}/form").get_data(as_text=True)
    assert "<b>2</b> rows left out" in page
    assert [l["item_no"] for l in model_of(page)["lines"]] == ["1", "4", "5", "6", "7"]


def test_the_import_calls_the_one_shared_predicate(monkeypatch):
    calls = []
    real = SI.qty0_unpriced

    def spy(qty, figures):
        calls.append(qty)
        return real(qty, figures)
    monkeypatch.setattr(SI, "qty0_unpriced", spy)
    boqimport.drop_qty0(built([["1", "Pipe", 0, "Mtr", None, None, None, None]]))
    assert calls, "boqimport.drop_qty0() asks sheetimport.qty0_unpriced()"
    calls.clear()
    W._drop_qty0([{"is_header": False, "qty": "0", "labour_rate": "", "_row": 2}], "labour")
    assert calls, "workorder._drop_qty0() asks the same function"


# ═══ 5. The typed form — untouched ═══════════════════════════════════════════

def _line(**kw):
    li = {"line_id": "", "item_no": "1", "parent_item_no": "", "section": "A",
          "is_header": False, "description": "Pipe", "remark": "", "unit": "Mtr",
          "area_qty": {}, "total_qty": "0",
          "supply_base_rate": "", "supply_escalation_pct": "", "supply_rate": "",
          "supply_hsn": "", "supply_gst_rate": "",
          "install_base_rate": "", "install_escalation_pct": "", "install_rate": "",
          "install_sac": "", "install_gst_rate": ""}
    li.update(kw)
    return li


@pytest.mark.parametrize("rate", ["", "0"])
def test_a_quantity_0_typed_by_hand_still_saves(client, rate):
    model = {"sections": [{"code": "A", "title": "", "areas": []}],
             "lines": [_line(supply_rate=rate), _line(item_no="2", total_qty="3",
                                                     supply_rate="10")]}
    rec = save_model(client, model)
    assert isinstance(rec, dict), rec[:2000]
    first = rec["line_items"][0]
    assert first["total_qty"] == 0.0 and first["item_no"] == "1"
    assert first["supply_rate"] == (None if rate == "" else 0.0)


def test_a_revision_keeps_a_quantity_0_line(client):
    rec = save_model(client, {"sections": [{"code": "A", "title": "", "areas": []}],
                              "lines": [_line(), _line(item_no="2", total_qty="3",
                                                       supply_rate="10")]})
    page = client.get(f"/boq/create?revise={rec['id']}").get_data(as_text=True)
    lines = model_of(page)["lines"]
    assert [(l["item_no"], l["total_qty"]) for l in lines] == [("1", "0"), ("2", "3")]


# ═══ 6. The work order — the shared call leaves out exactly what it did ══════

def _old_wo_row_test(r, declared):
    """`workorder._drop_qty0()`'s row test as it stood at 6c1cb90, verbatim but
    for its helper inlined — the reference the shared call is held to:

        if r.get("is_header") or not _is_zero(r.get("qty")):
            continue
        rated = any((_figure(r.get(f))[0] or 0) > 0 for f in declared)
        if not rated:
            drop.add(i)
        elif "rate only" not in str(r.get("note") or "").lower():
            <note>
    """
    v, why = W._figure(r.get("qty"))
    if r.get("is_header") or not (why == "" and v == 0):
        return "kept"
    rated = any((W._figure(r.get(f))[0] or 0) > 0 for f in declared)
    return "dropped" if not rated else "noted"


QTYS = ["0", "0.0", "-0", " 0 ", "0,0", "", None, "abc", "5", "-1", "1e20", "nan", "inf", "1,000"]
RATES = ["", None, "0", "0.00", "-5", "5", "abc", "1e20", "nan", "inf"]


@pytest.mark.parametrize("tracks", ["both", "labour", "material"])
def test_the_work_orders_rows_are_exactly_what_they_were(tracks):
    declared = W.TRACK_RATES[tracks]
    checked = 0
    for q in QTYS:
        for m in RATES:
            for lab in RATES:
                row = {"is_header": False, "item_no": "1", "description": "x", "_row": 9,
                       "_parent": "", "_sec": None, "qty": q,
                       "material_rate": m, "labour_rate": lab, "note": ""}
                want = _old_wo_row_test(row, declared)
                left = []
                kept = W._drop_qty0([dict(row)], tracks, "T", left)
                got = ("dropped" if not kept else
                       "noted" if "rate only" in kept[0]["note"] else "kept")
                assert got == want, (tracks, q, m, lab, got, want)
                assert (left == [("T", 9)]) == (want == "dropped")
                checked += 1
    assert checked == len(QTYS) * len(RATES) ** 2


def test_the_work_orders_own_labour_only_sheet_still_leaves_out_its_four_rows(client):
    """The R3 acceptance in `tests/test_wo_nxtra.py`, its synthetic sheet,
    read through the shared call: the same rows, the same note."""
    import test_wo_nxtra as WX
    g = SI.from_rows([("S", "visible", WX.LABOUR_ONLY)])["grid"][0]
    mapping = W.guess_mapping(g)
    si_map = {c: (W._TO_SI.get(t, "") if t != SI.UNDECIDED else "") for c, t in mapping.items()}
    left = []
    rows = W.rows_from_build(SI.build(g, si_map, guided=True), mapping,
                             W.item_column_values(g, mapping), tracks="labour",
                             tab_name="Sprinkler", left_out=left)
    assert [row for _t, row in left] == [7, 8, 9, 10]
    assert any("rate only — quantity 0 on the sheet" in r["note"] for r in rows)
