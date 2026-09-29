"""
boqimport.py — Import a BOQ from the client's own Excel file  (29 Sep 2026)
==========================================================================
CLIENT_CHANGES.md §0, **thirty-fourth block** — new chargeable scope outside
MG/SF/2026-06, authorised by Manas Gawde on 29 September 2026.

    GET,POST /boq/import                the upload form
    GET,POST /boq/import/<token>        the preview: sheet, column mapping,
                                        flags, totals check, confirm
    GET      /boq/import/<token>/form   /boq/create, PREFILLED — nothing saved

**Nothing is saved until the operator presses Create BOQ on the ordinary form.**
The prefilled page IS `boq.create_boq()`, reached through its one `imported`
seam: the same editor, the same Save, the same duplicate/revision/size checks
and every line minted its `line_id` by `boq._clean_lines()` exactly as a typed
line is. This module never writes to `STORE["boqs"]`.

Import direction — one way, never reversed
------------------------------------------
    boqimport.py ──► sheetimport.py   the reader: bytes in, plain dicts out
    boqimport.py ──► boq.py           create_boq(imported=…), MAX_LINES,
                                      MAX_JSON_BYTES, BOQ_STYLES
    boq.py       ──► boqimport.py     NEVER. /boq/create links here with
                                      url_for("boqimport.upload"), a string.

Both halves are asserted at AST level in `tests/test_import_directions.py`.

The staging collection — `STORE["boq_imports"]`
-----------------------------------------------
The upload is parsed ONCE into a grid of cell values and staged under an
unguessable token (`secrets.token_urlsafe`), because the preview and the
confirm are separate requests and the file itself is never kept:

    {id, token, user_id, created_at, created_ts, filename, sheets, grid,
     sheet_index, mapping, layout, known, confirmed}

* **Owned.** Only the user who uploaded it may open it. Anybody else — and a
  token that has expired or was already used — gets the same 404 page, so the
  answer does not say whether a token exists.
* **Short-lived.** Rows older than 24 hours are purged on EVERY request to this
  module. A user keeps at most three; an upload past that drops their oldest.
* **Consumed.** A confirmed import's row is deleted the moment the prefilled
  form is rendered. ⚠ A **known layout** (below) keeps its row until the purge,
  because the form it goes straight to carries a *Change mapping* link back to
  the preview, and a deleted row has no preview to go back to.
* **The token only ever travels in a PATH.** Never a query string, never a
  hidden field that echoes back into one.

The layout memory — `STORE["import_layouts"]`
---------------------------------------------
    {id = signature, signature, mapping, created_by, created_at, use_count}

`sheetimport.signature()` hashes the header texts and their columns. Confirming
a mapping upserts it; an upload whose sheet matches a stored signature skips the
preview and opens the prefilled form directly.

The upload never touches disk
-----------------------------
Werkzeug spools any file part over 500 KB to a temporary FILE while it parses
the body — `attachment.py` records that as unavoidable for a form the whole
application shares. It is avoidable for ONE route: form parsing is lazy, the
gate (`auth._gate`) never reads the body, so `_read_upload()` swaps this one
request's stream factory for an in-memory buffer before `request.files` is
first touched. The Content-Length is checked against the cap first, so the
buffer is bounded before a byte is read.
"""

import datetime
import io
import json
import secrets
import time

from flask import Blueprint, redirect, request, url_for

import auth
import boq as BQ
import branding as B
import pipeline as P
import sheetimport as SI
from chrome import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES
from store import STORE

boqimport_bp = Blueprint("boqimport", __name__, url_prefix="/boq/import")


# =============================================================================
# BUSINESS RULES — tune here, not in a branch
# =============================================================================

STAGE_TTL_SECONDS = 24 * 3600
MAX_STAGED_PER_USER = 3

# Multipart overhead on top of the file itself: boundaries, part headers and
# the filename. Anything past cap + this is refused from the Content-Length
# header, before the body is read at all.
FORM_OVERHEAD_BYTES = 64 * 1024

# How much of a long cell the preview grid shows. DISPLAY ONLY — the staged
# grid keeps the whole text (up to sheetimport.MAX_CELL_CHARS).
PREVIEW_CELL_CHARS = 140

# The banner lists flags row by row up to this many, then says how many more.
BANNER_FLAG_ROWS = 200


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _uid() -> str:
    return (auth.current_user() or {}).get("id", "")


