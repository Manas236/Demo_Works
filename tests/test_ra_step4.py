"""
Tests for Task 3 (Step 4): Printed RA Bill Tax Invoice document (/ra/print/<id>).
"""

import json
import re

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


def test_amount_in_words_carries_exactly_one_inr(client, clean_store):
    """`_amount_in_words()` supplies its own prefix. The page printed both."""
    line = boq_line("1", 100, s_rate=100.0)
    make_boq("b1", [line])
    c1 = claim("1", 10, rate=100.0)
    rid = make_bill("r1", "b1", 1, "supply", [c1])

    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    words = re.search(r'class="amount-words">(.*?)</div>', html, re.S).group(1)
    assert words.count("INR") == 1, words.strip()
    assert "INR INR" not in html


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
    assert "add HSN/SAC code" in html   # the house amber chip, as on the tax invoice


def test_no_rendered_page_contains_doubled_rara_prefix(client, clean_store):
    line = boq_line("1", 100)
    make_boq("b1", [line])
    c1 = claim("1", 10, rate=100.0)
    rid = make_bill("r1", "b1", 1, "supply", [c1])

    for url in ["/ra/", f"/ra/create?boq=b1&leg=supply", f"/ra/view/{rid}", f"/ra/print/{rid}"]:
        res = client.get(url)
        assert res.status_code == 200
        assert "RARA" not in res.get_data(as_text=True)


def test_boq_facts_takes_the_ra_number_and_owns_the_prefix(client, clean_store):
    """
    `RARA1 · supply` was fixed by making `_boq_facts()` sniff for a leading
    "RA" and skip its own prefix. That left one parameter carrying two
    contracts — an integer from five call sites and a pre-formatted string from
    `_entry_form` — with nothing to stop the next caller picking the wrong one.

    The parameter is the integer. This pins that, both ways: the number renders
    with exactly one prefix, and a pre-formatted string is now a loud error at
    the call rather than a quiet doubling on the page.
    """
    make_boq("b1", [boq_line("1", 100)])
    boq = STORE["boqs"]["b1"]

    assert "RA7 &middot; supply" in ra._boq_facts(boq, "supply", 7)

    with pytest.raises((TypeError, ValueError)):
        ra._boq_facts(boq, "supply", "RA7")

    # And the two real callers hand it the number, not their heading.
    html = client.get("/ra/create?boq=b1&leg=supply").get_data(as_text=True)
    assert "<h1>RA1</h1>" in html
    assert "RA1 &middot; supply" in html


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


# ═══ The family fold — presentation only ═══════════════════════════════════
#
# `tests/test_ra_collapse_js.py` runs the real toggles under Node and diffs the
# payload. These are the server half: what the page emits, and what survives a
# POST from it.

def test_a_folded_family_is_hidden_and_never_dropped_from_the_form(client, clean_store):
    """
    The hard constraint on the whole fold: **every BOQ line still renders and
    every input is still in the document.** Folding a family sets
    `display:none` on its rows; it does not remove them, because a removed row
    posts nothing and the claim would go out short in silence.
    """
    header, child = _family("LONG SPEC HEADER " * 20)
    second = boq_line("1.2", 60, s_rate=70.0)
    second["parent_item_no"] = "1"
    solo = boq_line("2", 40, s_rate=90.0)
    make_boq("b1", [header, child, second, solo])

    html = client.get("/ra/create?boq=b1&leg=supply").get_data(as_text=True)

    for line in (child, second, solo):
        assert f'id="q_{line["line_id"]}"' in html
        assert f'id="r_{line["line_id"]}"' in html

    # Collapsed by default, and only the children.
    assert f'id="row_{child["line_id"]}"' in html
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    assert body.count('style="display:none;"') == 2
    assert f'id="row_{solo["line_id"]}"' in body
    assert 'cl-line is-child' in body
    assert 'style="display:none;"' not in re.search(
        rf'<tr class="cl-line[^>]*id="row_{solo["line_id"]}"[^>]*>', body).group(0)

    # Wired to the header's own line_id, and told how big the family is.
    assert f"""onclick="toggleFamily('{header['line_id']}')\"""" in html
    assert "spec &middot; 2 items" in html
    assert "Expand all" in html and "Collapse all" in html


def test_a_claim_saved_from_a_folded_family_is_identical_to_one_saved_open(client, clean_store):
    """
    The fold is not in the payload and not in the record. The same POST body a
    folded page produces is the one an expanded page produces, and it saves the
    same bill either way.
    """
    header, child = _family()
    make_boq("b1", [header, child])
    lid = child["line_id"]

    payload = json.dumps({"lines": [{"line_id": lid, "qty": "10", "rate": "50.0"}]})
    res = client.post("/ra/create?boq=b1&leg=supply",
                      data={"ra_json": payload, "date": "2026-08-09"})
    assert res.status_code == 302
    saved = list(STORE["ra_bills"].values())[0]

    assert len(saved["claims"]) == 1
    assert saved["claims"][0]["line_id"] == lid
    assert saved["claims"][0]["qty"] == 10.0
    assert saved["claims"][0]["rate"] == 50.0
    assert saved["claim_subtotal"] == 500.0


def test_a_family_opens_on_arrival_when_one_of_its_children_carries_a_figure(client, clean_store):
    """
    boq.py's contract: a rejected POST forces the offending line open, because
    a complaint about line 47 that leaves line 47 shut is worse than no
    validation. Same rule here, and it is also what makes `/ra/edit` show the
    lines the bill actually claimed instead of a wall of shut headers.
    """
    header, child = _family()
    make_boq("b1", [header, child])
    lid = child["line_id"]

    # A POST that fails the over-claim block: 900 against an approved 100.
    payload = json.dumps({"lines": [{"line_id": lid, "qty": "900", "rate": "50"}]})
    res = client.post("/ra/create?boq=b1&leg=supply",
                      data={"ra_json": payload, "date": "2026-08-09"})
    assert res.status_code == 200                      # re-rendered, not saved
    html = res.get_data(as_text=True)

    assert not STORE["ra_bills"]
    assert 'data-open="1"' in html
    row = re.search(rf'<tr class="cl-line[^>]*id="row_{lid}"[^>]*>', html).group(0)
    assert "display:none" not in row, "the rejected line came back folded away"
    assert 'value="900"' in html                       # and nothing was lost


