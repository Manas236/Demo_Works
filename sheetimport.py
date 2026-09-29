"""
sheetimport.py — read the client's own Excel BOQ, whatever its layout
=====================================================================
Built 29 September 2026 for **Import BOQ from Excel v1**, CLIENT_CHANGES.md §0,
thirty-fourth block.

**This module imports nothing from the app** — not `store`, not `pipeline`, not
`boq`. It is handed bytes and a filename and hands back plain dicts; the routes,
the staging collection and every word of HTML belong to `boqimport.py`. That is
what lets it be tested on workbooks built in memory, and what keeps a parser
from ever reaching into a record. `tests/test_import_directions.py` holds the
leaf. `openpyxl` and `xlrd` are imported INSIDE the two readers, never at module
level — `photo.py`'s arrangement for Pillow — so a server without them still
boots and `/boq/import` says the reader is unavailable.

What it guarantees, in the order a file meets it
------------------------------------------------
1. **The bytes decide the format, never the name.** `PK\\x03\\x04` is a zip and
   must be a macro-free Excel workbook; `D0 CF 11 E0` is an OLE2 compound file
   and must be an Excel 97-2003 workbook. Anything else — a CSV, a PDF, a
   renamed executable — is refused with a sentence. An `.xlsm`, and an `.xls`
   carrying a VBA project, are refused outright: nothing here runs a macro, but
   a macro-bearing file is not one this form takes.
2. **Size is bounded before anything is parsed.** 5 MB uploaded; for an .xlsx
   the zip's declared uncompressed sizes are summed first and the file is
   refused above 50 MB, so a zip bomb is refused by arithmetic rather than by
   running out of memory. (`zipfile` itself refuses a member that inflates past
   the size it declared.)
3. **XML goes through defusedxml.** openpyxl picks it up by itself when it is
   installed; an .xlsx is REFUSED while `openpyxl.xml.DEFUSEDXML` is False.
4. **Nothing is written to disk and the file is not kept.** It is read from a
   BytesIO and dropped. What survives is the staged GRID — cell values, trimmed
   to the used range — never the workbook.
5. **Formulas are read, never computed.** The value Excel saved is the value. A
   formula with no saved value is FLAGGED — never evaluated, never guessed.
6. **Nothing the user must decide is guessed.** A rate column that does not say
   which track it is on is left UNSET, so the user picks Supply or Installation.
   "R.O." in a quantity is left BLANK and flagged, never 0 — a 0 would hard-block
   the first real RA claim on that line. "9.3+1.5+6" is flagged, never added up.

⚠ **`item_no` is TEXT and only ever a display label.** A number is written the
way Excel displays it (`4.0999999999999996` becomes "4.1", a `0.00` format
keeps "1.10"), duplicates stay duplicates, and nothing here parses one into a
key. `line_id` is minted by `boq._clean_lines()` on save, like any typed line.

⚠ **Only the TOTAL quantity is read (v1).** Floor / area split columns and
separate take-off tabs are ignored — a decision, recorded in CLIENT_CHANGES.md.
"""

import datetime
import hashlib
import io
import json
import math
import re
import zipfile

# =============================================================================
# LIMITS — tune here, not in a branch
# =============================================================================

# The upload itself. Same ceiling as an attachment and a profile photo.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# An .xlsx is a zip of XML. Its declared uncompressed size is summed BEFORE
# openpyxl sees it; the client's largest real workbook is 2.1 MB inflated.
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024

# The staged grid, per sheet. A sheet past either is REFUSED, never truncated:
# a schedule cut at row 1,500 is a schedule missing its last lines with nothing
# on the page saying so.
MAX_GRID_ROWS = 1500
MAX_GRID_COLS = 40

# ⚠ **4,000, not the 500 the build brief named.** Twenty of the fifty-six
#   clauses in the client's own seeded schedule run past 500 characters (the
#   longest is 1,369), and a BOQ header line carries the whole specification
#   paragraph. A 500 cap would have cut the client's own clause text on import,
#   which INTRODUCTION.md §9 forbids. A cell longer than this is cut AND
#   flagged on its row — never silently.
MAX_CELL_CHARS = 4000

# How far a sheet is walked before it is refused as not a schedule. Counted in
# rows the reader yields, empty ones included, so a sheet formatted down to
# row 1,048,576 is refused in bounded time.
MAX_SCAN_ROWS = 100_000
MAX_SCAN_COLS = 2_000

# The whole staged workbook, in JSON characters. The selected sheet always
# fits (it is checked on its own); other sheets are staged while they fit and
# listed as not staged after that. `db.sync()` re-hashes every record on every
# request, so a staging row is paid for until it is deleted.
STAGE_BUDGET_CHARS = 2_000_000

# Where the header is looked for, and what counts as one.
HEADER_SCAN_ROWS = 40
MIN_HEADER_SCORE = 2
HEADER_LABEL_MAX = 60

# How many data rows the preview shows under the column dropdowns.
PREVIEW_ROWS = 20

# The totals check: the sheet's grand total against sum(qty x rate), per track.
TOTALS_TOLERANCE = 1.0

UNAVAILABLE = ("The Excel reader is not installed on this server. Ask whoever "
               "looks after it to run: pip install -r requirements.txt")

# =============================================================================
# THE TARGETS a column can be mapped to
# =============================================================================
#
# ⚠ **Six more than the build brief listed, each for a stated reason:**
#   `install_base_rate` / `install_escalation_pct` — the client's Sify sheet
#   carries an installation base rate, and the brief's own reproduction test
#   compares rates; `supply_amount` / `install_amount` — a two-track sheet has
#   one amount column per track, and the totals check is per track; `amount`
#   stays as the brief's single check-only column (one track, or the combined
#   total of both). None of the amount columns is imported — the form computes
#   amounts from quantity and rate, always.
TARGETS = (
    ("",                       "— ignore —"),
    ("item_no",                "Item No."),
    ("description",            "Description"),
    ("qty",                    "Quantity (total)"),
    ("unit",                   "Unit"),
    ("supply_base_rate",       "Supply · base rate"),
    ("escalation_pct",         "Supply · escalation %"),
    ("supply_rate",            "Supply · unit rate"),
    ("supply_amount",          "Supply · amount (check only)"),
    ("install_base_rate",      "Installation · base rate"),
    ("install_escalation_pct", "Installation · escalation %"),
    ("install_rate",           "Installation · unit rate"),
    ("install_amount",         "Installation · amount (check only)"),
    ("amount",                 "Amount (check only)"),
)
TARGET_KEYS = tuple(k for k, _l in TARGETS)
TARGET_LABEL = dict(TARGETS)

# A guessed column the user MUST decide. Never a valid target on confirm.
UNDECIDED = "?"

RATE_FIELDS = ("supply_base_rate", "escalation_pct", "supply_rate",
               "install_base_rate", "install_escalation_pct", "install_rate")
AMOUNT_FIELDS = ("supply_amount", "install_amount", "amount")
PCT_FIELDS = ("escalation_pct", "install_escalation_pct")


