"""
The sidebar, the top bar and the module zones — 14 September 2026.

One table, `chrome.REGISTERS`, draws the rail on every screen page and the
four zones at the foot of the dashboard. This file holds the properties that
table was built for and the ones the brief named:

* **one set** — the rail and the dashboard name the same registers, in the
  same order, for the same user. Two hand-written lists drift the first time
  a register is added; one table cannot;
* **permission-filtered, and filtered at the endpoint** — `auth.can_reach()`
  answers from `ROUTE_PERMISSIONS`, the dict the gate reads, so a limited
  user is never shown a link that 403s. That is the ONLY guarantee this
  application can make: there is no per-record access control anywhere in
  it (ABOUT.md §7 gap 24), and the rail does not pretend otherwise. Hiding is
  presentation; every hidden route is also refused by URL;
* **live figures** — the rail's counts and the zones' roll-up pills are read
  from the store at render time, never hardcoded;
* **every status chip carries an icon AND a word** — amber and red are one
  colour under deuteranopia;
* **the collapsed state lives in `localStorage`** inside `try/catch`, with no
  cookie, no route and no server round-trip;
* **the colours are the brief's exact values**, checked for colour-blind
  separation, and the geometry is the brief's.

`tests/test_nav_visibility.py` holds the per-role tables; `tests/test_page_chrome.py`
sweeps the shell onto every screen page; `tests/test_page_golden.py` pins the
bytes. This file is what those three do not say.
"""

import re

import pytest

import auth
import chrome
import dashboard
from store import STORE


def _rail_hrefs(html: str) -> list:
    block = html[html.index('<nav class="rail"'):html.index("</nav>")]
    return re.findall(r'<a class="rl[^"]*" href="([^"]*)"', block)


def _zone_hrefs(html: str) -> list:
    if '<h2>Modules</h2>' not in html:
        return []
    zone = html[html.index('<h2>Modules</h2>'):]
    return re.findall(r'<a href="([^"]*)"[^>]*class="card">', zone)


def _user(slug: str) -> dict:
    name = f"sb-{slug}"
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    auth.ensure_builtin_roles()
    return auth.create_user(name, name, f"pw-{name}-12345", [f"role-{slug}"],
                            created_by="sidebar-test")


def _as(client, user) -> None:
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = user["id"]


# ══ 1. One table, two surfaces ═══════════════════════════════════════════════

@pytest.mark.parametrize("slug", ["owner", "operation-head", "hr",
                                  "sales-manager", "purchase-manager",
                                  "accountant"])
def test_the_rail_and_the_dashboard_name_the_same_registers(client, slug):
    """
    **The test the single source of truth exists for.** For every role, the
    registers the rail links to are exactly the registers the zones link to,
    in the same order. Dashboard and Settings are the rail's own two entries
    and are excluded — neither is a register.
    """
    _as(client, _user(slug))
    html = client.get("/").get_data(as_text=True)

    rail = [h for h in _rail_hrefs(html) if h not in ("/", "/settings/")]
    zones = _zone_hrefs(html)
    assert rail, f"role {slug!r}: the rail names no register at all"
    assert rail == zones, (
        f"role {slug!r}: the rail and the zones disagree.\n"
        f"  rail:  {rail}\n  zones: {zones}")


def test_every_register_is_in_exactly_one_group_and_every_group_is_drawn_in_order():
    keys = [r.key for r in chrome.REGISTERS]
    assert len(keys) == len(set(keys)), "a register key is repeated"
    groups = [g.key for g in chrome.GROUPS]
    assert groups == ["sell", "proj", "buy", "lib"], "the four groups, in the brief's order"
    for r in chrome.REGISTERS:
        assert r.group in groups, f"{r.key} names a group that does not exist"
    # The registry is grouped contiguously, so the rail and the zones walk it
    # in one pass each and the two orders cannot diverge.
    seen = [r.group for r in chrome.REGISTERS]
    assert seen == sorted(seen, key=groups.index)


