"""
attendance.py — Attendance & site-wise labour cost  (CLIENT_CHANGES-2.md **C5**)
================================================================================
Blueprint  : attendance_bp
Mounted at : /attendance  (registered in app.py)

Routes
------
  GET       /attendance/                 — one day's muster + site-wise cost
  GET,POST  /attendance/mark             — mark one person, one site, one day
  GET,POST  /attendance/edit/<id>        — correct a marking
  GET,POST  /attendance/delete/<id>      — GET confirms, POST destroys

What C5 is
----------
CLIENT_CHANGES-2.md **C5**, in full:

    - Presentee / absentee, recorded **daily**
    - Salary as 0 or 1 based on attendance
    - **One employee = one site = one day**
    - OT = (salary ÷ 8) × hours
    - Presentation table: Employee — Site — OT time

    **This is a labour cost tracker, not payroll.** It feeds project costing.
    Statutory matters — PF, ESIC, professional tax, minimum wages — are the
    client's responsibility and this is stated in MG/SF/2026-02 §5.

Built under the **third 29 August 2026** override block in `CLIENT_CHANGES.md`
§0. Before that block C5 was one of the six remaining NOT STARTED items and was
gated; `employee.py` says in as many words that it built nothing toward it.

⚠ **PAYROLL IS NOT WHAT THIS IS.** No PF, no ESIC, no professional tax, no
minimum-wage check, no payslip, no bank file, no statutory register. It records
who was on which site on which day and what that came to. Anybody reading a
figure here as somebody's pay is reading it wrong, and the register says so on
its face.

════════════════════════════════════════════════════════════════════════════
⚠ THE OT MULTIPLIER IS A SETTING. NO LITERAL MULTIPLIER LIVES IN THIS FILE.
════════════════════════════════════════════════════════════════════════════

CC-2 is explicit and the reason is not stylistic. The client's own figure is
`salary ÷ 8 × hours`, which is **1× ordinary rate**. Statutory overtime under
the Factories Act and most state Shops & Establishments Acts is generally
**twice** ordinary wages, so **hardcoding the client's figure would make this
software compute a statutory underpayment.**

So it lives at `/settings` (`settings.ot_multiplier()`), it defaults to the
client's figure, and the settings page carries a line saying what it is and
what it is not. `ot_amount()` below takes the multiplier as an **argument** and
`tests/test_attendance.py` walks this module's AST and fails on any numeric
constant in a multiplication inside the calculation path.

`STANDARD_HOURS_PER_DAY` is the one number that IS a constant here, and it is
CC-2's own: the `÷ 8` in *"OT = (salary ÷ 8) × hours"*. It is a divisor
defining what "an hour of a day" means, not a rate anybody is paid at.

════════════════════════════════════════════════════════════════════════════
⚠ THE RATE IS A **DAY RATE**, AND `wage_days_per_month` IS GONE
════════════════════════════════════════════════════════════════════════════

Corrected 30 August 2026 under the third override block of that date, after the
owner said that **Samruddhi pays daily or weekly, never monthly**.

`wage_days_per_month` was a setting **we** invented to divide a monthly salary
into a daily wage, on the reading that CC-2's `salary` was monthly. That reading
was wrong, and CC-2 says so twice in its own five bullets:

* *"Salary as 0 or 1 based on attendance"* — one day present pays `salary × 1`.
  On a monthly figure that is a month's pay for a day's work.
* *"OT = (salary ÷ 8) × hours"*, which CC-2's own note calls **"1× ordinary
  rate"**. `salary ÷ 8` is an ordinary hourly rate only if `salary` is a **day's**
  wage and 8 is the hours in a day.

So the divisor solved a problem that never existed, and it is **deleted** rather
than re-tuned: from `/settings`, from `settings.py`, from this file, and from
PROGRESS.md §4c, where a beyond-CC-2 item is retired.

⚠ **NOTHING IS CONVERTED AND NOTHING IS RECOMPUTED.** A marking made before the
correction snapshotted a **monthly** salary. Those snapshots are history — they
are the record of what that day was assessed at — so they keep their key, keep
their number, and carry `employee.RATE_MODEL_FIELD == PRE_DAY_RATE`. What
changes is that `cost_of()` **refuses to produce a figure** for them instead of
producing one that is roughly twenty-six times too large. `employee.py` owns
that marker and this module reads it; the arrow may not run the other way.

⚠ **Marked markings are excluded from every total on the page and the page says
how many.** A site figure quietly missing three people's wages is the same class
of defect as one quietly counting a monthly salary as a day's.

════════════════════════════════════════════════════════════════════════════
⚠ ONE EMPLOYEE = ONE SITE = ONE DAY, ENFORCED AT WRITE TIME
════════════════════════════════════════════════════════════════════════════

CC-2's third bullet, read as a **uniqueness constraint on (employee, date)**:
on any given day a person is on **one** site, so there is at most one record
per employee per day and that record names the site.

The reading matters and the alternative is worse. Keying on
`(employee, site, date)` would permit the same person to be marked present on
three sites on one day, each costing a full day's wage — **the same labour
counted three times**, silently, on the figure this module exists to produce.
Refusing the second marking is the only reading that cannot do that. If the
client ever needs a split day, that is a share-of-a-day field and a change to
this constraint, not a second record.

It is enforced in `conflicting_record()`, called by **both** write routes
before anything is stored — not in the form, and not by a `<select>` that
happens to omit the name. A form is a convenience; the refusal is the rule.

════════════════════════════════════════════════════════════════════════════
⚠ SITE IS FREE TEXT AND IS DELIBERATELY NOT A PROJECT
════════════════════════════════════════════════════════════════════════════

The existing project record was considered first, as the brief for this pass
required, and it does not fit. Three reasons, in order of weight:

1. **A project is not a site in this application's own data model.** A BOQ
   carries `project_name` **and** `site_location` as two separate fields
   (ABOUT.md §3). One project runs at several sites; one site can carry work
   for more than one project. Reusing `project_id` here would assert an
   identity the rest of the app already denies.
2. **`employee.site` is already free text**, and C4 chose that deliberately —
   *"Linking a person to a project is C5/C6 territory and both are gated."*
   Marking attendance against the field the master already carries is one
   vocabulary; marking it against a different entity is two.
3. **A `project_id` on an attendance record is the first half of C6**, which is
   BLOCKED on the client's Open question 4. The override authorising C5 says
   in terms not to lay groundwork for it.

So the site is typed, and the form **prefills the employee's own posted site**
so the common case is one keystroke. No second site entity was invented, which
is the other thing the brief forbade.

════════════════════════════════════════════════════════════════════════════
⚠ WHAT THIS MODULE DOES NOT DO — C6 IS BLOCKED AND STAYS BLOCKED
════════════════════════════════════════════════════════════════════════════

**Nothing here is exported and nothing consumes it.** The site-wise labour cost
is displayed on **this module's own pages and nowhere else**. There is no
figure on the dashboard, none on `/projects/view/<id>`, none in `charge.py`,
and no function any other module calls.

That is not tidiness. **C6 is BLOCKED on CC-2's Open question 4** — whether
attendance-based wages or the BOQ's installation base rate is authoritative for
labour cost. Subtracting both counts labour twice. C5 can be built without that
answer; **wiring it into C6 cannot**, so it is not wired.
`projectview.py`'s standing prohibition — *"no revenue total, no cost total, no
margin, no profit, no net, no balance"* — is untouched, and
`tests/test_attendance.py` asserts at AST level that no module imports this one.

Imports, and why `settings` is on the list
------------------------------------------
```
attendance.py ──► employee.py   active_employees() — the master C4 shipped
attendance.py ──► settings.py   the OT multiplier and the wage divisor
attendance.py ──► dashboard, branding, pipeline, store, quotation
```

`employee.py ──► attendance.py` is **NEVER**: the register links out with
`url_for` and imports nothing, which is the one-way trick this codebase already
runs between quotation/proforma and boq/ra. Importing back would be a cycle.

⚠ **`charge.py` is forbidden in both directions**, and that prohibition did
*not* expire when C5 was authorised. Wages recorded here and expenses recorded
there are two ledgers, and joining them is a P&L question — C6's.

`attendance.py ──► settings.py` follows `po_draft.py` and `challan.py`, which
both read a settings-owned series the same way. It is required by C5 itself:
CC-2 asks for the multiplier to be configurable, and configuration lives there.

Escaping
--------
Every field on this record is typed by a user and every one reaches HTML.
`P.esc` at the interpolation site, never a response filter, and **never on a
money format** (ABOUT.md §9).
"""

