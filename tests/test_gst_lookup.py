"""
GSTIN auto-fill on the address book (29 September 2026) — `gst_lookup.py` and
the four routes and the form in `address.py`.

⚠ **NO LIVE NETWORK.** `conftest._no_gst_network` refuses every outbound call
  for the whole suite; the `net` fixture below replaces that refusal with
  RECORDED answers. The two error bodies are the portal's own, verbatim, as
  measured from an Indian IP on 29 September 2026 (docs/GST_PORTAL.md). The
  success body carries exactly the keys the portal returned that day, with
  invented values — the real one is a proprietor's personal name and address.

⚠ **Nothing here reads a CAPTCHA.** The "image" is eight bytes of PNG header
  and zeros, and every answer is typed into the test by hand, exactly as a
  person types it into the form.

Sections: 1 the offline check · 2 the browser's copy of it, under Node ·
3 the site-address guard · 4 the portal, mocked · 5 the fallback's order ·
6 the cache · 7 sessions and limits · 8 one attempt, five seconds, honest ·
9 routes and permissions · 10 what a save does · 11 escaping · 12 the form.
"""

import ast
import copy
import http.client
import json
import pathlib
import shutil
import socket
import subprocess
import types

import pytest

import address
import auth
import db
import gst_lookup as G
import pipeline as P
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

# Captured at IMPORT — collection time, before `conftest._no_gst_network`
# patches the attribute — so section 8 can drive the real function against a
# fake opener.
REAL_OPEN = G._open


def valid(first14: str) -> str:
    """A GSTIN with the right check character. Invented unless said otherwise."""
    return first14 + G.check_char(first14)


# Samruddhi's OWN GSTIN — given for the live test of 29 September 2026, and
# confirmed there by the portal (status Active). The one real registration in
# this file; it is printed on every tax invoice Samruddhi issues.
REAL_GSTIN = "27BGRPB0456K1Z7"
# Invented, check-valid, and each names a State.
GOOD = valid("27AAAPZ1234C1Z")          # Maharashtra
OTHER = valid("24AAAPZ5678D1Z")         # Gujarat

PNG = bytes.fromhex("89504e470d0a1a0a") + bytes(64)

# The portal's own answers, verbatim (docs/GST_PORTAL.md).
WRONG_CAPTCHA = {"url": "/", "message": None, "errorCode": "SWEB_9000"}
NO_SUCH_GSTIN = {"status_cd": "0",
                 "error": {"message": "Invalid GSTIN / UID", "error_cd": "SWEB_9035"},
                 "cmpRt": "NA"}
# gstinapi.in's real keyless answer, measured the same day.
FALLBACK_401 = {"error": "API key required. Pass x-api-key header.",
                "fix": "Create a key at https://www.gstinapi.in/api-keys and send "
                       "it as the x-api-key header."}

ADR = ("UNIT 4, 2ND FLOOR, SUNRISE ESTATE, LBS MARG, BHANDUP WEST, Mumbai, "
       "Mumbai Suburban, Maharashtra, 400078")


def portal_body(gstin=GOOD, **over) -> dict:
    """A success body with EXACTLY the keys measured on 29 September 2026."""
    body = {
        "ntcrbs": "SPO", "adhrVFlag": "No", "lgnm": "EXAMPLE TRADERS PRIVATE LIMITED",
        "stj": "State - Maharashtra,Zone - MUMBAI,Division - X,Charge - Y",
        "dty": "Regular", "cxdt": "", "gstin": gstin,
        "nba": ["Wholesale Business", "Works Contract"], "ekycVFlag": "No",
        "cmpRt": "NA", "rgdt": "01/07/2017", "ctb": "Private Limited Company",
        "pradr": {"adr": ADR}, "sts": "Active", "tradeNam": "EXAMPLE FIRE SYSTEMS",
        "isFieldVisitConducted": "No", "ctj": "State - CBIC,Zone - MUMBAI",
        "einvoiceStatus": "No",
    }
    body.update(over)
    return body


def js(obj) -> tuple:
    """A recorded answer: (status, content type, body bytes)."""
    return 200, "application/json", json.dumps(obj).encode("utf-8")


class FakeNet:
    """
    Stands in for `gst_lookup._open`: records every call and answers from the
    three attributes. An answer is a (status, ctype, bytes) tuple or an
    exception INSTANCE, which is raised — exactly how a timeout or a dropped
    connection reaches the real callers.
    """

    def __init__(self):
        self.calls = []
        self.captcha = (200, "image/png", PNG)
        self.search = js(portal_body())
        self.fallback = js({"success": True, "data": {}})

    def __call__(self, request, jar=None):
        if isinstance(request, str):
            url, method, data, headers = request, "GET", None, {}
        else:
            url, method = request.full_url, request.get_method()
            data, headers = request.data, dict(request.header_items())
        self.calls.append({"url": url, "method": method, "data": data,
                           "headers": headers, "jar": jar})
        if url.startswith(G.CAPTCHA_URL):
            answer = self.captcha
        elif url == G.SEARCH_URL:
            answer = self.search
        elif url.startswith("https://www.gstinapi.in/"):
            answer = self.fallback
        else:
            raise AssertionError(f"unexpected outbound call to {url}")
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def to(self, prefix):
        return [c for c in self.calls if c["url"].startswith(prefix)]


@pytest.fixture()
def net(monkeypatch):
    fake = FakeNet()
    monkeypatch.setattr(G, "_open", fake)
    return fake


@pytest.fixture()
def key(monkeypatch):
    monkeypatch.setenv("GST_API_KEY", "gak_test_key_not_real")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """The book is not cleared by `conftest._fresh_store()`; this file writes to
    it, so it puts it back. Sessions, limits and the cache start empty."""
    saved = copy.deepcopy(STORE["addresses"])
    seeded = STORE.get("_addr_seeded")
    # Another file may have emptied the book and left the seed flag set, so
    # `ensure_demo_addresses()` would be a no-op. It skips ids it finds.
    STORE["_addr_seeded"] = False
    address.ensure_demo_addresses()       # now, so no route seeds mid-test
    STORE.setdefault("gst_cache", {}).clear()
    G._SESSIONS.clear()
    G._CALLS.clear()
    yield
    STORE["addresses"].clear()
    STORE["addresses"].update(saved)
    STORE["_addr_seeded"] = seeded
    STORE["gst_cache"].clear()
    G._SESSIONS.clear()
    G._CALLS.clear()


