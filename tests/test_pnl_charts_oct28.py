"""
THE P&L's TWO PICTURES — §0 **fifty-eighth** block, item 5.

The client's ask from the 28 October 2026 Yogesh meeting: *"I want to see
where the money went."* Server-rendered inline **SVG** — no JS, no CDN, no
chart library — in a new leaf, `pnl_chart.py`.

**The assertions that matter most:**

- `test_EVERY_CHART_CARRIES_A_TABLE_OF_THE_SAME_NUMBERS`. Not a fallback: an
  `<svg>` that fails to render, a screen reader, a forced-colours mode and a
  print stylesheet all leave the picture out, and the figures must not go with
  it. It is also the relief the palette's light-end contrast obligates.
- `test_THE_WATERFALL_NEVER_BLENDS_AN_ESTIMATE_WITH_AN_ACTUAL`. The client
  asked for *"BOQ value, then each cost head, ending at margin"* — and a bar
  chart that starts at the **planned** revenue and subtracts **actual** costs
  ends at a figure that is neither margin. The BOQ value is a labelled
  reference rule instead, and no bar is a blend.
- `test_an_axis_with_no_denominator_draws_no_point`. *"Nothing has been
  dispatched"* and *"there is no supply on this schedule"* are different
  statements, and a 0% spoke claims the first.
- `test_the_leaf_does_no_arithmetic`. Every figure arrives computed, so there
  is still exactly one place in this application where money is worked out.

⚠ **Screen only.** `/projects/view` has no print route and does not gain one;
  no printed document changes and every print golden holds.
"""

import ast
import pathlib

import pytest

import pnl as PNL
import pnl_chart as PC
from store import STORE


_OWNED = ("projects", "boqs", "purchases", "ra_bills", "invoices", "proformas",
          "work_orders", "charges", "attendance", "receipts",
          "delivery_challans", "measurements")

PID = "p1"
L1, L2 = "aaaaaaaaaaaa", "bbbbbbbbbbbb"


@pytest.fixture()
def world(client):
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["projects"][PID] = {
        "id": PID, "name": "Jamnagar", "norm_name": "jamnagar", "client": "IOCL",
        "notes": "", "site_address_id": "", "site_address": "",
        "created_at": "2026-10-01 09:00", "updated_at": "2026-10-01 09:00"}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def _line(lid, qty="100", sup="100", sup_base="60", ins="40", ins_base="25"):
    return {"line_id": lid, "item_no": "1", "is_header": False,
            "description": "Pipe", "unit": "Mtrs", "total_qty": qty,
            "supply_rate": sup, "supply_base_rate": sup_base,
            "supply_escalation_pct": "0", "supply_discount_pct": "",
            "install_rate": ins, "install_base_rate": ins_base,
            "install_escalation_pct": "0", "install_discount_pct": ""}


def _boq(lines=None):
    STORE["boqs"]["b1"] = {
        "id": "b1", "ref": "SF/BOQ/26-27/0019", "rev_no": 0, "supersedes": "",
        "date": "2026-10-01", "project_id": PID,
        "line_items": lines if lines is not None else [_line(L1), _line(L2)],
        "subtotal": 28000.0}
    return STORE["boqs"]["b1"]


def _ra(claim=10000.0, grand=11800.0):
    STORE["ra_bills"]["r1"] = {
        "id": "r1", "ref": "SF/RA/26-27/0001", "ra_no": 1, "date": "2026-10-15",
        "boq_id": "b1", "leg": "supply", "status": "issued",
        "claim_subtotal": claim, "grand_total": grand, "claims": [],
        "tax_invoice_ref": "", "deduction_total": 0.0, "net_payable": claim,
        "tax_amount": grand - claim}


def _po(taxable=6000.0, line_ids=(L1,)):
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": "SF/PO/26-27/0007", "date": "2026-10-12",
        "status": "Issued", "vendor_name": "Acme", "project_id": PID,
        "boq_id": "", "taxable_value": taxable, "subtotal": taxable,
        "grand_total": taxable * 1.18, "charges": [],
        "items": [{"line_id": lid, "qty": 10, "rate": 60} for lid in line_ids]}


def _dc(qty=40):
    STORE["delivery_challans"]["dc1"] = {
        "id": "dc1", "ref": "SF/DC/26-27/0001", "date": "2026-10-05",
        "boq_id": "b1", "items": [{"line_id": L1, "qty": qty}]}


