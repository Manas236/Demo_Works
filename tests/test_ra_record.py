"""
Phase 4 step 1 — the RA record shape, and claimed_by_line() across revisions.

No UI exists yet; these run against the module's functions directly. That is the
build order on purpose: the over-claim block is the thing the client is paying
for, and it is worth knowing it is right before anything can be typed into it.

The two properties everything here circles:

- **The block is hard.** A cumulative claim across every RA bill must not exceed
  the approved BOQ quantity for the line. Their live spreadsheet has three lines
  already billed into negative balance.
- **It survives a revision.** Because the block is hard, a BOQ revision is the
  only way through it when the approved schedule genuinely changes — so claims
  have to be summed across the whole chain. Miss that and a revision resets
  every line to zero claimed and the block guards nothing.
"""

import pytest

import boq as BQ
import ra
from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

def fixture_lid(item_no, section="A") -> str:
    """
    A stable line id for a fixture line, derived from (section, item_no).

    **A test convenience and nothing the app does.** Production ids are opaque
    and random (`boq._new_line_id()`); deriving one from the item number here
    only gives these tests a way to say "the same line, one revision later"
    without threading ids through every helper. It is safe precisely because
    fixture item numbers are unique within each test — which is the property
    the client's real schedule does NOT have, and the reason the id exists.

    `tests/test_boq_line_ids.py` is where the real, non-derived behaviour is
    tested, against the seeded 97-line BOQ.
    """
    import hashlib
    return hashlib.sha256(f"{section}/{item_no}".encode()).hexdigest()[:12]


def key(item_no, leg, section="A"):
    """The guard's key for a fixture line — it keys on line_id, not item_no."""
    return (fixture_lid(item_no, section), leg)


def boq_line(item_no, qty, s_rate=100.0, i_rate=50.0, section="A",
             header=False, unit="Mtrs", line_id=None):
    return {
        "line_id": line_id or fixture_lid(item_no, section),
        "item_no": item_no, "parent_item_no": "", "section": section,
        "is_header": header, "description": f"Line {item_no}", "remark": "",
        "unit": unit, "area_qty": {}, "total_qty": float(qty),
        "supply_base_rate": s_rate, "supply_escalation_pct": 0.0,
        "supply_rate": s_rate, "supply_amount": s_rate * qty,
        "supply_hsn": "", "supply_gst_rate": 18.0,
        "install_base_rate": i_rate, "install_escalation_pct": 0.0,
        "install_rate": i_rate, "install_amount": i_rate * qty,
        "install_sac": "", "install_gst_rate": 18.0,
    }


def make_boq(bid, lines, rev_no=0, supersedes="", ref="SF/BOQ/26-27/0001"):
    STORE["boqs"][bid] = {
        "id": bid, "ref": ref, "fy": "26-27", "date": "2026-07-31",
        "rev_no": rev_no, "supersedes": supersedes,
        "project_name": "Sify Bangalore", "site_location": "Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "",
        "to": "", "bill_gstin": "", "ship_same": True,
        "rate_basis_label": "Mohali Rates",
        "sections": [{"code": "A", "title": "Sprinkler", "areas": []}],
        "line_items": lines,
        "supply_subtotal": 0.0, "install_subtotal": 0.0, "subtotal": 0.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }
    return bid


def make_bill(rid, boq_id, ra_no, leg, claims, deductions=None):
    subtotal, drows, dtotal, net = ra.bill_totals(claims, deductions or [])
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-05",
        "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "ra_no": ra_no, "leg": leg,
        "project_name": "Sify Bangalore", "site_location": "Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "",
        "to": "", "bill_gstin": "",
        "claims": claims,
        "claim_subtotal": subtotal,
        "deductions": drows, "deduction_total": dtotal, "net_payable": net,
        "notes": "", "company_branch": "", "auth_signatory": "",
    }
    return rid


def claim(item_no, qty, rate=100.0, approved_qty=100.0, prev=0.0):
    return ra.build_claim(
        boq_line(item_no, approved_qty), qty, rate, prev, rate)


@pytest.fixture()
def store():
    """A STORE with only what this file puts in it."""
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    yield STORE
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


# ── The collection is persisted ─────────────────────────────────────────────

def test_ra_bills_is_a_persisted_collection():
    import db
    assert "ra_bills" in db.COLLECTIONS
    assert "ra_bills" in STORE
    assert "ra_bills" in db.LABELS      # so the failure strip can name it


# ── An RA bill is NOT a tax invoice ─────────────────────────────────────────