def plant(gstin=GOOD, age_days=0.0, **fields):
    """Put a normalised result in the cache, as a lookup `age_days` ago would."""
    res = G._from_portal(portal_body(gstin), gstin)
    res.update(fields)
    G._remember(res)
    STORE["gst_cache"][gstin]["fetched_ts"] -= age_days * 86400
    return res


def a_user(role_id: str, name: str):
    auth.ensure_builtin_roles()
    return auth.find_user(name) or auth.create_user(
        name, name, f"{name}-password-123", [role_id], created_by="test")


def a_role(rid: str, perms):
    auth.ensure_builtin_roles()
    STORE["roles"][rid] = {"id": rid, "name": rid, "permissions": sorted(perms),
                           "builtin": False}
    return rid


def sign_in(client, user):
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = user["id"]


def form(**over) -> dict:
    """A complete, valid /address/add post."""
    data = {"label": "Test Site", "type": "office", "company": "Test Co",
            "contact_name": "", "line1": "Plot 1", "line2": "", "landmark": "",
            "city": "Mumbai", "state": "Maharashtra", "pincode": "400001",
            "phone": "", "email": "", "gstin": ""}
    data.update(over)
    return data


def new_address(client, **over) -> str:
    before = set(STORE["addresses"])
    r = client.post("/address/add", data=form(**over))
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    (aid,) = set(STORE["addresses"]) - before
    return aid


# ═══ 1. The offline check ════════════════════════════════════════════════════

def test_samruddhis_real_gstin_passes_the_check():
    assert G.check_digit_ok(REAL_GSTIN)
    off = G.offline(REAL_GSTIN)
    assert off["valid"] and off["error"] == ""


def test_every_single_character_mutation_is_refused():
    """
    The check character's whole job. For two check-valid GSTINs, every one of
    the 15 positions is replaced by each of the other 35 symbols; every result
    that still has a GSTIN's SHAPE must fail the check — a mod-36 Luhn catches
    every single substitution. The count is asserted, so the loop cannot
    silently test nothing.
    """
    checked = 0
    for g in (REAL_GSTIN, GOOD):
        assert G.check_digit_ok(g)
        for i in range(15):
            for ch in G.ALPHABET:
                if ch == g[i]:
                    continue
                m = g[:i] + ch + g[i + 1:]
                if G.GSTIN_RE.match(m):
                    assert not G.check_digit_ok(m), m
                    assert G.offline(m)["valid"] is False, m
                    checked += 1
    assert checked > 300, checked


def test_the_state_code_and_pan_are_read_from_the_gstin():
    off = G.offline(REAL_GSTIN)
    assert (off["state_code"], off["state"], off["pan"]) == ("27", "Maharashtra", "BGRPB0456K")
    assert G.pan_of(REAL_GSTIN) == "BGRPB0456K"
    assert G.offline(OTHER)["state"] == "Gujarat"


def test_every_state_the_gstin_can_name_is_one_the_form_offers():
    """The fill sets the form's <select>; a State it cannot offer fills nothing."""
    assert set(P.GST_STATE_CODES) <= set(address.INDIAN_STATES)


@pytest.mark.parametrize("code", ["97", "99", "25", "28"])
def test_an_unallotted_state_code_is_valid_and_fills_no_state(code):
    g = valid(code + "AAAPZ1234C1Z")
    off = G.offline(g)
    assert off["valid"] and off["state"] == "" and code in off["note"]


def test_the_error_never_names_the_right_check_character():
    """One of fifteen is wrong — offering 'the' fix would invite the wrong one."""
    bad = GOOD[:14] + ("A" if GOOD[14] != "A" else "B")
    err = G.offline(bad)["error"]
    assert "mistyped" in err and GOOD[14] not in err.replace("GST", "")


def test_case_and_outer_spaces_are_forgiven_nothing_else_is():
    assert G.offline(f"  {REAL_GSTIN.lower()} ")["valid"]
    assert not G.offline(REAL_GSTIN[:7] + " " + REAL_GSTIN[7:])["valid"]


@pytest.mark.parametrize("raw,fragment", [
    ("27BGRPB0456K1Z", "this one has 14"),
    ("27BGRPB0456K1Z77", "this one has 16"),
    ("27BGRPB0456K1X7", "not the shape"),
])
def test_length_and_shape_errors(raw, fragment):
    assert fragment in G.offline(raw)["error"]


def test_the_address_form_and_the_lookup_share_one_pattern():
    assert address._GSTIN_RE is G.GSTIN_RE


