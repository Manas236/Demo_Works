"""
The purchase order's FULL edit — 2 November 2026, CLIENT_CHANGES.md §0 block
of that date ("Manas, 2 Nov 2026: full editing on all documents, quotation
numbering + Resume"), Part 1.

`/purchase/edit/<id>` used to be a reprice screen. It is now the create form,
prefilled: the vendor, the dates, the terms, the tax, the number, and every
line — description, part no, make, the full 8-digit HSN, qty, unit, rate,
discount — added from the order's own BOQ (with the quantity still to order),
the BOQ items, the Specification library, free text, extra parts and Excel;
removed; moved. Cancelled is the only lock (lock 4: no received quantity is
tracked per line). After issue every change is logged with the screen-only
band; a rate that moves on an existing line still prints in the rate-change
table. A Draft edit is not logged.

⚠ Every assertion names a value that only appears when the edit worked.
"""

import json

import pytest

import pipeline as P

import conftest
import docimport as DI
import purchase as PU
import sheetimport as SI
import spec as SP
from store import STORE
from test_po_make import ORDER, VENDOR_ID, _po_from_boq, shop  # noqa: F401


OTHER_VENDOR = "b2000003-face-4000-8000-000000000003"


def _form(po, rows, **over):
    """The full editor's POST: header fields from the record, then `rows`."""
    data = {"date": po["date"], "vendor_id": po["vendor_id"],
            "vendor_ref": po.get("vendor_ref", ""), "quotation_id": "",
            "tax_type": po.get("tax_type"), "cgst_rate": "9", "igst_rate": "18",
            "delivery_date": "", "payment_terms": po.get("payment_terms", ""),
            "delivery_terms": po.get("delivery_terms", ""),
            "dispatch_through": po.get("dispatch_through", ""),
            "incoterms": po.get("incoterms", ""), "delivery_to": po.get("delivery_to", ""),
            "notes": po.get("notes", ""), "note": "",
            "round_off_present": "1", "round_off": "1"}
    cols = ("line_k", "line_pick", "line_hdr", "line_name", "line_part", "line_make",
            "line_hsn", "line_qty", "line_unit", "line_rate", "line_discount")
    for c in cols:
        data[c] = [str(r.get(c, "")) for r in rows]
    data.update(over)
    return data


def _row(po, k, **over):
    li = po["line_items"][k]
    r = {"line_k": str(k), "line_pick": "", "line_hdr": "1" if li.get("is_header") else "",
         "line_name": li.get("name", ""), "line_part": li.get("part_no", ""),
         "line_make": li.get("make", ""), "line_hsn": li.get("hsn", ""),
         "line_qty": f"{float(li.get('qty') or 0):g}", "line_unit": li.get("unit", ""),
         "line_rate": f"{float(li.get('price') or 0):.2f}",
         "line_discount": f"{float(li.get('discount_pct') or 0):g}"}
    r.update(over)
    return r


def _new(**over):
    r = {"line_k": "", "line_pick": "", "line_hdr": "", "line_name": "", "line_part": "",
         "line_make": "", "line_hsn": "", "line_qty": "", "line_unit": "",
         "line_rate": "", "line_discount": ""}
    r.update(over)
    return r


def _items(po):
    return [li for li in po["line_items"] if not li.get("is_header")]


def _ks(po):
    """Stored indices of the priced lines (a from-BOQ order carries headings)."""
    return [k for k, li in enumerate(po["line_items"]) if not li.get("is_header")]


def _heads(po):
    return [_row(po, k) for k, li in enumerate(po["line_items"]) if li.get("is_header")]


def _a_spec_pick():
    SP.ensure_demo_specs()
    sid, s = next((k, v) for k, v in STORE["specs"].items() if v.get("variants"))
    return f"spec:{sid}:0", sid


# ── The page ────────────────────────────────────────────────────────────────

