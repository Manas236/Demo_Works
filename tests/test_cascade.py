"""
tests/test_cascade.py — the dependency-graph walk and cascade delete.

Pure STORE tests, no Flask/`client` involved — `cascade.py` is data-layer
logic with no route of its own, and the routes that will call it (Phase 2/3
of the universal-delete feature) get their own per-route tests once they
exist. This file is what proves the walk itself is correct: the transitive
closure, the diamond-dedup, and the one hard rule — a Tax Invoice anywhere
in the closure blocks the whole delete rather than letting it cascade past.
"""

import pytest

from store import STORE

import cascade


COLLECTIONS = (
    "quotations", "proformas", "invoices", "purchases", "purchase_orders",
    "boqs", "ra_bills", "receipts", "merged_ras", "measurements",
    "delivery_challans", "charges", "attachments",
)


@pytest.fixture(autouse=True)
def fresh_store():
    for key in COLLECTIONS:
        STORE.setdefault(key, {}).clear()
    yield
    for key in COLLECTIONS:
        STORE.setdefault(key, {}).clear()


def _put(collection, rid, **fields):
    rec = {"id": rid, **fields}
    STORE.setdefault(collection, {})[rid] = rec
    return rec


def test_boq_cascade_collects_the_full_chain():
    _put("boqs", "boq-1")
    _put("ra_bills", "ra-1", boq_id="boq-1")
    _put("receipts", "rcpt-1", ra_id="ra-1")
    _put("delivery_challans", "dc-1", boq_id="boq-1")
    _put("measurements", "ms-1", boq_id="boq-1")
    _put("purchase_orders", "draft-1", boq_id="boq-1")
    _put("purchases", "po-1", boq_id="boq-1")

    report = cascade.impact_of("boqs", "boq-1")

    assert report["blocked"] is None
    found = {(it["collection"], it["id"]) for it in report["items"]}
    assert found == {
        ("ra_bills", "ra-1"), ("receipts", "rcpt-1"),
        ("delivery_challans", "dc-1"), ("measurements", "ms-1"),
        ("purchase_orders", "draft-1"), ("purchases", "po-1"),
    }
    assert cascade.summarize(report["items"])["RA Bill"] == 1
    assert cascade.summarize(report["items"])["Receipt"] == 1


def test_boq_cascade_delete_removes_everything_and_only_that():
    _put("boqs", "boq-1")
    _put("boqs", "boq-2")  # a second, unrelated BOQ — must survive
    _put("ra_bills", "ra-1", boq_id="boq-1")
    _put("receipts", "rcpt-1", ra_id="ra-1")
    _put("delivery_challans", "dc-1", boq_id="boq-1")
    _put("delivery_challans", "dc-2", boq_id="boq-2")  # unrelated — must survive

    destroyed = cascade.delete_cascade("boqs", "boq-1")

    assert {("ra_bills", "ra-1"), ("receipts", "rcpt-1"),
            ("delivery_challans", "dc-1")} == {
        (it["collection"], it["id"]) for it in destroyed}
    assert "boq-1" not in STORE["boqs"]
    assert "boq-2" in STORE["boqs"]
    assert "dc-2" in STORE["delivery_challans"]
    assert STORE["ra_bills"] == {}
    assert STORE["receipts"] == {}
    assert STORE["delivery_challans"] == {"dc-2": STORE["delivery_challans"]["dc-2"]}


def test_a_draft_po_converted_to_a_real_po_is_not_double_counted():
    """
    A diamond: the real PO is reachable both directly off the BOQ (`boq_id`)
    and via the draft PO it was converted from (`draft_id`). The visited set
    must dedup on (collection, id), not on the path that found it — this is
    the exact gap ABOUT.md flags for `po_draft.delete_po()` today (deleting a
    draft never checked `converted_po_ids`, leaving the real PO's `draft_id`
    dangling); cascade.py is the fix.
    """
    _put("boqs", "boq-1")
    _put("purchase_orders", "draft-1", boq_id="boq-1")
    _put("purchases", "po-1", boq_id="boq-1", draft_id="draft-1")

    report = cascade.impact_of("boqs", "boq-1")

    po_hits = [it for it in report["items"]
               if it["collection"] == "purchases" and it["id"] == "po-1"]
    assert len(po_hits) == 1

    destroyed = cascade.delete_cascade("boqs", "boq-1")
    assert sum(1 for it in destroyed if it["collection"] == "purchases") == 1
    assert STORE["purchases"] == {}


