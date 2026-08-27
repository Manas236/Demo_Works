"""
The discount column on the final purchase order — CLIENT_CHANGES-2.md **A2**.

Built under the **27 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md` §0,
which names A1, A2 and A5 and no more.

### What this file is actually for

A2 is one column, and a column is easy to add and easy to get wrong in a way
nothing shouts about. Two things had to be true and neither is visible from a
route returning 200:

1. **The discount is inside the tax base.** `_line_total()` discounts the line,
   the line lands in `subtotal`, and `subtotal` is the *only* argument
   `_tax_lines()` computes tax from. So tax follows the discount down. A test
   that only checked the grand total would pass with the discount applied
   *after* tax and be wrong by the tax on the discount — which on this file's
   figures is ₹180, and on a real order is a number somebody has to explain to
   a vendor.
2. **Nothing else moved.** The buy sheet has its own column tuple and its own
   `.c-disc` rule precisely so the three pinned sell-side documents do not
   move; `tests/test_print_golden.py` is what proves that, and this file proves
   the buy sheet actually draws the column that cost.

Assertions are against **rendered bytes** and **stored figures**, not against
status codes.
"""

import pytest

import address
import docsheet as DS
import purchase as PU
from store import STORE

# The same fixed-UUID vendor `tests/test_boq_to_po.py` names, from
# `address.ensure_demo_addresses()`. `_vendor_from()` takes the address book and
# nothing else — a PO quotes the vendor's GSTIN back at them on a record we
# claim input tax credit against, so a typed one-off supplier is refused.
VENDOR_ID = "b2000006-face-4000-8000-000000000006"


# ── The arithmetic, with no HTTP anywhere near it ──────────────────────────

def test_a_line_with_no_discount_is_byte_for_byte_the_old_arithmetic():
    """
    The compatibility claim the whole item rests on.

    Every purchase order written before 27 August 2026 has no `discount_pct` at
    all, and `_line_total()` must reproduce `round(rate * qty, 2)` exactly for
    them — not approximately, and not to two places after a float detour.
    """
    for rate, qty in ((2024.0, 120.0), (1150.0, 4.0), (128000.0, 2.0),
                      (0.1, 3.0), (14572.5, 7.0), (1800.0, 17.0)):
        assert PU._line_total(rate, qty, 0.0) == round(rate * qty, 2)
        assert PU._line_total(rate, qty, None) == round(rate * qty, 2)


def test_the_discount_comes_off_the_line_and_is_rounded_once():
    """
    ₹1,000 × 3 less 10% is ₹2,700, and it is reached by discounting the product
    rather than by discounting an already-rounded amount.

    The second figure is the one that matters: rounding twice on an awkward
    percentage lands a paisa away, and a purchase order a paisa away from the
    vendor's invoice is a phone call.
    """
    assert PU._line_total(1000.0, 3.0, 10.0) == 2700.0
    assert PU._line_total(1111.11, 3.0, 33.333) == round(
        1111.11 * 3.0 * (1 - 33.333 / 100.0), 2)
    assert PU._line_total(1000.0, 1.0, 100.0) == 0.0


@pytest.mark.parametrize("raw,expect", [
    ("", 0.0), ("   ", 0.0), ("0", 0.0), ("10", 10.0),
    ("12.5", 12.5), ("100", 100.0),
])
def test_a_discount_box_reads_as_a_percentage_and_blank_is_not_a_discount(raw, expect):
    pct, err = PU._parse_discount(raw, "Fire pump set")
    assert err == ""
    assert pct == expect


@pytest.mark.parametrize("raw,fragment", [
    ("-1",    "cannot be negative"),
    ("-0.5",  "cannot be negative"),
    ("100.1", "cannot be more than 100%"),
    ("250",   "cannot be more than 100%"),
    ("abc",   "must be a number"),
])
def test_a_discount_outside_nought_to_a_hundred_is_refused_by_name(raw, fragment):
    """
    Refused, and refused *naming the item* — a form with fifteen line rows and
    a bare "invalid discount" is a hunt.
    """
    pct, err = PU._parse_discount(raw, "Fire pump set")
    assert fragment in err
    assert "Fire pump set" in err
    assert pct == 0.0


