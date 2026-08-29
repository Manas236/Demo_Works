"""
Extra free-text lines on a purchase order.

⚠ **THIS IS NOT ONE OF CLIENT_CHANGES-2.md's TWENTY PHASE 3 ITEMS**, and this
file says so first because the mistake is cheap to make and expensive to
correct. It is a client request made *after* the 19 August 2026 meeting that
produced that list, it carries no 3A/3B/3C tag, and it is priced in neither
MG/SF/2026-01 nor MG/SF/2026-02. Built under the **29 August 2026 OVERRIDE**
block in `CLIENT_CHANGES.md` §0, which records it as new unpriced scope and
forbids counting it toward the board.

### The requirement

BOQ items are not enough. When raising a purchase order the client needs to ask
the vendor for additional parts that appear nowhere on the BOQ. He sent a list
of those parts with **no prices and no units**, and wants assumed prices seeded
so that a real order can go out today and be corrected later.

### The shape, which the owner chose and this file pins

**Extra lines are free text typed onto each order.** No parts master, no
catalogue collection, no picker, no per-vendor rate table. `po_parts.py` is a
**typeahead prefill and nothing else** — every rate in it an assumed
placeholder, expected to be overwritten.

### The three things that must not be conflated

There are **three** concepts on this record, not two:

    line_items   BOQ-derived / catalogue lines, carry a `line_id`  → subtotal
    extra_lines  free-text parts, carry NO `line_id`               → subtotal
    charges      A3's labelled repeater (loading, freight)         → taxable_value

An extra line is a **line**, not a charge: it is goods this company is buying
from this vendor, so it sits inside `subtotal` exactly where a `line_items` row
sits. A charge is what the vendor bills us *beyond* the goods and joins one
step later. Getting that wrong produces the right grand total by the wrong
route and prints it in the wrong place on the sheet.

`test_the_worked_example` is the load-bearing test here: it puts all three on
one order at once and asserts every figure.
"""

import pytest

import address
import po_parts as PP
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"