import datetime
import uuid

from flask import Blueprint, redirect, request, url_for

import branding as B
import employee as EMP
import pipeline as P
import settings as S
from store import STORE
from dashboard import BASE_STYLES, _nav, rupees
from employee import active_employees, employees
from quotation import QUOTATION_STYLES

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")


# =============================================================================
# BUSINESS RULES
# =============================================================================

# CC-2's own divisor: "OT = (salary ÷ 8) × hours". It defines what one hour of
# a working day is, and it is not a rate anybody is paid at — which is why it
# is a constant here while the multiplier is a setting. If the client ever
# works a different standard day, this is the one line to change.
STANDARD_HOURS_PER_DAY = 8.0

# More than this in one day is a typo, not overtime — `employee.py`'s
# MAX_MONTHLY_SALARY guard, one field along. Twenty-four hours of overtime on
# top of a working day is not a shift anybody worked.
MAX_OT_HOURS = 16.0

PRESENT = "present"
ABSENT = "absent"
STATUSES = (PRESENT, ABSENT)


def records() -> dict:
    return STORE.setdefault("attendance", {})


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.date.today().isoformat()


def _esc(v) -> str:
    return P.esc(str(v or ""))


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# =============================================================================
# THE ARITHMETIC — every rate arrives as an argument
# =============================================================================
#
# ⚠ **Read the header before editing anything below.** No numeric constant may
# appear in a multiplication in this section: the OT multiplier and the wage
# divisor are both settings, and a literal here is the statutory-underpayment
# defect CC-2 names. `tests/test_attendance.py` walks the AST of these three
# functions and fails on one.

