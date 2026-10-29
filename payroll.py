"""
payroll.py — the pay ledger and the monthly PAYSLIP
====================================================
Blueprint  : payroll_bp
Mounted at : /payroll  (registered in app.py)

Routes
------
  GET       /payroll/                         — one month: every person, their slip
  POST      /payroll/generate                 — create the month's missing drafts
  GET       /payroll/slip/<id>                — one slip, and its actions
  POST      /payroll/slip/<id>/extras         — a draft's typed figures
  POST      /payroll/slip/<id>/refresh        — re-snapshot a draft
  POST      /payroll/slip/<id>/issue          — freeze it (and carry a shortfall)
  GET,POST  /payroll/slip/<id>/cancel         — GET asks for a reason, POST cancels
  GET       /payroll/slip/print/<id>          — the printed payslip
  GET       /payroll/print-month              — every issued slip of a month
  GET       /payroll/entries                  — the pay ledger, and the add form
  POST      /payroll/entries/add              — one advance / travel / loan line
  GET,POST  /payroll/entries/edit/<id>        — correct one
  GET,POST  /payroll/entries/delete/<id>      — GET confirms, POST destroys

What this is — CLIENT_CHANGES.md §0, the FIFTY-FIFTH block (29 October 2026)
---------------------------------------------------------------------------
⚠ **CHARGED NEW SCOPE, price not yet agreed.** The client's own payslip
(`Salary Slip Format.xlsx`), drawn from the muster. ``attendance.py`` stays a
labour cost tracker and says so; THIS module is the payslip.

The client's slip, and the arithmetic here, line for line:

    Basic           = the day wages of the month   (attendance, per day's rate)
    OT Payment      = the overtime of the month    (attendance, the setting's multiplier)
    Travelling Exp. = the month's travel entries
    Gross           = Basic + Other Allowance + OT Payment + Travelling
    Total Deduction = Salary Advance + Loan Deduction + MLWF + PF + ESIC + PT
    Net             = Gross − Total Deduction, rounded to the RUPEE, half up

⚠ **THE WAGE IS NOT COMPUTED HERE.** Basic and OT come out of
`attendance.month_figures()`, which prices every marking with the muster's
own wage function at the OT-multiplier setting. This is the THIRD module
allowed to import `attendance.py` and it takes readers only — the wage
functions are refused to it by `tests/test_attendance.py`, on `pnl.py`'s
terms: a second module able to compute a wage is a second place the OT
multiplier could be hardcoded.

⚠ **TWO BUGS IN THE CLIENT'S SLIP ARE FIXED, NOT COPIED.**
1. Their Total Deduction formula leaves out MLWF, PF, ESIC and PT, so a figure
   typed in one of them prints and is not deducted. Here it is deducted.
   ⚠ **None of the four is COMPUTED.** HR types them on a draft;
   MG/SF/2026-02 §5 leaves statutory matters with the client.
2. Their loan cells point at the wrong columns. Here *Loan* is what was owed
   before this month, *Loan Deduction* is this month's, and *Loan Balance* is
   the first minus the second.

⚠ **THE LOAN BALANCE IS DERIVED, NEVER STORED.** `ra.claimed_by_line()`'s rule
and the receipts ledger's: a stored balance is wrong the moment an earlier
entry is corrected. A deduction larger than the balance WARNS and never
blocks — the receipts ledger's overpayment rule — and the balance goes signed.

⚠ **A SLIP SNAPSHOTS EVERYTHING AND PRINTS FROM ITS OWN ROWS**
(CLIENT_CHANGES.md §1.2). A draft can be refreshed; an issued slip never moves,
and if what it was drawn from changes afterwards the slip shows an amber band
naming both figures rather than restating itself.

⚠ **ADVANCE BIGGER THAN THE WAGES** (Manas, 29 October 2026): the slip pays ₹0
and ISSUING it writes the shortfall as an advance dated the 1st of the next
month (`source = "carry:<slip id>"`). Cancelling the slip removes that entry,
and is refused once the next month's slip is issued. A carried entry is never
edited or deleted from the ledger — only by cancelling its slip.

Imports
-------
```
payroll.py ──► attendance.py   month_figures(), employees_marked_in() — readers
payroll.py ──► employee.py     the master, for name / code / designation
payroll.py ──► docsheet.py     the shared printed sheet
payroll.py ──► auth.py         has_perm() — which buttons to draw
```
Nothing imports this module but `app.py` and `payimport.py`.
"""

import calendar
import datetime
import uuid
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, has_request_context, redirect, request, url_for

import attendance as AT
import auth
import branding as B
import docsheet as DS
import employee as EMP
import pipeline as P
from chrome import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES, _inr
from store import STORE

payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")


# =============================================================================
# VOCABULARY
# =============================================================================

ADVANCE = "advance"
TRAVEL = "travel"
LOAN_GIVEN = "loan_given"
LOAN_DEDUCTION = "loan_deduction"
OPENING_LOAN = "opening_loan"
ENTRY_TYPES = (ADVANCE, TRAVEL, LOAN_GIVEN, LOAN_DEDUCTION, OPENING_LOAN)
ENTRY_LABELS = {
    ADVANCE:        "Salary advance",
    TRAVEL:         "Travelling expenses",
    LOAN_GIVEN:     "Loan given",
    LOAN_DEDUCTION: "Loan deduction",
    OPENING_LOAN:   "Opening loan balance",
}
LOAN_UP = (OPENING_LOAN, LOAN_GIVEN)

SOURCE_MANUAL = "manual"
CARRY_PREFIX = "carry:"
IMPORT_PREFIX = "import:"

DRAFT = "Draft"
ISSUED = "Issued"
CANCELLED = "Cancelled"

# The four statutory figures HR may type on a draft. Printed in the client's
# order, deducted (their slip did not), never computed.
STATUTORY = (("mlwf", "MLWF"), ("pf", "PF"), ("esic", "ESIC"), ("pt", "PT"))

