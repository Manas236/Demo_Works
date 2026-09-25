"""
tests/test_series_floors.py — settable starting numbers, 25 September 2026
==========================================================================

ABOUT.md §7 gap 36: *"Eight of the ten document number series cannot be set to
a starting number, so a go-live restarts them at 0001 beside the client's
running paper book."* CLIENT_CHANGES.md §0, the thirty-first block.

The rule, and every test here is one face of it:

    next = max(existing max in the current numbering scope + 1, floor)

Four claims, and they fail for different reasons:

1. **A blank floor is today's behaviour, byte-identical.** This is the one that
   protects everything already shipped, and it is asserted against the real
   minters rather than against `series.next_seq()`.
2. **A floor only ever moves a series FORWARD.** `max()` cannot pull one
   backwards, and the POST refuses a floor that would try.
3. **An FY-reset series' floor belongs to its financial year and to no other.**
   The April reset under Rule 46(b) still happens, so a floor can never repeat
   a serial across years.
4. **`quotation.py` is frozen and its series gets no floor.**

⚠ **The three scan MODES are not interchangeable** and `series.py`'s header
  says why. `RI` matches on the series segment in the string, because a bill's
  `fy` key is right for the bill while the `tax_invoice_ref` typed onto it may
  belong to another series; `PI` has no financial year at all. A test that
  only exercised `FY_FIELD` would miss both.
"""

import pathlib

import pytest

import boq as BQ
import invoice
import measurement as MS
import merged_ra
import pipeline as P
import proforma
import purchase
import ra
import receipt
import series as SER
import settings as ST
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

FY = "26-27"
DATE = "2026-09-25"          # inside 26-27
NEXT_FY = "27-28"
NEXT_DATE = "2027-06-10"     # inside 27-28

# (series key, the minter, the collection it scans, the field it reads)
MINTERS = [
    ("TI",   lambda: invoice._next_ref(DATE),            "invoices",     "ref"),
    ("RI",   lambda: ra.next_tax_invoice_ref(DATE),      "ra_bills",     "tax_invoice_ref"),
    ("MI",   lambda: merged_ra.next_tax_invoice_ref(DATE), "merged_ras", "tax_invoice_ref"),
    ("PI",   lambda: proforma._next_ref(),               "proformas",    "ref"),
    ("RA",   lambda: ra.next_ref(DATE),                  "ra_bills",     "ref"),
    ("BOQ",  lambda: BQ._next_ref(DATE),                 "boqs",         "ref"),
    ("MS",   lambda: MS.next_ref(DATE),                  "measurements", "ref"),
    ("RCPT", lambda: receipt.next_ref(DATE),             "receipts",     "ref"),
    ("PO",   lambda: purchase._next_ref(DATE),           "purchases",    "ref"),
]

# What each series mints from an empty store with no floor — gap 36's own table.
EMPTY_STORE_REFS = {
    "TI":   "SF/TI/26-27/0001",
    "RI":   "SF/RI/26-27/0001",
    "MI":   "SF/MI/26-27/0001",
    "PI":   "PI-0001",
    "RA":   "SF/RA/26-27/0001",
    "BOQ":  "SF/BOQ/26-27/0001",
    "MS":   "SF/MS/26-27/0001",
    "RCPT": "SF/RCPT/26-27/0001",
    "PO":   "SF/PO/26-27/0001",
}


@pytest.fixture()
def empty(monkeypatch):
    """Every collection a series scans, emptied, and every floor cleared."""
    monkeypatch.setattr(ST, "_today_fy", lambda: FY)
    for s in SER.SERIES:
        STORE.setdefault(s.collection, {}).clear()
    STORE.setdefault("settings", {}).pop(SER.FLOORS_RECORD, None)
    yield
    for s in SER.SERIES:
        STORE.setdefault(s.collection, {}).clear()
    STORE.setdefault("settings", {}).pop(SER.FLOORS_RECORD, None)


def _plant(key, ref, fy=FY):
    """One record carrying `ref` in the field this series counts."""
    s = SER.BY_KEY[key]
    rid = f"planted-{key}-{ref}"
    STORE.setdefault(s.collection, {})[rid] = {"id": rid, "fy": fy,
                                               s.field: ref}
    return rid


# ═══ 1. A blank floor is today's behaviour ════════════════════════════════

