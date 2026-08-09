"""
The printed RA bill is a TAX INVOICE, and an issued tax invoice does not move.

This is the test the snapshot exists for, and it is the one that was missing.

`3770616` froze `hsn_sac` and `gst_rate` onto every claim row and froze the
CGST/SGST/tax/rounding/grand totals onto the bill at save. That work only means
something if `/ra/print/<id>` reads those stored fields and nothing else — and
until this file, nothing checked. `91a36e6`/`f19c142` built the printed document
around a loop over `boq["line_items"]`, so three live reads got through:

  * the **item number** printed on each claim row came from the current BOQ
    line, overriding the snapshot `/ra/view` correctly shows (ABOUT.md §3, "a
    document prints the snapshot");
  * the **row set and row order** came from the current BOQ, so a line dropped
    from the schedule vanished from the table while its amount stayed inside
    the Claim Subtotal — an invoice whose rows do not add up to its own total;
  * the buyer/project block fell back to the live BOQ whenever the bill's own
    copy was blank.

Each of the tests below fails against that code. The assertion is the strongest
one available: **byte-identical output**. Anything weaker — "the rate is still
2024" — passes while some other field silently tracks the schedule.

Not covered by design: nothing here revises a bill through `/ra/edit`. Editing a
bill is *supposed* to change what it prints. The property is that revising the
BOQ *underneath* an untouched bill changes nothing.
"""

import re

import pytest

import boq as BQ
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


def _issued_bill():
    """
    A BOQ shaped like the client's — a spec header with a child under it, plus
    a standalone line — and one issued supply bill claiming across both.
    """
    header = boq_line("4", 0, header=True)
    header["description"] = "Supply, fabrication and installation of C class pipe"
    child = boq_line("4.1", 700, s_rate=2024.0)
    child["parent_item_no"] = "4"
    child["supply_hsn"] = "73090090"
    solo = boq_line("17", 120, s_rate=1800.0)
    solo["supply_hsn"] = "84241000"
    make_boq("b1", [header, child, solo])

    c1 = claim("4.1", 80, rate=2024.0)
    c1["line_id"] = child["line_id"]
    c1["hsn_sac"] = "73090090"
    c2 = claim("17", 12, rate=1800.0)
    c2["line_id"] = solo["line_id"]
    c2["hsn_sac"] = "84241000"

    rid = make_bill("r1", "b1", 1, "supply", [c1, c2],
                    po_ref="PO-4417", po_date="2026-07-02")
    return rid, child, solo


