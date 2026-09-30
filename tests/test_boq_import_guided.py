"""
Import BOQ from Excel — the structure, the totals, the real flags and the
guided fix on /boq/create (30 September 2026, CLIENT_CHANGES.md §0,
thirty-seventh block).

Every workbook here is BUILT IN MEMORY; the client's Jamnagar sheet is never
read by a test. `jamnagar()` reproduces its rows 5 to 17 at their real row
numbers — the two-row heading at rows 3 and 4 included — with the figures the
sheet carries.

The rules under test (ABOUT.md §5 `/boq/import`, *The structure*):

* a sub-heading, spec text and a numbered header need no item number and are
  never flagged; a priced row with no number under a numbered one is
  <parent>.a, .b … .z, .aa — "auto" — or the sheet's own "a)" — "sheet";
* an amount alone is a subtotal / section / grand / combined total by
  arithmetic (a footing check, never a line) or a LUMP SUM; a zero is none;
* the blocking flags: no quantity; an amount or a quantity with no rate;
  qty × rate more than ±1.00 off the sheet's amount;
* the prefilled form rings exactly those fields, server-side on a refused
  POST too — and the save accepts exactly what it always did.
"""

import io
import json
import re
import shutil
import subprocess

import pytest

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")

import boq                     # noqa: E402
import boqimport               # noqa: E402
import sheetimport as SI       # noqa: E402
from store import STORE        # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

HEAD2 = [["Sr.No.", "Description of Material & Service", "Make", "Qty", "Supply",
          "Amount", "Installation ", "Amount"],
         [None, None, None, None, "Rate", None, "Rate", None]]
TOP = [["  Samruddhi fire"], ["FIRE FIGHTING SYSTEM VERTIV"]]

# Rows 5 to 17 of the client's hydrant sheet, at their own row numbers.
ROWS_5_17 = [
    [None, "(A) BOQ FOR HYDRANT SYSTEM"],                                       # 5
    [None, "Hydrant System Line"],                                              # 6
    [1, "COAL TAR TAPE 4MM THICK AS PER  IS 10221", "OEM"],                     # 7
    [None, "Supply, Installation, Testing & Commissioning of coal tar tape"],   # 8
    [None, "150 mm NB", None, 350, 3050, 1067500, 1380, 483000],               # 9
    [None, "100 mm NB", None, 50, 2210, 110500, 920, 46000],                   # 10
    [None, "80 mm NB", None, 50, 2500, 125000, 690, 34500],                    # 11
    [2, "Supply, Installation, Testing & Commissioning of RCC Hume Pipe"],     # 12
    [None, "300 mm NB", None, 350],                                             # 13
    [3, "M.S. PIPE CLASS-C HEAVY DUTY"],                                        # 14
    [None, "Supply, Installation, Testing & Commissioning of MS pipe", "Jindal "],  # 15
    [None, "150 mm   (ERW Pipe IS1239 HVY BBE)", None, 1000, 2450, 2450000, 1110, 1110000],  # 16
    [None, "100 mm   (ERW Pipe IS1239 HVY BBE)", None, 36, 1600, 57600, 740, 26640],        # 17
]

SIMPLE = ["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount",
          "Installation Rate", "Installation Amount"]


def xlsx(rows, title="Quotation") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def built(rows):
    st = SI.read(xlsx(rows), "t.xlsx")
    g = st["grid"][st["selected"]]
    m = SI.guess_mapping(g)
    return SI.build(g, m), g, m


def jamnagar(extra=()):
    return built(TOP + HEAD2 + ROWS_5_17 + list(extra))


def by_row(res, rnum):
    return next(l for l in res["lines"] if l["row"] == rnum)


def flags_on(res, rnum):
    return [f for f in res["flags"] if f["row"] == rnum]


# ═══ A. The structure — rows 5 to 17 ══════════════════════════════════════════

def test_the_heading_pair_and_the_amount_tracks():
    res, g, m = jamnagar()
    assert g["header"] == [2, 3]
    # F and H name no track; each takes the rate column to its left.
    assert [m[str(c)] for c in range(8)] == [
        "item_no", "description", "make", "qty",
        "supply_rate", "supply_amount", "install_rate", "install_amount"]


