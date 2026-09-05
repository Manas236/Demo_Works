"""
The dashboard's BOQ/RA visual cues — the four items of 3 September 2026.

⚠ **This file exists to hold the EQUIVALENCES, not only the output.**
`dashboard.py` may not import `boq.py`, `ra.py` or `approval.py` — it is
imported BY the first two for `BASE_STYLES` and `_nav()`, so an import back is a
cycle at boot (ABOUT.md §2, `tests/test_import_directions.py`). It therefore
matches status strings literally, exactly as `_metrics()` already does for
`purchase.PO_STATUSES`. A comment asserting that two functions agree is worth
nothing the day one of them is renamed; the sweeps below fail instead, which is
the shape `tests/test_approval_b7.py` uses to hold `print_exempt_states` against
`ra.status_of()`.

Every money assertion here is **tax-exclusive** — `claim_subtotal` against
`subtotal`, never `grand_total`. ABOUT.md §7 gap 31 is the display bug that
comes from mixing the two, and it cost a real over-claim investigation on
3 September 2026.
"""

import approval
import dashboard
import ra as RA
from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

def _boq(bid, ref, subtotal, project_id="", supersedes="", date="2026-08-10"):
    STORE["boqs"][bid] = {
        "id": bid, "ref": ref, "date": date, "subtotal": float(subtotal),
        "project_id": project_id, "supersedes": supersedes, "rev_no": 0,
        "project_name": f"Project for {ref}", "account_name": "Main Contractor",
        "line_items": [], "sections": [],
    }
    return STORE["boqs"][bid]


def _bill(rid, ref, boq_id, claim, status="issued", approval_status=None,
          grandfathered=False, date="2026-08-12", leg="supply", deduction=None):
    """
    One RA bill carrying THREE money fields that are all different on purpose.

    ⚠ **`net_payable` deliberately differs from `claim_subtotal`.** It defaults
    to a 10% retention withheld, because a fixture where the two are equal
    cannot tell them apart — and a mutation swapping one for the other passed
    silently against the first version of this file until the mutation run
    caught it. `grand_total` is the tax-inclusive figure gap 31 is about, and no
    assertion in this file may ever match it.
    """
    ded = float(claim) * 0.10 if deduction is None else float(deduction)
    rec = {
        "id": rid, "ref": ref, "date": date, "boq_id": boq_id, "leg": leg,
        "claim_subtotal": float(claim),
        # A tax-INCLUSIVE figure deliberately present and deliberately wrong to
        # sum: any panel that reaches for it instead of `claim_subtotal` will
        # produce a number no assertion here matches. Gap 31, made testable.
        "grand_total": float(claim) * 1.18,
        "deduction_total": ded,
        "net_payable": float(claim) - ded,
        "claims": [], "status": status,
        "project_name": "Site A", "account_name": "Main Contractor",
    }
    if approval_status is not None:
        rec["approval_status"] = approval_status
    if grandfathered:
        rec[approval.GRANDFATHER_FIELD] = True
    STORE["ra_bills"][rid] = rec
    return rec


# ── Item 1: the two counts ──────────────────────────────────────────────────

def test_open_boqs_counts_only_the_tip_of_each_revision_chain(client):
    STORE["boqs"].clear()
    _boq("b1", "SF/BOQ/26-27/0001", 100.0)
    _boq("b2", "SF/BOQ/26-27/0002", 200.0, supersedes="b1")
    _boq("b3", "SF/BOQ/26-27/0003", 300.0)

    m = dashboard._boq_ra()
    assert m["boq_open_count"] == 2, "b1 is superseded by b2 and is not open"
    assert m["boq_revised_count"] == 1


def test_open_boq_definition_agrees_with_boq_superseded_ids(client):
    """The mirror of `boq.superseded_ids()`, asserted rather than commented."""
    import boq as BQ

    STORE["boqs"].clear()
    _boq("b1", "R1", 10.0)
    _boq("b2", "R2", 20.0, supersedes="b1")
    _boq("b3", "R3", 30.0, supersedes="b2")

    assert dashboard._superseded_boq_ids() == BQ.superseded_ids()
    for bid in STORE["boqs"]:
        assert dashboard._boq_is_open(bid, dashboard._superseded_boq_ids()) == (
            bid not in BQ.superseded_ids())


