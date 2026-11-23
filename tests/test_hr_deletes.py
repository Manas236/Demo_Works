"""
HR deletes her own attendance imports and DRAFT payslips — CLIENT_CHANGES.md
§0 eighty-sixth block (23 November 2026, ruled 23 Nov).

On 13 November HR got "Only an Owner can do this" taking an import out: the
/payroll/import/ "Take out" link was drawn on `payroll.delete` (HR holds it)
while `payimport.delete_import` was in `auth.OWNER_ONLY`. Now:

* `payimport.delete_import` — `payroll.delete`, and a non-Owner only for an
  import they uploaded; an Owner for any.
* `payroll.delete_slip` — a DRAFT only, for everybody; issued slips are
  cancelled (unchanged, `payroll.issue`), never deleted.
"""

import pytest

import auth
import payroll as PAY
from store import STORE
from test_payimport import _site, _upload, workbook, PUSHKAR

COLLS = ("employees", "attendance", "pay_entries", "payslips", "pay_imports")


@pytest.fixture(autouse=True)
def _clean():
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    users_before = set(STORE.setdefault("users", {}))
    yield
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    # The logins a test made are taken back out (STORE["users"] outlives it).
    for uid in set(STORE["users"]) - users_before:
        STORE["users"].pop(uid, None)


def _user(slug, name=None):
    auth.ensure_builtin_roles()
    name = name or f"hrdel-{slug}"
    old = auth.find_user(name)
    if old:
        del STORE["users"][old["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="hr-delete-test")


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


def _person():
    STORE["employees"]["pk"] = {"id": "pk", "name": "PUSHKAR MISHRA",
                                "active": True, "day_rate": 833.0, "code": ""}


def _committed_import(client):
    _site()
    _person()
    sid = _upload(client, workbook([PUSHKAR]))
    client.post(f"/payroll/import/commit/{sid}", data={
        "month": "2026-09", "site_0": "addr-roadpali", "emp_0": "pk"})
    assert STORE["pay_imports"][sid]["status"] == "committed"
    return sid


def test_the_route_left_the_owner_tier():
    assert "payimport.delete_import" not in auth.OWNER_ONLY
    assert "payroll.delete_slip" not in auth.OWNER_ONLY
    assert auth.ROUTE_PERMISSIONS["payroll.delete_slip"] == "payroll.delete"
    assert "payroll.delete" in dict((k, v) for k, (_n, v) in
                                    auth.BUILTIN_ROLES.items())["hr"]
    # Issued slips: still cancelled, not deleted; the cancel route unchanged.
    assert auth.ROUTE_PERMISSIONS["payroll.cancel_slip"] == "payroll.issue"
    assert "payroll.delete_entry" in auth.OWNER_ONLY, "ledger entries unchanged"
    assert "attendance.delete_attendance" in auth.OWNER_ONLY


def test_hr_takes_out_her_own_import(client):
    hr = _user("hr")
    _as(client, hr)
    sid = _committed_import(client)
    assert STORE["pay_imports"][sid]["uploaded_by_id"] == hr["id"]
    page = client.get("/payroll/import/").get_data(as_text=True)
    assert f'/payroll/import/delete/{sid}">Take out</a>' in page
    assert client.get(f"/payroll/import/delete/{sid}").status_code == 200
    client.post(f"/payroll/import/delete/{sid}")
    assert STORE["pay_imports"][sid]["status"] == "removed"
    assert STORE["attendance"] == {}


def test_hr_cannot_take_out_somebody_elses_import(client):
    sid = _committed_import(client)                 # uploaded by the Owner
    _as(client, _user("hr"))
    page = client.get("/payroll/import/").get_data(as_text=True)
    assert "Take out" not in page
    r = client.post(f"/payroll/import/delete/{sid}")
    assert r.status_code == 302 and "uploaded" in r.headers["Location"]
    assert STORE["pay_imports"][sid]["status"] == "committed"
    assert len(STORE["attendance"]) == 30


def test_a_legacy_import_is_matched_on_the_uploaders_exact_name(client):
    hr = _user("hr", "sonali")
    sid = _committed_import(client)
    rec = STORE["pay_imports"][sid]
    rec.pop("uploaded_by_id")
    rec["uploaded_by"] = "sonali"
    _as(client, hr)
    client.post(f"/payroll/import/delete/{sid}")
    assert rec["status"] == "removed"


def test_the_owner_takes_out_anybodys_import(client):
    hr = _user("hr")
    _as(client, hr)
    sid = _committed_import(client)
    _as(client, auth.find_user("test-owner"))
    client.post(f"/payroll/import/delete/{sid}")
    assert STORE["pay_imports"][sid]["status"] == "removed"


def test_a_role_without_payroll_delete_is_still_refused(client):
    sid = _committed_import(client)
    _as(client, _user("accountant"))
    assert client.post(f"/payroll/import/delete/{sid}").status_code == 403
    assert STORE["pay_imports"][sid]["status"] == "committed"


def _draft():
    _person()
    slip, err = PAY.create_draft("pk", "2026-09")
    assert not err
    return slip


def test_hr_deletes_a_draft_payslip(client):
    slip = _draft()
    _as(client, _user("hr"))
    page = client.get(f"/payroll/slip/{slip['id']}").get_data(as_text=True)
    assert f'/payroll/slip/{slip["id"]}/delete">Delete draft</a>' in page
    r = client.post(f"/payroll/slip/{slip['id']}/delete")
    assert r.status_code == 302
    assert slip["id"] not in STORE["payslips"]
    assert PAY.live_slip("pk", "2026-09") == {}, "the month is free again"


@pytest.mark.parametrize("who", ["hr", "owner"])
def test_an_issued_or_cancelled_slip_is_never_deleted(client, who):
    slip = _draft()
    assert not PAY.issue(slip)
    if who == "hr":
        _as(client, _user("hr"))
    page = client.get(f"/payroll/slip/{slip['id']}").get_data(as_text=True)
    assert "Delete draft" not in page
    client.post(f"/payroll/slip/{slip['id']}/delete")
    assert STORE["payslips"][slip["id"]]["status"] == PAY.ISSUED
    assert not PAY.cancel(slip, "wrong month")
    client.post(f"/payroll/slip/{slip['id']}/delete")
    assert STORE["payslips"][slip["id"]]["status"] == PAY.CANCELLED


def test_sales_cannot_delete_a_draft(client):
    slip = _draft()
    _as(client, _user("sales-manager"))
    assert client.post(f"/payroll/slip/{slip['id']}/delete").status_code == 403
    assert slip["id"] in STORE["payslips"]
