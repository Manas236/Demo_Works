"""
Choosing which payslips to print, issue or draft — CLIENT_CHANGES.md §0's
SEVENTY-THIRD block (13 November 2026, NO CHARGE, a usability fix to the
fifty-fifth block's payslip).

HR could not choose WHICH slips: *Print every issued slip* printed every
ISSUED slip of the month and nothing else, and issuing was one slip at a time.
What this file holds, ruling by ruling:

* the register draws a tick on every row, a select-all, Clear and a count,
  and its three filters (`q`, `site`, `status`) work on the server;
* *Print selected* prints the ticked people's LIVE slips — Issued and Draft,
  the draft stamped — never a cancelled one, names a ticked person with no
  slip, ignores ids it never drew, is capped, and each sheet is byte-identical
  to that slip's own print;
* *Issue selected*: the first POST writes NOTHING; the second calls the
  single `issue()` per draft (so the carry entry is the single route's), skips
  the rest with reasons, and is refused without `payroll.issue` on both POSTs;
* *Create drafts for selected* is `create_draft()` for the ticked only;
* `/payroll/print-month` is unchanged for issued slips, and its empty message
  counts the drafts.
"""

import copy
import re

import pytest

import attendance as AT
import auth
import payroll as PAY
import settings as S
from store import STORE

COLLS = ("employees", "attendance", "pay_entries", "payslips", "pay_imports")
MONTH = "2026-09"


@pytest.fixture(autouse=True)
def _clean():
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)
    yield
    for c in COLLS:
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(S.LABOUR_RECORD, None)


def _person(eid, name, rate=1000.0, code=""):
    STORE["employees"][eid] = {"id": eid, "name": name, "code": code,
                               "designation": "Helper", "active": True,
                               "day_rate": rate}


def _mark(eid, day, site=""):
    rid = f"{eid}-{day}-{site}"
    STORE["attendance"][rid] = {
        "id": rid, "date": day, "employee_id": eid,
        "employee_name": STORE["employees"][eid]["name"], "employee_code": "",
        "day_rate": STORE["employees"][eid]["day_rate"], "site": site,
        "status": AT.PRESENT, "ot_hours": 0.0}


def _advance(eid, amount, day):
    key = f"{eid}-adv-{day}-{amount}"
    STORE["pay_entries"][key] = {
        "id": key, "employee_id": eid, "employee_name": "", "date": day,
        "type": PAY.ADVANCE, "amount": amount, "note": "",
        "source": PAY.SOURCE_MANUAL}


def _crew():
    """
    Five people on September: ANITA issued, BHARAT draft, CHETAN cancelled
    (and nothing live), DEEPA no slip, EKTA draft with an advance bigger than
    her wages (so issuing her carries). Two sites.
    """
    _person("a", "ANITA", code="SF-01")
    _person("b", "BHARAT", code="SF-02")
    _person("c", "CHETAN", code="SF-03")
    _person("d", "DEEPA", code="SF-04")
    _person("e", "EKTA", code="SF-05")
    _mark("a", "2026-09-01", "Pune Plant")
    _mark("a", "2026-09-02", "Thane Tower")
    _mark("b", "2026-09-01", "Pune Plant")
    _mark("c", "2026-09-01", "Thane Tower")
    _mark("d", "2026-09-01", "Thane Tower")
    _mark("e", "2026-09-01", "")
    _advance("e", 5000.0, "2026-09-20")
    a, _ = PAY.create_draft("a", MONTH)
    PAY.issue(a)
    b, _ = PAY.create_draft("b", MONTH)
    c, _ = PAY.create_draft("c", MONTH)
    PAY.cancel(c, "wrong rate")
    e, _ = PAY.create_draft("e", MONTH)
    return {"a": a, "b": b, "c": c, "e": e}


def _html(client, url, **kw):
    r = client.get(url, **kw)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def _register_names(html):
    """The employees the register DREW a tick for, in order."""
    return re.findall(r'name="emp" value="([^"]*)"', html)


# ── the reader ───────────────────────────────────────────────────────────────

def test_sites_marked_in_reads_the_marking_label_and_skips_a_blank():
    _crew()
    _mark("a", "2026-10-01", "Elsewhere")            # another month
    got = AT.sites_marked_in(MONTH)
    assert got == {"a": {"Pune Plant", "Thane Tower"}, "b": {"Pune Plant"},
                   "c": {"Thane Tower"}, "d": {"Thane Tower"}}
    assert "e" not in got, "a marking with no site files nobody under a site"
    assert AT.sites_marked_in("nonsense") == {}


# ── 1. the register ──────────────────────────────────────────────────────────

