"""
Named, reusable pictures on the Product Inquiry and the real purchase order —
29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, B2, from the
28 October 2026 meeting with Yogesh Bankar.

    pictures addable from the create form, optional; each picture has a NAME,
    printed under it; pictures kept in a library keyed to the item — the spec
    id where there is one, otherwise the normalised description — so the next
    document for the same item offers that picture preselected.

⚠ **THE CREATE FORM OFFERS THE LIBRARY, IT DOES NOT CARRY FILE BOXES**, and
  the reason is measured rather than stylistic: the §0 **forty-ninth** block
  recorded that nginx refuses a request over 8 MB with its own 413 page
  (DEPLOY.md) and a phone photo is 3–5 MB, so a form with several file boxes
  fails on the second picture with nothing of ours on screen — and a browser
  cannot refill a file box, so every refused save empties them all. A
  `<select>` carries no bytes. New pictures are uploaded on the document's own
  Pictures page, which is what registers one into the library. Put to Manas
  with that named; his answer is the §0 block.

⚠ Nothing here passes against a blank page: each assertion names a picture
  id, a name that only appears when the caption rendered, or a refusal.
"""

import io
import json

import pytest

PIL = pytest.importorskip("PIL")

import boqpick as BP       # noqa: E402
import lineimage as LI     # noqa: E402
import pipeline as P       # noqa: E402
import po_draft as PD      # noqa: E402
from store import STORE    # noqa: E402
from test_line_pictures import _FS, _jpeg, _saved  # noqa: E402


@pytest.fixture()
def shop(client):
    import address
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    STORE.setdefault("purchases", {}).clear()
    STORE.setdefault(LI.COLLECTION, {}).clear()
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    lines = [li for li in STORE["boqs"][bid]["line_items"]
             if not li.get("is_header")]
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    yield {"boq": bid, "lines": lines, "vendor": vendor}
    STORE["purchase_orders"].clear()
    STORE["purchases"].clear()
    STORE[LI.COLLECTION].clear()


# ═══ 1. The item key — exact, never fuzzy ══════════════════════════════════

def test_a_spec_code_match_keys_on_the_spec_id(client):
    import spec as SP
    SP.ensure_demo_specs()
    sid, s = next(iter(STORE["specs"].items()))
    code = s["code"]
    assert LI.item_key_of({"part_no": code, "description": "anything"}) == f"spec:{sid}"


def test_the_spec_match_is_exact_after_strip_and_nothing_else(client):
    import spec as SP
    SP.ensure_demo_specs()
    sid, s = next(iter(STORE["specs"].items()))
    code = s["code"]
    assert LI.item_key_of({"part_no": f"  {code}  "}) == f"spec:{sid}"
    # ⚠ `po_parts.py`'s lesson for the third time: no casefold, no prefix.
    assert LI.item_key_of({"part_no": code.lower()}) != f"spec:{sid}"
    assert LI.item_key_of({"part_no": code + "X"}) != f"spec:{sid}"


def test_without_a_spec_code_it_keys_on_the_normalised_description(client):
    a = LI.item_key_of({"part_no": "", "description": "Butterfly  Valve 150 NB"})
    b = LI.item_key_of({"part_no": "", "description": "butterfly valve 150 nb"})
    assert a == b == "desc:" + P.norm_name("Butterfly Valve 150 NB")
    assert a != LI.item_key_of({"description": "Butterfly valve 200 NB"})


def test_a_line_with_neither_is_offered_nothing(client):
    assert LI.item_key_of({}) == ""
    assert LI.item_key_of({"part_no": "", "description": "   "}) == ""
    assert LI.library_for({}) == []


def test_a_purchase_order_line_keys_on_its_name_not_a_description(client):
    """`line_items` rows carry `name`, BOQ-side rows carry `description`."""
    assert LI.item_key_of({"name": "Gate valve"}) == "desc:gate valve"


# ═══ 2. The library — a NAME over the ids the module already stores ════════

def test_register_stores_a_name_and_an_item_and_no_bytes(client):
    iid = _saved()
    rid = LI.register(iid, "  SANT  body   ", "desc:gate valve", "tester")
    assert rid
    row = STORE[LI.COLLECTION][rid]
    assert row["image"] == iid and row["item_key"] == "desc:gate valve"
    assert row["name"] == "SANT body", "whitespace collapsed, not stored raw"
    assert row["by"] == "tester" and len(row["at"]) == 16
    # ⚠ The BYTES are not here and never were.
    assert not any(isinstance(v, (bytes, bytearray)) for v in row.values())
    assert "data:image" not in json.dumps(row)