def test_merged_ra_matches_either_leg():
    _put("boqs", "boq-1")
    _put("ra_bills", "ra-supply", boq_id="boq-1")
    _put("ra_bills", "ra-install", boq_id="boq-1")
    _put("merged_ras", "m-1", supply_ra_id="ra-supply", installation_ra_id="ra-install")

    report = cascade.impact_of("boqs", "boq-1")
    merged_hits = [it for it in report["items"] if it["collection"] == "merged_ras"]
    assert len(merged_hits) == 1, "one merged record referencing both legs must be counted once"

    cascade.delete_cascade("boqs", "boq-1")
    assert STORE["merged_ras"] == {}


def test_quotation_cascades_to_proforma_when_no_invoice_exists():
    _put("quotations", "q-1")
    _put("proformas", "pi-1", quotation_id="q-1")

    report = cascade.impact_of("quotations", "q-1")
    assert report["blocked"] is None
    assert [it["collection"] for it in report["items"]] == ["proformas"]

    cascade.delete_cascade("quotations", "q-1")
    assert STORE["quotations"] == {}
    assert STORE["proformas"] == {}


def test_a_tax_invoice_anywhere_downstream_blocks_the_whole_delete():
    """
    The one hard rule: a GST invoice number must stay consecutive, so nothing
    may cascade-delete a Tax Invoice, however many hops upstream the delete
    started. Quotation -> Proforma -> Tax Invoice must refuse at the
    Quotation, not silently skip the invoice and delete the rest.
    """
    _put("quotations", "q-1")
    _put("proformas", "pi-1", quotation_id="q-1")
    _put("invoices", "ti-1", proforma_id="pi-1")

    report = cascade.impact_of("quotations", "q-1")
    assert report["blocked"] == {
        "collection": "invoices", "id": "ti-1", "label": "Tax Invoice"}
    assert report["items"] == []

    with pytest.raises(cascade.CascadeBlocked):
        cascade.delete_cascade("quotations", "q-1")

    # Nothing was touched — a blocked delete must be all-or-nothing.
    assert "q-1" in STORE["quotations"]
    assert "pi-1" in STORE["proformas"]
    assert "ti-1" in STORE["invoices"]


def test_deleting_a_proforma_directly_is_blocked_by_its_own_invoice():
    _put("proformas", "pi-1")
    _put("invoices", "ti-1", proforma_id="pi-1")

    report = cascade.impact_of("proformas", "pi-1")
    assert report["blocked"]["id"] == "ti-1"

    with pytest.raises(cascade.CascadeBlocked):
        cascade.delete_cascade("proformas", "pi-1")
    assert "pi-1" in STORE["proformas"]


def test_charge_cascade_deletes_its_attachments():
    _put("charges", "ch-1")
    _put("attachments", "att-1", parent_type="charge", parent_id="ch-1")
    _put("attachments", "att-2", parent_type="receipt", parent_id="rcpt-9")

    report = cascade.impact_of("charges", "ch-1")
    assert [it["id"] for it in report["items"]] == ["att-1"]

    cascade.delete_cascade("charges", "ch-1")
    assert "att-1" not in STORE["attachments"]
    assert "att-2" in STORE["attachments"], "a receipt's attachment must not be touched by a charge delete"
    assert STORE["charges"] == {}


def test_a_record_with_no_dependents_reports_empty():
    _put("boqs", "boq-lonely")
    report = cascade.impact_of("boqs", "boq-lonely")
    assert report == {"blocked": None, "items": []}
    assert cascade.delete_cascade("boqs", "boq-lonely") == []
    assert STORE["boqs"] == {}
