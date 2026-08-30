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
⚠ A MARKING SAYS WHICH PROJECT IT IS FOR — AND THE SITE STILL IS NOT ONE
════════════════════════════════════════════════════════════════════════════

Added 30 August 2026 under the **SIXTH** override block of that date. ⚠ **It is
not CC-2 scope**: C5's five bullets name no project, it belongs to PROGRESS.md
§4c, and nobody may cite it as a delivered CC-2 item.

**The problem it exists for.** `'Bangalore, Karnataka'` carries **four** live
projects, and folding the duplicate address on 30 August concentrated them there
rather than thinning them out. Every marking booked at that address answers for
all four, so `/projects/view/<id>` rendered the same money on four pages with a
note apologising for it. **The site is not a strong enough key to attribute
labour**, and a note is not a fix. So the marking carries the answer:

    project_id     the JOIN — an id somebody picked
    project_name   the LABEL, snapshotted at save

⚠ **This is `charge.py`'s shape and not a second one.** That ledger has stored
`project_id` beside a snapshotted `project_name` since it was written, and this
module reads `STORE["projects"]` directly exactly as it does — `charge → project`
is forbidden at AST level with the reason *"a charge reads STORE['projects']
directly"*, and **`attendance → project` is forbidden on the same terms.** The
one-way trick, used for the eighth time.

⚠ **AN ABSENT `project_id` MEANS LEGACY, NOT "NO PROJECT".** Nothing in this
application backfills it and **no third state marker is invented** —
`project.is_legacy_site()` reading the **shape** rather than a mark is the
precedent one collection along. `tools/backfill_marking_projects.py` is the bulk
mapping, and it is a tool an operator runs deliberately.

**The picker is filtered to the site, and the rules are three:**

| projects on the chosen site | what the form does |
|---|---|
| exactly one | ⚠ **preselected** — the common case costs no extra decision |
| more than one | ⚠ **a choice is REQUIRED to save.** Not defaulted, not the first, not the most recent |
| none | blank, and it **saves fine** — an office or a store belongs to no project |

Defaulting the middle row is the whole defect wearing a different hat: it would
put a day's labour against a project nobody chose, which is `po_parts.py`'s 156
invented aliases in a third register. `resolve_project()` owns all three, both
write routes call it, and the `<script>` on the form only re-renders options —
**a form is a convenience; the refusal is the rule.**

⚠ **A MARKING MAY NOT CARRY A PROJECT WHOSE SITE IS NOT THE MARKING'S SITE.**
`resolve_project()` takes the **resolved** site id, so changing the site drops a
`project_id` that no longer belongs to it before anything is stored — and a
hand-made POST naming a project at another address stores nothing.

⚠ **THIS DOES NOT UNBLOCK C6 AND NOTHING HERE MAY BE READ AS GROUNDWORK FOR
IT.** C6 is BLOCKED on CC-2's **Open question 4** — whether attendance wages or
the BOQ installation base rate is authoritative for labour cost. **Attributing a
day is not costing a project.** Open question 4 asks which figure is
authoritative; this asks which project a day was worked for, which is a fact
somebody on site knows. Recording the second does not answer the first, and no
margin, project total or net is built anywhere.

════════════════════════════════════════════════════════════════════════════
⚠ SITE IS AN ADDRESS-BOOK PICKER, AND IS STILL DELIBERATELY NOT A PROJECT
════════════════════════════════════════════════════════════════════════════

⚠ **It was free text until 30 August 2026 and that was the defect the owner
reported.** Free text is why one place is spelled more than one way across this
database, and a site-wise labour cost split across two spellings is wrong in a
way nobody notices, because both halves look right. The vocabulary lives in
`employee.py` — `site_field_html()`, `resolve_site()`, `unmapped_sites_in()` —
and this module reads it through the import it already has, so the two forms
cannot describe one field two ways.

⚠ **An existing string that matched nothing is LEFT, MARKED and REPORTED.** It
is never fuzzy-matched: a wrong automatic match moves labour cost to the wrong
site, which is `po_parts.py`'s 156 invented aliases in a different register.
The record carries `site_source == "unmapped"`, the row shows a chip, the
register shows a band listing every unmapped string, and mapping one is a
deliberate act on the edit form.

⚠ **A project is still not a site, and `site` is still NOT `project_id`.** The
marking now carries **both**, as two fields answering two questions, and the
reasons the site keeps its own field are unchanged:

1. **A project is not a site in this application's own data model.** A BOQ
   carries `project_name` **and** `site_location` as two separate fields
   (ABOUT.md §3). One project runs at several sites; one site can carry work
   for more than one project. Collapsing the two into one key would assert an
   identity the rest of the app already denies — and would make the filtered
   picker above impossible, because it is precisely a question about *which
   projects are at this site*.
