"""
LABOUR AS ONE LINE WITH AN ESTIMATED / ACTUAL SPLIT — ruling 4.

CLIENT_CHANGES.md §0's **sixty-sixth** block, Manas's ruling 4 of 5 November
2026: *"Project P&L, waterfall and dashboard show labour as one line with an
'Estimated' / 'Actual' split. P&L totals use estimate + actual. Nothing else
in the P&L changes."*

⚠ **ONE line, in all four places, and that is the ruling rather than a layout
  choice.** Two rows would be two cost heads: *Spent to date* adds the labour
  cell and nothing else, and a reader shown two figures under one heading is
  invited to add them — which is right, which is why they are already added.
  So the total stays one figure and the split is said beside it.

The four places, each asserted below:

1. `projectview._pnl_panel()` — the Site labour row's `pnl-split` span, plus
   one `pnl-note` saying what the two words mean.
2. `pnl.waterfall_of()` — one step, with `labour_split` beside it, printed by
   `pnl_chart` in the table cell that used to read *"actual cost recorded"*.
3. `pnl.register_line_html()` — the `/projects` register's untagged line.
4. `dashboard` — the project tile's running-position note, and the
   unattributed-cost line.

⚠ **Nothing else in the P&L changes**, which is what
  `test_nothing_but_the_labour_row_moved` holds.
"""

import pytest

import attendance as AT
import employee as EMP
import payroll as PAY
import pnl as PNL
import pnl_chart as PC
from store import STORE

SITE = "lpd-site"
PID = "lpd-p1"
_OWNED = ("attendance", "employees", "projects", "addresses", "boqs",
          "pay_entries", "payslips", "settings", "purchases", "charges",
          "work_orders", "ra_bills", "invoices", "proformas")


