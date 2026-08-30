"""
The two register SCREENS the owner has actually seen — `/attendance/` and `/dc/`.

⚠ **These are the only two pages in this application that have ever been
rendered to a human eye.** Everything else has been built, tested and never
opened. He reported three things about them: the pages are confusing, the
attendance table is misaligned, and on Delivery Challans he cannot tell what to
click.

⚠ **This edition covers the attendance day view only.** The delivery challan
register lands in the next commit, and the sections below grow with it — which
is why `SHARED` names one module and `challan` is still on the not-yet list.

### What this file pins

1. ⚠ **Numeric headers are right-aligned, not only numeric cells.** That is the
   misalignment, and it was a specificity bug rather than a missing class:
   `.att-table th { text-align:left }` is (0,1,1) and beat `.att-amt` at
   (0,1,0), so every money header sat left over a right-aligned column.
2. ⚠ **One primary action per row.** A bare challan number rendered as a link is
   a reference, not a target — the owner could not tell what to click, and a
   single digit is the smallest target this application offers.
3. **The destructive action is de-weighted.** Delete carried the same visual
   weight as Edit while destroying a record.
4. **A reference code never wraps mid-code.** `SF/BOQ/26-27/` on one line and
   `0001` on the next makes the row taller and reads as broken.
5. **The print sheet is reachable from the register**, not only from the
   document page it hangs off.
6. ⚠ **The two registers use ONE pattern**, `dashboard.REGISTER_STYLES`. Two
   registers at opposite ends of the affordance spectrum in one application is
   the problem; the styling of either one is not.
7. ⚠ **NO PINNED GOLDEN MOVES.** `REGISTER_STYLES` is a separate constant,
   deliberately not in `BASE_STYLES`, and no page a golden hashes loads it.

⚠ **What this file deliberately does NOT do: restyle the other registers.** The
owner has not seen them. `test_the_other_registers_are_recorded_as_inconsistent`
names them so the next pass takes them deliberately rather than discovering the
inconsistency by accident.
"""

import pathlib
import re

import pytest

import dashboard as D
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

DAY = "2026-08-29"

_MINTED = set()


@pytest.fixture(autouse=True)
def _clean():
    for key in ("employees", "attendance"):
        STORE.setdefault(key, {}).clear()
    _MINTED.clear()
    yield
    for key in ("employees", "attendance"):
        STORE.setdefault(key, {}).clear()
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


def _addr(label="Whitefield"):
    aid = f"addr-{label.lower().replace(' ', '-')}"
    _MINTED.add(aid)
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": "site",
        "contact_name": "", "company": "", "line1": "1 Site Road",
        "line2": "", "landmark": "", "city": "Bengaluru",
        "state": "Karnataka", "pincode": "560066", "country": "India",
        "phone": "", "email": "", "gstin": "",
    }
    return aid


