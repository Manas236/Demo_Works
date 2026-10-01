"""
Import BOQ from Excel — what the Iron Mountain sheet broke (1 October 2026,
CLIENT_CHANGES.md §0, thirty-ninth block).

Every sheet here is SYNTHETIC. The client's own workbook is never read by a
test and never copied into the repository. Most sheets are built with
`sheetimport.from_rows()` — the same staging, header and scoring path as
`read()`, minus the reader — so this module runs with openpyxl absent too
(ABOUT.md §1's row 3); the few tests that need a real number format build a
workbook and skip inside the function without openpyxl.

The rules, one block each (ABOUT.md §5 `/boq/import`):

B  a numeric item number is rounded to its fixed format's decimals, else to at
   most 2, and its trailing zeros are stripped; a text item is untouched.
C  "RO", "R.O.", "R/O", "RATE ONLY" in the quantity: a RATE-ONLY line — qty 0,
   rates kept, a grey chip, a remark; not blocking; with no rate it gets the
   ordinary blocking rate need, worded "rate-only line with no rate".
D  two or more unnumbered, unpriced rows under one parent, each immediately
   followed by a child, are GROUP LABELS put in front of their children.
E  once the grand total is recognised by label AND sums, no later row is a line.
F  a number in the Make column is not a make.
G  "Rates on this sheet are: Selling rates / Our cost" — cost puts each rate
   in the BASE rate, the markup in the ESCALATION, and the form works out the
   unit rate; every check runs on the sheet's own figures; the print never
   shows a base rate.
"""

import json
import re
import shutil
import subprocess

import pytest

import boq
import boqimport
import sheetimport as SI
from store import STORE

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

SIMPLE = ["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount",
          "Installation Rate", "Installation Amount"]
COST = ["Sr. No.", "Description", "Qty", "Unit", "Own Cost Supply Rate", "Supply Amount",
        "Own Cost Installation Rate", "Installation Amount"]


# ═══ Helpers ═════════════════════════════════════════════════════════════════

def grid_of(rows, title="BOQ"):
    st = SI.from_rows([(title, "visible", rows)])
    return st, st["grid"][st["selected"]]


def built(rows, override=None):
    _st, g = grid_of(rows)
    m = SI.guess_mapping(g)
    m.update(override or {})
    return SI.build(g, m), g, m


def by_row(res, rnum):
    return next(l for l in res["lines"] if l["row"] == rnum)


def line(res, item):
    return next(l for l in res["lines"] if l["item_no"] == item)


def stage_rows(rows, name="sheet.xlsx"):
    """Stage a synthetic sheet for the suite's signed-in Owner — the path
    `test_entity_fallbacks.py`'s sweep fixture takes. Call AFTER `client`."""
    import conftest
    wb = SI.from_rows([("BOQ", "visible", rows)])
    tok, known = boqimport.stage(wb, name, conftest.ensure_test_user()["id"])
    return tok, known


def post_preview(client, tok, action="update", rate_mode=None, markup=None, override=None):
    rec = STORE["boq_imports"][tok]
    mapping = dict(rec["mapping"])
    mapping.update(override or {})
    form = {f"map_{c}": t for c, t in mapping.items()}
    form.update({"action": action, "sheet": str(rec.get("sheet_index") or 0)})
    if rate_mode is not None:
        form["rate_mode"] = rate_mode
    if markup is not None:
        form["markup"] = markup
    return client.post(f"/boq/import/{tok}", data=form)


def model_of(html: str) -> dict:
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", html, re.S)
    assert m, "the page carries no editor model"
    return json.loads(m.group(1))


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def save(client, model, **over):
    form = {"date": "2026-10-01", "project_name": "Imported project",
            "account_name": "Imported customer", "rev_no": "0",
            "boq_json": json.dumps(model)}
    form.update(over)
    return client.post("/boq/create", data=form)


