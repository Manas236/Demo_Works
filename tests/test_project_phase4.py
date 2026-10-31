"""
Phase 4 projects — CLIENT_CHANGES.md §0 sixty-third block, Part C
(31 October 2026).

What this file holds to, each by a figure or a name that only appears when the
feature worked:

C2  every document raised from a BOQ shows on its project by read-time
    inheritance — a RECEIPT through its RA bill, a WORK ORDER that carries a
    `boq_id` through its BOQ — and a document whose own tag disagrees with its
    BOQ's project gets an amber band naming BOTH, on both pages, with neither
    tag changed;
C3  the contract value is the TIP revision only, and a document raised under
    an older revision still counts and is flagged "raised under revision N";
C4  a manual PO's project is set on EDIT as well as create;
C5  billed counts an RA bill and the tax invoice carrying its number ONCE, and
    a merged set once; an issued PO is cost the moment it is issued (draft,
    cancelled and product inquiries are not); before any bill the running
    position is the cost as a negative, with its note; coverage beside the
    actual cost; the dashboard's Unattributed cost line;
C7  the spider's BOQ and procurement axes, and the dashboard tile's billed %.
"""

import pytest

import pnl as PNL
from store import STORE

from test_pnl_charts_oct28 import (  # noqa: F401 — `world` is a fixture
    L1, PID, _boq, _dc, _line, _ms, _panel, _po, _ra, world)


