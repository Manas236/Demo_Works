"""
employee.py — Employee Master  (CLIENT_CHANGES-2.md **C4**)
============================================================
Blueprint  : employee_bp
Mounted at : /employee  (registered in app.py)

Routes
------
  GET       /employee/                — the register
  GET,POST  /employee/new             — add an employee
  GET       /employee/view/<id>       — one employee's record
  GET,POST  /employee/edit/<id>       — change it
  GET,POST  /employee/delete/<id>     — GET confirms, POST destroys

What C4 is, and the whole of what it is
---------------------------------------
CLIENT_CHANGES-2.md **C4** reads, in full: *"Employee details and salary."*
That is the entire specification, and this module is the entire answer to it —
a register of people with what each is paid, and nothing else.

Built under the **29 August 2026** override block in `CLIENT_CHANGES.md` §0.
Before that block, C4 was one of the seven NOT STARTED items and was gated.

════════════════════════════════════════════════════════════════════════════
⚠ THE RATE IS A **DAY RATE**. IT WAS A MONTHLY SALARY AND THAT WAS OUR ERROR.
════════════════════════════════════════════════════════════════════════════

Corrected 30 August 2026 under the third override block of that date, after the
owner said that **Samruddhi pays daily or weekly, never monthly**.

The monthly reading was never CC-2's. Read C5's own two bullets together:

    - Salary as 0 or 1 based on attendance
    - OT = (salary ÷ 8) × hours

and CC-2's note on the second, which calls it **"1× ordinary rate"**. That is
only true if `salary ÷ 8` is an **hourly** rate — so `salary` is a **day's**
wage and 8 is hours in a day. On the monthly reading, one day present pays a
whole month's salary and `salary ÷ 8` is three days' pay per overtime hour.
**CC-2's `salary` was a day rate from the beginning.** `wage_days_per_month`,
the divisor invented to turn a monthly figure into a daily one, solved a
problem that never existed and is **deleted** rather than re-tuned.

⚠ **NO STORED FIGURE IS CONVERTED.** Rereading a monthly salary as a day rate
multiplies every wage by roughly twenty-six, and we do not know which records
were entered as what. So every employee that existed at the migration is
**marked** — `rate_model == PRE_DAY_RATE` — the page says on screen that the
rate needs re-entering, and `day_rate_of()` **refuses to answer** for a marked
record rather than answer wrongly. `attendance.cost_of()` reads that refusal and
produces no figure at all.

The marker is a **closed historical set**, exactly as `measurement.py`'s
pre-measurement pin is. `tools/backfill_day_rate.py` counts it and writes the
moment to `STORE["settings"]["day_rate_migration"]`;
`tests/test_day_rate_pin.py` fails if an employee created after that moment
carries the mark. Without that test the marker stops being a set somebody
counted and becomes a state any future record can fall into, which is the same
as not having the rule.

⚠ **The mark is never inferred from a missing `day_rate`.** It is read from the
explicit field and nothing else — `measurement.is_pre_measurement()`'s argument,
one register along: inferring it is precisely how a record written next year
through a route with a bug in it would quietly join a set closed in August.

⚠ **No pay-frequency field exists and none may be added without CC-2 asking for
one.** Weekly payment is a payout *cadence*, not a rate *unit*. Attendance is
recorded daily, so a day rate serves a daily payout and a weekly one alike.

⚠ **OUT OF SCOPE HERE, AND STILL TRUE OF THIS FILE:**

* **No attendance and no overtime in this module.** Presentee / absentee, OT
  and site-wise labour cost are **C5**, and C5 was authorised on 29 August 2026
  (third pass) — but it lives in its own module, [attendance.py](attendance.py),
  which imports this one. **Nothing was added here for it.** The register links
  out with `url_for`, which needs no import; importing back would be a cycle.
* **No wage calculation.** `day_rate` is a number recorded against a person.
  Nothing in *this* file multiplies, prorates or divides it — `attendance.py`
  reads the figure and does the arithmetic there, against an OT multiplier that
  is a **setting rather than a constant**.
* **No link to `charge.py` and none to a P&L.** `employee.py ↔ charge.py` stays
  forbidden in **both** directions at AST level, and that prohibition did *not*
  expire when C5 was authorised: joining the wages ledger to the people data is
  a profit-and-loss question and **C6 is BLOCKED** on CC-2's Open question 4.

A leaf, and one with no way in from the chrome
-----------------------------------------------
Imports `dashboard`, `branding`, `pipeline`, `store` and `quotation` — the same
five `charge.py` takes — **plus `address`, from 30 August 2026**, for the site
picker. `attendance.py` imports this module and reads the picker through it, so
the arrow to the address book is taken once rather than twice.
`po_draft.py` and `challan.py` already reach the same book the same way.
Nothing imports this module except `attendance.py`.

⚠ **`project` stays forbidden in both directions.** A site is an address, not a
project — the `addresses` record carries no project key and `projects` carries a
free-text `site_address` string, so the two do not join. Rolling site-wise
labour cost up to a project is **C6**, which is BLOCKED, and the shortfall is
recorded in ABOUT.md rather than worked around here.

✅ **IT IS NOW IN THE NAV AND ON THE LAUNCHER** (29 August 2026, third pass).
It shipped with neither, deliberately: `dashboard._nav()` is embedded in every
printed page and hidden by CSS, so one more nav entry moves **every print
golden in the repo**, and `charge.py` had shipped the same way for the same
reason. ⚠ **The cost of that call was that the owner could not find a page he
had paid for**, which is why it was reversed in a pass authorised to
re-baseline: five goldens moved +248 bytes each, in the `head` block alone, and
nothing on any printed sheet changed.

⚠ **Access: Owner, Director and HR only, and that restriction is SPEC-TRACED.**
CLIENT_CHANGES-2.md **B4** states exactly one per-role restriction — *"HR
information is restricted from Sales, Purchase and Accounts"* — and an employee
master carrying **salary** is that information in its plainest form. Sales
Manager, Purchase Manager and Accountant hold none of `employee.*`. That is not
a derivation and it is marked `§` in `docs/ACCESS_MATRIX.md`.

  ⚠ Note what B4 does **not** settle, because it is the next thing somebody
    will assume: CC-2's own *"Stated by the client, NOT in MG/SF/2026-02"*
    section records **HR editing salary** as untagged and unpriced, and the
    Accountant's *"overview of employees"* and *"manage employees and their
    site"* likewise. HR holds `employee.edit` here because an employee master
    somebody can read but nobody can maintain is not a master — but nobody may
    read that as the untagged item having been delivered. It has not been.

Escaping
--------
Every field on this record is typed by a user, and every one of them reaches
HTML. `P.esc` at the interpolation site, never a response filter, and never on
a money format (ABOUT.md §9).
"""

