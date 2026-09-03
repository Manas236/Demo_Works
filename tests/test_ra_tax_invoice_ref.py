"""
The single-leg RA bill's statutory serial — `ra.next_tax_invoice_ref()`.

**What this closes.** [DOMAIN.md §4.2](DOMAIN.md) says the Tax Invoice No. and
the RA Bill No. are two series that count independently, and that the tax
invoice number **must not be derived from `ra_no`**. Until 3 September 2026
nothing in this application minted one for an ordinary RA bill:
`tax_invoice_ref` was a plain typed form field, and `print_ra()` fell back
`tax_invoice_ref` → `ref` → a string built from `ra_no` when it was left blank.
So the prohibition held on every bill where the operator filled the field and
**failed silently on every bill where they did not** — which is the majority of
them. C3 (2 September 2026) minted a series for the *merged* document only and
said in terms that this gap stayed open and would need an override block of its
own. The first `CLIENT_CHANGES.md` §0 block of 3 September 2026 is that block.

⚠ **MINTING HAPPENS IN THE ROUTE, WHICH IS WHY THIS FILE POSTS.**
`tests/test_merged_ra.py`'s `_bill()` helper writes records straight into
`STORE`, so a test built on it asserts a property of its own fixture and cannot
see this behaviour at all — that is exactly why
`test_a_single_leg_bills_tax_invoice_ref_is_UNCHANGED` went on passing after the
gap closed, and it is recorded there. Everything here that matters goes through
`POST /ra/create`.

⚠ **THE HISTORICAL SET IS PINNED AS HARD AS THE NEW BEHAVIOUR.** Bills written
before this change keep a blank `tax_invoice_ref` and go on printing exactly
what they printed before. Their numbers have been quoted in somebody else's
books; replacing one silently — or printing a dash where a number used to be —
is the act the whole max+1 discipline exists to prevent. Whether any is
backfilled is the owner's decision and the §0 block reserves it.
"""

import json
import re

import pytest

import ra
from store import STORE
from test_ra_record import boq_line, claim, make_bill, make_boq

# The printed header renders one label/value pair per `quotation._meta()` row.
# Reading the VALUE out of the "Tax Invoice No." row is the only assertion that
# can tell a serial printed in the right place from the same string appearing
# somewhere else on a sheet that also carries `ref` three times over — a bare
# `in html` passes on both and is what makes this kind of test vacuous.
_TAXNO = re.compile(
    r'<span class="m-lbl">Tax Invoice No\.</span>'
    r'<span class="m-val">(.*?)</span>', re.S)


def _printed_tax_invoice_no(html: str) -> str:
    m = _TAXNO.search(html)
    assert m, "the printed sheet has no Tax Invoice No. row at all"
    return m.group(1).strip()


@pytest.fixture()
def clean(client):
    for key in ("boqs", "ra_bills", "merged_ras"):
        STORE.setdefault(key, {}).clear()
    STORE["_boq_seeded"] = False
    yield STORE


def _schedule(bid="b1", qty=1000):
    """One priced line on a schedule a claim can actually be raised on."""
    line = boq_line("1", qty, s_rate=100.0)
    make_boq(bid, [line])
    return line["line_id"]


def _raise(client, bid, lid, qty=1, date="2026-08-12", leg="supply", **form):
    """One bill through the real route. Returns the stored record."""
    before = set(STORE["ra_bills"])
    data = {"date": date,
            "ra_json": json.dumps({"lines": [
                {"line_id": lid, "qty": str(qty), "rate": "100"}]})}
    data.update(form)
    res = client.post(f"/ra/create?boq={bid}&leg={leg}", data=data)
    assert res.status_code == 302, res.get_data(as_text=True)[:2000]
    rid = (set(STORE["ra_bills"]) - before).pop()
    return STORE["ra_bills"][rid]


# =============================================================================
# 1. THE GAP IS CLOSED — a blank field is minted, not derived
# =============================================================================

def test_a_bill_raised_with_the_field_blank_is_MINTED_a_serial(client, clean):
    """
    The whole point. Before this, a blank field meant the printed Tax Invoice
    No. fell through to `ref` and then to a string built from `ra_no`.

    Non-vacuous by mutation: reverting `create_ra()`'s
    `tax_invoice_ref or next_tax_invoice_ref(date_val)` to the bare form leaves
    the field empty and this fails.
    """
    lid = _schedule()
    bill = _raise(client, "b1", lid)

    assert bill["tax_invoice_ref"] == "SF/RI/26-27/0001"