def _page(client, pid=PID) -> str:
    r = client.get(f"/projects/view/{pid}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _project(pid, name):
    STORE["projects"][pid] = {
        "id": pid, "name": name, "norm_name": name.lower(), "client": "",
        "notes": "", "site_address_id": "", "site_address": "",
        "created_at": "2026-10-01 09:00", "updated_at": "2026-10-01 09:00"}


# ══ C5 — billed once, cost when issued, the running position ════════════════

def test_an_ra_bill_and_the_tax_invoice_carrying_its_number_are_billed_ONCE(world):
    _boq()
    _ra(claim=10000.0, grand=11800.0)
    STORE["ra_bills"]["r1"]["tax_invoice_ref"] = "SF/TI/26-27/0042"
    STORE["invoices"]["t1"] = {
        "id": "t1", "ref": "sf/ti/26-27/0042 ", "date": "2026-10-15",
        "boq_id": "b1", "status": "", "subtotal": 10000.0, "grand_total": 11800.0}
    r = PNL.project_pnl(PID)
    assert r["to_date"]["billed"] == 10000.0, "the same money was counted twice"
    assert [s["ra_ref"] for s in r["same_number"]] == ["SF/RA/26-27/0001"]
    # …and a SECOND, different tax invoice is billed on top.
    STORE["invoices"]["t2"] = dict(STORE["invoices"]["t1"], id="t2",
                                   ref="SF/TI/26-27/0043", subtotal=500.0)
    assert PNL.project_pnl(PID)["to_date"]["billed"] == 10500.0


def test_a_merged_set_is_billed_once_at_its_legs(world):
    _boq()
    _ra(claim=10000.0, grand=11800.0)
    STORE["ra_bills"]["r2"] = dict(STORE["ra_bills"]["r1"], id="r2", ra_no=2,
                                   ref="SF/RA/26-27/0002", leg="installation",
                                   claim_subtotal=4000.0, grand_total=4720.0)
    STORE.setdefault("merged_ras", {})["m1"] = {
        "id": "m1", "tax_invoice_ref": "SF/MI/26-27/0001", "status": "live",
        "supply_ra_id": "r1", "installation_ra_id": "r2", "boq_id": "b1",
        "claim_subtotal": 14000.0, "grand_total": 16520.0}
    try:
        assert PNL.project_pnl(PID)["to_date"]["billed"] == 14000.0
    finally:
        STORE["merged_ras"].pop("m1", None)


@pytest.mark.parametrize("status, counted", [
    ("Draft", False), ("Issued", True), ("Acknowledged", True),
    ("Partially Received", True), ("Received", True), ("Cancelled", False)])
def test_a_po_is_cost_the_moment_it_is_issued(world, status, counted):
    _boq()
    _po(taxable=6000.0)
    STORE["purchases"]["po1"]["status"] = status
    assert PNL.project_pnl(PID)["to_date"]["actual"] == (6000.0 if counted else 0.0)


def test_a_product_inquiry_is_never_a_cost(world):
    _boq()
    STORE.setdefault("purchase_orders", {})["d1"] = {
        "id": "d1", "ref": "SF/DPO/0001", "boq_id": "b1", "lines": []}
    try:
        r = PNL.project_pnl(PID)
        assert r["to_date"]["actual"] == 0.0 and r["excluded"]["po_drafts"] == 1
    finally:
        STORE["purchase_orders"].pop("d1", None)


def test_before_any_bill_the_running_position_is_the_cost_as_a_negative(world):
    _boq()
    _po(taxable=6000.0)
    r = PNL.project_pnl(PID)
    assert r["to_date"]["billed"] == 0.0 and r["to_date"]["margin"] == -6000.0
    seg = _panel(world)
    assert "No bill raised yet: cost so far." in seg
    assert "the running position, billed less spent" in seg
    _ra()
    assert "No bill raised yet" not in _panel(world)


def test_coverage_sits_beside_the_actual_cost(world):
    _boq()
    _po(line_ids=(L1,))
    seg = _panel(world)
    row = seg.split("Spent to date", 1)[1].split("</tr>", 1)[0]
    assert "(1 of 2 BOQ lines has a PO)" in row


def test_the_dashboard_shows_unattributed_cost_and_billed_percent(world):
    _boq()
    _ra(claim=10000.0)
    STORE["purchases"]["po9"] = {
        "id": "po9", "ref": "SF/PO/26-27/0099", "status": "Issued",
        "project_id": "", "boq_id": "", "taxable_value": 2500.0,
        "subtotal": 2500.0, "grand_total": 2950.0, "charges": [], "items": []}
    html = world.get("/").get_data(as_text=True)
    assert "Unattributed cost:" in html and "2,500" in html
    assert "of the contract value" in html
    planned = PNL.project_pnl(PID)["planned"]["revenue"]
    assert f"{10000.0 / planned * 100.0:.1f}%" in html


# ══ C2 — inheritance at read time, and the band when two tags disagree ══════

def test_a_receipt_shows_on_the_project_through_its_bill(world):
    _boq()
    _ra()
    STORE["receipts"]["rc1"] = {"id": "rc1", "ref": "SF/RCPT/26-27/0077",
                                "ra_id": "r1", "date": "2026-10-20",
                                "amount": 5900.0, "mode": "NEFT", "written_off": 0.0}
    html = _page(world)
    assert "SF/RCPT/26-27/0077" in html and "against SF/RA/26-27/0001" in html
    assert "project_id" not in STORE["receipts"]["rc1"], "nothing is copied"


def test_dcs_and_measurement_sheets_show_through_their_boq(world):
    _boq(); _dc(); _ms()
    html = _page(world)
    assert "SF/DC/26-27/0001" in html and "SF/MS/26-27/0001" in html


def test_a_work_order_carrying_a_boq_link_follows_its_boq(world):
    import workorder as WO
    _boq()
    _project("p2", "Elsewhere")
    STORE["work_orders"]["w1"] = {
        "id": "w1", "ref": "WO-0042", "date": "2026-10-10", "status": "issued",
        "project_id": "", "boq_id": "b1", "gst_rate": 0,
        "lines": [{"item_no": "1", "description": "x", "unit": "Nos", "qty": 1,
                   "material_rate": 0, "labour_rate": 700}]}
    assert PNL.project_of(STORE["work_orders"]["w1"]) == PID
    assert PNL.project_pnl(PID)["to_date"]["wo"]["amount"] == 700.0
    import app as _app
    with _app.app.test_request_context():
        assert "WO-0042" in WO.project_panel_html(PID)
    assert PNL.untagged_cost()["wo"]["count"] == 0, "on a page AND untagged"


def test_a_disagreeing_tag_is_banded_on_both_pages_and_never_changed(world):
    _boq()
    _project("p2", "Other Job")
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": "SF/PO/26-27/0007", "date": "2026-10-12",
        "status": "Issued", "project_id": "p2", "boq_id": "b1",
        "boq_ref": "SF/BOQ/26-27/0019", "taxable_value": 100.0,
        "subtotal": 100.0, "grand_total": 118.0, "charges": [], "items": []}
    assert PNL.project_conflict(STORE["purchases"]["po1"]) == ("p2", PID)
    for pid in (PID, "p2"):
        html = _page(world, pid)
        assert "Purchase order SF/PO/26-27/0007</b> is tagged to <b>Other Job</b>" in html
        assert "is filed under <b>Jamnagar</b>" in html
        assert "neither tag has been changed" in html
    assert STORE["purchases"]["po1"]["project_id"] == "p2"


