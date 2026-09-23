"""
cascade.py — the shared dependent-record graph for delete
=============================================================
No routes. A data-only registry of which STORE collections reference which,
plus the two operations every delete route needs: "what would this also
destroy" and "destroy it and everything it found".

Why this exists rather than 19 hand-written per-type walkers: every existing
dependency guard in this app (`address.references_of()`,
`project.attached_boq_count()`, `product.can_delete_product()`,
`ra.can_delete()`) is a one-off, hand-written against `STORE[...]` directly —
there is no ORM and no foreign-key graph to introspect (CLIENT_CHANGES.md
§1.3: a reference is always an id field on the downstream record, never a
list on the upstream one). This module is the first attempt at one place
that says what points at what, in the same "one-way trick" every leaf module
already uses: it reads `STORE[...]` directly and never imports the modules
that own those collections, so the acyclic-import rule holds. It sits where
`pipeline.py` sits — above the leaf modules, imported by their routes, never
importing back.

**Scope is deliberately narrower than "everything that references anything".**
Two different relationships exist in this app and only one of them belongs
here:

- A **transactional chain** record only exists *because* its parent does — a
  Receipt has no reason to exist without the RA Bill it pays, a Delivery
  Challan without the BOQ it moved material against. These are what
  `CASCADE_GRAPH` walks, and deleting the parent is defined to mean deleting
  the whole subtree.
- **Master/reference data** (Address, Employee, Project, Spec, Product) is
  pointed *at* by documents, not produced from them. Deleting a Project must
  not be able to cascade into deleting every BOQ and RA bill raised under it
  as a side effect of tidying up a master record. Those guards stay exactly
  where they already live (`address.references_of()`,
  `project.attached_boq_count()`, `product.can_delete_product()`) and this
  module does not touch them.

**The one hard stop: a Tax Invoice.** A GST invoice number has to stay
consecutive — deleting one, even as a side effect of deleting something three
hops upstream, leaves an unaccounted gap in a legally consecutive series.
There is no delete route for `invoices` anywhere in this app (see
`invoice.py` — only a cancel/void flow). So the walk below treats reaching
the `invoices` collection as a hard stop: the whole operation is refused, not
partially cascaded, the instant one is found anywhere in the closure.
"""

from typing import NamedTuple

from store import STORE
import attachment


class Edge(NamedTuple):
    collection: str        # STORE key of the dependent collection
    fields: tuple           # field name(s) on the dependent record; OR-matched
    label: str              # human label for the confirmation page
    parent_type: str | None = None   # attachments only: also require this parent_type


class CascadeBlocked(Exception):
    """Raised by delete_cascade() when a Tax Invoice sits in the closure."""
    def __init__(self, blocker: dict):
        self.blocker = blocker
        super().__init__(
            f"Cannot delete: Tax Invoice {blocker.get('id')} exists downstream.")


# Doc type (STORE collection of the record being deleted) -> its direct
# dependents. The walk below follows this transitively, so a two-hop parent
# (BOQ -> RA Bill -> Receipt) does not need its own entry for the second hop.
CASCADE_GRAPH: dict[str, list[Edge]] = {
    "quotations": [
        Edge("proformas", ("quotation_id",), "Proforma Invoice"),
    ],
    "proformas": [
        # The hard stop. Listed as an edge (not specially skipped) so the walk
        # discovers it in the normal course of recursion and blocks there.
        Edge("invoices", ("proforma_id",), "Tax Invoice"),
    ],
    "boqs": [
        Edge("ra_bills", ("boq_id",), "RA Bill"),
        Edge("delivery_challans", ("boq_id",), "Delivery Challan"),
        Edge("measurements", ("boq_id",), "Measurement Sheet"),
        Edge("purchase_orders", ("boq_id",), "Draft Purchase Order"),
        Edge("purchases", ("boq_id",), "Purchase Order"),
    ],
    "ra_bills": [
        Edge("receipts", ("ra_id",), "Receipt"),
        Edge("merged_ras", ("supply_ra_id", "installation_ra_id"), "Merged RA"),
    ],
    "purchase_orders": [
        # A draft PO's own converted-to-real-PO back-link (`purchases.draft_id`).
        # Closes the existing gap where deleting a draft left its converted PO
        # with a dangling `draft_id` — see ABOUT.md §7 gap on po_draft.py.
        Edge("purchases", ("draft_id",), "Purchase Order"),
    ],
    "charges": [
        Edge("attachments", ("parent_id",), "Attachment", parent_type="charge"),
    ],
    "receipts": [
        Edge("attachments", ("parent_id",), "Attachment", parent_type="receipt"),
    ],
}

