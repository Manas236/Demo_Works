"""
Import BOQ from Excel v1 (29 September 2026) — `sheetimport.py` and `boqimport.py`.

Every workbook here is BUILT IN MEMORY with openpyxl; no binary is committed.
The two tests that read the client's real files skip when those files are not
on the box (`fixtures/sify_boq.xlsx`, `client_docs/*.xls` — both gitignored).

The load-bearing rules, each with its own test below:

* a single rate column is left for the user to call Supply or Installation;
* "I.R." / "NA" in a quantity stay BLANK and flagged — never 0 ("RO", "R.O.",
  "R/O" and "Rate only" are a RATE-ONLY line at 0 from 1 October 2026 —
  `tests/test_boq_import_cost.py`);
* text arithmetic, NA, Excel errors, dates and unsaved formulas are flagged and
  never computed;
* nothing is truncated: an oversize schedule is refused whole;
* nothing is saved until Create BOQ — and the save is the ordinary one.
"""

import datetime
import io
import json
import re
import shutil
import subprocess
import time
import zipfile

import pytest

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")

import auth                    # noqa: E402
import boq                     # noqa: E402
import boqimport               # noqa: E402
import sheetimport as SI       # noqa: E402
from store import STORE        # noqa: E402

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent

HEAD = ["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount"]


# ═══ Helpers ═════════════════════════════════════════════════════════════════

def xlsx(rows, title="BOQ", sheets=(), merge=(), formats=None) -> bytes:
    """A workbook in memory. `sheets` adds (title, rows, state) sheets after the
    first; `formats` is {"E3": "0%"} applied to the first sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    for rng in merge:
        ws.merge_cells(rng)
    for ref, fmt in (formats or {}).items():
        ws[ref].number_format = fmt
    for name, srows, state in sheets:
        s = wb.create_sheet(name)
        s.sheet_state = state
        for r in srows:
            s.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def read_first(rows, **kw):
    st = SI.read(xlsx(rows, **kw), "t.xlsx")
    return st, st["grid"][st["selected"]]


def built(rows, override=None, **kw):
    st, g = read_first(rows, **kw)
    m = SI.guess_mapping(g)
    m.update(override or {})
    return SI.build(g, m), g, m


def line(result, item):
    return next(l for l in result["lines"] if l["item_no"] == item)


def col_of(grid, target, mapping):
    return next(int(c) for c, t in mapping.items() if t == target)


def upload(client, data: bytes, name="boq.xlsx"):
    return client.post("/boq/import", data={"workbook": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def token_of(resp) -> str:
    return resp.headers["Location"].split("/boq/import/")[1].split("/")[0]


def mapping_form(mapping: dict, action="confirm", sheet=0) -> dict:
    form = {f"map_{c}": t for c, t in mapping.items()}
    form.update({"action": action, "sheet": str(sheet)})
    return form


def model_of(html: str) -> dict:
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", html, re.S)
    assert m, "the page carries no editor model"
    return json.loads(m.group(1))


def confirm_to_form(client, data: bytes, override=None):
    """Upload, confirm the guessed mapping (with `override`), open the form."""
    r = upload(client, data)
    assert r.status_code == 303, r.get_data(as_text=True)[:400]
    tok = token_of(r)
    rec = STORE["boq_imports"][tok]
    mapping = dict(rec["mapping"])
    mapping.update(override or {})
    r = client.post(f"/boq/import/{tok}", data=mapping_form(mapping))
    assert r.status_code == 303, r.get_data(as_text=True)[:2000]
    form = client.get(r.headers["Location"])
    assert form.status_code == 200
    return tok, form.get_data(as_text=True)


def a_user(role_id: str, name: str):
    auth.ensure_builtin_roles()
    return auth.find_user(name) or auth.create_user(
        name, name, f"{name}-password-123", [role_id], created_by="test")


# ═══ 1. The header ═══════════════════════════════════════════════════════════

def test_a_two_row_merged_header_is_read_as_one():
    st, g = read_first([
        ["Sr. No.", "Description", "Qty", "Unit", "Supply", None, "Installation", None],
        [None, None, None, None, "Rate", "Amount", "Rate", "Amount"],
        ["1", "Pipe", 10, "Mtrs", 100, 1000, 50, 500],
    ], merge=("E1:F1", "G1:H1"))
    assert g["header"] == [0, 1]
    labels = SI.header_labels(g)
    assert labels[4] == "Supply Rate" and labels[7] == "Installation Amount"
    m = SI.guess_mapping(g)
    assert [m[str(c)] for c in range(8)] == [
        "item_no", "description", "qty", "unit",
        "supply_rate", "supply_amount", "install_rate", "install_amount"]


def test_a_title_row_above_the_header_is_not_merged_into_it():
    """A one-label upper row is a title, not a band: carrying "BILL OF
    QUANTITIES" across every column would stamp "quantities" on all of them."""
    _st, g = read_first([["BILL OF QUANTITIES"], HEAD, ["1", "Pipe", 2, "Nos", 10, 20]])
    assert g["header"] == [1, 1]


def test_the_first_data_row_is_never_swallowed_into_the_header():
    """Found by this file: "Rate Only" in a quantity scored the keyword
    "rate", and the row was taken as the second half of a two-row header —
    the line vanished from the import with nothing on the page saying so."""
    _st, g = read_first([HEAD, ["1", "Pipe", "Rate Only", "Mtrs", 100, None]])
    assert g["header"] == [0, 0]
    _st, g = read_first([HEAD, ["1", "Pipe", "Rate Only", "Mtrs", None, None],
                         ["2", "Valve", 2, "Nos", 5, None]])
    assert SI.data_start(g) == 1


def test_a_single_rate_column_is_left_for_the_user_to_call():
    _st, g = read_first([["Sr", "Description", "Qty", "Unit", "Rate", "Amount"],
                         ["1", "Pipe", 10, "Mtrs", 100, 1000]])
    m = SI.guess_mapping(g)
    assert m["4"] == SI.UNDECIDED
    assert "supply_rate" not in m.values() and "install_rate" not in m.values(), (
        "the lone rate was given a track — that is the one guess this import "
        "must never make")
    probs = SI.mapping_problems(g, m)
    assert any("choose Supply or Installation" in p for p in probs)