def test_a_grandfathered_bill_is_never_counted_as_pending(client):
    """
    ⚠ The load-bearing exclusion. Every RA bill on the live database is
    grandfathered, so without this the tile reads "7 awaiting approval" forever
    when nobody can action a single one of them.
    """
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0, grandfathered=True)
    _bill("r2", "RA2", "b1", 100.0, grandfathered=True, approval_status="pending")

    assert dashboard._boq_ra()["ra_pending_count"] == 0


def test_a_bill_with_no_approval_status_is_pending_like_approval_status_of(client):
    STORE["ra_bills"].clear()
    b = _bill("r1", "RA1", "b1", 100.0)
    assert approval.status_of(b) == approval.PENDING
    assert dashboard._ra_awaits_approval(b) is True
    assert dashboard._boq_ra()["ra_pending_count"] == 1


def test_approved_and_rejected_bills_are_not_pending(client):
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0, approval_status="approved")
    _bill("r2", "RA2", "b1", 100.0, approval_status="rejected")
    _bill("r3", "RA3", "b1", 100.0, approval_status="pending")

    assert dashboard._boq_ra()["ra_pending_count"] == 1


def test_a_cancelled_bill_is_not_waiting_on_anybody(client):
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0, status="cancelled", approval_status="pending")
    assert dashboard._boq_ra()["ra_pending_count"] == 0


def test_a_draft_bill_still_climbs_the_ladder_and_is_counted(client):
    """A draft counts, exactly as `claimed_by_line()` counts its quantity."""
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0, status="draft", approval_status="pending")
    assert dashboard._boq_ra()["ra_pending_count"] == 1


def test_the_pending_predicate_agrees_with_approval_status_of_on_every_status(client):
    """
    Sweep `approval.STATUSES` plus the absent case. The dashboard's literal
    reading must agree with the canonical helper on every value it can hold,
    once the two axes it handles separately — grandfathered and cancelled — are
    held constant.
    """
    for status in list(approval.STATUSES) + [None, "", "  APPROVED  ", "nonsense"]:
        STORE["ra_bills"].clear()
        b = _bill("r1", "RA1", "b1", 100.0, approval_status=status)
        canonical = approval.status_of(b) == approval.PENDING
        assert dashboard._ra_awaits_approval(b) is canonical, (
            f"disagreed with approval.status_of() on {status!r}")


def test_the_cancelled_predicate_agrees_with_ra_is_cancelled_on_every_status(client):
    """Sweep `ra.STATUSES` plus the unrecognised case, which reads as issued."""
    for status in list(RA.STATUSES) + [None, "", "submitted", "certified", "NONSENSE"]:
        b = {"status": status}
        assert dashboard._ra_is_cancelled(b) == RA.is_cancelled(b), (
            f"disagreed with ra.is_cancelled() on {status!r}")


# ── Item 1: what actually reaches the page ──────────────────────────────────

def test_the_band_renders_both_tiles_on_the_dashboard(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0)
    _bill("r1", "RA1", "b1", 100.0, approval_status="pending")

    html = client.get("/").get_data(as_text=True)
    assert "Projects &amp; site billing" in html
    assert "Open BOQs" in html
    assert "RAs pending approval" in html


def test_the_tiles_reuse_the_existing_kpi_classes(client):
    """
    Same tile shape and colours as the quotation band — no new visual style.
    `.kpi`, `.k-lbl`, `.k-val`, `.k-sub` and the two colour variants are the
    ones `_insight_html()` already draws.
    """
    html = client.get("/").get_data(as_text=True)
    band = html[html.find("Projects &amp; site billing"):]
    band = band[:band.find("</div>\n        </div>")]
    assert 'class="panel kpi k-rate"' in band
    assert 'class="panel kpi k-hot"' in band
    assert 'class="k-lbl"' in band and 'class="k-val"' in band


