"""
Every page in this app is the same page.

`dashboard.BASE_STYLES` and `dashboard._nav()` are what make that true, and
nothing enforced it — a module could render its own `<style>` block, its own
header and its own layout, look plausible on its own, and be visibly a
different application the moment somebody clicked through to it. Two of them
did: `/client/` and `/po/` shipped with a hand-rolled `.page-container` /
`.page-head` / `.client-header` layout, none of which exists anywhere else in
this repo, and `/po/print` loaded `QUOTATION_STYLES` without `VIEW_DOC_STYLES`
so the document it was printing had no sheet under it at all.

This file is the sweep that would have caught both. It walks **`app.url_map`**
rather than a hand-written list, so a module added later is checked the day it
is registered rather than the day somebody notices.

What it deliberately does not check: that two pages look *identical*. Modules
layer their own stylesheet after `BASE_STYLES` and should — `RA_STYLES`,
`PURCHASE_STYLES` and `BOQ_STYLES` all do. The property is that they layer
**after the shared one**, not instead of it.
"""

import pytest

from store import STORE


# Rules that legitimately render no app chrome, each with its reason. A page
# added later is checked unless it is named here, and naming one is a decision
# somebody has to write down.
NO_CHROME = {
    "/static/<path:filename>": "no /static folder exists; assets are data URIs",
    # The print-only routes. `/boq/print` set this shape: the document alone
    # behind a `.no-print` action bar, because the nav is furniture and the
    # sheet is the deliverable. They still load the shared stylesheet, which is
    # the half this file checks for them.
    "/po/print/<id>":  "print-only: the document alone, /boq/print's shape",
    "/boq/print/<id>": "print-only: the document alone",
}

# The screen routes the previous two passes added. Listed explicitly as well as
# swept, so that deleting one from the app is a red test rather than a quietly
# smaller sweep.
NEW_PAGES = ["/client/", "/po/"]


@pytest.fixture()
def populated(client):
    """Enough of a store that every page has something to render."""
    client.get("/boq/")
    client.get("/settings/")
    import address
    address.ensure_demo_addresses()
    bid = next(b for b, rec in STORE["boqs"].items() if not rec.get("supersedes"))
    yield {"boq": bid}


def _screen_urls(app_module, ids):
    """Every parameterless GET rule, plus the id-taking ones we can fill."""
    out = []
    for rule in sorted(app_module.app.url_map.iter_rules(), key=lambda r: r.rule):
        if "GET" not in rule.methods or rule.rule in NO_CHROME:
            continue
        if rule.arguments:
            continue          # covered by test_entity_fallbacks.py's own sweep
        out.append(rule.rule + ids.get(rule.rule, ""))
    return out


def test_every_screen_page_carries_the_shared_nav(populated, client):
    """
    `_nav()` is the only surface genuinely on every page, which is why both of
    the app's standing warnings ride on it: the amber settings dot, and the red
    persistence strip that means nothing is being saved. A page that draws its
    own header instead loses both and looks fine doing it.
    """
    import app as app_module
    ids = {"/ra/create": f"?boq={populated['boq']}&leg=supply",
           "/po/create": f"?boq={populated['boq']}"}

    for url in _screen_urls(app_module, ids):
        r = client.get(url)
        assert r.status_code == 200, f"{url} did not render"
        html = r.get_data(as_text=True)
        assert '<nav>' in html and 'class="nav-brand"' in html, (
            f"{url} does not render dashboard._nav(). Import it rather than "
            f"drawing a header — the persistence strip and the settings dot "
            f"both ride on it.")


def test_every_page_layers_its_css_after_the_shared_stylesheet(populated, client):
    """
    `BASE_STYLES` carries the reset, the nav, `.card`, `.btn`, `.alert`, the
    footer and the 580px breakpoint. A page that skips it and writes its own
    is a second design system.
    """
    import app as app_module
    ids = {"/ra/create": f"?boq={populated['boq']}&leg=supply",
           "/po/create": f"?boq={populated['boq']}"}

    for url in _screen_urls(app_module, ids):
        html = client.get(url).get_data(as_text=True)
        # A marker unique to BASE_STYLES rather than the constant itself: the
        # test should fail on "this page has no shared stylesheet", not on
        # "somebody edited a rule in it".
        assert ".nav-brand" in html, f"{url} does not load BASE_STYLES"


def test_the_printed_pages_load_the_shared_document_sheet(populated, client):
    """
    The other half. A print route may drop the nav — that is what `.no-print`
    and `/boq/print` established — but it may not drop the A4 sheet, or it
    prints a document with no frame, no letterhead and no print rules.

    `/po/print` did exactly that: `QUOTATION_STYLES` without `VIEW_DOC_STYLES`,
    so `.doc-outer` and `.page-frame` had no rules behind them at all.
    """
    import po_draft
    import address
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    lines = [li for li in STORE["boqs"][populated["boq"]]["line_items"]
             if not li.get("is_header")][:2]
    import json
    r = client.post(f"/po/create?boq={populated['boq']}", data={
        "date": "2026-08-15", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"],
                                          "qty": "", "pcs": ""} for li in lines]})})
    assert r.status_code == 302
    pid = next(iter(STORE["purchase_orders"]))

    for url in (f"/po/print/{pid}", f"/boq/print/{populated['boq']}"):
        html = client.get(url).get_data(as_text=True)
        assert ".page-frame" in html, f"{url} has no A4 sheet behind it"
        # The action bar is `no-print` — a class token, so it may be combined
        # with another (`screen-acts no-print`) and still be the same thing.
        assert "no-print" in html, f"{url} prints its own screen chrome"

    STORE["purchase_orders"].clear()


@pytest.mark.parametrize("path", NEW_PAGES)
def test_the_new_registers_are_reachable_from_the_dashboard(populated, client, path):
    """
    Not "the route exists" — **the user can get to it without typing a URL.**
    The module strip on `/` is this app's launcher; the nav carries only
    Settings, by design (ABOUT.md §5).
    """
    home = client.get("/").get_data(as_text=True)
    assert f'href="{path}"' in home, (
        f"{path} is not on the dashboard's module strip, so the only way to "
        f"reach it is to know the URL.")


def test_no_page_uses_a_browser_confirm_dialog(populated, client):
    """
    ABOUT.md §7.9f: `confirm()` is not a guard. It never runs for a
    link-prefetching browser, a crawler, a chat client unfurling a pasted URL,
    or the back button — each of which issues a plain GET. Destructive routes
    render a confirmation PAGE and mutate only inside the POST branch.

    Asserted over the rendered output rather than the source, because the sink
    that matters is the one the browser receives.
    """
    import app as app_module
    ids = {"/ra/create": f"?boq={populated['boq']}&leg=supply",
           "/po/create": f"?boq={populated['boq']}"}

    for url in _screen_urls(app_module, ids):
        html = client.get(url).get_data(as_text=True)
        assert "confirm(" not in html, (
            f"{url} carries a browser confirm() dialog. Render a confirmation "
            f"page and destroy only in the POST branch — ABOUT.md §7.9f.")