# ═══ 2. The browser's copy of the check, under Node ══════════════════════════

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _node(script: str):
    """Run address.GST_SCRIPT (no DOM: the wiring half skips itself) + `script`."""
    src = address.GST_SCRIPT.replace("<script>", "").replace("</script>", "")
    out = subprocess.run(["node"], input=src + "\n" + script, capture_output=True,
                         text=True, timeout=60, encoding="utf8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _cases():
    out = [REAL_GSTIN, GOOD, OTHER, "", " 27bgrpb0456k1z7 ", "27BGRPB0456K1Z",
           "27BGRPB0456K1X7", valid("97AAAPZ1234C1Z"), "ZZ" + REAL_GSTIN[2:]]
    for g in (REAL_GSTIN, GOOD):
        for i in range(15):
            for ch in G.ALPHABET:
                if ch != g[i]:
                    out.append(g[:i] + ch + g[i + 1:])
    return out


@needs_node
def test_the_browser_check_agrees_with_the_server_on_every_case():
    """
    The browser validates on the 15th character and the server on Save; if the
    two ever disagree, a GSTIN the page accepted is refused at Save, or the
    reverse. Every field of every answer — messages included — is compared.
    """
    cases = _cases()
    states = {code: name for name, code in P.GST_STATE_CODES.items()}
    got = _node(f"var S = {json.dumps(states)}; var C = {json.dumps(cases)};"
                "console.log(JSON.stringify(C.map(function (c) { return GST.offline(c, S); })));")
    assert len(got) == len(cases) > 1000
    for case, js_answer in zip(cases, got):
        assert js_answer == G.offline(case), case


def test_the_browser_pattern_is_the_servers():
    assert f"/{G.GSTIN_RE.pattern}/" in address.GST_SCRIPT


# ═══ 3. A project site keeps its own address lines ═══════════════════════════

def _result(**over):
    r = G._from_portal(portal_body(), GOOD)
    r.update(over)
    return r


CURRENT = {"label": "Hinjewadi Project Site", "company": "", "line1": "Building B",
           "line2": "Phase II, Hinjewadi", "city": "Pune", "state": "", "pincode": "411057"}


@needs_node
def test_a_site_is_given_its_name_and_state_and_never_its_address_lines():
    plan = _node(f"console.log(JSON.stringify(GST.plan({json.dumps(_result())}, 'site', "
                 f"{json.dumps(CURRENT)})));")
    assert plan == {"company": "EXAMPLE FIRE SYSTEMS", "state": "Maharashtra"}


@needs_node
def test_an_office_is_given_the_split_address():
    plan = _node(f"console.log(JSON.stringify(GST.plan({json.dumps(_result())}, 'office', "
                 f"{json.dumps(dict(CURRENT, label=''))})));")
    assert plan == {"company": "EXAMPLE FIRE SYSTEMS", "label": "EXAMPLE FIRE SYSTEMS",
                    "state": "Maharashtra", "line1": "UNIT 4, 2ND FLOOR, SUNRISE ESTATE",
                    "line2": "LBS MARG, BHANDUP WEST", "city": "Mumbai",
                    "pincode": "400078"}


@needs_node
def test_an_address_that_cannot_be_split_fills_no_line_and_a_label_is_never_replaced():
    r = _result(address=G.split_address("somewhere with no PIN"))
    plan = _node(f"console.log(JSON.stringify(GST.plan({json.dumps(r)}, 'billing', "
                 f"{json.dumps(CURRENT)})));")
    assert set(plan) == {"company", "state"}


def test_the_site_guard_names_the_site_type_and_not_site_types():
    """`SITE_TYPES` includes the office — where a principal place usually IS."""
    assert address.GST_NO_ADDRESS_FILL_TYPE == "site"
    assert "var NO_ADDRESS_FILL = 'site';" in address.GST_SCRIPT
    assert address.SITE_TYPES == ("site", "office")


def test_the_site_form_explains_why_its_lines_are_kept(client):
    address.ensure_demo_addresses()
    site = client.get("/address/edit/b2000002-face-4000-8000-000000000002").get_data(as_text=True)
    office = client.get("/address/edit/b2000001-face-4000-8000-000000000001").get_data(as_text=True)
    assert 'id="gst-site-note">' in site and "never the address lines" in site
    assert 'id="gst-site-note" hidden>' in office


def test_the_split_reads_the_two_ends_and_declares_the_rest():
    assert G.split_address(ADR) == {
        "line1": "UNIT 4, 2ND FLOOR, SUNRISE ESTATE", "line2": "LBS MARG, BHANDUP WEST",
        "city": "Mumbai", "state": "Maharashtra", "pincode": "400078", "split": True}
    assert G.split_address("Plot 5, Pune, Maharashtra, 411001")["city"] == "Pune"
    assert G.split_address("Plot 5, Pune, Maharashtra, 011001")["split"] is False
    assert G.split_address("Plot 5, Pune, Atlantis, 411001")["split"] is False


# ═══ 4. The portal, mocked ═══════════════════════════════════════════════════

def start(uid="u1"):
    res = G.captcha(uid)
    assert res["ok"], res
    return res["token"]


def test_a_found_gstin_is_normalised_cached_and_asked_for_once(net):
    token = start()
    res = G.lookup(GOOD, "123456", token, "u1")
    assert res["ok"] and res["cached"] is False
    r = res["result"]
    assert (r["legal_name"], r["trade_name"], r["status"], r["active"]) == (
        "EXAMPLE TRADERS PRIVATE LIMITED", "EXAMPLE FIRE SYSTEMS", "Active", True)
    assert (r["constitution"], r["taxpayer_type"], r["registration_date"]) == (
        "Private Limited Company", "Regular", "2017-07-01")
    assert r["address"]["pincode"] == "400078" and r["source"] == "GST portal"
    searches = net.to(G.SEARCH_URL)
    assert len(searches) == 1
    assert json.loads(searches[0]["data"]) == {"gstin": GOOD, "captcha": "123456"}
    assert searches[0]["method"] == "POST"
    # the search rides on the SAME cookie jar the CAPTCHA was fetched with
    assert searches[0]["jar"] is net.to(G.CAPTCHA_URL)[0]["jar"]
    assert G.cached(GOOD)["legal_name"] == "EXAMPLE TRADERS PRIVATE LIMITED"


def test_a_wrong_captcha_asks_for_a_fresh_one_and_spends_the_session(net, key):
    net.search = js(WRONG_CAPTCHA)
    token = start()
    res = G.lookup(GOOD, "000000", token, "u1")
    assert res == {"ok": False, "error": "captcha", "refresh_captcha": True,
                   "message": "That CAPTCHA was not right — here is a fresh one."}
    assert net.to("https://www.gstinapi.in/") == []      # not a portal FAILURE
    again = G.lookup(GOOD, "000000", token, "u1")
    assert again["error"] == "expired" and again["refresh_captcha"]
    assert len(net.to(G.SEARCH_URL)) == 1


def test_an_unknown_gstin_is_not_found_and_not_sent_to_the_fallback(net, key):
    net.search = js(NO_SUCH_GSTIN)
    res = G.lookup(GOOD, "123456", start(), "u1")
    assert res["error"] == "not_found"
    assert net.to("https://www.gstinapi.in/") == []
    assert G.cached(GOOD) is None


@pytest.mark.parametrize("failure", [
    socket.timeout("timed out"), TimeoutError("timed out"),
    http.client.RemoteDisconnected("Remote end closed connection without response"),
    ConnectionRefusedError(), (500, "text/html", b"<html>maintenance</html>"),
    (200, "text/html", b"<html>not json</html>"),
], ids=["socket-timeout", "timeout", "dropped", "refused", "http-500", "html"])
def test_a_portal_that_does_not_answer_says_enter_manually(net, failure):
    net.search = failure
    res = G.lookup(GOOD, "123456", start(), "u1")
    assert res == {"ok": False, "error": "unavailable", "refresh_captcha": False,
                   "message": "Auto-fill unavailable, enter manually."}
    assert G.cached(GOOD) is None


@pytest.mark.parametrize("change", [
    {"lgnm": None}, {"sts": ""}, {"pradr": {"addr": {"pncd": "400078"}}},
    {"pradr": "flat string"}, {"gstin": OTHER},
], ids=["no-legal-name", "no-status", "structured-address", "address-not-object",
        "a-different-gstin"])
def test_a_changed_response_shape_is_a_failure_never_a_blank_fill(net, change):
    body = portal_body()
    body.update(change)
    if change.get("lgnm", 1) is None:
        body.pop("lgnm")
        body["legalName"] = "RENAMED KEY PVT LTD"
    net.search = js(body)
    res = G.lookup(GOOD, "123456", start(), "u1")
    assert res["error"] == "unavailable"


def test_the_portals_latin_1_label_is_survived(net):
    body = json.dumps(portal_body(lgnm="SHRÉE TRADERS")).encode("latin-1")
    net.search = (200, "application/json", body)
    assert G.lookup(GOOD, "123456", start(), "u1")["result"]["legal_name"] == "SHRÉE TRADERS"


def test_a_captcha_that_is_not_six_digits_is_not_sent_and_not_spent(net):
    token = start()
    res = G.lookup(GOOD, "12345", token, "u1")
    assert res["error"] == "captcha_format"
    assert net.to(G.SEARCH_URL) == []
    assert G.lookup(GOOD, "123456", token, "u1")["ok"]


def test_an_invalid_gstin_never_leaves_the_building(net):
    res = G.lookup(GOOD[:14] + "0" if GOOD[14] != "0" else GOOD[:14] + "1", "123456",
                   start(), "u1")
    assert res["error"] == "invalid"
    assert net.to(G.SEARCH_URL) == []


def test_a_captcha_response_that_is_not_an_image_is_a_failure(net):
    net.captcha = (200, "text/html", b"<html>blocked</html>")
    res = G.captcha("u1")
    assert res["ok"] is False and res["error"] == "unavailable"


# ═══ 5. The fallback — only after the portal fails, and only with a key ═════

FALLBACK_DATA = {"gstin": GOOD, "legal_name": "EXAMPLE TRADERS PRIVATE LIMITED",
                 "trade_name": "EXAMPLE FIRE SYSTEMS", "status": "Active",
                 "taxpayer_type": "Regular", "business_constitution": None,
                 "registration_date": "2017-07-01", "cancellation_date": None,
                 "state_code": "27", "address": "UNIT 4, LBS MARG, Bhandup, Mumbai",
                 "pincode": "400078"}


def test_a_healthy_portal_never_reaches_the_fallback(net, key):
    assert G.lookup(GOOD, "123456", start(), "u1")["result"]["source"] == "GST portal"
    assert net.to("https://www.gstinapi.in/") == []


def test_a_failed_portal_goes_to_the_fallback_after_it_and_sends_the_key(net, key):
    net.search = socket.timeout()
    net.fallback = js({"success": True, "data": FALLBACK_DATA})
    res = G.lookup(GOOD, "123456", start(), "u1")
    assert res["ok"] and res["result"]["source"] == "gstinapi.in"
    urls = [c["url"] for c in net.calls]
    assert urls.index(G.SEARCH_URL) < urls.index(f"https://www.gstinapi.in/v1/gstin/{GOOD}")
    call = net.to("https://www.gstinapi.in/")[0]
    assert {k.lower(): v for k, v in call["headers"].items()}["x-api-key"] == "gak_test_key_not_real"
    assert res["result"]["address"]["pincode"] == "400078"
    assert G.cached(GOOD)["source"] == "gstinapi.in"


def test_without_a_key_the_fallback_is_never_called(net):
    net.search = socket.timeout()
    res = G.lookup(GOOD, "123456", start(), "u1")
    assert res["message"] == "Auto-fill unavailable, enter manually."
    assert net.to("https://www.gstinapi.in/") == []


def test_the_fallback_reads_the_flat_envelope_too(net, key):
    net.search = socket.timeout()
    net.fallback = js(FALLBACK_DATA)
    assert G.lookup(GOOD, "123456", start(), "u1")["ok"]


@pytest.mark.parametrize("answer,code", [
    ((404, "application/json", b'{"success": false, "error": "not registered"}'), "not_found"),
    ((401, "application/json", json.dumps(FALLBACK_401).encode()), "unavailable"),
    ((502, "application/json", b'{"success": false}'), "unavailable"),
    (js({"success": True, "data": {"gstin": GOOD}}), "unavailable"),
    (socket.timeout(), "unavailable"),
], ids=["404", "401-recorded", "502", "shape", "timeout"])
def test_a_fallback_that_fails_too_says_so(net, key, answer, code):
    net.search = socket.timeout()
    net.fallback = answer
    assert G.lookup(GOOD, "123456", start(), "u1")["error"] == code


def test_a_captcha_that_would_not_load_lets_the_same_user_reach_the_fallback(net, key):
    net.captcha = http.client.RemoteDisconnected("dropped")
    cap = G.captcha("u1")
    assert cap["ok"] is False and cap["fallback"] is True and cap["token"]
    net.fallback = js({"success": True, "data": FALLBACK_DATA})
    res = G.lookup(GOOD, "", cap["token"], "u1")
    assert res["ok"] and res["result"]["source"] == "gstinapi.in"
    assert net.to(G.SEARCH_URL) == []


def test_a_browser_cannot_ask_for_the_fallback_by_itself(net, key):
    """The fallback costs money. Only a failure THIS SERVER saw opens it."""
    token = start()                                   # a healthy session
    assert G.lookup(GOOD, "", token, "u1")["error"] == "captcha_required"
    assert G.lookup(GOOD, "", "", "u1")["error"] == "captcha_required"
    assert G.lookup(GOOD, "", "made-up-token", "u1")["error"] == "captcha_required"
    net.captcha = socket.timeout()
    down = G.captcha("u2")["token"]                   # somebody ELSE's failure
    assert G.lookup(GOOD, "", down, "u1")["error"] == "captcha_required"
    assert net.to("https://www.gstinapi.in/") == []


# ═══ 6. The cache ════════════════════════════════════════════════════════════

def test_a_fresh_hit_fills_with_no_captcha_and_no_network(net):
    plant(age_days=29)
    res = G.lookup(GOOD, "", "", "u1")
    assert res["ok"] and res["cached"] is True
    assert net.calls == []


def test_a_hit_older_than_thirty_days_asks_for_a_captcha(net):
    plant(age_days=31)
    assert G.cached(GOOD) is None
    assert G.lookup(GOOD, "", "", "u1")["error"] == "captcha_required"


def test_refresh_skips_a_fresh_hit_and_a_captcha_always_goes_to_the_portal(net):
    plant(legal_name="OLD NAME")
    assert G.lookup(GOOD, "", "", "u1", refresh=True)["error"] == "captcha_required"
    res = G.lookup(GOOD, "123456", start(), "u1")
    assert res["cached"] is False and res["result"]["legal_name"] != "OLD NAME"
    assert G.cached(GOOD)["legal_name"] == "EXAMPLE TRADERS PRIVATE LIMITED"


@pytest.mark.parametrize("ts", [None, "yesterday", float("nan"), 1e18],
                         ids=["none", "text", "nan", "future"])
def test_an_unreadable_or_future_timestamp_is_stale_never_fresh(ts):
    """⚠ `nan` is the case that FOUND a bug: every comparison with NaN is
    False, so `age < 0 or age > limit` called a NaN row fresh."""
    plant()
    STORE["gst_cache"][GOOD]["fetched_ts"] = ts
    assert G.cached(GOOD) is None


def test_the_cache_holds_the_result_and_nothing_of_the_session(net):
    token = start()
    G.lookup(GOOD, "654321", token, "u1")
    row = STORE["gst_cache"][GOOD]
    assert set(row) == {"id", "gstin", "result", "fetched_at", "fetched_ts", "source"}
    blob = db._blob(row)
    for secret in (token, "654321", "CaptchaCookie", "TS0134d082", "Cookie"):
        assert secret not in blob


def test_no_portal_session_ever_reaches_the_persisted_store(net):
    token = start()
    everything = "".join(db._blob(STORE.get(c)) for c in db.COLLECTIONS)
    assert token not in everything
    assert "gst_cache" in db.COLLECTIONS and "gst_cache" in db.LABELS


# ═══ 7. Sessions and limits ══════════════════════════════════════════════════

def test_a_session_belongs_to_the_user_who_started_it(net):
    token = start("u1")
    assert G.lookup(GOOD, "123456", token, "u2")["error"] == "expired"
    assert G.lookup(GOOD, "123456", token, "u1")["ok"]


def test_a_session_expires_after_five_minutes(net, monkeypatch):
    token = start()
    now = G._now_ts()
    monkeypatch.setattr(G, "_now_ts", lambda: now + G.SESSION_TTL + 1)
    assert G.lookup(GOOD, "123456", token, "u1")["error"] == "expired"
    assert token not in G._SESSIONS                  # pruned on access


def test_ten_searches_a_minute_per_user_and_the_window_slides(net, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(G, "time", types.SimpleNamespace(
        monotonic=lambda: clock[0], time=lambda: 1.8e9))
    net.search = js(WRONG_CAPTCHA)

    def fresh(uid):
        """A session whose CAPTCHA fetch is not counted — this test is about
        the SEARCH bucket, and the CAPTCHA bucket has the same limit."""
        token = start(uid)
        G._CALLS.pop(("captcha", uid), None)
        return token

    for _ in range(G.RATE_LIMIT):
        assert G.lookup(GOOD, "000000", fresh("u1"), "u1")["error"] == "captcha"
    assert G.lookup(GOOD, "000000", fresh("u1"), "u1")["error"] == "rate_limited"
    assert G.lookup(GOOD, "000000", fresh("u2"), "u2")["error"] == "captcha"
    clock[0] += G.RATE_WINDOW + 1
    assert G.lookup(GOOD, "000000", fresh("u1"), "u1")["error"] == "captcha"


def test_captcha_reloads_are_limited_without_losing_the_one_on_screen(net, monkeypatch):
    monkeypatch.setattr(G, "time", types.SimpleNamespace(monotonic=lambda: 5.0, time=lambda: 1.8e9))
    tokens = [G.captcha("u1", "")["token"] for _ in range(G.RATE_LIMIT)]
    refused = G.captcha("u1", tokens[-1])
    assert refused["error"] == "rate_limited" and refused["token"] == tokens[-1]
    assert G._session(tokens[-1], "u1") is not None


# ═══ 8. One attempt, five seconds, honest headers ════════════════════════════

def test_the_suite_cannot_reach_the_portal():
    """
    `conftest._no_gst_network` is in force for a test that asked for nothing.

    ⚠ **The identity check comes FIRST, and that order is the point.** If the
      conftest refusal is ever removed, `G._open` IS the real function and this
      test fails on that line — before the call below could open a socket to a
      government portal from CI.
    """
    assert G._open is not REAL_OPEN
    with pytest.raises(OSError):
        G._open(G.CAPTCHA_URL)
    assert G.captcha("u1")["error"] == "unavailable"


def test_every_outbound_call_carries_the_five_second_timeout(monkeypatch):
    seen = []

    class Opener:
        addheaders = []

        def open(self, request, timeout=None):
            seen.append(timeout)
            raise socket.timeout()

    monkeypatch.setattr(G.urllib.request, "build_opener", lambda *h: Opener())
    with pytest.raises(socket.timeout):
        REAL_OPEN("https://example.invalid/")
    assert seen == [5] and G.TIMEOUT == 5


def _gst_tree():
    return ast.parse((REPO / "gst_lookup.py").read_text(encoding="utf8"))


def test_only_open_touches_the_network_and_it_is_called_three_times():
    """One choke point — what conftest's refusal replaces — and no loops."""
    tree = _gst_tree()
    opens = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            f = call.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in ("open", "urlopen"):
                assert fn.name == "_open", f"{fn.name} opens a URL itself"
            if name == "_open":
                opens.append(fn.name)
                for loop in (n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.While))):
                    assert call not in list(ast.walk(loop)), f"{fn.name} retries"
    assert sorted(opens) == ["_fallback_search", "_portal_search", "captcha"]


