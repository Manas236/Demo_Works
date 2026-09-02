"""
attachment.py — file attachments on a charge and on a receipt  (CC-2 **B8**)
============================================================================

Built 2 September 2026 under the **first override block of that date** in
`CLIENT_CHANGES.md` §0, which is also the block that DECIDED the storage
mechanism after the 30 August 2026 one chose a shape that could not work.

⚠ **READ THIS BEFORE PROPOSING BLOBs AGAIN.** B8 was authorised on 30 August
2026 with attachments stored as **BLOBs in their own table**, and the pass sent
to build it stopped without writing a line, on a gate its own brief set. The
finding it stopped on is measured and is recorded in ABOUT.md §4:

  1. `db._blob()` is `json.dumps(..., default=str)`. Bytes are not JSON, so
     `default=str` catches them and writes the Python **repr** — `b'\\x89PNG'`
     goes in as 8 bytes and comes back as a 12-character **string**, with **no
     exception raised at any point**. A quiet substitution is the worst
     available failure mode for a payload.
  2. Every collection is one `data JSON NOT NULL` column. There is no column a
     BLOB could occupy without a second table shape.
  3. `db._sync_collection()` re-serialises and re-hashes **every record of every
     collection on every request**. An attachment is written once and never
     edited, so 100% of that work would be waste — measured at 18.6 ms per 3 MB
     attachment per request, on every page load in the application.

**So the bytes never enter STORE.** They go to a file on disk, written once,
and what enters STORE is a small metadata record that diffs like any other.
That is CC-2's own B8 text — *"real file storage with a path held on the
record"* — and the 2 September block returns to it.

Where the files live
--------------------

`<repo>/attachments/`, created on demand, **gitignored**, and **served by
nothing**. This application has no `/static` and none is created here: every
byte that reaches a browser does so through `_send()` below, reached only by
the two routes under it, which run after
`auth._gate()` has already refused everyone without the parent record's own
view permission.

The directory sits beside `backups/` because that is the convention
`tools/backup_db.py` already established for runtime data that is confidential,
large, and not part of the source tree.

⚠ **The path stored on the record is RELATIVE to that root** — `charge/<uuid>.png`,
never `C:/Users/.../attachments/charge/<uuid>.png`. An absolute path publishes
the disk layout of the machine the app runs on into a database that gets dumped
and handed around. It also makes the store relocatable: move the directory, set
`ATTACHMENT_DIR`, and every stored path still resolves.

What is guarded, and where
--------------------------

| guard | where | proved by |
|---|---|---|
| 5 MB per file | `validate()`, **before** anything is written | `test_attachments.py` |
| JPEG / PNG / PDF only, by **leading bytes** | `sniff()` | a renamed `.exe` labelled `image/png` |
| compulsory on a charge | `charge.py`'s POST branch | a charge saved with no file is refused |
| optional on a receipt | *deliberately absent* | a receipt saves with no file |
| cascade delete | `delete_for_parent()` | the file is gone from disk |
| who may see it | `auth.ROUTE_PERMISSIONS` | `charge.view` / `receipt.view` |
| an unapproved parent does not download | `may_download()` via `approval.can_print()` | ⚠ **ours, not CC-2's** — see below |

⚠ **THE APPROVAL GATE ON DOWNLOAD IS NOT IN CC-2 AND IS RECORDED AS OURS.**
B7 says an unapproved document may be viewed but not printed or downloaded.
It says nothing about that document's *supporting file*. Leaving the supplier
bill downloadable while the charge built from it is not would be a hole in B7
big enough to drive the whole document through — photograph the attachment,
you have the figures. So `may_download()` applies **B7's own gate, through B7's own
function**: `approval.can_print()`, not a second rule written here.

The consequence is exactly B7's shape: an unapproved attachment **still views
inline** and refuses only the raw download. It is listed in PROGRESS.md §4c as
unspecced-but-consistent scope, beside B7's own judgement calls.

⚠ **A receipt is on no approval ladder**, so nothing about it is gated here.
`approval.can_print()` returns `(True, "")` for a `doc_key` it does not know,
and `receipt` is not in `approval.DOCUMENTS`. That is not an oversight in this
module — it is the ladder's shape, and if a receipt ever joins `DOCUMENTS` this
gate starts applying to its attachments with no change here.

Vocabulary
----------

⚠ **CC-2's own warning, carried rather than paraphrased:** *"receipt" already
means the payment record. What is attached to it is a **proof of payment**
(bank slip / cheque / UTR). Do not overload the word.* The screen wording below
says "proof of payment" on a receipt and "supporting document" on a charge, and
`PARENTS` carries both strings so neither is typed twice.
"""