def test_confirm_refuses_an_undecided_rate_and_then_takes_it_as_the_selling_rate(client):
    """
    ⚠ **AMENDED 6 October 2026** (CLIENT_CHANGES.md §0, forty-fourth block,
    R1): the staged mapping is the ADVICE now, and the advice takes a lone
    rate column as the selling rate — so the staged row no longer holds "?"
    for column E, and posting it back as staged confirms at once. The refusal
    is unchanged and is still proven: a "?" POSTED for the column is refused
    exactly as before. Was:

        m = dict(STORE["boq_imports"][tok]["mapping"])
        r = client.post(f"/boq/import/{tok}", data=mapping_form(m))
        assert r.status_code == 200    # the staged "?" refused
    """
    data = xlsx([["Sr", "Description", "Qty", "Unit", "Rate", "Amount"],
                 ["1", "Pipe", 10, "Mtrs", 100, 1000]])
    tok = token_of(upload(client, data))
    m = dict(STORE["boq_imports"][tok]["mapping"])
    assert m["4"] == "supply_rate", "the advice pre-sets a lone rate as the selling rate"
    m["4"] = SI.UNDECIDED
    r = client.post(f"/boq/import/{tok}", data=mapping_form(m))
    assert r.status_code == 200
    assert "choose Supply or Installation" in r.get_data(as_text=True)
    assert tok in STORE["boq_imports"], "a refused confirm consumed the import"

    m["4"] = "supply_rate"
    r = client.post(f"/boq/import/{tok}", data=mapping_form(m))
    assert r.status_code == 303
    model = model_of(client.get(r.headers["Location"]).get_data(as_text=True))
    ln = model["lines"][0]
    # DECISION ALREADY TAKEN: one rate per track is the SELLING rate, and the
    # base rate stays BLANK for the client to fill in — never a copy of it.
    assert ln["supply_rate"] == "100"
    assert ln["supply_base_rate"] == ""
    assert ln["supply_escalation_pct"] == ""


def test_base_rate_and_escalation_import_as_they_are():
    rows = [["Sr", "Description", "Qty", "Unit", "Supply Mohali Rates", "Supply Esc",
             "Supply Rate", "Supply Amount"],
            ["1", "Pipe", 10, "Mtrs", 1760, 0.15, 2024, 20240],
            ["2", "Valve", 2, "Nos", 1000, 0.07, 1070, 2140]]
    res, g, m = built(rows, formats={"F2": "0%", "F3": "0%"})
    assert m["4"] == "supply_base_rate" and m["5"] == "escalation_pct" and m["6"] == "supply_rate"
    one, two = line(res, "1"), line(res, "2")
    assert one["supply_base_rate"] == 1760.0 and one["supply_rate"] == 2024.0
    # ×100 exactly as tools/gen_demo_data.py read the client's cell — the float
    # dust included, so the seeded figures reproduce bit for bit.
    assert one["escalation_pct"] == 0.15 * 100.0
    assert two["escalation_pct"] == 0.07 * 100.0 == 7.000000000000001
    # A rate that disagrees with base × (1 + esc) is kept as entered.
    assert two["supply_rate"] == 1070.0


def test_an_escalation_typed_as_a_plain_number_is_not_multiplied():
    res, _g, _m = built([["Sr", "Description", "Qty", "Unit", "Supply Base Rate",
                          "Supply Esc %", "Supply Rate"],
                         ["1", "Pipe", 10, "Mtrs", 1000, 15, 1150]])
    assert line(res, "1")["escalation_pct"] == 15.0


def test_a_dash_base_rate_is_blank_and_not_a_flag():
    """The client's "-" in a base-rate cell: negotiated directly — boq._opt_num()'s rule."""
    res, _g, _m = built([["Sr", "Description", "Qty", "Unit", "Supply Base Rate",
                          "Supply Esc", "Supply Rate"],
                         ["1", "Tamper switch", 4, "Nos", "-", None, 2000]])
    ln = line(res, "1")
    assert ln["supply_base_rate"] is None and ln["supply_rate"] == 2000.0
    assert not ln["flags"] and not res["flags"]


# ═══ 2. Quantities that are not numbers ══════════════════════════════════════

@pytest.mark.parametrize("raw", ["I.R.", "R. O."])
def test_rate_only_stays_blank_and_flagged_and_never_zero(raw):
    """
    ⚠ **Amended 1 October 2026 (CLIENT_CHANGES.md §0, thirty-ninth block).**
    The parameters read `["R.O.", "I.R.", "RO", "Rate Only", "R. O."]`. The
    brief's four spellings — "RO", "R.O.", "R/O", "RATE ONLY" — are now a
    RATE-ONLY line at quantity 0 (`tests/test_boq_import_cost.py`); what the
    old pattern matched beyond those two words keeps v1's rule, asserted here
    unchanged.
    """
    res, _g, _m = built([HEAD, ["1", "Pipe", raw, "Mtrs", 100, None]])
    ln = line(res, "1")
    assert ln["qty"] is None
    assert ln["qty"] != 0
    assert ln["block"] is True
    assert any("Rate only on source sheet" in f for f in ln["flags"])
    f = next(f for f in res["flags"] if f["kind"] == "rate_only")
    assert f["severity"] == "red" and f["raw"] == raw and f["col"] == "C"
    # And on the way to the form: an EMPTY string, not "0".
    model = boqimport.editor_model(res)
    assert model["lines"][0]["total_qty"] == ""
    assert model["lines"][0]["_block"] is True


def test_na_an_excel_error_and_a_date_are_flagged_and_left_blank():
    res, _g, _m = built([
        HEAD,
        ["1", "Pipe", "NA", "Mtrs", 100, None],
        ["2", "Valve", "#VALUE!", "Nos", 100, None],
        ["3", "Hose", datetime.date(2024, 3, 1), "Nos", 100, None],
        ["4", "Nozzle", 5, "Nos", "#REF!", None],
    ])
    kinds = {f["row"]: f["kind"] for f in res["flags"]}
    assert kinds == {2: "na", 3: "error", 4: "date", 5: "error"}
    for item in ("1", "2", "3"):
        assert line(res, item)["qty"] is None and line(res, item)["block"]
    # A bad RATE is flagged amber and does not block: the quantity is there.
    four = line(res, "4")
    assert four["qty"] == 5.0 and four["supply_rate"] is None and not four["block"]
    assert next(f for f in res["flags"] if f["row"] == 5)["severity"] == "amber"


