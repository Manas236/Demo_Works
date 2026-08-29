"""
User text must reach the page ESCAPED — asserted on the rendered bytes.

### Why this file exists, and why it did not before Phase 3B

Before access control there were no sessions, so a stored `<script>` in a
product name was a defacement: annoying, visible, and confined to whoever typed
it. Phase 3B put a session cookie in front of every page. The same payload is
now a **session-hijack against whoever reads the record** — an Owner opening
the catalogue runs the author's script with the Owner's cookie — and that
defeats the access layer the same phase shipped.

CLIENT_CHANGES-2.md says so directly, under "Security items promoted by this
phase": *"a stored XSS lets one user hijack another's session and approve their
own submissions"*. It names `product.py` and `quotation.py`; those were where
the spec pointed and not where the bug stopped. This file sweeps **every route
in `app.url_map`** so the next one is caught by enumeration rather than by
somebody remembering.

### What it asserts, and why "absent" is not good enough

Three separate claims, and they fail for different reasons:

* **The payload is present.** `test_the_sweep_really_did_reach_the_pages` is
  the control. Every assertion below is "X is NOT in the body", which passes
  perfectly against a page that rendered nothing, a 302, or a fixture that
  never wired the payload up. Without this control the whole file is theatre.

* **The payload is present ESCAPED — not stripped.** Asserting only that
  `<script>` is absent would pass against code that silently deletes the
  characters, and this repo's first principle is that the client's imperfect
  data must **survive rather than be repaired** (INTRODUCTION.md §9). A
  customer legitimately called `Smith & Sons <Bombay>` must print, intact,
  as `Smith &amp; Sons &lt;Bombay&gt;`.

* **The braces are not executed.** `P.esc` escapes `< > & " '` and deliberately
  **not** `{` or `}`, so escaping alone does not close server-side template
  injection. A value reading `{{ config['SECRET_KEY'] }}` used to print this
  application's signing key — which is session forgery, i.e. the whole access
  layer. That is ABOUT.md §7 gap 9d, and `_page()` in `product.py` and
  `quotation.py` is what closed it.

### The payloads

Five characters and two shapes, chosen because each breaks a different context:

| payload | what it breaks if unescaped |
|---|---|
| `<script>alert(1)</script>` | element content |
| `"` | a double-quoted attribute |
| `'` | a single-quoted attribute |
| `&` | entity context — and it is the one that proves stripping is not escaping |
| `<img src=x onerror=...>` | element content, with no `<script>` tag to grep for |
| `</title><script>…` | the `<title>` element, which is RCDATA — a `<script>` INSIDE it does not run, but `</title>` ends it |
| `</script>` inside JSON | a `<script>` block carrying `json.dumps` output |
| `{{ config[…] }}` | a second Jinja parse (`render_template_string`) |

The `</title>` one is not hypothetical padding: it is how this file's sibling
found that `branding.page_title()` passed a record's `ref` through raw on nine
routes.
"""

import re

import pytest

import branding as B
import test_entity_fallbacks as EF
from store import STORE


# ── The payloads ───────────────────────────────────────────────────────────
#
# `MARK` is a plain-ASCII sentinel so a hit can be attributed to a field, and
# so the control test can prove the payload genuinely reached the page even
# when every dangerous character has been escaped away.

MARK = "XSSPROBE"

# The stored payload. Every character that has to be escaped, plus the two
# tag shapes and the title breakout, in one string.
PAYLOAD = (
    MARK
    + "<script>alert(1)</script>"
    + '"'
    + "'"
    + "&"
    + "<img src=x onerror=alert(2)>"
    + "</title><script>alert(3)</script>"
)

# What the payload must look like once it has been escaped. `html.escape` with
# quote=True — which is what `pipeline.esc()` is — produces exactly this.
ESCAPED = (
    MARK
    + "&lt;script&gt;alert(1)&lt;/script&gt;"
    + "&quot;"
    + "&#x27;"
    + "&amp;"
    + "&lt;img src=x onerror=alert(2)&gt;"
    + "&lt;/title&gt;&lt;script&gt;alert(3)&lt;/script&gt;"
)

# The raw fragments that must never appear. Each is a separate assertion so a
# failure names which context leaked rather than just "something did".
FORBIDDEN = {
    "a <script> element":      "<script>alert(1)</script>",
    "an onerror image":        "<img src=x onerror=alert(2)>",
    "a </title> breakout":     "</title><script>alert(3)</script>",
}