def test_child_descriptions_are_sent_in_full_and_only_headers_are_clamped(client, clean_store):
    """
    `white-space:nowrap` on the description column of a CLAIM ENTRY table is
    wrong even with the fold: the operator is matching a paper measurement
    sheet to a row, and hover-to-reveal fails on touch and fails again with two
    documents side by side. Child lines wrap to two lines and carry their whole
    description; the parent header, which holds a paragraph, stays clamped.
    """
    long_child_desc = "150mm dia ISI heavy duty C class pipe with all fittings " * 4
    header, child = _family("HEADER PARAGRAPH " * 30)
    child["description"] = long_child_desc
    make_boq("b1", [header, child])

    html = client.get("/ra/create?boq=b1&leg=supply").get_data(as_text=True)

    assert long_child_desc.strip() in html             # in full, in the cell
    assert 'class="cl-clamp"' in html
    assert "…" in html                                 # the header, truncated
    assert 'class="ls-desc"' in html
    # The claim rows must not be nowrap any more.
    assert ".cl-desc  { min-width:180px; max-width:280px; }" in html


def test_no_ui_state_reaches_an_ra_record(client, clean_store):
    """
    `ra.clean_claims()` keeps the record clean **by construction**, not by
    stripping — the same call `boq._clean_lines()` makes. It reads three keys
    off a posted line (`line_id`, `qty`, `rate`) and takes everything else from
    the approved BOQ line, then `build_claim()` returns a fresh dict of named
    keys. There is no path by which an extra key in the payload can land in a
    claim row, whatever the editor decides to post next.
    """
    header, child = _family()
    make_boq("b1", [header, child])

    payload = json.dumps({"lines": [{
        "line_id": child["line_id"], "qty": "10", "rate": "50",
        "_open": True, "_collapsed": False, "_spec": "x", "_auto": {"qty": 1},
        "amount": 999999.0, "approved_qty": 999999.0, "certified_qty": 42.0,
        "item_no": "SPOOFED", "description": "SPOOFED", "hsn_sac": "SPOOFED",
    }]})
    res = client.post("/ra/create?boq=b1&leg=supply",
                      data={"ra_json": payload, "date": "2026-08-09"})
    assert res.status_code == 302

    row = list(STORE["ra_bills"].values())[0]["claims"][0]
    assert not [k for k in row if k.startswith("_")]
    assert "SPOOFED" not in json.dumps(row)
    assert row["amount"] == 500.0                      # recomputed, not taken
    assert row["approved_qty"] == 100.0                # from the BOQ
    # `certified_qty` used to be asserted `is None` here — never postable, but
    # present on the row. Certification is gone entirely (CLIENT_CHANGES.md item
    # 3), so the posted key must not survive onto the record AT ALL, which is
    # the stronger form of the same assertion.
    assert "certified_qty" not in row
    assert row["item_no"] == "1.1"                     # snapshot off the BOQ


def _family(header_desc="SPEC HEADER PARAGRAPH"):
    """A spec header and one child that really is under it — the Sify shape."""
    header = boq_line("1", 0, header=True)
    header["description"] = header_desc
    child = boq_line("1.1", 100, s_rate=50.0)
    child["parent_item_no"] = "1"
    return header, child


def test_parent_spec_header_lines_printed_on_ra_bill(client, clean_store):
    header, child = _family()
    make_boq("b1", [header, child])
    c1 = claim("1.1", 10, rate=50.0)
    c1["line_id"] = child["line_id"]

    rid = make_bill("r1", "b1", 1, "supply", [c1])
    res = client.get(f"/ra/print/{rid}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "SPEC HEADER PARAGRAPH" in html


def test_spec_header_with_nothing_claimed_under_it_is_not_printed(client, clean_store):
    """
    The header is context for the lines being claimed. A family where nothing
    was claimed has no place on this bill's invoice — printing it states that a
    specification is part of a claim that does not mention it.
    """
    header, child = _family("UNCLAIMED FAMILY HEADER")
    other = boq_line("2", 100, s_rate=50.0)
    make_boq("b1", [header, child, other])

    c1 = claim("2", 4, rate=50.0)
    c1["line_id"] = other["line_id"]
    rid = make_bill("r1", "b1", 1, "supply", [c1])

    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "UNCLAIMED FAMILY HEADER" not in html
    assert "Line 2" in html


def test_spec_header_prints_in_full_and_is_never_truncated(client, clean_store):
    """
    `boq.view_boq()` prints the same paragraph in full. An ellipsis dropped into
    the middle of a specification clause on a TAX INVOICE is a document saying
    something other than what was agreed.
    """
    long_clause = ("Supply, fabrication, installation, testing and commissioning "
                   "of heavy duty C class pipe conforming to IS 1239 ") * 12
    header, child = _family(long_clause)
    make_boq("b1", [header, child])
    c1 = claim("1.1", 10, rate=50.0)
    c1["line_id"] = child["line_id"]
    rid = make_bill("r1", "b1", 1, "supply", [c1])

    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    cell = re.search(r'<td colspan="6"[^>]*>(.*?)</td>', html, re.S)
    assert cell, "no spec header row was rendered"
    assert cell.group(1).strip() == long_clause.strip()