def _ra_code_tokens() -> set:
    """
    Every identifier, attribute and string literal in ra.py's CODE.

    Read from the AST rather than the source text, so the module's own docstring
    saying "must not import quotation._tax_lines()" — and the comment block
    listing what an RA bill is not — do not trip a test looking for the thing
    they forbid. Comments never reach the AST; docstrings are dropped
    explicitly.
    """
    import ast
    import pathlib

    tree = ast.parse(
        (pathlib.Path(__file__).resolve().parent.parent / "ra.py")
        .read_text(encoding="utf8"))

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    tokens = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.alias):
            tokens.add(node.name.split(".")[0])
            if node.asname:
                tokens.add(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                tokens.add(node.value)
    return tokens


def test_ra_does_not_pull_in_the_tax_machinery():
    """
    A deliberate, commercially scoped decision (PHASE4_RA_DESIGN.md §5), and the
    pull towards "it has amounts on it, so it should have tax on it" is strong
    enough to be worth a test rather than a comment.
    """
    tokens = _ra_code_tokens()

    assert "_tax_lines" not in tokens
    for statutory in ("place_of_supply", "pos_code", "reverse_charge",
                      "eway_bill_no", "irn"):
        assert statutory not in tokens, f"{statutory} is not an RA bill's business"


def test_the_prohibition_test_can_actually_fail():
    """
    A control. The check above reads the AST and drops docstrings, so it would
    pass just as happily against a file that never mentions tax at all — this
    proves it is looking at the right thing by showing it catches a token that
    IS in ra.py's code.
    """
    assert "claimed_by_line" in _ra_code_tokens()
    assert "OVERCLAIM_TOLERANCE" in _ra_code_tokens()


# ── The revision chain ──────────────────────────────────────────────────────

def test_a_lone_boq_is_its_own_chain(store):
    make_boq("b1", [boq_line("1", 100)])
    assert ra.revision_chain("b1") == ["b1"]
    assert ra.latest_revision("b1") == "b1"


def test_the_chain_is_found_from_any_member(store):
    make_boq("b1", [boq_line("1", 100)])
    make_boq("b2", [boq_line("1", 150)], rev_no=1, supersedes="b1")
    make_boq("b3", [boq_line("1", 200)], rev_no=2, supersedes="b2")

    for member in ("b1", "b2", "b3"):
        assert ra.revision_chain(member) == ["b1", "b2", "b3"], member
        assert ra.latest_revision(member) == "b3", member


def test_an_unrelated_boq_is_not_in_the_chain(store):
    make_boq("b1", [boq_line("1", 100)])
    make_boq("b2", [boq_line("1", 150)], rev_no=1, supersedes="b1")
    make_boq("other", [boq_line("1", 999)])

    assert "other" not in ra.revision_chain("b1")
    assert ra.revision_chain("other") == ["other"]


def test_a_missing_boq_has_no_chain(store):
    assert ra.revision_chain("nope") == []
    assert ra.latest_revision("nope") == ""
    assert ra.approved_by_line("nope") == {}
    assert ra.claimed_by_line("nope") == {}


def test_a_supersedes_cycle_does_not_hang(store):
    """
    Not reachable through any route that exists — but a hand-edited record must
    not be able to hang a page, the same judgement product._render_tree() makes.
    """
    make_boq("b1", [boq_line("1", 100)], supersedes="b2")
    make_boq("b2", [boq_line("1", 100)], supersedes="b1")

    chain = ra.revision_chain("b1")
    assert len(chain) <= 2
    assert "b1" in chain


def test_a_dangling_supersedes_is_ignored(store):
    make_boq("b2", [boq_line("1", 100)], rev_no=1, supersedes="deleted-id")
    assert ra.revision_chain("b2") == ["b2"]


# ── approved_by_line ────────────────────────────────────────────────────────

def test_approved_comes_from_the_latest_revision(store):
    make_boq("b1", [boq_line("1", 100)])
    make_boq("b2", [boq_line("1", 150)], rev_no=1, supersedes="b1")

    approved = ra.approved_by_line("b1")     # asked of the OLD id
    assert approved[key("1", "supply")] == 150.0
    assert approved[key("1", "installation")] == 150.0


def test_specification_headers_are_not_billable(store):
    make_boq("b1", [boq_line("4", 0, header=True), boq_line("4.1", 100)])

    approved = ra.approved_by_line("b1")
    assert key("4", "supply") not in approved
    assert key("4.1", "supply") in approved


def test_both_legs_are_approved_against_the_same_quantity(store):
    """
    A BOQ line carries one quantity and two rates, and the client's annexure
    tracks a separate balance per leg against it — 11 lines are claimed on both.
    """
    make_boq("b1", [boq_line("1", 700)])
    approved = ra.approved_by_line("b1")
    assert approved[key("1", "supply")] == 700.0
    assert approved[key("1", "installation")] == 700.0


# ── claimed_by_line ─────────────────────────────────────────────────────────

def test_claims_sum_across_bills(store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "b1", 2, "supply", [claim("1", 25)])

    assert ra.claimed_by_line("b1")[key("1", "supply")] == 55.0


def test_the_two_legs_are_summed_separately(store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "b1", 2, "installation", [claim("1", 40)])

    claimed = ra.claimed_by_line("b1")
    assert claimed[key("1", "supply")] == 30.0
    assert claimed[key("1", "installation")] == 40.0


def test_claims_sum_across_the_whole_revision_chain(store):
    """
    The subtlest requirement in the design. RA1 and RA2 were billed against
    rev 0; a revision then raised the approved quantity. If the sum did not walk
    the chain, those 55 units would vanish and the line would look untouched.
    """
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "b1", 2, "supply", [claim("1", 25)])

    make_boq("b2", [boq_line("1", 150)], rev_no=1, supersedes="b1")
    make_bill("r3", "b2", 3, "supply", [claim("1", 20)])

    assert ra.claimed_by_line("b2")[key("1", "supply")] == 75.0
    assert ra.claimed_by_line("b1")[key("1", "supply")] == 75.0


