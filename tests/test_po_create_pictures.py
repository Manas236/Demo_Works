"""
Pictures on the REAL purchase order at creation and on its edit form —
CLIENT_CHANGES.md §0 eighty-eighth block (23 November 2026, asked 28 Oct).

The Product Inquiry's feature, on `/purchase/create` and `/purchase/edit`:
optional; picked from the named reusable library (new pictures are uploaded
on the order's Pictures page, which registers them); the item's newest
library picture is offered preselected; the NAME prints under the picture.
A PO with no pictures prints byte-identical (the print goldens hold that);
with an empty library the forms draw no picture control at all.
"""

import pytest

PIL = pytest.importorskip("PIL")

import buypick as BYP           # noqa: E402
import lineimage as LI          # noqa: E402
from store import STORE         # noqa: E402
from test_line_pictures import _saved                      # noqa: E402
from test_po_buypick import _form, _newest_po, _seed, hidden  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _clean_library():
    STORE.setdefault(LI.COLLECTION, {}).clear()
    yield
    STORE.setdefault(LI.COLLECTION, {}).clear()


def _spec_pick():
    sid, s = next((k, v) for k, v in STORE["specs"].items() if v.get("variants"))
    value = f"spec:{sid}:0"
    ident, err = BYP.resolve(value)
    assert not err
    return value, ident


def _library(ident, name="SANT body"):
    iid = _saved()
    assert LI.register(iid, name, LI.item_key_of(
        {"part_no": ident["part_no"], "name": ident["name"]}), "test")
    return iid


def test_an_empty_library_draws_no_picture_control(client, hidden):
    _seed()
    page = client.get("/purchase/create").get_data(as_text=True)
    assert 'name="line_image"' not in page and "var PICS" not in page


def test_the_create_form_offers_the_library_and_saves_the_choice(client, hidden):
    _seed()
    value, ident = _spec_pick()
    iid = _library(ident)
    page = client.get("/purchase/create").get_data(as_text=True)
    assert 'name="line_image"' in page and "var PICS" in page
    assert iid in page and "SANT body" in page
    data = _form(lines=[(value, 2, 100)])
    data["line_image"] = [iid]
    r = client.post("/purchase/create", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    line = _newest_po()["line_items"][0]
    assert line["image"] == iid and line["image_name"] == "SANT body"
    doc = client.get(f"/purchase/view/{_newest_po()['id']}").get_data(as_text=True)
    assert '<div class="c-img-n">SANT body</div>' in doc
    assert 'class="c-img"><img src="data:image/jpeg;base64,' in doc


def test_no_choice_means_no_picture_and_a_crafted_id_is_ignored(client, hidden):
    _seed()
    value, ident = _spec_pick()
    _library(ident)
    stranger = _saved(colour=(10, 200, 10))          # a file in nobody's library
    data = _form(lines=[(value, 1, 10), (value, 1, 10)])
    data["line_image"] = ["", stranger]
    assert client.post("/purchase/create", data=data).status_code == 302
    a, b = _newest_po()["line_items"]
    assert "image" not in a and "image" not in b


def test_a_refused_create_keeps_the_picture_choice(client, hidden):
    _seed()
    value, ident = _spec_pick()
    iid = _library(ident)
    data = _form(lines=[(value, 1, 10)])
    data["line_image"] = [""]
    data["date"] = ""
    page = client.post("/purchase/create", data=data).get_data(as_text=True)
    sel = page.split('name="line_image"')[1].split("</select>")[0]
    assert f'value="{iid}">SANT body</option>' in sel, "still offered"
    assert "selected" not in sel, "the operator chose none — kept, not re-defaulted"
    data["line_image"] = [iid]
    page = client.post("/purchase/create", data=data).get_data(as_text=True)
    sel = page.split('name="line_image"')[1].split("</select>")[0]
    assert f'value="{iid}" selected' in sel


def _saved_po(client, value, image=""):
    data = _form(lines=[(value, 2, 100)])
    if image:
        data["line_image"] = [image]
    assert client.post("/purchase/create", data=data).status_code == 302
    return _newest_po()


def test_the_edit_form_offers_the_library_and_changes_or_removes_it(client, hidden):
    _seed()
    value, ident = _spec_pick()
    po = _saved_po(client, value)
    assert "image" not in po["line_items"][0]
    plain = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="line_image_0"' not in plain, "nothing to offer: unchanged row"
    iid = _library(ident)
    page = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert 'name="line_image_0"' in page
    assert f'<option value="{iid}" selected>SANT body</option>' in page, \
        "the item's library picture is offered preselected"
    form = {k: v for k, v in _edit_form(page).items()}
    form["line_image_0"] = iid
    r = client.post(f"/purchase/edit/{po['id']}", data=form)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    line = STORE["purchases"][po["id"]]["line_items"][0]
    assert line["image"] == iid and line["image_name"] == "SANT body"
    form["line_image_0"] = ""
    client.post(f"/purchase/edit/{po['id']}", data=form)
    assert "image" not in STORE["purchases"][po["id"]]["line_items"][0]


def _edit_form(page):
    """Every named input and select on the edit form, as the browser posts."""
    import re
    from werkzeug.datastructures import MultiDict
    form = page.split('<form method="POST"', 1)[1].split("</form>", 1)[0]
    out = MultiDict()
    for m in re.finditer(r'<input([^>]*)>', form):
        a = m.group(1)
        n = re.search(r'name="([^"]+)"', a)
        if not n or 'type="checkbox"' in a and "checked" not in a:
            continue
        v = re.search(r'value="([^"]*)"', a)
        out.add(n.group(1), (v.group(1) if v else "").replace("&amp;", "&"))
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', form, re.S):
        sel = re.search(r'<option value="([^"]*)"[^>]*selected', m.group(2))
        out.add(m.group(1), sel.group(1) if sel else "")
    return out
