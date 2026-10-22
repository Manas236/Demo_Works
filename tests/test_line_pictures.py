"""
tests/test_line_pictures.py — a picture beside the description (21 October 2026)
================================================================================

CLIENT_CHANGES.md §0, forty-second block. The client asked for a picture beside
each line's description on the proforma invoice and the purchase order; Manas
answered four questions before any of it was written:

1. **library default + per-line override** — a picture set once on a
   spec-library clause lands on a PI line written from it; any PI, PO or
   draft-PO line can have its own uploaded, replaced or removed;
2. **the real PO and the draft PO** both;
3. **a separate Image column**, after Part No;
4. commercial status **left unstated**.

What this file holds, section by section:

1. `lineimage.py` itself — the re-encode, the content address, the refusals,
   and that nothing but a JPEG it wrote can reach an `<img src>`.
2. The library default — the clause's picture, and the PI that takes it.
3. The printed sheets — the column appears only with a picture, and a
   document without one is untouched (the goldens hold the byte identity).
4. The Pictures pages — one line per request, the fingerprint, the gates.
5. The picture survives the routes that rebuild lines: a reprice, a draft
   converted to an order.
6. The roles — a control nobody can use is not drawn, and the URL still
   refuses.
"""

import io
import re

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

import approval  # noqa: E402
import auth  # noqa: E402
import lineimage as LI  # noqa: E402
import photo  # noqa: E402
from store import STORE  # noqa: E402


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _jpeg(w=800, h=600, colour=(200, 30, 30), gps=False) -> bytes:
    img = Image.new("RGB", (w, h), colour)
    buf = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"
        exif.get_ifd(0x8825)[1] = "N"
        img.save(buf, "JPEG", exif=exif.tobytes())
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def _png(w=300, h=300) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (0, 120, 200, 0)).save(buf, "PNG")
    return buf.getvalue()


class _FS:
    """The slice of Werkzeug's FileStorage `photo.load()` reads."""

    def __init__(self, data: bytes, filename="part.jpg"):
        self.stream = io.BytesIO(data)
        self.filename = filename


def _saved(colour=(200, 30, 30), w=800, h=600) -> str:
    image_id, err = LI.save(_FS(_jpeg(w, h, colour)))
    assert not err, err
    return image_id