def test_rows_5_to_17_derive_the_expected_structure():
    res, _g, _m = jamnagar()
    assert res["sections"] == [{"code": "A", "title": "BOQ FOR HYDRANT SYSTEM"}]
    got = {l["row"]: (l["kind"], l["item_no"], l["parent_item_no"], l["is_header"], l["item_src"])
           for l in res["lines"]}
    assert got == {
        6:  ("subheading", "", "", True, ""),
        7:  ("header", "1", "", True, "sheet"),
        8:  ("spec_text", "", "1", True, ""),
        9:  ("sub_item", "1.a", "1", False, "auto"),
        10: ("sub_item", "1.b", "1", False, "auto"),
        11: ("sub_item", "1.c", "1", False, "auto"),
        12: ("header", "2", "", True, "sheet"),
        13: ("sub_item", "2.a", "2", False, "auto"),
        14: ("header", "3", "", True, "sheet"),
        15: ("spec_text", "", "3", True, ""),
        16: ("sub_item", "3.a", "3", False, "auto"),
        17: ("sub_item", "3.b", "3", False, "auto"),
    }
    assert by_row(res, 15)["make"] == "Jindal", "the Make on spec text is kept"
    assert by_row(res, 7)["make"] == "OEM"


def test_rows_6_and_8_carry_no_flag_and_row_13_needs_a_rate():
    res, _g, _m = jamnagar()
    assert not flags_on(res, 6) and not by_row(res, 6)["needs"]
    assert not flags_on(res, 8) and not by_row(res, 8)["needs"]
    thirteen = by_row(res, 13)
    assert [n["field"] for n in thirteen["needs"]] == ["rate"]
    assert [f["kind"] for f in flags_on(res, 13)] == ["no_rate"]
    assert flags_on(res, 13)[0]["severity"] == "red"
    assert thirteen["qty"] == 350.0
    # Row 13 is the ONLY blocking flag in rows 5 to 17.
    assert [(n["row"], n["field"]) for n in res["needs"]] == [(13, "rate")]
    assert res["counts"]["auto_items"] == 6


def test_no_line_is_flagged_for_a_missing_item_number_any_more():
    res, _g, _m = jamnagar()
    assert not [f for f in res["flags"] if f["kind"] == "no_item"]


def test_the_form_model_folds_spec_text_and_sub_headings():
    """The save refuses a line with no item number, so what `build()` derives
    as spec text is folded into its parent, and a sub-heading into the
    section title. Nothing on the sheet is dropped."""
    res, _g, _m = jamnagar()
    model = boqimport.editor_model(res)
    assert all(l["item_no"] for l in model["lines"])
    assert model["sections"][0]["title"] == "BOQ FOR HYDRANT SYSTEM — Hydrant System Line"
    one = next(l for l in model["lines"] if l["item_no"] == "1")
    assert one["description"].endswith("\nSupply, Installation, Testing & Commissioning of coal tar tape")
    assert one["remark"] == "Make: OEM"
    three = next(l for l in model["lines"] if l["item_no"] == "3")
    assert three["remark"] == "Make: Jindal"
    assert [l["item_no"] for l in model["lines"]] == [
        "1", "1.a", "1.b", "1.c", "2", "2.a", "3", "3.a", "3.b"]
    assert next(l for l in model["lines"] if l["item_no"] == "1.a")["_item_src"] == "auto"


def test_a_priced_standalone_numbered_item():
    res, _g, _m = built([SIMPLE, ["21", "Electric hooter", 1, "Nos", None, None, 9000, 9000],
                         [None, "wired to the panel", None, None, None, None, None, None]])
    one = by_row(res, 2)
    assert (one["kind"], one["item_no"], one["is_header"], one["parent_item_no"]) == ("item", "21", False, "")
    assert one["install_rate"] == 9000.0 and not one["needs"], "installation-only is a valid line"
    txt = by_row(res, 3)
    assert (txt["kind"], txt["parent_item_no"]) == ("spec_text", "21")


def test_sheet_provided_labels_are_used_as_they_stand():
    res, _g, _m = built([SIMPLE, ["4", "Butterfly valve", None, None, None, None, None, None],
                         [None, "a) 150 mm", 2, "Nos", 100, 200, None, None],
                         [None, "(b) 100 mm", 2, "Nos", 90, 180, None, None],
                         [None, "c. 80 mm", 1, "Nos", 80, 80, None, None],
                         [None, "65 mm", 1, "Nos", 70, 70, None, None]])
    kids = [(l["item_no"], l["item_src"], l["description"]) for l in res["lines"] if not l["is_header"]]
    assert kids == [("4.a", "sheet", "150 mm"), ("4.b", "sheet", "100 mm"),
                    ("4.c", "sheet", "80 mm"), ("4.d", "auto", "65 mm")]