def test_the_minted_serial_is_NOT_derived_from_ra_no(client, clean):
    """
    DOMAIN.md §4.2's actual prohibition, asserted as a prohibition rather than
    as an equality: the two series count independently, so the serial must not
    move when `ra_no` does.
    """
    lid = _schedule()
    first = _raise(client, "b1", lid, qty=1)
    second = _raise(client, "b1", lid, qty=1)

    assert (first["ra_no"], second["ra_no"]) == (1, 2)
    # Both are RA bills on ONE project, so ra_no counts 1,2 — and the serials
    # count 1,2 as well. That alone proves nothing, so a SECOND project is what
    # separates the two counters below.
    lid2 = _schedule("b2")
    third = _raise(client, "b2", lid2, qty=1)

    assert third["ra_no"] == 1, "ra_no is per project"
    assert third["tax_invoice_ref"] == "SF/RI/26-27/0003", (
        "the statutory serial restarted with the project. It is the seller's "
        "own series across ALL work — DOMAIN.md §4.2 — and deriving it from "
        "ra_no is the one thing that section forbids.")


def test_a_typed_value_still_wins(client, clean):
    """
    The field stays typeable — the operator may be transcribing a serial from a
    book the client keeps. Minting only fills a blank.
    """
    lid = _schedule()
    bill = _raise(client, "b1", lid, tax_invoice_ref="THEIR-BOOK/77")

    assert bill["tax_invoice_ref"] == "THEIR-BOOK/77"


def test_a_typed_value_does_not_advance_the_minted_series(client, clean):
    """
    ⚠ A hand-typed value in a foreign shape is skipped, not parsed. A legacy
    `SF/TI/26-27/0007` sitting in this field is not an `RI` number and must not
    move the `RI` counter — the tail digits of one series are meaningless to
    another.
    """
    lid = _schedule()
    _raise(client, "b1", lid, tax_invoice_ref="SF/TI/26-27/0007")
    second = _raise(client, "b1", lid)

    assert second["tax_invoice_ref"] == "SF/RI/26-27/0001"


# =============================================================================
# 2. RULE 46(b) — the same budget C3 works to
# =============================================================================

def test_the_minted_serial_fits_rule_46b(client, clean):
    """`SF/RI/26-27/0001` is exactly 16 characters, as `SF/MI/…` and `SF/TI/…`
    are. A number the GST portal will reject is worse than an unbranded one."""
    lid = _schedule()
    ref = _raise(client, "b1", lid)["tax_invoice_ref"]

    assert len(ref) == 16, f"{ref!r} is {len(ref)} characters; Rule 46(b) allows 16"


def test_the_cap_still_holds_at_the_top_of_the_series(clean):
    """A cap that only holds at 0001 is not a cap. Checked to 9999, where the
    `:04d` format stops growing."""
    for seq in (1, 99, 1000, 9998):
        STORE["ra_bills"] = {"x": {"fy": "26-27",
                                   "tax_invoice_ref": f"SF/RI/26-27/{seq:04d}"}}
        ref = ra.next_tax_invoice_ref("2026-08-12")
        assert len(ref) <= 16, f"{ref!r} is {len(ref)} characters"


def test_the_cap_DROPS_THE_PREFIX_rather_than_issuing_an_overlong_number(clean, monkeypatch):
    """
    ⚠ **The test above cannot see the cap at all and this one is why it is
    kept beside it.** `SF/RI/26-27/0001` is 16 characters, so it fits whatever
    `_TAXREF_CAP` says — raising the cap to 64 changes nothing observable while
    the company short name is two letters. The cap only bites through
    `P.fy_ref()` when the prefix would push the number over, which is exactly
    the case `fy_ref` exists to handle: *a number the GST portal will reject is
    worse than an unbranded one.*

    Non-vacuous by mutation: `_TAXREF_CAP = 64` fails this and passes the one
    above it.
    """
    import branding

    monkeypatch.setattr(branding, "COMPANY_SHORT", "SAMRUDDHIFIRE")
    STORE["ra_bills"] = {}

    ref = ra.next_tax_invoice_ref("2026-08-12")

    assert len(ref) <= 16, f"{ref!r} is {len(ref)} characters; Rule 46(b) allows 16"
    assert ref == "RI/26-27/0001", (
        "the prefix was kept and the number went over Rule 46(b)'s budget")


