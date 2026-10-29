"""
payimport.py — import the client's monthly attendance workbook
==============================================================
Blueprint  : payimport_bp
Mounted at : /payroll/import  (registered in app.py)

Routes
------
  GET,POST  /payroll/import/                    — upload a workbook
  GET       /payroll/import/preview/<id>        — what it would do; changes nothing
  POST      /payroll/import/commit/<id>         — do it
  GET,POST  /payroll/import/delete/<id>         — GET confirms, POST takes an import back out

CLIENT_CHANGES.md §0, the FIFTY-FIFTH block (29 October 2026). ⚠ **CHARGED NEW
SCOPE, price not yet agreed.**

The client's sheet, as received (`ATTENDANCE DATA.xlsx`, September 2026)
------------------------------------------------------------------------
* A title row — ``ATTENDANCE FOR THE MONTH OF SEPTEMPER - 2026`` (their
  spelling): the month is read from the first three letters of the month word
  and the operator CONFIRMS it on the preview.
* A header row: ``SR.NO | NAME | DESIGNATION | SITE``, then one cell per
  calendar day holding the day number, every THIRD column, then ``Days | OT |
  OTCD | TOTAL DAYS | PER DAY SALARY | TOTAL SALARY | ADV | BALANCE | EXTRA EXP
  | LOAN | ACTUAL SALARY | BALANCE LOAN``.
* Each day is three columns: present (1 / 0.5 / 0), overtime hours, and a
  third nobody uses. Paid leave is a CELL COMMENT ("GANPATI PAID LEAVE") on a 1.

⚠ **EVERY COLUMN IS FOUND BY ITS HEADER TEXT, NEVER BY ITS LETTER.** Their real
master (the October tab their payslip links to) has 31 days, so every column
after the days sits three to the right of the September file's. The day count
must be 28–31 and may not exceed the confirmed month.

⚠ **BLANK IS NOT 0.** A blank day is a day nobody marked — people who joined
mid-month have leading blanks — and it writes nothing. A 0 writes an ABSENT
marking. A cell holding only spaces is blank. The client's standing rule from
the BOQ import, "blank comes in blank, 0 comes in as 0".

⚠ **NAMES ARE MATCHED EXACTLY** — trimmed, inner spaces collapsed, case
ignored, and nothing else. Their sheet carries "GUDDU" and "GUDDU KUMAR" on
two sites; a fuzzy match would merge two people's wages. An unmatched row is
SKIPPED unless the operator chooses "create" or names the person.

⚠ **THE MONEY COLUMNS** (Manas, 29 October 2026): PER DAY SALARY fills a BLANK
rate only, and a different rate is shown with an unticked box; ADV, EXTRA EXP
and LOAN become that month's ledger entries dated its last day; BALANCE LOAN
seeds an opening loan dated its 1st, only for somebody with no loan entries
yet. The derived columns (Days, TOTAL SALARY, ACTUAL SALARY …) are NEVER
imported — the app computes them, and the preview sets its figure beside the
sheet's cached ACTUAL SALARY so a difference is seen before anything is written.

⚠ **A DAY ALREADY MARKED IN THE APP IS NEVER OVERWRITTEN** —
`attendance.import_marking()` refuses it and the result counts it as skipped.

⚠ **ONE IMPORT PER MONTH.** Every record written carries the import's id; a
month already imported is refused until that import is taken back out, and
taking it out is refused once a payslip for that month is issued.
"""

import calendar
import io
import re
import uuid

from flask import Blueprint, redirect, request, url_for

import address as AD
import attendance as AT
import sheetimport as SI
import auth
import employee as EMP
import payroll as PAY
from store import STORE

payimport_bp = Blueprint("payimport", __name__, url_prefix="/payroll/import")

MAX_UPLOAD_BYTES = SI.MAX_UPLOAD_BYTES
HEADER_SEARCH_ROWS = 12
# Four leading columns, three a day for 31 days, a dozen totals, and room.
SHEET_MAX_COLS = 160