def _ms(qty=30, status="approved"):
    STORE["measurements"]["ms1"] = {
        "id": "ms1", "ref": "SF/MS/26-27/0001", "date": "2026-10-08",
        "boq_id": "b1", "approval_status": status,
        "items": [{"line_id": L1, "qty": qty, "is_header": False}]}


def _panel(client) -> str:
    r = client.get(f"/projects/view/{PID}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '<div class="panel pnl" id="pnl">' in html
    return html.split('<div class="panel pnl" id="pnl">', 1)[1]


# =============================================================================
# THE TABLE UNDER EVERY CHART
# =============================================================================

def test_EVERY_CHART_CARRIES_A_TABLE_OF_THE_SAME_NUMBERS(world):
    """THE ASSERTION THAT MATTERS MOST (1 of 4)."""
    _boq(); _ra(); _po(); _dc(); _ms()
    seg = _panel(world)
    assert seg.count('class="pnl-rows pnl-fig-tbl"') == 2, (
        "each of the two charts must carry its own table of the same figures")
    assert seg.count("The same figures, as text") == 2
    # …and the figures really are in it.
    assert "10,000.00" in seg and "6,000.00" in seg


def test_the_tables_are_not_conditional(world):
    """An empty-ish project still gets both tables — the table is the record,
    not a fallback that appears when something goes wrong."""
    _boq()
    seg = _panel(world)
    assert seg.count("The same figures, as text") == 2


def test_both_charts_are_inline_svg_with_no_script_and_no_cdn(world):
    _boq(); _ra(); _po()
    seg = _panel(world)
    assert seg.count("<svg viewBox=") == 2
    for bad in ("<script", "cdn.", "unpkg", "jsdelivr", "chart.js", "d3.",
                "https://"):
        assert bad not in seg.lower(), f"{bad!r} reached the P&L panel"


def test_each_chart_has_a_text_alternative_for_a_screen_reader(world):
    _boq(); _ra()
    seg = _panel(world)
    assert seg.count('role="img"') == 2
    assert seg.count("aria-label=") >= 2
    assert "<title>" in seg, "each mark carries a native SVG tooltip, no JS"


# =============================================================================
# THE WATERFALL
# =============================================================================

def test_THE_WATERFALL_NEVER_BLENDS_AN_ESTIMATE_WITH_AN_ACTUAL(world):
    """
    THE ASSERTION THAT MATTERS MOST (2 of 4). The chart STARTS at what was
    billed. The BOQ value is a labelled reference, not a bar — a bar chart
    from planned revenue down through actual cost ends at a figure that is
    neither the planned margin nor the margin to date.
    """
    _boq(); _ra(claim=10000.0); _po(taxable=6000.0)
    r = PNL.project_pnl(PID)
    wf = PNL.waterfall_of(r)
    assert wf["start"] == ("Billed to date", r["to_date"]["billed"])
    assert wf["result"] == ("Margin to date", r["to_date"]["margin"])
    assert wf["planned_revenue"] == r["planned"]["revenue"]
    # the plan is NOT one of the steps
    assert all(v != wf["planned_revenue"] for _k, _l, v in wf["steps"])
    seg = _panel(world)
    assert "a reference mark on the chart, never one of its bars" in seg
    assert "a plan and an actual are not added" in seg


def test_the_result_is_pnls_own_margin_and_not_a_second_sum(world):
    """Re-adding the bars would be a second arithmetic path to a figure that
    already exists; rounding would make them disagree eventually."""
    _boq(); _ra(claim=10000.0); _po(taxable=6000.0)
    r = PNL.project_pnl(PID)
    wf = PNL.waterfall_of(r)
    assert wf["result"][1] is r["to_date"]["margin"]


def test_THE_RENDERER_PRINTS_THE_RESULT_IT_WAS_HANDED(world):
    """
    The other half, and the half that matters: the renderer must print
    `result` **as given** rather than walking its own bars to a second figure.

    ⚠ Measured — this is a mutation that SURVIVED the first version of this
      file. The test above pins `waterfall_of()`, which is where the figure
      comes from; it says nothing about `pnl_chart.py`, where the walking
      would happen. So this hands the renderer a dict whose steps deliberately
      do **not** sum to its result and checks which number comes out.
    """
    wf = {"start": ("Billed to date", 10000.0),
          "steps": [("po", "Purchase orders", 1000.0)],
          # 10,000 - 1,000 would be 9,000. It is not 9,000.
          "result": ("Margin to date", 4242.0),
          "planned_revenue": None, "planned_margin": None,
          "labour_withheld": False}
    html = PC.waterfall_html(wf)
    assert "4,242.00" in html, "the renderer did not print the result it was given"
    assert "9,000.00" not in html, (
        "the renderer walked the bars to a second figure — that is a second "
        "arithmetic path to a number pnl.py already owns")


def test_a_negative_margin_is_drawn_below_the_axis(world):
    """A bar of height 0 for a real loss is the most misleading thing this
    chart could do."""
    _boq(); _ra(claim=1000.0); _po(taxable=9000.0)
    r = PNL.project_pnl(PID)
    assert r["to_date"]["margin"] < 0
    html = PC.waterfall_html(PNL.waterfall_of(r))
    assert PC.B.CHART_LOST in html, "a loss wears the status colour"
    assert "below the line is a" in html, "the caption must say so in words"


def test_a_positive_margin_wears_the_good_status_colour(world):
    _boq(); _ra(claim=10000.0); _po(taxable=1000.0)
    html = PC.waterfall_html(PNL.waterfall_of(PNL.project_pnl(PID)))
    assert PC.B.CHART_WON in html


def test_sign_is_never_colour_alone(world):
    """The method's rule for status colour: a label beside it, never the hue
    by itself. Position does it here, and the figure is printed."""
    _boq(); _ra(claim=1000.0); _po(taxable=9000.0)
    html = PC.waterfall_html(PNL.waterfall_of(PNL.project_pnl(PID)))
    assert "-8,000" in html or "-8000" in html


def test_a_cost_head_with_no_figure_is_dropped_and_a_nil_one_is_kept(world):
    """`We have bought nothing` is a fact worth a bar; `this reader may not
    see wages` is not a nil."""
    _boq(); _ra()
    wf = PNL.waterfall_of(PNL.project_pnl(PID, include_labour=False))
    keys = [k for k, _l, _v in wf["steps"]]
    assert "labour" not in keys, "a withheld row is not drawn as a nil cost"
    assert wf["labour_withheld"] is True
    assert "withheld" in PC.waterfall_html(wf)
    wf2 = PNL.waterfall_of(PNL.project_pnl(PID, include_labour=True))
    assert "labour" in [k for k, _l, _v in wf2["steps"]]


def test_the_charges_outside_the_tax_base_row_only_appears_when_it_exists(world):
    _boq(); _ra()
    assert "po_exempt" not in [k for k, _l, _v in
                               PNL.waterfall_of(PNL.project_pnl(PID))["steps"]]


# =============================================================================
# THE SPIDER
# =============================================================================

def test_there_are_exactly_six_axes_in_a_fixed_order(world):
    """
    ⚠ AMENDED 31 October 2026 (CLIENT_CHANGES.md §0 sixty-third block, C7),
    declared: Manas's axis list is BOQ, procurement, dispatch, measurement,
    billed, collected. Still an EXACT list in a FIXED order — no weaker. The
    old assertion, verbatim:
        assert [a["key"] for a in PNL.progress_of(PID)] == [
            "dispatched", "measured", "billed", "collected", "bought"]
    The *bought* count of lines is still on the panel, as the coverage line.
    """
    _boq()
    assert [a["key"] for a in PNL.progress_of(PID)] == [
        "boq", "procurement", "dispatched", "measured", "billed", "collected"]


def test_every_axis_is_a_ratio_of_two_figures_of_the_same_kind(world):
    """
    The one thing that makes five axes on one 0-100% scale readable. In
    particular COLLECTED is cash against GST-INCLUSIVE billing: a percentage
    taken across that boundary is gap 31 wearing a different hat and would
    read ~15% low for ever.
    """
    _boq(); _ra(claim=10000.0, grand=11800.0)
    STORE["receipts"]["rc1"] = {"id": "rc1", "ra_id": "r1", "date": "2026-10-20",
                                "amount": 5900.0, "mode": "NEFT", "ref": "x",
                                "written_off": 0.0}
    axes = {a["key"]: a for a in PNL.progress_of(PID)}
    assert axes["collected"]["denom"] == 11800.0, (
        "collected must be measured against GST-INCLUSIVE billing")
    assert axes["collected"]["pct"] == 50.0
    assert axes["billed"]["denom"] == PNL.project_pnl(PID)["planned"]["revenue"]


def test_an_axis_with_no_denominator_draws_no_point(world):
    """
    THE ASSERTION THAT MATTERS MOST (3 of 4). "Nothing has been dispatched"
    and "there is no supply on this schedule" are different statements.
    """
    _boq(lines=[_line(L1, sup="", sup_base="")])     # installation only
    axes = {a["key"]: a for a in PNL.progress_of(PID)}
    assert axes["dispatched"]["pct"] is None
    assert axes["dispatched"]["note"], "the reason must be stated"
    html = PC.spider_html(PNL.progress_of(PID))
    assert "no priced supply quantity" in html
    assert "draws no point" in html


def test_dispatched_counts_challan_quantity_against_the_tip(world):
    _boq(); _dc(qty=40)                              # 40 of 200 supply qty
    axes = {a["key"]: a for a in PNL.progress_of(PID)}
    assert axes["dispatched"]["pct"] == 20.0


def test_measured_uses_the_same_answer_as_the_overclaim_ceiling(world):
    """`measurement.approved_qty_by_line()` — so the spoke and the guard
    cannot disagree about what counts as measured."""
    _boq(); _ms(qty=50)                              # 50 of 200 install qty
    axes = {a["key"]: a for a in PNL.progress_of(PID)}
    assert axes["measured"]["pct"] == 25.0


def test_a_REJECTED_measurement_counts_toward_nothing(world):
    """
    ⚠ **The approval ladder is SWITCHED OFF in code** (12 September 2026,
    `approval.LADDER_ON = False`), so an **undecided** sheet DOES count —
    `measurement.feeds_ceiling()` says so and `ra.overclaims()` caps against
    it. This spoke reads the same predicate, so the two cannot disagree. What
    never counts, ladder on or off, is a sheet somebody REJECTED.

    Measured: with `status="pending"` the spoke is 25%, which is the ladder-off
    rule working, not a defect.
    """
    _boq(); _ms(qty=50, status="pending")
    assert {a["key"]: a for a in PNL.progress_of(PID)}["measured"]["pct"] == 25.0
    STORE["measurements"]["ms1"]["approval_status"] = "rejected"
    assert {a["key"]: a for a in PNL.progress_of(PID)}["measured"]["pct"] == 0.0, (
        "a rejected sheet moves no ceiling and no spoke")


def test_the_drawn_radius_is_clamped_and_the_printed_figure_is_not(world):
    """An over-collection stays readable as one rather than being flattened
    into 'complete'."""
    _boq(); _ra(claim=10000.0, grand=11800.0)
    STORE["receipts"]["rc1"] = {"id": "rc1", "ra_id": "r1", "date": "2026-10-20",
                                "amount": 20000.0, "mode": "NEFT", "ref": "x",
                                "written_off": 0.0}
    axes = {a["key"]: a for a in PNL.progress_of(PID)}
    assert axes["collected"]["pct"] > 100.0, "the figure is not clamped"
    html = PC.spider_html(PNL.progress_of(PID))
    assert "over 100%" in html, "and the table says so"


def test_the_spider_uses_short_names_and_the_table_the_full_ones(world):
    """Measured at 390 px: the full names pushed the page 156 px into a
    horizontal scrollbar, because a radar's labels run outward from the rim."""
    _boq()
    import re
    html = PC.spider_html(PNL.progress_of(PID))
    svg, table = html.split("</svg>", 1)
    drawn = " ".join(re.findall(r'class="sp-name">(.*?)</text>', svg))
    assert "Dispatched" in drawn and "Supply dispatched" not in drawn, (
        f"the drawn axis labels are {drawn!r}")
    # ⚠ The native `<title>` tooltip keeps the FULL name on purpose — it is
    #   not drawn, costs no width, and is what a hover reads out.
    assert "<title>Supply dispatched:" in svg
    assert "Supply dispatched" in table, "the full name is kept in the table"


# =============================================================================
# THE LEAF
# =============================================================================

def test_the_leaf_does_no_arithmetic(world):
    """
    THE ASSERTION THAT MATTERS MOST (4 of 4). Every money figure arrives
    computed from `pnl.py`; this module turns numbers into COORDINATES. The
    arithmetic it is allowed is geometry — and geometry never touches a figure
    that is not already a ratio or a coordinate.
    """
    src = (pathlib.Path(__file__).resolve().parent.parent / "pnl_chart.py")
    names = set()
    for node in ast.walk(ast.parse(src.read_text(encoding="utf8"))):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert names == {"math", "branding", "pipeline", "quotation"}, (
        f"pnl_chart.py imports {sorted(names)} — it must reach no module that "
        f"knows a project, above all not pnl.py: the figures are handed in")


def test_the_palette_comes_from_branding_and_nothing_is_minted(world):
    """Colours are `branding.CHART_*`. The ramp passed the ORDINAL checks
    (monotone lightness, adjacent ΔL, light-end contrast, single hue) and the
    two status colours clear 3:1 on white — measured 29 October 2026."""
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "pnl_chart.py").read_text(encoding="utf8")
    import re
    body = src.split('"""', 2)[2]        # past the module docstring
    drawing = body.split("CHART_CSS")[0]
    # Everything after the four named chrome constants is the DRAWING code,
    # and it must hold no hex at all: a data mark's colour comes from
    # branding.CHART_*, and the grid / rings / zero line / connector are the
    # four constants declared together above it.
    after = drawing.split('C_RING = ', 1)[1].split("\n", 1)[1]
    assert not re.findall(r"#[0-9a-fA-F]{6}\b", after), (
        f"a hex literal in the drawing code: "
        f"{re.findall(r'#[0-9a-fA-F]{{6}}', after)} — a series colour belongs "
        f"in branding.py and recessive chrome in the constants above")
    assert drawing.count("B.CHART_") >= 4, "the palette really is read"
    # …and CHART_WARN is NOT used as a fill: it is 1.83:1 on white, below the
    # 3:1 floor. Checked against the CODE, not the file — the module docstring
    # names it precisely to record why it is excluded, and a check that could
    # not tell the two apart would punish the explanation.
    assert "CHART_WARN" not in drawing
    assert "CHART_WARN" not in src.split("CHART_CSS")[1]