def day_rate_of(record) -> tuple:
    """
    `(rate, ok)` — what this marking's day rate is, and whether it may be used.

    ⚠ **There is no arithmetic here and that is the correction.** This used to
    be `daily_wage(monthly_salary, days_per_month)`, dividing a monthly figure
    by a divisor we invented. CC-2's `salary` is a **day rate**, so a day's wage
    is the stored figure and nothing else — the division was the bug, not the
    divisor's value.

    ⚠ **`ok` is False on a marking made under the old model**, and the rate is
    then `None` rather than zero. Zero is a figure somebody could have chosen; a
    wrong answer shaped like a right one is the thing this whole change exists
    to remove.
    """
    if EMP.is_pre_day_rate(record):
        return None, False
    return round(_num((record or {}).get("day_rate")), 2), True


def ot_amount(day_wage, hours, multiplier) -> float:
    """
    What overtime came to. `multiplier` is `settings.ot_multiplier()`.

    CC-2's formula is `(salary ÷ 8) × hours`, where *salary* is the **day**
    rate — which is what CC-2's own note means by calling it "1× ordinary
    rate", since `salary ÷ 8` is an hourly rate only on a daily figure. The
    multiplier CC-2 requires to be configurable rides on the end.

    ⚠ **`multiplier` is an argument and must stay one.** The client's figure is
    1×; the statutory rate is generally twice, and a `1` written into this
    function would compute an underpayment that nobody could see.
    """
    hourly = _num(day_wage) / STANDARD_HOURS_PER_DAY
    return round(hourly * _num(hours) * _num(multiplier), 2)


def cost_of(record, multiplier) -> dict:
    """
    `{"day", "ot", "total", "refused", "reason"}` for one marking.

    **"Salary as 0 or 1 based on attendance"** is CC-2's second bullet and it is
    this line: a present day earns one day's wage, an absent day earns none.

    ⚠ **A marking made under the old monthly model is REFUSED, not costed.**
    The three money keys come back `None` — never `0.0`, which would read as
    "this day cost nothing" and be silently added into a site total. Its stored
    snapshot is untouched: it is the record of what that day was assessed at,
    and recomputing history is the thing every freeze contract in this app
    exists to prevent (`proforma.prior_invoiced`, `ra.prev_balance`).

    ⚠ **Overtime on an absent day is nil, and that is a decision.** CC-2 does
    not say, and the two readings are "he was not there, so there is no
    overtime" and "the hours were typed, so pay them". The first is taken: an
    absentee with overtime hours is a marking somebody got wrong, and paying
    for hours on a day the register says nobody worked would be the more
    expensive mistake to make silently. The hours are still **stored and shown**
    so the contradiction is visible rather than swallowed.
    """
    wage, ok = day_rate_of(record)
    if not ok:
        return {"day": None, "ot": None, "total": None,
                "refused": True, "reason": EMP.PRE_DAY_RATE_REFUSAL}
    present = str(record.get("status") or "") == PRESENT
    day = wage if present else 0.0
    ot = ot_amount(wage, record.get("ot_hours"), multiplier) if present else 0.0
    return {"day": day, "ot": ot, "total": round(day + ot, 2),
            "refused": False, "reason": ""}


# =============================================================================
# READING THE COLLECTION
# =============================================================================

def records_on(date: str) -> list:
    """Every marking for one day, employee-name order."""
    day = str(date or "").strip()
    return sorted((r for r in records().values()
                   if str(r.get("date") or "") == day),
                  key=lambda r: str(r.get("employee_name") or "").lower())


def conflicting_record(employee_id: str, date: str, except_id: str = "") -> dict:
    """
    The existing marking that blocks this one, or `{}`.

    ⚠ **This is CC-2's "one employee = one site = one day" and it is the whole
    of it.** Keyed on `(employee, date)` and deliberately **not** on
    `(employee, site, date)` — see the header: the second reading lets one
    person be marked present on three sites on one day and bills a full day's
    wage three times, silently, on the only figure this module produces.

    Called by both write routes **before** anything is stored. A form that
    merely omits the name from a dropdown is a convenience; this is the rule.
    """
    eid = str(employee_id or "")
    day = str(date or "").strip()
    if not eid or not day:
        return {}
    for rid, r in records().items():
        if rid == except_id:
            continue
        if str(r.get("employee_id") or "") == eid and \
                str(r.get("date") or "") == day:
            return r
    return {}


