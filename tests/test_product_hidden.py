"""
The product catalogue is HIDDEN — behind a toggle, from everybody, reversibly.

11 September 2026, CLIENT_CHANGES.md §0, the twenty-seventh block. The owner
is not sure the twelve seeded catalogue items have anything to do with the
client, so the module is switched off for everyone — an Owner included — until
he is. Because he is not sure, the hide is a **toggle**
(`auth.HIDDEN_BLUEPRINTS`), not a deletion: the three `product.*` permissions
and the four registry rows are untouched, every role keeps exactly the grants
it had, and un-hiding is one line.

Two halves, and both are needed:

- **Hidden** (the shipped state): every product route refuses every role on
  both verbs, nothing is destroyed, no card, no link, no count; the roles
  editor shows the grants disabled and cannot add or remove them; the access
  matrix marks them `⊘`.
- **Un-hidden** (`catalogue_unhidden`): today's behaviour exactly — the day
  the toggle is emptied, everything comes back as it was. The existing
  product-page tests run under that fixture and are what prove `product.py`
  itself; this file proves the toggle.

`product.py` is not edited by the pass that hid it and stays fully frozen
(INTRODUCTION.md §7) — asserted here too, because a hide that needed an edit
to the module it hides would not be a hide.
"""

import pathlib
import re
import subprocess

import pytest

import auth
import dashboard
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

ROLES = ["owner", "director", "operation-head", "hr", "sales-manager",
         "purchase-manager", "accountant"]

PRODUCT_PERMS = {"product.view", "product.create", "product.delete"}
PRODUCT_ENDPOINTS = {"product.list_products", "product.view_product",
                     "product.add_product", "product.delete_product"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _user(slug: str) -> dict:
    name = f"hid-{slug}"
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="hidden-test")


def _as(client, slug: str) -> None:
    auth.ensure_builtin_roles()
    user = _user(slug)
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


def _seed_products(client) -> str:
    """Seed the catalogue through the dashboard and return one product id."""
    client.get("/")
    assert STORE["products"], "the dashboard visit did not seed the catalogue"
    return next(iter(STORE["products"]))


def _product_urls(pid: str) -> list:
    """(method, url) for every product route, both verbs where they answer."""
    return [
        ("GET",  "/product/"),
        ("GET",  f"/product/view/{pid}"),
        ("GET",  "/product/add"),
        ("POST", "/product/add"),
        ("GET",  f"/product/delete/{pid}"),
        ("POST", f"/product/delete/{pid}"),
    ]


ADD_FORM = {"name": "Smuggled item", "part_no": "SMG-1", "hsn": "8424",
            "unit": "Nos", "base_price": "1", "description": "", "type": "standalone"}


# ══ 0. The shipped configuration, pinned ═══════════════════════════════════

def test_the_shipped_toggle_hides_exactly_the_product_blueprint():
    """
    One entry, `product`, and nothing else. A second blueprint landing here
    by accident would switch a module off for the client with no test going
    red anywhere else — every other assertion in this file is about `product`.
    """
    assert auth.HIDDEN_BLUEPRINTS == {"product"}
    assert auth.blueprint_hidden("product")
    assert not auth.blueprint_hidden("spec")
    assert auth.is_hidden_endpoint("product.list_products")
    assert not auth.is_hidden_endpoint("spec.list_specs")
    assert not auth.is_hidden_endpoint(None)
    assert not auth.is_hidden_endpoint("")


def test_the_permissions_and_registry_rows_are_untouched():
    """
    The whole point of a toggle. The permissions are still in the catalogue,
    the endpoints are still classified, and the builtin roles still carry the
    grants — so un-hiding brings every role back exactly as it was.
    """
    assert PRODUCT_PERMS <= set(auth.PERMISSIONS)
    assert PRODUCT_ENDPOINTS <= set(auth.ROUTE_PERMISSIONS)
    assert {auth.ROUTE_PERMISSIONS[e] for e in PRODUCT_ENDPOINTS} == PRODUCT_PERMS
    owner_perms = set(auth.BUILTIN_ROLES["owner"][1])
    assert PRODUCT_PERMS <= owner_perms, "the Owner role lost a product grant"


def test_hidden_permissions_is_derived_from_the_registry():
    """
    Exactly the three product permissions, and no other — derived by walking
    `ROUTE_PERMISSIONS`, so a permission split across a hidden and a visible
    blueprint would stay live rather than take a reachable page with it.
    """
    assert auth.hidden_permissions() == PRODUCT_PERMS