def available() -> dict:
    """{"xlsx": bool, "xls": bool} — whether each reader can run on this
    server. An .xlsx reader without defusedxml counts as unavailable, because
    `_read_xlsx()` refuses in that state."""
    out = {}
    try:
        import openpyxl.xml
        out["xlsx"] = bool(getattr(openpyxl.xml, "DEFUSEDXML", False))
    except ImportError:
        out["xlsx"] = False
    try:
        import xlrd  # noqa: F401
        out["xls"] = True
    except ImportError:
        out["xls"] = False
    return out


class Refused(Exception):
    """A file (or a sheet) this module will not read, with the sentence the
    operator is shown. Never carries a stack trace or a library's wording."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# =============================================================================
# SMALL HELPERS
# =============================================================================

def col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA. The column name the operator sees in Excel."""
    s, n = "", int(i) + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _norm(label) -> str:
    """A header cell, lower-cased and whitespace-collapsed."""
    return re.sub(r"\s+", " ", str(label or "")).strip().lower()


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _kind(grid: dict, ri: int, ci) -> str:
    if ci is None:
        return ""
    return (grid.get("kinds") or {}).get(f"{ri}:{ci}", "")


def _value(grid: dict, ri: int, ci):
    if ci is None:
        return None
    vals = grid["rows"][ri][1]
    return vals[ci] if ci < len(vals) else None


# =============================================================================
# 1. THE BYTES — format, size, macros
# =============================================================================

XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
# How the VBA storage is named in an OLE2 directory entry (UTF-16LE).
_VBA_OLE_NAME = "_VBA_PROJECT_CUR".encode("utf-16-le")

MACRO_REFUSAL = ("This workbook carries macros (.xlsm). Open it in Excel, "
                 "use Save As → Excel Workbook (.xlsx), and upload that copy.")


def sniff_format(data: bytes) -> str:
    """
    `"xlsx"` or `"xls"`, from the LEADING BYTES — or `Refused`.

    The filename and the browser's Content-Type are the uploader's to choose;
    the content is not. `attachment.sniff()`'s rule.
    """
    if data.startswith(XLSX_MAGIC):
        return "xlsx"
    if data.startswith(XLS_MAGIC):
        return "xls"
    raise Refused("That file is not an Excel workbook. Upload the BOQ as an "
                  ".xlsx or .xls file — a CSV, PDF or scanned sheet cannot be "
                  "read here.")


def _check_xlsx_container(data: bytes) -> None:
    """The zip-level refusals, all decided before openpyxl is called."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        raise Refused("That file looks like an .xlsx but it could not be "
                      "opened — it may be damaged. Open it in Excel, save it "
                      "again and upload the new copy.")
    total = sum(max(0, int(i.file_size)) for i in infos)
    if total > MAX_UNCOMPRESSED_BYTES:
        raise Refused(f"That workbook unpacks to {total / 1048576:.0f} MB, and "
                      f"the limit is {MAX_UNCOMPRESSED_BYTES // 1048576} MB. "
                      f"Save the BOQ sheet on its own as a new workbook and "
                      f"upload that.")
    names = [i.filename.lower() for i in infos]
    if any(n.endswith("vbaproject.bin") for n in names):
        raise Refused(MACRO_REFUSAL)
    try:
        ctypes_xml = zf.read("[Content_Types].xml").decode("utf-8", "replace").lower()
    except KeyError:
        raise Refused("That file is a zip archive but not an Excel workbook.")
    if "macroenabled" in ctypes_xml:
        raise Refused(MACRO_REFUSAL)
    if ("spreadsheetml.sheet.main+xml" not in ctypes_xml
            and "spreadsheetml.template.main+xml" not in ctypes_xml):
        raise Refused("That file is an Office document but not an Excel "
                      "workbook. Upload the BOQ as an .xlsx or .xls file.")


# =============================================================================
# 2. READING — each reader yields the same neutral shape
# =============================================================================
#
# A sheet is read into {row_number: {col_index: (value, kind)}} where value is
# a str, an int/float, or "" for a special cell, and kind is:
#
#   ""        an ordinary value
#   "error"   an Excel error (#VALUE!, #REF!, …) — value is its text
#   "date"    a date-formatted cell — value is its ISO text
#   "formula" a formula with NO saved value — value is ""
#   "pct"     a number formatted as a percentage (0.15 shown as 15%)
#   "dp:N"    a number formatted with N fixed decimals (item "1.10")
#   "bool"    TRUE / FALSE
#   "long"    text cut at MAX_CELL_CHARS

def _num_kind(number_format: str) -> str:
    fmt = str(number_format or "")
    if "%" in fmt:
        return "pct"
    m = re.fullmatch(r"0\.(0+)", fmt.strip())
    return f"dp:{len(m.group(1))}" if m else ""


def _text_cell(v: str):
    s = v if isinstance(v, str) else str(v)
    if not s.strip():
        return None
    if len(s) > MAX_CELL_CHARS:
        return s[:MAX_CELL_CHARS], "long"
    return s, ""


class _SheetTooBig(Exception):
    pass


class _Collector:
    """Accumulates one sheet's non-empty cells, refusing past the limits."""

    def __init__(self):
        self.cells = {}
        self.cols = set()

    def put(self, r: int, c: int, value, kind: str) -> None:
        row = self.cells.get(r)
        if row is None:
            if len(self.cells) >= MAX_GRID_ROWS:
                raise _SheetTooBig(
                    f"more than {MAX_GRID_ROWS:,} rows with something in them")
            row = self.cells[r] = {}
        row[c] = (value, kind)
        if c not in self.cols:
            self.cols.add(c)
            if len(self.cols) > MAX_GRID_COLS:
                raise _SheetTooBig(
                    f"more than {MAX_GRID_COLS} columns with something in them")


def _read_xlsx(data: bytes) -> list:
    """[(name, visibility, cells_or_refusal)] for every worksheet."""
    _check_xlsx_container(data)
    try:
        import openpyxl
        import openpyxl.xml
    except ImportError:
        raise Refused(UNAVAILABLE)
    if not getattr(openpyxl.xml, "DEFUSEDXML", False):
        # Fail closed. openpyxl would otherwise parse the workbook's XML with
        # the standard library, and this is a file somebody else wrote.
        raise Refused("The Excel reader on this server is missing its XML "
                      "safety layer (defusedxml), so .xlsx files are refused. "
                      "Ask whoever looks after the server to run: "
                      "pip install -r requirements.txt")

    try:
        wb_v = openpyxl.load_workbook(io.BytesIO(data), read_only=True,
                                      data_only=True, keep_links=False)
        wb_f = openpyxl.load_workbook(io.BytesIO(data), read_only=True,
                                      data_only=False, keep_links=False)
    except Exception as exc:                       # openpyxl raises many shapes
        raise Refused(_unreadable(exc, "an .xlsx"))

    out = []
    try:
        for ws_v, ws_f in zip(wb_v.worksheets, wb_f.worksheets):
            name = str(ws_v.title)
            vis = str(getattr(ws_v, "sheet_state", "visible") or "visible")
            try:
                out.append((name, vis, _xlsx_cells(ws_v, ws_f)))
            except _SheetTooBig as exc:
                out.append((name, vis, str(exc)))
    except Exception as exc:
        raise Refused(_unreadable(exc, "an .xlsx"))
    finally:
        for wb in (wb_v, wb_f):
            try:
                wb.close()
            except Exception:
                pass
    return out


