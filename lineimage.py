"""
Pictures beside a document line — a LEAF (21 October 2026, client request
after go-live, CLIENT_CHANGES.md §0 forty-ninth block).

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
  ABOUT.md §7 gap 76 records it.

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
from datetime import datetime
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

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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
# THE LIBRARY — a NAME and an ITEM, over the ids this module already stores
# =============================================================================
#
# 29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, B2, from the
# 28 October meeting with Yogesh Bankar:
#
#     pictures addable from the create form, optional; each picture has a
#     NAME, printed under it; pictures kept in a library keyed to the item —
#     the spec id where there is one, otherwise the normalised description —
#     so the next document for the same item offers that picture preselected.
#
# **No second store.** The bytes are still one content-addressed JPEG under
# `attachment.root() / SUBDIR`, named by its own sha256, exactly as above. A
# library row is a **name and an item key over one of those ids**, in its own
# collection — CLIENT_CHANGES.md §1.3's rule: one item accumulates several
# pictures over a project's life, so it is not a list on anything.
#
# ⚠ **THE NAME IS ALSO SNAPSHOTTED ONTO THE LINE, and that is deliberate.**
#   A printed document reads its own rows and nothing else (§1.2), so the
#   name under the picture on a sent purchase order must not move when
#   somebody renames the library entry next month. The line carries
#   `image_name` beside `image`; the library is what the *form* offers, never
#   what the *sheet* reads. `name_on()` is the one writer of the pair and
#   `cell()` the one reader.
#
# ⚠ **The item key is EXACT, never fuzzy** — `po_parts.py`'s lesson (ABOUT.md
#   §2h) for the third time. A spec clause's code matched exactly gives
#   `spec:<id>`; everything else falls back to `desc:<normalised
#   description>`, which is `pipeline.norm_name()` — casefolded and
#   whitespace-collapsed and nothing else. Two lines that read the same offer
#   each other's pictures; two that do not, do not.

COLLECTION = "line_image_library"

NAME_MAX = 60     # the Make column's cap, which is the same kind of label
NAME_KEY = "image_name"


def _rows() -> dict:
    return STORE.setdefault(COLLECTION, {})


def item_key_of(line) -> str:
    """
    What this line is, for the purpose of offering it a picture.

    `spec:<spec id>` when the line's `part_no` is EXACTLY a specification
    clause's code — the same match `library_image_for()` makes, and codes are
    unique (`spec._validate()`). Otherwise `desc:<normalised description>`.
    `""` for a line with neither, which is offered nothing.
    """
    line = line or {}
    code = str(line.get("part_no") or "").strip()
    if code:
        for sid, s in (STORE.get("specs") or {}).items():
            if str(s.get("code") or "").strip() == code:
                return f"spec:{sid}"
    desc = P.norm_name(line.get("description") or line.get("name") or "")
    return f"desc:{desc}" if desc else ""


def register(image_id: str, name: str, item_key: str, who: str = "") -> str:
    """
    Put one picture in the library under a name, and return its row id.

    **Idempotent on (item key, image id).** Uploading the same picture twice
    for the same item renames the row it already has rather than growing a
    second one — the ids are content-addressed, so "the same picture" is a
    fact and not a guess.
    """
    iid = valid_id(image_id)
    key = str(item_key or "").strip()
    # ⚠ **A row must point at a file that is actually there.** `library_for()`
    #   drops one that does not, so storing it would be a row whose only
    #   effect is to be discarded on every read — and a row that outlives the
    #   file it names is how an id with nothing behind it gets offered.
    if not (iid and key and exists(iid)):
        return ""
    label = " ".join(str(name or "").split())[:NAME_MAX]
    rows = _rows()
    for rid, r in rows.items():
        if r.get("image") == iid and r.get("item_key") == key:
            if label:
                r["name"] = label
            r["at"] = _now()
            r["seq"] = _next_seq(rows)
            return rid
    rid = uuid.uuid4().hex
    rows[rid] = {"id": rid, "image": iid, "item_key": key, "name": label,
                 "at": _now(), "seq": _next_seq(rows),
                 "by": str(who or "").strip() or "unknown"}
    return rid


def _next_seq(rows: dict) -> int:
    """
    A monotonic sequence over the library, for ORDERING.

    ⚠ **`at` is to the minute and cannot order two rows written in the same
      one** — which is every row a test writes, and every row an operator
      writes while they have the Pictures page open. "Newest first" has to be
      a fact and not a coincidence of dict order.
    """
    return 1 + max((int(r.get("seq") or 0) for r in rows.values()), default=0)


def library_for(line) -> list:
    """
    `[(image_id, name)]` for this line's item, newest first — what a form
    offers. A row whose file is missing offers nothing, which is
    `library_image_for()`'s own rule.
    """
    key = item_key_of(line)
    if not key:
        return []
    out = []
    for r in sorted(_rows().values(),
                    key=lambda r: (int(r.get("seq") or 0), str(r.get("at") or "")),
                    reverse=True):
        if r.get("item_key") != key:
            continue
        iid = valid_id(r.get("image"))
        if iid and exists(iid) and iid not in {i for i, _n in out}:
            out.append((iid, str(r.get("name") or "")))
    return out


def grid_has_offers(lines) -> bool:
    """
    Does the library hold anything for ANY of these lines, or does any of them
    already carry a picture?  **Decides whether a picker draws the column at
    all** — `sheet_has_images()`'s own rule one form along: *the column
    appears only when a picture does.*

    ⚠ **This is what keeps `/po/create`'s pinned golden still.** On a
    schedule whose items are in nobody's library the picker renders
    byte-for-byte what it rendered before B2 — no column, no header, no cell.
    The operator adds the first picture for an item on the document's own
    Pictures page, which is what the §0 block says.
    """
    for li in lines or []:
        if li.get("is_header"):
            continue
        if image_of(li) or library_for(li):
            return True
    return False


def library_name_of(line, image_id) -> str:
    """The library's name for this picture on this item, or ""."""
    iid = valid_id(image_id)
    for i, n in library_for(line):
        if i == iid:
            return n
    return ""