def test_the_stylesheet_travels_inside_the_panel(world):
    """`PNL_CSS`'s arrangement: a reader without `project.pnl` gets no byte
    of it, which is what keeps `tests/test_pnl_access.py` green."""
    _boq()
    assert ".pnl-svg" in PC.CHART_CSS
    import auth
    assert ".pnl-svg" in _panel(world)


def test_a_reader_without_project_pnl_sees_no_chart(world, monkeypatch):
    _boq(); _ra()
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "project.pnl" else real(p))
    html = world.get(f"/projects/view/{PID}").get_data(as_text=True)
    # ⚠ Not a bare `<svg` check: the app shell's rail icons are inline SVG too
    #   and are on every page for everybody. The CHART class is the test.
    assert 'class="pnl-svg' not in html
    assert ".pnl-svg" not in html, "nor one byte of its stylesheet"
    assert "The same figures, as text" not in html


def test_the_charts_are_screen_only(world):
    """`/projects/view` has no print route and does not gain one here."""
    import app as app_module
    printers = [r.rule for r in app_module.app.url_map.iter_rules()
                if "/projects" in r.rule and "print" in r.rule]
    assert printers == [], f"the project page grew a print route: {printers}"


# =============================================================================
# THE DASHBOARD ROW
# =============================================================================