def _xlsx_cells(ws_v, ws_f) -> dict:
    """One worksheet, read from the two parses in lockstep: values from the
    data-only parse, and "is this a formula" from the other. openpyxl cannot
    give both from one parse."""
    ws_v.reset_dimensions()
    ws_f.reset_dimensions()
    col = _Collector()
    f_rows = ws_f.iter_rows()
    for r, row_v in enumerate(ws_v.iter_rows(), start=1):
        row_f = next(f_rows, ())
        if r > MAX_SCAN_ROWS:
            raise _SheetTooBig(f"it runs past row {MAX_SCAN_ROWS:,}")
        if len(row_v) > MAX_SCAN_COLS:
            raise _SheetTooBig(f"a row runs past column {MAX_SCAN_COLS:,}")
        for c, cell in enumerate(row_v):
            v = cell.value
            if v is None:
                fc = row_f[c] if c < len(row_f) else None
                if fc is not None and getattr(fc, "data_type", None) == "f":
                    col.put(r, c, "", "formula")
                continue
            dt = getattr(cell, "data_type", None)
            if dt == "e":
                col.put(r, c, str(v), "error")
            elif isinstance(v, bool):
                col.put(r, c, "TRUE" if v else "FALSE", "bool")
            elif isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
                col.put(r, c, v.isoformat(), "date")
            elif isinstance(v, (int, float)):
                if not math.isfinite(v):
                    col.put(r, c, "#NUM!", "error")
                elif getattr(cell, "is_date", False):
                    col.put(r, c, str(v), "date")
                else:
                    col.put(r, c, v, _num_kind(getattr(cell, "number_format", "")))
            else:
                t = _text_cell(v)
                if t is not None:
                    col.put(r, c, t[0], t[1])
    return col


def _read_xls(data: bytes) -> list:
    """[(name, visibility, cells_or_refusal)] for every sheet of an .xls."""
    if _VBA_OLE_NAME in data:
        raise Refused(MACRO_REFUSAL.replace("(.xlsm)", "(a VBA project)"))
    try:
        import xlrd
    except ImportError:
        raise Refused(UNAVAILABLE)
    try:
        book = xlrd.open_workbook(file_contents=data, formatting_info=True,
                                  on_demand=True)
    except Exception as exc:                       # xlrd raises many shapes
        raise Refused(_unreadable(exc, "an Excel 97-2003 (.xls)"))

    vis_name = {0: "visible", 1: "hidden", 2: "veryHidden"}
    out = []
    try:
        for i in range(book.nsheets):
            sh = book.sheet_by_index(i)
            vis = vis_name.get(getattr(sh, "visibility", 0), "visible")
            try:
                out.append((str(sh.name), vis, _xls_cells(book, sh, xlrd)))
            except _SheetTooBig as exc:
                out.append((str(sh.name), vis, str(exc)))
            book.unload_sheet(i)
    except Exception as exc:
        raise Refused(_unreadable(exc, "an Excel 97-2003 (.xls)"))
    finally:
        try:
            book.release_resources()
        except Exception:
            pass
    return out


def _xls_cells(book, sh, xlrd):
    if sh.nrows > MAX_SCAN_ROWS:
        raise _SheetTooBig(f"it runs past row {MAX_SCAN_ROWS:,}")
    col = _Collector()
    for r in range(sh.nrows):
        n = sh.row_len(r)
        if n > MAX_SCAN_COLS:
            raise _SheetTooBig(f"a row runs past column {MAX_SCAN_COLS:,}")
        for c in range(n):
            t = sh.cell_type(r, c)
            if t in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                continue
            v = sh.cell_value(r, c)
            if t == xlrd.XL_CELL_TEXT:
                tc = _text_cell(v)
                if tc is not None:
                    col.put(r + 1, c, tc[0], tc[1])
            elif t == xlrd.XL_CELL_NUMBER:
                if not math.isfinite(v):
                    col.put(r + 1, c, "#NUM!", "error")
                else:
                    col.put(r + 1, c, v, _num_kind(_xls_format(book, sh, r, c)))
            elif t == xlrd.XL_CELL_DATE:
                try:
                    txt = xlrd.xldate_as_datetime(v, book.datemode).isoformat()
                except Exception:
                    txt = str(v)
                col.put(r + 1, c, txt, "date")
            elif t == xlrd.XL_CELL_BOOLEAN:
                col.put(r + 1, c, "TRUE" if v else "FALSE", "bool")
            elif t == xlrd.XL_CELL_ERROR:
                col.put(r + 1, c, xlrd.error_text_from_code.get(v, "#ERROR"), "error")
    return col


def _xls_format(book, sh, r, c) -> str:
    try:
        xf = book.xf_list[sh.cell_xf_index(r, c)]
        return book.format_map[xf.format_key].format_str
    except Exception:
        return ""


def _unreadable(exc, what: str) -> str:
    """The refusal for a file a reader choked on — never the library's words."""
    if type(exc).__module__.startswith("defusedxml"):
        return ("That workbook contains XML this reader refuses to process "
                "(entity or DTD declarations). Open it in Excel, save it as a "
                "new .xlsx and upload that copy.")
    return (f"That file could not be read as {what} workbook — it may be "
            f"damaged or password-protected. Open it in Excel, save it again "
            f"and upload the new copy.")


# =============================================================================
# 3. STAGING — the grid, trimmed to the used range
# =============================================================================

def _grid_of(col: _Collector) -> dict:
    """
    The collector as a staged grid.

    `cols` is the ORIGINAL 0-based column index of each kept column, so a
    column is always named by the letter the operator sees in Excel; `rows`
    carries the ORIGINAL row number for the same reason — a flag that says
    "row 57" has to mean row 57 of their sheet. Only rows and columns with
    something in them are kept.
    """
    cols = sorted(col.cols)
    pos = {c: i for i, c in enumerate(cols)}
    rows, kinds = [], {}
    for r in sorted(col.cells):
        vals = [None] * len(cols)
        for c, (v, k) in col.cells[r].items():
            ci = pos[c]
            vals[ci] = v
            if k:
                kinds[f"{len(rows)}:{ci}"] = k
        while vals and vals[-1] is None:
            vals.pop()
        rows.append([r, vals])
    grid = {"cols": cols, "rows": rows, "kinds": kinds}
    grid["header"] = detect_header(grid)
    return grid