def preselected(line):
    """
    `(image_id, name)` a form should open at, or `("", "")`.

    **The line's own picture first**, because somebody chose it; otherwise the
    item's most recent library entry, which is the *"offers that picture
    preselected"* half of B2.
    """
    own = image_of(line)
    if own:
        return own, name_of(line) or library_name_of(line, own)
    offers = library_for(line)
    return offers[0] if offers else ("", "")


def select_html(line, field: str, aria: str = "Picture",
                style: str = "", el_id: str = "") -> str:
    """
    One `<select>` of the library for this line's item — the control a create
    form carries.

    ⚠ **A SELECT AND NOT A FILE BOX, and the reason is measured rather than
      stylistic.** The §0 forty-ninth block recorded it: nginx refuses a
      request over 8 MB with its OWN 413 page (DEPLOY.md) and a phone photo
      is 3–5 MB, so a form carrying several file boxes fails on the second
      picture with nothing of ours on screen — and a browser cannot refill a
      file box, so every refused save would empty them all. A select carries
      no bytes at all. **New pictures are uploaded on the document's own
      Pictures page**, which is what registers one into the library.

    `""` when the item has nothing to offer AND the line carries nothing, so
    a document whose items are not in the library renders byte-for-byte what
    it did.
    """
    offers = library_for(line)
    own = image_of(line)
    if not offers and not own:
        return ""
    sel, _n = preselected(line)
    opts = ['<option value="">&mdash; no picture &mdash;</option>']
    seen = set()
    for iid, name in offers:
        seen.add(iid)
        mark = " selected" if iid == sel else ""
        label = name or f"picture {iid[:8]}"
        opts.append(f'<option value="{iid}"{mark}>{P.esc(label)}</option>')
    if own and own not in seen:
        # A picture set on this line that is not in the library — one uploaded
        # before B2, or on another item. Offered so an edit does not drop it.
        label = name_of(line) or f"this line's picture ({own[:8]})"
        opts.append(f'<option value="{own}" selected>{P.esc(label)}</option>')
    st = f' style="{style}"' if style else ""
    # `el_id` is for a grid whose payload builder reads the control by id
    # rather than posting the form field (`boqpick.js()`); the `name` is kept
    # either way, so a form that DOES post works unchanged.
    eid = f' id="{P.esc(el_id)}"' if el_id else ""
    return (f'<select name="{P.esc(field)}"{eid} aria-label="{P.esc(aria)}"{st}>'
            + "".join(opts) + "</select>")


def apply_choice(line: dict, posted, allowed_line: dict = None) -> bool:
    """
    Put the posted library choice on `line`, with its NAME snapshotted.
    Returns True when something changed.

    `""` removes the picture. An id that is not the minted shape, has no file,
    or is neither on the line already nor in `allowed_line`'s library is
    **ignored** — a crafted POST cannot attach an arbitrary file.
    """
    allowed_line = allowed_line if allowed_line is not None else line
    iid = valid_id(str(posted or "").strip())
    was = image_of(line), name_of(line)
    if not iid:
        if str(posted or "").strip() == "" and image_of(line):
            clear_image(line)
            line.pop(NAME_KEY, None)
            return True
        return False
    if not exists(iid):
        return False
    ok = {i for i, _n in library_for(allowed_line)} | {image_of(allowed_line)}
    if iid not in ok:
        return False
    set_image(line, iid)
    name_on(line, library_name_of(allowed_line, iid))
    return (image_of(line), name_of(line)) != was


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


def name_of(line) -> str:
    """The picture's NAME as this line snapshotted it, or "". §1.2's rule."""
    return " ".join(str((line or {}).get(NAME_KEY) or "").split())[:NAME_MAX]


def name_on(line: dict, name: str) -> None:
    """Snapshot the name beside the id. Absent when blank — no empty key."""
    label = " ".join(str(name or "").split())[:NAME_MAX]
    if label:
        line[NAME_KEY] = label
    else:
        line.pop(NAME_KEY, None)