@pytest.mark.parametrize("raw", ["9.3+1.5+6", "1.2X3", "(2+3)*4"])
def test_text_arithmetic_is_flagged_and_never_evaluated(raw):
    res, _g, _m = built([HEAD, ["1", "Pipe", raw, "Mtrs", 100, None]])
    ln = line(res, "1")
    assert ln["qty"] is None and ln["block"]
    f = res["flags"][0]
    assert f["kind"] == "arith" and f["raw"] == raw
    assert raw in f["message"]
    blob = json.dumps(res)
    for evaluated in ("16.8", "3.6", "20.0"):
        assert evaluated not in blob, f"{raw!r} was worked out to {evaluated}"


def test_a_formula_with_no_saved_value_is_flagged_not_computed():
    """openpyxl writes formulas with no cached value — exactly the case of a
    workbook generated by a tool and never opened and saved in Excel."""
    res, _g, _m = built([HEAD, ["1", "Pipe", "=2*5", "Mtrs", 100, None]])
    ln = line(res, "1")
    assert ln["qty"] is None and ln["block"]
    f = res["flags"][0]
    assert f["kind"] == "formula"
    assert "open and save in Excel" in f["message"]
    assert "10" not in json.dumps(ln["qty"])


def test_numbers_typed_as_text_are_read_but_words_are_not():
    res, _g, _m = built([HEAD, ["1", "Pipe", "1,200.50", "Mtrs", " 100 ", None],
                         ["2", "Valve", "twelve", "Nos", 5, None]])
    assert line(res, "1")["qty"] == 1200.5 and line(res, "1")["supply_rate"] == 100.0
    assert line(res, "2")["qty"] is None
    assert next(f for f in res["flags"] if f["row"] == 3)["kind"] == "text"


# ═══ 3. Rows that are not lines ══════════════════════════════════════════════

def test_subtotal_total_of_and_carried_forward_rows_are_dropped():
    res, _g, _m = built([
        HEAD,
        ["4", "Pipes", None, None, None, None],
        ["4.1", "25 mm", 10, "Mtrs", 100, 1000],
        [None, "Total of 4.0", None, None, None, 1000],
        [None, "Sub Total", None, None, None, 1000],
        [None, "Carried forward", None, None, None, 1000],
        ["5", "Valve", 1, "Nos", 500, 500],
        [None, "Grand Total", None, None, None, 1500],
    ])
    descs = [l["description"] for l in res["lines"]]
    assert descs == ["Pipes", "25 mm", "Valve"]
    assert res["counts"]["totals_dropped"] == 4


def test_a_heading_that_starts_with_total_is_not_dropped():
    """No figure on the row and more than a bare total word: it is a heading."""
    res, _g, _m = built([HEAD, ["7", "Total flooding system", None, None, None, None],
                         ["7.1", "Nozzle", 3, "Nos", 100, 300]])
    assert line(res, "7")["is_header"] is True
    assert line(res, "7.1")["parent_item_no"] == "7"


def test_parent_header_lines_and_their_children():
    res, _g, _m = built([
        HEAD,
        ["24", "MS pipe, IS 1239 heavy class — the whole clause", None, None, None, None],
        ["24.a", "200 mm", 5, "Mtrs", 3000, None],
        ["24.b", "150 mm", 8, "Mtrs", 2000, None],
        ["25", "Butterfly valve", None, None, None, None],
        ["a)", "150 mm", 1, "Nos", 14572.5, None],
        ["26", "Flow switch", 2, "Nos", 900, None],
    ])
    head = line(res, "24")
    assert head["is_header"] and head["qty"] is None and head["supply_rate"] is None
    assert [line(res, i)["parent_item_no"] for i in ("24.a", "24.b")] == ["24", "24"]
    assert line(res, "a)")["parent_item_no"] == "25"
    assert line(res, "26")["parent_item_no"] == ""
    assert res["counts"] == dict(res["counts"], headers=2, lines=4)


def test_section_rows_become_sections():
    res, _g, _m = built([
        HEAD,
        ["A", "WET SPRINKLER SYSTEM", None, None, None, None],
        ["1", "Sprinkler", 10, "Nos", 300, None],
        ["SECTION B", "Hydrant system", None, None, None, None],
        ["1", "Hydrant valve", 2, "Nos", 5000, None],
        [None, "FIRE PUMPS", None, None, None, None],
        ["1", "Jockey pump", 1, "Set", 90000, None],
    ])
    assert [(s["code"], s["title"]) for s in res["sections"]] == [
        ("A", "WET SPRINKLER SYSTEM"), ("B", "Hydrant system"), ("C", "FIRE PUMPS")]
    assert [l["section"] for l in res["lines"]] == ["A", "B", "C"]
    assert res["counts"]["sections"] == 3


def test_lines_above_the_first_section_row_get_a_free_code():
    res, _g, _m = built([HEAD, ["1", "Before any section", 1, "Nos", 1, None],
                         ["B", "SECOND", None, None, None, None],
                         ["1", "In B", 1, "Nos", 1, None]])
    assert [s["code"] for s in res["sections"]] == ["A", "B"]
    assert [l["section"] for l in res["lines"]] == ["A", "B"]


def test_a_repeated_section_code_is_renamed_and_flagged():
    res, _g, _m = built([HEAD, ["A", "FIRST", None, None, None, None],
                         ["1", "x", 1, "Nos", 1, None],
                         ["A", "AGAIN", None, None, None, None],
                         ["1", "y", 1, "Nos", 1, None]])
    assert [s["code"] for s in res["sections"]] == ["A", "A-2"]
    assert any(f["kind"] == "dup_section" for f in res["flags"])


# ═══ 4. Item numbers — text, verbatim, duplicates kept ═══════════════════════

def test_duplicate_item_numbers_are_both_kept():
    res, _g, _m = built([HEAD, ["17", "Flexible drop", 10, "Nos", 1800, None],
                         ["17", "150 mm butterfly valve", 2, "Nos", 14572.5, None]])
    assert [l["item_no"] for l in res["lines"]] == ["17", "17"]
    assert [l["description"] for l in res["lines"]] == ["Flexible drop", "150 mm butterfly valve"]