# ── Through the form, into the record ──────────────────────────────────────

def _a_product():
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()
    pid, p = sorted(STORE["products"].items())[0]
    return pid, p


def _raise_po(client, *, rate, qty, disc, cgst="9"):
    pid, _p = _a_product()
    return client.post("/purchase/create", data={
        "date": "2026-04-18",
        "vendor_id": VENDOR_ID,
        "status": "Draft",
        "tax_type": "cgst_sgst", "cgst_rate": cgst, "igst_rate": "0",
        "line_product_id": pid, "line_qty": qty,
        "line_rate": rate, "line_discount": disc,
    }, follow_redirects=False)


def _only_po():
    assert len(STORE["purchases"]) == 1
    return list(STORE["purchases"].values())[0]


def test_the_discount_is_stored_on_the_line_and_the_amount_is_already_net(client):
    assert _raise_po(client, rate="1000", qty="3", disc="10").status_code == 302
    po = _only_po()
    line = po["line_items"][0]
    assert line["price"] == 1000.0, "the rate is what was quoted, not what we pay"
    assert line["discount_pct"] == 10.0
    assert line["total"] == 2700.0, "the amount column is net of the discount"


def test_the_discount_reduces_the_tax_because_it_is_inside_the_tax_base(client):
    """
    **The load-bearing test of A2.**

    ₹1,000 × 10 = ₹10,000 list, less 10% = ₹9,000 taxable, CGST 9% + SGST 9% =
    ₹1,620, order value ₹10,620.

    If the discount sat *outside* the tax base the tax would be ₹1,800 on the
    undiscounted ₹10,000 and the order value would be ₹10,800 — ₹180 of input
    credit this office would be telling a vendor to bill for a price nobody is
    paying. The two figures below are what separate those cases.
    """
    assert _raise_po(client, rate="1000", qty="10", disc="10").status_code == 302
    po = _only_po()
    assert po["subtotal"] == 9000.0, "the taxable value follows the discount down"
    assert po["tax_info"]["CGST"] == pytest.approx(810.0)
    assert po["tax_info"]["SGST"] == pytest.approx(810.0)
    assert po["tax_info"]["total"] == pytest.approx(1620.0)
    assert po["grand_total"] == pytest.approx(10620.0)
    # Stated the other way round, so this fails loudly if anyone moves it:
    assert po["grand_total"] != pytest.approx(10800.0)


def test_an_omitted_discount_list_writes_the_same_record_it_always_did(client):
    """
    A POST from anything that does not render the column — an older bookmarked
    form, a script — must not be a broken form. Missing reads as zero.
    """
    pid, _p = _a_product()
    r = client.post("/purchase/create", data={
        "date": "2026-04-18",
        "vendor_id": VENDOR_ID,
        "status": "Draft",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0",
        "line_product_id": pid, "line_qty": "4", "line_rate": "1150",
    })
    assert r.status_code == 302
    po = _only_po()
    assert po["line_items"][0]["discount_pct"] == 0.0
    assert po["line_items"][0]["total"] == 4600.0
    assert po["subtotal"] == 4600.0


def test_a_refused_discount_stops_the_order_being_written_at_all(client):
    pid, _p = _a_product()
    r = client.post("/purchase/create", data={
        "date": "2026-04-18",
        "vendor_id": VENDOR_ID,
        "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "0", "igst_rate": "0",
        "line_product_id": pid, "line_qty": "4", "line_rate": "1150",
        "line_discount": "150",
    })
    assert r.status_code == 200, "a rejected form re-renders, it does not redirect"
    assert "cannot be more than 100%" in r.get_data(as_text=True)
    assert STORE["purchases"] == {}, "nothing was written"


# ── On the printed sheet ───────────────────────────────────────────────────