def test_the_series_is_RI_and_collides_with_NEITHER_other_counter(clean):
    """
    ⚠ Three counters mint tax invoice numbers in this application. Two of them
    emitting one series would put the **same statutory serial on two different
    documents**, which is the precise failure Rule 46(b) exists to prevent.
    """
    import invoice
    import merged_ra

    assert ra._TAXREF_SERIES == "RI"
    assert len({ra._TAXREF_SERIES,
                invoice._REF_SERIES,
                merged_ra._REF_SERIES}) == 3, (
        "two tax-invoice counters share a series string")
    assert ra._TAXREF_SERIES != ra._REF_SERIES, (
        "the statutory serial and our document number share a series")


def test_the_counter_reads_its_own_collection_and_no_other(clean):
    """
    A merged document's `SF/MI/…` and a sell-side `SF/TI/…` are in other
    collections and must not be visible to this counter. `ra.py` may not import
    `invoice.py` at all, and does not import `merged_ra.py`.
    """
    STORE["merged_ras"] = {"m": {"fy": "26-27",
                                 "tax_invoice_ref": "SF/MI/26-27/0042"}}
    STORE["ra_bills"] = {}

    assert ra.next_tax_invoice_ref("2026-08-12") == "SF/RI/26-27/0001"


# =============================================================================
# 3. THE COUNTER — max+1, FY-scoped, and a spent number stays spent
# =============================================================================

def test_the_counter_is_max_plus_one_and_not_len_plus_one(clean):
    """A gap must never re-issue a number already quoted in somebody's ledger."""
    STORE["ra_bills"] = {
        "a": {"fy": "26-27", "tax_invoice_ref": "SF/RI/26-27/0001"},
        "c": {"fy": "26-27", "tax_invoice_ref": "SF/RI/26-27/0003"},
    }

    assert ra.next_tax_invoice_ref("2026-08-12") == "SF/RI/26-27/0004", (
        "len+1 would re-issue 0003, which has already been on a document")


def test_a_cancelled_bills_serial_is_SPENT(client, clean):
    """
    ⚠ Exactly `next_ra_no()`'s rule, one field along. Cancelling withdraws the
    claim; it does not return the statutory serial to the pool, because that
    number has been quoted in somebody else's books.
    """
    lid = _schedule()
    first = _raise(client, "b1", lid)
    first["status"] = "cancelled"

    second = _raise(client, "b1", lid)

    assert second["tax_invoice_ref"] == "SF/RI/26-27/0002"


def test_the_series_is_scoped_to_the_financial_year(clean):
    """Consecutive and unique **within the year** is what Rule 46(b) asks for."""
    STORE["ra_bills"] = {
        "a": {"fy": "25-26", "tax_invoice_ref": "SF/RI/25-26/0009"},
    }

    assert ra.next_tax_invoice_ref("2026-08-12") == "SF/RI/26-27/0001"


def test_a_bill_with_no_serial_at_all_does_not_break_the_counter(clean):
    """Every legacy bill is exactly this shape."""
    STORE["ra_bills"] = {
        "a": {"fy": "26-27", "tax_invoice_ref": ""},
        "b": {"fy": "26-27"},
    }

    assert ra.next_tax_invoice_ref("2026-08-12") == "SF/RI/26-27/0001"


# =============================================================================
# 4. THE CLOSED HISTORICAL SET — pinned as hard as the new behaviour
# =============================================================================

def test_printing_a_LEGACY_bill_writes_nothing_to_the_record(client, clean):
    """
    ⚠ **A print route that writes is a print route that changes a document by
    being looked at**, and the number would then depend on who opened it first.
    Minting happens in `create_ra()` and nowhere else.

    Non-vacuous by mutation: moving the mint into `print_ra()` fails this.
    """
    line = boq_line("1", 100, s_rate=100.0)
    make_boq("b1", [line])
    make_bill("r1", "b1", 1, "supply", [claim("1", 10, rate=100.0)])
    STORE["ra_bills"]["r1"]["tax_invoice_ref"] = ""

    assert client.get("/ra/print/r1").status_code == 200

    assert STORE["ra_bills"]["r1"]["tax_invoice_ref"] == "", (
        "printing minted a serial onto an already-issued document")


