"""
`compute_tax_totals()` honours the per-line `gst_rate` it already stores.

ABOUT.md §7 gap 14: `build_claim()` has snapshotted `gst_rate` onto every claim
row since the record shape was written, and the tax arithmetic never read it —
it applied the bill-level `cgst_rate` / `sgst_rate` / `igst_rate` to every line
and summed. Right on a single-rate bill, wrong on one mixing 18% goods with 12%
or 5% work, and wrong on a document headed TAX INVOICE.

Three things this file is really guarding:

1. **The uniform-rate answer did not move.** Every bill the client has actually
   sent us is single-rate, and the figures below are pinned as literals taken
   from the code BEFORE this change — not recomputed — so a drift shows up as a
   failure rather than as a quietly-updated expectation.
2. **Rounding happens once.** The old code rounded each LINE's tax to the paisa
   and added 87 of them up. Per-slab rounding would do the same thing more
   slowly. The document totals round once, from the unrounded slab sums.
3. **Nothing stored was touched.** An issued bill's tax block is a frozen
   snapshot. Bills written before `tax_slabs` existed have no such key, and both
   the arithmetic and the printed sheet have to carry on as if nothing happened.

⚠ **The tax HEAD is deliberately not in scope.** Whether a bill is CGST+SGST or
  IGST still comes from `tax_type`, still defaults to `cgst_sgst`, and is still
  not derived from a place of supply — §7 gap 15, open pending the client's CA.
  Nothing here asserts a head is correct, only that a rate is split across
  whichever head the bill already carries.
"""

import ast
import json
import pathlib

import pytest

import boq as BQ
import demo_data as DD
import ra
from quotation import _inr
from store import STORE
from conftest import printable

# ⚠ The printed figures below moved to `_inr()`'s Indian digit grouping when
# `/ra/print` was rebuilt on the shared A4 sheet. Same figures, same
# assertions; only the grouping the document prints them in changed, and it
# changed to the one ABOUT.md §9 has always specified for a printed document.
# The tax LABELS also lost their trailing colon: `docsheet.sum_row()` is the
# same row the tax invoice uses, and that sheet has never punctuated them.

REPO = pathlib.Path(__file__).resolve().parent.parent

# ── The seeded schedule, claimed in full ───────────────────────────────────
#
# Captured by running the PRE-CHANGE `compute_tax_totals()` over these exact
# claims. Literals on purpose: a recomputation would agree with whatever the
# code does today, which is the one thing this test must not do.
#
# All 87 priced lines of the Sify schedule are 18%, so this is the uniform-rate
# case and the figures must not move by a paisa.
FULL_SUPPLY = {
    "claim_subtotal": 6177563.3,
    "net_payable":    6177563.3,
    "cgst_amount":    555980.7,
    "sgst_amount":    555980.7,
    "igst_amount":    0.0,
    "tax_amount":     1111961.4,
    "rounding_off":   0.3,
    "grand_total":    7289525.0,
}

# The first twelve priced lines — the size of bill ABOUT.md quotes for
# SF/RA/26-27/0001, and the one whose rounding line is non-zero.
FIRST_12_SUPPLY = {
    "claim_subtotal": 375069.0,
    "net_payable":    375069.0,
    "cgst_amount":    33756.21,
    "sgst_amount":    33756.21,
    "igst_amount":    0.0,
    "tax_amount":     67512.42,
    "rounding_off":   -0.42,
    "grand_total":    442581.0,
}


def _priced(boq_id, n=None):
    lines = [li for li in STORE["boqs"][boq_id]["line_items"]
             if not li["is_header"] and li["total_qty"] > 0]
    return lines[:n] if n else lines


@pytest.fixture()
def seeded(client):
    STORE["ra_bills"].clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()


@pytest.fixture()
def store_free():
    """
    For the pure-arithmetic tests, which touch no app state at all.

    `compute_tax_totals()` is a function of its arguments — no STORE, no
    request, no bill. Saying so with a fixture that only guards the collection
    keeps that property visible rather than incidental.
    """
    STORE["ra_bills"].clear()
    yield
    STORE["ra_bills"].clear()


def _supply_claims(boq_id, n=None):
    return [ra.build_claim(li, li["total_qty"], li["supply_rate"], 0.0,
                           li["supply_rate"], leg="supply")
            for li in _priced(boq_id, n)]


