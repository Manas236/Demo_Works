"""
Print sweep — step 1 of 3: render every printed document in its variants.

Written for the 17 November 2026 print-clipping sweep (the title band under the
banner, ABOUT.md §2d / §6). NOT part of the suite: it needs Chromium for steps 2
and 3, and the suite runs on boxes with none — so the browser-free halves of
what it found are pinned in tests/test_print_edge.py and tests/test_merged_ra.py
instead, and this stays a tool.

It builds every document through the SAME fixtures tests/test_print_golden.py
uses — the in-memory test store, never a real database — and writes each
variant's HTML to $SWEEP_OUT/<document>__<variant>.html:

    normal     the golden record as pinned
    stress     very long party names and multi-line addresses, long item
               descriptions, 64 lines (runs to several pages), 13-digit
               amounts kept under Rs 1,000 crore (see ABOUT.md §7 gap 119)
    sparse     PO No / PO date, HSN, GSTIN, notes blank
    signed     a signature and a stamp set (docsheet._sig_art)
    draft / cancelled   where the document has the overprint
    and every copy label: copy-set documents print the whole set.

Run from the repository root (PYTHONPATH puts the suite's conftest on the path,
`-p conftest` loads its fixtures, and the file is named so that a plain
`python -m pytest` never collects it):

    SWEEP_OUT=/tmp/sweep/html PYTHONPATH=.:tests \
        python -m pytest -q -p conftest -p no:cacheprovider tools/print_sweep/render_variants.py
    node tools/print_sweep/print_sweep.js /tmp/sweep/html /tmp/sweep
    python tools/print_sweep/pdf_check.py /tmp/sweep
    python tools/print_sweep/contact_sheets.py /tmp/sweep/png /tmp/sweep/sheets

Then LOOK at the sheets — the checks find candidates, they do not judge them.
"""
import base64
import copy
import io
import os
import pathlib

import pytest

import branding as B
from store import STORE
from test_print_golden import (  # noqa: F401
    GOLD_DC, GOLD_DPO, GOLD_MERGED, GOLD_MS, GOLD_MS_LEGACY, GOLD_PI, GOLD_PO,
    GOLD_Q, GOLD_RA_INSTALL, GOLD_TI, golden, golden_dc, golden_dpo,
    golden_merged, golden_ms, golden_ms_legacy, golden_ra, pinned_identity)
from test_work_orders import GOLD_WO, golden_wo  # noqa: F401

OUT = pathlib.Path(os.environ.get("SWEEP_OUT", "/tmp/sweep"))
OUT.mkdir(parents=True, exist_ok=True)

LONG_NAME = ("Maharashtra Industrial Infrastructure & Fire Life-Safety "
             "Developers Consortium Private Limited (Western Region Projects Division)")
LONG_ADDR = ("Unit No. 1407-1412, Fourteenth Floor, Tower B, Lodha Supremus "
             "Business Park\nOpposite New Passport Office, Road No. 22, Wagle "
             "Industrial Estate, Thane (West)\nNear Mulund Check Naka, Off Eastern "
             "Express Highway, Thane District\nMaharashtra - 400604, India\n"
             "Kind Attention: Mr Venkataramanan Subramaniam Iyer, Senior General "
             "Manager (Projects & Procurement)")
LONG_DESC = ("Supply, installation, testing and commissioning of MS heavy duty "
             "'C' class ERW black steel pipe conforming to IS 1239 (Part 1) / "
             "IS 3589 with all fittings such as elbows, tees, reducers, flanges, "
             "nuts, bolts and gaskets, including cutting, threading, welding, "
             "two coats of red oxide primer and two coats of synthetic enamel "
             "paint, supports, clamps and hydro-testing at 15 kg/cm2 for 2 hours")
BIG = 99999999.99
N = 64


