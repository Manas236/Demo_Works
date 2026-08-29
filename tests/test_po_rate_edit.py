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

### The narrowing this file used to pin — LIFTED 28 August 2026

~~`can_edit_rates()` allows **Draft only**.~~ It did until 28 August 2026,
under the override block of that date in `CLIENT_CHANGES.md` §0.

**The tests below were written so that this change would have to be
deliberate**, and it was: four of them asserted the narrowing and four of them
were rewritten, each keeping its old assertion verbatim in a comment. Nothing
here was quietly relaxed and nothing was deleted.

**Why it was lifted.** The reason anybody wants an editable base rate is that a
wrong rate has *already gone out*; Draft-only leaves exactly that case
unsolved. The objection the narrowing protected — a vendor has already been
told a price — is answered by **recording** the change instead of forbidding
it, which is what `reprice_log` is.

**One status is still refused: `Cancelled`.** A withdrawn order is not a live
order and repricing it would restate a document we have said is void.
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

def test_every_live_status_can_be_repriced_and_a_cancelled_one_cannot():
    """
    The gate, stated against every status the lifecycle has.

    **This test asserted the opposite until 28 August 2026.** What it said then,
    kept rather than deleted:

        assert PU.can_edit_rates({"status": "Draft"})[0] is True
        for status in PU.PO_STATUSES:
            if status == "Draft":
                continue
            allowed, why = PU.can_edit_rates({"status": status})
            assert allowed is False, f"{status} was allowed through"
            assert status in why, "the refusal must say which status refused it"
            assert "fresh purchase order" in why

    Written as a sweep over `PO_STATUSES` rather than five named cases, so a
    seventh status added later is covered the day it is added.
    """
    for status in PU.PO_STATUSES:
        allowed, why = PU.can_edit_rates({"status": status, "ref": "SF/PO/X"})
        if status == "Cancelled":
            assert allowed is False, "a cancelled order was repriced"
            assert "cancelled" in why.lower(), \
                "the refusal must say why, not merely refuse"
            assert "fresh purchase order" in why, \
                "and must name the supported route"
        else:
            assert allowed is True, f"{status} was refused"
            assert why == ""


def test_an_order_with_no_status_at_all_is_treated_as_a_draft():
    """`DEFAULT_STATUS` is Draft, and a record written without one is new."""
    assert PU.DEFAULT_STATUS == "Draft"
    assert PU.can_edit_rates({})[0] is True


def test_the_form_opens_on_an_issued_order_and_says_it_has_gone_out(client):
    """
    **Asserted the refusal until 28 August 2026.** What it said then:

        r = client.get(f"/purchase/edit/{po['id']}")
        assert r.status_code == 302, "an issued order must not render the form"
        assert "Only a Draft order can be repriced" in r.headers["Location"] \
            or "Issued" in r.headers["Location"]

    Opening is now the point. The second half is what stops that being a silent
    widening: the form has to tell the operator the vendor is holding these
    figures, because that is the fact the old refusal was carrying.
    """
    po = _raise(client, status="Issued")
    r = client.get(f"/purchase/edit/{po['id']}")
    assert r.status_code == 200, "an issued order must render the form now"
    html = r.get_data(as_text=True)
    assert "Issued" in html
    assert "has been sent it" in html, \
        "the form must say the vendor is holding what is being changed"
    assert "Every change is recorded" in html, \
        "and must say the change is recorded, which is what replaced the refusal"