def test_the_counter_runs_past_z_to_aa():
    rows = [SIMPLE, ["9", "Sprinkler heads, many sizes", None, None, None, None, None, None]]
    rows += [[None, f"size {k}", 1, "Nos", 10, 10, None, None] for k in range(29)]
    res, _g, _m = built(rows)
    nos = [l["item_no"] for l in res["lines"] if not l["is_header"]]
    assert nos[:2] == ["9.a", "9.b"] and nos[25] == "9.z"
    assert nos[26:] == ["9.aa", "9.ab", "9.ac"]
    assert SI.sub_label(0) == "a" and SI.sub_label(25) == "z" and SI.sub_label(26) == "aa"


def test_the_counter_resets_at_every_numbered_row_and_section():
    res, _g, _m = built([SIMPLE, ["A", "PUMPS", None, None, None, None, None, None],
                         ["1", "Pump", None, None, None, None, None, None],
                         [None, "x", 1, "Nos", 1, 1, None, None],
                         ["2", "Panel", None, None, None, None, None, None],
                         [None, "y", 1, "Nos", 1, 1, None, None],
                         ["B", "HYDRANTS", None, None, None, None, None, None],
                         ["1", "Valve", None, None, None, None, None, None],
                         [None, "z", 1, "Nos", 1, 1, None, None]])
    assert [(l["section"], l["item_no"]) for l in res["lines"] if not l["is_header"]] == [
        ("A", "1.a"), ("A", "2.a"), ("B", "1.a")]


# ═══ The heading ══════════════════════════════════════════════════════════════

def test_a_repeated_heading_drops_nothing_above_it():
    """The Sify shape: the heading again above section B, scoring HIGHER than
    the first. Every row above the repeat is read; the repeat is not a line
    and is not flagged."""
    first = ["Sr.", "Description", "Total QTY", "Unit", "Supply", "Installation"]
    again = ["Sr. No.", "Description of Items", "Total Qty", "Unit",
             "Supply Rate (INR)", "Installation Rate (INR)"]
    res, g, _m = built([first,
                        ["A", "WET SPRINKLER SYSTEM", None, None, None, None],
                        ["1", "Sprinkler", 10, "Nos", 300, 50],
                        ["2", "Pipe", 20, "Mtrs", 400, 60],
                        ["B", "HYDRANT SYSTEM", None, None, None, None],
                        again,
                        ["1", "Hydrant valve", 2, "Nos", 5000, 500]])
    assert g["header"] == [0, 0], "the FIRST heading wins"
    assert [(l["section"], l["item_no"]) for l in res["lines"]] == [
        ("A", "1"), ("A", "2"), ("B", "1")]
    assert res["counts"]["repeats"] == 1
    assert not [f for f in res["flags"] if f["row"] == 6]


# ═══ B. Amount-only rows ══════════════════════════════════════════════════════

def _foot(rows):
    return built([SIMPLE] + rows)[0]


def test_a_subtotal_that_adds_up_is_a_check_and_not_a_line():
    res = _foot([["1", "Pipe", 2, "Mtrs", 100, 200, 10, 20],
                 ["2", "Valve", 1, "Nos", 300, 300, 30, 30],
                 [None, None, None, None, None, 500, None, 50]])
    assert [l["item_no"] for l in res["lines"]] == ["1", "2"]
    (c,) = res["checks"]
    assert (c["row"], c["kind"], c["status"]) == (4, "subtotal", "match")


def test_a_labelled_subtotal_that_does_not_add_up_is_flagged_with_both_figures():
    res = _foot([["1", "Pipe", 2, "Mtrs", 100, 200, None, None],
                 [None, "Sub Total", None, None, None, 260, None, None]])
    assert [l["item_no"] for l in res["lines"]] == ["1"]
    (c,) = res["checks"]
    assert c["status"] == "mismatch"
    assert c["figures"] == [{"col": "supply_amount", "sheet": 260.0, "lines": 200.0}]
    (f,) = [f for f in res["flags"] if f["kind"] == "total_bad"]
    assert "260" in f["message"] and "200" in f["message"] and f["severity"] == "amber"
    assert not res["needs"], "a total that does not foot asks for a look, not a figure"


