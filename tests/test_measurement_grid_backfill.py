"""
`tools/backfill_measurement_grid.py` — the marking, and what it refuses to do.

Authorised by the twenty-third §0 block of `CLIENT_CHANGES.md`, 6 September
2026. Not CC-2 scope; PROGRESS.md §4c.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **THE TWO LIVE SHEETS ARE NOT RESHAPED AND NOT DELETED.** `items` — the
   `line_id` rows that feed the installation ceiling — must come out of the
   migration byte-identical. A backfill that "helpfully" derived a grid from
   the description prose would be inventing a measurement two parties sign.
2. **Idempotent.** A second run marks nothing.
3. **A joint sheet is left alone.** It is not this script's business.
4. **It grants no permission and touches no user or role** — the acknowledgement
   the fifth 29 August 2026 override block asks the next migration to honour.
"""

import copy
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import measurement as MS  # noqa: E402

import backfill_measurement_grid as BF  # noqa: E402


# The two live sheets, in the shape the database actually holds them.
LIVE_0001 = {
    "id": "01d2f59e-12a5-4a16-91e5-0d90aa3d2a9a",
    "ref": "SF/MS/26-27/0001", "fy": "26-27", "date": "2026-08-30",
    "boq_id": "b3288694", "boq_ref": "SF/BOQ/26-27/0007", "boq_rev_no": 0,
    "project_name": "Banglore", "site_location": "Banglore, Karnataka",
    "account_name": "Sanghvi Steel & Pipes",
    "location": "", "measured_by": "", "witnessed_by": "", "notes": "",
    "company_branch": "", "auth_signatory": "",
    "created_at": "2026-08-30 11:14", "created_by": "7d9586bcdd59",
    "items": [
        {"qty": 5.0, "unit": "Nos", "boq_qty": 5.0, "item_no": "1",
         "line_id": "c1d6e99b0e9e", "is_header": False,
         "description": "SS braided sprinkler flexible drop pipes"},
        {"qty": 5.0, "unit": "Nos.", "boq_qty": 5.0, "item_no": "1",
         "line_id": "e0335c3c1d41", "is_header": False,
         "description": "63 mm dia instantaneous pattern branch pipe"},
    ],
}

LIVE_0002 = {
    "id": "a3d8e6a0-d0c9-49e4-8e6e-864fd89b4290",
    "ref": "SF/MS/26-27/0002", "fy": "26-27", "date": "2026-08-31",
    "boq_id": "b8", "boq_ref": "SF/BOQ/26-27/0008", "boq_rev_no": 0,
    "project_name": "Sify Bangalore", "site_location": "Bangalore, Karnataka",
    "account_name": "Prudent Teqtis Pvt Ltd",
    # ⚠ The whole reason this record cannot be migrated: `location` is ONE
    #   free-text field on the sheet, not a property of a row, and there is no
    #   diameter column anywhere. "5,7" is a pair of floor numbers.
    "location": "5,7", "measured_by": "", "witnessed_by": "", "notes": "",
    "company_branch": "", "auth_signatory": "",
    "created_at": "2026-08-31 09:40", "created_by": "7d9586bcdd59",
    "items": [
        {"qty": 0.0, "unit": "", "item_no": "4", "line_id": "9ef3247b6e3d",
         "is_header": True, "description": "Heavy 'C' class MS pipes"},
        {"qty": 4.0, "unit": "Mtrs.", "boq_qty": 4.0, "item_no": "4.1",
         "line_id": "6199eca470a8", "is_header": False,
         "description": "150mm dia     ISI"},
        {"qty": 12.0, "unit": "Mtrs.", "boq_qty": 12.0, "item_no": "4.2",
         "line_id": "d52da19f4873", "is_header": False,
         "description": "100mm dia     ISI"},
    ],
}


@pytest.fixture()
def live():
    return {LIVE_0001["id"]: copy.deepcopy(LIVE_0001),
            LIVE_0002["id"]: copy.deepcopy(LIVE_0002)}


# ── The plan ────────────────────────────────────────────────────────────────

def test_both_live_sheets_are_marked(live):
    to_mark, already, joint = BF.plan(live)
    assert len(to_mark) == 2
    assert already == [] and joint == []


def test_a_second_run_marks_NOTHING(live):
    """Idempotence, and it is asserted by running the thing twice."""
    to_mark, _a, _j = BF.plan(live)
    for mid in to_mark:
        live[mid]["grid_model"] = MS.GRID_MODEL_LEGACY

    to_mark2, already, joint = BF.plan(live)
    assert to_mark2 == [], "a second run would mark a sheet again"
    assert len(already) == 2
    assert joint == []


def test_a_JOINT_sheet_is_never_touched(live):
    live["new"] = {"id": "new", "ref": "SF/MS/26-27/0003",
                   "grid_model": MS.GRID_MODEL_JOINT, "items": []}
    to_mark, _already, joint = BF.plan(live)
    assert joint == ["new"]
    assert "new" not in to_mark


