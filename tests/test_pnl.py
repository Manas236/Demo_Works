"""
CC-2 **C6** — the project profit and loss, asserted to the paisa.

CLIENT_CHANGES.md §0, forty-seventh block (8 October 2026). Every figure is
derived by `pnl.py` and rendered by `projectview._pnl_panel()`; nothing is
stored. This file builds ONE synthetic project carrying every source the panel
reads — two BOQ revisions, issued / draft / cancelled RA bills, a merged RA, tax
invoices through a proforma, committed / Draft / Cancelled / pre-A3 purchase
orders, a draft PO sent for pricing, issued and draft work orders, charges and
attendance markings with and without a project — and asserts each row against a
constant worked out BY HAND below, never against the module's own arithmetic.

### The synthetic project, worked by hand

PLANNED — the tip is `pnl-b1` (Rev 1, 2026-09-15); `pnl-b0` (Rev 0) is NOT read.

    line  qty   supply rate/disc/base   install rate/base   revenue   cost
    L1    10    1000 / – / 800          300 / 200            13,000    10,000
    L2     5    2000 / 10% / 1500       – / –                 9,000     7,500
    L3     4     500 / – / –  (no base) – / –                 2,000         –   no_base
    L4     –     100 / – / 80           – / –                     –         –   no_qty
    L5     3       – / – / 50           – / –                     –         –   no_rate, base on an unpriced track
    L6    (a specification header — no figures)
    L7     2       – / – / –            0 / 100                   0       200   nil-priced, costed
                                                                ------    ------
                                                                24,000    17,700   margin 6,300 = 26.25%

    priced (a track billed above 0): L1 L2 L3 L4 = 4;  no base rate on a billed
    track: L3 = 1 → "1 of 4 priced lines has no base rate".

TO DATE — tax-exclusive

    RA bills issued   RA1 50,000 (on Rev 0) + RA2 30,000 + RA3 10,000  = 90,000
                      RA4 draft 7,777 and RA5 cancelled 8,888 are OUT
    Tax invoices      TI1 20,000; TI2 cancelled OUT; TI3 carries RA2's number
                      (SF/TI/26-27/0042) and is the same billing — OUT       = 20,000
    Billed                                                                  110,000
    Purchase orders   PO1 Issued 12,000 + PO2 Received 3,000 + PO7 Partially
                      Received, pre-A3, subtotal 1,000; PO3 Draft and PO4
                      Cancelled OUT                                          = 16,000
    PO charges outside the tax base   PO2's freight                          =    500
    Work orders       WO1 issued: 10 × (100 + 50) = 1,500; WO2 draft OUT     =  1,500
    Charges           C1 2,000 + C2 500                                      =  2,500
    Site labour       M1 present, 1,000 + (1,000 ÷ 8) × 2 × 1 = 1,250;
                      M2 absent 0; M3 predates the day rate — REFUSED         =  1,250
    Spent                                                                    21,750
    Margin to date    110,000 − 21,750                                       88,250
    Estimate − actual 17,700 − 21,750                                        −4,050

CASH — GST included

    Billed incl. GST  59,000 + 35,400 + 11,800                              106,200
    Received          40,000 (RA1) + 35,400 (RA2)                            75,400
    Written off       RA1, allowed short                                      1,000
    Outstanding       106,200 − 75,400 − 1,000                               29,800
    Tax invoices incl. GST, not in the outstanding                           23,600

UNTAGGED — the register's line

    PO5 Issued, no project 2,500 + PO6 Acknowledged, deleted project 600  =   3,100
    WO3 issued, no project: 2 × 400                                       =     800
    C3 no project                                                         =     700
    M4 no project, present, 800                                           =     800
                                                                              5,400   (1 dangling)
"""

import copy
import re

import pytest

import pnl as PNL
from quotation import _inr
from store import STORE

PID = "pnl-p"
OTHER = "pnl-other"
GONE = "pnl-gone"                    # a project id that names no project

# ── The hand-worked figures ────────────────────────────────────────────────
PLAN_REVENUE = 24000.00
PLAN_COST = 17700.00
PLAN_MARGIN = 6300.00
PLAN_PCT = 26.25
RA_TAXABLE = 90000.00
TI_TAXABLE = 20000.00
BILLED = 110000.00
PO_TAXABLE = 16000.00
PO_EXEMPT = 500.00
WO_GRAND = 1500.00
CHARGES = 2500.00
LABOUR = 1250.00
ACTUAL = 21750.00
MARGIN_TO_DATE = 88250.00
VARIANCE = -4050.00
CASH_BILLED = 106200.00
CASH_RECEIVED = 75400.00
CASH_WRITTEN_OFF = 1000.00
CASH_OUTSTANDING = 29800.00
TI_INCL_GST = 23600.00
UNTAGGED = 5400.00

# The collections `conftest.client` deliberately does NOT clear between tests.
_KEPT = ("projects", "ra_bills", "receipts", "purchase_orders", "work_orders",
         "charges", "attendance", "employees")


def _line(lid, **kw):
    li = {"line_id": lid, "item_no": lid[-1], "section": "A", "description":
          f"Line {lid}", "unit": "Nos", "is_header": False, "total_qty": None,
          "supply_rate": None, "supply_base_rate": None,
          "install_rate": None, "install_base_rate": None}
    li.update(kw)
    return li


