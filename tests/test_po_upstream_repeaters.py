"""
The extra-parts and additional-charge repeaters on the two UPSTREAM forms —
`/purchase/from-boq/<boq_id>` and `/purchase/from-draft/<draft_id>` — and the
live Amount column on every purchase-order form.

### What changed, and why it is a reversal rather than a gap closing

Both repeaters were kept OFF the two upstream forms **deliberately**, twice:
A3's charges on 28 August 2026 and the extra parts on 29 August, each recorded
as a deviation — *"picker flows over a schedule; a free-text surface on a
picker is a second design; a part on no schedule is added afterwards on
`/purchase/edit/<id>`, exactly as a charge is."* ABOUT.md §5 `/purchase`,
PROGRESS.md §4a, and `test_the_repeater_is_NOT_on_the_two_picker_flows` pinned
it.

**The owner rejected that on 14 September 2026**, having raised an order from a
draft and found both sections missing from the form that goes to the vendor
while the reprice form beside it carried both. An order is written once;
sending it out and then reopening it to add the loading charge is the
re-entry the route exists to avoid. So the two widgets are drawn on all four
forms now — `_extra_section_html()` and `_charge_section_html()`, the same
functions, so no form can describe either field differently — and both lists
reach `_write_upstream_po()` and enter the arithmetic through `_totals_of()`,
the same single door `create_purchase()` uses.

**What did NOT change:** the schedule-line rule. `/from-boq` still refuses
nothing ticked and `/from-draft` still refuses a draft with no lines. The extra
parts ride on an order that has a schedule behind it; an order of extra parts
alone belongs on `/purchase/create` (gap 38).

### The second half — the Amount column

`/purchase/edit/<id>` shipped with `function recalc() {}` — a stub so the
shared widgets could call it — which left every Amount cell reading "—"
against a row carrying a quantity and a rate. The fix moved the JavaScript the
repeater needs into ONE helper, `_po_form_script_html()`, drawn by every form,
with the per-row arithmetic (`lineAmt()`, `_line_total()`'s shape) in it
once. There is no JS harness in this repo, so what is asserted here is that the
stub is gone, the helper is on every page, and the reprice rows carry the
`data-qty` the preview multiplies by. ⚠ **That proves the bytes are served,
not that they run** — the same limit `tests/test_po_extra_lines.py` §8 states.

⚠ No assertion in this file may pass against a blank page. Every one names a
  part, a charge, a figure or a key that only appears when the feature worked.
"""

import json

import pytest

import address
import boq as BQ
import demo_data as DD
import po_parts as PP
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"