# Keys that must NOT be poisoned. Ids are looked up, compared and put into
# `url_for`, so a payload in one produces a 404 sweep rather than an escaping
# check; the others are structural and drive branching.
DO_NOT_POISON = {
    "id", "line_id", "product_id", "ra_id", "boq_id", "project_id",
    "quotation_id", "proforma_id", "invoice_id", "draft_id", "vendor_id",
    "consignee_id", "address_id", "user_id", "role_ids", "permissions",
    "password_hash", "norm_name", "type", "status", "username", "builtin",
    # B6 (29 Aug 2026). `created_by` holds a user id and is compared against the
    # session's id by `approval.can_approve()` — the creator guard. Poisoning it
    # would not test an escaping sink (it never reaches HTML); it would silently
    # make every record look as though somebody else raised it, and the guard
    # would stop refusing on the pages this sweep walks. `approval_status` is a
    # closed vocabulary like `status` beside it, for the same reason.
    "created_by", "approval_status", "role",
}

_LOOKS_LIKE_AN_ID = re.compile(r"[0-9a-fA-F-]{8,}\Z")


def _poison(node) -> int:
    """Append `PAYLOAD` to every free-text string in a record tree."""
    hit = 0
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key in DO_NOT_POISON:
                continue
            if isinstance(value, str):
                if value and not _LOOKS_LIKE_AN_ID.match(value):
                    node[key] = value + PAYLOAD
                    hit += 1
            else:
                hit += _poison(value)
    elif isinstance(node, list):
        for value in node:
            if isinstance(value, (dict, list)):
                hit += _poison(value)
    return hit


POISONED_COLLECTIONS = (
    "products", "specs", "boqs", "ra_bills", "receipts", "quotations",
    "proformas", "invoices", "purchases", "purchase_orders",
    "delivery_challans", "projects", "charges", "addresses", "settings",
)


@pytest.fixture()
def hostile(populated_store, client):
    """
    The whole store, with a payload in every free-text field, plus a hostile
    company identity pushed through `branding.apply_settings()`.

    The identity half is not decoration and cannot be done by writing
    `STORE["settings"]`: `/settings` saves and then calls
    `B.apply_settings(overrides)`, and the letterhead reads the module globals
    rather than the store. Poisoning the store alone leaves every printed
    document untested — which is exactly how this sink survived until now.
    """
    fields = 0
    for name in POISONED_COLLECTIONS:
        fields += _poison(STORE.get(name, {}))

    saved = {key: B.DEFAULTS[key] for key in B.SETTINGS_KEYS}
    B.apply_settings({k: v + PAYLOAD for k, v in saved.items()})
    try:
        yield {"fields": fields, "urls": EF._urls(populated_store)}
    finally:
        # Put the identity back. These are module globals, so a test that left
        # them hostile would corrupt the letterhead for every later test in the
        # session — including the print goldens, which hash it.
        B.apply_settings({})


# One record in every collection, and an id for every parameterised rule.
#
# Borrowed rather than rebuilt. `test_entity_fallbacks.populated` already
# constructs exactly the store this file needs — a quotation, a proforma, a tax
# invoice, a purchase order, two RA bills, a receipt, a draft PO, a challan, a
# project, a charge and a spare user — and its `_urls()` helper **fails** on any
# parameterised rule that is neither exercised nor listed in its `SKIP`. That
# guard is the reason this sweep cannot be silently outgrown by a new route,
# and duplicating the fixture here would have given us a second copy to forget
# to update. A pytest fixture is an ordinary object, so rebinding the name in
# this module registers it for this module.
populated = EF.populated
populated_store = EF.populated


# ══ 1. The control — the payload really is on the pages ════════════════════

def test_the_sweep_really_did_reach_the_pages(hostile, client):
    """
    **Read this before believing anything below it.**

    Every other assertion in this file is "these bytes are NOT in the body",
    and that passes just as well against an empty page, a redirect, or a
    fixture that quietly stopped wiring the payload in. This proves the
    payload is genuinely reaching real rendered pages, and that a healthy
    majority of them carry it — not one page out of eighty.
    """
    assert hostile["fields"] > 100, (
        f"only {hostile['fields']} fields were poisoned; the fixture is not "
        f"populating the store any more")

    carrying = []
    for url in hostile["urls"]:
        response = client.get(url)
        assert response.status_code == 200, f"{url} did not render"
        if MARK in response.get_data(as_text=True):
            carrying.append(url)

    assert len(carrying) > len(hostile["urls"]) // 2, (
        f"only {len(carrying)} of {len(hostile['urls'])} pages carried the "
        f"payload at all. The sweep below is asserting almost nothing.")


