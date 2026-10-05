"""
tests/test_wo_nxtra.py — the client's own work-order sheet (5 October 2026)
==========================================================================
CLIENT_CHANGES.md §0, forty-third block — Work Orders pass 3, rulings R1 to R7.

Two halves:

* **SYNTHETIC** — always run. Each shape the client's sheet showed, built with
  `sheetimport.from_rows()` and so needing no workbook reader and no file:
  the two-row "Installation / Unit Rate" header with floor labels beside it,
  the "INR" units row, a labour-only sheet, quantity-0 rows with and without
  a rate, and two tabs with their columns in different places.
* **NXTRA ACCEPTANCE** — the real file, `fixtures/work_order_nxtra.xlsx`, which
  is GITIGNORED and never committed (the `sify_boq.xlsx` convention): every
  test that reads it SKIPS where it is absent. Upload it, tick Sprinkler and
  Wet Spray System, accept the guessed mapping with no manual change, confirm,
  and the figures on the client's own cover sheet come out.
"""

import html as H
import io
import pathlib
import re

import pytest

import auth
import sheetimport as SI
import workorder as W
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
NXTRA = REPO / "fixtures" / "work_order_nxtra.xlsx"


@pytest.fixture(autouse=True)
def _clean():
    STORE.setdefault("work_orders", {}).clear()
    STORE.setdefault("wo_imports", {}).clear()
    yield
    STORE["work_orders"].clear()
    STORE["wo_imports"].clear()


def _body(html):
    start = html.index('<tbody id="wo-lines-body">')
    return html[start:html.index("</tbody>", start)]


def _rows(html):
    """The form's line rows as dicts of their posted values, in order."""
    out = []
    for tr in _body(html).split('<tr class="wo-ln')[1:]:
        r = {"header": tr.startswith(" wo-hd")}
        for name in ("ln_id", "ln_note", "ln_hdr", "ln_sec", "ln_item", "ln_unit",
                     "ln_qty", "ln_mrate", "ln_lrate"):
            m = re.search(rf'name="{name}" value="([^"]*)"', tr)
            r[name] = H.unescape(m.group(1)) if m else None
        m = re.search(r'<textarea name="ln_desc"[^>]*>(.*?)</textarea>', tr, re.S)
        r["ln_desc"] = H.unescape(m.group(1)) if m else ""
        r["need"] = tr.count('class="wo-need"')
        out.append(r)
    return out


def _form_back(html, **extra):
    """The rendered form posted back exactly as it stands — no edit at all."""
    rows = _rows(html)
    data = {"date": "2026-10-05", "contractor_name": "Tej Infratech Solutions"}
    tr = re.search(r'id="tracks" name="tracks">(.*?)</select>', html, re.S).group(1)
    data["tracks"] = re.search(r'<option value="(\w+)" selected>', tr).group(1)
    data["gst_rate"] = H.unescape(re.search(r'name="gst_rate"[^>]*value="([^"]*)"', html).group(1))
    data["terms"] = H.unescape(re.search(r'<textarea id="terms" name="terms"[^>]*>(.*?)</textarea>',
                                         html, re.S).group(1))
    for name in ("ln_id", "ln_note", "ln_hdr", "ln_sec", "ln_item", "ln_unit",
                 "ln_qty", "ln_mrate", "ln_lrate", "ln_desc"):
        vals = [r[name] for r in rows]
        if all(v is None for v in vals):
            continue
        data[name] = ["" if v is None else v for v in vals]
    data.update(extra)
    return data


def _preview_confirm(client, tok, tabs):
    """Show the ticked tabs, then confirm with every guessed select AS RENDERED."""
    page = client.post(f"/wo/import/{tok}", data={"tab": [str(t) for t in tabs],
                                                  "act": "tabs"}).get_data(as_text=True)
    form = {"tab": [str(t) for t in tabs], "act": "confirm"}
    for name, opts in re.findall(r'<select name="(map_\d+_\d+)"[^>]*>(.*?)</select>', page, re.S):
        m = re.search(r'<option value="([^"]*)" selected>', opts)
        form[name] = m.group(1) if m else ""
    return page, client.post(f"/wo/import/{tok}", data=form)