def _create(client, *, rate="1000", qty="10", status="Draft", cgst="9",
            tax_type="cgst_sgst", extras=(), charges=()):
    """
    Raise an order through the real route.

    `extras` is `[(desc, unit, qty, rate, disc), ...]`, posted the way the
    browser posts the repeater: five parallel lists. `charges` is A3's
    `[(label, amount, taxable), ...]`.
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
        "extra_desc":     [str(e[0]) for e in extras],
        "extra_unit":     [str(e[1]) for e in extras],
        "extra_qty":      [str(e[2]) for e in extras],
        "extra_rate":     [str(e[3]) for e in extras],
        "extra_discount": [str(e[4]) for e in extras],
        "charge_label":  [c[0] for c in charges],
        "charge_amount": [str(c[1]) for c in charges],
    }
    for n, c in enumerate(charges):
        if c[2]:
            data[f"charge_taxable_{n}"] = "1"
    return client.post("/purchase/create", data=data)


def _po(client, **kw):
    r = _create(client, **kw)
    assert r.status_code == 302, "the order was not created"
    return list(STORE["purchases"].values())[0]


# ══ 1. The worked example — all three concepts on one order ═══════════════

def test_the_worked_example(client):
    """
    **The arithmetic, end to end, with all three kinds of money present.**

        1 item @ 10,000 x 1              10,000.00   line_items
        Bullet fastener 8mm  100 @ 12  +  1,200.00   extra_lines  ← a LINE
        Cutting wheel 4 inch  20 @ 45  +    900.00   extra_lines  ← a LINE
                                       ───────────
        Sub Total                        12,100.00   ← extra lines are INSIDE it
        Loading & Unloading            +  1,500.00   charges, taxable
                                       ───────────
        Taxable Value                    13,600.00   ← tax computes on THIS
        CGST @ 9%                      +  1,224.00
        SGST @ 9%                      +  1,224.00
                                       ───────────
        Order Value                      16,048.00

    Every one of those figures is asserted.

    **The counterfactual, because the difference is the point.** Route the two
    extra lines through `_parse_charges()` instead — the tempting merge, since
    both are "money that was not on the schedule" — and the *grand total* comes
    out identical at 16,048.00 while `subtotal` reads **10,000** instead of
    12,100. The order would then print a Sub Total that does not include goods
    it is ordering, with 2,100 rupees of parts appearing under the totals as
    though the vendor were billing us a fee. **The total hides the error; the
    printed sheet does not.** That is why they enter at different points.
    """
    po = _po(client, rate="10000", qty="1", extras=[
        ("Bullet fastener 8mm", "Nos", "100", "12", ""),
        ("Cutting wheel 4 inch", "Nos", "20", "45", ""),
    ], charges=[("Loading & Unloading", "1500", True)])

    assert po["subtotal"] == 12100.00
    assert PU.extra_lines_total(po["extra_lines"]) == 2100.00
    assert po["taxable_value"] == 13600.00
    assert po["tax_info"]["CGST"] == 1224.00
    assert po["tax_info"]["SGST"] == 1224.00
    assert po["grand_total"] == 16048.00

    # The counterfactual, asserted rather than described: had the extra lines
    # gone in as charges, subtotal would have stayed at the item total.
    assert po["subtotal"] != 10000.00, \
        "extra lines belong INSIDE subtotal, not after it with the charges"


# ══ 2. It reaches the record and the printed order ════════════════════════

def test_an_extra_line_reaches_the_stored_record(client):
    po = _po(client, extras=[("Butane gas", "Nos", "4", "130", "")])
    assert len(po["extra_lines"]) == 1
    row = po["extra_lines"][0]
    assert row["description"] == "Butane gas"
    assert row["unit"] == "Nos"
    assert row["qty"] == 4.0
    assert row["rate"] == 130.0
    assert row["total"] == 520.00


def test_an_extra_line_reaches_the_printed_order(client):
    """It prints as a line in the items table, not as a note under the totals."""
    po = _po(client, extras=[("Butane gas", "Nos", "4", "130", "")])
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Butane gas" in html
    # In the items table, on an ordinary item row — the same class a
    # `line_items` row uses, because it is the same kind of thing.
    body = html.split('<div class="items-wrap">')[1]
    assert "Butane gas" in body, "an extra line belongs in the items table"


def test_the_subtotal_includes_the_extra_line(client):
    """`subtotal` is the sum of the lines, and an extra line IS a line."""
    plain = _po(client, rate="1000", qty="10")
    assert plain["subtotal"] == 10000.00

    STORE["purchases"].clear()
    withx = _po(client, rate="1000", qty="10",
                extras=[("Paint roller", "Nos", "5", "90", "")])
    assert withx["subtotal"] == 10450.00
    assert withx["total_qty"] == 15.0, \
        "extra lines are quantities of goods and count toward the order's qty"


# ══ 3. The discount, and that it is inside the tax base ═══════════════════

def test_a_discount_on_an_extra_line_reduces_the_tax_base(client):
    """
    A2's rule, applied to an extra line: **the discount is inside the base.**

    100 @ 12 = 1,200 less 25% = 900. That 900 is what lands in `total`, so it
    is what `subtotal` sums, and `subtotal` is the first term the tax is
    computed from. Taxing 1,200 would overstate the input credit we tell the
    vendor to bill — the same reasoning `_line_total()` carries for item rows,
    reached through the same function rather than a second copy of it.
    """
    # The item line is present but free, so the whole tax base is the extra
    # line and the arithmetic below has nothing else in it.
    po = _po(client, rate="0", qty="1", cgst="9",
             extras=[("Bullet fastener 8mm", "Nos", "100", "12", "25")])
    row = po["extra_lines"][0]
    assert row["discount_pct"] == 25.0
    assert row["total"] == 900.00, "rounded once, on the discounted product"

    assert po["subtotal"] == 900.00
    assert po["taxable_value"] == 900.00
    assert po["tax_info"]["CGST"] == 81.00, "9% of 900, not of 1,200"

    # The counterfactual: undiscounted, the base would be 1,200 and the CGST
    # 108.00 — 27 rupees of input credit on one line, on a price nobody is
    # paying. That is what "the discount is inside the base" buys.
    assert po["tax_info"]["CGST"] != 108.00


def test_the_discount_arithmetic_is_the_same_function_as_the_item_rows(client):
    """
    Not a second copy of `_line_total()`, and not a second copy of
    `_parse_discount()` either.

    Asserted by result rather than by reading the source: an extra line and an
    item line with the same qty, rate and discount must produce the identical
    amount, to the paisa, including the rounding.
    """
    po = _po(client, rate="1234.56", qty="7", extras=[
        ("Some part nobody has heard of", "Nos", "7", "1234.56", "13.5")])
    item = [r for r in po["line_items"] if not r.get("is_header")][0]
    # The item row carries no discount; compute what one with 13.5% would be.
    assert po["extra_lines"][0]["total"] == PU._line_total(1234.56, 7, 13.5)
    assert item["total"] == PU._line_total(1234.56, 7, 0)


# ══ 4. NO line_id. Ever. ══════════════════════════════════════════════════

def test_an_extra_line_carries_no_line_id(client):
    """
    **`line_id` is a BOQ identity and an extra line has no BOQ ancestor.**

    Not "is empty" — **absent**. `/purchase/from-boq` matches a row back to a
    schedule on this key (ABOUT.md §2f, and the ₹1,99,122.50 that matching on
    `item_no` once cost). A free-text part is on no schedule, so minting one
    would make it claim an ancestry it does not have, and any code walking PO
    lines by `line_id` would silently pick it up.
    """
    po = _po(client, extras=[("Butane gas", "Nos", "4", "130", "")])
    for row in po["extra_lines"]:
        assert "line_id" not in row, \
            "an extra line must not carry a line_id, not even a blank one"


def test_no_code_reads_line_id_unguarded_over_po_lines():
    """
    The other half of the rule: nothing may assume the key is there.

    Every read of `line_id` in `purchase.py` goes through `.get()` or
    `BQ._line_id()`, both of which tolerate absence. A bare `row["line_id"]`
    would raise a KeyError the first time an order carrying an extra line met
    it, which is the failure this test exists to make impossible to introduce.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "purchase.py").read_text(encoding="utf8")
    for bad in ('["line_id"]', "['line_id']"):
        assert bad not in src, (
            f"purchase.py subscripts line_id directly ({bad}). An extra line "
            f"has no line_id, so every read of it must be .get()-guarded.")