def test_product_py_is_not_edited_by_the_hide():
    """
    The module is frozen (INTRODUCTION.md §7) and the hide lives entirely in
    `auth.py`. `eff0034` is the baseline the freeze test in
    `tests/test_nav_user_chip.py` already uses.
    """
    try:
        r = subprocess.run(["git", "diff", "--name-only", "eff0034", "--", "product.py"],
                           cwd=REPO, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available here")
    if r.returncode != 0:
        pytest.skip("this checkout does not reach eff0034")
    assert not r.stdout.strip(), "product.py was edited — the hide must live in auth.py"


# ══ 1. Hidden: every route, every role, both verbs, nothing destroyed ═══════

@pytest.mark.parametrize("slug", ROLES)
def test_every_product_route_refuses_every_role_on_both_verbs(client, slug):
    """
    An Owner holds every permission and is refused exactly as the Accountant
    is: the refusal comes BEFORE the permission is consulted. The page says the
    module is switched off, so the reader is not sent to ask for a grant they
    already hold.
    """
    pid = _seed_products(client)
    _as(client, slug)
    before = {k: dict(v) for k, v in STORE["products"].items()}

    for method, url in _product_urls(pid):
        data = ADD_FORM if url.endswith("/add") else None
        r = client.open(url, method=method, data=data)
        assert r.status_code == 403, f"{slug}: {method} {url} answered {r.status_code}"
        body = r.get_data(as_text=True)
        assert "switched off" in body, f"{slug}: {method} {url} did not say why"
        assert "HIDDEN_BLUEPRINTS" in body

    assert STORE["products"] == before, f"{slug}: a refused request changed the catalogue"
    assert pid in STORE["products"], "a refused delete removed the record"
    assert not any(p.get("part_no") == "SMG-1" for p in STORE["products"].values()), (
        "a refused add still wrote a product")


def test_a_stranger_is_bounced_to_login_not_told_what_is_installed(anon_client):
    """
    Hidden beats PUBLIC — but a stranger gets the ordinary login bounce, not a
    page naming a module. A refusal page that says what is installed tells
    somebody with no session what to come back for.
    """
    r = anon_client.get("/product/")
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("Location", "")


def test_the_refusal_is_logged_with_its_own_reason(client):
    _seed_products(client)
    _as(client, "owner")
    client.get("/product/")
    newest = auth.REFUSAL_LOG[0]
    assert newest["endpoint"] == "product.list_products"
    assert newest["reason"] == "blueprint hidden"


@pytest.mark.parametrize("slug", ROLES)
def test_can_reach_mirrors_the_gate_for_every_role(client, slug):
    """
    `can_reach()` is what draws cards and links; `_gate()` is what refuses.
    They are two functions and must agree — for a hidden endpoint the answer
    is False for everybody, Owner included.
    """
    auth.ensure_builtin_roles()
    user = _user(slug)
    for endpoint in PRODUCT_ENDPOINTS:
        assert not auth.can_reach(endpoint, user), f"{slug} is offered {endpoint}"
    # and a control, so an implementation returning False for everything
    # would not pass: the Owner can still reach the spec library.
    if slug == "owner":
        assert auth.can_reach("spec.list_specs", user)


# ══ 2. Hidden: no card, no link, no count ═══════════════════════════════════

@pytest.mark.parametrize("slug", ROLES)
def test_no_role_sees_a_catalogue_card_or_link(client, slug):
    _seed_products(client)
    _as(client, slug)
    html = client.get("/").get_data(as_text=True)
    titles = re.findall(r'<div class="card-title">(.*?)</div>', html)
    assert "Product Catalogue" not in titles, f"{slug} sees the catalogue card"
    assert 'href="/product/' not in html, f"{slug}'s dashboard links into the catalogue"


def test_the_dashboard_counts_no_catalogue_items_while_hidden(client):
    """
    `_metrics()` reads the same toggle: the `p_*` figures are nil while the
    module is hidden, however many records the collection holds. A count of
    records nobody can open is not a figure to show anybody.
    """
    _seed_products(client)
    assert len(STORE["products"]) >= 12
    with client.application.test_request_context("/"):
        m = dashboard._metrics()
    assert (m["p_total"], m["p_assembly"], m["p_support"]) == (0, 0, 0)


def test_the_spec_card_is_unaffected(client):
    """A control: hiding one module does not take its neighbour with it."""
    _seed_products(client)
    _as(client, "owner")
    html = client.get("/").get_data(as_text=True)
    assert "Spec Library" in re.findall(r'<div class="card-title">(.*?)</div>', html)


# ══ 3. Hidden: the roles editor cannot add or remove a hidden grant ═════════

def _role_editor(client, slug: str) -> str:
    auth.ensure_builtin_roles()
    _as(client, "owner")
    return client.get(f"/roles/edit/role-{slug}").get_data(as_text=True)


def _label_of(html: str, pid: str) -> str:
    """The one `<label>…</label>` that carries this permission's code."""
    at = html.index(f"<code>{pid}</code>")
    start = html.rindex("<label", 0, at)
    end = html.index("</label>", at)
    return html[start:end]


def test_the_roles_editor_draws_hidden_grants_disabled_and_says_why(client):
    html = _role_editor(client, "director")
    for pid in PRODUCT_PERMS:
        # the box exists, is disabled, and carries NO name= — it posts nothing
        block = _label_of(html, pid)
        assert 'disabled' in block, f"{pid} is offered as a live checkbox"
        assert 'name="permissions"' not in block, f"{pid}'s box would post a value"
        assert "module hidden" in block, f"{pid} does not say the module is hidden"
    # the Director holds all three, so all three are drawn CHECKED — the stored
    # state is shown, not blanked
    director = STORE["roles"]["role-director"]["permissions"]
    assert PRODUCT_PERMS <= set(director)
    for pid in PRODUCT_PERMS:
        assert "checked" in _label_of(html, pid), f"{pid} is held but drawn unticked"
    # a control: a visible permission is still an ordinary, named checkbox
    spec_block = _label_of(html, "spec.view")
    assert 'name="permissions"' in spec_block and "disabled" not in spec_block


def test_saving_a_role_keeps_its_hidden_grants_exactly(client):
    """
    A disabled checkbox posts nothing. Without `_merge_hidden_grants()` every
    save of every role would silently drop `product.*` — and un-hiding the
    module weeks later would find nobody holding it. The POST here omits the
    three entirely, exactly as a browser would.
    """
    auth.ensure_builtin_roles()
    _as(client, "owner")
    role = STORE["roles"]["role-director"]
    before = sorted(role["permissions"])
    visible = [p for p in before if p not in PRODUCT_PERMS]

    r = client.post("/roles/edit/role-director", data={"permissions": visible})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:300]
    assert sorted(role["permissions"]) == before, (
        "saving the role with the hidden boxes absent from the POST changed "
        "its grants — the hidden ones must ride through from the record")


