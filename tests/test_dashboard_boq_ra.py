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
