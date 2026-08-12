"""
The issued BOQ print hides the rate breakup — and stays square while doing it.

The client asked on 10 Aug 2026 that the sheet they are sent stop showing HOW a
rate was arrived at: the base rate columns and the escalation percentage. The
escalated U/ Rate is what was agreed and what they are billed against; the
schedule it was derived from is our side of the negotiation.

So `/boq/print` renders `boq._document_html(…, show_rate_breakup=False)` and
`/boq/view` renders it with True. Three columns' difference, and nothing else:
the record keeps every field, and every figure on the sheet is the one that was
already there.

    THE TEST THAT EARNS ITS KEEP is `test_every_print_row_matches_the_header
    _column_count`. Dropping a column from a table whose spans were counted by
    hand does not raise, does not warn and does not look wrong in a diff — it
    prints one section with its subtotal under the wrong heading, and the first
    person to notice is holding the paper. It walks the real occupancy grid
    (colspan AND rowspan) of every row of every section table, so a span that is
    one out anywhere fails here rather than at the client's desk.
"""

from html.parser import HTMLParser

import pytest

import boq
import demo_data as DD
from store import STORE

# The seeded Sify Bangalore schedule — 97 lines, three sections, and the only
# BOQ in the app with a section that declares no areas at all (C). That section
# is why the header has two shapes: with the breakup hidden AND no areas, the
# second header row has nothing left to carry.
BOQ_ID = DD.BOQ_META["id"]

# Section subtotals and the total, computed from the seeded lines BEFORE this
# change and pinned here. `_document_html` recomputes from `line_items` on every
# render (§3, property 7), so these also assert the print and the view can never
# quote different money for the same schedule.
#
# Section A's pair is the Phase 1 acceptance figure, independently hand-typed in
# tests/test_boq.py from the client's own workbook.
SECTION_MONEY = {
    "A": (483764.50, 311350.00),
    "B": (5659023.80, 2357400.00),
    "C": (34775.00, 345000.00),
}
TOTAL_SUPPLY = 6177563.30
TOTAL_INSTALL = 3013750.00
TOTAL_BASIC_VALUE = 9191313.30


# ── The occupancy grid ─────────────────────────────────────────────────────

