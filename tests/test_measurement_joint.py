"""
The JOINT MEASUREMENT SHEET — the grid, the snapshot, and the legacy branch.

Authorised by the **twenty-third §0 block of `CLIENT_CHANGES.md`, 6 September
2026**, and transcribed from the client's own workbook.

⚠ **CC-2 SAYS NOTHING ABOUT ANY OF THIS.** C2 is two sentences and neither of
  them mentions printing, a layout, a location, a diameter or a
  countersignature. Everything pinned in this file is **ours or Manas's,
  unspecced and unpriced**, and the §0 block lists each ruling by name so
  Yogesh can disagree with any of them individually. Nobody may cite a test in
  this file as evidence of a delivered CC-2 requirement.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **THE INSTALLATION CAP STILL BITES.** The brief for this pass instructed
   that measurement stop capping the RA claim. Both the cap and the per-line
   `line_id` link already existed and ship, so that instruction would have
   **deleted two live guards** — silently, through the grandfather path — and
   contradicted C2's only sentence. Manas withdrew it on 6 September 2026. The
   grid is carried **beside** `items`, never instead of it, and the tests below
   are what stop a later pass quietly reversing that.
2. ⚠ **The column set is SNAPSHOTTED at create.** A `/settings` edit must never
   restate a sheet somebody has already signed.
3. ⚠ **The legacy branch survives.** Two live sheets predate the grid and
   neither maps onto it.
4. **Every numeric column is totalled, over every row** — a deliberate
   departure from the client's own broken TOTAL row.
5. **No blank filler rows print.**
"""

import json

import pytest

import approval
import boq as BQ
import demo_data as DD
import measurement as MS
import settings as ST
from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _restore_columns():
    """
    ⚠ **The column list is a SHARED settings record**, so a test that edits it
    leaks into every test after it. Two tests below deliberately edit it, and
    without this fixture they silently rewrote the column set the rest of the
    file measures against — which is exactly how the first draft of this file
    reported six failures that were all one bug.
    """
    before = STORE.get("settings", {}).get(ST.MEASUREMENT_COLUMNS_RECORD)
    yield
    if before is None:
        STORE.get("settings", {}).pop(ST.MEASUREMENT_COLUMNS_RECORD, None)
    else:
        STORE["settings"][ST.MEASUREMENT_COLUMNS_RECORD] = before


@pytest.fixture()
def seeded(client):
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()


def priced(boq_id, n=None):
    lines = [li for li in STORE["boqs"][boq_id]["line_items"]
             if not li["is_header"] and li["total_qty"] > 0]
    return lines[:n] if n else lines


def ms_payload(rows):
    return json.dumps({"lines": [{"line_id": lid, "qty": q} for lid, q in rows]})


def grid_payload(rows):
    """`rows` is `[(label, {key: value}, remarks), ...]`."""
    return json.dumps({"rows": [{"label": lbl, "values": vals, "remarks": rem}
                                for lbl, vals, rem in rows]})


def raise_joint(client, boq_id, lines, grid, **extra):
    data = {"date": "2026-09-06", "location": "", "measured_by": "R. Kadam",
            "witnessed_by": "", "notes": "",
            "ms_json": ms_payload(lines), "grid_json": grid_payload(grid),
            "system": "Hydrant & Sprinkler Line", "material": "MS Pipe",
            "dia_meter": "25 mm To 150 mm", "area": "All Area"}
    data.update(extra)
    return client.post(f"/measurement/create?boq={boq_id}", data=data)


def only_sheet():
    return next(iter(STORE["measurements"].values()))


def _approve(ms):
    ms["approval_status"] = approval.APPROVED
    return ms


# ═══════════════════════════════════════════════════════════════════════════
# 1. THE CAP STILL BITES — the ruling that was reversed
# ═══════════════════════════════════════════════════════════════════════════

