"""
No GET in this app destroys anything.

`/address/delete`, `/product/delete` and `/spec/delete` all used to delete on
GET, guarded only by a browser `confirm()`. That dialog is not a guard. It never
runs for:

- a **link-prefetching browser**, which fetches `href`s before you click them;
- a **crawler** or security scanner walking the site;
- a **chat client or mail scanner** unfurling a pasted URL;
- the **back button**, or a refresh of a page that was itself a redirect.

Each of those issues a plain GET, and each would have silently destroyed a
record. `ra.delete_ra()` already did it correctly — GET renders a confirmation
page, POST destroys — and all three now match that shape exactly.

    THE TEST THAT CANNOT BE OUTGROWN is `test_no_registered_route_destroys_on_get`.
    It walks the app's real URL map rather than a hand-written list, so a fourth
    delete route added later is covered the day it is registered, without anyone
    remembering to add it here.
"""

import pytest

import product as product_mod
import spec as spec_mod
from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(client):
    """The demo catalogue, address book and spec library, through the app."""
    client.get("/")                      # seeds products + addresses
    client.get("/spec/")                 # seeds the spec library
    yield


def _a_deletable_product() -> str:
    """A product not locked into any assembly — one the guard would allow."""
    return next(pid for pid in STORE["products"]
                if product_mod.can_delete_product(pid)[0])


def _a_child_product():
    """(child_id, parent_name) for a product an assembly depends on."""
    for pid, p in STORE["products"].items():
        for child in p.get("children") or []:
            return child["product_id"], p["name"]
    return None, None


# ═══ The sweep ═════════════════════════════════════════════════════════════

def test_no_registered_route_destroys_on_get(client, seeded):
    """
    Every delete route in the URL map accepts POST, and none is GET-only.

    Read off `app.url_map`, so this covers routes that do not exist yet. A
    GET-only delete route cannot be anything but a destructive GET.

    ⚠ **Read what this asserts, which is less than the name suggests: that every
      delete rule ACCEPTS POST.** It catches a GET-only delete route — the
      failure mode that actually existed — but it **cannot** catch a route that
      accepts both methods and still destroys on GET. Such a route passes here.

      The property is held per route by the four tests below and in
      `tests/test_ra_routes.py`, each of which issues a real GET and asserts the
      store is unchanged. Those are hand-written and do **not** extend to a
      fifth route automatically: **a new delete route must ship its own GET
      test.** ABOUT.md §7.9f carries that as a standing rule.
    """
    import app as app_module

    offenders = []
    for rule in app_module.app.url_map.iter_rules():
        if "delete" not in rule.rule.lower():
            continue
        methods = rule.methods or set()
        if "POST" not in methods:
            offenders.append(f"{rule.rule} accepts {sorted(methods - {'HEAD', 'OPTIONS'})}")

    assert not offenders, (
        "these delete routes cannot be POSTed to, so they must destroy on GET: "
        + "; ".join(offenders))


# ═══ Per route: GET destroys nothing, POST destroys ════════════════════════

def test_get_on_address_delete_destroys_nothing(client, seeded):
    aid = next(iter(STORE["addresses"]))
    before = dict(STORE["addresses"])

    r = client.get(f"/address/delete/{aid}")

    assert r.status_code == 200, "the GET must render a page, not redirect"
    assert STORE["addresses"] == before
    assert aid in STORE["addresses"]

    html = r.get_data(as_text=True)
    assert "This cannot be undone" in html
    assert 'method="POST"' in html
    assert "Keep it" in html


def test_post_on_address_delete_destroys(client, seeded):
    aid = next(iter(STORE["addresses"]))

    r = client.post(f"/address/delete/{aid}")

    assert r.status_code == 302
    assert aid not in STORE["addresses"]


def test_get_on_spec_delete_destroys_nothing(client, seeded):
    sid = next(iter(STORE["specs"]))
    before = dict(STORE["specs"])

    r = client.get(f"/spec/delete/{sid}")

    assert r.status_code == 200
    assert STORE["specs"] == before
    assert sid in STORE["specs"]

    html = r.get_data(as_text=True)
    assert "This cannot be undone" in html
    assert 'method="POST"' in html
    # The design note travels with the confirmation, since it is the thing a
    # user hesitating over this button actually needs to know.
    assert "BOQs written from it are unaffected" in html