# ══ 5. Blank rows, and rows with no rate ══════════════════════════════════

def test_an_all_blank_row_is_dropped_silently(client):
    """
    The editor opens with three blank rows on purpose, and an untouched one is
    not a mistake to shout about — `_parse_lines()`'s own contract.
    """
    po = _po(client, extras=[
        ("", "", "", "", ""),
        ("Butane gas", "Nos", "4", "130", ""),
        ("", "", "", "", ""),
    ])
    assert len(po["extra_lines"]) == 1
    assert po["extra_lines"][0]["description"] == "Butane gas"


def test_a_description_with_no_rate_is_kept_and_shown_as_incomplete(client):
    """
    **This is the client's actual case**, so it is kept rather than refused: he
    sent a list of parts with no prices at all. The row stores rate 0 and the
    printed order flags it in the same amber the blank-HSN guard uses, because
    the vendor is being asked to price it.
    """
    po = _po(client, extras=[("Some unpriced thing", "Nos", "5", "", "")])
    assert len(po["extra_lines"]) == 1
    row = po["extra_lines"][0]
    assert row["rate"] == 0.0
    assert row["total"] == 0.0
    assert row["rate_is_assumed"] is False, \
        "no rate means nothing was assumed — there is no figure to assume"

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Some unpriced thing" in html
    assert "todo-chip" in html, "an unpriced line must be flagged as incomplete"


def test_a_figure_with_no_description_is_refused(client):
    """
    A figure on a purchase order that does not say what it is for is exactly
    what a vendor queries. Same refusal `_parse_charges()` makes.
    """
    r = _create(client, extras=[("", "Nos", "10", "500", "")])
    assert r.status_code == 200, "the form should re-render, not redirect"
    assert "no description" in r.get_data(as_text=True)
    assert not STORE["purchases"], "nothing may be written on a refused POST"


def test_a_negative_rate_is_refused(client):
    r = _create(client, extras=[("Butane gas", "Nos", "4", "-130", "")])
    assert r.status_code == 200
    assert "cannot be negative" in r.get_data(as_text=True)
    assert not STORE["purchases"]


# ══ 6. The assumed-rate marker ════════════════════════════════════════════

def test_the_prefill_sets_rate_is_assumed(client):
    """
    A seeded part at its seeded rate is marked. The mark says "this figure came
    out of `po_parts.py` and nobody has replaced it", which is the whole of what
    it claims.
    """
    _canon, unit, seeded = PP.lookup("Butane gas")
    po = _po(client, extras=[("Butane gas", unit, "4", str(seeded), "")])
    assert po["extra_lines"][0]["rate_is_assumed"] is True


def test_an_edited_rate_clears_the_assumed_mark(client):
    """
    **Clears the moment the rate is edited to anything else.** Derived on the
    server from the rate itself rather than remembered in a hidden field, so a
    stale or tampered form cannot clear the mark while keeping the figure.
    """
    po = _po(client, extras=[("Butane gas", "Nos", "4", "155", "")])
    assert po["extra_lines"][0]["rate_is_assumed"] is False
    assert po["extra_lines"][0]["rate"] == 155.0


def test_a_part_that_is_on_no_seed_list_is_never_marked_assumed(client):
    po = _po(client, extras=[("Entirely bespoke bracket", "Nos", "2", "999", "")])
    row = po["extra_lines"][0]
    assert row["rate_is_assumed"] is False
    assert row["description"] == "Entirely bespoke bracket", \
        "free text is accepted exactly as typed — this is not a vocabulary"


def test_the_assumed_chip_never_appears_in_the_printed_output(client):
    """
    ⚠ **The vendor receives the order; the vendor does not receive our note that
      we invented the price.**

    Two things are asserted, because either alone would be a false comfort:
    the chip is on the screen page at all (otherwise the test passes for the
    wrong reason), and the stylesheet takes it out at print.
    """
    _c, unit, seeded = PP.lookup("Butane gas")
    po = _po(client, extras=[("Butane gas", unit, "4", str(seeded), "")])
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)

    assert "xl-assumed" in html, "the chip must render on screen"
    # Rewritten on 29 August 2026 when the chip wording changed. The previous
    # assertion was, verbatim:
    #
    #     assert "assumed" in html
    #
    # It never failed and never could: `xl-assumed` is the CLASS name, so the
    # substring was in the page whatever the chip said — it would have passed
    # against a chip reading "verified market price". The text is asserted now.
    assert "placeholder &middot; not quoted" in html,         "the chip must say the figure is a placeholder nobody has quoted"

    # ...and must be removed at print by a rule, not by hope.
    assert "@media print { .xl-assumed { display:none !important; } }" in html, \
        "the assumed chip must be display:none at print"