def test_a_section_total_is_the_sum_of_its_subtotals():
    res = _foot([["1", "Pipe", 2, "Mtrs", 100, 200, None, None],
                 [None, None, None, None, None, 200, None, None],
                 ["2", "Valve", 1, "Nos", 300, 300, None, None],
                 [None, None, None, None, None, 300, None, None],
                 [None, None, None, None, None, 500, None, None]])
    assert [c["kind"] for c in res["checks"]] == ["subtotal", "subtotal", "section total"]
    assert all(c["status"] == "match" for c in res["checks"])
    assert [l["item_no"] for l in res["lines"]] == ["1", "2"]


def test_a_grand_total_and_a_combined_total_are_recognised():
    """Rows 124 and 125 of the Jamnagar sheet: "A+B+C" with no brackets, and
    supply + installation together in the installation column."""
    res = _foot([["A", "PUMPS", None, None, None, None, None, None],
                 ["1", "Pump", 1, "Set", 7000, 7000, 2500, 2500],
                 [None, "TOTAL AMOUNT (A) Rs.", None, None, None, 7000, None, 2500],
                 [None, "TOTAL AMOUNT   A+B+C", None, None, None, 7000, None, 2500],
                 [None, "Total", None, None, None, None, None, 9500]])
    assert [(c["row"], c["kind"], c["status"]) for c in res["checks"]] == [
        (4, "subtotal", "match"), (5, "grand total", "match"), (6, "combined total", "match")]
    assert res["totals"]["status"] == "match" and res["totals"]["row"] == 5
    assert [l["item_no"] for l in res["lines"]] == ["1"]


def test_an_amount_alone_that_is_no_total_is_a_lump_sum():
    res = _foot([["1", "Pipe", 2, "Mtrs", 100, 200, None, None],
                 [None, None, None, None, None, 200, None, None],
                 [None, "Testing and commissioning", None, None, None, 15000, None, None]])
    ls = by_row(res, 4)
    assert ls["lump_sum"] and (ls["qty"], ls["unit"], ls["supply_rate"]) == (1.0, "LS", 15000.0)
    assert ls["install_rate"] is None
    assert ls["item_no"] == "1.a" and ls["item_src"] == "auto", "labelled per section A"
    assert [f["kind"] for f in flags_on(res, 4)] == ["lump_sum"]
    assert flags_on(res, 4)[0]["severity"] == "amber" and not ls["needs"]
    assert res["counts"]["lump_sums"] == 1
    model = boqimport.editor_model(res)
    row = next(l for l in model["lines"] if l["item_no"] == "1.a")
    assert row["_ls"] is True and row["total_qty"] == "1" and row["supply_rate"] == "15000"


def test_a_lump_sum_lands_in_the_track_of_its_amount_column():
    res = _foot([["5", "Scaffolding", None, None, None, None, None, 8000]])
    ls = by_row(res, 2)
    assert (ls["supply_rate"], ls["install_rate"], ls["item_no"]) == (None, 8000.0, "5")


def test_a_zero_amount_is_no_amount():
    """The Jamnagar spec rows carry 0 in both amount cells: never a ₹0 lump
    sum, never a subtotal — they fall through to the structure rules."""
    res = _foot([["6", "TEST & DRAIN VALVE", None, None, None, 0, None, 0],
                 [None, "Providing and fixing test and drain valve", None, None, None, 0, None, 0],
                 [None, "50 mm", 2, "Nos", 5400, 10800, 500, 1000]])
    assert [(l["kind"], l["item_no"]) for l in res["lines"]] == [
        ("header", "6"), ("spec_text", ""), ("sub_item", "6.a")]
    assert not res["checks"] and not res["counts"]["lump_sums"]


# ═══ C. The real flags ════════════════════════════════════════════════════════

def test_qty_times_rate_off_the_amount_leaves_the_rate_blank_and_says_both():
    res = _foot([["1", "Pipe", 10, "Mtrs", 100, 1200, 50, 500]])
    ln = by_row(res, 2)
    assert ln["supply_rate"] is None, "never guessed: which of the two is wrong is not ours to say"
    assert ln["install_rate"] == 50.0
    (n,) = ln["needs"]
    assert n["field"] == "supply_rate"
    assert "10 × rate 100 = 1,000" in n["message"] and "1,200" in n["message"]


def test_within_a_rupee_is_not_a_mismatch():
    res = _foot([["1", "Pipe", 3, "Mtrs", 100.25, 300.75 + 0.9, None, None]])
    assert not res["needs"]


