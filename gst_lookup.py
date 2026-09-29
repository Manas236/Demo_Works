"""
gst_lookup.py — a GSTIN checked offline, and the GST portal behind one function
================================================================================
No routes. `address.py` owns the two route pairs and every byte of HTML; this
module answers two questions and nothing else:

  * **Is this a GSTIN?** — `offline()`: the 15-character shape, the official
    base-36 check character (character 15), the State its first two digits
    name and the PAN in characters 3–12. No network, no store. The same
    arithmetic runs in the browser (`address.GST_SCRIPT`), and
    `tests/test_gst_lookup.py` runs that JavaScript under Node against this
    Python so the two cannot drift.
  * **What does the GST portal say about it?** — `lookup()`, the ONE public
    function behind which the portal call, the gstinapi.in fallback, the
    normalisation and the 30-day cache all sit. `captcha()` is the other half
    of the conversation: it starts a portal session and hands back the image.

⚠ **A HUMAN TYPES EVERY CAPTCHA.** Nothing in this module reads, decodes,
  measures or solves a CAPTCHA image. `captcha()` checks only that the bytes
  it was handed BEGIN like an image file — the same magic-byte test
  `attachment.sniff()` makes — and passes them to the browser untouched. There
  is no OCR library, no solving service and no retry loop anywhere in the
  application, and `tests/test_gst_lookup.py` asserts the absence at AST level.

⚠ **ONE ATTEMPT, `timeout=5`, NO RETRIES — on every outbound call.** With
  `gunicorn --workers 1 --threads 1` (DEPLOY.md; `series.py` is why) an
  outbound call blocks EVERY user of the application until it returns, so the
  worst case of one lookup is the sum of its calls' timeouts: 5 s for the
  CAPTCHA, 5 s for the search, 5 s more if the fallback runs. Measured from an
  Indian IP on 29 September 2026 the portal answered in 0.4–1.1 s — and
  dropped 5 of 17 connections outright (docs/GST_PORTAL.md). A dropped
  connection is a failed attempt, and a failed attempt says "Auto-fill
  unavailable, enter manually." It is not retried.

⚠ **The portal's cookie jars NEVER enter STORE or MySQL.** They live in
  `_SESSIONS`, a module-level dict in this process's RAM, keyed by a random
  token that `address.py` keeps in the signed Flask session, and they expire
  after five minutes. A jar is somebody's live session with a government
  portal; `db.sync()` would write it to a table on the next request. The one
  thing that IS persisted is `STORE["gst_cache"]`: the normalised, public
  registration details of a GSTIN and when they were fetched — never a cookie,
  a token, a CAPTCHA or a raw response.

⚠ **Honest headers.** The User-Agent names this application. There is no
  browser impersonation, no Referer or Origin, no timing jitter: step 1 of the
  build (docs/GST_PORTAL.md) proved the portal answers cookies + CAPTCHA + a
  JSON body, and nothing more is sent.

A LEAF: imports `store`, `pipeline` and the standard library, and nothing
else. `address.py` imports it; it never imports `address.py` back
(`tests/test_import_directions.py`).
"""

import http.cookiejar
import json
import os
import random
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import pipeline as P
from store import STORE


# =============================================================================
# THE OFFLINE CHECK — no network, no store
# =============================================================================

# The 36 symbols of a GSTIN, in the order the check-character arithmetic
# numbers them: '0' is 0, '9' is 9, 'A' is 10, 'Z' is 35.
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# 2-digit State code + 10-character PAN + entity number + 'Z' + check
# character — a REGULAR taxpayer's GSTIN. ⚠ This is exactly the pattern
# `address.py` validated with before this module existed, moved here rather
# than copied so the form, the save and the lookup cannot disagree about what a
# GSTIN looks like. `address._GSTIN_RE` is now this object.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")

_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
_CAPTCHA_RE = re.compile(r"^[0-9]{6}$")   # the portal's own rule: 6 digits


def check_char(first14: str) -> str:
    """
    The official check character for the first 14 characters of a GSTIN.

    Each character is its position in `ALPHABET`, multiplied by 1 at odd
    positions and 2 at even ones (counting from one); each product
    contributes its base-36 quotient plus its remainder; the check character
    is whatever brings the total to a multiple of 36.

    Raises `ValueError` on a character outside `ALPHABET` — callers check the
    shape first.
    """
    total = 0
    for i, ch in enumerate(first14):
        product = ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return ALPHABET[(36 - total % 36) % 36]


