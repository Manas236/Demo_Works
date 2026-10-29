"""
The payslip and the pay ledger — CLIENT_CHANGES.md §0 fifty-fifth block
(29 October 2026, CHARGED new scope).

The worked examples are the client's OWN September 2026 sheet, four people
from it, figure for figure: Amit Kumar Yadav (overtime and the rupee),
Pushkar Mishra (a loan with a balance), Mahesh Nanaware (the advance bigger
than the wages) and Manjesh Kumar (travel, and a loan deduction with no loan).

What else this file holds:

* the net is rounded HALF UP — never `round()`'s half-to-even, which is what
  the RA bill does (ABOUT.md §7 gap 84);
* their slip's two bugs are fixed: a statutory figure typed on a draft IS
  deducted, and the loan reads opening − deduction = balance;
* an issued slip never moves, and says so when what it was drawn from has;
* one live slip per person per month; a carried advance comes out with its
  slip, and only while the next month is not issued;
* the printed slip is on the shared sheet — its letterhead is the tax
  invoice's — and renders no rail;
* access: Owner, Director and HR; Sales, Purchase and Accounts refused; the
  two destroy routes Owner-only.
"""

import pytest

import attendance as AT
import auth
import docsheet as DS
import payroll as PAY
import settings as S
from store import STORE

COLLS = ("employees", "attendance", "pay_entries", "payslips", "pay_imports")


@pytest.fixture(autouse=True)
def _clean():
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    yield
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)


def _person(eid, name, rate, **over):
    p = {"id": eid, "name": name, "code": "", "designation": "Helper",
         "active": True, "day_rate": rate}
    p.update(over)
    STORE["employees"][eid] = p
    return p


def _mark(eid, day, status=AT.PRESENT, ot=0.0, rate=None):
    rate = STORE["employees"][eid]["day_rate"] if rate is None else rate
    rid = f"{eid}-{day}"
    STORE["attendance"][rid] = {
        "id": rid, "date": day, "employee_id": eid,
        "employee_name": STORE["employees"][eid]["name"], "employee_code": "",
        "day_rate": rate, "site": "", "status": status, "ot_hours": ot}


def _entry(eid, kind, amount, day, source=PAY.SOURCE_MANUAL):
    key = f"{eid}-{kind}-{day}-{amount}"
    STORE["pay_entries"][key] = {
        "id": key, "employee_id": eid, "employee_name": "", "date": day,
        "type": kind, "amount": amount, "note": "", "source": source}


SEPT = [f"2026-09-{d:02d}" for d in range(1, 31)]


def _amit():
    _person("amit", "AMIT KUMAR YADAV", 550.0)
    ot = {2: 2, 4: 3, 5: 3, 7: 3, 8: 3, 10: 3}     # 17 hours
    for i, day in enumerate(SEPT, start=1):
        _mark("amit", day, AT.ABSENT if i == 30 else AT.PRESENT,
              ot.get(i, 0.0))
    _entry("amit", PAY.ADVANCE, 5000.0, "2026-09-30")


# ── 1. the client's own figures ──────────────────────────────────────────────

def test_amit_kumar_yadav_overtime_and_the_rupee():
    _amit()
    s = PAY.snapshot("amit", "2026-09")
    assert s["paid_days"] == 29 and s["ot_hours"] == 17
    assert s["basic"] == 15950.0
    assert s["ot"] == 1168.75            # 550 / 8 × 17 at the client's 1×
    assert s["gross"] == 17118.75
    assert s["net_raw"] == 12118.75      # their ACTUAL SALARY, to the paisa
    assert s["payable"] == 12119 and s["round_off"] == 0.25
    assert s["ot_rate"] == 68.75