def test_register_is_idempotent_on_the_item_and_the_picture(client):
    iid = _saved()
    a = LI.register(iid, "First", "desc:x")
    b = LI.register(iid, "Renamed", "desc:x")
    assert a == b, "the same picture on the same item is ONE row"
    assert len(STORE[LI.COLLECTION]) == 1
    assert STORE[LI.COLLECTION][a]["name"] == "Renamed"


def test_the_same_picture_on_two_items_is_two_rows(client):
    iid = _saved()
    a = LI.register(iid, "Valve body", "desc:x")
    b = LI.register(iid, "Also used here", "desc:y")
    assert a != b and len(STORE[LI.COLLECTION]) == 2


def test_register_refuses_an_invented_id_or_a_keyless_item(client):
    assert LI.register("f" * 64, "n", "desc:x") == ""   # no file behind it
    assert LI.register("not-an-id", "n", "desc:x") == ""
    assert LI.register(_saved(), "n", "") == ""
    assert STORE.get(LI.COLLECTION) == {}


def test_the_name_is_capped(client):
    rid = LI.register(_saved(), "N" * 500, "desc:x")
    assert len(STORE[LI.COLLECTION][rid]["name"]) == LI.NAME_MAX


def test_library_for_lists_newest_first_and_drops_a_missing_file(client):
    a = _saved(colour=(10, 20, 30))
    b = _saved(colour=(40, 50, 60))
    LI.register(a, "Older", "desc:x")
    LI.register(b, "Newer", "desc:x")
    rows = LI.library_for({"description": "x"})
    assert [n for _i, n in rows] == ["Newer", "Older"]
    LI._path(a).unlink()
    LI._CACHE.clear()
    assert [n for _i, n in LI.library_for({"description": "x"})] == ["Newer"]


# ═══ 3. The name is SNAPSHOTTED on the line and printed under the picture ══

def test_the_name_lives_on_the_line_and_is_absent_when_blank(client):
    line = {}
    LI.name_on(line, "  Valve  body ")
    assert line[LI.NAME_KEY] == "Valve body"
    LI.name_on(line, "")
    assert LI.NAME_KEY not in line, "no empty key"


def test_the_printed_cell_carries_the_name_under_the_picture(client):
    iid = _saved()
    line = {LI.KEY: iid, LI.NAME_KEY: "SANT body"}
    cell = LI.cell(line)
    assert '<div class="c-img-n">SANT body</div>' in cell
    assert 'alt="SANT body"' in cell


def test_a_picture_with_no_name_prints_exactly_what_it_printed_before(client):
    """
    ⚠ The property that keeps every document raised before B2 still: a line
    with a picture and no name emits the cell it always emitted.
    """
    iid = _saved()
    src = LI.src_of(iid)
    assert LI.cell({LI.KEY: iid}) == f'<td class="c-img"><img src="{src}" alt=""/></td>'
    assert LI.cell({}) == '<td class="c-img"></td>'
    assert LI.EMPTY_CELL == '<td class="c-img"></td>'


def test_the_name_is_escaped_on_the_sheet(client):
    line = {LI.KEY: _saved(), LI.NAME_KEY: '<script>x</script>"'}
    cell = LI.cell(line)
    assert "<script>x</script>" not in cell
    assert "&lt;script&gt;" in cell


def test_the_caption_css_rides_only_with_the_column(client):
    assert ".c-img-n" in LI.SHEET_CSS
    import docsheet as DS
    assert ".c-img-n" not in DS.SHEET_STYLES, (
        "the caption's rule must ride with the column, not with every sheet")


def test_renaming_a_library_row_moves_no_document_already_raised(client, shop):
    """
    ⚠ §1.2. The library is what a FORM offers; the SHEET reads the line's own
    `image_name`.
    """
    iid = _saved()
    rid = LI.register(iid, "As raised", "desc:x")
    line = {"description": "x"}
    LI.apply_choice(line, iid, {"description": "x"})
    assert LI.name_of(line) == "As raised"
    STORE[LI.COLLECTION][rid]["name"] = "Renamed next month"
    assert LI.name_of(line) == "As raised", "the snapshot moved"
    assert '<div class="c-img-n">As raised</div>' in LI.cell(line)


# ═══ 4. carry() takes the name with the id ═════════════════════════════════

def test_carry_takes_the_name_and_writes_no_empty_key(client):
    iid = _saved()
    assert LI.carry({}) == {}
    assert LI.carry({LI.KEY: iid}) == {LI.KEY: iid}
    assert LI.carry({LI.KEY: iid, LI.NAME_KEY: "N"}) == {LI.KEY: iid,
                                                         LI.NAME_KEY: "N"}


