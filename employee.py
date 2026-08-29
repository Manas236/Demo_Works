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

⚠ **OUT OF SCOPE HERE, AND STILL TRUE OF THIS FILE:**

* **No attendance and no overtime in this module.** Presentee / absentee, OT
  and site-wise labour cost are **C5**, and C5 was authorised on 29 August 2026
  (third pass) — but it lives in its own module, [attendance.py](attendance.py),
  which imports this one. **Nothing was added here for it.** The register links
  out with `url_for`, which needs no import; importing back would be a cycle.
* **No salary calculation.** `monthly_salary` is a number recorded against a
  person. Nothing in *this* file multiplies, prorates or divides it —
  `attendance.py` reads the figure and does the arithmetic there, against an
  OT multiplier that is a **setting rather than a constant**.
* **No link to `charge.py` and none to a P&L.** `employee.py ↔ charge.py` stays
  forbidden in **both** directions at AST level, and that prohibition did *not*
  expire when C5 was authorised: joining the wages ledger to the people data is
  a profit-and-loss question and **C6 is BLOCKED** on CC-2's Open question 4.

A leaf, and one with no way in from the chrome
-----------------------------------------------
Imports `dashboard`, `branding`, `pipeline`, `store` and `quotation` — the same
five `charge.py` takes, and nothing else. Nothing imports it.

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

import branding as B
import pipeline as P
from store import STORE
from dashboard import BASE_STYLES, _nav, rupees
from quotation import QUOTATION_STYLES

employee_bp = Blueprint("employee", __name__, url_prefix="/employee")


# =============================================================================
# BUSINESS RULES
# =============================================================================

# A salary bigger than this is a typo, not a salary — the same class of guard as
# `purchase.MAX_CHARGE_AMOUNT`. Ten lakh a month is somebody's stray zero.
MAX_MONTHLY_SALARY = 1000000.0


def employees() -> dict:
    return STORE.setdefault("employees", {})


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


