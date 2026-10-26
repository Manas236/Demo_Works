"""
The **Make** column on the purchase order and the draft PO (26 October 2026) —
CLIENT_CHANGES.md §0, the fifty-third block, change 2.

Make is the brand of an item — "SANT" on a butterfly valve. The rules:

* a free-text, optional `make` on every line of the PO (`line_items` and
  `extra_lines`) and of the draft PO, **snapshotted on the line** and absent
  when blank;
* on the create AND edit forms of both, and carried through every path that
  builds a PO line: from the BOQ, converting a draft, and Import from Excel —
  whose column pickers offer it;
* printed as a column **immediately right of "Description"**, narrow;
* **not prefilled**: neither a BOQ line nor a specification-library variant has
  a make field, so every Make box opens blank (a BOQ remark reading
  "Make: Jindal" is NOT read — it is not a field);
* an order written before this — no `make` key anywhere — still prints, with an
  empty cell under the column, which is never hidden.

⚠ No assertion here may pass against a blank page: each names a make, a cell
  or a position that only appears when the feature worked.
"""

import json
import re

import pytest

import address
import boq as BQ
import boqpick as BP
import demo_data as DD
import docimport as DI
import docsheet as DS
import po_draft as DPO
import sheetimport as SI
import conftest
from store import STORE
from test_print_golden import (  # noqa: F401
    GOLD_DPO, GOLD_PO, golden, golden_dpo, golden_ra, pinned_identity)