import datetime
import uuid

from flask import Blueprint, redirect, request, url_for

import address as AD
import branding as B
import pipeline as P
from store import STORE
from dashboard import BASE_STYLES, _nav, rupees
from quotation import QUOTATION_STYLES

employee_bp = Blueprint("employee", __name__, url_prefix="/employee")


# =============================================================================
# BUSINESS RULES
# =============================================================================

# A day rate bigger than this is a typo, not a rate — the same class of guard as
# `purchase.MAX_CHARGE_AMOUNT`.
#
# ⚠ **It moved with the unit and had to.** It was `MAX_MONTHLY_SALARY =
# 1000000.0`, and a guard sized for a month catches almost nothing on a day: a
# day rate with two stray zeros still walks through ten lakh. One lakh **a day**
# is already far beyond any site wage this register will see, so it still
# refuses nothing real. ⚠ **The number is OURS** — CC-2 gives no ceiling of any
# kind — and it is one line to change if a real rate is ever refused by it.
MAX_DAY_RATE = 100000.0

# ── The old-model marker, and why this module owns it ────────────────────────
#
# `attendance.py` imports this module and never the reverse (a cycle), so the
# vocabulary for "this rate was entered under the monthly model" lives here and
# is read there. That is `measurement.py` owning the marker `ra.py` renders,
# one register along.
RATE_MODEL_FIELD = "rate_model"
PRE_DAY_RATE = "pre_day_rate"

# Where the migration writes its moment and its count. Read by
# `tests/test_day_rate_pin.py`, which is what keeps the set closed.
PIN_KEY = "day_rate_migration"

PRE_DAY_RATE_NOTE = (
    "the figure on this record was entered when this register held a MONTHLY "
    "salary. It has not been converted and it will not be guessed at — a "
    "monthly figure read as a day rate is about twenty-six times too big. "
    "Open the record and type the day rate.")

PRE_DAY_RATE_CHIP_TITLE = (
    "Day rate not confirmed. This record carries a figure entered under the "
    "old monthly model and no wage is computed from it.")

PRE_DAY_RATE_REFUSAL = (
    "No wage is computed for this person until the day rate is re-entered. "
    "A figure here would be the old monthly salary read as a day's pay.")


def employees() -> dict:
    return STORE.setdefault("employees", {})


def migration_record() -> dict:
    """
    What `tools/backfill_day_rate.py` wrote, or `{}` on a database it has never
    been run against.

    ⚠ **Absent means the migration has not run**, and that is the honest answer
    rather than a default — a fresh database claiming a migration happened would
    measure every later record against a moment that never existed.
    """
    got = STORE.get("settings", {}).get(PIN_KEY)
    return got if isinstance(got, dict) else {}


def is_pre_day_rate(record) -> bool:
    """
    Whether this record carries a rate entered under the monthly model.

    ⚠ **Reads the explicit mark and nothing else.** Never `not record.get(
    "day_rate")`, and never "it has a `monthly_salary` key": inferring it is how
    a record written next year through a route with a bug in it joins a set that
    was closed in August. `measurement.is_pre_measurement()` makes the identical
    argument and for the identical reason.
    """
    return str((record or {}).get(RATE_MODEL_FIELD) or "") == PRE_DAY_RATE


def needs_rate_pin(record) -> bool:
    """
    Whether the migration would mark this record.

    True for a record that predates the day rate — it carries no `day_rate` and
    is not already marked. Idempotent by construction: a marked record is not
    marked twice.
    """
    if not isinstance(record, dict):
        return False
    if RATE_MODEL_FIELD in record:
        return False
    return "day_rate" not in record


def day_rate_of(record) -> tuple:
    """
    `(rate, ok)` — the one place anything asks what a person is paid a day.

    ⚠ **`ok` is False for a marked record and the rate is then `None`, not
    zero.** Zero is a figure somebody could have chosen (C4 permits a
    proprietor drawing nothing) and returning it here would be a wrong answer
    wearing a right answer's shape. Every caller has to handle the refusal,
    which is the point.
    """
    if is_pre_day_rate(record):
        return None, False
    try:
        return round(float((record or {}).get("day_rate") or 0.0), 2), True
    except (TypeError, ValueError):
        return None, False


def pre_day_rate_marker(record) -> str:
    """The on-screen band. One spelling, here, read by both this module and
    `attendance.py` — a second copy is a marker that says something different
    after the next edit."""
    if not is_pre_day_rate(record):
        return ""
    return ('<div class="emp-stale"><b>Day rate not confirmed.</b> '
            + _esc(PRE_DAY_RATE_NOTE) + '</div>')