def test_a_joint_sheet_STILL_carries_its_line_items(client, seeded):
    """
    ⚠ **THE LOAD-BEARING TEST OF THIS WHOLE PASS.**

    The grid is keyed by (location, dia). The RA installation ceiling is keyed
    by `line_id`. If a joint sheet carried only the grid, `items` would be
    empty, `approved_qty_by_line()` would return `{}` — and `ra.py` reads `{}`
    as *"this project predates measurement, keep the BOQ ceiling"*. Every new
    project would silently lose its cap **while showing as approved**.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 3)],
                [("H1", {"d100": 12.5}, "")])
    ms = only_sheet()

    assert MS.is_joint(ms), "a sheet raised today should be the joint model"
    assert ms["items"], "the joint sheet dropped its line_id rows — THE CAP IS GONE"
    assert any(r.get("line_id") == li["line_id"] for r in ms["items"])


def test_the_installation_ceiling_still_comes_from_the_measurement(client, seeded):
    """CC-2's own sentence, still true after the redesign."""
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 3)],
                [("H1", {"d100": 12.5}, "")])
    _approve(only_sheet())

    ceiling = MS.approved_qty_by_line(seeded)
    assert ceiling.get(li["line_id"]) == 3, (
        "the approved measured quantity is no longer reaching ra.overclaims() "
        "— the installation leg has silently reverted to the BOQ ceiling")


def test_the_grid_does_NOT_feed_the_ceiling(client, seeded):
    """
    The two halves are independent, and this is the honest statement of §4.1's
    surviving half: a grid cell is not a claimable quantity, because a
    (location, dia) pair cannot be resolved to a `line_id` without guessing.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 3)],
                [("H1", {"d100": 999.0}, "")])
    _approve(only_sheet())
    # 3 from `items`, and emphatically not 999 from the grid.
    assert MS.approved_qty_by_line(seeded).get(li["line_id"]) == 3


# ═══════════════════════════════════════════════════════════════════════════
# 2. THE COLUMN SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════

def test_the_column_set_is_snapshotted_onto_the_record(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    ms = only_sheet()
    assert len(ms["grid_columns"]) == 12
    assert [c["key"] for c in ms["grid_columns"]][:3] == ["d25", "d32", "d40"]


def test_a_LATER_settings_change_does_not_restate_an_existing_sheet(client, seeded):
    """
    ⚠ The RA bill's own claim-row invariant, and it has already shipped as a
    defect once in this repo. A sheet two parties signed must print the columns
    it was signed with.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    ms = only_sheet()
    before = [dict(c) for c in ms["grid_columns"]]

    ST.save_measurement_columns([{"key": "d25", "label": "25 NB",
                                  "group": "", "unit": "m"}])
    assert ST.measurement_columns() != before, "the settings edit did not land"

    assert MS.grid_columns_of(ms) == before, (
        "editing /settings restated a sheet that already exists")
    _approve(ms)
    h = client.get(f"/measurement/print/{ms['id']}").get_data(as_text=True)
    assert "200 NB" in h, "the printed sheet followed /settings, not its snapshot"


def test_a_new_sheet_DOES_take_the_new_columns(client, seeded):
    """The snapshot freezes existing sheets, not future ones."""
    ST.save_measurement_columns([
        {"key": "d15", "label": "15 NB", "group": "", "unit": "m"},
        {"key": "d20", "label": "20 NB", "group": "", "unit": "m"},
    ])
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d15": 4}, "")])
    assert [c["key"] for c in only_sheet()["grid_columns"]] == ["d15", "d20"]


def test_the_seeded_columns_are_the_clients_own_twelve():
    keys = [c["key"] for c in ST.DEFAULT_MEASUREMENT_COLUMNS]
    assert keys == ["d25", "d32", "d40", "d50", "d65", "d80", "d100", "d150",
                    "d200", "msa", "pendant", "upright"]


