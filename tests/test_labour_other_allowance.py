"""
OTHER ALLOWANCE IS PROJECT LABOUR — CLIENT_CHANGES.md §0 **sixty-seventh**
block (6 November 2026).

The sixty-sixth block read an issued slip's earnings as *wages + OT + travel*
(`attendance.SLIP_COST_HEADS`) and left `other_allowance` out as a declared
judgement call. Manas's ruling reverses that one call: **an issued slip's
earnings on the P&L include other allowance.** Nothing else moves.

What this file holds:

* **The payroll figures do not move.** Every slip figure — basic, OT, travel,
  other allowance, gross, total deduction, net, round-off, payable and the
  carried advance — is pinned as a LITERAL measured on origin's tip `5cc8214`,
  before the change. Only the P&L labour figure may move.
* **A slip with other allowance**: the allowance reaches the projects, split
  by days exactly as the other heads are.
* **A slip without it**: the P&L figure is what it was.
* A **draft** slip carrying an allowance is still the estimate.
"""

import pytest

import attendance as AT
import employee as EMP
import payroll as PAY
import pnl as PNL
from store import STORE

SITE = "oa-jam"
P1, P2 = "oa-jamnagar", "oa-jamnagar-shed"
_OWNED = ("attendance", "employees", "projects", "addresses",
          "pay_entries", "payslips", "settings")