def site_costs(date: str) -> list:
    """
    `[{site, people, present, ot_hours, day_cost, ot_cost, total, refused}, …]`
    for one day, site order — **CC-2's "site-wise labour cost"**.

    Computed live from the markings, never stored. A maintained total is a
    number one code path can forget to update, and this repo has paid for that
    twice — `ra.claimed_by_line()` and `challan.dispatched_by_line()` both
    derive for the same reason.

    ⚠ **A refused marking is COUNTED in `people` and `refused` and contributes
    nothing to the money.** Dropping it from `people` too would hide that
    somebody was on the site; folding its old monthly figure into `day_cost`
    would overstate the site by a factor of about twenty-six. Both halves are
    reported so the page can say the total is short and by how many people.
    """
    multiplier = S.ot_multiplier()

    buckets = {}
    for r in records_on(date):
        site = str(r.get("site") or "").strip() or "(no site named)"
        c = cost_of(r, multiplier)
        b = buckets.setdefault(site, {"site": site, "people": 0, "present": 0,
                                      "ot_hours": 0.0, "day_cost": 0.0,
                                      "ot_cost": 0.0, "total": 0.0,
                                      "refused": 0})
        b["people"] += 1
        if str(r.get("status") or "") == PRESENT:
            b["present"] += 1
            b["ot_hours"] += _num(r.get("ot_hours"))
        if c["refused"]:
            b["refused"] += 1
            continue
        b["day_cost"] = round(b["day_cost"] + c["day"], 2)
        b["ot_cost"] = round(b["ot_cost"] + c["ot"], 2)
        b["total"] = round(b["total"] + c["total"], 2)
    return [buckets[k] for k in sorted(buckets)]


# =============================================================================
# VALIDATION
# =============================================================================

def _validate(form, except_id: str = "") -> tuple:
    """
    `(data, error)` for the mark and edit forms.

    **Always returns data**, so a rejected form re-renders with what was typed
    and writes nothing — `address._validate()`'s contract, which this app holds
    to everywhere.
    """
    data = {
        "date":        (form.get("date") or "").strip()[:10],
        "employee_id": (form.get("employee_id") or "").strip(),
        "site":        (form.get("site") or "").strip()[:160],
        "status":      (form.get("status") or "").strip().lower(),
        "ot_raw":      (form.get("ot_hours") or "").strip(),
        "notes":       (form.get("notes") or "").strip()[:500],
    }

    if not data["date"]:
        return data, "A date is required — attendance is recorded daily."
    try:
        datetime.date.fromisoformat(data["date"])
    except ValueError:
        return data, "That is not a date this register can read (YYYY-MM-DD)."

    if not data["employee_id"]:
        return data, "Choose an employee."

    person = employees().get(data["employee_id"])
    if not person:
        return data, "That employee is not on the register any more."

    # ⚠ Checked on the RECORD, not on the dropdown. The picker lists active
    #   people only, so an inactive one cannot be chosen — but a posted id can
    #   name anybody, and somebody who has left cannot be marked present.
    if not person.get("active"):
        return data, (f"{person.get('name') or 'That employee'} is marked as no "
                      f"longer employed. Reactivate them on the employee "
                      f"register before recording attendance.")

    # ⚠ **Refused at the WRITE, not merely shown as unpriced afterwards.**
    #   A marking snapshots the rate, so recording one against an unconfirmed
    #   employee would mint a NEW record that is already old-model — which is
    #   exactly how the closed set grows, and `tests/test_day_rate_pin.py` would
    #   go red for a reason nobody could act on. The refusal names the person
    #   and the page that fixes it.
    if EMP.is_pre_day_rate(person):
        return data, (
            f"{P.esc(str(person.get('name') or 'That employee'))} has no "
            f"confirmed day rate. The figure on their record was entered when "
            f"this register held a MONTHLY salary, and it has not been "
            f"converted. Open their record on the employee register and type "
            f"the day rate first — marking the day now would record a wage "
            f"nobody chose.")

    if data["status"] not in STATUSES:
        return data, "Mark the day present or absent."

    raw = data["ot_raw"]
    if raw:
        try:
            hours = float(raw)
        except ValueError:
            return data, "Overtime hours: enter a number."
        if hours < 0:
            return data, "Overtime hours cannot be negative."
        if hours > MAX_OT_HOURS:
            return data, (f"Overtime hours: more than {int(MAX_OT_HOURS)} in "
                          f"one day is a typo, not a shift.")
    else:
        hours = 0.0
    data["ot_hours"] = round(hours, 2)

    clash = conflicting_record(data["employee_id"], data["date"], except_id)
    if clash:
        return data, (
            f"{P.esc(str(person.get('name') or 'That employee'))} is already "
            f"marked for {P.esc(data['date'])}, at "
            f"{P.esc(str(clash.get('site') or 'no site named'))}. "
            f"One employee, one site, one day — edit that record instead of "
            f"adding a second, or the same day's wage is counted twice.")

    data["person"] = person
    return data, ""


# =============================================================================
# CSS — screen only
# =============================================================================
# No print stylesheet and no `@media print` block: this module renders no
# document. A muster is not something that leaves this office.