def test_the_register_draws_a_tick_per_row_select_all_clear_and_a_count(client):
    _crew()
    html = _html(client, f"/payroll/?month={MONTH}")
    assert _register_names(html) == ["a", "b", "c", "d", "e"]
    assert 'id="pay-all"' in html and 'id="pay-clear"' in html
    assert 'type="reset"' in html, "Clear works with no script"
    assert 'id="pay-count"' in html and "0 selected" in html
    for label in ("Print selected", "Issue selected",
                  "Create drafts for selected",
                  "Create the month&rsquo;s missing drafts",
                  "Print every issued slip"):
        assert label in html, label
    assert 'formaction="/payroll/print-selected"' in html
    assert 'formaction="/payroll/issue-selected"' in html
    assert 'formaction="/payroll/create-selected"' in html


def test_the_issue_and_draft_buttons_follow_the_permission(client):
    _crew()
    user = _hr_without("payroll.issue", "payroll.edit")
    _as(client, user)
    html = _html(client, f"/payroll/?month={MONTH}")
    assert "Print selected" in html
    assert "Issue selected" not in html
    assert "Create drafts for selected" not in html


@pytest.mark.parametrize("q,want", [
    ("anita", ["a"]), ("ANI", ["a"]), ("sf-03", ["c"]), ("SF-0", list("abcde")),
    ("nobody", []), ("", list("abcde"))])
def test_the_search_matches_name_or_code(client, q, want):
    _crew()
    html = _html(client, "/payroll/", query_string={"month": MONTH, "q": q})
    assert _register_names(html) == want
    if not want:
        assert "matches the filters" in html


def test_the_site_filter_keeps_anyone_marked_there_at_least_once(client):
    _crew()
    html = _html(client, "/payroll/",
                 query_string={"month": MONTH, "site": "Thane Tower"})
    assert _register_names(html) == ["a", "c", "d"]
    html = _html(client, "/payroll/",
                 query_string={"month": MONTH, "site": "Pune Plant"})
    assert _register_names(html) == ["a", "b"]
    # The dropdown is filled from the month's markings.
    assert '<option value="Pune Plant"' in html
    assert '<option value="Thane Tower"' in html


@pytest.mark.parametrize("status,want", [
    ("", list("abcde")), ("draft", ["b", "e"]), ("issued", ["a"]),
    ("none", ["c", "d"]), ("garbage", list("abcde"))])
def test_the_status_filter(client, status, want):
    _crew()
    html = _html(client, "/payroll/",
                 query_string={"month": MONTH, "status": status})
    assert _register_names(html) == want


def test_filters_combine_and_select_all_reaches_only_the_rows_shown(client):
    _crew()
    html = _html(client, "/payroll/", query_string={
        "month": MONTH, "status": "draft", "site": "Pune Plant"})
    assert _register_names(html) == ["b"]
    assert "Showing 1 of 5" in html
    # The selection form carries the filters back, so the redirect keeps them.
    assert 'name="status" value="draft"' in html
    assert 'name="site" value="Pune Plant"' in html


# ── 2. Print selected ────────────────────────────────────────────────────────

def _print_selected(client, *ids, month=MONTH):
    return _html(client, "/payroll/print-selected",
                 query_string=[("month", month)] + [("emp", i) for i in ids])


def test_print_selected_prints_only_the_ticked_issued_and_draft(client):
    _crew()
    html = _print_selected(client, "a", "b", "c", "d")
    assert html.count('<div class="slip-page">') == 2
    assert "ANITA" in html and "BHARAT" in html
    assert "EKTA" not in html, "not ticked, not printed"
    assert html.count('<div class="slip-mark">DRAFT</div>') == 1
    assert '<div class="slip-mark">CANCELLED</div>' not in html, \
        "a cancelled slip never prints"
    assert "1 issued, 1 draft (stamped DRAFT)" in html
    # CHETAN (cancelled only) and DEEPA have no live slip: named, not printed.
    assert "create the draft first: CHETAN, DEEPA." in html
    assert '<nav class="rail"' not in html


def test_print_selected_sorts_by_name(client):
    _crew()
    html = _print_selected(client, "e", "b", "a")
    assert html.index("ANITA") < html.index("BHARAT") < html.index("EKTA")


def test_each_sheet_is_byte_identical_to_the_slips_own_print(client):
    slips = _crew()
    html = _print_selected(client, "a", "b", "e")
    for key in ("a", "b", "e"):
        own = _html(client, f"/payroll/slip/print/{slips[key]['id']}")
        sheet = own[own.index('<div class="slip-page">'):
                    own.rindex("</div>\n</div>\n</body>") + len("</div>")]
        assert sheet.startswith('<div class="slip-page">')
        assert sheet in html, f"{key}'s sheet differs from its own print"