@pytest.fixture()
def world(client):
    """Jamnagar and Jamnagar Shed on ONE site; three workers on 800 a day."""
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["settings"]["labour_cost"] = {"ot_multiplier": "2"}
    STORE["addresses"][SITE] = {"id": SITE, "label": "JAMNAGAR",
                                "type": "site", "archived": False}
    for pid, name in ((P1, "Jamnagar"), (P2, "Jamnagar Shed")):
        STORE["projects"][pid] = {
            "id": pid, "name": name, "norm_name": name.lower(),
            "client": "IOCL", "notes": "", "site_address_id": SITE,
            "site_address": "JAMNAGAR",
            "created_at": "2026-10-01 09:00", "updated_at": "2026-10-01 09:00"}
    for eid, name in (("w1", "RAMESH PATIL"), ("w2", "SURESH JADHAV"),
                      ("w3", "GUDDU KUMAR")):
        STORE["employees"][eid] = {
            "id": eid, "name": name, "code": eid.upper(),
            "designation": "Fitter", "day_rate": 800.0, "active": True,
            "site": "JAMNAGAR", EMP.SITE_ADDRESS_FIELD: SITE,
            EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def _mark(eid, date, pid, status="present", ot=0.0):
    mid = f"{eid}-{date}"
    STORE["attendance"][mid] = {
        "id": mid, "employee_id": eid, "date": date, "status": status,
        "ot_hours": ot, "day_rate": 800.0,
        "employee_name": STORE["employees"][eid]["name"],
        "site": "JAMNAGAR", EMP.SITE_ADDRESS_FIELD: SITE,
        EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK, "project_id": pid,
        "project_name": STORE["projects"][pid]["name"]}


def _entry(eid, kind, amount, date):
    key = f"{eid}-{kind}-{date}"
    STORE["pay_entries"][key] = {"id": key, "employee_id": eid, "date": date,
                                 "type": kind, "amount": amount,
                                 "source": "manual"}


def _slip(eid, month, other=0.0, issue=True):
    """Through payroll.py's own calls: draft, type the allowance, issue."""
    slip, err = PAY.create_draft(eid, month)
    assert not err, err
    slip["other_allowance"] = other
    assert not PAY.refresh(slip)
    if issue:
        assert not PAY.issue(slip)
    return slip


def scenario():
    """
    October 2026, one site, two projects.

    w1  20 days Jamnagar (OT 2h on four of them) + 6 days Shed, one half day;
        travel 500.25, an advance of 2,000, OTHER ALLOWANCE 1,250.50 — ISSUED.
    w2  26 days Shed; an advance of 25,000, bigger than the wages, so the slip
        pays 0 and carries the rest; NO other allowance — ISSUED.
    w3  10 days Jamnagar; other allowance 3,000 on a DRAFT — never issued.
    """
    for d in range(1, 21):
        _mark("w1", f"2026-10-{d:02d}", P1, ot=2.0 if d % 5 == 0 else 0.0,
              status="half" if d == 7 else "present")
    for d in range(21, 27):
        _mark("w1", f"2026-10-{d:02d}", P2)
    _entry("w1", PAY.TRAVEL, 500.25, "2026-10-31")
    _entry("w1", PAY.ADVANCE, 2000.0, "2026-10-15")
    for d in range(1, 27):
        _mark("w2", f"2026-10-{d:02d}", P2)
    _entry("w2", PAY.ADVANCE, 25000.0, "2026-10-10")
    for d in range(1, 11):
        _mark("w3", f"2026-10-{d:02d}", P1)
    return {"w1": _slip("w1", "2026-10", other=1250.50),
            "w2": _slip("w2", "2026-10"),
            "w3": _slip("w3", "2026-10", other=3000.0, issue=False)}


SLIP_KEYS = ("basic", "ot", "travel", "other_allowance", "gross", "advance",
             "loan_deduction", "total_deduction", "net_raw", "round_off",
             "payable", "carry", "paid_days")


def _figures(slip):
    return {k: slip["snapshot"][k] for k in SLIP_KEYS}


# ── The payroll figures, measured on 5cc8214 BEFORE the change ─────────────

# ⚠ Printed by the unchanged code and pasted in. Compared by `repr`, so even
#   an int becoming a float (w2's `travel` is the int 0 on the slip) fails.
PAYROLL_BEFORE = {
    "w1": "{'basic': 20400.0, 'ot': 1600.0, 'travel': 500.25, "
          "'other_allowance': 1250.5, 'gross': 23750.75, 'advance': 2000.0, "
          "'loan_deduction': 0.0, 'total_deduction': 2000.0, "
          "'net_raw': 21750.75, 'round_off': 0.25, 'payable': 21751, "
          "'carry': 0.0, 'paid_days': 25.5}",
    "w2": "{'basic': 20800.0, 'ot': 0.0, 'travel': 0, "
          "'other_allowance': 0.0, 'gross': 20800.0, 'advance': 25000.0, "
          "'loan_deduction': 0.0, 'total_deduction': 25000.0, "
          "'net_raw': -4200.0, 'round_off': 0.0, 'payable': 0, "
          "'carry': 4200.0, 'paid_days': 26.0}",
    "w3": "{'basic': 8000.0, 'ot': 0.0, 'travel': 0, "
          "'other_allowance': 3000.0, 'gross': 11000.0, 'advance': 0, "
          "'loan_deduction': 0.0, 'total_deduction': 0.0, "
          "'net_raw': 11000.0, 'round_off': 0.0, 'payable': 11000, "
          "'carry': 0.0, 'paid_days': 10.0}",
}


def test_payroll_figures_are_byte_identical(world):
    slips = scenario()
    for eid, want in PAYROLL_BEFORE.items():
        assert repr(_figures(slips[eid])) == want, eid
    carried = STORE["pay_entries"][slips["w2"]["carry_entry_id"]]
    assert (carried["date"], carried["type"], carried["amount"]) == \
        ("2026-11-01", PAY.ADVANCE, 4200.0)
    assert slips["w3"]["status"] == PAY.DRAFT


def _labour(pid):
    return PNL.project_pnl(pid)["to_date"]["labour"]


def test_a_slip_with_other_allowance_puts_it_on_the_projects(world):
    """w1's whole slip earnings — 20,400 + 1,600 + 500.25 + 1,250.50 =
    23,750.75 — split 19.5 : 6 paid days across the two projects."""
    scenario()
    assert AT.slip_earnings(STORE["payslips"][[
        k for k, s in STORE["payslips"].items() if s["employee_id"] == "w1"][0]]
    ) == 23750.75
    one, shed = _labour(P1), _labour(P2)
    w1_on_jam = round(23750.75 * 19.5 / 25.5, 2)
    w1_on_shed = round(23750.75 * 6 / 25.5, 2)
    assert one["actual"] == w1_on_jam
    assert shed["actual"] == round(w1_on_shed + 20800.0, 2)


def test_a_slip_without_other_allowance_is_unchanged(world):
    """w2 carries none: Jamnagar Shed's share of w2 is 20,800 before and
    after — the slip's earnings are its wages."""
    scenario()
    w2 = [s for s in STORE["payslips"].values() if s["employee_id"] == "w2"][0]
    assert AT.slip_earnings(w2) == 20800.0


def test_a_draft_with_other_allowance_is_still_the_estimate(world):
    """w3: 10 days × 800 on the estimate; the draft's 3,000 is nowhere."""
    scenario()
    one = _labour(P1)
    assert one["estimate"] == 8000.0
    assert one["total"] == round(one["actual"] + 8000.0, 2)


def test_the_jamnagar_figures(world):
    """
    The two projects' P&L labour, as reported in the §0 block. Measured on
    `5cc8214` before the change: Jamnagar 8,000.00 + 17,206.07 = 25,206.07;
    Jamnagar Shed 0.00 + 26,094.18 = 26,094.18. Only w1's 1,250.50 of other
    allowance moves, split 19.5 : 6 paid days (956.27 and 294.23).
    """
    scenario()
    one, shed = _labour(P1), _labour(P2)
    assert (one["estimate"], one["actual"], one["total"]) == \
        (8000.0, 18162.34, 26162.34)
    assert (shed["estimate"], shed["actual"], shed["total"]) == \
        (0.0, 26388.41, 26388.41)