# ══ 2. No route emits the payload raw ══════════════════════════════════════

@pytest.mark.parametrize("what", sorted(FORBIDDEN))
def test_no_route_emits_the_payload_raw(hostile, client, what):
    """
    The sweep that matters, one context per parametrised case.

    Read off `app.url_map` through `test_entity_fallbacks._urls`, so a route
    added later is covered the day it is registered — and that helper *fails*
    on a parameterised rule that is neither exercised nor explicitly skipped,
    so a new page cannot slip past by being forgotten.
    """
    fragment = FORBIDDEN[what]
    leaked = []
    for url in hostile["urls"]:
        if fragment in client.get(url).get_data(as_text=True):
            leaked.append(url)

    assert not leaked, (
        f"these routes emitted {what} unescaped — a signed-in reader of any "
        f"of them runs the author's script in their own session:\n  "
        + "\n  ".join(leaked))


# ══ 3. Escaped, not stripped ═══════════════════════════════════════════════

def test_the_payload_survives_escaped_rather_than_being_stripped(hostile, client):
    """
    INTRODUCTION.md §9: *the client's own data is imperfect, and it must
    survive rather than be repaired.* A customer really called
    `Smith & Sons <Bombay>` must still print as their own name.

    So "the payload is absent" is the wrong assertion: it passes against code
    that silently deletes the characters, which is data loss dressed as a
    security fix. This asserts the escaped spelling is present, byte for byte,
    on at least one page — and the control above proves the sweep is looking
    at populated ones.
    """
    seen = [url for url in hostile["urls"]
            if ESCAPED in client.get(url).get_data(as_text=True)]
    assert seen, (
        "the payload appears nowhere in its escaped spelling. Either nothing "
        "renders it, or something is stripping the characters instead of "
        "escaping them — which loses the customer's real name.")


# ══ 4. Braces are not a second template ════════════════════════════════════

SSTI_MODULES = {
    # url                          collection    field to poison
    "/product/":                   ("products",   "name"),
    "/quotation/":                 ("quotations", "account_name"),
    "/spec/":                      ("specs",      "title"),
    "/boq/":                       ("boqs",       "project_name"),
}


@pytest.mark.parametrize("url", sorted(SSTI_MODULES))
def test_a_stored_jinja_expression_is_not_executed(populated_store, client, url):
    """
    `P.esc` escapes `< > & " '` and deliberately **not** braces, so escaping on
    its own leaves server-side template injection wide open — ABOUT.md §7 gap
    9d. A view that ends `render_template_string(template)` on a string that is
    already fully interpolated parses it a second time and executes whatever
    `{{ … }}` arrived from a user.

    The payload asks for the signing key, because that is the consequence that
    matters now: with sessions live, leaking `SECRET_KEY` means an attacker
    mints a valid cookie for any account, and every permission check in
    `auth.py` becomes theatre.

    Asserted three ways, because each catches a different failure:
      * the key is not in the body;
      * the expression printed literally, so the value survived;
      * the page still rendered — a `{% … %}` payload used to 500 it, which is
        a stored denial of service.
    """
    import app as app_module

    collection, field = SSTI_MODULES[url]
    record = next(iter(STORE[collection].values()))
    record[field] = "PWNED{{ config['SECRET_KEY'] }}{% for x in y %}"

    response = client.get(url)
    body = response.get_data(as_text=True)

    assert response.status_code == 200, (
        f"{url} did not render with a stored Jinja tag in {collection}."
        f"{field} — a stored denial of service")
    assert app_module.app.secret_key not in body, (
        f"{url} printed the application's signing key. A stored "
        f"{{{{ config }}}} is being executed, which means any user who can "
        f"type into {collection}.{field} can forge a session cookie for "
        f"anybody.")
    assert "PWNED" in body, f"{url} did not render the value at all"


# ══ 5. JSON embedded in a <script> block ═══════════════════════════════════

JSON_SCRIPT_PAGES = ("/quotation/create", "/boq/create")