def _upload(client, url, line, fp, data, name="part.jpg"):
    return client.post(url, data={"action": "upload", "line": line, "fp": fp,
                                  "picture": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def _user(name, role_ids):
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name.title(), f"pw-{name}-12345", role_ids,
                            created_by="pictures-test")


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


SPEC_ID = "spec-pic-1"
SPEC_CODE = "PIC-VALVE-150"
Q_ID = "q-pic-1"
PO_ID = "po-pic-1"
DPO_ID = "dpo-pic-1"


def _spec(image=""):
    s = {"id": SPEC_ID, "code": SPEC_CODE, "title": "Butterfly valve",
         "spec_text": "Butterfly valve, PN16, wafer pattern.", "category": "Valves",
         "supply_hsn": "84818090", "install_sac": "995461",
         "supply_gst_rate": 18.0, "install_gst_rate": 18.0,
         "variants": [{"label": "150 mm", "dimension": "150", "dim_unit": "mm",
                       "unit": "Nos", "default_supply_base_rate": 14000.0,
                       "default_install_base_rate": 900.0}]}
    if image:
        s["image"] = image
    STORE["specs"][SPEC_ID] = s
    return s


def _quotation():
    q = {"id": Q_ID, "ref": "QT-0901", "date": "2026-10-20",
         "account_name": "Prudent Teqtis Pvt Ltd", "to": "Prudent Teqtis Pvt Ltd\nBangalore",
         "line_items": [
             {"type": "item", "name": "Supply of Butterfly valve — 150 mm",
              "part_no": SPEC_CODE, "hsn": "84818090", "qty": 4.0, "unit": "Nos",
              "price": 14000.0, "total": 56000.0, "depth": 0},
             {"type": "item", "name": "Pressure gauge <b>0-20</b>",
              "part_no": "NOT-IN-LIBRARY", "hsn": "90262000", "qty": 2.0,
              "unit": "Nos", "price": 1500.0, "total": 3000.0, "depth": 0},
         ],
         "subtotal": 59000.0, "tax_type": "cgst_sgst",
         "tax_info": {"CGST": 5310.0, "SGST": 5310.0, "total": 10620.0,
                      "cgst_rate": 9.0, "sgst_rate": 9.0},
         "grand_total": 69620.0, "total_qty": 6.0}
    STORE["quotations"][Q_ID] = q
    return q


def _raise_pi(client) -> dict:
    r = client.post(f"/proforma/from/{Q_ID}",
                    data={"date": "2026-10-21", "advance_pct": "100"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    pid = r.headers["Location"].split("/proforma/view/")[1].split("?")[0]
    return STORE["proformas"][pid]


def _po(status="Issued", **extra):
    po = {"id": PO_ID, "ref": "SF/PO/26-27/0901", "fy": "26-27", "date": "2026-10-20",
          "vendor_id": "", "vendor_name": "Valve House", "to": "Valve House\nPune",
          "line_items": [
              {"type": "item", "is_header": True, "line_id": "hdr000000001",
               "name": "Valves — clause", "part_no": "24", "hsn": "", "qty": 0.0,
               "unit": "", "price": 0.0, "total": 0.0, "depth": 0},
              {"type": "item", "is_header": False, "line_id": "abc000000001",
               "name": "Butterfly valve 150 mm", "part_no": "24.a", "hsn": "84818090",
               "qty": 4.0, "unit": "Nos", "price": 14000.0, "total": 56000.0,
               "depth": 0},
          ],
          "extra_lines": [
              {"type": "extra", "description": "150mm flange", "hsn": "", "unit": "Nos",
               "qty": 8.0, "rate": 1350.0, "discount_pct": 0.0, "total": 10800.0,
               "rate_is_assumed": False},
          ],
          "charges": [], "subtotal": 66800.0, "taxable_value": 66800.0,
          "tax_type": "cgst_sgst",
          "tax_info": {"CGST": 6012.0, "SGST": 6012.0, "total": 12024.0,
                       "cgst_rate": 9.0, "sgst_rate": 9.0},
          "grand_total": 78824.0, "total_qty": 12.0, "status": status,
          "status_history": []}
    po.update(extra)
    STORE["purchases"][PO_ID] = po
    return po


def _dpo():
    d = {"id": DPO_ID, "ref": "SF/DPO/0901", "date": "2026-10-20", "boq_id": "",
         "boq_ref": "SF/BOQ/26-27/0001", "vendor_id": "", "vendor_name": "Valve House",
         "to": "Valve House\nPune",
         "items": [
             {"line_id": "hdr000000001", "is_header": True, "item_no": "24",
              "description": "Valves — clause", "unit": "", "qty": 0.0},
             {"line_id": "abc000000001", "is_header": False, "item_no": "24.a",
              "description": "Butterfly valve 150 mm", "unit": "Nos", "qty": 4.0,
              "pcs": ""},
         ]}
    STORE.setdefault("purchase_orders", {})[DPO_ID] = d
    return d


def _items_block(html: str) -> str:
    i = html.find('<div class="items-wrap">')
    return html[i:html.find("</table>", i)]


# ═════════════════════════════════════════════════════════════════════════════
# 1. lineimage.py
# ═════════════════════════════════════════════════════════════════════════════

def test_a_picture_is_re_encoded_shrunk_and_not_cropped():
    image_id = _saved(w=1600, h=400)
    data = (LI.root() / f"{image_id}.jpg").read_bytes()
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG"
    assert max(img.size) == LI.MAX_SIDE
    # 4:1 in, 4:1 out — a part is never cut to a square the way a face is.
    assert img.size == (LI.MAX_SIDE, LI.MAX_SIDE // 4)


def test_the_store_is_content_addressed_and_lives_under_the_attachment_root():
    import attachment
    a = _saved(colour=(10, 20, 30))
    b = _saved(colour=(10, 20, 30))
    assert a == b, "the same upload twice must be one file under one id"
    files = list(LI.root().glob("*.jpg"))
    assert len(files) == 1
    # Under attachment.root(), so tools/backup_db.py's walk already takes it.
    assert attachment.root() in files[0].parents


def test_no_metadata_survives():
    image_id, err = LI.save(_FS(_jpeg(gps=True)))
    assert not err
    img = Image.open(io.BytesIO((LI.root() / f"{image_id}.jpg").read_bytes()))
    assert not img.getexif(), "EXIF (and GPS with it) must not survive the re-encode"


def test_a_transparent_png_becomes_a_jpeg_on_white():
    image_id, err = LI.save(_FS(_png(), "part.png"))
    assert not err
    assert LI.src_of(image_id).startswith(LI.PREFIX)


@pytest.mark.parametrize("data, needle", [
    (b"MZ" + bytes(200), "not a JPEG, PNG or WebP image"),
    (_jpeg()[:200], "could not be read"),
    (b"", "No picture was chosen."),
])
def test_bad_uploads_are_refused_in_the_word_picture(data, needle):
    fs = _FS(data, "part.jpg" if data else "")
    image_id, err = LI.save(fs)
    assert image_id == ""
    assert needle in err
    written = list(LI.root().glob("*.jpg")) if LI.root().is_dir() else []
    assert not written, "a refused upload writes nothing"


def test_an_oversize_picture_is_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(photo, "MAX_BYTES", 1000)
    image_id, err = LI.save(_FS(_jpeg()))
    assert image_id == "" and "That picture is" in err and "the limit is" in err


def test_the_profile_photo_still_says_photo():
    """`photo.load()` is shared now; the profile photo's words did not move."""
    _uri, err = photo.encode(_FS(b"", ""))
    assert err == "No photo was chosen."


@pytest.mark.parametrize("bad", ["", "../../app", "A" * 64, "g" * 64, None, 42])
def test_src_of_refuses_anything_that_is_not_a_minted_id(bad):
    assert LI.src_of(bad) == ""


def test_src_of_refuses_a_missing_or_tampered_file():
    image_id = _saved()
    path = LI.root() / f"{image_id}.jpg"
    LI._CACHE.clear()
    path.write_bytes(_jpeg(colour=(1, 2, 3)))     # a real JPEG, but not THIS one
    assert LI.src_of(image_id) == "", "a file whose bytes no longer hash to its name"
    path.unlink()
    LI._CACHE.clear()
    assert LI.src_of(image_id) == ""
    assert not LI.exists(image_id)


# ═════════════════════════════════════════════════════════════════════════════
# 2. The library default
# ═════════════════════════════════════════════════════════════════════════════

def test_a_clause_takes_a_picture_and_gives_it_back(client):
    _spec()
    r = client.post(f"/spec/picture/{SPEC_ID}",
                    data={"action": "upload", "picture": (io.BytesIO(_jpeg()), "v.jpg")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    iid = LI.image_of(STORE["specs"][SPEC_ID])
    assert iid and LI.exists(iid)
    page = client.get(f"/spec/view/{SPEC_ID}?msg=Picture+saved&type=success").get_data(as_text=True)
    assert LI.src_of(iid) in page
    assert "Picture saved" in page, "the view page shows the message it is sent"

    client.post(f"/spec/picture/{SPEC_ID}", data={"action": "remove"})
    assert "image" not in STORE["specs"][SPEC_ID]


def test_a_refused_clause_upload_says_why_on_the_page(client):
    _spec()
    r = client.post(f"/spec/picture/{SPEC_ID}",
                    data={"action": "upload", "picture": (io.BytesIO(b"MZ" + bytes(99)), "x.jpg")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"not a JPEG, PNG or WebP image" in r.data
    assert "image" not in STORE["specs"][SPEC_ID]


def test_editing_the_clause_keeps_its_picture(client):
    s = _spec(image=_saved())
    keep = s["image"]
    form = {"code": SPEC_CODE, "title": "Butterfly valve (edited)",
            "spec_text": s["spec_text"], "category": "Valves",
            "supply_hsn": "84818090", "install_sac": "995461",
            "supply_gst_rate": "18", "install_gst_rate": "18",
            "var_label": "150 mm", "var_dimension": "150", "var_dim_unit": "mm",
            "var_unit": "Nos", "var_supply": "14000", "var_install": "900"}
    r = client.post(f"/spec/edit/{SPEC_ID}", data=form)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    assert STORE["specs"][SPEC_ID]["title"] == "Butterfly valve (edited)"
    assert STORE["specs"][SPEC_ID]["image"] == keep


def test_a_pi_line_takes_the_library_picture_by_exact_code(client):
    _spec(image=_saved())
    q = _quotation()
    pi = _raise_pi(client)
    assert LI.image_of(pi["line_items"][0]) == STORE["specs"][SPEC_ID]["image"]
    assert "image" not in pi["line_items"][1], "no clause, no picture — no empty key"
    # Onto the PI's copy, never back onto the quotation.
    assert all("image" not in r for r in q["line_items"])


def test_the_library_never_overrides_a_picture_a_line_already_carries(client):
    _spec(image=_saved(colour=(1, 1, 1)))
    q = _quotation()
    own = _saved(colour=(250, 250, 0))
    q["line_items"][0]["image"] = own
    pi = _raise_pi(client)
    assert pi["line_items"][0]["image"] == own


def test_a_code_that_only_resembles_the_clause_gets_nothing():
    _spec(image=_saved())
    for near in (SPEC_CODE.lower(), SPEC_CODE + "-X", " " + SPEC_CODE[:-1]):
        assert LI.library_image_for(near) == ""
    assert LI.library_image_for(" " + SPEC_CODE + " ")   # strip() and nothing else


def test_the_convert_form_previews_which_lines_will_carry_a_picture(client):
    _spec(image=_saved())
    _quotation()
    page = client.get(f"/proforma/from/{Q_ID}").get_data(as_text=True)
    assert "1 line will carry the specification library" in page
    assert "<th>Picture</th>" in page


# ═════════════════════════════════════════════════════════════════════════════
# 3. The printed sheets
# ═════════════════════════════════════════════════════════════════════════════

def test_the_pi_prints_an_image_column_only_when_a_line_has_a_picture(client):
    _quotation()
    pi = _raise_pi(client)
    bare = client.get(f"/proforma/view/{pi['id']}").get_data(as_text=True)
    assert "c-img" not in bare and LI.SHEET_CSS not in bare

    pi["line_items"][0]["image"] = _saved()
    html = client.get(f"/proforma/view/{pi['id']}").get_data(as_text=True)
    items = _items_block(html)
    assert '<th class="c-img">Image</th>' in items
    # The column sits between Part No and the description.
    assert items.index('class="c-partno"') < items.index('class="c-img"') < items.index('class="c-desc"')
    assert items.count('<img src="data:image/jpeg;base64,') == 1
    assert items.count('<td class="c-img"></td>') == 1, "the line with none gets an empty cell"
    assert 'colspan="4"' not in items, "every summary label spans the Image column too"
    assert LI.SHEET_CSS in html


def test_the_po_prints_the_column_for_an_item_and_an_extra_part(client):
    po = _po()
    bare = client.get(f"/purchase/view/{PO_ID}").get_data(as_text=True)
    assert "c-img" not in bare

    po["extra_lines"][0]["image"] = _saved()
    items = _items_block(client.get(f"/purchase/view/{PO_ID}").get_data(as_text=True))
    assert '<th class="c-img">Image</th>' in items
    assert items.count('<img src="data:image/jpeg;base64,') == 1
    # The header row and the item row each carry an empty Image cell, the
    # description span of the header is unchanged, every summary label is 5.
    assert items.count('<td class="c-img"></td>') == 2
    assert 'colspan="7" class="c-desc"' in items
    assert 'colspan="4"' not in items and 'colspan="5"' in items


def test_the_draft_po_prints_the_column_on_view_and_on_print(client):
    d = _dpo()
    assert "c-img" not in client.get(f"/po/print/{DPO_ID}").get_data(as_text=True)
    d["items"][1]["image"] = _saved()
    for url in (f"/po/print/{DPO_ID}", f"/po/view/{DPO_ID}"):
        html = client.get(url).get_data(as_text=True)
        items = _items_block(html)
        assert '<th class="c-img">Image</th>' in items
        assert items.count('<img src="data:image/jpeg;base64,') == 1
        assert 'colspan="6" class="c-desc"' in items
        assert LI.SHEET_CSS in html


def test_a_missing_picture_file_prints_no_column_and_no_error(client):
    d = _dpo()
    d["items"][1]["image"] = "0" * 64
    r = client.get(f"/po/print/{DPO_ID}")
    assert r.status_code == 200 and "c-img" not in r.get_data(as_text=True)


# ═════════════════════════════════════════════════════════════════════════════
# 4. The Pictures pages
# ═════════════════════════════════════════════════════════════════════════════

def test_the_pi_pictures_page_uploads_onto_one_line_only(client):
    _quotation()
    pi = _raise_pi(client)
    page = client.get(f"/proforma/pictures/{pi['id']}").get_data(as_text=True)
    # Escaped where the description reaches the page.
    assert "Pressure gauge &lt;b&gt;0-20&lt;/b&gt;" in page
    fp = LI.fingerprint(pi["line_items"][1]["name"])
    r = _upload(client, f"/proforma/pictures/{pi['id']}", "li:1", fp, _jpeg())
    assert r.status_code == 302 and "Picture+saved+on+line+2" in r.headers["Location"]
    assert LI.image_of(pi["line_items"][1])
    assert "image" not in pi["line_items"][0]
    # The figures did not move.
    assert pi["line_items"][1]["total"] == 3000.0 and pi["grand_total"] == 69620.0


def test_a_stale_page_is_refused_rather_than_landing_on_another_line(client):
    _quotation()
    pi = _raise_pi(client)
    stale = LI.fingerprint("a line that used to be here")
    r = _upload(client, f"/proforma/pictures/{pi['id']}", "li:0", stale, _jpeg())
    assert "type=error" in r.headers["Location"]
    assert not any(LI.image_of(l) for l in pi["line_items"])
    r = _upload(client, f"/proforma/pictures/{pi['id']}", "li:9",
                LI.fingerprint("x"), _jpeg())
    assert "type=error" in r.headers["Location"]


def test_remove_takes_the_picture_off_and_says_so_when_there_is_none(client):
    _quotation()
    pi = _raise_pi(client)
    fp = LI.fingerprint(pi["line_items"][0]["name"])
    r = client.post(f"/proforma/pictures/{pi['id']}",
                    data={"action": "remove", "line": "li:0", "fp": fp})
    assert "has+no+picture+to+remove" in r.headers["Location"]
    pi["line_items"][0]["image"] = _saved()
    client.post(f"/proforma/pictures/{pi['id']}",
                data={"action": "remove", "line": "li:0", "fp": fp})
    assert "image" not in pi["line_items"][0]


def test_the_library_button_fills_blanks_only_and_is_drawn_only_when_it_would(client):
    _quotation()
    pi = _raise_pi(client)                       # raised BEFORE the clause had one
    _spec()
    url = f"/proforma/pictures/{pi['id']}"
    assert "library&rsquo;s picture" not in client.get(url).get_data(as_text=True)
    STORE["specs"][SPEC_ID]["image"] = _saved()
    assert "on 1 line with none" in client.get(url).get_data(as_text=True)
    client.post(url, data={"action": "library"})
    assert pi["line_items"][0]["image"] == STORE["specs"][SPEC_ID]["image"]
    assert "image" not in pi["line_items"][1]


def test_the_po_pictures_page_covers_items_and_extra_parts_and_logs(client):
    po = _po()
    url = f"/purchase/pictures/{PO_ID}"
    page = client.get(url).get_data(as_text=True)
    assert 'value="li:1"' in page and 'value="xl:0"' in page
    assert 'value="li:0"' not in page, "a specification header carries no picture"
    _upload(client, url, "xl:0", LI.fingerprint("150mm flange"), _jpeg())
    assert LI.image_of(po["extra_lines"][0])
    assert po["status_history"][-1]["note"] == "Picture saved on line 2."


def test_the_draft_po_pictures_page(client):
    d = _dpo()
    url = f"/po/pictures/{DPO_ID}"
    _upload(client, url, "it:1", LI.fingerprint("Butterfly valve 150 mm"), _jpeg())
    assert LI.image_of(d["items"][1])
    assert "image" not in d["items"][0]


def test_every_view_page_offers_its_pictures_page(client):
    _quotation()
    pi = _raise_pi(client)
    _po()
    _dpo()
    for view, target in ((f"/proforma/view/{pi['id']}", f"/proforma/pictures/{pi['id']}"),
                         (f"/purchase/view/{PO_ID}", f"/purchase/pictures/{PO_ID}"),
                         (f"/po/view/{DPO_ID}", f"/po/pictures/{DPO_ID}")):
        assert f'href="{target}"' in client.get(view).get_data(as_text=True), view


# ═════════════════════════════════════════════════════════════════════════════
# 5. The routes that rebuild lines keep the picture
# ═════════════════════════════════════════════════════════════════════════════

def test_a_reprice_keeps_an_extra_parts_picture_on_its_own_row(client):
    po = _po()
    po["extra_lines"].insert(0, {"type": "extra", "description": "16 sq mm wire",
                                 "hsn": "", "unit": "Mtrs", "qty": 10.0, "rate": 175.0,
                                 "discount_pct": 0.0, "total": 1750.0,
                                 "rate_is_assumed": False})
    pic = _saved()
    po["extra_lines"][1]["image"] = pic           # the flange, second row
    form = client.get(f"/purchase/edit/{PO_ID}").get_data(as_text=True)
    assert form.count('name="extra_image"') >= 3, "every row carries the box, and the template"
    assert f'name="extra_image" value="{pic}"' in form

    # What the form posts: the wire row removed, the flange now FIRST.
    r = client.post(f"/purchase/edit/{PO_ID}", data={
        "line_rate": ["14000"], "line_discount": [""],
        "extra_desc": ["150mm flange", ""], "extra_unit": ["Nos", ""],
        "extra_qty": ["8", ""], "extra_rate": ["1400", ""],
        "extra_discount": ["", ""], "extra_hsn": ["", ""],
        "extra_image": [pic, ""]})
    assert r.status_code == 302
    assert len(po["extra_lines"]) == 1
    assert po["extra_lines"][0]["description"] == "150mm flange"
    assert po["extra_lines"][0]["image"] == pic


def test_a_posted_picture_id_the_store_does_not_hold_is_dropped(client):
    po = _po()
    client.post(f"/purchase/edit/{PO_ID}", data={
        "line_rate": ["14000"], "line_discount": [""],
        "extra_desc": ["150mm flange"], "extra_unit": ["Nos"], "extra_qty": ["8"],
        "extra_rate": ["1350"], "extra_discount": [""], "extra_hsn": [""],
        "extra_image": ["a" * 64]})
    assert "image" not in po["extra_lines"][0]


def test_an_extra_line_with_no_picture_carries_no_key():
    import purchase
    from werkzeug.datastructures import MultiDict
    lines, err = purchase._parse_extra_lines(MultiDict([
        ("extra_desc", "150mm flange"), ("extra_unit", "Nos"), ("extra_qty", "1"),
        ("extra_rate", "10"), ("extra_discount", ""), ("extra_hsn", ""),
        ("extra_image", "")]))
    assert not err and "image" not in lines[0]


def test_converting_a_draft_takes_each_lines_picture_across(client):
    d = _dpo()
    pic = _saved()
    d["items"][1]["image"] = pic
    vid = "addr-pic-vendor"
    STORE["addresses"][vid] = {"id": vid, "label": "Valve House", "type": "vendor",
                               "company": "Valve House", "city": "Pune",
                               "state": "Maharashtra", "country": "India"}
    r = client.post(f"/purchase/from-draft/{DPO_ID}", data={
        "date": "2026-10-21", "vendor_id": vid, "status": "Draft",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "18",
        "dl_line_id": ["abc000000001"], "dl_qty": ["4"], "dl_rate": ["14000"]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    new = [p for p in STORE["purchases"].values() if p.get("draft_id") == DPO_ID]
    assert len(new) == 1
    body = [l for l in new[0]["line_items"] if not l.get("is_header")]
    assert body[0]["image"] == pic
    assert all("image" not in l for l in new[0]["line_items"] if l.get("is_header"))


# ═════════════════════════════════════════════════════════════════════════════
# 6. Gates and roles
# ═════════════════════════════════════════════════════════════════════════════

def test_a_cancelled_po_refuses_pictures_and_draws_no_button(client):
    _po(status="Cancelled")
    assert "/purchase/pictures/" not in client.get(f"/purchase/view/{PO_ID}").get_data(as_text=True)
    for r in (client.get(f"/purchase/pictures/{PO_ID}"),
              _upload(client, f"/purchase/pictures/{PO_ID}", "li:1",
                      LI.fingerprint("Butterfly valve 150 mm"), _jpeg())):
        assert r.status_code == 302 and "/purchase/view/" in r.headers["Location"]
    assert not LI.image_of(STORE["purchases"][PO_ID]["line_items"][1])


def test_an_approved_po_refuses_pictures_while_the_ladder_is_on(client, ladder_on):
    _po(approval_status="approved", approved_at="2026-10-20 10:00")
    allowed, why = __import__("purchase").pictures_allowed(STORE["purchases"][PO_ID])
    assert not allowed and "approved" in why
    assert "/purchase/pictures/" not in client.get(f"/purchase/view/{PO_ID}").get_data(as_text=True)
    r = _upload(client, f"/purchase/pictures/{PO_ID}", "li:1",
                LI.fingerprint("Butterfly valve 150 mm"), _jpeg())
    assert "/purchase/view/" in r.headers["Location"]
    assert approval.ladder_on()


def test_a_role_without_the_permission_sees_no_control_and_is_refused(client):
    """Accountant: views PIs and POs, raises neither."""
    _quotation()
    pi = _raise_pi(client)
    _po()
    _spec()
    acct = _user("pic-accountant", ["role-accountant"])
    _as(client, acct)
    assert "/proforma/pictures/" not in client.get(f"/proforma/view/{pi['id']}").get_data(as_text=True)
    assert "/purchase/pictures/" not in client.get(f"/purchase/view/{PO_ID}").get_data(as_text=True)
    for url in (f"/proforma/pictures/{pi['id']}", f"/purchase/pictures/{PO_ID}"):
        assert client.get(url).status_code in (302, 403)
        r = _upload(client, url, "li:0", "x", _jpeg())
        assert r.status_code in (302, 403)
    assert not any(LI.image_of(l) for l in pi["line_items"])


def test_a_role_that_reads_the_library_sees_the_picture_but_no_upload(client):
    _spec(image=_saved())
    sm = _user("pic-sales", ["role-sales-manager"])
    _as(client, sm)
    page = client.get(f"/spec/view/{SPEC_ID}").get_data(as_text=True)
    assert LI.src_of(STORE["specs"][SPEC_ID]["image"]) in page
    assert "/spec/picture/" not in page
    r = client.post(f"/spec/picture/{SPEC_ID}", data={"action": "remove"})
    assert r.status_code in (302, 403)
    assert LI.image_of(STORE["specs"][SPEC_ID])


def test_no_permission_was_minted_for_pictures():
    for ep, perm in (("proforma.pictures", "proforma.create"),
                     ("purchase.pictures", "purchase.create"),
                     ("po_draft.pictures", "po.edit"),
                     ("spec.picture", "spec.edit")):
        assert auth.ROUTE_PERMISSIONS[ep] == perm
    assert not [p for p in auth.PERMISSIONS if "picture" in p or "image" in p]


def test_the_pictures_page_draws_one_form_per_line_never_one_for_all(client):
    """nginx refuses a request over 8 MB with its own page — one file per POST."""
    _po()
    page = client.get(f"/purchase/pictures/{PO_ID}").get_data(as_text=True)
    forms = re.findall(r'<form[^>]*enctype="multipart/form-data"[^>]*>(.*?)</form>', page, re.S)
    assert len(forms) == 2
    assert all(f.count('type="file"') == 1 for f in forms)