2. **The employee master and the muster share one vocabulary**, which is the
   address book for both. Marking attendance against the field the master
   already carries is one vocabulary; marking it against a different entity is
   two. The project is a **third** field, not a replacement for either.
3. **The site is what the employee record can prefill**; the project is what
   only the person marking the day knows. That asymmetry is why one is
   defaulted and the other is asked for.

✅ **An address DOES join to a project, since 30 August 2026 (fourth pass).**
This paragraph used to read *"an address does not join to a project either …
site-wise labour cost cannot roll up to a project today"*, and it is corrected
rather than deleted, because the shortfall it named is what the field above
closes. `projects.site_address_id` is the link, and `projects_on_site()` below
is the whole of how this module reads it.

The form **prefills the employee's own posted site**, so the common case is
still one selection, and the project picker preselects when the site carries
exactly one project. No second site entity was invented and no project entity
was invented either — `STORE["projects"]` is read as it stands.

════════════════════════════════════════════════════════════════════════════
⚠ WHAT THIS MODULE DOES NOT DO — C6 IS BLOCKED AND STAYS BLOCKED
════════════════════════════════════════════════════════════════════════════

⚠ **THIS PARAGRAPH WAS TWO PASSES STALE AND IS CORRECTED RATHER THAN DELETED**,
because what it used to claim is the thing a reader must not carry away. It read:

    **Nothing here is exported and nothing consumes it.** The site-wise labour
    cost is displayed on **this module's own pages and nowhere else**. There is
    no figure on the dashboard, none on `/projects/view/<id>`, none in
    `charge.py`, and no function any other module calls. … and
    `tests/test_attendance.py` asserts at AST level that no module imports this
    one.

**Both of those stopped being true on 30 August 2026 (fifth pass)**, when the
Site Labour section was authorised: `projectview.py` imports this module and
`/projects/view/<id>` carries figures out of it. The guard was rewritten in the
same pass — `test_only_projectview_imports_the_attendance_module` is an
**allowlist of exactly one** — and this sentence was left behind. What still
stands, unweakened:

* the dashboard card is **counts only**;
* **`charge.py` is forbidden in both directions** and that has not moved;
* **`projectview.py` is the only importer**, it takes **rendered cells** —
  `marking_cells()`, `markings_at_site()`, and now `markings_for_project()` and
  `unattributed_at_site()` — and it may not reach `cost_of()`, `ot_amount()`,
  `day_rate_of()` or `site_costs()`. A second module able to compute a wage is a
  second place the OT multiplier could be hardcoded.

**C6 is BLOCKED on CC-2's Open question 4** — whether attendance-based wages or
the BOQ's installation base rate is authoritative for labour cost. Subtracting
both counts labour twice. ⚠ **The `project_id` above does not answer it**: it
records which project a day was worked for, not which figure is authoritative
for what that day cost. `projectview.py`'s standing prohibition — *"no revenue
total, no cost total, no margin, no profit, no net, no balance"* — is untouched,
and the two sums the Site Labour section now draws are two columns inside **one**
panel, which its first sentence has always permitted.

Imports, and why `settings` is on the list
------------------------------------------
```
attendance.py ──► employee.py   active_employees() — the master C4 shipped
attendance.py ──► settings.py   the OT multiplier and the wage divisor
attendance.py ──► dashboard, branding, pipeline, store, quotation
attendance.py ──► project.py    ⚠ NEVER. STORE["projects"] is read directly.
```

⚠ **`project.py` is forbidden and the marking still carries a `project_id`** —
which is not a contradiction, it is `charge.py`'s arrangement copied exactly.
`test_import_directions.py` already refuses `charge → project` with the reason
*"a charge reads STORE['projects'] directly"*, and it now refuses
`attendance → project` on the same terms. Importing the module would buy one
`.get("name")` and would pull `address.py` — and through it `product.py`'s
stylesheet — into the import graph of the muster, for a dict lookup. The link is
an id, a name and a `url_for`, and `STORE["projects"]` carries all three.

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
from dashboard import BASE_STYLES, REGISTER_STYLES, _nav, rupees
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


# =============================================================================
# THE PROJECT — an id somebody picked, filtered to the site
# =============================================================================
#
# ⚠ **`charge.py`'s shape, read the way `charge.py` reads it.** That ledger has
#   stored `project_id` beside a snapshotted `project_name` since it was
#   written, and it reaches `STORE["projects"]` directly rather than importing
#   `project.py` — `test_import_directions.py` refuses that arrow with the
#   reason *"a charge reads STORE['projects'] directly"*, and refuses this
#   module's on the same terms. One shape, two ledgers, no second pattern.

