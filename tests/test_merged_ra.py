"""
CC-2 **C3** — the merged RA bill.

Built 2 September 2026 under the first override block of that date, which
unblocked C3 by answering **BQ2** and then **BQ1**.

⚠ **CC-2's six invariants each get a test AND a control**, because every one of
them is a refusal, and a refusal that refuses everything satisfies its own test:

| invariant | the refusal | its control |
|---|---|---|
| both legs ISSUED | a draft leg refuses | two issued legs merge |
| same project | two chains refuse | one chain merges |
| at most one **live** merge per bill | a second merge refuses | cancel it and the same pair merges |
| a merged leg cannot be cancelled | `ra.can_cancel()` refuses | cancel the merge, the leg cancels |
| no claims of its own | the record has no `claims` key | the over-claim guard does not move |
| totals are the **stored** sums | editing the BOQ moves nothing | the sum is the two bills' own figures |

Plus BQ1 and BQ2 in code: the series is capped at 16, it is minted from its own
counter, and it **does not collide with `invoice.py`'s**.
"""

import pytest

import approval
import boq as BQ
import demo_data as DD
import invoice
import merged_ra
import pipeline as P
import ra as RA
from store import STORE

from conftest import ensure_test_user


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture()
def chain(client):
    """A seeded BOQ with one issued supply bill and one issued installation bill."""
    client.get("/boq/")
    BQ.ensure_demo_boq()
    bid = DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE.setdefault("merged_ras", {}).clear()
    line = next(li for li in STORE["boqs"][bid]["line_items"]
                if not li["is_header"] and li["total_qty"] > 0)
    return {"boq_id": bid, "line": line}


def _bill(chain, rid, ra_no, leg, ref, status="issued", qty=1.0, boq_id=None):
    line = chain["line"]
    rate = float(line["supply_rate"] if leg == "supply" else line["install_rate"])
    claims = [RA.build_claim(line, qty, rate, 0.0, rate, leg=leg)]
    subtotal, drows, dtotal, net = RA.bill_totals(claims, [])
    rec = {
        "id": rid, "ref": ref, "fy": "26-27", "date": "2026-09-01",
        "boq_id": boq_id or chain["boq_id"], "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "ra_no": ra_no, "leg": leg, "claims": claims,
        "claim_subtotal": subtotal, "deductions": drows,
        "deduction_total": dtotal, "net_payable": net,
        "tax_amount": round(net * 0.18, 2), "rounding_off": 0.0,
        "grand_total": round(net * 1.18, 2),
        "status": status, "issued_on": "2026-09-01", "cancelled_on": "",
        "cancel_reason": "", "notes": "", "project_name": "Test Project",
        "to": "A Contractor", "tax_type": "cgst_sgst",
    }
    STORE.setdefault("ra_bills", {})[rid] = rec
    return rec


@pytest.fixture()
def pair(chain):
    s = _bill(chain, "m-supply", 1, "supply", "SF/RA/26-27/0001")
    i = _bill(chain, "m-install", 2, "installation", "SF/RA/26-27/0002")
    return chain, s, i


# =============================================================================
# 1. BQ2 — the 16-character cap, and what it does NOT touch
# =============================================================================

def test_the_minted_reference_fits_rule_46b(pair):
    """⚠ BQ2's answer in code: a tax invoice number is capped at 16 characters."""
    _chain, s, i = pair
    doc, err = merged_ra.create(s, i)
    assert doc is not None, err
    ref = doc["tax_invoice_ref"]
    assert len(ref) <= 16, f"{ref!r} is {len(ref)} characters; Rule 46(b) allows 16"
    assert ref == "SF/MI/26-27/0001"


def test_the_cap_still_holds_at_the_top_of_the_series():
    """
    A cap that only holds at 0001 is not a cap. Checked to 9999, which is where
    the `:04d` format stops growing.
    """
    import branding as B

    for seq in (1, 99, 1000, 9999):
        ref = P.fy_ref(B.COMPANY_SHORT, merged_ra._REF_SERIES, "26-27", seq,
                       cap=merged_ra._REF_CAP)
        assert len(ref) <= 16, f"{ref!r} is {len(ref)} characters at seq={seq}"