def test_four_level_numbering_and_float_item_numbers_are_kept_as_shown():
    """⚠ Amended 1 October 2026: a `0.00`-formatted 1.1 read "1.10" and reads
    "1.1" — rounded to the format's decimals, trailing zeros stripped (the
    brief's rule; `tests/test_boq_import_cost.py`). It asserted
    `line(res, "1.10")`."""
    res, _g, _m = built([
        HEAD,
        ["2.1.4", "Clause", None, None, None, None],
        ["2.1.4.1", "Sub item", 1, "Nos", 10, None],
        [4.1, "Float item", 1, "Nos", 10, None],
        [1.1, "Two-decimal item", 1, "Nos", 10, None],
    ], formats={"A5": "0.00"})
    assert line(res, "2.1.4.1")["parent_item_no"] == "2.1.4"
    assert line(res, "4.1")["description"] == "Float item"
    assert line(res, "1.1")["description"] == "Two-decimal item"
    assert all(isinstance(l["item_no"], str) for l in res["lines"])


def test_an_item_number_excel_turned_into_a_date_is_flagged():
    res, _g, _m = built([HEAD, [datetime.date(2026, 1, 1), "Was 1.1", 1, "Nos", 10, None]])
    assert res["lines"][0]["item_no"] == ""
    assert {f["kind"] for f in res["flags"]} >= {"item_date", "no_item"}


# ═══ 5. Sheets ═══════════════════════════════════════════════════════════════

def test_a_hidden_sheet_is_listed_and_never_preselected():
    visible = [HEAD, ["1", "one", 1, "Nos", 1, None]]
    busier = [HEAD] + [[str(i), f"line {i}", i, "Nos", 10, None] for i in range(1, 30)]
    st = SI.read(xlsx(visible, title="Front", sheets=(("Workings", busier, "hidden"),)), "t.xlsx")
    assert [(s["name"], s["visibility"]) for s in st["sheets"]] == [
        ("Front", "visible"), ("Workings", "hidden")]
    assert st["sheets"][1]["score"] > st["sheets"][0]["score"]
    assert st["selected"] == 0


def test_the_busiest_visible_sheet_is_preselected():
    summary = [["Sr", "System Description", "Supply Amount"], ["A", "PUMPS", 5000]]
    detail = [HEAD] + [[str(i), f"line {i}", i, "Nos", 10, None] for i in range(1, 6)]
    st = SI.read(xlsx(summary, title="Summary", sheets=(("Detail", detail, "visible"),)), "t.xlsx")
    assert st["selected"] == 1


def test_with_every_rate_cell_empty_the_schedule_still_beats_its_summary():
    """Found on the client's own files: rate cells empty on every sheet made
    every score 0, and the one-page summary in front was chosen."""
    head = ["Sr", "Particulars", "Qty", "Unit", "Supply Rate", "Supply Amount"]
    summary = [head, ["A", "PUMPS", None, None, None, 5000], ["1", "x", 1, "Set", None, 5000]]
    detail = [head] + [[str(i), f"line {i}", i, "Nos", None, 100 * i] for i in range(1, 8)]
    st = SI.read(xlsx(summary, title="Summary", sheets=(("Schedule", detail, "visible"),)), "t.xlsx")
    assert [s["score"] for s in st["sheets"]] == [0, 0]
    assert st["selected"] == 1


def test_switching_sheet_in_the_preview_reguesses_the_mapping(client):
    a = [["Sr", "Description", "Qty", "Unit", "Rate"], ["1", "x", 1, "Nos", 1]]
    b = [["Item", "Particulars", "Unit", "Quantity", "Installation Rate"],
         ["1", "y", "Nos", 2, 5]]
    tok = token_of(upload(client, xlsx(a, title="A", sheets=(("B", b, "visible"),))))
    r = client.post(f"/boq/import/{tok}", data={"sheet": "1", "action": "update"})
    assert r.status_code == 303
    rec = STORE["boq_imports"][tok]
    assert rec["sheet_index"] == 1
    assert rec["mapping"]["3"] == "qty" and rec["mapping"]["4"] == "install_rate"


# ═══ 6. The totals check ═════════════════════════════════════════════════════

def test_the_totals_check_matches_within_a_rupee():
    res, _g, _m = built([HEAD, ["1", "Pipe", 3, "Mtrs", 100.25, 300.75],
                         ["2", "Valve", 1, "Nos", 500, 500],
                         [None, "Grand Total", None, None, None, 801.5]])
    assert res["totals"]["status"] == "match"
    c = res["totals"]["checks"][0]
    assert c["computed"] == 800.75 and c["sheet"] == 801.5


def test_the_totals_check_reports_a_mismatch_with_both_figures(client):
    rows = [HEAD, ["1", "Pipe", 3, "Mtrs", 100, 300],
            [None, "Grand Total", None, None, None, 350]]
    res, _g, _m = built(rows)
    t = res["totals"]
    assert t["status"] == "mismatch" and t["row"] == 3
    c = t["checks"][0]
    assert (c["computed"], c["sheet"], c["difference"]) == (300.0, 350.0, -50.0)
    body = client.get(f"/boq/import/{token_of(upload(client, xlsx(rows)))}").get_data(as_text=True)
    assert "does not match" in body and "350.00" in body and "300.00" in body


def test_no_grand_total_is_said_so():
    res, _g, _m = built([HEAD, ["1", "Pipe", 3, "Mtrs", 100, 300]])
    assert res["totals"]["status"] == "no_total"


def test_two_tracks_are_checked_separately():
    res, _g, _m = built([
        ["Sr", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount",
         "Installation Rate", "Installation Amount"],
        ["1", "Pipe", 2, "Mtrs", 100, 200, 50, 100],
        [None, "Grand Total", None, None, None, 200, None, 999]])
    by = {c["track"]: c["status"] for c in res["totals"]["checks"]}
    assert by == {"supply": "match", "install": "mismatch"}


# ═══ 7. What the file must be ════════════════════════════════════════════════

@pytest.mark.parametrize("data", [
    b"%PDF-1.4 not a workbook",
    b"Sr,Description,Qty\n1,Pipe,10\n",
    bytes.fromhex("4d5a9000") + bytes(64),
])
def test_bytes_that_are_not_excel_are_refused(data):
    with pytest.raises(SI.Refused) as exc:
        SI.read(data, "boq.xlsx")
    assert "not an Excel workbook" in exc.value.message


