"""
The rupee round-off, the unsaved-form Resume, and the library's lump-sum filter.

31 October 2026, CLIENT_CHANGES.md §0 sixty-second block. Yogesh, on the call:
a PO showed ₹11,419.80 — the final amount must be a whole rupee, .50 and above
up, below .50 down; and pressing Back on a half-made PO lost every line.
"""

import json

import pytest

import address
import roundoff as RO
import formdraft as FD
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"


# ══ 1. The rule ═════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw, want", [
    (11419.80, 11420.0), (11419.50, 11420.0), (11419.49, 11419.0),
    (2.5, 3.0), (3.5, 4.0), (0.0, 0.0), (100.0, 100.0), (2395.40, 2395.0)])
def test_half_up_not_round_to_even(raw, want):
    assert RO.rupee(raw) == want


def test_split_returns_the_signed_difference():
    assert RO.split(11419.80) == (11420.0, 0.2)
    assert RO.split(11419.40) == (11419.0, -0.4)
    assert RO.label(0.2) == "+0.20" and RO.label(-0.4) == "-0.40"


def test_roundoff_is_a_leaf():
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "roundoff.py").read_text()
    mods = {n.module if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [n])}
    assert mods <= {"decimal"}


# ══ 2. The purchase order ═══════════════════════════════════════════════════

def _po_form(rate, qty=1, **extra):
    d = {"date": "2026-10-31", "vendor_id": VENDOR_ID, "status": "Draft",
         "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0",
         "extra_desc": ["Gasket"], "extra_unit": ["Nos"], "extra_qty": [str(qty)],
         "extra_rate": [str(rate)], "extra_discount": [""]}
    d.update(extra)
    return d


def test_a_new_po_is_rounded_and_prints_its_round_off(client):
    address.ensure_demo_addresses()
    # 9678 + 18% = 11,420.04 → 11,420, round off -0.04
    r = client.post("/purchase/create", data=_po_form(9678))
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    po = list(STORE["purchases"].values())[-1]
    assert po["grand_total"] == 11420.0 and po["round_off"] == -0.04
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Round off" in html and "-0.04" in html and "11,420.00" in html


def test_a_whole_rupee_po_prints_no_round_off_row(client):
    address.ensure_demo_addresses()
    assert client.post("/purchase/create", data=_po_form(1000)).status_code == 302
    po = list(STORE["purchases"].values())[-1]
    assert po["round_off"] == 0.0
    assert "Round off" not in client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)


def test_an_old_po_without_round_off_prints_as_it_did(client):
    address.ensure_demo_addresses()
    assert client.post("/purchase/create", data=_po_form(9678)).status_code == 302
    po = list(STORE["purchases"].values())[-1]
    po.pop("round_off")
    po["grand_total"] = 11420.04
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Round off" not in html and "11,420.04" in html


# ══ 3. The RA bill: .50 now goes UP ═════════════════════════════════════════

def test_ra_rounding_is_half_up():
    import ra
    assert ra.compute_rounding_off(100.50) == (0.5, 101.0)
    assert ra.compute_rounding_off(101.50) == (0.5, 102.0)
    assert ra.compute_rounding_off(100.49) == (-0.49, 100.0)


# ══ 4. The work order — only from today ═════════════════════════════════════

def test_a_new_work_order_rounds_and_an_old_one_does_not():
    import workorder as WO
    line = {"item_no": "1", "description": "Labour", "unit": "Nos", "qty": 1,
            "material_rate": 0, "labour_rate": 9678}
    old = {"lines": [line], "gst_rate": 18}
    new = {"lines": [line], "gst_rate": 18, "rounds_to_rupee": True}
    assert WO.totals_of(old)["total"] == 11420.04 and WO.totals_of(old)["round_off"] == 0.0
    t = WO.totals_of(new)
    assert t["total"] == 11420.0 and t["round_off"] == -0.04


# ══ 5. The proforma and the tax invoice off a BOQ ═══════════════════════════

def test_boq_figures_round_the_invoice_value():
    import proforma
    items = [{"type": "item", "name": "x", "qty": 1, "price": 9678.0, "total": 9678.0,
              "gst_rate": 18.0, "hsn": ""}]
    _sub, tax, grand, _q = proforma.boq_figures(items, "cgst_sgst")
    assert grand == RO.rupee(9678.0 + tax["total"])
    assert grand == round(grand)


# ══ 6. Resume an unsaved purchase order ═════════════════════════════════════

def test_the_create_page_carries_the_draft_script(client):
    address.ensure_demo_addresses()
    html = client.get("/purchase/create").get_data(as_text=True)
    assert "draft:' + location.pathname" in html
    assert "var RESUMED = false;" in html


def test_a_resume_post_redraws_and_never_saves(client):
    address.ensure_demo_addresses()
    before = len(STORE["purchases"])
    data = _po_form(555, qty=3)
    data[FD.RESUME_FIELD] = "1"
    r = client.post("/purchase/create", data=data)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert len(STORE["purchases"]) == before
    assert 'value="Gasket"' in html                 # the typed part came back
    assert "var RESUMED = true;" in html            # and the banner is not re-offered
    assert 'class="alert alert-error"' not in html  # a redraw, not a refusal


def test_a_resume_does_not_spend_a_document_number(client):
    import series as SER
    import pipeline as P
    address.ensure_demo_addresses()
    want = SER.next_seq("PO", P.fy_of("2026-10-31"))
    data = _po_form(555)
    data[FD.RESUME_FIELD] = "1"
    client.post("/purchase/create", data=data)
    assert SER.next_seq("PO", P.fy_of("2026-10-31")) == want


def test_formdraft_is_a_leaf_and_escapes_its_word():
    assert "<b>unsaved a&lt;b&gt;</b>" in FD.script("form", "a<b>")
    assert FD.is_resume({"_resume": "1"}) and not FD.is_resume({})


# ══ 7. The library skips lump-sum and percentage lines ══════════════════════

def test_lump_sum_and_percentage_lines_are_not_learned():
    import boq as BQ
    lines = [
        {"line_id": "aaaaaaaaac01", "is_header": False, "description": "Design in BIM",
         "unit": "Lot.", "supply_rate": 1.0},
        {"line_id": "aaaaaaaaac02", "is_header": False, "description": "Fire NOC",
         "unit": "LS", "supply_rate": 1.0},
        {"line_id": "aaaaaaaaac03", "is_header": False,
         "description": "Fittings, transportation @ 20% of the supply total",
         "unit": "Nos", "supply_rate": 1.0},
        {"line_id": "aaaaaaaaac04", "is_header": False, "description": "Gate valve 80mm",
         "unit": "Nos", "supply_rate": 1.0},
    ]
    got = [c["spec_text"] for c in BQ.library_payload({"line_items": lines})]
    assert got == ["Gate valve 80mm"]