def test_the_ra_bills_own_reference_cap_is_NOT_changed():
    """
    ⚠ **BQ2 splits the question and this is the half that must not move.**

    `ref` is our document number and keeps its 64 characters; only
    `tax_invoice_ref` inherits Rule 46(b). Lowering `ra._REF_CAP` would shorten
    every RA reference in the database for no statutory reason at all.
    """
    assert RA._REF_CAP == 64, (
        "ra._REF_CAP moved. BQ2's ruling is that the RA bill's own `ref` is a "
        "document number with no statutory cap, and that only the tax invoice "
        "serial inherits Rule 46(b)'s 16.")
    assert merged_ra._REF_CAP == 16


def test_the_dead_premise_is_marked_as_one_in_ra_py():
    """
    BQ2 required whoever answered it to correct `ra.py`'s comment, which said
    the RA bill *"is not"* a tax invoice — a premise the 8 August amendment
    reversed. A right answer resting on a dead reason is how the next reader
    gets it wrong.

    ⚠ **The old sentence is still in the file ON PURPOSE.** The correction
    quotes what it corrected, which is this repository's house style everywhere
    else — so "the string is gone" would be the wrong assertion, and would push
    the next person to delete the history rather than keep it. What must be true
    is that it no longer stands as a **claim**.
    """
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent / "ra.py").read_text(encoding="utf8")
    # Collapsed, because the phrase is wrapped across a comment line break and
    # a raw substring search would be asserting the line width rather than the
    # wording. The leading `#` and the `**` emphasis go too — they sit BETWEEN
    # the two words once the line break is removed, which is the trap this
    # comment exists to stop somebody falling into twice.
    flat = " ".join(src.replace("#", " ").replace("*", "").split()).lower()

    assert "dead premise" in flat, (
        "ra.py does not name the dead premise BQ2 required correcting")
    assert "used to read" in flat, (
        "the correction does not mark the old wording as former, so a reader "
        "cannot tell the quotation from the ruling")
    assert "tax_invoice_ref" in src, (
        "the corrected comment should name the field that DOES inherit Rule "
        "46(b)'s cap, or it only says what is not true")


# =============================================================================
# 2. BQ1 — an independent series that does not collide
# =============================================================================

def test_the_merged_series_does_not_collide_with_the_tax_invoice_series(pair):
    """
    ⚠ **The collision this ruling exists to avoid.** `invoice.py` mints
    `SF/TI/...` at cap 16. Two counters emitting the same series would put ONE
    statutory serial on TWO documents — the precise failure Rule 46(b) prevents,
    and strictly worse than the ambiguity BQ1 was resolving.
    """
    assert merged_ra._REF_SERIES != invoice._REF_SERIES, (
        "the merged document and the sell-side tax invoice mint the same "
        "series. One statutory serial would land on two different documents.")

    _chain, s, i = pair
    doc, err = merged_ra.create(s, i)
    assert doc is not None, err
    assert "/TI/" not in doc["tax_invoice_ref"]
    assert "/MI/" in doc["tax_invoice_ref"]


def test_the_reference_is_derived_from_neither_leg(pair):
    """
    ⚠ CC-2's BQ1: *"do not resolve it by quietly having the merged document
    reuse one leg's number."* `SF/RA/26-27/0004` is exactly 16 characters, so
    there is no room to decorate one into a unique merged variant.
    """
    _chain, s, i = pair
    doc, err = merged_ra.create(s, i)
    assert doc is not None, err
    ref = doc["tax_invoice_ref"]
    assert ref != s["ref"] and ref != i["ref"]
    assert s["ref"] not in ref and i["ref"] not in ref

    # ⚠ **The sharp version: give the legs high numbers and the merged serial
    #   must not follow them.** Asserting "the leg's ra_no is not a substring of
    #   the merged one" would be satisfied by accident — `1` is inside `0001` —
    #   so the sequence itself is measured. A derived serial would come out at
    #   0042 or 0091 rather than at its own counter's next value.
    s["ra_no"], i["ra_no"] = 42, 91
    s["ref"], i["ref"] = "SF/RA/26-27/0042", "SF/RA/26-27/0091"
    merged_ra.apply_cancel(doc, "released for the second half of this test")
    second, err2 = merged_ra.create(s, i)
    assert second is not None, err2
    assert second["tax_invoice_ref"] == "SF/MI/26-27/0002", (
        f"the merged serial is {second['tax_invoice_ref']!r}, which tracks a "
        f"leg's number rather than its own counter")