def test_the_post_lands_on_an_issued_order_and_is_recorded(client):
    """
    **Asserted the refusal until 28 August 2026.** What it said then:

        po["status"] = "Issued"
        r = client.post(f"/purchase/edit/{po['id']}", data={"line_rate": "1"})
        assert r.status_code == 302
        assert po["line_items"][0]["price"] == 1000.0, "the rate moved anyway"

    The rate is now allowed to move — and the assertion that replaces "it did
    not move" is "it moved **and left a record**". A reprice that changed a
    figure without writing one would be the actual regression.
    """
    po = _raise(client, status="Draft")
    assert client.get(f"/purchase/edit/{po['id']}").status_code == 200
    po["status"] = "Issued"

    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": "1", "line_discount": ""})
    assert r.status_code == 302
    assert po["line_items"][0]["price"] == 1.0, "the rate did not move"
    assert len(po["reprice_log"]) == 1, "the rate moved with no record of it"
    assert po["reprice_log"][0]["status"] == "Issued", \
        "the record must say what the order was when it was repriced"


def test_a_cancelled_order_still_refuses_both_verbs(client):
    """
    The one status that is still refused, through the real routes.

    GET and POST both, for the reason the route docstring gives: checking only
    one verb leaves the other open to anyone who kept the URL.
    """
    po = _raise(client, status="Draft")
    po["status"] = "Cancelled"

    r = client.get(f"/purchase/edit/{po['id']}")
    assert r.status_code == 302, "a cancelled order rendered the form"

    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": "1", "line_discount": ""})
    assert r.status_code == 302
    assert po["line_items"][0]["price"] == 1000.0, \
        "a cancelled order was repriced through the POST"
    assert not po.get("reprice_log")


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


def test_the_reprice_button_is_offered_on_every_live_order_and_not_on_a_cancelled_one(client):
    """
    A button that redirects to a refusal is a worse answer than no button — the
    same rule the 27 August navigation pass applied to the whole nav. That rule
    is unchanged; what changed is which orders the gate lets through.

    **Asserted Draft-only until 28 August 2026.** What it said then:

        po["status"] = "Issued"
        issued_page = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
        assert f"/purchase/edit/{po['id']}" not in issued_page
        assert ">Reprice</a>" not in issued_page

    ⚠ This is the change that moved `/purchase/view`'s pinned golden: the
      golden order is **Issued** and now carries a Reprice button.
    """
    po = _raise(client, status="Draft")
    for status in PU.PO_STATUSES:
        po["status"] = status
        page = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
        if status == "Cancelled":
            assert f"/purchase/edit/{po['id']}" not in page, \
                "a cancelled order offered a Reprice button"
            assert ">Reprice</a>" not in page
        else:
            assert f"/purchase/edit/{po['id']}" in page, \
                f"{status} was not offered a Reprice button"
            assert ">Reprice</a>" in page


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
    authorise us to take on the client's behalf.

    ⚠ **Retargeted on 29 August 2026, and the old assertion is kept verbatim
      here because it is the thing that changed:**

          assert len(auth.PERMISSIONS) == 61

      That was a **global** count standing in for a claim about **A1**. It was
      right when it was written and it stayed right for a day, but it fails the
      moment any *unrelated* item mints a permission — which C4, the employee
      master, legitimately does (four of them: `employee.view` / `create` /
      `edit` / `delete`). A global count cannot tell "A1 quietly grew a
      permission" from "somebody built a different feature", and only the first
      is a defect.

      So the property is now stated where it actually lives: **the buy side
      still has exactly the three permissions it had**, and repricing is gated
      by one of them rather than by a fourth. That is what A1 claimed, it is
      strictly more specific than the count it replaces, and it goes on being
      true no matter what the rest of the application mints.
    """
    # ⚠ **Rewritten 29 August 2026 for B6, and the reason is the one this
    #   docstring already anticipated one item early.** The assertion below
    #   stood verbatim as:
    #
    #       assert buy_side == {"purchase.view", "purchase.create", "purchase.edit"}, (
    #           "A1 minted a purchase permission. Repricing is gated by "
    #           "`purchase.create`, which already exists.")
    #
    #   B6 — the approval ladder — mints `purchase.approve`, and CC-2 names the
    #   PO as one of the four approvable documents outright. That is the exact
    #   case the docstring above describes for C4: an *unrelated* item minting a
    #   permission, which a set-equality over the whole prefix cannot tell apart
    #   from "A1 quietly grew one". Only the first is a defect and B6 is not it.
    #
    #   So the claim is narrowed the same way it was narrowed once before —
    #   toward the property A1 actually asserted — rather than deleted or
    #   loosened to `>=`. **A1's three are still exactly A1's three**, every
    #   later addition has to be named here to pass, and repricing is still
    #   gated by one of the original three.
    A1_ERA = {"purchase.view", "purchase.create", "purchase.edit"}
    MINTED_SINCE = {
        # item that minted it -> permission
        "B6, the approval ladder (29 Aug 2026)": "purchase.approve",
    }

    buy_side = {p for p in auth.PERMISSIONS if p.startswith("purchase.")}
    assert buy_side == A1_ERA | set(MINTED_SINCE.values()), (
        "The buy-side permission set is not A1's three plus the additions named "
        "in MINTED_SINCE. If a later item minted this, name it there; if A1 "
        "grew one, that is the defect this test exists for — repricing is gated "
        "by `purchase.create`, which already exists.")
    assert auth.ROUTE_PERMISSIONS["purchase.edit_purchase_rates"] in A1_ERA, (
        "Repricing is no longer gated by one of A1's original three "
        "permissions, which is what A1 claimed.")


# ── The record — A1's other half, 28 August 2026 ───────────────────────────
#
# The Draft-only restriction was doing one job: stopping a figure a vendor had
# been told from moving behind the document. Lifting it without putting
# something in its place would remove the protection and keep none of it. This
# is what took its place, so these tests are load-bearing for the decision and
# not decoration on it.

def test_a_reprice_records_the_old_rate_and_the_new_one_per_line(client):
    po = _raise(client, rate="1000", qty="10", status="Issued")

    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "900", "line_discount": ""}
                       ).status_code == 302

    log = po["reprice_log"]
    assert len(log) == 1, "one submit, one entry"
    entry = log[0]
    assert len(entry["lines"]) == 1
    line = entry["lines"][0]
    assert line["rate_from"] == 1000.0
    assert line["rate_to"] == 900.0
    assert entry["at"], "an entry with no timestamp answers half the question"
    assert entry["by"], "and one with no author answers neither"


def test_the_discount_move_is_recorded_beside_the_rate(client):
    """A2's discount is money too, and a change to it is a reprice."""
    po = _raise(client, rate="1000", qty="10", disc="", status="Issued")

    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "1000", "line_discount": "10"}
                       ).status_code == 302

    line = po["reprice_log"][0]["lines"][0]
    assert (line["rate_from"], line["rate_to"]) == (1000.0, 1000.0)
    assert (line["disc_from"], line["disc_to"]) == (0.0, 10.0)