def test_unknown_and_out_of_month_ids_are_ignored(client):
    _crew()
    _person("z", "ZOYA")
    _mark("z", "2026-10-03")                     # October only
    html = _print_selected(client, "a", "NO-SUCH-ID", "z", "")
    assert html.count('<div class="slip-page">') == 1
    assert "ZOYA" not in html and "NO-SUCH-ID" not in html
    assert "create the draft first" not in html


def test_nothing_printable_renders_the_summary_not_an_empty_page(client):
    _crew()
    html = _print_selected(client, "c", "d")
    assert '<div class="slip-page">' not in html
    assert "Nothing to print." in html and "CHETAN, DEEPA" in html
    html = _print_selected(client)
    assert "Nobody is ticked" in html


def test_the_number_of_ids_is_capped_at_the_employee_count(client):
    _crew()                                              # five employees
    html = _print_selected(client, "x1", "x2", "x3", "x4", "x5", "a")
    assert '<div class="slip-page">' not in html, (
        "a sixth id past five employees must never be looked up")
    assert len(PAY.picked_ids(["a"] * 1000 + ["b"], MONTH)) == 1
    assert PAY.picked_ids(["b", "a", "b"], MONTH) == ["b", "a"]


# ── 3. Issue selected ────────────────────────────────────────────────────────

def _state():
    return copy.deepcopy({c: STORE.get(c) for c in COLLS})


def test_the_first_post_writes_nothing_and_lists_what_it_would_do(client):
    _crew()
    before = _state()
    r = client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["a", "b", "c", "d", "e"]})
    assert r.status_code == 200
    assert _state() == before, "the confirmation page wrote to the store"
    html = r.get_data(as_text=True)
    assert "Issue these 2" in html
    assert "BHARAT" in html and "EKTA" in html
    b_net = STORE["payslips"][next(s for s in STORE["payslips"]
                                   if STORE["payslips"][s]["employee_id"] == "b")]
    total = PAY._money(b_net["snapshot"]["payable"])
    assert f"<b>{total}</b>" in html, "the total net (EKTA's net is 0)"
    assert "4,000.00" in html, "EKTA's carry is shown"
    assert "ANITA &mdash; already issued" in html
    assert "CHETAN &mdash; cancelled" in html
    assert "DEEPA &mdash; no slip" in html
    assert 'name="confirm" value="1"' in html


def test_the_second_post_issues_the_drafts_through_issue(client):
    slips = _crew()
    r = client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["a", "b", "c", "d", "e"], "confirm": "1",
        "status": "draft"})
    assert r.status_code == 302
    assert "status=draft" in r.location, "the filters come back"
    assert "2+issued%2C+3+skipped" in r.location or \
        "2 issued, 3 skipped" in r.location.replace("+", " ").replace("%2C", ",")
    assert slips["b"]["status"] == PAY.ISSUED
    assert slips["e"]["status"] == PAY.ISSUED
    assert slips["a"]["status"] == PAY.ISSUED            # untouched
    assert slips["c"]["status"] == PAY.CANCELLED
    assert PAY.live_slip("d", MONTH) == {}, "issuing never creates a slip"
    carry = STORE["pay_entries"][slips["e"]["carry_entry_id"]]
    assert (carry["type"], carry["date"], carry["amount"], carry["source"]) == (
        PAY.ADVANCE, "2026-10-01", 4000.0, PAY.CARRY_PREFIX + slips["e"]["id"])


def test_the_carry_entry_is_exactly_what_a_single_issue_writes(client):
    """Two identical people; one issued alone, one through the bulk route."""
    for eid, name in (("p", "PARIDHI"), ("q", "QASIM")):
        _person(eid, name)
        _mark(eid, "2026-09-01")
        _advance(eid, 3000.0, "2026-09-25")
    p, _ = PAY.create_draft("p", MONTH)
    q, _ = PAY.create_draft("q", MONTH)
    client.post(f"/payroll/slip/{p['id']}/issue")
    client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["q"], "confirm": "1"})
    one = STORE["pay_entries"][p["carry_entry_id"]]
    bulk = STORE["pay_entries"][q["carry_entry_id"]]
    volatile = {"id", "employee_id", "employee_name", "source", "created_at",
                "updated_at"}
    assert {k: v for k, v in one.items() if k not in volatile} == \
           {k: v for k, v in bulk.items() if k not in volatile}
    assert set(one) == set(bulk)
    assert {k: v for k, v in p["snapshot"].items() if k not in (
        "employee_name", "entry_ids")} == {
        k: v for k, v in q["snapshot"].items() if k not in (
            "employee_name", "entry_ids")}


