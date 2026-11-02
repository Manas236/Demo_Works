"""
"Edit issued invoice" — `invoice.edit_issued`, 2 November 2026
(CLIENT_CHANGES.md §0 block of that date, Part 3, Manas's ruling).

Correcting a tax invoice after it has been issued — the standalone one, an RA
bill's and a merged set's — is its own permission. Owner + Director hold it by
default; it is a tick on the Director's permissions page; nobody else has it
until an Owner ticks it. `purchase@`'s role (Purchase Manager) is refused by
default — even when it is also given `invoice.create`.
"""

import pytest

import auth
from store import STORE
from test_invoice_edit import _form, _ti


def _user(name, role_ids):
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", role_ids,
                            created_by="perm-test")


def _as(client, user):
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = user["id"]


@pytest.fixture()
def ti(client):
    auth.ensure_builtin_roles()
    STORE["invoices"].clear()
    return _ti()


def test_the_permission_is_in_the_catalogue_and_on_owner_and_director_only():
    assert auth.PERMISSIONS["invoice.edit_issued"][0] == "Edit issued invoice"
    holders = sorted(slug for slug, (_n, perms) in auth.BUILTIN_ROLES.items()
                     if "invoice.edit_issued" in perms)
    assert holders == ["director", "owner"]


def test_the_three_after_issue_routes_are_gated_by_it():
    for ep in ("invoice.edit_invoice", "ra.edit_text", "merged_ra.edit_text"):
        assert auth.ROUTE_PERMISSIONS[ep] == "invoice.edit_issued", ep


def test_purchase_role_cannot_edit_an_issued_invoice_by_default(client, ti, monkeypatch):
    role = STORE["roles"]["role-purchase-manager"]
    assert "invoice.edit_issued" not in role["permissions"]
    # Even with the right to RAISE one and to see them, the edit is refused.
    # (`monkeypatch` puts the stored role back: roles outlive a test.)
    monkeypatch.setitem(role, "permissions",
                        sorted(set(role["permissions"]) | {"invoice.view", "invoice.create"}))
    purchase = _user("purchase@", ["role-purchase-manager"])
    _as(client, purchase)
    assert client.get("/invoice/edit/te1").status_code in (302, 403)
    r = client.post("/invoice/edit/te1", data=_form(ti, notes="hacked"))
    assert r.status_code in (302, 403)
    assert STORE["invoices"]["te1"]["notes"] == ""
    view = client.get("/invoice/view/te1").get_data(as_text=True)
    assert "/invoice/edit/te1" not in view, "no button for a refusal"


def test_a_director_edits_an_issued_invoice(client, ti):
    _as(client, _user("dir@", ["role-director"]))
    r = client.post("/invoice/edit/te1", data=_form(ti, notes="Director's fix"))
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert STORE["invoices"]["te1"]["notes"] == "Director's fix"


def test_it_is_a_tick_on_the_directors_permissions_page(client, ti):
    page = client.get("/roles/edit/role-director").get_data(as_text=True)
    assert 'value="invoice.edit_issued"' in page and "Edit issued invoice" in page
    assert 'value="invoice.edit_issued" checked' in page or \
        ('value="invoice.edit_issued"' in page and "checked" in
         page[page.index('value="invoice.edit_issued"'):][:80])


def test_an_owner_can_tick_it_onto_another_role(client, ti, monkeypatch):
    role = STORE["roles"]["role-sales-manager"]
    monkeypatch.setitem(role, "permissions", role["permissions"] + ["invoice.edit_issued"])
    _as(client, _user("sales@", ["role-sales-manager"]))
    r = client.post("/invoice/edit/te1", data=_form(ti, notes="Sales fix"))
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert STORE["invoices"]["te1"]["notes"] == "Sales fix"
