"""
The delivery challan — CLIENT_CHANGES.md item 5.

Four properties this document exists to have, and each one is a section below:

  * **it is a snapshot.** The printed challan is driven by its own stored rows
    and never re-read from the live BOQ. This is the highest-value test in the
    file and it is written first, because the defect it guards has already
    shipped once in this repo: `print_ra()` looped `boq["line_items"]` instead
    of `bill["claims"]`, so a deleted BOQ line vanished from the printed table
    while the stored subtotal kept counting it.
  * **`line_id` is the key.** `item_no` is a display label, it is not unique
    even within one section, and keying on it is the defect that once waved
    through Rs 1,99,122.50 of over-claim on the client's own schedule.
  * **no money reaches the page.** Not a rate, not an amount, not a tax head,
    not a total, not a bank block, not the rupee sign. A challan that carries
    money is an invoice wearing a different heading.
  * **over-dispatch warns and never blocks.** The opposite call from the RA
    over-claim guard, and deliberately so — see §5.

⚠ The BOQ these tests run against is **built here rather than seeded**. The
  seeded Sify schedule is 97 lines of real specification prose, and an
  assertion that the word "Rate" is absent from a page is not an assertion
  about the code when the page carries 1,300 characters of somebody else's
  clause text. A fixed four-line schedule with known descriptions is what makes
  the negative assertions in §6 mean anything.
"""

import json
import pathlib
import re

import pytest

import boq as BQ
import branding as B
import challan
import pipeline as P
import settings as SET
from store import STORE

CHALLAN_SOURCE = (pathlib.Path(__file__).resolve().parent.parent
                  / "challan.py").read_text(encoding="utf-8")

# 15 characters: State code, PAN, entity number, 'Z', checksum. The shape is
# fixed by the GST registration scheme, which is what makes it greppable.
_GSTIN_SHAPED = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")

BID = "dc-test-boq"


def _line(line_id, item_no, desc, unit="Nos", qty=10.0, parent="",
          header=False, rate=7130.0):
    return {
        "line_id": line_id, "item_no": item_no, "parent_item_no": parent,
        "section": "A", "is_header": header, "description": desc,
        "remark": "", "unit": unit, "area_qty": {"T1": qty}, "total_qty": qty,
        "supply_base_rate": 6200.0, "supply_escalation_pct": 15.0,
        "supply_rate": rate, "supply_amount": rate * qty,
        "supply_hsn": "84818030", "supply_gst_rate": 18.0,
        "install_base_rate": None, "install_escalation_pct": 0.0,
        "install_rate": 0.0, "install_amount": 0.0,
        "install_sac": "", "install_gst_rate": 18.0,
    }


# The two lines carrying item_no 17 are the point of §2: they are different
# products at different rates, exactly as section A of the client's own
# workbook has them. Anything keying on the label collapses them into one.
LINES = [
    _line("aaaaaaaaaaaa", "24", "Butterfly valve clause, wafer type, cast iron "
          "body, tested to twice working pressure.", unit="", qty=0.0,
          header=True, rate=0.0),
    _line("bbbbbbbbbbbb", "24.a", "80mm Butterfly valve- SANT", parent="24",
          qty=8.0, rate=7130.0),
    _line("cccccccccccc", "17", "Flexible sprinkler drop, 1000mm",
          qty=40.0, rate=1800.0),
    _line("dddddddddddd", "17", "150mm Butterfly valve- SANT",
          qty=6.0, rate=14572.50),
]


@pytest.fixture()
def boq_tip(client):
    """A fixed four-line schedule, and a clean challan collection and series."""
    STORE["boqs"].clear()
    STORE.setdefault("delivery_challans", {}).clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)
    STORE["boqs"][BID] = {
        "id": BID, "ref": "SF/BOQ/26-27/0001", "fy": "26-27",
        "date": "2026-04-01", "rev_no": 0, "supersedes": "",
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": "Prudent Teqtis Pvt Ltd\nBangalore", "bill_gstin": "",
        "ship_same": "on", "rate_basis_label": "Mohali Rates",
        "sections": [{"code": "A", "title": "Hydrant system", "areas": ["T1"]}],
        "line_items": [dict(li) for li in LINES],
        "supply_subtotal": 0.0, "install_subtotal": 0.0, "subtotal": 0.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }
    yield BID
    STORE["boqs"].clear()
    STORE["delivery_challans"].clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)


