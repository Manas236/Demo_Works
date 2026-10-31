"""
"Round off to nearest rupee" — a tick on every money document — and the RA
set's cancel-together rule.

31 October 2026, CLIENT_CHANGES.md §0 sixty-third block (Parts A and D).
Manas: *"round-off on all documents, nothing left behind"*, decided per
document by the operator, TICKED BY DEFAULT, stored as `round_off_on`.

What this file holds to:

1.  the rule itself — ticked rounds HALF UP and stores the difference;
    unticked is the exact two-decimal figure and a round-off of 0; a POST from
    no form offering the tick is the document's LEGACY behaviour;
2.  the tick is on every money form it should be on, and on none it should
    not (DC, measurement sheet, Product Inquiry);
3.  each document honours it — PO, PI (both paths), TI (both paths, the PI
    path opening at the PI's choice), Work Order (mapped onto
    `rounds_to_rupee`), RA bill, quotation, BOQ (grand total only), payslip;
4.  a record WITHOUT `round_off_on` behaves exactly as it did;
5.  the Supply + Installation set rounds ONCE on the merged tax invoice
    (cancelling the set together is `tests/test_ra_set_cancel.py`).

⚠ No assertion here may pass against a blank page: each names a figure, a
  field or a link target that only appears when the feature worked.
"""

import json
import re

import pytest

import address
import demo_data as DD
import merged_ra as MRA
import ra as RA
import roundoff as RO
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"


# ══ 1. The rule ═════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw, want", [
    (1235.36415, 1235.36), (2.675, 2.68), (2.665, 2.67), (-2.675, -2.68),
    (0.005, 0.01), (100.0, 100.0), (None, 0.0)])
def test_paise_is_half_up_to_two_decimals(raw, want):
    assert RO.paise(raw) == want


def test_apply_ticked_and_unticked():
    assert RO.apply(11419.80, True) == (11420.0, 0.2)
    assert RO.apply(11419.80, False) == (11419.8, 0.0)
    assert RO.apply(1235.36415, False) == (1235.36, 0.0)


def test_a_post_without_the_marker_is_the_documents_legacy():
    assert RO.form_choice({}, legacy=True) is True
    assert RO.form_choice({}, legacy=False) is False
    # The marker with no box is a tick the operator CLEARED.
    assert RO.form_choice({RO.MARK: "1"}, legacy=True) is False
    assert RO.form_choice({RO.MARK: "1", RO.FIELD: "1"}, legacy=False) is True


def test_a_record_without_the_field_is_legacy():
    assert RO.is_on({}, legacy=True) is True
    assert RO.is_on({}, legacy=False) is False
    assert RO.is_on({RO.FIELD: False}, legacy=True) is False


def test_paise_tax_rounds_heads_and_sums_them_and_leaves_rates():
    t = RO.paise_tax({"CGST": 111.18374, "SGST": 111.18374, "total": 222.36748,
                      "cgst_rate": 9.0, "sgst_rate": 9.0})
    assert t == {"CGST": 111.18, "SGST": 111.18, "total": 222.36,
                 "cgst_rate": 9.0, "sgst_rate": 9.0}


def test_the_checkbox_is_ticked_by_default_and_carries_its_marker():
    on, off = RO.checkbox_html(True), RO.checkbox_html(False)
    assert f'name="{RO.MARK}" value="1"' in on and f'name="{RO.FIELD}"' in on
    assert "checked" in on and "checked" not in off
    assert "Round off to nearest rupee" in on


# ══ 2. Which forms carry it ═════════════════════════════════════════════════

TICK = f'name="{RO.FIELD}" value="1" checked'


@pytest.fixture()
def sched(client):
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()
    client.get("/boq/")
    client.get("/settings/")
    address.ensure_demo_addresses()
    yield DD.BOQ_META["id"]
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()


@pytest.mark.parametrize("url", [
    "/purchase/create", "/purchase/from-boq/{bid}", "/proforma/from-boq/{bid}",
    "/invoice/from-boq/{bid}", "/wo/create", "/ra/create?boq={bid}&leg=supply",
    "/quotation/create", "/boq/create", "/raboth/create?boq={bid}"])