def _mixed_claims():
    """
    Two lines, two rates, deliberately clean numbers.

    1000.00 at 18% and 500.00 at 12%. The arithmetic is exact at every step, so
    the slab figures and the document figures agree to the paisa and the
    assertions below are about the grouping rather than about float noise.
    """
    line_18 = {"line_id": "aaaaaaaaaaaa", "item_no": "1", "section": "A",
               "description": "MS pipe", "unit": "Mtrs", "total_qty": 100.0,
               "supply_hsn": "73063090", "supply_gst_rate": 18.0}
    line_12 = {"line_id": "bbbbbbbbbbbb", "item_no": "2", "section": "A",
               "description": "Civil work", "unit": "Sq.Mtrs", "total_qty": 100.0,
               "supply_hsn": "995462", "supply_gst_rate": 12.0}
    return [ra.build_claim(line_18, 10, 100.0, 0.0, 100.0, leg="supply"),
            ra.build_claim(line_12, 10, 50.0, 0.0, 50.0, leg="supply")]


# ═══ 1. The uniform-rate answer did not move ═══════════════════════════════

def test_seeded_bill_totals_are_unchanged(seeded):
    """Every priced supply line of the Sify schedule, at one rate: 18%."""
    claims = _supply_claims(seeded)
    assert len(claims) == 87
    assert sorted({c["gst_rate"] for c in claims}) == [18.0]

    t = ra.compute_tax_totals(claims, [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    for key, expected in FULL_SUPPLY.items():
        assert t[key] == expected, f"{key} moved: {t[key]} != {expected}"


def test_seeded_twelve_line_bill_totals_are_unchanged(seeded):
    """The bill size ABOUT.md quotes, and the one with a real rounding line."""
    t = ra.compute_tax_totals(_supply_claims(seeded, 12), [],
                              tax_type="cgst_sgst", cgst_rate=9.0, sgst_rate=9.0)
    for key, expected in FIRST_12_SUPPLY.items():
        assert t[key] == expected, f"{key} moved: {t[key]} != {expected}"


def test_a_uniform_bill_produces_exactly_one_slab(seeded):
    slabs = ra.compute_tax_totals(_supply_claims(seeded), [])["tax_slabs"]
    assert len(slabs) == 1
    assert slabs[0]["gst_rate"] == 18.0
    assert slabs[0]["cgst_rate"] == 9.0 and slabs[0]["sgst_rate"] == 9.0
    assert slabs[0]["taxable_value"] == FULL_SUPPLY["claim_subtotal"]
    assert slabs[0]["line_count"] == 87


def test_document_rates_still_label_a_single_slab_bill(seeded):
    """`cgst_rate` / `sgst_rate` keep their meaning: what the tax line says."""
    t = ra.compute_tax_totals(_supply_claims(seeded), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    assert t["cgst_rate"] == 9.0
    assert t["sgst_rate"] == 9.0


# ═══ 2. Mixed-rate correctness ═════════════════════════════════════════════

def test_mixed_rate_bill_groups_into_two_slabs(store_free):
    t = ra.compute_tax_totals(_mixed_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    slabs = t["tax_slabs"]

    assert [s["gst_rate"] for s in slabs] == [12.0, 18.0]      # ascending
    assert [s["taxable_value"] for s in slabs] == [500.0, 1000.0]
    assert [s["line_count"] for s in slabs] == [1, 1]
    assert [s["hsn_sac"] for s in slabs] == [["995462"], ["73063090"]]


def test_mixed_rate_slab_taxable_values_sum_to_the_claim_total(store_free):
    t = ra.compute_tax_totals(_mixed_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    assert round(sum(s["taxable_value"] for s in t["tax_slabs"]), 2) == \
        t["claim_subtotal"] == 1500.0


def test_each_slabs_tax_is_its_own_taxable_times_its_own_rate(store_free):
    t = ra.compute_tax_totals(_mixed_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    for s in t["tax_slabs"]:
        expected = round(s["taxable_value"] * s["gst_rate"] / 100.0, 2)
        assert s["tax_amount"] == expected
        # …and the head split adds back up to it.
        assert round(s["cgst_amount"] + s["sgst_amount"] + s["igst_amount"], 2) \
            == expected

    # 500 @ 12% = 60.00 ; 1000 @ 18% = 180.00
    assert [s["tax_amount"] for s in t["tax_slabs"]] == [60.0, 180.0]
    assert [s["cgst_amount"] for s in t["tax_slabs"]] == [30.0, 90.0]


def test_mixed_rate_document_total_is_the_slab_sum_plus_rounding(store_free):
    t = ra.compute_tax_totals(_mixed_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    slab_tax = round(sum(s["tax_amount"] for s in t["tax_slabs"]), 2)

    assert t["tax_amount"] == slab_tax == 240.0
    assert t["cgst_amount"] == 120.0 and t["sgst_amount"] == 120.0
    assert t["grand_total"] == round(
        t["net_payable"] + slab_tax + t["rounding_off"], 2) == 1740.0


def test_the_mixed_bill_is_no_longer_taxed_at_the_flat_bill_rate(store_free):
    """
    The regression this whole change exists to end.

    Before, both lines were taxed at the bill's 9 + 9 regardless of what they
    stored: 1500 x 18% = 270.00. The 12% line is now taxed at 12%.
    """
    t = ra.compute_tax_totals(_mixed_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    assert t["tax_amount"] == 240.0
    assert t["tax_amount"] != 270.0


def test_mixed_rate_under_igst_splits_the_same_way(store_free):
    """The head is unchanged; only which column the slab lands in differs."""
    t = ra.compute_tax_totals(_mixed_claims(), [], tax_type="igst",
                              igst_rate=18.0)
    assert t["igst_amount"] == 240.0
    assert t["cgst_amount"] == 0.0 and t["sgst_amount"] == 0.0
    assert [s["igst_amount"] for s in t["tax_slabs"]] == [60.0, 180.0]
    assert [s["cgst_amount"] for s in t["tax_slabs"]] == [0.0, 0.0]


# ═══ 3. Nothing stored was touched ═════════════════════════════════════════

def test_a_claim_row_without_a_gst_rate_falls_back_to_the_bill_rate(store_free):
    """
    The no-migration guarantee.

    A row that predates the field is taxed at exactly what it was taxed at
    before this function read the field at all, so no stored bill has to be
    rewritten and no backfill has to run.
    """
    rows = _mixed_claims()
    for r in rows:
        r.pop("gst_rate")

    t = ra.compute_tax_totals(rows, [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    assert len(t["tax_slabs"]) == 1
    assert t["tax_slabs"][0]["gst_rate"] == 18.0        # 9 + 9, as declared
    assert t["tax_amount"] == 270.0                     # 1500 x 18%


def test_an_explicit_zero_gst_rate_is_a_real_nil_slab(store_free):
    """0.0 that is present means 0%. Only a MISSING field falls back."""
    rows = _mixed_claims()
    rows[1]["gst_rate"] = 0.0

    t = ra.compute_tax_totals(rows, [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    assert [s["gst_rate"] for s in t["tax_slabs"]] == [0.0, 18.0]
    assert t["tax_slabs"][0]["tax_amount"] == 0.0
    assert t["tax_amount"] == 180.0                     # only the 18% line


def test_a_stored_bills_tax_totals_are_never_recomputed(client, seeded):
    """
    An issued bill's figures are frozen, including ones this change disagrees
    with. `/ra/print` renders the record, not a fresh calculation.
    """
    claims = _supply_claims(seeded, 2)
    for c in claims:
        c["gst_rate"] = 12.0            # would compute differently today

    rid = "frozen-bill"
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": "SF/RA/26-27/0009", "fy": "26-27",
        "date": "2026-08-06", "boq_id": seeded, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "ra_no": 9, "leg": "supply", "claims": claims,
        "claim_subtotal": 111111.11, "deductions": [], "deduction_total": 0.0,
        "net_payable": 111111.11, "tax_type": "cgst_sgst",
        "cgst_rate": 9.0, "sgst_rate": 9.0, "igst_rate": 18.0,
        "cgst_amount": 11111.11, "sgst_amount": 22222.22, "igst_amount": 0.0,
        "tax_amount": 33333.33, "rounding_off": 0.0, "grand_total": 144444.44,
        "status": "draft", "issued_on": "", "cancelled_on": "",
        "cancel_reason": "", "notes": "",
        # APPROVED — CC-2 B7 refuses to print a bill that has not
        # completed its ladder, and this test is about the TAX BLOCK on
        # the printed sheet, not about the ladder. See
        # tests/conftest.py::printable for why it is written directly.
        "approval_status": "approved",
    }
    before = dict(STORE["ra_bills"][rid])

    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)

    assert STORE["ra_bills"][rid] == before, "printing mutated the record"
    assert "11,111.11" in html and "22,222.22" in html
    assert _inr(144_444.44) in html
    # No tax_slabs key, so it takes the legacy single-slab path unchanged.
    assert "tax_slabs" not in STORE["ra_bills"][rid]
    assert "Taxable @" not in html
    assert "Total CGST" not in html


# ═══ 4. The printed sheet ══════════════════════════════════════════════════

def test_single_slab_print_keeps_todays_tax_block(client, seeded):
    """
    A single-rate bill's printed sheet is byte-for-byte what it was.

    Verified out of band by rendering this same bill against the pre-change
    `ra.py` and diffing: 58,658 bytes, zero differing lines. What is pinned here
    is the tax block itself — the exact labels, and the absence of anything the
    multi-slab path would add.
    """
    lines = _priced(seeded, 12)
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-11", "notes": "",
        "ra_json": json.dumps({"lines": [
            {"line_id": li["line_id"], "qty": str(li["total_qty"]),
             "rate": str(li["supply_rate"])} for li in lines]}),
    })
    assert r.status_code == 302, r.data[:2000]
    rid = next(iter(STORE["ra_bills"]))

    assert len(STORE["ra_bills"][rid]["tax_slabs"]) == 1
    # CC-2 B7: an unapproved document does not print. This bill was raised
    # through /ra/create so it starts pending, and what is pinned below is the
    # printed TAX BLOCK, not the ladder.
    printable(STORE["ra_bills"][rid])
    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)

    assert "CGST @ 9%" in html
    assert "SGST @ 9%" in html
    assert "Taxable @" not in html          # no rate-wise table
    assert "Total CGST" not in html         # totals keep their rate label

    # The pinned figures reach the sheet.
    assert _inr(33_756.21) in html
    assert _inr(442_581.00) in html


def test_two_slab_print_carries_both_rate_rows(client, seeded):
    """A mixed bill gains the rate-wise table and drops the single rate label."""
    rid = "mixed-bill"
    claims = _mixed_claims()
    t = ra.compute_tax_totals(claims, [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": "SF/RA/26-27/0010", "fy": "26-27",
        "date": "2026-08-06", "boq_id": seeded, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "ra_no": 10, "leg": "supply", "claims": claims,
        "claim_subtotal": t["claim_subtotal"], "deductions": [],
        "deduction_total": 0.0, "net_payable": t["net_payable"],
        "tax_type": t["tax_type"], "cgst_rate": t["cgst_rate"],
        "sgst_rate": t["sgst_rate"], "igst_rate": t["igst_rate"],
        "cgst_amount": t["cgst_amount"], "sgst_amount": t["sgst_amount"],
        "igst_amount": t["igst_amount"], "tax_amount": t["tax_amount"],
        "tax_slabs": t["tax_slabs"], "rounding_off": t["rounding_off"],
        "grand_total": t["grand_total"],
        "status": "draft", "issued_on": "", "cancelled_on": "",
        "cancel_reason": "", "notes": "",
        # APPROVED - CC-2 B7. This test is about the printed tax block,
        # not the ladder. See tests/conftest.py::printable.
        "approval_status": "approved",
    }

    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)

    assert "Taxable @ 12%" in html
    assert "Taxable @ 18%" in html
    assert "CGST 6% + SGST 6%" in html
    assert "CGST 9% + SGST 9%" in html
    assert "995462" in html and "73063090" in html
    # Both slab taxable values and both slab taxes.
    assert _inr(500.00) in html and _inr(1_000.00) in html
    assert "60.00" in html and "180.00" in html
    # The totals no longer claim a single rate.
    assert "Total CGST" in html and "Total SGST" in html
    assert "CGST @ 9%" not in html


# ═══ 4b. The rate-wise column foots against the document total ═════════════
#
# GSTR-1 is filed RATE-WISE: each slab's taxable value and tax are their own
# line on the return, read off this document. So the slab figures have to be the
# ones the totals were computed from — `compute_tax_totals()` rounds each slab
# once and sums the ROUNDED slabs.
#
# The fixture below is chosen so the two schemes genuinely disagree. 1000.00 at
# 5% and 1003.25 at 12% give a CGST column of 25.00 + 60.20 = 85.20, where
# rounding once from the unrounded sum gives 85.19. If the arithmetic ever goes
# back to rounding at document level, these fail rather than drifting quietly.

def _footing_claims():
    """1000.00 @ 5% and 1003.25 @ 12% — where the two rounding schemes differ."""
    line_5 = {"line_id": "cccccccccccc", "item_no": "1", "section": "A",
              "description": "Nil-ish rated goods", "unit": "Nos",
              "total_qty": 100.0, "supply_hsn": "73063090",
              "supply_gst_rate": 5.0}
    line_12 = {"line_id": "dddddddddddd", "item_no": "2", "section": "A",
               "description": "Works contract", "unit": "Sq.Mtrs",
               "total_qty": 100.0, "supply_hsn": "995462",
               "supply_gst_rate": 12.0}
    return [ra.build_claim(line_5, 10, 100.0, 0.0, 100.0, leg="supply"),
            ra.build_claim(line_12, 25, 40.13, 0.0, 40.13, leg="supply")]


def test_the_slab_column_sums_to_the_document_total(store_free):
    """Every printed rate-wise column adds up to the total beneath it."""
    t = ra.compute_tax_totals(_footing_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    slabs = t["tax_slabs"]
    assert len(slabs) == 2

    assert round(sum(s["cgst_amount"] for s in slabs), 2) == t["cgst_amount"]
    assert round(sum(s["sgst_amount"] for s in slabs), 2) == t["sgst_amount"]
    assert round(sum(s["igst_amount"] for s in slabs), 2) == t["igst_amount"]
    assert round(sum(s["tax_amount"] for s in slabs), 2) == t["tax_amount"]
    assert round(sum(s["taxable_value"] for s in slabs), 2) == t["claim_subtotal"]


def test_the_footing_fixture_really_does_discriminate(store_free):
    """
    Without this, the test above would pass under either rounding scheme.

    1000.00 x 2.5% = 25.0000 and 1003.25 x 6% = 60.1950. Summed rounded that is
    85.20; rounded once from 85.1950 it is 85.19. The document must say 85.20,
    because 25.00 and 60.20 are the two figures printed above it.
    """
    t = ra.compute_tax_totals(_footing_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    slabs = t["tax_slabs"]

    assert [s["taxable_value"] for s in slabs] == [1000.0, 1003.25]
    assert [s["cgst_amount"] for s in slabs] == [25.0, 60.2]

    round_once = round(1000.0 * 2.5 / 100.0 + 1003.25 * 6.0 / 100.0, 2)
    assert round_once == 85.19                    # the scheme NOT chosen
    assert t["cgst_amount"] == 85.2               # the scheme chosen


def test_a_slabs_own_total_foots_from_its_head_parts(store_free):
    """A slab row's tax is its CGST and SGST added, not the rate applied again."""
    t = ra.compute_tax_totals(_footing_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    for s in t["tax_slabs"]:
        assert s["tax_amount"] == round(
            s["cgst_amount"] + s["sgst_amount"] + s["igst_amount"], 2)


def test_the_grand_total_identity_still_holds_on_the_footing_bill(store_free):
    t = ra.compute_tax_totals(_footing_claims(), [], tax_type="cgst_sgst",
                              cgst_rate=9.0, sgst_rate=9.0)
    assert t["grand_total"] == round(
        t["net_payable"] + t["tax_amount"] + t["rounding_off"], 2)


# ═══ 5. The import direction that made this the right place ════════════════

def test_ra_does_not_import_invoice(store_free):
    """
    §2b's load-bearing prohibition, re-asserted where the tax work landed.

    The reason `ra.py` may not import `invoice.py` is precisely that the RA
    bill's tax block is per-line and the sell chain's is document-level. This
    change is what finally makes that true of the arithmetic, so it is also the
    change most tempted to reach for the other module's helpers.
    """
    tree = ast.parse((REPO / "ra.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    for forbidden in ("invoice", "proforma", "purchase", "product", "spec"):
        assert forbidden not in imported, f"ra.py must not import {forbidden}.py"