def test_the_printed_order_draws_the_column_and_the_percentage(client):
    assert _raise_po(client, rate="1000", qty="10", disc="12.5").status_code == 302
    po = _only_po()
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)

    assert '<th class="c-disc">Disc %</th>' in html
    assert '<td class="c-disc">12.5%</td>' in html
    # The rate is still the list rate and the amount is still net.
    assert '<td class="c-price">1,000.00</td>' in html
    assert '<td class="c-total">8,750.00</td>' in html
    # And the taxable value the sheet prints is the discounted one.
    assert "8,750.00" in html
    assert "10,000.00" not in html


def test_a_line_with_no_discount_prints_a_dash_not_a_zero(client):
    """
    "0%" down a whole column reads like a negotiation that failed. An em dash
    reads like what it is: no discount was given on that line.
    """
    assert _raise_po(client, rate="1000", qty="3", disc="").status_code == 302
    po = _only_po()
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert '<td class="c-disc">&#8212;</td>' in html
    assert '<td class="c-disc">0%</td>' not in html


def test_every_row_of_the_printed_table_is_nine_cells_wide(client):
    """
    The alignment guarantee.

    A summary row one cell short does not fail anything — it silently pulls the
    Order Value out from under the Amount column and prints a document that
    looks fine until somebody reads the wrong number off it. So every row is
    counted, including the ones `docsheet` builds.
    """
    assert _raise_po(client, rate="1000", qty="10", disc="10").status_code == 302
    po = _only_po()
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)

    table = html.split('<div class="items-wrap">', 1)[1].split("</table>", 1)[0]
    assert table.count("<th ") == 9 == len(DS.BUY_COLUMNS)

    for row in table.split("<tr")[1:]:
        body = row.split("</tr>", 1)[0]
        width = 0
        for cell in body.split("<td")[1:]:
            head = cell.split(">", 1)[0]
            span = 1
            if 'colspan="' in head:
                span = int(head.split('colspan="', 1)[1].split('"', 1)[0])
            width += span
        if width:                      # the <thead> row has no <td> at all
            assert width == 9, f"a row is {width} cells wide, not 9: {body[:120]}"


# ── What must NOT have happened ────────────────────────────────────────────

def test_the_sell_chain_never_learned_about_the_discount_column():
    """
    A discount a **vendor** allowed **us** has no business on a quotation, a
    proforma or a tax invoice. The separation is two tuples and a CSS constant,
    and it is asserted here as well as by the three pinned goldens, because a
    golden tells you *that* something moved and this tells you *what* was meant
    to be true.
    """
    assert len(DS.SELL_COLUMNS) == 8
    assert "c-disc" not in [cls for cls, _lbl in DS.SELL_COLUMNS]
    assert DS.SUM_BLANKS == ("c-qty", "c-unit", "c-price")
    assert DS.TOTAL_BLANKS == ("c-unit", "c-price")

    import quotation
    assert ".c-disc" not in quotation.QUOTATION_STYLES, \
        "the discount rule belongs to PURCHASE_STYLES; three goldens depend on it"
    assert ".c-disc" in PU.PURCHASE_STYLES


def test_the_shared_summary_rows_still_default_to_the_sell_side_shape():
    """
    `sum_row()` and `total_row()` grew a parameter. The default has to be the
    old output exactly, or the tax invoice and the proforma move for a change
    that was never about them.
    """
    assert DS.sum_row("Taxable Value", "1,000.00") == (
        '\n        <tr class="row-sum">\n'
        '          <td colspan="4" class="sum-lbl">Taxable Value</td>\n'
        '          <td class="c-qty"></td><td class="c-unit"></td>'
        '<td class="c-price"></td>\n'
        '          <td class="c-total">1,000.00</td>\n'
        '        </tr>')
    assert DS.total_row("Total", "6", "1,000.00") == (
        '\n    <tr class="row-total row-sum">\n'
        '      <td colspan="4" class="sum-lbl">Total</td>\n'
        '      <td class="c-qty">6</td>\n'
        '      <td class="c-unit"></td><td class="c-price"></td>\n'
        '      <td class="c-total">1,000.00</td>\n'
        '    </tr>')