def node(boot: dict, script: str):
    """Run boq._BOQ_JS against `boot` and `script` in one Node process — the
    harness `tests/test_boq_import.py` uses, fed on STDIN."""
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = (js.replace("BOQ_BOOT", json.dumps(boot))
            .replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}"))
    stub = ("var STUB = {}; ['bulk-spec','bulk-section','line-editor','sec-editor',"
            "'boq_json','import-block','dup-warn','zeroqty-hint','jump-bar']"
            ".forEach(function(k){ STUB[k] = {value:'', innerHTML:''}; });\n"
            "var document = { getElementById: function(id) { return STUB[id] || null; } };\n")
    out = subprocess.run(["node"], input=stub + js + "\n" + script, capture_output=True,
                         text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


# ═══ B. Item numbers ═════════════════════════════════════════════════════════

@pytest.mark.parametrize("value,kind,want", [
    (5.199999999999999, "dp:2", "5.2"),          # the brief's four
    (17.200000000000003, "dp:2", "17.2"),
    (3.01, "dp:2", "3.01"),
    (4.0, "dp:2", "4"),
    (5.199999999999999, "", "5.2"),              # no fixed format: at most 2
    (17.200000000000003, "", "17.2"),
    (4.0999999999999996, "", "4.1"),             # the Sify sheet's own float
    (11.699999999999998, "dp:2", "11.7"),        # the Iron Mountain sheet's
    (1.1, "dp:2", "1.1"),                        # was "1.10"
    (2.125, "dp:3", "2.125"),                    # a fixed format's own decimals
    (7.0, "dp:1", "7"),
    (12, "", "12"),
    (0.0, "", "0"),
])
def test_a_numeric_item_is_rounded_and_its_trailing_zeros_stripped(value, kind, want):
    assert SI._item_text(value, kind) == want


@pytest.mark.parametrize("text", ["2.1.4", "a)", "4.10", "1.20", "A-1", "3.01"])
def test_a_text_item_cell_stays_exactly_as_it_is(text):
    assert SI._item_text(text, "") == text
    assert SI._item_text(f"  {text} ", "") == text


def test_item_numbers_through_a_staged_sheet_and_into_the_form_model():
    res, _g, _m = built([SIMPLE,
                         [17, "Pipe", None, None, None, None, None, None],
                         [17.200000000000003, "250MM", 2, "Rmt.", 100, 200, None, None],
                         [5.199999999999999, "150 MM Dia", 1, "Rmt.", 10, 10, None, None],
                         [4.0, "Valve", 1, "Nos", 5, 5, None, None]])
    assert [l["item_no"] for l in res["lines"]] == ["17", "17.2", "5.2", "4"]
    model = boqimport.editor_model(res)
    assert [l["item_no"] for l in model["lines"]] == ["17", "17.2", "5.2", "4"]


def test_a_number_in_a_description_keeps_v1s_reading():
    """B is about ITEM numbers. A figure in the description or unit column is
    shown as before — ten significant digits, not rounded to two."""
    res, _g, _m = built([SIMPLE, ["1", 1.125, 2, "Nos", 10, 20, None, None]])
    assert line(res, "1")["description"] == "1.125"


def test_a_fixed_number_format_through_a_real_workbook():
    """The Iron Mountain shape: every item cell `0.00`-formatted."""
    openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")
    import io
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in [SIMPLE, [5, "Exhaust pipe", None, None, None, None, None, None],
              [5.199999999999999, "150 MM Dia", 2, "Rmt.", 10, 20, None, None],
              [17.200000000000003, "250MM", 1, "Rmt.", 10, 10, None, None],
              [3.01, "15 Mtr.", 1, "Nos", 10, 10, None, None],
              [4.0, "Valve", 1, "Nos", 10, 10, None, None]]:
        ws.append(r)
    for ref in ("A2", "A3", "A4", "A5", "A6"):
        ws[ref].number_format = "0.00"
    buf = io.BytesIO()
    wb.save(buf)
    st = SI.read(buf.getvalue(), "t.xlsx")
    g = st["grid"][st["selected"]]
    res = SI.build(g, SI.guess_mapping(g))
    assert [l["item_no"] for l in res["lines"]] == ["5", "5.2", "17.2", "3.01", "4"]


# ═══ C. Rate-only lines ══════════════════════════════════════════════════════

@pytest.mark.parametrize("raw", ["RO", "R.O.", "R/O", "RATE ONLY", "ro", "r.o.",
                                 " Rate Only ", "rate  only", "R / O", "R.O"])
def test_ro_in_the_quantity_is_a_rate_only_line_at_zero(raw):
    res, _g, _m = built([SIMPLE, ["1", "Gate valve", raw, "Nos", 500, None, 120, None]])
    ln = line(res, "1")
    assert ln["qty"] == 0.0 and ln["rate_only"] is True
    assert (ln["supply_rate"], ln["install_rate"]) == (500.0, 120.0), "the rates are kept"
    assert ln["block"] is False and not ln["needs"] and not res["needs"]
    assert not ln["flags"] and not res["flags"], "rate only is not a flag on its own"
    assert res["counts"]["rate_only"] == 1 and res["counts"]["rate_only_no_rate"] == 0
    row = boqimport.editor_model(res)["lines"][0]
    assert row["total_qty"] == "0" and row["_ro"] is True and "_block" not in row
    assert row["remark"] == "Rate only (RO) on the source sheet"
    assert (row["supply_rate"], row["install_rate"]) == ("500", "120")


@pytest.mark.parametrize("raw", ["I.R.", "R. O.", "NA"])
def test_other_words_in_the_quantity_keep_v1s_rule(raw):
    res, _g, _m = built([SIMPLE, ["1", "Gate valve", raw, "Nos", 500, None, None, None]])
    ln = line(res, "1")
    assert ln["qty"] is None and ln["block"] is True and ln["rate_only"] is False


def test_a_rate_only_lines_make_follows_its_remark():
    res, _g, _m = built([SIMPLE + ["Make"],
                         ["1", "Gate valve", "RO", "Nos", 500, None, None, None, "Sant"]])
    row = boqimport.editor_model(res)["lines"][0]
    assert row["remark"] == "Rate only (RO) on the source sheet; Make: Sant"


@pytest.mark.parametrize("rates", [(None, None), (0, None), (0, 0)])
def test_a_rate_only_line_with_no_rate_gets_the_blocking_rate_need(rates):
    """A zero is no rate here: a rate-only line's 0 is no quantity anybody
    measured, so it does not make a 0 rate count."""
    s, i = rates
    res, _g, _m = built([SIMPLE, ["1", "DN 300", "RO", "Nos", s, None, i, None]])
    ln = line(res, "1")
    assert [n["field"] for n in ln["needs"]] == ["rate"]
    (f,) = [f for f in res["flags"] if f["row"] == 2]
    assert (f["kind"], f["severity"], f["message"]) == (
        "ro_no_rate", "red", "rate-only line with no rate")
    assert res["counts"]["rate_only_no_rate"] == 1
    assert ln["block"] is False, "the quantity is 0, not blank"


def test_a_rate_only_line_with_no_rate_is_asked_whatever_its_amount_cells_hold():
    """An explicit 0 amount prices a QUANTITY at nil (the Sify rule). A rate-only
    line has none, so the 0 says nothing and the rate is still asked for."""
    res, _g, _m = built([SIMPLE, ["1", "DN 300", "RO", "Nos", None, 0, None, 0]])
    assert [n["field"] for n in line(res, "1")["needs"]] == ["rate"]


def test_not_priced_answers_a_rate_only_lines_need():
    res, _g, _m = built([SIMPLE, ["1", "DN 300", "RO", "Nos", None, None, None, None]])
    model = boqimport.editor_model(res)
    assert boq.annotate_needs(model["lines"], model["sections"], with_errors=False) == 1
    model["lines"][0]["supply_rate"] = "0"          # what "Not priced (₹0)" types
    assert boq.annotate_needs(model["lines"], model["sections"], with_errors=False) == 0


def test_the_preview_summary_counts_rate_only_lines(client):
    tok, _k = stage_rows([SIMPLE, ["1", "DN 300", "RO", "Nos", None, None, None, None],
                          ["2", "DN 250", "R.O.", "Nos", 4000, None, 300, None],
                          ["3", "DN 200", 2, "Nos", 3000, 6000, 200, 400]])
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "<b>2</b> rate-only lines" in body
    assert "1 of them has no rate on either track" in text_of(body)


def test_a_sheet_without_ro_draws_no_rate_only_group(client):
    tok, _k = stage_rows([SIMPLE, ["1", "DN 200", 2, "Nos", 3000, 6000, 200, 400]])
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "rate-only line" not in body and 'id="imp-ro"' not in body


def test_a_rate_only_line_saves_at_zero_with_its_rates_and_remark(client):
    tok, _k = stage_rows([SIMPLE, ["1", "Gate valve", "RO", "Nos", 500, None, 120, None]])
    r = post_preview(client, tok, action="confirm")
    assert r.status_code == 303
    model = model_of(client.get(r.headers["Location"]).get_data(as_text=True))
    before = set(STORE["boqs"])
    assert save(client, model).status_code == 302
    (bid,) = set(STORE["boqs"]) - before
    (li,) = STORE["boqs"][bid]["line_items"]
    assert (li["total_qty"], li["supply_rate"], li["install_rate"]) == (0.0, 500.0, 120.0)
    assert li["remark"] == "Rate only (RO) on the source sheet"
    assert not any(k.startswith("_") for k in li), "UI state reached the record"


@needs_node
def test_a_rate_only_line_carries_a_grey_chip_and_is_not_blocked():
    res, _g, _m = built([SIMPLE, ["1", "Gate valve", "RO", "Nos", 500, None, None, None]])
    got = node(boqimport.editor_model(res), """
      MODEL.sections[0]._open = true; renderLines();
      console.log(JSON.stringify({html: STUB['line-editor'].innerHTML, ok: saveJSON()}));
    """)
    assert 'class="chip-ro"' in got["html"] and ">rate only</span>" in got["html"]
    assert "quantity needed" not in got["html"]
    assert got["ok"] is True


# ═══ D. Group labels inside an item ══════════════════════════════════════════

SLUICE = [
    SIMPLE,
    ["11", "Sluice valves: pressure rated, flanged", None, None, None, None, None, None],
    [None, "PN-25", None, None, None, None, None, None],
    ["11.1", "DN 250", 8, "Nos", 74096, 592768, 3900, 31200],
    ["11.2", "DN 200", 4, "Nos", 45678, 182712, 3200, 12800],
    [None, "PN-16", None, None, None, None, None, None],
    ["11.6", "DN 250", 4, "Nos", 67360, 269440, 3900, 15600],
    ["11.7", "DN 200", 4, "Nos", 41526, 166104, 3200, 12800],
    ["12", "Diaphragm valve", None, None, None, None, None, None],
    ["12.1", "DN 150", 2, "Set", 419432, 838864, 105000, 210000],
]


def test_two_labels_each_followed_by_children_are_group_labels():
    res, _g, _m = built(SLUICE)
    assert [by_row(res, r)["kind"] for r in (3, 6)] == ["group_label", "group_label"]
    assert [line(res, i)["description"] for i in ("11.1", "11.2", "11.6", "11.7")] == [
        "PN-25 · DN 250", "PN-25 · DN 200", "PN-16 · DN 250", "PN-16 · DN 200"]
    assert res["counts"]["group_labels"] == 2


def test_a_label_stops_at_the_next_numbered_item():
    res, _g, _m = built(SLUICE)
    assert line(res, "12.1")["description"] == "DN 150"
    assert line(res, "12")["description"] == "Diaphragm valve"


def test_labels_are_not_appended_to_the_parents_text():
    res, _g, _m = built(SLUICE)
    model = boqimport.editor_model(res)
    head = next(l for l in model["lines"] if l["item_no"] == "11")
    assert head["description"] == "Sluice valves: pressure rated, flanged"
    assert "PN-25" not in head["description"] and "PN-16" not in head["description"]
    assert [l["item_no"] for l in model["lines"]] == [
        "11", "11.1", "11.2", "11.6", "11.7", "12", "12.1"]


def test_labels_over_auto_numbered_sizes():
    """Unnumbered priced rows become 11.a … — a child all the same."""
    res, _g, _m = built([SIMPLE,
                         ["11", "Sluice valves", None, None, None, None, None, None],
                         [None, "PN-25", None, None, None, None, None, None],
                         [None, "DN 250", 2, "Nos", 100, 200, None, None],
                         [None, "PN-16", None, None, None, None, None, None],
                         [None, "DN 250", 3, "Nos", 90, 270, None, None]])
    assert [(l["item_no"], l["description"]) for l in res["lines"] if not l["is_header"]] == [
        ("11.a", "PN-25 · DN 250"), ("11.b", "PN-16 · DN 250")]


def test_the_deluge_valves_spec_lines_stay_spec_text():
    """The Iron Mountain sheet's D 7: "i) Mains deluge valve" is followed by
    another spec line, not a child — only "ii)" is — so neither is a label."""
    res, _g, _m = built([SIMPLE,
                         ["7", "Deluge valve assembly", None, None, None, None, None, None],
                         [None, "i) Mains deluge valve", None, None, None, None, None, None],
                         [None, "ii) Pressure gauges with gate valve", None, None, None, None,
                          None, None],
                         ["7.1", "DN 100", 2, "Nos", 62000, 124000, 15000, 30000]])
    assert [by_row(res, r)["kind"] for r in (3, 4)] == ["spec_text", "spec_text"]
    assert line(res, "7.1")["description"] == "DN 100"
    head = next(l for l in boqimport.editor_model(res)["lines"] if l["item_no"] == "7")
    assert head["description"] == ("Deluge valve assembly\ni) Mains deluge valve\n"
                                   "ii) Pressure gauges with gate valve")
    assert res["counts"]["group_labels"] == 0


def test_a_monitors_spec_bullets_stay_spec_text():
    bullets = ["Monitor Size: 4\". As Per IS:8442 Type", "360 Degree Horizontal Rotation",
               "Flow Rate: 1750 LPM (500 GPM)", "Pressure: 7KG/cm2"]
    res, _g, _m = built([SIMPLE, ["1", "Oscillating water cum foam monitor", None, None, None,
                                  None, None, None]]
                        + [[None, b, None, None, None, None, None, None] for b in bullets]
                        + [["1.1", "Water Cum Foam Monitor", 3, "Nos", 315000, 945000,
                            6500, 19500]])
    assert all(by_row(res, r)["kind"] == "spec_text" for r in (3, 4, 5, 6))
    assert line(res, "1.1")["description"] == "Water Cum Foam Monitor"


def test_a_single_label_stays_spec_text():
    """The Jamnagar shape: one spec line, then the sizes."""
    res, _g, _m = built([SIMPLE,
                         ["1", "COAL TAR TAPE", None, None, None, None, None, None],
                         [None, "Supply, Installation & Commissioning of coal tar tape",
                          None, None, None, None, None, None],
                         [None, "150 mm NB", 350, None, 3050, 1067500, 1380, 483000],
                         [None, "100 mm NB", 50, None, 2210, 110500, 920, 46000]])
    assert by_row(res, 3)["kind"] == "spec_text"
    assert [l["description"] for l in res["lines"] if l["kind"] == "sub_item"] == [
        "150 mm NB", "100 mm NB"]


def test_a_labels_make_goes_to_the_parents_remark():
    res, _g, _m = built([SIMPLE + ["Make"],
                         ["11", "Sluice valves", None, None, None, None, None, None, None],
                         [None, "PN-25", None, None, None, None, None, None, "Kirloskar"],
                         ["11.1", "DN 250", 1, "Nos", 10, 10, None, None, None],
                         [None, "PN-16", None, None, None, None, None, None, None],
                         ["11.2", "DN 250", 1, "Nos", 10, 10, None, None, None]])
    head = next(l for l in boqimport.editor_model(res)["lines"] if l["item_no"] == "11")
    assert head["remark"] == "Make: Kirloskar"


# ═══ E. Below the grand total ════════════════════════════════════════════════

ABOVE = [SIMPLE,
         ["A", "FIRE PUMP ROOM", None, None, None, None, None, None],
         ["1", "Pump", 2, "Nos", 1000, 2000, 100, 200],
         ["2", "Valve", 3, "Nos", 500, 1500, 50, 150],
         [None, "TOTAL OF FIRE PUMP ROOM", None, None, None, 3500, None, 350],
         [None, "GRAND TOTAL", None, None, None, 3500, None, 350]]
TRAILER = [[None, None, None, "Fittings, Transportation,loading,unloading", 0.2, 700, None,
            None],
           [None, None, None, None, None, 4200, "Total =", None],
           ["DELIVERABLES FROM VENDOR/MANUFACTURER", None, None, None, "SPECIAL NOTES IF ANY",
            None, None, None],
           ["1. TRANSPORTATION / FREIGHT :", None, None, None, None, None, None, None]]


def test_nothing_below_a_recognised_grand_total_becomes_a_line():
    res, _g, _m = built(ABOVE + TRAILER)
    assert [l["row"] for l in res["lines"]] == [3, 4]
    assert res["counts"]["lump_sums"] == 0, "the add-on and the running total are no lump sum"
    notes = [f for f in res["flags"] if f["kind"] == "below_grand"]
    assert [f["row"] for f in notes] == [7, 8, 9, 10]
    assert all("row 6 is the grand total" in f["message"] for f in notes)
    assert "Fittings, Transportation,loading,unloading" in notes[0]["message"]
    assert notes[0]["field"] == "Below the grand total" and notes[0]["severity"] == "amber"
    assert not res["needs"], "a note, never a need"
    assert res["counts"]["below_grand"] == 4


def test_the_rows_above_are_read_exactly_as_before():
    with_trailer, _g, _m = built(ABOVE + TRAILER)
    without, _g2, _m2 = built(ABOVE)
    assert with_trailer["lines"] == without["lines"]
    assert with_trailer["checks"] == without["checks"]
    assert with_trailer["totals"] == without["totals"]


def test_the_notes_are_listed_under_other_notes_on_the_preview(client):
    tok, _k = stage_rows(ABOVE + TRAILER)
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "other notes from the reader" in body
    for r in (7, 8, 9, 10):
        assert f"Row {r} &middot; Below the grand total: not imported" in body
    assert "4</b> rows below the grand total left out" in body


def test_a_grand_total_that_does_not_add_up_ends_nothing():
    """Label without the sums: not recognised, so the rows after it are read."""
    rows = [SIMPLE, ["1", "Pump", 2, "Nos", 1000, 2000, None, None],
            [None, "GRAND TOTAL", None, None, None, 9999, None, None],
            ["2", "Valve", 3, "Nos", 500, 1500, None, None]]
    res, _g, _m = built(rows)
    assert [l["item_no"] for l in res["lines"]] == ["1", "2"]
    assert not [f for f in res["flags"] if f["kind"] == "below_grand"]


def test_a_total_row_below_the_grand_total_is_still_a_check():
    """The Jamnagar sheet's rows 124 and 125: the combined total under the
    grand total is a footing check, which is not a line, and stays one."""
    rows = [SIMPLE, ["A", "PUMPS", None, None, None, None, None, None],
            ["1", "Pump", 1, "Set", 7000, 7000, 2500, 2500],
            [None, "TOTAL AMOUNT (A) Rs.", None, None, None, 7000, None, 2500],
            [None, "TOTAL AMOUNT   A+B+C", None, None, None, 7000, None, 2500],
            [None, "Total", None, None, None, None, None, 9500]]
    res, _g, _m = built(rows)
    assert [(c["row"], c["kind"], c["status"]) for c in res["checks"]] == [
        (4, "subtotal", "match"), (5, "grand total", "match"), (6, "combined total", "match")]
    assert not [f for f in res["flags"] if f["kind"] == "below_grand"]


# ═══ F. Make ═════════════════════════════════════════════════════════════════

def test_a_number_in_the_make_column_is_dropped_and_noted():
    res, _g, _m = built([SIMPLE + ["Make"],
                         ["1", "DN 250", 4, "Nos", 67360, 269440, 3900, 15600, 80832],
                         ["2", "DN 200", 4, "Nos", 41526, 166104, 3200, 12800, "49831.2"],
                         ["3", "DN 150", 2, "Nos", 100, 200, None, None, "Sant"]])
    assert [line(res, i)["make"] for i in ("1", "2", "3")] == ["", "", "Sant"]
    notes = [f for f in res["flags"] if f["kind"] == "make_number"]
    assert [(f["row"], f["raw"], f["field"], f["col"]) for f in notes] == [
        (2, "80832", "Make", "I"), (3, "49831.2", "Make", "I")]
    assert not res["needs"] and not line(res, "1")["flags"], "listed, never on the row"
    rows = boqimport.editor_model(res)["lines"]
    assert [r["remark"] for r in rows] == ["", "", "Make: Sant"]


def test_a_number_as_make_on_spec_text_is_dropped_too():
    res, _g, _m = built([SIMPLE + ["Make"],
                         ["1", "Clause", None, None, None, None, None, None, None],
                         [None, "More of the clause", None, None, None, None, None, None, 1200],
                         [None, "50 mm", 2, "Nos", 10, 20, None, None, None]])
    assert by_row(res, 3)["make"] == ""
    assert [f["row"] for f in res["flags"] if f["kind"] == "make_number"] == [3]


# ═══ G. Cost sheets ══════════════════════════════════════════════════════════

COST_ROWS = [COST,
             ["1", "Gate valve DN 150", 3, "Nos", 4321, 12963, 1200, 3600],
             ["2", "Sprinkler", 10, "Nos", 220, 2200, None, None],
             ["3", "Seismic supports", 1, "Lot", None, None, None, None],
             [None, "GRAND TOTAL", None, None, None, 15163, None, 3600]]


@pytest.mark.parametrize("heading,word", [
    ("OWN COST (INR)", "own cost"), ("Cost Rate", "cost"), ("Purchase Rate", "purchase"),
    ("Buy Rate", "buy"), ("Buying Price", "buying"),
])
def test_cost_words_are_read_from_the_heading(heading, word):
    _st, g = grid_of([["Sr. No.", "Description", "Qty", heading],
                      ["1", "x", 1, 10]])
    assert SI.cost_words(g) == [(word, heading)]


def test_a_selling_heading_has_no_cost_words():
    _st, g = grid_of([SIMPLE, ["1", "x", 1, "Nos", 10, 10, None, None]])
    assert SI.cost_words(g) == []


def test_cost_words_come_from_the_heading_rows_only():
    _st, g = grid_of([["Purchase order no. 17 — cost centre 4"],
                      SIMPLE, ["1", "cost of pipes", 1, "Nos", 10, 10, None, None]])
    assert SI.cost_words(g) == []


@pytest.mark.parametrize("raw,want", [("15", 15.0), ("12.5", 12.5), (" 0 ", 0.0),
                                      ("15%", 15.0), ("1,000", 1000.0)])
def test_a_markup_is_a_number_zero_or_more(raw, want):
    assert boqimport.parse_markup(raw) == want


@pytest.mark.parametrize("raw", ["", "  ", "-5", "abc", "nan", "inf", None, "15 %%"])
def test_anything_else_is_no_markup(raw):
    assert boqimport.parse_markup(raw) is None


def test_the_preview_preselects_our_cost_and_says_why(client):
    tok, known = stage_rows(COST_ROWS)
    assert known is False
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert re.search(r'value="cost" id="rm-cost"\s+checked', body)
    assert "Pre-selected: the heading says “own cost” (in “Own Cost Supply Rate”)" in body
    assert 'id="imp-markup" class="form-group">' in body, "the markup box is shown"
    assert re.search(r'name="markup" min="0" step="any"\s+value="" required', body)
    assert "Checked against the sheet&rsquo;s cost figures" in body


def test_a_selling_sheet_defaults_to_selling_with_no_reason(client):
    tok, _k = stage_rows([SIMPLE, ["1", "x", 1, "Nos", 10, 10, None, None]])
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert re.search(r'value="selling" id="rm-selling"\s+checked', body)
    assert "Pre-selected" not in body
    assert 'id="imp-markup" class="form-group" style="display:none;"' in body
    assert 'id="imp-costcheck" class="imp-note" style="display:none;"' in body


def test_the_choice_can_be_changed_either_way(client):
    cost_tok, _k = stage_rows(COST_ROWS)
    assert post_preview(client, cost_tok, rate_mode="selling").status_code == 303
    body = client.get(f"/boq/import/{cost_tok}").get_data(as_text=True)
    assert re.search(r'value="selling" id="rm-selling"\s+checked', body)
    assert "Pre-selected" not in body
    sell_tok, _k = stage_rows([SIMPLE, ["1", "x", 1, "Nos", 10, 10, None, None]])
    post_preview(client, sell_tok, rate_mode="cost", markup="10")
    body = client.get(f"/boq/import/{sell_tok}").get_data(as_text=True)
    assert re.search(r'value="cost" id="rm-cost"\s+checked', body)
    assert 'value="10" required' in body


@pytest.mark.parametrize("markup", ["", "-5", "abc"])
def test_a_cost_sheet_will_not_confirm_without_a_markup(client, markup):
    tok, _k = stage_rows(COST_ROWS)
    r = post_preview(client, tok, action="confirm", rate_mode="cost", markup=markup)
    assert r.status_code == 200
    assert "Type the markup % for this cost sheet" in r.get_data(as_text=True)
    assert not STORE["boq_imports"][tok]["confirmed"]


def test_a_zero_markup_confirms_and_warns_first(client):
    tok, _k = stage_rows(COST_ROWS)
    post_preview(client, tok, rate_mode="cost", markup="0")
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert '<p id="imp-zero" class="imp-note imp-warn">' in body
    assert "At 0% the sale price will equal cost." in body
    r = post_preview(client, tok, action="confirm", rate_mode="cost", markup="0")
    assert r.status_code == 303


def test_a_cost_sheet_may_not_map_a_base_rate_or_an_escalation(client):
    tok, _k = stage_rows([COST + ["Esc"], ["1", "x", 1, "Nos", 10, 10, None, None, 5]])
    last = str(max(int(c) for c in STORE["boq_imports"][tok]["mapping"]))
    r = post_preview(client, tok, action="confirm", rate_mode="cost", markup="10",
                     override={last: "escalation_pct"})
    assert r.status_code == 200
    assert "no column can be Supply · escalation %" in r.get_data(as_text=True)
    # The same mapping in SELLING mode confirms: the refusal is cost-only.
    r = post_preview(client, tok, action="confirm", rate_mode="selling",
                     override={last: "escalation_pct"})
    assert r.status_code == 303


def cost_model(markup):
    res, _g, _m = built(COST_ROWS)
    return res, boqimport.editor_model(res, markup=markup)


def test_cost_mode_puts_each_rate_in_the_base_and_the_markup_in_the_escalation():
    _res, model = cost_model(15.0)
    one, two, three = model["lines"]
    assert (one["supply_base_rate"], one["supply_escalation_pct"], one["supply_rate"]) == (
        "4321", "15", "")
    assert (one["install_base_rate"], one["install_escalation_pct"], one["install_rate"]) == (
        "1200", "15", "")
    assert one["_cost"] == ["supply", "install"]
    # A track with no rate stays as it was.
    assert (two["install_base_rate"], two["install_escalation_pct"], two["install_rate"]) == (
        "", "", "")
    assert two["_cost"] == ["supply"]
    assert "_cost" not in three
    assert (three["supply_base_rate"], three["supply_escalation_pct"], three["supply_rate"]) == (
        "", "", "")


def test_lines_with_no_rate_keep_their_flags_in_cost_mode():
    res, sell = cost_model(None)
    _res, cost = cost_model(15.0)
    assert [l.get("_need") for l in sell["lines"]] == [l.get("_need") for l in cost["lines"]]
    assert [l.get("_flags") for l in sell["lines"]] == [l.get("_flags") for l in cost["lines"]]
    assert [n["field"] for n in by_row(res, 4)["needs"]] == ["rate"]


def test_selling_mode_is_v1_exactly():
    res, _g, _m = built(COST_ROWS)
    assert boqimport.editor_model(res) == boqimport.editor_model(res, markup=None)
    one = boqimport.editor_model(res)["lines"][0]
    assert (one["supply_base_rate"], one["supply_escalation_pct"], one["supply_rate"]) == (
        "", "", "4321")
    assert "_cost" not in one


def test_every_check_runs_on_the_sheets_own_cost_figures():
    """qty × rate against the amount, and the grand total, are the sheet's own
    arithmetic: the markup is applied after, on the form, and never reaches
    `build()`. A cost sheet that foots, foots whatever the markup."""
    res, _g, _m = built(COST_ROWS)
    assert not [n for n in res["needs"] if n["field"] != "rate"], "no qty × rate mismatch"
    assert res["totals"]["status"] == "match"
    assert [c["sheet"] for c in res["totals"]["checks"]] == [15163.0, 3600.0]
    (chk,) = res["checks"]
    assert (chk["kind"], chk["status"]) == ("grand total", "match")


def test_the_form_says_it_came_from_a_cost_sheet(client):
    tok, _k = stage_rows(COST_ROWS)
    r = post_preview(client, tok, action="confirm", rate_mode="cost", markup="15")
    assert r.status_code == 303
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert ("Imported from a cost sheet: base rate = sheet rate, escalation = 15% on "
            "every line, editable per line.") in text_of(body)
    model = model_of(body)
    assert model["lines"][0]["supply_base_rate"] == "4321"
    assert model["lines"][0]["_cost"] == ["supply", "install"]


def test_a_selling_import_carries_no_cost_banner(client):
    tok, _k = stage_rows([SIMPLE, ["1", "x", 1, "Nos", 10, 10, None, None]])
    r = post_preview(client, tok, action="confirm")
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Imported from a cost sheet" not in body


@needs_node
def test_the_form_works_the_unit_rate_out_with_its_own_computation():
    """`bootCost()` types `suggestRate()` — what "use" beside the box would —
    into each blank unit rate, then drops `_cost`; the hint then has nothing to
    say because the two agree."""
    _res, model = cost_model(15.0)
    got = node(model, """
      var L = MODEL.lines;
      console.log(JSON.stringify({s: L[0].supply_rate, i: L[0].install_rate,
        s2: L[1].supply_rate, i2: L[1].install_rate, s3: L[2].supply_rate,
        left: L.filter(function (x) { return x._cost; }).length,
        same: String(suggestRate('4321', '15'))}));
    """)
    assert (got["s"], got["i"], got["s2"], got["i2"], got["s3"]) == (
        "4969.15", "1380", "253", "", "")
    assert got["left"] == 0 and got["same"] == "4969.15"


@needs_node
def test_the_rounding_the_existing_computation_applies():
    """The worked example ABOUT.md quotes. The FORM rounds to the paisa
    (`suggestRate()`: Math.round(x × 100) / 100); the SERVER, deriving a blank
    unit rate on save (`boq._derived_rate()`), does not round at all."""
    model = {"sections": [{"code": "A", "title": "", "areas": []}],
             "lines": [{"line_id": "", "item_no": "1", "parent_item_no": "", "section": "A",
                        "is_header": False, "description": "x", "remark": "", "unit": "Nos",
                        "area_qty": {}, "total_qty": "3", "supply_base_rate": "100",
                        "supply_escalation_pct": "15", "supply_rate": "",
                        "supply_hsn": "", "supply_gst_rate": "", "install_base_rate": "",
                        "install_escalation_pct": "", "install_rate": "",
                        "install_sac": "", "install_gst_rate": "", "_cost": ["supply"]}]}
    got = node(model, "console.log(JSON.stringify(MODEL.lines[0].supply_rate));")
    assert got == "115"
    assert boq._derived_rate(100.0, 15.0) == 114.99999999999999
    items, err, _i = boq._clean_lines(
        [dict(model["lines"][0], _cost=None)], [{"code": "A", "title": "", "areas": []}])
    assert not err and items[0]["supply_rate"] == 114.99999999999999


def test_the_printed_boq_never_shows_a_cost_imports_base_rate(client):
    tok, _k = stage_rows(COST_ROWS)
    r = post_preview(client, tok, action="confirm", rate_mode="cost", markup="15")
    model = model_of(client.get(r.headers["Location"]).get_data(as_text=True))
    for l in model["lines"]:                   # what bootCost() types on load
        for t in l.pop("_cost", []):
            l[f"{t}_rate"] = str(round(float(l[f"{t}_base_rate"]) * 1.15, 2))
    before = set(STORE["boqs"])
    assert save(client, model).status_code == 302
    (bid,) = set(STORE["boqs"]) - before
    rec = STORE["boqs"][bid]
    one = rec["line_items"][0]
    assert (one["supply_base_rate"], one["supply_escalation_pct"], one["supply_rate"]) == (
        4321.0, 15.0, 4969.15)
    printed = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert "4,969.15" in printed, "the unit rate prints"
    for base in ("4,321", "4321", "1,200.00", "220.00"):
        assert base not in printed, f"a base-rate figure ({base}) reached the print"
    assert "15%" not in printed and "Esc." not in printed and "Rate Basis" not in printed
    # …and the internal copy still shows it, so the figure is really there.
    viewed = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "4,321.00" in viewed and "15%" in viewed


def test_a_cost_layout_never_skips_the_preview(client):
    """The markup is the operator's to type every time: a layout confirmed as
    cost stops at the preview with its mapping applied, never at the form."""
    import conftest
    tok, _k = stage_rows(COST_ROWS)
    post_preview(client, tok, action="confirm", rate_mode="cost", markup="15")
    g = STORE["boq_imports"][tok]["grid"][0]
    lay = STORE["import_layouts"][SI.signature(g)]
    assert lay["rate_mode"] == "cost" and "markup" not in lay
    again, known = boqimport.stage(SI.from_rows([("BOQ", "visible", COST_ROWS)]), "again.xlsx",
                                   conftest.ensure_test_user()["id"])
    assert known is False
    body = client.get(f"/boq/import/{again}").get_data(as_text=True)
    assert "Pre-selected: this layout was last confirmed as our cost" in body


def test_a_selling_layout_still_goes_straight_to_the_form(client):
    import conftest
    rows = [SIMPLE, ["1", "x", 1, "Nos", 10, 10, None, None]]
    tok, _k = stage_rows(rows)
    post_preview(client, tok, action="confirm")
    _again, known = boqimport.stage(SI.from_rows([("BOQ", "visible", rows)]), "again.xlsx",
                                    conftest.ensure_test_user()["id"])
    assert known is True


def test_a_sheet_change_drops_the_old_sheets_choice(client):
    import conftest
    wb = SI.from_rows([("Cost", "visible", COST_ROWS),
                       ("Other", "visible", [SIMPLE, ["1", "x", 1, "Nos", 10, 10, None, None]])])
    tok, _k = boqimport.stage(wb, "two.xlsx", conftest.ensure_test_user()["id"])
    rec = STORE["boq_imports"][tok]
    rec["rate_mode"], rec["markup"] = "cost", "15"
    other = 1 - rec["sheet_index"]
    client.post(f"/boq/import/{tok}", data={"action": "update", "sheet": str(other)})
    assert (rec["rate_mode"], rec["markup"]) == ("", "")


# ═══ Regression — the Jamnagar shape ═════════════════════════════════════════

JAM_HEAD = [["  Samruddhi fire"], ["FIRE FIGHTING SYSTEM VERTIV"],
            ["Sr.No.", "Description of Material & Service", "Make", "Qty", "Supply",
             "Amount", "Installation ", "Amount"],
            [None, None, None, None, "Rate", None, "Rate", None]]
JAM_ROWS = [
    [None, "(A) BOQ FOR HYDRANT SYSTEM"],
    [None, "Hydrant System Line"],
    [1, "COAL TAR TAPE 4MM THICK AS PER  IS 10221", "OEM"],
    [None, "Supply, Installation, Testing & Commissioning of coal tar tape"],
    [None, "150 mm NB", None, 350, 3050, 1067500, 1380, 483000],
    [None, "100 mm NB", None, 50, 2210, 110500, 920, 46000],
    [None, "80 mm NB", None, 50, 2500, 125000, 690, 34500],
    [2, "Supply, Installation, Testing & Commissioning of RCC Hume Pipe"],
    [None, "300 mm NB", None, 350],
    [3, "M.S. PIPE CLASS-C HEAVY DUTY"],
    [None, "Supply, Installation, Testing & Commissioning of MS pipe", "Jindal "],
    [None, "150 mm   (ERW Pipe IS1239 HVY BBE)", None, 1000, 2450, 2450000, 1110, 1110000],
    [None, "100 mm   (ERW Pipe IS1239 HVY BBE)", None, 36, 1600, 57600, 740, 26640],
]


def test_the_jamnagar_shape_still_produces_the_same_flags_and_structure():
    """Rows 5 to 17 of the client's Jamnagar sheet, as
    `tests/test_boq_import_guided.py` holds them: still one blocking flag
    (row 13, a quantity with no rate), the same items, no label, no note."""
    res, _g, _m = built(JAM_HEAD + JAM_ROWS)
    assert [(f["row"], f["kind"]) for f in res["flags"]] == [(13, "no_rate")]
    assert [(n["row"], n["field"]) for n in res["needs"]] == [(13, "rate")]
    assert [l["item_no"] for l in res["lines"] if l["item_no"]] == [
        "1", "1.a", "1.b", "1.c", "2", "2.a", "3", "3.a", "3.b"]
    assert by_row(res, 8)["kind"] == by_row(res, 15)["kind"] == "spec_text"
    assert res["counts"]["group_labels"] == res["counts"]["rate_only"] == 0
    assert res["counts"]["below_grand"] == 0
    model = boqimport.editor_model(res)
    one = next(l for l in model["lines"] if l["item_no"] == "1")
    assert one["description"].endswith("\nSupply, Installation, Testing & Commissioning of coal tar tape")