def read(data: bytes, filename: str = "") -> dict:
    """
    Read an uploaded workbook into the staged shape, or raise `Refused`.

    Returns::

        {"format": "xlsx" | "xls",
         "sheets": [{"name", "visibility", "rows", "cols", "staged",
                     "refusal", "score"}, …],     # in workbook order
         "grid":   [grid | None, …],               # aligned with "sheets"
         "selected": index of the pre-selected sheet}

    ⚠ The pre-selected sheet is the VISIBLE sheet with the most rows carrying a
      number in both a quantity-like and a rate-like column. A hidden sheet is
      listed and may be chosen, and is never chosen for the operator.
    """
    if not data:
        raise Refused("That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise Refused(f"That file is {len(data) / 1048576:.1f} MB and the "
                      f"limit is {MAX_UPLOAD_BYTES // 1048576} MB. Save the BOQ "
                      f"sheet on its own as a new workbook and upload that.")
    fmt = sniff_format(data)
    if fmt == "xlsx" and str(filename or "").lower().endswith(".xlsm"):
        raise Refused(MACRO_REFUSAL)
    raw = _read_xlsx(data) if fmt == "xlsx" else _read_xls(data)
    return _assemble(fmt, raw)


def from_rows(sheets: list, fmt: str = "xlsx") -> dict:
    """
    `read()`'s result from plain rows — `[(name, visibility, [[cell, …], …])]`
    — with no workbook and no reader involved.

    It exists so a caller with no openpyxl (ABOUT.md §1's row-3 configuration)
    can still produce a staged workbook through the SAME staging, header,
    scoring and budget code `read()` uses: `tests/test_entity_fallbacks.py`'s
    sweep fixture is that caller. Cells are taken as plain values; there are
    no formats, dates or formulas to carry.
    """
    raw = []
    for name, vis, rows in sheets:
        col = _Collector()
        try:
            for r, vals in enumerate(rows, start=1):
                for c, v in enumerate(vals):
                    if v is None:
                        continue
                    if _is_number(v):
                        col.put(r, c, v, "")
                    else:
                        t = _text_cell(v)
                        if t is not None:
                            col.put(r, c, t[0], t[1])
        except _SheetTooBig as exc:
            raw.append((str(name), str(vis), str(exc)))
            continue
        raw.append((str(name), str(vis), col))
    return _assemble(fmt, raw)


def _assemble(fmt: str, raw: list) -> dict:
    """The per-sheet staging, scoring, pre-selection and budget that turn a
    reader's output into what `read()` returns."""
    sheets, grids = [], []
    for name, vis, cells in raw:
        entry = {"name": name, "visibility": vis, "rows": 0, "cols": 0,
                 "staged": False, "refusal": "", "score": 0, "qty_rows": 0}
        grid = None
        if isinstance(cells, str):
            entry["refusal"] = f"Not read: {cells}. Split the sheet and import each part."
        else:
            grid = _grid_of(cells)
            entry["rows"], entry["cols"] = len(grid["rows"]), len(grid["cols"])
            entry["score"], entry["qty_rows"] = _schedule_score(grid)
            entry["staged"] = bool(grid["rows"])
            if not grid["rows"]:
                entry["refusal"] = "Empty."
                grid = None
        sheets.append(entry)
        grids.append(grid)

    if not any(s["staged"] for s in sheets):
        why = "; ".join(f"{s['name']}: {s['refusal']}" for s in sheets) or "no sheets"
        raise Refused(f"No sheet in that workbook could be read ({why}).")

    selected = pick_sheet(sheets)

    # The budget. The selected sheet is checked on its own; the rest ride
    # while they fit, in workbook order, and are listed as not staged after.
    used = 0
    for i in [selected] + [j for j in range(len(sheets)) if j != selected]:
        if grids[i] is None:
            continue
        size = len(json.dumps(grids[i], ensure_ascii=False, separators=(",", ":")))
        if used + size > STAGE_BUDGET_CHARS:
            if i == selected:
                raise Refused(f"The sheet “{sheets[i]['name']}” holds more text "
                              f"than one import can carry. Split it into two "
                              f"sheets and import each.")
            sheets[i]["staged"] = False
            sheets[i]["refusal"] = ("Not held for preview — the workbook is too "
                                    "large to stage every sheet. Save this sheet "
                                    "on its own and import it.")
            grids[i] = None
            continue
        used += size
    return {"format": fmt, "sheets": sheets, "grid": grids, "selected": selected}


def pick_sheet(sheets: list) -> int:
    """
    The visible staged sheet with the highest schedule score; first wins a tie.

    ⚠ The score is the brief's — rows with a number in BOTH a quantity-like
      and a rate-like column — and `qty_rows` (rows with a quantity at all) only
      breaks a tie. Found on the client's own files: a workbook whose rate
      cells are empty scores 0 on every sheet, and the first sheet — its
      one-page SUMMARY — was chosen over the 131-row schedule behind it.

    Falls back to the first staged sheet, visible or not, only when no visible
    sheet could be staged at all.
    """
    def rank(s):
        return (s.get("score", 0), s.get("qty_rows", 0))

    best = None
    for i, s in enumerate(sheets):
        if s.get("staged") and s.get("visibility") == "visible":
            if best is None or rank(s) > rank(sheets[best]):
                best = i
    if best is None:
        best = next(i for i, s in enumerate(sheets) if s.get("staged"))
    return best


# =============================================================================
# 4. THE HEADER — where it is, and what each column probably is
# =============================================================================
#
# The keywords the brief named, plus four this pass added and records:
# "sl" (Sl. No. is on six of the client's own sheets), "specification",
# "material" / "labour" (the common names for the two tracks in Indian
# schedules). Nothing here reads a header longer than 60 characters: a long
# cell is data, not a column head.

_KW = {
    "sr":           re.compile(r"\bsr\b|\bs\.?\s?no\b|\bsl\b|\bserial\b"),
    "item":         re.compile(r"\bitems?\b"),
    "description":  re.compile(r"descr|particular|specification|name of (?:the )?(?:item|work)"),
    "qty":          re.compile(r"\bqty\b|quantit|\bqnty\b"),
    "unit":         re.compile(r"\bunits?\b|\buom\b|u\.o\.m"),
    "rate":         re.compile(r"\brates?\b"),
    "amount":       re.compile(r"\bamount\b|\bamt\b"),
    "supply":       re.compile(r"\bsupply\b|\bmaterial\b"),
    "installation": re.compile(r"install|\blabou?r\b|\berection\b"),
    "base":         re.compile(r"\bbase\b|\bbasic\b"),
    "esc":          re.compile(r"\besc\b|escal"),
}
_TOTAL_WORD = re.compile(r"\btotal\b")


def _hits(label: str) -> set:
    t = _norm(label)
    if not t or len(t) > HEADER_LABEL_MAX:
        return set()
    return {k for k, rx in _KW.items() if rx.search(t)}


def _labels(vals: list) -> list:
    out = []
    for v in vals:
        out.append(v if isinstance(v, str) else "")
    return out


def _score(labels: list) -> int:
    return sum(len(_hits(l)) for l in labels)


