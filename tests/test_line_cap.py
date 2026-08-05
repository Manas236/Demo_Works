"""
The 600-line cap on a BOQ, and the 413 backstop behind it.

Why a cap exists at all, and why it belongs to this round rather than being a
separate tidy-up: the whole BOQ is stored as one JSON document in a single
MySQL column (ABOUT.md §4). A record the server will not accept is a record
that can never be written — and since sync() now RETRIES a failed collection on
every request instead of giving up, such a record would be re-offered and
re-refused forever, keeping the persistence strip lit and burning a round trip
per request. Task 1 made failure survivable; this is what stops it being
permanent.

Two layers, and the difference between them matters:

- `boq._clean_lines()` rejects 601 lines the way it rejects a missing item
  number — re-render, nothing lost, the offending line named and forced open.
  This is the defence, and it means the request never becomes a 413.
- The 413 handler catches what bypasses the form, plus the one case the line
  cap cannot cover: 600 legal lines that happen to serialise past Flask's
  MAX_FORM_MEMORY_SIZE. It cannot give the work back — Werkzeug rejects the
  body before the form is parsed — so it says so rather than pretending.
"""

import json

import pytest

from store import STORE
from test_boq import FORM, line


MAX = 600


def payload(n_lines: int) -> dict:
    """A well-formed BOQ of exactly n priced lines, one section, no areas."""
    return {
        "sections": [{"code": "A", "title": "Sprinkler system", "areas": []}],
        "lines": [
            dict(line(str(i + 1), f"Line {i + 1} - 100mm dia MS pipe, ISI marked",
                      "Mtrs.", None, None, "1000", "10", "1100", "500", "0", "500"),
                 total_qty="10")
            for i in range(n_lines)
        ],
    }


def post(client, n_lines: int):
    return client.post("/boq/create",
                       data=dict(FORM, boq_json=json.dumps(payload(n_lines))))


def boot_of(html: str) -> dict:
    """The editor model the rejected page re-rendered with."""
    start = html.index("var MODEL = ") + len("var MODEL = ")
    end = html.index(";\nvar SPECS", start)
    return json.loads(html[start:end])


# ── The cap ─────────────────────────────────────────────────────────────────

def test_600_lines_is_accepted(client):
    r = post(client, MAX)

    assert r.status_code == 302, r.get_data(as_text=True)[:3000]
    assert len(STORE["boqs"]) == 1
    boq = next(iter(STORE["boqs"].values()))
    assert len(boq["line_items"]) == MAX


def test_601_lines_is_rejected(client):
    r = post(client, MAX + 1)

    assert r.status_code == 200          # re-rendered, not redirected
    assert STORE["boqs"] == {}           # and nothing was written


def test_601_is_rejected_without_becoming_a_413(client):
    """
    The point of putting the cap in the view. A 413 loses the editor outright;
    a rejection re-renders it with every line still in place.
    """
    r = post(client, MAX + 1)

    assert r.status_code != 413
    assert r.status_code == 200


def test_the_message_names_the_line_and_the_reason(client):
    html = post(client, MAX + 1).get_data(as_text=True)

    assert "601 lines and the limit is 600" in html
    assert "Line 601 is the first one over it" in html
    assert "remove 1 line," in html
    assert "split the schedule into a second BOQ" in html


def test_the_message_counts_the_overage(client):
    html = post(client, MAX + 40).get_data(as_text=True)

    assert "640 lines and the limit is 600" in html
    assert "remove 40 lines," in html


# ── Lossless ────────────────────────────────────────────────────────────────

def test_the_rejection_loses_nothing(client):
    """
    The always-return-the-user's-input contract. All 601 lines come back, in
    order, with their rates — the same guarantee a missing item number gets.
    """
    html = post(client, MAX + 1).get_data(as_text=True)
    boot = boot_of(html)

    assert len(boot["lines"]) == MAX + 1
    assert boot["lines"][0]["description"].startswith("Line 1 -")
    assert boot["lines"][MAX]["description"].startswith("Line 601 -")
    assert boot["lines"][300]["supply_rate"] == "1100"
    assert boot["sections"][0]["code"] == "A"


def test_the_plain_form_fields_survive_too(client):
    html = post(client, MAX + 1).get_data(as_text=True)

    assert "Sify Bangalore" in html          # project_name
    assert "Prudent Teqtis Pvt Ltd" in html  # account_name
    assert "Mohali Rates" in html            # rate_basis_label