@pytest.mark.parametrize("key,mint,_coll,_f", MINTERS)
def test_an_empty_store_with_no_floor_mints_what_it_always_did(
        key, mint, _coll, _f, empty):
    """
    ⚠ **The claim that protects everything already shipped.** Asserted against
    the real minters and against gap 36's own recorded table, not against
    `series.next_seq()` — a test of the leaf against itself would prove
    nothing about the documents.
    """
    assert mint() == EMPTY_STORE_REFS[key]


@pytest.mark.parametrize("key,mint,_coll,_f", MINTERS)
def test_max_plus_one_with_no_floor_is_unchanged(key, mint, _coll, _f, empty):
    """max+1 over the records present, never len+1 — the rule every series in
    this application already held to, re-asserted through the leaf."""
    s = SER.BY_KEY[key]
    sample = EMPTY_STORE_REFS[key]
    head = sample.rsplit("0001", 1)[0]
    _plant(key, f"{head}0007")
    _plant(key, f"{head}0003")
    assert mint() == f"{head}0008", "max+1 over the highest, not len+1"


# ═══ 2. A floor only ever moves a series FORWARD ══════════════════════════

@pytest.mark.parametrize("key,mint,_coll,_f", MINTERS)
def test_a_floor_moves_an_empty_series_to_the_floor(key, mint, _coll, _f, empty):
    """The whole point: a go-live continues the office's paper book instead of
    restarting at 0001 beside it."""
    s = SER.BY_KEY[key]
    SER.save_floor(key, s.scope_for(FY), 150)
    head = EMPTY_STORE_REFS[key].rsplit("0001", 1)[0]
    assert mint() == f"{head}0150"


@pytest.mark.parametrize("key,mint,_coll,_f", MINTERS)
def test_a_floor_BELOW_the_current_max_is_inert_and_never_reissues(
        key, mint, _coll, _f, empty):
    """
    ⚠ **`max()`, not "the floor wins".** A floor below where the series has
    already reached must not pull it backwards onto a number that is already
    on somebody's document and in their ledger. `/settings` refuses such a
    floor at the POST, but the arithmetic has to be safe even if one reaches
    the store by another route.
    """
    s = SER.BY_KEY[key]
    head = EMPTY_STORE_REFS[key].rsplit("0001", 1)[0]
    _plant(key, f"{head}0200")
    SER.save_floor(key, s.scope_for(FY), 50)
    assert mint() == f"{head}0201", "a low floor must be ignored, not obeyed"


def test_a_floor_EQUAL_to_the_next_number_changes_nothing():
    """The boundary. `max(N, N)` is `N`, so setting the floor to exactly what
    the series was going to mint is legal and inert."""
    assert SER.next_seq.__doc__  # the rule is documented where it lives
    STORE.setdefault("invoices", {}).clear()
    STORE.setdefault("settings", {}).pop(SER.FLOORS_RECORD, None)
    try:
        _plant("TI", "SF/TI/26-27/0004")
        assert SER.next_seq("TI", FY) == 5
        SER.save_floor("TI", FY, 5)
        assert SER.next_seq("TI", FY) == 5
    finally:
        STORE["invoices"].clear()
        STORE["settings"].pop(SER.FLOORS_RECORD, None)


# ═══ 3. The financial year — Rule 46(b)'s April reset survives ════════════

def test_an_fy_floor_is_INERT_in_the_next_financial_year(empty):
    """
    ⚠ **THE HEADLINE, and the question gap 36 refused to guess at.** It said:
    *"Does a start of 0150 apply only to 26-27, or does it persist across the
    year boundary? That is the client's numbering policy, not an engineering
    choice, and getting it wrong produces a duplicate statutory invoice
    number."*

    The answer recorded in the thirty-first §0 block is **only to the year it
    was set for**, and this is that answer in code. Under the other reading a
    floor of 150 would mint `SF/TI/27-28/0150` in the new year as well — and
    `SF/TI/26-27/0150` and `SF/TI/27-28/0150` are different strings, so that
    would not duplicate a serial either. What it WOULD do is silently move the
    new year's series off 0001 forever, on a policy nobody set.
    """
    SER.save_floor("TI", FY, 150)
    assert invoice._next_ref(DATE) == "SF/TI/26-27/0150"
    assert invoice._next_ref(NEXT_DATE) == "SF/TI/27-28/0001", (
        "a floor set for 26-27 reached into 27-28 — the April reset under "
        "Rule 46(b) must still put the new year at 0001")


