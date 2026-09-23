"""
tests/test_delete_rollout.py — the universal delete rollout, at the route.

`tests/test_cascade.py` proves the WALK is correct against a seeded STORE with
no Flask involved. This file proves the ROUTES that call it behave, which is a
different claim and needs a different kind of test:

- **Every new delete route ships its own GET-does-not-mutate test.** ABOUT.md
  §7.9f's standing rule, and it does not generalise. The `url_map` sweep in
  `tests/test_delete_methods.py` walks every rule whose path contains "delete"
  and asserts it ACCEPTS POST — which catches a GET-only delete route, the
  failure mode `9d060ee` actually had, but **cannot** catch a route that
  accepts both methods and still destroys on GET. Only a real GET against a
  real record, with the store compared either side, catches that.
- **The Tax Invoice hard stop, from the route's side.** `cascade.py` refuses;
  what this file checks is that the route SAYS SO rather than half-deleting.
- **The two guards that were missing entirely** — Project never counted
  charges or attendance, Employee counted nothing at all.

⚠ The `client` fixture signs in as the seeded **Owner**. Every route here is in
  `auth.OWNER_ONLY`, so any other role would get a 403 and these tests would be
  measuring the gate rather than the route. The gate itself is proved in
  `tests/test_owner_only_delete.py`, which is where a non-Owner belongs.
"""

import pytest

from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

def _put(collection, rid, **fields):
    rec = {"id": rid, **fields}
    STORE.setdefault(collection, {})[rid] = rec
    return rec


# ⚠ `conftest._fresh_store()` clears the document collections but NOT
#   `projects`, `employees`, `charges`, `attendance`, `ra_bills`, `receipts`
#   or `purchase_orders` — it never needed to, because the suites that use
#   those plant ids of their own. This file plants FIXED ids in all of them
#   (`pr1`, `e1`, `dp1`…), so without this a project left carrying a charge by
#   one test refuses to delete in the next one and the failure reads as a bug
#   in the guard. Local rather than a conftest change: the leak is this file's.
_PLANTED = ("projects", "employees", "charges", "attendance",
            "ra_bills", "receipts", "purchase_orders", "purchases")


@pytest.fixture(autouse=True)
def _clear_planted():
    for key in _PLANTED:
        STORE.setdefault(key, {}).clear()
    yield
    for key in _PLANTED:
        STORE.setdefault(key, {}).clear()


def _ids():
    """
    Every record id in the store, by collection.

    ⚠ Sizes would be the wrong measure for a GET test: `/boq/delete/<id>`
      calls `ensure_demo_boq()` and `ensure_demo_specs()` on the way in, which
      legitimately ADD records. What must not happen is that anything
      disappears, so the claim is made over ids and in one direction.
    """
    return {k: set(v) for k, v in STORE.items() if isinstance(v, dict)}


def _assert_nothing_vanished(before):
    after = _ids()
    for collection, ids in before.items():
        missing = ids - after.get(collection, set())
        assert not missing, (
            f"a GET destroyed {collection}: {sorted(missing)}. The GET on a "
            f"delete route renders a confirmation and must write nothing — "
            f"ABOUT.md §7.9f.")


@pytest.fixture()
def chain(client):
    """
    One BOQ with the whole execution chain hanging off it, plus a separate
    quotation → proforma leg. Deliberately built by hand rather than through
    the forms: this file is about what DELETE does, and a fixture that went
    through six create routes would fail for reasons that are not this file's.
    """
    _put("boqs", "b1", ref="SF/BOQ/26-27/0090", project_name="Sify",
         site_location="Rabale", line_items=[], supersedes="")
    _put("ra_bills", "r1", boq_id="b1", ref="SF/RA/26-27/0090", ra_no=1,
         status="draft", claims=[])
    _put("receipts", "rc1", ra_id="r1", ref="SF/RCPT/26-27/0090", amount=100.0)
    _put("delivery_challans", "dc1", boq_id="b1", ref="SF/DC/26-27/0090")
    _put("measurements", "m1", boq_id="b1", ref="SF/MS/26-27/0090")
    _put("purchase_orders", "dp1", boq_id="b1", ref="SF/DPO/26-27/0090")
    _put("purchases", "p1", boq_id="b1", ref="SF/PO/26-27/0090",
         vendor_name="Acme", date="2026-09-01", line_items=[], status="draft")

    # ⚠ Fuller than the others on purpose: `view_quotation()` renders the whole
    #   A4 sheet and reads `grand_total` without a default, so a thin record
    #   raises a KeyError on the one test that loads that page.
    _put("quotations", "q1", ref="SF/QTN/26-27/0090", customer_name="Sify",
         date="2026-09-01", line_items=[], grand_total=1000.0, subtotal=1000.0,
         tax_type="exempt", tax_info={"total": 0.0}, status="draft",
         customer_address="", customer_gstin="", customer_state="")
    _put("proformas", "pf1", quotation_id="q1", ref="SF/PI/26-27/0090",
         customer_name="Sify", date="2026-09-01", line_items=[])
    return client


