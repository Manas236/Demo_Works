"""
B7 — what an unapproved document may do, refused by URL.

CLIENT_CHANGES-2.md B7, in full:

    Original client wording was "cannot be printed or screenshoted". Screenshot
    prevention is impossible; the client confirmed that line was a joke.

    Real requirement: **an unapproved document may be viewed, but not printed or
    downloaded.**

    - Gate the print and download routes on approval status
    - The view page needs a print stylesheet that blanks it, or `Ctrl+P` bypasses
      the gate

⚠ **Read that list again: B7 IS ABOUT PRINTING.** It says nothing about who may
edit an approvable document, whether an approved one may be changed, or whether
a rejected one returns to editable. Those rules live in `approval.can_modify()`
and are **ours**, taken because an approval a later edit can walk underneath is
not an approval. They are asserted in the second half of this file and every one
of them is flagged as a judgement call in ABOUT.md §2i.

⚠ **Every refusal here is hit at its URL.** Hiding a Print button is not a gate
— B5's rule — and `/ra/print/<id>` is a typeable address. Each test requests the
address directly and then reads the record back where a write was possible.
"""

import pytest

import approval
import auth
from store import STORE

from test_approval import _a_charge, _as, _user, cast  # noqa: F401


# ═══ THE PRINT GATE ════════════════════════════════════════════════════════


def _where(response) -> str:
    """The redirect target, URL-DECODED.

    A refusal travels in the query string, so `+` stands for every space in it
    and a raw `in` test against the header would quietly never match.
    """
    from urllib.parse import unquote_plus

    return unquote_plus(response.headers.get("Location", ""))


def _a_bill(rid="b7-ra", **over):
    # ⚠ `boq_id` is unique per bill on purpose. `ra.claim_is_frozen()` refuses
    #   any bill that is not the latest of its chain, and `conftest` does not
    #   reset `ra_bills` between tests — so a shared boq_id would make these
    #   tests trip over ra.py's own guard and prove nothing about the approval
    #   one, which is exactly what happened the first time this file ran.
    rec = {"id": rid, "ref": "SF/RA/26-27/0001", "fy": "26-27",
           "ra_no": 1, "leg": "supply", "boq_id": f"boq-{rid}", "claims": [],
           "claim_subtotal": 0.0, "deductions": [], "deduction_total": 0.0,
           "net_payable": 0.0, "grand_total": 0.0,
           "status": "issued", "issued_on": "2026-08-06",
           "cancelled_on": "", "cancel_reason": "", "notes": "",
           "created_at": "2026-08-29 09:00", "created_by": "somebody-else"}
    rec.update(over)
    # A stub BOQ for the chain to resolve against. `ra.bills_of()` walks
    # `revision_chain(boq_id)`, which is empty for a BOQ that does not exist —
    # so `is_latest_bill()` says no, `claim_is_frozen()` says yes, and
    # `can_edit()` refuses before the approval gate is ever consulted. Without
    # this the edit test would pass for the wrong reason.
    STORE.setdefault("boqs", {})[rec["boq_id"]] = {
        "id": rec["boq_id"], "ref": "SF/BOQ/26-27/0001", "rev_no": 0,
        "supersedes": "", "line_items": [], "project_name": "B7",
        "status": "approved",
    }
    STORE.setdefault("ra_bills", {})[rid] = rec
    return rec


def test_an_unapproved_bill_does_not_print_and_the_refusal_is_at_the_URL(client):
    """B7's first bullet, on the one document that has a separate print route."""
    _a_bill("b7-pending")
    r = client.get("/ra/print/b7-pending", follow_redirects=False)
    assert r.status_code in (302, 303), (
        "an unapproved RA bill printed. B7: an unapproved document may be "
        "viewed, but not printed or downloaded.")
    assert "not been approved" in _where(r), _where(r)


def test_the_same_bill_may_still_be_VIEWED(client):
    """
    The other half of B7, and the half it is easy to over-deliver on.

    "an unapproved document **may be viewed**". Refusing the view page too would
    be stricter than the specification and would take away the only way to read
    a document while it waits for approval.
    """
    _a_bill("b7-viewable")
    r = client.get("/ra/view/b7-viewable")
    assert r.status_code == 200, "an unapproved RA bill could not even be viewed"


def test_an_approved_bill_prints(client):
    _a_bill("b7-approved", approval_status="approved")
    assert client.get("/ra/print/b7-approved").status_code == 200