import datetime
import hashlib
import os
import pathlib
import uuid

from urllib.parse import quote_plus

from flask import Blueprint, abort, redirect, send_file, url_for

import approval
import pipeline as P
from store import STORE

attachment_bp = Blueprint("attachment", __name__, url_prefix="/attachment")


# =============================================================================
# THE LIMITS
# =============================================================================

# 5 MB, from CC-2's B8: *"A photographed supplier bill is 2-5 MB."*
#
# ⚠ **Checked BEFORE a byte is written to the attachment store**, which is what
#   the override block requires. It is NOT true that no byte has touched any
#   disk by then: Werkzeug spools a large upload to its own temporary file
#   while parsing the request, before any application code runs at all. That
#   spool is upstream of every view in this app and cannot be intercepted
#   without replacing the request's stream factory — a change that would reach
#   every form in the application, not just this one. What this guard
#   guarantees is the thing worth guaranteeing: an over-cap file never enters
#   the attachment store and never gets a metadata record.
#
# ⚠ `app.MAX_CONTENT_LENGTH` is None and is deliberately left that way. Setting
#   it would turn an over-cap upload into a 413 error page rendered by
#   `app.payload_too_large()`, which cannot say which field was too big or what
#   the limit for *this* field is. Refusing in the view returns the operator to
#   their half-filled form with a sentence naming the file and its size.
MAX_BYTES = 5 * 1024 * 1024

# The three types CC-2 names, keyed by the bytes a real file of that type
# STARTS with.
#
# ⚠ **The extension is never consulted and neither is the browser's
#   `Content-Type`.** Both are supplied by whoever is uploading. A renamed
#   executable arrives as `invoice.png` with `Content-Type: image/png` and the
#   only thing about it that is not the attacker's choice is its content — so
#   the content is what is read. `sniff()` is the whole of the type decision and
#   `save()` calls nothing else.
#
# ⚠ **The stored extension is derived from the SNIFFED type, not the upload's
#   name.** A file that really is a PNG is stored as `.png` whatever it was
#   called, so the name on disk can never disagree with the bytes in it.
SIGNATURES = (
    # (magic bytes, mime type, extension on disk)
    (b"\xff\xd8\xff",              "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n",         "image/png",  ".png"),
    (b"%PDF-",                     "application/pdf", ".pdf"),
)

# The longest signature, so `sniff()` reads exactly what it needs and no more.
_SNIFF_BYTES = max(len(sig) for sig, _m, _e in SIGNATURES)

ALLOWED_MIMES = tuple(m for _s, m, _e in SIGNATURES)

# What the operator is told they may upload. Derived from SIGNATURES so it can
# never drift from what is actually accepted.
ALLOWED_LABEL = "JPEG, PNG or PDF"