# ── Item 2: claimed value, tax-exclusive, against its denominator ───────────

def test_claimed_value_sums_claim_subtotal_and_never_grand_total(client):
    """
    ⚠ ABOUT.md §7 gap 31, made a failing test rather than a comment. The
    fixture's `grand_total` is `claim_subtotal * 1.18`, so a panel reaching for
    the tax-inclusive field produces 118 rather than 100 and this fails.
    """
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 60.0)
    _bill("r2", "RA2", "b1", 40.0)

    assert dashboard._boq_ra()["ra_claimed_value"] == 100.0


def test_a_cancelled_bill_is_excluded_from_the_claimed_total(client):
    """`claimed_by_line()`'s rule in money: a withdrawn claim claims nothing."""
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0)
    _bill("r2", "RA2", "b1", 500.0, status="cancelled")

    assert dashboard._boq_ra()["ra_claimed_value"] == 100.0


def test_a_draft_bill_is_included_in_the_claimed_total(client):
    """
    The other half of `claimed_by_line()`'s rule, and the half that separates
    it from `claims_by_line_id()`. A draft's claim is committed on save.
    """
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0, status="draft")
    assert dashboard._boq_ra()["ra_claimed_value"] == 100.0


def test_an_unrecognised_status_counts_rather_than_vanishing(client):
    """
    `ra.status_of()` reads anything unrecognised as `issued`, so a hand-edited
    record keeps its money in the total instead of silently dropping out.
    """
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 100.0, status="submitted")
    assert dashboard._boq_ra()["ra_claimed_value"] == 100.0


def test_the_denominator_counts_only_open_schedules(client):
    STORE["boqs"].clear()
    _boq("b1", "R1", 1000.0)
    _boq("b2", "R2", 4000.0, supersedes="b1")

    m = dashboard._boq_ra()
    assert m["boq_open_value"] == 4000.0, "b1 was replaced by b2, not added to"


def test_merged_ra_documents_are_not_summed_into_the_claimed_total(client):
    """
    A merged document is built from two bills that are already in the sum.
    Adding its own `claim_subtotal` would double-count every merged claim —
    the money counterpart of the warning `claimed_by_line()` enforces on
    quantity.
    """
    STORE["ra_bills"].clear()
    STORE["merged_ras"].clear()
    _bill("r1", "RA1", "b1", 100.0, leg="supply")
    _bill("r2", "RA2", "b1", 50.0, leg="installation")
    STORE["merged_ras"]["m1"] = {
        "id": "m1", "ref": "SF/RI/26-27/0001", "boq_id": "b1",
        "supply_ra_id": "r1", "installation_ra_id": "r2",
        "claim_subtotal": 150.0, "status": "issued",
    }

    assert dashboard._boq_ra()["ra_claimed_value"] == 150.0, (
        "the two legs, counted once — not 300")


def test_the_claimed_tile_shows_its_denominator(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0)
    _bill("r1", "RA1", "b1", 250.0)

    html = client.get("/").get_data(as_text=True)
    assert "Claimed to date" in html
    assert "approved" in html and "of open schedules" in html
    assert "25% of open schedules" in html


def test_no_percentage_is_drawn_when_there_is_no_open_schedule(client):
    """A percentage of nothing is not 0% and must not be rendered as one."""
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 250.0)

    html = client.get("/").get_data(as_text=True)
    assert "no open schedule to claim against" in html
    assert "% of open schedules" not in html