def test_a_LEGACY_bill_still_prints_exactly_what_it_printed_before(client, clean):
    """
    ⚠ **The grandfathered set is left alone, deliberately**, and this is the
    test that stops a later pass tidying it away. These bills have been printed
    and sent. Printing a dash where a number used to be is the same act as
    replacing it, with a different result.

    The fallback is `tax_invoice_ref` → `ref` → a string built from `ra_no`, and
    for these records it is still what DOMAIN.md §4.2 forbids. That is the open
    half, it is recorded in `print_ra()` and in the §0 block, and closing it is
    the owner's decision rather than an agent's.
    """
    line = boq_line("1", 100, s_rate=100.0)
    make_boq("b1", [line])
    make_bill("r1", "b1", 1, "supply", [claim("1", 10, rate=100.0)])
    bill = STORE["ra_bills"]["r1"]
    bill["tax_invoice_ref"] = ""

    html = client.get("/ra/print/r1").get_data(as_text=True)

    assert _printed_tax_invoice_no(html) == bill["ref"], (
        "a legacy bill's printed Tax Invoice No. changed. Its number has been "
        "quoted in somebody else's books.")


def test_a_bill_raised_TODAY_never_reaches_the_legacy_fallback(client, clean):
    """
    The other half of the pin: the fallback survives for the closed set and is
    unreachable for anything new, because `create_ra()` always leaves a value
    behind for the first `or` to short-circuit on.
    """
    lid = _schedule()
    bill = _raise(client, "b1", lid)

    html = client.get(f"/ra/print/{bill['id']}").get_data(as_text=True)

    printed = _printed_tax_invoice_no(html)
    assert printed == "SF/RI/26-27/0001"
    assert printed != bill["ref"], (
        "the printed Tax Invoice No. is still our RA document number")
    assert not printed.endswith(f"{bill['ra_no']:04d}") or printed.startswith("SF/RI"), (
        "the printed Tax Invoice No. is still built from ra_no")


# =============================================================================
# 5. EDITING — a draft may be corrected, and nothing is silently minted
# =============================================================================

def test_editing_a_draft_keeps_the_serial_it_was_minted(client, clean):
    """The serial is the bill's, not the edit's. Nothing re-mints on save."""
    lid = _schedule()
    bill = _raise(client, "b1", lid)
    minted = bill["tax_invoice_ref"]

    res = client.post(f"/ra/edit/{bill['id']}", data={
        "date": "2026-08-13",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "2", "rate": "100"}]})})
    assert res.status_code == 302, res.get_data(as_text=True)[:1500]

    # ⚠ A 302 is also what a REFUSAL returns — `can_edit()` and `_c1_refusal()`
    #   both redirect — so the status alone would let this test pass against an
    #   edit that never happened, and the serial would be unchanged for the
    #   wrong reason. Assert the edit LANDED before asserting what it left alone.
    stored = STORE["ra_bills"][bill["id"]]
    assert stored["claims"][0]["qty"] == 2.0, "the edit was refused, not applied"

    assert stored["tax_invoice_ref"] == minted


def test_editing_a_LEGACY_draft_does_NOT_mint_one(client, clean):
    """
    ⚠ **A bill that predates the counter is not given a number by being
    edited.** The set is closed at the moment the counter shipped; letting an
    edit backfill one is how a closed set grows — `approval.is_grandfathered()`
    and `measurement`'s pre-measurement pin make the identical argument.
    """
    line = boq_line("1", 100, s_rate=100.0)
    make_boq("b1", [line])
    # ⚠ `approval_status=""` is load-bearing. `make_bill()` marks a bill
    #   APPROVED by default — the files importing it are about the printed
    #   document — and B7 locks an approved bill's figures, so the edit below
    #   would be REFUSED rather than applied. It redirects either way, which is
    #   how this test first passed while proving nothing at all.
    make_bill("r1", "b1", 1, "supply", [claim("1", 10, rate=100.0)],
              status="draft", approval_status="")
    bill = STORE["ra_bills"]["r1"]
    bill["tax_invoice_ref"] = ""
    lid = STORE["boqs"]["b1"]["line_items"][0]["line_id"]

    res = client.post("/ra/edit/r1", data={
        "date": "2026-08-13",
        "ra_json": json.dumps({"lines": [
            {"line_id": lid, "qty": "5", "rate": "100"}]})})
    assert res.status_code == 302, res.get_data(as_text=True)[:1500]

    # Same trap as the test above: a refusal also redirects.
    assert STORE["ra_bills"]["r1"]["claims"][0]["qty"] == 5.0, (
        "the edit was refused, not applied — the assertion below would then "
        "pass for the wrong reason")

    assert STORE["ra_bills"]["r1"]["tax_invoice_ref"] == ""