def check_digit_ok(gstin: str) -> bool:
    """Whether a GSTIN of the right shape carries the right 15th character."""
    g = str(gstin or "").strip().upper()
    if not GSTIN_RE.match(g):
        return False
    return check_char(g[:14]) == g[14]


def pan_of(gstin: str) -> str:
    """Characters 3–12: the holder's PAN. '' unless the shape is right."""
    g = str(gstin or "").strip().upper()
    return g[2:12] if GSTIN_RE.match(g) else ""


def offline(gstin) -> dict:
    """
    Everything that can be known about a GSTIN without asking anybody.

        {"gstin", "valid", "error", "state_code", "state", "pan", "note"}

    `valid` means **the shape and the check character are right** — it says
    nothing about whether the portal has ever issued it. `error` is the
    sentence the form shows when `valid` is False, `""` otherwise.

    ⚠ **A State code nobody allots today is NOT an error.** `state` is read
      through `pipeline.state_of_gstin()`, which deliberately answers `""` for
      25 and 28 (merged away) and for 97 / 99; the shape and the check
      character are still right, so the GSTIN is still valid — `note` says why
      no State was filled, and nothing is guessed.
    ⚠ **The error never names the expected check character.** A mismatch means
      one of fifteen characters is wrong, not that the fifteenth is; offering
      the "right" last character would invite exactly the wrong correction.
    """
    g = str(gstin or "").strip().upper()
    out = {"gstin": g, "valid": False, "error": "", "state_code": "",
           "state": "", "pan": "", "note": ""}
    if not g:
        return out
    if len(g) != 15:
        out["error"] = (f"A GSTIN is 15 characters; this one has {len(g)}.")
        return out
    if not GSTIN_RE.match(g):
        out["error"] = ("That is not the shape of a GSTIN: a 2-digit State "
                        "code, the 10-character PAN, an entity number, the "
                        "letter Z and a check character.")
        return out
    if check_char(g[:14]) != g[14]:
        out["error"] = ("The check character does not match, so one of the "
                        "15 characters is mistyped. Check it against the GST "
                        "certificate.")
        return out
    out.update(valid=True, state_code=g[:2], pan=g[2:12],
               state=P.state_of_gstin(g))
    if not out["state"]:
        out["note"] = (f"State code {g[:2]} is not a current State or Union "
                       f"Territory code, so no State was filled.")
    return out


# =============================================================================
# THE PORTAL — endpoints, limits, and the sessions held between two requests
# =============================================================================
#
# Every constant below was READ from the portal's own page on 29 September
# 2026 (docs/GST_PORTAL.md), not guessed: the Search Taxpayer page's
# `searchTaxpayerpreLogin()` posts `{"gstin", "captcha"}` as JSON to
# /services/api/search/taxpayerDetails, and its `captcha` directive loads
# /services/captcha?rnd=<random>. The CAPTCHA response sets both cookies the
# search needs (`TS0134d082` and `CaptchaCookie`); the page itself does not
# have to be fetched first, which was measured rather than assumed.

PORTAL = "https://services.gst.gov.in"
CAPTCHA_URL = PORTAL + "/services/captcha"
SEARCH_URL = PORTAL + "/services/api/search/taxpayerDetails"

# ⚠ Five seconds, ONE attempt, for every outbound call — the brief's rule, and
#   the reason is the single-threaded server: see the module docstring.
TIMEOUT = 5

# How long a portal session (its cookie jar) is kept between the CAPTCHA and
# the search. The portal's own CAPTCHA lives about this long.
SESSION_TTL = 300

# Per user, per rolling minute. Two buckets: SEARCHES (the portal search and
# the fallback — anything that asks somebody else about a GSTIN) and CAPTCHAS
# (fetching an image). The brief names the first; the second is ours, because
# a "reload CAPTCHA" link is an outbound call too and a held-down reload
# would otherwise block the whole single-threaded application.
RATE_LIMIT = 10
RATE_WINDOW = 60

# A cached result younger than this fills the form with no CAPTCHA at all.
CACHE_TTL_DAYS = 30