# ── The standing rule: a GET destroys nothing ───────────────────────────────
#
# One test per route, written out rather than parametrised over a list, because
# a parametrised sweep that silently skips a route it cannot build a record for
# reads as five passes and proves four things.

def test_a_get_on_boq_delete_destroys_nothing(chain):
    before = _ids()
    r = chain.get("/boq/delete/b1")
    assert r.status_code == 200
    _assert_nothing_vanished(before)
    assert "b1" in STORE["boqs"]


def test_a_get_on_quotation_delete_destroys_nothing(chain):
    before = _ids()
    r = chain.get("/quotation/delete/q1")
    assert r.status_code == 200
    _assert_nothing_vanished(before)
    assert "q1" in STORE["quotations"]


def test_a_get_on_proforma_delete_destroys_nothing(chain):
    before = _ids()
    r = chain.get("/proforma/delete/pf1")
    assert r.status_code == 200
    _assert_nothing_vanished(before)
    assert "pf1" in STORE["proformas"]


def test_a_get_on_purchase_delete_destroys_nothing(chain):
    before = _ids()
    r = chain.get("/purchase/delete/p1")
    assert r.status_code == 200
    _assert_nothing_vanished(before)
    assert "p1" in STORE["purchases"]


def test_a_get_on_invoice_cancel_changes_nothing(chain):
    """
    Cancelling destroys no record, so `_ids()` cannot catch a GET that acts.
    The thing that must not change is the invoice's own status.
    """
    _put("invoices", "ti1", proforma_id="pf1", ref="SF/TI/26-27/0090",
         date="2026-09-01", line_items=[], grand_total=1000.0,
         customer_name="Sify")
    r = chain.get("/invoice/cancel/ti1")
    assert r.status_code == 200
    assert STORE["invoices"]["ti1"].get("status") != "cancelled"
    assert "cancel_reason" not in STORE["invoices"]["ti1"]


# ── The BOQ cascade — the largest blast radius in the app ───────────────────

def test_deleting_a_boq_takes_its_whole_chain(chain):
    r = chain.post("/boq/delete/b1", follow_redirects=False)
    assert r.status_code in (301, 302)

    for collection, rid in (("boqs", "b1"), ("ra_bills", "r1"),
                            ("receipts", "rc1"), ("delivery_challans", "dc1"),
                            ("measurements", "m1"), ("purchase_orders", "dp1"),
                            ("purchases", "p1")):
        assert rid not in STORE.get(collection, {}), (
            f"{collection}/{rid} survived the BOQ delete — it hangs off the "
            f"BOQ and cascade.CASCADE_GRAPH says so")


def test_the_confirmation_names_what_it_is_about_to_destroy(chain):
    """
    A route that destroys something the page did not name is a defect. The
    count and the per-type breakdown both have to reach the HTML.
    """
    html = chain.get("/boq/delete/b1").get_data(as_text=True)
    assert "6 other records" in html
    for label in ("RA Bill", "Receipt", "Delivery Challan",
                  "Measurement Sheet", "Draft Purchase Order", "Purchase Order"):
        assert label in html, f"the confirmation page does not mention {label}"