def _png(color, w=400, h=190):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, w - 10, h - 10), outline=color, width=8)
    d.line((20, h // 2, w - 20, h // 3), fill=color, width=6)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def signed():
    saved = (B.SIGNATURE_IMAGE, B.STAMP_IMAGE)
    B.SIGNATURE_IMAGE, B.STAMP_IMAGE = _png((10, 30, 140, 255)), _png((20, 60, 200, 255), 300, 300)
    yield
    B.SIGNATURE_IMAGE, B.STAMP_IMAGE = saved


def dump(client, name, url):
    r = client.get(url)
    assert r.status_code == 200, (name, url, r.status_code)
    (OUT / f"{name}.html").write_text(r.get_data(as_text=True), encoding="utf-8")


def _variants(client, coll, rid, url, name, stress, sparse, extra=()):
    base = copy.deepcopy(STORE[coll][rid])
    dump(client, f"{name}__normal", url)
    for vname, fn in (("stress", stress), ("sparse", sparse)) + tuple(extra):
        rec = copy.deepcopy(base)
        fn(rec)
        STORE[coll][rid] = rec
        dump(client, f"{name}__{vname}", url)
    STORE[coll][rid] = base


def _lines(n=N):
    out = []
    for i in range(n):
        out.append({"type": "item", "name": f"{i+1}. {LONG_DESC}" if i % 3 == 0
                    else f"Item {i+1}: 150 mm butterfly valve, PN16, with gear operator",
                    "part_no": f"PART-{i:05d}-XL", "hsn": "84818090", "qty": 99999.0,
                    "unit": "Nos", "price": 9999999.99, "total": BIG, "depth": 0})
    return out


def _party(rec):
    for k in ("account_name", "vendor_name", "contractor_name", "consignee_name",
              "ship_acct_name", "project_name"):
        if k in rec:
            rec[k] = LONG_NAME
    for k in ("to", "consignee_addr"):
        if k in rec:
            rec[k] = LONG_NAME + "\n" + LONG_ADDR
    for k in ("ship_addr", "site_location", "delivery_to"):
        if k in rec:
            rec[k] = LONG_ADDR.replace("\n", ", ")
    if "contact_person" in rec:
        rec["contact_person"] = "Mr Venkataramanan Subramaniam Iyer"
    for k in ("notes",):
        if k in rec:
            rec[k] = (LONG_DESC + ". ") * 2


def _money_big(rec):
    for k in ("subtotal", "grand_total", "net_payable", "amount_due"):
        if k in rec:
            rec[k] = BIG * 10
    if "tax_info" in rec:
        rec["tax_info"] = {"CGST": BIG, "SGST": BIG, "total": BIG * 2,
                           "cgst_rate": 9.0, "sgst_rate": 9.0}


def _sparse_common(rec):
    for k in ("po_number", "po_date", "po_no", "po_ref", "bill_gstin", "vendor_gstin",
              "contractor_gstin", "ship_gstin", "notes", "contact_person"):
        if k in rec:
            rec[k] = ""
    for li in rec.get("line_items") or []:
        li["hsn"] = ""


# ── Tax invoice, proforma, quotation, purchase order ─────────────────────────

def test_sell_side(client, golden):
    def stress(rec):
        _party(rec); rec["line_items"] = _lines(); _money_big(rec)
    for coll, rid, url, name in (
            ("invoices", GOLD_TI, f"/invoice/view/{GOLD_TI}", "tax_invoice"),
            ("proformas", GOLD_PI, f"/proforma/view/{GOLD_PI}", "proforma"),
            ("quotations", GOLD_Q, f"/quotation/view/{GOLD_Q}", "quotation"),
            ("purchases", GOLD_PO, f"/purchase/view/{GOLD_PO}", "purchase_order")):
        extra = ()
        if coll == "invoices":
            extra = (("cancelled", lambda r: r.update(status="cancelled",
                      cancelled_on="2026-06-01", cancel_reason="Wrong place of supply")),)
        _variants(client, coll, rid, url, name, stress, _sparse_common, extra)


def test_sell_side_signed(client, golden, signed):
    dump(client, "tax_invoice__signed", f"/invoice/view/{GOLD_TI}")
    dump(client, "proforma__signed", f"/proforma/view/{GOLD_PI}")
    dump(client, "quotation__signed", f"/quotation/view/{GOLD_Q}")
    dump(client, "purchase_order__signed", f"/purchase/view/{GOLD_PO}")


# ── RA bills (supply + installation), merged, BOQ ─────────────────────────────

def _stress_boq_and_ras():
    import ra
    boq = STORE["boqs"]["gold-boq"]
    _party(boq)
    head = boq["line_items"][0]
    kids = []
    for i in range(N):
        kids.append(dict(boq["line_items"][1], line_id=f"k{i:011d}",
                         item_no=f"24.{i+1}", description=(LONG_DESC if i % 4 == 0
                         else f"{50 + i} mm dia, ERW, 'C' class"),
                         area_qty={"T1": 99999.0}, total_qty=99999.0,
                         supply_rate=99999.99, supply_amount=BIG,
                         install_rate=9999.0, install_amount=BIG / 10))
    boq["line_items"] = [head] + kids
    for bid in [b for b in STORE["ra_bills"]]:
        bill = STORE["ra_bills"][bid]
        leg = bill.get("leg", "supply")
        claims = [ra.build_claim(k, 999.0, 99999.99, 0.0, 99999.99, leg=leg,
                                 hsn_sac="73063090", gst_rate=18.0) for k in kids]
        sub, drows, dtot, net = ra.bill_totals(claims, [])
        bill.update(ra.compute_tax_totals(claims, [], "cgst_sgst", 9.0, 9.0, 18.0))
        bill.update(claims=claims, claim_subtotal=sub, deductions=drows,
                    deduction_total=dtot, net_payable=net)
        _party(bill)


def test_ra_and_boq(client, golden_ra, golden_merged):
    snap = copy.deepcopy({k: STORE[k] for k in ("boqs", "ra_bills", "merged_ras")})
    urls = (("ra_supply", "/ra/print/gold-ra"),
            ("ra_installation", f"/ra/print/{GOLD_RA_INSTALL}"),
            ("merged_ra", f"/merged/print/{GOLD_MERGED}"),
            ("boq", "/boq/print/gold-boq"))
    for name, url in urls:
        dump(client, f"{name}__normal", url)
    _stress_boq_and_ras()
    _party(STORE["merged_ras"][GOLD_MERGED])
    for name, url in urls:
        dump(client, f"{name}__stress", url)
    for k, v in snap.items():
        STORE[k].clear(); STORE[k].update(copy.deepcopy(v))
    for b in STORE["ra_bills"].values():
        _sparse_common(b)
        for c in b.get("claims") or []:
            c["hsn_sac"] = ""
    _sparse_common(STORE["merged_ras"][GOLD_MERGED])
    _sparse_common(STORE["boqs"]["gold-boq"])
    for name, url in urls:
        dump(client, f"{name}__sparse", url)
    for k, v in snap.items():
        STORE[k].clear(); STORE[k].update(copy.deepcopy(v))
    STORE["ra_bills"]["gold-ra"].update(status="cancelled", cancelled_on="2026-06-09",
                                       cancel_reason="Claimed against the wrong BOQ revision")
    dump(client, "ra_supply__cancelled", "/ra/print/gold-ra")
    STORE["ra_bills"]["gold-ra"].update(status="draft")
    dump(client, "ra_supply__draft", "/ra/print/gold-ra")
    STORE["ra_bills"]["gold-ra"].update(status="issued")
    STORE["merged_ras"][GOLD_MERGED].update(status="cancelled", cancelled_on="2026-06-21",
                                           cancel_reason="Superseded")
    dump(client, "merged_ra__cancelled", f"/merged/print/{GOLD_MERGED}")
    for k, v in snap.items():
        STORE[k].clear(); STORE[k].update(copy.deepcopy(v))


def test_ra_signed(client, golden_ra, golden_merged, signed):
    dump(client, "ra_supply__signed", "/ra/print/gold-ra")
    dump(client, "merged_ra__signed", f"/merged/print/{GOLD_MERGED}")
    dump(client, "boq__signed", "/boq/print/gold-boq")


# ── Challan, draft PO, work order, measurement ────────────────────────────────

def _items(n=N, key="description"):
    return [{"line_id": f"i{i:011d}", "is_header": i % 16 == 0, "item_no": str(i + 1),
             key: (LONG_DESC if i % 5 == 0 else f"{80 + i} mm Butterfly valve - SANT, PN16"),
             "unit": "Nos", "qty": 99999.0, "pcs": "999"} for i in range(n)]


def test_challan_dpo(client, golden_ra, golden_dc, golden_dpo):
    def dc_stress(r):
        _party(r); r["items"] = _items(); r["dispatch_to"] = LONG_ADDR.replace("\n", ", ")
    _variants(client, "delivery_challans", GOLD_DC, f"/dc/print/{GOLD_DC}", "challan",
              dc_stress, _sparse_common)

    def dpo_stress(r):
        _party(r); r["items"] = _items()
    _variants(client, "purchase_orders", GOLD_DPO, f"/po/print/{GOLD_DPO}", "draft_po",
              dpo_stress, _sparse_common)


def test_challan_signed(client, golden_ra, golden_dc, golden_dpo, signed):
    dump(client, "challan__signed", f"/dc/print/{GOLD_DC}")
    dump(client, "draft_po__signed", f"/po/print/{GOLD_DPO}")


def test_work_order(client, golden_wo):
    def stress(r):
        _party(r)
        r["lines"] = [{"line_id": f"w{i:011d}", "item_no": str(i + 1), "unit": "Mtrs",
                       "description": LONG_DESC if i % 4 == 0 else f"Line {i+1}\nwith clamps",
                       "qty": 999.0, "material_rate": 99999.99, "labour_rate": 9999.99}
                      for i in range(N)]
    _variants(client, "work_orders", GOLD_WO, f"/wo/print/{GOLD_WO}", "work_order",
              stress, _sparse_common,
              (("draft", lambda r: r.update(status="draft")),
               ("cancelled", lambda r: r.update(status="cancelled", cancelled_on="2026-10-09",
                                                cancel_reason="Contractor withdrew"))))


def test_work_order_signed(client, golden_wo, signed):
    dump(client, "work_order__signed", f"/wo/print/{GOLD_WO}")


def test_measurement(client, golden_ra, golden_ms, golden_ms_legacy):
    def stress(r):
        _party(r)
        r["location"] = LONG_ADDR.replace("\n", ", ")
        r["grid_rows"] = [{"label": f"Floor {i} riser {i}", "values": {
            "d25": 99999.99, "d100": 9999.5, "msa": 999.0, "d150": 99999.0},
            "remarks": LONG_DESC[:140] if i % 3 == 0 else ""} for i in range(N)]
        r["items"] = [dict(it, boq_qty=99999.0) for it in _items()]
    _variants(client, "measurements", GOLD_MS, f"/measurement/print/{GOLD_MS}",
              "joint_measurement", stress, _sparse_common)

    def lstress(r):
        _party(r); r["items"] = [dict(it, boq_qty=99999.0) for it in _items()]
    _variants(client, "measurements", GOLD_MS_LEGACY,
              f"/measurement/print/{GOLD_MS_LEGACY}", "measurement_legacy",
              lstress, _sparse_common)


# ── Payslips ────────────────────────────────────────────────────────────────

def _payroll_seed(long=False):
    import attendance as AT
    import payroll as PAY
    for c in ("employees", "attendance", "pay_entries", "payslips", "pay_imports"):
        STORE.setdefault(c, {}).clear()
    ids = []
    people = [("amit", "AMIT KUMAR YADAV", 550.0), ("pk", "PUSHKAR MISHRA", 833.0),
              ("mn", "MAHESH NANAWARE", 1000.0)]
    if long:
        people = [(f"p{i}", ("VENKATARAMANAN SUBRAMANIAM IYER RAMAKRISHNAN "
                             "CHANDRASEKHARAN") + f" {i}", 99999.0) for i in range(3)]
    for eid, name, rate in people:
        STORE["employees"][eid] = {"id": eid, "name": name, "code": "EMP-000123456",
                                   "designation": ("Senior Fire Protection Systems Site "
                                                   "Supervisor (Hydrant & Sprinkler)") if long
                                   else "Helper", "active": True, "day_rate": rate}
        for d in range(1, 31):
            rid = f"{eid}-{d}"
            STORE["attendance"][rid] = {
                "id": rid, "date": f"2026-09-{d:02d}", "employee_id": eid,
                "employee_name": name, "employee_code": "", "day_rate": rate,
                "site": "", "status": AT.PRESENT, "ot_hours": 3.0}
        k = f"{eid}-adv"
        STORE["pay_entries"][k] = {"id": k, "employee_id": eid, "employee_name": "",
                                   "date": "2026-09-30", "type": PAY.ADVANCE,
                                   "amount": 5000.0, "note": "", "source": PAY.SOURCE_MANUAL}
        k = f"{eid}-loan"
        STORE["pay_entries"][k] = {"id": k, "employee_id": eid, "employee_name": "",
                                   "date": "2026-09-01", "type": PAY.OPENING_LOAN,
                                   "amount": 24200.0, "note": "", "source": PAY.SOURCE_MANUAL}
        ids.append(eid)
    return ids


def test_payslips(client, pinned_identity):
    import payroll as PAY
    for long in (False, True):
        tag = "stress" if long else "normal"
        ids = _payroll_seed(long)
        slips = [PAY.create_draft(e, "2026-09")[0] for e in ids]
        dump(client, f"payslip__draft_{tag}", f"/payroll/slip/print/{slips[0]['id']}")
        for s in slips:
            PAY.issue(s)
        dump(client, f"payslip__{tag}", f"/payroll/slip/print/{slips[0]['id']}")
        dump(client, f"payslip_month__{tag}", "/payroll/print-month?month=2026-09")
        qs = "&".join(f"emp={e}" for e in ids)
        r = client.get(f"/payroll/print-selected?month=2026-09&{qs}")
        if r.status_code == 200:
            (OUT / f"payslip_selected__{tag}.html").write_text(r.get_data(as_text=True))
        if not long:
            PAY.cancel(slips[1], "Wrong month")
            dump(client, "payslip__cancelled", f"/payroll/slip/print/{slips[1]['id']}")