def _combine(upper: list, lower: list):
    """
    A two-row header, merged: "Supply" over "Rate | Amount" becomes
    "supply rate | supply amount".

    An upper label carries rightward across empty upper cells for as long as
    the lower row has a label — the shape a merged cell leaves in the grid.
    ⚠ Only when the upper row has TWO or more labels: a one-label upper row is
      a title ("BILL OF QUANTITIES"), and carrying it across every column would
      stamp "quantities" on all of them.
    ⚠ And only when the lower row is MADE OF heading words: no figure in it,
      and every label either a keyword, the word "total", or three characters
      at most (a floor code: "GF", "B1"). Found by the suite: the first DATA
      row, carrying "Rate Only" in its quantity, scored a keyword and was
      swallowed into the header — the line vanished with nothing said.
    """
    for v in lower:
        if _is_number(v):
            return None
        if isinstance(v, str) and v.strip():
            t = _norm(v)
            if not (_hits(t) or _TOTAL_WORD.search(t) or len(t) <= 3):
                return None
    up, lo = _labels(upper), _labels(lower)
    width = max(len(up), len(lo))
    up += [""] * (width - len(up))
    lo += [""] * (width - len(lo))
    if sum(1 for u in up if u.strip() and len(u) <= HEADER_LABEL_MAX) < 2:
        return None
    out, carry = [], ""
    for u, l in zip(up, lo):
        if u.strip():
            carry = u
        elif not l.strip():
            carry = ""
        out.append(f"{carry} {l}".strip() if u.strip() or l.strip() else "")
    return out


def detect_header(grid: dict) -> list:
    """
    `[top, bottom]` grid-row indexes of the header (equal for a one-row
    header), or `[]` when none scores at least MIN_HEADER_SCORE.

    The row — or adjacent two-row pair — in the first 40 sheet rows with the
    most keyword hits. A pair wins only when it beats both of its rows alone,
    so a header with a section row under it stays a one-row header.
    """
    rows = grid["rows"]
    best_score, best = 0, []
    for ri, (rnum, vals) in enumerate(rows):
        if rnum > HEADER_SCAN_ROWS:
            break
        s1 = _score(_labels(vals))
        cand_score, cand = s1, [ri, ri]
        if ri + 1 < len(rows) and rows[ri + 1][0] == rnum + 1:
            combined = _combine(vals, rows[ri + 1][1])
            if combined is not None:
                s2 = _score(combined)
                if s2 > max(s1, _score(_labels(rows[ri + 1][1]))):
                    cand_score, cand = s2, [ri, ri + 1]
        if cand_score > best_score:
            best_score, best = cand_score, cand
    return best if best_score >= MIN_HEADER_SCORE else []


def header_labels(grid: dict) -> dict:
    """{grid column index: the column's header text} — combined for a pair."""
    hdr = grid.get("header") or []
    if not hdr:
        return {}
    top = grid["rows"][hdr[0]][1]
    if hdr[1] != hdr[0]:
        labels = _combine(top, grid["rows"][hdr[1]][1]) or _labels(grid["rows"][hdr[1]][1])
    else:
        labels = _labels(top)
    return {ci: l for ci, l in enumerate(labels) if l.strip()}


