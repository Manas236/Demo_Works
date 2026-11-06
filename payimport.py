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
import pipeline as P
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


# ⚠ **EVERY TAB, ONE TAB PER SITE** (6 November 2026, CLIENT_CHANGES.md §0
#   **sixty-eighth** block). The client keeps one tab per site; a worker who
#   moved during the month is on several tabs, and their day cells on each tab
#   are their days AT THAT SITE. A tab's site is its SITE column where filled,
#   otherwise the TAB NAME — and a tab name that names no site ("Sheet2",
#   "OCTOBER 2026", "ATTENDANCE") is not used. Where a tab of a workbook with
#   more than one tab then has rows with no site at all, the parse STOPS and
#   says so: which tab is which site is not guessed.

GENERIC_TAB = re.compile(r"^(sheet|tab)\s*\d*$", re.I)
NOT_A_SITE_WORDS = {"attendance", "salary", "muster", "summary", "total",
                    "payroll", "master"}


def _is_month_word(w: str) -> bool:
    for name in MONTHS_FULL:
        if w in (name, name[:3], "sept") or (len(w) >= 5 and name.startswith(w[:5])):
            return True
    return False


MONTHS_FULL = ["january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december"]


def tab_site(tab_name) -> str:
    """
    The site a TAB NAME names, or `""` when it names none: blank, a default
    name (`Sheet1`, `Tab 2`), or a name made of a month, a year or words like
    ATTENDANCE / SALARY. Trimmed and spaces collapsed, nothing else.
    """
    name = re.sub(r"\s+", " ", str(tab_name or "")).strip()
    if not name or GENERIC_TAB.match(name):
        return ""
    words = re.findall(r"[a-z]+|\d+", name.lower())
    if all(w.isdigit() or _is_month_word(w) or w in NOT_A_SITE_WORDS
           or w in ("for", "the", "of", "month") for w in words):
        return ""
    return name


def parse(workbook_bytes: bytes, filename: str = "") -> dict:
    """
    `{"month_guess", "days", "rows", "problems", "sites", "tabs", "workers"}`
    from one workbook — EVERY visible tab carrying a NAME header.

    ⚠ **Read through `sheetimport.py`**, the one module allowed to read a
    workbook: its size limits, its macro and zip-bomb refusals and its
    defusedxml rule all apply. Never raises on a bad sheet — every problem is a
    sentence in `problems`, and a sheet with a fatal one comes back with no
    rows.

    `tabs` says, per tab, where its site came from — `"column"` (the SITE
    column), `"tab"` (the tab name), `"mixed"`, or `"none"` — so the preview
    reports which layout the workbook uses. A HIDDEN tab is listed and not
    read: an old copy kept out of sight would otherwise be counted twice.
    """
    out = {"filename": filename, "month_guess": "", "days": 0, "rows": [],
           "problems": [], "sites": [], "tabs": [], "workers": []}
    try:
        staged = SI.read(workbook_bytes, filename, max_cols=SHEET_MAX_COLS)
    except SI.Refused as exc:
        out["problems"].append(str(exc))
        return out
    metas = staged.get("sheets") or []
    found = []
    for i, grid in enumerate(staged["grid"]):
        if grid is None:
            continue
        meta = metas[i] if i < len(metas) else {}
        hr = _find_header(_Sheet(grid, {}))
        if not hr:
            continue
        name = str(meta.get("name") or f"Sheet{i + 1}")
        if str(meta.get("visibility") or "visible") != "visible":
            out["tabs"].append({"name": name, "rows": 0, "site_from": "hidden",
                                "site": "", "_at": i})
            continue
        found.append((name, _Sheet(grid, SI.comments(workbook_bytes, i)), hr, i))
    if not found:
        out["problems"].append("No NAME header in the first rows of any sheet "
                               "— this is not the attendance sheet.")
        return out

    days_seen = set()
    for name, sheet, hr, at in found:
        tab = _parse_tab(sheet, hr, name, len(found) > 1)
        if tab["fatal"]:
            out["problems"].extend(tab["problems"])
            out["rows"] = []
            return out
        out["problems"].extend(tab["problems"])
        if not out["month_guess"]:
            out["month_guess"] = tab["month_guess"]
        days_seen.add(tab["days"])
        out["tabs"].append({"name": name, "rows": len(tab["rows"]),
                            "site_from": tab["site_from"],
                            "site": tab_site(name), "_at": at})
        out["rows"].extend(tab["rows"])
    if len(days_seen) > 1:
        out["problems"].append(
            "The tabs do not agree on how many days the month has ("
            + ", ".join(str(d) for d in sorted(days_seen)) + ") — check them.")
        out["rows"] = []
        return out
    out["days"] = days_seen.pop()
    out["tabs"].sort(key=lambda t: t.pop("_at"))
    for row in out["rows"]:
        if row["site"] and row["site"] not in out["sites"]:
            out["sites"].append(row["site"])
    out["workers"] = group_workers(out["rows"], out["problems"])
    return out


