"""
The joint sheet's sign-off, typed and saved — CLIENT_CHANGES.md §0,
thirty-sixth block, item C (decided by Manas Gawde, 30 September 2026).

Each party's Name, Designation and Date, and the counterparty's company name,
are typed on the form, stored on the record and printed on every reprint. The
SIGNATURE row stays a blank ruled cell for wet ink.

The rulings this file holds:

* **Additive, and absent means legacy.** A sheet saved before this carries
  none of the three keys and prints exactly as it did — blank cells, and the
  right-hand band derived from `account_name`. (The strongest form of that
  proof is `tests/test_print_golden.py`'s joint-sheet golden, whose fixture
  carries no key and which did NOT move in this pass.)
* **Blank prints as a blank ruled cell** — never a dash, never "None".
* **The date is the sheet's own date's twin** — `type="date"`, printed as
  stored.
* **Countersigning happens after the visit**, so the fields are editable on
  an existing sheet — through the existing edit route, and a save that
  changes only them changes nothing else on the record.
* **The installation ceiling is untouched**: `items[].line_id` and
  `measurement.approved_qty_by_line()`, which `ra.overclaims()` reads.
* **Absent from a POST is not blank** — a stale form cannot wipe a typed
  sign-off or pin an empty counterparty onto a new sheet.
"""

import copy
import json
import re

import pytest

import measurement as MS
from store import STORE
from test_measurement_joint import (  # noqa: F401  (fixtures + helpers)
    _restore_columns, seeded, priced, ms_payload, raise_joint, only_sheet)

SEVEN = ("signoff_ours", "signoff_theirs", "counterparty_name")
TYPED = {
    "signoff_ours_name": "R. Kadam", "signoff_ours_designation": "Site engineer",
    "signoff_ours_date": "2026-09-30",
    "signoff_theirs_name": "A. Shah",
    "signoff_theirs_designation": "Project manager",
    "signoff_theirs_date": "2026-10-01",
    "counterparty_name": "Reliance Industries Ltd (Jamnagar)",
}


def _new_sheet(client, boq_id, **extra):
    li = priced(boq_id, 2)
    r = raise_joint(client, boq_id, [(li[0]["line_id"], 1), (li[1]["line_id"], 2)],
                    [("H1", {"d25": 4.5}, "riser"), ("B1", {"d100": 12.0}, "")],
                    **extra)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return only_sheet()