def test_each_financial_year_takes_its_own_floor(empty):
    """Two years, two floors, neither reaching the other."""
    SER.save_floor("TI", "26-27", 150)
    SER.save_floor("TI", "27-28", 900)
    assert invoice._next_ref(DATE) == "SF/TI/26-27/0150"
    assert invoice._next_ref(NEXT_DATE) == "SF/TI/27-28/0900"


def test_a_NON_fy_series_floor_never_expires(empty):
    """
    The proforma is the one series with no financial year, so its floor is
    filed under `GLOBAL_SCOPE` and applies whatever the date is. Asserted, so
    that a future decision to year-scope the PI has to come through here.
    """
    assert SER.BY_KEY["PI"].fy_scoped is False
    SER.save_floor("PI", SER.GLOBAL_SCOPE, 40)
    assert proforma._next_ref() == "PI-0040"
    # and it is filed under the sentinel, not under a year
    assert SER.floors()["PI"] == {SER.GLOBAL_SCOPE: 40}


def test_a_floor_can_never_repeat_a_number_across_years(empty):
    """
    The property gap 36 was actually worried about, asserted as a property
    rather than as a case: across two financial years and a floor in each, no
    minted tax invoice number appears twice.
    """
    SER.save_floor("TI", "26-27", 150)
    SER.save_floor("TI", "27-28", 150)
    minted = []
    for datestr in (DATE, NEXT_DATE):
        for _ in range(5):
            ref = invoice._next_ref(datestr)
            minted.append(ref)
            _plant("TI", ref, fy=P.fy_of(datestr))
    assert len(minted) == len(set(minted)), f"a serial repeated: {minted}"


# ═══ 4. The POST refuses a floor that would do nothing ════════════════════

def test_the_post_refuses_a_floor_at_or_below_the_current_max_and_NAMES_it(empty):
    """
    ⚠ **A control that silently has no effect is worse than one that says
      why.** `next_seq()` would ignore such a floor, so storing it would leave
      an operator believing a series had been moved when it had not.
    """
    _plant("TI", "SF/TI/26-27/0042")
    data, error = ST._validate_series_floors({"floor_TI": "42"})
    assert error, "a floor equal to the current max must be refused"
    assert "42" in error, "the refusal must name the current max"
    assert "43" in error, "...and say what the lowest usable value is"

    data, error = ST._validate_series_floors({"floor_TI": "43"})
    assert not error, "one more than the current max is the boundary and is legal"


def test_the_post_refuses_a_non_numeric_or_zero_floor(empty):
    for raw in ("abc", "-1", "0", "1.5", "12x"):
        _data, error = ST._validate_series_floors({"floor_TI": raw})
        assert error, f"{raw!r} was accepted as a starting number"


def test_a_blank_floor_is_always_legal_and_stores_nothing(empty):
    data, error = ST._validate_series_floors({})
    assert not error
    ST.save_series_floors(data)
    assert SER.FLOORS_RECORD not in STORE["settings"], (
        "a form saved with every box blank must leave NO record at all, so a "
        "store with no floors is identical to one that never had any")


def test_clearing_a_floor_removes_it_and_then_the_whole_record(empty):
    ST.save_series_floors({"TI": "150"})
    assert SER.floor_of("TI", FY) == 150
    ST.save_series_floors({"TI": ""})
    assert SER.floor_of("TI", FY) == 0
    assert SER.FLOORS_RECORD not in STORE["settings"]


# ═══ 5. The record is a settings record, and NOT a branding override ══════

def test_the_floors_are_not_a_branding_override_and_cannot_light_the_amber_dot(empty):
    """
    ⚠ The nav's amber dot means *"a statutory detail is missing and a document
      will print a chip"*. A blank floor is the NORMAL configuration, so
      counting it would light that dot on every install that never opened this
      section — which is `po_draft_series`' and `delivery_challan_series`'
      reason for being separate records, a fifth time.
    """
    import branding as B

    ST.save_series_floors({"TI": "150"})
    assert SER.FLOORS_RECORD != ST.RECORD_ID
    assert SER.FLOORS_RECORD not in B.SETTINGS_KEYS
    # apply_settings reads only the company record; the floors are invisible to it
    B.apply_settings(ST.load_saved())
    assert not any(str(v) == "150" for v in B.current_settings().values())
    # and the completeness meter counts only ALL_FIELDS
    filled, total = ST._completeness(B.current_settings())
    assert total == len(ST.ALL_FIELDS)


