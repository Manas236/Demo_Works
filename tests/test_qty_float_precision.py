"""
The over-claim and measurement ceilings, under accumulated binary-float error.

**This file records a NEGATIVE audit result, and it is a tripwire rather than a
fix.** The concern it was written to test is real in shape: quantities are
Python floats, cumulative claimed quantity is DERIVED by summing every prior
claim and never stored, and `ra.OVERCLAIM_TOLERANCE` is **0.0** — a
zero-tolerance hard block sitting on float arithmetic. A final, legitimate,
exactly-to-the-BOQ claim landing a fraction above the ceiling would be refused
on a completed job, in front of the main contractor, and would read as the
software being wrong.

**It does not happen, because the comparison was already written to stop it.**
Both ceilings normalise before they judge:

    ra.py:1216           if round(cumulative - allowed, 6) > _QTY_EPSILON:
    measurement.py:629   if round(cumulative - app_qty, 6) > _QTY_EPSILON:

with `_QTY_EPSILON = 1e-6` in both. Measured on quantities of the shape the
client's real sheets carry — one-decimal metre runs like 9.3, 1.5, 2.9 and 12,
split across five and six RA bills — the **worst residual is 7.105427357601002e-15**
against a 1e-6 epsilon: **eight orders of magnitude of headroom**, about
1.4 × 10⁸ times. ABOUT.md §7 carries the full table.

    THE ASSERTIONS THAT MATTER MOST are the two `_would_fire_naively` ones.
    They assert that a naive `cumulative > allowed` **WOULD** wrongly refuse
    these claims — which is what makes the rounding load-bearing rather than
    decorative, and what makes this file fail the day somebody "simplifies" it
    away. A negative result is only worth keeping if it is defended.

⚠ **`OVERCLAIM_TOLERANCE` is deliberately not touched by any of this.** It
encodes a business rule the client agreed to; the defence is at the comparison
site and belongs there. CLIENT_CHANGES.md §0's block of 9 September 2026 bars
raising it in terms.
"""

import pytest

import measurement as MS
import ra
from store import STORE


# ── The shapes their real sheets carry ─────────────────────────────────────
#
# Metre runs to one decimal, whole numbers, and a kilogram split — the four
# units the schedules actually use (Mtrs, Nos, Kgs., Set). Each case is
# (label, typed BOQ ceiling, the per-bill claims that sum to it).
#
# ⚠ The ceiling is TYPED, not re-summed. That is the realistic worst case and
#   the only one that can produce a residual at all: `total_qty` is a figure
#   somebody entered on the schedule, while the cumulative is an accumulation
#   of six separate float additions. Where both sides are the same accumulation
#   the residual is exactly zero and there is nothing to test.
SPLITS = [
    ("metre run 25.7 over four bills", 25.7, [9.3, 1.5, 2.9, 12.0]),
    ("metre run 48.6 over six bills", 48.6, [9.3, 1.5, 2.9, 12.0, 14.2, 8.7]),
    ("measurement.py's own 12", 12.0, [1.1, 2.2, 8.7]),
    ("700 Mtrs over six bills", 700.0, [116.6, 116.6, 116.6, 116.6, 116.6, 117.0]),
    ("1250.75 Kgs over six bills", 1250.75,
     [208.45, 208.45, 208.45, 208.45, 208.45, 208.5]),
    ("87 Nos over six bills", 87.0, [14.0, 14.0, 14.0, 14.0, 14.0, 17.0]),
    ("0.3 over three bills", 0.3, [0.1, 0.1, 0.1]),
    ("five-way .1 split of 12", 12.0, [2.4, 2.4, 2.4, 2.4, 2.4]),
]

_LID = "aaaaaaaaaaaa"


