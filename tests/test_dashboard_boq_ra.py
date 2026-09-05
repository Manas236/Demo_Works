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
          grandfathered=False, date="2026-08-12", leg="supply"):
    rec = {
        "id": rid, "ref": ref, "date": date, "boq_id": boq_id, "leg": leg,
        "claim_subtotal": float(claim),
        # A tax-INCLUSIVE figure deliberately present and deliberately wrong to
        # sum: any panel that reaches for it instead of `claim_subtotal` will
        # produce a number no assertion here matches. Gap 31, made testable.
        "grand_total": float(claim) * 1.18,
        "net_payable": float(claim), "claims": [], "status": status,
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