VENDOR_ID = "b2000006-face-4000-8000-000000000006"
ORDER = {"date": "2026-10-26", "vendor_id": VENDOR_ID, "status": "Draft",
         "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "18"}


@pytest.fixture()
def shop(client):
    """
    The seeded Sify schedule and a vendor from the address book. The draft-PO
    series is put back afterwards: raising a draft advances its stored counter,
    and a record left behind would reach every later test that reads settings.
    """
    import settings as SET
    client.get("/boq/")
    client.get("/settings/")
    address.ensure_demo_addresses()
    saved_series = STORE["settings"].get(SET.PO_SERIES_RECORD)
    bid = DD.BOQ_META["id"]
    priced = [li for li in STORE["boqs"][bid]["line_items"]
              if not li.get("is_header") and float(li.get("total_qty") or 0) > 0]
    yield {"boq": bid, "lines": priced}
    STORE.setdefault("purchase_orders", {}).clear()
    STORE["purchases"].clear()
    if saved_series is None:
        STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    else:
        STORE["settings"][SET.PO_SERIES_RECORD] = saved_series


def _only(collection):
    recs = list(STORE[collection].values())
    assert len(recs) == 1, f"expected one {collection} record, found {len(recs)}"
    return recs[0]


def _heads(html: str) -> list:
    """The printed items table's column classes, in order."""
    items = html[html.index('<div class="items-wrap">'):]
    head = items[:items.index("</tr></thead>")]
    return re.findall(r'<th class="([^"]+)"', head)


def _row_of(html: str, text: str) -> str:
    """The printed table row carrying `text`."""
    at = html.index(text)
    return html[html.rindex("<tr", 0, at):html.index("</tr>", at)]


def _cells(row: str) -> list:
    return re.findall(r'<td class="([^"]+)"', row)


# ══ 1. The column, where it prints ═════════════════════════════════════════

def test_the_po_prints_make_immediately_right_of_the_description(client, golden):
    html = client.get(f"/purchase/view/{GOLD_PO}").get_data(as_text=True)
    heads = _heads(html)
    assert heads[heads.index("c-desc") + 1] == "c-make"
    assert '<th class="c-make">Make</th>' in html
    assert ".quotation-doc .c-make { width:18mm;" in html, "the column is not kept narrow"
    assert "c-make" not in html[:html.index('<div class="items-wrap">')], (
        "the column's rule must ride in the items block, not the sheet's head")


def test_the_draft_po_prints_make_immediately_right_of_the_description(client, golden_dpo):
    for url in (f"/po/print/{GOLD_DPO}", f"/po/view/{GOLD_DPO}"):
        html = client.get(url).get_data(as_text=True)
        heads = _heads(html)
        assert heads[heads.index("c-desc") + 1] == "c-make", url
        assert ".quotation-doc .c-make { width:18mm;" in html


def test_every_po_row_is_as_wide_as_its_head_with_a_picture_too(client, golden):
    """The Image column and the Make column together: every row still 11 wide."""
    import lineimage as LI
    po = STORE["purchases"][GOLD_PO]
    po["line_items"][0]["make"] = "SANT"
    html = client.get(f"/purchase/view/{GOLD_PO}").get_data(as_text=True)
    table = html.split('<div class="items-wrap">', 1)[1].split("</table>", 1)[0]
    width = table.count("<th ")
    assert width == len(DS.BUY_COLUMNS) == 10
    for row in table.split("<tr")[1:]:
        cells = row.split("</tr>", 1)[0].split("<td")[1:]
        if cells:
            span = sum(int(c.split('colspan="', 1)[1].split('"', 1)[0])
                       if 'colspan="' in c.split(">", 1)[0] else 1 for c in cells)
            assert span == width, row[:160]
    assert LI.COLUMN not in DS.BUY_COLUMNS


# ══ 2. Old records ═════════════════════════════════════════════════════════

def test_an_old_po_with_no_make_key_prints_an_empty_cell(client, golden):
    po = STORE["purchases"][GOLD_PO]
    assert not any("make" in r for r in po["line_items"])
    html = client.get(f"/purchase/view/{GOLD_PO}").get_data(as_text=True)
    assert '<th class="c-make">Make</th>' in html, "the column must not be hidden"
    row = _row_of(html, "Fire pump set, 2280 LPM")
    cells = _cells(row)
    assert cells[cells.index("c-desc") + 1] == "c-make"
    assert '<td class="c-make"></td>' in row


def test_an_old_draft_po_with_no_make_key_prints_an_empty_cell(client, golden_dpo):
    html = client.get(f"/po/print/{GOLD_DPO}").get_data(as_text=True)
    assert html.count('<td class="c-make"></td>') >= 1


# ══ 3. Create and edit — the purchase order ════════════════════════════════

def test_make_on_an_extra_part_is_stored_and_printed_beside_the_description(client, shop):
    r = client.post("/purchase/create", data=dict(
        ORDER, extra_desc=["80mm Butterfly valve", "", ""], extra_make=["SANT", "", ""],
        extra_unit=["Nos", "", ""], extra_qty=["2", "", ""], extra_rate=["4200", "", ""]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    xl = _only("purchases")["extra_lines"][0]
    assert xl["make"] == "SANT"
    html = client.get(f"/purchase/view/{_only('purchases')['id']}").get_data(as_text=True)
    row = _row_of(html, "80mm Butterfly valve")
    assert '<td class="c-make">SANT</td>' in row
    cells = _cells(row)
    assert cells[cells.index("c-desc") + 1] == "c-make"


def test_a_blank_make_writes_no_key(client, shop):
    client.post("/purchase/create", data=dict(
        ORDER, extra_desc=["Gasket", "", ""], extra_make=["  ", "", ""],
        extra_qty=["1", "", ""], extra_rate=["10", "", ""]))
    assert "make" not in _only("purchases")["extra_lines"][0]


def test_make_on_a_catalogue_item_is_stored(client, shop, catalogue_unhidden):
    pid, p = next(iter(STORE["products"].items()))
    r = client.post("/purchase/create", data=dict(
        ORDER, line_product_id=[pid], line_make=["Kirloskar"], line_qty=["1"],
        line_rate=["100"], line_discount=[""]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert _only("purchases")["line_items"][0]["make"] == "Kirloskar"


def test_the_create_form_offers_make_on_both_repeaters(client, shop):
    html = client.get("/purchase/create").get_data(as_text=True)
    assert 'name="line_make"' in html and 'name="extra_make"' in html
    assert "<span>Part</span><span>Make</span>" in html
    assert "<span>Item</span><span>Make</span>" in html


def test_a_rejected_create_keeps_the_typed_make(client, shop):
    r = client.post("/purchase/create", data=dict(
        ORDER, date="", extra_desc=["Valve", "", ""], extra_make=["SANT", "", ""]))
    assert r.status_code == 200
    assert 'name="extra_make" value="SANT"' in r.get_data(as_text=True)


def test_make_is_capped_and_escaped(client, shop):
    client.post("/purchase/create", data=dict(
        ORDER, extra_desc=["Valve", "", ""], extra_make=["<b>X</b>" + "y" * 100, "", ""],
        extra_qty=["1", "", ""], extra_rate=["1", "", ""]))
    po = _only("purchases")
    assert len(po["extra_lines"][0]["make"]) == BP.MAKE_MAX
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "<b>X</b>" not in html and "&lt;b&gt;X&lt;/b&gt;" in html


def _po_from_boq(client, shop, n=2):
    """A Draft order with real `line_items`, raised from the schedule."""
    r = client.post(f"/purchase/from-boq/{shop['boq']}", data=dict(ORDER, po_json=json.dumps(
        {"lines": [{"line_id": li["line_id"], "qty": "3", "rate": "100"}
                   for li in shop["lines"][:n]]})))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    po = _only("purchases")
    return po, [x for x in po["line_items"] if not x.get("is_header")]


def _reprice_form(rows, **extra):
    data = {"line_rate": [f"{float(x.get('price') or 0):.2f}" for x in rows],
            "line_discount": ["" for _x in rows]}
    data.update(extra)
    return data


def test_make_is_edited_on_the_reprice_form_items_and_extra_parts(client, shop):
    po, rows = _po_from_boq(client, shop)
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert page.count('<input type="text" name="line_make"') == len(rows) == 2
    assert "<span>Item</span><span>Make</span>" in page
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_make=["SANT", ""], extra_desc=["Flange 150mm"],
        extra_make=["Tata"], extra_qty=["2"], extra_rate=["300"]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert "Make+updated" in r.headers["Location"]
    assert rows[0]["make"] == "SANT" and "make" not in rows[1]
    assert po["extra_lines"][0]["make"] == "Tata"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert '<td class="c-make">SANT</td>' in html and '<td class="c-make">Tata</td>' in html
    # Cleared, the key goes again.
    client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(rows, line_make=["", ""]))
    assert "make" not in rows[0]


def test_a_make_only_save_is_recorded_not_reported_as_nothing(client, shop):
    po, rows = _po_from_boq(client, shop)
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(
        rows, line_make=["SANT", ""]))
    assert "Nothing+changed" not in r.headers["Location"]
    assert "Make+updated+on+1+line" in r.headers["Location"]
    assert any("Make updated" in str(h.get("note", "")) for h in po.get("status_history") or [])
    assert not po.get("reprice_log"), "a make is not a rate and never enters the rate trail"


def test_a_stale_reprice_form_without_make_boxes_keeps_every_make(client, shop):
    po, rows = _po_from_boq(client, shop)
    rows[0]["make"] = "SANT"
    client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(rows))
    assert rows[0]["make"] == "SANT"


def test_a_make_list_of_the_wrong_length_is_refused(client, shop):
    po, rows = _po_from_boq(client, shop)
    r = client.post(f"/purchase/edit/{po['id']}", data=_reprice_form(rows, line_make=["SANT"]))
    assert r.status_code == 200
    assert "That order has changed since this form was opened" in r.get_data(as_text=True)
    assert "make" not in rows[0]


# ══ 4. From the BOQ, and nothing prefilled ═════════════════════════════════

def test_make_survives_po_from_boq(client, shop):
    li = shop["lines"][0]
    r = client.post(f"/purchase/from-boq/{shop['boq']}", data=dict(ORDER, po_json=json.dumps(
        {"lines": [{"line_id": li["line_id"], "qty": "3", "rate": "100", "make": "SANT"}]})))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    po = _only("purchases")
    line = next(x for x in po["line_items"] if not x.get("is_header"))
    assert line["make"] == "SANT" and line["line_id"] == li["line_id"]
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert '<td class="c-make">SANT</td>' in html


def test_the_from_boq_picker_opens_every_make_blank_even_with_a_make_in_the_remark(client, shop):
    li = shop["lines"][0]
    li["remark"] = "Make: Jindal"
    html = client.get(f"/purchase/from-boq/{shop['boq']}").get_data(as_text=True)
    assert f'id="m_{li["line_id"]}" value=""' in html
    assert 'value="Jindal"' not in html
    assert '<th class="pk-make" style="width:120px;">Make</th>' in html


def test_a_rejected_from_boq_keeps_the_typed_make(client, shop):
    li = shop["lines"][0]
    r = client.post(f"/purchase/from-boq/{shop['boq']}", data=dict(ORDER, date="", po_json=json.dumps(
        {"lines": [{"line_id": li["line_id"], "qty": "3", "rate": "100", "make": "SANT"}]})))
    assert r.status_code == 200
    assert f'id="m_{li["line_id"]}" value="SANT"' in r.get_data(as_text=True)


def test_no_boq_line_and_no_spec_variant_has_a_make_field_to_prefill_from(shop):
    """The premise behind "leave it blank" — checked, so it fails the day one appears."""
    for li in STORE["boqs"][shop["boq"]]["line_items"]:
        assert "make" not in li and "brand" not in li
    for spec in STORE["specs"].values():
        for v in spec.get("variants") or []:
            assert "make" not in v and "brand" not in v


# ══ 5. The draft PO — create, edit, convert ════════════════════════════════

def _draft(client, shop, make="SANT", pcs="2"):
    li = shop["lines"][0]
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-26", "vendor_id": VENDOR_ID, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "5",
                                          "pcs": pcs, "make": make}]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return _only("purchase_orders"), li