def test_the_gap_31_reconciliation_reproduces_on_the_clients_own_figures(client):
    """
    ⚠ The real case from ABOUT.md §7 gap 31, as a regression test.

    BOQ SF/BOQ/26-27/0006 approved ₹9,585; two bills claimed ₹750 and ₹8,835,
    one leg each, at exactly their approved quantities. Read tax-INCLUSIVE the
    chips are ₹885 + ₹10,425 = ₹11,310 and the schedule looks ₹1,725 over.
    Read tax-exclusive it reconciles to the rupee at 100%.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b6", "SF/BOQ/26-27/0006", 9585.0)
    _bill("r6", "SF/RA/26-27/0006", "b6", 750.0, leg="installation")
    _bill("r7", "SF/RA/26-27/0007", "b6", 8835.0, leg="supply")

    m = dashboard._boq_ra()
    assert m["ra_claimed_value"] == 9585.0
    assert m["boq_open_value"] == 9585.0
    assert m["ra_claimed_value"] / m["boq_open_value"] == 1.0, "100%, not 118%"


def test_claimed_value_is_the_claim_and_not_the_net_of_deductions(client):
    """
    ⚠ `net_payable` is also tax-exclusive, and is still the wrong field.

    It is `claim_subtotal - deduction_total`. Retention withheld against a
    claim does not reduce what was CLAIMED against the schedule — the claim
    stands at its full value and the money is held back from it. A panel
    summing `net_payable` under-states the claimed share of every schedule with
    a retention on it, which is most of them.

    This test exists because a mutation swapping the two fields passed against
    the first version of this file: every fixture had `net_payable` equal to
    `claim_subtotal`, so nothing could tell them apart.
    """
    STORE["ra_bills"].clear()
    _bill("r1", "RA1", "b1", 1000.0, deduction=100.0)

    bill = STORE["ra_bills"]["r1"]
    assert bill["net_payable"] == 900.0, "the fixture must distinguish the two"
    assert dashboard._boq_ra()["ra_claimed_value"] == 1000.0, (
        "the claim, not the claim net of retention")


# ── Item 3: the activity feed, and the permission filter on it ──────────────

def _role(slug, *permissions):
    """A throwaway role holding exactly the permissions named, and a user on it."""
    import auth

    auth.ensure_builtin_roles()
    auth.roles()[f"role-{slug}"] = {
        "id": f"role-{slug}", "name": slug, "builtin": False,
        "permissions": ["dashboard.view", *permissions]}
    existing = auth.find_user(f"act-{slug}")
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(f"act-{slug}", slug, f"pw-act-{slug}-12345",
                            [f"role-{slug}"], created_by="activity-test")


def _as(client, user):
    import auth

    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


def _seed_activity():
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b1", "SF/BOQ/26-27/0001", 5000.0, date="2026-08-01")
    _bill("r1", "SF/RA/26-27/0001", "b1", 1200.0, date="2026-08-20")


def test_the_feed_interleaves_boqs_and_ra_bills_newest_first(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b1", "SF/BOQ/26-27/0001", 100.0, date="2026-08-01")
    _boq("b2", "SF/BOQ/26-27/0002", 200.0, date="2026-08-15")
    _bill("r1", "SF/RA/26-27/0001", "b1", 50.0, date="2026-08-10")
    _bill("r2", "SF/RA/26-27/0002", "b1", 60.0, date="2026-08-20")

    refs = [r["ref"] for r in dashboard._boq_ra()["activity"]]
    assert refs == ["SF/RA/26-27/0002", "SF/BOQ/26-27/0002",
                    "SF/RA/26-27/0001", "SF/BOQ/26-27/0001"]


def test_the_feed_orders_by_the_documents_own_date_not_insertion_order(client):
    """
    There is no `created_at` on either record — see `_activity_rows()`. The key
    is `(date, ref)` descending, which is `projectview.py`'s existing key for
    the same collections.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b_old", "SF/BOQ/26-27/0009", 100.0, date="2026-01-01")
    _boq("b_new", "SF/BOQ/26-27/0001", 100.0, date="2026-12-01")

    refs = [r["ref"] for r in dashboard._boq_ra()["activity"]]
    assert refs[0] == "SF/BOQ/26-27/0001", "the later date leads, not the later insert"