def pre_day_rate_chip(record) -> str:
    """The register chip, same rule and same single spelling."""
    if not is_pre_day_rate(record):
        return ""
    return (f'<span title="{_esc(PRE_DAY_RATE_CHIP_TITLE)}" '
            f'class="emp-badge emp-stale-chip">RATE NOT CONFIRMED</span>')


# =============================================================================
# THE SITE — a picker over the ADDRESS BOOK, not free text
# =============================================================================
#
# Corrected 30 August 2026 under the third override block of that date. `site`
# was free text on this record and on an attendance marking, which is why the
# live data spells one place more than one way — `Banglore` here,
# `Bangalore, Karnataka` on a BOQ, `Sify Bangalore` as a project name. A
# site-wise labour cost that splits one site across two spellings is wrong in a
# way nobody notices, because both halves look right.
#
# ⚠ **This module owns the vocabulary and `attendance.py` reads it**, exactly as
#   it owns the old-model rate marker. `attendance.py` imports this file and
#   never the reverse, so one definition serves both forms and they cannot
#   describe one field two ways.
#
# ⚠ **It is deliberately NOT a link to a project**, and the prohibition
#   `test_import_directions.py` holds on `employee → project` is untouched. A
#   BOQ carries `project_name` *and* `site_location` as separate fields; one
#   project runs at several sites. A `project_id` here is the first half of
#   **C6**, which is BLOCKED.
#
#   ⚠ And an address does **not** join to a project in this application — the
#   `addresses` record has fourteen keys and none of them names one, while
#   `projects` carries a free-text `site_address` string. So site-wise labour
#   cost **cannot** roll up to a project today. That shortfall belongs to C6, it
#   is recorded in ABOUT.md rather than solved here, and nothing below pretends
#   otherwise.

SITE_ADDRESS_FIELD = "site_address_id"
SITE_SOURCE_FIELD = "site_source"
SITE_BOOK = "book"
SITE_UNMAPPED = "unmapped"

# ⚠ **Which address types may be a site, and the narrowing is OURS.** People
#   work at sites and at the office; a **vendor**'s address is somebody we buy
#   from, and offering it as a place somebody worked a shift would put labour
#   cost against a supplier. `billing` and `shipping` are where paperwork and
#   goods go, not where a fitter stands. It is one tuple to widen if a real site
#   turns out to be filed under another type — `address.picker_options()` takes
#   the same `only_types` argument `/purchase`'s vendor picker uses.
#
# ⚠ **MOVED to `address.py` on 30 August 2026 (fourth pass); this is an ALIAS.**
#   A project now takes its site from the same book, and `project.py` may not
#   import this module — `test_import_directions.py` forbids `employee → project`
#   and the reverse arrow would put the muster in the project's import graph. So
#   the tuple went one level down, to the module that owns the vocabulary and
#   that both of them already import. **Two pickers that can disagree about what
#   counts as a site is the defect**, and one definition is the fix. The name
#   stays here because `attendance.py` and `tools/backfill_site_links.py` read
#   it through this module; both keep working unchanged.
SITE_TYPES = AD.SITE_TYPES

UNMAPPED_SITE_NOTE = (
    "this site was typed as free text before the address book became the "
    "source, and nothing in the book matches it exactly. It has been left "
    "exactly as recorded rather than guessed at — a wrong match moves labour "
    "cost to the wrong site. Pick the right address to map it, or add it to "
    "the address book first.")

UNMAPPED_SITE_CHIP_TITLE = (
    "Site not in the address book. Recorded as free text and left as it "
    "stands; no wrong match has been guessed at.")


def site_options(selected: str = "") -> str:
    """The site picker's `<option>` list — `SITE_TYPES` only."""
    return AD.picker_options("— choose a site from the address book —",
                             only_types=SITE_TYPES, selected=selected)


def site_label_of(address_id: str) -> str:
    """
    The address's label, or `""` when the id names nothing.

    ⚠ **The label is SNAPSHOTTED onto the record**, alongside the id, for the
    reason `challan.py` snapshots its consignee and `ra.py` its party block: a
    marking is the record of a day that has happened, and renaming an address
    next March must not silently restate which site somebody worked on.
    """
    a = (STORE.get("addresses") or {}).get(str(address_id or "")) or {}
    return str(a.get("label") or "")


def is_unmapped_site(record) -> bool:
    """
    Whether this record's site is a free-text string nothing in the book
    matched.

    ⚠ **Reads the explicit mark**, never "it has a `site` and no
    `site_address_id`" — `is_pre_day_rate()`'s argument, and for the same
    reason. A record written through the picker today either carries a book
    link or carries no site at all, so an inferred mark could only ever be a
    guess about a record that predates the picker.
    """
    return str((record or {}).get(SITE_SOURCE_FIELD) or "") == SITE_UNMAPPED


def unmapped_sites_in(records) -> dict:
    """
    `{site string: [ids]}` — every site string in `records` a human still has to
    map.

    ⚠ **This is the report the migration promises and the pages render.** An
    unmapped string that nothing surfaces is a silent drop by another route: the
    figure is still attributed to a site nobody can find in the book, and nobody
    is ever told.

    ⚠ **It takes the collection as an ARGUMENT and names none.** This module is
    held by `tests/test_employee.py` to mentioning no C5 concept in code — C4 is
    details and a rate, and nothing else — so the muster passes its own
    collection in and merges the two answers on its own page. That is the same
    shape `boq.revision_blockers()` takes the claim map as an argument for, and
    for the same reason: the import direction, not taste.
    """
    out = {}
    for rid, r in (records or {}).items():
        if not is_unmapped_site(r):
            continue
        out.setdefault(str(r.get("site") or ""), []).append(rid)
    return out


