"""
The joint measurement sheet fits its page — CLIENT_CHANGES.md §0,
thirty-sixth block, item B (30 September 2026).

On production the letterhead, the header block, the grid and the right-hand
sign-off party all ran past the right edge of the page frame, the logo was
clipped, and "100 NB (M)" wrapped onto three lines. Measured in a headless
print of the old code, the cause was two things together:

* the grid gave every column a fixed millimetre width (about 263mm in all),
  and `.page-frame` is a `<table>`, so it grew to hold the grid — taking the
  letterhead and the sign-off with it past a card that stayed 210mm wide,
  because the 297mm outer rule sat on the INNER element;
* the grid heads wore the app's screen `th` (letter-spaced, a screen size),
  which `.q-table th` resets and `.jm-grid th` never did.

What this file holds is the layout's CONTRACT, not its pixels — the pixels
are in the render proof of the pass and in the golden in
`tests/test_print_golden.py`:

* the grid's widths are percentages that sum to 100, LOCATION and REMARKS
  wider, numerics equal — for both the landscape and the portrait paper;
* no cell carries a width of its own;
* the page frame is the landscape variant, for a joint sheet only;
* the staff-only site band is on the screen and never on the paper;
* a head is two lines, a row and the sign-off never split, the parties are
  equal halves, and a measured figure prints as it was typed.
"""

import re

import pytest

import docsheet as DS
import measurement as MS
from store import STORE
from test_print_golden import (  # noqa: F401  (fixtures)
    pinned_identity, golden, golden_ms, GOLD_MS, GOLD_TI, GOLD_PI, GOLD_PO,
    blank_identity)

COLGROUP = re.compile(r'<colgroup style="([^"]+)">(.*?)</colgroup>', re.S)


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def _widths(html):
    """`({var: float}, [col classes])` from the grid's colgroup."""
    m = COLGROUP.search(html)
    assert m, "the grid has no colgroup — its widths are nobody's"
    vars_ = {k.strip(): float(v.strip().rstrip("%"))
             for k, v in (p.split(":") for p in m.group(1).split(";"))}
    cols = re.findall(r'<col class="([^"]+)"/>', m.group(2))
    return vars_, cols


def _grid(html):
    return html.split('<table class="jm-grid">')[1].split("</table>")[0]


# ── The widths ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("suffix", ["", "-p"], ids=["landscape", "portrait"])
def test_the_grid_widths_sum_to_100_with_location_and_remarks_wider(
        suffix, client, golden_ms):
    html = _get(client, f"/measurement/print/{GOLD_MS}")
    w, cols = _widths(html)
    n = len(STORE["measurements"][GOLD_MS]["grid_columns"])
    assert cols == ["jm-c-loc"] + ["jm-c-num"] * n + ["jm-c-rem"]
    loc, num, rem = w[f"--jm-loc{suffix}"], w[f"--jm-num{suffix}"], w[f"--jm-rem{suffix}"]
    assert loc + n * num + rem == pytest.approx(100, abs=0.01)
    assert loc > num and rem > num, "LOCATION and REMARKS must be wider"


def test_portrait_paper_gives_the_numeric_columns_more_of_the_page():
    """Measured: at the landscape shares "SUPPORTS" broke mid-word on A4 portrait."""
    _l, num_l, _r = MS.grid_col_widths(12, "landscape")
    loc_p, num_p, rem_p = MS.grid_col_widths(12, "portrait")
    assert num_p > num_l
    assert (loc_p, rem_p) < MS.GRID_WIDTHS["landscape"]


def test_a_sheet_with_no_numeric_columns_still_sums_to_100():
    for page in MS.GRID_WIDTHS:
        loc, num, rem = MS.grid_col_widths(0, page)
        assert num == 0 and loc + rem == 100


def test_every_column_takes_its_width_from_the_colgroup_and_nothing_else():
    css = MS.MS_JOINT_STYLES
    for key in ("loc", "num", "rem"):
        assert f"col.jm-c-{key} {{ width:var(--jm-{key}); }}" in css
        assert f"col.jm-c-{key} {{ width:var(--jm-{key}-p); }}" in css
    assert "table-layout:fixed" in css and "table.jm-grid { width:100%" in css


def test_no_cell_on_the_grid_carries_a_width_of_its_own(client, golden_ms):
    """The fixed millimetre widths are what pushed the frame off the page."""
    grid = _grid(_get(client, f"/measurement/print/{GOLD_MS}"))
    for tag in re.findall(r"<t[hd][^>]*>", grid):
        assert "width" not in tag, f"a grid cell carries its own width: {tag}"
    for rule in re.findall(r"\.jm-(?:loc|num|grp|rem)\s*\{[^}]*\}", MS.MS_JOINT_STYLES):
        assert "width" not in rule, f"a grid class carries a fixed width: {rule}"
    assert not re.search(r"\d+mm", " ".join(
        re.findall(r"table\.jm-grid col[^}]*\}", MS.MS_JOINT_STYLES)))


# ── The frame ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("route", ["print", "view"])
def test_a_joint_sheet_is_drawn_on_the_landscape_frame(route, client, golden_ms):
    html = _get(client, f"/measurement/{route}/{GOLD_MS}")
    assert '<div class="doc-outer sheet-landscape">' in html
    assert DS.LANDSCAPE_STYLES in html and DS.LANDSCAPE_SCRIPT in html
    assert "A4 landscape" in html