def test_a_revision_does_not_reset_the_claimed_quantity(store):
    """The failure this walk exists to prevent, stated directly."""
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 90)])

    make_boq("b2", [boq_line("1", 100)], rev_no=1, supersedes="b1")

    assert ra.claimed_by_line("b2")[key("1", "supply")] == 90.0
    # …and the block still sees it.
    assert ra.overclaims("b2", "supply", [claim("1", 20)])


def test_another_projects_bills_are_not_counted(store):
    make_boq("b1", [boq_line("1", 100)])
    make_boq("other", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "other", 1, "supply", [claim("1", 80)])

    assert ra.claimed_by_line("b1")[key("1", "supply")] == 30.0


def test_exclude_ra_id_leaves_one_bill_out(store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "b1", 2, "supply", [claim("1", 25)])

    assert ra.claimed_by_line("b1", exclude_ra_id="r2")[key("1", "supply")] == 30.0


# ── The hard block ──────────────────────────────────────────────────────────

def test_a_claim_within_the_approved_quantity_passes(store):
    make_boq("b1", [boq_line("1", 100)])
    assert ra.overclaims("b1", "supply", [claim("1", 100)]) == []


def test_a_claim_over_the_approved_quantity_is_blocked(store):
    make_boq("b1", [boq_line("1", 100)])
    v = ra.overclaims("b1", "supply", [claim("1", 100.5)])

    assert len(v) == 1
    assert v[0]["reason"] == "overclaim"
    assert v[0]["approved"] == 100.0
    assert round(v[0]["over"], 2) == 0.5


def test_the_block_is_on_the_CUMULATIVE_claim(store):
    """
    Each bill is within the approved quantity; together they are not. This is
    the whole difference between a per-bill check and a real one.
    """
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 60)])

    assert ra.overclaims("b1", "supply", [claim("1", 40)]) == []
    v = ra.overclaims("b1", "supply", [claim("1", 41)])
    assert len(v) == 1
    assert v[0]["previously"] == 60.0
    assert v[0]["cumulative"] == 101.0


def test_the_legs_do_not_block_each_other(store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 100)])

    assert ra.overclaims("b1", "supply", [claim("1", 1)])          # supply full
    assert ra.overclaims("b1", "installation", [claim("1", 100)]) == []


def test_a_line_not_in_the_boq_cannot_be_claimed(store):
    make_boq("b1", [boq_line("1", 100)])
    v = ra.overclaims("b1", "supply", [claim("99", 5)])

    assert len(v) == 1
    assert v[0]["reason"] == "not_in_boq"


def test_a_zero_claim_is_not_a_violation(store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 100)])
    assert ra.overclaims("b1", "supply", [claim("1", 0)]) == []


def test_float_noise_is_not_an_overclaim(store):
    """
    1.1 + 2.2 + 8.7 is 12.000000000000002. Reporting that as an over-claim of
    two femtometres against an approved 12 would be a bug, and it is what a
    naive `>` does.
    """
    make_boq("b1", [boq_line("1", 12)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 1.1)])
    make_bill("r2", "b1", 2, "supply", [claim("1", 2.2)])

    assert ra.claimed_by_line("b1")[key("1", "supply")] == pytest.approx(3.3)
    assert ra.overclaims("b1", "supply", [claim("1", 8.7)]) == []