def test_every_column_carries_a_unit():
    """
    ⚠ A TOTAL row that adds metres to kilograms is a lie the client's own sheet
    tells quietly. Naming the unit in the head is what stops it.
    """
    for c in ST.DEFAULT_MEASUREMENT_COLUMNS:
        assert c["unit"], f"column {c['key']} has no unit"
    units = {c["key"]: c["unit"] for c in ST.DEFAULT_MEASUREMENT_COLUMNS}
    assert units["d25"] == "m"
    assert units["msa"] == "kgs"
    assert units["pendant"] == "Nos" and units["upright"] == "Nos"


def test_the_units_reach_the_printed_head(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"msa": 4}, "")])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)
    assert "(kgs)" in h and "(Nos)" in h and "(m)" in h


# ═══════════════════════════════════════════════════════════════════════════
# 3. THE TOTAL ROW — a deliberate departure from the client's arithmetic
# ═══════════════════════════════════════════════════════════════════════════

def test_every_numeric_column_is_totalled_over_every_row(client, seeded):
    """
    ⚠ Their workbook totals `25 NB` **not at all**, totals an unlabelled column
    over a DIFFERENT row range (9-35 against 9-25), and totals
    `SUPPORTS (MSA kgs)` not at all. We total every column over every row, and
    this is the test that stops somebody "fixing" it back to match their paper.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [
        ("H1", {"d25": 10, "msa": 5.5}, ""),
        ("B1", {"d25": 15, "msa": 4.5, "pendant": 3}, ""),
        ("B2", {"d25": 5}, ""),
    ])
    totals = MS.grid_totals(only_sheet())
    assert totals["d25"] == 30, "the 25 NB column is not totalled"
    assert totals["msa"] == 10, "the SUPPORTS (MSA kgs) column is not totalled"
    assert totals["pendant"] == 3
    assert totals["d200"] == 0


def test_the_total_row_reaches_the_printed_sheet(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)],
                [("H1", {"d25": 10}, ""), ("B1", {"d25": 15}, "")])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)
    assert "TOTAL" in h
    assert "25.00" in h or "25" in h


def test_there_is_no_unlabelled_column(client, seeded):
    """Their sheet's phantom column is dropped, not reproduced."""
    for c in ST.DEFAULT_MEASUREMENT_COLUMNS:
        assert str(c.get("label") or "").strip(), (
            "a column with no label is the client's own spreadsheet bug")


# ═══════════════════════════════════════════════════════════════════════════
# 4. ROWS
# ═══════════════════════════════════════════════════════════════════════════

def test_the_seventeen_client_locations_are_seeded_in_order():
    assert MS.DEFAULT_LOCATION_ROWS == (
        "H1", "SH 1", "B1", "B2", "B3", "B4", "B5", "B6", "B7",
        "Hosereel", "Hose Box", "Hydrant", "Air Release", "Air Vessel",
        "RRL Hose", "Branch Pipe", "4 Way")
    assert len(MS.DEFAULT_LOCATION_ROWS) == 17


def test_the_seeded_rows_appear_on_the_entry_form(client, seeded):
    h = client.get(f"/measurement/create?boq={seeded}").get_data(as_text=True)
    for name in ("H1", "Hosereel", "Air Vessel", "4 Way"):
        assert f'value="{name}"' in h, f"the seeded row {name} is not on the form"


def test_rows_can_be_renamed_and_added(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)],
                [("Basement 3 riser", {"d80": 22}, "behind the lift shaft")])
    rows = MS.grid_rows_of(only_sheet())
    assert len(rows) == 1
    assert rows[0]["label"] == "Basement 3 riser"
    assert rows[0]["remarks"] == "behind the lift shaft"