def test_post_on_spec_delete_destroys(client, seeded):
    sid = next(iter(STORE["specs"]))

    r = client.post(f"/spec/delete/{sid}")

    assert r.status_code == 302
    assert sid not in STORE["specs"]


def test_get_on_product_delete_destroys_nothing(client, seeded):
    pid = _a_deletable_product()
    before = dict(STORE["products"])

    r = client.get(f"/product/delete/{pid}")

    assert r.status_code == 200
    assert STORE["products"] == before
    assert pid in STORE["products"]

    html = r.get_data(as_text=True)
    assert "This cannot be undone" in html
    assert 'method="POST"' in html


def test_post_on_product_delete_destroys(client, seeded):
    pid = _a_deletable_product()

    r = client.post(f"/product/delete/{pid}")

    assert r.status_code == 302
    assert pid not in STORE["products"]


# ═══ The guards that already existed still fire ════════════════════════════

def test_the_assembly_child_refusal_survives_on_post(client, seeded):
    """
    `/product/delete`'s integrity guard is unchanged — the one behaviour this
    conversion was most likely to drop.
    """
    child_id, parent_name = _a_child_product()
    assert child_id, "the seeded catalogue has no assembly to test with"

    r = client.post(f"/product/delete/{child_id}")

    assert r.status_code == 302
    assert child_id in STORE["products"], "an assembly child was deleted"
    assert "used in assembly" in r.headers["Location"].replace("+", " ").replace("%20", " ")


def test_the_assembly_child_refusal_also_fires_on_the_confirmation_page(client, seeded):
    """
    The refusal comes BEFORE the confirmation renders, so a locked product never
    shows a button that would fail. The reason is shown, not hidden — the same
    call `ra.delete_ra()` makes.
    """
    child_id, _parent = _a_child_product()

    r = client.get(f"/product/delete/{child_id}")

    assert r.status_code == 302
    assert child_id in STORE["products"]


def test_deleting_a_missing_record_still_redirects_with_a_reason(client, seeded):
    for url in ("/address/delete/nope", "/product/delete/nope", "/spec/delete/nope"):
        for method in ("get", "post"):
            r = getattr(client, method)(url)
            assert r.status_code == 302, f"{method.upper()} {url}"


# ═══ The links that used to fire them ══════════════════════════════════════

def test_no_list_page_still_relies_on_a_browser_confirm(client, seeded):
    """
    The `confirm()` dialogs are gone from the three delete controls.

    Leaving them would be harmless but dishonest: it would suggest the dialog is
    what protects the record, when the method is.
    """
    for url in ("/address/", "/product/"):
        html = client.get(url).get_data(as_text=True)
        assert "confirm('Delete" not in html, f"{url} still guards a delete with confirm()"

    sid = next(iter(STORE["specs"]))
    html = client.get(f"/spec/edit/{sid}").get_data(as_text=True)
    assert "return confirmDelete" not in html      # the call
    assert "function confirmDelete" not in html    # and its definition


def test_spec_delete_link_points_at_the_confirmation_page(client, seeded):
    sid = next(iter(STORE["specs"]))
    html = client.get(f"/spec/edit/{sid}").get_data(as_text=True)
    assert f"/spec/delete/{sid}" in html


# ═══ product.py stayed inside its blast radius ═════════════════════════════

def test_the_product_confirmation_page_is_not_jinja_rendered(client, seeded):
    """
    product.py is on the forbidden list (INTRODUCTION.md §7) because it has no
    output escaping and still renders through `render_template_string`. The one
    page added there is returned DIRECTLY, so a product name containing Jinja
    cannot execute — the new page adds no sink to a file full of them.
    """
    import uuid
    pid = str(uuid.uuid4())
    STORE["products"][pid] = {
        "id": pid, "name": "{{ 7*7 }}", "part_no": "{{ config }}", "hsn": "",
        "unit": "Nos", "base_price": 1.0, "description": "",
        "type": "standalone", "children": [],
    }

    html = client.get(f"/product/delete/{pid}").get_data(as_text=True)

    assert "49" not in html.split("<body")[1] or "{{ 7*7 }}" in html
    assert "SECRET_KEY" not in html
    # Escaped, not executed, and not raw either.
    assert "{{ 7*7 }}" in html or "&#34; 7*7 &#34;" in html