ATTENDANCE_STYLES = """
<style>
  .att-table { width:100%; border-collapse:collapse; margin-top:1rem; }
  .att-table th {
    text-align:left; padding:.5rem; border-bottom:2px solid var(--border);
    font-size:.72rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.05em;
  }
  .att-table td {
    padding:.55rem .5rem; border-bottom:1px solid var(--border);
    font-size:.86rem; vertical-align:top;
  }
  .att-table tr:nth-child(even) { background:var(--surface); }
  .att-amt { text-align:right; font-variant-numeric:tabular-nums; }
  .att-sub { display:block; font-size:.76rem; color:var(--muted); }

  .att-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem; white-space:nowrap;
  }
  .att-in  { background:#E4F3E7; color:#1E6B2E; }
  .att-out { background:#EDECF1; color:#4B4459; }
  .att-row-out td { opacity:.72; }

  .att-note {
    background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--navy); border-radius:var(--radius);
    padding:.9rem 1.2rem; margin-bottom:1.4rem; font-size:.88rem;
  }
  .att-note b { color:var(--navy); }
  .att-note .an-sub { color:var(--muted); font-size:.82rem; margin-top:.25rem; }

  .att-card {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.2rem 1.4rem; margin-bottom:1.2rem;
  }
  .att-daybar {
    display:flex; gap:.7rem; align-items:flex-end; flex-wrap:wrap;
    margin-bottom:1.2rem;
  }
  .att-daybar .form-group { margin:0; }
  .field-hint {
    display:block; margin-top:.35rem; font-size:.76rem;
    color:var(--muted); line-height:1.45; font-weight:400;
    text-transform:none; letter-spacing:0;
  }
  .att-warn {
    background:#FFF6E5; border:1px solid #F0D8A8; border-left:3px solid var(--saffron);
    border-radius:var(--radius); padding:.7rem 1rem; margin:.8rem 0;
    font-size:.83rem;
  }

  /* The old-model band and the in-row refusal. Amber, which in this app means
     "incomplete but working": the marking is real and the day happened, and
     the one thing missing is a figure nobody may guess at. */
  .att-stale {
    background:#FFF6E5; border:1px solid #F0D8A8;
    border-left:3px solid var(--saffron); border-radius:var(--radius);
    padding:.8rem 1rem; margin:0 0 1.2rem; font-size:.84rem; line-height:1.55;
    color:#6B4E00;
  }
  .att-stale b { color:#8A5A00; }
  /* Sits where the money would be, so a reader never has to decide whether an
     empty cell means nil or means unknown. Nil is a figure; this is not. */
  .att-norate { color:#8A5A00; font-weight:600; font-size:.79rem;
                white-space:nowrap; }
</style>
"""


