"""
Profile photos (26 September 2026) — photo.py, /account and /users/edit.

The rules under test:

* every user sets or clears their OWN photo at /account;
* an **Owner** sets or clears ANYONE's from /users/edit/<id>;
* a **Director** reaches /users/edit through admin.users but can neither see
  nor use the photo form there — refused on POST, not merely hidden;
* what is stored is always a fresh 192 px JPEG written by Pillow: no EXIF
  (GPS) survives, only JPEG/PNG/WebP by leading bytes, 5 MB cap, bombs refused;
* the chip shows the photo when there is one and is BYTE-IDENTICAL to the old
  initials chip when there is not (a page golden depends on that);
* nothing but a well-formed base64 JPEG data URI ever reaches an `<img src>`,
  even from a record edited directly in the database.

Every refusal is paired with a control on the same route that must succeed.
"""

import base64
import io

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

import auth  # noqa: E402
import photo  # noqa: E402
from store import STORE  # noqa: E402


# ── Files ──────────────────────────────────────────────────────────────────

def _jpeg(w=800, h=600, colour=(200, 30, 30), gps=False) -> bytes:
    img = Image.new("RGB", (w, h), colour)
    buf = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"                      # Make
        gps_ifd = exif.get_ifd(0x8825)                  # GPSInfo
        gps_ifd[1] = "N"
        gps_ifd[2] = (19.0, 2.0, 3.0)                    # latitude
        img.save(buf, "JPEG", exif=exif.tobytes())
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def _png(w=300, h=300, alpha=False) -> bytes:
    img = Image.new("RGBA" if alpha else "RGB", (w, h),
                    (0, 120, 200, 0) if alpha else (0, 120, 200))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _webp() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (240, 320), (10, 200, 10)).save(buf, "WEBP")
    return buf.getvalue()