def test_every_money_create_form_opens_ticked(client, sched, url):
    r = client.get(url.format(bid=sched))
    assert r.status_code == 200, url
    assert TICK in r.get_data(as_text=True), f"{url} has no ticked round-off box"


@pytest.mark.parametrize("url", [
    "/dc/create?boq={bid}", "/measurement/create?boq={bid}", "/po/create?boq={bid}"])
def test_no_tick_where_there_is_no_money_total(client, sched, url):
    r = client.get(url.format(bid=sched))
    assert r.status_code == 200, url
    assert f'name="{RO.FIELD}"' not in r.get_data(as_text=True), url


# ══ 3. The purchase order ═══════════════════════════════════════════════════

def _po_form(rate, qty=1, **extra):
    d = {"date": "2026-10-31", "vendor_id": VENDOR_ID, "status": "Draft",
         "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0",
         "extra_desc": ["Gasket"], "extra_unit": ["Nos"], "extra_qty": [str(qty)],
         "extra_rate": [str(rate)], "extra_discount": [""]}
    d.update(extra)
    return d


def _new_po(client, **tick):
    address.ensure_demo_addresses()
    r = client.post("/purchase/create", data=_po_form(9678, **tick))
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return list(STORE["purchases"].values())[-1]


def test_an_unticked_po_is_the_exact_figure_with_no_round_off_row(client):
    po = _new_po(client, **{RO.MARK: "1"})
    assert po[RO.FIELD] is False
    assert po["grand_total"] == 11420.04 and po["round_off"] == 0.0
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Round off" not in html and "11,420.04" in html


def test_a_ticked_po_rounds_as_before(client):
    po = _new_po(client, **{RO.MARK: "1", RO.FIELD: "1"})
    assert po[RO.FIELD] is True
    assert po["grand_total"] == 11420.0 and po["round_off"] == -0.04


def test_a_reprice_can_flip_the_tick_and_the_form_shows_the_stored_choice(client):
    po = _new_po(client, **{RO.MARK: "1", RO.FIELD: "1"})
    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert TICK in html
    form = {"line_rate": [], "line_discount": [], "note": "",
            "extra_desc": ["Gasket"], "extra_unit": ["Nos"], "extra_qty": ["1"],
            "extra_rate": ["9678"], "extra_discount": [""], RO.MARK: "1"}
    r = client.post(f"/purchase/edit/{po['id']}", data=form)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    assert po[RO.FIELD] is False and po["grand_total"] == 11420.04
    assert TICK not in client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)


def test_a_legacy_po_reprices_rounded_as_it_always_did(client):
    po = _new_po(client)
    po.pop(RO.FIELD)
    form = {"line_rate": [], "line_discount": [], "note": "",
            "extra_desc": ["Gasket"], "extra_unit": ["Nos"], "extra_qty": ["1"],
            "extra_rate": ["9678"], "extra_discount": [""]}
    assert client.post(f"/purchase/edit/{po['id']}", data=form).status_code == 302
    assert po["grand_total"] == 11420.0 and RO.FIELD not in po


# ══ 4. The proforma and the tax invoice ═════════════════════════════════════

def _lines(bid, n=1):
    lines = [li for li in STORE["boqs"][bid]["line_items"]
             if not li.get("is_header") and float(li.get("supply_rate") or 0) > 0]
    return json.dumps({"lines": [{"line_id": li["line_id"], "qty": "1.5"}
                                 for li in lines[:n]]})


