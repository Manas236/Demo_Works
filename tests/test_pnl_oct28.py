"""
THE PROFIT AND LOSS, ONE CLICK AWAY — §0 **fifty-eighth** block, item 4.

CC-2's **C6** was built on 8 October 2026 (the forty-seventh block) and this
**extends** it; it does not rebuild it. What already existed and is untouched:
the three sections that never mix, the planned figures from each chain's TIP
revision, billed (RA bills plus tax invoices through `project_of()`, with the
merged RA counted as a note and never as money), the committed-PO / work-order
/ charge / labour cost rows, the margin to date, the estimate-against-actual
cost variance, the cash section (billed, received, written off, outstanding)
and the amber band for a bill raised under an earlier revision.

**What this pass adds, and what each new test is for:**

1. **COVERAGE** — `pnl.po_coverage()`: *"N of M priced BOQ lines have a
   committed purchase order."* ⚠ **The reason it exists**: the margin to date
   is billed-so-far less spent-so-far, so early in a job almost nothing has
   been bought and the panel shows a handsome margin that is really a project
   nobody has started buying for. Coverage is the sentence that says which it
   is.
2. **PLANNED MARGIN AGAINST ACTUAL** — a second difference beside the cost
   variance, never a replacement for it.
3. **COST TAGGED TO NO PROJECT, ON THE PROJECT'S OWN PAGE.** It was under the
   `/projects` register only, and a reader who opens a project from the
   dashboard never sees the register — so this project's cost read as the
   whole company's. ⚠ It is **not** this project's money and nothing adds it.
4. **ONE CLICK** — a P&L link per project on the dashboard and the register,
   both gated by the existing `project.pnl`.
"""

import pytest

import pnl as PNL
from store import STORE


_OWNED = ("projects", "boqs", "purchases", "ra_bills", "invoices",
          "proformas", "work_orders", "charges", "attendance", "receipts")

PID = "p1"


@pytest.fixture()
def world(client):
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["projects"][PID] = {
        "id": PID, "name": "Jamnagar", "norm_name": "jamnagar",
        "client": "IOCL", "notes": "", "site_address_id": "",
        "site_address": "", "created_at": "2026-10-01 09:00",
        "updated_at": "2026-10-01 09:00"}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


# ⚠ **A line id must match `boq._LINE_ID_RE` — `^[0-9a-f]{12}$`.** A
#   malformed one is treated as ABSENT (`boq._line_id()`: *"a browser that
#   sent something this shape does not match is a browser whose id we have no
#   reason to believe"*), so fixtures using "L1" measured a coverage of 0 of 0
#   and proved nothing. Measured: that is exactly what happened on the first
#   run of this file.
L1 = "aaaaaaaaaaaa"
L2 = "bbbbbbbbbbbb"


def _line(lid, qty="10", sup_rate="100", sup_base="60"):
    return {"line_id": lid, "item_no": "1", "is_header": False,
            "description": "Pipe", "unit": "Mtrs", "total_qty": qty,
            "supply_rate": sup_rate, "supply_base_rate": sup_base,
            "supply_escalation_pct": "0", "supply_discount_pct": "",
            "install_rate": "", "install_base_rate": "",
            "install_escalation_pct": "", "install_discount_pct": ""}


def _boq(bid="b1", pid=PID, lines=None, rev_no=0, supersedes="",
         ref="SF/BOQ/26-27/0019"):
    STORE["boqs"][bid] = {
        "id": bid, "ref": ref, "rev_no": rev_no, "supersedes": supersedes,
        "date": "2026-10-01", "project_id": pid,
        "line_items": lines if lines is not None else [_line(L1), _line(L2)],
        "subtotal": 2000.0, "supply_subtotal": 2000.0, "install_subtotal": 0.0}
    return STORE["boqs"][bid]


def _po(poid="po1", pid=PID, status="Issued", line_ids=(L1,), taxable=600.0,
        boq_id=""):
    STORE["purchases"][poid] = {
        "id": poid, "ref": f"SF/PO/26-27/{poid}", "date": "2026-10-12",
        "status": status, "vendor_name": "Acme", "project_id": pid,
        "boq_id": boq_id, "taxable_value": taxable, "subtotal": taxable,
        "grand_total": taxable * 1.18, "charges": [],
        "items": [{"line_id": lid, "description": "Pipe", "qty": 10,
                   "rate": 60} for lid in line_ids]}
    return STORE["purchases"][poid]