def _payload(*pairs):
    return json.dumps({"lines": [{"line_id": lid, "qty": str(qty)}
                                 for lid, qty in pairs]})


def _create(client, bid, payload, **extra):
    data = {"date": "2026-07-28", "dispatch_mode": "Transport",
            "dispatch_to": "Bangalore", "consignee_name": "Samruddhi Fire",
            "consignee_addr": "Sify Infinit\nBangalore",
            "consignee_phone": "95765 76713", "po_no": "", "po_date": "",
            "notes": "", "dc_json": payload}
    data.update(extra)
    return client.post(f"/dc/create?boq={bid}", data=data)


def _only_dc():
    return next(iter(STORE["delivery_challans"].values()))


def _doc(html: str) -> str:
    """
    The document region of a rendered page, with the logo stripped.

    Both halves matter. The stylesheet stack declares `.c-total`,
    `.row-total`, `.bank-box` and `.amount-words`, so a page-wide search for
    the word "Total" answers a question about CSS rather than about the
    document. And the letterhead carries the logo as a ~40 KB base64 data URI,
    whose alphabet is uppercase letters — a three-letter token like `IGST` can
    turn up in it by chance, and an assertion that fails on a coin toss is
    worse than no assertion.
    """
    region = html.split('<div class="quotation-doc">')[1]
    return re.sub(r"<img\b[^>]*>", "", region)


# ═══ 1. The snapshot — the highest-value test here ═════════════════════════

def test_the_print_is_driven_by_the_challans_own_rows_not_the_live_boq(
        client, boq_tip):
    """
    CLIENT_CHANGES.md §1.2, and the defect that has already shipped once.

    The schedule is revised underneath an existing challan — description, item
    number, unit, quantity, the project name, and the outright deletion of a
    dispatched line — and the printed document must not move by one byte.
    """
    assert _create(client, boq_tip,
                   _payload(("bbbbbbbbbbbb", 2), ("cccccccccccc", 5))
                   ).status_code == 302
    dc = _only_dc()
    before = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "80mm Butterfly valve- SANT" in before, "the fixture printed nothing"

    boq = STORE["boqs"][boq_tip]
    boq["project_name"] = "MODIFIED PROJECT"
    boq["site_location"] = "MODIFIED SITE"
    for li in boq["line_items"]:
        if li["line_id"] == "bbbbbbbbbbbb":
            li["description"] = "MODIFIED DESCRIPTION"
            li["item_no"] = "MODIFIEDNO"
            li["unit"] = "MODIFIEDUNIT"
            li["total_qty"] = 7654321.0
    # And the outright deletion of a line this challan dispatched.
    boq["line_items"] = [li for li in boq["line_items"]
                         if li["line_id"] != "cccccccccccc"]

    after = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert after == before, "the document moved when the schedule under it did"
    # The byte comparison above is the assertion; these name what would have
    # moved, against the document region rather than the stylesheet stack.
    doc = _doc(after)
    for token in ("MODIFIED PROJECT", "MODIFIED SITE", "MODIFIED DESCRIPTION",
                  "MODIFIEDNO", "MODIFIEDUNIT", "7654321"):
        assert token not in doc, f"{token} leaked from the live BOQ"
    assert "Flexible sprinkler drop" in doc,\
        "a deleted BOQ line vanished from a challan that dispatched it"