def _parse_tab(sheet: "_Sheet", hr: int, tab_name: str, many: bool) -> dict:
    """One tab's rows, read exactly as the single-sheet parser always read
    them, each carrying its `tab` and its site (SITE column, else tab name)."""
    out = {"fatal": False, "problems": [], "rows": [], "days": 0,
           "month_guess": "", "site_from": "none"}
    where = f"Tab “{tab_name}”: " if many else ""
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

    # ⚠ The SITE column is required only where the tab NAME cannot stand in.
    tab_named = tab_site(tab_name)
    missing = [h for h in (H_NAME, H_SITE) if h not in named
               and not (h == H_SITE and tab_named)]
    if missing:
        out["problems"].append(f"{where}Missing header(s): "
                               f"{', '.join(missing).upper()}.")
        out["fatal"] = True
        return out
    n = len(day_cols)
    if n < 28 or n > 31 or sorted(day_cols) != list(range(1, n + 1)):
        out["problems"].append(f"{where}The day columns run 1–{n} with gaps or "
                               f"out of range; a month has 28 to 31 days.")
        out["fatal"] = True
        return out
    out["days"] = n

    def col(h):
        return named.get(h)

    sources = set()
    for r in [x for x in sheet.order if x > hr]:
        raw_name = sheet.get(r, col(H_NAME))
        if _blank(raw_name):
            break
        cell = (re.sub(r"\s+", " ", str(sheet.get(r, col(H_SITE)) or "")).strip()
                if col(H_SITE) is not None else "")
        site, src = (cell, "column") if cell else (tab_named, "tab" if tab_named else "none")
        sources.add(src)
        row = {"line": r, "tab": tab_name,
               "name": re.sub(r"\s+", " ", str(raw_name)).strip(),
               "designation": str(sheet.get(r, col(H_DESIG)) or "").strip()
               if col(H_DESIG) is not None else "",
               "site": site, "site_from": src,
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
        out["rows"].append(row)

    out["site_from"] = (sources.pop() if len(sources) == 1
                        else "mixed" if sources else "none")
    # ⚠ STOP, never guess: a tab of a several-tab workbook whose rows carry no
    #   site at all cannot be told apart from the others.
    if many and any(row["site_from"] == "none" for row in out["rows"]):
        out["problems"].append(
            f"{where}rows with no SITE, and the tab name does not name a site — "
            f"the import cannot tell which site these days were at. Fill the "
            f"SITE column or rename the tab to the site, and upload again.")
        out["fatal"] = True
    return out


# =============================================================================
# ONE WORKER ACROSS TABS — one worker-month (§0 sixty-eighth block)
# =============================================================================

def group_workers(rows: list, problems: list) -> list:
    """
    `[{"name", "rows": [row index …]}]` — the rows that are ONE person.

    Rows on different tabs whose names normalise equal (`norm()`, the exact
    rule `match_employee()` uses) are one worker: one employee pick, one
    month of markings, one set of ledger lines, one payslip. ⚠ A name that
    appears TWICE ON ONE TAB is two rows the sheet itself keeps apart, so it
    is never merged — every row of that name stays its own, and it is said.
    """
    by_name, order = {}, []
    for i, row in enumerate(rows):
        key = norm(row["name"])
        if key not in by_name:
            by_name[key] = []
            order.append(key)
        by_name[key].append(i)
    out = []
    for key in order:
        idx = by_name[key]
        tabs = [rows[i].get("tab", "") for i in idx]
        if len(set(tabs)) < len(tabs):
            problems.append(f"“{rows[idx[0]]['name']}” appears more than once "
                            f"on one tab — those rows are not merged.")
            out.extend({"name": rows[i]["name"], "rows": [i]} for i in idx)
        else:
            out.append({"name": rows[idx[0]]["name"], "rows": idx})
    return out


def workers_of(rec: dict) -> list:
    """The stored grouping, or one worker per row for an import staged before
    the grouping existed."""
    return rec.get("workers") or [{"name": r["name"], "rows": [i]}
                                  for i, r in enumerate(rec["rows"])]


def worker_days(rec: dict, worker: dict) -> tuple:
    """
    `(days, clashes)` — the worker's days across their tabs.

    `days` is `[(row index, day dict)]`, one per calendar day; `clashes` is
    `[{"day", "tabs"}]` for every day marked on TWO OR MORE tabs.

    ⚠ **A day on two tabs is imported on NEITHER.** One person is on one site
    on one day (CC-2 C5); two marks for one day are a mistake in the sheet,
    and picking one would put the wage on a site nobody chose — and adding
    both would pay the day twice. The preview flags it; the commit skips it
    and says so; it can be marked by hand once resolved, and the import never
    overwrites a marked day.
    """
    seen = {}
    for i in worker["rows"]:
        for d in rec["rows"][i]["days"]:
            seen.setdefault(d["day"], []).append((i, d))
    days, clashes = [], []
    for day in sorted(seen):
        hits = seen[day]
        if len(hits) == 1:
            days.append(hits[0])
        else:
            clashes.append({"day": day,
                            "tabs": [rec["rows"][i].get("tab", "") or "the sheet"
                                     for i, _ in hits]})
    return days, clashes


def linked_clashes(rec: dict, links: dict) -> dict:
    """
    `{first row index: [{"day", "tabs", "with"}]}` — the days that two or more
    sheet ROWS LINKED TO ONE EMPLOYEE both mark.

    `links` is `{first row index: employee id}` — the operator's picks (or,
    on the preview, the picks the page is showing). `""` and `"new"` link
    nothing: a new employee is a new person per row.

    ⚠ **The same rule as `worker_days()`, one step further out** (6 November
      2026, CLIENT_CHANGES.md §0 seventy-first block). `group_workers()`
      merges rows whose names normalise EQUAL; two spellings of one person
      (*PUSHKAR MISHRA* / *PUSHKAR MISRA*) stay two workers, and once both are
      picked as the same employee a day marked under each used to be written
      ONCE, from whichever row came first — a site chosen by row order. Now
      it is what a day on two tabs under one spelling is: flagged on the
      preview and imported on NEITHER.
    """
    by_emp = {}
    for w in workers_of(rec):
        first = w["rows"][0]
        eid = str(links.get(first) or "").strip()
        if eid and eid != "new":
            by_emp.setdefault(eid, []).append(w)
    out = {}
    for eid, ws in by_emp.items():
        if len(ws) < 2:
            continue
        seen = {}
        for w in ws:
            for i, d in worker_days(rec, w)[0]:
                seen.setdefault(d["day"], []).append((w, i))
        for day, hits in sorted(seen.items()):
            if len({id(w) for w, _i in hits}) < 2:
                continue
            tabs = [rec["rows"][i].get("tab", "") or "the sheet" for _w, i in hits]
            for w, i in hits:
                others = sorted({x["name"] for x, _ in hits if x is not w})
                out.setdefault(w["rows"][0], []).append(
                    {"day": day, "tabs": tabs, "with": others})
    return out


def linked_signature(clashes: dict) -> str:
    """A stable string naming every linked clash — what the preview showed,
    carried back by the commit form so the commit knows it was seen."""
    return ";".join(f"{k}:{c['day']}" for k in sorted(clashes)
                    for c in clashes[k])


def worker_money(rec: dict, worker: dict) -> tuple:
    """
    `(money, problems)` — the worker's money columns across tabs.

    ADV, EXTRA EXP, LOAN and the cached ACTUAL SALARY are SUMMED: each tab's
    figure is that site's share of one month. PER DAY SALARY and BALANCE LOAN
    are one figure about the person, not about a site: taken where every tab
    that fills it agrees, and LEFT OUT (with a note) where two disagree.
    """
    rows = [rec["rows"][i] for i in worker["rows"]]
    money, problems = {}, []
    for key in ("advance", "travel", "loan", "actual"):
        vals = [r["money"].get(key) for r in rows if r["money"].get(key) is not None]
        money[key] = round(sum(vals), 2) if vals else None
    for key, label in (("rate", "PER DAY SALARY"), ("balance_loan", "BALANCE LOAN")):
        vals = {round(r["money"][key], 2) for r in rows
                if r["money"].get(key) is not None}
        if len(vals) > 1:
            problems.append(f"{label} differs between tabs ("
                            + ", ".join(f"{v:,.2f}" for v in sorted(vals))
                            + ") — not imported")
            money[key] = None
        else:
            money[key] = vals.pop() if vals else None
    return money, problems


def worker_row(rec: dict, worker: dict) -> dict:
    """The worker as ONE row — what `app_net()` and the preview price."""
    days, _clashes = worker_days(rec, worker)
    money, _p = worker_money(rec, worker)
    return {"days": [d for _i, d in days], "money": money}


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


# ⚠ **THE SITE PICKER STOPPED CARRYING THE PROJECT, 5 November 2026** —
#   CLIENT_CHANGES.md §0's **sixty-sixth** block, ruling 2: *"Site → project is
#   decided PER WORKER at import."* `docs/LABOUR_PL.md` §2 is the defect.
#
#   It used to offer one entry per **(site, project)** pair, so a site carrying
#   two live projects could not be picked without picking one of them — for the
#   WHOLE SHEET. Jamnagar and Jamnagar Shed share an address, and every worker
#   on either landed on whichever one the operator chose. There was no shape in
#   which half the rows went to the Shed.
#
#   Now: one entry per book site, plus **No project (overhead)** at the top,
#   and the project is a per-worker control on the row (`proj_<i>`).
#
# ⚠ **The `addr|project` form is still ACCEPTED by `resolve_choice()`** and is
#   no longer OFFERED. It is a site-level answer that overrides the per-worker
#   pick for every row at that site, which is what a saved form or a scripted
#   post may carry, and refusing it would turn an old URL into a lost import.

# "No project (overhead)" — ruling 2's *"e.g. OFFICE"*. Not an address and not
# a project; `attendance.OVERHEAD_CHOICE` is the one spelling.
OVERHEAD = AT.OVERHEAD_CHOICE


def site_choices() -> list:
    """
    `[(value, label, address_label)]` — the sheet-site picker.

    One entry per live book site (value: the address id), and **one overhead
    entry** whose value is `OVERHEAD` and whose address label is `""`, so
    `preselect()` can never match it by accident.

    ⚠ **The project is NOT in here any more** — see the block above.
    """
    out = [(OVERHEAD, "No project — overhead (office, workshop, yard)", "")]
    for a in sorted((STORE.get("addresses") or {}).values(),
                    key=lambda a: str(a.get("label") or "").lower()):
        if a.get("type") not in AD.SITE_TYPES or a.get("archived"):
            continue
        label = str(a.get("label") or "")
        out.append((str(a["id"]), label, label))
    return out


def preselect(site: str, choices: list) -> str:
    """
    The one choice whose ADDRESS LABEL equals the sheet's SITE exactly (trimmed
    only — `employee.resolve_site()`'s rule), or "". Never a near match, and
    never when that address offers more than one choice.

    ⚠ **A multi-project site now PRESELECTS, where before it could not.** The
      pairs are gone, so an address appears once and the exact-label match is
      unambiguous again. The decision that used to be forced here — *which* of
      the two projects — is now asked on each worker's row, which is where
      ruling 2 puts it.

    ⚠ **The overhead entry carries an empty address label on purpose**, so a
      sheet whose SITE column is blank cannot match it. Overhead is always a
      deliberate pick.
    """
    hits = [v for v, _, addr in choices
            if addr.strip() == site.strip() and addr.strip()]
    return hits[0] if len(hits) == 1 else ""


def resolve_choice(value: str, sheet_site: str = "") -> tuple:
    """
    `(site_fields, project_fields, error)` for one sheet site's pick.

    | value | site | project |
    |---|---|---|
    | `OVERHEAD` | the sheet's own string, kept and marked **unmapped** | overhead |
    | `<addr>` / `<addr>` + `|` | the book site | `None` where the site carries **2 or more** projects — *ask per worker*; the only one where it carries one; blank where it carries none |
    | `<addr>` + `|overhead` | the book site | overhead |
    | `<addr>` + `|<pid>` | the book site | that project, for every row at that site (not offered; still accepted) |

    ⚠ **`project_fields is None` is the per-worker deferral and is not an
      error.** It used to be `"several projects are at that site — choose one"`,
      which abandoned the whole import — so the cheapest way past it was to
      pick *a* project, which is the silent mis-attribution this module exists
      to prevent (`docs/LABOUR_PL.md` §2, consequence 2).

    ⚠ **Overhead with no book site KEEPS the sheet's string** rather than
      clearing it. `employee.resolve_site()`'s middle row, for its reason: the
      string is evidence of where somebody worked. It is marked `unmapped`, and
      an overhead marking is excluded from `off_project_labour()`, so it is
      reported nowhere as an unanswered question.
    """
    raw = str(value or "").strip()
    if raw == OVERHEAD:
        return ({"site": str(sheet_site or "").strip()[:200],
                 EMP.SITE_ADDRESS_FIELD: "",
                 EMP.SITE_SOURCE_FIELD: EMP.SITE_UNMAPPED},
                AT.overhead_fields(True), "")

    aid, _, pid = raw.partition("|")
    label = EMP.site_label_of(aid)
    if not label:
        return {}, {}, "choose a site from the address book"
    site = {"site": label, EMP.SITE_ADDRESS_FIELD: aid,
            EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK}
    candidates = {p["id"]: p for p in AT.projects_on_site(aid)}

    if pid == OVERHEAD:
        return site, AT.overhead_fields(True), ""
    if pid:
        p = candidates.get(pid)
        if not p:
            return {}, {}, "that project is not at that site"
        return site, {"project_id": p["id"],
                      "project_name": str(p.get("name") or "")}, ""
    if len(candidates) > 1:
        return site, None, ""
    if len(candidates) == 1:
        p = next(iter(candidates.values()))
        return site, {"project_id": p["id"],
                      "project_name": str(p.get("name") or "")}, ""
    return site, {"project_id": "", "project_name": ""}, ""


def resolve_row_project(value: str, site_fields: dict) -> tuple:
    """
    `(project_fields, error)` for one WORKER's `proj_<i>` pick, against the
    site that row is being saved with — ruling 2's per-worker decision.

    ⚠ **Checked against the row's own site**, never against the form's: a
      project must be filed at the address the marking carries, which is
      `attendance.resolve_project()`'s invariant and the reason this takes the
      resolved fields rather than an index.

    ⚠ **A blank is REFUSED, and that is ruling 2's last line** — *"No default →
      must be picked before commit."* The two readings of a blank on an
      ambiguous site are "the operator has not got to it" and "the operator
      means none", and the second has its own choice on the control
      (`OVERHEAD`). Guessing between them puts a day's wage on a project
      nobody chose.
    """
    raw = str(value or "").strip()[:64]
    if raw == OVERHEAD:
        return AT.overhead_fields(True), ""
    if not raw:
        return {}, ("two or more projects are at that site — choose which one "
                    "for this person, or “No project (overhead)”")
    aid = str((site_fields or {}).get(EMP.SITE_ADDRESS_FIELD) or "").strip()
    for p in AT.projects_on_site(aid):
        if str(p.get("id")) == raw:
            return {"project_id": str(p.get("id")),
                    "project_name": str(p.get("name") or "")}, ""
    return {}, "that project is not at that site"


# =============================================================================
# THE WRITE
# =============================================================================

# =============================================================================
# THE SAVED SITE MAPPING — a sheet's site name, answered once (§0 68th block)
# =============================================================================
#
# ⚠ **Keyed by the sheet's SITE NAME, normalised** (`norm()`), and holding the
#   address-book site it means and — where that address carries two or more
#   projects (RIL Jamnagar / RIL Jamnagar Shed) — WHICH project that name
#   means. It is written by a successful commit and read by the next preview
#   (prefilled, still changeable) and the next commit (an unanswered shared
#   site falls back to it). A saved answer whose address or project no longer
#   exists is ignored, never repaired. One settings record, created on first
#   use; nothing existing changes shape.

SITE_MAP_RECORD = "pay_import_sites"


def saved_sites() -> dict:
    rec = (STORE.get("settings") or {}).get(SITE_MAP_RECORD) or {}
    return rec.get("sites") or {}


def saved_for(site_name) -> dict:
    """`{"label", "site", "project", "saved_at"}` for one sheet site name, or {}."""
    return saved_sites().get(norm(site_name)) or {}


def save_sites(answers: dict) -> None:
    """`answers`: `{sheet site name: (site value, project value)}`."""
    rec = STORE.setdefault("settings", {}).setdefault(
        SITE_MAP_RECORD, {"id": SITE_MAP_RECORD, "sites": {}})
    sites = rec.setdefault("sites", {})
    for name, (site_value, project_value) in answers.items():
        sites[norm(name)] = {"label": name, "site": site_value,
                             "project": project_value,
                             "saved_at": PAY._now()}


def _site_value_of(sf: dict, pf) -> str:
    if pf and pf.get(AT.OVERHEAD_FIELD) and not sf.get(EMP.SITE_ADDRESS_FIELD):
        return OVERHEAD
    return str(sf.get(EMP.SITE_ADDRESS_FIELD) or "")


def _no_site_project(person: dict, month: str) -> dict:
    """
    The project for a day the sheet gives NO site for: that worker's project
    last month (`attendance.project_last_month()` — unanimous only, overhead
    included), else unassigned. ⚠ **Only ever for a day with no site**; a site
    the sheet gives is never overridden by it.
    """
    last = AT.project_last_month(person.get("id"), month) if person else {}
    if last.get(AT.OVERHEAD_FIELD):
        return AT.overhead_fields(True)
    if last.get("project_id"):
        return {"project_id": last["project_id"],
                "project_name": last.get("project_name", "")}
    return {"project_id": "", "project_name": ""}


# =============================================================================
# THE WRITE
# =============================================================================

LINKED_CLASH_ERROR = ("Two rows are linked to the same employee and both "
                      "mark the same day — flagged below. Those days will "
                      "be imported on NEITHER row; commit again to go "
                      "ahead, or link the rows differently.")


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

    # ⚠ **The site AND, where it is shared, the project — once per SITE NAME**
    #   (§0 sixty-eighth block). A tab is a site, so the name already says which
    #   of two projects at one address the days were for; the answer comes from
    #   `sproj_<i>`, else from the saved mapping for that name. Only where
    #   neither answers does a project fall to the per-worker `proj_<i>` of the
    #   sixty-sixth block, still accepted, no longer drawn.
    mapping, answers = {}, {}
    for i, site in enumerate(rec["sites"]):
        raw = str(form.get(f"site_{i}") or "").strip()
        sf, pf, err = resolve_choice(raw, site)
        if err:
            return {}, f"Site “{site}”: {err}."
        if pf is None:
            sp = str(form.get(f"sproj_{i}") or "").strip()
            if not sp:
                saved = saved_for(site)
                if saved.get("site") == sf.get(EMP.SITE_ADDRESS_FIELD):
                    sp = str(saved.get("project") or "")
            if sp:
                pf, perr = resolve_row_project(sp, sf)
                if perr:
                    return {}, f"Site “{site}”: {perr}."
                answers[site] = (sf[EMP.SITE_ADDRESS_FIELD], sp)
        else:
            _a, _, given = raw.partition("|")
            answers[site] = (_site_value_of(sf, pf), given)
        mapping[site] = (sf, pf)

    workers = workers_of(rec)

    # Every per-worker fallback pick is checked BEFORE anything is written.
    worker_pick = {}
    for w in workers:
        first = w["rows"][0]
        if not (form.get(f"emp_{first}") or "").strip():
            continue
        shared = {rec["rows"][i]["site"] for i in w["rows"]
                  if rec["rows"][i]["site"]
                  and mapping.get(rec["rows"][i]["site"], ({}, {}))[1] is None}
        for site in sorted(shared):
            sf = mapping[site][0]
            if not str(form.get(f"proj_{first}") or "").strip():
                n = len(AT.projects_on_site(sf.get(EMP.SITE_ADDRESS_FIELD)))
                return {}, (f"Site “{site}”: {n} projects are at that site — "
                            f"choose which one this site name means, or "
                            f"“No project (overhead)”.")
            pf, perr = resolve_row_project(form.get(f"proj_{first}"), sf)
            if perr:
                return {}, f"{w['name']}: {perr}."
            worker_pick[(first, site)] = pf

    # ⚠ **Two rows linked to one employee, one day marked on both** (§0
    #   seventy-first block): imported on NEITHER, and only once the preview
    #   has SHOWN it — the picks are the operator's, made on the preview, so a
    #   commit whose picks create a clash the page did not show goes back to
    #   the preview with those picks, where it is flagged, and nothing is
    #   written.
    links = {w["rows"][0]: (form.get(f"emp_{w['rows'][0]}") or "").strip()
             for w in workers_of(rec)}
    cross = linked_clashes(rec, links)
    if cross and str(form.get("linked_seen") or "") != linked_signature(cross):
        return {}, LINKED_CLASH_ERROR

    batch = rec["id"]
    lo, hi = PAY.month_bounds(month)
    summary = {"markings": 0, "skipped_days": 0, "entries": 0, "created": 0,
               "rates_filled": 0, "rates_updated": 0, "rows_skipped": 0,
               "loan_mismatch": [], "clashes": []}
    for w in workers:
        first = w["rows"][0]
        choice = (form.get(f"emp_{first}") or "").strip()
        if not choice:
            summary["rows_skipped"] += len(w["rows"])
            continue
        lead = rec["rows"][first]
        money, _mp = worker_money(rec, w)
        sheet_rate = money.get("rate")
        if choice == "new":
            home = next((mapping[rec["rows"][i]["site"]][0] for i in w["rows"]
                         if rec["rows"][i]["site"] in mapping), {})
            data, err = EMP._validate({
                "name": lead["name"], "designation": lead["designation"],
                "day_rate": "" if sheet_rate is None else str(sheet_rate),
                "site_id": home.get(EMP.SITE_ADDRESS_FIELD, ""), "active": "1"})
            if err:
                return {}, f"Row {lead['line']} ({lead['name']}): {err}"
            person = EMP.employees()[EMP.create_record(data)]
            summary["created"] += 1
        else:
            person = EMP.employees().get(choice)
            if not person:
                return {}, f"Row {lead['line']}: that employee no longer exists."
            if sheet_rate is not None and not person.get("day_rate") \
                    and not EMP.is_pre_day_rate(person):
                person["day_rate"] = round(sheet_rate, 2)
                summary["rates_filled"] += 1
            elif sheet_rate is not None and form.get(f"rate_{first}") \
                    and round(sheet_rate, 2) != round(float(person.get("day_rate") or 0), 2):
                person["day_rate"] = round(sheet_rate, 2)
                person.pop(EMP.RATE_MODEL_FIELD, None)
                person.pop("monthly_salary", None)
                summary["rates_updated"] += 1

        days, clashes = worker_days(rec, w)
        for c in clashes:
            summary["clashes"].append(
                f"{lead['name']} day {c['day']} ({' / '.join(c['tabs'])})")
        linked = {c["day"] for c in cross.get(first, [])}
        for c in cross.get(first, []):
            summary["clashes"].append(
                f"{lead['name']} day {c['day']} (also marked as "
                f"{' / '.join(c['with'])}, linked to the same employee)")
        no_site_pf = None
        for i, d in days:
            if d["day"] in linked:
                continue
            site = rec["rows"][i]["site"]
            if site:
                sf, pf = mapping.get(site, ({}, {}))
                if pf is None:
                    pf = worker_pick[(first, site)]
            else:
                if no_site_pf is None:
                    no_site_pf = _no_site_project(person, month)
                sf, pf = {}, no_site_pf
            day = f"{month}-{d['day']:02d}"
            rid, err = AT.import_marking(person, day, d["status"], d["ot"],
                                         sf, pf, batch, d.get("note", ""))
            if rid:
                summary["markings"] += 1
            else:
                summary["skipped_days"] += 1

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

    save_sites(answers)
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


def _site_project_cell(i: int, site: str, site_value: str, saved: dict) -> str:
    """
    The project control for ONE SHEET SITE NAME (§0 sixty-eighth block):
    drawn only where the picked address carries two or more live projects,
    prefilled from the saved mapping when it answers for that same address.
    It replaces the sixty-sixth block's per-worker picker — a tab is a site,
    so the site's NAME says which project, once for everybody on it.

    ⚠ It carries `data-row-project` and `data-sheet-site` (the sheet's site
      name), so the page's script re-populates it when the site select
      changes, exactly as it did the per-worker control. The server decides:
      `resolve_row_project()` refuses a project not at that site.
    """
    at = (AT.projects_on_site(site_value)
          if site_value and site_value != OVERHEAD else [])
    if len(at) < 2:
        return (f'<select name="sproj_{i}" data-row-project="{i}" '
                f'data-sheet-site="{_esc(site)}" disabled>'
                f'<option value="">&mdash;</option></select>')
    want = str(saved.get("project") or "") if saved.get("site") == site_value else ""
    ids = [str(p.get("id")) for p in at]
    if want not in ids + [OVERHEAD]:
        want = ""
    opts = [f'<option value=""{"" if want else " selected"}>'
            f'&mdash; choose which project &mdash;</option>']
    for p in at:
        pid = str(p.get("id"))
        opts.append(f'<option value="{_esc(pid)}"'
                    f'{" selected" if pid == want else ""}>'
                    f'{_esc(p.get("name") or "(unnamed)")}</option>')
    opts.append(f'<option value="{_esc(OVERHEAD)}"'
                f'{" selected" if want == OVERHEAD else ""}>'
                f'No project (overhead)</option>')
    return (f'<select name="sproj_{i}" data-row-project="{i}" '
            f'data-sheet-site="{_esc(site)}">{"".join(opts)}</select>')


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
    site_pick = {}            # sheet site -> the value the select is showing
    for i, site in enumerate(rec["sites"]):
        saved = saved_for(site)
        valid = {v for v, _l, _a in choices}
        pick = (saved.get("site") if saved.get("site") in valid
                else preselect(site, choices))
        site_pick[site] = pick
        opts = ['<option value="">— choose —</option>'] + [
            f'<option value="{_esc(v)}"{" selected" if v == pick else ""}>'
            f'{_esc(label)}</option>' for v, label, _ in choices]
        # ⚠ **What the site carries is printed BESIDE the picker**, so the
        #   operator can see before committing which rows are going to ask for
        #   a project. A multi-project site is the one that does.
        at = AT.projects_on_site(pick) if pick and pick != OVERHEAD else []
        if pick == OVERHEAD:
            note = "overhead — these days land on no project"
        elif len(at) > 1:
            note = (f'{len(at)} projects here: '
                    + ", ".join(str(p.get("name") or "") for p in at)
                    + " — say which one this site name means")
        elif len(at) == 1:
            note = f'one project here: {at[0].get("name") or ""} — assigned'
        elif pick:
            note = "no project at this site — these days go to Unassigned"
        else:
            note = ""
        if saved and saved.get("site") == pick:
            note += " · saved from an earlier import"
        site_rows += (f'<tr><td><b>{_esc(site)}</b></td>'
                      f'<td><select name="site_{i}" data-sheet-site="{i}" '
                      f'required>{"".join(opts)}</select></td>'
                      f'<td>{_site_project_cell(i, site, pick, saved)}</td>'
                      f'<td class="pay-sub">{_esc(note)}</td></tr>')

    people = sorted(EMP.employees().values(),
                    key=lambda e: str(e.get("name") or "").lower())

    def _pick(i, name):
        """The employee this row's select shows: a pick carried back from a
        refused commit, else the name match."""
        if f"emp_{i}" in request.args:
            got = str(request.args.get(f"emp_{i}") or "").strip()
            return EMP.employees().get(got) or ({"id": got} if got == "new"
                                                else {})
        return match_employee(name)

    picks = {w["rows"][0]: _pick(w["rows"][0], rec["rows"][w["rows"][0]]["name"])
             for w in workers_of(rec)}
    cross = linked_clashes(rec, {k: (v or {}).get("id", "")
                                 for k, v in picks.items()})
    emp_rows = ""
    for w in workers_of(rec):
        i = w["rows"][0]
        row = rec["rows"][i]
        wrow = worker_row(rec, w)
        days, clashes = worker_days(rec, w)
        money_notes = worker_money(rec, w)[1]
        hit = picks[i] if (picks[i] or {}).get("name") else {}
        chosen = (picks[i] or {}).get("id", "")
        opts = [f'<option value="">— skip this row —</option>',
                f'<option value="new"{" selected" if chosen == "new" else ""}>'
                'Create a new employee</option>']
        opts += [f'<option value="{_esc(e["id"])}"{" selected" if hit and e["id"] == hit["id"] else ""}>'
                 f'{_esc(e.get("name"))}{" (" + _esc(e.get("code")) + ")" if e.get("code") else ""}</option>'
                 for e in people]
        m = wrow["money"]
        rate = m.get("rate")
        rate_cell = "&mdash;" if rate is None else PAY._money(rate)
        if hit and rate is not None and hit.get("day_rate") and \
                round(rate, 2) != round(float(hit.get("day_rate") or 0), 2):
            rate_cell += (f'<br><label><input type="checkbox" name="rate_{i}"/> '
                          f'replace {PAY._money(hit.get("day_rate"))}</label>')
        paid = sum(AT.share_of(d["status"]) for d in wrow["days"])
        ot = sum(d["ot"] for d in wrow["days"] if d["status"] in AT.OT_STATUSES)
        net = app_net(wrow, month)
        actual = m.get("actual")
        diff = (actual is not None and round(actual, 2) != round(net, 2))
        conflicts = 0
        if hit and month:
            marked = {r.get("date") for r in AT.month_markings(hit["id"], month)}
            conflicts = sum(1 for d in wrow["days"]
                            if f"{month}-{d['day']:02d}" in marked)
        notes = [p for k in w["rows"] for p in rec["rows"][k]["problems"]]
        notes += money_notes
        if clashes:
            notes.append("⚠ marked on two tabs, NOT imported until resolved: "
                         + "; ".join(f"day {c['day']} ({' / '.join(c['tabs'])})"
                                     for c in clashes))
        if cross.get(i):
            notes.append("⚠ linked to the same employee as "
                         + ", ".join(sorted({n for c in cross[i] for n in c["with"]}))
                         + " and both mark the same day, NOT imported on "
                           "either until resolved: "
                         + "; ".join(f"day {c['day']} ({' / '.join(c['tabs'])})"
                                     for c in cross[i]))
        if conflicts:
            notes.append(f"{conflicts} day(s) already marked in the app — skipped")
        if m.get("loan") and not m.get("balance_loan"):
            notes.append("a loan deduction with no BALANCE LOAN")
        per_site = {}
        for k, _d in days:
            key = rec["rows"][k]["site"]
            per_site[key] = per_site.get(key, 0) + 1
        where = "; ".join(
            f"{_esc(k) if k else 'no site'}: {n} d" for k, n in per_site.items())
        if per_site.get(""):
            last = _no_site_project(hit, month) if hit and month else {}
            where += (" &mdash; no-site days take "
                      + (_esc(last.get("project_name")) if last.get("project_id")
                         else "overhead" if last.get(AT.OVERHEAD_FIELD)
                         else "no project (Unassigned)")
                      + " (last month)")
        tabs = (", ".join(_esc(rec["rows"][k].get("tab", "")) for k in w["rows"]
                          if rec["rows"][k].get("tab")) or _esc(row["site"]))
        emp_rows += f"""
      <tr{' style="background:#fff3e0"' if diff or notes else ''}>
        <td>{_esc(row['name'])}<span class="pay-sub">{tabs}</span></td>
        <td><select name="emp_{i}">{''.join(opts)}</select></td>
        <td class="pay-sub">{where or '&mdash;'}</td>
        <td class="num">{len(wrow['days'])} / {PAY._days(paid)}</td>
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
    # ⚠ **Through `pipeline.json_for_script()`, never `json.dumps`** — a project
    #   named with the seven characters `</script>` would otherwise close the
    #   block and every byte after it would be parsed as HTML (ABOUT.md §7.9e).
    #   A project name and a sheet's SITE string are both free text.
    tabs_html = " &middot; ".join(
        f'{_esc(t["name"])} ({t["rows"]} rows, site from '
        + {"column": "the SITE column", "tab": "the tab name",
           "mixed": "the SITE column and the tab name",
           "none": "nowhere — no site", "hidden": "— hidden, not read"}.get(
               t["site_from"], _esc(t["site_from"])) + ")"
        for t in rec.get("tabs") or []) or "one sheet"
    projects_by_site = AT.projects_by_site_json()
    sheet_sites = P.json_for_script(
        {str(i): s for i, s in enumerate(rec["sites"])})
    overhead_json = P.json_for_script(OVERHEAD)
    body = f"""
  {PAY._flash()}
  <div class="page-top"><h1>Check the import &mdash; {_esc(rec.get('filename'))}</h1>
    <a class="btn btn-ghost" href="{url_for('payimport.upload')}">&#8592; Back</a></div>
  {warn}
  {f'<div class="pay-warn"><ul>{problems}</ul></div>' if problems else ''}
  <div class="pay-note"><b>Tabs read:</b> {tabs_html}</div>
  <div class="pay-note"><b>Nothing has been written.</b> {rec['days']} day columns,
    {len(rec['rows'])} rows, {len(workers_of(rec))} people. A blank day writes nothing; 0 writes an absence; 0.5 a
    half day; a 1 carrying a "paid leave" comment, paid leave. Names are matched
    exactly &mdash; an unmatched row is skipped unless you choose. The app's net
    is priced by the muster's own arithmetic; where the sheet's ACTUAL SALARY
    differs it is shown in bold.</div>
  <form method="POST" action="{url_for('payimport.commit_import', id=id)}">
    <div class="form-section">
      <div class="section-title">Month</div>
      <input type="month" name="month" required value="{_esc(month)}"/>
      <input type="hidden" name="linked_seen" value="{_esc(linked_signature(cross))}"/>
    </div>
    <div class="form-section">
      <div class="section-title">Where each SITE in the sheet is</div>
      <table class="pay-tbl">{site_rows}</table>
    </div>
    <div class="pay-card"><table class="pay-tbl">
      <tr><th>Sheet row</th><th>Employee</th><th>Sites</th>
          <th class="num">Marked / paid days</th>
          <th class="num">OT hrs</th><th class="num">Day rate</th>
          <th class="num">Adv / travel / loan ded. / loan owed</th>
          <th class="num">App net</th><th>Notes</th></tr>
      {emp_rows}
    </table></div>
    <button class="btn">Import</button>
  </form>
<script>
/* Re-populate each worker's PROJECT control when its sheet SITE changes
   (5 November 2026, CLIENT_CHANGES.md §0's sixty-sixth block, ruling 2).

   ⚠ It decides NOTHING. `resolve_choice()` and `resolve_row_project()` re-read
     STORE["projects"] on the POST and refuse a project that is not at the
     row's site; this only keeps the control honest while it is being used, the
     way `attendance.py`'s project picker does on the mark form.

   ⚠ It runs on `change` and NOT on load. The server rendered the correct
     options, including the last-month default, and re-deriving them here on
     load would make the browser the authority on a value the server decided.

   ⚠ It never invents a default. A site with several projects opens blank —
     the commit refuses and says so — because a default the operator did not
     choose is the whole defect ruling 2 closes. */
(function () {{
  var BY_SITE = {projects_by_site};
  var SHEET = {sheet_sites};
  var OVERHEAD = {overhead_json};

  function cellsFor(sheetSite) {{
    var all = document.querySelectorAll("[data-row-project]"), out = [], i;
    for (i = 0; i < all.length; i++) {{
      if (all[i].getAttribute("data-sheet-site") === sheetSite) {{
        out.push(all[i]);
      }}
    }}
    return out;
  }}

  var selects = document.querySelectorAll("[data-sheet-site][name^='site_']");
  for (var s = 0; s < selects.length; s++) {{
    (function (sel) {{
      sel.addEventListener("change", function () {{
        var sheetSite = SHEET[sel.getAttribute("data-sheet-site")] || "";
        var list = sel.value === OVERHEAD ? [] : (BY_SITE[sel.value] || []);
        var cells = cellsFor(sheetSite), c, i;
        for (c = 0; c < cells.length; c++) {{
          var box = cells[c];
          while (box.firstChild) {{ box.removeChild(box.firstChild); }}
          var blank = document.createElement("option");
          blank.value = "";
          blank.textContent = "\u2014 choose which project \u2014";
          box.appendChild(blank);
          for (i = 0; i < list.length; i++) {{
            var o = document.createElement("option");
            o.value = list[i][0];
            /* textContent, never innerHTML — a project name is free text. */
            o.textContent = list[i][1];
            box.appendChild(o);
          }}
          var oh = document.createElement("option");
          oh.value = OVERHEAD;
          oh.textContent = "No project (overhead)";
          box.appendChild(oh);
          box.value = sel.value === OVERHEAD ? OVERHEAD : "";
          box.disabled = list.length < 2 && sel.value !== OVERHEAD;
        }}
      }});
    }})(selects[s]);
  }}
}})();
</script>"""
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
        keep = {}
        if error == LINKED_CLASH_ERROR:
            # The operator's picks travel back, so the preview shows the
            # clash THEY made, not the one its own name match would make.
            keep = {k: v for k, v in request.form.items()
                    if k.startswith(("emp_", "rate_", "site_", "sproj_",
                                     "proj_"))}
        return redirect(url_for("payimport.preview", id=id,
                                month=request.form.get("month"),
                                msg=error, type="error", **keep))
    msg = (f"Imported: {summary['markings']} day(s) marked, "
           f"{summary['skipped_days']} skipped as already marked, "
           f"{summary['entries']} ledger entr(ies), {summary['created']} new "
           f"employee(s), {summary['rows_skipped']} row(s) skipped.")
    if summary["loan_mismatch"]:
        msg += " Loan differs from the ledger for: " + "; ".join(
            summary["loan_mismatch"])
    if summary.get("clashes"):
        msg += (" NOT imported — marked on two tabs, mark by hand once "
                "resolved: " + "; ".join(summary["clashes"]))
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