def test_make_survives_draft_po_create_and_prints(client, shop):
    d, li = _draft(client, shop)
    row = next(x for x in d["items"] if not x.get("is_header"))
    assert row["make"] == "SANT" and row["pcs"] == "2"
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert '<td class="c-make">SANT</td>' in html


def test_the_draft_po_create_form_carries_the_make_box(client, shop):
    html = client.get(f"/po/create?boq={shop['boq']}").get_data(as_text=True)
    assert '<th class="pk-make" style="width:120px;">Make</th>' in html
    assert "make: (el('m_' + lid) || {}).value || ''" in html


def test_make_is_edited_on_the_draft_po_edit_form(client, shop):
    d, li = _draft(client, shop)
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    page = client.get(f"/po/edit/{d['id']}").get_data(as_text=True)
    assert f'name="item_make_{n}"' in page and 'value="SANT"' in page
    r = client.post(f"/po/edit/{d['id']}", data={
        "date": "2026-10-26", "vendor_id": VENDOR_ID, "notes": "", "delivery_to": "",
        f"item_make_{n}": "Kirloskar"})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert d["items"][n]["make"] == "Kirloskar"
    # Cleared, the key goes.
    client.post(f"/po/edit/{d['id']}", data={
        "date": "2026-10-26", "vendor_id": VENDOR_ID, f"item_make_{n}": ""})
    assert "make" not in d["items"][n]