def test_the_specification_clause_is_snapshotted_not_looked_up(client, boq_tip):
    """
    `print_ra()` still reads one thing from the live BOQ — the parent clause,
    because no claim row carries it. This document carries it, so nothing here
    reads the BOQ at all. Deleting the header proves which.
    """
    assert _create(client, boq_tip, _payload(("bbbbbbbbbbbb", 2))).status_code == 302
    dc = _only_dc()
    heads = [r for r in dc["items"] if r["is_header"]]
    assert len(heads) == 1 and heads[0]["description"].strip()

    boq = STORE["boqs"][boq_tip]
    boq["line_items"] = [li for li in boq["line_items"]
                         if li["line_id"] != "aaaaaaaaaaaa"]
    html = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "Butterfly valve clause" in html, \
        "the clause disappeared with the BOQ header — it is not snapshotted"


# ═══ 2. `line_id` is the key, `item_no` is a label ═════════════════════════

def test_two_lines_sharing_an_item_no_produce_two_distinct_rows(client, boq_tip):
    """
    Section A of the client's own workbook carries item 17 twice, on a
    flexible sprinkler drop and on a 150 mm butterfly valve. Anything keying on
    the label collapses 87 priced lines into 77.
    """
    assert _create(client, boq_tip,
                   _payload(("cccccccccccc", 5), ("dddddddddddd", 3))
                   ).status_code == 302
    rows = [r for r in _only_dc()["items"] if not r["is_header"]]

    assert len(rows) == 2, f"item 17 collapsed into {len(rows)} row(s)"
    assert {r["line_id"] for r in rows} == {"cccccccccccc", "dddddddddddd"}
    by_lid = {r["line_id"]: r for r in rows}
    assert by_lid["cccccccccccc"]["description"] == "Flexible sprinkler drop, 1000mm"
    assert by_lid["dddddddddddd"]["description"] == "150mm Butterfly valve- SANT"
    assert by_lid["cccccccccccc"]["qty"] == 5.0
    assert by_lid["dddddddddddd"]["qty"] == 3.0
    assert {r["item_no"] for r in rows} == {"17"}, \
        "the fixture no longer has a duplicated item number to key wrongly on"


def test_a_posted_line_id_that_is_not_on_this_boq_is_dropped(client, boq_tip):
    """A row that matches nothing is skipped, never guessed back through
    `item_no` — CLIENT_CHANGES.md §1.4."""
    assert _create(client, boq_tip,
                   _payload(("cccccccccccc", 5), ("ffffffffffff", 99))
                   ).status_code == 302
    rows = [r for r in _only_dc()["items"] if not r["is_header"]]
    assert len(rows) == 1 and rows[0]["line_id"] == "cccccccccccc"


# ═══ 3. Numbering — global, seedable, and never reissued ═══════════════════

def test_the_series_is_seedable_to_continue_their_paper_book(client, boq_tip):
    """
    Their challan 54 is a **bare integer with no prefix**, one running series
    across every site. A hardcoded start at 1 collides with their book on the
    first movement, so both halves are editable at `/settings`.
    """
    r = client.post("/settings/", data={"dc_prefix": "", "dc_next_no": "55"})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert SET.dc_series() == {"prefix": "", "next_no": "55"}

    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    assert _only_dc()["ref"] == "55", "the series did not continue their book"


def test_a_prefix_switches_the_series_to_the_padded_house_shape(client, boq_tip):
    """Set a prefix and it numbers like every other series in this app."""
    assert client.post("/settings/", data={"dc_prefix": "SF/DC",
                                           "dc_next_no": "7"}).status_code == 302
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    assert _only_dc()["ref"] == "SF/DC/0007"


def test_a_deleted_challan_does_not_release_its_number(client, boq_tip):
    """
    A high-water mark, never `max+1` over the survivors. The number has
    travelled with a load of material; a second document bearing it is
    indistinguishable from the first. `po_draft.next_ref()` shipped as `max+1`
    and was fixed — this is the fixed implementation.
    """
    assert client.post("/settings/", data={"dc_prefix": "",
                                           "dc_next_no": "55"}).status_code == 302
    for lid in ("bbbbbbbbbbbb", "cccccccccccc", "dddddddddddd"):
        assert _create(client, boq_tip, _payload((lid, 1))).status_code == 302

    refs = sorted(d["ref"] for d in STORE["delivery_challans"].values())
    assert refs == ["55", "56", "57"], refs

    highest = next(cid for cid, d in STORE["delivery_challans"].items()
                   if d["ref"] == "57")
    assert client.post(f"/dc/delete/{highest}").status_code == 302
    assert len(STORE["delivery_challans"]) == 2

    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    refs = sorted(d["ref"] for d in STORE["delivery_challans"].values())
    assert refs == ["55", "56", "58"], \
        f"the deleted challan handed its number back: {refs}"