def unmapped_site_chip(record) -> str:
    """The register chip. One spelling, here, read by both modules."""
    if not is_unmapped_site(record):
        return ""
    return (f'<span title="{_esc(UNMAPPED_SITE_CHIP_TITLE)}" '
            f'class="emp-badge emp-stale-chip">SITE NOT MAPPED</span>')


def resolve_site(form, record=None) -> tuple:
    """
    `(fields, error)` — turn a posted `site_id` into the three stored keys.

    Three outcomes and no fourth:

    | posted | stored |
    |---|---|
    | a real address id | `site` = its label, `site_address_id` = the id, `site_source` = `"book"` |
    | blank, on a record whose site is unmapped | ⚠ **the unmapped string is KEPT**, untouched |
    | blank, otherwise | no site — all three cleared |

    ⚠ **The middle row is the one that matters.** Leaving the picker alone on a
    record carrying `Banglore` must not silently delete `Banglore`: the string
    is evidence of where somebody worked, and the whole rule for this migration
    is that an unmapped string is left, marked and reported rather than dropped.
    Mapping it is a deliberate act, exactly as re-entering a day rate is.

    ⚠ An id that names **nothing** is refused rather than stored blank. A stored
    dangling id would be a link to a site that does not exist, which reads on
    every page as a mapped record and is not one.
    """
    posted = (form.get("site_id") or "").strip()

    if posted:
        label = site_label_of(posted)
        if not label:
            return {}, ("That site is not in the address book any more. Pick "
                        "another, or add it at the address book first.")
        return {"site": label,
                SITE_ADDRESS_FIELD: posted,
                SITE_SOURCE_FIELD: SITE_BOOK}, ""

    if record is not None and is_unmapped_site(record):
        return {"site": str(record.get("site") or ""),
                SITE_ADDRESS_FIELD: "",
                SITE_SOURCE_FIELD: SITE_UNMAPPED}, ""

    return {"site": "", SITE_ADDRESS_FIELD: "", SITE_SOURCE_FIELD: ""}, ""


def site_field_html(record=None, selected: str = "", hint_extra: str = "") -> str:
    """
    The picker plus whatever the record needs said about it — one definition,
    rendered on the employee form and on the attendance form, so the two cannot
    describe one field two ways.
    """
    unmapped = ""
    if record is not None and is_unmapped_site(record):
        unmapped = (
            f'<div class="emp-stale" style="margin:.5rem 0 0;">'
            f'<b>Recorded as &ldquo;{_esc(record.get("site"))}&rdquo;, which is '
            f'not in the address book.</b> {_esc(UNMAPPED_SITE_NOTE)} '
            f'Leaving the picker alone keeps it exactly as it is.</div>')

    return f"""
        <div class="form-group">
          <label for="site_id">Site</label>
          <select id="site_id" name="site_id">{site_options(selected)}</select>
          <small class="field-hint">From the <a
            href="{url_for('address.list_addresses')}">address book</a>, not
            typed. One site spelled two ways splits its labour cost in half
            without either half looking wrong.{
              ' ' + hint_extra if hint_extra else ''}</small>
          {unmapped}
        </div>"""


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.date.today().isoformat()


def _esc(v) -> str:
    return P.esc(str(v or ""))


def active_employees() -> list:
    """
    Every **active** employee, name order.

    The one accessor anything downstream should reach for. A deactivated
    employee stays on the register and stays in the database — the record of
    what somebody was paid does not stop being true when they leave — but they
    are not somebody you can assign work or a site to, so anywhere that means
    "pick a person", this is the list.
    """
    return sorted((e for e in employees().values() if e.get("active")),
                  key=lambda e: str(e.get("name") or "").lower())


def _code_taken(code: str, except_id: str = "") -> bool:
    """
    Whether an employee code is already in use.

    Codes are how a person is identified on a muster or a wage sheet, so two
    people holding one is the same defect as two customers sharing an invoice
    number. Compared case-insensitively, because `SF-01` and `sf-01` are one
    code written twice and nobody typing the second means a different person.
    """
    code = str(code or "").strip().lower()
    if not code:
        return False
    return any(str(e.get("code") or "").strip().lower() == code
               and eid != except_id
               for eid, e in employees().items())


def _validate(form, except_id: str = "", must_confirm_rate: bool = False,
              record=None) -> tuple:
    """
    `(data, error)` for the create and edit forms.

    A rejected form re-renders with what was typed and writes nothing — the
    `address._validate()` contract this app holds to everywhere.

    Required: a name, and a day rate that is a non-negative number.
    Everything else is optional, because a register nobody can add to until
    they have every field is a register that stays empty. **The rate may be
    zero** — a proprietor or a family member drawing nothing is real, and
    refusing it would force somebody to invent a figure.

    ⚠ **`must_confirm_rate` makes the rate REQUIRED, and it is passed exactly
    when the record being edited still carries the old monthly marker.** On
    every other record a blank means "nothing recorded" and reads as zero, which
    is C4's rule and stays. Here a blank would clear the marker while recording
    nothing, so the one record whose whole problem is an unconfirmed rate would
    end up confirmed at zero by somebody pressing Save.
    """
    data = {
        "name":        (form.get("name") or "").strip()[:120],
        "code":        (form.get("code") or "").strip()[:40],
        "designation": (form.get("designation") or "").strip()[:120],
        "date_joined": (form.get("date_joined") or "").strip()[:10],
        "salary_raw":  (form.get("day_rate") or "").strip(),
        "notes":       (form.get("notes") or "").strip()[:500],
        # ⚠ Echoed back so a rejected form re-renders with the picker where the
        #   operator left it — `address._validate()`'s always-return-data
        #   contract, applied to a `<select>` rather than an `<input>`.
        "site_id":     (form.get("site_id") or "").strip(),
        # An unchecked checkbox posts nothing at all, so this reads as False —
        # which is why the FORM ships it ticked on a new record. The default
        # lives where the field is created, not where it is read. Same rule
        # `purchase._parse_charges()` states for its taxable flag.
        "active":      bool(form.get("active")),
    }

    if not data["name"]:
        return data, "Employee name is required."
    if _code_taken(data["code"], except_id):
        return data, (f"Employee code '{data['code']}' is already used by "
                      f"somebody else. Codes identify a person on a wage "
                      f"sheet, so two people cannot share one.")

    site_fields, site_error = resolve_site(form, record)
    if site_error:
        return data, site_error
    data.update(site_fields)

    raw = data["salary_raw"]
    if raw:
        rate = P.parse_money(raw)
        if rate < 0:
            return data, "Day rate cannot be negative."
        if rate > MAX_DAY_RATE:
            return data, ("That day rate is larger than this register allows. "
                          "It is a rate for ONE DAY, not a month — check for a "
                          "stray zero.")
    elif must_confirm_rate:
        return data, ("Type this person's day rate before saving. The figure "
                      "already on the record is a MONTHLY salary and cannot be "
                      "carried over — leaving this blank would record a rate of "
                      "zero, not keep the old one.")
    else:
        rate = 0.0
    data["day_rate"] = round(rate, 2)

    return data, ""


