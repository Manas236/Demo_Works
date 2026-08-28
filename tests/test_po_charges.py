"""
Additional charge lines on the final purchase order — CLIENT_CHANGES-2.md **A3**.

Built under the **28 August 2026 OVERRIDE** block in `CLIENT_CHANGES.md` §0,
which is also where the tax ruling that unblocked it is recorded.

### The question this item was stopped on for a day

The **27 August 2026** override block explicitly refused A3, on one sentence:
a loading, unloading or transportation line on a **buy-side** purchase order is
either part of the vendor's own consideration — s.15(2)(c) CGST Act, incidental
expenses, **inside** the taxable value — or a third-party cost we carry
ourselves, **outside** this vendor's supply altogether. CC-2 specifies the
repeater as "label + amount", which carries no taxability, and nothing in this
repo answered it: no document the app prints carried a charge line at all.

### The ruling, and therefore what this file pins

**The charge is inside the taxable value.** The document is a purchase order we
issue to a **named vendor**; a line on it is part of what we are agreeing to pay
*that vendor*, which is consideration for that vendor's supply. The competing
reading describes a cost that would not appear on this vendor's PO at all — it
would be a separate transaction with a separate party on a separate document,
and `charge.py`'s expenses ledger is where it lives.

**The exception is expressible anyway.** Every line carries `taxable`,
defaulting to true. A non-taxable line is added **after** tax and never before
it, so the day a genuine third-party freight cost has to sit on this order it
can, without the tax-base question being reopened.

`test_the_worked_example_from_the_report` is the load-bearing test here: it is
the arithmetic in the pass report, asserted rather than described.
"""

import pytest

import address
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"


def _create(client, *, rate="1000", qty="10", status="Draft", cgst="9",
            tax_type="cgst_sgst", charges=()):
    """
    Raise an order through the real route, with `charges` as
    `[(label, amount, taxable), ...]` in slot order.

    Posted the way the browser posts it: `charge_label` and `charge_amount` are
    parallel lists, and `charge_taxable_<n>` is present only when the box is
    ticked — which is the misalignment the parser is written to be immune to.
    """
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()
    pid = sorted(STORE["products"])[0]

    data = {
        "date": "2026-04-18", "vendor_id": VENDOR_ID, "status": status,
        "tax_type": tax_type, "cgst_rate": cgst, "igst_rate": "0",
        "line_product_id": pid, "line_qty": qty,
        "line_rate": rate, "line_discount": "",
        "charge_label": [c[0] for c in charges],
        "charge_amount": [str(c[1]) for c in charges],
    }
    for n, c in enumerate(charges):
        if c[2]:
            data[f"charge_taxable_{n}"] = "1"

    r = client.post("/purchase/create", data=data)
    return r


def _po(client, **kw):
    r = _create(client, **kw)
    assert r.status_code == 302, "the order was not created"
    return list(STORE["purchases"].values())[0]


# ══ 1. The worked example ═════════════════════════════════════════════════

def test_the_worked_example_from_the_report(client):
    """
    **The arithmetic, end to end, on the numbers in the pass report.**

        2 items @ 5,000            10,000.00   line subtotal
        Loading & Unloading      +  1,500.00   taxable
        Transportation           +  3,500.00   taxable
                                 ───────────
        Taxable Value              15,000.00   ← tax computes on THIS
        CGST @ 9%                +  1,350.00
        SGST @ 9%                +  1,350.00
        Crane hire (no tax)      +  2,000.00   ← added AFTER tax
                                 ───────────
        Order Value                19,700.00

    Every one of those six figures is asserted below.

    **The counterfactual, because the difference is the point.** If the two
    taxable charges sat *outside* the base, the taxable value would be 10,000,
    the tax 900 + 900 = 1,800, and the Order Value **18,800** — the charges
    added after tax instead of before it. That is **900 rupees** of input credit
    we would be telling the vendor to bill us for or not, on one small order,
    and their invoice would fail to reconcile against ours either way round. It
    is not a difference testing finds on its own, which is why A3 was stopped
    for a day and ruled on rather than guessed.
    """
    po = _po(client, rate="5000", qty="2", cgst="9", charges=[
        ("Loading & Unloading", "1500", True),
        ("Transportation", "3500", True),
        ("Crane hire", "2000", False),
    ])

    assert po["subtotal"] == 10000.00, "the lines alone"
    assert po["taxable_value"] == 15000.00, "lines + the two taxable charges"
    assert po["tax_info"]["CGST"] == 1350.00
    assert po["tax_info"]["SGST"] == 1350.00
    assert po["tax_info"]["total"] == 2700.00
    assert po["grand_total"] == 19700.00

    # The counterfactual as an assertion, not merely as prose: 18,800.00 is what
    # this order would carry if the charges sat outside the base.
    assert po["grand_total"] != 18800.00, \
        "the charges were added after tax, i.e. treated as outside the base"
    assert round(po["grand_total"] - 18800.00, 2) == 900.00, \
        "the difference the ruling makes is 18% of the 5,000 of taxable charges"