def test_the_feed_carries_tax_exclusive_amounts(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _bill("r1", "SF/RA/26-27/0001", "b1", 1000.0)

    row = dashboard._boq_ra()["activity"][0]
    assert row["amount"] == 1000.0, "claim_subtotal, never grand_total (1180)"


def test_a_cancelled_bill_stays_in_the_feed_and_is_labelled(client):
    """
    The feed answers "what moved", and a withdrawn claim moved. It is out of
    the money totals — where its claim genuinely is nothing — and in the record
    of what happened.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _bill("r1", "SF/RA/26-27/0001", "b1", 100.0, status="cancelled")

    rows = dashboard._boq_ra()["activity"]
    assert len(rows) == 1
    assert "cancelled" in rows[0]["note"]


def test_the_feed_is_capped_and_says_how_many_it_left_out(client):
    """
    ⚠ Both halves, and the count of DRAWN ROWS is the half that matters. An
    earlier version asserted only the "+ 3 more" label — which is computed from
    `len(rows)` and goes on rendering correctly even when the cap on the loop is
    removed, so removing the cap passed. The row count is what pins it.
    """
    import re

    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    for i in range(dashboard.ACTIVITY_LIMIT + 3):
        _boq(f"b{i}", f"SF/BOQ/26-27/{i:04d}", 100.0, date=f"2026-08-{i + 1:02d}")

    html = client.get("/").get_data(as_text=True)
    feed = html[html.find("Recent BOQ &amp; RA activity"):]
    feed = feed[:feed.find("</section>")]
    drawn = re.findall(r'href="/boq/view/b\d+"', feed)

    assert len(drawn) == dashboard.ACTIVITY_LIMIT, (
        f"{len(drawn)} rows drawn, cap is {dashboard.ACTIVITY_LIMIT}")
    assert "+ 3 more" in html


def test_the_feed_renders_a_link_to_each_document(client):
    _seed_activity()
    html = client.get("/").get_data(as_text=True)
    assert "Recent BOQ &amp; RA activity" in html
    assert "/boq/view/b1" in html
    assert "/ra/view/r1" in html


# ── The judgement call, proved non-vacuous by role ──────────────────────────

def test_a_user_without_ra_view_is_not_shown_ra_bills_in_the_feed(client):
    """
    ⚠ **THE ITEM 3 JUDGEMENT CALL, asserted.** This panel names a document, its
    project and its amount — a materially bigger disclosure than the aggregate
    counts above it, which ABOUT.md §7 gap 27 deliberately leaves unfiltered.
    A BOQ-only role sees schedules and no claims.
    """
    _seed_activity()
    _as(client, _role("boqonly", "boq.view"))

    html = client.get("/").get_data(as_text=True)
    assert "SF/BOQ/26-27/0001" in html, "a schedule it may open was hidden"
    assert "SF/RA/26-27/0001" not in html, "a bill it may NOT open was named"
    assert "/ra/view/r1" not in html


def test_a_user_without_boq_view_is_not_shown_boqs_in_the_feed(client):
    """The mirror image — the two kinds filter independently."""
    _seed_activity()
    _as(client, _role("raonly", "ra.view"))

    html = client.get("/").get_data(as_text=True)
    assert "SF/RA/26-27/0001" in html, "a bill it may open was hidden"
    assert "SF/BOQ/26-27/0001" not in html, "a schedule it may NOT open was named"
    assert "/boq/view/b1" not in html


def test_a_user_reaching_neither_register_gets_no_activity_panel_at_all(client):
    _seed_activity()
    _as(client, _role("neither"))

    html = client.get("/").get_data(as_text=True)
    assert "Recent BOQ &amp; RA activity" not in html
    assert "SF/BOQ/26-27/0001" not in html
    assert "SF/RA/26-27/0001" not in html


def test_the_feed_filter_agrees_with_the_gate_that_would_refuse_the_link(client):
    """
    ⚠ Every row the feed draws must be a row whose own link actually opens.

    This is the property the filter exists for, and it is asserted end-to-end
    rather than by inspecting `can_reach()`: each document link rendered on the
    page is requested, and none of them may refuse. ABOUT.md §7 gap 24 is why
    the check is endpoint-level — this application has no object-level gate on
    `/boq/view/<id>` or `/ra/view/<id>` for the feed to consult.
    """
    import re

    _seed_activity()
    _as(client, _role("boqonly2", "boq.view"))

    html = client.get("/").get_data(as_text=True)
    links = set(re.findall(r'href="(/(?:boq|ra)/view/[^"]+)"', html))
    assert links, "the feed drew no document links at all — test is vacuous"
    for href in links:
        assert client.get(href).status_code == 200, f"{href} was drawn but refuses"


# ── Item 4: per-project progress ────────────────────────────────────────────

def _project(pid, name):
    STORE.setdefault("projects", {})[pid] = {"id": pid, "name": name}


def _by_name(rows):
    return {r["name"]: r for r in rows}


def test_progress_is_claimed_over_approved_both_tax_exclusive(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _bill("r1", "SF/RA/26-27/0001", "b1", 250.0)

    row = _by_name(dashboard._boq_ra()["proj_progress"])["Tower B"]
    assert row["approved"] == 1000.0
    assert row["claimed"] == 250.0
    assert row["pct"] == 25.0, "118% would mean grand_total leaked in"


def test_the_approved_side_counts_open_schedules_only(client):
    """A superseded revision was replaced, not added to."""
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _boq("b2", "SF/BOQ/26-27/0002", 3000.0, project_id="p1", supersedes="b1")

    row = _by_name(dashboard._boq_ra()["proj_progress"])["Tower B"]
    assert row["approved"] == 3000.0, "the chain was summed instead of its tip"


def test_the_claimed_side_counts_bills_against_superseded_revisions_too(client):
    """
    The asymmetry, and it is deliberate. A bill names the specific revision it
    was measured against; an old claim against rev 0 is still money claimed on
    that project after rev 1 supersedes it. Dropping it under-counts the
    numerator in the same project the rule above protects the denominator of.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _boq("b2", "SF/BOQ/26-27/0002", 2000.0, project_id="p1", supersedes="b1")
    _bill("r1", "SF/RA/26-27/0001", "b1", 300.0)   # against the OLD revision
    _bill("r2", "SF/RA/26-27/0002", "b2", 200.0)

    row = _by_name(dashboard._boq_ra()["proj_progress"])["Tower B"]
    assert row["claimed"] == 500.0, "the claim against rev 0 was dropped"
    assert row["approved"] == 2000.0


def test_a_cancelled_bill_does_not_count_toward_a_projects_claimed(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _bill("r1", "SF/RA/26-27/0001", "b1", 100.0)
    _bill("r2", "SF/RA/26-27/0002", "b1", 900.0, status="cancelled")

    row = _by_name(dashboard._boq_ra()["proj_progress"])["Tower B"]
    assert row["claimed"] == 100.0


def test_unassigned_boqs_get_their_own_row_and_are_not_dropped(client):
    """
    Not hypothetical. On the live database on 5 September 2026 three of eight
    schedules carry no `project_id`, one of them worth Rs 91.9 lakh - more
    approved value than every assigned project on the box put together.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _boq("b2", "SF/BOQ/26-27/0002", 9000.0, project_id="")

    rows = _by_name(dashboard._boq_ra()["proj_progress"])
    assert "Unassigned" in rows, "a schedule with no project vanished"
    assert rows["Unassigned"]["approved"] == 9000.0


def test_the_unassigned_row_does_not_link_anywhere(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _boq("b1", "SF/BOQ/26-27/0001", 9000.0, project_id="")

    html = client.get("/").get_data(as_text=True)
    panel = html[html.find("Claimed against approved"):]
    panel = panel[:panel.find("</section>")]
    assert "Unassigned" in panel
    assert "/projects/view/" not in panel, "Unassigned was linked as a project"


def test_a_bill_whose_schedule_is_gone_lands_in_unassigned_not_nowhere(client):
    """Real money must not silently leave the panel."""
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _bill("r1", "SF/RA/26-27/0001", "deleted-boq", 700.0)

    rows = _by_name(dashboard._boq_ra()["proj_progress"])
    assert rows["Unassigned"]["claimed"] == 700.0


def test_the_panel_total_reconciles_with_the_claimed_tile(client):
    """
    The two items must agree. Every non-cancelled bill lands in exactly one
    row, so the rows sum to `ra_claimed_value` - including the bills whose
    schedule is missing.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _boq("b2", "SF/BOQ/26-27/0002", 500.0, project_id="")
    _bill("r1", "SF/RA/26-27/0001", "b1", 300.0)
    _bill("r2", "SF/RA/26-27/0002", "b2", 200.0)
    _bill("r3", "SF/RA/26-27/0003", "gone", 50.0)
    _bill("r4", "SF/RA/26-27/0004", "b1", 999.0, status="cancelled")

    m = dashboard._boq_ra()
    assert sum(r["claimed"] for r in m["proj_progress"]) == m["ra_claimed_value"]


def test_no_bar_is_drawn_for_a_project_with_nothing_approved(client):
    """
    A project with claims against a schedule that is gone has claimed against
    nothing. `pct` is None, not 0.0 - `projectview._total_of()`'s rule.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _bill("r1", "SF/RA/26-27/0001", "gone", 700.0)

    rows = _by_name(dashboard._boq_ra()["proj_progress"])
    assert rows["Unassigned"]["pct"] is None

    html = client.get("/").get_data(as_text=True)
    assert "no open schedule" in html


def test_an_over_claim_shows_its_real_figure_with_the_bar_clamped(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 100.0, project_id="p1")
    _bill("r1", "SF/RA/26-27/0001", "b1", 150.0)

    row = _by_name(dashboard._boq_ra()["proj_progress"])["Tower B"]
    assert row["pct"] == 150.0

    html = client.get("/").get_data(as_text=True)
    assert "150% claimed" in html, "the real figure must stay readable"
    assert "width:150.0%" not in html, "the bar must not run off its track"


def test_the_project_list_is_capped_with_a_link_to_the_rest(client):
    import re

    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    for i in range(dashboard.PROGRESS_LIMIT + 2):
        _project(f"p{i}", f"Project {i}")
        _boq(f"b{i}", f"SF/BOQ/26-27/{i:04d}", 100.0, project_id=f"p{i}",
             date=f"2026-08-{i + 1:02d}")

    html = client.get("/").get_data(as_text=True)
    panel = html[html.find("Claimed against approved"):]
    panel = panel[:panel.find("</section>")]
    assert len(re.findall(r'class="pp-row"', panel)) == dashboard.PROGRESS_LIMIT
    assert "+ 2 more" in panel
    assert "all projects" in panel


def test_the_progress_panel_needs_both_registers(client):
    """A ratio half of which the reader cannot see is not a figure to show."""
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p1", "Tower B")
    _boq("b1", "SF/BOQ/26-27/0001", 1000.0, project_id="p1")
    _bill("r1", "SF/RA/26-27/0001", "b1", 250.0)

    _as(client, _role("boqonly3", "boq.view", "project.view"))
    html = client.get("/").get_data(as_text=True)
    assert "Claimed against approved" not in html


def test_the_gap_31_project_reconciles_at_one_hundred_percent(client):
    """
    The live case, end to end. BOQ SF/BOQ/26-27/0006 approved Rs 9,585 and its
    two bills claimed Rs 750 + Rs 8,835. The bar reads 100%, not 118%.
    """
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    _project("p6", "Work2")
    _boq("b6", "SF/BOQ/26-27/0006", 9585.0, project_id="p6")
    _bill("r6", "SF/RA/26-27/0006", "b6", 750.0, leg="installation")
    _bill("r7", "SF/RA/26-27/0007", "b6", 8835.0, leg="supply")

    row = _by_name(dashboard._boq_ra()["proj_progress"])["Work2"]
    assert row["pct"] == 100.0

    html = client.get("/").get_data(as_text=True)
    assert "100% claimed" in html