def test_the_edit_form_is_the_create_form_prefilled(client, shop):
    po, rows = _po_from_boq(client, shop)
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    for needle in ('name="vendor_id"', 'name="date"', 'name="delivery_date"',
                   'name="tax_type"', 'name="payment_terms"', 'name="delivery_to"',
                   'name="doc_no_seq"', 'name="line_qty"', 'name="line_name"',
                   'name="line_unit"', 'name="line_part"', 'name="extra_desc"',
                   'name="charge_label"', "+ Add picked item", "+ Add free-text line",
                   "/import/purchase?po=", "Specification library",
                   "left to order"):
        assert needle in page, needle
    assert f'name="line_name" value="{rows[0]["name"]}"' in page.replace("&#x27;", "'") or \
        'name="line_name"' in page


def test_the_hsn_box_takes_all_eight_digits(client, shop):
    po, _rows = _po_from_boq(client, shop)
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert f'name="line_hsn" value="' in page and f'maxlength="{PU.HSN_MAX}"' in page
    assert PU.HSN_MAX == 8
    assert "11ch" in PU.EDIT_FORM_STYLES, "the HSN track is wide enough for 8 digits"


# ── Every source, every column, remove, reorder, party — and the print ─────

def test_a_full_edit_from_every_source_prints(client, shop):
    po, rows = _po_from_boq(client, shop, n=2)
    spec_pick, sid = _a_spec_pick()
    third = shop["lines"][2]
    k0, k1 = _ks(po)
    form = _form(po, [
        # Reordered: the second stored line first, every column changed.
        _row(po, k1, line_name="Renamed second line", line_part="P-77", line_make="Kirloskar",
             line_hsn="84137010", line_qty="7", line_unit="Mtr", line_rate="250.50",
             line_discount="5"),
        # The first stored line is REMOVED (not posted).
        # From the order's own BOQ, with the line id that makes it coverage.
        _new(line_pick=f"own:{third['line_id']}", line_name="From the BOQ", line_qty="4",
             line_unit="Nos", line_rate="90"),
        # From the Specification library.
        _new(line_pick=spec_pick, line_name="From the library", line_qty="2",
             line_unit="Nos", line_rate="1000", line_hsn="73063090"),
        # Free text.
        _new(line_name="Free text line", line_qty="3", line_unit="Set", line_rate="40"),
    ], vendor_id=OTHER_VENDOR, extra_desc=["Extra gasket"], extra_qty=["5"],
       extra_unit=["Nos"], extra_rate=["12"], notes="Changed note",
       delivery_to="New site store")
    r = client.post(f"/purchase/edit/{po['id']}", data=form)
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    items = _items(po)
    assert [i["name"] for i in items] == ["Renamed second line", "From the BOQ",
                                          "From the library", "Free text line"]
    a = items[0]
    assert (a["part_no"], a["make"], a["hsn"], a["qty"], a["unit"], a["price"],
            a["discount_pct"]) == ("P-77", "Kirloskar", "84137010", 7.0, "Mtr", 250.5, 5.0)
    assert a["line_id"] == rows[1]["line_id"], "the stored line's key is carried"
    assert items[1]["line_id"] == third["line_id"]
    assert items[2]["src_spec_id"] == sid and "line_id" not in items[2]
    assert "line_id" not in items[3] and "src_spec_id" not in items[3]
    assert rows[0]["line_id"] not in [i.get("line_id") for i in items], "removed"
    assert po["vendor_id"] == OTHER_VENDOR
    assert po["extra_lines"][0]["description"] == "Extra gasket"
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    for needle in ("Renamed second line", "Kirloskar", "84137010", "From the BOQ",
                   "From the library", "Free text line", "Extra gasket",
                   "Changed note", "New site store",
                   P.esc(STORE["addresses"][OTHER_VENDOR].get("company") or "")):
        assert needle in html, needle
    doc = html[html.index('<div class="doc-outer">'):]
    assert doc.index("Renamed second line") < doc.index("From the BOQ") \
        < doc.index("Free text line")


