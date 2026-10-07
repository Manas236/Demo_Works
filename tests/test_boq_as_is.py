"""
The BOQ opens AS IT IS — blank stays blank, 0 stays 0, nothing blocks on a
blank (6 October 2026, CLIENT_CHANGES.md §0, forty-fifth block, A1–A8).

Every workbook here is BUILT IN MEMORY (`sheetimport.from_rows()`, or openpyxl
in memory where a cell FORMAT or a FORMULA is the point); no binary is
committed and no text from a client's real sheet appears in this file.

The load-bearing rules, each with its tests below:

* A1 — the reader brings every mapped cell through as the sheet has it:
  blank → None, 0 → 0, text in a numeric column → None plus "<Field>: <text>"
  in the remark, an Excel error → "<Field>: #VALUE! in sheet", a bare "-" →
  blank, an accounting-format 0 → 0, a formula's cached "" → blank, a fully
  empty row → no line;
* A2 — a quantity × rate that differs from the sheet's amount KEEPS the rate
  and is an amber note giving both figures, never a need;
* A3 — blank is a valid saved state on the import, the typed form and a
  revision: nothing is asked for, nothing is ringed, the save never stops on
  a blank; text TYPED into a numeric box is refused, naming the line;
* A4 — amount = quantity × net rate only when both are present; totals sum
  what is present and say on screen what they skipped;
* A5 — the print shows a blank as a blank cell and a 0 as 0;
* A6 — RA: a line with no rate is greyed, refused and skipped by a prefill; a
  blank quantity takes the rate-only line's rule; the purchase / challan /
  draft-PO / measurement grid prefills a blank quantity blank; the project
  page says "N lines not priced";
* A8 — the net rate rounds HALF UP (Excel's ROUND), Python and the editor's
  JavaScript alike.
"""

import io
import json
import re
import shutil
import subprocess

import pytest

import boq
import boqimport
import boqpick
import conftest
import ra
import sheetimport as SI
from store import STORE

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


# ═══ Helpers ═════════════════════════════════════════════════════════════════

HEAD = ["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount",
        "Installation Rate", "Installation Amount"]
MAP = {"0": "item_no", "1": "description", "2": "qty", "3": "unit",
       "4": "supply_rate", "5": "supply_amount", "6": "install_rate",
       "7": "install_amount"}


def grid_of(rows, name="BOQ"):
    return SI.from_rows([(name, "visible", rows)])["grid"][0]


def built(rows, mapping=None, guided=False):
    g = grid_of([HEAD] + rows)
    return SI.build(g, dict(mapping or MAP), guided=guided)


def line_at(res, row):
    return next(l for l in res["lines"] if l["row"] == row)


def a_line(**kw):
    li = {"line_id": "", "item_no": "1", "parent_item_no": "", "section": "A",
          "is_header": False, "description": "Pipe", "remark": "", "unit": "Mtr",
          "area_qty": {}, "total_qty": "10",
          "supply_base_rate": "", "supply_escalation_pct": "", "supply_rate": "100",
          "supply_hsn": "", "supply_gst_rate": "",
          "install_base_rate": "", "install_escalation_pct": "", "install_rate": "",
          "install_sac": "", "install_gst_rate": "",
          "supply_disc_pct": "", "install_disc_pct": ""}
    li.update(kw)
    return li


def one_section(*lines, areas=()):
    return {"sections": [{"code": "A", "title": "", "areas": list(areas)}],
            "lines": list(lines)}


def save_model(client, model, **form):
    """POST a model to /boq/create the way the editor would; the saved record,
    or the refusal page's text."""
    data = {"date": "2026-10-06", "project_name": "P", "account_name": "A",
            "boq_json": json.dumps(model)}
    data.update(form)
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data=data)
    new = set(STORE["boqs"]) - before
    if r.status_code == 302 and new:
        return STORE["boqs"][new.pop()]
    return r.get_data(as_text=True)


def markup(html):
    """The page with its scripts taken out — what is RENDERED, not what a
    comment in `_BOQ_JS` says about what used to be."""
    return re.sub(r"<(script|style)>.*?</\1>", "", html, flags=re.S)


def table_of(html):
    """The section tables of a BOQ page, letterhead and totals left out."""
    return html[html.index('<table class="boq-table">'):html.index('<div class="boq-grand">')]