def _shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{ATTENDANCE_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
<footer><p>{B.COMPANY_NAME} &middot; {B.APP_SUBTITLE} &middot; attendance and labour cost</p></footer>
</main>
</body></html>"""


def _alert(msg: str, kind: str = "error") -> str:
    if not msg:
        return ""
    icon = "&#10003;" if kind == "success" else "&#10007;"
    return f'<div class="alert alert-{_esc(kind)}">{icon} {msg}</div>'


def _flash() -> str:
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "success" if request.args.get("type") == "success" else "error"
    return _alert(_esc(msg), kind)


# The one sentence that has to be on every page of this module.
NOT_PAYROLL = (
    "A labour cost tracker, not payroll. PF, ESIC, professional tax and "
    "minimum wages are not computed here and are not this software's.")


def _employee_options(selected: str) -> str:
    """Active employees only — `employee.active_employees()` is the accessor."""
    out = ['<option value="">— choose —</option>']
    for e in active_employees():
        sel = " selected" if e["id"] == selected else ""
        label = e.get("name") or "(unnamed)"
        code = str(e.get("code") or "").strip()
        if code:
            label = f"{label} ({code})"
        out.append(f'<option value="{_esc(e["id"])}"{sel}>{_esc(label)}</option>')
    return "".join(out)


def _site_of(employee_id: str) -> str:
    person = employees().get(str(employee_id or "")) or {}
    return str(person.get("site") or "")


# =============================================================================
# ROUTES
# =============================================================================

@attendance_bp.route("/")
def list_attendance():
    """
    One day's muster, and the site-wise labour cost underneath it.

    A **day** at a time, because that is the unit CC-2 records in and the unit
    the constraint is written on. `?date=` moves it; no argument means today.
    """
    date = (request.args.get("date") or "").strip() or _today()
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        date = _today()

    multiplier = S.ot_multiplier()
    rows = records_on(date)
    refused_here = 0

    if rows:
        body_rows = []
        for r in rows:
            c = cost_of(r, multiplier)
            present = str(r.get("status") or "") == PRESENT
            badge = ('<span class="att-badge att-in">Present</span>' if present
                     else '<span class="att-badge att-out">Absent</span>')
            code = str(r.get("employee_code") or "").strip()
            sub = f'<span class="att-sub">{_esc(code)}</span>' if code else ""
            hours = _num(r.get("ot_hours"))
            # An absentee carrying overtime hours is a contradiction, and it is
            # SHOWN rather than swallowed — see `cost_of()`.
            ot_cell = P.esc(f"{hours:g}")
            if hours and not present:
                ot_cell += ' <span class="att-sub">not paid — marked absent</span>'

            # ⚠ A refused marking shows a REASON where the money would be,
            #   spanning the three money columns. A blank cell would read as
            #   nil, and nil is a figure — the one thing this must not state.
            if c["refused"]:
                refused_here += 1
                money = (f'<td class="att-amt att-norate" colspan="3" '
                         f'title="{_esc(EMP.PRE_DAY_RATE_CHIP_TITLE)}">'
                         f'day rate not confirmed</td>')
            else:
                money = (f'<td class="att-amt">{rupees(c["day"])}</td>'
                         f'<td class="att-amt">{rupees(c["ot"])}</td>'
                         f'<td class="att-amt"><b>{rupees(c["total"])}</b></td>')

            body_rows.append(f"""
      <tr class="{'' if present else 'att-row-out'}">
        <td>{_esc(r.get('employee_name'))}{sub}</td>
        <td>{_esc(r.get('site')) or '<span class="att-sub">no site named</span>'}</td>
        <td>{badge}</td>
        <td class="att-amt">{ot_cell}</td>
        {money}
        <td>
          <a class="btn btn-ghost" href="{url_for('attendance.edit_attendance', id=r['id'])}">Edit</a>
          <a class="btn btn-ghost" href="{url_for('attendance.delete_attendance', id=r['id'])}">Delete</a>
        </td>
      </tr>""")
        table = f"""
    <table class="att-table">
      <thead><tr>
        <th>Employee</th><th>Site</th><th>Status</th>
        <th class="att-amt">OT hours</th><th class="att-amt">Day rate</th>
        <th class="att-amt">Overtime</th><th class="att-amt">Total</th><th></th>
      </tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>"""
    else:
        table = ('<p class="att-sub" style="margin-top:1rem;">Nobody is marked '
                 'for this day yet.</p>')

    stale_band = ""
    if refused_here:
        stale_band = f"""
  <div class="att-stale">
    <b>{refused_here} of this day's markings {"carries" if refused_here == 1
        else "carry"} a rate entered under the old monthly model, and
    {"it is" if refused_here == 1 else "they are"} left out of every total
    below.</b>
    This register held a <b>monthly salary</b> until 30 August 2026 and holds a
    <b>day rate</b> now. The stored snapshots have <b>not</b> been converted
    &mdash; a monthly figure read as a day's pay is about twenty-six times too
    big &mdash; so no wage is computed from them at all.
    Re-enter the rate on
    <a href="{url_for('employee.list_employees')}">the employee register</a>;
    markings recorded after that carry the new rate.
  </div>"""

    sites = site_costs(date)
    if sites:
        site_rows = "".join(f"""
      <tr>
        <td>{_esc(s['site'])}{
          f'<span class="att-sub">{s["refused"]} not costed &mdash; day rate '
          f'not confirmed</span>' if s['refused'] else ''}</td>
        <td class="att-amt">{s['present']} of {s['people']}</td>
        <td class="att-amt">{P.esc(f"{s['ot_hours']:g}")}</td>
        <td class="att-amt">{rupees(s['day_cost'])}</td>
        <td class="att-amt">{rupees(s['ot_cost'])}</td>
        <td class="att-amt"><b>{rupees(s['total'])}</b></td>
      </tr>""" for s in sites)
        day_total = round(sum(s["total"] for s in sites), 2)
        short_by = sum(s["refused"] for s in sites)
        site_panel = f"""
    <div class="att-card">
      <div class="section-title">Site-wise labour cost &mdash; {_esc(date)}</div>
      <table class="att-table">
        <thead><tr>
          <th>Site</th><th class="att-amt">Present</th>
          <th class="att-amt">OT hours</th><th class="att-amt">Day rate</th>
          <th class="att-amt">Overtime</th><th class="att-amt">Total</th>
        </tr></thead>
        <tbody>{site_rows}</tbody>
        <tfoot><tr>
          <td colspan="5" class="att-amt"><b>All sites</b></td>
          <td class="att-amt"><b>{rupees(day_total)}</b></td>
        </tr></tfoot>
      </table>
      <p class="att-sub" style="margin-top:.8rem;">
        Computed from this day's markings at
        <b>&times;{P.esc(f"{multiplier:g}")}</b> overtime, from
        <a href="{url_for('settings.edit_settings')}">Settings</a>. A day's wage
        is the employee's own <b>day rate</b> &mdash; there is no divisor and no
        monthly figure. Nothing is stored; change the multiplier and this page
        changes with it.{
          f' <b>This total is short by {short_by} '
          f'{"marking" if short_by == 1 else "markings"}</b> whose day rate is '
          f'not confirmed.' if short_by else ''}
      </p>
    </div>"""
    else:
        site_panel = ""

    return _shell("Attendance", f"""
  {_flash()}
  <div class="page-top">
    <h1>Attendance <span>&amp; labour cost</span></h1>
    <div style="display:flex;gap:.7rem;">
      <a href="{url_for('attendance.mark_attendance', date=date)}" class="btn">+ Mark a day</a>
      <a href="{url_for('employee.list_employees')}" class="btn btn-ghost">Employees</a>
    </div>
  </div>

  <div class="att-note">
    <b>One employee, one site, one day.</b> A second marking for the same person
    on the same day is refused rather than added &mdash; two records would count
    one day's wage twice.
    <div class="an-sub">{NOT_PAYROLL}</div>
  </div>

  {stale_band}

  <form method="GET" action="{url_for('attendance.list_attendance')}" class="att-daybar">
    <div class="form-group">
      <label for="date">Date</label>
      <input type="date" id="date" name="date" value="{_esc(date)}"/>
    </div>
    <button type="submit" class="btn btn-ghost">Show</button>
  </form>

  {table}
  {site_panel}