MAX_ENTRY = 10_000_000.0       # a typo, not an advance


def entries() -> dict:
    return STORE.setdefault("pay_entries", {})


def slips() -> dict:
    return STORE.setdefault("payslips", {})


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _esc(v) -> str:
    return P.esc(str(v if v is not None else ""))


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _user_name() -> str:
    """Who did it, for the record's trail — "" outside a request (a tool)."""
    if not has_request_context():
        return ""
    u = auth.current_user() or {}
    return str(u.get("display_name") or u.get("username") or "")


# =============================================================================
# MONTHS
# =============================================================================

def valid_month(raw) -> str:
    """`YYYY-MM`, or "" for anything that is not one."""
    text = str(raw or "").strip()[:7]
    try:
        datetime.date.fromisoformat(text + "-01")
    except ValueError:
        return ""
    return text


def default_month(today: datetime.date = None) -> str:
    """The previous calendar month — the month a payslip is written FOR."""
    today = today or datetime.date.today()
    last = today.replace(day=1) - datetime.timedelta(days=1)
    return last.strftime("%Y-%m")


def month_bounds(month: str) -> tuple:
    """(first day, last day) as ISO strings."""
    y, m = int(month[:4]), int(month[5:7])
    return (f"{month}-01", f"{month}-{calendar.monthrange(y, m)[1]:02d}")