def test_an_order_with_no_assumed_rate_draws_no_chip(client):
    po = _po(client, extras=[("Entirely bespoke bracket", "Nos", "2", "999", "")])
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert '<span class="xl-assumed">' not in html


# ══ 7. The seed table itself ══════════════════════════════════════════════

def test_an_alias_prefills_the_same_rate_as_its_canonical_name():
    """
    The client's list had duplicates and typos. Both spellings must reach the
    same row, or the operator has to know which one is the "real" one.
    """
    for alias, canonical in [
        ("Soket 15mm",            "Socket 15mm"),
        ("Bullet Fastner 8mm",    "Bullet fastener 8mm"),
        ("Lather hand gloves",    "Leather hand gloves"),
        ("M.S ANGEL 50 X 50 X 5 MM", "M.S. angle 50x50x5 mm"),
        ("MS coupling 15mm threded", "MS coupling 15mm threaded"),
        ("4\" Cutting wheel",     "Cutting wheel 4 inch"),
        ("Cutting wheel",         "Cutting wheel 4 inch"),
        ("2\" roller",            "2 inch roller"),
        ("GP Thinner 20ltr",      "GP thinner 20 ltr"),
        ("4sq 2core Flexible Wire", "4 sq mm 2-core flexible wire"),
        ("20a 1ph 3way Ac Box",   "20A 1ph 3-way AC box"),
        ("Safety shoes 10no",     "Safety shoes"),
    ]:
        assert PP.lookup(alias) == PP.lookup(canonical), \
            f"{alias!r} must prefill the same rate as {canonical!r}"


def test_an_alias_prefills_through_the_form_too(client):
    """
    The alias is not just a lookup nicety: a line typed with the client's own
    spelling must be marked assumed at the canonical rate, or the mark would
    quietly depend on how somebody spelled it.
    """
    _c, _u, seeded = PP.lookup("Bullet fastener 8mm")
    po = _po(client, extras=[("Bullet Fastner 8mm", "Nos", "10", str(seeded), "")])
    assert po["extra_lines"][0]["rate_is_assumed"] is True
    assert po["extra_lines"][0]["description"] == "Bullet Fastner 8mm", \
        "what was typed is what is stored — the alias resolves the RATE, not the text"


def test_no_part_is_seeded_twice():
    """
    Duplicates were to be resolved into `aliases`, not seeded as two rows. A
    part with two entries would carry two different assumed rates and prefill
    whichever the dict happened to reach first.
    """
    seen = {}
    for canonical, row in PP.PARTS.items():
        for key in [canonical] + list(row.get("aliases") or []):
            norm = PP._norm(key)
            assert norm not in seen or seen[norm] == canonical, (
                f"{key!r} maps to both {seen.get(norm)!r} and {canonical!r}")
            seen[norm] = canonical


def test_the_brand_qualified_variants_are_kept_apart():
    """
    `Yellow primer` and `Yellow primer Asian` are different goods at different
    rates, and the client drew the distinction himself. Folding them would lose
    it.
    """
    assert PP.lookup("Yellow primer 20 ltr")[2] != \
        PP.lookup("Yellow primer Asian 20 ltr")[2]
    assert PP.lookup("PO red paint 20 ltr")[2] != \
        PP.lookup("PO red paint Asian 20 ltr")[2]


def test_po_red_paint_is_seeded_verbatim_and_not_renamed():
    """
    ⚠ **An OPEN QUESTION FOR THE CLIENT, pinned so it cannot be closed by
      accident.**

    "PO red paint" is most likely red-oxide primer, written `P.O. Red` or
    `R.O. Red` on the client's sheet. It has deliberately **not** been renamed:
    guessing would put a word in the client's mouth on a document that goes to
    a vendor. If the answer comes back "red oxide", change the canonical names
    and add these spellings as aliases — and delete this test with the commit
    that does it, not before.
    """
    assert "PO red paint 20 ltr" in PP.PARTS
    assert not any("oxide" in name.lower() for name in PP.PARTS), \
        "nobody has answered the question yet; do not rename it silently"


def test_the_seeded_rates_are_never_presented_as_real_prices():
    """
    The one claim this whole feature must never make. Asserted against the
    module's own docstring, because that is the text a reader lands on.
    """
    doc = (PP.__doc__ or "").upper()
    assert "ASSUMED PLACEHOLDER" in doc
    assert "NOT A QUOTED" in doc or "NONE OF IT IS A QUOTED" in doc


# ══ 8. The edit form ══════════════════════════════════════════════════════