def _boq(bid, rev, supersedes, project, ref, date, lines):
    return {"id": bid, "ref": ref, "date": date, "rev_no": rev,
            "supersedes": supersedes, "project_id": project,
            "project_name": "Ridge Logistics", "account_name": "Ridge Logistics Pvt Ltd",
            "blank_model": "as_is", "sections": [{"code": "A", "title": "Sprinklers",
                                                  "areas": []}],
            "line_items": lines, "subtotal": 0.0}


def _bill(rid, boq_id, ra_no, ref, status, taxable, grand, leg="supply",
          tax_ref="", boq_ref="", rev=1):
    return {"id": rid, "boq_id": boq_id, "boq_ref": boq_ref, "boq_rev_no": rev,
            "ra_no": ra_no, "ref": ref, "leg": leg, "status": status,
            "claim_subtotal": taxable, "deduction_total": 0.0,
            "net_payable": taxable, "tax_amount": round(grand - taxable, 2),
            "grand_total": grand, "tax_invoice_ref": tax_ref, "claims": []}


def _po(pid_, project, status, **kw):
    po = {"id": pid_, "ref": f"SF/PO/26-27/{pid_[-2:]}", "date": "2026-09-20",
          "vendor_name": "Shah Pipes", "project_id": project, "status": status}
    po.update(kw)
    return po


def _wo(wid, project, status, qty, mat, lab):
    return {"id": wid, "ref": f"SF/WO/{wid[-2:]}", "project_id": project,
            "status": status, "tracks": "both", "gst_rate": 18.0,
            "contractor_name": "K. Patil", "lines": [
                {"line_id": "aaaaaaaaaaa1", "description": "Pipe laying",
                 "unit": "Mtrs", "qty": qty, "material_rate": mat,
                 "labour_rate": lab}]}


def _mark(mid, project, status, rate, ot=0.0, pre=False, site="pnl-site"):
    m = {"id": mid, "date": "2026-09-25", "employee_id": f"e-{mid}",
         "employee_name": f"Worker {mid}", "employee_code": mid.upper(),
         "day_rate": rate, "site": "Ridge site", "site_address_id": site,
         "site_source": "book", "project_id": project, "project_name": "",
         "status": status, "ot_hours": ot, "notes": ""}
    if pre:
        m.pop("day_rate")
        m["monthly_salary"] = 24000.0
        m["rate_model"] = "pre_day_rate"
    return m