def test_a_priced_line_with_no_quantity_needs_one():
    res = _foot([["1", "Pipe", None, "Mtrs", 100, 1000, None, None]])
    assert [n["field"] for n in by_row(res, 2)["needs"]] == ["total_qty"]


def test_an_amount_with_no_rate_needs_the_rate_of_that_track():
    res = _foot([["1", "Pipe", 10, "Mtrs", 100, 1000, None, 700]])
    assert [n["field"] for n in by_row(res, 2)["needs"]] == ["install_rate"]


def test_an_explicit_zero_amount_is_a_nil_priced_line_and_is_not_asked_about():
    res = _foot([["1", "Pipe", 10, "Mtrs", None, 0, None, 0]])
    assert not by_row(res, 2)["needs"]


def test_unit_handling_is_unchanged():
    res = _foot([["1", "Pipe", 2, " Mtrs. ", 100, 200, None, None]])
    assert by_row(res, 2)["unit"] == "Mtrs."


# ═══ D. The preview ═══════════════════════════════════════════════════════════

def upload(client, data: bytes):
    return client.post("/boq/import", data={"workbook": (io.BytesIO(data), "j.xlsx")},
                       content_type="multipart/form-data")


def token_of(resp) -> str:
    return resp.headers["Location"].split("/boq/import/")[1].split("/")[0].split("#")[0]


def test_the_preview_groups_what_it_found(client):
    tok = token_of(upload(client, xlsx(TOP + HEAD2 + ROWS_5_17)))
    body = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "What each column holds" in body
    assert "<b>1</b> field needs you" in body
    assert "<b>6</b> item numbers filled in from the sheet&rsquo;s structure" in body
    assert "<b>0</b> lump sums" in body
    assert "subtotals checked" in body or "subtotal checked" in body
    assert "flagged cell" not in body, "the per-row dump is gone"
    assert 'value="confirm@5.rate"' in body


def test_a_summary_link_confirms_and_lands_on_the_field(client):
    tok = token_of(upload(client, xlsx(TOP + HEAD2 + ROWS_5_17)))
    m = dict(STORE["boq_imports"][tok]["mapping"])
    form = {f"map_{c}": t for c, t in m.items()}
    form.update(action="confirm@5.rate", sheet="0")
    r = client.post(f"/boq/import/{tok}", data=form)
    assert r.status_code == 303
    assert r.headers["Location"].endswith(f"/boq/import/{tok}/form#need-5-rate")


def test_a_malformed_goto_is_ignored(client):
    tok = token_of(upload(client, xlsx(TOP + HEAD2 + ROWS_5_17)))
    m = dict(STORE["boq_imports"][tok]["mapping"])
    form = {f"map_{c}": t for c, t in m.items()}
    form.update(action='confirm@5.rate"><script>', sheet="0")
    r = client.post(f"/boq/import/{tok}", data=form)
    assert r.headers["Location"].endswith(f"/boq/import/{tok}/form")


# ═══ E. The prefilled form ════════════════════════════════════════════════════

def model_of(html: str) -> dict:
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", html, re.S)
    assert m, "the page carries no editor model"
    return json.loads(m.group(1))


def open_form(client, rows):
    r = upload(client, xlsx(rows))
    tok = token_of(r)
    m = dict(STORE["boq_imports"][tok]["mapping"])
    form = {f"map_{c}": t for c, t in m.items()}
    form.update(action="confirm", sheet="0")
    r = client.post(f"/boq/import/{tok}", data=form)
    return client.get(r.headers["Location"]).get_data(as_text=True)


BLOCKING = TOP + HEAD2 + ROWS_5_17 + [
    [None, "65 mm NB", None, None, 1000, 5000, None, None],      # no quantity
    [None, "50 mm NB", None, 10, 100, 1200, None, None],         # qty × rate ≠ amount
]


def bar_count(html: str) -> int:
    return int(re.search(r'id="needs-bar" class="needs-bar[^"]*" data-count="(\d+)"', html).group(1))


def test_the_prefilled_page_carries_one_marker_per_blocking_flag(client):
    res, _g, _m = built(BLOCKING)
    assert len(res["needs"]) == 3
    body = open_form(client, BLOCKING)
    model = model_of(body)
    assert sum(len(l.get("_needs") or []) for l in model["lines"]) == 3
    assert sum(len(l.get("_need") or []) for l in model["lines"]) == 3
    assert bar_count(body) == 3
    assert "<b>3</b> fields need you" in body