def test_an_unticked_boq_proforma_is_exact(client, sched):
    r = client.post(f"/proforma/from-boq/{sched}", data={
        "date": "2026-10-31", "advance_pct": "100", "validity_days": "15",
        "leg": "supply", "tax_type": "cgst_sgst", "pi_json": _lines(sched, 3),
        RO.MARK: "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    pi = list(STORE["proformas"].values())[-1]
    assert pi[RO.FIELD] is False and pi["round_off"] == 0.0
    assert pi["grand_total"] == RO.paise(pi["subtotal"] + pi["tax_info"]["total"])


def test_a_ticked_boq_tax_invoice_is_whole(client, sched):
    r = client.post(f"/invoice/from-boq/{sched}", data={
        "date": "2026-10-31", "place_of_supply": "Karnataka",
        "advance_received": "0", "leg": "supply", "tax_type": "cgst_sgst",
        "ti_json": _lines(sched, 3), RO.MARK: "1", RO.FIELD: "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    ti = list(STORE["invoices"].values())[-1]
    assert ti[RO.FIELD] is True and ti["grand_total"] == round(ti["grand_total"])


@pytest.fixture()
def pi_odd(client):
    """A proforma whose total is not whole, written straight into the store."""
    STORE["proformas"]["p-ro"] = {
        "id": "p-ro", "ref": "PI-0777", "date": "2026-10-31",
        "account_name": "A Customer", "to": "A Customer\nPune",
        "line_items": [{"name": "Pipe", "qty": 1, "rate": 9678.0, "total": 9678.0,
                        "unit": "Nos", "hsn": "7306"}],
        "subtotal": 9678.0, "grand_total": 11420.04, "total_qty": 1,
        "tax_type": "cgst_sgst",
        "tax_info": {"CGST": 871.02, "SGST": 871.02, "total": 1742.04,
                     "cgst_rate": 9.0, "sgst_rate": 9.0},
    }
    yield STORE["proformas"]["p-ro"]
    STORE["proformas"].pop("p-ro", None)


def test_the_ti_form_opens_at_the_proformas_choice(client, pi_odd):
    pi_odd[RO.FIELD] = False
    html = client.get("/invoice/from/p-ro").get_data(as_text=True)
    assert f'name="{RO.FIELD}"' in html and TICK not in html
    pi_odd[RO.FIELD] = True
    assert TICK in client.get("/invoice/from/p-ro").get_data(as_text=True)


def test_a_ti_from_an_unticked_pi_is_exact_unless_the_ti_ticks_it(client, pi_odd):
    pi_odd[RO.FIELD] = False
    form = {"date": "2026-10-31", "place_of_supply": "Maharashtra",
            "advance_received": "0"}
    assert client.post("/invoice/from/p-ro", data=form).status_code == 302
    ti = list(STORE["invoices"].values())[-1]
    assert ti["grand_total"] == 11420.04 and ti["round_off"] == 0.0
    assert ti[RO.FIELD] is False
    # The TI's own tick wins over the PI's choice.
    form.update({RO.MARK: "1", RO.FIELD: "1"})
    assert client.post("/invoice/from/p-ro", data=form).status_code == 302
    ti2 = list(STORE["invoices"].values())[-1]
    assert ti2["grand_total"] == 11420.0 and ti2["round_off"] == -0.04


def test_a_legacy_pi_gives_a_rounded_ti_as_before(client, pi_odd):
    form = {"date": "2026-10-31", "place_of_supply": "Maharashtra",
            "advance_received": "0"}
    assert client.post("/invoice/from/p-ro", data=form).status_code == 302
    assert list(STORE["invoices"].values())[-1]["grand_total"] == 11420.0


# ══ 5. The work order — `rounds_to_rupee` mapped onto the tick ══════════════

def test_the_work_order_tick_maps_onto_rounds_to_rupee():
    import workorder as WO
    line = {"item_no": "1", "description": "Labour", "unit": "Nos", "qty": 1,
            "material_rate": 0, "labour_rate": 9678}
    older = {"lines": [line], "gst_rate": 18}                          # never rounded
    today = {"lines": [line], "gst_rate": 18, "rounds_to_rupee": True}  # §0 62nd
    assert WO.totals_of(older)["total"] == 11420.04
    assert WO.totals_of(today)["total"] == 11420.0
    # The tick, where present, wins — either way.
    assert WO.totals_of(dict(today, round_off_on=False))["total"] == 11420.04
    assert WO.totals_of(dict(older, round_off_on=True))["total"] == 11420.0


def _wo_data(**over):
    d = {"date": "2026-10-31", "contractor_id": "", "contractor_name": "Ravi",
         "contractor_gstin": "", "contractor_addr": "Pune", "project_id": "",
         "notes": "", "gst_rate": "18",
         "ln_id": [""], "ln_item": ["1"], "ln_desc": ["Labour"], "ln_unit": ["Nos"],
         "ln_qty": ["1"], "ln_mrate": ["0"], "ln_lrate": ["9678"], "ln_note": [""]}
    d.update(over)
    return d


def test_an_unticked_work_order_and_a_draft_edit_that_ticks_it(client):
    import workorder as WO
    before = set(STORE["work_orders"])
    assert client.post("/wo/create", data=_wo_data(**{RO.MARK: "1"})).status_code == 302
    (wid,) = set(STORE["work_orders"]) - before
    wo = STORE["work_orders"][wid]
    assert wo[RO.FIELD] is False and "rounds_to_rupee" not in wo
    assert WO.totals_of(wo)["total"] == 11420.04
    assert TICK not in client.get(f"/wo/edit/{wid}").get_data(as_text=True)
    r = client.post(f"/wo/edit/{wid}", data=_wo_data(**{RO.MARK: "1", RO.FIELD: "1"}))
    assert r.status_code == 302
    assert WO.totals_of(wo)["total"] == 11420.0
    STORE["work_orders"].pop(wid, None)


# ══ 6. The RA bill ══════════════════════════════════════════════════════════

def test_compute_tax_totals_honours_the_tick():
    claims = [{"line_id": "x", "qty": 1, "rate": 9678.0, "amount": 9678.0,
               "gst_rate": 18.0}]
    on = RA.compute_tax_totals(claims, [])
    off = RA.compute_tax_totals(claims, [], round_on=False)
    assert (on["rounding_off"], on["grand_total"]) == (-0.04, 11420.0)
    assert (off["rounding_off"], off["grand_total"]) == (0.0, 11420.04)


def test_the_ra_form_opens_ticked(client, sched):
    html = client.get(f"/ra/create?boq={sched}&leg=supply").get_data(as_text=True)
    assert TICK in html


# ══ 7. The quotation ════════════════════════════════════════════════════════

def _quote(client, **extra):
    import specpick
    specpick.ensure_seeded()
    sid = next(sid for sid, s in STORE["specs"].items()
               if s["variants"][0].get("default_supply_base_rate") is not None)
    sel = [{"sid": sid, "vidx": 0, "leg": "supply", "qty": 12.345,
            "price": 100.07, "show_price": True}]
    data = {"account_name": "Tick Customer", "qtn_date": "2026-10-31",
            "tax_type": "cgst_sgst", "tax_cgst": "9", "tax_sgst": "9",
            "tax_igst": "18", "tax_vat": "5", "selections_json": json.dumps(sel)}
    data.update(extra)
    r = client.post("/quotation/create", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    return list(STORE["quotations"].values())[-1]


def test_a_ticked_quotation_rounds_and_prints_the_row(client):
    q = _quote(client, **{RO.MARK: "1", RO.FIELD: "1"})
    assert q[RO.FIELD] is True and q["grand_total"] == round(q["grand_total"])
    assert q["round_off"] != 0.0
    html = client.get(f"/quotation/view/{q['id']}").get_data(as_text=True)
    assert "Round off" in html and RO.label(q["round_off"]) in html


def test_an_unticked_or_legacy_quotation_is_not_rounded(client):
    q = _quote(client, **{RO.MARK: "1"})
    assert q[RO.FIELD] is False and q["round_off"] == 0.0
    legacy = _quote(client)      # no marker: a quotation was never rounded
    assert legacy[RO.FIELD] is False and legacy["round_off"] == 0.0
    legacy.pop("round_off"), legacy.pop(RO.FIELD)
    assert "Round off" not in client.get(
        f"/quotation/view/{legacy['id']}").get_data(as_text=True)


# ══ 8. The BOQ — the grand total only ═══════════════════════════════════════

def _boq_post(client, **extra):
    li = {"line_id": "", "item_no": "1", "parent_item_no": "", "section": "A",
          "is_header": False, "description": "Pipe", "remark": "", "unit": "Mtr",
          "area_qty": {}, "total_qty": "12.345",
          "supply_base_rate": "", "supply_escalation_pct": "", "supply_rate": "100.07",
          "supply_hsn": "", "supply_gst_rate": "",
          "install_base_rate": "", "install_escalation_pct": "", "install_rate": "",
          "install_sac": "", "install_gst_rate": "",
          "supply_disc_pct": "", "install_disc_pct": ""}
    data = {"date": "2026-10-31", "project_name": "Tick Job", "account_name": "A",
            "boq_json": json.dumps({"sections": [{"code": "A", "title": "",
                                                  "areas": []}], "lines": [li]})}
    data.update(extra)
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (bid,) = set(STORE["boqs"]) - before
    return STORE["boqs"][bid]


def test_a_ticked_boq_prints_a_round_off_and_a_grand_total(client):
    import boq as BQ
    b = _boq_post(client, **{RO.MARK: "1", RO.FIELD: "1"})
    line = [li for li in b["line_items"] if not li.get("is_header")][0]
    assert line["supply_amount"] == 1235.36, "the line amount is to the paisa"
    assert BQ.grand_of(b) == (1235.36, -0.36, 1235.0)
    assert b["round_off"] == -0.36
    html = client.get(f"/boq/print/{b['id']}").get_data(as_text=True)
    assert "ROUND OFF" in html and "GRAND TOTAL" in html and "-0.36" in html


def test_an_unticked_or_legacy_boq_draws_the_sheet_it_drew(client):
    import boq as BQ
    b = _boq_post(client, **{RO.MARK: "1"})
    assert b[RO.FIELD] is False and BQ.grand_of(b) == (1235.36, 0.0, 1235.36)
    assert "ROUND OFF" not in client.get(f"/boq/print/{b['id']}").get_data(as_text=True)
    legacy = _boq_post(client)
    legacy.pop(RO.FIELD), legacy.pop("round_off")
    assert BQ.grand_of(legacy)[1] == 0.0
    assert "ROUND OFF" not in client.get(f"/boq/print/{legacy['id']}").get_data(as_text=True)


# ══ 9. The payslip — net pay ════════════════════════════════════════════════

LOAN = {"opening": 0.0, "deduction": 0.0, "balance": 0.0}


def test_the_payslip_tick_and_the_carry_forward():
    import payroll as PAY
    fig = {"basic": 12118.5, "ot": 0.0}
    assert PAY.compute(fig, [], LOAN)["payable"] == 12119       # half up
    off = PAY.compute(fig, [], LOAN, round_on=False)
    assert (off["payable"], off["round_off"]) == (12118.5, 0.0)
    rows = [{"type": PAY.ADVANCE, "amount": 13000.0}]
    for on in (True, False):
        neg = PAY.compute(fig, rows, LOAN, round_on=on)
        assert (neg["payable"], neg["carry"]) == (0, 881.5), "carry-forward moved"


def test_a_legacy_slip_refreshes_rounded():
    import payroll as PAY
    assert RO.is_on({"status": PAY.DRAFT}, True) is True


# ══ 10. The Supply + Installation set — rounded ONCE ═══════════════════════

def _both(client, bid, **over):
    html = client.get(f"/raboth/create?boq={bid}").get_data(as_text=True)
    flat = " ".join(html.split())
    data = {"boq": bid, "date": "2026-10-31"}
    for leg in ("supply", "installation"):
        lid, rate = re.findall(
            r'name="%s_qty_([0-9a-f]{12})"[^>]*?/>.*?name="%s_rate_\1" value="([^"]*)"'
            % (leg, leg), flat)[0]
        data[f"{leg}_qty_{lid}"] = "1.5"
        data[f"{leg}_rate_{lid}"] = str(float(rate) + 0.07)
    data.update(over)
    r = client.post(f"/raboth/create?boq={bid}", data=data)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:600]
    (m,) = STORE["merged_ras"].values()
    legs = sorted(STORE["ra_bills"].values(), key=lambda b: int(b["ra_no"]))
    return m, legs


def test_the_set_is_rounded_once_on_the_merged_invoice_never_per_leg(client, sched):
    m, legs = _both(client, sched, **{RO.MARK: "1", RO.FIELD: "1"})
    assert [b["rounding_off"] for b in legs] == [0.0, 0.0], "a leg was rounded"
    exact = round(sum(b["grand_total"] for b in legs), 2)
    assert m["grand_total"] == round(m["grand_total"]), "the invoice is not whole"
    assert round(exact + m["rounding_off"], 2) == m["grand_total"]
    assert m[RO.FIELD] is True


def test_an_unticked_set_is_exact(client, sched):
    m, legs = _both(client, sched, **{RO.MARK: "1"})
    assert m["rounding_off"] == 0.0
    assert m["grand_total"] == round(sum(b["grand_total"] for b in legs), 2)