def _ra(rid="r1", pid_boq="b1", claim=1000.0, grand=1180.0, status="issued",
        leg="supply", ra_no=1):
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/000{ra_no}", "ra_no": ra_no,
        "date": "2026-10-15", "boq_id": pid_boq, "leg": leg, "status": status,
        "claim_subtotal": claim, "grand_total": grand, "claims": [],
        "tax_invoice_ref": "", "deduction_total": 0.0,
        "net_payable": claim, "tax_amount": grand - claim}
    return STORE["ra_bills"][rid]


def _panel(client, pid=PID) -> str:
    r = client.get(f"/projects/view/{pid}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '<div class="panel pnl" id="pnl">' in html, "no P&L panel"
    return html.split('<div class="panel pnl" id="pnl">', 1)[1]


# =============================================================================
# WHAT ALREADY EXISTED IS STILL THERE — the regression guard on the extension
# =============================================================================

def test_the_three_sections_still_never_mix(world):
    """
    ABOUT.md §7 gap 31: a tax-exclusive figure beside a tax-inclusive one. The
    new rows go INSIDE the tax-exclusive section and the cash section keeps its
    own heading, which still says GST is included.
    """
    _boq()
    seg = _panel(world)
    assert "tax-exclusive</span>" in seg
    assert "GST included</span>" in seg
    i_todate = seg.index("To date <span>")
    i_cash = seg.index("<h3>Cash <span>")
    assert i_todate < seg.index("Planned margin against actual") < i_cash, (
        "the new difference must sit in the tax-EXCLUSIVE section, not beside "
        "the GST-inclusive cash figures")


def test_the_existing_cost_variance_is_still_there(world):
    """A second difference was ADDED beside it; it did not replace it."""
    _boq()
    seg = _panel(world)
    assert "Estimate against actual." in seg
    assert "Planned margin against actual." in seg


def test_collected_and_outstanding_are_still_the_cash_section(world):
    _boq()
    _ra()
    seg = _panel(world)
    assert "<th>Received</th>" in seg
    assert "<th>Outstanding</th>" in seg


# =============================================================================
# 1. COVERAGE
# =============================================================================

def test_coverage_counts_priced_lines_with_a_committed_order(world):
    _boq()                              # two priced lines, L1 and L2
    _po(line_ids=(L1,))
    cov = PNL.po_coverage(PID)
    assert (cov["lines"], cov["covered"], cov["orders"]) == (2, 1, 1)
    assert cov["pct"] == 50.0
    seg = _panel(world)
    # The verb agrees with the COUNT COVERED, which is the subject: "1 … has",
    # "2 … have".
    assert "1 of 2 priced BOQ lines has a committed purchase order" in seg
    assert "(50.00%)" in seg


def test_COVERAGE_SAYS_A_LOW_COST_MAY_NOT_BE_A_PROFIT(world):
    """
    THE ASSERTION THAT MATTERS MOST. The whole reason coverage exists: a job
    that has billed and bought nothing shows a flattering margin, and the page
    has to say so rather than leave it to be inferred.
    """
    _boq()
    _ra(claim=1000.0)                   # billed, nothing bought
    seg = _panel(world)
    assert "0 of 2 priced BOQ lines have a committed purchase order" in seg
    assert "has not been bought yet" in seg
    assert "a healthy margin here may simply be a job nobody has started buying for" in seg


def test_a_DRAFT_order_covers_nothing(world):
    """`COMMITTED_PO_STATUSES`, the same tuple the cost row reads, so the two
    cannot disagree about what an order is."""
    _boq()
    _po(status="Draft", line_ids=(L1, L2))
    assert PNL.po_coverage(PID)["covered"] == 0
    assert PNL.po_coverage(PID)["orders"] == 0


def test_a_CANCELLED_order_covers_nothing(world):
    _boq()
    _po(status="Cancelled", line_ids=(L1, L2))
    assert PNL.po_coverage(PID)["covered"] == 0


@pytest.mark.parametrize("status", ["Issued", "Acknowledged",
                                    "Partially Received", "Received"])
def test_every_committed_status_covers(world, status):
    _boq()
    _po(status=status, line_ids=(L1,))
    assert PNL.po_coverage(PID)["covered"] == 1


def test_an_EXTRA_PART_carries_no_line_id_and_is_reported_not_dropped(world):
    """
    `purchase.py`'s rule, held from this side: *"an extra line carries NO
    `line_id` and must never be given one."* It covers nothing and lands in
    `unmatched`.
    """
    _boq()
    po = _po(line_ids=(L1,))
    po["items"].append({"description": "Extra clamp", "qty": 5, "rate": 30})
    cov = PNL.po_coverage(PID)
    assert (cov["covered"], cov["unmatched"]) == (1, 1)
    assert "1 order line matches no priced line on the latest revision" in _panel(world)


def test_a_line_a_REVISION_removed_is_not_covered(world):
    """
    The plan is the TIP and the tip has no such line, so an order against
    Rev 0 naming it is `unmatched`. The honest answer, and the same reading
    `tips_of()` gives the planned figures.
    """
    _boq("b1", lines=[_line(L1), _line(L2)])
    _boq("b2", rev_no=1, supersedes="b1", lines=[_line(L1)],
         ref="SF/BOQ/26-27/0020")
    _po(line_ids=(L1, L2))
    cov = PNL.po_coverage(PID)
    assert cov["lines"] == 1, "the tip has one line"
    assert (cov["covered"], cov["unmatched"]) == (1, 1)


def test_an_UNPRICED_line_is_not_in_the_denominator(world):
    """The population is `plan_of()`'s `priced` — a line billed on at least
    one track. An unpriced line is not a line anybody buys against."""
    _boq(lines=[_line(L1), _line(L2, sup_rate="", sup_base="")])
    assert PNL.po_coverage(PID)["lines"] == 1


def test_no_schedule_says_so_rather_than_showing_nil_coverage(world):
    """0 of 0 is not a statement about anything."""
    cov = PNL.po_coverage(PID)
    assert (cov["lines"], cov["pct"]) == (0, None)
    assert "no BOQ lines to say how much of this job has been bought" in _panel(world)


def test_coverage_reads_project_of_so_a_boq_derived_order_counts(world):
    """An order raised from the BOQ carries no `project_id` of its own once
    the BOQ moved; `project_of()` is the one reader and coverage uses it."""
    _boq()
    _po(pid="", boq_id="b1", line_ids=(L1,))
    assert PNL.po_coverage(PID)["covered"] == 1


def test_nothing_is_derived_from_coverage(world):
    """It is a count of lines printed beside the money, never a correction to
    it. Changing coverage must move no figure."""
    _boq()
    before = PNL.project_pnl(PID)
    _po(line_ids=(L1, L2))
    after = PNL.project_pnl(PID)
    assert after["coverage"]["covered"] == 2
    assert before["planned"] == after["planned"]
    assert before["to_date"]["billed"] == after["to_date"]["billed"]


# =============================================================================
# 2. PLANNED MARGIN AGAINST ACTUAL
# =============================================================================

def test_the_margin_variance_is_a_difference_between_two_rounded_totals(world):
    """
    Planned: 2 lines x 10 x (100 - 60) = 800 margin. Billed 1,000, spent 600,
    so the margin to date is 400 — 400 behind the plan.
    """
    _boq()
    _ra(claim=1000.0)
    _po(taxable=600.0)
    r = PNL.project_pnl(PID)
    assert r["planned"]["margin"] == 800.0
    assert r["to_date"]["margin"] == 400.0
    assert r["to_date"]["margin_variance"] == -400.0
    seg = _panel(world)
    assert "behind the plan by" in seg
    assert "This is timing as much as result" in seg


def test_ahead_of_the_plan_is_worded_as_such(world):
    _boq()
    _ra(claim=2000.0)
    r = PNL.project_pnl(PID)
    assert r["to_date"]["margin_variance"] == 1200.0
    assert "ahead of the plan by" in _panel(world)


def test_no_plan_means_no_margin_variance_rather_than_zero(world):
    """`_stored()`'s rule across this module: None, never 0.0 — a 0 would be
    a statement the data never made."""
    _ra(claim=1000.0)
    assert PNL.project_pnl(PID)["to_date"]["margin_variance"] is None
    assert "no planned margin to set the margin to date against" in _panel(world)


def test_the_estimate_and_the_actual_are_never_blended(world):
    """Two figures and a difference, which is what the forty-seventh block
    built and what this one keeps."""
    _boq()
    _po(taxable=600.0)
    r = PNL.project_pnl(PID)["to_date"]
    # Planned cost is 2 lines x 10 qty x 60 base = 1,200 (the MARGIN is 800:
    # revenue 2,000 less cost 1,200). Estimate less actual cost = 600.
    assert r["variance"] == 1200.0 - 600.0, "estimate less actual cost"
    seg = _panel(world)
    assert "not yet spent of the estimate" in seg


def test_the_variance_says_it_excludes_labour_when_wages_are_withheld(world,
                                                                      monkeypatch):
    _boq()
    _ra(claim=1000.0)
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "attendance.view" else real(p))
    assert "(excluding site labour)" in _panel(world)