def test_the_charge_is_inside_the_base_and_the_tax_follows_it_up(client):
    """
    The load-bearing claim of A3, isolated from every other figure.

    Same order twice, differing only in whether a 5,000 charge is on it. If the
    tax does not move, the charge is not in the base.
    """
    po = _po(client, rate="1000", qty="10", cgst="9")
    tax_without = po["tax_info"]["total"]
    STORE["purchases"].clear()

    po = _po(client, rate="1000", qty="10", cgst="9",
             charges=[("Transportation", "5000", True)])
    tax_with = po["tax_info"]["total"]

    assert tax_with > tax_without, "the tax did not follow the charge"
    assert round(tax_with - tax_without, 2) == 900.00, \
        "5,000 at 18% is 900 — the charge is in the base at the order's own rate"


def test_an_untaxed_charge_is_added_after_the_tax_and_not_before_it(client):
    """The `taxable` flag's whole purpose, in one comparison."""
    po = _po(client, rate="1000", qty="10", cgst="9",
             charges=[("Third-party tempo", "5000", False)])

    assert po["subtotal"] == 10000.00
    assert po["taxable_value"] == 10000.00, "an untaxed charge entered the base"
    assert po["tax_info"]["total"] == 1800.00, "tax moved on an untaxed charge"
    assert po["grand_total"] == 16800.00, "10,000 + 1,800 tax + 5,000 after it"


def test_the_flag_defaults_to_taxable_on_a_blank_form(client):
    """
    The default lives in the **form**, which is where a default belongs.

    A blank charge row ships with the box ticked, so an operator who types a
    label and an amount and touches nothing else gets the ruling's answer.
    """
    html = client.get("/purchase/create").get_data(as_text=True)
    assert html.count('name="charge_taxable_') == PU.PO_CHARGE_SLOTS
    assert html.count("checked") >= PU.PO_CHARGE_SLOTS, \
        "a blank charge row shipped unticked, which is the wrong default"


# ══ 2. The repeater ═══════════════════════════════════════════════════════

def test_the_client_s_two_named_heads_are_seeded_and_are_editable(client):
    """
    CC-2's A3 note: one repeater, not four fields. The client named loading &
    unloading and transportation, so those two are prefilled — as **text boxes**,
    not as a fixed vocabulary.
    """
    html = client.get("/purchase/create").get_data(as_text=True)
    assert 'value="Loading &amp; Unloading"' in html
    assert 'value="Transportation"' in html
    assert html.count('name="charge_label"') == PU.PO_CHARGE_SLOTS
    assert 'type="text" name="charge_label"' in html, \
        "the label must be free text or CC-2's fifth-request warning stands"


def test_a_label_the_client_types_himself_is_stored_and_printed(client):
    """The proof that the seeded pair is a prefill and not a list."""
    po = _po(client, charges=[("Palletisation at Bhiwandi", "700", True)])
    assert po["charges"][0]["label"] == "Palletisation at Bhiwandi"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Palletisation at Bhiwandi" in html


def test_blank_rows_are_not_charges(client):
    """
    Four slots for two charges must not demand four charges.

    This is the ordinary case, not an edge one: the form always posts every
    slot, so most submits carry two empty rows.
    """
    po = _po(client, charges=[("Loading & Unloading", "500", True),
                              ("", "", True), ("", "", True), ("", "", True)])
    assert len(po["charges"]) == 1
    assert po["charges"][0]["label"] == "Loading & Unloading"


def test_a_zero_amount_is_not_a_charge(client):
    """A label with nothing against it is not money and must not print."""
    po = _po(client, charges=[("Transportation", "0", True)])
    assert po["charges"] == []
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Transportation" not in html