def test_a_hand_made_post_cannot_add_a_hidden_grant(client):
    """
    HR holds no `product.*`. Posting `product.view` onto it must not confer
    it: the editor refuses to offer the grant, so a crafted request must not
    be able to make it.
    """
    auth.ensure_builtin_roles()
    _as(client, "owner")
    role = STORE["roles"]["role-hr"]
    assert not (PRODUCT_PERMS & set(role["permissions"]))
    posted = list(role["permissions"]) + ["product.view"]
    r = client.post("/roles/edit/role-hr", data={"permissions": posted})
    assert r.status_code in (302, 303)
    assert "product.view" not in role["permissions"]


def test_a_hand_made_post_cannot_remove_a_hidden_grant(client):
    """The mirror: the Director's three grants survive a POST that lists none."""
    auth.ensure_builtin_roles()
    _as(client, "owner")
    role = STORE["roles"]["role-director"]
    visible = [p for p in role["permissions"] if p not in PRODUCT_PERMS]
    client.post("/roles/edit/role-director", data={"permissions": visible})
    assert PRODUCT_PERMS <= set(role["permissions"])


def test_a_new_role_starts_with_no_hidden_grant(client):
    """It never held one, so there is nothing to carry through."""
    auth.ensure_builtin_roles()
    _as(client, "owner")
    r = client.post("/roles/create", data={"name": "Hidden-grant probe",
                                           "permissions": ["spec.view", "product.view"]})
    assert r.status_code in (302, 303)
    made = next(r_ for r_ in STORE["roles"].values() if r_["name"] == "Hidden-grant probe")
    assert made["permissions"] == ["spec.view"]


def test_merge_hidden_grants_is_the_rule_stated_once():
    """The helper, on its own, so the two POST tests above are not the only proof."""
    assert auth._merge_hidden_grants(["spec.view"], ["product.view", "boq.view"]) == \
        ["product.view", "spec.view"]
    assert auth._merge_hidden_grants(["spec.view", "product.create"], []) == ["spec.view"], (
        "a posted hidden id must not survive the merge — _posted_permissions() "
        "already drops it and the merge must not resurrect it")


# ══ 4. The access matrix marks them, rather than showing grants nobody can use