def projects_on_site(address_id) -> list:
    """
    Every project whose site is this address-book id, name order.

    ⚠ **A BLANK id matches NOTHING, and that guard is the whole function** —
    `markings_at_site()`'s rule, for the same reason one register along. An
    unmapped marking stores `site_address_id: ""` and so does a project with no
    site linked, so a plain `==` would offer **every unlinked project in the
    database** as a candidate for **every unmapped marking** — a join between two
    records that share only the fact that neither was ever filled in.

    ⚠ **It answers about the SITE, and the site is the filter the picker uses.**
    A project is not a site (see the header); this is the question *which
    projects are recorded at this place*, which is the only question the address
    can answer and the reason `site` keeps its own field.
    """
    aid = str(address_id or "").strip()
    if not aid:
        return []
    return sorted((p for p in (STORE.get("projects") or {}).values()
                   if str(p.get("site_address_id") or "").strip() == aid),
                  key=lambda p: str(p.get("name") or "").lower())


def resolve_project(form, site_address_id) -> tuple:
    """
    `(fields, error)` — the two project keys a marking carries, or why not.

    Takes the **resolved** site id rather than reading the form's, so the answer
    is always about the site the marking is actually being saved with.

    Four outcomes and no fifth:

    | posted | projects on that site | stored |
    |---|---|---|
    | one of them | any | `project_id` = the id, `project_name` = its name **snapshotted** |
    | not one of them | any | ⚠ **DROPPED** — see below |
    | blank | 0 or 1 | no project; both keys cleared |
    | blank | 2 or more | ⚠ **REFUSED.** A choice is required |

    ⚠ **Row 2 is how "changing the site clears a project that no longer belongs
    to it" is implemented, and it is a drop rather than a refusal on purpose.**
    The server cannot tell a re-picked site from a hand-made POST: both arrive as
    a `project_id` that is not at this address. Dropping it is safe in both
    readings — **the stored record can never carry a project whose site is not
    its own** — and the operator is not left staring at an error about a field
    the browser changed underneath them. Where the new site carries several
    projects the next rule then asks for a fresh choice, which is the honest
    prompt; where it carries one, the form has already preselected it.

    ⚠ **Row 4 is the point of the whole change and it is NOT defaulted.**
    `'Bangalore, Karnataka'` carries four projects. Picking the first, the newest
    or the only-one-that-looks-right would put a day's labour against a project
    nobody chose — silently, on the figure this module exists to produce.

    ⚠ **The NAME is snapshotted, not looked up**, exactly as `employee_name` and
    the site label beside it are. Renaming a project next March must not restate
    which project a day in August was worked for.
    """
    candidates = projects_on_site(site_address_id)
    by_id = {str(p.get("id")): p for p in candidates}

    posted = (form.get("project_id") or "").strip()[:64]
    chosen = by_id.get(posted)          # None for blank AND for "not here"

    if chosen is not None:
        return {"project_id": str(chosen.get("id")),
                "project_name": str(chosen.get("name") or "")}, ""

    if len(candidates) > 1:
        names = ", ".join(str(p.get("name") or "(unnamed)") for p in candidates)
        return {}, (
            f"{len(candidates)} projects are recorded at this site — {names}. "
            f"Choose which one this day was worked for. It is not defaulted: "
            f"this marking's wage appears on the project you pick, and picking "
            f"for you would put it against one nobody chose.")

    return {"project_id": "", "project_name": ""}, ""


def markings_for_project(project_id) -> list:
    """
    Every marking booked TO one project, newest day first.

    ⚠ **A BLANK id matches nothing** — `markings_at_site()`'s guard again, and
    here it is load-bearing twice over: a legacy marking carries no
    `project_id`, so `""` matching `""` would hand **every unattributed marking
    in the database** to any caller that lost track of its own id.
    """
    key = str(project_id or "").strip()
    if not key:
        return []
    return sorted((r for r in records().values()
                   if str(r.get("project_id") or "").strip() == key),
                  key=lambda r: (str(r.get("date") or ""),
                                 str(r.get("employee_name") or "").lower()),
                  reverse=True)


def unattributed_at_site(address_id) -> list:
    """
    Markings booked at one site that name **no project** — the legacy rows.

    ⚠ **Absent means LEGACY, not "no project", and this function does not claim
    to tell them apart.** It reads the shape — a marking at this site with an
    empty `project_id` — exactly as `project.is_legacy_site()` reads a project's,
    and no third state marker is invented to distinguish "nobody has mapped this
    yet" from "this genuinely belongs to no project". The page says what is true
    of both: they are booked here and attributed to nothing.
    """
    return [r for r in markings_at_site(address_id)
            if not str(r.get("project_id") or "").strip()]


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
                                      "refused": 0, "unmapped": False})
        # ⚠ A bucket is unmapped if ANY marking in it is. Buckets are keyed on
        #   the site STRING, so a mapped and an unmapped record can only share
        #   one when the strings are identical — which is the case a human has
        #   to look at, not one to hide.
        if EMP.is_unmapped_site(r):
            b["unmapped"] = True
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