def test_pushkar_mishra_a_loan_with_a_balance():
    _person("pk", "PUSHKAR MISHRA", 833.0)
    for day in SEPT:
        _mark("pk", day)
    _entry("pk", PAY.OPENING_LOAN, 24200.0, "2026-09-01")
    _entry("pk", PAY.ADVANCE, 5500.0, "2026-09-30")
    _entry("pk", PAY.LOAN_DEDUCTION, 10000.0, "2026-09-30")
    s = PAY.snapshot("pk", "2026-09")
    assert s["gross"] == 24990.0
    assert (s["loan_opening"], s["loan_deduction"], s["loan_balance"]) == (
        24200.0, 10000.0, 14200.0)
    assert s["total_deduction"] == 15500.0
    assert s["payable"] == 9490
    # …and in October the loan opens at what September left.
    assert PAY.loan_figures("pk", "2026-10")["opening"] == 14200.0


def test_mahesh_nanaware_the_advance_bigger_than_the_wages():
    _person("mn", "MAHESH NANAWARE", 1000.0)
    for day in SEPT[:4]:
        _mark("mn", day)
    _entry("mn", PAY.ADVANCE, 6000.0, "2026-09-30")
    slip, err = PAY.create_draft("mn", "2026-09")
    assert not err
    assert slip["snapshot"]["payable"] == 0
    assert slip["snapshot"]["carry"] == 2000.0
    assert not PAY.issue(slip)
    carried = STORE["pay_entries"][slip["carry_entry_id"]]
    assert (carried["type"], carried["date"], carried["amount"]) == (
        PAY.ADVANCE, "2026-10-01", 2000.0)
    # October's slip carries it as an advance.
    assert PAY.snapshot("mn", "2026-10")["advance"] == 2000.0


def test_manjesh_kumar_travel_and_a_deduction_with_no_loan():
    _person("mk", "MANJESH KUMAR", 500.0)
    ot = {9: 2, 10: 2, 11: 2, 12: 2, 13: 2, 14: 2, 15: 2, 16: 2}   # 16 hours
    for i, day in enumerate(SEPT, start=1):
        if i >= 8:
            _mark("mk", day, ot=ot.get(i, 0.0))
    _entry("mk", PAY.ADVANCE, 3000.0, "2026-09-30")
    _entry("mk", PAY.TRAVEL, 1820.0, "2026-09-30")
    _entry("mk", PAY.LOAN_DEDUCTION, 2000.0, "2026-09-30")
    s = PAY.snapshot("mk", "2026-09")
    assert s["paid_days"] == 23 and s["ot_hours"] == 16
    assert s["gross"] == 14320.0
    assert s["payable"] == 9320
    assert s["loan_balance"] == -2000.0, "warned, never blocked, shown signed"


# ── 2. the rupee and the client's slip's bugs ────────────────────────────────

@pytest.mark.parametrize("raw,want", [(100.5, 101), (101.5, 102),
                                      (1456.5, 1457), (1457.5, 1458),
                                      (99.49, 99), (0.5, 1)])
def test_the_rupee_is_half_up_not_half_even(raw, want):
    assert PAY.rupee_half_up(raw) == want


def test_a_typed_statutory_figure_is_deducted():
    _amit()
    slip, _ = PAY.create_draft("amit", "2026-09")
    slip["statutory"] = {"mlwf": 0, "pf": 100, "esic": 0, "pt": 200}
    PAY.refresh(slip)
    s = slip["snapshot"]
    assert s["pf"] == 100 and s["pt"] == 200
    assert s["total_deduction"] == 5300.0
    assert s["payable"] == 11819          # 12118.75 − 300, half up


def test_the_overtime_follows_the_setting():
    _amit()
    STORE["settings"][S.LABOUR_RECORD] = {"ot_multiplier": "2"}
    assert PAY.snapshot("amit", "2026-09")["ot"] == 2337.5


# ── 3. the slip's life ───────────────────────────────────────────────────────

def test_one_live_slip_per_person_per_month():
    _amit()
    a, _ = PAY.create_draft("amit", "2026-09")
    b, err = PAY.create_draft("amit", "2026-09")
    assert b == {} and err
    assert not PAY.cancel(a, "wrong month")
    c, err = PAY.create_draft("amit", "2026-09")
    assert c and not err


def test_cancel_needs_a_reason():
    _amit()
    a, _ = PAY.create_draft("amit", "2026-09")
    assert PAY.cancel(a, "  ")
    assert a["status"] == PAY.DRAFT


