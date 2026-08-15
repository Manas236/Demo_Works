"""
BOQ revisions are reachable, and the over-claim guard actually guards them.

The record has carried `supersedes` since the shape was written, and the whole
chain was built out behind it — `ra.revision_chain()`, `ra.claimed_by_line()`
summing across the chain, `boq.revision_blockers()`. **Nothing called any of
it.** No form wrote a non-empty `supersedes`, so every chain was one link long,
every revision restarted every line's claimed quantity at zero, and the
over-claim block passed everything on precisely the schedules that had been
revised.

That is the failure this file exists to make impossible, and it was *silent*:
no error, no warning, a guard quietly answering yes.

    THE ASSERTION THAT MATTERS MOST is
    `test_a_revision_number_above_zero_without_a_predecessor_is_refused`.
    Everything else here checks that a link works once it is made; that one
    checks you cannot make the broken state at all.

Scope note: `revision_blockers()`' own logic is untouched — it was designed and
correct, just uncalled. What is new is the call site, the selector that feeds it
and the refusals around it.
"""

import json

import pytest

import boq as BQ
import demo_data as DD
import ra
from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

def _line(lid, item_no="1", qty=100.0, s_rate=100.0):
    return {"line_id": lid, "item_no": item_no, "parent_item_no": "",
            "section": "A", "is_header": False, "description": f"Line {item_no}",
            "remark": "", "unit": "Mtrs", "area_qty": {}, "total_qty": qty,
            "supply_base_rate": s_rate, "supply_escalation_pct": 0.0,
            "supply_rate": s_rate, "supply_amount": s_rate * qty,
            "supply_hsn": "73063090", "supply_gst_rate": 18.0,
            "install_base_rate": 50.0, "install_escalation_pct": 0.0,
            "install_rate": 50.0, "install_amount": 50.0 * qty,
            "install_sac": "995462", "install_gst_rate": 18.0}


def _mkboq(bid, rev=0, supersedes="", lines=None,
           project="Sify Bangalore", account="Prudent Teqtis Pvt Ltd"):
    STORE["boqs"][bid] = {
        "id": bid, "ref": f"SF/BOQ/26-27/{rev + 1:04d}", "fy": "26-27",
        "date": "2026-08-11", "rev_no": rev, "supersedes": supersedes,
        "project_name": project, "site_location": "Bangalore",
        "account_name": account, "contact_person": "", "to": "",
        "bill_gstin": "", "ship_same": True, "rate_basis_label": "Mohali Rates",
        "sections": [{"code": "A", "title": "Sprinkler", "areas": []}],
        "line_items": lines if lines is not None else [_line("aaaaaaaaaaaa")],
        "supply_subtotal": 0.0, "install_subtotal": 0.0, "subtotal": 0.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }
    return bid


def _mkbill(rid, boq_id, ra_no, claims, leg="supply"):
    subtotal, drows, dtotal, net = ra.bill_totals(claims, [])
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-06", "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "ra_no": ra_no, "leg": leg, "claims": claims,
        "claim_subtotal": subtotal, "deductions": drows,
        "deduction_total": dtotal, "net_payable": net,
        "status": "draft", "issued_on": "", "cancelled_on": "",
        "cancel_reason": "", "notes": "",
    }
    return rid


@pytest.fixture()
def clean(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    yield
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


def _form(rev_no="0", supersedes="", lines=None, project="Sify Bangalore",
          account="Prudent Teqtis Pvt Ltd", **over):
    """A minimal but complete POST body for /boq/create."""
    rows = lines if lines is not None else [
        {"line_id": "aaaaaaaaaaaa", "item_no": "1", "parent_item_no": "",
         "section": "A", "is_header": False, "description": "Line 1",
         "remark": "", "unit": "Mtrs", "area_qty": {}, "total_qty": "100",
         "supply_base_rate": "100", "supply_escalation_pct": "0",
         "supply_rate": "100", "supply_hsn": "73063090", "supply_gst_rate": "18",
         "install_base_rate": "50", "install_escalation_pct": "0",
         "install_rate": "50", "install_sac": "995462", "install_gst_rate": "18"}]
    data = {
        "date": "2026-08-12", "rev_no": rev_no, "supersedes": supersedes,
        "project_name": project, "account_name": account,
        "site_location": "Bangalore", "rate_basis_label": "Mohali Rates",
        "boq_json": json.dumps({
            "sections": [{"code": "A", "title": "Sprinkler", "areas": []}],
            "lines": rows}),
    }
    data.update(over)
    return data


# ═══ 1. The state you must not be able to create ═══════════════════════════

def test_a_revision_number_above_zero_without_a_predecessor_is_refused(client, clean):
    """
    **The assertion this whole commit is for.**

    Revision 1 with nothing to supersede is the silent failure: the record says
    it replaces something, the chain is one link long, and every line's claimed
    quantity restarts at zero. It now refuses, visibly, and says why.
    """
    r = client.post("/boq/create", data=_form(rev_no="2", supersedes=""))

    assert r.status_code == 200, "a refusal re-renders the form, never redirects"
    assert STORE["boqs"] == {}, "nothing may be written on a refused POST"

    html = r.get_data(as_text=True)
    assert "marked Revision 2 but no BOQ was chosen" in html
    assert "restarts every line" in html.replace("&#39;", "'")


def test_revision_zero_with_no_predecessor_is_the_normal_case(client, clean):
    """The control: an original schedule still saves with no link at all."""
    r = client.post("/boq/create", data=_form(rev_no="0", supersedes=""))
    assert r.status_code == 302
    assert len(STORE["boqs"]) == 1
    assert next(iter(STORE["boqs"].values()))["supersedes"] == ""


def test_a_predecessor_from_another_project_is_refused(client, clean):
    _mkboq("other", rev=0, project="Different Tower", account="Someone Else Ltd")

    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="other"))

    assert r.status_code == 200
    assert "other" in STORE["boqs"] and len(STORE["boqs"]) == 1
    assert "is for a different project or customer" in r.get_data(as_text=True)