def test_no_retry_one_call_per_attempt_even_when_it_fails(net, key):
    net.captcha = socket.timeout()
    G.captcha("u1")
    assert len(net.to(G.CAPTCHA_URL)) == 1
    net.captcha = (200, "image/png", PNG)
    net.search = socket.timeout()
    net.fallback = socket.timeout()
    G.lookup(GOOD, "123456", start(), "u1")
    assert len(net.to(G.SEARCH_URL)) == 1 and len(net.to("https://www.gstinapi.in/")) == 1


def test_the_headers_are_honest(net):
    G.lookup(GOOD, "123456", start(), "u1")
    assert "SamruddhiQMS" in G.USER_AGENT and "Mozilla" not in G.USER_AGENT
    sent = {k.lower() for k in net.to(G.SEARCH_URL)[0]["headers"]}
    assert not sent & {"referer", "origin", "x-requested-with", "cookie"}


FORBIDDEN_LIBS = {"pytesseract", "tesserocr", "easyocr", "cv2", "keras", "torch",
                  "tensorflow", "twocaptcha", "anticaptchaofficial", "capsolver",
                  "requests", "httpx", "aiohttp", "bs4"}


def _imports(path):
    names = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
        if isinstance(n, ast.Import):
            names |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module)
    return names


def test_nothing_in_the_application_can_read_or_solve_a_captcha():
    """No OCR, no solving service, no scraping stack — anywhere, not only here."""
    for mod in REPO.glob("*.py"):
        roots = {i.split(".")[0] for i in _imports(mod)}
        assert not roots & FORBIDDEN_LIBS, (mod.name, roots & FORBIDDEN_LIBS)
    assert "PIL" not in {i.split(".")[0] for i in _imports(REPO / "gst_lookup.py")}