def test_the_series_counts_max_plus_one_and_never_reissues(pair):
    """
    A cancelled document keeps its number. Re-issuing a spent statutory serial
    is the one thing a number series may never do.
    """
    _chain, s, i = pair
    first, _e = merged_ra.create(s, i)
    assert first["tax_invoice_ref"] == "SF/MI/26-27/0001"

    merged_ra.apply_cancel(first, "withdrawn")
    second, err = merged_ra.create(s, i)
    assert second is not None, err
    assert second["tax_invoice_ref"] == "SF/MI/26-27/0002", (
        "the cancelled document's number was reissued. It has been quoted in "
        "somebody else's ledger and a second document bearing it is "
        "indistinguishable from the first.")


def test_a_single_leg_bills_tax_invoice_ref_is_UNCHANGED(pair):
    """
    ⚠ **REWRITTEN 3 September 2026. "UNCHANGED" now means "unchanged BY THE
    MERGE", and the standalone gap this used to pin is CLOSED.**

    What it said, and it was true on the day it was written:

        ⚠ **The limitation the override block states in its own words**, pinned
        so nobody reads C3 as having closed it: this pass mints a series for the
        MERGED document only. A single-leg RA bill's `tax_invoice_ref` is still
        a typed field with no counter behind it — DOMAIN.md §4.2's STATUS
        paragraph stands.

    Its two original assertions, kept verbatim so what changed is legible:

        assert not s.get("tax_invoice_ref"), (
            "an RA bill acquired a minted tax_invoice_ref. That gap is real and "
            "is explicitly NOT in C3's scope — closing it needs an override "
            "block of its own.")
        assert not i.get("tax_invoice_ref")

    **The override block it asked for is the first of 3 September 2026**, and
    `ra.next_tax_invoice_ref()` is the counter. So the first assertion is now
    the opposite of the rule and is gone — but note what it was really testing:
    `_bill()` writes its record **directly** rather than posting `/ra/create`,
    so it asserted a property of the fixture and would have gone on passing
    unchanged after the gap closed. ⚠ **The 3 September §0 block predicted this
    test would fail and it does not.** The prediction was wrong, it is recorded
    rather than quietly dropped, and `tests/test_ra_tax_invoice_ref.py` is where
    the closing of the gap is actually held — through the route, which is the
    only place minting happens.

    **What survives is C3's own invariant and it is the half worth keeping:**
    merging must not write a serial onto either leg. That was previously
    unfalsifiable here, because a leg had no serial for the merge to overwrite.
    It does now, so this asserts it against a value that a bug could plausibly
    clobber.
    """
    _chain, s, i = pair
    s["tax_invoice_ref"] = "SF/RI/26-27/0009"
    i["tax_invoice_ref"] = "SF/RI/26-27/0010"

    doc, err = merged_ra.create(s, i)
    assert doc is not None, err

    assert s["tax_invoice_ref"] == "SF/RI/26-27/0009", "merging wrote a serial onto a leg"
    assert i["tax_invoice_ref"] == "SF/RI/26-27/0010", "merging wrote a serial onto a leg"
    assert doc["tax_invoice_ref"] == "SF/MI/26-27/0001", (
        "the merged document's serial is derived from a leg's. BQ1's answer is "
        "that it is minted from its own counter, derived from NEITHER leg.")


# =============================================================================
# 3. WHAT MAY BE MERGED — ra.py's own status rules, not a looser set
# =============================================================================

def test_two_issued_bills_from_one_project_merge(pair):
    """The control every refusal below is measured against."""
    _chain, s, i = pair
    doc, err = merged_ra.create(s, i)
    assert doc is not None, f"a legitimate merge was refused: {err}"
    assert doc["supply_ra_id"] == s["id"]
    assert doc["installation_ra_id"] == i["id"]