def test_an_issued_slip_never_moves_and_says_so(client):
    _amit()
    slip, _ = PAY.create_draft("amit", "2026-09")
    PAY.issue(slip)
    before = client.get(f"/payroll/slip/print/{slip['id']}").get_data()
    STORE["employees"]["amit"]["name"] = "SOMEBODY ELSE"
    STORE["employees"]["amit"]["day_rate"] = 900.0
    _entry("amit", PAY.ADVANCE, 1000.0, "2026-09-15")
    after = client.get(f"/payroll/slip/print/{slip['id']}").get_data()
    assert before == after, "an issued slip prints from its own rows only"
    assert not PAY.refresh(slip) == "", "an issued slip is never refreshed"
    view = client.get(f"/payroll/slip/{slip['id']}").get_data(as_text=True)
    assert "Changed since this slip was" in view


def test_a_draft_refreshes():
    _amit()
    slip, _ = PAY.create_draft("amit", "2026-09")
    _entry("amit", PAY.ADVANCE, 1000.0, "2026-09-15")
    assert slip["snapshot"]["advance"] == 5000.0
    assert PAY.refresh(slip) == ""
    assert slip["snapshot"]["advance"] == 6000.0


def test_cancelling_removes_the_carry_only_while_next_month_is_open():
    _person("mn", "MAHESH NANAWARE", 1000.0)
    for day in SEPT[:4]:
        _mark("mn", day)
    _entry("mn", PAY.ADVANCE, 6000.0, "2026-09-30")
    _mark("mn", "2026-10-01")
    sep, _ = PAY.create_draft("mn", "2026-09")
    PAY.issue(sep)
    carry_id = sep["carry_entry_id"]
    oct_, _ = PAY.create_draft("mn", "2026-10")
    PAY.issue(oct_)
    err = PAY.cancel(sep, "redo")
    assert err and carry_id in STORE["pay_entries"], "October was drawn with it"
    assert not PAY.cancel(oct_, "redo")
    assert not PAY.cancel(sep, "redo")
    assert carry_id not in STORE["pay_entries"]


def test_a_slip_never_feeds_itself_its_own_carry():
    _person("mn", "MAHESH NANAWARE", 1000.0)
    for day in SEPT[:4]:
        _mark("mn", day)
    _entry("mn", PAY.ADVANCE, 6000.0, "2026-09-30")
    sep, _ = PAY.create_draft("mn", "2026-09")
    PAY.issue(sep)
    assert sep["snapshot"]["advance"] == 6000.0


# ── 4. the printed sheet ─────────────────────────────────────────────────────

def test_the_slip_prints_on_the_shared_sheet_and_without_the_rail(client):
    _amit()
    slip, _ = PAY.create_draft("amit", "2026-09")
    html = client.get(f"/payroll/slip/print/{slip['id']}").get_data(as_text=True)
    assert DS.letterhead() in html, "the tax invoice's letterhead, byte for byte"
    assert '<nav class="rail"' not in html
    assert DS.PRINT_EDGE_STYLES in html
    for label in ("Basic", "OT Payment", "Travelling Expenses", "Gross Salary",
                  "Loan Deduction", "Loan Balance", "Salary Advance", "PF",
                  "Total Deduction", "Actual Salary", "Prepared By",
                  "Received By", "12,119.00"):
        assert label in html, label
    assert "DRAFT" in html


def test_the_month_print_carries_only_issued_slips(client):
    _amit()
    _person("pk", "PUSHKAR MISHRA", 833.0)
    _mark("pk", "2026-09-01")
    a, _ = PAY.create_draft("amit", "2026-09")
    PAY.create_draft("pk", "2026-09")
    PAY.issue(a)
    html = client.get("/payroll/print-month?month=2026-09").get_data(as_text=True)
    assert "AMIT KUMAR YADAV" in html and "PUSHKAR MISHRA" not in html
    assert '<nav class="rail"' not in html