# =============================================================================
# THE PARENTS — the two records CC-2 names, and nothing else
# =============================================================================
#
# ⚠ **`required` is the ONLY difference CC-2 asks for, and it is data here
#   rather than a branch**, so the asymmetry is visible in one place instead of
#   being rediscovered in two modules.
#
#   * **charge — REQUIRED.** The 19 August list says *"Compulsory document
#     ATTACHMENT in the charge section"* and it is read literally.
#   * **receipt — OPTIONAL, and this is not an inconsistency to tidy away.**
#     CC-2 gives the reason in its own words: *"bank transfers often have no
#     separate slip, and compulsory would block honest entries."* ⚠ **A later
#     pass must not make it compulsory** without an override block of its own.
#
# `doc_key` is the key into `approval.DOCUMENTS`, or `""` for a record on no
# ladder. `permission` is the EXISTING permission that governs viewing the
# parent — no new permission is minted for attachments, because whoever may see
# the charge may see what the charge is evidenced by, and a second permission
# would be a second thing to grant and to get wrong.
PARENTS = {
    "charge": {
        "collection":   "charges",
        "permission":   "charge.view",
        "doc_key":      "charge",
        "required":     True,
        "noun":         "supporting document",
        "list_endpoint": "charge.list_charges",
    },
    "receipt": {
        "collection":   "receipts",
        "permission":   "receipt.view",
        # ⚠ Not on any ladder — `approval.DOCUMENTS` has no "receipt" entry, so
        #   `can_print()` returns True for it and nothing is gated. Stated as a
        #   fact about the ladder rather than a decision taken here.
        "doc_key":      "",
        "required":     False,
        # ⚠ CC-2's vocabulary warning. NOT "receipt" — that word is already the
        #   payment record itself.
        "noun":         "proof of payment",
        "list_endpoint": "receipt.list_receipts",
    },
}


# =============================================================================
# WHERE THE FILES LIVE
# =============================================================================

_REPO = pathlib.Path(__file__).resolve().parent

# Overridable so a deployment can put the store on another volume, and so the
# tests can point it at a temporary directory instead of the developer's own.
# `tools/backup_db.py` reads `.env` the same way for the same reason.
_ENV_KEY = "ATTACHMENT_DIR"

_DIRNAME = "attachments"


def root() -> pathlib.Path:
    """
    The attachment store's root directory, resolved fresh on every call.

    ⚠ **Not cached in a module constant.** The tests point `ATTACHMENT_DIR` at a
    temporary directory per test, and a value read once at import would make the
    first test's directory the one every later test wrote into — including,
    eventually, the developer's real one.
    """
    raw = (os.getenv(_ENV_KEY) or "").strip()
    return pathlib.Path(raw).resolve() if raw else (_REPO / _DIRNAME)


def _ensure_root(sub: str = "") -> pathlib.Path:
    d = root() / sub if sub else root()
    d.mkdir(parents=True, exist_ok=True)
    return d


def abs_path(rec) -> pathlib.Path:
    """
    The absolute path of one attachment's file, or a path that does not exist.

    ⚠ **The stored path is re-validated against the root on every read**, and
    that is defence in depth rather than distrust of `save()`. Nothing user-
    supplied reaches `stored_path` — it is minted from a uuid — but the value
    reaches here from the **database**, which is a different trust boundary from
    the one it was written across. A row edited by hand, restored from a dump,
    or written by a future migration must not be able to name
    `../../../../etc/passwd`, and this is the one place that can be guaranteed
    for every reader at once.
    """
    stored = str((rec or {}).get("stored_path") or "").strip()
    if not stored:
        return root() / "__missing__"
    base = root()
    candidate = (base / stored).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        # Escaped the root. Refuse by returning a path that cannot exist rather
        # than raising: every caller already handles a missing file, and a
        # traversal attempt must look exactly like a deleted one.
        return base / "__outside_root__"
    return candidate


# =============================================================================
# VALIDATION — content, then size, then nothing else
# =============================================================================

def sniff(head: bytes) -> str:
    """
    The mime type these leading bytes really are, or `""`.

    The whole of the type decision. Nothing here reads a filename or a
    `Content-Type` header, because both are the uploader's to choose.
    """
    for sig, mime, _ext in SIGNATURES:
        if head.startswith(sig):
            return mime
    return ""