def _a_day(client):
    """One marking on one day, through the real routes."""
    aid = _addr()
    r = client.post("/employee/new", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "1000",
        "site_id": aid, "active": "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    eid = list(STORE["employees"])[-1]

    r = client.post("/attendance/mark", data={
        "date": DAY, "employee_id": eid, "site_id": aid,
        "status": "present", "ot_hours": "2", "notes": ""})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return client.get(f"/attendance/?date={DAY}").get_data(as_text=True)


# ═══ 1. ⚠ ALIGNMENT — the headers too, not only the cells ══════════════════

def test_the_numeric_headers_carry_the_alignment_class(client):
    """
    Every money and count column heads with `.num`, which is what
    `REGISTER_STYLES` right-aligns. Before this the class was on the cells and
    not on the `<th>`.
    """
    html = _a_day(client)
    for label in ("OT hours", "Day rate", "Overtime", "Total"):
        assert re.search(rf'<th class="num">{re.escape(label)}</th>', html), (
            f"the {label!r} header is not marked numeric, so it renders left "
            f"over a right-aligned column")


def test_the_rule_actually_beats_the_bare_th_rule():
    """
    ⚠ **The specificity, asserted rather than assumed — because this is exactly
    what was wrong.** A bare `th` rule inside the same sheet sets
    `text-align:left`; the numeric rule has to be more specific or the header
    stays left however many classes it carries.
    """
    css = D.REGISTER_STYLES
    assert ".reg-table th.num" in css, (
        "the numeric header rule is not element-qualified, so `.reg-table th` "
        "beats it and every money header renders left again")
    bare = css.index(".reg-table th {")
    qualified = css.index(".reg-table th.num")
    assert qualified > bare, (
        "the qualified rule must come after the bare one — equal specificity "
        "would then be decided by order, and this way it is decided twice")


def test_a_numeric_cell_and_its_header_agree(client):
    """
    Behavioural rather than structural: for every numeric header there is a
    numeric cell, so the pairing cannot drift as columns move.
    """
    html = _a_day(client)
    heads = len(re.findall(r'<th class="num">', html))
    cells = len(re.findall(r'<td class="num">', html))
    assert heads >= 4, "the numeric columns vanished"
    assert cells >= heads, (
        "there are more numeric headers than numeric cells — a column heads "
        "right and renders left")


# ═══ 2. ⚠ NAMING — one name per thing, in both tables ══════════════════════

def test_the_day_filter_is_called_a_DATE_and_the_column_a_DAY_RATE(client):
    """
    ⚠ **The exact confusion the owner reported.** The page carried a `DAY`
    filter meaning a date, a `DAY` column meaning wages, and a `DAY WAGES`
    column meaning the same figure — one name for two things and two names for
    one.
    """
    html = _a_day(client)
    assert '<label for="date">Date</label>' in html, (
        "the date filter is still labelled 'Day', which is also what the wage "
        "column was called")
    assert ">Day wages<" not in html, "the third spelling is back"
    assert html.count('<th class="num">Day rate</th>') == 2, (
        "the muster and the site table must head that column identically — "
        "two names for one figure is what this fixes")


# ═══ 3. ⚠ ACTIONS — inside a real column, and de-weighted ══════════════════

def test_the_actions_live_in_a_column_with_a_header(client):
    html = _a_day(client)
    assert '<th class="reg-acts">Actions</th>' in html, (
        "the actions column has no header, so it has no width of its own and "
        "pushes the TOTAL column out of the table")
    assert '<td class="reg-acts">' in html


def test_delete_is_de_weighted_relative_to_edit(client):
    """
    ⚠ **Delete destroys a record and Edit does not**, so they may not carry the
    same weight. They were both `btn btn-ghost`.
    """
    html = _a_day(client)
    assert 'class="reg-sub" href="/attendance/edit/' in html
    assert 'class="reg-danger" href="/attendance/delete/' in html
    assert 'class="btn btn-ghost" href="/attendance/delete/' not in html, (
        "Delete still carries the same class as every other control on the "
        "page")


# ═══ 4. ⚠ ONE VISUAL LANGUAGE ══════════════════════════════════════════════

def test_both_tables_on_the_attendance_page_are_the_same_shape(client):
    """
    The top table was bare and the bottom one sat in a white card with a red
    header — same page, same data, two designs.
    """
    html = _a_day(client)
    assert html.count('class="reg-card"') >= 2, (
        "the two tables are not both in a card")
    assert html.count('<table class="reg-table">') == 2, (
        "the two tables are not both the shared table")
    assert 'class="att-table"' not in html, "the old private table style is back"


# ═══ 6. ⚠ NO PINNED GOLDEN MOVES, AND NONE COULD ═══════════════════════════

def test_the_register_styles_are_not_in_BASE_STYLES():
    """
    ⚠ **The rule that keeps this pass out of the print goldens.**
    `BASE_STYLES` is on every page in this app **including every printed one**,
    so a register rule added there moves five pinned digests for a change that
    has nothing to do with paper (ABOUT.md §7's first gap). `USER_CHIP_STYLES`
    is the precedent for a constant that lives in `dashboard.py` and is emitted
    only where it is wanted.
    """
    assert ".reg-table" not in D.BASE_STYLES, (
        "the register pattern is in BASE_STYLES, so it is on every printed "
        "document and every golden has moved")
    assert ".reg-card" not in D.BASE_STYLES
    assert ".reg-table" in D.REGISTER_STYLES


# ═══ 7. ⚠ WHAT WAS DELIBERATELY LEFT ALONE ═════════════════════════════════

# Every register in this application, and whether it uses the shared pattern.
# ⚠ **This list is a RECORD, not a queue.** The owner has seen two pages. The
#   other thirteen have never been rendered to a human eye, and restyling one
#   of those is how a pass ships a regression nobody notices for months. When
#   somebody does take them, this is the list and this test is what tells them
#   the job is finished.
SHARED = ("attendance",)
NOT_YET_SHARED = (
    "boq", "challan", "charge", "client", "employee", "invoice",
    "measurement", "po_draft", "proforma", "product", "project", "purchase",
    "quotation", "ra", "receipt", "spec",
)


def test_the_other_registers_are_recorded_as_inconsistent():
    """
    ⚠ **The registers do NOT share a table-rendering helper**, and this test is
    where that fact is written down. Each module writes its own `<table>` and
    its own CSS class — `.q-table`, `.emp-table`, `.cl-table`, `.ledger-table`,
    `.proj-tbl`, `.claims`, `.data`, `.tbl`, `.pk-table`, and several bare
    `<table>` elements. `dashboard.BASE_STYLES` carries `.btn` and `.alert` and
    no table rule at all.

    So fixing the pattern once did **not** fix every register, and this names
    the ones now inconsistent with the two the owner has seen.
    """
    for name in SHARED:
        src = (REPO / f"{name}.py").read_text(encoding="utf8")
        assert "REGISTER_STYLES" in src, (
            f"{name}.py no longer uses the shared register pattern")

    still_own = []
    for name in NOT_YET_SHARED:
        src = (REPO / f"{name}.py").read_text(encoding="utf8")
        if "REGISTER_STYLES" not in src:
            still_own.append(name)

    assert still_own == list(NOT_YET_SHARED), (
        f"a register was migrated to the shared pattern without this list "
        f"being updated: {sorted(set(NOT_YET_SHARED) - set(still_own))}. That "
        f"is a page the owner has not seen — the pass report has to say so.")