def test_the_dashboard_row_carries_billed_spent_and_the_margin(world):
    _boq(); _ra(claim=10000.0); _po(taxable=6000.0)
    html = world.get("/").get_data(as_text=True)
    assert 'class="pp-mini"' in html
    assert "Margin to date" in html
    assert "pp-up" in html, "a positive margin wears the good tone"


def test_a_negative_dashboard_margin_wears_the_other_tone(world):
    _boq(); _ra(claim=1000.0); _po(taxable=9000.0)
    assert "pp-down" in world.get("/").get_data(as_text=True)


def test_the_dashboard_row_is_gated_by_project_pnl(world, monkeypatch):
    _boq(); _ra()
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "project.pnl" else real(p))
    assert 'class="pp-mini"' not in world.get("/").get_data(as_text=True)


def test_the_dashboard_margin_says_when_it_excludes_labour(world, monkeypatch):
    """B4's wall, asked here as the panel asks it."""
    _boq(); _ra()
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "attendance.view" else real(p))
    assert "excl. labour" in world.get("/").get_data(as_text=True)


def test_the_dashboard_reaches_pnl_in_the_function_body_only(world):
    """
    `pnl.py` imports boq, ra, purchase, workorder, merged_ra and attendance,
    and every one of those imports `dashboard.py` for BASE_STYLES — a
    module-level arrow is a cycle at boot.
    `tests/test_import_directions.py` pins it; this states it beside the
    behaviour.
    """
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "dashboard.py").read_text(encoding="utf8")
    tree = ast.parse(src)
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert "pnl" not in top, "dashboard.py imports pnl at module level"
    assert "import pnl" in src, "…and never reaches it at all"