# ═══ 5. apply_choice — the library decides, not the POST ═══════════════════

def test_a_choice_in_the_items_library_is_applied_with_its_name(client):
    iid = _saved()
    LI.register(iid, "Valve body", "desc:x")
    line = {"description": "x"}
    assert LI.apply_choice(line, iid, {"description": "x"}) is True
    assert LI.image_of(line) == iid and LI.name_of(line) == "Valve body"


def test_a_picture_from_ANOTHER_items_library_is_refused(client):
    """⚠ A crafted POST cannot attach an arbitrary stored picture."""
    iid = _saved()
    LI.register(iid, "Belongs to y", "desc:y")
    line = {"description": "x"}
    assert LI.apply_choice(line, iid, {"description": "x"}) is False
    assert LI.KEY not in line


def test_an_invented_id_and_a_file_that_is_not_there_are_refused(client):
    line = {"description": "x"}
    assert LI.apply_choice(line, "f" * 64, {"description": "x"}) is False
    assert LI.apply_choice(line, "nonsense", {"description": "x"}) is False
    assert LI.KEY not in line


def test_a_blank_choice_removes_the_picture_and_its_name(client):
    iid = _saved()
    LI.register(iid, "N", "desc:x")
    line = {"description": "x"}
    LI.apply_choice(line, iid, {"description": "x"})
    assert LI.apply_choice(line, "", {"description": "x"}) is True
    assert LI.KEY not in line and LI.NAME_KEY not in line


def test_a_picture_on_the_line_whose_FILE_IS_GONE_is_refused(client):
    """
    ⚠ The one case `exists()` is the only guard for. The library-membership
    check lets this id through — it is on the stored line, and `library_for()`
    has already dropped any row whose file is missing — so without the file
    check a line whose picture was deleted off disk would be re-attached and
    then render an empty cell with a caption under it.
    """
    iid = _saved()
    stored = {"description": "x", LI.KEY: iid, LI.NAME_KEY: "Was here"}
    LI._path(iid).unlink()
    LI._CACHE.clear()
    line = {"description": "x"}
    assert LI.apply_choice(line, iid, stored) is False
    assert LI.KEY not in line and LI.NAME_KEY not in line


def test_a_picture_already_on_the_line_stays_choosable(client):
    """One set before B2, or on another item — an edit must not drop it."""
    iid = _saved()
    stored = {"description": "x", LI.KEY: iid}
    line = {"description": "x"}
    assert LI.apply_choice(line, iid, stored) is True
    assert LI.image_of(line) == iid


# ═══ 6. The column appears only when a picture does ════════════════════════

def test_the_picker_draws_no_picture_column_when_the_library_is_empty(client, shop):
    """
    ⚠ The property that keeps `/po/create`'s pinned golden still, and the
    reason the print goldens did not move either.
    """
    assert LI.grid_has_offers(STORE["boqs"][shop["boq"]]["line_items"]) is False
    for url in (f"/po/create?boq={shop['boq']}",
                f"/purchase/from-boq/{shop['boq']}"):
        html = client.get(url).get_data(as_text=True)
        assert 'class="pk-img"' not in html, url
        assert ">Picture</th>" not in html, url


def test_the_picker_draws_the_column_once_the_item_has_a_picture(client, shop):
    li = shop["lines"][0]
    iid = _saved()
    LI.register(iid, "SANT body", LI.item_key_of(
        {"part_no": li.get("item_no"), "description": li.get("description")}),
        "tester")
    assert LI.grid_has_offers(STORE["boqs"][shop["boq"]]["line_items"]) is True
    for url in (f"/po/create?boq={shop['boq']}",
                f"/purchase/from-boq/{shop['boq']}"):
        html = client.get(url).get_data(as_text=True)
        assert '<th class="pk-img" style="width:150px;">Picture</th>' in html, url
        assert f'id="img_{li["line_id"]}"' in html, url
        assert f'<option value="{iid}" selected>SANT body</option>' in html, url
        # ⚠ A SELECT and never a file box.
        assert 'name="img_' in html and 'type="file"' not in html, url


def test_a_line_the_library_knows_nothing_about_gets_an_empty_cell(client, shop):
    a, b = shop["lines"][0], shop["lines"][1]
    LI.register(_saved(), "Only A", LI.item_key_of(
        {"part_no": a.get("item_no"), "description": a.get("description")}))
    html = client.get(f"/po/create?boq={shop['boq']}").get_data(as_text=True)
    assert f'id="img_{a["line_id"]}"' in html
    assert f'id="img_{b["line_id"]}"' not in html
    assert '<td class="pk-img"></td>' in html