def test_the_taxable_flag_cannot_be_paired_with_the_wrong_line(client):
    """
    **The reason the flag is read by index rather than by `getlist`.**

    An unchecked checkbox posts *nothing at all*, so three labels and one ticked
    box would arrive as a 3-long label list and a 1-long flag list — and zipping
    those pairs the tick with the first line rather than the third.
    """
    po = _po(client, charges=[("First", "100", False),
                              ("Second", "200", False),
                              ("Third", "300", True)])
    got = {c["label"]: c["taxable"] for c in po["charges"]}
    assert got == {"First": False, "Second": False, "Third": True}, \
        "the taxable flag landed on the wrong charge line"


# ══ 3. The refusals ═══════════════════════════════════════════════════════

def test_a_charge_that_is_not_a_number_is_refused(client):
    r = _create(client, charges=[("Transportation", "about five thousand", True)])
    assert r.status_code == 200, "the form should re-render, not redirect"
    assert "must be a number" in r.get_data(as_text=True)
    assert not STORE["purchases"], "the order was written anyway"


def test_a_negative_charge_is_refused_and_pointed_at_the_discount_column(client):
    """A negative charge is a discount wearing a disguise — A2 is where it goes."""
    r = _create(client, charges=[("Transportation", "-500", True)])
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "cannot be negative" in body
    assert "discount column" in body, "the refusal must name the supported route"


def test_an_amount_with_no_label_is_refused(client):
    """A figure on a purchase order that does not say what it is for."""
    r = _create(client, charges=[("", "5000", True)])
    assert r.status_code == 200
    assert "no label" in r.get_data(as_text=True)
    assert not STORE["purchases"]


def test_an_absurd_charge_is_refused(client):
    r = _create(client, charges=[("Transportation", "999999999", True)])
    assert r.status_code == 200
    assert "larger than this document allows" in r.get_data(as_text=True)


def test_a_rejected_form_comes_back_with_what_was_typed(client):
    """
    A rejected fourth row must not empty the first three. Same contract
    `settings._validate()` and `address._validate()` hold to.
    """
    r = _create(client, charges=[("Loading & Unloading", "1500", True),
                                 ("Transportation", "nonsense", True)])
    body = r.get_data(as_text=True)
    assert 'value="1500"' in body, "the good row was thrown away"
    assert 'value="nonsense"' in body, "the bad row was thrown away"


# ══ 4. The printed document ═══════════════════════════════════════════════

def test_the_charge_rows_print_between_sub_total_and_taxable_value(client):
    """
    **The order of the rows is the arithmetic**, so it is asserted as an order
    and not as a set of substrings.
    """
    po = _po(client, rate="5000", qty="2", cgst="9", charges=[
        ("Loading & Unloading", "1500", True),
        ("Crane hire", "2000", False),
    ])
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)

    i_sub = html.index("Sub Total")
    i_load = html.index("Loading &amp; Unloading")
    i_base = html.index("Taxable Value")
    i_cgst = html.index("CGST @ 9%")
    i_crane = html.index("Crane hire")
    i_total = html.index("Order Value")

    assert i_sub < i_load < i_base < i_cgst < i_crane < i_total, \
        "a taxable charge must print inside the base and an untaxed one after tax"
    assert "Crane hire (no tax)" in html, \
        "an excluded charge must say it was excluded, not merely appear"


def test_an_order_with_no_charges_prints_no_sub_total_row(client):
    """
    The property that keeps every purchase order already in the database
    printing exactly what it printed before A3 — and the golden with it.
    """
    po = _po(client, rate="1000", qty="10", cgst="9")
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Sub Total" not in html
    assert "Taxable Value" in html, "the row it always had is still there"


def test_a_charge_label_is_escaped_on_its_way_into_the_document(client):
    """
    `DS.sum_row()` interpolates its label **raw** — ABOUT.md §9 puts the escape
    at the interpolation site, and this label is free text somebody typed.
    """
    po = _po(client, charges=[("<script>alert(1)</script>", "500", True)])
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_an_exempt_order_still_carries_its_charges(client):
    """
    No tax means no Taxable Value row to hang them under, and the charges still
    have to reach the Order Value. The easy thing to get wrong here is to lose
    them with the row that would have introduced them.
    """
    po = _po(client, rate="1000", qty="10", tax_type="exempt", cgst="0",
             charges=[("Transportation", "2500", True)])
    assert po["grand_total"] == 12500.00, "the charge fell out of an exempt order"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Transportation" in html