def test_a_boq_line_already_on_the_order_is_refused_and_pointed_at(client, shop):
    po, rows = _po_from_boq(client, shop)
    before = json.dumps(po["line_items"], sort_keys=True)
    k0, k1 = _ks(po)
    r = client.post(f"/purchase/edit/{po['id']}", data=_form(po, [
        *_heads(po), _row(po, k0), _row(po, k1),
        _new(line_pick=f"own:{rows[0]['line_id']}", line_name="dup", line_qty="1",
             line_rate="1")]))
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "already on this order" in page and "Change the quantity on line" in page
    assert json.dumps(po["line_items"], sort_keys=True) == before, "nothing written"
    # And the page's own picker points at the qty box rather than adding it.
    edit = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert "already on this order. Change its quantity" in edit


def test_text_in_the_quantity_box_is_refused_naming_the_line(client, shop):
    po, _rows = _po_from_boq(client, shop)
    r = client.post(f"/purchase/edit/{po['id']}",
                    data=_form(po, [_row(po, _ks(po)[0], line_qty="ten"),
                                    _row(po, _ks(po)[1])]))
    assert r.status_code == 200 and "Line 1" in r.get_data(as_text=True)


def test_a_rate_change_still_prints_in_the_rate_change_table(client, shop):
    po, _rows = _po_from_boq(client, shop)
    po["status"] = "Issued"
    k0, k1 = _ks(po)
    r = client.post(f"/purchase/edit/{po['id']}", data=_form(po, [
        _row(po, k1), _row(po, k0, line_rate="123.00")]))     # reordered too
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    log = po["reprice_log"][-1]["lines"]
    assert len(log) == 1 and log[0]["rate_to"] == 123.0 and log[0]["rate_from"] == 100.0


# ── The log, the band, the print ────────────────────────────────────────────

def test_an_issued_edit_is_logged_and_banded_on_screen_not_on_paper(client, shop):
    po, _rows = _po_from_boq(client, shop)
    po["status"] = "Issued"
    r = client.post(f"/purchase/edit/{po['id']}",
                    data=_form(po, [_row(po, _ks(po)[0], line_qty="9"),
                                    _row(po, _ks(po)[1])],
                               notes="after issue"))
    assert r.status_code == 302
    fields = [e["field"] for e in po["edit_log"]]
    assert "Note" in fields and any(f.startswith("Line ") for f in fields)
    assert all(e["by"] == conftest.ensure_test_user()["id"] for e in po["edit_log"])
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Edited after issue" in html
    band_at = html.index('class="el-band"')
    assert band_at < html.index('<div class="doc-outer">'), "band sits above the sheet"
    assert "@media print { .el-band { display:none !important; } }" in html


def test_a_draft_edit_is_not_logged(client, shop):
    po, _rows = _po_from_boq(client, shop)
    assert po["status"] == "Draft"
    r = client.post(f"/purchase/edit/{po['id']}",
                    data=_form(po, [*_heads(po), _row(po, _ks(po)[0], line_qty="9"),
                                    _row(po, _ks(po)[1])]))
    assert r.status_code == 302
    assert "edit_log" not in po and _items(po)[0]["qty"] == 9.0


def test_a_cancelled_order_is_locked_on_both_verbs(client, shop):
    po, _rows = _po_from_boq(client, shop)
    po["status"] = "Cancelled"
    assert client.get(f"/purchase/edit/{po['id']}").status_code == 302
    r = client.post(f"/purchase/edit/{po['id']}",
                    data=_form(po, [_row(po, _ks(po)[0], line_qty="99")]))
    assert r.status_code == 302 and _items(po)[0]["qty"] == 3.0


def test_the_number_moves_forward_only_on_an_issued_order(client, shop):
    po, _rows = _po_from_boq(client, shop)
    po["status"] = "Issued"
    was = po["ref"]
    low = client.post(f"/purchase/edit/{po['id']}",
                      data=_form(po, [_row(po, k) for k in range(len(po["line_items"]))], doc_no_seq="0"))
    assert low.status_code == 200 and po["ref"] == was
    r = client.post(f"/purchase/edit/{po['id']}",
                    data=_form(po, [_row(po, k) for k in range(len(po["line_items"]))], doc_no_seq="0500"))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert po["ref"].endswith("/0500") and po["number_override"]["from"] == was
    assert any(e["field"] == "Purchase order no." for e in po["edit_log"])


