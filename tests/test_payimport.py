"""
Importing the client's monthly attendance workbook — CLIENT_CHANGES.md §0
fifty-fifth block (29 October 2026, CHARGED new scope).

The synthetic sheets here are built in memory in the client's own shape (their
September 2026 sheet: a title row, SR.NO | NAME | DESIGNATION | SITE, three
columns a day, then Days … BALANCE LOAN), so nothing here needs their file. The
last test reads their real workbook when it is present at
`client_docs/payroll/ATTENDANCE_DATA.xlsx` (gitignored) and skips otherwise.

What this file holds:

* every column is found by its HEADER, so a 31-day sheet with everything three
  columns further right reads the same;
* blank is not 0; 0.5 is a half day; a "paid leave" comment on a 1 is paid
  leave; anything else is a problem, never a guess;
* names match EXACTLY — "GUDDU" is not "GUDDU KUMAR";
* the preview writes nothing; the commit writes markings and ledger lines
  carrying the batch id, never overwrites a day already marked, seeds an
  opening loan only where there is no loan yet, and fills a blank rate only;
* one import per month, and taking one out is whole, keeps what it did not
  write, and is refused once a slip for the month is issued.
"""

import io
import pathlib

import pytest

import attendance as AT
import payimport as PI
import payroll as PAY
from store import STORE

openpyxl = pytest.importorskip("openpyxl")

REPO = pathlib.Path(__file__).resolve().parent.parent
COLLS = ("employees", "attendance", "pay_entries", "payslips", "pay_imports")
TAIL = ["Days", "OT", "OTCD", "TOTAL DAYS", "PER DAY SALARY", "TOTAL SALARY",
        "ADV", "BALANCE", "EXTRA EXP", "LOAN", "ACTUAL SALARY", "BALANCE LOAN"]


@pytest.fixture(autouse=True)
def _clean():
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    yield
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    for aid in ("addr-roadpali", "addr-office"):
        STORE.setdefault("addresses", {}).pop(aid, None)