def _validate(form, except_id: str = "", record=None) -> tuple:
    """
    `(data, error)` for the mark and edit forms.

    **Always returns data**, so a rejected form re-renders with what was typed
    and writes nothing — `address._validate()`'s contract, which this app holds
    to everywhere.
    """
    data = {
        "date":        (form.get("date") or "").strip()[:10],
        "employee_id": (form.get("employee_id") or "").strip(),
        # ⚠ Echoed back so a rejected form re-renders with the picker where
        #   the operator left it — `address._validate()`'s always-return-data
        #   contract, applied to a `<select>`.
        "site_id":     (form.get("site_id") or "").strip(),
        # ⚠ Echoed for the same reason `site_id` is: a rejected form re-renders
        #   with the picker where the operator left it. It is the RAW post —
        #   `resolve_project()` below is what decides whether it may be stored.
        "project_id":  (form.get("project_id") or "").strip(),
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

    site_fields, site_error = EMP.resolve_site(form, record)
    if site_error:
        return data, site_error
    data.update(site_fields)

    # ⚠ **The project is resolved AFTER the site and AGAINST it**, never against
    #   whatever the form happened to post as `site_id`. That ordering is the
    #   whole of "a marking may not carry a project whose site is not the
    #   marking's site": `resolve_project()` is handed the site that is about to
    #   be stored, so a project belonging to any other address cannot survive it.
    #   Re-picking the site therefore drops a stale project by construction
    #   rather than by a second check somebody has to remember to write.
    project_fields, project_error = resolve_project(
        form, site_fields.get(EMP.SITE_ADDRESS_FIELD))
    if project_error:
        return data, project_error
    data.update(project_fields)

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

# ⚠ **The CELL rules, extracted so two pages can render one marking the same
#   way.** `boqpick.PICKER_CSS` spliced into `po_draft.PO_STYLES` is the
#   precedent and `docsheet.BANK_CSS` is the older one: raw CSS in a constant,
#   spliced into this module's own sheet at the character position it has always
#   occupied, and wrapped afresh by the other consumer.
#
#   The other consumer is `projectview.py`'s Site Labour section, which composes
#   `marking_cells()` into a table of its own. Without these rules the status
#   pill, the sub-lines and the refusal cell arrive on that page as bare
#   unstyled text — which is precisely the defect this same pass fixed on
#   `/attendance/`, where `employee.py`'s chip classes were never loaded.
#
#   ⚠ **`.reg-sub-line` is deliberately NOT in here.** It is
#   `dashboard.REGISTER_STYLES`' rule, `marking_cells()` uses it only in the
#   **site** cell, and the project page renders no site column — every row in
#   that section is at the same site by construction. Copying the rule down here
#   would put a second definition of a shared class in the repo to serve a cell
#   nobody draws.
MARKING_CELL_CSS = """
  .att-sub { display:block; font-size:.76rem; color:var(--muted); }

  .att-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem; white-space:nowrap;
  }
  .att-in  { background:#E4F3E7; color:#1E6B2E; }
  .att-out { background:#EDECF1; color:#4B4459; }
  .att-row-out td { opacity:.72; }

  /* Sits where the money would be, so a reader never has to decide whether an
     empty cell means nil or means unknown. Nil is a figure; this is not. */
  .att-norate { color:#8A5A00; font-weight:600; font-size:.79rem;
                white-space:nowrap; }
"""

ATTENDANCE_STYLES = "\n<style>\n" + MARKING_CELL_CSS + """
  /* ⚠ `.att-table` and `.att-amt` are GONE, 30 August 2026. Both tables on
     this page use `dashboard.REGISTER_STYLES`' `.reg-table` and `.num`, which
     is what makes them one visual language rather than two — and what fixes
     the misalignment the owner reported: `.att-table th` was specificity
     (0,1,1) and beat `.att-amt` at (0,1,0), so every money HEADER sat left
     over a right-aligned column. `.reg-table th.num` is (0,2,1). Do not
     reintroduce a table style here; the pattern is shared on purpose. */

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
  /* ⚠ `.att-warn` is GONE, 30 August 2026 — it was declared and never used by
     a single element in this module, and `.att-stale` below is the amber band
     that is. A rule nobody renders is a rule the next reader has to check
     before changing anything near it. */

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
  /* ⚠ `.att-norate` moved into MARKING_CELL_CSS above, spliced back in at the
     position the cell rules have always occupied. It is a CELL rule and the
     project page's Site Labour section renders that cell too. */
</style>
"""


def _shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{REGISTER_STYLES}{ATTENDANCE_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
<footer><p>{B.COMPANY_NAME} &middot; {B.APP_SUBTITLE} &middot; attendance and labour cost</p></footer>
</main>
</body></html>"""


def marking_cells(record, multiplier) -> dict:
    """
    One marking's cells, rendered once and composed by whoever is drawing a row.

    ⚠ **This is an EXTRACTION, not a new renderer.** Every string below came out
    of `list_attendance()`'s row loop unchanged, because a second module wanted
    the same row and two copies of a money cell is how the four letterheads in
    ABOUT.md §2d drifted apart. The keys are cells, not a finished `<tr>`: the
    muster carries a Site column and an Actions column, and the project page's
    Site Labour section carries a Date column and neither of those — so the
    **composition** differs per page while the **cells** do not.

    Returns `employee`, `site`, `status`, `ot`, `money`, plus `row_class` and
    the `refused` flag its caller needs to count the shortfall.

    ⚠ **`money` is one string spanning three columns, and it has to be**: a
    refused marking renders a single `colspan="3"` reason cell where the three
    figures would go. A caller must therefore drop it in whole and must give the
    money block exactly three columns.

    ⚠ **Only `attendance.py` may compute a wage.** `multiplier` arrives as an
    argument for the reason `ot_amount()` takes one — the OT multiplier is a
    setting and a literal is a statutory underpayment — and a caller passes
    `settings.ot_multiplier()` rather than a figure of its own.
    """
    c = cost_of(record, multiplier)
    present = str(record.get("status") or "") == PRESENT

    badge = ('<span class="att-badge att-in">Present</span>' if present
             else '<span class="att-badge att-out">Absent</span>')
    code = str(record.get("employee_code") or "").strip()
    sub = f'<span class="att-sub">{_esc(code)}</span>' if code else ""

    hours = _num(record.get("ot_hours"))
    # An absentee carrying overtime hours is a contradiction, and it is
    # SHOWN rather than swallowed — see `cost_of()`.
    ot_cell = P.esc(f"{hours:g}")
    if hours and not present:
        ot_cell += ' <span class="att-sub">not paid — marked absent</span>'

    # ⚠ A refused marking shows a REASON where the money would be,
    #   spanning the three money columns. A blank cell would read as
    #   nil, and nil is a figure — the one thing this must not state.
    if c["refused"]:
        money = (f'<td class="num att-norate" colspan="3" '
                 f'title="{_esc(EMP.PRE_DAY_RATE_CHIP_TITLE)}">'
                 f'day rate not confirmed</td>')
    else:
        money = (f'<td class="num">{rupees(c["day"])}</td>'
                 f'<td class="num">{rupees(c["ot"])}</td>'
                 f'<td class="num"><b>{rupees(c["total"])}</b></td>')

    site = (_esc(record.get('site'))
            or '<span class="reg-sub-line">no site named</span>')

    return {
        "employee": f"{_esc(record.get('employee_name'))}{sub}",
        "site": f"{site}{EMP.unmapped_site_note(record)}",
        "status": badge,
        "ot": ot_cell,
        "money": money,
        "row_class": "" if present else "att-row-out",
        "refused": bool(c["refused"]),
        "total": c["total"],
    }


def markings_at_site(address_id: str) -> list:
    """
    Every marking booked at one address-book site, newest day first.

    ⚠ **A BLANK `address_id` MATCHES NOTHING, and that guard is the whole
    function.** An unmapped marking stores `site_address_id: ""` and so does a
    project with no site linked, so a plain `==` would put **every unmapped
    marking in the database** onto **every unlinked project's page** — a join
    between two records that share only the fact that neither was ever filled
    in. The caller's empty state says the project has no site linked; it says so
    because this returned nothing, not because the caller checked separately.

    ⚠ **This answers "booked at this SITE", never "belonging to this PROJECT".**
    Nothing on a marking names a project. Where several projects share one
    address the same markings answer for all of them, and saying which is C6 —
    BLOCKED on CC-2's Open question 4.
    """
    key = str(address_id or "").strip()
    if not key:
        return []
    return sorted((r for r in records().values()
                   if str(r.get("site_address_id") or "").strip() == key),
                  key=lambda r: (str(r.get("date") or ""),
                                 str(r.get("employee_name") or "").lower()),
                  reverse=True)


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


def _project_options(site_address_id, selected: str) -> str:
    """
    The project picker's `<option>` list for one site, and the three rules are
    visible in the placeholder rather than hidden in the validator.

    ⚠ **The placeholder's WORDING carries the rule.** *"— choose which project —"*
    on a site with several says a decision is owed; *"— none —"* on a site with
    one says leaving it is a real option; *"— no project at this site —"* says
    there is nothing to choose and the save will go through. A single generic
    placeholder would make the required case look optional, which is the one
    thing this control exists to prevent.

    ⚠ **The preselect happens HERE and only for a single candidate.** With two
    or more, `selected` is honoured if it is still one of them and otherwise
    nothing is chosen — never the first, never the newest.
    """
    projects = projects_on_site(site_address_id)
    ids = [str(p.get("id")) for p in projects]

    if not projects:
        placeholder = "— no project at this site —"
    elif len(projects) == 1:
        placeholder = "— none —"
    else:
        placeholder = "— choose which project —"

    keep = str(selected or "")
    if keep not in ids:
        # Not one of this site's projects: either the site was just changed, or
        # the marking predates the field. One candidate preselects; several do
        # not — `resolve_project()` refuses the blank and says why.
        keep = ids[0] if len(ids) == 1 else ""

    out = [f'<option value=""{"" if keep else " selected"}>'
           f'{_esc(placeholder)}</option>']
    for p in projects:
        pid = str(p.get("id"))
        sel = " selected" if pid == keep else ""
        out.append(f'<option value="{_esc(pid)}"{sel}>'
                   f'{_esc(p.get("name") or "(unnamed)")}</option>')
    return "".join(out)


def _projects_by_site_json() -> str:
    """
    `{site id: [[project id, project name], …]}` for the form's `<script>`.

    ⚠ **Through `pipeline.json_for_script()`, never `json.dumps`** — a project
    named with the seven characters `</script>` would otherwise close the block
    and every byte after it would be parsed as HTML (ABOUT.md §7.9e). A project
    name is free text somebody typed, which is exactly the input that rule
    exists for.

    ⚠ **This is a CONVENIENCE and carries no authority.** It re-renders the
    options when the site changes so the operator is not offered projects from
    somewhere else; `resolve_project()` is what refuses a save, and it re-reads
    `STORE["projects"]` rather than trusting anything that came back from the
    browser. A form is a convenience; the refusal is the rule.
    """
    out = {}
    for p in (STORE.get("projects") or {}).values():
        aid = str(p.get("site_address_id") or "").strip()
        if not aid:
            continue
        out.setdefault(aid, []).append([str(p.get("id")),
                                        str(p.get("name") or "(unnamed)")])
    for rows in out.values():
        rows.sort(key=lambda r: r[1].lower())
    return P.json_for_script(out)


def _site_of(employee_id: str) -> str:
    """
    The address-book id of where this person is posted, for the form's prefill.

    ⚠ It returns the **link**, not the label. Prefilling a picker needs an
    option value; the label is a snapshot the server takes at save from whatever
    was actually chosen. An employee whose own site is unmapped prefills nothing
    — there is no option to select — and the form opens with the picker blank,
    which is the honest state rather than a guess.
    """
    person = employees().get(str(employee_id or "")) or {}
    return str(person.get(EMP.SITE_ADDRESS_FIELD) or "")


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
            cells = marking_cells(r, multiplier)
            if cells["refused"]:
                refused_here += 1

            body_rows.append(f"""
      <tr class="{cells['row_class']}">
        <td>{cells['employee']}</td>
        <td>{cells['site']}</td>
        <td>{cells['status']}</td>
        <td class="num">{cells['ot']}</td>
        {cells['money']}
        <td class="reg-acts">
          <a class="reg-sub" href="{url_for('attendance.edit_attendance', id=r['id'])}">Edit</a>
          <a class="reg-danger" href="{url_for('attendance.delete_attendance', id=r['id'])}">Delete</a>
        </td>
      </tr>""")
        # ⚠ **`.num` is on every money HEADER as well as every money cell.**
        #   That is the misalignment the owner reported: the class was on both
        #   before, and `.att-table th { text-align:left }` (0,1,1) beat
        #   `.att-amt` (0,1,0), so every money header sat left over a
        #   right-aligned column. `dashboard.REGISTER_STYLES` carries
        #   `.reg-table th.num` at 0,2,1 and it wins.
        #
        # ⚠ **"Day rate" is the column's name in BOTH tables**, and the filter
        #   above is "Date". The page used to carry a DAY filter meaning a date,
        #   a DAY column meaning wages, and a DAY WAGES column meaning the same
        #   figure — one name for two things and two names for one.
        table = f"""
  <div class="reg-card">
    <div class="reg-head">
      <span class="reg-title">Muster &mdash; {_esc(date)}</span>
      <span class="reg-note">Who was on site, and what the day came to.</span>
    </div>
    <div class="reg-scroll">
    <table class="reg-table">
      <thead><tr>
        <th>Employee</th><th>Site</th><th>Status</th>
        <th class="num">OT hours</th><th class="num">Day rate</th>
        <th class="num">Overtime</th><th class="num">Total</th>
        <th class="reg-acts">Actions</th>
      </tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    </div>
  </div>"""
    else:
        table = """
  <div class="reg-card">
    <div class="reg-empty">Nobody is marked for this day yet.</div>
  </div>"""

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

    # ⚠ **The unmapped-site report, on the page rather than only in a tool.**
    #   A string nothing surfaces is a silent drop by another route: the labour
    #   cost is still attributed to a site nobody can find in the book, and
    #   nobody is ever told. It lists EVERY unmapped string across both
    #   collections, not only the ones on this day, because mapping is a job
    #   somebody does once rather than a day at a time.
    #   ⚠ Merged from the two collections HERE rather than inside
    #   `unmapped_sites_in()`, because `employee.py` may not name a C5 concept
    #   in code (`tests/test_employee.py` walks its source). This module may
    #   read `STORE["employees"]` — it already imports the module — so the merge
    #   belongs on the page that reports it.
    by_emp = EMP.unmapped_sites_in(employees())
    by_att = EMP.unmapped_sites_in(records())
    unmapped = {s: (len(by_emp.get(s, [])), len(by_att.get(s, [])))
                for s in sorted(set(by_emp) | set(by_att))}
    if unmapped:
        items = "".join(
            f'<li><b>{_esc(site)}</b> &mdash; '
            f'{n_emp} employee {"record" if n_emp == 1 else "records"}, '
            f'{n_att} {"marking" if n_att == 1 else "markings"}</li>'
            for site, (n_emp, n_att) in unmapped.items())
        unmapped_band = f"""
  <div class="att-stale">
    <b>{len(unmapped)} site
    {"string is" if len(unmapped) == 1 else "strings are"} not in the address
    book.</b> {_esc(EMP.UNMAPPED_SITE_NOTE)}
    <ul style="margin:.5rem 0 0 1.1rem;">{items}</ul>
    <div style="margin-top:.5rem;">Map one by opening the record and choosing
      the right address; add a missing site to the
      <a href="{url_for('address.list_addresses')}">address book</a> first.</div>
  </div>"""
    else:
        unmapped_band = ""

    sites = site_costs(date)
    if sites:
        site_rows = "".join(f"""
      <tr>
        <td>{_esc(s['site'])}{
          f'<span class="reg-sub-line">{s["refused"]} not costed &mdash; day '
          f'rate not confirmed</span>' if s['refused'] else ''}{
          EMP.unmapped_site_note_html() if s['unmapped'] else ''}</td>
        <td class="num">{s['present']} of {s['people']}</td>
        <td class="num">{P.esc(f"{s['ot_hours']:g}")}</td>
        <td class="num">{rupees(s['day_cost'])}</td>
        <td class="num">{rupees(s['ot_cost'])}</td>
        <td class="num"><b>{rupees(s['total'])}</b></td>
      </tr>""" for s in sites)
        day_total = round(sum(s["total"] for s in sites), 2)
        short_by = sum(s["refused"] for s in sites)
        # ⚠ **The same card, the same table, the same column names as the
        #   muster above.** The two used to be styled differently — the top one
        #   bare and the bottom one in a white card with a red header — which is
        #   two visual languages for one page of one kind of data.
        site_panel = f"""
  <div class="reg-card">
    <div class="reg-head">
      <span class="reg-title">Site-wise labour cost &mdash; {_esc(date)}</span>
      <span class="reg-note">CC-2's presentation table: employee, site, OT
        time.</span>
    </div>
    <div class="reg-scroll">
      <table class="reg-table">
        <thead><tr>
          <th>Site</th><th class="num">Present</th>
          <th class="num">OT hours</th><th class="num">Day rate</th>
          <th class="num">Overtime</th><th class="num">Total</th>
        </tr></thead>
        <tbody>{site_rows}</tbody>
        <tfoot><tr>
          <td colspan="5" class="num"><b>All sites</b></td>
          <td class="num"><b>{rupees(day_total)}</b></td>
        </tr></tfoot>
      </table>
    </div>
    <p class="reg-note" style="padding:.8rem 1.1rem;margin:0;">
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
  {unmapped_band}

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
          back: str, record: dict = None) -> str:
    """One form for mark and edit, so the two cannot drift apart."""
    eid = str(data.get("employee_id") or "")
    status = str(data.get("status") or PRESENT)
    # ⚠ The site is resolved ONCE and the project picker is filtered by that
    #   same value, so the two controls cannot open describing different sites.
    site_id = str(data.get("site_id") or "") or _site_of(eid)
    project_options = _project_options(site_id, data.get("project_id"))
    projects_by_site = _projects_by_site_json()
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
        {EMP.site_field_html(
            record, site_id,
            'Prefilled from where this person is posted. It is deliberately '
            '<b>not</b> the project &mdash; one project runs at several sites '
            'and one site can carry several projects, which is what the next '
            'field is for.')}
      </div>

      <div class="form-group">
        <label for="project_id">Project</label>
        <select id="project_id" name="project_id">{project_options}</select>
        <small class="field-hint">Which project this day was worked for.
          <b>Only the projects recorded at the site above are offered</b> &mdash;
          a marking may not name a project somewhere else. Where the site
          carries <b>one</b> project it is filled in for you; where it carries
          <b>several</b>, choosing is required, because picking for you would
          put this day&rsquo;s wage against a project nobody chose. Where it
          carries <b>none</b>, leave it &mdash; an office or a store belongs to
          no project.</small>
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

<script>
/* Re-render the project picker when the SITE changes, so the operator is never
   offered a project from somewhere else.

   ⚠ It runs on `change` and NOT on load. The server has already rendered the
     correct options — including the preselect, and including whatever a
     rejected form is echoing back — and re-deriving them here on load would
     make the browser the authority on a value the server just decided.

   ⚠ It decides NOTHING. `resolve_project()` re-reads STORE["projects"] and
     refuses the save; this only keeps the control honest while it is being
     used. The three placeholder wordings are the same three the server writes,
     because a control that says "— none —" under JS and "— choose which
     project —" without it is two forms. */
(function () {{
  var BY_SITE = {projects_by_site};
  var site = document.getElementById("site_id");
  var proj = document.getElementById("project_id");
  if (!site || !proj) {{ return; }}

  site.addEventListener("change", function () {{
    var list = BY_SITE[site.value] || [];
    var keep = proj.value;

    while (proj.firstChild) {{ proj.removeChild(proj.firstChild); }}

    var blank = document.createElement("option");
    blank.value = "";
    blank.textContent = list.length > 1 ? "\\u2014 choose which project \\u2014"
                      : list.length === 1 ? "\\u2014 none \\u2014"
                      : "\\u2014 no project at this site \\u2014";
    proj.appendChild(blank);

    var still = false, i;
    for (i = 0; i < list.length; i++) {{
      var o = document.createElement("option");
      o.value = list[i][0];
      /* textContent, never innerHTML — a project name is free text. */
      o.textContent = list[i][1];
      proj.appendChild(o);
      if (list[i][0] === keep) {{ still = true; }}
    }}

    /* One candidate preselects. Several never do — that is the decision the
       operator is being asked for, and defaulting it is the whole defect. */
    proj.value = still ? keep : (list.length === 1 ? list[0][0] : "");
  }});
}})();
</script>
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
                # ⚠ Three keys. `site` is the address LABEL snapshotted, for
                # the reason every other back-reference in this app is stored
                # rather than looked up: renaming an address next March must
                # not restate which site somebody worked on last August.
                "site":          data["site"],
                EMP.SITE_ADDRESS_FIELD: data[EMP.SITE_ADDRESS_FIELD],
                EMP.SITE_SOURCE_FIELD:  data[EMP.SITE_SOURCE_FIELD],
                # ⚠ Two keys, `charge.py`'s shape: the id somebody picked and
                # the name SNAPSHOTTED beside it. Both come out of
                # `resolve_project()` and neither is ever read off the form
                # directly, which is what guarantees the project stored here is
                # one of the projects at the site stored two lines up.
                "project_id":    data["project_id"],
                "project_name":  data["project_name"],
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
        "site_id":     str(record.get(EMP.SITE_ADDRESS_FIELD) or ""),
        # ⚠ The STORED project, echoed as it stands. A marking written before
        #   this field existed has none, and the form opens with the picker on
        #   whatever the site's own rule gives it — preselected where the site
        #   carries one project, and asking where it carries several. Nothing
        #   here backfills the record; saving the form is what writes one.
        "project_id":  str(record.get("project_id") or ""),
        "status":      record.get("status") or PRESENT,
        "ot_raw":      f"{_num(record.get('ot_hours')):g}",
        "notes":       record.get("notes") or "",
    }
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form, except_id=id, record=record)
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
                EMP.SITE_ADDRESS_FIELD: data[EMP.SITE_ADDRESS_FIELD],
                EMP.SITE_SOURCE_FIELD:  data[EMP.SITE_SOURCE_FIELD],
                # ⚠ Re-snapshotted like the three above, and **cleared when the
                # site moves**: `resolve_project()` was handed the new site, so
                # a project that belonged to the old one is already gone from
                # `data`. Writing it unconditionally is what makes that true of
                # the stored record rather than only of the form.
                "project_id":     data["project_id"],
                "project_name":   data["project_name"],
                "status":         data["status"],
                "ot_hours":       data["ot_hours"],
                "notes":          data["notes"],
                "updated_at":     _now(),
            })
            return redirect(url_for("attendance.list_attendance",
                                    date=data["date"],
                                    msg="Attendance updated.", type="success"))

    return _shell("Edit attendance", _form(
        data, error, record=record,
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