def test_the_plan_is_ordered_by_reference(live):
    """So the printed before/after is readable and stable across runs."""
    to_mark, _a, _j = BF.plan(live)
    assert [live[m]["ref"] for m in to_mark] == ["SF/MS/26-27/0001",
                                                 "SF/MS/26-27/0002"]


# ── What must survive ───────────────────────────────────────────────────────

def test_the_mark_is_the_ONLY_field_that_changes(live):
    """
    ⚠ **The load-bearing assertion of this file.** `items` carries the
    `line_id` quantities that feed `ra.overclaims()` through
    `measurement.approved_qty_by_line()`. A migration that touched them would
    move an installation ceiling, silently, on live data.
    """
    before = copy.deepcopy(live)
    to_mark, _a, _j = BF.plan(live)
    for mid in to_mark:
        live[mid]["grid_model"] = MS.GRID_MODEL_LEGACY

    for mid, rec in live.items():
        was = before[mid]
        assert set(rec) - set(was) == {"grid_model"}, (
            f"{rec.get('ref')} gained a field other than the mark")
        for key, value in was.items():
            assert rec[key] == value, (
                f"{rec.get('ref')}.{key} was changed by the migration")


def test_no_quantity_moves(live):
    def total(recs):
        return sum(float(r.get("qty") or 0.0)
                   for rec in recs.values() for r in rec.get("items") or [])

    before = total(live)
    for mid in BF.plan(live)[0]:
        live[mid]["grid_model"] = MS.GRID_MODEL_LEGACY
    assert total(live) == before == 26.0


def test_a_marked_sheet_still_renders_through_the_legacy_layout(live):
    for mid in BF.plan(live)[0]:
        live[mid]["grid_model"] = MS.GRID_MODEL_LEGACY
    for rec in live.values():
        h = MS._document_html(rec)
        assert "MEASUREMENT OF WORK DONE" in h
        assert "JOINT MEASUREMENT SHEET" not in h
        assert rec["ref"] in h


def test_neither_sheet_could_have_been_migrated(live):
    """
    ⚠ The justification for the legacy branch, asserted rather than argued.
    A grid needs (location, diameter) **per row**. These records have a single
    free-text `location` on the sheet and no diameter field anywhere.
    """
    for rec in live.values():
        assert isinstance(rec["location"], str), (
            "location is a sheet-level string, not a per-row value")
        for row in rec["items"]:
            assert "location" not in row
            assert "dia" not in row and "diameter" not in row


# ── What it must not do ─────────────────────────────────────────────────────

def test_the_script_touches_no_user_no_role_and_no_permission():
    """
    ⚠ `backfill_created_by.py` reached into `STORE["roles"]`, and the fifth
    29 August 2026 override block acknowledges that retrospectively and asks the
    next migration to be authorised on its own terms. This one does not go near
    identity data, and that is asserted against the source rather than trusted.
    """
    src = pathlib.Path(BF.__file__).read_text(encoding="utf-8")
    body = "\n".join(line for line in src.splitlines()
                     if not line.strip().startswith("#"))
    # The docstring mentions them by name to explain the rule; the CODE must
    # not touch them.
    code = body.split('"""')[-1]
    for forbidden in ('STORE["users"]', "STORE['users']",
                      'STORE["roles"]', "STORE['roles']",
                      "grant", "permission"):
        assert forbidden not in code, (
            f"{forbidden!r} appears in the executable half of the migration")


def test_dry_run_is_the_default():
    """`--write` is a flag somebody types, never a default."""
    src = pathlib.Path(BF.__file__).read_text(encoding="utf-8")
    assert '"--write", action="store_true"' in src
    assert "DRY RUN" in src


def test_the_migration_records_itself():
    assert BF.MIGRATION_KEY == "measurement_grid_migration"
    src = pathlib.Path(BF.__file__).read_text(encoding="utf-8")
    for key in ('"at"', '"count"', '"ids"', '"refs"'):
        assert key in src, f"the migration record does not carry {key}"


def test_describe_prints_the_values_the_report_needs(live):
    line = BF.describe(live[LIVE_0002["id"]])
    assert "SF/MS/26-27/0002" in line
    assert "Sify Bangalore" in line
    assert "'5,7'" in line, "the location string is not in the before/after line"


def test_no_application_module_imports_the_backfill():
    """
    ⚠ Checked at AST level, not by grepping for the name. `measurement.py`
    **names** this script in a comment — deliberately, so the reader of
    `is_legacy_grid()` knows what writes the mark — and a substring search
    cannot tell a citation from a dependency. What must not exist is an
    **import**: a module that could reach this one could run a live migration
    by being served.
    """
    import ast

    offenders = []
    for py in REPO.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            if "backfill_measurement_grid" in names:
                offenders.append(py.name)
    assert not offenders, f"{offenders} import a one-off migration script"