def _validate(form, except_id: str = "") -> tuple:
    """
    `(data, error)` for the create and edit forms.

    A rejected form re-renders with what was typed and writes nothing — the
    `address._validate()` contract this app holds to everywhere.

    Required: a name, and a monthly salary that is a non-negative number.
    Everything else is optional, because a register nobody can add to until
    they have every field is a register that stays empty. **Salary may be
    zero** — a proprietor or a family member drawing nothing is real, and
    refusing it would force somebody to invent a figure.
    """
    data = {
        "name":        (form.get("name") or "").strip()[:120],
        "code":        (form.get("code") or "").strip()[:40],
        "designation": (form.get("designation") or "").strip()[:120],
        "site":        (form.get("site") or "").strip()[:160],
        "date_joined": (form.get("date_joined") or "").strip()[:10],
        "salary_raw":  (form.get("monthly_salary") or "").strip(),
        "notes":       (form.get("notes") or "").strip()[:500],
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

    raw = data["salary_raw"]
    if raw:
        salary = P.parse_money(raw)
        if salary < 0:
            return data, "Monthly salary cannot be negative."
        if salary > MAX_MONTHLY_SALARY:
            return data, ("That monthly salary is larger than this register "
                          "allows. Check for a stray zero.")
    else:
        salary = 0.0
    data["monthly_salary"] = round(salary, 2)

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
    monthly = sum(float(e.get("monthly_salary") or 0.0)
                  for e in employees().values() if e.get("active"))

    body = ""
    for e in rows:
        code_sub = (f'<span class="emp-sub">{_esc(e.get("code"))}</span>'
                    if e.get("code") else "")
        live = bool(e.get("active"))
        body += (
            f'<tr class="{"" if live else "emp-row-off"}">'
            f'<td><b>{_esc(e.get("name"))}</b>{code_sub}</td>'
            f'<td>{_esc(e.get("designation")) or "&#8212;"}</td>'
            f'<td>{_esc(e.get("site")) or "&#8212;"}</td>'
            f'<td>{_esc(e.get("date_joined")) or "&#8212;"}</td>'
            f'<td class="emp-amt">{rupees(e.get("monthly_salary") or 0.0)}</td>'
            f'<td><span class="emp-badge {"emp-on" if live else "emp-off"}">'
            f'{"Active" if live else "Inactive"}</span></td>'
            f'<td><a class="btn btn-ghost" '
            f'href="{url_for("employee.view_employee", id=e.get("id"))}">Open</a></td>'
            f'</tr>')
    empty = ('<tr><td colspan="7" style="color:var(--muted);text-align:center;">'
             'Nobody on the register yet.</td></tr>')

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
    Who works here, and what each is paid.
    <div class="en-sub">{total_active} active
      {"person" if total_active == 1 else "people"} &middot;
      {rupees(monthly)} a month in salary.
      This register records <b>details and salary only</b>. Attendance,
      overtime and site-wise labour cost are a separate piece of work and are
      not built.</div>
  </div>

  <div class="form-section">
    <table class="emp-table">
      <thead><tr>
        <th>Name</th><th>Designation</th><th>Site</th><th>Joined</th>
        <th class="emp-amt">Monthly salary</th><th>Status</th><th></th>
      </tr></thead>
      <tbody>{body or empty}</tbody>
    </table>
  </div>
""")


def _form(data: dict, error: str, action: str, submit_label: str,
          heading: str, back: str) -> str:
    """The create and edit forms, which are one form with two labels."""
    checked = " checked" if data.get("active") else ""
    return _shell(heading, f"""
  <div class="page-top">
    <h1>{heading}</h1>
    <a href="{back}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {_alert(error)}

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
        <div class="form-group">
          <label for="site">Site</label>
          <input type="text" id="site" name="site" maxlength="160"
                 value="{_esc(data.get('site'))}"
                 placeholder="where they are posted"/>
          <small class="field-hint">Free text. This is where somebody is
            posted, not a link to a project.</small>
        </div>
        <div class="form-group">
          <label for="date_joined">Date Joined</label>
          <input type="date" id="date_joined" name="date_joined"
                 value="{_esc(data.get('date_joined'))}"/>
        </div>
        <div class="form-group">
          <label for="monthly_salary">Monthly Salary (&#8377;)</label>
          <input type="number" id="monthly_salary" name="monthly_salary"
                 min="0" step="0.01" value="{_esc(data.get('salary_raw'))}"/>
          <small class="field-hint">What this person is paid a month. Nothing
            here calculates from it &mdash; no attendance, no overtime, no
            proration.</small>
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
                "id":             eid,
                "name":           data["name"],
                "code":           data["code"],
                "designation":    data["designation"],
                "site":           data["site"],
                "date_joined":    data["date_joined"],
                "monthly_salary": data["monthly_salary"],
                "active":         data["active"],
                "notes":          data["notes"],
                "created_at":     _now(),
                "updated_at":     _now(),
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

  <div class="emp-card">
    <div class="emp-grid">
      {cell("Employee code", _esc(e.get("code")))}
      {cell("Designation", _esc(e.get("designation")))}
      {cell("Site", _esc(e.get("site")))}
      {cell("Date joined", _esc(e.get("date_joined")))}
      {cell("Monthly salary", rupees(e.get("monthly_salary") or 0.0))}
      {cell("Status", "Currently employed" if e.get("active") else "No longer employed")}
    </div>
  </div>

  {f'<div class="emp-card">{cell("Notes", _esc(e.get("notes")))}</div>' if e.get("notes") else ""}

  <div class="emp-note">
    <b>Details and salary only.</b>
    <div class="en-sub">There is no attendance against this record, no overtime,
      and nothing that computes a wage from the figure above. Those are a
      separate piece of work and are not built.</div>
  </div>
""")


@employee_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_employee(id: str):
    """Change somebody's record."""
    e = employees().get(id)
    if not e:
        return redirect(url_for("employee.list_employees",
                                msg="Employee not found.", type="error"))

    data = dict(e)
    data["salary_raw"] = (f"{float(e.get('monthly_salary') or 0.0):.2f}"
                          if e.get("monthly_salary") else "")
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form, except_id=id)
        if not error:
            e.update({
                "name":           data["name"],
                "code":           data["code"],
                "designation":    data["designation"],
                "site":           data["site"],
                "date_joined":    data["date_joined"],
                "monthly_salary": data["monthly_salary"],
                "active":         data["active"],
                "notes":          data["notes"],
                "updated_at":     _now(),
            })
            return redirect(url_for("employee.view_employee", id=id,
                                    msg="Record updated.", type="success"))

    return _form(data, error, action=url_for("employee.edit_employee", id=id),
                 submit_label="Save changes",
                 heading="Edit <span>Employee</span>",
                 back=url_for("employee.view_employee", id=id))


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