def test_make_survives_converting_a_draft_to_a_po(client, shop):
    d, li = _draft(client, shop)
    page = client.get(f"/purchase/from-draft/{d['id']}").get_data(as_text=True)
    assert 'name="dl_make" value="SANT"' in page, "the draft's make must open the box"
    r = client.post(f"/purchase/from-draft/{d['id']}", data=dict(
        ORDER, dl_line_id=[li["line_id"]], dl_qty=["5"], dl_rate=["100"], dl_make=["SANT"]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    po = _only("purchases")
    assert next(x for x in po["line_items"] if not x.get("is_header"))["make"] == "SANT"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert '<td class="c-make">SANT</td>' in html


def test_a_make_typed_on_conversion_beats_the_drafts(client, shop):
    d, li = _draft(client, shop)
    client.post(f"/purchase/from-draft/{d['id']}", data=dict(
        ORDER, dl_line_id=[li["line_id"]], dl_qty=["5"], dl_rate=["100"], dl_make=["Tata"]))
    po = _only("purchases")
    assert next(x for x in po["line_items"] if not x.get("is_header"))["make"] == "Tata"


def test_snapshot_editing_the_draft_later_does_not_move_the_po(client, shop):
    d, li = _draft(client, shop)
    client.post(f"/purchase/from-draft/{d['id']}", data=dict(
        ORDER, dl_line_id=[li["line_id"]], dl_qty=["5"], dl_rate=["100"], dl_make=["SANT"]))
    po = _only("purchases")
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    client.post(f"/po/edit/{d['id']}", data={
        "date": "2026-10-26", "vendor_id": VENDOR_ID, f"item_make_{n}": "Other"})
    assert next(x for x in po["line_items"] if not x.get("is_header"))["make"] == "SANT"


# ══ 6. Import from Excel ════════════════════════════════════════════════════

def _staged(kind, rows, ctx=None):
    wb = SI.from_rows([("Sheet1", "visible", rows)])
    return DI.stage(DI.KINDS[kind], wb, "sheet.xlsx", conftest.ensure_test_user()["id"],
                    ctx or {})


def _applied(client, kind, tok):
    rec = STORE["doc_imports"][tok]
    form = {f"map_{c}": t for c, t in rec["mapping"].items()}
    form.update({"action": "confirm", "sheet": str(rec["sheet_index"])})
    r = client.post(f"/import/{kind}/{tok}", data=form)
    assert r.status_code == 303, r.get_data(as_text=True)[:2000]
    return client.get(r.headers["Location"]).get_data(as_text=True), rec


@pytest.mark.parametrize("kind", ["purchase", "dpo"])
def test_both_po_imports_offer_make_in_their_column_picker(kind):
    keys = SI.schema_keys(DI.KINDS[kind].schema({"boq_id": "x"}))
    assert "make" in keys


def test_the_purchase_parts_import_guesses_the_make_column_and_prefills_it(client):
    tok = _staged("purchase", [["Part", "Make", "Qty", "Rate"],
                               ["80mm Butterfly valve", "SANT", 2, 4200]])
    html, rec = _applied(client, "purchase", tok)
    assert "make" in rec["mapping"].values(), "the Make heading was not guessed"
    assert 'name="extra_make" value="SANT"' in html


def test_the_draft_po_import_prefills_the_pickers_make(client, shop):
    b = STORE["boqs"][shop["boq"]]
    li = next(x for x in b["line_items"] if not x.get("is_header")
              and len([y for y in b["line_items"] if y.get("item_no") == x.get("item_no")]) == 1)
    tok = _staged("dpo", [["Item", "Order qty", "Make"], [li["item_no"], 6, "SANT"]],
                  {"boq_id": shop["boq"]})
    html, _rec = _applied(client, "dpo", tok)
    assert f'id="m_{li["line_id"]}" value="SANT"' in html