# =============================================================================
# CSS — screen only
# =============================================================================
# No print stylesheet and no `@media print` block: this module renders no
# document. An employee record is not something that leaves this office.

EMPLOYEE_STYLES = """
<style>
  .emp-table { width:100%; border-collapse:collapse; margin-top:1rem; }
  .emp-table th {
    text-align:left; padding:.5rem; border-bottom:2px solid var(--border);
    font-size:.72rem; font-weight:700; color:var(--muted);
    text-transform:uppercase; letter-spacing:.05em;
  }
  .emp-table td {
    padding:.55rem .5rem; border-bottom:1px solid var(--border);
    font-size:.86rem; vertical-align:top;
  }
  .emp-table tr:nth-child(even) { background:var(--surface); }
  .emp-amt { text-align:right; font-variant-numeric:tabular-nums; }
  .emp-sub { display:block; font-size:.76rem; color:var(--muted); }

  /* Inactive is a state, not a deletion: the row stays and says so. */
  .emp-badge {
    display:inline-block; font-size:.68rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em;
    border-radius:10px; padding:.14rem .5rem; white-space:nowrap;
  }
  .emp-on  { background:#E4F3E7; color:#1E6B2E; }
  .emp-off { background:#EDECF1; color:#4B4459; }
  .emp-row-off td { opacity:.62; }

  /* The old-model marker. Amber, because this app's amber means "incomplete
     but working" — the person is on the register and everything about them
     reads correctly except the one figure nobody may guess at. */
  .emp-stale-chip { background:#FFF3D6; color:#7A5300; }
  .emp-stale {
    background:#FFF6E5; border:1px solid #F0D8A8;
    border-left:3px solid var(--saffron); border-radius:var(--radius);
    padding:.7rem 1rem; margin:.8rem 0; font-size:.84rem; line-height:1.55;
    color:#6B4E00;
  }
  .emp-stale b { color:#8A5A00; }
  /* A refusal sits where the money would have been, so a reader never has to
     work out whether a blank cell means nil or means unknown. */
  .emp-norate { color:#8A5A00; font-weight:600; font-size:.8rem;
                white-space:nowrap; }

  .emp-note {
    background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--navy); border-radius:var(--radius);
    padding:.9rem 1.2rem; margin-bottom:1.4rem; font-size:.88rem;
  }
  .emp-note b { color:var(--navy); }
  .emp-note .en-sub { color:var(--muted); font-size:.82rem; margin-top:.25rem; }

  .emp-card {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.2rem 1.4rem; margin-bottom:1.2rem;
  }
  .emp-grid {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:1rem 1.4rem;
  }
  .emp-lbl {
    font-size:.7rem; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted); margin-bottom:.15rem;
  }
  .emp-val { font-size:.95rem; font-weight:600; }
  .field-hint {
    display:block; margin-top:.35rem; font-size:.76rem;
    color:var(--muted); line-height:1.45; font-weight:400;
    text-transform:none; letter-spacing:0;
  }
</style>
"""