def _stage(rows_by_tab, uid=None):
    from conftest import ensure_test_user
    wb = SI.from_rows([(name, "visible", rows) for name, rows in rows_by_tab])
    return wb, W.stage(wb, "synthetic.xlsx", uid or ensure_test_user()["id"])


# ══ SYNTHETIC — R2, the header band (the SHARED reader) ══════════════════════

TWO_ROW = [
    ["Sr. No.", "Description", "DC building", None, None, "Total Quantity", "Unit", "Installation"],
    [None, None, "GF", "1F", "Terrace", None, None, "Unit Rate (INR)"],
    ["1", "Pipe laying", 10, 5, 1, 16, "Mtr", 100],
    ["2", "Valve fixing", 2, None, None, 2, "Nos", 450],
]


def test_a_rate_row_under_installation_joins_the_band_and_names_the_track():
    """R2a: "Installation" over "Unit Rate (INR)", floor labels beside it."""
    g = SI.from_rows([("S", "visible", TWO_ROW)])["grid"][0]
    assert g["header"] == [0, 1]
    labels = SI.header_labels(g)
    assert labels[2] == "DC building GF" and labels[4] == "DC building Terrace"
    assert SI.guess_mapping(g)["7"] == "install_rate"          # the BOQ importer
    assert W.guess_mapping(g)["7"] == "labour_rate"            # the work order's
    assert SI.data_start(g) == 2


def test_without_a_rate_label_the_floor_row_is_still_refused_as_a_header():
    """The control: R2a is about a RATE label under a heading, nothing wider —
    a floor row with no rate label in it stays out of the band, as before."""
    rows = [r[:] for r in TWO_ROW]
    rows[1][7] = None
    g = SI.from_rows([("S", "visible", rows)])["grid"][0]
    assert g["header"] == [0, 0]


INR = [
    ["Sr. No.", "Description", "Total Quantity", "Unit", "Installation", None],
    [None, None, None, None, "Unit Rate", "Total cost"],
    [None, None, None, None, "INR", "INR"],
    ["1", "Pipe laying", 50, "Mtr", 540, 27000],
]


def test_a_units_row_under_the_band_joins_it_and_is_not_a_line():
    """R2b: "INR | INR" under "Unit Rate | Total cost"."""
    g = SI.from_rows([("S", "visible", INR)])["grid"][0]
    assert g["header"] == [0, 2]
    assert SI.header_labels(g)[4] == "Installation Unit Rate"
    m = SI.guess_mapping(g)
    assert (m["4"], m["5"]) == ("install_rate", "install_amount")
    result = SI.build(g, m)
    assert [l["row"] for l in result["lines"]] == [4]          # the INR row is no line
    assert result["needs"] == []


@pytest.mark.parametrize("token", ["INR", "Rs", "Rs.", "₹", "(INR)", "Nos", "%", " inr "])
def test_every_unit_token_makes_a_units_row(token):
    rows = [r[:] for r in INR]
    rows[2] = [None, None, None, None, token, None]
    g = SI.from_rows([("S", "visible", rows)])["grid"][0]
    assert g["header"] == [0, 2]


def test_a_row_with_a_word_beside_the_unit_token_is_not_a_units_row():
    rows = [r[:] for r in INR]
    rows[2] = [None, "Pipe", None, None, "INR", "INR"]
    g = SI.from_rows([("S", "visible", rows)])["grid"][0]
    assert g["header"] == [0, 1]


# ══ SYNTHETIC — R1, R3: a labour-only sheet, quantity-0 rows ═════════════════

