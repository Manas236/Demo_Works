"""
Tests for Task 3 (Step 4): Printed RA Bill Tax Invoice document (/ra/print/<id>).
"""

import json
import pytest
import boq as BQ
import ra
from store import STORE
from test_ra_record import boq_line, make_boq, make_bill, claim


@pytest.fixture()
def clean_store(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["_boq_seeded"] = False
    yield STORE
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


def test_print_ra_renders_200_and_carries_tax_invoice_header(client, clean_store):
    line = boq_line("1", 100, s_rate=100.0)
    line["supply_hsn"] = "73063090"
    make_boq("b1", [line])
    c1 = claim("1", 10, rate=100.0)
    c1["hsn_sac"] = "73063090"

    make_bill("r1", "b1", 1, "supply", [c1], po_ref="PO-998877", po_date="2026-08-01")

    res = client.get("/ra/print/r1")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "TAX INVOICE" in html
    assert "PO-998877" in html
    assert "73063090" in html
    assert "CGST @" in html
    assert "SGST @" in html
    assert "Grand Total" in html
    assert "Bank Details" in html


def test_print_ra_renders_igst_when_tax_type_is_igst(client, clean_store):
    line = boq_line("1", 100, s_rate=100.0)
    make_boq("b1", [line])
    c1 = claim("1", 10, rate=100.0)

    make_bill("r1", "b1", 1, "supply", [c1], tax_type="igst", igst_rate=18.0, igst_amount=180.0, tax_amount=180.0, grand_total=1180.0)

    res = client.get("/ra/print/r1")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "TAX INVOICE" in html
    assert "IGST @" in html


def test_print_ra_non_existent_bill_redirects(client, clean_store):
    res = client.get("/ra/print/nonexistent")
    assert res.status_code == 302
    assert "/ra/" in res.headers["Location"]


def test_blank_hsn_sac_renders_amber_warning_badge_on_print(client, clean_store):
    line = boq_line("1", 100)
    line["supply_hsn"] = ""
    make_boq("b1", [line])
    c1 = claim("1", 10, rate=100.0)
    c1["hsn_sac"] = ""

    make_bill("r1", "b1", 1, "supply", [c1])

    res = client.get("/ra/print/r1")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Blank HSN/SAC" in html


def test_no_rendered_page_contains_doubled_rara_prefix(client, clean_store):
    line = boq_line("1", 100)
    make_boq("b1", [line])
    c1 = claim("1", 10, rate=100.0)
    rid = make_bill("r1", "b1", 1, "supply", [c1])

    for url in ["/ra/", f"/ra/create?boq=b1&leg=supply", f"/ra/view/{rid}", f"/ra/print/{rid}"]:
        res = client.get(url)
        assert res.status_code == 200
        assert "RARA" not in res.get_data(as_text=True)


def test_dashboard_contains_ra_tile(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Running Account Bills" in html
    assert "/ra/" in html


def test_clamped_schedule_preserves_post_body_and_saved_record(client, clean_store):
    header = {"line_id": "lid-head", "item_no": "1", "description": "LONG SPEC HEADER " * 20, "is_header": True}
    child = boq_line("1.1", 100, s_rate=50.0)
    make_boq("b1", [header, child])

    lid = child["line_id"]
    payload = json.dumps({"lines": [{"line_id": lid, "qty": "10", "rate": "50.0"}]})
    res = client.post("/ra/create?boq=b1&leg=supply", data={"ra_json": payload, "date": "2026-08-09"})
    assert res.status_code == 302

    saved = list(STORE["ra_bills"].values())[0]
    assert len(saved["claims"]) == 1
    assert saved["claims"][0]["line_id"] == lid
    assert saved["claims"][0]["qty"] == 10.0
    assert saved["claims"][0]["rate"] == 50.0


def test_parent_spec_header_lines_printed_on_ra_bill(client, clean_store):
    header = {"line_id": "lid-head", "item_no": "1", "description": "SPEC HEADER PARAGRAPH", "is_header": True}
    child = boq_line("1.1", 100, s_rate=50.0)
    make_boq("b1", [header, child])
    c1 = claim("1.1", 10, rate=50.0)
    c1["line_id"] = child["line_id"]

    rid = make_bill("r1", "b1", 1, "supply", [c1])
    res = client.get(f"/ra/print/{rid}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "SPEC HEADER PARAGRAPH" in html