def test_a_superseded_boq_is_refused(chain):
    """
    Not a cascade rule — a chain rule. The newer revision's `supersedes` points
    at this record, and `ra.revision_chain()` walks that link to total what has
    been claimed across the chain.
    """
    _put("boqs", "b2", ref="SF/BOQ/26-27/0090-R1", supersedes="b1",
         project_name="Sify", site_location="Rabale", line_items=[])
    r = chain.post("/boq/delete/b1", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "b1" in STORE["boqs"], "a superseded BOQ was deleted anyway"


# ── The Tax Invoice hard stop ───────────────────────────────────────────────

def _with_invoice():
    _put("invoices", "ti1", proforma_id="pf1", ref="SF/TI/26-27/0090",
         date="2026-09-01", line_items=[], grand_total=1000.0,
         customer_name="Sify")


def test_a_proforma_with_a_tax_invoice_cannot_be_deleted(chain):
    _with_invoice()
    chain.post("/proforma/delete/pf1", follow_redirects=False)
    assert "pf1" in STORE["proformas"], "a proforma under a tax invoice was deleted"
    assert "ti1" in STORE["invoices"], "the tax invoice was destroyed"


def test_a_quotation_is_blocked_two_hops_up_by_a_tax_invoice(chain):
    """
    The closure is quotation → proforma → invoice. The block has to be found by
    the WALK, not by a hand-written check at the quotation, or the next
    document added to the chain will not be covered by it.
    """
    _with_invoice()
    chain.post("/quotation/delete/q1", follow_redirects=False)
    assert "q1" in STORE["quotations"]
    assert "pf1" in STORE["proformas"], "the proforma was cascaded past the block"
    assert "ti1" in STORE["invoices"]


def test_the_blocked_confirmation_says_why_and_offers_no_button(chain):
    _with_invoice()
    html = chain.get("/quotation/delete/q1").get_data(as_text=True)
    assert "Tax Invoice" in html
    assert "consecutive" in html
    assert 'method="POST"' not in html, (
        "a blocked confirmation still drew a delete button — the page must "
        "not offer what the route will refuse")


def test_a_quotation_with_no_invoice_takes_its_proformas(chain):
    chain.post("/quotation/delete/q1", follow_redirects=False)
    assert "q1" not in STORE["quotations"]
    assert "pf1" not in STORE["proformas"], (
        "the proforma survived its quotation — a PI exists only because a "
        "quotation does")


# ── The Tax Invoice: cancel, never delete ───────────────────────────────────

def test_there_is_no_delete_route_for_a_tax_invoice(client):
    """
    The prohibition, asserted against the live url_map rather than trusted.
    A GST invoice number has to stay consecutive.
    """
    import app as app_module
    rules = [r.rule for r in app_module.app.url_map.iter_rules()
             if r.rule.startswith("/invoice/")]
    assert not any("delete" in r for r in rules), (
        f"a delete route appeared on the tax invoice: {rules}")


def test_cancelling_keeps_the_record_the_number_and_the_reason(chain):
    _with_invoice()
    chain.post("/invoice/cancel/ti1",
               data={"cancel_reason": "raised on the wrong customer",
                     "cancelled_on": "2026-09-23"},
               follow_redirects=False)
    ti = STORE["invoices"]["ti1"]
    assert ti["status"] == "cancelled"
    assert ti["ref"] == "SF/TI/26-27/0090", "the number was released"
    assert ti["cancel_reason"] == "raised on the wrong customer"
    assert ti["cancelled_on"] == "2026-09-23"


def test_a_cancellation_without_a_reason_is_refused(chain):
    """
    Six months later the only remaining question is why the number is missing
    from the run, and the reason is the only thing that will answer it.
    """
    _with_invoice()
    r = chain.post("/invoice/cancel/ti1", data={"cancel_reason": "  "})
    assert r.status_code == 200, "an empty reason should re-render, not redirect"
    assert STORE["invoices"]["ti1"].get("status") != "cancelled"


def test_a_cancelled_invoice_prints_marked(chain):
    _with_invoice()
    STORE["invoices"]["ti1"].update(status="cancelled",
                                    cancelled_on="2026-09-23",
                                    cancel_reason="duplicate")
    html = chain.get("/invoice/view/ti1").get_data(as_text=True)
    assert "CANCELLED" in html
    assert "lc-mark" in html, "the overprint watermark is missing"
    assert "not reissued" in html


def test_there_is_no_un_cancel(chain):
    _with_invoice()
    STORE["invoices"]["ti1"]["status"] = "cancelled"
    r = chain.get("/invoice/cancel/ti1", follow_redirects=False)
    assert r.status_code in (301, 302), (
        "the cancel page rendered for an already-cancelled invoice")


# ── The dangling-reference gaps this rollout closed ─────────────────────────

def test_deleting_a_draft_po_takes_the_order_it_was_converted_into(chain):
    """
    ABOUT.md §7's dangling-`draft_id` gap. Before 23 September 2026 the draft
    was popped alone and the real order kept pointing at it.
    """
    STORE["purchases"]["p1"]["draft_id"] = "dp1"
    chain.post("/po/delete/dp1", follow_redirects=False)
    assert "dp1" not in STORE["purchase_orders"]
    assert "p1" not in STORE["purchases"], (
        "the converted order survived its draft with a dangling draft_id")


def test_the_draft_po_confirmation_names_the_converted_order(chain):
    STORE["purchases"]["p1"]["draft_id"] = "dp1"
    html = chain.get("/po/delete/dp1").get_data(as_text=True)
    assert "Purchase Order" in html, (
        "the draft PO confirmation cascades into a real order without saying so")


def test_deleting_a_purchase_order_clears_the_drafts_back_link(chain):
    """
    The mirror image, and the one `cascade.py` deliberately cannot do:
    `converted_po_ids` is a LIST ON THE UPSTREAM RECORD, which is the
    documented exception to this app's "a reference is always an id field on
    the downstream record" rule. The graph walks downstream fields only.
    """
    STORE["purchases"]["p1"]["draft_id"] = "dp1"
    STORE["purchase_orders"]["dp1"]["converted_po_ids"] = ["p1", "p-other"]
    chain.post("/purchase/delete/p1", follow_redirects=False)
    assert "p1" not in STORE["purchases"]
    assert STORE["purchase_orders"]["dp1"]["converted_po_ids"] == ["p-other"], (
        "the draft still lists a converted order that no longer exists")


# ── The two master-data guards that were missing ────────────────────────────

def test_a_project_with_charges_cannot_be_deleted(client):
    """
    ⚠ Before 23 September 2026 `attached_boq_count()` was the WHOLE guard, so a
      project with a wages ledger and no BOQ deleted cleanly and left every
      charge pointing at a `project_id` that no longer resolved.
    """
    _put("projects", "pr1", name="Rabale")
    _put("charges", "c1", project_id="pr1", person="A", date="2026-09-01",
         taxable_amount=100, gst_amount=0)
    client.post("/projects/delete/pr1", follow_redirects=False)
    assert "pr1" in STORE["projects"], "a project with charges was deleted"


def test_a_project_with_attendance_cannot_be_deleted(client):
    _put("projects", "pr1", name="Rabale")
    _put("attendance", "a1", project_id="pr1", employee_id="e1",
         date="2026-09-01")
    client.post("/projects/delete/pr1", follow_redirects=False)
    assert "pr1" in STORE["projects"], "a project with attendance was deleted"


def test_a_project_with_nothing_attached_still_deletes(client):
    _put("projects", "pr1", name="Rabale")
    client.post("/projects/delete/pr1", follow_redirects=False)
    assert "pr1" not in STORE["projects"], (
        "the widened guard now refuses a project it should still allow")


def test_an_employee_with_attendance_cannot_be_deleted(client):
    """
    ⚠ There was NO guard here at all before 23 September 2026.
    """
    _put("employees", "e1", name="R. Kumar", code="E-1")
    _put("attendance", "a1", employee_id="e1", date="2026-09-01")
    client.post("/employee/delete/e1", follow_redirects=False)
    assert "e1" in STORE["employees"], "an employee with attendance was deleted"


def test_an_employee_with_nothing_against_them_still_deletes(client):
    _put("employees", "e1", name="R. Kumar", code="E-1")
    client.post("/employee/delete/e1", follow_redirects=False)
    assert "e1" not in STORE["employees"]


def test_the_employee_refusal_offers_deactivating_instead(client):
    _put("employees", "e1", name="R. Kumar", code="E-1")
    _put("attendance", "a1", employee_id="e1", date="2026-09-01")
    html = client.get("/employee/delete/e1").get_data(as_text=True)
    assert "Deactivate" in html
    assert "Delete this record" not in html, (
        "the page still offers a delete it will refuse")


# ── Master data is never cascaded into ──────────────────────────────────────

def test_no_master_collection_is_in_the_cascade_graph():
    """
    The scope rule, asserted rather than left to the module docstring: deleting
    a Project must never be able to destroy every BOQ raised under it.
    """
    import cascade
    masters = {"projects", "employees", "addresses", "specs", "products"}
    assert not (masters & set(cascade.CASCADE_GRAPH)), (
        "a master collection has been given cascade edges — deleting a "
        "register row must not destroy the documents that point at it")
    reached = {edge.collection
               for edges in cascade.CASCADE_GRAPH.values() for edge in edges}
    assert not (masters & reached), (
        "a cascade edge now points AT master data")


def test_the_quotation_view_hides_delete_when_an_invoice_sits_below(chain):
    """
    The button follows the route, two hops down.

    ⚠ A proforma under a quotation is NOT a reason to hide it — that cascades
      quite happily and the confirmation names it. A TAX INVOICE under that
      proforma is, because the route refuses outright and a control that
      offers a refusal teaches nothing.
    """
    html = chain.get("/quotation/view/q1").get_data(as_text=True)
    assert "quotation/delete/q1" in html, (
        "the Delete control is missing on a quotation that only has a "
        "proforma under it — that case cascades and is not refused")

    _with_invoice()
    html = chain.get("/quotation/view/q1").get_data(as_text=True)
    assert "quotation/delete/q1" not in html, (
        "the Delete control is still drawn on a quotation with a tax invoice "
        "below it, which the route refuses")
