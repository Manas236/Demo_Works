"""
Server-side template injection — the six "Group 1" modules.

`spec.py` and `boq.py` were fixed first and are guarded by
tests/test_hardening.py. This file is the same class of bug in the six modules
that matched that pattern exactly: every view escapes with `pipeline.esc()` /
`address._e()`, every one f-strings user text into element text, and every one
ended with `render_template_string()` on an already-finished string.

    proforma · invoice · purchase · address · settings · dashboard

`quotation.py` and `product.py` are deliberately NOT here. quotation.py builds
its pages with `.format()` and has attribute, `<script>` and option-text sinks
the one-line fix does not reach; product.py does not escape at all. Both need
their own pass — ABOUT.md §7.9d.

Everything here is driven through a **rendered page**. A test that greps the
module for `render_template_string` would pass against a module that had been
"fixed" by wrapping the same second parse in a helper, and would fail against a
module that reached the same safety a different way. What matters is what comes
back over HTTP.
"""

import pytest

import address
import pipeline as P
from store import STORE

# The marker brackets the payload so an assertion can tell "the braces reached
# the page untouched" from "something ate them". Braces are not HTML-significant
# and `esc()` deliberately does not escape them, so on a correct page the
# marker and the opening delimiter arrive adjacent and intact.
MARK = "SSTIMARK"


@pytest.fixture(autouse=True)
def _restore_settings():
    """
    The settings case pushes its payload onto `branding` through
    `apply_settings()`, which is process-global and reaches every letterhead in
    the app. Put the real identity back afterwards so a later test in the same
    session is not reading this one's leftovers.
    """
    import branding as B
    import settings as S

    saved = dict(STORE["settings"])
    yield
    STORE["settings"].clear()
    STORE["settings"].update(saved)
    B.apply_settings(S.load_saved())


def _secret() -> str:
    """The app's ACTUAL secret, not the literal in app.py's fallback."""
    import app as app_module
    return app_module.app.secret_key


# ── Record builders ────────────────────────────────────────────────────────
#
# Each returns the list of URLs that must survive the payload. The FIRST entry
# is the page the text is rendered on; the rest are pages that carry the same
# record and must not fall over because of it.


def _added(collection: str, before: set) -> str:
    """
    The id of the record this POST just wrote.

    Deliberately not `next(iter(STORE[c]))`. These builders run several times
    against one client, and once a collection is non-empty "the first key" is
    some earlier test's record — which reads as a *passing* injection test
    against a page that never carried the payload at all. The control test at
    the foot of this file caught exactly that.
    """
    new = set(STORE[collection]) - before
    assert len(new) == 1, f"expected 1 new {collection} record, got {len(new)}"
    return new.pop()

def _a_quotation() -> str:
    """A minimal but well-formed quotation — enough to raise a PI against."""
    import uuid
    qid = str(uuid.uuid4())
    q = {
        "id": qid, "ref": "QT-9001", "date": "2026-08-04",
        "account_name": "Test Contractor Pvt Ltd", "contact_person": "",
        "to": "Test Contractor Pvt Ltd\nMumbai", "bill_gstin": "",
        "bill_state": "Maharashtra", "ship_same": "on",
        "line_items": [{"type": "item", "name": "MS pipe", "part_no": "P-1",
                        "hsn": "73063090", "qty": 10.0, "unit": "Mtrs",
                        "price": 1000.0, "total": 10000.0, "depth": 0}],
        "subtotal": 10000.0, "tax_type": "exempt", "tax_info": {"total": 0.0},
        "grand_total": 10000.0, "total_qty": 10.0,
    }
    P.ensure_fields(q)
    STORE["quotations"][qid] = q
    return qid


def build_proforma(client, text):
    qid = _a_quotation()
    before = set(STORE["proformas"])
    r = client.post(f"/proforma/from/{qid}", data={
        "date": "2026-08-04", "advance_pct": "100", "notes": text})
    assert r.status_code == 302, "the PI was not created — check the form fields"
    pid = _added("proformas", before)
    return [f"/proforma/view/{pid}", "/proforma/"]


def build_invoice(client, text):
    qid = _a_quotation()
    before_pi = set(STORE["proformas"])
    assert client.post(f"/proforma/from/{qid}", data={
        "date": "2026-08-04", "advance_pct": "100"}).status_code == 302
    pid = _added("proformas", before_pi)

    before = set(STORE["invoices"])
    r = client.post(f"/invoice/from/{pid}", data={
        "date": "2026-08-04", "place_of_supply": "Maharashtra",
        "advance_received": "0", "notes": text})
    assert r.status_code == 302, "the tax invoice was not created"
    iid = _added("invoices", before)
    # The PI view page lists the invoices raised against it as .ti-chips, so it
    # carries this record too and has to survive it as well.
    return [f"/invoice/view/{iid}", "/invoice/", f"/proforma/view/{pid}"]