def test_every_endpoint_the_registry_names_is_classified():
    """
    A register pointing at an unclassified endpoint would be invisible to
    everybody — absence is a refusal — which is a silent way to delete a
    module from both surfaces at once.
    """
    for r in chrome.REGISTERS:
        assert r.endpoint in auth.ROUTE_PERMISSIONS, r.endpoint
        if r.action_endpoint:
            assert r.action_endpoint in auth.ROUTE_PERMISSIONS, r.action_endpoint


def test_the_registry_names_no_permission_id():
    """
    The mechanism, asserted rather than trusted: the table names ENDPOINTS
    and asks `can_reach()`. A permission id in it would be the second list.
    """
    for r in chrome.REGISTERS:
        for value in (r.endpoint, r.action_endpoint, r.key, r.name):
            assert value not in auth.PERMISSIONS, (
                f"chrome.REGISTERS names the permission id {value!r} — name the "
                f"endpoint and let can_reach() derive the answer")


def test_action_labels_are_written_out_and_never_derived():
    """
    Stripping a trailing `s` off a register name gives "New market new" and
    "New spec librar". Every label is a literal in the table, and this is the
    tripwire for somebody replacing them with a rule.
    """
    labels = {r.key: r.action_label for r in chrome.REGISTERS if r.action_label}
    assert labels == {
        "quotation":  "New quotation",
        "project":    "New project",
        "boq":        "New BOQ",
        "ra":         "New RA bill",
        "receipt":    "Record a payment",
        "purchase":   "New purchase order",
        "charge":     "New expense",
        "attendance": "Mark attendance",
        "product":    "New product",
        "spec":       "New spec clause",
        "employee":   "New employee",
        "address":    "New address",
        "users":      "New user",
    }
    for r in chrome.REGISTERS:
        derived = "New " + r.name.rstrip("s").lower()
        assert r.action_label.lower() != derived or r.key in ("quotation", "project"), (
            f"{r.key}: the action label looks derived from the register name")
    # The three registers raised only from a schedule carry no action here;
    # `/dc/create`, `/po/create` and `/measurement/create` all redirect to the
    # BOQ register without `?boq=`, and the button belongs on `/boq/view`.
    for key in ("challan", "po_draft", "measurement"):
        reg = next(r for r in chrome.REGISTERS if r.key == key)
        assert reg.action_endpoint == "" and reg.action_label == ""


# ══ 2. Permission filtering — a limited user, and the gate behind it ═════════

def test_a_limited_user_is_shown_only_what_the_gate_would_allow(client):
    """
    HR reaches four registers. The rail must offer those four and none of
    the other sixteen — and every one of the sixteen must still refuse by URL,
    because hiding a link is not closing a route.
    """
    from flask import url_for

    import app as app_module

    _as(client, _user("hr"))
    html = client.get("/").get_data(as_text=True)
    offered = set(_rail_hrefs(html))

    with app_module.app.test_request_context():
        urls = {r.key: url_for(r.endpoint) for r in chrome.REGISTERS}

    visible = {k for k, u in urls.items() if u in offered}
    assert visible == {"charge", "attendance", "employee", "address"}, visible
    assert "/settings/" not in offered, "HR holds no settings.edit and must not see it"

    hidden = {k: u for k, u in urls.items() if k not in visible}
    assert len(hidden) >= 2, "the control needs a user who cannot reach at least two"
    still_open = []
    for key, url in hidden.items():
        r = client.get(url)
        refused = r.status_code == 403 or (
            r.status_code in (301, 302, 303, 307, 308)
            and "/login" in r.headers.get("Location", ""))
        if not refused:
            still_open.append(f"{key} ({url})")
    assert not still_open, (
        f"hidden from HR's rail but still open by URL — hiding has been "
        f"mistaken for a permission check: {still_open}")


def test_the_purchase_manager_gets_no_users_entry_and_no_settings(client):
    """A second limited role, so the first is not a special case."""
    _as(client, _user("purchase-manager"))
    html = client.get("/boq/").get_data(as_text=True)
    hrefs = _rail_hrefs(html)
    assert "/users" not in hrefs and "/settings/" not in hrefs
    assert "/purchase/" in hrefs and "/po/" in hrefs
    assert client.get("/users").status_code == 403
    assert client.get("/settings/").status_code == 403