# ═══ 7. End to end — chosen on the create form, printed, and reused ═══════

def _register_for(line, name="SANT body"):
    iid = _saved()
    LI.register(iid, name, LI.item_key_of(
        {"part_no": line.get("item_no"), "description": line.get("description")}),
        "tester")
    return iid


def test_a_picture_chosen_on_the_inquirys_create_form_is_saved_and_printed(client, shop):
    li = shop["lines"][0]
    iid = _register_for(li)
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "image": iid}]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    d = next(iter(STORE["purchase_orders"].values()))
    row = next(x for x in d["items"] if not x.get("is_header"))
    assert row[LI.KEY] == iid and row[LI.NAME_KEY] == "SANT body"
    sheet = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert '<div class="c-img-n">SANT body</div>' in sheet
    assert '<th class="c-img">Image</th>' in sheet


def test_a_picture_chosen_on_the_real_POs_from_boq_form_is_saved_and_printed(client, shop):
    li = shop["lines"][0]
    iid = _register_for(li, "Jindal body")
    r = client.post(f"/purchase/from-boq/{shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "rate": "100", "image": iid}]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    po = next(iter(STORE["purchases"].values()))
    row = next(x for x in po["line_items"] if not x.get("is_header"))
    assert row[LI.KEY] == iid and row[LI.NAME_KEY] == "Jindal body"
    sheet = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert '<div class="c-img-n">Jindal body</div>' in sheet


def test_the_next_document_for_the_same_item_offers_it_PRESELECTED(client, shop):
    """⚠ The sentence B2 is actually about."""
    li = shop["lines"][0]
    iid = _register_for(li, "SANT body")
    first = client.get(f"/po/create?boq={shop['boq']}").get_data(as_text=True)
    assert f'<option value="{iid}" selected>SANT body</option>' in first
    second = client.get(f"/purchase/from-boq/{shop['boq']}").get_data(as_text=True)
    assert f'<option value="{iid}" selected>SANT body</option>' in second


def test_a_crafted_payload_cannot_attach_another_items_picture(client, shop):
    a, b = shop["lines"][0], shop["lines"][1]
    iid = _register_for(a, "Only A's")
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": b["line_id"], "qty": "1",
                                          "image": iid}]})})
    assert r.status_code == 302
    d = next(iter(STORE["purchase_orders"].values()))
    row = next(x for x in d["items"] if not x.get("is_header"))
    assert LI.KEY not in row, "a picture from another item's library landed"


def test_the_picture_and_its_name_survive_conversion_to_a_real_PO(client, shop):
    li = shop["lines"][0]
    iid = _register_for(li, "SANT body")
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "image": iid}]})})
    d = next(iter(STORE["purchase_orders"].values()))
    form = client.get(f"/purchase/from-draft/{d['id']}").get_data(as_text=True)
    assert f'<option value="{iid}" selected>SANT body</option>' in form
    rows = [x for x in d["items"] if not x.get("is_header")]
    r = client.post(f"/purchase/from-draft/{d['id']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "dl_line_id": [x["line_id"] for x in rows],
        "dl_qty": ["1"] * len(rows), "dl_rate": ["100"] * len(rows)})
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    po = next(iter(STORE["purchases"].values()))
    row = next(x for x in po["line_items"] if not x.get("is_header"))
    assert row[LI.KEY] == iid and row[LI.NAME_KEY] == "SANT body"


def test_the_inquirys_editor_offers_the_library_and_saves_the_choice(client, shop):
    li = shop["lines"][0]
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4"}]})})
    assert r.status_code == 302
    d = next(iter(STORE["purchase_orders"].values()))
    iid = _register_for(li, "Added later")
    page = client.get(f"/po/edit/{d['id']}").get_data(as_text=True)
    assert 'name="it_image"' in page
    # ⚠ PRESELECTED, which is B2's own sentence: the item's newest library
    #   entry is what the next form opens at.
    assert f'<option value="{iid}" selected>Added later</option>' in page

    from test_po_full_edit import _rows
    body = _rows(d)
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    body["it_image"][n] = iid
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    assert d["items"][n][LI.KEY] == iid
    assert d["items"][n][LI.NAME_KEY] == "Added later"


# ═══ 8. The Pictures page is where a picture ENTERS the library ════════════

def _upload(client, url, key, fp, data, name="", fname="part.jpg"):
    return client.post(url, data={
        "action": "upload", "line": key, "fp": fp, "picture_name": name,
        "picture": (io.BytesIO(data), fname)},
        content_type="multipart/form-data")


