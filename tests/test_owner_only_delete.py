"""
tests/test_owner_only_delete.py — the Owner-only gate on delete routes.

`auth.OWNER_ONLY` is a hardcoded rule layered on top of the permission
registry: an endpoint in it is refused to anyone who is not Owner, even a
Director who holds the underlying `*.delete` permission via `/roles`. This
file proves that layering both ways — Director refused, Owner let through the
gate — and pins which endpoints are (and are deliberately not) in the set.
"""

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