# =============================================================================
# 3. COST TAGGED TO NO PROJECT, ON THE PROJECT PAGE
# =============================================================================

def test_the_untagged_cost_is_on_the_project_page_too(world):
    _boq()
    _po("po-loose", pid="", taxable=7777.0)
    seg = _panel(world)
    assert "Cost tagged to no project at all" in seg
    assert "7,777.00" in seg


def test_IT_IS_NOT_THIS_PROJECTS_MONEY_AND_NOTHING_ADDS_IT(world):
    """
    THE ASSERTION THAT MATTERS MOST for this section. It is shown because a
    project page read on its own otherwise looks like the whole picture — not
    because it belongs to this project.
    """
    _boq()
    _po("po-mine", pid=PID, taxable=600.0)
    before = PNL.project_pnl(PID)["to_date"]["actual"]
    _po("po-loose", pid="", taxable=9999.0)
    after = PNL.project_pnl(PID)["to_date"]["actual"]
    assert before == after == 600.0, (
        f"untagged cost leaked into this project's actual cost: "
        f"{before} -> {after}")
    seg = _panel(world)
    assert "not this project&rsquo;s cost and nothing above includes it" in seg


def test_it_is_the_same_function_the_register_line_uses(world):
    _po("po-loose", pid="", taxable=4242.0)
    assert PNL.project_pnl(PID)["untagged"] == PNL.untagged_cost()
    assert "4,242.00" in PNL.register_line_html(PNL.untagged_cost())