def build_purchase(client, text):
    address.ensure_demo_addresses()
    from product import ensure_demo_products
    ensure_demo_products()
    vendor = next(a for a in STORE["addresses"].values() if a.get("type") == "vendor")
    product = next(iter(STORE["products"]))

    before = set(STORE["purchases"])
    r = client.post("/purchase/create", data={
        "date": "2026-08-04", "vendor_id": vendor["id"], "status": "Draft",
        "tax_type": "exempt", "notes": text,
        "line_product_id": [product], "line_qty": ["2"], "line_rate": ["500"]})
    assert r.status_code == 302, "the purchase order was not created"
    poid = _added("purchases", before)
    return [f"/purchase/view/{poid}", "/purchase/"]


def build_address(client, text):
    # Seed first: every address route calls `ensure_demo_addresses()`, so on a
    # fresh store the POST writes seven records and the diff below cannot tell
    # which one is ours.
    address.ensure_demo_addresses()
    before = set(STORE["addresses"])
    r = client.post("/address/add", data={
        "label": f"{MARK} test", "type": "office", "contact_name": "",
        "company": text, "line1": "Unit 1", "line2": "", "landmark": "",
        "city": "Mumbai", "state": "Maharashtra", "pincode": "400001",
        "phone": "", "email": "", "gstin": ""})
    assert r.status_code == 302, "the address was not created"
    aid = _added("addresses", before)
    return [f"/address/edit/{aid}", "/address/"]


def build_settings(client, text):
    # Every other field posts blank, which means "not set" and falls back to the
    # branding.py default — see ABOUT.md §5. The autouse fixture puts the real
    # identity back afterwards.
    r = client.post("/settings/", data={"COMPANY_ADDR": text})
    assert r.status_code == 302, "the settings were not saved"
    return ["/settings/", "/"]


def build_dashboard(client, text):
    qid = _a_quotation()
    STORE["quotations"][qid]["account_name"] = text
    # Both panels that print an account name: "Recent quotations" always, and
    # "Needs attention" once the deal is overdue.
    STORE["quotations"][qid]["exp_closing"] = "2020-01-01"
    return ["/"]


BUILDERS = {
    "proforma":  build_proforma,
    "invoice":   build_invoice,
    "purchase":  build_purchase,
    "address":   build_address,
    "settings":  build_settings,
    "dashboard": build_dashboard,
}


# ═══ CLASS: server-side template injection via render_template_string ══════

@pytest.mark.parametrize("module", sorted(BUILDERS))
@pytest.mark.parametrize("payload", ["{{ config }}", "{{ 7*7 }}"])
def test_jinja_in_user_text_is_never_evaluated(client, module, payload):
    """
    `esc()` escapes `< > & " '` and deliberately not braces, so any page
    re-parsed by Jinja executes template syntax that arrived from a user. A
    clause reading `{{ config }}` printed the Flask config — SECRET_KEY with it.

    These views return finished HTML instead of handing it back to Jinja.
    """
    text = f"{MARK}{payload}{MARK}"
    urls = BUILDERS[module](client, text)

    for url in urls:
        html = client.get(url).get_data(as_text=True)
        assert _secret() not in html, f"{url} leaked SECRET_KEY"
        assert f"{MARK}49{MARK}" not in html, f"{url} evaluated {payload}"

    # And on the page that carries it, it survives as the literal text it is.
    html = client.get(urls[0]).get_data(as_text=True)
    assert f"{MARK}{{{{" in html, (
        f"{urls[0]} did not render {payload} literally — "
        f"something consumed the braces")


@pytest.mark.parametrize("module", sorted(BUILDERS))
def test_a_malformed_template_tag_cannot_500_the_page(client, module):
    """
    The denial-of-service half, and the worse one: `{% for x in y %}` raises a
    TemplateSyntaxError, the text is STORED, and none of these six modules has
    an edit route that could take it back out. One save used to break the page
    permanently for everybody.
    """
    urls = BUILDERS[module](client, "{% for x in y %}")
    for url in urls:
        assert client.get(url).status_code == 200, f"{url} broke on {'{% %}'}"


def test_the_stored_text_really_does_reach_the_page(client):
    """
    The control. Every assertion above is "the payload did NOT do something",
    which passes just as well against a page that dropped the field entirely.
    This proves the text is genuinely on the page being asserted about.
    """
    for module in sorted(BUILDERS):
        urls = BUILDERS[module](client, f"{MARK}-{module}-plain")
        html = client.get(urls[0]).get_data(as_text=True)
        assert f"{MARK}-{module}-plain" in html, (
            f"{module}: the payload never reached {urls[0]}, so the injection "
            f"tests above are vacuous")