def test_the_series_is_global_and_not_per_boq(client, boq_tip):
    """One running series across all sites — the opposite of `ra_no`, which is
    that project's own sequence."""
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302

    other = "dc-test-boq-2"
    STORE["boqs"][other] = dict(STORE["boqs"][boq_tip], id=other,
                                ref="SF/BOQ/26-27/0002",
                                project_name="A different site", supersedes="")
    assert _create(client, other, _payload(("cccccccccccc", 1))).status_code == 302
    assert sorted(d["ref"] for d in STORE["delivery_challans"].values()) == ["1", "2"]


# ═══ 4. The picker ═════════════════════════════════════════════════════════

def test_the_create_form_lists_every_boq_line_with_a_checkbox(client, boq_tip):
    html = client.get(f"/dc/create?boq={boq_tip}").get_data(as_text=True)
    for lid in ("bbbbbbbbbbbb", "cccccccccccc", "dddddddddddd"):
        assert f'id="c_{lid}"' in html, f"line {lid} has no checkbox"
        assert f'id="q_{lid}"' in html, f"line {lid} has no quantity box"
    assert "selectAll()" in html and "clearAll()" in html
    # And no Pcs column: that is one variant of their purchase order, not their
    # challan.
    assert 'id="p_cccccccccccc"' not in html
    assert ">Pcs</th>" not in html


def test_nothing_ticked_is_refused_and_writes_nothing(client, boq_tip):
    """A challan with nothing on it is not a document."""
    r = _create(client, boq_tip, json.dumps({"lines": []}))
    assert r.status_code == 200, "an empty selection was accepted"
    assert "No lines are ticked" in r.get_data(as_text=True)
    assert not STORE["delivery_challans"], "an empty challan was written"


def test_unticked_lines_are_absent_from_the_snapshot(client, boq_tip):
    assert _create(client, boq_tip, _payload(("cccccccccccc", 5))).status_code == 302
    rows = [r for r in _only_dc()["items"] if not r["is_header"]]
    assert {r["line_id"] for r in rows} == {"cccccccccccc"}
    html = client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True)
    assert "150mm Butterfly valve- SANT" not in html


def test_an_edited_quantity_is_snapshotted_not_the_schedules(client, boq_tip):
    """
    The BOQ carries 40 of this line. Two are going out on this load, and two
    is what the challan says.
    """
    assert _create(client, boq_tip, _payload(("cccccccccccc", 2))).status_code == 302
    row = next(r for r in _only_dc()["items"] if not r["is_header"])
    assert row["qty"] == 2.0

    doc = _doc(client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True))
    assert '<td class="c-qty">2</td>' in doc
    assert '<td class="c-qty">40</td>' not in doc, \
        "the schedule's quantity printed instead of the one that was typed"


def test_a_ticked_size_brings_its_specification_clause(client, boq_tip):
    """
    DOMAIN.md §2.2 — the clause the size is described by travels with it,
    carrying no quantity. This is also the regression `po_draft` shipped:
    `is_header` was read as `type`, so no header was ever recognised.
    """
    assert _create(client, boq_tip, _payload(("bbbbbbbbbbbb", 2))).status_code == 302
    heads = [r for r in _only_dc()["items"] if r["is_header"]]
    assert len(heads) == 1, "the clause did not come with its size"
    assert heads[0]["item_no"] == "24"
    assert heads[0]["description"].startswith("Butterfly valve clause")
    assert heads[0]["qty"] == 0.0, "a specification header must carry no quantity"