LABOUR_ONLY = [
    ["Sr. No.", "Description", "Qty", "Unit", "Installation", None],
    [None, None, None, None, "Unit Rate", "Total cost"],
    ["A", "SPRINKLER SYSTEM", None, None, None, None],
    ["1", "Pipes", None, None, None, None],
    ["a", "150 mm", 0, "Mtr", 1080, 0],            # qty 0 WITH a rate: rate-only
    ["b", "100 mm", 50, "Mtr", 720, 36000],
    ["c", "80 mm", 0, "Mtr", 0, 0],                # qty 0, no rate: left out
    ["2", "Valves", None, None, None, None],
    ["a", "150 mm", 0, "Nos", 0, 0],               # every child left out ...
    ["b", "100 mm", 0, "Nos", 0, 0],               # ... so heading 2 goes too
    ["3", "Hangers", 4, "Nos", 450, 1800],
]


def test_a_labour_only_sheet_imports_labour_only_with_nothing_to_answer(client):
    _wb, tok = _stage([("Sprinkler", LABOUR_ONLY)])
    _page, r = _preview_confirm(client, tok, [0])
    html = r.get_data(as_text=True)
    assert '<option value="labour" selected>' in html
    assert 'name="ln_mrate"' not in html
    rows = _rows(html)
    assert sum(r_["need"] for r_ in rows) == 0
    assert [(r_["ln_item"], r_["ln_hdr"]) for r_ in rows] == [
        ("A", "1"), ("1", "1"), ("a", "0"), ("b", "0"), ("3", "0")]
    assert rows[0]["ln_sec"] == "1"                            # the sheet's section


def test_qty_zero_rows_are_left_out_or_kept_as_rate_only_and_listed(client):
    _wb, tok = _stage([("Sprinkler", LABOUR_ONLY)])
    page, r = _preview_confirm(client, tok, [0])
    assert "4 rows left out" in page                           # said on the preview
    html = r.get_data(as_text=True)
    assert "4 rows left out" in html                           # and on the form
    assert "Sprinkler rows 7, 8, 9, 10" in html
    kept = {r_["ln_desc"]: r_ for r_ in _rows(html)}
    assert kept["150 mm"]["ln_qty"] == "0" and kept["150 mm"]["ln_lrate"] == "1080"
    assert "rate only — quantity 0 on the sheet" in kept["150 mm"]["ln_note"]
    assert "80 mm" not in kept and "Valves" not in kept        # no orphan heading


def test_a_blank_quantity_is_not_zero_and_is_never_left_out(client):
    rows = [r[:] for r in LABOUR_ONLY]
    rows[6] = ["c", "80 mm", None, "Mtr", 540, None]
    _wb, tok = _stage([("Sprinkler", rows)])
    _page, r = _preview_confirm(client, tok, [0])
    by = {r_["ln_desc"]: r_ for r_ in _rows(r.get_data(as_text=True))}
    assert by["80 mm"]["ln_qty"] == "" and by["80 mm"]["need"] >= 1
    # Nor is it called a rate-only line: that note means a 0 on the sheet.
    assert "rate only" not in by["80 mm"]["ln_note"]


def _hd(item, text, row, sec="A", parent="", section=False):
    h = {"is_header": True, "item_no": item, "description": text, "_row": row,
         "_parent": parent, "_sec": sec, "qty": "", "labour_rate": "", "note": ""}
    if section:
        h["section"] = True
    return h


def _ln(item, text, row, qty, rate, parent="", sec="A"):
    return {"is_header": False, "item_no": item, "description": text, "_row": row,
            "_parent": parent, "_sec": sec, "qty": qty, "labour_rate": rate, "note": ""}