def test_an_upload_names_the_picture_and_registers_it(client, shop):
    li = shop["lines"][0]
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4"}]})})
    d = next(iter(STORE["purchase_orders"].values()))
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    row = d["items"][n]
    page = client.get(f"/po/pictures/{d['id']}").get_data(as_text=True)
    assert 'name="picture_name"' in page, "the Pictures page has no Name box"
    r = _upload(client, f"/po/pictures/{d['id']}", f"it:{n}",
                LI.fingerprint(row.get("description")), _jpeg(), "SANT body")
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert LI.image_of(row) and LI.name_of(row) == "SANT body"
    # ⚠ And it is now in the item's library, so the NEXT document offers it.
    assert [n for _i, n in LI.library_for(row)] == ["SANT body"]
    page = client.get(f"/po/pictures/{d['id']}").get_data(as_text=True)
    assert "SANT body" in page


def test_an_upload_with_no_name_is_allowed_and_prints_no_caption(client, shop):
    li = shop["lines"][0]
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4"}]})})
    d = next(iter(STORE["purchase_orders"].values()))
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    row = d["items"][n]
    r = _upload(client, f"/po/pictures/{d['id']}", f"it:{n}",
                LI.fingerprint(row.get("description")), _jpeg(), "")
    assert r.status_code == 302
    assert LI.image_of(row) and LI.NAME_KEY not in row
    sheet = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert 'class="c-img-n"' not in sheet


def test_removing_a_picture_drops_its_name_and_keeps_the_library_row(client, shop):
    li = shop["lines"][0]
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4"}]})})
    d = next(iter(STORE["purchase_orders"].values()))
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    row = d["items"][n]
    fp = LI.fingerprint(row.get("description"))
    _upload(client, f"/po/pictures/{d['id']}", f"it:{n}", fp, _jpeg(), "SANT body")
    assert len(STORE[LI.COLLECTION]) == 1
    r = client.post(f"/po/pictures/{d['id']}",
                    data={"action": "remove", "line": f"it:{n}", "fp": fp})
    assert r.status_code == 302
    assert LI.KEY not in row and LI.NAME_KEY not in row
    assert len(STORE[LI.COLLECTION]) == 1, (
        "the library row is the ITEM's picture, not this line's")


def test_the_pictures_page_can_choose_from_the_library(client, shop):
    li = shop["lines"][0]
    iid = _register_for(li, "From the library")
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4"}]})})
    d = next(iter(STORE["purchase_orders"].values()))
    n = next(i for i, x in enumerate(d["items"]) if not x.get("is_header"))
    row = d["items"][n]
    fp = LI.fingerprint(row.get("description"))
    page = client.get(f"/po/pictures/{d['id']}").get_data(as_text=True)
    assert 'name="picture_id"' in page
    r = client.post(f"/po/pictures/{d['id']}", data={
        "action": "choose", "line": f"it:{n}", "fp": fp, "picture_id": iid})
    assert r.status_code == 302
    assert LI.image_of(row) == iid and LI.name_of(row) == "From the library"


def test_a_hostile_name_is_escaped_everywhere_it_renders(client, shop):
    li = shop["lines"][0]
    payload = '<script>alert(1)</script>"&<img src=x onerror=alert(2)>'
    iid = _register_for(li, payload)
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "image": iid}]})})
    d = next(iter(STORE["purchase_orders"].values()))
    for url in (f"/po/create?boq={shop['boq']}", f"/po/print/{d['id']}",
                f"/po/view/{d['id']}", f"/po/edit/{d['id']}",
                f"/po/pictures/{d['id']}"):
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html, url
        assert "<img src=x onerror=alert(2)>" not in html, url
        assert "&lt;script&gt;" in html, url


# ═══ 9. The storage rule is unchanged — no base64 on a record ═════════════

def test_no_record_anywhere_grows_a_base64_payload(client, shop):
    li = shop["lines"][0]
    iid = _register_for(li, "SANT body")
    client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "image": iid}]})})
    for coll in ("purchase_orders", LI.COLLECTION):
        blob = json.dumps(STORE.get(coll) or {}, default=str)
        assert "data:image" not in blob, coll
        assert len(blob) < 50_000, f"{coll} is carrying bytes"
    # The file is on disk, under the attachment root, as it has been since
    # 21 October 2026.
    assert LI._path(iid).is_file()
    assert LI._path(iid).parent.name == LI.SUBDIR


def test_the_library_is_a_persisted_collection(client):
    import db
    assert LI.COLLECTION in db.COLLECTIONS
    assert LI.COLLECTION in STORE