def _accumulate(parts):
    """Exactly how `claimed_by_line()` sums: one float `+=` per claim row."""
    total = 0.0
    for p in parts:
        total += p
    return total


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def clean(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["measurements"].clear()
    yield
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["measurements"].clear()


def _mkboq(bid, ceiling):
    STORE["boqs"][bid] = {
        "id": bid, "ref": "SF/BOQ/26-27/0001", "fy": "26-27",
        "date": "2026-08-12", "rev_no": 0, "supersedes": "",
        "project_id": "", "project_name": "Float Audit",
        "site_location": "", "account_name": "Prudent Teqtis Pvt Ltd",
        "contact_person": "", "to": "", "bill_gstin": "", "ship_same": True,
        "rate_basis_label": "Base Rate",
        "sections": [{"code": "A", "title": "Sprinkler", "areas": []}],
        "line_items": [{
            "line_id": _LID, "item_no": "1", "parent_item_no": "",
            "section": "A", "is_header": False, "description": "Pipe run",
            "remark": "", "unit": "Mtrs", "area_qty": {},
            "total_qty": ceiling,
            "supply_base_rate": 100.0, "supply_escalation_pct": 0.0,
            "supply_rate": 100.0, "supply_amount": 100.0 * ceiling,
            "supply_hsn": "73063090", "supply_gst_rate": 18.0,
            "install_base_rate": 50.0, "install_escalation_pct": 0.0,
            "install_rate": 50.0, "install_amount": 50.0 * ceiling,
            "install_sac": "995462", "install_gst_rate": 18.0}],
        "supply_subtotal": 0.0, "install_subtotal": 0.0, "subtotal": 0.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }
    return bid


def _mkbill(rid, boq_id, ra_no, qty, leg="supply"):
    claims = [{"line_id": _LID, "item_no": "1", "description": "Pipe run",
               "unit": "Mtrs", "qty": qty, "rate": 100.0,
               "amount": qty * 100.0, "hsn": "73063090", "gst_rate": 18.0}]
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-06", "boq_id": boq_id,
        "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0, "ra_no": ra_no,
        "leg": leg, "claims": claims, "claim_subtotal": qty * 100.0,
        "deductions": [], "deduction_total": 0.0,
        "net_payable": qty * 100.0, "status": "issued", "issued_on": "2026-08-06",
        "cancelled_on": "", "cancel_reason": "", "notes": "",
    }
    return rid


# ═══ 1. The residual itself — measured, in full precision ══════════════════

@pytest.mark.parametrize("label,ceiling,parts", SPLITS,
                         ids=[s[0] for s in SPLITS])
def test_the_residual_is_orders_of_magnitude_below_the_epsilon(
        label, ceiling, parts):
    """
    The audit's actual finding, per shape.

    Not "the residual is small" but "the residual is far enough below
    `_QTY_EPSILON` that no plausible schedule closes the gap". The margin is
    asserted at 1000×, which the worst measured case clears by five further
    orders of magnitude.
    """
    residual = abs(_accumulate(parts) - ceiling)
    assert residual < ra._QTY_EPSILON / 1000.0, (
        f"{label}: residual {residual!r} is within a thousandth of "
        f"_QTY_EPSILON ({ra._QTY_EPSILON!r}) — the headroom this audit "
        f"measured has gone and the guard is now at risk")


def test_the_worst_residual_across_every_shape_is_still_negligible():
    """One figure, so a regression across the whole set is one failure."""
    worst = max(abs(_accumulate(p) - c) for _l, c, p in SPLITS)
    assert worst < 1e-9, f"worst residual {worst!r} — re-run the audit"


# ═══ 2. The guard does not refuse a legitimate final claim ═════════════════

@pytest.mark.parametrize("label,ceiling,parts", SPLITS,
                         ids=[s[0] for s in SPLITS])
def test_a_claim_exactly_to_the_boq_is_not_refused(clean, label, ceiling, parts):
    """
    The scenario the audit was commissioned for, end to end through
    `ra.overclaims()`: every prior bill stored, the last one claiming the
    remainder, cumulative landing exactly on the schedule.
    """
    _mkboq("b1", ceiling)
    for i, q in enumerate(parts[:-1]):
        _mkbill(f"ra{i}", "b1", i + 1, q)

    breaches = ra.overclaims("b1", "supply",
                             [{"line_id": _LID, "qty": parts[-1]}])
    assert breaches == [], (
        f"{label}: the final legitimate claim was REFUSED — "
        f"{[ra.overclaim_message(v) for v in breaches]}")