def test_a_refused_upload_stages_nothing(client):
    r = upload(client, b"Sr,Description\n1,Pipe\n", "boq.xlsx")
    assert r.status_code == 200
    assert "not an Excel workbook" in r.get_data(as_text=True)
    assert not STORE["boq_imports"]


def _rezip(data: bytes, edit) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            z.writestr(info.filename, edit(info.filename, src.read(info.filename)))
    return out.getvalue()


def test_an_xlsm_is_refused_by_content_type_and_by_name():
    plain = xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])
    macro = _rezip(plain, lambda n, b: b.replace(b"sheet.main+xml",
                                                 b"sheet.macroEnabled.main+xml")
                   if n == "[Content_Types].xml" else b)
    for data, name in ((macro, "boq.xlsx"), (plain, "boq.xlsm")):
        with pytest.raises(SI.Refused) as exc:
            SI.read(data, name)
        assert "macros" in exc.value.message


def test_a_vba_project_inside_the_zip_is_refused():
    plain = xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])
    src = zipfile.ZipFile(io.BytesIO(plain))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            z.writestr(info.filename, src.read(info.filename))
        z.writestr("xl/vbaProject.bin", b"\x00" * 16)
    with pytest.raises(SI.Refused) as exc:
        SI.read(out.getvalue(), "boq.xlsx")
    assert "macros" in exc.value.message


def test_a_zip_bomb_is_refused_by_arithmetic_before_openpyxl_runs(monkeypatch):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b"spreadsheetml.sheet.main+xml")
        z.writestr("xl/worksheets/sheet1.xml", bytes(51 * 1024 * 1024))
    data = out.getvalue()
    assert len(data) < SI.MAX_UPLOAD_BYTES, "the bomb must get past the upload cap"

    def never(*_a, **_k):
        raise AssertionError("openpyxl was handed a zip bomb")
    monkeypatch.setattr(openpyxl, "load_workbook", never)
    with pytest.raises(SI.Refused) as exc:
        SI.read(data, "boq.xlsx")
    assert "unpacks to 51 MB" in exc.value.message


def test_an_upload_over_five_megabytes_is_refused():
    with pytest.raises(SI.Refused) as exc:
        SI.read(b"PK\x03\x04" + bytes(SI.MAX_UPLOAD_BYTES), "boq.xlsx")
    assert "limit is 5 MB" in exc.value.message


def test_an_xlsx_is_refused_when_defusedxml_is_not_active(monkeypatch):
    import openpyxl.xml
    monkeypatch.setattr(openpyxl.xml, "DEFUSEDXML", False)
    with pytest.raises(SI.Refused) as exc:
        SI.read(xlsx([HEAD]), "boq.xlsx")
    assert "defusedxml" in exc.value.message
    assert SI.available()["xlsx"] is False


def test_openpyxl_really_is_parsing_through_defusedxml():
    """The positive control for the test above: on this box the flag is on,
    so the refusal is reachable only by switching it off."""
    import openpyxl.xml
    assert openpyxl.xml.DEFUSEDXML is True
    assert SI.available()["xlsx"] is True


# ═══ 8. Oversize — refused whole, never truncated ════════════════════════════

def test_an_oversize_schedule_is_refused_not_truncated(client):
    n = boq.MAX_LINES + 1
    rows = [HEAD] + [[str(i), f"line {i}", 1, "Nos", 10, None] for i in range(1, n + 1)]
    tok = token_of(upload(client, xlsx(rows)))
    m = STORE["boq_imports"][tok]["mapping"]
    r = client.post(f"/boq/import/{tok}", data=mapping_form(m))
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert f"This sheet has {n} lines; the BOQ limit is about {boq.MAX_LINES}" in body
    assert "Create BOQ" not in body or "var MODEL" not in body
    assert STORE["boq_imports"][tok]["confirmed"] is False
    # The model the refusal measured is the WHOLE sheet.
    g = boqimport._grid(STORE["boq_imports"][tok])
    assert len(boqimport.editor_model(SI.build(g, SI.clean_mapping(g, m)))["lines"]) == n


def test_a_schedule_too_large_by_bytes_names_a_smaller_limit():
    rows = [HEAD] + [[str(i), "x" * 3000, 1, "Nos", 10, None] for i in range(1, 121)]
    res, _g, _m = built(rows)
    msg = boqimport.too_large(boqimport.editor_model(res))
    about = int(re.search(r"limit is about (\d+)", msg).group(1))
    assert "This sheet has 120 lines" in msg and about < 120


def test_a_sheet_past_the_grid_limit_is_refused_not_cut(monkeypatch):
    monkeypatch.setattr(SI, "MAX_GRID_ROWS", 10)
    rows = [HEAD] + [[str(i), f"l{i}", 1, "Nos", 1, None] for i in range(1, 12)]
    with pytest.raises(SI.Refused) as exc:
        SI.read(xlsx(rows), "boq.xlsx")
    assert "more than 10 rows" in exc.value.message


def test_a_long_cell_is_cut_only_with_a_flag():
    long = "Specification " * 400
    res, _g, _m = built([HEAD, ["1", long, 1, "Nos", 1, None]])
    ln = line(res, "1")
    assert len(ln["description"]) == SI.MAX_CELL_CHARS
    assert any(f["kind"] == "long" for f in res["flags"])


def test_the_client_length_of_a_clause_survives_whole():
    """The brief's 500-character cap would have cut 20 of the 56 seeded clauses."""
    import demo_data as DD
    longest = max((s["spec_text"] for s in DD.SPECS), key=len)
    assert len(longest) > 500
    res, _g, _m = built([HEAD, ["1", longest, None, None, None, None]])
    assert line(res, "1")["description"] == longest
    assert not res["flags"]


# ═══ 9. The upload: in memory, bounded ═══════════════════════════════════════

def test_the_upload_never_reaches_werkzeugs_temporary_file(client, monkeypatch):
    import werkzeug.wrappers.request as WR

    def spool(*_a, **_k):
        raise AssertionError("the upload went through Werkzeug's disk spool")
    monkeypatch.setattr(WR, "default_stream_factory", spool)
    r = upload(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]]))
    assert r.status_code == 303