def cells(html, row_text):
    """The <td> texts of the one table row that carries `row_text`."""
    for tr in re.findall(r'<tr class="row-line">(.*?)</tr>', html, re.S):
        if row_text in tr:
            return [re.sub(r"<[^>]+>", "", td).strip()
                    for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
    raise AssertionError(f"no row carries {row_text!r}")


# ═══ A1. The reader — every mapped cell as the sheet has it ══════════════════

def test_blank_is_none_and_zero_is_zero_for_every_numeric_target():
    res = built([["1", "Blanks", None, "Nos", None, None, None, None],
                 ["2", "Zeros", 0, "Nos", 0, 0, 0, 0],
                 ["3", "Figures", 4, "Nos", 25, 100, 5, 20]])
    blanks, zeros, figures = (line_at(res, r) for r in (2, 3, 4))
    for f in ("qty", "supply_rate", "install_rate"):
        assert blanks[f] is None, (f, "blank is ABSENT, never 0")
        assert zeros[f] == 0.0 and zeros[f] is not None, (f, "0 is 0")
    assert (figures["qty"], figures["supply_rate"], figures["install_rate"]) == (4.0, 25.0, 5.0)
    assert not res["needs"] and not any(l["block"] for l in res["lines"])


def test_base_escalation_and_discount_blank_or_zero_come_through_as_they_are():
    head = ["Sr", "Description", "Qty", "Base", "Esc %", "Rate", "Disc %"]
    m = {"0": "item_no", "1": "description", "2": "qty", "3": "supply_base_rate",
         "4": "escalation_pct", "5": "supply_rate", "6": "supply_disc_pct"}
    g = grid_of([head, ["1", "Blank", 1, None, None, 10, None],
                 ["2", "Zero", 1, 0, 0, 10, 0]])
    res = SI.build(g, m)
    a, b = line_at(res, 2), line_at(res, 3)
    for f in ("supply_base_rate", "escalation_pct", "supply_disc_pct"):
        assert a[f] is None, f
        assert b[f] == 0.0, f


@pytest.mark.parametrize("text", ["Included", "By client", "NA", "Nil", "Lumpsum", "9.3+1.5+6"])
def test_text_in_a_numeric_column_is_blank_and_kept_in_the_remark(text):
    res = built([["1", "Pipe", text, "Mtr", 100, None, None, None]])
    li = line_at(res, 2)
    assert li["qty"] is None, "the figure is absent — never 0, never guessed"
    assert li["as_remark"] == [f"Qty: {text}"]
    assert not li["needs"] and not li["block"] and not res["needs"]
    assert not li["flags"], "kept in the remark — no chip on the line"
    model = boqimport.editor_model(res)
    assert model["lines"][0]["remark"] == f"Qty: {text}"
    assert model["lines"][0]["total_qty"] == ""
    assert "_need" not in model["lines"][0] and "_block" not in model["lines"][0]


def test_text_in_a_rate_column_goes_to_the_remark_after_the_sheets_own_words():
    head = HEAD + ["Make", "Remarks"]
    m = dict(MAP, **{"8": "make", "9": "remark"})
    res = SI.build(grid_of([head, ["1", "Valve", 2, "Nos", "By client", None, 50, 100,
                                   "Kirloskar", "as per drawing"]]), m)
    li = line_at(res, 2)
    assert li["supply_rate"] is None and li["install_rate"] == 50.0
    row = boqimport.editor_model(res)["lines"][0]
    assert row["remark"] == "as per drawing; Make: Kirloskar; Supply rate: By client"


def test_a_bare_dash_is_blank_with_no_remark():
    res = built([["1", "Pipe", 3, "Mtr", "-", None, "-", None]])
    li = line_at(res, 2)
    assert li["supply_rate"] is None and li["install_rate"] is None
    assert li["as_remark"] == [] and not res["flags"]


def test_a_dash_quantity_is_blank_too():
    res = built([["1", "Pipe", "-", "Mtr", 100, None, None, None]])
    li = line_at(res, 2)
    assert li["qty"] is None and li["as_remark"] == []


@pytest.mark.parametrize("err", ["#VALUE!", "#REF!", "#DIV/0!", "#N/A"])
def test_an_excel_error_is_blank_and_said_in_the_remark(err):
    res = built([["1", "Pipe", 10, "Mtr", err, None, None, None]])
    li = line_at(res, 2)
    assert li["supply_rate"] is None
    assert li["as_remark"] == [f"Supply rate: {err} in sheet"]
    assert not res["needs"]


def test_a_fully_empty_row_is_not_a_line():
    res = built([["1", "Pipe", 10, "Mtr", 100, None, None, None],
                 [None, None, None, None, None, None, None, None],
                 ["2", "Bend", 5, "Nos", 20, None, None, None]])
    assert [l["row"] for l in res["lines"]] == [2, 4]


def _xlsx(rows, fmt=None, formulas=()):
    openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOQ"
    for r in rows:
        ws.append(r)
    for ref, number_format in (fmt or {}).items():
        ws[ref].number_format = number_format
    for ref, formula in formulas:
        ws[ref] = formula
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ACCOUNTING = '_(* #,##0.00_);_(* (#,##0.00);_(* "-"??_);_(@_)'


def test_an_accounting_format_zero_that_shows_a_dash_is_zero():
    """The VALUE wins: Excel shows "-" for this 0, the cell holds 0."""
    data = _xlsx([HEAD, ["1", "Pipe", 10, "Mtr", 0, 0, 120, 1200]],
                 fmt={"E2": ACCOUNTING, "F2": ACCOUNTING})
    st = SI.read(data, "t.xlsx")
    res = SI.build(st["grid"][0], MAP)
    li = line_at(res, 2)
    assert li["supply_rate"] == 0.0 and li["install_rate"] == 120.0
    assert li["as_remark"] == []


def test_a_formula_with_no_saved_value_is_blank_and_counted_not_flagged():
    """openpyxl writes formulas WITHOUT a cached value, which is exactly the
    reading of a cached "" — the two cannot be told apart (ABOUT.md §5)."""
    data = _xlsx([HEAD, ["1", "Pipe", 10, "Mtr", 100, None, None, None]],
                 formulas=[("G2", '=IF(1=1,"",5)')])
    st = SI.read(data, "t.xlsx")
    g = st["grid"][0]
    assert "formula" in g["kinds"].values(), "the fixture must carry a formula cell"
    res = SI.build(g, MAP)
    li = line_at(res, 2)
    assert li["install_rate"] is None and li["as_remark"] == []
    assert res["counts"]["formula_blank"] == 1
    assert not [f for f in res["flags"] if f["kind"] == "formula"]


def test_a_formula_cached_empty_string_is_blank():
    """The cached-"" case built by hand: <c t="str"><f>…</f><v></v></c>."""
    import zipfile
    data = _xlsx([HEAD, ["1", "Pipe", 10, "Mtr", 100, None, 7, None]])
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w")
    for n in zin.namelist():
        b = zin.read(n)
        if n == "xl/worksheets/sheet1.xml":
            s = b.decode()
            s, k = re.subn(r'<c r="G2"[^>]*>.*?</c>',
                           '<c r="G2" t="str"><f>IF(1=1,"",5)</f><v></v></c>', s)
            assert k == 1
            b = s.encode()
        zout.writestr(n, b)
    zout.close()
    res = SI.build(SI.read(out.getvalue(), "t.xlsx")["grid"][0], MAP)
    li = line_at(res, 2)
    assert li["install_rate"] is None and li["as_remark"] == []


# ═══ A2. A mismatch keeps the rate and is a note ══════════════════════════════

def test_a_mismatch_keeps_the_rate_and_is_a_non_blocking_note():
    res = built([["1", "Pipe", 10, "Mtr", 100, 1500, None, None]])
    li = line_at(res, 2)
    assert li["supply_rate"] == 100.0, "never blanked — the rate is the sheet's"
    assert not li["needs"] and not res["needs"] and not li["block"]
    notes = [f for f in res["flags"] if f["kind"] == "as_mismatch"]
    assert len(notes) == 1 and notes[0]["severity"] == "amber"
    msg = notes[0]["message"]
    assert "the sheet says 1,500" in msg and "the BOQ computes 1,000" in msg
    assert msg in li["flags"], "a note on the line's chip — amber, not red"


def test_the_work_order_keeps_the_guided_rules():
    """`guided=True` is the 30 September rule set, which `workorder.py` passes."""
    res = built([["1", "Pipe", 10, "Mtr", 100, 1500, None, None]], guided=True)
    li = line_at(res, 2)
    assert li["supply_rate"] is None, "guided: the mismatched rate is left blank"
    assert [n["field"] for n in li["needs"]] == ["supply_rate"]
    res = built([["1", "Pipe", "NA", "Mtr", 100, None, None, None]], guided=True)
    assert line_at(res, 2)["block"], "guided: a word in the quantity blocks"


def test_no_line_needs_anything_as_it_is():
    res = built([[None, "No number, no figures", None, None, 100, None, None, None],
                 ["2", None, 5, "Nos", None, None, None, None],
                 ["3", "RO line", "RO", "Nos", None, None, None, None],
                 ["4", "An amount, no rate", 2, "Nos", None, 400, None, None]])
    assert res["needs"] == []
    assert all(not l["needs"] and not l["block"] for l in res["lines"])
    four = line_at(res, 5)
    assert any("the sheet says 400" in m and "no supply rate" in m for m in four["flags"])


def test_the_rate_only_line_keeps_its_zero_and_its_sheet_zero_rate():
    res = built([["1", "Flange", "RO", "Nos", 0, None, None, None]])
    li = line_at(res, 2)
    assert li["rate_only"] and li["qty"] == 0.0
    assert li["supply_rate"] == 0.0, "the sheet's 0 rate stays 0 (A1)"


def test_the_net_rate_note_keeps_rate_and_discount():
    head = ["Sr", "Description", "Qty", "Rate", "Disc %", "Net"]
    m = {"0": "item_no", "1": "description", "2": "qty", "3": "supply_rate",
         "4": "supply_disc_pct", "5": "supply_net_rate"}
    res = SI.build(grid_of([head, ["1", "Pipe", 2, 100, 10, 80]]), m)
    li = line_at(res, 2)
    assert li["supply_rate"] == 100.0 and li["supply_disc_pct"] == 10.0
    assert any(f["kind"] == "as_net" for f in res["flags"]) and not res["needs"]


def test_a_discount_above_100_is_kept_in_the_remark_not_dropped():
    head = ["Sr", "Description", "Qty", "Rate", "Disc"]
    m = {"0": "item_no", "1": "description", "2": "qty", "3": "supply_rate",
         "4": "supply_disc_pct"}
    res = SI.build(grid_of([head, ["1", "Pipe", 2, 100, 250]]), m)
    li = line_at(res, 2)
    assert li["supply_disc_pct"] is None and li["as_remark"] == ["Supply disc %: 250"]


def test_the_half_up_net_rate_is_the_same_in_the_reader_and_the_boq():
    for unit, disc in ((2.5, 15), (10.05, 50), (1.15, 50), (2024, 10), (0.75, 50)):
        assert SI._half_up(unit * (100 - disc) / 100) == boq.net_of(unit, disc)


# ═══ The preview and the prefilled form ═══════════════════════════════════════

def _stage(rows_by_tab):
    wb = SI.from_rows([(t, "visible", rows) for t, rows in rows_by_tab])
    tok, _known = boqimport.stage(wb, "sheet.xlsx", conftest.ensure_test_user()["id"])
    return tok


def _rendered(html):
    form = {"picker": "1", "action": "confirm"}
    for name, opts in re.findall(r'<select name="(map_\d+_\d+)"[^>]*>(.*?)</select>', html, re.S):
        mm = re.search(r'<option value="([^"]*)" selected>', opts)
        form[name] = mm.group(1) if mm else ""
    for name in re.findall(r'<input type="checkbox" name="(use_\d+_\d+)" value="1" checked', html):
        form[name] = "1"
    form["tab"] = re.findall(r'<input type="checkbox" name="tab" value="(\d+)" checked', html)
    return form


SHEET = [["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount"],
         ["1", "Pipe 100 mm", 10, "Mtr", 100, 1000],
         ["2", "Pipe 80 mm", None, "Mtr", 80, None],
         ["3", "Valve", 4, "Nos", None, None],
         ["4", "Bend", 0, "Nos", 0, 0],
         ["5", "Hanger", "Included", "Nos", 30, None],
         ["6", "Flange", 2, "Nos", 50, 999]]


def test_the_preview_and_the_form_never_ask_for_anything(client):
    tok = _stage([("BOQ", SHEET)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "need you" not in html and "Nothing blocks the save." in html
    assert "2 lines have no quantity" in html and "1 line has no rate" in html
    assert "the sheet says 999" in html, "the mismatch, both figures, on the preview"
    assert "Hanger" in html or "Included" in html
    r = client.post(f"/boq/import/{tok}", data=_rendered(html))
    assert r.status_code == 303
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\nvar SPECS", page, re.S).group(1))
    by_no = {l["item_no"]: l for l in model["lines"]}
    assert by_no["2"]["total_qty"] == "" and by_no["3"]["supply_rate"] == ""
    # ⚠ AMENDED 7 October 2026 — CLIENT_CHANGES.md §0, forty-sixth block, which
    #   NARROWS the forty-fifth block's "0 stays 0" for the import's line rows:
    #   "4 Bend" has quantity 0, a 0 rate and a 0 amount, so it is LEFT OUT and
    #   listed. The assertion as it stood:
    #     assert by_no["4"]["total_qty"] == "0" and by_no["4"]["supply_rate"] == "0"
    #   A 0 on a line that carries a rate still comes through as 0 —
    #   tests/test_boq_import_qty0.py holds that, through the same import.
    assert "4" not in by_no, "quantity 0, no rate, no amount: left out"
    assert "<b>1</b> row left out" in html and "row 5 &ldquo;Bend&rdquo;" in html
    assert "<b>1</b> row left out" in page, "the prefilled form carries the same count"
    assert by_no["5"]["total_qty"] == "" and by_no["5"]["remark"] == "Qty: Included"
    assert by_no["6"]["supply_rate"] == "50", "the mismatched rate is kept"
    for l in model["lines"]:
        assert "_need" not in l and "_block" not in l
    shown = markup(page)
    assert 'id="needs-bar"' not in shown and "need you" not in shown
    assert "Not priced" not in shown and 'class="np-btn"' not in shown
    assert "has-red" not in shown


def test_the_imported_boq_saves_exactly_as_the_sheet_is(client):
    tok = _stage([("BOQ", SHEET)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    r = client.post(f"/boq/import/{tok}", data=_rendered(html))
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\nvar SPECS", page, re.S).group(1))
    rec = save_model(client, model, account_name="")
    assert isinstance(rec, dict), rec[:2000]
    by_no = {l["item_no"]: l for l in rec["line_items"]}
    assert by_no["1"]["total_qty"] == 10.0 and by_no["1"]["supply_amount"] == 1000.0
    assert by_no["2"]["total_qty"] is None and by_no["2"]["supply_amount"] is None
    assert by_no["3"]["supply_rate"] is None and by_no["3"]["supply_amount"] is None
    # ⚠ AMENDED 7 October 2026 — CLIENT_CHANGES.md §0, forty-sixth block: "4 Bend"
    #   (quantity 0, a 0 rate, a 0 amount) is left out of the import, so it is
    #   not saved. The assertions as they stood:
    #     assert by_no["4"]["total_qty"] == 0.0 and by_no["4"]["supply_rate"] == 0.0
    #     assert by_no["4"]["supply_amount"] == 0.0
    #   It carried an amount of 0, so the subtotal below did not move.
    assert "4" not in by_no and len(rec["line_items"]) == 5
    assert by_no["5"]["remark"] == "Qty: Included" and by_no["5"]["total_qty"] is None
    assert by_no["6"]["supply_rate"] == 50.0 and by_no["6"]["supply_amount"] == 100.0
    assert rec[boq.BLANK_MODEL_KEY] == boq.BLANK_MODEL
    assert rec["supply_subtotal"] == pytest.approx(1000.0 + 0.0 + 100.0)


# ═══ A3. The save — blank is a valid state ═══════════════════════════════════

@pytest.mark.parametrize("box", ["total_qty", "supply_rate", "supply_base_rate",
                                 "supply_escalation_pct", "supply_disc_pct",
                                 "install_rate", "install_base_rate",
                                 "install_escalation_pct", "install_disc_pct"])
def test_blank_saves_absent_and_zero_saves_zero(client, box):
    rec = save_model(client, one_section(a_line(**{box: ""}),
                                         a_line(item_no="2", **{box: "0"})))
    blank, zero = rec["line_items"]
    want_blank = None
    if box.endswith("_disc_pct"):
        assert box not in blank, "a discount nobody typed is ABSENT"
    else:
        assert blank[box] is want_blank, (box, blank[box])
    assert zero[box] == 0.0 and zero[box] is not None


def test_amount_is_absent_when_qty_or_rate_is_blank_and_zero_for_a_zero(client):
    rec = save_model(client, one_section(
        a_line(total_qty="", supply_rate="100"),
        a_line(item_no="2", total_qty="5", supply_rate=""),
        a_line(item_no="3", total_qty="0", supply_rate="100"),
        a_line(item_no="4", total_qty="5", supply_rate="0"),
        a_line(item_no="5", total_qty="5", supply_rate="100")))
    amts = [l["supply_amount"] for l in rec["line_items"]]
    assert amts == [None, None, 0.0, 0.0, 500.0]
    assert [l["install_amount"] for l in rec["line_items"]] == [None] * 5
    assert rec["supply_subtotal"] == 500.0 and rec["subtotal"] == 500.0


def test_a_boq_with_every_rate_blank_saves(client):
    rec = save_model(client, one_section(
        a_line(supply_rate=""), a_line(item_no="2", supply_rate="", total_qty="")))
    assert isinstance(rec, dict)
    assert all(l["supply_rate"] is None for l in rec["line_items"])
    assert rec["subtotal"] == 0.0


def test_item_number_description_unit_and_account_may_all_be_blank(client):
    rec = save_model(client, one_section(a_line(item_no="", description="", unit="",
                                                total_qty="", supply_rate="")),
                     account_name="")
    assert isinstance(rec, dict), rec[:1500]
    li = rec["line_items"][0]
    assert (li["item_no"], li["description"], li["unit"]) == ("", "", "")
    assert rec["account_name"] == ""


def test_a_blank_escalation_beside_a_base_is_absent_and_nothing_is_derived(client):
    rec = save_model(client, one_section(a_line(supply_base_rate="100",
                                                supply_escalation_pct="", supply_rate="")))
    li = rec["line_items"][0]
    assert li["supply_base_rate"] == 100.0
    assert li["supply_escalation_pct"] is None, "a blank escalation is not 0%"
    assert li["supply_rate"] is None, "a blank rate is not filled from base × (1 + esc)"
    assert li["supply_amount"] is None


def test_an_area_section_with_no_area_figure_has_a_blank_quantity(client):
    model = one_section(a_line(area_qty={"L1": "", "L2": ""}, total_qty=""),
                        a_line(item_no="2", area_qty={"L1": "0"}, total_qty=""),
                        areas=("L1", "L2"))
    rec = save_model(client, model)
    a, b = rec["line_items"]
    assert a["total_qty"] is None and a["area_qty"] == {}
    assert b["total_qty"] == 0.0 and b["area_qty"] == {"L1": 0.0}


@pytest.mark.parametrize("box", ["total_qty", "supply_rate", "supply_base_rate",
                                 "supply_escalation_pct", "install_rate",
                                 "supply_gst_rate"])
def test_text_typed_into_a_numeric_box_is_refused_naming_the_line(client, box):
    body = save_model(client, one_section(a_line(item_no="7.b", **{box: "abc"})))
    assert isinstance(body, str), "text in a numeric box is the one value refusal left"
    assert "Line 7.b" in body and "is not a number" in body
    assert f'"_err": ["{box}"]' in body


def test_a_percent_sign_and_thousands_commas_are_numbers(client):
    rec = save_model(client, one_section(a_line(supply_base_rate="1,760",
                                                supply_escalation_pct="15%",
                                                supply_rate="2,024", supply_gst_rate="18%")))
    li = rec["line_items"][0]
    assert (li["supply_base_rate"], li["supply_escalation_pct"], li["supply_rate"],
            li["supply_gst_rate"]) == (1760.0, 15.0, 2024.0, 18.0)


def test_negative_figures_keep_their_refusal(client):
    assert "has a negative quantity" in save_model(client, one_section(a_line(total_qty="-1")))
    assert "has a negative rate" in save_model(client, one_section(a_line(supply_rate="-5")))


def test_the_project_name_and_the_date_still_stop_a_save(client):
    assert "needs a project name" in save_model(client, one_section(a_line()), project_name="")
    assert "needs a date" in save_model(client, one_section(a_line()), date="")


def test_the_create_form_has_no_bar_no_block_and_a_quiet_note_slot(client):
    html = markup(client.get("/boq/create").get_data(as_text=True))
    assert 'id="needs-bar"' not in html and 'id="import-block"' not in html
    assert 'id="blank-note"' in html
    assert 'id="account_name" name="account_name"' in html
    acct = re.search(r'<input type="text" id="account_name"[^>]*>', html).group(0)
    assert "required" not in acct, "a blank account name saves (A3)"


def test_a_refused_save_rings_only_wrong_boxes_never_blank_ones(client):
    body = save_model(client, one_section(a_line(item_no="", description="", total_qty="",
                                                 supply_rate="x")))
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", body, re.S)
    li = json.loads(m.group(1))["lines"][0]
    assert li["_err"] == ["supply_rate"], "the blank item, description and qty are not marked"
    assert boq.line_problems(a_line(item_no="", description="", total_qty=""),
                             {"A": {"areas": []}}) == []


# ═══ A5. View and print ════════════════════════════════════════════════════════

def _blank_zero_boq(client):
    return save_model(client, one_section(
        a_line(item_no="1", description="Blank qty", total_qty="", supply_rate="100"),
        a_line(item_no="2", description="Blank rate", total_qty="5", supply_rate=""),
        a_line(item_no="3", description="Zero both", total_qty="0", supply_rate="0",
               install_rate="0"),
        a_line(item_no="4", description="Priced", total_qty="2", supply_rate="250",
               install_rate="")))


def test_the_print_shows_blank_as_blank_and_zero_as_zero(client):
    rec = _blank_zero_boq(client)
    html = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
    t = table_of(html)
    # Sr | Description | Qty | Unit | S rate | S amt | I rate | I amt
    assert cells(t, "Blank qty") == ["1", "Blank qty", "", "Mtr", "100.00", "", "", ""]
    assert cells(t, "Blank rate") == ["2", "Blank rate", "5", "Mtr", "", "", "", ""]
    assert cells(t, "Zero both") == ["3", "Zero both", "0", "Mtr", "0.00", "0.00", "0.00", "0.00"]
    assert cells(t, "Priced") == ["4", "Priced", "2", "Mtr", "250.00", "500.00", "", ""]
    for bad in (">None<", ">nan<", ">-<"):
        assert bad not in t
    assert "excludes" not in html and "no quantity" not in html, "no note on print"


def test_the_view_says_what_the_totals_skipped_and_counts_the_blanks(client):
    rec = _blank_zero_boq(client)
    html = client.get(f"/boq/view/{rec['id']}").get_data(as_text=True)
    assert "1 line has no rate, 1 line has no quantity." in html
    assert "Subtotal (A) excludes 2 lines with no amount" in html
    assert "Total excludes 2 lines with no amount" in html
    assert 'id="unpriced-note"' not in html, "the amber note is replaced"
    assert "@media print { .unpriced-note, .quiet-note, .skip-note" in html
    register = client.get("/boq/").get_data(as_text=True)
    assert "excludes 2 lines with no amount" in register, "the register's total says it too"


def test_a_record_saved_before_the_rule_prints_exactly_as_it_did(client):
    """No marker: a 0 rate prints blank and a None base prints "-" — the closed
    historical set, read as it always was and never migrated."""
    rec = save_model(client, one_section(a_line(supply_rate="0", total_qty="3")))
    rec.pop(boq.BLANK_MODEL_KEY)
    t = table_of(client.get(f"/boq/print/{rec['id']}").get_data(as_text=True))
    assert cells(t, "Pipe")[4] == "", "a legacy 0 rate prints blank, as before"
    view = client.get(f"/boq/view/{rec['id']}").get_data(as_text=True)
    assert '<td class="b-base">-</td>' in view


# ═══ Revisions ════════════════════════════════════════════════════════════════

def test_a_revision_carries_blanks_and_a_filled_rate_makes_the_line_claimable(client):
    rec = save_model(client, one_section(a_line(supply_rate=""), a_line(item_no="2")))
    page = client.get(f"/boq/create?revise={rec['id']}").get_data(as_text=True)
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\nvar SPECS", page, re.S).group(1))
    assert model["lines"][0]["supply_rate"] == "", "a blank comes back blank, not 0"
    rev = save_model(client, model, rev_no="1", supersedes=rec["id"])
    assert isinstance(rev, dict) and rev["line_items"][0]["supply_rate"] is None
    assert ra.no_rate_lines(rec["id"], "supply") == {rev["line_items"][0]["line_id"]}
    model["lines"][0]["supply_rate"] = "120"
    for l, saved in zip(model["lines"], rev["line_items"]):
        l["line_id"] = saved["line_id"]
    rev2 = save_model(client, model, rev_no="2", supersedes=rev["id"])
    assert isinstance(rev2, dict), rev2[:1500]
    assert ra.no_rate_lines(rec["id"], "supply") == set()


# ═══ A6. RA ═══════════════════════════════════════════════════════════════════

def _ra_boq(client):
    rec = save_model(client, one_section(
        a_line(item_no="1", description="No rate", supply_rate="", total_qty="5"),
        a_line(item_no="2", description="Priced", supply_rate="100", total_qty="5"),
        a_line(item_no="3", description="No qty", supply_rate="100", total_qty="")))
    conftest.chain_ready(rec["id"])
    return rec


def test_the_claim_grid_greys_a_line_with_no_rate(client):
    rec = _ra_boq(client)
    nr, priced, _ = (l["line_id"] for l in rec["line_items"])
    html = client.get(f"/ra/create?boq={rec['id']}&leg=supply").get_data(as_text=True)
    row = re.search(rf'<tr class="([^"]*)" id="row_{nr}".*?</tr>', html, re.S)
    assert row and "cl-done" in row.group(1)
    assert ra.NO_RATE_MESSAGE in row.group(0)
    assert f'id="q_{nr}"' not in html, "no input: nothing about it is posted"
    assert f'id="q_{priced}"' in html


def test_a_post_naming_a_no_rate_line_is_refused_naming_it(client):
    rec = _ra_boq(client)
    nr = rec["line_items"][0]["line_id"]
    before = set(STORE["ra_bills"])
    r = client.post(f"/ra/create?boq={rec['id']}&leg=supply",
                    data={"date": "2026-10-06",
                          "ra_json": json.dumps({"lines": [{"line_id": nr, "qty": "1",
                                                            "rate": "10"}]})})
    assert set(STORE["ra_bills"]) == before
    body = r.get_data(as_text=True)
    assert "Item 1 (supply): No rate on the BOQ. Add it in a revision." in body


def test_a_blank_quantity_takes_the_rate_only_lines_rule(client):
    """`overclaims()` on a rate-only line (quantity 0) and on a blank-quantity
    line gives the SAME refusal: 0 approved, over by the whole claim."""
    blank = _ra_boq(client)
    ro = save_model(client, one_section(a_line(item_no="3", description="No qty",
                                               supply_rate="100", total_qty="0")))
    b_lid, r_lid = blank["line_items"][2]["line_id"], ro["line_items"][0]["line_id"]
    assert ra.approved_by_line(blank["id"])[(b_lid, "supply")] == 0.0
    assert ra.approved_by_line(ro["id"])[(r_lid, "supply")] == 0.0
    vb = ra.overclaims(blank["id"], "supply", [{"line_id": b_lid, "qty": 2.0}])
    vr = ra.overclaims(ro["id"], "supply", [{"line_id": r_lid, "qty": 2.0}])
    strip = lambda v: {k: x for k, x in v.items() if k != "line_id"}  # noqa: E731
    assert [strip(v) for v in vb] == [strip(v) for v in vr]
    assert vb[0]["reason"] == "overclaim" and vb[0]["approved"] == 0.0
    assert ra.overclaim_message(vb[0]) == ra.overclaim_message(vr[0])


def test_a_challan_prefill_skips_a_no_rate_line_and_lists_it(client):
    rec = _ra_boq(client)
    nr, priced, _ = (l["line_id"] for l in rec["line_items"])
    STORE["delivery_challans"]["dc-asis"] = {
        "id": "dc-asis", "ref": "DC-77", "date": "2026-10-06", "boq_id": rec["id"],
        "boq_ref": rec["ref"],
        "items": [{"line_id": nr, "item_no": "1", "description": "No rate", "unit": "Mtr",
                   "is_header": False, "qty": 3.0},
                  {"line_id": priced, "item_no": "2", "description": "Priced", "unit": "Mtr",
                   "is_header": False, "qty": 4.0}]}
    html = client.get(f"/ra/create?boq={rec['id']}&leg=supply&dc=dc-asis").get_data(as_text=True)
    assert "Not prefilled &mdash; no rate on the BOQ</b>: 1 (3)" in html
    assert re.search(rf'id="q_{priced}"\s+value="4"', html)


# ═══ A6. The other documents and the project page ════════════════════════════

def test_the_line_picker_prefills_a_blank_quantity_blank(client):
    rec = save_model(client, one_section(a_line(total_qty=""), a_line(item_no="2", total_qty="0")))
    html = boqpick.rows_html(rec, None, None, False, "Quantity")
    a, b = (l["line_id"] for l in rec["line_items"])
    assert re.search(rf'id="q_{a}"\s+value=""', html), "blank, never 0"
    assert re.search(rf'id="q_{b}"\s+value="0"', html), "a 0 is 0"
    for url in (f"/dc/create?boq={rec['id']}", f"/po/create?boq={rec['id']}",
                f"/purchase/from-boq/{rec['id']}", f"/measurement/create?boq={rec['id']}"):
        page = client.get(url)
        assert page.status_code == 200, (url, page.status_code, page.headers.get("Location"))
        assert re.search(rf'id="q_{a}"\s+value=""', page.get_data(as_text=True)), url


def test_the_project_page_says_how_many_lines_are_not_priced(client):
    rec = save_model(client, one_section(a_line(supply_rate=""), a_line(item_no="2")))
    STORE["projects"]["p-asis"] = {"id": "p-asis", "name": "As is", "status": "active"}
    rec["project_id"] = "p-asis"
    html = client.get("/projects/view/p-asis").get_data(as_text=True)
    assert "1 line not priced" in html


# ═══ A8. Half up — Python and the editor ═════════════════════════════════════

@pytest.mark.parametrize("unit,disc,net", [
    (2.5, 15, 2.13),          # 2.125 exactly: half UP (was 2.12, half to even)
    (0.75, 50, 0.38),
    (10.05, 50, 5.03),        # 5.025 is 5.0249999… in binary: Excel says 5.03
    (1.15, 50, 0.58),         # 0.575 is 0.57499999…: Excel says 0.58
    (5.35, 50, 2.68),         # 2.675 is 2.67499999…: Excel says 2.68
    (2024.0, 10, 1821.6),
    (100.0, None, 100.0),
    (100.0, 0, 100.0),
])
def test_the_net_rate_rounds_half_up(unit, disc, net):
    assert boq.net_of(unit, disc) == net


def test_no_unit_rate_is_no_net_rate():
    assert boq.net_of(None, 10) is None and boq.net_rate({"supply_rate": None}, "supply") is None
    assert boq.amount_of(None, 5.0) is None and boq.amount_of(3.0, None) is None
    assert boq.amount_of(0.0, 5.0) == 0.0 and boq.amount_of(3.0, 0.0) == 0.0


def _js(boot=None):
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    return (js.replace("BOQ_BOOT", json.dumps(boot or {"sections": [], "lines": []}))
              .replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}"))


_STUB = ("var STUB = {}; ['bulk-spec','bulk-section','line-editor','sec-editor','boq_json',"
         "'blank-note','jump-bar','dup-warn','zeroqty-hint']"
         ".forEach(function(k){ STUB[k] = {value:'', innerHTML:''}; });\n"
         "var document = { getElementById: function(id) { return STUB[id] || null; } };\n")


def _node(script, boot=None):
    out = subprocess.run([NODE], input=_STUB + _js(boot) + "\n" + script,
                         capture_output=True, text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_node
def test_the_editor_rounds_the_net_rate_exactly_as_the_server_does():
    cases = [(2.5, "15"), (0.75, "50"), (10.05, "50"), (1.15, "50"), (5.35, "50"),
             (0.25, "50"), (5.25, "50"), (2024, "10"), (100.25, "10"), (1999.99, "12.5"),
             (7, "33.333"), (123.45, "7.5"), (0.1, "30"), (99.99, "50"), (4.5, "1")]
    lines = [{"supply_rate": str(u), "supply_disc_pct": d} for u, d in cases]
    lines += [{"supply_rate": "", "supply_disc_pct": "10"}, {"supply_rate": "0"}]
    got = _node("var L = " + json.dumps(lines) + ";\n"
                "console.log(JSON.stringify(L.map(function (l) { return netRate(l, 'supply'); })));")
    assert got == [boq.net_rate(l, "supply") for l in lines]


@needs_node
def test_the_editor_sums_present_amounts_and_counts_the_skipped():
    boot = one_section(a_line(total_qty="", supply_rate="100"),
                       a_line(item_no="2", total_qty="3", supply_rate=""),
                       a_line(item_no="3", total_qty="2", supply_rate="50"))
    got = _node("MODEL.sections[0]._open = true; renderLines();"
                "console.log(JSON.stringify({t: sectionTotals('A'),"
                " note: STUB['blank-note'].innerHTML}));", boot)
    assert got["t"] == [100, 0, 2]
    assert "1 line has no rate, 1 line has no quantity." in got["note"]


@needs_node
def test_the_editor_saves_an_imported_boq_full_of_blanks():
    boot = one_section(a_line(total_qty="", supply_rate="", _row=5, _flags=["Row 5: x"]),
                       a_line(item_no="", description="", total_qty="", _row=6))
    got = _node("MODEL.sections[0]._open = true; renderLines();"
                "var ok = saveJSON();"
                "console.log(JSON.stringify({ok: ok, posted: STUB['boq_json'].value.length > 0,"
                " html: STUB['line-editor'].innerHTML}));", boot)
    assert got["ok"] is True and got["posted"], "a blank never stops the save"
    assert "is-red" not in got["html"] and "quantity needed" not in got["html"]
    assert "Not priced" not in got["html"]


@needs_node
def test_moving_an_imported_line_never_gives_it_a_quantity():
    boot = {"sections": [{"code": "A", "title": "", "areas": []},
                         {"code": "B", "title": "", "areas": []}],
            "lines": [a_line(total_qty="", _row=4), a_line(item_no="2", total_qty="")]}
    got = _node("setSection(0, 'B'); setSection(1, 'B');"
                "console.log(JSON.stringify([MODEL.lines[0].total_qty, MODEL.lines[1].total_qty]));",
                boot)
    assert got == ["", "1"], "imported: stays blank; typed: the form's default of 1"