def test_every_snapshotted_row_carries_a_real_description(client, boq_tip):
    """
    The control for the picker section.

    `po_draft` read `line["desc"]`, which a BOQ line does not have, so every
    row was snapshotted empty — and its own test asserted `"" in html` and
    passed. Assert the descriptions exist before believing anything else.
    """
    assert _create(client, boq_tip,
                   _payload(("bbbbbbbbbbbb", 1), ("cccccccccccc", 1),
                            ("dddddddddddd", 1))).status_code == 302
    for row in _only_dc()["items"]:
        assert row["description"].strip(), \
            f"row {row['item_no']} was snapshotted with no description"
        assert "unit" in row and "qty" in row


# ═══ 5. Over-dispatch — warn, never block ══════════════════════════════════

def test_a_second_challan_past_the_boq_quantity_is_ACCEPTED(client, boq_tip):
    """
    The opposite call from the RA over-claim guard, and it is deliberate.

    That guard is a hard block because it guards money billed to a main
    contractor and an over-claim is a false claim. This is a goods-movement
    note: sites have replacements, breakages, free issue and returns, and
    refusing a lawful movement here only pushes it onto paper this system never
    sees.
    """
    # The BOQ carries 6 of line d. Send 4, then 4 more.
    assert _create(client, boq_tip, _payload(("dddddddddddd", 4))).status_code == 302
    r = _create(client, boq_tip, _payload(("dddddddddddd", 4)))
    assert r.status_code == 302, "the over-dispatch was blocked"
    assert len(STORE["delivery_challans"]) == 2, "the second challan was not written"
    assert challan.BLOCK_OVER_DISPATCH is False


def test_the_amber_band_names_the_lines_that_went_over(client, boq_tip):
    assert _create(client, boq_tip, _payload(("dddddddddddd", 4))).status_code == 302
    assert _create(client, boq_tip,
                   _payload(("dddddddddddd", 4), ("cccccccccccc", 1))
                   ).status_code == 302

    over = next(d for d in STORE["delivery_challans"].values()
                if len(d["items"]) == 2)
    html = client.get(f"/dc/view/{over['id']}").get_data(as_text=True)
    band = html.split('class="dc-warn"')[1].split("</div>")[0]

    assert "150mm Butterfly valve- SANT" in band, "the band does not name the line"
    assert "8 dispatched against 6" in band, "the band does not state the figures"
    assert "Flexible sprinkler drop" not in band, \
        "a line that is within its quantity was named as over-dispatched"


def test_a_challan_within_the_schedule_shows_no_band(client, boq_tip):
    """The control: the band is not simply always on."""
    assert _create(client, boq_tip, _payload(("dddddddddddd", 2))).status_code == 302
    html = client.get(f"/dc/view/{_only_dc()['id']}").get_data(as_text=True)
    assert 'class="dc-warn"' not in html


def test_cumulative_dispatch_is_summed_across_the_revision_chain(client, boq_tip):
    """
    Derived, never stored, and summed across the whole chain — `ra.claimed_by_line()`'s
    rule. A per-record sum would report nil dispatched the moment a schedule
    was revised, silently and only on the projects that had been revised.
    """
    assert _create(client, boq_tip, _payload(("dddddddddddd", 5))).status_code == 302

    rev = "dc-test-boq-rev1"
    STORE["boqs"][rev] = dict(STORE["boqs"][boq_tip], id=rev,
                              ref="SF/BOQ/26-27/0001-R1", rev_no=1,
                              supersedes=boq_tip,
                              line_items=[dict(li) for li in LINES])
    assert _create(client, rev, _payload(("dddddddddddd", 3))).status_code == 302

    newer = next(d for d in STORE["delivery_challans"].values()
                 if d["boq_id"] == rev)
    rows = challan.over_dispatched(newer)
    assert rows, "the revision reset the dispatched total to zero"
    assert rows[0][2] == 8.0, f"expected 8 dispatched across the chain, got {rows[0][2]}"


# ═══ 6. No money reaches the page ══════════════════════════════════════════

MONEY_TOKENS = ["CGST", "SGST", "IGST", "Taxable", "Bank Details",
                "Grand Total", "Amount in Words", "Amount In Words",
                "&#8377;", "₹", "INR ", "Rate", "Amount"]