def _imports() -> dict:
    return STORE.setdefault("boq_imports", {})


def _layouts() -> dict:
    return STORE.setdefault("import_layouts", {})


# =============================================================================
# STAGING — purge, own, cap
# =============================================================================

def purge(now: float = None) -> int:
    """
    Delete every staged import older than 24 hours. Runs on every request to
    this module. A row whose timestamp cannot be read is deleted too — an
    import nobody can date is an import nobody should be able to open.
    """
    now = time.time() if now is None else now
    gone = 0
    for tok, rec in list(_imports().items()):
        ts = rec.get("created_ts") if isinstance(rec, dict) else None
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or now - ts > STAGE_TTL_SECONDS:
            del _imports()[tok]
            gone += 1
    return gone


def _own(token: str):
    """The staged import under `token` if the signed-in user raised it."""
    rec = _imports().get(str(token or ""))
    if not isinstance(rec, dict):
        return None
    uid = _uid()
    if not uid or rec.get("user_id") != uid:
        return None
    return rec


def _cap_per_user(uid: str) -> None:
    mine = sorted(((rec.get("created_ts") or 0, tok) for tok, rec in _imports().items()
                   if isinstance(rec, dict) and rec.get("user_id") == uid),
                  reverse=True)
    for _ts, tok in mine[MAX_STAGED_PER_USER:]:
        del _imports()[tok]


def _grid(rec: dict):
    try:
        return rec["grid"][int(rec.get("sheet_index") or 0)]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _sheet(rec: dict) -> dict:
    try:
        return rec["sheets"][int(rec.get("sheet_index") or 0)]
    except (IndexError, KeyError, TypeError, ValueError):
        return {}


def _known_mapping(grid: dict):
    """(mapping, layout record) when this sheet's layout has been confirmed
    before and its stored mapping still applies cleanly; (None, None) else."""
    sig = SI.signature(grid)
    lay = _layouts().get(sig) if sig else None
    if not isinstance(lay, dict):
        return None, None
    mapping = SI.clean_mapping(grid, lay.get("mapping") or {})
    if SI.mapping_problems(grid, mapping):
        return None, None
    return mapping, lay


def stage(wb: dict, filename: str, uid: str) -> tuple:
    """
    Stage a read workbook for `uid` and return `(token, known)`.

    `known` is True when the pre-selected sheet's layout has been confirmed
    before and its mapping still applies: the caller then goes straight to the
    prefilled form. The per-user cap runs here, after the new row is in.
    """
    token = secrets.token_urlsafe(24)
    sel = wb["selected"]
    grid = wb["grid"][sel]
    mapping, layout = _known_mapping(grid)
    known = mapping is not None
    if not known:
        mapping = SI.guess_mapping(grid)
    _imports()[token] = {
        "id": token, "token": token, "user_id": uid,
        "created_at": _now(), "created_ts": time.time(),
        "filename": filename, "format": wb["format"],
        "sheets": wb["sheets"], "grid": wb["grid"],
        "sheet_index": sel, "mapping": mapping,
        "layout": SI.signature(grid), "known": known, "confirmed": False,
    }
    _cap_per_user(uid)
    if known:
        layout["use_count"] = int(layout.get("use_count") or 0) + 1
    return token, known


def _upsert_layout(grid: dict, mapping: dict) -> None:
    sig = SI.signature(grid)
    if not sig:
        return
    lay = _layouts().get(sig)
    if isinstance(lay, dict):
        lay["mapping"] = dict(mapping)
        lay["use_count"] = int(lay.get("use_count") or 0) + 1
    else:
        _layouts()[sig] = {"id": sig, "signature": sig, "mapping": dict(mapping),
                           "created_by": _uid(), "created_at": _now(), "use_count": 1}


# =============================================================================
# THE UPLOAD — in memory, bounded, and read once
# =============================================================================

def _memory_stream(*_args, **_kwargs):
    """The stream factory for this one request: a BytesIO, never a temp file."""
    return io.BytesIO()