def test_a_heading_keeps_only_its_own_children_and_an_orphan_goes():
    """
    The three shapes the client's sheet showed (5 Oct 2026), straight into
    `_drop_qty0()`:

    * a heading's children are the rows the sheet puts under it — after it,
      and before the next heading carrying the SAME number: the contractor's
      own terms below the items are numbered 1, 2 again, and item 1's real
      children above them must not keep them;
    * a numbered heading followed by its sibling, not its child, is an orphan;
    * an UNNUMBERED heading may introduce numbered ones and stays while they
      do; with nothing under it before a section, it goes.
    """
    rows = [
        _hd("", "Design, installation and commissioning", 2, sec="B"),
        _hd("A", "SPRINKLER SYSTEM", None, section=True),
        _hd("", "Pipes and fittings", 4),
        _hd("1", "MS pipe", 5),
        _ln("a", "150 mm", 6, "10", "100", parent="1"),
        _ln("b", "100 mm", 7, "0", "0", parent="1"),
        _hd("2", "Valves", 8),
        _ln("a", "150 mm valve", 9, "0", "0", parent="2"),
        _ln("3", "Hangers", 10, "4", "450"),          # heading 2's SIBLING
        _hd("1", "All tools by the contractor", 12),  # their terms, numbered again
        _hd("2", "Material in customer scope", 13),
        _hd("B", "SPRAY SYSTEM", None, section=True),
        _ln("1", "Nozzle", 15, "0", "0"),            # every line gone: so is B
    ]
    left = []
    kept = W._drop_qty0(rows, "labour", "Sprinkler", left)
    assert [(r["item_no"], r["description"]) for r in kept] == [
        ("A", "SPRINKLER SYSTEM"), ("", "Pipes and fittings"), ("1", "MS pipe"),
        ("a", "150 mm"), ("3", "Hangers")]
    # Listed by sheet row; a section title has none to list.
    assert [row for _tab, row in left] == [2, 7, 8, 9, 12, 13, 15]


def test_the_bom_import_keeps_its_qty_zero_rows():
    """R3 is a WORK-ORDER rule: `sheetimport.build()` — the BOQ's reader — still
    returns every priced line, quantity 0 or not."""
    g = SI.from_rows([("S", "visible", LABOUR_ONLY)])["grid"][0]
    result = SI.build(g, SI.guess_mapping(g))
    assert [l["description"] for l in result["lines"] if not l["is_header"]] == [
        "150 mm", "100 mm", "80 mm", "150 mm", "100 mm", "Hangers"]


# ══ SYNTHETIC — R4, two tabs with their columns in different places ══════════

TAB_A = [["Sr. No.", "Description", "Floor 1", "Total Quantity", "Unit", "Labour Rate"],
         ["1", "Pipe laying", 4, 10, "Mtr", 100]]
TAB_B = [["Sr. No.", "Description", "Total Quantity", "Unit", "Labour Rate"],
         ["1", "Nozzle fixing", 3, "Nos", 50],
         ["2", "Testing", 1, "Lot", 2000]]


def test_two_tabs_are_mapped_per_tab_and_built_into_one_work_order(client):
    wb, tok = _stage([("Sprinkler", TAB_A), ("Spray", TAB_B)])
    rec = W.staged()[tok]
    assert rec["ticked"] == [wb["selected"]]                   # only the reader's pick
    assert W.guess_mapping(wb["grid"][0])["3"] == "qty"        # quantity in D ...
    assert W.guess_mapping(wb["grid"][1])["2"] == "qty"        # ... and in C
    page, r = _preview_confirm(client, tok, [0, 1])
    assert page.count('name="map_0_') == 6 and page.count('name="map_1_') == 5
    html = r.get_data(as_text=True)
    rows = _rows(html)
    assert [(r_["ln_desc"], r_["ln_sec"]) for r_ in rows] == [
        ("Sprinkler", "1"), ("Pipe laying", "0"),
        ("Spray", "1"), ("Nozzle fixing", "0"), ("Testing", "0")]
    assert r.status_code == 200 and client.post("/wo/create", data=_form_back(html)).status_code == 302
    (wo,) = STORE["work_orders"].values()
    groups = W.section_groups(wo)
    assert [(g["title"], g["grand"]) for g in groups] == [("Sprinkler", 1000.0),
                                                          ("Spray", 2150.0)]


def test_mapping_problems_are_named_per_tab(client):
    bad = [["Sr. No.", "Description", "Qty", "Rate"], ["1", "Work", 1, 5]]
    _wb, tok = _stage([("Sprinkler", TAB_A), ("Odd", bad)])
    _page, r = _preview_confirm(client, tok, [0, 1])
    html = r.get_data(as_text=True)
    assert "Odd: Column D looks like a rate but does not say which" in html
    assert 'id="wo-form"' not in html