def test_a_draft_leg_is_refused(chain):
    """⚠ A draft is not a claim that has gone anywhere, and a merge invoices."""
    s = _bill(chain, "d-supply", 1, "supply", "SF/RA/26-27/0001", status="draft")
    i = _bill(chain, "d-install", 2, "installation", "SF/RA/26-27/0002")
    doc, err = merged_ra.create(s, i)
    assert doc is None, "a draft bill was merged"
    assert "draft" in err.lower()
    assert not STORE.get("merged_ras"), "a refused merge still minted a serial"


def test_a_cancelled_leg_is_refused(chain):
    """A cancelled bill claims nothing, so there is nothing of it to invoice."""
    s = _bill(chain, "c-supply", 1, "supply", "SF/RA/26-27/0001", status="cancelled")
    i = _bill(chain, "c-install", 2, "installation", "SF/RA/26-27/0002")
    doc, err = merged_ra.create(s, i)
    assert doc is None, "a cancelled bill was merged"
    assert "cancel" in err.lower()


def test_the_status_rules_are_ra_pys_own(chain):
    """
    ⚠ **Not a looser set invented here.** `candidates()` must defer to
    `ra.is_issued()`, so a change to `ra.STATUSES` or to `status_of()`'s
    normalisation reaches this module without an edit.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(merged_ra.candidates))
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "RA.is_issued" in calls, (
        "candidates() no longer asks ra.py whether a bill is issued. The status "
        "rules would then be a second, drifting copy.")


def test_two_legs_of_the_same_kind_are_refused(chain):
    s1 = _bill(chain, "s1", 1, "supply", "SF/RA/26-27/0001")
    s2 = _bill(chain, "s2", 2, "supply", "SF/RA/26-27/0002")
    doc, err = merged_ra.create(s1, s2)
    assert doc is None and "installation" in err.lower()


def test_bills_from_different_projects_are_refused(chain):
    """CC-2: a merged document covers **one** project's supply and installation."""
    other = "boq-other"
    STORE["boqs"][other] = dict(STORE["boqs"][chain["boq_id"]])
    STORE["boqs"][other]["id"] = other

    s = _bill(chain, "x-supply", 1, "supply", "SF/RA/26-27/0001")
    i = _bill(chain, "x-install", 1, "installation", "SF/RA/26-27/0002",
              boq_id=other)
    doc, err = merged_ra.create(s, i)
    assert doc is None, "bills from two different projects were merged"
    assert "different projects" in err.lower()


# =============================================================================
# 4. AT MOST ONE LIVE MERGE — and cancelling releases both legs
# =============================================================================

def test_a_bill_cannot_be_in_two_live_merges(chain):
    """
    ⚠ CC-2: *"A bill may appear in at most one live merged document. Otherwise
    the same money is invoiced twice."*
    """
    s = _bill(chain, "p-supply", 1, "supply", "SF/RA/26-27/0001")
    i1 = _bill(chain, "p-install-1", 2, "installation", "SF/RA/26-27/0002")
    i2 = _bill(chain, "p-install-2", 3, "installation", "SF/RA/26-27/0003")

    first, err = merged_ra.create(s, i1)
    assert first is not None, err

    second, err2 = merged_ra.create(s, i2)
    assert second is None, (
        "the same supply bill was invoiced twice, under two live merged "
        "documents")
    assert "at most one" in err2.lower() or "already inside" in err2.lower()
    assert len(STORE["merged_ras"]) == 1


def test_cancelling_the_merge_releases_both_legs(chain):
    """
    ⚠ **The control**, and CC-2's own remedy: *"Cancel the merged document
    first, which releases both legs."* Without this the rule above would be a
    permanent lock rather than an invariant.
    """
    s = _bill(chain, "r-supply", 1, "supply", "SF/RA/26-27/0001")
    i = _bill(chain, "r-install", 2, "installation", "SF/RA/26-27/0002")

    first, _e = merged_ra.create(s, i)
    assert merged_ra.live_merge_of(s["id"]) is first

    merged_ra.apply_cancel(first, "raised in error")

    assert merged_ra.live_merge_of(s["id"]) is None, "the supply leg was not released"
    assert merged_ra.live_merge_of(i["id"]) is None, "the installation leg was not released"

    again, err = merged_ra.create(s, i)
    assert again is not None, f"the released pair could not be merged again: {err}"