""")


def _form(data: dict, error: str, action: str, submit_label: str,
          back: str) -> str:
    """One form for mark and edit, so the two cannot drift apart."""
    eid = str(data.get("employee_id") or "")
    site = str(data.get("site") or "") or _site_of(eid)
    status = str(data.get("status") or PRESENT)
    return f"""
  {_alert(error) if error else ''}
  <div class="page-top">
    <h1>{_esc(submit_label)}</h1>
    <a href="{back}" class="btn btn-ghost">&#8592; Back</a>
  </div>

  <div class="att-note">
    <b>One employee, one site, one day.</b> If this person is already marked for
    this date the save is refused and the existing record is named &mdash; edit
    that one instead.
    <div class="an-sub">{NOT_PAYROLL}</div>
  </div>

  <form method="POST" action="{action}">
    <div class="form-section">
      <div class="section-title">The day</div>
      <div class="fg3">
        <div class="form-group">
          <label for="date">Date *</label>
          <input type="date" id="date" name="date" required
                 value="{_esc(data.get('date'))}"/>
        </div>
        <div class="form-group">
          <label for="employee_id">Employee *</label>
          <select id="employee_id" name="employee_id" required>
            {_employee_options(eid)}
          </select>
          <small class="field-hint">Active employees only. Somebody who has left
            cannot be marked &mdash; reactivate them on the register first.</small>
        </div>
        <div class="form-group">
          <label for="site">Site</label>
          <input type="text" id="site" name="site" maxlength="160"
                 value="{_esc(site)}" placeholder="where they worked that day"/>
          <small class="field-hint">Free text, prefilled from where this person
            is posted. It is deliberately <b>not</b> a project &mdash; one
            project runs at several sites.</small>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">Attendance and overtime</div>
      <div class="fg3">
        <div class="form-group">
          <label for="status">Present or absent *</label>
          <select id="status" name="status" required>
            <option value="present"{' selected' if status == PRESENT else ''}>Present</option>
            <option value="absent"{' selected' if status == ABSENT else ''}>Absent</option>
          </select>
          <small class="field-hint">A present day earns the employee's
            <b>day rate</b>; an absent day earns none. That is CC-2's
            <i>&ldquo;salary as 0 or 1 based on attendance&rdquo;</i>.</small>
        </div>
        <div class="form-group">
          <label for="ot_hours">Overtime hours</label>
          <input type="number" id="ot_hours" name="ot_hours" min="0"
                 max="{int(MAX_OT_HOURS)}" step="0.25"
                 value="{_esc(data.get('ot_raw'))}"/>
          <small class="field-hint">Paid at the day's hourly rate times the
            multiplier set in <a href="{url_for('settings.edit_settings')}">Settings</a>.
            Overtime on an <b>absent</b> day is recorded and not paid.</small>
        </div>
        <div class="form-group">
          <label for="notes">Notes</label>
          <input type="text" id="notes" name="notes" maxlength="500"
                 value="{_esc(data.get('notes'))}"/>
        </div>
      </div>
    </div>

    <div class="form-actions">
      <button type="submit" class="btn">{_esc(submit_label)}</button>
      <a href="{back}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