def test_no_ticked_tab_is_refused(client):
    _wb, tok = _stage([("Sprinkler", TAB_A)])
    html = client.post(f"/wo/import/{tok}", data={"act": "confirm"}).get_data(as_text=True)
    assert "Tick at least one tab to import." in html


# ══ NXTRA ACCEPTANCE — the client's own file, skipped where it is absent ══════

needs_nxtra = pytest.mark.skipif(not NXTRA.exists(),
                                 reason="fixtures/work_order_nxtra.xlsx is gitignored and absent")


@needs_nxtra
def test_the_boq_importer_now_maps_the_sprinkler_rate_column():
    """R2's assertion on the real file: column N, "Installation" over "Unit
    Rate (INR)" with floor labels beside it, is the installation rate."""
    pytest.importorskip("openpyxl")
    wb = SI.read(NXTRA.read_bytes(), NXTRA.name)
    names = [s["name"] for s in wb["sheets"]]
    sprinkler = wb["grid"][names.index("Sprinkler")]
    n = sprinkler["cols"].index(13)                             # column N
    assert SI.header_labels(sprinkler)[n].startswith("Installation Unit Rate")
    assert SI.guess_mapping(sprinkler)["13"] == "install_rate"
    spray = wb["grid"][names.index("Wet Spray System")]
    assert spray["header"][1] - spray["header"][0] == 2        # the INR row joined


@needs_nxtra
def test_the_client_sheet_imports_with_nothing_to_answer_and_their_figures(client):
    pytest.importorskip("openpyxl")
    r = client.post("/wo/import", data={"workbook": (io.BytesIO(NXTRA.read_bytes()),
                                                     "work_order_nxtra.xlsx")},
                    content_type="multipart/form-data")
    tok = r.headers["Location"].rsplit("/", 1)[-1]
    names = [s["name"] for s in W.staged()[tok]["sheets"]]
    tabs = [names.index("Sprinkler"), names.index("Wet Spray System")]
    page, r = _preview_confirm(client, tok, tabs)
    html = r.get_data(as_text=True)

    # Zero fields to answer; Labour only; no material box rendered anywhere.
    rows = _rows(html)
    assert sum(r_["need"] for r_ in rows) == 0
    assert 'class="wo-need"' not in _body(html)
    assert '<option value="labour" selected>' in html
    assert 'name="ln_mrate"' not in html
    priced = [r_ for r_ in rows if r_["ln_hdr"] == "0"]
    assert len(priced) == 42                                    # 33 + 9
    assert sum(1 for r_ in priced if r_["ln_qty"] == "0") == 6  # the rate-only six
    assert "75 rows left out" in html                         # 38 + 37, measured

    # Posted back exactly as rendered: it saves.
    r = client.post("/wo/create", data=_form_back(html))
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (wid, wo), = STORE["work_orders"].items()
    assert wo["tracks"] == "labour" and wo["gst_rate"] == 18.0
    assert all("material_rate" not in l for l in wo["lines"])

    t = W.totals_of(wo)
    assert (t["grand"], t["gst"], t["total"]) == (352800.0, 63504.0, 416304.0)
    assert [(g["title"], g["grand"]) for g in W.section_groups(wo)] == [
        ("WATER SPRINKLER SYSTEM", 307080.0), ("WATER SPRAY SYSTEM", 45720.0)]

    printed = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    flat = re.sub(r"\s+", " ", printed)
    for label, amount in (("Subtotal - WATER SPRINKLER SYSTEM", "3,07,080.00"),
                          ("Subtotal - WATER SPRAY SYSTEM", "45,720.00"),
                          ("Total", "3,52,800.00"),
                          ("GST @ 18%", "63,504.00"),
                          ("Total (incl. GST)", "4,16,304.00")):
        assert re.search(rf'class="sum-lbl">{re.escape(label)}</td>.*?'
                         rf'<td class="c-total">{re.escape(amount)}</td> </tr>', flat), label
    assert "Four Lakh Sixteen Thousand Three Hundred Four" in printed
    assert "Labour only" in printed and "<th class=\"c-price\">Rate</th>" in printed