@pytest.mark.parametrize("token", MONEY_TOKENS)
def test_no_money_of_any_kind_reaches_the_printed_challan(client, boq_tip, token):
    """
    Asserted over the **document region with the logo stripped** — see `_doc()`
    for why a page-wide search would be answering a question about CSS and
    about base64.
    """
    assert _create(client, boq_tip,
                   _payload(("bbbbbbbbbbbb", 2), ("dddddddddddd", 1))
                   ).status_code == 302
    doc = _doc(client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True))
    assert token not in doc, f"the printed challan carries {token!r}"


def test_the_money_assertions_are_running_against_a_real_document(client, boq_tip):
    """
    The control, and the whole reason §6 is trustworthy.

    Fourteen "not in" assertions pass just as well against an error page, an
    empty string, or a document region the split silently produced from the
    wrong marker. This proves the page under test is the challan, has rows on
    it, and would have shown a rate if one had been printed.
    """
    assert _create(client, boq_tip,
                   _payload(("bbbbbbbbbbbb", 2), ("dddddddddddd", 1))
                   ).status_code == 302
    doc = _doc(client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True))

    assert "DELIVERY CHALLAN" in doc
    assert "DESCRIPTION OF GOODS" in doc
    assert "80mm Butterfly valve- SANT" in doc
    assert "150mm Butterfly valve- SANT" in doc
    assert "Name &amp; Signature of Receiver" in doc
    assert doc.count('class="row-item"') == 2, "the goods table has no rows"


def test_no_rate_from_the_boq_reaches_the_challan(client, boq_tip):
    """
    The figures, not the labels. Line d is priced at 14,572.50 in the schedule
    and dispatching it must not put that number on a delivery note.
    """
    assert _create(client, boq_tip, _payload(("dddddddddddd", 1))).status_code == 302
    doc = _doc(client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True))
    for text in ("14572.50", "14,572.50", "14,572", "1,800", "7130"):
        assert text not in doc, f"the BOQ rate {text} reached the challan"
    assert challan.PRINT_RATES is False
    assert challan.PRINT_TAX is False
    assert challan.PRINT_TOTALS is False


def test_the_goods_table_has_exactly_four_columns(client, boq_tip):
    """Sr.No. | Description | Qty | Unit — their DC54, and nothing else."""
    assert _create(client, boq_tip, _payload(("dddddddddddd", 1))).status_code == 302
    doc = _doc(client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True))
    heads = re.findall(r'<th class="(c-[a-z-]+)">([^<]*)</th>', doc)
    assert heads == [("c-sno", "Sr.No."), ("c-desc", "Description"),
                     ("c-qty", "Qty"), ("c-unit", "Unit")], heads


# ═══ 7. The seller identity is read, never written into this file ══════════
#
# `tests/test_ra_seller_identity.py`'s rule, applied to the second document
# that prints who we are. The convention is `ra.py`'s exactly: read `branding`
# at render time, derive the State from the GSTIN, and keep no fallback behind
# either — a fallback is how a literal survives, and it appears at the one
# moment nobody is checking.

def test_challan_py_carries_no_state_name_literal():
    found = sorted(state for state in P.GST_STATE_CODES
                   if re.search(rf"\b{re.escape(state)}\b", CHALLAN_SOURCE))
    assert not found, (
        f"challan.py names {found} in its source. The seller's State is derived "
        f"from the company GSTIN via pipeline.gstin_state_label().")


def test_challan_py_carries_no_gstin_literal():
    found = sorted(set(_GSTIN_SHAPED.findall(CHALLAN_SOURCE)))
    assert not found, (
        f"challan.py carries the GSTIN literal(s) {found}. It comes from "
        f"settings, and a hardcoded one behind an `or` prints exactly when the "
        f"real one is missing.")