def test_the_band_is_absent_when_everything_is_tagged(world):
    _boq()
    _po(pid=PID)
    assert "Cost tagged to no project at all" not in _panel(world)


def test_a_dangling_project_id_is_named_on_the_band(world):
    _boq()
    _po("po-gone", pid="p-deleted", taxable=500.0)
    seg = _panel(world)
    assert "Cost tagged to no project at all" in seg
    assert "a project that no longer exists" in seg


# =============================================================================
# 4. ONE CLICK
# =============================================================================

def test_the_register_carries_a_pnl_link_per_project(world):
    html = world.get("/projects/").get_data(as_text=True)
    assert f'href="/projects/view/{PID}#pnl"' in html
    assert "P&amp;L</a>" in html


def test_the_dashboard_carries_a_pnl_link_per_project(world):
    _boq()
    _ra(claim=1000.0)
    html = world.get("/").get_data(as_text=True)
    assert 'class="pp-pnl"' in html
    assert f'href="/projects/view/{PID}#pnl"' in html


def test_both_links_are_gated_by_project_pnl(world, monkeypatch):
    """The panel's own permission. A link to a panel the reader may not see is
    a link to nothing."""
    _boq()
    _ra(claim=1000.0)
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "project.pnl" else real(p))
    assert "#pnl" not in world.get("/projects/").get_data(as_text=True)
    assert 'class="pp-pnl"' not in world.get("/").get_data(as_text=True)


def test_the_unassigned_dashboard_row_gets_no_link(world):
    """It has no project to open. `_project_progress()` gives it a row and no
    `pid`, deliberately, and a link would 404."""
    _boq(pid="")
    _ra(claim=1000.0)
    html = world.get("/").get_data(as_text=True)
    assert "Unassigned" in html
    assert 'class="pp-pnl"' not in html


def test_the_panel_is_still_only_owner_and_director(world, monkeypatch):
    """The forty-seventh block's access rule is untouched by this pass."""
    _boq()
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "project.pnl" else real(p))
    html = world.get(f"/projects/view/{PID}").get_data(as_text=True)
    assert '<div class="panel pnl" id="pnl">' not in html