def test_one_unit_past_the_ceiling_is_still_refused(clean):
    """
    The control. A guard that never fires is not a guard, and the headroom
    above must not have been bought by blunting it.
    """
    ceiling, parts = 48.6, [9.3, 1.5, 2.9, 12.0, 14.2, 8.7]
    _mkboq("b1", ceiling)
    for i, q in enumerate(parts[:-1]):
        _mkbill(f"ra{i}", "b1", i + 1, q)

    breaches = ra.overclaims("b1", "supply",
                             [{"line_id": _LID, "qty": parts[-1] + 1.0}])
    assert len(breaches) == 1 and breaches[0]["reason"] == "overclaim"


def test_a_real_overclaim_just_above_the_epsilon_is_refused(clean):
    """
    Where the line actually sits. 1e-5 over is ten times `_QTY_EPSILON` and is
    refused; the measured float residual is 7.1e-15 and is not. The guard
    discriminates between the two, which is the whole claim of this audit.
    """
    _mkboq("b1", 12.0)
    breaches = ra.overclaims("b1", "supply",
                             [{"line_id": _LID, "qty": 12.0 + 1e-5}])
    assert len(breaches) == 1, "1e-5 over the ceiling should be refused"


# ═══ 3. The rounding is LOAD-BEARING — the assertions that matter most ═════

def test_the_naive_comparison_would_wrongly_refuse_these_claims():
    """
    **The assertion this file exists for.**

    `round(cumulative - allowed, 6) > _QTY_EPSILON` is not decoration. On the
    metre-run shapes above, a bare `cumulative > allowed` refuses a claim that
    is exactly to the schedule. This test names the cases where that is true,
    so that removing the rounding fails here rather than at a site meeting.
    """
    naive_failures = [label for label, ceiling, parts in SPLITS
                      if _accumulate(parts) > ceiling]
    assert naive_failures, (
        "no shape here reproduces under a naive '>' — this test has stopped "
        "defending anything and the shapes need revisiting")
    # Measured 9 September 2026: three of the eight.
    assert "metre run 25.7 over four bills" in naive_failures
    assert "metre run 48.6 over six bills" in naive_failures
    assert "0.3 over three bills" in naive_failures


def test_the_guard_as_written_refuses_none_of_them():
    """The same eight shapes through the real comparison expression."""
    for label, ceiling, parts in SPLITS:
        cumulative = _accumulate(parts)
        allowed = ceiling * (1.0 + ra.OVERCLAIM_TOLERANCE)
        assert not (round(cumulative - allowed, 6) > ra._QTY_EPSILON), \
            f"{label} would be refused by the guard as written"


def test_the_tolerance_is_still_zero():
    """
    The business rule, pinned. This audit was explicitly barred from buying
    headroom by raising it — the defence is at the comparison site.
    """
    assert ra.OVERCLAIM_TOLERANCE == 0.0


# ═══ 4. The same class on the measurement cap ══════════════════════════════

@pytest.mark.parametrize("label,ceiling,parts", SPLITS,
                         ids=[s[0] for s in SPLITS])
def test_the_measurement_cap_does_not_refuse_an_exact_sheet(
        clean, label, ceiling, parts):
    """
    `measurement.overmeasures()` carries the identical shape against the BOQ
    quantity, and gets the identical treatment. Sheets split the same way.
    """
    _mkboq("b1", ceiling)
    for i, q in enumerate(parts[:-1]):
        STORE["measurements"][f"ms{i}"] = {
            "id": f"ms{i}", "ref": f"SF/MS/26-27/{i + 1:04d}", "fy": "26-27",
            "date": "2026-08-06", "boq_id": "b1",
            "boq_ref": "SF/BOQ/26-27/0001", "status": "approved",
            "items": [{"line_id": _LID, "item_no": "1", "qty": q,
                       "is_header": False}],
        }

    breaches = MS.overmeasures(
        "b1", [{"line_id": _LID, "item_no": "1", "qty": parts[-1],
                "is_header": False}])
    assert breaches == [], (
        f"{label}: the final legitimate measurement was REFUSED — "
        f"{[MS.overmeasure_message(v) for v in breaches]}")


def test_the_two_ceilings_share_one_epsilon_value():
    """
    They are separate constants in separate modules by design — `ra.py` and
    `measurement.py` do not import each other's — but they must agree, or a
    quantity that measures cleanly refuses to bill.
    """
    assert ra._QTY_EPSILON == MS._QTY_EPSILON == 1e-6