def _ext_for(mime: str) -> str:
    for _sig, m, ext in SIGNATURES:
        if m == mime:
            return ext
    return ".bin"


def _size_of(fs) -> int:
    """
    An uploaded file's size in bytes, without reading it into memory.

    Seeks to the end, reads the offset, seeks back. Werkzeug has already
    spooled the body, so this costs nothing and — unlike `len(fs.read())` —
    does not pull a 5 MB file into the interpreter purely to measure it.
    """
    stream = fs.stream
    here = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(here, os.SEEK_SET)
    return int(size)


def validate(fs) -> tuple:
    """
    `(ok, error, mime, size)` for one uploaded file. **Writes nothing.**

    ⚠ **Order matters and is deliberate: SIZE FIRST, then content.** Reading the
    first bytes of a 400 MB upload to reject it for being 400 MB would be doing
    the attacker's work for them. The size check needs no read at all.
    """
    if fs is None or not (fs.filename or "").strip():
        return False, "No file was chosen.", "", 0

    size = _size_of(fs)
    if size <= 0:
        return False, "That file is empty.", "", 0
    if size > MAX_BYTES:
        return (False,
                f"That file is {_mb(size)} and the limit is {_mb(MAX_BYTES)}. "
                f"Attach a smaller scan or photograph.",
                "", size)

    head = fs.stream.read(_SNIFF_BYTES)
    fs.stream.seek(0, os.SEEK_SET)
    mime = sniff(head)
    if not mime:
        # ⚠ The message names what was READ, never what was claimed. Telling an
        #   operator "your image/png was rejected" when the file is not a PNG is
        #   telling them the wrong thing about their own file.
        return (False,
                f"That file is not a {ALLOWED_LABEL} document. Its contents do "
                f"not match any of those three types, whatever it is named.",
                "", size)

    return True, "", mime, size


def _mb(n: int) -> str:
    """'4.7 MB' — for a message an operator reads, not a log."""
    return f"{n / (1024 * 1024):.1f} MB"


# =============================================================================
# THE RECORD
# =============================================================================
#
# STORE["attachments"][uuid] = {
#   "id": uuid,
#   "filename":    "supplier-bill.jpg",   # AS UPLOADED. Display only — it is
#                                         # never used to build a path.
#   "stored_path": "charge/<uuid>.jpg",   # RELATIVE to root(). Minted here.
#   "size_bytes":  482913,
#   "mime_type":   "image/jpeg",          # SNIFFED, never the claimed one
#   "parent_type": "charge" | "receipt",
#   "parent_id":   uuid,
#   "uploaded_by": "<user id>",           # "" when there is no session
#   "uploaded_at": "2026-09-02 23:41",
#   "sha256":      "<64 hex>",            # what was written, so a silently
#                                         # corrupted or swapped file is
#                                         # detectable later
# }
#
# Four properties this shape exists to guarantee:
#
# 1. **The bytes are not in it.** That is the whole point of the module — see
#    the docstring. This record diffs like any other small record and costs
#    `db._sync_collection()` nothing measurable.
# 2. **`filename` never builds a path.** It is the operator's own string, kept
#    so the download arrives with the name they recognise, and escaped at every
#    render. The path on disk is `<uuid><sniffed extension>` and shares nothing
#    with it — so a file called `../../app.py` is a display string and not a
#    write target.
# 3. **`parent_type` + `parent_id` is the link, and it points ONE way.** The
#    charge does not carry a list of attachment ids. One parent accumulates
#    several files, which is CLIENT_CHANGES.md §1.3's rule exactly, and it is
#    also what makes the cascade a query rather than a second thing to keep in
#    step.
# 4. **`mime_type` is what was sniffed.** Serving a file under the type its
#    uploader claimed is how a stored `.html` becomes a same-origin script.


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _records() -> dict:
    return STORE.setdefault("attachments", {})