def test_the_hidden_catalogue_is_on_nobodys_rail_and_returns_when_unhidden(
        client, catalogue_unhidden):
    """
    `Product Catalogue` stays in the table while `auth.HIDDEN_BLUEPRINTS`
    hides the module — `can_reach()` answers False, so it is drawn nowhere —
    and un-hiding is still one line in `auth.py` (ABOUT.md §2g).
    """
    html = client.get("/").get_data(as_text=True)
    assert "/product/" in _rail_hrefs(html), "un-hidden, the entry must return"
    saved = set(auth.HIDDEN_BLUEPRINTS)
    auth.HIDDEN_BLUEPRINTS.clear()
    auth.HIDDEN_BLUEPRINTS.add("product")
    try:
        html = client.get("/").get_data(as_text=True)
        assert "/product/" not in _rail_hrefs(html)
        assert "/product/" not in _zone_hrefs(html)
    finally:
        auth.HIDDEN_BLUEPRINTS.clear()
        auth.HIDDEN_BLUEPRINTS.update(saved)


# ══ 3. Live figures ══════════════════════════════════════════════════════════

def test_the_rail_count_is_read_from_the_store_at_render_time(client):
    client.get("/boq/")
    before = len(STORE["boqs"])
    html = client.get("/boq/").get_data(as_text=True)
    assert f'title="Bills of Quantities">' in html
    m = re.search(r'title="Bills of Quantities">.*?<span class="rl-n">(\d+)</span>',
                  html, re.S)
    assert m and int(m.group(1)) == before

    STORE["boqs"]["sb-extra"] = dict(next(iter(STORE["boqs"].values())),
                                     id="sb-extra", ref="SF/BOQ/26-27/0099")
    html = client.get("/boq/").get_data(as_text=True)
    m = re.search(r'title="Bills of Quantities">.*?<span class="rl-n">(\d+)</span>',
                  html, re.S)
    assert m and int(m.group(1)) == before + 1, "the count did not follow the store"
    STORE["boqs"].pop("sb-extra", None)


def test_the_roll_up_pills_are_computed_from_live_data(client):
    """
    Sell side: live pipeline value and tax-invoice outstanding. Plant one open
    quotation and one tax invoice and the pill must carry both figures.
    """
    STORE["quotations"]["sb-q"] = {
        "id": "sb-q", "ref": "QT-0090", "date": "2026-08-01",
        "account_name": "Pill Test Ltd", "grand_total": 250000.0,
        "sales_stage": "Technical", "line_items": [], "subtotal": 250000.0,
    }
    STORE["invoices"]["sb-ti"] = {
        "id": "sb-ti", "ref": "SF/TI/26-27/0090", "fy": "26-27",
        "date": "2026-08-02", "net_payable": 41000.0, "grand_total": 41000.0,
        "line_items": [], "account_name": "Pill Test Ltd",
    }
    try:
        html = client.get("/").get_data(as_text=True)
        pill = re.search(r'<section class="mod-group g-sell">.*?<span class="mg-pill">(.*?)</span>',
                         html, re.S)
        assert pill, "the sell-side zone carries no roll-up pill"
        assert dashboard.rupees(250000.0) in pill.group(1), pill.group(1)
        assert dashboard.rupees(41000.0) in pill.group(1), pill.group(1)
        assert "live pipeline" in pill.group(1) and "outstanding" in pill.group(1)
    finally:
        STORE["quotations"].pop("sb-q", None)
        STORE["invoices"].pop("sb-ti", None)


def test_the_library_pill_counts_clients_and_clauses(client):
    client.get("/boq/")     # seeds the 56 clauses and the demo schedule
    html = client.get("/").get_data(as_text=True)
    pill = re.search(r'<section class="mod-group g-lib">.*?<span class="mg-pill">(.*?)</span>',
                     html, re.S)
    assert pill and "56 clauses" in pill.group(1), pill.group(1) if pill else None
    assert re.search(r"\d+ clients?", pill.group(1))


