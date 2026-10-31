"""
PAISE INTEGRITY — every money-document create path, with awkward inputs.

31 October 2026, CLIENT_CHANGES.md §0 sixty-third block, Part B. The client's
customer portal rejected a bill because an amount on it carried THREE
decimals. Two rules, asserted on every create path below:

    R1  no stored money value has more than two decimals;
    R2  the document foots to the paisa — the subtotal is the sum of the
        stored line amounts, and the grand total is subtotal + tax + charges
        (+ round off), so the printed total is the sum of the printed lines,
        the tax and the round-off.

The awkward inputs, wherever the path takes them: quantity **12.345**, rate
**100.07**, a **7.5 %** discount, and an **18 %** line beside a **12 %** one.
Each path runs with the round-off tick ON and OFF, because an unticked total
is the exact figure and that is where a third decimal would show.

⚠ A path that cannot take one of the inputs says so in its builder (a
  purchase order is taxed at ONE rate, so it carries no 12 % line; a work
  order has no discount box) — nothing is silently skipped.
"""

import json
import re
from decimal import Decimal

import pytest

import address
import roundoff as RO
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"
QTY, RATE, DISC = "12.345", "100.07", "7.5"

# Every key whose value is MONEY on any document's record. Rates that are
# percentages (`gst_rate`, `cgst_rate`, `discount_pct`, `advance_pct`) and
# quantities are not money and are not in this set.
MONEY = {
    "total", "amount", "subtotal", "grand_total", "taxable_value", "round_off",
    "rounding_off", "claim_subtotal", "net_payable", "tax_amount",
    "cgst_amount", "sgst_amount", "igst_amount", "deduction_total",
    "amount_due", "balance_due", "supply_amount", "install_amount",
    "supply_subtotal", "install_subtotal", "payable", "net_raw", "gross",
    "CGST", "SGST", "IGST", "VAT", "taxable", "advance_received",
    "material", "labour", "gst", "carry", "basic", "ot", "prior_invoiced",
}


