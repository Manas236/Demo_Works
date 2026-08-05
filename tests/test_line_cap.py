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
from urllib.parse import urlencode

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

def encoded_size(data: dict) -> int:
    """
    What actually goes on the wire.

    MAX_FORM_MEMORY_SIZE is checked against the URL-ENCODED body, not against
    the JSON. `application/x-www-form-urlencoded` percent-escapes every quote,
    brace, comma, colon, space and newline, and JSON is made of those — the real
    demo BOQ expands 1.36x, terser lines 1.51x. Measuring the decoded string
    against the limit understates the wire by a third and is how a "there is
    plenty of headroom" conclusion gets reached for a request that 413s.
    """
    return len(urlencode(data).encode())


def test_the_byte_cap_is_below_the_form_limit_at_the_worst_observed_expansion():
    """
    The property the whole cap rests on: it must fire before Werkzeug does.

    1.51 is the worst expansion measured across the real demo schedule and the
    terse synthetic lines here. The margin left over is for the twenty other
    form fields, of which only `notes` can be large.
    """
    import app as app_module
    import boq

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]
    worst_case_wire = boq.MAX_JSON_BYTES * 1.51

    assert worst_case_wire < limit, (
        f"MAX_JSON_BYTES={boq.MAX_JSON_BYTES} expands to {worst_case_wire:.0f} "
        f"bytes at 1.51x, past the {limit}-byte form limit.")
    assert limit - worst_case_wire > 40_000, "too little room for the other fields"


def test_no_realistic_boq_shape_can_reach_a_413_through_the_form():
    """
    The requirement, stated as a property rather than as one example.

    For every line shape this app has seen — the client's real 97-line schedule
    and the terse synthetic one — a payload sitting exactly ON the byte cap must
    still fit on the wire. If a future line shape expands worse than 1.51x this
    fails, and it names the shape that broke it.
    """
    import app as app_module
    import boq
    import spec

    limit = app_module.app.config["MAX_FORM_MEMORY_SIZE"]

    spec.ensure_demo_specs()
    boq.ensure_demo_boq()
    real_boot, _ = boq._demo_form_payload()

    shapes = {
        "real demo schedule": real_boot,
        "terse synthetic": payload(97),
    }

    for name, boot in shapes.items():
        js = json.dumps(boot)
        ratio = encoded_size(dict(FORM, boq_json=js)) / len(js.encode())
        at_cap = boq.MAX_JSON_BYTES * ratio

        assert at_cap < limit, (
            f"{name}: expands {ratio:.2f}x, so a payload at the "
            f"{boq.MAX_JSON_BYTES}-byte cap is {at_cap:.0f} bytes on the wire "
            f"— past the {limit}-byte form limit. Lower MAX_JSON_BYTES.")


def test_a_payload_just_under_the_byte_cap_is_accepted(client):
    import boq

    data = payload(1)
    # One line, padded to just under the cap. Line count is irrelevant here —
    # this is the schedule the byte cap exists for and the line cap cannot see.
    head = len(json.dumps(data).encode())
    data["lines"][0]["description"] = "D" * (boq.MAX_JSON_BYTES - head - 100)
    js = json.dumps(data)
    assert len(js.encode()) < boq.MAX_JSON_BYTES

    r = client.post("/boq/create", data=dict(FORM, boq_json=js))

    assert r.status_code == 302, r.get_data(as_text=True)[:2000]
    assert len(STORE["boqs"]) == 1


def test_a_payload_just_over_the_byte_cap_is_rejected(client):
    import boq

    data = payload(1)
    head = len(json.dumps(data).encode())
    data["lines"][0]["description"] = "D" * (boq.MAX_JSON_BYTES - head + 500)
    js = json.dumps(data)
    assert len(js.encode()) > boq.MAX_JSON_BYTES

    r = client.post("/boq/create", data=dict(FORM, boq_json=js))

    assert r.status_code == 200          # rejected, not 413, not written
    assert r.status_code != 413
    assert STORE["boqs"] == {}


def test_the_byte_cap_message_blames_the_schedule_not_a_line(client):
    """
    The one place this differs from every other rule in _clean_lines: no single
    line is at fault, so naming one would point the user at a row that is not
    the problem.
    """
    import boq

    data = payload(1)
    head = len(json.dumps(data).encode())
    data["lines"][0]["description"] = "D" * (boq.MAX_JSON_BYTES - head + 500)
    html = client.post("/boq/create",
                       data=dict(FORM, boq_json=json.dumps(data))).get_data(as_text=True)

    assert "This schedule is too large to save" in html
    assert "No single line is at fault" in html
    assert "293 KB" in html               # MAX_JSON_BYTES // 1024
    assert "is the first one over it" not in html


def test_the_byte_cap_rejection_loses_nothing(client):
    """Same contract as every other rejection: the editor comes back intact."""
    import boq

    data = payload(30)
    data["sections"][0]["title"] = "Sprinkler system"
    head = len(json.dumps(data).encode())
    data["lines"][0]["description"] = "D" * (boq.MAX_JSON_BYTES - head + 500)

    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(data)))
    boot = boot_of(r.get_data(as_text=True))

    assert len(boot["lines"]) == 30
    assert boot["lines"][29]["description"].startswith("Line 30 -")
    assert boot["lines"][5]["supply_rate"] == "1100"
    assert boot["sections"][0]["title"] == "Sprinkler system"
    assert "Sify Bangalore" in r.get_data(as_text=True)


def test_the_byte_cap_opens_no_line(client):
    """err_idx is -1, so nothing is forced open — there is no offending row."""
    import boq

    data = payload(30)
    head = len(json.dumps(data).encode())
    data["lines"][0]["description"] = "D" * (boq.MAX_JSON_BYTES - head + 500)

    boot = boot_of(client.post(
        "/boq/create", data=dict(FORM, boq_json=json.dumps(data))).get_data(as_text=True))

    assert not any(li.get("_open") for li in boot["lines"])


def test_the_line_cap_is_reported_ahead_of_the_byte_cap(client):
    """
    Both can be breached at once. "Remove 40 lines" is actionable; "the
    schedule is too large" is the fallback for when no line count explains it.
    """
    data = payload(MAX + 40)
    html = client.post("/boq/create",
                       data=dict(FORM, boq_json=json.dumps(data))).get_data(as_text=True)

    assert "640 lines and the limit is 600" in html
    assert "This schedule is too large to save" not in html


def test_the_real_demo_schedule_still_round_trips(client):
    """
    The regression the byte cap could plausibly cause: the client's own 97-line
    workbook is the largest real payload in the app, and it must stay well
    inside both caps.
    """
    import boq

    boq.ensure_demo_specs()
    boq.ensure_demo_boq()
    boot, _prefill = boq._demo_form_payload()
    js = json.dumps(boot)

    assert len(js.encode()) < boq.MAX_JSON_BYTES
    assert len(boot["lines"]) < boq.MAX_LINES


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