def signature(grid: dict) -> str:
    """
    The LAYOUT SIGNATURE — sha256 of the normalised header texts and the
    column each sits in. Two uploads of the same template produce the same
    signature whatever their data, which is what lets a confirmed mapping be
    reused. "" when no header was found: a sheet with no header is never a
    known layout.
    """
    labels = header_labels(grid)
    if not labels:
        return ""
    cols = grid["cols"]
    payload = json.dumps(sorted((int(cols[ci]), _norm(l)) for ci, l in labels.items()),
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def guess_mapping(grid: dict) -> dict:
    """
    {str(Excel column index): target | "?" | ""} — a first guess the preview
    shows under every column, which the user confirms or changes.

    ⚠ **A rate column is given a TRACK only when its own header, or the band
      above it, names the track** ("Supply Rate", "Installation" over "Rate").
      A rate column that does not is left "?" — the user must choose Supply or
      Installation, and confirm refuses until they do. With one rate on the
      sheet that is the brief's rule exactly; with several it is the same rule
      applied to each.
    """
    labels = header_labels(grid)
    cols = grid["cols"]
    info = {}
    for ci, label in labels.items():
        h = _hits(label)
        track = ("supply" if "supply" in h else "install" if "installation" in h else "")
        info[ci] = (h, track, _norm(label))

    out = {str(c): "" for c in cols}
    taken = set()

    def put(ci, target):
        out[str(cols[ci])] = target
        if target and target != UNDECIDED:
            taken.add(target)

    order = sorted(info)
    # Item number: a serial column first; "Item" alone only when there is none
    # and it is not the description ("Item Description").
    for ci in order:
        h, _t, _l = info[ci]
        if "sr" in h and "description" not in h and "item_no" not in taken:
            put(ci, "item_no")
    for ci in order:
        h, _t, _l = info[ci]
        if (out[str(cols[ci])] == "" and "description" in h
                and "description" not in taken):
            put(ci, "description")
    if "item_no" not in taken:
        for ci in order:
            h, _t, _l = info[ci]
            if out[str(cols[ci])] == "" and "item" in h and not (h & {"rate", "amount", "qty", "unit"}):
                put(ci, "item_no")
                break
    # Quantity: the one that says "total" when there are several (floor /
    # area splits are ignored in v1); otherwise the first.
    qtys = [ci for ci in order if out[str(cols[ci])] == ""
            and "qty" in info[ci][0] and not (info[ci][0] & {"rate", "amount"})]
    if qtys:
        tot = [ci for ci in qtys if _TOTAL_WORD.search(info[ci][2])]
        put((tot or qtys)[0], "qty")
    for ci in order:
        h, _t, _l = info[ci]
        if (out[str(cols[ci])] == "" and "unit" in h
                and not (h & {"rate", "amount", "qty"}) and "unit" not in taken):
            put(ci, "unit")

    # Rates and escalations, per track.
    rates, escs = {}, {}
    for ci in order:
        h, track, _l = info[ci]
        if out[str(cols[ci])] != "":
            continue
        if "esc" in h:
            escs.setdefault(track, []).append(ci)
        elif "rate" in h and "amount" not in h:
            rates.setdefault(track, []).append(ci)
    for track in sorted(set(rates) | set(escs)):
        rs, es = rates.get(track, []), escs.get(track, [])
        if not track:
            # No track named anywhere near these columns: every one is the
            # user's decision.
            for ci in rs + es:
                put(ci, UNDECIDED)
            continue
        base_t = "supply_base_rate" if track == "supply" else "install_base_rate"
        esc_t = "escalation_pct" if track == "supply" else "install_escalation_pct"
        unit_t = "supply_rate" if track == "supply" else "install_rate"
        if es:
            put(es[0], esc_t)
            left = [ci for ci in rs if ci < es[0]]
            right = [ci for ci in rs if ci > es[0]]
            if left:
                put(left[-1], base_t)
            if right:
                put(right[0], unit_t)
        elif len(rs) >= 2 and any("base" in info[ci][0] for ci in rs):
            b = next(ci for ci in rs if "base" in info[ci][0])
            put(b, base_t)
            put(next(ci for ci in rs if ci != b), unit_t)
        elif rs:
            put(rs[0], unit_t)

    # Amounts — check only. One per track, and one without a track.
    for ci in order:
        h, track, label = info[ci]
        if out[str(cols[ci])] != "":
            continue
        is_amount = "amount" in h or (_TOTAL_WORD.search(label) and "qty" not in h)
        if not is_amount:
            continue
        t = ("supply_amount" if track == "supply"
             else "install_amount" if track == "install" else "amount")
        if t not in taken:
            put(ci, t)
    return out


def _schedule_score(grid: dict) -> tuple:
    """`(score, qty_rows)` — rows under the header with a number in the guessed
    quantity column AND in some rate-like column, and rows with a quantity at
    all. What `pick_sheet()` ranks by, in that order."""
    if not grid.get("header"):
        return 0, 0
    mapping = guess_mapping(grid)
    cols = grid["cols"]
    pos = {str(c): i for i, c in enumerate(cols)}
    qty = [pos[k] for k, t in mapping.items() if t == "qty"]
    rate_like = [pos[k] for k, t in mapping.items()
                 if t in RATE_FIELDS or t == UNDECIDED]
    if not qty:
        return 0, 0
    n = q = 0
    for ri in range(grid["header"][1] + 1, len(grid["rows"])):
        if not (_is_number(_value(grid, ri, qty[0])) and _kind(grid, ri, qty[0]) != "date"):
            continue
        q += 1
        if any(_is_number(_value(grid, ri, c)) for c in rate_like):
            n += 1
    return n, q


def data_start(grid: dict) -> int:
    """The first grid row under the header (0 when there is no header)."""
    hdr = grid.get("header") or []
    return hdr[1] + 1 if hdr else 0


# =============================================================================
# 5. THE MAPPING — what confirm refuses
# =============================================================================

def clean_mapping(grid: dict, posted: dict) -> dict:
    """A posted {column: target} reduced to known columns and known targets.
    An unknown target reads as ignore; "?" is kept so it can be refused."""
    out = {}
    for c in grid["cols"]:
        t = str(posted.get(str(c), "") or "")
        out[str(c)] = t if (t in TARGET_KEYS or t == UNDECIDED) else ""
    return out


def mapping_problems(grid: dict, mapping: dict) -> list:
    """Why this mapping cannot be confirmed yet — [] when it can."""
    probs = []
    for c in grid["cols"]:
        if mapping.get(str(c)) == UNDECIDED:
            probs.append(f"Column {col_letter(c)} looks like a rate but does not "
                         f"say which: choose Supply or Installation for it, or "
                         f"Ignore it.")
    seen = {}
    for c in grid["cols"]:
        t = mapping.get(str(c), "")
        if t and t != UNDECIDED:
            seen.setdefault(t, []).append(col_letter(c))
    for t, letters in seen.items():
        if len(letters) > 1:
            probs.append(f"{TARGET_LABEL[t]} is chosen for {len(letters)} columns "
                         f"({', '.join(letters)}). Keep one.")
    if "description" not in seen:
        probs.append("Choose the column that holds the Description.")
    if "qty" not in seen:
        probs.append("Choose the column that holds the Quantity. Only the total "
                     "quantity is imported; floor or area columns are left out.")
    return probs


# =============================================================================
# 6. THE ROWS — lines, headers, sections, totals, flags
# =============================================================================

_RATE_ONLY = re.compile(r"^\s*(?:r\s*\.?\s*o\s*\.?|i\s*\.?\s*r\s*\.?|r\s*/\s*o|rate\s*only)\s*$", re.I)
_NA = re.compile(r"^\s*(?:n\s*\.?\s*a\s*\.?|n\s*/\s*a|nil|-+|—|–)\s*$", re.I)
_DASH = re.compile(r"^\s*(?:-+|—|–)\s*$")
_ERROR_TEXT = re.compile(r"^\s*#(?:VALUE!|REF!|DIV/0!|N/A|NAME\?|NUM!|NULL!|SPILL!|CALC!)\s*$", re.I)
_NUMERIC_TEXT = re.compile(r"^\s*[-+]?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\s*$")
_ARITH = re.compile(r"^\s*\(?\s*\d+(?:\.\d+)?\s*\)?(?:\s*[-+*/xX×]\s*\(?\s*\d+(?:\.\d+)?\s*\)?)+\s*$")

_TOTAL_LABEL = re.compile(
    r"^\s*(?:grand\s*total|g\.?\s*total\b|sub\s*-?\s*total|total\b|"
    r"carried\s+(?:forward|over)|brought\s+forward|c\s*/\s*f\b|b\s*/\s*f\b)", re.I)
_GRAND = re.compile(r"grand\s*total|\bg\.?\s*total\b|total\s*\([^)]*\+[^)]*\)|net\s+total", re.I)
_PARTIAL = re.compile(r"sub\s*-?\s*total|carried|brought|c\s*/\s*f|b\s*/\s*f|total\s+of\s+\S", re.I)
# A label that is NOTHING BUT a total word. Such a row is a total even with no
# figure on it (its formula may have no saved value); any longer label —
# "Total flooding system" is a heading — has to carry a figure somewhere on
# the row before it is treated as a total and dropped.
_BARE_TOTAL = re.compile(r"^\s*(?:grand\s*|g\.?\s*|sub\s*-?\s*|net\s*)?total\s*[:.\-=>]*\s*$", re.I)
TOTAL_LABEL_MAX = 60

# A section code in the item column: "A", "B", "II", "SECTION B", "Part C".
# The prefix word is case-insensitive; the code itself must be CAPITALS, so a
# sub-item "a" or "ii" is never read as a section.
_SECTION_ITEM = re.compile(r"^(?:(?i:section|part|schedule|system)\s*[-:.]?\s*)?([A-Z]{1,2}|[IVX]{1,4})\s*[.):]?$")
_SECTION_WORD = re.compile(r"^(?:section|part|schedule)\s*[-:.]?\s*([A-Za-z0-9]{1,3})\b[\s.:\-–—]*(.*)$", re.I | re.S)
_SUB_LABEL = re.compile(r"^\(?(?:[a-z]{1,2}|[ivx]{1,4})\)?\.?$")

# Flag kinds. RED ones on the QUANTITY leave it blank and BLOCK the save on the
# form until somebody types a figure or removes the line; see boqimport.py and
# ABOUT.md §7 gap 42 for why a blank quantity would otherwise be saved as 0.
_FLAG_TEXT = {
    "rate_only": "Rate only on source sheet — quantity left blank",
    "na":        "“{raw}” on the source sheet — left blank",
    "error":     "Excel error {raw} — left blank",
    "date":      "a date ({raw}) where a number belongs — left blank",
    "formula":   "formula, no saved value — open and save in Excel, then import again",
    "arith":     "sum written as text ({raw}) — not worked out; left blank",
    "text":      "text “{raw}” where a number belongs — left blank",
    "long":      "text longer than {n:,} characters — cut; paste the rest by hand",
    "no_item":   "no item number on the source sheet — the form will ask for one",
    "no_desc":   "figures but no description — the form will ask for one",
    "amount_only": "an amount with no quantity or rate — imported as a header; the amount is not carried",
    "item_date": "the item number is a date on the source sheet ({raw}) — left blank",
    "dup_section": "section {raw} appears again — this one is named {new}; rename it if you like",
}


def _numeric(value, kind: str, field: str):
    """
    `(number | None, flag_kind | "")` for one quantity or rate cell.

    Blank is `(None, "")`. A number is itself — ×100 when it is a percentage
    in an escalation column, which is how the client's Sify sheet stores 15%
    and how `tools/gen_demo_data.py` read it. Everything else is `None` and a
    flag: this function never turns a word into a figure, and the only text it
    reads as a number is a plain number with thousands separators.
    """
    if kind == "formula":
        return None, "formula"
    if kind == "error":
        return None, "error"
    if kind == "date":
        return None, "date"
    if value is None:
        return None, ""
    if _is_number(value):
        v = float(value)
        if kind == "pct" and field in PCT_FIELDS:
            v = v * 100.0
        return v, ""
    s = str(value).strip()
    if not s:
        return None, ""
    if field == "qty" and _RATE_ONLY.match(s):
        return None, "rate_only"
    if field != "qty" and _DASH.match(s):
        # The client's "-" in a rate cell: negotiated directly, not escalated —
        # blank, and NOT a flag. `boq._opt_num()` reads it the same way.
        return None, ""
    if _ERROR_TEXT.match(s):
        return None, "error"
    if _NA.match(s):
        return None, "na"
    if _NUMERIC_TEXT.match(s):
        return float(s.replace(",", "")), ""
    if _ARITH.match(s):
        return None, "arith"
    return None, "text"


def _item_text(value, kind: str) -> str:
    """An item number as the text Excel shows. Never a float."""
    if value is None or kind in ("formula", "error", "date"):
        return ""
    if _is_number(value):
        if kind.startswith("dp:"):
            return f"{float(value):.{int(kind[3:])}f}"
        f = float(value)
        return str(int(f)) if f.is_integer() else f"{f:.10g}"
    return str(value).strip()


def _plain(value, kind: str) -> str:
    """Any other text cell: description, unit."""
    if value is None or kind == "formula":
        return ""
    if _is_number(value):
        return _item_text(value, kind)
    return str(value).strip()


def _is_caps_title(s: str) -> bool:
    letters = [ch for ch in s if ch.isalpha()]
    return (3 <= len(letters) and len(s) <= 120 and "\n" not in s
            and all(not ch.islower() for ch in letters))


def _section_of(item: str, desc: str):
    """(code, title) when this row is a section break, else None. Code "" means
    "assign the next free letter"."""
    m = _SECTION_ITEM.match(item)
    if item and m:
        return m.group(1), desc
    if not item:
        m = _SECTION_WORD.match(desc)
        if m:
            return m.group(1).upper(), (m.group(2).strip() or desc)
        if desc and _is_caps_title(desc):
            return "", desc
    return None


def _is_child(item: str, head: str) -> bool:
    if not head or item == head or not item.startswith(head):
        return False
    nxt = item[len(head)]
    return nxt in ".-/ (" or (head[-1].isdigit() and nxt.isalpha())


def build(grid: dict, mapping: dict) -> dict:
    """
    The confirmed mapping applied to every row under the header.

    Returns::

        {"sections": [{"code", "title"}],
         "lines":    [{"row", "item_no", "parent_item_no", "section",
                       "is_header", "description", "unit", "qty",
                       <rate fields>, "flags": [...], "block": bool}],
         "flags":    [{"row", "col", "field", "raw", "kind", "message",
                       "severity"}],
         "counts":   {"lines", "headers", "sections", "totals_dropped", "flagged"},
         "totals":   {...}}

    Numbers are floats or None — shaping them for the form is `boqimport.py`'s
    job. `block` is True on a line whose QUANTITY was left blank by a flag.
    """
    cols = grid["cols"]
    pos = {str(c): i for i, c in enumerate(cols)}
    col_of = {}
    for c in cols:
        t = mapping.get(str(c), "")
        if t and t != UNDECIDED and t not in col_of:
            col_of[t] = pos[str(c)]
    mapped_cis = set(col_of.values())

    flags, lines, sections, totals_rows = [], [], [], []
    counts = {"lines": 0, "headers": 0, "sections": 0, "totals_dropped": 0, "flagged": 0}

    def flag(rnum, field, kind, raw="", severity="amber", **extra):
        msg = _FLAG_TEXT[kind].format(raw=raw, n=MAX_CELL_CHARS, **extra)
        ci = col_of.get(field)
        f = {"row": rnum, "col": col_letter(cols[ci]) if ci is not None else "",
             "field": TARGET_LABEL.get(field, field), "raw": raw, "kind": kind,
             "message": msg, "severity": severity}
        flags.append(f)
        return f

    # "\x00" is the placeholder for the section lines sit in before the sheet
    # names one; it is replaced by a real code once every code is known.
    DEFAULT = "\x00"
    cur_section = DEFAULT
    headers_by_section = {}       # section -> [(item_no, line index)]
    family = None                 # the most recent header, while its family runs

    for ri in range(data_start(grid), len(grid["rows"])):
        rnum = grid["rows"][ri][0]

        def cell(field):
            ci = col_of.get(field)
            return _value(grid, ri, ci), _kind(grid, ri, ci)

        iv, ik = cell("item_no")
        item = _item_text(iv, ik)
        dv, dk = cell("description")
        desc = _plain(dv, dk)
        uv, uk = cell("unit")
        unit = _plain(uv, uk)

        nums, nflags, raws = {}, {}, {}
        for field in ("qty",) + RATE_FIELDS + AMOUNT_FIELDS:
            v, k = cell(field)
            n, fk = _numeric(v, k, field)
            nums[field], nflags[field] = n, fk
            raws[field] = "" if v is None else str(v)

        # ── Total rows: dropped, remembered for the check ──────────────────
        labels = [x for x in (item, desc, unit) if x]
        for ci, v in enumerate(grid["rows"][ri][1]):
            if ci not in mapped_cis and isinstance(v, str) and v.strip():
                labels.append(v.strip())
        total_label = next((l for l in labels if len(l) <= TOTAL_LABEL_MAX
                            and _TOTAL_LABEL.match(l)), "")
        qty_ci, item_ci = col_of.get("qty"), col_of.get("item_no")
        has_figure = any(
            (_is_number(v) and ci not in (qty_ci, item_ci)) or _kind(grid, ri, ci) == "formula"
            for ci, v in enumerate(grid["rows"][ri][1]))
        if (total_label and nums["qty"] is None and not nflags["qty"]
                and (has_figure or _BARE_TOTAL.match(total_label))):
            totals_rows.append({"row": rnum, "label": total_label,
                                "amounts": {f: nums[f] for f in AMOUNT_FIELDS}})
            counts["totals_dropped"] += 1
            continue

        has_numbers = nums["qty"] is not None or any(nums[f] is not None for f in RATE_FIELDS)
        has_num_flags = bool(nflags["qty"]) or any(nflags[f] for f in RATE_FIELDS)

        if not (item or desc or has_numbers or has_num_flags):
            continue

        # ── Section rows ────────────────────────────────────────────────────
        if not has_numbers and not has_num_flags:
            sec = _section_of(item, desc)
            if sec is not None:
                code, title = sec
                sections.append({"code": code, "title": title, "row": rnum})
                cur_section = len(sections) - 1      # resolved to a code below
                family = None
                counts["sections"] += 1
                continue

        line = {"row": rnum, "item_no": item, "parent_item_no": "",
                "section": cur_section, "is_header": False,
                "description": desc, "unit": unit, "qty": None,
                "flags": [], "block": False}
        for f in RATE_FIELDS:
            line[f] = None

        if ik == "date" and iv is not None:
            line["flags"].append(flag(rnum, "item_no", "item_date", raw=str(iv))["message"])
        if dk == "long":
            line["flags"].append(flag(rnum, "description", "long")["message"])

        if not has_numbers and not has_num_flags:
            if not desc:
                continue                              # an item number and nothing else
            line["is_header"] = True
            if any(nums[f] is not None for f in AMOUNT_FIELDS):
                line["flags"].append(flag(rnum, "description", "amount_only")["message"])
        else:
            line["qty"] = nums["qty"]
            for f in RATE_FIELDS:
                line[f] = nums[f]
            for field in ("qty",) + RATE_FIELDS:
                fk = nflags[field]
                if not fk:
                    continue
                red = field == "qty"
                f = flag(rnum, field, fk, raw=raws[field],
                         severity="red" if red else "amber")
                line["flags"].append(f"{TARGET_LABEL[field]}: {f['message']}")
                if red:
                    line["block"] = True
            if not desc:
                line["flags"].append(flag(rnum, "description", "no_desc")["message"])

        if not item and (line["is_header"] or desc):
            line["flags"].append(flag(rnum, "item_no", "no_item")["message"])

        # ── Parent: the specification hierarchy, never a BOM ────────────────
        heads = headers_by_section.setdefault(cur_section, [])
        parent = ""
        for h_item, _idx in heads:
            if _is_child(item, h_item) and len(h_item) > len(parent):
                parent = h_item
        if not parent and family is not None and (not item or _SUB_LABEL.match(item)):
            parent = family
        if not line["is_header"] and item and not parent and family is not None:
            family = None                             # a new top-level line ends it
        line["parent_item_no"] = parent

        if line["is_header"]:
            counts["headers"] += 1
            if item:
                heads.append((item, len(lines)))
                family = item
        else:
            counts["lines"] += 1
        if line["flags"]:
            counts["flagged"] += 1
        lines.append(line)

    # ── Section codes ──────────────────────────────────────────────────────
    # The sheet's own codes are reserved first; lines above the first section
    # row take the first free letter (so "A" when the sheet never uses it);
    # a caps-title section with no code takes the next free one after that.
    explicit = [s["code"] for s in sections if s["code"]]
    used = set()
    letters = [chr(c) for c in range(ord("A"), ord("Z") + 1)]

    def next_free():
        for l in letters:
            if l not in used and l not in explicit:
                return l
        n = 1
        while f"S{n}" in used:
            n += 1
        return f"S{n}"

    default_code = ""
    if any(l["section"] == DEFAULT for l in lines):
        default_code = next_free()
        used.add(default_code)

    codes = []
    for s in sections:
        code = s["code"] or next_free()
        if code in used:
            base, n = code, 2
            while f"{base}-{n}" in used:
                n += 1
            new = f"{base}-{n}"
            flag(s["row"], "item_no", "dup_section", raw=base, new=new)
            code = new
        used.add(code)
        codes.append(code)
    out_sections = []
    if default_code:
        out_sections.append({"code": default_code, "title": ""})
    for s, code in zip(sections, codes):
        out_sections.append({"code": code, "title": s["title"]})
    for l in lines:
        l["section"] = default_code if l["section"] == DEFAULT else codes[l["section"]]
    if not out_sections:
        out_sections.append({"code": "A", "title": ""})

    return {"sections": out_sections, "lines": lines, "flags": flags,
            "counts": counts,
            "totals": _totals_check(lines, totals_rows, col_of)}


def _totals_check(lines: list, totals_rows: list, col_of: dict) -> dict:
    """
    sum(qty × rate) per track against the sheet's own grand total.

    The grand total is the last row labelled "Grand Total" (or "TOTAL (A+B+C)");
    failing that, the one plain "Total" row when there is exactly one. Several
    plain totals and no grand one is reported as no total found — picking one
    would be a guess about which section's figure it is.
    """
    grand = None
    for t in totals_rows:
        if _GRAND.search(t["label"]):
            grand = t
    if grand is None:
        plain = [t for t in totals_rows if not _PARTIAL.search(t["label"])]
        if len(plain) == 1:
            grand = plain[0]

    computed = {"supply": 0.0, "install": 0.0}
    for l in lines:
        if l["is_header"] or l["qty"] is None:
            continue
        if l.get("supply_rate") is not None:
            computed["supply"] += l["qty"] * l["supply_rate"]
        if l.get("install_rate") is not None:
            computed["install"] += l["qty"] * l["install_rate"]

    tracks = [t for t in ("supply", "install") if f"{t}_rate" in col_of]
    checks = []
    for t in tracks:
        col = f"{t}_amount" if f"{t}_amount" in col_of else (
            "amount" if "amount" in col_of and len(tracks) == 1 else "")
        checks.append({"track": t, "computed": round(computed[t], 2), "column": col})
    if len(tracks) == 2 and "amount" in col_of and not any(c["column"] == "amount" for c in checks):
        checks.append({"track": "both", "column": "amount",
                       "computed": round(computed["supply"] + computed["install"], 2)})

    status = "no_total" if grand is None else "no_figure"
    for c in checks:
        sheet = grand["amounts"].get(c["column"]) if (grand and c["column"]) else None
        c["sheet"] = None if sheet is None else round(float(sheet), 2)
        if c["sheet"] is None:
            c["status"] = "no_figure"
            continue
        c["difference"] = round(c["computed"] - c["sheet"], 2)
        c["status"] = "match" if abs(c["difference"]) <= TOTALS_TOLERANCE else "mismatch"
    if grand is not None:
        judged = [c for c in checks if c["status"] in ("match", "mismatch")]
        if judged:
            status = "mismatch" if any(c["status"] == "mismatch" for c in judged) else "match"
    return {"status": status, "row": grand["row"] if grand else None,
            "label": grand["label"] if grand else "", "checks": checks,
            "total_rows": len(totals_rows)}