def _post_photo(client, url, data: bytes, name="me.jpg"):
    return client.post(url, data={"action": "photo_upload",
                                  "photo": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def _decoded(user) -> Image.Image:
    raw = base64.b64decode(user["photo"][len(photo.PREFIX):])
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


# ── People ─────────────────────────────────────────────────────────────────

def _user(name, role_ids):
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name.replace("-", " ").title(), f"pw-{name}-12345", role_ids,
                            created_by="photo-test")


def _as(client, user):
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = user["id"]


@pytest.fixture()
def owner(client):
    auth.ensure_builtin_roles()
    o = _user("photo-owner", ["role-owner"])
    _as(client, o)
    yield o
    STORE["users"].pop(o["id"], None)


@pytest.fixture()
def director(client):
    auth.ensure_builtin_roles()
    d = _user("photo-director", ["role-director"])
    assert not auth.is_owner(d) and auth.ADMIN_PERM in auth.permissions_of(d)
    yield d
    STORE["users"].pop(d["id"], None)


@pytest.fixture()
def staff(client):
    auth.ensure_builtin_roles()
    s = _user("photo-staff", ["role-accountant"])
    yield s
    STORE["users"].pop(s["id"], None)


# ══ 1. Own photo at /account ═══════════════════════════════════════════════

def test_a_user_uploads_their_own_photo(client, staff):
    _as(client, staff)
    r = _post_photo(client, "/account", _jpeg())
    assert r.status_code == 200
    assert b"The photo has been updated." in r.data
    assert photo.src_of(staff).startswith(photo.PREFIX)
    img = _decoded(staff)
    assert img.format == "JPEG" and img.size == (photo.SIDE, photo.SIDE)
    assert staff["photo_updated_by"] == staff["id"]


def test_png_with_transparency_and_webp_are_accepted_and_become_jpeg(client, staff):
    _as(client, staff)
    _post_photo(client, "/account", _png(alpha=True), "a.png")
    assert _decoded(staff).format == "JPEG"
    # transparent pixels are flattened onto white, not black
    assert _decoded(staff).getpixel((96, 96))[0] > 240
    _post_photo(client, "/account", _webp(), "a.webp")
    assert _decoded(staff).size == (photo.SIDE, photo.SIDE)


def test_gps_metadata_does_not_survive(client, staff):
    src = _jpeg(gps=True)
    assert Image.open(io.BytesIO(src)).getexif(), "fixture must carry EXIF"
    _as(client, staff)
    _post_photo(client, "/account", src)
    stored = base64.b64decode(staff["photo"][len(photo.PREFIX):])
    assert not Image.open(io.BytesIO(stored)).getexif()
    assert b"Exif" not in stored and b"PhoneMaker" not in stored


def test_the_stored_photo_is_small(client, staff):
    _as(client, staff)
    _post_photo(client, "/account", _jpeg(4000, 3000))
    assert len(staff["photo"]) < 30_000


def test_a_user_removes_their_own_photo(client, staff):
    _as(client, staff)
    _post_photo(client, "/account", _jpeg())
    r = client.post("/account", data={"action": "photo_remove"})
    assert b"The photo has been removed." in r.data
    assert "photo" not in staff and photo.src_of(staff) == ""


def test_the_password_form_still_works_beside_the_photo_form(client, staff):
    _as(client, staff)
    r = client.post("/account", data={"current_password": "pw-photo-staff-12345",
                                      "new_password": "a-new-password",
                                      "confirm_password": "a-new-password"})
    assert b"Your password has been changed." in r.data
    assert "photo" not in staff


# ══ 2. What is refused ═════════════════════════════════════════════════════

@pytest.mark.parametrize("data,name", [
    (b"%PDF-1.7 not a photo", "cv.pdf"),
    (b"MZ\x90\x00 an executable", "me.jpg"),
    (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "me.png"),
    (b"GIF89a....", "me.gif"),
])
def test_anything_but_jpeg_png_webp_is_refused_by_content(client, staff, data, name):
    _as(client, staff)
    r = _post_photo(client, "/account", data, name)
    assert b"is not a JPEG, PNG or WebP image" in r.data
    assert "photo" not in staff


def test_a_truncated_jpeg_is_refused(client, staff):
    _as(client, staff)
    r = _post_photo(client, "/account", _jpeg()[:200])
    assert b"could not be read" in r.data
    assert "photo" not in staff


def test_an_oversize_file_is_refused_before_decoding(client, staff, monkeypatch):
    _as(client, staff)
    monkeypatch.setattr(photo, "MAX_BYTES", 1000)
    r = _post_photo(client, "/account", _jpeg())
    assert b"the limit is" in r.data
    assert "photo" not in staff


def test_a_decompression_bomb_is_refused(client, staff, monkeypatch):
    _as(client, staff)
    monkeypatch.setattr(photo, "MAX_PIXELS", 10_000)
    r = _post_photo(client, "/account", _jpeg(400, 400))   # 160k px > 2x limit
    assert b"too large to process" in r.data
    r = _post_photo(client, "/account", _jpeg(120, 120))   # 14.4k px: warn band
    assert b"too large to process" in r.data
    assert "photo" not in staff


def test_no_file_chosen_is_refused(client, staff):
    _as(client, staff)
    r = client.post("/account", data={"action": "photo_upload"},
                    content_type="multipart/form-data")
    assert b"No photo was chosen." in r.data


def test_removing_when_there_is_none_changes_nothing(client, staff):
    _as(client, staff)
    r = client.post("/account", data={"action": "photo_remove"})
    assert b"There is no photo to remove." in r.data
    assert "photo_updated_at" not in staff


def test_a_server_without_pillow_says_so(client, staff, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("no PIL")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    _as(client, staff)
    r = _post_photo(client, "/account", _jpeg())
    assert b"not available on this server" in r.data
    assert "photo" not in staff


# ══ 3. Other people's photos: Owner yes, Director no ═══════════════════════

def test_an_owner_sets_and_clears_someone_elses_photo(client, owner, staff):
    r = _post_photo(client, f"/users/edit/{staff['id']}", _jpeg())
    assert r.status_code == 200 and b"The photo has been updated." in r.data
    assert photo.src_of(staff) and staff["photo_updated_by"] == owner["id"]
    client.post(f"/users/edit/{staff['id']}", data={"action": "photo_remove"})
    assert "photo" not in staff


def test_the_owner_sees_the_photo_form_on_the_edit_page(client, owner, staff):
    page = client.get(f"/users/edit/{staff['id']}").data
    assert b'name="action" value="photo_upload"' in page


def test_a_director_cannot_set_someone_elses_photo(client, director, staff):
    _as(client, director)
    page = client.get(f"/users/edit/{staff['id']}")
    assert page.status_code == 200, "control: the Director must reach the page"
    assert b"photo_upload" not in page.data, "the form must not be drawn"
    r = _post_photo(client, f"/users/edit/{staff['id']}", _jpeg())
    assert b"Only an Owner can change another person" in r.data
    assert "photo" not in staff


def test_a_director_cannot_clear_someone_elses_photo(client, director, staff):
    staff["photo"] = photo.PREFIX + base64.b64encode(_jpeg(10, 10)).decode()
    _as(client, director)
    client.post(f"/users/edit/{staff['id']}", data={"action": "photo_remove"})
    assert staff.get("photo"), "a Director cleared somebody else's photo"


def test_a_photo_post_to_edit_does_not_touch_roles_or_password(client, owner, staff):
    before = (list(staff["role_ids"]), staff["password_hash"], staff["display_name"])
    _post_photo(client, f"/users/edit/{staff['id']}", _jpeg())
    assert (staff["role_ids"], staff["password_hash"], staff["display_name"]) == (
        before[0], before[1], before[2])


def test_the_ordinary_edit_still_works_for_a_director(client, director, staff):
    _as(client, director)
    r = client.post(f"/users/edit/{staff['id']}",
                    data={"display_name": "Renamed", "role_ids": ["role-hr"]})
    assert r.status_code in (302, 303)
    assert staff["display_name"] == "Renamed" and staff["role_ids"] == ["role-hr"]


# ══ 4. Rendering ═══════════════════════════════════════════════════════════

def test_the_chip_shows_the_photo(client, staff):
    _as(client, staff)
    _post_photo(client, "/account", _jpeg())
    page = client.get("/account").data.decode()
    assert f'<img class="nu-avatar" src="{staff["photo"]}"' in page


def test_the_chip_without_a_photo_is_the_old_initials_chip(client, staff):
    _as(client, staff)
    page = client.get("/account").data.decode()
    assert '<span class="nu-avatar">PS</span>' in page
    assert '<img class="nu-avatar"' not in page


@pytest.mark.parametrize("tampered", [
    'javascript:alert(1)',
    'data:image/svg+xml;base64,PHN2Zz4=',
    'data:image/jpeg;base64,AAAA" onerror="alert(1)',
    'data:text/html;base64,PGgxPg==',
    photo.PREFIX + "A" * (photo.MAX_STORED + 10),
    12345,
])
def test_a_tampered_record_never_reaches_an_img_src(client, staff, tampered):
    staff["photo"] = tampered
    _as(client, staff)
    page = client.get("/account").data.decode()
    assert photo.src_of(staff) == ""
    assert '<img class="nu-avatar"' not in page
    assert "onerror" not in page and "javascript:alert" not in page