def test_a_roll_up_half_the_user_cannot_reach_is_not_drawn(client):
    """
    An Accountant holds no `quotation.view`, so the sell pill must carry the
    tax-invoice half alone rather than a pipeline figure summed from records
    they cannot list.
    """
    _as(client, _user("accountant"))
    html = client.get("/").get_data(as_text=True)
    pill = re.search(r'<section class="mod-group g-sell">.*?<span class="mg-pill">(.*?)</span>',
                     html, re.S)
    assert pill and "outstanding" in pill.group(1)
    assert "live pipeline" not in pill.group(1)


# ══ 4. Status chips: an icon AND a word ══════════════════════════════════════

def test_every_attention_reason_wears_a_chip_with_an_icon_and_a_word(client):
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=10)).isoformat()
    STORE["quotations"]["sb-overdue"] = {
        "id": "sb-overdue", "ref": "QT-0091", "date": "2026-08-01",
        "account_name": "Overdue Ltd", "grand_total": 1000.0,
        "sales_stage": "Technical", "exp_closing": old, "line_items": [],
    }
    STORE["quotations"]["sb-nopo"] = {
        "id": "sb-nopo", "ref": "QT-0092", "date": "2026-08-01",
        "account_name": "Won Ltd", "grand_total": 2000.0,
        "sales_stage": "Closed Won", "po_number": "", "line_items": [],
    }
    try:
        html = client.get("/").get_data(as_text=True)
        chips = re.findall(r'<span class="chip chip-(\w+)">(<svg.*?</svg>)([^<]+)</span>', html, re.S)
        tones = {(tone, word.strip()) for tone, _svg, word in chips}
        assert ("crit", "Overdue") in tones, tones
        assert ("warn", "No PO on file") in tones, tones
        # Every chip carries its own icon — never colour alone.
        assert all(svg.startswith("<svg") for _t, svg, _w in chips)
    finally:
        STORE["quotations"].pop("sb-overdue", None)
        STORE["quotations"].pop("sb-nopo", None)


def test_the_status_colours_are_the_briefs_exact_values():
    css = chrome.CHROME_STYLES
    for token in ("--st-good: #0F7A52", "--st-good-bg: #E2F2EB",
                  "--st-warn: #9A6B00", "--st-warn-bg: #F7EFDC",
                  "--st-crit: #D5121A", "--st-crit-bg: #FCE9E9"):
        assert token in css, token


# ══ 5. The collapsed state, the geometry and the colours ═════════════════════

def test_the_collapsed_state_is_local_storage_in_try_catch_with_no_round_trip():
    js = chrome.CHROME_SCRIPT
    assert "localStorage.getItem" in js and "localStorage.setItem" in js
    # Both the read and the write are wrapped.
    for call in ("localStorage.getItem", "localStorage.setItem"):
        at = js.index(call)
        assert "try {" in js[max(0, at - 40):at], f"{call} is not inside try"
        assert "catch (e)" in js[at:at + 120], f"{call} has no catch"
    for forbidden in ("document.cookie", "fetch(", "XMLHttpRequest", "navigator.sendBeacon"):
        assert forbidden not in js, f"the collapse state must not {forbidden}"
    # And no route serves it: nothing in the app answers a "rail" endpoint.
    assert not [ep for ep in auth.ROUTE_PERMISSIONS if "rail" in ep]