# The named headers, normalised. Only the INPUT columns are read as data; the
# one derived column read is ACTUAL SALARY, and only for the reconciliation.
H_NAME, H_DESIG, H_SITE = "name", "designation", "site"
H_RATE, H_ADV, H_EXTRA = "per day salary", "adv", "extra exp"
H_LOAN, H_BAL_LOAN, H_ACTUAL = "loan", "balance loan", "actual salary"

MONTHS = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}

PAID_LEAVE_MARK = "paid leave"

STAGED, COMMITTED, REMOVED = "staged", "committed", "removed"


def imports() -> dict:
    return STORE.setdefault("pay_imports", {})


def norm(text) -> str:
    """Trim, collapse inner whitespace, case-fold. The ONLY normalisation."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _number(v):
    """A float, or None for a blank. Raises ValueError on text."""
    if _blank(v):
        return None
    if isinstance(v, bool):
        raise ValueError(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", "").strip())


def _esc(v) -> str:
    return PAY._esc(v)


# =============================================================================
# READING THE WORKBOOK — pure, no STORE
# =============================================================================

def month_from_title(text) -> str:
    """
    'ATTENDANCE FOR THE MONTH OF SEPTEMPER - 2026' → '2026-09', or ''.

    The first word whose first three letters name a month, and a four-digit
    year. Their own spelling ("SEPTEMPER") is why it is three letters and not
    the whole word — and why the operator confirms the month on the preview.
    """
    month = year = None
    for w in re.findall(r"[A-Za-z]+|\d{4}", str(text or "")):
        if w.isdigit():
            year = int(w)
        elif month is None and len(w) >= 3 and w[:3].lower() in MONTHS:
            month = MONTHS[w[:3].lower()]
    return f"{year:04d}-{month:02d}" if month and year else ""


class _Sheet:
    """
    One staged grid from `sheetimport.read()`, addressed the way the client's
    Excel is: 1-based row numbers and 0-based ORIGINAL column indices. A cell
    the reader did not keep (an empty column) reads as None.
    """

    def __init__(self, grid: dict, notes: dict):
        self.pos = {c: i for i, c in enumerate(grid["cols"])}
        self.rows = {r: vals for r, vals in grid["rows"]}
        self.order = [r for r, _ in grid["rows"]]
        self.notes = notes

    def get(self, r, c):
        i = self.pos.get(c)
        vals = self.rows.get(r) or []
        return vals[i] if i is not None and i < len(vals) else None

    def width(self):
        return (max(self.pos) + 1) if self.pos else 0


def _find_header(sheet: _Sheet) -> int:
    for r in sheet.order[:HEADER_SEARCH_ROWS]:
        for c in range(sheet.width()):
            if norm(sheet.get(r, c)) == H_NAME:
                return r
    return 0


def parse(workbook_bytes: bytes, filename: str = "") -> dict:
    """
    `{"month_guess", "days", "rows", "problems", "sites"}` from one workbook.

    ⚠ **Read through `sheetimport.py`**, the one module allowed to read a
    workbook: its size limits, its macro and zip-bomb refusals and its
    defusedxml rule all apply. The sheet used is the first one carrying a NAME
    header. Never raises on a bad sheet — every problem is a sentence in
    `problems`, and a sheet with a fatal one comes back with no rows.
    """
    out = {"filename": filename, "month_guess": "", "days": 0, "rows": [],
           "problems": [], "sites": []}
    try:
        staged = SI.read(workbook_bytes, filename, max_cols=SHEET_MAX_COLS)
    except SI.Refused as exc:
        out["problems"].append(str(exc))
        return out
    sheet, hr = None, 0
    for i, grid in enumerate(staged["grid"]):
        if grid is None:
            continue
        cand = _Sheet(grid, {})
        hr = _find_header(cand)
        if hr:
            sheet = _Sheet(grid, SI.comments(workbook_bytes, i))
            break
    if sheet is None:
        out["problems"].append("No NAME header in the first rows of any sheet "
                               "— this is not the attendance sheet.")
        return out

    for r in sheet.order:
        if r >= hr:
            break
        for c in range(sheet.width()):
            guess = month_from_title(sheet.get(r, c))
            if guess:
                out["month_guess"] = guess
                break
        if out["month_guess"]:
            break

    named, day_cols = {}, {}
    for c in range(sheet.width()):
        v = sheet.get(hr, c)
        key = norm(v)
        if key and key not in named:
            named[key] = c
        if isinstance(v, (int, float)) and not isinstance(v, bool) \
                and float(v).is_integer() and 1 <= int(v) <= 31:
            day_cols[int(v)] = c
        elif isinstance(v, str) and v.strip().isdigit() and 1 <= int(v) <= 31:
            day_cols[int(v.strip())] = c

    missing = [h for h in (H_NAME, H_SITE) if h not in named]
    if missing:
        out["problems"].append(f"Missing header(s): {', '.join(missing).upper()}.")
        return out
    n = len(day_cols)
    if n < 28 or n > 31 or sorted(day_cols) != list(range(1, n + 1)):
        out["problems"].append(f"The day columns run 1–{n} with gaps or out of "
                               f"range; a month has 28 to 31 days.")
        return out
    out["days"] = n

    def col(h):
        return named.get(h)

    sites = []
    for r in [x for x in sheet.order if x > hr]:
        raw_name = sheet.get(r, col(H_NAME))
        if _blank(raw_name):
            break
        row = {"line": r, "name": re.sub(r"\s+", " ", str(raw_name)).strip(),
               "designation": str(sheet.get(r, col(H_DESIG)) or "").strip()
               if col(H_DESIG) is not None else "",
               "site": re.sub(r"\s+", " ", str(sheet.get(r, col(H_SITE))
                                                or "")).strip(),
               "days": [], "problems": [], "money": {}}
        for d in range(1, n + 1):
            c = day_cols[d]
            pv, ov, third = sheet.get(r, c), sheet.get(r, c + 1), sheet.get(r, c + 2)
            if not _blank(third):
                row["problems"].append(f"day {d}: a value in the third column "
                                       f"({third!r}) — not imported")
            try:
                present = _number(pv)
                ot = _number(ov)
            except ValueError:
                row["problems"].append(f"day {d}: {pv!r}/{ov!r} is not a number")
                continue
            if present is None:
                if ot:
                    row["problems"].append(f"day {d}: overtime on an unmarked "
                                           f"day — not imported")
                continue
            note = str(sheet.notes.get((r, c)) or "").strip()
            if present == 1 and PAID_LEAVE_MARK in norm(note):
                status = AT.PAID_LEAVE
            elif present == 1:
                status = AT.PRESENT
            elif present == 0.5:
                status = AT.HALF
            elif present == 0:
                status = AT.ABSENT
            else:
                row["problems"].append(f"day {d}: {present:g} is not 1, 0.5 or 0")
                continue
            ot = ot or 0.0
            if ot < 0 or ot > AT.MAX_OT_HOURS:
                row["problems"].append(f"day {d}: {ot:g} overtime hours")
                continue
            row["days"].append({"day": d, "status": status, "ot": ot,
                                "note": note[:200]})
        for key, h in (("rate", H_RATE), ("advance", H_ADV), ("travel", H_EXTRA),
                       ("loan", H_LOAN), ("balance_loan", H_BAL_LOAN),
                       ("actual", H_ACTUAL)):
            if col(h) is None:
                continue
            try:
                v = _number(sheet.get(r, col(h)))
            except ValueError:
                row["problems"].append(f"{h.upper()}: not a number")
                v = None
            if v is not None and v < 0 and key != "actual":
                row["problems"].append(f"{h.upper()}: negative")
                v = None
            row["money"][key] = v
        if row["site"] and row["site"] not in sites:
            sites.append(row["site"])
        out["rows"].append(row)
    out["sites"] = sites
    return out


# =============================================================================
# MATCHING AND THE APP'S OWN FIGURE — still nothing written
# =============================================================================

def match_employee(name: str) -> dict:
    """The one employee whose name normalises equal, or {} (also when two do)."""
    key = norm(name)
    hits = [e for e in EMP.employees().values() if norm(e.get("name")) == key]
    return hits[0] if len(hits) == 1 else {}


def app_net(row: dict, month: str) -> float:
    """
    What the app would pay for this row, priced by attendance's own
    `labour_cost_of()` on the row's days — never by arithmetic here.
    """
    rate = row["money"].get("rate") or 0.0
    synthetic = [{"status": d["status"], "ot_hours": d["ot"], "day_rate": rate}
                 for d in row["days"]]
    wages = AT.labour_cost_of(synthetic)["total"]
    m = row["money"]
    return round(wages + (m.get("travel") or 0) - (m.get("advance") or 0)
                 - (m.get("loan") or 0), 2)


def month_imported(month: str) -> dict:
    for rec in imports().values():
        if rec.get("month") == month and rec.get("status") == COMMITTED:
            return rec
    return {}


def site_choices() -> list:
    """
    `[(value, label, address_label)]` — every book site, and each project at
    it as its own choice, so a site carrying several projects cannot be picked
    without picking the project (`attendance.resolve_project()`'s rule).
    """
    out = []
    for a in sorted((STORE.get("addresses") or {}).values(),
                    key=lambda a: str(a.get("label") or "").lower()):
        if a.get("type") not in AD.SITE_TYPES or a.get("archived"):
            continue
        label = str(a.get("label") or "")
        projects = AT.projects_on_site(a["id"])
        if not projects:
            out.append((f"{a['id']}|", label, label))
        for p in projects:
            out.append((f"{a['id']}|{p['id']}", f"{label} — {p.get('name')}",
                        label))
    return out


def preselect(site: str, choices: list) -> str:
    """
    The one choice whose ADDRESS LABEL equals the sheet's SITE exactly (trimmed
    only — `employee.resolve_site()`'s rule), or "". Never a near match, and
    never when that address offers more than one choice.
    """
    hits = [v for v, _, addr in choices if addr.strip() == site.strip()]
    return hits[0] if len(hits) == 1 else ""


def resolve_choice(value: str) -> tuple:
    """`(site_fields, project_fields, error)` for one `addr|project` value."""
    aid, _, pid = str(value or "").partition("|")
    label = EMP.site_label_of(aid)
    if not label:
        return {}, {}, "choose a site from the address book"
    candidates = {p["id"]: p for p in AT.projects_on_site(aid)}
    if pid:
        p = candidates.get(pid)
        if not p:
            return {}, {}, "that project is not at that site"
        proj = {"project_id": p["id"], "project_name": str(p.get("name") or "")}
    elif len(candidates) > 1:
        return {}, {}, "several projects are at that site — choose one"
    elif len(candidates) == 1:
        p = next(iter(candidates.values()))
        proj = {"project_id": p["id"], "project_name": str(p.get("name") or "")}
    else:
        proj = {"project_id": "", "project_name": ""}
    return ({"site": label, EMP.SITE_ADDRESS_FIELD: aid,
             EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK}, proj, "")


# =============================================================================
# THE WRITE
# =============================================================================

def commit(rec: dict, form) -> tuple:
    """`(summary, error)`. Writes markings, ledger entries and new employees."""
    month = PAY.valid_month(form.get("month"))
    if not month:
        return {}, "Confirm the month."
    y, m = int(month[:4]), int(month[5:7])
    if rec["days"] > calendar.monthrange(y, m)[1]:
        return {}, (f"The sheet has {rec['days']} days and "
                    f"{PAY.month_label(month)} has fewer — check the month.")
    if month_imported(month):
        return {}, (f"{PAY.month_label(month)} was already imported. Take that "
                    f"import out first.")

    mapping = {}
    for i, site in enumerate(rec["sites"]):
        sf, pf, err = resolve_choice(form.get(f"site_{i}"))
        if err:
            return {}, f"Site “{site}”: {err}."
        mapping[site] = (sf, pf)

    batch = rec["id"]
    lo, hi = PAY.month_bounds(month)
    summary = {"markings": 0, "skipped_days": 0, "entries": 0, "created": 0,
               "rates_filled": 0, "rates_updated": 0, "rows_skipped": 0,
               "loan_mismatch": []}
    for i, row in enumerate(rec["rows"]):
        choice = (form.get(f"emp_{i}") or "").strip()
        if not choice:
            summary["rows_skipped"] += 1
            continue
        sf, pf = mapping.get(row["site"], ({}, {}))
        sheet_rate = row["money"].get("rate")
        if choice == "new":
            data, err = EMP._validate({
                "name": row["name"], "designation": row["designation"],
                "day_rate": "" if sheet_rate is None else str(sheet_rate),
                "site_id": sf.get(EMP.SITE_ADDRESS_FIELD, ""), "active": "1"})
            if err:
                return {}, f"Row {row['line']} ({row['name']}): {err}"
            person = EMP.employees()[EMP.create_record(data)]
            summary["created"] += 1
        else:
            person = EMP.employees().get(choice)
            if not person:
                return {}, f"Row {row['line']}: that employee no longer exists."
            if sheet_rate is not None and not person.get("day_rate") \
                    and not EMP.is_pre_day_rate(person):
                person["day_rate"] = round(sheet_rate, 2)
                summary["rates_filled"] += 1
            elif sheet_rate is not None and form.get(f"rate_{i}") \
                    and round(sheet_rate, 2) != round(float(person.get("day_rate") or 0), 2):
                person["day_rate"] = round(sheet_rate, 2)
                person.pop(EMP.RATE_MODEL_FIELD, None)
                person.pop("monthly_salary", None)
                summary["rates_updated"] += 1

        for d in row["days"]:
            day = f"{month}-{d['day']:02d}"
            rid, err = AT.import_marking(person, day, d["status"], d["ot"],
                                         sf, pf, batch, d.get("note", ""))
            if rid:
                summary["markings"] += 1
            else:
                summary["skipped_days"] += 1

        money = row["money"]
        for key, kind, date in (("advance", PAY.ADVANCE, hi),
                                ("travel", PAY.TRAVEL, hi),
                                ("loan", PAY.LOAN_DEDUCTION, hi)):
            amt = money.get(key)
            if amt:
                _write_entry(person, kind, amt, date, batch, rec["filename"])
                summary["entries"] += 1
        bal = money.get("balance_loan")
        if bal:
            has_loan = any(e.get("type") in PAY.LOAN_UP + (PAY.LOAN_DEDUCTION,)
                           and not str(e.get("source") or "").endswith(batch)
                           for e in PAY.entries_of(person["id"]))
            if has_loan:
                derived = PAY.loan_figures(person["id"], month)["opening"]
                if round(derived, 2) != round(bal, 2):
                    summary["loan_mismatch"].append(
                        f"{person.get('name')}: sheet {bal:,.2f}, ledger "
                        f"{derived:,.2f}")
            else:
                _write_entry(person, PAY.OPENING_LOAN, bal, lo, batch,
                             rec["filename"])
                summary["entries"] += 1

    rec.update({"status": COMMITTED, "month": month, "committed_at": PAY._now(),
                "committed_by": PAY._user_name(), "summary": summary})
    return summary, ""


def _write_entry(person, kind, amount, date, batch, filename):
    eid = str(uuid.uuid4())
    PAY.entries()[eid] = {
        "id": eid, "employee_id": person["id"],
        "employee_name": str(person.get("name") or ""), "date": date,
        "type": kind, "amount": round(float(amount), 2),
        "note": f"imported from {filename}"[:500],
        "source": PAY.IMPORT_PREFIX + batch,
        "created_at": PAY._now(), "created_by": PAY._user_name(),
        "updated_at": PAY._now()}


def batch_entries(batch) -> list:
    key = PAY.IMPORT_PREFIX + str(batch or "")
    return [e for e in PAY.entries().values() if e.get("source") == key] \
        if batch else []


def issued_blocker(rec: dict) -> dict:
    """An issued slip in this import's month for anybody this import touched."""
    people = {r.get("employee_id") for r in AT.batch_markings(rec["id"])}
    people |= {e.get("employee_id") for e in batch_entries(rec["id"])}
    for s in PAY.slips().values():
        if s.get("month") == rec.get("month") and s.get("status") == PAY.ISSUED \
                and s.get("employee_id") in people:
            return s
    return {}


def remove(rec: dict) -> tuple:
    """`(counts, error)` — take one committed import back out whole."""
    if rec.get("status") != COMMITTED:
        return {}, "Only a committed import can be taken out."
    blocker = issued_blocker(rec)
    if blocker:
        return {}, ("A payslip for this month is issued and was drawn from this "
                    "import. Cancel it first.")
    markings = AT.remove_batch(rec["id"])
    gone = [e["id"] for e in batch_entries(rec["id"])]
    for eid in gone:
        PAY.entries().pop(eid, None)
    rec.update({"status": REMOVED, "removed_at": PAY._now(),
                "removed_by": PAY._user_name()})
    return {"markings": markings, "entries": len(gone)}, ""


# =============================================================================
# THE PAGES
# =============================================================================

def _rec_or_back(id):
    rec = imports().get(id)
    if not rec:
        return None, redirect(url_for("payimport.upload",
                                      msg="That import no longer exists.",
                                      type="error"))
    return rec, None


@payimport_bp.route("/", methods=["GET", "POST"])
def upload():
    error = ""
    if request.method == "POST":
        f = request.files.get("workbook")
        data = f.read(MAX_UPLOAD_BYTES + 1) if f else b""
        if not data:
            error = "Choose the attendance workbook (.xlsx)."
        elif len(data) > MAX_UPLOAD_BYTES:
            error = "That file is larger than an attendance sheet should be."
        else:
            parsed = parse(data, (f.filename or "")[:120])
            if not parsed["rows"]:
                error = " ".join(parsed["problems"]) or "No employee rows found."
            else:
                sid = str(uuid.uuid4())
                parsed.update({"id": sid, "status": STAGED,
                               "month": parsed["month_guess"],
                               "uploaded_at": PAY._now(),
                               "uploaded_by": PAY._user_name()})
                imports()[sid] = parsed
                return redirect(url_for("payimport.preview", id=sid))

    done = sorted(imports().values(), key=lambda r: str(r.get("uploaded_at")),
                  reverse=True)
    rows = "".join(
        f'<tr><td>{_esc(r.get("uploaded_at"))}</td><td>{_esc(r.get("filename"))}</td>'
        f'<td>{_esc(PAY.month_label(r.get("month") or ""))}</td>'
        f'<td>{_esc(r.get("status"))}</td><td>'
        + (f'<a href="{url_for("payimport.preview", id=r["id"])}">Open</a>'
           if r.get("status") == STAGED else "")
        + (f' <a href="{url_for("payimport.delete_import", id=r["id"])}">Take out</a>'
           if r.get("status") == COMMITTED and auth.has_perm("payroll.delete")
           else "")
        + '</td></tr>' for r in done[:30])
    body = f"""
  {PAY._alert(error)}{PAY._flash()}
  <div class="page-top"><h1>Import attendance from Excel</h1>
    <a class="btn btn-ghost" href="{url_for('payroll.payroll_register')}">&#8592; Payslips</a></div>
  <div class="pay-note">The client's monthly attendance sheet: one row per
    person, three columns per day (present 1 / 0.5 / 0, overtime hours, unused),
    then PER DAY SALARY, ADV, EXTRA EXP, LOAN and BALANCE LOAN. Columns are found
    by their headings. <b>Nothing is written until you confirm the preview</b>,
    and a day already marked in the app is never overwritten.</div>
  <form method="POST" enctype="multipart/form-data" class="form-section">
    <input type="file" name="workbook" accept=".xlsx" required/>
    <button class="btn">Read it</button>
  </form>
  <div class="pay-card"><table class="pay-tbl">
    <tr><th>Uploaded</th><th>File</th><th>Month</th><th>Status</th><th></th></tr>
    {rows or '<tr><td colspan="5">Nothing imported yet.</td></tr>'}
  </table></div>"""
    return PAY._shell("Import attendance", body)


@payimport_bp.route("/preview/<id>")
def preview(id):
    rec, back = _rec_or_back(id)
    if back:
        return back
    if rec.get("status") != STAGED:
        return redirect(url_for("payimport.upload",
                                msg="That import is no longer waiting.",
                                type="error"))
    month = PAY.valid_month(request.args.get("month")) or rec.get("month") or ""
    already = month_imported(month) if month else {}
    choices = site_choices()

    site_rows = ""
    for i, site in enumerate(rec["sites"]):
        pick = preselect(site, choices)
        opts = ['<option value="">— choose —</option>'] + [
            f'<option value="{_esc(v)}"{" selected" if v == pick else ""}>'
            f'{_esc(label)}</option>' for v, label, _ in choices]
        site_rows += (f'<tr><td><b>{_esc(site)}</b></td><td><select name="site_{i}" '
                      f'required>{"".join(opts)}</select></td></tr>')

    people = sorted(EMP.employees().values(),
                    key=lambda e: str(e.get("name") or "").lower())
    emp_rows = ""
    for i, row in enumerate(rec["rows"]):
        hit = match_employee(row["name"])
        opts = [f'<option value="">— skip this row —</option>',
                '<option value="new">Create a new employee</option>']
        opts += [f'<option value="{_esc(e["id"])}"{" selected" if hit and e["id"] == hit["id"] else ""}>'
                 f'{_esc(e.get("name"))}{" (" + _esc(e.get("code")) + ")" if e.get("code") else ""}</option>'
                 for e in people]
        m = row["money"]
        rate = m.get("rate")
        rate_cell = "&mdash;" if rate is None else PAY._money(rate)
        if hit and rate is not None and hit.get("day_rate") and \
                round(rate, 2) != round(float(hit.get("day_rate") or 0), 2):
            rate_cell += (f'<br><label><input type="checkbox" name="rate_{i}"/> '
                          f'replace {PAY._money(hit.get("day_rate"))}</label>')
        paid = sum(AT.share_of(d["status"]) for d in row["days"])
        ot = sum(d["ot"] for d in row["days"] if d["status"] in AT.OT_STATUSES)
        net = app_net(row, month)
        actual = m.get("actual")
        diff = (actual is not None and round(actual, 2) != round(net, 2))
        conflicts = 0
        if hit and month:
            marked = {r.get("date") for r in AT.month_markings(hit["id"], month)}
            conflicts = sum(1 for d in row["days"]
                            if f"{month}-{d['day']:02d}" in marked)
        notes = list(row["problems"])
        if conflicts:
            notes.append(f"{conflicts} day(s) already marked in the app — skipped")
        if m.get("loan") and not m.get("balance_loan"):
            notes.append("a loan deduction with no BALANCE LOAN")
        emp_rows += f"""
      <tr{' style="background:#fff3e0"' if diff or notes else ''}>
        <td>{_esc(row['name'])}<span class="pay-sub">{_esc(row['site'])}</span></td>
        <td><select name="emp_{i}">{''.join(opts)}</select></td>
        <td class="num">{len(row['days'])} / {PAY._days(paid)}</td>
        <td class="num">{PAY._days(ot)}</td>
        <td class="num">{rate_cell}</td>
        <td class="num">{PAY._money(m.get('advance'))} / {PAY._money(m.get('travel'))}
          / {PAY._money(m.get('loan'))} / {PAY._money(m.get('balance_loan'))}</td>
        <td class="num">{PAY._money(net)}{f'<br><b>sheet {PAY._money(actual)}</b>' if diff else ''}</td>
        <td>{_esc('; '.join(notes))}</td>
      </tr>"""

    warn = ""
    if not rec.get("month_guess"):
        warn += '<div class="pay-warn">The month could not be read from the title — set it below.</div>'
    if already:
        warn += (f'<div class="pay-warn">{_esc(PAY.month_label(month))} is already '
                 f'imported. Committing is refused until that import is taken out.</div>')
    problems = "".join(f"<li>{_esc(p)}</li>" for p in rec.get("problems", []))
    body = f"""
  {PAY._flash()}
  <div class="page-top"><h1>Check the import &mdash; {_esc(rec.get('filename'))}</h1>
    <a class="btn btn-ghost" href="{url_for('payimport.upload')}">&#8592; Back</a></div>
  {warn}
  {f'<div class="pay-warn"><ul>{problems}</ul></div>' if problems else ''}
  <div class="pay-note"><b>Nothing has been written.</b> {rec['days']} day columns,
    {len(rec['rows'])} rows. A blank day writes nothing; 0 writes an absence; 0.5 a
    half day; a 1 carrying a "paid leave" comment, paid leave. Names are matched
    exactly &mdash; an unmatched row is skipped unless you choose. The app's net
    is priced by the muster's own arithmetic; where the sheet's ACTUAL SALARY
    differs it is shown in bold.</div>
  <form method="POST" action="{url_for('payimport.commit_import', id=id)}">
    <div class="form-section">
      <div class="section-title">Month</div>
      <input type="month" name="month" required value="{_esc(month)}"/>
    </div>
    <div class="form-section">
      <div class="section-title">Where each SITE in the sheet is</div>
      <table class="pay-tbl">{site_rows}</table>
    </div>
    <div class="pay-card"><table class="pay-tbl">
      <tr><th>Sheet row</th><th>Employee</th><th class="num">Marked / paid days</th>
          <th class="num">OT hrs</th><th class="num">Day rate</th>
          <th class="num">Adv / travel / loan ded. / loan owed</th>
          <th class="num">App net</th><th>Notes</th></tr>
      {emp_rows}
    </table></div>
    <button class="btn">Import</button>
  </form>"""
    return PAY._shell("Check the import", body)


@payimport_bp.route("/commit/<id>", methods=["POST"])
def commit_import(id):
    rec, back = _rec_or_back(id)
    if back:
        return back
    if rec.get("status") != STAGED:
        return redirect(url_for("payimport.upload",
                                msg="That import is no longer waiting.",
                                type="error"))
    summary, error = commit(rec, request.form)
    if error:
        return redirect(url_for("payimport.preview", id=id,
                                month=request.form.get("month"),
                                msg=error, type="error"))
    msg = (f"Imported: {summary['markings']} day(s) marked, "
           f"{summary['skipped_days']} skipped as already marked, "
           f"{summary['entries']} ledger entr(ies), {summary['created']} new "
           f"employee(s), {summary['rows_skipped']} row(s) skipped.")
    if summary["loan_mismatch"]:
        msg += " Loan differs from the ledger for: " + "; ".join(
            summary["loan_mismatch"])
    return redirect(url_for("payroll.payroll_register", month=rec["month"],
                            msg=msg, type="success"))


@payimport_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_import(id):
    """GET confirms, POST destroys — Owner-only (auth.OWNER_ONLY)."""
    rec, back = _rec_or_back(id)
    if back:
        return back
    error = ""
    if request.method == "POST":
        counts, error = remove(rec)
        if not error:
            return redirect(url_for("payimport.upload",
                                    msg=(f"Taken out: {counts['markings']} "
                                         f"marking(s), {counts['entries']} "
                                         f"ledger entr(ies). Employees it "
                                         f"created are kept."),
                                    type="success"))
    body = f"""
  {PAY._alert(error)}
  <div class="page-top"><h1>Take this import out?</h1></div>
  <div class="pay-note">{_esc(rec.get('filename'))},
    {_esc(PAY.month_label(rec.get('month') or ''))}:
    {len(AT.batch_markings(id))} marking(s) and {len(batch_entries(id))} ledger
    entr(ies) it wrote are deleted. Days marked by hand, and employees it
    created, are kept. Refused once a payslip for the month is issued.</div>
  <form method="POST"><button class="btn">Take it out</button>
    <a class="btn btn-ghost" href="{url_for('payimport.upload')}">Back</a></form>"""
    return PAY._shell("Take an import out", body)