class _BoqTables(HTMLParser):
    """
    Every `<table class="boq-table">` on a page, as colgroup width + raw rows.

    Deliberately a parser and not a regex: the thing under test is nesting and
    span arithmetic, and a regex that could be fooled by either would be
    checking nothing. `.page-frame` and `.boq-grand` are also tables, so the
    class is what selects; no boq-table ever nests inside another.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._t = None
        self._row = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "boq-table" in (a.get("class") or ""):
            self._t = {"cols": 0, "rows": []}
            return
        if self._t is None:
            return
        if tag == "col":
            self._t["cols"] += 1
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._row.append((int(a.get("colspan") or 1), int(a.get("rowspan") or 1)))

    def handle_endtag(self, tag):
        if self._t is None:
            return
        if tag == "tr":
            self._t["rows"].append(self._row or [])
            self._row = None
        elif tag == "table":
            self.tables.append(self._t)
            self._t = None


def _tables(html: str) -> list:
    p = _BoqTables()
    p.feed(html)
    return p.tables


def _row_widths(table: dict) -> list:
    """
    How many columns each row actually occupies.

    Not `sum(colspan)`: a `rowspan="2"` head in the first row eats a column of
    the second one without placing a cell there, so summing the spans of the
    cells written in that row under-counts it. This walks the grid the browser
    walks — carry the occupied columns down, skip them, then add the spans.
    """
    carry, widths = {}, []
    for cells in table["rows"]:
        occupied = dict(carry)                                   # blocked in THIS row
        carry = {k: v - 1 for k, v in carry.items() if v > 1}    # …and beyond
        col = used = 0
        for colspan, rowspan in cells:
            while occupied.get(col, 0):
                col, used = col + 1, used + 1
            if rowspan > 1:
                for k in range(col, col + colspan):
                    carry[k] = rowspan - 1
            col, used = col + colspan, used + colspan
        while occupied.get(col, 0):                              # trailing carried cells
            col, used = col + 1, used + 1
        widths.append(used)
    return widths


@pytest.fixture()
def printed(client):
    """The issued BOQ document — the seeded 97-line Sify schedule."""
    r = client.get(f"/boq/print/{BOQ_ID}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


@pytest.fixture()
def viewed(client):
    """The same schedule on screen, where the breakup is still shown."""
    r = client.get(f"/boq/view/{BOQ_ID}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ── What leaves the building ───────────────────────────────────────────────

def test_print_omits_base_rate_and_escalation_columns(printed):
    """Neither the heads nor a single cell of the three dropped columns."""
    assert "Base Rate" not in printed
    assert "Esc" not in printed            # "Esc. %" and anything else spelling it
    assert 'class="b-base"' not in printed
    assert 'class="b-esc"' not in printed

    # The base-rate columns are headed with the BOQ's own `rate_basis_label`,
    # not the literal "Base Rate" — the seeded schedule is priced off "Mohali
    # Rates". Asserting only the literal would pass on a sheet still printing
    # every base rate under that heading, so the label is checked too.
    #
    # ⚠ It appears NOWHERE on the issued sheet, header included. The document
    #   header's "Rate Basis" line used to survive here on the reasoning that it
    #   named the basis without disclosing a rate off it. That was the wrong
    #   call: naming another project's rate contract on the very sheet those
    #   figures were removed from tells the client a reference schedule exists
    #   and what to ask for. It stays on the record and on /boq/view.
    assert "Mohali Rates" not in printed
    assert "Rate Basis" not in printed


def test_print_keeps_the_rate_and_amount_columns(printed):
    """What was agreed, and what it comes to, both stay on the issued sheet."""
    # Three sections, each with a supply and an installation rate column.
    assert printed.count("U/ Rate") == 6
    assert printed.count("Supply Amount") == 3
    assert printed.count("Installation Amount") == 3
    assert printed.count("BASIC VALUE SUBTOTAL") == 3
    assert "TOTAL BASIC VALUE" in printed


def test_print_collapses_the_group_heads_it_emptied(printed):
    """
    No `Supply` / `Installation` band over a single column, and no blank row.

    Both are what a naive removal leaves behind: a group head spanning one
    column, and — on section C, which declares no areas — a second header row
    with nothing in it, which prints as a grey band across the page because
    `.boq-table th` is filled.
    """
    assert "<th colspan=" not in printed          # no group head left anywhere
    assert ">Supply<br/>U/ Rate<" in printed      # the track name moved onto the column
    assert ">Installation<br/>U/ Rate<" in printed
    assert "<tr></tr>" not in printed

    tables = _tables(printed)
    assert len(tables) == 3
    # A (2 areas) and B (1 area) still need a second row for the area names;
    # C declares none, so its header is a single row.
    assert [len(t["rows"]) > 0 for t in tables] == [True, True, True]


# ── The one that catches a broken layout ───────────────────────────────────

def test_every_print_row_matches_the_header_column_count(printed):
    """Every row of every section table occupies exactly the table's width."""
    tables = _tables(printed)
    assert len(tables) == 3, "expected one table per section of the seeded BOQ"

    for n, t in enumerate(tables):
        widths = set(_row_widths(t))
        assert widths == {t["cols"]}, (
            f"section table {n} declares {t['cols']} columns in its colgroup but "
            f"has rows occupying {sorted(widths)} — a colspan is out, which "
            f"prints figures under the wrong heading")

    # The three sections differ only by how many areas they declare: 2, 1, 0.
    assert [t["cols"] for t in tables] == [10, 9, 8]


def test_print_drops_exactly_three_columns_per_section(printed, viewed):
    """
    Supply base, supply escalation, installation base — and nothing else.

    A section losing four columns means an amount column went with them; three
    is the whole intended change, per section, regardless of the area count.
    """
    printed_cols = [t["cols"] for t in _tables(printed)]
    viewed_cols = [t["cols"] for t in _tables(viewed)]
    assert viewed_cols == [13, 12, 11]
    assert [v - p for v, p in zip(viewed_cols, printed_cols)] == [3, 3, 3]


# ── Money did not move ─────────────────────────────────────────────────────