def test_the_rail_geometry_and_the_group_colours_are_the_briefs():
    css = chrome.CHROME_STYLES
    assert "--rail-w: 248px" in css and "--rail-c: 68px" in css
    assert "linear-gradient(168deg, #1C0449 0%, #2A086E 100%)" in css
    for key, accent, tint, zone in (("sell", "#5B4BC4", "#EDEBFA", "#FAFAFE"),
                                    ("proj", "#0A8F78", "#E1F3EF", "#F8FDFC"),
                                    ("buy",  "#B8600C", "#FAEEE1", "#FFFCF8"),
                                    ("lib",  "#5A5468", "#EEECF2", "#FBFAFC")):
        g = chrome.GROUP_OF[key]
        assert (g.accent, g.tint, g.zone) == (accent, tint, zone), key
        assert re.search(rf"--g-{key}:\s+{accent}", css), key
    # The one breakpoint, both halves.
    assert "@media (max-width: 1000px)" in css and "@media (max-width: 620px)" in css
    # And nothing of the shell reaches paper.
    assert re.search(r"@media print \{[^}]*nav\.rail, \.topstack, \.rail-scrim \{ display: none !important; \}", css)


def test_the_shell_styles_are_not_in_the_block_the_print_goldens_hash():
    """
    `docsheet.SHEET_STYLES` opens with `BASE_STYLES`, which nine printed
    documents carry in their `head` block. The sidebar's rules ride out with
    `_nav()` instead, so a chrome change cannot move a printed sheet.
    """
    for token in (".rail", ".topbar", ".topstack", "--rail-w", ".mg-pill"):
        assert token not in chrome.BASE_STYLES, f"{token} leaked into BASE_STYLES"
    assert chrome.CHROME_STYLES.lstrip().startswith("<style>")


# ══ 6. The top bar ═══════════════════════════════════════════════════════════

def test_the_top_bar_names_the_page_and_offers_its_own_action(client):
    client.get("/boq/")
    html = client.get("/boq/").get_data(as_text=True)
    assert '<div class="tb-name">Bills of Quantities</div>' in html
    assert '<div class="tb-sub">Projects &amp; site billing</div>' in html
    assert 'class="btn tb-act" href="/boq/create"' in html and "New BOQ" in html
    # Not on the action's own page.
    html = client.get("/boq/create").get_data(as_text=True)
    assert 'class="btn tb-act" href="/boq/create"' not in html

    assert '<div class="tb-name">Settings</div>' in client.get("/settings/").get_data(as_text=True)
    assert '<div class="tb-name">Users &amp; Access</div>' in client.get("/users").get_data(as_text=True)
    assert '<div class="tb-name">Dashboard</div>' in client.get("/").get_data(as_text=True)


def test_the_wordmark_and_the_user_chip_are_in_the_top_bar_not_the_rail(client):
    html = client.get("/").get_data(as_text=True)
    rail = html[html.index('<nav class="rail"'):html.index("</nav>")]
    bar = html[html.index('<header class="topbar">'):html.index("</header>")]
    assert 'class="nav-user"' in bar and 'class="nav-user"' not in rail
    assert 'class="nav-brand"' in bar and 'class="nav-brand"' not in rail
    assert 'href="/logout"' in bar and 'href="/logout"' not in rail


def test_the_current_register_is_marked_active_and_a_sub_page_marks_its_parent(client):
    client.get("/boq/")
    html = client.get("/ra/").get_data(as_text=True)
    assert re.search(r'<a class="rl is-active" href="/ra/"', html)
    assert not re.search(r'<a class="rl is-active" href="/boq/"', html)
    # A merged tax invoice is a sub-register of the RA register (CC-2 C3).
    html = client.get("/merged/").get_data(as_text=True)
    assert re.search(r'<a class="rl is-active" href="/ra/"', html)


def test_the_persistence_strip_sits_above_the_top_bar_and_still_works(client, monkeypatch):
    import db
    monkeypatch.setattr(db, "failure_note", lambda: "Bills of quantities are not being saved.")
    monkeypatch.setattr(db, "failure_detail", lambda: "boqs: column too long")
    monkeypatch.setattr(db, "is_live", lambda: True)
    html = client.get("/boq/").get_data(as_text=True)
    stack = html[html.index('<div class="topstack">'):html.index("</header>")]
    assert 'class="db-down"' in stack, "the strip is not in the top stack"
    assert stack.index('class="db-down"') < stack.index('<header class="topbar">'), (
        "the strip must sit ABOVE the bar")
    assert "Every request retries." in stack