def test_auto_chips_ride_on_the_model(client):
    body = open_form(client, TOP + HEAD2 + ROWS_5_17)
    model = model_of(body)
    assert [l["item_no"] for l in model["lines"] if l.get("_item_src") == "auto"] == [
        "1.a", "1.b", "1.c", "2.a", "3.a", "3.b"]
    assert 'var BOQ_GUIDE = {"imported": true, "refused": false};' in body


def _post(client, model, **over):
    form = {"date": "2026-09-30", "project_name": "Jamnagar", "account_name": "Prudent",
            "rev_no": "0", "boq_json": json.dumps(model)}
    form.update(over)
    return client.post("/boq/create", data=form)


def test_a_refused_post_re_renders_with_the_same_markers(client):
    model = model_of(open_form(client, BLOCKING))
    r = _post(client, model, project_name="")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    again = model_of(body)
    assert sum(len(l.get("_needs") or []) for l in again["lines"]) == 3
    # …and the header field this save refused is marked by the SERVER.
    assert 'data-needs-form="project_name" data-needs="project_name" class="needs"' in body
    assert bar_count(body) == 4
    assert '"refused": true' in body


def test_the_markers_follow_the_posted_values(client):
    model = model_of(open_form(client, BLOCKING))
    for l in model["lines"]:
        if any(n["f"] == "rate" for n in l.get("_need") or []):
            l["install_rate"] = "75"                  # one filled in, two left
    r = _post(client, model, account_name="")
    again = model_of(r.get_data(as_text=True))
    assert sum(len(l.get("_needs") or []) for l in again["lines"]) == 2


def test_an_ordinary_validation_failure_is_marked_too(client):
    """A typed form, no import anywhere: the line the save refused is ringed."""
    model = {"sections": [{"code": "A", "title": "", "areas": []}],
             "lines": [{"item_no": "", "description": "Pipe", "section": "A",
                        "total_qty": "2", "supply_rate": "10", "supply_hsn": "12"},
                       {"item_no": "2", "description": "", "section": "A",
                        "total_qty": "1", "supply_rate": "5"}]}
    r = _post(client, model)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    again = model_of(body)
    assert again["lines"][0]["_needs"] == ["item_no", "supply_hsn"]
    assert again["lines"][1]["_needs"] == ["description"]
    assert bar_count(body) == 3


def test_the_server_still_accepts_what_it_always_did(client):
    """GUIDANCE ONLY. A POST that ignores the rings is saved exactly as before
    — a blank quantity as 0, ABOUT.md §7 gap 42, deliberately left open."""
    model = model_of(open_form(client, BLOCKING))
    before = set(STORE["boqs"])
    r = _post(client, model)
    assert r.status_code == 302
    (bid,) = set(STORE["boqs"]) - before
    items = STORE["boqs"][bid]["line_items"]
    assert not any(k.startswith("_") for l in items for k in l)
    blank = next(l for l in items if l["description"] == "65 mm NB")
    assert blank["total_qty"] == 0.0


def test_the_plain_form_has_a_hidden_bar_and_no_marks(client):
    body = client.get("/boq/create").get_data(as_text=True)
    assert '<div id="needs-bar" class="needs-bar" data-count="0" style="display:none;"></div>' in body
    assert "data-needs=" not in body.split("var MODEL")[0]


def test_the_pulse_stops_under_reduced_motion(client):
    body = client.get("/boq/create").get_data(as_text=True)
    assert "@media (prefers-reduced-motion: reduce) { .needs { animation:none; } }" in body
    assert ".has-needs::after { content:\"!\"" in body
    assert "var(--brand)" in body