# Honest identification. See the module docstring.
USER_AGENT = "SamruddhiQMS/1.0 (address-book GSTIN lookup; human-typed CAPTCHA)"

# The portal's error codes, read from `searchtpCtrl1.0.js`. Wrong CAPTCHA
# arrives as `{"errorCode": "SWEB_9000"}`; an unknown GSTIN as
# `{"error": {"error_cd": "SWEB_9035"}}` — two envelopes, and both are real.
PORTAL_WRONG_CAPTCHA = {"SWEB_9000"}
PORTAL_NO_SUCH_GSTIN = {"SWEB_9032", "SWEB_9035"}

# The status strings the portal's own page treats as NOT live — its
# `isCxSts` expression, verbatim. Anything other than exactly "Active" is
# shown in red and needs an acknowledgement to save; this set only decides the
# wording ("cancelled" vs merely "not active").
PORTAL_DEAD_STATUSES = frozenset({
    "Cancelled", "Cancelled due to expiry of registration period",
    "Cancelled suo-moto", "Cancelled on application of Taxpayer", "Inactive",
    "Suspended", "Cancelled on Request of Taxpayer",
})

# ── The fallback — used only when the PORTAL fails and a key is configured ──
#
# gstinapi.in, read from https://gstinapi.in/docs on 29 September 2026:
# `GET /v1/gstin/{gstin}` with the key in an `x-api-key` header. ⚠ **This
# adapter is UNPROVEN against a live key** — none was available to the build.
# Its own two pages disagree about the envelope (a flat object on the home
# page, `{"success", "data": {...}}` in the reference), so both are accepted
# and anything else is a shape mismatch. Its real keyless answer was measured:
# HTTP 401, `{"error": "...", "fix": "..."}` — no `success` key at all.
FALLBACK_URL = "https://www.gstinapi.in/v1/gstin/{gstin}"
# ⚠ Read with the LITERAL name at both call sites, never through a
#   constant: `tests/test_deployment_config.py` finds environment variables
#   by their `os.getenv("...")` literals, and a name behind a constant is a
#   variable that sweep cannot see and `.env.example` need not list.
FALLBACK_KEY_ENV = "GST_API_KEY"

# token -> {"jar", "user_id", "created", "portal_down"}. RAM only — see above.
_SESSIONS: dict = {}
# (bucket, user_id) -> [monotonic timestamps within the window]
_CALLS: dict = {}
# Held only around dict reads and writes, NEVER across a network call.
_LOCK = threading.Lock()
# A hard ceiling on held sessions, whatever the rate limit lets through.
_MAX_SESSIONS = 500


def _now_ts() -> float:
    return time.time()


def _prune(now: float) -> None:
    """Drop expired sessions. Caller holds `_LOCK`."""
    for tok in [t for t, e in _SESSIONS.items()
                if now - e["created"] > SESSION_TTL]:
        _SESSIONS.pop(tok, None)
    while len(_SESSIONS) > _MAX_SESSIONS:
        oldest = min(_SESSIONS, key=lambda t: _SESSIONS[t]["created"])
        _SESSIONS.pop(oldest, None)