def _edit(client, ms, **overrides):
    """POST the edit form back exactly as the sheet stands, plus `overrides`."""
    data = {k: ms.get(k, "") for k in ("date", "location", "measured_by",
                                       "witnessed_by", "notes", "system",
                                       "material", "dia_meter", "area")}
    data["ms_json"] = ms_payload([(r["line_id"], r["qty"]) for r in ms["items"]
                                  if not r.get("is_header")])
    data["grid_json"] = json.dumps({"rows": ms["grid_rows"]})
    data.update(overrides)
    r = client.post(f"/measurement/edit/{ms['id']}", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return STORE["measurements"][ms["id"]]


def _signoff_block(html):
    """Both boxes — `_joint_document_html()` writes them on one line."""
    block = html.split('<div class="jm-sign">')[1].split("\n")[0]
    assert block.count('class="jm-party"') == 2
    return block


def _cell(html, label):
    """The typed value printed in the row `label` — every occurrence."""
    return re.findall(rf'<div class="jm-slbl">{re.escape(label)}</div>'
                      r'<div class="jm-sval">([^<]*)</div>', html)


def _print(client, ms):
    r = client.get(f"/measurement/print/{ms['id']}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ── The form ────────────────────────────────────────────────────────────────

def test_the_create_form_offers_seven_fields_and_prefills_the_counterparty(
        client, seeded):
    boq = STORE["boqs"][seeded]
    html = client.get(f"/measurement/create?boq={seeded}").get_data(as_text=True)
    for key in TYPED:
        assert f'name="{key}"' in html, f"the form has no {key} field"
    assert re.search(r'id="counterparty_name" name="counterparty_name"\s+'
                     rf'value="{re.escape(boq["account_name"])}"', html), (
        "the counterparty does not start as the BOQ's bill-to party")
    assert "signature" not in " ".join(re.findall(r'name="(signoff[^"]*)"', html))


def test_both_dates_are_the_sheets_own_date_input(client, seeded):
    html = client.get(f"/measurement/create?boq={seeded}").get_data(as_text=True)
    for key in ("date", "signoff_ours_date", "signoff_theirs_date"):
        assert f'<input type="date" id="{key}" name="{key}"' in html, key


# ── Create, print, reprint ──────────────────────────────────────────────────

def test_the_typed_sign_off_is_stored_and_printed_on_every_reprint(
        client, seeded):
    ms = _new_sheet(client, seeded, **TYPED)
    assert ms["signoff_ours"] == {"name": "R. Kadam",
                                  "designation": "Site engineer",
                                  "date": "2026-09-30"}
    assert ms["signoff_theirs"] == {"name": "A. Shah",
                                    "designation": "Project manager",
                                    "date": "2026-10-01"}
    assert ms["counterparty_name"] == "Reliance Industries Ltd (Jamnagar)"
    for _ in range(2):                       # a reprint prints the same
        html = _print(client, ms)
        assert _cell(html, "NAME") == ["R. Kadam", "A. Shah"]
        assert _cell(html, "DESIGNATION") == ["Site engineer"]
        assert _cell(html, "DESIGN.") == ["Project manager"]
        assert _cell(html, "DATE") == ["2026-09-30", "2026-10-01"]
        assert ('<div class="jm-band">Reliance Industries Ltd (Jamnagar)</div>'
                in html)


def test_the_date_prints_exactly_as_the_sheets_own_date_does(client, seeded):
    ms = _new_sheet(client, seeded, **TYPED)
    html = _print(client, ms)
    assert f"<b>{ms['date']}</b>" in html or ms["date"] in html
    assert "2026-09-30" in _cell(html, "DATE")


def test_the_signature_rows_stay_blank_whatever_is_posted(client, seeded):
    ms = _new_sheet(client, seeded, signoff_ours_signature="FORGED",
                    signoff_theirs_signature="FORGED", **TYPED)
    html = _print(client, ms)
    assert _cell(html, "SIGNATURE") == [""] and _cell(html, "SIGN.") == [""]
    assert "FORGED" not in json.dumps(ms) and "FORGED" not in html


def test_blank_fields_print_as_blank_ruled_cells_never_a_dash(client, seeded):
    blanks = {k: "" for k in TYPED if k != "counterparty_name"}
    ms = _new_sheet(client, seeded, **blanks)
    block = _signoff_block(_print(client, ms))
    assert block.count('<div class="jm-sval"></div>') == 8
    for bad in ("None", "&mdash;", "&#8212;", "—", "N/A", "TBD"):
        assert bad not in block, f"a blank sign-off cell printed {bad!r}"


# ── Absent means legacy ─────────────────────────────────────────────────────

def test_a_sheet_without_the_keys_prints_exactly_as_it_did(client, seeded):
    """
    The markup of the two boxes before this pass, verbatim, for a sheet that
    carries none of the three keys: the company band, the BOQ's bill-to band,
    and eight empty cells.
    """
    ms = _new_sheet(client, seeded)
    for key in SEVEN:
        assert key not in ms, f"a sheet raised with no sign-off wrote {key}"
    rows_ours = "".join(f'<div class="jm-srow"><div class="jm-slbl">{l}</div>'
                        f'<div class="jm-sval"></div></div>'
                        for l in ("NAME", "DESIGNATION", "SIGNATURE", "DATE"))
    rows_theirs = "".join(f'<div class="jm-srow"><div class="jm-slbl">{l}</div>'
                          f'<div class="jm-sval"></div></div>'
                          for l in ("NAME", "DESIGN.", "SIGN.", "DATE"))
    theirs = (f'<div class="jm-party"><div class="jm-band">'
              f'{ms["account_name"]}</div>{rows_theirs}</div>')
    html = _print(client, ms)
    assert rows_ours in html and theirs in html


def test_an_absent_counterparty_derives_and_a_cleared_one_stays_clear(
        client, seeded):
    ms = _new_sheet(client, seeded)
    assert MS.counterparty_of(ms) == ms["account_name"]
    ms["counterparty_name"] = ""
    assert MS.counterparty_of(ms) == ""
    assert '<div class="jm-band"></div>' in _print(client, ms)


def test_reading_a_legacy_sheet_writes_nothing_to_it(client, seeded):
    ms = _new_sheet(client, seeded)
    before = copy.deepcopy(ms)
    _print(client, ms)
    client.get(f"/measurement/view/{ms['id']}")
    client.get(f"/measurement/edit/{ms['id']}")
    assert STORE["measurements"][ms["id"]] == before


# ── Editable on an existing sheet ───────────────────────────────────────────

def test_the_edit_form_shows_what_the_sheet_prints(client, seeded):
    ms = _new_sheet(client, seeded)
    html = client.get(f"/measurement/edit/{ms['id']}").get_data(as_text=True)
    assert re.search(r'name="counterparty_name"\s+value="'
                     + re.escape(ms["account_name"]) + '"', html), (
        "a legacy sheet's edit form does not start from the band it prints")


def test_the_sign_off_is_typed_on_an_existing_sheet(client, seeded):
    ms = _new_sheet(client, seeded)
    ms = _edit(client, ms, **TYPED)
    html = _print(client, ms)
    assert _cell(html, "NAME") == ["R. Kadam", "A. Shah"]
    assert ms["counterparty_name"] == TYPED["counterparty_name"]


def test_a_sign_off_edit_changes_the_seven_fields_and_nothing_else(
        client, seeded):
    """
    ⚠ Compared field by field. The first save through the edit route adds the
    two approval keys `clear_approvals()` has always written (see the next
    test), so the sheet is saved once unchanged and THEN signed.
    """
    ms = _edit(client, _new_sheet(client, seeded))
    before = copy.deepcopy(ms)
    after = _edit(client, ms, **TYPED)
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert changed == set(SEVEN), (
        f"a sign-off edit changed {sorted(changed - set(SEVEN))} as well")


def test_the_first_edit_adds_only_the_approval_reset_it_always_added(
        client, seeded):
    ms = _new_sheet(client, seeded)
    before = copy.deepcopy(ms)
    after = _edit(client, ms, **TYPED)
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert changed == set(SEVEN) | {"approvals", "approval_status"}
    assert after["approvals"] == [] and after["approval_status"] == "pending"


def test_the_installation_ceiling_is_untouched_by_the_sign_off(client, seeded):
    ms = _edit(client, _new_sheet(client, seeded))
    lines_before = [(r["line_id"], r["qty"]) for r in ms["items"]]
    ceiling_before = MS.approved_qty_by_line(seeded)
    assert ceiling_before, "the sheet feeds no ceiling — the check is vacuous"
    ms = _edit(client, ms, **TYPED)
    assert [(r["line_id"], r["qty"]) for r in ms["items"]] == lines_before
    assert MS.approved_qty_by_line(seeded) == ceiling_before


def test_a_form_without_the_fields_keeps_what_was_typed(client, seeded):
    """
    A form drawn before this pass, submitted after it, must not wipe it.

    Asserted against the TYPED values, not against a snapshot taken after an
    edit — an edit that wiped them would otherwise wipe the snapshot too, and
    the first draft of this test passed against exactly that mutation.
    """
    ms = _new_sheet(client, seeded, **TYPED)
    ms = _edit(client, ms)                       # posts none of the seven
    assert ms["signoff_ours"] == {"name": "R. Kadam",
                                  "designation": "Site engineer",
                                  "date": "2026-09-30"}
    assert ms["signoff_theirs"] == {"name": "A. Shah",
                                    "designation": "Project manager",
                                    "date": "2026-10-01"}
    assert ms["counterparty_name"] == TYPED["counterparty_name"]


def test_one_field_can_be_cleared_without_touching_the_others(client, seeded):
    ms = _new_sheet(client, seeded, **TYPED)
    ms = _edit(client, ms, **dict(TYPED, signoff_theirs_designation=""))
    assert ms["signoff_theirs"] == {"name": "A. Shah", "designation": "",
                                    "date": "2026-10-01"}
    assert _cell(_print(client, ms), "DESIGN.") == [""]