def _shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{EMPLOYEE_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
<footer><p>{B.COMPANY_NAME} &middot; {B.APP_SUBTITLE} &middot; employee master</p></footer>
</main>
</body></html>"""


def _alert(msg: str, kind: str = "error") -> str:
    if not msg:
        return ""
    icon = "&#10003;" if kind == "success" else "&#10007;"
    return f'<div class="alert alert-{_esc(kind)}">{icon} {_esc(msg)}</div>'


def _flash() -> str:
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "success" if request.args.get("type") == "success" else "error"
    return _alert(msg, kind)


# =============================================================================
# ROUTES
# =============================================================================

@employee_bp.route("/")
def list_employees():
    """
    The register. Active first, then inactive, each in name order.

    Inactive rows are **shown**, greyed and badged, rather than filtered out.
    Somebody who has left is still the person a past wage sheet names, and a
    register that hides them makes an old record unreadable.
    """
    show_all = request.args.get("all") == "1"
    rows = sorted(employees().values(),
                  key=lambda e: (not e.get("active"),
                                 str(e.get("name") or "").lower()))
    if not show_all:
        rows = [e for e in rows if e.get("active")]

    total_active = sum(1 for e in employees().values() if e.get("active"))
    total_all = len(employees())

    # ⚠ The daily total counts CONFIRMED rates only, and says how many it left
    #   out. Silently summing a marked record's monthly figure into a figure
    #   labelled "a day" is the exact error this whole change exists to undo.
    unconfirmed = sum(1 for e in employees().values()
                      if e.get("active") and is_pre_day_rate(e))
    daily = sum(day_rate_of(e)[0] or 0.0
                for e in employees().values()
                if e.get("active") and day_rate_of(e)[1])

    body = ""
    for e in rows:
        code_sub = (f'<span class="emp-sub">{_esc(e.get("code"))}</span>'
                    if e.get("code") else "")
        live = bool(e.get("active"))
        rate, ok = day_rate_of(e)
        rate_cell = (rupees(rate) if ok else
                     f'<span class="emp-norate">not confirmed</span>')
        body += (
            f'<tr class="{"" if live else "emp-row-off"}">'
            f'<td><b>{_esc(e.get("name"))}</b>{code_sub}</td>'
            f'<td>{_esc(e.get("designation")) or "&#8212;"}</td>'
            f'<td>{_esc(e.get("site")) or "&#8212;"}'
            f'{unmapped_site_chip(e)}</td>'
            f'<td>{_esc(e.get("date_joined")) or "&#8212;"}</td>'
            f'<td class="emp-amt">{rate_cell}</td>'
            f'<td><span class="emp-badge {"emp-on" if live else "emp-off"}">'
            f'{"Active" if live else "Inactive"}</span>'
            f'{pre_day_rate_chip(e)}</td>'
            f'<td><a class="btn btn-ghost" '
            f'href="{url_for("employee.view_employee", id=e.get("id"))}">Open</a></td>'
            f'</tr>')
    empty = ('<tr><td colspan="7" style="color:var(--muted);text-align:center;">'
             'Nobody on the register yet.</td></tr>')

    stale_band = ""
    if unconfirmed:
        stale_band = f"""
  <div class="emp-stale">
    <b>{unconfirmed} {"record carries" if unconfirmed == 1 else "records carry"}
    a rate entered under the old monthly model.</b>
    This register used to hold a <b>monthly salary</b>; it holds a
    <b>day rate</b> now. {_esc(PRE_DAY_RATE_NOTE)}
    Until each one is re-entered, no wage is computed from it anywhere &mdash;
    on this page or on the muster.
  </div>"""

    # ⚠ The unmapped-site report for THIS register's own records. A string that
    #   nothing surfaces is a silent drop by another route.
    unmapped = unmapped_sites_in(employees())
    unmapped_band = ""
    if unmapped:
        items = "".join(
            f'<li><b>{_esc(site)}</b> &mdash; {len(ids)} '
            f'{"record" if len(ids) == 1 else "records"}</li>'
            for site, ids in sorted(unmapped.items()))
        unmapped_band = f"""
  <div class="emp-stale">
    <b>{len(unmapped)} site {"string is" if len(unmapped) == 1 else
    "strings are"} not in the address book.</b>
    {_esc(UNMAPPED_SITE_NOTE)}
    <ul style="margin:.5rem 0 0 1.1rem;">{items}</ul>
    <div style="margin-top:.5rem;">Map one by opening the record and choosing
      the right address; add a missing site to the
      <a href="{url_for('address.list_addresses')}">address book</a> first.</div>
  </div>"""

    toggle = (f'<a href="{url_for("employee.list_employees")}" class="btn btn-ghost">Active only</a>'
              if show_all else
              f'<a href="{url_for("employee.list_employees", all=1)}" class="btn btn-ghost">'
              f'Show inactive too ({total_all - total_active})</a>')

    return _shell("Employees", f"""
  <div class="page-top">
    <h1>Employee <span>Master</span></h1>
    <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
      {toggle}
      <a href="{url_for('attendance.list_attendance')}" class="btn btn-ghost">Attendance</a>
      <a href="{url_for('employee.new_employee')}" class="btn">&#43; Add Employee</a>
    </div>
  </div>
  {_flash()}

  <div class="emp-note">
    Who works here, and what each is paid <b>a day</b>.
    <div class="en-sub">{total_active} active
      {"person" if total_active == 1 else "people"} &middot;
      {rupees(daily)} a day in wages{
        f" across the {total_active - unconfirmed} whose rate is confirmed"
        if unconfirmed else ""}.
      Wages here are <b>daily</b> &mdash; the register held a monthly salary
      until 30 August 2026 and that was our error, not the client's.
      This register records <b>details and the day rate only</b>; attendance,
      overtime and site-wise labour cost live on
      <a href="{url_for('attendance.list_attendance')}">Attendance</a>.</div>
  </div>
  {stale_band}
  {unmapped_band}

  <div class="form-section">
    <table class="emp-table">
      <thead><tr>
        <th>Name</th><th>Designation</th><th>Site</th><th>Joined</th>
        <th class="emp-amt">Day rate</th><th>Status</th><th></th>
      </tr></thead>
      <tbody>{body or empty}</tbody>
    </table>
  </div>
""")


def _form(data: dict, error: str, action: str, submit_label: str,
          heading: str, back: str, stale: dict = None,
          stale_site: dict = None) -> str:
    """The create and edit forms, which are one form with two labels."""
    checked = " checked" if data.get("active") else ""

    # ⚠ **A marked record opens with the rate box EMPTY and the old figure only
    #   named in the band above it.** Prefilling the box with the monthly
    #   salary under a label reading "Day rate" invites the operator to confirm
    #   a figure roughly twenty-six times too large by pressing Save, which is
    #   the whole failure this change exists to prevent. Re-entering has to be
    #   a deliberate act, so the box starts blank and `_validate()` refuses a
    #   blank on exactly this record.
    stale_band = ""
    if stale:
        old = stale.get("monthly_salary")
        old_txt = (f" The figure it carries is <b>{rupees(old)}</b>, recorded "
                   f"as a MONTHLY salary." if old not in (None, "") else "")
        stale_band = f"""
  <div class="emp-stale">
    <b>Type this person's day rate.</b>{old_txt}
    It has <b>not</b> been converted: we do not know whether it was entered as a
    month, a week or something else, and dividing it would put a guess on a wage
    sheet. Type what this person is paid <b>for one day</b> &mdash; do not divide
    the figure above.
  </div>"""

    return _shell(heading, f"""
  <div class="page-top">
    <h1>{heading}</h1>
    <a href="{back}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {_alert(error)}
  {stale_band}

  <form method="POST" action="{action}">
    <div class="form-section">
      <div class="section-title">Who</div>
      <div class="fg3">
        <div class="form-group">
          <label for="name">Name *</label>
          <input type="text" id="name" name="name" required maxlength="120"
                 value="{_esc(data.get('name'))}"/>
        </div>
        <div class="form-group">
          <label for="code">Employee Code</label>
          <input type="text" id="code" name="code" maxlength="40"
                 value="{_esc(data.get('code'))}" placeholder="e.g. SF-014"/>
          <small class="field-hint">How this person is identified on a muster or
            a wage sheet. Two people cannot share one.</small>
        </div>
        <div class="form-group">
          <label for="designation">Designation</label>
          <input type="text" id="designation" name="designation" maxlength="120"
                 value="{_esc(data.get('designation'))}"
                 placeholder="e.g. Fitter, Site Supervisor"/>
        </div>
        {site_field_html(stale_site, str(data.get('site_id') or ''),
                         'Where this person is posted — it prefills the '
                         'attendance form and is not a link to a project.')}
        <div class="form-group">
          <label for="date_joined">Date Joined</label>
          <input type="date" id="date_joined" name="date_joined"
                 value="{_esc(data.get('date_joined'))}"/>
        </div>
        <div class="form-group">
          <label for="day_rate">Day Rate (&#8377;){' *' if stale else ''}</label>
          <input type="number" id="day_rate" name="day_rate"
                 min="0" max="{int(MAX_DAY_RATE)}" step="0.01"
                 {'required' if stale else ''}
                 value="{_esc(data.get('salary_raw'))}"/>
          <small class="field-hint">What this person is paid for <b>one
            day</b> &mdash; not a month and not a week. Attendance multiplies it
            by the days worked and computes overtime from it; nothing on this
            page calculates anything.</small>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-title">Status</div>
      <div class="form-group">
        <label style="display:flex;gap:.5rem;align-items:center;text-transform:none;font-weight:500;">
          <input type="checkbox" name="active" value="1"{checked}/>
          <span>Currently employed</span>
        </label>
        <small class="field-hint">Untick when somebody leaves. The record stays
          on the register &mdash; what they were paid does not stop being true
          &mdash; but they no longer appear where a person is picked.</small>
      </div>
      <div class="form-group">
        <label for="notes">Notes</label>
        <input type="text" id="notes" name="notes" maxlength="500"
               value="{_esc(data.get('notes'))}"/>
      </div>
    </div>

    <div class="form-actions">
      <button type="submit" class="btn">{_esc(submit_label)}</button>
      <a href="{back}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
""")


@employee_bp.route("/new", methods=["GET", "POST"])
def new_employee():
    """Add somebody to the register."""
    # A new record ships ACTIVE — you are adding somebody who works here. The
    # default lives here, in the form, because an unchecked box posts nothing.
    data = {"date_joined": _today(), "active": True}
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form)
        if not error:
            eid = str(uuid.uuid4())
            employees()[eid] = {
                "id":          eid,
                "name":        data["name"],
                "code":        data["code"],
                "designation": data["designation"],
                # ⚠ Three keys, not one. `site` is the address LABEL
                # snapshotted, `site_address_id` is the link, and
                # `site_source` says which of `resolve_site()`'s three
                # outcomes applied.
                "site":             data["site"],
                SITE_ADDRESS_FIELD: data[SITE_ADDRESS_FIELD],
                SITE_SOURCE_FIELD:  data[SITE_SOURCE_FIELD],
                "date_joined": data["date_joined"],
                # ⚠ A DAY rate. A record written here carries no `rate_model`
                # key at all, which is what `tests/test_day_rate_pin.py` sweeps
                # for: an employee created after the migration must never carry
                # the old-model marker, or the closed set has grown.
                "day_rate":    data["day_rate"],
                "active":      data["active"],
                "notes":       data["notes"],
                "created_at":  _now(),
                "updated_at":  _now(),
            }
            return redirect(url_for("employee.view_employee", id=eid,
                                    msg=f"{data['name']} added to the register.",
                                    type="success"))

    return _form(data, error, action=url_for("employee.new_employee"),
                 submit_label="Add employee", heading="New <span>Employee</span>",
                 back=url_for("employee.list_employees"))



@employee_bp.route("/view/<id>")
def view_employee(id: str):
    """One person's record."""
    e = employees().get(id)
    if not e:
        return redirect(url_for("employee.list_employees",
                                msg="Employee not found.", type="error"))

    badge = ('<span class="emp-badge emp-on">Active</span>' if e.get("active")
             else '<span class="emp-badge emp-off">Inactive</span>')

    def cell(label, value):
        return (f'<div><div class="emp-lbl">{label}</div>'
                f'<div class="emp-val">{value or "&#8212;"}</div></div>')

    rate, ok = day_rate_of(e)
    rate_cell = (cell("Day rate", rupees(rate)) if ok else
                 cell("Day rate",
                      '<span class="emp-norate">not confirmed</span>'))

    return _shell(str(e.get("name")), f"""
  <div class="page-top">
    <h1>{_esc(e.get('name'))} {badge}</h1>
    <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
      <a href="{url_for('employee.list_employees')}" class="btn btn-ghost">All Employees</a>
      <a href="{url_for('employee.edit_employee', id=id)}" class="btn btn-ghost">Edit</a>
      <a href="{url_for('employee.delete_employee', id=id)}" class="btn btn-ghost">Delete</a>
    </div>
  </div>
  {_flash()}
  {pre_day_rate_marker(e)}

  <div class="emp-card">
    <div class="emp-grid">
      {cell("Employee code", _esc(e.get("code")))}
      {cell("Designation", _esc(e.get("designation")))}
      {cell("Site", _esc(e.get("site")) + unmapped_site_chip(e))}
      {cell("Date joined", _esc(e.get("date_joined")))}
      {rate_cell}
      {cell("Status", "Currently employed" if e.get("active") else "No longer employed")}
    </div>
  </div>

  {f'<div class="emp-card">{cell("Notes", _esc(e.get("notes")))}</div>' if e.get("notes") else ""}

  <div class="emp-note">
    <b>Details and the day rate only.</b>
    <div class="en-sub">The rate above is what this person is paid for
      <b>one day</b>. Nothing on this page computes anything from it &mdash;
      <a href="{url_for('attendance.list_attendance')}">Attendance</a> is where a
      day worked becomes a figure, and it reads this record rather than the
      other way round.</div>
  </div>
""")


@employee_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_employee(id: str):
    """Change somebody's record."""
    e = employees().get(id)
    if not e:
        return redirect(url_for("employee.list_employees",
                                msg="Employee not found.", type="error"))

    # ⚠ Read BEFORE the POST branch writes, because saving clears the mark and
    #   the band has to be decided on the state the operator was shown.
    stale = dict(e) if is_pre_day_rate(e) else None

    stale_site = dict(e) if is_unmapped_site(e) else None

    data = dict(e)
    data["site_id"] = str(e.get(SITE_ADDRESS_FIELD) or "")
    # ⚠ A marked record's box starts BLANK — see `_form()`. The old monthly
    #   figure is shown in the band, never in a box labelled "Day rate".
    data["salary_raw"] = ("" if stale else
                          f"{float(e.get('day_rate') or 0.0):.2f}"
                          if e.get("day_rate") else "")
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form, except_id=id,
                                must_confirm_rate=bool(stale), record=e)
        if not error:
            e.update({
                "name":        data["name"],
                "code":        data["code"],
                "designation": data["designation"],
                # ⚠ Three keys, not one. `site` is the address LABEL
                # snapshotted, `site_address_id` is the link, and
                # `site_source` says which of `resolve_site()`'s three
                # outcomes applied.
                "site":             data["site"],
                SITE_ADDRESS_FIELD: data[SITE_ADDRESS_FIELD],
                SITE_SOURCE_FIELD:  data[SITE_SOURCE_FIELD],
                "date_joined": data["date_joined"],
                "day_rate":    data["day_rate"],
                "active":      data["active"],
                "notes":       data["notes"],
                "updated_at":  _now(),
            })
            # ⚠ **Confirming the rate ends the old model for this record, and
            #   the superseded monthly figure goes with the marker.** Leaving
            #   `monthly_salary` behind would leave two rate fields on one
            #   record with nothing saying which is live — the next reader picks
            #   one, and half the time it is the wrong one. Every old figure is
            #   printed and recorded by `tools/backfill_day_rate.py` before it
            #   marks anything, and the pre-migration `mysqldump` holds them all.
            if stale:
                e.pop(RATE_MODEL_FIELD, None)
                e.pop("monthly_salary", None)
            return redirect(url_for("employee.view_employee", id=id,
                                    msg="Record updated.", type="success"))

    return _form(data, error, action=url_for("employee.edit_employee", id=id),
                 submit_label="Save changes",
                 heading="Edit <span>Employee</span>",
                 back=url_for("employee.view_employee", id=id),
                 stale=stale, stale_site=stale_site)


@employee_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_employee(id: str):
    """
    Remove somebody from the register.

    ⚠ **GET renders a confirmation and mutates NOTHING; only the POST branch
      destroys.** That is `9d060ee`'s shape and this repo's standing rule
      (ABOUT.md §7.9f): a browser `confirm()` is not a guard, because a
      link-prefetching browser, a crawler, a mail scanner unfurling a pasted URL
      and the back button all issue a plain GET.

    The confirmation offers **deactivating instead**, and says why: a person who
    has left is not a mistake to erase. Deleting is for a row entered in error.
    """
    e = employees().get(id)
    if not e:
        return redirect(url_for("employee.list_employees",
                                msg="Employee not found.", type="error"))

    if request.method == "POST":
        employees().pop(id, None)
        return redirect(url_for("employee.list_employees",
                                msg=f"{e.get('name')} removed from the register.",
                                type="success"))

    return _shell("Delete Employee", f"""
  <div class="page-top"><h1>Delete <span>Employee</span></h1></div>
  <div class="del-box">
    <h2>&#9888; This cannot be undone</h2>
    <div class="del-line">
      You are about to delete <b>{_esc(e.get('name'))}</b>
      {f"({_esc(e.get('code'))})" if e.get("code") else ""}
      and the salary recorded against them.
    </div>
  </div>
  <div class="emp-note">
    <b>If this person has left, deactivate them instead.</b>
    <div class="en-sub">An inactive employee stays on the register and stops
      appearing where a person is picked. Deleting is for a row entered by
      mistake &mdash; it removes the record of what somebody was paid.</div>
  </div>
  <form method="POST" action="{url_for('employee.delete_employee', id=id)}"
        style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <button type="submit" class="btn">Delete this record</button>
    <a href="{url_for('employee.edit_employee', id=id)}" class="btn btn-ghost">Deactivate instead</a>
    <a href="{url_for('employee.view_employee', id=id)}" class="btn btn-ghost">Keep it</a>
  </form>
""")