def test_the_spool_patch_point_is_the_real_one(monkeypatch):
    """The control for the test above: an ordinary multipart request DOES
    reach that factory, so a green result there is not a patch that missed."""
    import werkzeug.wrappers.request as WR
    from werkzeug.test import EnvironBuilder

    called = []

    def spool(*a, **k):
        called.append(1)
        return io.BytesIO()
    monkeypatch.setattr(WR, "default_stream_factory", spool)
    env = EnvironBuilder(method="POST", data={"f": (io.BytesIO(b"abc"), "a.xlsx")}).get_environ()
    assert WR.Request(env).files["f"].read() == b"abc"
    assert called


def test_an_over_cap_upload_is_refused_before_the_body_is_parsed(client, monkeypatch):
    def never(*_a, **_k):
        raise AssertionError("an over-cap upload was parsed")
    monkeypatch.setattr(SI, "read", never)
    big = b"PK\x03\x04" + bytes(SI.MAX_UPLOAD_BYTES + boqimport.FORM_OVERHEAD_BYTES)
    r = upload(client, big)
    assert r.status_code == 200
    assert "limit is 5 MB" in r.get_data(as_text=True)
    assert not STORE["boq_imports"]


def test_the_staged_row_holds_cell_values_and_never_the_file(client):
    data = xlsx([HEAD, ["1", "Pipe", 1, "Nos", 1, None]])
    tok = token_of(upload(client, data))
    rec = STORE["boq_imports"][tok]
    blob = json.dumps(rec)
    assert "PK\\u0003\\u0004" not in blob and "[Content_Types]" not in blob
    # `rate_mode` and `markup` from 1 October 2026 — selling rates or our cost.
    # ⚠ AMENDED 6 October 2026 (the §0 forty-fourth block, R4/R5): `ticked`,
    #   `tab_maps` and `names` — the tabs to build, the other tabs' mappings,
    #   and the names as typed on the preview; still cell values only. Was:
    #     {"id", "token", "user_id", "created_at", "created_ts", "filename",
    #      "format", "sheets", "grid", "sheet_index", "mapping", "layout",
    #      "known", "confirmed", "rate_mode", "markup"}
    assert set(rec) == {"id", "token", "user_id", "created_at", "created_ts", "filename",
                        "format", "sheets", "grid", "sheet_index", "mapping", "layout",
                        "known", "confirmed", "rate_mode", "markup",
                        "ticked", "tab_maps", "names"}
    assert rec["grid"][0]["rows"][1][1][:2] == ["1", "Pipe"]


# ═══ 10. The staging row: owned, consumed, purged, capped ═══════════════════

def test_another_users_token_is_a_404_and_is_not_consumed(client):
    tok = token_of(upload(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])))
    STORE["boq_imports"][tok]["confirmed"] = True
    other = a_user("role-owner", "import-other")
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = other["id"]
    for method, url in (("get", f"/boq/import/{tok}"), ("post", f"/boq/import/{tok}"),
                        ("get", f"/boq/import/{tok}/form")):
        r = getattr(client, method)(url, data={"action": "confirm"} if method == "post" else None)
        assert r.status_code == 404, (method, url, r.status_code)
        assert "not available" in r.get_data(as_text=True)
    assert tok in STORE["boq_imports"], "somebody else's request consumed the import"
    # A token that never existed gets the very same page.
    r = client.get("/boq/import/no-such-token")
    assert r.status_code == 404 and "not available" in r.get_data(as_text=True)


def test_the_staged_row_is_deleted_once_the_form_renders(client):
    tok, body = confirm_to_form(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]]))
    assert "Imported from" in body
    assert tok not in STORE["boq_imports"]
    assert client.get(f"/boq/import/{tok}/form").status_code == 404


def test_rows_older_than_24_hours_are_purged_on_any_import_request(client):
    tok = token_of(upload(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])))
    STORE["boq_imports"][tok]["created_ts"] -= boqimport.STAGE_TTL_SECONDS + 1
    assert client.get("/boq/import").status_code == 200
    assert tok not in STORE["boq_imports"]


def test_a_row_younger_than_24_hours_survives_the_purge(client):
    tok = token_of(upload(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])))
    STORE["boq_imports"][tok]["created_ts"] -= boqimport.STAGE_TTL_SECONDS - 60
    client.get("/boq/import")
    assert tok in STORE["boq_imports"]


def test_a_user_keeps_at_most_three_staged_imports(client):
    data = xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])
    toks = []
    for i in range(4):
        toks.append(token_of(upload(client, data)))
        # Distinct ages, oldest first, so "the oldest goes" is observable.
        STORE["boq_imports"][toks[-1]]["created_ts"] = time.time() - 100 + i
    assert len(STORE["boq_imports"]) == boqimport.MAX_STAGED_PER_USER
    assert toks[0] not in STORE["boq_imports"], "the cap dropped the wrong import"
    assert all(t in STORE["boq_imports"] for t in toks[1:])


def test_the_token_never_travels_in_a_query_string(client):
    tok = token_of(upload(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]])))
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert f"?token={tok}" not in body and f"token={tok}" not in body
    assert f'action="/boq/import/{tok}"' in body


# ═══ 11. The known layout ════════════════════════════════════════════════════

def test_a_known_layout_skips_the_preview(client):
    first = xlsx([HEAD, ["1", "first", 1, "Nos", 10, None]])
    confirm_to_form(client, first)
    sig = next(iter(STORE["import_layouts"]))
    assert STORE["import_layouts"][sig]["use_count"] == 1

    again = xlsx([HEAD, ["9", "different data, same template", 4, "Mtrs", 55, None]])
    r = upload(client, again)
    assert r.status_code == 303 and r.headers["Location"].endswith("/form")
    tok = token_of(r)
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Recognised a layout" in body
    assert f'href="/boq/import/{tok}">Change mapping' in body
    assert model_of(body)["lines"][0]["description"] == "different data, same template"
    assert STORE["import_layouts"][sig]["use_count"] == 2
    # Kept for the Change-mapping link — and that link works.
    assert tok in STORE["boq_imports"]
    assert client.get(f"/boq/import/{tok}").status_code == 200


def test_a_different_layout_still_gets_the_preview(client):
    confirm_to_form(client, xlsx([HEAD, ["1", "first", 1, "Nos", 10, None]]))
    other = [["Item", "Particulars", "Quantity", "UOM", "Supply Rate"], ["1", "x", 1, "Nos", 1]]
    r = upload(client, xlsx(other))
    assert r.status_code == 303 and not r.headers["Location"].endswith("/form")