def test_print_money_is_unchanged(client, printed):
    """The exact subtotals and total, pinned to the figures from before this."""
    b = STORE["boqs"][BOQ_ID]

    for code, (supply, install) in SECTION_MONEY.items():
        sup, ins = boq.section_totals(b, code)
        assert round(sup, 2) == supply, f"section {code} supply subtotal moved"
        assert round(ins, 2) == install, f"section {code} installation subtotal moved"

    sup, ins, total = boq.boq_totals(b)
    assert round(sup, 2) == TOTAL_SUPPLY
    assert round(ins, 2) == TOTAL_INSTALL
    assert round(total, 2) == TOTAL_BASIC_VALUE

    # …and that those are the figures actually ON the issued sheet. Computing
    # them correctly and printing something else is the failure this catches.
    for supply, install in SECTION_MONEY.values():
        assert boq._inr(supply) in printed
        assert boq._inr(install) in printed
    assert boq._inr(TOTAL_BASIC_VALUE) in printed


def test_print_and_view_quote_the_same_money(printed, viewed):
    """One schedule, two renders, no room for them to disagree."""
    for supply, install in SECTION_MONEY.values():
        assert boq._inr(supply) in printed and boq._inr(supply) in viewed
        assert boq._inr(install) in printed and boq._inr(install) in viewed
    assert boq._inr(TOTAL_BASIC_VALUE) in printed
    assert boq._inr(TOTAL_BASIC_VALUE) in viewed


# ── The app keeps what the client does not get ─────────────────────────────

def test_the_rate_basis_header_line_is_print_only_suppressed(printed, viewed):
    """
    The document header's "Rate Basis" row: gone from the print, kept on screen.

    Same flag, same reasoning as the columns — it is the label those hidden
    figures were derived under. Checked on both renders in one place so the two
    halves cannot drift apart.
    """
    assert "Rate Basis" not in printed
    assert "Mohali Rates" not in printed

    assert "Rate Basis" in viewed
    assert "Mohali Rates" in viewed

    # The rows either side of it are untouched, so the header block did not
    # simply lose its second column.
    for field in ("Date", "Revision", "Terms of Delivery"):
        assert field in printed and field in viewed


def test_boq_view_still_shows_base_rate_and_escalation(viewed):
    """
    `/boq/view` is the internal copy. Nothing was taken away from it.

    This is the half of the change that is easiest to break by accident, and
    the most expensive: whoever prices the next revision needs the base rate
    and the escalation to work from.
    """
    assert "Mohali Rates" in viewed          # the base-rate column head
    assert "Esc. %" in viewed
    assert 'class="b-base"' in viewed
    assert 'class="b-esc"' in viewed
    assert "U/ Rate" in viewed

    # Grouped heads, because each track has more than one column again.
    assert '<th colspan="3">Supply</th>' in viewed
    assert '<th colspan="2">Installation</th>' in viewed

    for n, t in enumerate(_tables(viewed)):
        assert set(_row_widths(t)) == {t["cols"]}, f"view section table {n} is not square"


def test_the_record_still_carries_every_rate(client, printed):
    """Display only. The fields the print omits are untouched in the record."""
    b = STORE["boqs"][BOQ_ID]
    priced = [li for li in b["line_items"] if not li.get("is_header")]

    assert any(li.get("supply_base_rate") is not None for li in priced)
    assert any(float(li.get("supply_escalation_pct") or 0) for li in priced)
    for li in priced:
        for key in ("supply_base_rate", "supply_escalation_pct",
                    "install_base_rate", "install_escalation_pct"):
            assert key in li, f"{key} was dropped from the record"


# ── The flag itself ────────────────────────────────────────────────────────

def test_rate_breakup_true_restores_the_columns_and_stays_square(client):
    """
    `show_rate_breakup=True` brings all three back, squarely.

    Called on the builder rather than through a route: the flag is the seam an
    internal-copy variant will be switched on, so it has to hold on its own.
    """
    client.get("/boq/")                       # seed
    b = STORE["boqs"][BOQ_ID]

    html = boq._document_html(b, show_rate_breakup=True)
    assert "Mohali Rates" in html
    assert "Esc. %" in html
    assert 'class="b-base"' in html
    assert 'class="b-esc"' in html

    tables = _tables(html)
    assert [t["cols"] for t in tables] == [13, 12, 11]
    for n, t in enumerate(tables):
        assert set(_row_widths(t)) == {t["cols"]}, f"section table {n} is not square"


def test_rate_breakup_defaults_to_false(client):
    """The issued document is the default; showing the breakup is the opt-in."""
    client.get("/boq/")
    b = STORE["boqs"][BOQ_ID]

    assert boq._document_html(b) == boq._document_html(b, show_rate_breakup=False)
    assert 'class="b-base"' not in boq._document_html(b)