def test_a_completely_blank_row_is_not_stored(client, seeded):
    """
    ⚠ **No blank filler rows.** Their paper carries about ten ruled blanks
    before the TOTAL row. A blank ruled row underneath a countersignature is an
    invitation to write on the document after it has been signed — the delivery
    challan pass's argument, and stronger here because this document is signed
    by the customer too.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [
        ("H1", {"d25": 10}, ""),
        ("", {}, ""),          # an untouched filler row
        ("", {}, ""),
    ])
    rows = MS.grid_rows_of(only_sheet())
    assert len(rows) == 1, "a blank filler row was stored"
    assert rows[0]["label"] == "H1"


def test_a_NAMED_row_with_no_values_is_kept(client, seeded):
    """
    A location that was visited and found to carry nothing is a fact worth
    printing. It is not a filler row, and the two must not be confused.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)],
                [("Hydrant", {}, "nothing installed yet")])
    assert len(MS.grid_rows_of(only_sheet())) == 1


def test_a_negative_measurement_is_refused(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": -4}, "")])
    assert not STORE["measurements"], "a negative grid value was saved"


def test_a_non_numeric_cell_is_refused(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)],
                [("H1", {"d25": "twelve"}, "")])
    assert not STORE["measurements"]


def test_a_cell_for_a_column_that_does_not_exist_is_dropped(client, seeded):
    """
    The snapshot is what the sheet prints, so a value with no column to sit in
    would be invisible. Dropped rather than stored.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)],
                [("H1", {"d25": 4, "d999": 7}, "")])
    assert MS.grid_rows_of(only_sheet())[0]["values"] == {"d25": 4.0}


# ═══════════════════════════════════════════════════════════════════════════
# 5. SITE IS INHERITED, NEVER TYPED
# ═══════════════════════════════════════════════════════════════════════════

def test_the_form_offers_no_site_INPUT(client, seeded):
    """
    ⚠ Three spellings of one city are already live in this database because
    site was free text in three places. A fourth free-text site box would be
    the same mistake a fourth time, so there is no input to type into.
    """
    h = client.get(f"/measurement/create?boq={seeded}").get_data(as_text=True)
    assert 'name="site"' not in h
    assert 'name="site_label"' not in h
    assert 'name="site_address"' not in h


def test_site_is_snapshotted_onto_the_record(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    ms = only_sheet()
    assert "site_label" in ms and "site_source" in ms


def test_a_typed_site_is_IGNORED_rather_than_stored(client, seeded):
    """A hand-made POST does not get to reintroduce free text."""
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")],
                site_label="Bangaluru", site="Banglore")
    ms = only_sheet()
    assert ms["site_label"] != "Bangaluru"


def test_the_amber_band_shows_when_the_site_is_the_schedules_free_text(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    ms = only_sheet()
    _approve(ms)
    h = client.get(f"/measurement/print/{ms['id']}").get_data(as_text=True)
    if ms.get("site_source") in ("boq", "none"):
        assert "jm-drift" in h, "no amber band on an unjoined site"


def test_the_dia_hint_is_derived_but_never_auto_filled(client, seeded):
    """
    ⚠ Their own sample reads *"25 mm To 150 mm"* while their grid carries a
    **200 NB** column. The field is a stated scope for the system, not a
    summary of the grid, so the hint reports and the box is left alone.
    """
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)],
                [("H1", {"d25": 4, "d200": 9}, "")],
                dia_meter="25 mm To 150 mm")
    ms = only_sheet()
    assert ms["dia_meter"] == "25 mm To 150 mm", "the stated scope was overwritten"
    hint = MS.dia_hint(ms)
    assert "25 NB" in hint and "200 NB" in hint
    assert MS.columns_in_use(ms) == ["25 NB", "200 NB"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. THE TWO-PARTY SIGN-OFF — the reason it is called *joint*
# ═══════════════════════════════════════════════════════════════════════════

def test_the_sheet_is_countersigned_by_both_parties(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)

    assert h.count('class="jm-party"') == 2, "this is not a JOINT sheet"
    for label in ("NAME", "DESIGNATION", "SIGNATURE", "DATE", "DESIGN.", "SIGN."):
        assert f">{label}<" in h, f"the sign-off is missing {label}"


def test_the_right_hand_party_is_the_boqs_bill_to(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    ms = only_sheet()
    _approve(ms)
    h = client.get(f"/measurement/print/{ms['id']}").get_data(as_text=True)
    assert ms["account_name"] and ms["account_name"] in h


def test_an_absent_bill_to_prints_EMPTY_and_not_a_placeholder(seeded):
    """
    ⚠ A placeholder on a countersignature block is a name somebody might sign
    underneath. Where the BOQ carries no party the band is blank.
    """
    ms = {"grid_model": MS.GRID_MODEL_JOINT, "grid_columns": [],
          "grid_rows": [], "account_name": "", "ref": "X", "date": "2026-09-06"}
    h = MS._joint_document_html(ms)
    assert '<div class="jm-band"></div>' in h
    for bad in ("TBD", "N/A", "Customer", "Main Contractor", "&mdash;"):
        assert f'<div class="jm-band">{bad}</div>' not in h


# ═══════════════════════════════════════════════════════════════════════════
# 7. THE LEGACY BRANCH — two live sheets predate the grid
# ═══════════════════════════════════════════════════════════════════════════

def test_a_record_with_no_grid_mark_is_legacy():
    assert MS.is_legacy_grid({}) is True
    assert MS.is_legacy_grid({"items": []}) is True
    assert MS.is_legacy_grid({"grid_model": MS.GRID_MODEL_LEGACY}) is True
    assert MS.is_legacy_grid({"grid_model": MS.GRID_MODEL_JOINT}) is False


def test_a_legacy_sheet_still_renders_through_the_old_layout():
    """
    ⚠ **`SF/MS/26-27/0001` and `SF/MS/26-27/0002` must go on rendering.**
    Neither carries a location or a diameter as structured data, so neither
    maps onto the grid and migrating them would mean inventing data.
    """
    legacy = {
        "id": "x", "ref": "SF/MS/26-27/0001", "date": "2026-08-30",
        "boq_ref": "SF/BOQ/26-27/0007", "project_name": "Banglore",
        "account_name": "Sanghvi Steel & Pipes",
        "site_location": "Banglore, Karnataka", "location": "",
        "measured_by": "", "witnessed_by": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
        "items": [{"line_id": "c1d6e99b0e9e", "item_no": "1", "qty": 5.0,
                   "unit": "Nos", "boq_qty": 5.0, "is_header": False,
                   "description": "SS braided sprinkler flexible drop"}],
    }
    h = MS._document_html(legacy)
    assert "MEASUREMENT OF WORK DONE" in h, "the legacy layout is gone"
    assert "JOINT MEASUREMENT SHEET" not in h
    assert "SS braided sprinkler flexible drop" in h
    # `_fmt_qty` prints a whole quantity without decimals, which is what the
    # legacy sheet has always done.
    assert ">5<" in h and "Nos" in h


def test_the_legacy_branch_is_chosen_by_the_MARK_and_not_by_a_missing_field():
    """
    ⚠ `pre_measurement`'s rule and `pre_approval_system`'s, applied a third
    time: "has no grid" and "was written before grids existed" are different
    facts. A branch that cannot tell them apart will one day render a NEW sheet
    through the OLD template because somebody's grid failed to save.
    """
    marked = {"grid_model": MS.GRID_MODEL_LEGACY, "items": []}
    assert MS.is_legacy_grid(marked)
    # A joint sheet whose grid is empty is still a joint sheet.
    empty_joint = {"grid_model": MS.GRID_MODEL_JOINT,
                   "grid_columns": [], "grid_rows": []}
    assert not MS.is_legacy_grid(empty_joint)
    assert "JOINT MEASUREMENT SHEET" in MS._document_html(empty_joint)


def test_a_legacy_sheet_gets_no_landscape_styles(client, seeded):
    """
    The legacy sheet is portrait and must stay byte-for-byte what it was. The
    landscape @page rule reaching it would silently re-lay-out two live
    documents.
    """
    legacy = {"id": "leg1", "ref": "SF/MS/26-27/0001", "date": "2026-08-30",
              "boq_ref": "B", "project_name": "P", "account_name": "A",
              "site_location": "S", "location": "", "measured_by": "",
              "witnessed_by": "", "notes": "", "company_branch": "",
              "auth_signatory": "", "items": [], "approval_status": "approved"}
    STORE["measurements"]["leg1"] = legacy
    h = client.get("/measurement/print/leg1").get_data(as_text=True)
    assert "A4 landscape" not in h
    assert "MEASUREMENT OF WORK DONE" in h


# ═══════════════════════════════════════════════════════════════════════════
# 8. NOTHING THAT MUST NOT BE ON THE SHEET
# ═══════════════════════════════════════════════════════════════════════════

def test_no_money_reaches_the_joint_sheet(client, seeded):
    """A rate on a measurement turns it into a claim — challan.py's rule."""
    li = next(x for x in priced(seeded) if float(x["install_rate"] or 0) > 0)
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)
    assert "&#8377;" not in h
    assert f"{float(li['install_rate']):,.2f}" not in h