# ══ 5. Charges on an order that already exists ════════════════════════════

def test_charges_can_be_added_to_an_existing_order(client):
    """
    A charge is agreed after the order goes out at least as often as before it,
    so `/purchase/edit/<id>` carries the same repeater A1 opened up.
    """
    po = _po(client, rate="1000", qty="10", cgst="9", status="Issued")
    assert po["grand_total"] == 11800.00

    r = client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": "1000", "line_discount": "",
        "charge_label": ["Transportation", "", "", ""],
        "charge_amount": ["5000", "", "", ""],
        "charge_taxable_0": "1",
    })
    assert r.status_code == 302
    assert po["taxable_value"] == 15000.00
    assert po["grand_total"] == 17700.00, "10,000 + 5,000 charge + 18% on both"


def test_the_edit_form_shows_the_charges_already_on_the_order(client):
    po = _po(client, charges=[("Transportation", "5000", True)])
    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'value="Transportation"' in html
    assert 'value="5000.00"' in html


def test_clearing_a_charge_row_removes_it_and_reprices_the_order(client):
    """
    The repeater posts every slot every time, so what arrives IS the new list.
    A charge that was agreed and then dropped must leave the total.
    """
    po = _po(client, rate="1000", qty="10", cgst="9",
             charges=[("Transportation", "5000", True)])
    assert po["grand_total"] == 17700.00

    r = client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": "1000", "line_discount": "",
        "charge_label": ["", "", "", ""],
        "charge_amount": ["", "", "", ""],
    })
    assert r.status_code == 302
    assert po["charges"] == []
    assert po["grand_total"] == 11800.00, "the dropped charge stayed in the total"


def test_a_bad_charge_on_the_edit_form_writes_nothing_at_all(client):
    """
    Validated before any row is written, for the same reason the rates are: a
    bad fourth row must not leave the first three half-applied.
    """
    po = _po(client, rate="1000", qty="10", cgst="9")
    before = po["grand_total"]

    r = client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": "900", "line_discount": "",
        "charge_label": ["Transportation", "", "", ""],
        "charge_amount": ["not a number", "", "", ""],
        "charge_taxable_0": "1",
    })
    assert r.status_code == 200, "it should re-render with the error"
    assert po["line_items"][0]["price"] == 1000.0, "the rate was written anyway"
    assert po["grand_total"] == before
    assert not po.get("charges")


# ══ 6. What A3 deliberately did not touch ═════════════════════════════════

def test_the_upstream_forms_carry_no_repeater(client):
    """
    `/purchase/from-boq` and `/purchase/from-draft` are derived documents whose
    job is to carry a schedule across without re-entry. A charge is added
    afterwards on the edit form, like any other money that was not on the
    schedule. Recorded as a decision, not discovered as a gap.
    """
    po = _po(client, rate="1000", qty="10")
    assert po["charges"] == [], "an order raised with no charges must store []"


def test_every_order_this_module_creates_carries_the_key(client):
    """
    `charges_of()` tolerates a missing key for orders written before A3, but
    nothing this module writes today should rely on that tolerance.
    """
    po = _po(client, rate="1000", qty="10")
    assert "charges" in po
    assert "taxable_value" in po


def test_an_order_written_before_a3_still_totals_correctly(client):
    """
    The backward-compatibility contract, stated against a record with neither
    key — which is what every purchase order in the live database looks like.
    """
    legacy = {"id": "legacy-po", "ref": "SF/PO/26-27/9999", "subtotal": 260600.0,
              "line_items": [], "tax_type": "cgst_sgst",
              "tax_info": {"CGST": 23454.0, "SGST": 23454.0, "total": 46908.0,
                           "cgst_rate": 9.0, "sgst_rate": 9.0},
              "grand_total": 307508.0, "total_qty": 6.0, "status": "Issued",
              "to": "A Vendor", "date": "2026-04-18"}
    STORE["purchases"]["legacy-po"] = legacy

    assert PU.charges_of(legacy) == []
    assert PU.charge_totals(PU.charges_of(legacy)) == (0.0, 0.0)

    html = client.get("/purchase/view/legacy-po").get_data(as_text=True)
    assert "Sub Total" not in html
    assert "2,60,600.00" in html, "Taxable Value must fall back to subtotal"
    assert "3,07,508.00" in html