def test_only_the_lines_that_moved_are_recorded(client):
    """
    A four-line order with one changed rate must not produce four rows.

    A log that lists every line every time is a log nobody reads, and "which
    line moved" is the question it exists to answer.
    """
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()
    pids = sorted(STORE["products"])[:3]
    r = client.post("/purchase/create", data={
        "date": "2026-04-18", "vendor_id": VENDOR_ID, "status": "Issued",
        "tax_type": "exempt", "cgst_rate": "0", "igst_rate": "0",
        "line_product_id": pids, "line_qty": ["1", "1", "1"],
        "line_rate": ["100", "200", "300"], "line_discount": ["", "", ""],
    })
    assert r.status_code == 302
    po = list(STORE["purchases"].values())[0]
    assert len(po["line_items"]) == 3

    assert client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": ["100", "250", "300"],
        "line_discount": ["", "", ""],
    }).status_code == 302

    lines = po["reprice_log"][0]["lines"]
    assert len(lines) == 1, "unchanged lines were recorded as changes"
    assert (lines[0]["rate_from"], lines[0]["rate_to"]) == (200.0, 250.0)


def test_a_submit_that_changes_nothing_writes_no_entry(client):
    """A form re-submitted unchanged is not a reprice and must not read as one."""
    po = _raise(client, rate="1000", qty="10", status="Issued")

    r = client.post(f"/purchase/edit/{po['id']}",
                    data={"line_rate": "1000.00", "line_discount": ""})
    assert r.status_code == 302
    assert not po.get("reprice_log"), "an unchanged submit invented a history"
    assert "Nothing+changed" in r.headers["Location"].replace("%20", "+") \
        or "Nothing changed" in r.headers["Location"], \
        "and the operator must be told that, not told it saved"