def test_a_garbled_floors_record_is_ignored_rather_than_raising(empty):
    """A hand-edited settings row must never 500 a register. Every reader goes
    through `floors()`, which drops anything it cannot read."""
    STORE["settings"][SER.FLOORS_RECORD] = {
        "TI": {"26-27": "not-a-number"},
        "NOPE": {"26-27": 5},
        "PI": "not-a-dict",
        "RA": {"26-27": -4},
    }
    assert SER.floors() == {}
    assert invoice._next_ref(DATE) == "SF/TI/26-27/0001"


# ═══ 6. quotation.py is frozen and gets no floor ══════════════════════════

def test_the_quotation_series_has_no_floor_and_quotation_py_is_untouched():
    """
    ⚠ **INTRODUCTION.md §7's freeze, and the thirty-first §0 block declining to
      open a fifth carve-out for it.** A quotation is an offer, not a tax
      document — Rule 46(b) governs a tax invoice — so nothing about the
      client's paper book depends on its number.
    """
    assert "QT" not in SER.BY_KEY
    assert not any(s.collection == "quotations" for s in SER.SERIES)

    src = (REPO / "quotation.py").read_text(encoding="utf8")
    assert "import series" not in src, "quotation.py is frozen"
    assert "next_seq" not in src
    # and it still mints the way §7.5 records
    assert 'n = len(STORE["quotations"]) + 1' in src


def test_the_draft_po_and_challan_keep_their_own_counters(empty):
    """
    They are **stored high-water counters**, not max+1 scans: deleting a
    challan spends its number rather than handing it back. A floor would be a
    second, weaker mechanism competing with a stronger one, so they are NOT in
    the registry and their behaviour is unchanged.
    """
    assert not any(s.collection in ("purchase_orders", "delivery_challans")
                   for s in SER.SERIES)
    import challan
    import po_draft

    ST.save_dc_series("", 55)
    assert challan.next_ref() == "55", "the client's own bare-integer book"
    ST.save_po_series("SF/DPO", 37)
    assert po_draft.next_ref() == "SF/DPO/0037"
    ST.save_dc_series("", "")
    ST.save_po_series("", "")


# ═══ 7. The three scan modes are each somebody's decision ═════════════════

def test_a_typed_foreign_serial_does_not_move_the_RI_counter(empty):
    """
    ⚠ **ABOUT.md §7 gap 32's record, re-asserted through the leaf.** One live
    bill carries a hand-typed `SF/TI/26-27/0007` in `tax_invoice_ref`. It is
    not an `RI` number and must not move the `RI` sequence — which is why `RI`
    matches on the **series segment in the string** rather than on the
    record's `fy` key (`series.SERIES_PREFIX`). Flattening the three modes
    into one would re-open exactly this.
    """
    _plant("RI", "SF/TI/26-27/0007")
    assert ra.next_tax_invoice_ref(DATE) == "SF/RI/26-27/0001", (
        "a typed TI serial moved the RI counter")
    assert SER.current_max("RI", FY) == 0


def test_a_typed_foreign_serial_does_not_move_the_TI_counter_either(empty):
    """The other half, and the one gap 32 actually reports: the typed value
    lives on an RA bill, so `invoice.py` never sees it at all."""
    _plant("RI", "SF/TI/26-27/0007")
    assert invoice._next_ref(DATE) == "SF/TI/26-27/0001"


def test_the_TI_floor_is_the_clean_tool_for_gap_32(empty):
    """
    ⚠ **Not a fix for gap 32 — that stays OPEN and the live record is not
      touched — but the tool the thirty-first §0 block records it as.** A `TI`
      floor of 8 makes `invoice.py` incapable of ever minting the `0007` that
      is already typed onto a live RA bill, without validating anybody's
      typing or guessing at their numbering.
    """
    _plant("RI", "SF/TI/26-27/0007")     # the live bill's typed value
    SER.save_floor("TI", FY, 8)
    minted = [invoice._next_ref(DATE)]
    _plant("TI", minted[0])
    minted.append(invoice._next_ref(DATE))
    assert minted == ["SF/TI/26-27/0008", "SF/TI/26-27/0009"]
    assert "SF/TI/26-27/0007" not in minted