def test_only_gst_lookup_may_open_a_network_connection():
    net_libs = {"urllib.request", "http.client", "http.cookiejar", "socket"}
    offenders = sorted(m.name for m in REPO.glob("*.py")
                       if m.name != "gst_lookup.py" and _imports(m) & net_libs)
    assert offenders == [], offenders


def test_the_captcha_bytes_reach_the_browser_untouched(client, net):
    r = client.get("/address/gst/captcha")
    assert r.status_code == 200 and r.data == PNG
    assert r.headers["Content-Type"] == "image/png"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in r.headers["Cache-Control"]


# ═══ 9. Routes and permissions ═══════════════════════════════════════════════

ROUTES = {"address.gst_captcha_add": "address.create",
          "address.gst_lookup_add": "address.create",
          "address.gst_captcha_edit": "address.edit",
          "address.gst_lookup_edit": "address.edit"}


def test_the_four_routes_carry_their_forms_permissions():
    for ep, perm in ROUTES.items():
        assert auth.ROUTE_PERMISSIONS[ep] == perm


def _hit(client, which, aid):
    urls = {"address.gst_captcha_add": ("get", "/address/gst/captcha"),
            "address.gst_lookup_add": ("post", "/address/gst/lookup"),
            "address.gst_captcha_edit": ("get", f"/address/edit/{aid}/gst/captcha"),
            "address.gst_lookup_edit": ("post", f"/address/edit/{aid}/gst/lookup")}
    verb, url = urls[which]
    return getattr(client, verb)(url, data={"gstin": GOOD} if verb == "post" else None)


