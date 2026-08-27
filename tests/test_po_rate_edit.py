"""
Repricing an existing purchase order — CLIENT_CHANGES-2.md **A1**.

Built under the **27 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md` §0.

### What A1 actually was, before this

Not "the rate cannot be edited". The rate was always editable **at creation**:
`/purchase/create` has a rate box, `/purchase/from-boq` has one per picked
line, and `RATE_PREFILL_FIELD` only ever *suggested* the schedule's supply base
rate. `tests/test_boq_to_po.py` already pinned that. What did not exist was any
route that changed a **stored** line rate — `POST /purchase/<id>/update` is
status-and-note only and says so in its docstring. This file covers the half
that was missing.

### The narrowing this file also pins

`can_edit_rates()` allows **Draft only**, and CC-2's A1 line carries no such
qualification — it is ours, not the client's, taken because a Draft is
"written, not yet sent to the vendor" and an Issued order is one a supplier is
holding. **These tests assert the narrowing exists**; they do not assert it is
the right commercial answer, which is not a question code can settle. If the
client rules that an Issued order may be repriced, the tests below are what has
to be deliberately changed, and that is the point of writing them this way.
"""

import pytest

import address
import auth
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"


def _raise(client, *, rate="1000", qty="10", disc="", status="Draft",
           cgst="9", tax_type="cgst_sgst"):
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()
    pid = sorted(STORE["products"])[0]
    r = client.post("/purchase/create", data={
        "date": "2026-04-18", "vendor_id": VENDOR_ID, "status": status,
        "tax_type": tax_type, "cgst_rate": cgst, "igst_rate": "0",
        "line_product_id": pid, "line_qty": qty,
        "line_rate": rate, "line_discount": disc,
    })
    assert r.status_code == 302, "the order was not created"
    assert len(STORE["purchases"]) == 1
    return list(STORE["purchases"].values())[0]


# ── The gate ───────────────────────────────────────────────────────────────

def test_only_a_draft_order_can_be_repriced():
    """
    The narrowing, stated against every status the lifecycle has.

    `Draft` is `PO_STATUSES[0]` and its comment reads "written, not yet sent to
    the vendor". Everything after it has been sent.
    """
    assert PU.can_edit_rates({"status": "Draft"})[0] is True
    for status in PU.PO_STATUSES:
        if status == "Draft":
            continue
        allowed, why = PU.can_edit_rates({"status": status})
        assert allowed is False, f"{status} was allowed through"
        assert status in why, "the refusal must say which status refused it"
        assert "fresh purchase order" in why


def test_an_order_with_no_status_at_all_is_treated_as_a_draft():
    """`DEFAULT_STATUS` is Draft, and a record written without one is new."""
    assert PU.DEFAULT_STATUS == "Draft"
    assert PU.can_edit_rates({})[0] is True


def test_the_form_refuses_to_open_on_an_issued_order(client):
    po = _raise(client, status="Issued")
    r = client.get(f"/purchase/edit/{po['id']}")
    assert r.status_code == 302, "an issued order must not render the form"
    assert "Only a Draft order can be repriced" in r.headers["Location"] \
        or "Issued" in r.headers["Location"]


def test_the_post_refuses_on_an_issued_order_too(client):
    """
    Checking only on GET would leave the POST open to anyone who kept the URL —
    including somebody who opened the form while the order was a Draft and
    submitted it after it was issued.
    """
    po = _raise(client, status="Draft")
    assert client.get(f"/purchase/edit/{po['id']}").status_code == 200
    po["status"] = "Issued"
    r = client.post(f"/purchase/edit/{po['id']}", data={"line_rate": "1"})
    assert r.status_code == 302
    assert po["line_items"][0]["price"] == 1000.0, "the rate moved anyway"


def test_a_missing_order_redirects_rather_than_raising(client):
    r = client.get("/purchase/edit/no-such-order")
    assert r.status_code == 302
    assert "not+found" in r.headers["Location"].replace("%20", "+") \
        or "not found" in r.headers["Location"]


# ── The arithmetic ─────────────────────────────────────────────────────────