def test_the_three_tax_invoice_series_cannot_collide(empty):
    """
    ⚠ **Measured on 25 September 2026 and recorded in the thirty-first §0
      block**, which is why they were NOT unified into one leaf series.
      `pipeline.fy_ref()` drops the company prefix when Rule 46(b)'s 16
      characters would be exceeded, and **never** the series segment — so
      every minted string differs in that segment whatever the ordinals are.
    """
    for n in (1, 7, 42, 9999):
        refs = {P.fy_ref(short, code, FY, n, cap=16)
                for code in ("TI", "RI", "MI")
                for short in ("SF",)}
        assert len(refs) == 3, f"two of TI/RI/MI collided at ordinal {n}: {refs}"
    # and with the prefix dropped, which is the branch that could have collapsed them
    for short in ("SAMRUDDHI", "SAMRUDDHIFIRESERVICES"):
        refs = {P.fy_ref(short, code, FY, 7, cap=16) for code in ("TI", "RI", "MI")}
        assert len(refs) == 3, f"the cap's prefix-drop collapsed the series: {refs}"


def test_ra_py_still_does_not_import_invoice_py():
    """The prohibition the floor work had to leave standing, asserted here as
    well as in `tests/test_import_directions.py`, because a reader of this file
    needs to see that unifying the series was refused rather than forgotten."""
    src = (REPO / "ra.py").read_text(encoding="utf8")
    assert "import invoice" not in src
    leaf = (REPO / "series.py").read_text(encoding="utf8")
    assert "import invoice" not in leaf and "import ra" not in leaf, (
        "series.py must stay a leaf — it reads STORE directly, the house "
        "one-way trick, and imports no document module")


# ═══ 8. The form shows every series, including the two that keep counters ══

def test_the_settings_page_draws_a_box_for_every_series(client):
    """One place to see every series, which is what gap 36's table asked for."""
    html = client.get("/settings/").get_data(as_text=True)
    for s in SER.SERIES:
        assert f'name="floor_{s.key}"' in html, f"no control for {s.label}"
    # and the two that keep counters are still on the same page
    assert 'name="po_next_no"' in html
    assert 'name="dc_next_no"' in html
    # ...and the frozen one is not
    assert 'name="floor_QT"' not in html


def test_the_settings_page_names_the_highest_issued_number(client, empty):
    """The figure the refusal quotes has to be visible before the operator
    types, not only after they are refused."""
    _plant("TI", "SF/TI/26-27/0042")
    html = client.get("/settings/").get_data(as_text=True)
    assert "highest issued: <b>0042</b>" in html


def test_a_refused_floor_re_renders_the_form_with_what_was_typed(client, empty):
    """`address._validate()`'s contract: a rejected form comes back holding the
    operator's own input, never blanked."""
    _plant("TI", "SF/TI/26-27/0042")
    r = client.post("/settings/", data={"floor_TI": "7"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "at or below" in html
    assert 'id="floor_TI" name="floor_TI" inputmode="numeric" value="7"' in html
    assert SER.FLOORS_RECORD not in STORE["settings"], "a refused floor was stored"


def test_a_VALID_floor_posted_through_the_form_is_actually_STORED(client, empty):
    """
    ⚠ **Written because a mutation was MISSED on 25 September 2026.** Deleting
      `save_series_floors(sf_data)` from the POST handler left the whole suite
      green: every other test here calls `SER.save_floor()` or
      `ST.save_series_floors()` directly, so nothing exercised the one line
      that connects the form to the store. An operator would have typed a
      starting number, been told "Company details saved.", and had it silently
      discarded.

    This is the end-to-end path and the only test here that takes it.
    """
    r = client.post("/settings/", data={"floor_TI": "150", "floor_PI": "40"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "Company details saved." in r.get_data(as_text=True)

    assert SER.floor_of("TI", FY) == 150, "the TI floor was not stored"
    assert SER.floor_of("PI", SER.GLOBAL_SCOPE) == 40, "the PI floor was not stored"
    # ...and it reaches the document, which is the only thing that matters
    assert invoice._next_ref(DATE) == "SF/TI/26-27/0150"
    assert proforma._next_ref() == "PI-0040"


def test_the_refusal_names_the_current_max_and_the_lowest_usable_value(empty):
    """
    The refusal's TEXT, asserted on its own rather than only inside the
    round-trip test — so a message that stopped quoting either figure fails
    here by name. An operator refused without being told what the highest
    issued number is has to go and find it themselves.
    """
    _plant("TI", "SF/TI/26-27/0042")
    _data, error = ST._validate_series_floors({"floor_TI": "7"})
    assert error
    assert "42" in error, "the refusal must name the CURRENT MAX"
    assert "43" in error, "the refusal must name the LOWEST USABLE value"
    assert "Tax invoice" in error, "...and say which series it is about"
