"""
Tests for Task 1 (Step 3): RA Register and Certification Entry UI.
"""

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


def test_register_renders_for_zero_bills(client, clean_store):
    res = client.get("/ra/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Register" in html
    assert "No Running Account bills yet" in html


def test_register_renders_for_one_and_many_bills(client, clean_store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "b1", 2, "installation", [claim("1", 20)])

    res = client.get("/ra/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "RA1" in html
    assert "RA2" in html
    assert "supply" in html
    assert "installation" in html
    assert "Latest" in html


def test_three_state_certification_display(clean_store):
    make_boq("b1", [boq_line("1", 100), boq_line("2", 100)])
    
    # None certified
    r1_claims = [claim("1", 30), claim("2", 20)]
    make_bill("r1", "b1", 1, "supply", r1_claims)
    b1 = STORE["ra_bills"]["r1"]
    badge1 = ra.certification_status_badge(b1)
    assert "None" in badge1

    # Partial certified
    r2_claims = [claim("1", 30), claim("2", 20)]
    r2_claims[0]["certified_qty"] = 30.0
    r2_claims[0]["certified_rate"] = 100.0
    make_bill("r2", "b1", 2, "supply", r2_claims)
    b2 = STORE["ra_bills"]["r2"]
    badge2 = ra.certification_status_badge(b2)
    assert "Partial" in badge2

    # Full certified
    r3_claims = [claim("1", 30), claim("2", 20)]
    r3_claims[0]["certified_qty"] = 30.0
    r3_claims[0]["certified_rate"] = 100.0
    r3_claims[1]["certified_qty"] = 20.0
    r3_claims[1]["certified_rate"] = 100.0
    make_bill("r3", "b1", 3, "supply", r3_claims)
    b3 = STORE["ra_bills"]["r3"]
    badge3 = ra.certification_status_badge(b3)
    assert "Full" in badge3


def test_none_vs_zero_round_trip_through_post(client, clean_store):
    make_boq("b1", [boq_line("1", 100), boq_line("2", 100)])
    c1 = claim("1", 30)
    c2 = claim("2", 20)
    make_bill("r1", "b1", 1, "supply", [c1, c2])

    lid1 = c1["line_id"]
    lid2 = c2["line_id"]

    # POST: cert_qty for lid1 is blank (""), for lid2 is "0"
    res = client.post("/ra/certify/r1", data={
        "status": "submitted",
        "certified_on": "2026-08-09",
        f"cert_qty_{lid1}": "",
        f"cert_rate_{lid1}": "",
        f"cert_qty_{lid2}": "0",
        f"cert_rate_{lid2}": "100.0",
    }, follow_redirects=True)
    assert res.status_code == 200

    b1 = STORE["ra_bills"]["r1"]
    c1_updated = [c for c in b1["claims"] if c["line_id"] == lid1][0]
    c2_updated = [c for c in b1["claims"] if c["line_id"] == lid2][0]

    assert c1_updated["certified_qty"] is None
    assert c2_updated["certified_qty"] == 0.0


def test_certification_works_on_non_latest_bill(client, clean_store):
    make_boq("b1", [boq_line("1", 100)])
    c1 = claim("1", 30)
    make_bill("r1", "b1", 1, "supply", [c1])
    make_bill("r2", "b1", 2, "supply", [claim("1", 20)])

    b1 = STORE["ra_bills"]["r1"]
    assert ra.claim_is_frozen(b1) is True

    lid1 = c1["line_id"]
    res = client.post("/ra/certify/r1", data={
        "status": "certified",
        "certified_on": "2026-08-09",
        f"cert_qty_{lid1}": "30.0",
        f"cert_rate_{lid1}": "100.0",
    }, follow_redirects=True)
    assert res.status_code == 200

    b1_updated = STORE["ra_bills"]["r1"]
    assert b1_updated["status"] == "certified"
    c1_updated = b1_updated["claims"][0]
    assert c1_updated["certified_qty"] == 30.0


def test_delete_still_refuses_certified_bill(client, clean_store):
    make_boq("b1", [boq_line("1", 100)])
    c1 = claim("1", 30)
    c1["certified_qty"] = 30.0
    c1["certified_rate"] = 100.0
    make_bill("r1", "b1", 1, "supply", [c1])

    b1 = STORE["ra_bills"]["r1"]
    allowed, why = ra.can_delete(b1)
    assert allowed is False
    assert "carries certification data" in why

    res = client.post("/ra/delete/r1", follow_redirects=True)
    assert res.status_code == 200
    assert "r1" in STORE["ra_bills"]