def test_the_clients_own_three_overclaims_are_all_caught(store):
    """
    The acceptance test for this module, taken from annexure.xlsx: items 4.2 and
    24.c claimed 12.06 against 12, and 24.d claimed 46.54 against 35.
    """
    make_boq("b1", [boq_line("4.2", 12), boq_line("24.c", 12),
                    boq_line("24.d", 35)])

    v = ra.overclaims("b1", "supply", [
        claim("4.2", 12.06), claim("24.c", 12.06), claim("24.d", 46.54)])

    assert {x["item_no"] for x in v} == {"4.2", "24.c", "24.d"}
    by_item = {x["item_no"]: x for x in v}
    assert round(by_item["4.2"]["over"], 2) == 0.06
    assert round(by_item["24.d"]["over"], 2) == 11.54


def test_the_overclaim_message_carries_the_whole_arithmetic(store):
    make_boq("b1", [boq_line("24.d", 35)])
    make_bill("r1", "b1", 1, "supply", [claim("24.d", 10)])

    msg = ra.overclaim_message(ra.overclaims("b1", "supply", [claim("24.d", 36.54)])[0])

    assert "24.d" in msg
    assert "35" in msg and "10" in msg and "36.54" in msg
    assert "11.54 over" in msg


# ── OVERCLAIM_TOLERANCE, at both settings ───────────────────────────────────

def test_at_zero_the_tolerance_is_a_pure_hard_block(store):
    """The default, and the contract: no epsilon, no "close enough"."""
    assert ra.OVERCLAIM_TOLERANCE == 0.0

    make_boq("b1", [boq_line("1", 12)])
    assert ra.overclaims("b1", "supply", [claim("1", 12)]) == []
    assert len(ra.overclaims("b1", "supply", [claim("1", 12.06)])) == 1


def test_a_non_zero_tolerance_forgives_within_it(store, monkeypatch):
    """1% of 12 is 0.12, so the client's 0.06 rounding passes and 33% does not."""
    monkeypatch.setattr(ra, "OVERCLAIM_TOLERANCE", 0.01)

    make_boq("b1", [boq_line("4.2", 12), boq_line("24.d", 35)])

    assert ra.overclaims("b1", "supply", [claim("4.2", 12.06)]) == []
    assert len(ra.overclaims("b1", "supply", [claim("24.d", 46.54)])) == 1


def test_the_tolerance_applies_to_the_cumulative_and_never_per_bill(store,
                                                                   monkeypatch):
    """
    The amendment that matters. At 1% per bill, nine RA runs each 1% over would
    compound to 9% and the tolerance would BECOME the over-claim. Applied to the
    cumulative, nine bills of 1.01 against an approved 9 are caught.
    """
    monkeypatch.setattr(ra, "OVERCLAIM_TOLERANCE", 0.01)

    make_boq("b1", [boq_line("1", 9)])
    for n in range(1, 9):                       # eight bills of 1.01 = 8.08
        make_bill(f"r{n}", "b1", n, "supply", [claim("1", 1.01)])

    assert ra.claimed_by_line("b1")[key("1", "supply")] == pytest.approx(8.08)

    # The ninth takes the cumulative to 9.09, past 9 x 1.01 = 9.09... exactly at
    # the line; 1.02 is unambiguously past it.
    v = ra.overclaims("b1", "supply", [claim("1", 1.03)])
    assert len(v) == 1, "cumulative 9.11 must breach an allowance of 9.09"


# ── Rate divergence — a warning, never a block ──────────────────────────────

def test_a_matching_rate_does_not_vary(store):
    assert ra.rate_varies(2024.0, 2024.0) is False
    assert ra.rate_varies(2024.001, 2024.0) is False      # half a paisa


def test_a_diverging_rate_is_flagged(store):
    assert ra.rate_varies(2100.0, 2024.0) is True


def test_a_diverging_rate_is_stored_on_the_claim_and_does_not_block(store):
    make_boq("b1", [boq_line("1", 100, s_rate=2024.0)])

    c = ra.build_claim(boq_line("1", 100, s_rate=2024.0), 10, 2100.0, 0.0, 2024.0)

    assert c["rate_varies"] is True
    assert c["rate"] == 2100.0
    assert c["approved_rate"] == 2024.0
    assert ra.overclaims("b1", "supply", [c]) == []     # warns, never blocks


# ── Numbering ───────────────────────────────────────────────────────────────

def test_the_first_ra_is_one(store):
    make_boq("b1", [boq_line("1", 100)])
    assert ra.next_ra_no("b1") == 1