def _read_upload():
    """
    `(bytes, filename)` of the uploaded workbook, or `SI.Refused`.

    ⚠ **Order is the guarantee.** The Content-Length is checked BEFORE
      `request.files` is touched, because touching it is what makes Werkzeug
      read the body; the stream factory is swapped before it too, so the part
      lands in memory and never in a temporary file.
    """
    limit = SI.MAX_UPLOAD_BYTES + FORM_OVERHEAD_BYTES
    length = request.content_length
    if length is None:
        raise SI.Refused("The upload arrived without a length and was not read. "
                         "Try again from the form.")
    if length > limit:
        raise SI.Refused(f"That upload is {length / 1048576:.1f} MB and the limit "
                         f"is {SI.MAX_UPLOAD_BYTES // 1048576} MB. Save the BOQ "
                         f"sheet on its own as a new workbook and upload that.")
    request.max_content_length = limit
    request._get_file_stream = _memory_stream
    fs = request.files.get("workbook")
    if fs is None or not (fs.filename or "").strip():
        raise SI.Refused("Choose the Excel file to import.")
    data = fs.stream.read(SI.MAX_UPLOAD_BYTES + 1)
    return data, str(fs.filename or "").strip()


# =============================================================================
# LINES — the staged grid shaped for the BOQ editor
# =============================================================================

def num_text(v) -> str:
    """
    A number as the text the editor holds, EXACTLY.

    The shortest text that reads back as the same float — so 2024.0 is "2024"
    and 7.000000000000001 stays itself. It is never rounded: the client's
    sheets carry figures a formula left with float dust, and rounding here
    would change an agreed rate by a paisa before anybody had looked at it.
    `boq._form_payload_from()` uses `:g`, which keeps six digits; that is its
    business and is not reused here for exactly this reason.
    """
    if v is None:
        return ""
    f = float(v)
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


def editor_model(result: dict) -> dict:
    """
    `sheetimport.build()`'s result as the editor's boot model — the shape
    `boq._form_payload_from()` produces, plus three UI keys the editor draws
    and `boq._clean_lines()` never reads:

        _flags  the row's flag sentences — a chip on the row
        _block  the quantity was left blank by a flag — red, and the form
                refuses to submit until it is typed (ABOUT.md §7 gap 42)
        _row    the source row number, for the chip and the band

    Every line goes in with a blank `line_id`, so each is minted on save.
    """
    lines = []
    for l in result["lines"]:
        header = bool(l["is_header"])
        row = {
            "line_id": "",
            "item_no": l["item_no"],
            "parent_item_no": l["parent_item_no"],
            "section": l["section"],
            "is_header": header,
            "description": l["description"],
            "remark": "",
            "unit": "" if header else l["unit"],
            "area_qty": {},
            "total_qty": "" if header else num_text(l["qty"]),
            "supply_base_rate": "" if header else num_text(l["supply_base_rate"]),
            "supply_escalation_pct": "" if header else num_text(l["escalation_pct"]),
            "supply_rate": "" if header else num_text(l["supply_rate"]),
            "supply_hsn": "", "supply_gst_rate": "",
            "install_base_rate": "" if header else num_text(l["install_base_rate"]),
            "install_escalation_pct": "" if header else num_text(l["install_escalation_pct"]),
            "install_rate": "" if header else num_text(l["install_rate"]),
            "install_sac": "", "install_gst_rate": "",
            "_row": l["row"],
        }
        if l["flags"]:
            row["_flags"] = [f"Row {l['row']}: {m}" for m in l["flags"]]
        if l["block"] and not header:
            row["_block"] = True
        lines.append(row)
    return {"sections": [{"code": s["code"], "title": s["title"], "areas": []}
                         for s in result["sections"]],
            "lines": lines}