def test_a_legacy_sheet_stays_a_portrait_page(client, golden_ms):
    STORE["measurements"]["leg-x"] = {
        "id": "leg-x", "ref": "SF/MS/26-27/0001", "date": "2026-08-30",
        "boq_ref": "B", "project_name": "P", "account_name": "A",
        "site_location": "S", "location": "", "measured_by": "",
        "witnessed_by": "", "notes": "", "company_branch": "",
        "auth_signatory": "", "items": [], "approval_status": "approved"}
    html = _get(client, "/measurement/print/leg-x")
    assert "sheet-landscape" not in html and DS.LANDSCAPE_SCRIPT not in html
    assert '<div class="doc-outer">' in html


def test_the_landscape_variant_is_not_in_the_shared_stack(client, golden):
    """Opt-in only: no other document may turn landscape through it."""
    assert DS.LANDSCAPE_CSS not in DS.SHEET_STYLES
    for url in (f"/invoice/view/{GOLD_TI}", f"/proforma/view/{GOLD_PI}",
                f"/purchase/view/{GOLD_PO}"):
        html = _get(client, url)
        assert "sheet-landscape" not in html and DS.LANDSCAPE_SCRIPT not in html


def test_a_touch_device_withdraws_the_landscape_request():
    """A phone scales a landscape page box onto portrait paper — withdraw it."""
    assert "(pointer: coarse)" in DS.LANDSCAPE_SCRIPT
    assert "@page { size:auto; }" in DS.LANDSCAPE_SCRIPT


# ── The staff-only band ─────────────────────────────────────────────────────

@pytest.mark.parametrize("source", ["boq", "none"])
def test_the_site_band_is_on_the_screen_and_never_on_the_paper(
        source, client, golden_ms):
    STORE["measurements"][GOLD_MS]["site_source"] = source
    view = _get(client, f"/measurement/view/{GOLD_MS}")
    printed = _get(client, f"/measurement/print/{GOLD_MS}")
    assert '<div class="jm-drift">' in view
    assert '<div class="jm-drift">' not in printed
    assert "free-text string on the schedule" not in printed
    assert "No site is recorded against this sheet" not in printed


# ── Heads, rows, parties ────────────────────────────────────────────────────

def test_a_head_is_its_label_on_one_line_and_its_unit_on_the_next(
        client, golden_ms):
    grid = _grid(_get(client, f"/measurement/print/{GOLD_MS}"))
    assert ('<span class="jm-hl">100 NB</span><span class="jm-unit">(m)</span>'
            in grid)
    assert ('<span class="jm-hl">PENDANT</span><span class="jm-unit">(Nos)</span>'
            in grid)
    css = MS.MS_JOINT_STYLES
    assert ".jm-hl { white-space:nowrap; }" in css
    assert ".jm-unit { display:block;" in css
    assert "overflow-wrap:anywhere" not in css.split(".jm-band")[0], (
        "a grid head may break mid-word")


def test_the_grid_does_not_wear_the_apps_screen_th():
    """BASE_STYLES' bare `th` is letter-spaced at a screen size — declare over it."""
    rule = re.search(r"table\.jm-grid th,\s*\.quotation-doc table\.jm-grid td "
                     r"\{[^}]*\}", MS.MS_JOINT_STYLES).group(0)
    for prop in ("letter-spacing:normal", "font-size:var(--fs-sm)",
                 "font-family:inherit", "color:var(--doc-ink)"):
        assert prop in rule, prop


def test_a_row_and_the_sign_off_never_split_across_pages():
    css = MS.MS_JOINT_STYLES
    printed = css.split("@media print {")[1]
    assert "table.jm-grid > thead { display:table-header-group; }" in printed
    for sel in (".quotation-doc table.jm-grid tr", ".quotation-doc .jm-sign",
                ".quotation-doc .jm-party"):
        assert sel in printed
    assert "break-inside:avoid; page-break-inside:avoid;" in printed


def test_the_two_parties_are_equal_halves_side_by_side():
    assert ("grid-template-columns:minmax(0,1fr) minmax(0,1fr);"
            in MS.MS_JOINT_STYLES)


def test_a_measured_figure_prints_as_it_was_typed(client, golden_ms):
    """`_fmt_qty()` rounds to six significant figures: 1023.125 was 1023.12."""
    ms = STORE["measurements"][GOLD_MS]
    ms["grid_rows"].append({"label": "Tank farm",
                            "values": {"d150": 1023.125, "d200": 0.0},
                            "remarks": ""})
    grid = _grid(_get(client, f"/measurement/print/{GOLD_MS}"))
    assert ">1023.125<" in grid
    assert ">1045.125<" in grid, "the 150 NB TOTAL is 22 + 1023.125"
    assert MS._fmt_cell(0.0) == "" and MS._fmt_cell(64.0) == "64"


def test_the_blank_address_chip_is_still_drawn(client, golden_ms, blank_identity):
    """Explicitly untouched: it goes away when /settings is filled."""
    html = _get(client, f"/measurement/print/{GOLD_MS}")
    assert '<span class="todo-chip">add registered address</span>' in html