# Collections whose records need more than a plain STORE pop on delete.
_ATTACHMENT_PARENTS = {"charges": "charge", "receipts": "receipt"}


def _matches(rec: dict, edge: Edge, target_id: str) -> bool:
    if edge.parent_type is not None and str(rec.get("parent_type") or "") != edge.parent_type:
        return False
    return any(str(rec.get(f) or "") == target_id for f in edge.fields)


def _walk(doc_type: str, doc_id: str, visited: set):
    """
    Depth-first generator over every transitive dependent of (doc_type, doc_id).

    Yields dicts: {"collection", "id", "label", "rec"}. Raises CascadeBlocked
    the instant a Tax Invoice is found anywhere in the closure. `visited`
    guards against visiting the same (collection, id) twice on a diamond —
    e.g. a Purchase Order that is both a direct BOQ dependent and reachable
    again via the Draft PO it was converted from.
    """
    for edge in CASCADE_GRAPH.get(doc_type, []):
        collection = STORE.get(edge.collection) or {}
        for rid, rec in list(collection.items()):
            if not isinstance(rec, dict) or not _matches(rec, edge, doc_id):
                continue
            key = (edge.collection, rid)
            if key in visited:
                continue
            visited.add(key)
            if edge.collection == "invoices":
                raise CascadeBlocked({
                    "collection": "invoices", "id": rid, "label": edge.label,
                })
            yield {"collection": edge.collection, "id": rid, "label": edge.label, "rec": rec}
            yield from _walk(edge.collection, rid, visited)


def impact_of(doc_type: str, doc_id: str) -> dict:
    """
    Every record that deleting (doc_type, doc_id) would also destroy.

    Returns {"blocked": None, "items": [...]} normally, or
    {"blocked": {"collection", "id", "label"}, "items": []} the instant a Tax
    Invoice is found anywhere in the closure — the caller should refuse the
    whole delete rather than show a partial preview.
    """
    items = []
    try:
        for item in _walk(doc_type, doc_id, set()):
            items.append(item)
    except CascadeBlocked as exc:
        return {"blocked": exc.blocker, "items": []}
    return {"blocked": None, "items": items}


def summarize(items: list) -> dict:
    """{"RA Bill": 3, "Receipt": 7, ...} — for a one-line confirmation summary."""
    counts: dict = {}
    for it in items:
        counts[it["label"]] = counts.get(it["label"], 0) + 1
    return counts


def _destroy_one(collection: str, rid: str) -> None:
    parent_type = _ATTACHMENT_PARENTS.get(collection)
    if parent_type:
        attachment.delete_for_parent(parent_type, rid)
    (STORE.get(collection) or {}).pop(rid, None)


def delete_cascade(doc_type: str, doc_id: str) -> list:
    """
    Deletes (doc_type, doc_id) and every transitive dependent.

    Refuses via CascadeBlocked if a Tax Invoice sits anywhere in the closure
    — callers should check `impact_of()` first and show the block message
    rather than let this raise, but it re-checks itself so it is never
    correct to call without a fresh impact check immediately before.

    Deletes dependents before the record they depend on (reverse discovery
    order), then the record itself. Returns the list of destroyed dependents
    (not including doc_id itself) for a post-delete summary.
    """
    report = impact_of(doc_type, doc_id)
    if report["blocked"] is not None:
        raise CascadeBlocked(report["blocked"])

    for item in reversed(report["items"]):
        _destroy_one(item["collection"], item["id"])

    _destroy_one(doc_type, doc_id)
    return report["items"]