def test_a_leg_inside_a_live_merge_cannot_be_cancelled(chain):
    """
    ⚠ CC-2: *"A source bill inside a live merged document cannot be cancelled."*

    Without it a cancelled leg would leave a live tax invoice standing over a
    claim that claims nothing — an invoice for money no bill supports.
    """
    s = _bill(chain, "k-supply", 1, "supply", "SF/RA/26-27/0001")
    i = _bill(chain, "k-install", 2, "installation", "SF/RA/26-27/0002")

    allowed_before, _why = RA.can_cancel(s)
    assert allowed_before, "precondition: the bill is cancellable before merging"

    doc, _e = merged_ra.create(s, i)
    allowed, why = RA.can_cancel(s)
    assert not allowed, "a bill inside a live merged document was cancellable"
    assert doc["tax_invoice_ref"] in why, (
        "the refusal should name the document holding the bill, so the operator "
        "knows what to cancel first")

    merged_ra.apply_cancel(doc, "withdrawn")
    allowed_after, _w = RA.can_cancel(s)
    assert allowed_after, (
        "cancelling the merged document did not release the leg for "
        "cancellation — the rule is a permanent lock rather than an invariant")


def test_the_two_sides_agree_on_what_a_live_merge_is(chain):
    """
    `ra._live_merge_holding()` and `merged_ra.live_merge_of()` ask the same
    question from opposite sides of a one-way import, so they are two functions
    that must agree. Held over every status value rather than left to a comment.
    """
    s = _bill(chain, "a-supply", 1, "supply", "SF/RA/26-27/0001")
    i = _bill(chain, "a-install", 2, "installation", "SF/RA/26-27/0002")
    doc, _e = merged_ra.create(s, i)

    for status in ("live", "cancelled", "", "nonsense", None):
        doc["status"] = status
        mine = merged_ra.live_merge_of(s["id"])
        theirs = RA._live_merge_holding(s["id"])
        assert (mine is None) == (theirs is None), (
            f"with status={status!r}, merged_ra says {mine!r} and ra.py says "
            f"{theirs!r}. A bill would be cancellable from one side and locked "
            f"from the other.")


# =============================================================================
# 5. NO CLAIMS OF ITS OWN — and the over-claim guard does not move
# =============================================================================

def test_the_merged_record_holds_no_claims_of_its_own(pair):
    """
    ⚠ CC-2: *"The merged record never holds claims of its own. It references
    the two source bills. Copying claim rows into it would make the over-claim
    guard count the same quantity twice."*
    """
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    assert "claims" not in doc, (
        "the merged record carries claim rows. ra.claimed_by_line() would count "
        "the same quantity a second time and every over-claim check downstream "
        "would be wrong in the direction that lets money through.")


def test_merging_does_not_move_the_overclaim_guard(pair):
    """
    The consequence, measured rather than argued.

    ⚠ **AND IT IS WEAKER THAN THE TEST ABOVE IT TODAY — stated so nobody reads
    it as more.** `ra.claimed_by_line()` walks `STORE["ra_bills"]`, and a merged
    document lives in `STORE["merged_ras"]`, so copying claim rows onto the
    merged record does **not** move this figure as things stand: mutation-tested
    on 2 September 2026, and this test went on passing while
    `test_the_merged_record_holds_no_claims_of_its_own` caught it. **The shape
    test is the one that bites.**

    This is kept anyway, as the guard for the change that would make CC-2's
    warning real: a later pass that files merged documents in `ra_bills` — to
    put them on one register, say — and this fails the day it does. That is the
    arrangement worth having, but it must not be mistaken for a live proof.
    """
    _chain, s, i = pair
    boq_id = s["boq_id"]
    before = dict(RA.claimed_by_line(boq_id))

    doc, _e = merged_ra.create(s, i)
    after = dict(RA.claimed_by_line(boq_id))

    assert after == before, (
        "merging two bills changed the claimed quantity against the schedule. "
        "The merged document is being counted as a third claim.")