def test_a_second_reprice_appends_and_does_not_replace(client):
    """
    The whole value of the record is that it is a chain.

    An overwrite would leave the *current* rate visible and the one before it
    gone, which is the state the Draft-only restriction existed to prevent.
    """
    po = _raise(client, rate="1000", qty="10", status="Issued")

    for rate in ("900", "850"):
        assert client.post(f"/purchase/edit/{po['id']}",
                           data={"line_rate": rate, "line_discount": ""}
                           ).status_code == 302

    log = po["reprice_log"]
    assert len(log) == 2
    assert log[0]["lines"][0]["rate_from"] == 1000.0
    assert log[0]["lines"][0]["rate_to"] == 900.0
    assert log[1]["lines"][0]["rate_from"] == 900.0
    assert log[1]["lines"][0]["rate_to"] == 850.0


def test_the_note_is_carried_onto_the_record(client):
    po = _raise(client, rate="1000", qty="10", status="Issued")
    assert client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": "900", "line_discount": "",
        "note": "revised after Sanghvi's second quote",
    }).status_code == 302
    assert po["reprice_log"][0]["note"] == "revised after Sanghvi's second quote"


def test_the_history_is_shown_on_the_order(client):
    """
    Recorded and not surfaced is the same as not recorded, for the person the
    record exists for.
    """
    po = _raise(client, rate="1000", qty="10", status="Issued")
    assert client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": "900", "line_discount": "", "note": "vendor revised",
    }).status_code == 302

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Rate changes" in html, "the reprice trail is not on the page"
    assert "vendor revised" in html
    assert "1,000.00" in html and "900.00" in html, \
        "the old rate and the new one must both be readable"


def test_an_order_never_repriced_shows_no_rate_changes_panel(client):
    """
    The other half, and the one that keeps every existing order's page
    unchanged — which is what stops this feature moving documents it did not
    touch.
    """
    po = _raise(client, rate="1000", qty="10", status="Issued")
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Rate changes" not in html
    # The class is in the stylesheet unconditionally; it is the DIV that must
    # be absent, so match the markup rather than the name of the rule.
    assert '<div class="po-reprice">' not in html


def test_the_operator_name_is_escaped_on_its_way_to_the_page(client):
    """
    `by` is a display name off a user record, which is user text — ABOUT.md §9.

    Written against the stored record rather than a crafted login, because the
    escaping site is the render and that is what this asserts.
    """
    po = _raise(client, rate="1000", qty="10", status="Issued")
    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "900", "line_discount": ""}
                       ).status_code == 302
    po["reprice_log"][0]["by"] = '<script>x</script>'

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html


def test_the_reprice_trail_does_not_reach_the_printed_sheet(client):
    """
    It lives inside `.po-panel`, which is `display:none` at print.

    What the vendor holds is the order, not our record of having changed it.
    Asserted through the stylesheet the page actually ships, because that is
    where the guarantee lives.
    """
    po = _raise(client, rate="1000", qty="10", status="Issued")
    assert client.post(f"/purchase/edit/{po['id']}",
                       data={"line_rate": "900", "line_discount": ""}
                       ).status_code == 302

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    at = html.find('<div class="po-reprice">')
    assert at > 0
    panel_at = html.find('<div class="po-panel">')
    assert 0 < panel_at < at, "the trail escaped the panel that hides it at print"
    assert "@media print { .po-panel { display:none; } }" in html