def test_a_new_rate_reprices_the_line_the_tax_and_the_order_value(client):
    """
    ₹1,000 × 10 at CGST 9% + SGST 9% is ₹11,800. Repriced to ₹900 it is
    ₹9,000 taxable and ₹10,620 — the tax follows the rate down because
    `_totals_of()` recomputes from the new subtotal rather than scaling the old
    total.
    """
    po = _raise(client, rate="1000", qty="10")
    assert po["grand_total"] == pytest.approx(11800.0)

    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": "900", "line_discount": ""})
    assert r.status_code == 302

    assert po["line_items"][0]["price"] == 900.0
    assert po["line_items"][0]["total"] == 9000.0
    assert po["subtotal"] == 9000.0
    assert po["tax_info"]["CGST"] == pytest.approx(810.0)
    assert po["tax_info"]["total"] == pytest.approx(1620.0)
    assert po["grand_total"] == pytest.approx(10620.0)


def test_a_discount_can_be_applied_to_an_order_that_did_not_have_one(client):
    """
    The join between A1 and A2, and the only way a **BOQ-derived** order gets a
    discount at all: `_po_lines_from_picked()` writes no `discount_pct`, so the
    schedule's lines arrive undiscounted and this form is where that is fixed.
    """
    po = _raise(client, rate="1000", qty="10", disc="")
    assert po["line_items"][0]["discount_pct"] == 0.0

    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": "1000", "line_discount": "10"})
    assert r.status_code == 302
    assert po["line_items"][0]["discount_pct"] == 10.0
    assert po["line_items"][0]["total"] == 9000.0
    assert po["grand_total"] == pytest.approx(10620.0)


def test_the_tax_type_is_not_editable_here_and_survives_a_reprice(client):
    """
    Whether a vendor charges CGST+SGST or IGST is a fact about where they are,
    not a price we negotiated. It was settled when the order was raised and a
    POST that tries to move it must be ignored, not honoured.
    """
    po = _raise(client, rate="1000", qty="10", tax_type="cgst_sgst", cgst="9")
    r = client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": "1000", "line_discount": "",
        "tax_type": "igst", "igst_rate": "18", "cgst_rate": "0",
    })
    assert r.status_code == 302
    assert po["tax_type"] == "cgst_sgst"
    assert "IGST" not in po["tax_info"]
    assert po["tax_info"]["cgst_rate"] == 9.0
    assert po["grand_total"] == pytest.approx(11800.0)


def test_an_exempt_order_stays_exempt_and_totals_to_its_subtotal(client):
    po = _raise(client, rate="500", qty="2", tax_type="exempt", cgst="0")
    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": "400", "line_discount": ""})
    assert r.status_code == 302
    assert po["subtotal"] == 800.0
    assert po["grand_total"] == 800.0
    assert po["tax_info"]["total"] == 0.0


@pytest.mark.parametrize("field,value,fragment", [
    ("line_rate",     "-5",  "cannot be negative"),
    ("line_discount", "150", "cannot be more than 100%"),
    ("line_discount", "abc", "must be a number"),
])
def test_a_bad_figure_is_refused_and_nothing_on_the_order_moves(
        client, field, value, fragment):
    """
    Nothing is written until every row has validated. A form that applied rows
    one at a time and then hit a bad one would leave the order half repriced and
    its totals describing neither price.
    """
    po = _raise(client, rate="1000", qty="10")
    before = dict(po["line_items"][0]), po["grand_total"]

    data = {"line_rate": "1000", "line_discount": ""}
    data[field] = value
    r = client.post(f"/purchase/edit/{po['id']}", data=data)

    assert r.status_code == 200, "a rejected form re-renders"
    assert fragment in r.get_data(as_text=True)
    assert (dict(po["line_items"][0]), po["grand_total"]) == before


def test_a_post_with_the_wrong_number_of_rows_is_refused_outright(client):
    """
    The form cannot add or remove a line, so a short post is a stale tab or a
    tampered one. Zipping it against whatever arrived would reprice the wrong
    line and report success.
    """
    po = _raise(client, rate="1000", qty="10")
    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": ["900", "800"]})
    assert r.status_code == 200
    assert "changed since this form was opened" in r.get_data(as_text=True)
    assert po["line_items"][0]["price"] == 1000.0


# ── What it must not touch ─────────────────────────────────────────────────