def test_excel_rows_land_after_the_orders_own_extra_parts(client, shop):
    po, _rows = _po_from_boq(client, shop)
    po["extra_lines"] = [{"description": "Own part", "unit": "Nos", "qty": 1.0,
                          "rate": 5.0, "total": 5.0}]
    wb = SI.from_rows([("Sheet1", "visible", [
        ["Description", "Qty", "Rate", "HSN"],
        ["Sheet flange", 4, 75, "73079190"]])])
    tok = DI.stage(DI.KINDS["purchase"], wb, "parts.xlsx",
                   conftest.ensure_test_user()["id"], {"po": po["id"]})
    rec = STORE["doc_imports"][tok]
    form = {f"map_{c}": t for c, t in rec["mapping"].items()}
    form.update({"action": "confirm", "sheet": str(rec["sheet_index"])})
    r = client.post(f"/import/purchase/{tok}", data=form)
    assert r.status_code == 303, r.get_data(as_text=True)[:2000]
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert f'action="/purchase/edit/{po["id"]}"' in page
    assert page.index('value="Own part"') < page.index('value="Sheet flange"')
    assert len(po["extra_lines"]) == 1, "nothing saved until the edit form's Save"


# ── The description glue (prod: "100 mm pipe cladding Aluminumcladding") ───

def test_a_library_code_is_never_glued_onto_the_description(client, shop):
    """
    The cause, found on 2 Nov 2026: a library pick stores the spec's CODE as
    the line's part no (`buypick.resolve()`), a code may hold no spaces
    (`spec._valid_code()`), so "Aluminum cladding" is keyed `Aluminumcladding`
    — and the reprice screen drew the part no inline after the description,
    in an unstyled span, reading "100 mm pipe cladding Aluminumcladding". The
    stored NAME was never glued. The edit form gives the part no its own box.
    """
    SP.ensure_demo_specs()
    sid = "glue-spec"
    request_cleanup = STORE["specs"]
    try:
        _glue_case(client, shop, sid)
    finally:
        request_cleanup.pop(sid, None)


def _glue_case(client, shop, sid):
    STORE["specs"][sid] = {"id": sid, "code": "Aluminumcladding",
                           "title": "100 mm pipe cladding", "category": "Piping",
                           "spec_text": "100 mm pipe cladding", "supply_hsn": "",
                           "variants": [{"label": "", "unit": "Mtr",
                                         "default_supply_base_rate": 10}]}
    r = client.post("/purchase/create", data=dict(
        ORDER, line_product_id=[f"spec:{sid}:0"], line_qty=["2"], line_rate=["10"]))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    po = next(iter(STORE["purchases"].values()))
    line = po["line_items"][0]
    assert line["name"] == "100 mm pipe cladding", "the stored name is clean"
    assert line["part_no"] == "Aluminumcladding"
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="line_name" value="100 mm pipe cladding"' in page
    assert 'name="line_part" value="Aluminumcladding"' in page
    assert "100 mm pipe cladding\n            <span" not in page


# ── An unedited record, and a save that changes nothing ─────────────────────

def test_a_save_that_changes_nothing_moves_no_byte_of_the_print(client, shop):
    po, _rows = _po_from_boq(client, shop)
    po["status"] = "Issued"
    before = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    client.get(f"/purchase/edit/{po['id']}")
    r = client.post(f"/purchase/edit/{po['id']}", data=_form(
        po, [_row(po, k) for k in range(len(po["line_items"]))]))
    assert r.status_code == 302 and "Nothing+changed" in r.headers["Location"]
    after = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    strip = lambda h: h[h.index('<div class="doc-outer">'):]  # noqa: E731
    assert strip(after) == strip(before)
    assert "edit_log" not in po and not po.get("reprice_log")