def carry(src: dict) -> dict:
    """
    `{"image": id}` — and `image_name` with it — when `src` carries a picture,
    otherwise `{}`: for a route that builds a new line out of an upstream one
    (a draft PO's row becoming a purchase order's) and must keep the picture
    without writing an empty key onto every line that never had one.

    ⚠ **The NAME travels with the id** (29 October 2026, §0 fifty-ninth block,
      B2), because the new document is its own snapshot and must print the
      name it was raised with — not whatever the library says next month.
    """
    iid = image_of(src)
    if not iid:
        return {}
    name = name_of(src)
    return {KEY: iid, **({NAME_KEY: name} if name else {})}


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
  /* The picture's NAME, under it (29 Oct 2026, §0 fifty-ninth block, B2).
     Emitted only on a line that HAS a name, so a document raised before B2
     prints the cell it always printed. */
  .quotation-doc .c-img-n { font-size:5.4pt; line-height:1.15; text-align:center;
                            margin-top:.5mm; overflow-wrap:anywhere;
                            color:var(--doc-soft, #475569); }
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
    """
    One Image cell. A line with no picture gets an empty cell, not a gap.

    ⚠ **The NAME prints under the picture** (29 October 2026, §0 fifty-ninth
      block, B2) — read from the LINE's own `image_name`, never from the
      library, because a printed document reads its own rows (§1.2). A line
      with a picture and no name prints exactly what it printed before, which
      is what keeps every document raised before B2 still.
    """
    src = src_of(image_of(line))
    if not src:
        return f'<td class="c-img">{EMPTY_INNER}</td>'
    name = name_of(line)
    cap = f'<div class="c-img-n">{P.esc(name)}</div>' if name else ""
    return f'<td class="c-img"><img src="{src}" alt="{P.esc(name)}"/>{cap}</td>'


EMPTY_INNER = ""


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
  /* The picture's NAME (29 Oct 2026, §0 fifty-ninth block, B2). */
  .pic-nm { font-size:.68rem; color:var(--muted); text-align:center;
            margin-top:.2rem; overflow-wrap:anywhere; }
  .pic-name { max-width:11rem; font-size:.78rem; }
  .pic-acts select { max-width:13rem; font-size:.78rem; }
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
            nm = name_of(line)
            thumb = (f'<img src="{src}" alt="{P.esc(nm)}"/>'
                     + (f'<div class="pic-nm">{P.esc(nm)}</div>' if nm else ""))
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
            # ⚠ **The NAME box rides with the upload** (29 October 2026, §0
            #   fifty-ninth block, B2). One request still carries one file, so
            #   the 8 MB limit is nowhere near — it carries one short string
            #   as well. A blank name is allowed: the picture is still a
            #   picture, it just prints without a caption.
            acts = (f'<form method="POST" action="{action}" enctype="multipart/form-data">'
                    f'{hidden}<input type="hidden" name="action" value="upload"/>'
                    f'<input type="text" name="picture_name" maxlength="{NAME_MAX}" '
                    f'placeholder="Name (optional)" class="pic-name" '
                    f'aria-label="Name for line {P.esc(e["sno"])}\'s picture"/>'
                    f'<input type="file" name="picture" accept="{ACCEPT}" required '
                    f'aria-label="Picture for line {P.esc(e["sno"])}"/>'
                    f'<button type="submit" class="btn btn-ghost">'
                    f'{"Replace" if iid else "Upload"}</button></form>')
            # And the library for this item, where it has anything to offer —
            # the same control the create forms carry, so a picture uploaded
            # once is reusable on the next document for the same item.
            offers = library_for(line)
            if offers or iid:
                acts += (f'<form method="POST" action="{action}">'
                         f'{hidden}<input type="hidden" name="action" value="choose"/>'
                         f'{select_html(line, "picture_id", "Picture from the library")}'
                         f'<button type="submit" class="btn btn-ghost">Use</button></form>')
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


def apply_post(form, files, entries: list, who: str = "") -> tuple:
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
        # The NAME goes with the picture; the LIBRARY row stays, because it
        # is the item's picture and not this line's.
        e["line"].pop(NAME_KEY, None)
        return f"Picture removed from {label}.", ""
    if action == "upload":
        image_id, error = save(files.get("picture") if files else None)
        if error:
            return "", error
        # ⚠ **Registered in the library AND snapshotted onto the line**
        #   (29 October 2026, §0 fifty-ninth block, B2). The library is what
        #   the next document for this item offers; the snapshot is what this
        #   document prints (§1.2).
        name = str((form.get("picture_name") if form else "") or "")
        register(image_id, name, item_key_of(e["line"]), who)
        set_image(e["line"], image_id)
        name_on(e["line"], name)
        return f"Picture saved on {label}.", ""
    if action == "choose":
        posted = str(form.get("picture_id") or "")
        if not apply_choice(e["line"], posted, e["line"]):
            return "", ("That picture is not in this item's library. Nothing "
                        "was changed." if posted.strip()
                        else f"{label.capitalize()} has no picture to remove.")
        if image_of(e["line"]):
            return f"Picture set on {label}.", ""
        return f"Picture removed from {label}.", ""
    return "", "Nothing was changed."