# ═══ 12. The form — and saving it the ordinary way ═══════════════════════════

def test_the_create_form_links_to_the_import(client):
    body = client.get("/boq/create").get_data(as_text=True)
    assert 'href="/boq/import"' in body and "Import from Excel" in body


def test_the_plain_create_form_carries_no_import_banner_or_action(client):
    body = client.get("/boq/create").get_data(as_text=True)
    assert '<form method="POST" onsubmit="return saveJSON()">' in body
    assert "Imported from" not in body


def test_the_prefilled_form_posts_to_boq_create(client):
    _tok, body = confirm_to_form(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]]))
    assert '<form method="POST" action="/boq/create" onsubmit="return saveJSON()">' in body
    assert "Nothing has been saved" in body


def _save(client, model, **over):
    form = {"date": "2026-09-29", "project_name": "Imported project",
            "account_name": "Imported customer", "rev_no": "0",
            "boq_json": json.dumps(model)}
    form.update(over)
    return client.post("/boq/create", data=form)


def test_saving_the_imported_form_is_the_ordinary_save(client):
    # ⚠ The blocked quantity is "NA" from 1 October 2026; it was "R.O.", which
    #   is now a rate-only line at 0 and no longer blocks.
    data = xlsx([HEAD, ["1", "Pipe", 10, "Mtrs", 100, None],
                 ["1", "Pipe again", 2, "Mtrs", 90, None],
                 ["2", "Valve", "NA", "Nos", 500, None]])
    _tok, body = confirm_to_form(client, data)
    model = model_of(body)
    assert all(l["line_id"] == "" for l in model["lines"])
    model["lines"][2]["total_qty"] = "3"            # what the red band asks for
    before = set(STORE["boqs"])
    r = _save(client, model)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (bid,) = set(STORE["boqs"]) - before
    rec = STORE["boqs"][bid]
    items = rec["line_items"]
    assert [l["item_no"] for l in items] == ["1", "1", "2"]
    assert all(re.fullmatch(r"[0-9a-f]{12}", l["line_id"]) for l in items)
    assert len({l["line_id"] for l in items}) == 3
    assert items[0]["supply_base_rate"] is None and items[0]["supply_rate"] == 100.0
    assert items[2]["total_qty"] == 3.0
    assert not any(k.startswith("_") for l in items for k in l), "UI state reached the record"
    assert not STORE["boq_imports"]


def test_gap_42_a_blank_quantity_posted_anyway_is_saved_as_zero(client):
    """
    ⚠ **A TRIPWIRE, not a requirement.** ABOUT.md §7 gap 42: `_clean_lines()`
    reads a blank typed quantity as 0.0, and this pass was told not to change
    that path. The browser refuses to submit while an imported line is still
    blank (the JS test below); a POST that bypasses the browser is saved at 0.
    When gap 42 is closed this test SHOULD fail — rewrite it to the new rule
    then, keeping this docstring's old assertion quoted.

    ⚠ The blocked quantity is "NA" from 1 October 2026; it was "R.O.", which
    is now a rate-only line at quantity 0 and is no longer blank.
    """
    data = xlsx([HEAD, ["1", "Valve", "NA", "Nos", 500, None]])
    _tok, body = confirm_to_form(client, data)
    model = model_of(body)
    assert model["lines"][0]["total_qty"] == "" and model["lines"][0]["_block"]
    before = set(STORE["boqs"])
    assert _save(client, model).status_code == 302
    (bid,) = set(STORE["boqs"]) - before
    assert STORE["boqs"][bid]["line_items"][0]["total_qty"] == 0.0


def test_a_rejected_save_keeps_the_flags_on_the_rows(client):
    _tok, body = confirm_to_form(client, xlsx([HEAD, ["1", "Valve", "NA", "Nos", 5, None]]))
    model = model_of(body)
    r = _save(client, model, project_name="")
    assert r.status_code == 200
    again = model_of(r.get_data(as_text=True))
    assert again["lines"][0]["_block"] is True and again["lines"][0]["_flags"]


def test_duplicate_detection_still_runs_on_an_imported_revision(client):
    """The ordinary revision checks run on an imported schedule unchanged: a
    rev_no above 0 with nothing superseded is refused exactly as when typed."""
    _tok, body = confirm_to_form(client, xlsx([HEAD, ["1", "x", 1, "Nos", 1, None]]))
    r = _save(client, model_of(body), rev_no="1")
    assert r.status_code == 200
    assert "no BOQ was chosen" in r.get_data(as_text=True)


# ═══ 13. Escaping — a hostile workbook, both pages ═══════════════════════════

PAYLOAD = "<script>alert(1)</script>\"'&<img src=x onerror=alert(2)>"


def test_a_hostile_workbook_is_escaped_on_the_preview_and_the_form(client):
    rows = [HEAD, [PAYLOAD, "Desc " + PAYLOAD, "R.O." + PAYLOAD, "Nos" + PAYLOAD, 5, None]]
    data = xlsx(rows, title="Sheet <b onmouseover=x>")
    r = upload(client, data, name="evil" + PAYLOAD + ".xlsx")
    tok = token_of(r)
    for url in (f"/boq/import/{tok}",):
        body = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in body
        assert "<img src=x onerror=alert(2)>" not in body
        assert "<b onmouseover=x>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    m = dict(STORE["boq_imports"][tok]["mapping"])
    r = client.post(f"/boq/import/{tok}", data=mapping_form(m))
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "<img src=x onerror=alert(2)>" not in body
    assert "<b onmouseover=x>" not in body


# ═══ 14. Access and the import graph ═════════════════════════════════════════

def test_every_import_route_carries_the_boq_create_permission():
    import app as app_module
    eps = {r.endpoint for r in app_module.app.url_map.iter_rules()
           if r.endpoint.startswith("boqimport.")}
    assert eps == {"boqimport.upload", "boqimport.preview", "boqimport.form"}
    for ep in eps:
        assert auth.ROUTE_PERMISSIONS[ep] == auth.ROUTE_PERMISSIONS["boq.create_boq"] == "boq.create"
    doc = (REPO / "docs" / "ACCESS_MATRIX.md").read_text(encoding="utf8")
    assert ("| `boq.create` | `boq.create_boq`, `boqimport.form`, "
            "`boqimport.preview`, `boqimport.upload` |") in doc