def _print(client, rid):
    res = client.get(f"/ra/print/{rid}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


# ═══ The property ══════════════════════════════════════════════════════════

def test_printed_bill_is_byte_identical_after_the_boq_is_revised(client, clean_store):
    """
    Change a rate, a quantity and an HSN on a claimed line. The issued bill must
    render exactly as it did before — not equivalently, identically.
    """
    rid, child, _solo = _issued_bill()
    before = _print(client, rid)

    line = STORE["boqs"]["b1"]["line_items"][1]
    assert line["line_id"] == child["line_id"]      # the line we claimed on
    line["supply_rate"] = 2500.0                    # a rate
    line["supply_base_rate"] = 2500.0
    line["total_qty"] = 5000.0                      # a quantity
    line["supply_hsn"] = "99999999"                 # an HSN

    assert _print(client, rid) == before


def test_printed_bill_is_byte_identical_after_the_boq_renumbers_the_line(client, clean_store):
    """
    A revision may renumber freely (ABOUT.md §3, "what a revision may do"). The
    document said 4.1 and must go on saying 4.1 — `/ra/view` already gets this
    right and shows *(now 7.7)* beside the snapshot; the printed invoice has no
    business showing 7.7 at all.
    """
    rid, _child, _solo = _issued_bill()
    before = _print(client, rid)
    assert ">4.1<" in before

    STORE["boqs"]["b1"]["line_items"][1]["item_no"] = "7.7"

    after = _print(client, rid)
    assert after == before
    assert "7.7" not in after


def test_printed_bill_is_byte_identical_after_description_and_unit_move(client, clean_store):
    rid, _child, _solo = _issued_bill()
    before = _print(client, rid)

    line = STORE["boqs"]["b1"]["line_items"][1]
    line["description"] = "A COMPLETELY DIFFERENT ITEM"
    line["unit"] = "Kgs"

    assert _print(client, rid) == before


def test_a_claimed_line_deleted_from_the_boq_still_prints_and_the_bill_ties(client, clean_store):
    """
    The worst of the three, because it is silent and it breaks arithmetic.

    Dropping the line from the schedule used to drop the row from the printed
    table while `claim_subtotal` — a stored figure — went on including it. The
    invoice then showed rows summing to 21,600 above a Claim Subtotal of
    183,520, and nothing on the page said why.

    (`boq.revision_blockers()` refuses to drop a claimed line through the
    revision route, which is not built yet. The document must not depend on a
    guard somewhere else to be arithmetically honest about its own contents.)
    """
    rid, _child, _solo = _issued_bill()
    before = _print(client, rid)

    boq = STORE["boqs"]["b1"]
    boq["line_items"] = [li for li in boq["line_items"] if li.get("item_no") != "4.1"]

    after = _print(client, rid)
    bill = STORE["ra_bills"][rid]

    # Both claim rows still print, with their own frozen figures...
    assert ">4.1<" in after, "a claimed line vanished from the invoice with the BOQ line"
    assert "161,920.00" in after and "21,600.00" in after
    # ...and they still add up to the stored subtotal on the same page.
    assert f"{bill['claim_subtotal']:,.2f}" in after
    assert bill["claim_subtotal"] == pytest.approx(161_920.00 + 21_600.00)

    # The one permitted difference: the spec header went with the relation that
    # named it. It is the only thing this document reads from the live BOQ, and
    # putting the paragraph back is all it takes to make the page identical.
    assert "Supply, fabrication and installation of C class pipe" in before
    assert "Supply, fabrication and installation of C class pipe" not in after
    squash = lambda s: " ".join(s.split())
    header_row = re.search(
        r'<tr style="background:#f8fafc;font-weight:700;">.*?</tr>',
        squash(before), re.S).group(0)
    assert squash(before).replace(header_row, "", 1).replace("  ", " ") == \
           squash(after)


def test_printed_bill_survives_the_boq_record_disappearing_entirely(client, clean_store):
    """
    The bill stores everything it needs. Losing the schedule must cost the
    document its spec-header context and nothing else — no 500, no missing row,
    no changed figure.
    """
    rid, _child, _solo = _issued_bill()
    before = _print(client, rid)

    STORE["boqs"].clear()
    after = _print(client, rid)

    assert "161,920.00" in after and "21,600.00" in after
    assert ">4.1<" in after and ">17<" in after
    bill = STORE["ra_bills"][rid]
    for figure in ("claim_subtotal", "net_payable", "grand_total"):
        assert f"{bill[figure]:,.2f}" in after
    # The one documented difference: the spec header is a relation held only by
    # the BOQ, so it goes when the BOQ goes. Nothing else may.
    assert "Supply, fabrication and installation" in before
    assert "Supply, fabrication and installation" not in after


def test_the_buyer_block_never_falls_back_to_the_live_boq(client, clean_store):
    """
    `create_ra()` copies the six party/project fields onto the bill at issue.
    Reading the BOQ when the copy is blank reintroduces the dependency the copy
    exists to remove, and does it only on the bills where it can matter.
    """
    rid, _child, _solo = _issued_bill()
    bill = STORE["ra_bills"][rid]
    bill["account_name"] = ""
    bill["project_name"] = ""

    before = _print(client, rid)
    STORE["boqs"]["b1"]["account_name"] = "SOMEBODY ELSE ENTIRELY"
    STORE["boqs"]["b1"]["project_name"] = "A DIFFERENT PROJECT"

    after = _print(client, rid)
    assert after == before
    assert "SOMEBODY ELSE ENTIRELY" not in after
    assert "A DIFFERENT PROJECT" not in after


def test_frozen_totals_are_read_never_recomputed(client, clean_store):
    """
    The totals block prints what was stored, even when the stored figures no
    longer follow from the rows. That is deliberate: `3770616` froze them so a
    certified bill cannot restate itself when a tax constant moves. A renderer
    that recomputes would silently reissue every historical bill at today's
    rates the day someone edits `cgst_rate`.
    """
    rid, _child, _solo = _issued_bill()
    bill = STORE["ra_bills"][rid]
    bill["cgst_amount"] = 11111.11
    bill["sgst_amount"] = 22222.22
    bill["tax_amount"] = 33333.33
    bill["rounding_off"] = -0.44
    bill["grand_total"] = 216852.89

    html = _print(client, rid)
    assert "11,111.11" in html
    assert "22,222.22" in html
    assert "216,852.89" in html
    assert "-0.44" in html


def test_print_reads_no_live_value_even_when_every_boq_field_is_replaced(client, clean_store):
    """
    The blanket version: replace every field of every BOQ line with a marker,
    keeping only what the header RELATION is made of — `line_id`, `is_header`,
    `section`, `parent_item_no`, and `item_no` on the header rows that
    `parent_item_no` points at. A claimed line's own item number is poisoned
    with everything else, because it is a value and the bill has its own.

    Only the spec header's own text may change, because that text is the
    relation's payload and lives nowhere else (see `ra.print_ra`'s docstring).
    """
    rid, _child, _solo = _issued_bill()
    before = _print(client, rid)

    for li in STORE["boqs"]["b1"]["line_items"]:
        fields = ["line_id", "is_header", "parent_item_no", "section"]
        if li.get("is_header"):
            fields.append("item_no")        # what parent_item_no points at
        keep = {k: li[k] for k in fields}
        li.clear()
        li.update(keep)
        li.setdefault("item_no", "POISON-ITEM-NO")
        li["unit"] = "POISON"
        li["total_qty"] = 424242.0
        li["supply_rate"] = 424242.0
        li["install_rate"] = 424242.0
        li["supply_hsn"] = "POISONHSN"
        li["install_sac"] = "POISONSAC"
        li["supply_gst_rate"] = 99.0
        li["install_gst_rate"] = 99.0
        li["description"] = "POISON DESCRIPTION"

    after = _print(client, rid)
    for marker in ("POISON", "424,242", "424242"):
        assert marker not in after.replace("POISON DESCRIPTION", "", 1), marker
    # Everything except the header paragraph is untouched.
    assert after.replace("POISON DESCRIPTION", "Supply, fabrication and "
                         "installation of C class pipe") == before
