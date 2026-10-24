"""
tests/test_owner_only_delete.py — the Owner-only gate on delete routes.

`auth.OWNER_ONLY` is a hardcoded rule layered on top of the permission
registry: an endpoint in it is refused to anyone who is not Owner, even a
Director who holds the underlying `*.delete` permission via `/roles`. This
file proves that layering both ways — Director refused, Owner let through the
gate — and pins which endpoints are (and are deliberately not) in the set.

⚠ **The set is no longer every destroy route** (21 October 2026,
CLIENT_CHANGES.md §0 fifty-second block). Five moved to
`auth.PERMISSION_ONLY_DESTROYS` — the four transaction documents and the draft
work order that mirrors the PO — and are gated by their `*.delete` permission
alone. So this file now proves **three** things rather than two:

1. the layering still works where it still applies (`ra.delete_ra`: Director
   holds `ra.delete`, Director is refused anyway);
2. the carve-out really carved — a Director reaches all five, which is the
   whole point of the block and the thing that was silently false before it;
3. **every** delete route in the live `url_map` is in exactly one of the three
   sets below, so a route added later cannot land in neither and inherit a
   tier by accident.
"""

import pytest

import auth
from store import STORE


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


def _director(client):
    auth.ensure_builtin_roles()
    existing = auth.find_user("owner-only-director")
    if existing:
        del STORE["users"][existing["id"]]
    user = auth.create_user("owner-only-director", "Director Person",
                            "owner-only-director-password", ["role-director"],
                            created_by="test")
    _as(client, user)
    return user


# ── The registry itself ─────────────────────────────────────────────────────

def test_owner_only_covers_exactly_the_true_destroy_routes():
    """
    Pinned rather than derived: every endpoint here really does destroy a
    document (`STORE[...].pop`/`del`), and the ones sharing a `*.delete`
    permission but not destroying a document themselves — archiving an
    address, removing one attachment file — are deliberately excluded. See
    the docstring beside `auth.OWNER_ONLY`.
    """
    assert auth.OWNER_ONLY == {
        # ⚠ `invoice.cancel_invoice` is the odd one and is here on purpose: it
        # does NOT destroy a record — the invoice keeps its number, its figures
        # and its printability — but it is the ONLY way to withdraw a tax
        # invoice, because a GST series has to stay consecutive and there is no
        # `/invoice/delete` to put here instead. Withdrawing a document is the
        # same order of act as destroying one, so it takes the same tier, and
        # the fifty-second block left it here for exactly that reason while
        # four of its 23 September siblings left.
        # `test_the_tax_invoice_has_no_edit_route_to_gate` holds the no-delete
        # half from the other side.
        "invoice.cancel_invoice",
        "ra.delete_ra",
        "receipt.delete_receipt",
        "po_draft.delete_po",
        "challan.delete_dc",
        "measurement.delete_ms",
        "charge.delete_charge",
        "employee.delete_employee",
        "attendance.delete_attendance",
        "project.delete_project",
        "spec.delete_spec",
        "product.delete_product",
        "address.delete_address",
    }
    excluded = {
        "address.archive_address", "address.unarchive_address",
        "attachment.delete_charge", "attachment.delete_receipt",
    }
    assert not (excluded & auth.OWNER_ONLY)


def test_the_carve_out_is_exactly_the_five_the_forty_seventh_block_named():
    """
    Pinned so that a sixth name needs a decision. `PERMISSION_ONLY_DESTROYS`
    is read by nothing at runtime — it is the written-down half of an absence
    from `OWNER_ONLY` — so only this assertion stands between it and drift.
    """
    assert auth.PERMISSION_ONLY_DESTROYS == {
        "boq.delete_boq",
        "quotation.delete_quotation",
        "proforma.delete_proforma",
        "purchase.delete_purchase",
        # Not an independent decision: §0's forty-first block, ruling I, fixes
        # a draft work order's access as exactly the PO's, per action.
        # `tests/test_work_orders.py` asserts the pairing from its own side.
        "workorder.delete_wo",
    }


def test_the_two_sets_are_disjoint():
    """
    An endpoint in both would mean the carve-out never happened while
    appearing to, and `_gate()` reads `OWNER_ONLY` — so `OWNER_ONLY` would
    quietly win.
    """
    overlap = auth.OWNER_ONLY & auth.PERMISSION_ONLY_DESTROYS
    assert not overlap, f"in both sets, so the carve-out is a no-op: {overlap}"


# The two delete-path routes that destroy no document. Kept here rather than in
# auth.py because nothing in the application needs to know: they are ordinary
# permission-gated routes and the only question they raise is this test's.
NOT_A_DESTROY = {
    "attachment.delete_charge",
    "attachment.delete_receipt",
}