def test_the_second_post_rechecks_and_never_trusts_the_first_page(client):
    slips = _crew()
    client.post("/payroll/issue-selected", data={"month": MONTH,
                                                 "emp": ["b", "e"]})
    # Between the two POSTs: B is cancelled elsewhere.
    PAY.cancel(slips["b"], "changed my mind")
    r = client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["b", "e"], "confirm": "1"})
    assert "1 issued, 1 skipped" in r.location.replace("+", " ").replace("%2C", ",")
    assert slips["b"]["status"] == PAY.CANCELLED
    assert slips["e"]["status"] == PAY.ISSUED


def test_issue_selected_with_nothing_ticked_goes_back(client):
    _crew()
    before = _state()
    r = client.post("/payroll/issue-selected", data={"month": MONTH,
                                                     "confirm": "1"})
    assert r.status_code == 302 and "Tick" in r.location
    assert _state() == before


def _hr_without(*perms):
    auth.ensure_builtin_roles()
    name = "pay-select-hr"
    old = auth.find_user(name)
    if old:
        del STORE["users"][old["id"]]
    user = auth.create_user(name, name, f"pw-{name}-12345", ["role-hr"],
                            created_by="payroll-select-test")
    user[auth.PERM_DENY_FIELD] = list(perms)
    return user


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


def test_issue_selected_is_refused_without_payroll_issue_on_both_posts(client):
    _crew()
    _as(client, _hr_without("payroll.issue"))
    before = _state()
    first = client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["b", "e"]})
    second = client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["b", "e"], "confirm": "1"})
    for r in (first, second):
        assert r.status_code in (302, 403)
        assert "Issue these" not in r.get_data(as_text=True)
    assert _state() == before
    assert auth.ROUTE_PERMISSIONS["payroll.issue_selected"] == "payroll.issue"


def test_the_hr_role_holding_issue_may_issue(client):
    slips = _crew()
    _as(client, _hr_without())
    client.post("/payroll/issue-selected", data={
        "month": MONTH, "emp": ["b"], "confirm": "1"})
    assert slips["b"]["status"] == PAY.ISSUED


# ── 4. Create drafts for selected ────────────────────────────────────────────

def test_create_selected_drafts_only_the_ticked_without_a_live_slip(client):
    slips = _crew()
    _person("f", "FARHAN")
    _mark("f", "2026-09-04")
    r = client.post("/payroll/create-selected", data={
        "month": MONTH, "emp": ["a", "b", "c", "d"]})
    assert r.status_code == 302
    assert "2 draft slip(s) created, 2 skipped" in \
        r.location.replace("+", " ").replace("%28", "(").replace("%29", ")") \
                  .replace("%2C", ",")
    assert PAY.live_slip("d", MONTH)["status"] == PAY.DRAFT
    assert PAY.live_slip("c", MONTH)["status"] == PAY.DRAFT, \
        "a cancelled slip frees the month, create_draft()'s own rule"
    assert PAY.live_slip("f", MONTH) == {}, "not ticked, not drafted"
    assert slips["a"]["status"] == PAY.ISSUED


def test_create_selected_is_refused_without_payroll_edit(client):
    _crew()
    _as(client, _hr_without("payroll.edit"))
    before = _state()
    client.post("/payroll/create-selected", data={"month": MONTH,
                                                  "emp": ["d"]})
    assert _state() == before
    assert auth.ROUTE_PERMISSIONS["payroll.create_selected"] == "payroll.edit"


# ── 5. print-month ───────────────────────────────────────────────────────────

def test_print_month_is_unchanged_for_issued_slips(client):
    slips = _crew()
    html = _html(client, f"/payroll/print-month?month={MONTH}")
    with client.application.test_request_context():
        want = PAY._print_page(
            f"Payslips {PAY.month_label(MONTH)}",
            f'<div class="slip-page">{PAY.slip_sheet(slips["a"])}</div>',
            f"/payroll/?month={MONTH}")
    assert html == want
    assert '<div class="slip-mark">DRAFT</div>' not in html


def test_print_month_with_no_slip_at_all_keeps_its_old_message(client):
    html = _html(client, f"/payroll/print-month?month={MONTH}")
    assert "<p>No slip is issued for September 2026 yet.</p>" in html


def test_print_month_with_only_drafts_says_how_many(client):
    _person("b", "BHARAT")
    _person("e", "EKTA")
    _mark("b", "2026-09-01")
    _mark("e", "2026-09-01")
    PAY.create_draft("b", MONTH)
    PAY.create_draft("e", MONTH)
    html = _html(client, f"/payroll/print-month?month={MONTH}")
    assert '<div class="slip-page">' not in html
    assert "2 draft slips are waiting" in html
    assert "Print selected" in html