def test_no_band_without_a_disagreement(world):
    _boq(); _po()
    assert "neither tag has been changed" not in _page(world)
    assert PNL.project_conflict({"project_id": "", "boq_id": "b1"}) is None


# ══ C3 — the tip revision only, and the older-revision flag ═════════════════

def _revise():
    STORE["boqs"]["b2"] = dict(STORE["boqs"]["b1"], id="b2", rev_no=1,
                               supersedes="b1", date="2026-10-20",
                               ref="SF/BOQ/26-27/0019-R1",
                               line_items=[_line(L1, qty="50")])


def test_contract_value_is_the_tip_revision_only(world):
    _boq()
    _revise()
    plan = PNL.project_pnl(PID)["planned"]
    assert [t["boq_id"] for t in plan["tips"]] == ["b2"]
    assert plan["revenue"] == 50 * 100 + 50 * 40, "a superseded revision added in"


def test_a_document_raised_under_an_older_revision_counts_and_is_flagged(world):
    _boq()
    _ra(claim=10000.0)
    _dc()
    _revise()
    assert PNL.project_pnl(PID)["to_date"]["billed"] == 10000.0, "real money dropped"
    html = _page(world)
    assert "<b>Delivery challan SF/DC/26-27/0001</b> was raised under revision 0" in html
    assert "<b>RA bill SF/RA/26-27/0001</b> was raised under revision 0" in html
    assert "SF/BOQ/26-27/0019-R1 Rev 1, dated 2026-10-20" in html


# ══ C4 — a manual PO's project on edit ══════════════════════════════════════

def test_a_manual_po_takes_its_project_on_edit(world):
    import address
    address.ensure_demo_addresses()
    _project("p2", "Edit Job")
    r = world.post("/purchase/create", data={
        "date": "2026-10-31", "vendor_id": "b2000006-face-4000-8000-000000000006",
        "status": "Draft", "tax_type": "exempt", "cgst_rate": "0", "igst_rate": "0",
        "extra_desc": ["Gasket"], "extra_unit": ["Nos"], "extra_qty": ["1"],
        "extra_rate": ["100"], "extra_discount": [""]})
    assert r.status_code == 302
    po = list(STORE["purchases"].values())[-1]
    assert po["project_id"] == ""
    assert 'name="project_id"' in world.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    form = {"line_rate": [], "line_discount": [], "note": "", "project_id": "p2",
            "extra_desc": ["Gasket"], "extra_unit": ["Nos"], "extra_qty": ["1"],
            "extra_rate": ["100"], "extra_discount": [""]}
    assert world.post(f"/purchase/edit/{po['id']}", data=form).status_code == 302
    assert po["project_id"] == "p2" and po["project_name"] == "Edit Job"
    form["project_id"] = "no-such-project"
    world.post(f"/purchase/edit/{po['id']}", data=form)
    assert po["project_id"] == "p2", "a dead project id was written"


def test_a_po_from_a_boq_has_no_project_box_on_edit(world):
    _boq()
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": "SF/PO/26-27/0007", "date": "2026-10-12",
        "status": "Issued", "project_id": "", "boq_id": "b1",
        "boq_ref": "SF/BOQ/26-27/0019", "taxable_value": 0.0, "subtotal": 0.0,
        "grand_total": 0.0, "charges": [], "line_items": [], "extra_lines": [],
        "tax_type": "exempt", "tax_info": {"total": 0.0}}
    html = world.get("/purchase/edit/po1").get_data(as_text=True)
    assert 'name="project_id"' not in html
    assert "follows schedule" in html


# ══ C7 — the new spider axes ════════════════════════════════════════════════

def test_the_boq_and_procurement_axes(world):
    _boq()
    _po(taxable=6000.0)
    axes = {a["key"]: a for a in PNL.progress_of(PID)}
    assert axes["boq"]["pct"] == 100.0
    planned_cost = PNL.project_pnl(PID)["planned"]["cost"]
    assert axes["procurement"]["numer"] == 6000.0
    assert axes["procurement"]["pct"] == round(6000.0 / planned_cost * 100.0, 2)
    STORE["boqs"]["b1"]["line_items"].append(_line("cccccccccccc", qty=""))
    assert {a["key"]: a for a in PNL.progress_of(PID)}["boq"]["pct"] == 66.67