def test_a_role_without_the_address_permissions_is_refused_all_four(client, net):
    address.ensure_demo_addresses()
    sign_in(client, a_user("role-hr", "gst-hr"))
    for ep in ROUTES:
        assert _hit(client, ep, "b2000001-face-4000-8000-000000000001").status_code == 403, ep
    assert net.calls == []


def test_a_stranger_is_sent_to_sign_in(anon_client, net):
    for url in ("/address/gst/captcha", "/address/edit/x/gst/captcha"):
        assert anon_client.get(url).status_code == 302
    assert anon_client.post("/address/gst/lookup", data={"gstin": GOOD}).status_code == 302
    assert net.calls == []


def test_each_pair_follows_its_own_permission(client, net):
    """A custom role holding create but not edit reaches the add pair only —
    the reason there are four endpoints and not two."""
    address.ensure_demo_addresses()
    aid = "b2000001-face-4000-8000-000000000001"
    sign_in(client, a_user(a_role("role-gst-create", ["address.view", "address.create"]),
                           "gst-create-only"))
    assert _hit(client, "address.gst_captcha_add", aid).status_code == 200
    assert _hit(client, "address.gst_lookup_add", aid).status_code == 200
    assert _hit(client, "address.gst_captcha_edit", aid).status_code == 403
    assert _hit(client, "address.gst_lookup_edit", aid).status_code == 403
    sign_in(client, a_user(a_role("role-gst-edit", ["address.view", "address.edit"]),
                           "gst-edit-only"))
    assert _hit(client, "address.gst_captcha_add", aid).status_code == 403
    assert _hit(client, "address.gst_lookup_edit", aid).status_code == 200