def test_an_already_revised_predecessor_is_refused(client, clean):
    """Two revisions of one schedule fork the chain; nothing can unpick that."""
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="rev0"))

    assert r.status_code == 200
    assert len(STORE["boqs"]) == 2
    assert "has already been revised" in r.get_data(as_text=True)


def test_a_predecessor_that_no_longer_exists_is_refused(client, clean):
    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="ghost"))
    assert r.status_code == 200
    assert STORE["boqs"] == {}
    assert "no longer exists" in r.get_data(as_text=True)


# ═══ 2. The link works, and the guard sees through it ══════════════════════

def test_a_revision_saves_with_the_link_written(client, clean):
    _mkboq("rev0", rev=0)

    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="rev0"))
    assert r.status_code == 302

    new = next(b for b in STORE["boqs"].values() if b["id"] != "rev0")
    assert new["supersedes"] == "rev0"
    assert new["rev_no"] == 1
    assert ra.revision_chain(new["id"]) == ["rev0", new["id"]]


def test_a_claim_on_the_predecessor_counts_against_the_successors_guard(client, clean):
    """
    The point of the whole exercise.

    30 of 100 claimed under rev 0. After revising, the successor's guard must
    still see those 30 — claiming the remaining 70 is fine and claiming 71 is
    not. Without the link the chain is one record long, `claimed_by_line()`
    returns nothing, and all 100 are claimable a second time.
    """
    lid = "aaaaaaaaaaaa"
    _mkboq("rev0", rev=0)
    _mkbill("ra1", "rev0", 1,
            [ra.build_claim(_line(lid), 30, 100.0, 0.0, 100.0, leg="supply")])

    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="rev0"))
    assert r.status_code == 302
    rev1 = next(b["id"] for b in STORE["boqs"].values() if b["id"] != "rev0")

    # The chain carries the earlier claim forward.
    assert ra.claimed_by_line(rev1) == {(lid, "supply"): 30.0}

    # 70 exactly exhausts the line…
    ok = client.post(f"/ra/create?boq={rev1}&leg=supply", data={
        "date": "2026-08-12",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "70", "rate": "100"}]})})
    assert ok.status_code == 302, ok.data[:1500]

    # …and one more unit is refused, by the guard, across the revision.
    over = client.post(f"/ra/create?boq={rev1}&leg=supply", data={
        "date": "2026-08-12",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "1", "rate": "100"}]})})
    assert over.status_code == 200
    assert "already claimed on earlier RA bills" in over.get_data(as_text=True)


def test_without_the_link_the_guard_would_have_passed_it(client, clean):
    """
    The regression, stated directly.

    Same two schedules, same claim, `supersedes` left empty — which is every
    revision this app could produce before this commit. The successor's guard
    sees nothing and the same 100 units are claimable all over again.
    """
    lid = "aaaaaaaaaaaa"
    _mkboq("rev0", rev=0)
    _mkbill("ra1", "rev0", 1,
            [ra.build_claim(_line(lid), 30, 100.0, 0.0, 100.0, leg="supply")])
    _mkboq("orphan", rev=0, supersedes="")          # unlinked, as before

    assert ra.claimed_by_line("orphan") == {}
    assert ra.claimed_by_line("rev0") == {(lid, "supply"): 30.0}