ORDER = {"date": "2026-09-14", "vendor_id": VENDOR_ID, "status": "Draft",
         "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "18"}


@pytest.fixture()
def shop(client):
    """The seeded Sify schedule and a vendor from the address book."""
    client.get("/boq/")
    client.get("/settings/")
    address.ensure_demo_addresses()
    bid = DD.BOQ_META["id"]
    priced = [li for li in STORE["boqs"][bid]["line_items"]
              if not li.get("is_header") and float(li.get("total_qty") or 0) > 0]
    yield {"boq": bid, "lines": priced}
    STORE.setdefault("purchase_orders", {}).clear()
    STORE["purchases"].clear()


def _a_draft(client, boq_id, lines):
    r = client.post(f"/po/create?boq={boq_id}", data={
        "date": "2026-09-14", "vendor_id": VENDOR_ID, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "",
                                          "pcs": ""} for li in lines]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return next(iter(STORE["purchase_orders"]))


def _from_boq(client, shop, lines, **over):
    data = dict(ORDER, po_json=json.dumps({"lines": [
        {"line_id": li["line_id"], "qty": "10", "rate": "1000"} for li in lines]}))
    data.update(over)
    return client.post(f"/purchase/from-boq/{shop['boq']}", data=data)


def _from_draft(client, did, lines, **over):
    data = dict(ORDER, dl_line_id=[li["line_id"] for li in lines],
                dl_qty=["10"] * len(lines), dl_rate=["1000"] * len(lines))
    data.update(over)
    return client.post(f"/purchase/from-draft/{did}", data=data)


def _only_po():
    assert len(STORE["purchases"]) == 1, "expected exactly one purchase order"
    return next(iter(STORE["purchases"].values()))


# The same two additions on every POST below: one extra part with a discount,
# one taxable charge and one exempt charge. Worked figures, on one schedule
# line at 10 x 1000:
#
#   subtotal      = 10,000 + (4 x 150 x 0.90 = 540)   = 10,540.00
#   taxable_value = 10,540 + 250 (loading, taxable)   = 10,790.00
#   tax           = 10,790 x 18%                      =  1,942.20
#   grand_total   = 10,790 + 1,942.20 + 60 (exempt)   = 12,792.20
ADDITIONS = {
    "extra_desc": ["150mm flange", "", ""], "extra_unit": ["Nos", "", ""],
    "extra_qty": ["4", "", ""], "extra_rate": ["150", "", ""],
    "extra_discount": ["10", "", ""],
    "charge_label": ["Loading & Unloading", "Transportation", "Octroi", ""],
    "charge_amount": ["250", "", "60", ""],
    "charge_taxable_0": "1",
    # charge_taxable_2 deliberately absent: the Octroi line is exempt.
}


# ══ 1. Both surfaces are on both forms ═════════════════════════════════════

def test_from_boq_offers_both_repeaters(shop, client):
    html = client.get(f"/purchase/from-boq/{shop['boq']}").get_data(as_text=True)
    assert 'name="extra_desc"' in html and 'id="xl-parts"' in html
    assert 'name="charge_label"' in html and 'name="charge_taxable_0"' in html
    assert 'value="Loading &amp; Unloading"' in html, "the seeded head must prefill"
    assert 'id="xline-tpl"' in html and "function xlFill" in html
    assert "function xlAmounts" in html, "the shared script must be on the page"


def test_from_draft_offers_both_repeaters(shop, client):
    did = _a_draft(client, shop["boq"], shop["lines"][:2])
    html = client.get(f"/purchase/from-draft/{did}").get_data(as_text=True)
    assert 'name="extra_desc"' in html and 'id="xl-parts"' in html
    assert 'name="charge_label"' in html and 'name="charge_taxable_0"' in html
    assert 'value="Loading &amp; Unloading"' in html
    assert 'id="xline-tpl"' in html and "function xlFill" in html
    assert "function xlAmounts" in html


def test_the_sections_sit_between_the_lines_and_the_tax(shop, client):
    """Where `/purchase/create` draws them, so the form reads the same way."""
    html = client.get(f"/purchase/from-boq/{shop['boq']}").get_data(as_text=True)
    lines = html.index("Lines to order")
    extra = html.index("Extra parts")
    charge = html.index("Additional charges")
    tax = html.index("Tax the vendor will charge us")
    assert lines < extra < charge < tax


# ══ 2. Both lists reach the record, through _totals_of() ═══════════════════

def test_from_boq_stores_the_extra_part_and_both_charges(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    po = _only_po()

    assert [x["description"] for x in po["extra_lines"]] == ["150mm flange"]
    x = po["extra_lines"][0]
    assert (x["unit"], x["qty"], x["rate"], x["discount_pct"], x["total"]) == \
        ("Nos", 4.0, 150.0, 10.0, 540.0)
    assert "line_id" not in x, "an extra line has no BOQ ancestor"
    assert x["rate_is_assumed"] is False, "150 is not the seeded placeholder for anything"

    assert po["charges"] == [
        {"label": "Loading & Unloading", "amount": 250.0, "taxable": True},
        {"label": "Octroi", "amount": 60.0, "taxable": False},
    ]
    assert po["subtotal"] == 10540.0
    assert po["taxable_value"] == 10790.0
    assert round(po["tax_info"]["CGST"], 2) == round(po["tax_info"]["SGST"], 2) == 971.1
    assert po["grand_total"] == 12792.2
    assert po["total_qty"] == 14.0, "extra parts are goods and count toward quantity"
    # The upstream links are untouched by the additions.
    assert po["boq_id"] == shop["boq"]
    priced = [r_ for r_ in po["line_items"] if not r_.get("is_header")]
    assert [r_["line_id"] for r_ in priced] == [shop["lines"][0]["line_id"]]


def test_from_draft_stores_the_extra_part_and_both_charges(shop, client):
    picked = shop["lines"][:1]
    did = _a_draft(client, shop["boq"], picked)
    r = _from_draft(client, did, picked, **ADDITIONS)
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    po = _only_po()

    assert [x["description"] for x in po["extra_lines"]] == ["150mm flange"]
    assert po["extra_lines"][0]["total"] == 540.0
    assert [c["label"] for c in po["charges"]] == ["Loading & Unloading", "Octroi"]
    assert po["subtotal"] == 10540.0
    assert po["taxable_value"] == 10790.0
    assert po["grand_total"] == 12792.2
    assert po["draft_id"] == did
    assert STORE["purchase_orders"][did]["converted_po_ids"] == [po["id"]]


def test_the_figures_are_totals_of_and_not_a_private_copy(shop, client):
    """The same arithmetic `create_purchase()` and `_reprice()` use, by call."""
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302
    po = _only_po()
    sub, taxable, tax, grand, qty = PU._totals_of(
        po["line_items"], po["tax_type"], 9.0, 18.0, po["charges"], po["extra_lines"])
    assert (sub, taxable, grand, qty) == (
        po["subtotal"], po["taxable_value"], po["grand_total"], po["total_qty"])
    assert tax == po["tax_info"]


def test_both_reach_the_printed_order(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302
    po = _only_po()
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "150mm flange" in html
    assert "Loading &amp; Unloading" in html
    assert "Octroi (no tax)" in html, "an exempt charge prints as such"
    assert "12,792.20" in html


# ══ 3. Nothing typed is lost on a rejected POST, and nothing is written ═════

@pytest.mark.parametrize("route", ["from-boq", "from-draft"])
def test_a_rejected_post_hands_back_what_was_typed_in_both_repeaters(
        shop, client, route):
    """
    A figure with no description is refused by `_parse_extra_lines()`; the
    refusal must come back with the other rows still filled in, and with the
    charge rows still filled in too — `_form_values()`'s contract, which is
    `address._validate()`'s.
    """
    bad = dict(ADDITIONS, extra_desc=["150mm flange", "", ""],
               extra_qty=["4", "7", ""])          # row 2: a qty, no part
    picked = shop["lines"][:1]
    if route == "from-boq":
        r = _from_boq(client, shop, picked, **bad)
    else:
        did = _a_draft(client, shop["boq"], picked)
        r = _from_draft(client, did, picked, **bad)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Extra line 2 has figures but no description" in html
    assert 'value="150mm flange"' in html, "the good row was emptied"
    assert 'value="7"' in html, "the bad row's figure was emptied"
    assert 'value="Octroi"' in html and 'value="60"' in html, \
        "the charge rows were emptied"
    assert len(STORE["purchases"]) == 0, "a rejected POST must write nothing"


@pytest.mark.parametrize("route", ["from-boq", "from-draft"])
def test_a_bad_charge_is_refused_the_same_way(shop, client, route):
    bad = dict(ADDITIONS, charge_label=["", "", "", ""], charge_amount=["250", "", "", ""])
    picked = shop["lines"][:1]
    if route == "from-boq":
        r = _from_boq(client, shop, picked, **bad)
    else:
        did = _a_draft(client, shop["boq"], picked)
        r = _from_draft(client, did, picked, **bad)
    assert r.status_code == 200
    assert "has an amount but no label" in r.get_data(as_text=True)
    assert len(STORE["purchases"]) == 0


# ══ 4. The server prefill works here too — the browser is not the mechanism ═

def test_a_seeded_part_with_a_blank_rate_is_filled_on_the_server(shop, client):
    picked = shop["lines"][:1]
    did = _a_draft(client, shop["boq"], picked)
    r = _from_draft(client, did, picked,
                    extra_desc=["Butane gas"], extra_unit=[""],
                    extra_qty=["4"], extra_rate=[""], extra_discount=[""])
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    x = _only_po()["extra_lines"][0]
    _canonical, unit, seeded = PP.lookup("Butane gas")
    assert x["rate"] == seeded and x["unit"] == unit
    assert x["rate_is_assumed"] is True, "a seeded figure is a placeholder, and marked"


# ══ 5. The schedule-line rule did not move ═════════════════════════════════

def test_from_boq_with_nothing_ticked_is_still_refused_extra_parts_or_not(shop, client):
    """An order of extra parts alone belongs on `/purchase/create`, not here."""
    r = _from_boq(client, shop, [], **ADDITIONS)
    assert r.status_code == 200
    assert "No lines are ticked" in r.get_data(as_text=True)
    assert len(STORE["purchases"]) == 0


def test_an_order_with_neither_addition_is_what_it_always_was(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1])
    assert r.status_code == 302
    po = _only_po()
    assert po["extra_lines"] == [] and po["charges"] == []
    assert po["subtotal"] == po["taxable_value"] == 10000.0
    assert po["grand_total"] == 11800.0


# ══ 6. The Amount column — the stub is gone and the helper is everywhere ═══

def test_the_reprice_form_no_longer_stubs_recalc(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302
    po = _only_po()
    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert "function recalc() {}" not in html, "the stub that left every Amount '—'"
    assert "function xlAmounts" in html and "function lineAmt" in html
    # The item row carries the quantity the preview multiplies by, and its
    # boxes call the preview.
    assert '<div class="line-row" data-qty="10">' in html
    assert html.count('oninput="recalc()"') >= 2, "rate and discount boxes must be live"
    # The script sits AFTER the form, so the rows exist when recalc() runs at load.
    assert html.index("</form>") < html.index("function xlAmounts")


@pytest.mark.parametrize("page", ["create", "from-boq", "from-draft", "edit"])
def test_every_form_draws_the_one_shared_script(shop, client, page):
    """
    One `XSEED`, one `xlFill`, one `lineAmt` per page — the helper, not a
    copy. Two copies were how the reprice form's stub happened.
    """
    if page == "create":
        path = "/purchase/create"
    elif page == "from-boq":
        path = f"/purchase/from-boq/{shop['boq']}"
    elif page == "from-draft":
        path = f"/purchase/from-draft/{_a_draft(client, shop['boq'], shop['lines'][:1])}"
    else:
        assert _from_boq(client, shop, shop["lines"][:1]).status_code == 302
        path = f"/purchase/edit/{_only_po()['id']}"
    html = client.get(path).get_data(as_text=True)
    for marker in ("var XSEED = ", "function xlFill(", "function lineAmt(",
                   "function xlAmounts(", "function addExtra(", 'id="xline-tpl"'):
        assert html.count(marker) == 1, f"{page}: {marker!r} appears {html.count(marker)}x"
    assert "xlNorm" not in html
    assert html.count("function recalc(") == 1, f"{page}: the page must define recalc() once"
    served = json.loads(html.split("var XSEED = ", 1)[1].split(";", 1)[0])
    assert set(served) == set(PP.INDEX)


def test_purchase_py_holds_one_copy_of_the_prefill_lookup():
    """The `XSEED[...]` lookup is written once, in `_po_form_script_html()`."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "purchase.py").read_text(encoding="utf8")
    assert src.count("var XSEED = ") == 1
    assert src.count("function xlFill(") == 1
    assert src.count("function addExtra(") == 1
    assert src.count("Math.round(q * r * (1 - d / 100) * 100) / 100") == 1, \
        "_line_total()'s JavaScript shape must exist once, in lineAmt()"


# ══ 7. The HSN box — the chip was asking for a figure no form offered ══════
#
# The printed order runs every goods row's HSN through `B.field()`, which
# draws the `add HSN` chip on a blank one — and prints it, as bracketed
# italics, to the vendor. An item row's HSN comes from the catalogue; an extra
# part had NO HSN field at all, so every extra part printed "[add HSN]" and
# nothing anybody typed could satisfy it. The owner asked where the box was.
# It exists now, on the same repeater on all four forms, optional and free
# text — `po_parts.py` seeds none, because an HSN is statutory data and an
# invented one is worse than a chip.

def test_every_form_offers_an_hsn_box_on_the_extra_row(shop, client):
    did = _a_draft(client, shop["boq"], shop["lines"][:1])
    for path in ("/purchase/create", f"/purchase/from-boq/{shop['boq']}",
                 f"/purchase/from-draft/{did}"):
        html = client.get(path).get_data(as_text=True)
        assert 'name="extra_hsn"' in html, f"{path}: no HSN box on the extra row"
        assert "<span>Part</span><span>HSN</span>" in html, f"{path}: no HSN column head"


def test_an_hsn_typed_on_an_extra_part_is_stored_and_printed(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1],
                  **dict(ADDITIONS, extra_hsn=["73072900", "", ""]))
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    po = _only_po()
    assert po["extra_lines"][0]["hsn"] == "73072900"

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    row = html.split("150mm flange", 1)[1].split("</tr>", 1)[0]
    assert '<td class="c-hsn">73072900</td>' in row
    assert "add HSN" not in row, "a typed HSN must not be chipped"


def test_a_blank_hsn_still_prints_the_chip_but_can_now_be_answered(shop, client):
    """
    The chip is right to ask — the house rule is that a blank statutory field
    never looks deliberate — and this pins that it still asks. What changed is
    that the reprice form now carries the box to answer it with.
    """
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302
    po = _only_po()
    assert po["extra_lines"][0]["hsn"] == ""
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    row = html.split("150mm flange", 1)[1].split("</tr>", 1)[0]
    assert '<span class="todo-chip">add HSN</span>' in row

    edit = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="extra_hsn" value=""' in edit, "the reprice form must offer the box"


def test_the_hsn_round_trips_through_the_reprice_form(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302
    po = _only_po()
    x = po["extra_lines"][0]
    r = client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": ["1000"], "line_discount": [""],
        "extra_desc": [x["description"]], "extra_hsn": ["73072900"],
        "extra_unit": [x["unit"]], "extra_qty": ["4"], "extra_rate": ["150"],
        "extra_discount": ["10"]})
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    assert po["extra_lines"][0]["hsn"] == "73072900"
    assert po["extra_lines"][0]["total"] == 540.0, "nothing else on the row moved"

    edit = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="extra_hsn" value="73072900"' in edit


def test_an_extra_line_written_before_the_box_reads_as_blank(shop, client):
    """No backfill: a stored row with no `hsn` key prints the chip, as it did."""
    r = _from_boq(client, shop, shop["lines"][:1], **ADDITIONS)
    assert r.status_code == 302
    po = _only_po()
    del po["extra_lines"][0]["hsn"]
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    row = html.split("150mm flange", 1)[1].split("</tr>", 1)[0]
    assert '<span class="todo-chip">add HSN</span>' in row
    edit = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="extra_hsn" value=""' in edit


def test_an_hsn_with_no_description_is_refused_like_any_other_figure(shop, client):
    r = _from_boq(client, shop, shop["lines"][:1],
                  **dict(ADDITIONS, extra_hsn=["", "73072900", ""]))
    assert r.status_code == 200
    assert "Extra line 2 has figures but no description" in r.get_data(as_text=True)
    assert len(STORE["purchases"]) == 0


def test_no_seeded_part_carries_an_hsn():
    """`po_parts.py` prefills a unit and a placeholder rate — never an HSN."""
    for name, part in PP.PARTS.items():
        assert "hsn" not in {k.lower() for k in part}, f"{name} seeds an HSN"
    for key, hit in PP.prefill_map().items():
        assert set(hit) == {"u", "r"}, f"{key}: the prefill map must carry unit and rate only"