def _allow(bucket: str, user_id: str) -> bool:
    """Record one call for this user in this bucket, or refuse it."""
    now = time.monotonic()
    key = (bucket, str(user_id or ""))
    with _LOCK:
        recent = [t for t in _CALLS.get(key, []) if now - t < RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            _CALLS[key] = recent
            return False
        recent.append(now)
        _CALLS[key] = recent
        return True


def _session(token: str, user_id: str) -> dict | None:
    """A live session this user owns, or None. Prunes on the way in."""
    with _LOCK:
        _prune(_now_ts())
        entry = _SESSIONS.get(str(token or ""))
        if entry and entry["user_id"] == str(user_id or ""):
            return entry
        return None


def forget(token: str) -> None:
    """Drop a session — a new CAPTCHA replaces the old one."""
    with _LOCK:
        _SESSIONS.pop(str(token or ""), None)


# The most any response is read into memory. A CAPTCHA is ~5 KB and a search
# body under 1 KB (measured); a portal error page is not worth more than this.
MAX_BODY = 200_000


def _open(request, jar=None) -> tuple:
    """
    **THE ONE PLACE THIS MODULE TOUCHES THE NETWORK.** `(status, content_type,
    body)` for any HTTP answer, error statuses included; a timeout, a refused
    or dropped connection or a TLS failure RAISES, and every caller treats a
    raise as "the far end did not answer".

    ⚠ It is one function so it can be replaced whole: `tests/conftest.py`
      swaps it for a refusal around EVERY test, so no route sweep in the suite
      can reach the real portal, and `tests/test_gst_lookup.py` swaps it for
      recorded answers. An AST test holds that nothing else in this module
      opens a URL.
    ⚠ `timeout=TIMEOUT`, one call, no retry — here, so no caller can forget.
    """
    handlers = [urllib.request.HTTPCookieProcessor(jar)] if jar is not None else []
    op = urllib.request.build_opener(*handlers)
    op.addheaders = [("User-Agent", USER_AGENT)]
    try:
        resp = op.open(request, timeout=TIMEOUT)
        status, headers, body = resp.status, resp.headers, resp.read(MAX_BODY)
    except urllib.error.HTTPError as e:
        status, headers, body = e.code, e.headers, e.read(MAX_BODY)
    ctype = str((headers or {}).get("Content-Type") or "").split(";")[0].strip()
    return status, ctype, body


def _looks_like_an_image(data: bytes) -> bool:
    """The first bytes of a PNG, JPEG or GIF — the type check, and all of it."""
    return (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
            or data[:6] in (b"GIF87a", b"GIF89a"))


def captcha(user_id: str, old_token: str = "") -> dict:
    """
    Start a portal session and fetch its CAPTCHA image.

        {"ok": True,  "token", "image": <bytes>, "content_type"}
        {"ok": False, "token", "error", "message", "fallback"}

    ⚠ The token is returned EVEN ON FAILURE, and the session is kept marked
      `portal_down`: that mark is the only thing that lets a following
      `lookup()` with no CAPTCHA go to the fallback. A browser cannot ask for
      the fallback by itself — it can only report that the server itself just
      failed to reach the portal, and the server remembers whether it did.
    """
    uid = str(user_id or "")
    if not _allow("captcha", uid):
        # Refused BEFORE the old session is touched: the CAPTCHA already on
        # screen stays answerable.
        return {"ok": False, "token": str(old_token or ""), "error": "rate_limited",
                "message": _RATE_MESSAGE, "fallback": False}
    forget(old_token)
    token = secrets.token_urlsafe(24)

    jar = http.cookiejar.CookieJar()
    image, ctype = b"", ""
    try:
        status, ctype, image = _open(f"{CAPTCHA_URL}?rnd={random.random()}", jar)
        good = status == 200 and _looks_like_an_image(image)
    except Exception:   # timeout, refusal, a dropped connection, TLS — all one answer
        good = False

    with _LOCK:
        _prune(_now_ts())
        _SESSIONS[token] = {"jar": jar, "user_id": uid, "created": _now_ts(),
                            "portal_down": not good}
    if good:
        return {"ok": True, "token": token, "image": image,
                "content_type": ctype or "image/png"}
    return {"ok": False, "token": token, "error": "unavailable",
            "message": _UNAVAILABLE_MESSAGE, "fallback": fallback_configured()}


# =============================================================================
# THE ONE PUBLIC LOOKUP
# =============================================================================

_UNAVAILABLE_MESSAGE = "Auto-fill unavailable, enter manually."
_RATE_MESSAGE = ("Too many GSTIN lookups in the last minute — wait a moment, "
                 "or enter the details by hand.")


def _err(code: str, message: str, *, refresh: bool = False) -> dict:
    return {"ok": False, "error": code, "message": message,
            "refresh_captcha": refresh}


def fallback_configured() -> bool:
    """Whether `GST_API_KEY` is set. Read per call, so a test can set it."""
    return bool(str(os.getenv("GST_API_KEY") or "").strip())


def lookup(gstin, captcha_answer: str = "", token: str = "",
           user_id: str = "", refresh: bool = False) -> dict:
    """
    Registration details for a GSTIN, or why not. THE ONE PUBLIC FUNCTION.

    Order of answering, and each step is a decision:

    1. **The offline check.** A GSTIN that fails it never leaves the building.
    2. **No CAPTCHA posted** — the browser asks this the moment the 15th
       character is typed:
         * a cached result under 30 days old is returned at once, with no
           CAPTCHA (unless `refresh`, which is the "refresh" link);
         * if THIS user's session saw the portal fail and a fallback key is
           set, the fallback is asked;
         * otherwise `captcha_required` — the page loads a CAPTCHA.
    3. **A CAPTCHA posted** — the portal is asked ONCE, with the session's own
       cookie jar, and the session is spent whatever happens: the portal
       rotates `CaptchaCookie` on every search, so a second search on the same
       jar is a wrong CAPTCHA by construction.
         * wrong CAPTCHA → `captcha`, `refresh_captcha: True`;
         * unknown GSTIN → `not_found`;
         * a timeout, an error, or a body whose shape is not the one measured
           → the fallback if a key is set, else `unavailable`.

    Success is `{"ok": True, "result": {...}, "cached": bool}`; the result
    shape is `_result()`'s. Every success is written to the cache.
    """
    uid = str(user_id or "")
    check = offline(gstin)
    if not check["valid"]:
        return _err("invalid", check["error"] or "Type a 15-character GSTIN.")
    g = check["gstin"]

    answer = str(captcha_answer or "").strip()
    if not answer:
        if not refresh:
            hit = cached(g)
            if hit:
                return {"ok": True, "result": hit, "cached": True}
        entry = _session(token, uid)
        if entry and entry["portal_down"] and fallback_configured():
            forget(token)
            return _via_fallback(g, uid, portal_failed=True)
        return _err("captcha_required", "Type the CAPTCHA to fetch the details.")

    if not _CAPTCHA_RE.match(answer):
        # The portal's own rule. Not spent: the image on screen is still valid.
        return _err("captcha_format", "The CAPTCHA is the 6 digits in the picture.")

    entry = _session(token, uid)
    if not entry or entry["portal_down"]:
        # No session, somebody else's, expired — or one whose image never
        # loaded, so there is no CAPTCHA the answer could be FOR.
        return _err("expired", "That CAPTCHA has expired — here is a fresh one.",
                    refresh=True)
    forget(token)
    if not _allow("search", uid):
        return _err("rate_limited", _RATE_MESSAGE)

    body = _portal_search(entry["jar"], g, answer)
    if body is None:
        return _via_fallback(g, uid, portal_failed=True, counted=True)

    if (_error_codes(body) & PORTAL_WRONG_CAPTCHA):
        return _err("captcha", "That CAPTCHA was not right — here is a fresh one.",
                    refresh=True)
    if _error_codes(body) & PORTAL_NO_SUCH_GSTIN:
        return _err("not_found", "The GST portal has no taxpayer with this GSTIN. "
                                 "Check it against the certificate.")

    result = _from_portal(body, g)
    if result is None:
        return _via_fallback(g, uid, portal_failed=True, counted=True)
    _remember(result)
    return {"ok": True, "result": result, "cached": False}


def _error_codes(body: dict) -> set:
    """
    Every error code in a portal body, from EITHER envelope.

    Both were measured: a wrong CAPTCHA is `{"errorCode": "SWEB_9000", ...}`
    at the top level; an unknown GSTIN is `{"error": {"error_cd":
    "SWEB_9035", ...}}`, nested. The portal's own page checks both.
    """
    codes = {_s(body.get("errorCode"))}
    nested = body.get("error")
    if isinstance(nested, dict):
        codes.add(_s(nested.get("error_cd")))
    codes.discard("")
    return codes


def _portal_search(jar, gstin: str, answer: str) -> dict | None:
    """One POST to the portal. The parsed JSON object, or None on any failure."""
    req = urllib.request.Request(
        SEARCH_URL, method="POST",
        data=json.dumps({"gstin": gstin, "captcha": answer}).encode("utf-8"),
        headers={"Content-Type": "application/json;charset=utf-8",
                 "Accept": "application/json, text/plain, */*"})
    try:
        status, _ctype, raw = _open(req, jar)
    except Exception:
        return None
    return _json_object(raw) if status == 200 else None


def _json_object(raw: bytes) -> dict | None:
    """
    Parse a response body into a dict, or None.

    ⚠ The portal labels its JSON `charset=ISO-8859-1` (measured). JSON is
      UTF-8 by definition, so UTF-8 is tried first and Latin-1 — which can
      decode any byte sequence — second.
    """
    for enc in ("utf-8", "latin-1"):
        try:
            data = json.loads(raw.decode(enc))
            return data if isinstance(data, dict) else None
        except (UnicodeDecodeError, ValueError):
            continue
    return None


def _via_fallback(gstin: str, uid: str, *, portal_failed: bool,
                  counted: bool = False) -> dict:
    """The portal failed. Ask gstinapi.in if a key is set; else say so."""
    if not fallback_configured():
        return _err("unavailable", _UNAVAILABLE_MESSAGE)
    if not counted and not _allow("search", uid):
        return _err("rate_limited", _RATE_MESSAGE)
    outcome = _fallback_search(gstin)
    if outcome == "not_found":
        return _err("not_found", "No taxpayer is registered under this GSTIN.")
    if outcome is None:
        return _err("unavailable", _UNAVAILABLE_MESSAGE)
    _remember(outcome)
    return {"ok": True, "result": outcome, "cached": False}


def _fallback_search(gstin: str):
    """One GET to gstinapi.in: a result, "not_found", or None."""
    key = str(os.getenv("GST_API_KEY") or "").strip()
    req = urllib.request.Request(
        FALLBACK_URL.format(gstin=urllib.parse.quote(gstin)),
        headers={"x-api-key": key, "Accept": "application/json",
                 "User-Agent": USER_AGENT})
    try:
        status, _ctype, raw = _open(req)
    except Exception:
        return None
    if status == 404:
        # Its documented "GSTIN not registered". Every other failure —
        # 400/401/402/403/429/502 — is "we could not find out", not "no".
        return "not_found"
    body = _json_object(raw) if status == 200 else None
    return _from_fallback(body, gstin) if body is not None else None


# =============================================================================
# NORMALISATION — one result shape, whoever answered
# =============================================================================

def _s(value) -> str:
    """A field as a stripped string; anything that is not a string is ''."""
    return value.strip() if isinstance(value, str) else ""


def _iso_date(text: str) -> str:
    """'28/01/2020' or '2020-01-28' → '2020-01-28'; anything else as it came."""
    t = _s(text)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return t


def split_address(text: str) -> dict:
    """
    The portal's ONE-LINE principal address, split into the address book's
    fields — a heuristic, and every part of it is declared.

    ⚠ **The portal does not return a structured address.** Measured on
      29 September 2026: `pradr` carries a single key, `adr`, one string of
      comma-separated parts in the order floor, number, building, street,
      locality, city, district, State, PIN — with the empty ones left out.
      Nothing marks which part is which.

    So only the two ENDS are read with confidence: the last part is the PIN
    (six digits, not starting with 0) and the one before it is the State (a
    name in `pipeline.GST_STATE_CODES`). If either is missing the string is
    not the shape measured and **nothing is split** — `split` is False and the
    page shows the address as the portal wrote it.

    Past those two, the rest is a guess the form flags for review: the last
    remaining part is taken as the DISTRICT and dropped (the book has no
    district field), the one before it as the CITY, and what is left is
    halved into line 1 and line 2 at a comma. Where fewer than two parts are
    left beside the district, the district is the city.
    """
    blank = {"line1": "", "line2": "", "city": "", "state": "", "pincode": "",
             "split": False}
    parts = [p.strip() for p in _s(text).split(",") if p.strip()]
    if len(parts) < 2 or not _PIN_RE.match(parts[-1]) \
            or parts[-2] not in P.GST_STATE_CODES:
        return blank
    pincode, state = parts[-1], parts[-2]
    rest = parts[:-2]
    district = rest.pop() if rest else ""
    if len(rest) >= 2:
        city = rest.pop()
    else:
        city = district
    half = (len(rest) + 1) // 2
    return {"line1": ", ".join(rest[:half]), "line2": ", ".join(rest[half:]),
            "city": city, "state": state, "pincode": pincode, "split": True}


def _result(*, gstin, legal_name, trade_name, status, constitution,
            taxpayer_type, registration_date, cancellation_date,
            address_text, source) -> dict:
    """The one result shape. The cache holds exactly this."""
    return {
        "gstin":             gstin,
        "legal_name":        legal_name,
        "trade_name":        trade_name,
        "status":            status,
        "active":            status == "Active",
        "cancelled":         status in PORTAL_DEAD_STATUSES,
        "constitution":      constitution,
        "taxpayer_type":     taxpayer_type,
        "registration_date": _iso_date(registration_date),
        "cancellation_date": _iso_date(cancellation_date),
        "state":             P.state_of_gstin(gstin),
        "address_text":      address_text,
        "address":           split_address(address_text),
        "source":            source,
        "fetched_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _from_portal(body: dict, gstin: str) -> dict | None:
    """
    The portal's success body, or None if it is not the shape measured.

    ⚠ **The shape test is the fallback's trigger**, so it is strict about the
      four keys the form depends on — `gstin` (and it must be THIS gstin),
      `lgnm`, `sts` and `pradr.adr` — and lenient about the rest. A portal
      release that renames `lgnm` must fall through to the fallback or to
      "enter manually", never fill a form with blanks.
    """
    pradr = body.get("pradr")
    if (_s(body.get("gstin")).upper() != gstin or not _s(body.get("lgnm"))
            or not _s(body.get("sts")) or not isinstance(pradr, dict)
            or not _s(pradr.get("adr"))):
        return None
    return _result(gstin=gstin, legal_name=_s(body.get("lgnm")),
                   trade_name=_s(body.get("tradeNam")),
                   status=_s(body.get("sts")),
                   constitution=_s(body.get("ctb")),
                   taxpayer_type=_s(body.get("dty")),
                   registration_date=_s(body.get("rgdt")),
                   cancellation_date=_s(body.get("cxdt")),
                   address_text=_s(pradr.get("adr")),
                   source="GST portal")


def _from_fallback(body: dict, gstin: str) -> dict | None:
    """gstinapi.in's body — flat or under `data` — or None. See FALLBACK_URL."""
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    if (_s(data.get("gstin")).upper() != gstin or not _s(data.get("legal_name"))
            or not _s(data.get("status"))):
        return None
    address = _s(data.get("address"))
    pin = _s(data.get("pincode"))
    if address and pin and not address.endswith(pin):
        # Its `address` is documented without the State and PIN; add them so
        # `split_address()` reads it the way it reads the portal's.
        state = P.state_of_gstin(gstin)
        address = ", ".join(x for x in (address, state, pin) if x)
    return _result(gstin=gstin, legal_name=_s(data.get("legal_name")),
                   trade_name=_s(data.get("trade_name")),
                   status=_s(data.get("status")),
                   constitution=_s(data.get("business_constitution")),
                   taxpayer_type=_s(data.get("taxpayer_type")),
                   registration_date=_s(data.get("registration_date")),
                   cancellation_date=_s(data.get("cancellation_date")),
                   address_text=address, source="gstinapi.in")


# =============================================================================
# THE CACHE — STORE["gst_cache"], keyed by GSTIN
# =============================================================================

def _remember(result: dict) -> None:
    """
    Write a normalised result to the cache.

    ⚠ Only the normalised result goes in — public registration details and
      when they were fetched. Never a cookie, a token, a CAPTCHA or the raw
      body.
    """
    g = result["gstin"]
    STORE.setdefault("gst_cache", {})[g] = {
        "id": g, "gstin": g, "result": result,
        "fetched_at": result["fetched_at"], "fetched_ts": _now_ts(),
        "source": result["source"],
    }


def cached(gstin, max_age_days: float = CACHE_TTL_DAYS) -> dict | None:
    """
    The cached result for a GSTIN if it is younger than `max_age_days`.

    A row whose timestamp cannot be read is treated as stale, never as fresh.

    ⚠ **The test is written as "inside the window", not "outside it".** A NaN
      timestamp makes every comparison False, so `age < 0 or age > limit`
      would call a NaN row FRESH — found by `tests/test_gst_lookup.py`. A
      timestamp in the future is refused for the same reason: a row that
      claims to be fetched tomorrow would never expire.
    """
    g = str(gstin or "").strip().upper()
    row = (STORE.get("gst_cache") or {}).get(g)
    if not isinstance(row, dict) or not isinstance(row.get("result"), dict):
        return None
    try:
        age = _now_ts() - float(row.get("fetched_ts"))
    except (TypeError, ValueError):
        return None
    if not 0 <= age <= max_age_days * 86400:
        return None
    return row["result"]