def test_next_ra_no_does_not_restart_across_a_revision(client, clean):
    lid = "aaaaaaaaaaaa"
    _mkboq("rev0", rev=0)
    _mkbill("ra1", "rev0", 1,
            [ra.build_claim(_line(lid), 10, 100.0, 0.0, 100.0, leg="supply")])

    client.post("/boq/create", data=_form(rev_no="1", supersedes="rev0"))
    rev1 = next(b["id"] for b in STORE["boqs"].values() if b["id"] != "rev0")

    assert ra.next_ra_no(rev1) == 2


# ═══ 3. Blockers reach the form ════════════════════════════════════════════

def test_a_revision_dropping_a_claimed_line_is_refused_and_names_it(client, clean):
    """
    `revision_blockers()` finally has a caller. Its reasons reach the page.
    """
    kept, dropped = "aaaaaaaaaaaa", "bbbbbbbbbbbb"
    _mkboq("rev0", rev=0, lines=[_line(kept, "1"), _line(dropped, "17")])
    _mkbill("ra1", "rev0", 1,
            [ra.build_claim(_line(dropped, "17"), 5, 100.0, 0.0, 100.0, leg="supply")])

    # The revision posts only the surviving line.
    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="rev0"))

    assert r.status_code == 200
    assert len(STORE["boqs"]) == 1, "the refused revision was not written"

    html = r.get_data(as_text=True)
    assert "cannot be removed by this revision" in html
    assert "Item 17 (section A) cannot be removed" in html
    assert "claimed on bill RA1" in html


def test_dropping_an_unclaimed_line_stays_free(client, clean):
    kept, dropped = "aaaaaaaaaaaa", "bbbbbbbbbbbb"
    _mkboq("rev0", rev=0, lines=[_line(kept, "1"), _line(dropped, "17")])

    r = client.post("/boq/create", data=_form(rev_no="1", supersedes="rev0"))
    assert r.status_code == 302


def test_the_boq_module_builds_the_same_claim_map_as_ra(client, clean):
    """
    `boq.claims_against_chain()` duplicates a slice of `ra.claims_by_line_id()`
    because boq.py may never import ra.py (ABOUT.md §2b). This is what stops the
    two drifting apart silently.
    """
    lid = "aaaaaaaaaaaa"
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")
    _mkbill("ra1", "rev0", 1,
            [ra.build_claim(_line(lid), 5, 100.0, 0.0, 100.0, leg="supply")])
    _mkbill("ra2", "rev1", 2,
            [ra.build_claim(_line(lid), 5, 100.0, 0.0, 100.0, leg="supply")])

    assert BQ.claims_against_chain("rev1") == ra.claims_by_line_id("rev1")
    assert BQ.claims_against_chain("rev1") == {lid: [1, 2]}


# ═══ 4. The selector ═══════════════════════════════════════════════════════

def test_the_create_form_offers_a_supersedes_selector(client, clean):
    _mkboq("rev0", rev=0)
    html = client.get("/boq/create").get_data(as_text=True)

    assert 'name="supersedes"' in html
    assert "None: this is an original schedule" in html
    assert "SF/BOQ/26-27/0001" in html


def test_candidates_are_restricted_to_the_same_project_and_party(client, clean):
    _mkboq("mine",  rev=0, project="Sify Bangalore", account="Prudent Teqtis Pvt Ltd")
    _mkboq("other", rev=0, project="Different Tower", account="Someone Else Ltd")

    both = BQ.revision_candidates()
    assert {bid for bid, _ in both} == {"mine", "other"}

    same = BQ.revision_candidates("Sify Bangalore", "Prudent Teqtis Pvt Ltd")
    assert [bid for bid, _ in same] == ["mine"]


def test_the_match_tolerates_case_and_spacing(client, clean):
    _mkboq("mine", rev=0, project="Sify Bangalore", account="Prudent Teqtis Pvt Ltd")

    same = BQ.revision_candidates("  sify   BANGALORE ", "prudent teqtis pvt ltd")
    assert [bid for bid, _ in same] == ["mine"]


def test_an_already_superseded_boq_is_not_offered(client, clean):
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    assert [bid for bid, _ in BQ.revision_candidates()] == ["rev1"]


def test_revise_prefills_the_form_and_preselects_the_predecessor(client, clean):
    _mkboq("rev0", rev=0)
    html = client.get("/boq/create?revise=rev0").get_data(as_text=True)

    assert 'value="rev0" selected' in html
    assert 'id="rev_no" name="rev_no" value="1"' in html
    assert "Sify Bangalore" in html
    # The line ids ride along, which is what keeps the claims matched.
    assert "aaaaaaaaaaaa" in html


def test_the_view_page_offers_revise_only_on_the_tip_of_a_chain(client, clean):
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    tip = client.get("/boq/view/rev1").get_data(as_text=True)
    assert "revise=rev1" in tip

    old = client.get("/boq/view/rev0").get_data(as_text=True)
    assert "revise=rev0" not in old
    assert "Revised by SF/BOQ/26-27/0002" in old