def test_nothing_about_approval_reaches_the_joint_sheet(client, seeded):
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)
    for bad in ("Approval", "Approve", "Pending", "Rejected", "ladder"):
        assert bad not in h, f"{bad!r} reached the printed sheet"


def test_the_letterhead_is_the_shared_one_and_reads_settings(client, seeded):
    """
    ⚠ **Take the address from `/settings`, never from a constant.** A second
    letterhead drawn in this module is exactly what `docsheet.py` was extracted
    to stop, and it had already found four that had drifted apart.
    """
    import branding as B
    li = priced(seeded, 1)[0]
    raise_joint(client, seeded, [(li["line_id"], 1)], [("H1", {"d25": 4}, "")])
    _approve(only_sheet())
    h = client.get(f"/measurement/print/{only_sheet()['id']}").get_data(as_text=True)
    assert '<div class="lh-addr">' in h
    if B.COMPANY_ADDR:
        assert B.COMPANY_ADDR[:20] in h


def test_no_state_name_or_gstin_is_written_into_the_module():
    """
    `tests/test_ra_seller_identity.py`'s rule, applied to this module's new
    half: our identity is read at render time and never typed into a file.
    """
    import pathlib
    import re
    src = pathlib.Path(MS.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", src)


# ═══════════════════════════════════════════════════════════════════════════
# 9. THE SETTINGS ROUND TRIP
# ═══════════════════════════════════════════════════════════════════════════

def test_the_columns_round_trip_through_the_settings_textarea():
    text = ST.measurement_columns_text(ST.DEFAULT_MEASUREMENT_COLUMNS)
    back, err = ST._validate_measurement_columns(text)
    assert err == ""
    assert back == ST.DEFAULT_MEASUREMENT_COLUMNS


def test_a_blank_box_restores_the_seeded_twelve():
    back, err = ST._validate_measurement_columns("")
    assert err == "" and len(back) == 12


def test_a_duplicate_column_key_is_refused():
    _c, err = ST._validate_measurement_columns("a|A||m\na|B||m")
    assert "twice" in err


def test_a_column_key_that_is_not_a_field_name_is_refused():
    """The key names a form field, so it has to be usable as one."""
    _c, err = ST._validate_measurement_columns("not a key|X||m")
    assert err


def test_a_column_with_no_key_is_refused():
    _c, err = ST._validate_measurement_columns("|Label||m")
    assert "key" in err


def test_the_group_and_unit_are_optional():
    cols, err = ST._validate_measurement_columns("d25|25 NB")
    assert err == ""
    assert cols == [{"key": "d25", "label": "25 NB", "group": "", "unit": ""}]