def test_the_register_lists_the_month_and_creates_drafts(client):
    _amit()
    html = client.get("/payroll/?month=2026-09").get_data(as_text=True)
    assert "AMIT KUMAR YADAV" in html and "12,119.00" in html
    r = client.post("/payroll/generate?month=2026-09")
    assert r.status_code == 302
    assert len(STORE["payslips"]) == 1
    client.post("/payroll/generate?month=2026-09")
    assert len(STORE["payslips"]) == 1, "never a second live slip"


# ── 5. the ledger ────────────────────────────────────────────────────────────

def test_the_ledger_adds_an_entry_and_derives_the_balance(client):
    _person("pk", "PUSHKAR MISHRA", 833.0)
    r = client.post("/payroll/entries/add", data={
        "employee_id": "pk", "date": "2026-09-01", "type": PAY.LOAN_GIVEN,
        "amount": "5000", "note": "festival"})
    assert r.status_code == 302
    _entry("pk", PAY.LOAN_DEDUCTION, 1500.0, "2026-09-30")
    assert PAY.loan_balance("pk") == 3500.0
    assert all("balance" not in e for e in STORE["pay_entries"].values()), \
        "no balance is stored"


@pytest.mark.parametrize("amount", ["0", "-5", "abc", "99999999"])
def test_the_ledger_refuses_a_bad_amount(client, amount):
    _person("pk", "PUSHKAR MISHRA", 833.0)
    client.post("/payroll/entries/add", data={
        "employee_id": "pk", "date": "2026-09-01", "type": PAY.ADVANCE,
        "amount": amount})
    assert STORE["pay_entries"] == {}


def test_a_carried_entry_is_not_edited_or_deleted_from_the_ledger(client):
    _person("mn", "MAHESH NANAWARE", 1000.0)
    _mark("mn", "2026-09-01")
    _entry("mn", PAY.ADVANCE, 6000.0, "2026-09-30")
    slip, _ = PAY.create_draft("mn", "2026-09")
    PAY.issue(slip)
    cid = slip["carry_entry_id"]
    client.post(f"/payroll/entries/delete/{cid}")
    client.post(f"/payroll/entries/edit/{cid}", data={
        "employee_id": "mn", "date": "2026-10-01", "type": PAY.ADVANCE,
        "amount": "1"})
    assert STORE["pay_entries"][cid]["amount"] == 5000.0


def test_delete_confirms_on_get_and_destroys_on_post(client):
    _person("pk", "PUSHKAR MISHRA", 833.0)
    _entry("pk", PAY.ADVANCE, 100.0, "2026-09-02")
    eid = next(iter(STORE["pay_entries"]))
    assert client.get(f"/payroll/entries/delete/{eid}").status_code == 200
    assert eid in STORE["pay_entries"]
    client.post(f"/payroll/entries/delete/{eid}")
    assert eid not in STORE["pay_entries"]


# ── 6. access ────────────────────────────────────────────────────────────────

def _user_with(slug):
    auth.ensure_builtin_roles()
    name = f"pay-test-{slug}"
    old = auth.find_user(name)
    if old:
        del STORE["users"][old["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="payroll-test")


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


@pytest.mark.parametrize("slug,ok", [("hr", True), ("director", True),
                                     ("sales-manager", False),
                                     ("purchase-manager", False),
                                     ("accountant", False),
                                     ("operation-head", False)])
def test_who_may_open_the_payslips(client, slug, ok):
    _as(client, _user_with(slug))
    r = client.get("/payroll/?month=2026-09")
    assert (r.status_code == 200) is ok


def test_a_director_cannot_delete_a_pay_entry(client):
    _person("pk", "PUSHKAR MISHRA", 833.0)
    _entry("pk", PAY.ADVANCE, 100.0, "2026-09-02")
    eid = next(iter(STORE["pay_entries"]))
    _as(client, _user_with("director"))
    client.post(f"/payroll/entries/delete/{eid}")
    assert eid in STORE["pay_entries"], "Owner-only, like the marking"
    assert "payroll.delete_entry" in auth.OWNER_ONLY
    assert "payimport.delete_import" in auth.OWNER_ONLY