def next_month_first(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01"


def month_label(month: str) -> str:
    """'2026-10' → 'October 2026'."""
    try:
        return datetime.date.fromisoformat(month + "-01").strftime("%B %Y")
    except ValueError:
        return month


# =============================================================================
# THE LEDGER — derived figures only
# =============================================================================

def entries_of(employee_id) -> list:
    eid = str(employee_id or "")
    if not eid:
        return []
    return sorted((e for e in entries().values()
                   if str(e.get("employee_id") or "") == eid),
                  key=lambda e: (str(e.get("date") or ""),
                                 str(e.get("created_at") or "")))


def month_entries(employee_id, month) -> list:
    lo, hi = month_bounds(month)
    return [e for e in entries_of(employee_id)
            if lo <= str(e.get("date") or "") <= hi]


def _sum(rows, kind) -> float:
    return round(sum(_num(e.get("amount")) for e in rows
                     if e.get("type") == kind), 2)


def loan_figures(employee_id, month) -> dict:
    """
    `{"opening", "deduction", "balance"}` for one month, all DERIVED.

    *opening* — what was owed before this month's deduction: every opening
    balance and loan given up to the month's last day, less every deduction
    BEFORE the month. *deduction* — this month's. *balance* — the difference,
    signed: a deduction larger than the loan goes negative and is shown.
    """
    lo, hi = month_bounds(month)
    up, down_before, down_now = 0.0, 0.0, 0.0
    for e in entries_of(employee_id):
        day = str(e.get("date") or "")
        amt = _num(e.get("amount"))
        if e.get("type") in LOAN_UP and day <= hi:
            up += amt
        elif e.get("type") == LOAN_DEDUCTION:
            if day < lo:
                down_before += amt
            elif day <= hi:
                down_now += amt
    opening = round(up - down_before, 2)
    return {"opening": opening, "deduction": round(down_now, 2),
            "balance": round(opening - down_now, 2)}


def loan_balance(employee_id) -> float:
    """What is owed today, across every entry — derived."""
    total = 0.0
    for e in entries_of(employee_id):
        if e.get("type") in LOAN_UP:
            total += _num(e.get("amount"))
        elif e.get("type") == LOAN_DEDUCTION:
            total -= _num(e.get("amount"))
    return round(total, 2)


# =============================================================================
# THE SLIP'S ARITHMETIC — sums and the rupee, nothing else
# =============================================================================

def rupee_half_up(value) -> int:
    """The nearest rupee, HALF UP — 12118.50 → 12119, never banker's rounding."""
    return int(Decimal(str(round(float(value), 2))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))


def compute(figures: dict, month_rows: list, loan: dict,
            other_allowance=0.0, statutory: dict = None) -> dict:
    """
    Every figure on the slip, from the month's wage figures (attendance), the
    month's ledger rows and the derived loan. Pure: reads nothing else.
    """
    statutory = statutory or {}
    basic = round(_num(figures.get("basic")), 2)
    ot = round(_num(figures.get("ot")), 2)
    travel = _sum(month_rows, TRAVEL)
    advance = _sum(month_rows, ADVANCE)
    other = round(_num(other_allowance), 2)
    stat = {k: round(_num(statutory.get(k)), 2) for k, _ in STATUTORY}
    gross = round(basic + other + ot + travel, 2)
    total_ded = round(advance + loan["deduction"] + sum(stat.values()), 2)
    net_raw = round(gross - total_ded, 2)
    if net_raw < 0:
        payable, round_off, carry = 0, 0.0, round(-net_raw, 2)
    else:
        payable = rupee_half_up(net_raw)
        round_off, carry = round(payable - net_raw, 2), 0.0
    out = {"basic": basic, "ot": ot, "travel": travel, "other_allowance": other,
           "gross": gross, "advance": advance,
           "loan_opening": loan["opening"], "loan_deduction": loan["deduction"],
           "loan_balance": loan["balance"], "total_deduction": total_ded,
           "net_raw": net_raw, "round_off": round_off, "payable": payable,
           "carry": carry}
    out.update(stat)
    return out


def _carried_from(slip_id) -> list:
    return [e for e in entries().values()
            if str(e.get("source") or "") == CARRY_PREFIX + str(slip_id)]


def snapshot(employee_id, month, other_allowance=0.0, statutory=None,
             own_slip_id: str = "") -> dict:
    """
    Everything a slip stores, drawn live. ⚠ The slip's OWN carried entry (it
    sits in the next month) is never in this month's rows, so a refresh cannot
    feed a slip its own shortfall.
    """
    person = EMP.employees().get(employee_id) or {}
    fig = AT.month_figures(employee_id, month)
    rows = [e for e in month_entries(employee_id, month)
            if not own_slip_id
            or str(e.get("source") or "") != CARRY_PREFIX + own_slip_id]
    loan = loan_figures(employee_id, month)
    money = compute(fig, rows, loan, other_allowance, statutory)
    rates = fig["rates"]
    snap = {
        "employee_name": str(person.get("name") or ""),
        "employee_code": str(person.get("code") or ""),
        "designation": str(person.get("designation") or ""),
        "rates": rates,
        "present_days": fig["present_days"], "half_days": fig["half_days"],
        "paid_leave_days": fig["paid_leave_days"],
        "absent_days": fig["absent_days"], "paid_days": fig["paid_days"],
        "ot_hours": fig["ot_hours"], "ot_rate": fig["ot_rate"],
        "multiplier": fig["multiplier"], "markings": fig["markings"],
        "refused": fig["refused"],
        "entry_ids": [e["id"] for e in rows],
    }
    snap.update(money)
    return snap


# =============================================================================
# SLIPS
# =============================================================================

def live_slip(employee_id, month) -> dict:
    """The one Draft or Issued slip of a person and month, or {}."""
    for s in slips().values():
        if (s.get("employee_id") == employee_id and s.get("month") == month
                and s.get("status") in (DRAFT, ISSUED)):
            return s
    return {}


def create_draft(employee_id, month) -> tuple:
    """`(slip, error)`. One live slip per person per month — refused otherwise."""
    if not EMP.employees().get(employee_id):
        return {}, "That employee is not on the register."
    if live_slip(employee_id, month):
        return {}, "A slip already exists for that month — cancel it first."
    sid = str(uuid.uuid4())
    rec = {"id": sid, "employee_id": employee_id, "month": month,
           "status": DRAFT, "other_allowance": 0.0,
           "statutory": {k: 0.0 for k, _ in STATUTORY},
           "snapshot": snapshot(employee_id, month, own_slip_id=sid),
           "carry_entry_id": "", "created_at": _now(),
           "created_by": _user_name(), "updated_at": _now()}
    slips()[sid] = rec
    return rec, ""


def refresh(slip: dict) -> str:
    if slip.get("status") != DRAFT:
        return "Only a draft is refreshed — an issued slip never moves."
    slip["snapshot"] = snapshot(slip["employee_id"], slip["month"],
                                slip.get("other_allowance"),
                                slip.get("statutory"), own_slip_id=slip["id"])
    slip["updated_at"] = _now()
    return ""


def issue(slip: dict) -> str:
    """Freeze a draft; carry a shortfall into the next month as an advance."""
    if slip.get("status") != DRAFT:
        return "Only a draft can be issued."
    refresh(slip)
    carry = _num(slip["snapshot"].get("carry"))
    if carry > 0:
        eid = str(uuid.uuid4())
        entries()[eid] = {
            "id": eid, "employee_id": slip["employee_id"],
            "employee_name": slip["snapshot"]["employee_name"],
            "date": next_month_first(slip["month"]), "type": ADVANCE,
            "amount": carry,
            "note": (f"Carried from the {month_label(slip['month'])} payslip — "
                     f"the advance was more than the wages."),
            "source": CARRY_PREFIX + slip["id"],
            "created_at": _now(), "created_by": _user_name(),
            "updated_at": _now()}
        slip["carry_entry_id"] = eid
    slip["status"] = ISSUED
    slip["issued_at"] = _now()
    slip["issued_by"] = _user_name()
    slip["updated_at"] = _now()
    return ""


def cancel(slip: dict, reason: str) -> str:
    reason = str(reason or "").strip()[:500]
    if slip.get("status") == CANCELLED:
        return "That slip is already cancelled."
    if not reason:
        return "Say why — a cancelled slip keeps its reason."
    if slip.get("status") == ISSUED and slip.get("carry_entry_id"):
        nxt = next_month_first(slip["month"])[:7]
        blocker = live_slip(slip["employee_id"], nxt)
        if blocker.get("status") == ISSUED:
            return (f"The {month_label(nxt)} slip is issued and was drawn with "
                    f"this slip's carried advance. Cancel that one first.")
        entries().pop(slip["carry_entry_id"], None)
    slip["status"] = CANCELLED
    slip["cancel_reason"] = reason
    slip["cancelled_at"] = _now()
    slip["cancelled_by"] = _user_name()
    slip["updated_at"] = _now()
    return ""


def divergence(slip: dict) -> dict:
    """For an issued slip: the live figures, when they no longer match."""
    if slip.get("status") != ISSUED:
        return {}
    live = snapshot(slip["employee_id"], slip["month"],
                    slip.get("other_allowance"), slip.get("statutory"),
                    own_slip_id=slip["id"])
    snap = slip.get("snapshot") or {}
    keys = ("basic", "ot", "travel", "advance", "loan_deduction", "payable")
    if all(round(_num(live.get(k)), 2) == round(_num(snap.get(k)), 2)
           for k in keys):
        return {}
    return live


def month_roster(month) -> list:
    """Every employee with a marking, a ledger row or a slip in the month."""
    ids = set(AT.employees_marked_in(month))
    lo, hi = month_bounds(month)
    ids |= {str(e.get("employee_id") or "") for e in entries().values()
            if lo <= str(e.get("date") or "") <= hi}
    ids |= {s.get("employee_id") for s in slips().values()
            if s.get("month") == month}
    people = EMP.employees()
    ids = {i for i in ids if i}
    return sorted(ids, key=lambda i: str((people.get(i) or {}).get("name")
                                         or i).lower())


# =============================================================================
# THE PAGES
# =============================================================================

PAYROLL_CSS = """
<style>
  .pay-note { background:#fff8e1; border:1px solid #f0c36d; border-radius:8px;
              padding:10px 14px; margin:0 0 14px; font-size:.86rem; }
  .pay-warn { background:#fff3e0; border:1px solid #f0a35d; border-radius:8px;
              padding:10px 14px; margin:0 0 14px; font-size:.86rem; }
  .pay-chip { display:inline-block; padding:2px 8px; border-radius:10px;
              font-size:.74rem; font-weight:600; background:#eef; }
  .pay-chip.draft { background:#fff3cd; } .pay-chip.issued { background:#d4edda; }
  .pay-chip.cancelled { background:#f8d7da; }
  .pay-card { background:#fff; border:1px solid #e5e5e5; border-radius:10px;
              padding:10px 12px; margin:0 0 14px; overflow-x:auto; }
  .pay-sub { display:block; font-size:.76rem; color:var(--muted, #777); }
  .pay-acts { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 14px; }
  .pay-acts form { display:inline; }
  .pay-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
              gap:10px; }
  table.pay-tbl { width:100%; border-collapse:collapse; font-size:.86rem; }
  table.pay-tbl th, table.pay-tbl td { padding:6px 8px; border-bottom:1px solid #e5e5e5;
              text-align:left; }
  table.pay-tbl td.num, table.pay-tbl th.num { text-align:right; }
</style>"""

SLIP_CSS = """
<style>
  .slip-title { text-align:center; font-weight:700; font-size:1.05rem;
                margin:6px 0 10px; }
  table.slip-head, table.slip-body { width:100%; border-collapse:collapse;
                font-size:.86rem; }
  table.slip-head td { padding:4px 6px; border:1px solid #999; }
  table.slip-head td.k, table.slip-body td.k { width:22%; font-weight:600; }
  table.slip-body { margin-top:8px; }
  table.slip-body th { background:#f2f2f2; border:1px solid #999; padding:5px 6px;
                text-align:left; }
  table.slip-body td { border:1px solid #999; padding:4px 6px; }
  table.slip-body td.num { text-align:right; white-space:nowrap; }
  table.slip-body tr.tot td { font-weight:700; background:#fafafa; }
  .slip-net { margin-top:8px; border:1px solid #999; padding:6px 8px;
              display:flex; justify-content:space-between; font-weight:700; }
  .slip-sign { display:flex; justify-content:space-between; margin-top:56px;
               font-size:.86rem; }
  .slip-sign div { border-top:1px solid #333; padding-top:4px; width:38%;
                   text-align:center; }
  .slip-mark { position:relative; text-align:center; font-weight:800;
               letter-spacing:.3em; color:#c62828; border:2px solid #c62828;
               padding:4px; margin:6px auto; width:50%; }
  .slip-page { page-break-after:always; }
  .slip-page:last-child { page-break-after:auto; }
</style>"""


def _shell(title: str, body: str, extra_styles: str = "") -> str:
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{PAYROLL_CSS}{extra_styles}
</head>
<body>
{_nav()}
<main>
{body}
<footer><p>{B.COMPANY_NAME} &middot; {B.APP_SUBTITLE} &middot; payroll</p></footer>
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
    return _alert(msg, "success" if request.args.get("type") == "success"
                  else "error")


def _money(v) -> str:
    return _inr(_num(v))


def _days(v) -> str:
    return P.esc(f"{_num(v):g}")


def _chip(status: str) -> str:
    cls = {DRAFT: "draft", ISSUED: "issued", CANCELLED: "cancelled"}.get(status, "")
    return f'<span class="pay-chip {cls}">{_esc(status)}</span>'


def _post_btn(action: str, label: str, cls: str = "btn") -> str:
    return (f'<form method="POST" action="{action}">'
            f'<button class="{cls}">{label}</button></form>')


@payroll_bp.route("/")
def payroll_register():
    """One month: every person with a marking, a ledger row or a slip."""
    month = valid_month(request.args.get("month")) or default_month()
    rows = []
    for eid in month_roster(month):
        person = EMP.employees().get(eid) or {}
        slip = live_slip(eid, month)
        snap = slip.get("snapshot") if slip else snapshot(eid, month)
        link = (f'<a href="{url_for("payroll.view_slip", id=slip["id"])}">'
                f'{_chip(slip["status"])}</a>' if slip
                else '<span class="pay-sub">no slip</span>')
        rows.append(f"""
      <tr>
        <td>{_esc(person.get('name') or '(not on the register)')}{
          f'<span class="pay-sub">{_esc(person.get("code"))}</span>'
          if person.get('code') else ''}</td>
        <td class="num">{_days(snap.get('paid_days'))}</td>
        <td class="num">{_days(snap.get('ot_hours'))}</td>
        <td class="num">{_money(snap.get('gross'))}</td>
        <td class="num">{_money(snap.get('total_deduction'))}</td>
        <td class="num"><b>{_money(snap.get('payable'))}</b>{
          f'<span class="pay-sub">carry {_money(snap.get("carry"))}</span>'
          if _num(snap.get('carry')) else ''}</td>
        <td>{link}</td>
      </tr>""")
    table = (f"""
  <div class="pay-card">
    <table class="pay-tbl">
      <tr><th>Employee</th><th class="num">Paid days</th><th class="num">OT hrs</th>
          <th class="num">Gross</th><th class="num">Deductions</th>
          <th class="num">Net payable</th><th>Slip</th></tr>
      {''.join(rows)}
    </table>
  </div>""" if rows else
        '<div class="pay-card"><p>Nobody was marked, and no advance or loan '
        'was recorded, in this month.</p></div>')

    acts = []
    if auth.has_perm("payroll.edit"):
        acts.append(_post_btn(url_for("payroll.generate", month=month),
                              "Create the month&rsquo;s missing drafts"))
    acts.append(f'<a class="btn btn-ghost" href="'
                f'{url_for("payroll.print_month", month=month)}">'
                f'Print every issued slip</a>')
    acts.append(f'<a class="btn btn-ghost" href="'
                f'{url_for("payroll.list_entries", month=month)}">Pay ledger</a>')
    if auth.has_perm("payroll.import"):
        acts.append(f'<a class="btn btn-ghost" href="'
                    f'{url_for("payimport.upload")}">Import attendance from '
                    f'Excel</a>')
    acts.append(f'<a class="btn btn-ghost" href="'
                f'{url_for("attendance.list_attendance")}">&#8592; Muster</a>')

    body = f"""
  {_flash()}
  <div class="page-top">
    <h1>Payslips &mdash; {_esc(month_label(month))}</h1>
  </div>
  <form method="GET" class="pay-acts">
    <input type="month" name="month" value="{_esc(month)}"/>
    <button class="btn btn-ghost">Show</button>
  </form>
  <div class="pay-acts">{''.join(acts)}</div>
  <div class="pay-note">Figures without a slip are drawn live from the muster
    and the pay ledger. A slip <b>snapshots</b> them; an issued slip never
    moves. Net pay is rounded to the rupee, half up.</div>
  {table}"""
    return _shell(f"Payslips {month_label(month)}", body)


@payroll_bp.route("/generate", methods=["POST"])
def generate():
    month = valid_month(request.args.get("month") or request.form.get("month"))
    if not month:
        return redirect(url_for("payroll.payroll_register",
                                msg="Choose a month.", type="error"))
    made = 0
    for eid in month_roster(month):
        if EMP.employees().get(eid) and not live_slip(eid, month):
            _, err = create_draft(eid, month)
            made += 0 if err else 1
    return redirect(url_for("payroll.payroll_register", month=month,
                            msg=f"{made} draft slip(s) created.", type="success"))


def _slip_or_back(id):
    slip = slips().get(id)
    if not slip:
        return None, redirect(url_for("payroll.payroll_register",
                                      msg="That slip no longer exists.",
                                      type="error"))
    return slip, None


def slip_sheet(slip: dict) -> str:
    """The printed payslip, from the slip's OWN snapshot and nothing else."""
    s = slip.get("snapshot") or {}
    rates = s.get("rates") or []
    rate_cell = (_money(rates[0]) if len(rates) == 1
                 else ("varies" if rates else "&mdash;"))
    ot_rate = ("&mdash;" if s.get("ot_rate") is None else _money(s.get("ot_rate")))
    days_note = []
    if s.get("half_days"):
        days_note.append(f"{s['half_days']} half")
    if s.get("paid_leave_days"):
        days_note.append(f"{s['paid_leave_days']} paid leave")
    days_cell = _days(s.get("paid_days")) + (
        f" <small>({_esc(', '.join(days_note))})</small>" if days_note else "")

    earn = [("Basic", _money(s.get("basic"))),
            ("Other Allowance", _money(s.get("other_allowance"))),
            ("Paid Days", days_cell),
            ("Rate / Day", rate_cell),
            ("OT Hours", _days(s.get("ot_hours"))),
            ("OT Rate / Hour", ot_rate),
            ("OT Payment", _money(s.get("ot"))),
            ("Travelling Expenses", _money(s.get("travel")))]
    ded = [("Loan", _money(s.get("loan_opening"))),
           ("Loan Deduction", _money(s.get("loan_deduction"))),
           ("Loan Balance", _money(s.get("loan_balance"))),
           ("Salary Advance", _money(s.get("advance")))]
    ded += [(label, _money(s.get(key))) for key, label in STATUTORY]
    n = max(len(earn), len(ded))
    earn += [("", "")] * (n - len(earn))
    ded += [("", "")] * (n - len(ded))
    body_rows = "".join(
        f'<tr><td class="k">{a}</td><td class="num">{b}</td>'
        f'<td class="k">{c}</td><td class="num">{d}</td></tr>'
        for (a, b), (c, d) in zip(earn, ded))

    mark = ""
    if slip.get("status") == CANCELLED:
        mark = '<div class="slip-mark">CANCELLED</div>'
    elif slip.get("status") == DRAFT:
        mark = '<div class="slip-mark">DRAFT</div>'
    carry = ""
    if _num(s.get("carry")):
        carry = (f'<div class="pay-warn">The advance was more than the wages: '
                 f'{_money(s.get("carry"))} is carried to '
                 f'{_esc(month_label(next_month_first(slip["month"])[:7]))} as '
                 f'an advance.</div>')
    return f"""{DS.sheet_open()}
    <div class="slip-title">Payslip for the month of {_esc(month_label(slip.get('month', '')))}</div>
    {mark}
    <table class="slip-head">
      <tr><td class="k">Employee Name</td><td>{_esc(s.get('employee_name'))}</td>
          <td class="k">Employee Code</td><td>{_esc(s.get('employee_code'))}</td></tr>
      <tr><td class="k">Designation</td><td>{_esc(s.get('designation'))}</td>
          <td class="k">Present Days</td><td>{days_cell}</td></tr>
    </table>
    <table class="slip-body">
      <tr><th colspan="2">Earnings</th><th colspan="2">Deductions</th></tr>
      {body_rows}
      <tr class="tot"><td class="k">Gross Salary</td><td class="num">{_money(s.get('gross'))}</td>
          <td class="k">Total Deduction</td><td class="num">{_money(s.get('total_deduction'))}</td></tr>
    </table>
    <div class="slip-net"><span>Actual Salary{
      f' <small>(round off {_money(s.get("round_off"))})</small>'
      if _num(s.get('round_off')) else ''}</span><span>{_money(s.get('payable'))}</span></div>
{DS.amount_words("In words", float(s.get('payable') or 0))}
    {carry}
    <div class="slip-sign"><div>Prepared By</div><div>Received By</div></div>
{DS.sheet_close()}"""


def _print_page(title: str, sheets: str, back: str) -> str:
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>
  {B.HEAD_ICON}
  {DS.SHEET_STYLES}{SLIP_CSS}{PAYROLL_CSS}{DS.PRINT_EDGE_STYLES}
</head>
<body>
<div class="screen-acts no-print">
  <a href="{back}" class="btn btn-ghost">&#8592;&nbsp;Back</a>
  <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
</div>
<div class="doc-outer">
{sheets}
</div>
</body></html>"""


@payroll_bp.route("/slip/<id>")
def view_slip(id):
    slip, back = _slip_or_back(id)
    if back:
        return back
    status = slip.get("status")
    acts = [f'<a class="btn" href="{url_for("payroll.print_slip", id=id)}">'
            f'&#128438; Print</a>']
    if status == DRAFT and auth.has_perm("payroll.edit"):
        acts.append(_post_btn(url_for("payroll.refresh_slip", id=id),
                              "Refresh from the muster", "btn btn-ghost"))
    if status == DRAFT and auth.has_perm("payroll.issue"):
        acts.append(_post_btn(url_for("payroll.issue_slip", id=id), "Issue"))
    if status in (DRAFT, ISSUED) and auth.has_perm("payroll.issue"):
        acts.append(f'<a class="btn btn-ghost" href="'
                    f'{url_for("payroll.cancel_slip", id=id)}">Cancel slip</a>')
    acts.append(f'<a class="btn btn-ghost" href="'
                f'{url_for("payroll.payroll_register", month=slip["month"])}">'
                f'&#8592; The month</a>')

    band = ""
    live = divergence(slip)
    if live:
        snap = slip["snapshot"]
        band = (f'<div class="pay-warn"><b>Changed since this slip was '
                f'issued.</b> Issued net {_money(snap.get("payable"))}; drawn '
                f'today it would be {_money(live.get("payable"))}. The slip is '
                f'deliberately not restated &mdash; cancel and redraw it if the '
                f'change is right.</div>')
    if status == CANCELLED:
        band += (f'<div class="pay-warn"><b>Cancelled</b> '
                 f'{_esc(slip.get("cancelled_at"))}: '
                 f'{_esc(slip.get("cancel_reason"))}</div>')
    s = slip.get("snapshot") or {}
    if s.get("refused"):
        band += (f'<div class="pay-warn">{_esc(s["refused"])} marking(s) carry '
                 f'an unconfirmed monthly rate and are not paid here.</div>')
    if _num(s.get("loan_balance")) < 0:
        band += ('<div class="pay-warn">The loan deduction is more than the '
                 'loan owed &mdash; check the pay ledger.</div>')

    extras = ""
    if status == DRAFT and auth.has_perm("payroll.edit"):
        stat = slip.get("statutory") or {}
        fields = "".join(
            f'<div class="form-group"><label>{label}</label><input type="number" '
            f'step="0.01" min="0" name="{key}" value="{_esc(stat.get(key, 0))}"/>'
            f'</div>' for key, label in STATUTORY)
        extras = f"""
  <form method="POST" action="{url_for('payroll.save_extras', id=id)}"
        class="form-section">
    <div class="section-title">Typed on the draft</div>
    <div class="pay-grid">
      <div class="form-group"><label>Other allowance</label>
        <input type="number" step="0.01" min="0" name="other_allowance"
               value="{_esc(slip.get('other_allowance', 0))}"/></div>
      {fields}
    </div>
    <small class="field-hint">PF, ESIC, PT and MLWF are typed by HR and are
      <b>not computed</b> by this software. A figure typed here is deducted.</small>
    <div><button class="btn">Save</button></div>
  </form>"""

    body = f"""
  {_flash()}
  <div class="page-top">
    <h1>{_esc(s.get('employee_name'))} &mdash; {_esc(month_label(slip['month']))}
      {_chip(status)}</h1>
  </div>
  <div class="pay-acts">{''.join(acts)}</div>
  {band}
  {extras}
  <div class="doc-outer">{slip_sheet(slip)}</div>"""
    return _shell("Payslip", body, DS.SHEET_STYLES + SLIP_CSS)


@payroll_bp.route("/slip/<id>/extras", methods=["POST"])
def save_extras(id):
    slip, back = _slip_or_back(id)
    if back:
        return back
    if slip.get("status") != DRAFT:
        return redirect(url_for("payroll.view_slip", id=id,
                                msg="Only a draft is edited.", type="error"))
    vals = {}
    for key in ["other_allowance"] + [k for k, _ in STATUTORY]:
        raw = (request.form.get(key) or "0").strip() or "0"
        try:
            v = round(float(raw), 2)
        except ValueError:
            return redirect(url_for("payroll.view_slip", id=id,
                                    msg=f"{key}: enter a number.", type="error"))
        if v < 0 or v > MAX_ENTRY:
            return redirect(url_for("payroll.view_slip", id=id,
                                    msg=f"{key}: out of range.", type="error"))
        vals[key] = v
    slip["other_allowance"] = vals.pop("other_allowance")
    slip["statutory"] = vals
    refresh(slip)
    return redirect(url_for("payroll.view_slip", id=id, msg="Saved.",
                            type="success"))


@payroll_bp.route("/slip/<id>/refresh", methods=["POST"])
def refresh_slip(id):
    slip, back = _slip_or_back(id)
    if back:
        return back
    err = refresh(slip)
    return redirect(url_for("payroll.view_slip", id=id,
                            msg=err or "Redrawn from the muster and the ledger.",
                            type="error" if err else "success"))


@payroll_bp.route("/slip/<id>/issue", methods=["POST"])
def issue_slip(id):
    slip, back = _slip_or_back(id)
    if back:
        return back
    err = issue(slip)
    return redirect(url_for("payroll.view_slip", id=id,
                            msg=err or "Issued.",
                            type="error" if err else "success"))


@payroll_bp.route("/slip/<id>/cancel", methods=["GET", "POST"])
def cancel_slip(id):
    slip, back = _slip_or_back(id)
    if back:
        return back
    error = ""
    if request.method == "POST":
        error = cancel(slip, request.form.get("reason"))
        if not error:
            return redirect(url_for("payroll.view_slip", id=id,
                                    msg="Cancelled.", type="success"))
    carry = (" Its carried advance is removed from the ledger."
             if slip.get("carry_entry_id") else "")
    body = f"""
  {_alert(error)}
  <div class="page-top"><h1>Cancel this payslip</h1></div>
  <div class="pay-note">{_esc((slip.get('snapshot') or {}).get('employee_name'))},
    {_esc(month_label(slip['month']))}. A cancelled slip stays on record with
    its reason and frees the month for a new one.{carry}</div>
  <form method="POST" class="form-section">
    <div class="form-group"><label>Reason *</label>
      <input name="reason" required maxlength="500"/></div>
    <button class="btn">Cancel the slip</button>
    <a class="btn btn-ghost" href="{url_for('payroll.view_slip', id=id)}">Back</a>
  </form>"""
    return _shell("Cancel payslip", body)


@payroll_bp.route("/slip/print/<id>")
def print_slip(id):
    slip, back = _slip_or_back(id)
    if back:
        return back
    s = slip.get("snapshot") or {}
    return _print_page(f"Payslip {s.get('employee_name', '')} {slip['month']}",
                       f'<div class="slip-page">{slip_sheet(slip)}</div>',
                       url_for("payroll.view_slip", id=id))


@payroll_bp.route("/print-month")
def print_month():
    month = valid_month(request.args.get("month")) or default_month()
    issued = sorted((s for s in slips().values()
                     if s.get("month") == month and s.get("status") == ISSUED),
                    key=lambda s: str((s.get("snapshot") or {})
                                      .get("employee_name") or "").lower())
    sheets = "".join(f'<div class="slip-page">{slip_sheet(s)}</div>'
                     for s in issued) or (
        f'<p>No slip is issued for {_esc(month_label(month))} yet.</p>')
    return _print_page(f"Payslips {month_label(month)}", sheets,
                       url_for("payroll.payroll_register", month=month))


# =============================================================================
# THE LEDGER PAGES
# =============================================================================

def _validate_entry(form) -> tuple:
    data = {"employee_id": (form.get("employee_id") or "").strip(),
            "date": (form.get("date") or "").strip()[:10],
            "type": (form.get("type") or "").strip(),
            "amount_raw": (form.get("amount") or "").strip(),
            "note": (form.get("note") or "").strip()[:500]}
    person = EMP.employees().get(data["employee_id"])
    if not person:
        return data, "Choose an employee."
    try:
        datetime.date.fromisoformat(data["date"])
    except ValueError:
        return data, "A date is required (YYYY-MM-DD)."
    if data["type"] not in ENTRY_TYPES:
        return data, "Choose what the entry is."
    try:
        amount = round(float(data["amount_raw"]), 2)
    except ValueError:
        return data, "Amount: enter a number."
    if amount <= 0 or amount > MAX_ENTRY:
        return data, "Amount: more than nil, and not a typo."
    data["amount"] = amount
    data["person"] = person
    return data, ""


def _is_carry(entry) -> bool:
    return str(entry.get("source") or "").startswith(CARRY_PREFIX)


def _employee_options(selected: str) -> str:
    out = ['<option value="">— choose —</option>']
    for e in sorted(EMP.employees().values(),
                    key=lambda e: str(e.get("name") or "").lower()):
        sel = " selected" if e["id"] == selected else ""
        label = e.get("name") or "(unnamed)"
        if e.get("code"):
            label = f"{label} ({e['code']})"
        out.append(f'<option value="{_esc(e["id"])}"{sel}>{_esc(label)}</option>')
    return "".join(out)


def _type_options(selected: str) -> str:
    return "".join(f'<option value="{k}"{" selected" if k == selected else ""}>'
                   f'{_esc(ENTRY_LABELS[k])}</option>' for k in ENTRY_TYPES)


def _entry_form(data: dict, action: str, label: str) -> str:
    return f"""
  <form method="POST" action="{action}" class="form-section">
    <div class="pay-grid">
      <div class="form-group"><label>Employee *</label>
        <select name="employee_id" required>{_employee_options(data.get('employee_id', ''))}</select></div>
      <div class="form-group"><label>Date *</label>
        <input type="date" name="date" required value="{_esc(data.get('date'))}"/></div>
      <div class="form-group"><label>What *</label>
        <select name="type">{_type_options(data.get('type', ADVANCE))}</select></div>
      <div class="form-group"><label>Amount *</label>
        <input type="number" step="0.01" min="0.01" name="amount" required
               value="{_esc(data.get('amount_raw', data.get('amount', '')))}"/></div>
      <div class="form-group"><label>Note</label>
        <input name="note" maxlength="500" value="{_esc(data.get('note'))}"/></div>
    </div>
    <button class="btn">{label}</button>
  </form>"""


@payroll_bp.route("/entries")
def list_entries():
    month = valid_month(request.args.get("month"))
    eid = (request.args.get("employee") or "").strip()
    rows = sorted(entries().values(), key=lambda e: (
        str(e.get("date") or ""), str(e.get("created_at") or "")), reverse=True)
    if month:
        lo, hi = month_bounds(month)
        rows = [e for e in rows if lo <= str(e.get("date") or "") <= hi]
    if eid:
        rows = [e for e in rows if e.get("employee_id") == eid]
    can_edit = auth.has_perm("payroll.edit")
    can_del = auth.has_perm("payroll.delete")
    people = EMP.employees()
    trs = []
    for e in rows:
        acts = ""
        if _is_carry(e):
            acts = '<span class="pay-sub">carried by a slip</span>'
        else:
            if can_edit:
                acts += (f'<a href="{url_for("payroll.edit_entry", id=e["id"])}">'
                         f'Edit</a> ')
            if can_del:
                acts += (f'<a href="{url_for("payroll.delete_entry", id=e["id"])}">'
                         f'Delete</a>')
        person = people.get(e.get("employee_id")) or {}
        trs.append(f"""
      <tr><td>{_esc(e.get('date'))}</td>
          <td>{_esc(person.get('name') or e.get('employee_name'))}</td>
          <td>{_esc(ENTRY_LABELS.get(e.get('type'), e.get('type')))}</td>
          <td class="num">{_money(e.get('amount'))}</td>
          <td>{_esc(e.get('note'))}{
            f'<span class="pay-sub">imported</span>'
            if str(e.get('source') or '').startswith(IMPORT_PREFIX) else ''}</td>
          <td>{acts}</td></tr>""")
    balance = ""
    if eid:
        balance = (f'<div class="pay-note">Loan owed today by '
                   f'{_esc((people.get(eid) or {}).get("name"))}: '
                   f'<b>{_money(loan_balance(eid))}</b> &mdash; derived from the '
                   f'entries below, never stored.</div>')
    form = ""
    if can_edit:
        form = ('<h2>Add an entry</h2>' + _entry_form(
            {"employee_id": eid, "date": datetime.date.today().isoformat()},
            url_for("payroll.add_entry"), "Add"))
    body = f"""
  {_flash()}
  <div class="page-top"><h1>Pay ledger</h1>
    <a class="btn btn-ghost" href="{url_for('payroll.payroll_register', month=month or default_month())}">&#8592; Payslips</a></div>
  <form method="GET" class="pay-acts">
    <select name="employee"><option value="">Everybody</option>{
      ''.join(f'<option value="{_esc(p["id"])}"{" selected" if p["id"] == eid else ""}>'
              f'{_esc(p.get("name"))}</option>'
              for p in sorted(people.values(), key=lambda p: str(p.get("name") or "").lower()))}</select>
    <input type="month" name="month" value="{_esc(month)}"/>
    <button class="btn btn-ghost">Filter</button>
  </form>
  {balance}
  <div class="pay-card"><table class="pay-tbl">
    <tr><th>Date</th><th>Employee</th><th>What</th><th class="num">Amount</th>
        <th>Note</th><th></th></tr>
    {''.join(trs) or '<tr><td colspan="6">No entries.</td></tr>'}
  </table></div>
  {form}"""
    return _shell("Pay ledger", body)


@payroll_bp.route("/entries/add", methods=["POST"])
def add_entry():
    data, error = _validate_entry(request.form)
    if error:
        return redirect(url_for("payroll.list_entries",
                                employee=data.get("employee_id"),
                                msg=error, type="error"))
    eid = str(uuid.uuid4())
    entries()[eid] = {
        "id": eid, "employee_id": data["employee_id"],
        "employee_name": str(data["person"].get("name") or ""),
        "date": data["date"], "type": data["type"], "amount": data["amount"],
        "note": data["note"], "source": SOURCE_MANUAL,
        "created_at": _now(), "created_by": _user_name(), "updated_at": _now()}
    return redirect(url_for("payroll.list_entries", employee=data["employee_id"],
                            msg="Entry recorded.", type="success"))


@payroll_bp.route("/entries/edit/<id>", methods=["GET", "POST"])
def edit_entry(id):
    entry = entries().get(id)
    if not entry or _is_carry(entry):
        return redirect(url_for("payroll.list_entries",
                                msg="That entry cannot be edited here.",
                                type="error"))
    data, error = dict(entry), ""
    if request.method == "POST":
        data, error = _validate_entry(request.form)
        if not error:
            entry.update({"employee_id": data["employee_id"],
                          "employee_name": str(data["person"].get("name") or ""),
                          "date": data["date"], "type": data["type"],
                          "amount": data["amount"], "note": data["note"],
                          "updated_at": _now()})
            return redirect(url_for("payroll.list_entries",
                                    employee=entry["employee_id"],
                                    msg="Entry corrected.", type="success"))
    body = f"""
  {_alert(error)}
  <div class="page-top"><h1>Correct an entry</h1></div>
  <div class="pay-note">An issued payslip that used this entry does not move;
    it shows the difference instead.</div>
  {_entry_form(data, url_for('payroll.edit_entry', id=id), 'Save')}"""
    return _shell("Correct an entry", body)


@payroll_bp.route("/entries/delete/<id>", methods=["GET", "POST"])
def delete_entry(id):
    """GET confirms, POST destroys — `9d060ee`'s shape. Owner-only (auth)."""
    entry = entries().get(id)
    if not entry or _is_carry(entry):
        return redirect(url_for("payroll.list_entries",
                                msg="That entry cannot be deleted here.",
                                type="error"))
    if request.method == "POST":
        entries().pop(id, None)
        return redirect(url_for("payroll.list_entries",
                                employee=entry.get("employee_id"),
                                msg="Entry deleted.", type="success"))
    body = f"""
  <div class="page-top"><h1>Delete this entry?</h1></div>
  <div class="pay-note">{_esc(entry.get('date'))} &middot;
    {_esc(entry.get('employee_name'))} &middot;
    {_esc(ENTRY_LABELS.get(entry.get('type'), entry.get('type')))} &middot;
    {_money(entry.get('amount'))}. An issued payslip that used it does not move.</div>
  <form method="POST"><button class="btn">Delete</button>
    <a class="btn btn-ghost" href="{url_for('payroll.list_entries')}">Back</a></form>"""
    return _shell("Delete entry", body)