def build_project():
    """Write the synthetic project into STORE. The caller has cleared it."""
    STORE["projects"][PID] = {"id": PID, "name": "Ridge Logistics — Sprinklers",
                              "norm_name": "ridge logistics — sprinklers",
                              "client": "Ridge Logistics Pvt Ltd", "notes": "",
                              "site_address_id": "", "site_address": "",
                              "created_at": "2026-07-01 10:00"}
    STORE["projects"][OTHER] = {"id": OTHER, "name": "Another job",
                                "norm_name": "another job", "client": "",
                                "notes": "", "site_address_id": "",
                                "site_address": "", "created_at": "2026-07-02 10:00"}

    STORE["boqs"]["pnl-b0"] = _boq("pnl-b0", 0, "", PID, "SF/BOQ/26-27/0101",
                                   "2026-07-01", [
        _line("pnl-l1", total_qty=8.0, supply_rate=1000.0, supply_base_rate=800.0)])
    STORE["boqs"]["pnl-b1"] = _boq("pnl-b1", 1, "pnl-b0", PID, "SF/BOQ/26-27/0102",
                                   "2026-09-15", [
        _line("pnl-l1", total_qty=10.0, supply_rate=1000.0, supply_base_rate=800.0,
              install_rate=300.0, install_base_rate=200.0),
        _line("pnl-l2", total_qty=5.0, supply_rate=2000.0, supply_disc_pct=10.0,
              supply_base_rate=1500.0),
        _line("pnl-l3", total_qty=4.0, supply_rate=500.0),
        _line("pnl-l4", supply_rate=100.0, supply_base_rate=80.0),
        _line("pnl-l5", total_qty=3.0, supply_base_rate=50.0),
        {"line_id": "pnl-l6", "item_no": "6", "section": "A", "is_header": True,
         "description": "Specification text", "unit": ""},
        _line("pnl-l7", total_qty=2.0, install_rate=0.0, install_base_rate=100.0),
    ])
    STORE["boqs"]["pnl-ob"] = _boq("pnl-ob", 0, "", OTHER, "SF/BOQ/26-27/0199",
                                   "2026-08-01", [
        _line("pnl-o1", total_qty=1.0, supply_rate=99999.0, supply_base_rate=1.0)])

    bills = [
        _bill("pnl-ra1", "pnl-b0", 1, "SF/RA/26-27/0101", "issued", 50000.0, 59000.0,
              tax_ref="SF/RI/26-27/0101", boq_ref="SF/BOQ/26-27/0101", rev=0),
        _bill("pnl-ra2", "pnl-b1", 2, "SF/RA/26-27/0102", "issued", 30000.0, 35400.0,
              tax_ref="SF/TI/26-27/0042", boq_ref="SF/BOQ/26-27/0102"),
        _bill("pnl-ra3", "pnl-b1", 3, "SF/RA/26-27/0103", "issued", 10000.0, 11800.0,
              leg="installation", tax_ref="SF/RI/26-27/0103",
              boq_ref="SF/BOQ/26-27/0102"),
        _bill("pnl-ra4", "pnl-b1", 4, "SF/RA/26-27/0104", "draft", 7777.0, 9177.0,
              boq_ref="SF/BOQ/26-27/0102"),
        _bill("pnl-ra5", "pnl-b1", 5, "SF/RA/26-27/0105", "cancelled", 8888.0, 10488.0,
              boq_ref="SF/BOQ/26-27/0102"),
        _bill("pnl-rao", "pnl-ob", 1, "SF/RA/26-27/0199", "issued", 66666.0, 78666.0,
              boq_ref="SF/BOQ/26-27/0199", rev=0),
    ]
    for b in bills:
        STORE["ra_bills"][b["id"]] = b

    STORE["merged_ras"]["pnl-m1"] = {
        "id": "pnl-m1", "tax_invoice_ref": "SF/MI/26-27/0101", "status": "live",
        "supply_ra_id": "pnl-ra2", "installation_ra_id": "pnl-ra3",
        "supply_ref": "SF/RA/26-27/0102", "installation_ref": "SF/RA/26-27/0103",
        "boq_id": "pnl-b1", "claim_subtotal": 40000.0, "tax_amount": 7200.0,
        "grand_total": 47200.0}

    STORE["receipts"]["pnl-rc1"] = {"id": "pnl-rc1", "ra_id": "pnl-ra1",
                                    "date": "2026-09-30", "amount": 40000.0,
                                    "write_off": 1000.0}
    STORE["receipts"]["pnl-rc2"] = {"id": "pnl-rc2", "ra_id": "pnl-ra2",
                                    "date": "2026-10-01", "amount": 35400.0,
                                    "write_off": 0.0}

    STORE["proformas"]["pnl-pi1"] = {"id": "pnl-pi1", "ref": "PI-0101",
                                     "project_id": PID, "grand_total": 1.0}
    STORE["proformas"]["pnl-pi2"] = {"id": "pnl-pi2", "ref": "PI-0102",
                                     "project_id": OTHER, "grand_total": 1.0}
    STORE["invoices"]["pnl-ti1"] = {"id": "pnl-ti1", "proforma_id": "pnl-pi1",
                                    "ref": "SF/TI/26-27/0041", "date": "2026-09-10",
                                    "subtotal": 20000.0, "grand_total": 23600.0}
    STORE["invoices"]["pnl-ti2"] = {"id": "pnl-ti2", "proforma_id": "pnl-pi1",
                                    "ref": "SF/TI/26-27/0043", "date": "2026-09-11",
                                    "status": "cancelled",
                                    "subtotal": 5000.0, "grand_total": 5900.0}
    STORE["invoices"]["pnl-ti3"] = {"id": "pnl-ti3", "proforma_id": "pnl-pi1",
                                    "ref": "SF/TI/26-27/0042", "date": "2026-09-12",
                                    "subtotal": 30000.0, "grand_total": 35400.0}
    STORE["invoices"]["pnl-ti4"] = {"id": "pnl-ti4", "proforma_id": "pnl-pi2",
                                    "ref": "SF/TI/26-27/0044", "date": "2026-09-13",
                                    "subtotal": 12345.0, "grand_total": 14567.1}

    for po in (
        _po("pnl-po01", PID, "Issued", subtotal=12000.0, taxable_value=12000.0,
            grand_total=14160.0),
        _po("pnl-po02", PID, "Received", subtotal=3000.0, taxable_value=3000.0,
            charges=[{"label": "Freight", "amount": 500.0, "taxable": False}],
            grand_total=4040.0),
        _po("pnl-po03", PID, "Draft", subtotal=9999.0, taxable_value=9999.0,
            grand_total=11798.82),
        _po("pnl-po04", PID, "Cancelled", subtotal=4444.0, taxable_value=4444.0,
            grand_total=5243.92),
        _po("pnl-po05", "", "Issued", subtotal=2500.0, taxable_value=2500.0,
            grand_total=2950.0),
        _po("pnl-po06", GONE, "Acknowledged", subtotal=600.0, taxable_value=600.0,
            grand_total=708.0),
        # Written before A3 (28 August 2026): no `taxable_value`, no charges —
        # ABOUT.md §3: its taxable value IS its subtotal.
        _po("pnl-po07", PID, "Partially Received", subtotal=1000.0,
            grand_total=1180.0),
    ):
        STORE["purchases"][po["id"]] = po

    STORE["purchase_orders"]["pnl-dpo1"] = {"id": "pnl-dpo1", "ref": "DPO-0101",
                                            "boq_id": "pnl-b1", "items": []}

    STORE["work_orders"]["pnl-wo01"] = _wo("pnl-wo01", PID, "issued", 10.0, 100.0, 50.0)
    STORE["work_orders"]["pnl-wo02"] = _wo("pnl-wo02", PID, "draft", 1.0, 999.0, 0.0)
    STORE["work_orders"]["pnl-wo03"] = _wo("pnl-wo03", "", "issued", 2.0, 400.0, 0.0)

    for cid, project, taxable, gst in (("pnl-c1", PID, 2000.0, 360.0),
                                       ("pnl-c2", PID, 500.0, 0.0),
                                       ("pnl-c3", "", 700.0, 126.0)):
        STORE["charges"][cid] = {"id": cid, "date": "2026-09-20",
                                 "person": "R. Kadam", "head": "Travel",
                                 "description": "Site visit", "project_id": project,
                                 "taxable_amount": taxable, "gst_amount": gst,
                                 "created_at": "2026-09-20 10:00"}

    for m in (_mark("m1", PID, "present", 1000.0, ot=2.0),
              _mark("m2", PID, "absent", 800.0),
              _mark("m3", PID, "present", 0.0, pre=True),
              _mark("m4", "", "present", 800.0)):
        STORE["attendance"][m["id"]] = m