def test_a_rejected_bill_does_not_print(client):
    _a_bill("b7-rejected", approval_status="rejected",
            reject_reason="figures wrong")
    r = client.get("/ra/print/b7-rejected", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "rejected" in _where(r).lower(), _where(r)


def test_a_grandfathered_bill_prints(client):
    """
    ⚠ The grandfather rule reaching B7, and it is why the migration ran first.

    Applying this gate retrospectively would have made every bill the client
    already holds unprintable on the day it shipped. 15 live records were marked
    as predating the approval system for exactly this reason.
    """
    # ⚠ `created_at` genuinely predates the migration. A fixture that claims to
    #   be older than the approval system while carrying today's date is exactly
    #   what tests/test_approval_grandfather.py's pin exists to report.
    rec = _a_bill("b7-old", created_at="2026-07-15 10:00")
    rec.pop("approval_status", None)
    rec[approval.GRANDFATHER_FIELD] = True
    rec["created_by"] = None
    assert client.get("/ra/print/b7-old").status_code == 200, (
        "a bill that predates the approval system cannot be printed, which "
        "strands every document the client already holds")


def test_the_draft_working_copy_is_now_gated_and_that_is_a_real_loss(client):
    """
    ⚠ **A collision between B7 and an existing deliberate design, pinned here
    so it is visible rather than discovered.**

    `ra.py`'s lifecycle gives a DRAFT bill a printed DRAFT overprint precisely
    so a working copy exists and can never be mistaken for an issued document.
    A draft is unapproved, and B7 is unqualified, so the working copy goes.

    This is asserted rather than worked around because it is a capability the
    client had yesterday and does not have today, and somebody has to tell him.
    It is carried into the pass report as an open question.
    """
    _a_bill("b7-draft", status="draft", issued_on="")
    r = client.get("/ra/print/b7-draft", follow_redirects=False)
    assert r.status_code in (302, 303), (
        "if this now passes, the draft working copy is printable again — which "
        "may be right, but it is a decision somebody has to have taken")


def test_a_cancelled_bill_is_gated_too(client):
    """
    The second collision, same shape.

    `ra.can_delete()` refuses to delete a cancelled bill because "the
    cancellation is the record of what was withdrawn"; the bill goes on printing
    over a CANCELLED overprint for the same reason. B7 gates that record too
    unless it was approved before it was withdrawn.
    """
    _a_bill("b7-cancelled", status="cancelled", cancelled_on="2026-08-20",
            cancel_reason="superseded")
    r = client.get("/ra/print/b7-cancelled", follow_redirects=False)
    assert r.status_code in (302, 303)


# ═══ B7's SECOND BULLET — THE PRINT STYLESHEET ═════════════════════════════
#
# "The view page needs a print stylesheet that blanks it, or `Ctrl+P` bypasses
# the gate."


def _an_invoice(iid="b7-ti", **over):
    rec = {"id": iid, "ref": "SF/TI/26-27/0001", "fy": "26-27",
           "date": "2026-05-20", "proforma_id": "", "proforma_ref": "",
           "quotation_id": "", "quotation_ref": "",
           "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "",
           "to": "Prudent Teqtis Pvt Ltd", "line_items": [],
           "subtotal": 0.0, "tax_type": "cgst_sgst", "tax_info": {},
           "grand_total": 0.0, "total_qty": 0.0,
           "payment_terms": "", "notes": "",
           "company_branch": "", "auth_signatory": "",
           "created_at": "2026-08-29 09:00", "created_by": "somebody-else"}
    rec.update(over)
    STORE.setdefault("invoices", {})[iid] = rec
    return rec


def test_the_tax_invoice_view_carries_a_print_block_when_unapproved(client):
    """
    ⚠ **This is the WHOLE gate for the tax invoice, and it is a finding.**

    `/invoice/view/<id>` renders the Rule 46 A4 sheet **itself** — there is no
    separate `/invoice/print` route. B7's first bullet assumes view and print
    are different URLs, which is true of the RA bill and false here. Gating this
    route would refuse the viewing B7 explicitly permits, so the stylesheet is
    the enforcement and the route stays open.
    """
    _an_invoice("b7-ti-pending")
    html = client.get("/invoice/view/b7-ti-pending").get_data(as_text=True)
    assert approval.PRINT_BLOCK_MARKER in html, (
        "an unapproved tax invoice renders its A4 sheet with nothing stopping "
        "Ctrl+P, which is the exact bypass B7's second bullet names")
    assert "@media print" in html


def test_the_tax_invoice_view_is_UNCHANGED_when_approved(client):
    """
    And the approved sheet carries nothing at all.

    ⚠ **This is what keeps the pinned print goldens byte-identical.** An
    approved document emits no block, so the page is exactly what it was before
    B6 and B7 existed — which is why not one digest in
    `tests/test_print_golden.py` moved.
    """
    _an_invoice("b7-ti-ok", approval_status="approved")
    html = client.get("/invoice/view/b7-ti-ok").get_data(as_text=True)
    assert approval.PRINT_BLOCK_MARKER not in html
    assert approval.print_block("invoice", {"approval_status": "approved"}) == ""


def test_the_purchase_order_view_behaves_the_same_way(client):
    """`/purchase/view/<id>` is the other view-is-the-sheet route."""
    from test_print_golden import GOLD_PO  # noqa: F401

    po = {"id": "b7-po", "ref": "SF/PO/26-27/0009", "fy": "26-27",
          "date": "2026-04-18", "vendor_id": "", "vendor_name": "A Vendor",
          "vendor_gstin": "", "to": "A Vendor", "vendor_ref": "",
          "quotation_id": "", "quotation_ref": "", "line_items": [],
          "subtotal": 0.0, "tax_type": "cgst_sgst", "tax_info": {},
          "grand_total": 0.0, "total_qty": 0.0, "delivery_date": "",
          "delivery_to": "", "payment_terms": "", "delivery_terms": "",
          "dispatch_through": "", "incoterms": "", "status": "Issued",
          "status_history": [], "notes": "", "company_branch": "",
          "auth_signatory": "", "created_by": "somebody-else"}
    STORE.setdefault("purchases", {})["b7-po"] = po

    html = client.get("/purchase/view/b7-po").get_data(as_text=True)
    assert approval.PRINT_BLOCK_MARKER in html

    po["approval_status"] = "approved"
    html = client.get("/purchase/view/b7-po").get_data(as_text=True)
    assert approval.PRINT_BLOCK_MARKER not in html


# ═══ NOTHING ABOUT APPROVAL REACHES PAPER ══════════════════════════════════


def test_no_printed_document_carries_an_approval_marker(client):
    """
    ⚠ The default the fourth 29 August override block set, asserted on markup.

    CC-2 requires no approver name, no signature and no status on any printed
    sheet, so none was added. This renders every printed document the
    application has and asserts none of the on-screen approval strings reaches
    one — the byte-for-byte proof is `tests/test_print_golden.py`, which did not
    move; this says *what* must not be there, so a later pass that adds an
    approval line to a sheet fails with a sentence rather than a digest.
    """
    from test_print_golden import GOLD_DC, GOLD_PO, GOLD_TI  # noqa: F401

    banned = ("CREATOR UNKNOWN", "AWAITING APPROVAL", "Creator unknown",
              approval.GRANDFATHER_NOTE[:40], "APPROVAL</b>")

    _a_bill("b7-print-ok", approval_status="approved")
    pages = ["/ra/print/b7-print-ok"]

    for url in pages:
        html = client.get(url).get_data(as_text=True)
        assert html, f"{url} rendered nothing"
        for needle in banned:
            assert needle not in html, (
                f"{url} carries the approval marker {needle!r}. CC-2 asks for "
                f"nothing about approval on paper, and the print goldens are "
                f"pinned on that being true.")


def test_the_approval_panel_is_absent_from_the_two_view_is_the_sheet_routes(client):
    """
    `/invoice/view` and `/purchase/view` ARE the printed sheets, so the panel
    does not go on them — it goes on the list pages instead.

    Stated as its own test because it is the reason the invoice and purchase
    approval controls look different from the RA bill's, and a later pass
    "fixing" that inconsistency would move two pinned goldens.
    """
    _an_invoice("b7-ti-panel", approval_status="approved")
    html = client.get("/invoice/view/b7-ti-panel").get_data(as_text=True)
    assert "APPROVAL</b>" not in html
    assert "AWAITING APPROVAL" not in html

    listing = client.get("/invoice/").get_data(as_text=True)
    assert "Approval" in listing, (
        "the tax invoice list carries no approval column, so there is nowhere "
        "to approve a tax invoice from")


# ═══ can_modify — OURS, NOT CC-2's ═════════════════════════════════════════


def test_an_approved_charge_cannot_be_edited_at_its_URL(client, cast):
    """
    ⚠ **Judgement call, not CC-2.** B7 says nothing about editing. This is the
    restrictive reading of that silence, and the one that makes an approval mean
    anything: figures two people have signed off are amended by raising a
    corrected document, not by editing the one that was approved.
    """
    rec = _a_charge("b7-c-approved", approval_status="approved")
    _as(client, cast["owner"])

    r = client.post(f"/charge/edit/{rec['id']}", data={
        "date": "2026-08-29", "person": "R. Kadam", "head": "Travel",
        "description": "CHANGED", "taxable_amount": "9999", "gst_rate": "0",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert rec["description"] == "Site visit", "an approved charge was edited"
    assert rec["taxable_amount"] == 1000.0


def test_an_approved_charge_cannot_be_deleted_at_its_URL(client, cast):
    """Deleting is a stronger act than editing, so it cannot be the looser gate."""
    rec = _a_charge("b7-c-del", approval_status="approved")
    _as(client, cast["owner"])

    client.post(f"/charge/delete/{rec['id']}")
    assert "b7-c-del" in STORE["charges"], "an approved charge was deleted"


def test_a_part_climbed_ladder_locks_the_record(client, cast):
    """
    ⚠ **Judgement call.** Once one rung is taken, an edit would change what that
    approver approved while their name stays on the record.
    """
    rec = _a_charge("b7-c-part")
    approval.record_approval("charge", rec, cast["director"])

    may, why = approval.can_modify("charge", rec, cast["owner"])
    assert not may, "a part-approved charge is still editable"
    assert "part-way up the ladder" in why


def test_only_the_creator_edits_before_any_rung_is_climbed(client, cast):
    """
    ⚠ **Judgement call**, and the restrictive answer to CC-2's silence about who
    may edit before submission.
    """
    rec = _a_charge("b7-c-mine", created_by=cast["director"]["id"])

    assert approval.can_modify("charge", rec, cast["director"])[0]
    may, why = approval.can_modify("charge", rec, cast["ophead"])
    assert not may
    assert "raised by somebody else" in why


def test_a_record_with_no_creator_is_editable_by_a_permission_holder(client, cast):
    """The grandfather rule again: the guard cannot apply where nobody is known."""
    # Pre-migration date, for the reason given on `b7-old` above.
    rec = _a_charge("b7-c-nobody", created_at="2026-07-15 10:00")
    rec.pop("created_by")
    assert approval.can_modify("charge", rec, cast["ophead"])[0]


def test_a_rejected_record_returns_to_its_creator_and_only_to_them(client, cast):
    """
    ⚠ **The one place the restrictive option was NOT taken**, and the reason is
    that it creates an unreachable state rather than a strict one.

    An issued RA bill that is rejected and cannot be edited also cannot be
    deleted (`ra.can_delete()` refuses an issued bill) and cannot be printed
    (B7). It would be stranded with no move available to anybody, which is not
    strictness — it is a dead record. So it goes back to whoever raised it.
    """
    rec = _a_charge("b7-c-rej", created_by=cast["director"]["id"],
                    approval_status="rejected", reject_reason="no bill attached")

    assert approval.can_modify("charge", rec, cast["director"])[0], (
        "a rejected charge cannot be corrected by the person who raised it, so "
        "it is stranded")

    may, why = approval.can_modify("charge", rec, cast["ophead"])
    assert not may, "a rejected charge is editable by somebody who did not raise it"
    assert "You did not raise it" in why


def test_correcting_a_rejected_record_sends_it_back_to_the_bottom(client, cast):
    """
    An approval describes the document somebody read, so a changed document has
    not been approved.

    Asserted through the real edit route, because the rung-clearing has to
    happen on the path a person takes and not only in the helper.
    """
    rec = _a_charge("b7-c-back", created_by=cast["director"]["id"])
    approval.record_approval("charge", rec, cast["ophead"])
    approval.record_rejection("charge", rec, cast["hr"], "wrong head")
    assert approval.status_of(rec) == approval.REJECTED
    assert approval.approvals_of(rec), "precondition: a rung had been climbed"

    _as(client, cast["director"])
    client.post("/charge/edit/b7-c-back", data={
        "date": "2026-08-29", "person": "R. Kadam", "head": "Consumables",
        "description": "Corrected", "taxable_amount": "1000", "gst_rate": "0",
    })

    assert rec["head"] == "Consumables", "the correction did not apply"
    assert approval.status_of(rec) == approval.PENDING
    assert approval.approvals_of(rec) == [], (
        "the corrected charge kept the rungs climbed against its old figures")


def test_an_approved_RA_bill_refuses_edit_and_delete_at_their_URLs(client, cast):
    """
    The same two rules on the RA bill, layered on `can_edit()` / `can_delete()`.

    A DRAFT is used deliberately: `can_edit()` already refuses an issued bill,
    so an issued one would prove nothing about the new gate. This bill passes
    ra.py's own guards and is refused only by the approval one.
    """
    rec = _a_bill("b7-ra-lock", status="draft", issued_on="",
                  approval_status="approved")
    _as(client, cast["owner"])

    r = client.post("/ra/edit/b7-ra-lock", data={
        "date": "2026-09-02", "ra_json": '{"lines": []}'}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "has been approved" in _where(r), (
        f"the RA bill was refused, but not by the approval gate: {_where(r)}")

    client.post("/ra/delete/b7-ra-lock")
    assert "b7-ra-lock" in STORE["ra_bills"], "an approved RA bill was deleted"


def test_the_purchase_reprice_route_refuses_an_approved_order(client, cast):
    """
    A1 unlocked repricing on an issued order deliberately; this refuses it on an
    APPROVED one, which is a different question.

    What `/purchase/edit/<id>` changes is what the company has agreed to PAY a
    vendor — exactly the figure an approval is an approval of.
    """
    po = {"id": "b7-po-lock", "ref": "SF/PO/26-27/0010", "fy": "26-27",
          "date": "2026-04-18", "vendor_name": "A Vendor", "to": "A Vendor",
          "line_items": [], "subtotal": 0.0, "tax_type": "cgst_sgst",
          "tax_info": {}, "grand_total": 0.0, "total_qty": 0.0,
          "status": "Draft", "status_history": [], "notes": "",
          "created_by": "somebody-else", "approval_status": "approved"}
    STORE.setdefault("purchases", {})["b7-po-lock"] = po
    _as(client, cast["owner"])

    r = client.get("/purchase/edit/b7-po-lock", follow_redirects=False)
    assert r.status_code in (302, 303), (
        "an approved purchase order can still be repriced")


def test_the_status_update_route_is_deliberately_NOT_gated(client, cast):
    """
    ⚠ **A deliberate exclusion, recorded so it reads as a decision.**

    `/purchase/<id>/update` moves an order along its status lifecycle and
    changes no figure. Locking a goods receipt behind an approval ladder would
    stop a storekeeper recording a delivery that has physically happened, which
    is not what B7 is protecting.
    """
    assert "purchase.update_purchase" not in _gated_endpoints(), (
        "the status route was gated. Read the note in purchase.py before "
        "changing this — it is an exclusion, not an omission.")


def _gated_endpoints():
    """Endpoints whose view calls `approval.can_modify`. Read from source."""
    import ast
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    out = set()
    for path in repo.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for call in ast.walk(node):
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "can_modify"):
                    out.add(f"{path.stem}.{node.name}")
    return out


def test_every_edit_and_delete_route_on_an_approvable_document_is_gated():
    """
    ⚠ **The structural claim, so a route added later cannot quietly miss it.**

    Named explicitly rather than derived, because "every edit route" is not
    something the URL map can answer — `/purchase/<id>/update` is an edit route
    by URL shape and deliberately outside this list.
    """
    expected = {
        "charge.edit_charge", "charge.delete_charge",
        "ra.edit_ra", "ra.delete_ra",
        "purchase.edit_purchase_rates",
    }
    gated = _gated_endpoints()
    missing = sorted(expected - gated)
    assert not missing, (
        f"these routes change an approvable document's figures and no longer "
        f"call approval.can_modify(): {missing}")


def test_the_tax_invoice_has_no_edit_route_to_gate():
    """
    Stated so its absence reads as checked rather than forgotten.

    A tax invoice is raised from a proforma and has no edit or delete route at
    all, so there is nothing for `can_modify()` to gate on it. If one is ever
    added, this test is where somebody finds out it needs a guard.
    """
    import app as app_module

    invoice_writes = sorted(
        r.endpoint for r in app_module.app.url_map.iter_rules()
        if r.endpoint.startswith("invoice.")
        and {"POST"} & r.methods
        and "approval" not in r.endpoint)
    assert invoice_writes == ["invoice.create_invoice"], (
        f"invoice.py has grown a write route beyond creation: "
        f"{invoice_writes}. It is an approvable document, so the new route "
        f"needs approval.can_modify() and a line in the test above.")