def test_the_rows_are_stacked_and_not_combined(pair):
    """
    CC-2's own example keeps Item 1 (supply) and Item 1 (installation) as TWO
    rows. Combining them would need the legs to agree on a unit, a rate and an
    HSN/SAC, and they agree on none of the three.
    """
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    rows = merged_ra.stacked_rows(doc)

    assert len(rows) == len(s["claims"]) + len(i["claims"]), (
        "the two legs' rows were combined rather than stacked")
    assert [r["_leg"] for r in rows] == (["supply"] * len(s["claims"])
                                         + ["installation"] * len(i["claims"])), (
        "supply should come first, then installation")


# =============================================================================
# 6. THE TOTALS ARE THE STORED SUMS — never recomputed from the live BOQ
# =============================================================================

def test_the_total_is_the_sum_of_the_stored_totals(pair):
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    for key in ("claim_subtotal", "net_payable", "grand_total"):
        assert doc[key] == pytest.approx(round(s[key] + i[key], 2)), (
            f"{key} is not the sum of the two bills' own stored {key}")


def test_revising_the_boq_does_not_move_a_merged_document(pair):
    """
    ⚠ **The defect class CC-2 names by name** — *"same defect class as the
    `print_ra` bug already fixed once."* A document the client already holds
    must not restate itself when the schedule moves.
    """
    chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    frozen = float(doc["grand_total"])

    # Move every rate on the live schedule, hard.
    for li in STORE["boqs"][chain["boq_id"]]["line_items"]:
        if not li.get("is_header"):
            li["supply_rate"] = float(li.get("supply_rate") or 0.0) * 10
            li["install_rate"] = float(li.get("install_rate") or 0.0) * 10

    assert float(doc["grand_total"]) == frozen, (
        "the merged document's total moved when the BOQ was revised. It must be "
        "the sum of what the two bills STORED, never recomputed from the live "
        "schedule.")
    assert merged_ra._sum_totals(s, i)["grand_total"] == pytest.approx(frozen)


def test_receipts_stay_on_the_source_bills(pair):
    """
    ⚠ CC-2: *"Receipts stay attached to the source bills. The merged document
    derives its balance by summing them. Do not repoint receipts."*
    """
    _chain, s, i = pair
    STORE.setdefault("receipts", {})["rc-1"] = {
        "id": "rc-1", "ref": "SF/RCPT/26-27/0001", "fy": "26-27",
        "date": "2026-09-02", "ra_id": s["id"], "amount": 1000.0,
        "write_off": 0.0, "mode": "neft", "boq_id": s["boq_id"],
    }
    doc, _e = merged_ra.create(s, i)

    assert STORE["receipts"]["rc-1"]["ra_id"] == s["id"], (
        "the receipt was repointed at the merged document")
    expected = round(RA.outstanding_of(s) + RA.outstanding_of(i), 2)
    assert merged_ra.balance(doc) == pytest.approx(expected), (
        "the merged balance is not the sum of the two legs' outstanding")


# =============================================================================
# 7. THE LADDER, THE REGISTER AND THE ROUTES
# =============================================================================

def test_the_merged_document_climbs_the_ra_ladder():
    spec = approval.DOCUMENTS["merged_ra"]
    assert spec["steps"] == ("operation-head", "director"), (
        "B6 gives RA / Tax Invoice / PO the Operation Head + Director ladder, "
        "and a merged RA is both of the first two at once")
    assert spec["sequential"] is False
    assert spec["collection"] == "merged_ras"


def test_no_permission_was_minted_for_c3():
    """
    ⚠ A permission that reaches no role is the failure ABOUT.md §2g records
    shipping three times. C3 reuses `ra.*` throughout.
    """
    import auth

    minted = [p for p in auth.PERMISSIONS
              if p.startswith("merged") or p.startswith("merged_ra.")]
    assert minted == [], f"C3 minted {minted} — reuse ra.* or reconcile them"
    assert auth.ROUTE_PERMISSIONS["merged_ra.create_merged"] == "ra.create"
    assert auth.ROUTE_PERMISSIONS["merged_ra.cancel_merged"] == "ra.cancel"
    assert auth.ROUTE_PERMISSIONS["merged_ra.list_merged"] == "ra.view"
    assert auth.ROUTE_PERMISSIONS["approval.approve_merged_ra"] == "ra.approve"


