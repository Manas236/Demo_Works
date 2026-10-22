"""
Pictures beside a document line — a LEAF (21 October 2026, client request
after go-live, CLIENT_CHANGES.md §0 forty-second block).

The client asked for a picture beside the description on the **proforma
invoice**, the **purchase order** and the **draft purchase order**. Manas's
four answers, taken before any of this was written:

1. **The library is the default, every line can override it.** A picture is
   set once on a specification-library clause; a proforma line written from
   that clause gets it automatically when the PI is raised. Any line on any of
   the three documents can have a picture uploaded, replaced or removed on the
   document's own **Pictures** page.
2. **The real purchase order AND the draft PO** — the draft is the one a
   supplier prices from, which is where a picture helps most.
3. **A separate Image column**, between Part No and the description.
4. **Commercial status left unstated**, by his choice.

Where the bytes live, and why not on the record
-----------------------------------------------
A picture is re-encoded through Pillow (`photo.load()` — the profile photo's
validation, shared) into a JPEG no larger than `MAX_SIDE` px on its long side,
and written ONCE to a file under `attachment.root() / SUBDIR`, named by the
**sha256 of its own bytes**. A line carries only that 64-character id under the
key `image`.

* **Not a base64 string on the line.** `db.sync()` re-serialises and re-hashes
  every record of every collection on every request (ABOUT.md §4); twenty
  pictures on a purchase order would put ~400 KB through that loop on every
  page load, for a payload that never changes. B8 met exactly this and its
  answer was a file on disk with a small record pointing at it — this is that
  answer again.
* **Content-addressed, so an id IS its content.** The same picture uploaded on
  ten orders is one file, and referencing it by id is as good as a copy for
  the snapshot rule (CLIENT_CHANGES.md §1.2): the bytes behind an id can never
  change. `src_of()` re-hashes what it reads and refuses a file whose content
  no longer matches its name.
* **Under the attachment root, so the backup already takes it.**
  `tools/backup_db.py` zips everything under `attachment.root()`.
* **Never deleted.** A file may be shared by many lines on many documents, and
  there is no index of who uses it. Deleting a document leaves its pictures on
  disk; at ~20 KB each that is a cost worth paying for never stranding a line.
  ABOUT.md §7 gap 56 records it.

The printed sheet still carries no external asset: `src_of()` inlines the file
as a `data:` URI at render, which is the house rule (ABOUT.md §1) — a document
must print with no server to fetch from.

The column appears only when a picture does
-------------------------------------------
`sheet_has_images()` decides it per document. A document with no picture —
every document written before this module existed, and every one nobody adds a
picture to — renders **byte-for-byte what it always rendered**, which is what
keeps `tests/test_print_golden.py` still. The column's stylesheet,
`SHEET_CSS`, is emitted only on a sheet that draws the column.

⚠ **Imports `store`, `pipeline` and `photo` at module level and nothing else of
ours.** `attachment` is reached inside `root()` only, because it imports
`approval` and through it the auth layer, and Pillow inside `save()` only —
`photo.py`'s arrangement, so a box without Pillow boots. Every document module
imports this one; it imports none of them back. `tests/test_import_directions.py`
holds that as a whitelist.
"""

import base64
import hashlib
import io
import os
import pathlib
import re
import uuid

import photo
import pipeline as P
from store import STORE


# =============================================================================
# THE STORE
# =============================================================================

SUBDIR = "line-images"

# Long side, px. The printed cell is ~18 mm, so 360 px is ~500 dpi there —
# sharp on paper and on a 3x phone screen, and still ~15–30 KB as a JPEG.
MAX_SIDE = 360
QUALITY = 82

# A re-encoded 360 px JPEG is far below this. A file on disk past it is not one
# `save()` wrote, and is never inlined into a page.
MAX_STORED_BYTES = 256 * 1024

ID_RE = re.compile(r"^[0-9a-f]{64}$")
JPEG_MAGIC = b"\xff\xd8\xff"
PREFIX = "data:image/jpeg;base64,"

# What the operator may upload — `photo.py`'s formats, said once.
ACCEPT = "image/jpeg,image/png,image/webp"

# Read-through cache of data URIs, keyed by (store root, id). Content-addressed
# files never change, so an entry can never go stale; the root is in the key
# because the tests point the store at a fresh directory per test.
_CACHE: dict = {}
_CACHE_MAX = 512