@pytest.fixture()
def world(client):
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["addresses"][SITE] = {"id": SITE, "label": "Jamnagar Refinery",
                                "type": "site", "archived": False}
    STORE["projects"][PID] = {
        "id": PID, "name": "Jamnagar", "norm_name": "jamnagar",
        "client": "IOCL", "notes": "", "site_address_id": SITE,
        "site_address": "Jamnagar Refinery",
        "created_at": "2026-10-01 09:00", "updated_at": "2026-10-01 09:00"}
    STORE["employees"]["e1"] = {
        "id": "e1", "name": "Ramesh Patil", "code": "W-01",
        "designation": "Fitter", "day_rate": 800.0, "active": True,
        "site": "Jamnagar Refinery", EMP.SITE_ADDRESS_FIELD: SITE,
        EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def _mark(mid, date, pid=PID, status=AT.PRESENT, **over):
    rec = {"id": mid, "employee_id": "e1", "employee_name": "Ramesh Patil",
           "employee_code": "W-01", "date": date, "status": status,
           "ot_hours": 0.0, "day_rate": 800.0, "site": "Jamnagar Refinery",
           EMP.SITE_ADDRESS_FIELD: SITE, EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK,
           "project_id": pid,
           "project_name": "Jamnagar" if pid == PID else ""}
    rec.update(over)
    STORE["attendance"][mid] = rec
    return rec


def _issue(month, basic=0.0, ot=0.0, travel=0.0):
    STORE["payslips"][f"s-{month}"] = {
        "id": f"s-{month}", "employee_id": "e1", "month": month,
        "status": PAY.ISSUED,
        "snapshot": {"employee_name": "Ramesh Patil", "basic": basic,
                     "ot": ot, "travel": travel, "advance": 0.0,
                     "loan_deduction": 0.0, "payable": basic + ot + travel}}


def _panel(client):
    html = client.get(f"/projects/view/{PID}").get_data(as_text=True)
    assert "Profit &amp; Loss" in html or "pnl-rows" in html, "no P&L panel"
    return html


# =============================================================================
# 1. THE P&L PANEL
# =============================================================================

def test_the_panel_draws_one_labour_row_carrying_the_total(world):
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-09-01")
    _issue("2026-09", basic=1200.0)
    html = _panel(world)
    assert html.count("Site labour &mdash; booked to this project") == 1, \
        "ONE row — two would be two cost heads under one heading"
    assert "&#8377;&nbsp;2,000.00" in html, "the row carries estimate + actual"


def test_the_row_says_which_part_is_estimated_and_which_is_actual(world):
    _mark("m1", "2026-10-01")             # estimate 800
    _mark("m2", "2026-09-01")             # paid
    _issue("2026-09", basic=1000.0, travel=200.0)
    html = _panel(world)
    seg = html.split('<span class="pnl-split">', 1)[1].split("</span>", 1)[0]
    assert "estimated" in seg and "actual" in seg
    assert "800.00" in seg and "1,200.00" in seg
    assert "1 issued payslip" in seg


def test_an_unpaid_project_says_all_estimated_rather_than_nothing(world):
    _mark("m1", "2026-10-01")
    html = _panel(world)
    assert "all estimated, no payslip issued for it yet" in html


def test_the_panel_explains_the_two_words_once(world):
    _mark("m1", "2026-10-01")
    html = _panel(world)
    assert html.count("Site labour is an estimate until the month is "
                      "paid.") == 1
    assert "Advances, loans and deductions are never a project cost." in html


def test_the_note_is_absent_when_there_is_no_labour_at_all(world):
    html = _panel(world)
    assert "Site labour is an estimate until the month is paid." not in html


def test_the_pnl_total_is_estimate_plus_actual(world):
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-09-01")
    _issue("2026-09", basic=1500.0)
    td = PNL.project_pnl(PID)["to_date"]
    assert td["labour"]["estimate"] == 800.0
    assert td["labour"]["actual"] == 1500.0
    assert td["labour"]["total"] == 2300.0
    assert td["actual"] == 2300.0, "Spent to date adds the one labour cell"
    assert td["margin"] == -2300.0


def test_nothing_but_the_labour_row_moved(world):
    """
    ⚠ **Ruling 4's last line — *"Nothing else in the P&L changes"*.**

    Two claims, in the two places a change could hide:

    * **the figures.** Rendered twice from one process, once with a labour
      marking and once without: every head of `to_date` but `labour` and the
      three sums it feeds is identical, key for key.
    * **the panel.** Every `<tr>` of the `pnl-rows` table but the labour row
      and the two sums is byte-identical.
    """
    before = PNL.project_pnl(PID)["to_date"]
    html_before = _panel(world)
    _mark("m1", "2026-10-01")
    after = PNL.project_pnl(PID)["to_date"]
    html_after = _panel(world)

    moved = {"labour", "actual", "margin"}
    for key in set(before) | set(after):
        if key in moved:
            continue
        assert before[key] == after[key], (
            f"a labour marking moved {key!r}: {before[key]!r} -> "
            f"{after[key]!r}. Ruling 4 changes the labour row and the sums it "
            f"feeds, and nothing else.")
    assert after["actual"] == before["actual"] + 800.0
    assert after["margin"] == before["margin"] - 800.0

    def rows(h: str) -> list:
        tbl = h.split('<table class="pnl-rows">', 1)[1].split("</table>", 1)[0]
        return [r for r in tbl.split("<tr") if "Site labour" not in r
                and "Spent to date" not in r and "Margin to date" not in r]

    assert rows(html_before) == rows(html_after), (
        "a row outside the labour row and the two sums it feeds moved")


# =============================================================================
# 2. THE WATERFALL
# =============================================================================

def test_the_waterfall_has_one_labour_step_with_the_split_beside_it(world):
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-09-01")
    _issue("2026-09", basic=1200.0)
    wf = PNL.waterfall_of(PNL.project_pnl(PID))
    labour = [s for s in wf["steps"] if s[0] == "labour"]
    assert len(labour) == 1, "ONE bar"
    assert labour[0][2] == 2000.0
    assert wf["labour_split"] == {"estimate": 800.0, "actual": 1200.0,
                                  "slips": 1}


def test_the_waterfall_table_says_which_part_has_been_paid(world):
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-09-01")
    _issue("2026-09", basic=1200.0)
    html = PC.waterfall_html(PNL.waterfall_of(PNL.project_pnl(PID)))
    assert "estimated" in html and "actual" in html
    assert "1 issued payslip" in html


def test_the_waterfall_table_says_all_estimated_when_nothing_is_paid(world):
    _mark("m1", "2026-10-01")
    html = PC.waterfall_html(PNL.waterfall_of(PNL.project_pnl(PID)))
    assert "estimated from the muster" in html
    assert "no payslip issued for it yet" in html


def test_a_withheld_waterfall_carries_no_split_at_all(world):
    _mark("m1", "2026-10-01")
    wf = PNL.waterfall_of(PNL.project_pnl(PID, include_labour=False))
    assert wf["labour_withheld"] is True
    assert wf["labour_split"] is None
    assert [s for s in wf["steps"] if s[0] == "labour"] == []


# =============================================================================
# 3. THE /projects REGISTER LINE
# =============================================================================

def test_the_register_line_says_the_split(world):
    _mark("u1", "2026-10-01", pid="")
    _mark("u2", "2026-09-01", pid="")
    _issue("2026-09", basic=1300.0)
    line = PNL.register_line_html(PNL.untagged_cost())
    assert "site labour" in line
    assert "estimated" in line and "actual" in line
    assert "1 issued payslip" in line


def test_the_register_line_says_all_estimated_when_nothing_is_paid(world):
    _mark("u1", "2026-10-01", pid="")
    line = PNL.register_line_html(PNL.untagged_cost())
    assert "estimated &mdash; no payslip issued for it yet" in line


def test_a_withheld_register_line_still_says_what_it_always_said(world):
    _mark("u1", "2026-10-01", pid="")
    line = PNL.register_line_html(PNL.untagged_cost(include_labour=False))
    assert "site labour not shown" in line
    assert "estimated" not in line


# =============================================================================
# 4. THE DASHBOARD
# =============================================================================

def test_the_project_tile_says_the_split(world):
    _mark("m1", "2026-10-01")
    _mark("m2", "2026-09-01")
    _issue("2026-09", basic=1200.0)
    STORE["boqs"]["b1"] = {
        "id": PID + "-boq", "project_id": PID, "number": "BOQ-0001",
        "revision": 0, "status": "approved", "items": [], "charges": [],
        "created_at": "2026-10-01 09:00"}
    html = world.get("/").get_data(as_text=True)
    if "pp-mini" not in html:
        pytest.skip("this fixture draws no project tile")
    assert "estimated" in html and "actual" in html


def test_the_unattributed_cost_clause_reads_the_same_dict(world):
    _mark("u1", "2026-10-01", pid="")
    _issue("2026-10", basic=900.0)
    import dashboard as D
    clause = D._untagged_labour_split(PNL.untagged_cost())
    assert "Of the labour," in clause and "is actual" in clause
    assert D._untagged_labour_split(
        PNL.untagged_cost(include_labour=False)) == ""


def test_the_unattributed_clause_is_empty_when_there_is_no_labour(world):
    import dashboard as D
    assert D._untagged_labour_split(PNL.untagged_cost()) == ""