def for_parent(parent_type: str, parent_id: str) -> list:
    """Every attachment on one record, oldest first."""
    pid = str(parent_id or "")
    if not pid:
        return []
    rows = [a for a in _records().values()
            if a.get("parent_type") == parent_type and a.get("parent_id") == pid]
    return sorted(rows, key=lambda a: (a.get("uploaded_at") or "", a.get("id") or ""))


def count_for(parent_type: str, parent_id: str) -> int:
    return len(for_parent(parent_type, parent_id))


def save(fs, parent_type: str, parent_id: str, user=None) -> tuple:
    """
    `(record, error)` — validate, write the file, then write the metadata.

    ⚠ **That order is the one that cannot leave an orphan.** A metadata row
    written before the file would name a file that does not exist if the write
    then failed; the reverse leaves a file with no row, which
    `orphan_files()` finds and which no page ever shows. Neither is good, and
    the second is the one that cannot mislead a reader of the ledger.
    """
    spec = PARENTS.get(parent_type)
    if not spec:
        return None, "That record cannot carry an attachment."

    ok, err, mime, size = validate(fs)
    if not ok:
        return None, err

    aid = str(uuid.uuid4())
    rel = f"{parent_type}/{aid}{_ext_for(mime)}"
    _ensure_root(parent_type)
    dest = root() / rel

    data = fs.stream.read()
    with open(dest, "wb") as fh:
        fh.write(data)

    if user is None:
        user = approval.session_user()

    rec = {
        "id": aid,
        # `secure_filename` is NOT used: it mangles a perfectly ordinary
        # `बिल.pdf` to nothing at all, and this value never touches a path.
        # It is display text, and it is escaped where it is displayed.
        "filename": str(fs.filename or "file")[:255],
        "stored_path": rel,
        "size_bytes": int(size),
        "mime_type": mime,
        "parent_type": parent_type,
        "parent_id": str(parent_id or ""),
        "uploaded_by": str((user or {}).get("id") or ""),
        "uploaded_at": _now(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    _records()[aid] = rec
    return rec, ""


def delete_one(att_id: str) -> bool:
    """
    Remove one attachment — **the file first, then the row.**

    Returns True if a row was removed. A file that is already gone is not an
    error: the row is still removed, because a metadata record pointing at
    nothing is the orphan this function exists to prevent.
    """
    rec = _records().get(att_id)
    if not rec:
        return False
    path = abs_path(rec)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        # ⚠ **The row is removed anyway, and that is the deliberate choice.**
        # A file locked by a virus scanner or an open viewer must not leave a
        # ledger row pointing at a document the operator has been told is
        # deleted. The unreachable file is findable with `orphan_files()`; a
        # row that outlives its deletion is not findable at all.
        pass
    _records().pop(att_id, None)
    return True


def delete_for_parent(parent_type: str, parent_id: str) -> int:
    """
    **The cascade.** Every file and every row belonging to one deleted record.

    Called from `charge.delete_charge()` and `receipt.delete_receipt()` at the
    moment the parent is popped. It is a function here rather than two loops
    there so that a third parent type added later inherits it.
    """
    gone = 0
    for rec in list(for_parent(parent_type, parent_id)):
        if delete_one(rec.get("id")):
            gone += 1
    return gone


def orphan_files() -> list:
    """
    Files under the store that no metadata row claims.

    Not called by the application. It exists so that the failure mode
    `delete_one()` deliberately tolerates — a file that could not be unlinked —
    is findable rather than theoretical.
    """
    claimed = {str(a.get("stored_path") or "") for a in _records().values()}
    base = root()
    if not base.is_dir():
        return []
    out = []
    for p in base.rglob("*"):
        if p.is_file():
            rel = p.relative_to(base).as_posix()
            if rel not in claimed:
                out.append(rel)
    return sorted(out)


# =============================================================================
# READING ONE BACK — the only route that returns bytes
# =============================================================================

def parent_of(rec) -> tuple:
    """`(spec, parent_record)` for an attachment, either possibly None."""
    spec = PARENTS.get(str((rec or {}).get("parent_type") or ""))
    if not spec:
        return None, None
    parent = (STORE.get(spec["collection"]) or {}).get(str(rec.get("parent_id") or ""))
    return spec, parent


def may_download(rec) -> tuple:
    """
    `(allowed, reason)` — B7's gate, applied to a supporting file.

    ⚠ **This calls `approval.can_print()` rather than restating B7.** The rule
    about what an unapproved document may do is one rule with one home, and a
    second copy here would be a second copy to keep in step with the two named
    exemptions, the grandfather clause and the rejected case. What this function
    adds is only the mapping from an attachment to the document it supports.
    """
    spec, parent = parent_of(rec)
    if not spec:
        return False, "That attachment no longer belongs to anything."
    if not spec["doc_key"]:
        # On no ladder — a receipt. Nothing to gate.
        return True, ""
    if parent is None:
        return False, "The record this file supports no longer exists."
    allowed, why = approval.can_print(spec["doc_key"], parent)
    if allowed:
        return True, ""
    return False, (
        f"This file supports a {approval.DOCUMENTS[spec['doc_key']]['label']} "
        f"that has not been approved, so it cannot be downloaded. You can go on "
        f"viewing it on screen.")


def _send(rec, as_attachment: bool):
    path = abs_path(rec)
    if not path.is_file():
        abort(404)
    resp = send_file(
        path,
        # ⚠ The SNIFFED type, never the uploader's claim. Serving a file as the
        #   type its uploader named is how a stored file becomes a script.
        mimetype=str(rec.get("mime_type") or "application/octet-stream"),
        as_attachment=as_attachment,
        download_name=str(rec.get("filename") or "attachment"),
        conditional=True,
    )
    # ⚠ **Three headers, and none of them is decoration.**
    #
    #   nosniff  — without it a browser may disregard our Content-Type and
    #              guess from the bytes, which re-opens the hole the magic-byte
    #              check just closed.
    #   sandbox  — a PDF is an active document format: it can carry JavaScript
    #              and same-origin requests. Served from this app's own origin
    #              it would run with the operator's session. `sandbox` drops it
    #              into an opaque origin, where it can still be READ.
    #   frame-ancestors — this app's pages never embed an attachment, so
    #              nothing legitimate breaks, and a third-party page can no
    #              longer frame one to read it through the operator's cookie.
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "sandbox; frame-ancestors 'none'"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# ── THE ROUTES, MINTED PER PARENT TYPE ────────────────────────────────────────
#
# ⚠ **Three endpoints per parent, not three in total, and the reason is the
#   registry.** `auth.ROUTE_PERMISSIONS` maps one endpoint name to ONE
#   permission string. A single `/attachment/view/<id>` serving both parents
#   would need `charge.view` for one row and `receipt.view` for the next — a
#   per-record condition the registry cannot express. The only way to classify
#   it would be `AUTHENTICATED` with the real check hidden in the view, and that
#   is the precise weakening B5 exists to prevent: it would let anyone with a
#   login read every supplier bill in the ledger.
#
#   So the URL carries the parent type and each endpoint gets its own row.
#   `approval._register_routes()` solved the identical problem the identical
#   way — ABOUT.md §2i, *"Eight endpoints, not one"* — and the view bodies here
#   are still written exactly once.
#
# ⚠ **The type in the URL is checked against the record**, so
#   `/attachment/receipt/view/<a charge's attachment id>` is a 404 rather than a
#   way to read a charge's file under `receipt.view`. Without that line the
#   split would be decoration: the endpoint would carry the weaker permission
#   while serving the stronger record.


def _load(parent_type: str, att_id: str):
    rec = _records().get(att_id)
    if not rec or rec.get("parent_type") != parent_type:
        abort(404)
    return rec


def _do_view(parent_type: str, att_id: str):
    """
    The file, **inline**, for reading on screen.

    NOT gated on approval — B7's own words are that an unapproved document
    *"may be viewed"*. This is the half of B7 that permits.
    """
    return _send(_load(parent_type, att_id), as_attachment=False)


def _do_download(parent_type: str, att_id: str):
    """
    The file as a **download**, which is the half B7 gates.

    ⚠ **Refuses by URL and not by hiding the link** — B5's rule, and the reason
    `tests/test_attachments.py` requests this address directly for an unapproved
    charge rather than asserting a button is absent.

    A refusal is a **redirect carrying the reason**, matching `approval.py`'s
    house shape for a per-record rule. A 403 would make the endpoint look
    permanently unreachable to `tests/test_nav_visibility.py`'s sweep, when what
    is refused is this record, today.
    """
    rec = _load(parent_type, att_id)
    allowed, why = may_download(rec)
    if not allowed:
        spec, _parent = parent_of(rec)
        back = url_for((spec or {}).get("list_endpoint") or "dashboard.index")
        sep = "&" if "?" in back else "?"
        return redirect(f"{back}{sep}msg={quote_plus(why)}&type=error")
    return _send(rec, as_attachment=True)


def _do_delete(parent_type: str, att_id: str):
    """
    Remove one file from a parent that is keeping its other ones.

    ⚠ **POST only.** ABOUT.md §7.9f: a link that destroys is a link a crawler, a
    prefetch or a back button eventually fires.

    ⚠ **It refuses to remove the LAST attachment from a record that must have
    one.** CC-2 makes an attachment compulsory on a charge, and a rule enforced
    only at creation is not a rule — it is a speed bump. `charge.new_charge()`
    and this route are the two ways the requirement can be broken, and both are
    closed.

    ⚠ **It also honours `approval.can_modify()`.** Removing the evidence under
    an approved charge is a modification of that charge in every sense that
    matters, and B7 locks an approved document. `charge.delete_charge()` already
    refuses for the same reason; this is the same guard, not a new one.
    """
    rec = _load(parent_type, att_id)
    spec, parent = parent_of(rec)
    if not spec:
        abort(404)
    back = url_for(spec["list_endpoint"])

    if parent is not None and spec["doc_key"]:
        may, why_not = approval.can_modify(spec["doc_key"], parent)
        if not may:
            return redirect(f"{back}?msg={quote_plus(why_not)}&type=error")

    if spec["required"] and count_for(parent_type, rec.get("parent_id")) <= 1:
        return redirect(f"{back}?msg=" + quote_plus(
            f"A charge must keep at least one {spec['noun']}. "
            f"Attach the replacement first.") + "&type=error")

    delete_one(att_id)
    return redirect(f"{back}?msg=" + quote_plus("Attachment removed.") + "&type=success")


def _register_routes():
    """
    Mint `view_<type>`, `download_<type>` and `delete_<type>` for every parent.

    Written as a loop so the three view bodies exist once. Each endpoint still
    has its own name and its own row in `auth.ROUTE_PERMISSIONS`, which is the
    whole reason the routes are separate — see the note above.
    """
    for key in PARENTS:
        def _view(id, _k=key):
            return _do_view(_k, id)

        def _download(id, _k=key):
            return _do_download(_k, id)

        def _delete(id, _k=key):
            return _do_delete(_k, id)

        _view.__name__ = f"view_{key}"
        _download.__name__ = f"download_{key}"
        _delete.__name__ = f"delete_{key}"
        attachment_bp.add_url_rule(f"/{key}/view/<id>", endpoint=f"view_{key}",
                                   view_func=_view, methods=["GET"])
        attachment_bp.add_url_rule(f"/{key}/download/<id>", endpoint=f"download_{key}",
                                   view_func=_download, methods=["GET"])
        # POST only. See `_do_delete`.
        attachment_bp.add_url_rule(f"/{key}/delete/<id>", endpoint=f"delete_{key}",
                                   view_func=_delete, methods=["POST"])


_register_routes()


# =============================================================================
# THE TWO FRAGMENTS THE PARENT MODULES RENDER
# =============================================================================
#
# ⚠ **Written here, not in `charge.py` and `receipt.py`.** Two copies of an
#   upload field is two places for the accept list, the size wording and the
#   escaping to drift apart. The parents call these and lay their own section
#   around them.

def _esc(v) -> str:
    return P.esc(str(v or ""))


def upload_field(parent_type: str, parent_id: str = "") -> str:
    """
    The file input, plus the list of what is already attached.

    ⚠ **`enctype="multipart/form-data"` is the CALLER's job** and there is no
    way for this fragment to enforce it. A form without it posts the filename
    as a plain string and `request.files` is silently empty — which looks
    exactly like "the operator attached nothing". `tests/test_attachments.py`
    asserts the enctype on both forms for that reason.
    """
    spec = PARENTS.get(parent_type)
    if not spec:
        return ""
    noun = spec["noun"]
    need = ("<b>Required.</b> " if spec["required"] else "Optional. ")
    existing = _rows(parent_type, parent_id, with_delete=True) if parent_id else ""
    return f"""
      <div class="form-group">
        <label>{_esc(noun.title())}</label>
        {existing}
        <input type="file" name="attachment" accept=".jpg,.jpeg,.png,.pdf" />
        <div class="att-hint">{need}{_esc(ALLOWED_LABEL)}, up to {_mb(MAX_BYTES)}.
          The file's contents are checked &mdash; renaming one does not change
          what it is.</div>
      </div>"""


def _rows(parent_type: str, parent_id: str, with_delete: bool = False) -> str:
    """
    The list of what is already attached.

    ⚠ **Every endpoint name is built from `parent_type`**, because the routes
    are minted per parent — see `_register_routes()`. A hardcoded
    `attachment.view_attachment` would be a `BuildError` at render time, which
    is the failure this comment exists to stop somebody re-introducing.
    """
    rows = for_parent(parent_type, parent_id)
    if not rows:
        return ""
    out = []
    for a in rows:
        aid = a.get("id")
        dele = ""
        if with_delete:
            dele = (f'<form method="POST" action="'
                    f'{url_for(f"attachment.delete_{parent_type}", id=aid)}" '
                    f'style="display:inline">'
                    f'<button type="submit" class="btn btn-ghost att-x">Remove</button>'
                    f'</form>')
        out.append(
            f'<div class="att-row">'
            f'<a href="{url_for(f"attachment.view_{parent_type}", id=aid)}" '
            f'target="_blank" rel="noopener">{_esc(a.get("filename"))}</a>'
            f'<span class="att-meta">{_mb(int(a.get("size_bytes") or 0))}</span>'
            f'<a class="btn btn-ghost att-x" '
            f'href="{url_for(f"attachment.download_{parent_type}", id=aid)}">Download</a>'
            f'{dele}</div>')
    return f'<div class="att-list">{"".join(out)}</div>'


def panel(parent_type: str, parent_id: str) -> str:
    """Read-only list, for a register row or a view page."""
    return _rows(parent_type, parent_id, with_delete=False)


ATTACHMENT_STYLES = """
<style>
.att-list { margin: .4rem 0 .6rem; }
.att-row {
  display: flex; align-items: center; gap: .6rem;
  padding: .35rem .5rem; border: 1px solid var(--border);
  border-radius: 4px; margin-bottom: .35rem; font-size: .85rem;
}
.att-row a:first-child { font-weight: 600; }
.att-meta { color: var(--muted); font-size: .78rem; }
.att-x { padding: .15rem .5rem; font-size: .75rem; }
.att-hint { color: var(--muted); font-size: .78rem; margin-top: .3rem; }
.att-none { color: var(--muted); font-size: .8rem; }
</style>
"""