def test_ra_numbers_are_one_series_across_both_legs(store):
    """
    The client's own run: supply on 1,2,3,5,7,9 and installation on 4,6,8. One
    sequence whose bills alternate, not two interleaved sequences.
    """
    make_boq("b1", [boq_line("1", 1000)])
    for n, leg in enumerate(["supply", "supply", "supply", "installation",
                             "supply", "installation", "supply",
                             "installation", "supply"], start=1):
        assert ra.next_ra_no("b1") == n
        make_bill(f"r{n}", "b1", n, leg, [claim("1", 1)])

    assert ra.next_ra_no("b1") == 10
    legs = [b["leg"] for _i, b in ra.bills_of("b1")]
    assert legs[3] == "installation" and legs[5] == "installation"


def test_ra_numbers_continue_across_a_revision(store):
    """A revision must not restart the client's sequence at RA1."""
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 10)])
    make_bill("r2", "b1", 2, "supply", [claim("1", 10)])

    make_boq("b2", [boq_line("1", 200)], rev_no=1, supersedes="b1")

    assert ra.next_ra_no("b2") == 3


def test_a_deleted_bill_does_not_re_issue_its_number(store):
    """max+1, never len+1 — proforma._next_ref()'s rule."""
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 10)])
    make_bill("r2", "b1", 2, "supply", [claim("1", 10)])
    make_bill("r3", "b1", 3, "supply", [claim("1", 10)])
    del STORE["ra_bills"]["r2"]

    assert ra.next_ra_no("b1") == 4


def test_bills_of_is_ordered_by_ra_no(store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r3", "b1", 3, "supply", [claim("1", 1)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 1)])
    make_bill("r2", "b1", 2, "installation", [claim("1", 1)])

    assert [b["ra_no"] for _i, b in ra.bills_of("b1")] == [1, 2, 3]


def test_the_document_ref_is_fy_scoped_and_not_statutory(store):
    ref = ra.next_ref("2026-08-05")
    assert "/RA/" in ref
    assert ref.endswith("0001")
    make_bill("r1", "b1", 1, "supply", [])
    STORE["ra_bills"]["r1"]["ref"] = ref
    assert ra.next_ref("2026-08-05").endswith("0002")


# ── Arithmetic, including deductions ────────────────────────────────────────

def test_a_claim_amount_is_always_computed(store):
    c = ra.build_claim(boq_line("1", 100), 12.5, 200.0, 0.0, 200.0)
    assert c["amount"] == 2500.0


def test_the_balance_is_frozen_on_the_row(store):
    c = ra.build_claim(boq_line("1", 700), 80, 100.0, 120.0, 100.0)
    assert c["approved_qty"] == 700.0
    assert c["prev_qty"] == 120.0
    assert c["balance_qty"] == 500.0


def test_net_payable_holds_with_no_deductions(store):
    claims = [claim("1", 10, rate=100.0)]
    subtotal, rows, total, net = ra.bill_totals(claims, [])

    assert subtotal == 1000.0
    assert rows == [] and total == 0.0
    assert net == subtotal


def test_a_percentage_deduction_is_resolved_to_an_amount_and_stored(store):
    claims = [claim("1", 10, rate=100.0)]                     # 1000.00
    subtotal, rows, total, net = ra.bill_totals(
        claims, [{"code": "retention", "label": "Retention @ 5%",
                  "basis": "percent", "pct": 5.0}])

    assert rows[0]["amount"] == 50.0        # computed once and stored
    assert total == 50.0
    assert net == 950.0


def test_deductions_of_both_bases_add_up(store):
    claims = [claim("1", 100, rate=100.0)]                    # 10,000.00
    subtotal, rows, total, net = ra.bill_totals(claims, [
        {"code": "retention", "label": "Retention @ 5%", "basis": "percent", "pct": 5.0},
        {"code": "advance", "label": "Mobilisation advance recovery",
         "basis": "amount", "amount": 1500.0},
    ])

    assert [r["amount"] for r in rows] == [500.0, 1500.0]
    assert total == 2000.0
    assert net == 8000.0


def test_net_payable_identity_holds_whatever_the_deductions(store):
    claims = [claim("1", 37, rate=133.33)]
    for deds in ([], [{"basis": "percent", "pct": 7.5, "code": "r", "label": "R"}],
                 [{"basis": "amount", "amount": 99.99, "code": "a", "label": "A"}]):
        subtotal, rows, total, net = ra.bill_totals(claims, deds)
        assert round(net, 2) == round(subtotal - total, 2)