def test_every_delete_route_in_the_url_map_is_classified():
    """
    The sweep the `OWNER_ONLY` docstring promises, and the guard the
    fifty-second block made necessary.

    Before that block every destroy route was Owner-only, so a new one that
    nobody classified was caught by `_gate()`'s default-deny the moment it was
    missing from `ROUTE_PERMISSIONS`, and its tier was not a question — there
    was one answer. Now there are two, and an unclassified delete route gets
    the looser of them by default. This fails instead.

    ⚠ It walks the path, not the permission, so it also covers a destroy route
      that somebody classifies under an unrelated permission.
    """
    import app as app_module

    found = {r.endpoint for r in app_module.app.url_map.iter_rules()
             if "delete" in r.rule.lower()}
    classified = auth.OWNER_ONLY | auth.PERMISSION_ONLY_DESTROYS | NOT_A_DESTROY
    unclassified = sorted(found - classified)

    assert not unclassified, (
        f"delete route(s) in no set: {unclassified}. Decide the tier on "
        f"purpose: `auth.OWNER_ONLY` (Owner tier on top of the permission), "
        f"`auth.PERMISSION_ONLY_DESTROYS` (the permission alone, which needs a "
        f"§0 block), or this file's NOT_A_DESTROY if it destroys no document.")


def test_every_owner_only_endpoint_is_actually_registered():
    """
    A stale endpoint name in OWNER_ONLY (a route renamed or removed) would
    silently stop protecting anything. Caught here rather than by a route
    that turns out to be reachable by everyone.
    """
    import app as app_module
    registered = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    missing = auth.OWNER_ONLY - registered
    assert not missing, f"OWNER_ONLY names endpoints not in the url_map: {missing}"


# ── The gate itself, on a representative sample ─────────────────────────────

def test_a_director_is_refused_on_get_and_post_though_the_permission_is_held(client):
    """
    Director holds `ra.delete` per the access matrix (§ACCESS_MATRIX.md) —
    this is not "no permission", it is "permission held, Owner tier not".
    """
    director = _director(client)
    assert "ra.delete" in auth.permissions_of(director), (
        "test assumes Director holds ra.delete — if that grant changes, "
        "this test needs a different non-Owner role that still holds it")

    for method in ("GET", "POST"):
        r = client.open("/ra/delete/zz-no-such-id", method=method)
        assert r.status_code == 403, (
            f"{method} /ra/delete/<id> should refuse a non-Owner holder of "
            f"ra.delete, got {r.status_code}")


# ── The carve-out, proved from the Director's side ──────────────────────────
#
# The five routes and the permission each one is gated by on its own. `/wo` is
# `purchase.delete` and not a `wo.*` id of its own — ruling I again.
CARVE_OUT_URLS = [
    ("/boq/delete/zz-no-such-id",       "boq.delete"),
    ("/quotation/delete/zz-no-such-id", "quotation.delete"),
    ("/proforma/delete/zz-no-such-id",  "proforma.delete"),
    ("/purchase/delete/zz-no-such-id",  "purchase.delete"),
    ("/wo/delete/zz-no-such-id",        "purchase.delete"),
]


@pytest.mark.parametrize("url,perm", CARVE_OUT_URLS)
def test_a_director_now_clears_the_gate_on_the_five_carved_out_routes(client, url, perm):
    """
    The fifty-second block's whole point, and the state that was silently
    false between 23 September and 21 October 2026: the grant at
    `/roles/edit/<id>` now does something.

    A 403 here means the carve-out did not take — either the endpoint is back
    in `OWNER_ONLY`, or `_gate()` grew a second Owner check. The record does
    not exist, so the view itself may redirect; anything but 403 proves the
    gate let the Director through.
    """
    director = _director(client)
    assert perm in auth.permissions_of(director), (
        f"test assumes Director holds {perm} — if that grant is withdrawn, "
        f"this route is unreachable for a reason this test is not measuring")

    r = client.get(url)
    assert r.status_code != 403, (
        f"GET {url} refused a Director holding {perm}; the 21 October "
        f"carve-out is not in effect")


@pytest.mark.parametrize("url,perm", CARVE_OUT_URLS)
def test_the_carved_out_routes_still_refuse_a_role_without_the_permission(client, url, perm):
    """
    The other half, and the one that matters for the blast radius: taking the
    Owner tier off these routes left them gated, not open. HR holds no
    `*.delete` of any kind, so each of the five must still refuse.
    """
    auth.ensure_builtin_roles()
    existing = auth.find_user("owner-only-hr")
    if existing:
        del STORE["users"][existing["id"]]
    hr = auth.create_user("owner-only-hr", "HR Person",
                          "owner-only-hr-password", ["role-hr"],
                          created_by="test")
    assert perm not in auth.permissions_of(hr)
    _as(client, hr)

    for method in ("GET", "POST"):
        r = client.open(url, method=method)
        assert r.status_code == 403, (
            f"{method} {url} let through a role with no {perm}, got "
            f"{r.status_code}")


def test_an_owner_clears_the_gate(client):
    """
    `client` signs in as the seeded Owner (tests/conftest.py). The gate must
    not be the thing that stops them — a 403 here would mean OWNER_ONLY is
    refusing the one tier it exists to allow. (The record does not exist, so
    the *view* may still redirect with a "not found" message — anything but
    403 proves the gate let it through.)
    """
    r = client.get("/ra/delete/zz-no-such-id")
    assert r.status_code != 403


def test_archiving_an_address_is_not_owner_gated(client):
    """
    The deliberate exclusion, proved rather than just asserted in the set
    test above: archiving is POST-only and not a destroy, and a Director
    holding `address.delete` must still be able to do it.
    """
    director = _director(client)
    assert "address.delete" in auth.permissions_of(director)
    r = client.post("/address/archive/zz-no-such-id")
    assert r.status_code != 403