@pytest.mark.parametrize("url", JSON_SCRIPT_PAGES)
def test_stored_text_cannot_close_an_embedded_script_block(
        populated_store, client, url):
    """
    `json.dumps` does **not** escape `<`, so a stored value containing the
    seven characters `</script>` closes the block it is embedded in and every
    byte after it parses as HTML — ABOUT.md §7 gap 9e.

    Both these forms embed the whole address book, and `/quotation/create`
    embeds the product catalogue as well. `pipeline.json_for_script()` spells
    `<`, `>` and `&` as ordinary JSON escapes, which the browser decodes back
    unchanged, so the data is identical and only its spelling on the wire
    differs.
    """
    breakout = "</script><img src=x onerror=alert(9)>"
    for address_record in STORE["addresses"].values():
        address_record["label"] = "ADDRPWN" + breakout
        address_record["company"] = "ADDRPWN" + breakout
    for product_record in STORE["products"].values():
        product_record["name"] = "PRODPWN" + breakout

    body = client.get(url).get_data(as_text=True)
    assert breakout not in body, (
        f"{url} embedded a stored `</script>` verbatim. The block closes early "
        f"and everything after it is parsed as HTML — use "
        f"pipeline.json_for_script().")


# ══ 6. Reflected parameters ════════════════════════════════════════════════
#
# The stored payloads above need an attacker to have write access to a record.
# These do not: a crafted link handed to a signed-in Owner is enough, which
# makes them the cheapest of the lot to exploit and the easiest to miss —
# `?type=` lands inside a `class="…"` attribute, where nothing looks like text.

REFLECTING_PAGES = ("/boq/", "/invoice/", "/product/", "/proforma/", "/purchase/",
                    "/quotation/", "/ra/", "/settings/", "/spec/", "/dc/", "/po/",
                    "/receipt/", "/charge/", "/client/", "/projects/", "/address/",
                    "/users", "/roles")


@pytest.mark.parametrize("page", REFLECTING_PAGES)
def test_the_alert_banner_does_not_reflect_a_crafted_link(client, page):
    """
    Every list page in this app renders `?msg=` in a redirect banner and takes
    its colour from `?type=`. `msg` was mostly escaped; **`type` was not, on
    nine of these pages**, because it lands in a class attribute rather than in
    text and reads like a constant.

    Both are asserted with an attribute-breakout payload, which is what
    actually gets out of `class="alert alert-…"`.
    """
    payload = 'XSSREFL"><script>alert(4)</script>'
    body = client.get(page, query_string={"msg": payload, "type": payload}) \
                 .get_data(as_text=True)
    assert payload not in body, (
        f"{page} reflected a query parameter into the page unescaped. A link "
        f"sent to a signed-in user runs script in their session — no stored "
        f"record needed.")


# ══ 7. The company identity ════════════════════════════════════════════════

PRINTED_DOCUMENTS = ("boq", "ra", "po", "dc")


def test_the_company_identity_cannot_inject_into_a_letterhead(hostile, client):
    """
    The sink that was outside both files CLIENT_CHANGES-2.md names.

    Every field on `/settings` — the legal name, the tagline, the address, the
    GSTIN, the whole bank block — is typed by a user and printed on the
    letterhead of every document this office issues. It reached the page raw,
    through `branding.field()` and a scatter of bare `B.COMPANY_*`
    interpolations in `docsheet.py`, `boq.py` and `quotation.py`.

    It is the worst-placed of the lot: it is on the page an Owner reads, and it
    is on **every** document rather than one record's own page.

    `hostile` pushes the payload through `apply_settings()`, which is the path
    `/settings` itself takes — writing `STORE["settings"]` does not reach the
    letterhead, and a test that did that would pass against the broken code.
    """
    leaked = []
    for url in hostile["urls"]:
        body = client.get(url).get_data(as_text=True)
        for what, fragment in FORBIDDEN.items():
            if fragment in body:
                leaked.append(f"{url} ({what})")

    assert not leaked, (
        "a hostile company identity reached these pages unescaped:\n  "
        + "\n  ".join(sorted(set(leaked))))


def test_the_identity_is_restored_after_the_hostile_fixture():
    """
    The fixture's own guard.

    `apply_settings()` writes module globals, so a fixture that failed to put
    them back would leave every later test in the session rendering a poisoned
    letterhead — including `tests/test_print_golden.py`, which hashes it. That
    failure would surface as five unrelated golden failures and cost an
    afternoon, so it is asserted here where it can say what happened.
    """
    assert B.COMPANY_TAGLINE == B.DEFAULTS["COMPANY_TAGLINE"]
    assert MARK not in B.COMPANY_TAGLINE