def test_a_sales_manager_may_look_up(client, net):
    sign_in(client, a_user("role-sales-manager", "gst-sales"))
    assert client.get("/address/gst/captcha").status_code == 200


def test_the_form_draws_the_lookup_only_where_the_gate_would_allow_it(client, monkeypatch):
    """`can_reach()` is the predicate — pull the lookup out of reach and the
    CAPTCHA controls go, while the offline check and manual entry stay."""
    html = client.get("/address/add").get_data(as_text=True)
    assert 'id="gst-captcha"' in html and '"lookup": "/address/gst/lookup"' in html
    monkeypatch.setitem(auth.ROUTE_PERMISSIONS, "address.gst_lookup_add", "__nobody__")
    sign_in(client, a_user("role-sales-manager", "gst-sales2"))
    html = client.get("/address/add").get_data(as_text=True)
    assert 'id="gst-captcha"' not in html and '"lookup": null' in html
    assert 'name="gstin"' in html and "GST.offline" in html


def test_the_edit_pair_answers_gone_for_an_address_that_does_not_exist(client, net):
    r = client.get("/address/edit/no-such-id/gst/captcha")
    assert r.status_code == 410 and r.get_json()["error"] == "gone"
    assert client.post("/address/edit/no-such-id/gst/lookup",
                       data={"gstin": GOOD}).status_code == 410
    assert net.calls == []


def test_the_lookup_is_post_only_and_never_saves_an_address(client, net):
    assert client.get("/address/gst/lookup").status_code == 405
    before = copy.deepcopy(STORE["addresses"])
    client.get("/address/gst/captcha")
    r = client.post("/address/gst/lookup", data={"gstin": GOOD, "captcha": "123456"})
    assert r.get_json()["ok"] is True
    assert r.headers["Content-Type"].startswith("application/json")
    assert STORE["addresses"] == before


def test_the_portal_token_lives_in_the_signed_session_and_only_there(client, net):
    client.get("/address/gst/captcha")
    with client.session_transaction() as s:
        token = s[address.GST_SESSION_KEY]
    assert token in G._SESSIONS
    assert token not in "".join(db._blob(STORE.get(c)) for c in db.COLLECTIONS)
    client.get("/address/gst/captcha")                 # a reload replaces it
    with client.session_transaction() as s:
        assert s[address.GST_SESSION_KEY] != token
    assert token not in G._SESSIONS


def test_a_failed_captcha_answers_json_with_the_fallback_flag(client, net, key):
    net.captcha = socket.timeout()
    r = client.get("/address/gst/captcha")
    assert r.status_code == 503
    assert r.get_json() == {"ok": False, "error": "unavailable", "fallback": True,
                            "message": "Auto-fill unavailable, enter manually."}


def test_both_limits_answer_429(client, net):
    import time
    uid = auth.find_user("test-owner")["id"]
    assert client.get("/address/gst/captcha").status_code == 200
    G._CALLS[("search", uid)] = [time.monotonic()] * G.RATE_LIMIT
    r = client.post("/address/gst/lookup", data={"gstin": GOOD, "captcha": "000000"})
    assert r.status_code == 429 and r.get_json()["error"] == "rate_limited"
    G._CALLS[("captcha", uid)] = [time.monotonic()] * G.RATE_LIMIT
    r = client.get("/address/gst/captcha")
    assert r.status_code == 429 and r.get_json()["error"] == "rate_limited"
    assert net.to(G.SEARCH_URL) == []


# ═══ 10. What a save does ════════════════════════════════════════════════════

def test_a_new_gstin_must_pass_the_check_character(client):
    bad = GOOD[:14] + ("A" if GOOD[14] != "A" else "B")
    before = set(STORE["addresses"])
    html = client.post("/address/add", data=form(gstin=bad)).get_data(as_text=True)
    assert "mistyped" in html and set(STORE["addresses"]) == before


def test_a_blank_gstin_is_still_allowed(client):
    aid = new_address(client, gstin="")
    rec = STORE["addresses"][aid]
    assert rec["gstin"] == "" and "gst_status" not in rec and "gst_verified_at" not in rec


def test_a_stored_gstin_that_fails_the_check_survives_an_unrelated_edit(client):
    """INTRODUCTION.md §9 — the demo's invented GSTINs, and five live ones.

    The legacy record is planted here, written straight into the store the way
    a save before this rule wrote it, rather than borrowed from the demo book:
    other files edit the demo addresses and the book is not reset between them.
    """
    aid = "gst-legacy-address"
    legacy = GOOD[:14] + ("A" if GOOD[14] != "A" else "B")
    assert address._GSTIN_RE.match(legacy) and not G.check_digit_ok(legacy)
    STORE["addresses"][aid] = dict(form(gstin=legacy, label="Legacy Vendor",
                                        type="vendor"), id=aid, country="India")
    page = client.get(f"/address/edit/{aid}").get_data(as_text=True)
    assert "fails the check-character test" in page
    rec = dict(STORE["addresses"][aid])
    r = client.post(f"/address/edit/{aid}", data=form(
        **{k: rec.get(k, "") for k in ("label", "type", "company", "contact_name",
                                        "line1", "line2", "landmark", "city", "state",
                                        "pincode", "email", "gstin")}, phone="+91 98200 00000"))
    assert r.status_code == 302
    assert STORE["addresses"][aid]["gstin"] == legacy
    assert STORE["addresses"][aid]["phone"] == "+91 98200 00000"
    other_bad = legacy[:14] + ("A" if legacy[14] != "A" else "B")
    if G.check_digit_ok(other_bad):
        other_bad = legacy[:14] + "C"
    html = client.post(f"/address/edit/{aid}", data=form(gstin=other_bad)).get_data(as_text=True)
    assert "mistyped" in html and STORE["addresses"][aid]["gstin"] == legacy