@pytest.fixture()
def project(client):
    """The synthetic project, over a store with nothing else in the
    collections the panel reads; everything put back afterwards."""
    saved = {k: copy.deepcopy(STORE.get(k) or {}) for k in _KEPT}
    saved_labour = copy.deepcopy((STORE.get("settings") or {}).get("labour_cost"))
    for k in _KEPT:
        STORE.setdefault(k, {}).clear()
    # The OT multiplier at the client's own figure, 1x (settings.LABOUR_DEFAULTS).
    STORE.setdefault("settings", {}).pop("labour_cost", None)
    build_project()
    yield PID
    for k, v in saved.items():
        STORE[k].clear()
        STORE[k].update(v)
    if saved_labour is None:
        STORE["settings"].pop("labour_cost", None)
    else:
        STORE["settings"]["labour_cost"] = saved_labour


def _panel(html: str) -> str:
    """The Profit & Loss panel's own markup, cut out of the page."""
    start = html.index('<div class="panel pnl" id="pnl">')
    end = html.index("<!-- BOQs Panel -->", start)
    return html[start:end]


def _cell(v) -> str:
    """A figure as it sits in a table cell — bounded by the tag either side, so
    `1,000.00` is never found inside `21,000.00`."""
    return f">{_inr(v)}<"


def _text(html: str) -> str:
    """What a reader sees: stylesheets and tags gone, entities decoded."""
    import html as _h
    html = re.sub(r"(?is)<style\b.*?</style>", " ", html)
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"(?s)<[^>]+>", " ", html)))