def test_the_access_matrix_marks_hidden_grants():
    text = (REPO / "docs" / "ACCESS_MATRIX.md").read_text(encoding="utf8")
    for pid in PRODUCT_PERMS:
        row = next(line for line in text.splitlines() if f"`{pid}` |" in line and "<br/>" in line)
        assert "module hidden" in row, f"{pid}'s row is not marked hidden"
        assert "·" not in row and "§" not in row, (
            f"{pid}'s row still shows a live grant mark: {row}")
        assert "⊘" in row
    assert "HIDDEN_BLUEPRINTS = ['product']" in text


# ══ 5. Un-hidden: today's behaviour exactly ═════════════════════════════════

@pytest.mark.usefixtures("catalogue_unhidden")
def test_emptying_the_toggle_brings_the_catalogue_back_exactly(client):
    """
    The one-line reversal, exercised. With the set emptied: the routes open,
    the card is drawn, nothing is derived as hidden, the roles editor offers
    the boxes live, and — the part the merge exists for — every grant is
    still there to come back to.
    """
    import product as product_mod   # read only — the module is frozen

    _seed_products(client)
    # a product no assembly depends on, so the delete confirmation renders
    # rather than bouncing with the integrity refusal (a 302, and correct)
    pid = next(p for p in STORE["products"] if product_mod.can_delete_product(p)[0])
    _as(client, "owner")

    assert auth.hidden_permissions() == set()
    for endpoint in PRODUCT_ENDPOINTS:
        assert auth.can_reach(endpoint, auth.current_user() or _user("owner"))

    assert client.get("/product/").status_code == 200
    assert client.get(f"/product/view/{pid}").status_code == 200
    assert client.get("/product/add").status_code == 200
    assert client.get(f"/product/delete/{pid}").status_code == 200

    html = client.get("/").get_data(as_text=True)
    assert "Product Catalogue" in re.findall(r'<div class="card-title">(.*?)</div>', html)
    with client.application.test_request_context("/"):
        assert dashboard._metrics()["p_total"] == len(STORE["products"])

    editor = client.get("/roles/edit/role-director").get_data(as_text=True)
    block = _label_of(editor, "product.view")
    assert 'name="permissions"' in block and "disabled" not in block
    assert "module hidden" not in editor


@pytest.mark.usefixtures("catalogue_unhidden")
def test_un_hidden_a_save_can_remove_a_product_grant_again(client):
    """
    Today's behaviour: with the module visible, unticking the box removes the
    grant. The merge only freezes grants while the module is hidden.
    """
    auth.ensure_builtin_roles()
    _as(client, "owner")
    role = STORE["roles"]["role-director"]
    visible = [p for p in role["permissions"] if p not in PRODUCT_PERMS]
    client.post("/roles/edit/role-director", data={"permissions": visible})
    assert not (PRODUCT_PERMS & set(role["permissions"]))


def test_the_fixture_restores_the_toggle(client):
    """
    A test that emptied the set and did not put it back would leave every
    later test in the process running un-hidden. Run after the two above in
    file order; asserts the shipped state is back.
    """
    assert auth.HIDDEN_BLUEPRINTS == {"product"}


# ══ 6. Snapshots are untouched ══════════════════════════════════════════════

def test_an_existing_quotation_with_catalogue_lines_still_renders(client):
    """
    Every quotation written before the hide carries catalogue-shaped
    `line_items` and `selections`. They are snapshots (ABOUT.md §3) and the
    hide reads none of them — the document renders exactly as it did.
    """
    import pipeline as P

    _seed_products(client)
    pid = next(iter(STORE["products"]))
    p = STORE["products"][pid]
    q = {
        "id": "q-hidden-snapshot", "ref": "QT-9901", "date": "2026-09-01",
        "account_name": "Snapshot Customer", "contact_person": "", "to": "Snapshot Customer",
        "tax_type": "cgst_sgst", "cgst_rate": 9.0, "sgst_rate": 9.0, "igst_rate": 18.0,
        "vat_rate": 5.0,
        "tax_info": {"CGST": 90.0, "SGST": 90.0, "total": 180.0,
                     "cgst_rate": 9.0, "sgst_rate": 9.0},
        "subtotal": 1000.0, "grand_total": 1180.0, "total_qty": 1.0,
        "selections": [{"pid": pid, "qty": 1, "price": 1000.0, "show_price": True,
                        "components": []}],
        "line_items": [{"type": "item", "name": p["name"], "part_no": p["part_no"],
                        "hsn": p.get("hsn", ""), "qty": 1.0, "unit": p["unit"],
                        "price": 1000.0, "total": 1000.0, "depth": 0}],
    }
    P.ensure_fields(q)
    STORE["quotations"][q["id"]] = q
    r = client.get(f"/quotation/view/{q['id']}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert P.esc(p["name"]) in body
    assert P.esc(p["part_no"]) in body