def test_ra_approve_and_invoice_approve_reach_the_same_roles():
    """
    The check the `approval.DOCUMENTS` note claims was made rather than assumed.

    It is what makes `ra.approve` a safe choice for the merged document: if the
    two ever diverge, choosing one over the other starts conferring something,
    and this fails so the choice is re-taken deliberately.
    """
    import auth

    def holders(perm):
        return {name for name, spec in auth.BUILTIN_ROLES.items()
                if perm in set(spec[-1] if isinstance(spec, tuple) else spec)}

    assert holders("ra.approve") == holders("invoice.approve"), (
        "ra.approve and invoice.approve no longer reach the same roles, so "
        "which one the merged document carries now confers something. Re-take "
        "the decision in approval.DOCUMENTS deliberately.")


def test_the_merge_action_is_on_the_ra_register(client, pair):
    """
    ⚠ CC-2, in its own words: *"Build the merge action ON THE RA REGISTER from
    day one. The draft-PO → PO bridge was initially shipped without its entry
    point; do not repeat that."*
    """
    body = client.get("/ra/").get_data(as_text=True)
    assert "/merged/" in body, (
        "the RA register carries no link to the merged documents. CC-2 names "
        "this register as the merge action's entry point.")


def test_an_unapproved_merged_document_does_not_print(client, pair):
    """B7, applied to the merged document exactly as it is to an RA bill."""
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    assert not approval.is_approved(doc)

    r = client.get(f"/merged/print/{doc['id']}", follow_redirects=False)
    assert r.status_code in (302, 303), "an unapproved merged tax invoice printed"


def test_an_approved_merged_document_prints(client, pair):
    """⚠ The control: the gate must be B7's, not a wall."""
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    doc["approval_status"] = approval.APPROVED

    r = client.get(f"/merged/print/{doc['id']}")
    assert r.status_code == 200, "an approved merged tax invoice was refused"
    body = r.get_data(as_text=True)
    assert doc["tax_invoice_ref"] in body
    assert "MERGED TAX INVOICE" in body


def test_the_printed_sheet_carries_both_legs(client, pair):
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)
    doc["approval_status"] = approval.APPROVED
    body = client.get(f"/merged/print/{doc['id']}").get_data(as_text=True)
    assert s["ref"] in body and i["ref"] in body, (
        "the merged sheet does not name both source bills")
    assert "SUPPLY" in body.upper() and "INSTALLATION" in body.upper()


def test_the_cancel_route_answers_post_only_for_the_change(client, pair):
    """A GET renders the confirmation and mutates nothing."""
    _chain, s, i = pair
    doc, _e = merged_ra.create(s, i)

    r = client.get(f"/merged/cancel/{doc['id']}")
    assert r.status_code == 200
    assert merged_ra.is_live(doc), "a GET on the cancel route withdrew the document"

    client.post(f"/merged/cancel/{doc['id']}", data={"reason": "error"},
                follow_redirects=False)
    assert merged_ra.is_cancelled(doc)


def test_merged_ras_does_not_import_backwards():
    """
    `merged_ra.py ──► ra.py`, never the reverse. `ra.py` reads
    `STORE["merged_ras"]` directly and links with `url_for` — the one-way trick.
    """
    import pathlib
    import ast

    repo = pathlib.Path(__file__).resolve().parent.parent
    tree = ast.parse((repo / "ra.py").read_text(encoding="utf8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "merged_ra" not in imported, (
        "ra.py imports merged_ra.py, which is a cycle: merged_ra imports ra for "
        "the chain, the status predicates and the outstanding arithmetic.")
    src = (repo / "ra.py").read_text(encoding="utf8")
    assert "merged_ras" in src, "ra.py should read STORE['merged_ras'] directly"
    assert 'url_for("merged_ra.' in src, "ra.py should link with url_for"