def test_the_seller_block_follows_settings(client, boq_tip):
    before = B.current_settings()
    try:
        B.apply_settings({"COMPANY_GSTIN": "27AAAAA0000A1Z5",
                          "COMPANY_ADDR": "Sector-10, Koparkhairane, Navi Mumbai - 400709",
                          "COMPANY_PHONE": "8898420303"})
        assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
        doc = _doc(client.get(f"/dc/print/{_only_dc()['id']}").get_data(as_text=True))
        assert "27AAAAA0000A1Z5" in doc
        assert "Maharashtra (27)" in doc
        assert "Koparkhairane" in doc
    finally:
        B.apply_settings(before)


def test_the_consignee_defaults_to_us_and_never_to_the_billed_party(client, boq_tip):
    """
    DOMAIN.md §5.1. On DC54 the consignee is Samruddhi themselves at their own
    site store. The BOQ's `account_name` is the main contractor being billed,
    and it is exactly the party the goods are NOT being consigned to.
    """
    html = client.get(f"/dc/create?boq={boq_tip}").get_data(as_text=True)
    default = B.COMPANY_LEGAL or B.COMPANY_NAME
    assert f'name="consignee_name"\n                 value="{P.esc(default)}"' \
        in html.replace("\r\n", "\n"), "the consignee did not default to us"
    assert 'value="Prudent Teqtis Pvt Ltd"' not in html, \
        "the consignee was wired to the party being billed"


# ═══ 8. A superseded BOQ is refused at the route ═══════════════════════════

def test_a_superseded_boq_is_refused_at_the_route(client, boq_tip):
    """
    Gated on `boq.superseded_ids()`, exactly as `/ra/create` and `/po/create`
    are — the same predicate the `/boq/view` action bar branches on, so the
    link and the route cannot disagree. A link is not a guard.
    """
    STORE["boqs"]["newer"] = dict(STORE["boqs"][boq_tip], id="newer",
                                  ref="SF/BOQ/26-27/0009", supersedes=boq_tip)
    r = client.get(f"/dc/create?boq={boq_tip}")
    assert r.status_code == 302
    assert "superseded" in r.headers["Location"].lower()
    assert not STORE["delivery_challans"]


def test_the_boq_action_bar_offers_a_challan_only_on_the_tip(client, boq_tip):
    html = client.get(f"/boq/view/{boq_tip}").get_data(as_text=True)
    assert f'href="/dc/create?boq={boq_tip}"' in html, \
        "the BOQ page offers no way to raise a challan"

    STORE["boqs"]["newer"] = dict(STORE["boqs"][boq_tip], id="newer",
                                  ref="SF/BOQ/26-27/0009", supersedes=boq_tip)
    html = client.get(f"/boq/view/{boq_tip}").get_data(as_text=True)
    assert f'href="/dc/create?boq={boq_tip}"' not in html, \
        "a superseded schedule still offers the challan link"


# ═══ 9. The delete route ═══════════════════════════════════════════════════

def test_get_on_dc_delete_destroys_nothing(client, boq_tip):
    """
    ABOUT.md §7.9f's standing rule for a NEW delete route: it ships its own
    per-route GET test. The `url_map` sweep proves only that the rule accepts
    POST — it cannot catch a route that accepts both and still destroys on GET.
    """
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    cid = _only_dc()["id"]

    r = client.get(f"/dc/delete/{cid}")
    assert r.status_code == 200, "the GET did not render a confirmation page"
    assert "Delete it" in r.get_data(as_text=True)
    assert "confirm(" not in r.get_data(as_text=True)
    assert cid in STORE["delivery_challans"], "a GET destroyed the record"

    r = client.post(f"/dc/delete/{cid}")
    assert r.status_code == 302
    assert cid not in STORE["delivery_challans"]


# ═══ 10. Edit — the party and the dispatch, never the lines ════════════════