def test_a_role_without_boq_create_is_refused_every_import_route(client):
    hr = a_user("role-hr", "import-hr")
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = hr["id"]
    for url in ("/boq/import", "/boq/import/x", "/boq/import/x/form"):
        assert client.get(url).status_code == 403, url
    assert upload(client, xlsx([HEAD])).status_code == 403


def test_the_import_page_is_drawn_for_a_holder_and_not_for_hr():
    owner = a_user("role-owner", "import-owner2")
    hr = a_user("role-hr", "import-hr2")
    assert auth.can_reach("boqimport.upload", owner)
    assert not auth.can_reach("boqimport.upload", hr)


# ═══ 15. The editor's red block — the real JavaScript, under Node ═══════════

def _node(boot: dict, script: str):
    """Run boq._BOQ_JS against `boot` and `script` in one Node process, fed on
    STDIN — no temporary file is written."""
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_form_will_not_submit_while_an_imported_quantity_is_blank():
    # "NA" from 1 October 2026 — "R.O." is a rate-only line now, at 0.
    res, _g, _m = built([HEAD, ["1", "Pipe", 10, "Mtrs", 100, None],
                         ["2", "Valve", "NA", "Nos", 500, None]])
    boot = boqimport.editor_model(res)
    got = _node(boot, """
      var first = saveJSON();
      var band = STUB['import-block'].innerHTML;
      var posted = STUB['boq_json'].value;
      setLine(1, 'total_qty', '4');
      var second = saveJSON();
      console.log(JSON.stringify({first: first, band: band, posted: posted,
                                  second: second, after: STUB['import-block'].innerHTML,
                                  sent: JSON.parse(STUB['boq_json'].value).lines[1].total_qty}));
    """)
    assert got["first"] is False and got["posted"] == ""
    assert "1 imported line needs a quantity before this BOQ can be saved" in got["band"]
    assert got["second"] is True and got["after"] == "" and got["sent"] == "4"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_moving_a_blocked_line_does_not_give_it_a_default_quantity():
    # "NA" from 1 October 2026 — "R.O." is a rate-only line now, at 0.
    res, _g, _m = built([HEAD, ["A", "FIRST", None, None, None, None],
                         ["1", "Valve", "NA", "Nos", 500, None],
                         ["B", "SECOND", None, None, None, None],
                         ["1", "Pipe", 3, "Mtrs", 10, None]])
    boot = boqimport.editor_model(res)
    got = _node(boot, """
      setSection(0, 'B');
      console.log(JSON.stringify({qty: MODEL.lines[0].total_qty, ok: saveJSON()}));
    """)
    assert got == {"qty": "", "ok": False}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_flagged_row_carries_a_chip():
    res, _g, _m = built([HEAD, ["1", "Pipe", 10, "Mtrs", "#REF!", None],
                         ["2", "Valve", "NA", "Nos", 5, None]])
    got = _node(boqimport.editor_model(res), """
      MODEL.sections[0]._open = true; renderLines();
      console.log(JSON.stringify(STUB['line-editor'].innerHTML));
    """)
    assert 'class="ls-flag"' in got and 'class="ls-flag is-red"' in got
    assert "quantity needed" in got


# ═══ 16. The client's own files, when this box has them ══════════════════════

def test_importing_the_sify_workbook_reproduces_the_seeded_boq(client, sify_boq_xlsx):
    """
    ⚠ **Never run on the box that wrote it** — `sify_boq.xlsx` is gitignored
    and was absent there, so this skips. The mapping is the one
    `tools/gen_demo_data.py` reads the sheet with (A item, B description,
    E total qty, F unit, G/H/I supply base / escalation / rate, K/L
    installation base / rate), confirmed the way an operator would; the
    comparison is every imported line that carries an item number — the rows
    the generator itself takes — against the 97 seeded lines, in order.
    """
    import demo_data as DD
    st = SI.read(sify_boq_xlsx.read_bytes(), "sify_boq.xlsx")
    idx = next(i for i, s in enumerate(st["sheets"]) if s["name"] == "Quotation")
    g = st["grid"][idx]
    mapping = {str(c): "" for c in g["cols"]}
    mapping.update({"0": "item_no", "1": "description", "4": "qty", "5": "unit",
                    "6": "supply_base_rate", "7": "escalation_pct", "8": "supply_rate",
                    "10": "install_base_rate", "11": "install_rate"})
    res = SI.build(g, mapping)
    got = [l for l in res["lines"] if l["item_no"]]
    client.get("/boq/")
    seeded = STORE["boqs"][DD.BOQ_META["id"]]["line_items"]
    assert len(got) == len(seeded)
    for imp, seed in zip(got, seeded):
        assert imp["item_no"] == seed["item_no"]
        assert imp["description"] == seed["description"]
        if seed["is_header"]:
            assert imp["is_header"]
            continue
        assert (imp["qty"] or 0.0) == seed["total_qty"], seed["item_no"]
        assert imp["unit"] == seed["unit"], seed["item_no"]
        assert imp["supply_base_rate"] == seed["supply_base_rate"], seed["item_no"]
        assert (imp["escalation_pct"] or 0.0) == seed["supply_escalation_pct"], seed["item_no"]
        assert (imp["supply_rate"] or 0.0) == seed["supply_rate"], seed["item_no"]
        assert imp["install_base_rate"] == seed["install_base_rate"], seed["item_no"]
        assert (imp["install_rate"] or 0.0) == seed["install_rate"], seed["item_no"]


def _client_xls():
    d = REPO / "client_docs"
    return sorted(d.glob("*.xls")) if d.is_dir() else []


@pytest.mark.skipif(not _client_xls(), reason="no client_docs/*.xls on this box "
                    "(the folder is gitignored and holds the client's own files)")
def test_every_client_xls_reads_through_the_xls_path():
    """Structural only — no client figure or name is asserted or printed."""
    for path in _client_xls():
        st = SI.read(path.read_bytes(), path.name)
        assert st["format"] == "xls", path.name
        assert any(s["staged"] for s in st["sheets"]), path.name
        g = st["grid"][st["selected"]]
        SI.build(g, SI.guess_mapping(g))
