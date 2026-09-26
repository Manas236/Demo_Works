"""
Profile photos — a LEAF (26 September 2026, client request after go-live).

A user may upload their own photo at `/account`; an **Owner** may set or clear
anybody's from `/users/edit/<id>`. Nobody else can touch another person's
photo. The photo replaces the initials in the nav chip and on the account page.

Why the photo is RE-ENCODED, never stored as uploaded
-----------------------------------------------------
Every upload goes through Pillow and comes out as a fresh 192 x 192 JPEG. That
one step does four jobs, and each of them is a reason Pillow became a runtime
dependency rather than an optional one:

* **It strips the metadata.** A photo taken on a phone carries EXIF, and EXIF
  carries GPS. Office staff photographed at home would otherwise publish where
  they live to every colleague who hovers the nav. A re-encode writes pixels
  and nothing else.
* **It kills polyglots.** A file that is a valid JPEG *and* something else is
  only ever stored as the JPEG Pillow wrote, never as the bytes that arrived.
* **It makes the stored size small and fixed.** A 4 MB phone photo becomes
  ~10 KB. The chip is on every screen page, so the photo rides along on every
  page load; storing the original would add megabytes to each one.
* **It lets the photo live in the user record as a base64 data URI**, which is
  the repo's convention for images (no `/static`, ABOUT.md §1). So there is no
  file route, no new endpoint, no new permission, and the nightly DB dump
  already backs it up.

Record shape (on the existing `users` record; nothing else changes)::

    photo             "data:image/jpeg;base64,..."   absent = no photo
    photo_updated_at  "YYYY-MM-DD HH:MM:SS"
    photo_updated_by  uid of whoever set or cleared it

⚠ **`src_of()` is the only reader.** It returns the stored value only when it
  is exactly the shape `encode()` writes, so a record edited directly in MySQL
  can never put anything but a base64 JPEG into an `<img src>`.

⚠ **Imports nothing from the app.** `auth.py` and `chrome.py` both import this
  module; `tests/test_import_directions.py` holds the leaf.
"""

import base64
import datetime
import io
import os
import re
import warnings

MAX_BYTES = 5 * 1024 * 1024        # same ceiling as attachments
MAX_PIXELS = 40_000_000             # refuse decompression bombs before decoding
SIDE = 192                          # stored square, px — sharp at 96 px on 2x screens
QUALITY = 82

PREFIX = "data:image/jpeg;base64,"
# A 192 px JPEG at q82 is ~6-20 KB; 64 KB of base64 is generous headroom and a
# hard ceiling on what a tampered record can make every page carry.
MAX_STORED = 64 * 1024
_STORED_RE = re.compile(r"^data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}$")

# What a real file STARTS with. The name and the browser's Content-Type are the
# uploader's choice; the content is not (attachment.py's rule).
SIGNATURES = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
)
ALLOWED_LABEL = "JPEG, PNG or WebP"


def _sniff(head: bytes) -> str:
    for sig, fmt in SIGNATURES:
        if head.startswith(sig):
            return fmt
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return ""


def _size_of(fs) -> int:
    stream = fs.stream
    here = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(here, os.SEEK_SET)
    return int(size)


def encode(fs) -> tuple:
    """
    `(data_uri, error)` for one uploaded file. Exactly one of the two is "".

    Order is size, then leading bytes, then decode — the cheap refusals first.
    """
    if fs is None or not (fs.filename or "").strip():
        return "", "No photo was chosen."
    size = _size_of(fs)
    if size <= 0:
        return "", "That file is empty."
    if size > MAX_BYTES:
        return "", (f"That photo is {size / 1048576:.1f} MB and the limit is "
                    f"{MAX_BYTES / 1048576:.0f} MB.")

    raw = fs.stream.read(MAX_BYTES + 1)
    fmt = _sniff(raw[:16])
    if not fmt:
        return "", f"That file is not a {ALLOWED_LABEL} image."

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return "", "Photo upload is not available on this server yet."

    try:
        with warnings.catch_warnings():
            # Pillow WARNS between 1x and 2x its limit and only raises past 2x.
            # Both are a refusal here.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            old_limit = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = MAX_PIXELS
            try:
                img = Image.open(io.BytesIO(raw))
                if (img.format or "").upper() != fmt:
                    return "", f"That file is not a {ALLOWED_LABEL} image."
                img.load()
            finally:
                Image.MAX_IMAGE_PIXELS = old_limit
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return "", "That image is too large to process. Use a normal photo."
    except Exception:
        return "", "That image could not be read. Try saving it again as a JPEG."

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    else:
        img = img.convert("RGB")
    img = ImageOps.fit(img, (SIDE, SIDE), Image.LANCZOS, centering=(0.5, 0.4))

    out = io.BytesIO()
    img.save(out, "JPEG", quality=QUALITY, optimize=True)   # no exif= : none written
    uri = PREFIX + base64.b64encode(out.getvalue()).decode("ascii")
    if len(uri) > MAX_STORED:
        return "", "That photo could not be made small enough. Try a simpler image."
    return uri, ""


def src_of(user) -> str:
    """The stored photo as an `<img src>`, or "" — never anything else."""
    val = (user or {}).get("photo") or ""
    if isinstance(val, str) and len(val) <= MAX_STORED and _STORED_RE.match(val):
        return val
    return ""


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def set_photo(user, data_uri: str, by: str) -> None:
    user["photo"] = data_uri
    user["photo_updated_at"] = _now()
    user["photo_updated_by"] = by or ""


def clear_photo(user, by: str) -> None:
    user.pop("photo", None)
    user["photo_updated_at"] = _now()
    user["photo_updated_by"] = by or ""