def test_extra_lines_round_trip_through_the_edit_form(client):
    po = _po(client, extras=[("Butane gas", "Nos", "4", "130", "")])
    r = client.get(f"/purchase/edit/{po['id']}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Butane gas" in html, "the stored line must come back into the form"
    assert 'name="extra_desc"' in html


def test_the_edit_form_can_add_and_remove_an_extra_line(client):
    """
    Not positional, unlike the item rows: this repeater can gain and lose rows,
    so `_reprice()` re-reads it whole rather than diffing it.
    """
    po = _po(client, rate="1000", qty="10",
             extras=[("Butane gas", "Nos", "4", "130", "")])
    pid = po["id"]
    rows = PU._priced_rows(po)

    r = client.post(f"/purchase/edit/{pid}", data={
        "line_rate": [f"{float(x.get('price') or 0):.2f}" for _i, x in rows],
        "line_discount": ["" for _ in rows],
        "extra_desc":     ["Paint roller", "Red jacket"],
        "extra_unit":     ["Nos", "Nos"],
        "extra_qty":      ["3", "2"],
        "extra_rate":     ["90", "650"],
        "extra_discount": ["", ""],
        "charge_label": [], "charge_amount": [],
    })
    assert r.status_code == 302
    po = STORE["purchases"][pid]
    assert [x["description"] for x in po["extra_lines"]] == \
        ["Paint roller", "Red jacket"]
    assert po["subtotal"] == 10000.0 + 270.0 + 1300.0


def test_editing_only_the_extra_lines_is_not_reported_as_nothing_changed(client):
    """
    "Nothing changed, so nothing was recorded" would be a lie about a save that
    happened. It goes on the order's own status trail rather than faking an
    entry in `reprice_log`, which lists rate movements on item lines.
    """
    po = _po(client, rate="1000", qty="10")
    pid = po["id"]
    rows = PU._priced_rows(po)
    before = len(po.get("status_history") or [])

    r = client.post(f"/purchase/edit/{pid}", data={
        "line_rate": [f"{float(x.get('price') or 0):.2f}" for _i, x in rows],
        "line_discount": ["" for _ in rows],
        "extra_desc": ["Paint roller"], "extra_unit": ["Nos"],
        "extra_qty": ["3"], "extra_rate": ["90"], "extra_discount": [""],
        "charge_label": [], "charge_amount": [],
    }, follow_redirects=False)
    assert r.status_code == 302

    po = STORE["purchases"][pid]
    assert len(po["status_history"]) == before + 1
    assert not po.get("reprice_log"), \
        "an extra-line edit is not a rate movement on an item line"


# ══ 9. Where the repeater is, and where it deliberately is not ════════════

def test_the_repeater_is_on_create_and_edit(client):
    po = _po(client)
    for url in ("/purchase/create", f"/purchase/edit/{po['id']}"):
        html = client.get(url).get_data(as_text=True)
        assert 'name="extra_desc"' in html, f"{url} must offer the repeater"
        assert 'id="xl-parts"' in html, f"{url} must offer the typeahead"


def test_the_repeater_is_NOT_on_the_two_picker_flows(client):
    """
    ⚠ **A deliberate deviation, matching the call A3 made for its own repeater.**

    `/purchase/from-boq` and `/purchase/from-draft` are picker flows over a
    schedule; their job is to carry ticked lines across without re-entry.
    Bolting a free-text surface onto a picker is a second design — two ways of
    adding a line on one form, one traceable to the schedule and one not. A part
    on no schedule is added afterwards on `/purchase/edit/<id>`.
    """
    import boq
    boq.ensure_demo_boq()
    boq_id = sorted(STORE["boqs"])[0]
    html = client.get(f"/purchase/from-boq/{boq_id}").get_data(as_text=True)
    assert 'name="extra_desc"' not in html, \
        "the picker flow must not grow a free-text line surface"


def test_every_order_this_module_creates_carries_the_key(client):
    """
    `extra_lines` is written even when empty, exactly as `charges` is, so code
    downstream never has to ask which route wrote the record.
    """
    import boq
    boq.ensure_demo_boq()
    po = _po(client)
    assert "extra_lines" in po and po["extra_lines"] == []


def test_an_order_written_before_this_pass_reads_as_empty(client):
    """
    No backfill. An order with no `extra_lines` key at all reads as `[]` and
    renders byte-for-byte what it always rendered — the same contract
    `charges_of()` and `proforma.prior_invoiced` hold to.
    """
    po = _po(client)
    del po["extra_lines"]
    assert PU.extra_lines_of(po) == []
    assert PU.extra_lines_total(PU.extra_lines_of(po)) == 0.0
    assert client.get(f"/purchase/view/{po['id']}").status_code == 200


# ══ 10. Job costing — extra-line value gets its own row ═══════════════════

def test_extra_line_value_is_reported_on_a_row_of_its_own(client):
    """
    **An extra line is real cost with no BOQ line behind it.**

    Folded silently into `committed` it would be invisible; dropped, it would
    understate the job. So it is reported as its own figure *as well as* inside
    `committed` — the honest pair, because it genuinely is part of the
    commitment and it genuinely answers to nothing on any schedule.
    """
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()
    import quotation  # noqa: F401

    qid = "jc-quote-0001"
    STORE["quotations"][qid] = {"id": qid, "ref": "QT-9001",
                                "grand_total": 100000.0, "line_items": []}
    pid = sorted(STORE["products"])[0]
    client.post("/purchase/create", data={
        "date": "2026-04-18", "vendor_id": VENDOR_ID, "status": "Draft",
        "quotation_id": qid,
        "tax_type": "exempt", "cgst_rate": "0", "igst_rate": "0",
        "line_product_id": pid, "line_qty": "10", "line_rate": "1000",
        "line_discount": "",
        "extra_desc": ["Paint roller"], "extra_unit": ["Nos"],
        "extra_qty": ["5"], "extra_rate": ["90"], "extra_discount": [""],
        "charge_label": [], "charge_amount": [],
    })

    jc = PU.job_cost(qid)
    assert jc["committed"] == 10450.0, "the whole commitment"
    assert jc["extra_committed"] == 450.0, "and how much of it is on no schedule"
    assert jc["extra_count"] == 1
    assert jc["extra_committed"] < jc["committed"], \
        "the breakout is part of committed, not a second total beside it"


def test_the_job_costing_chip_says_so_only_when_there_is_something_to_say(client):
    """
    Rendered only when there is extra-line value — which is what keeps
    `/purchase/view`'s pinned bytes still on an order that has none. Same
    contract as the Reprice button and the upstream chip strip.
    """
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()

    qid = "jc-quote-0002"
    STORE["quotations"][qid] = {"id": qid, "ref": "QT-9002",
                                "grand_total": 100000.0, "line_items": []}
    pid = sorted(STORE["products"])[0]

    def _raise(extras):
        return client.post("/purchase/create", data={
            "date": "2026-04-18", "vendor_id": VENDOR_ID, "status": "Draft",
            "quotation_id": qid,
            "tax_type": "exempt", "cgst_rate": "0", "igst_rate": "0",
            "line_product_id": pid, "line_qty": "10", "line_rate": "1000",
            "line_discount": "",
            "extra_desc":     [e[0] for e in extras],
            "extra_unit":     [e[1] for e in extras],
            "extra_qty":      [e[2] for e in extras],
            "extra_rate":     [e[3] for e in extras],
            "extra_discount": ["" for _ in extras],
            "charge_label": [], "charge_amount": [],
        })

    _raise([])
    plain = list(STORE["purchases"].values())[0]
    html = client.get(f"/purchase/view/{plain['id']}").get_data(as_text=True)
    assert "job costing" in html
    assert "extra parts" not in html, \
        "an order with no extra lines must draw the string it always drew"

    _raise([("Paint roller", "Nos", "5", "90")])
    withx = [p for p in STORE["purchases"].values() if p["extra_lines"]][0]
    html = client.get(f"/purchase/view/{withx['id']}").get_data(as_text=True)
    assert "extra parts" in html
    assert "on no schedule" in html


# ══ 11. The control — nothing else moved ══════════════════════════════════

# The golden fixtures live in `test_print_golden.py` and are imported here
# rather than copied. A fixture is found in the test module's own namespace, so
# importing the decorated functions is enough to make them usable below —
# `pinned_identity` comes too because the other three depend on it.
from test_print_golden import (  # noqa: E402
    golden, golden_dc, golden_picker, golden_ra, pinned_identity,  # noqa: F401
)


def test_the_other_pinned_documents_did_not_move(client, golden, golden_ra,
                                                 golden_dc, golden_picker):
    """
    **The control for this whole pass.**

    `/purchase/view` moved and was re-baselined, in the `head` block, by exactly
    the 1,800 characters of `.xl-*` stylesheet. **Nothing else may have.** This
    re-runs the other pinned digests from `test_print_golden.py` against their
    own recorded values — the proforma, the tax invoice, the RA bill, the
    delivery challan and `/po/create` — so that a change to a shared sheet
    cannot hide behind a purchase order that was expected to move.

    It is deliberately a second assertion of what `test_print_golden.py` already
    checks. Two files failing says "a shared sheet moved"; one says "the buy
    side moved", and telling those apart from the failure message is worth the
    duplication.

    ⚠ **The quotation view page is NOT among them, and that is a fact about the
      repo rather than an omission here.** `test_print_golden.py` pins the
      proforma, the tax invoice, the purchase order, the RA bill, the delivery
      challan and the `/po/create` picker form — six things, and
      `/quotation/view` is not one of them. There is no `Q_WHOLE` to assert
      against. `quotation.py` was not edited in this pass, and the sheets it
      owns are covered transitively by the five documents below that render
      through them.
    """
    from test_print_golden import (
        GOLD_DC, GOLD_PI, GOLD_PICK_BOQ, GOLD_TI,
        DC_BLOCKS, DC_LEN, DC_WHOLE,
        PI_BLOCKS, PI_LEN, PI_WHOLE,
        PICK_BLOCKS, PICK_LEN, PICK_WHOLE, PICKER_BLOCKS,
        RA_BLOCKS, RA_LEN, RA_WHOLE,
        TI_BLOCKS, TI_LEN, TI_WHOLE,
        _check,
    )

    for url, whole, length, blocks, markers, what in [
        (f"/proforma/view/{GOLD_PI}", PI_WHOLE, PI_LEN, PI_BLOCKS,
         None, "proforma"),
        (f"/invoice/view/{GOLD_TI}", TI_WHOLE, TI_LEN, TI_BLOCKS,
         None, "tax invoice"),
        ("/ra/print/gold-ra", RA_WHOLE, RA_LEN, RA_BLOCKS, None, "RA bill"),
        (f"/dc/print/{GOLD_DC}", DC_WHOLE, DC_LEN, DC_BLOCKS,
         None, "delivery challan"),
        (f"/po/create?boq={GOLD_PICK_BOQ}", PICK_WHOLE, PICK_LEN, PICK_BLOCKS,
         PICKER_BLOCKS, "/po/create picker form"),
    ]:
        r = client.get(url)
        assert r.status_code == 200, f"{what} did not render"
        kw = {"markers": markers} if markers is not None else {}
        _check(r.get_data(as_text=True), whole, length, blocks, what=what, **kw)


# ══ 8. The server is the mechanism, and the JavaScript is not ═════════════
#
# ⚠ **The pass that built this feature could not run a line of its own
#   JavaScript, and neither can this file.** There is no JS test harness in this
#   repo and adding one was not authorised. `xlFill()`, `addExtra()` and
#   `recalc()` were asserted only as *strings present in the response* — which
#   proves they were rendered and proves nothing about whether they work.
#
#   Worse, the page carried `xlNorm()`, a JavaScript reimplementation of
#   `po_parts._norm()`, with **nothing checking that the two agreed**. The day
#   they diverged, the box would prefill a rate the server then declined to mark
#   as a placeholder, and an invented price would reach a vendor with no chip on
#   it — the exact failure the chip exists to prevent.
#
#   The fix was not a test for the divergence. It was to **remove the
#   possibility of one**: the server fills a blank rate on POST from
#   `po_parts.py`, and the browser gets a finished lookup table it resolves
#   nothing with. Every test below runs with **no JavaScript executed at all**,
#   which is both the honest test condition and the condition the repo is in.


def test_the_server_fills_a_blank_rate_for_a_seeded_part(client):
    """
    **The load-bearing test of the inversion.** A seeded description with an
    empty rate box, posted with no JavaScript anywhere near it, comes back
    priced from `po_parts.py` — and flagged, because the figure is the
    placeholder.
    """
    _canon, unit, seeded = PP.lookup("Butane gas")
    po = _po(client, extras=[("Butane gas", "", "4", "", "")])
    row = po["extra_lines"][0]

    assert row["rate"] == seeded, "the server must fill the rate, not the browser"
    assert row["unit"] == unit, "and the unit with it"
    assert row["total"] == round(seeded * 4, 2)
    assert row["rate_is_assumed"] is True

    # It is inside `subtotal`, exactly as a typed rate would be.
    assert po["subtotal"] == round(10 * 1000 + seeded * 4, 2)


def test_an_alias_fills_the_same_rate_as_its_canonical_name_on_POST(client):
    """
    Server-side, through the form, with a blank rate box. Until 29 August 2026
    the map handed to the browser held **canonical names only**, so not one of
    the client's own spellings ever prefilled anything.
    """
    _c, canon_unit, seeded = PP.lookup("Bullet fastener 8mm")
    po = _po(client, extras=[("Bullet Fastner 8mm", "", "10", "", "")])
    row = po["extra_lines"][0]

    assert row["rate"] == seeded
    assert row["unit"] == canon_unit
    assert row["rate_is_assumed"] is True
    assert row["description"] == "Bullet Fastner 8mm", \
        "what was typed is what is stored — the alias resolves the RATE, not the text"


def test_a_description_matching_nothing_is_stored_as_typed_with_a_blank_rate(client):
    """
    The list narrows nothing. A part on no seed row is accepted exactly as
    typed, keeps its blank rate, and carries no flag — there is no figure to
    call a placeholder.
    """
    po = _po(client, extras=[("Entirely bespoke bracket", "Nos", "2", "", "")])
    row = po["extra_lines"][0]

    assert row["description"] == "Entirely bespoke bracket"
    assert row["rate"] == 0.0
    assert row["total"] == 0.0
    assert row["rate_is_assumed"] is False


def test_a_rate_different_from_the_seed_is_stored_verbatim_and_not_flagged(client):
    """
    A real quoted price. The server must not touch it and must not call it a
    placeholder — the box was not blank, so nothing is filled.
    """
    _c, _u, seeded = PP.lookup("Butane gas")
    typed = seeded + 25.0
    po = _po(client, extras=[("Butane gas", "Nos", "4", str(typed), "")])
    row = po["extra_lines"][0]

    assert row["rate"] == typed, "a typed rate is never overwritten"
    assert row["rate_is_assumed"] is False


def test_a_rate_equal_to_the_seed_IS_flagged_however_it_was_typed(client):
    """
    ⚠ **The marker is a claim about the FIGURE, not about who put it there.**

    Type `Butane gas` and its seeded rate by hand, with the server filling
    nothing, and the line is still flagged. A human who types the placeholder
    from memory has invented a price just as surely as the server has, and the
    chip says so in those terms rather than implying the operator was assisted.
    """
    _c, _u, seeded = PP.lookup("Butane gas")
    po = _po(client, extras=[("Butane gas", "Nos", "4", str(seeded), "")])
    assert po["extra_lines"][0]["rate_is_assumed"] is True


def test_an_explicit_zero_rate_is_a_typed_rate_and_is_not_filled(client):
    """
    `0` is a figure somebody chose; an empty box is not. Only the empty box is
    filled, which is the same "suggest, never impose" contract `fillRate()`
    holds one repeater along.
    """
    po = _po(client, extras=[("Butane gas", "Nos", "4", "0", "")])
    row = po["extra_lines"][0]
    assert row["rate"] == 0.0, "an explicit zero must survive the prefill"
    assert row["rate_is_assumed"] is False


def test_a_typed_unit_is_never_overwritten_by_the_seeded_one(client):
    po = _po(client, extras=[("Butane gas", "Cylinder", "4", "", "")])
    row = po["extra_lines"][0]
    assert row["unit"] == "Cylinder"
    assert row["rate"] == PP.lookup("Butane gas")[2], \
        "the rate still fills; only the unit was already given"


# ══ 9. The lookup map handed to the browser ═══════════════════════════════

def test_the_prefill_map_is_the_server_index_and_nothing_else():
    """
    Same keys as `po_parts.INDEX` — the set `PP.lookup()` matches on. Built
    from it rather than beside it, so "what the browser thinks matches" and
    "what the server matches" cannot become two different questions.
    """
    m = PP.prefill_map()
    assert set(m) == set(PP.INDEX), \
        "the browser's key set must BE the server's key set"
    for key, canonical in PP.INDEX.items():
        assert m[key]["r"] == float(PP.PARTS[canonical]["assumed_rate"])
        assert m[key]["u"] == PP.PARTS[canonical]["unit"]


def test_the_prefill_map_contains_no_un_normalised_keys():
    """
    Every key is already through `_norm()`. The browser is handed a finished
    table, never the rules for building one.
    """
    for key in PP.prefill_map():
        assert key == PP._norm(key), f"{key!r} reaches the page un-normalised"


def test_the_prefill_map_resolves_aliases_before_it_reaches_the_page():
    """
    The alias keys must be IN the map. Until 29 August 2026 it was built from
    `PARTS` alone — canonical names only, no aliases — so every one of the
    client's own spellings missed in the browser.
    """
    m = PP.prefill_map()
    for alias, canonical in [("soket 15mm", "Socket 15mm"),
                             ("bullet fastner 8mm", "Bullet fastener 8mm"),
                             ("lather hand gloves", "Leather hand gloves"),
                             ("cutting wheel", "Cutting wheel 4 inch")]:
        assert alias in m, f"{alias!r} must be a key the browser can hit"
        assert m[alias]["r"] == float(PP.PARTS[canonical]["assumed_rate"])


@pytest.mark.parametrize("page", ["create", "edit"])
def test_the_page_carries_no_JS_normalisation_function(client, page):
    """
    ⚠ **`xlNorm()` is gone and must not come back.**

    It was a second implementation of `po_parts._norm()`, in another language,
    that nothing could check. One source of truth means the page holds a
    finished table and no rules — so there is no normalisation *function* on it
    to drift from the Python one.
    """
    po = _po(client, extras=[("Butane gas", "Nos", "4", "", "")])
    path = "/purchase/create" if page == "create" else f"/purchase/edit/{po['id']}"
    html = client.get(path).get_data(as_text=True)

    assert "xlNorm" not in html, \
        "the page must carry no JavaScript reimplementation of _norm()"
    assert "XSEED" in html, "the rendered lookup table must still be there"
    assert "function xlFill" in html


@pytest.mark.parametrize("page", ["create", "edit"])
def test_the_rendered_map_on_the_page_is_normalised_and_alias_resolved(client, page):
    """
    Asserted against the bytes actually served, not against `prefill_map()` —
    the map is rendered through `json_for_script()` and it is the rendered form
    the browser reads.
    """
    import json

    po = _po(client, extras=[("Butane gas", "Nos", "4", "", "")])
    path = "/purchase/create" if page == "create" else f"/purchase/edit/{po['id']}"
    html = client.get(path).get_data(as_text=True)

    raw = html.split("var XSEED = ", 1)[1].split(";", 1)[0]
    served = json.loads(raw)

    assert set(served) == set(PP.INDEX), "the served map must be the whole index"
    for key in served:
        assert key == PP._norm(key), f"{key!r} was served un-normalised"
    assert "soket 15mm" in served, "aliases must reach the browser resolved"
