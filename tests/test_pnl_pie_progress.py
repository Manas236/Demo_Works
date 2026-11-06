"""
THE COST PIE AND THE PROGRESS BARS — CLIENT_CHANGES.md §0's **sixty-ninth**
block, item 1 (6 November 2026). The spider is gone; these replace it.

* **The pie draws only the heads above zero**, each in the SAME colour as the
  waterfall's bar for that head; a thin slice (under `P_LABEL_MIN_PCT`) is
  named in the key only; no cost at all is *"No costs yet"*, never an empty
  circle.
* **Every figure is `pnl.py`'s.** `cost_split_of()` adds no figure: its
  amounts are `waterfall_of()`'s and its total is *Spent to date*.
* **The progress bars** are the spider's six steps, one row each; a step with
  no denominator is a dash and an empty bar, never 0%.

`tests/test_pnl_chart_layout.py` is the overlap proof, in a browser.
"""

import re

import pnl as PNL
import pnl_chart as PC
from store import STORE
from test_pnl_charts_oct28 import (  # noqa: F401 — `world` is a fixture
    PID, world, _boq, _ra, _po)


def _wo(amount):
    STORE["work_orders"]["w1"] = {
        "id": "w1", "ref": "SF/WO/26-27/0001", "project_id": PID,
        "status": "issued", "tracks": "both", "gst_rate": 18.0,
        "contractor_name": "K", "lines": [
            {"line_id": "cccccccccccc", "description": "Laying", "unit": "Nos",
             "qty": 1.0, "material_rate": 0.0, "labour_rate": amount}]}


def _charge(amount):
    STORE["charges"]["c1"] = {
        "id": "c1", "date": "2026-10-02", "person": "R", "head": "Travel",
        "description": "x", "project_id": PID, "taxable_amount": amount,
        "gst_amount": 0.0, "created_at": "2026-10-02 10:00"}


def test_the_split_is_pnls_own_figures_and_adds_none(world):
    _boq(); _ra(); _po(taxable=6000.0); _charge(2000.0)
    r = PNL.project_pnl(PID)
    split = PNL.cost_split_of(r)
    assert split["total"] is r["to_date"]["actual"]
    steps = {k: v for k, _l, v in PNL.waterfall_of(r)["steps"]}
    for s in split["slices"]:
        assert s["amount"] == steps[s["key"]]
    assert [s["key"] for s in split["slices"]] == ["po", "charges"]
    assert [s["pct"] for s in split["slices"]] == [75.0, 25.0]
    assert abs(sum(s["share"] for s in split["slices"]) - 1.0) < 1e-12


def test_only_heads_above_zero_get_a_slice_and_a_nil_one_is_still_said(world):
    _boq(); _ra(); _po(taxable=6000.0)
    split = PNL.cost_split_of(PNL.project_pnl(PID))
    assert [s["key"] for s in split["slices"]] == ["po"]
    assert ("wo", "Work orders") in split["nil"]
    html = PC.cost_pie_html(split)
    assert html.count("<path") == 0 and html.count("<circle") == 1, \
        "one head is a whole circle, not a 360-degree arc"
    assert "Work orders" in html and "no slice" in html


def test_the_pie_wears_the_waterfalls_colour_for_each_head(world):
    _boq(); _ra(claim=50000.0); _po(taxable=6000.0); _wo(3000.0); _charge(2000.0)
    r = PNL.project_pnl(PID)
    wf = PC.waterfall_html(PNL.waterfall_of(r))
    pie = PC.cost_pie_html(PNL.cost_split_of(r))
    bar_fill = dict(re.findall(r"<title>([^:<]+): [^<]*</title><rect[^>]*"
                               r'fill="(#[0-9A-Fa-f]{6})"', wf))
    slice_fill = dict(re.findall(r"<title>([^:<]+): [^<]*</title><path[^>]*"
                                 r'fill="(#[0-9A-Fa-f]{6})"', pie))
    assert set(slice_fill) == {"Purchase orders", "Work orders", "Charges"}
    for head, colour in slice_fill.items():
        assert bar_fill[head] == colour, head


def test_no_cost_is_said_and_no_circle_is_drawn(world):
    _boq(); _ra()
    html = PC.cost_pie_html(PNL.cost_split_of(PNL.project_pnl(PID)))
    assert "No costs yet" in html
    assert "<svg" not in html and "<circle" not in html
    assert "The same figures, as text" in html


def test_a_thin_slice_is_named_in_the_key_and_not_on_the_picture(world):
    _boq(); _ra(claim=500000.0); _po(taxable=200000.0); _charge(500.0)
    html = PC.cost_pie_html(PNL.cost_split_of(PNL.project_pnl(PID)))
    svg, rest = html.split("</svg>", 1)
    assert "Charges" not in re.sub(r"<title>.*?</title>", "", svg), \
        "0.25% gets no label on the slice"
    assert "Charges" in rest.split("</ul>", 1)[0], "…the key names it"
    assert "500" in rest.split("</ul>", 1)[0]
    assert "Purchase orders" in re.sub(r"<title>.*?</title>", "", svg)


def test_a_label_carries_head_amount_and_share(world):
    _boq(); _ra(claim=5000000.0); _po(taxable=2160000.0); _charge(540000.0)
    html = PC.cost_pie_html(PNL.cost_split_of(PNL.project_pnl(PID)))
    svg = html.split("</svg>", 1)[0]
    assert "Purchase orders" in svg and "21.60L · 80%" in svg
    assert "5.40L · 20%" in svg


def test_the_long_head_has_a_short_name_on_the_pictures_only(world):
    _boq(); _ra(claim=50000.0)
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": "x", "date": "2026-10-12", "status": "Issued",
        "vendor_name": "A", "project_id": PID, "boq_id": "",
        "taxable_value": 6000.0, "subtotal": 6000.0, "grand_total": 9000.0,
        "charges": [{"label": "Freight", "amount": 2000.0, "taxable": False}],
        "items": []}
    r = PNL.project_pnl(PID)
    wf = PC.waterfall_html(PNL.waterfall_of(r))
    svg, table = wf.split("</svg>", 1)
    assert "PO charges outside the tax base" not in re.sub(
        r"<title>.*?</title>", "", svg)
    assert ">PO charges</tspan>" in svg and ">(non-taxable)</tspan>" in svg, \
        "wrapped onto two lines inside its own bar"
    assert "PO charges outside the tax base" in table


def test_waterfall_names_are_never_rotated():
    assert "rotate" not in PC.waterfall_html({
        "start": ("Billed to date", 1.0), "steps": [], "result": ("M", 1.0),
        "planned_revenue": None, "planned_margin": None})


def test_progress_shows_a_dash_for_no_figure_and_a_bar_otherwise(world):
    _boq(); _ra(claim=10000.0)
    html = PC.progress_html(PNL.progress_of(PID))
    rows = re.findall(r'<div class="prog-row".*?</div>', html)
    assert len(rows) == 6
    by = {re.search(r'prog-name">(.*?)<', r).group(1): r for r in rows}
    # billed and nothing received: a REAL 0%, which is a figure, not a dash
    assert ">0%<" in by["Collected"] and "&mdash;" not in by["Collected"]
    assert "prog-fill" in by["BOQ priced"] and ">100%<" in by["BOQ priced"]