def _too_fine(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return Decimal(repr(float(v))).as_tuple().exponent < -2


def _offenders(rec, path="") -> list:
    """Every MONEY value anywhere in `rec` carrying more than two decimals."""
    out = []
    if isinstance(rec, dict):
        for k, v in rec.items():
            here = f"{path}.{k}"
            if (k in MONEY or str(k).startswith(("CGST @", "SGST @", "IGST @"))) \
                    and _too_fine(v):
                out.append((here, v))
            out += _offenders(v, here)
    elif isinstance(rec, list):
        for i, v in enumerate(rec):
            out += _offenders(v, f"{path}[{i}]")
    return out


def _r1(rec, what):
    bad = _offenders(rec)
    assert not bad, f"{what}: money beyond two decimals: {bad[:6]}"


def _p(x) -> float:
    return round(float(x or 0.0), 2)


def _foot_sell(rec, what, lines_key="line_items"):
    """A PI / TI / quotation / PO: lines → subtotal → + tax → grand."""
    lines = [r for r in rec.get(lines_key) or [] if isinstance(r, dict)
             and not r.get("is_header") and r.get("type", "item") != "header"]
    lines += [r for r in rec.get("extra_lines") or []]
    assert lines, f"{what}: no lines — the sweep would pass on nothing"
    assert _p(sum(_p(r.get("total")) for r in lines)) == _p(rec["subtotal"]), (
        f"{what}: subtotal is not the sum of the stored line amounts")
    tax = rec.get("tax_info") or {}
    heads = [v for k, v in tax.items() if k != "total" and not k.endswith("_rate")
             and isinstance(v, (int, float))]
    if heads:
        assert _p(sum(heads)) == _p(tax["total"]), f"{what}: tax rows do not foot"
    base = _p(rec.get("taxable_value", rec["subtotal"]))
    charges = sum(_p(c.get("amount")) for c in rec.get("charges") or []
                  if not c.get("taxable"))
    want = _p(base + _p(tax.get("total")) + charges + _p(rec.get("round_off")))
    assert want == _p(rec["grand_total"]), (
        f"{what}: {base} + tax {tax.get('total')} + round off "
        f"{rec.get('round_off')} != grand {rec['grand_total']}")


def _foot_ra(b, what):
    assert _p(sum(_p(c["amount"]) for c in b["claims"])) == _p(b["claim_subtotal"]), what
    assert _p(b["cgst_amount"] + b["sgst_amount"] + b["igst_amount"]) == _p(b["tax_amount"])
    assert _p(b["net_payable"] + b["tax_amount"] + b["rounding_off"]) == _p(b["grand_total"]), what


TICKS = {"on": {RO.MARK: "1", RO.FIELD: "1"}, "off": {RO.MARK: "1"}}


# ── the schedule every BOQ-side path is raised from ────────────────────────

def _boq_line(item, gst):
    return {"line_id": "", "item_no": item, "parent_item_no": "", "section": "A",
            "is_header": False, "description": f"Pipe {item}", "remark": "",
            "unit": "Mtr", "area_qty": {}, "total_qty": QTY,
            "supply_base_rate": "80", "supply_escalation_pct": "",
            "supply_rate": RATE, "supply_hsn": "7306", "supply_gst_rate": gst,
            "install_base_rate": "20", "install_escalation_pct": "",
            "install_rate": "40.33", "install_sac": "995461",
            "install_gst_rate": gst, "supply_disc_pct": DISC,
            "install_disc_pct": DISC}


@pytest.fixture()
def world(client):
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()
    client.get("/boq/")
    client.get("/settings/")
    address.ensure_demo_addresses()
    yield client
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()


def _boq(client, tick):
    model = {"sections": [{"code": "A", "title": "", "areas": []}],
             "lines": [_boq_line("1", "18"), _boq_line("2", "12")]}
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={
        "date": "2026-10-31", "project_name": "Paise Job", "account_name": "A",
        "boq_json": json.dumps(model), **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (bid,) = set(STORE["boqs"]) - before
    return STORE["boqs"][bid]


def _picked(boq, key="qty", value=QTY):
    return json.dumps({"lines": [{"line_id": li["line_id"], key: value}
                                 for li in boq["line_items"] if not li.get("is_header")]})


def _newest(coll):
    return list(STORE[coll].values())[-1]


# ══ The sweep ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tick", ["on", "off"])
def test_boq(world, tick):
    import boq as BQ
    b = _boq(world, tick)
    _r1(b, "BOQ")
    sup, ins, tot = BQ.boq_totals(b)
    lines = [li for li in b["line_items"] if not li.get("is_header")]
    assert _p(sum(li["supply_amount"] + li["install_amount"] for li in lines)) == _p(tot)
    t, ro, g = BQ.grand_of(b)
    assert _p(t + ro) == _p(g)
    assert lines[0]["supply_amount"] == 1142.65        # 12.345 × 92.56 (100.07 less 7.5 %), to the paisa


@pytest.mark.parametrize("tick", ["on", "off"])
def test_quotation(world, tick):
    import specpick
    specpick.ensure_seeded()
    sids = [sid for sid, s in STORE["specs"].items()
            if s["variants"][0].get("default_supply_base_rate") is not None][:2]
    sel = [{"sid": sid, "vidx": 0, "leg": "supply", "qty": float(QTY),
            "price": float(RATE), "show_price": True} for sid in sids]
    r = world.post("/quotation/create", data={
        "account_name": "Paise", "qtn_date": "2026-10-31", "tax_type": "cgst_sgst",
        "tax_cgst": "9", "tax_sgst": "9", "tax_igst": "18", "tax_vat": "5",
        "selections_json": json.dumps(sel), **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    q = _newest("quotations")
    _r1(q, "quotation")
    _foot_sell(q, "quotation")


def _quotation_for_pi():
    """A quotation as one saved BEFORE this pass would be: raw products."""
    STORE["quotations"]["q-paise"] = {
        "id": "q-paise", "ref": "SF/Q/9999", "date": "2026-10-31",
        "account_name": "Paise", "to": "Paise", "tax_type": "cgst_sgst",
        "line_items": [
            {"type": "item", "name": "A", "qty": 12.345, "price": 100.07,
             "total": 12.345 * 100.07, "depth": 0, "unit": "Nos"},
            {"type": "item", "name": "B", "qty": 12.345, "price": 92.56475,
             "total": 12.345 * 92.56475, "depth": 0, "unit": "Nos"}],
        "subtotal": 12.345 * 100.07 + 12.345 * 92.56475,
        "tax_info": {"CGST": (12.345 * 100.07 + 12.345 * 92.56475) * 0.09,
                     "SGST": (12.345 * 100.07 + 12.345 * 92.56475) * 0.09,
                     "total": (12.345 * 100.07 + 12.345 * 92.56475) * 0.18,
                     "cgst_rate": 9.0, "sgst_rate": 9.0},
        "grand_total": (12.345 * 100.07 + 12.345 * 92.56475) * 1.18,
        "total_qty": 24.69,
    }
    return "q-paise"


@pytest.mark.parametrize("tick", ["on", "off"])
def test_proforma_from_quotation_and_tax_invoice_from_it(world, tick):
    qid = _quotation_for_pi()
    r = world.post(f"/proforma/from/{qid}", data={
        "date": "2026-10-31", "advance_pct": "100", "validity_days": "15",
        "confirm_over": "1", **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    pi = _newest("proformas")
    _r1(pi, "PI from quotation")
    _foot_sell(pi, "PI from quotation")
    r = world.post(f"/invoice/from/{pi['id']}", data={
        "date": "2026-10-31", "place_of_supply": "Maharashtra",
        "advance_received": "0", **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    ti = _newest("invoices")
    _r1(ti, "TI from PI")
    _foot_sell(ti, "TI from PI")
    STORE["quotations"].pop(qid, None)


@pytest.mark.parametrize("tick", ["on", "off"])
@pytest.mark.parametrize("leg", ["supply", "both"])
def test_proforma_and_tax_invoice_from_the_boq(world, tick, leg):
    b = _boq(world, tick)
    r = world.post(f"/proforma/from-boq/{b['id']}", data={
        "date": "2026-10-31", "advance_pct": "100", "validity_days": "15",
        "leg": leg, "tax_type": "cgst_sgst", "pi_json": _picked(b), **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    pi = _newest("proformas")
    _r1(pi, "PI from BOQ")
    _foot_sell(pi, "PI from BOQ")
    r = world.post(f"/invoice/from-boq/{b['id']}", data={
        "date": "2026-10-31", "place_of_supply": "Karnataka",
        "advance_received": "0", "leg": leg, "tax_type": "cgst_sgst",
        "ti_json": _picked(b), **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    ti = _newest("invoices")
    _r1(ti, "TI from BOQ")
    _foot_sell(ti, "TI from BOQ")


@pytest.mark.parametrize("tick", ["on", "off"])
def test_purchase_order_from_scratch(world, tick):
    """One tax rate per order (the vendor charges one), so no 12 % line."""
    r = world.post("/purchase/create", data={
        "date": "2026-10-31", "vendor_id": VENDOR_ID, "status": "Issued",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0",
        "extra_desc": ["Gasket", "Bolt"], "extra_unit": ["Nos", "Nos"],
        "extra_qty": [QTY, QTY], "extra_rate": [RATE, "7.33"],
        "extra_discount": [DISC, ""],
        "charge_label": ["Freight"], "charge_amount": ["123.455"],
        "charge_taxable": [], **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    po = _newest("purchases")
    _r1(po, "PO")
    _foot_sell(po, "PO")


@pytest.mark.parametrize("tick", ["on", "off"])
def test_purchase_order_from_the_boq(world, tick):
    b = _boq(world, tick)
    r = world.post(f"/purchase/from-boq/{b['id']}", data={
        "date": "2026-10-31", "vendor_id": VENDOR_ID, "status": "Issued",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "18",
        "po_json": json.dumps({"lines": [
            {"line_id": li["line_id"], "qty": QTY, "rate": RATE}
            for li in b["line_items"] if not li.get("is_header")]}),
        **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    po = _newest("purchases")
    _r1(po, "PO from BOQ")
    _foot_sell(po, "PO from BOQ")


@pytest.mark.parametrize("tick", ["on", "off"])
def test_purchase_order_from_a_product_inquiry(world, tick):
    b = _boq(world, tick)
    lines = [li for li in b["line_items"] if not li.get("is_header")]
    r = world.post(f"/po/create?boq={b['id']}", data={
        "date": "2026-10-31", "vendor_id": VENDOR_ID, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "",
                                          "pcs": ""} for li in lines]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    did = _newest("purchase_orders")["id"]
    r = world.post(f"/purchase/from-draft/{did}", data={
        "date": "2026-10-31", "vendor_id": VENDOR_ID, "status": "Issued",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "18",
        "dl_line_id": [li["line_id"] for li in lines],
        "dl_qty": [QTY, QTY], "dl_rate": [RATE, "92.56"], **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    po = _newest("purchases")
    _r1(po, "PO from inquiry")
    _foot_sell(po, "PO from inquiry")


@pytest.mark.parametrize("tick", ["on", "off"])
def test_work_order(world, tick):
    """No discount box on a work order; awkward quantity and rates instead."""
    import workorder as WO
    before = set(STORE["work_orders"])
    r = world.post("/wo/create", data={
        "date": "2026-10-31", "contractor_id": "", "contractor_name": "Ravi",
        "contractor_gstin": "", "contractor_addr": "Pune", "project_id": "",
        "notes": "", "gst_rate": "18",
        "ln_id": ["", ""], "ln_item": ["1", "2"], "ln_desc": ["A", "B"],
        "ln_unit": ["Nos", "Nos"], "ln_qty": [QTY, QTY],
        "ln_mrate": [RATE, "0"], "ln_lrate": ["40.33", "7.5"], "ln_note": ["", ""],
        **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (wid,) = set(STORE["work_orders"]) - before
    wo = STORE["work_orders"][wid]
    t = WO.totals_of(wo)
    _r1(t, "WO totals")
    rows = [WO.line_amounts(li) for li in wo["lines"]]
    assert _p(sum(r[2] for r in rows)) == _p(t["grand"])
    assert _p(t["grand"] + t["gst"] + t["round_off"]) == _p(t["total"])
    STORE["work_orders"].pop(wid, None)


@pytest.mark.parametrize("tick", ["on", "off"])
def test_ra_bill(world, tick):
    import ra as RA
    b = _boq(world, tick)
    from conftest import chain_ready
    chain_ready(b["id"])
    lines = [{"line_id": li["line_id"], "qty": QTY}
             for li in b["line_items"] if not li.get("is_header")]
    r = world.post(f"/ra/create?boq={b['id']}&leg=supply", data={
        "date": "2026-10-31", "ra_json": json.dumps({"lines": lines}),
        **TICKS[tick]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    bill = _newest("ra_bills")
    assert len(bill["claims"]) == 2 and {c["gst_rate"] for c in bill["claims"]} == {18.0, 12.0}
    _r1(bill, "RA bill")
    _foot_ra(bill, "RA bill")
    assert bill["grand_total"] == (round(bill["grand_total"]) if tick == "on"
                                   else bill["grand_total"])


@pytest.mark.parametrize("tick", ["on", "off"])
def test_ra_supply_and_installation_set(world, tick):
    b = _boq(world, tick)
    from conftest import chain_ready
    chain_ready(b["id"])
    data = {"boq": b["id"], "date": "2026-10-31", **TICKS[tick]}
    for li in b["line_items"]:
        if li.get("is_header"):
            continue
        for leg, rate in (("supply", RATE), ("installation", "40.33")):
            data[f"{leg}_qty_{li['line_id']}"] = QTY
            data[f"{leg}_rate_{li['line_id']}"] = rate
    r = world.post(f"/raboth/create?boq={b['id']}", data=data)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:600]
    m = _newest("merged_ras")
    legs = [STORE["ra_bills"][m["supply_ra_id"]], STORE["ra_bills"][m["installation_ra_id"]]]
    for leg in legs:
        _r1(leg, "RA leg")
        _foot_ra(leg, "RA leg")
    _r1(m, "merged RA")
    assert _p(sum(l["grand_total"] for l in legs) + m["rounding_off"]
              - sum(l["rounding_off"] for l in legs)) == _p(m["grand_total"])


@pytest.mark.parametrize("on", [True, False])
def test_payslip(on):
    import payroll as PAY
    loan = {"opening": 0.0, "deduction": 0.0, "balance": 0.0}
    rows = [{"type": PAY.ADVANCE, "amount": 100.075}, {"type": PAY.TRAVEL, "amount": 12.345}]
    s = PAY.compute({"basic": 1235.36415, "ot": 7.555}, rows, loan, 3.333, round_on=on)
    _r1(s, "payslip")
    assert _p(s["gross"] - s["total_deduction"]) == _p(s["net_raw"])
    assert _p(s["net_raw"] + s["round_off"]) == _p(s["payable"])


# ══ The printed sheet carries no third decimal in a money cell ══════════════

def test_the_printed_tax_invoice_has_no_three_decimal_amount(world):
    b = _boq(world, "off")
    world.post(f"/invoice/from-boq/{b['id']}", data={
        "date": "2026-10-31", "place_of_supply": "Karnataka",
        "advance_received": "0", "leg": "supply", "tax_type": "cgst_sgst",
        "ti_json": _picked(b), **TICKS["off"]})
    ti = _newest("invoices")
    html = world.get(f"/invoice/view/{ti['id']}").get_data(as_text=True)
    cells = re.findall(r'class="c-(?:total|price)"[^>]*>([^<]*)<', html)
    assert cells, "no money cell found — the check would pass on nothing"
    assert not [c for c in cells if re.search(r"\d\.\d{3}", c)], cells
    assert f"{ti['grand_total']:,.2f}" in html


# ══ tools/scan_paise.py — read-only, by type and number ═════════════════════

def _scan_mod():
    import importlib.util
    import pathlib
    p = pathlib.Path(__file__).resolve().parent.parent / "tools" / "scan_paise.py"
    spec = importlib.util.spec_from_file_location("scan_paise", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_scan_names_old_records_by_type_and_number_and_changes_nothing():
    import copy
    import workorder as WO
    sp = _scan_mod()
    store = {
        "boqs": {"b1": {"ref": "SF/BOQ/0007", "line_items": [
            {"supply_amount": 1142.6532000000002, "install_amount": 460.59}]}},
        "invoices": {"t1": {"ref": "SF/TI/26-27/0003", "grand_total": 1200.0,
                            "tax_info": {"CGST @ 9%": 10.0125, "cgst_rate": 9.123}}},
        "purchases": {"p1": {"ref": "SF/PO/26-27/0001", "grand_total": 11420.0,
                             "line_items": [{"qty": 12.345, "total": 1235.36}]}},
        "work_orders": {"w1": {"ref": "WO-1", "gst_rate": 18, "lines": [
            {"item_no": "1", "qty": 1, "material_rate": 0, "labour_rate": 9678}]}},
    }
    before = copy.deepcopy(store)
    found = sp.scan(store, wo_totals=WO.totals_of)
    assert store == before, "the scan wrote to the store"
    named = {(label, number) for label, number, _bad in found}
    assert named == {("BOQ", "SF/BOQ/0007"), ("Tax Invoice", "SF/TI/26-27/0003")}, found
    boq_bad = next(bad for label, _n, bad in found if label == "BOQ")
    assert boq_bad == [("line_items[0].supply_amount", 1142.6532000000002)]
    # A quantity (12.345) and a percentage rate (9.123) are not money.
    assert "SF/PO" not in sp.report(found) and "cgst_rate" not in sp.report(found)


def test_the_scan_has_no_write_mode(capsys):
    sp = _scan_mod()
    assert sp.main(["--write"]) == 2
    assert "READ-ONLY" in capsys.readouterr().out
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "tools" / "scan_paise.py").read_text()
    tree = ast.parse(src)
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "sync" not in calls, "the scan must never persist"