def test_python_and_js_agree_on_what_meets_a_need():
    """`_need_met()` and `line_problems()` against the page's `needMet()` and
    `errMet()`, over the cases that differ: blank, 0, "-", text, negative, a
    header, an area section, a bad HSN."""
    if NODE is None:
        pytest.skip("node not installed")
    sections = [{"code": "A", "title": "", "areas": []}, {"code": "B", "title": "", "areas": ["L0"]}]
    cases = [
        {"section": "A", "total_qty": ""}, {"section": "A", "total_qty": "0"},
        {"section": "A", "total_qty": "-"}, {"section": "A", "total_qty": "2"},
        {"section": "A", "total_qty": "abc"}, {"section": "A", "total_qty": "-3"},
        {"section": "A", "is_header": True, "total_qty": ""},
        {"section": "B", "area_qty": {"L0": "4"}}, {"section": "B", "area_qty": {}},
        {"section": "A", "supply_rate": "5", "install_rate": ""},
        {"section": "A", "supply_rate": "", "install_rate": "0"},
        {"section": "A", "supply_rate": "-1"},
        {"section": "Z", "item_no": "1", "description": "x"},
        {"section": "A", "item_no": " ", "description": "x", "supply_hsn": "1234x"},
        {"section": "A", "item_no": "1", "description": "x", "install_sac": "995461"},
    ]
    fields = ["total_qty", "supply_rate", "install_rate", "rate", "item_no", "description"]
    by_code = {s["code"]: s for s in sections}
    py = []
    for c in cases:
        areas = by_code.get(c["section"], {}).get("areas") or []
        py.append({"need": [boq._need_met(c, f, areas) for f in fields],
                   "err": sorted(boq.line_problems(c, by_code))})
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = (js.replace("BOQ_BOOT", json.dumps({"sections": sections, "lines": []}))
            .replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}"))
    stub = ("var STUB = {}; ['bulk-spec','bulk-section','line-editor','sec-editor','boq_json']"
            ".forEach(function(k){ STUB[k] = {value:'', innerHTML:''}; });\n"
            "var document = { getElementById: function(id) { return STUB[id] || null; } };\n")
    script = ("var CASES = " + json.dumps(cases) + "; var F = " + json.dumps(fields) + ";\n"
              "var ALL = ['section','item_no','description','total_qty','supply_rate',"
              "'install_rate','supply_hsn','install_sac'];\n"
              "console.log(JSON.stringify(CASES.map(function (c) {\n"
              "  return {need: F.map(function (f) { return needMet(c, f); }),\n"
              "          err: ALL.filter(function (f) { return !errMet(c, f); }).sort()};\n"
              "})));")
    out = subprocess.run([NODE], input=stub + js + "\n" + script, capture_output=True,
                         text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == py


# ═══ E. The editor's JavaScript, under Node ═══════════════════════════════════

_DOM = r"""
var FOCUSED = null, SCROLLED = null;
function Elem(id) {
  this.id = id; this.value = ''; this.innerHTML = ''; this.style = {};
  this.attrs = {}; this.cls = {};
  var self = this;
  this.classList = { add: function (c) { self.cls[c] = 1; },
                     remove: function (c) { delete self.cls[c]; },
                     contains: function (c) { return !!self.cls[c]; } };
  this.parentNode = { classList: { add: function () {}, remove: function () {} } };
}
Elem.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
Elem.prototype.getAttribute = function (k) { return this.attrs[k]; };
Elem.prototype.removeAttribute = function (k) { delete this.attrs[k]; };
Elem.prototype.scrollIntoView = function (o) { SCROLLED = this.id + ':' + o.block; };
Elem.prototype.focus = function () { FOCUSED = this.id; };
var STUB = {};
['bulk-spec','bulk-section','line-editor','sec-editor','boq_json','import-block',
 'dup-warn','zeroqty-hint','jump-bar','needs-bar'].forEach(function (k) { STUB[k] = new Elem(k); });
var LF = {};
var document = {
  getElementById: function (id) { return STUB[id] || null; },
  querySelectorAll: function () { return []; },
  querySelector: function (sel) {
    var m = /data-lf="([^"]+)"/.exec(sel);
    if (!m) return null;
    if (STUB['line-editor'].innerHTML.indexOf('data-lf="' + m[1] + '"') < 0) return null;
    return LF[m[1]] || (LF[m[1]] = new Elem(m[1]));
  }
};
"""


def _node(boot: dict, script: str, guide=None):
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = (js.replace("BOQ_BOOT", json.dumps(boot))
            .replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}"))
    pre = _DOM + ("var BOQ_GUIDE = " + json.dumps(guide) + ";\n" if guide else "")
    out = subprocess.run([NODE], input=pre + js + "\n" + script, capture_output=True,
                         text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _boot(rows):
    res, _g, _m = built(rows)
    model = boqimport.editor_model(res)
    boq.annotate_needs(model["lines"], model["sections"], with_errors=False)
    return res, model


@needs_node
def test_the_rendered_editor_carries_exactly_one_mark_per_blocking_flag():
    res, model = _boot(BLOCKING)
    got = _node(model, """
      var h = STUB['line-editor'].innerHTML;
      console.log(JSON.stringify({marks: (h.match(/data-needs="/g) || []).length,
                                  badges: (h.match(/has-needs/g) || []).length,
                                  autos: (h.match(/class="chip-auto"/g) || []).length,
                                  bar: STUB['needs-bar'].innerHTML}));
    """)
    assert got["marks"] == len(res["needs"]) == 3
    assert got["badges"] == 3
    assert got["autos"] >= 6
    assert "<b>3</b> fields need you" in got["bar"] and "Next" in got["bar"] and "Prev" in got["bar"]


@needs_node
def test_on_load_an_import_goes_to_the_first_field_and_next_wraps():
    _res, model = _boot(BLOCKING)
    got = _node(model, """
      var first = [FOCUSED, SCROLLED];
      goNeed(1); var second = FOCUSED;
      goNeed(1); var third = FOCUSED;
      goNeed(1); var wrapped = FOCUSED;
      goNeed(-1); var back = FOCUSED;
      console.log(JSON.stringify({first: first, second: second, third: third,
                                  wrapped: wrapped, back: back}));
    """, guide={"imported": True})
    lines = model["lines"]
    idx = [i for i, l in enumerate(lines) if l.get("_need")]
    want = []
    for i in idx:
        for n in lines[i]["_need"]:
            want.append(f"{i}:{'supply_rate' if n['f'] == 'rate' else n['f']}")
    assert got["first"] == [want[0], want[0] + ":center"]
    assert [got["second"], got["third"], got["wrapped"], got["back"]] == [
        want[1], want[2], want[0], want[2]]


@needs_node
def test_a_valid_value_clears_the_mark_and_clearing_it_brings_it_back():
    """
    ⚠ **A typed 0 now ANSWERS a rate flag (30 September 2026)** — the owner's
    brief: the client's sheets leave lines unpriced on purpose. Until then this
    test held `zero == 1`, the old "a number greater than 0" rule. Only a blank
    still asks; tests/test_boq_child_context.py holds the rest of the rule.
    """
    _res, model = _boot(TOP + HEAD2 + ROWS_5_17)
    i = next(k for k, l in enumerate(model["lines"]) if l.get("_need"))
    got = _node(model, f"""
      var before = needList().length;
      setLine({i}, 'install_rate', '0');   var zero = needList().length;
      setLine({i}, 'install_rate', '');    var blank = needList().length;
      setLine({i}, 'install_rate', '75');  var filled = needList().length;
      var bar = STUB['needs-bar'].innerHTML;
      var lf = LF['{i}:supply_rate'];
      var cleared = lf && !lf.attrs['data-needs'];
      setLine({i}, 'install_rate', '');    var again = needList().length;
      var back = lf && lf.attrs['data-needs'];
      console.log(JSON.stringify({{before: before, zero: zero, blank: blank, filled: filled,
                                  bar: bar, cleared: cleared, again: again, back: back}}));
    """)
    assert (got["before"], got["zero"], got["blank"], got["filled"], got["again"]) == (1, 0, 1, 0, 1)
    assert "All filled" in got["bar"] and "review and save" in got["bar"]
    assert got["cleared"] is True and got["back"] == "rate"


@needs_node
def test_save_is_stopped_in_the_browser_and_jumps_to_the_first_field():
    _res, model = _boot(BLOCKING)
    got = _node(model, """
      FOCUSED = null;
      var ok = saveJSON();
      console.log(JSON.stringify({ok: ok, posted: STUB['boq_json'].value, focused: FOCUSED}));
    """)
    assert got["ok"] is False and got["posted"] == "" and got["focused"]


@needs_node
def test_the_suggested_child_number_follows_the_letter_convention():
    boot = {"sections": [{"code": "A", "title": "", "areas": []}],
            "lines": [{"item_no": "24", "parent_item_no": "", "section": "A", "is_header": True,
                       "description": "Clause", "area_qty": {}},
                      {"item_no": "24.a", "parent_item_no": "24", "section": "A",
                       "description": "x", "area_qty": {}},
                      {"item_no": "24.b", "parent_item_no": "24", "section": "A",
                       "description": "y", "area_qty": {}},
                      {"item_no": "", "parent_item_no": "24", "section": "A",
                       "description": "z", "area_qty": {}},
                      {"item_no": "", "parent_item_no": "", "section": "A",
                       "description": "w", "area_qty": {}}]}
    got = _node(boot, """
      console.log(JSON.stringify([itemPlaceholder(3), itemPlaceholder(4), subLabel(26)]));
    """)
    assert got == ["24.c", "4.a", "aa"]