def workbook(rows, days=30, title="ATTENDANCE FOR THE MONTH OF SEPTEMPER - 2026"):
    """
    `rows`: dicts with name, designation, site, marks {day: (present, ot)},
    comments {day: text}, and money {rate, adv, extra, loan, actual, bal}.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(1, 1, title)
    for c, h in enumerate(["SR.NO", "NAME", "DESIGNATION", "SITE"], start=1):
        ws.cell(2, c, h)
    for d in range(1, days + 1):
        ws.cell(2, 5 + 3 * (d - 1), float(d))
    tail0 = 5 + 3 * days
    for i, h in enumerate(TAIL):
        ws.cell(2, tail0 + i, h)
    col = {h: tail0 + i for i, h in enumerate(TAIL)}
    for r, row in enumerate(rows, start=3):
        ws.cell(r, 1, float(r - 2))
        ws.cell(r, 2, row["name"])
        ws.cell(r, 3, row.get("designation", "HELPER"))
        ws.cell(r, 4, row.get("site", "ROADPALI"))
        for d, (present, ot) in row.get("marks", {}).items():
            c = 5 + 3 * (d - 1)
            ws.cell(r, c, present)
            if ot is not None:
                ws.cell(r, c + 1, ot)
        for d, text in row.get("comments", {}).items():
            ws.cell(r, 5 + 3 * (d - 1)).comment = openpyxl.comments.Comment(
                text, "HR")
        m = row.get("money", {})
        for key, h in (("rate", "PER DAY SALARY"), ("adv", "ADV"),
                       ("extra", "EXTRA EXP"), ("loan", "LOAN"),
                       ("actual", "ACTUAL SALARY"), ("bal", "BALANCE LOAN")):
            if m.get(key) is not None:
                ws.cell(r, col[h], m[key])
    ws.cell(3 + len(rows), 1, "TOTAL SALARY")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


AMIT = {"name": "AMIT KUMAR YADAV", "site": "ROADPALI",
        "marks": {1: (1, None), 2: (1, 2), 3: (0.5, 1), 4: (0, None),
                  5: (1, None)},
        "comments": {5: "GANPATI PAID LEAVE\n"},
        "money": {"rate": 550, "adv": 1000, "actual": 1406.25}}


# ── 1. reading ───────────────────────────────────────────────────────────────

def test_the_month_comes_from_their_own_spelling():
    assert PI.month_from_title("ATTENDANCE FOR THE MONTH OF SEPTEMPER - 2026") == "2026-09"
    assert PI.month_from_title("Attendance October 2026") == "2026-10"
    assert PI.month_from_title("ATTENDANCE") == ""


def test_parse_reads_each_status_and_skips_a_blank():
    r = PI.parse(workbook([AMIT]), "a.xlsx")
    assert r["problems"] == [] and r["month_guess"] == "2026-09"
    assert r["days"] == 30 and r["sites"] == ["ROADPALI"]
    days = {d["day"]: (d["status"], d["ot"]) for d in r["rows"][0]["days"]}
    assert days == {1: (AT.PRESENT, 0.0), 2: (AT.PRESENT, 2.0),
                    3: (AT.HALF, 1.0), 4: (AT.ABSENT, 0.0),
                    5: (AT.PAID_LEAVE, 0.0)}, "day 6 onward is blank: nothing"
    assert r["rows"][0]["money"]["rate"] == 550


def test_a_31_day_sheet_three_columns_further_right_reads_the_same():
    thirty = PI.parse(workbook([AMIT], days=30))
    thirty_one = PI.parse(workbook([AMIT], days=31,
                                   title="ATTENDANCE FOR THE MONTH OF OCTOBER - 2026"))
    assert thirty_one["days"] == 31
    assert thirty_one["rows"][0]["days"] == thirty["rows"][0]["days"]
    assert thirty_one["rows"][0]["money"] == thirty["rows"][0]["money"]


def test_a_value_that_is_not_1_half_or_0_is_a_problem_not_a_guess():
    bad = dict(AMIT, marks={1: (2, None), 2: (1, 30)})
    r = PI.parse(workbook([bad]))
    assert r["rows"][0]["days"] == []
    assert len(r["rows"][0]["problems"]) == 2


def test_a_sheet_without_the_heading_is_refused():
    wb = openpyxl.Workbook()
    wb.active.cell(1, 1, "nothing here")
    buf = io.BytesIO()
    wb.save(buf)
    r = PI.parse(buf.getvalue())
    assert r["rows"] == [] and r["problems"]


def test_the_preview_figure_is_the_muster_arithmetic():
    row = PI.parse(workbook([AMIT]))["rows"][0]
    # 550 × (1 + 1 + 0.5 + 0 + 1) + 550/8 × (2 + 1) − 1000
    assert PI.app_net(row, "2026-09") == 1131.25


# ── 2. matching ──────────────────────────────────────────────────────────────

def test_names_match_exactly_and_never_fuzzily():
    STORE["employees"]["g1"] = {"id": "g1", "name": "GUDDU", "active": True}
    STORE["employees"]["g2"] = {"id": "g2", "name": "Guddu  Kumar ", "active": True}
    assert PI.match_employee("GUDDU")["id"] == "g1"
    assert PI.match_employee("GUDDU KUMAR")["id"] == "g2"
    assert PI.match_employee("GUDU") == {}


# ── 3. the write ─────────────────────────────────────────────────────────────

def _site():
    STORE.setdefault("addresses", {})["addr-roadpali"] = {
        "id": "addr-roadpali", "label": "ROADPALI", "type": "site",
        "line1": "x", "city": "Navi Mumbai", "state": "Maharashtra",
        "pincode": "410218", "country": "India"}


def _upload(client, data):
    r = client.post("/payroll/import/", data={
        "workbook": (io.BytesIO(data), "ATTENDANCE DATA.xlsx")},
        content_type="multipart/form-data")
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return r.headers["Location"].rsplit("/", 1)[-1]


PUSHKAR = {"name": "PUSHKAR MISHRA", "site": "ROADPALI",
           "marks": {d: (1, None) for d in range(1, 31)},
           "money": {"rate": 833, "adv": 5500, "loan": 10000, "bal": 24200,
                     "actual": 9490}}
NEWBIE = {"name": "NIRAJ", "site": "ROADPALI",
          "marks": {28: (1, None), 29: (1, None), 30: (1, None)},
          "money": {"rate": 600, "adv": 200}}


def test_the_whole_import(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "Pushkar Mishra",
                                "active": True, "day_rate": 0.0, "code": ""}
    sid = _upload(client, workbook([PUSHKAR, NEWBIE, AMIT]))
    assert STORE["attendance"] == {} and STORE["pay_entries"] == {}

    page = client.get(f"/payroll/import/preview/{sid}").get_data(as_text=True)
    assert "PUSHKAR MISHRA" in page and "Nothing has been written" in page
    assert STORE["attendance"] == {}, "the preview writes nothing"

    r = client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "addr-roadpali|",
        "emp_0": "pk", "emp_1": "new", "emp_2": ""})
    assert r.status_code == 302

    pk_days = AT.month_markings("pk", "2026-09")
    assert len(pk_days) == 30
    assert {m["import_batch"] for m in pk_days} == {sid}
    assert STORE["employees"]["pk"]["day_rate"] == 833.0, "a blank rate filled"
    new = [e for e in STORE["employees"].values() if e["name"] == "NIRAJ"]
    assert len(new) == 1 and new[0]["day_rate"] == 600.0
    assert not [e for e in STORE["employees"].values()
                if e["name"] == "AMIT KUMAR YADAV"], "a skipped row writes nothing"

    loan = PAY.loan_figures("pk", "2026-09")
    assert (loan["opening"], loan["deduction"], loan["balance"]) == (
        24200.0, 10000.0, 14200.0)
    assert PAY.snapshot("pk", "2026-09")["payable"] == 9490, \
        "the app's slip equals their ACTUAL SALARY"
    assert STORE["pay_imports"][sid]["status"] == PI.COMMITTED


def test_a_month_is_imported_once(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}
    form = {"month": "2026-09", "site_0": "addr-roadpali|", "emp_0": "pk"}
    a = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{a}", data=form)
    b = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{b}", data=form)
    assert STORE["pay_imports"][b]["status"] == PI.STAGED
    assert len(AT.month_markings("pk", "2026-09")) == 30


def test_a_day_marked_by_hand_is_never_overwritten(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}
    STORE["attendance"]["hand"] = {
        "id": "hand", "date": "2026-09-01", "employee_id": "pk",
        "employee_name": "PUSHKAR MISHRA", "day_rate": 833.0,
        "status": AT.ABSENT, "ot_hours": 0.0, "site": ""}
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "addr-roadpali|", "emp_0": "pk"})
    assert STORE["attendance"]["hand"]["status"] == AT.ABSENT
    assert len(AT.month_markings("pk", "2026-09")) == 30


def test_an_existing_loan_is_compared_never_reseeded(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}
    STORE["pay_entries"]["old"] = {
        "id": "old", "employee_id": "pk", "date": "2026-08-01",
        "type": PAY.LOAN_GIVEN, "amount": 30000.0, "source": "manual"}
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "addr-roadpali|", "emp_0": "pk"})
    kinds = [e["type"] for e in STORE["pay_entries"].values()]
    assert PAY.OPENING_LOAN not in kinds
    assert STORE["pay_imports"][sid]["summary"]["loan_mismatch"]


def test_a_site_must_be_mapped(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "", "emp_0": "pk"})
    assert STORE["attendance"] == {}


def test_taking_an_import_out_is_whole_and_keeps_the_rest(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}
    sid = _upload(client, workbook([PUSHKAR, NEWBIE]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "addr-roadpali|", "emp_0": "pk",
        "emp_1": "new"})
    STORE["attendance"]["hand"] = {
        "id": "hand", "date": "2026-10-01", "employee_id": "pk",
        "status": AT.PRESENT, "day_rate": 833.0}
    assert client.get(f"/payroll/import/delete/{sid}").status_code == 200
    assert AT.batch_markings(sid), "GET confirms and destroys nothing"
    client.post(f"/payroll/import/delete/{sid}")
    assert AT.batch_markings(sid) == [] and PI.batch_entries(sid) == []
    assert "hand" in STORE["attendance"]
    assert [e for e in STORE["employees"].values() if e["name"] == "NIRAJ"], \
        "an employee it created is kept"
    assert STORE["pay_imports"][sid]["status"] == PI.REMOVED


def test_taking_an_import_out_is_refused_once_a_slip_is_issued(client):
    _site()
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "addr-roadpali|", "emp_0": "pk"})
    slip, _ = PAY.create_draft("pk", "2026-09")
    PAY.issue(slip)
    client.post(f"/payroll/import/delete/{sid}")
    assert AT.batch_markings(sid), "refused: the slip was drawn from it"


# ── 4. the client's real September sheet, when it is here ────────────────────

REAL = REPO / "client_docs" / "payroll" / "ATTENDANCE_DATA.xlsx"


@pytest.mark.skipif(not REAL.exists(), reason="the client's workbook is not in "
                    "this checkout (client_docs/ is gitignored)")
def test_the_clients_own_sheet_reads_and_every_net_matches_theirs():
    r = PI.parse(REAL.read_bytes(), REAL.name)
    assert r["month_guess"] == "2026-09" and r["days"] == 30
    assert len(r["rows"]) == 38
    assert r["sites"] == ["OFFICE", "BANGALORE", "JAMNAGAR", "ROADPALI", "GOVANDI"]
    compared = 0
    for row in r["rows"]:
        actual = row["money"].get("actual")
        if actual is None:
            continue
        assert round(actual, 2) == round(PI.app_net(row, "2026-09"), 2), row["name"]
        compared += 1
    assert compared == 37
    paid_leave = {row["name"]: [d["day"] for d in row["days"]
                                if d["status"] == AT.PAID_LEAVE]
                  for row in r["rows"]}
    assert paid_leave["ADITI PATADE"] == [11, 12]