def _page(client) -> str:
    r = client.get(f"/projects/view/{PID}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ══ 1. PLANNED — from the tip revision, to the paisa ═══════════════════════

def test_the_plan_is_read_from_the_tip_revision_to_the_paisa(project):
    p = PNL.project_pnl(PID)["planned"]
    assert [t["boq_id"] for t in p["tips"]] == ["pnl-b1"]
    tip = p["tips"][0]
    assert (tip["ref"], tip["rev_no"], tip["date"]) == \
        ("SF/BOQ/26-27/0102", 1, "2026-09-15")
    assert (p["revenue"], p["cost"], p["margin"], p["margin_pct"]) == \
        (PLAN_REVENUE, PLAN_COST, PLAN_MARGIN, PLAN_PCT)


def test_an_earlier_revision_is_never_planned(project):
    """Rev 0's own line is 8 × 1,000. Repricing Rev 0 moves nothing; repricing
    the tip moves the plan by exactly the tip's arithmetic."""
    STORE["boqs"]["pnl-b0"]["line_items"][0]["supply_rate"] = 99999.0
    assert PNL.project_pnl(PID)["planned"]["revenue"] == PLAN_REVENUE
    STORE["boqs"]["pnl-b1"]["line_items"][0]["supply_rate"] = 1100.0  # +100 × 10
    assert PNL.project_pnl(PID)["planned"]["revenue"] == PLAN_REVENUE + 1000.0


def test_the_plan_is_derived_at_every_read_never_snapshotted(project, client):
    """A revision raised after the page was opened is the plan the next time —
    nothing was frozen by the first read."""
    _page(client)
    rev2 = copy.deepcopy(STORE["boqs"]["pnl-b1"])
    rev2.update(id="pnl-b2", rev_no=2, supersedes="pnl-b1",
                ref="SF/BOQ/26-27/0103", date="2026-10-05")
    rev2["line_items"][0]["total_qty"] = 20.0      # L1: +13,000 revenue, +10,000 cost
    STORE["boqs"]["pnl-b2"] = rev2
    p = PNL.project_pnl(PID)["planned"]
    assert [(t["ref"], t["rev_no"]) for t in p["tips"]] == [("SF/BOQ/26-27/0103", 2)]
    assert (p["revenue"], p["cost"]) == (PLAN_REVENUE + 13000.0, PLAN_COST + 10000.0)
    assert "SF/BOQ/26-27/0103" in _panel(_page(client))


def test_the_coverage_is_counted_and_said_beside_the_margin(project, client):
    p = PNL.project_pnl(PID)["planned"]
    assert (p["priced"], p["no_base"], p["no_rate"], p["no_qty"],
            p["base_on_unpriced"]) == (4, 1, 1, 1, 1)
    text = _text(_panel(_page(client)))
    assert "1 of 4 priced lines has no base rate" in text
    assert "the planned margin overstated" in text
    assert "1 line has no rate, 1 line has no quantity" in text
    assert "never read as 0" in text
    assert "1 base rate sits on a track with no selling rate" in text


def test_a_blank_rate_or_quantity_is_skipped_and_never_read_as_zero(project):
    """
    L5 carries a base of 50 on 3 units and NO rate. Read as a rate of 0 it
    would be priced at nil and cost 150, and the estimate would read 17,850.
    L4 has a rate and NO quantity; read as 0 it would leave the count.
    Each control types the 0 the blank must never be mistaken for.
    """
    p = PNL.project_pnl(PID)["planned"]
    assert p["cost"] == PLAN_COST and p["no_rate"] == 1 and p["no_qty"] == 1

    STORE["boqs"]["pnl-b1"]["line_items"][4]["supply_rate"] = 0.0     # L5: a typed 0
    q = PNL.project_pnl(PID)["planned"]
    assert (q["cost"], q["no_rate"], q["base_on_unpriced"]) == (PLAN_COST + 150.0, 0, 0)

    STORE["boqs"]["pnl-b1"]["line_items"][3]["total_qty"] = 0.0       # L4: a typed 0
    r = PNL.project_pnl(PID)["planned"]
    assert (r["no_qty"], r["revenue"]) == (0, PLAN_REVENUE)


def test_a_missing_base_rate_is_not_a_cost_of_zero(project):
    """L3 is billed at 500 × 4 = 2,000 with no base. Its revenue is in, its cost
    is NOT RECORDED — counted, never a zero. Give it a base and both move."""
    STORE["boqs"]["pnl-b1"]["line_items"][2]["supply_base_rate"] = 400.0
    p = PNL.project_pnl(PID)["planned"]
    assert (p["cost"], p["no_base"], p["revenue"]) == \
        (PLAN_COST + 1600.0, 0, PLAN_REVENUE)


def test_a_plan_with_no_revenue_has_no_percentage(project, client):
    for li in STORE["boqs"]["pnl-b1"]["line_items"]:
        for k in ("supply_rate", "install_rate"):
            if k in li:
                li[k] = None
    p = PNL.project_pnl(PID)["planned"]
    assert (p["revenue"], p["margin_pct"]) == (0.0, None)
    assert "no planned revenue to take a percentage of" in _text(_panel(_page(client)))


def test_a_project_with_no_schedule_has_no_plan_and_says_so(project, client):
    for bid in ("pnl-b0", "pnl-b1"):
        STORE["boqs"][bid]["project_id"] = ""
    r = PNL.project_pnl(PID)
    assert r["planned"]["tips"] == [] and r["planned"]["revenue"] is None
    assert r["to_date"]["variance"] is None
    # The RA bills went with their schedules, so billed is the tax invoices
    # alone — and TI3 COUNTS now: the RA bill whose number it shared is no
    # longer this project's, so on this project it is no longer a duplicate.
    assert r["to_date"]["ra"]["amount"] == 0.0
    assert r["to_date"]["billed"] == TI_TAXABLE + 30000.0
    assert r["same_number"] == []
    text = _text(_panel(_page(client)))
    assert "No schedule is attached to this project" in text
    assert "there is no estimate to set the cost spent against" in text


def test_totals_round_once_half_up_to_the_paisa(project):
    """
    3 × 0.835 is 2.505 on paper and 2.50499999… in binary. The line's product
    is the BOQ's own (`boq.amount_of()`, unrounded) and the TOTAL rounds once,
    half up, to Excel's 2.51 — never Python's binary 2.50 (ABOUT.md §7 gap 62).
    """
    STORE["boqs"]["pnl-b1"]["line_items"] = [
        _line("pnl-r1", total_qty=3.0, supply_rate=0.835, supply_base_rate=0.835)]
    p = PNL.project_pnl(PID)["planned"]
    assert (p["revenue"], p["cost"]) == (2.51, 2.51)
    assert f"{3 * 0.835:.2f}" == "2.50", "the binary product no longer rounds down"


# ══ 2. TO DATE — billed ═════════════════════════════════════════════════════

def test_billed_revenue_is_the_issued_bills_stored_taxable_value(project):
    t = PNL.project_pnl(PID)["to_date"]
    assert t["ra"] == {"amount": RA_TAXABLE, "count": 3, "no_figure": 0}
    assert t["ti"] == {"amount": TI_TAXABLE, "count": 1, "no_figure": 0}
    assert t["billed"] == BILLED


def test_a_bill_is_read_off_its_own_record_never_off_the_boq(project):
    """The snapshot rule: every live rate times ten, and billed does not move."""
    for li in STORE["boqs"]["pnl-b1"]["line_items"]:
        if li.get("supply_rate"):
            li["supply_rate"] *= 10
    assert PNL.project_pnl(PID)["to_date"]["billed"] == BILLED


@pytest.mark.parametrize("rid, amount, key", [
    ("pnl-ra4", 7777.0, "ra_draft"),
    ("pnl-ra5", 8888.0, "ra_cancelled"),
])
def test_a_draft_or_cancelled_bill_is_not_billed(project, rid, amount, key):
    """Excluded by its STATUS — the control issues the same record and its
    exact figure arrives."""
    r = PNL.project_pnl(PID)
    assert r["to_date"]["ra"]["amount"] == RA_TAXABLE and r["excluded"][key] == 1
    STORE["ra_bills"][rid]["status"] = "issued"
    s = PNL.project_pnl(PID)
    assert s["to_date"]["ra"]["amount"] == RA_TAXABLE + amount
    assert s["excluded"][key] == 0


def test_a_bill_on_another_projects_schedule_is_not_this_projects(project):
    STORE["ra_bills"]["pnl-rao"]["boq_id"] = "pnl-b1"
    assert PNL.project_pnl(PID)["to_date"]["ra"]["amount"] == RA_TAXABLE + 66666.0


def test_a_merged_ra_counts_the_bills_it_stacks_once(project):
    """CC-2 C3: the merged document holds no claims and carries the SUM of its
    two legs' stored totals. Its legs are counted; it is not — in the margin
    section and in the cash section alike."""
    r = PNL.project_pnl(PID)
    assert r["to_date"]["ra"]["amount"] == RA_TAXABLE      # not + 40,000
    assert r["cash"]["billed"] == CASH_BILLED              # not + 47,200
    assert r["merged"] == [{"ref": "SF/MI/26-27/0101",
                            "legs": ["SF/RA/26-27/0102", "SF/RA/26-27/0103"],
                            "grand_total": 47200.0}]
    STORE["merged_ras"]["pnl-m1"]["status"] = "cancelled"
    s = PNL.project_pnl(PID)
    assert (s["to_date"]["billed"], s["cash"]["billed"], s["merged"]) == \
        (BILLED, CASH_BILLED, [])


def test_a_tax_invoice_reaches_the_project_through_its_proforma(project):
    STORE["proformas"]["pnl-pi2"]["project_id"] = PID          # TI4 comes with it
    assert PNL.project_pnl(PID)["to_date"]["ti"]["amount"] == TI_TAXABLE + 12345.0


def test_a_cancelled_tax_invoice_is_not_billed(project):
    r = PNL.project_pnl(PID)
    assert r["excluded"]["ti_cancelled"] == 1
    STORE["invoices"]["pnl-ti2"].pop("status")
    assert PNL.project_pnl(PID)["to_date"]["ti"]["amount"] == TI_TAXABLE + 5000.0


def test_a_tax_invoice_carrying_an_ra_bills_number_is_counted_once(project):
    """
    RA2's `tax_invoice_ref` is `SF/TI/26-27/0042`, typed before the RI series
    existed, and TI3 IS that invoice: one billing on two records. Counted once,
    as the RA bill. The control renumbers TI3 and its 30,000 arrives.
    """
    r = PNL.project_pnl(PID)
    assert r["to_date"]["ti"]["amount"] == TI_TAXABLE
    assert r["same_number"] == [{"ti_ref": "SF/TI/26-27/0042",
                                 "ra_ref": "SF/RA/26-27/0102", "taxable": 30000.0}]
    # The number is compared as it is on paper — case and spacing ignored.
    STORE["ra_bills"]["pnl-ra2"]["tax_invoice_ref"] = "  sf/ti/26-27/0042 "
    assert PNL.project_pnl(PID)["to_date"]["ti"]["amount"] == TI_TAXABLE
    STORE["invoices"]["pnl-ti3"]["ref"] = "SF/TI/26-27/0045"
    s = PNL.project_pnl(PID)
    assert (s["to_date"]["ti"]["amount"], s["same_number"]) == (TI_TAXABLE + 30000.0, [])


def test_only_an_issued_bill_can_swallow_a_tax_invoice(project):
    """A DRAFT RA bill is not billed, so a tax invoice sharing its number must
    be — otherwise the billing is counted zero times instead of twice."""
    STORE["ra_bills"]["pnl-ra2"]["status"] = "draft"
    t = PNL.project_pnl(PID)["to_date"]
    assert t["ra"]["amount"] == RA_TAXABLE - 30000.0
    assert t["ti"]["amount"] == TI_TAXABLE + 30000.0


# ══ 3. TO DATE — spent, one row per source ══════════════════════════════════

def test_purchase_orders_count_in_a_committed_status_at_taxable_value(project):
    r = PNL.project_pnl(PID)
    assert r["to_date"]["po"] == {"amount": PO_TAXABLE, "count": 3, "no_figure": 0}
    assert r["to_date"]["po_exempt"] == {"amount": PO_EXEMPT, "count": 1}
    assert (r["excluded"]["po_draft_status"], r["excluded"]["po_cancelled"]) == (1, 1)
    assert PNL.COMMITTED_PO_STATUSES == ("Issued", "Acknowledged",
                                         "Partially Received", "Received")


@pytest.mark.parametrize("poid, amount", [("pnl-po03", 9999.0), ("pnl-po04", 4444.0)])
def test_a_draft_or_cancelled_purchase_order_is_not_a_cost(project, poid, amount):
    STORE["purchases"][poid]["status"] = "Issued"
    assert PNL.project_pnl(PID)["to_date"]["po"]["amount"] == PO_TAXABLE + amount


def test_an_unrecognised_po_status_is_counted_and_not_costed(project):
    STORE["purchases"]["pnl-po01"]["status"] = "Shipped"
    r = PNL.project_pnl(PID)
    assert r["to_date"]["po"]["amount"] == PO_TAXABLE - 12000.0
    assert r["excluded"]["po_unknown"] == 1


def test_a_po_with_no_status_reads_as_draft_the_way_purchase_py_reads_it(project):
    STORE["purchases"]["pnl-po01"].pop("status")
    r = PNL.project_pnl(PID)
    assert r["to_date"]["po"]["amount"] == PO_TAXABLE - 12000.0
    assert r["excluded"]["po_draft_status"] == 2


def test_an_order_written_before_a3_is_costed_at_its_subtotal_never_its_grand_total(project):
    """PO7 has no `taxable_value` and no charges — ABOUT.md §3: its taxable
    value IS its subtotal, 1,000. Never its GST-inclusive 1,180 (gap 31)."""
    assert PNL.project_pnl(PID)["to_date"]["po"]["amount"] == PO_TAXABLE
    STORE["purchases"]["pnl-po07"].pop("subtotal")
    t = PNL.project_pnl(PID)["to_date"]
    assert (t["po"]["amount"], t["po"]["no_figure"]) == (PO_TAXABLE - 1000.0, 1)


def test_a_draft_po_sent_for_pricing_is_never_a_cost(project):
    """`po_draft.py`'s draft is an intent. Even dressed with figures it is
    counted for the note and priced nowhere."""
    STORE["purchase_orders"]["pnl-dpo1"].update(
        grand_total=50000.0, subtotal=50000.0, taxable_value=50000.0,
        project_id=PID, status="Issued")
    r = PNL.project_pnl(PID)
    assert r["to_date"]["actual"] == ACTUAL and r["excluded"]["po_drafts"] == 1


def test_only_an_issued_work_order_is_a_cost_on_its_own_row_and_before_gst(project):
    r = PNL.project_pnl(PID)
    assert r["to_date"]["wo"] == {"amount": WO_GRAND, "count": 1}
    assert r["excluded"]["wo_draft"] == 1
    # WO1 is 1,770 with its 18% GST; the P&L reads the pre-tax 1,500.
    assert r["to_date"]["actual"] == ACTUAL
    STORE["work_orders"]["pnl-wo02"]["status"] = "issued"
    assert PNL.project_pnl(PID)["to_date"]["wo"]["amount"] == WO_GRAND + 999.0


def test_charges_count_at_their_taxable_amount(project):
    """C1 carries 360 of GST; the P&L reads its taxable 2,000."""
    assert PNL.project_pnl(PID)["to_date"]["charges"] == \
        {"amount": CHARGES, "count": 2, "no_figure": 0}


def test_site_labour_is_attendances_own_arithmetic_on_this_projects_markings(project):
    lab = PNL.project_pnl(PID)["to_date"]["labour"]
    assert lab == {"total": LABOUR, "markings": 3, "costed": 2, "refused": 1,
                   "withheld": False}
    # M4 names no project: not this project's. Tag it, and its 800 arrives.
    STORE["attendance"]["m4"]["project_id"] = PID
    assert PNL.project_pnl(PID)["to_date"]["labour"]["total"] == LABOUR + 800.0


def test_the_overtime_multiplier_is_the_setting(project):
    """M1 at 2x: 1,000 + (1,000 ÷ 8) × 2 × 2 = 1,500."""
    STORE["settings"]["labour_cost"] = {"ot_multiplier": "2"}
    assert PNL.project_pnl(PID)["to_date"]["labour"]["total"] == 1500.0


def test_margin_to_date_and_the_estimate_against_actual(project):
    t = PNL.project_pnl(PID)["to_date"]
    assert (t["actual"], t["margin"], t["variance"]) == \
        (ACTUAL, MARGIN_TO_DATE, VARIANCE)


# ══ 4. CASH — GST included, and never mixed with the margin ═══════════════

def test_the_cash_section_is_the_bills_gst_inclusive_figures(project):
    assert PNL.project_pnl(PID)["cash"] == {
        "billed": CASH_BILLED, "received": CASH_RECEIVED,
        "written_off": CASH_WRITTEN_OFF, "outstanding": CASH_OUTSTANDING,
        "count": 3, "no_figure": 0, "ti_billed": TI_INCL_GST, "ti_count": 1,
        "ti_no_figure": 0}


def test_the_tax_exclusive_and_tax_inclusive_sections_never_mix(project, client):
    """
    ABOUT.md §7 gap 31's shape: a GST-inclusive figure beside a tax-exclusive
    one. Every bill's grand total and the cash totals appear ONLY under Cash;
    every taxable total appears only above it — and each heading says which.
    """
    panel = _panel(_page(client))
    above, cash = panel[:panel.index("<h3>Cash")], panel[panel.index("<h3>Cash"):]
    for incl in (CASH_BILLED, 59000.0, 11800.0, CASH_RECEIVED, CASH_OUTSTANDING):
        assert _cell(incl) not in above, f"{_inr(incl)} (GST-inclusive) above Cash"
    for excl in (RA_TAXABLE, TI_TAXABLE, BILLED, ACTUAL, MARGIN_TO_DATE):
        assert _cell(excl) not in cash, f"{_inr(excl)} (tax-exclusive) under Cash"
    assert "<h3>Cash <span>GST included</span></h3>" in panel
    assert panel.count("tax-exclusive</span></h3>") == 2


# ══ 5. THE PANEL — every row on the page ═══════════════════════════════════

def test_the_panel_shows_every_row_to_the_paisa(project, client):
    panel = _panel(_page(client))
    for v in (PLAN_REVENUE, PLAN_COST, RA_TAXABLE, TI_TAXABLE, BILLED,
              PO_TAXABLE, PO_EXEMPT, WO_GRAND, CHARGES, LABOUR, ACTUAL,
              MARGIN_TO_DATE, CASH_BILLED, CASH_RECEIVED, CASH_WRITTEN_OFF,
              CASH_OUTSTANDING):
        assert _cell(v) in panel, f"{_inr(v)} is not in a cell of the panel"
    text = _text(panel)
    assert "Planned margin ₹ 6,300.00 26.25% of planned revenue" in text
    assert "spent beyond the estimate ₹ 4,050.00" in text
    assert "SF/BOQ/26-27/0102 Rev 1 2026-09-15" in text
    assert "SF/MI/26-27/0101 stacks SF/RA/26-27/0102 and SF/RA/26-27/0103" in text
    assert "Tax invoice SF/TI/26-27/0042 carries the same tax invoice number" in text
    assert "1 marking predates the day-rate correction" in text
    for left_out in ("1 draft RA bill", "1 cancelled RA bill", "1 cancelled tax invoice",
                     "1 purchase order still in Draft", "1 cancelled purchase order",
                     "1 draft purchase order sent out for pricing",
                     "1 work order not yet issued"):
        assert left_out in text, left_out
    assert "this reflects timing" in text


def test_a_bill_on_an_earlier_revision_raises_the_amber_note(project, client):
    panel = _panel(_page(client))
    assert 'class="pm-drift"' in panel
    assert ("SF/RA/26-27/0101 was raised against SF/BOQ/26-27/0101 Rev 0, and the "
            "plan reads SF/BOQ/26-27/0102 Rev 1, dated 2026-09-15") in _text(panel)
    # Not reconciled: the bill still counts at its own 50,000.
    assert PNL.project_pnl(PID)["to_date"]["ra"]["amount"] == RA_TAXABLE
    # The control: on the tip, there is nothing to say.
    STORE["ra_bills"]["pnl-ra1"]["boq_id"] = "pnl-b1"
    assert 'class="pm-drift"' not in _panel(_page(client))


def test_nothing_is_stored_by_reading_the_pnl(project, client):
    keys = ("projects", "boqs", "ra_bills", "merged_ras", "receipts", "proformas",
            "invoices", "purchases", "purchase_orders", "work_orders", "charges",
            "attendance")
    before = copy.deepcopy({k: STORE.get(k) for k in keys})
    _page(client)
    client.get("/projects/")
    PNL.project_pnl(PID)
    PNL.untagged_cost()
    assert {k: STORE.get(k) for k in keys} == before


def test_a_reader_without_wages_is_told_the_labour_row_is_withheld(project, client):
    """
    CC-2 B4's HR wall. An Accountant granted `project.pnl` (a checkbox) still
    does not hold `attendance.view`: the labour row says it is withheld and
    the totals beside it say they exclude it — never a silent short total.
    """
    import auth
    role = STORE["roles"]["role-accountant"]
    saved = list(role["permissions"])
    uid = "pnl-accountant"
    STORE["users"][uid] = {"id": uid, "username": "pnl-acct@test",
                           "display_name": "P Accountant", "password_hash": "x",
                           "role_ids": ["role-accountant"], "active": True}
    try:
        role["permissions"] = saved + ["project.pnl"]
        with client.session_transaction() as s:
            s[auth.SESSION_KEY] = uid
        panel = _panel(_page(client))
        text = _text(panel)
        assert "withheld: it needs the View attendance permission" in text
        assert _cell(LABOUR) not in panel
        assert _cell(ACTUAL - LABOUR) in panel                 # 20,500.00
        assert _cell(BILLED - (ACTUAL - LABOUR)) in panel       # 89,500.00
        assert "Spent to date (excluding site labour, withheld)" in text
        assert "Margin to date (excluding site labour, withheld)" in text
    finally:
        role["permissions"] = saved
        STORE["users"].pop(uid, None)


# ══ 6. UNTAGGED — the register's line ══════════════════════════════════════

def test_cost_tagged_to_no_project_is_summed_for_the_register(project):
    u = PNL.untagged_cost()
    assert u["po"] == {"amount": 3100.0, "count": 2}
    assert u["wo"] == {"amount": 800.0, "count": 1}
    assert u["charges"] == {"amount": 700.0, "count": 1}
    assert (u["labour"]["total"], u["labour"]["markings"]) == (800.0, 1)
    assert (u["total"], u["dangling"], u["no_figure"]) == (UNTAGGED, 1, 0)


def test_the_register_line_says_it_and_tagging_moves_the_money(project, client):
    html = client.get("/projects/").get_data(as_text=True)
    text = _text(html)
    assert "Cost not tagged to any project: ₹ 5,400.00 — tax-exclusive" in text
    assert "1 of these records names a project that no longer exists" in text
    # Tag PO5 to the project: it leaves the line and arrives on the P&L.
    STORE["purchases"]["pnl-po05"]["project_id"] = PID
    assert PNL.untagged_cost()["total"] == UNTAGGED - 2500.0
    assert PNL.project_pnl(PID)["to_date"]["po"]["amount"] == PO_TAXABLE + 2500.0


def test_a_marking_naming_a_deleted_project_is_untagged_labour(project):
    """`attendance.markings_on_no_project()`: a blank `project_id` and a
    dangling one alike — a marking pointing at a project that no longer exists
    is on no project's page, so it must be on the register's line."""
    STORE["attendance"]["m4"]["project_id"] = GONE
    u = PNL.untagged_cost()
    assert (u["labour"]["total"], u["dangling"], u["total"]) == (800.0, 2, UNTAGGED)
    STORE["attendance"]["m4"]["project_id"] = OTHER     # a live project: tagged
    assert PNL.untagged_cost()["total"] == UNTAGGED - 800.0


def test_an_untagged_draft_or_cancelled_record_is_not_untagged_cost(project):
    """The register line applies the P&L's own statuses: a Draft PO, a draft
    work order and a cancelled one are not costs anywhere."""
    STORE["purchases"]["pnl-po03"]["project_id"] = ""
    STORE["work_orders"]["pnl-wo02"]["project_id"] = ""
    assert PNL.untagged_cost()["total"] == UNTAGGED