def root() -> pathlib.Path:
    """
    The directory pictures are written to: `attachment.root() / SUBDIR`.

    ⚠ **Resolved on every call, never cached** — `attachment.root()`'s own
    rule, because the tests repoint `ATTACHMENT_DIR` per test. Imported inside
    the function: `attachment` imports `approval`, which this leaf must not
    pull into the module graph for one path.
    """
    import attachment
    return attachment.root() / SUBDIR


def valid_id(value) -> str:
    """`value` when it is the shape `save()` mints, otherwise ""."""
    return value if isinstance(value, str) and ID_RE.match(value) else ""


def _path(image_id: str) -> pathlib.Path:
    # Only ever called with an id that passed `valid_id()`, so the name is 64
    # hex characters and cannot climb out of the directory.
    return root() / f"{image_id}.jpg"


def exists(image_id) -> bool:
    iid = valid_id(image_id)
    return bool(iid) and _path(iid).is_file()


def save(fs) -> tuple:
    """
    `(image_id, error)` for one uploaded file. Exactly one of the two is "".

    `photo.load()` does every refusal — size, format by leading bytes, a
    decompression bomb, a file Pillow cannot read — and hands back an upright
    RGB image. This shrinks it to fit `MAX_SIDE` **without cropping** (a
    profile photo is cut to a square; a part must not lose an end) and writes
    it once under its own hash.
    """
    img, error = photo.load(fs, "picture")
    if error:
        return "", error

    from PIL import Image
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=QUALITY, optimize=True)  # no exif= : none written
    data = out.getvalue()
    if len(data) > MAX_STORED_BYTES:
        return "", "That picture could not be made small enough. Try a simpler image."

    image_id = hashlib.sha256(data).hexdigest()
    target = _path(image_id)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written beside the target and renamed into place, so a reader never
        # sees half a file under a finished name.
        tmp = target.with_name(f".{image_id}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return image_id, ""


def src_of(image_id) -> str:
    """
    The picture as an `<img src>` data URI, or "" — **the only reader**.

    "" for an id that is not the minted shape, a file that is missing, a file
    that is not a JPEG, one past `MAX_STORED_BYTES`, or one whose bytes no
    longer hash to its name. A row edited in MySQL, or a file swapped on disk,
    can therefore never put anything into an `<img src>` but a JPEG this
    module wrote.
    """
    iid = valid_id(image_id)
    if not iid:
        return ""
    key = (str(root()), iid)
    hit = _CACHE.get(key)
    if hit:
        return hit
    try:
        path = _path(iid)
        if path.stat().st_size > MAX_STORED_BYTES:
            return ""
        data = path.read_bytes()
    except OSError:
        return ""
    if not data.startswith(JPEG_MAGIC) or hashlib.sha256(data).hexdigest() != iid:
        return ""
    uri = PREFIX + base64.b64encode(data).decode("ascii")
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = uri
    return uri


# =============================================================================
# THE LINE
# =============================================================================

KEY = "image"


def image_of(line) -> str:
    """The picture id a line carries, or "". Absent means no picture."""
    return valid_id((line or {}).get(KEY))


def set_image(line: dict, image_id: str) -> None:
    line[KEY] = image_id


def clear_image(line: dict) -> None:
    line.pop(KEY, None)


def carry(src: dict) -> dict:
    """
    `{"image": id}` when `src` carries a picture, otherwise `{}` — for a
    route that builds a new line out of an upstream one (a draft PO's row
    becoming a purchase order's) and must keep the picture without writing an
    empty key onto every line that never had one.
    """
    iid = image_of(src)
    return {KEY: iid} if iid else {}


def library_image_for(code) -> str:
    """
    The picture on the specification-library clause whose `code` is exactly
    `code`, or "" — the library DEFAULT.

    A proforma line written from the library carries the clause's code as its
    `part_no` (`specpick.process_selections()`), and codes are unique
    (`spec._validate()`), so this is an exact match on an identifier rather
    than a guess. **Exact after `strip()` and nothing else** — no casefold, no
    prefix — `po_parts.py`'s lesson (ABOUT.md §2h). Read straight out of
    `STORE["specs"]`, the one-way trick: this leaf never imports `spec.py`.
    A clause whose picture file is missing offers nothing.
    """
    code = str(code or "").strip()
    if not code:
        return ""
    for s in (STORE.get("specs") or {}).values():
        if str(s.get("code") or "").strip() == code:
            iid = image_of(s)
            return iid if exists(iid) else ""
    return ""


def fill_from_library(lines: list) -> int:
    """
    Give every line with no picture the library's picture for its `part_no`,
    where the library has one. Returns how many lines were filled.

    **Only ever fills a blank.** A line that already carries a picture —
    somebody chose it — is left exactly as it is.
    """
    n = 0
    for line in lines or []:
        if image_of(line):
            continue
        iid = library_image_for(line.get("part_no"))
        if iid:
            set_image(line, iid)
            n += 1
    return n


def fingerprint(text) -> str:
    """
    A short hash of a line's description, posted beside its position so a
    Pictures form opened before the document changed cannot put a picture on
    whatever line has since moved into that position.
    """
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


# =============================================================================
# THE PRINTED SHEET
# =============================================================================

COLUMN = ("c-img", "Image")

# ⚠ **Emitted only on a sheet that draws the column** — never added to
#   `VIEW_DOC_STYLES`, `PURCHASE_STYLES` or `PO_DOC_STYLES`, which every pinned
#   golden hashes. 20 mm out of the description's share; the picture is held
#   inside 18 mm square without being cropped or stretched.
SHEET_CSS = """<style>
  /* Pictures beside a line (lineimage.py, 21 Oct 2026) — only on a sheet that has one. */
  .quotation-doc .c-img     { width:20mm; text-align:center; vertical-align:middle; padding:1mm; }
  .quotation-doc .c-img img { display:block; margin:0 auto; max-width:18mm; max-height:18mm;
                              width:auto; height:auto; object-fit:contain; }
  @media screen and (max-width:760px) {
    .quotation-doc .c-img img { max-width:56px; max-height:56px; }
  }
</style>"""


def sheet_has_images(lines) -> bool:
    """Does any line resolve to a picture? Decides whether the column is drawn."""
    return any(src_of(image_of(l)) for l in (lines or []))


def with_column(columns) -> tuple:
    """`columns` with the Image column inserted after the part-number column."""
    out = []
    for col in columns:
        out.append(col)
        if col[0] == "c-partno":
            out.append(COLUMN)
    return tuple(out)


def cell(line) -> str:
    """One Image cell. A line with no picture gets an empty cell, not a gap."""
    src = src_of(image_of(line))
    img = f'<img src="{src}" alt=""/>' if src else ""
    return f'<td class="c-img">{img}</td>'


EMPTY_CELL = '<td class="c-img"></td>'


# =============================================================================
# THE PICTURES PAGE — what every document's page shares
# =============================================================================
#
# Each document owns its route, its permission and its page shell; this owns
# the rows and the POST. **One upload per request**, deliberately: nginx caps a
# request at 8 MB (DEPLOY.md) and a phone photo is 3–5 MB, so a single form
# carrying several would be refused by nginx's own 413 page, not ours.

PAGE_CSS = """<style>
  .pic-table { width:100%; border-collapse:collapse; font-size:.86rem; }
  .pic-table th { text-align:left; font-size:.72rem; text-transform:uppercase;
                  letter-spacing:.04em; color:var(--muted); padding:.5rem .6rem;
                  border-bottom:1px solid var(--border, #e5e7eb); }
  .pic-table td { padding:.6rem; border-bottom:1px solid var(--border, #e5e7eb);
                  vertical-align:middle; }
  .pic-thumb { width:84px; height:84px; border:1px solid var(--border, #e5e7eb);
               border-radius:8px; display:flex; align-items:center; justify-content:center;
               background:#fff; overflow:hidden; }
  .pic-thumb img { max-width:80px; max-height:80px; object-fit:contain; }
  .pic-none { font-size:.72rem; color:var(--muted); text-align:center; padding:0 .3rem; }
  .pic-desc { max-width:520px; overflow-wrap:anywhere; }
  .pic-part { color:var(--muted); font-size:.76rem; }
  .pic-acts { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; }
  .pic-acts form { display:flex; gap:.4rem; align-items:center; margin:0; }
  .pic-acts input[type=file] { max-width:220px; font-size:.78rem; }
  .pic-src { font-size:.72rem; color:var(--muted); margin-top:.25rem; }
  .pic-lib { margin:0 0 1rem; }
  @media (max-width:620px) {
    .pic-table thead { display:none; }
    .pic-table tr { display:block; border-bottom:1px solid var(--border, #e5e7eb); padding:.4rem 0; }
    .pic-table td { display:block; border:0; padding:.3rem .2rem; }
  }
</style>"""


def entry(key: str, sno, part_no, description, line: dict) -> dict:
    """One row of the Pictures page: where the line is, and what it says."""
    return {"key": key, "sno": sno, "part_no": str(part_no or ""),
            "description": str(description or ""), "line": line}


def rows_html(entries: list, action: str, editable: bool) -> str:
    """
    The Pictures page's table — one row per line that can carry a picture,
    each with its own Upload form and, where it has one, its own Remove form.

    `editable` False draws the pictures and no controls at all: a control
    that can only produce a refusal is not drawn (the owner's rule).
    """
    body = ""
    for e in entries:
        line = e["line"]
        iid = image_of(line)
        src = src_of(iid)
        if src:
            thumb = f'<img src="{src}" alt=""/>'
        elif iid:
            thumb = '<span class="pic-none">file missing &mdash; upload again</span>'
        else:
            thumb = '<span class="pic-none">no picture</span>'
        part = (f'<div class="pic-part">{P.esc(e["part_no"])}</div>'
                if e["part_no"] else "")
        acts = ""
        if editable:
            fp = fingerprint(e["description"])
            hidden = (f'<input type="hidden" name="line" value="{P.esc(e["key"])}"/>'
                      f'<input type="hidden" name="fp" value="{fp}"/>')
            acts = (f'<form method="POST" action="{action}" enctype="multipart/form-data">'
                    f'{hidden}<input type="hidden" name="action" value="upload"/>'
                    f'<input type="file" name="picture" accept="{ACCEPT}" required '
                    f'aria-label="Picture for line {P.esc(e["sno"])}"/>'
                    f'<button type="submit" class="btn btn-ghost">'
                    f'{"Replace" if iid else "Upload"}</button></form>')
            if iid:
                acts += (f'<form method="POST" action="{action}">'
                         f'{hidden}<input type="hidden" name="action" value="remove"/>'
                         f'<button type="submit" class="btn btn-ghost">Remove</button></form>')
        body += f"""
        <tr>
          <td>{P.esc(e["sno"])}</td>
          <td><div class="pic-thumb">{thumb}</div></td>
          <td class="pic-desc">{part}{P.esc(e["description"])}</td>
          <td><div class="pic-acts">{acts}</div></td>
        </tr>"""
    if not body:
        body = ('\n        <tr><td colspan="4" class="pic-none" style="text-align:left;">'
                'This document has no line that can carry a picture.</td></tr>')
    return f"""
    <table class="pic-table">
      <thead><tr><th>S.No</th><th>Picture</th><th>Line</th><th></th></tr></thead>
      <tbody>{body}
      </tbody>
    </table>"""


def apply_post(form, files, entries: list) -> tuple:
    """
    `(message, error)` for one Pictures POST. Exactly one of the two is "".

    Finds the line by its posted key **and** checks its fingerprint, so a
    page opened before the document changed refuses rather than landing the
    picture on another line. Nothing is written unless everything passes.
    """
    by_key = {e["key"]: e for e in entries}
    e = by_key.get(str(form.get("line") or ""))
    if e is None:
        return "", "That line is not on this document. Nothing was changed."
    if str(form.get("fp") or "") != fingerprint(e["description"]):
        return "", ("This document changed after the page was opened, so the "
                    "picture was not saved. The page below is current — try again.")

    action = str(form.get("action") or "")
    label = f"line {e['sno']}"
    if action == "remove":
        if not image_of(e["line"]):
            return "", f"{label.capitalize()} has no picture to remove."
        clear_image(e["line"])
        return f"Picture removed from {label}.", ""
    if action == "upload":
        image_id, error = save(files.get("picture") if files else None)
        if error:
            return "", error
        set_image(e["line"], image_id)
        return f"Picture saved on {label}.", ""
    return "", "Nothing was changed."