def test_a_gstin_the_portal_lists_as_cancelled_needs_the_acknowledgement(client):
    plant(sts="Cancelled", status="Cancelled", active=False)
    before = set(STORE["addresses"])
    html = client.post("/address/add", data=form(gstin=GOOD)).get_data(as_text=True)
    assert set(STORE["addresses"]) == before
    assert "I understand this GSTIN is" in html
    assert 'id="gst-dead">' in html and 'id="gst-ack" required' in html
    aid = new_address(client, gstin=GOOD, gst_ack="1")
    rec = STORE["addresses"][aid]
    assert rec["gst_status"] == "Cancelled" and rec["gst_verified_at"]


def test_the_status_comes_from_the_server_never_from_the_form(client):
    plant(status="Suspended", active=False)
    before = set(STORE["addresses"])
    client.post("/address/add", data=form(gstin=GOOD, gst_status="Active",
                                          gst_verified_at="2099-01-01 00:00"))
    assert set(STORE["addresses"]) == before           # still gated
    aid = new_address(client, gstin=GOOD, gst_ack="1", gst_status="Active")
    assert STORE["addresses"][aid]["gst_status"] == "Suspended"


def test_an_active_or_unknown_gstin_is_not_gated(client):
    plant()
    aid = new_address(client, gstin=GOOD)
    assert STORE["addresses"][aid]["gst_status"] == "Active"
    aid2 = new_address(client, gstin=OTHER)            # never looked up
    assert "gst_status" not in STORE["addresses"][aid2]


def test_the_stamp_follows_the_gstin(client):
    plant()
    aid = new_address(client, gstin=GOOD)
    STORE["gst_cache"].clear()
    client.post(f"/address/edit/{aid}", data=form(gstin=GOOD, phone="+91 98200 11111"))
    assert STORE["addresses"][aid]["gst_status"] == "Active"   # unchanged GSTIN: kept
    client.post(f"/address/edit/{aid}", data=form(gstin=OTHER))
    rec = STORE["addresses"][aid]
    assert "gst_status" not in rec and "gst_verified_at" not in rec   # changed: dropped


def test_an_address_with_no_gst_keys_renders_everywhere(client):
    address.ensure_demo_addresses()
    for aid in STORE["addresses"]:
        for url in (f"/address/view/{aid}", f"/address/edit/{aid}"):
            assert client.get(url).status_code == 200, url
    assert client.get("/address/").status_code == 200


def test_editing_a_referenced_address_still_logs_and_logs_only_what_it_did(client, monkeypatch):
    plant()
    aid = new_address(client, gstin="")
    monkeypatch.setitem(STORE["projects"], "p-gst", {"id": "p-gst", "name": "GST Proj",
                                                      "site_address_id": aid})
    client.post(f"/address/edit/{aid}", data=form(gstin=GOOD))
    log = STORE["addresses"][aid]["edit_log"]
    assert len(log) == 1
    fields = [c["field"] for c in log[0]["changes"]]
    assert fields == ["gstin"]
    assert STORE["addresses"][aid]["gst_status"] == "Active"


# ═══ 11. Escaping — every portal-sourced field ═══════════════════════════════

PAYLOADS = ['<script>alert("gst")</script>', '"><img src=x onerror=alert(1)>',
            "</title><script>alert(2)</script>"]
PORTAL_FIELDS = ("legal_name", "trade_name", "status", "constitution", "taxpayer_type",
                 "registration_date", "address_text", "source", "fetched_at")


@pytest.mark.parametrize("payload", PAYLOADS, ids=["script", "onerror", "title"])
def test_every_portal_field_reaches_the_form_escaped(client, payload):
    aid = new_address(client, gstin=GOOD)
    plant(active=False, **{f: f"{payload} {f}" for f in PORTAL_FIELDS})
    html = client.get(f"/address/edit/{aid}").get_data(as_text=True)
    assert payload not in html
    for f in PORTAL_FIELDS:
        assert f"{address._e(payload)} {f}" in html, f


@pytest.mark.parametrize("payload", PAYLOADS, ids=["script", "onerror", "title"])
def test_the_stored_status_reaches_the_view_page_escaped(client, payload):
    aid = new_address(client, gstin=GOOD)
    STORE["addresses"][aid].update(gst_status=payload, gst_verified_at=payload)
    html = client.get(f"/address/view/{aid}").get_data(as_text=True)
    assert payload not in html
    assert address._e(payload) in html


def test_the_lookup_answer_is_json_and_never_html(client, net):
    net.search = js(portal_body(lgnm=PAYLOADS[0]))
    client.get("/address/gst/captcha")
    r = client.post("/address/gst/lookup", data={"gstin": GOOD, "captcha": "123456"})
    assert r.headers["Content-Type"].startswith("application/json")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.get_json()["result"]["legal_name"] == PAYLOADS[0]


def test_the_script_writes_portal_text_with_textcontent_only():
    wiring = address.GST_SCRIPT.split("DOMContentLoaded", 1)[1]
    assert "innerHTML" not in wiring and "insertAdjacentHTML" not in wiring
    assert "outerHTML" not in wiring and "document.write" not in wiring


# ═══ 12. The form ════════════════════════════════════════════════════════════

def test_the_gstin_is_the_first_field_on_both_forms(client):
    address.ensure_demo_addresses()
    for url in ("/address/add", "/address/edit/b2000001-face-4000-8000-000000000001"):
        html = client.get(url).get_data(as_text=True)
        field = '<input type="text" name="gstin" id="gst-input"'
        assert html.index(field) < html.index('name="label"'), url
        assert html.count('<input type="text" name="gstin"') == 1, url
        assert "GST_CFG" in html and "var GST = " in html


def test_the_captcha_box_posts_nothing_with_the_address(client):
    html = client.get("/address/add").get_data(as_text=True)
    box = html[html.index('id="gst-captcha"'):]
    box = box[:box.index("</div>")]
    assert "name=" not in box


def test_the_list_page_carries_none_of_it(client):
    """`/address/` is pinned by a page golden; the feature is form-only."""
    html = client.get("/address/").get_data(as_text=True)
    assert "gst-captcha" not in html and "GST_CFG" not in html and ".gst-box" not in html