"""


@attendance_bp.route("/mark", methods=["GET", "POST"])
def mark_attendance():
    """Mark one person, on one site, for one day."""
    date = (request.args.get("date") or "").strip() or _today()
    data = {"date": date, "status": PRESENT}
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form)
        if not error:
            person = data["person"]
            rid = str(uuid.uuid4())
            records()[rid] = {
                "id":            rid,
                "date":          data["date"],
                "employee_id":   person["id"],
                # ⚠ Snapshotted, all three. A wage figure for a day already
                # worked must not move when somebody's salary is revised or
                # their name corrected — the freeze contract every document in
                # this app holds to (ABOUT.md §3). `cost_of()` reads the
                # snapshot; nothing re-reads the master.
                "employee_name": person.get("name") or "",
                "employee_code": person.get("code") or "",
                # ⚠ A DAY rate, snapshotted. It was `monthly_salary` until
                # 30 August 2026; markings written before that keep that key
                # and their number untouched, and carry the old-model marker.
                # A marking written HERE can never be old-model, because
                # `_validate()` refuses an employee whose rate is unconfirmed.
                "day_rate":      float(person.get("day_rate") or 0.0),
                "site":          data["site"],
                "status":        data["status"],
                "ot_hours":      data["ot_hours"],
                "notes":         data["notes"],
                "created_at":    _now(),
                "updated_at":    _now(),
            }
            return redirect(url_for("attendance.list_attendance",
                                    date=data["date"],
                                    msg="Attendance recorded.",
                                    type="success"))

    return _shell("Mark attendance", _form(
        data, error,
        action=url_for("attendance.mark_attendance"),
        submit_label="Mark attendance",
        back=url_for("attendance.list_attendance", date=data.get("date") or date)))


@attendance_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_attendance(id):
    """
    Correct a marking.

    ⚠ **The uniqueness check passes this record's own id as `except_id`**, so
    saving a record unchanged is not a clash with itself. That is the one way
    this constraint is usually got wrong, and it makes every edit refuse.
    """
    record = records().get(id)
    if not record:
        return redirect(url_for("attendance.list_attendance",
                                msg="No such attendance record.", type="error"))

    data = {
        "date":        record.get("date") or "",
        "employee_id": record.get("employee_id") or "",
        "site":        record.get("site") or "",
        "status":      record.get("status") or PRESENT,
        "ot_raw":      f"{_num(record.get('ot_hours')):g}",
        "notes":       record.get("notes") or "",
    }
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form, except_id=id)
        if not error:
            person = data["person"]
            record.update({
                "date":           data["date"],
                "employee_id":    person["id"],
                # Re-snapshotted on an edit, because an edit is a restatement
                # of what this day was: if the person changed, the name, code
                # and salary that go with them change too. An untouched edit
                # rewrites them to the same values.
                "employee_name":  person.get("name") or "",
                "employee_code":  person.get("code") or "",
                "day_rate":       float(person.get("day_rate") or 0.0),
                "site":           data["site"],
                "status":         data["status"],
                "ot_hours":       data["ot_hours"],
                "notes":          data["notes"],
                "updated_at":     _now(),
            })
            return redirect(url_for("attendance.list_attendance",
                                    date=data["date"],
                                    msg="Attendance updated.", type="success"))

    return _shell("Edit attendance", _form(
        data, error,
        action=url_for("attendance.edit_attendance", id=id),
        submit_label="Save attendance",
        back=url_for("attendance.list_attendance",
                     date=data.get("date") or record.get("date") or _today())))


@attendance_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_attendance(id):
    """
    ⚠ **GET confirms, POST destroys** — `9d060ee`'s shape and ABOUT.md §7.9f's
    standing rule for any new delete route.

    A browser `confirm()` is not a guard: a link-prefetching browser, a
    crawler, a mail scanner unfurling a pasted URL and the back button all
    issue a plain GET. `tests/test_delete_methods.py` sweeps `app.url_map` and
    catches a GET-**only** delete route, but says in terms that it cannot catch
    one accepting both verbs that still destroys on GET — so this route ships
    its own hand-written GET test, which is point 2 of that rule and is not
    optional.
    """
    record = records().get(id)
    if not record:
        return redirect(url_for("attendance.list_attendance",
                                msg="No such attendance record.", type="error"))

    date = record.get("date") or _today()

    if request.method == "POST":
        records().pop(id, None)
        return redirect(url_for("attendance.list_attendance", date=date,
                                msg="Attendance record deleted.",
                                type="success"))

    return _shell("Delete attendance", f"""
  <div class="page-top">
    <h1>Delete <span>attendance</span></h1>
    <a href="{url_for('attendance.list_attendance', date=date)}" class="btn btn-ghost">&#8592; Back</a>
  </div>

  <div class="att-card">
    <p>Remove the marking for
      <b>{_esc(record.get('employee_name'))}</b> at
      <b>{_esc(record.get('site')) or 'no site named'}</b> on
      <b>{_esc(date)}</b>?</p>
    <p class="att-sub">The day stops counting toward that site's labour cost.
      This is a correction, not a record of somebody's absence &mdash; mark them
      <b>absent</b> instead if that is what happened, which keeps the day on the
      register at nil cost.</p>
    <form method="POST" action="{url_for('attendance.delete_attendance', id=id)}"
          style="margin-top:1rem;display:flex;gap:.7rem;">
      <button type="submit" class="btn">Delete it</button>
      <a href="{url_for('attendance.list_attendance', date=date)}" class="btn btn-ghost">Cancel</a>
    </form>
  </div>
""")