def test_the_quantity_the_vendor_the_lines_and_the_reference_do_not_move(client):
    """
    "Base rate editable" is a field unlock. A form that re-derived the line list
    would have to answer what happens to the `line_id` a BOQ-derived order
    carries, which is the key `/purchase/from-boq` turns on.
    """
    po = _raise(client, rate="1000", qty="10")
    frozen = {k: po[k] for k in
              ("ref", "date", "vendor_id", "vendor_name", "to", "vendor_gstin",
               "quotation_id", "boq_id", "status", "delivery_date")}
    n_lines, qty, name = len(po["line_items"]), po["line_items"][0]["qty"], \
        po["line_items"][0]["name"]

    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "700",
                             "line_discount": ""}).status_code == 302

    assert {k: po[k] for k in frozen} == frozen
    assert len(po["line_items"]) == n_lines
    assert po["line_items"][0]["qty"] == qty
    assert po["line_items"][0]["name"] == name
    assert po["total_qty"] == 10.0


def test_a_specification_header_gets_no_rate_box_and_keeps_its_zeroes(client):
    """
    A header carried down from a BOQ clause has no quantity, no rate and no
    amount. `_priced_rows()` skips it, so the form has one box fewer than the
    order has lines — and a rate written into a header row would be a figure in
    a row that contributes to neither total.
    """
    po = _raise(client, rate="1000", qty="10")
    po["line_items"].insert(0, {
        "type": "item", "is_header": True, "name": "Section A — Wet riser",
        "part_no": "A", "hsn": "", "qty": 0.0, "unit": "", "price": 0.0,
        "total": 0.0, "depth": 0,
    })
    assert len(PU._priced_rows(po)) == 1, "the header was offered a rate box"

    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert html.count('name="line_rate"') == 1
    assert "Wet riser" not in html, "a header must not appear as a priced row"

    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "900",
                             "line_discount": ""}).status_code == 302
    assert po["line_items"][0]["total"] == 0.0
    assert po["line_items"][0]["price"] == 0.0
    assert po["subtotal"] == 9000.0, "the header leaked into the order value"


# ── The page, and the door to it ───────────────────────────────────────────

def test_the_form_shows_the_stored_rate_and_discount(client):
    po = _raise(client, rate="1234.50", qty="3", disc="7.5")
    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="line_rate" value="1234.50"' in html
    assert 'name="line_discount" value="7.5"' in html
    assert "CGST 9% + SGST 9%" in html


def test_the_reprice_button_is_offered_on_a_draft_and_not_after(client):
    """
    A button that redirects to a refusal is a worse answer than no button — the
    same rule the 27 August navigation pass applied to the whole nav.
    """
    po = _raise(client, status="Draft")
    draft_page = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert f"/purchase/edit/{po['id']}" in draft_page
    assert ">Reprice</a>" in draft_page

    po["status"] = "Issued"
    issued_page = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert f"/purchase/edit/{po['id']}" not in issued_page
    assert ">Reprice</a>" not in issued_page


def test_the_reprice_is_written_onto_the_order_history(client):
    po = _raise(client, rate="1000", qty="10")
    before = len(po.get("status_history") or [])

    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "900", "line_discount": "",
                             "note": "revised after Sanghvi's second quote"
                             }).status_code == 302
    hist = po["status_history"]
    assert len(hist) == before + 1
    assert "Sanghvi" in hist[-1]["note"]


def test_without_a_note_the_history_records_both_order_values(client):
    po = _raise(client, rate="1000", qty="10")
    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "900",
                             "line_discount": ""}).status_code == 302
    note = po["status_history"][-1]["note"]
    assert "11,800" in note and "10,620" in note


# ── The classification ─────────────────────────────────────────────────────

def test_the_route_is_gated_by_the_permission_that_commits_money():
    """
    `purchase.edit` means "update a purchase order's status". Changing what this
    company has agreed to pay a vendor is the authority `purchase.create`
    confers, and a strictly larger one than marking a delivery received.
    """
    assert auth.ROUTE_PERMISSIONS["purchase.edit_purchase_rates"] == "purchase.create"
    assert auth.ROUTE_PERMISSIONS["purchase.update_purchase"] == "purchase.edit"
    assert "status" in auth.PERMISSIONS["purchase.edit"][0].lower()


def test_no_new_permission_was_minted_for_this(client):
    """
    Minting one would force a per-role decision CLIENT_CHANGES-2.md B4 does not
    authorise us to take on the client's behalf. 61 is the figure
    `docs/ACCESS_MATRIX.md` carries.
    """
    assert len(auth.PERMISSIONS) == 61