def test_edit_changes_the_consignee_and_dispatch_fields(client, boq_tip):
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    cid = _only_dc()["id"]

    r = client.post(f"/dc/edit/{cid}", data={
        "date": "2026-08-02", "dispatch_mode": "Own vehicle",
        "dispatch_to": "Pune site", "consignee_name": "Samruddhi Fire — Pune",
        "consignee_addr": "Hinjewadi Phase II", "consignee_phone": "9000000000",
        "po_no": "PT/PO/2026/117", "po_date": "2026-04-11", "notes": "part load"})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]

    dc = STORE["delivery_challans"][cid]
    assert dc["date"] == "2026-08-02"
    assert dc["dispatch_mode"] == "Own vehicle"
    assert dc["dispatch_to"] == "Pune site"
    assert dc["consignee_name"] == "Samruddhi Fire — Pune"
    assert dc["consignee_phone"] == "9000000000"
    assert dc["po_no"] == "PT/PO/2026/117"


def test_edit_cannot_change_the_lines(client, boq_tip):
    """
    A challan is signed for on arrival, and the lines on it are what left the
    yard. `/po/edit` makes the same call and `purchase.update_purchase()` made
    it first.
    """
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    cid = _only_dc()["id"]
    before = [dict(r) for r in STORE["delivery_challans"][cid]["items"]]

    # The form does not render the picker on edit; this posts one anyway.
    r = client.post(f"/dc/edit/{cid}", data={
        "date": "2026-08-02", "dispatch_mode": "Transport", "dispatch_to": "",
        "consignee_name": "Samruddhi Fire", "consignee_addr": "",
        "consignee_phone": "", "po_no": "", "po_date": "", "notes": "",
        "dc_json": _payload(("bbbbbbbbbbbb", 99), ("dddddddddddd", 99))})
    assert r.status_code == 302

    assert STORE["delivery_challans"][cid]["items"] == before, \
        "the lines moved under a challan somebody has already signed for"

    html = client.get(f"/dc/edit/{cid}").get_data(as_text=True)
    assert 'id="c_bbbbbbbbbbbb"' not in html, "the edit form renders the picker"


def test_an_edit_never_reissues_the_number(client, boq_tip):
    assert _create(client, boq_tip, _payload(("cccccccccccc", 1))).status_code == 302
    dc = _only_dc()
    ref, cid = dc["ref"], dc["id"]

    assert client.post(f"/dc/edit/{cid}", data={
        "date": "2026-09-01", "dispatch_mode": "Transport", "dispatch_to": "",
        "consignee_name": "Samruddhi Fire", "consignee_addr": "",
        "consignee_phone": "", "po_no": "", "po_date": "",
        "notes": "revised"}).status_code == 302
    assert STORE["delivery_challans"][cid]["ref"] == ref


# ═══ The consignee picker sits BESIDE the free text, never instead of it ═══

def test_the_address_book_is_an_optional_prefill_not_a_replacement(client, boq_tip):
    """
    `po_draft.vendor_from()`'s arrangement, and the first draft-PO pass had the
    replacement rejected. A site store that exists for four months is not worth
    an address-book entry.
    """
    import address
    address.ensure_demo_addresses()
    html = client.get(f"/dc/create?boq={boq_tip}").get_data(as_text=True)
    assert 'name="consignee_name"' in html and 'name="consignee_addr"' in html
    assert 'name="consignee_phone"' in html
    assert 'name="consignee_id"' in html, "the address-book prefill is missing"

    aid = next(iter(STORE["addresses"]))
    r = _create(client, boq_tip, _payload(("cccccccccccc", 1)),
                consignee_id=aid, consignee_name="", consignee_addr="",
                consignee_phone="")
    assert r.status_code == 302
    dc = _only_dc()
    assert dc["consignee_source"] == "book"
    assert dc["consignee_name"].strip(), "the picked address filled nothing"

    # And it is snapshotted: editing the book afterwards does not move the page.
    before = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    STORE["addresses"][aid]["company"] = "RENAMED LTD"
    assert client.get(f"/dc/print/{dc['id']}").get_data(as_text=True) == before


def test_no_consignee_at_all_is_refused(client, boq_tip):
    r = _create(client, boq_tip, _payload(("cccccccccccc", 1)),
                consignee_id="", consignee_name="", consignee_addr="")
    assert r.status_code == 200
    assert "needs a consignee" in r.get_data(as_text=True)
    assert not STORE["delivery_challans"]