def too_large(model: dict) -> str:
    """
    The refusal for a schedule the form could never save, or "".

    Measured the way `boq.create_boq()` measures the POST: the line count
    against `MAX_LINES`, then the UTF-8 bytes of the JSON the editor will post
    against `MAX_JSON_BYTES`. ⚠ **Never truncated**: a BOQ that silently lost
    its last forty lines would print, bill and total as if it were whole.
    """
    n = len(model["lines"])
    size = len(json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if n <= BQ.MAX_LINES and size <= BQ.MAX_JSON_BYTES:
        return ""
    about = BQ.MAX_LINES if size <= BQ.MAX_JSON_BYTES else int(BQ.MAX_JSON_BYTES * n / max(size, 1))
    about = max(1, min(about, BQ.MAX_LINES))
    return (f"This sheet has {n} lines; the BOQ limit is about {about}. Split it — "
            f"save each part as its own sheet and import them as separate BOQs. "
            f"Nothing was cut off: the import stops here rather than drop lines.")


# =============================================================================
# RENDERING
# =============================================================================

IMPORT_STYLES = """
<style>
.imp-card{background:var(--card,#fff);border:1px solid var(--border,#e2e8f0);border-radius:12px;padding:1.1rem 1.2rem;margin-bottom:1rem;}
.imp-card h2{font-size:1rem;margin:0 0 .6rem;}
.imp-note{font-size:.82rem;color:var(--muted,#64748b);margin:.4rem 0 0;}
.imp-file{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;}
.imp-file input[type=file]{flex:1 1 260px;min-width:0;}
.imp-wrap{overflow-x:auto;border:1px solid var(--border,#e2e8f0);border-radius:10px;}
.imp-grid{border-collapse:collapse;font-size:.78rem;min-width:100%;}
.imp-grid th,.imp-grid td{border-bottom:1px solid var(--border,#e2e8f0);padding:.3rem .45rem;vertical-align:top;text-align:left;white-space:pre-wrap;max-width:22rem;}
.imp-grid thead th{background:#f8fafc;position:sticky;top:0;}
.imp-grid .imp-rn{color:var(--muted,#64748b);font-variant-numeric:tabular-nums;white-space:nowrap;}
.imp-grid tr.imp-hdr td{background:#eef2ff;font-weight:600;}
.imp-grid td.is-flag{background:#fef3c7;}
.imp-grid td.is-red{background:#fee2e2;}
.imp-grid select{font-size:.76rem;max-width:12rem;}
.imp-grid select.is-undecided{border-color:#dc2626;background:#fef2f2;}
.imp-flags{margin:.3rem 0 0 1.1rem;padding:0;font-size:.8rem;}
.imp-flags li{margin:.15rem 0;}
.imp-flags li.is-red{color:#b91c1c;}
.imp-stats{display:flex;gap:1.2rem;flex-wrap:wrap;font-size:.85rem;}
.imp-stats b{font-size:1.05rem;}
.imp-ok{color:#15803d;font-weight:600;}
.imp-bad{color:#b91c1c;font-weight:600;}
.imp-banner{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:.8rem 1rem;margin-bottom:1rem;font-size:.86rem;}
.imp-banner.has-red{border-color:#fca5a5;background:#fff7f7;}
.imp-banner details{margin-top:.5rem;}
.imp-banner summary{cursor:pointer;font-weight:600;}
.imp-actions{display:flex;gap:.7rem;flex-wrap:wrap;justify-content:flex-end;margin-top:1rem;}
</style>
"""


def _page(title: str, body: str) -> str:
    """A finished page. Never Jinja-rendered (ABOUT.md §1)."""
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{BQ.BOQ_STYLES}{IMPORT_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
  <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE}</p></footer>
</main>
</body></html>"""


def _not_found():
    """
    The one answer for a token that is not yours, has expired, or was used.

    Returned with status 404 DIRECTLY rather than through `abort(404)`: the
    app-wide 404 handler redirects to the dashboard, which would tell the
    client this request succeeded and would lose the sentence below.
    """
    body = f"""
  <div class="page-top"><h1>Import <span>not found</span></h1></div>
  <div class="imp-card">
    <p>This import is not available. It may have expired (an upload is kept for
    24 hours), it may already have been opened into the BOQ form, or it belongs
    to someone else.</p>
    <p class="imp-note">Nothing was saved. Upload the file again to start over.</p>
    <div class="imp-actions">
      <a class="btn" href="{url_for('boqimport.upload')}">Upload an Excel BOQ</a>
    </div>
  </div>"""
    return _page("Import not found", body), 404


def _upload_page(error: str = "") -> str:
    avail = SI.available()
    alert = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>' if error else ""
    missing = [k for k, ok in avail.items() if not ok]
    unavailable = ""
    if missing:
        unavailable = (f'<div class="alert alert-error">&#10007; '
                       f'{P.esc(SI.UNAVAILABLE)} (missing: {P.esc(", ".join(missing))})</div>')
    body = f"""
  {alert}{unavailable}
  <div class="page-top">
    <h1>Import <span>BOQ from Excel</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boq.create_boq')}" class="btn btn-ghost">&#8592; Back to Create BOQ</a>
    </div>
  </div>
  <div class="imp-card">
    <h2>Your own BOQ workbook, any layout</h2>
    <form method="POST" enctype="multipart/form-data" class="imp-file">
      <input type="file" name="workbook" accept=".xlsx,.xls" required/>
      <button class="btn" type="submit">Upload</button>
    </form>
    <p class="imp-note">An <b>.xlsx</b> or <b>.xls</b> file up to
    {SI.MAX_UPLOAD_BYTES // 1048576} MB. A workbook with macros (.xlsm) is refused
    &mdash; save it as .xlsx first. The file is read once and not kept.</p>
    <p class="imp-note">You will see the sheet with a guessed column for each
    heading, and every cell the reader could not take as a number, before
    anything else happens. Then the ordinary <b>Create BOQ</b> form opens with
    every line filled in. <b>Nothing is saved until you press Create BOQ.</b></p>
    <p class="imp-note">Only the <b>total</b> quantity is read; floor or area
    columns are left out. Where the sheet gives one rate per line, that rate is
    taken as the <b>selling</b> rate and the base rate is left blank for you to
    fill in later.</p>
  </div>"""
    return _page("Import BOQ", body)


def _cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return num_text(v)
    s = str(v)
    if len(s) > PREVIEW_CELL_CHARS:
        s = s[:PREVIEW_CELL_CHARS - 1] + "…"
    return s


def _target_select(col: int, current: str) -> str:
    opts = []
    if current == SI.UNDECIDED:
        opts.append(f'<option value="{SI.UNDECIDED}" selected>'
                    f'&#8212; choose: Supply or Installation &#8212;</option>')
    for key, label in SI.TARGETS:
        sel = " selected" if key == current else ""
        opts.append(f'<option value="{P.esc(key)}"{sel}>{P.esc(label)}</option>')
    cls = ' class="is-undecided"' if current == SI.UNDECIDED else ""
    return (f'<select name="map_{int(col)}"{cls} aria-label="Column '
            f'{SI.col_letter(col)}">{"".join(opts)}</select>')


def _money(v) -> str:
    return "&mdash;" if v is None else f"&#8377;&nbsp;{float(v):,.2f}"


def _totals_html(totals: dict) -> str:
    status = totals.get("status")
    if status == "no_total":
        n = totals.get("total_rows") or 0
        why = (f" ({n} total row{'s' if n != 1 else ''} on the sheet, none marked "
               f"Grand Total)" if n else "")
        return f"Totals check: <b>no grand total found</b> on the sheet{why}."
    parts = []
    track_name = {"supply": "Supply", "install": "Installation", "both": "Supply + Installation"}
    for c in totals.get("checks") or []:
        name = track_name.get(c.get("track"), "")
        if c.get("status") == "no_figure":
            parts.append(f"{name}: computed {_money(c.get('computed'))}, "
                         f"no figure on the total row")
        elif c.get("status") == "match":
            parts.append(f'{name}: <span class="imp-ok">matches</span> '
                         f"{_money(c.get('sheet'))}")
        else:
            parts.append(f'{name}: <span class="imp-bad">does not match</span> &mdash; '
                         f"sheet {_money(c.get('sheet'))}, quantity &times; rate "
                         f"{_money(c.get('computed'))} (difference "
                         f"{_money(c.get('difference'))})")
    where = f" (row {int(totals['row'])}, “{P.esc(totals.get('label'))}”)" if totals.get("row") else ""
    if not parts:
        return f"Totals check: a grand total row was found{where} but no rate is mapped to check it against."
    return f"Totals check{where}: " + "; ".join(parts) + "."


def _flag_list(flags: list, limit: int = BANNER_FLAG_ROWS) -> str:
    items = []
    for f in flags[:limit]:
        where = f"Row {int(f['row'])}" + (f", column {P.esc(f['col'])}" if f.get("col") else "")
        raw = f" (“{P.esc(f['raw'])}”)" if f.get("raw") and f.get("kind") in ("text", "na", "error") else ""
        cls = ' class="is-red"' if f.get("severity") == "red" else ""
        items.append(f"<li{cls}>{where} &middot; {P.esc(f['field'])}: "
                     f"{P.esc(f['message'])}{raw}</li>")
    more = len(flags) - limit
    if more > 0:
        items.append(f"<li>&hellip; and {more} more.</li>")
    return f'<ul class="imp-flags">{"".join(items)}</ul>' if items else ""


def _preview_page(token: str, rec: dict, error: str = "", problems=None) -> str:
    grid = _grid(rec)
    sheet = _sheet(rec)
    mapping = SI.clean_mapping(grid, rec.get("mapping") or {})
    result = SI.build(grid, mapping)
    problems = SI.mapping_problems(grid, mapping) if problems is None else problems

    alert = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>' if error else ""
    if problems:
        alert += ('<div class="alert alert-error" style="display:block;">'
                  '<div style="font-weight:700;margin-bottom:.3rem;">&#10007; '
                  'Before this can open as a BOQ:</div><ul style="margin:0 0 0 1.1rem;">'
                  + "".join(f"<li>{P.esc(p)}</li>" for p in problems) + "</ul></div>")

    # Sheet picker.
    opts = []
    for i, s in enumerate(rec.get("sheets") or []):
        tag = "" if s.get("visibility") == "visible" else " (hidden)"
        dis = "" if s.get("staged") else " disabled"
        sel = " selected" if i == rec.get("sheet_index") else ""
        opts.append(f'<option value="{i}"{sel}{dis}>{P.esc(s.get("name"))}{tag} '
                    f'&middot; {int(s.get("rows") or 0)} rows</option>')
    unread = [s for s in rec.get("sheets") or [] if not s.get("staged")]
    unread_html = ""
    if unread:
        unread_html = ('<ul class="imp-flags">' + "".join(
            f"<li>{P.esc(s.get('name'))}: {P.esc(s.get('refusal') or 'not read')}</li>"
            for s in unread) + "</ul>")

    # The grid: column letters, a dropdown per column, the header row(s),
    # then the first rows of data. Cells a flag came from are shaded.
    cols = grid["cols"]
    flagged = {}
    for f in result["flags"]:
        key = (f["row"], f["col"])
        if flagged.get(key) != "is-red":
            flagged[key] = "is-red" if f.get("severity") == "red" else "is-flag"
    head_cells = "".join(f"<th>{SI.col_letter(c)}</th>" for c in cols)
    map_cells = "".join(f"<th>{_target_select(c, mapping.get(str(c), ''))}</th>" for c in cols)
    body_rows = []
    hdr = grid.get("header") or []
    shown = list(range(hdr[0], hdr[1] + 1)) if hdr else []
    start = SI.data_start(grid)
    shown += list(range(start, min(len(grid["rows"]), start + SI.PREVIEW_ROWS)))
    for ri in shown:
        rnum, vals = grid["rows"][ri]
        tds = []
        for ci, c in enumerate(cols):
            v = vals[ci] if ci < len(vals) else None
            cls = flagged.get((rnum, SI.col_letter(c)), "")
            cls_attr = f' class="{cls}"' if cls else ""
            tds.append(f"<td{cls_attr}>{P.esc(_cell_text(v))}</td>")
        rcls = ' class="imp-hdr"' if hdr and hdr[0] <= ri <= hdr[1] else ""
        body_rows.append(f'<tr{rcls}><td class="imp-rn">{int(rnum)}</td>{"".join(tds)}</tr>')
    more_rows = len(grid["rows"]) - (start + SI.PREVIEW_ROWS)
    more_note = (f'<p class="imp-note">&hellip; and {more_rows} more rows on the sheet, '
                 f'all of which are read.</p>' if more_rows > 0 else "")
    no_header = ("" if hdr else
                 '<p class="imp-note">No heading row was recognised on this sheet, '
                 'so every column starts as <i>ignore</i> and the lines start at the '
                 'top. Choose what each column holds.</p>')

    c = result["counts"]
    red = sum(1 for f in result["flags"] if f.get("severity") == "red")
    stats = (f'<div class="imp-stats"><span><b>{c["lines"]}</b> lines</span>'
             f'<span><b>{c["headers"]}</b> spec headers</span>'
             f'<span><b>{c["sections"]}</b> sections</span>'
             f'<span><b>{c["totals_dropped"]}</b> total rows left out</span>'
             f'<span><b>{len(result["flags"])}</b> flagged cells'
             f'{f" ({red} blocking)" if red else ""}</span></div>')

    known = ""
    if rec.get("layout") and rec["layout"] in _layouts():
        lay = _layouts()[rec["layout"]]
        known = (f'<p class="imp-note">This layout has been confirmed '
                 f'{int(lay.get("use_count") or 0)} time(s) before; its saved column '
                 f'choices are applied. Confirming again saves any change.</p>')

    act = url_for("boqimport.preview", token=token)
    body = f"""
  {alert}
  <div class="page-top">
    <h1>Import <span>check the columns</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('boqimport.upload')}" class="btn btn-ghost">&#8592; Upload a different file</a>
    </div>
  </div>
  <form method="POST" action="{act}">
    <div class="imp-card">
      <h2>{P.esc(rec.get("filename"))}</h2>
      <div class="imp-file">
        <label for="sheet" style="font-weight:600;font-size:.85rem;">Sheet</label>
        <select id="sheet" name="sheet">{"".join(opts)}</select>
        <button class="btn btn-ghost" type="submit" name="action" value="update">Show this sheet</button>
      </div>
      <p class="imp-note">A hidden sheet is listed and never chosen for you.
      Each import reads one sheet.</p>
      {unread_html}
      {known}
    </div>

    <div class="imp-card">
      <h2>What each column holds</h2>
      {no_header}
      <div class="imp-wrap">
        <table class="imp-grid">
          <thead><tr><th>Row</th>{head_cells}</tr><tr><th></th>{map_cells}</tr></thead>
          <tbody>{"".join(body_rows)}</tbody>
        </table>
      </div>
      {more_note}
      <p class="imp-note">A rate column that does not say whether it is Supply or
      Installation is left for you to choose. With one rate per line that rate is
      the <b>selling</b> rate; the base rate stays blank for you to fill in later.
      Amount columns are only used to check the totals.</p>
      <div class="imp-actions">
        <button class="btn btn-ghost" type="submit" name="action" value="update">Update preview</button>
      </div>
    </div>

    <div class="imp-card">
      <h2>What will be imported</h2>
      {stats}
      <p style="margin:.6rem 0 0;font-size:.85rem;">{_totals_html(result["totals"])}</p>
      {_flag_list(result["flags"])}
      <p class="imp-note">Every flagged cell is left <b>blank</b> on the form &mdash;
      nothing is worked out or turned into 0. A red one is a quantity: the form will
      not save until you type it or remove the line.</p>
      <div class="imp-actions">
        <button class="btn" type="submit" name="action" value="confirm">Confirm &amp; open the BOQ form</button>
      </div>
    </div>
  </form>"""
    return _page("Import BOQ", body)


def _banner(token: str, rec: dict, result: dict) -> str:
    """The summary that sits on top of the prefilled form. Escaped here; the
    form's own `demo_banner` sits beside it."""
    c = result["counts"]
    sheet = _sheet(rec)
    blocked = sum(1 for l in result["lines"] if l["block"] and not l["is_header"])
    known = ""
    if rec.get("known"):
        lay = _layouts().get(rec.get("layout") or "") or {}
        known = (f'<p style="margin:.4rem 0 0;">Recognised a layout confirmed '
                 f'{int(lay.get("use_count") or 0)} time(s) before, and applied its '
                 f'column choices. <a href="{url_for("boqimport.preview", token=token)}">'
                 f'Change mapping</a></p>')
    red = ""
    if blocked:
        red = (f'<p style="margin:.4rem 0 0;color:#b91c1c;"><b>{blocked} line'
               f'{"s" if blocked != 1 else ""} need a quantity before this BOQ can be '
               f'saved.</b> The sheet gave it as something other than a number '
               f'(“R.O.”, “NA”, a sum written as text&hellip;). Those rows are marked '
               f'red. Type the quantity, or remove the line &mdash; a blank quantity '
               f'would be saved as 0, and an RA bill cannot claim against a line at 0.</p>')
    flags = ""
    if result["flags"]:
        flags = (f'<details{" open" if blocked else ""}><summary>{len(result["flags"])} '
                 f'flagged cell{"s" if len(result["flags"]) != 1 else ""}, by row</summary>'
                 f'{_flag_list(result["flags"])}</details>')
    cls = "imp-banner has-red" if blocked else "imp-banner"
    return (f'<div class="{cls}">&#128229; Imported from <b>{P.esc(rec.get("filename"))}</b>, '
            f'sheet “{P.esc(sheet.get("name"))}” &mdash; {c["lines"]} lines, '
            f'{c["headers"]} spec headers, {len(result["sections"])} section'
            f'{"s" if len(result["sections"]) != 1 else ""}; {c["totals_dropped"]} total '
            f'row{"s" if c["totals_dropped"] != 1 else ""} left out. '
            f'<b>Nothing has been saved.</b> Check the lines, fill in the project and '
            f'customer, then press Create BOQ &mdash; or just leave the page.'
            f'<p style="margin:.4rem 0 0;">{_totals_html(result["totals"])}</p>'
            f'{known}{red}{flags}</div>')


# =============================================================================
# ROUTES
# =============================================================================

@boqimport_bp.route("", methods=["GET", "POST"])
def upload():
    purge()
    if request.method == "GET":
        return _upload_page()

    try:
        data, filename = _read_upload()
        wb = SI.read(data, filename)
    except SI.Refused as refused:
        return _upload_page(refused.message)

    token, known = stage(wb, filename, _uid())
    if known:
        return redirect(url_for("boqimport.form", token=token), code=303)
    return redirect(url_for("boqimport.preview", token=token), code=303)


@boqimport_bp.route("/<token>", methods=["GET", "POST"])
def preview(token: str):
    purge()
    rec = _own(token)
    if rec is None or _grid(rec) is None:
        return _not_found()
    if request.method == "GET":
        return _preview_page(token, rec)

    # A different sheet: a fresh guess for it (or its known layout), and back
    # to the preview. The mapping posted with it belonged to the old sheet.
    try:
        wanted = int(request.form.get("sheet", rec.get("sheet_index") or 0))
    except (TypeError, ValueError):
        wanted = rec.get("sheet_index") or 0
    sheets = rec.get("sheets") or []
    if (wanted != rec.get("sheet_index") and 0 <= wanted < len(sheets)
            and sheets[wanted].get("staged") and rec["grid"][wanted] is not None):
        rec["sheet_index"] = wanted
        grid = rec["grid"][wanted]
        known_map, _lay = _known_mapping(grid)
        rec["mapping"] = known_map if known_map is not None else SI.guess_mapping(grid)
        rec["layout"] = SI.signature(grid)
        rec["known"] = False
        return redirect(url_for("boqimport.preview", token=token), code=303)

    grid = _grid(rec)
    posted = {k[4:]: v for k, v in request.form.items() if k.startswith("map_")}
    rec["mapping"] = SI.clean_mapping(grid, posted)

    if request.form.get("action") != "confirm":
        return redirect(url_for("boqimport.preview", token=token), code=303)

    problems = SI.mapping_problems(grid, rec["mapping"])
    if problems:
        return _preview_page(token, rec, problems=problems)
    refusal = too_large(editor_model(SI.build(grid, rec["mapping"])))
    if refusal:
        return _preview_page(token, rec, error=refusal)
    _upsert_layout(grid, rec["mapping"])
    rec["layout"] = SI.signature(grid)
    rec["confirmed"], rec["known"] = True, False
    return redirect(url_for("boqimport.form", token=token), code=303)


@boqimport_bp.route("/<token>/form")
def form(token: str):
    purge()
    rec = _own(token)
    if rec is None or _grid(rec) is None:
        return _not_found()
    if not (rec.get("confirmed") or rec.get("known")):
        return redirect(url_for("boqimport.preview", token=token), code=303)

    grid = _grid(rec)
    mapping = SI.clean_mapping(grid, rec.get("mapping") or {})
    problems = SI.mapping_problems(grid, mapping)
    if problems:
        rec["known"] = False
        return _preview_page(token, rec, problems=problems)
    result = SI.build(grid, mapping)
    model = editor_model(result)
    refusal = too_large(model)
    if refusal:
        rec["known"], rec["confirmed"] = False, False
        return _preview_page(token, rec, error=refusal)

    html = BQ.create_boq(imported={"boot": model, "prefill": {},
                                   "banner_html": _banner(token, rec, result)})
    # Consumed. A known layout keeps its row for the Change-mapping link; the
    # 24-hour purge takes it.
    if rec.get("confirmed"):
        _imports().pop(token, None)
    return html