def test_the_offending_line_is_forced_open(client):
    """
    Every line is collapsed by default, so a complaint about line 601 that
    leaves line 601 shut is worse than no validation — the same rule the
    per-line messages already hold to.
    """
    boot = boot_of(post(client, MAX + 1).get_data(as_text=True))

    assert boot["lines"][MAX]["_open"] is True
    assert boot["sections"][0]["_open"] is True


def test_open_state_the_user_set_is_preserved(client):
    """UI state posted by the browser survives a rejection, as §2b requires."""
    data = payload(MAX + 1)
    data["lines"][7]["_open"] = True
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(data)))

    boot = boot_of(r.get_data(as_text=True))
    assert boot["lines"][7]["_open"] is True     # theirs
    assert boot["lines"][MAX]["_open"] is True   # and the offender's


def test_the_cap_does_not_leak_ui_state_into_a_saved_record(client):
    """600 lines with _open set still writes a clean record."""
    data = payload(MAX)
    for li in data["lines"]:
        li["_open"] = True
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(data)))

    assert r.status_code == 302
    boq = next(iter(STORE["boqs"].values()))
    assert all("_open" not in li for li in boq["line_items"])


# ── The cap is checked before the per-line rules ────────────────────────────

def test_the_cap_is_reported_ahead_of_a_per_line_fault(client):
    """
    Validating 5000 rows to then reject the lot for being 5000 rows is work
    nobody asked for, and "line 12 needs a description" is the wrong complaint
    about a schedule that is 400 lines too long.
    """
    data = payload(MAX + 1)
    data["lines"][11]["description"] = ""
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(data)))

    html = r.get_data(as_text=True)
    assert "the limit is 600" in html
    assert "needs a description" not in html


# ── Size, measured rather than assumed ──────────────────────────────────────

def test_600_realistic_lines_fit_inside_the_form_limit(client):
    """
    The cap is only the primary defence if a capped BOQ actually gets through.
    The demo's 97 real lines serialise at ~701 bytes each; this asserts the
    headroom rather than trusting it, and will fail loudly if the line shape
    grows enough to push a legal BOQ into 413 territory.
    """
    import app as app_module

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]
    size = len(json.dumps(payload(MAX)).encode())

    assert size < limit, (
        f"600 lines now serialise to {size} bytes, past the {limit}-byte form "
        f"limit — a legal BOQ would 413. Raise MAX_FORM_MEMORY_SIZE or lower "
        f"MAX_LINES.")


# ── The 413 backstop ────────────────────────────────────────────────────────

def test_an_oversize_post_gets_our_page_and_not_the_bare_werkzeug_one(client):
    """
    The backstop, exercised the only way it can be: a body past
    MAX_FORM_MEMORY_SIZE, which Werkzeug rejects before any view runs.
    """
    import app as app_module

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]
    r = client.post("/boq/create", data={"boq_json": "x" * (limit + 5000)})

    assert r.status_code == 413
    html = r.get_data(as_text=True)

    # Ours, not Werkzeug's.
    assert "The page was not saved" in html
    assert "browser&#x27;s Back button" in html or "browser's Back button" in html
    assert "limited to 600 lines" in html
    assert "The data value transmitted exceeds" not in html


def test_the_413_page_keeps_the_app_chrome(client):
    """
    A bare Werkzeug page drops the user out of the app entirely. This one still
    has the nav, so there is a way back that is not the Back button.
    """
    import app as app_module

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]
    html = client.post("/boq/create",
                       data={"boq_json": "x" * (limit + 5000)}).get_data(as_text=True)

    assert "<nav>" in html
    assert "Back to dashboard" in html


def test_the_413_stays_a_413(client):
    """
    Unlike the 404 and 500 handlers beside it, this one does not redirect. A 302
    would tell the browser, the logs and any future API client that an oversize
    POST succeeded.
    """
    import app as app_module

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]
    r = client.post("/boq/create", data={"boq_json": "x" * (limit + 5000)})

    assert r.status_code == 413
    assert "Location" not in r.headers


def test_an_oversize_post_writes_nothing(client):
    import app as app_module

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]
    client.post("/boq/create", data={"boq_json": "x" * (limit + 5000)})

    assert STORE["boqs"] == {}
